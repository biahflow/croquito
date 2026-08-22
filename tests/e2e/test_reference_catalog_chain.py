"""Acervo de catálogos da plataforma, ponta a ponta pela API `/v1` autenticada (F-037 T5).

Contraponto de `tests/api/test_estimate_round_routes.py`
(`test_o_orcamento_do_acervo_e_identico_ao_do_arquivo_proprio`): lá a equivalência entre os
dois caminhos de instalação é provada sobre uma fixture de rota, com um catálogo de duas
entradas escrito à mão e sem prancha nenhuma. Aqui a mesma afirmação — *a procedência é
metadado do gesto de instalar, não regra que muda preço* (ADR-0047 decisão 7) — é provada
sobre a cadeia REAL: prancha sintética, extração da legenda consumida pelo worker no mesmo
processo, revisão do takeoff, decisão de código citando a fonte, montagem, auditoria e
planilha publicada. É nesse caminho inteiro que ela pode falhar sem ninguém ver.

Molde estrutural: `tests/e2e/test_estimate_rounds_v1.py`, no cenário de cascata de TRÊS
fontes (`test_estimate_round_target_over_and_exact_limit_through_v1_api`). As três nascem
das MESMAS funções de domínio que os comandos `import-catalog`/`import-emop`/
`import-compositions` chamam por baixo (`read_price_catalog`,
`read_emop_catalog_with_report`, `compile_compositions`), nunca do CLI que os embrulha.

Dois testes, cada um provando um par de critérios da task:

1. `test_reference_catalog_serves_two_tenants_through_v1_api` — uma publicação ÚNICA do
   operador da plataforma atravessa a cadeia inteira de DOIS tenants diferentes, sem
   segundo upload (escopos 1 e 3), e nenhuma resposta da cadeia carrega o prefixo do
   objeto do acervo (escopo 4).
2. `test_reference_catalog_and_tenant_upload_produce_the_same_estimate` — o MESMO catálogo
   instalado pelos dois caminhos produz as mesmas linhas, os mesmos totais e a mesma
   coluna FONTE na planilha; a única diferença é a `provenance` da entrada da cascata
   (escopo 2).

O portão de ambiente da extração (`CROQUITO_AI_MAX_ESTIMATED_COST_USD` +
`CROQUITO_ANTHROPIC_API_KEY`) é freio de config, não chamada de rede: quem responde é
`legend_fixture_adapter` sobre a MESMA prancha sintética, offline. O único acesso direto ao
object store é para reler a planilha PUBLICADA — a URL assinada da fixture não é buscável
por HTTP —, exatamente como o arquivo-molde faz.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, cast

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from croquito_api.config import ApiSettings
from croquito_api.database import Database
from croquito_api.estimate_rounds import estimate_workbook_key
from croquito_api.main import create_app
from croquito_api.reference_catalogs import REFERENCE_CATALOG_PREFIX
from croquito_valuation.assignment import CodeAssignmentInput
from croquito_valuation.canonical import canonicalize_workbook
from croquito_valuation.catalog import read_price_catalog
from croquito_valuation.composition import compile_compositions
from croquito_valuation.emop import read_emop_catalog_with_report
from croquito_valuation.estimate import Estimate
from croquito_valuation.estimate_workbook import audit_estimate_workbook
from croquito_valuation.models import PriceCatalog, PriceOrigin
from croquito_valuation.takeoff import TakeoffPacket
from croquito_valuation.template import default_template
from croquito_worker.local_queue import LocalQueueWorker, LocalWorkerSettings
from croquito_worker.valuation.emop_fixture import emop_fixture_layout, write_emop_dbf
from croquito_worker.valuation.estimate_fixture import (
    SYNTHETIC_ESTIMATE_WORKSITE_NAME,
    build_demo_estimate_assignments,
    build_synthetic_composition_set,
)
from croquito_worker.valuation.legend_fixtures import legend_fixture_adapter
from croquito_worker.valuation.plate import PlateArtifacts, render_synthetic_plate
from croquito_worker.valuation.round_extraction import AI_BUDGET_ENV
from croquito_worker.valuation.synthetic import (
    SYNTHETIC_CONTRACT_SOURCE_LABEL,
    SYNTHETIC_REFERENCE_MONTH,
    build_demo_takeoff_decisions,
    build_synthetic_previous_mapao,
)
from tests.fakes import FakeObjectStore, FakeQueue

QUEUE_URL: Final = "http://localstack/queue"
BUCKET: Final = "croquito-acervo-e2e"

PLATFORM_TENANT: Final = "tenant-plataforma"
"""Quem publica no acervo. Não é o tenant de rodada nenhuma, de propósito: o acervo é dado
da PLATAFORMA (`reference_catalogs` é a única tabela sem `tenant_id`), e é isso que permite
uma publicação só servir tenants diferentes."""

TENANT_SCALLE: Final = "tenant-scalle"
TENANT_TOCA: Final = "tenant-toca"

ROLE: Final = "orcamentista"
PLATFORM_ROLE: Final = "platform_operator"
_ANTHROPIC_KEY_ENV: Final = "CROQUITO_ANTHROPIC_API_KEY"

ADDRESS: Final = "RUA SINTETICA DO ACERVO, S/N"
BDI_PERCENT: Final = "25.00"
ACERVO_DISPLAY_NAME: Final = "SCO-Rio FGV06 desonerado (acervo sintético)"


# --- montagem -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Stack:
    """API sobre SQLite em arquivo + storage/fila em memória compartilhados com o worker.

    Mesma montagem da fixture `stack` de `tests/e2e/test_estimate_rounds_v1.py`, embrulhada
    num dado em vez de numa fixture porque o segundo teste precisa de DOIS ambientes
    independentes no mesmo caso — um por caminho de instalação.
    """

    client: TestClient
    storage: FakeObjectStore
    queue: FakeQueue
    worker: LocalQueueWorker


def _build_stack(workdir: Path, *, plate: PlateArtifacts) -> _Stack:
    workdir.mkdir(parents=True, exist_ok=True)
    database_url = f"sqlite+pysqlite:///{workdir / 'acervo-chain.db'}"
    database = Database(database_url)
    database.create_schema()
    settings = ApiSettings(
        database_url=database_url,
        artifact_bucket=BUCKET,
        aws_region="sa-east-1",
        aws_endpoint_url="http://localhost:4566",
        queue_url=QUEUE_URL,
        oidc_issuer=None,
        oidc_audience=None,
        web_origin="http://localhost:5173",
        allow_test_tokens=True,
    )
    app = create_app(settings=settings, database=database)
    storage = FakeObjectStore()
    queue = FakeQueue()
    app.state.artifact_store = storage
    app.state.queue.client = queue
    worker = LocalQueueWorker(
        LocalWorkerSettings(
            database_url=database_url,
            queue_url=QUEUE_URL,
            aws_region="sa-east-1",
            aws_endpoint_url="http://localhost:4566",
            artifact_bucket=BUCKET,
        ),
        valuation_extraction_adapter=legend_fixture_adapter(plate),
    )
    worker.client = queue
    worker.s3_client = storage
    return _Stack(client=TestClient(app), storage=storage, queue=queue, worker=worker)


@dataclass(frozen=True, slots=True)
class _Cascade:
    """As três fontes de preço da rodada, construídas uma vez e instaladas em todo ambiente.

    Construir uma vez e reusar é o que torna a comparação do segundo teste conferível: os
    dois ambientes instalam BYTES idênticos, então qualquer diferença no orçamento vem do
    caminho de instalação, que é justamente a variável sob teste.
    """

    sco: PriceCatalog
    emop: PriceCatalog
    composition: PriceCatalog

    def as_sequence(self) -> list[PriceCatalog]:
        return [self.sco, self.emop, self.composition]


def _build_cascade(workdir: Path) -> _Cascade:
    workdir.mkdir(parents=True, exist_ok=True)
    template = default_template()
    sco = read_price_catalog(
        build_synthetic_previous_mapao(workdir / "previous-mapao.xlsx"),
        template,
        source_label=SYNTHETIC_CONTRACT_SOURCE_LABEL,
        reference_month=SYNTHETIC_REFERENCE_MONTH,
    )
    emop, _notes = read_emop_catalog_with_report(
        write_emop_dbf(workdir / "emop-sintetico.dbf"), emop_fixture_layout()
    )
    composition_set = build_synthetic_composition_set()
    composition = compile_compositions(
        composition_set,
        source_sha256=hashlib.sha256(composition_set.model_dump_json().encode("utf-8")).hexdigest(),
    )
    return _Cascade(sco=sco, emop=emop, composition=composition)


# --- helpers de requisição ------------------------------------------------------------------


def _headers(key: str | None = None, *, tenant: str, roles: str = ROLE) -> dict[str, str]:
    headers = {"Authorization": f"Bearer test:{tenant}:pessoa-sintetica:{roles}"}
    if key is not None:
        headers["Idempotency-Key"] = key
    return headers


def _catalog_upload_bytes(catalog: PriceCatalog) -> bytes:
    return catalog.model_dump_json().encode("utf-8")


def _presign_and_put(
    stack: _Stack,
    *,
    filename: str,
    content_type: str,
    payload: bytes,
    key: str,
    tenant: str,
) -> dict[str, Any]:
    presign = stack.client.post(
        "/v1/uploads/presign",
        headers=_headers(key, tenant=tenant),
        json={
            "filename": filename,
            "content_type": content_type,
            "size_bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        },
    )
    assert presign.status_code == 200, presign.text
    stack.storage.put_direct(
        object_key=presign.json()["object_key"], body=payload, content_type=content_type
    )
    return cast(dict[str, Any], presign.json())


def _publish_to_acervo(
    stack: _Stack, *, catalog: PriceCatalog, display_name: str, key: str
) -> Response:
    """Publica no acervo o MESMO arquivo que o upload do cliente subiria.

    O presign é o DA PLATAFORMA (`/v1/platform/reference-catalogs/presign`, F-037 T6) e não
    aceita `content_type` no corpo: o acervo publica catálogo normalizado e nada mais.
    """
    payload = _catalog_upload_bytes(catalog)
    presign = stack.client.post(
        "/v1/platform/reference-catalogs/presign",
        headers=_headers(f"presign-{key}", tenant=PLATFORM_TENANT, roles=PLATFORM_ROLE),
        json={
            "filename": "catalogo.json",
            "size_bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        },
    )
    assert presign.status_code == 200, presign.text
    stack.storage.put_direct(
        object_key=presign.json()["object_key"], body=payload, content_type="application/json"
    )
    return cast(
        Response,
        stack.client.post(
            "/v1/platform/reference-catalogs",
            headers=_headers(key, tenant=PLATFORM_TENANT, roles=PLATFORM_ROLE),
            json={"upload_id": presign.json()["upload_id"], "display_name": display_name},
        ),
    )


def _install_by_upload(
    stack: _Stack,
    round_id: str,
    *,
    catalog: PriceCatalog,
    base_version: int,
    key: str,
    tenant: str,
) -> Response:
    """Instala a tabela PRÓPRIA do cliente: o caminho que existia antes da F-037."""
    upload = _presign_and_put(
        stack,
        filename=f"catalogo-{catalog.origin.value}.json",
        content_type="application/json",
        payload=_catalog_upload_bytes(catalog),
        key=f"presign-{key}",
        tenant=tenant,
    )
    return cast(
        Response,
        stack.client.post(
            f"/v1/estimate-rounds/{round_id}/catalogs",
            headers=_headers(key, tenant=tenant),
            json={"upload_id": upload["upload_id"], "base_version": base_version},
        ),
    )


def _install_from_acervo(
    stack: _Stack,
    round_id: str,
    *,
    reference_catalog_id: str,
    base_version: int,
    key: str,
    tenant: str,
) -> Response:
    """Instala citando a tabela do acervo: nenhum arquivo sobe e nada é assinado."""
    return cast(
        Response,
        stack.client.post(
            f"/v1/estimate-rounds/{round_id}/catalogs",
            headers=_headers(key, tenant=tenant),
            json={"reference_catalog_id": reference_catalog_id, "base_version": base_version},
        ),
    )


def _packet_from_takeoff_response(body: dict[str, Any]) -> TakeoffPacket:
    """`GET .../takeoff` junta uma âncora por item (`anchored_packet`); o domínio não a
    conhece (`extra="forbid"`), então ela sai antes de revalidar o pacote."""
    document = dict(body["packet"])
    items = []
    for item in document["items"]:
        item = dict(item)
        item.pop("anchor", None)
        items.append(item)
    return TakeoffPacket.model_validate({**document, "items": items})


def _drain(worker: LocalQueueWorker) -> int:
    """Consome toda a fila corrente."""
    processed = 0
    while worker.run_once():
        processed += 1
    return processed


def _cascade_entry(cascade: list[dict[str, Any]], origin: PriceOrigin) -> dict[str, Any]:
    """A entrada da cascata de uma origem; ausência é falha de teste, não `None` silencioso."""
    for entry in cascade:
        if entry["origin"] == origin.value:
            return entry
    raise AssertionError(f"origem ausente da cascata devolvida: {origin.value}")


def _canonical_cells(canonical: dict[str, object], sheet_name: str) -> dict[str, dict[str, object]]:
    sheets = canonical["sheets"]
    assert isinstance(sheets, list)
    for sheet in sheets:
        assert isinstance(sheet, dict)
        if sheet["name"] == sheet_name:
            cells = sheet["cells"]
            assert isinstance(cells, list)
            return {str(cell["ref"]): cell for cell in cells if isinstance(cell, dict)}
    raise AssertionError(f"aba ausente no canônico: {sheet_name}")


# --- trechos da cadeia, compartilhados pelos dois testes ------------------------------------


def _plate_through_takeoff(
    stack: _Stack,
    round_id: str,
    *,
    version: int,
    tenant: str,
    prefix: str,
    plate: PlateArtifacts,
    collected: list[Response],
) -> tuple[int, TakeoffPacket]:
    """Da prancha ao takeoff revisado: sobe, extrai pela fila e decide item a item.

    Idêntico nos dois testes e nos dois tenants — é justamente por ser idêntico que ele
    isola a variável sob teste: o que muda entre os cenários é só como a cascata foi
    instalada, nunca o que aconteceu com a prancha.
    """
    plate_upload = _presign_and_put(
        stack,
        filename="prancha.pdf",
        content_type="application/pdf",
        payload=plate.pdf_path.read_bytes(),
        key=f"{prefix}-presign-prancha",
        tenant=tenant,
    )
    associated = stack.client.post(
        f"/v1/estimate-rounds/{round_id}/plate",
        headers=_headers(f"{prefix}-prancha", tenant=tenant),
        json={"upload_id": plate_upload["upload_id"], "base_version": version},
    )
    assert associated.status_code == 200, associated.text
    collected.append(associated)
    version = associated.json()["version"]

    extraction = stack.client.post(
        f"/v1/estimate-rounds/{round_id}/plate/extractions",
        headers=_headers(f"{prefix}-extracao", tenant=tenant),
        json={"base_version": version},
    )
    assert extraction.status_code == 202, extraction.text
    collected.append(extraction)

    assert _drain(stack.worker) == 1

    after_extraction = stack.client.get(
        f"/v1/estimate-rounds/{round_id}", headers=_headers(tenant=tenant)
    )
    assert after_extraction.status_code == 200, after_extraction.text
    collected.append(after_extraction)
    assert after_extraction.json()["extraction"]["status"] == "done"
    version = after_extraction.json()["version"]

    takeoff = stack.client.get(
        f"/v1/estimate-rounds/{round_id}/takeoff", headers=_headers(tenant=tenant)
    )
    assert takeoff.status_code == 200, takeoff.text
    collected.append(takeoff)
    packet = _packet_from_takeoff_response(takeoff.json())

    decisions = build_demo_takeoff_decisions(packet).decisions
    last: dict[str, Any] | None = None
    for index, decision in enumerate(decisions):
        response = stack.client.post(
            f"/v1/estimate-rounds/{round_id}/takeoff/decisions",
            headers=_headers(f"{prefix}-takeoff-{index}", tenant=tenant),
            json={
                "base_version": version,
                "item_id": decision.item_id,
                "action": decision.action,
                "quantity": None if decision.quantity is None else str(decision.quantity),
                "unit": decision.unit,
                "note": decision.note,
            },
        )
        assert response.status_code == 200, response.text
        collected.append(response)
        last = response.json()
        version = last["version"]
    assert last is not None
    assert last["review_status"] == "complete"

    assert _drain(stack.worker) == len(decisions)

    final = stack.client.get(
        f"/v1/estimate-rounds/{round_id}/takeoff", headers=_headers(tenant=tenant)
    )
    assert final.status_code == 200, final.text
    collected.append(final)
    return version, _packet_from_takeoff_response(final.json())


def _decide_codes(
    stack: _Stack,
    round_id: str,
    *,
    version: int,
    tenant: str,
    prefix: str,
    assignments: list[CodeAssignmentInput],
    collected: list[Response],
) -> int:
    """Confirma (ou rejeita) o código de cada item CITANDO o digest da fonte escolhida."""
    for index, assignment in enumerate(assignments):
        response = stack.client.post(
            f"/v1/estimate-rounds/{round_id}/code-assignments/decisions",
            headers=_headers(f"{prefix}-codigo-{index}", tenant=tenant),
            json={
                "base_version": version,
                "item_id": assignment.item_id,
                "action": assignment.action,
                "code": assignment.code,
                "catalog_sha256": assignment.catalog_sha256,
                "note": assignment.note,
            },
        )
        assert response.status_code == 200, response.text
        collected.append(response)
        version = response.json()["version"]
    return version


def _create_round(
    stack: _Stack, *, tenant: str, worksite_key: str, reference_label: str, key: str
) -> Response:
    return cast(
        Response,
        stack.client.post(
            "/v1/estimate-rounds",
            headers=_headers(key, tenant=tenant),
            json={
                "worksite_key": worksite_key,
                "worksite_name": SYNTHETIC_ESTIMATE_WORKSITE_NAME,
                "reference_label": reference_label,
                "address": ADDRESS,
            },
        ),
    )


def _published_workbook(
    stack: _Stack, *, tenant: str, round_id: str, estimate_sha256: str, workbook_sha256: str
) -> bytes:
    """Relê do object store o `.xlsx` que a rodada publicou, pela chave derivada do digest.

    É o único acesso direto ao store nestes testes, e ele é sobre um objeto de OUTRO
    prefixo: a planilha mora sob `tenants/`, é da rodada e tem URL assinada — o que a
    fixture não sabe fazer é buscá-la por HTTP.
    """
    workbook_bytes = stack.storage.body(
        estimate_workbook_key(tenant_id=tenant, round_id=round_id, estimate_sha256=estimate_sha256)
    )
    assert hashlib.sha256(workbook_bytes).hexdigest() == workbook_sha256
    return workbook_bytes


def _source_cell_of_first_sco_line(workbook_path: Path, estimate: Estimate) -> str:
    """Conteúdo da célula FONTE da primeira linha precificada pelo SCO, na planilha reaberta."""
    template = default_template()
    layout = template.estimate
    assert layout is not None
    index = next(
        position
        for position, line in enumerate(estimate.lines)
        if line.price_origin is PriceOrigin.SCO
    )
    cells = _canonical_cells(canonicalize_workbook(workbook_path, template), layout.sheet_name)
    value = cells[f"{layout.columns.source.letter}{layout.header_row + index + 1}"]["value"]
    assert isinstance(value, str)
    return value


# --- 1. uma publicação, dois tenants, nenhuma chave do acervo vazando ------------------------


def test_reference_catalog_serves_two_tenants_through_v1_api(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Uma tabela publicada UMA vez leva dois tenants diferentes até a planilha (escopos 1 e 3).

    O que este teste protege é o que a ausência de `tenant_id` em `reference_catalogs` existe
    para permitir: publicar é ato da PLATAFORMA, e a mesma publicação serve rodadas de
    clientes distintos sem novo upload. O contra-exemplo que ele impede é sutil — um acervo
    que "funciona" porque cada cliente republica o mesmo arquivo não é acervo, é upload com
    outro nome; por isso o teste termina conferindo que a listagem da plataforma continua com
    UMA linha depois de as duas cadeias terem fechado.

    Junto vem o escopo 4, que é uma recusa e não um recurso: nenhuma resposta desta cadeia —
    publicação, escolha, instalação, estado da rodada, decisões, montagem, leitura — carrega
    o prefixo do objeto do acervo. A `workbook_url` do `GET .../estimate` continua saindo, e
    é outro objeto: a planilha DESTA rodada, sob o prefixo do tenant. O que a asserção veda é
    o endereço de `platform/reference-catalogs/`, que nenhuma rota assina (ADR-0047 decisão 6).
    """
    plate = render_synthetic_plate(tmp_path / "plate-source")
    monkeypatch.setenv(AI_BUDGET_ENV, "1.50")
    monkeypatch.setenv(_ANTHROPIC_KEY_ENV, "chave-de-teste-nunca-usada")
    stack = _build_stack(tmp_path / "ambiente", plate=plate)
    cascade = _build_cascade(tmp_path / "fontes")
    collected: list[Response] = []

    # 1. O operador da plataforma publica o catálogo SCO — e é o ÚNICO upload de catálogo do
    # acervo neste teste. Tudo o que vier depois é escolha, nunca reenvio.
    publication = _publish_to_acervo(
        stack, catalog=cascade.sco, display_name=ACERVO_DISPLAY_NAME, key="publica-sco"
    )
    assert publication.status_code == 201, publication.text
    collected.append(publication)
    published = publication.json()
    reference_catalog_id = published["reference_catalog_id"]
    assert published["origin"] == "sco"
    assert published["source_sha256"] == cascade.sco.source_sha256
    assert published["available"] is True

    # 2. Cada tenant percorre a cadeia inteira sobre a MESMA publicação.
    for tenant, prefix in ((TENANT_SCALLE, "scalle"), (TENANT_TOCA, "toca")):
        created = _create_round(
            stack,
            tenant=tenant,
            worksite_key=f"praca-sintetica-acervo-{prefix}",
            reference_label=f"ORCAMENTO ACERVO {prefix.upper()} 01/2026",
            key=f"{prefix}-rodada",
        )
        assert created.status_code == 201, created.text
        collected.append(created)
        round_id = created.json()["round_id"]
        version = created.json()["version"]

        # 2a. A escolha: a tabela publicada aparece na lista desta rodada, com o mesmo
        # identificador que a publicação devolveu. É por esta rota que a orçamentista sabe
        # que existe algo para escolher — sem ela, o acervo seria um dado sem porta.
        options = stack.client.get(
            f"/v1/estimate-rounds/{round_id}/reference-catalogs", headers=_headers(tenant=tenant)
        )
        assert options.status_code == 200, options.text
        collected.append(options)
        offered = options.json()["catalogs"]
        assert [catalog["reference_catalog_id"] for catalog in offered] == [reference_catalog_id]
        assert offered[0]["display_name"] == ACERVO_DISPLAY_NAME
        assert offered[0]["source_sha256"] == cascade.sco.source_sha256

        # 2b. Instala o SCO CITANDO a tabela do acervo: nenhum arquivo sobe.
        from_acervo = _install_from_acervo(
            stack,
            round_id,
            reference_catalog_id=reference_catalog_id,
            base_version=version,
            key=f"{prefix}-instala-acervo",
            tenant=tenant,
        )
        assert from_acervo.status_code == 201, from_acervo.text
        collected.append(from_acervo)
        version = from_acervo.json()["version"]

        # 2c. EMOP e composição continuam entrando pelo upload de sempre — a EMOP é tabela
        # paga e a composição é do cliente por natureza, então a plataforma não as distribui
        # (`PUBLISHABLE_ORIGINS`). A cascata tem TRÊS fontes porque o orçamentista sintético
        # decide o gramado por composição manual: com duas, `build_demo_estimate_assignments`
        # falharia com `SYNTHETIC_CASCADE_ORIGIN_MISSING`, e enxugar o teste aqui seria
        # trocar a cadeia real por uma que a fixture não sabe decidir.
        for index, catalog in enumerate((cascade.emop, cascade.composition)):
            by_upload = _install_by_upload(
                stack,
                round_id,
                catalog=catalog,
                base_version=version,
                key=f"{prefix}-instala-upload-{index}",
                tenant=tenant,
            )
            assert by_upload.status_code == 201, by_upload.text
            collected.append(by_upload)
            version = by_upload.json()["version"]

        # 2d. A entrada do SCO declara a procedência do acervo e o digest da publicação; as
        # outras duas declaram a tabela própria. A cascata é a mesma estrutura nos dois
        # caminhos — o que muda é o fato de quem publicou o arquivo (ADR-0047 decisão 7).
        state = stack.client.get(f"/v1/estimate-rounds/{round_id}", headers=_headers(tenant=tenant))
        assert state.status_code == 200, state.text
        collected.append(state)
        cascade_payload = state.json()["cascade"]
        assert [entry["provenance"] for entry in cascade_payload] == [
            "reference_catalog",
            "tenant_upload",
            "tenant_upload",
        ]
        sco_entry = _cascade_entry(cascade_payload, PriceOrigin.SCO)
        assert sco_entry["source_sha256"] == published["source_sha256"]
        assert sco_entry["reference_month"] == published["reference_month"]

        # 2e. Prancha, extração pela fila, takeoff revisado e decisão de código.
        version, final_packet = _plate_through_takeoff(
            stack,
            round_id,
            version=version,
            tenant=tenant,
            prefix=prefix,
            plate=plate,
            collected=collected,
        )
        version = _decide_codes(
            stack,
            round_id,
            version=version,
            tenant=tenant,
            prefix=prefix,
            assignments=build_demo_estimate_assignments(
                final_packet, cascade.as_sequence()
            ).assignments,
            collected=collected,
        )

        # 2f. Monta, audita e publica a planilha — o fim da cadeia que a escolha do acervo
        # abriu.
        built = stack.client.post(
            f"/v1/estimate-rounds/{round_id}/estimate",
            headers=_headers(f"{prefix}-orcamento", tenant=tenant),
            json={"base_version": version, "bdi_percent": BDI_PERCENT},
        )
        assert built.status_code == 200, built.text
        collected.append(built)
        assert built.json()["workbook_present"] is True

        estimate = Estimate.model_validate(built.json()["estimate"])
        assert any(line.price_origin is PriceOrigin.SCO for line in estimate.lines)
        assert all(
            line.catalog_sha256 == cascade.sco.source_sha256
            for line in estimate.lines
            if line.price_origin is PriceOrigin.SCO
        )

        read = stack.client.get(
            f"/v1/estimate-rounds/{round_id}/estimate", headers=_headers(tenant=tenant)
        )
        assert read.status_code == 200, read.text
        collected.append(read)
        assert read.json()["workbook_present"] is True
        assert read.json()["workbook_url"] is not None

    # 3. Depois das duas cadeias, o acervo continua com UMA linha: nenhuma republicação
    # aconteceu no meio do caminho, e é isso que "uma publicação serve dois tenants" quer
    # dizer.
    listing = stack.client.get(
        "/v1/platform/reference-catalogs",
        headers=_headers(tenant=PLATFORM_TENANT, roles=PLATFORM_ROLE),
    )
    assert listing.status_code == 200, listing.text
    collected.append(listing)
    assert [catalog["reference_catalog_id"] for catalog in listing.json()["catalogs"]] == [
        reference_catalog_id
    ]
    assert listing.json()["catalogs"][0]["object_sha256"] == published["object_sha256"]

    # 4. Escopo 4: nenhuma resposta da cadeia carrega o endereço do objeto do acervo.
    #
    # A contraprova de que a asserção não é vazia vem antes dela: a tabela do acervo APARECE
    # nas respostas da cadeia, pelo identificador dela. O que não aparece em nenhuma é a
    # chave sob `platform/reference-catalogs/` — que é justamente o que nenhuma rota assina.
    assert sum(reference_catalog_id in response.text for response in collected) >= 2
    for response in collected:
        assert REFERENCE_CATALOG_PREFIX not in response.text, response.request.url


