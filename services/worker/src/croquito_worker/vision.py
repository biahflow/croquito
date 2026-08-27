"""Propostas geométricas em pixels; nunca medidas ou entidades CAD aprovadas."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, replace
from itertools import pairwise
from pathlib import Path
from typing import Annotated, Any, Final, Literal, Protocol

import cv2
import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from croquito_worker.io_utils import atomic_write_text

DETECTOR_VERSION: Final = "opencv-proposals-v1"

GEOMETRY_EXTRACTION_ALGORITHM: Final = "provider-geometry-extraction-v1"
"""Marca a proposta que veio de um modelo, para a auditoria não confundir com Hough."""


class GeometryElementLike(Protocol):
    """Forma mínima de um elemento de geometria; evita o worker importar providers aqui.

    Propriedades e não atributos: atributo de Protocol é invariante, e os campos concretos
    são `Literal`, que não satisfaz `str` nessa posição.
    """

    @property
    def label(self) -> str: ...
    @property
    def kind(self) -> str: ...
    @property
    def layer_hint(self) -> str: ...
    @property
    def closed(self) -> bool: ...
    @property
    def vertices(self) -> list[Any]: ...
    @property
    def center(self) -> Any | None: ...
    @property
    def radius(self) -> float | None: ...
    # Âncoras do arco: presentes só a partir de `geometry-extraction@2.0.0`, e sempre as
    # três juntas ou nenhuma. Opcionais aqui porque artefato gravado sob o contrato antigo
    # continua atravessando esta conversão sem ganhar ângulo que ninguém observou.
    @property
    def arc_start(self) -> Any | None: ...
    @property
    def arc_mid(self) -> Any | None: ...
    @property
    def arc_end(self) -> Any | None: ...


class VisionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class PixelPoint(VisionModel):
    x: float = Field(ge=0)
    y: float = Field(ge=0)


class PixelLine(VisionModel):
    type: Literal["line"] = "line"
    start: PixelPoint
    end: PixelPoint


class PixelCircle(VisionModel):
    type: Literal["circle"] = "circle"
    center: PixelPoint
    radius: float = Field(gt=0)


class PixelPolyline(VisionModel):
    type: Literal["polyline"] = "polyline"
    # 200 pontos acompanha o teto do contrato de geometria; o limite antigo de 40 recusaria
    # um contorno detalhado. `closed` deixou de ser sempre verdadeiro porque muro e limite
    # de lote raramente fecham, e fechá-los à força inventaria geometria.
    points: list[PixelPoint] = Field(min_length=3, max_length=200)
    closed: bool = True


PixelGeometryValue = PixelLine | PixelCircle | PixelPolyline

PixelGeometry = Annotated[
    PixelGeometryValue,
    Field(discriminator="type"),
]


class VisionProposal(VisionModel):
    id: str = Field(pattern=r"^vp_[a-f0-9]{16}$")
    kind: Literal["line", "circle", "contour"]
    geometry: PixelGeometry
    algorithm: str
    # Opcional desde o ADR-0050 (decisão 2): mede confiança de DETECTOR, e para uma forma
    # que uma pessoa desenhou não existe número honesto a pôr aqui. `1.0` seria afirmar
    # certeza máxima justamente onde não houve medição nenhuma; ausência é o que se sabe.
    # Aditivo, no mesmo idioma de `arc_angles_observed`: artefato antigo continua válido.
    quality_score: float | None = Field(default=None, ge=0, le=1)
    precision: Literal["unresolved"] = "unresolved"
    export: Literal[False] = False
    # Semântica observada, quando a proposta vem de um modelo. Opcional: o caminho
    # determinístico não sabe o que uma linha representa, e não deve fingir que sabe.
    label: str | None = Field(default=None, max_length=120)
    layer_hint: str | None = Field(default=None, max_length=40)
    # A janela angular deste arco veio de âncoras observadas, não da meia-volta fabricada.
    # Aditivo com default para artefato antigo continuar validando: ausência é exatamente o
    # que ele declara — ninguém observou. É o que autoriza o refino a apenas LAPIDAR a
    # orientação, em vez de reconquistá-la varrendo a volta inteira.
    arc_angles_observed: bool = False
    # De quais propostas OBSERVADAS esta forma nasceu (ADR-0050, decisão 3). Vazio em toda
    # proposta de máquina; obrigatório e não vazio na correção humana — sem forma de origem
    # não há correção, há desenho livre, e desenho livre é CAD, não revisão.
    #
    # Não existe o par `superseded_by` no fragmento (decisão 4): "superada" é derivado
    # desta relação, e um campo gravado que duplica a relação acaba discordando dela.
    derived_from: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("derived_from")
    @classmethod
    def validate_derived_from(cls, value: list[str]) -> list[str]:
        for proposal_id in value:
            if not re.fullmatch(r"vp_[a-f0-9]{16}", proposal_id):
                raise ValueError(f"derivação aponta para id inválido: {proposal_id}")
        if len(set(value)) != len(value):
            raise ValueError("derivação repete a mesma proposta")
        return value


class VisionProposalSet(VisionModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    dataset_id: str
    page_number: int = Field(ge=1)
    image_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    image_width_px: int = Field(gt=0)
    image_height_px: int = Field(gt=0)
    coordinate_space: Literal["source_image_pixels"] = "source_image_pixels"
    # O conjunto declara quem o produziu: o detector OpenCV local ou a extração de
    # geometria por provider registrada na tinta. Cada proposta segue carregando o
    # próprio `algorithm`; nada aqui muda os invariantes (`unresolved`, export=false).
    # `human-correction-v1` é o conjunto de proveniência própria da correção humana
    # (ADR-0050, decisão 1): não se cria um tipo paralelo, porque associação, calibração e
    # solver consomem `VisionProposal` e um segundo formato duplicaria, em três lugares, os
    # invariantes `unresolved`/`export=false` que nunca podem divergir.
    detector_version: Literal[
        "opencv-proposals-v1",
        "provider-geometry-extraction-v1",
        "human-correction-v1",
    ] = DETECTOR_VERSION
    configured_limits: dict[str, int]
    limit_reached: list[str]
    proposals: list[VisionProposal]
    safety_notes: list[str] = Field(min_length=3)

    @field_validator("dataset_id")
    @classmethod
    def validate_dataset_id(cls, value: str) -> str:
        if not value or len(value) > 64:
            raise ValueError("dataset_id inválido")
        return value

    @model_validator(mode="after")
    def validate_derivation_matches_provenance(self) -> VisionProposalSet:
        """Derivação e proveniência dizem a mesma coisa, ou o conjunto não é válido.

        Correção humana SEM origem seria desenho livre (ADR-0050, decisão 3); proposta de
        máquina COM origem seria uma observação afirmando derivar de outra, que é o
        contrário do que o detector faz. As duas metades da regra moram aqui porque é o
        conjunto que declara quem o produziu.
        """
        correcao = self.detector_version == "human-correction-v1"
        for proposal in self.proposals:
            if correcao and not proposal.derived_from:
                raise ValueError(
                    f"correção humana sem forma de origem: {proposal.id}",
                )
            if not correcao and proposal.derived_from:
                raise ValueError(
                    f"proposta de máquina não deriva de outra: {proposal.id}",
                )
        return self


@dataclass(frozen=True)
class VisionConfig:
    max_dimension: int = 2200
    max_lines: int = 80
    max_circles: int = 16
    max_contours: int = 16
    line_angle_tolerance_degrees: float = 4.0
    line_distance_tolerance_ratio: float = 0.006
    line_gap_tolerance_ratio: float = 0.025
    circle_min_support: float = 0.83
    suppress_handwriting: bool = True
    handwriting_max_height_ratio: float = 0.045
    handwriting_min_density: float = 0.16
    clip_to_drawing_region: bool = True
    drawing_region_min_area_ratio: float = 0.15
    drawing_region_margin_px: float = 12.0
    ink_corroboration_tolerance_px: int = 9
    ink_corroboration_min_coverage: float = 0.6
    ink_corroboration_samples: int = 64


@dataclass
class _Segment:
    angle: float
    rho: float
    start_t: float
    end_t: float
    support: float

    @property
    def length(self) -> float:
        return self.end_t - self.start_t


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _proposal_id(image_digest: str, kind: str, geometry: VisionModel) -> str:
    canonical = json.dumps(geometry.model_dump(), sort_keys=True, separators=(",", ":"))
    value = hashlib.sha256(f"{image_digest}:{kind}:{canonical}".encode()).hexdigest()[:16]
    return f"vp_{value}"


def _resize_for_detection(image: np.ndarray, max_dimension: int) -> tuple[np.ndarray, float]:
    height, width = image.shape[:2]
    scale = min(1.0, max_dimension / max(height, width))
    if scale == 1.0:
        return image, scale
    resized = cv2.resize(
        image,
        (round(width * scale), round(height * scale)),
        interpolation=cv2.INTER_AREA,
    )
    return resized, scale


def _ink_mask(image: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    grayscale = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(grayscale, (5, 5), 0)
    adaptive = cv2.adaptiveThreshold(
        blurred,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        41,
        13,
    )
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    saturation = hsv[:, :, 1]
    value = hsv[:, :, 2]
    colored_ink = np.where((saturation > 35) & (value < 252), 255, 0).astype(np.uint8)
    mask = cv2.bitwise_or(adaptive, colored_ink)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    return grayscale, mask


def _segment_from_points(x1: float, y1: float, x2: float, y2: float) -> _Segment:
    angle = math.atan2(y2 - y1, x2 - x1) % math.pi
    unit_x, unit_y = math.cos(angle), math.sin(angle)
    normal_x, normal_y = -unit_y, unit_x
    first_t = x1 * unit_x + y1 * unit_y
    second_t = x2 * unit_x + y2 * unit_y
    midpoint_x = (x1 + x2) / 2
    midpoint_y = (y1 + y2) / 2
    rho = midpoint_x * normal_x + midpoint_y * normal_y
    return _Segment(
        angle=angle,
        rho=rho,
        start_t=min(first_t, second_t),
        end_t=max(first_t, second_t),
        support=math.hypot(x2 - x1, y2 - y1),
    )


def _angle_difference(first: float, second: float) -> float:
    difference = abs(first - second)
    return min(difference, math.pi - difference)


def _merge_segments(
    segments: list[_Segment],
    *,
    angle_tolerance: float,
    distance_tolerance: float,
    gap_tolerance: float,
) -> list[_Segment]:
    merged: list[_Segment] = []
    for candidate in sorted(segments, key=lambda segment: segment.length, reverse=True):
        match: _Segment | None = None
        for existing in merged:
            gap = max(
                0.0,
                max(existing.start_t, candidate.start_t) - min(existing.end_t, candidate.end_t),
            )
            if (
                _angle_difference(existing.angle, candidate.angle) <= angle_tolerance
                and abs(existing.rho - candidate.rho) <= distance_tolerance
                and gap <= gap_tolerance
            ):
                match = existing
                break
        if match is None:
            merged.append(candidate)
            continue
        combined_support = match.support + candidate.support
        match.rho = (
            match.rho * match.support + candidate.rho * candidate.support
        ) / combined_support
        match.start_t = min(match.start_t, candidate.start_t)
        match.end_t = max(match.end_t, candidate.end_t)
        match.support = combined_support
    return merged


def _line_proposals(
    mask: np.ndarray,
    image_digest: str,
    inverse_scale: float,
    config: VisionConfig,
) -> list[VisionProposal]:
    height, width = mask.shape
    minimum_dimension = min(width, height)
    diagonal = math.hypot(width, height)
    raw_lines = cv2.HoughLinesP(
        mask,
        rho=1,
        theta=math.pi / 360,
        threshold=max(45, round(minimum_dimension * 0.045)),
        minLineLength=max(70, round(minimum_dimension * 0.09)),
        maxLineGap=max(12, round(minimum_dimension * 0.018)),
    )
    if raw_lines is None:
        return []
    segments = [
        _segment_from_points(float(x1), float(y1), float(x2), float(y2))
        for line in raw_lines
        for x1, y1, x2, y2 in [line[0]]
    ]
    merged = _merge_segments(
        segments,
        angle_tolerance=math.radians(config.line_angle_tolerance_degrees),
        distance_tolerance=max(5.0, minimum_dimension * config.line_distance_tolerance_ratio),
        gap_tolerance=max(18.0, minimum_dimension * config.line_gap_tolerance_ratio),
    )
    proposals: list[VisionProposal] = []
    for segment in sorted(merged, key=lambda item: item.length, reverse=True)[: config.max_lines]:
        unit_x, unit_y = math.cos(segment.angle), math.sin(segment.angle)
        normal_x, normal_y = -unit_y, unit_x
        x1 = (segment.start_t * unit_x + segment.rho * normal_x) * inverse_scale
        y1 = (segment.start_t * unit_y + segment.rho * normal_y) * inverse_scale
        x2 = (segment.end_t * unit_x + segment.rho * normal_x) * inverse_scale
        y2 = (segment.end_t * unit_y + segment.rho * normal_y) * inverse_scale
        geometry = PixelLine(
            start=PixelPoint(x=max(0, x1), y=max(0, y1)),
            end=PixelPoint(x=max(0, x2), y=max(0, y2)),
        )
        score = min(1.0, segment.length / (diagonal * 0.55))
        proposals.append(
            VisionProposal(
                id=_proposal_id(image_digest, "line", geometry),
                kind="line",
                geometry=geometry,
                algorithm="probabilistic_hough+collinear_merge",
                quality_score=round(score, 4),
            )
        )
    return proposals


def _circle_support(mask: np.ndarray, center_x: float, center_y: float, radius: float) -> float:
    height, width = mask.shape
    supported = 0
    samples = 180
    search_radius = max(2, round(min(width, height) * 0.0025))
    for index in range(samples):
        angle = 2 * math.pi * index / samples
        x = round(center_x + radius * math.cos(angle))
        y = round(center_y + radius * math.sin(angle))
        x1, x2 = max(0, x - search_radius), min(width, x + search_radius + 1)
        y1, y2 = max(0, y - search_radius), min(height, y + search_radius + 1)
        if x1 < x2 and y1 < y2 and np.any(mask[y1:y2, x1:x2] > 0):
            supported += 1
    return supported / samples


def _circle_proposals(
    grayscale: np.ndarray,
    mask: np.ndarray,
    image_digest: str,
    inverse_scale: float,
    config: VisionConfig,
) -> list[VisionProposal]:
    height, width = grayscale.shape
    minimum_dimension = min(width, height)
    smoothed = cv2.medianBlur(grayscale, 5)
    raw_circles = cv2.HoughCircles(
        smoothed,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=max(50, round(minimum_dimension * 0.08)),
        param1=110,
        param2=29,
        minRadius=max(12, round(minimum_dimension * 0.012)),
        maxRadius=max(30, round(minimum_dimension * 0.28)),
    )
    if raw_circles is None:
        return []
    candidates: list[tuple[float, float, float, float]] = []
    for center_x, center_y, radius in raw_circles[0]:
        support = _circle_support(mask, float(center_x), float(center_y), float(radius))
        if support >= config.circle_min_support:
            candidates.append((support, float(center_x), float(center_y), float(radius)))

    selected: list[tuple[float, float, float, float]] = []
    for candidate in sorted(candidates, reverse=True):
        _, center_x, center_y, radius = candidate
        duplicate = any(
            math.hypot(center_x - other_x, center_y - other_y) < minimum_dimension * 0.025
            and abs(radius - other_radius) < minimum_dimension * 0.02
            for _, other_x, other_y, other_radius in selected
        )
        if not duplicate:
            selected.append(candidate)
        if len(selected) >= config.max_circles:
            break

    proposals: list[VisionProposal] = []
    for support, center_x, center_y, radius in selected:
        geometry = PixelCircle(
            center=PixelPoint(x=center_x * inverse_scale, y=center_y * inverse_scale),
            radius=radius * inverse_scale,
        )
        proposals.append(
            VisionProposal(
                id=_proposal_id(image_digest, "circle", geometry),
                kind="circle",
                geometry=geometry,
                algorithm="gradient_hough+edge_support",
                quality_score=round(support, 4),
            )
        )
    return proposals


def _contour_proposals(
    mask: np.ndarray,
    image_digest: str,
    inverse_scale: float,
    config: VisionConfig,
) -> list[VisionProposal]:
    height, width = mask.shape
    image_area = width * height
    connected = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    contours, _hierarchy = cv2.findContours(
        connected,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE,
    )
    candidates: list[tuple[float, np.ndarray]] = []
    for contour in contours:
        area = abs(cv2.contourArea(contour))
        if area < image_area * 0.004 or area > image_area * 0.88:
            continue
        perimeter = cv2.arcLength(contour, True)
        if perimeter <= 0:
            continue
        circularity = 4 * math.pi * area / (perimeter * perimeter)
        if circularity > 0.78:
            continue
        approximation = cv2.approxPolyDP(contour, 0.012 * perimeter, True)
        point_count = len(approximation)
        if point_count < 3 or point_count > 40:
            continue
        quality = min(1.0, area / (image_area * 0.15))
        candidates.append((quality, approximation))

    proposals: list[VisionProposal] = []
    for quality, approximation in sorted(candidates, key=lambda item: item[0], reverse=True)[
        : config.max_contours
    ]:
        geometry = PixelPolyline(
            points=[
                PixelPoint(
                    x=float(point[0][0]) * inverse_scale,
                    y=float(point[0][1]) * inverse_scale,
                )
                for point in approximation
            ]
        )
        proposals.append(
            VisionProposal(
                id=_proposal_id(image_digest, "contour", geometry),
                kind="contour",
                geometry=geometry,
                algorithm="morphological_close+contour_approximation",
                quality_score=round(quality, 4),
            )
        )
    return proposals


def _suppress_circle_like_contours(
    contours: list[VisionProposal],
    circles: list[VisionProposal],
) -> list[VisionProposal]:
    circle_geometries = [
        proposal.geometry for proposal in circles if isinstance(proposal.geometry, PixelCircle)
    ]
    filtered: list[VisionProposal] = []
    for proposal in contours:
        geometry = proposal.geometry
        if not isinstance(geometry, PixelPolyline):
            filtered.append(proposal)
            continue
        xs = [point.x for point in geometry.points]
        ys = [point.y for point in geometry.points]
        center_x = (min(xs) + max(xs)) / 2
        center_y = (min(ys) + max(ys)) / 2
        width = max(xs) - min(xs)
        height = max(ys) - min(ys)
        duplicates_circle = any(
            math.hypot(center_x - circle.center.x, center_y - circle.center.y)
            <= circle.radius * 0.45
            and 1.3 * circle.radius <= width <= 2.8 * circle.radius
            and 1.3 * circle.radius <= height <= 2.8 * circle.radius
            for circle in circle_geometries
        )
        if not duplicates_circle:
            filtered.append(proposal)
    return filtered


ARC_SAMPLES: Final = 24
"""Segmentos usados para amostrar um arco: não existe arco no espaço de pixels."""

ARC_OBSERVED_MIN_SWEEP_DEGREES: Final = 10.0
"""Varredura mínima entre as âncoras para a janela observada valer como observação.

