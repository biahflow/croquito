"""Rotas `/v1/valuation-rounds` de F-003 (T6/T7/T9/T10/T11): da rodada ao boletim e ao dossiê.

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
  do pacote anterior jamais é servido como se fosse do corrente (ADR-0030);
- **shortlist de código**: um `GET` que calcula o artefato derivado não move o token de
  concorrência da rodada, e o refino pago nunca é descartado por recompute determinístico;
- **braço semântico**: híbrido é braço pago — sem entitlement é `403`, e com entitlement e
  sem índice publicado é `503` declarado, nunca léxico fingindo ser híbrido;
- **fechamento da rodada**: a identidade da obra vem da RODADA e o corpo do cálculo a
  recusa, o boletim é recomputado na leitura em vez de servido como gravado, e a fronteira
  licitada fecha em `BULLETIN_PRICE_ORIGIN_FORBIDDEN` (ADR-0027) — item fora do SCO vira
  dossiê de aditivo, nunca preço de outra tabela.
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

from croquito_api import valuation_rounds
from croquito_api.config import ApiSettings
from croquito_api.database import (
    AuditRecord,
    Database,
    DomainEventRecord,
    TenantAiProcessingEntitlementRecord,
    ValuationRoundRecord,
    ValuationRoundRevisionRecord,
)
from croquito_api.main import create_app
from croquito_api.valuation_rounds import (
    append_revision,
    approve_valuation,
    bulletin_export_contract,
    document_digest,
)
from croquito_core.ids import new_uuid7
from croquito_valuation.assignment import (
    LLM_RERANK_SUFFIX,
    CodeSuggestionSet,
    SuggestionRefinement,
)
from croquito_valuation.calc_matrix import (
    CalcContribution,
    CalcMatrix,
    ServiceContributions,
)
from croquito_valuation.canonical import AuditedWorksite, AuditFinding, AuditReport
from croquito_valuation.models import (
    CalcOperand,
    CalcRecipe,
    ContributionBasis,
    PriceCatalog,
    PriceCatalogEntry,
    PriceOrigin,
    Valuation,
)
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


def _catalog_bytes(*, unit: str = "m", origin: PriceOrigin = PriceOrigin.SCO) -> bytes:
    """Catálogo sintético de uma entrada.

    `unit` existe para exercitar a unidade divergente; `origin` para exercitar a fronteira
    licitada do ADR-0027 — o código sintético satisfaz tanto o padrão fechado do SCO quanto
    o superset das demais origens, então a única coisa que muda entre os dois é a origem.
    """
    catalog = PriceCatalog(
        source_label="CATALOGO SINTETICO",
        reference_month="2026-01",
        source_sha256="c" * 64,
        origin=origin,
        entries=[
            PriceCatalogEntry(
                code="CE04100010(/)",
                description="ALAMBRADO GALVANIZADO",
                unit=unit,
                unit_price=Decimal("50.00"),
                family_code="CE",
                family_name="SERVICOS SINTETICOS",
                subgroup_code="CE0410",
                subgroup_name="ITENS SINTETICOS",
                origin=origin,
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
    client: TestClient,
    *,
    tenant: str = _TENANT,
    key: str = "catalogo-001",
    unit: str = "m",
    origin: PriceOrigin = PriceOrigin.SCO,
) -> dict[str, Any]:
    return _presign_and_put(
        client,
        tenant=tenant,
        filename="catalogo.json",
        content_type="application/json",
        payload=_catalog_bytes(unit=unit, origin=origin),
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
    catalog_unit: str = "m",
    catalog_origin: PriceOrigin = PriceOrigin.SCO,
    **overrides: Any,
) -> dict[str, Any]:
    upload = _catalog_upload(
        client, tenant=tenant, key=f"catalogo-{key}", unit=catalog_unit, origin=catalog_origin
    )
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
_ITEM_SECOND = "ti_00000000000000a3"
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


def test_chave_de_obra_fora_do_padrao_recusa_na_criacao_e_nao_no_boletim(
    tmp_path: Path,
) -> None:
    """A chave é imutável na rodada, então recusá-la tarde é recusá-la sem conserto.

    O domínio exige `WORKSITE_KEY_PATTERN` só quando o boletim é montado; sem esta guarda a
    rodada nasceria válida com `PRAÇA X` e quebraria no `POST /calc`, dezenas de decisões
    depois, quando a única saída seria abrir rodada nova e refazer a revisão inteira.
    """
    client = _client(tmp_path)
    upload = _catalog_upload(client)

    response = client.post(
        "/v1/valuation-rounds",
        headers=_headers(),
        json=_round_payload(catalog_upload_id=upload["upload_id"], worksite_key="PRAÇA X"),
    )

    assert response.status_code == 422
    assert not _revisions(client)


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


# --- códigos: shortlist, busca e decisão ------------------------------------------------

_CATALOG_CODE = "CE04100010(/)"
_CODE_OUT_OF_CATALOG = "CE04100099(/)"


def _round_with_confirmed_item(
    client: TestClient, *, catalog_unit: str = "m", key: str = "rodada-codigos"
) -> dict[str, Any]:
    """Rodada com o takeoff publicado e o único item já confirmado pelo orçamentista.

    O item é confirmado pela ROTA de decisão, e não escrito à mão: é a revisão completa do
    takeoff que abre a etapa de código, e fabricá-la direto no banco esconderia justamente a
    precondição que a shortlist exige.
    """
    created = _create_round(client, key=key, catalog_unit=catalog_unit)
    published = _publish_takeoff(client, created["round_id"], _takeoff_packet())
    decided = _decide(
        client,
        created["round_id"],
        base_version=published["version"],
        quantity="10.00",
        key=f"{key}-takeoff",
    )
    assert decided.status_code == 200, decided.text
    return {"round_id": created["round_id"], "version": decided.json()["version"]}


def _revisions(client: TestClient) -> list[ValuationRoundRevisionRecord]:
    with _database(client).sessions() as session:
        return list(
            session.scalars(
                select(ValuationRoundRevisionRecord).order_by(ValuationRoundRevisionRecord.version)
            ).all()
        )


def _round_version(client: TestClient, round_id: str) -> int:
    with _database(client).sessions() as session:
        record = session.get(ValuationRoundRecord, round_id)
        assert record is not None
        return record.version


def _suggestions(client: TestClient, round_id: str) -> Any:
    return client.get(f"/v1/valuation-rounds/{round_id}/code-suggestions", headers=_headers())


def _decide_code(
    client: TestClient,
    round_id: str,
    *,
    base_version: int,
    tenant: str = _TENANT,
    key: str = "codigo-001",
    **body: Any,
) -> Any:
    payload: dict[str, Any] = {
        "base_version": base_version,
        "item_id": _ITEM_CLEAR,
        "action": "confirm",
        "code": _CATALOG_CODE,
    }
    payload.update(body)
    return client.post(
        f"/v1/valuation-rounds/{round_id}/code-assignments/decisions",
        headers=_headers(tenant, key=key),
        json=payload,
    )


def _close_package(
    client: TestClient,
    round_id: str,
    *,
    base_version: int,
    tenant: str = _TENANT,
    key: str = "fechamento-001",
    **body: Any,
) -> Any:
    payload: dict[str, Any] = {"base_version": base_version, "item_id": _ITEM_CLEAR}
    payload.update(body)
    return client.post(
        f"/v1/valuation-rounds/{round_id}/code-assignments/closures",
        headers=_headers(tenant, key=key),
        json=payload,
    )


def test_a_shortlist_e_calculada_uma_vez_e_nao_avanca_a_versao_da_rodada(tmp_path: Path) -> None:
    """Artefato derivado entra na cadeia sem mover o token de concorrência (decisão de
    2026-08-17): um `GET` que avançasse a versão faria a decisão seguinte levar `409`."""
    client = _client(tmp_path)
    prepared = _round_with_confirmed_item(client)

    first = _suggestions(client, prepared["round_id"])

    assert first.status_code == 200, first.text
    body = first.json()
    assert body["computed"] is True
    assert body["matching"] == "lexical"
    assert body["version"] == prepared["version"]
    assert body["semantic_notes"], "o motivo do braço ausente precisa viajar na resposta"
    suggestions = CodeSuggestionSet.model_validate(body["suggestions"])
    assert [item.item_id for item in suggestions.suggestions] == [_ITEM_CLEAR]
    assert suggestions.suggestions[0].candidates[0].code == _CATALOG_CODE
    # A revisão nova existe (a shortlist ficou gravada) e a versão da rodada não andou.
    revisions = _revisions(client)
    assert [revision.version for revision in revisions] == [1, 2, 3]
    assert revisions[-1].code_suggestions_json is not None
    assert _round_version(client, prepared["round_id"]) == prepared["version"]

    second = _suggestions(client, prepared["round_id"])

    assert second.status_code == 200
    assert second.json()["computed"] is False
    assert second.json()["suggestions_sha256"] == body["suggestions_sha256"]
    assert second.json()["suggestions"] == body["suggestions"]
    # Nenhuma revisão nova: a segunda leitura serve o artefato, não o recalcula.
    assert len(_revisions(client)) == 3


def test_a_shortlist_recusa_takeoff_com_revisao_incompleta(tmp_path: Path) -> None:
    """Shortlist sobre pacote meio revisado congelaria um artefato sem os itens que ainda
    vão ser confirmados — e a leitura seguinte serviria justamente esse artefato."""
    client = _client(tmp_path)
    published = _round_with_takeoff(client)

    response = _suggestions(client, published["round_id"])

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "TAKEOFF_REVIEW_INCOMPLETE"
    assert detail["details"]["pending_item_ids"] == [_ITEM_CLEAR]
    assert len(_revisions(client)) == 1


def test_a_shortlist_sem_takeoff_publicado_e_etapa_fora_de_ordem(tmp_path: Path) -> None:
    client = _client(tmp_path)
    created = _create_round(client)

    response = _suggestions(client, created["round_id"])

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ROUND_STAGE_NOT_READY"


def test_catalogo_indisponivel_recusa_shortlist_e_busca(tmp_path: Path) -> None:
    """Catálogo instalado que sumiu do armazenamento é falha de ambiente, não do ato."""
    client = _client(tmp_path)
    prepared = _round_with_confirmed_item(client)
    with _database(client).sessions() as session:
        record = session.get(ValuationRoundRecord, prepared["round_id"])
        assert record is not None
        _store(client).objects.pop(record.catalog_object_key)

    shortlist = _suggestions(client, prepared["round_id"])
    search = client.get(
        f"/v1/valuation-rounds/{prepared['round_id']}/catalog/search?q=alambrado",
        headers=_headers(),
    )

    assert [shortlist.status_code, search.status_code] == [409, 409]
    for response in (shortlist, search):
        assert response.json()["detail"]["code"] == "CATALOG_REQUIRED"
    assert len(_revisions(client)) == 2


def test_o_recompute_avanca_a_versao_e_regrava_a_shortlist(tmp_path: Path) -> None:
    client = _client(tmp_path)
    prepared = _round_with_confirmed_item(client)
    first = _suggestions(client, prepared["round_id"])
    assert first.status_code == 200, first.text

    response = client.post(
        f"/v1/valuation-rounds/{prepared['round_id']}/code-suggestions/recompute",
        headers=_headers(key="recompute-001"),
        json={"base_version": prepared["version"]},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["computed"] is True
    assert body["version"] == prepared["version"] + 1
    assert body["suggestions_sha256"] == first.json()["suggestions_sha256"]
    assert _round_version(client, prepared["round_id"]) == prepared["version"] + 1
    revisions = _revisions(client)
    assert [revision.version for revision in revisions] == [1, 2, 3, 4]
    with _database(client).sessions() as session:
        audits = session.scalars(select(AuditRecord)).all()
        recomputed = [
            audit for audit in audits if audit.action == "VALUATION_CODE_SUGGESTIONS_RECOMPUTED"
        ]
        assert len(recomputed) == 1
        assert all(set(audit.metadata_json) == {"request_id"} for audit in audits)


def test_o_recompute_nunca_descarta_o_refino_pago(tmp_path: Path) -> None:
    """Recalcular por caminho determinístico apagaria o lineage da chamada paga."""
    client = _client(tmp_path)
    prepared = _round_with_confirmed_item(client)
    base = CodeSuggestionSet.model_validate(
        _suggestions(client, prepared["round_id"]).json()["suggestions"]
    )
    refined = base.model_copy(
        update={
            "suggester_version": base.suggester_version + LLM_RERANK_SUFFIX,
            "refinement": SuggestionRefinement(
                provider="anthropic",
                model_id="claude-sonnet-5",
                prompt_version="sco-refinement@1.0.1",
                input_digest="a" * 64,
            ),
        }
    )
    with _database(client).sessions() as session:
        head = session.scalars(
            select(ValuationRoundRevisionRecord).order_by(
                ValuationRoundRevisionRecord.version.desc()
            )
        ).first()
        assert head is not None
        head.code_suggestions_json = refined.model_dump(mode="json")
        session.commit()

    response = client.post(
        f"/v1/valuation-rounds/{prepared['round_id']}/code-suggestions/recompute",
        headers=_headers(key="recompute-refinada"),
        json={"base_version": prepared["version"]},
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "SUGGESTIONS_ALREADY_REFINED"
    assert detail["details"]["suggester_version"].endswith(LLM_RERANK_SUFFIX)
    assert len(_revisions(client)) == 3
    # A shortlist refinada continua sendo servida, com o lineage intacto.
    served = _suggestions(client, prepared["round_id"]).json()
    assert served["suggestions"]["refinement"]["model_id"] == "claude-sonnet-5"


def test_o_recompute_cura_a_shortlist_que_deixou_de_validar(tmp_path: Path) -> None:
    """Artefato ilegível não cai na guarda do refino: o recompute é a cura dele.

    Servi-lo, esse sim, é recusa — a tela nunca renderiza o que o domínio não valida.
    """
    client = _client(tmp_path)
    prepared = _round_with_confirmed_item(client)
    assert _suggestions(client, prepared["round_id"]).status_code == 200
    with _database(client).sessions() as session:
        head = session.scalars(
            select(ValuationRoundRevisionRecord).order_by(
                ValuationRoundRevisionRecord.version.desc()
            )
        ).first()
        assert head is not None
        head.code_suggestions_json = {"schema_version": "1.1.0"}
        session.commit()

    served = _suggestions(client, prepared["round_id"])
    recomputed = client.post(
        f"/v1/valuation-rounds/{prepared['round_id']}/code-suggestions/recompute",
        headers=_headers(key="recompute-corrompida"),
        json={"base_version": prepared["version"]},
    )

    assert served.status_code == 422
    assert served.json()["detail"]["code"] == "DOMAIN_VALIDATION_FAILED"
    assert recomputed.status_code == 200, recomputed.text
    assert recomputed.json()["computed"] is True
    assert _suggestions(client, prepared["round_id"]).json()["computed"] is False


def test_recompute_com_base_version_divergente_recusa_sem_gravar(tmp_path: Path) -> None:
    client = _client(tmp_path)
    prepared = _round_with_confirmed_item(client)

    response = client.post(
        f"/v1/valuation-rounds/{prepared['round_id']}/code-suggestions/recompute",
        headers=_headers(key="recompute-conflito"),
        json={"base_version": prepared["version"] + 7},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "REVISION_CONFLICT"
    assert len(_revisions(client)) == 2


def test_idempotencia_do_recompute_devolve_a_mesma_resposta(tmp_path: Path) -> None:
    client = _client(tmp_path)
    prepared = _round_with_confirmed_item(client)
    url = f"/v1/valuation-rounds/{prepared['round_id']}/code-suggestions/recompute"

    first = client.post(
        url, headers=_headers(key="recompute-x"), json={"base_version": prepared["version"]}
    )
    second = client.post(
        url, headers=_headers(key="recompute-x"), json={"base_version": prepared["version"]}
    )
    reused = client.post(
        url, headers=_headers(key="recompute-x"), json={"base_version": prepared["version"] + 1}
    )
    headerless = client.post(url, json={"base_version": prepared["version"] + 1})

    assert first.status_code == 200, first.text
    assert second.json() == first.json()
    assert reused.status_code == 409
    assert reused.json()["detail"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert headerless.status_code == 401
    assert len(_revisions(client)) == 3


def test_a_busca_lexica_e_o_padrao_e_declara_o_braco_semantico_ausente(tmp_path: Path) -> None:
    client = _client(tmp_path)
    prepared = _round_with_confirmed_item(client)

    response = client.get(
        f"/v1/valuation-rounds/{prepared['round_id']}/catalog/search?q=alambrado&limit=5",
        headers=_headers(),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["matching"] == "lexical"
    assert body["limit"] == 5
    assert [result["code"] for result in body["results"]] == [_CATALOG_CODE]
    assert body["semantic_notes"], "degradar em silêncio esconderia o braço que não rodou"
    assert body["version"] == prepared["version"]


def test_a_busca_sem_termo_utilizavel_recusa(tmp_path: Path) -> None:
    client = _client(tmp_path)
    prepared = _round_with_confirmed_item(client)

    response = client.get(
        f"/v1/valuation-rounds/{prepared['round_id']}/catalog/search?q=-", headers=_headers()
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "CATALOG_QUERY_EMPTY"


def test_o_braco_hibrido_exige_entitlement_e_ainda_assim_declara_a_falta_do_indice(
    tmp_path: Path,
) -> None:
    """Híbrido é braço pago: sem contrato, `403`; com contrato e sem índice, `503` honesto."""
    client = _client(tmp_path, real_providers_enabled=True)
    prepared = _round_with_confirmed_item(client)
    url = f"/v1/valuation-rounds/{prepared['round_id']}/catalog/search?q=alambrado&arm=hybrid"

    without = client.get(url, headers=_headers())
    _grant_entitlement(client)
    granted = client.get(url, headers=_headers())

    assert without.status_code == 403
    assert without.json()["detail"]["code"] == "AI_PROCESSING_NOT_AUTHORIZED"
    assert granted.status_code == 503
    detail = granted.json()["detail"]
    assert detail["code"] == "PROVIDER_UNAVAILABLE"
    assert detail["details"]["code"] == "SEMANTIC_INDEX_ABSENT"


def test_as_decisoes_de_codigo_listam_conjunto_ausente_e_pendencia(tmp_path: Path) -> None:
    """Conjunto inexistente não é erro: é o estado de quem acabou de chegar na etapa."""
    client = _client(tmp_path)
    prepared = _round_with_confirmed_item(client)

    response = client.get(
        f"/v1/valuation-rounds/{prepared['round_id']}/code-assignments", headers=_headers()
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["assignments"] is None
    assert body["assignments_sha256"] is None
    assert body["confirmed"] == 0
    assert body["rejected"] == 0
    assert [item["item_id"] for item in body["pending_items"]] == [_ITEM_CLEAR]
    # Quantidade sai como TEXTO também aqui: `float` perderia a escala escrita na legenda.
    assert body["pending_items"][0]["quantity"] == "10.00"


def test_as_decisoes_de_codigo_sem_takeoff_publicado_sao_etapa_fora_de_ordem(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)
    created = _create_round(client)

    listing = client.get(
        f"/v1/valuation-rounds/{created['round_id']}/code-assignments", headers=_headers()
    )
    decision = _decide_code(client, created["round_id"], base_version=1)

    assert [listing.status_code, decision.status_code] == [409, 409]
    for response in (listing, decision):
        detail = response.json()["detail"]
        assert detail["code"] == "ROUND_STAGE_NOT_READY"
        assert detail["details"] == {"stage": "takeoff"}


def test_a_confirmacao_de_codigo_grava_revisao_e_avanca_a_versao(tmp_path: Path) -> None:
    client = _client(tmp_path)
    prepared = _round_with_confirmed_item(client)

    response = _decide_code(client, prepared["round_id"], base_version=prepared["version"])

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["version"] == prepared["version"] + 1
    assert body["confirmed"] == 1
    assert body["rejected"] == 0
    assert body["closed"] == 0
    # Confirmar UM código não termina o item: sob a cardinalidade N:N o elemento pode
    # disparar mais serviços, e só o fechamento diz que não dispara. Enquanto isso ele
    # continua na lista do que falta fazer, que é a que a tela mostra.
    assert [item["item_id"] for item in body["pending_items"]] == [_ITEM_CLEAR]
    assignment = body["assignments"]["assignments"][0]
    assert assignment["item_id"] == _ITEM_CLEAR
    assert assignment["code"] == _CATALOG_CODE
    assert assignment["unit_compatible"] is True
    assert assignment["decision"]["reviewer_id"] == "orcamentista-sintetica"
    assert assignment["decision"]["reviewer_role"] == "orcamentista"
    revisions = _revisions(client)
    assert [revision.version for revision in revisions] == [1, 2, 3]
    assert revisions[-1].code_assignments_json is not None
    # Append-only: a revisão anterior continua sem decisão de código.
    assert revisions[-2].code_assignments_json is None
    with _database(client).sessions() as session:
        audits = session.scalars(select(AuditRecord)).all()
        decided = [audit for audit in audits if audit.action == "VALUATION_ITEM_CODE_DECIDED"]
        assert len(decided) == 1
        assert decided[0].resource_id == prepared["round_id"]
        assert all(set(audit.metadata_json) == {"request_id"} for audit in audits)


def test_a_rejeicao_de_codigo_exige_justificativa_e_recusa_codigo(tmp_path: Path) -> None:
    client = _client(tmp_path)
    prepared = _round_with_confirmed_item(client)

    sem_nota = _decide_code(
        client,
        prepared["round_id"],
        base_version=prepared["version"],
        key="rejeicao-sem-nota",
        action="reject",
        code=None,
    )
    com_codigo = _decide_code(
        client,
        prepared["round_id"],
        base_version=prepared["version"],
        key="rejeicao-com-codigo",
        action="reject",
        note="item medido fora do contrato",
    )
    aceita = _decide_code(
        client,
        prepared["round_id"],
        base_version=prepared["version"],
        key="rejeicao-ok",
        action="reject",
        code=None,
        note="item medido fora do contrato",
    )

    assert sem_nota.status_code == 422
    assert com_codigo.status_code == 422
    assert com_codigo.json()["detail"]["details"]["code"] == "ASSIGNMENT_CODE_ON_REJECT"
    assert aceita.status_code == 200, aceita.text
    body = aceita.json()
    assert body["rejected"] == 1
    assert body["assignments"]["assignments"][0]["code"] is None
    assert body["pending_items"] == []


def test_o_dominio_recusa_re_decisao_codigo_fora_do_catalogo_e_item_nao_confirmado(
    tmp_path: Path,
) -> None:
    """As quatro recusas são do domínio; a rota não republica nenhum desses códigos."""
    client = _client(tmp_path)
    prepared = _round_with_confirmed_item(client)
    first = _decide_code(client, prepared["round_id"], base_version=prepared["version"])
    assert first.status_code == 200, first.text
    ja_decidido = _decide_code(
        client, prepared["round_id"], base_version=prepared["version"] + 1, key="codigo-002"
    )
    desconhecido = _decide_code(
        client,
        prepared["round_id"],
        base_version=prepared["version"] + 1,
        key="codigo-003",
        item_id=_ITEM_AMBIGUOUS,
    )

    outra = _round_with_confirmed_item(client, key="rodada-fora-catalogo")
    fora_do_catalogo = _decide_code(
        client,
        outra["round_id"],
        base_version=outra["version"],
        key="codigo-004",
        code=_CODE_OUT_OF_CATALOG,
    )

    proposta = _round_with_takeoff(client)
    nao_confirmado = _decide_code(
        client, proposta["round_id"], base_version=proposta["version"], key="codigo-005"
    )

    assert ja_decidido.status_code == 422
    assert ja_decidido.json()["detail"]["details"]["code"] == "ASSIGNMENT_ITEM_ALREADY_DECIDED"
    assert desconhecido.status_code == 422
    assert desconhecido.json()["detail"]["details"]["code"] == "ASSIGNMENT_UNKNOWN_ITEM"
    assert fora_do_catalogo.status_code == 422
    assert fora_do_catalogo.json()["detail"]["details"]["code"] == "ASSIGNMENT_CODE_NOT_IN_CATALOG"
    assert nao_confirmado.status_code == 422
    assert nao_confirmado.json()["detail"]["details"]["code"] == "ASSIGNMENT_ITEM_NOT_CONFIRMED"


def test_unidade_divergente_sem_nota_recusa_a_confirmacao(tmp_path: Path) -> None:
    """O orçamentista pode medir em unidade diferente da tabela, mas nunca em silêncio."""
    client = _client(tmp_path)
    prepared = _round_with_confirmed_item(client, catalog_unit="un")

    sem_nota = _decide_code(client, prepared["round_id"], base_version=prepared["version"])
    com_nota = _decide_code(
        client,
        prepared["round_id"],
        base_version=prepared["version"],
        key="codigo-com-nota",
        note="medido em metro; tabela publica a unidade",
    )

    assert sem_nota.status_code == 422
    detail = sem_nota.json()["detail"]
    assert detail["code"] == "DOMAIN_VALIDATION_FAILED"
    assert detail["details"]["code"] == "ASSIGNMENT_UNIT_INCOMPATIBLE_WITHOUT_NOTE"
    assert com_nota.status_code == 200, com_nota.text
    assert com_nota.json()["assignments"]["assignments"][0]["unit_compatible"] is False


def test_a_decisao_de_codigo_recusa_carimbo_de_identidade_e_conflito_de_versao(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)
    prepared = _round_with_confirmed_item(client)

    for forbidden in ("reviewer_id", "reviewer_role", "decided_at", "decision_id"):
        response = _decide_code(
            client,
            prepared["round_id"],
            base_version=prepared["version"],
            key=f"codigo-{forbidden}",
            **{forbidden: "x"},
        )
        assert response.status_code == 422, forbidden
        assert "extra" in response.text.lower()

    conflito = _decide_code(
        client, prepared["round_id"], base_version=prepared["version"] + 7, key="codigo-conflito"
    )

    assert conflito.status_code == 409
    assert conflito.json()["detail"]["code"] == "REVISION_CONFLICT"
    assert len(_revisions(client)) == 2


def test_idempotencia_da_decisao_de_codigo_devolve_a_mesma_resposta(tmp_path: Path) -> None:
    client = _client(tmp_path)
    prepared = _round_with_confirmed_item(client)

    first = _decide_code(client, prepared["round_id"], base_version=prepared["version"])
    second = _decide_code(client, prepared["round_id"], base_version=prepared["version"])
    reused = _decide_code(
        client,
        prepared["round_id"],
        base_version=prepared["version"],
        action="reject",
        code=None,
        note="mudou de ideia",
    )
    headerless = client.post(
        f"/v1/valuation-rounds/{prepared['round_id']}/code-assignments/decisions",
        headers={"Authorization": f"Bearer test:{_TENANT}:orcamentista-sintetica:orcamentista"},
        json={
            "base_version": prepared["version"],
            "item_id": _ITEM_CLEAR,
            "action": "confirm",
            "code": _CATALOG_CODE,
        },
    )

    assert first.status_code == 200, first.text
    assert second.json() == first.json()
    assert reused.status_code == 409
    assert reused.json()["detail"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert headerless.status_code == 400
    assert headerless.json()["detail"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"
    assert len(_revisions(client)) == 3


def test_papel_e_tenant_valem_nas_rotas_de_codigo(tmp_path: Path) -> None:
    """Papel antes do lookup, rodada alheia indistinguível de inexistente, e `401` sem token."""
    client = _client(tmp_path)
    prepared = _round_with_confirmed_item(client)
    round_id = prepared["round_id"]
    unknown = str(new_uuid7())
    engineer = _headers(roles="engineer")
    intruder = _headers(_OTHER_TENANT, key="intruso-codigos")

    sem_papel = [
        client.get(f"/v1/valuation-rounds/{unknown}/code-suggestions", headers=engineer),
        client.post(
            f"/v1/valuation-rounds/{unknown}/code-suggestions/recompute",
            headers=engineer,
            json={"base_version": 1},
        ),
        client.get(f"/v1/valuation-rounds/{unknown}/catalog/search?q=alambrado", headers=engineer),
        client.get(f"/v1/valuation-rounds/{unknown}/code-assignments", headers=engineer),
        client.post(
            f"/v1/valuation-rounds/{unknown}/code-assignments/decisions",
            headers=_headers(roles="engineer", key="codigo-sem-papel"),
            json={
                "base_version": 1,
                "item_id": _ITEM_CLEAR,
                "action": "confirm",
                "code": _CATALOG_CODE,
            },
        ),
    ]
    outro_tenant = [
        client.get(f"/v1/valuation-rounds/{round_id}/code-suggestions", headers=intruder),
        client.post(
            f"/v1/valuation-rounds/{round_id}/code-suggestions/recompute",
            headers=intruder,
            json={"base_version": prepared["version"]},
        ),
        client.get(f"/v1/valuation-rounds/{round_id}/catalog/search?q=alambrado", headers=intruder),
        client.get(f"/v1/valuation-rounds/{round_id}/code-assignments", headers=intruder),
        _decide_code(
            client,
            round_id,
            base_version=prepared["version"],
            tenant=_OTHER_TENANT,
            key="codigo-intruso",
        ),
    ]
    sem_token = [
        client.get(f"/v1/valuation-rounds/{round_id}/code-suggestions"),
        client.post(
            f"/v1/valuation-rounds/{round_id}/code-suggestions/recompute",
            json={"base_version": prepared["version"]},
        ),
        client.get(f"/v1/valuation-rounds/{round_id}/catalog/search?q=alambrado"),
        client.get(f"/v1/valuation-rounds/{round_id}/code-assignments"),
        client.post(
            f"/v1/valuation-rounds/{round_id}/code-assignments/decisions",
            json={
                "base_version": prepared["version"],
                "item_id": _ITEM_CLEAR,
                "action": "confirm",
                "code": _CATALOG_CODE,
            },
        ),
    ]

    assert [response.status_code for response in sem_papel] == [403] * 5
    assert all(response.json()["detail"]["code"] == "FORBIDDEN" for response in sem_papel)
    assert [response.status_code for response in outro_tenant] == [404] * 5
    assert [response.status_code for response in sem_token] == [401] * 5
    # Nenhuma das recusas gravou artefato nem moveu a versão da rodada.
    assert len(_revisions(client)) == 2
    assert _round_version(client, round_id) == prepared["version"]


# --- boletim e dossiê do aditivo --------------------------------------------------------


def _build_calc(
    client: TestClient,
    round_id: str,
    *,
    base_version: int,
    tenant: str = _TENANT,
    key: str = "calc-001",
    **body: Any,
) -> Any:
    payload: dict[str, Any] = {"base_version": base_version}
    payload.update(body)
    return client.post(
        f"/v1/valuation-rounds/{round_id}/calc",
        headers=_headers(tenant, key=key),
        json=payload,
    )


def _build_dossier(
    client: TestClient,
    round_id: str,
    *,
    base_version: int,
    tenant: str = _TENANT,
    key: str = "dossie-001",
    **body: Any,
) -> Any:
    payload: dict[str, Any] = {"base_version": base_version}
    payload.update(body)
    return client.post(
        f"/v1/valuation-rounds/{round_id}/amendment-dossier",
        headers=_headers(tenant, key=key),
        json=payload,
    )


_REJECTION_NOTE = "item fora do SCO contratado"


def _round_with_decided_code(
    client: TestClient, *, action: str = "confirm", key: str = "rodada-fechamento"
) -> dict[str, Any]:
    """Rodada pronta para o fechamento: item confirmado no takeoff e código já decidido.

    As duas decisões passam pelas ROTAS, e não pelo banco: é a decisão de código que separa
    o item que vira linha do boletim do item que vira pedido de aditivo, e fabricá-la à mão
    esconderia justamente a precondição que boletim e dossiê exigem.
    """
    rejeicao: dict[str, Any] = {"code": None, "note": _REJECTION_NOTE}
    prepared = _round_with_confirmed_item(client, key=key)
    decided = _decide_code(
        client,
        prepared["round_id"],
        base_version=prepared["version"],
        key=f"{key}-codigo",
        action=action,
        **({} if action == "confirm" else rejeicao),
    )
    assert decided.status_code == 200, decided.text
    if action != "confirm":
        # A rejeição fecha o item sozinha: não há pacote a declarar completo.
        return {"round_id": prepared["round_id"], "version": decided.json()["version"]}

    # O boletim não é montado sobre pacote aberto. Fechar é ato humano próprio, e passa
    # pela ROTA pelo mesmo motivo que a decisão de código: fabricá-lo à mão esconderia a
    # precondição que `CALC_PACKAGE_NOT_CLOSED` existe para cobrar.
    closed = _close_package(
        client,
        prepared["round_id"],
        base_version=decided.json()["version"],
        key=f"{key}-fechamento",
    )
    assert closed.status_code == 200, closed.text
    return {"round_id": prepared["round_id"], "version": closed.json()["version"]}


def _stored_document(client: TestClient, round_id: str, column: str) -> dict[str, Any]:
    with _database(client).sessions() as session:
        revision = session.scalar(
            select(ValuationRoundRevisionRecord)
            .where(ValuationRoundRevisionRecord.round_id == round_id)
            .order_by(ValuationRoundRevisionRecord.version.desc())
        )
        assert revision is not None
        document = getattr(revision, column)
        assert document is not None
        return cast(dict[str, Any], document)


def _tamper_document(client: TestClient, round_id: str, column: str, document: Any) -> None:
    """Reescreve o artefato da cabeça da rodada como um banco adulterado o traria."""
    with _database(client).sessions() as session:
        revision = session.scalar(
            select(ValuationRoundRevisionRecord)
            .where(ValuationRoundRevisionRecord.round_id == round_id)
            .order_by(ValuationRoundRevisionRecord.version.desc())
        )
        assert revision is not None
        setattr(revision, column, document)
        session.commit()


def test_o_calc_constroi_o_boletim_com_a_identidade_da_rodada(tmp_path: Path) -> None:
    """Os rótulos da obra saem da RODADA, não do corpo, e o cálculo não aprova nada."""
    client = _client(tmp_path)
    prepared = _round_with_decided_code(client)

    response = _build_calc(client, prepared["round_id"], base_version=prepared["version"])

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["round_id"] == prepared["round_id"]
    assert body["version"] == prepared["version"] + 1
    # Dinheiro sai como texto: um número de JSON perderia o centavo que o TRUNC acabou de fixar.
    assert body["total_amount"] == "500.00"
    valuation = body["valuation"]
    assert valuation["period_number"] == 1
    assert valuation["reference_label"] == "MEDICAO 01/2026"
    assert valuation["approval"] is None
    bulletin = valuation["bulletins"][0]
    assert bulletin["worksite_key"] == "praca-sintetica-norte"
    assert bulletin["worksite_name"] == "PRACA SINTETICA NORTE"
    assert bulletin["address"] == "RUA SINTETICA, S/N"
    assert bulletin["contract_label"] == "CONTRATO SINTETICO 01/2026"
    assert bulletin["lines"] == [
        {
            "item_number": "1",
            "code": _CATALOG_CODE,
            "description": "ALAMBRADO GALVANIZADO",
            "unit": "m",
            "unit_price": "50.00",
            "quantity": "10.00",
            "total": "500.00",
        }
    ]
    # Sem plano de cálculo, cada item recebe o bloco de quantidade direta do próprio domínio.
    blocks = valuation["calc_sheets"][0]["blocks"]
    assert [block["recipe"] for block in blocks] == ["direct_quantity"]
    stored = _stored_document(client, prepared["round_id"], "valuation_json")
    assert stored["bulletins"][0]["total_amount"] == "500.00"
    assert body["valuation_sha256"] == document_digest(stored)


def test_o_corpo_do_calc_recusa_a_identidade_da_obra(tmp_path: Path) -> None:
    """`worksite_key`, `period_number`, `address` e `contract_label` são da rodada.

    Aceitá-los aqui deixaria o cliente reescrever a identidade da obra no meio da cadeia —
    a mesma medição sairia com outro nome de praça sem que nada na rodada tivesse mudado.
    """
    client = _client(tmp_path)
    prepared = _round_with_decided_code(client)

    recusas: dict[str, Any] = {
        "worksite_key": "outra-praca",
        "worksite_name": "OUTRA PRACA",
        "period_number": 9,
        "reference_label": "MEDICAO 09/2026",
        "address": "OUTRA RUA, 100",
        "contract_label": "OUTRO CONTRATO",
    }
    for campo, valor in recusas.items():
        response = _build_calc(
            client,
            prepared["round_id"],
            base_version=prepared["version"],
            key=f"calc-{campo}",
            **{campo: valor},
        )
        assert response.status_code == 422, campo
        assert "extra" in response.text.lower()

    # Uma revisão a mais que antes: o fechamento do pacote é ato próprio e grava a sua.
    assert len(_revisions(client)) == 4
    assert _round_version(client, prepared["round_id"]) == prepared["version"]


def _single_service_matrix() -> dict[str, Any]:
    """Matriz com UM serviço (o código confirmado da fixture) alimentado por UM elemento."""
    matrix = CalcMatrix(
        services=[
            ServiceContributions(
                code=_CATALOG_CODE,
                contributions=[
                    CalcContribution(
                        source_item_id=_ITEM_CLEAR,
                        label="ALAMBRADO GALVANIZADO",
                        basis=ContributionBasis.FULL,
                        recipe=CalcRecipe.DECLARED_PRODUCT,
                        operands=[
                            CalcOperand(name="COMPRIMENTO", value=Decimal("10.00"), unit="m")
                        ],
                    )
                ],
            )
        ]
    )
    return matrix.model_dump(mode="json")


def test_o_calc_aceita_a_matriz_e_a_persiste_na_revisao(tmp_path: Path) -> None:
    """A matriz posta no corpo funde por código, monta o boletim e fica gravada auditável."""
    client = _client(tmp_path)
    prepared = _round_with_decided_code(client)

    response = _build_calc(
        client,
        prepared["round_id"],
        base_version=prepared["version"],
        calc_matrix=_single_service_matrix(),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    lines = body["valuation"]["bulletins"][0]["lines"]
    assert [line["code"] for line in lines] == [_CATALOG_CODE]
    # A matriz validada é gravada na revisão nova, re-legível byte-a-byte com o que foi posto.
    stored = _stored_document(client, prepared["round_id"], "calc_matrix_json")
    assert stored == _single_service_matrix()


def test_o_calc_recusa_matriz_malformada_como_dominio(tmp_path: Path) -> None:
    """Matriz inválida volta como `422 DOMAIN_VALIDATION_FAILED`, não como erro de esquema."""
    client = _client(tmp_path)
    prepared = _round_with_decided_code(client)

    response = _build_calc(
        client,
        prepared["round_id"],
        base_version=prepared["version"],
        calc_matrix={"services": []},
    )

    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "DOMAIN_VALIDATION_FAILED"


def test_o_calc_com_codigo_pendente_recusa_com_o_vocabulario_do_dominio(tmp_path: Path) -> None:
    """Item confirmado no takeoff sem decisão de código é invariante, não etapa fora de ordem."""
    client = _client(tmp_path)
    created = _create_round(client, key="rodada-pendente")
    packet = _takeoff_packet([_takeoff_item(), _takeoff_item(item_id=_ITEM_SECOND)])
    published = _publish_takeoff(client, created["round_id"], packet)
    primeiro = _decide(
        client,
        created["round_id"],
        base_version=published["version"],
        quantity="10.00",
        key="pendente-takeoff-1",
    )
    segundo = _decide(
        client,
        created["round_id"],
        base_version=primeiro.json()["version"],
        item_id=_ITEM_SECOND,
        quantity="10.00",
        key="pendente-takeoff-2",
    )
    decidido = _decide_code(
        client,
        created["round_id"],
        base_version=segundo.json()["version"],
        key="pendente-codigo",
    )

    response = _build_calc(
        client, created["round_id"], base_version=decidido.json()["version"], key="calc-pendente"
    )

    assert response.status_code == 422, response.text
    details = response.json()["detail"]["details"]
    assert details["code"] == "CALC_ASSIGNMENT_MISSING"
    assert details["item_ids"] == [_ITEM_SECOND]
    assert _round_version(client, created["round_id"]) == decidido.json()["version"]


def test_o_calc_sem_conjunto_de_codigos_e_etapa_fora_de_ordem(tmp_path: Path) -> None:
    """Conjunto ainda inexistente é ORDEM da cadeia (409), não invariante violada (422)."""
    client = _client(tmp_path)
    prepared = _round_with_confirmed_item(client, key="rodada-sem-codigo")

    response = _build_calc(client, prepared["round_id"], base_version=prepared["version"])

    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "ROUND_STAGE_NOT_READY"
    assert detail["details"] == {"stage": "code_assignments"}


def test_o_calc_recusa_catalogo_cuja_origem_nao_e_o_sco(tmp_path: Path) -> None:
    """A fronteira licitada fecha no boletim (ADR-0027): preço nunca vem de outra tabela.

    Item confirmado que não tem código no SCO/contrato vira dossiê de aditivo; precificá-lo
    pela EMOP violaria a regra do erário fixada pela orçamentista.
    """
    client = _client(tmp_path)
    created = _create_round(client, key="rodada-emop", catalog_origin=PriceOrigin.EMOP)
    published = _publish_takeoff(client, created["round_id"], _takeoff_packet())
    decidido_takeoff = _decide(
        client,
        created["round_id"],
        base_version=published["version"],
        quantity="10.00",
        key="emop-takeoff",
    )
    decidido_codigo = _decide_code(
        client,
        created["round_id"],
        base_version=decidido_takeoff.json()["version"],
        key="emop-codigo",
    )
    assert decidido_codigo.status_code == 200, decidido_codigo.text

    response = _build_calc(
        client, created["round_id"], base_version=decidido_codigo.json()["version"], key="calc-emop"
    )

    assert response.status_code == 422, response.text
    details = response.json()["detail"]["details"]
    assert details["code"] == "BULLETIN_PRICE_ORIGIN_FORBIDDEN"
    assert details["origin"] == "emop"
    # Nada foi gravado: a recusa acontece antes de qualquer boletim existir.
    with _database(client).sessions() as session:
        record = session.get(ValuationRoundRecord, created["round_id"])
        assert record is not None
        assert record.version == decidido_codigo.json()["version"]
    assert all(revision.valuation_json is None for revision in _revisions(client))


def test_o_calc_recusa_base_version_divergente_e_exige_idempotency_key(tmp_path: Path) -> None:
    """A guarda de concorrência é MUDANÇA pretendida: `/calc/build` local não tinha nenhuma."""
    client = _client(tmp_path)
    prepared = _round_with_decided_code(client)

    conflito = _build_calc(
        client, prepared["round_id"], base_version=prepared["version"] + 7, key="calc-conflito"
    )
    headerless = client.post(
        f"/v1/valuation-rounds/{prepared['round_id']}/calc",
        headers={"Authorization": f"Bearer test:{_TENANT}:orcamentista-sintetica:orcamentista"},
        json={"base_version": prepared["version"]},
    )

    assert conflito.status_code == 409
    assert conflito.json()["detail"]["code"] == "REVISION_CONFLICT"
    assert headerless.status_code == 400
    assert headerless.json()["detail"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"
    # Uma revisão a mais que antes: o fechamento do pacote é ato próprio e grava a sua.
    assert len(_revisions(client)) == 4
    assert _round_version(client, prepared["round_id"]) == prepared["version"]


def test_idempotencia_do_calc_devolve_a_mesma_resposta(tmp_path: Path) -> None:
    client = _client(tmp_path)
    prepared = _round_with_decided_code(client)

    first = _build_calc(client, prepared["round_id"], base_version=prepared["version"])
    second = _build_calc(client, prepared["round_id"], base_version=prepared["version"])
    reused = _build_calc(client, prepared["round_id"], base_version=prepared["version"] + 1)

    assert first.status_code == 200, first.text
    assert second.json() == first.json()
    assert reused.status_code == 409
    assert reused.json()["detail"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    # Uma revisão a mais que antes: o fechamento do pacote é ato próprio e grava a sua.
    assert len(_revisions(client)) == 5


def test_o_boletim_e_recomputado_na_leitura_e_nunca_servido_como_gravado(tmp_path: Path) -> None:
    """Total adulterado no banco não vira `200`: quem recomputa é o validador do modelo.

    Servir o total como ele foi gravado faria a tela renderizar uma medição que ninguém
    conferiu — e é justamente o número que vai virar dinheiro público.
    """
    client = _client(tmp_path)
    prepared = _round_with_decided_code(client)
    construido = _build_calc(client, prepared["round_id"], base_version=prepared["version"])
    assert construido.status_code == 200, construido.text

    antes = client.get(f"/v1/valuation-rounds/{prepared['round_id']}/bulletin", headers=_headers())
    document = _stored_document(client, prepared["round_id"], "valuation_json")
    document["bulletins"][0]["total_amount"] = "999.00"
    _tamper_document(client, prepared["round_id"], "valuation_json", document)
    depois = client.get(f"/v1/valuation-rounds/{prepared['round_id']}/bulletin", headers=_headers())

    assert antes.status_code == 200, antes.text
    assert antes.json()["total_amount"] == "500.00"
    assert depois.status_code == 422, depois.text
    details = depois.json()["detail"]["details"]
    assert details["code"] == "BULLETIN_TOTAL_MISMATCH"
    # A recomputação fica visível na recusa: o esperado é a soma refeita das linhas, e o
    # declarado é o que o banco trazia. Nenhum boletim é servido junto.
    assert (details["expected"], details["declared"]) == ("500.00", "999.00")
    assert "valuation" not in depois.json()


def test_o_boletim_ainda_nao_construido_e_etapa_fora_de_ordem(tmp_path: Path) -> None:
    client = _client(tmp_path)
    prepared = _round_with_decided_code(client)

    response = client.get(
        f"/v1/valuation-rounds/{prepared['round_id']}/bulletin", headers=_headers()
    )

    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "ROUND_STAGE_NOT_READY"
    assert detail["details"] == {"stage": "bulletin"}


def test_o_dossie_lista_o_codigo_rejeitado_com_justificativa_e_sem_preco(tmp_path: Path) -> None:
    """O dossiê não tem campo de preço por construção (ADR-0027) e não cria RE-RA nenhum."""
    client = _client(tmp_path)
    prepared = _round_with_decided_code(client, action="reject")

    response = _build_dossier(client, prepared["round_id"], base_version=prepared["version"])

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["version"] == prepared["version"] + 1
    assert body["item_count"] == 1
    item = body["dossier"]["items"][0]
    assert item["item_id"] == _ITEM_CLEAR
    assert item["justification"] == "item fora do SCO contratado"
    assert item["decision"]["action"] == "reject"
    assert item["decision"]["reviewer_role"] == "orcamentista"
    assert "price" not in json.dumps(body["dossier"])
    stored = _stored_document(client, prepared["round_id"], "amendment_dossier_json")
    assert body["dossier_sha256"] == document_digest(stored)


def test_o_dossie_sem_rejeicao_de_codigo_sai_vazio_e_nao_e_erro(tmp_path: Path) -> None:
    """Rodada em que todo código foi confirmado não tem aditivo a pedir — e isso é normal."""
    client = _client(tmp_path)
    prepared = _round_with_decided_code(client)

    response = _build_dossier(client, prepared["round_id"], base_version=prepared["version"])

    assert response.status_code == 200, response.text
    assert response.json()["item_count"] == 0


def test_o_dossie_com_decisao_de_codigo_pendente_recusa(tmp_path: Path) -> None:
    """O dossiê é artefato de FECHAMENTO: ele nunca publica foto parcial da rodada."""
    client = _client(tmp_path)
    created = _create_round(client, key="rodada-dossie-pendente")
    packet = _takeoff_packet([_takeoff_item(), _takeoff_item(item_id=_ITEM_SECOND)])
    published = _publish_takeoff(client, created["round_id"], packet)
    primeiro = _decide(
        client,
        created["round_id"],
        base_version=published["version"],
        quantity="10.00",
        key="dossie-takeoff-1",
    )
    segundo = _decide(
        client,
        created["round_id"],
        base_version=primeiro.json()["version"],
        item_id=_ITEM_SECOND,
        quantity="10.00",
        key="dossie-takeoff-2",
    )
    decidido = _decide_code(
        client,
        created["round_id"],
        base_version=segundo.json()["version"],
        action="reject",
        code=None,
        note="item fora do SCO contratado",
        key="dossie-codigo",
    )

    response = _build_dossier(
        client, created["round_id"], base_version=decidido.json()["version"], key="dossie-pendente"
    )

    assert response.status_code == 422, response.text
    details = response.json()["detail"]["details"]
    assert details["code"] == "AMENDMENT_DOSSIER_ASSIGNMENTS_INCOMPLETE"
    assert details["item_ids"] == [_ITEM_SECOND]


def test_o_dossie_sem_conjunto_de_codigos_e_etapa_fora_de_ordem(tmp_path: Path) -> None:
    client = _client(tmp_path)
    prepared = _round_with_confirmed_item(client, key="rodada-dossie-sem-codigo")

    response = _build_dossier(client, prepared["round_id"], base_version=prepared["version"])

    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "ROUND_STAGE_NOT_READY"
    assert detail["details"] == {"stage": "code_assignments"}


def test_o_dossie_recusa_base_version_divergente_e_e_idempotente(tmp_path: Path) -> None:
    client = _client(tmp_path)
    prepared = _round_with_decided_code(client, action="reject")

    conflito = _build_dossier(
        client, prepared["round_id"], base_version=prepared["version"] + 7, key="dossie-conflito"
    )
    first = _build_dossier(client, prepared["round_id"], base_version=prepared["version"])
    second = _build_dossier(client, prepared["round_id"], base_version=prepared["version"])

    assert conflito.status_code == 409
    assert conflito.json()["detail"]["code"] == "REVISION_CONFLICT"
    assert first.status_code == 200, first.text
    assert second.json() == first.json()
    # Três revisões da cadeia (takeoff, decisão, código) mais a do dossiê: a segunda
    # chamada com a mesma chave devolveu a resposta guardada e não gravou nada.
    assert len(_revisions(client)) == 4


def test_o_dossie_e_revalidado_na_leitura(tmp_path: Path) -> None:
    """Espelho do boletim: artefato que não passa na revalidação é `422`, nunca `200`."""
    client = _client(tmp_path)
    prepared = _round_with_decided_code(client, action="reject")
    construido = _build_dossier(client, prepared["round_id"], base_version=prepared["version"])
    assert construido.status_code == 200, construido.text

    antes = client.get(
        f"/v1/valuation-rounds/{prepared['round_id']}/amendment-dossier", headers=_headers()
    )
    document = _stored_document(client, prepared["round_id"], "amendment_dossier_json")
    document["items"][0]["justification"] = "justificativa reescrita fora da decisão"
    _tamper_document(client, prepared["round_id"], "amendment_dossier_json", document)
    depois = client.get(
        f"/v1/valuation-rounds/{prepared['round_id']}/amendment-dossier", headers=_headers()
    )

    assert antes.status_code == 200, antes.text
    assert antes.json()["item_count"] == 1
    assert depois.status_code == 422, depois.text
    assert depois.json()["detail"]["details"]["code"] == "AMENDMENT_DOSSIER_ITEM_STATE_INVALID"


def test_o_dossie_ainda_nao_construido_e_etapa_fora_de_ordem(tmp_path: Path) -> None:
    client = _client(tmp_path)
    prepared = _round_with_decided_code(client, action="reject")

    response = client.get(
        f"/v1/valuation-rounds/{prepared['round_id']}/amendment-dossier", headers=_headers()
    )

    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "ROUND_STAGE_NOT_READY"
    assert detail["details"] == {"stage": "amendment_dossier"}


def test_papel_e_tenant_valem_nas_rotas_de_fechamento(tmp_path: Path) -> None:
    """Papel antes do lookup, rodada alheia indistinguível de inexistente, e `401` sem token."""
    client = _client(tmp_path)
    prepared = _round_with_decided_code(client)
    round_id = prepared["round_id"]
    unknown = str(new_uuid7())
    engineer = _headers(roles="engineer")
    intruder = _headers(_OTHER_TENANT, key="intruso-fechamento")

    sem_papel = [
        client.post(
            f"/v1/valuation-rounds/{unknown}/calc",
            headers=_headers(roles="engineer", key="calc-sem-papel"),
            json={"base_version": 1},
        ),
        client.get(f"/v1/valuation-rounds/{unknown}/bulletin", headers=engineer),
        client.post(
            f"/v1/valuation-rounds/{unknown}/amendment-dossier",
            headers=_headers(roles="engineer", key="dossie-sem-papel"),
            json={"base_version": 1},
        ),
        client.get(f"/v1/valuation-rounds/{unknown}/amendment-dossier", headers=engineer),
    ]
    outro_tenant = [
        _build_calc(
            client,
            round_id,
            base_version=prepared["version"],
            tenant=_OTHER_TENANT,
            key="calc-intruso",
        ),
        client.get(f"/v1/valuation-rounds/{round_id}/bulletin", headers=intruder),
        _build_dossier(
            client,
            round_id,
            base_version=prepared["version"],
            tenant=_OTHER_TENANT,
            key="dossie-intruso",
        ),
        client.get(f"/v1/valuation-rounds/{round_id}/amendment-dossier", headers=intruder),
    ]
    sem_token = [
        client.post(
            f"/v1/valuation-rounds/{round_id}/calc", json={"base_version": prepared["version"]}
        ),
        client.get(f"/v1/valuation-rounds/{round_id}/bulletin"),
        client.post(
            f"/v1/valuation-rounds/{round_id}/amendment-dossier",
            json={"base_version": prepared["version"]},
        ),
        client.get(f"/v1/valuation-rounds/{round_id}/amendment-dossier"),
    ]

    assert [response.status_code for response in sem_papel] == [403] * 4
    assert all(response.json()["detail"]["code"] == "FORBIDDEN" for response in sem_papel)
    assert [response.status_code for response in outro_tenant] == [404] * 4
    assert [response.status_code for response in sem_token] == [401] * 4
    # Uma revisão a mais que antes: o fechamento do pacote é ato próprio e grava a sua.
    assert len(_revisions(client)) == 4
    assert _round_version(client, round_id) == prepared["version"]


# --- corrida na cadeia de revisões ------------------------------------------------------


def _rival_revision(client: TestClient, round_id: str) -> Any:
    """Faz uma segunda gravação tomar a posição que esta requisição ia ocupar.

    O `append_revision` real já rodou e a sessão da rota ainda não commitou: inserir aqui,
    por outra sessão, é o que reproduz a corrida sem depender de threads — a posição da
    cadeia é decidida por `uq_valuation_round_version`, e não pela ordem em que os dois
    caminhos começaram.
    """

    def append_e_perde_a_corrida(*args: Any, **kwargs: Any) -> Any:
        revision = append_revision(*args, **kwargs)
        with _database(client).sessions.begin() as rival:
            rival.add(
                ValuationRoundRevisionRecord(
                    id=str(new_uuid7()),
                    tenant_id=_TENANT,
                    round_id=round_id,
                    version=revision.version,
                    created_by="requisicao-concorrente",
                    **{
                        column: value
                        for column, value in kwargs["changes"].items()
                        if column != "artifact_refs_json"
                    },
                )
            )
        return revision

    return append_e_perde_a_corrida


def test_leitura_que_perde_a_corrida_da_shortlist_serve_a_do_vencedor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A tela faz polling, então duas leituras simultâneas são o caso normal, não o raro.

    As duas calculam a MESMA shortlist — o cálculo é determinístico — e disputam a mesma
    posição da cadeia. Quem perde serve o artefato de quem chegou antes; devolver `500`
    transformaria concorrência de tela em falha de servidor.
    """
    client = _client(tmp_path)
    prepared = _round_with_confirmed_item(client)
    round_id = prepared["round_id"]
    monkeypatch.setattr("croquito_api.main.append_revision", _rival_revision(client, round_id))

    response = _suggestions(client, round_id)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["computed"] is False
    # A shortlist servida é a do vencedor, e é uma shortlist de verdade: o item confirmado
    # continua tendo candidatos, e não um envelope vazio que a corrida deixou pelo caminho.
    assert body["suggestions"]["suggestions"]
    # A rodada não mudou de versão por causa de uma leitura, nem com corrida no meio.
    assert _round_version(client, round_id) == prepared["version"]


