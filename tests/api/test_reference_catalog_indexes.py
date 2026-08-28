"""Índice de embeddings publicado pela plataforma (F-041 fatia 1, ADR-0054).

Irmã de `test_reference_catalogs.py`, e deliberadamente com a mesma forma: o índice repete
a exceção mais forte do schema — tabela pública **sem `tenant_id`** — e por isso repete
também a obrigação de testar a CONDIÇÃO que a sustenta antes de testar qualquer rota:

1. **nada na tabela deriva de conteúdo de cliente**, com a lista de colunas fechada e a
   contraprova de que as tabelas sem tenant continuam sendo exatamente duas;
2. **o objeto fica fora de `tenants/` e nenhuma rota o assina** — a guarda de prefixo de
   `signed_artifact_url` recusa uma chave do índice, e recusar é o comportamento correto:
   o servidor lê o índice, o cliente nunca o baixa.

Os demais blocos cobrem a administração (publicar, listar, retirar, sempre com o papel
exigido ANTES de qualquer lookup) e a LEITURA: achar o índice pelo par
(digest do catálogo, receita) e amarrá-lo com `bind_index_to_catalog`, que é a mesma
conferência do CLI e do servidor de medição — não uma cópia dela.

Ligar o braço semântico na shortlist é fatia própria e não está aqui: nesta fatia a cascata
continua chamando o matcher com `SemanticArm(..., "unavailable", ...)`.

Nenhum índice de verdade é construído: `index-catalog` é comando pago, e o que a suíte usa
é a fábrica determinística e offline de `sco_matching_fixtures` — mesmo contrato de
documento, vetores fabricados por hash de radicais. Ela prova o caminho do artefato, nunca
a qualidade semântica; a medida real é o golden com o índice pago.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from croquito_api import main as api_main
from croquito_api.config import ApiSettings, JourneyAvailabilitySettings, StorageFlavor
from croquito_api.database import (
    AuditRecord,
    Base,
    Database,
    ReferenceCatalogEmbeddingRecord,
    UploadRecord,
)
from croquito_api.main import create_app
from croquito_api.reference_catalog_indexes import (
    CATALOG_INDEX_MAX_BYTES,
    REFERENCE_CATALOG_INDEX_PREFIX,
    STATUS_AVAILABLE,
    STATUS_WITHDRAWN,
    SemanticIndexCache,
    published_index_for_catalog,
    read_semantic_index,
    reference_catalog_index_key,
    resolve_semantic_index,
)
from croquito_api.valuation_rounds import CATALOG_MAX_BYTES, signed_artifact_url
from croquito_valuation.errors import ValuationValidationError
from croquito_valuation.models import PriceCatalog, PriceCatalogEntry, PriceOrigin
from croquito_worker.valuation.sco_matching import INDEX_TEXT_RECIPE, index_document
from croquito_worker.valuation.sco_matching_fixtures import (
    FIXTURE_EMBEDDINGS_DIMS,
    FIXTURE_EMBEDDINGS_MODEL,
    FIXTURE_EMBEDDINGS_PROVIDER,
    fixture_catalog_index,
    fixture_semantic_index,
)
from tests.fakes import FakeObjectStore

_OPERATOR_TENANT = "tenant-plataforma"
_CLIENT_TENANT = "tenant-scalle"
_OTHER_CLIENT_TENANT = "tenant-toca"

_ACERVO_PATH = "/v1/platform/reference-catalogs"
_INDEXES_PATH = "/v1/platform/reference-catalog-indexes"
_INDEX_PRESIGN_PATH = f"{_INDEXES_PATH}/presign"

_UUID_INEXISTENTE = "0192f000-0000-7000-8000-000000000000"

#: O índice real do catálogo do SCO, construído por ato humano em 2026-08-25: 4.964 itens x
#: 1.536 dimensões (ADR-0054). É a medição que justifica o teto próprio, e por isso ela
#: entra no teste como número, não como lembrança de docstring.
_INDICE_REAL_MEDIDO_BYTES: Final = 40_700_000

#: Cada coluna do índice e de onde ela vem. É a lista que a decisão 1 do ADR-0047,
#: estendida pelo ADR-0054, obriga a manter fechada: enquanto toda origem for "estava dentro
#: do documento publicado" ou "é o ato do operador", nada aqui deriva de conteúdo de cliente
#: e a ausência de `tenant_id` continua sustentada. Repare que não há sequer um campo
#: digitado — o índice não tem nome de exibição, porque a identidade dele é o modelo, a
#: receita e o catálogo que ele indexa.
_ORIGEM_DE_CADA_COLUNA: Final[dict[str, str]] = {
    "id": "gerado pelo servidor (UUIDv7)",
    "reference_catalog_id": "entrada do acervo citada no ato de publicar",
    "catalog_source_sha256": "lido de dentro do catalog-embeddings.json publicado",
    "text_recipe": "lido de dentro do catalog-embeddings.json publicado",
    "provider": "lido de dentro do catalog-embeddings.json publicado",
    "model_id": "lido de dentro do catalog-embeddings.json publicado",
    "dims": "lido de dentro do catalog-embeddings.json publicado",
    "code_count": "contado no catalog-embeddings.json publicado",
    "object_key": "derivado do digest do arquivo publicado",
    "object_sha256": "digest dos bytes do arquivo publicado pelo operador",
    "status": "estado de circulação, decidido por ato do operador",
    "published_by": "identidade do operador que publicou",
    "published_at": "relógio do servidor no ato de publicar",
    "withdrawn_at": "relógio do servidor no ato de retirar",
}


# --- montagem ---------------------------------------------------------------------------


def _app(tmp_path: Path, *, storage_flavor: StorageFlavor = "s3") -> tuple[TestClient, Database]:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'indices.db'}"
    database = Database(database_url)
    database.create_schema()
    settings = ApiSettings(
        database_url=database_url,
        artifact_bucket="croquito-test-artifacts",
        aws_region="sa-east-1",
        aws_endpoint_url="http://localhost:4566",
        queue_url=None,
        oidc_issuer=None,
        oidc_audience=None,
        web_origin="http://localhost:5173",
        allow_test_tokens=True,
        storage_flavor=storage_flavor,
        journeys=JourneyAvailabilitySettings(),
    )
    application = create_app(settings=settings, database=database)
    application.state.artifact_store = FakeObjectStore()
    return TestClient(application), database


def _store(client: TestClient) -> FakeObjectStore:
    return cast(FakeObjectStore, cast(Any, client.app).state.artifact_store)


def _index_cache(client: TestClient) -> SemanticIndexCache:
    """O cache preso à aplicação, e não um novo: é ele que a fatia 2 vai usar."""
    return cast(SemanticIndexCache, cast(Any, client.app).state.semantic_index_cache)


def _headers(tenant: str, roles: str, *, key: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer test:{tenant}:pessoa-sintetica:{roles}"}
    if key is not None:
        headers["Idempotency-Key"] = key
    return headers


def _operator(key: str | None = None) -> dict[str, str]:
    return _headers(_OPERATOR_TENANT, "platform_operator", key=key)


def _catalog(
    *, source_seed: str = "planilha-sco", reference_month: str = "2026-07"
) -> PriceCatalog:
    """Catálogo sintético de duas entradas, no formato que o CLI de importação produz."""
    return PriceCatalog(
        source_label="SCO-RIO FGV06 DESONERADO",
        reference_month=reference_month,
        source_sha256=hashlib.sha256(source_seed.encode()).hexdigest(),
        origin=PriceOrigin.SCO,
        entries=[
            PriceCatalogEntry(
                code="CE04100010(/)",
                description="ALAMBRADO GALVANIZADO",
                unit="m",
                unit_price="50.00",
                family_code="CE",
                family_name="SERVICOS SINTETICOS",
                subgroup_code="CE0410",
                subgroup_name="ITENS SINTETICOS",
                origin=PriceOrigin.SCO,
            ),
            PriceCatalogEntry(
                code="IP49150409(/)",
                description="REFLETOR DE LED EM POSTE EXISTENTE",
                unit="un",
                unit_price="900.00",
                family_code="IP",
                family_name="ILUMINACAO SINTETICA",
                subgroup_code="IP4915",
                subgroup_name="ITENS SINTETICOS",
                origin=PriceOrigin.SCO,
            ),
        ],
    )


def _index_bytes(catalog: PriceCatalog, *, text_recipe: str | None = None) -> bytes:
    """Documento de índice fabricado — offline, determinístico e sem chamada paga."""
    document = fixture_catalog_index(catalog)
    if text_recipe is not None:
        document = document.model_copy(update={"text_recipe": text_recipe})
    return index_document(document).encode("utf-8")


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


def _publish_catalog(client: TestClient, catalog: PriceCatalog, *, key: str = "catalogo") -> str:
    """Publica o catálogo pelo acervo e devolve o `reference_catalog_id`.

    O índice tem FK para o acervo, e o `Database` liga `PRAGMA foreign_keys=ON` no SQLite:
    publicar o catálogo primeiro não é conveniência de fixture, é a ordem que o schema exige.
    """
    payload = catalog.model_dump_json().encode("utf-8")
    upload_id = _presign_and_put(
        client, path=f"{_ACERVO_PATH}/presign", payload=payload, key=f"cat-{key}"
    )
    resposta = client.post(
        _ACERVO_PATH,
        headers=_operator(f"cat-{key}"),
        json={"upload_id": upload_id, "display_name": "SCO-Rio FGV06 desonerado"},
    )
    assert resposta.status_code == 201, resposta.text
    return cast(str, resposta.json()["reference_catalog_id"])


def _publish_index(
    client: TestClient,
    *,
    reference_catalog_id: str,
    payload: bytes,
    key: str = "indice-001",
) -> Any:
    upload_id = _presign_and_put(client, path=_INDEX_PRESIGN_PATH, payload=payload, key=key)
    return client.post(
        _INDEXES_PATH,
        headers=_operator(key),
        json={"upload_id": upload_id, "reference_catalog_id": reference_catalog_id},
    )


def _publicado(client: TestClient, *, key: str = "indice-001") -> tuple[PriceCatalog, Any]:
    """Catálogo publicado no acervo e o índice dele publicado em seguida."""
    catalog = _catalog()
    catalog_id = _publish_catalog(client, catalog, key=key)
    resposta = _publish_index(
        client, reference_catalog_id=catalog_id, payload=_index_bytes(catalog), key=key
    )
    assert resposta.status_code == 201, resposta.text
    return catalog, resposta


# --- a condição que sustenta a tabela sem `tenant_id` -------------------------------------


def test_nenhuma_coluna_do_indice_deriva_de_conteudo_de_cliente() -> None:
    """A guarda escrita do ADR-0054 D2, verificada em vez de confiada à memória.

    Duas afirmações, e as duas precisam continuar verdadeiras: o índice não tem `tenant_id`
    e cada coluna dele vem do documento público que o operador publicou ou do próprio ato de
    publicar; e as tabelas sem `tenant_id` continuam sendo exatamente DUAS — o catálogo
    público e o índice dele. A terceira exceção, se um dia houver, é decisão de arquitetura.
    """
    colunas = {coluna.name for coluna in ReferenceCatalogEmbeddingRecord.__table__.columns}

    assert "tenant_id" not in colunas
    assert colunas == set(_ORIGEM_DE_CADA_COLUNA)

    sem_tenant = {
        tabela.name for tabela in Base.metadata.sorted_tables if "tenant_id" not in tabela.columns
    }
    assert sem_tenant == {"reference_catalogs", "reference_catalog_embeddings"}


def test_a_chave_do_indice_fica_fora_do_prefixo_do_tenant_e_nao_e_assinavel(
    tmp_path: Path,
) -> None:
    """`signed_artifact_url` RECUSA uma chave do índice, e recusar é o comportamento certo.

    A guarda não é afrouxada nem contornada: o servidor lê o índice, o cliente nunca o
    baixa. A recusa vale para qualquer tenant, inclusive o do operador que publicou.
    """
    client, _ = _app(tmp_path)
    _, publicacao = _publicado(client)
    chave = reference_catalog_index_key(object_sha256=publicacao.json()["object_sha256"])
    store = _store(client)

    assert chave.startswith(REFERENCE_CATALOG_INDEX_PREFIX)
    assert not chave.startswith("tenants/")
    for tenant in (_CLIENT_TENANT, _OTHER_CLIENT_TENANT, _OPERATOR_TENANT):
        assert signed_artifact_url(store, object_key=chave, tenant_id=tenant) is None


def test_nenhuma_resposta_do_indice_carrega_chave_de_objeto_url_assinada_nem_vetor(
    tmp_path: Path,
) -> None:
    client, _ = _app(tmp_path)
    _, publicacao = _publicado(client)
    listagem = client.get(_INDEXES_PATH, headers=_operator())
    retirada = client.post(
        f"{_INDEXES_PATH}/{publicacao.json()['reference_catalog_index_id']}/withdraw",
        headers=_operator("retirada-001"),
    )

    for resposta in (publicacao, listagem, retirada):
        assert resposta.status_code in {200, 201}, resposta.text
        assert REFERENCE_CATALOG_INDEX_PREFIX not in resposta.text
        assert "http" not in resposta.text
        assert "object_key" not in resposta.text
        assert "vectors_base64" not in resposta.text


def test_a_chave_do_indice_recusa_digest_que_nao_e_sha256() -> None:
    """Montar caminho a partir de texto que ninguém olhou é como um `..` entra numa chave."""
    for invalido in ("../segredo", "NAO-E-DIGEST", "a" * 63, datetime.now(UTC).isoformat()):
        try:
            reference_catalog_index_key(object_sha256=invalido)
        except ValueError:
            continue
        raise AssertionError(f"digest inválido aceito: {invalido}")


# --- publicar -----------------------------------------------------------------------------


def test_publicar_grava_a_linha_e_o_objeto_fora_de_tenants(tmp_path: Path) -> None:
    """O caminho feliz: o objeto vai para o prefixo do índice e a linha lê o DOCUMENTO.

    Nada da linha é digitado — provider, modelo, dimensões, receita, contagem e digest do
    catálogo indexado saem todos de dentro do arquivo. É essa propriedade que impede um
    índice de ser publicado com uma receita que ele não tem, degradando a busca em silêncio.
    """
    client, database = _app(tmp_path)
    catalog = _catalog()
    catalog_id = _publish_catalog(client, catalog)
    conteudo = _index_bytes(catalog)

    publicacao = _publish_index(
        client, reference_catalog_id=catalog_id, payload=conteudo, key="feliz"
    )

    assert publicacao.status_code == 201, publicacao.text
    corpo = publicacao.json()
    assert corpo["reference_catalog_id"] == catalog_id
    assert corpo["catalog_source_sha256"] == catalog.source_sha256
    assert corpo["text_recipe"] == INDEX_TEXT_RECIPE
    assert corpo["provider"] == FIXTURE_EMBEDDINGS_PROVIDER
    assert corpo["model_id"] == FIXTURE_EMBEDDINGS_MODEL
    assert corpo["dims"] == FIXTURE_EMBEDDINGS_DIMS
    assert corpo["code_count"] == len(catalog.entries)
    assert corpo["available"] is True
    chave = reference_catalog_index_key(object_sha256=corpo["object_sha256"])
    assert not chave.startswith("tenants/")
    assert _store(client).read_object(object_key=chave, max_bytes=len(conteudo) + 1) == conteudo
    with database.sessions() as session:
        registro = session.scalars(select(ReferenceCatalogEmbeddingRecord)).one()
        assert registro.object_key == chave
        assert registro.status == STATUS_AVAILABLE
        assert registro.published_by == "pessoa-sintetica"
        assert registro.withdrawn_at is None


def test_republicar_o_mesmo_indice_e_recusado_por_codigo_estavel(tmp_path: Path) -> None:
    """Publicação é imutável e endereçada por digest; índice reconstruído é entrada NOVA."""
    client, database = _app(tmp_path)
    catalog = _catalog()
    catalog_id = _publish_catalog(client, catalog)
    conteudo = _index_bytes(catalog)

    primeira = _publish_index(
        client, reference_catalog_id=catalog_id, payload=conteudo, key="primeira"
    )
    repetida = _publish_index(
        client, reference_catalog_id=catalog_id, payload=conteudo, key="repetida"
    )
    outra_receita = _publish_index(
        client,
        reference_catalog_id=catalog_id,
        payload=_index_bytes(catalog, text_recipe="description-unit-v2"),
        key="v2",
    )

    assert primeira.status_code == 201, primeira.text
    assert repetida.status_code == 409
    assert repetida.json()["code"] == "REFERENCE_CATALOG_INDEX_ALREADY_PUBLISHED"
    assert (
        repetida.json()["detail"]["details"]["reference_catalog_index_id"]
        == primeira.json()["reference_catalog_index_id"]
    )
    assert outra_receita.status_code == 201, outra_receita.text
    with database.sessions() as session:
        receitas = {
            registro.text_recipe
            for registro in session.scalars(select(ReferenceCatalogEmbeddingRecord))
        }
        assert receitas == {INDEX_TEXT_RECIPE, "description-unit-v2"}


def test_indice_construido_sobre_outro_catalogo_e_recusado(tmp_path: Path) -> None:
    """O `catalog_sha256` de dentro do documento tem de bater com o catálogo citado.

    Sem esta conferência, o acervo passaria a oferecer um índice cujos códigos o catálogo
    escolhido nem tem — e a recusa fechada só apareceria muito depois, na amarração, como
    degradação sem causa visível. Nada é gravado: nem linha, nem objeto.
    """
    client, database = _app(tmp_path)
    catalog = _catalog()
    catalog_id = _publish_catalog(client, catalog)
    outro = _catalog(source_seed="planilha-de-outra-obra")

    resposta = _publish_index(
        client, reference_catalog_id=catalog_id, payload=_index_bytes(outro), key="alheio"
    )

    assert resposta.status_code == 422
    assert resposta.json()["code"] == "REFERENCE_CATALOG_INDEX_CATALOG_MISMATCH"
    detalhes = resposta.json()["detail"]["details"]
    assert detalhes["index_catalog_sha256"] == outro.source_sha256
    assert detalhes["catalog_source_sha256"] == catalog.source_sha256
    assert not any(
        chave.startswith(REFERENCE_CATALOG_INDEX_PREFIX) for chave in _store(client).objects
    )
    with database.sessions() as session:
        assert session.query(ReferenceCatalogEmbeddingRecord).count() == 0


def test_publicar_indice_de_catalogo_inexistente_e_404(tmp_path: Path) -> None:
    client, database = _app(tmp_path)
    catalog = _catalog()
    _publish_catalog(client, catalog)

    resposta = _publish_index(
        client,
        reference_catalog_id=_UUID_INEXISTENTE,
        payload=_index_bytes(catalog),
        key="fantasma",
    )

    assert resposta.status_code == 404
    assert resposta.json()["code"] == "NOT_FOUND"
    with database.sessions() as session:
        assert session.query(ReferenceCatalogEmbeddingRecord).count() == 0


def test_documento_que_nao_e_indice_e_recusado_sem_devolver_o_conteudo(tmp_path: Path) -> None:
    """Recusa de contrato com o código de DOMÍNIO, e nada do arquivo na resposta.

    Dois documentos ruins de naturezas diferentes, e os dois recusam com o mesmo código
    estável: um que nem tem a forma do índice, e um cujo invariante próprio falha — os
    vetores não batem com códigos vezes dimensões, que é o `INDEX_PAYLOAD_INVALID` levantado
    de dentro do validador do modelo e recuperado de dentro do encapsulamento do pydantic.
    """
    client, database = _app(tmp_path)
    catalog = _catalog()
    catalog_id = _publish_catalog(client, catalog)
    truncado = fixture_catalog_index(catalog).model_dump()
    truncado["codes"] = truncado["codes"][:1]

    sem_forma = _publish_index(
        client,
        reference_catalog_id=catalog_id,
        payload=b'{"schema_version": "catalog-embeddings-v1", "codes": []}',
        key="lixo",
    )
    invariante = _publish_index(
        client,
        reference_catalog_id=catalog_id,
        payload=json.dumps(truncado).encode("utf-8"),
        key="truncado",
    )

    for resposta in (sem_forma, invariante):
        assert resposta.status_code == 422, resposta.text
        assert resposta.json()["code"] == "REFERENCE_CATALOG_INDEX_UNREADABLE"
        assert resposta.json()["detail"]["details"] == {"code": "INDEX_PAYLOAD_INVALID"}
        assert "vectors_base64" not in resposta.text
    with database.sessions() as session:
        assert session.query(ReferenceCatalogEmbeddingRecord).count() == 0


def test_o_teto_do_indice_e_proprio_e_cobre_o_indice_real_medido() -> None:
    """O teto novo não é precaução: é requisito medido (ADR-0054, consequências).

    O índice real do catálogo do SCO tem 40,7 MB e o teto do CATÁLOGO é 32 MiB — o artefato
    de verdade não passa pelo limite existente. Por isso constante própria, e não
    afrouxamento da outra: são artefatos diferentes, com tamanhos e riscos diferentes.
    """
    assert CATALOG_INDEX_MAX_BYTES == 64 * 1024 * 1024
    assert CATALOG_MAX_BYTES < _INDICE_REAL_MEDIDO_BYTES < CATALOG_INDEX_MAX_BYTES


def test_indice_maior_que_o_teto_e_recusado_por_inteiro_e_nao_truncado(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Passar do teto recusa o documento POR EXTENSO, com a causa nomeada.

    Truncar seria pior que recusar: o documento cortado desserializaria como JSON inválido e
    a causa verdadeira — o tamanho — sumiria numa recusa de contrato. O teto é reduzido aqui
    em vez de fabricarmos 64 MiB de bytes: o que está sob teste é o mecanismo da recusa, e o
    valor real do teto é conferido pelo teste da constante, ao lado da medição que o
    justifica.
    """
    client, database = _app(tmp_path)
    catalog = _catalog()
    catalog_id = _publish_catalog(client, catalog)
    conteudo = _index_bytes(catalog)
    monkeypatch.setattr(api_main, "CATALOG_INDEX_MAX_BYTES", 512)
    assert len(conteudo) > 512

    resposta = _publish_index(
        client, reference_catalog_id=catalog_id, payload=conteudo, key="grande"
    )

    assert resposta.status_code == 422
    assert resposta.json()["code"] == "REFERENCE_CATALOG_INDEX_TOO_LARGE"
    assert resposta.json()["detail"]["details"] == {
        "max_bytes": 512,
        "size_bytes": len(conteudo),
    }
    assert not any(
        chave.startswith(REFERENCE_CATALOG_INDEX_PREFIX) for chave in _store(client).objects
    )
    with database.sessions() as session:
        assert session.query(ReferenceCatalogEmbeddingRecord).count() == 0


