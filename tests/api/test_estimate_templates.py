"""O gabarito da prefeitura como artefato de plataforma (F-043 T2).

Até esta tarefa o gabarito de ordem fixa só existia como arquivo JSON lido por caminho no CLI
do worker — a API não conhecia `WorkbookTemplate` —, e por isso a jornada web não tinha como
oferecê-lo. Estes testes fixam as três rotas que o tornam dado publicável e versionado.

O que eles medem, e a ordem importa: **papel antes de lookup**, **domínio antes de escrita**,
**imutabilidade conferida na rota**. O terceiro é o que a `UniqueConstraint` não cobre — o
gabarito de plataforma tem `tenant_id` nulo, e `NULL` não colide com `NULL` nem em PostgreSQL
nem em SQLite —, e por isso ele tem teste próprio em vez de confiar no banco.

Dado 100% sintético: o gabarito real do cliente não está no repositório e não estará (F-043 T1,
"Decisão do dono já tomada"). A fixture entra pela mesma porta por onde o real entrará.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from fastapi.testclient import TestClient
from sqlalchemy import select

from croquito_api.config import ApiSettings
from croquito_api.database import Database, EstimateTemplateRecord
from croquito_api.main import create_app
from croquito_core.ids import new_uuid7
from tests.fakes import FakeObjectStore

_TENANT = "tenant-a"
_PLATFORM_TENANT = "tenant-plataforma"

_NAME = "PREFEITURA SINTETICA — PLANILHA ORÇAMENTÁRIA"
_SOURCE_LABEL = "Gabarito sintético de teste"
_REVISION = "REV. 03 — 2026-08"


def _client(tmp_path: Path) -> TestClient:
    database = Database(f"sqlite+pysqlite:///{tmp_path / 'estimate-templates.db'}")
    database.create_schema()
    settings = ApiSettings(
        database_url=f"sqlite+pysqlite:///{tmp_path / 'estimate-templates.db'}",
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
    tenant: str = _TENANT, roles: str = "orcamentista", *, key: str = "gabarito-001"
) -> dict[str, str]:
    return {
        "Authorization": f"Bearer test:{tenant}:pessoa-sintetica:{roles}",
        "Idempotency-Key": key,
    }


def _operator(key: str = "gabarito-plataforma") -> dict[str, str]:
    return _headers(_PLATFORM_TENANT, "platform_operator", key=key)


def _database(client: TestClient) -> Database:
    return cast(Database, cast(Any, client.app).state.database)


def _column(letter: str, label: str) -> dict[str, Any]:
    return {"letter": letter, "label": label, "width": 14}


def _grid(
    *,
    revision: str = _REVISION,
    rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Um `EstimateTemplateLayout` sintético, na forma que o documento real terá.

    Três linhas em vez de 433: o que se mede aqui é a fronteira da API, e o escritor que
    percorre o gabarito inteiro já tem oráculo próprio na T1.
    """
    return {
        "sheet_name": "PLANILHA ORÇAMENTÁRIA",
        "title": "PLANILHA ORÇAMENTÁRIA SINTÉTICA",
        "revision_label": revision,
        "memory_sheet_name": "MEMÓRIA DE CÁLCULO",
        "header_row": 8,
        "columns": {
            "group": _column("A", "GRUPO"),
            "item": _column("B", "ITEM"),
            "code": _column("C", "CÓDIGO"),
            "description": _column("D", "DISCRIMINAÇÃO"),
            "unit": _column("E", "UN"),
            "quantity": _column("F", "QUANT"),
            "unit_price": _column("G", "PREÇO UNIT"),
            "total": _column("H", "TOTAL"),
        },
        "rows": rows
        if rows is not None
        else [
            {
                "group": "01",
                "item": "01.1",
                "code": "PJ14100500(/)",
                "description": "PISO INTERTRAVADO 6CM",
                "unit": "m2",
                "unit_price": "62.40",
            },
            {
                "group": "01",
                "item": "01.2",
                "code": "PJ14150203(A)",
                "description": "PISO PODOTATIL DIRECIONAL",
                "unit": "m2",
                "unit_price": "148.20",
            },
            {
                "group": "02",
                "item": "02.1",
                "code": "PJ25400100(B)",
                "description": "GRAMA ESMERALDA EM PLACAS",
                "unit": "m2",
                "unit_price": "96.50",
            },
        ],
    }


