import hashlib
import json
from decimal import Decimal
from pathlib import Path
from typing import cast
from zipfile import ZipFile

import pytest
from pydantic import ValidationError

from croquito_core.errors import DomainValidationError
from croquito_core.ids import new_uuid7
from croquito_core.models import (
    ELEMENT_LABEL_MAX_LENGTH,
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
    SceneRevision,
    UnitCode,
)
from croquito_worker.pipeline import run_synthetic_pipeline
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


# ADR-0058 T1: `element_ref` é o elo estável de identidade de elemento — ao lado do `id`
# de linha e do texto livre do rótulo, nunca no lugar de nenhum dos dois. Esta tarefa só
# declara o campo, a invariante mínima (camada coerente) e prova que o portão de export e
# o pacote exportado não mudam de comportamento sem ele.


def test_element_ref_is_optional_and_coexists_with_id_and_label() -> None:
    """`element_ref` não substitui `id` (identidade de linha) nem o texto do rótulo."""
    scene = build_synthetic_scene()
    assert all(entity.element_ref is None for entity in scene.entities)

    entity_with_ref = Entity(
        kind=EntityKind.LINE,
        layer=LayerName.MURO,
        precision=Precision.DERIVED,
        geometry=LineGeometry(start=Point2D(x=0, y=0), end=Point2D(x=1, y=0)),
        element_ref="EL-001",
    )
    assert entity_with_ref.element_ref == "EL-001"
    assert entity_with_ref.id is not None
    assert entity_with_ref.id != entity_with_ref.element_ref


@pytest.mark.parametrize("invalid_ref", ["EL-1", "EL-01", "el-001", "001", "EL001", ""])
def test_element_ref_rejects_values_outside_the_declared_pattern(invalid_ref: str) -> None:
    with pytest.raises(ValidationError, match="element_ref"):
        Entity(
            kind=EntityKind.LINE,
            layer=LayerName.MURO,
            precision=Precision.DERIVED,
            geometry=LineGeometry(start=Point2D(x=0, y=0), end=Point2D(x=1, y=0)),
            element_ref=invalid_ref,
        )


def _entity_on_layer(layer: LayerName, *, element_ref: str | None) -> Entity:
    return Entity(
        kind=EntityKind.LINE,
        layer=layer,
        precision=Precision.DERIVED,
        geometry=LineGeometry(start=Point2D(x=0, y=0), end=Point2D(x=1, y=0)),
        element_ref=element_ref,
    )


def test_scene_accepts_the_same_element_ref_on_several_traces_of_the_same_layer() -> None:
    """Um elemento pode ter vários traços — o ref identifica o elemento, não a linha."""
    scene = SceneRevision(
        job_id=new_uuid7(),
        version=1,
        entities=[
            _entity_on_layer(LayerName.MURO, element_ref="EL-001"),
            _entity_on_layer(LayerName.MURO, element_ref="EL-001"),
        ],
    )
    assert {entity.element_ref for entity in scene.entities} == {"EL-001"}


def test_scene_refuses_element_ref_mixed_across_layers() -> None:
    """Misturar camadas sob o mesmo element_ref não é um elemento coerente (ADR-0058)."""
    with pytest.raises(ValidationError, match="ELEMENT_REF_LAYER_MISMATCH"):
        SceneRevision(
            job_id=new_uuid7(),
            version=1,
            entities=[
                _entity_on_layer(LayerName.MURO, element_ref="EL-001"),
                _entity_on_layer(LayerName.ALAMBRADO, element_ref="EL-001"),
            ],
        )


