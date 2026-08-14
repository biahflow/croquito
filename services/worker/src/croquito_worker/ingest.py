"""Ingestão local de PDF sem upload ou inferência externa."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, ConfigDict, Field, field_validator


class PageManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    number: int = Field(ge=1)
    width_points: float = Field(gt=0)
    height_points: float = Field(gt=0)
    rotation_degrees: int
    rendered_width_px: int = Field(gt=0)
    rendered_height_px: int = Field(gt=0)
    ink_coverage: float = Field(ge=0, le=1)
    text_character_count: int = Field(ge=0)
    vector_drawing_count: int = Field(ge=0)
    blank_candidate: bool
    image_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    render_file: str


class PdfManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0.0"
    dataset_id: str
    role: str
    source_basename: str
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_size_bytes: int = Field(ge=1)
    page_count: int = Field(ge=1)
    encrypted: bool
    rendered_at: datetime
    renderer: str
    retention_notice: str
    pages: list[PageManifest]

    @field_validator("dataset_id")
    @classmethod
    def validate_dataset_id(cls, value: str) -> str:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,63}", value):
            raise ValueError("dataset_id deve usar apenas minúsculas, números e hífen")
        return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_write_text(path: Path, content: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _page_metrics(image_path: Path) -> tuple[int, int, float]:
    with Image.open(image_path) as image:
        grayscale = image.convert("L")
        histogram = grayscale.histogram()
        pixel_count = grayscale.width * grayscale.height
        ink_pixels = sum(histogram[:245])
        return grayscale.width, grayscale.height, ink_pixels / pixel_count


def build_contact_sheet(
    image_paths: list[Path],
    output_path: Path,
    *,
    title: str,
) -> None:
    columns = min(3, len(image_paths))
    rows = math.ceil(len(image_paths) / columns)
    cell_width, cell_height = 460, 620
    header_height = 58
    sheet = Image.new(
        "RGB",
        (columns * cell_width, header_height + rows * cell_height),
        "#e9ece8",
    )
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=20)
    label_font = ImageFont.load_default(size=16)
    draw.text((18, 18), title, fill="#26362e", font=font)

    for index, path in enumerate(image_paths):
        with Image.open(path) as source:
            thumbnail = source.convert("RGB")
            thumbnail.thumbnail((cell_width - 34, cell_height - 50))
        column = index % columns
        row = index // columns
        x = column * cell_width + (cell_width - thumbnail.width) // 2
        y = header_height + row * cell_height + 30
        sheet.paste(thumbnail, (x, y))
        draw.text(
            (column * cell_width + 14, header_height + row * cell_height + 8),
            f"Pagina {index + 1}",
            fill="#40554a",
            font=label_font,
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=output_path.parent,
        prefix=f".{output_path.stem}.",
        suffix=".png",
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        sheet.save(temporary_path, format="PNG", optimize=True)
        os.replace(temporary_path, output_path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def ingest_pdf(
    input_path: Path,
    output_root: Path,
    *,
    dataset_id: str,
    role: str,
    dpi: int = 200,
) -> tuple[PdfManifest, Path]:
    """Renderiza e registra um PDF local sem copiar o original."""
    if dpi < 96 or dpi > 600:
        raise ValueError("dpi deve estar entre 96 e 600")
    source = input_path.expanduser().resolve(strict=True)
    if source.suffix.lower() != ".pdf":
        raise ValueError("a entrada deve ser um arquivo PDF")

    output_dir = output_root / dataset_id
    output_dir.mkdir(parents=True, exist_ok=True)
    document = pymupdf.open(source)
    try:
        if document.needs_pass:
            raise ValueError("PDF protegido por senha não pode ser ingerido sem autorização")
        if document.page_count < 1:
            raise ValueError("PDF não possui páginas")

        matrix = pymupdf.Matrix(dpi / 72, dpi / 72)
        page_records: list[PageManifest] = []
        page_paths: list[Path] = []
        for page_index in range(document.page_count):
            page = document.load_page(page_index)
            page_path = output_dir / f"page-{page_index + 1:03d}.png"
            descriptor, temporary_name = tempfile.mkstemp(
                dir=output_dir,
                prefix=f".page-{page_index + 1:03d}.",
                suffix=".png",
            )
            os.close(descriptor)
            temporary_path = Path(temporary_name)
            try:
                pixmap = page.get_pixmap(matrix=matrix, alpha=False, colorspace=pymupdf.csRGB)
                pixmap.save(temporary_path)
                os.replace(temporary_path, page_path)
            finally:
                if temporary_path.exists():
                    temporary_path.unlink()

            rendered_width, rendered_height, ink_coverage = _page_metrics(page_path)
            page_records.append(
                PageManifest(
                    number=page_index + 1,
                    width_points=page.rect.width,
                    height_points=page.rect.height,
                    rotation_degrees=page.rotation,
                    rendered_width_px=rendered_width,
                    rendered_height_px=rendered_height,
                    ink_coverage=ink_coverage,
                    text_character_count=len(page.get_text("text")),
                    vector_drawing_count=len(page.get_drawings()),
                    blank_candidate=ink_coverage < 0.001,
                    image_sha256=_sha256(page_path),
                    render_file=page_path.name,
                )
            )
            page_paths.append(page_path)

        contact_sheet = output_dir / "contact-sheet.png"
        build_contact_sheet(
            page_paths,
            contact_sheet,
            title=f"{dataset_id} - revisao local",
        )
        manifest = PdfManifest(
            dataset_id=dataset_id,
            role=role,
            source_basename=source.name,
            source_sha256=_sha256(source),
            source_size_bytes=source.stat().st_size,
            page_count=document.page_count,
            encrypted=document.is_encrypted,
            rendered_at=datetime.now(UTC),
            renderer=f"PyMuPDF {pymupdf.VersionBind} @ {dpi} DPI",
            retention_notice="Artefato local temporário; não versionar e remover em até 7 dias.",
            pages=page_records,
        )
        manifest_path = output_dir / "manifest.json"
        serialized_manifest = json.dumps(
            manifest.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        _atomic_write_text(
            manifest_path,
            f"{serialized_manifest}\n",
        )
        return manifest, manifest_path
    finally:
        document.close()
