"""A prévia da abertura, no servidor (F-040 T7).

A T6 tinha posto essa conta no CLIENTE, contrariando a regra da jornada de medição em
`apps/web/AGENTS.md` ("a tela nunca soma, multiplica ou arredonda dinheiro/quantidade") e
obrigando o navegador a redescobrir duas identidades do domínio que nenhuma leitura expunha:
o acumulado (`vigente` menos `saldo`) e o medido do período, somado das linhas do boletim.

O teste que sustenta a rota é `test_a_previa_devolve_os_mesmos_numeros_da_rodada_criada`: a
prévia e a rodada realmente criada partem do MESMO corpo e precisam devolver os mesmos
números. Elas compartilham `_contracted_valuation_origin` e `_apply_declared_acts`, então
divergir aqui significa que alguém duplicou o caminho de domínio — que é exatamente o que
esta tarefa veio desfazer.

A semeadura reusa os helpers de `test_valuation_round_from_estimate`: a cadeia que produz o
orçamento assinado e a rodada anterior aprovada já é coberta lá, e repeti-la aqui só tornaria
estes testes lentos sem dizer nada novo sobre a prévia.
"""

from __future__ import annotations

import hashlib
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from croquito_api.database import ValuationRoundRecord, ValuationRoundRevisionRecord
from tests.api.test_valuation_round_from_estimate import (
    _CODE,
    _CODE_NEW,
    _OBJECT_KEY,
    _WORKSITE_KEY,
    _catalog_bytes,
    _estimate,
    _open_next,
    _re_ra,
    _seed_estimate_round,
    _seed_previous_round,
    _signed,
)
from tests.api.test_valuation_round_routes import (
    _OTHER_TENANT,
    _TENANT,
    _client,
    _database,
    _store,
)

_PREVIEW = "/v1/valuation-round-previews"


def _read_headers(tenant: str = _TENANT, roles: str = "orcamentista") -> dict[str, str]:
    """Cabeçalhos de LEITURA: sem `Idempotency-Key`.

    A prévia não grava, então não há nada a repetir — e é isso que estes cabeçalhos fixam.
    Usar `_headers` aqui esconderia a exigência caso ela voltasse por engano.
    """
    return {"Authorization": f"Bearer test:{tenant}:orcamentista-sintetica:{roles}"}


def _preview(client: TestClient, *, tenant: str = _TENANT, **body: Any) -> Any:
    return client.post(_PREVIEW, headers=_read_headers(tenant), json=dict(body))


def _com_catalogo(client: TestClient) -> str:
    """Põe os bytes do catálogo contratual no armazenamento e devolve o digest deles."""
    payload = _catalog_bytes()
    _store(client).put_direct(object_key=_OBJECT_KEY, body=payload, content_type="application/json")
    return hashlib.sha256(payload).hexdigest()


def _por_codigo(response: Any) -> dict[str, dict[str, Any]]:
    return {linha["code"]: linha for linha in response.json()["lines"]}