def test_element_ref_survives_the_new_revision_created_on_approval() -> None:
    """Reproduz a reconstrução por `model_dump` que a aprovação faz em
    `services/api/src/croquito_api/main.py` (novo `id` de revisão, `version + 1`,
    entidades recriadas) e prova que `element_ref` atravessa — é a garantia central da
    Decisão 1 do ADR-0058: o elo sobrevive à revisão, ao contrário do `Entity.id`.
    """
    scene = build_synthetic_scene()
    scene.entities[0].element_ref = "EL-001"
    scene.entities[1].element_ref = "EL-001"
    original_entity_id = scene.entities[0].id

    approved_scene = SceneRevision.model_validate(
        {
            **scene.model_dump(mode="json"),
            "id": str(new_uuid7()),
            "version": scene.version + 1,
            "approved": True,
        }
    )

    assert approved_scene.id != scene.id
    assert approved_scene.version == scene.version + 1
    # As entidades são recriadas com os mesmos `id`s de linha (o dump preserva `id`).
    assert approved_scene.entities[0].id == original_entity_id
    assert approved_scene.entities[0].element_ref == "EL-001"
    assert approved_scene.entities[1].element_ref == "EL-001"


def test_export_gate_does_not_change_behaviour_because_of_element_ref() -> None:
    """`export_errors()`/`ensure_exportable()` não ganham nem perdem condição por causa de
    `element_ref` — o portão de exportação continua o mesmo antes e depois da Decisão 1.
    """
    baseline = build_synthetic_scene()
    baseline_errors = baseline.export_errors()

    with_refs = build_synthetic_scene()
    with_refs.entities[0].element_ref = "EL-001"
    with_refs.entities[1].element_ref = "EL-001"
    with_refs.entities[2].element_ref = "EL-002"

    assert with_refs.export_errors() == baseline_errors
    assert not any("element_ref" in error.lower() or "EL-" in error for error in baseline_errors)
    with_refs.ensure_exportable()

    # Uma entidade unresolved/approximate/exact-sem-provenance continua barrada pelo motivo
    # de sempre, `element_ref` não abre nem fecha exceção nenhuma no portão.
    with_refs.entities[0].precision = Precision.UNRESOLVED
    with pytest.raises(DomainValidationError, match="UNRESOLVED_ENTITY"):
        with_refs.ensure_exportable()


# ---------------------------------------------------------------------------
# F-047 T2b — o rótulo legível do elemento.
# ---------------------------------------------------------------------------


def _scene_with_labels(labels: dict[str, str]) -> SceneRevision:
    return SceneRevision(
        job_id=new_uuid7(),
        version=1,
        entities=[
            _entity_on_layer(LayerName.MURO, element_ref="EL-001"),
            _entity_on_layer(LayerName.ALAMBRADO, element_ref="EL-002"),
        ],
        element_labels=labels,
    )


def test_scene_accepts_a_readable_label_per_element_ref() -> None:
    """O rótulo mora na cena, por `element_ref` — nunca repetido em cada entidade."""
    scene = _scene_with_labels({"EL-001": "Muro da divisa", "EL-002": "Alambrado da quadra"})

    assert scene.element_labels == {"EL-001": "Muro da divisa", "EL-002": "Alambrado da quadra"}
    # O rótulo não vira campo de entidade: quem carrega o nome é a cena, e o traço carrega
    # só a identidade. Duas verdades sobre o mesmo nome não existem.
    assert all(not hasattr(entity, "label") for entity in scene.entities)


def test_scene_without_labels_is_valid_and_has_an_empty_map() -> None:
    """Cena sem rótulo nenhum continua válida: nomear é opcional (critério 3 da T2b)."""
    scene = _scene_with_labels({})

    assert scene.element_labels == {}


def test_label_for_an_element_ref_that_no_entity_uses_is_refused() -> None:
    """Critério 1: rótulo é nome DE elemento; sem elemento, não é nome de nada."""
    with pytest.raises(ValidationError, match="ELEMENT_LABEL_UNKNOWN_REF"):
        _scene_with_labels({"EL-009": "Elemento que não existe"})


@pytest.mark.parametrize("invalid_label", ["", "   ", "\t\n"])
def test_empty_or_blank_label_is_refused(invalid_label: str) -> None:
    """Critério 2: rótulo vazio ou só de espaço não é nome — é campo esquecido."""
    with pytest.raises(ValidationError, match="element_labels"):
        _scene_with_labels({"EL-001": invalid_label})


