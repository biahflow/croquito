from pathlib import Path

import pymupdf

from croquitodxf_worker.ingest import ingest_pdf


def _create_synthetic_pdf(path: Path) -> None:
    document = pymupdf.open()
    page = document.new_page(width=595, height=842)
    page.draw_rect(pymupdf.Rect(80, 100, 510, 620), color=(0, 0, 0), width=2)
    page.insert_text((80, 75), "FIXTURE SINTETICA 31,95 m")
    document.save(path)
    document.close()


def test_ingest_renders_pdf_and_writes_manifest(tmp_path: Path) -> None:
    input_path = tmp_path / "fixture.pdf"
    _create_synthetic_pdf(input_path)

    manifest, manifest_path = ingest_pdf(
        input_path,
        tmp_path / "output",
        dataset_id="fixture-pdf-v1",
        role="test",
        dpi=120,
    )

    assert manifest.page_count == 1
    assert manifest.source_basename == "fixture.pdf"
    assert manifest.pages[0].blank_candidate is False
    assert manifest.pages[0].text_character_count > 0
    assert (manifest_path.parent / manifest.pages[0].render_file).is_file()
    assert (manifest_path.parent / "contact-sheet.png").is_file()
    assert manifest_path.is_file()
