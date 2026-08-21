"""Código de insumo/serviço no formato do catálogo público (SCO).

Amostra de referência: `AD04050050(/)` — duas letras de família, oito dígitos fatiados
em 2/2/4 (`AD 04 05 0050`) e uma variante entre parênteses (`/` para o item base, letra
maiúscula para as variantes `(A)`, `(B)`). Essa é a forma **canônica**: a única que este
contexto armazena, valida (`SCO_CODE_PATTERN`) e compara.

O catálogo publicado pela CGM-Rio, porém, escreve o mesmo código com separadores
(`AD 04.05.0050 (/)`). Essa forma é aceita apenas na **fronteira de leitura**, por
`canonical_sco_code`, que devolve o código canônico; nada além do leitor de planilha
conhece a forma publicada.

A classificação do item aparece em três níveis, e o catálogo publicado pode escrevê-los
como texto com nome junto do código, em colunas próprias:

1. **Família** — duas letras e o nome (`AD Pavimentação`), na coluna mais à esquerda.
2. **Nível intermediário** — família e dois dígitos (`AD 04 Serviços de pavimentação`).
3. **Subgrupo** — família e quatro dígitos, escrito com separadores (`AD 04.05 Piso`)
   ou colado (`AD0410Meio-fio`), no mesmo formato do `subgroup_row_code` do item.

Os três parsers abaixo leem esses níveis; nenhum deles decide hierarquia sozinho, quem
compara prefixo e ordem é o leitor do catálogo.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from croquito_valuation.errors import ValuationValidationError

SCO_CODE_PATTERN: Final = r"^[A-Z]{2}\d{8}\((?:/|[A-Z])\)$"
CONTRACT_CODE_PATTERN: Final = r"^[A-Z]{2}\d{8}(?:\((?:/|[A-Z])\))?$"
"""Superset estrutural do código SCO: o código completo ou a forma nua sem variante.

A forma nua (`IE00040849`: duas letras e oito dígitos, sem `(...)`) existe para item
contratado fora da tabela SCO — o catálogo publicado não o precifica, mas o contrato real
o mede. Este padrão só garante a estrutura; ele não decide sozinho quais códigos nus uma
importação aceita. Essa decisão é do `WorkbookTemplate` (`extra_code_patterns`): o padrão
declarado ali precisa, além de casar o texto, ter a forma deste superset — quem revalida
isso é o leitor do consolidado (`workbook_reader.py`, chamando `is_contract_code`), não o
modelo.
"""
SCO_PUBLISHED_CODE_PATTERN: Final = r"^([A-Z]{2})\s*(\d{2})\.(\d{2})\.(\d{4})\s*\((/|[A-Z])\)$"
"""Forma com separadores em que o catálogo publicado escreve o código do item.

