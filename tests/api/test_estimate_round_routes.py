"""Rotas `/v1/estimate-rounds` de F-020 (T3): da rodada aberta à planilha publicada.

Espelho estrutural de `test_valuation_round_routes.py`, protegendo as mesmas invariantes
de fronteira — papel antes do lookup, IDOR, `Idempotency-Key`, `base_version` — mais as
que só existem deste lado do ADR-0027:

- **cascata é dado ordenado**: uma origem por fonte
  (`ESTIMATE_CASCADE_ORIGIN_DUPLICATE`), a ordem instalada é a que a shortlist e a busca
  devolvem, e reordenar muda o que o orçamentista vê na etapa seguinte;
- **ordem é imutável depois da decisão de código**: reordenar depois disso é recusado no
  ato, e não na decisão seguinte, porque o domínio amarra o conjunto de decisões ao
  catálogo cabeça da cascata;
- **a decisão CITA a fonte**: confirmação sem `catalog_sha256` é recusa de contrato, e é a
  citação que faz cada linha do orçamento dizer de qual tabela o preço veio;
- **portão fail-closed da planilha**: auditoria divergente não publica `.xlsx`, não grava
  revisão e não devolve valor nenhum do cliente na mensagem de erro;
- **URL assinada**: sai só no `GET`, depois de conferido o prefixo do tenant, e nunca é
  gravada no registro de idempotência nem em auditoria.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from croquito_api import estimate_rounds
from croquito_api.config import ApiSettings
from croquito_api.database import (
    AuditRecord,
    Database,
    EstimateRoundRecord,
    EstimateRoundRevisionRecord,
    IdempotencyRecord,
)
from croquito_api.main import create_app
from croquito_api.valuation_rounds import document_digest
from croquito_core.ids import new_uuid7
from croquito_valuation.estimate_workbook import EstimateAuditFinding, EstimateAuditReport
from croquito_valuation.models import PriceCatalog, PriceCatalogEntry, PriceOrigin
from croquito_valuation.takeoff import (
    PlateBox,
    PlateEvidence,
    TakeoffItem,
    TakeoffItemStatus,
    TakeoffPacket,
)
from croquito_worker.valuation.round_extraction import PLATE_IMAGE_DIGEST, PLATE_IMAGE_REF
from tests.fakes import FakeObjectStore, synthetic_pdf

_TENANT = "tenant-a"
_OTHER_TENANT = "tenant-b"

_SCO_CODE = "CE04100010(/)"
_EMOP_CODE = "03.005.0010-A"
_ITEM_FIRST = "ti_00000000000000b1"
_ITEM_SECOND = "ti_00000000000000b2"
_IMAGE_DIGEST = "a" * 64


# --- montagem ---------------------------------------------------------------------------


def _client(tmp_path: Path) -> TestClient:
    database = Database(f"sqlite+pysqlite:///{tmp_path / 'estimate-api.db'}")
    database.create_schema()
    settings = ApiSettings(
        database_url=f"sqlite+pysqlite:///{tmp_path / 'estimate-api.db'}",
        artifact_bucket="croquito-test-artifacts",
        aws_region="sa-east-1",
        aws_endpoint_url="http://localhost:4566",
        queue_url=None,
        oidc_issuer=None,
        oidc_audience=None,
        web_origin="http://localhost:5173",
        allow_test_tokens=True,
        real_providers_enabled=False,
    )
    application = create_app(settings=settings, database=database)
    application.state.artifact_store = FakeObjectStore()
    return TestClient(application)


def _headers(
    tenant: str = _TENANT,
    roles: str = "orcamentista",
    *,
    key: str = "estimate-request-001",
) -> dict[str, str]:
    return {
        "Authorization": f"Bearer test:{tenant}:orcamentista-sintetica:{roles}",
        "Idempotency-Key": key,
    }


def _store(client: TestClient) -> FakeObjectStore:
    return cast(FakeObjectStore, cast(Any, client.app).state.artifact_store)


def _database(client: TestClient) -> Database:
    return cast(Database, cast(Any, client.app).state.database)


def _revisions(client: TestClient) -> list[EstimateRoundRevisionRecord]:
    with _database(client).sessions() as session:
        return list(session.scalars(select(EstimateRoundRevisionRecord)))


def _catalog_bytes(
    *,
    origin: PriceOrigin,
    unit: str = "m",
    unit_price: str = "50.00",
    label: str = "CATALOGO SINTETICO",
    source_sha256: str | None = None,
) -> bytes:
    """Catálogo sintético de uma entrada, com o código que a origem exige.

    `unit_price` diferente por origem é o que torna visível, no orçamento, QUAL fonte
    precificou a linha — a proveniência deixa de ser rótulo e vira número conferível.
    """
    code = _SCO_CODE if origin == PriceOrigin.SCO else _EMOP_CODE
    catalog = PriceCatalog(
        source_label=label,
        reference_month="2026-01",
        # `source_sha256` é o digest do arquivo de ORIGEM que o importador leu, e por isso
        # não é o digest do JSON que sobe pelo presign: os dois viajam separados na cascata.
        source_sha256=(
            source_sha256 or hashlib.sha256(f"origem-{origin.value}".encode()).hexdigest()
        ),
        origin=origin,
        entries=[
            PriceCatalogEntry(
                code=code,
                description="ALAMBRADO GALVANIZADO",
                unit=unit,
                unit_price=Decimal(unit_price),
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


def _round_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "worksite_key": "praca-sintetica-norte",
        "worksite_name": "PRACA SINTETICA NORTE",
        "reference_label": "ORCAMENTO-BASE 2026",
        "address": "RUA SINTETICA, S/N",
    }
    payload.update(overrides)
    return payload


def _create_round(
    client: TestClient, *, tenant: str = _TENANT, key: str = "rodada-001", **overrides: Any
) -> dict[str, Any]:
    response = client.post(
        "/v1/estimate-rounds",
        headers=_headers(tenant, key=key),
        json=_round_payload(**overrides),
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, Any], response.json())


def _install_catalog(
    client: TestClient,
    round_id: str,
    *,
    origin: PriceOrigin,
    base_version: int,
    tenant: str = _TENANT,
    key: str | None = None,
    unit: str = "m",
    unit_price: str = "50.00",
    source_sha256: str | None = None,
) -> Any:
    suffix = key or f"catalogo-{origin.value}"
    upload = _presign_and_put(
        client,
        tenant=tenant,
        filename="catalogo.json",
        content_type="application/json",
        payload=_catalog_bytes(
            origin=origin, unit=unit, unit_price=unit_price, source_sha256=source_sha256
        ),
        key=f"upload-{suffix}",
    )
    return client.post(
        f"/v1/estimate-rounds/{round_id}/catalogs",
        headers=_headers(tenant, key=suffix),
        json={"upload_id": upload["upload_id"], "base_version": base_version},
    )


def _plate_upload(client: TestClient, *, tenant: str = _TENANT, key: str = "prancha") -> Any:
    return _presign_and_put(
        client,
        tenant=tenant,
        filename="prancha.pdf",
        content_type="application/pdf",
        payload=synthetic_pdf(),
        key=key,
    )


def _takeoff_item(
    item_id: str, *, status: TakeoffItemStatus = TakeoffItemStatus.PROPOSED
) -> TakeoffItem:
    """Item sintético como a extração o publica: proposto, com a quantidade já lida."""
    return TakeoffItem(
        id=item_id,
        evidence=PlateEvidence(
            plate_id="rodada-sintetica",
            page_number=1,
            image_sha256=_IMAGE_DIGEST,
            bbox=PlateBox(left=10, top=10, right=210, bottom=60),
        ),
        raw_text="ALAMBRADO GALVANIZADO 10,00 m",
        label="ALAMBRADO GALVANIZADO",
        quantity=Decimal("10.00"),
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
        items=items if items is not None else [_takeoff_item(_ITEM_FIRST)],
        safety_notes=[
            "Extração automática da legenda; quantidade não confirmada.",
            "Decisão do orçamentista obrigatória antes de qualquer orçamento.",
        ],
    )


def _publish_takeoff(
    client: TestClient,
    round_id: str,
    packet: TakeoffPacket,
    *,
    tenant: str = _TENANT,
) -> dict[str, Any]:
    """Publica o pacote como o comando de fila faria, e avança a rodada.

    O teste escreve a revisão direto porque a extração é PAGA: exercitá-la aqui só para
    chegar ao takeoff faria cada teste desta seção depender do braço do provider.
    """
    document = packet.model_dump(mode="json")
    with _database(client).sessions() as session:
        record = session.get(EstimateRoundRecord, round_id)
        assert record is not None
        head = session.scalar(
            select(EstimateRoundRevisionRecord)
            .where(EstimateRoundRevisionRecord.round_id == round_id)
            .order_by(EstimateRoundRevisionRecord.version.desc())
            .limit(1)
        )
        session.add(
            EstimateRoundRevisionRecord(
                id=str(new_uuid7()),
                tenant_id=tenant,
                round_id=round_id,
                version=1 if head is None else head.version + 1,
                parent_revision_id=None if head is None else head.id,
                created_by="estimate-extraction-v1",
                takeoff_packet_json=document,
                artifact_refs_json={
                    PLATE_IMAGE_REF: (
                        f"tenants/{tenant}/estimate-rounds/{round_id}/plate/page-001.png"
                    )
                },
                artifact_digests_json={PLATE_IMAGE_DIGEST: packet.image_sha256},
            )
        )
        record.version += 1
        session.commit()
        version = record.version
    return {"packet_sha256": document_digest(document), "version": version}


def _confirm_takeoff_item(
    client: TestClient,
    round_id: str,
    *,
    item_id: str,
    base_version: int,
    key: str,
    tenant: str = _TENANT,
) -> Any:
    return client.post(
        f"/v1/estimate-rounds/{round_id}/takeoff/decisions",
        headers=_headers(tenant, key=key),
        json={"base_version": base_version, "item_id": item_id, "action": "confirm"},
    )


def _round_with_cascade_and_takeoff(
    client: TestClient,
    packet: TakeoffPacket | None = None,
    *,
    confirm: Sequence[str] = (_ITEM_FIRST,),
) -> dict[str, Any]:
    """Rodada com SCO e EMOP instalados, nessa ordem, e o takeoff publicado e revisado.

    A confirmação passa pela ROTA de decisão, e não por escrita direta: é o caminho que o
    orçamentista percorre, e usá-lo aqui faz cada cenário adiante partir de um estado que
    a própria API produziu.
    """
    created = _create_round(client)
    round_id = created["round_id"]
    sco = _install_catalog(client, round_id, origin=PriceOrigin.SCO, base_version=1)
    assert sco.status_code == 201, sco.text
    emop = _install_catalog(
        client, round_id, origin=PriceOrigin.EMOP, base_version=2, unit_price="40.00"
    )
    assert emop.status_code == 201, emop.text
    published = _publish_takeoff(client, round_id, packet or _takeoff_packet())
    version = published["version"]
    for index, item_id in enumerate(confirm, start=1):
        decided = _confirm_takeoff_item(
            client, round_id, item_id=item_id, base_version=version, key=f"takeoff-{index}"
        )
        assert decided.status_code == 200, decided.text
        version = decided.json()["version"]
    return {
        "round_id": round_id,
        "cascade": emop.json()["cascade"],
        "packet_sha256": published["packet_sha256"],
        "version": version,
    }


def _confirm_code(
    client: TestClient,
    round_id: str,
    *,
    item_id: str,
    code: str,
    catalog_sha256: str,
    base_version: int,
    key: str,
    tenant: str = _TENANT,
) -> Any:
    return client.post(
        f"/v1/estimate-rounds/{round_id}/code-assignments/decisions",
        headers=_headers(tenant, key=key),
        json={
            "base_version": base_version,
            "item_id": item_id,
            "action": "confirm",
            "code": code,
            "catalog_sha256": catalog_sha256,
        },
    )


# --- criação e papel --------------------------------------------------------------------


def test_a_rodada_nasce_sem_cascata_e_com_versao_um(tmp_path: Path) -> None:
    client = _client(tmp_path)

    body = _create_round(client)

    assert body["version"] == 1
    assert body["status"] == "OPEN"
    with _database(client).sessions() as session:
        record = session.get(EstimateRoundRecord, body["round_id"])
        assert record is not None
        assert record.tenant_id == _TENANT
        assert record.catalog_cascade_json == []
        assert record.extraction_status == "idle"
        assert record.address == "RUA SINTETICA, S/N"


def test_sem_o_papel_toda_rota_recusa_antes_do_lookup(tmp_path: Path) -> None:
    """`403` inclusive na LEITURA e inclusive para rodada inexistente.

    É o que impede alguém sem o papel de descobrir, pela diferença entre `403` e `404`, o
    que existe no tenant vizinho.
    """
    client = _client(tmp_path)
    created = _create_round(client)
    round_id = created["round_id"]
    ghost = uuid4()
    headers = _headers(roles="engineer", key="sem-papel")

    reads = [
        "/v1/estimate-rounds",
        f"/v1/estimate-rounds/{round_id}",
        f"/v1/estimate-rounds/{ghost}",
        f"/v1/estimate-rounds/{round_id}/plate",
        f"/v1/estimate-rounds/{round_id}/takeoff",
        f"/v1/estimate-rounds/{round_id}/takeoff/overlay",
        f"/v1/estimate-rounds/{round_id}/code-suggestions",
        f"/v1/estimate-rounds/{round_id}/catalog/search?q=alambrado",
        f"/v1/estimate-rounds/{round_id}/code-assignments",
        f"/v1/estimate-rounds/{round_id}/estimate",
    ]
    for path in reads:
        response = client.get(path, headers=headers)
        assert response.status_code == 403, path
        assert response.json()["detail"]["code"] == "FORBIDDEN", path

    writes: list[tuple[str, dict[str, Any]]] = [
        ("/v1/estimate-rounds", _round_payload()),
        (
            f"/v1/estimate-rounds/{round_id}/catalogs",
            {"upload_id": str(uuid4()), "base_version": 1},
        ),
        (
            f"/v1/estimate-rounds/{round_id}/catalogs/order",
            {"base_version": 1, "cascade": ["a" * 64]},
        ),
        (f"/v1/estimate-rounds/{round_id}/plate", {"upload_id": str(uuid4()), "base_version": 1}),
        (f"/v1/estimate-rounds/{round_id}/plate/extractions", {"base_version": 1}),
        (
            f"/v1/estimate-rounds/{round_id}/takeoff/decisions",
            {"base_version": 1, "item_id": _ITEM_FIRST, "action": "confirm"},
        ),
        (f"/v1/estimate-rounds/{round_id}/code-suggestions/recompute", {"base_version": 1}),
        (
            f"/v1/estimate-rounds/{round_id}/code-assignments/decisions",
            {
                "base_version": 1,
                "item_id": _ITEM_FIRST,
                "action": "confirm",
                "code": _SCO_CODE,
                "catalog_sha256": "a" * 64,
            },
        ),
        (f"/v1/estimate-rounds/{round_id}/estimate", {"base_version": 1, "bdi_percent": "25.00"}),
        (
            f"/v1/estimate-rounds/{round_id}/target",
            {"base_version": 1, "target_amount": "10000.00"},
        ),
    ]
    for path, payload in writes:
        response = client.post(path, headers=headers, json=payload)
        assert response.status_code == 403, path
        assert response.json()["detail"]["code"] == "FORBIDDEN", path


def test_rodada_de_outro_tenant_e_404_e_nunca_403(tmp_path: Path) -> None:
    client = _client(tmp_path)
    created = _create_round(client)

    response = client.get(
        f"/v1/estimate-rounds/{created['round_id']}",
        headers=_headers(_OTHER_TENANT, key="ioador"),
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "NOT_FOUND"


def test_post_sem_idempotency_key_recusa(tmp_path: Path) -> None:
    client = _client(tmp_path)
    created = _create_round(client)
    headers = _headers()
    headers.pop("Idempotency-Key")

    criacao = client.post("/v1/estimate-rounds", headers=headers, json=_round_payload())
    orcamento = client.post(
        f"/v1/estimate-rounds/{created['round_id']}/estimate",
        headers=headers,
        json={"base_version": 1, "bdi_percent": "25.00"},
    )
    teto = client.post(
        f"/v1/estimate-rounds/{created['round_id']}/target",
        headers=headers,
        json={"base_version": 1, "target_amount": "10000.00"},
    )

    for response in (criacao, orcamento, teto):
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"


def test_idempotency_key_reusada_com_outro_comando_recusa(tmp_path: Path) -> None:
    client = _client(tmp_path)
    body = _round_payload()

    first = client.post("/v1/estimate-rounds", headers=_headers(key="rodada-x"), json=body)
    second = client.post("/v1/estimate-rounds", headers=_headers(key="rodada-x"), json=body)
    reused = client.post(
        "/v1/estimate-rounds",
        headers=_headers(key="rodada-x"),
        json={**body, "worksite_name": "OUTRA OBRA"},
    )

    assert first.status_code == 201
    assert second.json() == first.json()
    assert reused.status_code == 409
    assert reused.json()["detail"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    with _database(client).sessions() as session:
        assert len(session.scalars(select(EstimateRoundRecord)).all()) == 1


def test_base_version_velho_recusa_sem_gravar_nada(tmp_path: Path) -> None:
    client = _client(tmp_path)
    created = _create_round(client)
    round_id = created["round_id"]
    assert _install_catalog(client, round_id, origin=PriceOrigin.SCO, base_version=1).status_code

    stale = _install_catalog(
        client, round_id, origin=PriceOrigin.EMOP, base_version=1, key="catalogo-velho"
    )

    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "REVISION_CONFLICT"
    with _database(client).sessions() as session:
        record = session.get(EstimateRoundRecord, round_id)
        assert record is not None
        assert [entry["origin"] for entry in record.catalog_cascade_json] == ["sco"]


# --- teto de verba (ADR-0040) ------------------------------------------------------------


def _set_target(
    client: TestClient,
    round_id: str,
    *,
    base_version: int,
    target_amount: str,
    target_label: str | None = None,
    key: str,
    tenant: str = _TENANT,
) -> Any:
    body: dict[str, Any] = {"base_version": base_version, "target_amount": target_amount}
    if target_label is not None:
        body["target_label"] = target_label
    return client.post(
        f"/v1/estimate-rounds/{round_id}/target",
        headers=_headers(tenant, key=key),
        json=body,
    )


def test_criar_rodada_com_teto_o_estado_devolve_o_bloco(tmp_path: Path) -> None:
    client = _client(tmp_path)

    created = _create_round(
        client,
        target_amount="50000.00",
        target_label="Relação de Praças 2026 · demanda 14",
    )

    state = client.get(
        f"/v1/estimate-rounds/{created['round_id']}", headers=_headers(key="estado-com-teto")
    )
    assert state.status_code == 200, state.text
    body = state.json()
    assert body["target"] == {
        "amount": "50000.00",
        "label": "Relação de Praças 2026 · demanda 14",
    }
    # Sem orçamento montado ainda: só `target` aparece, nada de consumo é derivado.
    assert "consumed" not in body
    assert "remaining" not in body
    assert "over" not in body
    with _database(client).sessions() as session:
        record = session.get(EstimateRoundRecord, created["round_id"])
        assert record is not None
        assert record.target_amount == "50000.00"
        assert record.target_label == "Relação de Praças 2026 · demanda 14"


def test_listagem_mostra_teto_cru_sem_consumo(tmp_path: Path) -> None:
    """A listagem devolve `target_amount`/`target_label` crus; nunca `consumed`/`over`.

    A listagem não busca a cabeça de cada rodada — buscá-la só para derivar o consumo
    faria uma página inteira pagar N consultas extras por um bloco que a Tela 1 do mock
    não pede ali.
    """
    client = _client(tmp_path)
    com_teto = _create_round(
        client,
        key="rodada-com-teto",
        worksite_key="praca-sintetica-com-teto",
        target_amount="85000.00",
        target_label="Relação de Praças 2026 · demanda 14",
    )
    sem_teto = _create_round(client, key="rodada-sem-teto", worksite_key="praca-sintetica-sem-teto")

    listagem = client.get("/v1/estimate-rounds", headers=_headers(key="listagem-teto"))

    assert listagem.status_code == 200, listagem.text
    items = {item["round_id"]: item for item in listagem.json()["items"]}
    com_teto_item = items[com_teto["round_id"]]
    assert com_teto_item["target_amount"] == "85000.00"
    assert com_teto_item["target_label"] == "Relação de Praças 2026 · demanda 14"
    assert "consumed" not in com_teto_item
    assert "over" not in com_teto_item
    sem_teto_item = items[sem_teto["round_id"]]
    assert sem_teto_item["target_amount"] is None
    assert sem_teto_item["target_label"] is None


def test_criar_rodada_sem_teto_o_bloco_fica_ausente_mesmo_com_orcamento_montado(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)
    state = _round_ready_for_estimate(client)
    montagem = client.post(
        f"/v1/estimate-rounds/{state['round_id']}/estimate",
        headers=_headers(key="montagem-sem-teto"),
        json={"base_version": state["version"], "bdi_percent": "25.00"},
    )
    assert montagem.status_code == 200, montagem.text
    body = montagem.json()
    for key in ("target", "consumed", "remaining", "over"):
        assert key not in body

    leitura = client.get(
        f"/v1/estimate-rounds/{state['round_id']}", headers=_headers(key="estado-sem-teto")
    )
    assert leitura.status_code == 200, leitura.text
    for key in ("target", "consumed", "remaining", "over"):
        assert key not in leitura.json()


def test_declarar_teto_depois_da_criacao(tmp_path: Path) -> None:
    client = _client(tmp_path)
    created = _create_round(client)
    round_id = created["round_id"]

    response = _set_target(
        client, round_id, base_version=1, target_amount="12345.67", key="declarar-teto"
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["round_id"] == round_id
    assert body["version"] == 2
    assert body["target"] == {"amount": "12345.67", "label": None}
    with _database(client).sessions() as session:
        record = session.get(EstimateRoundRecord, round_id)
        assert record is not None
        assert record.target_amount == "12345.67"
        assert record.target_label is None
        assert record.version == 2


def test_editar_teto_ja_declarado(tmp_path: Path) -> None:
    client = _client(tmp_path)
    created = _create_round(client, target_amount="10000.00", target_label="Verba original")
    round_id = created["round_id"]

    edited = _set_target(
        client,
        round_id,
        base_version=1,
        target_amount="20000.00",
        target_label="Verba revista",
        key="editar-teto",
    )

    assert edited.status_code == 200, edited.text
    body = edited.json()
    assert body["target"] == {"amount": "20000.00", "label": "Verba revista"}
    assert body["version"] == 2
    with _database(client).sessions() as session:
        record = session.get(EstimateRoundRecord, round_id)
        assert record is not None
        assert record.target_amount == "20000.00"
        assert record.target_label == "Verba revista"


def test_teto_com_base_version_velho_recusa_sem_gravar_nada(tmp_path: Path) -> None:
    client = _client(tmp_path)
    created = _create_round(client, target_amount="10000.00")
    round_id = created["round_id"]
    ok = _set_target(client, round_id, base_version=1, target_amount="20000.00", key="teto-ok")
    assert ok.status_code == 200, ok.text

    stale = _set_target(
        client, round_id, base_version=1, target_amount="99999.99", key="teto-velho"
    )

    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "REVISION_CONFLICT"
    with _database(client).sessions() as session:
        record = session.get(EstimateRoundRecord, round_id)
        assert record is not None
        # A gravação válida venceu; a tentativa com `base_version` velho não tocou nada.
        assert record.target_amount == "20000.00"


def test_teto_invalido_recusa_com_o_codigo_unico(tmp_path: Path) -> None:
    client = _client(tmp_path)
    created = _create_round(client)
    round_id = created["round_id"]

    for index, invalid_amount in enumerate(("0.00", "-10.00", "não-é-um-decimal"), start=1):
        response = _set_target(
            client,
            round_id,
            base_version=1,
            target_amount=invalid_amount,
            key=f"teto-invalido-{index}",
        )
        assert response.status_code == 422, invalid_amount
        assert response.json()["detail"]["code"] == "ESTIMATE_TARGET_INVALID", invalid_amount
    with _database(client).sessions() as session:
        record = session.get(EstimateRoundRecord, round_id)
        assert record is not None
        assert record.target_amount is None
        assert record.version == 1


def test_criar_rodada_com_teto_invalido_recusa_na_criacao(tmp_path: Path) -> None:
    client = _client(tmp_path)

    response = client.post(
        "/v1/estimate-rounds",
        headers=_headers(key="criacao-teto-invalido"),
        json=_round_payload(target_amount="0.00"),
    )

    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "ESTIMATE_TARGET_INVALID"
    with _database(client).sessions() as session:
        assert session.scalars(select(EstimateRoundRecord)).all() == []


def test_bloco_derivado_nos_tres_estados_do_teto(tmp_path: Path) -> None:
    """O mesmo orçamento montado (`total_amount == "1125.00"`), três tetos diferentes.

    O limite exato é o caso que a comparação em dinheiro mais pode errar: teto igual ao
    total conhecido do cenário tem que devolver `over: false` e `remaining == "0.00"`,
    nunca um resíduo de ponto flutuante.
    """
    client = _client(tmp_path)
    state = _round_ready_for_estimate(client)
    round_id = state["round_id"]
    montagem = client.post(
        f"/v1/estimate-rounds/{round_id}/estimate",
        headers=_headers(key="montagem-teto"),
        json={"base_version": state["version"], "bdi_percent": "25.00"},
    )
    assert montagem.status_code == 200, montagem.text
    assert montagem.json()["total_amount"] == "1125.00"
    version = montagem.json()["version"]

    dentro = _set_target(
        client, round_id, base_version=version, target_amount="2000.00", key="teto-dentro"
    )
    assert dentro.status_code == 200, dentro.text
    dentro_body = dentro.json()
    assert dentro_body["consumed"] == "1125.00"
    assert dentro_body["remaining"] == "875.00"
    assert dentro_body["over"] is False

    limite = _set_target(
        client,
        round_id,
        base_version=dentro_body["version"],
        target_amount="1125.00",
        key="teto-limite",
    )
    assert limite.status_code == 200, limite.text
    limite_body = limite.json()
    assert limite_body["consumed"] == "1125.00"
    assert limite_body["remaining"] == "0.00"
    assert limite_body["over"] is False

    estourado = _set_target(
        client,
        round_id,
        base_version=limite_body["version"],
        target_amount="1124.99",
        key="teto-estourado",
    )
    assert estourado.status_code == 200, estourado.text
    estourado_body = estourado.json()
    assert estourado_body["consumed"] == "1125.00"
    assert estourado_body["remaining"] == "-0.01"
    assert estourado_body["over"] is True

    # O `GET /estimate` deriva o MESMO bloco, lendo o `total_amount` gravado — nunca
    # recomputando dinheiro.
    leitura = client.get(
        f"/v1/estimate-rounds/{round_id}/estimate", headers=_headers(key="leitura-teto")
    )
    assert leitura.status_code == 200, leitura.text
    assert leitura.json()["remaining"] == "-0.01"
    assert leitura.json()["over"] is True


# --- cascata ----------------------------------------------------------------------------


def test_a_cascata_guarda_a_ordem_de_instalacao(tmp_path: Path) -> None:
    client = _client(tmp_path)
    created = _create_round(client)
    round_id = created["round_id"]

    _install_catalog(client, round_id, origin=PriceOrigin.SCO, base_version=1)
    response = _install_catalog(client, round_id, origin=PriceOrigin.EMOP, base_version=2)

    assert response.status_code == 201, response.text
    cascade = response.json()["cascade"]
    assert [entry["position"] for entry in cascade] == [1, 2]
    assert [entry["origin"] for entry in cascade] == ["sco", "emop"]
    # Referência interna do store não sai para o cliente.
    assert all("object_key" not in entry and "upload_id" not in entry for entry in cascade)


def test_origem_repetida_na_cascata_recusa_com_o_codigo_do_dominio(tmp_path: Path) -> None:
    client = _client(tmp_path)
    created = _create_round(client)
    round_id = created["round_id"]
    _install_catalog(client, round_id, origin=PriceOrigin.SCO, base_version=1)

    response = _install_catalog(
        client, round_id, origin=PriceOrigin.SCO, base_version=2, key="catalogo-sco-2"
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "ESTIMATE_CASCADE_ORIGIN_DUPLICATE"
    assert detail["details"]["origin"] == "sco"
    with _database(client).sessions() as session:
        record = session.get(EstimateRoundRecord, round_id)
        assert record is not None
        assert len(record.catalog_cascade_json) == 1
        assert record.version == 2


def test_duas_fontes_com_o_mesmo_digest_de_origem_recusam(tmp_path: Path) -> None:
    """Origens diferentes, mesmo arquivo de origem: o digest deixaria de identificar a fonte.

    É o digest de origem que a confirmação de código cita, que a reordenação recebe e que a
    montagem usa para achar o catálogo. Com dois candidatos, nenhuma das três consegue
    distinguir a fonte — e nada disso teria conserto depois da instalação.
    """
    client = _client(tmp_path)
    created = _create_round(client)
    round_id = created["round_id"]
    compartilhado = "9" * 64
    primeiro = _install_catalog(
        client, round_id, origin=PriceOrigin.SCO, base_version=1, source_sha256=compartilhado
    )
    assert primeiro.status_code == 201, primeiro.text

    response = _install_catalog(
        client,
        round_id,
        origin=PriceOrigin.EMOP,
        base_version=2,
        source_sha256=compartilhado,
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ESTIMATE_CASCADE_ORIGIN_DUPLICATE"
    with _database(client).sessions() as session:
        record = session.get(EstimateRoundRecord, round_id)
        assert record is not None
        assert len(record.catalog_cascade_json) == 1


def test_reordenacao_exige_permutacao_completa(tmp_path: Path) -> None:
    client = _client(tmp_path)
    state = _round_with_cascade_and_takeoff(client)
    digests = [entry["source_sha256"] for entry in state["cascade"]]

    parcial = client.post(
        f"/v1/estimate-rounds/{state['round_id']}/catalogs/order",
        headers=_headers(key="ordem-parcial"),
        json={"base_version": state["version"], "cascade": digests[:1]},
    )
    repetida = client.post(
        f"/v1/estimate-rounds/{state['round_id']}/catalogs/order",
        headers=_headers(key="ordem-repetida"),
        json={"base_version": state["version"], "cascade": [digests[0], digests[0]]},
    )

    for response in (parcial, repetida):
        assert response.status_code == 422, response.text
        assert response.json()["detail"]["code"] == "ESTIMATE_CASCADE_ORDER_INVALID"


def test_reordenar_a_cascata_muda_a_precificacao_da_sugestao_seguinte(tmp_path: Path) -> None:
    """A ordem é dado: promover a EMOP muda o bloco que abre a shortlist e a busca.

    É o efeito que o ADR-0027 quer visível — a preferência de tabela é do orçamentista, e
    ela aparece na etapa seguinte sem que nada seja recalculado escondido.
    """
    client = _client(tmp_path)
    state = _round_with_cascade_and_takeoff(client)
    round_id = state["round_id"]
    digests = [entry["source_sha256"] for entry in state["cascade"]]

    antes = client.get(
        f"/v1/estimate-rounds/{round_id}/code-suggestions", headers=_headers(key="shortlist-1")
    )
    assert antes.status_code == 200, antes.text
    candidatos_antes = antes.json()["suggestions"]["suggestions"][0]["candidates"]
    assert [candidate["code"] for candidate in candidatos_antes] == [_SCO_CODE, _EMOP_CODE]

    busca_antes = client.get(
        f"/v1/estimate-rounds/{round_id}/catalog/search",
        headers=_headers(key="busca-1"),
        params={"q": "alambrado"},
    )
    assert busca_antes.status_code == 200, busca_antes.text
    assert [result["price_origin"] for result in busca_antes.json()["results"]] == ["sco", "emop"]
    assert [result["cascade_position"] for result in busca_antes.json()["results"]] == [1, 2]

    reorder = client.post(
        f"/v1/estimate-rounds/{round_id}/catalogs/order",
        headers=_headers(key="ordem-nova"),
        json={"base_version": state["version"], "cascade": [digests[1], digests[0]]},
    )
    assert reorder.status_code == 200, reorder.text
    assert [entry["origin"] for entry in reorder.json()["cascade"]] == ["emop", "sco"]

    depois = client.post(
        f"/v1/estimate-rounds/{round_id}/code-suggestions/recompute",
        headers=_headers(key="shortlist-2"),
        json={"base_version": reorder.json()["version"]},
    )
    assert depois.status_code == 200, depois.text
    candidatos_depois = depois.json()["suggestions"]["suggestions"][0]["candidates"]
    assert [candidate["code"] for candidate in candidatos_depois] == [_EMOP_CODE, _SCO_CODE]

    busca_depois = client.get(
        f"/v1/estimate-rounds/{round_id}/catalog/search",
        headers=_headers(key="busca-2"),
        params={"q": "alambrado"},
    )
    assert [result["price_origin"] for result in busca_depois.json()["results"]] == ["emop", "sco"]


def test_reordenar_depois_da_decisao_de_codigo_recusa_no_ato(tmp_path: Path) -> None:
    """Recusa aqui, e não na decisão seguinte, que é onde o domínio a descobriria.

    `CodeAssignmentSet` é amarrado ao catálogo CABEÇA da cascata; deixar a reordenação
    passar faria a próxima decisão falhar com `ASSIGNMENT_CATALOG_MISMATCH` — sobre um
    catálogo que ninguém trocou — e sem volta, porque não há rota que apague decisão.
    """
    client = _client(tmp_path)
    state = _round_with_cascade_and_takeoff(client)
    round_id = state["round_id"]
    digests = [entry["source_sha256"] for entry in state["cascade"]]
    decided = _confirm_code(
        client,
        round_id,
        item_id=_ITEM_FIRST,
        code=_SCO_CODE,
        catalog_sha256=digests[0],
        base_version=state["version"],
        key="decisao-1",
    )
    assert decided.status_code == 200, decided.text

    response = client.post(
        f"/v1/estimate-rounds/{round_id}/catalogs/order",
        headers=_headers(key="ordem-tarde"),
        json={"base_version": decided.json()["version"], "cascade": [digests[1], digests[0]]},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ESTIMATE_CASCADE_LOCKED"
    with _database(client).sessions() as session:
        record = session.get(EstimateRoundRecord, round_id)
        assert record is not None
        assert [entry["origin"] for entry in record.catalog_cascade_json] == ["sco", "emop"]


def test_busca_sem_termo_utilizavel_recusa(tmp_path: Path) -> None:
    client = _client(tmp_path)
    state = _round_with_cascade_and_takeoff(client)

    response = client.get(
        f"/v1/estimate-rounds/{state['round_id']}/catalog/search",
        headers=_headers(key="busca-vazia"),
        params={"q": "-"},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "CATALOG_QUERY_EMPTY"


def test_etapas_fora_de_ordem_recusam_com_stage_not_ready(tmp_path: Path) -> None:
    client = _client(tmp_path)
    created = _create_round(client)
    round_id = created["round_id"]

    takeoff = client.get(
        f"/v1/estimate-rounds/{round_id}/takeoff", headers=_headers(key="takeoff-cedo")
    )
    orcamento = client.get(
        f"/v1/estimate-rounds/{round_id}/estimate", headers=_headers(key="orcamento-cedo")
    )
    montagem = client.post(
        f"/v1/estimate-rounds/{round_id}/estimate",
        headers=_headers(key="montagem-cedo"),
        json={"base_version": 1, "bdi_percent": "25.00"},
    )

    for response in (takeoff, orcamento, montagem):
        assert response.status_code == 409, response.text
        assert response.json()["detail"]["code"] == "ROUND_STAGE_NOT_READY"
    # A montagem sem cascata nomeia a etapa que falta, e não a que veio depois.
    assert montagem.json()["detail"]["details"]["stage"] == "catalogs"


# --- decisão de código ------------------------------------------------------------------


def test_confirmacao_sem_citar_a_fonte_e_recusa_de_contrato(tmp_path: Path) -> None:
    client = _client(tmp_path)
    state = _round_with_cascade_and_takeoff(client)

    response = client.post(
        f"/v1/estimate-rounds/{state['round_id']}/code-assignments/decisions",
        headers=_headers(key="sem-fonte"),
        json={
            "base_version": state["version"],
            "item_id": _ITEM_FIRST,
            "action": "confirm",
            "code": _SCO_CODE,
        },
    )

    assert response.status_code == 422
    assert not _revisions_with(client, "code_assignments_json")


def test_confirmacao_citando_fonte_fora_da_cascata_recusa_pelo_dominio(tmp_path: Path) -> None:
    client = _client(tmp_path)
    state = _round_with_cascade_and_takeoff(client)

    response = _confirm_code(
        client,
        state["round_id"],
        item_id=_ITEM_FIRST,
        code=_SCO_CODE,
        catalog_sha256="f" * 64,
        base_version=state["version"],
        key="fonte-desconhecida",
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "DOMAIN_VALIDATION_FAILED"
    assert detail["details"]["code"] == "ASSIGNMENT_CATALOG_UNKNOWN"


def test_a_decisao_carrega_a_fonte_citada_para_o_conjunto(tmp_path: Path) -> None:
    client = _client(tmp_path)
    state = _round_with_cascade_and_takeoff(client)
    digests = [entry["source_sha256"] for entry in state["cascade"]]

    response = _confirm_code(
        client,
        state["round_id"],
        item_id=_ITEM_FIRST,
        code=_SCO_CODE,
        catalog_sha256=digests[0],
        base_version=state["version"],
        key="decisao-fonte",
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["confirmed"] == 1
    assignment = body["assignments"]["assignments"][0]
    assert assignment["catalog_sha256"] == digests[0]
    assert assignment["code"] == _SCO_CODE


# --- montagem e planilha ----------------------------------------------------------------


def _revisions_with(client: TestClient, column: str) -> list[EstimateRoundRevisionRecord]:
    return [revision for revision in _revisions(client) if getattr(revision, column) is not None]


def _round_ready_for_estimate(client: TestClient) -> dict[str, Any]:
    """Rodada com duas fontes, dois itens confirmados e um código por fonte.

    Um item por origem é o que faz a proveniência do orçamentista aparecer em NÚMERO: os
    dois catálogos precificam diferente, e o total só fecha se cada linha tiver usado o
    preço da fonte que a decisão citou.
    """
    packet = _takeoff_packet([_takeoff_item(_ITEM_FIRST), _takeoff_item(_ITEM_SECOND)])
    state = _round_with_cascade_and_takeoff(client, packet, confirm=(_ITEM_FIRST, _ITEM_SECOND))
    digests = [entry["source_sha256"] for entry in state["cascade"]]
    first = _confirm_code(
        client,
        state["round_id"],
        item_id=_ITEM_FIRST,
        code=_SCO_CODE,
        catalog_sha256=digests[0],
        base_version=state["version"],
        key="decisao-sco",
    )
    assert first.status_code == 200, first.text
    second = _confirm_code(
        client,
        state["round_id"],
        item_id=_ITEM_SECOND,
        code=_EMOP_CODE,
        catalog_sha256=digests[1],
        base_version=first.json()["version"],
        key="decisao-emop",
    )
    assert second.status_code == 200, second.text
    return {**state, "version": second.json()["version"], "digests": digests}


def test_o_caminho_feliz_publica_orcamento_e_planilha_auditada(tmp_path: Path) -> None:
    client = _client(tmp_path)
    state = _round_ready_for_estimate(client)
    round_id = state["round_id"]

    response = client.post(
        f"/v1/estimate-rounds/{round_id}/estimate",
        headers=_headers(key="montagem"),
        json={"base_version": state["version"], "bdi_percent": "25.00"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["bdi_percent"] == "25.00"
    # O item citando o SCO custa 50,00 e o que cita a EMOP custa 40,00: sem BDI, 500,00 +
    # 400,00; com BDI de 25%, 10 x TRUNC(62,50) + 10 x TRUNC(50,00). O total só fecha se
    # cada linha tiver usado o preço da fonte que a DECISÃO citou — e não o da primeira
    # fonte da cascata, que precificaria as duas linhas a 625,00.
    assert body["total_amount_without_bdi"] == "900.00"
    assert body["total_amount"] == "1125.00"
    assert [line["price_origin"] for line in body["estimate"]["lines"]] == ["sco", "emop"]
    assert body["workbook_present"] is True
    # A resposta gravada no registro de idempotência jamais carrega URL assinada.
    assert "workbook_url" not in body
    with _database(client).sessions() as session:
        stored = session.scalars(
            select(IdempotencyRecord).where(
                IdempotencyRecord.operation == f"estimate-rounds.estimate:{round_id}"
            )
        ).all()
        assert len(stored) == 1
        assert "workbook_url" not in stored[0].response_json

    revisions = _revisions_with(client, "estimate_json")
    assert len(revisions) == 1
    object_key = revisions[0].artifact_refs_json[estimate_rounds.ESTIMATE_WORKBOOK_REF]
    assert object_key.startswith(f"tenants/{_TENANT}/estimate-rounds/{round_id}/estimate/")
    published = _store(client).objects[object_key]
    assert published.content_type == estimate_rounds.ESTIMATE_WORKBOOK_CONTENT_TYPE
    assert (
        hashlib.sha256(published.body).hexdigest()
        == revisions[0].artifact_digests_json[estimate_rounds.ESTIMATE_WORKBOOK_DIGEST]
    )

    leitura = client.get(
        f"/v1/estimate-rounds/{round_id}/estimate", headers=_headers(key="leitura")
    )
    assert leitura.status_code == 200, leitura.text
    assert leitura.json()["workbook_url"] == f"https://storage.invalid/{object_key}?temporary=true"
    assert leitura.json()["total_amount"] == "1125.00"

    with _database(client).sessions() as session:
        audits = session.scalars(
            select(AuditRecord).where(AuditRecord.resource_type == "estimate_round")
        ).all()
        assert [audit.action for audit in audits][-1] == "ESTIMATE_BUILT"
        # URL assinada nunca entra em auditoria.
        assert all("storage.invalid" not in str(audit.metadata_json) for audit in audits)


def test_o_estado_da_rodada_declara_cascata_orcamento_e_planilha(tmp_path: Path) -> None:
    client = _client(tmp_path)
    state = _round_ready_for_estimate(client)
    round_id = state["round_id"]
    montagem = client.post(
        f"/v1/estimate-rounds/{round_id}/estimate",
        headers=_headers(key="montagem-estado"),
        json={"base_version": state["version"], "bdi_percent": "25.00"},
    )
    assert montagem.status_code == 200, montagem.text

    response = client.get(f"/v1/estimate-rounds/{round_id}", headers=_headers(key="estado"))

    assert response.status_code == 200, response.text
    body = response.json()
    assert [entry["origin"] for entry in body["cascade"]] == ["sco", "emop"]
    assert body["estimate"]["present"] is True
    assert body["estimate"]["workbook_present"] is True
    assert body["codes"]["confirmed"] == 2
    assert body["reviewer_role"] == "orcamentista"

    listagem = client.get("/v1/estimate-rounds", headers=_headers(key="listagem"))
    assert listagem.status_code == 200, listagem.text
    item = listagem.json()["items"][0]
    assert item["stage"] == "estimate"
    assert item["cascade_origins"] == ["sco", "emop"]


def test_takeoff_com_item_pendente_recusa_a_montagem(tmp_path: Path) -> None:
    client = _client(tmp_path)
    packet = _takeoff_packet([_takeoff_item(_ITEM_FIRST), _takeoff_item(_ITEM_SECOND)])
    # Só o primeiro item é decidido: o segundo continua pendente de revisão.
    state = _round_with_cascade_and_takeoff(client, packet, confirm=(_ITEM_FIRST,))
    digests = [entry["source_sha256"] for entry in state["cascade"]]
    decided = _confirm_code(
        client,
        state["round_id"],
        item_id=_ITEM_FIRST,
        code=_SCO_CODE,
        catalog_sha256=digests[0],
        base_version=state["version"],
        key="decisao-pendente",
    )
    assert decided.status_code == 200, decided.text

    response = client.post(
        f"/v1/estimate-rounds/{state['round_id']}/estimate",
        headers=_headers(key="montagem-pendente"),
        json={"base_version": decided.json()["version"], "bdi_percent": "25.00"},
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "ROUND_STAGE_NOT_READY"
    assert detail["details"]["stage"] == "takeoff"
    assert not _revisions_with(client, "estimate_json")


def test_bdi_ilegivel_recusa_antes_de_montar_qualquer_coisa(tmp_path: Path) -> None:
    client = _client(tmp_path)
    state = _round_ready_for_estimate(client)

    ilegivel = client.post(
        f"/v1/estimate-rounds/{state['round_id']}/estimate",
        headers=_headers(key="bdi-ruim"),
        json={"base_version": state["version"], "bdi_percent": "vinte"},
    )
    negativo = client.post(
        f"/v1/estimate-rounds/{state['round_id']}/estimate",
        headers=_headers(key="bdi-negativo"),
        json={"base_version": state["version"], "bdi_percent": "-1.00"},
    )

    for response in (ilegivel, negativo):
        assert response.status_code == 422, response.text
        assert response.json()["detail"]["code"] == "ESTIMATE_BDI_INVALID"
    assert not _revisions_with(client, "estimate_json")


def test_auditoria_divergente_nao_publica_nada(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Portão fail-closed: o `.xlsx` não sobe, a revisão não nasce e a rodada não avança.

    A recusa também não vaza valor do cliente: `EstimateAuditFinding` carrega preço e
    quantidade em `expected`/`found`, e o que sai é só o CÓDIGO do achado.
    """
    client = _client(tmp_path)
    state = _round_ready_for_estimate(client)
    round_id = state["round_id"]
    objects_before = set(_store(client).objects)

    def _divergent(*_args: Any, **_kwargs: Any) -> EstimateAuditReport:
        return EstimateAuditReport(
            status="divergent",
            workbook_sha256="d" * 64,
            sheet_name="ORCAMENTO",
            checked_cells=1,
            formula_cells=0,
            total_amount=Decimal("1125.00"),
            findings=[
                EstimateAuditFinding(
                    code="CELL_VALUE_MISMATCH",
                    sheet="ORCAMENTO",
                    ref="I8",
                    expected="1125.00",
                    found="9999.99",
                    detail="line_total",
                )
            ],
        )

    monkeypatch.setattr(estimate_rounds, "audit_estimate_workbook", _divergent)

    response = client.post(
        f"/v1/estimate-rounds/{round_id}/estimate",
        headers=_headers(key="auditoria-ruim"),
        json={"base_version": state["version"], "bdi_percent": "25.00"},
    )

    assert response.status_code == 500
    detail = response.json()["detail"]
    assert detail["code"] == "ESTIMATE_WORKBOOK_AUDIT_FAILED"
    assert detail["details"]["finding_codes"] == ["CELL_VALUE_MISMATCH"]
    assert "9999.99" not in response.text and "1125.00" not in response.text
    assert set(_store(client).objects) == objects_before
    assert not _revisions_with(client, "estimate_json")
    with _database(client).sessions() as session:
        record = session.get(EstimateRoundRecord, round_id)
        assert record is not None
        assert record.version == state["version"]


