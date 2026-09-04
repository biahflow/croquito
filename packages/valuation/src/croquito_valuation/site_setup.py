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
pular a parcela em silêncio.

A proveniência carrega **identidade e versão** (`kit_id` e `kit_version`), e é por isso que
`apply_site_setup_kit` exige `kit_id` de quem chama: o `SiteSetupKit` é o documento do acervo
e não sabe quem ele é. Até a Emenda 1 do ADR-0060 (2026-09-04) só a versão era registrada, e
dois acervos diferentes que declarassem a mesma versão eram indistinguíveis na matriz — com
as duas origens do ADR (plataforma e tenant), duas linhagens chamarem sua primeira versão de
`1.0.0` é o caso esperado, não o acidente.

**A assimetria entre prever e aplicar é deliberada, e é a feature: a pré-visualização
MARCA, a aplicação RECUSA.**

`preview_site_setup_kit` não levanta `SITE_SETUP_PARAMETER_MISSING` nem
`SITE_SETUP_CODE_ABSENT`: ela devolve **todas** as parcelas incluídas, cada uma dizendo o
que a impede de nascer (`missing_parameters`, `code_absent`) e com `quantity` nula quando a
conta não pôde ser feita. Prever não é aplicar — recusar a lista inteira porque duas de
vinte e quatro parcelas citam um parâmetro que a orçamentista não tem produzia um beco sem
saída: a saída oferecida pela recusa ("remova na pré-visualização as parcelas que os citam")
exigia uma pré-visualização que a própria recusa impedia de existir.

`apply_site_setup_kit` continua **inteiramente** fechada, e não pode ser afrouxada: ela é o
ato que mexe na matriz, e materializar "o que dá" produziria uma planilha parcial com
aparência de completa — o modo de falha mais caro desta feature (decisão 5 do Design
Approval Package, emendada em 2026-08-28 só do lado da prévia). Uma leitura que marca não
grava nada; uma escrita parcial fica gravada.

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
from uuid import UUID

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


def _included_parcels(
    kit: SiteSetupKit, *, excluded_parcel_ids: Collection[str]
) -> list[SiteSetupParcel]:
    """As parcelas que sobram depois das exclusões, na ordem do acervo.

    Única parte da conferência que a pré-visualização compartilha com a aplicação, e a
    única recusa que sobrevive nas duas: id de exclusão que o acervo não tem é erro de quem
    CHAMA, não estado do trabalho da orçamentista — não há o que marcar numa parcela que
    não existe.
    """
    excluded = set(excluded_parcel_ids)
    unknown_excluded = sorted(excluded - {parcel.id for parcel in kit.parcels})
    if unknown_excluded:
        raise ValuationValidationError(
            "SITE_SETUP_UNKNOWN_PARCEL",
            "id de exclusão não existe neste acervo",
            {"ids": unknown_excluded},
        )
    return [parcel for parcel in kit.parcels if parcel.id not in excluded]


def _resolve_selected_parcels(
    kit: SiteSetupKit,
    parameters: Mapping[str, Decimal],
    *,
    kit_id: UUID,
    excluded_parcel_ids: Collection[str],
    available_codes: Collection[str] | None,
) -> list[tuple[SiteSetupParcel, CalcContribution]]:
    """Falha fechada e materialização da APLICAÇÃO — a pré-visualização não passa por aqui.

    Nada nasce parcialmente: a conferência inteira corre antes de qualquer parcela ser
    materializada. A ordem das recusas é: id de exclusão desconhecido (erro do chamador),
    depois parâmetro faltante, depois código ausente do catálogo — só então materializa.

    Até 2026-08-28 a pré-visualização compartilhava esta função. Ela deixou de compartilhar
    porque prever e aplicar querem coisas diferentes do mesmo estado (ver a docstring do
    módulo); o que sobrou em comum é `_included_parcels`, e ele não reintroduz recusa
    nenhuma no caminho da prévia.
    """
    included = _included_parcels(kit, excluded_parcel_ids=excluded_parcel_ids)

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
        (parcel, _contribution_of(parcel, parameters, kit_id=kit_id, kit_version=kit.version))
        for parcel in included
    ]


