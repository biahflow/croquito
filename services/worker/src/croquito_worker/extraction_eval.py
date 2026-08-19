"""Eval comparativa da extração de geometria por modelo, medida contra a tinta do papel.

Sem gabarito não existe recall honesto. O que dá para verificar é se a geometria proposta
cai sobre traço real, se as regiões que fecham no papel fecham na saída, e se os elementos
vieram rotulados. A comparação final entre providers é humana, olhando o diff.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from croquito_worker.io_utils import atomic_write_text
from croquito_worker.providers import (
    GeometryExtractionOutput,
    PromptTask,
    ProviderAdapter,
    build_request,
)
from croquito_worker.vision import (
    PixelPolyline,
    VisionConfig,
    VisionProposal,
    corroborate_with_ink,
    proposals_from_geometry,
    register_to_ink,
)

TRANSMISSION_MAX_DIMENSION = 2400
"""Lado maior da imagem enviada; o provider recusa payload grande demais."""

TRANSMISSION_MAX_BYTES = 3_600_000
"""Limite de ~5 MB dos providers vale sobre o payload **base64**, que cresce um terço.

Medir os bytes binários deixaria passar uma imagem de 4 MB que vira 5,5 MB na transmissão
e é recusada com 400 — depois de o budget já ter sido reservado.
"""


class ExtractionNotAllowlistedError(RuntimeError):
    """O documento não está liberado para sair para um provider externo."""


def prepare_transmission(source: Path) -> tuple[bytes, int, int]:
    """Reduz a página para caber no limite do provider, sem mexer no mapeamento.

    O contrato devolve coordenadas normalizadas e a conversão multiplica pelas dimensões
    **originais**, então reduzir o que trafega não desloca a geometria de volta. Enviar a
    página de 22 MB apenas faria a chamada falhar depois de reservar budget.
    """
    from io import BytesIO

    from PIL import Image

    with Image.open(source) as image:
        original_width, original_height = image.size
        reduced = image.convert("RGB")
        reduced.thumbnail(
            (TRANSMISSION_MAX_DIMENSION, TRANSMISSION_MAX_DIMENSION),
            Image.Resampling.LANCZOS,
        )
        buffer = BytesIO()
        reduced.save(buffer, format="PNG", optimize=True)
        payload = buffer.getvalue()
        if len(payload) > TRANSMISSION_MAX_BYTES:
            buffer = BytesIO()
            reduced.save(buffer, format="JPEG", quality=88)
            payload = buffer.getvalue()
    return payload, original_width, original_height


@dataclass(frozen=True)
class ExtractionCandidate:
    """Um eixo de comparação: provider e modelo por trás do mesmo pedido."""

    name: str
    adapter: ProviderAdapter


class ProposalRegistrationReport(BaseModel):
    """Linha por proposta do antes/depois do registro, para a revisão olhar elemento a elemento.

    A média por eixo esconde o que importa: um ótimo agregado pode subir a taxa e ainda
    assim ter piorado um elemento que já estava certo. Aqui cada proposta declara as três
    coberturas, qual colocação virou base e que ajuste recebeu.
    """

    model_config = ConfigDict(extra="forbid")

    proposal_id: str
    label: str | None = None
    kind: str
    coverage_raw: float = Field(ge=0, le=1)
    coverage_global: float = Field(ge=0, le=1)
    coverage_refined: float = Field(ge=0, le=1)
    base: str
    refinement: str
    centre_shift_px: float = 0.0
    radius_delta_px: float = 0.0
    orientation_delta_degrees: float = 0.0
    # Contorno quase-retangular declara o deslocamento de cada aresta, na ordem topo, base,
    # esquerda e direita. É o que distingue corrigir o TAMANHO do elemento de empurrá-lo
    # inteiro, e sem os quatro números a revisão não consegue conferir o contorno na folha.
    edge_shifts_px: list[float] = Field(default_factory=list)
    # Linha declara quanto cada ponta deslizou ao longo da própria direção, na ordem início e
    # fim. É o que distingue a linha que andou da linha que era comprida demais.
    tip_shifts_px: list[float] = Field(default_factory=list)
    # O refino moveu o elemento por obrigação de ordem, não por ganho de tinta: a colocação
    # de base cruzava um vizinho paralelo já assentado.
    order_constrained: bool = False
    # Nenhuma colocação preservava a ordem traçada. A proposta é incompatível com as
    # vizinhas e isso vai para a revisão em vez de ser resolvido escolhendo um lado.
    order_unresolved: bool = False


class StepFidelityPoint(BaseModel):
    """Ponto normalizado (0..1) do gabarito do degrau — mesmo espaço do contrato de geometria."""

    model_config = ConfigDict(extra="forbid")

    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class StepFidelitySegment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: StepFidelityPoint
    end: StepFidelityPoint


class StepGabarito(BaseModel):
    """Gabarito do "degrau" de um muro em recuo: dois trechos retos e o cotovelo entre eles.

    As coordenadas são normalizadas para acompanhar o mesmo espaço do contrato de geometria;
    `image_width_px`/`image_height_px` é metadado da folha (necessário para reconverter em
    pixels na hora de comparar com a proposta, que sempre chega em pixels da imagem
    original), não uma medida duplicada. `build_degrau_step_gabarito` deriva os dois
    trechos e o cotovelo das constantes `DEGRAU_*_PX` do render — nenhuma coordenada aqui
    nasce digitada duas vezes.
    """

    model_config = ConfigDict(extra="forbid")

    image_width_px: int = Field(gt=0)
    image_height_px: int = Field(gt=0)
    segment_a: StepFidelitySegment
    segment_b: StepFidelitySegment
    # NÃO é gate: a posição absoluta do cotovelo pune registro global, não forma (ver
    # `assess_step_fidelity`). Usada só para o diagnóstico
    # `STEP_JOG_TRANSITION_REGISTRATION_OFFSET_PX` — o quanto a transição estrutural
    # encontrada está longe de onde o gabarito espera, sinal de deslocamento de registro
    # para a revisão humana olhar, não motivo de reprovação.
    jog_vertex: StepFidelityPoint
    # 12 px é acima da tolerância de corroboração de tinta (9 px): a folga cobre ruído de
    # leitura sem deixar passar um degrau de 30 px achatado para uma reta única.
    offset_tolerance_px: float = Field(gt=0, default=12.0)
    min_vertex_count: int = Field(ge=4, default=4)


class StepFidelityReport(BaseModel):
    """Resultado do gate do degrau para um braço: reprova o que a corroboração de tinta não pega.

    Um muro achatado — duas `line` retas, ou uma reta única — pode aderir à tinta tanto
    quanto o muro fiel; `corroborated_rate` mede aderência ao traço, não continuidade
    topológica. Este relatório é o que distingue os dois casos.
    """

    model_config = ConfigDict(extra="forbid")

    element_found: bool
    single_element: bool
    vertex_count: int = Field(ge=0)
    offset_a_px: float | None = None
    offset_b_px: float | None = None
    jog_transition_found: bool
    step_preserved: bool
    notes: list[str] = Field(default_factory=list)


def _step_line_offset(
    point: tuple[float, float], axis_start: tuple[float, float], axis_end: tuple[float, float]
) -> float:
    """Distância perpendicular (com sinal) de `point` à reta infinita `axis_start`→`axis_end`."""
    axis_x, axis_y = axis_end[0] - axis_start[0], axis_end[1] - axis_start[1]
    norm = math.hypot(axis_x, axis_y)
    if norm == 0:
        return 0.0
    point_x, point_y = point[0] - axis_start[0], point[1] - axis_start[1]
    return (point_x * axis_y - point_y * axis_x) / norm


def _step_axis_projection(
    point: tuple[float, float], axis_start: tuple[float, float], axis_end: tuple[float, float]
) -> float:
    """Componente de `point` AO LONGO do eixo `axis_start`→`axis_end` — não perpendicular a ele.

    É o que mede "andou ao longo do trecho", em oposição a `_step_line_offset`, que mede
    "andou para o lado". Um jog de verdade é perpendicular ao eixo: o par de vértices que o
    faz quase não muda esta componente, só a de `_step_line_offset`.
    """
    axis_x, axis_y = axis_end[0] - axis_start[0], axis_end[1] - axis_start[1]
    norm = math.hypot(axis_x, axis_y)
    if norm == 0:
        return 0.0
    point_x, point_y = point[0] - axis_start[0], point[1] - axis_start[1]
    return (point_x * axis_x + point_y * axis_y) / norm


def assess_step_fidelity(
    proposals: list[VisionProposal], gabarito: StepGabarito
) -> StepFidelityReport:
    """Mede se o degrau do muro sobreviveu à extração, sobre propostas já em pixels.

    Critério: um único elemento POLYLINE aberto, com ao menos `min_vertex_count` vértices,
    cobrindo os dois trechos do gabarito com afastamentos médios (perpendiculares ao eixo do
    trecho A) distintos além da tolerância, e uma TRANSIÇÃO ESTRUTURAL entre os dois
    trechos: um par de vértices CONSECUTIVOS da polilinha em que um foi classificado no
    trecho A e o outro no trecho B, com deslocamento AO LONGO do eixo do trecho A (não
    perpendicular a ele) dentro da tolerância. Um jog de verdade é perpendicular ao trecho:
    o par que faz a curva quase não anda ao longo do eixo, só cruza de lado.

    A versão anterior exigia um vértice a `offset_tolerance_px` da POSIÇÃO ABSOLUTA do
    cotovelo do gabarito — e isso pune registro global, não forma. A primeira rodada paga
    real (candidato `geometry-extraction@2.0.2`) devolveu o muro CERTO — polilinha única
    aberta, offsets médios 12,4/-17,0 px (delta 29,4 px ≈ jog de 30 px) —, mas o traçado
    inteiro tinha ~12 px de deslocamento GLOBAL de registro (o modelo ancorou noutra borda
    do traço) e o vértice do cotovelo caiu a mais de `offset_tolerance_px` da posição
    absoluta esperada: o critério antigo reprovava um degrau estruturalmente correto por
    causa de translação, não de forma. O critério estrutural não olha ONDE o degrau está na
    folha, só COMO ele é feito — e continua reprovando os mesmos três casos:

    - Duas `line` de dois vértices (a reprodução exata da resposta real do Opus no
      Guaxindiba V3): nunca viram candidatas, porque só `PixelPolyline` entra na contagem
      de vértices.
    - Reta única: entra como candidata, mas todos os vértices caem no mesmo trecho (nenhuma
      transição de trecho A→B existe) ou os afastamentos médios ficam iguais
      (`STEP_FLATTENED`).
    - Rampa suave (vértices extras espalhando a subida ao longo de muitos pixels em vez de
      um cotovelo): existe transição de trecho, mas o par que a faz anda demais ao longo do
      eixo — além da tolerância —, então `jog_transition_found` continua falso.
    """
    width, height = gabarito.image_width_px, gabarito.image_height_px

    def denormalize(point: StepFidelityPoint) -> tuple[float, float]:
        return (point.x * width, point.y * height)

    axis_a_start = denormalize(gabarito.segment_a.start)
    axis_a_end = denormalize(gabarito.segment_a.end)
    axis_b_start = denormalize(gabarito.segment_b.start)
    axis_b_end = denormalize(gabarito.segment_b.end)
    jog_vertex_px = denormalize(gabarito.jog_vertex)
    tolerance = gabarito.offset_tolerance_px

    candidates = [
        proposal
        for proposal in proposals
        if isinstance(proposal.geometry, PixelPolyline)
        and not proposal.geometry.closed
        and len(proposal.geometry.points) >= gabarito.min_vertex_count
    ]
    if not candidates:
        return StepFidelityReport(
            element_found=False,
            single_element=False,
            vertex_count=0,
            jog_transition_found=False,
            step_preserved=False,
            notes=["STEP_ELEMENT_NOT_FOUND"],
        )

    single_element = len(candidates) == 1
    candidate_geometry = candidates[0].geometry
    # Já filtrado acima: só `PixelPolyline` entra em `candidates`. Reafirmar aqui é o que
    # deixa o mypy estreitar o `Union` — a comprehension não propaga o isinstance para fora.
    assert isinstance(candidate_geometry, PixelPolyline)
    points = [(vertex.x, vertex.y) for vertex in candidate_geometry.points]
    vertex_count = len(points)

    # Cada ponto vai para o trecho cuja reta (do gabarito) ele fica mais perto — não um corte
    # ingênuo por x, que empataria os dois vértices do cotovelo no mesmo lado. Os rótulos são
    # mantidos na ordem original: é o que permite achar o PAR CONSECUTIVO que muda de trecho.
    labels = [
        "a"
        if abs(_step_line_offset(point, axis_a_start, axis_a_end))
        <= abs(_step_line_offset(point, axis_b_start, axis_b_end))
        else "b"
        for point in points
    ]
    points_a = [point for point, label in zip(points, labels, strict=True) if label == "a"]
    points_b = [point for point, label in zip(points, labels, strict=True) if label == "b"]

    offset_a = (
        sum(_step_line_offset(point, axis_a_start, axis_a_end) for point in points_a)
        / len(points_a)
        if points_a
        else None
    )
    offset_b = (
        sum(_step_line_offset(point, axis_a_start, axis_a_end) for point in points_b)
        / len(points_b)
        if points_b
        else None
    )

    # Transição estrutural: par CONSECUTIVO que muda de trecho com pouco deslocamento AO
    # LONGO do eixo — é isso que distingue um cotovelo de uma rampa que também cruza de lado,
    # só que espalhada por muitos pixels.
    jog_transition_found = False
    transition_registration_offset_px: float | None = None
    for index in range(len(points) - 1):
        if labels[index] == labels[index + 1]:
            continue
        along_axis_separation = abs(
            _step_axis_projection(points[index + 1], axis_a_start, axis_a_end)
            - _step_axis_projection(points[index], axis_a_start, axis_a_end)
        )
        if along_axis_separation <= tolerance:
            jog_transition_found = True
            # Diagnóstico, não gate: o quanto o cotovelo encontrado está longe da posição
            # absoluta do gabarito — sinal de deslocamento de registro, para a revisão olhar.
            transition_registration_offset_px = min(
                math.dist(points[index], jog_vertex_px),
                math.dist(points[index + 1], jog_vertex_px),
            )
            break

    notes: list[str] = []
    if not single_element:
        notes.append(f"STEP_MULTIPLE_CANDIDATES:{len(candidates)}")
    if offset_a is None or offset_b is None:
        notes.append("STEP_SEGMENT_MISSING")
    elif abs(offset_a - offset_b) <= tolerance:
        notes.append(f"STEP_FLATTENED:offset_delta_px={round(abs(offset_a - offset_b), 2)}")
    if not jog_transition_found:
        notes.append("STEP_JOG_TRANSITION_NOT_FOUND")
    elif transition_registration_offset_px is not None:
        notes.append(
            "STEP_JOG_TRANSITION_REGISTRATION_OFFSET_PX:"
            f"{round(transition_registration_offset_px, 2)}"
        )

    step_preserved = (
        single_element
        and offset_a is not None
        and offset_b is not None
        and abs(offset_a - offset_b) > tolerance
        and jog_transition_found
    )
    return StepFidelityReport(
        element_found=True,
        single_element=single_element,
        vertex_count=vertex_count,
        offset_a_px=round(offset_a, 2) if offset_a is not None else None,
        offset_b_px=round(offset_b, 2) if offset_b is not None else None,
        jog_transition_found=jog_transition_found,
        step_preserved=step_preserved,
        notes=notes,
    )


def build_degrau_step_gabarito() -> StepGabarito:
    """Deriva o gabarito do degrau das MESMAS constantes que desenham a fixture sintética.

    Nenhuma coordenada aqui é digitada de novo: `synthetic.DEGRAU_WALL_VERTICES_PX` é o
    traço que `render_degrau_boundary_input` desenha, e a normalização só divide pelo
    tamanho da folha.
    """
    from croquito_worker.synthetic import (
        DEGRAU_PAGE_HEIGHT_PX,
        DEGRAU_PAGE_WIDTH_PX,
        DEGRAU_WALL_VERTICES_PX,
    )

    width, height = DEGRAU_PAGE_WIDTH_PX, DEGRAU_PAGE_HEIGHT_PX
    start, elbow_high, elbow_low, end = DEGRAU_WALL_VERTICES_PX

    def normalize(point: tuple[int, int]) -> StepFidelityPoint:
        return StepFidelityPoint(x=point[0] / width, y=point[1] / height)

    return StepGabarito(
        image_width_px=width,
        image_height_px=height,
        segment_a=StepFidelitySegment(start=normalize(start), end=normalize(elbow_high)),
        segment_b=StepFidelitySegment(start=normalize(elbow_low), end=normalize(end)),
        jog_vertex=normalize(elbow_low),
    )


class ExtractionArmReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    provider: str
    model_id: str
    prompt_version: str
    element_count: int = Field(ge=0)
    ink_coverage_mean: float = Field(ge=0, le=1)
    corroborated_rate: float = Field(ge=0, le=1)
    closed_region_count: int = Field(ge=0)
    labelled_rate: float = Field(ge=0, le=1)
    layered_rate: float = Field(ge=0, le=1)
    latency_ms: int = Field(ge=0)
    estimated_cost_usd: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    notes: list[str]
    # Só o registro preenche: a eval bruta não tem antes/depois para declarar.
    proposal_registration: list[ProposalRegistrationReport] = Field(default_factory=list)
    # Só preenchido quando a eval roda com `step_gabarito`: nem toda fixture tem degrau.
    step: StepFidelityReport | None = None


class ExtractionEvalReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    image_sha256: str
    arms: list[ExtractionArmReport]
    thresholds: dict[str, float]
    passed: bool


def allowlisted_digests() -> frozenset[str]:
    return frozenset(
        digest.strip().lower()
        for digest in os.getenv("CROQUITO_AI_EXTRACTION_ALLOWED_DIGESTS", "").split(",")
        if digest.strip()
    )


def bind_page_to_document(manifest_path: Path, page_sha256: str) -> str:
    """Liga o render da página ao documento do manifest e devolve o digest de origem.

    É a metade **estrutural** de `authorize_page`: prova que o PNG que vai ser enviado é
    uma página daquele documento, e nada mais. Ela existe separada porque há mais de uma
    forma de consentimento no repositório — a allowlist por ambiente (`authorize_page`) e o
    ato de upload do próprio orçamentista no servidor local —, e as duas precisam do MESMO
    amarrado página↔documento antes de qualquer byte sair da máquina. Quem dispensa a
    allowlist não pode dispensar este vínculo: sem ele, um PNG largado no diretório viraria
    evidência de um documento que ninguém enviou.
    """
    manifest = json.loads(manifest_path.read_text())
    source_sha256 = str(manifest.get("source_sha256", "")).lower()
    if page_sha256.lower() not in {
        str(page.get("image_sha256", "")).lower() for page in manifest.get("pages", [])
    }:
        raise ExtractionNotAllowlistedError(
            "A imagem não pertence ao manifest informado: o render não pode ser ligado a "
            "um documento autorizado."
        )
    return source_sha256


def authorize_page(manifest_path: Path, page_sha256: str) -> str:
    """Liga o render da página ao documento autorizado e devolve o digest de origem.

    A allowlist vale sobre o **documento**, não sobre um PNG derivado dele: autorizar o
    render permitiria enviar qualquer imagem que alguém colocasse na pasta. É o mesmo
    amarrado que o `seed-review` faz entre evidência e upload.
    """
    source_sha256 = bind_page_to_document(manifest_path, page_sha256)
    if source_sha256 not in allowlisted_digests():
        raise ExtractionNotAllowlistedError(
            f"Documento fora da allowlist de extração ({source_sha256[:12]}…): defina "
            "CROQUITO_AI_EXTRACTION_ALLOWED_DIGESTS antes de enviar para um provider "
            "externo."
        )
    return source_sha256


def _coverage_stats(
    proposals: list[VisionProposal], minimum_coverage: float
) -> tuple[float, float]:
    total = len(proposals)
    if not total:
        return 0.0, 0.0
    coverages = [proposal.quality_score for proposal in proposals]
    corroborated = [value for value in coverages if value >= minimum_coverage]
    return round(sum(coverages) / total, 4), round(len(corroborated) / total, 4)


def _arm_report(
    candidate: ExtractionCandidate,
    proposals: list[VisionProposal],
    *,
    execution_provider: str,
    model_id: str,
    prompt_version: str,
    latency_ms: int,
    estimated_cost_usd: float | None,
    input_tokens: int | None,
    output_tokens: int | None,
    notes: list[str],
    minimum_coverage: float,
    step: StepFidelityReport | None = None,
) -> ExtractionArmReport:
    total = len(proposals)
    ink_coverage_mean, corroborated_rate = _coverage_stats(proposals, minimum_coverage)
    return ExtractionArmReport(
        name=candidate.name,
        provider=execution_provider,
        model_id=model_id,
        prompt_version=prompt_version,
        element_count=total,
        ink_coverage_mean=ink_coverage_mean,
        corroborated_rate=corroborated_rate,
        closed_region_count=sum(
            1
            for proposal in proposals
            if isinstance(proposal.geometry, PixelPolyline) and proposal.geometry.closed
        ),
        labelled_rate=(
            round(sum(1 for item in proposals if item.label) / total, 4) if total else 0.0
        ),
        layered_rate=(
            round(sum(1 for item in proposals if item.layer_hint) / total, 4) if total else 0.0
        ),
        latency_ms=latency_ms,
        estimated_cost_usd=estimated_cost_usd,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        notes=notes,
        step=step,
    )


def run_extraction_eval(
    image_path: Path,
    candidates: list[ExtractionCandidate],
    output_dir: Path,
    *,
    manifest_path: Path,
    config: VisionConfig | None = None,
    minimum_corroborated_rate: float = 0.7,
    step_gabarito: StepGabarito | None = None,
) -> tuple[ExtractionEvalReport, Path]:
    """Roda o mesmo pedido em cada eixo e mede a saída contra a tinta do próprio croqui.

    Desde 2026-08-19, cada eixo passa por `register_to_ink` ANTES de `corroborate_with_ink`
    — SEMPRE, não só quando `step_gabarito` é informado. É a mesma ordem e a mesma config
    que `provider_review.build_provider_review_snapshot` usa na cadeia real: sem registro,
    a eval mede deslocamento GLOBAL de enquadramento que a produção corrige antes de
    qualquer leitura chegar à revisão humana — não é o que o usuário final recebe. O
    achado que motivou: o candidato `geometry-extraction@2.0.2` devolveu o muro-degrau
    estruturalmente certo, mas com ~12 px de deslocamento global, e ficava com
    `corroborated_rate=0.5` contra tolerância de 9 px sem este registro.

    Números de `corroborated_rate`/`ink_coverage_mean` de antes desta mudança NÃO são
    comparáveis aos de depois — rodadas históricas registradas em Model Routing foram
    medidas sem este registro prévio.
    """
    effective_config = config or VisionConfig()
    output_dir.mkdir(parents=True, exist_ok=True)
    source = image_path.resolve(strict=True)
    # A allowlist vale sobre o documento de origem; o lineage registra o que trafegou.
    image_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    authorize_page(manifest_path, image_sha256)

    payload, width, height = prepare_transmission(source)
    request = build_request(
        PromptTask.GEOMETRY_EXTRACTION,
        image_bytes=payload,
        image_sha256=hashlib.sha256(payload).hexdigest(),
        image_width_px=width,
        image_height_px=height,
        region_label="main_plan",
    )
    arms: list[ExtractionArmReport] = []
    for candidate in candidates:
        execution = candidate.adapter.execute(request)
        if not isinstance(execution.output, GeometryExtractionOutput):
            raise ValueError(f"{candidate.name} não devolveu contrato de geometria")
        proposals = proposals_from_geometry(
            execution.output.elements,
            image_digest=image_sha256,
            width=width,
            height=height,
        )
        notes: list[str] = []
        if proposals:
            # Espelha `provider_review.build_provider_review_snapshot`: registro ANTES da
            # corroboração, mesma ordem e mesma config. Um eval que corrobora geometria
            # crua mede deslocamento GLOBAL de registro que a produção corrige antes de
            # qualquer leitura chegar à revisão — não é o que o usuário final recebe.
            proposals, registration = register_to_ink(proposals, source, config=effective_config)
            notes.append(
                f"INK_REGISTRATION:{registration.coverage_before:.3f}"
                f"->{registration.coverage_after:.3f}"
                f"->{registration.coverage_refined:.3f}"
            )
        corroborated, ink_notes = corroborate_with_ink(proposals, source, config=effective_config)
        notes.extend(ink_notes)
        step_report = (
            assess_step_fidelity(corroborated, step_gabarito) if step_gabarito is not None else None
        )
        arms.append(
            _arm_report(
                candidate,
                corroborated,
                execution_provider=execution.provider.value,
                model_id=execution.model_id,
                prompt_version=execution.prompt.prompt_version,
                latency_ms=execution.latency_ms,
                estimated_cost_usd=(
                    float(execution.usage.estimated_cost_usd)
                    if execution.usage.estimated_cost_usd is not None
                    else None
                ),
                input_tokens=execution.usage.input_tokens,
                output_tokens=execution.usage.output_tokens,
                notes=notes,
                minimum_coverage=effective_config.ink_corroboration_min_coverage,
                step=step_report,
            )
        )
        atomic_write_text(
            output_dir / f"{candidate.name}-proposals.json",
            json.dumps(
                [item.model_dump(mode="json") for item in corroborated],
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )

    thresholds = {"corroborated_rate": minimum_corroborated_rate}
    if step_gabarito is not None:
        thresholds["step_preserved"] = 1.0
    report = ExtractionEvalReport(
        image_sha256=image_sha256,
        arms=arms,
        thresholds=thresholds,
        # Um eixo que propõe geometria sem tinta por baixo reprova: é o sinal de invenção.
        # Um eixo que achata o degrau reprova mesmo com tinta alta: é o sinal de topologia
        # perdida, que a corroboração sozinha não vê.
        passed=bool(arms)
        and all(arm.corroborated_rate >= minimum_corroborated_rate for arm in arms)
        and (
            step_gabarito is None
            or all(arm.step is not None and arm.step.step_preserved for arm in arms)
        ),
    )
    report_path = output_dir / "extraction-eval.json"
    atomic_write_text(
        report_path,
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
    )
    return report, report_path


def register_extraction_arms(
    output_dir: Path,
    image_path: Path,
    *,
    config: VisionConfig | None = None,
) -> tuple[ExtractionEvalReport, Path]:
    """Assenta as propostas já pagas sobre a tinta e remede, sem nova chamada externa.

    Modelos de visão acertam a estrutura e erram o registro; `register_to_ink` corrige
    enquadramento (uma transformação global por eixo de comparação) e depois reassenta cada
    elemento sozinho dentro do ajuste que o tipo dele autoriza — sem poder inventar
    geometria. A taxa original fica preservada em nota e a tabela por proposta guarda o
    antes/depois de cada elemento, para o relatório continuar auditável linha a linha.
    """
    effective_config = config or VisionConfig()
    report_path = output_dir / "extraction-eval.json"
    report = ExtractionEvalReport.model_validate(json.loads(report_path.read_text()))
    source = image_path.resolve(strict=True)
    image_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    if image_sha256 != report.image_sha256:
        raise ValueError("imagem não corresponde ao relatório da eval: registro recusado")
    proposals_adapter = TypeAdapter(list[VisionProposal])
    minimum_coverage = effective_config.ink_corroboration_min_coverage
    arms: list[ExtractionArmReport] = []
    for arm in report.arms:
        proposals = proposals_adapter.validate_json(
            (output_dir / f"{arm.name}-proposals.json").read_text()
        )
        registered, registration = register_to_ink(proposals, source, config=effective_config)
        corroborated, notes = corroborate_with_ink(registered, source, config=effective_config)
        atomic_write_text(
            output_dir / f"{arm.name}-registered.json",
            json.dumps(
                [item.model_dump(mode="json") for item in corroborated],
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )
        ink_coverage_mean, corroborated_rate = _coverage_stats(corroborated, minimum_coverage)
        refined_count = sum(1 for item in registration.elements if item.refinement != "none")
        constrained_count = sum(1 for item in registration.elements if item.order_constrained)
        unresolved = [item.proposal_id for item in registration.elements if item.order_unresolved]
        arms.append(
            arm.model_copy(
                update={
                    "ink_coverage_mean": ink_coverage_mean,
                    "corroborated_rate": corroborated_rate,
                    "notes": [
                        *notes,
                        f"CORROBORATED_BEFORE_REGISTRATION:{arm.corroborated_rate}",
                        # `rot` é o ângulo realmente aplicado: quarto de volta mais o
                        # desvio fino. Registrar só o quarto esconderia a folha torta.
                        "REGISTERED:"
                        f"rot={round(registration.total_rotation_degrees, 4)};"
                        f"sx={round(registration.scale_x, 4)};"
                        f"sy={round(registration.scale_y, 4)};"
                        f"dx={round(registration.offset_x, 2)};"
                        f"dy={round(registration.offset_y, 2)}",
                        "REFINED:"
                        f"global={registration.coverage_after};"
                        f"refined={registration.coverage_refined};"
                        f"moved={refined_count}/{len(registration.elements)}",
                        # A ordem traçada é invariante do registro: quantos elementos a
                        # ordem obrigou a mover e quais ficaram sem colocação compatível.
                        "ORDER_GUARD:"
                        f"relocated={constrained_count}/{len(registration.elements)};"
                        f"unresolved={len(unresolved)}"
                        + (f":{','.join(unresolved)}" if unresolved else ""),
                    ],
                    "proposal_registration": [
                        ProposalRegistrationReport(
                            proposal_id=element.proposal_id,
                            label=element.label,
                            kind=element.kind,
                            coverage_raw=element.coverage_raw,
                            coverage_global=element.coverage_global,
                            coverage_refined=element.coverage_refined,
                            base=element.base,
                            refinement=element.refinement,
                            centre_shift_px=element.centre_shift_px,
                            radius_delta_px=element.radius_delta_px,
                            orientation_delta_degrees=element.orientation_delta_degrees,
                            # Vazio quando o ajuste não foi por aresta: quatro zeros num
                            # círculo sugeririam uma busca que não houve.
                            edge_shifts_px=(
                                list(element.edge_shifts_px)
                                if element.refinement == "edges"
                                else []
                            ),
                            tip_shifts_px=(
                                list(element.tip_shifts_px) if element.refinement == "tips" else []
                            ),
                            order_constrained=element.order_constrained,
                            order_unresolved=element.order_unresolved,
                        )
                        for element in registration.elements
                    ],
                }
            )
        )
    minimum_rate = report.thresholds.get("corroborated_rate", 0.7)
    updated = ExtractionEvalReport(
        image_sha256=report.image_sha256,
        arms=arms,
        thresholds=report.thresholds,
        passed=bool(arms) and all(arm.corroborated_rate >= minimum_rate for arm in arms),
    )
    atomic_write_text(
        report_path,
        json.dumps(updated.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
    )
    return updated, report_path
