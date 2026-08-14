import math
from decimal import Decimal
from uuid import UUID

import pytest

from croquito_core.models import (
    DimensionGeometry,
    Entity,
    EntityKind,
    LayerName,
    LineGeometry,
    Measurement,
    MeasurementKind,
    Point2D,
    Precision,
    Provenance,
    SceneRevision,
    TextGeometry,
)
from croquito_worker.dimension_annotation import (
    DimensionAnnotationError,
    annotate_note,
    annotate_traced_line,
)

JOB_ID = UUID("00000000-0000-7000-8000-000000000701")
TRACED_ID = UUID("00000000-0000-7000-8000-000000000702")


def _scene_with_traced_line(length: float = 14.21) -> SceneRevision:
    """Linha traçada por pixels, um pouco fora da cota escrita de 14,50 m."""
    return SceneRevision(
        job_id=JOB_ID,
        version=1,
        entities=[
            Entity(
                id=TRACED_ID,
                kind=EntityKind.LINE,
                layer=LayerName.APROXIMADO,
                precision=Precision.APPROXIMATE,
                geometry=LineGeometry(start=Point2D(x=0, y=0), end=Point2D(x=length, y=0)),
                provenance=Provenance(
                    source_type="vision_proposal_calibrated",
                    source_ids=["vp_1111111111111111"],
                    summary_code="HUMAN_SELECTED_PIXEL_PROPOSAL",
                ),
            )
        ],
        accepted_approximation_ids=[TRACED_ID],
    )


def _annotate(scene: SceneRevision, value: str = "14.50") -> tuple[Entity, Entity, Measurement]:
    return annotate_traced_line(
        scene,
        entity_id=TRACED_ID,
        reading_id="rd_1450145014501450",
        decision_id="dec-1",
        value_si=Decimal(value),
        written_decimals=2,
        kind=MeasurementKind.LENGTH,
    )


def test_written_dimension_overrides_the_traced_length() -> None:
    adjusted, dimension, measurement = _annotate(_scene_with_traced_line())

    assert isinstance(adjusted.geometry, LineGeometry)
    length = math.hypot(
        adjusted.geometry.end.x - adjusted.geometry.start.x,
        adjusted.geometry.end.y - adjusted.geometry.start.y,
    )
    assert length == pytest.approx(14.50)
    assert adjusted.id == TRACED_ID
    # A linha continua approximate: só o comprimento veio da folha, a posição é pixel.
    assert adjusted.precision is Precision.APPROXIMATE
    assert dimension.layer is LayerName.COTAS
    assert dimension.precision is Precision.EXACT
    assert isinstance(dimension.geometry, DimensionGeometry)
    assert measurement.confirmed is True
    assert measurement.entity_id == TRACED_ID


def test_line_is_rescaled_around_its_own_midpoint() -> None:
    adjusted, _dimension, _measurement = _annotate(_scene_with_traced_line())

    # Reposicionar por uma das pontas arrastaria o desenho inteiro para longe do que o
    # profissional viu na tela.
    assert isinstance(adjusted.geometry, LineGeometry)
    midpoint = (adjusted.geometry.start.x + adjusted.geometry.end.x) / 2
    assert midpoint == pytest.approx(14.21 / 2)


def test_annotated_scene_passes_the_measurement_conformity_gate() -> None:
    scene = _scene_with_traced_line()
    adjusted, dimension, measurement = _annotate(scene)
    annotated = SceneRevision.model_validate(
        {
            **scene.model_dump(mode="json"),
            "approved": True,
            "entities": [adjusted.model_dump(mode="json"), dimension.model_dump(mode="json")],
            "measurements": [measurement.model_dump(mode="json")],
        }
    )

    # Sem o ajuste a cena reprovaria com MEASUREMENT_MISMATCH: 14,21 m contra 14,50 m
    # escritos, muito além da tolerância de meia casa decimal.
    assert annotated.export_errors() == []


def test_unadjusted_line_would_fail_the_conformity_gate() -> None:
    scene = _scene_with_traced_line()
    _adjusted, _dimension, measurement = _annotate(scene)
    untouched = SceneRevision.model_validate(
        {
            **scene.model_dump(mode="json"),
            "approved": True,
            "measurements": [measurement.model_dump(mode="json")],
        }
    )

    assert any(error.startswith("MEASUREMENT_MISMATCH") for error in untouched.export_errors())


def test_note_lands_on_the_element_layer_as_exact_text() -> None:
    scene = _scene_with_traced_line()

    note = annotate_note(
        scene,
        entity_id=TRACED_ID,
        layer=LayerName.MURO,
        text="muro vizinho h=3,80",
        reading_id="rd_3800380038003800",
        decision_id="dec-2",
    )

    assert note.kind is EntityKind.TEXT
    assert note.layer is LayerName.MURO
    # O texto é literalmente o que está escrito na folha, conferido por uma pessoa.
    assert note.precision is Precision.EXACT
    assert isinstance(note.geometry, TextGeometry)
    assert note.geometry.text == "muro vizinho h=3,80"
    assert note.provenance is not None
    assert note.provenance.source_ids[0] == "rd_3800380038003800"


def test_note_does_not_add_a_measurement_to_check_against_geometry() -> None:
    """Altura de muro não existe em planta: não há geometria para conferir contra ela."""
    scene = _scene_with_traced_line()
    note = annotate_note(
        scene,
        entity_id=TRACED_ID,
        layer=LayerName.MURO,
        text="muro vizinho h=3,80",
        reading_id="rd_3800380038003800",
        decision_id="dec-2",
    )
    annotated = SceneRevision.model_validate(
        {
            **scene.model_dump(mode="json"),
            "approved": True,
            "entities": [
                *[item.model_dump(mode="json") for item in scene.entities],
                note.model_dump(mode="json"),
            ],
        }
    )

    assert annotated.measurements == []
    assert annotated.export_errors() == []


def test_note_rotation_is_stored_in_radians_like_the_rest_of_the_scene() -> None:
    """`dxf.py` converte para grau na escrita; gravar grau aqui dobrava a conversão.

    Numa linha vertical o defeito escrevia 90 no campo, o `math.degrees` do export levava a
    5157°, e a anotação saía atravessada no desenho.
    """
    scene = _scene_with_traced_line()
    vertical = scene.entities[0].model_copy(
        update={"geometry": LineGeometry(start=Point2D(x=0, y=0), end=Point2D(x=0, y=10))}
    )
    scene = scene.model_copy(update={"entities": [vertical]})

    note = annotate_note(
        scene,
        entity_id=TRACED_ID,
        layer=LayerName.MURO,
        text="muro vizinho h=3,80",
        reading_id="rd_1450145014501450",
        decision_id="dec-1",
    )

    assert isinstance(note.geometry, TextGeometry)
    assert note.geometry.rotation == pytest.approx(math.pi / 2)
    assert math.degrees(note.geometry.rotation) == pytest.approx(90.0)


def test_annotation_refuses_a_non_line_entity() -> None:
    scene = _scene_with_traced_line()
    with pytest.raises(DimensionAnnotationError, match="não existe"):
        annotate_traced_line(
            scene,
            entity_id=JOB_ID,
            reading_id="rd_1450145014501450",
            decision_id="dec-1",
            value_si=Decimal("14.50"),
            written_decimals=2,
            kind=MeasurementKind.LENGTH,
        )
