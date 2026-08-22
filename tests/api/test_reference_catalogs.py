"""Acervo de catálogos de referência da plataforma (F-037 T1 e T6, ADR-0047).

O que está sob teste aqui é uma exceção deliberada ao invariante mais forte do schema:
`reference_catalogs` é a única tabela sem `tenant_id`. Por isso os dois primeiros blocos
não testam rota nenhuma — eles testam a CONDIÇÃO que sustenta a exceção:

1. **nada na tabela deriva de conteúdo de cliente** (decisão 1), com a lista de colunas
   fechada e a contraprova de que nenhuma outra tabela do schema perdeu o `tenant_id`;
2. **o objeto fica fora de `tenants/` e nenhuma rota o assina** (decisão 6) — a guarda de
   prefixo de `signed_artifact_url` recusa uma chave do acervo, e recusar é o comportamento
   correto: o cliente escolhe a tabela, ele não a baixa.

Os demais blocos cobrem a administração: subir o arquivo (o presign da T6), publicar
(imutável por digest), listar (inclusive o que saiu de circulação) e retirar (que marca
estado e não apaga), sempre com o papel `platform_operator` exigido ANTES de qualquer
lookup.

O bloco da T6 carrega o teste que fecha um defeito, e ele é de dois lados: com o croqui
`disabled`, o operador publica do começo ao fim, e `POST /v1/uploads/presign` CONTINUA
recusando no mesmo ambiente — a correção não podia ser afrouxar o portão da F-034.

Instalar um catálogo do acervo na cascata de uma rodada é a T2 e vive em
`tests/api/test_estimate_round_routes.py`; o que esta suíte prova sobre "serve tenants
diferentes" é o que se decide sem rodada: a chave não depende de tenant, e o mesmo objeto é
lido igual por qualquer sessão.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, cast

from fastapi.testclient import TestClient
from sqlalchemy import select

from croquito_api.config import ApiSettings, JourneyAvailabilitySettings, StorageFlavor
from croquito_api.database import AuditRecord, Base, Database, ReferenceCatalogRecord, UploadRecord
from croquito_api.main import create_app
from croquito_api.reference_catalogs import (
    REFERENCE_CATALOG_PREFIX,
    STATUS_AVAILABLE,
    STATUS_WITHDRAWN,
    reference_catalog_key,
)
from croquito_api.valuation_rounds import CatalogCache, read_catalog, signed_artifact_url
from croquito_valuation.models import PriceCatalog, PriceCatalogEntry, PriceOrigin
from tests.fakes import FakeObjectStore

_OPERATOR_TENANT = "tenant-plataforma"
_CLIENT_TENANT = "tenant-scalle"
_OTHER_CLIENT_TENANT = "tenant-toca"

_SCO_CODE = "CE04100010(/)"
_NON_SCO_CODE = "03.005.0010-A"

_ACERVO_PATH = "/v1/platform/reference-catalogs"
_PRESIGN_PATH = f"{_ACERVO_PATH}/presign"
_CROQUI_PRESIGN_PATH = "/v1/uploads/presign"

#: Cada coluna do acervo e de onde ela vem. É a lista que a decisão 1 do ADR-0047 obriga a
#: manter fechada: enquanto toda origem for "o operador digitou" ou "estava dentro do
#: arquivo publicado", nada ali deriva de conteúdo de cliente e a ausência de `tenant_id`
#: continua sustentada. Coluna nova entra aqui por decisão consciente, nunca por descuido.
_ORIGEM_DE_CADA_COLUNA: Final[dict[str, str]] = {
    "id": "gerado pelo servidor (UUIDv7)",
    "display_name": "digitado pelo operador da plataforma",
    "origin": "lido de dentro do catalog.json publicado",
    "reference_month": "lido de dentro do catalog.json publicado",
    "object_sha256": "digest dos bytes do arquivo publicado pelo operador",
    "source_sha256": "carimbado pelo importador dentro do catalog.json",
    "entry_count": "contado no catalog.json publicado",
    "object_key": "derivado do digest do arquivo publicado",
    "status": "estado de circulação, decidido por ato do operador",
    "published_by": "identidade do operador que publicou",
    "published_at": "relógio do servidor no ato de publicar",
    "withdrawn_at": "relógio do servidor no ato de retirar",
}


# --- montagem ---------------------------------------------------------------------------


def _app(
    tmp_path: Path,
    *,
    journeys: JourneyAvailabilitySettings | None = None,
    storage_flavor: StorageFlavor = "s3",
) -> tuple[TestClient, Database]:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'acervo.db'}"
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
        journeys=journeys or JourneyAvailabilitySettings(),
    )
    application = create_app(settings=settings, database=database)
    application.state.artifact_store = FakeObjectStore()
    return TestClient(application), database


def _store(client: TestClient) -> FakeObjectStore:
    return cast(FakeObjectStore, cast(Any, client.app).state.artifact_store)


def _headers(tenant: str, roles: str, *, key: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer test:{tenant}:pessoa-sintetica:{roles}"}
    if key is not None:
        headers["Idempotency-Key"] = key
    return headers


def _operator(key: str | None = None) -> dict[str, str]:
    return _headers(_OPERATOR_TENANT, "platform_operator", key=key)


def _catalog_bytes(
    *,
    origin: PriceOrigin = PriceOrigin.SCO,
    reference_month: str = "2026-07",
    source_label: str = "SCO-RIO FGV06 DESONERADO",
    source_sha256: str | None = None,
) -> bytes:
    """Catálogo sintético de uma entrada, no formato que o CLI de importação produz."""
    code = _SCO_CODE if origin == PriceOrigin.SCO else _NON_SCO_CODE
    catalog = PriceCatalog(
        source_label=source_label,
        reference_month=reference_month,
        source_sha256=(
            source_sha256 or hashlib.sha256(f"planilha-{origin.value}".encode()).hexdigest()
        ),
        origin=origin,
        entries=[
            PriceCatalogEntry(
                code=code,
                description="ALAMBRADO GALVANIZADO",
                unit="m",
                unit_price="50.00",
                family_code="CE",
                family_name="SERVICOS SINTETICOS",
                subgroup_code="CE0410",
                subgroup_name="ITENS SINTETICOS",
                origin=origin,
            )
        ],
    )
    return catalog.model_dump_json().encode("utf-8")


def _presign_and_put(client: TestClient, *, payload: bytes, key: str) -> str:
    """Sobe o `catalog.json` pelo presign DA PLATAFORMA e devolve o `upload_id`.

    Deliberadamente não é `/v1/uploads/presign`: aquele é do croqui e cai no portão de
    disponibilidade da F-034 (T6). O caminho que o operador usa de verdade é este.
    """
    presign = client.post(
        _PRESIGN_PATH,
        headers=_operator(f"presign-{key}"),
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
    return cast(str, presign.json()["upload_id"])


def _publish(
    client: TestClient,
    *,
    payload: bytes | None = None,
    display_name: str = "SCO-Rio FGV06 desonerado",
    key: str = "publicacao-001",
) -> Any:
    body = payload if payload is not None else _catalog_bytes()
    upload_id = _presign_and_put(client, payload=body, key=key)
    return client.post(
        _ACERVO_PATH,
        headers=_operator(key),
        json={"upload_id": upload_id, "display_name": display_name},
    )


# --- a condição que sustenta a tabela sem `tenant_id` -------------------------------------


def test_nenhuma_coluna_do_acervo_deriva_de_conteudo_de_cliente() -> None:
    """A guarda escrita da decisão 1 do ADR-0047, verificada em vez de confiada à memória.

    Duas afirmações, e as duas precisam continuar verdadeiras: o acervo não tem `tenant_id`
    e cada coluna dele vem do operador ou do arquivo público que ele publicou; e nenhuma
    OUTRA tabela do schema perdeu o `tenant_id` — a exceção continua sendo uma só.
    """
    colunas = {coluna.name for coluna in ReferenceCatalogRecord.__table__.columns}

    assert "tenant_id" not in colunas
    assert colunas == set(_ORIGEM_DE_CADA_COLUNA)

    sem_tenant = {
        tabela.name for tabela in Base.metadata.sorted_tables if "tenant_id" not in tabela.columns
    }
    assert sem_tenant == {"reference_catalogs"}


def test_a_chave_do_acervo_fica_fora_do_prefixo_do_tenant_e_nao_e_assinavel(
    tmp_path: Path,
) -> None:
    """`signed_artifact_url` RECUSA uma chave do acervo, e recusar é o comportamento certo.

    A guarda não é afrouxada nem contornada (ADR-0047 decisão 6): o cliente escolhe a
    tabela, o servidor é quem a lê. A recusa vale para qualquer tenant, inclusive o do
    operador que publicou.
    """
    client, _ = _app(tmp_path)
    publicacao = _publish(client)
    assert publicacao.status_code == 201, publicacao.text
    chave = reference_catalog_key(object_sha256=publicacao.json()["object_sha256"])
    store = _store(client)

    assert chave.startswith(REFERENCE_CATALOG_PREFIX)
    assert not chave.startswith("tenants/")
    for tenant in (_CLIENT_TENANT, _OTHER_CLIENT_TENANT, _OPERATOR_TENANT):
        assert signed_artifact_url(store, object_key=chave, tenant_id=tenant) is None


def test_nenhuma_resposta_do_acervo_carrega_chave_de_objeto_nem_url_assinada(
    tmp_path: Path,
) -> None:
    client, _ = _app(tmp_path)
    publicacao = _publish(client)
    listagem = client.get(_ACERVO_PATH, headers=_operator())
    retirada = client.post(
        f"{_ACERVO_PATH}/{publicacao.json()['reference_catalog_id']}/withdraw",
        headers=_operator("retirada-001"),
    )

    for resposta in (publicacao, listagem, retirada):
        assert resposta.status_code in {200, 201}, resposta.text
        assert REFERENCE_CATALOG_PREFIX not in resposta.text
        assert "http" not in resposta.text
        assert "object_key" not in resposta.text


# --- presign da plataforma (T6) -----------------------------------------------------------


def test_com_o_croqui_desligado_o_operador_publica_do_comeco_ao_fim(tmp_path: Path) -> None:
    """O defeito que a T6 fecha, provado no ambiente onde ele aparecia.

    O portão de disponibilidade da F-034 é dependência do router e `/v1/uploads` é do croqui:
    enquanto publicar dependia daquele presign, um ambiente com o croqui `disabled` — que é
    justamente o módulo que a F-034 nasceu para poder desligar — deixava o acervo sem como
    ser alimentado, sem que nada indicasse por quê.

    A contraprova está no mesmo teste, e é o que impede a correção de virar afrouxamento:
    `/v1/uploads/presign` CONTINUA recusando com `JOURNEY_UNAVAILABLE`, para o mesmo
    operador, no mesmo ambiente e com o mesmo corpo.
    """
    client, database = _app(tmp_path, journeys=JourneyAvailabilitySettings(croqui="disabled"))
    conteudo = _catalog_bytes()
    corpo_do_presign = {
        "filename": "catalogo.json",
        "size_bytes": len(conteudo),
        "sha256": hashlib.sha256(conteudo).hexdigest(),
    }

    presign = client.post(
        _PRESIGN_PATH, headers=_operator("presign-com-croqui-desligado"), json=corpo_do_presign
    )
    assert presign.status_code == 200, presign.text
    _store(client).put_direct(
        object_key=presign.json()["object_key"], body=conteudo, content_type="application/json"
    )
    publicacao = client.post(
        _ACERVO_PATH,
        headers=_operator("publica-com-croqui-desligado"),
        json={"upload_id": presign.json()["upload_id"], "display_name": "SCO-Rio 07/2026"},
    )
    pelo_croqui = client.post(
        _CROQUI_PRESIGN_PATH,
        headers=_operator("presign-pelo-croqui"),
        json={**corpo_do_presign, "content_type": "application/json"},
    )

    assert publicacao.status_code == 201, publicacao.text
    assert publicacao.json()["reference_month"] == "2026-07"
    assert pelo_croqui.status_code == 403
    assert pelo_croqui.json()["code"] == "JOURNEY_UNAVAILABLE"
    with database.sessions() as session:
        assert session.scalars(select(ReferenceCatalogRecord)).one().status == STATUS_AVAILABLE


def test_o_presign_do_acervo_exige_platform_operator_antes_de_gravar(tmp_path: Path) -> None:
    """Papel antes de qualquer coisa: `403` e nenhum `UploadRecord`, nem chave assinada."""
    client, database = _app(tmp_path)
    conteudo = _catalog_bytes()

    resposta = client.post(
        _PRESIGN_PATH,
        headers=_headers(_CLIENT_TENANT, "orcamentista", key="presign-sem-papel"),
        json={
            "filename": "catalogo.json",
            "size_bytes": len(conteudo),
            "sha256": hashlib.sha256(conteudo).hexdigest(),
        },
    )

    assert resposta.status_code == 403
    assert resposta.json()["code"] == "FORBIDDEN"
    assert "url" not in resposta.json()
    with database.sessions() as session:
        assert session.query(UploadRecord).count() == 0


def test_o_presign_do_acervo_fixa_o_tipo_em_json(tmp_path: Path) -> None:
    """O acervo publica catálogo normalizado e nada mais, então o tipo não vem do corpo.

    Duas recusas, e as duas antes de qualquer gravação: declarar `content_type` é campo
    desconhecido no contrato, e nome de arquivo que não case com JSON é `INVALID_UPLOAD`.
    """
    client, database = _app(tmp_path)
    conteudo = _catalog_bytes()
    base = {"size_bytes": len(conteudo), "sha256": hashlib.sha256(conteudo).hexdigest()}

    declarando_pdf = client.post(
        _PRESIGN_PATH,
        headers=_operator("tipo-pdf"),
        json={**base, "filename": "prancha.pdf", "content_type": "application/pdf"},
    )
    declarando_json = client.post(
        _PRESIGN_PATH,
        headers=_operator("tipo-json"),
        json={**base, "filename": "catalogo.json", "content_type": "application/json"},
    )
    nome_de_pdf = client.post(
        _PRESIGN_PATH, headers=_operator("nome-pdf"), json={**base, "filename": "prancha.pdf"}
    )

    assert declarando_pdf.status_code == 422
    assert declarando_json.status_code == 422
    assert nome_de_pdf.status_code == 422
    assert nome_de_pdf.json()["code"] == "INVALID_UPLOAD"
    with database.sessions() as session:
        assert session.query(UploadRecord).count() == 0


def test_o_presign_do_acervo_grava_upload_do_tenant_do_operador(tmp_path: Path) -> None:
    """O objeto ainda é do operador: só a publicação o move para o prefixo do acervo.

    Assinar direto para dentro de `platform/reference-catalogs/` poria no acervo um arquivo
    que ninguém leu — a conferência do digest e da origem acontece na publicação.
    """
    client, database = _app(tmp_path)
    conteudo = _catalog_bytes()

    resposta = client.post(
        _PRESIGN_PATH,
        headers=_operator("presign-do-operador"),
        json={
            "filename": "catalogo final.json",
            "size_bytes": len(conteudo),
            "sha256": hashlib.sha256(conteudo).hexdigest().upper(),
        },
    )

    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    upload_id = corpo["upload_id"]
    assert (
        corpo["object_key"] == f"tenants/{_OPERATOR_TENANT}/uploads/{upload_id}/catalogo-final.json"
    )
    assert not corpo["object_key"].startswith(REFERENCE_CATALOG_PREFIX)
    with database.sessions() as session:
        registro = session.scalars(select(UploadRecord)).one()
        assert registro.tenant_id == _OPERATOR_TENANT
        assert registro.content_type == "application/json"
        assert registro.sha256 == hashlib.sha256(conteudo).hexdigest()
    with database.sessions() as session:
        evento = session.scalars(
            select(AuditRecord).where(AuditRecord.action == "UPLOAD_PRESIGNED")
        ).one()
        assert evento.tenant_id == _OPERATOR_TENANT
        assert evento.resource_id == upload_id


def test_o_presign_do_acervo_exige_chave_de_idempotencia_e_repete_a_resposta(
    tmp_path: Path,
) -> None:
    client, database = _app(tmp_path)
    conteudo = _catalog_bytes()
    corpo = {
        "filename": "catalogo.json",
        "size_bytes": len(conteudo),
        "sha256": hashlib.sha256(conteudo).hexdigest(),
    }

    sem_chave = client.post(_PRESIGN_PATH, headers=_operator(), json=corpo)
    primeira = client.post(_PRESIGN_PATH, headers=_operator("mesma-chave"), json=corpo)
    replay = client.post(_PRESIGN_PATH, headers=_operator("mesma-chave"), json=corpo)

    assert sem_chave.status_code == 400
    assert primeira.status_code == 200, primeira.text
    assert replay.json() == primeira.json()
    with database.sessions() as session:
        assert session.query(UploadRecord).count() == 1


def test_o_header_de_checksum_do_acervo_existe_so_no_perfil_que_o_assina(
    tmp_path: Path,
) -> None:
    """O header entra na assinatura só no S3; mandá-lo ao GCS faria o PUT falhar."""
    conteudo = _catalog_bytes()
    corpo = {
        "filename": "catalogo.json",
        "size_bytes": len(conteudo),
        "sha256": hashlib.sha256(conteudo).hexdigest(),
    }
    respostas: dict[StorageFlavor, dict[str, str]] = {}
    for flavor in ("s3", "gcs"):
        raiz = tmp_path / flavor
        raiz.mkdir()
        client, _ = _app(raiz, storage_flavor=flavor)
        resposta = client.post(_PRESIGN_PATH, headers=_operator(f"checksum-{flavor}"), json=corpo)
        assert resposta.status_code == 200, resposta.text
        respostas[flavor] = resposta.json()["headers"]

    assert respostas["s3"]["Content-Type"] == "application/json"
    assert respostas["s3"]["x-amz-checksum-sha256"]
    assert respostas["gcs"] == {"Content-Type": "application/json"}


# --- publicar -----------------------------------------------------------------------------


def test_publicar_uma_vez_serve_qualquer_tenant(tmp_path: Path) -> None:
    """Uma publicação existe UMA vez na plataforma e não pertence a tenant nenhum.

    A instalação numa rodada é a T2; o que já é decidível aqui é o que a sustenta: a chave
    não carrega tenant, a linha não tem coluna de tenant, e qualquer leitor do store recebe
    os mesmos bytes — que continuam validando como o catálogo publicado.
    """
    client, database = _app(tmp_path)
    conteudo = _catalog_bytes()

    publicacao = _publish(client, payload=conteudo)

    assert publicacao.status_code == 201, publicacao.text
    corpo = publicacao.json()
    assert corpo["origin"] == "sco"
    assert corpo["reference_month"] == "2026-07"
    assert corpo["entry_count"] == 1
    assert corpo["available"] is True
    chave = reference_catalog_key(object_sha256=corpo["object_sha256"])
    assert _store(client).read_object(object_key=chave, max_bytes=len(conteudo) + 1) == conteudo
    # Duas rodadas de tenants DIFERENTES leem o mesmo objeto pelo mesmo caminho que a
    # instalação usará (T2): `read_catalog` confere o digest e valida o domínio, e nada nele
    # depende de tenant — a chave é a mesma para os dois porque o catálogo não tem dono.
    lidos = [
        read_catalog(
            _store(client),
            object_key=chave,
            digest=corpo["object_sha256"],
            cache=CatalogCache(),
            details={"tenant_id": tenant},
        )
        for tenant in (_CLIENT_TENANT, _OTHER_CLIENT_TENANT)
    ]
    assert [catalogo.reference_month for catalogo in lidos] == ["2026-07", "2026-07"]
    assert lidos[0] == lidos[1]
    with database.sessions() as session:
        registro = session.scalars(select(ReferenceCatalogRecord)).one()
        assert registro.object_key == chave
        assert registro.status == STATUS_AVAILABLE
        assert registro.published_by == "pessoa-sintetica"


def test_publicar_le_origem_data_base_e_contagem_de_dentro_do_arquivo(tmp_path: Path) -> None:
    """O rótulo não pode discordar do conteúdo: só o nome de exibição é digitado."""
    client, database = _app(tmp_path)
    conteudo = _catalog_bytes(
        origin=PriceOrigin.SINAPI, reference_month="2026-05", source_label="SINAPI RJ"
    )

    publicacao = _publish(
        client, payload=conteudo, display_name="Nome que o operador escolheu", key="sinapi"
    )

    assert publicacao.status_code == 201, publicacao.text
    with database.sessions() as session:
        registro = session.scalars(select(ReferenceCatalogRecord)).one()
        assert registro.display_name == "Nome que o operador escolheu"
        assert registro.origin == "sinapi"
        assert registro.reference_month == "2026-05"
        assert registro.source_sha256 == PriceCatalog.model_validate_json(conteudo).source_sha256
        assert registro.entry_count == 1


def test_corpo_que_tenta_declarar_origem_ou_data_base_e_recusado(tmp_path: Path) -> None:
    """Campo desconhecido é recusa de CONTRATO, antes de qualquer leitura de arquivo."""
    client, database = _app(tmp_path)
    upload_id = _presign_and_put(client, payload=_catalog_bytes(), key="rotulo")

    resposta = client.post(
        _ACERVO_PATH,
        headers=_operator("rotulo-mentiroso"),
        json={
            "upload_id": upload_id,
            "display_name": "SCO-Rio",
            "origin": "sinapi",
            "reference_month": "2020-01",
            "entry_count": 99999,
        },
    )

    assert resposta.status_code == 422
    with database.sessions() as session:
        assert session.query(ReferenceCatalogRecord).count() == 0


def test_republicar_o_mesmo_conteudo_recusa_e_data_base_nova_e_entrada_nova(
    tmp_path: Path,
) -> None:
    """Publicação é imutável por digest (ADR-0047 decisão 3, ADR-0027 decisão 4)."""
    client, database = _app(tmp_path)
    conteudo = _catalog_bytes(reference_month="2026-07")

    primeira = _publish(client, payload=conteudo, key="julho")
    repetida = _publish(client, payload=conteudo, key="julho-de-novo")
    nova_data_base = _publish(
        client, payload=_catalog_bytes(reference_month="2026-08"), key="agosto"
    )

    assert primeira.status_code == 201
    assert repetida.status_code == 409
    assert repetida.json()["detail"]["code"] == "REFERENCE_CATALOG_ALREADY_PUBLISHED"
    assert (
        repetida.json()["detail"]["details"]["reference_catalog_id"]
        == primeira.json()["reference_catalog_id"]
    )
    assert nova_data_base.status_code == 201
    with database.sessions() as session:
        publicadas = {
            registro.reference_month for registro in session.scalars(select(ReferenceCatalogRecord))
        }
        assert publicadas == {"2026-07", "2026-08"}


def test_origem_que_a_plataforma_nao_distribui_e_recusada(tmp_path: Path) -> None:
    """EMOP é tabela paga e composição é do cliente (ADR-0047 decisão 8): nem uma nem outra
    entram no acervo, e nada é gravado — nem linha, nem objeto."""
    client, database = _app(tmp_path)

    resposta = _publish(client, payload=_catalog_bytes(origin=PriceOrigin.EMOP), key="emop")

    assert resposta.status_code == 422
    assert resposta.json()["detail"]["code"] == "REFERENCE_CATALOG_ORIGIN_NOT_PUBLISHABLE"
    assert resposta.json()["detail"]["details"]["origin"] == "emop"
    assert not any(chave.startswith(REFERENCE_CATALOG_PREFIX) for chave in _store(client).objects)
    with database.sessions() as session:
        assert session.query(ReferenceCatalogRecord).count() == 0


def test_publicar_exige_chave_de_idempotencia_e_repete_a_mesma_resposta(tmp_path: Path) -> None:
    client, database = _app(tmp_path)
    conteudo = _catalog_bytes()
    upload_id = _presign_and_put(client, payload=conteudo, key="idempotencia")
    corpo = {"upload_id": upload_id, "display_name": "SCO-Rio FGV06 desonerado"}

    sem_chave = client.post(_ACERVO_PATH, headers=_operator(), json=corpo)
    primeira = client.post(_ACERVO_PATH, headers=_operator("mesma-chave"), json=corpo)
    replay = client.post(_ACERVO_PATH, headers=_operator("mesma-chave"), json=corpo)

    assert sem_chave.status_code == 400
    assert primeira.status_code == 201, primeira.text
    assert replay.json() == primeira.json()
    with database.sessions() as session:
        assert session.query(ReferenceCatalogRecord).count() == 1


def test_publicar_audita_no_tenant_do_operador_com_o_catalogo_nos_detalhes(
    tmp_path: Path,
) -> None:
    """Decisão 11 do ADR-0047: o ato não tem tenant alvo, e o fato verdadeiro é quem o fez."""
    client, database = _app(tmp_path)

    publicacao = _publish(client)

    assert publicacao.status_code == 201
    with database.sessions() as session:
        evento = session.scalars(
            select(AuditRecord).where(AuditRecord.action == "REFERENCE_CATALOG_PUBLISHED")
        ).one()
        assert evento.tenant_id == _OPERATOR_TENANT
        assert evento.resource_type == "reference_catalog"
        assert evento.resource_id == publicacao.json()["reference_catalog_id"]
        assert evento.metadata_json["reference_catalog_id"] == evento.resource_id
        assert evento.metadata_json["origin"] == "sco"
        assert evento.metadata_json["reference_month"] == "2026-07"


# --- listar e retirar de circulação --------------------------------------------------------


def test_listagem_traz_o_acervo_inteiro_inclusive_o_que_saiu_de_circulacao(
    tmp_path: Path,
) -> None:
    client, _ = _app(tmp_path)
    julho = _publish(client, payload=_catalog_bytes(reference_month="2026-07"), key="julho")
    agosto = _publish(client, payload=_catalog_bytes(reference_month="2026-08"), key="agosto")
    retirada = client.post(
        f"{_ACERVO_PATH}/{julho.json()['reference_catalog_id']}/withdraw",
        headers=_operator("retira-julho"),
    )
    assert retirada.status_code == 200, retirada.text

    listagem = client.get(_ACERVO_PATH, headers=_operator())

    assert listagem.status_code == 200
    catalogos = listagem.json()["catalogs"]
    assert [catalogo["reference_month"] for catalogo in catalogos] == ["2026-07", "2026-08"]
    assert [catalogo["available"] for catalogo in catalogos] == [False, True]
    assert catalogos[0]["reference_catalog_id"] == julho.json()["reference_catalog_id"]
    assert catalogos[0]["withdrawn_at"] is not None
    assert catalogos[0]["published_by"] == "pessoa-sintetica"
    assert catalogos[1]["reference_catalog_id"] == agosto.json()["reference_catalog_id"]


def test_retirar_de_circulacao_nao_apaga_linha_nem_objeto(tmp_path: Path) -> None:
    """Rodada antiga referencia o objeto e continua funcionando: retirar é marcar estado."""
    client, database = _app(tmp_path)
    conteudo = _catalog_bytes()
    publicacao = _publish(client, payload=conteudo)
    catalogo_id = publicacao.json()["reference_catalog_id"]
    chave = reference_catalog_key(object_sha256=publicacao.json()["object_sha256"])

    retirada = client.post(
        f"{_ACERVO_PATH}/{catalogo_id}/withdraw", headers=_operator("retirada-001")
    )

    assert retirada.status_code == 200, retirada.text
    assert retirada.json()["available"] is False
    assert retirada.json()["withdrawn_at"] is not None
    assert _store(client).read_object(object_key=chave, max_bytes=len(conteudo) + 1) == conteudo
    with database.sessions() as session:
        registro = session.scalars(select(ReferenceCatalogRecord)).one()
        assert registro.id == catalogo_id
        assert registro.status == STATUS_WITHDRAWN
        assert registro.object_key == chave


def test_retirar_o_que_ja_saiu_de_circulacao_preserva_a_data_do_ato_original(
    tmp_path: Path,
) -> None:
    client, database = _app(tmp_path)
    catalogo_id = _publish(client).json()["reference_catalog_id"]
    caminho = f"{_ACERVO_PATH}/{catalogo_id}/withdraw"

    primeira = client.post(caminho, headers=_operator("retira-1"))
    with database.sessions() as session:
        carimbo = session.scalars(select(ReferenceCatalogRecord)).one().withdrawn_at
    repetida = client.post(caminho, headers=_operator("retira-2"))

    assert primeira.status_code == 200
    assert repetida.status_code == 200
    with database.sessions() as session:
        # A data verdadeira é a da retirada, não a da última vez que alguém repetiu o pedido.
        assert session.scalars(select(ReferenceCatalogRecord)).one().withdrawn_at == carimbo
    with database.sessions() as session:
        eventos = session.scalars(
            select(AuditRecord).where(AuditRecord.action == "REFERENCE_CATALOG_WITHDRAWN")
        ).all()
        assert len(eventos) == 1


def test_retirar_catalogo_inexistente_e_404(tmp_path: Path) -> None:
    client, _ = _app(tmp_path)

    resposta = client.post(
        f"{_ACERVO_PATH}/0192f000-0000-7000-8000-000000000000/withdraw",
        headers=_operator("retira-fantasma"),
    )

    assert resposta.status_code == 404
    assert resposta.json()["code"] == "NOT_FOUND"


# --- papel --------------------------------------------------------------------------------


def test_o_acervo_exige_platform_operator_antes_de_qualquer_lookup(tmp_path: Path) -> None:
    """Quem não tem o papel recebe `403` e não descobre o que existe — nem se existe.

    A recusa é a mesma para um id que existe e para um que não existe, e nada é gravado: é
    o que impede a diferença entre `403` e `404` de virar leitura do acervo por quem não
    pode lê-lo.
    """
    client, database = _app(tmp_path)
    publicado = _publish(client).json()["reference_catalog_id"]
    upload_id = _presign_and_put(client, payload=_catalog_bytes(reference_month="2026-09"), key="x")
    sem_papel = _headers(_CLIENT_TENANT, "orcamentista", key="tentativa-sem-papel")

    listagem = client.get(_ACERVO_PATH, headers=_headers(_CLIENT_TENANT, "orcamentista"))
    publicacao = client.post(
        _ACERVO_PATH,
        headers=sem_papel,
        json={"upload_id": upload_id, "display_name": "Tabela indevida"},
    )
    existente = client.post(f"{_ACERVO_PATH}/{publicado}/withdraw", headers=sem_papel)
    inexistente = client.post(
        f"{_ACERVO_PATH}/0192f000-0000-7000-8000-000000000000/withdraw", headers=sem_papel
    )

    for resposta in (listagem, publicacao, existente, inexistente):
        assert resposta.status_code == 403
        assert resposta.json()["code"] == "FORBIDDEN"
    with database.sessions() as session:
        registro = session.scalars(select(ReferenceCatalogRecord)).one()
        assert registro.status == STATUS_AVAILABLE
        assert registro.withdrawn_at is None


def test_a_chave_do_acervo_recusa_digest_que_nao_e_sha256() -> None:
    """Montar caminho a partir de texto que ninguém olhou é como um `..` entra numa chave."""
    for invalido in ("../segredo", "NAO-E-DIGEST", "a" * 63, datetime.now(UTC).isoformat()):
        try:
            reference_catalog_key(object_sha256=invalido)
        except ValueError:
            continue
        raise AssertionError(f"digest inválido aceito: {invalido}")