def test_decisao_de_codigo_que_perde_a_corrida_e_conflito_e_nao_erro_de_servidor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`base_version` é conferido em memória: duas decisões que leram a mesma versão passam
    as duas pela guarda e vão disputar a mesma posição da cadeia. Quem perde recebeu uma
    rodada que mudou depois da leitura dele, que é o que `REVISION_CONFLICT` diz."""
    client = _client(tmp_path)
    prepared = _round_with_confirmed_item(client)
    round_id = prepared["round_id"]
    monkeypatch.setattr("croquito_api.main.append_revision", _rival_revision(client, round_id))

    response = _decide_code(client, round_id, base_version=prepared["version"])

    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "REVISION_CONFLICT"


def test_calc_que_perde_a_corrida_e_conflito_e_nao_erro_de_servidor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O boletim entra na cadeia pela mesma porta das decisões, e perde a corrida do mesmo jeito.

    No servidor de medição `/calc/build` não tinha guarda nenhuma e sempre sobrescrevia o
    artefato; em `/v1` a construção é ato humano da cadeia append-only, e duas construções
    simultâneas não podem ocupar a mesma posição.
    """
    client = _client(tmp_path)
    prepared = _round_with_decided_code(client)
    round_id = prepared["round_id"]
    monkeypatch.setattr("croquito_api.main.append_revision", _rival_revision(client, round_id))

    response = _build_calc(client, round_id, base_version=prepared["version"])

    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "REVISION_CONFLICT"