def test_publicar_exige_chave_de_idempotencia_e_repete_a_mesma_resposta(tmp_path: Path) -> None:
    client, database = _app(tmp_path)
    catalog = _catalog()
    catalog_id = _publish_catalog(client, catalog)
    upload_id = _presign_and_put(
        client, path=_INDEX_PRESIGN_PATH, payload=_index_bytes(catalog), key="idempotencia"
    )
    corpo = {"upload_id": upload_id, "reference_catalog_id": catalog_id}

    sem_chave = client.post(_INDEXES_PATH, headers=_operator(), json=corpo)
    primeira = client.post(_INDEXES_PATH, headers=_operator("mesma-chave"), json=corpo)
    replay = client.post(_INDEXES_PATH, headers=_operator("mesma-chave"), json=corpo)

    assert sem_chave.status_code == 400
    assert primeira.status_code == 201, primeira.text
    assert replay.json() == primeira.json()
    with database.sessions() as session:
        assert session.query(ReferenceCatalogEmbeddingRecord).count() == 1


def test_publicar_audita_no_tenant_do_operador_com_a_receita_e_o_modelo(tmp_path: Path) -> None:
    """O ato não tem tenant alvo, e o fato verdadeiro é quem o fez — com o que decide a
    aceitação do índice na amarração (receita e modelo) nos detalhes."""
    client, database = _app(tmp_path)

    _, publicacao = _publicado(client)

    with database.sessions() as session:
        evento = session.scalars(
            select(AuditRecord).where(AuditRecord.action == "REFERENCE_CATALOG_INDEX_PUBLISHED")
        ).one()
        assert evento.tenant_id == _OPERATOR_TENANT
        assert evento.resource_type == "reference_catalog_index"
        assert evento.resource_id == publicacao.json()["reference_catalog_index_id"]
        assert evento.metadata_json["text_recipe"] == INDEX_TEXT_RECIPE
        assert evento.metadata_json["model_id"] == FIXTURE_EMBEDDINGS_MODEL


