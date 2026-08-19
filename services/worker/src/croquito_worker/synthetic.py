"""Fixture sintética reprodutível, sem conteúdo de cliente."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from PIL import Image, ImageDraw, ImageFont

from croquito_core.models import (
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

# Fixture dedicada do "muro em degrau" (gate de fidelidade do recuo). Reproduz a assinatura
# geométrica do defeito real da primeira revisão do Guaxindiba V3 (2026-08-19): um muro que
# muda de afastamento a meio do traçado — dois trechos retos ligados por um jog
# perpendicular —, que o Opus devolveu como duas `line` retas. A corroboração de tinta
# sozinha não pega isso: cada trecho, sozinho, adere à tinta tanto quanto o muro fiel.
# Os comprimentos e afastamentos replicam os números reais do caso (19,75 / 1,50 / 14,50 /
# 4,80 / 3,30 m) na mesma escala; `DEGRAU_*_PX` é a fonte única — `extraction_eval.py`
# deriva o gabarito normalizado destas mesmas constantes, nenhum número nasce duas vezes.
DEGRAU_PAGE_WIDTH_PX = 1400
DEGRAU_PAGE_HEIGHT_PX = 1050
DEGRAU_SCALE_PX_PER_M = Decimal("20.0")

DEGRAU_FIELD_WIDTH_M = Decimal("24.00")
DEGRAU_FIELD_HEIGHT_M = Decimal("20.50")
DEGRAU_FIELD_LEFT_PX = 120
DEGRAU_FIELD_TOP_PX = 140
DEGRAU_FIELD_WIDTH_PX = int(DEGRAU_FIELD_WIDTH_M * DEGRAU_SCALE_PX_PER_M)
DEGRAU_FIELD_HEIGHT_PX = int(DEGRAU_FIELD_HEIGHT_M * DEGRAU_SCALE_PX_PER_M)
DEGRAU_FIELD_RIGHT_PX = DEGRAU_FIELD_LEFT_PX + DEGRAU_FIELD_WIDTH_PX
DEGRAU_FIELD_BOTTOM_PX = DEGRAU_FIELD_TOP_PX + DEGRAU_FIELD_HEIGHT_PX

# O muro nasce no canto inferior direito do campo e segue aberto para a direita — nunca
# fecha —, com o degrau (jog) entre os dois trechos retos.
DEGRAU_WALL_START_X_PX = DEGRAU_FIELD_RIGHT_PX
DEGRAU_WALL_START_Y_PX = DEGRAU_FIELD_BOTTOM_PX
DEGRAU_TRECHO_A_LENGTH_PX = 395
DEGRAU_JOG_LENGTH_PX = 30
DEGRAU_TRECHO_B_LENGTH_PX = 290
DEGRAU_TRECHO_A_LENGTH_M = Decimal(DEGRAU_TRECHO_A_LENGTH_PX) / DEGRAU_SCALE_PX_PER_M
DEGRAU_JOG_LENGTH_M = Decimal(DEGRAU_JOG_LENGTH_PX) / DEGRAU_SCALE_PX_PER_M
DEGRAU_TRECHO_B_LENGTH_M = Decimal(DEGRAU_TRECHO_B_LENGTH_PX) / DEGRAU_SCALE_PX_PER_M

DEGRAU_WALL_JOG_X_PX = DEGRAU_WALL_START_X_PX + DEGRAU_TRECHO_A_LENGTH_PX
DEGRAU_WALL_JOG_Y_PX = DEGRAU_WALL_START_Y_PX + DEGRAU_JOG_LENGTH_PX
DEGRAU_WALL_END_X_PX = DEGRAU_WALL_JOG_X_PX + DEGRAU_TRECHO_B_LENGTH_PX
DEGRAU_WALL_END_Y_PX = DEGRAU_WALL_JOG_Y_PX

# Vértices do muro-degrau, na ordem traçada: início, cotovelo alto (fim do trecho A),
# cotovelo baixo (início do trecho B), fim. Quatro vértices, aberto (não fecha).
DEGRAU_WALL_VERTICES_PX: tuple[
    tuple[int, int], tuple[int, int], tuple[int, int], tuple[int, int]
] = (
    (DEGRAU_WALL_START_X_PX, DEGRAU_WALL_START_Y_PX),
    (DEGRAU_WALL_JOG_X_PX, DEGRAU_WALL_START_Y_PX),
    (DEGRAU_WALL_JOG_X_PX, DEGRAU_WALL_JOG_Y_PX),
    (DEGRAU_WALL_END_X_PX, DEGRAU_WALL_END_Y_PX),
)

# Afastamentos desenhados (análogos aos 4,80/3,30 do Guaxindiba): distância vertical de cada
# trecho até a mesma linha de referência (guia). A diferença entre eles é exatamente o jog —
# nunca um segundo número solto — e é o que os torna "distintos" de propósito.
DEGRAU_AFASTAMENTO_A_M = Decimal("4.80")
DEGRAU_AFASTAMENTO_B_M = DEGRAU_AFASTAMENTO_A_M - DEGRAU_JOG_LENGTH_M
DEGRAU_GUIA_Y_PX = DEGRAU_WALL_START_Y_PX + int(DEGRAU_AFASTAMENTO_A_M * DEGRAU_SCALE_PX_PER_M)


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
        "CROQUITO - DADO SINTETICO, SEM CONTEUDO DE CLIENTE",
        fill="#4a5568",
        font=font,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG", optimize=True)


def _degrau_text(value: Decimal) -> str:
    return format(value, ".2f").replace(".", ",")


def render_degrau_boundary_input(path: Path) -> None:
    """Renderiza um campo e um muro em recuo (degrau), para o gate de fidelidade do traçado.

    Reproduz a assinatura do defeito real da primeira revisão do Guaxindiba V3: um muro
    aberto com dois trechos retos ligados por um jog perpendicular, nunca visto pela eval de
    recall — que mede corroboração de tinta, não continuidade topológica. Todas as
    coordenadas vêm de `DEGRAU_*_PX`; `extraction_eval.build_degrau_step_gabarito` deriva o
    gabarito normalizado destas mesmas constantes.
    """
    width, height = DEGRAU_PAGE_WIDTH_PX, DEGRAU_PAGE_HEIGHT_PX
    image = Image.new("RGB", (width, height), "#f5f1e8")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=22)
    small_font = ImageFont.load_default(size=18)

    draw.rectangle(
        (DEGRAU_FIELD_LEFT_PX, DEGRAU_FIELD_TOP_PX, DEGRAU_FIELD_RIGHT_PX, DEGRAU_FIELD_BOTTOM_PX),
        outline="#243447",
        width=5,
    )
    draw.line(list(DEGRAU_WALL_VERTICES_PX), fill="#243447", width=5, joint="curve")

    # Guia (limite/curva de referência) e os dois afastamentos distintos até ela — o
    # análogo sintético dos 4,80/3,30 m do Guaxindiba.
    guia_left = DEGRAU_WALL_START_X_PX - 20
    guia_right = DEGRAU_WALL_END_X_PX + 20
    draw.line((guia_left, DEGRAU_GUIA_Y_PX, guia_right, DEGRAU_GUIA_Y_PX), fill="#596a7a", width=2)

    mid_x_a = (DEGRAU_WALL_START_X_PX + DEGRAU_WALL_JOG_X_PX) // 2
    mid_x_b = (DEGRAU_WALL_JOG_X_PX + DEGRAU_WALL_END_X_PX) // 2
    draw.line((mid_x_a, DEGRAU_WALL_START_Y_PX, mid_x_a, DEGRAU_GUIA_Y_PX), fill="#9b2c2c", width=2)
    draw.text(
        (mid_x_a + 8, (DEGRAU_WALL_START_Y_PX + DEGRAU_GUIA_Y_PX) // 2 - 10),
        f"{_degrau_text(DEGRAU_AFASTAMENTO_A_M)} m",
        fill="#9b2c2c",
        font=small_font,
    )
    draw.line((mid_x_b, DEGRAU_WALL_JOG_Y_PX, mid_x_b, DEGRAU_GUIA_Y_PX), fill="#9b2c2c", width=2)
    draw.text(
        (mid_x_b + 8, (DEGRAU_WALL_JOG_Y_PX + DEGRAU_GUIA_Y_PX) // 2 - 10),
        f"{_degrau_text(DEGRAU_AFASTAMENTO_B_M)} m",
        fill="#9b2c2c",
        font=small_font,
    )

    # Cotas em texto dos dois trechos e do jog, no mesmo estilo das cotas existentes.
    draw.text(
        (mid_x_a - 45, DEGRAU_WALL_START_Y_PX - 30),
        f"{_degrau_text(DEGRAU_TRECHO_A_LENGTH_M)} m",
        fill="#9b2c2c",
        font=small_font,
    )
    draw.text(
        (DEGRAU_WALL_JOG_X_PX + 8, (DEGRAU_WALL_START_Y_PX + DEGRAU_WALL_JOG_Y_PX) // 2 - 10),
        f"{_degrau_text(DEGRAU_JOG_LENGTH_M)} m",
        fill="#9b2c2c",
        font=small_font,
    )
    draw.text(
        (mid_x_b - 45, DEGRAU_WALL_JOG_Y_PX - 30),
        f"{_degrau_text(DEGRAU_TRECHO_B_LENGTH_M)} m",
        fill="#9b2c2c",
        font=small_font,
    )
    draw.text(
        (40, 35),
        "CROQUITO - DADO SINTETICO, SEM CONTEUDO DE CLIENTE",
        fill="#4a5568",
        font=font,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG", optimize=True)