# --- F-028: aprovação nominal e exportação auditada do boletim ----------------------------


def _approve(
    client: TestClient,
    round_id: str,
    *,
    base_version: int,
    tenant: str = _TENANT,
    roles: str = "orcamentista",
    key: str = "aprovar-001",
) -> Any:
    return client.post(
        f"/v1/valuation-rounds/{round_id}/approve",
        headers=_headers(tenant, roles, key=key),
        json={"base_version": base_version},
    )


def _export_bulletin(
    client: TestClient,
    round_id: str,
    *,
    base_version: int,
    tenant: str = _TENANT,
    roles: str = "orcamentista",
    key: str = "exportar-001",
) -> Any:
    return client.post(
        f"/v1/valuation-rounds/{round_id}/bulletin/export",
        headers=_headers(tenant, roles, key=key),
        json={"base_version": base_version},
    )


def _get_bulletin(client: TestClient, round_id: str, *, tenant: str = _TENANT) -> Any:
    return client.get(
        f"/v1/valuation-rounds/{round_id}/bulletin", headers=_headers(tenant, key="leitura")
    )


def _round_with_bulletin(client: TestClient, *, key: str = "rodada-boletim") -> dict[str, Any]:
    """Rodada até o boletim construído — a precondição de aprovar e de exportar."""
    prepared = _round_with_decided_code(client, key=key)
    built = _build_calc(
        client, prepared["round_id"], base_version=prepared["version"], key=f"{key}-calc"
    )
    assert built.status_code == 200, built.text
    return {"round_id": prepared["round_id"], "version": built.json()["version"]}


