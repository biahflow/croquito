"""Escrita da primeira revisão de leitura; evidência autorizada nunca é sobrescrita."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection, RowMapping

from croquitodxf_core.ids import new_uuid7
from croquitodxf_worker.association import AssociationSet
from croquitodxf_worker.rectangle_solver import RectangleSolveRequest
from croquitodxf_worker.review import ReviewPacket
from croquitodxf_worker.vision import VisionProposalSet


class ReviewAlreadyExistsError(RuntimeError):
    """The job already carries a review revision; seeding refuses to replace evidence."""


def json_expression(dialect_name: str, name: str) -> str:
    """Casts a bound JSON string to the column type expected by the dialect."""
    if dialect_name == "postgresql":
        return f"CAST(:{name} AS JSONB)"
    return f"json(:{name})"


def json_column(value: Any) -> Any:
    """Raw SQL returns JSON as text on SQLite and as a structure on PostgreSQL."""
    return json.loads(value) if isinstance(value, str) else value


def _json_parameter(parameters: dict[str, Any], dialect: str, name: str, value: Any) -> str:
    """Binds one JSON column, emitting the literal NULL when there is nothing to store."""
    if value is None:
        return "NULL"
    parameters[name] = json.dumps(value, ensure_ascii=False)
    return json_expression(dialect, name)


def insert_review_revision_v1(
    connection: Connection,
    *,
    tenant_id: str,
    job_id: str,
    packet: ReviewPacket,
    associations: AssociationSet,
    proposals: VisionProposalSet,
    evidence_refs: dict[str, Any],
    solver_request: RectangleSolveRequest | None,
    solver_blockers: list[str],
    required_blocker_codes: list[str],
    required_criteria_texts: dict[str, str],
    created_by: str,
) -> UUID:
    """Persists review revision 1 for a job, refusing to overwrite an existing one."""
    existing = connection.execute(
        text(
            "SELECT id FROM review_revisions "
            "WHERE job_id = :job_id AND tenant_id = :tenant_id LIMIT 1"
        ),
        {"job_id": job_id, "tenant_id": tenant_id},
    ).scalar_one_or_none()
    if existing is not None:
        raise ReviewAlreadyExistsError(job_id)

    dialect = connection.engine.dialect.name
    review_id = new_uuid7()
    parameters: dict[str, Any] = {
        "id": str(review_id),
        "tenant_id": tenant_id,
        "job_id": job_id,
        "packet": json.dumps(packet.model_dump(mode="json")),
        "associations": json.dumps(associations.model_dump(mode="json")),
        "proposals": json.dumps(proposals.model_dump(mode="json")),
        "selected_associations": json.dumps({}),
        "evidence_refs": json.dumps(evidence_refs),
        "solver_blockers": json.dumps(solver_blockers),
        "required_blockers": json.dumps(required_blocker_codes),
        "required_criteria_texts": json.dumps(required_criteria_texts, ensure_ascii=False),
        "created_by": created_by,
    }
    if solver_request is None:
        solver_request_expression = "NULL"
    else:
        solver_request_expression = json_expression(dialect, "solver_request")
        parameters["solver_request"] = json.dumps(solver_request.model_dump(mode="json"))

    connection.execute(
        text(
            "INSERT INTO review_revisions "
            "(id, tenant_id, job_id, version, parent_review_id, packet_json, "
            "associations_json, proposals_json, selected_associations_json, "
            "calibration_json, proposal_decisions_json, evidence_refs_json, "
            "solver_request_json, solver_blockers_json, required_blocker_codes_json, "
            "required_criteria_texts_json, scene_revision_id, created_by, created_at) "
            "VALUES (:id, :tenant_id, :job_id, 1, NULL, "
            f"{json_expression(dialect, 'packet')}, "
            f"{json_expression(dialect, 'associations')}, "
            f"{json_expression(dialect, 'proposals')}, "
            f"{json_expression(dialect, 'selected_associations')}, "
            "NULL, NULL, "
            f"{json_expression(dialect, 'evidence_refs')}, "
            f"{solver_request_expression}, "
            f"{json_expression(dialect, 'solver_blockers')}, "
            f"{json_expression(dialect, 'required_blockers')}, "
            f"{json_expression(dialect, 'required_criteria_texts')}, NULL, "
            ":created_by, CURRENT_TIMESTAMP)"
        ),
        parameters,
    )
    return review_id


def insert_next_review_revision(
    connection: Connection,
    *,
    tenant_id: str,
    job_id: str,
    base_review: RowMapping,
    review_id: UUID,
    created_by: str,
    proposals_json: dict[str, Any],
    associations_json: dict[str, Any],
    calibration_json: dict[str, Any] | None,
    scene_revision_id: str | None,
) -> None:
    """Persists `base_review.version + 1`, copying every other column from it verbatim.

    Used by `refresh-proposals`, which never touches decisions, the packet or evidence
    refs: only the proposal snapshot, the recomputed association candidates and, when a
    calibration no longer holds, the calibration and the scene it points at change.
    """
    dialect = connection.engine.dialect.name
    parameters: dict[str, Any] = {
        "id": str(review_id),
        "tenant_id": tenant_id,
        "job_id": job_id,
        "version": int(base_review["version"]) + 1,
        "parent_review_id": base_review["id"],
        "created_by": created_by,
        "scene_revision_id": scene_revision_id,
    }
    columns = {
        "packet_json": json_column(base_review["packet_json"]),
        "associations_json": associations_json,
        "proposals_json": proposals_json,
        "selected_associations_json": json_column(base_review["selected_associations_json"]),
        "calibration_json": calibration_json,
        "proposal_decisions_json": json_column(base_review["proposal_decisions_json"]),
        "trace_acceptance_json": json_column(base_review["trace_acceptance_json"]),
        "evidence_refs_json": json_column(base_review["evidence_refs_json"]),
        "solver_request_json": json_column(base_review["solver_request_json"]),
        "solver_blockers_json": json_column(base_review["solver_blockers_json"]),
        "required_blocker_codes_json": json_column(base_review["required_blocker_codes_json"]),
        "required_criteria_texts_json": json_column(base_review["required_criteria_texts_json"]),
    }
    expressions = {
        name: _json_parameter(parameters, dialect, name, value) for name, value in columns.items()
    }
    connection.execute(
        text(
            "INSERT INTO review_revisions "
            "(id, tenant_id, job_id, version, parent_review_id, packet_json, "
            "associations_json, proposals_json, selected_associations_json, "
            "calibration_json, proposal_decisions_json, trace_acceptance_json, "
            "evidence_refs_json, solver_request_json, solver_blockers_json, "
            "required_blocker_codes_json, required_criteria_texts_json, "
            "scene_revision_id, created_by, created_at) "
            "VALUES (:id, :tenant_id, :job_id, :version, :parent_review_id, "
            f"{expressions['packet_json']}, {expressions['associations_json']}, "
            f"{expressions['proposals_json']}, {expressions['selected_associations_json']}, "
            f"{expressions['calibration_json']}, {expressions['proposal_decisions_json']}, "
            f"{expressions['trace_acceptance_json']}, {expressions['evidence_refs_json']}, "
            f"{expressions['solver_request_json']}, {expressions['solver_blockers_json']}, "
            f"{expressions['required_blocker_codes_json']}, "
            f"{expressions['required_criteria_texts_json']}, "
            ":scene_revision_id, :created_by, CURRENT_TIMESTAMP)"
        ),
        parameters,
    )
