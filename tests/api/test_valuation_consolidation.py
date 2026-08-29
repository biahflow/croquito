"""A consolidação por código e a deriva declarada chegando ao cliente (F-046 T4e, ADR-0062).

A T4c ligou a praça inteira à `/v1` e a T5b tentou fechar a tela — e parou duas vezes, com
evidência, em vez de somar no navegador:

- O total consolidado do mesmo código ENTRE folhas não era servido por rota nenhuma. A
  resposta trazia o total da praça e o total de CADA folha; a linha por código somando as
  folhas — que é justamente o número que a PLANILHA GERAL entrega à prefeitura — só existia
  dentro do `.xlsx`.
- A deriva de centavo do ADR-0062 nunca saía do artefato: `ConsolidationDrift` nasce no plano
  da pasta e viaja no relatório de gravação e na auditoria, e a rota de exportação descartava
  o laudo.

Quatro coisas são provadas aqui, e a segunda manda nas outras:

- **A leitura do boletim traz a consolidação por código**, somando as folhas da praça.
- **Ela é o MESMO número que a planilha da mesma rodada imprime**, célula a célula. Se as
  duas derivações pudessem divergir seria bug, e é este teste que fecha a porta.
- **A deriva declarada chega ao cliente** com os dois valores, a diferença e o código.
- **A praça de UMA folha** tem consolidação trivialmente igual ao boletim da folha, e nada
  do que está gravado muda por servi-la.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from croquito_api.database import ValuationRoundRecord
from croquito_api.valuation_rounds import (
    bulletin_export_contract,
    document_digest,
    head_revision,
    load_catalog,
    render_valuation_workbook,
)
from croquito_valuation.models import Valuation
from croquito_valuation.template import default_template
from croquito_valuation.workbook_writer import plan_workbook
from tests.api.test_valuation_round_routes import (
    _TENANT,
    _build_calc,
    _client,
    _database,
    _headers,
    _round_with_decided_code,
)
from tests.api.test_valuation_worksite_calc import _praca_na_v1
from tests.api.test_valuation_worksite_codes import _codificar_a_segunda_folha

_LEITURA = {"Authorization": f"Bearer test:{_TENANT}:orcamentista-sintetica:orcamentista"}
"""Cabeçalho sem `Idempotency-Key`: o `GET` do boletim é leitura e não aceita chave."""


def _praca_medida(
    client: TestClient,
    *,
    key: str,
    catalog_unit_price: Decimal = Decimal("50.00"),
    quantidade_folha_1: Decimal = Decimal("200.00"),
    quantidade_folha_2: Decimal = Decimal("50.00"),
    **round_overrides: Any,
) -> dict[str, Any]:
    """Praça de duas folhas codificadas e com o boletim montado pelas ROTAS."""
    praca = _praca_na_v1(
        client,
        catalog_unit_price=catalog_unit_price,
        quantidade_folha_1=quantidade_folha_1,
        quantidade_folha_2=quantidade_folha_2,
        **round_overrides,
    )
    versao = _codificar_a_segunda_folha(client, praca)
    resposta = _build_calc(client, praca["round_id"], base_version=versao, key=key)
    assert resposta.status_code == 200, resposta.text
    return {"round_id": praca["round_id"], "corpo": cast(dict[str, Any], resposta.json())}


def _consolidacao_impressa(client: TestClient, round_id: str, valuation: Valuation) -> Any:
    """O que a pasta desta MESMA rodada imprime por código, na coluna corrente da GERAL.

    A rodada de `/v1` grava o `.xlsx` sem consolidado contratual — não há PLANILHA GERAL a
    imprimir lá —, então o oráculo é a pasta planejada sobre o consolidado que a própria
    rodada fabrica para o portão de exportação (`bulletin_export_contract`), com o catálogo
    instalado nela. É a mesma medição, o mesmo catálogo e o mesmo escritor; o que se prova
    é que a linha servida ao cliente e a linha impressa não podem divergir.

    A pasta é gravada e AUDITADA antes de o plano ser lido: laudo aprovado é o que faz do
    plano um oráculo do arquivo, e não só de si mesmo.
    """
    with _database(client).sessions() as session:
        record = session.get(ValuationRoundRecord, round_id)
        assert record is not None
        catalog = load_catalog(
            cast(Any, client.app).state.artifact_store,
            record,
            cache=cast(Any, client.app).state.catalog_cache,
        )
    contract = bulletin_export_contract(valuation)
    template = default_template()
    rendered = render_valuation_workbook(valuation, catalog, template, contract)
    assert rendered.audit.status == "ok"
    plan = plan_workbook(valuation, catalog, template, contract)
    geral = next(sheet for sheet in plan.sheets if sheet.name == template.general.sheet_name)
    celulas = {(cell.role, cell.item_number): cell for cell in geral.cells}
    return {
        line.code: (
            celulas[("general_current_quantity", line.item_number)].number,
            celulas[("general_current_amount", line.item_number)].number,
        )
        for line in contract.lines
    }


# --------------------------------------------------------------------------------------
# a consolidação por código
# --------------------------------------------------------------------------------------


def test_a_leitura_do_boletim_traz_a_consolidacao_por_codigo_entre_as_folhas(
    tmp_path: Path,
) -> None:
    """O número que faltava: o mesmo código somado ENTRE as folhas da praça.

    200,00 m2 na folha 1 e 50,00 m2 na folha 2, ao mesmo código: a resposta já trazia as duas
    linhas e o total da praça, mas não a linha de 250,00 m2 que a prefeitura lê. Cada decimal
    sai como TEXTO, e a diferença contra a soma dos boletins sai calculada — a tela não
    subtrai centavo.
    """
    client = _client(tmp_path)
    medida = _praca_medida(client, key="calc-consolidacao")

    consolidacao = medida["corpo"]["consolidation"]

    assert len(consolidacao) == 1
    linha = consolidacao[0]
    assert linha["code"] == "CE04100010(/)"
    assert linha["unit"] == "m2"
    assert linha["unit_price"] == "50.00"
    assert linha["quantity"] == "250.00"
    assert linha["amount"] == "12500.00"
    assert linha["bulletins_amount"] == "12500.00"
    assert linha["difference"] == "0.00"
    # E ela diz de QUAIS folhas o número veio, na ordem das folhas da praça.
    assert linha["worksite_keys"] == [
        "praca-sintetica-norte-p1",
        "praca-sintetica-norte-p2",
    ]
    # Sem truncamento a perder, nenhuma deriva é declarada — e a lista sai vazia, não ausente.
    assert medida["corpo"]["consolidation_drifts"] == []


@pytest.mark.parametrize(
    ("preco", "quantidade_1", "quantidade_2"),
    [
        # Sem deriva: 200,00 + 50,00 a 50,00, nenhum centavo a truncar.
        (Decimal("50.00"), Decimal("200.00"), Decimal("50.00")),
        # Com deriva: 1,15 + 2,15 a 12,50, e o consolidado fica um centavo acima da soma.
        (Decimal("12.50"), Decimal("1.15"), Decimal("2.15")),
    ],
    ids=["sem-deriva", "com-deriva"],
)
def test_a_consolidacao_servida_e_a_que_a_planilha_da_mesma_rodada_imprime(
    tmp_path: Path, preco: Decimal, quantidade_1: Decimal, quantidade_2: Decimal
) -> None:
    """Critério 2: duas derivações do mesmo número seriam duas verdades esperando divergir.

    A consolidação que a rota serve e a coluna corrente da PLANILHA GERAL saem da MESMA
    função (`workbook_writer.consolidate_by_code`); este teste amarra as duas pontas no
    artefato da própria rodada, código a código.

    O caminho COM deriva entra de propósito: é justamente quando `TRUNC(Σq x p)` deixa de ser
    `Σ TRUNC(qᵢ x p)` que uma segunda derivação silenciosa apareceria como um centavo de
    diferença entre o que a tela mostra e o que a prefeitura lê.
    """
    client = _client(tmp_path)
    medida = _praca_medida(
        client,
        key="calc-paridade",
        catalog_unit_price=preco,
        quantidade_folha_1=quantidade_1,
        quantidade_folha_2=quantidade_2,
    )
    valuation = Valuation.model_validate(medida["corpo"]["valuation"])

    impresso = _consolidacao_impressa(client, medida["round_id"], valuation)

    servido = {
        linha["code"]: (Decimal(linha["quantity"]), Decimal(linha["amount"]))
        for linha in medida["corpo"]["consolidation"]
    }
    assert servido == impresso


def test_a_deriva_de_centavo_declarada_chega_ao_cliente(tmp_path: Path) -> None:
    """Critério 3: o ADR-0062 mandou DECLARAR a deriva a quem confere — e quem confere lê a tela.

    1,15 m2 e 2,15 m2 a 12,50: cada folha trunca a própria linha (14,37 + 26,87 = 41,24) e a
    consolidação imprime `TRUNC(3,30 x 12,50) = 41,25`. O centavo de diferença não é erro nem
    recusa: é fato declarado, com os dois valores e o código à vista.

    A deriva sai na LEITURA do boletim, e não do laudo da exportação, por dois motivos que o
    `_bulletin_payload` registra: a rodada de `/v1` grava a pasta sem consolidado contratual,
    então a lista da auditoria é sempre vazia neste caminho; e a conferência acontece antes de
    exportar.
    """
    client = _client(tmp_path)
    medida = _praca_medida(
        client,
        key="calc-deriva",
        catalog_unit_price=Decimal("12.50"),
        quantidade_folha_1=Decimal("1.15"),
        quantidade_folha_2=Decimal("2.15"),
    )

    derivas = medida["corpo"]["consolidation_drifts"]

    assert len(derivas) == 1
    deriva = derivas[0]
    assert deriva["reason"] == "TRUNC_CONSOLIDATION_DRIFT"
    assert deriva["code"] == "CE04100010(/)"
    assert deriva["quantity"] == "3.30"
    assert deriva["general"] == "41.25"
    assert deriva["bulletins"] == "41.24"
    assert deriva["difference"] == "0.01"
    # A linha de cada folha continua truncando só o que ela mede: nenhum boletim é ajustado.
    linhas = [
        linha for boletim in medida["corpo"]["valuation"]["bulletins"] for linha in boletim["lines"]
    ]
    assert [linha["total"] for linha in linhas] == ["14.37", "26.87"]
    assert medida["corpo"]["total_amount"] == "41.24"
    # E a consolidação servida carrega os dois valores lado a lado, não só o que governa.
    linha_consolidada = medida["corpo"]["consolidation"][0]
    assert linha_consolidada["amount"] == "41.25"
    assert linha_consolidada["bulletins_amount"] == "41.24"


def test_a_consolidacao_sai_tambem_na_leitura_do_boletim_gravado(tmp_path: Path) -> None:
    """O `GET` responde a mesma consolidação do ato que a montou; recarregar a tela não a perde."""
    client = _client(tmp_path)
    medida = _praca_medida(client, key="calc-consolidacao-get")

    leitura = client.get(f"/v1/valuation-rounds/{medida['round_id']}/bulletin", headers=_LEITURA)

    assert leitura.status_code == 200, leitura.text
    assert leitura.json()["consolidation"] == medida["corpo"]["consolidation"]
    assert leitura.json()["consolidation_drifts"] == medida["corpo"]["consolidation_drifts"]


def test_a_praca_de_uma_folha_consolida_o_proprio_boletim_e_nao_grava_nada_novo(
    tmp_path: Path,
) -> None:
    """Critério 4: com uma folha só a consolidação é trivial — e continua sendo DERIVADA.

    Nada da consolidação entra em `valuation_json`: o digest servido continua sendo o do
    documento gravado, que é o mesmo boletim de sempre. Persistir um número derivado ao lado
    do fato que o gera seria criar dois donos para ele.
    """
    client = _client(tmp_path)
    preparada = _round_with_decided_code(client, key="praca-uma-folha-t4e")
    resposta = _build_calc(
        client, preparada["round_id"], base_version=preparada["version"], key="calc-uma-folha"
    )

    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    valuation = Valuation.model_validate(corpo["valuation"])
    assert len(valuation.bulletins) == 1
    linhas = valuation.bulletins[0].lines
    assert [linha["code"] for linha in corpo["consolidation"]] == [linha.code for linha in linhas]
    assert [Decimal(linha["amount"]) for linha in corpo["consolidation"]] == [
        linha.total for linha in linhas
    ]
    assert corpo["consolidation_drifts"] == []

    with _database(client).sessions() as session:
        cabeca = head_revision(session, round_id=preparada["round_id"], tenant_id=_TENANT)
        assert cabeca is not None
        gravado = cabeca.valuation_json
        assert gravado is not None
    # O documento gravado é o boletim e só ele; a consolidação não foi persistida ao lado.
    assert "consolidation" not in gravado
    assert corpo["valuation_sha256"] == document_digest(gravado)


def test_a_consolidacao_acompanha_a_aprovacao_e_a_exportacao(tmp_path: Path) -> None:
    """As quatro respostas do boletim servem a mesma consolidação, do build ao `.xlsx` publicado."""
    client = _client(tmp_path)
    medida = _praca_medida(client, key="calc-consolidacao-fluxo")
    round_id = medida["round_id"]

    aprovacao = client.post(
        f"/v1/valuation-rounds/{round_id}/approve",
        headers=_headers(key="aprovar-consolidacao"),
        json={"base_version": medida["corpo"]["version"]},
    )
    assert aprovacao.status_code == 200, aprovacao.text
    assert aprovacao.json()["consolidation"] == medida["corpo"]["consolidation"]

    exportacao = client.post(
        f"/v1/valuation-rounds/{round_id}/bulletin/export",
        headers=_headers(key="exportar-consolidacao"),
        json={"base_version": aprovacao.json()["version"]},
    )
    assert exportacao.status_code == 200, exportacao.text
    assert exportacao.json()["consolidation"] == medida["corpo"]["consolidation"]
    assert exportacao.json()["workbook_present"] is True