Abaixo disso as três âncoras cabem na espessura do traço: a diferença angular é ruído de
leitura, não abertura observada, e usá-la produziria um toco de arco no lugar da forma. O
elemento cai no fallback fabricado, que é declaradamente um chute e será reconquistado
contra a tinta.
"""

ARC_OBSERVED_MIN_ANCHOR_RADIUS_PX: Final = 1.0
"""Distância mínima entre âncora e centro para o ângulo dela existir.

Âncora sobre o centro não tem direção: `atan2(0, 0)` devolve 0 e o arco sairia apontando
para um lado que ninguém observou. Preferir o fallback declarado a fabricar em silêncio.
"""


def _circumcircle(
    first: PixelPoint, second: PixelPoint, third: PixelPoint
) -> tuple[float, float, float] | None:
    """Centro (x, y) e raio do círculo pelos três pontos; `None` quando colineares.

    É o que permite ao contrato aceitar arco só de âncoras: três pontos determinam o
    círculo, então center/radius omitidos pelo modelo saem daqui — deterministicamente e
    em pixels, no espaço onde a geometria vive. Devolve floats crus porque o circuncentro
    de um arco raso pode cair FORA da página, e `PixelPoint` (ge=0) recusaria a
    coordenada; só os pontos amostrados da curva voltam presos aos limites da folha.
    """
    determinant = 2.0 * (
        first.x * (second.y - third.y)
        + second.x * (third.y - first.y)
        + third.x * (first.y - second.y)
    )
    if abs(determinant) < 1e-9:
        return None
    first_sq = first.x * first.x + first.y * first.y
    second_sq = second.x * second.x + second.y * second.y
    third_sq = third.x * third.x + third.y * third.y
    centre_x = (
        first_sq * (second.y - third.y)
        + second_sq * (third.y - first.y)
        + third_sq * (first.y - second.y)
    ) / determinant
    centre_y = (
        first_sq * (third.x - second.x)
        + second_sq * (first.x - third.x)
        + third_sq * (second.x - first.x)
    ) / determinant
    return centre_x, centre_y, math.dist((centre_x, centre_y), (first.x, first.y))


def _observed_arc_window(
    centre_x: float,
    centre_y: float,
    start: PixelPoint,
    mid: PixelPoint,
    end: PixelPoint,
) -> tuple[float, float] | None:
    """Ângulo inicial e varredura, em radianos, medidos EM PIXELS a partir do centro.

    Os ângulos saem do espaço de pixels e não do normalizado porque o normalizado é
    anisotrópico: dividir x pela largura e y pela altura de uma página não quadrada torce
    todo ângulo que não seja múltiplo de 90°, e o arco pousaria girado sobre a tinta.

    O sentido é escolhido pelo `mid`: vale a varredura start→end que PASSA por ele. É o que
    separa arco maior de arco menor sem depender de o modelo conhecer convenção nenhuma de
    sentido — a folha diz por onde a curva passa, e o ponto do meio é essa evidência.
    """
    radii = [math.dist((point.x, point.y), (centre_x, centre_y)) for point in (start, mid, end)]
    if min(radii) < ARC_OBSERVED_MIN_ANCHOR_RADIUS_PX:
        return None
    angles = [math.atan2(point.y - centre_y, point.x - centre_x) for point in (start, mid, end)]
    start_angle, mid_angle, end_angle = angles
    forward = (end_angle - start_angle) % math.tau
    to_mid = (mid_angle - start_angle) % math.tau
    sweep = forward if to_mid <= forward else forward - math.tau
    if abs(sweep) < math.radians(ARC_OBSERVED_MIN_SWEEP_DEGREES):
        return None
    return start_angle, sweep


def proposals_from_geometry(
    elements: Iterable[GeometryElementLike],
    *,
    image_digest: str,
    width: int,
    height: int,
) -> list[VisionProposal]:
    """Converte geometria normalizada de um modelo em propostas em pixels.

    A proposta continua `unresolved` e não exportável: mudar quem observou não muda o que
    a observação vale. O que ela ganha é `label` e `layer_hint`, que o caminho
    determinístico não tem como preencher.

    A janela angular do arco vem das três âncoras quando o contrato as traz
    (`geometry-extraction@2.0.0`) e continua fabricada como meia-volta 0..π quando não traz.
    `arc_angles_observed` declara qual dos dois aconteceu, porque é a diferença entre uma
    orientação que o refino apenas lapida e uma que ele precisa reconquistar na tinta.
    """
    proposals: list[VisionProposal] = []
    for element in elements:

        def point(item: Any) -> PixelPoint:
            return PixelPoint(
                x=min(float(width), max(0.0, item.x * width)),
                y=min(float(height), max(0.0, item.y * height)),
            )

        geometry: PixelGeometryValue
        kind: Literal["line", "circle", "contour"]
        arc_angles_observed = False
        if element.kind == "circle":
            assert element.center is not None and element.radius is not None
            radius = element.radius * min(width, height)
            if radius <= 0:
                continue
            geometry = PixelCircle(center=point(element.center), radius=radius)
            kind = "circle"
        elif element.kind == "arc":
            anchors_reported = (
                element.arc_start is not None
                and element.arc_mid is not None
                and element.arc_end is not None
            )
            if element.center is not None and element.radius is not None:
                reported_centre = point(element.center)
                centre_x, centre_y = reported_centre.x, reported_centre.y
                radius = element.radius * min(width, height)
            else:
                # Contrato @2.0.0: arco pode vir só com as três âncoras — três pontos
                # determinam o círculo, então o centro e o raio saem do circuncírculo EM
                # PIXELS (medido na eval real: Opus reportou as âncoras e omitiu o par
                # derivável). Âncoras colineares não determinam círculo nenhum: elemento
                # pulado, nunca fabricado por cima de observação inutilizável.
                assert anchors_reported  # validador do contrato: sem par, três âncoras
                fit = _circumcircle(
                    point(element.arc_start),
                    point(element.arc_mid),
                    point(element.arc_end),
                )
                if fit is None:
                    continue
                centre_x, centre_y, radius = fit
            if radius <= 0:
                continue
            window = (
                _observed_arc_window(
                    centre_x,
                    centre_y,
                    point(element.arc_start),
                    point(element.arc_mid),
                    point(element.arc_end),
                )
                if anchors_reported
                else None
            )
            if window is None:
                if element.center is None or element.radius is None:
                    # Arco só de âncoras cuja janela degenerou: não há center/radius
                    # observados para sustentar um chute — fabricar meia-volta sobre um
                    # circuncírculo derivado de observação ruim seria tinta inventada.
                    continue
                # Sem âncoras utilizáveis a abertura é FABRICADA: meia-volta fixa, que o
                # registro reconquista contra a tinta. É chute declarado, não observação.
                first_angle, sweep = 0.0, math.pi
            else:
                first_angle, sweep = window
                arc_angles_observed = True
            # Sem PixelArc, amostrar é a representação honesta: preserva a forma traçada
            # em vez de promovê-la a círculo inteiro. O raio vem de `radius`, não das
            # âncoras: elas dizem POR ONDE a curva passa, o contrato diz o raio dela.
            geometry = PixelPolyline(
                points=[
                    PixelPoint(
                        x=min(float(width), max(0.0, centre_x + radius * math.cos(angle))),
                        y=min(float(height), max(0.0, centre_y + radius * math.sin(angle))),
                    )
                    for angle in (
                        first_angle + sweep * step / (ARC_SAMPLES - 1)
                        for step in range(ARC_SAMPLES)
                    )
                ],
                closed=False,
            )
            kind = "contour"
        elif element.kind == "line":
            geometry = PixelLine(start=point(element.vertices[0]), end=point(element.vertices[-1]))
            kind = "line"
        else:
            geometry = PixelPolyline(
                points=[point(vertex) for vertex in element.vertices],
                closed=element.closed,
            )
            kind = "contour"
        proposals.append(
            VisionProposal(
                id=_proposal_id(image_digest, kind, geometry),
                kind=kind,
                geometry=geometry,
                algorithm=GEOMETRY_EXTRACTION_ALGORITHM,
                quality_score=0.0,
                label=element.label,
                layer_hint=None if element.layer_hint == "unknown" else element.layer_hint,
                arc_angles_observed=arc_angles_observed,
            )
        )
    return proposals


def _sample_points(geometry: PixelGeometryValue, samples: int) -> list[tuple[float, float]]:
    """Pontos ao longo da geometria, densidade independente do número de vértices."""
    if isinstance(geometry, PixelCircle):
        return [
            (
                geometry.center.x + geometry.radius * math.cos(step * math.tau / samples),
                geometry.center.y + geometry.radius * math.sin(step * math.tau / samples),
            )
            for step in range(samples)
        ]
    if isinstance(geometry, PixelLine):
        vertices = [(geometry.start.x, geometry.start.y), (geometry.end.x, geometry.end.y)]
    else:
        vertices = [(point.x, point.y) for point in geometry.points]
        if geometry.closed:
            vertices.append(vertices[0])
    spans = list(pairwise(vertices))
    total = sum(math.dist(start, end) for start, end in spans)
    if total <= 0:
        return vertices
    points: list[tuple[float, float]] = []
    for start, end in spans:
        length = math.dist(start, end)
        steps = max(1, round(samples * length / total))
        for step in range(steps + 1):
            ratio = step / steps
            points.append(
                (start[0] + (end[0] - start[0]) * ratio, start[1] + (end[1] - start[1]) * ratio)
            )
    return points


def corroborate_with_ink(
    proposals: list[VisionProposal],
    image_path: Path,
    *,
    config: VisionConfig | None = None,
) -> tuple[list[VisionProposal], list[str]]:
    """Mede quanto de cada proposta cai sobre tinta real do croqui.

    É a defesa determinística contra alucinação: um elemento que o modelo afirma e o papel
    não mostra fica com cobertura baixa. O elemento é **rebaixado, não descartado** —
    descartar esconderia a invenção; rebaixar a coloca na frente do revisor.
    """
    effective_config = config or VisionConfig()
    image = cv2.imread(str(image_path.resolve(strict=True)), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"imagem ilegível: {image_path.name}")
    original_height, original_width = image.shape[:2]
    resized, scale = _resize_for_detection(image, effective_config.max_dimension)
    _grayscale, mask = _ink_mask(resized)
    tolerance = max(1, effective_config.ink_corroboration_tolerance_px)
    # O traço à mão tem espessura e a coordenada do modelo é aproximada: exigir acerto
    # exato de pixel reprovaria geometria boa.
    reachable = cv2.dilate(
        mask,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (tolerance * 2 + 1, tolerance * 2 + 1)),
        iterations=1,
    )
    height, width = reachable.shape[:2]
    corroborated: list[VisionProposal] = []
    notes: list[str] = []
    for proposal in proposals:
        points = _sample_points(proposal.geometry, effective_config.ink_corroboration_samples)
        hits = 0
        for x, y in points:
            column = min(width - 1, max(0, int(x * scale)))
            row = min(height - 1, max(0, int(y * scale)))
            if reachable[row, column] > 0:
                hits += 1
        coverage = hits / len(points) if points else 0.0
        corroborated.append(proposal.model_copy(update={"quality_score": round(coverage, 4)}))
        if coverage < effective_config.ink_corroboration_min_coverage:
            notes.append(f"INK_NOT_FOUND:{proposal.label or proposal.id}")
    if original_width and original_height:
        # Mantém explícito que a medida vale para a imagem de origem, não para a redução.
        notes.append(f"INK_CORROBORATION_AT:{original_width}x{original_height}")
    return corroborated, notes


ROTATION_SEARCH_SPAN_DEGREES: Final = 3.0
"""Meia-janela da busca de rotação fina em torno do melhor quarto de volta."""

ROTATION_SEARCH_STEP_DEGREES: Final = 0.5
"""Passo grosso da rotação fina; a folha escaneada raramente entra torta mais que isso."""

ROTATION_REFINE_SPAN_DEGREES: Final = 0.5
"""Meia-janela do segundo passe de rotação, ao redor do ângulo grosso vencedor."""

ROTATION_REFINE_STEP_DEGREES: Final = 0.1
"""Passo fino: abaixo disso o deslocamento na ponta do desenho cabe na tolerância da tinta."""

ELEMENT_SHIFT_SPAN_RATIO: Final = 0.005
"""Piso da janela do empurrão por elemento, como fração do lado maior da página."""

ELEMENT_BBOX_SHIFT_RATIO: Final = 0.15
"""Janela do empurrão como fração da diagonal do próprio elemento.

A janela é a **maior** entre esta e a fração da página. Só a fração da página aperta o
elemento grande — no Guaxindiba vários refinos bateram na borda dos 0,5% —, e só a fração
do elemento soltaria demais a marca de pênalti, que tem 15 px de raio.
"""

ELEMENT_SHIFT_MAX_SPAN_RATIO: Final = 0.02
"""Teto da janela do empurrão, como fração do lado maior da página.

Sem teto, 15% da diagonal de um contorno grande vira janela de centenas de pixels, e aí a
cobertura deixa de medir o que se quer: num croqui cheio de linhas longas e paralelas ela
premia qualquer tinta alcançada, não a tinta **daquele** elemento. Medido no Guaxindiba: o
muro perimetral deslizava 335 px e ia parar sobre a escrita à mão, ganhando cobertura sem
ganhar razão. Mis-assentamento residual legítimo é da ordem de dezenas de pixels; centenas
significam que a proposta nunca esteve ali.
"""

EDGE_SHIFT_MAX_SPAN_RATIO: Final = 0.05
"""Teto da janela do refino POR ARESTA, como fração do lado maior da página.

Maior que o teto do empurrão rígido, porque o erro que ele corrige é outro. O empurrão
rígido corrige **assentamento**, cujo resíduo legítimo é da ordem de dezenas de pixels; o
refino por aresta corrige **tamanho**, e a aresta oposta à que já pousou na tinta carrega o
erro de escala inteiro do elemento. Medido no Guaxindiba: o contorno do campo saiu 1,28x
mais alto que a tinta e a base dele precisava de 285 px — o teto de 2% (134 px) não
alcançava, e sem alcançar o encontro desenhado campo/patamar, que é o que amarra o traçado,
não voltava a existir.
"""

EDGE_SHIFT_EXTENT_RATIO: Final = 0.35
"""Janela por aresta como fração da extensão do elemento PERPENDICULAR àquela aresta.