# --- presign ------------------------------------------------------------------------------


def test_o_presign_do_indice_exige_platform_operator_antes_de_gravar(tmp_path: Path) -> None:
    """Papel antes de qualquer coisa: `403` e nenhum `UploadRecord`, nem chave assinada."""
    client, database = _app(tmp_path)
    conteudo = _index_bytes(_catalog())

    resposta = client.post(
        _INDEX_PRESIGN_PATH,
        headers=_headers(_CLIENT_TENANT, "orcamentista", key="presign-sem-papel"),
        json={
            "filename": "indice.json",
            "size_bytes": len(conteudo),
            "sha256": hashlib.sha256(conteudo).hexdigest(),
        },
    )

    assert resposta.status_code == 403
    assert resposta.json()["code"] == "FORBIDDEN"
    assert "url" not in resposta.json()
    with database.sessions() as session:
        assert session.query(UploadRecord).count() == 0


def test_o_presign_do_indice_fixa_o_tipo_em_json_e_grava_no_tenant_do_operador(
    tmp_path: Path,
) -> None:
    """O objeto ainda é do operador: só a publicação o move para o prefixo do índice.

    Assinar direto para dentro de `platform/reference-catalog-indexes/` poria lá um arquivo
    que ninguém leu — a conferência do digest, do contrato e do catálogo acontece ao publicar.
    """
    client, database = _app(tmp_path)
    conteudo = _index_bytes(_catalog())
    base = {"size_bytes": len(conteudo), "sha256": hashlib.sha256(conteudo).hexdigest()}

    declarando_tipo = client.post(
        _INDEX_PRESIGN_PATH,
        headers=_operator("tipo-declarado"),
        json={**base, "filename": "indice.json", "content_type": "application/json"},
    )
    nome_de_pdf = client.post(
        _INDEX_PRESIGN_PATH, headers=_operator("nome-pdf"), json={**base, "filename": "prancha.pdf"}
    )
    valido = client.post(
        _INDEX_PRESIGN_PATH, headers=_operator("valido"), json={**base, "filename": "indice.json"}
    )

    assert declarando_tipo.status_code == 422
    assert nome_de_pdf.status_code == 422
    assert nome_de_pdf.json()["code"] == "INVALID_UPLOAD"
    assert valido.status_code == 200, valido.text
    corpo = valido.json()
    assert (
        corpo["object_key"]
        == f"tenants/{_OPERATOR_TENANT}/uploads/{corpo['upload_id']}/indice.json"
    )
    assert not corpo["object_key"].startswith(REFERENCE_CATALOG_INDEX_PREFIX)
    with database.sessions() as session:
        registro = session.scalars(select(UploadRecord)).one()
        assert registro.tenant_id == _OPERATOR_TENANT
        assert registro.content_type == "application/json"


