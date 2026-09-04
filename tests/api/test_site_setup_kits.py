"""Acervo de parcelas de canteiro na `/v1` (F-042 T2, ADR-0060).

Quatro invariantes atravessam a suíte, e são elas que a T2 existe para garantir:

- **fronteira de tenant**: o acervo tem duas origens (plataforma sem `tenant_id`, tenant com
  `tenant_id`), e o acervo de um tenant **nunca** é visível a outro. Provado com dois tenants,
  na listagem e no lookup;
- **pré-visualização não escreve**: nenhuma revisão nova, nenhuma versão avançada. É o
  controle que a feature exige contra "aplicar sem olhar", e um controle que gravasse deixaria
  de ser conferência;
- **merge por `kit_origin` = `(kit_id, kit_version)`**: reaplicar substitui só as parcelas
  daquele acervo; contribuição autorada à mão e de OUTRO acervo sobrevivem intactas. É o
  coração da task, e os três casos são testados. A chave era só a versão até 2026-09-04, e a
  Emenda 1 do ADR-0060 a trocou pelo PAR: dois acervos DIFERENTES que declarem a mesma versão
  deixaram de colidir, e proveniência anterior à emenda (`kit_id` nulo) nunca casa com a de um
  acervo;
- **falha fechada por extenso NO APPLY**: parâmetro citado e não declarado nomeia **todos**
  os que faltam, e código fora do catálogo da cascata nomeia o código — as duas em
  `problem+json`, com o código estável do domínio em `details.code`, e nenhuma linha
  materializada.

A quinta entrou com a T4, e é uma **assimetria deliberada**: a pré-visualização deixou de
recusar por parâmetro faltante e por código ausente, e passou a MARCAR (`missing_parameters`,
`code_absent`, `blocked_parcel_ids`). Recusar ali era beco sem saída — a saída oferecida pela
recusa era remover as parcelas na pré-visualização que a própria recusa impedia de existir.
Os testes das duas metades ficam lado a lado, no mesmo estado, para que afrouxar o apply
apareça como teste vermelho.

Nenhuma rota desta suíte chama provider: o acervo é determinístico e nada aqui paga.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import select

from croquito_api.config import ApiSettings
from croquito_api.database import (
    Database,
    EstimateRoundRecord,
    EstimateRoundRevisionRecord,
    SiteSetupKitRecord,
)
from croquito_api.main import create_app
from croquito_core.ids import new_uuid7
from croquito_valuation.calc_matrix import CalcContribution, CalcMatrix, ServiceContributions
from croquito_valuation.models import (
    CalcOperand,
    CalcRecipe,
    ContributionBasis,
    PriceCatalog,
    PriceCatalogEntry,
    PriceOrigin,
    SiteSetupOrigin,
)
from tests.fakes import FakeObjectStore

_TENANT = "tenant-a"
_OTHER_TENANT = "tenant-b"
_PLATFORM_TENANT = "tenant-plataforma"

_SCO_CODE = "CE04100010(/)"
"""O único código do catálogo sintético — é ele que a falha fechada do acervo confere."""

_ABSENT_CODE = "CE09999999(/)"
"""Código com formato válido de catálogo e ausente da cascata: o acervo desatualizado."""

_KIT_VERSION = "1.0.0"
_OTHER_KIT_VERSION = "9.9.9"
"""Versão de OUTRO acervo, cujas parcelas o merge tem de preservar intactas."""
_OTHER_KIT_ID = UUID("01930000-0000-7000-8000-0000000000ff")
"""Identidade desse OUTRO acervo. Nunca é publicada por rota nenhuma: ela existe para a
matriz de partida dos testes de merge, que é escrita direto no banco."""


# --- montagem ---------------------------------------------------------------------------


def _client(tmp_path: Path) -> TestClient:
    database = Database(f"sqlite+pysqlite:///{tmp_path / 'site-setup-api.db'}")
    database.create_schema()
    settings = ApiSettings(
        database_url=f"sqlite+pysqlite:///{tmp_path / 'site-setup-api.db'}",
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
    tenant: str = _TENANT, roles: str = "orcamentista", *, key: str = "acervo-001"
) -> dict[str, str]:
    return {
        "Authorization": f"Bearer test:{tenant}:pessoa-sintetica:{roles}",
        "Idempotency-Key": key,
    }


def _operator(key: str = "acervo-plataforma") -> dict[str, str]:
    return _headers(_PLATFORM_TENANT, "platform_operator", key=key)


def _store(client: TestClient) -> FakeObjectStore:
    return cast(FakeObjectStore, cast(Any, client.app).state.artifact_store)


def _database(client: TestClient) -> Database:
    return cast(Database, cast(Any, client.app).state.database)


def _revisions(client: TestClient, round_id: str) -> list[EstimateRoundRevisionRecord]:
    with _database(client).sessions() as session:
        return list(
            session.scalars(
                select(EstimateRoundRevisionRecord)
                .where(EstimateRoundRevisionRecord.round_id == round_id)
                .order_by(EstimateRoundRevisionRecord.version)
            )
        )


def _head_matrix(client: TestClient, round_id: str) -> dict[str, Any] | None:
    revisions = _revisions(client, round_id)
    if not revisions:
        return None
    return revisions[-1].calc_matrix_json


def _catalog_bytes() -> bytes:
    """Catálogo sintético de UMA entrada; é ele que decide qual código o acervo pode citar."""
    catalog = PriceCatalog(
        source_label="CATALOGO SINTETICO",
        reference_month="2026-01",
        source_sha256=hashlib.sha256(b"origem-sco").hexdigest(),
        origin=PriceOrigin.SCO,
        entries=[
            PriceCatalogEntry(
                code=_SCO_CODE,
                description="ALAMBRADO GALVANIZADO",
                unit="m",
                unit_price=Decimal("50.00"),
                family_code="CE",
                family_name="SERVICOS SINTETICOS",
                subgroup_code="CE0410",
                subgroup_name="ITENS SINTETICOS",
                origin=PriceOrigin.SCO,
            )
        ],
    )
    return catalog.model_dump_json().encode("utf-8")


def _create_round(client: TestClient, *, tenant: str = _TENANT, key: str = "rodada") -> str:
    response = client.post(
        "/v1/estimate-rounds",
        headers=_headers(tenant, key=key),
        json={
            "worksite_key": "praca-sintetica-norte",
            "worksite_name": "PRACA SINTETICA NORTE",
            "reference_label": "ORCAMENTO-BASE 2026",
            "address": "RUA SINTETICA, S/N",
        },
    )
    assert response.status_code == 201, response.text
    return cast(str, response.json()["round_id"])


def _round_with_cascade(client: TestClient, *, tenant: str = _TENANT, suffix: str = "a") -> str:
    """Rodada com o catálogo sintético instalado — o mínimo para o acervo poder ser aplicado.

    A cascata é o que define `available_codes`: sem ela, o acervo não teria contra o que
    conferir o código de cada parcela, e o risco do acervo desatualizado ficaria sem portão.
    """
    round_id = _create_round(client, tenant=tenant, key=f"rodada-{suffix}")
    payload = _catalog_bytes()
    presign = client.post(
        "/v1/uploads/presign",
        headers=_headers(tenant, key=f"upload-{suffix}"),
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
        headers=_headers(tenant, key=f"catalogo-{suffix}"),
        json={"upload_id": presign.json()["upload_id"], "base_version": 1},
    )
    assert installed.status_code == 201, installed.text
    return round_id


def _round_version(client: TestClient, round_id: str) -> int:
    with _database(client).sessions() as session:
        record = session.get(EstimateRoundRecord, round_id)
        assert record is not None
        return record.version


# --- documentos do acervo -----------------------------------------------------------------


def _operand(
    name: str, *, value: str | None = None, parameter: str | None = None, unit: str | None = None
) -> dict[str, Any]:
    operand: dict[str, Any] = {"name": name}
    if value is not None:
        operand["value"] = value
    if parameter is not None:
        operand["parameter"] = parameter
    if unit is not None:
        operand["unit"] = unit
    return operand


_WC_PARCEL_ID = "ss_00000000000000a1"
_PLACA_PARCEL_ID = "ss_00000000000000a2"
_AREA_PARCEL_ID = "ss_00000000000000a3"
_OUTRA_LINHAGEM_PARCEL_ID = "ss_00000000000000b1"


def _kit_document(
    *,
    version: str = _KIT_VERSION,
    source_label: str = "CANTEIRO SINTETICO",
    parcels: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Acervo sintético: duas parcelas do mesmo código, uma constante e uma paramétrica.

    Espelha a memória real do documento que originou a feature — `1 x 2 meses` para o
    banheiro químico e `2,00 x 1,40` para a placa de obra.
    """
    return {
        "version": version,
        "source_label": source_label,
        "parcels": parcels
        if parcels is not None
        else [
            {
                "id": _WC_PARCEL_ID,
                "code": _SCO_CODE,
                "label": "WC QUIMICO",
                "recipe": CalcRecipe.QTY_TIMES_MONTHS.value,
                "operands": [
                    _operand("QTD", value="1"),
                    _operand("MESES", parameter="prazo_meses", unit="meses"),
                ],
            },
            {
                "id": _PLACA_PARCEL_ID,
                "code": _SCO_CODE,
                "label": "PLACA DE OBRA",
                "recipe": CalcRecipe.DECLARED_PRODUCT.value,
                "operands": [
                    _operand("COMP", value="2.00", unit="m"),
                    _operand("ALT", value="1.40", unit="m"),
                ],
            },
        ],
    }