Não é a diagonal do elemento, que é a medida do empurrão rígido, e a diferença é o que
separa corrigir tamanho de colapsar a forma. O erro que esta busca corrige é proporcional à
profundidade que a aresta atravessa: a base do campo erra uma fração da ALTURA do campo, não
da diagonal dele. Medido no Guaxindiba, a diagonal erra nos dois sentidos ao mesmo tempo —
a faixa de área vegetativa (221 px de altura contra 1.528 px de diagonal) ganharia 229 px de
janela e o topo dela desceria 220 px para pousar na linha de baixo do patamar, achatando o
elemento; e os patamares, que precisavam de até 310 px, ganhariam só 272. Pela extensão
perpendicular os dois casos ficam certos: 77 px para a faixa, até 323 px para os patamares.
"""

EDGE_ORTHOGONALITY_TOLERANCE_DEGREES: Final = 12.0
"""Desvio máximo de uma aresta em relação ao eixo para o contorno ser quase-retangular.

É o mesmo valor de `geometry_solver.AXIS_TOLERANCE_DEGREES`, e de propósito: quem decide
depois que este contorno é retangular é a regularização do traçado, e o refino não pode
chamar de retângulo o que ela vai tratar como diagonal. O valor é repetido em vez de
importado porque `geometry_solver` depende de `topology`, que depende deste módulo; um teste
amarra os dois para a repetição não virar divergência.
"""

EDGE_MIN_EXTENT_RATIO: Final = 0.5
"""Quanto de cada extensão do contorno o refino por aresta é obrigado a preservar.

Corrigir tamanho é o trabalho deste ajuste; anular o elemento não é. Sem esse piso um par de
arestas paralelas pode fechar sobre a mesma tinta e o contorno vira um traço de cobertura
perfeita: no Guaxindiba a faixa de área vegetativa (221 px de altura), empurrada 157 px pelo
corredor da ordem contra a base do contorno do terreno, terminava com 9 px de altura e
cobertura 1,0 — deitada sobre a linha de outro elemento. Quando a correção que a ordem já
exige não cabe no piso, o refino por aresta se declara inaplicável e o elemento volta para o
empurrão rígido: ordem é defeito de posição, e resize não conserta posição.
"""

EDGE_MIN_LENGTH_PX: Final = 1.0
"""Aresta mais curta que um pixel não é aresta: o contorno é degenerado e segue no rígido."""

TIP_TRAVEL_EXTENT_RATIO: Final = EDGE_SHIFT_EXTENT_RATIO
"""Janela de cada ponta de linha como fração do comprimento dela, com o mesmo teto de página.

É deliberadamente a mesma fração do refino por aresta, pela mesma razão: o erro que ela
corrige é proporcional à profundidade que a ponta percorre, e para uma linha essa
profundidade é o próprio comprimento. Medido no Guaxindiba: a linha de meio de campo saiu
2.792 px de ponta a ponta contra 2.313 px de tinta, com a ponta de cima 304 px além do traço,
sobre o pedaço de tinta da cota "6,60" que desce perto dali.
"""

TIP_MIN_INK_RUN_TOLERANCES: Final = 2.0
"""Trecho contínuo mínimo de tinta NA DIREÇÃO da linha para uma ponta aceitar parada, em
múltiplos da tolerância do halo de corroboração.

Traço cruzante não diz onde a linha acaba. Ele contribui uma espessura de traço ao longo da
direção — e, com o halo, uma banda de tolerância a mais de cada lado —, o bastante para a
ponta parar ali e nunca alcançar a tinta própria. Duas tolerâncias é o limiar natural:
"mais perto que a tolerância os dois são o mesmo traço" é a definição que este módulo já usa
para ordem e corroboração, então tinta que só se estende por uma tolerância na direção é
espessura de traço, não extensão.

Medido no Guaxindiba (linha de meio de campo, `vp_5008192d7f695899`): a ponta de cima parou
em y=2096, no halo do risco horizontal que cruza a coluna em y=2118..2153 — 44 px antes da
tinta própria. Encostada ali, ela ficava mais perto da faixa do muro (2123,5) que da do campo
(2130,0), o traçado amarrou o 21,75 na faixa errada e a cadeia estourou em três resíduos de
2,20 m (19,75, 8,60 e o próprio 21,75).
"""

ELEMENT_RADIUS_TOLERANCE: Final = 0.15
"""Quanto o raio de um círculo/arco pode ser reajustado contra a tinta, em fração."""

ARC_FIT_MAX_RELATIVE_RESIDUAL: Final = 0.06
"""Resíduo máximo do ajuste de círculo, relativo ao raio, para a polilinha ser um arco."""

ARC_MIN_SAGITTA_RATIO: Final = 0.04
"""Flecha mínima sobre a corda: sem barriga não há arco, há reta."""

ARC_MIN_POINTS: Final = 6
"""Vértices mínimos para afirmar curvatura; menos que isso é traçado, não amostragem."""

ARC_ORIENTATION_STEP_DEGREES: Final = 5.0
"""Passo grosso da busca de orientação do arco, varrendo a volta inteira."""

ARC_ORIENTATION_REFINE_SPAN_DEGREES: Final = 5.0
"""Meia-janela do segundo passe de orientação, ao redor do ângulo grosso vencedor."""

ARC_ORIENTATION_REFINE_STEP_DEGREES: Final = 1.0
"""Passo fino da orientação; abaixo disso o deslocamento no arco cabe na tinta."""

ARC_OBSERVED_ORIENTATION_SPAN_DEGREES: Final = 15.0
"""Meia-janela da orientação quando ela foi OBSERVADA nas âncoras do contrato.

Orientação fabricada precisa ser reconquistada e por isso a busca varre a volta inteira.
Observada, ela é evidência: o refino pode lapidá-la contra a tinta — o modelo erra o
assentamento, e alguns graus de erro de leitura são esperados — mas não pode substituí-la.
Sem a janela, um quarto de volta com mais tinta por baixo (a meia-lua vizinha, a curva do
canteiro ao lado) apagaria em silêncio o que a folha mostrava, e o relatório declararia um
giro que a evidência contradiz. Quinze graus é o dobro do passo grosso mais o passe fino:
cabe o erro de leitura e não cabe outra forma.
"""

ORDER_GUARD_MIN_EXTENT_RATIO: Final = 0.005
"""Extensão mínima de uma tangente, em fração do lado maior da página, para declarar ordem.

Abaixo disso a tangente é curta demais para dizer de que lado um elemento está: a marca de
pênalti do Guaxindiba tem 30 px de diâmetro e não ordena nada.
"""

ORDER_GUARD_MIN_OVERLAP_RATIO: Final = 0.2
"""Quanto da tangente do elemento o vizinho precisa cobrir para mandar nela.

A fração é medida sobre a tangente RESTRINGIDA, não sobre a do vizinho, e a assimetria é
proposital. Uma linha que cobre a aresta inteira de um elemento diz de que lado dela ele
está; um portão de 150 px atravessando um muro de 3.800 px não diz nada sobre o muro —
ele está dentro do muro, não de um lado dele.
"""

_ORDER_ANCHOR_EPSILON: Final = 1e-3
"""Folga sub-pixel para pousar DENTRO do corredor aberto, e não exatamente sobre o limite."""

ElementRefinement = Literal["none", "translation", "edges", "tips", "circle", "arc"]

_Transform = tuple[float, float, float, float]
"""`scale_x`, `scale_y`, `offset_x`, `offset_y` — a parte não angular da transformação."""

_RunField = Callable[[tuple[float, float]], Callable[[NDArray[np.float64]], float]]
"""Fábrica da evidência de **trecho contínuo** numa direção: direção → medida de tinta.

