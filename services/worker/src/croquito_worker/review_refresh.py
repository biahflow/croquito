"""Recomputa o snapshot de propostas de visão de um job vivo, sem tocar decisões humanas.

O registro fino de propostas (handoff R1) produz geometria melhor sob os MESMOS ids
`vp_…`. Este módulo é o único caminho para essa geometria entrar num job que já tem
revisão, decisões e talvez calibração: ele nunca sobrescreve a revisão vigente — sempre
cria uma nova, com o packet e as decisões copiados byte a byte, os candidatos de
associação recomputados contra a evidência vigente e a calibração revalidada pela mesma
regra da API (`croquito_worker.proposal_calibration.revalidate_calibration`). Uma
calibração que não sobrevive à deriva nunca reprojeta a entidade já aceita: a cena
corrente ganha a issue crítica `CALIBRATION_SUPERSEDED` em vez disso.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import create_engine, text

from croquito_core.ids import new_uuid7
from croquito_core.models import Entity, Issue, IssueSeverity, SceneRevision
from croquito_worker.association import associate_readings
from croquito_worker.local_queue import LocalWorkerSettings
from croquito_worker.proposal_calibration import (
    HUMAN_ACCEPTED_PROPOSAL_SOURCE_TYPE,
    revalidate_calibration,
)
from croquito_worker.review import ReviewPacket, file_sha256
from croquito_worker.review_store import (
    insert_next_review_revision,
    json_column,
    json_expression,
)
from croquito_worker.vision import VisionProposalSet

__all__ = [
    "ProposalRefreshDelta",
    "RefreshInputs",
    "RefreshRefusedError",
    "RefreshResult",
    "refresh_proposals",
]

CALIBRATION_SUPERSEDED_MESSAGE = (
    "A calibração não é mais válida para a cena atual; recalibre antes de exportar."
)


class RefreshRefusedError(RuntimeError):
    """A guardrail refused the refresh; nothing was written."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class RefreshInputs:
    job_id: UUID
    tenant_id: str
    proposals_path: Path
    image_path: Path
    operator_id: str


@dataclass(frozen=True, slots=True)
class ProposalRefreshDelta:
    proposal_id: str
    quality_score_before: float
    quality_score_after: float


@dataclass(frozen=True, slots=True)
class RefreshResult:
    job_id: UUID
    review_id: UUID
    review_version_before: int
    review_version_after: int
    proposals: int
    deltas: tuple[ProposalRefreshDelta, ...]
    calibration_status: Literal["kept", "superseded", "absent"]


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _human_accepted_entities(scene: SceneRevision) -> list[Entity]:
    """Entities a professional accepted from a pixel proposal; refresh never rewrites them."""
    return [
        entity
        for entity in scene.entities
        if entity.provenance is not None
        and entity.provenance.source_type == HUMAN_ACCEPTED_PROPOSAL_SOURCE_TYPE
    ]


def _validate_proposals(inputs: RefreshInputs) -> VisionProposalSet:
    """Pure, file-only validation: loads the refined snapshot and checks its own digest."""
    proposals = VisionProposalSet.model_validate(_load(inputs.proposals_path))
    image_digest = file_sha256(inputs.image_path)
    if image_digest != proposals.image_sha256:
        raise RefreshRefusedError("IMAGE_DIGEST_MISMATCH")
    return proposals