def _kit_document_de_outra_linhagem() -> dict[str, Any]:
    """Acervo DIFERENTE que declara a MESMA versão — o caso da Emenda 1 do ADR-0060.

    Com as duas origens do ADR (plataforma e tenant), duas linhagens independentes chamarem
    sua primeira versão de `1.0.0` não é acidente: é o esperado. Só constantes, para que a
    aplicação dele não dependa de parâmetro nenhum da rodada.
    """
    return _kit_document(
        source_label="CANTEIRO DE OUTRA LINHAGEM",
        parcels=[
            {
                "id": _OUTRA_LINHAGEM_PARCEL_ID,
                "code": _SCO_CODE,
                "label": "VIGIA NOTURNO",
                "recipe": CalcRecipe.DAYS_TIMES_HOURS.value,
                "operands": [_operand("DIAS", value="8"), _operand("H", value="24")],
            }
        ],
    )


def _kit_with_two_parameters() -> dict[str, Any]:
    """Acervo que cita DOIS parâmetros: é o que torna conferível "nomeando todos"."""
    document = _kit_document()
    parcels = cast("list[dict[str, Any]]", document["parcels"])
    parcels.append(
        {
            "id": _AREA_PARCEL_ID,
            "code": _SCO_CODE,
            "label": "LIMPEZA PERMANENTE",
            "recipe": CalcRecipe.DECLARED_PRODUCT.value,
            "operands": [_operand("AREA", parameter="area_intervencao", unit="m2")],
        }
    )
    return document


def _kit_citing_absent_code() -> dict[str, Any]:
    return _kit_document(
        parcels=[
            {
                "id": _WC_PARCEL_ID,
                "code": _ABSENT_CODE,
                "label": "WC QUIMICO",
                "recipe": CalcRecipe.DECLARED_PRODUCT.value,
                "operands": [_operand("QTD", value="1")],
            }
        ]
    )


def _publish_platform_kit(
    client: TestClient,
    *,
    name: str = "CANTEIRO PADRAO",
    document: dict[str, Any] | None = None,
    key: str = "publicacao",
) -> Any:
    return client.post(
        "/v1/platform/site-setup-kits",
        headers=_operator(key=key),
        json={"name": name, "document": document if document is not None else _kit_document()},
    )


def _insert_tenant_kit(
    client: TestClient,
    *,
    tenant: str,
    name: str,
    version: str = _KIT_VERSION,
) -> str:
    """Acervo do tenant gravado direto, para exercitar a fronteira sem passar pela autoria.

    A rota de autoria precisa de matriz na rodada, e a fronteira de tenant não depende dela:
    escrever a linha aqui isola o que este teste afirma.
    """
    document = _kit_document(version=version, source_label=name)
    kit_id = str(new_uuid7())
    with _database(client).sessions() as session:
        session.add(
            SiteSetupKitRecord(
                id=kit_id,
                tenant_id=tenant,
                name=name,
                kit_version=version,
                source_label=name,
                document_json=document,
                document_sha256=hashlib.sha256(name.encode()).hexdigest(),
                withdrawn_at=None,
                created_by="orcamentista-sintetica",
                created_at=datetime.now(UTC),
            )
        )
        session.commit()
    return kit_id


def _write_matrix(client: TestClient, round_id: str, matrix: CalcMatrix, *, tenant: str) -> int:
    """Grava uma revisão com a matriz posta, como o build do orçamento faria.

    Escrita direta e não pela rota de `estimate`: montar o orçamento exigiria takeoff revisado
    e decisão de código, e nada disso é o que estes testes afirmam. O que importa aqui é o
    ESTADO da matriz na cabeça da rodada.
    """
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
                created_by="orcamentista-sintetica",
                calc_matrix_json=matrix.model_dump(mode="json"),
            )
        )
        record.version += 1
        session.commit()
        return record.version


def _manual_contribution(label: str = "PARCELA A MAO") -> CalcContribution:
    """Parcela autorada à mão: `kit_origin` nulo. O merge tem de preservá-la intacta."""
    return CalcContribution(
        label=label,
        basis=ContributionBasis.STANDALONE,
        recipe=CalcRecipe.DECLARED_PRODUCT,
        operands=[CalcOperand(name="QTD", value=Decimal("7.00"))],
    )


def _other_kit_contribution() -> CalcContribution:
    """Parcela de OUTRO acervo: mesma base, identidade e versão diferentes. Também sobrevive."""
    return CalcContribution(
        label="PARCELA DE OUTRO ACERVO",
        basis=ContributionBasis.STANDALONE,
        recipe=CalcRecipe.DECLARED_PRODUCT,
        operands=[CalcOperand(name="QTD", value=Decimal("3.00"))],
        kit_origin=SiteSetupOrigin(
            kit_id=_OTHER_KIT_ID, kit_version=_OTHER_KIT_VERSION, parcel_id=_WC_PARCEL_ID
        ),
    )


def _pre_amendment_contribution(*, kit_version: str = _KIT_VERSION) -> CalcContribution:
    """Parcela gravada ANTES da Emenda 1: proveniência sem identidade (`kit_id` nulo).

    A versão é, de propósito, a MESMA do acervo que os testes aplicam: sob a chave antiga ela
    seria substituída, e é exatamente isso que a emenda deixou de fazer — "não observado" não
    é "o mesmo acervo".
    """
    return CalcContribution(
        label="PARCELA ANTERIOR A EMENDA",
        basis=ContributionBasis.STANDALONE,
        recipe=CalcRecipe.DECLARED_PRODUCT,
        operands=[CalcOperand(name="QTD", value=Decimal("5.00"))],
        kit_origin=SiteSetupOrigin(kit_version=kit_version, parcel_id=_WC_PARCEL_ID),
    )


