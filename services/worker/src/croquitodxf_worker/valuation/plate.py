"""Prancha sintética do projetista: desenho, legenda quantificada e gabarito numa fonte só.

A prancha que chega ao orçamentista traz a legenda **já quantificada** — pisos em m²,
alambrado em m com a altura anotada, mobiliário em unidades, área de intervenção. É a
legenda que carrega o quantitativo; o desenho é ilustração. Este módulo reproduz essa
forma numa prancha inteiramente inventada, para que a extração possa ser exercitada sem
nenhuma prancha de cliente.

O ponto do módulo é `SYNTHETIC_LEGEND_ROWS`: a MESMA tupla alimenta o que é impresso na
prancha e o gabarito devolvido em `PlateArtifacts` (rótulo, texto da quantidade, unidade,
nota e bbox em pixels). Nenhum número da legenda é escrito duas vezes — quem muda a
constante muda o desenho e o gabarito juntos, como `FIELD_WIDTH` faz em
`croquitodxf_worker.synthetic`.

O que **não** é contrato: os bytes do PDF. O pymupdf grava identificadores próprios a
cada `save`, então dois renders da mesma prancha têm digests diferentes. O contrato é o
outro: os digests em `PlateArtifacts` são os do que acabou de ser gerado, e é por eles
que o pacote de takeoff fica amarrado à prancha que o originou.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Final

import pymupdf

from croquitodxf_valuation.catalog import file_sha256
from croquitodxf_valuation.errors import ValuationValidationError
from croquitodxf_valuation.takeoff import PlateBox

SYNTHETIC_PLATE_ID: Final = "plate-sintetica-v1"
PLATE_EXTRACTOR_VERSION: Final = "1.0.0"
"""Versão do par layout+gabarito. Mudou a legenda ou o layout, muda aqui: é ela que o
extrator fixture registra como `extractor_version` em cada item."""

PLATE_PAGE_NUMBER: Final = 1
PLATE_PDF_FILENAME: Final = "prancha.pdf"
PLATE_IMAGE_FILENAME: Final = "prancha.png"

PLATE_DPI: Final = 150


@dataclass(frozen=True, slots=True)
class LegendRow:
    """Uma linha da legenda quantificada: o que é impresso e o que o gabarito espera.

    `quantity` é `None` na linha deliberadamente ilegível — a que vira item `ambiguous`,
    com o elemento identificado e a quantidade não. `raw_quantity_text` é a quantidade
    como escrita em português na prancha; `quantity` é o `Decimal` do gabarito.
    """

    label: str
    raw_quantity_text: str
    quantity: Decimal | None
    unit: str
    note: str | None = None

    @property
    def plate_label(self) -> str:
        """Rótulo como impresso: a nota (`h=1,20m`) anda colada ao elemento na prancha."""
        return self.label if self.note is None else f"{self.label} ({self.note})"

    def as_written(self) -> str:
        """A linha inteira como escrita na legenda; é o `raw_text` preservado no takeoff."""
        return f"{self.plate_label} {self.raw_quantity_text} {self.unit}"


SYNTHETIC_LEGEND_ROWS: Final[tuple[LegendRow, ...]] = (
    LegendRow("PISO INTERTRAVADO SINTETICO", "61,20", Decimal("61.20"), "M2"),
    LegendRow("GRAMADO SINTETICO", "1.234,50", Decimal("1234.50"), "M2"),
    LegendRow("ALAMBRADO SINTETICO", "48,75", Decimal("48.75"), "M", note="h=1,20m"),
    LegendRow("BANCO DE CONCRETO SINTETICO", "4", Decimal("4"), "UN"),
    LegendRow("LUMINARIA DUPLA SINTETICA", "7", Decimal("7"), "UN"),
    LegendRow("AREA DE INTERVENCAO SINTETICA", "2.345,67", Decimal("2345.67"), "M2"),
    LegendRow("PISO EMBORRACHADO SINTETICO", "---", None, "M2"),
)
"""Legenda inventada com a forma do domínio real: dois pisos em m², um alambrado em m com
altura anotada, dois mobiliários em unidade, a área de intervenção e uma última linha
ilegível de propósito — a que obriga o orçamentista a informar a quantidade.