# --- listar e retirar de circulação --------------------------------------------------------


def test_listagem_traz_todos_os_indices_inclusive_os_retirados(tmp_path: Path) -> None:
    client, _ = _app(tmp_path)
    catalog = _catalog()
    catalog_id = _publish_catalog(client, catalog)
    v1 = _publish_index(
        client, reference_catalog_id=catalog_id, payload=_index_bytes(catalog), key="v1"
    )
    v2 = _publish_index(
        client,
        reference_catalog_id=catalog_id,
        payload=_index_bytes(catalog, text_recipe="description-unit-v2"),
        key="v2",
    )
    retirada = client.post(
        f"{_INDEXES_PATH}/{v1.json()['reference_catalog_index_id']}/withdraw",
        headers=_operator("retira-v1"),
    )
    assert retirada.status_code == 200, retirada.text

    listagem = client.get(_INDEXES_PATH, headers=_operator())

    assert listagem.status_code == 200
    indices = listagem.json()["indexes"]
    assert [indice["text_recipe"] for indice in indices] == [
        INDEX_TEXT_RECIPE,
        "description-unit-v2",
    ]
    assert [indice["available"] for indice in indices] == [False, True]
    assert indices[0]["reference_catalog_index_id"] == v1.json()["reference_catalog_index_id"]
    assert indices[0]["withdrawn_at"] is not None
    assert indices[1]["reference_catalog_index_id"] == v2.json()["reference_catalog_index_id"]