def test_a_previa_devolve_os_mesmos_numeros_da_rodada_criada(tmp_path: Path) -> None:
    """O par que impede a prévia de divergir da criação em silêncio.

    Mesma entrada — a mesma RE-RA sobre a mesma rodada anterior aprovada —, e os números da
    projeção precisam ser os que o consolidado gravado passa a declarar. Se um dia os dois
    caminhos se separarem, é aqui que a separação aparece.
    """
    client = _client(tmp_path)
    digest = _com_catalogo(client)
    previous = _seed_previous_round(client, measured=Decimal("5.00"), catalog_sha256=digest)
    amendment = _re_ra(
        label="2ª RE-RA",
        lines=[
            {"code": _CODE, "quantity_delta": "3"},
            {"code": _CODE_NEW, "quantity_delta": "2", "is_new_item": True},
        ],
    )

    projetado = _preview(client, previous_round_id=previous, period_number=2, amendment=amendment)
    assert projetado.status_code == 200, projetado.text

    criado = _open_next(client, previous, amendment=amendment)
    assert criado.status_code == 201, criado.text
    leitura = client.get(
        f"/v1/valuation-rounds/{criado.json()['round_id']}",
        headers=_read_headers(),
    )
    assert leitura.status_code == 200, leitura.text

    gravado = {q["code"]: q for q in leitura.json()["contracted"]["quantities"]}
    previsto = _por_codigo(projetado)
    assert set(previsto) == set(gravado)
    for code, quantidade in gravado.items():
        assert previsto[code]["contracted_quantity"] == quantidade["contracted_quantity"]
        # O vigente DEPOIS da declaração é o que a rodada nasce declarando.
        assert previsto[code]["new_current_quantity"] == quantidade["current_quantity"]
        assert previsto[code]["new_balance_quantity"] == quantidade["current_balance_quantity"]

    # E os números concretos, escritos por extenso: 12,00 contratados, 5,00 medidos e
    # aprovados no período 1, +3,00 de RE-RA e um item novo de +2,00.
    herdada = previsto[_CODE]
    assert herdada["contracted_quantity"] == "12.00"
    assert herdada["current_quantity"] == "12.00"
    # O delta sai NORMALIZADO pelo domínio ("3" vira "3.00"), com o sinal sempre explícito
    # para "+3,00" não chegar à tela como "3,00".
    assert herdada["amendment_delta"] == "+3.00"
    assert herdada["new_current_quantity"] == "15.00"
    assert herdada["accumulated_quantity"] == "5.00"
    assert herdada["new_balance_quantity"] == "10.00"
    nova = previsto[_CODE_NEW]
    assert nova["is_new_item"] is True
    assert nova["contracted_quantity"] == "0.00"
    assert nova["new_current_quantity"] == "2.00"
    assert nova["new_balance_quantity"] == "2.00"


def test_a_previa_nao_grava_nada(tmp_path: Path) -> None:
    """Somente leitura: nenhuma rodada nova, nenhuma revisão nova, versão intacta."""
    client = _client(tmp_path)
    digest = _com_catalogo(client)
    previous = _seed_previous_round(client, measured=Decimal("5.00"), catalog_sha256=digest)

    resposta = _preview(
        client,
        previous_round_id=previous,
        period_number=2,
        amendment=_re_ra(lines=[{"code": _CODE, "quantity_delta": "3"}]),
    )

    assert resposta.status_code == 200, resposta.text
    with _database(client).sessions() as session:
        rodadas = list(session.query(ValuationRoundRecord).all())
        assert [rodada.id for rodada in rodadas] == [previous]
        anterior = rodadas[0]
        assert anterior.version == 1
        # O consolidado da rodada ANTERIOR não se move: a projeção é da rodada que ainda
        # não existe, e escrevê-la de volta na origem reescreveria período já aprovado.
        stored = anterior.contract_workbook_json
        assert stored is not None
        assert stored["amendments"] == []
        revisoes = list(session.query(ValuationRoundRevisionRecord).all())
        assert len(revisoes) == 1


def test_a_previa_sem_declaracao_repete_contratado_no_vigente(tmp_path: Path) -> None:
    """A herança da rodada anterior: sem RE-RA, contratado e vigente repetem o mesmo número.

    É de propósito (decisão 4 do pacote de design aprovado): é o que faz a diferença aparecer
    no dia em que ela existir. `amendment_delta` sai `null` — ausência de declaração não é
    delta zero declarado.
    """
    client = _client(tmp_path)
    digest = _com_catalogo(client)
    previous = _seed_previous_round(client, measured=Decimal("5.00"), catalog_sha256=digest)

    resposta = _preview(client, previous_round_id=previous, period_number=2)

    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["worksite_key"] == _WORKSITE_KEY
    assert corpo["period_number"] == 2
    linha = _por_codigo(resposta)[_CODE]
    assert linha["contracted_quantity"] == "12.00"
    assert linha["current_quantity"] == "12.00"
    assert linha["new_current_quantity"] == "12.00"
    assert linha["amendment_delta"] is None
    assert linha["re_ratified"] is False
    assert linha["is_new_item"] is False


