import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest

from croquito_api.database import (
    Database,
    JobRecord,
    ProjectRecord,
    ReviewRevisionRecord,
    UploadRecord,
)
from croquito_worker.criteria import ScopeCriterion
from croquito_worker.local_queue import LocalWorkerSettings
from croquito_worker.review_seed import SeedInputs, SeedRefusedError, seed_review
from tests.bundles import write_seed_bundle
from tests.fakes import FakeObjectStore, synthetic_pdf

JOB_ID = UUID("00000000-0000-7000-8000-000000000901")
TENANT_ID = "tenant-seed"
CRITERION_TEXT = "Perímetro, linha central, círculo, áreas e gols são entidades CAD limpas."


def _seed_database(
    tmp_path: Path, *, source_sha256: str, status: str = "REVIEW_REQUIRED"
) -> tuple[Database, str]:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'seed.db'}"
    database = Database(database_url)
    database.create_schema()
    expires_at = datetime.now(UTC) + timedelta(days=7)
    with database.sessions.begin() as session:
        session.add(
            ProjectRecord(
                id="project-seed",
                tenant_id=TENANT_ID,
                name="Golden",
                default_unit="m",
                created_by="reviewer",
                expires_at=expires_at,
            )
        )
        session.add(
            UploadRecord(
                id="upload-seed",
                tenant_id=TENANT_ID,
                object_key=f"tenants/{TENANT_ID}/uploads/upload-seed/entrada.pdf",
                filename="entrada.pdf",
                content_type="application/pdf",
                size_bytes=1024,
                sha256=source_sha256,
            )
        )
        session.flush()
        session.add(
            JobRecord(
                id=str(JOB_ID),
                tenant_id=TENANT_ID,
                project_id="project-seed",
                upload_id="upload-seed",
                status=status,
                stage="PREVIEWING",
                expires_at=expires_at,
            )
        )
    return database, database_url


def _inputs(
    bundle: dict[str, Path],
    *,
    tenant_id: str = TENANT_ID,
    job_id: UUID = JOB_ID,
    required_criteria: tuple[ScopeCriterion, ...] = (
        ScopeCriterion(code="ACC_GUA_001", text=CRITERION_TEXT),
    ),
) -> SeedInputs:
    return SeedInputs(
        job_id=job_id,
        tenant_id=tenant_id,
        packet_path=bundle["packet"],
        associations_path=bundle["associations"],
        proposals_path=bundle["proposals"],
        rectangle_request_path=bundle["rectangle_request"],
        manifest_path=bundle["manifest"],
        image_path=bundle["image"],
        required_criteria=required_criteria,
        operator_id="tenant-admin-01",
    )


def _criteria_for(mutation: str) -> tuple[ScopeCriterion, ...]:
    """A semeadura é fronteira de confiança e revalida o critério.

    `model_construct` simula quem montou o objeto sem passar pelo contrato — é o único
    jeito de exercitar a guarda, já que `ScopeCriterion` recusa código e texto inválidos
    na construção normal.
    """
    if mutation == "invalid_criterion":
        return (ScopeCriterion.model_construct(code="acc-gua-001", text=None),)
    if mutation == "invalid_criterion_text":
        return (ScopeCriterion.model_construct(code="ACC_GUA_001", text="x" * 501),)
    return (ScopeCriterion(code="ACC_GUA_001", text=CRITERION_TEXT),)


def _settings(database_url: str) -> LocalWorkerSettings:
    return LocalWorkerSettings(
        database_url=database_url,
        queue_url="",
        aws_region="sa-east-1",
        aws_endpoint_url="http://localstack",
    )


