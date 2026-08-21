"""Carga local de um pacote de revisão autorizado para uma sessão autenticada.

O comando não interpreta o documento, não chama provedores e não decide nada: ele apenas
liga evidência já preparada localmente a um job existente, recusando qualquer divergência
entre o pacote e o upload que o tenant realmente enviou.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

import boto3
from botocore.config import Config as BotoConfig
from sqlalchemy import create_engine, text

from croquito_worker.association import AssociationSet
from croquito_worker.criteria import (
    CRITERION_PATTERN,
    CRITERION_TEXT_MAX_CHARS,
    ScopeCriterion,
)
from croquito_worker.ingest import PdfManifest
from croquito_worker.local_queue import LocalWorkerSettings
from croquito_worker.rectangle_solver import RectangleSolveRequest, solve_rectangle
from croquito_worker.review import ReadingStatus, ReviewPacket, file_sha256
from croquito_worker.review_store import ReviewAlreadyExistsError, insert_review_revision_v1
from croquito_worker.vision import VisionProposalSet

__all__ = [
    # Reexportado: o padrão do código de critério nasceu aqui e segue importável daqui.
    "CRITERION_PATTERN",
    "SeedInputs",
    "SeedRefusedError",
    "SeedResult",
    "seed_review",
]

SEED_SAFETY_NOTE = (
    "Pacote autorizado carregado por seed local; nenhuma decisão humana foi fabricada."
)


class SeedRefusedError(RuntimeError):
    """A guardrail refused the seed; nothing was written and nothing was uploaded."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class SeedInputs:
    job_id: UUID
    tenant_id: str
    packet_path: Path
    associations_path: Path
    proposals_path: Path
    rectangle_request_path: Path
    manifest_path: Path
    image_path: Path
    required_criteria: tuple[ScopeCriterion, ...]
    operator_id: str


@dataclass(frozen=True, slots=True)
class SeedResult:
    job_id: UUID
    review_id: UUID
    review_version: int
    readings: int
    proposals: int
    blockers: tuple[str, ...]
    required_criteria: tuple[ScopeCriterion, ...]
    image_sha256: str
    source_image_key: str
    # Leituras que entraram sem toque humano (F-029, só com a dupla chave do ADR-0041
    # presente). Vazio é o padrão, e é o que a semeadura sempre produziu.
    auto_decided_reading_ids: tuple[str, ...] = ()


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_documents(
    inputs: SeedInputs,
) -> tuple[ReviewPacket, AssociationSet, VisionProposalSet, RectangleSolveRequest, PdfManifest]:
    packet = ReviewPacket.model_validate(_load(inputs.packet_path))
    associations = AssociationSet.model_validate(_load(inputs.associations_path))
    proposals = VisionProposalSet.model_validate(_load(inputs.proposals_path))
    request = RectangleSolveRequest.model_validate(_load(inputs.rectangle_request_path))
    manifest = PdfManifest.model_validate(_load(inputs.manifest_path))

    # A semeadura é fronteira de confiança: o contrato do critério é revalidado aqui,
    # mesmo que quem chamou já devesse tê-lo respeitado.
    for criterion in inputs.required_criteria:
        if not CRITERION_PATTERN.fullmatch(criterion.code):
            raise SeedRefusedError("INVALID_CRITERION_CODE")
        if criterion.text is not None and not 1 <= len(criterion.text) <= CRITERION_TEXT_MAX_CHARS:
            raise SeedRefusedError("INVALID_CRITERION_TEXT")

    dataset_ids = {packet.dataset_id, associations.dataset_id, proposals.dataset_id}
    page_numbers = {packet.page_number, associations.page_number, proposals.page_number}
    if len(dataset_ids) != 1 or len(page_numbers) != 1:
        raise SeedRefusedError("DATASET_MISMATCH")

    image_digest = file_sha256(inputs.image_path)
    page = next((item for item in manifest.pages if item.number == packet.page_number), None)
    if page is None:
        raise SeedRefusedError("DATASET_MISMATCH")
    digests = {
        packet.image_sha256,
        associations.image_sha256,
        proposals.image_sha256,
        page.image_sha256,
    }
    if digests != {image_digest}:
        raise SeedRefusedError("IMAGE_DIGEST_MISMATCH")

    if any(
        reading.decision is not None
        or reading.status in {ReadingStatus.CONFIRMED, ReadingStatus.REJECTED}
        for reading in packet.readings
    ):
        raise SeedRefusedError("PACKET_CONTAINS_DECISIONS")

    reading_ids = {reading.id for reading in packet.readings}
    proposal_ids = {proposal.id for proposal in proposals.proposals}
    for candidate in associations.candidates:
        if candidate.reading_id not in reading_ids or candidate.proposal_id not in proposal_ids:
            raise SeedRefusedError("UNKNOWN_ASSOCIATION_REFERENCE")

    solver_reading_ids = [
        identifier
        for identifier in (
            request.width_reading_id,
            request.height_reading_id,
            request.centre_circle_reading_id,
        )
        if identifier is not None
    ]
    if any(identifier not in reading_ids for identifier in solver_reading_ids):
        raise SeedRefusedError("SOLVER_READING_NOT_IN_PACKET")
    associated_readings = {candidate.reading_id for candidate in associations.candidates}
    if any(identifier not in associated_readings for identifier in solver_reading_ids):
        raise SeedRefusedError("SOLVER_READING_HAS_NO_CANDIDATE")

    return packet, associations, proposals, request, manifest