def _preview(
    client: TestClient,
    round_id: str,
    *,
    kit_id: str,
    parameters: dict[str, str] | None = None,
    excluded: list[str] | None = None,
    tenant: str = _TENANT,
    key: str = "preview",
) -> Any:
    body: dict[str, Any] = {"kit_id": kit_id}
    if parameters is not None:
        body["parameters"] = parameters
    if excluded is not None:
        body["excluded_parcel_ids"] = excluded
    return client.post(
        f"/v1/estimate-rounds/{round_id}/site-setup/preview",
        headers=_headers(tenant, key=key),
        json=body,
    )


def _apply(
    client: TestClient,
    round_id: str,
    *,
    kit_id: str,
    base_version: int,
    parameters: dict[str, str] | None = None,
    excluded: list[str] | None = None,
    tenant: str = _TENANT,
    key: str = "apply",
) -> Any:
    body: dict[str, Any] = {"kit_id": kit_id, "base_version": base_version}
    if parameters is not None:
        body["parameters"] = parameters
    if excluded is not None:
        body["excluded_parcel_ids"] = excluded
    return client.post(
        f"/v1/estimate-rounds/{round_id}/site-setup/apply",
        headers=_headers(tenant, key=key),
        json=body,
    )


# --- fronteira de tenant (ADR-0060) -------------------------------------------------------


def test_a_rodada_ve_o_acervo_da_plataforma_e_o_do_tenant_e_nunca_o_de_outro(
    tmp_path: Path,
) -> None:
    """A fronteira do ADR-0060, com DOIS tenants: acervo alheio não aparece na escolha."""
    client = _client(tmp_path)
    round_id = _round_with_cascade(client)
    publicado = _publish_platform_kit(client)
    assert publicado.status_code == 201, publicado.text
    proprio = _insert_tenant_kit(client, tenant=_TENANT, name="ACERVO DA CASA")
    alheio = _insert_tenant_kit(client, tenant=_OTHER_TENANT, name="ACERVO DO VIZINHO")

    resposta = client.get(
        f"/v1/estimate-rounds/{round_id}/site-setup-kits", headers=_headers(key="escolha")
    )

    assert resposta.status_code == 200, resposta.text
    body = resposta.json()
    oferecidos = {kit["kit_id"]: kit["origin"] for kit in body["kits"]}
    assert oferecidos == {
        publicado.json()["kit_id"]: "platform",
        proprio: "tenant",
    }
    assert alheio not in oferecidos


def test_acervo_de_outro_tenant_e_indistinguivel_de_inexistente_no_lookup(
    tmp_path: Path,
) -> None:
    """A fronteira não vale só para a listagem: citar o acervo alheio por id é `404`."""
    client = _client(tmp_path)
    round_id = _round_with_cascade(client)
    alheio = _insert_tenant_kit(client, tenant=_OTHER_TENANT, name="ACERVO DO VIZINHO")

    resposta = _preview(client, round_id, kit_id=alheio, parameters={"prazo_meses": "2"})

    assert resposta.status_code == 404, resposta.text
    assert resposta.json()["detail"]["code"] == "NOT_FOUND"


def test_acervo_retirado_de_circulacao_some_da_escolha_e_recusa_na_aplicacao(
    tmp_path: Path,
) -> None:
    """Retirar não apaga: ele sai da escolha e a aplicação recusa com código próprio."""
    client = _client(tmp_path)
    round_id = _round_with_cascade(client)
    publicado = _publish_platform_kit(client)
    kit_id = publicado.json()["kit_id"]

    retirada = client.post(
        f"/v1/platform/site-setup-kits/{kit_id}/withdraw", headers=_operator(key="retirada")
    )
    assert retirada.status_code == 200, retirada.text
    assert retirada.json()["available"] is False
    assert retirada.json()["withdrawn_at"] is not None

    escolha = client.get(
        f"/v1/estimate-rounds/{round_id}/site-setup-kits", headers=_headers(key="escolha")
    )
    aplicacao = _preview(client, round_id, kit_id=kit_id, parameters={"prazo_meses": "2"})

    assert escolha.json()["kits"] == []
    assert aplicacao.status_code == 409, aplicacao.text
    assert aplicacao.json()["detail"]["code"] == "SITE_SETUP_KIT_WITHDRAWN"
    with _database(client).sessions() as session:
        assert session.scalars(select(SiteSetupKitRecord)).one().id == kit_id


def test_a_listagem_de_plataforma_nao_mostra_acervo_de_tenant(tmp_path: Path) -> None:
    """Acervo do cliente é dado dele: listá-lo aqui daria ao operador a lista de todos."""
    client = _client(tmp_path)
    publicado = _publish_platform_kit(client)
    _insert_tenant_kit(client, tenant=_TENANT, name="ACERVO DA CASA")

    resposta = client.get("/v1/platform/site-setup-kits", headers=_operator(key="lista"))

    assert resposta.status_code == 200, resposta.text
    assert [kit["kit_id"] for kit in resposta.json()["kits"]] == [publicado.json()["kit_id"]]


# --- publicação ---------------------------------------------------------------------------


def test_publicar_exige_platform_operator_antes_de_qualquer_lookup(tmp_path: Path) -> None:
    """`403` sem o papel, e nenhuma linha gravada — nem para quem tem papel de rodada."""
    client = _client(tmp_path)

    resposta = client.post(
        "/v1/platform/site-setup-kits",
        headers=_headers(key="sem-papel"),
        json={"name": "CANTEIRO PADRAO", "document": _kit_document()},
    )
    listagem = client.get("/v1/platform/site-setup-kits", headers=_headers(key="sem-papel-2"))

    assert resposta.status_code == 403
    assert resposta.json()["detail"]["code"] == "FORBIDDEN"
    assert listagem.status_code == 403
    with _database(client).sessions() as session:
        assert session.scalars(select(SiteSetupKitRecord)).all() == []


def test_publicar_a_mesma_versao_duas_vezes_e_recusa_e_nao_sobrescrita(tmp_path: Path) -> None:
    """Acervo é imutável: a segunda publicação recusa e a primeira continua sozinha."""
    client = _client(tmp_path)
    primeira = _publish_platform_kit(client, key="publicacao-1")
    assert primeira.status_code == 201, primeira.text

    segunda = _publish_platform_kit(
        client,
        document=_kit_document(source_label="OUTRO ROTULO"),
        key="publicacao-2",
    )

    assert segunda.status_code == 409, segunda.text
    assert segunda.json()["detail"]["code"] == "SITE_SETUP_KIT_ALREADY_PUBLISHED"
    assert segunda.json()["detail"]["details"]["kit_version"] == _KIT_VERSION
    with _database(client).sessions() as session:
        gravado = session.scalars(select(SiteSetupKitRecord)).one()
        assert gravado.source_label == "CANTEIRO SINTETICO"


def test_publicar_documento_invalido_recusa_como_dominio(tmp_path: Path) -> None:
    """Operando constante E paramétrico ao mesmo tempo é invariante do domínio, não schema."""
    client = _client(tmp_path)

    resposta = _publish_platform_kit(
        client,
        document=_kit_document(
            parcels=[
                {
                    "id": _WC_PARCEL_ID,
                    "code": _SCO_CODE,
                    "label": "WC QUIMICO",
                    "recipe": CalcRecipe.DECLARED_PRODUCT.value,
                    "operands": [_operand("QTD", value="1", parameter="prazo_meses")],
                }
            ]
        ),
    )

    assert resposta.status_code == 422, resposta.text
    detalhe = resposta.json()["detail"]
    assert detalhe["code"] == "DOMAIN_VALIDATION_FAILED"
    assert detalhe["details"]["code"] == "SITE_SETUP_OPERAND_AMBIGUOUS"


