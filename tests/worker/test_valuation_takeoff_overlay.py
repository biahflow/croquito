"""Balão numerado + legenda em coluna do overlay de takeoff.

O rótulo inline antigo (`elemento | estado | quantidade`) colidia em prancha real: fonte
proporcional à largura da folha, linhas de legenda contíguas de poucos pixels de altura.
Estes testes cobrem o que substituiu o rótulo — geometria pura (`balloon_layout`,
`legend_panel_layout`) testável sem PIL, e determinismo do render completo.
"""

from __future__ import annotations

import math
from itertools import combinations
from pathlib import Path

import pytest

from croquito_valuation.takeoff import PlateBox
from croquito_worker.valuation.plate import render_synthetic_plate
from croquito_worker.valuation.takeoff_fixture import extract_takeoff_fixture
from croquito_worker.valuation.takeoff_overlay import (
    BALLOON_MAX_DIAMETER_FRACTION,
    BALLOON_MIN_DIAMETER_PX,
    balloon_layout,
    legend_panel_layout,
    render_takeoff_overlay,
)


def _dense_boxes(
    count: int, *, row_height: int = 20, left: int = 6000, width: int = 1800, top0: int = 400
) -> list[PlateBox]:
    """Linhas de legenda contíguas — o formato de uma folha real densa, não a sintética."""
    return [
        PlateBox(
            left=left,
            top=top0 + index * row_height,
            right=left + width,
            bottom=top0 + (index + 1) * row_height,
        )
        for index in range(count)
    ]


def test_balloons_of_contiguous_rows_never_overlap_on_a_large_real_sized_sheet() -> None:
    """~20 px de altura por linha numa folha de 8000x5600: o caso que a folha real trouxe."""
    boxes = _dense_boxes(60)

    placements = balloon_layout(boxes, image_width=8000)

    assert len(placements) == len(boxes)
    for first, second in combinations(placements, 2):
        distance = math.hypot(first.center_x - second.center_x, first.center_y - second.center_y)
        assert distance >= first.radius + second.radius - 1e-6, (
            "dois balões vizinhos não podem se sobrepor"
        )


def test_balloon_diameter_never_goes_below_the_floor() -> None:
    boxes = [PlateBox(left=100, top=100, right=200, bottom=104)]  # bbox de 4 px de altura

    placements = balloon_layout(boxes, image_width=8000)

    assert placements[0].radius * 2 == pytest.approx(BALLOON_MIN_DIAMETER_PX)


def test_balloon_diameter_never_goes_above_the_sheet_width_ceiling() -> None:
    boxes = [PlateBox(left=100, top=100, right=200, bottom=2000)]  # bbox de 1900 px de altura

    placements = balloon_layout(boxes, image_width=8000)

    assert placements[0].radius * 2 <= 8000 * BALLOON_MAX_DIAMETER_FRACTION + 1e-9


def test_balloon_diameter_scales_with_bbox_height_not_sheet_width() -> None:
    """A folha real (9362 px) e a sintética (1750 px) não podem produzir balões do
    mesmo item em proporções diferentes por causa da largura — só a altura do bbox conta
    (desde que o teto de 3% da largura não entre em jogo em nenhuma das duas)."""
    box = PlateBox(left=1000, top=1000, right=1100, bottom=1020)  # 20 px de altura

    on_real_sheet = balloon_layout([box], image_width=9362)
    on_synthetic_sheet = balloon_layout([box], image_width=1750)

    assert on_real_sheet[0].radius == pytest.approx(on_synthetic_sheet[0].radius)


def test_balloon_never_leaves_the_image_on_the_left() -> None:
    boxes = [PlateBox(left=2, top=100, right=50, bottom=120)]

    placements = balloon_layout(boxes, image_width=8000)

    assert placements[0].center_x - placements[0].radius >= -1e-9


def test_balloon_layout_is_empty_for_no_boxes() -> None:
    assert balloon_layout([], image_width=8000) == []


def test_legend_panel_never_covers_the_banner_and_fits_the_image() -> None:
    banner_bottom = 212.0
    image_width, image_height = 9362, 6623

    for item_count in (1, 7, 40, 250):
        layout = legend_panel_layout(
            item_count,
            image_width=image_width,
            image_height=image_height,
            banner_bottom=banner_bottom,
        )
        left, top, right, bottom = layout.panel_box

        assert top > banner_bottom, "o painel nunca pode começar em cima do banner"
        assert left >= 0.0
        assert right <= image_width
        assert bottom <= image_height
        assert layout.columns >= 1
        assert layout.rows_per_column >= 1


def test_legend_panel_breaks_into_more_columns_when_the_list_does_not_fit_one() -> None:
    layout = legend_panel_layout(200, image_width=1750, image_height=1238, banner_bottom=56.0)

    assert layout.columns > 1
    _left, top, right, bottom = layout.panel_box
    assert top > 56.0
    assert right <= 1750
    assert bottom <= 1238


def test_legend_panel_fits_a_short_list_in_a_single_column() -> None:
    layout = legend_panel_layout(7, image_width=1750, image_height=1238, banner_bottom=56.0)

    assert layout.columns == 1
    assert layout.rows_per_column >= 7


def test_two_renders_of_the_same_packet_produce_identical_bytes(tmp_path: Path) -> None:
    """Determinismo: mesma entrada, mesmos pixels — a diferença não pode nascer do balão
    numerado nem da composição translúcida do painel de legenda."""
    artifacts = render_synthetic_plate(tmp_path / "plate")
    packet = extract_takeoff_fixture(artifacts)

    first = render_takeoff_overlay(artifacts.image_path, packet)
    second = render_takeoff_overlay(artifacts.image_path, packet)

    assert first.size == second.size
    assert first.tobytes() == second.tobytes()


def test_render_takeoff_overlay_places_a_balloon_and_legend_entry_per_item(
    tmp_path: Path,
) -> None:
    """Smoke do caminho completo sobre a prancha sintética real: não deve levantar nada
    e deve produzir uma imagem do mesmo tamanho da prancha."""
    artifacts = render_synthetic_plate(tmp_path / "plate")
    packet = extract_takeoff_fixture(artifacts)

    image = render_takeoff_overlay(artifacts.image_path, packet)

    assert image.size == (artifacts.image_width, artifacts.image_height)
