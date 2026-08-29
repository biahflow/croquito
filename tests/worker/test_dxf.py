import csv
import json
import math
from pathlib import Path
from zipfile import ZipFile

import pytest
from ezdxf.filemanagement import readfile

from croquito_core.errors import DomainValidationError
from croquito_core.ids import new_uuid7
from croquito_core.models import (
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
from croquito_worker.dxf import APP_ID, AutoDecidedReadingAudit, export_scene_package
from croquito_worker.pipeline import run_synthetic_pipeline
from croquito_worker.synthetic import FIELD_HEIGHT, FIELD_WIDTH, build_synthetic_scene


def test_synthetic_pipeline_creates_audited_package(tmp_path: Path) -> None:
    result = run_synthetic_pipeline(tmp_path)

    assert result.audit.status == "approved"
    assert result.audit.errors == []
    assert all(result.audit.checks.values())
    assert result.dxf_path.is_file()
    assert result.preview_path.is_file()
    assert result.preview_path.stat().st_size > 0

    document = readfile(result.dxf_path)
    assert document.header["$INSUNITS"] == 6
    assert all(entity.has_xdata(APP_ID) for entity in document.modelspace())
    dimensions = list(document.modelspace().query("DIMENSION"))
    assert [dimension.dxf.angle for dimension in dimensions] == [0.0, 90.0]

    with ZipFile(result.package_path) as archive:
        assert set(archive.namelist()) == {
            "desenho.dxf",
            "preview.png",
            "auditoria.json",
            "quantitativos.csv",
            "hipoteses.json",
        }


def test_a_auditoria_so_ganha_a_lista_nominal_quando_houve_cota_automatica(
    tmp_path: Path,
) -> None:
    """Sem auto-decisão a auditoria sai exatamente como sempre saiu; com ela, nomeada.

    A chave é acrescentada só quando existe o que listar: um `[]` fixo mudaria o conteúdo
    de todo pacote publicado por um modo que nem está ligado.
    """
    without = run_synthetic_pipeline(tmp_path / "sem")
    audit_without = json.loads(without.audit_path.read_text(encoding="utf-8"))
    assert "auto_decided_readings" not in audit_without

    scene = build_synthetic_scene()
    with_auto = export_scene_package(
        scene,
        tmp_path / "com",
        auto_decided_readings=[
            AutoDecidedReadingAudit(
                reading_id="rd_1111111111111111",
                decision_id="hd_1111111111111111",
                raw_text="25,90",
                value_si="25.90",
                unit="m",
                proposal_id="vp_1111111111111111",
                reading_confidence=0.85,
                association_confidence=0.9,
                threshold=0.6,
                score_version="1.0.0",
            ),
            # Tier de anotação (ADR-0044, D1a): entrou com UMA testemunha e SEM vínculo,
            # e o pacote diz as duas coisas — quem confere não aceita de um rótulo o que
            # aceita de uma medida, e precisa ver que nada foi preso ao elemento.
            AutoDecidedReadingAudit(
                reading_id="rd_2222222222222222",
                decision_id="hd_2222222222222222",
                raw_text="h=3,80",
                value_si="3.80",
                unit="m",
                proposal_id=None,
                reading_confidence=0.45,
                association_confidence=0.9,
                threshold=0.6,
                score_version="1.0.0",
                tier="anotacao",
                probable_proposal_id="vp_2222222222222222",
            ),
        ],
    )
    audit_with = json.loads(with_auto.audit_path.read_text(encoding="utf-8"))
    assert audit_with["status"] == "approved"
    assert audit_with["auto_decided_readings"] == [
        {
            "reading_id": "rd_1111111111111111",
            "decision_id": "hd_1111111111111111",
            "raw_text": "25,90",
            "value_si": "25.90",
            "unit": "m",
            "proposal_id": "vp_1111111111111111",
            "reading_confidence": 0.85,
            "association_confidence": 0.9,
            "threshold": 0.6,
            "score_version": "1.0.0",
            "tier": "cota",
            "probable_proposal_id": None,
        },
        {
            "reading_id": "rd_2222222222222222",
            "decision_id": "hd_2222222222222222",
            "raw_text": "h=3,80",
            "value_si": "3.80",
            "unit": "m",
            "proposal_id": None,
            "reading_confidence": 0.45,
            "association_confidence": 0.9,
            "threshold": 0.6,
            "score_version": "1.0.0",
            "tier": "anotacao",
            "probable_proposal_id": "vp_2222222222222222",
        },
    ]
    # O portão de exportação não muda: a listagem é auditoria, não permissão.
    assert audit_with["checks"] == audit_without["checks"]


def test_export_refuses_unapproved_scene(tmp_path: Path) -> None:
    scene = build_synthetic_scene()
    scene.approved = False

    with pytest.raises(DomainValidationError, match="SCENE_NOT_APPROVED"):
        export_scene_package(scene, tmp_path)


def _quantities_rows(tmp_path: Path) -> list[dict[str, str]]:
    with open(tmp_path / "quantitativos.csv", encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def test_element_ref_agrupa_linhas_somando_comprimento_e_pegando_a_pior_precisao(
    tmp_path: Path,
) -> None:
    """F-047 T3, critérios 1-4: coluna aditiva, grupo vira uma linha com grandezas somadas,
    a pior precisão do grupo, e quem não declarou ref continua uma linha por entidade."""
    scene = build_synthetic_scene()
    campo_entities = [entity for entity in scene.entities if entity.layer == LayerName.CAMPO]
    assert len(campo_entities) == 4
    top, right, bottom, left = campo_entities

    top.element_ref = "EL-000100"
    right.element_ref = "EL-000100"
    right.precision = Precision.DERIVED  # top continua exact: o grupo deve virar a pior.

    # Reconstrói para forçar a invariante de camada compartilhada do ADR-0058 a rodar de
    # novo (validate_assignment não repete o validador de nível de cena ao mutar campo).
    scene = SceneRevision.model_validate(scene.model_dump())

    export_scene_package(scene, tmp_path)
    with open(tmp_path / "quantitativos.csv", encoding="utf-8", newline="") as stream:
        fieldnames = csv.DictReader(stream).fieldnames
    rows = _quantities_rows(tmp_path)

    # Coluna aditiva: ao lado de entity_id, nunca no lugar dele.
    assert fieldnames == [
        "entity_id",
        "element_ref",
        "layer",
        "kind",
        "precision",
        "length_m",
        "perimeter_m",
        "area_m2",
    ]

    grouped = [row for row in rows if row["element_ref"] == "EL-000100"]
    assert len(grouped) == 1
    row = grouped[0]
    assert row["entity_id"] == "; ".join(sorted([str(top.id), str(right.id)]))
    assert row["layer"] == "CAMPO"
    assert row["kind"] == "line"
    assert row["precision"] == "derived"  # a pior entre exact e derived, nunca promovida.
    assert math.isclose(float(row["length_m"]), FIELD_WIDTH + FIELD_HEIGHT, rel_tol=1e-6)
    assert row["perimeter_m"] == ""
    assert row["area_m2"] == ""

    # bottom/left não declararam ref: continuam uma linha cada, com a coluna nova vazia.
    solo_rows = {row["entity_id"]: row for row in rows if row["element_ref"] == ""}
    assert str(bottom.id) in solo_rows
    assert str(left.id) in solo_rows
    assert solo_rows[str(bottom.id)]["precision"] == "exact"
    assert math.isclose(float(solo_rows[str(bottom.id)]["length_m"]), FIELD_WIDTH, rel_tol=1e-6)


def test_element_ref_agrupa_circulos_somando_perimetro_e_area(tmp_path: Path) -> None:
    """F-047 T3, critério 2: perímetro e área também somam entre si dentro do grupo."""
    provenance = Provenance(
        source_type="synthetic_test", source_ids=["fixture:f-047-t3"], summary_code="TEST_FIXTURE"
    )
    circle_a = Entity(
        kind=EntityKind.CIRCLE,
        layer=LayerName.EQUIPAMENTOS,
        precision=Precision.EXACT,
        geometry=CircleGeometry(center=Point2D(x=0, y=0), radius=1.0),
        provenance=provenance,
        element_ref="EL-000200",
    )
    circle_b = Entity(
        kind=EntityKind.CIRCLE,
        layer=LayerName.EQUIPAMENTOS,
        precision=Precision.EXACT,
        geometry=CircleGeometry(center=Point2D(x=5, y=0), radius=2.0),
        provenance=provenance,
        element_ref="EL-000200",
    )
    scene = SceneRevision(
        job_id=new_uuid7(),
        version=1,
        approved=True,
        entities=[circle_a, circle_b],
    )

    export_scene_package(scene, tmp_path, package_stem="circulos-agrupados")
    rows = _quantities_rows(tmp_path)

    assert len(rows) == 1
    row = rows[0]
    expected_perimeter = 2 * math.pi * 1.0 + 2 * math.pi * 2.0
    expected_area = math.pi * 1.0**2 + math.pi * 2.0**2
    assert row["length_m"] == ""
    assert math.isclose(float(row["perimeter_m"]), expected_perimeter, rel_tol=1e-6)
    assert math.isclose(float(row["area_m2"]), expected_area, rel_tol=1e-6)


def test_croqui_sem_element_ref_nao_ganha_a_coluna(tmp_path: Path) -> None:
    """F-047 T3, critério 5: sem nenhuma identidade declarada, a coluna nem aparece."""
    scene = build_synthetic_scene()
    export_scene_package(scene, tmp_path)

    with open(tmp_path / "quantitativos.csv", encoding="utf-8", newline="") as stream:
        header = stream.readline().strip()

    assert header == "entity_id,layer,kind,precision,length_m,perimeter_m,area_m2"
    assert "element_ref" not in header


def test_polilinha_aberta_produz_comprimento_sem_perimetro_nem_area(tmp_path: Path) -> None:
    """F-047 T3b, critério 1: polilinha aberta (um muro/alambrado) contribui `length_m`
    como a soma euclidiana dos segmentos, e nenhum `perimeter_m`/`area_m2` — abrir região
    não é fechá-la, e inventar área seria geometria fabricada."""
    provenance = Provenance(
        source_type="synthetic_test", source_ids=["fixture:f-047-t3b"], summary_code="TEST_FIXTURE"
    )
    wall = Entity(
        kind=EntityKind.POLYLINE,
        layer=LayerName.MURO,
        precision=Precision.EXACT,
        geometry=PolylineGeometry(
            points=[
                Point2D(x=0, y=0),
                Point2D(x=3, y=0),
                Point2D(x=3, y=4),
            ],
            closed=False,
        ),
        provenance=provenance,
    )
    scene = SceneRevision(job_id=new_uuid7(), version=1, approved=True, entities=[wall])

    export_scene_package(scene, tmp_path, package_stem="polilinha-aberta")
    rows = _quantities_rows(tmp_path)

    assert len(rows) == 1
    row = rows[0]
    # (0,0)->(3,0) = 3.0 ; (3,0)->(3,4) = 4.0 ; soma = 7.0.
    assert math.isclose(float(row["length_m"]), 7.0, rel_tol=1e-6)
    assert row["perimeter_m"] == ""
    assert row["area_m2"] == ""


def test_polilinha_fechada_continua_sem_length_m(tmp_path: Path) -> None:
    """F-047 T3b, critério 2: polilinha fechada não muda — continua só perímetro/área,
    sem ganhar `length_m`."""
    provenance = Provenance(
        source_type="synthetic_test", source_ids=["fixture:f-047-t3b"], summary_code="TEST_FIXTURE"
    )
    square = Entity(
        kind=EntityKind.POLYLINE,
        layer=LayerName.MURO,
        precision=Precision.EXACT,
        geometry=PolylineGeometry(
            points=[
                Point2D(x=0, y=0),
                Point2D(x=2, y=0),
                Point2D(x=2, y=2),
                Point2D(x=0, y=2),
            ],
            closed=True,
        ),
        provenance=provenance,
    )
    scene = SceneRevision(job_id=new_uuid7(), version=1, approved=True, entities=[square])

    export_scene_package(scene, tmp_path, package_stem="polilinha-fechada")
    rows = _quantities_rows(tmp_path)

    assert len(rows) == 1
    row = rows[0]
    assert row["length_m"] == ""
    assert math.isclose(float(row["perimeter_m"]), 8.0, rel_tol=1e-6)
    assert math.isclose(float(row["area_m2"]), 4.0, rel_tol=1e-6)


def test_element_ref_agrupa_polilinha_aberta_somando_comprimento(tmp_path: Path) -> None:
    """F-047 T3b, critério 3: o agrupamento por `element_ref` da T3 continua valendo —
    polilinha aberta soma comprimento com as demais entidades do grupo, e a precisão da
    linha agrupada continua sendo a pior do grupo."""
    provenance = Provenance(
        source_type="synthetic_test", source_ids=["fixture:f-047-t3b"], summary_code="TEST_FIXTURE"
    )
    open_polyline = Entity(
        kind=EntityKind.POLYLINE,
        layer=LayerName.ALAMBRADO,
        precision=Precision.EXACT,
        geometry=PolylineGeometry(
            points=[Point2D(x=0, y=0), Point2D(x=3, y=0), Point2D(x=3, y=4)],
            closed=False,
        ),
        provenance=provenance,
        element_ref="EL-000300",
    )
    line = Entity(
        kind=EntityKind.LINE,
        layer=LayerName.ALAMBRADO,
        precision=Precision.DERIVED,
        geometry=LineGeometry(start=Point2D(x=3, y=4), end=Point2D(x=3, y=9)),
        provenance=provenance,
        element_ref="EL-000300",
    )
    scene = SceneRevision(
        job_id=new_uuid7(), version=1, approved=True, entities=[open_polyline, line]
    )

    export_scene_package(scene, tmp_path, package_stem="polilinha-aberta-agrupada")
    rows = _quantities_rows(tmp_path)

    assert len(rows) == 1
    row = rows[0]
    assert math.isclose(float(row["length_m"]), 7.0 + 5.0, rel_tol=1e-6)
    assert row["perimeter_m"] == ""
    assert row["area_m2"] == ""
    assert row["precision"] == "derived"  # a pior entre exact e derived.
