from uuid import UUID

import pytest

from croquitodxf_core.models import (
    CircleGeometry,
    Entity,
    EntityKind,
    LayerName,
    LineGeometry,
    Point2D,
    PolylineGeometry,
    Precision,
    Provenance,
    SceneRevision,
)
from croquitodxf_worker.proposal_calibration import (
    CalibrationAnchor,
    CalibrationError,
    approximate_entity_from_proposal,
    calibrate_affine,
    calibrate_similarity,
)
from croquitodxf_worker.vision import (
    PixelCircle,
    PixelLine,
    PixelPoint,
    PixelPolyline,
    VisionProposal,
    VisionProposalSet,
)

JOB_ID = UUID("00000000-0000-7000-8000-000000000601")
HORIZONTAL_ID = UUID("00000000-0000-7000-8000-000000000602")
VERTICAL_ID = UUID("00000000-0000-7000-8000-000000000603")


def _proposals(*, parallel: bool = False) -> VisionProposalSet:
    second_start = PixelPoint(x=0, y=20) if parallel else PixelPoint(x=0, y=0)
    second_end = PixelPoint(x=100, y=20) if parallel else PixelPoint(x=0, y=100)
    return VisionProposalSet(
        dataset_id="proposal-calibration-fixture-v1",
        page_number=1,
        image_sha256="a" * 64,
        image_width_px=200,
        image_height_px=200,
        configured_limits={"line": 80, "circle": 16, "contour": 16},
        limit_reached=[],
        proposals=[
            VisionProposal(
                id="vp_1111111111111111",
                kind="line",
                geometry=PixelLine(start=PixelPoint(x=0, y=0), end=PixelPoint(x=100, y=0)),
                algorithm="fixture",
                quality_score=1,
            ),
            VisionProposal(
                id="vp_2222222222222222",
                kind="line",
                geometry=PixelLine(start=second_start, end=second_end),
                algorithm="fixture",
                quality_score=1,
            ),
            VisionProposal(
                id="vp_3333333333333333",
                kind="circle",
                geometry=PixelCircle(center=PixelPoint(x=50, y=50), radius=10),
                algorithm="fixture",
                quality_score=1,
            ),
            VisionProposal(
                id="vp_4444444444444444",
                kind="contour",
                geometry=PixelPolyline(
                    points=[PixelPoint(x=10, y=10), PixelPoint(x=20, y=10), PixelPoint(x=15, y=20)]
                ),
                algorithm="fixture",
                quality_score=1,
            ),
        ],
        safety_notes=["fixture", "pixels", "não exportável"],
    )


def _scene() -> SceneRevision:
    provenance = Provenance(
        source_type="fixture", source_ids=["measurement"], summary_code="SOLVER"
    )
    return SceneRevision(
        job_id=JOB_ID,
        version=1,
        entities=[
            Entity(
                id=HORIZONTAL_ID,
                kind=EntityKind.LINE,
                layer=LayerName.CAMPO,
                precision=Precision.EXACT,
                geometry=LineGeometry(start=Point2D(x=10, y=5), end=Point2D(x=20, y=5)),
                provenance=provenance,
            ),
            Entity(
                id=VERTICAL_ID,
                kind=EntityKind.LINE,
                layer=LayerName.CAMPO,
                precision=Precision.DERIVED,
                geometry=LineGeometry(start=Point2D(x=10, y=5), end=Point2D(x=10, y=15)),
                provenance=provenance,
            ),
        ],
    )


def _anchors() -> list[CalibrationAnchor]:
    return [
        CalibrationAnchor(proposal_id="vp_1111111111111111", entity_id=HORIZONTAL_ID),
        CalibrationAnchor(proposal_id="vp_2222222222222222", entity_id=VERTICAL_ID),
    ]