def test_a_previa_da_medicao_seguinte_traz_o_periodo_que_fechou(tmp_path: Path) -> None:
    """O medido do período, por código e no total, vem do SERVIDOR.

    Era a segunda derivação que a T6 fazia por fora: somar as linhas de `GET /bulletin` no
    navegador, porque o read-model da rodada não expunha o período medido.
    """
    client = _client(tmp_path)
    digest = _com_catalogo(client)
    previous = _seed_previous_round(client, measured=Decimal("5.00"), catalog_sha256=digest)

    resposta = _preview(client, previous_round_id=previous, period_number=2)

    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["previous_period_number"] == 1
    # 5,00 medidos a 50,00 o metro.
    assert corpo["measured_total_amount"] == "250.00"
    assert _por_codigo(resposta)[_CODE]["measured_quantity"] == "5.00"


def test_a_previa_do_orcamento_assinado_nao_cita_periodo_anterior(tmp_path: Path) -> None:
    """A outra porta contratada: não existe período anterior a citar, e o campo sai `null`.

    Declarar `"0.00"` ali afirmaria que nada foi medido antes, quando a verdade é que não há
    antes nenhum — a primeira medição nasce do orçamento assinado.
    """
    client = _client(tmp_path)
    estimate_round_id = _seed_estimate_round(client, document=_signed(_estimate()))

    resposta = _preview(
        client,
        estimate_round_id=estimate_round_id,
        period_number=1,
        amendment=_re_ra(),
    )

    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["previous_period_number"] is None
    assert corpo["measured_total_amount"] is None
    linha = _por_codigo(resposta)[_CODE]
    assert linha["measured_quantity"] is None
    # 12,00 contratados - 2,00 declarados = 10,00 vigentes, e o contratado não se move.
    assert linha["contracted_quantity"] == "12.00"
    assert linha["amendment_delta"] == "-2.00"
    assert linha["new_current_quantity"] == "10.00"


def test_a_previa_materializa_o_item_novo_do_catalogo_contratual(tmp_path: Path) -> None:
    """Descrição, unidade e preço do item novo vêm do catálogo — não da tela (ADR-0056, d. 7).

    Até a T6 quem procurava o código no catálogo era o navegador, com busca própria e
    debounce. A prévia agora devolve a linha já materializada pelo mesmo código que a criação
    executa, e a tela não precisa saber que existe um catálogo.
    """
    client = _client(tmp_path)
    digest = _com_catalogo(client)
    previous = _seed_previous_round(client, measured=Decimal("5.00"), catalog_sha256=digest)

    resposta = _preview(
        client,
        previous_round_id=previous,
        period_number=2,
        amendment=_re_ra(lines=[{"code": _CODE_NEW, "quantity_delta": "2", "is_new_item": True}]),
    )

    assert resposta.status_code == 200, resposta.text
    nova = _por_codigo(resposta)[_CODE_NEW]
    assert nova["description"] == "PORTAO SINTETICO GALVANIZADO"
    assert nova["unit"] == "un"
    assert nova["contracted_unit_price"] == "30.00"
    assert nova["is_new_item"] is True


def test_a_previa_recusa_o_item_novo_fora_do_catalogo(tmp_path: Path) -> None:
    """A recusa é a MESMA da criação, e chega antes de o orçamentista gravar.

    Uma prévia que projetasse a linha e só recusasse no `POST` da criação seria uma prévia
    que mente.
    """
    client = _client(tmp_path)
    digest = _com_catalogo(client)
    previous = _seed_previous_round(client, measured=Decimal("5.00"), catalog_sha256=digest)
    fora_do_catalogo = _re_ra(
        lines=[{"code": "CE99999999(/)", "quantity_delta": "2", "is_new_item": True}]
    )

    projetado = _preview(
        client, previous_round_id=previous, period_number=2, amendment=fora_do_catalogo
    )
    criado = _open_next(client, previous, amendment=fora_do_catalogo)

    assert projetado.status_code == 422, projetado.text
    assert projetado.json()["code"] == "AMENDMENT_NEW_ITEM_CODE_MISSING"
    assert criado.status_code == projetado.status_code
    assert criado.json()["code"] == projetado.json()["code"]


