"""Overlay de revisão do takeoff: o que foi lido, onde foi lido e o que ainda não vale.

Espelho do `render_review_overlay` das cotas (`croquitodxf_worker.review`): mesmas cores
por estado, mesmo desenho de banner e a mesma regra que interessa — o digest da imagem é
conferido contra o pacote **antes** de qualquer traço. Overlay de outra imagem é overlay
que mente sobre onde o número foi lido.

O banner é fixo e não some com o tempo: mesmo com todos os itens confirmados, a legenda
quantificada não é medição — ela ainda precisa virar boletim atrás do portão de aprovação
e saldo do contexto de medição.

Rótulo inline (nome completo colado ao bbox, com fonte proporcional à largura da folha)
funcionava na prancha sintética, mas colidia em prancha real: linhas de legenda de ~30 px
de altura recebiam texto maior que a própria linha e empilhavam sobre a vizinha,
ilegível. O export DXF já resolveu o mesmo problema para a cena métrica
(`croquitodxf_worker.element_labels.place_labels`: nome completo só onde cabe, resto vira
balão numerado + legenda em coluna). O princípio é o mesmo aqui, mas o problema não é
idêntico — este módulo desenha em pixels sobre o render da prancha, não em metros sobre
entidades de cena, e a linha de legenda de um item nunca tem "onde cabe" ao lado (as
linhas são contíguas por construção), então o balão + coluna é o modo único, não uma
alternativa ao rótulo inline.
"""

from __future__ import annotations

import math
import os
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from PIL import Image, ImageDraw, ImageFont

from croquitodxf_valuation.catalog import file_sha256
from croquitodxf_valuation.errors import ValuationValidationError
from croquitodxf_valuation.takeoff import PlateBox, TakeoffItem, TakeoffItemStatus, TakeoffPacket

TAKEOFF_OVERLAY_BANNER = (
    "LEGENDA QUANTIFICADA - REVISAO DO ORCAMENTISTA OBRIGATORIA - NAO GERA MEDICAO"
)

Box = tuple[float, float, float, float]

# --- Balão numerado por item -------------------------------------------------

BALLOON_DIAMETER_RATIO: Final = 1.8
"""Diâmetro-base do balão como múltiplo da altura do bbox do item: cai entre 1,2x e 2,5x
antes de qualquer piso/teto absoluto — o meio do intervalo pedido, não uma das pontas."""

BALLOON_MIN_DIAMETER_PX: Final = 18.0
"""Piso absoluto: abaixo disso o número não é legível em nenhuma folha."""

BALLOON_MAX_DIAMETER_FRACTION: Final = 0.03
"""Teto absoluto, como fração da LARGURA DA IMAGEM — o balão nunca cresce com a folha."""

BALLOON_GAP_PX: Final = 4.0
"""Respiro entre a borda do balão e a borda esquerda do bbox do item."""

BALLOON_RAILS: Final = 2
"""Trilhos horizontais tentados antes de aceitar sobreposição residual, no piso."""

BALLOON_NUMBER_FONT_RATIO: Final = 1.15
"""Altura de fonte do número do balão, em raios do balão."""


@dataclass(frozen=True, slots=True)
class BalloonPlacement:
    """Centro, raio e trilho de um balão — geometria pura, sem numeração nem cor."""

    center_x: float
    center_y: float
    radius: float
    rail: int


def _balloon_diameter(bbox_height: float, *, image_width: int) -> float:
    ceiling = max(image_width * BALLOON_MAX_DIAMETER_FRACTION, BALLOON_MIN_DIAMETER_PX)
    return min(max(bbox_height * BALLOON_DIAMETER_RATIO, BALLOON_MIN_DIAMETER_PX), ceiling)


