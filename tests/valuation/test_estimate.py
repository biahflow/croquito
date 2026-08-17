"""Orçamento-base: a cascata é dado e o preço de cada linha diz de onde veio.

O que estes testes fixam é a fronteira do `ADR-0027` pelo lado da pré-licitação: três
fontes convivendo no mesmo orçamento, cada linha declarando origem/catálogo/data-base, o
item que nenhuma fonte precificou saindo declarado em vez de precificado por semelhança, e
as recusas que impedem o preço de um item de sair de uma fonte que ninguém citou.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal

import pytest
from pydantic import ValidationError

from croquito_valuation.assignment import CodeAssignment, CodeAssignmentSet
from croquito_valuation.calc import CalcBlockPlan, CalcPlan, ItemCalcPlan
from croquito_valuation.errors import ValuationValidationError, valuation_error_codes
from croquito_valuation.estimate import Estimate, build_worksite_estimate
from croquito_valuation.models import (
    CalcOperand,
    CalcRecipe,
    PriceCatalog,
    PriceCatalogEntry,
    PriceOrigin,
    ReviewerDecision,
)
from croquito_valuation.takeoff import (
    PlateBox,
    PlateEvidence,
    TakeoffItem,
    TakeoffItemStatus,
    TakeoffPacket,
)
from croquito_worker.valuation.cli import ESTIMATE_FILENAME, main

_PLATE_ID = "praca-sintetica-oeste-prancha-01"
_DIGEST = "a" * 64
_PDF_DIGEST = "b" * 64
_SCO_DIGEST = "c" * 64
_EMOP_DIGEST = "d" * 64
_COMPOSITION_DIGEST = "e" * 64
_ABSENT_DIGEST = "f" * 64
_WORKSITE_KEY = "praca-sintetica-oeste"
_WORKSITE_NAME = "PRACA SINTETICA OESTE"
_REVIEWER = "orcamentista-sintetico"
_DECIDED_AT = datetime(2026, 4, 15, 12, 0, tzinfo=UTC)

_PAVEMENT_ITEM = "ti_0000000000000001"
_LAWN_ITEM = "ti_0000000000000002"
_BENCH_ITEM = "ti_0000000000000003"
_LAMP_ITEM = "ti_0000000000000004"

_SCO_CODE = "AD04050060(/)"
_EMOP_CODE = "EMOP.CE.001"
_COMPOSITION_CODE = "COMP.GRAMADO.001"


def _evidence() -> PlateEvidence:
    return PlateEvidence(
        plate_id=_PLATE_ID,
        page_number=1,
        image_sha256=_DIGEST,
        bbox=PlateBox(left=10, top=10, right=110, bottom=60),
    )


def _decision(
    item_id: str, action: Literal["confirm", "reject"] = "confirm", *, note: str | None = None
) -> ReviewerDecision:
    return ReviewerDecision(
        decision_id=f"vd_{item_id[3:]}",
        action=action,
        reviewer_id=_REVIEWER,
        reviewer_role="orcamentista",
        decided_at=_DECIDED_AT,
        note=note,
    )


def _confirmed_item(
    item_id: str, *, label: str, unit: str = "m2", quantity: str = "10.00"
) -> TakeoffItem:
    return TakeoffItem(
        id=item_id,
        evidence=_evidence(),
        raw_text=f"{label} {quantity} {unit}",
        label=label,
        quantity=Decimal(quantity),
        unit=unit,
        source="legend_extraction",
        extractor="legend-extractor-sintetico",
        extractor_version="1.0.0",
        status=TakeoffItemStatus.CONFIRMED,
        decision=_decision(item_id),
    )


def _packet(items: list[TakeoffItem] | None = None) -> TakeoffPacket:
    return TakeoffPacket(
        plate_id=_PLATE_ID,
        page_number=1,
        image_sha256=_DIGEST,
        source_pdf_sha256=_PDF_DIGEST,
        items=items if items is not None else _default_items(),
        safety_notes=[
            "Extração automática da legenda; quantidade não confirmada.",
            "Decisão do orçamentista obrigatória antes de qualquer orçamento.",
        ],
    )


def _default_items() -> list[TakeoffItem]:
    return [
        _confirmed_item(_PAVEMENT_ITEM, label="PISO INTERTRAVADO SINTETICO", quantity="61.20"),
        _confirmed_item(_LAWN_ITEM, label="GRAMADO SINTETICO", quantity="1234.50"),
        _confirmed_item(_BENCH_ITEM, label="BANCO SINTETICO", unit="un", quantity="4.00"),
        _confirmed_item(_LAMP_ITEM, label="LUMINARIA SINTETICA", unit="un", quantity="7.00"),
    ]


def _entry(
    *,
    code: str,
    description: str,
    unit: str,
    unit_price: str,
    origin: PriceOrigin,
) -> PriceCatalogEntry:
    return PriceCatalogEntry(
        code=code,
        description=description,
        unit=unit,
        unit_price=Decimal(unit_price),
        family_code="XX",
        family_name="FAMILIA SINTETICA",
        subgroup_code="XX01",
        subgroup_name="SUBGRUPO SINTETICO",
        origin=origin,
    )


def _sco_catalog() -> PriceCatalog:
    return PriceCatalog(
        source_label="CATALOGO SCO SINTETICO",
        reference_month="2026-01",
        source_sha256=_SCO_DIGEST,
        entries=[
            _entry(
                code=_SCO_CODE,
                description="PISO INTERTRAVADO SINTETICO 10CM",
                unit="m2",
                unit_price="131.20",
                origin=PriceOrigin.SCO,
            )
        ],
        origin=PriceOrigin.SCO,
    )


def _emop_catalog(*, source_sha256: str = _EMOP_DIGEST) -> PriceCatalog:
    return PriceCatalog(
        source_label="CATALOGO EMOP SINTETICO",
        reference_month="2026-06",
        source_sha256=source_sha256,
        entries=[
            _entry(
                code=_EMOP_CODE,
                description="MOBILIARIO SINTETICO EMOP",
                unit="un",
                unit_price="980.00",
                origin=PriceOrigin.EMOP,
            )
        ],
        origin=PriceOrigin.EMOP,
    )


def _composition_catalog() -> PriceCatalog:
    return PriceCatalog(
        source_label="COMPOSICOES SINTETICAS",
        reference_month="2026-07",
        source_sha256=_COMPOSITION_DIGEST,
        entries=[
            _entry(
                code=_COMPOSITION_CODE,
                description="GRAMADO SINTETICO EM PLACAS",
                unit="m2",
                unit_price="28.75",
                origin=PriceOrigin.COMPOSITION,
            )
        ],
        origin=PriceOrigin.COMPOSITION,
    )


def _cascade() -> tuple[PriceCatalog, ...]:
    return (_sco_catalog(), _emop_catalog(), _composition_catalog())


def _assignment(
    item_id: str,
    *,
    status: Literal["confirmed", "rejected"] = "confirmed",
    code: str | None = None,
    catalog_sha256: str | None = None,
    unit_compatible: bool = True,
) -> CodeAssignment:
    action: Literal["confirm", "reject"] = "confirm" if status == "confirmed" else "reject"
    return CodeAssignment(
        item_id=item_id,
        status=status,
        code=code if status == "confirmed" else None,
        catalog_sha256=catalog_sha256 if status == "confirmed" else None,
        unit_compatible=unit_compatible if status == "confirmed" else False,
        decision=_decision(item_id, action, note=None if status == "confirmed" else "sem cotação"),
    )


def _assignment_set(
    assignments: list[CodeAssignment] | None = None,
    *,
    plate_id: str = _PLATE_ID,
    catalog_sha256: str = _SCO_DIGEST,
) -> CodeAssignmentSet:
    return CodeAssignmentSet(
        plate_id=plate_id,
        page_number=1,
        image_sha256=_DIGEST,
        catalog_sha256=catalog_sha256,
        assignments=assignments if assignments is not None else _default_assignments(),
        safety_notes=[
            "Confirmação de código é ato humano rastreável.",
            "A fonte de preço de cada item é a citada na confirmação.",
        ],
    )


def _default_assignments() -> list[CodeAssignment]:
    return [
        _assignment(_PAVEMENT_ITEM, code=_SCO_CODE, catalog_sha256=_SCO_DIGEST),
        _assignment(_LAWN_ITEM, code=_COMPOSITION_CODE, catalog_sha256=_COMPOSITION_DIGEST),
        _assignment(_BENCH_ITEM, code=_EMOP_CODE, catalog_sha256=_EMOP_DIGEST),
        _assignment(_LAMP_ITEM, status="rejected"),
    ]


def _build(
    *,
    packet: TakeoffPacket | None = None,
    assignments: CodeAssignmentSet | None = None,
    cascade: tuple[PriceCatalog, ...] | None = None,
    calc_plan: CalcPlan | None = None,
) -> Estimate:
    result = build_worksite_estimate(
        packet if packet is not None else _packet(),
        assignments if assignments is not None else _assignment_set(),
        cascade if cascade is not None else _cascade(),
        worksite_key=_WORKSITE_KEY,
        worksite_name=_WORKSITE_NAME,
        address="RUA SINTETICA 400",
        calc_plan=calc_plan,
    )
    return result.estimate


# --------------------------------------------------------------------------------------
# caminho feliz: três origens, proveniência por linha e item sem preço declarado
# --------------------------------------------------------------------------------------


def test_the_three_sources_price_their_own_lines_with_full_provenance() -> None:
    estimate = _build()

    assert [line.code for line in estimate.lines] == [_SCO_CODE, _COMPOSITION_CODE, _EMOP_CODE]
    assert [line.price_origin for line in estimate.lines] == [
        PriceOrigin.SCO,
        PriceOrigin.COMPOSITION,
        PriceOrigin.EMOP,
    ]
    assert [line.catalog_sha256 for line in estimate.lines] == [
        _SCO_DIGEST,
        _COMPOSITION_DIGEST,
        _EMOP_DIGEST,
    ]
    assert [line.reference_month for line in estimate.lines] == ["2026-01", "2026-07", "2026-06"]
    assert [line.source_label for line in estimate.lines] == [
        "CATALOGO SCO SINTETICO",
        "COMPOSICOES SINTETICAS",
        "CATALOGO EMOP SINTETICO",
    ]
    # 61,20 x 131,20 + 1234,50 x 28,75 + 4,00 x 980,00, cada total truncado antes da soma.
    assert [str(line.total) for line in estimate.lines] == ["8029.44", "35491.87", "3920.00"]
    assert estimate.total_amount == Decimal("47441.31")


def test_the_cascade_manifest_keeps_the_declared_order() -> None:
    estimate = _build()

    assert [source.origin for source in estimate.cascade] == [
        PriceOrigin.SCO,
        PriceOrigin.EMOP,
        PriceOrigin.COMPOSITION,
    ]
    assert [source.source_sha256 for source in estimate.cascade] == [
        _SCO_DIGEST,
        _EMOP_DIGEST,
        _COMPOSITION_DIGEST,
    ]


def test_the_order_of_the_cascade_is_the_one_the_caller_declared() -> None:
    """Nenhum "SCO primeiro" embutido: invertida na entrada, invertida no manifesto."""
    inverted = tuple(reversed(_cascade()))

    estimate = _build(cascade=inverted)

    assert [source.origin for source in estimate.cascade] == [
        PriceOrigin.COMPOSITION,
        PriceOrigin.EMOP,
        PriceOrigin.SCO,
    ]
    # A ordem da cascata não muda o preço de linha nenhuma: quem escolhe a fonte é a
    # citação da confirmação, não a posição na lista.
    assert estimate.total_amount == Decimal("47441.31")


def test_the_item_rejected_in_the_whole_cascade_is_declared_not_priced() -> None:
    estimate = _build()

    assert estimate.unpriced_item_ids == [_LAMP_ITEM]
    assert _LAMP_ITEM not in {line.code for line in estimate.lines}
    assert len(estimate.lines) == 3


def test_the_calc_memory_is_the_same_of_the_bulletin() -> None:
    plan = CalcPlan(
        plans=[
            ItemCalcPlan(
                item_id=_PAVEMENT_ITEM,
                blocks=[
                    CalcBlockPlan(
                        label="TRECHO SINTETICO",
                        recipe=CalcRecipe.LENGTH_TIMES_WIDTH,
                        operands=[
                            CalcOperand(name="COMPRIMENTO", value=Decimal("12.00"), unit="m"),
                            CalcOperand(name="LARGURA", value=Decimal("5.10"), unit="m"),
                        ],
                    )
                ],
            )
        ]
    )

    estimate = _build(calc_plan=plan)

    sheets = {sheet.item_number: sheet for sheet in estimate.calc_sheets}
    assert set(sheets) == {line.item_number for line in estimate.lines}
    assert sheets["1"].blocks[0].recipe is CalcRecipe.LENGTH_TIMES_WIDTH
    assert sheets["1"].total_quantity == Decimal("61.20")
    # Item sem plano recebe o bloco de quantidade direta, como no boletim.
    assert sheets["2"].blocks[0].recipe is CalcRecipe.DIRECT_QUANTITY


def test_the_estimate_survives_a_json_round_trip() -> None:
    estimate = _build()

    again = Estimate.model_validate_json(estimate.model_dump_json())

    assert again == estimate


def test_the_estimate_carries_its_own_safety_notes() -> None:
    estimate = _build()

    assert len(estimate.safety_notes) >= 2
    assert any("PRÉ-licitação" in note for note in estimate.safety_notes)


# --------------------------------------------------------------------------------------
# recusas da cascata e da citação de fonte
# --------------------------------------------------------------------------------------


def test_two_catalogs_of_the_same_origin_are_refused() -> None:
    cascade = (_sco_catalog(), _emop_catalog(), _emop_catalog(source_sha256=_ABSENT_DIGEST))

    with pytest.raises(ValuationValidationError) as raised:
        _build(cascade=cascade)

    assert raised.value.code == "ESTIMATE_CASCADE_ORIGIN_DUPLICATE"
    assert raised.value.details["origins"] == ["emop"]


def test_an_empty_cascade_is_refused() -> None:
    with pytest.raises(ValuationValidationError) as raised:
        _build(cascade=())

    assert raised.value.code == "ESTIMATE_CASCADE_EMPTY"


def test_a_confirmation_without_a_cited_source_does_not_price_anything() -> None:
    assignments = _assignment_set(
        [
            _assignment(_PAVEMENT_ITEM, code=_SCO_CODE),
            _assignment(_LAWN_ITEM, code=_COMPOSITION_CODE, catalog_sha256=_COMPOSITION_DIGEST),
            _assignment(_BENCH_ITEM, code=_EMOP_CODE, catalog_sha256=_EMOP_DIGEST),
            _assignment(_LAMP_ITEM, status="rejected"),
        ]
    )

    with pytest.raises(ValuationValidationError) as raised:
        _build(assignments=assignments)

    assert raised.value.code == "ESTIMATE_ASSIGNMENT_CATALOG_REQUIRED"
    assert raised.value.details["item_id"] == _PAVEMENT_ITEM


def test_a_source_outside_the_cascade_is_refused() -> None:
    assignments = _assignment_set(
        [
            _assignment(_PAVEMENT_ITEM, code=_SCO_CODE, catalog_sha256=_ABSENT_DIGEST),
            _assignment(_LAWN_ITEM, code=_COMPOSITION_CODE, catalog_sha256=_COMPOSITION_DIGEST),
            _assignment(_BENCH_ITEM, code=_EMOP_CODE, catalog_sha256=_EMOP_DIGEST),
            _assignment(_LAMP_ITEM, status="rejected"),
        ]
    )

    with pytest.raises(ValuationValidationError) as raised:
        _build(assignments=assignments)

    assert raised.value.code == "ASSIGNMENT_CATALOG_UNKNOWN"


def test_a_code_absent_from_the_cited_catalog_is_refused() -> None:
    """O código existe na cascata, mas não no catálogo que a decisão citou."""
    assignments = _assignment_set(
        [
            _assignment(_PAVEMENT_ITEM, code=_SCO_CODE, catalog_sha256=_SCO_DIGEST),
            _assignment(_LAWN_ITEM, code=_COMPOSITION_CODE, catalog_sha256=_COMPOSITION_DIGEST),
            _assignment(_BENCH_ITEM, code=_COMPOSITION_CODE, catalog_sha256=_EMOP_DIGEST),
            _assignment(_LAMP_ITEM, status="rejected"),
        ]
    )

    with pytest.raises(ValuationValidationError) as raised:
        _build(assignments=assignments)

    assert raised.value.code == "CATALOG_CODE_UNKNOWN"


def test_a_code_whose_shape_does_not_match_the_cited_origin_is_refused() -> None:
    """Código EMOP citado contra o SCO é erro de FONTE, não código ausente.

    A checagem é assimétrica de propósito, como a de `PriceCatalogEntry`: só a origem `sco`
    tem forma fechada, e um código SCO cabe dentro do superset estrutural das outras — lá,
    quem responde é a ausência no catálogo (`CATALOG_CODE_UNKNOWN`).
    """
    assignments = _assignment_set(
        [
            _assignment(_PAVEMENT_ITEM, code=_EMOP_CODE, catalog_sha256=_SCO_DIGEST),
            _assignment(_LAWN_ITEM, code=_COMPOSITION_CODE, catalog_sha256=_COMPOSITION_DIGEST),
            _assignment(_BENCH_ITEM, code=_EMOP_CODE, catalog_sha256=_EMOP_DIGEST),
            _assignment(_LAMP_ITEM, status="rejected"),
        ]
    )

    with pytest.raises(ValuationValidationError) as raised:
        _build(assignments=assignments)

    assert raised.value.code == "ESTIMATE_CODE_INVALID_FOR_ORIGIN"
    assert raised.value.details["price_origin"] == "sco"


# --------------------------------------------------------------------------------------
# recusas herdadas do espelho do boletim
# --------------------------------------------------------------------------------------


def test_an_assignment_set_from_another_plate_is_refused() -> None:
    with pytest.raises(ValuationValidationError) as raised:
        _build(assignments=_assignment_set(plate_id="outra-prancha"))

    assert raised.value.code == "ESTIMATE_ASSIGNMENT_PACKET_MISMATCH"


def test_a_confirmed_item_without_code_decision_is_refused() -> None:
    assignments = _assignment_set(
        [
            _assignment(_PAVEMENT_ITEM, code=_SCO_CODE, catalog_sha256=_SCO_DIGEST),
            _assignment(_LAWN_ITEM, code=_COMPOSITION_CODE, catalog_sha256=_COMPOSITION_DIGEST),
            _assignment(_BENCH_ITEM, code=_EMOP_CODE, catalog_sha256=_EMOP_DIGEST),
        ]
    )

    with pytest.raises(ValuationValidationError) as raised:
        _build(assignments=assignments)

    assert raised.value.code == "ESTIMATE_ASSIGNMENT_MISSING"
    assert raised.value.details["item_ids"] == [_LAMP_ITEM]


def test_every_code_rejected_leaves_no_estimate_to_publish() -> None:
    assignments = _assignment_set(
        [_assignment(item.id, status="rejected") for item in _default_items()]
    )

    with pytest.raises(ValuationValidationError) as raised:
        _build(assignments=assignments)

    assert raised.value.code == "ESTIMATE_NO_ITEMS"


def test_a_quantity_with_more_than_two_decimals_is_refused() -> None:
    items = [
        _confirmed_item(_PAVEMENT_ITEM, label="PISO INTERTRAVADO SINTETICO", quantity="61.205"),
        _confirmed_item(_LAWN_ITEM, label="GRAMADO SINTETICO", quantity="1234.50"),
        _confirmed_item(_BENCH_ITEM, label="BANCO SINTETICO", unit="un", quantity="4.00"),
        _confirmed_item(_LAMP_ITEM, label="LUMINARIA SINTETICA", unit="un", quantity="7.00"),
    ]

    with pytest.raises(ValuationValidationError) as raised:
        _build(packet=_packet(items))

    assert raised.value.code == "ESTIMATE_QUANTITY_SCALE_UNSUPPORTED"


def test_a_plan_that_does_not_close_with_the_confirmed_quantity_is_refused() -> None:
    plan = CalcPlan(
        plans=[
            ItemCalcPlan(
                item_id=_PAVEMENT_ITEM,
                blocks=[
                    CalcBlockPlan(
                        label="TRECHO SINTETICO",
                        recipe=CalcRecipe.LENGTH_TIMES_WIDTH,
                        operands=[
                            CalcOperand(name="COMPRIMENTO", value=Decimal("12.00"), unit="m"),
                            CalcOperand(name="LARGURA", value=Decimal("5.00"), unit="m"),
                        ],
                    )
                ],
            )
        ]
    )

    with pytest.raises(ValuationValidationError) as raised:
        _build(calc_plan=plan)

    assert raised.value.code == "ESTIMATE_PLAN_QUANTITY_MISMATCH"


# --------------------------------------------------------------------------------------
# releitura: totais e fontes revalidados
# --------------------------------------------------------------------------------------


def _estimate_payload() -> dict[str, object]:
    return dict(json.loads(_build().model_dump_json()))


def test_a_line_total_that_diverges_on_re_read_is_refused() -> None:
    payload = _estimate_payload()
    lines = payload["lines"]
    assert isinstance(lines, list)
    lines[0]["total"] = "1.00"

    with pytest.raises(ValidationError) as raised:
        Estimate.model_validate(payload)

    assert "ESTIMATE_LINE_TOTAL_MISMATCH" in valuation_error_codes(raised.value)


def test_a_total_amount_that_diverges_on_re_read_is_refused() -> None:
    payload = _estimate_payload()
    payload["total_amount"] = "1.00"

    with pytest.raises(ValidationError) as raised:
        Estimate.model_validate(payload)

    assert valuation_error_codes(raised.value) == ["ESTIMATE_TOTAL_MISMATCH"]


def test_a_line_pointing_to_a_source_outside_the_cascade_is_refused_on_re_read() -> None:
    payload = _estimate_payload()
    lines = payload["lines"]
    assert isinstance(lines, list)
    lines[0]["catalog_sha256"] = _ABSENT_DIGEST

    with pytest.raises(ValidationError) as raised:
        Estimate.model_validate(payload)

    assert valuation_error_codes(raised.value) == ["ESTIMATE_LINE_SOURCE_UNKNOWN"]


def test_a_line_whose_reference_month_diverges_from_the_cascade_is_refused_on_re_read() -> None:
    """Data-base é parte da identidade da fonte: mudar só ela também recusa."""
    payload = _estimate_payload()
    lines = payload["lines"]
    assert isinstance(lines, list)
    lines[0]["reference_month"] = "2025-12"

    with pytest.raises(ValidationError) as raised:
        Estimate.model_validate(payload)

    assert valuation_error_codes(raised.value) == ["ESTIMATE_LINE_SOURCE_UNKNOWN"]


def test_a_line_code_that_does_not_match_its_declared_origin_is_refused_on_re_read() -> None:
    payload = _estimate_payload()
    lines = payload["lines"]
    assert isinstance(lines, list)
    lines[0]["code"] = _EMOP_CODE  # a linha continua declarando origem sco

    with pytest.raises(ValidationError) as raised:
        Estimate.model_validate(payload)

    assert "ESTIMATE_CODE_INVALID_FOR_ORIGIN" in valuation_error_codes(raised.value)


def test_a_repeated_item_number_is_refused_on_re_read() -> None:
    payload = _estimate_payload()
    lines = payload["lines"]
    assert isinstance(lines, list)
    lines.append(dict(lines[0]))

    with pytest.raises(ValidationError) as raised:
        Estimate.model_validate(payload)

    assert valuation_error_codes(raised.value) == ["ESTIMATE_DUPLICATE_ITEM"]


@pytest.mark.parametrize("item_ids", [["nao-e-item"], [_LAMP_ITEM, _LAMP_ITEM]])
def test_an_invalid_list_of_unpriced_items_is_refused_on_re_read(item_ids: list[str]) -> None:
    payload = _estimate_payload()
    payload["unpriced_item_ids"] = item_ids

    with pytest.raises(ValidationError) as raised:
        Estimate.model_validate(payload)

    assert valuation_error_codes(raised.value) == ["ESTIMATE_UNPRICED_ITEM_INVALID"]


def test_a_calc_sheet_missing_for_a_line_is_refused_on_re_read() -> None:
    payload = _estimate_payload()
    sheets = payload["calc_sheets"]
    assert isinstance(sheets, list)
    payload["calc_sheets"] = sheets[:-1]

    with pytest.raises(ValidationError) as raised:
        Estimate.model_validate(payload)

    assert valuation_error_codes(raised.value) == ["ESTIMATE_CALC_SHEET_MISMATCH"]


def test_an_assignment_for_an_item_outside_the_packet_is_refused() -> None:
    assignments = _assignment_set(
        [
            *_default_assignments(),
            _assignment("ti_00000000000000ff", code=_SCO_CODE, catalog_sha256=_SCO_DIGEST),
        ]
    )

    with pytest.raises(ValuationValidationError) as raised:
        _build(assignments=assignments)

    assert raised.value.code == "ESTIMATE_ASSIGNMENT_UNKNOWN_ITEM"


def test_a_plan_for_an_item_left_out_of_the_estimate_is_refused() -> None:
    plan = CalcPlan(
        plans=[
            ItemCalcPlan(
                item_id=_LAMP_ITEM,  # item com código rejeitado: não vira linha
                blocks=[
                    CalcBlockPlan(
                        label="TRECHO SINTETICO",
                        recipe=CalcRecipe.DIRECT_QUANTITY,
                        operands=[CalcOperand(name="QUANTIDADE", value=Decimal("7.00"), unit="un")],
                    )
                ],
            )
        ]
    )

    with pytest.raises(ValuationValidationError) as raised:
        _build(calc_plan=plan)

    assert raised.value.code == "ESTIMATE_PLAN_UNKNOWN_ITEM"


def test_a_calc_sheet_that_diverges_from_the_line_quantity_is_refused_on_re_read() -> None:
    payload = _estimate_payload()
    sheets = payload["calc_sheets"]
    assert isinstance(sheets, list)
    sheets[0]["blocks"][0]["operands"][0]["value"] = "1.00"
    sheets[0]["blocks"][0]["subtotal"] = "1.00"
    sheets[0]["total_quantity"] = "1.00"

    with pytest.raises(ValidationError) as raised:
        Estimate.model_validate(payload)

    assert valuation_error_codes(raised.value) == ["ESTIMATE_QUANTITY_MISMATCH"]


# --------------------------------------------------------------------------------------
# CLI: build-estimate publica só o que passou por todas as recusas
# --------------------------------------------------------------------------------------


def _stdout(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    return dict(json.loads(lines[-1]))


def _write(path: Path, payload: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")
    return path


def _cli_args(tmp_path: Path, catalog_paths: list[Path], output_dir: Path) -> list[str]:
    packet_path = _write(tmp_path / "takeoff-packet.json", _packet().model_dump_json(indent=2))
    assignments_path = _write(
        tmp_path / "code-assignments.json", _assignment_set().model_dump_json(indent=2)
    )
    args = [
        "build-estimate",
        "--packet",
        str(packet_path),
        "--assignments",
        str(assignments_path),
    ]
    for catalog_path in catalog_paths:
        args += ["--catalog", str(catalog_path)]
    return [
        *args,
        "--worksite-key",
        _WORKSITE_KEY,
        "--worksite-name",
        _WORKSITE_NAME,
        "--output",
        str(output_dir),
    ]


def _write_cascade(tmp_path: Path) -> list[Path]:
    return [
        _write(tmp_path / f"catalog-{catalog.origin.value}.json", catalog.model_dump_json(indent=2))
        for catalog in _cascade()
    ]


def test_cli_build_estimate_publishes_the_estimate(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output_dir = tmp_path / "estimate"

    exit_code = main(_cli_args(tmp_path, _write_cascade(tmp_path), output_dir))

    assert exit_code == 0
    payload = _stdout(capsys)
    assert payload["cascade"] == ["sco", "emop", "composition"]
    assert payload["lines_by_origin"] == {"composition": 1, "emop": 1, "sco": 1}
    assert payload["unpriced"] == [_LAMP_ITEM]
    estimate = Estimate.model_validate_json(
        (output_dir / ESTIMATE_FILENAME).read_text(encoding="utf-8")
    )
    assert estimate.total_amount == Decimal("47441.31")


def test_cli_build_estimate_refuses_a_cascade_with_two_sources_of_the_same_origin(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    catalog_paths = _write_cascade(tmp_path)
    output_dir = tmp_path / "estimate"

    exit_code = main(_cli_args(tmp_path, [*catalog_paths, catalog_paths[1]], output_dir))

    assert exit_code == 2
    assert _stdout(capsys)["refused"] == "ESTIMATE_CASCADE_ORIGIN_DUPLICATE"
    assert not output_dir.exists() or list(output_dir.iterdir()) == []