def test_a_previa_recusa_o_catalogo_ausente_do_armazenamento(tmp_path: Path) -> None:
    """Catálogo que não está no armazenamento é falha de ambiente: `CATALOG_REQUIRED`.

    Sem os bytes não há de onde materializar o item novo, e a prévia recusa pelo mesmo
    portão da criação — não por um erro genérico de servidor.
    """
    client = _client(tmp_path)
    # A rodada anterior declara um digest de catálogo que NINGUÉM gravou no armazenamento.
    previous = _seed_previous_round(client, measured=Decimal("5.00"))

    resposta = _preview(
        client,
        previous_round_id=previous,
        period_number=2,
        amendment=_re_ra(lines=[{"code": _CODE_NEW, "quantity_delta": "2", "is_new_item": True}]),
    )

    assert resposta.status_code == 422, resposta.text
    assert resposta.json()["code"] == "CATALOG_REQUIRED"


def test_a_previa_recusa_a_rodada_anterior_nao_aprovada(tmp_path: Path) -> None:
    """Mesmo portão da criação: o acumulado é a base do saldo (ADR-0056, decisão 5)."""
    client = _client(tmp_path)
    previous = _seed_previous_round(client, measured=Decimal("5.00"), approved=False)

    resposta = _preview(client, previous_round_id=previous, period_number=2)

    assert resposta.status_code == 409, resposta.text
    assert resposta.json()["code"] == "NEXT_ROUND_PREVIOUS_NOT_APPROVED"


def test_a_previa_recusa_periodo_fora_de_sequencia(tmp_path: Path) -> None:
    client = _client(tmp_path)
    previous = _seed_previous_round(client, measured=Decimal("5.00"))

    resposta = _preview(client, previous_round_id=previous, period_number=7)

    assert resposta.status_code == 409, resposta.text
    assert resposta.json()["code"] == "PERIOD_NOT_SEQUENTIAL"


def test_a_previa_exige_exatamente_uma_origem_contratada(tmp_path: Path) -> None:
    """Sem contratado não há contratado, vigente nem saldo a projetar."""
    client = _client(tmp_path)
    previous = _seed_previous_round(client, measured=Decimal("5.00"))

    nenhuma = _preview(client, period_number=2)
    duas = _preview(
        client,
        previous_round_id=previous,
        estimate_round_id=str(_seed_estimate_round(client, document=_signed(_estimate()))),
        period_number=2,
    )

    assert nenhuma.status_code == 422, nenhuma.text
    assert duas.status_code == 422, duas.text


def test_a_previa_nao_atravessa_tenant(tmp_path: Path) -> None:
    """A rodada anterior de outro tenant é indistinguível de inexistente."""
    client = _client(tmp_path)
    previous = _seed_previous_round(client, measured=Decimal("5.00"))

    resposta = _preview(client, tenant=_OTHER_TENANT, previous_round_id=previous, period_number=2)

    assert resposta.status_code == 404, resposta.text
    assert resposta.json()["code"] == "NOT_FOUND"


def test_a_previa_exige_o_papel_da_medicao(tmp_path: Path) -> None:
    client = _client(tmp_path)
    previous = _seed_previous_round(client, measured=Decimal("5.00"))

    resposta = client.post(
        _PREVIEW,
        headers=_read_headers(roles="revisor"),
        json={"previous_round_id": previous, "period_number": 2},
    )

    assert resposta.status_code == 403, resposta.text
