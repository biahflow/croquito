"""Composição de custo manual: o preço que o orçamentista monta, compilado a catálogo.

Terceira fonte da cascata do orçamento-base (`ADR-0027`), depois do SCO e da EMOP: quando
nenhuma tabela publicada tem o item, o orçamentista monta o preço unitário somando
coeficientes de mão de obra, insumo e equipamento. Aqui isso é **dado**, não planilha
solta: `CostComposition` guarda as linhas, o preço unitário é sempre recomputado
(divergência recusa) e `compile_compositions` transforma o conjunto num `PriceCatalog`
com `origin=composition` — a jusante tudo consome catálogo, uniforme.

Regra da orçamentista (M8): esta fonte vale só PRÉ-licitação. O catálogo compilado aqui é
recusado pela cadeia da medição de obra licitada (`BULLETIN_PRICE_ORIGIN_FORBIDDEN`, em
`calc.py`/`workbook_writer.py`); item licitado fora do contrato vira dossiê de aditivo
(`amendment_dossier.py`), nunca preço de composição.

## O arredondamento é conservador e declarado

O preço unitário fecha assim: **trunca cada linha** (`money_trunc(coeficiente x preço)`),
soma as linhas já truncadas e trunca o fechamento. Truncar por linha nunca devolve mais do
que truncar só no fim — 1,5 x 3,333 duas vezes vale 9,98 por linha e 9,99 no fim —, e a
escolha é a conservadora de propósito: cada parcela do preço é a parcela que a memória
imprime, e um centavo a mais no preço unitário se multiplica por toda a quantidade do
orçamento. A regra vive no modelo (recomputada na leitura), não no importador.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Final, Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import Field, model_validator

from croquito_valuation.errors import ValuationValidationError
from croquito_valuation.models import (
    MAX_DESCRIPTION_LENGTH,
    NON_SCO_CODE_PATTERN,
    REFERENCE_MONTH_PATTERN,
    SHA256_PATTERN,
    ExactDecimal,
    PriceCatalog,
    PriceCatalogEntry,
    PriceOrigin,
    ValuationContractModel,
)
from croquito_valuation.rounding import money_trunc

COMPOSITION_SCHEMA_VERSION: Final = "1.0.0"

_COMPOSITION_CATALOG_ID_NAMESPACE: Final = uuid5(
    NAMESPACE_URL, "https://croquito.local/valuation/catalog/composition"
)


def composition_catalog_id_for(source_sha256: str) -> UUID:
    """Id derivado do conteúdo do arquivo de composições: recompilar dá o mesmo catálogo.

    Namespace próprio, como `emop_catalog_id_for` (`emop.py`) e `catalog_id_for`
    (`catalog.py`): três fontes de natureza diferente nunca devem colidir de id, mesmo que
    o SHA-256 dos bytes coincidisse por acaso.
    """
    return uuid5(_COMPOSITION_CATALOG_ID_NAMESPACE, source_sha256)


class CompositionLine(ValuationContractModel):
    """Uma parcela da composição: insumo, mão de obra ou equipamento com coeficiente.

    `reference` é a fonte do preço do insumo **como o autor a declara** (um código EMOP,
    "cotação local 2026-08", uma nota fiscal): texto livre porque a origem de um insumo de
    composição manual não tem formato fechado. Ele documenta a parcela; nada aqui consulta
    a referência para buscar preço, e o preço da parcela é o declarado.
    """

    kind: Literal["labor", "material", "equipment"]
    description: str = Field(min_length=1, max_length=MAX_DESCRIPTION_LENGTH)
    unit: str = Field(min_length=1, max_length=20)
    coefficient: ExactDecimal = Field(gt=0)
    unit_price: ExactDecimal = Field(ge=0)
    reference: str | None = Field(default=None, min_length=1, max_length=200)

    @property
    def amount(self) -> Decimal:
        """Parcela da linha no preço unitário, já truncada — dinheiro nunca arredonda."""
        return money_trunc(self.coefficient * self.unit_price)


class CostComposition(ValuationContractModel):
    """Composição de custo de um serviço: as parcelas e o preço unitário que elas fecham.

    O código não é SCO: uma composição manual existe justamente porque o item não está na
    tabela publicada, então ele obedece ao superset estrutural de código não-SCO
    (`NON_SCO_CODE_PATTERN`), o mesmo da entrada de catálogo EMOP.

    A classificação (família e subgrupo) é **declarada pelo autor**: não existe hierarquia
    publicada para um preço que ele mesmo montou, e o catálogo compilado precisa dos mesmos
    campos de qualquer outra fonte.
    """

    code: str = Field(min_length=1, max_length=30)
    description: str = Field(min_length=1, max_length=MAX_DESCRIPTION_LENGTH)
    unit: str = Field(min_length=1, max_length=20)
    family_code: str = Field(min_length=1, max_length=20)
    family_name: str = Field(min_length=1, max_length=200)
    subgroup_code: str = Field(min_length=1, max_length=20)
    subgroup_name: str = Field(min_length=1, max_length=200)
    lines: list[CompositionLine] = Field(min_length=1)
    unit_price: ExactDecimal = Field(ge=0)

    @property
    def expected_unit_price(self) -> Decimal:
        """Preço unitário recomputado: trunca por linha, soma e trunca o fechamento."""
        return money_trunc(sum((line.amount for line in self.lines), Decimal("0.00")))

    @model_validator(mode="after")
    def validate_code(self) -> CostComposition:
        if re.fullmatch(NON_SCO_CODE_PATTERN, self.code) is None:
            raise ValuationValidationError(
                "COMPOSITION_CODE_INVALID",
                "código de composição não tem a estrutura esperada de código não-SCO",
                {"code": self.code},
            )
        return self

    @model_validator(mode="after")
    def validate_unit_price(self) -> CostComposition:
        expected = self.expected_unit_price
        if self.unit_price != expected:
            raise ValuationValidationError(
                "COMPOSITION_TOTAL_MISMATCH",
                "preço unitário da composição não confere com a soma truncada das linhas",
                {"code": self.code, "expected": str(expected), "declared": str(self.unit_price)},
            )
        return self


class CompositionSet(ValuationContractModel):
    """Conjunto de composições manuais de uma data-base; a fonte que vira catálogo."""

    schema_version: Literal["1.0.0"] = COMPOSITION_SCHEMA_VERSION
    source_label: str = Field(min_length=1, max_length=200)
    reference_month: str = Field(pattern=REFERENCE_MONTH_PATTERN)
    compositions: list[CostComposition] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_codes(self) -> CompositionSet:
        codes = [composition.code for composition in self.compositions]
        duplicated = sorted({code for code in codes if codes.count(code) > 1})
        if duplicated:
            raise ValuationValidationError(
                "COMPOSITION_DUPLICATE_CODE",
                "conjunto de composições possui código repetido",
                {"codes": duplicated},
            )
        return self


def compile_compositions(composition_set: CompositionSet, *, source_sha256: str) -> PriceCatalog:
    """Compila o conjunto de composições num catálogo com `origin=composition`.

    `source_sha256` é o digest do arquivo de composições de origem: é ele que amarra o
    catálogo compilado à fonte e que dá o id determinístico
    (`composition_catalog_id_for`). Recompilar o mesmo arquivo devolve o mesmo catálogo;
    editar uma composição muda o digest, o id e a data de referência do que a jusante
    consome — nunca há troca silenciosa de preço.

    A entrada compilada **duplica** o preço da composição de origem, trade-off declarado no
    `ADR-0027`: a fonte de verdade continua sendo a composição, e é o digest que impede as
    duas de divergirem em silêncio.
    """
    if re.fullmatch(SHA256_PATTERN, source_sha256) is None:
        raise ValuationValidationError(
            "COMPOSITION_SOURCE_DIGEST_INVALID",
            "digest da fonte das composições não é um SHA-256",
            {"source_sha256": source_sha256},
        )
    entries = [
        PriceCatalogEntry(
            code=composition.code,
            description=composition.description,
            unit=composition.unit,
            unit_price=composition.unit_price,
            family_code=composition.family_code,
            family_name=composition.family_name,
            subgroup_code=composition.subgroup_code,
            subgroup_name=composition.subgroup_name,
            origin=PriceOrigin.COMPOSITION,
        )
        for composition in composition_set.compositions
    ]
    return PriceCatalog(
        id=composition_catalog_id_for(source_sha256),
        source_label=composition_set.source_label,
        reference_month=composition_set.reference_month,
        source_sha256=source_sha256,
        entries=entries,
        origin=PriceOrigin.COMPOSITION,
    )