def test_retirar_carimba_a_data_sem_apagar_linha_nem_objeto(tmp_path: Path) -> None:
    """Retirar é marcar estado: a shortlist já gravada cita o digest do índice que a fez."""
    client, database = _app(tmp_path)
    catalog, publicacao = _publicado(client)
    indice_id = publicacao.json()["reference_catalog_index_id"]
    chave = reference_catalog_index_key(object_sha256=publicacao.json()["object_sha256"])

    retirada = client.post(f"{_INDEXES_PATH}/{indice_id}/withdraw", headers=_operator("retira"))

    assert retirada.status_code == 200, retirada.text
    assert retirada.json()["available"] is False
    assert retirada.json()["withdrawn_at"] is not None
    assert _store(client).read_object(object_key=chave, max_bytes=10_000_000) is not None
    with database.sessions() as session:
        registro = session.scalars(select(ReferenceCatalogEmbeddingRecord)).one()
        assert registro.id == indice_id
        assert registro.status == STATUS_WITHDRAWN
        assert registro.object_key == chave
        # E a resolução deixa de encontrá-lo: a fonte volta a contribuir só com o léxico,
        # que é estado normal e não erro (ADR-0054 D6).
        assert (
            published_index_for_catalog(session, catalog_source_sha256=catalog.source_sha256)
            is None
        )