def test_a_escolha_traz_o_parametro_com_unidade_e_quantas_parcelas_o_citam(
    tmp_path: Path,
) -> None:
    """O que a tela precisa para pedir os campos: nome, unidade e "citado por N parcelas"."""
    client = _client(tmp_path)
    round_id = _round_with_cascade(client)
    _publish_platform_kit(client, document=_kit_with_two_parameters())

    resposta = client.get(
        f"/v1/estimate-rounds/{round_id}/site-setup-kits", headers=_headers(key="escolha")
    )

    kit = resposta.json()["kits"][0]
    assert kit["parcel_count"] == 3
    assert kit["parameters"] == [
        {"name": "prazo_meses", "unit": "meses", "cited_by": 1},
        {"name": "area_intervencao", "unit": "m2", "cited_by": 1},
    ]


def test_parametro_com_unidades_discordantes_sai_sem_unidade_e_nao_recusa(
    tmp_path: Path,
) -> None:
    """Escolher uma das duas faria a tela rotular o campo com o que metade das parcelas nega."""
    client = _client(tmp_path)
    round_id = _round_with_cascade(client)
    _publish_platform_kit(
        client,
        document=_kit_document(
            parcels=[
                {
                    "id": _WC_PARCEL_ID,
                    "code": _SCO_CODE,
                    "label": "WC QUIMICO",
                    "recipe": CalcRecipe.DECLARED_PRODUCT.value,
                    "operands": [_operand("MESES", parameter="prazo", unit="meses")],
                },
                {
                    "id": _PLACA_PARCEL_ID,
                    "code": _SCO_CODE,
                    "label": "VIGIA",
                    "recipe": CalcRecipe.DECLARED_PRODUCT.value,
                    "operands": [_operand("DIAS", parameter="prazo", unit="dias")],
                },
            ]
        ),
    )

    resposta = client.get(
        f"/v1/estimate-rounds/{round_id}/site-setup-kits", headers=_headers(key="escolha")
    )

    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["kits"][0]["parameters"] == [
        {"name": "prazo", "unit": None, "cited_by": 2}
    ]


# --- pré-visualização ---------------------------------------------------------------------


def test_a_previsualizacao_mostra_a_conta_e_nao_grava_nada(tmp_path: Path) -> None:
    """Critério 2: nenhuma revisão nova, nenhuma versão avançada — é leitura."""
    client = _client(tmp_path)
    round_id = _round_with_cascade(client)
    kit_id = _publish_platform_kit(client).json()["kit_id"]
    versao_antes = _round_version(client, round_id)
    revisoes_antes = len(_revisions(client, round_id))

    resposta = _preview(client, round_id, kit_id=kit_id, parameters={"prazo_meses": "2"})

    assert resposta.status_code == 200, resposta.text
    body = resposta.json()
    assert body["kit_version"] == _KIT_VERSION
    assert [(row["parcel_id"], row["quantity"]) for row in body["rows"]] == [
        (_WC_PARCEL_ID, "2.00"),
        (_PLACA_PARCEL_ID, "2.80"),
    ]
    assert body["rows"][0]["operands"] == [
        {"name": "QTD", "value": "1", "unit": None, "parameter": None},
        {"name": "MESES", "value": "2", "unit": "meses", "parameter": "prazo_meses"},
    ]
    assert body["blocked_parcel_ids"] == []
    assert _round_version(client, round_id) == versao_antes
    assert len(_revisions(client, round_id)) == revisoes_antes


def test_a_parcela_removida_na_previsualizacao_nao_aparece_e_nao_altera_as_demais(
    tmp_path: Path,
) -> None:
    """Critério 3 da feature, do lado da conferência."""
    client = _client(tmp_path)
    round_id = _round_with_cascade(client)
    kit_id = _publish_platform_kit(client).json()["kit_id"]

    resposta = _preview(
        client,
        round_id,
        kit_id=kit_id,
        parameters={"prazo_meses": "2"},
        excluded=[_WC_PARCEL_ID],
    )

    assert resposta.status_code == 200, resposta.text
    assert [(row["parcel_id"], row["quantity"]) for row in resposta.json()["rows"]] == [
        (_PLACA_PARCEL_ID, "2.80")
    ]


def test_parametro_faltante_a_previa_marca_e_a_aplicacao_recusa(tmp_path: Path) -> None:
    """A assimetria da T4, lado a lado no MESMO estado: a prévia mostra, o apply recusa.

    A prévia devolve **todas** as parcelas — as duas que só usam constante trazem quantidade
    calculada, e a que cita `area_intervencao` sai com `quantity: null` e o parâmetro
    nomeado. É essa lista que existe para a orçamentista poder remover a parcela que ela não
    tem como declarar. O apply, no mesmo estado, continua recusando por extenso com os DOIS
    nomes e sem gravar nada.
    """
    client = _client(tmp_path)
    round_id = _round_with_cascade(client)
    kit_id = _publish_platform_kit(client, document=_kit_with_two_parameters()).json()["kit_id"]
    versao = _round_version(client, round_id)

    previa = _preview(client, round_id, kit_id=kit_id, parameters={})
    aplicacao = _apply(client, round_id, kit_id=kit_id, base_version=versao, parameters={})

    assert previa.status_code == 200, previa.text
    corpo = previa.json()
    assert [(linha["parcel_id"], linha["quantity"]) for linha in corpo["rows"]] == [
        (_WC_PARCEL_ID, None),
        (_PLACA_PARCEL_ID, "2.80"),
        (_AREA_PARCEL_ID, None),
    ]
    assert [linha["missing_parameters"] for linha in corpo["rows"]] == [
        ["prazo_meses"],
        [],
        ["area_intervencao"],
    ]
    assert all(linha["code_absent"] is False for linha in corpo["rows"])
    assert corpo["blocked_parcel_ids"] == [_WC_PARCEL_ID, _AREA_PARCEL_ID]
    # Ausência é `null`, nunca `"0"`: zero é um valor, e o operando não resolvido não tem um.
    assert corpo["rows"][0]["operands"][1] == {
        "name": "MESES",
        "value": None,
        "unit": "meses",
        "parameter": "prazo_meses",
    }

    assert aplicacao.status_code == 422, aplicacao.text
    detalhe = aplicacao.json()["detail"]
    assert detalhe["code"] == "DOMAIN_VALIDATION_FAILED"
    assert detalhe["details"]["code"] == "SITE_SETUP_PARAMETER_MISSING"
    assert detalhe["details"]["parameters"] == ["prazo_meses", "area_intervencao"]
    assert _round_version(client, round_id) == versao
    assert _head_matrix(client, round_id) is None


def test_a_previa_aplicavel_depois_de_remover_a_parcela_que_bloqueava(tmp_path: Path) -> None:
    """A saída que a recusa prometia e não existia: remover na prévia e aplicar o resto.

    É o beco sem saída que a T4 corrige — antes dela, a recusa acontecia ANTES de haver
    lista de onde remover, e as parcelas que a rodada tinha como declarar não tinham caminho
    nenhum até a matriz.
    """
    client = _client(tmp_path)
    round_id = _round_with_cascade(client)
    kit_id = _publish_platform_kit(client, document=_kit_with_two_parameters()).json()["kit_id"]
    versao = _round_version(client, round_id)

    previa = _preview(
        client,
        round_id,
        kit_id=kit_id,
        parameters={"prazo_meses": "2"},
        excluded=[_AREA_PARCEL_ID],
    )
    aplicacao = _apply(
        client,
        round_id,
        kit_id=kit_id,
        base_version=versao,
        parameters={"prazo_meses": "2"},
        excluded=[_AREA_PARCEL_ID],
    )

    assert previa.status_code == 200, previa.text
    assert previa.json()["blocked_parcel_ids"] == []
    assert aplicacao.status_code == 200, aplicacao.text
    lida = CalcMatrix.model_validate(_head_matrix(client, round_id))
    assert [parcela.label for parcela in lida.services[0].contributions] == [
        "WC QUIMICO",
        "PLACA DE OBRA",
    ]


