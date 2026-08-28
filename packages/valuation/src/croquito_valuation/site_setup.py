"""Acervo de parcelas de canteiro: dado, conferência e aplicação de uma unidade (F-042).

O canteiro de uma praça nasce de meia dúzia de parcelas que se repetem obra a obra —
aluguel de banheiro químico, container, vigia, placa de obra, transporte de andaime — e
cujos insumos **não estão na legenda da prancha**: são função de parâmetros da obra (prazo,
área de intervenção, semi-perímetro, altura do alambrado), não da geometria. O modelo do
domínio já sabe o que elas são (`ContributionBasis.STANDALONE`, `models.py`); o que faltava
era o acervo. Hoje a orçamentista as digita uma a uma, a cada praça.

O repositório já resolveu o mesmo problema uma vez, para o transporte (`haulage.py`): uma
tabela redigitada a cada praça virou seed versionado e curável. Este módulo segue o mesmo
molde para o canteiro — dado, conferência e cálculo de uma unidade, sem percorrer a rodada
nem persistir nada.

Uma `SiteSetupParcel` é uma contribuição `STANDALONE` autorada de antemão: código do
catálogo, `CalcRecipe` e operandos, em que cada operando é **ou** uma constante **ou** uma
referência nomeada a um parâmetro de obra. `apply_site_setup_kit` resolve as referências
contra os parâmetros declarados na rodada e materializa `CalcContribution`s prontas para
entrar na `CalcMatrix` existente — com proveniência (`SiteSetupOrigin`, em `models.py`, pelo
motivo de import documentado lá) e **falha fechada**: parâmetro citado e não declarado, ou
código fora do catálogo disponível, recusa por extenso nomeando o que falta, em vez de
pular a parcela em silêncio. `preview_site_setup_kit` responde "o que vai nascer" com a
mesma falha fechada, sem materializar nada na matriz.

O que este módulo **não** faz: montar a `CalcMatrix` da rodada, decidir quais parcelas
remover, ou trazer o primeiro acervo real. O acervo do Campo do Toca é ato humano da
orçamentista (Human Gate 4 da feature) e não é seed empacotado aqui — `load_site_setup_kit`
só valida o formato de um payload já declarado por quem chama.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from pydantic import Field, model_validator

from croquito_valuation.calc_matrix import (
    CalcContribution,
    ServiceContributions,
    materialize_contribution,
)
from croquito_valuation.errors import ValuationValidationError
from croquito_valuation.models import (
    NON_SCO_CODE_PATTERN,
    SITE_SETUP_PARCEL_ID_PATTERN,
    CalcOperand,
    CalcRecipe,
    ContributionBasis,
    ExactDecimal,
    SiteSetupOrigin,
    ValuationContractModel,
)
from croquito_valuation.sco import SCO_CODE_PATTERN

_KIT_VERSION_MAX_LENGTH: Final = 40
_SOURCE_LABEL_MAX_LENGTH: Final = 200


class SiteSetupOperand(ValuationContractModel):
    """Um operando do acervo: constante literal **ou** referência a um parâmetro de obra.

    `name` é dado, não identificador — vai para a célula do operando materializado, no
    molde de `CalcOperand.name`/`HaulageFactor.name`. `parameter` é o nome do parâmetro
    de obra que `apply_site_setup_kit` resolve contra a rodada; nunca os dois ao mesmo
    tempo, e nunca nenhum dos dois.
    """

    name: str = Field(min_length=1, max_length=60)
    value: ExactDecimal | None = Field(default=None, gt=0)
    """Constante literal, sempre positiva, no molde de `HaulageFactor.value` (`haulage.py`).

    Zero num acervo é erro de autoria, não uma parcela que vale zero: o acervo é curado e
    distribuído, então uma constante zerada nasceria zerada em toda praça que o usasse, em
    silêncio. Quando a parcela não se aplica, o caminho é removê-la na pré-visualização.
    Parâmetro resolvido em runtime não tem essa restrição — ali o valor é declarado pela
    orçamentista e conferido na pré-visualização, que mostra a conta."""

    parameter: str | None = Field(default=None, min_length=1, max_length=60)
    unit: str | None = Field(default=None, min_length=1, max_length=20)

    @model_validator(mode="after")
    def validate_value_xor_parameter(self) -> SiteSetupOperand:
        if self.value is not None and self.parameter is not None:
            raise ValuationValidationError(
                "SITE_SETUP_OPERAND_AMBIGUOUS",
                "operando do acervo não pode ser constante e referência a parâmetro ao mesmo tempo",
                {"name": self.name},
            )
        if self.value is None and self.parameter is None:
            raise ValuationValidationError(
                "SITE_SETUP_OPERAND_EMPTY",
                "operando do acervo precisa ser constante ou referência a parâmetro",
                {"name": self.name},
            )
        return self


class SiteSetupParcel(ValuationContractModel):
    """Uma parcela do acervo: uma contribuição `STANDALONE` autorada de antemão.

    `id` é a identidade estável **dentro do acervo** (`SITE_SETUP_PARCEL_ID_PATTERN`,
    `models.py`); `code` é validado contra o mesmo superset estrutural de código de
    catálogo que `ServiceHaulage.validate_codes` usa (`haulage.py`), porque uma parcela de
    canteiro real cita tanto código SCO quanto código contratual fora da tabela.
    """

    id: str = Field(pattern=SITE_SETUP_PARCEL_ID_PATTERN)
    code: str = Field(min_length=1, max_length=30)
    label: str = Field(min_length=1, max_length=120)
    recipe: CalcRecipe
    operands: list[SiteSetupOperand] = Field(min_length=1)
    deductions: list[SiteSetupOperand] = Field(default_factory=list)
    note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_code(self) -> SiteSetupParcel:
        if (
            re.fullmatch(SCO_CODE_PATTERN, self.code) is None
            and re.fullmatch(NON_SCO_CODE_PATTERN, self.code) is None
        ):
            raise ValuationValidationError(
                "SITE_SETUP_CODE_INVALID",
                "código da parcela do acervo não tem formato de código de catálogo",
                {"id": self.id, "code": self.code},
            )
        return self


class SiteSetupKit(ValuationContractModel):
    """O acervo: um conjunto versionado de parcelas de canteiro, curado e curável.

    `version` e `source_label` seguem o molde de `HaulageTable` (`haulage.py`) —
    identificação estável e versionada, e de onde o acervo foi autorado.
    """

    version: str = Field(min_length=1, max_length=_KIT_VERSION_MAX_LENGTH)
    source_label: str = Field(min_length=1, max_length=_SOURCE_LABEL_MAX_LENGTH)
    parcels: list[SiteSetupParcel] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_parcel_ids(self) -> SiteSetupKit:
        seen: set[str] = set()
        duplicated: list[str] = []
        for parcel in self.parcels:
            if parcel.id in seen:
                duplicated.append(parcel.id)
            seen.add(parcel.id)
        if duplicated:
            raise ValuationValidationError(
                "SITE_SETUP_DUPLICATE_PARCEL",
                "acervo tem parcela com id repetido",
                {"ids": sorted(set(duplicated))},
            )
        return self

    def parameter_names(self) -> tuple[str, ...]:
        """Todo parâmetro citado por qualquer operando ou dedução do acervo.

        Ordem estável (primeira aparição) e sem repetição — o que a orçamentista precisa
        declarar antes de aplicar o acervo inteiro, sem exclusão nenhuma.
        """
        return tuple(_collect_parameter_names(self.parcels))


def _collect_parameter_names(parcels: Sequence[SiteSetupParcel]) -> list[str]:
    """Parâmetros citados pelas parcelas dadas, ordem de primeira aparição, sem repetição."""
    seen: set[str] = set()
    names: list[str] = []
    for parcel in parcels:
        for operand in (*parcel.operands, *parcel.deductions):
            if operand.parameter is not None and operand.parameter not in seen:
                seen.add(operand.parameter)
                names.append(operand.parameter)
    return names


def _resolve_operand(operand: SiteSetupOperand, parameters: Mapping[str, Decimal]) -> CalcOperand:
    """Constante literal ou parâmetro já resolvido contra a rodada; `name`/`unit` preservados."""
    if operand.value is not None:
        value = operand.value
    else:
        assert operand.parameter is not None  # invariante de SiteSetupOperand: um dos dois.
        value = parameters[operand.parameter]
    return CalcOperand(name=operand.name, value=value, unit=operand.unit)


def _resolve_selected_parcels(
    kit: SiteSetupKit,
    parameters: Mapping[str, Decimal],
    *,
    excluded_parcel_ids: Collection[str],
    available_codes: Collection[str] | None,
) -> list[tuple[SiteSetupParcel, CalcContribution]]:
    """Falha fechada e materialização, compartilhadas por aplicação e pré-visualização.

    As duas funções públicas precisam da mesma checagem antes de produzir qualquer coisa:
    nada nasce parcialmente, nem na aplicação nem na pré-visualização (item 4 do task
    contract). A ordem das recusas é: id de exclusão desconhecido (erro do chamador),
    depois parâmetro faltante, depois código ausente do catálogo — só então materializa.
    """
    excluded = set(excluded_parcel_ids)
    known_ids = {parcel.id for parcel in kit.parcels}
    unknown_excluded = sorted(excluded - known_ids)
    if unknown_excluded:
        raise ValuationValidationError(
            "SITE_SETUP_UNKNOWN_PARCEL",
            "id de exclusão não existe neste acervo",
            {"ids": unknown_excluded},
        )

    included = [parcel for parcel in kit.parcels if parcel.id not in excluded]

    missing_parameters = [
        name for name in _collect_parameter_names(included) if name not in parameters
    ]
    if missing_parameters:
        raise ValuationValidationError(
            "SITE_SETUP_PARAMETER_MISSING",
            "acervo cita parâmetro de obra não declarado nesta rodada",
            {"parameters": missing_parameters},
        )

    if available_codes is not None:
        available = set(available_codes)
        seen_codes: set[str] = set()
        missing_codes: list[str] = []
        for parcel in included:
            if parcel.code not in available and parcel.code not in seen_codes:
                seen_codes.add(parcel.code)
                missing_codes.append(parcel.code)
        if missing_codes:
            raise ValuationValidationError(
                "SITE_SETUP_CODE_ABSENT",
                "acervo cita código que não está no catálogo disponível",
                {"codes": missing_codes},
            )

    return [
        (
            parcel,
            CalcContribution(
                source_item_id=None,
                label=parcel.label,
                basis=ContributionBasis.STANDALONE,
                recipe=parcel.recipe,
                operands=[_resolve_operand(operand, parameters) for operand in parcel.operands],
                deductions=[_resolve_operand(operand, parameters) for operand in parcel.deductions],
                note=parcel.note,
                kit_origin=SiteSetupOrigin(kit_version=kit.version, parcel_id=parcel.id),
            ),
        )
        for parcel in included
    ]


def apply_site_setup_kit(
    kit: SiteSetupKit,
    parameters: Mapping[str, Decimal],
    *,
    excluded_parcel_ids: Collection[str] = (),
    available_codes: Collection[str] | None = None,
) -> list[ServiceContributions]:
    """Aplica o acervo, resolvendo parâmetros e materializando contribuições `STANDALONE`.

    Pura e idempotente: mesma entrada, mesma saída, sem estado global, sem I/O. Agrupa por
    `code`, na ordem de primeira aparição da parcela no acervo — mesma convenção de
    `assembleCalcMatrix` (`apps/web/src/orcamento/matrix.ts`). Duas parcelas do mesmo
    código entram como duas contribuições do mesmo `ServiceContributions`.
    """
    resolved = _resolve_selected_parcels(
        kit,
        parameters,
        excluded_parcel_ids=excluded_parcel_ids,
        available_codes=available_codes,
    )
    grouped: dict[str, list[CalcContribution]] = {}
    for parcel, contribution in resolved:
        grouped.setdefault(parcel.code, []).append(contribution)
    return [
        ServiceContributions(code=code, contributions=contributions)
        for code, contributions in grouped.items()
    ]


@dataclass(frozen=True, slots=True)
class SiteSetupPreviewRow:
    """Uma linha de pré-visualização: o que uma parcela vai virar, sem materializar na matriz."""

    parcel_id: str
    code: str
    label: str
    operands: tuple[CalcOperand, ...]
    quantity: Decimal


def preview_site_setup_kit(
    kit: SiteSetupKit,
    parameters: Mapping[str, Decimal],
    *,
    excluded_parcel_ids: Collection[str] = (),
    available_codes: Collection[str] | None = None,
) -> list[SiteSetupPreviewRow]:
    """O que vai nascer se o acervo for aplicado, sem materializar nada na matriz.

    A quantidade de cada linha vem do mesmo caminho que a matriz usa para materializar
    (`calc_matrix.materialize_contribution`, que por sua vez usa `quantity_round`/`product_of`) — a
    aritmética não é reimplementada aqui. Usa a mesma falha fechada de `apply_site_setup_kit`.
    """
    resolved = _resolve_selected_parcels(
        kit,
        parameters,
        excluded_parcel_ids=excluded_parcel_ids,
        available_codes=available_codes,
    )
    rows: list[SiteSetupPreviewRow] = []
    for parcel, contribution in resolved:
        block = materialize_contribution(contribution, upstream_quantity=None)
        rows.append(
            SiteSetupPreviewRow(
                parcel_id=parcel.id,
                code=parcel.code,
                label=parcel.label,
                operands=tuple(block.operands),
                quantity=block.subtotal,
            )
        )
    return rows


def load_site_setup_kit(payload: str) -> SiteSetupKit:
    """Acervo carregado de um payload já declarado por quem chama, validado na leitura.

    No molde de `default_haulage_table()` (`haulage.py`), exceto que não há seed
    empacotado nesta task: o primeiro acervo é ato humano da orçamentista, a partir de uma
    praça já feita (feature.md, Human Gate 4). Isto só materializa o formato e a validação.
    """
    return SiteSetupKit.model_validate_json(payload)
