"""Transformação determinística de propostas em pixels para rascunhos métricos.

O módulo nunca produz entidades ``exact``: uma calibração confirmada apenas permite
que o revisor preserve uma hipótese visual como geometria ``approximate``.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, replace
from itertools import product
from typing import Any
from uuid import UUID

from croquito_core.models import (
    CircleGeometry,
    Entity,
    EntityKind,
    LayerName,
    LineGeometry,
    Point2D,
    PolylineGeometry,
    Precision,
    Provenance,
    SceneRevision,
)
from croquito_worker.vision import (
    PixelCircle,
    PixelLine,
    PixelPoint,
    PixelPolyline,
    VisionProposal,
    VisionProposalSet,
)

HUMAN_ACCEPTED_PROPOSAL_SOURCE_TYPE = "vision_proposal_calibrated"
"""Provenance source type of an entity a professional accepted from a pixel proposal."""

CALIBRATION_DRIFT_TOLERANCE_M = 1e-6
"""Absolute tolerance, in metres, for revalidating a stored transform against a new scene."""

CALIBRATION_MAX_RMSE_M = 0.5
"""Uma calibração que não reproduz as próprias âncoras não é uma calibração."""

ISOTROPY_TOLERANCE = 1.01
"""Above this axis-scale ratio a circle can no longer be exported as a circle."""

ELLIPSE_SEGMENTS = 72
"""Segments used to sample a circle whose axes were scaled differently."""


class CalibrationError(ValueError):
    """A proposta ou os anchors não permitem uma transformação segura."""


@dataclass(frozen=True)
class CalibrationAnchor:
    proposal_id: str
    # Nulo significa "deixe o ajuste descobrir": as quatro arestas de um retângulo são
    # indistinguíveis para quem escolhe numa lista, e errar produz cisalhamento silencioso.
    entity_id: UUID | None = None
    reversed: bool = False


@dataclass(frozen=True)
class SimilarityTransform:
    """x_m = a*x_px - b*y_px + tx; y_m = b*x_px + a*y_px + ty."""

    a: float
    b: float
    tx: float
    ty: float
    rmse_m: float

    def point(self, point: PixelPoint) -> Point2D:
        return Point2D(
            x=self.a * point.x - self.b * point.y + self.tx,
            y=self.b * point.x + self.a * point.y + self.ty,
        )

    @property
    def scale_x_m_per_px(self) -> float:
        return math.hypot(self.a, self.b)

    @property
    def scale_y_m_per_px(self) -> float:
        return math.hypot(self.a, self.b)

    @property
    def anisotropy(self) -> float:
        return 1.0


@dataclass(frozen=True)
class AffineTransform:
    """x_m = m11*x_px + m12*y_px + tx; y_m = m21*x_px + m22*y_px + ty.

    Um croqui à mão raramente é isotrópico: as duas direções do papel podem estar em
    escalas diferentes. A similaridade não tem solução quando duas âncoras
    perpendiculares discordam da escala, então ela não serve para traçar a folha.
    O preço é que ângulos fora dos eixos das âncoras deixam de ser preservados.
    """

    m11: float
    m12: float
    m21: float
    m22: float
    tx: float
    ty: float
    rmse_m: float

    def point(self, point: PixelPoint) -> Point2D:
        return Point2D(
            x=self.m11 * point.x + self.m12 * point.y + self.tx,
            y=self.m21 * point.x + self.m22 * point.y + self.ty,
        )

    @property
    def scale_x_m_per_px(self) -> float:
        return math.hypot(self.m11, self.m21)

    @property
    def scale_y_m_per_px(self) -> float:
        return math.hypot(self.m12, self.m22)

    @property
    def anisotropy(self) -> float:
        scales = (self.scale_x_m_per_px, self.scale_y_m_per_px)
        smallest = min(scales)
        if smallest < 1e-12:
            raise CalibrationError("Escala degenerada em um dos eixos.")
        return max(scales) / smallest


CalibrationTransform = SimilarityTransform | AffineTransform


def _line_direction(start: Point2D | PixelPoint, end: Point2D | PixelPoint) -> tuple[float, float]:
    return end.x - start.x, end.y - start.y


def _cross(first: tuple[float, float], second: tuple[float, float]) -> float:
    return first[0] * second[1] - first[1] * second[0]


def _length(vector: tuple[float, float]) -> float:
    return math.hypot(*vector)


def _proposal_by_id(proposals: VisionProposalSet, proposal_id: str) -> VisionProposal:
    for proposal in proposals.proposals:
        if proposal.id == proposal_id:
            return proposal
    raise CalibrationError("Proposta de calibração não encontrada no snapshot.")


def _solve_linear_system(matrix: list[list[float]], vector: list[float]) -> list[float]:
    """Eliminação de Gauss para a matriz normal 4x4, sem dependência numérica extra."""
    size = len(vector)
    augmented = [[*row[:], value] for row, value in zip(matrix, vector, strict=True)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) < 1e-12:
            raise CalibrationError("Anchors não determinam uma transformação de similaridade.")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        factor = augmented[column][column]
        augmented[column] = [value / factor for value in augmented[column]]
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            augmented[row] = [
                value - factor * pivot_value
                for value, pivot_value in zip(augmented[row], augmented[column], strict=True)
            ]
    return [augmented[row][-1] for row in range(size)]


def _anchor_pairs(
    proposals: VisionProposalSet,
    scene: SceneRevision,
    anchors: Iterable[CalibrationAnchor],
) -> list[tuple[PixelPoint, Point2D]]:
    anchor_list = list(anchors)
    if len(anchor_list) != 2 or len({anchor.proposal_id for anchor in anchor_list}) != 2:
        raise CalibrationError("A calibração requer exatamente duas propostas de linha distintas.")
    if len({anchor.entity_id for anchor in anchor_list}) != 2:
        raise CalibrationError("A calibração requer exatamente duas entidades de linha distintas.")

    entities = {entity.id: entity for entity in scene.entities}
    pairs: list[tuple[PixelPoint, Point2D]] = []
    source_directions: list[tuple[float, float]] = []
    target_directions: list[tuple[float, float]] = []
    for anchor in anchor_list:
        proposal = _proposal_by_id(proposals, anchor.proposal_id)
        entity = entities.get(anchor.entity_id) if anchor.entity_id is not None else None
        if not isinstance(proposal.geometry, PixelLine) or proposal.kind != "line":
            raise CalibrationError("Somente propostas de linha podem servir de anchor.")
        if entity is None or entity.precision not in {Precision.EXACT, Precision.DERIVED}:
            raise CalibrationError("Anchor deve apontar para entidade exact ou derived existente.")
        if not isinstance(entity.geometry, LineGeometry):
            raise CalibrationError("Anchor deve apontar para uma entidade de linha.")
        target_start, target_end = (
            (entity.geometry.end, entity.geometry.start)
            if anchor.reversed
            else (entity.geometry.start, entity.geometry.end)
        )
        source_direction = _line_direction(proposal.geometry.start, proposal.geometry.end)
        target_direction = _line_direction(target_start, target_end)
        if _length(source_direction) < 1e-9 or _length(target_direction) < 1e-9:
            raise CalibrationError("Anchors degenerados não são permitidos.")
        source_directions.append(source_direction)
        target_directions.append(target_direction)
        pairs.extend([(proposal.geometry.start, target_start), (proposal.geometry.end, target_end)])

    if abs(_cross(*source_directions)) < 1e-9 or abs(_cross(*target_directions)) < 1e-9:
        raise CalibrationError("Anchors paralelos não determinam uma calibração verificável.")
    return pairs


def calibrate_similarity(
    proposals: VisionProposalSet,
    scene: SceneRevision,
    anchors: Iterable[CalibrationAnchor],
) -> SimilarityTransform:
    pairs = _anchor_pairs(proposals, scene, anchors)

    normal = [[0.0 for _ in range(4)] for _ in range(4)]
    right = [0.0 for _ in range(4)]
    for source, target in pairs:
        rows = (
            ([source.x, -source.y, 1.0, 0.0], target.x),
            ([source.y, source.x, 0.0, 1.0], target.y),
        )
        for coefficients, expected in rows:
            for row in range(4):
                right[row] += coefficients[row] * expected
                for column in range(4):
                    normal[row][column] += coefficients[row] * coefficients[column]
    a, b, tx, ty = _solve_linear_system(normal, right)
    if not all(math.isfinite(value) for value in (a, b, tx, ty)) or math.hypot(a, b) < 1e-9:
        raise CalibrationError("Transformação de calibração inválida.")
    transform = SimilarityTransform(a=a, b=b, tx=tx, ty=ty, rmse_m=0.0)
    squared_error = sum(
        (transform.point(source).x - target.x) ** 2 + (transform.point(source).y - target.y) ** 2
        for source, target in pairs
    )
    return SimilarityTransform(a=a, b=b, tx=tx, ty=ty, rmse_m=math.sqrt(squared_error / len(pairs)))


def calibrate_affine(
    proposals: VisionProposalSet,
    scene: SceneRevision,
    anchors: Iterable[CalibrationAnchor],
) -> AffineTransform:
    """Ajusta escala por eixo, rotação e translação; cada eixo métrico é independente."""
    pairs = _anchor_pairs(proposals, scene, anchors)

    solved: list[list[float]] = []
    for axis in (0, 1):
        normal = [[0.0 for _ in range(3)] for _ in range(3)]
        right = [0.0 for _ in range(3)]
        for source, target in pairs:
            coefficients = [source.x, source.y, 1.0]
            expected = target.x if axis == 0 else target.y
            for row in range(3):
                right[row] += coefficients[row] * expected
                for column in range(3):
                    normal[row][column] += coefficients[row] * coefficients[column]
        solved.append(_solve_linear_system(normal, right))
    (m11, m12, tx), (m21, m22, ty) = solved
    if not all(math.isfinite(value) for value in (m11, m12, m21, m22, tx, ty)):
        raise CalibrationError("Transformação afim inválida.")
    if abs(m11 * m22 - m12 * m21) < 1e-12:
        raise CalibrationError("Transformação afim degenerada: os eixos colapsam.")
    transform = AffineTransform(m11=m11, m12=m12, m21=m21, m22=m22, tx=tx, ty=ty, rmse_m=0.0)
    squared_error = sum(
        (transform.point(source).x - target.x) ** 2 + (transform.point(source).y - target.y) ** 2
        for source, target in pairs
    )
    return AffineTransform(
        m11=m11,
        m12=m12,
        m21=m21,
        m22=m22,
        tx=tx,
        ty=ty,
        rmse_m=math.sqrt(squared_error / len(pairs)),
    )


def resolve_calibration(
    proposals: VisionProposalSet,
    scene: SceneRevision,
    anchors: Iterable[CalibrationAnchor],
    *,
    mode: str = "affine",
) -> tuple[CalibrationTransform, list[CalibrationAnchor]]:
    """Descobre a que linha métrica, e em que sentido, cada proposta corresponde.

    Escolher isso na tela é impossível: as quatro arestas de um retângulo têm o mesmo
    rótulo e o mesmo comprimento. E errar não falha — a transformação afim absorve o
    engano como cisalhamento e devolve um traçado plausível. Então o ajuste decide, e o
    resultado só vale se reproduzir as próprias âncoras dentro da tolerância.
    """
    anchor_list = list(anchors)
    fit = calibrate_affine if mode == "affine" else calibrate_similarity
    usable = [
        entity.id
        for entity in scene.entities
        if isinstance(entity.geometry, LineGeometry)
        and entity.precision in {Precision.EXACT, Precision.DERIVED}
    ]
    options = [
        [anchor.entity_id] if anchor.entity_id is not None else usable for anchor in anchor_list
    ]
    best: tuple[CalibrationTransform, list[CalibrationAnchor]] | None = None
    for entity_ids in product(*options):
        if len(set(entity_ids)) != len(entity_ids):
            continue
        for flags in product((False, True), repeat=len(anchor_list)):
            candidate = [
                replace(anchor, entity_id=entity_id, reversed=flag)
                for anchor, entity_id, flag in zip(anchor_list, entity_ids, flags, strict=True)
            ]
            try:
                transform = fit(proposals, scene, candidate)
            except CalibrationError:
                continue
            if best is None or transform.rmse_m < best[0].rmse_m:
                best = (transform, candidate)
    if best is None:
        raise CalibrationError("Nenhuma combinação de anchors produz uma calibração válida.")
    if best[0].rmse_m > CALIBRATION_MAX_RMSE_M:
        raise CalibrationError(
            f"A calibração não reproduz as próprias âncoras: erro de {best[0].rmse_m:.2f} m "
            f"contra o limite de {CALIBRATION_MAX_RMSE_M:.2f} m. "
            "As duas linhas escolhidas provavelmente não são arestas da cena métrica."
        )
    return best


def approximate_entity_from_proposal(
    proposal: VisionProposal,
    transform: CalibrationTransform,
    *,
    calibration_id: UUID,
    review_id: UUID,
) -> Entity:
    geometry = proposal.geometry
    provenance = Provenance(
        source_type=HUMAN_ACCEPTED_PROPOSAL_SOURCE_TYPE,
        source_ids=[proposal.id, str(calibration_id), str(review_id)],
        summary_code="HUMAN_SELECTED_PIXEL_PROPOSAL",
    )
    if isinstance(geometry, PixelLine):
        return Entity(
            kind=EntityKind.LINE,
            layer=LayerName.APROXIMADO,
            precision=Precision.APPROXIMATE,
            geometry=LineGeometry(
                start=transform.point(geometry.start), end=transform.point(geometry.end)
            ),
            provenance=provenance,
        )
    if isinstance(geometry, PixelCircle):
        if transform.anisotropy > ISOTROPY_TOLERANCE:
            # Escalas de eixo diferentes levam o círculo a uma elipse, e o scene graph
            # não tem elipse. Amostrar é honesto; manter círculo com raio médio não é.
            return Entity(
                kind=EntityKind.POLYLINE,
                layer=LayerName.APROXIMADO,
                precision=Precision.APPROXIMATE,
                geometry=PolylineGeometry(
                    points=[
                        transform.point(
                            PixelPoint(
                                x=geometry.center.x
                                + geometry.radius * math.cos(step * math.tau / ELLIPSE_SEGMENTS),
                                y=geometry.center.y
                                + geometry.radius * math.sin(step * math.tau / ELLIPSE_SEGMENTS),
                            )
                        )
                        for step in range(ELLIPSE_SEGMENTS)
                    ],
                    closed=True,
                ),
                provenance=provenance,
            )
        center = transform.point(geometry.center)
        radius = geometry.radius * transform.scale_x_m_per_px
        if not math.isfinite(radius) or radius <= 0:
            raise CalibrationError("Raio transformado inválido.")
        return Entity(
            kind=EntityKind.CIRCLE,
            layer=LayerName.APROXIMADO,
            precision=Precision.APPROXIMATE,
            geometry=CircleGeometry(center=center, radius=radius),
            provenance=provenance,
        )
    if isinstance(geometry, PixelPolyline):
        return Entity(
            kind=EntityKind.POLYLINE,
            layer=LayerName.APROXIMADO,
            precision=Precision.APPROXIMATE,
            geometry=PolylineGeometry(
                points=[transform.point(point) for point in geometry.points],
                # Fechar à força transformaria um muro aberto num polígono que ninguém
                # desenhou — e o auditor exige área positiva em polilinha fechada.
                closed=geometry.closed,
            ),
            provenance=provenance,
        )
    raise CalibrationError("Tipo de proposta não suportado.")


def matrix_of(transform: CalibrationTransform) -> tuple[float, float, float, float, float, float]:
    """Representação canônica (m11, m12, m21, m22, tx, ty), comum aos dois modos."""
    if isinstance(transform, AffineTransform):
        return (
            transform.m11,
            transform.m12,
            transform.m21,
            transform.m22,
            transform.tx,
            transform.ty,
        )
    return (transform.a, -transform.b, transform.b, transform.a, transform.tx, transform.ty)


def transform_from_calibration_json(calibration_json: dict[str, Any]) -> CalibrationTransform:
    """Reconstrói a transformação gravada, aceitando o formato anterior à matriz.

    Opera sobre o dicionário já persistido (``calibration_json``) em vez do modelo de
    resposta da API, para que API e worker revalidem a mesma calibração com a mesma regra.
    """
    matrix = calibration_json.get("matrix")
    if matrix is None:
        return SimilarityTransform(
            a=calibration_json["scale_m_per_px"] * math.cos(calibration_json["rotation_radians"]),
            b=calibration_json["scale_m_per_px"] * math.sin(calibration_json["rotation_radians"]),
            tx=calibration_json["translation_m"][0],
            ty=calibration_json["translation_m"][1],
            rmse_m=calibration_json["rmse_m"],
        )
    m11, m12, m21, m22, tx, ty = matrix
    if calibration_json.get("mode", "similarity") == "similarity":
        return SimilarityTransform(a=m11, b=m21, tx=tx, ty=ty, rmse_m=calibration_json["rmse_m"])
    return AffineTransform(
        m11=m11, m12=m12, m21=m21, m22=m22, tx=tx, ty=ty, rmse_m=calibration_json["rmse_m"]
    )


def revalidate_calibration(
    calibration_json: dict[str, Any] | None,
    *,
    proposals_json: dict[str, Any] | None,
    scene: SceneRevision,
    scene_record_id: str,
) -> dict[str, Any] | None:
    """Re-solves the stored transform against a new scene; returns None when it no longer holds.

    A drifting or unsolvable calibration never rewrites accepted geometry: the caller raises a
    critical issue instead, so the professional recalibrates before anything can be exported.

    Shared by the API's decision endpoints and the worker's `refresh-proposals` command so both
    apply the exact same drift rule against the exact same tolerance.
    """
    if calibration_json is None or proposals_json is None:
        return None
    mode = calibration_json.get("mode", "similarity")
    anchors = [
        CalibrationAnchor(
            proposal_id=anchor["proposal_id"],
            entity_id=UUID(anchor["entity_id"]) if anchor.get("entity_id") else None,
            reversed=anchor.get("reversed", False),
        )
        for anchor in calibration_json["anchors"]
    ]
    calibrate = calibrate_affine if mode == "affine" else calibrate_similarity
    try:
        transform = calibrate(VisionProposalSet.model_validate(proposals_json), scene, anchors)
    except CalibrationError:
        return None
    # Comparar a matriz cobre os dois modos; escala e rotação isoladas não descrevem
    # uma transformação com escala por eixo. Calibração legada é reconstruída a partir
    # dos campos antigos, então continua sujeita ao mesmo teste de deriva.
    stored_matrix = matrix_of(transform_from_calibration_json(calibration_json))
    if any(
        abs(current - previous) > CALIBRATION_DRIFT_TOLERANCE_M
        for current, previous in zip(matrix_of(transform), stored_matrix, strict=True)
    ):
        return None
    return {
        **calibration_json,
        "scene_revision_id": str(UUID(scene_record_id)),
        "scene_version": scene.version,
    }