def _publish(
    client: TestClient,
    *,
    name: str = _NAME,
    document: dict[str, Any] | None = None,
    key: str = "publica-gabarito",
    headers: dict[str, str] | None = None,
) -> Any:
    return client.post(
        "/v1/platform/estimate-templates",
        json={
            "name": name,
            "source_label": _SOURCE_LABEL,
            "document": document if document is not None else _grid(),
        },
        headers=headers if headers is not None else _operator(key),
    )


def _refusal_codes(body: Any) -> list[str]:
    """Todos os códigos estáveis que a recusa carrega, em qualquer profundidade do envelope.

    A busca é recursiva de propósito, como em `test_valuation_round_from_estimate._refusal_errors`:
    o topo do `problem+json` traz `DOMAIN_VALIDATION_FAILED`, e o código específico do domínio
    viaja nas violações. O que se mede é QUE a causa chega ao cliente, não em qual chave o
    envelope a aninhou — amarrar no caminho faria o teste quebrar numa mudança de forma que
    não muda o que a orçamentista lê.
    """
    encontrados: list[str] = []
    if isinstance(body, dict):
        for valor in body.values():
            if isinstance(valor, str) and valor.isupper() and "_" in valor:
                encontrados.append(valor)
            else:
                encontrados.extend(_refusal_codes(valor))
    elif isinstance(body, list):
        for item in body:
            encontrados.extend(_refusal_codes(item))
    return encontrados


# --- publicação ---------------------------------------------------------------------------


def test_o_gabarito_publicado_devolve_a_revisao_lida_de_dentro_do_documento(
    tmp_path: Path,
) -> None:
    """AC 1 e AC 5: a revisão não entra pelo corpo, e por isso não pode discordar do documento.

    É o `revision_label` que a planilha gerada IMPRIME. Deixá-lo entrar ao lado do conteúdo
    abriria a porta para a linha dizer uma revisão e o arquivo descrever outra — o silêncio que
    o campo existe para desfazer.
    """
    client = _client(tmp_path)

    response = _publish(client)

    assert response.status_code == 201, response.text
    corpo = response.json()
    assert corpo["template_version"] == _REVISION
    assert corpo["name"] == _NAME
    assert corpo["origin"] == "platform"
    assert corpo["row_count"] == 3
    assert corpo["sheet_name"] == "PLANILHA ORÇAMENTÁRIA"
    assert corpo["available"] is True
    assert corpo["withdrawn_at"] is None
    assert len(corpo["document_sha256"]) == 64
    # A revisão não é campo do corpo: mandá-la não a muda.
    assert "revision_label" not in corpo


def test_o_documento_inteiro_fica_gravado_e_as_linhas_nao_voltam_pelo_fio(
    tmp_path: Path,
) -> None:
    """O gabarito real tem 433 linhas; a listagem não tem o que fazer com elas."""
    client = _client(tmp_path)

    corpo = _publish(client).json()

    assert "rows" not in corpo
    with _database(client).sessions() as session:
        record = session.scalar(
            select(EstimateTemplateRecord).where(
                EstimateTemplateRecord.id == corpo["estimate_template_id"]
            )
        )
        assert record is not None
        assert record.tenant_id is None, "gabarito de plataforma não tem dono"
        assert len(record.document_json["rows"]) == 3


def test_o_gabarito_de_plataforma_e_imutavel_mesmo_com_tenant_nulo(tmp_path: Path) -> None:
    """AC 3, e é a armadilha principal desta tarefa.

    `NULL` não colide com `NULL`: a `UniqueConstraint` sobre `(tenant_id, name,
    template_version)` NÃO protege o acervo de plataforma, nem em PostgreSQL nem em SQLite.
    Quem recusa é a rota. Se esta conferência sair, republicar passa a sobrescrever em
    silêncio, e a planilha já gerada passa a citar uma revisão que descreve outro conteúdo.
    """
    client = _client(tmp_path)
    assert _publish(client, key="primeira").status_code == 201

    repetida = _publish(client, key="segunda")

    assert repetida.status_code == 409, repetida.text
    assert "ESTIMATE_TEMPLATE_ALREADY_PUBLISHED" in _refusal_codes(repetida.json())
    with _database(client).sessions() as session:
        assert len(session.scalars(select(EstimateTemplateRecord)).all()) == 1