# --- prancha e extração ------------------------------------------------------------------


def test_a_prancha_e_associada_uma_vez_so(tmp_path: Path) -> None:
    client = _client(tmp_path)
    created = _create_round(client)
    round_id = created["round_id"]
    first_upload = _plate_upload(client, key="prancha-1")

    first = client.post(
        f"/v1/estimate-rounds/{round_id}/plate",
        headers=_headers(key="assoc-1"),
        json={"upload_id": first_upload["upload_id"], "base_version": 1},
    )
    second_upload = _plate_upload(client, key="prancha-2")
    second = client.post(
        f"/v1/estimate-rounds/{round_id}/plate",
        headers=_headers(key="assoc-2"),
        json={"upload_id": second_upload["upload_id"], "base_version": 2},
    )

    assert first.status_code == 200, first.text
    assert first.json()["image_url"] is None
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "ROUND_PLATE_ALREADY_PRESENT"


def test_extracao_paga_recusa_sem_provider_no_ambiente(tmp_path: Path) -> None:
    """Ambiente sem braço pago não enfileira nada e não move a rodada."""
    client = _client(tmp_path)
    created = _create_round(client)
    round_id = created["round_id"]
    upload = _plate_upload(client, key="prancha-extracao")
    associated = client.post(
        f"/v1/estimate-rounds/{round_id}/plate",
        headers=_headers(key="assoc-extracao"),
        json={"upload_id": upload["upload_id"], "base_version": 1},
    )
    assert associated.status_code == 200, associated.text

    response = client.post(
        f"/v1/estimate-rounds/{round_id}/plate/extractions",
        headers=_headers(key="extracao"),
        json={"base_version": associated.json()["version"]},
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "PROVIDER_UNAVAILABLE"
    with _database(client).sessions() as session:
        record = session.get(EstimateRoundRecord, round_id)
        assert record is not None
        assert record.extraction_status == "idle"


def test_url_assinada_so_sai_sob_o_prefixo_do_tenant(tmp_path: Path) -> None:
    """Chave gravada fora do prefixo é tratada como inexistente; o presign nem é chamado."""
    client = _client(tmp_path)
    state = _round_ready_for_estimate(client)
    round_id = state["round_id"]
    montagem = client.post(
        f"/v1/estimate-rounds/{round_id}/estimate",
        headers=_headers(key="montagem-prefixo"),
        json={"base_version": state["version"], "bdi_percent": "25.00"},
    )
    assert montagem.status_code == 200, montagem.text

    with _database(client).sessions() as session:
        revision = session.scalar(
            select(EstimateRoundRevisionRecord)
            .where(EstimateRoundRevisionRecord.round_id == round_id)
            .order_by(EstimateRoundRevisionRecord.version.desc())
            .limit(1)
        )
        assert revision is not None
        revision.artifact_refs_json = {
            **revision.artifact_refs_json,
            estimate_rounds.ESTIMATE_WORKBOOK_REF: (
                f"tenants/{_OTHER_TENANT}/estimate-rounds/{round_id}/estimate/roubo.xlsx"
            ),
        }
        session.commit()

    response = client.get(
        f"/v1/estimate-rounds/{round_id}/estimate", headers=_headers(key="leitura-prefixo")
    )

    assert response.status_code == 200, response.text
    assert response.json()["workbook_url"] is None


def test_a_extracao_e_o_estado_nascem_com_carimbo_de_criacao(tmp_path: Path) -> None:
    """A rodada recém-criada declara `created`, e não uma etapa que ela não alcançou."""
    client = _client(tmp_path)
    created = _create_round(client)

    listagem = client.get("/v1/estimate-rounds", headers=_headers(key="listagem-nova"))

    assert listagem.status_code == 200, listagem.text
    item = listagem.json()["items"][0]
    assert item["round_id"] == created["round_id"]
    assert item["stage"] == "created"
    assert item["cascade_origins"] == []
    assert item["extraction_status"] == "idle"
    assert item["reference_label"] == "ORCAMENTO-BASE 2026"
