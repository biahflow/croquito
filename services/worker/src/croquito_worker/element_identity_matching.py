"""Como um rótulo de elemento se compara com outro — duas forças, ambas declaradas.

Unknown 1 do contrato da F-051, resolvido aqui (T4) contra o dado real, e não contra o
gosto de quem escreve o código. Os dois lados da comparação vêm de fontes diferentes:

- **o hint da leitura** (`DimensionReading.target_entity_label`) chega do provider como a
  letra do balão: `"A"`, `"B"`, `"C"`, `"D"`, `"arquibancada 1"` (issue #139, primeira
  revisão completa de croqui real);
- **o rótulo do elemento** é escrito por uma pessoa no ato de declaração: `"B"`,
  `"grade B"`, `"B — fecho da área de lazer"` (ADR-0063 e o Design Approval Package
  aprovado da feature usam essas formas).

Daí duas funções de força DELIBERADAMENTE diferente, e é a diferença que precisa ficar
escrita — não a semelhança:

- `label_group_key` (agrupar sugestões, F-051 T3) compara por **igualdade normalizada**.
  Agrupar é dizer "estas propostas são a MESMA coisa": só a mesma palavra agrupa, e
  `"grade B"` nunca entra no balde de `"B"`. Sem fusão transitiva, sem vizinhança.
- `hint_matches_label` (casar a cota-balão com o elemento, F-051 T4) aceita também o hint
  como **token isolado** do rótulo, porque é assim que o dado real chega: o modelo lê a
  letra do balão, a pessoa escreve o nome do elemento com a letra dentro dele.

O que NUNCA entra aqui: distância de edição, similaridade, prefixo, "contém" de substring.
Casamento difuso silencioso é exatamente o que o ADR-0063 recusa — a candidata é
observação, mas uma observação errada custa o tempo de quem revisa, e um critério que
ninguém consegue prever de cabeça custa a confiança inteira. Tudo aqui é determinístico e
cabe numa frase: normaliza caixa e espaço; casa igual, ou casa como palavra inteira.
"""

from __future__ import annotations

from typing import Final

LABEL_TOKEN_SEPARATORS: Final = ("—", "-", "·", ":", "/")
"""Separadores que quebram um rótulo em palavras, além do espaço.

Vêm da forma como o rótulo descritivo é escrito na folha e na tela: `"B — fecho da área de
lazer"`, `"grade B / lateral"`, `"B: arquibancada"`. O travessão e o hífen estão os dois na
lista porque teclado e editor produzem os dois pelo mesmo motivo.

O preço declarado: `"B-1"` também se parte, então o hint `"B"` casa com o elemento
`"B-1"`. Preferimos oferecer a candidata a mais — ela ranqueia, nunca confirma, e quem
revisa vê a folha — do que esconder o referente de quem escreveu o nome com travessão.
"""


def normalize_element_label(value: str) -> str:
    """A forma comparável de um rótulo: sem espaço nas pontas, sem distinção de caixa.

    `casefold` e não `lower`: o rótulo é texto de croqui em português, e `casefold` é a
    normalização de caixa que trata corretamente os casos que `lower` deixa passar.
    Acento NÃO é removido — `"área"` e `"area"` são palavras diferentes, e apagar a
    diferença seria começar a adivinhar o que a pessoa quis escrever.
    """
    return value.strip().casefold()


def label_group_key(label: str) -> str:
    """A chave de AGRUPAMENTO de rótulos (F-051 T3): igualdade normalizada, e só.

    Duas propostas entram no mesmo grupo quando o modelo deu a elas o mesmo nome — a menos
    de caixa e espaço nas pontas. `"Grade B"` e `"grade b"` são o mesmo nome escrito com a
    mão trocada; `"grade B"` e `"B"` não são, e agrupar os dois inventaria um elemento que
    ninguém afirmou.
    """
    return normalize_element_label(label)


def _label_tokens(normalized_label: str) -> frozenset[str]:
    """As palavras inteiras de um rótulo já normalizado."""
    text = normalized_label
    for separator in LABEL_TOKEN_SEPARATORS:
        text = text.replace(separator, " ")
    return frozenset(token for token in text.split() if token)


def hint_matches_label(hint: str, label: str) -> bool:
    """O hint da cota-balão aponta para este elemento? (F-051 T4, ADR-0063 decisão 3.)

    Verdadeiro em dois casos, ambos exatos:

    1. **Igualdade normalizada** — `"B"` casa com `"B"`, com `" b "` e com `"b"`.
    2. **Token isolado** — o hint é uma palavra inteira do rótulo: `"B"` casa com
       `"grade B"` e com `"B — fecho da área de lazer"`.

    Falso em tudo o mais: `"E"` não casa com nada que não seja um `"E"`, e `"B"` não casa
    com `"fecho"` nem com `"grade"`. Nunca há vizinhança, parecença ou prefixo.

    A relação é ASSIMÉTRICA de propósito: o hint procura pelo rótulo, não o contrário. O
    hint é a letra que o técnico escreveu dentro do balão; o rótulo é o nome do elemento,
    que pode carregar a descrição inteira. `"grade B"` como hint não casa com o elemento
    `"B"` — quem escreve a descrição toda no balão não está usando a convenção do balão.

    Vários elementos podem casar com o mesmo hint (`"grade B"` e `"alambrado B"` contra
    `"B"`). Isso é resultado legítimo, não empate a desfazer: cada um vira candidata, e
    quem revisa escolhe olhando a folha. Nenhum critério secreto elege um vencedor.
    """
    normalized_hint = normalize_element_label(hint)
    if not normalized_hint:
        return False
    normalized_label = normalize_element_label(label)
    if normalized_hint == normalized_label:
        return True
    return normalized_hint in _label_tokens(normalized_label)