def seed_review(
    inputs: SeedInputs,
    settings: LocalWorkerSettings,
    *,
    s3_client: Any | None = None,
) -> SeedResult:
    """Binds an authorized review packet to an existing job, refusing every divergence."""
    packet, associations, proposals, request, manifest = _validate_documents(inputs)
    engine = create_engine(settings.database_url)
    with engine.connect() as connection:
        job = (
            connection.execute(
                text(
                    "SELECT jobs.status, uploads.sha256 AS upload_sha256 FROM jobs "
                    "JOIN uploads ON uploads.id = jobs.upload_id "
                    "WHERE jobs.id = :job_id AND jobs.tenant_id = :tenant_id "
                    "AND uploads.tenant_id = :tenant_id"
                ),
                {"job_id": str(inputs.job_id), "tenant_id": inputs.tenant_id},
            )
            .mappings()
            .one_or_none()
        )
        if job is None:
            raise SeedRefusedError("JOB_NOT_FOUND")
        if job["status"] != "REVIEW_REQUIRED":
            raise SeedRefusedError("JOB_NOT_REVIEWABLE")
        if job["upload_sha256"] != manifest.source_sha256:
            raise SeedRefusedError("EVIDENCE_DOES_NOT_MATCH_UPLOAD")
        existing = connection.execute(
            text(
                "SELECT id FROM review_revisions "
                "WHERE job_id = :job_id AND tenant_id = :tenant_id LIMIT 1"
            ),
            {"job_id": str(inputs.job_id), "tenant_id": inputs.tenant_id},
        ).scalar_one_or_none()
        if existing is not None:
            raise SeedRefusedError("REVIEW_ALREADY_EXISTS")

    seeded_packet = packet.model_copy(
        update={"safety_notes": [*packet.safety_notes, SEED_SAFETY_NOTE]}
    )
    # Dry run without associations: records the honest blockers a professional still has to clear.
    dry_run = solve_rectangle(seeded_packet, request, confirmed_associations={})

    source_image_key = f"tenants/{inputs.tenant_id}/jobs/{inputs.job_id}/review/source.png"
    storage: Any = s3_client or boto3.client(
        "s3",
        region_name=settings.aws_region,
        endpoint_url=settings.aws_endpoint_url,
        # Mesma configuração do client da API: interop S3 do GCS exige path-style.
        config=BotoConfig(signature_version="s3v4", s3={"addressing_style": "path"}),
    )
    with inputs.image_path.open("rb") as image_stream:
        storage.put_object(
            Bucket=settings.artifact_bucket,
            Key=source_image_key,
            Body=image_stream,
            ContentType="image/png",
            **({"ServerSideEncryption": "AES256"} if settings.storage_sse_enabled else {}),
        )

    with engine.begin() as connection:
        try:
            seeded = insert_review_revision_v1(
                connection,
                tenant_id=inputs.tenant_id,
                job_id=str(inputs.job_id),
                packet=seeded_packet,
                associations=associations,
                proposals=proposals,
                evidence_refs={"source_image_key": source_image_key},
                solver_request=request,
                solver_blockers=list(dry_run.blockers),
                required_blocker_codes=[criterion.code for criterion in inputs.required_criteria],
                required_criteria_texts={
                    criterion.code: criterion.text
                    for criterion in inputs.required_criteria
                    if criterion.text is not None
                },
                created_by=f"seed-review:{inputs.operator_id}",
            )
        except ReviewAlreadyExistsError as error:
            raise SeedRefusedError("REVIEW_ALREADY_EXISTS") from error

    # Os blockers relatados são os PERSISTIDOS, não os do ensaio: com o modo automático
    # ligado, a gravação decide leituras e o ensaio acima passa a descrever um estado que
    # não é o da revisão. Com o modo desligado os dois são o mesmo objeto de conteúdo.
    return SeedResult(
        job_id=inputs.job_id,
        review_id=seeded.review_id,
        review_version=1,
        readings=len(seeded_packet.readings),
        proposals=len(proposals.proposals),
        blockers=seeded.solver_blockers,
        required_criteria=inputs.required_criteria,
        image_sha256=packet.image_sha256,
        source_image_key=source_image_key,
        auto_decided_reading_ids=tuple(decision.reading_id for decision in seeded.auto_decisions),
    )
