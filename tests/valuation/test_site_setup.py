"""O acervo de parcelas de canteiro (F-042): dado, falha fechada e materialização.

As formas reais citadas na feature (`feature.md`) são o oráculo dos valores: `1 x 2 meses`
(banheiro químico, container), `23 dias x 12 h` + `8 dias x 24 h` (vigia, duas parcelas do
mesmo código), `2,00 x 1,40` (placa de obra) e `132,21 x 3` (transporte de andaime, os dois
operandos vindos de parâmetro).
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from croquito_valuation.assignment import CodeAssignmentSet
from croquito_valuation.calc_matrix import CalcContribution, CalcMatrix, resolve_calc_matrix
from croquito_valuation.errors import ValuationValidationError, valuation_error_codes
from croquito_valuation.models import CalcOperand, CalcRecipe, ContributionBasis, SiteSetupOrigin
from croquito_valuation.site_setup import (
    SiteSetupKit,
    SiteSetupOperand,
    SiteSetupParcel,
    apply_site_setup_kit,
    load_site_setup_kit,
    preview_site_setup_kit,
)

_KIT_VERSION = "sco-site-setup-v1-test"

_BANHEIRO = "SE01100050(/)"
_CONTAINER = "SE01110050(/)"
_VIGIA = "SE01300050(/)"
_PLACA = "SE01150050(/)"
_ANDAIME = "SE00050050(/)"

_ID_BANHEIRO = "ss_0000000000000001"
_ID_CONTAINER = "ss_0000000000000002"
_ID_VIGIA_DIA = "ss_0000000000000003"
_ID_VIGIA_NOITE = "ss_0000000000000004"
_ID_PLACA = "ss_0000000000000005"
_ID_ANDAIME = "ss_0000000000000006"

_PARAMETERS = {
    "prazo_meses": Decimal("2"),
    "semi_perimetro": Decimal("132.21"),
    "altura_alambrado": Decimal("3"),
}


def _operand(
    name: str,
    *,
    value: Decimal | None = None,
    parameter: str | None = None,
    unit: str | None = None,
) -> SiteSetupOperand:
    return SiteSetupOperand(name=name, value=value, parameter=parameter, unit=unit)


def _kit() -> SiteSetupKit:
    return SiteSetupKit(
        version=_KIT_VERSION,
        source_label="fixture sintética F-042 (Campo do Toca)",
        parcels=[
            SiteSetupParcel(
                id=_ID_BANHEIRO,
                code=_BANHEIRO,
                label="ALUGUEL DE BANHEIRO QUIMICO",
                recipe=CalcRecipe.QTY_TIMES_MONTHS,
                operands=[
                    _operand("QTD", value=Decimal("1")),
                    _operand("MESES", parameter="prazo_meses"),
                ],
            ),
            SiteSetupParcel(
                id=_ID_CONTAINER,
                code=_CONTAINER,
                label="CONTAINER",
                recipe=CalcRecipe.QTY_TIMES_MONTHS,
                operands=[
                    _operand("QTD", value=Decimal("1")),
                    _operand("MESES", parameter="prazo_meses"),
                ],
            ),
            SiteSetupParcel(
                id=_ID_VIGIA_DIA,
                code=_VIGIA,
                label="VIGIA DIURNO",
                recipe=CalcRecipe.DAYS_TIMES_HOURS,
                operands=[
                    _operand("DIAS", value=Decimal("23")),
                    _operand("H", value=Decimal("12")),
                ],
            ),
            SiteSetupParcel(
                id=_ID_VIGIA_NOITE,
                code=_VIGIA,
                label="VIGIA NOTURNO",
                recipe=CalcRecipe.DAYS_TIMES_HOURS,
                operands=[
                    _operand("DIAS", value=Decimal("8")),
                    _operand("H", value=Decimal("24")),
                ],
            ),
            SiteSetupParcel(
                id=_ID_PLACA,
                code=_PLACA,
                label="PLACA DE OBRA",
                recipe=CalcRecipe.DECLARED_PRODUCT,
                operands=[
                    _operand("LARGURA", value=Decimal("2.00"), unit="m"),
                    _operand("ALTURA", value=Decimal("1.40"), unit="m"),
                ],
            ),
            SiteSetupParcel(
                id=_ID_ANDAIME,
                code=_ANDAIME,
                label="TRANSPORTE DE ANDAIME",
                recipe=CalcRecipe.DECLARED_PRODUCT,
                operands=[
                    _operand("SEMI PERIMETRO", parameter="semi_perimetro", unit="m"),
                    _operand("ALTURA", parameter="altura_alambrado", unit="m"),
                ],
            ),
        ],
    )


def _empty_assignment_set() -> CodeAssignmentSet:
    return CodeAssignmentSet(
        plate_id="praca-sintetica-site-setup",
        page_number=1,
        image_sha256="a" * 64,
        catalog_sha256="c" * 64,
        assignments=[],
        closures=[],
        safety_notes=[
            "Confirmação de código é ato humano rastreável.",
            "Preço e unidade impressos são conferidos no portão de exportação.",
        ],
    )


# --------------------------------------------------------------------------------------
# materialização: constante e parâmetro, nas formas reais da feature
# --------------------------------------------------------------------------------------


def test_constant_and_parameter_operands_materialize_the_quantities_from_the_feature() -> None:
    rows = {row.parcel_id: row for row in preview_site_setup_kit(_kit(), _PARAMETERS)}

    assert rows[_ID_BANHEIRO].quantity == Decimal("2.00")
    assert rows[_ID_CONTAINER].quantity == Decimal("2.00")
    assert rows[_ID_VIGIA_DIA].quantity == Decimal("276.00")
    assert rows[_ID_VIGIA_NOITE].quantity == Decimal("192.00")
    assert rows[_ID_PLACA].quantity == Decimal("2.80")
    assert rows[_ID_ANDAIME].quantity == Decimal("396.63")


def test_two_parcels_of_the_same_code_become_two_contributions_of_one_service() -> None:
    services = apply_site_setup_kit(_kit(), _PARAMETERS)

    vigia = next(service for service in services if service.code == _VIGIA)
    assert len(vigia.contributions) == 2
    assert [c.label for c in vigia.contributions] == ["VIGIA DIURNO", "VIGIA NOTURNO"]


def test_contributions_are_standalone_without_source_item_and_carry_kit_origin() -> None:
    services = apply_site_setup_kit(_kit(), _PARAMETERS)

    for service in services:
        for contribution in service.contributions:
            assert contribution.basis is ContributionBasis.STANDALONE
            assert contribution.source_item_id is None
            assert contribution.kit_origin is not None
            assert contribution.kit_origin.kit_version == _KIT_VERSION


# --------------------------------------------------------------------------------------
# falha fechada: parâmetro faltante
# --------------------------------------------------------------------------------------


def test_missing_parameters_are_refused_naming_all_of_them_and_nothing_is_materialized() -> None:
    with pytest.raises(ValuationValidationError) as raised:
        apply_site_setup_kit(_kit(), {"prazo_meses": Decimal("2")})

    assert raised.value.code == "SITE_SETUP_PARAMETER_MISSING"
    assert raised.value.details["parameters"] == ["semi_perimetro", "altura_alambrado"]


def test_missing_parameter_cited_only_by_an_excluded_parcel_is_not_refused() -> None:
    services = apply_site_setup_kit(
        _kit(),
        {"prazo_meses": Decimal("2")},
        excluded_parcel_ids=[_ID_ANDAIME],
    )

    assert {code for service in services for code in [service.code]} == {
        _BANHEIRO,
        _CONTAINER,
        _VIGIA,
        _PLACA,
    }


# --------------------------------------------------------------------------------------
# falha fechada: código fora do catálogo disponível
# --------------------------------------------------------------------------------------


def test_code_absent_from_available_codes_is_refused_naming_the_code() -> None:
    with pytest.raises(ValuationValidationError) as raised:
        apply_site_setup_kit(
            _kit(),
            _PARAMETERS,
            available_codes=[_BANHEIRO, _CONTAINER, _VIGIA, _PLACA],
        )

    assert raised.value.code == "SITE_SETUP_CODE_ABSENT"
    assert raised.value.details["codes"] == [_ANDAIME]


def test_unknown_excluded_parcel_id_is_refused() -> None:
    with pytest.raises(ValuationValidationError) as raised:
        apply_site_setup_kit(_kit(), _PARAMETERS, excluded_parcel_ids=["ss_ffffffffffffffff"])

    assert raised.value.code == "SITE_SETUP_UNKNOWN_PARCEL"
    assert raised.value.details["ids"] == ["ss_ffffffffffffffff"]


# --------------------------------------------------------------------------------------
# exclusão e idempotência
# --------------------------------------------------------------------------------------


def test_excluding_one_parcel_does_not_change_the_others() -> None:
    full = {row.parcel_id: row for row in preview_site_setup_kit(_kit(), _PARAMETERS)}
    without_container = {
        row.parcel_id: row
        for row in preview_site_setup_kit(_kit(), _PARAMETERS, excluded_parcel_ids=[_ID_CONTAINER])
    }

    assert _ID_CONTAINER not in without_container
    remaining_ids = set(full) - {_ID_CONTAINER}
    for parcel_id in remaining_ids:
        assert without_container[parcel_id].quantity == full[parcel_id].quantity
        assert without_container[parcel_id].operands == full[parcel_id].operands


def test_applying_twice_with_the_same_parameters_is_idempotent() -> None:
    kit = _kit()

    first = apply_site_setup_kit(kit, _PARAMETERS)
    second = apply_site_setup_kit(kit, _PARAMETERS)

    assert first == second


# --------------------------------------------------------------------------------------
# operando ambíguo/vazio
# --------------------------------------------------------------------------------------


def test_operand_with_both_value_and_parameter_is_refused() -> None:
    with pytest.raises(ValidationError) as raised:
        SiteSetupOperand(name="MESES", value=Decimal("2"), parameter="prazo_meses")

    assert valuation_error_codes(raised.value) == ["SITE_SETUP_OPERAND_AMBIGUOUS"]


def test_a_constant_operand_of_zero_is_refused() -> None:
    """Mesma doutrina de `HaulageFactor.value` (`gt=0`): num acervo curado e distribuído,
    constante zerada nasceria zerada em toda praça que o usasse, em silêncio."""
    with pytest.raises(ValidationError):
        _operand("MESES", value=Decimal("0"))


def test_a_negative_constant_operand_is_refused() -> None:
    with pytest.raises(ValidationError):
        _operand("MESES", value=Decimal("-2"))


def test_a_parameter_declared_as_zero_is_not_refused_by_the_kit() -> None:
    """O parâmetro é declarado pela orçamentista e conferido na pré-visualização, que mostra
    a conta — a restrição do acervo é sobre a constante autorada, não sobre a rodada."""
    rows = preview_site_setup_kit(
        _kit(),
        {**_PARAMETERS, "prazo_meses": Decimal("0")},
    )

    banheiro = next(row for row in rows if row.parcel_id == _ID_BANHEIRO)
    assert banheiro.quantity == Decimal("0.00")


def test_operand_with_neither_value_nor_parameter_is_refused() -> None:
    with pytest.raises(ValidationError) as raised:
        SiteSetupOperand(name="MESES")

    assert valuation_error_codes(raised.value) == ["SITE_SETUP_OPERAND_EMPTY"]


# --------------------------------------------------------------------------------------
# proveniência (kit_origin) só em parcela standalone
# --------------------------------------------------------------------------------------


def test_kit_origin_on_a_non_standalone_contribution_is_refused() -> None:
    with pytest.raises(ValidationError) as raised:
        CalcContribution(
            source_item_id="ti_0000000000000001",
            label="AREA",
            basis=ContributionBasis.FULL,
            recipe=CalcRecipe.LENGTH_TIMES_WIDTH,
            operands=[CalcOperand(name="AREA", value=Decimal("10"))],
            kit_origin=SiteSetupOrigin(kit_version=_KIT_VERSION, parcel_id=_ID_BANHEIRO),
        )

    assert valuation_error_codes(raised.value) == ["CALC_CONTRIBUTION_KIT_ORIGIN_NOT_STANDALONE"]


# --------------------------------------------------------------------------------------
# entra na CalcMatrix existente sem afrouxar nada
# --------------------------------------------------------------------------------------


def test_apply_output_enters_a_valid_calc_matrix_and_resolves_without_error() -> None:
    services = apply_site_setup_kit(_kit(), _PARAMETERS)
    matrix = CalcMatrix(services=services)

    resolved = resolve_calc_matrix([], _empty_assignment_set(), calc_matrix=matrix)

    resolved_codes = {service.code for service in resolved.services}
    assert resolved_codes == {_BANHEIRO, _CONTAINER, _VIGIA, _PLACA, _ANDAIME}
    vigia = next(service for service in resolved.services if service.code == _VIGIA)
    assert vigia.total_quantity == Decimal("468.00")


# --------------------------------------------------------------------------------------
# carregamento de acervo declarado
# --------------------------------------------------------------------------------------


def test_load_site_setup_kit_round_trips_a_declared_payload() -> None:
    kit = _kit()

    loaded = load_site_setup_kit(kit.model_dump_json())

    assert loaded == kit