O texto ilegível é escrito com hífens ASCII porque as fontes Base14 do PDF trocam
travessão por outro glifo ao gravar: o que fica no papel tem de ser exatamente o que o
gabarito declara, senão o `raw_text` do item mentiria sobre a prancha."""

PLATE_TITLE: Final = "PLANTA DE URBANIZACAO SINTETICA"
PLATE_SUBTITLE: Final = "DADO SINTETICO - NENHUMA PRANCHA DE CLIENTE FOI LIDA"
LEGEND_TITLE: Final = "LEGENDA QUANTIFICADA"

# Folha A4 paisagem arredondada para múltiplo de 12 pt: a 150 DPI (25/12 px/pt) a página
# inteira cai em pixel exato, então o bbox do gabarito não depende do arredondamento da
# folha — só das posições declaradas abaixo.
PAGE_WIDTH_PT: Final = 840.0
PAGE_HEIGHT_PT: Final = 588.0
MARGIN_PT: Final = 36.0

TITLE_BASELINE_PT: Final = 52.0
TITLE_SIZE_PT: Final = 15.0
SUBTITLE_BASELINE_PT: Final = 70.0
SUBTITLE_SIZE_PT: Final = 8.0

DRAWING_LEFT_PT: Final = MARGIN_PT
DRAWING_TOP_PT: Final = 96.0
DRAWING_RIGHT_PT: Final = 470.0
DRAWING_BOTTOM_PT: Final = 540.0

LEGEND_LEFT_PT: Final = 500.0
LEGEND_RIGHT_PT: Final = PAGE_WIDTH_PT - MARGIN_PT
LEGEND_TITLE_BASELINE_PT: Final = 90.0
LEGEND_HEADER_TOP_PT: Final = 96.0
LEGEND_HEADER_HEIGHT_PT: Final = 24.0
LEGEND_ROW_HEIGHT_PT: Final = 32.0
LEGEND_LABEL_OFFSET_PT: Final = 8.0
LEGEND_QUANTITY_OFFSET_PT: Final = 196.0
LEGEND_UNIT_OFFSET_PT: Final = 268.0
LEGEND_TEXT_BASELINE_OFFSET_PT: Final = 20.0
LEGEND_TEXT_SIZE_PT: Final = 9.0

_INK: Final = (0.14, 0.20, 0.28)
_LIGHT_INK: Final = (0.40, 0.46, 0.53)
_PAPER_STROKE: Final = (0.62, 0.66, 0.70)


def _to_pixels(value_pt: float) -> int:
    """Converte ponto do PDF para pixel do render, na mesma escala usada pelo pixmap."""
    return round(value_pt * PLATE_DPI / 72.0)


PLATE_IMAGE_WIDTH_PX: Final = _to_pixels(PAGE_WIDTH_PT)
PLATE_IMAGE_HEIGHT_PX: Final = _to_pixels(PAGE_HEIGHT_PT)


@dataclass(frozen=True, slots=True)
class PlateLegendRow:
    """Uma linha da legenda e o retângulo em pixels onde ela foi impressa."""

    row: LegendRow
    bbox: PlateBox


@dataclass(frozen=True, slots=True)
class PlateArtifacts:
    """Prancha gerada agora: caminhos, digests e o gabarito da legenda em pixels.

    É este objeto — não um caminho arbitrário — que o extrator fixture aceita. O par
    gerar+extrair anda junto de propósito: fixture não fabrica observação sobre documento
    que ela não desenhou.
    """

    plate_id: str
    page_number: int
    pdf_path: Path
    image_path: Path
    pdf_sha256: str
    image_sha256: str
    image_width: int
    image_height: int
    rows: tuple[PlateLegendRow, ...]


def _row_top_pt(index: int) -> float:
    return LEGEND_HEADER_TOP_PT + LEGEND_HEADER_HEIGHT_PT + index * LEGEND_ROW_HEIGHT_PT


def _row_bbox(index: int) -> PlateBox:
    """bbox da linha em pixels, derivado das mesmas posições que imprimiram a linha."""
    top_pt = _row_top_pt(index)
    return PlateBox(
        left=_to_pixels(LEGEND_LEFT_PT),
        top=_to_pixels(top_pt),
        right=min(_to_pixels(LEGEND_RIGHT_PT), PLATE_IMAGE_WIDTH_PX),
        bottom=min(_to_pixels(top_pt + LEGEND_ROW_HEIGHT_PT), PLATE_IMAGE_HEIGHT_PX),
    )


def _draw_plan(page: pymupdf.Page) -> None:
    """Esquema da praça: ilustração, não fonte de quantitativo.

    Na prancha real a quantidade mora na legenda, e é a legenda que a extração lê. O
    desenho existe para que a prancha tenha a forma de uma prancha.
    """
    page.draw_rect(
        pymupdf.Rect(DRAWING_LEFT_PT, DRAWING_TOP_PT, DRAWING_RIGHT_PT, DRAWING_BOTTOM_PT),
        color=_INK,
        width=1.4,
    )
    inner = pymupdf.Rect(
        DRAWING_LEFT_PT + 40.0,
        DRAWING_TOP_PT + 40.0,
        DRAWING_RIGHT_PT - 40.0,
        DRAWING_BOTTOM_PT - 150.0,
    )
    page.draw_rect(inner, color=_LIGHT_INK, width=1.0)
    page.draw_circle(
        pymupdf.Point((inner.x0 + inner.x1) / 2.0, (inner.y0 + inner.y1) / 2.0),
        46.0,
        color=_LIGHT_INK,
        width=1.0,
    )
    page.draw_line(
        pymupdf.Point(DRAWING_LEFT_PT + 20.0, DRAWING_BOTTOM_PT - 110.0),
        pymupdf.Point(DRAWING_RIGHT_PT - 20.0, DRAWING_BOTTOM_PT - 110.0),
        color=_LIGHT_INK,
        width=1.0,
    )
    page.insert_text(
        pymupdf.Point(DRAWING_LEFT_PT + 12.0, DRAWING_BOTTOM_PT - 30.0),
        "ESQUEMA SEM ESCALA - QUANTITATIVO NA LEGENDA",
        fontsize=SUBTITLE_SIZE_PT,
        fontname="helv",
        color=_LIGHT_INK,
    )


def _draw_legend(page: pymupdf.Page) -> None:
    """Imprime a legenda a partir de `SYNTHETIC_LEGEND_ROWS`, uma linha por constante."""
    page.insert_text(
        pymupdf.Point(LEGEND_LEFT_PT, LEGEND_TITLE_BASELINE_PT),
        LEGEND_TITLE,
        fontsize=TITLE_SIZE_PT - 4.0,
        fontname="hebo",
        color=_INK,
    )
    header = pymupdf.Rect(
        LEGEND_LEFT_PT,
        LEGEND_HEADER_TOP_PT,
        LEGEND_RIGHT_PT,
        LEGEND_HEADER_TOP_PT + LEGEND_HEADER_HEIGHT_PT,
    )
    page.draw_rect(header, color=_INK, width=1.0)
    for text, offset in (
        ("ELEMENTO", LEGEND_LABEL_OFFSET_PT),
        ("QUANT.", LEGEND_QUANTITY_OFFSET_PT),
        ("UN", LEGEND_UNIT_OFFSET_PT),
    ):
        page.insert_text(
            pymupdf.Point(LEGEND_LEFT_PT + offset, LEGEND_HEADER_TOP_PT + 16.0),
            text,
            fontsize=LEGEND_TEXT_SIZE_PT,
            fontname="hebo",
            color=_INK,
        )

    for index, row in enumerate(SYNTHETIC_LEGEND_ROWS):
        top_pt = _row_top_pt(index)
        page.draw_rect(
            pymupdf.Rect(LEGEND_LEFT_PT, top_pt, LEGEND_RIGHT_PT, top_pt + LEGEND_ROW_HEIGHT_PT),
            color=_PAPER_STROKE,
            width=0.8,
        )
        baseline = top_pt + LEGEND_TEXT_BASELINE_OFFSET_PT
        for text, offset in (
            (row.plate_label, LEGEND_LABEL_OFFSET_PT),
            (row.raw_quantity_text, LEGEND_QUANTITY_OFFSET_PT),
            (row.unit, LEGEND_UNIT_OFFSET_PT),
        ):
            page.insert_text(
                pymupdf.Point(LEGEND_LEFT_PT + offset, baseline),
                text,
                fontsize=LEGEND_TEXT_SIZE_PT,
                fontname="helv",
                color=_INK,
            )


def _write_plate_pdf(pdf_path: Path) -> None:
    """Grava a prancha em nome temporário e publica com `os.replace`."""
    document = pymupdf.open()
    try:
        page = document.new_page(width=PAGE_WIDTH_PT, height=PAGE_HEIGHT_PT)
        page.insert_text(
            pymupdf.Point(MARGIN_PT, TITLE_BASELINE_PT),
            PLATE_TITLE,
            fontsize=TITLE_SIZE_PT,
            fontname="hebo",
            color=_INK,
        )
        page.insert_text(
            pymupdf.Point(MARGIN_PT, SUBTITLE_BASELINE_PT),
            PLATE_SUBTITLE,
            fontsize=SUBTITLE_SIZE_PT,
            fontname="helv",
            color=_LIGHT_INK,
        )
        _draw_plan(page)
        _draw_legend(page)
        document.set_metadata({})
        descriptor, temporary_name = tempfile.mkstemp(
            dir=pdf_path.parent,
            prefix=f".{pdf_path.stem}.",
            suffix=".pdf",
        )
        os.close(descriptor)
        temporary_path = Path(temporary_name)
        try:
            document.save(temporary_path)
            os.replace(temporary_path, pdf_path)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()
    finally:
        document.close()


def _render_plate_image(pdf_path: Path, image_path: Path) -> tuple[int, int]:
    """Renderiza a página gravada em PNG atômico e devolve as dimensões conferidas."""
    document = pymupdf.open(pdf_path)
    try:
        page = document.load_page(PLATE_PAGE_NUMBER - 1)
        matrix = pymupdf.Matrix(PLATE_DPI / 72.0, PLATE_DPI / 72.0)
        pixmap = page.get_pixmap(matrix=matrix, alpha=False, colorspace=pymupdf.csRGB)
    finally:
        document.close()
    width, height = int(pixmap.width), int(pixmap.height)
    if (width, height) != (PLATE_IMAGE_WIDTH_PX, PLATE_IMAGE_HEIGHT_PX):
        raise ValuationValidationError(
            "PLATE_RENDER_UNEXPECTED_SIZE",
            "render da prancha sintética divergiu das dimensões declaradas pelo layout",
            {
                "rendered": [width, height],
                "expected": [PLATE_IMAGE_WIDTH_PX, PLATE_IMAGE_HEIGHT_PX],
            },
        )
    descriptor, temporary_name = tempfile.mkstemp(
        dir=image_path.parent,
        prefix=f".{image_path.stem}.",
        suffix=".png",
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        pixmap.save(temporary_path)
        os.replace(temporary_path, image_path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
    return width, height


def render_synthetic_plate(output_dir: Path) -> PlateArtifacts:
    """Gera `prancha.pdf` + `prancha.png` e devolve digests e gabarito da legenda."""
    output_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = output_dir / PLATE_PDF_FILENAME
    image_path = output_dir / PLATE_IMAGE_FILENAME
    _write_plate_pdf(pdf_path)
    width, height = _render_plate_image(pdf_path, image_path)
    return PlateArtifacts(
        plate_id=SYNTHETIC_PLATE_ID,
        page_number=PLATE_PAGE_NUMBER,
        pdf_path=pdf_path,
        image_path=image_path,
        pdf_sha256=file_sha256(pdf_path),
        image_sha256=file_sha256(image_path),
        image_width=width,
        image_height=height,
        rows=tuple(
            PlateLegendRow(row=row, bbox=_row_bbox(index))
            for index, row in enumerate(SYNTHETIC_LEGEND_ROWS)
        ),
    )
