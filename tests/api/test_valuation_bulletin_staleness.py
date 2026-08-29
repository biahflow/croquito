"""O boletim gravado que deixou de descrever a praça (F-046 T5c).

A T4c ligou o boletim da praça inteira e a T4e trouxe a consolidação por código; a
declaração de identidade (decisão 4 do ADR-0057) passou a mudar o que a praça deve somar.
O que faltava era a rodada saber DIZER isso: o boletim seguia gravado com o total antigo,
o `valuation_sha256` seguia o mesmo — porque de fato nada nele mudou — e o único aviso
existia no toast de um ato que já tinha passado. A ordem que o pacote de design desenha —
montar, ver a dupla contagem, declarar a identidade, ver o total novo — não era percorrível
numa rodada só.

O que se prova aqui:

- **Boletim recém-montado não nasce vencido**, e os dois digests de fonte saem iguais:
  aviso permanente é aviso que se aprende a ignorar.
- **Os atos que mudam o total vencem o boletim gravado** — declarar identidade, revogar
  código, acrescentar folha —, e o vencimento é dito pelo SERVIDOR, comparando o carimbo
  gravado no ato de montar com as fontes de agora.
- **Remontar devolve o estado não vencido**, com o total novo e o carimbo novo.
- **A rodada montada antes desta feature não passa a mentir**: sem o carimbo do passado
  nada é afirmado, e ela sai como não vencida com os dois digests à vista.
- **A aprovação e a caducidade dela continuam sendo outra pergunta**: o boletim vencido não
  se confunde com a assinatura caduca.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from croquito_api.valuation_rounds import BULLETIN_SOURCES_DIGEST, head_revision
from tests.api.test_valuation_round_routes import (
    _TENANT,
    _associate_plate,
    _build_calc,
    _client,
    _database,
    _headers,
    _round_with_decided_code,
)
from tests.api.test_valuation_worksite import _ITEM
from tests.api.test_valuation_worksite_calc import _CODIGO_DA_RODADA, _praca_na_v1
from tests.api.test_valuation_worksite_codes import _codificar_a_segunda_folha

_LEITURA = {"Authorization": f"Bearer test:{_TENANT}:orcamentista-sintetica:orcamentista"}


def _estado(client: TestClient, round_id: str) -> dict[str, Any]:
    resposta = client.get(f"/v1/valuation-rounds/{round_id}", headers=_LEITURA)
    assert resposta.status_code == 200, resposta.text
    return dict(resposta.json()["bulletin"])


def _boletim(client: TestClient, round_id: str) -> dict[str, Any]:
    resposta = client.get(f"/v1/valuation-rounds/{round_id}/bulletin", headers=_LEITURA)
    assert resposta.status_code == 200, resposta.text
    return dict(resposta.json())


# --------------------------------------------------------------------------------------
# o boletim recém-montado
# --------------------------------------------------------------------------------------


def test_o_boletim_recem_montado_nao_nasce_vencido(tmp_path: Path) -> None:
    """Critério 5: sem ato posterior não há o que vencer, nas três respostas que o servem."""
    client = _client(tmp_path)
    preparada = _round_with_decided_code(client, key="boletim-novo")
    round_id = preparada["round_id"]

    montado = _build_calc(client, round_id, base_version=preparada["version"], key="calc-novo")

    assert montado.status_code == 200, montado.text
    for corpo in (montado.json(), _boletim(client, round_id), _estado(client, round_id)):
        assert corpo["stale"] is False
        # Os dois digests saem, e iguais: é a igualdade que sustenta o "não vencido".
        assert corpo["sources_digest"] is not None
        assert corpo["sources_digest"] == corpo["current_sources_digest"]
    # E o carimbo ficou gravado na revisão do boletim, ao lado dele.
    with _database(client).sessions() as session:
        cabeca = head_revision(session, round_id=round_id, tenant_id=_TENANT)
        assert cabeca is not None
        assert (cabeca.artifact_digests_json or {})[BULLETIN_SOURCES_DIGEST] == montado.json()[
            "sources_digest"
        ]


def test_a_rodada_sem_boletim_nao_tem_o_que_vencer(tmp_path: Path) -> None:
    """Etapa que não aconteceu sai neutra, e não como "vencida" nem como "em dia"."""
    client = _client(tmp_path)
    preparada = _round_with_decided_code(client, key="sem-boletim")

    bulletin = _estado(client, preparada["round_id"])

    assert bulletin["present"] is False
    assert bulletin["stale"] is False
    assert bulletin["sources_digest"] is None
    assert bulletin["current_sources_digest"] is None


# --------------------------------------------------------------------------------------
# os atos que vencem o boletim
# --------------------------------------------------------------------------------------


def test_a_identidade_declarada_vence_o_boletim_gravado(tmp_path: Path) -> None:
    """O defeito que esta tarefa fecha: o ato mandava remontar e nada dizia que era preciso.

    O boletim gravado continua o mesmo — e o `valuation_sha256` prova isso, porque de fato
    ninguém o tocou. O que muda é a praça de onde ele saiu, e é essa diferença que a rodada
    passa a declarar.
    """
    client = _client(tmp_path)
    praca = _praca_na_v1(client)
    versao = _codificar_a_segunda_folha(client, praca)
    montado = _build_calc(
        client, praca["round_id"], base_version=versao, key="calc-antes-do-vinculo"
    )
    assert montado.status_code == 200, montado.text
    antes = montado.json()
    assert Decimal(antes["total_amount"]) == Decimal("12500.00")

    vinculo = client.post(
        f"/v1/valuation-rounds/{praca['round_id']}/worksite/identity-links",
        headers=_headers(key="vinculo-que-vence"),
        json={
            "base_version": antes["version"],
            "kept": {"plate_id": praca["plate_a"], "item_id": _ITEM},
            "discarded": {"plate_id": praca["plate_b"], "item_id": _ITEM},
            "note": "mesmo piso desenhado nas duas folhas da praça",
        },
    )
    assert vinculo.status_code == 200, vinculo.text

    depois = _estado(client, praca["round_id"])
    assert depois["stale"] is True
    assert depois["sources_digest"] == antes["sources_digest"]
    assert depois["current_sources_digest"] != depois["sources_digest"]
    # A medição gravada é a MESMA: o total antigo continua ali, e é justamente por isso que
    # o vencimento precisa ser dito.
    assert depois["valuation_sha256"] == antes["valuation_sha256"]
    assert Decimal(_boletim(client, praca["round_id"])["total_amount"]) == Decimal("12500.00")


def test_remontar_o_boletim_devolve_o_estado_nao_vencido_com_o_total_novo(
    tmp_path: Path,
) -> None:
    """Critérios 2 e 5: o ato que a tela passa a oferecer resolve o estado que ela declara."""
    client = _client(tmp_path)
    praca = _praca_na_v1(client)
    versao = _codificar_a_segunda_folha(client, praca)
    montado = _build_calc(client, praca["round_id"], base_version=versao, key="calc-1")
    assert montado.status_code == 200, montado.text
    vinculo = client.post(
        f"/v1/valuation-rounds/{praca['round_id']}/worksite/identity-links",
        headers=_headers(key="vinculo-remontagem"),
        json={
            "base_version": montado.json()["version"],
            "kept": {"plate_id": praca["plate_a"], "item_id": _ITEM},
            "discarded": {"plate_id": praca["plate_b"], "item_id": _ITEM},
            "note": "mesmo piso desenhado nas duas folhas da praça",
        },
    )
    assert vinculo.status_code == 200, vinculo.text
    assert _estado(client, praca["round_id"])["stale"] is True

    remontado = _build_calc(
        client, praca["round_id"], base_version=vinculo.json()["version"], key="calc-2"
    )

    assert remontado.status_code == 200, remontado.text
    corpo = remontado.json()
    assert corpo["stale"] is False
    assert corpo["sources_digest"] == corpo["current_sources_digest"]
    # 200,00 m2 a 50,00, uma vez só: a fusão declarada chegou ao total.
    assert Decimal(corpo["total_amount"]) == Decimal("10000.00")
    assert _estado(client, praca["round_id"])["stale"] is False


def test_a_revogacao_de_codigo_vence_o_boletim_gravado(tmp_path: Path) -> None:
    """Desfazer um código confirmado (F-045) também muda o que a praça soma."""
    client = _client(tmp_path)
    praca = _praca_na_v1(client)
    versao = _codificar_a_segunda_folha(client, praca)
    montado = _build_calc(client, praca["round_id"], base_version=versao, key="calc-antes")
    assert montado.status_code == 200, montado.text

    desfeito = client.post(
        f"/v1/valuation-rounds/{praca['round_id']}/code-assignments/revocations",
        headers=_headers(key="revogacao-que-vence"),
        json={
            "base_version": montado.json()["version"],
            "plate_id": praca["plate_b"],
            "item_id": _ITEM,
            "code": _CODIGO_DA_RODADA,
            "note": "confirmei o código errado nesta folha",
        },
    )

    assert desfeito.status_code == 200, desfeito.text
    assert _estado(client, praca["round_id"])["stale"] is True


def test_acrescentar_folha_vence_o_boletim_antes_mesmo_da_extracao(tmp_path: Path) -> None:
    """A praça já não é a mesma que foi medida, ainda que a folha nova não tenha pacote.

    Esperar a extração para dizer isso seria deixar o orçamentista acrescentar uma folha e
    continuar lendo um total que ele mesmo acabou de tornar parcial.
    """
    client = _client(tmp_path)
    preparada = _round_with_decided_code(client, key="folha-nova")
    round_id = preparada["round_id"]
    montado = _build_calc(client, round_id, base_version=preparada["version"], key="calc-1folha")
    assert montado.status_code == 200, montado.text
    assert _estado(client, round_id)["stale"] is False

    acrescentada = _associate_plate(
        client, round_id, base_version=montado.json()["version"], key="folha-2"
    )

    assert acrescentada.status_code == 200, acrescentada.text
    assert _estado(client, round_id)["stale"] is True


# --------------------------------------------------------------------------------------
# o que NÃO vence
# --------------------------------------------------------------------------------------


def test_aprovar_e_exportar_nao_vencem_o_boletim(tmp_path: Path) -> None:
    """Nenhum dos dois toca as fontes; chamar isso de vencido seria ruído puro.

    Aprovar continua sendo a outra pergunta: `approval.stale` fala da assinatura, e
    `stale` fala da praça. Aqui a assinatura está em dia e o boletim também.
    """
    client = _client(tmp_path)
    preparada = _round_with_decided_code(client, key="aprovar-nao-vence")
    round_id = preparada["round_id"]
    montado = _build_calc(client, round_id, base_version=preparada["version"], key="calc-aprovar")
    assert montado.status_code == 200, montado.text

    aprovado = client.post(
        f"/v1/valuation-rounds/{round_id}/approve",
        headers=_headers(key="aprovacao-nao-vence"),
        json={"base_version": montado.json()["version"]},
    )

    assert aprovado.status_code == 200, aprovado.text
    corpo = aprovado.json()
    assert corpo["stale"] is False
    assert corpo["approval"]["approved"] is True
    assert corpo["approval"]["stale"] is False
    assert _estado(client, round_id)["stale"] is False


def test_o_boletim_montado_antes_desta_feature_nao_e_declarado_vencido(
    tmp_path: Path,
) -> None:
    """Sem o carimbo do passado nada pode ser afirmado — e nada é inventado no lugar.

    A revisão gravada por uma versão anterior da API não tem `bulletin_sources_sha256`. A
    leitura mostra os dois digests (um deles ausente) e NÃO chama a rodada de vencida:
    afirmar "vencido" sem o fato que o sustenta é a mesma invenção que este bloco recusa.
    """
    client = _client(tmp_path)
    preparada = _round_with_decided_code(client, key="boletim-legado")
    round_id = preparada["round_id"]
    montado = _build_calc(client, round_id, base_version=preparada["version"], key="calc-legado")
    assert montado.status_code == 200, montado.text
    with _database(client).sessions() as session:
        cabeca = head_revision(session, round_id=round_id, tenant_id=_TENANT)
        assert cabeca is not None
        digests = dict(cabeca.artifact_digests_json or {})
        digests.pop(BULLETIN_SOURCES_DIGEST)
        cabeca.artifact_digests_json = digests
        session.commit()

    bulletin = _estado(client, round_id)

    assert bulletin["present"] is True
    assert bulletin["stale"] is False
    assert bulletin["sources_digest"] is None
    assert bulletin["current_sources_digest"] is not None
