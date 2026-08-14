"""Transcrição standalone de cotas por um único arm de provider, e mesclagem em ReviewPacket.

Dois degraus do mesmo fluxo: `run_transcription` chama `PromptTask.MEASUREMENT_EXTRACTION`
com um único eixo de provider (espelho de `extraction_eval.run_extraction_eval`, que só faz
`GEOMETRY_EXTRACTION`); `merge_readings_into_packet` converte a saída bruta em
`DimensionReading` honestas e mescla com um pacote de revisão existente, sem decidir nada —
a leitura nasce sempre `proposed`/`ambiguous`, nunca `confirmed`.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from PIL import Image
from pydantic import BaseModel, ConfigDict, Field

from croquitodxf_core.models import MeasurementKind, UnitCode
from croquitodxf_worker.extraction_eval import (
    ExtractionCandidate,
    authorize_page,
    prepare_transmission,
)
from croquitodxf_worker.io_utils import atomic_write_text
from croquitodxf_worker.providers import (
    MeasurementExtractionOutput,
    NormalizedBox,
    PromptTask,
    build_request,
)
from croquitodxf_worker.review import (
    DimensionReading,
    EvidenceRegion,
    PixelBox,
    ProviderLineage,
    ReadingStatus,
    ReviewPacket,
)


class TranscriptionMergeError(ValueError):
    """A leitura transcrita não pode ser ligada com segurança ao pacote base."""


class TranscriptionReport(BaseModel):
    """Resumo sem conteúdo de cota: só IDs, contagens, custo e duração."""

    model_config = ConfigDict(extra="forbid")

    arm: str
    provider: str
    model_id: str
    prompt_version: str
    image_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    reading_count: int = Field(ge=0)
    counts_by_kind: dict[str, int]
    counts_by_legibility: dict[str, int]
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost_usd: float | None = None
    latency_ms: int = Field(ge=0)
    notes: list[str]


class TranscriptionArtifact(BaseModel):
    """`MeasurementExtractionOutput` validada mais a proveniência exigida pelo merge.

    Desvio documentado do texto literal do spec ("`{arm}-readings.json`: a
    `MeasurementExtractionOutput` validada, dump canônico"): o contrato bruto não carrega
    provider/model/prompt, e sem esses campos `readings-to-packet` não teria como montar
    `DimensionReading.extractor`/`extractor_version`/`provider_lineage` a partir só do
    artefato de leituras. Este modelo embrulha a saída validada (`output`, dump canônico
    igual ao que o spec pedia) junto da proveniência mínima — nada de payload bruto do
    provider, só os mesmos campos que `ProviderLineage` já expõe em outros pacotes.
    """

    model_config = ConfigDict(extra="forbid")

    arm: str
    provider: str
    model_id: str
    prompt_id: str
    prompt_version: str
    prompt_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    schema_version: str
    input_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    latency_ms: int = Field(ge=0)
    raw_response_ref: str | None = None
    output: MeasurementExtractionOutput


def run_transcription(
    image_path: Path,
    candidate: ExtractionCandidate,
    output_dir: Path,
    *,
    manifest_path: Path,
) -> tuple[TranscriptionArtifact, TranscriptionReport, Path, Path]:
    """Transcreve cotas com um único eixo de provider; espelho de `run_extraction_eval`.

    Reusa `authorize_page` (a allowlist do documento é checada antes de qualquer chamada
    externa) e `prepare_transmission` (mesmo limite de payload dos providers). Não foi
    preciso fatorar `build_extraction_arm`: ele já é independente de task — a task só
    entra depois, em `build_request` — então nada ali está acoplado à extração de
    geometria.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    source = image_path.resolve(strict=True)
    image_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    # A allowlist vale sobre o documento de origem; nenhuma chamada externa antes dela.
    authorize_page(manifest_path, image_sha256)

    payload, width, height = prepare_transmission(source)
    request = build_request(
        PromptTask.MEASUREMENT_EXTRACTION,
        image_bytes=payload,
        image_sha256=hashlib.sha256(payload).hexdigest(),
        image_width_px=width,
        image_height_px=height,
        region_label="main_plan",
    )
    execution = candidate.adapter.execute(request)
    if not isinstance(execution.output, MeasurementExtractionOutput):
        raise ValueError(f"{candidate.name} não devolveu contrato de transcrição de medida")

    counts_by_kind: dict[str, int] = {}
    counts_by_legibility: dict[str, int] = {}
    for reading in execution.output.readings:
        counts_by_kind[reading.kind] = counts_by_kind.get(reading.kind, 0) + 1
        counts_by_legibility[reading.legibility] = (
            counts_by_legibility.get(reading.legibility, 0) + 1
        )

    notes = [
        f"READINGS_RETURNED:{len(execution.output.readings)}",
        "AMBIGUOUS_OR_ILLEGIBLE:"
        f"{sum(1 for item in execution.output.readings if item.legibility != 'clear')}",
    ]

    artifact = TranscriptionArtifact(
        arm=candidate.name,
        provider=execution.provider.value,
        model_id=execution.model_id,
        prompt_id=execution.prompt.prompt_id,
        prompt_version=execution.prompt.prompt_version,
        prompt_hash=execution.prompt.template_hash,
        schema_version=execution.prompt.schema_version,
        input_digest=execution.input_digest,
        latency_ms=execution.latency_ms,
        raw_response_ref=execution.raw_response_ref,
        output=execution.output,
    )
    report = TranscriptionReport(
        arm=candidate.name,
        provider=execution.provider.value,
        model_id=execution.model_id,
        prompt_version=execution.prompt.prompt_version,
        image_sha256=image_sha256,
        reading_count=len(execution.output.readings),
        counts_by_kind=counts_by_kind,
        counts_by_legibility=counts_by_legibility,
        input_tokens=execution.usage.input_tokens,
        output_tokens=execution.usage.output_tokens,
        estimated_cost_usd=(
            float(execution.usage.estimated_cost_usd)
            if execution.usage.estimated_cost_usd is not None
            else None
        ),
        latency_ms=execution.latency_ms,
        notes=notes,
    )

    readings_path = output_dir / f"{candidate.name}-readings.json"
    atomic_write_text(
        readings_path,
        json.dumps(artifact.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
    )
    report_path = output_dir / "transcription-report.json"
    atomic_write_text(
        report_path,
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
    )
    return artifact, report, readings_path, report_path


DiscardReason = Literal[
    "degenerate_bbox",
    "unsupported_unit",
    "unsupported_kind",
    "missing_value",
    "missing_target_hint",
    "duplicate",
]


class DiscardedReadingNote(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=1)
    reason: DiscardReason
    detail: str = Field(min_length=1, max_length=200)


class CollisionResolutionNote(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=1)
    original_id: str = Field(pattern=r"^rd_[a-f0-9]{16}$")
    resolved_id: str = Field(pattern=r"^rd_[a-f0-9]{16}$")
    attempts: int = Field(ge=1)


class MergeReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str = Field(min_length=1, max_length=64)
    page_number: int = Field(ge=1)
    image_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    base_reading_count: int = Field(ge=0)
    new_reading_count: int = Field(ge=0)
    accepted_count: int = Field(ge=0)
    duplicate_count: int = Field(ge=0)
    discarded_count: int = Field(ge=0)
    discarded_by_reason: dict[str, int]
    discarded: list[DiscardedReadingNote]
    id_collisions: list[CollisionResolutionNote]
    alternatives_reported: int = Field(ge=0)
    total_reading_count: int = Field(ge=0)


def _reading_pixel_box(bbox: NormalizedBox, *, width: int, height: int) -> PixelBox | None:
    """Mesmo cálculo do precedente `provider_review._pixel_box`, mas descarta em vez de assumir.

    O bbox normalizado sempre tem área positiva (validado no contrato de leitura), mas o
    truncamento inteiro ao converter para pixels pode zerar a área numa imagem grande: aqui
    isso vira descarte explícito com nota, nunca um `PixelBox` de área zero aceito calado.
    """
    left = max(0, int(bbox.left * width))
    top = max(0, int(bbox.top * height))
    right = min(width, max(1, int(bbox.right * width)))
    bottom = min(height, max(1, int(bbox.bottom * height)))
    if right <= left or bottom <= top:
        return None
    return PixelBox(left=left, top=top, right=right, bottom=bottom)


def _map_unit(unit: str) -> UnitCode | None:
    if unit == "m":
        return UnitCode.METRE
    if unit == "mm":
        return UnitCode.MILLIMETRE
    return None


def _map_kind(kind: str) -> MeasurementKind | None:
    try:
        return MeasurementKind(kind)
    except ValueError:
        return None


def _boxes_intersect(first: PixelBox, second: PixelBox) -> bool:
    left = max(first.left, second.left)
    top = max(first.top, second.top)
    right = min(first.right, second.right)
    bottom = min(first.bottom, second.bottom)
    return right > left and bottom > top


def _reading_id(image_sha256: str, index: int, *, attempt: int = 0) -> str:
    """Mesmo esquema do precedente `provider_review._reading_id`, com sufixo para colisão.

    Colisão nunca reaproveita o índice de outra leitura (o índice é a posição real na
    saída do provider); em vez disso, acrescenta um contador de tentativa determinístico
    ao mesmo índice até achar um ID livre.
    """
    seed = f"{image_sha256}:{index}" if attempt == 0 else f"{image_sha256}:{index}:{attempt}"
    return f"rd_{hashlib.sha256(seed.encode()).hexdigest()[:16]}"


def _resolve_reading_id(image_sha256: str, index: int, known_ids: set[str]) -> tuple[str, int]:
    attempt = 0
    candidate = _reading_id(image_sha256, index, attempt=attempt)
    while candidate in known_ids:
        attempt += 1
        candidate = _reading_id(image_sha256, index, attempt=attempt)
    return candidate, attempt


def merge_readings_into_packet(
    artifact: TranscriptionArtifact,
    base_packet: ReviewPacket,
    *,
    manifest_path: Path,
    image_path: Path,
) -> tuple[ReviewPacket, MergeReport]:
    """Converte a transcrição bruta em `DimensionReading` e mescla com o pacote base.

    `dataset_id`/`page_number`/`image_sha256` vêm sempre do manifest (nunca hardcoded);
    devem bater com os do pacote base, senão a evidência da leitura nova não conseguiria
    apontar para o mesmo documento/página que o pacote já revisa.
    """
    source = image_path.resolve(strict=True)
    image_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    dataset_id = manifest.get("dataset_id") if isinstance(manifest, dict) else None
    pages = manifest.get("pages", []) if isinstance(manifest, dict) else []
    matched_page = next(
        (
            page
            for page in pages
            if isinstance(page, dict)
            and str(page.get("image_sha256", "")).lower() == image_sha256.lower()
        ),
        None,
    )
    if not isinstance(dataset_id, str) or not dataset_id or matched_page is None:
        raise TranscriptionMergeError(
            "A imagem não pertence ao manifest informado: evidência recusada."
        )
    page_number = matched_page.get("number")
    if not isinstance(page_number, int):
        raise TranscriptionMergeError(
            "O manifest não informa o número da página para a imagem: evidência recusada."
        )
    raw_width = matched_page.get("rendered_width_px")
    raw_height = matched_page.get("rendered_height_px")
    if (
        isinstance(raw_width, int)
        and raw_width > 0
        and isinstance(raw_height, int)
        and raw_height > 0
    ):
        width, height = raw_width, raw_height
    else:
        with Image.open(source) as opened:
            width, height = opened.size

    if (
        base_packet.dataset_id != dataset_id
        or base_packet.page_number != page_number
        or base_packet.image_sha256 != image_sha256
    ):
        raise TranscriptionMergeError(
            "A evidência do manifest diverge do pacote base: merge recusado."
        )

    lineage = ProviderLineage(
        provider=artifact.provider,
        model_id=artifact.model_id,
        prompt_id=artifact.prompt_id,
        prompt_version=artifact.prompt_version,
        prompt_hash=artifact.prompt_hash,
        schema_version=artifact.schema_version,
        input_digest=artifact.input_digest,
        latency_ms=artifact.latency_ms,
        raw_response_ref=artifact.raw_response_ref,
    )
    extractor = artifact.provider
    extractor_version = f"{artifact.model_id}+{artifact.prompt_version}"

    known_ids = {reading.id for reading in base_packet.readings}
    accepted: list[DimensionReading] = []
    discarded: list[DiscardedReadingNote] = []
    id_collisions: list[CollisionResolutionNote] = []
    alternatives_reported = 0

    for index, reading in enumerate(artifact.output.readings, start=1):
        if reading.alternatives:
            alternatives_reported += 1

        pixel_box = _reading_pixel_box(reading.bbox, width=width, height=height)
        if pixel_box is None:
            discarded.append(
                DiscardedReadingNote(
                    index=index,
                    reason="degenerate_bbox",
                    detail="bbox normalizado converge para área zero em pixels",
                )
            )
            continue

        unit = _map_unit(reading.unit)
        if unit is None:
            discarded.append(
                DiscardedReadingNote(
                    index=index,
                    reason="unsupported_unit",
                    detail=f"unidade '{reading.unit}' fora do contrato de leitura (m ou mm)",
                )
            )
            continue

        kind = _map_kind(reading.kind)
        if kind is None:
            discarded.append(
                DiscardedReadingNote(
                    index=index,
                    reason="unsupported_kind",
                    detail=f"tipo de medida '{reading.kind}' fora do contrato de leitura",
                )
            )
            continue

        if reading.normalized_value is None:
            discarded.append(
                DiscardedReadingNote(
                    index=index,
                    reason="missing_value",
                    detail="leitura sem valor numérico normalizado",
                )
            )
            continue

        if reading.target_hint is None:
            discarded.append(
                DiscardedReadingNote(
                    index=index,
                    reason="missing_target_hint",
                    detail="leitura sem alvo (target_hint) identificado",
                )
            )
            continue

        value_si = reading.normalized_value
        duplicate_of = next(
            (
                base_reading.id
                for base_reading in base_packet.readings
                if base_reading.value_si == value_si
                and base_reading.unit == unit
                and _boxes_intersect(base_reading.evidence.bbox, pixel_box)
            ),
            None,
        )
        if duplicate_of is not None:
            discarded.append(
                DiscardedReadingNote(
                    index=index,
                    reason="duplicate",
                    detail=f"duplica a leitura base {duplicate_of}",
                )
            )
            continue

        reading_id, attempts = _resolve_reading_id(image_sha256, index, known_ids)
        known_ids.add(reading_id)
        if attempts:
            id_collisions.append(
                CollisionResolutionNote(
                    index=index,
                    original_id=_reading_id(image_sha256, index),
                    resolved_id=reading_id,
                    attempts=attempts,
                )
            )

        target_hint = f"{reading.target_hint.entity_label}: {reading.target_hint.feature}"[:120]
        accepted.append(
            DimensionReading(
                id=reading_id,
                evidence=EvidenceRegion(
                    dataset_id=dataset_id,
                    page_number=page_number,
                    image_sha256=image_sha256,
                    bbox=pixel_box,
                ),
                raw_text=reading.raw_text,
                value_si=value_si,
                unit=unit,
                kind=kind,
                written_decimals=reading.written_precision,
                target_hint=target_hint,
                extractor=extractor,
                extractor_version=extractor_version,
                provider_lineage=[lineage],
                status=(
                    ReadingStatus.AMBIGUOUS
                    if reading.legibility != "clear"
                    else ReadingStatus.PROPOSED
                ),
                decision=None,
            )
        )

    merged_packet = ReviewPacket.model_validate(
        {
            **base_packet.model_dump(),
            "readings": [*base_packet.readings, *accepted],
            "safety_notes": [
                *base_packet.safety_notes,
                "TRANSCRIÇÃO MESCLADA: leituras novas permanecem sem decisão humana.",
            ],
        }
    )

    discarded_by_reason: dict[str, int] = {}
    duplicate_count = 0
    for note in discarded:
        discarded_by_reason[note.reason] = discarded_by_reason.get(note.reason, 0) + 1
        if note.reason == "duplicate":
            duplicate_count += 1

    report = MergeReport(
        dataset_id=dataset_id,
        page_number=page_number,
        image_sha256=image_sha256,
        base_reading_count=len(base_packet.readings),
        new_reading_count=len(artifact.output.readings),
        accepted_count=len(accepted),
        duplicate_count=duplicate_count,
        discarded_count=len(discarded),
        discarded_by_reason=discarded_by_reason,
        discarded=discarded,
        id_collisions=id_collisions,
        alternatives_reported=alternatives_reported,
        total_reading_count=len(merged_packet.readings),
    )
    return merged_packet, report


def write_merge_artifacts(
    packet: ReviewPacket,
    report: MergeReport,
    output_dir: Path,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    packet_path = output_dir / "review-packet-merged.json"
    report_path = output_dir / "merge-report.json"
    atomic_write_text(
        packet_path,
        json.dumps(packet.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
    )
    atomic_write_text(
        report_path,
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
    )
    return packet_path, report_path