def test_calibration_maps_circle_and_contour_to_approximate_entities() -> None:
    proposals = _proposals()
    transform = calibrate_similarity(proposals, _scene(), _anchors())

    assert transform.rmse_m == pytest.approx(0)
    circle = approximate_entity_from_proposal(
        proposals.proposals[2], transform, calibration_id=JOB_ID, review_id=JOB_ID
    )
    contour = approximate_entity_from_proposal(
        proposals.proposals[3], transform, calibration_id=JOB_ID, review_id=JOB_ID
    )

    assert circle.kind is EntityKind.CIRCLE
    assert circle.precision is Precision.APPROXIMATE
    assert isinstance(circle.geometry, CircleGeometry)
    assert circle.geometry.center.x == pytest.approx(15)
    assert circle.geometry.radius == pytest.approx(1)
    assert contour.kind is EntityKind.POLYLINE
    assert isinstance(contour.geometry, PolylineGeometry)
    assert contour.geometry.closed is True
    assert contour.layer is LayerName.APROXIMADO
    assert contour.provenance is not None
    assert contour.provenance.source_ids[0] == "vp_4444444444444444"


def _anisotropic_scene() -> SceneRevision:
    """Mesmos 100 px em cada eixo, mas 10 m na horizontal e 15 m na vertical."""
    scene = _scene()
    vertical = scene.entities[1]
    return scene.model_copy(
        update={
            "entities": [
                scene.entities[0],
                vertical.model_copy(
                    update={
                        "geometry": LineGeometry(start=Point2D(x=10, y=5), end=Point2D(x=10, y=20))
                    }
                ),
            ]
        }
    )


def test_similarity_cannot_fit_axes_with_different_scales() -> None:
    """O croqui à mão é anisotrópico; escala única não tem solução e o erro explode."""
    transform = calibrate_similarity(_proposals(), _anisotropic_scene(), _anchors())

    assert transform.rmse_m > 0.5
    assert transform.anisotropy == 1.0


def test_affine_recovers_one_scale_per_axis() -> None:
    proposals = _proposals()
    transform = calibrate_affine(proposals, _anisotropic_scene(), _anchors())

    assert transform.rmse_m == pytest.approx(0, abs=1e-9)
    assert transform.scale_x_m_per_px == pytest.approx(0.1)
    assert transform.scale_y_m_per_px == pytest.approx(0.15)
    assert transform.anisotropy == pytest.approx(1.5)


def test_anisotropic_calibration_samples_circle_instead_of_faking_a_radius() -> None:
    proposals = _proposals()
    transform = calibrate_affine(proposals, _anisotropic_scene(), _anchors())

    entity = approximate_entity_from_proposal(
        proposals.proposals[2], transform, calibration_id=JOB_ID, review_id=JOB_ID
    )

    assert entity.kind is EntityKind.POLYLINE
    assert entity.precision is Precision.APPROXIMATE
    assert isinstance(entity.geometry, PolylineGeometry)
    assert entity.geometry.closed is True
    xs = [point.x for point in entity.geometry.points]
    ys = [point.y for point in entity.geometry.points]
    # Raio de 10 px vira 1 m na horizontal e 1,5 m na vertical: é elipse, não círculo.
    assert (max(xs) - min(xs)) == pytest.approx(2.0, abs=1e-3)
    assert (max(ys) - min(ys)) == pytest.approx(3.0, abs=1e-3)


def test_isotropic_affine_still_yields_a_circle() -> None:
    proposals = _proposals()
    transform = calibrate_affine(proposals, _scene(), _anchors())

    entity = approximate_entity_from_proposal(
        proposals.proposals[2], transform, calibration_id=JOB_ID, review_id=JOB_ID
    )

    assert entity.kind is EntityKind.CIRCLE
    assert isinstance(entity.geometry, CircleGeometry)
    assert entity.geometry.radius == pytest.approx(1)


def test_calibration_rejects_parallel_anchors() -> None:
    with pytest.raises(CalibrationError, match="paralelos"):
        calibrate_similarity(_proposals(parallel=True), _scene(), _anchors())


def test_calibration_rejects_non_line_anchor() -> None:
    with pytest.raises(CalibrationError, match="Somente propostas de linha"):
        calibrate_similarity(
            _proposals(),
            _scene(),
            [
                CalibrationAnchor(proposal_id="vp_3333333333333333", entity_id=HORIZONTAL_ID),
                CalibrationAnchor(proposal_id="vp_2222222222222222", entity_id=VERTICAL_ID),
            ],
        )