def test_parcela_excluida_e_bloqueada_nao_entra_em_blocked_parcel_ids(tmp_path: Path) -> None:
    """Ela não vai nascer de qualquer jeito: marcá-la pediria um campo que ninguém precisa."""
    client = _client(tmp_path)
    round_id = _round_with_cascade(client)
    kit_id = _publish_platform_kit(client, document=_kit_with_two_parameters()).json()["kit_id"]

    resposta = _preview(
        client,
        round_id,
        kit_id=kit_id,
        parameters={},
        excluded=[_AREA_PARCEL_ID],
    )

    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["excluded_parcel_ids"] == [_AREA_PARCEL_ID]
    assert _AREA_PARCEL_ID not in [linha["parcel_id"] for linha in corpo["rows"]]
    assert corpo["blocked_parcel_ids"] == [_WC_PARCEL_ID]


def test_codigo_fora_do_catalogo_a_previa_marca_e_a_aplicacao_recusa(tmp_path: Path) -> None:
    """O risco do acervo silenciosamente desatualizado: à vista na prévia, recusado no apply.

    A conta da parcela FECHA (ela só usa constante), e por isso a quantidade sai preenchida:
    o que falta não é o número, é o código no catálogo da rodada. Nascer, ela não nasce — o
    apply continua recusando nomeando o código, e nada é gravado.
    """
    client = _client(tmp_path)
    round_id = _round_with_cascade(client)
    kit_id = _publish_platform_kit(client, document=_kit_citing_absent_code()).json()["kit_id"]
    versao = _round_version(client, round_id)

    previa = _preview(client, round_id, kit_id=kit_id, parameters={})
    aplicacao = _apply(client, round_id, kit_id=kit_id, base_version=versao, parameters={})

    assert previa.status_code == 200, previa.text
    (linha,) = previa.json()["rows"]
    assert linha["code"] == _ABSENT_CODE
    assert linha["code_absent"] is True
    assert linha["missing_parameters"] == []
    assert linha["quantity"] == "1.00"
    assert previa.json()["blocked_parcel_ids"] == [_WC_PARCEL_ID]

    assert aplicacao.status_code == 422, aplicacao.text
    detalhe = aplicacao.json()["detail"]
    assert detalhe["code"] == "DOMAIN_VALIDATION_FAILED"
    assert detalhe["details"]["code"] == "SITE_SETUP_CODE_ABSENT"
    assert detalhe["details"]["codes"] == [_ABSENT_CODE]
    assert _head_matrix(client, round_id) is None


def test_exclusao_que_cita_parcela_inexistente_continua_recusando_na_previa(
    tmp_path: Path,
) -> None:
    """Erro de quem CHAMA, não estado do trabalho: parcela que não existe não tem o que marcar."""
    client = _client(tmp_path)
    round_id = _round_with_cascade(client)
    kit_id = _publish_platform_kit(client).json()["kit_id"]

    resposta = _preview(
        client,
        round_id,
        kit_id=kit_id,
        parameters={"prazo_meses": "2"},
        excluded=["ss_ffffffffffffffff"],
    )

    assert resposta.status_code == 422, resposta.text
    detalhe = resposta.json()["detail"]
    assert detalhe["code"] == "DOMAIN_VALIDATION_FAILED"
    assert detalhe["details"]["code"] == "SITE_SETUP_UNKNOWN_PARCEL"


def test_parametro_ilegivel_recusa_nomeando_todos_os_ruins(tmp_path: Path) -> None:
    """Texto que não é decimal exato nunca vira número aproximado, e a recusa lista todos."""
    client = _client(tmp_path)
    round_id = _round_with_cascade(client)
    kit_id = _publish_platform_kit(client, document=_kit_with_two_parameters()).json()["kit_id"]

    resposta = _preview(
        client,
        round_id,
        kit_id=kit_id,
        parameters={"prazo_meses": "dois", "area_intervencao": "-1"},
    )

    assert resposta.status_code == 422, resposta.text
    detalhe = resposta.json()["detail"]
    assert detalhe["code"] == "SITE_SETUP_PARAMETER_INVALID"
    assert detalhe["details"]["parameters"] == ["area_intervencao", "prazo_meses"]


# --- aplicação ----------------------------------------------------------------------------


def test_aplicar_grava_revisao_nova_avanca_a_versao_e_materializa_as_parcelas(
    tmp_path: Path,
) -> None:
    """O ato humano: matriz validada na revisão nova, com proveniência em cada parcela."""
    client = _client(tmp_path)
    round_id = _round_with_cascade(client)
    kit_id = _publish_platform_kit(client).json()["kit_id"]
    versao = _round_version(client, round_id)

    resposta = _apply(
        client, round_id, kit_id=kit_id, base_version=versao, parameters={"prazo_meses": "2"}
    )

    assert resposta.status_code == 200, resposta.text
    body = resposta.json()
    assert body["version"] == versao + 1
    assert body["applied_parcel_count"] == 2
    assert body["replaced_parcel_count"] == 0
    assert _round_version(client, round_id) == versao + 1

    matriz = _head_matrix(client, round_id)
    assert matriz is not None
    # Revalidado pelo domínio: a matriz gravada é lida de volta como `CalcMatrix`.
    lida = CalcMatrix.model_validate(matriz)
    assert [service.code for service in lida.services] == [_SCO_CODE]
    parcelas = lida.services[0].contributions
    assert [contribution.label for contribution in parcelas] == ["WC QUIMICO", "PLACA DE OBRA"]
    assert all(contribution.basis is ContributionBasis.STANDALONE for contribution in parcelas)
    assert all(contribution.source_item_id is None for contribution in parcelas)
    # A proveniência cita a IDENTIDADE do acervo aplicado, e não só a versão dele: é o
    # `kit_id` que a própria rota devolve, vindo da linha encontrada (ADR-0060, Emenda 1).
    assert [contribution.kit_origin for contribution in parcelas] == [
        SiteSetupOrigin(kit_id=UUID(kit_id), kit_version=_KIT_VERSION, parcel_id=_WC_PARCEL_ID),
        SiteSetupOrigin(kit_id=UUID(kit_id), kit_version=_KIT_VERSION, parcel_id=_PLACA_PARCEL_ID),
    ]
    assert body["kit_id"] == kit_id


def test_aplicar_com_base_version_defasada_e_conflito_e_nao_grava(tmp_path: Path) -> None:
    client = _client(tmp_path)
    round_id = _round_with_cascade(client)
    kit_id = _publish_platform_kit(client).json()["kit_id"]
    versao = _round_version(client, round_id)

    resposta = _apply(
        client,
        round_id,
        kit_id=kit_id,
        base_version=versao - 1,
        parameters={"prazo_meses": "2"},
    )

    assert resposta.status_code == 409, resposta.text
    assert resposta.json()["detail"]["code"] == "REVISION_CONFLICT"
    assert _head_matrix(client, round_id) is None


def test_aplicar_repete_a_resposta_com_a_mesma_idempotency_key(tmp_path: Path) -> None:
    """Replay não aplica duas vezes: a resposta gravada volta e a versão não anda de novo."""
    client = _client(tmp_path)
    round_id = _round_with_cascade(client)
    kit_id = _publish_platform_kit(client).json()["kit_id"]
    versao = _round_version(client, round_id)

    primeira = _apply(
        client,
        round_id,
        kit_id=kit_id,
        base_version=versao,
        parameters={"prazo_meses": "2"},
        key="apply-idem",
    )
    segunda = _apply(
        client,
        round_id,
        kit_id=kit_id,
        base_version=versao,
        parameters={"prazo_meses": "2"},
        key="apply-idem",
    )

    assert primeira.status_code == 200, primeira.text
    assert segunda.status_code == 200, segunda.text
    assert segunda.json() == primeira.json()
    assert _round_version(client, round_id) == versao + 1