def test_label_longer_than_the_declared_ceiling_is_refused() -> None:
    """Critério 2: o teto é declarado no contrato, e não uma convenção da tela."""
    _scene_with_labels({"EL-001": "A" * ELEMENT_LABEL_MAX_LENGTH})

    with pytest.raises(ValidationError, match="element_labels"):
        _scene_with_labels({"EL-001": "A" * (ELEMENT_LABEL_MAX_LENGTH + 1)})


def test_label_key_outside_the_element_ref_pattern_is_refused() -> None:
    """A chave é um `element_ref`, com a mesma forma que a entidade carrega."""
    with pytest.raises(ValidationError, match="element_labels"):
        SceneRevision(
            job_id=new_uuid7(),
            version=1,
            entities=[_entity_on_layer(LayerName.MURO, element_ref="EL-001")],
            element_labels={"muro-da-divisa": "Muro da divisa"},
        )


def test_two_elements_with_the_same_label_are_still_two_elements() -> None:
    """Critério 5, no núcleo: rótulo é texto livre e NÃO é identidade.

    Dois refs distintos com o mesmo nome continuam sendo dois elementos — em nenhum lugar o
    rótulo agrupa, casa ou soma. É a rejeição central do ADR-0058 aplicada ao campo novo.
    """
    scene = _scene_with_labels({"EL-001": "Alambrado da quadra", "EL-002": "Alambrado da quadra"})

    refs = {entity.element_ref for entity in scene.entities}
    assert refs == {"EL-001", "EL-002"}
    assert len(scene.element_labels) == 2
    assert scene.element_labels["EL-001"] == scene.element_labels["EL-002"]


def test_label_survives_the_new_revision_created_on_approval() -> None:
    """Critério 4: o nome atravessa a revisão nova, como o `element_ref` atravessa."""
    scene = build_synthetic_scene()
    scene.entities[0].element_ref = "EL-001"
    scene.entities[1].element_ref = "EL-001"
    scene.element_labels = {"EL-001": "Alambrado da quadra"}

    approved_scene = SceneRevision.model_validate(
        {
            **scene.model_dump(mode="json"),
            "id": str(new_uuid7()),
            "version": scene.version + 1,
            "approved": True,
        }
    )

    assert approved_scene.element_labels == {"EL-001": "Alambrado da quadra"}


def test_export_gate_does_not_change_behaviour_because_of_the_label() -> None:
    """O rótulo é apresentação: não abre nem fecha exceção no portão de exportação."""
    baseline = build_synthetic_scene()
    baseline_errors = baseline.export_errors()

    with_label = build_synthetic_scene()
    with_label.entities[0].element_ref = "EL-001"
    with_label.element_labels = {"EL-001": "Alambrado da quadra"}

    assert with_label.export_errors() == baseline_errors
    with_label.ensure_exportable()