# --- 2. os dois caminhos, o mesmo orçamento -------------------------------------------------


def test_reference_catalog_and_tenant_upload_produce_the_same_estimate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O critério que dá sentido à feature, provado pela cadeia HTTP inteira (escopo 2).

    Dois ambientes independentes, a MESMA cascata de três fontes (bytes idênticos, porque os
    catálogos são construídos uma vez só), a mesma prancha, as mesmas decisões de takeoff e
    de código. A ÚNICA diferença é o caminho de instalação do SCO: num ambiente ele sobe como
    arquivo do cliente, no outro é publicado no acervo e escolhido de lá.

    O que precisa sair igual é tudo o que o orçamento afirma sobre preço — linha a linha,
    total com e sem BDI, cascata declarada e a coluna FONTE da planilha reaberta. O que
    precisa sair DIFERENTE é uma coisa só: a `provenance` da entrada da cascata. Se um dia a
    procedência escorregar para dentro da linha (por exemplo, virando `price_origin` ou
    aparecendo na coluna FONTE), este teste é quem reprova — a rota isolada em
    `tests/api/test_estimate_round_routes.py` não vê a planilha.

    `unpriced_item_ids` é comparado por RÓTULO, e não pelo id cru: o id do item deriva de
    `plate_id`, que é `rodada-{round_id}` (`round_extraction.dataset_id` +
    `legend_extraction.legend_item_id`), logo é único por rodada por construção. Comparar os
    ids seria comparar o identificador da rodada, não o resultado do orçamento.
    """
    plate = render_synthetic_plate(tmp_path / "plate-source")
    monkeypatch.setenv(AI_BUDGET_ENV, "1.50")
    monkeypatch.setenv(_ANTHROPIC_KEY_ENV, "chave-de-teste-nunca-usada")
    cascade = _build_cascade(tmp_path / "fontes")

    by_upload = _build_stack(tmp_path / "por-upload", plate=plate)
    from_acervo = _build_stack(tmp_path / "pelo-acervo", plate=plate)

    results: dict[str, tuple[Estimate, dict[str, Any], Path, list[str]]] = {}
    collected: list[Response] = []
    for name, stack in (("upload", by_upload), ("acervo", from_acervo)):
        created = _create_round(
            stack,
            tenant=TENANT_SCALLE,
            worksite_key="praca-sintetica-comparada",
            reference_label="ORCAMENTO COMPARADO 01/2026",
            key="rodada-comparada",
        )
        assert created.status_code == 201, created.text
        round_id = created.json()["round_id"]
        version = created.json()["version"]

        # A diferença única entre os dois ambientes: como o SCO entra. EMOP e composição
        # sobem por upload nos dois, porque a plataforma não distribui nenhuma das duas.
        if name == "acervo":
            publication = _publish_to_acervo(
                stack, catalog=cascade.sco, display_name=ACERVO_DISPLAY_NAME, key="publica-sco"
            )
            assert publication.status_code == 201, publication.text
            sco_installed = _install_from_acervo(
                stack,
                round_id,
                reference_catalog_id=publication.json()["reference_catalog_id"],
                base_version=version,
                key="instala-sco",
                tenant=TENANT_SCALLE,
            )
        else:
            sco_installed = _install_by_upload(
                stack,
                round_id,
                catalog=cascade.sco,
                base_version=version,
                key="instala-sco",
                tenant=TENANT_SCALLE,
            )
        assert sco_installed.status_code == 201, sco_installed.text
        version = sco_installed.json()["version"]

        for index, catalog in enumerate((cascade.emop, cascade.composition)):
            installed = _install_by_upload(
                stack,
                round_id,
                catalog=catalog,
                base_version=version,
                key=f"instala-propria-{index}",
                tenant=TENANT_SCALLE,
            )
            assert installed.status_code == 201, installed.text
            version = installed.json()["version"]

        version, final_packet = _plate_through_takeoff(
            stack,
            round_id,
            version=version,
            tenant=TENANT_SCALLE,
            prefix=name,
            plate=plate,
            collected=collected,
        )
        version = _decide_codes(
            stack,
            round_id,
            version=version,
            tenant=TENANT_SCALLE,
            prefix=name,
            assignments=build_demo_estimate_assignments(
                final_packet, cascade.as_sequence()
            ).assignments,
            collected=collected,
        )

        built = stack.client.post(
            f"/v1/estimate-rounds/{round_id}/estimate",
            headers=_headers("orcamento-comparado", tenant=TENANT_SCALLE),
            json={"base_version": version, "bdi_percent": BDI_PERCENT},
        )
        assert built.status_code == 200, built.text
        body = built.json()
        assert body["workbook_present"] is True
        estimate = Estimate.model_validate(body["estimate"])

        # A planilha publicada, relida do store e gravada em disco para auditoria.
        workbook_path = tmp_path / f"orcamento-{name}.xlsx"
        workbook_path.write_bytes(
            _published_workbook(
                stack,
                tenant=TENANT_SCALLE,
                round_id=round_id,
                estimate_sha256=body["estimate_sha256"],
                workbook_sha256=body["workbook_sha256"],
            )
        )

        # Os itens sem preço, traduzidos de volta para o rótulo que a prancha declara.
        label_by_id = {item.id: item.label for item in final_packet.items}
        unpriced_labels = sorted(label_by_id[item_id] for item_id in estimate.unpriced_item_ids)

        state = stack.client.get(
            f"/v1/estimate-rounds/{round_id}", headers=_headers(tenant=TENANT_SCALLE)
        )
        assert state.status_code == 200, state.text
        results[name] = (
            estimate,
            _cascade_entry(state.json()["cascade"], PriceOrigin.SCO),
            workbook_path,
            unpriced_labels,
        )

    estimate_by_upload, sco_by_upload, workbook_by_upload, unpriced_by_upload = results["upload"]
    estimate_from_acervo, sco_from_acervo, workbook_from_acervo, unpriced_from_acervo = results[
        "acervo"
    ]

    # 1. O orçamento é o mesmo dado, linha a linha: `EstimateLine` carrega preço, código,
    # origem, digest da fonte, data-base e rótulo — e nada disso pode depender de quem
    # publicou o arquivo.
    # A contagem entra antes da comparação para que ela não possa passar por vacuidade: dois
    # orçamentos vazios também seriam "iguais", e o que este teste afirma é sobre conteúdo.
    assert len(estimate_by_upload.lines) == 5  # seis itens confirmados menos a luminária
    assert [line.model_dump() for line in estimate_from_acervo.lines] == [
        line.model_dump() for line in estimate_by_upload.lines
    ]
    assert estimate_from_acervo.total_amount == estimate_by_upload.total_amount
    assert (
        estimate_from_acervo.total_amount_without_bdi == estimate_by_upload.total_amount_without_bdi
    )
    assert [source.model_dump() for source in estimate_from_acervo.cascade] == [
        source.model_dump() for source in estimate_by_upload.cascade
    ]
    assert unpriced_from_acervo == unpriced_by_upload
    assert unpriced_from_acervo == ["LUMINARIA DUPLA SINTETICA"]

    # 2. A prova central: a procedência difere, o digest da fonte não. Uma é o fato de quem
    # publicou o arquivo; o outro é a identidade do catálogo que a linha do orçamento cita.
    assert sco_from_acervo["provenance"] == "reference_catalog"
    assert sco_by_upload["provenance"] == "tenant_upload"
    assert sco_from_acervo["source_sha256"] == sco_by_upload["source_sha256"]
    assert sco_from_acervo["source_sha256"] == cascade.sco.source_sha256

    # 3. As duas planilhas auditam limpo e a coluna FONTE da linha do SCO diz a mesma coisa
    # nas duas — o nome da TABELA, nunca o do caminho por onde ela entrou.
    template = default_template()
    for workbook_path, estimate in (
        (workbook_by_upload, estimate_by_upload),
        (workbook_from_acervo, estimate_from_acervo),
    ):
        audit = audit_estimate_workbook(workbook_path, estimate, template)
        assert audit.status == "ok", audit.findings
        assert audit.findings == []

    source_by_upload = _source_cell_of_first_sco_line(workbook_by_upload, estimate_by_upload)
    source_from_acervo = _source_cell_of_first_sco_line(workbook_from_acervo, estimate_from_acervo)
    assert source_from_acervo == source_by_upload
    assert "SCO" in source_from_acervo
    assert "reference_catalog" not in source_from_acervo
    assert "acervo" not in source_from_acervo.lower()

    # 4. E a recusa do escopo 4 vale igual neste caminho: a cadeia do ambiente que instalou
    # pelo acervo também não devolve, em resposta nenhuma, o endereço do objeto publicado.
    for response in collected:
        assert REFERENCE_CATALOG_PREFIX not in response.text, response.request.url
