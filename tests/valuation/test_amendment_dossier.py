"""Dossiê do aditivo: instrui o pedido de aditivo de contrato (RE-RA), nunca precifica.

Aditivo é rejeição na CONFIRMAÇÃO DE CÓDIGO (`CodeAssignment.status == "rejected"`) de um
item CONFIRMADO no takeoff — nunca a rejeição na revisão do takeoff (item não medido).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

import pytest
from pydantic import ValidationError

from croquito_valuation.amendment_dossier import (
    AMENDMENT_DOSSIER_SCHEMA_VERSION,
    AmendmentDossier,
    AmendmentDossierItem,
    build_amendment_dossier,
)
from croquito_valuation.assignment import (
    CodeAssignment,
    CodeAssignmentSet,
    ItemPackageClosure,
)
from croquito_valuation.errors import ValuationValidationError, valuation_error_codes
from croquito_valuation.models import ReviewerDecision
from croquito_valuation.takeoff import (
    PlateBox,
    PlateEvidence,
    TakeoffItem,
    TakeoffItemStatus,
    TakeoffPacket,
)

_PLATE_ID = "praca-sintetica-norte-prancha-01"
_DIGEST = "a" * 64
_PDF_DIGEST = "b" * 64
_CATALOG_DIGEST = "c" * 64
_CONTRACT_DIGEST = "d" * 64
_REVIEWER = "orcamentista-sintetico"
_DECIDED_AT = datetime(2026, 2, 1, 12, 0, tzinfo=UTC)
_ITEM_1 = "ti_0000000000000001"
_ITEM_2 = "ti_0000000000000002"


def _evidence() -> PlateEvidence:
    return PlateEvidence(
        plate_id=_PLATE_ID,
        page_number=1,
        image_sha256=_DIGEST,
        bbox=PlateBox(left=10, top=10, right=110, bottom=60),
    )


def _confirmed_item(
    *,
    item_id: str = _ITEM_1,
    label: str = "GRAMADO SINTETICO",
    unit: str = "m2",
    quantity: Decimal = Decimal("58.50"),
    note: str | None = None,
) -> TakeoffItem:
    decision = ReviewerDecision(
        decision_id=f"vd_{item_id[3:]}",
        action="confirm",
        reviewer_id=_REVIEWER,
        reviewer_role="orcamentista",
        decided_at=_DECIDED_AT,
    )
    return TakeoffItem(
        id=item_id,
        evidence=_evidence(),
        raw_text=f"{label} {quantity} {unit}",
        label=label,
        quantity=quantity,
        unit=unit,
        source="legend_extraction",
        extractor="legend-extractor-sintetico",
        extractor_version="1.0.0",
        note=note,
        status=TakeoffItemStatus.CONFIRMED,
        decision=decision,
    )


def _packet(items: list[TakeoffItem] | None = None) -> TakeoffPacket:
    return TakeoffPacket(
        plate_id=_PLATE_ID,
        page_number=1,
        image_sha256=_DIGEST,
        source_pdf_sha256=_PDF_DIGEST,
        items=items if items is not None else [_confirmed_item()],
        safety_notes=[
            "Extração automática da legenda; quantidade não confirmada.",
            "Decisão do orçamentista obrigatória antes de qualquer boletim.",
        ],
    )


def _assignment(
    item_id: str,
    *,
    status: Literal["confirmed", "rejected"] = "rejected",
    code: str | None = None,
    note: str | None = "sem cotação aplicável no contrato sintético",
) -> CodeAssignment:
    action: Literal["confirm", "reject"] = "confirm" if status == "confirmed" else "reject"
    decision = ReviewerDecision(
        decision_id=f"vd_{item_id[3:]}",
        action=action,
        reviewer_id=_REVIEWER,
        reviewer_role="orcamentista",
        decided_at=_DECIDED_AT,
        note=note,
    )
    return CodeAssignment(
        item_id=item_id,
        status=status,
        code=code if status == "confirmed" else None,
        unit_compatible=status == "confirmed",
        decision=decision,
    )


def _assignment_set(
    packet: TakeoffPacket,
    assignments: list[CodeAssignment],
    *,
    catalog_sha256: str = _CATALOG_DIGEST,
    contract_sha256: str | None = _CONTRACT_DIGEST,
) -> CodeAssignmentSet:
    return CodeAssignmentSet(
        plate_id=packet.plate_id,
        page_number=packet.page_number,
        image_sha256=packet.image_sha256,
        catalog_sha256=catalog_sha256,
        contract_sha256=contract_sha256,
        assignments=assignments,
        # Fixture no regime de pacote (`2.0.0`): cada item confirmado nasce com o pacote
        # FECHADO, que é o que a orçamentista faz quando o elemento dispara um serviço só.
        # Sem isso o boletim recusaria em `CALC_PACKAGE_NOT_CLOSED`, e com razão.
        closures=[
            ItemPackageClosure(item_id=item.item_id, decision=item.decision)
            for item in assignments
            if item.status == "confirmed"
        ],
        safety_notes=[
            "Confirmação de código é ato humano rastreável; a sugestão lexical nunca "
            "confirma sozinha.",
            "Preço e unidade impressos continuam sendo conferidos contra catálogo e "
            "contrato no portão de exportação.",
        ],
    )


# --------------------------------------------------------------------------------------
# dossiê com rejeições: campos completos, ordem do packet
# --------------------------------------------------------------------------------------


def test_dossier_with_rejections_carries_full_fields_in_packet_order() -> None:
    lawn = _confirmed_item(
        item_id=_ITEM_1, label="GRAMADO SINTETICO", unit="m2", quantity=Decimal("58.50")
    )
    fence = _confirmed_item(
        item_id=_ITEM_2,
        label="ALAMBRADO SINTETICO",
        unit="m2",
        quantity=Decimal("40.00"),
        note="h=1.20m",
    )
    packet = _packet([lawn, fence])
    assignments = _assignment_set(
        packet,
        [
            _assignment(lawn.id, note="sem cotação aplicável no contrato sintético"),
            _assignment(fence.id, note="código do alambrado ausente do SCO publicado"),
        ],
    )

    dossier = build_amendment_dossier(packet, assignments)

    assert dossier.schema_version == AMENDMENT_DOSSIER_SCHEMA_VERSION
    assert dossier.plate_id == packet.plate_id
    assert dossier.page_number == packet.page_number
    assert dossier.image_sha256 == packet.image_sha256
    assert dossier.source_pdf_sha256 == packet.source_pdf_sha256
    assert dossier.catalog_sha256 == assignments.catalog_sha256
    assert dossier.contract_sha256 == assignments.contract_sha256
    assert len(dossier.safety_notes) >= 2

    assert [item.item_id for item in dossier.items] == [lawn.id, fence.id]

    first, second = dossier.items
    assert first.label == lawn.label
    assert first.raw_text == lawn.raw_text
    assert first.quantity == lawn.quantity
    assert first.unit == lawn.unit
    assert first.item_note is None
    assert first.justification == "sem cotação aplicável no contrato sintético"
    assert first.decision.action == "reject"
    assert first.evidence == lawn.evidence

    assert second.item_note == "h=1.20m"
    assert second.justification == "código do alambrado ausente do SCO publicado"


# --------------------------------------------------------------------------------------
# dossiê vazio é desfecho válido
# --------------------------------------------------------------------------------------


def test_dossier_without_any_rejection_is_valid_and_empty() -> None:
    item = _confirmed_item()
    packet = _packet([item])
    assignments = _assignment_set(
        packet, [_assignment(item.id, status="confirmed", code="AD04050060(/)")]
    )

    dossier = build_amendment_dossier(packet, assignments)

    assert dossier.items == []


def test_an_empty_dossier_is_a_valid_model_by_construction() -> None:
    dossier = AmendmentDossier(
        plate_id=_PLATE_ID,
        page_number=1,
        image_sha256=_DIGEST,
        source_pdf_sha256=_PDF_DIGEST,
        catalog_sha256=_CATALOG_DIGEST,
        contract_sha256=_CONTRACT_DIGEST,
        items=[],
        safety_notes=[
            "O dossiê não precifica nenhum item e não cria nem altera Amendment/RE-RA.",
            "A solicitação do aditivo à prefeitura é ato contratual humano, fora deste sistema.",
        ],
    )
    assert dossier.items == []


# --------------------------------------------------------------------------------------
# matriz de recusa: as quatro ordens do spec
# --------------------------------------------------------------------------------------


def test_a_packet_mismatch_between_assignments_and_packet_is_refused_first() -> None:
    item = _confirmed_item()
    packet = _packet([item])
    assignments = _assignment_set(packet, [_assignment(item.id)])
    other_assignments = assignments.model_copy(update={"plate_id": "outra-prancha"})

    with pytest.raises(ValuationValidationError) as raised:
        build_amendment_dossier(packet, other_assignments)

    assert raised.value.code == "AMENDMENT_DOSSIER_PACKET_MISMATCH"


def test_an_assignment_for_an_item_not_confirmed_in_the_takeoff_is_refused() -> None:
    item = _confirmed_item()
    packet = _packet([item])
    assignments = _assignment_set(
        packet,
        [_assignment(item.id), _assignment("ti_ffffffffffffffff")],
    )

    with pytest.raises(ValuationValidationError) as raised:
        build_amendment_dossier(packet, assignments)

    assert raised.value.code == "AMENDMENT_DOSSIER_UNKNOWN_ITEM"
    assert raised.value.details["item_ids"] == ["ti_ffffffffffffffff"]


def test_a_confirmed_item_without_a_code_assignment_is_refused() -> None:
    item = _confirmed_item()
    packet = _packet([item])
    assignments = _assignment_set(packet, [])

    with pytest.raises(ValuationValidationError) as raised:
        build_amendment_dossier(packet, assignments)

    assert raised.value.code == "AMENDMENT_DOSSIER_ASSIGNMENTS_INCOMPLETE"
    assert raised.value.details["item_ids"] == [item.id]


def test_a_rejection_without_a_justification_note_is_refused() -> None:
    item = _confirmed_item()
    packet = _packet([item])
    # `note=None` só é alcançável construindo o `CodeAssignment` diretamente: o domínio de
    # confirmação (`CodeAssignmentInput.note`) já exige `min_length=1` quando presente, mas
    # não torna a nota obrigatória — é o dossiê que a exige.
    assignments = _assignment_set(packet, [_assignment(item.id, note=None)])

    with pytest.raises(ValuationValidationError) as raised:
        build_amendment_dossier(packet, assignments)

    assert raised.value.code == "AMENDMENT_DOSSIER_JUSTIFICATION_MISSING"
    assert raised.value.details["item_ids"] == [item.id]


# --------------------------------------------------------------------------------------
# rejeição na revisão do takeoff não é aditivo (não entra aqui)
# --------------------------------------------------------------------------------------


def test_a_takeoff_rejection_never_reaches_the_dossier_because_it_is_not_confirmed() -> None:
    """Item rejeitado na revisão do takeoff (ex.: área de intervenção) nunca aparece em
    `confirmed_items()`, então nunca pode ganhar assignment nem entrar no dossiê."""
    rejected_decision = ReviewerDecision(
        decision_id=f"vd_{_ITEM_1[3:]}",
        action="reject",
        reviewer_id=_REVIEWER,
        reviewer_role="orcamentista",
        decided_at=_DECIDED_AT,
        note="área de referência da prancha",
    )
    takeoff_rejected = TakeoffItem(
        id=_ITEM_1,
        evidence=_evidence(),
        raw_text="AREA DE INTERVENCAO",
        label="AREA DE INTERVENCAO",
        quantity=None,
        unit="m2",
        source="legend_extraction",
        extractor="legend-extractor-sintetico",
        extractor_version="1.0.0",
        status=TakeoffItemStatus.REJECTED,
        decision=rejected_decision,
    )
    packet = _packet([takeoff_rejected])
    assignments = _assignment_set(packet, [])

    dossier = build_amendment_dossier(packet, assignments)

    assert dossier.items == []


# --------------------------------------------------------------------------------------
# duplicidade de item no dossiê recusa (defesa do modelo)
# --------------------------------------------------------------------------------------


def test_duplicated_item_ids_in_a_dossier_are_refused_by_construction() -> None:
    item = AmendmentDossierItem(
        item_id=_ITEM_1,
        label="GRAMADO SINTETICO",
        raw_text="GRAMADO SINTETICO 58.50 m2",
        quantity=Decimal("58.50"),
        unit="m2",
        justification="sem cotação aplicável",
        decision=ReviewerDecision(
            decision_id=f"vd_{_ITEM_1[3:]}",
            action="reject",
            reviewer_id=_REVIEWER,
            reviewer_role="orcamentista",
            decided_at=_DECIDED_AT,
            note="sem cotação aplicável",
        ),
        evidence=_evidence(),
    )

    with pytest.raises(ValidationError) as raised:
        AmendmentDossier(
            plate_id=_PLATE_ID,
            page_number=1,
            image_sha256=_DIGEST,
            source_pdf_sha256=_PDF_DIGEST,
            catalog_sha256=_CATALOG_DIGEST,
            contract_sha256=_CONTRACT_DIGEST,
            items=[item, item],
            safety_notes=[
                "O dossiê não precifica nenhum item e não cria nem altera Amendment/RE-RA.",
                "A solicitação do aditivo à prefeitura é ato contratual humano.",
            ],
        )

    assert valuation_error_codes(raised.value) == ["AMENDMENT_DOSSIER_DUPLICATE_ITEM"]


def test_a_dossier_item_with_an_incoherent_decision_is_refused_by_construction() -> None:
    """Um dossiê adulterado fora do builder não sobrevive à revalidação do modelo: o item
    exige decisão de rejeição e justificativa idêntica à nota da decisão (mesmo desenho de
    `CodeAssignment.validate_state`)."""
    base_kwargs = {
        "item_id": _ITEM_1,
        "label": "GRAMADO SINTETICO",
        "raw_text": "GRAMADO SINTETICO 58.50 m2",
        "quantity": Decimal("58.50"),
        "unit": "m2",
        "justification": "sem cotação aplicável",
        "evidence": _evidence(),
    }

    confirm_decision = ReviewerDecision(
        decision_id=f"vd_{_ITEM_1[3:]}",
        action="confirm",
        reviewer_id=_REVIEWER,
        reviewer_role="orcamentista",
        decided_at=_DECIDED_AT,
        note="sem cotação aplicável",
    )
    with pytest.raises(ValidationError) as raised:
        AmendmentDossierItem(decision=confirm_decision, **base_kwargs)
    assert valuation_error_codes(raised.value) == ["AMENDMENT_DOSSIER_ITEM_STATE_INVALID"]

    divergent_note_decision = ReviewerDecision(
        decision_id=f"vd_{_ITEM_1[3:]}",
        action="reject",
        reviewer_id=_REVIEWER,
        reviewer_role="orcamentista",
        decided_at=_DECIDED_AT,
        note="outra nota que não é a justificativa",
    )
    with pytest.raises(ValidationError) as raised:
        AmendmentDossierItem(decision=divergent_note_decision, **base_kwargs)
    assert valuation_error_codes(raised.value) == ["AMENDMENT_DOSSIER_ITEM_STATE_INVALID"]


# --------------------------------------------------------------------------------------
# assert estrutural: o JSON serializado nunca carrega chave de preço
# --------------------------------------------------------------------------------------


def test_the_serialized_dossier_never_carries_a_price_key() -> None:
    lawn = _confirmed_item()
    packet = _packet([lawn])
    assignments = _assignment_set(
        packet, [_assignment(lawn.id, note="sem cotação aplicável no contrato sintético")]
    )

    dossier = build_amendment_dossier(packet, assignments)

    document = json.loads(dossier.model_dump_json())

    def _walk(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                assert key not in {"unit_price", "total", "price", "amount"}, key
                _walk(value)
        elif isinstance(node, list):
            for value in node:
                _walk(value)

    _walk(document)