def _divergent_audit(*_args: Any, **_kwargs: Any) -> AuditReport:
    """Laudo reprovado com valor de cliente dentro — o teste confere que ele NÃO vaza."""
    return AuditReport(
        status="divergent",
        workbook_sha256="d" * 64,
        worksites=[
            AuditedWorksite(
                worksite_key="praca-do-toca",
                bulletin_sheet="BM",
                memory_sheet="MEMORIA",
                total_amount=Decimal("1125.00"),
            )
        ],
        checked_cells=1,
        formula_cells=0,
        total_amount=Decimal("1125.00"),
        findings=[
            AuditFinding(
                code="CELL_VALUE_MISMATCH",
                sheet="BM",
                ref="H8",
                expected="1125.00",
                found="9999.99",
                detail="line_total",
            )
        ],
    )


def test_a_aprovacao_carimba_a_identidade_do_token_e_amarra_o_digest(tmp_path: Path) -> None:
    """Quem aprovou é o subject do JWT, e o ato fica preso ao conteúdo que ele aprovou.

    O digest gravado tem de conferir com o `content_digest()` da medição DEPOIS do ato:
    `approval` está fora do cálculo, então aprovar não muda o que foi aprovado.
    """
    client = _client(tmp_path)
    prepared = _round_with_bulletin(client)
    round_id = prepared["round_id"]

    response = _approve(client, round_id, base_version=prepared["version"])

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["version"] == prepared["version"] + 1
    stored = Valuation.model_validate(_stored_document(client, round_id, "valuation_json"))
    assert stored.approval is not None
    assert stored.approval.decision.reviewer_id == "orcamentista-sintetica"
    assert stored.approval.decision.action == "confirm"
    assert stored.approval.valuation_digest == stored.content_digest()
    approval = body["approval"]
    assert approval["approved"] is True
    assert approval["approved_by"] == "orcamentista-sintetica"
    assert approval["stale"] is False
    assert approval["approved_digest"] == approval["current_digest"]


