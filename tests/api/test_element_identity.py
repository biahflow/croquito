"""F-047 T2: o ato humano de identidade de elemento na revisão (ADR-0058, decisão 2).

O que estes testes protegem, em uma frase cada: o `element_ref` é cunhado pelo servidor e
recusado quando o cliente tenta escolhê-lo; a cunhagem é sequencial e nunca reaproveita um
número já usado no job; camadas misturadas recusam com erro legível em vez de 500; declarar
sobre cena aprovada cria revisão nova e deixa a aprovada intacta; desfazer é ato próprio,
registrado; e, sem nenhuma declaração, o caminho da revisão responde exatamente como hoje.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from croquito_api.config import ApiSettings
from croquito_api.database import (
    AuditRecord,
    Database,
    JobRecord,
    ProjectRecord,
    RevisionRecord,
    UploadRecord,
)
from croquito_api.main import create_app
from croquito_core.ids import new_uuid7
from croquito_core.models import (
    ELEMENT_LABEL_MAX_LENGTH,
    Entity,
    EntityKind,
    LayerName,
    LineGeometry,
    Point2D,
    Precision,
    Provenance,
    SceneRevision,
)

JOB_ID = UUID("00000000-0000-7000-8000-0000000e1e00")


def _headers(
    tenant_id: str = "tenant-a", roles: str = "engineer", key: str = "k-1"
) -> dict[str, str]:
    return {
        "Authorization": f"Bearer test:{tenant_id}:reviewer:{roles}",
        "Idempotency-Key": key,
    }


def _entity(*, y: float, layer: LayerName = LayerName.CONTORNO) -> Entity:
    """Traço métrico com provenance, para que a cena possa até ser aprovada."""
    return Entity(
        id=new_uuid7(),
        kind=EntityKind.LINE,
        layer=layer,
        precision=Precision.DERIVED,
        geometry=LineGeometry(start=Point2D(x=0.0, y=y), end=Point2D(x=10.0, y=y)),
        provenance=Provenance(
            source_type="fixture",
            source_ids=["synthetic-element-identity"],
            summary_code="SYNTHETIC_FIXTURE",
        ),
    )


def _client(tmp_path: Path, scene: SceneRevision, *, tenant_id: str = "tenant-a") -> TestClient:
    url = f"sqlite+pysqlite:///{tmp_path / 'elements.db'}"
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


def _declare(
    client: TestClient,
    *,
    entity_ids: list[str],
    base_version: int,
    key: str,
    tenant_id: str = "tenant-a",
    roles: str = "engineer",
    element_ref: str | None = None,
    label: str | None = None,
    reason: str = "Estes traços são o mesmo canteiro.",
) -> Any:
    body: dict[str, Any] = {
        "base_version": base_version,
        "entity_ids": entity_ids,
        "reason": reason,
    }
    if element_ref is not None:
        body["element_ref"] = element_ref
    if label is not None:
        body["label"] = label
    return client.post(
        f"/v1/jobs/{JOB_ID}/elements",
        headers=_headers(tenant_id, roles, key),
        json=body,
    )


def _revoke(
    client: TestClient,
    *,
    element_ref: str,
    base_version: int,
    key: str,
    reason: str = "Agrupamento errado, refazer.",
) -> Any:
    return client.post(
        f"/v1/jobs/{JOB_ID}/elements/revocations",
        headers=_headers(key=key),
        json={"base_version": base_version, "element_ref": element_ref, "reason": reason},
    )


def _two_entity_scene() -> tuple[SceneRevision, Entity, Entity]:
    first = _entity(y=0.0)
    second = _entity(y=1.0)
    return (
        SceneRevision(job_id=JOB_ID, version=1, entities=[first, second]),
        first,
        second,
    )


def test_declaracao_cunha_o_ref_no_servidor_e_registra_autor_e_instante(tmp_path: Path) -> None:
    scene, first, second = _two_entity_scene()
    client = _client(tmp_path, scene)
    before = datetime.now(UTC)

    response = _declare(
        client, entity_ids=[str(first.id), str(second.id)], base_version=1, key="declare-1"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["act"] == "declared"
    assert body["element_ref"] == "EL-001"
    assert sorted(body["entity_ids"]) == sorted([str(first.id), str(second.id)])
    # O papel profissional do ato, nunca o subject de quem o praticou.
    assert body["acted_by_role"] == "engineer"
    assert "reviewer" not in response.text
    acted_at = datetime.fromisoformat(body["acted_at"])
    assert acted_at.tzinfo is not None and acted_at >= before
    assert body["scene"]["version"] == 2
    assert [entity["element_ref"] for entity in body["scene"]["entities"]] == ["EL-001", "EL-001"]

    with _database(client).sessions.begin() as session:
        revisions = list(
            session.scalars(
                select(RevisionRecord)
                .where(RevisionRecord.job_id == str(JOB_ID))
                .order_by(RevisionRecord.version)
            )
        )
        assert [item.version for item in revisions] == [1, 2]
        # Autor e instante do ato ficam gravados na revisão, não só na resposta.
        assert revisions[1].created_by == "reviewer"
        assert revisions[1].created_at.replace(tzinfo=UTC) == acted_at
        assert revisions[1].parent_revision_id == str(scene.id)
        # A revisão de origem nunca é editada.
        assert all(entity["element_ref"] is None for entity in revisions[0].scene["entities"])
        audit = session.scalars(
            select(AuditRecord).where(AuditRecord.action == "ELEMENT_IDENTITY_DECLARED")
        ).all()
        assert len(audit) == 1
        assert audit[0].metadata_json["element_ref"] == "EL-001"


def test_element_ref_mandado_pelo_cliente_recusa_com_codigo_estavel(tmp_path: Path) -> None:
    scene, first, _ = _two_entity_scene()
    client = _client(tmp_path, scene)

    response = _declare(
        client,
        entity_ids=[str(first.id)],
        base_version=1,
        key="declare-choose",
        element_ref="EL-042",
    )

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "ELEMENT_REF_NOT_ASSIGNABLE"
    with _database(client).sessions.begin() as session:
        assert (
            session.scalar(select(RevisionRecord.version).order_by(RevisionRecord.version.desc()))
            == 1
        )


def test_cunhagem_e_sequencial_e_nunca_reaproveita_o_ref_revogado(tmp_path: Path) -> None:
    """Depois de revogar EL-002, a próxima declaração cunha EL-003, não EL-002.

    Reaproveitar o número faria duas coisas diferentes do mesmo job se chamarem pelo mesmo
    nome ao longo das revisões — a quantidade errada em silêncio que o ADR-0058 recusa.
    """
    first, second, third = _entity(y=0.0), _entity(y=1.0), _entity(y=2.0)
    scene = SceneRevision(job_id=JOB_ID, version=1, entities=[first, second, third])
    client = _client(tmp_path, scene)

    assert (
        _declare(client, entity_ids=[str(first.id)], base_version=1, key="d1").json()["element_ref"]
        == "EL-001"
    )
    assert (
        _declare(client, entity_ids=[str(second.id)], base_version=2, key="d2").json()[
            "element_ref"
        ]
        == "EL-002"
    )

    revoked = _revoke(client, element_ref="EL-002", base_version=3, key="r1")
    assert revoked.status_code == 200
    assert revoked.json()["act"] == "revoked"
    assert revoked.json()["entity_ids"] == [str(second.id)]
    assert revoked.json()["scene"]["version"] == 4
    assert [entity["element_ref"] for entity in revoked.json()["scene"]["entities"]] == [
        "EL-001",
        None,
        None,
    ]

    minted_again = _declare(client, entity_ids=[str(third.id)], base_version=4, key="d3")
    assert minted_again.json()["element_ref"] == "EL-003"


def test_desfazer_registra_autor_instante_e_cria_revisao_nova(tmp_path: Path) -> None:
    scene, first, _ = _two_entity_scene()
    client = _client(tmp_path, scene)
    _declare(client, entity_ids=[str(first.id)], base_version=1, key="d1")

    response = _revoke(client, element_ref="EL-001", base_version=2, key="r1")

    assert response.status_code == 200
    body = response.json()
    assert body["acted_by_role"] == "engineer"
    assert datetime.fromisoformat(body["acted_at"]).tzinfo is not None
    with _database(client).sessions.begin() as session:
        versions = list(
            session.scalars(
                select(RevisionRecord.version)
                .where(RevisionRecord.job_id == str(JOB_ID))
                .order_by(RevisionRecord.version)
            )
        )
        assert versions == [1, 2, 3]
        # A revisão que declarou continua dizendo o que dizia: desfazer não reescreve o passado.
        declared = session.scalar(
            select(RevisionRecord).where(
                RevisionRecord.job_id == str(JOB_ID), RevisionRecord.version == 2
            )
        )
        assert declared is not None
        assert declared.scene["entities"][0]["element_ref"] == "EL-001"
        audit = session.scalars(
            select(AuditRecord).where(AuditRecord.action == "ELEMENT_IDENTITY_REVOKED")
        ).all()
        assert len(audit) == 1
        assert audit[0].metadata_json["element_ref"] == "EL-001"


def test_desfazer_o_que_nunca_foi_declarado_recusa_com_codigo_estavel(tmp_path: Path) -> None:
    scene, _, _ = _two_entity_scene()
    client = _client(tmp_path, scene)

    response = _revoke(client, element_ref="EL-007", base_version=1, key="r1")

    assert response.status_code == 409
    assert response.json()["code"] == "ELEMENT_NOT_DECLARED"


def test_camadas_diferentes_no_mesmo_grupo_recusam_com_erro_legivel(tmp_path: Path) -> None:
    """A invariante da T1 recusa ANTES de montar a cena: 422 legível, nunca 500."""
    first = _entity(y=0.0, layer=LayerName.CONTORNO)
    second = _entity(y=1.0, layer=LayerName.QUADRA)
    scene = SceneRevision(job_id=JOB_ID, version=1, entities=[first, second])
    client = _client(tmp_path, scene)

    response = _declare(
        client, entity_ids=[str(first.id), str(second.id)], base_version=1, key="d1"
    )

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["code"] == "ELEMENT_REF_LAYER_MISMATCH"
    assert body["detail"]["details"]["layers"] == ["CONTORNO", "QUADRA"]
    with _database(client).sessions.begin() as session:
        assert (
            session.scalar(select(RevisionRecord.version).order_by(RevisionRecord.version.desc()))
            == 1
        )


def test_entidade_ja_declarada_exige_revogar_antes_de_mudar_de_elemento(tmp_path: Path) -> None:
    scene, first, second = _two_entity_scene()
    client = _client(tmp_path, scene)
    _declare(client, entity_ids=[str(first.id)], base_version=1, key="d1")

    response = _declare(
        client, entity_ids=[str(first.id), str(second.id)], base_version=2, key="d2"
    )

    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "ELEMENT_ALREADY_DECLARED"
    assert body["detail"]["details"]["entity_ids"] == [str(first.id)]


def test_entidade_inexistente_e_repetida_recusam_como_erro_de_dominio(tmp_path: Path) -> None:
    scene, first, _ = _two_entity_scene()
    client = _client(tmp_path, scene)

    unknown = _declare(client, entity_ids=[str(new_uuid7())], base_version=1, key="d1")
    repeated = _declare(client, entity_ids=[str(first.id), str(first.id)], base_version=1, key="d2")

    assert unknown.status_code == 422
    assert unknown.json()["code"] == "DOMAIN_VALIDATION_FAILED"
    assert repeated.status_code == 422
    assert repeated.json()["code"] == "DOMAIN_VALIDATION_FAILED"


def test_declarar_sobre_cena_aprovada_cria_revisao_nova_e_nao_toca_na_aprovada(
    tmp_path: Path,
) -> None:
    scene, first, second = _two_entity_scene()
    client = _client(tmp_path, scene)
    approved = client.post(
        f"/v1/jobs/{JOB_ID}/approve",
        headers=_headers(key="approve-1"),
        json={
            "revision_id": str(scene.id),
            "source_evidence_checked": True,
            "geometry_checked": True,
            "limitations_acknowledged": True,
            "statement": "Conferi a evidência e a geometria desta prancha sintética.",
        },
    )
    assert approved.status_code == 200
    approved_id = approved.json()["id"]
    assert approved.json()["approved"] is True

    response = _declare(
        client, entity_ids=[str(first.id), str(second.id)], base_version=2, key="d1"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["element_ref"] == "EL-001"
    # A revisão nova nasce NÃO aprovada: carrega a mesma geometria, mas ninguém a aprovou.
    assert body["scene"]["approved"] is False
    assert body["scene"]["version"] == 3
    with _database(client).sessions.begin() as session:
        still_approved = session.get(RevisionRecord, approved_id)
        assert still_approved is not None
        assert still_approved.approved_at is not None
        assert still_approved.scene["approved"] is True
        # A aprovação continua valendo para o conteúdo que aprovou: sem identidade nenhuma.
        assert all(entity["element_ref"] is None for entity in still_approved.scene["entities"])


def test_ato_de_identidade_exige_idempotency_key_e_repete_a_mesma_resposta(
    tmp_path: Path,
) -> None:
    scene, first, _ = _two_entity_scene()
    client = _client(tmp_path, scene)

    without_key = client.post(
        f"/v1/jobs/{JOB_ID}/elements",
        headers={"Authorization": "Bearer test:tenant-a:reviewer:engineer"},
        json={"base_version": 1, "entity_ids": [str(first.id)], "reason": "Um elemento."},
    )
    assert without_key.status_code == 400

    first_call = _declare(client, entity_ids=[str(first.id)], base_version=1, key="same")
    replay = _declare(client, entity_ids=[str(first.id)], base_version=1, key="same")

    assert first_call.status_code == 200
    assert replay.status_code == 200
    assert replay.json() == first_call.json()
    with _database(client).sessions.begin() as session:
        assert (
            session.scalar(select(RevisionRecord.version).order_by(RevisionRecord.version.desc()))
            == 2
        )

    reused = _declare(
        client, entity_ids=[str(first.id)], base_version=1, key="same", reason="Outro motivo agora."
    )
    assert reused.status_code == 409
    assert reused.json()["code"] == "IDEMPOTENCY_KEY_REUSED"


def test_base_version_desatualizada_recusa_como_revision_conflict(tmp_path: Path) -> None:
    scene, first, second = _two_entity_scene()
    client = _client(tmp_path, scene)
    _declare(client, entity_ids=[str(first.id)], base_version=1, key="d1")

    stale = _declare(client, entity_ids=[str(second.id)], base_version=1, key="d2")

    assert stale.status_code == 409
    assert stale.json()["code"] == "REVISION_CONFLICT"


def test_declaracao_concorrente_no_mesmo_numero_perde_a_corrida_sem_duplicar_o_ref(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """Duas declarações simultâneas cunham `EL-001`; a segunda a gravar colide e recusa.

    A corrida é encenada onde ela de fato acontece: entre ler a versão corrente e gravar a
    revisão nova. O patch grava, na MESMA transação e com a MESMA versão, a revisão que a
    outra requisição teria criado — o que faz `uq_scene_version` reprovar o `flush` seguinte.
    """
    import croquito_api.main as api_main

    scene, first, _ = _two_entity_scene()
    client = _client(tmp_path, scene)
    original = api_main._next_element_ref

    def _mint_after_a_competing_revision(session: Any, **kwargs: Any) -> str:
        minted = original(session, **kwargs)
        competing = SceneRevision.model_validate(
            {**scene.model_dump(mode="json"), "id": str(new_uuid7()), "version": 2}
        )
        session.add(
            RevisionRecord(
                id=str(competing.id),
                tenant_id="tenant-a",
                job_id=str(JOB_ID),
                version=2,
                scene=competing.model_dump(mode="json"),
                created_by="outra-sessao",
            )
        )
        session.flush()
        return minted

    monkeypatch.setattr(api_main, "_next_element_ref", _mint_after_a_competing_revision)
    response = _declare(client, entity_ids=[str(first.id)], base_version=1, key="race")

    assert response.status_code == 409
    assert response.json()["code"] == "REVISION_CONFLICT"
    # A recusa vem da COLISÃO na gravação, não da conferência de `base_version` — que já
    # passou. Sem esta asserção o teste continuaria verde se o guarda de corrida sumisse.
    assert response.json()["detail"]["detail"] == (
        "Um ato concorrente de identidade criou outra revisão."
    )
    with _database(client).sessions.begin() as session:
        scenes = list(
            session.scalars(
                select(RevisionRecord.scene).where(RevisionRecord.job_id == str(JOB_ID))
            )
        )
        minted = [
            entity["element_ref"]
            for item in scenes
            for entity in item["entities"]
            if entity["element_ref"] is not None
        ]
        assert minted == []


def test_job_de_outro_tenant_responde_not_found(tmp_path: Path) -> None:
    scene, first, _ = _two_entity_scene()
    client = _client(tmp_path, scene)

    response = _declare(
        client, entity_ids=[str(first.id)], base_version=1, key="d1", tenant_id="tenant-b"
    )

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_papel_sem_qualificacao_profissional_nao_declara_identidade(tmp_path: Path) -> None:
    scene, first, _ = _two_entity_scene()
    client = _client(tmp_path, scene)

    response = _declare(
        client, entity_ids=[str(first.id)], base_version=1, key="d1", roles="cad_operator"
    )

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


def test_sem_nenhuma_declaracao_o_caminho_da_revisao_responde_como_hoje(tmp_path: Path) -> None:
    """Não-regressão: cena, revisão e aprovação seguem idênticas sem identidade nenhuma."""
    scene, first, _ = _two_entity_scene()
    client = _client(tmp_path, scene)

    current = client.get(f"/v1/jobs/{JOB_ID}/scene", headers=_headers())
    assert current.status_code == 200
    assert all(entity["element_ref"] is None for entity in current.json()["entities"])

    revision = client.post(
        f"/v1/jobs/{JOB_ID}/revisions",
        headers=_headers(key="rev-1"),
        json={
            "base_version": 1,
            "reason": "Desenho manual",
            "operations": [
                {
                    "op": "add_entity",
                    "entity": {
                        "id": str(new_uuid7()),
                        "kind": "line",
                        "layer": "REVISAO",
                        "precision": "unresolved",
                        "export": False,
                        "geometry": {
                            "type": "line",
                            "start": {"x": 0, "y": 0},
                            "end": {"x": 1, "y": 0},
                        },
                    },
                }
            ],
        },
    )
    assert revision.status_code == 200
    assert revision.json()["version"] == 2
    assert all(entity["element_ref"] is None for entity in revision.json()["entities"])
    assert str(first.id) in revision.text
    # T2b: sem nenhum rótulo, o mapa nasce vazio e nada muda no caminho de sempre.
    assert revision.json()["element_labels"] == {}


# ---------------------------------------------------------------------------
# F-047 T2b — o rótulo legível do elemento (decisão humana de 2026-08-29).
# ---------------------------------------------------------------------------


def _relabel(
    client: TestClient,
    *,
    element_ref: str,
    label: str,
    base_version: int,
    key: str,
    reason: str = "Nome conferido com a prancha.",
) -> Any:
    return client.post(
        f"/v1/jobs/{JOB_ID}/elements/labels",
        headers=_headers(key=key),
        json={
            "base_version": base_version,
            "element_ref": element_ref,
            "label": label,
            "reason": reason,
        },
    )


def _scene_of(client: TestClient, version: int) -> dict[str, Any]:
    with _database(client).sessions.begin() as session:
        record = session.scalar(
            select(RevisionRecord).where(
                RevisionRecord.job_id == str(JOB_ID), RevisionRecord.version == version
            )
        )
        assert record is not None
        return record.scene


def test_o_rotulo_entra_no_mesmo_ato_da_declaracao(tmp_path: Path) -> None:
    """Critério 3: nomear é parte do ato de declarar, não uma segunda viagem."""
    scene, first, _ = _two_entity_scene()
    client = _client(tmp_path, scene)

    response = _declare(
        client,
        entity_ids=[str(first.id)],
        base_version=1,
        key="declare-label",
        label="Alambrado da quadra",
    )

    assert response.status_code == 200
    body = response.json()
    assert body["element_ref"] == "EL-001"
    assert body["label"] == "Alambrado da quadra"
    assert body["scene"]["element_labels"] == {"EL-001": "Alambrado da quadra"}
    assert _scene_of(client, 2)["element_labels"] == {"EL-001": "Alambrado da quadra"}
    with _database(client).sessions.begin() as session:
        audit = session.scalars(
            select(AuditRecord).where(AuditRecord.action == "ELEMENT_IDENTITY_DECLARED")
        ).all()
        # A auditoria guarda QUE houve nome, nunca o texto: rótulo é conteúdo do croqui.
        assert audit[0].metadata_json["element_ref"] == "EL-001"
        assert audit[0].metadata_json["labeled"] is True
        assert "Alambrado" not in str(audit[0].metadata_json)


def test_declarar_sem_rotulo_continua_valido_e_o_mapa_nasce_vazio(tmp_path: Path) -> None:
    """Critério 3 e 8: o rótulo é opcional; cena sem nome nenhum é cena válida."""
    scene, first, _ = _two_entity_scene()
    client = _client(tmp_path, scene)

    response = _declare(client, entity_ids=[str(first.id)], base_version=1, key="sem-label")

    assert response.status_code == 200
    assert response.json()["label"] is None
    assert response.json()["scene"]["element_labels"] == {}
    current = client.get(f"/v1/jobs/{JOB_ID}/scene", headers=_headers())
    assert current.json()["element_labels"] == {}


@pytest.mark.parametrize("label", ["   ", "\t"])
def test_rotulo_vazio_ou_so_de_espaco_recusa_com_codigo_estavel(tmp_path: Path, label: str) -> None:
    """Critério 2: `"   "` é campo esquecido, e a recusa é 422 nomeado, nunca 500."""
    scene, first, _ = _two_entity_scene()
    client = _client(tmp_path, scene)

    response = _declare(
        client, entity_ids=[str(first.id)], base_version=1, key="branco", label=label
    )

    assert response.status_code == 422
    assert response.json()["code"] == "ELEMENT_LABEL_INVALID"
    with _database(client).sessions.begin() as session:
        # Recusa não cria revisão: a cena continua na versão que já existia.
        assert list(session.scalars(select(RevisionRecord.version))) == [1]


def test_rotulo_acima_do_teto_recusa_no_contrato(tmp_path: Path) -> None:
    """Critério 2: o teto é do contrato — o servidor não trunca nome de ninguém."""
    scene, first, _ = _two_entity_scene()
    client = _client(tmp_path, scene)

    response = _declare(
        client,
        entity_ids=[str(first.id)],
        base_version=1,
        key="teto",
        label="A" * (ELEMENT_LABEL_MAX_LENGTH + 1),
    )

    assert response.status_code == 422


def test_o_rotulo_gravado_e_aparado_nas_pontas(tmp_path: Path) -> None:
    scene, first, _ = _two_entity_scene()
    client = _client(tmp_path, scene)

    response = _declare(
        client,
        entity_ids=[str(first.id)],
        base_version=1,
        key="aparo",
        label="  Alambrado da quadra  ",
    )

    assert response.json()["label"] == "Alambrado da quadra"
    assert _scene_of(client, 2)["element_labels"] == {"EL-001": "Alambrado da quadra"}


def test_renomear_e_ato_declarado_com_autor_instante_e_revisao_nova(tmp_path: Path) -> None:
    """Critério 4: renomear nunca é edição silenciosa da revisão que já existe."""
    scene, first, _ = _two_entity_scene()
    client = _client(tmp_path, scene)
    _declare(client, entity_ids=[str(first.id)], base_version=1, key="d1", label="Alambrado")

    response = _relabel(
        client,
        element_ref="EL-001",
        label="Alambrado da quadra poliesportiva",
        base_version=2,
        key="rl-1",
    )

    assert response.status_code == 200
    body = response.json()
    assert body["act"] == "relabeled"
    assert body["element_ref"] == "EL-001"
    assert body["label"] == "Alambrado da quadra poliesportiva"
    assert body["entity_ids"] == [str(first.id)]
    assert body["acted_by_role"] == "engineer"
    assert datetime.fromisoformat(body["acted_at"]).tzinfo is not None
    assert body["scene"]["version"] == 3
    # A revisão anterior continua dizendo o nome que dizia: o passado não é reescrito.
    assert _scene_of(client, 2)["element_labels"] == {"EL-001": "Alambrado"}
    assert _scene_of(client, 3)["element_labels"] == {"EL-001": "Alambrado da quadra poliesportiva"}
    with _database(client).sessions.begin() as session:
        audit = session.scalars(
            select(AuditRecord).where(AuditRecord.action == "ELEMENT_LABEL_CHANGED")
        ).all()
        assert len(audit) == 1
        assert audit[0].metadata_json["element_ref"] == "EL-001"
        # O nome novo não vai para a auditoria: o ato é que é auditado, não o conteúdo.
        assert "Alambrado" not in str(audit[0].metadata_json)


def test_renomear_nao_move_entidade_nem_troca_a_identidade(tmp_path: Path) -> None:
    scene, first, _ = _two_entity_scene()
    client = _client(tmp_path, scene)
    _declare(client, entity_ids=[str(first.id)], base_version=1, key="d1")

    _relabel(client, element_ref="EL-001", label="Muro da divisa", base_version=2, key="rl-1")

    antes = _scene_of(client, 2)
    depois = _scene_of(client, 3)
    assert [entity["element_ref"] for entity in depois["entities"]] == [
        entity["element_ref"] for entity in antes["entities"]
    ]
    assert [entity["geometry"] for entity in depois["entities"]] == [
        entity["geometry"] for entity in antes["entities"]
    ]


def test_renomear_ref_que_a_revisao_nao_tem_recusa_com_codigo_estavel(tmp_path: Path) -> None:
    """Nomear um ref inexistente criaria o rótulo órfão que o núcleo recusa: 409 legível."""
    scene, _, _ = _two_entity_scene()
    client = _client(tmp_path, scene)

    response = _relabel(client, element_ref="EL-007", label="Nada", base_version=1, key="rl-1")

    assert response.status_code == 409
    assert response.json()["code"] == "ELEMENT_NOT_DECLARED"


def test_renomear_com_rotulo_so_de_espaco_recusa_com_codigo_estavel(tmp_path: Path) -> None:
    scene, first, _ = _two_entity_scene()
    client = _client(tmp_path, scene)
    _declare(client, entity_ids=[str(first.id)], base_version=1, key="d1")

    response = _relabel(client, element_ref="EL-001", label="   ", base_version=2, key="rl-1")

    assert response.status_code == 422
    assert response.json()["code"] == "ELEMENT_LABEL_INVALID"


def test_renomear_exige_idempotency_key_e_repete_a_mesma_resposta(tmp_path: Path) -> None:
    scene, first, _ = _two_entity_scene()
    client = _client(tmp_path, scene)
    _declare(client, entity_ids=[str(first.id)], base_version=1, key="d1")

    sem_chave = client.post(
        f"/v1/jobs/{JOB_ID}/elements/labels",
        headers={"Authorization": "Bearer test:tenant-a:reviewer:engineer"},
        json={
            "base_version": 2,
            "element_ref": "EL-001",
            "label": "Alambrado",
            "reason": "Nome da prancha.",
        },
    )
    assert sem_chave.status_code == 400

    primeira = _relabel(client, element_ref="EL-001", label="Alambrado", base_version=2, key="rl-1")
    repetida = _relabel(client, element_ref="EL-001", label="Alambrado", base_version=2, key="rl-1")

    assert primeira.status_code == 200
    assert repetida.json() == primeira.json()
    with _database(client).sessions.begin() as session:
        assert sorted(session.scalars(select(RevisionRecord.version))) == [1, 2, 3]


def test_revogar_a_identidade_leva_o_rotulo_junto(tmp_path: Path) -> None:
    """Critério 4: sem elemento o nome não nomeia nada — e órfão o núcleo recusaria."""
    scene, first, second = _two_entity_scene()
    client = _client(tmp_path, scene)
    _declare(client, entity_ids=[str(first.id)], base_version=1, key="d1", label="Alambrado")
    _declare(client, entity_ids=[str(second.id)], base_version=2, key="d2", label="Muro")

    response = _revoke(client, element_ref="EL-001", base_version=3, key="r1")

    assert response.status_code == 200
    assert response.json()["label"] is None
    # O rótulo do OUTRO elemento permanece: a revogação leva só o nome do que ela desfez.
    assert response.json()["scene"]["element_labels"] == {"EL-002": "Muro"}


def test_dois_elementos_com_o_mesmo_rotulo_continuam_sendo_dois_elementos(
    tmp_path: Path,
) -> None:
    """Critério 5, na API: rótulo não agrupa, não casa e não funde nada.

    Dois refs distintos com o MESMO nome continuam sendo dois elementos, com entidades
    próprias. Nada em lugar nenhum consulta o rótulo para decidir identidade.
    """
    scene, first, second = _two_entity_scene()
    client = _client(tmp_path, scene)

    um = _declare(
        client,
        entity_ids=[str(first.id)],
        base_version=1,
        key="d1",
        label="Alambrado da quadra",
    )
    outro = _declare(
        client,
        entity_ids=[str(second.id)],
        base_version=2,
        key="d2",
        label="Alambrado da quadra",
    )

    assert um.json()["element_ref"] == "EL-001"
    assert outro.json()["element_ref"] == "EL-002"
    assert outro.json()["scene"]["element_labels"] == {
        "EL-001": "Alambrado da quadra",
        "EL-002": "Alambrado da quadra",
    }
    entidades_por_ref = {
        entity["element_ref"]: entity["id"]
        for entity in outro.json()["scene"]["entities"]
        if entity["element_ref"] is not None
    }
    assert entidades_por_ref == {"EL-001": str(first.id), "EL-002": str(second.id)}
