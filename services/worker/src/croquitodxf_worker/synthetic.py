"""Fixture sintética reprodutível, sem conteúdo de cliente."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from PIL import Image, ImageDraw, ImageFont

from croquitodxf_core.models import (
    CircleGeometry,
    Constraint,
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

FIELD_WIDTH = 31.95
FIELD_HEIGHT = 25.90
CENTRE_CIRCLE_RADIUS = 3.0

# Arco de tinta do render, em pixels da folha sintética. Vive em pixels porque só o render
# o desenha — ele não entra na cena aprovada, e inventar uma medida em metros para ele
# sugeriria uma cota que ninguém escreveu. A fixture de geometria em `providers.py` deriva
# as coordenadas normalizadas destes valores; sem tinta por baixo, a conferência rebaixaria
# o elemento com INK_NOT_FOUND e a fixture provaria o contrário do que se propõe a provar.
ARC_CENTRE_PX = (390, 700)
ARC_RADIUS_PX = 120
ARC_START_DEGREES = 180
ARC_END_DEGREES = 360
"""Meia-lua aberta para baixo: a varredura 180°→360° do PIL sobe pelo lado de cima."""


def _id(suffix: int) -> UUID:
    return UUID(f"01900000-0000-7000-8000-{suffix:012d}")


def _synthetic_provenance(code: str, source_id: str) -> Provenance:
    return Provenance(
        source_type="synthetic_fixture",
        source_ids=[source_id],
        summary_code=code,
    )


def build_synthetic_scene() -> SceneRevision:
    """Cria uma quadra fictícia com medidas exatas e proveniência controlada."""
    source = _synthetic_provenance("SYNTHETIC_SPEC", "fixture:campo-retangular:v1")
    derived = _synthetic_provenance("DERIVED_FROM_SPEC", "fixture:campo-retangular:v1")
    top_id, right_id, bottom_id, left_id = (_id(1), _id(2), _id(3), _id(4))
    entities = [
        Entity(
            id=top_id,
            kind=EntityKind.LINE,
            layer=LayerName.CAMPO,
            precision=Precision.EXACT,
            geometry=LineGeometry(
                start=Point2D(x=0, y=FIELD_HEIGHT), end=Point2D(x=FIELD_WIDTH, y=FIELD_HEIGHT)
            ),
            provenance=source,
        ),
        Entity(
            id=right_id,
            kind=EntityKind.LINE,
            layer=LayerName.CAMPO,
            precision=Precision.EXACT,
            geometry=LineGeometry(
                start=Point2D(x=FIELD_WIDTH, y=FIELD_HEIGHT), end=Point2D(x=FIELD_WIDTH, y=0)
            ),
            provenance=source,
        ),
        Entity(
            id=bottom_id,
            kind=EntityKind.LINE,
            layer=LayerName.CAMPO,
            precision=Precision.EXACT,
            geometry=LineGeometry(start=Point2D(x=FIELD_WIDTH, y=0), end=Point2D(x=0, y=0)),
            provenance=source,
        ),
        Entity(
            id=left_id,
            kind=EntityKind.LINE,
            layer=LayerName.CAMPO,
            precision=Precision.EXACT,
            geometry=LineGeometry(start=Point2D(x=0, y=0), end=Point2D(x=0, y=FIELD_HEIGHT)),
            provenance=source,
        ),
        Entity(
            id=_id(5),
            kind=EntityKind.LINE,
            layer=LayerName.DETALHES,
            precision=Precision.DERIVED,
            geometry=LineGeometry(
                start=Point2D(x=FIELD_WIDTH / 2, y=0),
                end=Point2D(x=FIELD_WIDTH / 2, y=FIELD_HEIGHT),
            ),
            provenance=derived,
        ),
        Entity(
            id=_id(6),
            kind=EntityKind.CIRCLE,
            layer=LayerName.DETALHES,
            precision=Precision.EXACT,
            geometry=CircleGeometry(
                center=Point2D(x=FIELD_WIDTH / 2, y=FIELD_HEIGHT / 2),
                radius=CENTRE_CIRCLE_RADIUS,
            ),
            provenance=source,
        ),
        Entity(
            id=_id(7),
            kind=EntityKind.TEXT,
            layer=LayerName.TEXTOS,
            precision=Precision.DERIVED,
            geometry=TextGeometry(
                insertion=Point2D(x=11.25, y=12.4),
                text="FIXTURE SINTETICA",
                height=0.7,
            ),
            provenance=derived,
        ),
        Entity(
            id=_id(8),
            kind=EntityKind.DIMENSION,
            layer=LayerName.COTAS,
            precision=Precision.EXACT,
            geometry=DimensionGeometry(
                first=Point2D(x=0, y=FIELD_HEIGHT),
                second=Point2D(x=FIELD_WIDTH, y=FIELD_HEIGHT),
                base=Point2D(x=0, y=FIELD_HEIGHT + 2.0),
                text_override="31.95 m",
            ),
            provenance=source,
        ),
        Entity(
            id=_id(9),
            kind=EntityKind.DIMENSION,
            layer=LayerName.COTAS,
            precision=Precision.EXACT,
            geometry=DimensionGeometry(
                first=Point2D(x=0, y=0),
                second=Point2D(x=0, y=FIELD_HEIGHT),
                base=Point2D(x=-2.0, y=0),
                text_override="25.90 m",
            ),
            provenance=source,
        ),
    ]
    measurements = [
        Measurement(
            id=_id(101),
            entity_id=top_id,
            kind=MeasurementKind.WIDTH,
            raw_text="31,95 m",
            value_si=Decimal("31.95"),
            unit=UnitCode.METRE,
            written_decimals=2,
            confirmed=True,
            provenance=source,
        ),
        Measurement(
            id=_id(102),
            entity_id=left_id,
            kind=MeasurementKind.HEIGHT,
            raw_text="25,90 m",
            value_si=Decimal("25.90"),
            unit=UnitCode.METRE,
            written_decimals=2,
            confirmed=True,
            provenance=source,
        ),
        Measurement(
            id=_id(103),
            entity_id=_id(6),
            kind=MeasurementKind.RADIUS,
            raw_text="R=3,00 m",
            value_si=Decimal("3.00"),
            unit=UnitCode.METRE,
            written_decimals=2,
            confirmed=True,
            provenance=source,
        ),
    ]
    return SceneRevision(
        id=_id(200),
        job_id=_id(201),
        version=1,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        approved=True,
        entities=entities,
        measurements=measurements,
        constraints=[
            Constraint(
                id=_id(301),
                kind="orthogonal_rectangle",
                entity_ids=[top_id, right_id, bottom_id, left_id],
                tolerance=1e-9,
                hard=True,
                satisfied=True,
            )
        ],
    )


def render_synthetic_input(path: Path) -> None:
    """Renderiza uma entrada raster que simula uma folha simples digitalizada."""
    width, height = 1400, 1050
    image = Image.new("RGB", (width, height), "#f5f1e8")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=22)
    small_font = ImageFont.load_default(size=18)
    margin_x, margin_y = 170, 150
    scale = 30
    field_w = int(FIELD_WIDTH * scale)
    field_h = int(FIELD_HEIGHT * scale)
    left = margin_x
    top = margin_y
    right = left + field_w
    bottom = top + field_h
    draw.rectangle((left, top, right, bottom), outline="#243447", width=5)
    middle_x = (left + right) // 2
    middle_y = (top + bottom) // 2
    draw.line((middle_x, top, middle_x, bottom), fill="#596a7a", width=3)
    radius = int(CENTRE_CIRCLE_RADIUS * scale)
    draw.ellipse(
        (middle_x - radius, middle_y - radius, middle_x + radius, middle_y + radius),
        outline="#243447",
        width=4,
    )
    draw.arc(
        (
            ARC_CENTRE_PX[0] - ARC_RADIUS_PX,
            ARC_CENTRE_PX[1] - ARC_RADIUS_PX,
            ARC_CENTRE_PX[0] + ARC_RADIUS_PX,
            ARC_CENTRE_PX[1] + ARC_RADIUS_PX,
        ),
        ARC_START_DEGREES,
        ARC_END_DEGREES,
        fill="#243447",
        width=4,
    )
    draw.text((left + 340, middle_y - 12), "FIXTURE SINTETICA", fill="#243447", font=font)
    draw.line((left, top - 45, right, top - 45), fill="#9b2c2c", width=2)
    draw.text((middle_x - 55, top - 80), "31,95 m", fill="#9b2c2c", font=small_font)
    draw.line((left - 45, top, left - 45, bottom), fill="#9b2c2c", width=2)
    draw.text((left - 145, middle_y), "25,90 m", fill="#9b2c2c", font=small_font)
    draw.text(
        (40, 35),
        "CROQUITODXF - DADO SINTETICO, SEM CONTEUDO DE CLIENTE",
        fill="#4a5568",
        font=font,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG", optimize=True)
