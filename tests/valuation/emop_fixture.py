"""Gabarito e adulteradores de bytes da fixture EMOP; os bytes vêm do worker.

A MESMA fonte escreve os bytes .DBF e o gabarito: `EMOP_FIXTURE_ROWS`/`write_emop_dbf`
moram em `croquito_worker.valuation.emop_fixture` — porque a demo determinística
(`estimate-demo`) também precisa deles — e aqui ficam as duas coisas que só o teste usa: o
gabarito esperado (`expected_emop_entries`, derivado das mesmas linhas, então nenhum número
aparece duas vezes) e os adulteradores que quebram o arquivo depois de gravado, para
exercitar as recusas estruturais do leitor.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from croquito_valuation.emop import DEFAULT_EMOP_ENCODING
from croquito_valuation.models import PriceCatalogEntry, PriceOrigin
from croquito_worker.valuation.emop_fixture import (
    EMOP_CODE_PATTERN,
    EMOP_FIELD_SPECS,
    EMOP_FIXTURE_ROWS,
    EMOP_REFERENCE_MONTH,
    EMOP_SOURCE_LABEL,
    FIELD_CODE,
    FIELD_DESCRIPTION,
    FIELD_FAMILY_CODE,
    FIELD_FAMILY_NAME,
    FIELD_PRICE,
    FIELD_SUBGROUP_CODE,
    FIELD_SUBGROUP_NAME,
    FIELD_UNIT,
    EmopFixtureRow,
    emop_fixture_layout,
    write_emop_dbf,
)

__all__ = [
    "EMOP_CODE_PATTERN",
    "EMOP_FIELD_SPECS",
    "EMOP_FIXTURE_ROWS",
    "EMOP_REFERENCE_MONTH",
    "EMOP_SOURCE_LABEL",
    "FIELD_CODE",
    "FIELD_DESCRIPTION",
    "FIELD_FAMILY_CODE",
    "FIELD_FAMILY_NAME",
    "FIELD_PRICE",
    "FIELD_SUBGROUP_CODE",
    "FIELD_SUBGROUP_NAME",
    "FIELD_UNIT",
    "EmopFixtureRow",
    "corrupt_dbf_version",
    "corrupt_field_bytes",
    "emop_fixture_layout",
    "expected_emop_entries",
    "truncate_dbf_file",
    "write_emop_dbf",
]


def expected_emop_entries(
    rows: Sequence[EmopFixtureRow] = EMOP_FIXTURE_ROWS,
) -> list[PriceCatalogEntry]:
    """Gabarito das entradas que `read_emop_catalog` deve devolver: deletadas ficam fora."""
    return [
        PriceCatalogEntry(
            code=row.code,
            description=row.description,
            unit=row.unit,
            unit_price=row.price,
            family_code=row.family_code,
            family_name=row.family_name,
            subgroup_code=row.subgroup_code,
            subgroup_name=row.subgroup_name,
            origin=PriceOrigin.EMOP,
        )
        for row in rows
        if not row.deleted
    ]


def corrupt_dbf_version(path: Path, *, version: int = 0x04) -> None:
    """Sobrescreve o byte de versão do .DBF já gravado (default: dBASE IV, fora do lido)."""
    data = bytearray(path.read_bytes())
    data[0] = version
    path.write_bytes(bytes(data))


def truncate_dbf_file(path: Path, *, keep_bytes: int) -> None:
    """Corta o .DBF já gravado nos primeiros `keep_bytes`, simulando arquivo incompleto."""
    data = path.read_bytes()[:keep_bytes]
    path.write_bytes(data)


def _dbf_header_size() -> int:
    return 32 + len(EMOP_FIELD_SPECS) * 32 + 1


def _dbf_record_size() -> int:
    return 1 + sum(length for _, _, length, _ in EMOP_FIELD_SPECS)


def _dbf_field_offset(field_name: str) -> tuple[int, int]:
    """Offset do campo dentro do registro (após a flag de deleção) e o tamanho dele."""
    offset = 1
    for name, _field_type, length, _decimals in EMOP_FIELD_SPECS:
        if name == field_name:
            return offset, length
        offset += length
    raise AssertionError(f"campo desconhecido na fixture EMOP: {field_name}")


def corrupt_field_bytes(
    path: Path,
    *,
    row_index: int,
    field_name: str,
    raw_text: str,
    encoding: str = DEFAULT_EMOP_ENCODING,
) -> None:
    """Sobrescreve o texto bruto de um campo de um registro já gravado — bytes exatos,
    sem passar pelas conversões do domínio. É o que simula um .DBF adulterado depois de
    gerado: o mesmo arquivo, um campo alterado por fora do leitor. `row_index` é 0-based,
    na ordem de `rows` usada em `write_emop_dbf`."""
    data = bytearray(path.read_bytes())
    header_size = _dbf_header_size()
    record_size = _dbf_record_size()
    field_offset, field_length = _dbf_field_offset(field_name)
    record_start = header_size + row_index * record_size
    start = record_start + field_offset
    encoded = raw_text.encode(encoding)[:field_length].ljust(field_length, b" ")
    data[start : start + field_length] = encoded
    path.write_bytes(bytes(data))
