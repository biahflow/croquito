"""Extrator fixture da legenda: lê a prancha sintética, e só ela.

O M3 é offline. A extração real de uma prancha de cliente é marco futuro, com provider,
entitlement contratual e teto de gasto — nada disso existe aqui. Por isso este extrator
não recebe caminho de PDF: ele recebe o `PlateArtifacts` que `render_synthetic_plate`
acabou de devolver, com o gabarito da legenda que ele mesmo desenhou. Aceitar um arquivo
qualquer seria fabricar observação sobre documento real, que é exatamente o que a fixture
existe para não fazer.

O que sai daqui é observação: todo item nasce `proposed` (ou `ambiguous`, quando a
quantidade não é legível) e só vira quantitativo por `apply_takeoff_decisions`.
"""

from __future__ import annotations

import hashlib
from typing import Final

from croquito_valuation.catalog import file_sha256, normalize_unit
from croquito_valuation.errors import ValuationValidationError
from croquito_valuation.takeoff import (
    PlateEvidence,
    TakeoffItem,
    TakeoffItemStatus,
    TakeoffPacket,
)
from croquito_worker.valuation.plate import PLATE_EXTRACTOR_VERSION, PlateArtifacts

FIXTURE_EXTRACTOR: Final = "fixture_legend_extractor"
FIXTURE_EXTRACTOR_VERSION: Final = PLATE_EXTRACTOR_VERSION
"""A versão do extrator é a versão do layout que ele sabe ler: gabarito e desenho nascem
da mesma constante, então versioná-los separadamente só criaria oportunidade de mentira."""

FIXTURE_SAFETY_NOTES: Final[tuple[str, ...]] = (
    "Extração fixture sintética; nenhuma prancha de cliente foi lida.",
    "Decisão do orçamentista obrigatória antes de qualquer quantitativo.",
)


def takeoff_item_id(plate_id: str, label: str) -> str:
    """Id determinístico do item: a mesma prancha e o mesmo rótulo dão o mesmo id."""
    digest = hashlib.sha256(f"{plate_id}:{label}".encode()).hexdigest()[:16]
    return f"ti_{digest}"


def _verify_artifacts(artifacts: PlateArtifacts) -> None:
    """Confere que os arquivos ainda são os que o gerador produziu.

    O digest do PDF do pymupdf não é estável entre execuções, então ele não pode ser
    comparado com uma constante; o que se compara é o arquivo em disco com o digest
    calculado no momento da geração. Arquivo trocado ou editado entre gerar e extrair
    recusa em vez de virar item de takeoff.
    """
    divergent = {
        name: {"expected": expected, "actual": actual}
        for name, expected, actual in (
            ("pdf", artifacts.pdf_sha256, file_sha256(artifacts.pdf_path)),
            ("image", artifacts.image_sha256, file_sha256(artifacts.image_path)),
        )
        if expected != actual
    }
    if divergent:
        raise ValuationValidationError(
            "TAKEOFF_FIXTURE_ARTIFACT_MISMATCH",
            "artefato da prancha sintética diverge do digest registrado na geração",
            {"artifacts": divergent},
        )


def extract_takeoff_fixture(artifacts: PlateArtifacts) -> TakeoffPacket:
    """Constrói o pacote de takeoff da prancha sintética recém-gerada."""
    _verify_artifacts(artifacts)
    items: list[TakeoffItem] = []
    for entry in artifacts.rows:
        row = entry.row
        if entry.bbox.right > artifacts.image_width or entry.bbox.bottom > artifacts.image_height:
            raise ValuationValidationError(
                "TAKEOFF_FIXTURE_BBOX_OUTSIDE_IMAGE",
                "bbox da linha da legenda cai fora do render da prancha",
                {"label": row.label, "bbox": entry.bbox.model_dump()},
            )
        items.append(
            TakeoffItem(
                id=takeoff_item_id(artifacts.plate_id, row.label),
                evidence=PlateEvidence(
                    plate_id=artifacts.plate_id,
                    page_number=artifacts.page_number,
                    image_sha256=artifacts.image_sha256,
                    bbox=entry.bbox,
                ),
                raw_text=row.as_written(),
                label=row.label,
                quantity=row.quantity,
                unit=normalize_unit(row.unit),
                source="legend_extraction",
                extractor=FIXTURE_EXTRACTOR,
                extractor_version=FIXTURE_EXTRACTOR_VERSION,
                note=row.note,
                status=(
                    TakeoffItemStatus.AMBIGUOUS
                    if row.quantity is None
                    else TakeoffItemStatus.PROPOSED
                ),
            )
        )
    return TakeoffPacket(
        plate_id=artifacts.plate_id,
        page_number=artifacts.page_number,
        image_sha256=artifacts.image_sha256,
        source_pdf_sha256=artifacts.pdf_sha256,
        items=items,
        safety_notes=list(FIXTURE_SAFETY_NOTES),
    )
