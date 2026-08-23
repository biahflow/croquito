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

Desde a F-035 (ADR-0046), montar deixou de publicar e a cadeia tem três atos —
`estimate` → `estimate/approve` → `estimate/export` —, o que acrescenta três invariantes:

- **o portão de despacho é do DOMÍNIO** e corre antes de qualquer escrita: sem assinatura
  válida nada vai ao object store, nem a arquivo temporário;
- **quem montou não assina**, e a recusa compara IDENTIDADE, não papel — acumular
  `orcamentista` e `aprovador` no mesmo token não contorna;
- **o papel novo lê e não muta**: as 10 leituras aceitam os dois papéis, as 13 mutações da
  cadeia continuam exigindo `orcamentista`, e só `approve` exige `aprovador`.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

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
_PLATFORM_TENANT = "tenant-plataforma"
"""Quem publica no acervo. Não é o tenant da rodada de propósito: o acervo é dado da
PLATAFORMA, e uma tabela publicada por um tenant é instalável por outro sem novo upload."""

_SCO_CODE = "CE04100010(/)"
_EMOP_CODE = "03.005.0010-A"
_ITEM_FIRST = "ti_00000000000000b1"
_ITEM_SECOND = "ti_00000000000000b2"
_IMAGE_DIGEST = "a" * 64

_BUILDER_SUBJECT = "orcamentista-sintetica"
"""Quem monta o orçamento em todo teste que não fala de assinatura."""

_APPROVER_SUBJECT = "aprovadora-sintetica"
"""Quem assina. É deliberadamente OUTRA pessoa: na cadeia real quem aprova o orçamento não é
quem o montou (ADR-0046, decisão 5), e a fixture não desmente a regra."""