def test_reaplicar_o_mesmo_acervo_nao_duplica_e_preserva_o_trabalho_alheio(
    tmp_path: Path,
) -> None:
    """O coração da task, com os TRÊS casos do merge no mesmo estado.

    A matriz de partida tem uma parcela autorada à mão e uma de OUTRO acervo. Reaplicar o
    acervo com os mesmos parâmetros deixa a matriz idêntica à da primeira aplicação (critério
    4), e as duas parcelas alheias continuam lá, intactas.
    """
    client = _client(tmp_path)
    round_id = _round_with_cascade(client)
    kit_id = _publish_platform_kit(client).json()["kit_id"]
    versao = _write_matrix(
        client,
        round_id,
        CalcMatrix(
            services=[
                ServiceContributions(
                    code=_SCO_CODE,
                    contributions=[_manual_contribution(), _other_kit_contribution()],
                )
            ]
        ),
        tenant=_TENANT,
    )

    primeira = _apply(
        client,
        round_id,
        kit_id=kit_id,
        base_version=versao,
        parameters={"prazo_meses": "2"},
        key="apply-1",
    )
    assert primeira.status_code == 200, primeira.text
    matriz_depois_da_primeira = _head_matrix(client, round_id)

    segunda = _apply(
        client,
        round_id,
        kit_id=kit_id,
        base_version=primeira.json()["version"],
        parameters={"prazo_meses": "2"},
        key="apply-2",
    )

    assert segunda.status_code == 200, segunda.text
    assert segunda.json()["replaced_parcel_count"] == 2
    assert _head_matrix(client, round_id) == matriz_depois_da_primeira

    lida = CalcMatrix.model_validate(_head_matrix(client, round_id))
    parcelas = lida.services[0].contributions
    assert [contribution.label for contribution in parcelas] == [
        "PARCELA A MAO",
        "PARCELA DE OUTRO ACERVO",
        "WC QUIMICO",
        "PLACA DE OBRA",
    ]
    # A parcela autorada à mão continua sem proveniência de acervo, e a do outro acervo
    # continua apontando para a identidade e a versão DELE: nenhuma das duas foi tocada.
    assert parcelas[0].kit_origin is None
    assert parcelas[1].kit_origin == SiteSetupOrigin(
        kit_id=_OTHER_KIT_ID, kit_version=_OTHER_KIT_VERSION, parcel_id=_WC_PARCEL_ID
    )


def test_dois_acervos_diferentes_com_a_mesma_versao_coexistem_na_matriz(tmp_path: Path) -> None:
    """O defeito que a Emenda 1 do ADR-0060 corrigiu, provado ponta a ponta.

    Dois acervos DIFERENTES, publicados com a MESMA `kit_version`, aplicados à mesma rodada.
    Sob a chave antiga (só a versão) o segundo apagaria as parcelas do primeiro; sob a chave
    `(kit_id, kit_version)` os dois coexistem, cada parcela citando o acervo de onde nasceu.
    """
    client = _client(tmp_path)
    round_id = _round_with_cascade(client)
    primeiro = _publish_platform_kit(client, name="CANTEIRO PADRAO", key="publicacao-1").json()
    segundo = _publish_platform_kit(
        client,
        name="CANTEIRO DE OUTRA LINHAGEM",
        document=_kit_document_de_outra_linhagem(),
        key="publicacao-2",
    ).json()
    # A premissa do teste: mesma versão, identidades distintas. Sem isto ele não prova nada.
    assert primeiro["kit_version"] == segundo["kit_version"] == _KIT_VERSION
    assert primeiro["kit_id"] != segundo["kit_id"]

    aplicacao_1 = _apply(
        client,
        round_id,
        kit_id=primeiro["kit_id"],
        base_version=_round_version(client, round_id),
        parameters={"prazo_meses": "2"},
        key="apply-1",
    )
    assert aplicacao_1.status_code == 200, aplicacao_1.text
    aplicacao_2 = _apply(
        client,
        round_id,
        kit_id=segundo["kit_id"],
        base_version=aplicacao_1.json()["version"],
        key="apply-2",
    )

    assert aplicacao_2.status_code == 200, aplicacao_2.text
    # Nada do primeiro acervo foi substituído: a versão coincide, a identidade não.
    assert aplicacao_2.json()["replaced_parcel_count"] == 0
    lida = CalcMatrix.model_validate(_head_matrix(client, round_id))
    parcelas = lida.services[0].contributions
    assert [contribution.label for contribution in parcelas] == [
        "WC QUIMICO",
        "PLACA DE OBRA",
        "VIGIA NOTURNO",
    ]
    assert [contribution.kit_origin for contribution in parcelas] == [
        SiteSetupOrigin(
            kit_id=UUID(primeiro["kit_id"]),
            kit_version=_KIT_VERSION,
            parcel_id=_WC_PARCEL_ID,
        ),
        SiteSetupOrigin(
            kit_id=UUID(primeiro["kit_id"]),
            kit_version=_KIT_VERSION,
            parcel_id=_PLACA_PARCEL_ID,
        ),
        SiteSetupOrigin(
            kit_id=UUID(segundo["kit_id"]),
            kit_version=_KIT_VERSION,
            parcel_id=_OUTRA_LINHAGEM_PARCEL_ID,
        ),
    ]


def test_reaplicar_um_dos_dois_acervos_de_mesma_versao_nao_toca_no_outro(
    tmp_path: Path,
) -> None:
    """A outra metade do mesmo caso: com os dois na matriz, reaplicar um substitui só o dele."""
    client = _client(tmp_path)
    round_id = _round_with_cascade(client)
    primeiro = _publish_platform_kit(client, name="CANTEIRO PADRAO", key="publicacao-1").json()
    segundo = _publish_platform_kit(
        client,
        name="CANTEIRO DE OUTRA LINHAGEM",
        document=_kit_document_de_outra_linhagem(),
        key="publicacao-2",
    ).json()
    aplicacao_1 = _apply(
        client,
        round_id,
        kit_id=primeiro["kit_id"],
        base_version=_round_version(client, round_id),
        parameters={"prazo_meses": "2"},
        key="apply-1",
    )
    aplicacao_2 = _apply(
        client,
        round_id,
        kit_id=segundo["kit_id"],
        base_version=aplicacao_1.json()["version"],
        key="apply-2",
    )
    assert aplicacao_2.status_code == 200, aplicacao_2.text

    reaplicacao = _apply(
        client,
        round_id,
        kit_id=primeiro["kit_id"],
        base_version=aplicacao_2.json()["version"],
        parameters={"prazo_meses": "2"},
        key="apply-3",
    )

    assert reaplicacao.status_code == 200, reaplicacao.text
    # As duas do primeiro acervo saíram e voltaram; a do segundo não foi contada nem tocada.
    assert reaplicacao.json()["replaced_parcel_count"] == 2
    lida = CalcMatrix.model_validate(_head_matrix(client, round_id))
    parcelas = lida.services[0].contributions
    assert [contribution.label for contribution in parcelas] == [
        "VIGIA NOTURNO",
        "WC QUIMICO",
        "PLACA DE OBRA",
    ]
    assert parcelas[0].kit_origin == SiteSetupOrigin(
        kit_id=UUID(segundo["kit_id"]),
        kit_version=_KIT_VERSION,
        parcel_id=_OUTRA_LINHAGEM_PARCEL_ID,
    )


