"""Contrato de revisão de leituras, separado das propostas geométricas em pixels."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from croquito_core.models import MeasurementKind, UnitCode
from croquito_worker.criteria import CRITERION_CODE_PATTERN
from croquito_worker.io_utils import atomic_write_text

CriterionCode = Annotated[str, Field(pattern=CRITERION_CODE_PATTERN)]


class ReviewModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        allow_inf_nan=False,
        str_strip_whitespace=True,
    )


class ReadingStatus(StrEnum):
    PROPOSED = "proposed"
    AMBIGUOUS = "ambiguous"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class PixelBox(ReviewModel):
    left: int = Field(ge=0)
    top: int = Field(ge=0)
    right: int = Field(gt=0)
    bottom: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_bounds(self) -> PixelBox:
        if self.right <= self.left or self.bottom <= self.top:
            raise ValueError("bbox deve possuir área positiva")
        return self


class EvidenceRegion(ReviewModel):
    dataset_id: str = Field(min_length=1, max_length=64)
    page_number: int = Field(ge=1)
    image_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    coordinate_space: Literal["source_image_pixels"] = "source_image_pixels"
    bbox: PixelBox


class RegionCandidate(ReviewModel):
    """A provider-proposed page role; it has no coordinate-system authority."""

    id: str = Field(pattern=r"^rg_[a-f0-9]{16}$")
    kind: Literal["main_plan", "detail", "material_list", "annotation_cluster", "unknown"]
    label: str = Field(min_length=1, max_length=120)
    evidence: str = Field(min_length=1, max_length=300)
    polygon: list[tuple[float, float]] = Field(min_length=1)


class HumanDecision(ReviewModel):
    decision_id: str = Field(pattern=r"^hd_[a-f0-9]{16}$")
    action: Literal["confirm", "reject"]
    reviewer_id: str = Field(min_length=1, max_length=120)
    reviewer_role: Literal["engineer", "architect", "domain_reviewer"]
    decided_at: datetime
    note: str | None = Field(default=None, max_length=500)
    # Sucessão declarada: esta decisão substitui a anterior por um ato humano novo, e
    # nunca a apaga — a anterior continua na revisão parental. Ausente na primeira
    # decisão de uma leitura, e ausente em todo pacote gravado antes da retificação.
    rectifies_decision_id: str | None = Field(default=None, pattern=r"^hd_[a-f0-9]{16}$")

    @field_validator("decided_at")
    @classmethod
    def validate_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("decided_at exige timezone")
        return value

    @model_validator(mode="after")
    def validate_rectification(self) -> HumanDecision:
        if self.rectifies_decision_id is None:
            return self
        if self.note is None or len(self.note.strip()) < 3:
            raise ValueError("retificação de decisão exige justificativa escrita")
        return self


class ProviderLineage(ReviewModel):
    """Metadata needed to reproduce a provider observation without retaining its payload."""

    provider: str = Field(min_length=1, max_length=80)
    model_id: str = Field(min_length=1, max_length=160)
    prompt_id: str = Field(min_length=1, max_length=80)
    prompt_version: str = Field(min_length=1, max_length=40)
    prompt_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    schema_version: str = Field(min_length=1, max_length=40)
    input_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    latency_ms: int = Field(ge=0)
    # Chave privada da resposta bruta no object store, nunca o payload. Sem ela a
    # resposta é gravada e depois se torna irrecuperável a partir do banco.
    raw_response_ref: str | None = Field(default=None, max_length=400)
    # Opcionais e retrocompatíveis (F-031 T1): pacote antigo sem estes campos continua
    # carregando com `None` — nenhum replay quebra. `Decimal` serializa como string em
    # `model_dump(mode="json")`, o padrão do repo para valor monetário exato.
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    estimated_cost_usd: Decimal | None = Field(default=None, ge=0)


class DimensionReading(ReviewModel):
    id: str = Field(pattern=r"^rd_[a-f0-9]{16}$")
    evidence: EvidenceRegion
    raw_text: str = Field(min_length=1, max_length=200)
    value_si: Decimal | None = Field(default=None, gt=0)
    unit: UnitCode
    kind: MeasurementKind
    written_decimals: int = Field(ge=0, le=8)
    target_hint: str | None = Field(default=None, min_length=1, max_length=120)
    extractor: str = Field(min_length=1, max_length=80)
    extractor_version: str = Field(min_length=1, max_length=80)
    provider_lineage: list[ProviderLineage] = Field(default_factory=list, max_length=4)
    # Sinal do provider (kind="note" completo). Default False preserva pacotes
    # persistidos antigos em ReviewPacket.model_validate(record.packet_json) — nenhum
    # outro campo muda.
    annotation_suggested: bool = False
    # Registro de NASCIMENTO da corroboração por OCR, não recálculo vivo: True = o OCR
    # leu o mesmo texto na mesma região; False = o OCR rodou e não encontrou; None =
    # braço ausente/falhou (mesmo tratamento) ou pacote persistido antigo sem o campo.
    # Uma retificação posterior da leitura não reescreve este valor.
    ocr_corroborated: bool | None = None
    status: ReadingStatus
    decision: HumanDecision | None = None

    @model_validator(mode="after")
    def validate_review_state(self) -> DimensionReading:
        if self.unit not in {UnitCode.METRE, UnitCode.MILLIMETRE}:
            raise ValueError("leitura dimensional aceita somente m ou mm")
        if self.status is ReadingStatus.CONFIRMED:
            if self.value_si is None or self.decision is None:
                raise ValueError("leitura confirmada exige valor e decisão humana")
            if self.decision.action != "confirm":
                raise ValueError("decisão de leitura confirmada deve ser confirm")
        elif self.status is ReadingStatus.REJECTED:
            if self.decision is None or self.decision.action != "reject":
                raise ValueError("leitura rejeitada exige decisão humana reject")
        elif self.decision is not None:
            raise ValueError("proposta não revisada não pode carregar decisão humana")
        return self


class ReviewPacket(ReviewModel):
    schema_version: Literal["1.0.0", "1.1.0"] = "1.1.0"
    dataset_id: str = Field(min_length=1, max_length=64)
    page_number: int = Field(ge=1)
    image_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    region_candidates: list[RegionCandidate] = Field(default_factory=list)
    readings: list[DimensionReading]
    safety_status: Literal["human_review_required"] = "human_review_required"
    safety_notes: list[str] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_references(self) -> ReviewPacket:
        reading_ids = [reading.id for reading in self.readings]
        if len(reading_ids) != len(set(reading_ids)):
            raise ValueError("IDs de leitura devem ser únicos")
        for reading in self.readings:
            evidence = reading.evidence
            if evidence.dataset_id != self.dataset_id:
                raise ValueError("dataset da evidência diverge do pacote")
            if evidence.page_number != self.page_number:
                raise ValueError("página da evidência diverge do pacote")
            if evidence.image_sha256 != self.image_sha256:
                raise ValueError("digest da evidência diverge do pacote")
        return self


class SceneApproval(ReviewModel):
    approval_id: str = Field(pattern=r"^ap_[a-f0-9]{16}$")
    source_scene_id: UUID
    action: Literal["approve"] = "approve"
    reviewer_id: str = Field(min_length=1, max_length=120)
    reviewer_role: Literal["engineer", "architect", "domain_reviewer"]
    decided_at: datetime
    source_evidence_checked: Literal[True]
    geometry_checked: Literal[True]
    limitations_acknowledged: Literal[True]
    # Dois atos distintos sobre o mesmo critério de escopo (ADR-0017): a cena cobre o
    # critério (issue `resolved`) ou o profissional o assume pendente (issue `accepted`).
    covered_criteria: list[CriterionCode] = Field(default_factory=list)
    acknowledged_criteria: list[CriterionCode] = Field(default_factory=list)
    statement: str = Field(min_length=20, max_length=500)

    @field_validator("decided_at")
    @classmethod
    def validate_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("decided_at exige timezone")
        return value

    @model_validator(mode="after")
    def validate_criteria_declarations(self) -> SceneApproval:
        if set(self.covered_criteria) & set(self.acknowledged_criteria):
            raise ValueError("um critério não pode ser declarado coberto e pendente")
        return self


class ReadingDecisionInput(ReviewModel):
    reading_id: str = Field(pattern=r"^rd_[a-f0-9]{16}$")
    action: Literal["confirm", "reject"]
    reviewer_id: str = Field(min_length=1, max_length=120)
    reviewer_role: Literal["engineer", "architect", "domain_reviewer"]
    decided_at: datetime
    note: str | None = Field(default=None, max_length=500)
    raw_text: str | None = Field(default=None, min_length=1, max_length=200)
    value_si: Decimal | None = Field(default=None, gt=0)
    unit: UnitCode | None = None
    kind: MeasurementKind | None = None
    written_decimals: int | None = Field(default=None, ge=0, le=8)
    target_hint: str | None = Field(default=None, min_length=1, max_length=120)

    @field_validator("decided_at")
    @classmethod
    def validate_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("decided_at exige timezone")
        return value


class ReadingDecisionBatch(ReviewModel):
    decisions: list[ReadingDecisionInput] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_readings(self) -> ReadingDecisionBatch:
        ids = [decision.reading_id for decision in self.decisions]
        if len(ids) != len(set(ids)):
            raise ValueError("uma leitura só pode receber uma decisão por batch")
        return self


class ReadingRectificationInput(ReadingDecisionInput):
    """Correção declarada de uma decisão já registrada, como ato humano novo.

    O alvo é citado nominalmente (`rectifies_decision_id`) para que uma correção nunca
    caia sobre uma decisão que já mudou, e a justificativa é obrigatória: corrigir o
    registro de outro profissional sem dizer por quê não é rastreável.
    """

    rectifies_decision_id: str = Field(pattern=r"^hd_[a-f0-9]{16}$")
    note: str = Field(min_length=3, max_length=500)


class ReadingRectificationBatch(ReviewModel):
    rectifications: list[ReadingRectificationInput] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_readings(self) -> ReadingRectificationBatch:
        ids = [item.reading_id for item in self.rectifications]
        if len(ids) != len(set(ids)):
            raise ValueError("uma leitura só pode receber uma retificação por batch")
        return self


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_save_png(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.stem}.",
        suffix=".png",
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        image.save(temporary_path, format="PNG", optimize=True)
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _status_color(status: ReadingStatus) -> str:
    return {
        ReadingStatus.PROPOSED: "#1769aa",
        ReadingStatus.AMBIGUOUS: "#c66a00",
        ReadingStatus.CONFIRMED: "#18864b",
        ReadingStatus.REJECTED: "#b42318",
    }[status]


def render_review_overlay(image_path: Path, packet: ReviewPacket) -> Image.Image:
    if file_sha256(image_path) != packet.image_sha256:
        raise ValueError("digest da imagem não corresponde ao review packet")
    image = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=max(16, round(image.width * 0.006)))
    stroke = max(5, round(image.width * 0.002))
    grouped_readings: dict[tuple[int, int, int, int], list[DimensionReading]] = {}
    for reading in packet.readings:
        box = reading.evidence.bbox
        if box.right > image.width or box.bottom > image.height:
            raise ValueError(f"bbox fora da imagem: {reading.id}")
        box_key = (box.left, box.top, box.right, box.bottom)
        grouped_readings.setdefault(box_key, []).append(reading)

    for box_key, readings in grouped_readings.items():
        left, top, right, bottom = box_key
        color = _status_color(readings[0].status)
        draw.rectangle((left, top, right, bottom), outline=color, width=stroke)
        for label_offset, reading in enumerate(readings):
            color = _status_color(reading.status)
            value = (
                "?"
                if reading.value_si is None
                else f"{reading.value_si:.{reading.written_decimals}f} m SI"
            )
            label = f"{reading.id} | {reading.status.value} | {value}"
            label_box = draw.textbbox((left, top), label, font=font, stroke_width=1)
            label_height = label_box[3] - label_box[1] + 12
            label_top = max(0, top - label_height * (label_offset + 1))
            draw.rectangle(
                (left, label_top, min(image.width, label_box[2] + 12), label_top + label_height),
                fill=color,
            )
            draw.text(
                (left + 6, label_top + 4),
                label,
                fill="white",
                font=font,
                stroke_width=1,
                stroke_fill=color,
            )

    banner_height = max(52, round(image.height * 0.026))
    draw.rectangle((0, 0, image.width, banner_height), fill="#161b22")
    draw.text(
        (stroke * 2, max(4, banner_height // 5)),
        "REVIEW DE COTAS - DECISAO HUMANA OBRIGATORIA - NAO EXPORTAVEL",
        fill="white",
        font=font,
    )
    return image


def write_review_artifacts(
    packet: ReviewPacket,
    image_path: Path,
    output_dir: Path,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    packet_path = output_dir / "review-packet.json"
    overlay_path = output_dir / "review-overlay.png"
    serialized = json.dumps(
        packet.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    atomic_write_text(packet_path, f"{serialized}\n")
    _atomic_save_png(render_review_overlay(image_path, packet), overlay_path)
    return packet_path, overlay_path


def load_review_packet(path: Path) -> ReviewPacket:
    return ReviewPacket.model_validate_json(path.read_text(encoding="utf-8"))


def _decision_id(reading: DimensionReading, decision: ReadingDecisionInput) -> str:
    content: dict[str, str | None] = {
        "reading_id": reading.id,
        "action": decision.action,
        "reviewer_id": decision.reviewer_id,
        "reviewer_role": decision.reviewer_role,
        "decided_at": decision.decided_at.isoformat(),
        "raw_text": decision.raw_text,
        "value_si": str(decision.value_si) if decision.value_si is not None else None,
        "unit": decision.unit.value if decision.unit is not None else None,
        "kind": decision.kind.value if decision.kind is not None else None,
    }
    if isinstance(decision, ReadingRectificationInput):
        # A chave entra SOMENTE quando há alvo: o id de uma primeira decisão é
        # identidade histórica e continua byte a byte o mesmo depois desta mudança.
        content["rectifies_decision_id"] = decision.rectifies_decision_id
    canonical = json.dumps(
        content,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"hd_{hashlib.sha256(canonical.encode()).hexdigest()[:16]}"


def _decided_fields(reading: DimensionReading, decision: ReadingDecisionInput) -> dict[str, object]:
    """Campos da leitura depois do ato humano: o que ele não declara permanece."""
    return {
        "raw_text": decision.raw_text or reading.raw_text,
        "value_si": (decision.value_si if decision.value_si is not None else reading.value_si),
        "unit": decision.unit or reading.unit,
        "kind": decision.kind or reading.kind,
        "written_decimals": (
            decision.written_decimals
            if decision.written_decimals is not None
            else reading.written_decimals
        ),
        "target_hint": decision.target_hint or reading.target_hint,
        "status": (
            ReadingStatus.CONFIRMED if decision.action == "confirm" else ReadingStatus.REJECTED
        ),
    }


def apply_reading_decisions(
    packet: ReviewPacket,
    batch: ReadingDecisionBatch,
) -> ReviewPacket:
    """Cria um novo pacote imutável de leitura; nunca altera proposta de entrada."""
    decisions = {decision.reading_id: decision for decision in batch.decisions}
    known_ids = {reading.id for reading in packet.readings}
    unknown_ids = set(decisions) - known_ids
    if unknown_ids:
        raise ValueError(f"decisões apontam para leituras desconhecidas: {sorted(unknown_ids)}")

    updated_readings: list[DimensionReading] = []
    for reading in packet.readings:
        input_decision = decisions.get(reading.id)
        if input_decision is None:
            updated_readings.append(reading)
            continue
        if reading.status in {ReadingStatus.CONFIRMED, ReadingStatus.REJECTED}:
            raise ValueError(f"leitura já revisada não pode ser sobrescrita: {reading.id}")
        human_decision = HumanDecision(
            decision_id=_decision_id(reading, input_decision),
            action=input_decision.action,
            reviewer_id=input_decision.reviewer_id,
            reviewer_role=input_decision.reviewer_role,
            decided_at=input_decision.decided_at,
            note=input_decision.note,
        )
        update = {**_decided_fields(reading, input_decision), "decision": human_decision}
        updated_readings.append(DimensionReading.model_validate({**reading.model_dump(), **update}))

    return ReviewPacket.model_validate(
        {
            **packet.model_dump(),
            "readings": updated_readings,
            "safety_notes": [
                *packet.safety_notes,
                (
                    "Decisões humanas aplicadas; propostas originais permanecem "
                    "no histórico de entrada."
                ),
            ],
        }
    )


RECTIFICATION_SAFETY_NOTE = "Decisão retificada; a anterior permanece na revisão parental."


def rectify_reading_decisions(
    packet: ReviewPacket,
    batch: ReadingRectificationBatch,
) -> ReviewPacket:
    """Sucede decisões já registradas; a anterior nunca é editada nem apagada.

    A correção é um ato humano NOVO: a leitura recebe outra `HumanDecision`, com id
    próprio e `rectifies_decision_id` apontando nominalmente a decisão substituída. A
    decisão anterior continua viva no `packet_json` da revisão parental — o pacote
    devolvido aqui é sempre o conteúdo de uma revisão nova, nunca uma edição in place.
    Uma leitura sem decisão não é retificável: para ela existe a decisão normal.
    """
    rectifications = {item.reading_id: item for item in batch.rectifications}
    known_ids = {reading.id for reading in packet.readings}
    unknown_ids = set(rectifications) - known_ids
    if unknown_ids:
        raise ValueError(f"retificações apontam para leituras desconhecidas: {sorted(unknown_ids)}")

    updated_readings: list[DimensionReading] = []
    for reading in packet.readings:
        rectification = rectifications.get(reading.id)
        if rectification is None:
            updated_readings.append(reading)
            continue
        if (
            reading.status not in {ReadingStatus.CONFIRMED, ReadingStatus.REJECTED}
            or reading.decision is None
        ):
            raise ValueError(f"leitura sem decisão não pode ser retificada: {reading.id}")
        if rectification.rectifies_decision_id != reading.decision.decision_id:
            raise ValueError(f"a decisão retificada não é a vigente da leitura: {reading.id}")
        human_decision = HumanDecision(
            decision_id=_decision_id(reading, rectification),
            action=rectification.action,
            reviewer_id=rectification.reviewer_id,
            reviewer_role=rectification.reviewer_role,
            decided_at=rectification.decided_at,
            note=rectification.note,
            rectifies_decision_id=rectification.rectifies_decision_id,
        )
        update = {**_decided_fields(reading, rectification), "decision": human_decision}
        updated_readings.append(DimensionReading.model_validate({**reading.model_dump(), **update}))

    # A nota entra uma vez só: retificações repetidas não inflam o pacote.
    safety_notes = list(packet.safety_notes)
    if RECTIFICATION_SAFETY_NOTE not in safety_notes:
        safety_notes.append(RECTIFICATION_SAFETY_NOTE)
    return ReviewPacket.model_validate(
        {
            **packet.model_dump(),
            "readings": updated_readings,
            "safety_notes": safety_notes,
        }
    )