def refresh_proposals(inputs: RefreshInputs, settings: LocalWorkerSettings) -> RefreshResult:
    """Recomputes a live job's proposal snapshot, refusing every divergence fail-closed."""
    proposals = _validate_proposals(inputs)

    engine = create_engine(settings.database_url)
    with engine.connect() as connection:
        job = connection.execute(
            text("SELECT id FROM jobs WHERE id = :job_id AND tenant_id = :tenant_id"),
            {"job_id": str(inputs.job_id), "tenant_id": inputs.tenant_id},
        ).scalar_one_or_none()
        if job is None:
            raise RefreshRefusedError("JOB_NOT_FOUND")

        current = (
            connection.execute(
                text(
                    "SELECT id, version, packet_json, associations_json, proposals_json, "
                    "selected_associations_json, declared_chains_json, calibration_json, "
                    "proposal_decisions_json, "
                    "trace_acceptance_json, evidence_refs_json, solver_request_json, "
                    "solver_blockers_json, required_blocker_codes_json, "
                    "required_criteria_texts_json, scene_revision_id "
                    "FROM review_revisions WHERE job_id = :job_id AND tenant_id = :tenant_id "
                    "ORDER BY version DESC LIMIT 1"
                ),
                {"job_id": str(inputs.job_id), "tenant_id": inputs.tenant_id},
            )
            .mappings()
            .one_or_none()
        )
        if current is None or current["proposals_json"] is None:
            raise RefreshRefusedError("REVIEW_MISSING")

        current_proposals = VisionProposalSet.model_validate(json_column(current["proposals_json"]))
        if proposals.image_sha256 != current_proposals.image_sha256:
            raise RefreshRefusedError("IMAGE_DIGEST_MISMATCH")
        if (
            proposals.dataset_id != current_proposals.dataset_id
            or proposals.page_number != current_proposals.page_number
        ):
            raise RefreshRefusedError("DATASET_MISMATCH")

        current_ids = [proposal.id for proposal in current_proposals.proposals]
        new_ids = [proposal.id for proposal in proposals.proposals]
        if len(set(new_ids)) != len(new_ids) or set(new_ids) != set(current_ids):
            raise RefreshRefusedError("PROPOSAL_SET_MISMATCH")

        if proposals.model_dump(mode="json") == current_proposals.model_dump(mode="json"):
            raise RefreshRefusedError("REFRESH_ALREADY_APPLIED")

        packet = ReviewPacket.model_validate(json_column(current["packet_json"]))
        new_associations = associate_readings(packet, proposals)

        selected_associations: dict[str, str] = dict(
            json_column(current["selected_associations_json"]) or {}
        )
        candidate_pairs = {
            (candidate.reading_id, candidate.proposal_id)
            for candidate in new_associations.candidates
        }
        for reading_id, proposal_id in selected_associations.items():
            if (reading_id, proposal_id) not in candidate_pairs:
                raise RefreshRefusedError("REFRESH_BREAKS_SELECTED_ASSOCIATION")

        current_calibration_json = json_column(current["calibration_json"])
        next_calibration_json: dict[str, Any] | None = None
        next_scene_revision_id: str | None = current["scene_revision_id"]
        calibration_status: Literal["kept", "superseded", "absent"] = "absent"
        new_scene: SceneRevision | None = None
        parent_scene_id: str | None = None

        if current_calibration_json is not None:
            scene_row = (
                connection.execute(
                    text(
                        "SELECT id, version, scene FROM scene_revisions "
                        "WHERE id = :scene_id AND tenant_id = :tenant_id AND job_id = :job_id"
                    ),
                    {
                        "scene_id": current["scene_revision_id"],
                        "tenant_id": inputs.tenant_id,
                        "job_id": str(inputs.job_id),
                    },
                )
                .mappings()
                .one_or_none()
            )
            if scene_row is None:
                # Invariante quebrado: calibração ativa sem cena correspondente. Uma
                # calibração nunca sobrevive sem a cena que ela mede.
                calibration_status = "superseded"
            else:
                scene = SceneRevision.model_validate(json_column(scene_row["scene"]))
                next_calibration_json = revalidate_calibration(
                    current_calibration_json,
                    proposals_json=proposals.model_dump(mode="json"),
                    scene=scene,
                    scene_record_id=scene_row["id"],
                )
                if next_calibration_json is not None:
                    calibration_status = "kept"
                else:
                    calibration_status = "superseded"
                    preserved = _human_accepted_entities(scene)
                    if preserved:
                        # Nunca reprojeta a entidade aceita: ela viaja intacta para a
                        # cena nova, que só ganha a issue crítica que trava o export.
                        new_scene = SceneRevision.model_validate(
                            {
                                **scene.model_dump(mode="json"),
                                "id": str(new_uuid7()),
                                "version": scene.version + 1,
                                "issues": [
                                    *[issue.model_dump(mode="json") for issue in scene.issues],
                                    Issue(
                                        code="CALIBRATION_SUPERSEDED",
                                        severity=IssueSeverity.CRITICAL,
                                        message=CALIBRATION_SUPERSEDED_MESSAGE,
                                        entity_ids=[entity.id for entity in preserved],
                                    ).model_dump(mode="json"),
                                ],
                            }
                        )
                        parent_scene_id = scene_row["id"]
                        next_scene_revision_id = str(new_scene.id)

        review_id = new_uuid7()
        current_by_id = {proposal.id: proposal for proposal in current_proposals.proposals}
        deltas = tuple(
            sorted(
                (
                    ProposalRefreshDelta(
                        proposal_id=proposal.id,
                        quality_score_before=current_by_id[proposal.id].quality_score,
                        quality_score_after=proposal.quality_score,
                    )
                    for proposal in proposals.proposals
                ),
                key=lambda delta: delta.proposal_id,
            )
        )

        created_by = f"refresh-proposals:{inputs.operator_id}"
        with engine.begin() as write_connection:
            if new_scene is not None:
                dialect = write_connection.engine.dialect.name
                write_connection.execute(
                    text(
                        "INSERT INTO scene_revisions "
                        "(id, tenant_id, job_id, version, parent_revision_id, scene, "
                        "created_by, created_at) VALUES "
                        "(:id, :tenant_id, :job_id, :version, :parent_revision_id, "
                        f"{json_expression(dialect, 'scene')}, "
                        ":created_by, CURRENT_TIMESTAMP)"
                    ),
                    {
                        "id": str(new_scene.id),
                        "tenant_id": inputs.tenant_id,
                        "job_id": str(inputs.job_id),
                        "version": new_scene.version,
                        "parent_revision_id": parent_scene_id,
                        "scene": json.dumps(new_scene.model_dump(mode="json"), ensure_ascii=False),
                        "created_by": created_by,
                    },
                )
            insert_next_review_revision(
                write_connection,
                tenant_id=inputs.tenant_id,
                job_id=str(inputs.job_id),
                base_review=current,
                review_id=review_id,
                created_by=created_by,
                proposals_json=proposals.model_dump(mode="json"),
                associations_json=new_associations.model_dump(mode="json"),
                calibration_json=next_calibration_json,
                scene_revision_id=next_scene_revision_id,
            )

    return RefreshResult(
        job_id=inputs.job_id,
        review_id=review_id,
        review_version_before=int(current["version"]),
        review_version_after=int(current["version"]) + 1,
        proposals=len(proposals.proposals),
        deltas=deltas,
        calibration_status=calibration_status,
    )