def test_o_corpo_da_aprovacao_recusa_qualquer_carimbo_de_identidade(tmp_path: Path) -> None:
    """Nome de aprovador não viaja no corpo: quem recusa é o `extra="forbid"` do modelo."""
    client = _client(tmp_path)
    prepared = _round_with_bulletin(client)

    response = client.post(
        f"/v1/valuation-rounds/{prepared['round_id']}/approve",
        headers=_headers(key="aprovar-carimbo"),
        json={"base_version": prepared["version"], "reviewer_id": "fulano-da-silva"},
    )

    assert response.status_code == 422, response.text
    assert not _stored_document(client, prepared["round_id"], "valuation_json").get("approval")


def test_a_aprovacao_sem_boletim_construido_e_etapa_fora_de_ordem(tmp_path: Path) -> None:
    """Sem boletim não há o que aprovar, e isso é ORDEM da cadeia, não invariante violada."""
    client = _client(tmp_path)
    prepared = _round_with_decided_code(client)

    response = _approve(client, prepared["round_id"], base_version=prepared["version"])

    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "ROUND_STAGE_NOT_READY"


def test_a_exportacao_sem_aprovacao_e_recusada_pelo_portao_do_dominio(tmp_path: Path) -> None:
    """`VALUATION_NOT_APPROVED` vem de `ensure_exportable`, e nada é publicado."""
    client = _client(tmp_path)
    prepared = _round_with_bulletin(client)
    objects_before = set(_store(client).objects)

    response = _export_bulletin(client, prepared["round_id"], base_version=prepared["version"])

    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "DOMAIN_VALIDATION_FAILED"
    assert detail["details"]["code"] == "VALUATION_EXPORT_BLOCKED"
    assert "VALUATION_NOT_APPROVED" in detail["details"]["errors"]
    assert set(_store(client).objects) == objects_before


