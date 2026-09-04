"""O acervo de parcelas de canteiro (F-042): dado, falha fechada e materialização.

As formas reais citadas na feature (`feature.md`) são o oráculo dos valores: `1 x 2 meses`
(banheiro químico, container), `23 dias x 12 h` + `8 dias x 24 h` (vigia, duas parcelas do
mesmo código), `2,00 x 1,40` (placa de obra) e `132,21 x 3` (transporte de andaime, os dois
operandos vindos de parâmetro).
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError

from croquito_valuation.assignment import CodeAssignmentSet
from croquito_valuation.calc_matrix import (
    CalcContribution,
    CalcMatrix,
    ServiceContributions,
    resolve_calc_matrix,
)
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
_KIT_ID = UUID("01930000-0000-7000-8000-000000000001")
_OTHER_KIT_ID = UUID("01930000-0000-7000-8000-000000000002")
"""OUTRO acervo, que por coincidência declara a MESMA `_KIT_VERSION` — o caso que a Emenda 1
do ADR-0060 existe para distinguir, e que com as duas origens do acervo é o esperado."""

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
    services = apply_site_setup_kit(_kit(), _PARAMETERS, kit_id=_KIT_ID)

    vigia = next(service for service in services if service.code == _VIGIA)
    assert len(vigia.contributions) == 2
    assert [c.label for c in vigia.contributions] == ["VIGIA DIURNO", "VIGIA NOTURNO"]


def test_contributions_are_standalone_without_source_item_and_carry_kit_origin() -> None:
    """A proveniência sai com IDENTIDADE e versão desde a Emenda 1 do ADR-0060."""
    services = apply_site_setup_kit(_kit(), _PARAMETERS, kit_id=_KIT_ID)

    for service in services:
        for contribution in service.contributions:
            assert contribution.basis is ContributionBasis.STANDALONE
            assert contribution.source_item_id is None
            assert contribution.kit_origin is not None
            assert contribution.kit_origin.kit_id == _KIT_ID
            assert contribution.kit_origin.kit_version == _KIT_VERSION


# --------------------------------------------------------------------------------------
# falha fechada: parâmetro faltante
# --------------------------------------------------------------------------------------


def test_missing_parameters_are_refused_naming_all_of_them_and_nothing_is_materialized() -> None:
    with pytest.raises(ValuationValidationError) as raised:
        apply_site_setup_kit(_kit(), {"prazo_meses": Decimal("2")}, kit_id=_KIT_ID)

    assert raised.value.code == "SITE_SETUP_PARAMETER_MISSING"
    assert raised.value.details["parameters"] == ["semi_perimetro", "altura_alambrado"]


def test_missing_parameter_cited_only_by_an_excluded_parcel_is_not_refused() -> None:
    services = apply_site_setup_kit(
        _kit(),
        {"prazo_meses": Decimal("2")},
        kit_id=_KIT_ID,
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
            kit_id=_KIT_ID,
            available_codes=[_BANHEIRO, _CONTAINER, _VIGIA, _PLACA],
        )

    assert raised.value.code == "SITE_SETUP_CODE_ABSENT"
    assert raised.value.details["codes"] == [_ANDAIME]


# --------------------------------------------------------------------------------------
# a assimetria: a prévia marca, o apply recusa
# --------------------------------------------------------------------------------------


def test_preview_shows_every_parcel_and_marks_the_ones_that_cannot_be_born() -> None:
    """Só `_ID_ANDAIME` cita os dois parâmetros que faltam; as outras cinco calculam."""
    rows = preview_site_setup_kit(_kit(), {"prazo_meses": Decimal("2")})

    assert [row.parcel_id for row in rows] == [
        _ID_BANHEIRO,
        _ID_CONTAINER,
        _ID_VIGIA_DIA,
        _ID_VIGIA_NOITE,
        _ID_PLACA,
        _ID_ANDAIME,
    ]
    andaime = rows[-1]
    assert andaime.blocked is True
    assert andaime.missing_parameters == ("semi_perimetro", "altura_alambrado")
    # Ausência, e não zero: o operando não resolvido não tem valor nenhum a mostrar.
    assert andaime.quantity is None
    assert [(operand.name, operand.value, operand.parameter) for operand in andaime.operands] == [
        ("SEMI PERIMETRO", None, "semi_perimetro"),
        ("ALTURA", None, "altura_alambrado"),
    ]
    for row in rows[:-1]:
        assert row.blocked is False
        assert row.missing_parameters == ()
        assert row.quantity is not None
    assert rows[0].quantity == Decimal("2.00")


def test_apply_refuses_the_same_state_the_preview_merely_marks() -> None:
    """A assimetria provada lado a lado: a mesma entrada, marcada de um lado, recusada do outro."""
    parameters = {"prazo_meses": Decimal("2")}

    preview_site_setup_kit(_kit(), parameters)  # não levanta

    with pytest.raises(ValuationValidationError) as raised:
        apply_site_setup_kit(_kit(), parameters, kit_id=_KIT_ID)

    assert raised.value.code == "SITE_SETUP_PARAMETER_MISSING"
    assert raised.value.details["parameters"] == ["semi_perimetro", "altura_alambrado"]


def test_preview_marks_the_code_absent_from_the_catalog_without_refusing() -> None:
    """A conta fecha e a quantidade sai; o que falta é o código no catálogo da rodada."""
    rows = {
        row.parcel_id: row
        for row in preview_site_setup_kit(
            _kit(),
            _PARAMETERS,
            available_codes=[_BANHEIRO, _CONTAINER, _VIGIA, _PLACA],
        )
    }

    andaime = rows[_ID_ANDAIME]
    assert andaime.code_absent is True
    assert andaime.blocked is True
    assert andaime.quantity == Decimal("396.63")
    assert andaime.missing_parameters == ()
    assert all(not row.code_absent for parcel_id, row in rows.items() if parcel_id != _ID_ANDAIME)


def test_preview_marks_a_parcel_blocked_by_both_reasons_at_once() -> None:
    rows = {
        row.parcel_id: row
        for row in preview_site_setup_kit(
            _kit(),
            {"prazo_meses": Decimal("2")},
            available_codes=[_BANHEIRO, _CONTAINER, _VIGIA, _PLACA],
        )
    }

    andaime = rows[_ID_ANDAIME]
    assert andaime.missing_parameters == ("semi_perimetro", "altura_alambrado")
    assert andaime.code_absent is True
    assert andaime.quantity is None


def test_preview_of_an_excluded_blocked_parcel_produces_no_row_at_all() -> None:
    """Parcela removida não vira linha, e por isso não vira marca: ela não vai nascer."""
    rows = preview_site_setup_kit(
        _kit(),
        {"prazo_meses": Decimal("2")},
        excluded_parcel_ids=[_ID_ANDAIME],
    )

    assert _ID_ANDAIME not in [row.parcel_id for row in rows]
    assert all(not row.blocked for row in rows)


def test_a_missing_parameter_cited_only_by_a_deduction_still_blocks_the_row() -> None:
    """Dedução é parte da conta: parâmetro citado nela também impede o subtotal."""
    kit = SiteSetupKit(
        version=_KIT_VERSION,
        source_label="fixture sintética F-042 (dedução paramétrica)",
        parcels=[
            SiteSetupParcel(
                id=_ID_PLACA,
                code=_PLACA,
                label="PLACA DE OBRA COM DESCONTO",
                recipe=CalcRecipe.DECLARED_PRODUCT,
                operands=[_operand("LARGURA", value=Decimal("2.00"), unit="m")],
                deductions=[_operand("VAO", parameter="vao_descontado", unit="m")],
            )
        ],
    )

    (row,) = preview_site_setup_kit(kit, {})

    assert row.missing_parameters == ("vao_descontado",)
    assert row.quantity is None


def test_preview_still_refuses_an_exclusion_id_the_kit_does_not_have() -> None:
    """A única recusa que sobra na prévia é erro de quem chama, não estado do trabalho."""
    with pytest.raises(ValuationValidationError) as raised:
        preview_site_setup_kit(_kit(), _PARAMETERS, excluded_parcel_ids=["ss_ffffffffffffffff"])

    assert raised.value.code == "SITE_SETUP_UNKNOWN_PARCEL"
    assert raised.value.details["ids"] == ["ss_ffffffffffffffff"]


def test_unknown_excluded_parcel_id_is_refused() -> None:
    with pytest.raises(ValuationValidationError) as raised:
        apply_site_setup_kit(
            _kit(), _PARAMETERS, kit_id=_KIT_ID, excluded_parcel_ids=["ss_ffffffffffffffff"]
        )

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

    first = apply_site_setup_kit(kit, _PARAMETERS, kit_id=_KIT_ID)
    second = apply_site_setup_kit(kit, _PARAMETERS, kit_id=_KIT_ID)

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
            kit_origin=SiteSetupOrigin(
                kit_id=_KIT_ID, kit_version=_KIT_VERSION, parcel_id=_ID_BANHEIRO
            ),
        )

    assert valuation_error_codes(raised.value) == ["CALC_CONTRIBUTION_KIT_ORIGIN_NOT_STANDALONE"]


def test_two_different_kits_with_the_same_version_produce_distinguishable_provenance() -> None:
    """O caso que a Emenda 1 do ADR-0060 existe para resolver, no motor do domínio.

    Duas linhagens independentes chamarem sua primeira versão de `1.0.0` é o esperado, não o
    acidente: aplicar dois acervos DIFERENTES que declaram a mesma `version` produz parcelas
    com a MESMA versão e identidades distintas, e é essa distinção que o merge do apply usa
    (`merge_site_setup_contributions`) para não confundir um acervo com o outro.
    """
    primeiro = apply_site_setup_kit(_kit(), _PARAMETERS, kit_id=_KIT_ID)
    segundo = apply_site_setup_kit(_kit(), _PARAMETERS, kit_id=_OTHER_KIT_ID)

    origens_do_primeiro = [
        contribution.kit_origin for service in primeiro for contribution in service.contributions
    ]
    origens_do_segundo = [
        contribution.kit_origin for service in segundo for contribution in service.contributions
    ]
    assert all(origem is not None for origem in origens_do_primeiro + origens_do_segundo)
    assert {origem.kit_version for origem in origens_do_primeiro if origem is not None} == {
        _KIT_VERSION
    }
    assert {origem.kit_version for origem in origens_do_segundo if origem is not None} == {
        _KIT_VERSION
    }
    assert {origem.kit_id for origem in origens_do_primeiro if origem is not None} == {_KIT_ID}
    assert {origem.kit_id for origem in origens_do_segundo if origem is not None} == {_OTHER_KIT_ID}
    # Mesma versão, mesmas parcelas, mesma aritmética: só a identidade separa as duas.
    assert origens_do_primeiro != origens_do_segundo


def test_provenance_written_before_the_amendment_still_validates_with_a_null_kit_id() -> None:
    """`kit_id` ausente é "não observado", e não recusa: nenhuma rodada gravada é migrada."""
    antiga = SiteSetupOrigin.model_validate(
        {"kit_version": _KIT_VERSION, "parcel_id": _ID_BANHEIRO}
    )

    assert antiga.kit_id is None
    assert antiga.kit_version == _KIT_VERSION
    # Explícito e ausente são a mesma proveniência: as duas dizem "não observado".
    assert antiga == SiteSetupOrigin(kit_id=None, kit_version=_KIT_VERSION, parcel_id=_ID_BANHEIRO)


def test_a_fabricated_kit_id_is_refused_instead_of_becoming_provenance() -> None:
    """Identidade que não identifica acervo nenhum — `""` inclusive — recusa na leitura."""
    for fabricado in ("", "acervo-1"):
        with pytest.raises(ValidationError):
            SiteSetupOrigin.model_validate(
                {
                    "kit_id": fabricado,
                    "kit_version": _KIT_VERSION,
                    "parcel_id": _ID_BANHEIRO,
                }
            )


def test_the_round_document_round_trips_with_and_without_the_kit_id() -> None:
    """A matriz gravada na rodada volta idêntica pelos dois regimes de proveniência.

    É o `calc_matrix_json` da revisão: serializado com `model_dump(mode="json")` e relido com
    `model_validate`, exatamente como a rota grava e como `matrix_of` o revalida na leitura.
    Uma matriz que misture as duas proveniências é o estado de uma rodada que aplicou acervo
    antes e depois da emenda, e ela precisa atravessar o round-trip sem perder nem inventar
    identidade.
    """
    com_identidade = apply_site_setup_kit(_kit(), _PARAMETERS, kit_id=_KIT_ID)[0].contributions[0]
    sem_identidade = CalcContribution(
        label="PARCELA ANTERIOR A EMENDA",
        basis=ContributionBasis.STANDALONE,
        recipe=CalcRecipe.DECLARED_PRODUCT,
        operands=[CalcOperand(name="QTD", value=Decimal("1.00"))],
        kit_origin=SiteSetupOrigin(kit_version=_KIT_VERSION, parcel_id=_ID_BANHEIRO),
    )
    matriz = CalcMatrix(
        services=[
            ServiceContributions(code=_BANHEIRO, contributions=[com_identidade, sem_identidade])
        ]
    )

    documento = matriz.model_dump(mode="json")
    relida = CalcMatrix.model_validate(documento)

    assert relida == matriz
    # O JSON diz a mesma coisa que o modelo: identidade de um lado, ausência do outro.
    origens = [
        contribution["kit_origin"] for contribution in documento["services"][0]["contributions"]
    ]
    assert origens[0]["kit_id"] == str(_KIT_ID)
    assert origens[1]["kit_id"] is None
    # E o documento serializado de novo é byte a byte o mesmo: o round-trip é estável.
    assert relida.model_dump(mode="json") == documento


# --------------------------------------------------------------------------------------
# entra na CalcMatrix existente sem afrouxar nada
# --------------------------------------------------------------------------------------


def test_apply_output_enters_a_valid_calc_matrix_and_resolves_without_error() -> None:
    services = apply_site_setup_kit(_kit(), _PARAMETERS, kit_id=_KIT_ID)
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