def balloon_layout(boxes: Sequence[PlateBox], *, image_width: int) -> list[BalloonPlacement]:
    """Centro/raio/trilho de um balão por item, sem sobreposição entre vizinhos.

    Pura — não desenha nada — para poder ser testada isolada do PIL; é o oráculo do teste
    de colisão. Resolve os itens em ordem de posição vertical na folha (não na ordem do
    pacote): colisão é geometria da folha, não da lista de entrada. A numeração exibida
    continua vindo de quem chama, na ordem do pacote.

    Cada trilho (0 = junto ao bbox, 1 = mais afastado à esquerda) só guarda a borda
    inferior do último balão colocado nele. Como a varredura é crescente em Y, isso basta
    para garantir que um balão nunca sobrepõe NENHUM balão anterior do mesmo trilho — por
    indução: se o balão K não sobrepõe o (K-1) do trilho, e o (K-1) não sobrepunha os
    anteriores dele, a borda inferior de K-1 já é maior ou igual à de todos eles.

    Quando nem no piso um item cabe no trilho 0, ele tenta o trilho 1: os dois trilhos
    ficam separados por pelo menos o maior diâmetro calculado nesta chamada, o que
    garante que um balão de um trilho nunca alcança um balão do outro, qualquer que seja
    a proximidade vertical entre eles.
    """
    if not boxes:
        return []
    diameters = [_balloon_diameter(box.bottom - box.top, image_width=image_width) for box in boxes]
    max_diameter = max(diameters)
    centers_y = [(box.top + box.bottom) / 2 for box in boxes]
    order = sorted(range(len(boxes)), key=lambda index: centers_y[index])

    last_bottom = [float("-inf")] * BALLOON_RAILS
    placements: dict[int, BalloonPlacement] = {}
    for index in order:
        raw_radius = diameters[index] / 2
        center_y = centers_y[index]
        for rail in range(BALLOON_RAILS):
            gap = center_y - last_bottom[rail]
            is_last_rail = rail == BALLOON_RAILS - 1
            if gap >= raw_radius:
                radius = raw_radius
            elif gap >= BALLOON_MIN_DIAMETER_PX / 2:
                radius = gap
            elif is_last_rail:
                radius = BALLOON_MIN_DIAMETER_PX / 2
            else:
                continue
            last_bottom[rail] = center_y + radius
            box = boxes[index]
            center_x = box.left - BALLOON_GAP_PX - radius - rail * (max_diameter + BALLOON_GAP_PX)
            center_x = max(center_x, radius)  # clamp: o balão nunca sai da imagem à esquerda
            placements[index] = BalloonPlacement(
                center_x=center_x, center_y=center_y, radius=radius, rail=rail
            )
            break
    return [placements[index] for index in range(len(boxes))]


# --- Legenda em coluna --------------------------------------------------------

LEGEND_LABEL_MAX_CHARS: Final = 48

LEGEND_MARGIN_PX: Final = 14.0
LEGEND_FONT_MIN_PX: Final = 16.0
LEGEND_FONT_MAX_PX: Final = 40.0
LEGEND_FONT_WIDTH_RATIO: Final = 0.008
LEGEND_LINE_PITCH: Final = 1.6
LEGEND_COLUMN_WIDTH_RATIO: Final = 0.32
"""Largura de cada coluna da legenda, como fração da largura da imagem."""

LEGEND_MARKER_RATIO: Final = 0.6
"""Lado do quadradinho marcador de estado, em alturas de fonte da legenda."""

LEGEND_PANEL_FILL: Final = (255, 255, 255, 217)
"""Branco a ~85% de opacidade (217/255)."""

LEGEND_PANEL_BORDER: Final = (26, 26, 26, 255)
LEGEND_TEXT_COLOR: Final = (26, 26, 26)


@dataclass(frozen=True, slots=True)
class LegendLayout:
    """Geometria do painel de legenda — pura, testável sem desenhar nada."""

    panel_box: Box
    font_size: float
    row_height: float
    column_width: float
    columns: int
    rows_per_column: int


