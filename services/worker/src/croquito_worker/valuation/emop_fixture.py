"""Catálogo EMOP sintético: os bytes .DBF que o importador offline sabe ler.

O catálogo digital EMOP real é pago (assinatura GRE) e o arquivo real não existe neste
repositório. Os bytes gerados aqui não pretendem reproduzir o layout real — que é DADO,
fechado em `EmopCatalogLayout` a partir de um arquivo de cliente — e só exercitam o leitor
.DBF mínimo de `croquito_valuation.emop`.

Ele mora no worker, ao lado de `plate.py` e `synthetic.py`, pela mesma razão que aqueles:
é a fixture de produto que a DEMO determinística consome (`estimate-demo` precisa de uma
segunda fonte de preço, e a cascata do orçamento-base não seria demonstrável sem uma). Os
testes usam esta mesma fonte (`tests/valuation/emop_fixture.py` reexporta daqui e
acrescenta o gabarito e os adulteradores de bytes), de modo que os bytes gravados na demo e
os bytes gravados no teste não podem divergir.
"""

from __future__ import annotations

import struct
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Final

from croquito_valuation.emop import DEFAULT_EMOP_ENCODING, EmopCatalogLayout

EMOP_CODE_PATTERN: Final = r"^EMOP\.[A-Z]{2}\.\d{3}$"
"""Padrão sintético do exercício: um código EMOP real é dado do layout do cliente, não
constante de código — este padrão só existe para a fixture ter algo consistente a casar."""

EMOP_SOURCE_LABEL: Final = "CATALOGO EMOP SINTETICO (fixture)"
EMOP_REFERENCE_MONTH: Final = "2026-06"

FIELD_CODE: Final = "CODIGO"
FIELD_DESCRIPTION: Final = "DESCRICAO"
FIELD_UNIT: Final = "UNIDADE"
FIELD_PRICE: Final = "PRECO"
FIELD_FAMILY_CODE: Final = "FAMCOD"
FIELD_FAMILY_NAME: Final = "FAMNOME"
FIELD_SUBGROUP_CODE: Final = "SUBCOD"
FIELD_SUBGROUP_NAME: Final = "SUBNOME"

_CODE_LENGTH: Final = 15
_DESCRIPTION_LENGTH: Final = 60
_UNIT_LENGTH: Final = 10
_PRICE_LENGTH: Final = 12
_PRICE_DECIMALS: Final = 2
_FAMILY_CODE_LENGTH: Final = 5
_FAMILY_NAME_LENGTH: Final = 40
_SUBGROUP_CODE_LENGTH: Final = 8
_SUBGROUP_NAME_LENGTH: Final = 40

EMOP_FIELD_SPECS: Final[tuple[tuple[str, str, int, int], ...]] = (
    (FIELD_CODE, "C", _CODE_LENGTH, 0),
    (FIELD_DESCRIPTION, "C", _DESCRIPTION_LENGTH, 0),
    (FIELD_UNIT, "C", _UNIT_LENGTH, 0),
    (FIELD_PRICE, "N", _PRICE_LENGTH, _PRICE_DECIMALS),
    (FIELD_FAMILY_CODE, "C", _FAMILY_CODE_LENGTH, 0),
    (FIELD_FAMILY_NAME, "C", _FAMILY_NAME_LENGTH, 0),
    (FIELD_SUBGROUP_CODE, "C", _SUBGROUP_CODE_LENGTH, 0),
    (FIELD_SUBGROUP_NAME, "C", _SUBGROUP_NAME_LENGTH, 0),
)
"""(nome do campo, tipo DBF, tamanho em bytes, casas decimais) — a ordem gravada no
registro. `read_emop_catalog` não depende de ordem (lê por nome), mas o escritor precisa de
uma ordem fixa para montar os bytes, e os testes de adulteração precisam dela para achar o
offset de um campo dentro do registro."""


@dataclass(frozen=True, slots=True)
class EmopFixtureRow:
    """Uma linha sintética do catálogo EMOP: o que é gravado no .DBF e o que se espera dela.

    `deleted=True` é a linha que exercita a flag de deleção (`*`): pulada e contada,
    nunca importada.
    """

    code: str
    description: str
    unit: str
    price: Decimal
    family_code: str
    family_name: str
    subgroup_code: str
    subgroup_name: str
    deleted: bool = False


