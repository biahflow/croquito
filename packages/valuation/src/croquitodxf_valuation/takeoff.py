"""Contrato de takeoff (quantitativo da legenda) e decisão do orçamentista.

A prancha do projetista chega com a legenda já quantificada (pisos em m², alambrados em
m com altura anotada, mobiliário em unidades, área de intervenção). A extração dessa
legenda produz *observações* — `TakeoffItem`s sempre `proposed` ou `ambiguous` — que só
viram quantitativo com uma decisão humana rastreável (`ReviewerDecision`).

Este módulo é um espelho deliberado de `ReviewPacket`/`DimensionReading`
(`croquitodxf_worker.review`): mesma forma de pacote de revisão, mesmo ciclo
proposed/ambiguous → confirmed/rejected, mesma aplicação imutável de decisões. O
`ADR-0016` proíbe importar do worker; a duplicação de forma é proposital, como já
acontece com `ReviewerDecision` frente a `HumanDecision` — o que se repete é o formato
do ato de revisão, não o significado dele.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Final, Literal

from pydantic import Field, field_validator, model_validator

from croquitodxf_valuation.errors import ValuationValidationError
from croquitodxf_valuation.models import (
    SHA256_PATTERN,
    ExactDecimal,
    ReviewerDecision,
    ValuationContractModel,
)

TAKEOFF_SCHEMA_VERSION: Final = "1.0.0"


class TakeoffItemStatus(StrEnum):
    """Espelho de `ReadingStatus`: estado de revisão de uma linha da legenda.

    `AMBIGUOUS` é a linha cuja extração identificou o elemento mas não conseguiu ler a
    quantidade — por isso ela nunca carrega `quantity`.
    """

    PROPOSED = "proposed"
    AMBIGUOUS = "ambiguous"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class PlateBox(ValuationContractModel):
    """Espelho de `PixelBox`: recorte em pixels da prancha onde o item foi lido."""

    left: int = Field(ge=0)
    top: int = Field(ge=0)
    right: int = Field(gt=0)
    bottom: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_bounds(self) -> PlateBox:
        if self.right <= self.left or self.bottom <= self.top:
            raise ValuationValidationError(
                "TAKEOFF_BBOX_INVALID",
                "bbox do takeoff deve possuir área positiva",
                {
                    "left": self.left,
                    "top": self.top,
                    "right": self.right,
                    "bottom": self.bottom,
                },
            )
        return self


class PlateEvidence(ValuationContractModel):
    """Espelho de `EvidenceRegion`: âncora da prancha para a linha da legenda lida."""

    plate_id: str = Field(min_length=1, max_length=64)
    page_number: int = Field(ge=1)
    image_sha256: str = Field(pattern=SHA256_PATTERN)
    coordinate_space: Literal["source_image_pixels"] = "source_image_pixels"
    bbox: PlateBox


class TakeoffItem(ValuationContractModel):
    """Uma linha da legenda quantificada, do estado observado ao confirmado pelo orçamentista.

    Espelho de `DimensionReading`. `source` é a porta discriminada reservada no roadmap
    (`docs/product/ROADMAP.md`) para quando o quantitativo puder nascer do scene graph
    aprovado em vez da extração de legenda.
    """

    id: str = Field(pattern=r"^ti_[a-f0-9]{16}$")
    evidence: PlateEvidence
    raw_text: str = Field(min_length=1, max_length=300)
    label: str = Field(min_length=1, max_length=200)
    quantity: ExactDecimal | None = Field(default=None, gt=0)
    unit: str = Field(min_length=1, max_length=20)
    source: Literal["legend_extraction", "manual"]
    extractor: str = Field(min_length=1, max_length=80)
    extractor_version: str = Field(min_length=1, max_length=80)
    note: str | None = Field(default=None, max_length=300)
    status: TakeoffItemStatus
    decision: ReviewerDecision | None = None

    @model_validator(mode="after")
    def validate_review_state(self) -> TakeoffItem:
        if self.status is TakeoffItemStatus.CONFIRMED:
            if self.quantity is None or self.decision is None:
                raise ValuationValidationError(
                    "TAKEOFF_ITEM_CONFIRMED_INCOMPLETE",
                    "item confirmado exige quantidade e decisão do orçamentista",
                    {"id": self.id},
                )
            if self.decision.action != "confirm":
                raise ValuationValidationError(
                    "TAKEOFF_ITEM_CONFIRMED_INCOMPLETE",
                    "decisão de item confirmado deve ser confirm",
                    {"id": self.id},
                )
        elif self.status is TakeoffItemStatus.REJECTED:
            if self.decision is None or self.decision.action != "reject":
                raise ValuationValidationError(
                    "TAKEOFF_ITEM_REJECTED_WITHOUT_DECISION",
                    "item rejeitado exige decisão do orçamentista reject",
                    {"id": self.id},
                )
        elif self.status is TakeoffItemStatus.AMBIGUOUS:
            if self.decision is not None:
                raise ValuationValidationError(
                    "TAKEOFF_ITEM_UNREVIEWED_WITH_DECISION",
                    "item ainda não revisado não pode carregar decisão do orçamentista",
                    {"id": self.id},
                )
            if self.quantity is not None:
                raise ValuationValidationError(
                    "TAKEOFF_ITEM_AMBIGUOUS_WITH_QUANTITY",
                    "item ambíguo é a linha sem quantidade legível; não pode carregar quantidade",
                    {"id": self.id},
                )
        elif self.decision is not None:
            raise ValuationValidationError(
                "TAKEOFF_ITEM_UNREVIEWED_WITH_DECISION",
                "item ainda não revisado não pode carregar decisão do orçamentista",
                {"id": self.id},
            )
        return self


class TakeoffPacket(ValuationContractModel):
    """Pacote de takeoff de uma prancha: espelho de `ReviewPacket`.

    O JSON canônico é a fonte de verdade da extração; `safety_status` fixo lembra que a
    decisão do orçamentista continua obrigatória e nada aqui é quantitativo aprovado.
    """

    schema_version: Literal["1.0.0"] = TAKEOFF_SCHEMA_VERSION
    plate_id: str = Field(min_length=1, max_length=64)
    page_number: int = Field(ge=1)
    image_sha256: str = Field(pattern=SHA256_PATTERN)
    source_pdf_sha256: str = Field(pattern=SHA256_PATTERN)
    items: list[TakeoffItem] = Field(min_length=1)
    safety_status: Literal["human_review_required"] = "human_review_required"
    safety_notes: list[str] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_references(self) -> TakeoffPacket:
        item_ids = [item.id for item in self.items]
        if len(item_ids) != len(set(item_ids)):
            raise ValuationValidationError(
                "TAKEOFF_DUPLICATE_ITEM_ID",
                "IDs de item de takeoff devem ser únicos",
                {"ids": sorted(item_ids)},
            )
        for item in self.items:
            evidence = item.evidence
            if (
                evidence.plate_id != self.plate_id
                or evidence.page_number != self.page_number
                or evidence.image_sha256 != self.image_sha256
            ):
                raise ValuationValidationError(
                    "TAKEOFF_EVIDENCE_MISMATCH",
                    "evidência do item diverge da prancha do pacote",
                    {
                        "id": item.id,
                        "plate_id": evidence.plate_id,
                        "page_number": evidence.page_number,
                        "image_sha256": evidence.image_sha256,
                    },
                )
        return self

    def pending_items(self) -> list[TakeoffItem]:
        """Itens ainda não decididos pelo orçamentista (`proposed` ou `ambiguous`)."""
        return [
            item
            for item in self.items
            if item.status in {TakeoffItemStatus.PROPOSED, TakeoffItemStatus.AMBIGUOUS}
        ]

    def confirmed_items(self) -> list[TakeoffItem]:
        """Itens confirmados pelo orçamentista."""
        return [item for item in self.items if item.status is TakeoffItemStatus.CONFIRMED]


class TakeoffDecisionInput(ValuationContractModel):
    """Decisão do orçamentista sobre um item de takeoff; espelho de `ReadingDecisionInput`.

    `note` é o comentário do revisor sobre a própria decisão; `item_note` corrige a
    anotação que acompanha o item na legenda (ex.: `h=1.00m`). São campos distintos
    porque respondem a perguntas distintas — um documenta o ato de revisão, o outro
    corrige o dado do item.
    """

    item_id: str = Field(pattern=r"^ti_[a-f0-9]{16}$")
    action: Literal["confirm", "reject"]
    reviewer_id: str = Field(min_length=1, max_length=120)
    reviewer_role: Literal["orcamentista"]
    decided_at: datetime
    note: str | None = Field(default=None, max_length=500)
    raw_text: str | None = Field(default=None, min_length=1, max_length=300)
    label: str | None = Field(default=None, min_length=1, max_length=200)
    quantity: ExactDecimal | None = Field(default=None, gt=0)
    unit: str | None = Field(default=None, min_length=1, max_length=20)
    item_note: str | None = Field(default=None, max_length=300)

    @field_validator("decided_at")
    @classmethod
    def validate_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValuationValidationError(
                "TAKEOFF_DECISION_TIMESTAMP_NAIVE",
                "decisão de takeoff exige data e hora com fuso horário",
                {"decided_at": value.isoformat()},
            )
        return value


class TakeoffDecisionBatch(ValuationContractModel):
    """Espelho de `ReadingDecisionBatch`: no máximo uma decisão por item por lote."""

    decisions: list[TakeoffDecisionInput] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_items(self) -> TakeoffDecisionBatch:
        ids = [decision.item_id for decision in self.decisions]
        if len(ids) != len(set(ids)):
            raise ValuationValidationError(
                "TAKEOFF_DECISION_DUPLICATE_ITEM",
                "um item de takeoff só pode receber uma decisão por lote",
                {"ids": sorted(ids)},
            )
        return self


def _decision_id(item: TakeoffItem, decision: TakeoffDecisionInput) -> str:
    """Id determinístico da decisão: espelho de `_decision_id` do worker, prefixo `vd_`."""
    canonical = json.dumps(
        {
            "item_id": item.id,
            "action": decision.action,
            "reviewer_id": decision.reviewer_id,
            "reviewer_role": decision.reviewer_role,
            "decided_at": decision.decided_at.isoformat(),
            "raw_text": decision.raw_text,
            "label": decision.label,
            "quantity": str(decision.quantity) if decision.quantity is not None else None,
            "unit": decision.unit,
            "item_note": decision.item_note,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"vd_{hashlib.sha256(canonical.encode()).hexdigest()[:16]}"


def apply_takeoff_decisions(
    packet: TakeoffPacket,
    batch: TakeoffDecisionBatch,
) -> TakeoffPacket:
    """Cria um novo pacote imutável de takeoff; nunca altera o pacote de entrada.

    Confirmar um item `ambiguous` exige `quantity` no input: sem ela, a reconstrução do
    item cai no validador de estado e sobe `TAKEOFF_ITEM_CONFIRMED_INCOMPLETE` — o erro
    do modelo, não uma pré-checagem duplicada aqui.
    """
    decisions = {decision.item_id: decision for decision in batch.decisions}
    known_ids = {item.id for item in packet.items}
    unknown_ids = sorted(set(decisions) - known_ids)
    if unknown_ids:
        raise ValuationValidationError(
            "TAKEOFF_DECISION_UNKNOWN_ITEM",
            "decisão aponta para item de takeoff desconhecido",
            {"unknown_ids": unknown_ids},
        )

    updated_items: list[TakeoffItem] = []
    for item in packet.items:
        input_decision = decisions.get(item.id)
        if input_decision is None:
            updated_items.append(item)
            continue
        if item.status in {TakeoffItemStatus.CONFIRMED, TakeoffItemStatus.REJECTED}:
            raise ValuationValidationError(
                "TAKEOFF_ITEM_ALREADY_REVIEWED",
                "item de takeoff já revisado não pode ser sobrescrito",
                {"id": item.id},
            )
        reviewer_decision = ReviewerDecision(
            decision_id=_decision_id(item, input_decision),
            action=input_decision.action,
            reviewer_id=input_decision.reviewer_id,
            reviewer_role=input_decision.reviewer_role,
            decided_at=input_decision.decided_at,
            note=input_decision.note,
        )
        update = {
            "raw_text": input_decision.raw_text or item.raw_text,
            "label": input_decision.label or item.label,
            "quantity": (
                input_decision.quantity if input_decision.quantity is not None else item.quantity
            ),
            "unit": input_decision.unit or item.unit,
            "note": input_decision.item_note or item.note,
            "status": (
                TakeoffItemStatus.CONFIRMED
                if input_decision.action == "confirm"
                else TakeoffItemStatus.REJECTED
            ),
            "decision": reviewer_decision,
        }
        updated_items.append(TakeoffItem.model_validate({**item.model_dump(), **update}))

    return TakeoffPacket.model_validate(
        {
            **packet.model_dump(),
            "items": updated_items,
            "safety_notes": [
                *packet.safety_notes,
                (
                    "Decisões do orçamentista aplicadas; propostas originais permanecem "
                    "no histórico de entrada."
                ),
            ],
        }
    )


def load_takeoff_packet(path: Path) -> TakeoffPacket:
    """Espelho de `load_review_packet`: lê o pacote de takeoff do JSON canônico."""
    return TakeoffPacket.model_validate_json(path.read_text(encoding="utf-8"))
