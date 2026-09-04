"""F-051 T4: as duas comparações de rótulo, e a diferença de força entre elas (ADR-0063).

A tabela abaixo é a decisão do Unknown 1 do contrato da feature, escrita como oráculo: as
formas são as REAIS — o hint do balão como o provider o entrega na issue #139 ("A", "B",
"C", "D", "arquibancada 1") contra o rótulo como uma pessoa o escreve no ato de declaração
("B", "grade B", "B — fecho da área de lazer", registradas no ADR-0063 e no Design Approval
Package aprovado).

O que estes testes protegem: o casamento é EXATO em dois sentidos declarados (igualdade
normalizada ou palavra inteira) e nunca por parecença; agrupar é mais estrito que casar, de
propósito; e a assimetria hint→rótulo é intencional, não descuido.
"""

from __future__ import annotations

import pytest

from croquito_worker.element_identity_matching import (
    hint_matches_label,
    label_group_key,
    normalize_element_label,
)

#: (hint da leitura, rótulo do elemento declarado, casa?) — as formas do job de referência.
FORMAS_REAIS: list[tuple[str, str, bool]] = [
    # Igualdade, com e sem ruído de caixa e espaço.
    ("B", "B", True),
    ("b", "B", True),
    ("  B  ", "B", True),
    ("arquibancada 1", "arquibancada 1", True),
    # O hint como palavra inteira do rótulo descritivo: o caso que motivou a decisão.
    ("B", "grade B", True),
    ("B", "alambrado B", True),
    ("B", "B — fecho da área de lazer", True),
    ("B", "grade B / lateral", True),
    ("B", "B: arquibancada", True),
    ("D", "grade D", True),
    # O que NÃO casa, e é aqui que a decisão ganha valor.
    ("E", "B", False),
    ("E", "grade B", False),
    ("B", "fecho", False),
    ("B", "grade", False),
    ("B", "alambrado", False),
    ("arquibancada 1", "arquibancada 2", False),
    ("C", "arquibancada 1", False),
    # Assimetria declarada: o hint procura o rótulo, nunca o contrário.
    ("grade B", "B", False),
    # Substring não é palavra: "B" não está dentro de "BC" nem de "SUBIDA".
    ("B", "BC", False),
    ("B", "subida", False),
]


@pytest.mark.parametrize(("hint", "label", "casa"), FORMAS_REAIS)
def test_a_tabela_das_formas_reais_do_casamento(hint: str, label: str, casa: bool) -> None:
    assert hint_matches_label(hint, label) is casa


def test_agrupar_e_mais_estrito_que_casar_e_a_diferenca_e_o_ponto() -> None:
    """`"grade B"` casa com o hint `"B"`, e ainda assim NÃO agrupa com o rótulo `"B"`.

    Agrupar é afirmar "estas propostas são a mesma coisa"; casar é oferecer um referente
    possível para quem revisa escolher. Fundir as duas forças numa só criaria elemento que
    ninguém declarou, ou esconderia o referente de quem escreveu o nome por extenso.
    """
    assert hint_matches_label("B", "grade B") is True
    assert label_group_key("grade B") != label_group_key("B")


def test_agrupamento_ignora_caixa_e_espaco_e_nada_mais() -> None:
    assert label_group_key("Grade B") == label_group_key("  grade b ")
    assert label_group_key("grade B") != label_group_key("grade C")
    # Acento é diferença de palavra e continua sendo: normalizar caixa não é adivinhar.
    assert label_group_key("área") != label_group_key("area")


def test_hint_vazio_ou_so_de_espaco_nunca_casa() -> None:
    assert hint_matches_label("", "B") is False
    assert hint_matches_label("   ", "B") is False
    assert normalize_element_label("   ") == ""