def test_o_consolidado_derivado_nao_dispara_codigo_de_contrato_nem_afrouxa_a_aprovacao(
    tmp_path: Path,
) -> None:
    """O par que caracteriza a decisão do consolidado derivado do portão (F-028).

    A rodada de `/v1` não importa consolidado contratual, então `bulletin_export_contract`
    declara só o que a medição sabe. As duas metades precisam valer ao mesmo tempo:

    - no caminho feliz, NENHUM código de contrato ou saldo dispara — o consolidado derivado
      confere com a medição por construção, e um portão que reprovasse aqui estaria
      inventando um saldo que a rodada não tem;
    - a APROVAÇÃO continua integralmente obrigatória — é exatamente o que sobra do portão, e
      é o que a F-028 transforma em recusa de rota.

    Se algum dia a primeira metade passar a reprovar, é porque a rodada ganhou consolidado de
    verdade — e aí este teste é o lugar certo para a conversa.
    """
    client = _client(tmp_path)
    prepared = _round_with_bulletin(client)
    round_id = prepared["round_id"]
    valuation = Valuation.model_validate(_stored_document(client, round_id, "valuation_json"))
    contract = bulletin_export_contract(valuation)

    sem_aprovacao = valuation.export_errors(contract)
    com_aprovacao = approve_valuation(
        valuation, reviewer_id="orcamentista-sintetica", decided_at=datetime.now(UTC)
    ).export_errors(contract)

    # A aprovação é a ÚNICA violação aberta antes do ato: nenhum código de contrato/saldo.
    assert sem_aprovacao == ["VALUATION_NOT_APPROVED"]
    # E, com ela, o portão fica inteiramente limpo — sem afrouxar nada.
    assert com_aprovacao == []


