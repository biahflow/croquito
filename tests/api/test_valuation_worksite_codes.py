"""A etapa de código por FOLHA da praça (F-046 T4d, ADR-0057 decisão 6).

A T4c ligou o boletim da praça à `/v1` e, ao fazê-lo, encontrou o último bloqueador real:
não havia onde guardar o conjunto de códigos das folhas 2..N. `code_assignments_json` é
coluna única da revisão e `CodeAssignmentSet` é por PRANCHA, então a praça de N folhas
revisadas recusava alto — corretamente, nomeando os itens — e nunca fechava.

Cinco coisas são provadas aqui, e a última manda nas outras:

- **A praça de N folhas codificadas FECHA o boletim**, com o total saindo da consolidação
  por código das duas folhas e a memória saindo por folha.
- **O item fundido contribui UMA parcela** nesse caminho: a leitura absorvida entra com zero,
  ainda impressa na folha onde foi lida.
- **As cinco rotas da etapa alcançam a folha nomeada** — leitura, decisão, fechamento,
  revogação e shortlist —, e a folha inexistente é `404`.
- **A gravação é no lugar daquela folha**: a primeira viaja idêntica para a revisão nova.
- **A rodada de uma folha responde exatamente como hoje**, com as colunas novas em `NULL`.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any, cast

from fastapi.testclient import TestClient

from croquito_api.valuation_rounds import head_revision, round_plates
from croquito_valuation.assignment import CodeAssignmentSet
from croquito_valuation.models import Valuation
from tests.api.test_valuation_round_routes import (
    _TENANT,
    _build_calc,
    _client,
    _database,
    _headers,
    _round_with_decided_code,
)
from tests.api.test_valuation_worksite import _ITEM
from tests.api.test_valuation_worksite_calc import _CODIGO_DA_RODADA, _praca_na_v1


def _decidir_codigo(
    client: TestClient,
    round_id: str,
    *,
    base_version: int,
    key: str,
    item_id: str = _ITEM,
    **corpo: Any,
) -> Any:
    payload: dict[str, Any] = {
        "base_version": base_version,
        "item_id": item_id,
        "action": "confirm",
        "code": _CODIGO_DA_RODADA,
    }
    payload.update(corpo)
    return client.post(
        f"/v1/valuation-rounds/{round_id}/code-assignments/decisions",
        headers=_headers(key=key),
        json=payload,
    )


def _fechar_pacote(
    client: TestClient,
    round_id: str,
    *,
    base_version: int,
    key: str,
    item_id: str = _ITEM,
    **corpo: Any,
) -> Any:
    payload: dict[str, Any] = {"base_version": base_version, "item_id": item_id}
    payload.update(corpo)
    return client.post(
        f"/v1/valuation-rounds/{round_id}/code-assignments/closures",
        headers=_headers(key=key),
        json=payload,
    )


def _codificar_a_segunda_folha(client: TestClient, praca: dict[str, Any]) -> int:
    """Confirma o código do único item da folha 2 e fecha o pacote dele, pelas ROTAS.

    A folha 1 já chega codificada de `_praca_na_v1`; o que falta para a praça fechar é
    exatamente o que a T4d entrega. Passar pelas rotas, e não escrever o conjunto no banco, é
    o que faz este arquivo provar a ETAPA e não só a coluna nova.

    Devolve a versão corrente da rodada depois dos dois atos.
    """
    decidido = _decidir_codigo(
        client,
        praca["round_id"],
        base_version=praca["version"],
        key="codigo-folha-2",
        plate_id=praca["plate_b"],
    )
    assert decidido.status_code == 200, decidido.text
    fechado = _fechar_pacote(
        client,
        praca["round_id"],
        base_version=decidido.json()["version"],
        key="fechamento-folha-2",
        plate_id=praca["plate_b"],
    )
    assert fechado.status_code == 200, fechado.text
    return int(fechado.json()["version"])


# --------------------------------------------------------------------------------------
# a praça que fecha
# --------------------------------------------------------------------------------------


def test_a_praca_de_duas_folhas_codificadas_fecha_o_boletim(tmp_path: Path) -> None:
    """A razão de a T4d existir: a praça de N folhas passa a FECHAR.

    Antes daqui esta mesma rodada recusava com `CALC_ASSIGNMENT_MISSING`, porque a `/v1`
    guardava um conjunto de códigos só. Agora cada folha tem o seu, o boletim consome a união
    deles, o total sai da consolidação por código das duas e a memória sai por folha.
    """
    client = _client(tmp_path)
    praca = _praca_na_v1(client)

    versao = _codificar_a_segunda_folha(client, praca)
    resposta = _build_calc(client, praca["round_id"], base_version=versao, key="calc-praca-cheia")

    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    medicao = Valuation.model_validate(corpo["valuation"])
    # Um boletim POR FOLHA, cada um com chave própria: com mais de uma folha a praça deixa de
    # ser a folha (ADR-0057, decisão 8 pelo avesso).
    assert [boletim.worksite_key for boletim in medicao.bulletins] == [
        "praca-sintetica-norte-p1",
        "praca-sintetica-norte-p2",
    ]
    # 200,00 m2 na folha 1 e 50,00 m2 na folha 2, ao mesmo preço do catálogo da rodada: o
    # total é o consolidado das duas, e não o de uma delas.
    linhas = [linha for boletim in medicao.bulletins for linha in boletim.lines]
    assert [linha.quantity for linha in linhas] == [Decimal("200.00"), Decimal("50.00")]
    assert Decimal(corpo["total_amount"]) == sum((linha.total for linha in linhas), Decimal("0.00"))
    # A memória sai por folha, e cada bloco cita a folha de onde a leitura veio.
    assert {sheet.worksite_key for sheet in medicao.calc_sheets} == {
        "praca-sintetica-norte-p1",
        "praca-sintetica-norte-p2",
    }


def test_o_item_fundido_contribui_uma_parcela_so_no_boletim_da_praca(tmp_path: Path) -> None:
    """Declarada a fusão, a leitura absorvida deixa de contar — e continua à vista.

    O par `(plate_id, item_id)` é o mesmo elemento físico lido nas duas folhas. Sem a
    declaração as duas contam (fail-closed: erra para somar demais, e visivelmente); com ela,
    a que fica governa e a absorvida entra com zero, ainda impressa na folha onde foi lida.
    """
    client = _client(tmp_path)
    praca = _praca_na_v1(client)
    versao = _codificar_a_segunda_folha(client, praca)

    vinculo = client.post(
        f"/v1/valuation-rounds/{praca['round_id']}/worksite/identity-links",
        headers=_headers(key="vinculo-praca"),
        json={
            "base_version": versao,
            "kept": {"plate_id": praca["plate_a"], "item_id": _ITEM},
            "discarded": {"plate_id": praca["plate_b"], "item_id": _ITEM},
            "note": "mesmo piso desenhado nas duas folhas da praça",
        },
    )
    assert vinculo.status_code == 200, vinculo.text
    resposta = _build_calc(
        client,
        praca["round_id"],
        base_version=vinculo.json()["version"],
        key="calc-praca-fundida",
    )

    assert resposta.status_code == 200, resposta.text
    medicao = Valuation.model_validate(resposta.json()["valuation"])
    linhas = [linha for boletim in medicao.bulletins for linha in boletim.lines]
    # A parcela que FICA governa; a absorvida entra com zero em vez de sumir da folha dela.
    assert [linha.quantity for linha in linhas] == [Decimal("200.00"), Decimal("0.00")]
    assert linhas[1].total == Decimal("0.00")
    # Uma parcela só no total da praça: 200,00 m2, e não 250,00 m2.
    assert Decimal(resposta.json()["total_amount"]) == linhas[0].total


# --------------------------------------------------------------------------------------
# as rotas da etapa, por folha
# --------------------------------------------------------------------------------------


def test_a_leitura_da_etapa_de_codigo_por_folha_serve_o_conjunto_daquela_folha(
    tmp_path: Path,
) -> None:
    """`plate_id` ausente é a primeira folha; presente, a folha nomeada."""
    client = _client(tmp_path)
    praca = _praca_na_v1(client)
    _codificar_a_segunda_folha(client, praca)
    url = f"/v1/valuation-rounds/{praca['round_id']}/code-assignments"

    sem_folha = client.get(url, headers=_headers())
    primeira = client.get(url, headers=_headers(), params={"plate_id": praca["plate_a"]})
    segunda = client.get(url, headers=_headers(), params={"plate_id": praca["plate_b"]})
    inexistente = client.get(url, headers=_headers(), params={"plate_id": "folha-de-outra-praca"})

    assert sem_folha.status_code == 200, sem_folha.text
    # Ausente e primeira folha são a MESMA resposta, campo por campo: é essa igualdade que faz
    # a tela que ainda não conhece a praça continuar funcionando sem mudar uma linha.
    assert sem_folha.json() == primeira.json()
    assert sem_folha.json()["plate_id"] == praca["plate_a"]
    assert sem_folha.json()["assignments"]["plate_id"] == praca["plate_a"]
    assert segunda.status_code == 200, segunda.text
    assert segunda.json()["plate_id"] == praca["plate_b"]
    assert segunda.json()["assignments"]["plate_id"] == praca["plate_b"]
    assert segunda.json()["assignments_sha256"] != sem_folha.json()["assignments_sha256"]
    assert segunda.json()["closed"] == 1
    assert segunda.json()["pending_items"] == []
    assert inexistente.status_code == 404
    assert inexistente.json()["detail"]["code"] == "ROUND_PLATE_NOT_FOUND"


def test_a_folha_sem_decisao_de_codigo_e_estado_normal_e_nomeia_o_que_falta(
    tmp_path: Path,
) -> None:
    """Conjunto ausente na folha 2 não é erro: é a etapa aberta, com os itens nomeados."""
    client = _client(tmp_path)
    praca = _praca_na_v1(client)

    resposta = client.get(
        f"/v1/valuation-rounds/{praca['round_id']}/code-assignments",
        headers=_headers(),
        params={"plate_id": praca["plate_b"]},
    )

    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["plate_id"] == praca["plate_b"]
    assert corpo["assignments"] is None
    assert corpo["assignments_sha256"] is None
    assert corpo["confirmed"] == 0
    assert [item["item_id"] for item in corpo["pending_items"]] == [_ITEM]


def test_a_decisao_de_codigo_da_folha_2_nao_toca_o_conjunto_da_folha_1(tmp_path: Path) -> None:
    """A gravação é no lugar DAQUELA folha; a primeira viaja idêntica para a revisão nova."""
    client = _client(tmp_path)
    praca = _praca_na_v1(client)
    with _database(client).sessions() as session:
        cabeca = head_revision(session, round_id=praca["round_id"], tenant_id=_TENANT)
        assert cabeca is not None
        antes = cast(dict[str, Any], cabeca.code_assignments_json)

    _codificar_a_segunda_folha(client, praca)

    with _database(client).sessions() as session:
        cabeca = head_revision(session, round_id=praca["round_id"], tenant_id=_TENANT)
        assert cabeca is not None
        assert cabeca.code_assignments_json == antes
        mapa = cast(dict[str, Any], cabeca.worksite_plate_assignments_json)
        assert list(mapa) == [praca["plate_b"]]
        conjunto = CodeAssignmentSet.model_validate(mapa[praca["plate_b"]])
        assert conjunto.plate_id == praca["plate_b"]
        assert [assignment.item_id for assignment in conjunto.assignments] == [_ITEM]
        assert [closure.item_id for closure in conjunto.closures] == [_ITEM]


def test_a_decisao_de_codigo_em_folha_inexistente_e_recurso_ausente(tmp_path: Path) -> None:
    """Folha que não é desta praça é `404` de recurso, e não recusa de estado."""
    client = _client(tmp_path)
    praca = _praca_na_v1(client)

    resposta = _decidir_codigo(
        client,
        praca["round_id"],
        base_version=praca["version"],
        key="codigo-folha-fantasma",
        plate_id="folha-de-outra-praca",
    )

    assert resposta.status_code == 404, resposta.text
    assert resposta.json()["detail"]["code"] == "ROUND_PLATE_NOT_FOUND"


def test_o_desfazer_alcanca_a_folha_2_e_reabre_o_pacote_dela(tmp_path: Path) -> None:
    """Revogar também é por folha, e o efeito adiante é o da F-045."""
    client = _client(tmp_path)
    praca = _praca_na_v1(client)
    versao = _codificar_a_segunda_folha(client, praca)

    desfeito = client.post(
        f"/v1/valuation-rounds/{praca['round_id']}/code-assignments/revocations",
        headers=_headers(key="revogacao-folha-2"),
        json={
            "base_version": versao,
            "plate_id": praca["plate_b"],
            "item_id": _ITEM,
            "code": _CODIGO_DA_RODADA,
            "note": "confirmei o código errado nesta folha",
        },
    )

    assert desfeito.status_code == 200, desfeito.text
    corpo = desfeito.json()
    assert corpo["plate_id"] == praca["plate_b"]
    assert corpo["confirmed"] == 0
    assert corpo["closed"] == 0
    assert [item["item_id"] for item in corpo["pending_items"]] == [_ITEM]
    # O boletim volta a recusar aquele elemento, que é o efeito desejado do desfazer.
    recusa = _build_calc(
        client, praca["round_id"], base_version=corpo["version"], key="calc-apos-desfazer"
    )
    assert recusa.status_code == 422, recusa.text
    assert recusa.json()["detail"]["details"]["code"] == "CALC_ASSIGNMENT_MISSING"


def test_o_desfazer_em_folha_sem_conjunto_nenhum_recusa_sem_olhar_a_primeira(
    tmp_path: Path,
) -> None:
    """A folha 2 sem decisão nenhuma não herda o conjunto da folha 1 para poder desfazê-lo."""
    client = _client(tmp_path)
    praca = _praca_na_v1(client)

    resposta = client.post(
        f"/v1/valuation-rounds/{praca['round_id']}/code-assignments/revocations",
        headers=_headers(key="revogacao-folha-vazia"),
        json={
            "base_version": praca["version"],
            "plate_id": praca["plate_b"],
            "item_id": _ITEM,
            "code": _CODIGO_DA_RODADA,
            "note": "não há o que desfazer aqui",
        },
    )

    assert resposta.status_code == 422, resposta.text
    assert resposta.json()["detail"]["details"]["code"] == "ASSIGNMENT_REVOCATION_PAIR_UNKNOWN"


def test_a_shortlist_por_folha_e_calculada_sobre_o_pacote_daquela_folha(tmp_path: Path) -> None:
    """A shortlist é observação por ITEM, e os itens são os de UMA prancha."""
    client = _client(tmp_path)
    praca = _praca_na_v1(client)
    url = f"/v1/valuation-rounds/{praca['round_id']}/code-suggestions"

    primeira = client.get(url, headers=_headers())
    segunda = client.get(url, headers=_headers(), params={"plate_id": praca["plate_b"]})
    relida = client.get(url, headers=_headers(), params={"plate_id": praca["plate_b"]})

    assert primeira.status_code == 200, primeira.text
    assert primeira.json()["suggestions"]["plate_id"] == praca["plate_a"]
    assert segunda.status_code == 200, segunda.text
    assert segunda.json()["computed"] is True
    assert segunda.json()["suggestions"]["plate_id"] == praca["plate_b"]
    assert segunda.json()["suggestions"]["image_sha256"] == "b" * 64
    # Calculada UMA vez e persistida, por folha: a leitura seguinte serve o que está gravado.
    assert relida.json()["computed"] is False
    assert relida.json()["suggestions_sha256"] == segunda.json()["suggestions_sha256"]
    with _database(client).sessions() as session:
        cabeca = head_revision(session, round_id=praca["round_id"], tenant_id=_TENANT)
        assert cabeca is not None
        # A da primeira folha continua na coluna de sempre; a da folha 2 no mapa próprio.
        assert cabeca.code_suggestions_json is not None
        mapa = cast(dict[str, Any], cabeca.worksite_plate_suggestions_json)
        assert list(mapa) == [praca["plate_b"]]


# --------------------------------------------------------------------------------------
# a praça de uma folha não muda
# --------------------------------------------------------------------------------------


def test_a_etapa_de_codigo_de_uma_praca_de_uma_folha_responde_como_sempre(
    tmp_path: Path,
) -> None:
    """Nomear a única folha responde exatamente como não nomear folha nenhuma."""
    client = _client(tmp_path)
    preparada = _round_with_decided_code(client, key="praca-uma-folha-codigo")
    round_id = preparada["round_id"]
    with _database(client).sessions() as session:
        folha = round_plates(session, round_id=round_id, tenant_id=_TENANT)[0].plate_id
    url = f"/v1/valuation-rounds/{round_id}/code-assignments"

    sem_folha = client.get(url, headers=_headers())
    nomeada = client.get(url, headers=_headers(), params={"plate_id": folha})

    assert sem_folha.status_code == 200, sem_folha.text
    assert sem_folha.json() == nomeada.json()
    with _database(client).sessions() as session:
        cabeca = head_revision(session, round_id=round_id, tenant_id=_TENANT)
        assert cabeca is not None
        # A praça de uma folha nunca escreve no mapa: as colunas novas seguem `NULL`.
        assert cabeca.worksite_plate_assignments_json is None
        assert cabeca.worksite_plate_suggestions_json is None