`AD 04.05.0050 (/)` é o mesmo item que `AD04050050(/)`; os espaços depois da família e
antes do parêntese são opcionais. Este padrão existe só para a leitura de planilha
canonizar o que lê — ele nunca substitui `SCO_CODE_PATTERN` no armazenamento.
"""
SCO_FAMILY_ROW_PATTERN: Final = r"^[A-Z]{2}$"
SCO_SUBGROUP_ROW_PATTERN: Final = r"^[A-Z]{2}\d{4}$"
SCO_FAMILY_HEADER_PATTERN: Final = r"^([A-Z]{2})\s+(\S.*)$"
SCO_INTERMEDIATE_HEADER_PATTERN: Final = r"^([A-Z]{2})\s*(\d{2})\s+(\S.*)$"
SCO_SUBGROUP_HEADER_PATTERN: Final = r"^([A-Z]{2})\s*(\d{2})[.\s]*(\d{2})\s*([^\d\s.].*)$"

_SCO_CODE_RE: Final = re.compile(SCO_CODE_PATTERN)
_SCO_PUBLISHED_CODE_RE: Final = re.compile(SCO_PUBLISHED_CODE_PATTERN)
_CONTRACT_CODE_RE: Final = re.compile(CONTRACT_CODE_PATTERN)
_SCO_FAMILY_ROW_RE: Final = re.compile(SCO_FAMILY_ROW_PATTERN)
_SCO_SUBGROUP_ROW_RE: Final = re.compile(SCO_SUBGROUP_ROW_PATTERN)
_SCO_FAMILY_HEADER_RE: Final = re.compile(SCO_FAMILY_HEADER_PATTERN)
_SCO_INTERMEDIATE_HEADER_RE: Final = re.compile(SCO_INTERMEDIATE_HEADER_PATTERN)
_SCO_SUBGROUP_HEADER_RE: Final = re.compile(SCO_SUBGROUP_HEADER_PATTERN)


@dataclass(frozen=True, slots=True)
class ScoCodeParts:
    """Partes de um código SCO já validado."""

    family: str
    subgroup: str
    group: str
    item: str
    variant: str

    @property
    def code(self) -> str:
        """Reconstrói o código original a partir das partes."""
        return f"{self.family}{self.subgroup}{self.group}{self.item}({self.variant})"

    @property
    def subgroup_row_code(self) -> str:
        """Código do cabeçalho de subgrupo da planilha de preços (ex.: `AD0405`)."""
        return f"{self.family}{self.subgroup}{self.group}"


def parse_sco_code(code: str) -> ScoCodeParts:
    """Valida e fatia um código SCO; código fora do formato falha alto."""
    if not _SCO_CODE_RE.fullmatch(code):
        raise ValuationValidationError(
            "SCO_CODE_UNPARSEABLE",
            "código fora do formato SCO (esperado XX00000000(/) ou XX00000000(A))",
            {"code": code},
        )
    digits = code[2:10]
    return ScoCodeParts(
        family=code[:2],
        subgroup=digits[:2],
        group=digits[2:4],
        item=digits[4:],
        variant=code[11],
    )


def is_sco_code(value: str) -> bool:
    """`True` quando o texto é um código SCO completo."""
    return _SCO_CODE_RE.fullmatch(value) is not None


def canonical_sco_code(text: str) -> str | None:
    """Código canônico do item quando `text` é um código SCO; `None` quando não é.

    Aceita as duas formas em que o item aparece — a canônica (`AD04050050(/)`) e a
    publicada com separadores (`AD 04.05.0050 (/)`) — e devolve sempre a canônica, que é
    a única armazenável. Não levanta exceção: é o teste que o leitor de planilha usa para
    decidir se a linha é um item antes de tentar lê-la como cabeçalho.
    """
    if _SCO_CODE_RE.fullmatch(text):
        return text
    match = _SCO_PUBLISHED_CODE_RE.fullmatch(text)
    if match is None:
        return None
    family, subgroup, group, item, variant = match.groups()
    return f"{family}{subgroup}{group}{item}({variant})"


def is_contract_code(value: str) -> bool:
    """`True` quando o texto tem a estrutura de um código contratual: SCO completo ou nu.

    Nu é a forma sem variante (`IE00040849`) de um item contratado fora da tabela SCO.
    Este helper só confere estrutura; aceitar um código nu específico numa importação é
    decisão do template (`WorkbookTemplate.matches_extra_code`), não deste módulo.
    """
    return _CONTRACT_CODE_RE.fullmatch(value) is not None


def is_family_row_code(value: str) -> bool:
    """`True` quando o texto é o código de um cabeçalho de família (ex.: `AD`)."""
    return _SCO_FAMILY_ROW_RE.fullmatch(value) is not None


def is_subgroup_row_code(value: str) -> bool:
    """`True` quando o texto é o código de um cabeçalho de subgrupo (ex.: `AD0405`)."""
    return _SCO_SUBGROUP_ROW_RE.fullmatch(value) is not None


def parse_family_header(text: str) -> tuple[str, str] | None:
    """Lê `AD Pavimentação` e devolve `("AD", "Pavimentação")`; `None` se não for família.

    O espaço obrigatório logo depois das duas letras é o que separa um cabeçalho de
    família de um título de planilha como `PCRJ  SCO-Sistema de Custos`.
    """
    match = _SCO_FAMILY_HEADER_RE.fullmatch(text)
    if match is None:
        return None
    return match.group(1), match.group(2).strip()


def parse_intermediate_header(text: str) -> tuple[str, str] | None:
    """Lê `AD 04 Serviços de pavimentação` e devolve `("AD04", "Serviços de pavimentação")`.

    Nível entre a família e o subgrupo: exatamente dois dígitos seguidos de espaço. Um
    subgrupo (`AD 04.05 Piso`) ou um código completo não casam e devolvem `None`.
    """
    match = _SCO_INTERMEDIATE_HEADER_RE.fullmatch(text)
    if match is None:
        return None
    return f"{match.group(1)}{match.group(2)}", match.group(3).strip()


def parse_subgroup_header(text: str) -> tuple[str, str] | None:
    """Lê o cabeçalho de subgrupo e devolve `("AD0405", nome)`; `None` se não for subgrupo.

    Aceita as duas formas publicadas — com separadores (`AD 04.05 Piso intertravado`) e
    colada (`AD0410Meio-fio`). O nome precisa começar por caractere que não seja dígito,
    espaço nem ponto: é isso que impede um código de item de ser lido como subgrupo tanto
    na forma canônica (`AD04050050(/)`) quanto na publicada (`AD 04.05.0050 (/)`), cujo
    resto (`.0050 (/)`) seria lido como nome se o ponto fosse aceito. O código devolvido
    tem o mesmo formato de `ScoCodeParts.subgroup_row_code`.
    """
    match = _SCO_SUBGROUP_HEADER_RE.fullmatch(text)
    if match is None:
        return None
    return f"{match.group(1)}{match.group(2)}{match.group(3)}", match.group(4).strip()