def test_proveniencia_anterior_a_emenda_sobrevive_ao_apply_de_acervo_de_mesma_versao(
    tmp_path: Path,
) -> None:
    """`kit_id` nulo é "não observado", e "não observado" nunca é "o mesmo acervo".

    A matriz de partida tem uma parcela gravada antes da Emenda 1: sem identidade e com a
    MESMA versão do acervo que a rodada vai aplicar. Sob a chave antiga ela seria substituída
    por parcelas que nada provam ter nascido do mesmo lugar; sob a chave nova ela sobrevive
    intacta, como qualquer parcela alheia.
    """
    client = _client(tmp_path)
    round_id = _round_with_cascade(client)
    kit_id = _publish_platform_kit(client).json()["kit_id"]
    versao = _write_matrix(
        client,
        round_id,
        CalcMatrix(
            services=[
                ServiceContributions(code=_SCO_CODE, contributions=[_pre_amendment_contribution()])
            ]
        ),
        tenant=_TENANT,
    )

    resposta = _apply(
        client, round_id, kit_id=kit_id, base_version=versao, parameters={"prazo_meses": "2"}
    )

    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["replaced_parcel_count"] == 0
    lida = CalcMatrix.model_validate(_head_matrix(client, round_id))
    parcelas = lida.services[0].contributions
    assert [contribution.label for contribution in parcelas] == [
        "PARCELA ANTERIOR A EMENDA",
        "WC QUIMICO",
        "PLACA DE OBRA",
    ]
    # Continua sem identidade: nenhuma rodada gravada é migrada nem reinterpretada.
    assert parcelas[0].kit_origin == SiteSetupOrigin(
        kit_version=_KIT_VERSION, parcel_id=_WC_PARCEL_ID
    )


def test_o_apply_grava_na_proveniencia_o_id_da_linha_do_acervo_aplicado(
    tmp_path: Path,
) -> None:
    """A identidade gravada é conferida contra o BANCO, e não contra o corpo da requisição.

    Exercita o acervo do TENANT, a outra origem do ADR-0060: a proveniência das parcelas cita
    exatamente o `id` e a `kit_version` da linha aplicada.
    """
    client = _client(tmp_path)
    round_id = _round_with_cascade(client)
    kit_id = _insert_tenant_kit(client, tenant=_TENANT, name="ACERVO DA ORCAMENTISTA")

    resposta = _apply(
        client,
        round_id,
        kit_id=kit_id,
        base_version=_round_version(client, round_id),
        parameters={"prazo_meses": "2"},
    )

    assert resposta.status_code == 200, resposta.text
    with _database(client).sessions() as session:
        registro = session.get(SiteSetupKitRecord, kit_id)
        assert registro is not None
        esperada = (UUID(registro.id), registro.kit_version)
    lida = CalcMatrix.model_validate(_head_matrix(client, round_id))
    parcelas = lida.services[0].contributions
    assert parcelas
    assert [contribution.kit_origin for contribution in parcelas] == [
        SiteSetupOrigin(kit_id=esperada[0], kit_version=esperada[1], parcel_id=_WC_PARCEL_ID),
        SiteSetupOrigin(kit_id=esperada[0], kit_version=esperada[1], parcel_id=_PLACA_PARCEL_ID),
    ]


def test_reaplicar_com_parcela_removida_tira_so_aquela_parcela(tmp_path: Path) -> None:
    """A remoção da pré-visualização chega à matriz sem afetar as demais."""
    client = _client(tmp_path)
    round_id = _round_with_cascade(client)
    kit_id = _publish_platform_kit(client).json()["kit_id"]
    versao = _round_version(client, round_id)

    primeira = _apply(
        client,
        round_id,
        kit_id=kit_id,
        base_version=versao,
        parameters={"prazo_meses": "2"},
        key="apply-1",
    )
    segunda = _apply(
        client,
        round_id,
        kit_id=kit_id,
        base_version=primeira.json()["version"],
        parameters={"prazo_meses": "2"},
        excluded=[_WC_PARCEL_ID],
        key="apply-2",
    )

    assert segunda.status_code == 200, segunda.text
    lida = CalcMatrix.model_validate(_head_matrix(client, round_id))
    assert [contribution.label for contribution in lida.services[0].contributions] == [
        "PLACA DE OBRA"
    ]


# --- a matriz gravada, para a tela poder hidratar (T4) -------------------------------------


def _calc_matrix(
    client: TestClient, round_id: str, *, tenant: str = _TENANT, key: str = "matriz"
) -> Any:
    return client.get(
        f"/v1/estimate-rounds/{round_id}/calc-matrix", headers=_headers(tenant, key=key)
    )


def test_a_matriz_gravada_sai_na_leitura_sem_avancar_a_versao(tmp_path: Path) -> None:
    """Sem esta rota a matriz não saía em resposta nenhuma, e recarregar a tela perdia o que
    o acervo tinha aplicado. Leitura pura: nem revisão nova, nem contador andando."""
    client = _client(tmp_path)
    round_id = _round_with_cascade(client)
    kit_id = _publish_platform_kit(client).json()["kit_id"]
    aplicacao = _apply(
        client,
        round_id,
        kit_id=kit_id,
        base_version=_round_version(client, round_id),
        parameters={"prazo_meses": "2"},
    )
    assert aplicacao.status_code == 200, aplicacao.text
    versao = _round_version(client, round_id)
    revisoes = len(_revisions(client, round_id))

    resposta = _calc_matrix(client, round_id)

    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["round_id"] == round_id
    assert corpo["version"] == versao
    # O documento sai COMO ESTÁ GRAVADO, e é o mesmo que o apply devolveu.
    assert corpo["calc_matrix"] == _head_matrix(client, round_id)
    assert corpo["calc_matrix"] == aplicacao.json()["calc_matrix"]
    assert _round_version(client, round_id) == versao
    assert len(_revisions(client, round_id)) == revisoes


def test_a_matriz_e_null_no_regime_legado_e_nao_recusa(tmp_path: Path) -> None:
    """Rodada sem matriz é estado normal, não etapa fora de ordem: `null`, e não `409`."""
    client = _client(tmp_path)
    round_id = _round_with_cascade(client)

    resposta = _calc_matrix(client, round_id)

    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["calc_matrix"] is None


def test_a_matriz_de_outro_tenant_e_indistinguivel_de_inexistente(tmp_path: Path) -> None:
    """A fronteira da rodada vale na leitura nova como vale em todas as outras."""
    client = _client(tmp_path)
    round_id = _round_with_cascade(client)
    _write_matrix(client, round_id, _mixed_matrix(), tenant=_TENANT)

    resposta = _calc_matrix(client, round_id, tenant=_OTHER_TENANT, key="matriz-vizinho")

    assert resposta.status_code == 404, resposta.text
    assert resposta.json()["detail"]["code"] == "NOT_FOUND"


# --- autoria pela orçamentista ------------------------------------------------------------


def _author(
    client: TestClient,
    round_id: str,
    *,
    base_version: int,
    name: str = "CANTEIRO DA CASA",
    kit_version: str = "2.0.0",
    bindings: dict[str, str] | None = None,
    tenant: str = _TENANT,
    key: str = "autoria",
) -> Any:
    return client.post(
        f"/v1/estimate-rounds/{round_id}/site-setup/kits",
        headers=_headers(tenant, key=key),
        json={
            "base_version": base_version,
            "name": name,
            "kit_version": kit_version,
            "parameter_bindings": bindings if bindings is not None else {},
        },
    )


