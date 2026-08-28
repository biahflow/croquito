"""O braço semântico no caminho hospedado (F-041 fatia 2, ADR-0054).

A fatia 1 publicou o índice; esta suíte cobre o que acontece quando ele é **usado**. As
invariantes protegidas aqui não são de rota, são de custo e de honestidade:

1. **O `GET` da shortlist não paga nada.** O adapter que os testes de leitura instalam
   EXPLODE se alguém o chamar — é a única forma de provar uma invariante negativa. Mover a
   chamada paga para o `GET` quebraria o teste antes de quebrar a fatura, e é isso que ele
   existe para fazer.
2. **Nenhuma ausência recusa o ato.** Tenant sem entitlement, ambiente com providers
   desligados, fonte sem índice, índice recusado na amarração: todos devolvem `200` com a
   shortlist léxica e o motivo declarado. Um `403` aqui tiraria do orçamentista o braço
   léxico, que não custa nada.
3. **A nota diz QUAL fonte ficou sem** (D6), e as notas dos casos são distintas entre si:
   uma frase única mandaria a pessoa procurar o problema no lugar errado.
4. **A fusão RRF não atravessa fontes** (D5). Os blocos saem na ordem instalada da cascata,
   e é a ordem que o teste confere — não os scores.
5. **Nenhum vetor de consulta sobrevive ao ato** (emenda de 2026-08-28). O diretório
   temporário é observado e precisa não existir depois; e um segundo recompute paga de novo,
   que é a prova de comportamento de que nada foi guardado.

Nenhuma chamada paga acontece na suíte: o adapter é fabricado e o índice é o offline de
`sco_matching_fixtures` — mesmo contrato de documento, vetores por hash de radicais. Ele
prova o caminho do artefato e a fiação, nunca a qualidade semântica; a medida real é o
golden com o índice pago (`tests/valuation/test_matcher_golden.py`, sob `skipif`).
"""

from __future__ import annotations

import hashlib
import tempfile
from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any, Final, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from croquito_api.config import ApiSettings
from croquito_api.database import (
    Database,
    DomainEventRecord,
    EstimateRoundRevisionRecord,
    ValuationRoundRecord,
    ValuationRoundRevisionRecord,
)
from croquito_api.main import create_app
from croquito_api.semantic_arm import (
    ENTITLEMENT_INACTIVE_REASON,
    PROVIDERS_DISABLED_REASON,
)
from croquito_api.valuation_rounds import document_digest
from croquito_core.ids import new_uuid7
from croquito_valuation.assignment import (
    SCO_CASCADE_SUGGESTER_VERSION,
    SCO_HYBRID_CASCADE_SUGGESTER_VERSION,
    SCO_HYBRID_SUGGESTER_FAMILY,
    SUGGESTION_SCHEMA_VERSION,
    CodeSuggestionSet,
)
from croquito_valuation.models import PriceCatalog, PriceCatalogEntry, PriceOrigin
from croquito_valuation.takeoff import (
    PlateBox,
    PlateEvidence,
    TakeoffItem,
    TakeoffItemStatus,
    TakeoffPacket,
)
from croquito_worker.providers import EmbeddingsExecution, ProviderName, ProviderUsage
from croquito_worker.valuation.round_extraction import PLATE_IMAGE_DIGEST, PLATE_IMAGE_REF
from croquito_worker.valuation.sco_matching import index_document, normalize_query_text
from croquito_worker.valuation.sco_matching_fixtures import (
    FIXTURE_EMBEDDINGS_DIMS,
    FIXTURE_EMBEDDINGS_MODEL,
    fixture_catalog_index,
    fixture_vector,
)
from tests.fakes import FakeObjectStore

_TENANT: Final = "tenant-a"
_PLATFORM_TENANT: Final = "tenant-plataforma"
_BUILDER_SUBJECT: Final = "orcamentista-sintetica"
_ITEM: Final = "ti_00000000000000b1"
_IMAGE_DIGEST: Final = "a" * 64
_LABEL: Final = "ALAMBRADO GALVANIZADO"

_SCO_CODE: Final = "CE04100010(/)"
_SCO_SECOND_CODE: Final = "IP49150409(/)"
_EMOP_CODE: Final = "03.005.0010-A"
_SINAPI_CODE: Final = "88489"

_OUTRA_RECEITA: Final = "description-unit-v2"
"""A receita medida e DESCARTADA na rodada 2.1 (`INDEX_TEXT_RECIPE_MEASUREMENT`).

Ela é usada aqui porque é uma receita real que o contrato do documento aceita e que o
código corrente não usa — inventar uma string seria testar a recusa do enum, e não a
resolução por receita, que é o assunto."""

_ACERVO_PATH: Final = "/v1/platform/reference-catalogs"
_INDEXES_PATH: Final = "/v1/platform/reference-catalog-indexes"


# --- montagem -----------------------------------------------------------------------------