A medida devolvida vale 1,0 onde a tinta testemunha um trecho contínuo de pelo menos
`TIP_MIN_INK_RUN_TOLERANCES` tolerâncias ao longo daquela direção, e 0,0 onde a tinta é só
espessura de traço cruzante. É a diferença que a medida de cobertura não consegue fazer: no
halo isotrópico o risco do muro e a linha que ele cruza são a mesma mancha contínua.
"""


@dataclass(frozen=True)
class ElementRegistration:
    """Antes e depois de um elemento no refino local, para a auditoria por proposta.

    O refino é a única etapa que move um elemento sozinho, então cada movimento precisa
    aparecer: qual colocação virou base, que tipo de ajuste foi aplicado e quanto de tinta
    havia antes e depois. Sem isso o refino seria indistinguível de inventar geometria.
    """

    proposal_id: str
    label: str | None
    kind: str
    coverage_raw: float
    coverage_global: float
    coverage_refined: float
    base: Literal["raw", "global"]
    refinement: ElementRefinement
    centre_shift_px: float = 0.0
    radius_delta_px: float = 0.0
    # Só arco preenche. É o giro da janela angular sobre o círculo ajustado, e precisa
    # aparecer porque é o único ajuste que muda para onde a forma aponta.
    orientation_delta_degrees: float = 0.0
    # Só contorno quase-retangular preenche, na ordem topo, base, esquerda e direita — o
    # papel da aresta, não o índice do vértice, porque é o papel que a revisão consegue
    # conferir contra a folha. É o único ajuste que muda o TAMANHO do elemento, então os
    # quatro escalares precisam aparecer: com eles a revisão refaz o contorno de cabeça.
    edge_shifts_px: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    # Só linha preenche: quanto cada ponta deslizou AO LONGO da direção da linha, na ordem
    # início e fim, positivo no sentido início→fim. Positivo no início encurta, positivo no
    # fim estica. Aparece separado do empurrão porque muda a EXTENSÃO da observação, e o
    # revisor precisa ver que a linha encolheu tanto quanto precisa ver que ela andou.
    tip_shifts_px: tuple[float, float] = (0.0, 0.0)
    # A colocação de base cruzava vizinho e o elemento foi devolvido ao corredor da ordem.
    # É raro e precisa aparecer: é o único caso em que o refino move um elemento por
    # obrigação de ordem, e não por ganho de tinta.
    order_constrained: bool = False
    # Nenhuma colocação preservava a ordem: a proposta é internamente incompatível com as
    # vizinhas e o refino declara isso em vez de escolher um lado em silêncio.
    order_unresolved: bool = False


@dataclass(frozen=True)
class _Refinement:
    """Resultado do refino de um elemento, com o que precisa ser declarado no relatório."""

    geometry: PixelGeometryValue
    kind: ElementRefinement
    centre_shift_px: float = 0.0
    radius_delta_px: float = 0.0
    orientation_delta_degrees: float = 0.0
    edge_shifts_px: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    tip_shifts_px: tuple[float, float] = (0.0, 0.0)


@dataclass(frozen=True)
class InkRegistration:
    """Giro, translação e escala por eixo que melhor assentam o conjunto sobre a tinta."""

    scale_x: float
    scale_y: float
    offset_x: float
    offset_y: float
    coverage_before: float
    coverage_after: float
    # Um modelo descreve a planta na orientação em que a lê; o croqui pode estar deitado
    # na folha. Essa parte é sempre múltipla de 90°, então o espaço é pequeno e exato.
    rotation_degrees: int = 0
    # O papel também entra torto no scanner. Esse desvio é de poucos graus e não é
    # corrigível por quarto de volta: sem ele o erro cresce longe do centroide.
    fine_rotation_degrees: float = 0.0
    coverage_refined: float = 0.0
    elements: tuple[ElementRegistration, ...] = ()

    @property
    def moved(self) -> bool:
        return self.coverage_after > self.coverage_before

    @property
    def uniform_scale(self) -> float:
        return (self.scale_x + self.scale_y) / 2

    @property
    def total_rotation_degrees(self) -> float:
        """Ângulo realmente aplicado ao conjunto: o quarto de volta mais o desvio fino."""
        return self.rotation_degrees + self.fine_rotation_degrees

    def apply(self, x: float, y: float, *, centre: tuple[float, float]) -> tuple[float, float]:
        turned_x, turned_y = _quarter_turn(x - centre[0], y - centre[1], self.rotation_degrees)
        angle = math.radians(self.fine_rotation_degrees)
        cosine, sine = math.cos(angle), math.sin(angle)
        rotated_x = turned_x * cosine - turned_y * sine
        rotated_y = turned_x * sine + turned_y * cosine
        return (
            centre[0] + rotated_x * self.scale_x + self.offset_x,
            centre[1] + rotated_y * self.scale_y + self.offset_y,
        )


def _quarter_turn(x: float, y: float, degrees: int) -> tuple[float, float]:
    """Giro exato por múltiplo de 90°, sem seno nem cosseno: nada de erro de arredondamento."""
    if degrees == 90:
        return -y, x
    if degrees == 180:
        return -x, -y
    if degrees == 270:
        return y, -x
    return x, y


def _rotate_about_origin(points: NDArray[np.float64], degrees: float) -> NDArray[np.float64]:
    """Giro fino em torno da origem já centrada; o quarto de volta continua sendo exato."""
    if degrees == 0.0:
        return points
    angle = math.radians(degrees)
    cosine, sine = math.cos(angle), math.sin(angle)
    return np.column_stack(
        (
            points[:, 0] * cosine - points[:, 1] * sine,
            points[:, 0] * sine + points[:, 1] * cosine,
        )
    )


def _best_on_grid(
    evaluate: Callable[[_Transform], float],
    start: _Transform,
    start_score: float,
    *,
    shift_step: float,
    scale_step: float,
    shift_radius: int,
    scale_radius: int,
) -> tuple[float, _Transform]:
    """Melhor transformação de uma grade fixa ao redor de `start`.

    Grade e não otimizador: o resultado é reproduzível e explicável para quem audita o
    relatório depois. Empate fica com o primeiro candidato, então a ordem de varredura
    define o desempate e a saída é determinística.
    """
    best = (start_score, start)
    base_scale_x, base_scale_y, base_offset_x, base_offset_y = start
    for index_x in range(-shift_radius, shift_radius + 1):
        for index_y in range(-shift_radius, shift_radius + 1):
            for scale_index_x in range(-scale_radius, scale_radius + 1):
                for scale_index_y in range(-scale_radius, scale_radius + 1):
                    candidate: _Transform = (
                        base_scale_x + scale_index_x * scale_step,
                        base_scale_y + scale_index_y * scale_step,
                        base_offset_x + index_x * shift_step,
                        base_offset_y + index_y * shift_step,
                    )
                    if candidate[0] <= 0 or candidate[1] <= 0:
                        continue
                    score = evaluate(candidate)
                    if score > best[0]:
                        best = (score, candidate)
    return best


@dataclass(frozen=True)
class _CircleFit:
    centre_x: float
    centre_y: float
    radius: float


def _fit_circle(points: NDArray[np.float64]) -> _CircleFit | None:
    """Ajuste algébrico de círculo (Kåsa): forma fechada, sem iteração e sem semente.

    Resolve `x² + y² = a·x + b·y + c` por mínimos quadrados. Um otimizador iterativo daria
    resultado dependente de semente e de critério de parada — inauditável num artefato que
    precisa ser reproduzível.
    """
    if len(points) < 3:
        return None
    design = np.column_stack((points[:, 0], points[:, 1], np.ones(len(points))))
    target = points[:, 0] ** 2 + points[:, 1] ** 2
    try:
        solution = np.linalg.lstsq(design, target, rcond=None)[0]
    except np.linalg.LinAlgError:
        return None
    centre_x = float(solution[0]) / 2
    centre_y = float(solution[1]) / 2
    squared = float(solution[2]) + centre_x**2 + centre_y**2
    if not math.isfinite(squared) or squared <= 0:
        return None
    return _CircleFit(centre_x=centre_x, centre_y=centre_y, radius=math.sqrt(squared))


def _arc_of(geometry: PixelPolyline) -> _CircleFit | None:
    """Círculo por trás de uma polilinha aberta, quando existir um.

    Resíduo pequeno sozinho não basta: uma reta é o limite de um círculo de raio infinito
    e passaria com resíduo quase nulo. A flecha sobre a corda é o que separa curva de
    reta, e sem ela o refino re-formaria como arco um muro que ninguém desenhou curvo.
    """
    if geometry.closed or len(geometry.points) < ARC_MIN_POINTS:
        return None
    points = np.array([[point.x, point.y] for point in geometry.points], dtype=np.float64)
    fit = _fit_circle(points)
    if fit is None:
        return None
    distances = np.hypot(points[:, 0] - fit.centre_x, points[:, 1] - fit.centre_y)
    residual = float(np.max(np.abs(distances - fit.radius))) / fit.radius
    if residual > ARC_FIT_MAX_RELATIVE_RESIDUAL:
        return None
    chord = np.array(points[-1] - points[0], dtype=np.float64)
    chord_length = float(math.hypot(float(chord[0]), float(chord[1])))
    if chord_length <= 0:
        # Extremos coincidentes: sem corda não há flecha medível, e afirmar arco seria chute.
        return None
    normal = np.array([-chord[1], chord[0]], dtype=np.float64) / chord_length
    sagitta = float(np.max(np.abs((points - points[0]) @ normal)))
    if sagitta / chord_length < ARC_MIN_SAGITTA_RATIO:
        return None
    return fit


def _circle_points(
    centre_x: float, centre_y: float, radius: float, samples: int
) -> NDArray[np.float64]:
    """Mesma amostragem que `_sample_points` faz num `PixelCircle`."""
    angles = np.arange(samples, dtype=np.float64) * math.tau / samples
    return np.column_stack((centre_x + radius * np.cos(angles), centre_y + radius * np.sin(angles)))


def _arc_points(
    source: NDArray[np.float64],
    centre_x: float,
    centre_y: float,
    radius: float,
    count: int,
    orientation_degrees: float = 0.0,
) -> NDArray[np.float64]:
    """Re-amostra o arco em `count` pontos, preservando a EXTENSÃO angular observada.

    A extensão (quanto o arco varre) vem dos extremos atuais medidos contra o centro
    candidato, e o desenrolar (`unwrap`) mantém o sentido do traçado: sem ele um arco que
    cruza ±π voltaria pelo lado errado e viraria outra forma.

    `orientation_degrees` gira essa janela em torno do círculo. Quanto girar é decidido por
    quem chama, pelo alcance que a evidência autoriza: orientação FABRICADA — sem as
    âncoras do `geometry-extraction@2.0.0`, `proposals_from_geometry` abre 0..π fixo — é
    reconquistada na volta inteira, porque preservar chute não protegeria evidência
    nenhuma; orientação observada nas âncoras só é lapidada dentro de uma janela estreita.
    """
    angles = np.unwrap(np.arctan2(source[:, 1] - centre_y, source[:, 0] - centre_x))
    offset = math.radians(orientation_degrees)
    sweep = np.linspace(float(angles[0]) + offset, float(angles[-1]) + offset, count)
    return np.column_stack((centre_x + radius * np.cos(sweep), centre_y + radius * np.sin(sweep)))


def _bounding_diagonal(geometry: PixelGeometryValue) -> float:
    """Diagonal da caixa envolvente: o tamanho próprio do elemento, em pixels."""
    if isinstance(geometry, PixelCircle):
        return 2 * geometry.radius * math.sqrt(2)
    if isinstance(geometry, PixelLine):
        return math.hypot(geometry.end.x - geometry.start.x, geometry.end.y - geometry.start.y)
    xs = [point.x for point in geometry.points]
    ys = [point.y for point in geometry.points]
    return math.hypot(max(xs) - min(xs), max(ys) - min(ys))


def _element_window(geometry: PixelGeometryValue, span: float) -> float:
    """Janela do empurrão: cresce com o elemento, com piso e teto declarados na página."""
    return min(
        max(
            span * ELEMENT_SHIFT_SPAN_RATIO,
            ELEMENT_BBOX_SHIFT_RATIO * _bounding_diagonal(geometry),
        ),
        span * ELEMENT_SHIFT_MAX_SPAN_RATIO,
    )


@dataclass(frozen=True)
class _RectangularEdge:
    """Uma aresta de contorno quase-retangular e a feature de ordem que ela governa.

    `horizontal` diz que a aresta é quase paralela ao eixo x, e portanto que o deslocamento
    perpendicular dela é medido em **y**. `feature` é o índice em
    `_order_features(mode="bounds")` que essa aresta define — topo, base, esquerda ou
    direita —, e é o que liga o corredor da ordem do refino por elemento a uma aresta em vez
    de ao elemento inteiro: a mesma lei, aplicada quatro vezes.
    """

    start: int
    horizontal: bool
    feature: int


def _rectangular_edges(geometry: PixelGeometryValue) -> tuple[_RectangularEdge, ...] | None:
    """Quatro arestas quase-ortogonais de um contorno fechado, ou `None` se não for um.

    Exige contorno fechado de quatro vértices, cada aresta com comprimento útil e desvio de
    eixo dentro da tolerância, e as arestas **alternando** horizontal e vertical. Sem a
    alternância a forma não é um retângulo torto — é outra coisa, e deslocar as arestas dela
    perpendicularmente descreveria uma figura que ninguém observou. Contorno que não passa
    segue no empurrão rígido, que não muda forma nenhuma.
    """
    if not isinstance(geometry, PixelPolyline) or not geometry.closed:
        return None
    if len(geometry.points) != 4:
        return None
    tolerance = math.radians(EDGE_ORTHOGONALITY_TOLERANCE_DEGREES)
    horizontal: list[bool] = []
    for index in range(4):
        start, end = geometry.points[index], geometry.points[(index + 1) % 4]
        delta_x, delta_y = end.x - start.x, end.y - start.y
        if math.hypot(delta_x, delta_y) < EDGE_MIN_LENGTH_PX:
            return None
        angle = math.atan2(abs(delta_y), abs(delta_x))
        if angle <= tolerance:
            horizontal.append(True)
        elif angle >= math.pi / 2 - tolerance:
            horizontal.append(False)
        else:
            return None
    # As quatro precisam ALTERNAR: duas horizontais e duas verticais, nessa ordem. Testar só
    # que vizinhas diferem deixaria passar contorno de três arestas na mesma orientação, que
    # não tem os quatro papéis (topo, base, esquerda, direita) para distribuir.
    if horizontal[0] == horizontal[1] or horizontal[0] != horizontal[2]:
        return None
    if horizontal[1] != horizontal[3]:
        return None

    def midpoint(index: int) -> tuple[float, float]:
        start, end = geometry.points[index], geometry.points[(index + 1) % 4]
        return (start.x + end.x) / 2, (start.y + end.y) / 2

    # Qual das duas horizontais é o topo e qual é a base sai do desenho, não da ordem em que
    # o modelo listou os vértices: um contorno descrito no sentido anti-horário tem os mesmos
    # quatro papéis. Empate pelo índice mantém a saída determinística.
    horizontals = sorted(
        (index for index in range(4) if horizontal[index]),
        key=lambda index: (midpoint(index)[1], index),
    )
    verticals = sorted(
        (index for index in range(4) if not horizontal[index]),
        key=lambda index: (midpoint(index)[0], index),
    )
    feature_of = {horizontals[0]: 0, horizontals[1]: 1, verticals[0]: 2, verticals[1]: 3}
    return tuple(
        _RectangularEdge(start=index, horizontal=horizontal[index], feature=feature_of[index])
        for index in range(4)
    )


def _edge_window(geometry: PixelPolyline, edge: _RectangularEdge, span: float) -> float:
    """Janela do deslocamento de uma aresta: cresce com a profundidade que ela atravessa."""
    xs = [point.x for point in geometry.points]
    ys = [point.y for point in geometry.points]
    extent = (max(ys) - min(ys)) if edge.horizontal else (max(xs) - min(xs))
    return min(
        max(span * ELEMENT_SHIFT_SPAN_RATIO, EDGE_SHIFT_EXTENT_RATIO * extent),
        span * EDGE_SHIFT_MAX_SPAN_RATIO,
    )


def _edge_slope(geometry: PixelPolyline, edge: _RectangularEdge) -> float:
    """Inclinação da aresta em relação ao eixo dela; zero quando ela é exatamente ortogonal.

    É o quanto o canto desta aresta escorrega quando uma vizinha se desloca um pixel: o canto
    é interseção, e mover a vizinha o arrasta AO LONGO desta aresta. O corredor da ordem entra
    encolhido dessa folga, senão a primeira aresta que se mexe empurra o canto de volta para
    cima do vizinho e a busca trava — medido no Guaxindiba, a aresta esquerda do campo saturava
    o corredor e impedia a base de subir os 272 px que a levavam até a própria tinta.
    """
    start, end = geometry.points[edge.start], geometry.points[(edge.start + 1) % 4]
    delta_x, delta_y = end.x - start.x, end.y - start.y
    return abs(delta_y / delta_x) if edge.horizontal else abs(delta_x / delta_y)


def _edge_samples(
    geometry: PixelPolyline, edge: _RectangularEdge, samples: int
) -> NDArray[np.float64]:
    """Amostras da própria aresta: é a tinta dela que decide para onde ela vai.

    Medir o elemento inteiro é justamente o que impede a correção de tamanho — três arestas
    certas afogam a quarta, e o deslocamento que sobe a cobertura média é o rígido, que não
    corrige tamanho nenhum. As amostras saem da aresta na colocação de **base** e viajam com
    ela, de modo que a busca de cada aresta não dependa de onde as vizinhas pararam.
    """
    start, end = geometry.points[edge.start], geometry.points[(edge.start + 1) % 4]
    ratios = np.linspace(0.0, 1.0, max(4, samples // _EDGE_SAMPLE_DIVISOR))
    return np.column_stack(
        (start.x + (end.x - start.x) * ratios, start.y + (end.y - start.y) * ratios)
    )


def _line_intersection(
    first: tuple[tuple[float, float], tuple[float, float]],
    second: tuple[tuple[float, float], tuple[float, float]],
) -> tuple[float, float]:
    """Encontro de duas retas dadas por ponto e direção.

    Só é chamada com arestas vizinhas de um contorno quase-retangular, que estão a pelo menos
    66° uma da outra e têm comprimento maior que um pixel: o denominador não pode anular.
    """
    (first_x, first_y), (first_dx, first_dy) = first
    (second_x, second_y), (second_dx, second_dy) = second
    denominator = first_dx * second_dy - first_dy * second_dx
    ratio = ((second_x - first_x) * second_dy - (second_y - first_y) * second_dx) / denominator
    return first_x + first_dx * ratio, first_y + first_dy * ratio


def _with_edge_shifts(
    geometry: PixelPolyline,
    edges: Sequence[_RectangularEdge],
    shifts: Sequence[float],
) -> PixelPolyline:
    """Contorno com cada aresta deslocada perpendicularmente; cantos por interseção.

    A **direção** de cada aresta sai intacta — o deslocamento translada a reta suporte, não a
    gira —, então a ortogonalidade do contorno fica exatamente como estava e ele continua
    fechado com quatro vértices. O que muda é o tamanho, que é o erro que este ajuste existe
    para corrigir.
    """
    lines: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for edge, shift in zip(edges, shifts, strict=True):
        start, end = geometry.points[edge.start], geometry.points[(edge.start + 1) % 4]
        offset_x, offset_y = (0.0, shift) if edge.horizontal else (shift, 0.0)
        lines.append(((start.x + offset_x, start.y + offset_y), (end.x - start.x, end.y - start.y)))
    corners: list[PixelPoint] = []
    for index in range(4):
        # O vértice `index` abre a aresta `index` e fecha a anterior: é o encontro das duas.
        corner = _line_intersection(lines[index - 1], lines[index])
        corners.append(PixelPoint(x=max(0.0, corner[0]), y=max(0.0, corner[1])))
    return PixelPolyline(points=corners, closed=True)


OrderMode = Literal["bounds", "centre"]
"""Como o elemento declara em que lado do vizinho ele está."""


@dataclass(frozen=True)
class _OrderFeature:
    """Uma posição do elemento que precisa manter o lado, e o quanto ela cobre no outro eixo.

    `horizontal` diz que a posição é medida em **y** (aresta horizontal ou centro visto pelo
    eixo vertical); a extensão `lower..upper` é a do eixo transversal e serve para saber se
    o elemento e o vizinho chegam a se cobrir — quem não se cobre não declara ordem.
    """

    horizontal: bool
    position: float
    lower: float
    upper: float

    @property
    def extent(self) -> float:
        return self.upper - self.lower


def _order_mode(geometry: PixelGeometryValue) -> OrderMode:
    """Círculo e arco declaram ordem pelo CENTRO; linha e contorno, pelas tangentes.

    A caixa envolvente de um arco não é feature material dele: girar a janela angular sobre
    o mesmo círculo muda os quatro extremos sem que o arco tenha atravessado ninguém — a
    meia-lua de cima e a da direita têm o mesmo centro e caixas diferentes. O centro, esse,
    sobrevive ao re-fit de raio e de orientação, e é o que responde de que lado do vizinho a
    forma está.
    """
    if isinstance(geometry, PixelCircle):
        return "centre"
    if isinstance(geometry, PixelPolyline) and _arc_of(geometry) is not None:
        return "centre"
    return "bounds"


def _order_features(geometry: PixelGeometryValue, *, mode: OrderMode) -> tuple[_OrderFeature, ...]:
    """Posições que declaram ordem, em papel fixo por índice.

    Índice fixo é o que permite comparar o mesmo elemento antes e depois do ajuste: em
    `bounds` são topo, base, esquerda e direita; em `centre`, o centro visto por cada eixo.
    """
    if isinstance(geometry, PixelCircle):
        min_x, max_x = geometry.center.x - geometry.radius, geometry.center.x + geometry.radius
        min_y, max_y = geometry.center.y - geometry.radius, geometry.center.y + geometry.radius
    elif isinstance(geometry, PixelLine):
        min_x, max_x = sorted((geometry.start.x, geometry.end.x))
        min_y, max_y = sorted((geometry.start.y, geometry.end.y))
    else:
        xs = [point.x for point in geometry.points]
        ys = [point.y for point in geometry.points]
        min_x, max_x, min_y, max_y = min(xs), max(xs), min(ys), max(ys)
    if mode == "centre":
        centre_x, centre_y = _order_centre(geometry)
        return (
            _OrderFeature(horizontal=True, position=centre_y, lower=min_x, upper=max_x),
            _OrderFeature(horizontal=False, position=centre_x, lower=min_y, upper=max_y),
        )
    return (
        _OrderFeature(horizontal=True, position=min_y, lower=min_x, upper=max_x),
        _OrderFeature(horizontal=True, position=max_y, lower=min_x, upper=max_x),
        _OrderFeature(horizontal=False, position=min_x, lower=min_y, upper=max_y),
        _OrderFeature(horizontal=False, position=max_x, lower=min_y, upper=max_y),
    )


def _order_centre(geometry: PixelGeometryValue) -> tuple[float, float]:
    """Centro que o re-fit preserva: o do círculo declarado, ou o do círculo ajustado ao arco."""
    if isinstance(geometry, PixelCircle):
        return geometry.center.x, geometry.center.y
    if isinstance(geometry, PixelPolyline):
        fit = _arc_of(geometry)
        if fit is not None:
            return fit.centre_x, fit.centre_y
    points = _sample_points(geometry, 2)
    return points[0]


@dataclass(frozen=True)
class _OrderBarrier:
    """Feature de um elemento já assentado: o limite que o próximo não pode atravessar.

    Carrega as duas posições porque elas respondem a perguntas diferentes: a da REFERÊNCIA
    diz qual era a ordem traçada (e é onde a sobreposição é medida, na mesma colocação para
    todo mundo); a ASSENTADA é onde o vizinho ficou de fato, e é ela que barra.
    """

    reference: _OrderFeature
    placed: float


def _order_barriers(
    reference: Sequence[_OrderFeature], placed: Sequence[_OrderFeature], *, min_extent: float
) -> list[_OrderBarrier]:
    return [
        _OrderBarrier(reference=feature, placed=position.position)
        for feature, position in zip(reference, placed, strict=True)
        if feature.extent >= min_extent
    ]


@dataclass(frozen=True)
class _OrderGuard:
    """Corredor de cada feature: entre que posições ela fica sem inverter a ordem traçada.

    A ordem a preservar é a do conjunto PÓS-GLOBAL, que é a mesma do bruto: o estágio global
    aplica giro, escalas positivas e translação ao conjunto inteiro, e transformação assim
    não troca vizinho de lado. Quem pode trocar é o estágio por elemento — tanto o empurrão
    quanto a escolha entre colocação bruta e pós-global, que movem UM elemento sozinho.
    """

    limits: tuple[tuple[float, float], ...]

    def admits(self, features: Sequence[_OrderFeature]) -> bool:
        return all(
            low < feature.position < high
            for (low, high), feature in zip(self.limits, features, strict=True)
        )

    def violation(self, features: Sequence[_OrderFeature]) -> float:
        """Quantos pixels as features passam do corredor; zero quando a ordem está preservada.

        `admits` responde sim ou não, que basta para aceitar ou recusar uma colocação inteira.
        O refino por aresta precisa da medida: quando a colocação de base já cruza um vizinho,
        as quatro arestas partem de uma posição irregular, e o que se exige de cada candidato
        é não piorar o que já está errado — a mesma decisão que o refino por elemento toma ao
        recentrar a janela na correção mínima, só que legível aresta a aresta.
        """
        return sum(
            max(0.0, low - feature.position) + max(0.0, feature.position - high)
            for (low, high), feature in zip(self.limits, features, strict=True)
        )

    def shift_limits(
        self, base: Sequence[_OrderFeature]
    ) -> tuple[tuple[float, float], tuple[float, float]]:
        """Deslocamento admissível em x e em y a partir de uma colocação de base.

        Todo ajuste permitido move as features juntas — a translação move as tangentes, o
        re-fit move o centro —, então o corredor de cada uma vira um intervalo do próprio
        deslocamento e a interseção é exata, não aproximação.
        """
        horizontal, vertical = _UNBOUNDED, _UNBOUNDED
        for (low, high), feature in zip(self.limits, base, strict=True):
            interval = (low - feature.position, high - feature.position)
            if feature.horizontal:
                vertical = (max(vertical[0], interval[0]), min(vertical[1], interval[1]))
            else:
                horizontal = (max(horizontal[0], interval[0]), min(horizontal[1], interval[1]))
        return horizontal, vertical


_UNBOUNDED: Final[tuple[float, float]] = (-math.inf, math.inf)


def _order_guard(
    reference: Sequence[_OrderFeature],
    barriers: Iterable[_OrderBarrier],
    *,
    separation: float,
    min_extent: float,
) -> _OrderGuard:
    """Fecha o corredor de cada feature do elemento contra os vizinhos já assentados."""
    limits: list[tuple[float, float]] = []
    for feature in reference:
        low, high = _UNBOUNDED
        if feature.extent >= min_extent:
            for barrier in barriers:
                if barrier.reference.horizontal != feature.horizontal:
                    continue
                overlap = min(feature.upper, barrier.reference.upper) - max(
                    feature.lower, barrier.reference.lower
                )
                if overlap < ORDER_GUARD_MIN_OVERLAP_RATIO * feature.extent:
                    continue
                delta = feature.position - barrier.reference.position
                # Mais perto que a tolerância da tinta é o mesmo traço: não há ordem
                # declarada entre os dois, e é o caso que o traçado resolve com `keep_apart`.
                if abs(delta) <= separation:
                    continue
                # O corredor para uma tolerância ANTES da tinta do vizinho, não sobre ela:
                # encostar já é o defeito — foi encostando que a aresta do campo colheu a
                # cobertura do muro. A mesma tolerância que decide se existe ordem entre
                # duas features decide o quanto dessa ordem precisa sobreviver ao refino.
                if delta > 0:
                    low = max(low, barrier.placed + separation)
                else:
                    high = min(high, barrier.placed - separation)
        limits.append((low, high))
    return _OrderGuard(limits=tuple(limits))


def _search_interval(
    limit: tuple[float, float], window: float
) -> tuple[float, float, float] | None:
    """Faixa de busca e âncora num eixo: a janela do empurrão cortada pelo corredor da ordem.

    Quando a janela inteira cai fora do corredor — o que só acontece quando a colocação de
    base já cruzava um vizinho —, a janela é RECENTRADA na correção mínima que devolve o
    elemento ao corredor. O teto de 2% continua limitando quanto o elemento procura tinta;
    ele não pode impedir a correção que a ordem exige, e dentro do corredor o elemento não
    alcança a tinta do vizinho por construção.
    """
    low, high = limit
    if low >= high:
        # Corredor vazio: nenhuma colocação a partir desta base preserva a ordem.
        return None
    lower, upper = max(low, -window), min(high, window)
    if lower < upper:
        if lower < 0.0 < upper:
            return lower, upper, 0.0
        anchor = lower + _ORDER_ANCHOR_EPSILON if lower >= 0.0 else upper - _ORDER_ANCHOR_EPSILON
        return lower, upper, _clamped(anchor, lower, upper)
    anchor = _clamped(
        low + _ORDER_ANCHOR_EPSILON if low > 0 else high - _ORDER_ANCHOR_EPSILON, low, high
    )
    return max(low, anchor - window), min(high, anchor + window), anchor


def _direction_kernel(direction: tuple[float, float], length: int) -> NDArray[np.uint8]:
    """Elemento estruturante de um segmento centrado, na direção pedida.

    Lado ímpar para o centro ser um pixel só; o sentido não importa, porque um segmento que
    passa pelo centro é simétrico. `cv2.getStructuringElement` só entrega retângulo, elipse e
    cruz — nenhum deles é um segmento oblíquo —, então a reta é desenhada.
    """
    size = length + 1 - length % 2
    half = size // 2
    kernel = np.zeros((size, size), dtype=np.uint8)
    step_x, step_y = round(direction[0] * half), round(direction[1] * half)
    cv2.line(
        kernel,
        (half - step_x, half - step_y),
        (half + step_x, half + step_y),
        color=1,
        thickness=1,
    )
    return kernel


def _clamped(value: float, lower: float, upper: float) -> float:
    """Mantém a âncora dentro do corredor mesmo quando ele é mais estreito que a folga."""
    if upper - lower <= 2 * _ORDER_ANCHOR_EPSILON:
        return (lower + upper) / 2
    return min(max(value, lower + _ORDER_ANCHOR_EPSILON), upper - _ORDER_ANCHOR_EPSILON)


def register_to_ink(
    proposals: list[VisionProposal],
    image_path: Path,
    *,
    config: VisionConfig | None = None,
) -> tuple[list[VisionProposal], InkRegistration]:
    """Assenta as propostas sobre a tinta em dois estágios, sem inventar forma.

    O estágio **global** aplica uma só transformação a todo o conjunto — quarto de volta
    exato, desvio fino de poucos graus, escala por eixo e translação. Ele corrige
    enquadramento e folha torta, e não consegue inventar geometria: se o desenho proposto
    estiver errado, continuará errado.

    O estágio **por elemento** existe porque um ótimo agregado pode sacrificar um elemento
    que já estava certo — foi o que aconteceu com o muro perimetral do Guaxindiba. Cada
    proposta é então reassentada sozinha, com o ajuste permitido pelo tipo: linha e
    contorno só recebem empurrão rígido (nunca re-forma), círculo e arco podem reajustar
    centro e raio contra a tinta. A base do refino é a melhor colocação já disponível
    (bruta ou pós-global) e o resultado só é aceito quando supera essa base, de modo que
    **nenhuma proposta sai com menos tinta do que a melhor colocação admissível que tinha**.

    O refino por elemento **nunca inverte a ordem traçada entre elementos**. Ele é a única
    etapa que move um elemento sozinho, e num croqui cheio de linhas longas e paralelas a
    cobertura premia qualquer tinta alcançada: sem essa lei o contorno do campo pousa na
    tinta do muro vizinho e o muro pousa na linha do campo — os dois com cobertura alta e o
    DXF espelhado, porque o solver honra o lado do traçado. Os elementos são assentados em
    ordem de cobertura decrescente (quem tem mais tinta manda; empate pelo id, para a saída
    ser determinística) e cada um recebe um corredor fechado pelas tangentes já assentadas.
    """
    effective_config = config or VisionConfig()
    if not proposals:
        return proposals, InkRegistration(1.0, 1.0, 0.0, 0.0, 0.0, 0.0)
    image = cv2.imread(str(image_path.resolve(strict=True)), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"imagem ilegível: {image_path.name}")
    resized, scale = _resize_for_detection(image, effective_config.max_dimension)
    _grayscale, mask = _ink_mask(resized)
    tolerance = max(1, effective_config.ink_corroboration_tolerance_px)
    reachable = cv2.dilate(
        mask,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (tolerance * 2 + 1, tolerance * 2 + 1)),
        iterations=1,
    )
    height, width = reachable.shape[:2]
    sample_count = effective_config.ink_corroboration_samples

    def measure(points: NDArray[np.float64]) -> float:
        """Fração dos pontos que cai sobre tinta alcançável, na escala da detecção."""
        columns = np.clip((points[:, 0] * scale).astype(np.int64), 0, width - 1)
        rows = np.clip((points[:, 1] * scale).astype(np.int64), 0, height - 1)
        return float((reachable[rows, columns] > 0).mean())

    run_length = max(1, round(TIP_MIN_INK_RUN_TOLERANCES * tolerance))
    fields: dict[tuple[float, float], Callable[[NDArray[np.float64]], float]] = {}

    def runs_along(direction: tuple[float, float]) -> Callable[[NDArray[np.float64]], float]:
        """Medida da tinta que testemunha um trecho contínuo NESTA direção.

        Erode a tinta com um segmento na direção pedida — some tudo que não se estende por
        `run_length`, que é como um risco perpendicular desaparece — e devolve o halo apenas
        na PERPENDICULAR, que é para o que ele existe aqui: alcançar o traço cujo centro a
        proposta não pegou em cheio. Devolvê-lo também na direção reporia exatamente o que a
        erosão tirou: medido no Guaxindiba, a ponta voltava a parar em y=2121, ainda dentro do
        risco cruzante, e a cadeia continuava estourada.
        """
        key = (round(direction[0], 3), round(direction[1], 3))
        existing = fields.get(key)
        if existing is not None:
            return existing
        along = cv2.erode(mask, _direction_kernel(key, run_length), iterations=1)
        field = cv2.dilate(along, _direction_kernel((-key[1], key[0]), tolerance * 2), iterations=1)

        def on_a_run(points: NDArray[np.float64]) -> float:
            columns = np.clip((points[:, 0] * scale).astype(np.int64), 0, width - 1)
            rows = np.clip((points[:, 1] * scale).astype(np.int64), 0, height - 1)
            return float((field[rows, columns] > 0).mean())

        fields[key] = on_a_run
        return on_a_run

    def sampled(geometry: PixelGeometryValue) -> NDArray[np.float64]:
        return np.asarray(_sample_points(geometry, sample_count), dtype=np.float64)

    samples = np.concatenate([sampled(proposal.geometry) for proposal in proposals])
    centre = (float(samples[:, 0].mean()), float(samples[:, 1].mean()))

    centred = samples - np.array(centre)
    turned = {
        degrees: np.column_stack(_quarter_turn(centred[:, 0], centred[:, 1], degrees))
        for degrees in (0, 90, 180, 270)
    }

    def coverage(points: NDArray[np.float64], transform: _Transform) -> float:
        scale_x, scale_y, offset_x, offset_y = transform
        moved_x = centre[0] + points[:, 0] * scale_x + offset_x
        moved_y = centre[1] + points[:, 1] * scale_y + offset_y
        return measure(np.column_stack((moved_x, moved_y)))

    def evaluator(points: NDArray[np.float64]) -> Callable[[_Transform], float]:
        # Fecha sobre os pontos do candidato em vez de ler a variável do laço: fechar sobre
        # a variável faria todos os candidatos medirem a última orientação avaliada.
        def evaluate(transform: _Transform) -> float:
            return coverage(points, transform)

        return evaluate

    identity: _Transform = (1.0, 1.0, 0.0, 0.0)
    baseline = coverage(turned[0], identity)
    best_score, best_transform, best_quarter = baseline, identity, 0
    span = max(image.shape[0], image.shape[1])
    # Busca grosseira e depois fina, por orientação: determinística e explicável, ao
    # contrário de um otimizador opaco cujo resultado ninguém consegue auditar depois.
    for degrees in (0, 90, 180, 270):
        points = turned[degrees]
        local_score = coverage(points, identity)
        local_transform = identity
        for shift_step, scale_step, radius in ((span * 0.02, 0.04, 8), (span * 0.004, 0.008, 6)):
            local_score, local_transform = _best_on_grid(
                evaluator(points),
                local_transform,
                local_score,
                shift_step=shift_step,
                scale_step=scale_step,
                shift_radius=radius,
                scale_radius=2,
            )
        if local_score > best_score:
            best_score, best_transform, best_quarter = local_score, local_transform, degrees

    # Rotação fina ao redor do quarto de volta vencedor. A translação é reotimizada junto
    # em janela curta: girar em torno do centroide desloca as pontas, não o centro.
    fine_rotation = 0.0
    for angle_span, angle_step in (
        (ROTATION_SEARCH_SPAN_DEGREES, ROTATION_SEARCH_STEP_DEGREES),
        (ROTATION_REFINE_SPAN_DEGREES, ROTATION_REFINE_STEP_DEGREES),
    ):
        centre_angle = fine_rotation
        steps = round(angle_span / angle_step)
        for index in range(-steps, steps + 1):
            angle = round(centre_angle + index * angle_step, 6)
            score, transform = _best_on_grid(
                evaluator(_rotate_about_origin(turned[best_quarter], angle)),
                best_transform,
                best_score,
                shift_step=span * 0.004,
                scale_step=0.008,
                shift_radius=4,
                scale_radius=1,
            )
            if score > best_score:
                best_score, best_transform, fine_rotation = score, transform, angle

    registration = InkRegistration(
        rotation_degrees=best_quarter,
        fine_rotation_degrees=fine_rotation,
        scale_x=best_transform[0],
        scale_y=best_transform[1],
        offset_x=best_transform[2],
        offset_y=best_transform[3],
        coverage_before=round(baseline, 4),
        coverage_after=round(best_score, 4),
    )
    globally = [_registered(proposal, registration, centre) for proposal in proposals]

    minimum_extent = span * ORDER_GUARD_MIN_EXTENT_RATIO
    # Duas tangentes mais próximas que a tolerância da tinta caem no mesmo traço: entre elas
    # não há ordem para preservar. A tolerância é medida na escala da detecção, então volta
    # para a escala da imagem de origem, que é onde a geometria vive.
    separation = tolerance / scale
    coverage_raw = [measure(sampled(item.geometry)) for item in proposals]
    coverage_global = [measure(sampled(item.geometry)) for item in globally]
    # Um só modo por elemento, decidido nas DUAS colocações: assim a feature de referência,
    # a de base e a do candidato falam da mesma coisa, e o corredor continua exato.
    modes: list[OrderMode] = [
        "centre"
        if _order_mode(original.geometry) == "centre" and _order_mode(moved.geometry) == "centre"
        else "bounds"
        for original, moved in zip(proposals, globally, strict=True)
    ]
    reference = [
        _order_features(item.geometry, mode=mode)
        for item, mode in zip(globally, modes, strict=True)
    ]

    placed: list[PixelGeometryValue | None] = [None] * len(proposals)
    reports: list[ElementRegistration | None] = [None] * len(proposals)
    barriers: list[_OrderBarrier] = []
    settled = sorted(
        range(len(proposals)),
        key=lambda index: (-max(coverage_raw[index], coverage_global[index]), proposals[index].id),
    )
    for index in settled:
        geometry, report = _refine_element(
            proposals[index],
            globally[index],
            coverage_raw=coverage_raw[index],
            coverage_global=coverage_global[index],
            mode=modes[index],
            guard=_order_guard(
                reference[index],
                barriers,
                separation=separation,
                min_extent=minimum_extent,
            ),
            measure=measure,
            runs_along=runs_along,
            sampled=sampled,
            samples=sample_count,
            span=span,
        )
        placed[index] = geometry
        reports[index] = report
        barriers.extend(
            _order_barriers(
                reference[index],
                _order_features(geometry, mode=modes[index]),
                min_extent=minimum_extent,
            )
        )

    refined = [
        moved.model_copy(update={"geometry": geometry})
        for moved, geometry in zip(globally, placed, strict=True)
    ]
    coverage_refined = measure(np.concatenate([sampled(item.geometry) for item in refined]))
    return refined, replace(
        registration,
        coverage_refined=round(coverage_refined, 4),
        elements=tuple(report for report in reports if report is not None),
    )


def _refine_element(
    original: VisionProposal,
    moved: VisionProposal,
    *,
    coverage_raw: float,
    coverage_global: float,
    mode: OrderMode,
    guard: _OrderGuard,
    measure: Callable[[NDArray[np.float64]], float],
    runs_along: _RunField,
    sampled: Callable[[PixelGeometryValue], NDArray[np.float64]],
    samples: int,
    span: float,
) -> tuple[PixelGeometryValue, ElementRegistration]:
    """Reassenta uma proposta sozinha, com o ajuste que o tipo dela autoriza.

    A escolha entre colocação bruta e pós-global também é do refino, e também move um
    elemento sozinho: no Guaxindiba as duas colocações estão a ~700 px uma da outra, e foi
    o conjunto misturado — muro no bruto, campo no pós-global — que trocou as duas linhas
    de tinta. Por isso a base passa pelo mesmo corredor do empurrão, e a outra colocação
    entra como alternativa apenas quando a preferida não tem nenhuma posição admissível.

    É aqui que a janela de orientação do arco é decidida, porque é o último ponto do
    caminho que ainda vê a PROPOSTA: a geometria em pixels não guarda de onde veio a
    abertura angular, e sem a proposta o re-fit trataria observação e chute como iguais.
    """
    # Orientação observada nas âncoras é evidência e só pode ser lapidada; orientação
    # fabricada precisa ser reconquistada, e aí a busca varre a volta inteira.
    orientation_span = (
        ARC_OBSERVED_ORIENTATION_SPAN_DEGREES if original.arc_angles_observed else None
    )
    # O estágio global otimiza o agregado e pode piorar um elemento que já estava certo.
    # Partir da melhor colocação disponível é o que impede o conjunto de pagar essa conta.
    preferred: Literal["raw", "global"] = "raw" if coverage_raw > coverage_global else "global"
    alternate: Literal["raw", "global"] = "global" if preferred == "raw" else "raw"
    geometry_of = {"raw": original.geometry, "global": moved.geometry}
    coverage_of = {"raw": coverage_raw, "global": coverage_global}

    base = preferred
    settled: _Refinement | None = None
    coverage_refined = coverage_of[preferred]
    relocated = False
    for candidate_base in (preferred, alternate):
        base_geometry = geometry_of[candidate_base]
        base_coverage = coverage_of[candidate_base]
        admitted = guard.admits(_order_features(base_geometry, mode=mode))
        refined = _refined_geometry(
            base_geometry,
            base_coverage,
            measure=measure,
            runs_along=runs_along,
            samples=samples,
            window=_element_window(base_geometry, span),
            span=span,
            mode=mode,
            guard=guard,
            orientation_span=orientation_span,
        )
        if refined is None:
            continue
        # Remede a geometria final pelo mesmo caminho da conferência: a busca trabalha em
        # pontos crus, e o recorte em zero da construção poderia deslocar o resultado.
        measured = measure(sampled(refined.geometry)) if refined.kind != "none" else base_coverage
        # `tips` melhora a EXTENSÃO corroborada, que sobe sem a cobertura subir: uma linha
        # curta que estica sobre o traço continua com cobertura 1,0 e passa a testemunhar mais
        # tinta. Reverter por empate apagaria justamente essa correção. Todo o resto do refino
        # só muda posição, e aí empate continua sendo motivo para ficar onde estava.
        improved = measured > base_coverage or (
            refined.kind == "tips" and measured >= base_coverage
        )
        # Voltar para a base só é opção quando a base preserva a ordem. Quando ela cruza
        # vizinho, mover é obrigação, e a colocação admissível vale mesmo com menos tinta.
        if not improved and admitted:
            refined = _Refinement(geometry=base_geometry, kind="none")
            measured = base_coverage
        base, settled, coverage_refined = candidate_base, refined, measured
        # Ordem mandou: ou a base preferida foi abandonada, ou ela cruzava e o elemento
        # precisou voltar para o corredor. Nos dois casos quem decidiu não foi a tinta.
        relocated = not admitted or candidate_base != preferred
        break

    if settled is None:
        # Nenhuma colocação preserva a ordem: a proposta é incompatível com as vizinhas.
        # Ficar na base preferida e declarar é honesto; escolher um lado em silêncio não é.
        settled = _Refinement(geometry=geometry_of[preferred], kind="none")
    return settled.geometry, ElementRegistration(
        proposal_id=original.id,
        label=original.label,
        kind=original.kind,
        coverage_raw=round(coverage_raw, 4),
        coverage_global=round(coverage_global, 4),
        coverage_refined=round(coverage_refined, 4),
        base=base,
        refinement=settled.kind,
        centre_shift_px=round(settled.centre_shift_px, 2),
        radius_delta_px=round(settled.radius_delta_px, 2),
        orientation_delta_degrees=round(settled.orientation_delta_degrees, 2),
        edge_shifts_px=(
            round(settled.edge_shifts_px[0], 2),
            round(settled.edge_shifts_px[1], 2),
            round(settled.edge_shifts_px[2], 2),
            round(settled.edge_shifts_px[3], 2),
        ),
        tip_shifts_px=(
            round(settled.tip_shifts_px[0], 2),
            round(settled.tip_shifts_px[1], 2),
        ),
        order_constrained=relocated,
        order_unresolved=not guard.admits(_order_features(settled.geometry, mode=mode)),
    )


def _refined_geometry(
    geometry: PixelGeometryValue,
    base_coverage: float,
    *,
    measure: Callable[[NDArray[np.float64]], float],
    runs_along: _RunField,
    samples: int,
    window: float,
    span: float,
    mode: OrderMode,
    guard: _OrderGuard,
    orientation_span: float | None = None,
) -> _Refinement | None:
    """Melhor colocação ADMISSÍVEL a partir desta base, ou `None` se não existir nenhuma.

    `runs_along` só interessa à linha: é a evidência de trecho contínuo que decide onde uma
    ponta pode parar. Os outros ajustes movem o elemento inteiro ou uma aresta, e nenhum
    deles precisa distinguir a tinta própria da de um traço que cruza.

    `orientation_span` só interessa ao arco: é a meia-janela em graus dentro da qual a
    orientação pode ser lapidada. `None` é a volta inteira, que é o que a orientação
    fabricada exige.
    """
    if isinstance(geometry, PixelCircle):
        return _refit_circle(
            geometry, base_coverage, measure=measure, samples=samples, window=window, guard=guard
        )
    # Re-fit de arco só entra no modo `centre`, que é onde a ordem é medida por uma feature
    # que sobrevive ao giro. Fora dele o elemento é empurrado inteiro, e nada de forma muda.
    if mode == "centre" and isinstance(geometry, PixelPolyline):
        arc = _arc_of(geometry)
        if arc is not None:
            return _refit_arc(
                geometry,
                arc,
                base_coverage,
                measure=measure,
                samples=samples,
                window=window,
                guard=guard,
                orientation_span=orientation_span,
            )
    # Contorno fechado quase-retangular corrige TAMANHO, não só assentamento: cada aresta
    # busca a própria tinta. É o único ajuste deste estágio que muda a extensão de um
    # contorno, e é estreito de propósito — as quatro direções saem intactas e cada aresta
    # continua presa ao corredor da ordem.
    if mode == "bounds" and isinstance(geometry, PixelPolyline):
        edges = _rectangular_edges(geometry)
        if edges is not None:
            by_edge = _shift_edges(
                geometry,
                edges,
                measure=measure,
                samples=samples,
                span=span,
                guard=guard,
            )
            # `None` aqui é "por aresta não se aplica", não "não há colocação": o elemento cai
            # no empurrão rígido, que continua sendo o comportamento anterior inteiro.
            if by_edge is not None:
                return by_edge
    # Linha e contorno de qualquer outra forma só se movem inteiros. Deformá-los seria trocar
    # a observação do modelo por uma forma que a tinta sugere — o que este estágio não pode.
    pushed = _shift_rigidly(
        geometry,
        base_coverage,
        measure=measure,
        samples=samples,
        window=window,
        mode=mode,
        guard=guard,
    )
    # A linha ganha um segundo passo depois do empurrão: onde ela está é o empurrão que
    # resolve, até onde ela vai só as pontas resolvem. Nada disso muda a direção dela.
    if pushed is not None and isinstance(geometry, PixelLine):
        return _slide_line_tips(
            pushed,
            measure=measure,
            runs_along=runs_along,
            samples=samples,
            span=span,
            guard=guard,
        )
    return pushed


_SHIFT_LADDER: Final = (4, 16, 64)
"""Divisores da janela nos passes do empurrão: grosso, fino e acabamento.

