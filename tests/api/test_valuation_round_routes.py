"""Rotas `/v1/valuation-rounds` de F-003 (T6/T7): criação, listagem, estado e prancha.

O que estes testes protegem, além do caminho feliz:

- **papel antes do lookup**: quem não é `orcamentista` recebe `403` mesmo para uma rodada
  que não existe, e por isso não descobre pela diferença entre `403` e `404` o que existe
  no tenant vizinho;
- **IDOR**: rodada de outro tenant é `404`, nunca `403`;
- **concorrência otimista**: `base_version` divergente recusa sem gravar linha nenhuma;
- **URL assinada**: sai só depois de conferido o prefixo do tenant e nunca entra em
  auditoria — as duas coisas verificadas contra o banco, não contra a resposta;
- **chamada paga**: entitlement revogado não enfileira, extração em voo recusa, e a fila
  indisponível devolve `503` com o intent já durável.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest
from botocore.exceptions import BotoCoreError
from fastapi.testclient import TestClient
from sqlalchemy import select

from croquito_api.config import ApiSettings
from croquito_api.database import (
    AuditRecord,
    Database,
    TenantAiProcessingEntitlementRecord,
    ValuationRoundRecord,
    ValuationRoundRevisionRecord,
)
from croquito_api.main import create_app
from croquito_core.ids import new_uuid7
from croquito_valuation.models import PriceCatalog, PriceCatalogEntry
from croquito_worker.valuation.round_extraction import (
    AI_BUDGET_ENV,
    PLATE_IMAGE_REF,
)
from tests.fakes import FakeObjectStore, FakeQueue, synthetic_pdf

_TENANT = "tenant-a"
_OTHER_TENANT = "tenant-b"
_ANTHROPIC_KEY_ENV = "CROQUITO_ANTHROPIC_API_KEY"


# --- montagem ---------------------------------------------------------------------------


def _client(tmp_path: Path, *, real_providers_enabled: bool = False) -> TestClient:
    database = Database(f"sqlite+pysqlite:///{tmp_path / 'valuation-api.db'}")
    database.create_schema()
    settings = ApiSettings(
        database_url=f"sqlite+pysqlite:///{tmp_path / 'valuation-api.db'}",
        artifact_bucket="croquito-test-artifacts",
        aws_region="sa-east-1",
        aws_endpoint_url="http://localhost:4566",
        queue_url=None,
        oidc_issuer=None,
        oidc_audience=None,
        web_origin="http://localhost:5173",
        allow_test_tokens=True,
        real_providers_enabled=real_providers_enabled,
    )
    application = create_app(settings=settings, database=database)
    application.state.artifact_store = FakeObjectStore()
    return TestClient(application)


def _headers(
    tenant: str = _TENANT,
    roles: str = "orcamentista",
    *,
    key: str = "valuation-request-001",
) -> dict[str, str]:
    return {
        "Authorization": f"Bearer test:{tenant}:orcamentista-sintetica:{roles}",
        "Idempotency-Key": key,
    }


def _store(client: TestClient) -> FakeObjectStore:
    return cast(FakeObjectStore, cast(Any, client.app).state.artifact_store)


def _database(client: TestClient) -> Database:
    return cast(Database, cast(Any, client.app).state.database)


def _observed_queue(client: TestClient) -> FakeQueue:
    """Substitui apenas o transporte: o envelope publicado continua sendo o de produção."""
    queue = FakeQueue()
    processing_queue = cast(Any, client.app).state.queue
    processing_queue.queue_url = "http://localstack/queue"
    processing_queue.client = queue
    return queue


def _catalog_bytes() -> bytes:
    catalog = PriceCatalog(
        source_label="CATALOGO SINTETICO",
        reference_month="2026-01",
        source_sha256="c" * 64,
        entries=[
            PriceCatalogEntry(
                code="CE04100010(/)",
                description="ALAMBRADO GALVANIZADO",
                unit="m",
                unit_price=Decimal("50.00"),
                family_code="CE",
                family_name="SERVICOS SINTETICOS",
                subgroup_code="CE0410",
                subgroup_name="ITENS SINTETICOS",
            )
        ],
    )
    return catalog.model_dump_json().encode("utf-8")


def _presign_and_put(
    client: TestClient,
    *,
    tenant: str = _TENANT,
    filename: str,
    content_type: str,
    payload: bytes,
    key: str,
) -> dict[str, Any]:
    """Presign declarando o digest real e o PUT que o navegador faria."""
    presign = client.post(
        "/v1/uploads/presign",
        headers={**_headers(tenant, key=key)},
        json={
            "filename": filename,
            "content_type": content_type,
            "size_bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        },
    )
    assert presign.status_code == 200, presign.text
    _store(client).put_direct(
        object_key=presign.json()["object_key"], body=payload, content_type=content_type
    )
    return cast(dict[str, Any], presign.json())


def _catalog_upload(
    client: TestClient, *, tenant: str = _TENANT, key: str = "catalogo-001"
) -> dict[str, Any]:
    return _presign_and_put(
        client,
        tenant=tenant,
        filename="catalogo.json",
        content_type="application/json",
        payload=_catalog_bytes(),
        key=key,
    )


def _plate_upload(
    client: TestClient, *, tenant: str = _TENANT, key: str = "prancha-001"
) -> dict[str, Any]:
    return _presign_and_put(
        client,
        tenant=tenant,
        filename="prancha.pdf",
        content_type="application/pdf",
        payload=synthetic_pdf(),
        key=key,
    )


def _round_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "worksite_key": "praca-sintetica-norte",
        "worksite_name": "PRACA SINTETICA NORTE",
        "reference_label": "MEDICAO 01/2026",
        "period_number": 1,
        "address": "RUA SINTETICA, S/N",
        "contract_label": "CONTRATO SINTETICO 01/2026",
    }
    payload.update(overrides)
    return payload


def _create_round(
    client: TestClient,
    *,
    tenant: str = _TENANT,
    key: str = "rodada-001",
    **overrides: Any,
) -> dict[str, Any]:
    upload = _catalog_upload(client, tenant=tenant, key=f"catalogo-{key}")
    response = client.post(
        "/v1/valuation-rounds",
        headers=_headers(tenant, key=key),
        json=_round_payload(catalog_upload_id=upload["upload_id"], **overrides),
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, Any], response.json())


def _associate_plate(
    client: TestClient,
    round_id: str,
    *,
    tenant: str = _TENANT,
    base_version: int = 1,
    key: str = "prancha-assoc-001",
) -> Any:
    upload = _plate_upload(client, tenant=tenant, key=f"upload-{key}")
    return client.post(
        f"/v1/valuation-rounds/{round_id}/plate",
        headers=_headers(tenant, key=key),
        json={"upload_id": upload["upload_id"], "base_version": base_version},
    )


def _allow_paid_extraction(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ambiente com teto de gasto e credencial declarados; nenhuma chamada é feita aqui."""
    monkeypatch.setenv(AI_BUDGET_ENV, "1.50")
    monkeypatch.setenv(_ANTHROPIC_KEY_ENV, "chave-de-teste-nunca-usada")


