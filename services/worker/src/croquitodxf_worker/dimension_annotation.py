"""Liga uma cota confirmada a uma linha traçada, fazendo a cota prevalecer.

O croqui está fora de escala e a geometria traçada vem de pixels. Quando o profissional
declara que uma linha traçada é a cota escrita, o comprimento passa a valer o que está
escrito — direção e posição continuam vindo do traçado. É a regra do projeto: cota e
constraint têm precedência sobre pixel.
"""

from __future__ import annotations

import math
from decimal import Decimal
from uuid import UUID

from croquitodxf_core.models import (
    DimensionGeometry,
    Entity,
    EntityKind,
    LayerName,
    LineGeometry,
    Measurement,
    MeasurementKind,
    Point2D,
    Precision,
    Provenance,
    SceneRevision,
    TextGeometry,
    UnitCode,
)

DIMENSION_SOURCE_TYPE = "human_confirmed_reading+traced_line"
"""Provenance de uma cota amarrada a geometria aproximada."""

NOTE_SOURCE_TYPE = "human_confirmed_reading+note"
"""Provenance de uma anotação de texto presa a um elemento."""

MIN_DIMENSION_OFFSET_M = 1.0
"""Afastamento mínimo da linha de cota, em metros."""


class DimensionAnnotationError(ValueError):
    """A leitura ou a entidade não permitem amarrar uma cota."""


NOTE_TEXT_HEIGHT_M = 0.5
"""Altura do texto de anotação, em metros: legível num campo de dezenas de metros."""


def _offset(length: float) -> float:
    return max(MIN_DIMENSION_OFFSET_M, length * 0.06)


def annotate_note(
    scene: SceneRevision,
    *,
    entity_id: UUID,
    layer: LayerName,
    text: str,
    reading_id: str,
    decision_id: str,
) -> Entity:
    """Prende uma anotação de texto ao elemento a que ela se refere.

    Altura de muro, vão de portão e especificação de trave não existem em planta: em
    desenho técnico elas são anotadas, não desenhadas. O texto é o que está escrito na
    folha, confirmado por uma pessoa — por isso `exact`.
    """
    entity = next((item for item in scene.entities if item.id == entity_id), None)
    if entity is None:
        raise DimensionAnnotationError("A entidade da anotação não existe na cena.")
    if not isinstance(entity.geometry, LineGeometry):
        raise DimensionAnnotationError("Somente linha recebe anotação presa.")

    start, end = entity.geometry.start, entity.geometry.end
    length = math.hypot(end.x - start.x, end.y - start.y)
    if length < 1e-9:
        raise DimensionAnnotationError("Linha degenerada não recebe anotação.")
    offset = _offset(length)
    rotation = math.atan2(end.y - start.y, end.x - start.x)
    # Normalizado para (-π/2, π/2]: anotação acompanha a linha, mas nunca de cabeça
    # para baixo — meio giro não muda a direção da linha, só a legibilidade do texto.
    if rotation > math.pi / 2:
        rotation -= math.pi
    elif rotation <= -math.pi / 2:
        rotation += math.pi
    return Entity(
        kind=EntityKind.TEXT,
        layer=layer,
        precision=Precision.EXACT,
        geometry=TextGeometry(
            insertion=Point2D(
                x=(start.x + end.x) / 2 - (end.y - start.y) / length * offset,
                y=(start.y + end.y) / 2 + (end.x - start.x) / length * offset,
            ),
            text=text,
            height=NOTE_TEXT_HEIGHT_M,
            # Radiano: o campo é interno e o `dxf.py` é quem converte para grau na escrita.
            rotation=rotation,
        ),
        provenance=Provenance(
            source_type=NOTE_SOURCE_TYPE,
            source_ids=[reading_id, decision_id, str(entity_id)],
            summary_code="CONFIRMED_READING_AS_NOTE",
        ),
    )


def annotate_traced_line(
    scene: SceneRevision,
    *,
    entity_id: UUID,
    reading_id: str,
    decision_id: str,
    value_si: Decimal,
    written_decimals: int,
    kind: MeasurementKind,
) -> tuple[Entity, Entity, Measurement]:
    """Devolve (linha ajustada, entidade de cota, medida confirmada).

    A linha é reescalada em torno do próprio ponto médio: reposicioná-la por uma das
    pontas moveria o desenho inteiro em relação ao que o profissional viu na tela.
    """
    entity = next((item for item in scene.entities if item.id == entity_id), None)
    if entity is None:
        raise DimensionAnnotationError("A entidade da cota não existe na cena.")
    if not isinstance(entity.geometry, LineGeometry):
        raise DimensionAnnotationError("Somente linha aceita cota amarrada.")
    if kind not in {MeasurementKind.LENGTH, MeasurementKind.WIDTH, MeasurementKind.HEIGHT}:
        raise DimensionAnnotationError("A cota amarrada aceita comprimento, largura ou altura.")
    if value_si <= 0:
        raise DimensionAnnotationError("A cota precisa ser positiva.")

    start, end = entity.geometry.start, entity.geometry.end
    traced_length = math.hypot(end.x - start.x, end.y - start.y)
    if traced_length < 1e-9:
        raise DimensionAnnotationError("Linha degenerada não recebe cota.")

    target = float(value_si)
    centre_x, centre_y = (start.x + end.x) / 2, (start.y + end.y) / 2
    ratio = target / traced_length / 2
    dx, dy = (end.x - start.x) * ratio, (end.y - start.y) * ratio
    adjusted_start = Point2D(x=centre_x - dx, y=centre_y - dy)
    adjusted_end = Point2D(x=centre_x + dx, y=centre_y + dy)

    provenance = Provenance(
        source_type=DIMENSION_SOURCE_TYPE,
        source_ids=[reading_id, decision_id, str(entity_id)],
        summary_code="CONFIRMED_READING_OVER_TRACED_LINE",
    )
    adjusted = entity.model_copy(
        update={
            "geometry": LineGeometry(start=adjusted_start, end=adjusted_end),
            "provenance": provenance,
        }
    )

    offset = _offset(target)
    normal_x, normal_y = -(dy / (target / 2)), dx / (target / 2)
    dimension = Entity(
        kind=EntityKind.DIMENSION,
        layer=LayerName.COTAS,
        # A cota é exact: o número vem da folha, confirmado por uma pessoa. A linha que
        # ela mede continua approximate, porque a posição ainda vem de pixels.
        precision=Precision.EXACT,
        geometry=DimensionGeometry(
            first=adjusted_start,
            second=adjusted_end,
            base=Point2D(
                x=adjusted_start.x + normal_x * offset,
                y=adjusted_start.y + normal_y * offset,
            ),
            text_override=f"{value_si} m",
        ),
        provenance=provenance,
    )
    measurement = Measurement(
        entity_id=adjusted.id,
        kind=kind,
        value_si=value_si,
        unit=UnitCode.METRE,
        written_decimals=written_decimals,
        confirmed=True,
        provenance=provenance,
    )
    return adjusted, dimension, measurement