def test_revisao_nova_e_linha_nova(tmp_path: Path) -> None:
    """O outro lado da imutabilidade: revisar o gabarito é publicar de novo, não sobrescrever."""
    client = _client(tmp_path)
    assert _publish(client, key="rev-3").status_code == 201

    quarta = _publish(client, document=_grid(revision="REV. 04 — 2026-09"), key="rev-4")

    assert quarta.status_code == 201, quarta.text
    assert quarta.json()["template_version"] == "REV. 04 — 2026-09"
    with _database(client).sessions() as session:
        assert len(session.scalars(select(EstimateTemplateRecord)).all()) == 2


def test_a_mesma_chave_de_idempotencia_nao_publica_duas_vezes(tmp_path: Path) -> None:
    """AC 7."""
    client = _client(tmp_path)
    primeira = _publish(client, key="mesma-chave")
    segunda = _publish(client, key="mesma-chave")

    assert primeira.status_code == 201
    assert segunda.status_code == 201
    assert primeira.json() == segunda.json()
    with _database(client).sessions() as session:
        assert len(session.scalars(select(EstimateTemplateRecord)).all()) == 1


# --- o domínio recusa antes da escrita ------------------------------------------------------


def test_codigo_fora_do_formato_de_catalogo_recusa_com_o_codigo_do_dominio(
    tmp_path: Path,
) -> None:
    """AC 4: a invariante sai como recusa do domínio, nunca como erro de esquema do FastAPI."""
    client = _client(tmp_path)
    linhas = cast(list[dict[str, Any]], _grid()["rows"])
    linhas[0]["code"] = "isto não é código"

    response = _publish(client, document=_grid(rows=linhas))

    assert response.status_code == 422, response.text
    assert "TEMPLATE_ESTIMATE_GRID_CODE_INVALID" in _refusal_codes(response.json())
    with _database(client).sessions() as session:
        assert session.scalars(select(EstimateTemplateRecord)).all() == []


def test_codigo_repetido_entre_linhas_recusa(tmp_path: Path) -> None:
    """Um código em duas linhas faria a quantidade cair numa das duas à sorte da iteração."""
    client = _client(tmp_path)
    linhas = cast(list[dict[str, Any]], _grid()["rows"])
    linhas[1]["code"] = linhas[0]["code"]

    response = _publish(client, document=_grid(rows=linhas))

    assert response.status_code == 422, response.text
    assert "TEMPLATE_ESTIMATE_GRID_DUPLICATE_CODE" in _refusal_codes(response.json())


def test_item_repetido_recusa(tmp_path: Path) -> None:
    client = _client(tmp_path)
    linhas = cast(list[dict[str, Any]], _grid()["rows"])
    linhas[1]["item"] = linhas[0]["item"]

    response = _publish(client, document=_grid(rows=linhas))

    assert response.status_code == 422, response.text
    assert "TEMPLATE_ESTIMATE_GRID_DUPLICATE_ITEM" in _refusal_codes(response.json())


# --- papel antes de lookup ------------------------------------------------------------------


def test_quem_nao_e_operador_de_plataforma_recebe_403_nas_tres_rotas(tmp_path: Path) -> None:
    """AC 2, e o `403` vem ANTES de qualquer lookup.

    O id abaixo não existe, e ainda assim a resposta é `403` e não `404`: quem não tem o papel
    não descobre, pela diferença entre os dois, o que existe no acervo.
    """
    client = _client(tmp_path)
    inexistente = "01930000-0000-7000-8000-00000000dead"

    publicacao = _publish(client, headers=_headers(key="sem-papel"))
    listagem = client.get("/v1/platform/estimate-templates", headers=_headers(key="sem-papel-2"))
    retirada = client.post(
        f"/v1/platform/estimate-templates/{inexistente}/withdraw",
        headers=_headers(key="sem-papel-3"),
    )

    assert publicacao.status_code == 403, publicacao.text
    assert listagem.status_code == 403, listagem.text
    assert retirada.status_code == 403, retirada.text


# --- listagem e retirada --------------------------------------------------------------------


