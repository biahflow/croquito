"""Importador offline do catálogo EMOP: leitor .DBF mínimo + catálogo canônico.

O catálogo digital EMOP (Empresa Municipal de Obras e projetos) é uma assinatura GRE
paga, publicada em .DBF (dBASE III). O arquivo real não existe neste repositório — tudo
aqui é sintético, e o layout real (nomes de campo, encoding, padrão de código) fecha como
DADO depois, em `EmopCatalogLayout`, nunca como constante de código.

Regra da orçamentista (M8, `docs/architecture/VALUATION_CONTEXT.md`): em obra LICITADA o
contrato manda — preço nunca vem da EMOP. Este módulo só importa o catálogo com
`origin=PriceOrigin.EMOP` (`models.py`); é o guardrail em `calc.py::build_worksite_bulletin`
e `workbook_writer.py::_validate_against_catalog` (`BULLETIN_PRICE_ORIGIN_FORBIDDEN`) quem
impede esse catálogo de entrar na cadeia da medição. A cadeia SCO → EMOP → composição só
vale PRÉ-licitação (orçamento-base), fase futura e fora do escopo deste módulo.

## O leitor .DBF

Implementação mínima, stdlib puro, só do que o catálogo precisa: dBASE III sem memo
(byte de versão `0x03`), campos de texto (`C`) e numéricos (`N`) — qualquer outro tipo ou
versão recusa fechado (`EMOP_DBF_UNSUPPORTED`). Campo `N` é lido como TEXTO e convertido
direto para `Decimal` na hora de montar a entrada: o dBASE nunca guarda ponto flutuante
binário, então não há conversão por `float` no caminho do preço. Registro com a flag de
deleção (`*`) é pulado e contado — nunca vira entrada do catálogo. O terminador de EOF
(`0x1A`) é tolerado: o leitor para de ler pelo `record_count` do cabeçalho, nunca pelo
byte final do arquivo.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Final, NoReturn
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import Field, ValidationError, model_validator

from croquito_valuation.catalog import file_sha256
from croquito_valuation.errors import ValuationValidationError
from croquito_valuation.models import (
    REFERENCE_MONTH_PATTERN,
    PriceCatalog,
    PriceCatalogEntry,
    PriceOrigin,
    ValuationContractModel,
)

DEFAULT_EMOP_ENCODING: Final = "cp850"
"""Codepage padrão do layout: DOS Latin-1, o mais comum em exportação .DBF pt-BR. O
layout declara o encoding real (`EmopCatalogLayout.encoding`); este é só o default."""

_DBASE_III_VERSION: Final = 0x03
_FIXED_HEADER_SIZE: Final = 32
_FIELD_DESCRIPTOR_SIZE: Final = 32
_FIELD_NAME_SIZE: Final = 11
_HEADER_TERMINATOR: Final = 0x0D
_DELETED_FLAG: Final = 0x2A  # b"*"
_SUPPORTED_FIELD_TYPES: Final = frozenset({"C", "N"})

_EMOP_CATALOG_ID_NAMESPACE: Final = uuid5(
    NAMESPACE_URL, "https://croquito.local/valuation/catalog/emop"
)


def emop_catalog_id_for(source_sha256: str) -> UUID:
    """Id derivado do conteúdo do .DBF: reimportar o mesmo arquivo devolve o mesmo catálogo.

    Namespace próprio, distinto do `catalog_id_for` do catálogo SCO (`catalog.py`): as
    duas fontes nunca deveriam colidir de id mesmo que o SHA-256 dos bytes coincidisse
    por acaso, porque são catálogos de naturezas diferentes.
    """
    return uuid5(_EMOP_CATALOG_ID_NAMESPACE, source_sha256)


class EmopCatalogLayout(ValuationContractModel):
    """Layout do catálogo EMOP como DADO: nomes de campo do .DBF e regras de leitura.

    Espelha `WorkbookTemplate`/`CatalogLayout` (`template.py`): nenhuma posição ou nome
    de campo é constante do código. `code_pattern` é o padrão REAL do código EMOP —
    regex como dado, validada na construção com o mesmo cinto e suspensório de
    `WorkbookTemplate.validate_extra_code_patterns` (compila e não casa a string vazia).
    Toda linha lida ainda revalida contra o superset estrutural de
    `PriceCatalogEntry.validate_code_for_origin` (`NON_SCO_CODE_PATTERN`): um
    `code_pattern` frouxo demais aqui não basta para injetar um código fora da estrutura.
    """

    source_label: str = Field(min_length=1, max_length=200)
    reference_month: str = Field(pattern=REFERENCE_MONTH_PATTERN)
    code_field: str = Field(min_length=1, max_length=_FIELD_NAME_SIZE)
    description_field: str = Field(min_length=1, max_length=_FIELD_NAME_SIZE)
    unit_field: str = Field(min_length=1, max_length=_FIELD_NAME_SIZE)
    price_field: str = Field(min_length=1, max_length=_FIELD_NAME_SIZE)
    family_code_field: str = Field(min_length=1, max_length=_FIELD_NAME_SIZE)
    family_name_field: str = Field(min_length=1, max_length=_FIELD_NAME_SIZE)
    subgroup_code_field: str = Field(min_length=1, max_length=_FIELD_NAME_SIZE)
    subgroup_name_field: str = Field(min_length=1, max_length=_FIELD_NAME_SIZE)
    code_pattern: str = Field(min_length=1, max_length=200)
    encoding: str = Field(default=DEFAULT_EMOP_ENCODING, min_length=1, max_length=40)

    @model_validator(mode="after")
    def validate_code_pattern(self) -> EmopCatalogLayout:
        try:
            compiled = re.compile(self.code_pattern)
        except re.error as error:
            raise ValuationValidationError(
                "EMOP_LAYOUT_CODE_PATTERN_INVALID",
                "padrão de código do layout EMOP não compila como expressão regular",
                {"pattern": self.code_pattern, "reason": str(error)},
            ) from error
        if compiled.fullmatch("") is not None:
            raise ValuationValidationError(
                "EMOP_LAYOUT_CODE_PATTERN_INVALID",
                "padrão de código do layout EMOP casa a string vazia; frouxo demais para "
                "distinguir um código real",
                {"pattern": self.code_pattern},
            )
        return self

    @property
    def declared_fields(self) -> tuple[str, ...]:
        """Nomes de campo do .DBF que o layout precisa encontrar na tabela."""
        return (
            self.code_field,
            self.description_field,
            self.unit_field,
            self.price_field,
            self.family_code_field,
            self.family_name_field,
            self.subgroup_code_field,
            self.subgroup_name_field,
        )


@dataclass(frozen=True, slots=True)
class DbfField:
    """Um descritor de campo do .DBF já validado: nome, tipo e tamanho em bytes."""

    name: str
    field_type: str
    length: int


@dataclass(frozen=True, slots=True)
class DbfRecord:
    """Um registro do .DBF: valores por nome de campo (já decodificados e sem espaço nas
    pontas) e se ele carrega a flag de deleção."""

    values: dict[str, str]
    deleted: bool


@dataclass(frozen=True, slots=True)
class DbfTable:
    """Tabela .DBF lida: os campos declarados no cabeçalho e os registros, nesta ordem."""

    fields: tuple[DbfField, ...]
    records: tuple[DbfRecord, ...]


@dataclass(frozen=True, slots=True)
class EmopImportNotes:
    """O que a importação do .DBF observou sem recusar: só os registros deletados.

    Espelho minúsculo de `ContractImportNotes` (`workbook_reader.py`): nada aqui muda o
    catálogo devolvido, é o que o relatório do comando precisa para declarar a contagem.
    """

    deleted_count: int
    deleted_rows: tuple[int, ...]


def _dbf_unsupported(reason: str, **details: object) -> NoReturn:
    raise ValuationValidationError("EMOP_DBF_UNSUPPORTED", reason, details)


def _read_dbf_field_descriptors(data: bytes, header_size: int) -> tuple[DbfField, ...]:
    """Lê os descritores de campo entre o cabeçalho fixo e o terminador `0x0D`."""
    fields: list[DbfField] = []
    offset = _FIXED_HEADER_SIZE
    while True:
        if offset > header_size - 1:
            _dbf_unsupported(
                "cabeçalho sem terminador de descritores de campo antes do fim declarado",
                offset=offset,
                declared_header_size=header_size,
            )
        if offset + 1 > len(data):
            _dbf_unsupported("cabeçalho truncado: descritor de campo incompleto", offset=offset)
        if data[offset] == _HEADER_TERMINATOR:
            break
        if offset + _FIELD_DESCRIPTOR_SIZE > header_size - 1:
            _dbf_unsupported(
                "cabeçalho sem terminador de descritores de campo antes do fim declarado",
                offset=offset,
                declared_header_size=header_size,
            )
        if offset + _FIELD_DESCRIPTOR_SIZE > len(data):
            _dbf_unsupported("cabeçalho truncado: descritor de campo incompleto", offset=offset)
        descriptor = data[offset : offset + _FIELD_DESCRIPTOR_SIZE]
        raw_name = descriptor[0:_FIELD_NAME_SIZE]
        name = raw_name.split(b"\x00", 1)[0].decode("ascii", errors="replace").strip()
        field_type = chr(descriptor[11])
        length = descriptor[16]
        if not name:
            _dbf_unsupported("descritor de campo sem nome", offset=offset)
        if field_type not in _SUPPORTED_FIELD_TYPES:
            _dbf_unsupported(
                "tipo de campo fora de C/N; o leitor mínimo só lê texto e numérico",
                field=name,
                field_type=field_type,
            )
        if length <= 0:
            _dbf_unsupported("descritor de campo com tamanho inválido", field=name, length=length)
        fields.append(DbfField(name=name, field_type=field_type, length=length))
        offset += _FIELD_DESCRIPTOR_SIZE
    return tuple(fields)


def _read_dbf_table(path: Path, encoding: str) -> DbfTable:
    """Leitor mínimo de dBASE III: recusa fechado em qualquer estrutura fora do esperado."""
    data = path.read_bytes()
    if len(data) < _FIXED_HEADER_SIZE:
        _dbf_unsupported("arquivo truncado antes do fim do cabeçalho fixo", size=len(data))

    version = data[0]
    if version != _DBASE_III_VERSION:
        _dbf_unsupported(
            "versão do .DBF não suportada; só dBASE III sem memo (0x03) é lido",
            version=f"0x{version:02x}",
        )

    record_count = int.from_bytes(data[4:8], "little")
    header_size = int.from_bytes(data[8:10], "little")
    record_size = int.from_bytes(data[10:12], "little")
    if header_size < _FIXED_HEADER_SIZE + 1 or record_size < 1:
        _dbf_unsupported(
            "cabeçalho declara tamanhos inconsistentes",
            header_size=header_size,
            record_size=record_size,
        )
    if len(data) < header_size:
        _dbf_unsupported(
            "arquivo truncado antes do fim do cabeçalho declarado",
            declared=header_size,
            actual=len(data),
        )

    fields = _read_dbf_field_descriptors(data, header_size)
    declared_record_size = 1 + sum(field.length for field in fields)
    if declared_record_size != record_size:
        _dbf_unsupported(
            "tamanho de registro declarado no cabeçalho não confere com a soma dos campos",
            declared=record_size,
            computed=declared_record_size,
        )

    records: list[DbfRecord] = []
    offset = header_size
    for row_number in range(1, record_count + 1):
        if offset + record_size > len(data):
            _dbf_unsupported(
                "arquivo truncado no meio dos registros; menos registros do que o "
                "cabeçalho declara",
                row=row_number,
                declared_records=record_count,
            )
        record = data[offset : offset + record_size]
        deleted = record[0] == _DELETED_FLAG
        values: dict[str, str] = {}
        position = 1
        for field in fields:
            raw = record[position : position + field.length]
            try:
                text = raw.decode(encoding)
            except (LookupError, UnicodeDecodeError) as error:
                _dbf_unsupported(
                    "não foi possível decodificar campo com o encoding declarado no layout",
                    row=row_number,
                    field=field.name,
                    encoding=encoding,
                    cause=str(error),
                )
            values[field.name] = text.strip()
            position += field.length
        records.append(DbfRecord(values=values, deleted=deleted))
        offset += record_size

    return DbfTable(fields=fields, records=tuple(records))


def _row_error(row_number: int, reason: str, **details: object) -> NoReturn:
    raise ValuationValidationError(
        "EMOP_ROW_UNPARSEABLE",
        f"linha ilegível no catálogo EMOP (EMOP_ROW_UNPARSEABLE:{row_number}): {reason}",
        {"row": row_number, "reason": reason, **details},
    )


def read_emop_catalog_with_report(
    dbf_path: Path, layout: EmopCatalogLayout
) -> tuple[PriceCatalog, EmopImportNotes]:
    """Lê a tabela .DBF do catálogo EMOP e devolve o catálogo canônico e as notas da leitura.

    Fail-closed, na ordem: estrutura do .DBF em si (`EMOP_DBF_UNSUPPORTED`), campo
    declarado no layout ausente da tabela (`EMOP_FIELD_MISSING`), depois linha a linha —
    registro deletado é pulado e contado (nunca importado), código fora do
    `code_pattern` do layout, preço não numérico ou negativo, descrição vazia e por fim
    qualquer outra violação estrutural do modelo (`EMOP_ROW_UNPARSEABLE` em todos os
    casos, com o número da linha). Tabela sem nenhuma entrada válida recusa
    (`EMOP_EMPTY`); código duplicado recusa pelo `CATALOG_DUPLICATE_CODE` que o próprio
    `PriceCatalog` já garante. O catálogo devolvido nasce inteiro com
    `origin=PriceOrigin.EMOP` — é esse dado que os guardrails de `calc.py` e
    `workbook_writer.py` usam para recusar este catálogo na cadeia da medição licitada.
    """
    source_sha256 = file_sha256(dbf_path)
    table = _read_dbf_table(dbf_path, layout.encoding)

    available = {field.name for field in table.fields}
    missing = sorted({name for name in layout.declared_fields if name not in available})
    if missing:
        raise ValuationValidationError(
            "EMOP_FIELD_MISSING",
            "campo declarado no layout EMOP está ausente da tabela .DBF",
            {"fields": missing, "available": sorted(available)},
        )

    code_pattern = re.compile(layout.code_pattern)
    entries: list[PriceCatalogEntry] = []
    deleted_rows: list[int] = []
    for row_number, record in enumerate(table.records, start=1):
        if record.deleted:
            deleted_rows.append(row_number)
            continue

        code = record.values[layout.code_field]
        if not code_pattern.fullmatch(code):
            _row_error(row_number, "código fora do padrão declarado no layout", code=code)

        raw_price = record.values[layout.price_field]
        try:
            unit_price = Decimal(raw_price)
        except InvalidOperation:
            _row_error(row_number, "preço não numérico", code=code, raw_price=raw_price)
        if unit_price < 0:
            _row_error(row_number, "preço negativo", code=code, raw_price=raw_price)

        description = record.values[layout.description_field]
        if not description:
            _row_error(row_number, "linha sem descrição", code=code)

        try:
            entry = PriceCatalogEntry(
                code=code,
                description=description,
                unit=record.values[layout.unit_field],
                unit_price=unit_price,
                family_code=record.values[layout.family_code_field],
                family_name=record.values[layout.family_name_field],
                subgroup_code=record.values[layout.subgroup_code_field],
                subgroup_name=record.values[layout.subgroup_name_field],
                origin=PriceOrigin.EMOP,
            )
        except (ValidationError, ValuationValidationError) as error:
            _row_error(
                row_number,
                "linha não corresponde ao contrato de entrada do catálogo",
                code=code,
                cause=str(error),
            )
        entries.append(entry)

    if not entries:
        raise ValuationValidationError(
            "EMOP_EMPTY",
            "tabela .DBF não produziu nenhuma entrada válida para o catálogo",
            {"source": str(dbf_path), "deleted_rows": len(deleted_rows)},
        )

    catalog = PriceCatalog(
        id=emop_catalog_id_for(source_sha256),
        source_label=layout.source_label,
        reference_month=layout.reference_month,
        source_sha256=source_sha256,
        entries=entries,
        origin=PriceOrigin.EMOP,
    )
    notes = EmopImportNotes(deleted_count=len(deleted_rows), deleted_rows=tuple(deleted_rows))
    return catalog, notes


def read_emop_catalog(dbf_path: Path, layout: EmopCatalogLayout) -> PriceCatalog:
    """Lê o catálogo EMOP a partir do .DBF, descartando as notas da leitura."""
    catalog, _ = read_emop_catalog_with_report(dbf_path, layout)
    return catalog
