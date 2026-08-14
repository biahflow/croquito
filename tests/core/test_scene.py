from decimal import Decimal

import pytest
from pydantic import ValidationError

from croquito_core.errors import DomainValidationError
from croquito_core.models import (
    DiameterDimensionGeometry,
    Entity,
    EntityKind,
    Issue,
    IssueSeverity,
    IssueStatus,
    LayerName,
    LineGeometry,
    Measurement,
    MeasurementKind,
    Point2D,
    Precision,
    Provenance,
    UnitCode,
)
from croquito_worker.synthetic import build_synthetic_scene


def test_synthetic_scene_is_exportable() -> None:
    scene = build_synthetic_scene()

    scene.ensure_exportable()
    assert scene.export_errors() == []


def test_exact_entity_requires_provenance() -> None:
    with pytest.raises(ValidationError, match="provenance"):
        Entity(
            kind=EntityKind.LINE,
            layer=LayerName.CONTORNO,
            precision=Precision.EXACT,
            geometry=LineGeometry(start=Point2D(x=0, y=0), end=Point2D(x=1, y=0)),
        )


def test_diameter_dimension_follows_the_same_gates_as_the_other_entities() -> None:
    """Cota diametral é entidade como qualquer outra: kind casado e exact com rastro."""
    geometry = DiameterDimensionGeometry(
        center=Point2D(x=10, y=10),
        radius=2.5,
        angle=0.0,
        text_override="⌀ 5.00 m",
    )
    with pytest.raises(ValidationError, match="provenance"):
        Entity(
            kind=EntityKind.DIAMETER_DIMENSION,
            layer=LayerName.COTAS,
            precision=Precision.EXACT,
            geometry=geometry,
        )
    with pytest.raises(ValidationError, match="kind"):
        Entity(
            kind=EntityKind.DIMENSION,
            layer=LayerName.COTAS,
            precision=Precision.DERIVED,
            geometry=geometry,
        )

    entity = Entity(
        kind=EntityKind.DIAMETER_DIMENSION,
        layer=LayerName.COTAS,
        precision=Precision.EXACT,
        geometry=geometry,
        provenance=Provenance(
            source_type="human_confirmed_reading+explicit_association",
            source_ids=["rd_00000000000000d1"],
            summary_code="CONFIRMED_READING_OVER_CIRCLE",
        ),
    )
    assert entity.geometry.type == entity.kind.value


def test_unresolved_entity_blocks_export() -> None:
    scene = build_synthetic_scene()
    scene.entities[0].precision = Precision.UNRESOLVED

    with pytest.raises(DomainValidationError, match="UNRESOLVED_ENTITY"):
        scene.ensure_exportable()


def test_unaccepted_approximation_blocks_export() -> None:
    scene = build_synthetic_scene()
    scene.entities[0].precision = Precision.APPROXIMATE

    assert any(error.startswith("APPROXIMATION_NOT_ACCEPTED") for error in scene.export_errors())
    scene.accepted_approximation_ids.add(scene.entities[0].id)
    scene.ensure_exportable()


def test_confirmed_measurement_mismatch_is_detected() -> None:
    scene = build_synthetic_scene()
    source = Provenance(
        source_type="human_confirmation",
        source_ids=["test"],
        summary_code="HUMAN_CONFIRMED",
    )
    scene.measurements.append(
        Measurement(
            entity_id=scene.entities[0].id,
            kind=MeasurementKind.WIDTH,
            raw_text="99,00 m",
            value_si=Decimal("99.00"),
            unit=UnitCode.METRE,
            confirmed=True,
            provenance=source,
        )
    )

    assert any(error.startswith("MEASUREMENT_MISMATCH") for error in scene.export_errors())


def test_millimetre_written_precision_is_scaled_to_si() -> None:
    source = Provenance(
        source_type="human_confirmation",
        source_ids=["test-mm"],
        summary_code="HUMAN_CONFIRMED",
    )
    within_tolerance = build_synthetic_scene()
    within_tolerance.measurements = [
        Measurement(
            entity_id=within_tolerance.entities[0].id,
            kind=MeasurementKind.WIDTH,
            raw_text="31950,00 mm",
            value_si=Decimal("31.950004"),
            unit=UnitCode.MILLIMETRE,
            written_decimals=2,
            confirmed=True,
            provenance=source,
        )
    ]
    outside_tolerance = build_synthetic_scene()
    outside_tolerance.measurements = [
        Measurement(
            entity_id=outside_tolerance.entities[0].id,
            kind=MeasurementKind.WIDTH,
            raw_text="31950,00 mm",
            value_si=Decimal("31.950006"),
            unit=UnitCode.MILLIMETRE,
            written_decimals=2,
            confirmed=True,
            provenance=source,
        )
    ]

    assert within_tolerance.export_errors() == []
    assert any(
        error.startswith("MEASUREMENT_MISMATCH") for error in outside_tolerance.export_errors()
    )


def test_open_critical_issue_blocks_export_until_it_is_accepted() -> None:
    scene = build_synthetic_scene()
    scene.issues.append(
        Issue(
            code="ACC_GUA_001",
            severity=IssueSeverity.CRITICAL,
            message="Muro e portão ainda não estão cobertos pela cena métrica.",
        )
    )

    assert "OPEN_CRITICAL_ISSUE:ACC_GUA_001" in scene.export_errors()

    scene.issues[-1].status = IssueStatus.ACCEPTED

    scene.ensure_exportable()