def _mixed_matrix() -> CalcMatrix:
    """Matriz com uma parcela de elemento da prancha e duas de canteiro.

    A primeira NÃO pode entrar no acervo: ela tem origem geométrica, e um acervo que a
    carregasse só serviria àquela praça.
    """
    return CalcMatrix(
        services=[
            ServiceContributions(
                code=_SCO_CODE,
                contributions=[
                    CalcContribution(
                        source_item_id="ti_00000000000000b1",
                        label="ALAMBRADO GALVANIZADO",
                        basis=ContributionBasis.FULL,
                        recipe=CalcRecipe.DECLARED_PRODUCT,
                        operands=[
                            CalcOperand(name="COMPRIMENTO", value=Decimal("10.00"), unit="m")
                        ],
                    ),
                    CalcContribution(
                        label="WC QUIMICO",
                        basis=ContributionBasis.STANDALONE,
                        recipe=CalcRecipe.QTY_TIMES_MONTHS,
                        operands=[
                            CalcOperand(name="QTD", value=Decimal("1")),
                            CalcOperand(name="MESES", value=Decimal("2"), unit="meses"),
                        ],
                    ),
                    CalcContribution(
                        label="PLACA DE OBRA",
                        basis=ContributionBasis.STANDALONE,
                        recipe=CalcRecipe.DECLARED_PRODUCT,
                        operands=[
                            CalcOperand(name="COMP", value=Decimal("2.00"), unit="m"),
                            CalcOperand(name="ALT", value=Decimal("1.40"), unit="m"),
                        ],
                    ),
                ],
            )
        ]
    )


def test_a_autoria_grava_so_standalone_e_respeita_os_bindings(tmp_path: Path) -> None:
    """Critério da autoria: só canteiro entra, e só o operando citado vira parâmetro."""
    client = _client(tmp_path)
    round_id = _round_with_cascade(client)
    versao = _write_matrix(client, round_id, _mixed_matrix(), tenant=_TENANT)

    resposta = _author(client, round_id, base_version=versao, bindings={"0.MESES": "prazo_meses"})

    assert resposta.status_code == 201, resposta.text
    body = resposta.json()
    assert body["origin"] == "tenant"
    assert body["kit_version"] == "2.0.0"
    assert body["source_label"] == "PRACA SINTETICA NORTE"
    assert body["parcel_count"] == 2

    with _database(client).sessions() as session:
        gravado = session.scalars(select(SiteSetupKitRecord)).one()
        assert gravado.tenant_id == _TENANT
        documento = gravado.document_json
    parcelas = cast("list[dict[str, Any]]", documento["parcels"])
    assert [parcel["label"] for parcel in parcelas] == ["WC QUIMICO", "PLACA DE OBRA"]
    # O operando citado virou referência a parâmetro; todos os demais viraram constante.
    assert parcelas[0]["operands"] == [
        {"name": "QTD", "value": "1", "parameter": None, "unit": None},
        {"name": "MESES", "value": None, "parameter": "prazo_meses", "unit": "meses"},
    ]
    assert parcelas[1]["operands"][0]["parameter"] is None


def test_a_autoria_nao_muda_a_rodada(tmp_path: Path) -> None:
    """A rodada não mudou: nem revisão nova, nem contador de versão avançado."""
    client = _client(tmp_path)
    round_id = _round_with_cascade(client)
    versao = _write_matrix(client, round_id, _mixed_matrix(), tenant=_TENANT)
    revisoes = len(_revisions(client, round_id))

    resposta = _author(client, round_id, base_version=versao)

    assert resposta.status_code == 201, resposta.text
    assert _round_version(client, round_id) == versao
    assert len(_revisions(client, round_id)) == revisoes


def test_binding_para_operando_inexistente_recusa_nomeando_o_binding(tmp_path: Path) -> None:
    """Ignorar o binding congelaria como constante um número que ela quis declarar."""
    client = _client(tmp_path)
    round_id = _round_with_cascade(client)
    versao = _write_matrix(client, round_id, _mixed_matrix(), tenant=_TENANT)

    inexistente = _author(
        client, round_id, base_version=versao, bindings={"0.SEMANAS": "prazo"}, key="autoria-1"
    )
    fora_da_lista = _author(
        client, round_id, base_version=versao, bindings={"9.MESES": "prazo"}, key="autoria-2"
    )
    malformado = _author(
        client, round_id, base_version=versao, bindings={"MESES": "prazo"}, key="autoria-3"
    )

    for resposta, esperado in (
        (inexistente, ["0.SEMANAS"]),
        (fora_da_lista, ["9.MESES"]),
        (malformado, ["MESES"]),
    ):
        assert resposta.status_code == 422, resposta.text
        detalhe = resposta.json()["detail"]
        assert detalhe["code"] == "SITE_SETUP_BINDING_INVALID"
        assert detalhe["details"]["bindings"] == esperado
    with _database(client).sessions() as session:
        assert session.scalars(select(SiteSetupKitRecord)).all() == []


def test_a_autoria_sem_matriz_recusa_como_ordem_da_cadeia(tmp_path: Path) -> None:
    client = _client(tmp_path)
    round_id = _round_with_cascade(client)

    resposta = _author(client, round_id, base_version=_round_version(client, round_id))

    assert resposta.status_code == 409, resposta.text
    detalhe = resposta.json()["detail"]
    assert detalhe["code"] == "ROUND_STAGE_NOT_READY"
    assert detalhe["details"]["stage"] == "estimate"


def test_a_autoria_sem_parcela_de_canteiro_recusa_com_codigo_proprio(tmp_path: Path) -> None:
    """Matriz só com parcela de elemento da prancha não vira acervo de canteiro nenhum."""
    client = _client(tmp_path)
    round_id = _round_with_cascade(client)
    versao = _write_matrix(
        client,
        round_id,
        CalcMatrix(
            services=[
                ServiceContributions(
                    code=_SCO_CODE,
                    contributions=[
                        CalcContribution(
                            source_item_id="ti_00000000000000b1",
                            label="ALAMBRADO GALVANIZADO",
                            basis=ContributionBasis.FULL,
                            recipe=CalcRecipe.DECLARED_PRODUCT,
                            operands=[CalcOperand(name="COMPRIMENTO", value=Decimal("10.00"))],
                        )
                    ],
                )
            ]
        ),
        tenant=_TENANT,
    )

    resposta = _author(client, round_id, base_version=versao)

    assert resposta.status_code == 422, resposta.text
    assert resposta.json()["detail"]["code"] == "SITE_SETUP_KIT_EMPTY"


def test_o_acervo_autorado_fica_visivel_so_para_o_tenant_que_o_autorou(tmp_path: Path) -> None:
    """Fecha o ciclo: o que a orçamentista autora não vaza para a rodada do vizinho."""
    client = _client(tmp_path)
    round_id = _round_with_cascade(client)
    versao = _write_matrix(client, round_id, _mixed_matrix(), tenant=_TENANT)
    autorado = _author(client, round_id, base_version=versao)
    assert autorado.status_code == 201, autorado.text
    vizinho = _round_with_cascade(client, tenant=_OTHER_TENANT, suffix="b")

    minha = client.get(
        f"/v1/estimate-rounds/{round_id}/site-setup-kits", headers=_headers(key="escolha-a")
    )
    dele = client.get(
        f"/v1/estimate-rounds/{vizinho}/site-setup-kits",
        headers=_headers(_OTHER_TENANT, key="escolha-b"),
    )

    assert [kit["kit_id"] for kit in minha.json()["kits"]] == [autorado.json()["kit_id"]]
    assert dele.json()["kits"] == []


def test_autorar_a_mesma_versao_duas_vezes_no_mesmo_tenant_e_recusa(tmp_path: Path) -> None:
    client = _client(tmp_path)
    round_id = _round_with_cascade(client)
    versao = _write_matrix(client, round_id, _mixed_matrix(), tenant=_TENANT)

    primeira = _author(client, round_id, base_version=versao, key="autoria-1")
    segunda = _author(client, round_id, base_version=versao, key="autoria-2")

    assert primeira.status_code == 201, primeira.text
    assert segunda.status_code == 409, segunda.text
    assert segunda.json()["detail"]["code"] == "SITE_SETUP_KIT_ALREADY_PUBLISHED"
