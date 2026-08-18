"""Rotas `/v1/valuation-rounds` de F-003 (T6/T7/T9): criação, prancha e takeoff.

O que estes testes protegem, além do caminho feliz:

- **papel antes do lookup**: quem não é `orcamentista` recebe `403` mesmo para uma rodada
  que não existe, e por isso não descobre pela diferença entre `403` e `404` o que existe
  no tenant vizinho;
- **IDOR**: rodada de outro tenant é `404`, nunca `403`;
- **concorrência otimista**: `base_version` divergente recusa sem gravar linha nenhuma;
- **URL assinada**: sai só depois de conferido o prefixo do tenant e nunca entra em
  auditoria — as duas coisas verificadas contra o banco, não contra a resposta;
- **chamada paga**: entitlement revogado não enfileira, extração em voo recusa, e a fila
  indisponível devolve `503` com o intent já durável;
- **overlay do takeoff**: a decisão do orçamentista nunca espera pelo desenho, e um desenho
  do pacote anterior jamais é servido como se fosse do corrente (ADR-0030).
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
from croquito_api.valuation_rounds import document_digest
from croquito_core.ids import new_uuid7
from croquito_valuation.models import PriceCatalog, PriceCatalogEntry
from croquito_valuation.takeoff import (
    PlateBox,
    PlateEvidence,
    TakeoffItem,
    TakeoffItemStatus,
    TakeoffPacket,
)
from croquito_worker.valuation.round_extraction import (
    AI_BUDGET_ENV,
    PLATE_IMAGE_DIGEST,
    PLATE_IMAGE_REF,
    TAKEOFF_OVERLAY_DIGEST,
    TAKEOFF_OVERLAY_PACKET_DIGEST,
    TAKEOFF_OVERLAY_REF,
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


_ITEM_CLEAR = "ti_00000000000000a1"
_ITEM_AMBIGUOUS = "ti_00000000000000a2"
_IMAGE_DIGEST = "a" * 64
_OVERLAY_DIGEST = "e" * 64


def _takeoff_item(
    *, item_id: str = _ITEM_CLEAR, status: TakeoffItemStatus = TakeoffItemStatus.PROPOSED
) -> TakeoffItem:
    """Item sintético como a extração o publica: proposto, e ambíguo sem quantidade."""
    ambiguous = status is TakeoffItemStatus.AMBIGUOUS
    return TakeoffItem(
        id=item_id,
        evidence=PlateEvidence(
            plate_id="rodada-sintetica",
            page_number=1,
            image_sha256=_IMAGE_DIGEST,
            bbox=PlateBox(left=10, top=10, right=210, bottom=60),
        ),
        raw_text="ALAMBRADO GALVANIZADO --- m" if ambiguous else "ALAMBRADO GALVANIZADO 10,00 m",
        label="ALAMBRADO GALVANIZADO",
        quantity=None if ambiguous else Decimal("10.00"),
        unit="m",
        source="legend_extraction",
        extractor="legend-extractor-sintetico",
        extractor_version="1.0.0",
        status=status,
    )


def _takeoff_packet(items: list[TakeoffItem] | None = None) -> TakeoffPacket:
    return TakeoffPacket(
        plate_id="rodada-sintetica",
        page_number=1,
        image_sha256=_IMAGE_DIGEST,
        source_pdf_sha256="b" * 64,
        items=items if items is not None else [_takeoff_item()],
        safety_notes=[
            "Extração automática da legenda; quantidade não confirmada.",
            "Decisão do orçamentista obrigatória antes de qualquer boletim.",
        ],
    )


def _publish_takeoff(
    client: TestClient,
    round_id: str,
    packet: TakeoffPacket,
    *,
    tenant: str = _TENANT,
    overlay: bool = True,
    overlay_packet_sha256: str | None = None,
    overlay_key: str | None = None,
) -> dict[str, Any]:
    """Publica pacote e overlay como o comando de fila faria, e avança a rodada.

    O teste escreve a revisão direto porque a extração é PAGA: exercitá-la aqui só para
    chegar ao takeoff faria cada teste desta seção depender do braço do provider.
    """
    document = packet.model_dump(mode="json")
    digest = document_digest(document)
    refs = {PLATE_IMAGE_REF: f"tenants/{tenant}/valuation-rounds/{round_id}/plate/page-001.png"}
    digests = {PLATE_IMAGE_DIGEST: packet.image_sha256}
    if overlay:
        refs[TAKEOFF_OVERLAY_REF] = overlay_key or (
            f"tenants/{tenant}/valuation-rounds/{round_id}/takeoff/overlay.png"
        )
        digests[TAKEOFF_OVERLAY_DIGEST] = _OVERLAY_DIGEST
        digests[TAKEOFF_OVERLAY_PACKET_DIGEST] = overlay_packet_sha256 or digest
    with _database(client).sessions() as session:
        record = session.get(ValuationRoundRecord, round_id)
        assert record is not None
        session.add(
            ValuationRoundRevisionRecord(
                id=str(new_uuid7()),
                tenant_id=tenant,
                round_id=round_id,
                version=1,
                created_by="valuation-extraction-v1",
                takeoff_packet_json=document,
                artifact_refs_json=refs,
                artifact_digests_json=digests,
            )
        )
        record.version += 1
        session.commit()
        version = record.version
    return {"packet_sha256": digest, "version": version, "refs": refs}


def _round_with_takeoff(
    client: TestClient, packet: TakeoffPacket | None = None, **overrides: Any
) -> dict[str, Any]:
    created = _create_round(client)
    published = _publish_takeoff(
        client, created["round_id"], packet or _takeoff_packet(), **overrides
    )
    return {"round_id": created["round_id"], **published}


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
        client.get(f"/v1/valuation-rounds/{round_id}/takeoff"),
        client.get(f"/v1/valuation-rounds/{round_id}/takeoff/overlay"),
        client.post(
            f"/v1/valuation-rounds/{round_id}/takeoff/decisions",
            json={"base_version": 1, "item_id": _ITEM_CLEAR, "action": "confirm"},
        ),
    ]

    assert [response.status_code for response in responses] == [401] * 9


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
        client.get(f"/v1/valuation-rounds/{unknown}/takeoff", headers=headers),
        client.get(f"/v1/valuation-rounds/{unknown}/takeoff/overlay", headers=headers),
        client.post(
            f"/v1/valuation-rounds/{unknown}/takeoff/decisions",
            headers=headers,
            json={"base_version": 1, "item_id": _ITEM_CLEAR, "action": "confirm"},
        ),
    ]

    assert [response.status_code for response in responses] == [403] * 9
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
    takeoff = client.get(f"/v1/valuation-rounds/{round_id}/takeoff", headers=intruder)
    overlay = client.get(f"/v1/valuation-rounds/{round_id}/takeoff/overlay", headers=intruder)
    decision = client.post(
        f"/v1/valuation-rounds/{round_id}/takeoff/decisions",
        headers=_headers(_OTHER_TENANT, key="intruso-002"),
        json={"base_version": 1, "item_id": _ITEM_CLEAR, "action": "confirm"},
    )

    assert [state.status_code, plate.status_code, associate.status_code] == [404, 404, 404]
    assert extraction.status_code == 404
    assert [takeoff.status_code, overlay.status_code, decision.status_code] == [404, 404, 404]
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


# --- takeoff: leitura -------------------------------------------------------------------


def test_o_takeoff_sai_com_ancora_por_item_contagens_e_digest(tmp_path: Path) -> None:
    client = _client(tmp_path)
    published = _round_with_takeoff(
        client,
        _takeoff_packet(
            [
                _takeoff_item(),
                _takeoff_item(item_id=_ITEM_AMBIGUOUS, status=TakeoffItemStatus.AMBIGUOUS),
            ]
        ),
    )

    response = client.get(
        f"/v1/valuation-rounds/{published['round_id']}/takeoff", headers=_headers()
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["round_id"] == published["round_id"]
    assert body["version"] == published["version"]
    assert body["packet_sha256"] == published["packet_sha256"]
    assert body["review_status"] == "review_required"
    assert body["items"] == 2
    assert body["pending"] == 2
    assert body["proposed"] == 1
    assert body["ambiguous"] == 1
    assert body["confirmed"] == 0
    assert body["rejected"] == 0
    # Sem relatório de registro fino, nenhuma âncora é confiável (fail-closed).
    assert body["anchors_registered"] == 0
    assert body["anchors_raw"] == 2
    assert [item["anchor"] for item in body["packet"]["items"]] == ["raw", "raw"]


def test_o_digest_do_takeoff_e_o_mesmo_que_o_estado_da_rodada_publica(tmp_path: Path) -> None:
    """Dois valores diferentes fariam a tela achar que o pacote mudou entre duas telas."""
    client = _client(tmp_path)
    published = _round_with_takeoff(client)

    takeoff = client.get(
        f"/v1/valuation-rounds/{published['round_id']}/takeoff", headers=_headers()
    ).json()
    state = client.get(f"/v1/valuation-rounds/{published['round_id']}", headers=_headers()).json()

    assert takeoff["packet_sha256"] == state["takeoff"]["packet_sha256"]


def test_takeoff_sem_pacote_publicado_e_etapa_fora_de_ordem(tmp_path: Path) -> None:
    client = _client(tmp_path)
    created = _create_round(client)

    response = client.get(f"/v1/valuation-rounds/{created['round_id']}/takeoff", headers=_headers())

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "ROUND_STAGE_NOT_READY"
    assert detail["details"] == {"stage": "takeoff"}


# --- takeoff: overlay -------------------------------------------------------------------


def test_o_overlay_sai_por_url_assinada_e_declara_o_pacote_de_origem(tmp_path: Path) -> None:
    client = _client(tmp_path)
    published = _round_with_takeoff(client)

    response = client.get(
        f"/v1/valuation-rounds/{published['round_id']}/takeoff/overlay", headers=_headers()
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert published["refs"][TAKEOFF_OVERLAY_REF] in body["image_url"]
    assert body["image_sha256"] == _OVERLAY_DIGEST
    assert body["packet_sha256"] == published["packet_sha256"]
    assert body["overlay_packet_sha256"] == published["packet_sha256"]
    assert body["stale"] is False


def test_overlay_vencido_e_200_com_a_marca_e_nunca_passa_por_corrente(tmp_path: Path) -> None:
    """Esconder a divergência é pior do que declará-la (ADR-0030)."""
    client = _client(tmp_path)
    published = _round_with_takeoff(client, overlay_packet_sha256="f" * 64)

    response = client.get(
        f"/v1/valuation-rounds/{published['round_id']}/takeoff/overlay", headers=_headers()
    )

    assert response.status_code == 200
    body = response.json()
    assert body["stale"] is True
    assert body["overlay_packet_sha256"] == "f" * 64
    assert body["packet_sha256"] == published["packet_sha256"]
    assert body["image_url"]


def test_overlay_sem_pacote_de_origem_declarado_sai_vencido(tmp_path: Path) -> None:
    """Overlay publicado antes deste contrato não afirma frescor que não pode provar."""
    client = _client(tmp_path)
    published = _round_with_takeoff(client)
    with _database(client).sessions() as session:
        revision = session.scalars(select(ValuationRoundRevisionRecord)).one()
        digests = dict(revision.artifact_digests_json)
        digests.pop(TAKEOFF_OVERLAY_PACKET_DIGEST)
        revision.artifact_digests_json = digests
        session.commit()

    body = client.get(
        f"/v1/valuation-rounds/{published['round_id']}/takeoff/overlay", headers=_headers()
    ).json()

    assert body["stale"] is True
    assert body["overlay_packet_sha256"] is None


def test_overlay_ausente_e_etapa_fora_de_ordem(tmp_path: Path) -> None:
    client = _client(tmp_path)
    published = _round_with_takeoff(client, overlay=False)
    created = _create_round(client, key="rodada-sem-takeoff")

    published_response = client.get(
        f"/v1/valuation-rounds/{published['round_id']}/takeoff/overlay", headers=_headers()
    )
    empty_response = client.get(
        f"/v1/valuation-rounds/{created['round_id']}/takeoff/overlay", headers=_headers()
    )

    assert [published_response.status_code, empty_response.status_code] == [409, 409]
    for response in (published_response, empty_response):
        detail = response.json()["detail"]
        assert detail["code"] == "ROUND_STAGE_NOT_READY"
        assert detail["details"] == {"stage": "takeoff"}


def test_overlay_fora_do_prefixo_do_tenant_e_404_sem_chamar_o_presign(tmp_path: Path) -> None:
    client = _client(tmp_path)
    published = _round_with_takeoff(
        client, overlay_key=f"tenants/{_OTHER_TENANT}/valuation-rounds/x/takeoff/overlay.png"
    )
    signed: list[str] = []

    def _recording_presign(*, object_key: str) -> str:
        signed.append(object_key)
        return "https://storage.invalid/vazado"

    _store(client).presign_private_read = _recording_presign  # type: ignore[method-assign]

    response = client.get(
        f"/v1/valuation-rounds/{published['round_id']}/takeoff/overlay", headers=_headers()
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "NOT_FOUND"
    assert signed == []


# --- takeoff: decisão do orçamentista ---------------------------------------------------


def _decide(
    client: TestClient,
    round_id: str,
    *,
    base_version: int,
    tenant: str = _TENANT,
    key: str = "decisao-001",
    **body: Any,
) -> Any:
    payload: dict[str, Any] = {
        "base_version": base_version,
        "item_id": _ITEM_CLEAR,
        "action": "confirm",
    }
    payload.update(body)
    return client.post(
        f"/v1/valuation-rounds/{round_id}/takeoff/decisions",
        headers=_headers(tenant, key=key),
        json=payload,
    )


def test_a_decisao_grava_revisao_avanca_a_rodada_e_enfileira_o_overlay(tmp_path: Path) -> None:
    client = _client(tmp_path)
    queue = _observed_queue(client)
    published = _round_with_takeoff(client)

    response = _decide(
        client, published["round_id"], base_version=published["version"], quantity="12.00"
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["version"] == published["version"] + 1
    assert body["review_status"] == "complete"
    assert body["confirmed"] == 1
    assert body["pending"] == 0
    item = body["packet"]["items"][0]
    assert item["status"] == "confirmed"
    # Quantidade sai como TEXTO: `float` já teria perdido a escala escrita na legenda.
    assert item["quantity"] == "12.00"
    assert item["decision"]["reviewer_id"] == "orcamentista-sintetica"
    assert item["decision"]["reviewer_role"] == "orcamentista"
    # O overlay é consequência da decisão, não parte dela: até o worker redesenhá-lo, ele
    # declara o pacote anterior.
    assert body["overlay"]["stale"] is True
    assert body["overlay"]["overlay_packet_sha256"] == published["packet_sha256"]

    envelope = json.loads(queue.messages[0]["Body"])
    assert envelope == {
        "command": "rerender_takeoff_overlay",
        "round_id": published["round_id"],
        "tenant_id": _TENANT,
        "packet_sha256": body["packet_sha256"],
    }
    assert "job_id" not in envelope
    with _database(client).sessions() as session:
        record = session.get(ValuationRoundRecord, published["round_id"])
        assert record is not None
        assert record.version == published["version"] + 1
        revisions = session.scalars(
            select(ValuationRoundRevisionRecord).order_by(ValuationRoundRevisionRecord.version)
        ).all()
        assert [revision.version for revision in revisions] == [1, 2]
        assert revisions[1].created_by == "orcamentista-sintetica"
        assert revisions[1].parent_revision_id == revisions[0].id
        # Revisão é append-only: o pacote anterior continua exatamente como estava.
        assert revisions[0].takeoff_packet_json is not None
        assert revisions[0].takeoff_packet_json["items"][0]["status"] == "proposed"


def test_o_digest_enfileirado_sobrevive_a_ida_e_volta_do_banco(tmp_path: Path) -> None:
    """O worker recalcula o digest a partir da COLUNA, não do corpo que a rota enviou.

    Se a ida e volta pelo JSON do banco mudasse um único caractere da serialização, todo
    comando de re-render seria descartado por "pacote defasado" e o overlay ficaria vencido
    para sempre — falha que nenhum teste de um lado só perceberia.
    """
    client = _client(tmp_path)
    queue = _observed_queue(client)
    published = _round_with_takeoff(client)

    response = _decide(
        client, published["round_id"], base_version=published["version"], quantity="12.00"
    )

    assert response.status_code == 200, response.text
    enqueued = json.loads(queue.messages[0]["Body"])["packet_sha256"]
    with _database(client).sessions() as session:
        head = session.scalars(
            select(ValuationRoundRevisionRecord).order_by(
                ValuationRoundRevisionRecord.version.desc()
            )
        ).first()
        assert head is not None
        assert document_digest(head.takeoff_packet_json or {}) == enqueued


def test_a_decisao_com_fila_indisponivel_responde_200_e_deixa_o_overlay_vencido(
    tmp_path: Path,
) -> None:
    """A decisão já está durável quando o comando é publicado: falha de transporte não a
    derruba, e traduzi-la em `503` faria o cliente repetir um ato que já valeu."""
    client = _client(tmp_path)
    published = _round_with_takeoff(client)

    class _RefusingClient:
        def send_message(self, **_kwargs: Any) -> None:
            raise BotoCoreError()

    processing_queue = cast(Any, client.app).state.queue
    processing_queue.queue_url = "http://localstack/queue"
    processing_queue.client = _RefusingClient()

    response = _decide(client, published["round_id"], base_version=published["version"])

    assert response.status_code == 200, response.text
    assert response.json()["overlay"]["stale"] is True
    with _database(client).sessions() as session:
        record = session.get(ValuationRoundRecord, published["round_id"])
        assert record is not None
        assert record.version == published["version"] + 1
        assert len(session.scalars(select(ValuationRoundRevisionRecord)).all()) == 2
    overlay = client.get(
        f"/v1/valuation-rounds/{published['round_id']}/takeoff/overlay", headers=_headers()
    ).json()
    assert overlay["stale"] is True
    assert overlay["overlay_packet_sha256"] == published["packet_sha256"]


def test_item_ja_revisado_recusa_com_o_vocabulario_do_dominio(tmp_path: Path) -> None:
    client = _client(tmp_path)
    _observed_queue(client)
    published = _round_with_takeoff(client)
    first = _decide(client, published["round_id"], base_version=published["version"])
    assert first.status_code == 200, first.text

    response = _decide(
        client, published["round_id"], base_version=published["version"] + 1, key="decisao-002"
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "DOMAIN_VALIDATION_FAILED"
    assert detail["details"]["code"] == "TAKEOFF_ITEM_ALREADY_REVIEWED"


def test_confirmar_item_ambiguo_sem_quantidade_recusa_com_codigo_de_dominio(
    tmp_path: Path,
) -> None:
    """A invariante sobe embrulhada pelo Pydantic; o código de domínio continua saindo."""
    client = _client(tmp_path)
    queue = _observed_queue(client)
    published = _round_with_takeoff(
        client,
        _takeoff_packet(
            [_takeoff_item(item_id=_ITEM_AMBIGUOUS, status=TakeoffItemStatus.AMBIGUOUS)]
        ),
    )

    response = _decide(
        client, published["round_id"], base_version=published["version"], item_id=_ITEM_AMBIGUOUS
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "DOMAIN_VALIDATION_FAILED"
    assert detail["details"]["code"] == "TAKEOFF_ITEM_CONFIRMED_INCOMPLETE"
    assert list(queue.messages) == []
    with _database(client).sessions() as session:
        assert len(session.scalars(select(ValuationRoundRevisionRecord)).all()) == 1


def test_quantidade_ilegivel_recusa_antes_de_qualquer_gravacao(tmp_path: Path) -> None:
    client = _client(tmp_path)
    published = _round_with_takeoff(client)

    response = _decide(
        client, published["round_id"], base_version=published["version"], quantity="doze"
    )

    assert response.status_code == 422
    assert response.json()["detail"]["details"]["code"] == "LOCAL_QUANTITY_INVALID"
    with _database(client).sessions() as session:
        assert len(session.scalars(select(ValuationRoundRevisionRecord)).all()) == 1


def test_item_desconhecido_recusa_sem_gravar(tmp_path: Path) -> None:
    client = _client(tmp_path)
    published = _round_with_takeoff(client)

    response = _decide(
        client,
        published["round_id"],
        base_version=published["version"],
        item_id="ti_00000000000000ff",
    )

    assert response.status_code == 422
    assert response.json()["detail"]["details"]["code"] == "TAKEOFF_DECISION_UNKNOWN_ITEM"


def test_base_version_divergente_na_decisao_recusa_sem_gravar_nada(tmp_path: Path) -> None:
    client = _client(tmp_path)
    queue = _observed_queue(client)
    published = _round_with_takeoff(client)

    response = _decide(client, published["round_id"], base_version=published["version"] + 7)

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "REVISION_CONFLICT"
    assert detail["details"] == {
        "base_version": published["version"] + 7,
        "current_version": published["version"],
    }
    assert list(queue.messages) == []
    with _database(client).sessions() as session:
        record = session.get(ValuationRoundRecord, published["round_id"])
        assert record is not None
        assert record.version == published["version"]
        assert len(session.scalars(select(ValuationRoundRevisionRecord)).all()) == 1


def test_decisao_sem_takeoff_publicado_e_etapa_fora_de_ordem(tmp_path: Path) -> None:
    client = _client(tmp_path)
    created = _create_round(client)

    response = _decide(client, created["round_id"], base_version=1)

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ROUND_STAGE_NOT_READY"


def test_idempotencia_da_decisao_devolve_a_mesma_resposta(tmp_path: Path) -> None:
    client = _client(tmp_path)
    queue = _observed_queue(client)
    published = _round_with_takeoff(client)

    first = _decide(client, published["round_id"], base_version=published["version"])
    second = _decide(client, published["round_id"], base_version=published["version"])
    reused = _decide(
        client, published["round_id"], base_version=published["version"], quantity="9.00"
    )

    assert first.status_code == 200
    assert second.json() == first.json()
    assert reused.status_code == 409
    assert reused.json()["detail"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert len(queue.messages) == 1
    with _database(client).sessions() as session:
        assert len(session.scalars(select(ValuationRoundRevisionRecord)).all()) == 2


def test_decisao_sem_idempotency_key_recusa(tmp_path: Path) -> None:
    client = _client(tmp_path)
    published = _round_with_takeoff(client)
    headers = _headers()
    headers.pop("Idempotency-Key")

    response = client.post(
        f"/v1/valuation-rounds/{published['round_id']}/takeoff/decisions",
        headers=headers,
        json={"base_version": published["version"], "item_id": _ITEM_CLEAR, "action": "confirm"},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"


def test_o_corpo_da_decisao_recusa_o_carimbo_de_identidade(tmp_path: Path) -> None:
    """Identidade vem do `Principal` e instante do servidor; o corpo não carimba nenhum."""
    client = _client(tmp_path)
    published = _round_with_takeoff(client)

    for forbidden in ("reviewer_id", "reviewer_role", "decided_at", "decision_id"):
        response = _decide(
            client,
            published["round_id"],
            base_version=published["version"],
            key=f"decisao-{forbidden}",
            **{forbidden: "x"},
        )

        assert response.status_code == 422, forbidden
        assert "extra" in response.text.lower()
    with _database(client).sessions() as session:
        assert len(session.scalars(select(ValuationRoundRevisionRecord)).all()) == 1


def test_a_decisao_registra_auditoria_sem_url_assinada_nem_conteudo(tmp_path: Path) -> None:
    client = _client(tmp_path)
    _observed_queue(client)
    published = _round_with_takeoff(client)

    assert (
        _decide(client, published["round_id"], base_version=published["version"]).status_code == 200
    )

    with _database(client).sessions() as session:
        audits = session.scalars(select(AuditRecord)).all()
        decided = [audit for audit in audits if audit.action == "VALUATION_TAKEOFF_ITEM_DECIDED"]
        assert len(decided) == 1
        assert decided[0].resource_id == published["round_id"]
        assert all(set(audit.metadata_json) == {"request_id"} for audit in audits)