def _client(tmp_path: Path, *, real_providers_enabled: bool = True) -> TestClient:
    """Aplicação com providers reais LIGADOS por padrão.

    É o contrário do default das demais suítes, e de propósito: com `false` o braço nunca
    seria tentado e todo cenário desta suíte cairia na mesma nota de ambiente desligado. O
    caso desligado tem teste próprio, e ele passa `False` explicitamente.
    """
    url = f"sqlite+pysqlite:///{tmp_path / 'semantic-arm.db'}"
    database = Database(url)
    database.create_schema()
    settings = ApiSettings(
        database_url=url,
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
    # A via de embeddings é INJETADA no mesmo ponto que a produção usa
    # (`application.state.embeddings_adapter`, ADR-0054 aceite humano item 2). Nenhum teste
    # constrói o adapter real: ele lê credencial do ambiente e falaria com a rede.
    application.state.embeddings_adapter = None
    application.state.embeddings_unavailable_reason = PROVIDERS_DISABLED_REASON
    return TestClient(application)


def _state(client: TestClient) -> Any:
    return cast(Any, client.app).state


def _store(client: TestClient) -> FakeObjectStore:
    return cast(FakeObjectStore, _state(client).artifact_store)


def _database(client: TestClient) -> Database:
    return cast(Database, _state(client).database)


def _headers(
    tenant: str = _TENANT,
    roles: str = "orcamentista",
    *,
    key: str = "req-001",
    subject: str = _BUILDER_SUBJECT,
) -> dict[str, str]:
    return {
        "Authorization": f"Bearer test:{tenant}:{subject}:{roles}",
        "Idempotency-Key": key,
    }


def _operator(key: str = "op-001") -> dict[str, str]:
    return _headers(_PLATFORM_TENANT, "platform_operator", key=key)


class _FakeEmbeddings:
    """Via de embeddings determinística: os mesmos vetores que o índice fixture usa.

    Ela precisa concordar com `fixture_catalog_index` no espaço vetorial, senão a consulta
    seria recusada por dimensão divergente antes de a fusão acontecer. `calls` existe para
    que os testes de custo contem CHAMADAS, e não confiem em não ter havido nenhuma.
    """

    def __init__(self, *, dims: int = FIXTURE_EMBEDDINGS_DIMS) -> None:
        self.calls: list[tuple[str, ...]] = []
        self._dims = dims

    def embed(self, texts: Sequence[str]) -> EmbeddingsExecution:
        self.calls.append(tuple(texts))
        vectors = tuple(fixture_vector(text, dims=self._dims) for text in texts)
        return EmbeddingsExecution(
            provider=ProviderName.OPENAI,
            model_id=FIXTURE_EMBEDDINGS_MODEL,
            input_count=len(texts),
            input_digest=hashlib.sha256(b"fixture-query-batch").hexdigest(),
            dims=self._dims,
            latency_ms=7,
            usage=ProviderUsage(input_tokens=12, estimated_cost_usd=Decimal("0.0001")),
            vectors=vectors,
        )


class _ForbiddenEmbeddings:
    """Adapter que só sabe falhar: instalado onde nenhuma chamada paga pode acontecer.

    É a prova da invariante negativa do `GET`. Sem ele, "o `GET` não paga" seria uma
    afirmação sobre o código de hoje; com ele, mover a chamada para lá derruba o teste.
    """

    def embed(self, texts: Sequence[str]) -> EmbeddingsExecution:
        raise AssertionError(
            f"chamada paga de embeddings num caminho que não pode pagar ({len(texts)} textos)"
        )


def _arm(client: TestClient, adapter: object) -> None:
    """Liga a via de embeddings da aplicação, como o `create_app` faria com credencial."""
    _state(client).embeddings_adapter = adapter
    _state(client).embeddings_unavailable_reason = None


def _catalog(
    *,
    origin: PriceOrigin = PriceOrigin.SCO,
    source_sha256: str | None = None,
    codes: Sequence[str] | None = None,
) -> PriceCatalog:
    """Catálogo sintético, com o código que a origem exige.

    `source_sha256` é o digest do arquivo de ORIGEM declarado dentro do JSON, e não o digest
    dos bytes que sobem — é essa distinção que o ADR-0054 D3 usa para achar o índice, e é
    ela que um dos testes exercita ao seu contrário.
    """
    default = [_SCO_CODE] if origin == PriceOrigin.SCO else [_EMOP_CODE]
    return PriceCatalog(
        source_label=f"CATALOGO SINTETICO {origin.value.upper()}",
        reference_month="2026-01",
        source_sha256=(
            source_sha256 or hashlib.sha256(f"origem-{origin.value}".encode()).hexdigest()
        ),
        origin=origin,
        entries=[
            PriceCatalogEntry(
                code=code,
                description="ALAMBRADO GALVANIZADO EM TELA",
                unit="m",
                unit_price=Decimal("50.00"),
                family_code="CE",
                family_name="SERVICOS SINTETICOS",
                subgroup_code="CE0410",
                subgroup_name="ITENS SINTETICOS",
                origin=origin,
            )
            for code in (codes or default)
        ],
    )


def _presign_and_put(client: TestClient, *, path: str, payload: bytes, key: str) -> str:
    presign = client.post(
        path,
        headers=_operator(f"presign-{key}"),
        json={
            "filename": "artefato.json",
            "size_bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        },
    )
    assert presign.status_code == 200, presign.text
    _store(client).put_direct(
        object_key=presign.json()["object_key"], body=payload, content_type="application/json"
    )
    return cast(str, presign.json()["upload_id"])


def _publish_catalog_and_index(
    client: TestClient,
    catalog: PriceCatalog,
    *,
    key: str,
    index_catalog: PriceCatalog | None = None,
    text_recipe: str | None = None,
) -> None:
    """Publica o catálogo no acervo e o índice dele, pelas rotas de plataforma da fatia 1.

    `index_catalog` permite indexar um catálogo DIFERENTE do publicado, mantendo o digest de
    fonte igual — é como se fabrica a recusa de amarração sem escrever linha no banco pela
    mão. `text_recipe` idem, para o índice de receita divergente.
    """
    payload = catalog.model_dump_json().encode("utf-8")
    upload_id = _presign_and_put(
        client, path=f"{_ACERVO_PATH}/presign", payload=payload, key=f"cat-{key}"
    )
    published = client.post(
        _ACERVO_PATH,
        headers=_operator(f"cat-{key}"),
        json={"upload_id": upload_id, "display_name": f"acervo {key}"},
    )
    assert published.status_code == 201, published.text

    document = fixture_catalog_index(index_catalog or catalog)
    if text_recipe is not None:
        document = document.model_copy(update={"text_recipe": text_recipe})
    index_payload = index_document(document).encode("utf-8")
    index_upload = _presign_and_put(
        client, path=f"{_INDEXES_PATH}/presign", payload=index_payload, key=f"idx-{key}"
    )
    created = client.post(
        _INDEXES_PATH,
        headers=_operator(f"idx-{key}"),
        json={
            "upload_id": index_upload,
            "reference_catalog_id": published.json()["reference_catalog_id"],
        },
    )
    assert created.status_code == 201, created.text


def _entitle(client: TestClient, *, enabled: bool = True, key: str = "entitlement-001") -> None:
    response = client.put(
        f"/v1/platform/tenants/{_TENANT}/ai-processing-entitlement",
        headers=_operator(key),
        json={"enabled": enabled, "agreement_reference": "CONTRATO-SINTETICO-001"},
    )
    assert response.status_code == 200, response.text


def _install_catalog(
    client: TestClient, round_id: str, catalog: PriceCatalog, *, version: int
) -> int:
    """Instala uma fonte na cascata da rodada pelo caminho do upload do orçamentista."""
    payload = catalog.model_dump_json().encode("utf-8")
    presign = client.post(
        "/v1/uploads/presign",
        headers=_headers(key=f"up-{catalog.origin.value}-{version}"),
        json={
            "filename": "catalogo.json",
            "content_type": "application/json",
            "size_bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        },
    )
    assert presign.status_code == 200, presign.text
    _store(client).put_direct(
        object_key=presign.json()["object_key"], body=payload, content_type="application/json"
    )
    installed = client.post(
        f"/v1/estimate-rounds/{round_id}/catalogs",
        headers=_headers(key=f"cat-{catalog.origin.value}-{version}"),
        json={"upload_id": presign.json()["upload_id"], "base_version": version},
    )
    assert installed.status_code == 201, installed.text
    return cast(int, installed.json()["version"])


def _packet() -> TakeoffPacket:
    return TakeoffPacket(
        plate_id="rodada-sintetica",
        page_number=1,
        image_sha256=_IMAGE_DIGEST,
        source_pdf_sha256="b" * 64,
        items=[
            TakeoffItem(
                id=_ITEM,
                evidence=PlateEvidence(
                    plate_id="rodada-sintetica",
                    page_number=1,
                    image_sha256=_IMAGE_DIGEST,
                    bbox=PlateBox(left=10, top=10, right=210, bottom=60),
                ),
                raw_text=f"{_LABEL} 10,00 m",
                label=_LABEL,
                quantity=Decimal("10.00"),
                unit="m",
                source="legend_extraction",
                extractor="legend-extractor-sintetico",
                extractor_version="1.0.0",
                status=TakeoffItemStatus.PROPOSED,
            )
        ],
        safety_notes=[
            "Extração automática da legenda; quantidade não confirmada.",
            "Decisão do orçamentista obrigatória antes de qualquer orçamento.",
        ],
    )


def _round_with(client: TestClient, catalogs: Sequence[PriceCatalog]) -> dict[str, Any]:
    """Rodada com a cascata instalada NA ORDEM dada e o takeoff publicado e revisado."""
    created = client.post(
        "/v1/estimate-rounds",
        headers=_headers(key="rodada-001"),
        json={
            "worksite_key": "praca-sintetica-norte",
            "worksite_name": "PRACA SINTETICA NORTE",
            "reference_label": "ORCAMENTO-BASE 2026",
            "address": "RUA SINTETICA, S/N",
        },
    )
    assert created.status_code == 201, created.text
    round_id = cast(str, created.json()["round_id"])
    version = 1
    for catalog in catalogs:
        version = _install_catalog(client, round_id, catalog, version=version)

    packet = _packet()
    document = packet.model_dump(mode="json")
    with _database(client).sessions() as session:
        # O takeoff é escrito direto porque a extração é PAGA: exercitá-la aqui faria cada
        # cenário desta suíte depender do braço do provider de extração, que não é o assunto.
        head = session.scalar(
            select(EstimateRoundRevisionRecord)
            .where(EstimateRoundRevisionRecord.round_id == round_id)
            .order_by(EstimateRoundRevisionRecord.version.desc())
            .limit(1)
        )
        session.add(
            EstimateRoundRevisionRecord(
                id=str(new_uuid7()),
                tenant_id=_TENANT,
                round_id=round_id,
                version=1 if head is None else head.version + 1,
                parent_revision_id=None if head is None else head.id,
                created_by="estimate-extraction-v1",
                takeoff_packet_json=document,
                artifact_refs_json={
                    PLATE_IMAGE_REF: (
                        f"tenants/{_TENANT}/estimate-rounds/{round_id}/plate/page-001.png"
                    )
                },
                artifact_digests_json={PLATE_IMAGE_DIGEST: packet.image_sha256},
            )
        )
        session.commit()

    decided = client.post(
        f"/v1/estimate-rounds/{round_id}/takeoff/decisions",
        headers=_headers(key="takeoff-001"),
        json={"base_version": version, "decisions": [{"item_id": _ITEM, "action": "confirm"}]},
    )
    assert decided.status_code == 200, decided.text
    return {"round_id": round_id, "version": decided.json()["version"]}


def _get_suggestions(client: TestClient, round_id: str) -> Any:
    return client.get(
        f"/v1/estimate-rounds/{round_id}/code-suggestions", headers=_headers(key="ler-001")
    )


def _recompute(client: TestClient, round_id: str, *, version: int, key: str = "recalc-001") -> Any:
    return client.post(
        f"/v1/estimate-rounds/{round_id}/code-suggestions/recompute",
        headers=_headers(key=key),
        json={"base_version": version},
    )


def _prepared(
    client: TestClient,
    catalogs: Sequence[PriceCatalog],
    *,
    adapter: object | None = None,
) -> dict[str, Any]:
    """Rodada pronta para o recompute: entitlement ativo e via de embeddings instalada."""
    _entitle(client)
    _arm(client, adapter if adapter is not None else _FakeEmbeddings())
    return _round_with(client, catalogs)


def _notes(response: Any) -> list[str]:
    return cast(list[str], response.json()["semantic_notes"])


# --- 1. a shortlist híbrida existe no caminho hospedado -----------------------------------


def test_o_recompute_com_indice_publicado_devolve_shortlist_hibrida(tmp_path: Path) -> None:
    """Critério 1: fonte com índice publicado sai híbrida, com lineage e versão da família.

    É a entrega da feature vista de fora: a mesma rodada que hoje só teria a shortlist léxica
    passa a ter a fusão dos dois braços depois de um ato humano explícito.
    """
    client = _client(tmp_path)
    catalog = _catalog()
    _publish_catalog_and_index(client, catalog, key="sco")
    prepared = _prepared(client, [catalog])

    response = _recompute(client, prepared["round_id"], version=prepared["version"])

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["matching"] == "hybrid"
    suggestions = body["suggestions"]
    assert suggestions["suggester_version"] == SCO_HYBRID_CASCADE_SUGGESTER_VERSION
    assert suggestions["suggester_version"].startswith(SCO_HYBRID_SUGGESTER_FAMILY)
    assert len(suggestions["semantic"]) == 1
    assert suggestions["semantic"][0]["model_id"] == FIXTURE_EMBEDDINGS_MODEL
    assert suggestions["semantic"][0]["catalog_sha256"] == catalog.source_sha256


def test_a_leitura_seguinte_serve_a_shortlist_hibrida_ja_gravada(tmp_path: Path) -> None:
    """O ganho não é da resposta, é do ARTEFATO: ele fica gravado na cadeia de revisões.

    Depois do recompute, o `GET` serve o que está lá — com o adapter proibido instalado, o
    que prova de uma vez que ler o híbrido gravado também não paga nada.
    """
    client = _client(tmp_path)
    catalog = _catalog()
    _publish_catalog_and_index(client, catalog, key="sco")
    prepared = _prepared(client, [catalog])
    assert _recompute(client, prepared["round_id"], version=prepared["version"]).status_code == 200

    _arm(client, _ForbiddenEmbeddings())
    response = _get_suggestions(client, prepared["round_id"])

    assert response.status_code == 200, response.text
    assert response.json()["computed"] is False
    assert response.json()["matching"] == "hybrid"


# --- 2. cobertura parcial por fonte -------------------------------------------------------


def test_cascata_com_uma_fonte_indexada_roda_hibrido_so_nela_e_diz_qual_ficou_sem(
    tmp_path: Path,
) -> None:
    """Critério 2 e ADR-0054 D5/D6, as três afirmações juntas.

    A fonte indexada roda a fusão, a outra entra só com o braço léxico, e os blocos saem na
    ORDEM INSTALADA — a precedência das tabelas é decisão de quem monta o orçamento, e não
    pode ser desempatada por similaridade de texto. A nota nomeia a fonte que ficou de fora,
    e não uma frase única sobre "o braço".
    """
    client = _client(tmp_path)
    sco = _catalog(origin=PriceOrigin.SCO)
    emop = _catalog(origin=PriceOrigin.EMOP)
    _publish_catalog_and_index(client, sco, key="sco")
    prepared = _prepared(client, [sco, emop])

    response = _recompute(client, prepared["round_id"], version=prepared["version"])

    assert response.status_code == 200, response.text
    suggestions = response.json()["suggestions"]
    assert suggestions["suggester_version"] == SCO_HYBRID_CASCADE_SUGGESTER_VERSION
    # Uma entrada de lineage, e é a do SCO: a EMOP não tem índice publicado.
    assert [entry["catalog_sha256"] for entry in suggestions["semantic"]] == [sco.source_sha256]
    # Blocos na ordem instalada: todos os do SCO, depois todos os da EMOP.
    origens = [
        candidate["catalog_origin"] for candidate in suggestions["suggestions"][0]["candidates"]
    ]
    assert origens == ["sco", "emop"]

    notas = _notes(response)
    assert any("fonte 2 (emop)" in nota and "sem índice" in nota for nota in notas)
    assert not any("fonte 1 (sco)" in nota and "sem índice" in nota for nota in notas)


def test_a_fonte_sem_indice_nao_derruba_a_que_tem(tmp_path: Path) -> None:
    """Trocar a ordem não muda quem roda o braço: a cobertura é por FONTE, não por cascata.

    Com a fonte sem índice na FRENTE, o SCO continua híbrido. Degradar a cascata inteira
    porque a primeira fonte não tem índice tiraria do orçamentista a vizinhança semântica que
    ele tem — e ela já foi paga, uma vez, pela plataforma.
    """
    client = _client(tmp_path)
    sco = _catalog(origin=PriceOrigin.SCO)
    emop = _catalog(origin=PriceOrigin.EMOP)
    _publish_catalog_and_index(client, sco, key="sco")
    prepared = _prepared(client, [emop, sco])

    response = _recompute(client, prepared["round_id"], version=prepared["version"])

    assert response.status_code == 200, response.text
    suggestions = response.json()["suggestions"]
    assert suggestions["suggester_version"] == SCO_HYBRID_CASCADE_SUGGESTER_VERSION
    assert [entry["catalog_sha256"] for entry in suggestions["semantic"]] == [sco.source_sha256]
    origens = [
        candidate["catalog_origin"] for candidate in suggestions["suggestions"][0]["candidates"]
    ]
    assert origens == ["emop", "sco"]
    assert any("fonte 1 (emop)" in nota for nota in _notes(response))


# --- 3. o GET não paga nada ---------------------------------------------------------------


def test_o_get_da_shortlist_nao_faz_chamada_paga_nenhuma(tmp_path: Path) -> None:
    """Critério 3, provado por adapter que EXPLODE se for tocado (ADR-0054 D7).

    O índice está publicado, o entitlement está ativo e a via de embeddings existe: tudo o
    que o recompute precisaria. Ainda assim o `GET` sai léxico, porque ele não monta braço
    nenhum — e é essa a invariante, não a ausência circunstancial de índice.
    """
    client = _client(tmp_path)
    catalog = _catalog()
    _publish_catalog_and_index(client, catalog, key="sco")
    _entitle(client)
    proibido = _ForbiddenEmbeddings()
    _arm(client, proibido)
    prepared = _round_with(client, [catalog])

    response = _get_suggestions(client, prepared["round_id"])

    assert response.status_code == 200, response.text
    assert response.json()["matching"] == "lexical"
    assert response.json()["suggestions"]["suggester_version"] == SCO_CASCADE_SUGGESTER_VERSION
    assert response.json()["suggestions"]["semantic"] is None
    assert any("recálculo explícito" in nota for nota in _notes(response))


def test_o_get_nao_le_o_indice_publicado_nem_uma_vez(tmp_path: Path) -> None:
    """A invariante do `GET` é mais forte do que "não chamou o provider".

    Ele também não vai ao object store atrás dos ~40 MB do índice: não há braço para montar,
    então não há índice para ler. O cache do processo continua vazio depois da leitura, e é
    ele que denuncia uma leitura que tivesse acontecido.
    """
    client = _client(tmp_path)
    catalog = _catalog()
    _publish_catalog_and_index(client, catalog, key="sco")
    _entitle(client)
    _arm(client, _ForbiddenEmbeddings())
    prepared = _round_with(client, [catalog])

    assert _get_suggestions(client, prepared["round_id"]).status_code == 200

    cache = _state(client).semantic_index_cache
    assert cache.get((_index_digest(client), catalog.source_sha256)) is None


def _index_digest(client: TestClient) -> str:
    listagem = client.get(_INDEXES_PATH, headers=_operator("listar"))
    assert listagem.status_code == 200, listagem.text
    return cast(str, listagem.json()["indexes"][0]["object_sha256"])


# --- 4 e 5. as duas degradações de ambiente, distintas entre si ---------------------------


def test_tenant_sem_entitlement_recebe_shortlist_lexica_com_o_motivo_nunca_403(
    tmp_path: Path,
) -> None:
    """Critério 4 (ADR-0054 D8): a falta de contrato tira o braço pago, não o ato.

    `_require_active_ai_entitlement` devolveria `403` e o orçamentista perderia o recompute
    inteiro — inclusive o braço léxico, que não chama provider nenhum. Aqui a falta vira nota
    e a rodada avança de versão como qualquer outro ato humano.
    """
    client = _client(tmp_path)
    catalog = _catalog()
    _publish_catalog_and_index(client, catalog, key="sco")
    _arm(client, _ForbiddenEmbeddings())
    prepared = _round_with(client, [catalog])

    response = _recompute(client, prepared["round_id"], version=prepared["version"])

    assert response.status_code == 200, response.text
    assert response.json()["matching"] == "lexical"
    assert _notes(response) == [ENTITLEMENT_INACTIVE_REASON]
    assert response.json()["version"] > prepared["version"]
    # E a shortlist é a MESMA de sempre: sem braço semântico, o algoritmo não troca.
    assert response.json()["suggestions"]["suggester_version"] == SCO_CASCADE_SUGGESTER_VERSION


def test_entitlement_revogado_volta_a_degradar_sem_recusar(tmp_path: Path) -> None:
    """Revogar o contrato não quebra a tela: o recompute seguinte sai léxico com o motivo."""
    client = _client(tmp_path)
    catalog = _catalog()
    _publish_catalog_and_index(client, catalog, key="sco")
    prepared = _prepared(client, [catalog])
    primeiro = _recompute(client, prepared["round_id"], version=prepared["version"])
    assert primeiro.json()["matching"] == "hybrid"

    _entitle(client, enabled=False, key="entitlement-002")
    _arm(client, _ForbiddenEmbeddings())
    segundo = _recompute(
        client, prepared["round_id"], version=primeiro.json()["version"], key="recalc-002"
    )

    assert segundo.status_code == 200, segundo.text
    assert segundo.json()["matching"] == "lexical"
    assert _notes(segundo) == [ENTITLEMENT_INACTIVE_REASON]


def test_providers_desligados_degradam_com_nota_propria_distinta_da_de_entitlement(
    tmp_path: Path,
) -> None:
    """Critério 5: ambiente desligado e contrato ausente são problemas de gente diferente.

    Um é do operador da plataforma (variável de ambiente do serviço), o outro é comercial.
    Uma frase única para os dois mandaria a orçamentista abrir chamado no lugar errado, e é
    por isso que o teste compara as duas notas e exige que sejam diferentes.
    """
    client = _client(tmp_path, real_providers_enabled=False)
    catalog = _catalog()
    _publish_catalog_and_index(client, catalog, key="sco")
    _entitle(client)
    _arm(client, _ForbiddenEmbeddings())
    prepared = _round_with(client, [catalog])

    response = _recompute(client, prepared["round_id"], version=prepared["version"])

    assert response.status_code == 200, response.text
    assert response.json()["matching"] == "lexical"
    assert _notes(response) == [PROVIDERS_DISABLED_REASON]
    assert PROVIDERS_DISABLED_REASON != ENTITLEMENT_INACTIVE_REASON


def test_sem_via_de_embeddings_no_processo_a_nota_e_a_do_ambiente_nao_a_de_indice(
    tmp_path: Path,
) -> None:
    """Sem teto de gasto ou credencial, a nota fala do AMBIENTE, e não de índice ausente.

    O índice está lá; dizer que ele falta mandaria o operador republicar um artefato que já
    está publicado. É a mesma disciplina das outras notas: nomear o que de fato falta.
    """
    client = _client(tmp_path)
    catalog = _catalog()
    _publish_catalog_and_index(client, catalog, key="sco")
    _entitle(client)
    _state(client).embeddings_adapter = None
    _state(client).embeddings_unavailable_reason = "via de embeddings indisponível: sem teto"
    prepared = _round_with(client, [catalog])

    response = _recompute(client, prepared["round_id"], version=prepared["version"])

    assert response.status_code == 200, response.text
    assert _notes(response) == ["via de embeddings indisponível: sem teto"]
    assert not any("sem índice" in nota for nota in _notes(response))


def test_sem_nenhum_indice_o_recompute_devolve_a_mesma_shortlist_do_get(
    tmp_path: Path,
) -> None:
    """Enquanto ninguém publicar índice, o recálculo não muda a shortlist — só as notas.

    É a fronteira desta fatia: ela ACRESCENTA um braço, não troca a via. Um recompute que
    devolvesse outra ordem para uma rodada sem índice nenhum seria mudança de comportamento
    que ninguém pediu e ninguém mediu na cascata, e a orçamentista veria a lista mexer sem
    causa visível.

    A nota, essa muda: em vez de uma frase única, ela nomeia cada fonte que ficou sem índice.
    """
    client = _client(tmp_path)
    sco = _catalog(origin=PriceOrigin.SCO)
    emop = _catalog(origin=PriceOrigin.EMOP)
    prepared = _prepared(client, [sco, emop])

    lida = _get_suggestions(client, prepared["round_id"])
    recalculada = _recompute(client, prepared["round_id"], version=prepared["version"])

    assert lida.status_code == 200, lida.text
    assert recalculada.status_code == 200, recalculada.text
    assert (
        recalculada.json()["suggestions"]["suggester_version"]
        == lida.json()["suggestions"]["suggester_version"]
        == SCO_CASCADE_SUGGESTER_VERSION
    )
    assert (
        recalculada.json()["suggestions"]["suggestions"]
        == lida.json()["suggestions"]["suggestions"]
    )
    assert sorted(_notes(recalculada)) == sorted(
        [
            "busca semântica indisponível: fonte 1 (sco) sem índice de embeddings publicado",
            "busca semântica indisponível: fonte 2 (emop) sem índice de embeddings publicado",
        ]
    )


def test_o_motivo_do_ato_nao_e_repetido_uma_vez_por_fonte(tmp_path: Path) -> None:
    """Problema único, aviso único: entitlement inativo é UMA nota, não uma por tabela.

    O motivo do ato vale para a cascata inteira, e repeti-lo por fonte daria à tela três
    avisos idênticos sobre a mesma coisa — ruído que faz a nota que importa passar batida.
    """
    client = _client(tmp_path)
    sco = _catalog(origin=PriceOrigin.SCO)
    emop = _catalog(origin=PriceOrigin.EMOP)
    _publish_catalog_and_index(client, sco, key="sco")
    _arm(client, _ForbiddenEmbeddings())
    prepared = _round_with(client, [sco, emop])

    response = _recompute(client, prepared["round_id"], version=prepared["version"])

    assert response.status_code == 200, response.text
    assert _notes(response) == [ENTITLEMENT_INACTIVE_REASON]


# --- 6. a forma singular gravada continua legível -----------------------------------------


def test_shortlist_gravada_na_forma_singular_continua_legivel_apos_o_bump() -> None:
    """Critério 6: `1.2.0` com `semantic` singular carrega, e vira lista de um.

    Não é cortesia de contrato. `suggestions_of` trata artefato ilegível como AUSENTE, então
    um conjunto que deixasse de validar apagaria em silêncio o refino pago que ele carrega —
    o lineage que explica por que a ordem publicada é aquela.
    """
    antigo = {
        "schema_version": "1.2.0",
        "plate_id": "rodada-sintetica",
        "page_number": 1,
        "image_sha256": _IMAGE_DIGEST,
        "catalog_sha256": "c" * 64,
        "suggester_version": "hybrid-sco-suggester-v2",
        "semantic": {
            "provider": "openai",
            "model_id": "text-embedding-3-small",
            "dims": 1536,
            "index_sha256": "d" * 64,
        },
        "suggestions": [],
        "unmatched_item_ids": [],
        "safety_notes": ["nota 1", "nota 2", "nota 3"],
    }

    restaurado = CodeSuggestionSet.model_validate(antigo)

    assert restaurado.schema_version == "1.2.0"
    assert restaurado.semantic is not None
    assert len(restaurado.semantic) == 1
    assert restaurado.semantic[0].index_sha256 == "d" * 64
    # Sem `catalog_sha256`, a fonte é a do cabeçalho — que é o que o artefato antigo afirmava.
    assert restaurado.semantic[0].catalog_sha256 is None
    assert SUGGESTION_SCHEMA_VERSION == "1.3.0"


def test_a_shortlist_singular_gravada_na_rodada_nao_e_tratada_como_ausente(
    tmp_path: Path,
) -> None:
    """A mesma retrocompatibilidade vista de dentro da rodada, que é onde ela importa.

    `suggestions_of` é quem decide se a guarda de refino pago consegue ler o artefato. Uma
    shortlist antiga com refino que virasse "ausente" seria sobrescrita pelo recompute sem
    aviso nenhum — exatamente o que `SUGGESTIONS_ALREADY_REFINED` existe para impedir.
    """
    from croquito_api import estimate_rounds

    client = _client(tmp_path)
    catalog = _catalog()
    prepared = _prepared(client, [catalog])
    round_id = prepared["round_id"]
    antigo = {
        "schema_version": "1.2.0",
        "plate_id": "rodada-sintetica",
        "page_number": 1,
        "image_sha256": _IMAGE_DIGEST,
        "catalog_sha256": catalog.source_sha256,
        "suggester_version": "hybrid-sco-suggester-v2+llm-rerank-v1",
        "semantic": {
            "provider": "openai",
            "model_id": "text-embedding-3-small",
            "dims": 1536,
            "index_sha256": "d" * 64,
        },
        "refinement": {
            "provider": "openai",
            "model_id": "gpt-sintetico",
            "prompt_version": "sco-rerank-v1",
            "input_digest": "e" * 64,
        },
        "suggestions": [],
        "unmatched_item_ids": [],
        "safety_notes": ["nota 1", "nota 2", "nota 3"],
    }
    with _database(client).sessions() as session:
        head = session.scalar(
            select(EstimateRoundRevisionRecord)
            .where(EstimateRoundRevisionRecord.round_id == round_id)
            .order_by(EstimateRoundRevisionRecord.version.desc())
            .limit(1)
        )
        assert head is not None
        head.code_suggestions_json = antigo
        session.commit()
        recarregado = estimate_rounds.suggestions_of(head)

    assert recarregado is not None
    assert recarregado.semantic is not None

    recusado = _recompute(client, round_id, version=prepared["version"])

    assert recusado.status_code == 409, recusado.text
    assert recusado.json()["code"] == "SUGGESTIONS_ALREADY_REFINED"


# --- 7. índice recusado na amarração ------------------------------------------------------


def test_indice_recusado_na_amarracao_vira_nota_com_o_codigo_e_nao_derruba_o_recompute(
    tmp_path: Path,
) -> None:
    """Critério 7: há índice, ele foi RECUSADO, e isso é fato diferente de não haver índice.

    O cenário é real e não inventado: a busca é por DIGEST DA FONTE (ADR-0054 D3), e o
    `source_sha256` é um campo declarado dentro do catálogo, não o digest dos bytes que
    sobem. Um catálogo instalado que declara o mesmo digest de fonte e traz outros itens é
    encontrado pelo índice e recusado por `bind_index_to_catalog` — que é exatamente a
    conferência existir para isso.
    """
    client = _client(tmp_path)
    digest = hashlib.sha256(b"mesma-fonte-declarada").hexdigest()
    publicado = _catalog(source_sha256=digest)
    _publish_catalog_and_index(client, publicado, key="sco")
    divergente = _catalog(source_sha256=digest, codes=[_SCO_CODE, _SCO_SECOND_CODE])
    prepared = _prepared(client, [divergente])

    response = _recompute(client, prepared["round_id"], version=prepared["version"])

    assert response.status_code == 200, response.text
    assert response.json()["matching"] == "lexical"
    notas = _notes(response)
    assert len(notas) == 1
    assert "INDEX_CATALOG_MISMATCH" in notas[0]
    assert "recusado" in notas[0]


def test_indice_de_outra_receita_de_texto_nao_e_encontrado_e_a_nota_diz_sem_indice(
    tmp_path: Path,
) -> None:
    """Receita divergente é ausência, não recusa — e a diferença é declarada de propósito.

    A resolução filtra por `text_recipe` (D3), então um índice de receita antiga simplesmente
    não é encontrado. Recusa é o outro caso, e as duas notas precisam continuar distintas: só
    a primeira diz "publique um índice", só a segunda diz "republique o que está lá".
    """
    client = _client(tmp_path)
    catalog = _catalog()
    _publish_catalog_and_index(client, catalog, key="sco", text_recipe=_OUTRA_RECEITA)
    prepared = _prepared(client, [catalog])

    response = _recompute(client, prepared["round_id"], version=prepared["version"])

    assert response.status_code == 200, response.text
    assert response.json()["matching"] == "lexical"
    assert any("sem índice de embeddings publicado" in nota for nota in _notes(response))
    assert not any("recusado" in nota for nota in _notes(response))
    # O índice ESTÁ publicado; o que ele não é, é da receita corrente.
    listagem = client.get(_INDEXES_PATH, headers=_operator("listar"))
    assert [entry["text_recipe"] for entry in listagem.json()["indexes"]] == [_OUTRA_RECEITA]


def test_indice_retirado_de_circulacao_volta_a_fonte_para_o_braco_lexico(
    tmp_path: Path,
) -> None:
    """Retirar não apaga, mas para de resolver — e a fonte volta ao estado normal sem índice.

    Fecha o ciclo administrativo da fatia 1 pelo lado de quem consome: o operador retira, e a
    próxima rodada degrada declaradamente em vez de continuar servindo um índice retirado.
    """
    client = _client(tmp_path)
    catalog = _catalog()
    _publish_catalog_and_index(client, catalog, key="sco")
    listagem = client.get(_INDEXES_PATH, headers=_operator("listar"))
    index_id = listagem.json()["indexes"][0]["reference_catalog_index_id"]
    retirada = client.post(f"{_INDEXES_PATH}/{index_id}/withdraw", headers=_operator("retirar-001"))
    assert retirada.status_code == 200, retirada.text
    prepared = _prepared(client, [catalog])

    response = _recompute(client, prepared["round_id"], version=prepared["version"])

    assert response.status_code == 200, response.text
    assert response.json()["matching"] == "lexical"
    assert any("sem índice de embeddings publicado" in nota for nota in _notes(response))


# --- 8. o evento da rodada carrega grandezas, nunca conteúdo ------------------------------


def test_o_evento_do_recompute_declara_o_gasto_do_braco_e_nenhum_conteudo(
    tmp_path: Path,
) -> None:
    """Critério 8: rodou?, model id, tokens, custo e fontes com índice — e nada mais.

    A conferência de que não há conteúdo é feita contra o texto INTEIRO do payload, e não
    campo a campo: campo novo que carregasse rótulo ou descrição passaria por uma lista de
    campos conhecidos e não passa por aqui.
    """
    client = _client(tmp_path)
    sco = _catalog(origin=PriceOrigin.SCO)
    emop = _catalog(origin=PriceOrigin.EMOP)
    _publish_catalog_and_index(client, sco, key="sco")
    prepared = _prepared(client, [sco, emop])

    assert _recompute(client, prepared["round_id"], version=prepared["version"]).status_code == 200

    with _database(client).sessions() as session:
        eventos = [
            record.payload_json
            for record in session.scalars(select(DomainEventRecord))
            if record.payload_json.get("action") == "ESTIMATE_CODE_SUGGESTIONS_RECOMPUTED"
        ]
    assert len(eventos) == 1
    payload = eventos[0]
    assert payload["semantic_arm_ran"] is True
    assert payload["model_id"] == FIXTURE_EMBEDDINGS_MODEL
    assert payload["input_tokens"] == 12
    assert payload["estimated_cost_usd"] == "0.0001"
    assert payload["sources_with_index"] == 1
    assert payload["sources_total"] == 2

    texto = str(payload)
    assert _LABEL not in texto
    assert "ALAMBRADO" not in texto.upper()
    assert "PRACA SINTETICA" not in texto.upper()


def test_o_evento_declara_positivamente_que_o_braco_nao_rodou(tmp_path: Path) -> None:
    """`arm_ran=False` é registro positivo: a vizinhança semântica não participou, e por quê.

    Sem isso, uma rodada degradada seria indistinguível no evento de uma rodada que nunca
    tentou — e o custo declarado da plataforma deixaria de ser conferível.
    """
    client = _client(tmp_path)
    catalog = _catalog()
    _arm(client, _ForbiddenEmbeddings())
    prepared = _round_with(client, [catalog])

    assert _recompute(client, prepared["round_id"], version=prepared["version"]).status_code == 200

    with _database(client).sessions() as session:
        payload = next(
            record.payload_json
            for record in session.scalars(select(DomainEventRecord))
            if record.payload_json.get("action") == "ESTIMATE_CODE_SUGGESTIONS_RECOMPUTED"
        )
    assert payload["semantic_arm_ran"] is False
    assert payload["semantic_reason"] == ENTITLEMENT_INACTIVE_REASON
    assert payload["model_id"] is None
    assert payload["input_tokens"] is None
    assert payload["estimated_cost_usd"] is None
    assert payload["sources_with_index"] == 0
    assert payload["sources_total"] == 1


# --- 9. nenhum vetor de consulta é persistido ---------------------------------------------


def test_nenhum_vetor_de_consulta_sobrevive_ao_recompute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Critério 9 e a emenda de 2026-08-28: o cache do ato é criado, usado e some.

    O diretório temporário é observado no ponto onde ele nasce, e a asserção é que ele NÃO
    exista depois da resposta. É a prova direta; a de comportamento vem no teste seguinte.

    O motivo da decisão é fronteira de dado: o vetor de um rótulo é derivado de texto do
    cliente, e persisti-lo criaria classe nova de dado privado para governar.
    """
    client = _client(tmp_path)
    catalog = _catalog()
    _publish_catalog_and_index(client, catalog, key="sco")
    prepared = _prepared(client, [catalog])

    criados: list[str] = []
    original = tempfile.TemporaryDirectory

    class _Observado(original):  # type: ignore[misc,valid-type]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            criados.append(self.name)

    monkeypatch.setattr(tempfile, "TemporaryDirectory", _Observado)
    response = _recompute(client, prepared["round_id"], version=prepared["version"])

    assert response.status_code == 200, response.text
    assert response.json()["matching"] == "hybrid"
    assert criados, "o recompute precisa criar o diretório do cache de consulta do ato"
    for caminho in criados:
        assert not Path(caminho).exists()

    # E nada de vetor de consulta no object store nem na revisão gravada.
    for chave, objeto in _store(client).objects.items():
        assert "query-embeddings" not in chave
        assert b"query-embeddings-v1" not in objeto.body
    with _database(client).sessions() as session:
        for revisao in session.scalars(select(EstimateRoundRevisionRecord)):
            assert "query" not in str(revisao.code_suggestions_json or {})


def test_recompute_repetido_paga_de_novo_porque_nada_foi_guardado(tmp_path: Path) -> None:
    """A consequência ACEITA da decisão, virada em teste: o custo é por ato, toda vez.

    Se algum dia alguém persistir o cache "para economizar", este teste cai — e cair é o
    ponto: a economia mudaria a fronteira de dado da feature, e essa mudança é de ADR.
    """
    client = _client(tmp_path)
    catalog = _catalog()
    _publish_catalog_and_index(client, catalog, key="sco")
    adapter = _FakeEmbeddings()
    prepared = _prepared(client, [catalog], adapter=adapter)

    primeiro = _recompute(client, prepared["round_id"], version=prepared["version"])
    assert primeiro.status_code == 200, primeiro.text
    segundo = _recompute(
        client, prepared["round_id"], version=primeiro.json()["version"], key="recalc-002"
    )

    assert segundo.status_code == 200, segundo.text
    assert len(adapter.calls) == 2
    assert adapter.calls[0] == adapter.calls[1] == (normalize_query_text(_LABEL),)


def test_duas_fontes_do_mesmo_modelo_dividem_o_cache_do_ato(tmp_path: Path) -> None:
    """Dentro de UM recompute, o rótulo é embutido uma vez só, ainda que as fontes sejam duas.

    O cache do ato é por MODELO, e não por fonte: duas fontes indexadas pelo mesmo modelo
    compartilham o espaço vetorial, e resolver os mesmos rótulos duas vezes pagaria duas
    vezes pelo mesmo vetor. Repagar entre ATOS é a decisão; repagar dentro de um seria só
    desperdício.
    """
    client = _client(tmp_path)
    sco = _catalog(origin=PriceOrigin.SCO)
    # SINAPI, e não EMOP: o acervo só distribui SCO/SINAPI/SICRO (ADR-0047 D8), e a EMOP
    # entra por upload de quem tem a licença dela — logo ela nunca tem índice publicado.
    sinapi = _catalog(origin=PriceOrigin.SINAPI, codes=[_SINAPI_CODE])
    _publish_catalog_and_index(client, sco, key="sco")
    _publish_catalog_and_index(client, sinapi, key="sinapi")
    adapter = _FakeEmbeddings()
    prepared = _prepared(client, [sco, sinapi], adapter=adapter)

    response = _recompute(client, prepared["round_id"], version=prepared["version"])

    assert response.status_code == 200, response.text
    suggestions = response.json()["suggestions"]
    assert len(suggestions["semantic"]) == 2
    assert len(adapter.calls) == 1


# --- a shortlist gravada é a mesma que a resposta declara ---------------------------------


def test_a_shortlist_hibrida_gravada_bate_com_a_resposta_e_com_o_digest(
    tmp_path: Path,
) -> None:
    """O artefato da cadeia de revisões é o que a resposta afirma, digest incluído.

    A resposta é derivada do documento gravado, e não montada ao lado dele: se as duas
    pudessem divergir, o `suggestions_sha256` deixaria de identificar o que a orçamentista
    viu.
    """
    client = _client(tmp_path)
    catalog = _catalog()
    _publish_catalog_and_index(client, catalog, key="sco")
    prepared = _prepared(client, [catalog])

    response = _recompute(client, prepared["round_id"], version=prepared["version"])

    assert response.status_code == 200, response.text
    with _database(client).sessions() as session:
        gravadas = [
            revisao.code_suggestions_json
            for revisao in session.scalars(
                select(EstimateRoundRevisionRecord).order_by(EstimateRoundRevisionRecord.version)
            )
            if revisao.code_suggestions_json is not None
        ]
    assert gravadas[-1] == response.json()["suggestions"]
    assert document_digest(gravadas[-1]) == response.json()["suggestions_sha256"]
    assert CodeSuggestionSet.model_validate(gravadas[-1]).semantic is not None


# --- a medição licitada usa o MESMO índice, achado por digest da fonte --------------------


def _valuation_round(client: TestClient, catalog: PriceCatalog) -> dict[str, Any]:
    """Rodada de medição com o catálogo instalado por upload e o takeoff revisado.

    O catálogo sobe pelo caminho do cliente, e não pelo acervo: é o que a medição de obra
    licitada faz (ADR-0027 — uma tabela, a do contrato). O índice é encontrado assim mesmo,
    porque a busca é por DIGEST DA FONTE (ADR-0054 D3) — é literalmente o caso que a decisão
    nomeia, "um upload do cliente cujos bytes sejam os mesmos".
    """
    payload = catalog.model_dump_json().encode("utf-8")
    presign = client.post(
        "/v1/uploads/presign",
        headers=_headers(key="up-medicao"),
        json={
            "filename": "catalogo.json",
            "content_type": "application/json",
            "size_bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        },
    )
    assert presign.status_code == 200, presign.text
    _store(client).put_direct(
        object_key=presign.json()["object_key"], body=payload, content_type="application/json"
    )
    created = client.post(
        "/v1/valuation-rounds",
        headers=_headers(key="rodada-medicao"),
        json={
            "worksite_key": "praca-sintetica-norte",
            "worksite_name": "PRACA SINTETICA NORTE",
            "reference_label": "MEDICAO 01/2026",
            "period_number": 1,
            "address": "RUA SINTETICA, S/N",
            "contract_label": "CONTRATO SINTETICO 01/2026",
            "catalog_upload_id": presign.json()["upload_id"],
        },
    )
    assert created.status_code == 201, created.text
    round_id = cast(str, created.json()["round_id"])

    packet = _packet()
    with _database(client).sessions() as session:
        record = session.get(ValuationRoundRecord, round_id)
        assert record is not None
        session.add(
            ValuationRoundRevisionRecord(
                id=str(new_uuid7()),
                tenant_id=_TENANT,
                round_id=round_id,
                version=1,
                created_by="valuation-extraction-v1",
                takeoff_packet_json=packet.model_dump(mode="json"),
                artifact_refs_json={
                    PLATE_IMAGE_REF: (
                        f"tenants/{_TENANT}/valuation-rounds/{round_id}/plate/page-001.png"
                    )
                },
                artifact_digests_json={PLATE_IMAGE_DIGEST: packet.image_sha256},
            )
        )
        record.version += 1
        session.commit()
        version = record.version

    decided = client.post(
        f"/v1/valuation-rounds/{round_id}/takeoff/decisions",
        headers=_headers(key="takeoff-medicao"),
        json={"base_version": version, "decisions": [{"item_id": _ITEM, "action": "confirm"}]},
    )
    assert decided.status_code == 200, decided.text
    return {"round_id": round_id, "version": decided.json()["version"]}


def test_o_recompute_da_medicao_tambem_roda_o_braco_semantico(tmp_path: Path) -> None:
    """A medição licitada não fica de fora: um catálogo, um índice, a mesma fusão.

    Sem nota nenhuma: `semantic_notes` publica o que NÃO rodou, e aqui rodou tudo. Quem
    conta que o braço participou é o artefato — `semantic` e `suggester_version` —, que é
    onde a auditoria procura e que sobrevive à resposta.
    """
    client = _client(tmp_path)
    catalog = _catalog()
    _publish_catalog_and_index(client, catalog, key="sco")
    _entitle(client)
    _arm(client, _FakeEmbeddings())
    prepared = _valuation_round(client, catalog)

    response = client.post(
        f"/v1/valuation-rounds/{prepared['round_id']}/code-suggestions/recompute",
        headers=_headers(key="recalc-medicao"),
        json={"base_version": prepared["version"]},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["matching"] == "hybrid"
    assert body["suggestions"]["suggester_version"].startswith(SCO_HYBRID_SUGGESTER_FAMILY)
    assert len(body["suggestions"]["semantic"]) == 1
    assert body["suggestions"]["semantic"][0]["catalog_sha256"] == catalog.source_sha256
    assert _notes(response) == []


def test_o_get_da_shortlist_da_medicao_tambem_nao_paga_nada(tmp_path: Path) -> None:
    """A invariante do `GET` vale nas DUAS jornadas, com a mesma prova por adapter proibido."""
    client = _client(tmp_path)
    catalog = _catalog()
    _publish_catalog_and_index(client, catalog, key="sco")
    _entitle(client)
    _arm(client, _ForbiddenEmbeddings())
    prepared = _valuation_round(client, catalog)

    response = client.get(
        f"/v1/valuation-rounds/{prepared['round_id']}/code-suggestions",
        headers=_headers(key="ler-medicao"),
    )

    assert response.status_code == 200, response.text
    assert response.json()["matching"] == "lexical"
    assert response.json()["suggestions"]["semantic"] is None
    assert any("recálculo explícito" in nota for nota in _notes(response))


def test_a_medicao_sem_indice_publicado_degrada_nomeando_o_catalogo_da_rodada(
    tmp_path: Path,
) -> None:
    """Sem índice para o catálogo do contrato, a medição segue léxica com o motivo certo."""
    client = _client(tmp_path)
    catalog = _catalog()
    _entitle(client)
    _arm(client, _FakeEmbeddings())
    prepared = _valuation_round(client, catalog)

    response = client.post(
        f"/v1/valuation-rounds/{prepared['round_id']}/code-suggestions/recompute",
        headers=_headers(key="recalc-medicao"),
        json={"base_version": prepared["version"]},
    )

    assert response.status_code == 200, response.text
    assert response.json()["matching"] == "lexical"
    assert _notes(response) == [
        "busca semântica indisponível: o catálogo da rodada (sco) sem índice de "
        "embeddings publicado"
    ]
