"""Cena canônica independente de provedor e de formato CAD."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Final, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from croquito_core.errors import DomainValidationError
from croquito_core.ids import new_uuid7

SCENE_SCHEMA_VERSION: Final = "1.0.0"


class ContractModel(BaseModel):
    """Configuração comum para contratos persistidos ou trocados pela API."""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
        allow_inf_nan=False,
    )


class Precision(StrEnum):
    EXACT = "exact"
    DERIVED = "derived"
    APPROXIMATE = "approximate"
    UNRESOLVED = "unresolved"


class EntityKind(StrEnum):
    LINE = "line"
    POLYLINE = "polyline"
    CIRCLE = "circle"
    ARC = "arc"
    SPLINE = "spline"
    TEXT = "text"
    DIMENSION = "dimension"
    DIAMETER_DIMENSION = "diameter_dimension"


class LayerName(StrEnum):
    CONTORNO = "CONTORNO"
    CAMPO = "CAMPO"
    QUADRA = "QUADRA"
    MURO = "MURO"
    ALAMBRADO = "ALAMBRADO"
    PORTAO = "PORTAO"
    PATAMAR = "PATAMAR"
    EQUIPAMENTOS = "EQUIPAMENTOS"
    COTAS = "COTAS"
    TEXTOS = "TEXTOS"
    DETALHES = "DETALHES"
    APROXIMADO = "APROXIMADO"
    REVISAO = "REVISAO"


class MeasurementKind(StrEnum):
    LENGTH = "length"
    WIDTH = "width"
    HEIGHT = "height"
    RADIUS = "radius"
    DIAMETER = "diameter"
    ANGLE = "angle"
    AREA = "area"


class UnitCode(StrEnum):
    METRE = "m"
    MILLIMETRE = "mm"
    RADIAN = "rad"
    DEGREE = "deg"
    SQUARE_METRE = "m2"


class IssueSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class IssueStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    ACCEPTED = "accepted"


class Point2D(ContractModel):
    x: float
    y: float


class LineGeometry(ContractModel):
    type: Literal["line"] = "line"
    start: Point2D
    end: Point2D


class PolylineGeometry(ContractModel):
    type: Literal["polyline"] = "polyline"
    points: list[Point2D] = Field(min_length=2)
    closed: bool = False


class CircleGeometry(ContractModel):
    type: Literal["circle"] = "circle"
    center: Point2D
    radius: float = Field(gt=0)


class ArcGeometry(ContractModel):
    type: Literal["arc"] = "arc"
    center: Point2D
    radius: float = Field(gt=0)
    start_angle: float
    end_angle: float


class SplineGeometry(ContractModel):
    type: Literal["spline"] = "spline"
    fit_points: list[Point2D] = Field(min_length=3)


class TextGeometry(ContractModel):
    type: Literal["text"] = "text"
    insertion: Point2D
    text: str = Field(min_length=1, max_length=500)
    height: float = Field(gt=0)
    rotation: float = 0.0


class DimensionGeometry(ContractModel):
    type: Literal["dimension"] = "dimension"
    first: Point2D
    second: Point2D
    base: Point2D
    text_override: str | None = Field(default=None, max_length=100)


class DiameterDimensionGeometry(ContractModel):
    """Cota diametral (⌀) de um círculo, desenhada como DIMENSION diametral no CAD."""

    type: Literal["diameter_dimension"] = "diameter_dimension"
    center: Point2D
    radius: float = Field(gt=0)
    # Ângulo em radianos (convenção do repo) do raio onde a linha de cota atravessa o
    # círculo: mira a evidência da leitura na folha.
    angle: float
    text_override: str | None = Field(default=None, max_length=100)


Geometry = Annotated[
    LineGeometry
    | PolylineGeometry
    | CircleGeometry
    | ArcGeometry
    | SplineGeometry
    | TextGeometry
    | DimensionGeometry
    | DiameterDimensionGeometry,
    Field(discriminator="type"),
]


class Provenance(ContractModel):
    source_type: str = Field(min_length=1, max_length=80)
    source_ids: list[str] = Field(min_length=1, max_length=20)
    summary_code: str = Field(pattern=r"^[A-Z0-9_]{3,64}$")


class Entity(ContractModel):
    id: UUID = Field(default_factory=new_uuid7)
    kind: EntityKind
    layer: LayerName
    precision: Precision
    geometry: Geometry
    provenance: Provenance | None = None
    export: bool = True
    # Preenchimento declarado da região (ex.: a folha marca hachura na área vegetativa).
    # É apresentação rastreável, não geometria nova: o contorno continua sendo a entidade.
    fill: Literal["none", "hatch"] = "none"

    @model_validator(mode="after")
    def validate_kind_and_provenance(self) -> Entity:
        if self.kind.value != self.geometry.type:
            raise ValueError("kind deve corresponder ao discriminador geometry.type")
        if self.precision is Precision.EXACT and self.provenance is None:
            raise ValueError("entidade exact exige provenance")
        if self.fill != "none":
            closed_region = isinstance(self.geometry, CircleGeometry) or (
                isinstance(self.geometry, PolylineGeometry) and self.geometry.closed
            )
            if not closed_region:
                raise ValueError("fill exige região fechada (polilinha fechada ou círculo)")
        return self


class Measurement(ContractModel):
    id: UUID = Field(default_factory=new_uuid7)
    entity_id: UUID
    kind: MeasurementKind
    raw_text: str | None = Field(default=None, max_length=100)
    value_si: Decimal | None = None
    unit: UnitCode
    written_decimals: int = Field(default=2, ge=0, le=8)
    confirmed: bool = False
    provenance: Provenance | None = None

    @model_validator(mode="after")
    def validate_confirmation(self) -> Measurement:
        if self.confirmed and (self.value_si is None or self.provenance is None):
            raise ValueError("medida confirmada exige valor e provenance")
        return self


class Constraint(ContractModel):
    id: UUID = Field(default_factory=new_uuid7)
    kind: str = Field(min_length=1, max_length=80)
    entity_ids: list[UUID] = Field(min_length=1)
    tolerance: float = Field(ge=0)
    hard: bool = False
    satisfied: bool | None = None


class Issue(ContractModel):
    id: UUID = Field(default_factory=new_uuid7)
    code: str = Field(pattern=r"^[A-Z0-9_]{3,64}$")
    severity: IssueSeverity
    status: IssueStatus = IssueStatus.OPEN
    message: str = Field(min_length=1, max_length=500)
    entity_ids: list[UUID] = Field(default_factory=list)


def _measured_value(entity: Entity, kind: MeasurementKind) -> Decimal | None:
    geometry = entity.geometry
    if isinstance(geometry, LineGeometry) and kind in {
        MeasurementKind.LENGTH,
        MeasurementKind.WIDTH,
        MeasurementKind.HEIGHT,
    }:
        value = math.hypot(
            geometry.end.x - geometry.start.x,
            geometry.end.y - geometry.start.y,
        )
        return Decimal(str(value))
    if isinstance(geometry, CircleGeometry):
        if kind is MeasurementKind.RADIUS:
            return Decimal(str(geometry.radius))
        if kind is MeasurementKind.DIAMETER:
            return Decimal(str(geometry.radius * 2))
    if isinstance(geometry, ArcGeometry) and kind is MeasurementKind.RADIUS:
        return Decimal(str(geometry.radius))
    return None


class SceneRevision(ContractModel):
    schema_version: Literal["1.0.0"] = SCENE_SCHEMA_VERSION
    id: UUID = Field(default_factory=new_uuid7)
    job_id: UUID
    version: int = Field(ge=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    approved: bool = False
    accepted_approximation_ids: set[UUID] = Field(default_factory=set)
    entities: list[Entity]
    measurements: list[Measurement] = Field(default_factory=list)
    constraints: list[Constraint] = Field(default_factory=list)
    issues: list[Issue] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_references(self) -> SceneRevision:
        entity_ids = [entity.id for entity in self.entities]
        if len(entity_ids) != len(set(entity_ids)):
            raise ValueError("IDs de entidades devem ser únicos")
        known_ids = set(entity_ids)
        referenced_ids = {measurement.entity_id for measurement in self.measurements}
        referenced_ids.update(
            entity_id for constraint in self.constraints for entity_id in constraint.entity_ids
        )
        referenced_ids.update(entity_id for issue in self.issues for entity_id in issue.entity_ids)
        unknown_ids = referenced_ids - known_ids
        if unknown_ids:
            raise ValueError(f"referências apontam para entidades inexistentes: {unknown_ids}")
        if not self.accepted_approximation_ids <= known_ids:
            raise ValueError("accepted_approximation_ids contém entidade inexistente")
        return self

    def export_errors(self) -> list[str]:
        """Retorna violações que impedem a publicação de um pacote CAD."""
        errors: list[str] = []
        if not self.approved:
            errors.append("SCENE_NOT_APPROVED")

        entity_by_id = {entity.id: entity for entity in self.entities}
        for entity in self.entities:
            if not entity.export:
                continue
            if entity.precision is Precision.UNRESOLVED:
                errors.append(f"UNRESOLVED_ENTITY:{entity.id}")
            if (
                entity.precision is Precision.APPROXIMATE
                and entity.id not in self.accepted_approximation_ids
            ):
                errors.append(f"APPROXIMATION_NOT_ACCEPTED:{entity.id}")
            if entity.precision is Precision.EXACT and entity.provenance is None:
                errors.append(f"EXACT_WITHOUT_PROVENANCE:{entity.id}")

        for issue in self.issues:
            if issue.severity is IssueSeverity.CRITICAL and issue.status is IssueStatus.OPEN:
                errors.append(f"OPEN_CRITICAL_ISSUE:{issue.code}")

        for measurement in self.measurements:
            if not measurement.confirmed or measurement.value_si is None:
                continue
            measured = _measured_value(entity_by_id[measurement.entity_id], measurement.kind)
            if measured is None:
                continue
            written_tolerance = Decimal(1).scaleb(-measurement.written_decimals) / 2
            if measurement.unit is UnitCode.MILLIMETRE:
                written_tolerance *= Decimal("0.001")
            tolerance = max(Decimal("0.000001"), written_tolerance)
            if abs(measured - measurement.value_si) > tolerance:
                errors.append(f"MEASUREMENT_MISMATCH:{measurement.id}")
        return errors

    def ensure_exportable(self) -> None:
        errors = self.export_errors()
        if errors:
            raise DomainValidationError(errors)
