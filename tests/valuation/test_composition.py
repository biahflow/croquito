"""Composição manual: o preço unitário é recomputado, e o truncamento é conservador.

O que estes testes fixam é a regra de dinheiro do módulo — trunca cada linha, soma as
linhas truncadas e trunca o fechamento —, o par de recusas que impede a composição de
mentir sobre o próprio preço, e a compilação para catálogo `origin=composition`, que é a
forma como a fonte entra na cascata do orçamento-base.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from croquito_valuation.catalog import file_sha256
from croquito_valuation.composition import (
    CompositionLine,
    CompositionSet,
    CostComposition,
    compile_compositions,
    composition_catalog_id_for,
)
from croquito_valuation.errors import ValuationValidationError, valuation_error_codes
from croquito_valuation.models import PriceCatalog, PriceOrigin
from croquito_valuation.rounding import money_trunc
from croquito_worker.valuation.cli import (
    CATALOG_FILENAME,
    COMPOSITIONS_IMPORT_REPORT_FILENAME,
    main,
)

_SOURCE_DIGEST = "a" * 64
_OTHER_DIGEST = "b" * 64


def _line(
    *,
    kind: str = "material",
    description: str = "INSUMO SINTETICO",
    unit: str = "m2",
    coefficient: str = "1.00",
    unit_price: str = "10.00",
    reference: str | None = None,
) -> CompositionLine:
    return CompositionLine.model_validate(
        {
            "kind": kind,
            "description": description,
            "unit": unit,
            "coefficient": Decimal(coefficient),
            "unit_price": Decimal(unit_price),
            "reference": reference,
        }
    )


def _composition(
    *,
    code: str = "COMP.SINTETICA.001",
    lines: list[CompositionLine] | None = None,
    unit_price: Decimal | None = None,
) -> CostComposition:
    effective_lines = lines if lines is not None else [_line()]
    expected = money_trunc(sum((line.amount for line in effective_lines), Decimal("0.00")))
    return CostComposition(
        code=code,
        description="SERVICO SINTETICO COMPOSTO PELO ORCAMENTISTA",
        unit="m2",
        family_code="COMP",
        family_name="COMPOSICOES SINTETICAS",
        subgroup_code="COMP.01",
        subgroup_name="SERVICOS SINTETICOS",
        lines=effective_lines,
        unit_price=expected if unit_price is None else unit_price,
    )


def _composition_set(compositions: list[CostComposition] | None = None) -> CompositionSet:
    return CompositionSet(
        source_label="COMPOSICOES SINTETICAS (fixture)",
        reference_month="2026-07",
        compositions=compositions if compositions is not None else [_composition()],
    )


# --------------------------------------------------------------------------------------
# preço unitário: soma truncada linha a linha
# --------------------------------------------------------------------------------------


def test_unit_price_is_the_sum_of_the_lines_already_truncated() -> None:
    composition = _composition(
        lines=[
            _line(kind="material", coefficient="1.05", unit_price="18.40"),
            _line(kind="labor", unit="h", coefficient="0.35", unit_price="22.50"),
            _line(kind="equipment", unit="h", coefficient="0.05", unit_price="31.20"),
        ]
    )

    # 19,32 + 7,87 (7,875 truncado na própria linha) + 1,56.
    assert [str(line.amount) for line in composition.lines] == ["19.32", "7.87", "1.56"]
    assert composition.unit_price == Decimal("28.75")


def test_truncating_line_by_line_is_conservative_against_truncating_only_at_the_end() -> None:
    """O caso em que as duas regras divergem: 1,50 x 3,333 duas vezes.

    Por linha: 4,9995 → 4,99, duas vezes, soma 9,98. Só no fim: 9,999 → 9,99. A composição
    fica com 9,98 de propósito — um centavo a mais no preço unitário se multiplica por toda
    a quantidade do orçamento.
    """
    lines = [
        _line(kind="material", coefficient="1.50", unit_price="3.333"),
        _line(kind="labor", unit="h", coefficient="1.50", unit_price="3.333"),
    ]
    exact_sum = sum((line.coefficient * line.unit_price for line in lines), Decimal("0"))

    composition = _composition(lines=lines)

    assert money_trunc(exact_sum) == Decimal("9.99")
    assert composition.unit_price == Decimal("9.98")


def test_a_declared_unit_price_that_diverges_is_refused() -> None:
    with pytest.raises(ValidationError) as raised:
        _composition(unit_price=Decimal("11.00"))

    assert valuation_error_codes(raised.value) == ["COMPOSITION_TOTAL_MISMATCH"]


def test_a_coefficient_from_binary_float_is_refused() -> None:
    with pytest.raises(ValidationError) as raised:
        CompositionLine.model_validate(
            {
                "kind": "material",
                "description": "INSUMO SINTETICO",
                "unit": "m2",
                "coefficient": 1.05,
                "unit_price": Decimal("18.40"),
            }
        )

    assert valuation_error_codes(raised.value) == ["DECIMAL_FROM_FLOAT"]


@pytest.mark.parametrize("code", ["comp.gramado.001", "COMP GRAMADO", "C"])
def test_a_code_outside_the_non_sco_structure_is_refused(code: str) -> None:
    with pytest.raises(ValidationError) as raised:
        _composition(code=code)

    assert valuation_error_codes(raised.value) == ["COMPOSITION_CODE_INVALID"]


def test_a_repeated_code_in_the_set_is_refused() -> None:
    with pytest.raises(ValidationError) as raised:
        _composition_set([_composition(), _composition()])

    assert valuation_error_codes(raised.value) == ["COMPOSITION_DUPLICATE_CODE"]


# --------------------------------------------------------------------------------------
# compilação para catálogo
# --------------------------------------------------------------------------------------


def test_compiled_catalog_carries_the_composition_origin_and_the_source_digest() -> None:
    composition_set = _composition_set()

    catalog = compile_compositions(composition_set, source_sha256=_SOURCE_DIGEST)

    assert catalog.origin == PriceOrigin.COMPOSITION
    assert catalog.source_sha256 == _SOURCE_DIGEST
    assert catalog.id == composition_catalog_id_for(_SOURCE_DIGEST)
    assert catalog.reference_month == composition_set.reference_month
    assert catalog.source_label == composition_set.source_label
    entry = catalog.entry_for("COMP.SINTETICA.001")
    composition = composition_set.compositions[0]
    assert entry.origin == PriceOrigin.COMPOSITION
    assert entry.unit_price == composition.unit_price
    assert entry.description == composition.description
    assert entry.family_code == composition.family_code
    assert entry.subgroup_name == composition.subgroup_name


def test_the_catalog_id_follows_the_source_digest() -> None:
    composition_set = _composition_set()

    first = compile_compositions(composition_set, source_sha256=_SOURCE_DIGEST)
    again = compile_compositions(composition_set, source_sha256=_SOURCE_DIGEST)
    other = compile_compositions(composition_set, source_sha256=_OTHER_DIGEST)

    assert first.id == again.id
    assert first.id != other.id


def test_compiling_with_something_that_is_not_a_digest_is_refused() -> None:
    with pytest.raises(ValuationValidationError) as raised:
        compile_compositions(_composition_set(), source_sha256="nao-e-digest")

    assert raised.value.code == "COMPOSITION_SOURCE_DIGEST_INVALID"


# --------------------------------------------------------------------------------------
# CLI: import-compositions feliz e recusa fechada
# --------------------------------------------------------------------------------------


def _stdout(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    return dict(json.loads(lines[-1]))


def _write_set(path: Path, composition_set: CompositionSet) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(composition_set.model_dump_json(indent=2), encoding="utf-8")
    return path


def test_cli_import_compositions_publishes_the_catalog_and_its_own_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    input_path = _write_set(tmp_path / "compositions.json", _composition_set())
    output_dir = tmp_path / "import-compositions"

    exit_code = main(
        ["import-compositions", "--input", str(input_path), "--output", str(output_dir)]
    )

    assert exit_code == 0
    payload = _stdout(capsys)
    assert payload["consolidado"] == "not_imported"
    note = payload["note"]
    assert isinstance(note, str)
    assert "BULLETIN_PRICE_ORIGIN_FORBIDDEN" in note
    assert payload["compositions"] == 1
    assert payload["composition_lines"] == {"material": 1}

    catalog = PriceCatalog.model_validate_json(
        (output_dir / CATALOG_FILENAME).read_text(encoding="utf-8")
    )
    assert catalog.origin == PriceOrigin.COMPOSITION
    assert catalog.source_sha256 == file_sha256(input_path)

    report = json.loads(
        (output_dir / COMPOSITIONS_IMPORT_REPORT_FILENAME).read_text(encoding="utf-8")
    )
    for key, value in report.items():
        assert payload[key] == value


def test_cli_import_compositions_refuses_a_diverging_total_without_publishing_anything(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    valid = _composition_set()
    payload = json.loads(valid.model_dump_json())
    payload["compositions"][0]["unit_price"] = "99.99"
    input_path = tmp_path / "compositions.json"
    input_path.write_text(json.dumps(payload), encoding="utf-8")
    output_dir = tmp_path / "import-compositions"

    exit_code = main(
        ["import-compositions", "--input", str(input_path), "--output", str(output_dir)]
    )

    assert exit_code == 2
    assert _stdout(capsys)["refused"] == "COMPOSITION_TOTAL_MISMATCH"
    assert not output_dir.exists() or list(output_dir.iterdir()) == []
