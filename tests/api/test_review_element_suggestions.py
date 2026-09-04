"""F-051 T3: a sugestão assistida de identidade na REVISÃO, a partir do rótulo do modelo (ADR-0063).

O que estes testes protegem, em uma frase cada: a listagem devolve sugestão rotulada
`unresolved`, nunca identidade; a mesma revisão produz sempre as mesmas sugestões, na
mesma ordem; proposta já coberta por declaração ATIVA não é sugerida; sugerir não escreve
nada — o job inteiro fica intacto até alguém confirmar; um rótulo ERRADO de propósito
ainda é sugerido, e pode ser recusado sem nada ser escrito; a sugestão recusada não volta
a aparecer; e sem rótulo nenhum a listagem responde vazia sem tocar em nada.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import select

from croquito_api.config import ApiSettings
from croquito_api.database import (
    Database,
    JobRecord,
    ProjectRecord,
    ReviewElementSuggestionRejectionRecord,
    ReviewRevisionRecord,
    UploadRecord,
)
from croquito_api.main import create_app
from croquito_core.ids import new_uuid7
from croquito_worker.vision import PixelLine, PixelPoint, VisionProposal, VisionProposalSet

JOB_ID = UUID("00000000-0000-7000-8000-0000000e1e51")

DATASET_ID = "synthetic-toca-suggestions-v1"
DIGEST = "c" * 64


def _headers(
    tenant_id: str = "tenant-a", roles: str = "engineer", key: str | None = "k-1"
) -> dict[str, str]:
    headers = {"Authorization": f"Bearer test:{tenant_id}:reviewer:{roles}"}
    if key is not None:
        headers["Idempotency-Key"] = key
    return headers


def _proposal(id_: str, *, label: str | None) -> VisionProposal:
    return VisionProposal(
        id=id_,
        kind="line",
        geometry=PixelLine(start=PixelPoint(x=0, y=0), end=PixelPoint(x=10, y=0)),
        algorithm="fixture",
        quality_score=0.9,
        label=label,
    )


def _proposal_set(proposals: list[VisionProposal]) -> VisionProposalSet:
    return VisionProposalSet(
        dataset_id=DATASET_ID,
        page_number=1,
        image_sha256=DIGEST,
        image_width_px=300,
        image_height_px=200,
        configured_limits={"line": 80, "circle": 16, "contour": 16},
        limit_reached=[],
        proposals=proposals,
        safety_notes=["fixture", "pixels", "não exportável"],
    )


def _active_declaration(*, element_ref: str, label: str, proposal_ids: list[str]) -> dict[str, Any]:
    return {
        "element_ref": element_ref,
        "label": label,
        "proposal_ids": proposal_ids,
        "status": "active",
        "declared_by": "reviewer",
        "declared_role": "engineer",
        "declared_at": datetime.now(UTC).isoformat(),
    }


def _client(
    tmp_path: Path,
    *,
    proposals: VisionProposalSet | None,
    declarations: list[dict[str, Any]] | None = None,
    tenant_id: str = "tenant-a",
    job_id: UUID = JOB_ID,
) -> TestClient:
    url = f"sqlite+pysqlite:///{tmp_path / 'suggestions.db'}"
    database = Database(url)
    database.create_schema()
    settings = ApiSettings(
        database_url=url,
        artifact_bucket="test",
        aws_region="sa-east-1",
        aws_endpoint_url=None,
        queue_url=None,
        oidc_issuer=None,
        oidc_audience=None,
        web_origin="http://localhost:5173",
        allow_test_tokens=True,
    )
    now = datetime.now(UTC)
    with database.sessions.begin() as session:
        session.add(
            ProjectRecord(
                id="project",
                tenant_id=tenant_id,
                name="Teste",
                default_unit="m",
                created_by="worker",
                expires_at=now,
            )
        )
        session.add(
            UploadRecord(
                id="upload",
                tenant_id=tenant_id,
                object_key="protected/synthetic.pdf",
                filename="x.pdf",
                content_type="application/pdf",
                size_bytes=1,
                sha256="a" * 64,
            )
        )
        session.flush()
        session.add(
            JobRecord(
                id=str(job_id),
                tenant_id=tenant_id,
                project_id="project",
                upload_id="upload",
                status="REVIEW_REQUIRED",
                stage="PREVIEWING",
                expires_at=now,
            )
        )
        session.flush()
        session.add(
            ReviewRevisionRecord(
                id=str(new_uuid7()),
                tenant_id=tenant_id,
                job_id=str(job_id),
                version=1,
                packet_json={},
                associations_json={},
                proposals_json=proposals.model_dump(mode="json") if proposals is not None else None,
                element_declarations_json=declarations or [],
                created_by="worker",
                created_at=now,
            )
        )
    return TestClient(create_app(settings=settings, database=database))


def _database(client: TestClient) -> Database:
    return cast(Database, cast(Any, client.app).state.database)


def _list_suggestions(client: TestClient, *, job_id: UUID = JOB_ID, **headers_kwargs: Any) -> Any:
    return client.get(
        f"/v1/jobs/{job_id}/review/elements/suggestions", headers=_headers(**headers_kwargs)
    )


def _reject(
    client: TestClient,
    *,
    job_id: UUID = JOB_ID,
    suggestion_id: str,
    reason: str,
    key: str = "reject-1",
) -> Any:
    return client.post(
        f"/v1/jobs/{job_id}/review/elements/suggestions/{suggestion_id}/rejections",
        headers=_headers(key=key),
        json={"reason": reason},
    )


def test_listagem_devolve_sugestao_rotulada_unresolved_nunca_identidade(tmp_path: Path) -> None:
    proposals = _proposal_set(
        [
            _proposal("vp_1111111111111111", label="B"),
            _proposal("vp_2222222222222222", label="B"),
        ]
    )
    client = _client(tmp_path, proposals=proposals)

    response = _list_suggestions(client)

    assert response.status_code == 200
    body = response.json()
    assert body["review_version"] == 1
    assert len(body["suggestions"]) == 1
    suggestion = body["suggestions"][0]
    assert suggestion["status"] == "unresolved"
    assert suggestion["label"] == "B"
    assert suggestion["proposal_ids"] == ["vp_1111111111111111", "vp_2222222222222222"]
    assert suggestion["suggestion_id"].startswith("els_")

    # Determinístico: chamar de novo devolve exatamente a mesma sugestão, na mesma ordem.
    again = _list_suggestions(client).json()
    assert again == body


def test_sugestao_nao_confirmada_nao_produz_efeito_algum(tmp_path: Path) -> None:
    """Lê o job inteiro depois de gerar sugestões: nenhuma revisão nova, nenhuma identidade."""
    proposals = _proposal_set([_proposal("vp_1111111111111111", label="B")])
    client = _client(tmp_path, proposals=proposals)

    _list_suggestions(client)
    _list_suggestions(client)

    with _database(client).sessions.begin() as session:
        revisions = list(
            session.scalars(
                select(ReviewRevisionRecord).where(ReviewRevisionRecord.job_id == str(JOB_ID))
            )
        )
        assert len(revisions) == 1
        assert revisions[0].element_declarations_json == []
        assert revisions[0].version == 1


def test_proposta_ja_coberta_por_declaracao_ativa_nao_e_sugerida(tmp_path: Path) -> None:
    proposals = _proposal_set(
        [
            _proposal("vp_1111111111111111", label="B"),
            _proposal("vp_2222222222222222", label="C"),
        ]
    )
    declarations = [
        _active_declaration(element_ref="EL-001", label="B", proposal_ids=["vp_1111111111111111"])
    ]
    client = _client(tmp_path, proposals=proposals, declarations=declarations)

    body = _list_suggestions(client).json()

    assert [item["label"] for item in body["suggestions"]] == ["C"]


def test_rotulo_errado_de_proposito_pode_ser_recusado_e_nada_e_escrito(tmp_path: Path) -> None:
    """A «grade B» é, na verdade, o balão C espelhado — rótulo errado do modelo, de propósito.

    Prova que a sugestão é editável/recusável antes do ato: ela aparece mesmo com o rótulo
    errado (o produtor não sabe que está errado), e o revisor pode recusá-la sem que nada
    seja declarado.
    """
    proposals = _proposal_set([_proposal("vp_1111111111111111", label="B")])
    client = _client(tmp_path, proposals=proposals)
    before = datetime.now(UTC)
    suggestion = _list_suggestions(client).json()["suggestions"][0]
    assert suggestion["label"] == "B"

    rejection = _reject(
        client,
        suggestion_id=suggestion["suggestion_id"],
        reason="É o balão C espelhado, o rótulo do modelo está errado.",
    )

    assert rejection.status_code == 200
    body = rejection.json()
    assert body["suggestion_id"] == suggestion["suggestion_id"]
    assert body["proposal_ids"] == ["vp_1111111111111111"]
    assert body["rejected_by_role"] == "engineer"
    rejected_at = datetime.fromisoformat(body["rejected_at"])
    assert rejected_at.tzinfo is not None and rejected_at >= before

    # Nada foi escrito na revisão: nenhuma revisão nova, nenhuma identidade declarada.
    with _database(client).sessions.begin() as session:
        revisions = list(
            session.scalars(
                select(ReviewRevisionRecord).where(ReviewRevisionRecord.job_id == str(JOB_ID))
            )
        )
        assert len(revisions) == 1
        assert revisions[0].element_declarations_json == []
        stored = session.scalars(
            select(ReviewElementSuggestionRejectionRecord).where(
                ReviewElementSuggestionRejectionRecord.job_id == str(JOB_ID)
            )
        ).all()
        assert len(stored) == 1
        assert stored[0].rejected_by == "reviewer"
        assert stored[0].proposal_ids_json == ["vp_1111111111111111"]


def test_sugestao_recusada_nao_volta_a_ser_oferecida(tmp_path: Path) -> None:
    proposals = _proposal_set([_proposal("vp_1111111111111111", label="B")])
    client = _client(tmp_path, proposals=proposals)
    suggestion_id = _list_suggestions(client).json()["suggestions"][0]["suggestion_id"]
    _reject(client, suggestion_id=suggestion_id, reason="Rótulo errado, de propósito.")

    assert _list_suggestions(client).json()["suggestions"] == []

    # Recusar de novo (chave de idempotência nova) já não encontra a sugestão.
    again = _reject(client, suggestion_id=suggestion_id, reason="De novo.", key="reject-2")
    assert again.status_code == 404
    assert again.json()["code"] == "REVIEW_ELEMENT_SUGGESTION_NOT_FOUND"


def test_recusar_id_nunca_ofertado_responde_com_codigo_estavel(tmp_path: Path) -> None:
    proposals = _proposal_set([_proposal("vp_1111111111111111", label="B")])
    client = _client(tmp_path, proposals=proposals)

    response = _reject(client, suggestion_id="els_0000000000000000", reason="Não existe.")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "REVIEW_ELEMENT_SUGGESTION_NOT_FOUND"


def test_recusa_exige_idempotency_key_e_papel_profissional(tmp_path: Path) -> None:
    proposals = _proposal_set([_proposal("vp_1111111111111111", label="B")])
    client = _client(tmp_path, proposals=proposals)
    suggestion_id = _list_suggestions(client).json()["suggestions"][0]["suggestion_id"]

    without_key = client.post(
        f"/v1/jobs/{JOB_ID}/review/elements/suggestions/{suggestion_id}/rejections",
        headers={"Authorization": "Bearer test:tenant-a:reviewer:engineer"},
        json={"reason": "Sem chave."},
    )
    assert without_key.status_code == 400

    unqualified = client.post(
        f"/v1/jobs/{JOB_ID}/review/elements/suggestions/{suggestion_id}/rejections",
        headers=_headers(roles="cad_operator", key="k-role"),
        json={"reason": "Sem papel."},
    )
    assert unqualified.status_code == 403
    assert unqualified.json()["code"] == "FORBIDDEN"


def test_recusa_exige_motivo_com_pelo_menos_tres_caracteres(tmp_path: Path) -> None:
    proposals = _proposal_set([_proposal("vp_1111111111111111", label="B")])
    client = _client(tmp_path, proposals=proposals)
    suggestion_id = _list_suggestions(client).json()["suggestions"][0]["suggestion_id"]

    response = _reject(client, suggestion_id=suggestion_id, reason="oi")

    assert response.status_code == 422


def test_sem_rotulo_nenhum_a_listagem_vem_vazia_sem_tocar_em_nada(tmp_path: Path) -> None:
    proposals = _proposal_set(
        [_proposal("vp_1111111111111111", label=None), _proposal("vp_2222222222222222", label=None)]
    )
    client = _client(tmp_path, proposals=proposals)

    response = _list_suggestions(client)

    assert response.status_code == 200
    assert response.json() == {"review_version": 1, "suggestions": []}
    with _database(client).sessions.begin() as session:
        assert (
            session.scalar(
                select(ReviewRevisionRecord.version)
                .where(ReviewRevisionRecord.job_id == str(JOB_ID))
                .order_by(ReviewRevisionRecord.version.desc())
            )
            == 1
        )


def test_revisao_sem_snapshot_de_propostas_responde_proposals_not_ready(tmp_path: Path) -> None:
    client = _client(tmp_path, proposals=None)

    response = _list_suggestions(client)

    assert response.status_code == 409
    assert response.json()["code"] == "PROPOSALS_NOT_READY"


def test_job_de_outro_tenant_responde_not_found(tmp_path: Path) -> None:
    proposals = _proposal_set([_proposal("vp_1111111111111111", label="B")])
    client = _client(tmp_path, proposals=proposals)

    response = _list_suggestions(client, tenant_id="tenant-b")

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"
