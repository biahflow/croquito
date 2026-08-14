"""Build a non-exportable review snapshot from explicitly injected provider fixtures."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from PIL import Image

from croquitodxf_core.models import MeasurementKind, UnitCode
from croquitodxf_worker.association import AssociationSet, associate_readings
from croquitodxf_worker.providers import (
    GeometryExtractionOutput,
    MeasurementExtractionOutput,
    OcrOutput,
    PageSurveyOutput,
    PromptTask,
    ProviderExecution,
    ProviderRequest,
    ProviderSuite,
    SurveyRegion,
    build_request,
)
from croquitodxf_worker.review import (
    DimensionReading,
    EvidenceRegion,
    PixelBox,
    ProviderLineage,
    ReadingStatus,
    RegionCandidate,
    ReviewPacket,
)
from croquitodxf_worker.vision import (
    VisionProposalSet,
    corroborate_with_ink,
    proposals_from_geometry,
    register_to_ink,
)


class ProviderContractError(ValueError):
    """A fixture or provider result violated the deterministic review boundary."""


@dataclass(frozen=True)
class ProviderReviewSnapshot:
    packet: ReviewPacket
    associations: AssociationSet
    proposals: VisionProposalSet
    source_image_bytes: bytes


def _lineage(execution: ProviderExecution) -> ProviderLineage:
    return ProviderLineage(
        provider=execution.provider.value,
        model_id=execution.model_id,
        prompt_id=execution.prompt.prompt_id,
        prompt_version=execution.prompt.prompt_version,
        prompt_hash=execution.prompt.template_hash,
        schema_version=execution.prompt.schema_version,
        input_digest=execution.input_digest,
        latency_ms=execution.latency_ms,
        raw_response_ref=execution.raw_response_ref,
    )


def _reading_id(image_sha256: str, position: int) -> str:
    return f"rd_{hashlib.sha256(f'{image_sha256}:{position}'.encode()).hexdigest()[:16]}"


def _region_id(image_sha256: str, position: int) -> str:
    return f"rg_{hashlib.sha256(f'{image_sha256}:region:{position}'.encode()).hexdigest()[:16]}"


def _region_candidate(image_sha256: str, position: int, region: SurveyRegion) -> RegionCandidate:
    return RegionCandidate(
        id=_region_id(image_sha256, position),
        kind=region.kind,
        label=region.label,
        evidence=region.evidence,
        polygon=[(point.x, point.y) for point in region.polygon],
    )


def _pixel_box(
    *, left: float, top: float, right: float, bottom: float, width: int, height: int
) -> PixelBox:
    return PixelBox(
        left=max(0, int(left * width)),
        top=max(0, int(top * height)),
        right=min(width, max(1, int(right * width))),
        bottom=min(height, max(1, int(bottom * height))),
    )


def _measurement_kind(kind: str) -> MeasurementKind:
    try:
        return MeasurementKind(kind)
    except ValueError as error:
        raise ProviderContractError(f"tipo de medida fora do review packet: {kind}") from error


def _unit(unit: str) -> UnitCode:
    if unit == "m":
        return UnitCode.METRE
    if unit == "mm":
        return UnitCode.MILLIMETRE
    raise ProviderContractError(f"unidade fora do review packet: {unit}")


def build_provider_review_snapshot(
    image_path: Path,
    *,
    dataset_id: str,
    suite: ProviderSuite,
) -> ProviderReviewSnapshot:
    """Execute the fixture path without granting any provider result geometric authority."""
    source_image_bytes = image_path.read_bytes()
    image_sha256 = hashlib.sha256(source_image_bytes).hexdigest()
    with Image.open(image_path) as source_image:
        width, height = source_image.size

    def request(task: PromptTask) -> ProviderRequest:
        return build_request(
            task,
            image_bytes=source_image_bytes,
            image_sha256=image_sha256,
            image_width_px=width,
            image_height_px=height,
            region_label="main_plan",
        )

    survey = suite.openai.execute(request(PromptTask.PAGE_SURVEY))
    if not isinstance(survey.output, PageSurveyOutput) or not survey.output.regions:
        raise ProviderContractError("page survey não retornou região utilizável")
    region_candidates = [
        _region_candidate(image_sha256, position, region)
        for position, region in enumerate(survey.output.regions, start=1)
    ]
    main_plans = [region for region in region_candidates if region.kind == "main_plan"]
    if len(main_plans) != 1:
        packet = ReviewPacket(
            dataset_id=dataset_id,
            page_number=1,
            image_sha256=image_sha256,
            region_candidates=region_candidates,
            readings=[],
            safety_notes=[
                "REGION_CLASSIFICATION_REQUIRED",
                "Nenhuma região foi escolhida automaticamente para extração externa.",
            ],
        )
        return ProviderReviewSnapshot(
            packet=packet,
            associations=AssociationSet(
                dataset_id=dataset_id,
                page_number=1,
                image_sha256=image_sha256,
                candidates=[],
                unassociated_reading_ids=[],
                safety_notes=[
                    *packet.safety_notes,
                    "Associações não são calculadas antes da classificação humana.",
                ],
            ),
            proposals=VisionProposalSet(
                dataset_id=dataset_id,
                page_number=1,
                image_sha256=image_sha256,
                image_width_px=width,
                image_height_px=height,
                configured_limits={"line": 80, "circle": 16, "contour": 16},
                limit_reached=[],
                proposals=[],
                safety_notes=[
                    *packet.safety_notes,
                    "Propostas geométricas não são promovidas antes da classificação humana.",
                ],
            ),
            source_image_bytes=source_image_bytes,
        )
    ocr = suite.textract.execute(request(PromptTask.OCR))
    openai_extraction = suite.openai.execute(request(PromptTask.MEASUREMENT_EXTRACTION))
    anthropic_extraction = suite.bedrock_anthropic.execute(
        request(PromptTask.MEASUREMENT_EXTRACTION)
    )
    if not isinstance(ocr.output, OcrOutput):
        raise ProviderContractError("OCR não retornou contrato OCR")
    if not isinstance(openai_extraction.output, MeasurementExtractionOutput):
        raise ProviderContractError("OpenAI não retornou leituras de medida")
    if not isinstance(anthropic_extraction.output, MeasurementExtractionOutput):
        raise ProviderContractError("Claude não retornou leituras de medida")
    readings: list[DimensionReading] = []
    safety_notes = [
        "Leituras de OCR e dos dois providers são observações; revisão humana é obrigatória.",
        "Nenhuma leitura cria geometria métrica ou libera exportação.",
    ]
    anthropic_readings = anthropic_extraction.output.readings
    if len(openai_extraction.output.readings) != len(anthropic_readings):
        safety_notes.append("PROVIDER_READING_COUNT_DISAGREEMENT")
    for position, observation in enumerate(openai_extraction.output.readings, start=1):
        counterpart = (
            anthropic_readings[position - 1] if position <= len(anthropic_readings) else None
        )
        if observation.normalized_value is None or observation.target_hint is None:
            safety_notes.append(f"READING_{position}_INCOMPLETE")
            continue
        target_hint = observation.target_hint
        try:
            unit = _unit(observation.unit)
            kind = _measurement_kind(observation.kind)
        except ProviderContractError:
            safety_notes.append(f"READING_{position}_UNSUPPORTED_UNIT_OR_KIND")
            continue
        disagreed = (
            counterpart is None
            or counterpart.normalized_value != observation.normalized_value
            or counterpart.unit != observation.unit
            or counterpart.kind != observation.kind
            or counterpart.target_hint != observation.target_hint
        )
        if disagreed:
            safety_notes.append(f"READING_{position}_PROVIDER_DISAGREEMENT")
        readings.append(
            DimensionReading(
                id=_reading_id(image_sha256, position),
                evidence=EvidenceRegion(
                    dataset_id=dataset_id,
                    page_number=1,
                    image_sha256=image_sha256,
                    bbox=_pixel_box(
                        left=observation.bbox.left,
                        top=observation.bbox.top,
                        right=observation.bbox.right,
                        bottom=observation.bbox.bottom,
                        width=width,
                        height=height,
                    ),
                ),
                raw_text=observation.raw_text,
                value_si=Decimal(observation.normalized_value),
                unit=unit,
                kind=kind,
                written_decimals=observation.written_precision,
                target_hint=f"{target_hint.entity_label}: {target_hint.feature}",
                # A proveniência precisa dizer quem realmente leu. Um rótulo fixo de
                # fixture no caminho real esconderia que houve chamada externa paga.
                extractor=(
                    f"{openai_extraction.provider.value}+{anthropic_extraction.provider.value}"
                ),
                extractor_version=(f"{openai_extraction.model_id}+{anthropic_extraction.model_id}"),
                provider_lineage=[_lineage(openai_extraction), _lineage(anthropic_extraction)],
                status=(
                    ReadingStatus.AMBIGUOUS
                    if observation.legibility != "clear" or disagreed
                    else ReadingStatus.PROPOSED
                ),
            )
        )
    packet = ReviewPacket(
        dataset_id=dataset_id,
        page_number=1,
        image_sha256=image_sha256,
        region_candidates=region_candidates,
        readings=readings,
        safety_notes=safety_notes,
    )
    # Geometria vem do modelo, não da bbox do texto. Fabricar linha a partir do recorte
    # de uma cota nunca foi observação do desenho: era um marcador com forma de geometria.
    geometry_execution = suite.bedrock_anthropic.execute(request(PromptTask.GEOMETRY_EXTRACTION))
    if not isinstance(geometry_execution.output, GeometryExtractionOutput):
        raise ProviderContractError("extração de geometria não retornou contrato de geometria")
    proposals_list = proposals_from_geometry(
        geometry_execution.output.elements,
        image_digest=image_sha256,
        width=width,
        height=height,
    )
    proposal_notes = [
        "Geometria proposta por modelo; nenhuma medida vem dela.",
        "Toda proposta continua unresolved e não exportável até decisão humana.",
        "Seleção humana exige calibração explícita antes de criar rascunho approximate.",
    ]
    if proposals_list:
        # Registro assenta o conjunto e depois cada elemento sobre a tinta; a conferência
        # mede o que sobrou. A nota declara os três estágios: esconder o refino faria a
        # revisão acreditar que só houve deslocamento global.
        proposals_list, registration = register_to_ink(proposals_list, image_path)
        proposals_list, ink_notes = corroborate_with_ink(proposals_list, image_path)
        proposal_notes.append(
            f"INK_REGISTRATION:{registration.coverage_before:.3f}"
            f"->{registration.coverage_after:.3f}"
            f"->{registration.coverage_refined:.3f}"
        )
        proposal_notes.extend(ink_notes)
    proposals = VisionProposalSet(
        dataset_id=dataset_id,
        page_number=1,
        image_sha256=image_sha256,
        image_width_px=width,
        image_height_px=height,
        configured_limits={"line": 80, "circle": 16, "contour": 16},
        limit_reached=[],
        proposals=proposals_list,
        safety_notes=proposal_notes,
    )
    # Associação por proximidade real entre o recorte da cota e a geometria observada,
    # em vez do par sintético 1:1 que a fabricação produzia.
    associations = associate_readings(packet, proposals)
    return ProviderReviewSnapshot(
        packet=packet,
        associations=associations,
        proposals=proposals,
        source_image_bytes=source_image_bytes,
    )