EMOP_FIXTURE_ROWS: Final[tuple[EmopFixtureRow, ...]] = (
    EmopFixtureRow(
        code="EMOP.AD.001",
        description="PAVIMENTAÇÃO SINTÉTICA EMOP TIPO 1",
        unit="M2",
        price=Decimal("123.45"),
        family_code="AD",
        family_name="PAVIMENTACAO SINTETICA EMOP",
        subgroup_code="AD01",
        subgroup_name="PISO EMOP SINTETICO",
    ),
    EmopFixtureRow(
        code="EMOP.AD.002",
        description="PAVIMENTACAO SINTETICA EMOP TIPO 2",
        unit="M2",
        price=Decimal("150.00"),
        family_code="AD",
        family_name="PAVIMENTACAO SINTETICA EMOP",
        subgroup_code="AD01",
        subgroup_name="PISO EMOP SINTETICO",
    ),
    EmopFixtureRow(
        code="EMOP.CE.001",
        description="MOBILIARIO SINTETICO EMOP",
        unit="UN",
        price=Decimal("980.00"),
        family_code="CE",
        family_name="SERVICOS PRELIMINARES EMOP",
        subgroup_code="CE02",
        subgroup_name="MOBILIARIO EMOP SINTETICO",
    ),
    EmopFixtureRow(
        code="EMOP.AD.999",
        description="ITEM DESCONTINUADO EMOP",
        unit="M2",
        price=Decimal("1.00"),
        family_code="AD",
        family_name="PAVIMENTACAO SINTETICA EMOP",
        subgroup_code="AD01",
        subgroup_name="PISO EMOP SINTETICO",
        deleted=True,
    ),
)
"""Três linhas ativas em duas famílias/subgrupos e uma linha deletada de propósito."""


def emop_fixture_layout(*, encoding: str = DEFAULT_EMOP_ENCODING) -> EmopCatalogLayout:
    """Layout da fixture: os mesmos nomes de campo que `write_emop_dbf` grava."""
    return EmopCatalogLayout(
        source_label=EMOP_SOURCE_LABEL,
        reference_month=EMOP_REFERENCE_MONTH,
        code_field=FIELD_CODE,
        description_field=FIELD_DESCRIPTION,
        unit_field=FIELD_UNIT,
        price_field=FIELD_PRICE,
        family_code_field=FIELD_FAMILY_CODE,
        family_name_field=FIELD_FAMILY_NAME,
        subgroup_code_field=FIELD_SUBGROUP_CODE,
        subgroup_name_field=FIELD_SUBGROUP_NAME,
        code_pattern=EMOP_CODE_PATTERN,
        encoding=encoding,
    )


def _field_descriptor(name: str, field_type: str, length: int, decimals: int) -> bytes:
    """32 bytes do descritor de campo dBASE III: nome, tipo, tamanho, decimais e reservado."""
    name_bytes = name.encode("ascii").ljust(11, b"\x00")
    return (
        name_bytes
        + field_type.encode("ascii")
        + b"\x00\x00\x00\x00"  # endereço em memória: não usado no arquivo
        + bytes([length])
        + bytes([decimals])
        + b"\x00" * 14
    )


def _record_bytes(row: EmopFixtureRow, *, encoding: str) -> bytes:
    """Um registro: flag de deleção + cada campo largado/right-padded ao tamanho fixo."""
    delete_flag = b"*" if row.deleted else b" "
    price_text = format(row.price, f".{_PRICE_DECIMALS}f").rjust(_PRICE_LENGTH)
    fields = (
        row.code.ljust(_CODE_LENGTH),
        row.description.ljust(_DESCRIPTION_LENGTH),
        row.unit.ljust(_UNIT_LENGTH),
        price_text,
        row.family_code.ljust(_FAMILY_CODE_LENGTH),
        row.family_name.ljust(_FAMILY_NAME_LENGTH),
        row.subgroup_code.ljust(_SUBGROUP_CODE_LENGTH),
        row.subgroup_name.ljust(_SUBGROUP_NAME_LENGTH),
    )
    body = b"".join(text.encode(encoding) for text in fields)
    return delete_flag + body


def write_emop_dbf(
    path: Path,
    rows: Sequence[EmopFixtureRow] = EMOP_FIXTURE_ROWS,
    *,
    encoding: str = DEFAULT_EMOP_ENCODING,
    version: int = 0x03,
    include_eof_marker: bool = True,
) -> Path:
    """Grava os bytes .DBF (dBASE III) da fixture; a MESMA `rows` também gera o gabarito.

    Os bytes são determinísticos (a data de atualização do cabeçalho é constante), então o
    digest do arquivo é sempre o mesmo e a demo pode fixá-lo. `version` e
    `include_eof_marker` existem só para os testes de recusa estrutural — a fixture "feliz"
    nunca precisa deles fora do default.
    """
    field_descriptors = b"".join(
        _field_descriptor(name, field_type, length, decimals)
        for name, field_type, length, decimals in EMOP_FIELD_SPECS
    )
    header_size = 32 + len(field_descriptors) + 1
    record_size = 1 + sum(length for _, _, length, _ in EMOP_FIELD_SPECS)
    records = b"".join(_record_bytes(row, encoding=encoding) for row in rows)

    header = bytearray(32)
    header[0] = version
    header[1:4] = bytes((26, 6, 1))  # data de atualização (AAMMDD), arbitrária
    header[4:8] = struct.pack("<I", len(rows))
    header[8:10] = struct.pack("<H", header_size)
    header[10:12] = struct.pack("<H", record_size)

    payload = bytes(header) + field_descriptors + bytes([0x0D]) + records
    if include_eof_marker:
        payload += bytes([0x1A])

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path
