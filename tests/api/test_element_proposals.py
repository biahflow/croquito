"""F-047 T6: a proposta assistida de agrupamento na revisão (ADR-0058, decisão 2).

O que estes testes protegem, em uma frase cada: a listagem devolve propostas rotuladas
`unresolved`, nunca identidade; confirmar reusa o MESMO ato da T2 (`POST .../elements`),
sem segundo caminho de escrita; uma proposta ERRADA de propósito pode ser recusada, a
recusa fica registrada (quem e quando) e nada é escrito na cena; a proposta recusada não
volta a aparecer; e sem sinal nenhum a listagem responde vazia sem tocar em nada.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast, get_args
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import select

from croquito_api.config import ApiSettings
from croquito_api.database import (
    Database,
    ElementProposalRejectionRecord,
    JobRecord,
    ProjectRecord,
    RevisionRecord,
    UploadRecord,
)
from croquito_api.main import create_app
from croquito_core.ids import new_uuid7
from croquito_core.models import (
    Entity,
    EntityKind,
    LayerName,
    LineGeometry,
    Point2D,
    Precision,
    Provenance,
    SceneRevision,
    TextGeometry,
)
from croquito_valuation.takeoff import TakeoffItem

JOB_ID = UUID("00000000-0000-7000-8000-0000000e1e01")

_PROVENANCE = Provenance(source_type="fixture", source_ids=["batch-1"], summary_code="MURO_SEGMENT")


def _headers(
    tenant_id: str = "tenant-a", roles: str = "engineer", key: str | None = "k-1"
) -> dict[str, str]:
    headers = {"Authorization": f"Bearer test:{tenant_id}:reviewer:{roles}"}
    if key is not None:
        headers["Idempotency-Key"] = key
    return headers


def _wall_line(*, y: float, provenance: Provenance | None = _PROVENANCE) -> Entity:
    return Entity(
        id=new_uuid7(),
        kind=EntityKind.LINE,
        layer=LayerName.MURO,
        precision=Precision.DERIVED,
        geometry=LineGeometry(start=Point2D(x=0.0, y=y), end=Point2D(x=10.0, y=y)),
        provenance=provenance,
    )


def _client(tmp_path: Path, scene: SceneRevision, *, tenant_id: str = "tenant-a") -> TestClient:
    url = f"sqlite+pysqlite:///{tmp_path / 'proposals.db'}"
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
    with database.sessions.begin() as session:
        session.add(
            ProjectRecord(
                id="project",
                tenant_id=tenant_id,
                name="Teste",
                default_unit="m",
                created_by="reviewer",
                expires_at=scene.created_at,
            )
        )
        session.add(
            UploadRecord(
                id="upload",
                tenant_id=tenant_id,
                object_key="key",
                filename="x.pdf",
                content_type="application/pdf",
                size_bytes=1,
                sha256="a" * 64,
            )
        )
        session.flush()
        session.add(
            JobRecord(
                id=str(scene.job_id),
                tenant_id=tenant_id,
                project_id="project",
                upload_id="upload",
                status="REVIEW_REQUIRED",
                stage="PREVIEWING",
                expires_at=scene.created_at,
            )
        )
        session.flush()
        session.add(
            RevisionRecord(
                id=str(scene.id),
                tenant_id=tenant_id,
                job_id=str(scene.job_id),
                version=scene.version,
                scene=scene.model_dump(mode="json"),
                created_by="worker",
            )
        )
    return TestClient(create_app(settings=settings, database=database))


def _database(client: TestClient) -> Database:
    return cast(Database, cast(Any, client.app).state.database)


def _list_proposals(client: TestClient, **headers_kwargs: Any) -> Any:
    return client.get(f"/v1/jobs/{JOB_ID}/elements/proposals", headers=_headers(**headers_kwargs))


def _reject(client: TestClient, *, proposal_id: str, reason: str, key: str = "reject-1") -> Any:
    return client.post(
        f"/v1/jobs/{JOB_ID}/elements/proposals/{proposal_id}/rejections",
        headers=_headers(key=key),
        json={"reason": reason},
    )


def test_listagem_devolve_proposta_rotulada_unresolved_nunca_identidade(tmp_path: Path) -> None:
    first, second = _wall_line(y=0.0), _wall_line(y=1.0)
    scene = SceneRevision(job_id=JOB_ID, version=1, entities=[first, second])
    client = _client(tmp_path, scene)

    response = _list_proposals(client)

    assert response.status_code == 200
    body = response.json()
    assert body["scene_version"] == 1
    assert len(body["proposals"]) == 1
    proposal = body["proposals"][0]
    assert proposal["status"] == "unresolved"
    assert proposal["signal"] == "provenance"
    assert proposal["layer"] == "MURO"
    assert sorted(proposal["entity_ids"]) == sorted([str(first.id), str(second.id)])
    proposal_id = proposal["proposal_id"]
    assert proposal_id.startswith("elp_")

    # Determinístico: chamar de novo devolve exatamente a mesma proposta.
    again = _list_proposals(client).json()
    assert again == body


def test_confirmar_reusa_o_mesmo_ato_da_t2_sem_segundo_caminho(tmp_path: Path) -> None:
    first, second = _wall_line(y=0.0), _wall_line(y=1.0)
    scene = SceneRevision(job_id=JOB_ID, version=1, entities=[first, second])
    client = _client(tmp_path, scene)
    proposal = _list_proposals(client).json()["proposals"][0]

    declared = client.post(
        f"/v1/jobs/{JOB_ID}/elements",
        headers=_headers(key="declare-1"),
        json={
            "base_version": 1,
            "entity_ids": proposal["entity_ids"],
            "reason": "Confirmando a proposta assistida.",
        },
    )

    assert declared.status_code == 200
    assert declared.json()["element_ref"] == "EL-001"
    # A proposta confirmada some da listagem: as entidades já têm identidade.
    remaining = _list_proposals(client).json()["proposals"]
    assert remaining == []


def test_proposta_errada_de_proposito_pode_ser_recusada_e_nada_e_escrito(tmp_path: Path) -> None:
    """Dois muros DIFERENTES, mesmo lote de detecção: a proposta agrupa errado.

    O produtor não sabe que são dois elementos distintos — ele só vê camada e procedência
    iguais. É exatamente o tipo de erro que a recusa humana existe para corrigir.
    """
    near_wall, far_wall = _wall_line(y=0.0), _wall_line(y=50.0)
    scene = SceneRevision(job_id=JOB_ID, version=1, entities=[near_wall, far_wall])
    client = _client(tmp_path, scene)
    before = datetime.now(UTC)
    proposal = _list_proposals(client).json()["proposals"][0]
    assert sorted(proposal["entity_ids"]) == sorted([str(near_wall.id), str(far_wall.id)])

    rejection = _reject(
        client, proposal_id=proposal["proposal_id"], reason="São dois muros diferentes."
    )

    assert rejection.status_code == 200
    body = rejection.json()
    assert body["proposal_id"] == proposal["proposal_id"]
    assert body["rejected_by_role"] == "engineer"
    rejected_at = datetime.fromisoformat(body["rejected_at"])
    assert rejected_at.tzinfo is not None and rejected_at >= before

    # Nada foi escrito na cena: nenhuma revisão nova, nenhum element_ref.
    with _database(client).sessions.begin() as session:
        revisions = list(
            session.scalars(select(RevisionRecord).where(RevisionRecord.job_id == str(JOB_ID)))
        )
        assert len(revisions) == 1
        assert all(entity["element_ref"] is None for entity in revisions[0].scene["entities"])
        stored = session.scalars(
            select(ElementProposalRejectionRecord).where(
                ElementProposalRejectionRecord.job_id == str(JOB_ID)
            )
        ).all()
        assert len(stored) == 1
        assert stored[0].rejected_by == "reviewer"
        assert sorted(stored[0].entity_ids_json) == sorted([str(near_wall.id), str(far_wall.id)])

    scene_after = client.get(f"/v1/jobs/{JOB_ID}/scene", headers=_headers()).json()
    assert all(entity["element_ref"] is None for entity in scene_after["entities"])


def test_proposta_recusada_nao_volta_a_ser_oferecida(tmp_path: Path) -> None:
    near_wall, far_wall = _wall_line(y=0.0), _wall_line(y=50.0)
    scene = SceneRevision(job_id=JOB_ID, version=1, entities=[near_wall, far_wall])
    client = _client(tmp_path, scene)
    proposal_id = _list_proposals(client).json()["proposals"][0]["proposal_id"]
    _reject(client, proposal_id=proposal_id, reason="São dois muros diferentes.")

    assert _list_proposals(client).json()["proposals"] == []

    # Recusar de novo (chave de idempotência nova) já não encontra a proposta.
    again = _reject(client, proposal_id=proposal_id, reason="De novo.", key="reject-2")
    assert again.status_code == 404
    assert again.json()["code"] == "ELEMENT_PROPOSAL_NOT_FOUND"


def test_recusar_id_nunca_ofertado_responde_com_codigo_estavel(tmp_path: Path) -> None:
    scene = SceneRevision(job_id=JOB_ID, version=1, entities=[_wall_line(y=0.0)])
    client = _client(tmp_path, scene)

    response = _reject(client, proposal_id="elp_0000000000000000", reason="Não existe.")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "ELEMENT_PROPOSAL_NOT_FOUND"


def test_recusa_exige_idempotency_key_e_papel_profissional(tmp_path: Path) -> None:
    near_wall, far_wall = _wall_line(y=0.0), _wall_line(y=50.0)
    scene = SceneRevision(job_id=JOB_ID, version=1, entities=[near_wall, far_wall])
    client = _client(tmp_path, scene)
    proposal_id = _list_proposals(client).json()["proposals"][0]["proposal_id"]

    without_key = client.post(
        f"/v1/jobs/{JOB_ID}/elements/proposals/{proposal_id}/rejections",
        headers={"Authorization": "Bearer test:tenant-a:reviewer:engineer"},
        json={"reason": "Sem chave."},
    )
    assert without_key.status_code == 400

    unqualified = client.post(
        f"/v1/jobs/{JOB_ID}/elements/proposals/{proposal_id}/rejections",
        headers=_headers(roles="cad_operator", key="k-role"),
        json={"reason": "Sem papel."},
    )
    assert unqualified.status_code == 403
    assert unqualified.json()["code"] == "FORBIDDEN"


def test_sem_sinal_nenhum_a_listagem_vem_vazia_sem_tocar_em_nada(tmp_path: Path) -> None:
    scene = SceneRevision(job_id=JOB_ID, version=1, entities=[_wall_line(y=0.0, provenance=None)])
    client = _client(tmp_path, scene)

    response = _list_proposals(client)

    assert response.status_code == 200
    assert response.json() == {"scene_version": 1, "proposals": []}
    with _database(client).sessions.begin() as session:
        assert (
            session.scalar(select(RevisionRecord.version).order_by(RevisionRecord.version.desc()))
            == 1
        )


def test_proposta_nao_confirmada_nao_alimenta_quantidade_nenhuma(tmp_path: Path) -> None:
    """Nem `element_ref` na cena, nem elo possível para a quantidade da cena.

    A T4 abriu `TakeoffItem.source = scene_graph`, então a prova não pode mais ser "o
    terceiro valor não existe". Ela passa a ser a que sempre importou: proposta não
    confirmada **não escreve `element_ref` na cena**, e sem identidade dos dois lados o
    `QuantitySource` não resolve — é o elo que falta, não o vocabulário do campo.
    """
    first, second = _wall_line(y=0.0), _wall_line(y=1.0)
    scene = SceneRevision(job_id=JOB_ID, version=1, entities=[first, second])
    client = _client(tmp_path, scene)

    proposals = _list_proposals(client).json()["proposals"]
    assert len(proposals) == 1

    scene_after = client.get(f"/v1/jobs/{JOB_ID}/scene", headers=_headers()).json()
    assert all(entity["element_ref"] is None for entity in scene_after["entities"])

    # `scene_graph` existe desde a T4; o que não existe é identidade declarada para casar.
    assert "scene_graph" in get_args(TakeoffItem.model_fields["source"].annotation)
    item = TakeoffItem.model_validate(
        {
            "id": "ti_" + "a" * 16,
            "evidence": {
                "plate_id": "prancha-1",
                "page_number": 1,
                "image_sha256": "b" * 64,
                "coordinate_space": "source_image_pixels",
                "bbox": {"left": 1, "top": 1, "right": 10, "bottom": 10},
            },
            "raw_text": "MURO H=2,00 - 40,00 m",
            "label": "MURO",
            "quantity": None,
            "unit": "m",
            "source": "legend_extraction",
            "extractor": "fixture",
            "extractor_version": "1.0.0",
            "status": "ambiguous",
        }
    )
    assert item.element_ref is None


def test_label_proximity_agrupa_por_rotulo_mais_perto(tmp_path: Path) -> None:
    near_label_a = Entity(
        id=new_uuid7(),
        kind=EntityKind.LINE,
        layer=LayerName.ALAMBRADO,
        precision=Precision.DERIVED,
        geometry=LineGeometry(start=Point2D(x=0.0, y=10.0), end=Point2D(x=10.0, y=10.0)),
    )
    near_label_b = Entity(
        id=new_uuid7(),
        kind=EntityKind.LINE,
        layer=LayerName.ALAMBRADO,
        precision=Precision.DERIVED,
        geometry=LineGeometry(start=Point2D(x=0.0, y=10.5), end=Point2D(x=10.0, y=10.5)),
    )
    label = Entity(
        id=new_uuid7(),
        kind=EntityKind.TEXT,
        layer=LayerName.TEXTOS,
        precision=Precision.DERIVED,
        geometry=TextGeometry(insertion=Point2D(x=5.0, y=10.25), text="ALAMBRADO 1", height=0.2),
    )
    scene = SceneRevision(job_id=JOB_ID, version=1, entities=[near_label_a, near_label_b, label])
    client = _client(tmp_path, scene)

    proposal = _list_proposals(client).json()["proposals"][0]

    assert proposal["signal"] == "label_proximity"
    assert proposal["label"] == "ALAMBRADO 1"
    assert sorted(proposal["entity_ids"]) == sorted([str(near_label_a.id), str(near_label_b.id)])


def test_job_de_outro_tenant_responde_not_found(tmp_path: Path) -> None:
    scene = SceneRevision(job_id=JOB_ID, version=1, entities=[_wall_line(y=0.0)])
    client = _client(tmp_path, scene)

    response = _list_proposals(client, tenant_id="tenant-b")

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"
