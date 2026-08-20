"""Testes do comando `refresh-proposals`: matriz de recusa, recompute e calibração."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from PIL import Image
from pydantic import BaseModel, ValidationError

from croquito_api.database import (
    Database,
    JobRecord,
    ProjectRecord,
    ReviewRevisionRecord,
    RevisionRecord,
    UploadRecord,
)
from croquito_core.ids import new_uuid7
from croquito_core.models import (
    CircleGeometry,
    Entity,
    EntityKind,
    LayerName,
    LineGeometry,
    Point2D,
    Precision,
    Provenance,
    SceneRevision,
)
from croquito_worker.association import AssociationCandidate, AssociationSet
from croquito_worker.ingest import PageManifest, PdfManifest
from croquito_worker.local_queue import LocalWorkerSettings
from croquito_worker.proposal_calibration import (
    HUMAN_ACCEPTED_PROPOSAL_SOURCE_TYPE,
    CalibrationAnchor,
    calibrate_similarity,
    matrix_of,
)
from croquito_worker.rectangle_solver import RectangleSolveRequest
from croquito_worker.review import (
    DimensionReading,
    EvidenceRegion,
    PixelBox,
    ReadingStatus,
    ReviewPacket,
)
from croquito_worker.review_refresh import RefreshInputs, RefreshRefusedError, refresh_proposals
from croquito_worker.review_seed import SeedInputs, seed_review
from croquito_worker.vision import PixelLine, PixelPoint, VisionProposal, VisionProposalSet
from tests.fakes import FakeObjectStore, synthetic_pdf

JOB_ID = UUID("00000000-0000-7000-8000-000000001001")
TENANT_ID = "tenant-refresh"
DATASET_ID = "refresh-fixture-v1"

WIDTH_READING_ID = "rd_" + "a" * 16
HEIGHT_READING_ID = "rd_" + "b" * 16
WIDTH_PROPOSAL_ID = "vp_" + "a" * 16
HEIGHT_PROPOSAL_ID = "vp_" + "b" * 16

HORIZONTAL_ENTITY_ID = UUID("00000000-0000-7000-8000-000000001002")
VERTICAL_ENTITY_ID = UUID("00000000-0000-7000-8000-000000001003")
ACCEPTED_ENTITY_ID = UUID("00000000-0000-7000-8000-000000001004")


# --- fixtures: packet, propostas, associações, manifesto, request ----------------------


def _packet(*, digest: str) -> ReviewPacket:
    return ReviewPacket(
        dataset_id=DATASET_ID,
        page_number=1,
        image_sha256=digest,
        readings=[
            DimensionReading(
                id=WIDTH_READING_ID,
                evidence=EvidenceRegion(
                    dataset_id=DATASET_ID,
                    page_number=1,
                    image_sha256=digest,
                    bbox=PixelBox(left=0, top=0, right=10, bottom=4),
                ),
                raw_text="3,00 m",
                value_si=Decimal("3.00"),
                unit="m",
                kind="width",
                written_decimals=2,
                target_hint="campo principal",
                extractor="fixture",
                extractor_version="v1",
                status=ReadingStatus.PROPOSED,
            ),
            DimensionReading(
                id=HEIGHT_READING_ID,
                evidence=EvidenceRegion(
                    dataset_id=DATASET_ID,
                    page_number=1,
                    image_sha256=digest,
                    bbox=PixelBox(left=0, top=16, right=4, bottom=24),
                ),
                raw_text="2,00 m",
                value_si=Decimal("2.00"),
                unit="m",
                kind="height",
                written_decimals=2,
                target_hint="campo principal",
                extractor="fixture",
                extractor_version="v1",
                status=ReadingStatus.PROPOSED,
            ),
        ],
        safety_notes=["fixture local", "revisão humana obrigatória"],
    )


def _proposals(*, digest: str) -> VisionProposalSet:
    return VisionProposalSet(
        dataset_id=DATASET_ID,
        page_number=1,
        image_sha256=digest,
        image_width_px=40,
        image_height_px=30,
        configured_limits={"line": 80, "circle": 16, "contour": 16},
        limit_reached=[],
        proposals=[
            VisionProposal(
                id=WIDTH_PROPOSAL_ID,
                kind="line",
                geometry=PixelLine(start=PixelPoint(x=0, y=0), end=PixelPoint(x=30, y=0)),
                algorithm="fixture",
                quality_score=0.9,
            ),
            VisionProposal(
                id=HEIGHT_PROPOSAL_ID,
                kind="line",
                geometry=PixelLine(start=PixelPoint(x=0, y=0), end=PixelPoint(x=0, y=20)),
                algorithm="fixture",
                quality_score=0.9,
            ),
        ],
        safety_notes=["fixture", "pixels", "não exportável"],
    )


def _associations(*, digest: str) -> AssociationSet:
    return AssociationSet(
        dataset_id=DATASET_ID,
        page_number=1,
        image_sha256=digest,
        candidates=[
            AssociationCandidate(
                reading_id=WIDTH_READING_ID,
                proposal_id=WIDTH_PROPOSAL_ID,
                proposal_kind="line",
                relation="nearest_geometry",
                pixel_distance=2,
                proximity_score=0.9,
                visual_quality_score=0.9,
            ),
            AssociationCandidate(
                reading_id=HEIGHT_READING_ID,
                proposal_id=HEIGHT_PROPOSAL_ID,
                proposal_kind="line",
                relation="nearest_geometry",
                pixel_distance=2,
                proximity_score=0.9,
                visual_quality_score=0.9,
            ),
        ],
        unassociated_reading_ids=[],
        safety_notes=["pixels", "não confirma", "não exporta"],
    )


def _manifest(*, digest: str, source_sha256: str) -> PdfManifest:
    return PdfManifest(
        dataset_id=DATASET_ID,
        role="golden",
        source_basename="levantamento.pdf",
        source_sha256=source_sha256,
        source_size_bytes=1024,
        page_count=1,
        encrypted=False,
        rendered_at=datetime.now(UTC),
        renderer="pymupdf",
        retention_notice="Retenção local de sete dias.",
        pages=[
            PageManifest(
                number=1,
                width_points=595.0,
                height_points=842.0,
                rotation_degrees=0,
                rendered_width_px=40,
                rendered_height_px=30,
                ink_coverage=0.1,
                text_character_count=10,
                vector_drawing_count=2,
                blank_candidate=False,
                image_sha256=digest,
                render_file="page-001.png",
            )
        ],
    )


def _request() -> RectangleSolveRequest:
    return RectangleSolveRequest(
        feature_id="campo-refresh",
        width_reading_id=WIDTH_READING_ID,
        height_reading_id=HEIGHT_READING_ID,
        centre_circle_reading_id=None,
        require_centre_circle=False,
    )


def _write_json(path: Path, payload: BaseModel) -> Path:
    path.write_text(
        json.dumps(payload.model_dump(mode="json"), ensure_ascii=False), encoding="utf-8"
    )
    return path


def _write_bundle(directory: Path, *, source_sha256: str) -> tuple[dict[str, Path], str]:
    directory.mkdir(parents=True, exist_ok=True)
    image_path = directory / "page-001.png"
    Image.new("RGB", (40, 30), "white").save(image_path)
    digest = hashlib.sha256(image_path.read_bytes()).hexdigest()
    paths = {
        "image": image_path,
        "packet": _write_json(directory / "packet.json", _packet(digest=digest)),
        "associations": _write_json(directory / "associations.json", _associations(digest=digest)),
        "proposals": _write_json(directory / "proposals.json", _proposals(digest=digest)),
        "manifest": _write_json(
            directory / "manifest.json", _manifest(digest=digest, source_sha256=source_sha256)
        ),
        "rectangle_request": _write_json(directory / "request.json", _request()),
    }
    return paths, digest


def _refined_proposals(base: VisionProposalSet, mutation: str) -> VisionProposalSet:
    """Refined vp_… snapshot: same ids as `base`, only geometry/quality_score may move."""
    proposals = list(base.proposals)
    if mutation == "unchanged":
        return base
    if mutation == "quality":
        proposals[1] = proposals[1].model_copy(update={"quality_score": 0.99})
        return base.model_copy(update={"proposals": proposals})
    if mutation == "widen_width_line":
        proposals[0] = proposals[0].model_copy(
            update={"geometry": PixelLine(start=PixelPoint(x=0, y=0), end=PixelPoint(x=40, y=0))}
        )
        return base.model_copy(update={"proposals": proposals})
    if mutation == "break_association":
        proposals[0] = proposals[0].model_copy(
            update={
                "geometry": PixelLine(
                    start=PixelPoint(x=1000, y=1000), end=PixelPoint(x=1030, y=1000)
                )
            }
        )
        return base.model_copy(update={"proposals": proposals})
    if mutation == "dataset_mismatch":
        return base.model_copy(update={"page_number": 2})
    if mutation == "image_mismatch":
        return base.model_copy(update={"image_sha256": "b" * 64})
    if mutation == "extra_proposal":
        proposals.append(proposals[1].model_copy(update={"id": "vp_" + "c" * 16}))
        return base.model_copy(update={"proposals": proposals})
    if mutation == "missing_proposal":
        return base.model_copy(update={"proposals": proposals[:1]})
    if mutation == "duplicate_proposal":
        proposals.append(proposals[0])
        return base.model_copy(update={"proposals": proposals})
    raise ValueError(mutation)


# --- fixtures: banco e sessão de semeadura ----------------------------------------------


def _seed_database(tmp_path: Path, *, source_sha256: str) -> tuple[Database, str]:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'refresh.db'}"
    database = Database(database_url)
    database.create_schema()
    expires_at = datetime.now(UTC) + timedelta(days=7)
    with database.sessions.begin() as session:
        session.add(
            ProjectRecord(
                id="project-refresh",
                tenant_id=TENANT_ID,
                name="Golden",
                default_unit="m",
                created_by="reviewer",
                expires_at=expires_at,
            )
        )
        session.add(
            UploadRecord(
                id="upload-refresh",
                tenant_id=TENANT_ID,
                object_key=f"tenants/{TENANT_ID}/uploads/upload-refresh/entrada.pdf",
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
                project_id="project-refresh",
                upload_id="upload-refresh",
                status="REVIEW_REQUIRED",
                stage="PREVIEWING",
                expires_at=expires_at,
            )
        )
    return database, database_url


def _settings(database_url: str) -> LocalWorkerSettings:
    return LocalWorkerSettings(
        database_url=database_url,
        queue_url="",
        aws_region="sa-east-1",
        aws_endpoint_url="http://localstack",
    )


def _seed_v1(tmp_path: Path) -> tuple[Database, str, dict[str, Path], str]:
    """Seeds job + review v1 through the real `seed_review` path."""
    source_sha256 = hashlib.sha256(synthetic_pdf()).hexdigest()
    database, database_url = _seed_database(tmp_path, source_sha256=source_sha256)
    bundle, digest = _write_bundle(tmp_path / "bundle", source_sha256=source_sha256)
    seed_review(
        SeedInputs(
            job_id=JOB_ID,
            tenant_id=TENANT_ID,
            packet_path=bundle["packet"],
            associations_path=bundle["associations"],
            proposals_path=bundle["proposals"],
            rectangle_request_path=bundle["rectangle_request"],
            manifest_path=bundle["manifest"],
            image_path=bundle["image"],
            required_criteria=(),
            operator_id="tenant-admin-01",
        ),
        _settings(database_url),
        s3_client=FakeObjectStore(),
    )
    return database, database_url, bundle, digest


# --- sucesso: candidatos recomputados, packet e decisões intactas ----------------------


def test_refresh_recomputes_associations_and_bumps_review_version(tmp_path: Path) -> None:
    database, database_url, bundle, digest = _seed_v1(tmp_path)

    refined = _refined_proposals(_proposals(digest=digest), "quality")
    refined_path = _write_json(tmp_path / "refined.json", refined)

    result = refresh_proposals(
        RefreshInputs(
            job_id=JOB_ID,
            tenant_id=TENANT_ID,
            proposals_path=refined_path,
            image_path=bundle["image"],
            operator_id="tenant-admin-02",
        ),
        _settings(database_url),
    )

    assert result.review_version_before == 1
    assert result.review_version_after == 2
    assert result.proposals == 2
    assert result.calibration_status == "absent"
    delta_by_id = {delta.proposal_id: delta for delta in result.deltas}
    assert delta_by_id[HEIGHT_PROPOSAL_ID].quality_score_before == pytest.approx(0.9)
    assert delta_by_id[HEIGHT_PROPOSAL_ID].quality_score_after == pytest.approx(0.99)
    assert delta_by_id[WIDTH_PROPOSAL_ID].quality_score_before == pytest.approx(0.9)
    assert delta_by_id[WIDTH_PROPOSAL_ID].quality_score_after == pytest.approx(0.9)

    with database.sessions() as session:
        revisions = (
            session.query(ReviewRevisionRecord)
            .filter_by(job_id=str(JOB_ID))
            .order_by(ReviewRevisionRecord.version)
            .all()
        )
        assert [revision.version for revision in revisions] == [1, 2]
        v1, v2 = revisions
        assert v2.parent_review_id == v1.id
        # Packet e decisões viajam byte a byte: refresh não decide nada.
        assert v2.packet_json == v1.packet_json
        assert v2.proposal_decisions_json == v1.proposal_decisions_json
        assert v2.proposals_json == refined.model_dump(mode="json")
        assert v2.scene_revision_id is None
        assert v2.calibration_json is None
        assert v2.created_by == "refresh-proposals:tenant-admin-02"
        # Prova de que os candidatos foram RECOMPUTADOS, não copiados: o quality_score
        # novo aparece no candidato recém-gerado.
        height_candidates = [
            candidate
            for candidate in v2.associations_json["candidates"]
            if candidate["proposal_id"] == HEIGHT_PROPOSAL_ID
        ]
        assert height_candidates
        assert all(
            candidate["visual_quality_score"] == pytest.approx(0.99)
            for candidate in height_candidates
        )


def test_refresh_carries_the_declared_chains_forward(tmp_path: Path) -> None:
    """A cadeia declarada é ato humano sobre cotas; o refresh só mexe em pixels.

    `insert_next_review_revision` copia verbatim toda coluna que não seja proposta,
    associação ou calibração. Uma coluna esquecida ali não falha em lugar nenhum: ela
    apaga em silêncio o que uma pessoa declarou, e só aparece quando a cadeia some da
    tela sem ninguém ter retratado nada.
    """
    database, database_url, bundle, digest = _seed_v1(tmp_path)
    declared_chains = [
        {
            "chain_id": "ch_0123456789abcdef",
            "total_id": WIDTH_READING_ID,
            "part_ids": [HEIGHT_READING_ID, "rd_" + "c" * 16],
            "declared_by": "reviewer",
            "declared_role": "engineer",
            "declared_at": "2026-08-20T12:00:00+00:00",
        }
    ]
    with database.sessions.begin() as session:
        review = session.query(ReviewRevisionRecord).filter_by(job_id=str(JOB_ID)).one()
        assert review.declared_chains_json == []
        review.declared_chains_json = declared_chains

    refined_path = _write_json(
        tmp_path / "refined.json", _refined_proposals(_proposals(digest=digest), "quality")
    )
    result = refresh_proposals(
        RefreshInputs(
            job_id=JOB_ID,
            tenant_id=TENANT_ID,
            proposals_path=refined_path,
            image_path=bundle["image"],
            operator_id="tenant-admin-02",
        ),
        _settings(database_url),
    )

    assert result.review_version_after == 2
    with database.sessions() as session:
        next_review = (
            session.query(ReviewRevisionRecord).filter_by(job_id=str(JOB_ID), version=2).one()
        )
        assert next_review.declared_chains_json == declared_chains


def test_refresh_refuses_a_second_run_of_the_same_refined_file(tmp_path: Path) -> None:
    database, database_url, bundle, digest = _seed_v1(tmp_path)
    refined = _refined_proposals(_proposals(digest=digest), "quality")
    refined_path = _write_json(tmp_path / "refined.json", refined)
    refresh_proposals(
        RefreshInputs(
            job_id=JOB_ID,
            tenant_id=TENANT_ID,
            proposals_path=refined_path,
            image_path=bundle["image"],
            operator_id="tenant-admin-02",
        ),
        _settings(database_url),
    )

    with pytest.raises(RefreshRefusedError) as refusal:
        refresh_proposals(
            RefreshInputs(
                job_id=JOB_ID,
                tenant_id=TENANT_ID,
                proposals_path=refined_path,
                image_path=bundle["image"],
                operator_id="tenant-admin-02",
            ),
            _settings(database_url),
        )

    assert refusal.value.code == "REFRESH_ALREADY_APPLIED"
    with database.sessions() as session:
        assert session.query(ReviewRevisionRecord).filter_by(job_id=str(JOB_ID)).count() == 2


# --- matriz de recusa fail-closed -------------------------------------------------------

_UNCHANGED_MUTATIONS = {"unknown_job", "other_tenant", "no_review", "already_applied"}


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("unknown_job", "JOB_NOT_FOUND"),
        ("other_tenant", "JOB_NOT_FOUND"),
        ("no_review", "REVIEW_MISSING"),
        ("image_mismatch", "IMAGE_DIGEST_MISMATCH"),
        ("dataset_mismatch", "DATASET_MISMATCH"),
        ("extra_proposal", "PROPOSAL_SET_MISMATCH"),
        ("missing_proposal", "PROPOSAL_SET_MISMATCH"),
        ("duplicate_proposal", "PROPOSAL_SET_MISMATCH"),
        ("already_applied", "REFRESH_ALREADY_APPLIED"),
        ("break_association", "REFRESH_BREAKS_SELECTED_ASSOCIATION"),
    ],
)
def test_refresh_refuses_every_divergence(
    tmp_path: Path, mutation: str, expected_code: str
) -> None:
    source_sha256 = hashlib.sha256(synthetic_pdf()).hexdigest()
    database, database_url = _seed_database(tmp_path, source_sha256=source_sha256)
    bundle, digest = _write_bundle(tmp_path / "bundle", source_sha256=source_sha256)
    if mutation != "no_review":
        seed_review(
            SeedInputs(
                job_id=JOB_ID,
                tenant_id=TENANT_ID,
                packet_path=bundle["packet"],
                associations_path=bundle["associations"],
                proposals_path=bundle["proposals"],
                rectangle_request_path=bundle["rectangle_request"],
                manifest_path=bundle["manifest"],
                image_path=bundle["image"],
                required_criteria=(),
                operator_id="tenant-admin-01",
            ),
            _settings(database_url),
            s3_client=FakeObjectStore(),
        )
    if mutation == "break_association":
        # Simula uma associação já confirmada por um profissional antes do refresh.
        with database.sessions.begin() as session:
            review = session.query(ReviewRevisionRecord).filter_by(job_id=str(JOB_ID)).one()
            review.selected_associations_json = {WIDTH_READING_ID: WIDTH_PROPOSAL_ID}

    proposal_mutation = "unchanged" if mutation in _UNCHANGED_MUTATIONS else mutation
    refined = _refined_proposals(_proposals(digest=digest), proposal_mutation)
    refined_path = _write_json(tmp_path / f"refined-{mutation}.json", refined)

    job_id = UUID("00000000-0000-7000-8000-000000009999") if mutation == "unknown_job" else JOB_ID
    tenant_id = "tenant-other" if mutation == "other_tenant" else TENANT_ID

    with pytest.raises(RefreshRefusedError) as refusal:
        refresh_proposals(
            RefreshInputs(
                job_id=job_id,
                tenant_id=tenant_id,
                proposals_path=refined_path,
                image_path=bundle["image"],
                operator_id="tenant-admin-01",
            ),
            _settings(database_url),
        )

    assert refusal.value.code == expected_code
    with database.sessions() as session:
        expected_rows = 0 if mutation == "no_review" else 1
        assert (
            session.query(ReviewRevisionRecord).filter_by(job_id=str(JOB_ID)).count()
            == expected_rows
        )


def test_refresh_rejects_invalid_detector_version_via_pydantic(tmp_path: Path) -> None:
    """`detector_version` fora do Literal já é recusado pelo Pydantic, sem código refused."""
    malformed = {
        "dataset_id": DATASET_ID,
        "page_number": 1,
        "image_sha256": "a" * 64,
        "image_width_px": 40,
        "image_height_px": 30,
        "detector_version": "not-a-real-detector",
        "configured_limits": {"line": 80, "circle": 16, "contour": 16},
        "limit_reached": [],
        "proposals": [],
        "safety_notes": ["a", "b", "c"],
    }
    proposals_path = tmp_path / "malformed.json"
    proposals_path.write_text(json.dumps(malformed), encoding="utf-8")
    image_path = tmp_path / "page.png"
    Image.new("RGB", (40, 30), "white").save(image_path)

    with pytest.raises(ValidationError) as error:
        refresh_proposals(
            RefreshInputs(
                job_id=JOB_ID,
                tenant_id=TENANT_ID,
                proposals_path=proposals_path,
                image_path=image_path,
                operator_id="tenant-admin-01",
            ),
            _settings("sqlite+pysqlite:///:memory:"),
        )
    assert any("detector_version" in str(item["loc"]) for item in error.value.errors())


# --- calibração: revalidada pela mesma regra da API -------------------------------------


def _calibration_scene(*, with_accepted_entity: bool) -> SceneRevision:
    line_provenance = Provenance(
        source_type="fixture", source_ids=["measurement"], summary_code="SOLVER"
    )
    entities = [
        Entity(
            id=HORIZONTAL_ENTITY_ID,
            kind=EntityKind.LINE,
            layer=LayerName.CAMPO,
            precision=Precision.EXACT,
            geometry=LineGeometry(start=Point2D(x=0, y=0), end=Point2D(x=3, y=0)),
            provenance=line_provenance,
        ),
        Entity(
            id=VERTICAL_ENTITY_ID,
            kind=EntityKind.LINE,
            layer=LayerName.CAMPO,
            precision=Precision.EXACT,
            geometry=LineGeometry(start=Point2D(x=0, y=0), end=Point2D(x=0, y=2)),
            provenance=line_provenance,
        ),
    ]
    if with_accepted_entity:
        entities.append(
            Entity(
                id=ACCEPTED_ENTITY_ID,
                kind=EntityKind.CIRCLE,
                layer=LayerName.APROXIMADO,
                precision=Precision.APPROXIMATE,
                geometry=CircleGeometry(center=Point2D(x=1.5, y=1.0), radius=0.4),
                provenance=Provenance(
                    source_type=HUMAN_ACCEPTED_PROPOSAL_SOURCE_TYPE,
                    source_ids=["vp_accepted_fixture", "calibration-fixture", "review-fixture"],
                    summary_code="HUMAN_SELECTED_PIXEL_PROPOSAL",
                ),
            )
        )
    return SceneRevision(job_id=JOB_ID, version=1, entities=entities)


def _calibration_json(scene: SceneRevision, proposals: VisionProposalSet) -> dict[str, Any]:
    anchors = [
        CalibrationAnchor(proposal_id=WIDTH_PROPOSAL_ID, entity_id=HORIZONTAL_ENTITY_ID),
        CalibrationAnchor(proposal_id=HEIGHT_PROPOSAL_ID, entity_id=VERTICAL_ENTITY_ID),
    ]
    transform = calibrate_similarity(proposals, scene, anchors)
    matrix = matrix_of(transform)
    return {
        "calibration_id": str(new_uuid7()),
        "scene_revision_id": str(scene.id),
        "scene_version": scene.version,
        "anchors": [
            {
                "proposal_id": anchor.proposal_id,
                "entity_id": str(anchor.entity_id),
                "reversed": anchor.reversed,
            }
            for anchor in anchors
        ],
        "scale_m_per_px": transform.scale_x_m_per_px,
        "rotation_radians": math.atan2(transform.b, transform.a),
        "translation_m": [transform.tx, transform.ty],
        "rmse_m": transform.rmse_m,
        "mode": "similarity",
        "matrix": list(matrix),
        "scale_x_m_per_px": transform.scale_x_m_per_px,
        "scale_y_m_per_px": transform.scale_y_m_per_px,
        "anisotropy": transform.anisotropy,
    }


def _attach_scene_and_calibration(
    database: Database, *, scene: SceneRevision, calibration_json: dict[str, Any]
) -> None:
    with database.sessions.begin() as session:
        session.add(
            RevisionRecord(
                id=str(scene.id),
                tenant_id=TENANT_ID,
                job_id=str(JOB_ID),
                version=scene.version,
                parent_revision_id=None,
                scene=scene.model_dump(mode="json"),
                created_by="fixture",
            )
        )
        session.flush()
        review = session.query(ReviewRevisionRecord).filter_by(job_id=str(JOB_ID)).one()
        review.scene_revision_id = str(scene.id)
        review.calibration_json = calibration_json


def test_refresh_keeps_calibration_when_the_anchors_do_not_drift(tmp_path: Path) -> None:
    database, database_url, bundle, digest = _seed_v1(tmp_path)
    base_proposals = _proposals(digest=digest)
    scene = _calibration_scene(with_accepted_entity=False)
    calibration_json = _calibration_json(scene, base_proposals)
    _attach_scene_and_calibration(database, scene=scene, calibration_json=calibration_json)

    # Só o quality_score da altura muda; as duas linhas-âncora ficam intactas.
    refined = _refined_proposals(base_proposals, "quality")
    refined_path = _write_json(tmp_path / "refined.json", refined)

    result = refresh_proposals(
        RefreshInputs(
            job_id=JOB_ID,
            tenant_id=TENANT_ID,
            proposals_path=refined_path,
            image_path=bundle["image"],
            operator_id="tenant-admin-03",
        ),
        _settings(database_url),
    )

    assert result.calibration_status == "kept"
    with database.sessions() as session:
        v2 = session.query(ReviewRevisionRecord).filter_by(job_id=str(JOB_ID), version=2).one()
        assert v2.calibration_json is not None
        assert v2.calibration_json["scene_revision_id"] == str(scene.id)
        assert v2.scene_revision_id == str(scene.id)
        # Nenhuma cena nova nasce quando a calibração sobrevive à deriva.
        assert session.query(RevisionRecord).filter_by(job_id=str(JOB_ID)).count() == 1


def test_refresh_supersedes_calibration_and_freezes_accepted_geometry(tmp_path: Path) -> None:
    database, database_url, bundle, digest = _seed_v1(tmp_path)
    base_proposals = _proposals(digest=digest)
    scene = _calibration_scene(with_accepted_entity=True)
    calibration_json = _calibration_json(scene, base_proposals)
    _attach_scene_and_calibration(database, scene=scene, calibration_json=calibration_json)

    # A linha-âncora da largura muda de escala: a transformação recalculada diverge da
    # gravada muito além da tolerância de deriva.
    refined = _refined_proposals(base_proposals, "widen_width_line")
    refined_path = _write_json(tmp_path / "refined.json", refined)

    result = refresh_proposals(
        RefreshInputs(
            job_id=JOB_ID,
            tenant_id=TENANT_ID,
            proposals_path=refined_path,
            image_path=bundle["image"],
            operator_id="tenant-admin-04",
        ),
        _settings(database_url),
    )

    assert result.calibration_status == "superseded"
    with database.sessions() as session:
        v2 = session.query(ReviewRevisionRecord).filter_by(job_id=str(JOB_ID), version=2).one()
        assert v2.calibration_json is None
        assert v2.scene_revision_id != str(scene.id)

        new_scene_row = session.query(RevisionRecord).filter_by(id=v2.scene_revision_id).one()
        new_scene = SceneRevision.model_validate(new_scene_row.scene)
        assert new_scene.version == scene.version + 1
        superseded_issues = [
            issue for issue in new_scene.issues if issue.code == "CALIBRATION_SUPERSEDED"
        ]
        assert len(superseded_issues) == 1
        assert superseded_issues[0].entity_ids == [ACCEPTED_ENTITY_ID]

        # Nunca reprojeta: a geometria da entidade aceita chega intacta na cena nova.
        accepted = next(entity for entity in new_scene.entities if entity.id == ACCEPTED_ENTITY_ID)
        original_accepted = next(
            entity for entity in scene.entities if entity.id == ACCEPTED_ENTITY_ID
        )
        assert accepted.geometry == original_accepted.geometry

        # A revisão anterior — e a cena que ela referenciava — permanecem intocadas.
        old_scene_row = session.query(RevisionRecord).filter_by(id=str(scene.id)).one()
        assert old_scene_row.scene == scene.model_dump(mode="json")