def _contribution_of(
    parcel: SiteSetupParcel,
    parameters: Mapping[str, Decimal],
    *,
    kit_id: UUID | None,
    kit_version: str,
) -> CalcContribution:
    """A `CalcContribution` de uma parcela cujos parâmetros JÁ estão todos declarados.

    Uma só construção para os dois caminhos: a aplicação a materializa na matriz, e a
    pré-visualização a usa só para chegar ao subtotal pelo mesmo caminho aritmético. Chamá-la
    com parâmetro faltando é erro de programa (`KeyError` em `_resolve_operand`), e é por isso
    que a prévia confere `missing_parameters` antes.

    `kit_id` é `UUID | None` só porque a prévia passa `None`: a proveniência que ela constrói
    é descartada na mesma expressão em que nasce (só o `subtotal` é lido), e não chega a
    nenhuma matriz. Na APLICAÇÃO ele é sempre o id do acervo — `apply_site_setup_kit` o exige.
    """
    return CalcContribution(
        source_item_id=None,
        label=parcel.label,
        basis=ContributionBasis.STANDALONE,
        recipe=parcel.recipe,
        operands=[_resolve_operand(operand, parameters) for operand in parcel.operands],
        deductions=[_resolve_operand(operand, parameters) for operand in parcel.deductions],
        note=parcel.note,
        kit_origin=SiteSetupOrigin(kit_id=kit_id, kit_version=kit_version, parcel_id=parcel.id),
    )


