"""Execução idempotente de propostas CV para um dataset ingerido."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from croquito_worker.ingest import PdfManifest, build_contact_sheet
from croquito_worker.io_utils import atomic_write_text
from croquito_worker.vision import VisionProposalSet, write_proposal_artifacts


class VisionDatasetSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str
    page_count: int = Field(ge=1)
    proposal_count: int = Field(ge=0)
    counts_by_kind: dict[str, int]
    pages: list[dict[str, str | int]]
    contact_sheet_file: str
    safety_status: str


def propose_dataset(manifest_path: Path) -> tuple[VisionDatasetSummary, Path]:
    manifest_file = manifest_path.resolve(strict=True)
    manifest = PdfManifest.model_validate_json(manifest_file.read_text(encoding="utf-8"))
    dataset_dir = manifest_file.parent
    page_results: list[tuple[VisionProposalSet, Path, Path]] = []
    for page in manifest.pages:
        image_path = dataset_dir / page.render_file
        output_dir = dataset_dir / "vision" / f"page-{page.number:03d}"
        page_results.append(
            write_proposal_artifacts(
                image_path,
                output_dir,
                dataset_id=manifest.dataset_id,
                page_number=page.number,
            )
        )

    counts = {"line": 0, "circle": 0, "contour": 0}
    pages: list[dict[str, str | int]] = []
    for proposal_set, proposals_path, overlay_path in page_results:
        for proposal in proposal_set.proposals:
            counts[proposal.kind] += 1
        pages.append(
            {
                "page_number": proposal_set.page_number,
                "proposal_count": len(proposal_set.proposals),
                "limit_reached": ",".join(proposal_set.limit_reached),
                "proposals_file": str(proposals_path.relative_to(dataset_dir)),
                "overlay_file": str(overlay_path.relative_to(dataset_dir)),
            }
        )
    contact_sheet_path = dataset_dir / "vision" / "contact-sheet.png"
    build_contact_sheet(
        [overlay_path for _proposal_set, _proposals_path, overlay_path in page_results],
        contact_sheet_path,
        title=f"{manifest.dataset_id} - propostas CV nao exportaveis",
    )
    summary = VisionDatasetSummary(
        dataset_id=manifest.dataset_id,
        page_count=manifest.page_count,
        proposal_count=sum(counts.values()),
        counts_by_kind=counts,
        pages=pages,
        contact_sheet_file=str(contact_sheet_path.relative_to(dataset_dir)),
        safety_status="observational_only",
    )
    summary_path = dataset_dir / "vision" / "summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    serialized_summary = json.dumps(
        summary.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    atomic_write_text(summary_path, f"{serialized_summary}\n")
    return summary, summary_path