_APPROVER_ROLES = "aprovador"
_BOTH_ROLES = "orcamentista,aprovador"


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
    subject: str = _BUILDER_SUBJECT,
) -> dict[str, str]:
    """Token sintético do orçamentista que MONTA, salvo quando o teste pede outro subject.

    `subject` é parâmetro desde a F-035: a recusa de auto-aprovação compara identidade, e um
    token com subject fixo não teria como exercer "outra pessoa assina". O default continua
    sendo quem montava antes, para não reescrever os testes que não falam de assinatura.
    """
    return {
        "Authorization": f"Bearer test:{tenant}:{subject}:{roles}",
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


def _presign_reference_catalog(client: TestClient, *, payload: bytes, key: str) -> dict[str, Any]:
    """O presign DA PLATAFORMA (T6): publicar não passa pelo presign do croqui."""
    presign = client.post(
        "/v1/platform/reference-catalogs/presign",
        headers=_headers(_PLATFORM_TENANT, "platform_operator", key=key),
        json={
            "filename": "catalogo.json",
            "size_bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        },
    )
    assert presign.status_code == 200, presign.text
    _store(client).put_direct(
        object_key=presign.json()["object_key"], body=payload, content_type="application/json"
    )
    return cast(dict[str, Any], presign.json())


def _publish_reference_catalog(
    client: TestClient,
    *,
    origin: PriceOrigin = PriceOrigin.SCO,
    display_name: str = "SCO-Rio FGV06 desonerado",
    key: str = "acervo-sco",
    unit: str = "m",
    unit_price: str = "50.00",
    source_sha256: str | None = None,
) -> dict[str, Any]:
    """Publica no acervo da plataforma o MESMO arquivo que o upload subiria.

    Idêntico byte a byte ao de `_install_catalog` para o mesmo `origin`: é isso que torna
    conferível a afirmação de que a procedência é metadado, e não regra nova — os dois
    caminhos precisam produzir o mesmo `source_sha256` e o mesmo preço por linha.
    """
    payload = _catalog_bytes(
        origin=origin, unit=unit, unit_price=unit_price, source_sha256=source_sha256
    )
    upload = _presign_reference_catalog(client, payload=payload, key=f"upload-{key}")
    response = client.post(
        "/v1/platform/reference-catalogs",
        headers=_headers(_PLATFORM_TENANT, "platform_operator", key=key),
        json={"upload_id": upload["upload_id"], "display_name": display_name},
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, Any], response.json())


def _install_from_acervo(
    client: TestClient,
    round_id: str,
    *,
    reference_catalog_id: str,
    base_version: int,
    key: str,
    tenant: str = _TENANT,
) -> Any:
    """Instala citando a tabela do acervo: nenhum arquivo sobe, e nada é assinado."""
    return client.post(
        f"/v1/estimate-rounds/{round_id}/catalogs",
        headers=_headers(tenant, key=key),
        json={"reference_catalog_id": reference_catalog_id, "base_version": base_version},
    )


def _reference_catalog_options(
    client: TestClient, round_id: str, *, tenant: str = _TENANT, key: str = "escolha"
) -> Any:
    return client.get(
        f"/v1/estimate-rounds/{round_id}/reference-catalogs", headers=_headers(tenant, key=key)
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
    sco_from_acervo: bool = False,
) -> dict[str, Any]:
    """Rodada com SCO e EMOP instalados, nessa ordem, e o takeoff publicado e revisado.

    A confirmação passa pela ROTA de decisão, e não por escrita direta: é o caminho que o
    orçamentista percorre, e usá-lo aqui faz cada cenário adiante partir de um estado que
    a própria API produziu.

    `sco_from_acervo` troca **só** de onde o arquivo do SCO veio — mesmo conteúdo, mesma
    ordem, mesma EMOP por upload (que é o caminho dela: tabela paga, fora do acervo). É o
    que permite montar o mesmo orçamento pelos dois caminhos e comparar.
    """
    created = _create_round(client)
    round_id = created["round_id"]
    if sco_from_acervo:
        published = _publish_reference_catalog(client)
        sco = _install_from_acervo(
            client,
            round_id,
            reference_catalog_id=published["reference_catalog_id"],
            base_version=1,
            key="catalogo-sco-acervo",
        )
    else:
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


def _read_paths(round_id: str) -> list[str]:
    """As 10 LEITURAS de `/v1/estimate-rounds`, com rodada existente e inexistente.

    Fonte única dos dois testes de papel: uma lista por teste deixaria o teste do papel novo
    cobrir menos rotas que o antigo sem ninguém perceber, que é exatamente como uma rota
    escapa de um portão.
    """
    ghost = uuid4()
    return [
        "/v1/estimate-rounds",
        f"/v1/estimate-rounds/{round_id}",
        f"/v1/estimate-rounds/{ghost}",
        f"/v1/estimate-rounds/{round_id}/reference-catalogs",
        f"/v1/estimate-rounds/{ghost}/reference-catalogs",
        f"/v1/estimate-rounds/{round_id}/plate",
        f"/v1/estimate-rounds/{round_id}/takeoff",
        f"/v1/estimate-rounds/{round_id}/takeoff/overlay",
        f"/v1/estimate-rounds/{round_id}/code-suggestions",
        f"/v1/estimate-rounds/{round_id}/catalog/search?q=alambrado",
        f"/v1/estimate-rounds/{round_id}/code-assignments",
        f"/v1/estimate-rounds/{round_id}/estimate",
    ]


def _write_paths(round_id: str) -> list[tuple[str, dict[str, Any]]]:
    """As 13 MUTAÇÕES que exigem `orcamentista`, com um corpo mínimo válido de schema.

    `.../estimate/approve` fica de fora porque é a única mutação que NÃO exige este papel
    (ADR-0046, decisão 5); ela é conferida à parte em cada teste de papel.
    """
    return [
        ("/v1/estimate-rounds", _round_payload()),
        (
            f"/v1/estimate-rounds/{round_id}/catalogs",
            {"upload_id": str(uuid4()), "base_version": 1},
        ),
        (
            f"/v1/estimate-rounds/{round_id}/catalogs/order",
            {"base_version": 1, "cascade": ["a" * 64]},
        ),
        (
            f"/v1/estimate-rounds/{round_id}/catalogs/remove",
            {"base_version": 1, "source_sha256": "a" * 64},
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
        (f"/v1/estimate-rounds/{round_id}/estimate/export", {"base_version": 1}),
        (
            f"/v1/estimate-rounds/{round_id}/target",
            {"base_version": 1, "target_amount": "10000.00"},
        ),
        (
            f"/v1/estimate-rounds/{round_id}/regime",
            {"base_version": 1, "pricing_regime": "contracted_demand"},
        ),
    ]


def _template(path: str, round_id: str) -> str:
    """`/v1/estimate-rounds/<uuid>/estimate` -> `/v1/estimate-rounds/{round_id}/estimate`."""
    segments = []
    for segment in path.split("?", 1)[0].split("/"):
        try:
            UUID(segment)
        except ValueError:
            segments.append(segment)
        else:
            segments.append("{round_id}")
    return "/".join(segments)


def test_os_testes_de_papel_percorrem_toda_a_superficie_de_estimate_rounds(
    tmp_path: Path,
) -> None:
    """Drift guard dos dois testes de papel: rota nova entra nas listas, ou este teste cai.

    Sem ele, uma rota acrescentada depois nasceria fora dos dois testes e ninguém veria: o
    portão dela não seria conferido nem para quem não tem papel nenhum, nem para o
    `aprovador`. É o mesmo mecanismo de `unclassified_v1_paths` em `journeys.py` — cobrar a
    classificação em vez de confiar em quem escreve a rota lembrar da lista.
    """
    client = _client(tmp_path)
    round_id = str(new_uuid7())
    exposed = {
        (method, route.path)
        for route in cast(Any, client.app).routes
        if getattr(route, "path", "").startswith("/v1/estimate-rounds")
        for method in getattr(route, "methods", set())
    }

    covered = {("GET", _template(path, round_id)) for path in _read_paths(round_id)}
    covered |= {("POST", _template(path, round_id)) for path, _ in _write_paths(round_id)}
    # A única mutação fora de `_write_paths`, porque é a única que não exige `orcamentista`.
    covered.add(("POST", "/v1/estimate-rounds/{round_id}/estimate/approve"))

    assert exposed == covered


def test_sem_o_papel_toda_rota_recusa_antes_do_lookup(tmp_path: Path) -> None:
    """`403` inclusive na LEITURA e inclusive para rodada inexistente.

    É o que impede alguém sem o papel de descobrir, pela diferença entre `403` e `404`, o
    que existe no tenant vizinho.
    """
    client = _client(tmp_path)
    created = _create_round(client)
    round_id = created["round_id"]
    headers = _headers(roles="engineer", key="sem-papel")

    for path in _read_paths(round_id):
        response = client.get(path, headers=headers)
        assert response.status_code == 403, path
        assert response.json()["detail"]["code"] == "FORBIDDEN", path

    for path, payload in _write_paths(round_id):
        response = client.post(path, headers=headers, json=payload)
        assert response.status_code == 403, path
        assert response.json()["detail"]["code"] == "FORBIDDEN", path

    aprovacao = client.post(
        f"/v1/estimate-rounds/{round_id}/estimate/approve",
        headers=headers,
        json={"base_version": 1},
    )
    assert aprovacao.status_code == 403
    assert aprovacao.json()["detail"]["code"] == "FORBIDDEN"


def test_com_so_o_papel_aprovador_a_leitura_passa_e_toda_mutacao_recusa(tmp_path: Path) -> None:
    """Critério 6 da F-035, e o maior risco da entrega: dar leitura sem afrouxar mutação.

    O aprovador precisa ABRIR a jornada para ver o que assina (ADR-0046, decisão 5) — mas
    ler não é mutar. Este teste percorre as MESMAS 22 rotas do irmão acima mais as duas que a
    F-035 acrescentou, e é ele que reprova se uma mutação passar a aceitar o papel novo por
    engano. `.../estimate/approve` é a única exceção, e recusa aqui por outra causa: sem
    orçamento montado, ela é ordem da cadeia (`409`), nunca `403`.
    """
    client = _client(tmp_path)
    created = _create_round(client)
    round_id = created["round_id"]
    headers = _headers(roles=_APPROVER_ROLES, key="so-aprovador", subject=_APPROVER_SUBJECT)

    for path in _read_paths(round_id):
        response = client.get(path, headers=headers)
        assert response.status_code != 403, path
        assert response.status_code in {200, 404, 409, 422}, (path, response.text)

    for path, payload in _write_paths(round_id):
        response = client.post(path, headers=headers, json=payload)
        assert response.status_code == 403, path
        assert response.json()["detail"]["code"] == "FORBIDDEN", path

    aprovacao = client.post(
        f"/v1/estimate-rounds/{round_id}/estimate/approve",
        headers=headers,
        json={"base_version": 1},
    )
    assert aprovacao.status_code == 409, aprovacao.text
    assert aprovacao.json()["detail"]["code"] == "ROUND_STAGE_NOT_READY"


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
    regime = client.post(
        f"/v1/estimate-rounds/{created['round_id']}/regime",
        headers=headers,
        json={"base_version": 1, "pricing_regime": "contracted_demand"},
    )

    for response in (criacao, orcamento, teto, regime):
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


def test_listagem_mostra_regime_declarado_ausencia_e_pre_licitacao(tmp_path: Path) -> None:
    """A listagem devolve `pricing_regime` cru; ausência é a pré-licitação, sem valor inventado.

    O regime está na raiz da rodada (ADR-0045), então sai sem buscar a cabeça de cada
    rodada — a mesma razão pela qual `target_amount`/`target_label` não custam consulta
    extra.
    """
    client = _client(tmp_path)
    com_regime = _create_round(
        client,
        key="rodada-com-regime",
        worksite_key="praca-sintetica-com-regime",
        pricing_regime="contracted_demand",
    )
    sem_regime = _create_round(
        client, key="rodada-sem-regime", worksite_key="praca-sintetica-sem-regime"
    )

    listagem = client.get("/v1/estimate-rounds", headers=_headers(key="listagem-regime"))

    assert listagem.status_code == 200, listagem.text
    items = {item["round_id"]: item for item in listagem.json()["items"]}
    com_regime_item = items[com_regime["round_id"]]
    assert com_regime_item["pricing_regime"] == "contracted_demand"
    sem_regime_item = items[sem_regime["round_id"]]
    assert sem_regime_item["pricing_regime"] is None


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


# --- regime de preço da rodada (ADR-0045) ------------------------------------------------


def _set_regime(
    client: TestClient,
    round_id: str,
    *,
    base_version: int,
    pricing_regime: str = "contracted_demand",
    key: str,
    tenant: str = _TENANT,
) -> Any:
    return client.post(
        f"/v1/estimate-rounds/{round_id}/regime",
        headers=_headers(tenant, key=key),
        json={"base_version": base_version, "pricing_regime": pricing_regime},
    )


def _round_under_contract(client: TestClient) -> dict[str, Any]:
    """Rodada declarada sob contrato na ABERTURA, com a única fonte que ela aceita.

    A cascata é montada pela rota, e não por escrita direta: é a instalação que o regime
    restringe, e usá-la aqui prova que `sco` continua entrando por onde sempre entrou.
    """
    created = _create_round(client, pricing_regime="contracted_demand")
    round_id = created["round_id"]
    sco = _install_catalog(client, round_id, origin=PriceOrigin.SCO, base_version=1)
    assert sco.status_code == 201, sco.text
    return {
        "round_id": round_id,
        "version": sco.json()["version"],
        "cascade": sco.json()["cascade"],
    }


def test_criar_rodada_sob_contrato_o_estado_devolve_o_bloco_do_regime(tmp_path: Path) -> None:
    client = _client(tmp_path)

    created = _create_round(client, pricing_regime="contracted_demand")

    state = client.get(
        f"/v1/estimate-rounds/{created['round_id']}", headers=_headers(key="estado-regime")
    )
    assert state.status_code == 200, state.text
    assert state.json()["regime"] == {
        "value": "contracted_demand",
        "allowed_cascade_origins": ["sco"],
        # Sem decisão de código ainda: candidato a aditivo nasce da rejeição, e não houve.
        "amendment_candidates": 0,
    }
    with _database(client).sessions() as session:
        record = session.get(EstimateRoundRecord, created["round_id"])
        assert record is not None
        assert record.pricing_regime == "contracted_demand"
        assert record.version == 1


def test_rodada_sem_regime_nao_ganha_o_bloco_nem_com_orcamento_montado(tmp_path: Path) -> None:
    """Ausência não é um valor: nenhuma chave nova aparece na jornada de sempre.

    O cenário é o caminho feliz INTEIRO da F-020 — duas fontes, dois itens decididos e o
    orçamento montado —, porque é ele que esta feature não pode ter mudado.
    """
    client = _client(tmp_path)
    state = _round_ready_for_estimate(client)
    montagem = client.post(
        f"/v1/estimate-rounds/{state['round_id']}/estimate",
        headers=_headers(key="montagem-sem-regime"),
        json={"base_version": state["version"], "bdi_percent": "25.00"},
    )
    assert montagem.status_code == 200, montagem.text

    leitura = client.get(
        f"/v1/estimate-rounds/{state['round_id']}", headers=_headers(key="estado-sem-regime")
    )
    assert leitura.status_code == 200, leitura.text
    assert "regime" not in leitura.json()
    with _database(client).sessions() as session:
        record = session.get(EstimateRoundRecord, state["round_id"])
        assert record is not None
        assert record.pricing_regime is None


def test_declarar_o_regime_depois_da_criacao(tmp_path: Path) -> None:
    client = _client(tmp_path)
    created = _create_round(client)
    round_id = created["round_id"]

    response = _set_regime(client, round_id, base_version=1, key="declarar-regime")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["round_id"] == round_id
    assert body["version"] == 2
    assert body["regime"]["value"] == "contracted_demand"
    assert body["regime"]["allowed_cascade_origins"] == ["sco"]
    with _database(client).sessions() as session:
        record = session.get(EstimateRoundRecord, round_id)
        assert record is not None
        assert record.pricing_regime == "contracted_demand"
        assert record.version == 2
    # O regime é parâmetro da RODADA, como o teto: nenhuma revisão append-only nasce dele.
    assert _revisions(client) == []


def test_declarar_o_regime_com_cascata_limpa_e_possivel_depois_da_instalacao(
    tmp_path: Path,
) -> None:
    """Cascata só com `sco` já instalada não impede a declaração — não há o que remover."""
    client = _client(tmp_path)
    created = _create_round(client)
    round_id = created["round_id"]
    sco = _install_catalog(client, round_id, origin=PriceOrigin.SCO, base_version=1)
    assert sco.status_code == 201, sco.text

    response = _set_regime(client, round_id, base_version=2, key="declarar-com-sco")

    assert response.status_code == 200, response.text
    assert response.json()["regime"]["value"] == "contracted_demand"


def test_declarar_com_cascata_suja_recusa_sem_gravar_nada(tmp_path: Path) -> None:
    """Fonte proibida instalada recusa a declaração; nada é reescrito e nada é limpo.

    É a decisão 4 do ADR-0045: a alternativa aceita deixaria existir rodada "sob contrato"
    com EMOP dentro, que é exatamente o estado que a feature torna impossível.
    """
    client = _client(tmp_path)
    created = _create_round(client)
    round_id = created["round_id"]
    assert _install_catalog(client, round_id, origin=PriceOrigin.SCO, base_version=1).status_code
    emop = _install_catalog(client, round_id, origin=PriceOrigin.EMOP, base_version=2)
    assert emop.status_code == 201, emop.text

    response = _set_regime(client, round_id, base_version=3, key="declarar-suja")

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "ESTIMATE_REGIME_CASCADE_DIRTY"
    assert detail["details"]["origins"] == ["emop"]
    with _database(client).sessions() as session:
        record = session.get(EstimateRoundRecord, round_id)
        assert record is not None
        assert record.pricing_regime is None
        assert record.version == 3
        assert [entry["origin"] for entry in record.catalog_cascade_json] == ["sco", "emop"]


def test_declarar_depois_de_remover_a_fonte_proibida_e_possivel(tmp_path: Path) -> None:
    """A saída da cascata suja é a rota de remoção que já existe, e ela basta."""
    client = _client(tmp_path)
    created = _create_round(client)
    round_id = created["round_id"]
    assert _install_catalog(client, round_id, origin=PriceOrigin.SCO, base_version=1).status_code
    emop = _install_catalog(client, round_id, origin=PriceOrigin.EMOP, base_version=2)
    assert emop.status_code == 201, emop.text
    emop_digest = next(
        entry["source_sha256"] for entry in emop.json()["cascade"] if entry["origin"] == "emop"
    )

    removed = client.post(
        f"/v1/estimate-rounds/{round_id}/catalogs/remove",
        headers=_headers(key="remover-emop"),
        json={"base_version": 3, "source_sha256": emop_digest},
    )
    assert removed.status_code == 200, removed.text
    response = _set_regime(
        client, round_id, base_version=removed.json()["version"], key="declarar-limpa"
    )

    assert response.status_code == 200, response.text
    assert response.json()["regime"]["value"] == "contracted_demand"


def test_voltar_para_pre_licitacao_recusa_com_codigo_proprio(tmp_path: Path) -> None:
    """Mão única: nem a rodada declarada volta, nem a sem regime "declara pré-licitação"."""
    client = _client(tmp_path)
    declarada = _create_round(client, key="rodada-declarada", pricing_regime="contracted_demand")
    sem_regime = _create_round(client, key="rodada-sem-regime", worksite_key="praca-sintetica-sul")

    volta = _set_regime(
        client,
        declarada["round_id"],
        base_version=1,
        pricing_regime="pre_bid",
        key="voltar-declarada",
    )
    nunca = _set_regime(
        client,
        sem_regime["round_id"],
        base_version=1,
        pricing_regime="pre_bid",
        key="voltar-sem-regime",
    )

    for response, current in ((volta, "contracted_demand"), (nunca, None)):
        assert response.status_code == 409, response.text
        detail = response.json()["detail"]
        assert detail["code"] == "ESTIMATE_REGIME_IRREVERSIBLE"
        assert detail["details"] == {"requested_regime": "pre_bid", "current_regime": current}
    with _database(client).sessions() as session:
        for round_id, regime in (
            (declarada["round_id"], "contracted_demand"),
            (sem_regime["round_id"], None),
        ):
            record = session.get(EstimateRoundRecord, round_id)
            assert record is not None
            assert record.pricing_regime == regime
            assert record.version == 1


def test_criar_rodada_declarando_pre_licitacao_recusa_na_criacao(tmp_path: Path) -> None:
    client = _client(tmp_path)

    response = client.post(
        "/v1/estimate-rounds",
        headers=_headers(key="criacao-pre-licitacao"),
        json=_round_payload(pricing_regime="pre_bid"),
    )

    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "ESTIMATE_REGIME_IRREVERSIBLE"
    with _database(client).sessions() as session:
        assert session.scalars(select(EstimateRoundRecord)).all() == []


def test_regime_com_base_version_velho_recusa_sem_gravar_nada(tmp_path: Path) -> None:
    client = _client(tmp_path)
    created = _create_round(client)
    round_id = created["round_id"]
    teto = _set_target(client, round_id, base_version=1, target_amount="10000.00", key="teto-antes")
    assert teto.status_code == 200, teto.text

    stale = _set_regime(client, round_id, base_version=1, key="regime-velho")

    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "REVISION_CONFLICT"
    with _database(client).sessions() as session:
        record = session.get(EstimateRoundRecord, round_id)
        assert record is not None
        assert record.pricing_regime is None
        assert record.version == 2


def test_sob_o_regime_so_a_tabela_contratual_instala(tmp_path: Path) -> None:
    """`sco` entra; as quatro outras origens recusam na INSTALAÇÃO e a cascata não muda.

    A recusa acontece aqui, e não na montagem, porque é aqui que ainda há o que corrigir:
    do outro lado, o preço só seria recusado na medição, sobre serviço já executado.
    """
    client = _client(tmp_path)
    state = _round_under_contract(client)
    round_id = state["round_id"]
    version = state["version"]

    for origin in (
        PriceOrigin.EMOP,
        PriceOrigin.SINAPI,
        PriceOrigin.SICRO,
        PriceOrigin.COMPOSITION,
    ):
        response = _install_catalog(
            client, round_id, origin=origin, base_version=version, unit_price="40.00"
        )
        assert response.status_code == 409, (origin, response.text)
        detail = response.json()["detail"]
        assert detail["code"] == "ESTIMATE_CASCADE_ORIGIN_FORBIDDEN", origin
        assert detail["details"] == {
            "origin": origin.value,
            "allowed_origins": ["sco"],
        }, origin
    with _database(client).sessions() as session:
        record = session.get(EstimateRoundRecord, round_id)
        assert record is not None
        assert [entry["origin"] for entry in record.catalog_cascade_json] == ["sco"]
        assert record.version == version


def test_sem_regime_a_cascata_continua_livre(tmp_path: Path) -> None:
    """O contra-exemplo do teste acima: sem declaração, `emop` instala como sempre."""
    client = _client(tmp_path)
    created = _create_round(client)
    round_id = created["round_id"]
    assert _install_catalog(client, round_id, origin=PriceOrigin.SCO, base_version=1).status_code

    response = _install_catalog(
        client, round_id, origin=PriceOrigin.EMOP, base_version=2, unit_price="40.00"
    )

    assert response.status_code == 201, response.text
    assert [entry["origin"] for entry in response.json()["cascade"]] == ["sco", "emop"]


def test_item_rejeitado_sob_o_regime_e_candidato_a_aditivo(tmp_path: Path) -> None:
    """O sinal vem da REJEIÇÃO da orçamentista, e é o mesmo número de `codes.rejected`.

    Nenhum artefato novo nasce disso: sob contrato, item cuja confirmação de código foi
    rejeitada é candidato a aditivo (ADR-0045, decisão 5). O que o produto afirma é que a
    orçamentista não achou código na tabela contratual — nunca que o item não existe no
    contrato, que o orçamento não modela.
    """
    client = _client(tmp_path)
    state = _round_under_contract(client)
    round_id = state["round_id"]
    published = _publish_takeoff(
        client,
        round_id,
        _takeoff_packet([_takeoff_item(_ITEM_FIRST), _takeoff_item(_ITEM_SECOND)]),
    )
    version = published["version"]
    for index, item_id in enumerate((_ITEM_FIRST, _ITEM_SECOND), start=1):
        decided = _confirm_takeoff_item(
            client, round_id, item_id=item_id, base_version=version, key=f"regime-takeoff-{index}"
        )
        assert decided.status_code == 200, decided.text
        version = decided.json()["version"]
    confirmado = _confirm_code(
        client,
        round_id,
        item_id=_ITEM_FIRST,
        code=_SCO_CODE,
        catalog_sha256=state["cascade"][0]["source_sha256"],
        base_version=version,
        key="regime-decisao-sco",
    )
    assert confirmado.status_code == 200, confirmado.text

    rejeitado = client.post(
        f"/v1/estimate-rounds/{round_id}/code-assignments/decisions",
        headers=_headers(key="regime-decisao-rejeicao"),
        json={
            "base_version": confirmado.json()["version"],
            "item_id": _ITEM_SECOND,
            "action": "reject",
            "note": "sem código na tabela contratual para este serviço",
        },
    )

    assert rejeitado.status_code == 200, rejeitado.text
    leitura = client.get(
        f"/v1/estimate-rounds/{round_id}", headers=_headers(key="estado-candidato")
    )
    assert leitura.status_code == 200, leitura.text
    body = leitura.json()
    assert body["codes"]["rejected"] == 1
    assert body["codes"]["confirmed"] == 1
    # O mesmo número, lido sob o regime: candidato a aditivo é a leitura, não um artefato.
    assert body["regime"]["amendment_candidates"] == 1


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


# --- remoção da cascata (T7) --------------------------------------------------------------


def test_remocao_encolhe_a_cascata_e_avanca_a_versao(tmp_path: Path) -> None:
    client = _client(tmp_path)
    created = _create_round(client)
    round_id = created["round_id"]
    sco = _install_catalog(client, round_id, origin=PriceOrigin.SCO, base_version=1)
    assert sco.status_code == 201, sco.text
    emop = _install_catalog(client, round_id, origin=PriceOrigin.EMOP, base_version=2)
    assert emop.status_code == 201, emop.text
    sco_sha256 = sco.json()["cascade"][0]["source_sha256"]

    response = client.post(
        f"/v1/estimate-rounds/{round_id}/catalogs/remove",
        headers=_headers(key="remocao-sco"),
        json={"base_version": 3, "source_sha256": sco_sha256},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["version"] == 4
    assert [entry["origin"] for entry in body["cascade"]] == ["emop"]
    assert [entry["position"] for entry in body["cascade"]] == [1]
    with _database(client).sessions() as session:
        record = session.get(EstimateRoundRecord, round_id)
        assert record is not None
        assert [entry["origin"] for entry in record.catalog_cascade_json] == ["emop"]
        assert record.version == 4


def test_remocao_sem_idempotency_key_recusa(tmp_path: Path) -> None:
    client = _client(tmp_path)
    state = _round_with_cascade_and_takeoff(client)
    digests = [entry["source_sha256"] for entry in state["cascade"]]
    headers = _headers(key="remocao-sem-chave")
    headers.pop("Idempotency-Key")

    response = client.post(
        f"/v1/estimate-rounds/{state['round_id']}/catalogs/remove",
        headers=headers,
        json={"base_version": state["version"], "source_sha256": digests[0]},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"


def test_remocao_com_base_version_velha_recusa(tmp_path: Path) -> None:
    client = _client(tmp_path)
    state = _round_with_cascade_and_takeoff(client)
    digests = [entry["source_sha256"] for entry in state["cascade"]]

    response = client.post(
        f"/v1/estimate-rounds/{state['round_id']}/catalogs/remove",
        headers=_headers(key="remocao-versao-velha"),
        json={"base_version": 1, "source_sha256": digests[0]},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "REVISION_CONFLICT"


def test_remocao_de_digest_desconhecido_recusa(tmp_path: Path) -> None:
    client = _client(tmp_path)
    state = _round_with_cascade_and_takeoff(client)

    response = client.post(
        f"/v1/estimate-rounds/{state['round_id']}/catalogs/remove",
        headers=_headers(key="remocao-digest-desconhecido"),
        json={"base_version": state["version"], "source_sha256": "f" * 64},
    )

    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "ESTIMATE_CASCADE_ORDER_INVALID"


def test_remocao_de_fonte_citada_por_decisao_recusa(tmp_path: Path) -> None:
    """Recusa por FONTE: só a citada trava, e não a cascata inteira (ao contrário da ordem)."""
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
        key="decisao-remocao-1",
    )
    assert decided.status_code == 200, decided.text

    response = client.post(
        f"/v1/estimate-rounds/{round_id}/catalogs/remove",
        headers=_headers(key="remocao-tarde"),
        json={"base_version": decided.json()["version"], "source_sha256": digests[0]},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ESTIMATE_CASCADE_LOCKED"
    with _database(client).sessions() as session:
        record = session.get(EstimateRoundRecord, round_id)
        assert record is not None
        assert [entry["origin"] for entry in record.catalog_cascade_json] == ["sco", "emop"]


def test_remocao_de_fonte_nao_citada_e_permitida_mesmo_com_decisao_registrada(
    tmp_path: Path,
) -> None:
    """A trava é por fonte: remover a que NENHUMA decisão citou não é recusada."""
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
        key="decisao-remocao-2",
    )
    assert decided.status_code == 200, decided.text

    response = client.post(
        f"/v1/estimate-rounds/{round_id}/catalogs/remove",
        headers=_headers(key="remocao-nao-citada"),
        json={"base_version": decided.json()["version"], "source_sha256": digests[1]},
    )

    assert response.status_code == 200, response.text
    assert [entry["origin"] for entry in response.json()["cascade"]] == ["sco"]


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


def _estimate_documents(client: TestClient) -> list[dict[str, Any]]:
    """Os `estimate_json` gravados na cadeia, na ordem em que nasceram."""
    return [
        document
        for revision in _revisions(client)
        if isinstance(document := revision.estimate_json, dict)
    ]


def _round_ready_for_estimate(
    client: TestClient, *, sco_from_acervo: bool = False
) -> dict[str, Any]:
    """Rodada com duas fontes, dois itens confirmados e um código por fonte.

    Um item por origem é o que faz a proveniência do orçamentista aparecer em NÚMERO: os
    dois catálogos precificam diferente, e o total só fecha se cada linha tiver usado o
    preço da fonte que a decisão citou.
    """
    packet = _takeoff_packet([_takeoff_item(_ITEM_FIRST), _takeoff_item(_ITEM_SECOND)])
    state = _round_with_cascade_and_takeoff(
        client, packet, confirm=(_ITEM_FIRST, _ITEM_SECOND), sco_from_acervo=sco_from_acervo
    )
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


def _build_estimate(
    client: TestClient, round_id: str, *, base_version: int, key: str, bdi: str = "25.00"
) -> Any:
    return client.post(
        f"/v1/estimate-rounds/{round_id}/estimate",
        headers=_headers(key=key),
        json={"base_version": base_version, "bdi_percent": bdi},
    )


def _approve_estimate(
    client: TestClient,
    round_id: str,
    *,
    base_version: int,
    key: str,
    subject: str = _APPROVER_SUBJECT,
    roles: str = _APPROVER_ROLES,
) -> Any:
    return client.post(
        f"/v1/estimate-rounds/{round_id}/estimate/approve",
        headers=_headers(roles=roles, key=key, subject=subject),
        json={"base_version": base_version},
    )


def _export_estimate(client: TestClient, round_id: str, *, base_version: int, key: str) -> Any:
    return client.post(
        f"/v1/estimate-rounds/{round_id}/estimate/export",
        headers=_headers(key=key),
        json={"base_version": base_version},
    )


def test_montar_grava_o_orcamento_e_nao_publica_planilha_nenhuma(tmp_path: Path) -> None:
    """A quebra declarada da F-035: montar deixou de despachar.

    Um orçamento não nasce mais despachável — é esse instante, entre pronto e publicado, que
    a aprovação nominal existe para ocupar.
    """
    client = _client(tmp_path)
    state = _round_ready_for_estimate(client)
    round_id = state["round_id"]
    objects_before = set(_store(client).objects)

    response = _build_estimate(client, round_id, base_version=state["version"], key="montagem")

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
    assert body["workbook_present"] is False
    assert body["approval"]["approved"] is False
    assert body["approval"]["stale"] is False
    # Nada foi ao object store, e a resposta guardada na idempotência não carrega URL.
    assert set(_store(client).objects) == objects_before
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
    assert estimate_rounds.ESTIMATE_WORKBOOK_REF not in revisions[0].artifact_refs_json
    # Quem montou fica gravado em coluna própria: `created_by` é de quem fez o ÚLTIMO ato.
    assert revisions[0].estimate_built_by == _BUILDER_SUBJECT

    leitura = client.get(
        f"/v1/estimate-rounds/{round_id}/estimate", headers=_headers(key="leitura")
    )
    assert leitura.status_code == 200, leitura.text
    assert leitura.json()["workbook_url"] is None


def test_a_cadeia_completa_monta_assina_e_so_entao_publica(tmp_path: Path) -> None:
    """Montar → assinar → despachar, e a planilha só existe depois do terceiro ato."""
    client = _client(tmp_path)
    state = _round_ready_for_estimate(client)
    round_id = state["round_id"]

    montagem = _build_estimate(client, round_id, base_version=state["version"], key="montagem")
    assert montagem.status_code == 200, montagem.text

    assinatura = _approve_estimate(
        client, round_id, base_version=montagem.json()["version"], key="assinatura"
    )
    assert assinatura.status_code == 200, assinatura.text
    approval = assinatura.json()["approval"]
    assert approval["approved"] is True
    assert approval["approved_by"] == _APPROVER_SUBJECT
    assert approval["stale"] is False
    assert approval["approved_digest"] == approval["current_digest"]
    # Assinar não muda o que foi assinado: o digest do conteúdo é o mesmo de antes do ato.
    assert approval["current_digest"] == montagem.json()["approval"]["current_digest"]
    assert assinatura.json()["workbook_present"] is False

    despacho = _export_estimate(
        client, round_id, base_version=assinatura.json()["version"], key="despacho"
    )
    assert despacho.status_code == 200, despacho.text
    assert despacho.json()["workbook_present"] is True
    assert "workbook_url" not in despacho.json()

    revisions = _revisions_with(client, "estimate_json")
    assert [revision.estimate_built_by for revision in revisions] == [_BUILDER_SUBJECT] * 3
    head = revisions[-1]
    object_key = head.artifact_refs_json[estimate_rounds.ESTIMATE_WORKBOOK_REF]
    assert object_key.startswith(f"tenants/{_TENANT}/estimate-rounds/{round_id}/estimate/")
    # O endereço é o `content_digest()` — que exclui a aprovação —, e não o digest do
    # documento gravado: assinar não pode mudar o endereço da planilha do que foi assinado.
    assert object_key.endswith(f"/{approval['current_digest']}.xlsx")
    published = _store(client).objects[object_key]
    assert published.content_type == estimate_rounds.ESTIMATE_WORKBOOK_CONTENT_TYPE
    assert (
        hashlib.sha256(published.body).hexdigest()
        == head.artifact_digests_json[estimate_rounds.ESTIMATE_WORKBOOK_DIGEST]
    )

    leitura = client.get(
        f"/v1/estimate-rounds/{round_id}/estimate", headers=_headers(key="leitura-final")
    )
    assert leitura.status_code == 200, leitura.text
    assert leitura.json()["workbook_url"] == f"https://storage.invalid/{object_key}?temporary=true"
    assert leitura.json()["total_amount"] == "1125.00"

    with _database(client).sessions() as session:
        audits = session.scalars(
            select(AuditRecord).where(AuditRecord.resource_type == "estimate_round")
        ).all()
        assert [audit.action for audit in audits][-3:] == [
            "ESTIMATE_BUILT",
            "ESTIMATE_APPROVED",
            "ESTIMATE_WORKBOOK_EXPORTED",
        ]
        # URL assinada nunca entra em auditoria.
        assert all("storage.invalid" not in str(audit.metadata_json) for audit in audits)


def test_despachar_sem_assinatura_recusa_e_nao_escreve_nada(tmp_path: Path) -> None:
    """Critério 2 da F-035: o portão do DOMÍNIO corre antes de qualquer escrita.

    Sem ele, o CLI exigiria assinatura e a rota não, e passariam a existir duas verdades
    sobre o mesmo artefato.
    """
    client = _client(tmp_path)
    state = _round_ready_for_estimate(client)
    round_id = state["round_id"]
    montagem = _build_estimate(client, round_id, base_version=state["version"], key="montagem")
    assert montagem.status_code == 200, montagem.text
    objects_before = set(_store(client).objects)

    response = _export_estimate(
        client, round_id, base_version=montagem.json()["version"], key="despacho-sem-assinar"
    )

    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "DOMAIN_VALIDATION_FAILED"
    assert detail["details"]["code"] == "ESTIMATE_EXPORT_BLOCKED"
    assert detail["details"]["errors"] == ["ESTIMATE_NOT_APPROVED"]
    assert set(_store(client).objects) == objects_before
    with _database(client).sessions() as session:
        record = session.get(EstimateRoundRecord, round_id)
        assert record is not None
        assert record.version == montagem.json()["version"]


def test_quem_montou_nao_assina_nem_acumulando_os_dois_papeis(tmp_path: Path) -> None:
    """Critério 3 da F-035, sem molde na medição: a segregação compara IDENTIDADE.

    Se ela comparasse papel, bastaria atribuir os dois a uma pessoa para a segregação
    evaporar sem deixar rastro — e o papel novo seria cerimônia.
    """
    client = _client(tmp_path)
    state = _round_ready_for_estimate(client)
    round_id = state["round_id"]
    montagem = _build_estimate(client, round_id, base_version=state["version"], key="montagem")
    assert montagem.status_code == 200, montagem.text
    base_version = montagem.json()["version"]

    response = _approve_estimate(
        client,
        round_id,
        base_version=base_version,
        key="auto-aprovacao",
        subject=_BUILDER_SUBJECT,
        roles=_BOTH_ROLES,
    )

    assert response.status_code == 403, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "ESTIMATE_SELF_APPROVAL_FORBIDDEN"
    # A recusa não devolve quem montou: seria um diretório de usuários do tenant.
    assert _BUILDER_SUBJECT not in response.text
    assert _revisions_with(client, "estimate_json")[-1].estimate_json is not None
    leitura = client.get(
        f"/v1/estimate-rounds/{round_id}/estimate", headers=_headers(key="leitura-recusa")
    )
    assert leitura.json()["approval"]["approved"] is False

    # A mesma pessoa com os dois papéis DESPACHA sem problema — o que ela não pode é assinar.
    outra = _approve_estimate(client, round_id, base_version=base_version, key="assinatura-outra")
    assert outra.status_code == 200, outra.text


def test_corpo_com_identidade_recusa_antes_de_qualquer_lookup(tmp_path: Path) -> None:
    """Critério 4 da F-035: identidade é carimbo do servidor, e `extra=forbid` a recusa."""
    client = _client(tmp_path)
    state = _round_ready_for_estimate(client)
    round_id = state["round_id"]
    montagem = _build_estimate(client, round_id, base_version=state["version"], key="montagem")
    assert montagem.status_code == 200, montagem.text

    response = client.post(
        f"/v1/estimate-rounds/{round_id}/estimate/approve",
        headers=_headers(roles=_APPROVER_ROLES, key="corpo-com-nome", subject=_APPROVER_SUBJECT),
        json={
            "base_version": montagem.json()["version"],
            "approver_id": "quem-eu-quiser",
            "decided_at": "2026-08-22T12:00:00+00:00",
        },
    )

    assert response.status_code == 422, response.text
    assert _estimate_documents(client)[-1]["approval"] is None


def test_remontar_caduca_a_assinatura_e_o_despacho_recusa_ate_ato_novo(tmp_path: Path) -> None:
    """Critério 5 da F-035: a assinatura anterior é levada adiante, caduca e legível.

    Descartá-la apagaria em silêncio o fato de que alguém assinou.
    """
    client = _client(tmp_path)
    state = _round_ready_for_estimate(client)
    round_id = state["round_id"]
    montagem = _build_estimate(client, round_id, base_version=state["version"], key="montagem")
    assinatura = _approve_estimate(
        client, round_id, base_version=montagem.json()["version"], key="assinatura"
    )
    assert assinatura.status_code == 200, assinatura.text
    assinado_em = assinatura.json()["approval"]["approved_digest"]

    remontagem = _build_estimate(
        client, round_id, base_version=assinatura.json()["version"], key="remontagem", bdi="30.00"
    )
    assert remontagem.status_code == 200, remontagem.text
    caduca = remontagem.json()["approval"]
    assert caduca["approved"] is True
    assert caduca["stale"] is True
    assert caduca["approved_by"] == _APPROVER_SUBJECT
    assert caduca["approved_digest"] == assinado_em
    assert caduca["current_digest"] != assinado_em

    despacho = _export_estimate(
        client, round_id, base_version=remontagem.json()["version"], key="despacho-caduco"
    )
    assert despacho.status_code == 422, despacho.text
    assert despacho.json()["detail"]["details"]["errors"] == ["APPROVAL_CONTENT_MISMATCH"]

    estado = client.get(f"/v1/estimate-rounds/{round_id}", headers=_headers(key="estado-caduco"))
    assert estado.json()["approval"]["stale"] is True

    de_novo = _approve_estimate(
        client, round_id, base_version=remontagem.json()["version"], key="assinatura-2"
    )
    assert de_novo.status_code == 200, de_novo.text
    assert de_novo.json()["approval"]["stale"] is False
    publicado = _export_estimate(
        client, round_id, base_version=de_novo.json()["version"], key="despacho-2"
    )
    assert publicado.status_code == 200, publicado.text
    # As duas assinaturas continuam legíveis na cadeia append-only.
    assinaturas = [
        document["approval"]["decision"]["decision_id"]
        for document in _estimate_documents(client)
        if document["approval"] is not None
    ]
    assert len(set(assinaturas)) == 2


def test_aprovar_exige_orcamento_montado_e_autor_registrado(tmp_path: Path) -> None:
    """Sem orçamento, é ordem da cadeia; sem autor gravado, não há contra quem conferir."""
    client = _client(tmp_path)
    state = _round_ready_for_estimate(client)
    round_id = state["round_id"]

    sem_orcamento = _approve_estimate(
        client, round_id, base_version=state["version"], key="assinar-sem-montar"
    )
    assert sem_orcamento.status_code == 409, sem_orcamento.text
    assert sem_orcamento.json()["detail"]["code"] == "ROUND_STAGE_NOT_READY"
    assert sem_orcamento.json()["detail"]["details"]["stage"] == "estimate"

    montagem = _build_estimate(client, round_id, base_version=state["version"], key="montagem")
    assert montagem.status_code == 200, montagem.text
    # Revisão anterior a esta feature: orçamento gravado sem registro de quem o montou.
    with _database(client).sessions() as session:
        revision = session.scalar(
            select(EstimateRoundRevisionRecord)
            .where(EstimateRoundRevisionRecord.round_id == round_id)
            .order_by(EstimateRoundRevisionRecord.version.desc())
            .limit(1)
        )
        assert revision is not None
        revision.estimate_built_by = None
        session.commit()

    sem_autor = _approve_estimate(
        client, round_id, base_version=montagem.json()["version"], key="assinar-sem-autor"
    )
    assert sem_autor.status_code == 409, sem_autor.text
    assert sem_autor.json()["detail"]["code"] == "ESTIMATE_APPROVAL_AUTHOR_UNKNOWN"


def test_o_estado_da_rodada_declara_cascata_orcamento_e_aprovacao(tmp_path: Path) -> None:
    client = _client(tmp_path)
    state = _round_ready_for_estimate(client)
    round_id = state["round_id"]

    antes = client.get(f"/v1/estimate-rounds/{round_id}", headers=_headers(key="estado-vazio"))
    assert antes.status_code == 200, antes.text
    # Sem orçamento legível, o bloco não aparece: ausência não é um valor.
    assert "approval" not in antes.json()

    montagem = _build_estimate(
        client, round_id, base_version=state["version"], key="montagem-estado"
    )
    assert montagem.status_code == 200, montagem.text

    response = client.get(f"/v1/estimate-rounds/{round_id}", headers=_headers(key="estado"))

    assert response.status_code == 200, response.text
    body = response.json()
    assert [entry["origin"] for entry in body["cascade"]] == ["sco", "emop"]
    assert body["estimate"]["present"] is True
    assert body["estimate"]["workbook_present"] is False
    assert body["approval"]["approved"] is False
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
    montagem = _build_estimate(client, round_id, base_version=state["version"], key="montagem")
    assert montagem.status_code == 200, montagem.text
    assinatura = _approve_estimate(
        client, round_id, base_version=montagem.json()["version"], key="assinatura"
    )
    assert assinatura.status_code == 200, assinatura.text
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

    response = _export_estimate(
        client, round_id, base_version=assinatura.json()["version"], key="auditoria-ruim"
    )

    assert response.status_code == 500
    detail = response.json()["detail"]
    assert detail["code"] == "ESTIMATE_WORKBOOK_AUDIT_FAILED"
    assert detail["details"]["finding_codes"] == ["CELL_VALUE_MISMATCH"]
    assert "9999.99" not in response.text and "1125.00" not in response.text
    assert set(_store(client).objects) == objects_before
    assert estimate_rounds.ESTIMATE_WORKBOOK_REF not in _revisions(client)[-1].artifact_refs_json
    with _database(client).sessions() as session:
        record = session.get(EstimateRoundRecord, round_id)
        assert record is not None
        assert record.version == assinatura.json()["version"]


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


# --- acervo de catálogos na cascata (F-037 T2, ADR-0047) ---------------------------------


def test_a_tabela_do_acervo_instala_sem_upload_e_a_cascata_declara_a_procedencia(
    tmp_path: Path,
) -> None:
    """O caminho novo inteiro: publicar uma vez, escolher da lista, instalar sem arquivo.

    A tabela é publicada por OUTRO tenant — o da plataforma — e instalada na rodada do
    cliente sem novo upload: é o que a decisão 1 do ADR-0047 significa na prática, um
    documento público que não tem dono.
    """
    client = _client(tmp_path)
    publicada = _publish_reference_catalog(client)
    created = _create_round(client)
    round_id = created["round_id"]

    escolha = _reference_catalog_options(client, round_id)
    assert escolha.status_code == 200, escolha.text
    oferecidas = escolha.json()["catalogs"]
    assert [oferecida["reference_catalog_id"] for oferecida in oferecidas] == [
        publicada["reference_catalog_id"]
    ]
    assert oferecidas[0]["display_name"] == "SCO-Rio FGV06 desonerado"
    assert oferecidas[0]["origin"] == "sco"
    assert oferecidas[0]["entry_count"] == 1
    # A identidade do operador que publicou não viaja para quem escolhe.
    assert "published_by" not in oferecidas[0]

    response = _install_from_acervo(
        client,
        round_id,
        reference_catalog_id=publicada["reference_catalog_id"],
        base_version=1,
        key="instala-acervo",
    )

    assert response.status_code == 201, response.text
    entrada = response.json()["cascade"][0]
    assert entrada["provenance"] == "reference_catalog"
    assert entrada["origin"] == "sco"
    assert entrada["source_sha256"] == publicada["source_sha256"]
    assert entrada["reference_month"] == "2026-01"
    assert entrada["summary"]["entries"] == 1
    # Nem a chave do objeto nem o identificador da linha do acervo saem para o cliente.
    assert "object_key" not in entrada and "reference_catalog_id" not in entrada
    with _database(client).sessions() as session:
        record = session.get(EstimateRoundRecord, round_id)
        assert record is not None
        gravada = record.catalog_cascade_json[0]
        assert gravada["reference_catalog_id"] == publicada["reference_catalog_id"]
        assert gravada["object_sha256"] == publicada["object_sha256"]
        # Não houve upload: o campo do outro caminho fica ausente, e não vazio.
        assert "upload_id" not in gravada


def test_a_tabela_propria_continua_instalando_como_antes(tmp_path: Path) -> None:
    """O caminho de hoje não muda: mesma entrada, com a procedência que ela sempre teve."""
    client = _client(tmp_path)
    created = _create_round(client)
    round_id = created["round_id"]

    response = _install_catalog(client, round_id, origin=PriceOrigin.EMOP, base_version=1)

    assert response.status_code == 201, response.text
    entrada = response.json()["cascade"][0]
    assert entrada["provenance"] == "tenant_upload"
    assert entrada["origin"] == "emop"
    with _database(client).sessions() as session:
        record = session.get(EstimateRoundRecord, round_id)
        assert record is not None
        gravada = record.catalog_cascade_json[0]
        assert gravada["upload_id"]
        assert "reference_catalog_id" not in gravada


def test_corpo_com_as_duas_fontes_recusa_sem_gravar_nada(tmp_path: Path) -> None:
    """Citar o acervo E o arquivo no mesmo ato é ambíguo sobre o que instalar, não sobre a
    ordem de precedência do servidor — e escolher em silêncio gravaria o que ninguém pediu.
    """
    client = _client(tmp_path)
    publicada = _publish_reference_catalog(client)
    created = _create_round(client)
    round_id = created["round_id"]
    upload = _presign_and_put(
        client,
        filename="catalogo.json",
        content_type="application/json",
        payload=_catalog_bytes(origin=PriceOrigin.SCO),
        key="upload-ambiguo",
    )

    response = client.post(
        f"/v1/estimate-rounds/{round_id}/catalogs",
        headers=_headers(key="ambiguo"),
        json={
            "upload_id": upload["upload_id"],
            "reference_catalog_id": publicada["reference_catalog_id"],
            "base_version": 1,
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "ESTIMATE_CATALOG_SOURCE_INVALID"
    with _database(client).sessions() as session:
        record = session.get(EstimateRoundRecord, round_id)
        assert record is not None
        assert record.catalog_cascade_json == []
        assert record.version == 1


def test_corpo_sem_fonte_nenhuma_recusa_com_o_mesmo_codigo(tmp_path: Path) -> None:
    client = _client(tmp_path)
    created = _create_round(client)
    round_id = created["round_id"]

    response = client.post(
        f"/v1/estimate-rounds/{round_id}/catalogs",
        headers=_headers(key="sem-fonte"),
        json={"base_version": 1},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "ESTIMATE_CATALOG_SOURCE_INVALID"
    with _database(client).sessions() as session:
        record = session.get(EstimateRoundRecord, round_id)
        assert record is not None
        assert record.catalog_cascade_json == []


def test_o_orcamento_do_acervo_e_identico_ao_do_arquivo_proprio(tmp_path: Path) -> None:
    """O critério que prova que a procedência é METADADO, e não regra nova.

    Duas rodadas, dois ambientes, o mesmo catálogo do SCO: numa ele sobe como arquivo do
    cliente, na outra vem do acervo. Cada linha do orçamento tem de sair idêntica — mesmo
    `catalog_sha256`, mesma origem de preço, mesmo total —, porque quem publicou o arquivo
    não muda o que o arquivo diz.
    """
    (tmp_path / "arquivo").mkdir()
    (tmp_path / "acervo").mkdir()
    por_arquivo = _client(tmp_path / "arquivo")
    pelo_acervo = _client(tmp_path / "acervo")
    estado_arquivo = _round_ready_for_estimate(por_arquivo)
    estado_acervo = _round_ready_for_estimate(pelo_acervo, sco_from_acervo=True)

    montagens = [
        cliente.post(
            f"/v1/estimate-rounds/{estado['round_id']}/estimate",
            headers=_headers(key="montagem-comparada"),
            json={"base_version": estado["version"], "bdi_percent": "25.00"},
        )
        for cliente, estado in (
            (por_arquivo, estado_arquivo),
            (pelo_acervo, estado_acervo),
        )
    ]

    assert [montagem.status_code for montagem in montagens] == [200, 200], [
        montagem.text for montagem in montagens
    ]
    do_arquivo, do_acervo = (montagem.json() for montagem in montagens)
    assert do_acervo["estimate"]["lines"] == do_arquivo["estimate"]["lines"]
    assert do_acervo["total_amount"] == do_arquivo["total_amount"] == "1125.00"
    # A ÚNICA diferença é quem publicou o arquivo da primeira fonte.
    assert [entry["provenance"] for entry in estado_acervo["cascade"]] == [
        "reference_catalog",
        "tenant_upload",
    ]
    assert [entry["provenance"] for entry in estado_arquivo["cascade"]] == [
        "tenant_upload",
        "tenant_upload",
    ]
    assert estado_acervo["digests"] == estado_arquivo["digests"]


def test_sob_o_regime_a_escolha_so_oferece_a_tabela_contratual(tmp_path: Path) -> None:
    """A lista filtra pelo regime no SERVIDOR, e instalar o que ele recusa segue recusando.

    Oferecer na tela uma tabela que a instalação vai recusar é oferecer uma recusa; e o
    filtro não substitui a guarda, porque quem cita o identificador direto continua sendo
    recusado pelo mesmo código de sempre.
    """
    client = _client(tmp_path)
    _publish_reference_catalog(client)
    sinapi = _publish_reference_catalog(
        client, origin=PriceOrigin.SINAPI, display_name="SINAPI 07/2026", key="acervo-sinapi"
    )
    state = _round_under_contract(client)
    round_id = state["round_id"]

    escolha = _reference_catalog_options(client, round_id)
    assert escolha.status_code == 200, escolha.text
    assert [oferecida["origin"] for oferecida in escolha.json()["catalogs"]] == ["sco"]

    response = _install_from_acervo(
        client,
        round_id,
        reference_catalog_id=sinapi["reference_catalog_id"],
        base_version=state["version"],
        key="instala-sinapi",
    )

    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "ESTIMATE_CASCADE_ORIGIN_FORBIDDEN"
    assert detail["details"] == {"origin": "sinapi", "allowed_origins": ["sco"]}


def test_sem_regime_a_escolha_oferece_todas_as_tabelas_publicadas(tmp_path: Path) -> None:
    """Contra-exemplo do filtro: sem regime declarado, a lista não esconde nada."""
    client = _client(tmp_path)
    _publish_reference_catalog(client)
    _publish_reference_catalog(
        client, origin=PriceOrigin.SINAPI, display_name="SINAPI 07/2026", key="acervo-sinapi"
    )
    created = _create_round(client)

    escolha = _reference_catalog_options(client, created["round_id"])

    assert escolha.status_code == 200, escolha.text
    assert [oferecida["origin"] for oferecida in escolha.json()["catalogs"]] == ["sco", "sinapi"]


def test_tabela_fora_de_circulacao_some_da_escolha_e_nao_instala(tmp_path: Path) -> None:
    """Retirar é parar de oferecer, não apagar — e a recusa cita o próprio código."""
    client = _client(tmp_path)
    publicada = _publish_reference_catalog(client)
    retirada = client.post(
        f"/v1/platform/reference-catalogs/{publicada['reference_catalog_id']}/withdraw",
        headers=_headers(_PLATFORM_TENANT, "platform_operator", key="retirada"),
    )
    assert retirada.status_code == 200, retirada.text
    created = _create_round(client)
    round_id = created["round_id"]

    escolha = _reference_catalog_options(client, round_id)
    assert escolha.status_code == 200, escolha.text
    assert escolha.json()["catalogs"] == []

    response = _install_from_acervo(
        client,
        round_id,
        reference_catalog_id=publicada["reference_catalog_id"],
        base_version=1,
        key="instala-retirada",
    )

    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "REFERENCE_CATALOG_WITHDRAWN"
    assert detail["details"]["reference_catalog_id"] == publicada["reference_catalog_id"]
    with _database(client).sessions() as session:
        record = session.get(EstimateRoundRecord, round_id)
        assert record is not None
        assert record.catalog_cascade_json == []


def test_tabela_inexistente_no_acervo_e_404(tmp_path: Path) -> None:
    client = _client(tmp_path)
    created = _create_round(client)

    response = _install_from_acervo(
        client,
        created["round_id"],
        reference_catalog_id=str(uuid4()),
        base_version=1,
        key="instala-fantasma",
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "NOT_FOUND"


def test_origem_repetida_recusa_igual_venha_a_fonte_de_onde_vier(tmp_path: Path) -> None:
    """Uma origem por cascata vale para o acervo: a regra é da cascata, não do caminho."""
    client = _client(tmp_path)
    publicada = _publish_reference_catalog(client)
    created = _create_round(client)
    round_id = created["round_id"]
    primeiro = _install_catalog(client, round_id, origin=PriceOrigin.SCO, base_version=1)
    assert primeiro.status_code == 201, primeiro.text

    response = _install_from_acervo(
        client,
        round_id,
        reference_catalog_id=publicada["reference_catalog_id"],
        base_version=2,
        key="instala-sco-repetida",
    )

    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "ESTIMATE_CASCADE_ORIGIN_DUPLICATE"
    with _database(client).sessions() as session:
        record = session.get(EstimateRoundRecord, round_id)
        assert record is not None
        assert len(record.catalog_cascade_json) == 1


def test_digest_de_origem_repetido_recusa_mesmo_vindo_do_acervo(tmp_path: Path) -> None:
    """A terceira recusa de `ensure_source_installable` também não conhece procedência."""
    client = _client(tmp_path)
    compartilhado = "9" * 64
    publicada = _publish_reference_catalog(
        client,
        origin=PriceOrigin.SINAPI,
        display_name="SINAPI 07/2026",
        key="acervo-sinapi",
        source_sha256=compartilhado,
    )
    created = _create_round(client)
    round_id = created["round_id"]
    primeiro = _install_catalog(
        client, round_id, origin=PriceOrigin.SCO, base_version=1, source_sha256=compartilhado
    )
    assert primeiro.status_code == 201, primeiro.text

    response = _install_from_acervo(
        client,
        round_id,
        reference_catalog_id=publicada["reference_catalog_id"],
        base_version=2,
        key="instala-digest-repetido",
    )

    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "ESTIMATE_CASCADE_ORIGIN_DUPLICATE"


def test_remover_fonte_do_acervo_citada_por_decisao_recusa_igual(tmp_path: Path) -> None:
    """A trava por decisão de código vale para a fonte do acervo, sem exceção."""
    client = _client(tmp_path)
    state = _round_with_cascade_and_takeoff(client, sco_from_acervo=True)
    round_id = state["round_id"]
    digests = [entry["source_sha256"] for entry in state["cascade"]]
    decided = _confirm_code(
        client,
        round_id,
        item_id=_ITEM_FIRST,
        code=_SCO_CODE,
        catalog_sha256=digests[0],
        base_version=state["version"],
        key="decisao-acervo",
    )
    assert decided.status_code == 200, decided.text

    response = client.post(
        f"/v1/estimate-rounds/{round_id}/catalogs/remove",
        headers=_headers(key="remocao-acervo"),
        json={"base_version": decided.json()["version"], "source_sha256": digests[0]},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ESTIMATE_CASCADE_LOCKED"


def test_reordenar_preserva_a_procedencia_de_cada_fonte(tmp_path: Path) -> None:
    """Reordenar mexe na precedência, nunca em de onde o arquivo de cada fonte veio."""
    client = _client(tmp_path)
    state = _round_with_cascade_and_takeoff(client, sco_from_acervo=True)
    round_id = state["round_id"]
    digests = [entry["source_sha256"] for entry in state["cascade"]]

    response = client.post(
        f"/v1/estimate-rounds/{round_id}/catalogs/order",
        headers=_headers(key="ordem-acervo"),
        json={"base_version": state["version"], "cascade": list(reversed(digests))},
    )

    assert response.status_code == 200, response.text
    cascade = response.json()["cascade"]
    assert [entry["origin"] for entry in cascade] == ["emop", "sco"]
    assert [entry["provenance"] for entry in cascade] == ["tenant_upload", "reference_catalog"]
    with _database(client).sessions() as session:
        record = session.get(EstimateRoundRecord, round_id)
        assert record is not None
        assert record.catalog_cascade_json[1]["reference_catalog_id"]


def test_cascata_instalada_antes_da_feature_le_como_tabela_propria(tmp_path: Path) -> None:
    """Ausência de procedência é o registro anterior à F-037, e ele continua legível.

    Nada é reescrito retroativamente: a entrada gravada sem o campo é lida como tabela
    própria, que é o que ela é — era o único caminho que existia quando ela foi instalada.
    """
    client = _client(tmp_path)
    created = _create_round(client)
    round_id = created["round_id"]
    instalada = _install_catalog(client, round_id, origin=PriceOrigin.SCO, base_version=1)
    assert instalada.status_code == 201, instalada.text
    with _database(client).sessions() as session:
        record = session.get(EstimateRoundRecord, round_id)
        assert record is not None
        legada = dict(record.catalog_cascade_json[0])
        del legada["provenance"]
        record.catalog_cascade_json = [legada]
        session.commit()

    response = client.get(f"/v1/estimate-rounds/{round_id}", headers=_headers(key="estado-legado"))

    assert response.status_code == 200, response.text
    assert [entry["provenance"] for entry in response.json()["cascade"]] == ["tenant_upload"]


def test_a_escolha_do_acervo_e_404_na_rodada_de_outro_tenant(tmp_path: Path) -> None:
    """O acervo é público; a RODADA continua sendo do tenant, e alheia é indistinguível de
    inexistente."""
    client = _client(tmp_path)
    _publish_reference_catalog(client)
    created = _create_round(client)

    response = _reference_catalog_options(
        client, created["round_id"], tenant=_OTHER_TENANT, key="escolha-alheia"
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "NOT_FOUND"


def test_procedencia_que_o_registro_nao_sustenta_recusa_a_leitura(tmp_path: Path) -> None:
    """Entrada adulterada não é lida como se estivesse certa: fail-closed na leitura.

    Ausência de procedência é o registro legítimo de antes da F-037; procedência que
    CONTRADIZ o identificador de fonte gravado é registro corrompido, e lê-lo pelo rótulo
    faria a tela mostrar `DO ACERVO` sobre um arquivo que o cliente subiu.
    """
    client = _client(tmp_path)
    created = _create_round(client)
    round_id = created["round_id"]
    instalada = _install_catalog(client, round_id, origin=PriceOrigin.SCO, base_version=1)
    assert instalada.status_code == 201, instalada.text
    with _database(client).sessions() as session:
        record = session.get(EstimateRoundRecord, round_id)
        assert record is not None
        adulterada = {**record.catalog_cascade_json[0], "provenance": "reference_catalog"}
        record.catalog_cascade_json = [adulterada]
        session.commit()

    response = client.get(f"/v1/estimate-rounds/{round_id}", headers=_headers(key="adulterada"))

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "CATALOG_REQUIRED"
