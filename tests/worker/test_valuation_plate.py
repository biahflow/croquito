"""A prancha sintética e o gabarito da legenda nascem da mesma constante.

O que estes testes protegem não é a aparência da prancha: é a promessa de que o número
impresso no papel, o `raw_text` que o extrator vai preservar e o bbox que o overlay vai
desenhar saem todos de `SYNTHETIC_LEGEND_ROWS`. Se o desenho e o gabarito puderem
divergir, a fixture inteira deixa de valer como oráculo.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf
from PIL import Image

from croquito_valuation.catalog import file_sha256
from croquito_worker.valuation.plate import (
    PLATE_IMAGE_FILENAME,
    PLATE_IMAGE_HEIGHT_PX,
    PLATE_IMAGE_WIDTH_PX,
    PLATE_PDF_FILENAME,
    SYNTHETIC_LEGEND_ROWS,
    SYNTHETIC_PLATE_ID,
    render_synthetic_plate,
)


def test_render_writes_pdf_and_png_with_the_declared_digests(tmp_path: Path) -> None:
    artifacts = render_synthetic_plate(tmp_path / "plate")

    assert artifacts.plate_id == SYNTHETIC_PLATE_ID
    assert artifacts.pdf_path.name == PLATE_PDF_FILENAME
    assert artifacts.image_path.name == PLATE_IMAGE_FILENAME
    assert artifacts.pdf_sha256 == file_sha256(artifacts.pdf_path)
    assert artifacts.image_sha256 == file_sha256(artifacts.image_path)
    document = pymupdf.open(artifacts.pdf_path)
    try:
        assert document.page_count == 1
    finally:
        document.close()


def test_render_has_the_size_the_layout_declares(tmp_path: Path) -> None:
    """O bbox do gabarito é a posição em pt escalada pelo DPI; a folha tem de bater."""
    artifacts = render_synthetic_plate(tmp_path / "plate")

    with Image.open(artifacts.image_path) as image:
        assert image.size == (PLATE_IMAGE_WIDTH_PX, PLATE_IMAGE_HEIGHT_PX)
    assert (artifacts.image_width, artifacts.image_height) == (
        PLATE_IMAGE_WIDTH_PX,
        PLATE_IMAGE_HEIGHT_PX,
    )


def test_gabarito_has_one_row_per_legend_constant(tmp_path: Path) -> None:
    artifacts = render_synthetic_plate(tmp_path / "plate")

    assert [entry.row for entry in artifacts.rows] == list(SYNTHETIC_LEGEND_ROWS)


def test_printed_legend_is_exactly_what_the_gabarito_declares(tmp_path: Path) -> None:
    """O texto extraído do PDF gerado carrega rótulo, quantidade e unidade de cada linha.

    É o cheque que impede o gabarito de descrever uma prancha diferente da impressa —
    inclusive quando a fonte do PDF troca um glifo que não sabe gravar.
    """
    artifacts = render_synthetic_plate(tmp_path / "plate")
    document = pymupdf.open(artifacts.pdf_path)
    try:
        printed = document.load_page(0).get_text("text")
    finally:
        document.close()

    for row in SYNTHETIC_LEGEND_ROWS:
        assert row.plate_label in printed
        assert row.raw_quantity_text in printed
        assert f"{row.raw_quantity_text}\n{row.unit}" in printed


def test_row_boxes_have_positive_area_inside_the_render_and_do_not_overlap(
    tmp_path: Path,
) -> None:
    artifacts = render_synthetic_plate(tmp_path / "plate")

    previous_bottom = 0
    for entry in artifacts.rows:
        box = entry.bbox
        assert 0 <= box.left < box.right <= artifacts.image_width
        assert 0 <= box.top < box.bottom <= artifacts.image_height
        assert box.top >= previous_bottom
        previous_bottom = box.bottom


def test_two_renders_of_the_same_plate_share_the_gabarito(tmp_path: Path) -> None:
    """Os bytes do PDF variam a cada `save`; as posições e as quantidades, não."""
    first = render_synthetic_plate(tmp_path / "first")
    second = render_synthetic_plate(tmp_path / "second")

    assert [entry.bbox for entry in first.rows] == [entry.bbox for entry in second.rows]
    assert first.image_sha256 == second.image_sha256
