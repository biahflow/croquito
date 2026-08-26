"""Derivação de transporte, carga e bota-fora a partir dos serviços já orçados.

O capítulo de transporte de um orçamento não é medido na prancha: ele é **função do resto
do orçamento**. Na memória de cálculo da prefeitura isso aparece como uma tabela em que
cada linha diz `quantidade(outro serviço) x massa específica x espessura x distância`, com
a origem buscada por `VLOOKUP` dentro da própria aba.

A tabela é propriedade do contrato, não da obra: densidade de concreto e espessura de
camada descrevem o material. Hoje ela é redigitada a cada praça — 112 linhas —, e é isso
que este módulo elimina, transformando-a em seed versionado e curável
(`data/sco-haulage-v1.json`), no mesmo molde de `sco-synonyms-v1.json` e
`sco-legend-noise-v1.json`.

Três coisas que o desenho respeita, e que vieram do arquivo real:

1. **A chave é o código do catálogo.** A memória referencia a origem por número de item, que
   é posicional: no arquivo real, 330 dos 433 itens têm código diferente entre duas abas
   para o mesmo número. Aqui só existe código.
2. **A forma da fórmula muda com o destino.** O transporte horizontal tem distância
   (`P.ESP x ESP x DAM`), a carga e descarga não (`P.ESP x ESP`), e a retirada de entulho
   usa empolamento (`EMP`). Os fatores são declarados por linha, com o nome que a memória
   imprime — não há forma única embutida em código.
3. **O fator é sobrescrevível por obra.** A distância de carrinho de mão pode ser do
   canteiro e não do contrato; `overrides` permite trocá-la sem tocar na tabela, e enquanto
   ninguém decidir, vale a da fonte.

O que este módulo **não** faz: percorrer o orçamento montado gerando as linhas de
transporte. Isso depende da matriz de contribuições (F-038), que ainda não existe; aqui
estão o dado, a conferência e o cálculo de uma derivação.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from decimal import Decimal
from importlib import resources
from typing import Final

from pydantic import Field, model_validator

from croquito_valuation.errors import ValuationValidationError
from croquito_valuation.models import (
    NON_SCO_CODE_PATTERN,
    CalcOperand,
    ExactDecimal,
    ValuationContractModel,
    product_of,
)
from croquito_valuation.rounding import quantity_round
from croquito_valuation.sco import SCO_CODE_PATTERN

HAULAGE_SEED_VERSION: Final = "sco-haulage-v1"

_HAULAGE_SEED_FILENAME: Final = "sco-haulage-v1.json"


class HaulageFactor(ValuationContractModel):
    """Fator que converte a quantidade da origem, com o nome que a memória imprime.

    `name` é dado, não identificador: chega em português abreviado, como na planilha
    (`P.ESP`, `ESP`, `DAM`, `EMP`), e é o que vai para a célula do operando.
    """

    name: str = Field(min_length=1, max_length=60)
    value: ExactDecimal = Field(gt=0)
    unit: str | None = Field(default=None, min_length=1, max_length=20)


class ServiceHaulage(ValuationContractModel):
    """Uma linha da tabela: o serviço de destino, o de origem e os fatores entre eles."""

    target_code: str = Field(min_length=1, max_length=30)
    origin_code: str = Field(min_length=1, max_length=30)
    label: str = Field(min_length=1, max_length=120)
    factors: list[HaulageFactor] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_codes(self) -> ServiceHaulage:
        # O item que nenhuma tabela cotou também precisa ser transportado: o contrato real
        # traz códigos `IE...` fora do SCO, e recusá-los deixaria o entulho deles de fora.
        # Vale o mesmo superset estrutural das demais origens de preço.
        invalid = [
            code
            for code in (self.target_code, self.origin_code)
            if re.fullmatch(SCO_CODE_PATTERN, code) is None
            and re.fullmatch(NON_SCO_CODE_PATTERN, code) is None
        ]
        if invalid:
            raise ValuationValidationError(
                "HAULAGE_CODE_INVALID",
                "código da tabela de transporte não tem formato de código de catálogo",
                {"label": self.label, "codes": invalid},
            )
        if self.target_code == self.origin_code:
            raise ValuationValidationError(
                "HAULAGE_SELF_DERIVATION",
                "serviço não pode derivar a própria quantidade",
                {"label": self.label, "code": self.target_code},
            )
        return self


class HaulageTable(ValuationContractModel):
    """Tabela de derivação curada, versionada com o pacote.

    `unmapped_labels` não é sobra: são materiais que a fonte cobre e que não foi possível
    amarrar a um código — declará-los é o que impede que a tabela pareça completa quando
    não é.
    """

    version: str = Field(min_length=1, max_length=40)
    source_label: str = Field(min_length=1, max_length=200)
    derivations: list[ServiceHaulage] = Field(min_length=1)
    unmapped_labels: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_pairs(self) -> HaulageTable:
        seen: set[tuple[str, str]] = set()
        duplicated: list[str] = []
        for derivation in self.derivations:
            pair = (derivation.target_code, derivation.origin_code)
            if pair in seen:
                duplicated.append(f"{derivation.origin_code}->{derivation.target_code}")
            seen.add(pair)
        if duplicated:
            raise ValuationValidationError(
                "HAULAGE_DUPLICATE_PAIR",
                "a tabela de transporte deriva o mesmo par de serviços mais de uma vez",
                {"pairs": sorted(set(duplicated))},
            )
        return self

    def derivations_for(self, target_code: str) -> list[ServiceHaulage]:
        """Linhas que alimentam um serviço de destino, na ordem da tabela."""
        return [
            derivation for derivation in self.derivations if derivation.target_code == target_code
        ]


def default_haulage_table() -> HaulageTable:
    """Tabela empacotada com a biblioteca, validada na leitura."""
    payload = (
        resources.files("croquito_valuation")
        .joinpath("data", _HAULAGE_SEED_FILENAME)
        .read_text(encoding="utf-8")
    )
    return HaulageTable.model_validate_json(payload)


def _applied_factors(
    derivation: ServiceHaulage, overrides: Mapping[str, Decimal] | None
) -> list[HaulageFactor]:
    """Fatores da linha, com os que a obra sobrescreveu trocados pelo valor dela."""
    if not overrides:
        return list(derivation.factors)
    return [
        factor.model_copy(update={"value": overrides[factor.name]})
        if factor.name in overrides
        else factor
        for factor in derivation.factors
    ]


def derive_haulage_quantity(
    origin_quantity: Decimal,
    derivation: ServiceHaulage,
    *,
    overrides: Mapping[str, Decimal] | None = None,
) -> Decimal:
    """Quantidade do serviço derivado: a da origem multiplicada pelos fatores.

    É o `ROUND(PRODUCT(...);2)` da planilha, com o mesmo arredondamento de quantidade do
    resto da medição — o resultado confere ao centavo com a memória da prefeitura.
    """
    factors = _applied_factors(derivation, overrides)
    return quantity_round(product_of([origin_quantity, *(factor.value for factor in factors)]))


def haulage_operands(
    origin_quantity: Decimal,
    derivation: ServiceHaulage,
    *,
    origin_unit: str | None = None,
    overrides: Mapping[str, Decimal] | None = None,
) -> list[CalcOperand]:
    """Operandos prontos para a memória: a quantidade da origem e cada fator.

    A quantidade da origem entra **literal**, com o código citado no nome. É o que mantém a
    memória autocontida — a planilha publicada não carrega referência cruzada entre abas, e
    quem confere lê o número que foi usado, não uma fórmula que precisa resolver.
    """
    factors = _applied_factors(derivation, overrides)
    return [
        CalcOperand(
            name=f"QUANTIDADE {derivation.origin_code}"[:60],
            value=origin_quantity,
            unit=origin_unit,
        ),
        *(
            CalcOperand(name=factor.name, value=factor.value, unit=factor.unit)
            for factor in factors
        ),
    ]