# Digests âncora dos arquivos determinísticos do pacote exportado, calculados a partir do
# `run_synthetic_pipeline` ANTES desta tarefa (`git stash` do `models.py` alterado, mesma
# fixture). `desenho.dxf` e `auditoria.json` carregam timestamps/GUIDs que o ezdxf já
# variava a cada corrida, antes desta mudança (`$TDCREATE`, `$FINGERPRINTGUID`,
# `generated_at`, `dxf_sha256`) — por isso não entram na âncora byte a byte; o resto do
# conteúdo de `auditoria.json` entra, com esses campos removidos.
#
# `preview.png` NÃO tem âncora byte a byte de propósito (issue #163): o PNG é RENDERIZADO,
# e a rasterização de fonte muda entre plataformas — a âncora original, capturada em macOS,
# nunca bateu no Ubuntu do runner e manteve a quality da main vermelha por seis dias sem
# que o hash divergente significasse regressão nenhuma. O preview é verificado por
# determinismo dentro da corrida (duas execuções → bytes idênticos) e por estrutura; a
# não-regressão byte a byte mora nos artefatos determinísticos acima.
_QUANTITIES_SHA256_BEFORE_F047_T1 = (
    "5c357a521777cd5b48b569f343c1ae14fb25a49803e0e6caf92733e1694969fb"
)
_HYPOTHESES_SHA256_BEFORE_F047_T1 = (
    "9dd5a891a61c2139d0d28614a9fe66322384c3536feb6446f53de720e392f6d1"
)
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_AUDIT_BEFORE_F047_T1 = {
    "checks": {
        "entity_count_matches": True,
        "ezdxf_auditor_clean": True,
        "finite_extents": True,
        "layers_present": True,
        "reopened": True,
        "scene_still_exportable": True,
        "topology_valid": True,
        "units_are_metres": True,
        "xdata_complete": True,
    },
    "entity_count": 9,
    "errors": [],
    "extents": {
        "max": [32.240010509704064, 29.272131226405396],
        "min": [-3.372131226405396, -0.29001050970406694],
    },
    "revision_version": 1,
    "scene_id": "01900000-0000-7000-8000-000000000200",
    "status": "approved",
    "warnings": [],
}


def test_scene_without_element_ref_produces_the_same_export_package_as_before(
    tmp_path: Path,
) -> None:
    """Não-regressão (critério mais importante da T1): a fixture sintética não declara
    `element_ref`, e o pacote exportado tem que sair idêntico ao que saía antes deste campo
    existir. `quantitativos.csv` e `hipoteses.json` são determinísticos entre plataformas e
    comparados byte a byte contra a âncora capturada antes da mudança; `auditoria.json` é
    comparado igual, com os dois campos que já variavam por corrida (ver comentário acima)
    excluídos dos dois lados. `preview.png` é render — determinístico dentro da corrida,
    não entre plataformas (issue #163): é verificado por estrutura e por duas execuções
    idênticas, nunca por âncora.
    """
    result = run_synthetic_pipeline(tmp_path / "primeira")

    with ZipFile(result.package_path) as archive:
        assert (
            hashlib.sha256(archive.read("quantitativos.csv")).hexdigest()
            == _QUANTITIES_SHA256_BEFORE_F047_T1
        )
        assert (
            hashlib.sha256(archive.read("hipoteses.json")).hexdigest()
            == _HYPOTHESES_SHA256_BEFORE_F047_T1
        )
        preview = archive.read("preview.png")
        assert preview.startswith(_PNG_SIGNATURE)
        assert len(preview) > 1024, "preview vazio ou trivial não é um render da cena"
        auditoria = json.loads(archive.read("auditoria.json"))
        auditoria.pop("generated_at")
        auditoria.pop("dxf_sha256")
        # Extents do DXF incluem caixas de TEXTO, e métrica de fonte varia por plataforma
        # (issue #163, segunda dependência — ~2 mm medidos entre macOS e o Ubuntu do
        # runner, escondidos atrás da âncora do preview enquanto ela existiu). Comparação
        # exata em tudo, extents com tolerância declarada de 1 cm por componente: pega
        # regressão real de layout, ignora rasterização.
        extents = auditoria.pop("extents")
        esperado = dict(_AUDIT_BEFORE_F047_T1)
        extents_esperados = cast("dict[str, list[float]]", esperado.pop("extents"))
        assert auditoria == esperado
        for eixo in ("min", "max"):
            for valor, referencia in zip(extents[eixo], extents_esperados[eixo], strict=True):
                assert abs(valor - referencia) < 0.01, (
                    f"extents.{eixo} fora da tolerância de plataforma: {valor} vs {referencia}"
                )

    segunda = run_synthetic_pipeline(tmp_path / "segunda")
    with ZipFile(segunda.package_path) as archive:
        assert archive.read("preview.png") == preview, (
            "o render do preview deixou de ser determinístico dentro da mesma plataforma"
        )