def test_retirar_o_que_ja_saiu_de_circulacao_preserva_a_data_do_ato_original(
    tmp_path: Path,
) -> None:
    client, database = _app(tmp_path)
    _, publicacao = _publicado(client)
    caminho = f"{_INDEXES_PATH}/{publicacao.json()['reference_catalog_index_id']}/withdraw"

    primeira = client.post(caminho, headers=_operator("retira-1"))
    with database.sessions() as session:
        carimbo = session.scalars(select(ReferenceCatalogEmbeddingRecord)).one().withdrawn_at
    repetida = client.post(caminho, headers=_operator("retira-2"))

    assert primeira.status_code == 200
    assert repetida.status_code == 200
    with database.sessions() as session:
        # A data verdadeira é a da retirada, não a da última vez que alguém repetiu o pedido.
        assert (
            session.scalars(select(ReferenceCatalogEmbeddingRecord)).one().withdrawn_at == carimbo
        )
    with database.sessions() as session:
        eventos = session.scalars(
            select(AuditRecord).where(AuditRecord.action == "REFERENCE_CATALOG_INDEX_WITHDRAWN")
        ).all()
        assert len(eventos) == 1


def test_retirar_indice_inexistente_e_404(tmp_path: Path) -> None:
    client, _ = _app(tmp_path)

    resposta = client.post(
        f"{_INDEXES_PATH}/{_UUID_INEXISTENTE}/withdraw", headers=_operator("retira-fantasma")
    )

    assert resposta.status_code == 404
    assert resposta.json()["code"] == "NOT_FOUND"