O acabamento existe porque a janela agora escala com o elemento: sem o terceiro passe, um
contorno grande teria resolução final de dezenas de pixels.
"""


def _shift_search(
    base_coverage: float,
    evaluate: Callable[[float, float], float],
    window: float,
    limits: tuple[tuple[float, float], tuple[float, float]],
) -> tuple[float, float, float] | None:
    """Melhor empurrão (dx, dy) dentro da janela e do corredor da ordem, em grade fixa.

    Empate de cobertura fica com o **menor** deslocamento. Sem esse desempate a grade
    grossa aceita o primeiro empate que encontra, e como a janela escala com o elemento
    isso significava mover um contorno 335 px para ganhar exatamente a mesma tinta que um
    empurrão de 42 px daria: correção mínima é o que o refino deve procurar. O custo
    continua medido a partir da base, mesmo quando a busca começa longe dela.
    """
    horizontal = _search_interval(limits[0], window)
    vertical = _search_interval(limits[1], window)
    if horizontal is None or vertical is None:
        return None
    low_x, high_x, anchor_x = horizontal
    low_y, high_y, anchor_y = vertical
    start = base_coverage if anchor_x == 0.0 and anchor_y == 0.0 else evaluate(anchor_x, anchor_y)
    best_score, best_cost = start, math.hypot(anchor_x, anchor_y)
    best_x, best_y = anchor_x, anchor_y
    for divisor in _SHIFT_LADDER:
        step = window / divisor
        centre_x, centre_y = best_x, best_y
        for index_x in range(-4, 5):
            for index_y in range(-4, 5):
                shift_x = centre_x + index_x * step
                shift_y = centre_y + index_y * step
                if not low_x <= shift_x <= high_x or not low_y <= shift_y <= high_y:
                    continue
                score = evaluate(shift_x, shift_y)
                cost = math.hypot(shift_x, shift_y)
                if (score, -cost) > (best_score, -best_cost):
                    best_score, best_cost, best_x, best_y = score, cost, shift_x, shift_y
    return best_score, best_x, best_y


def _shift_rigidly(
    geometry: PixelGeometryValue,
    base_coverage: float,
    *,
    measure: Callable[[NDArray[np.float64]], float],
    samples: int,
    window: float,
    mode: OrderMode,
    guard: _OrderGuard,
) -> _Refinement | None:
    points = np.asarray(_sample_points(geometry, samples), dtype=np.float64)

    def evaluate(shift_x: float, shift_y: float) -> float:
        return measure(points + np.array([shift_x, shift_y]))

    # Translação move as features juntas, então o corredor vira um intervalo do próprio
    # deslocamento: o teste de ordem é exato e não custa nada dentro da busca.
    found = _shift_search(
        base_coverage, evaluate, window, guard.shift_limits(_order_features(geometry, mode=mode))
    )
    if found is None:
        return None
    score, shift_x, shift_y = found
    if score <= base_coverage and (shift_x, shift_y) == (0.0, 0.0):
        return _Refinement(geometry=geometry, kind="none")
    return _Refinement(
        geometry=_translated(geometry, shift_x, shift_y),
        kind="translation",
        centre_shift_px=math.hypot(shift_x, shift_y),
    )


_EDGE_SAMPLE_DIVISOR: Final = 4
"""A amostragem do elemento repartida entre as quatro arestas; cada uma mede a própria tinta."""


def _shift_edges(
    geometry: PixelPolyline,
    edges: Sequence[_RectangularEdge],
    *,
    measure: Callable[[NDArray[np.float64]], float],
    samples: int,
    span: float,
    guard: _OrderGuard,
) -> _Refinement | None:
    """Deslocamento perpendicular próprio para cada aresta, contra a tinta dela.

    O modelo erra TAMANHO, não só assentamento: no Guaxindiba o contorno do campo saiu 1,28x
    mais alto que a tinta. Empurrão rígido não conserta erro assim — ancorar o topo na tinta
    certa joga a base 285 px para dentro do patamar, e o encontro desenhado campo/patamar, que
    é o que amarra o traçado, deixa de existir. Cada aresta busca então a própria tinta, com
    quatro garantias:

    - **nunca-piora por aresta**: aresta que não encontra tinta melhor fica onde está, e a
      cobertura de cada uma é medida só nas amostras dela, na colocação de base, de modo que
      a busca de uma não dependa de onde as outras pararam;
    - **a lei da ordem vale por aresta**: o corredor que o refino por elemento fecha contra os
      vizinhos já assentados é o mesmo, e cada aresta responde pela feature que governa. O
      candidato é julgado no contorno **reconstruído** — um canto é interseção, e a aresta
      vizinha o desloca junto —, e ordem certa vence tinta, como no refino por elemento;
    - **correção mínima desempata**: cobertura igual fica com o menor deslocamento, aresta a
      aresta, o que minimiza a soma dos módulos;
    - **a forma sai preservada**: os cantos são a interseção das quatro retas deslocadas, as
      direções não giram e o contorno continua fechado.

    Cada passe varre o intervalo INTEIRO na resolução dele, em vez de refinar em torno do
    vencedor do passe anterior. A diferença é material aqui: um passe grosso anda mais que a
    tolerância da tinta e pode pular a tinta do próprio elemento, enxergando só a de um
    vizinho distante, e a partir daí o refino nunca mais volta. Medido no Guaxindiba: com
    refino em torno do vencedor, o topo da pequena área direita andava 284 px até a linha de
    outro elemento em vez dos 25 px até a própria — cobertura igual, correção onze vezes
    maior. Varrendo o intervalo inteiro, a correção mínima desempata de verdade.

    Devolve `None` quando o refino por aresta **não se aplica** a esta base: corredor da ordem
    sem folga para alguma aresta, ou correção de ordem que já achataria o contorno. Nesses
    casos o chamador cai no empurrão rígido, que move o elemento inteiro e não deforma nada —
    o comportamento anterior, intacto.
    """
    windows = [_edge_window(geometry, edge, span) for edge in edges]
    features = _order_features(geometry, mode="bounds")

    def bounded(margins: Sequence[float]) -> list[tuple[float, float, float]] | None:
        found: list[tuple[float, float, float]] = []
        for edge, window, margin in zip(edges, windows, margins, strict=True):
            low, high = guard.limits[edge.feature]
            position = features[edge.feature].position
            interval = _search_interval((low - position + margin, high - position - margin), window)
            if interval is None:
                return None
            found.append(interval)
        return found

    # Primeiro sem folga, só para saber o alcance de cada orientação; depois com a folga que
    # esse alcance pode consumir. Duas passadas fixas, sem iterar até convergir.
    reachable = bounded([0.0] * 4)
    if reachable is None:
        return None
    reach = {True: 0.0, False: 0.0}
    for edge, interval in zip(edges, reachable, strict=True):
        reach[edge.horizontal] = max(reach[edge.horizontal], abs(interval[0]), abs(interval[1]))
    intervals = bounded(
        [
            _edge_slope(geometry, edge) * reach[not edge.horizontal] + _ORDER_ANCHOR_EPSILON
            for edge in edges
        ]
    )
    if intervals is None:
        return None
    shifts = [interval[2] for interval in intervals]
    segments = [_edge_samples(geometry, edge, samples) for edge in edges]
    minimum = (
        EDGE_MIN_EXTENT_RATIO * (features[1].position - features[0].position),
        EDGE_MIN_EXTENT_RATIO * (features[3].position - features[2].position),
    )

    def coverage_of(index: int, shift: float) -> float:
        edge = edges[index]
        offset = np.array([0.0, shift]) if edge.horizontal else np.array([shift, 0.0])
        return measure(segments[index] + offset)

    def state_of(index: int, shift: float) -> tuple[float, bool]:
        """Violação da ordem e se o contorno sobrevive, medidas na forma reconstruída."""
        candidate = list(shifts)
        candidate[index] = shift
        moved = _order_features(_with_edge_shifts(geometry, edges, candidate), mode="bounds")
        kept = (
            moved[1].position - moved[0].position >= minimum[0]
            and moved[3].position - moved[2].position >= minimum[1]
        )
        return guard.violation(moved), kept

    # A correção que a ordem já exige não pode, sozinha, achatar o elemento: quando exige,
    # quem responde é o empurrão rígido, porque ordem é defeito de posição e não de tamanho.
    # O índice aqui é indiferente — o candidato é o próprio valor atual, então o que se mede
    # é o estado das quatro âncoras juntas.
    if not state_of(0, shifts[0])[1]:
        return None

    for divisor in _SHIFT_LADDER:
        for index, window in enumerate(windows):
            low, high = intervals[index][0], intervals[index][1]
            best_shift = shifts[index]
            best = (
                -state_of(index, best_shift)[0],
                coverage_of(index, best_shift),
                -abs(best_shift),
            )
            steps = max(1, math.ceil((high - low) / (window / divisor)))
            for step in range(steps + 1):
                shift = low + (high - low) * step / steps
                score, cost = coverage_of(index, shift), abs(shift)
                # A reconstrução só é paga quando o candidato tem chance: com a ordem já
                # preservada, nenhum candidato pode melhorar o primeiro termo da chave.
                if best[0] == 0.0 and (score, -cost) <= (best[1], best[2]):
                    continue
                violation, kept = state_of(index, shift)
                if not kept:
                    continue
                if (-violation, score, -cost) > best:
                    best, best_shift = (-violation, score, -cost), shift
            shifts[index] = best_shift

    if all(shift == 0.0 for shift in shifts):
        return _Refinement(geometry=geometry, kind="none")
    refined = _with_edge_shifts(geometry, edges, shifts)
    by_role = [0.0, 0.0, 0.0, 0.0]
    for edge, shift in zip(edges, shifts, strict=True):
        by_role[edge.feature] = shift
    return _Refinement(
        geometry=refined,
        kind="edges",
        centre_shift_px=math.dist(_corner_centre(geometry), _corner_centre(refined)),
        edge_shifts_px=(by_role[0], by_role[1], by_role[2], by_role[3]),
    )


def _tip_window(length: float, span: float) -> float:
    """Janela do deslizamento de uma ponta, com o mesmo piso e teto do refino por aresta."""
    return min(
        max(span * ELEMENT_SHIFT_SPAN_RATIO, TIP_TRAVEL_EXTENT_RATIO * length),
        span * EDGE_SHIFT_MAX_SPAN_RATIO,
    )


def _slide_line_tips(
    pushed: _Refinement,
    *,
    measure: Callable[[NDArray[np.float64]], float],
    runs_along: _RunField,
    samples: int,
    span: float,
    guard: _OrderGuard,
) -> _Refinement:
    """Depois do empurrão, cada ponta desliza AO LONGO da linha até a extensão que tem tinta.

    O empurrão rígido acerta ONDE a linha está e não tem como acertar ATÉ ONDE ela vai. No
    Guaxindiba a linha de meio de campo saiu 479 px mais comprida que o traço, com a ponta de
    cima pousada no pedaço de tinta da cota "6,60" — cobertura alta o bastante para o empurrão
    ficar satisfeito, e ponta órfã o bastante para o encosto com as arestas do campo não
    fechar. Sem esse encosto o traçado não amarra a linha ao campo e a cota some no solver.

    O que se maximiza é o **comprimento útil**: tinta coberta menos comprimento sem tinta,
    contado em pixels. Cobertura sozinha encolheria a linha até um toco sobre o traço mais
    grosso, e comprimento sozinho a esticaria pela folha inteira; a diferença entre os dois
    para exatamente onde a tinta acaba. É também o critério que decide um vão: a ponta só
    atravessa um trecho sem tinta quando o traço do outro lado é mais longo que o vão — foi
    o que manteve o toco da cota fora da linha, 69 px de tinta atrás de um vão de 275 px.

    Encolher e esticar não são simétricos, e a assimetria é o que impede a linha de crescer
    sobre traço alheio. Encolher tem parada natural: a tinta acaba e o comprimento útil para
    de subir. Esticar só tem parada quando a tinta acaba **dentro da janela** — quando ela
    segue além, o traço não diz onde a linha termina, e escolher um fim seria inventar
    extensão. Nesse caso a ponta não estica; ela só pode encolher. Sem essa regra o portão do
    Guaxindiba, que é uma abertura de 3,10 m desenhada sobre a linha do muro, crescia 35% para
    cada lado engolindo a tinta do muro e apagando o vão que ele existe para declarar.

    **Traço cruzante não é fim de linha.** Cobertura e comprimento útil só sabem se há tinta,
    não de quem ela é, e um risco perpendicular tem tinta: com o halo, o risco do muro e a
    linha que ele cruza viram uma mancha contínua, e a ponta para na borda dessa mancha sem
    nunca alcançar a tinta própria. Por isso uma parada só é aceita onde a tinta testemunha um
    trecho contínuo de pelo menos `TIP_MIN_INK_RUN_TOLERANCES` tolerâncias NA DIREÇÃO da linha
    (`runs_along`); onde a tinta é só espessura de traço, a ponta segue deslizando. Vale para
    encolher e para esticar, nas duas pontas. Medido no Guaxindiba: a ponta de cima da linha de
    meio parava em y=2096, 44 px antes da própria tinta, encostada na faixa do muro em vez da
    do campo — o 21,75 amarrava na faixa errada e a cadeia estourava em três resíduos de 2,20 m.

    O preço declarado é um resíduo para DENTRO da linha, da ordem da tolerância: a ponta pousa
    onde o trecho mínimo já está inteiro, não na primeira tinta. Não se troca por menos: no
    encontro em T a tinta do risco e a da linha se tocam, então "onde a tinta própria começa"
    é, no pixel, o topo do risco — e parar ali é justamente o defeito.

    As amostras têm passo fixo para que candidatos de comprimentos diferentes sejam comparados
    na mesma resolução.

    Quatro guardas: a cobertura nunca piora; a ordem nunca piora, pelo mesmo corredor e pelas
    mesmas barreiras do refino por elemento, medida na linha reconstruída; a linha não encolhe
    além do piso de extensão; e a direção sai intacta, porque as duas pontas só se movem sobre
    a própria reta — uma ponta errada não arrasta a outra.
    """
    line = pushed.geometry
    if not isinstance(line, PixelLine):
        return pushed
    start = np.array([line.start.x, line.start.y], dtype=np.float64)
    finish = np.array([line.end.x, line.end.y], dtype=np.float64)
    length = float(np.hypot(*(finish - start)))
    if length < EDGE_MIN_LENGTH_PX:
        return pushed
    direction = (finish - start) / length
    window = _tip_window(length, span)
    # O passo das amostras acompanha o passo mais fino da busca. Amostrar mais grosso que o
    # que a busca consegue mover deixa o comprimento útil com um quantum maior que a decisão:
    # medido na fixture, um vão de 74 px lido em passos de 16 px empatava com um traço de 64
    # px do outro lado dele, e a ponta atravessava o vão para colher tinta que não era dela.
    spacing = min(length / samples, window / _SHIFT_LADDER[-1])
    minimum = EDGE_MIN_EXTENT_RATIO * length

    def built(travel: Sequence[float]) -> tuple[PixelLine, float]:
        first = start + direction * travel[0]
        last = finish + direction * travel[1]
        return (
            PixelLine(
                start=PixelPoint(x=max(0.0, first[0]), y=max(0.0, first[1])),
                end=PixelPoint(x=max(0.0, last[0]), y=max(0.0, last[1])),
            ),
            length + travel[1] - travel[0],
        )

    def state_of(travel: Sequence[float]) -> tuple[float, float, float] | None:
        """Violação da ordem, comprimento útil e cobertura — ou `None` se encolheu demais."""
        moved, extent = built(travel)
        if extent < minimum:
            return None
        points = np.linspace(
            (moved.start.x, moved.start.y),
            (moved.end.x, moved.end.y),
            max(2, round(extent / spacing) + 1),
        )
        coverage = measure(points)
        violation = guard.violation(_order_features(moved, mode="bounds"))
        return violation, extent * (2 * coverage - 1), coverage

    on_a_run = runs_along((float(direction[0]), float(direction[1])))

    def stops_on_own_run(travel: Sequence[float], index: int) -> bool:
        """Esta ponta pararia sobre tinta que se estende NA DIREÇÃO da linha?

        Só a ponta que está se movendo é julgada: a outra pode estar num lugar que a evidência
        de trecho não sustenta, e prendê-la faria uma ponta errada custar a que ia acertar.
        """
        moved, _extent = built(travel)
        tip = moved.start if index == 0 else moved.end
        return on_a_run(np.array([[tip.x, tip.y]], dtype=np.float64)) >= 1.0

    def stroke_runs_past(index: int) -> bool:
        """A tinta cobre a janela inteira além desta ponta?

        Se cobre, o traço continua e não existe evidência de onde a linha acaba: a ponta pode
        encolher, nunca esticar. É a diferença entre corrigir a extensão observada e adotar a
        extensão do vizinho colinear.
        """
        outward = -direction if index == 0 else direction
        origin = start if index == 0 else finish
        probe = np.linspace(origin, origin + outward * window, max(2, round(window / spacing) + 1))
        return measure(probe) >= 1.0

    limits = [
        (0.0, window) if stroke_runs_past(0) else (-window, window),
        (-window, 0.0) if stroke_runs_past(1) else (-window, window),
    ]

    def reaching_a_run(index: int) -> tuple[float, float]:
        """Faixa desta ponta, estendida até a correção mínima que a põe sobre trecho próprio.

        Mesmo princípio do corredor da ordem em `_search_interval`: o teto limita quanto a
        ponta PROCURA tinta, e não pode impedir a correção que a lei exige — aqui a lei é a de
        que traço cruzante não é fim de linha. Sem isso a regra ficaria pior que o defeito: no
        Guaxindiba o trecho próprio começa 359 px adiante da ponta e o teto da janela dá 336,
        então nenhuma parada honesta caberia e a ponta ficaria onde o modelo a pôs, 344 px
        além da tinta, sobre o toco da cota "6,60".

        A extensão vale só para ENCOLHER, e no máximo até o piso de extensão: esticar até um
        trecho distante seria adotar extensão que a folha não deu, que é o que a assimetria do
        R1e existe para impedir.
        """
        low, high = limits[index]
        if stops_on_own_run((0.0, 0.0), index):
            return low, high
        inward = 1.0 if index == 0 else -1.0
        step = window / _SHIFT_LADDER[-1]
        distance = step
        while distance <= length - minimum:
            candidate = [0.0, 0.0]
            candidate[index] = inward * distance
            if stops_on_own_run(candidate, index):
                return min(low, inward * distance), max(high, inward * distance)
            distance += step
        return low, high

    reach = [reaching_a_run(0), reaching_a_run(1)]

    settled = state_of((0.0, 0.0))
    if settled is None:
        return pushed
    floor_coverage = settled[2]
    travel = [0.0, 0.0]
    for divisor in _SHIFT_LADDER:
        for index in (0, 1):
            best = state_of(travel)
            if best is None:
                return pushed
            # Parar sobre trecho próprio vem ANTES do comprimento útil, e depois da ordem: uma
            # ponta que já chegou ao halo de um cruzante tem cobertura cheia e comprimento
            # maior que qualquer parada honesta, então filtrar candidato não bastaria — ela
            # ficaria lá. Sair de cima do cruzante é obrigação, como sair de cima do vizinho.
            best_value = (
                -best[0],
                float(stops_on_own_run(travel, index)),
                best[1],
                -abs(travel[index]),
            )
            best_travel = travel[index]
            low, high = reach[index]
            steps = max(1, math.ceil((high - low) / (window / divisor)))
            for step in range(steps + 1):
                candidate = list(travel)
                candidate[index] = low + (high - low) * step / steps
                measured = state_of(candidate)
                # Cobertura nunca piora: esticar sobre folha em branco compra comprimento
                # útil sem comprar evidência, e este estágio não inventa extensão.
                if measured is None or measured[2] < floor_coverage:
                    continue
                # Parada só onde há trecho próprio: a tinta de um risco que cruza a linha não
                # diz até onde ela vai, e é a que o comprimento útil premiaria primeiro.
                if not stops_on_own_run(candidate, index):
                    continue
                value = (-measured[0], 1.0, measured[1], -abs(candidate[index]))
                if value > best_value:
                    best_value, best_travel = value, candidate[index]
            travel[index] = best_travel

    if travel == [0.0, 0.0]:
        return pushed
    moved, _extent = built(travel)
    return replace(
        pushed,
        geometry=moved,
        kind="tips",
        tip_shifts_px=(travel[0], travel[1]),
    )


def _corner_centre(geometry: PixelPolyline) -> tuple[float, float]:
    """Centro dos vértices: quanto o elemento andou no fim das contas, para o relatório."""
    count = len(geometry.points)
    return (
        sum(point.x for point in geometry.points) / count,
        sum(point.y for point in geometry.points) / count,
    )


def _translated(geometry: PixelGeometryValue, shift_x: float, shift_y: float) -> PixelGeometryValue:
    def point(x: float, y: float) -> PixelPoint:
        return PixelPoint(x=max(0.0, x + shift_x), y=max(0.0, y + shift_y))

    if isinstance(geometry, PixelLine):
        return PixelLine(
            start=point(geometry.start.x, geometry.start.y),
            end=point(geometry.end.x, geometry.end.y),
        )
    if isinstance(geometry, PixelCircle):
        return PixelCircle(
            center=point(geometry.center.x, geometry.center.y), radius=geometry.radius
        )
    return PixelPolyline(
        points=[point(item.x, item.y) for item in geometry.points],
        closed=geometry.closed,
    )


def _radius_ratios(base_ratio: float, step: float, radius: int) -> list[float]:
    """Fatores de raio da grade, presos à tolerância declarada."""
    ratios: list[float] = []
    for index in range(-radius, radius + 1):
        ratio = base_ratio + index * step
        if ratio <= 0 or abs(ratio - 1.0) > ELEMENT_RADIUS_TOLERANCE + 1e-9:
            continue
        ratios.append(ratio)
    return ratios


_RATIO_LADDER: Final = (3, 12, 48)
"""Divisores da tolerância de raio, um por passe do empurrão."""


def _refit_circle(
    geometry: PixelCircle,
    base_coverage: float,
    *,
    measure: Callable[[NDArray[np.float64]], float],
    samples: int,
    window: float,
    guard: _OrderGuard,
) -> _Refinement | None:
    """Reajusta centro e raio contra a tinta; a forma continua sendo um círculo.

    Como no empurrão rígido, empate de cobertura fica com a correção menor. A ordem é
    declarada pelo CENTRO, que o re-fit de raio não move: o corredor vira intervalo do
    deslocamento e vale para todos os raios da grade.
    """
    horizontal, vertical = guard.shift_limits(_order_features(geometry, mode="centre"))
    across = _search_interval(horizontal, window)
    along = _search_interval(vertical, window)
    if across is None or along is None:
        return None
    low_x, high_x, anchor_x = across
    low_y, high_y, anchor_y = along
    best = (base_coverage, 0.0, 0.0, 0.0, 1.0)
    if (anchor_x, anchor_y) != (0.0, 0.0):
        # A base cruza vizinho: o ponto de partida é a correção mínima que a ordem exige.
        best = (
            measure(
                _circle_points(
                    geometry.center.x + anchor_x,
                    geometry.center.y + anchor_y,
                    geometry.radius,
                    samples,
                )
            ),
            math.hypot(anchor_x, anchor_y),
            anchor_x,
            anchor_y,
            1.0,
        )
    for shift_divisor, ratio_divisor in zip(_SHIFT_LADDER, _RATIO_LADDER, strict=True):
        shift_step = window / shift_divisor
        ratio_step = ELEMENT_RADIUS_TOLERANCE / ratio_divisor
        _score, _cost, centre_x, centre_y, centre_ratio = best
        for index_x in range(-4, 5):
            for index_y in range(-4, 5):
                shift_x = centre_x + index_x * shift_step
                shift_y = centre_y + index_y * shift_step
                if not low_x <= shift_x <= high_x or not low_y <= shift_y <= high_y:
                    continue
                for ratio in _radius_ratios(centre_ratio, ratio_step, 3):
                    score = measure(
                        _circle_points(
                            geometry.center.x + shift_x,
                            geometry.center.y + shift_y,
                            geometry.radius * ratio,
                            samples,
                        )
                    )
                    cost = math.hypot(shift_x, shift_y) + abs(geometry.radius * (ratio - 1.0))
                    if (score, -cost) > (best[0], -best[1]):
                        best = (score, cost, shift_x, shift_y, ratio)
    score, _cost, shift_x, shift_y, ratio = best
    if score <= base_coverage and (shift_x, shift_y, ratio) == (0.0, 0.0, 1.0):
        return _Refinement(geometry=geometry, kind="none")
    return _Refinement(
        geometry=PixelCircle(
            center=PixelPoint(
                x=max(0.0, geometry.center.x + shift_x), y=max(0.0, geometry.center.y + shift_y)
            ),
            radius=geometry.radius * ratio,
        ),
        kind="circle",
        centre_shift_px=math.hypot(shift_x, shift_y),
        radius_delta_px=geometry.radius * (ratio - 1.0),
    )


def _signed_degrees(degrees: float) -> float:
    """Normaliza um giro para (-180, 180]: 350° é -10° de correção, não quase uma volta."""
    wrapped = degrees % 360.0
    return wrapped - 360.0 if wrapped > 180.0 else wrapped


def _refit_arc(
    geometry: PixelPolyline,
    fit: _CircleFit,
    base_coverage: float,
    *,
    measure: Callable[[NDArray[np.float64]], float],
    samples: int,
    window: float,
    guard: _OrderGuard,
    orientation_span: float | None = None,
) -> _Refinement | None:
    """Reajusta centro, raio e orientação do arco, preservando extensão angular e vértices.

    A orientação entra na busca com o alcance que a evidência autoriza. Sem
    `orientation_span` ela é reconquistada na volta inteira, que é o caso da abertura
    FABRICADA — arco de contrato anterior ao `geometry-extraction@2.0.0`, ou arco cujas
    âncoras vieram degeneradas: preservar valor fabricado não protegeria evidência nenhuma.
    Com `orientation_span`, a orientação veio das âncoras observadas e a busca só a lapida
    dentro de ±janela, com os mesmos passos: o modelo erra o assentamento, mas o que ele
    viu não pode ser substituído por um quarto de volta que colhe mais tinta de outra forma.

    O que continua preservado nos dois casos é a **extensão** — quanto o arco varre — e a
    contagem de pontos. Quando as âncoras foram observadas, essa extensão também é
    observação, e ela se propaga sozinha: sai dos extremos da polilinha-fonte.

    Descida por coordenada em duas rodadas: orientação (grossa e depois fina) e então
    centro/raio. Duas rodadas porque o melhor centro depende da orientação e vice-versa; a
    busca é monotônica, então rodada extra nunca piora. Empate de cobertura fica com a
    correção menor, medida em pixels — o giro entra como o arco que a ponta percorre
    (`raio * ângulo`), para somar com deslocamento e raio na mesma unidade.

    A ordem é declarada pelo centro do círculo ajustado, que o giro não move: a meia-lua
    pode virar para o lado da tinta sem que isso a leve para o outro lado de um vizinho.
    """
    source = np.array([[point.x, point.y] for point in geometry.points], dtype=np.float64)
    horizontal, vertical = guard.shift_limits(_order_features(geometry, mode="centre"))
    across = _search_interval(horizontal, window)
    along = _search_interval(vertical, window)
    if across is None or along is None:
        return None
    low_x, high_x, anchor_x = across
    low_y, high_y, anchor_y = along
    best = (base_coverage, 0.0, 0.0, 0.0, 1.0, 0.0)

    def points_of(
        shift_x: float, shift_y: float, ratio: float, orientation: float
    ) -> NDArray[np.float64]:
        return _arc_points(
            source,
            fit.centre_x + shift_x,
            fit.centre_y + shift_y,
            fit.radius * ratio,
            samples,
            orientation,
        )

    def cost_of(shift_x: float, shift_y: float, ratio: float, orientation: float) -> float:
        return (
            math.hypot(shift_x, shift_y)
            + abs(fit.radius * (ratio - 1.0))
            + fit.radius * abs(math.radians(_signed_degrees(orientation)))
        )

    def within_span(orientation: float) -> bool:
        # A janela é medida sobre o giro assinado: 355° é 5° de correção, e recusá-lo por
        # ser "quase uma volta" tiraria da lapidação metade do que ela existe para fazer.
        return orientation_span is None or abs(_signed_degrees(orientation)) <= orientation_span

    def consider(shift_x: float, shift_y: float, ratio: float, orientation: float) -> None:
        nonlocal best
        if not within_span(orientation):
            return
        score = measure(points_of(shift_x, shift_y, ratio, orientation))
        cost = cost_of(shift_x, shift_y, ratio, orientation)
        if (score, -cost) > (best[0], -best[1]):
            best = (score, cost, shift_x, shift_y, ratio, orientation)

    if (anchor_x, anchor_y) != (0.0, 0.0):
        # A base cruza vizinho: começar na correção mínima que a ordem exige, ainda que a
        # cobertura de lá seja menor. Ordem certa com menos tinta vence linha trocada.
        best = (
            measure(points_of(anchor_x, anchor_y, 1.0, 0.0)),
            math.hypot(anchor_x, anchor_y),
            anchor_x,
            anchor_y,
            1.0,
            0.0,
        )

    for _round in (0, 1):
        _score, _cost, shift_x, shift_y, ratio, _orientation = best
        # Varre a volta inteira; `within_span` é quem recorta a busca para ±janela quando a
        # orientação foi observada. Um só lugar decide o alcance, e ele vale também no
        # passe fino — senão a lapidação sairia da janela pelo arredondamento do vencedor.
        for index in range(round(360.0 / ARC_ORIENTATION_STEP_DEGREES)):
            consider(shift_x, shift_y, ratio, index * ARC_ORIENTATION_STEP_DEGREES)
        _score, _cost, shift_x, shift_y, ratio, coarse = best
        fine_steps = round(
            ARC_ORIENTATION_REFINE_SPAN_DEGREES / ARC_ORIENTATION_REFINE_STEP_DEGREES
        )
        for index in range(-fine_steps, fine_steps + 1):
            consider(shift_x, shift_y, ratio, coarse + index * ARC_ORIENTATION_REFINE_STEP_DEGREES)
        for shift_divisor, ratio_divisor in zip(_SHIFT_LADDER, _RATIO_LADDER, strict=True):
            shift_step = window / shift_divisor
            ratio_step = ELEMENT_RADIUS_TOLERANCE / ratio_divisor
            _score, _cost, centre_x, centre_y, centre_ratio, orientation = best
            for index_x in range(-4, 5):
                for index_y in range(-4, 5):
                    shift_x = centre_x + index_x * shift_step
                    shift_y = centre_y + index_y * shift_step
                    if not low_x <= shift_x <= high_x or not low_y <= shift_y <= high_y:
                        continue
                    for ratio in _radius_ratios(centre_ratio, ratio_step, 3):
                        consider(shift_x, shift_y, ratio, orientation)

    score, _cost, shift_x, shift_y, ratio, orientation = best
    if score <= base_coverage and (shift_x, shift_y, ratio, orientation) == (0.0, 0.0, 1.0, 0.0):
        return _Refinement(geometry=geometry, kind="none")
    rebuilt = _arc_points(
        source,
        fit.centre_x + shift_x,
        fit.centre_y + shift_y,
        fit.radius * ratio,
        len(geometry.points),
        orientation,
    )
    return _Refinement(
        geometry=PixelPolyline(
            points=[PixelPoint(x=max(0.0, float(x)), y=max(0.0, float(y))) for x, y in rebuilt],
            closed=False,
        ),
        kind="arc",
        centre_shift_px=math.hypot(shift_x, shift_y),
        radius_delta_px=fit.radius * (ratio - 1.0),
        orientation_delta_degrees=_signed_degrees(orientation),
    )


def _registered(
    proposal: VisionProposal, registration: InkRegistration, centre: tuple[float, float]
) -> VisionProposal:
    geometry = proposal.geometry
    if isinstance(geometry, PixelCircle):
        moved = registration.apply(geometry.center.x, geometry.center.y, centre=centre)
        updated: PixelGeometryValue = PixelCircle(
            center=PixelPoint(x=max(0.0, moved[0]), y=max(0.0, moved[1])),
            radius=geometry.radius * registration.uniform_scale,
        )
    elif isinstance(geometry, PixelLine):
        start = registration.apply(geometry.start.x, geometry.start.y, centre=centre)
        end = registration.apply(geometry.end.x, geometry.end.y, centre=centre)
        updated = PixelLine(
            start=PixelPoint(x=max(0.0, start[0]), y=max(0.0, start[1])),
            end=PixelPoint(x=max(0.0, end[0]), y=max(0.0, end[1])),
        )
    else:
        moved_points = [
            registration.apply(point.x, point.y, centre=centre) for point in geometry.points
        ]
        updated = PixelPolyline(
            points=[PixelPoint(x=max(0.0, x), y=max(0.0, y)) for x, y in moved_points],
            closed=geometry.closed,
        )
    return proposal.model_copy(update={"geometry": updated})


def _handwriting_mask(mask: NDArray[np.uint8], config: VisionConfig) -> NDArray[np.uint8]:
    """Marca as regiões de escrita à mão, sem ler o que está escrito.

    Caligrafia e desenho têm assinaturas opostas em morfologia: texto forma blocos
    baixos e densos de traço curto, desenho forma linhas longas, finas e isoladas.
    Dilatar ao longo da linha de escrita cola as letras de uma palavra num único
    componente, e aí espessura e densidade separam os dois casos.
    """
    height, width = mask.shape[:2]
    longest = max(height, width)
    span = max(3, longest // 110)
    text = np.zeros_like(mask)
    # O croqui traz escrita em três orientações. Colar só na horizontal deixa a palavra
    # vertical em pedaços soltos, que passam pelos testes e sobrevivem como traço.
    for kernel, across_height in (((span, 3), True), ((3, span), False)):
        glued = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_RECT, kernel), iterations=1)
        count, labels, stats, _centroids = cv2.connectedComponentsWithStats(glued, connectivity=8)
        for index in range(1, count):
            _left, _top, box_width, box_height, area = stats[index]
            thickness = box_height if across_height else box_width
            length = box_width if across_height else box_height
            if thickness > longest * config.handwriting_max_height_ratio:
                continue
            if length > longest * 0.5:
                # Atravessa meia folha: é desenho, não palavra.
                continue
            if area / float(box_width * box_height) < config.handwriting_min_density:
                # Traço esparso dentro da caixa: linha isolada, não escrita.
                continue
            text[labels == index] = 255
    return cv2.dilate(text, cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9)), iterations=1).astype(
        np.uint8
    )


def _drawing_region(mask: NDArray[np.uint8], config: VisionConfig) -> NDArray[np.int32] | None:
    """Maior contorno fechado da tinta: o desenho. Fora dele é borda de papel e sombra."""
    closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))
    contours, _hierarchy = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    largest = max(contours, key=cv2.contourArea)
    height, width = mask.shape[:2]
    if cv2.contourArea(largest) < height * width * config.drawing_region_min_area_ratio:
        # Sem um contorno dominante não há como afirmar onde termina o desenho.
        return None
    return cv2.convexHull(largest).astype(np.int32)


def _outside_drawing(
    proposal: VisionProposal, region: NDArray[np.int32], scale: float, margin: float
) -> bool:
    """Verdadeiro só quando a proposta inteira cai fora do desenho."""
    geometry = proposal.geometry
    if isinstance(geometry, PixelLine):
        points = [(geometry.start.x, geometry.start.y), (geometry.end.x, geometry.end.y)]
    elif isinstance(geometry, PixelCircle):
        points = [(geometry.center.x, geometry.center.y)]
    else:
        points = [(point.x, point.y) for point in geometry.points]
    return all(
        cv2.pointPolygonTest(region, (float(x * scale), float(y * scale)), True) < -margin
        for x, y in points
    )


def _covered_by_text(proposal: VisionProposal, text: NDArray[np.uint8], scale: float) -> bool:
    """Verdadeiro quando a proposta inteira mora dentro de região de escrita."""
    geometry = proposal.geometry
    if isinstance(geometry, PixelLine):
        points = [(geometry.start.x, geometry.start.y), (geometry.end.x, geometry.end.y)]
    elif isinstance(geometry, PixelCircle):
        points = [(geometry.center.x, geometry.center.y)]
    else:
        points = [(point.x, point.y) for point in geometry.points]
    height, width = text.shape[:2]
    for x, y in points:
        column = min(width - 1, max(0, int(x * scale)))
        row = min(height - 1, max(0, int(y * scale)))
        if text[row, column] == 0:
            return False
    return True


def detect_proposals(
    image_path: Path,
    *,
    dataset_id: str,
    page_number: int,
    config: VisionConfig | None = None,
) -> VisionProposalSet:
    """Detecta observações em pixels sem inferir escala, unidade ou semântica."""
    effective_config = config or VisionConfig()
    source = image_path.resolve(strict=True)
    image = cv2.imread(str(source), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"imagem ilegível: {source.name}")
    original_height, original_width = image.shape[:2]
    resized, scale = _resize_for_detection(image, effective_config.max_dimension)
    grayscale, mask = _ink_mask(resized)
    image_digest = _sha256(source)
    inverse_scale = 1 / scale
    lines = _line_proposals(mask, image_digest, inverse_scale, effective_config)
    circles = _circle_proposals(
        grayscale,
        mask,
        image_digest,
        inverse_scale,
        effective_config,
    )
    contours = _suppress_circle_like_contours(
        _contour_proposals(mask, image_digest, inverse_scale, effective_config),
        circles,
    )
    proposals = [*lines, *circles, *contours]
    suppressed_as_handwriting = 0
    suppressed_outside_drawing = 0
    if effective_config.suppress_handwriting:
        text = _handwriting_mask(mask, effective_config)
        kept = [item for item in proposals if not _covered_by_text(item, text, scale)]
        suppressed_as_handwriting = len(proposals) - len(kept)
        proposals = kept
    if effective_config.clip_to_drawing_region:
        region = _drawing_region(mask, effective_config)
        if region is not None:
            inside = [
                item
                for item in proposals
                if not _outside_drawing(
                    item, region, scale, effective_config.drawing_region_margin_px
                )
            ]
            suppressed_outside_drawing = len(proposals) - len(inside)
            proposals = inside
    # Sem pontuação, a proposta vai para o FIM do próprio tipo, e não para o topo:
    # ausência de medida não é qualidade máxima (ADR-0050, decisão 2). Este caminho é o do
    # detector, onde toda proposta tem score; a guarda existe para o dia em que um conjunto
    # sem score passar por aqui, e não para inventar ordem entre máquina e pessoa.
    proposals.sort(
        key=lambda item: (
            item.kind,
            -item.quality_score if item.quality_score is not None else 1.0,
            item.id,
        )
    )
    configured_limits = {
        "line": effective_config.max_lines,
        "circle": effective_config.max_circles,
        "contour": effective_config.max_contours,
    }
    counts_by_kind = {
        kind: sum(proposal.kind == kind for proposal in proposals) for kind in configured_limits
    }
    limit_reached = [
        kind for kind, limit in configured_limits.items() if counts_by_kind[kind] >= limit
    ]
    safety_notes = [
        "Coordinates are pixel observations, not engineering measurements.",
        "No scale, unit, object identity or dimension was inferred.",
        "Every proposal remains unresolved and non-exportable until reviewed.",
    ]
    if limit_reached:
        safety_notes.append(f"Configured proposal limit reached for: {', '.join(limit_reached)}.")
    if suppressed_outside_drawing:
        safety_notes.append(
            f"{suppressed_outside_drawing} proposals suppressed outside the drawing region."
        )
    if suppressed_as_handwriting:
        # Fica registrado: supressão é decisão do estágio, e precisa ser auditável.
        safety_notes.append(
            f"{suppressed_as_handwriting} proposals suppressed as handwriting regions."
        )
    return VisionProposalSet(
        dataset_id=dataset_id,
        page_number=page_number,
        image_sha256=image_digest,
        image_width_px=original_width,
        image_height_px=original_height,
        configured_limits=configured_limits,
        limit_reached=limit_reached,
        proposals=proposals,
        safety_notes=safety_notes,
    )


def _write_overlay(image_path: Path, proposals: VisionProposalSet, output_path: Path) -> None:
    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"imagem ilegível: {image_path.name}")
    overlay = image.copy()
    line_width = max(2, round(min(image.shape[:2]) / 600))
    counters = {"line": 0, "circle": 0, "contour": 0}
    colors = {"line": (67, 160, 71), "circle": (171, 71, 183), "contour": (42, 137, 224)}
    prefixes = {"line": "L", "circle": "C", "contour": "P"}
    overlay_thresholds = {"line": 0.20, "circle": 0.83, "contour": 0.04}
    # Proposta sem pontuação não é comparável a limiar de detector, e por isso é sempre
    # desenhada: esconder uma forma porque falta o número que ninguém mediu apagaria da
    # visão justamente o que uma pessoa declarou (ADR-0050, decisão 2).
    visible_proposals = [
        proposal
        for proposal in proposals.proposals
        if proposal.quality_score is None
        or proposal.quality_score >= overlay_thresholds[proposal.kind]
    ]
    for proposal in visible_proposals:
        counters[proposal.kind] += 1
        color = colors[proposal.kind]
        label = f"{prefixes[proposal.kind]}{counters[proposal.kind]:02d}"
        geometry = proposal.geometry
        anchor: tuple[int, int]
        if isinstance(geometry, PixelLine):
            start = (round(geometry.start.x), round(geometry.start.y))
            end = (round(geometry.end.x), round(geometry.end.y))
            cv2.line(overlay, start, end, color, line_width, cv2.LINE_AA)
            anchor = start
        elif isinstance(geometry, PixelCircle):
            center = (round(geometry.center.x), round(geometry.center.y))
            cv2.circle(overlay, center, round(geometry.radius), color, line_width, cv2.LINE_AA)
            anchor = (center[0] + round(geometry.radius), center[1])
        else:
            points = np.array(
                [[round(point.x), round(point.y)] for point in geometry.points],
                dtype=np.int32,
            )
            cv2.polylines(overlay, [points], True, color, line_width, cv2.LINE_AA)
            anchor = tuple(points[0])
        if counters[proposal.kind] <= 6:
            cv2.putText(
                overlay,
                label,
                anchor,
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                color,
                max(1, line_width - 1),
                cv2.LINE_AA,
            )
    rendered = cv2.addWeighted(overlay, 0.65, image, 0.35, 0)
    legend_height = max(56, round(rendered.shape[0] * 0.045))
    cv2.rectangle(rendered, (0, 0), (rendered.shape[1], legend_height), (24, 37, 31), -1)
    cv2.putText(
        rendered,
        "CV PROPOSALS - REVIEW OVERLAY - PIXELS ONLY - NOT EXPORTABLE",
        (18, round(legend_height * 0.62)),
        cv2.FONT_HERSHEY_SIMPLEX,
        max(0.55, rendered.shape[1] / 2600),
        (230, 244, 235),
        2,
        cv2.LINE_AA,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=output_path.parent,
        prefix=f".{output_path.stem}.",
        suffix=".png",
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        if not cv2.imwrite(str(temporary_path), rendered):
            raise OSError(f"falha ao escrever overlay: {output_path}")
        os.replace(temporary_path, output_path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def write_proposal_artifacts(
    image_path: Path,
    output_dir: Path,
    *,
    dataset_id: str,
    page_number: int,
    config: VisionConfig | None = None,
) -> tuple[VisionProposalSet, Path, Path]:
    proposal_set = detect_proposals(
        image_path,
        dataset_id=dataset_id,
        page_number=page_number,
        config=config,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    proposals_path = output_dir / "vision-proposals.json"
    overlay_path = output_dir / "vision-overlay.png"
    serialized = json.dumps(
        proposal_set.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    atomic_write_text(proposals_path, f"{serialized}\n")
    _write_overlay(image_path, proposal_set, overlay_path)
    return proposal_set, proposals_path, overlay_path