def test_a_aprovacao_caduca_quando_o_conteudo_muda_sob_ela(tmp_path: Path) -> None:
    """Aprovação amarrada por digest não sobrevive à mudança do que foi aprovado.

    O conteúdo é alterado como um banco adulterado o traria — mantendo a `approval` e
    mexendo num campo que o `content_digest()` cobre. Cobertura EXTRA, por baixo da jornada:
    o caminho real de caducidade é o recálculo, coberto por
    `test_o_recalculo_faz_a_aprovacao_caducar_e_a_exportacao_recusa`. Este aqui prova que o
    portão não depende de como a divergência apareceu — inclusive quando ela não veio de
    nenhuma rota.
    """
    client = _client(tmp_path)
    prepared = _round_with_bulletin(client)
    round_id = prepared["round_id"]
    approved = _approve(client, round_id, base_version=prepared["version"])
    assert approved.status_code == 200, approved.text
    document = _stored_document(client, round_id, "valuation_json")
    _tamper_document(
        client, round_id, "valuation_json", {**document, "reference_label": "AGOSTO/2026"}
    )

    leitura = _get_bulletin(client, round_id)
    exportacao = _export_bulletin(
        client, round_id, base_version=approved.json()["version"], key="exportar-caduca"
    )

    assert leitura.status_code == 200, leitura.text
    aprovacao = leitura.json()["approval"]
    assert aprovacao["stale"] is True
    assert aprovacao["approved_digest"] != aprovacao["current_digest"]
    assert exportacao.status_code == 422, exportacao.text
    assert "APPROVAL_CONTENT_MISMATCH" in exportacao.json()["detail"]["details"]["errors"]


def test_o_recalculo_faz_a_aprovacao_caducar_e_a_exportacao_recusa(tmp_path: Path) -> None:
    """Recalcular depois de aprovar produz a APROVAÇÃO CADUCA do desenho aprovado (F-028).

    A aprovação anterior é levada adiante pela rota do `/calc`, ainda amarrada ao digest do
    conteúdo que ela cobria. O resultado é o estado que o mock desenha por extenso: houve uma
    aprovação, ela tem dono e data, e ela NÃO cobre o que está na tela — os dois digests
    aparecem lado a lado. Preservar não é aprovar: o portão recusa a exportação com
    `APPROVAL_CONTENT_MISMATCH`.
    """
    client = _client(tmp_path)
    prepared = _round_with_bulletin(client)
    round_id = prepared["round_id"]
    approved = _approve(client, round_id, base_version=prepared["version"])
    assert approved.status_code == 200, approved.text
    digest_aprovado = approved.json()["approval"]["approved_digest"]

    recalculado = _build_calc(
        client, round_id, base_version=approved.json()["version"], key="calc-recalculo"
    )
    assert recalculado.status_code == 200, recalculado.text
    leitura = _get_bulletin(client, round_id)
    exportacao = _export_bulletin(
        client, round_id, base_version=recalculado.json()["version"], key="exportar-recalculo"
    )

    aprovacao = leitura.json()["approval"]
    assert aprovacao["stale"] is True
    # Quem aprovou e quando continuam visíveis: é isso que distingue caduca de nunca aprovada.
    assert aprovacao["approved_by"] == "orcamentista-sintetica"
    assert aprovacao["approved_at"] is not None
    # O digest aprovado é o ANTIGO, e o atual mudou — os dois lados que a tela mostra.
    assert aprovacao["approved_digest"] == digest_aprovado
    assert aprovacao["current_digest"] != digest_aprovado
    assert exportacao.status_code == 422, exportacao.text
    assert "APPROVAL_CONTENT_MISMATCH" in exportacao.json()["detail"]["details"]["errors"]