def apply_site_setup_kit(
    kit: SiteSetupKit,
    parameters: Mapping[str, Decimal],
    *,
    kit_id: UUID,
    excluded_parcel_ids: Collection[str] = (),
    available_codes: Collection[str] | None = None,
) -> list[ServiceContributions]:
    """Aplica o acervo, resolvendo parâmetros e materializando contribuições `STANDALONE`.

    Pura e idempotente: mesma entrada, mesma saída, sem estado global, sem I/O. Agrupa por
    `code`, na ordem de primeira aparição da parcela no acervo — mesma convenção de
    `assembleCalcMatrix` (`apps/web/src/orcamento/matrix.ts`). Duas parcelas do mesmo
    código entram como duas contribuições do mesmo `ServiceContributions`.

    `kit_id` é OBRIGATÓRIO, e continua sem quebrar a pureza: quem chama informa a identidade
    do acervo que aplicou, e esta função segue sem saber onde ele mora (ADR-0060 decisão 3).
    Ela é obrigatória porque `SiteSetupOrigin.kit_id` é opcional para **ler** proveniência
    anterior à Emenda 1, nunca para **gravar** parcela nova sem identidade: sem ela, uma
    reaplicação não reconheceria as parcelas que ela mesma materializou e as duplicaria.
    """
    resolved = _resolve_selected_parcels(
        kit,
        parameters,
        kit_id=kit_id,
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
class SiteSetupPreviewOperand:
    """Um operando como a pré-visualização o mostra: o valor quando há, o parâmetro sempre.

    Tipo próprio, e não `CalcOperand`, porque `CalcOperand.value` é obrigatório: reaproveitá-lo
    obrigaria a inventar um número para o operando cujo parâmetro ninguém declarou — zero, ou
    qualquer outro —, e um número inventado numa coluna de conta é exatamente o que o
    repositório proíbe. Aqui `value` é `None` quando o parâmetro falta, e `parameter` diz de
    onde o número veio (ou viria), inclusive quando ele já foi resolvido: é o que deixa a tela
    ligar a linha bloqueada ao campo que a orçamentista precisa preencher.

    `parameter` é `None` só na constante literal, que não vem de campo nenhum.
    """

    name: str
    value: Decimal | None
    unit: str | None
    parameter: str | None


@dataclass(frozen=True, slots=True)
class SiteSetupPreviewRow:
    """Uma linha de pré-visualização: o que uma parcela vai virar, sem materializar na matriz.

    Uma linha pode ser mostrada sem poder nascer, e os dois impedimentos são independentes:

    - `missing_parameters` são os parâmetros que **esta** parcela cita e a rodada não declarou,
      na ordem de primeira aparição. Sem eles a conta não fecha, e `quantity` é `None` —
      ausência, nunca zero, porque zero é um valor que alguém pode ter declarado;
    - `code_absent` diz que o código desta parcela não está no catálogo disponível. A conta
      fecha (e `quantity` sai preenchida), mas a parcela não pode nascer: é o risco do acervo
      silenciosamente desatualizado, à vista em vez de recusado.
    """

    parcel_id: str
    code: str
    label: str
    operands: tuple[SiteSetupPreviewOperand, ...]
    quantity: Decimal | None
    missing_parameters: tuple[str, ...]
    code_absent: bool

    @property
    def blocked(self) -> bool:
        """Não pode nascer como está — por parâmetro faltante, por código, ou pelos dois."""
        return bool(self.missing_parameters) or self.code_absent


def _preview_operand(
    operand: SiteSetupOperand, parameters: Mapping[str, Decimal]
) -> SiteSetupPreviewOperand:
    """Operando resolvido quando dá, e nomeando o parâmetro que falta quando não dá."""
    if operand.value is not None:
        return SiteSetupPreviewOperand(
            name=operand.name, value=operand.value, unit=operand.unit, parameter=None
        )
    assert operand.parameter is not None  # invariante de SiteSetupOperand: um dos dois.
    return SiteSetupPreviewOperand(
        name=operand.name,
        value=parameters.get(operand.parameter),
        unit=operand.unit,
        parameter=operand.parameter,
    )


def preview_site_setup_kit(
    kit: SiteSetupKit,
    parameters: Mapping[str, Decimal],
    *,
    excluded_parcel_ids: Collection[str] = (),
    available_codes: Collection[str] | None = None,
) -> list[SiteSetupPreviewRow]:
    """O que vai nascer se o acervo for aplicado, sem materializar nada na matriz.

    **Não recusa por parâmetro faltante nem por código ausente: marca.** É a metade tolerante
    da assimetria descrita na docstring do módulo — a lista existe justamente para que a
    orçamentista possa remover as parcelas que ela não tem como declarar e aplicar as demais.
    A única recusa que sobra é `SITE_SETUP_UNKNOWN_PARCEL`, que é erro de quem chama.

    A quantidade de cada linha calculável vem do mesmo caminho que a matriz usa para
    materializar (`calc_matrix.materialize_contribution`, que por sua vez usa
    `quantity_round`/`product_of`) — a aritmética não é reimplementada aqui. A linha que cita
    parâmetro não declarado não tem quantidade nenhuma, e por isso não chega a esse caminho.
    """
    available = None if available_codes is None else set(available_codes)
    rows: list[SiteSetupPreviewRow] = []
    for parcel in _included_parcels(kit, excluded_parcel_ids=excluded_parcel_ids):
        missing = tuple(
            name for name in _collect_parameter_names([parcel]) if name not in parameters
        )
        quantity: Decimal | None = None
        if not missing:
            # `kit_id=None` aqui não é proveniência "não observada": a contribuição construída
            # não sai desta expressão — só o `subtotal` dela é lido — e a prévia não grava
            # matriz nenhuma. Pedir a identidade do acervo para calcular um número obrigaria
            # toda leitura a carregá-la sem que ela chegasse a lugar algum.
            quantity = materialize_contribution(
                _contribution_of(parcel, parameters, kit_id=None, kit_version=kit.version),
                upstream_quantity=None,
            ).subtotal
        rows.append(
            SiteSetupPreviewRow(
                parcel_id=parcel.id,
                code=parcel.code,
                label=parcel.label,
                operands=tuple(
                    _preview_operand(operand, parameters) for operand in parcel.operands
                ),
                quantity=quantity,
                missing_parameters=missing,
                code_absent=available is not None and parcel.code not in available,
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