# --- papel --------------------------------------------------------------------------------


def test_as_rotas_do_indice_exigem_platform_operator_antes_de_qualquer_lookup(
    tmp_path: Path,
) -> None:
    """Quem não tem o papel recebe `403` e não descobre o que existe — nem se existe.

    A recusa é a mesma para um id que existe e para um que não existe, e nada muda: é o que
    impede a diferença entre `403` e `404` de virar leitura do acervo por quem não pode lê-lo.
    """
    client, database = _app(tmp_path)
    catalog = _catalog()
    catalog_id = _publish_catalog(client, catalog)
    publicado = _publish_index(
        client, reference_catalog_id=catalog_id, payload=_index_bytes(catalog), key="do-operador"
    ).json()["reference_catalog_index_id"]
    upload_id = _presign_and_put(
        client,
        path=_INDEX_PRESIGN_PATH,
        payload=_index_bytes(_catalog(source_seed="outra")),
        key="tentativa",
    )
    sem_papel = _headers(_CLIENT_TENANT, "orcamentista", key="tentativa-sem-papel")

    listagem = client.get(_INDEXES_PATH, headers=_headers(_CLIENT_TENANT, "orcamentista"))
    publicacao = client.post(
        _INDEXES_PATH,
        headers=sem_papel,
        json={"upload_id": upload_id, "reference_catalog_id": catalog_id},
    )
    existente = client.post(f"{_INDEXES_PATH}/{publicado}/withdraw", headers=sem_papel)
    inexistente = client.post(f"{_INDEXES_PATH}/{_UUID_INEXISTENTE}/withdraw", headers=sem_papel)

    for resposta in (listagem, publicacao, existente, inexistente):
        assert resposta.status_code == 403
        assert resposta.json()["code"] == "FORBIDDEN"
    with database.sessions() as session:
        registro = session.scalars(select(ReferenceCatalogEmbeddingRecord)).one()
        assert registro.status == STATUS_AVAILABLE
        assert registro.withdrawn_at is None


# --- resolver o índice para leitura --------------------------------------------------------


def test_o_resolvedor_acha_o_indice_pelo_digest_do_catalogo_e_pela_receita(
    tmp_path: Path,
) -> None:
    """A busca é por DIGEST da fonte, não por proveniência (ADR-0054 D3).

    O `SemanticIndex` devolvido já vem amarrado: códigos na ordem do catálogo, matriz com
    uma linha por código e o `index_sha256` do objeto publicado — pronto para o kNN, sem que
    nada aqui reimplemente a conferência de `bind_index_to_catalog`.
    """
    client, database = _app(tmp_path)
    catalog, publicacao = _publicado(client)

    with database.sessions() as session:
        indice = resolve_semantic_index(
            session,
            _store(client),
            catalog=catalog,
            cache=_index_cache(client),
        )

    assert indice is not None
    assert indice.catalog_sha256 == catalog.source_sha256
    assert indice.index_sha256 == publicacao.json()["object_sha256"]
    assert indice.codes == tuple(entry.code for entry in catalog.entries)
    assert indice.matrix.shape == (len(catalog.entries), FIXTURE_EMBEDDINGS_DIMS)