def test_depois_de_recalcular_exportar_exige_um_ato_novo_de_aprovacao(tmp_path: Path) -> None:
    """A invariante que vale em qualquer desenho: recalculou, só exporta quem aprovar de novo.

    Independe de o recálculo preservar ou descartar a aprovação anterior — o que este teste
    protege é que nenhuma assinatura velha autoriza conteúdo novo, e que a saída existe:
    aprovar de novo destrava a exportação.
    """
    client = _client(tmp_path)
    prepared = _round_with_bulletin(client)
    round_id = prepared["round_id"]
    approved = _approve(client, round_id, base_version=prepared["version"])
    recalculado = _build_calc(
        client, round_id, base_version=approved.json()["version"], key="calc-reaprovacao"
    )
    assert recalculado.status_code == 200, recalculado.text

    recusada = _export_bulletin(
        client, round_id, base_version=recalculado.json()["version"], key="exportar-recusada"
    )
    reaprovada = _approve(
        client, round_id, base_version=recalculado.json()["version"], key="aprovar-de-novo"
    )
    assert reaprovada.status_code == 200, reaprovada.text
    liberada = _export_bulletin(
        client, round_id, base_version=reaprovada.json()["version"], key="exportar-liberada"
    )

    assert recusada.status_code == 422, recusada.text
    assert recusada.json()["detail"]["details"]["code"] == "VALUATION_EXPORT_BLOCKED"
    # O ato novo cobre o conteúdo novo, e a exportação passa.
    assert reaprovada.json()["approval"]["stale"] is False
    assert liberada.status_code == 200, liberada.text
    assert liberada.json()["workbook_present"] is True


def test_a_exportacao_publica_por_digest_e_a_url_sai_so_na_leitura(tmp_path: Path) -> None:
    """Planilha endereçada pelo digest da medição; a URL assinada nunca é persistida."""
    client = _client(tmp_path)
    prepared = _round_with_bulletin(client)
    round_id = prepared["round_id"]
    approved = _approve(client, round_id, base_version=prepared["version"])
    assert approved.status_code == 200, approved.text
    valuation_sha256 = approved.json()["valuation_sha256"]

    response = _export_bulletin(client, round_id, base_version=approved.json()["version"])

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["workbook_present"] is True
    # A resposta do POST — que é o que a idempotência guarda — não carrega URL assinada.
    assert "workbook_url" not in body
    esperado = f"tenants/{_TENANT}/valuation-rounds/{round_id}/bulletin/{valuation_sha256}.xlsx"
    assert esperado in _store(client).objects
    with _database(client).sessions() as session:
        revision = session.scalar(
            select(ValuationRoundRevisionRecord)
            .where(ValuationRoundRevisionRecord.round_id == round_id)
            .order_by(ValuationRoundRevisionRecord.version.desc())
        )
        assert revision is not None
        assert revision.artifact_refs_json["bulletin_workbook"] == esperado
        assert revision.artifact_digests_json["bulletin_workbook_sha256"] == body["workbook_sha256"]
        # A exportação não altera a medição: o artefato da cabeça continua o mesmo.
        assert revision.valuation_json is not None

    leitura = _get_bulletin(client, round_id)
    assert leitura.status_code == 200, leitura.text
    assert leitura.json()["workbook_url"] is not None
    assert esperado in leitura.json()["workbook_url"]


def test_auditoria_divergente_do_boletim_nao_publica_nada(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Portão fail-closed: o `.xlsx` não sobe, a revisão não nasce e o valor não vaza."""
    client = _client(tmp_path)
    prepared = _round_with_bulletin(client)
    round_id = prepared["round_id"]
    approved = _approve(client, round_id, base_version=prepared["version"])
    assert approved.status_code == 200, approved.text
    objects_before = set(_store(client).objects)
    version_before = _round_version(client, round_id)
    monkeypatch.setattr(valuation_rounds, "audit_workbook", _divergent_audit)

    response = _export_bulletin(
        client, round_id, base_version=approved.json()["version"], key="exportar-auditoria"
    )

    assert response.status_code == 500
    detail = response.json()["detail"]
    assert detail["code"] == "VALUATION_WORKBOOK_AUDIT_FAILED"
    assert detail["details"]["finding_codes"] == ["CELL_VALUE_MISMATCH"]
    assert "9999.99" not in response.text and "1125.00" not in response.text
    assert set(_store(client).objects) == objects_before
    assert _round_version(client, round_id) == version_before


def test_a_exportacao_registra_auditoria_sem_url_assinada_nem_conteudo(tmp_path: Path) -> None:
    """O registro de auditoria guarda o ato e IDs opacos — nunca a URL nem o valor medido."""
    client = _client(tmp_path)
    prepared = _round_with_bulletin(client)
    round_id = prepared["round_id"]
    approved = _approve(client, round_id, base_version=prepared["version"])
    assert approved.status_code == 200, approved.text
    exportada = _export_bulletin(client, round_id, base_version=approved.json()["version"])
    assert exportada.status_code == 200, exportada.text

    with _database(client).sessions() as session:
        acoes = [
            record.action
            for record in session.scalars(select(AuditRecord)).all()
            if record.resource_id == round_id
        ]
        registros = json.dumps(
            [
                {"action": record.action, "resource_id": record.resource_id}
                for record in session.scalars(select(AuditRecord)).all()
            ]
        )

    assert "VALUATION_APPROVED" in acoes
    assert "BULLETIN_EXPORTED" in acoes
    assert "https://" not in registros
    assert exportada.json()["total_amount"] not in registros


def test_papel_idempotencia_e_concorrencia_valem_nas_duas_rotas_novas(tmp_path: Path) -> None:
    """As duas rotas novas herdam as guardas de sempre: papel, chave e `base_version`."""
    client = _client(tmp_path)
    prepared = _round_with_bulletin(client)
    round_id = prepared["round_id"]

    for rota in (f"{round_id}/approve", f"{round_id}/bulletin/export"):
        sem_papel = client.post(
            f"/v1/valuation-rounds/{rota}",
            headers=_headers(roles="engenheiro", key=f"papel-{rota}"),
            json={"base_version": prepared["version"]},
        )
        sem_chave = client.post(
            f"/v1/valuation-rounds/{rota}",
            headers={"Authorization": f"Bearer test:{_TENANT}:orcamentista-sintetica:orcamentista"},
            json={"base_version": prepared["version"]},
        )
        versao_velha = client.post(
            f"/v1/valuation-rounds/{rota}",
            headers=_headers(key=f"versao-{rota}"),
            json={"base_version": prepared["version"] - 1},
        )

        assert sem_papel.status_code == 403, sem_papel.text
        assert sem_chave.status_code == 400, sem_chave.text
        assert versao_velha.status_code == 409, versao_velha.text
        assert versao_velha.json()["detail"]["code"] == "REVISION_CONFLICT"


def test_idempotencia_das_rotas_novas_devolve_a_mesma_resposta(tmp_path: Path) -> None:
    """Repetir a chamada com a mesma chave devolve a resposta gravada, sem nova revisão."""
    client = _client(tmp_path)
    prepared = _round_with_bulletin(client)
    round_id = prepared["round_id"]

    primeira = _approve(client, round_id, base_version=prepared["version"], key="aprovar-idem")
    repetida = _approve(client, round_id, base_version=prepared["version"], key="aprovar-idem")
    exportada = _export_bulletin(
        client, round_id, base_version=primeira.json()["version"], key="exportar-idem"
    )
    reexportada = _export_bulletin(
        client, round_id, base_version=primeira.json()["version"], key="exportar-idem"
    )

    assert primeira.status_code == 200, primeira.text
    assert repetida.json() == primeira.json()
    assert exportada.status_code == 200, exportada.text
    assert reexportada.json() == exportada.json()
    assert _round_version(client, round_id) == exportada.json()["version"]


def test_acoes_auditadas_da_rodada_viram_evento_com_o_codigo_estavel(tmp_path: Path) -> None:
    """`valuation.action_recorded.v1` espelha 1:1 a ação já gravada em `audit_events`.

    O catálogo v1 não granulariza essas ações em tipos próprios: quem consome recebe o
    MESMO código estável que a auditoria interna usa, e criar um tipo por ação antes de
    haver consumo real publicaria contrato que envelhece sem nunca ter sido lido.

    O `version` acompanha o contador único da cadeia da rodada (ADR-0028 D3), que é o que
    dá ordem causal ao consumidor — `occurred_at` sozinho não garante.
    """
    client = _client(tmp_path)
    created = _create_round(client)
    round_id = created["round_id"]

    associated = _associate_plate(client, round_id)
    assert associated.status_code == 200, associated.text

    with _database(client).sessions() as session:
        eventos = (
            session.query(DomainEventRecord)
            .filter_by(event_type="croquito.valuation.action_recorded.v1")
            .order_by(DomainEventRecord.created_at, DomainEventRecord.id)
            .all()
        )
        auditados = [
            record.action
            for record in session.query(AuditRecord)
            .filter_by(resource_type="valuation_round")
            .order_by(AuditRecord.created_at, AuditRecord.id)
            .all()
        ]
        # Rodada não é job: `job_id` fica nulo, e é isso que separa as duas jornadas.
        assert {evento.job_id for evento in eventos} == {None}
        assert {evento.tenant_id for evento in eventos} == {_TENANT}
        assert [evento.payload_json["action"] for evento in eventos] == auditados
        assert eventos[0].payload_json == {
            "action": "VALUATION_ROUND_CREATED",
            "round_id": round_id,
            "version": 1,
        }
        assert eventos[-1].payload_json["action"] == "VALUATION_PLATE_ASSOCIATED"
        assert eventos[-1].payload_json["round_id"] == round_id
        # Nome da obra e chave do objeto são dados do cliente e não atravessam.
        assert set(eventos[-1].payload_json) == {"action", "round_id", "version"}
