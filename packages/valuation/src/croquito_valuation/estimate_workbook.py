"""Render do orçamento-base em planilha: uma aba própria, sem VLOOKUP a catálogo (ADR-0038).

Adaptador do escritor da medição (`workbook_writer.py`), NÃO generalização dele: o
`Estimate` não tem obra múltipla, `Valuation` nem `ContractWorkbook`, e o layout que ele
imprime é o do `EstimateLayout` (`template.py`), seção própria e opcional do
`WorkbookTemplate`. As peças pequenas e sem estado (`_text`/`_number`/`_formula`/
`_atomic_save`/`_sha256`) são cópias deliberadas do desenho de `workbook_writer.py` —
mesmo padrão de duplicação de helper trivial que já existe entre `workbook_writer.py` e
`canonical.py` (`_sha256` nos dois) — em vez de importar nomes privados de outro módulo.

O escritor planeja célula a célula (`plan_estimate_workbook`) antes de gravar, e o mesmo
plano é o oráculo do auditor: nenhuma das duas pontas inventa um valor que a outra não
compartilhe. O auditor reabre o arquivo com `openpyxl.load_workbook` (por dentro de
`canonical.canonicalize_workbook`, reusada como biblioteca do mini-avaliador da gramática
fechada de fórmulas — `GRAMMAR_PATTERNS` — sem estender `canonical.audit_workbook`, que é
da medição) e recomputa cada célula em `Decimal`; falha do auditor não publica nada, gate
exercido por quem chama `write_estimate_workbook`/`audit_estimate_workbook` em sequência
(o mesmo desenho de `run_export_valuation`, no worker).

Conteúdo impresso, por decisão do pacote aprovado (ADR-0038, decisão 5) e do contrato de
T2:

- uma linha por `EstimateLine`, com FONTE = origem + data-base numa célula só e as duas
  colunas de preço (sem e com BDI);
- BDI percentual declarado uma vez, não repetido por linha;
- o valor do BDI impresso é a diferença entre os totais truncados
  (`estimate.total_amount - estimate.total_amount_without_bdi`), nunca o percentual
  aplicado ao total geral — os dois totais já vêm prontos e validados do `Estimate`;
- bloco próprio "itens sem preço na cascata" com os ids declarados em
  `unpriced_item_ids`; o `Estimate` não carrega descrição desses itens (eles nunca viram
  linha), então só o id é impresso.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Final, Literal

from openpyxl import Workbook
from openpyxl.styles import Font
from pydantic import Field, model_validator

from croquito_valuation.canonical import canonicalize_workbook
from croquito_valuation.errors import ValuationValidationError
from croquito_valuation.estimate import Estimate
from croquito_valuation.models import ExactDecimal, ValuationContractModel
from croquito_valuation.rounding import quantity_round, trunc_divergence
from croquito_valuation.template import EstimateLayout, WorkbookTemplate

MAX_DECIMAL_PLACES: Final = 2
PINNED_REASON: Final = "TRUNC_DOUBLE_DIVERGENCE"
_FIXED_TIMESTAMP: Final = datetime(2026, 1, 1, tzinfo=UTC)

CellKind = Literal["text", "number", "formula"]


class EstimatePinnedCell(ValuationContractModel):
    """Célula de total de linha fixada por divergência de truncamento (espelho de
    `workbook_writer.PinnedCell`, sem o campo `sheet` — a planilha do orçamento tem uma
    aba só)."""

    ref: str
    reason: Literal["TRUNC_DOUBLE_DIVERGENCE"] = PINNED_REASON
    item_number: str
    quantity: ExactDecimal
    unit_price_with_bdi: ExactDecimal
    value: ExactDecimal


class EstimatePlannedCell(ValuationContractModel):
    """Uma célula planejada da aba do orçamento, com o valor exato que ela deve representar."""

    ref: str = Field(pattern=r"^[A-Z]{1,2}\d+$")
    kind: CellKind
    role: str = Field(min_length=1, max_length=60)
    item_number: str | None = None
    text: str | None = None
    number: ExactDecimal | None = None
    formula: str | None = None
    number_format: str | None = None
    bold: bool = False

    @model_validator(mode="after")
    def validate_payload(self) -> EstimatePlannedCell:
        if self.kind == "text" and self.text is None:
            raise ValuationValidationError(
                "PLANNED_CELL_INVALID", "célula de texto sem texto", {"ref": self.ref}
            )
        if self.kind == "number" and self.number is None:
            raise ValuationValidationError(
                "PLANNED_CELL_INVALID", "célula numérica sem valor", {"ref": self.ref}
            )
        if self.kind == "formula" and (self.formula is None or self.number is None):
            raise ValuationValidationError(
                "PLANNED_CELL_INVALID",
                "célula de fórmula precisa de fórmula e do valor exato esperado",
                {"ref": self.ref},
            )
        return self


class EstimateWorkbookPlan(ValuationContractModel):
    """Plano completo da aba do orçamento, usado para gravar e para auditar."""

    sheet_name: str
    cells: list[EstimatePlannedCell] = Field(min_length=1)
    column_widths: dict[str, int] = Field(default_factory=dict)
    pinned_cells: list[EstimatePinnedCell] = Field(default_factory=list)

    @property
    def formula_cells(self) -> int:
        """Quantas células de fórmula o plano prevê."""
        return sum(1 for cell in self.cells if cell.kind == "formula")


class EstimateWriteReport(ValuationContractModel):
    """Resultado da gravação da planilha do orçamento."""

    output_path: str
    workbook_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    sheet_name: str
    written_cells: int = Field(ge=1)
    formula_cells: int = Field(ge=0)
    pinned_cells: list[EstimatePinnedCell] = Field(default_factory=list)


class EstimateAuditFinding(ValuationContractModel):
    """Uma divergência entre o arquivo reaberto e o orçamento que a planilha deveria imprimir."""

    code: str = Field(min_length=1, max_length=60)
    sheet: str
    ref: str | None = None
    expected: str | None = None
    found: str | None = None
    detail: str | None = None


class EstimateAuditReport(ValuationContractModel):
    """Resultado da auditoria de round-trip da planilha do orçamento-base."""

    status: Literal["ok", "divergent"]
    workbook_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    sheet_name: str
    checked_cells: int = Field(ge=0)
    formula_cells: int = Field(ge=0)
    total_amount: ExactDecimal
    pinned_cells: list[EstimatePinnedCell] = Field(default_factory=list)
    findings: list[EstimateAuditFinding] = Field(default_factory=list)


def _checked_number(value: Decimal, ref: str, role: str) -> Decimal:
    exponent = value.as_tuple().exponent
    if isinstance(exponent, int) and exponent < -MAX_DECIMAL_PLACES:
        raise ValuationValidationError(
            "DECIMAL_SCALE_UNSUPPORTED",
            "planilha só representa duas casas decimais sem perder o valor exato",
            {"ref": ref, "role": role, "value": str(value)},
        )
    return value


def _text(
    ref: str,
    role: str,
    value: str,
    *,
    bold: bool = False,
    item_number: str | None = None,
) -> EstimatePlannedCell:
    return EstimatePlannedCell(
        ref=ref, kind="text", role=role, text=value, bold=bold, item_number=item_number
    )


def _number(
    ref: str,
    role: str,
    value: Decimal,
    *,
    number_format: str | None = None,
    bold: bool = False,
    item_number: str | None = None,
) -> EstimatePlannedCell:
    return EstimatePlannedCell(
        ref=ref,
        kind="number",
        role=role,
        item_number=item_number,
        number=_checked_number(value, ref, role),
        number_format=number_format,
        bold=bold,
    )


def _formula(
    ref: str,
    role: str,
    formula: str,
    value: Decimal,
    *,
    number_format: str | None = None,
    bold: bool = False,
    item_number: str | None = None,
) -> EstimatePlannedCell:
    return EstimatePlannedCell(
        ref=ref,
        kind="formula",
        role=role,
        item_number=item_number,
        formula=formula,
        number=_checked_number(value, ref, role),
        number_format=number_format,
        bold=bold,
    )


def _require_layout(template: WorkbookTemplate) -> EstimateLayout:
    if template.estimate is None:
        raise ValuationValidationError(
            "TEMPLATE_ESTIMATE_LAYOUT_MISSING",
            "o template não declara a seção do orçamento-base (WorkbookTemplate.estimate)",
            {},
        )
    return template.estimate


def _duplicated_refs(cells: list[EstimatePlannedCell]) -> list[str]:
    seen: set[str] = set()
    duplicated: list[str] = []
    for cell in cells:
        if cell.ref in seen:
            duplicated.append(cell.ref)
        seen.add(cell.ref)
    return duplicated


def plan_estimate_workbook(estimate: Estimate, template: WorkbookTemplate) -> EstimateWorkbookPlan:
    """Planeja a aba inteira do orçamento, com o valor exato de cada célula."""
    layout = _require_layout(template)
    columns = layout.columns
    pinned: list[EstimatePinnedCell] = []
    cells: list[EstimatePlannedCell] = [
        _text(f"{layout.label_column}1", "title", layout.title, bold=True)
    ]

    pairs: list[tuple[str, str]] = [(layout.intervention_label, estimate.worksite_name)]
    if estimate.address is not None:
        pairs.append((layout.address_label, estimate.address))
    pairs.append((layout.bdi_label, f"{quantity_round(estimate.bdi_percent)}%"))
    if layout.header_row < len(pairs) + 3:
        raise ValuationValidationError(
            "TEMPLATE_HEADER_ROW_TOO_SMALL",
            "linha de cabeçalho do orçamento não deixa espaço para o bloco de identificação",
            {"header_row": layout.header_row, "required_rows": len(pairs) + 3},
        )
    for index, (label, value) in enumerate(pairs):
        row = 2 + index
        cells.append(_text(f"{layout.label_column}{row}", "header_label", label, bold=True))
        cells.append(_text(f"{layout.value_column}{row}", "header_value", value))

    for column in columns.ordered:
        cells.append(
            _text(f"{column.letter}{layout.header_row}", "column_label", column.label, bold=True)
        )

    first_line_row = layout.header_row + 1
    for index, line in enumerate(estimate.lines):
        row = first_line_row + index
        item = line.item_number
        cells.append(_text(f"{columns.item.letter}{row}", "line_item", item, item_number=item))
        cells.append(_text(f"{columns.code.letter}{row}", "line_code", line.code, item_number=item))
        cells.append(
            _text(
                f"{columns.source.letter}{row}",
                "line_source",
                f"{line.price_origin.value.upper()} {line.reference_month}",
                item_number=item,
            )
        )
        cells.append(
            _text(
                f"{columns.description.letter}{row}",
                "line_description",
                line.description,
                item_number=item,
            )
        )
        cells.append(_text(f"{columns.unit.letter}{row}", "line_unit", line.unit, item_number=item))
        cells.append(
            _number(
                f"{columns.unit_price.letter}{row}",
                "line_unit_price",
                line.unit_price,
                number_format=layout.money_number_format,
                item_number=item,
            )
        )
        cells.append(
            _number(
                f"{columns.unit_price_with_bdi.letter}{row}",
                "line_unit_price_with_bdi",
                line.unit_price_with_bdi,
                number_format=layout.money_number_format,
                item_number=item,
            )
        )
        cells.append(
            _number(
                f"{columns.quantity.letter}{row}",
                "line_quantity",
                line.quantity,
                number_format=layout.quantity_number_format,
                item_number=item,
            )
        )
        quantity_ref = f"{columns.quantity.letter}{row}"
        price_ref = f"{columns.unit_price_with_bdi.letter}{row}"
        total_ref = f"{columns.total.letter}{row}"
        if trunc_divergence(line.quantity, line.unit_price_with_bdi):
            pinned.append(
                EstimatePinnedCell(
                    ref=total_ref,
                    item_number=item,
                    quantity=line.quantity,
                    unit_price_with_bdi=line.unit_price_with_bdi,
                    value=line.total,
                )
            )
            cells.append(
                _number(
                    total_ref,
                    "line_total_pinned",
                    line.total,
                    number_format=layout.money_number_format,
                    item_number=item,
                )
            )
        else:
            cells.append(
                _formula(
                    total_ref,
                    "line_total",
                    f"=TRUNC({quantity_ref}*{price_ref},2)",
                    line.total,
                    number_format=layout.money_number_format,
                    item_number=item,
                )
            )

    last_line_row = first_line_row + len(estimate.lines) - 1
    total_col = columns.total.letter
    total_without_bdi_row = last_line_row + 2
    bdi_amount_row = total_without_bdi_row + 1
    total_row = bdi_amount_row + 1

    total_without_bdi_ref = f"{total_col}{total_without_bdi_row}"
    cells.append(
        _text(
            f"{columns.description.letter}{total_without_bdi_row}",
            "total_without_bdi_label",
            layout.total_without_bdi_label,
            bold=True,
        )
    )
    cells.append(
        _number(
            total_without_bdi_ref,
            "estimate_total_without_bdi",
            estimate.total_amount_without_bdi,
            number_format=layout.money_number_format,
            bold=True,
        )
    )

    total_ref = f"{total_col}{total_row}"
    bdi_amount_label = f"{layout.bdi_label} ({quantity_round(estimate.bdi_percent)}%)"
    cells.append(
        _text(
            f"{columns.description.letter}{bdi_amount_row}",
            "bdi_amount_label",
            bdi_amount_label,
            bold=True,
        )
    )
    cells.append(
        _formula(
            f"{total_col}{bdi_amount_row}",
            "estimate_bdi_amount",
            f"={total_ref}-{total_without_bdi_ref}",
            estimate.total_amount - estimate.total_amount_without_bdi,
            number_format=layout.money_number_format,
            bold=True,
        )
    )

    cells.append(
        _text(
            f"{columns.description.letter}{total_row}",
            "total_label",
            layout.total_label,
            bold=True,
        )
    )
    cells.append(
        _formula(
            total_ref,
            "estimate_total",
            f"=SUM({total_col}{first_line_row}:{total_col}{last_line_row})",
            estimate.total_amount,
            number_format=layout.money_number_format,
            bold=True,
        )
    )

    if estimate.unpriced_item_ids:
        unpriced_header_row = total_row + 2
        cells.append(
            _text(
                f"{columns.item.letter}{unpriced_header_row}",
                "unpriced_section_label",
                layout.unpriced_section_label,
                bold=True,
            )
        )
        for offset, item_id in enumerate(estimate.unpriced_item_ids):
            row = unpriced_header_row + 1 + offset
            cells.append(_text(f"{columns.item.letter}{row}", "unpriced_item", item_id))

    duplicated = _duplicated_refs(cells)
    if duplicated:
        raise ValuationValidationError(
            "PLAN_CELL_COLLISION",
            "o plano da planilha do orçamento gravaria duas vezes a mesma célula",
            {"refs": duplicated},
        )

    return EstimateWorkbookPlan(
        sheet_name=layout.sheet_name,
        cells=cells,
        column_widths={column.letter: column.width for column in columns.ordered},
        pinned_cells=pinned,
    )


def _atomic_save(workbook: Workbook, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=output_path.parent, prefix=f".{output_path.name}.", suffix=".xlsx"
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        workbook.save(temporary_path)
        os.replace(temporary_path, output_path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_estimate_workbook(
    estimate: Estimate, template: WorkbookTemplate, output_path: Path
) -> EstimateWriteReport:
    """Grava a planilha do orçamento-base e devolve o relatório da gravação."""
    plan = plan_estimate_workbook(estimate, template)
    workbook = Workbook()
    # Mesma razão da medição: a data de criação é fixa para não carimbar o relógio local
    # no artefato; a idempotência que importa é a do conteúdo lógico, não a dos bytes.
    workbook.properties.created = _FIXED_TIMESTAMP
    worksheet = workbook.active
    assert worksheet is not None  # sempre existe: Workbook() nasce com uma aba ativa
    worksheet.title = plan.sheet_name
    for letter, width in plan.column_widths.items():
        worksheet.column_dimensions[letter].width = width
    for planned_cell in plan.cells:
        cell = worksheet[planned_cell.ref]
        if planned_cell.kind == "text":
            cell.value = planned_cell.text
        elif planned_cell.kind == "number":
            cell.value = planned_cell.number
        else:
            cell.value = planned_cell.formula
        if planned_cell.number_format is not None:
            cell.number_format = planned_cell.number_format
        if planned_cell.bold:
            cell.font = Font(bold=True)
    _atomic_save(workbook, output_path)
    return EstimateWriteReport(
        output_path=str(output_path),
        workbook_sha256=_sha256(output_path),
        sheet_name=plan.sheet_name,
        written_cells=len(plan.cells),
        formula_cells=plan.formula_cells,
        pinned_cells=plan.pinned_cells,
    )


def _expected_text(planned_cell: EstimatePlannedCell) -> str:
    """Valor canônico que o plano prevê para a célula, no mesmo formato do arquivo."""
    if planned_cell.kind == "text":
        return str(planned_cell.text)
    number = planned_cell.number
    if number is None:  # pragma: no cover - impedido pelo validador de EstimatePlannedCell
        raise ValuationValidationError(
            "PLANNED_CELL_INVALID",
            "célula numérica planejada sem valor",
            {"ref": planned_cell.ref},
        )
    return str(quantity_round(number))


def _canonical_sheet_names(canonical: dict[str, object]) -> list[str]:
    sheets = canonical["sheets"]
    assert isinstance(sheets, list)
    names: list[str] = []
    for sheet in sheets:
        assert isinstance(sheet, dict)
        names.append(str(sheet["name"]))
    return names


def _canonical_sheet_cells(
    canonical: dict[str, object], sheet_name: str
) -> dict[str, dict[str, object]] | None:
    sheets = canonical["sheets"]
    assert isinstance(sheets, list)
    for sheet in sheets:
        assert isinstance(sheet, dict)
        if str(sheet["name"]) != sheet_name:
            continue
        raw_cells = sheet["cells"]
        assert isinstance(raw_cells, list)
        indexed: dict[str, dict[str, object]] = {}
        for cell in raw_cells:
            assert isinstance(cell, dict)
            indexed[str(cell["ref"])] = cell
        return indexed
    return None


def audit_estimate_workbook(
    workbook_path: Path, estimate: Estimate, template: WorkbookTemplate
) -> EstimateAuditReport:
    """Reabre a planilha do orçamento, recomputa as fórmulas e compara centavo a centavo.

    Reusa `canonical.canonicalize_workbook` como biblioteca — a gramática fechada de
    fórmulas (`GRAMMAR_PATTERNS`) é a mesma da medição, e é ela que recomputa cada célula
    de fórmula em `Decimal` a partir do arquivo reaberto. A comparação célula a célula é
    própria: o `Estimate` não tem `Valuation`/`WorksiteBulletin`, então
    `canonical.audit_workbook` (que os exige) não serve aqui sem ser estendido — o que o
    contrato desta tarefa proíbe.
    """
    plan = plan_estimate_workbook(estimate, template)
    canonical = canonicalize_workbook(workbook_path, template)
    found_cells = _canonical_sheet_cells(canonical, plan.sheet_name)

    findings: list[EstimateAuditFinding] = []
    if found_cells is None:
        findings.append(
            EstimateAuditFinding(
                code="SHEET_MISSING",
                sheet=plan.sheet_name,
                detail="aba do orçamento não existe no arquivo gravado",
            )
        )
        found_cells = {}

    planned_refs: set[str] = set()
    for planned_cell in plan.cells:
        planned_refs.add(planned_cell.ref)
        found = found_cells.get(planned_cell.ref)
        if found is None:
            findings.append(
                EstimateAuditFinding(
                    code="CELL_MISSING",
                    sheet=plan.sheet_name,
                    ref=planned_cell.ref,
                    expected=_expected_text(planned_cell),
                    detail=planned_cell.role,
                )
            )
            continue
        expected_kind = planned_cell.kind
        found_kind = str(found["kind"])
        if expected_kind != found_kind:
            findings.append(
                EstimateAuditFinding(
                    code="CELL_KIND_MISMATCH",
                    sheet=plan.sheet_name,
                    ref=planned_cell.ref,
                    expected=expected_kind,
                    found=found_kind,
                    detail=planned_cell.role,
                )
            )
            continue
        expected_value = _expected_text(planned_cell)
        found_value = str(found["value"])
        if expected_value != found_value:
            findings.append(
                EstimateAuditFinding(
                    code="CELL_VALUE_MISMATCH",
                    sheet=plan.sheet_name,
                    ref=planned_cell.ref,
                    expected=expected_value,
                    found=found_value,
                    detail=planned_cell.role,
                )
            )
        if expected_kind == "formula":
            found_formula = str(found["formula"])
            if planned_cell.formula != found_formula:
                findings.append(
                    EstimateAuditFinding(
                        code="CELL_FORMULA_MISMATCH",
                        sheet=plan.sheet_name,
                        ref=planned_cell.ref,
                        expected=planned_cell.formula,
                        found=found_formula,
                        detail=planned_cell.role,
                    )
                )

    for ref in sorted(set(found_cells) - planned_refs):
        findings.append(
            EstimateAuditFinding(
                code="CELL_UNEXPECTED",
                sheet=plan.sheet_name,
                ref=ref,
                found=str(found_cells[ref]["value"]),
                detail="célula presente no arquivo e ausente do plano",
            )
        )
    for sheet_name in sorted(set(_canonical_sheet_names(canonical)) - {plan.sheet_name}):
        findings.append(
            EstimateAuditFinding(
                code="SHEET_UNEXPECTED",
                sheet=sheet_name,
                detail="aba presente no arquivo e ausente do plano",
            )
        )

    return EstimateAuditReport(
        status="ok" if not findings else "divergent",
        workbook_sha256=_sha256(workbook_path),
        sheet_name=plan.sheet_name,
        checked_cells=len(plan.cells),
        formula_cells=plan.formula_cells,
        total_amount=estimate.total_amount,
        pinned_cells=plan.pinned_cells,
        findings=findings,
    )