def legend_panel_layout(
    item_count: int, *, image_width: int, image_height: int, banner_bottom: float
) -> LegendLayout:
    """Painel da legenda: sempre abaixo do banner e sempre dentro da folha.

    Quebra em mais colunas (a segunda, e além dela se preciso) quando a lista não cabe na
    altura livre abaixo do banner. `panel_top` nasce estritamente abaixo de `banner_bottom`
    e `panel_right`/`panel_bottom` são sempre recortados pelas bordas da imagem — o painel
    nunca cobre o banner nem escapa da folha, por construção, não por checagem posterior.
    """
    font_size = min(
        LEGEND_FONT_MAX_PX, max(LEGEND_FONT_MIN_PX, image_width * LEGEND_FONT_WIDTH_RATIO)
    )
    row_height = font_size * LEGEND_LINE_PITCH
    panel_top = banner_bottom + LEGEND_MARGIN_PX
    available_height = max(row_height, image_height - panel_top - LEGEND_MARGIN_PX)
    rows_that_fit_one_column = max(1, int(available_height // row_height))
    column_width = image_width * LEGEND_COLUMN_WIDTH_RATIO
    available_width = max(column_width, image_width - 2 * LEGEND_MARGIN_PX)
    max_columns_that_fit = max(1, int(available_width // column_width))

    desired_columns = math.ceil(item_count / rows_that_fit_one_column)
    columns = max(1, min(max_columns_that_fit, desired_columns))
    rows_per_column = max(1, math.ceil(item_count / columns))

    panel_left = LEGEND_MARGIN_PX
    panel_right = min(image_width - LEGEND_MARGIN_PX, panel_left + columns * column_width)
    panel_bottom = min(
        image_height - LEGEND_MARGIN_PX,
        panel_top + rows_per_column * row_height + LEGEND_MARGIN_PX,
    )
    return LegendLayout(
        panel_box=(panel_left, panel_top, panel_right, panel_bottom),
        font_size=font_size,
        row_height=row_height,
        column_width=column_width,
        columns=columns,
        rows_per_column=rows_per_column,
    )


def _status_color(status: TakeoffItemStatus) -> str:
    """Mesma paleta do overlay de cotas: azul, laranja, verde e vermelho por estado."""
    return {
        TakeoffItemStatus.PROPOSED: "#1769aa",
        TakeoffItemStatus.AMBIGUOUS: "#c66a00",
        TakeoffItemStatus.CONFIRMED: "#18864b",
        TakeoffItemStatus.REJECTED: "#b42318",
    }[status]


def _legend_entry_text(number: int, item: TakeoffItem) -> str:
    """`NN. rótulo (truncado) | estado | quantidade unidade` — uma linha da legenda."""
    label = item.label
    if len(label) > LEGEND_LABEL_MAX_CHARS:
        label = f"{label[: LEGEND_LABEL_MAX_CHARS - 1]}…"
    quantity = "?" if item.quantity is None else f"{item.quantity} {item.unit}"
    return f"{number}. {label} | {item.status.value} | {quantity}"


def render_takeoff_overlay(image_path: Path, packet: TakeoffPacket) -> Image.Image:
    """Desenha bbox, balão numerado, legenda em coluna e banner sobre o render da prancha."""
    if file_sha256(image_path) != packet.image_sha256:
        raise ValuationValidationError(
            "TAKEOFF_OVERLAY_DIGEST_MISMATCH",
            "digest da imagem não corresponde ao pacote de takeoff",
            {"image": image_path.name, "expected": packet.image_sha256},
        )
    image = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(image)
    stroke = max(3, round(image.width * 0.002))

    boxes: list[PlateBox] = []
    for item in packet.items:
        box = item.evidence.bbox
        if box.right > image.width or box.bottom > image.height:
            raise ValuationValidationError(
                "TAKEOFF_OVERLAY_BBOX_OUTSIDE_IMAGE",
                "bbox do item cai fora da imagem da prancha",
                {"id": item.id, "bbox": box.model_dump()},
            )
        boxes.append(box)
        draw.rectangle(
            (box.left, box.top, box.right, box.bottom),
            outline=_status_color(item.status),
            width=stroke,
        )

    placements = balloon_layout(boxes, image_width=image.width)
    for number, (item, placement) in enumerate(zip(packet.items, placements, strict=True), start=1):
        color = _status_color(item.status)
        center_x, center_y, radius = placement.center_x, placement.center_y, placement.radius
        draw.ellipse(
            (center_x - radius, center_y - radius, center_x + radius, center_y + radius),
            fill=color,
        )
        digits = str(number)
        number_height = max(1, round(radius * BALLOON_NUMBER_FONT_RATIO))
        number_font = ImageFont.load_default(size=number_height)
        digit_box = draw.textbbox((0, 0), digits, font=number_font)
        digit_width = digit_box[2] - digit_box[0]
        digit_height = digit_box[3] - digit_box[1]
        draw.text(
            (center_x - digit_width / 2 - digit_box[0], center_y - digit_height / 2 - digit_box[1]),
            digits,
            fill="white",
            font=number_font,
        )

    banner_height = max(52, round(image.height * 0.032))

    legend = legend_panel_layout(
        len(packet.items),
        image_width=image.width,
        image_height=image.height,
        banner_bottom=banner_height,
    )
    panel_left, panel_top, panel_right, panel_bottom = legend.panel_box
    # Painel translúcido: compõe uma camada RGBA separada sobre a imagem em vez de
    # desenhar direto — é como se pinta branco a ~85% sem apagar o que está por baixo.
    overlay_layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    ImageDraw.Draw(overlay_layer).rectangle(
        (panel_left, panel_top, panel_right, panel_bottom),
        fill=LEGEND_PANEL_FILL,
        outline=LEGEND_PANEL_BORDER,
        width=2,
    )
    image = Image.alpha_composite(image.convert("RGBA"), overlay_layer).convert("RGB")
    draw = ImageDraw.Draw(image)

    legend_font = ImageFont.load_default(size=round(legend.font_size))
    marker_size = legend.font_size * LEGEND_MARKER_RATIO
    padding = LEGEND_MARGIN_PX / 2
    for index, item in enumerate(packet.items):
        column = index // legend.rows_per_column
        row = index % legend.rows_per_column
        entry_x = panel_left + padding + column * legend.column_width
        entry_y = panel_top + padding + row * legend.row_height
        draw.rectangle(
            (entry_x, entry_y, entry_x + marker_size, entry_y + marker_size),
            fill=_status_color(item.status),
        )
        draw.text(
            (entry_x + marker_size + 6, entry_y),
            _legend_entry_text(index + 1, item),
            fill=LEGEND_TEXT_COLOR,
            font=legend_font,
        )

    # Banner por último: fica sempre por cima do painel, mesmo que a geometria da legenda
    # algum dia mude — defesa em profundidade além do clamp de `legend_panel_layout`.
    draw.rectangle((0, 0, image.width, banner_height), fill="#161b22")
    banner_font = ImageFont.load_default(size=max(16, round(image.width * 0.011)))
    draw.text(
        (stroke * 2, max(4, banner_height // 5)),
        TAKEOFF_OVERLAY_BANNER,
        fill="white",
        font=banner_font,
    )
    return image


def save_takeoff_overlay(image: Image.Image, output_path: Path) -> Path:
    """Publica o PNG do overlay atomicamente; espelho de `_atomic_save_png`."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=output_path.parent,
        prefix=f".{output_path.stem}.",
        suffix=".png",
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        image.save(temporary_path, format="PNG", optimize=True)
        os.replace(temporary_path, output_path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
    return output_path


def write_takeoff_overlay(image_path: Path, packet: TakeoffPacket, output_path: Path) -> Path:
    """Renderiza e publica o overlay. A CLI separa os dois passos de propósito: uma
    recusa de digest precisa acontecer antes de qualquer arquivo ser gravado."""
    return save_takeoff_overlay(render_takeoff_overlay(image_path, packet), output_path)