def test_a_listagem_traz_o_acervo_inteiro_em_ordem_estavel(tmp_path: Path) -> None:
    client = _client(tmp_path)
    _publish(client, name="GABARITO B", key="b")
    _publish(client, name="GABARITO A", key="a")

    response = client.get("/v1/platform/estimate-templates", headers=_operator("lista"))

    assert response.status_code == 200, response.text
    nomes = [item["name"] for item in response.json()["templates"]]
    assert nomes == ["GABARITO A", "GABARITO B"]


def test_retirar_de_circulacao_carimba_e_nao_apaga(tmp_path: Path) -> None:
    """AC 6: uma planilha já publicada continua citando a revisão do gabarito que a gerou."""
    client = _client(tmp_path)
    template_id = _publish(client, key="para-retirar").json()["estimate_template_id"]

    retirada = client.post(
        f"/v1/platform/estimate-templates/{template_id}/withdraw",
        headers=_operator("retira"),
    )

    assert retirada.status_code == 200, retirada.text
    assert retirada.json()["available"] is False
    assert retirada.json()["withdrawn_at"] is not None
    listagem = client.get("/v1/platform/estimate-templates", headers=_operator("lista-pos"))
    assert [item["estimate_template_id"] for item in listagem.json()["templates"]] == [template_id]
    with _database(client).sessions() as session:
        record = session.scalar(
            select(EstimateTemplateRecord).where(EstimateTemplateRecord.id == template_id)
        )
        assert record is not None
        assert record.withdrawn_at is not None


def test_retirar_duas_vezes_nao_recarimba_a_data(tmp_path: Path) -> None:
    """Retirar o que já saiu de circulação devolve o registro como está.

    A comparação é do INSTANTE, não do texto: a primeira resposta sai do objeto em memória, que
    é tz-aware, e a segunda sai do SQLite, que não preserva fuso — em PostgreSQL as duas viriam
    com `Z`. A diferença é do banco de teste, e não do que a rota decide; o que o teste precisa
    provar é que a data não se moveu.
    """
    client = _client(tmp_path)
    template_id = _publish(client, key="dupla-retirada").json()["estimate_template_id"]
    primeira = client.post(
        f"/v1/platform/estimate-templates/{template_id}/withdraw",
        headers=_operator("retira-1"),
    )
    segunda = client.post(
        f"/v1/platform/estimate-templates/{template_id}/withdraw",
        headers=_operator("retira-2"),
    )

    assert primeira.status_code == 200
    assert segunda.status_code == 200
    primeiro_instante = datetime.fromisoformat(primeira.json()["withdrawn_at"])
    segundo_instante = datetime.fromisoformat(segunda.json()["withdrawn_at"])
    assert primeiro_instante.replace(tzinfo=None) == segundo_instante.replace(tzinfo=None)


def test_retirar_gabarito_de_tenant_pela_rota_de_plataforma_e_404(tmp_path: Path) -> None:
    """A cláusula `tenant_id IS NULL` no lookup não é redundante com o id.

    Nenhuma rota escreve gabarito com dono hoje — por isso a linha é semeada direto no banco.
    O teste existe agora justamente porque a cláusula não é consertável depois que o primeiro
    gabarito de tenant existir: sem ela, um operador de plataforma poderia retirar de
    circulação dado de um cliente.
    """
    client = _client(tmp_path)
    template_id = str(new_uuid7())
    with _database(client).sessions() as session:
        session.add(
            EstimateTemplateRecord(
                id=template_id,
                tenant_id=_TENANT,
                name="GABARITO DO TENANT",
                template_version="REV. 01",
                source_label="autorado pelo cliente",
                document_json=_grid(),
                document_sha256="d" * 64,
                withdrawn_at=None,
                created_by="orcamentista-sintetica",
                created_at=datetime.now(UTC),
            )
        )
        session.commit()

    retirada = client.post(
        f"/v1/platform/estimate-templates/{template_id}/withdraw",
        headers=_operator("retira-alheio"),
    )
    listagem = client.get("/v1/platform/estimate-templates", headers=_operator("lista-alheio"))

    assert retirada.status_code == 404, retirada.text
    assert listagem.json()["templates"] == [], (
        "gabarito de tenant não aparece no acervo da plataforma"
    )
