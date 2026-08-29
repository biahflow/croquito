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

#: Forma do `Entity.element_ref` (ADR-0058, decisão 1). Constante nomeada porque quem cunha
#: o ref é a API, do lado de fora deste pacote: repetir a regex lá faria as duas metades do
#: mesmo contrato — a que valida e a que cunha — poderem divergir em silêncio.
ELEMENT_REF_PATTERN: Final = r"^EL-\d{3,}$"

#: Prefixo do ref, separado do padrão para que quem lê o ordinal não o extraia por fatia
#: mágica (`ref[3:]`) espalhada por dois pacotes.
ELEMENT_REF_PREFIX: Final = "EL-"

#: Teto do rótulo legível do elemento (F-047 T2b). Nome de elemento é frase curta de croqui
#: ("Alambrado da quadra"), não descrição de serviço: o teto existe para que o campo não vire
#: depósito de texto que ninguém lê na etiqueta ao lado do `EL-00N`.
ELEMENT_LABEL_MAX_LENGTH: Final = 120

#: A chave do mapa de rótulos é um `element_ref`, com a mesma forma que a entidade carrega —
#: declarada aqui para que o contrato gerado a leve para o schema e para o TypeScript, em vez
#: de aceitar qualquer string como chave.
ElementRef = Annotated[str, Field(pattern=ELEMENT_REF_PATTERN)]

#: O rótulo em si. `min_length=1` com `str_strip_whitespace` do `ContractModel` é o que recusa
#: rótulo vazio ou só de espaço: "   " chega como "" à validação de tamanho.
ElementLabel = Annotated[str, Field(min_length=1, max_length=ELEMENT_LABEL_MAX_LENGTH)]


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
    # ADR-0058: identidade de elemento, ao lado do que a Entity já tem — nunca no lugar.
    # Não é `id` (identidade de linha, muda a cada revisão nova) nem `TextGeometry.text`
    # (a redação que o humano lê na prancha). É o elo estável que diz "este traço e aquele
    # balão são o mesmo elemento": cunhado pelo sistema no ato humano de declaração na
    # revisão, nunca digitado e nunca inferido por proximidade. Quem cunha é
    # `POST /v1/jobs/{job_id}/elements` (`croquito_api.main._next_element_ref`), sequencial
    # dentro do job; aqui ficam só a forma e a invariante mínima.
    element_ref: str | None = Field(default=None, pattern=ELEMENT_REF_PATTERN)

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
    # F-047 T2b: o nome legível do elemento, por `element_ref` e nunca por entidade — repetir
    # a mesma string em cada traço criaria duas verdades sobre o mesmo nome. É APRESENTAÇÃO:
    # o que casa cena↔legenda continua sendo só o `element_ref` (ADR-0058, decisão 2), e nada
    # em lugar nenhum pode passar a casar por este campo, que é texto livre. Também não
    # substitui `TextGeometry.text`, que é a redação escrita na prancha.
    element_labels: dict[ElementRef, ElementLabel] = Field(default_factory=dict)

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
        # ADR-0058: element_ref identifica UM elemento, nunca um agrupamento arbitrário.
        # A invariante mínima e defensável que esta tarefa implementa: entidades que
        # compartilham element_ref têm de compartilhar layer. Não prova que o grupo é
        # coerente (isso é ato humano, T2), mas recusa cedo o caso claramente errado —
        # misturar camadas sob o mesmo ref — em vez de deixá-lo virar quantidade errada
        # silenciosamente mais adiante na cadeia elemento → legenda → serviços.
        layers_by_ref: dict[str, set[LayerName]] = {}
        for entity in self.entities:
            if entity.element_ref is None:
                continue
            layers_by_ref.setdefault(entity.element_ref, set()).add(entity.layer)
        mismatched_refs = {ref for ref, layers in layers_by_ref.items() if len(layers) > 1}
        if mismatched_refs:
            raise ValueError(
                "ELEMENT_REF_LAYER_MISMATCH: element_ref compartilhado entre camadas "
                f"diferentes: {sorted(mismatched_refs)}"
            )
        # F-047 T2b: rótulo é nome DE elemento — sem elemento, não é nome de nada. Um rótulo
        # órfão sobreviveria a uma revogação e reapareceria colado no elemento seguinte que
        # cunhasse aquele ref, e nomear a coisa errada é pior do que não nomear.
        orphan_labels = sorted(set(self.element_labels) - set(layers_by_ref))
        if orphan_labels:
            raise ValueError(
                "ELEMENT_LABEL_UNKNOWN_REF: rótulo declarado para element_ref que nenhuma "
                f"entidade usa: {orphan_labels}"
            )
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