def test_seed_binds_authorized_packet_and_records_honest_blockers(tmp_path: Path) -> None:
    source_sha256 = hashlib.sha256(synthetic_pdf()).hexdigest()
    database, database_url = _seed_database(tmp_path, source_sha256=source_sha256)
    bundle = write_seed_bundle(tmp_path / "bundle", source_sha256=source_sha256)
    storage = FakeObjectStore()

    result = seed_review(_inputs(bundle), _settings(database_url), s3_client=storage)

    assert result.review_version == 1
    assert result.readings == 3
    # Nothing is confirmed by the seed: every solver reading still needs a human.
    assert any(
        blocker.startswith("WIDTH_HUMAN_CONFIRMATION_REQUIRED") for blocker in result.blockers
    )
    assert len(storage.puts) == 1
    assert storage.puts[0]["ServerSideEncryption"] == "AES256"
    with database.sessions() as session:
        review = session.query(ReviewRevisionRecord).filter_by(job_id=str(JOB_ID)).one()
        assert review.version == 1
        assert review.solver_request_json is not None
        assert review.solver_request_json["feature_id"] == "campo-principal"
        assert review.required_blocker_codes_json == ["ACC_GUA_001"]
        # O texto do critério viaja junto do código desde a semeadura.
        assert review.required_criteria_texts_json == {"ACC_GUA_001": CRITERION_TEXT}
        assert review.scene_revision_id is None
        assert review.created_by == "seed-review:tenant-admin-01"
        assert all(reading["status"] == "proposed" for reading in review.packet_json["readings"])


def test_seed_refuses_a_second_run_and_leaves_evidence_untouched(tmp_path: Path) -> None:
    source_sha256 = hashlib.sha256(synthetic_pdf()).hexdigest()
    database, database_url = _seed_database(tmp_path, source_sha256=source_sha256)
    bundle = write_seed_bundle(tmp_path / "bundle", source_sha256=source_sha256)
    storage = FakeObjectStore()
    seed_review(_inputs(bundle), _settings(database_url), s3_client=storage)

    with pytest.raises(SeedRefusedError) as refusal:
        seed_review(_inputs(bundle), _settings(database_url), s3_client=storage)

    assert refusal.value.code == "REVIEW_ALREADY_EXISTS"
    assert len(storage.puts) == 1
    with database.sessions() as session:
        assert session.query(ReviewRevisionRecord).filter_by(job_id=str(JOB_ID)).count() == 1


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("unknown_job", "JOB_NOT_FOUND"),
        ("other_tenant", "JOB_NOT_FOUND"),
        ("job_failed", "JOB_NOT_REVIEWABLE"),
        ("upload_mismatch", "EVIDENCE_DOES_NOT_MATCH_UPLOAD"),
        ("image_mismatch", "IMAGE_DIGEST_MISMATCH"),
        ("decided_packet", "PACKET_CONTAINS_DECISIONS"),
        ("missing_candidate", "SOLVER_READING_HAS_NO_CANDIDATE"),
        ("invalid_criterion", "INVALID_CRITERION_CODE"),
        ("invalid_criterion_text", "INVALID_CRITERION_TEXT"),
    ],
)
def test_seed_refuses_every_divergence(tmp_path: Path, mutation: str, expected_code: str) -> None:
    source_sha256 = hashlib.sha256(synthetic_pdf()).hexdigest()
    database, database_url = _seed_database(
        tmp_path,
        source_sha256=source_sha256,
        status="FAILED" if mutation == "job_failed" else "REVIEW_REQUIRED",
    )
    bundle = write_seed_bundle(
        tmp_path / "bundle",
        source_sha256=source_sha256,
        decided=mutation == "decided_packet",
        drop_circle_candidate=mutation == "missing_candidate",
        manifest_source_sha256="d" * 64 if mutation == "upload_mismatch" else None,
    )
    if mutation == "image_mismatch":
        # Rewriting the page after the bundle was built breaks the digest chain.
        bundle["image"].write_bytes(bundle["image"].read_bytes() + b"\x00")
    storage = FakeObjectStore()

    with pytest.raises(SeedRefusedError) as refusal:
        seed_review(
            _inputs(
                bundle,
                tenant_id="tenant-other" if mutation == "other_tenant" else TENANT_ID,
                job_id=(
                    UUID("00000000-0000-7000-8000-000000000999")
                    if mutation == "unknown_job"
                    else JOB_ID
                ),
                required_criteria=_criteria_for(mutation),
            ),
            _settings(database_url),
            s3_client=storage,
        )

    assert refusal.value.code == expected_code
    assert storage.puts == []
    with database.sessions() as session:
        assert session.query(ReviewRevisionRecord).count() == 0
