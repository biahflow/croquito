"""Eval determinística do takeoff da legenda: recall da fixture + gate do contrato.

Espelho de `vision_eval`/`solver_eval`: fixture sintética, relatório Pydantic fechado
(`extra="forbid"`) com `passed`, e JSON publicado atomicamente. A eval gera a mesma
prancha sintética que `extract-legend` gera, mede o recall da legenda contra
`SYNTHETIC_LEGEND_ROWS` e EXERCITA de verdade — não só lê o resultado do caminho feliz —
os invariantes que o domínio promete: nenhum item nasce confirmado, a linha ilegível vira
o único item ambíguo sem quantidade, o pacote fica amarrado por digest à prancha,
re-decisão sobre um item já revisado é recusada, confirmar o ambíguo sem informar
quantidade é recusado, revisar todos os itens pendentes zera `pending_items()` com
decisão rastreável em cada um, e uma prancha adulterada depois de gerada é recusada pela
extração.

Honestidade: esta eval valida a fixture sintética e o CONTRATO do fluxo de revisão do
takeoff, não precisão de extração numa prancha real de cliente — isso é marco futuro,
pago e com gates próprios (mesma ressalva de `docs/STATUS.md` para a eval de visão
sintética: "Isso valida a fixture, não precisão nos PDFs reais").
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from croquitodxf_valuation.catalog import normalize_unit
from croquitodxf_valuation.errors import ValuationValidationError, valuation_error_codes
from croquitodxf_valuation.takeoff import (
    TakeoffDecisionBatch,
    TakeoffDecisionInput,
    TakeoffItem,
    TakeoffItemStatus,
    TakeoffPacket,
    apply_takeoff_decisions,
)
from croquitodxf_worker.io_utils import atomic_write_text
from croquitodxf_worker.valuation.plate import (
    SYNTHETIC_LEGEND_ROWS,
    LegendRow,
    PlateArtifacts,
    render_synthetic_plate,
)
from croquitodxf_worker.valuation.takeoff_fixture import (
    FIXTURE_EXTRACTOR,
    FIXTURE_EXTRACTOR_VERSION,
    extract_takeoff_fixture,
)

_EVAL_REVIEWER_ID: Final = "orcamentista-eval-sintetico"
_EVAL_DECIDED_AT: Final = datetime(2026, 2, 1, 12, 0, tzinfo=UTC)
_EVAL_REDECISION_AT: Final = datetime(2026, 2, 2, 9, 0, tzinfo=UTC)
_EVAL_AMBIGUOUS_QUANTITY: Final = Decimal("18.40")
"""Quantidade informada pelo orçamentista sintético para a linha ilegível: ato humano
suprindo o que a extração não conseguiu ler, nunca derivada da prancha."""

_TAMPERED_IMAGE_FILENAME: Final = "takeoff-eval-tampered.png"

_REPORT_FILENAME: Final = "takeoff-eval.json"


class TakeoffEvalReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plate_id: str
    extractor: str
    extractor_version: str
    item_count: int = Field(ge=0)
    legend_recall: float = Field(ge=0, le=1)
    checks: dict[str, bool]
    thresholds: dict[str, float]
    passed: bool


def matches_gabarito(row: LegendRow, item: TakeoffItem) -> bool:
    """Um item extraído casa com a linha do gabarito por rótulo, unidade e quantidade.

    A linha ilegível (`row.quantity is None`) só casa com o item `ambiguous` sem
    quantidade — é exatamente essa ausência que o gabarito espera dela.

    É público porque a eval da extração paga (`valuation.extraction_eval`) mede o mesmo
    recall sobre a mesma prancha: duas definições de "casou" divergiriam e um dos dois
    números passaria a mentir.
    """
    if item.label != row.label or item.unit != normalize_unit(row.unit):
        return False
    if row.quantity is None:
        return item.status is TakeoffItemStatus.AMBIGUOUS and item.quantity is None
    return item.quantity == row.quantity


def legend_recall(proposed: TakeoffPacket) -> float:
    """Fração das linhas do gabarito sintético que o pacote extraído reproduz."""
    matched = sum(
        any(matches_gabarito(row, item) for item in proposed.items) for row in SYNTHETIC_LEGEND_ROWS
    )
    return matched / len(SYNTHETIC_LEGEND_ROWS)


def _confirm_decision(
    item_id: str, *, decided_at: datetime, quantity: Decimal | None = None
) -> TakeoffDecisionInput:
    return TakeoffDecisionInput(
        item_id=item_id,
        action="confirm",
        reviewer_id=_EVAL_REVIEWER_ID,
        reviewer_role="orcamentista",
        decided_at=decided_at,
        quantity=quantity,
    )


def _check_re_decision_refused(proposed: TakeoffPacket, first_proposed: TakeoffItem) -> bool:
    """Confirma um item e reaplica uma segunda decisão sobre ele: a segunda deve recusar."""
    once_reviewed = apply_takeoff_decisions(
        proposed,
        TakeoffDecisionBatch(
            decisions=[_confirm_decision(first_proposed.id, decided_at=_EVAL_DECIDED_AT)]
        ),
    )
    try:
        apply_takeoff_decisions(
            once_reviewed,
            TakeoffDecisionBatch(
                decisions=[_confirm_decision(first_proposed.id, decided_at=_EVAL_REDECISION_AT)]
            ),
        )
    except ValuationValidationError as error:
        return error.code == "TAKEOFF_ITEM_ALREADY_REVIEWED"
    return False


def _check_ambiguous_needs_informed_quantity(
    proposed: TakeoffPacket, ambiguous_item: TakeoffItem
) -> bool:
    """Confirmar o ambíguo sem quantidade recusa; o erro chega embrulhado pelo Pydantic."""
    try:
        apply_takeoff_decisions(
            proposed,
            TakeoffDecisionBatch(
                decisions=[_confirm_decision(ambiguous_item.id, decided_at=_EVAL_DECIDED_AT)]
            ),
        )
    except ValidationError as error:
        return "TAKEOFF_ITEM_CONFIRMED_INCOMPLETE" in valuation_error_codes(error)
    return False


def _check_review_completes_with_decisions(proposed: TakeoffPacket) -> bool:
    """Confirma todo item pendente (ambíguo com quantidade explícita) e fecha a revisão."""
    batch = TakeoffDecisionBatch(
        decisions=[
            _confirm_decision(
                item.id,
                decided_at=_EVAL_DECIDED_AT,
                quantity=(
                    _EVAL_AMBIGUOUS_QUANTITY if item.status is TakeoffItemStatus.AMBIGUOUS else None
                ),
            )
            for item in proposed.pending_items()
        ]
    )
    reviewed = apply_takeoff_decisions(proposed, batch)
    return reviewed.pending_items() == [] and all(
        item.decision is not None and item.decision.decision_id.startswith("vd_")
        for item in reviewed.items
    )


def _check_tampered_render_refused(output_dir: Path, plate: PlateArtifacts) -> bool:
    """Copia o PNG, altera 1 byte e confere que a extração recusa a prancha adulterada."""
    tampered_path = output_dir / _TAMPERED_IMAGE_FILENAME
    original_bytes = bytearray(plate.image_path.read_bytes())
    original_bytes[0] = (original_bytes[0] + 1) % 256
    tampered_path.write_bytes(bytes(original_bytes))
    tampered_artifacts = replace(plate, image_path=tampered_path)
    try:
        extract_takeoff_fixture(tampered_artifacts)
    except ValuationValidationError as error:
        return error.code == "TAKEOFF_FIXTURE_ARTIFACT_MISMATCH"
    return False


def run_takeoff_eval(output_dir: Path) -> tuple[TakeoffEvalReport, Path]:
    """Gera a prancha sintética, extrai a legenda e exercita os invariantes de revisão."""
    output_dir.mkdir(parents=True, exist_ok=True)
    plate = render_synthetic_plate(output_dir)
    proposed = extract_takeoff_fixture(plate)

    ambiguous_items = [
        item for item in proposed.items if item.status is TakeoffItemStatus.AMBIGUOUS
    ]
    illegible_rows = [row for row in SYNTHETIC_LEGEND_ROWS if row.quantity is None]
    first_proposed = next(
        item for item in proposed.items if item.status is TakeoffItemStatus.PROPOSED
    )

    checks: dict[str, bool] = {
        "no_item_born_confirmed": all(
            item.status in {TakeoffItemStatus.PROPOSED, TakeoffItemStatus.AMBIGUOUS}
            for item in proposed.items
        ),
        "ambiguous_without_quantity": (
            len(ambiguous_items) == len(illegible_rows)
            and {item.label for item in ambiguous_items} == {row.label for row in illegible_rows}
            and all(item.quantity is None for item in ambiguous_items)
        ),
        "evidence_bound_to_render": (
            proposed.image_sha256 == plate.image_sha256
            and proposed.source_pdf_sha256 == plate.pdf_sha256
        ),
        "re_decision_refused": _check_re_decision_refused(proposed, first_proposed),
        "ambiguous_needs_informed_quantity": _check_ambiguous_needs_informed_quantity(
            proposed, ambiguous_items[0]
        ),
        "review_completes_with_decisions": _check_review_completes_with_decisions(proposed),
        "tampered_render_refused": _check_tampered_render_refused(output_dir, plate),
    }

    recall = legend_recall(proposed)
    thresholds = {"legend_recall": 1.0}
    report = TakeoffEvalReport(
        plate_id=plate.plate_id,
        extractor=FIXTURE_EXTRACTOR,
        extractor_version=FIXTURE_EXTRACTOR_VERSION,
        item_count=len(proposed.items),
        legend_recall=recall,
        checks=checks,
        thresholds=thresholds,
        passed=recall >= thresholds["legend_recall"] and all(checks.values()),
    )
    report_path = output_dir / _REPORT_FILENAME
    serialized_report = json.dumps(
        report.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    atomic_write_text(report_path, f"{serialized_report}\n")
    return report, report_path
