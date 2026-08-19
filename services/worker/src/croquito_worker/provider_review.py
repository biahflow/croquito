"""Build a non-exportable review snapshot from explicitly injected provider fixtures."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from PIL import Image

from croquito_core.models import MeasurementKind, UnitCode
from croquito_worker.association import AssociationSet, associate_readings
from croquito_worker.providers import (
    GeometryExtractionOutput,
    MeasurementExtractionOutput,
    PageSurveyOutput,
    PromptTask,
    ProviderAdapter,
    ProviderExecution,
    ProviderExecutionError,
    ProviderFailureCode,
    ProviderName,
    ProviderRequest,
    ProviderSuite,
    SurveyRegion,
    build_request,
)
from croquito_worker.review import (
    DimensionReading,
    EvidenceRegion,
    PixelBox,
    ProviderLineage,
    ReadingStatus,
    RegionCandidate,
    ReviewPacket,
)
from croquito_worker.vision import (
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


def _measurement_output(execution: ProviderExecution, label: str) -> MeasurementExtractionOutput:
    if not isinstance(execution.output, MeasurementExtractionOutput):
        raise ProviderContractError(f"{label} não retornou leituras de medida")
    return execution.output


def _execute_with_fallback(
    primary: ProviderAdapter,
    secondary: ProviderAdapter,
    request: ProviderRequest,
    notes: list[str],
    note_code: str,
) -> ProviderExecution:
    """Executa no braço primário e só degrada para o reserva depois de falha permanente.

    A degradação nunca é silenciosa: `note_code` entra nas notas de segurança do pacote,
    porque uma tarefa atendida pelo reserva é evidência de outra procedência — esconder a
    troca faria a revisão humana ler o pacote como se o braço escolhido tivesse respondido.

    Falha transitória não chega aqui: quem esgota retentativa é o `RetryingProviderAdapter`,
    e o que este helper recebe já é a exceção final. `BUDGET_EXCEEDED` também não descreve o
    braço, e sim o teto compartilhado do job: a chamada de reserva consumiria o mesmo teto
    sem chance nenhuma de sucesso, então re-levanta antes de qualquer tentativa.
    """
    try:
        return primary.execute(request)
    except ProviderExecutionError as error:
        if error.code is ProviderFailureCode.BUDGET_EXCEEDED:
            raise
        execution = secondary.execute(request)
        notes.append(note_code)
        return execution


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

    # Anthropic é o braço primário de toda tarefa com escolha; OpenAI é o reserva e a
    # contraparte da comparação. As notas de fallback acompanham o pacote até o fim,
    # inclusive quando a página nem chega à extração.
    fallback_notes: list[str] = []
    survey = _execute_with_fallback(
        suite.anthropic,
        suite.openai,
        request(PromptTask.PAGE_SURVEY),
        fallback_notes,
        "PROVIDER_FALLBACK_PAGE_SURVEY_OPENAI",
    )
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
                *fallback_notes,
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
    # Os dois braços são chamados de propósito: a extração dupla é a comparação. Por isso
    # a captura é individual, e não pelo helper de fallback — um braço caído degrada o
    # modo, não substitui o outro.
    extraction_request = request(PromptTask.MEASUREMENT_EXTRACTION)
    anthropic_extraction: ProviderExecution | None
    openai_extraction: ProviderExecution | None
    try:
        anthropic_extraction = suite.anthropic.execute(extraction_request)
    except ProviderExecutionError as error:
        if error.code is ProviderFailureCode.BUDGET_EXCEEDED:
            raise
        anthropic_extraction = None
    try:
        openai_extraction = suite.openai.execute(extraction_request)
    except ProviderExecutionError as error:
        # Sem nenhum sobrevivente não existe leitura observada: reentregar o job é mais
        # honesto do que devolver um pacote de revisão vazio como se a página não tivesse
        # cota nenhuma.
        if error.code is ProviderFailureCode.BUDGET_EXCEEDED or anthropic_extraction is None:
            raise
        openai_extraction = None
    anchor: ProviderExecution
    counterpart_execution: ProviderExecution | None
    if anthropic_extraction is not None:
        anchor = anthropic_extraction
        anchor_output = _measurement_output(anthropic_extraction, "Claude")
        counterpart_execution = openai_extraction
        counterpart_output = (
            _measurement_output(openai_extraction, "OpenAI")
            if openai_extraction is not None
            else None
        )
    elif openai_extraction is not None:
        anchor = openai_extraction
        anchor_output = _measurement_output(openai_extraction, "OpenAI")
        counterpart_execution = None
        counterpart_output = None
    else:
        raise ProviderContractError("nenhum braço de extração sobreviveu")
    dual = counterpart_execution is not None and counterpart_output is not None
    readings: list[DimensionReading] = []
    safety_notes = [
        "Leituras dos dois providers são observações; revisão humana é obrigatória."
        if dual
        else "Leitura de um braço único sem comparação; revisão humana é obrigatória.",
        "Nenhuma leitura cria geometria métrica ou libera exportação.",
        *fallback_notes,
    ]
    if not dual:
        # Sem contraparte não existe leitura concordante: a nota nomeia quem sobreviveu e
        # toda leitura nasce ambígua mais abaixo.
        safety_notes.append(
            "PROVIDER_FALLBACK_SINGLE_EXTRACTOR_ANTHROPIC"
            if anchor.provider is ProviderName.ANTHROPIC
            else "PROVIDER_FALLBACK_SINGLE_EXTRACTOR_OPENAI"
        )
    counterpart_readings = counterpart_output.readings if counterpart_output is not None else []
    if dual and len(anchor_output.readings) != len(counterpart_readings):
        safety_notes.append("PROVIDER_READING_COUNT_DISAGREEMENT")
    # A proveniência precisa dizer quem realmente leu. Um rótulo fixo, ou o par mesmo com
    # um braço caído, esconderia que a leitura saiu de uma única observação.
    if counterpart_execution is None:
        extractor = anchor.provider.value
        extractor_version = anchor.model_id
        lineage = [_lineage(anchor)]
    else:
        extractor = f"{anchor.provider.value}+{counterpart_execution.provider.value}"
        extractor_version = f"{anchor.model_id}+{counterpart_execution.model_id}"
        lineage = [_lineage(anchor), _lineage(counterpart_execution)]
    for position, observation in enumerate(anchor_output.readings, start=1):
        counterpart = (
            counterpart_readings[position - 1]
            if dual and position <= len(counterpart_readings)
            else None
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
        disagreed = dual and (
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
                extractor=extractor,
                extractor_version=extractor_version,
                provider_lineage=lineage,
                # Sem comparação dupla não existe leitura `proposed`: o que um único braço
                # entrega é observação sem corroboração, e a revisão precisa ver isso.
                status=(
                    ReadingStatus.AMBIGUOUS
                    if not dual or observation.legibility != "clear" or disagreed
                    else ReadingStatus.PROPOSED
                ),
            )
        )
    # Geometria vem do modelo, não da bbox do texto. Fabricar linha a partir do recorte
    # de uma cota nunca foi observação do desenho: era um marcador com forma de geometria.
    # O pacote só é montado depois dela para que a nota de fallback da geometria chegue às
    # notas de segurança em vez de morrer no caminho.
    geometry_execution = _execute_with_fallback(
        suite.anthropic,
        suite.openai,
        request(PromptTask.GEOMETRY_EXTRACTION),
        safety_notes,
        "PROVIDER_FALLBACK_GEOMETRY_EXTRACTION_OPENAI",
    )
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
    packet = ReviewPacket(
        dataset_id=dataset_id,
        page_number=1,
        image_sha256=image_sha256,
        region_candidates=region_candidates,
        readings=readings,
        safety_notes=safety_notes,
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