def test_o_resolvedor_devolve_nada_quando_a_fonte_nao_tem_indice(tmp_path: Path) -> None:
    """Cobertura parcial é estado NORMAL (ADR-0054 D6): ausência não é exceção.

    Duas ausências diferentes provam a mesma coisa: catálogo sem índice nenhum, e catálogo
    com índice publicado sob outra receita — que é o desfecho de errar a ordem do deploy
    coordenado quando a receita muda.
    """
    client, database = _app(tmp_path)
    catalog = _catalog()
    catalog_id = _publish_catalog(client, catalog)
    store = _store(client)

    with database.sessions() as session:
        sem_indice = resolve_semantic_index(
            session, store, catalog=catalog, cache=SemanticIndexCache()
        )
    resposta = _publish_index(
        client,
        reference_catalog_id=catalog_id,
        payload=_index_bytes(catalog, text_recipe="description-unit-v2"),
        key="so-v2",
    )
    assert resposta.status_code == 201, resposta.text
    with database.sessions() as session:
        outra_receita = resolve_semantic_index(
            session, store, catalog=catalog, cache=SemanticIndexCache()
        )

    assert sem_indice is None
    assert outra_receita is None


def test_a_amarracao_recusa_indice_de_outro_catalogo_sem_reimplementar_a_conferencia(
    tmp_path: Path,
) -> None:
    """`bind_index_to_catalog` é a MESMA conferência do CLI e do servidor de medição.

    A rota já recusa publicar índice de outro catálogo, mas a recusa da leitura é a rede
    embaixo dela: um catálogo reimportado sob o mesmo digest de objeto, ou uma linha
    manipulada fora da rota, não podem produzir uma shortlist com códigos de outro contrato.
    """
    client, database = _app(tmp_path)
    catalog, _ = _publicado(client)
    outro = _catalog(source_seed="planilha-de-outra-obra")

    with database.sessions() as session:
        registro = session.scalars(select(ReferenceCatalogEmbeddingRecord)).one()
        with pytest.raises(ValuationValidationError) as recusa:
            read_semantic_index(
                _store(client), record=registro, catalog=outro, cache=SemanticIndexCache()
            )

    assert recusa.value.code == "INDEX_CATALOG_MISMATCH"
    assert catalog.source_sha256 != outro.source_sha256


def test_a_leitura_do_indice_reusa_o_cache_do_par_de_digests(tmp_path: Path) -> None:
    """O cache existe por custo medido; este teste prova que ele é de fato consultado.

    O objeto é REMOVIDO do store entre as duas leituras: se a segunda ainda devolve o
    índice, ela não voltou ao armazenamento. É a mesma prova que o `_IndexCache` do servidor
    de medição faz com `mtime`, adaptada ao que endereça o objeto aqui — o digest.
    """
    client, database = _app(tmp_path)
    catalog, publicacao = _publicado(client)
    cache = _index_cache(client)
    chave = reference_catalog_index_key(object_sha256=publicacao.json()["object_sha256"])

    with database.sessions() as session:
        primeira = resolve_semantic_index(session, _store(client), catalog=catalog, cache=cache)
        del _store(client).objects[chave]
        segunda = resolve_semantic_index(session, _store(client), catalog=catalog, cache=cache)

    assert primeira is not None
    assert segunda is primeira


def test_o_cache_nao_serve_indice_amarrado_a_outro_catalogo(tmp_path: Path) -> None:
    """A segunda metade da chave do cache é o digest do CATÁLOGO, e ela trabalha.

    Sem ela, um catálogo trocado receberia de volta o `SemanticIndex` amarrado ao anterior —
    a degradação silenciosa que a amarração existe para recusar. Com ela, a leitura volta ao
    objeto e a conferência acontece de novo.
    """
    client, database = _app(tmp_path)
    catalog, _ = _publicado(client)
    outro = _catalog(source_seed="planilha-de-outra-obra")
    cache = _index_cache(client)

    with database.sessions() as session:
        registro = session.scalars(select(ReferenceCatalogEmbeddingRecord)).one()
        read_semantic_index(_store(client), record=registro, catalog=catalog, cache=cache)
        with pytest.raises(ValuationValidationError) as recusa:
            read_semantic_index(_store(client), record=registro, catalog=outro, cache=cache)

    assert recusa.value.code == "INDEX_CATALOG_MISMATCH"


def test_o_cache_descarta_a_entrada_mais_antiga_ao_passar_do_teto() -> None:
    """Duas entradas por escolha de TAMANHO: ~40 MB de matriz cada (ADR-0054).

    Copiar o número do `CatalogCache` (4) custaria ~160 MB por processo. O teste guarda a
    política, não o número em si: o que não pode acontecer em silêncio é o cache crescer sem
    limite com objetos deste tamanho.
    """
    catalog = _catalog()
    outro = _catalog(source_seed="planilha-de-outra-obra")
    terceiro = _catalog(source_seed="planilha-de-uma-terceira-obra")
    cache = SemanticIndexCache(max_entries=2)

    for alvo in (catalog, outro, terceiro):
        cache.put(
            (f"digest-{alvo.source_sha256}", alvo.source_sha256), fixture_semantic_index(alvo)
        )

    assert cache.get((f"digest-{catalog.source_sha256}", catalog.source_sha256)) is None
    assert cache.get((f"digest-{outro.source_sha256}", outro.source_sha256)) is not None
    assert cache.get((f"digest-{terceiro.source_sha256}", terceiro.source_sha256)) is not None