def _grant_entitlement(client: TestClient, tenant: str = _TENANT) -> None:
    database = _database(client)
    with database.sessions() as session:
        session.add(
            TenantAiProcessingEntitlementRecord(
                id=str(new_uuid7()),
                tenant_id=tenant,
                status="ACTIVE",
                agreement_reference="ctr-sintetico-v1",
                authorized_by="platform-operator-sintetico",
                authorized_at=datetime.now(UTC),
            )
        )
        session.commit()


# --- criação ----------------------------------------------------------------------------


def test_a_rodada_nasce_com_catalogo_instalado_e_versao_um(tmp_path: Path) -> None:
    client = _client(tmp_path)
    upload = _catalog_upload(client)

    response = client.post(
        "/v1/valuation-rounds",
        headers=_headers(),
        json=_round_payload(catalog_upload_id=upload["upload_id"]),
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["version"] == 1
    assert body["status"] == "OPEN"
    with _database(client).sessions() as session:
        record = session.scalar(
            select(ValuationRoundRecord).where(ValuationRoundRecord.id == body["round_id"])
        )
        assert record is not None
        assert record.tenant_id == _TENANT
        assert record.period_number == 1
        assert record.address == "RUA SINTETICA, S/N"
        assert record.contract_label == "CONTRATO SINTETICO 01/2026"
        assert record.catalog_object_key == upload["object_key"]
        assert record.catalog_summary_json["entries"] == 1
        assert record.extraction_status == "idle"


def test_catalogo_ilegivel_recusa_a_rodada_com_o_codigo_de_dominio(tmp_path: Path) -> None:
    """Catálogo que não valida não vira rodada: ela nasceria inutilizável em toda etapa."""
    client = _client(tmp_path)
    payload = b'{"source_label": "SEM ENTRADAS"}'
    upload = _presign_and_put(
        client,
        filename="catalogo.json",
        content_type="application/json",
        payload=payload,
        key="catalogo-invalido",
    )

    response = client.post(
        "/v1/valuation-rounds",
        headers=_headers(),
        json=_round_payload(catalog_upload_id=upload["upload_id"]),
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "DOMAIN_VALIDATION_FAILED"
    assert detail["details"]["code"]
    with _database(client).sessions() as session:
        assert session.scalars(select(ValuationRoundRecord)).all() == []


def test_upload_de_catalogo_que_nao_e_json_recusa(tmp_path: Path) -> None:
    client = _client(tmp_path)
    upload = _plate_upload(client)

    response = client.post(
        "/v1/valuation-rounds",
        headers=_headers(),
        json=_round_payload(catalog_upload_id=upload["upload_id"]),
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_UPLOAD"


def test_o_corpo_recusa_o_carimbo_de_identidade(tmp_path: Path) -> None:
    """`reviewer_id` e companhia são do servidor; o `extra="forbid"` os recusa."""
    client = _client(tmp_path)
    upload = _catalog_upload(client)

    for forbidden in ("reviewer_id", "reviewer_role", "decided_at", "decision_id"):
        response = client.post(
            "/v1/valuation-rounds",
            headers=_headers(key=f"rodada-{forbidden}"),
            json=_round_payload(catalog_upload_id=upload["upload_id"], **{forbidden: "x"}),
        )

        assert response.status_code == 422, forbidden
        assert "extra" in response.text.lower()


def test_idempotencia_da_criacao_devolve_a_mesma_rodada(tmp_path: Path) -> None:
    client = _client(tmp_path)
    upload = _catalog_upload(client)
    body = _round_payload(catalog_upload_id=upload["upload_id"])

    first = client.post("/v1/valuation-rounds", headers=_headers(key="rodada-x"), json=body)
    second = client.post("/v1/valuation-rounds", headers=_headers(key="rodada-x"), json=body)
    reused = client.post(
        "/v1/valuation-rounds",
        headers=_headers(key="rodada-x"),
        json={**body, "worksite_name": "OUTRA OBRA"},
    )

    assert first.status_code == 201
    assert second.json() == first.json()
    assert reused.status_code == 409
    assert reused.json()["detail"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    with _database(client).sessions() as session:
        assert len(session.scalars(select(ValuationRoundRecord)).all()) == 1


def test_criacao_sem_idempotency_key_recusa(tmp_path: Path) -> None:
    client = _client(tmp_path)
    upload = _catalog_upload(client)
    headers = _headers()
    headers.pop("Idempotency-Key")

    response = client.post(
        "/v1/valuation-rounds",
        headers=headers,
        json=_round_payload(catalog_upload_id=upload["upload_id"]),
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"


# --- autorização e isolamento -----------------------------------------------------------

_READ_ROUTES = ("", "/plate")


def test_sem_authorization_toda_rota_de_medicao_devolve_401(tmp_path: Path) -> None:
    client = _client(tmp_path)
    created = _create_round(client)
    round_id = created["round_id"]

    responses = [
        client.get("/v1/valuation-rounds"),
        client.get(f"/v1/valuation-rounds/{round_id}"),
        client.get(f"/v1/valuation-rounds/{round_id}/plate"),
        client.post("/v1/valuation-rounds", json=_round_payload(catalog_upload_id=str(uuid4()))),
        client.post(
            f"/v1/valuation-rounds/{round_id}/plate",
            json={"upload_id": str(uuid4()), "base_version": 1},
        ),
        client.post(f"/v1/valuation-rounds/{round_id}/plate/extractions", json={"base_version": 1}),
    ]

    assert [response.status_code for response in responses] == [401] * 6


def test_papel_e_exigido_antes_do_lookup_da_rodada(tmp_path: Path) -> None:
    """Rodada inexistente com papel errado devolve 403: o `404` diria que ela não existe."""
    client = _client(tmp_path)
    unknown = str(new_uuid7())
    headers = _headers(roles="engineer")

    responses = [
        client.get("/v1/valuation-rounds", headers=headers),
        client.get(f"/v1/valuation-rounds/{unknown}", headers=headers),
        client.get(f"/v1/valuation-rounds/{unknown}/plate", headers=headers),
        client.post(
            "/v1/valuation-rounds", headers=headers, json=_round_payload(catalog_upload_id=unknown)
        ),
        client.post(
            f"/v1/valuation-rounds/{unknown}/plate",
            headers=headers,
            json={"upload_id": unknown, "base_version": 1},
        ),
        client.post(
            f"/v1/valuation-rounds/{unknown}/plate/extractions",
            headers=headers,
            json={"base_version": 1},
        ),
    ]

    assert [response.status_code for response in responses] == [403] * 6
    assert all(response.json()["detail"]["code"] == "FORBIDDEN" for response in responses)


def test_rodada_de_outro_tenant_e_404_e_nunca_403(tmp_path: Path) -> None:
    client = _client(tmp_path)
    created = _create_round(client)
    round_id = created["round_id"]
    intruder = _headers(_OTHER_TENANT, key="intruso-001")

    state = client.get(f"/v1/valuation-rounds/{round_id}", headers=intruder)
    plate = client.get(f"/v1/valuation-rounds/{round_id}/plate", headers=intruder)
    associate = client.post(
        f"/v1/valuation-rounds/{round_id}/plate",
        headers=intruder,
        json={"upload_id": str(uuid4()), "base_version": 1},
    )
    extraction = client.post(
        f"/v1/valuation-rounds/{round_id}/plate/extractions",
        headers=intruder,
        json={"base_version": 1},
    )
    listing = client.get("/v1/valuation-rounds", headers=intruder)

    assert [state.status_code, plate.status_code, associate.status_code] == [404, 404, 404]
    assert extraction.status_code == 404
    assert listing.json()["items"] == []


# --- estado e listagem ------------------------------------------------------------------


def test_o_estado_traz_etapas_catalogo_e_extracao(tmp_path: Path) -> None:
    client = _client(tmp_path)
    created = _create_round(client)

    response = client.get(f"/v1/valuation-rounds/{created['round_id']}", headers=_headers())

    assert response.status_code == 200
    body = response.json()
    assert body["round_id"] == created["round_id"]
    assert body["version"] == 1
    assert body["reviewer_role"] == "orcamentista"
    assert body["period_number"] == 1
    assert body["plate"]["present"] is False
    assert body["extraction"]["status"] == "idle"
    assert body["takeoff"]["present"] is False
    assert body["catalog"]["summary"]["entries"] == 1


def test_a_listagem_pagina_por_cursor_e_declara_a_etapa(tmp_path: Path) -> None:
    client = _client(tmp_path)
    first = _create_round(client, key="rodada-1", worksite_key="obra-1")
    second = _create_round(client, key="rodada-2", worksite_key="obra-2")
    third = _create_round(client, key="rodada-3", worksite_key="obra-3")
    assert _associate_plate(client, third["round_id"], key="prancha-3").status_code == 200

    page = client.get("/v1/valuation-rounds?limit=2", headers=_headers()).json()
    assert [item["round_id"] for item in page["items"]] == [
        third["round_id"],
        second["round_id"],
    ]
    assert page["items"][0]["stage"] == "plate"
    assert page["items"][1]["stage"] == "created"
    assert page["next_cursor"] is not None

    tail = client.get(
        f"/v1/valuation-rounds?limit=2&cursor={page['next_cursor']}", headers=_headers()
    ).json()
    assert [item["round_id"] for item in tail["items"]] == [first["round_id"]]
    assert tail["next_cursor"] is None


def test_cursor_invalido_recusa_sem_listar(tmp_path: Path) -> None:
    client = _client(tmp_path)
    _create_round(client)

    response = client.get("/v1/valuation-rounds?cursor=nao-e-cursor", headers=_headers())

    assert response.status_code == 422
    assert response.json()["detail"]["details"]["code"] == "CURSOR_INVALID"


# --- prancha ----------------------------------------------------------------------------


def test_a_prancha_associada_avanca_a_versao_da_rodada(tmp_path: Path) -> None:
    client = _client(tmp_path)
    created = _create_round(client)

    response = _associate_plate(client, created["round_id"])

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["version"] == 2
    assert body["image_url"] is None
    assert body["page_count"] is None
    with _database(client).sessions() as session:
        record = session.scalar(
            select(ValuationRoundRecord).where(ValuationRoundRecord.id == created["round_id"])
        )
        assert record is not None
        assert record.plate_object_key is not None
        assert record.version == 2


def test_segunda_prancha_na_mesma_rodada_recusa(tmp_path: Path) -> None:
    client = _client(tmp_path)
    created = _create_round(client)
    assert _associate_plate(client, created["round_id"]).status_code == 200

    response = _associate_plate(client, created["round_id"], base_version=2, key="prancha-2")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ROUND_PLATE_ALREADY_PRESENT"


def test_base_version_divergente_recusa_sem_gravar_nada(tmp_path: Path) -> None:
    client = _client(tmp_path)
    created = _create_round(client)

    response = _associate_plate(client, created["round_id"], base_version=7)

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "REVISION_CONFLICT"
    assert detail["details"] == {"base_version": 7, "current_version": 1}
    with _database(client).sessions() as session:
        record = session.scalar(
            select(ValuationRoundRecord).where(ValuationRoundRecord.id == created["round_id"])
        )
        assert record is not None
        assert record.plate_object_key is None
        assert record.version == 1
        assert session.scalars(select(ValuationRoundRevisionRecord)).all() == []


def test_a_prancha_ainda_nao_associada_e_etapa_fora_de_ordem(tmp_path: Path) -> None:
    client = _client(tmp_path)
    created = _create_round(client)

    response = client.get(f"/v1/valuation-rounds/{created['round_id']}/plate", headers=_headers())

    assert response.status_code == 409
    body = response.json()["detail"]
    assert body["code"] == "ROUND_STAGE_NOT_READY"
    assert body["details"] == {"stage": "plate"}


def test_a_imagem_promovida_sai_por_url_assinada_e_fora_da_auditoria(tmp_path: Path) -> None:
    client = _client(tmp_path)
    created = _create_round(client)
    assert _associate_plate(client, created["round_id"]).status_code == 200
    image_key = f"tenants/{_TENANT}/valuation-rounds/{created['round_id']}/plate/page-001.png"
    with _database(client).sessions() as session:
        session.add(
            ValuationRoundRevisionRecord(
                id=str(new_uuid7()),
                tenant_id=_TENANT,
                round_id=created["round_id"],
                version=1,
                created_by="valuation-extraction-v1",
                artifact_refs_json={PLATE_IMAGE_REF: image_key},
                artifact_digests_json={},
            )
        )
        session.commit()

    response = client.get(f"/v1/valuation-rounds/{created['round_id']}/plate", headers=_headers())

    assert response.status_code == 200
    image_url = response.json()["image_url"]
    assert image_url is not None
    assert image_key in image_url
    with _database(client).sessions() as session:
        audits = session.scalars(select(AuditRecord)).all()
        assert audits
        assert all(image_url not in json.dumps(audit.metadata_json) for audit in audits)
        assert all(set(audit.metadata_json) == {"request_id"} for audit in audits)


def test_chave_fora_do_prefixo_do_tenant_e_404_sem_chamar_o_presign(tmp_path: Path) -> None:
    """Assinar primeiro e conferir depois entregaria URL válida de objeto alheio."""
    client = _client(tmp_path)
    created = _create_round(client)
    assert _associate_plate(client, created["round_id"]).status_code == 200
    with _database(client).sessions() as session:
        session.add(
            ValuationRoundRevisionRecord(
                id=str(new_uuid7()),
                tenant_id=_TENANT,
                round_id=created["round_id"],
                version=1,
                created_by="valuation-extraction-v1",
                artifact_refs_json={
                    PLATE_IMAGE_REF: f"tenants/{_OTHER_TENANT}/valuation-rounds/x/plate.png"
                },
                artifact_digests_json={},
            )
        )
        session.commit()
    signed: list[str] = []

    def _recording_presign(*, object_key: str) -> str:
        signed.append(object_key)
        return "https://storage.invalid/vazado"

    store = _store(client)
    store.presign_private_read = _recording_presign  # type: ignore[method-assign]

    response = client.get(f"/v1/valuation-rounds/{created['round_id']}/plate", headers=_headers())

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "NOT_FOUND"
    assert signed == []


# --- extração paga ----------------------------------------------------------------------


def test_a_extracao_enfileira_o_comando_da_medicao_sem_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _allow_paid_extraction(monkeypatch)
    client = _client(tmp_path)
    queue = _observed_queue(client)
    created = _create_round(client)
    assert _associate_plate(client, created["round_id"]).status_code == 200

    with caplog.at_level(logging.DEBUG):
        response = client.post(
            f"/v1/valuation-rounds/{created['round_id']}/plate/extractions",
            headers=_headers(key="extracao-001"),
            json={"base_version": 2},
        )

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "queued"
    assert body["version"] == 3
    envelope = json.loads(queue.messages[0]["Body"])
    assert envelope == {
        "command": "extract_valuation_plate",
        "round_id": created["round_id"],
        "extraction_id": body["extraction_id"],
        "tenant_id": _TENANT,
    }
    assert "job_id" not in envelope
    with _database(client).sessions() as session:
        record = session.scalar(
            select(ValuationRoundRecord).where(ValuationRoundRecord.id == created["round_id"])
        )
        assert record is not None
        assert record.extraction_status == "queued"
        assert record.extraction_id == body["extraction_id"]
        assert record.extraction_requested_by == "orcamentista-sintetica"


def test_extracao_em_voo_recusa_a_segunda_chamada(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _allow_paid_extraction(monkeypatch)
    client = _client(tmp_path)
    _observed_queue(client)
    created = _create_round(client)
    assert _associate_plate(client, created["round_id"]).status_code == 200
    first = client.post(
        f"/v1/valuation-rounds/{created['round_id']}/plate/extractions",
        headers=_headers(key="extracao-001"),
        json={"base_version": 2},
    )
    assert first.status_code == 202

    response = client.post(
        f"/v1/valuation-rounds/{created['round_id']}/plate/extractions",
        headers=_headers(key="extracao-002"),
        json={"base_version": 3},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "EXTRACTION_IN_PROGRESS"


def test_pacote_ja_publicado_recusa_nova_extracao(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _allow_paid_extraction(monkeypatch)
    client = _client(tmp_path)
    _observed_queue(client)
    created = _create_round(client)
    assert _associate_plate(client, created["round_id"]).status_code == 200
    with _database(client).sessions() as session:
        session.add(
            ValuationRoundRevisionRecord(
                id=str(new_uuid7()),
                tenant_id=_TENANT,
                round_id=created["round_id"],
                version=1,
                created_by="valuation-extraction-v1",
                takeoff_packet_json={"plate_id": "prancha-sintetica"},
                artifact_refs_json={},
                artifact_digests_json={},
            )
        )
        session.commit()

    response = client.post(
        f"/v1/valuation-rounds/{created['round_id']}/plate/extractions",
        headers=_headers(key="extracao-001"),
        json={"base_version": 2},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ROUND_PLATE_ALREADY_PRESENT"


def test_extracao_sem_prancha_e_etapa_fora_de_ordem(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _allow_paid_extraction(monkeypatch)
    client = _client(tmp_path)
    queue = _observed_queue(client)
    created = _create_round(client)

    response = client.post(
        f"/v1/valuation-rounds/{created['round_id']}/plate/extractions",
        headers=_headers(key="extracao-001"),
        json={"base_version": 1},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ROUND_STAGE_NOT_READY"
    assert list(queue.messages) == []


def test_entitlement_revogado_recusa_sem_enfileirar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _allow_paid_extraction(monkeypatch)
    client = _client(tmp_path, real_providers_enabled=True)
    queue = _observed_queue(client)
    created = _create_round(client)
    assert _associate_plate(client, created["round_id"]).status_code == 200

    blocked = client.post(
        f"/v1/valuation-rounds/{created['round_id']}/plate/extractions",
        headers=_headers(key="extracao-001"),
        json={"base_version": 2},
    )

    assert blocked.status_code == 403
    assert blocked.json()["detail"]["code"] == "AI_PROCESSING_NOT_AUTHORIZED"
    assert list(queue.messages) == []
    with _database(client).sessions() as session:
        record = session.scalar(
            select(ValuationRoundRecord).where(ValuationRoundRecord.id == created["round_id"])
        )
        assert record is not None
        assert record.extraction_status == "idle"
        assert record.version == 2

    _grant_entitlement(client)
    allowed = client.post(
        f"/v1/valuation-rounds/{created['round_id']}/plate/extractions",
        headers=_headers(key="extracao-002"),
        json={"base_version": 2},
    )

    assert allowed.status_code == 202
    assert len(queue.messages) == 1


def test_ambiente_sem_teto_de_gasto_devolve_provider_indisponivel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pré-checagem roda antes de qualquer byte sair: sem teto, nada é enfileirado."""
    monkeypatch.delenv(AI_BUDGET_ENV, raising=False)
    monkeypatch.delenv(_ANTHROPIC_KEY_ENV, raising=False)
    client = _client(tmp_path)
    queue = _observed_queue(client)
    created = _create_round(client)
    assert _associate_plate(client, created["round_id"]).status_code == 200

    response = client.post(
        f"/v1/valuation-rounds/{created['round_id']}/plate/extractions",
        headers=_headers(key="extracao-001"),
        json={"base_version": 2},
    )

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["code"] == "PROVIDER_UNAVAILABLE"
    assert AI_BUDGET_ENV not in json.dumps(detail)
    assert list(queue.messages) == []


def test_fila_indisponivel_persiste_o_intent_e_o_comando_e_repetivel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _allow_paid_extraction(monkeypatch)
    client = _client(tmp_path)
    created = _create_round(client)
    assert _associate_plate(client, created["round_id"]).status_code == 200

    class _RefusingClient:
        def send_message(self, **_kwargs: Any) -> None:
            raise BotoCoreError()

    processing_queue = cast(Any, client.app).state.queue
    processing_queue.queue_url = "http://localstack/queue"
    processing_queue.client = _RefusingClient()

    refused = client.post(
        f"/v1/valuation-rounds/{created['round_id']}/plate/extractions",
        headers=_headers(key="extracao-001"),
        json={"base_version": 2},
    )

    assert refused.status_code == 503
    assert refused.json()["detail"]["code"] == "PROCESSING_UNAVAILABLE"
    with _database(client).sessions() as session:
        record = session.scalar(
            select(ValuationRoundRecord).where(ValuationRoundRecord.id == created["round_id"])
        )
        assert record is not None
        assert record.extraction_status == "queued"
        extraction_id = record.extraction_id

    queue = _observed_queue(client)
    retried = client.post(
        f"/v1/valuation-rounds/{created['round_id']}/plate/extractions",
        headers=_headers(key="extracao-001"),
        json={"base_version": 2},
    )

    assert retried.status_code == 202
    assert retried.json()["extraction_id"] == extraction_id
    assert json.loads(queue.messages[0]["Body"])["extraction_id"] == extraction_id
    with _database(client).sessions() as session:
        record = session.scalar(
            select(ValuationRoundRecord).where(ValuationRoundRecord.id == created["round_id"])
        )
        assert record is not None
        # A repetição não abre extração nova nem avança a rodada de novo.
        assert record.extraction_id == extraction_id
        assert record.version == 3
