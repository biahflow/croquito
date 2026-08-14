"""O traçado em lote entrega o desenho que o croqui descreve, não o papel torto.

A fixture reproduz os três defeitos medidos no Guaxindiba real de 2026-08-10:
anisotropia de 40% entre eixos, patamar desenhado com menos da metade da profundidade
cotada (6,5 contra 14,50) e coordenadas de imagem com Y para baixo — que entregaram um
DXF espelhado. Cada defeito vira um assert.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal
from uuid import UUID

import pytest
from ezdxf.entities.dimension import Dimension
from ezdxf.filemanagement import readfile
from pydantic import ValidationError

from croquito_core.models import (
    CircleGeometry,
    DiameterDimensionGeometry,
    DimensionGeometry,
    Entity,
    EntityKind,
    IssueSeverity,
    IssueStatus,
    LayerName,
    LineGeometry,
    Measurement,
    MeasurementKind,
    PolylineGeometry,
    Precision,
    SceneRevision,
    TextGeometry,
)
from croquito_worker.criteria import FALLBACK_CRITERION_MESSAGE, ScopeCriterion
from croquito_worker.dxf import export_scene_package
from croquito_worker.geometry_solver import BandSeparation
from croquito_worker.review import (
    DimensionReading,
    EvidenceRegion,
    HumanDecision,
    PixelBox,
    ReadingStatus,
    ReviewPacket,
    SceneApproval,
)
from croquito_worker.tracing import (
    DerivedDimensionRequest,
    KeepApartPair,
    TraceAcceptance,
    TraceDetailGroup,
    TraceSolveResult,
    approve_trace,
    solve_trace,
    write_approved_trace_revision,
)
from croquito_worker.vision import (
    PixelCircle,
    PixelLine,
    PixelPoint,
    PixelPolyline,
    VisionProposal,
)

DATASET_ID = "guaxindiba-sintetico-v1"
DIGEST = "ab" * 32

# Escalas de desenho da fixture, propositalmente anisotrópicas: 10 px/m no eixo X e
# 14 px/m no eixo Y. O patamar é desenhado com ~6,5 m visuais contra 14,50 m cotados.
CAMPO_LEFT_PX = 100.0
CAMPO_TOP_PX = 100.0
CAMPO_RIGHT_PX = CAMPO_LEFT_PX + 25.90 * 10
CAMPO_BOTTOM_PX = CAMPO_TOP_PX + 21.75 * 14
PATAMAR_BOTTOM_PX = CAMPO_BOTTOM_PX + 6.5 * 14
DIVIDER_1_PX = CAMPO_LEFT_PX + 9.55 * 10
DIVIDER_2_PX = DIVIDER_1_PX + 3.86 * 10

CAMPO_PROPOSAL = "vp_" + "a" * 16
PATAMAR_ESQ_PROPOSAL = "vp_" + "b" * 16
PATAMAR_CENTRO_PROPOSAL = "vp_" + "c" * 16
PATAMAR_DIR_PROPOSAL = "vp_" + "d" * 16
PORTAO_PROPOSAL = "vp_" + "e" * 16
CIRCULO_PROPOSAL = "vp_" + "f" * 16

LARGURA_READING = "rd_" + "1" * 16
ALTURA_READING = "rd_" + "2" * 16
PROFUNDIDADE_READING = "rd_" + "3" * 16
PAT_ESQ_READING = "rd_" + "4" * 16
PAT_CENTRO_READING = "rd_" + "5" * 16
PAT_DIR_READING = "rd_" + "6" * 16


def _rect(left: float, top: float, right: float, bottom: float) -> PixelPolyline:
    return PixelPolyline(
        points=[
            PixelPoint(x=left, y=top),
            PixelPoint(x=right, y=top),
            PixelPoint(x=right, y=bottom),
            PixelPoint(x=left, y=bottom),
        ],
        closed=True,
    )


def _proposals() -> list[VisionProposal]:
    return [
        VisionProposal(
            id=CAMPO_PROPOSAL,
            kind="contour",
            geometry=_rect(CAMPO_LEFT_PX, CAMPO_TOP_PX, CAMPO_RIGHT_PX, CAMPO_BOTTOM_PX),
            algorithm="fixture",
            quality_score=0.9,
            label="Campo sintético",
            layer_hint="CAMPO",
        ),
        VisionProposal(
            id=PATAMAR_ESQ_PROPOSAL,
            kind="contour",
            geometry=_rect(CAMPO_LEFT_PX, CAMPO_BOTTOM_PX, DIVIDER_1_PX, PATAMAR_BOTTOM_PX),
            algorithm="fixture",
            quality_score=0.9,
            label="Patamar de concreto esquerdo",
            layer_hint="PATAMAR",
        ),
        VisionProposal(
            id=PATAMAR_CENTRO_PROPOSAL,
            kind="contour",
            geometry=_rect(DIVIDER_1_PX, CAMPO_BOTTOM_PX, DIVIDER_2_PX, PATAMAR_BOTTOM_PX),
            algorithm="fixture",
            quality_score=0.9,
            label="Patamar central (entrada)",
            layer_hint="PATAMAR",
        ),
        VisionProposal(
            id=PATAMAR_DIR_PROPOSAL,
            kind="contour",
            geometry=_rect(DIVIDER_2_PX, CAMPO_BOTTOM_PX, CAMPO_RIGHT_PX, PATAMAR_BOTTOM_PX),
            algorithm="fixture",
            quality_score=0.9,
            label="Faixa de área vegetativa",
            layer_hint="PATAMAR",
        ),
        VisionProposal(
            id=PORTAO_PROPOSAL,
            kind="line",
            geometry=PixelLine(
                start=PixelPoint(x=300.0, y=CAMPO_TOP_PX),
                end=PixelPoint(x=330.0, y=CAMPO_TOP_PX),
            ),
            algorithm="fixture",
            quality_score=0.9,
            label="Portão norte",
            layer_hint="PORTAO",
        ),
        VisionProposal(
            id=CIRCULO_PROPOSAL,
            kind="circle",
            geometry=PixelCircle(
                center=PixelPoint(
                    x=(CAMPO_LEFT_PX + CAMPO_RIGHT_PX) / 2,
                    y=(CAMPO_TOP_PX + CAMPO_BOTTOM_PX) / 2,
                ),
                radius=30.0,
            ),
            algorithm="fixture",
            quality_score=0.9,
            label="Círculo central",
        ),
    ]


def _reading(
    identifier: str,
    *,
    value: str,
    kind: str,
    centre: tuple[int, int],
    confirmed: bool = True,
) -> DimensionReading:
    decision = (
        HumanDecision(
            decision_id="hd_" + identifier[3:11] + "00000000",
            action="confirm",
            reviewer_id="eng-teste",
            reviewer_role="engineer",
            decided_at=datetime(2026, 8, 10, 12, 0, tzinfo=UTC),
        )
        if confirmed
        else None
    )
    return DimensionReading(
        id=identifier,
        evidence=EvidenceRegion(
            dataset_id=DATASET_ID,
            page_number=1,
            image_sha256=DIGEST,
            bbox=PixelBox(
                left=centre[0] - 10,
                top=centre[1] - 10,
                right=centre[0] + 10,
                bottom=centre[1] + 10,
            ),
        ),
        raw_text=value.replace(".", ","),
        value_si=Decimal(value),
        unit="m",
        kind=kind,
        written_decimals=2,
        target_hint="fixture",
        extractor="fixture",
        extractor_version="v1",
        status=ReadingStatus.CONFIRMED if confirmed else ReadingStatus.PROPOSED,
        decision=decision,
    )


def _packet(*, confirmed: bool = True) -> ReviewPacket:
    return ReviewPacket(
        dataset_id=DATASET_ID,
        page_number=1,
        image_sha256=DIGEST,
        readings=[
            _reading(LARGURA_READING, value="25.90", kind="width", centre=(229, 95)),
            _reading(ALTURA_READING, value="21.75", kind="height", centre=(95, 252)),
            _reading(
                PROFUNDIDADE_READING,
                value="14.50",
                kind="height",
                centre=(95, 450),
                confirmed=confirmed,
            ),
            _reading(PAT_ESQ_READING, value="9.55", kind="length", centre=(148, 500)),
            _reading(PAT_CENTRO_READING, value="3.86", kind="length", centre=(215, 500)),
            _reading(PAT_DIR_READING, value="12.49", kind="length", centre=(296, 500)),
        ],
        safety_notes=["Fixture local.", "Revisão humana obrigatória."],
    )


def _acceptance() -> TraceAcceptance:
    return TraceAcceptance(
        acceptance_id="ta_" + "9" * 16,
        reviewer_id="eng-teste",
        reviewer_role="engineer",
        decided_at=datetime(2026, 8, 10, 12, 30, tzinfo=UTC),
        proposal_ids=[
            CAMPO_PROPOSAL,
            PATAMAR_ESQ_PROPOSAL,
            PATAMAR_CENTRO_PROPOSAL,
            PATAMAR_DIR_PROPOSAL,
            PORTAO_PROPOSAL,
            CIRCULO_PROPOSAL,
        ],
        hatch_proposal_ids=[PATAMAR_DIR_PROPOSAL],
    )


def _associations() -> dict[str, str]:
    return {
        LARGURA_READING: CAMPO_PROPOSAL,
        ALTURA_READING: CAMPO_PROPOSAL,
        PROFUNDIDADE_READING: PATAMAR_ESQ_PROPOSAL,
        PAT_ESQ_READING: PATAMAR_ESQ_PROPOSAL,
        PAT_CENTRO_READING: PATAMAR_CENTRO_PROPOSAL,
        PAT_DIR_READING: PATAMAR_DIR_PROPOSAL,
    }


def _solve() -> TraceSolveResult:
    return solve_trace(
        _packet(),
        _proposals(),
        _acceptance(),
        confirmed_associations=_associations(),
        image_width=600,
        image_height=700,
        title="CAMPO GUAXINDIBA SINTETICO",
    )


def _entity_of(scene: SceneRevision, proposal_id: str) -> Entity:
    traced_kinds = {EntityKind.LINE, EntityKind.POLYLINE, EntityKind.CIRCLE}
    for entity in scene.entities:
        if (
            entity.provenance
            and proposal_id in entity.provenance.source_ids
            and entity.kind in traced_kinds
        ):
            return entity
    raise AssertionError(f"entidade do traçado não encontrada: {proposal_id}")


def _bbox(geometry: object) -> tuple[float, float, float, float]:
    assert isinstance(geometry, PolylineGeometry)
    xs = [point.x for point in geometry.points]
    ys = [point.y for point in geometry.points]
    return min(xs), min(ys), max(xs), max(ys)


def _title_texts(scene: SceneRevision) -> list[str]:
    return [
        entity.geometry.text
        for entity in scene.entities
        if isinstance(entity.geometry, TextGeometry)
        and entity.provenance is not None
        and entity.provenance.summary_code == "TRACE_TITLE_BLOCK"
    ]


def test_cota_manda_sobre_o_tracado() -> None:
    """As medidas cotadas substituem a métrica projetada dos pixels."""
    result = _solve()
    assert result.status == "solved_unapproved", result.blockers
    assert result.scene is not None

    campo = _entity_of(result.scene, CAMPO_PROPOSAL)
    min_x, min_y, max_x, max_y = _bbox(campo.geometry)
    assert max_x - min_x == pytest.approx(25.90, abs=0.01)
    assert max_y - min_y == pytest.approx(21.75, abs=0.01)

    # O defeito medido no Guaxindiba real: patamar desenhado com 6,5 m mas cotado 14,50.
    patamar = _entity_of(result.scene, PATAMAR_ESQ_PROPOSAL)
    _, pat_min_y, _, pat_max_y = _bbox(patamar.geometry)
    assert pat_max_y - pat_min_y == pytest.approx(14.50, abs=0.01)

    esq = _bbox(_entity_of(result.scene, PATAMAR_ESQ_PROPOSAL).geometry)
    centro = _bbox(_entity_of(result.scene, PATAMAR_CENTRO_PROPOSAL).geometry)
    dir_ = _bbox(_entity_of(result.scene, PATAMAR_DIR_PROPOSAL).geometry)
    assert esq[2] - esq[0] == pytest.approx(9.55, abs=0.01)
    assert centro[2] - centro[0] == pytest.approx(3.86, abs=0.01)
    assert dir_[2] - dir_[0] == pytest.approx(12.49, abs=0.01)

    assert all(residual.passed for residual in result.residuals)


def test_orientacao_imagem_vira_cad() -> None:
    """Pixel cresce para baixo; o DXF cresce para cima. O portão norte fica no norte."""
    result = _solve()
    assert result.scene is not None
    portao = _entity_of(result.scene, PORTAO_PROPOSAL)
    assert isinstance(portao.geometry, LineGeometry)
    patamar = _bbox(_entity_of(result.scene, PATAMAR_ESQ_PROPOSAL).geometry)
    campo = _bbox(_entity_of(result.scene, CAMPO_PROPOSAL).geometry)
    # No croqui o portão está no muro norte e o patamar ao sul do campo.
    assert portao.geometry.start.y > campo[3] - 0.01
    assert patamar[3] <= campo[1] + 0.01


def test_precisao_declarada_e_aceite_em_lote() -> None:
    """Distância interna toda cotada sai exact; o resto permanece approximate aceito."""
    result = _solve()
    assert result.scene is not None
    campo = _entity_of(result.scene, CAMPO_PROPOSAL)
    assert campo.precision is Precision.EXACT
    assert campo.layer is LayerName.CAMPO

    portao = _entity_of(result.scene, PORTAO_PROPOSAL)
    assert portao.precision is Precision.APPROXIMATE
    assert portao.layer is LayerName.APROXIMADO
    assert portao.id in result.scene.accepted_approximation_ids

    circulo = _entity_of(result.scene, CIRCULO_PROPOSAL)
    assert circulo.precision is Precision.APPROXIMATE
    assert isinstance(circulo.geometry, CircleGeometry)
    assert circulo.id in result.scene.accepted_approximation_ids

    assert result.exact_entity_count == 4
    assert result.approximate_entity_count == 2


def test_prancha_dimensoes_hachura_e_carimbo(tmp_path: Path) -> None:
    """O pacote aprovado carrega cotas desenhadas, hachura declarada e carimbo."""
    result = _solve()
    assert result.scene is not None

    dimension_count = sum(
        1 for entity in result.scene.entities if entity.kind is EntityKind.DIMENSION
    )
    assert dimension_count == 6

    hatched = _entity_of(result.scene, PATAMAR_DIR_PROPOSAL)
    assert hatched.fill == "hatch"

    titles = _title_texts(result.scene)
    assert any("CAMPO GUAXINDIBA SINTETICO" in text for text in titles)
    assert any("ORIGEM (0,0)" in text for text in titles)

    approval = SceneApproval(
        approval_id="ap_" + "7" * 16,
        source_scene_id=result.scene.id,
        reviewer_id="eng-teste",
        reviewer_role="engineer",
        decided_at=datetime(2026, 8, 10, 13, 0, tzinfo=UTC),
        source_evidence_checked=True,
        geometry_checked=True,
        limitations_acknowledged=True,
        statement="Traçado conferido contra o croqui sintético de fixture.",
    )
    approved = approve_trace(result, approval)
    _, approval_path = write_approved_trace_revision(approved, tmp_path)
    export = export_scene_package(
        approved.scene,
        tmp_path,
        package_stem="tracado-teste",
        extra_package_files=[approval_path],
    )
    assert export.audit.status == "approved"
    assert export.preview_path.is_file()
    assert export.preview_path.stat().st_size > 0

    document = readfile(export.dxf_path)
    modelspace = document.modelspace()
    assert len(modelspace.query("HATCH")) == 1
    assert len(modelspace.query("DIMENSION")) == 6
    hatch = modelspace.query("HATCH").first
    assert hatch is not None
    assert hatch.has_xdata("CROQUITO")


def test_rotulos_nao_cobrem_o_desenho() -> None:
    """Todo elemento rotulado vira balão numerado + linha de legenda (nome inline aposentado).

    O "Patamar de concreto esquerdo" saiu inline na prancha real do Guaxindiba enquanto os
    outros cinco elementos saíram como balão — o usuário arbitrou consistência keynote em
    2026-08-13: sem exceção, todo elemento rotulado segue o mesmo caminho.
    """
    result = _solve()
    assert result.scene is not None
    scene = result.scene

    inline = [
        entity
        for entity in scene.entities
        if entity.provenance is not None
        and entity.provenance.summary_code == "ELEMENT_LABEL_INLINE"
    ]
    assert inline == [], "nome inline foi aposentado: nenhuma anotação deve usar esse código"

    balloons = [
        entity
        for entity in scene.entities
        if entity.provenance is not None and entity.provenance.summary_code == "ELEMENT_BALLOON"
    ]
    legend = [
        entity
        for entity in scene.entities
        if entity.provenance is not None
        and entity.provenance.summary_code == "ELEMENT_LEGEND_ENTRY"
    ]

    # Os seis elementos rotulados da fixture (campo, três patamares, portão, círculo)
    # viram balão, inclusive o patamar esquerdo — que antes comportava o nome dentro dele.
    balloon_circles = [e for e in balloons if e.kind is EntityKind.CIRCLE]
    assert len(balloon_circles) == 6
    legend_texts = [e.geometry.text for e in legend if isinstance(e.geometry, TextGeometry)]
    assert len(legend_texts) == 6
    assert any("Campo sintético" in text for text in legend_texts)
    assert any("Faixa de área vegetativa" in text for text in legend_texts)
    assert any("Patamar de concreto esquerdo" in text for text in legend_texts)

    # A legenda fica fora do desenho, à direita da extensão da geometria traçada.
    traced_max_x = max(
        point.x
        for entity in scene.entities
        if isinstance(entity.geometry, PolylineGeometry)
        for point in entity.geometry.points
    )
    for entity in legend:
        assert isinstance(entity.geometry, TextGeometry)
        assert entity.geometry.insertion.x > traced_max_x

    # Nenhuma anotação sobrepõe outra: caixas de balão e números.
    boxes: list[tuple[float, float, float, float]] = []
    for entity in balloons:
        geometry = entity.geometry
        if isinstance(geometry, TextGeometry):
            boxes.append(
                (
                    geometry.insertion.x,
                    geometry.insertion.y,
                    geometry.insertion.x + len(geometry.text) * geometry.height * 0.55,
                    geometry.insertion.y + geometry.height,
                )
            )
        elif isinstance(geometry, CircleGeometry):
            boxes.append(
                (
                    geometry.center.x - geometry.radius,
                    geometry.center.y - geometry.radius,
                    geometry.center.x + geometry.radius,
                    geometry.center.y + geometry.radius,
                )
            )
    for index, first in enumerate(boxes):
        for second in boxes[index + 1 :]:
            # O número dentro do próprio balão pode (e deve) sobrepor o círculo dele.
            contained = (
                first[0] >= second[0]
                and first[1] >= second[1]
                and first[2] <= second[2]
                and first[3] <= second[3]
            ) or (
                second[0] >= first[0]
                and second[1] >= first[1]
                and second[2] <= first[2]
                and second[3] <= first[3]
            )
            apart = (
                first[2] <= second[0]
                or second[2] <= first[0]
                or first[3] <= second[1]
                or second[3] <= first[1]
            )
            assert apart or contained, f"anotações sobrepostas: {first} x {second}"


def test_associacao_explicita_continua_obrigatoria() -> None:
    """Leitura sem confirmação completa bloqueia; proposta fora do aceite bloqueia."""
    result = solve_trace(
        _packet(confirmed=False),
        _proposals(),
        _acceptance(),
        confirmed_associations=_associations(),
        image_width=600,
        image_height=700,
    )
    assert result.status == "review_required"
    assert any("TRACE_HUMAN_CONFIRMATION_REQUIRED" in blocker for blocker in result.blockers)
    assert result.scene is None

    acceptance = _acceptance()
    acceptance = acceptance.model_copy(
        update={
            "proposal_ids": [p for p in acceptance.proposal_ids if p != PATAMAR_DIR_PROPOSAL],
            "hatch_proposal_ids": [],
        }
    )
    result = solve_trace(
        _packet(),
        _proposals(),
        acceptance,
        confirmed_associations=_associations(),
        image_width=600,
        image_height=700,
    )
    assert result.status == "review_required"
    assert any("ASSOCIATED_PROPOSAL_NOT_ACCEPTED" in blocker for blocker in result.blockers)


MURO_NORTE_PROPOSAL = "vp_" + "ab" * 8
GAP_READING = "rd_" + "8" * 16
NOTA_READING = "rd_" + "9" * 16


def _muro_norte() -> VisionProposal:
    """Muro vizinho acima do campo, desenhado fora de escala (~2,9 m contra 6,60 cotados)."""
    return VisionProposal(
        id=MURO_NORTE_PROPOSAL,
        kind="line",
        geometry=PixelLine(
            start=PixelPoint(x=CAMPO_LEFT_PX, y=60.0),
            end=PixelPoint(x=CAMPO_RIGHT_PX, y=60.0),
        ),
        algorithm="fixture",
        quality_score=0.9,
        label="Muro vizinho norte",
        layer_hint="MURO",
    )


def _solve_com_muro_norte(
    *, gap_kind: str = "height", note_associations: dict[str, str] | None = None
) -> TraceSolveResult:
    packet = _packet()
    packet = packet.model_copy(
        update={
            "readings": [
                *packet.readings,
                _reading(GAP_READING, value="6.60", kind=gap_kind, centre=(230, 80)),
                _reading(NOTA_READING, value="3.80", kind="height", centre=(230, 50)),
            ]
        }
    )
    readings = {reading.id: reading for reading in packet.readings}
    nota = readings[NOTA_READING].model_copy(update={"raw_text": "muro vizinho h=3,80"})
    packet = packet.model_copy(
        update={
            "readings": [
                nota if reading.id == NOTA_READING else reading for reading in packet.readings
            ]
        }
    )
    acceptance = _acceptance()
    acceptance = acceptance.model_copy(
        update={"proposal_ids": [*acceptance.proposal_ids, MURO_NORTE_PROPOSAL]}
    )
    return solve_trace(
        packet,
        [*_proposals(), _muro_norte()],
        acceptance,
        confirmed_associations={
            **_associations(),
            GAP_READING: [MURO_NORTE_PROPOSAL, CAMPO_PROPOSAL],
        },
        note_associations=note_associations,
        image_width=600,
        image_height=700,
    )


def test_vao_entre_elementos_aplica_a_cota() -> None:
    """O 6,60 do croqui: distância entre o muro vizinho e o campo, cotada e desenhada."""
    result = _solve_com_muro_norte()
    assert result.status == "solved_unapproved", result.blockers
    assert result.scene is not None
    assert GAP_READING not in result.unapplied_reading_ids

    muro = _entity_of(result.scene, MURO_NORTE_PROPOSAL)
    assert isinstance(muro.geometry, LineGeometry)
    campo = _bbox(_entity_of(result.scene, CAMPO_PROPOSAL).geometry)
    assert muro.geometry.start.y - campo[3] == pytest.approx(6.60, abs=0.01)

    assert any(residual.code == "GAP_RESIDUAL_Y" for residual in result.residuals)
    assert all(residual.passed for residual in result.residuals)
    gap_dimensions = [
        entity
        for entity in result.scene.entities
        if entity.kind is EntityKind.DIMENSION
        and entity.provenance is not None
        and entity.provenance.summary_code == "CONFIRMED_READING_OVER_ELEMENT_GAP"
    ]
    assert len(gap_dimensions) == 1
    # Vão não vira Measurement: não é medida de uma entidade só.
    assert all(m.raw_text != "6,60" for m in result.scene.measurements)


def test_vao_sem_eixo_declarado_fica_como_nao_aplicado() -> None:
    """Vão exige eixo declarado no kind; length não diz que distância a cota promete."""
    result = _solve_com_muro_norte(gap_kind="length")
    assert result.status == "solved_unapproved", result.blockers
    assert GAP_READING in result.unapplied_reading_ids


def test_nota_ancorada_viaja_para_o_desenho() -> None:
    """`h=3,80` não existe em planta: vira texto exact preso ao elemento, sem colisão."""
    result = _solve_com_muro_norte(note_associations={NOTA_READING: MURO_NORTE_PROPOSAL})
    assert result.status == "solved_unapproved", result.blockers
    assert result.scene is not None
    assert result.note_count == 1

    notas = [
        entity
        for entity in result.scene.entities
        if entity.provenance is not None
        and entity.provenance.summary_code == "CONFIRMED_READING_AS_NOTE"
    ]
    assert len(notas) == 1
    nota = notas[0]
    assert isinstance(nota.geometry, TextGeometry)
    assert nota.geometry.text == "muro vizinho h=3,80"
    assert nota.precision is Precision.EXACT
    assert nota.provenance is not None
    assert NOTA_READING in nota.provenance.source_ids


def test_notas_vizinhas_nao_se_sobrepoem_nem_fogem_do_elemento() -> None:
    """Duas notas na mesma aresta deslizam lateralmente em vez de fugir para longe."""
    segunda_nota = "rd_" + "a" * 16
    packet = _packet()
    packet = packet.model_copy(
        update={
            "readings": [
                *packet.readings,
                _reading(NOTA_READING, value="3.80", kind="height", centre=(230, 50)),
                _reading(segunda_nota, value="5.10", kind="height", centre=(240, 55)),
            ]
        }
    )
    acceptance = _acceptance()
    acceptance = acceptance.model_copy(
        update={"proposal_ids": [*acceptance.proposal_ids, MURO_NORTE_PROPOSAL]}
    )
    result = solve_trace(
        packet,
        [*_proposals(), _muro_norte()],
        acceptance,
        confirmed_associations=_associations(),
        note_associations={
            NOTA_READING: MURO_NORTE_PROPOSAL,
            segunda_nota: MURO_NORTE_PROPOSAL,
        },
        image_width=600,
        image_height=700,
    )
    assert result.status == "solved_unapproved", result.blockers
    assert result.scene is not None
    assert result.note_count == 2

    muro = _entity_of(result.scene, MURO_NORTE_PROPOSAL)
    assert isinstance(muro.geometry, LineGeometry)
    muro_y = muro.geometry.start.y
    notas = [
        entity
        for entity in result.scene.entities
        if entity.provenance is not None
        and entity.provenance.summary_code == "CONFIRMED_READING_AS_NOTE"
    ]
    assert len(notas) == 2
    boxes = []
    for nota in notas:
        geometry = nota.geometry
        assert isinstance(geometry, TextGeometry)
        # As duas notas ficam na vizinhança do muro, não desgarradas na folha.
        assert abs(geometry.insertion.y - muro_y) < geometry.height * 8
        boxes.append(
            (
                geometry.insertion.x,
                geometry.insertion.y,
                geometry.insertion.x + len(geometry.text) * geometry.height * 0.55,
                geometry.insertion.y + geometry.height,
            )
        )
    first, second = boxes
    apart = (
        first[2] <= second[0]
        or second[2] <= first[0]
        or first[3] <= second[1]
        or second[3] <= first[1]
    )
    assert apart, f"notas sobrepostas: {first} x {second}"


def test_keep_apart_separa_elementos_desenhados_coincidentes() -> None:
    """O caso da mureta: duas linhas uma sobre a outra na folha, mas 3,30 m na obra.

    Sem a declaração, os vértices fundem e o vão não tem o que medir (faixas iguais);
    com `keep_apart`, o vão aplica a cota e os elementos se separam no CAD.
    """
    anexo_id = "vp_" + "cd" * 8
    vao_reading = "rd_" + "b" * 16
    anexo = VisionProposal(
        id=anexo_id,
        kind="contour",
        geometry=_rect(CAMPO_RIGHT_PX, CAMPO_TOP_PX, CAMPO_RIGHT_PX + 60, CAMPO_BOTTOM_PX),
        algorithm="fixture",
        quality_score=0.9,
        label="Anexo colado no campo",
        layer_hint="MURO",
    )
    packet = _packet()
    packet = packet.model_copy(
        update={
            "readings": [
                *packet.readings,
                _reading(vao_reading, value="2.00", kind="width", centre=(365, 250)),
            ]
        }
    )
    associations: dict[str, str | list[str]] = {
        **_associations(),
        vao_reading: [CAMPO_PROPOSAL, anexo_id],
    }
    base_acceptance = _acceptance()

    # Sem a declaração: vértices fundem, o vão cai em não-aplicado declarado.
    fused = solve_trace(
        packet,
        [*_proposals(), anexo],
        base_acceptance.model_copy(
            update={"proposal_ids": [*base_acceptance.proposal_ids, anexo_id]}
        ),
        confirmed_associations=associations,
        image_width=600,
        image_height=700,
    )
    assert fused.status == "solved_unapproved", fused.blockers
    assert vao_reading in fused.unapplied_reading_ids

    # Com a declaração humana: os elementos separam e a cota manda no vão.
    separated = solve_trace(
        packet,
        [*_proposals(), anexo],
        base_acceptance.model_copy(
            update={
                "proposal_ids": [*base_acceptance.proposal_ids, anexo_id],
                "keep_apart_pairs": [(CAMPO_PROPOSAL, anexo_id)],
            }
        ),
        confirmed_associations=associations,
        image_width=600,
        image_height=700,
    )
    assert separated.status == "solved_unapproved", separated.blockers
    assert vao_reading not in separated.unapplied_reading_ids
    assert separated.scene is not None
    campo = _bbox(_entity_of(separated.scene, CAMPO_PROPOSAL).geometry)
    anexo_box = _bbox(_entity_of(separated.scene, anexo_id).geometry)
    assert anexo_box[0] - campo[2] == pytest.approx(2.00, abs=0.01)
    assert all(residual.passed for residual in separated.residuals)


# --- O anel de cotas do Guaxindiba v2 (2026-08-13) -------------------------------------
#
# Reprodução sintética do defeito medido no job real: `keep_apart` mantinha os vértices
# separados, mas a regularização reunia numa faixa só a cadeia dos patamares e a mureta —
# por uma ponte de um terceiro elemento (a faixa vegetativa) que encosta nos dois. Como a
# FAIXA é a variável do solver, a cadeia e o vão declarado passavam a pinar a MESMA
# incógnita e o conflito se espalhava em resíduos por todo o desenho.

RING_WIDTH, RING_HEIGHT = 1200, 800
RING_CAMPO = "vp_" + "1a" * 8
RING_PAT_ESQ = "vp_" + "2b" * 8
RING_PAT_CENTRO = "vp_" + "3c" * 8
RING_PAT_DIR = "vp_" + "4d" * 8
RING_MURETA = "vp_" + "5e" * 8
RING_VEGETATIVA = "vp_" + "6f" * 8

RING_LARGURA = "rd_" + "1a" * 8
RING_ALTURA = "rd_" + "2b" * 8
RING_ESQ = "rd_" + "3c" * 8
RING_CENTRO = "rd_" + "4d" * 8
RING_DIR = "rd_" + "5e" * 8
RING_VAO = "rd_" + "6f" * 8


def _ring_proposals() -> list[VisionProposal]:
    """Campo, cadeia de três patamares, mureta coincidente e a vegetativa que faz ponte.

    A cadeia é desenhada 60 px além da borda direita do campo (folha fora de escala, como
    a real). A mureta encosta na ponta da cadeia; nenhum vértice das duas cai na tolerância
    de fusão do outro — quem os liga é a vegetativa, a 3,2 px de uma e 4,2 px da outra.
    """
    return [
        VisionProposal(
            id=RING_CAMPO,
            kind="contour",
            geometry=_rect(100.0, 100.0, 500.0, 400.0),
            algorithm="fixture",
            quality_score=0.9,
            label="Contorno do campo",
            layer_hint="CAMPO",
        ),
        VisionProposal(
            id=RING_PAT_ESQ,
            kind="contour",
            geometry=_rect(100.0, 400.0, 240.0, 560.0),
            algorithm="fixture",
            quality_score=0.9,
            label="Patamar esquerdo",
            layer_hint="PATAMAR",
        ),
        VisionProposal(
            id=RING_PAT_CENTRO,
            kind="contour",
            geometry=_rect(240.0, 400.0, 300.0, 560.0),
            algorithm="fixture",
            quality_score=0.9,
            label="Patamar central",
            layer_hint="PATAMAR",
        ),
        VisionProposal(
            id=RING_PAT_DIR,
            kind="contour",
            geometry=_rect(300.0, 400.0, 560.0, 560.0),
            algorithm="fixture",
            quality_score=0.9,
            label="Patamar direito",
            layer_hint="PATAMAR",
        ),
        VisionProposal(
            id=RING_MURETA,
            kind="line",
            geometry=PixelLine(
                start=PixelPoint(x=566.0, y=120.0),
                end=PixelPoint(x=562.0, y=492.0),
            ),
            algorithm="fixture",
            quality_score=0.9,
            label="Mureta lateral direita",
            layer_hint="MURO",
        ),
        VisionProposal(
            id=RING_VEGETATIVA,
            kind="line",
            geometry=PixelLine(
                start=PixelPoint(x=563.0, y=489.0),
                end=PixelPoint(x=557.0, y=563.0),
            ),
            algorithm="fixture",
            quality_score=0.9,
            label="Faixa de área vegetativa",
            layer_hint="PATAMAR",
        ),
    ]


def _ring_packet() -> ReviewPacket:
    return ReviewPacket(
        dataset_id=DATASET_ID,
        page_number=1,
        image_sha256=DIGEST,
        readings=[
            _reading(RING_LARGURA, value="25.40", kind="width", centre=(300, 95)),
            _reading(RING_ALTURA, value="21.75", kind="height", centre=(95, 250)),
            _reading(RING_ESQ, value="9.55", kind="width", centre=(170, 480)),
            _reading(RING_CENTRO, value="3.86", kind="width", centre=(270, 480)),
            _reading(RING_DIR, value="12.49", kind="width", centre=(430, 480)),
            _reading(RING_VAO, value="3.30", kind="width", centre=(533, 300)),
        ],
        safety_notes=["Fixture local.", "Revisão humana obrigatória."],
    )


def _ring_acceptance(*, keep_apart: bool) -> TraceAcceptance:
    return TraceAcceptance(
        acceptance_id="ta_" + "7" * 16,
        reviewer_id="eng-teste",
        reviewer_role="engineer",
        decided_at=datetime(2026, 8, 13, 9, 0, tzinfo=UTC),
        proposal_ids=[
            RING_CAMPO,
            RING_PAT_ESQ,
            RING_PAT_CENTRO,
            RING_PAT_DIR,
            RING_MURETA,
            RING_VEGETATIVA,
        ],
        keep_apart_pairs=[(RING_MURETA, RING_PAT_DIR)] if keep_apart else [],
    )


def _ring_solve(*, keep_apart: bool) -> TraceSolveResult:
    return solve_trace(
        _ring_packet(),
        _ring_proposals(),
        _ring_acceptance(keep_apart=keep_apart),
        confirmed_associations={
            RING_LARGURA: RING_CAMPO,
            RING_ALTURA: RING_CAMPO,
            RING_ESQ: RING_PAT_ESQ,
            RING_CENTRO: RING_PAT_CENTRO,
            RING_DIR: RING_PAT_DIR,
            RING_VAO: [RING_CAMPO, RING_MURETA],
        },
        image_width=RING_WIDTH,
        image_height=RING_HEIGHT,
    )


def test_keep_apart_desamarra_a_cadeia_de_cotas_do_vao_declarado() -> None:
    """A cadeia 9,55+3,86+12,49 e o vão de 3,30 deixam de disputar a mesma faixa.

    Antes de `keep_apart` valer na regularização, este mesmo aceite resolvia em conflito:
    a ponta da cadeia e a mureta caíam na faixa da ponte da vegetativa, então o vão de
    3,30 contradizia a cadeia e o erro se espalhava pelos resíduos do desenho todo.
    """
    result = _ring_solve(keep_apart=True)

    assert result.status == "solved_unapproved", result.blockers
    assert RING_VAO not in result.unapplied_reading_ids
    assert all(residual.passed for residual in result.residuals), [
        (residual.code, str(residual.absolute_error_m)) for residual in result.residuals
    ]
    assert result.scene is not None
    campo = _bbox(_entity_of(result.scene, RING_CAMPO).geometry)
    patamar_dir = _bbox(_entity_of(result.scene, RING_PAT_DIR).geometry)
    mureta = _entity_of(result.scene, RING_MURETA).geometry
    assert isinstance(mureta, LineGeometry)
    # O campo mede o que a cota diz e a cadeia inteira soma o seu próprio total: nenhuma
    # das duas puxa a outra por uma faixa partilhada.
    assert campo[2] - campo[0] == pytest.approx(25.40, abs=0.01)
    assert patamar_dir[2] - campo[0] == pytest.approx(25.90, abs=0.01)
    # E o vão declarado pousa onde a folha manda, medido da borda do campo.
    assert mureta.start.x - campo[2] == pytest.approx(3.30, abs=0.01)


def test_sem_keep_apart_o_anel_de_cotas_acusa_o_conflito() -> None:
    """Sem a declaração humana, a mesma folha fecha um anel impossível — e o sistema acusa.

    É a contraprova do teste anterior: o que separa os dois é a declaração, não um limiar.
    """
    result = _ring_solve(keep_apart=False)

    assert result.status == "conflict", result.blockers
    assert "NUMERIC_RESIDUAL_EXCEEDS_TOLERANCE" in result.blockers
    assert any(not residual.passed for residual in result.residuals)


# --- Encosto em aresta e keep_apart por eixo (Guaxindiba v2, 2026-08-13) ---------------
#
# Dois defeitos medidos no DXF real exportado: (1) elemento que encosta no MEIO da aresta
# de outro nunca amarrava — a linha de meio de campo vazou 5,12 m pelo fundo do campo e as
# áreas saíram para fora da lateral; (2) o par mantido separado pelo dente horizontal do
# muro também soltava o encontro VERTICAL legítimo, e o sistema do muro deslizava.

TOUCH_WIDTH, TOUCH_HEIGHT = 1200, 800
TOUCH_CAMPO = "vp_" + "7a" * 8
TOUCH_MEIO = "vp_" + "8b" * 8
TOUCH_MURETA = "vp_" + "9c" * 8

TOUCH_LARGURA = "rd_" + "7a" * 8
TOUCH_ALTURA = "rd_" + "8b" * 8
TOUCH_VAO = "rd_" + "9c" * 8


def _touch_proposals() -> list[VisionProposal]:
    """Campo, linha de meio encostada no topo e no fundo, e mureta coincidente na lateral.

    A linha de meio para 4 px antes de cada aresta horizontal do campo, a 200 px de
    qualquer canto: nenhum vértice funde (a fusão precisa de 14,4 px aqui), e antes do
    encosto ela não tinha vizinho nenhum. A mureta corre a 6 px da lateral direita (o
    encosto em X que o revisor recusa, porque a folha cota 3,30 m entre as duas) e a ponta
    dela pousa 8 px acima da base do campo — o encontro em Y, que é real.
    """
    return [
        VisionProposal(
            id=TOUCH_CAMPO,
            kind="contour",
            geometry=_rect(100.0, 100.0, 500.0, 400.0),
            algorithm="fixture",
            quality_score=0.9,
            label="Contorno do campo",
            layer_hint="CAMPO",
        ),
        VisionProposal(
            id=TOUCH_MEIO,
            kind="line",
            geometry=PixelLine(
                start=PixelPoint(x=300.0, y=104.0),
                end=PixelPoint(x=300.0, y=396.0),
            ),
            algorithm="fixture",
            quality_score=0.9,
            label="Linha de meio de campo",
            layer_hint="CAMPO",
        ),
        VisionProposal(
            id=TOUCH_MURETA,
            kind="line",
            geometry=PixelLine(
                start=PixelPoint(x=506.0, y=120.0),
                end=PixelPoint(x=503.0, y=392.0),
            ),
            algorithm="fixture",
            quality_score=0.9,
            label="Mureta lateral direita",
            layer_hint="MURO",
        ),
    ]


def _touch_solve(keep_apart: list[tuple[str, str] | KeepApartPair]) -> TraceSolveResult:
    packet = ReviewPacket(
        dataset_id=DATASET_ID,
        page_number=1,
        image_sha256=DIGEST,
        readings=[
            _reading(TOUCH_LARGURA, value="25.40", kind="width", centre=(300, 95)),
            _reading(TOUCH_ALTURA, value="21.75", kind="height", centre=(95, 250)),
            _reading(TOUCH_VAO, value="3.30", kind="width", centre=(503, 250)),
        ],
        safety_notes=["Fixture local.", "Revisão humana obrigatória."],
    )
    acceptance = TraceAcceptance(
        acceptance_id="ta_" + "a" * 16,
        reviewer_id="eng-teste",
        reviewer_role="engineer",
        decided_at=datetime(2026, 8, 13, 10, 0, tzinfo=UTC),
        proposal_ids=[TOUCH_CAMPO, TOUCH_MEIO, TOUCH_MURETA],
        keep_apart_pairs=keep_apart,
    )
    return solve_trace(
        packet,
        _touch_proposals(),
        acceptance,
        confirmed_associations={
            TOUCH_LARGURA: TOUCH_CAMPO,
            TOUCH_ALTURA: TOUCH_CAMPO,
            TOUCH_VAO: [TOUCH_CAMPO, TOUCH_MURETA],
        },
        image_width=TOUCH_WIDTH,
        image_height=TOUCH_HEIGHT,
    )


def test_encosto_prende_a_linha_de_meio_ao_campo() -> None:
    """A linha de meio termina exatamente nas arestas do campo, não 5 m fora dele."""
    result = _touch_solve([KeepApartPair(first=TOUCH_CAMPO, second=TOUCH_MURETA, axis="x")])

    assert result.status == "solved_unapproved", result.blockers
    assert result.scene is not None
    campo = _bbox(_entity_of(result.scene, TOUCH_CAMPO).geometry)
    meio = _entity_of(result.scene, TOUCH_MEIO).geometry
    assert isinstance(meio, LineGeometry)
    assert campo[3] - campo[1] == pytest.approx(21.75, abs=0.01)
    # Mesma faixa: as pontas coincidem com as arestas do campo, não "quase".
    assert min(meio.start.y, meio.end.y) == pytest.approx(campo[1], abs=1e-6)
    assert max(meio.start.y, meio.end.y) == pytest.approx(campo[3], abs=1e-6)


def test_keep_apart_por_eixo_mantem_o_encontro_vertical_amarrado() -> None:
    """Separar em X (o dente) e amarrar em Y (a base) na mesma declaração.

    O par legado separa nos dois eixos e a base da mureta volta a flutuar pelo prior — é
    a contraprova de que o eixo declarado é o que segura o encontro, e de que o formato
    antigo continua com o significado antigo.
    """
    por_eixo = _touch_solve([KeepApartPair(first=TOUCH_CAMPO, second=TOUCH_MURETA, axis="x")])
    legado = _touch_solve([(TOUCH_CAMPO, TOUCH_MURETA)])

    for result in (por_eixo, legado):
        assert result.status == "solved_unapproved", result.blockers
        assert TOUCH_VAO not in result.unapplied_reading_ids
        assert result.scene is not None
        campo = _bbox(_entity_of(result.scene, TOUCH_CAMPO).geometry)
        mureta = _entity_of(result.scene, TOUCH_MURETA).geometry
        assert isinstance(mureta, LineGeometry)
        # O dente continua sendo o que a folha cota, nos dois formatos.
        assert min(mureta.start.x, mureta.end.x) - campo[2] == pytest.approx(3.30, abs=0.01)

    def _base_gap(result: TraceSolveResult) -> float:
        assert result.scene is not None
        campo = _bbox(_entity_of(result.scene, TOUCH_CAMPO).geometry)
        mureta = _entity_of(result.scene, TOUCH_MURETA).geometry
        assert isinstance(mureta, LineGeometry)
        return abs(min(mureta.start.y, mureta.end.y) - campo[1])

    assert _base_gap(por_eixo) == pytest.approx(0.0, abs=1e-6)
    # Solta, a base não pousa em lugar nenhum: sem faixa que a segure ela flutua pelo
    # prior, metros longe do campo — no job real o muro desceu 14,5 m por este caminho.
    assert _base_gap(legado) > 5.0


def test_keep_apart_aceita_os_dois_formatos_e_valida_igual() -> None:
    """O formato objeto passa pelas mesmas regras: distintos e aceitos."""
    base = {
        "acceptance_id": "ta_" + "b" * 16,
        "reviewer_id": "eng-teste",
        "reviewer_role": "engineer",
        "decided_at": datetime(2026, 8, 13, 10, 0, tzinfo=UTC),
        "proposal_ids": [TOUCH_CAMPO, TOUCH_MURETA],
    }
    misto = TraceAcceptance.model_validate(
        {
            **base,
            "keep_apart_pairs": [
                [TOUCH_CAMPO, TOUCH_MURETA],
                {"first": TOUCH_CAMPO, "second": TOUCH_MURETA, "axis": "y"},
            ],
        }
    )

    assert misto.keep_apart_separations() == [
        BandSeparation(TOUCH_CAMPO, TOUCH_MURETA, None),
        BandSeparation(TOUCH_CAMPO, TOUCH_MURETA, "y"),
    ]
    with pytest.raises(ValidationError, match="dois elementos distintos"):
        TraceAcceptance.model_validate(
            {**base, "keep_apart_pairs": [{"first": TOUCH_CAMPO, "second": TOUCH_CAMPO}]}
        )
    with pytest.raises(ValidationError, match="propostas aceitas"):
        TraceAcceptance.model_validate(
            {
                **base,
                "keep_apart_pairs": [{"first": TOUCH_CAMPO, "second": "vp_" + "0" * 16}],
            }
        )
    with pytest.raises(ValidationError):
        TraceAcceptance.model_validate(
            {
                **base,
                "keep_apart_pairs": [{"first": TOUCH_CAMPO, "second": TOUCH_MURETA, "axis": "z"}],
            }
        )


def test_cota_derivada_mede_trecho_desenhado() -> None:
    """O 1,50 do dente: pedido do revisor, valor da geometria resolvida, precisão derived."""
    result = solve_trace(
        _packet(),
        _proposals(),
        _acceptance(),
        confirmed_associations=_associations(),
        derived_dimension_requests=[
            DerivedDimensionRequest(
                proposal_id=PATAMAR_CENTRO_PROPOSAL,
                near_x_px=(DIVIDER_1_PX + DIVIDER_2_PX) / 2,
                near_y_px=CAMPO_BOTTOM_PX,
            )
        ],
        image_width=600,
        image_height=700,
    )
    assert result.status == "solved_unapproved", result.blockers
    assert result.scene is not None
    derived = [
        entity
        for entity in result.scene.entities
        if entity.kind is EntityKind.DIMENSION
        and entity.provenance is not None
        and entity.provenance.summary_code == "DERIVED_SPAN_DIMENSIONED"
    ]
    assert len(derived) == 1
    assert derived[0].precision is Precision.DERIVED
    geometry = derived[0].geometry
    assert isinstance(geometry, DimensionGeometry)
    # O trecho pedido é a aresta superior do patamar central, cotada em 3,86.
    assert geometry.text_override == "3.86 m"


def test_nota_geral_vai_para_o_carimbo_acima_do_titulo() -> None:
    """Nota que descreve o conjunto (tela aérea) não flutua no desenho: vai ao carimbo."""
    nota_geral = "rd_" + "e" * 16
    packet = _packet()
    packet = packet.model_copy(
        update={
            "readings": [
                *packet.readings,
                _reading(nota_geral, value="25.90", kind="length", centre=(230, 650)),
            ]
        }
    )
    result = solve_trace(
        packet,
        _proposals(),
        _acceptance(),
        confirmed_associations=_associations(),
        note_associations={nota_geral: "carimbo"},
        image_width=600,
        image_height=700,
    )
    assert result.status == "solved_unapproved", result.blockers
    assert result.scene is not None
    gerais = [
        entity
        for entity in result.scene.entities
        if entity.provenance is not None
        and entity.provenance.summary_code == "CONFIRMED_READING_AS_GENERAL_NOTE"
    ]
    assert len(gerais) == 1
    nota = gerais[0]
    assert nota.precision is Precision.EXACT
    assert isinstance(nota.geometry, TextGeometry)
    titulo = next(
        entity
        for entity in result.scene.entities
        if isinstance(entity.geometry, TextGeometry)
        and "GUAXINDIBA" in entity.geometry.text.upper()
    )
    assert isinstance(titulo.geometry, TextGeometry)
    # Acima do título, com respiro: a base da nota fica acima do topo do título.
    assert nota.geometry.insertion.y > titulo.geometry.insertion.y + titulo.geometry.height


def test_nota_curta_usa_fonte_menor() -> None:
    """`h = 0,20` é informação secundária: fonte menor para não brigar com os nomes."""
    curta = "rd_" + "c" * 16
    packet = _packet()
    packet = packet.model_copy(
        update={
            "readings": [
                *packet.readings,
                _reading(curta, value="0.20", kind="height", centre=(148, 420)),
            ]
        }
    )
    readings = {reading.id: reading for reading in packet.readings}
    ajustada = readings[curta].model_copy(update={"raw_text": "h = 0,20"})
    packet = packet.model_copy(
        update={
            "readings": [ajustada if r.id == curta else r for r in packet.readings],
        }
    )
    result = solve_trace(
        packet,
        _proposals(),
        _acceptance(),
        confirmed_associations=_associations(),
        note_associations={curta: PATAMAR_ESQ_PROPOSAL},
        image_width=600,
        image_height=700,
    )
    assert result.status == "solved_unapproved", result.blockers
    assert result.scene is not None
    nota = next(
        entity
        for entity in result.scene.entities
        if entity.provenance is not None
        and entity.provenance.summary_code == "CONFIRMED_READING_AS_NOTE"
    )
    assert isinstance(nota.geometry, TextGeometry)
    cotas = [
        entity for entity in result.scene.entities if isinstance(entity.geometry, DimensionGeometry)
    ]
    assert cotas, "fixture precisa ter cotas para comparar altura"
    # Nota curta é menor que o texto de cota do desenho.
    assert nota.geometry.height < 0.7 * _dimension_reference_height(result.scene)


def _dimension_reference_height(scene: SceneRevision) -> float:
    from croquito_worker.element_labels import dimension_text_height

    xs: list[float] = []
    ys: list[float] = []
    for entity in scene.entities:
        if isinstance(entity.geometry, PolylineGeometry):
            xs += [point.x for point in entity.geometry.points]
            ys += [point.y for point in entity.geometry.points]
    diagonal = ((max(xs) - min(xs)) ** 2 + (max(ys) - min(ys)) ** 2) ** 0.5
    return dimension_text_height(diagonal)


def test_nota_de_legenda_vai_para_a_linha_do_elemento() -> None:
    """Especificação que polui o desenho (Portão 1,0 x 2,05) viaja na legenda do balão."""
    spec = "rd_" + "d" * 16
    packet = _packet()
    packet = packet.model_copy(
        update={
            "readings": [
                *packet.readings,
                _reading(spec, value="2.05", kind="height", centre=(315, 95)),
            ]
        }
    )
    readings = {reading.id: reading for reading in packet.readings}
    ajustada = readings[spec].model_copy(update={"raw_text": "Portão 1,0 x 2,05"})
    packet = packet.model_copy(
        update={"readings": [ajustada if r.id == spec else r for r in packet.readings]}
    )
    result = solve_trace(
        packet,
        _proposals(),
        _acceptance(),
        confirmed_associations=_associations(),
        note_associations={spec: f"legenda:{PORTAO_PROPOSAL}"},
        image_width=600,
        image_height=700,
    )
    assert result.status == "solved_unapproved", result.blockers
    assert result.scene is not None
    # Nada flutua no desenho para esta leitura…
    assert not any(
        entity.provenance is not None
        and entity.provenance.summary_code == "CONFIRMED_READING_AS_NOTE"
        for entity in result.scene.entities
    )
    # …e a linha de legenda do portão carrega a especificação.
    legenda = [
        entity.geometry.text
        for entity in result.scene.entities
        if isinstance(entity.geometry, TextGeometry)
        and entity.provenance is not None
        and entity.provenance.summary_code == "ELEMENT_LEGEND_ENTRY"
    ]
    assert any("Portão norte — Portão 1,0 x 2,05" in text for text in legenda)


def test_nota_ancorada_pousa_onde_o_croqui_escreveu() -> None:
    """A âncora é a projeção da evidência no elemento, não o ponto médio do segmento."""
    result = _solve_com_muro_norte(note_associations={NOTA_READING: MURO_NORTE_PROPOSAL})
    assert result.scene is not None
    nota = next(
        entity
        for entity in result.scene.entities
        if entity.provenance is not None
        and entity.provenance.summary_code == "CONFIRMED_READING_AS_NOTE"
    )
    assert isinstance(nota.geometry, TextGeometry)
    muro = _entity_of(result.scene, MURO_NORTE_PROPOSAL)
    assert isinstance(muro.geometry, LineGeometry)
    # Evidência em x=230 px ≈ meio-esquerda do muro; o centro da nota deve ficar perto
    # da projeção (não no meio geométrico por acaso: muro vai de 100 a 359 px).
    centro_nota_x = (
        nota.geometry.insertion.x + len(nota.geometry.text) * nota.geometry.height * 0.55 / 2
    )
    esperado_x = (230 - 100) * (25.90 / 259.0) + min(muro.geometry.start.x, muro.geometry.end.x)
    assert centro_nota_x == pytest.approx(esperado_x, abs=3.0)


def test_texto_de_cota_declarado_pelo_revisor() -> None:
    """Vão de portão mostra a especificação (1,0 x 2,05); a medida segue no resíduo."""
    result = solve_trace(
        _packet(),
        _proposals(),
        _acceptance(),
        confirmed_associations=_associations(),
        dimension_texts={LARGURA_READING: "campo 25,90"},
        image_width=600,
        image_height=700,
    )
    assert result.status == "solved_unapproved", result.blockers
    assert result.scene is not None
    textos = [
        entity.geometry.text_override
        for entity in result.scene.entities
        if isinstance(entity.geometry, DimensionGeometry)
    ]
    assert "campo 25,90" in textos
    # Texto declarado para leitura sem vão associado é erro do insumo, não silêncio.
    invalido = solve_trace(
        _packet(),
        _proposals(),
        _acceptance(),
        confirmed_associations=_associations(),
        dimension_texts={"rd_" + "f" * 16: "orfão"},
        image_width=600,
        image_height=700,
    )
    assert invalido.status == "review_required"
    assert any("DIMENSION_TEXT_WITHOUT_SPAN" in blocker for blocker in invalido.blockers)


def test_nota_curta_fica_por_dentro_com_risco_vermelho() -> None:
    """As marcações h= ficam do lado de dentro, com traço de chamada na layer COTAS."""
    curta = "rd_" + "c" * 16
    packet = _packet()
    packet = packet.model_copy(
        update={
            "readings": [
                *packet.readings,
                _reading(curta, value="0.20", kind="height", centre=(148, 420)),
            ]
        }
    )
    readings = {reading.id: reading for reading in packet.readings}
    ajustada = readings[curta].model_copy(update={"raw_text": "h = 0,20"})
    packet = packet.model_copy(
        update={"readings": [ajustada if r.id == curta else r for r in packet.readings]}
    )
    result = solve_trace(
        packet,
        _proposals(),
        _acceptance(),
        confirmed_associations=_associations(),
        note_associations={curta: PATAMAR_ESQ_PROPOSAL},
        image_width=600,
        image_height=700,
    )
    assert result.status == "solved_unapproved", result.blockers
    assert result.scene is not None
    ticks = [
        entity
        for entity in result.scene.entities
        if entity.provenance is not None and entity.provenance.summary_code == "NOTE_LEADER_TICK"
    ]
    assert len(ticks) == 1
    assert ticks[0].layer is LayerName.COTAS
    assert ticks[0].kind is EntityKind.LINE
    assert curta in ticks[0].provenance.source_ids  # type: ignore[union-attr]


def test_nota_sem_confirmacao_bloqueia() -> None:
    """Anotação segue a mesma regra dos vãos: sem decisão humana completa, não entra."""
    packet = _packet()
    packet = packet.model_copy(
        update={
            "readings": [
                *packet.readings,
                _reading(
                    NOTA_READING, value="3.80", kind="height", centre=(230, 50), confirmed=False
                ),
            ]
        }
    )
    result = solve_trace(
        packet,
        _proposals(),
        _acceptance(),
        confirmed_associations=_associations(),
        note_associations={NOTA_READING: CAMPO_PROPOSAL},
        image_width=600,
        image_height=700,
    )
    assert result.status == "review_required"
    assert any("TRACE_HUMAN_CONFIRMATION_REQUIRED" in blocker for blocker in result.blockers)


def test_leitura_diagonal_fica_declarada_como_nao_aplicada() -> None:
    """Cota que não vira vão ortogonal não some: entra como aviso e nota no carimbo."""
    proposals = [
        *_proposals(),
        VisionProposal(
            id="vp_" + "0" * 16,
            kind="line",
            geometry=PixelLine(
                start=PixelPoint(x=400.0, y=560.0),
                end=PixelPoint(x=460.0, y=640.0),
            ),
            algorithm="fixture",
            quality_score=0.9,
            label="Rampa diagonal",
        ),
    ]
    packet = _packet()
    packet = packet.model_copy(
        update={
            "readings": [
                *packet.readings,
                _reading("rd_" + "7" * 16, value="10.00", kind="length", centre=(430, 600)),
            ]
        }
    )
    acceptance = _acceptance()
    acceptance = acceptance.model_copy(
        update={"proposal_ids": [*acceptance.proposal_ids, "vp_" + "0" * 16]}
    )
    result = solve_trace(
        packet,
        proposals,
        acceptance,
        confirmed_associations={**_associations(), "rd_" + "7" * 16: "vp_" + "0" * 16},
        image_width=600,
        image_height=700,
    )
    assert result.status == "solved_unapproved", result.blockers
    assert result.unapplied_reading_ids == ["rd_" + "7" * 16]
    assert result.scene is not None
    assert any(issue.code == "CONFIRMED_READING_NOT_APPLIED" for issue in result.scene.issues)
    notes = _title_texts(result.scene)
    assert any("NAO APLICADA" in text for text in notes)


def _detail_group(**overrides: object) -> TraceDetailGroup:
    base: dict[str, object] = {
        "detail_id": "A",
        "title": "Alambrado",
        "proposal_ids": [PORTAO_PROPOSAL],
        "mode": "solve",
    }
    return TraceDetailGroup.model_validate({**base, **overrides})


def test_grupo_de_detalhe_so_pode_conter_proposta_aceita() -> None:
    payload = _acceptance().model_dump(mode="json")
    payload["detail_groups"] = [
        _detail_group(proposal_ids=["vp_" + "0" * 16]).model_dump(mode="json")
    ]
    with pytest.raises(ValidationError, match="proposta aceita"):
        TraceAcceptance.model_validate(payload)


def test_proposta_nao_pode_estar_em_dois_grupos_de_detalhe() -> None:
    payload = _acceptance().model_dump(mode="json")
    payload["detail_groups"] = [
        _detail_group().model_dump(mode="json"),
        _detail_group(detail_id="B", title="Painel B").model_dump(mode="json"),
    ]
    with pytest.raises(ValidationError, match="mais de um grupo"):
        TraceAcceptance.model_validate(payload)


def test_planta_principal_nao_pode_ficar_vazia() -> None:
    payload = _acceptance().model_dump(mode="json")
    payload["detail_groups"] = [
        _detail_group(
            detail_id="T", title="Tudo em detalhe", proposal_ids=list(payload["proposal_ids"])
        ).model_dump(mode="json")
    ]
    with pytest.raises(ValidationError, match="planta principal"):
        TraceAcceptance.model_validate(payload)


DETALHE_PROPOSAL = "vp_" + "0" * 15 + "1"
DETALHE_READING = "rd_" + "8" * 16
GAP_DETALHE_READING = "rd_" + "9" * 16


def _painel_detalhe() -> VisionProposal:
    # Painel desenhado pequeno num canto da folha: 120x40 px, longe da planta.
    return VisionProposal(
        id=DETALHE_PROPOSAL,
        kind="contour",
        geometry=_rect(400.0, 40.0, 520.0, 80.0),
        algorithm="fixture",
        quality_score=0.9,
        label="Painel do alambrado",
        layer_hint="ALAMBRADO",
    )


def _solve_com_detalhe(
    *,
    mode: Literal["solve", "sketch"] = "solve",
    associate_panel: bool = True,
    extra_associations: dict[str, str | list[str]] | None = None,
    derived: tuple[DerivedDimensionRequest, ...] = (),
) -> TraceSolveResult:
    packet = _packet().model_copy(
        update={
            "readings": [
                *_packet().readings,
                _reading(DETALHE_READING, value="4.40", kind="height", centre=(530, 60)),
                _reading(GAP_DETALHE_READING, value="2.00", kind="width", centre=(370, 60)),
            ]
        }
    )
    acceptance = _acceptance().model_copy(
        update={
            "proposal_ids": [*_acceptance().proposal_ids, DETALHE_PROPOSAL],
            "detail_groups": [
                TraceDetailGroup(
                    detail_id="A",
                    title="Alambrado",
                    proposal_ids=[DETALHE_PROPOSAL],
                    mode=mode,
                )
            ],
        }
    )
    associations: dict[str, str | list[str]] = dict(_associations())
    if associate_panel:
        associations[DETALHE_READING] = DETALHE_PROPOSAL
    associations.update(extra_associations or {})
    return solve_trace(
        packet,
        [*_proposals(), _painel_detalhe()],
        acceptance,
        confirmed_associations=associations,
        derived_dimension_requests=derived,
        image_width=600,
        image_height=700,
        title="CAMPO GUAXINDIBA SINTETICO",
    )


def _summary_entities(scene: SceneRevision, summary_code: str) -> list[Entity]:
    return [
        entity
        for entity in scene.entities
        if entity.provenance is not None and entity.provenance.summary_code == summary_code
    ]


def test_grupo_de_detalhe_nao_altera_a_planta() -> None:
    base = _solve()
    com_detalhe = _solve_com_detalhe()

    assert com_detalhe.status == "solved_unapproved"
    assert base.scene is not None and com_detalhe.scene is not None
    campo_base = _entity_of(base.scene, CAMPO_PROPOSAL)
    campo_com = _entity_of(com_detalhe.scene, CAMPO_PROPOSAL)
    assert campo_base.geometry == campo_com.geometry
    assert base.scale_m_per_px == com_detalhe.scale_m_per_px
    # A escala do detalhe é própria: 4,40 m sobre 40 px, não a mediana da planta.
    assert com_detalhe.detail_group_scales["A"] == pytest.approx(4.40 / 40.0)


def test_detalhe_resolvido_tem_cota_propria_moldura_e_titulo() -> None:
    result = _solve_com_detalhe()

    assert result.scene is not None
    painel = _entity_of(result.scene, DETALHE_PROPOSAL)
    painel_box = _bbox(painel.geometry)
    campo_box = _bbox(_entity_of(result.scene, CAMPO_PROPOSAL).geometry)
    # Cota do grupo manda dentro do grupo; o painel fica na coluna à direita da planta.
    assert painel_box[3] - painel_box[1] == pytest.approx(4.40, abs=0.01)
    assert painel_box[0] > campo_box[2]
    assert "detail:A" in (painel.provenance.source_ids if painel.provenance else [])

    frames = _summary_entities(result.scene, "DETAIL_FRAME")
    assert len(frames) == 1
    assert frames[0].layer is LayerName.DETALHES
    frame_box = _bbox(frames[0].geometry)
    assert frame_box[0] <= painel_box[0] and frame_box[2] >= painel_box[2]

    titles = _summary_entities(result.scene, "DETAIL_TITLE")
    assert len(titles) == 1
    title_geometry = titles[0].geometry
    assert isinstance(title_geometry, TextGeometry)
    assert title_geometry.text == "DETALHE A — Alambrado"

    legend_entries = _summary_entities(result.scene, "ELEMENT_LEGEND_ENTRY")
    assert legend_entries
    for entry in legend_entries:
        entry_geometry = entry.geometry
        assert isinstance(entry_geometry, TextGeometry)
        assert entry_geometry.insertion.x >= frame_box[2]


def test_sketch_fica_aproximado_e_cota_vira_nota() -> None:
    result = _solve_com_detalhe(mode="sketch")

    assert result.status == "solved_unapproved"
    assert result.scene is not None
    painel = _entity_of(result.scene, DETALHE_PROPOSAL)
    assert painel.precision is Precision.APPROXIMATE
    assert painel.id in result.scene.accepted_approximation_ids
    assert painel.provenance is not None
    assert painel.provenance.summary_code == "DETAIL_SKETCH_AS_DRAWN"
    # A cota associada ao sketch não vira DIMENSION nem Measurement: vira nota presa.
    assert not any(
        DETALHE_READING in measurement.provenance.source_ids
        for measurement in result.scene.measurements
        if measurement.provenance is not None
    )
    assert not any(
        entity.kind is EntityKind.DIMENSION
        and entity.provenance is not None
        and DETALHE_READING in entity.provenance.source_ids
        for entity in result.scene.entities
    )
    assert any(
        entity.kind is EntityKind.TEXT
        and entity.provenance is not None
        and DETALHE_READING in entity.provenance.source_ids
        for entity in result.scene.entities
    )
    titles = _summary_entities(result.scene, "DETAIL_TITLE")
    title_geometry = titles[0].geometry
    assert isinstance(title_geometry, TextGeometry)
    assert title_geometry.text.endswith("(SEM ESCALA)")


def test_vao_entre_planta_e_detalhe_bloqueia() -> None:
    result = _solve_com_detalhe(
        extra_associations={GAP_DETALHE_READING: [CAMPO_PROPOSAL, DETALHE_PROPOSAL]}
    )
    assert result.status == "review_required"
    assert any(
        blocker.startswith("TRACE_ASSOCIATION_CROSSES_DETAIL_GROUP") for blocker in result.blockers
    )


def test_grupo_solve_sem_cota_aplicada_bloqueia() -> None:
    result = _solve_com_detalhe(associate_panel=False)
    assert result.status == "review_required"
    assert "DETAIL_GROUP_WITHOUT_APPLIED_READING:A" in result.blockers


def test_cota_derivada_em_sketch_bloqueia() -> None:
    result = _solve_com_detalhe(
        mode="sketch",
        derived=(
            DerivedDimensionRequest(proposal_id=DETALHE_PROPOSAL, near_x_px=460.0, near_y_px=60.0),
        ),
    )
    assert result.status == "review_required"
    assert f"DERIVED_DIMENSION_ON_SKETCH_DETAIL:{DETALHE_PROPOSAL}" in result.blockers


def test_export_com_detalhe_audita_e_exclui_quantidade_de_moldura(tmp_path: Path) -> None:
    """A prancha com grupo de detalhe passa na auditoria fail-closed do DXF.

    Moldura e título têm XDATA como qualquer entidade; grupo `solve` entra no CSV com a
    quantidade real; a moldura fica fora do CSV.
    """
    result = _solve_com_detalhe()
    assert result.scene is not None

    approval = SceneApproval(
        approval_id="ap_" + "6" * 16,
        source_scene_id=result.scene.id,
        reviewer_id="eng-teste",
        reviewer_role="engineer",
        decided_at=datetime(2026, 8, 10, 13, 0, tzinfo=UTC),
        source_evidence_checked=True,
        geometry_checked=True,
        limitations_acknowledged=True,
        statement="Traçado com grupo de detalhe conferido contra a fixture sintética.",
    )
    approved = approve_trace(result, approval)
    _, approval_path = write_approved_trace_revision(approved, tmp_path)
    export = export_scene_package(
        approved.scene,
        tmp_path,
        package_stem="tracado-detalhe",
        extra_package_files=[approval_path],
    )
    assert export.audit.status == "approved"

    frame = _summary_entities(approved.scene, "DETAIL_FRAME")[0]
    painel = _entity_of(approved.scene, DETALHE_PROPOSAL)
    quantities = (tmp_path / "quantitativos.csv").read_text(encoding="utf-8")
    assert str(painel.id) in quantities
    assert str(frame.id) not in quantities

    document = readfile(export.dxf_path)
    modelspace = document.modelspace()
    frame_polylines = [
        polyline for polyline in modelspace.query("LWPOLYLINE") if polyline.dxf.layer == "DETALHES"
    ]
    assert frame_polylines and all(polyline.has_xdata("CROQUITO") for polyline in frame_polylines)


def test_export_de_sketch_fica_fora_dos_quantitativos(tmp_path: Path) -> None:
    result = _solve_com_detalhe(mode="sketch")
    assert result.scene is not None
    approval = SceneApproval(
        approval_id="ap_" + "5" * 16,
        source_scene_id=result.scene.id,
        reviewer_id="eng-teste",
        reviewer_role="engineer",
        decided_at=datetime(2026, 8, 10, 13, 0, tzinfo=UTC),
        source_evidence_checked=True,
        geometry_checked=True,
        limitations_acknowledged=True,
        statement="Traçado com detalhe sketch conferido contra a fixture sintética.",
    )
    approved = approve_trace(result, approval)
    _, approval_path = write_approved_trace_revision(approved, tmp_path)
    export = export_scene_package(
        approved.scene,
        tmp_path,
        package_stem="tracado-sketch",
        extra_package_files=[approval_path],
    )
    assert export.audit.status == "approved"
    painel = _entity_of(approved.scene, DETALHE_PROPOSAL)
    quantities = (tmp_path / "quantitativos.csv").read_text(encoding="utf-8")
    assert str(painel.id) not in quantities


# Painel com o trecho central rebaixado, como a elevação A da Toca: borda esquerda reta
# (chão), borda direita em três níveis — pontas salientes e centro recuado.
PAINEL_RECORTADO_PROPOSAL = "vp_" + "7" * 16
LARGURA_PAINEL_READING = "rd_" + "a1" * 8
COMPRIMENTO_PAINEL_READING = "rd_" + "a2" * 8
CENTRO_PAINEL_READING = "rd_" + "a3" * 8
LOTE_LIVRE_PROPOSAL = "vp_" + "8" * 16
ALAMBRADO_REF_PROPOSAL = "vp_" + "9" * 16
REF_ALTURA_READING = "rd_" + "b1" * 8
GAP_TOPO_READING = "rd_" + "b2" * 8
GAP_DOBRA_READING = "rd_" + "b3" * 8
GAP_BASE_READING = "rd_" + "b4" * 8


def _painel_recortado() -> VisionProposal:
    return VisionProposal(
        id=PAINEL_RECORTADO_PROPOSAL,
        kind="contour",
        geometry=PixelPolyline(
            points=[
                PixelPoint(x=100, y=100),
                PixelPoint(x=300, y=100),
                PixelPoint(x=300, y=180),
                PixelPoint(x=220, y=180),
                PixelPoint(x=220, y=420),
                PixelPoint(x=280, y=420),
                PixelPoint(x=280, y=500),
                PixelPoint(x=100, y=500),
            ],
            closed=True,
        ),
        algorithm="fixture",
        quality_score=0.9,
        label="Painel recortado",
        layer_hint="ALAMBRADO",
    )


def _solve_painel_recortado(
    associations: dict[str, str | list[str] | dict[str, object]],
    *,
    readings: list[DimensionReading] | None = None,
) -> TraceSolveResult:
    packet = _packet().model_copy(
        update={
            "readings": readings
            if readings is not None
            else [
                _reading(LARGURA_PAINEL_READING, value="4.40", kind="width", centre=(200, 90)),
                _reading(COMPRIMENTO_PAINEL_READING, value="9.60", kind="height", centre=(90, 300)),
                _reading(CENTRO_PAINEL_READING, value="2.30", kind="width", centre=(160, 550)),
            ]
        }
    )
    acceptance = _acceptance().model_copy(
        update={"proposal_ids": [PAINEL_RECORTADO_PROPOSAL], "hatch_proposal_ids": []}
    )
    return solve_trace(
        packet,
        [_painel_recortado()],
        acceptance,
        confirmed_associations=associations,
        image_width=600,
        image_height=700,
    )


def test_vao_declarado_amarra_arestas_internas_do_elemento() -> None:
    """A cota 2,30 do rebaixo central não corresponde a nenhum segmento: sem o vão
    declarado ela cairia na aresta mais próxima da evidência (a ponta inferior) e
    encolheria a parte errada do painel."""
    result = _solve_painel_recortado(
        {
            LARGURA_PAINEL_READING: PAINEL_RECORTADO_PROPOSAL,
            COMPRIMENTO_PAINEL_READING: PAINEL_RECORTADO_PROPOSAL,
            CENTRO_PAINEL_READING: {
                "proposal_id": PAINEL_RECORTADO_PROPOSAL,
                "spans_px": [[[100, 300], [220, 300]]],
            },
        }
    )
    assert result.status == "solved_unapproved"
    assert result.scene is not None
    assert all(residual.passed for residual in result.residuals)
    painel = _entity_of(result.scene, PAINEL_RECORTADO_PROPOSAL)
    assert isinstance(painel.geometry, PolylineGeometry)
    xs = [point.x for point in painel.geometry.points]
    assert xs[1] == pytest.approx(4.40, abs=1e-6)
    assert xs[3] == pytest.approx(2.30, abs=1e-6)
    assert xs[4] == pytest.approx(2.30, abs=1e-6)


def test_vao_declarado_aplica_o_mesmo_valor_em_dois_trechos() -> None:
    """Pontas cheias arbitradas: a mesma leitura de 4,40 amarra as duas pontas do
    painel, mesmo com a ponta de baixo desenhada mais curta (280 px contra 300)."""
    result = _solve_painel_recortado(
        {
            LARGURA_PAINEL_READING: {
                "proposal_id": PAINEL_RECORTADO_PROPOSAL,
                "spans_px": [[[100, 140], [300, 140]], [[100, 460], [280, 460]]],
            },
            COMPRIMENTO_PAINEL_READING: PAINEL_RECORTADO_PROPOSAL,
        }
    )
    assert result.status == "solved_unapproved"
    assert result.scene is not None
    assert all(residual.passed for residual in result.residuals)
    painel = _entity_of(result.scene, PAINEL_RECORTADO_PROPOSAL)
    assert isinstance(painel.geometry, PolylineGeometry)
    xs = [point.x for point in painel.geometry.points]
    assert xs[1] == pytest.approx(4.40, abs=1e-6)
    assert xs[6] == pytest.approx(4.40, abs=1e-6)


def test_associacao_declarada_invalida_bloqueia() -> None:
    result = _solve_painel_recortado(
        {
            LARGURA_PAINEL_READING: PAINEL_RECORTADO_PROPOSAL,
            CENTRO_PAINEL_READING: {"proposal_id": PAINEL_RECORTADO_PROPOSAL},
        }
    )
    assert result.status == "review_required"
    assert f"TRACE_ASSOCIATION_INVALID:{CENTRO_PAINEL_READING}" in result.blockers


def _lote_livre_fixture() -> tuple[ReviewPacket, list[VisionProposal], TraceAcceptance]:
    packet = _packet().model_copy(
        update={
            "readings": [
                _reading(REF_ALTURA_READING, value="4.00", kind="height", centre=(310, 300)),
                _reading(GAP_TOPO_READING, value="1.50", kind="width", centre=(225, 105)),
                _reading(GAP_DOBRA_READING, value="1.80", kind="width", centre=(210, 300)),
                _reading(GAP_BASE_READING, value="1.40", kind="width", centre=(230, 495)),
            ]
        }
    )
    proposals = [
        VisionProposal(
            id=LOTE_LIVRE_PROPOSAL,
            kind="contour",
            geometry=PixelPolyline(
                points=[
                    PixelPoint(x=150, y=100),
                    PixelPoint(x=120, y=300),
                    PixelPoint(x=160, y=500),
                ],
                closed=False,
            ),
            algorithm="fixture",
            quality_score=0.9,
            label="Limite do lote",
            layer_hint="LOTE",
        ),
        VisionProposal(
            id=ALAMBRADO_REF_PROPOSAL,
            kind="line",
            geometry=PixelLine(start=PixelPoint(x=300, y=100), end=PixelPoint(x=300, y=500)),
            algorithm="fixture",
            quality_score=0.9,
            label="Alambrado de referência",
            layer_hint="ALAMBRADO",
        ),
    ]
    acceptance = _acceptance().model_copy(
        update={
            "proposal_ids": [LOTE_LIVRE_PROPOSAL, ALAMBRADO_REF_PROPOSAL],
            "hatch_proposal_ids": [],
            "freeform_proposal_ids": [LOTE_LIVRE_PROPOSAL],
        }
    )
    return packet, proposals, acceptance


def test_elemento_como_desenhado_recebe_afastamentos_por_vertice() -> None:
    """O limite do lote não é paralelo de propósito: com `freeform` cada vértice guarda a
    própria faixa e os três afastamentos (1,50/1,80/1,40) ancoram um vértice cada. Sem a
    declaração, a regularização colapsaria o contorno numa faixa só e as três cotas
    disputariam o mesmo vão."""
    packet, proposals, acceptance = _lote_livre_fixture()
    result = solve_trace(
        packet,
        proposals,
        acceptance,
        confirmed_associations={
            REF_ALTURA_READING: ALAMBRADO_REF_PROPOSAL,
            GAP_TOPO_READING: [LOTE_LIVRE_PROPOSAL, ALAMBRADO_REF_PROPOSAL],
            GAP_DOBRA_READING: [LOTE_LIVRE_PROPOSAL, ALAMBRADO_REF_PROPOSAL],
            GAP_BASE_READING: [LOTE_LIVRE_PROPOSAL, ALAMBRADO_REF_PROPOSAL],
        },
        image_width=600,
        image_height=700,
    )
    assert result.status == "solved_unapproved"
    assert result.scene is not None
    gap_residuals = [residual for residual in result.residuals if residual.code.startswith("GAP")]
    assert len(gap_residuals) == 3
    assert all(residual.passed for residual in gap_residuals)
    lote = _entity_of(result.scene, LOTE_LIVRE_PROPOSAL)
    referencia = _entity_of(result.scene, ALAMBRADO_REF_PROPOSAL)
    assert isinstance(lote.geometry, PolylineGeometry)
    assert isinstance(referencia.geometry, LineGeometry)
    referencia_x = referencia.geometry.start.x
    afastamentos = [referencia_x - point.x for point in lote.geometry.points]
    assert afastamentos[0] == pytest.approx(1.50, abs=1e-6)
    assert afastamentos[1] == pytest.approx(1.80, abs=1e-6)
    assert afastamentos[2] == pytest.approx(1.40, abs=1e-6)


def test_sem_freeform_os_afastamentos_distintos_conflitam() -> None:
    """O contraponto do teste acima: sem a declaração o contorno vira uma faixa só e as
    três cotas não podem ser satisfeitas ao mesmo tempo."""
    packet, proposals, acceptance = _lote_livre_fixture()
    result = solve_trace(
        packet,
        proposals,
        acceptance.model_copy(update={"freeform_proposal_ids": []}),
        confirmed_associations={
            REF_ALTURA_READING: ALAMBRADO_REF_PROPOSAL,
            GAP_TOPO_READING: [LOTE_LIVRE_PROPOSAL, ALAMBRADO_REF_PROPOSAL],
            GAP_DOBRA_READING: [LOTE_LIVRE_PROPOSAL, ALAMBRADO_REF_PROPOSAL],
            GAP_BASE_READING: [LOTE_LIVRE_PROPOSAL, ALAMBRADO_REF_PROPOSAL],
        },
        image_width=600,
        image_height=700,
    )
    gap_residuals = [residual for residual in result.residuals if residual.code.startswith("GAP")]
    assert gap_residuals and not all(residual.passed for residual in gap_residuals)


def test_freeform_exige_proposta_aceita() -> None:
    with pytest.raises(ValidationError, match="freeform"):
        _acceptance().model_copy(
            update={"freeform_proposal_ids": ["vp_" + "0" * 16]},
        ).model_validate(
            _acceptance()
            .model_copy(update={"freeform_proposal_ids": ["vp_" + "0" * 16]})
            .model_dump()
        )


# --- Base de dois elementos cotados com canto fundido (2026-08-12, reaproveitada) ------
#
# Histórico: até o E6 esta fixture era a regressão da gravata em si — dois retângulos com
# o canto A fundido, cada largura batendo exata sozinha mas a ORDEM entre as faixas B e D
# invertendo. Com o critério de dono comum do E6 (ver mais abaixo) isso deixou de bloquear
# sozinho: TOTAL e SUB são elementos DISTINTOS, e a faixa B (só de SUB) e a faixa D (só de
# TOTAL) não compartilham dono — é exatamente a relação COTADA entre dois elementos que o
# resíduo assinado do E3 já protege (se a folha diz que o trecho interno é maior que o
# total, o interno saltar para fora é o que ela declara, não defeito de solver). A fixture
# continua útil como base: `test_inversao_entre_faixas_com_dono_comum_continua_bloqueando`
# (E6, mais abaixo) usa exatamente estas duas faixas para provar que um TERCEIRO elemento
# presente nas duas volta a bloquear. A gravata AUTÊNTICA (auto-cruzamento de um único
# elemento) ganhou fixture própria em `_gravata_autentica_fixture`, logo adiante.

BAND_ORDER_TOTAL_PROPOSAL = "vp_" + "0" * 16
BAND_ORDER_SUB_PROPOSAL = "vp_" + "9" * 16
BAND_ORDER_TOTAL_READING = "rd_" + "0" * 16
BAND_ORDER_SUB_READING = "rd_" + "9" * 16

BAND_ORDER_A_PX, BAND_ORDER_B_PX, BAND_ORDER_D_PX = 100.0, 300.0, 500.0
BAND_ORDER_T0, BAND_ORDER_T1, BAND_ORDER_T2 = 100.0, 200.0, 300.0


def _band_order_fixture() -> tuple[ReviewPacket, list[VisionProposal], TraceAcceptance]:
    proposals = [
        VisionProposal(
            id=BAND_ORDER_TOTAL_PROPOSAL,
            kind="contour",
            geometry=_rect(BAND_ORDER_A_PX, BAND_ORDER_T0, BAND_ORDER_D_PX, BAND_ORDER_T1),
            algorithm="fixture",
            quality_score=0.9,
            label="Faixa total",
        ),
        # Colado por baixo do total: o vértice (A, T1) dos dois é o mesmo pixel, então a
        # topologia funde os dois num único canto — é o que dá à faixa "A" a mesma origem
        # nos dois elementos, condição para a inversão aparecer entre B e D.
        VisionProposal(
            id=BAND_ORDER_SUB_PROPOSAL,
            kind="contour",
            geometry=_rect(BAND_ORDER_A_PX, BAND_ORDER_T1, BAND_ORDER_B_PX, BAND_ORDER_T2),
            algorithm="fixture",
            quality_score=0.9,
            label="Faixa parcial",
        ),
    ]
    packet = ReviewPacket(
        dataset_id=DATASET_ID,
        page_number=1,
        image_sha256=DIGEST,
        readings=[
            _reading(
                BAND_ORDER_TOTAL_READING,
                value="5.00",
                kind="width",
                centre=(
                    int((BAND_ORDER_A_PX + BAND_ORDER_D_PX) / 2),
                    int(BAND_ORDER_T0 - 10),
                ),
            ),
            _reading(
                BAND_ORDER_SUB_READING,
                value="8.00",
                kind="width",
                centre=(
                    int((BAND_ORDER_A_PX + BAND_ORDER_B_PX) / 2),
                    int(BAND_ORDER_T1 + 10),
                ),
            ),
        ],
        safety_notes=["Fixture local.", "Revisão humana obrigatória."],
    )
    acceptance = TraceAcceptance(
        acceptance_id="ta_" + "0" * 16,
        reviewer_id="eng-teste",
        reviewer_role="engineer",
        decided_at=datetime(2026, 8, 12, 12, 30, tzinfo=UTC),
        proposal_ids=[BAND_ORDER_TOTAL_PROPOSAL, BAND_ORDER_SUB_PROPOSAL],
    )
    return packet, proposals, acceptance


# --- Gravata AUTÊNTICA: auto-cruzamento de um único elemento (E6, 2026-08-13) ----------
#
# O blocker nasceu para isto: a sequência de faixas de UMA polilinha perdendo a ordem, não
# dois elementos distintos com um canto fundido (ver comentário acima). A fixture é um
# elemento em L — uma polilinha fechada só, `GRAVATA_PROPOSAL` — com duas cotas internas:
# a largura do topo (5,0 m) e a largura da base (8,0 m). Como as duas faixas violadas
# pertencem sempre à MESMA proposta, o dono é trivialmente comum e o critério do E6 nunca
# dispensa o auto-cruzamento.

GRAVATA_PROPOSAL = "vp_" + "7" * 16
GRAVATA_TOTAL_READING = "rd_" + "7" * 16
GRAVATA_SUB_READING = "rd_" + "8" * 16

GRAVATA_A_PX, GRAVATA_B_PX, GRAVATA_D_PX = 100.0, 300.0, 500.0
GRAVATA_T0, GRAVATA_T1, GRAVATA_T2 = 100.0, 200.0, 300.0


def _gravata_autentica_fixture() -> tuple[ReviewPacket, list[VisionProposal], TraceAcceptance]:
    """Elemento em L (uma polilinha fechada só): topo A-D em T0, degrau D-B em T1, base
    B-A em T2. A largura confirmada do topo (5,0 m, A-D) é menor que a largura confirmada
    da base (8,0 m, A-B) do MESMO elemento — cada resíduo bate exato sozinho, mas a faixa
    da base ultrapassa a faixa do topo: a gravata, pega cedo no solve em vez de tarde no
    auditor de export."""
    points = [
        PixelPoint(x=GRAVATA_A_PX, y=GRAVATA_T0),
        PixelPoint(x=GRAVATA_D_PX, y=GRAVATA_T0),
        PixelPoint(x=GRAVATA_D_PX, y=GRAVATA_T1),
        PixelPoint(x=GRAVATA_B_PX, y=GRAVATA_T1),
        PixelPoint(x=GRAVATA_B_PX, y=GRAVATA_T2),
        PixelPoint(x=GRAVATA_A_PX, y=GRAVATA_T2),
    ]
    proposals = [
        VisionProposal(
            id=GRAVATA_PROPOSAL,
            kind="contour",
            geometry=PixelPolyline(points=points, closed=True),
            algorithm="fixture",
            quality_score=0.9,
            label="Elemento em L",
        ),
    ]
    packet = ReviewPacket(
        dataset_id=DATASET_ID,
        page_number=1,
        image_sha256=DIGEST,
        readings=[
            _reading(
                GRAVATA_TOTAL_READING,
                value="5.00",
                kind="width",
                centre=(int((GRAVATA_A_PX + GRAVATA_D_PX) / 2), int(GRAVATA_T0 - 10)),
            ),
            _reading(
                GRAVATA_SUB_READING,
                value="8.00",
                kind="width",
                centre=(int((GRAVATA_A_PX + GRAVATA_B_PX) / 2), int(GRAVATA_T2 + 10)),
            ),
        ],
        safety_notes=["Fixture local.", "Revisão humana obrigatória."],
    )
    acceptance = TraceAcceptance(
        acceptance_id="ta_" + "7" * 16,
        reviewer_id="eng-teste",
        reviewer_role="engineer",
        decided_at=datetime(2026, 8, 12, 12, 30, tzinfo=UTC),
        proposal_ids=[GRAVATA_PROPOSAL],
    )
    return packet, proposals, acceptance


def test_duas_cotas_inconsistentes_no_mesmo_elemento_invertem_a_ordem_e_bloqueiam() -> None:
    """Auto-cruzamento autêntico: a largura do topo (5,0 m) é menor que a largura da base
    do MESMO elemento (8,0 m) — cada resíduo bate exato sozinho, mas a faixa da base
    ultrapassa a faixa do topo. As duas faixas violadas pertencem à mesma proposta, então o
    critério de dono comum do E6 nunca as dispensa: a gravata continua bloqueando cedo no
    solve em vez de tarde no auditor de export."""
    packet, proposals, acceptance = _gravata_autentica_fixture()
    result = solve_trace(
        packet,
        proposals,
        acceptance,
        confirmed_associations={
            GRAVATA_TOTAL_READING: GRAVATA_PROPOSAL,
            GRAVATA_SUB_READING: GRAVATA_PROPOSAL,
        },
        image_width=1000,
        image_height=1000,
        title="TESTE INVERSAO DE ORDEM",
    )

    assert result.status == "conflict", result.blockers
    assert all(residual.passed for residual in result.residuals), result.residuals

    order_blockers = [
        blocker for blocker in result.blockers if blocker.startswith("TRACE_BAND_ORDER_INVERTED:")
    ]
    assert order_blockers, result.blockers
    for blocker in order_blockers:
        subject = blocker.split(":", maxsplit=1)[1]
        assert subject == GRAVATA_PROPOSAL

    assert result.scene is not None
    critical_codes = {
        issue.code for issue in result.scene.issues if issue.severity is IssueSeverity.CRITICAL
    }
    assert "TRACE_BAND_ORDER_INVERTED" in critical_codes

    approval = SceneApproval(
        approval_id="ap_" + "0" * 16,
        source_scene_id=result.scene.id,
        reviewer_id="eng-teste",
        reviewer_role="engineer",
        decided_at=datetime(2026, 8, 12, 13, 0, tzinfo=UTC),
        source_evidence_checked=True,
        geometry_checked=True,
        limitations_acknowledged=True,
        statement="Traçado com inversão de ordem, conferido contra a fixture sintética de teste.",
    )
    with pytest.raises(ValueError, match="blockers"):
        approve_trace(result, approval)


# --- "Como desenhado" dispensa a inversão de ordem só nas faixas dele (2026-08-13) ------
#
# Caso real (Guaxindiba v2): o degrau do recuo do muro (cotado, resolvido a 19,32 m)
# invertia contra o topo de um elemento decorativo sem cota, posicionado só pelo prior
# fraco — e o elemento já estava declarado `freeform`, mas ainda assim acusava. Decisão de
# produto: quem declara um elemento como desenhado já assumiu a posição desenhada dele, e
# a ordem dele contra o resto deixa de ser um defeito do traçado a bloquear. Inversão entre
# faixas normais continua acusando (a gravata acima é o caso protegido).

FREEFORM_ORDER_REF_PROPOSAL = "vp_" + "f1" * 8
FREEFORM_ORDER_MURO_PROPOSAL = "vp_" + "f2" * 8
FREEFORM_ORDER_FAR_PROPOSAL = "vp_" + "f3" * 8
FREEFORM_ORDER_ELEMENTO_PROPOSAL = "vp_" + "f4" * 8
FREEFORM_ORDER_REF_MURO_READING = "rd_" + "f1" * 8
FREEFORM_ORDER_MURO_FAR_READING = "rd_" + "f2" * 8

FREEFORM_ORDER_REF_X, FREEFORM_ORDER_MURO_X = 0.0, 100.0
FREEFORM_ORDER_ELEMENTO_X, FREEFORM_ORDER_FAR_X = 150.0, 1000.0


def _freeform_order_fixture(
    *, freeform: bool
) -> tuple[ReviewPacket, list[VisionProposal], TraceAcceptance]:
    """Referência e muro cotados (20,0 m em 100 px / 5,0 m em 900 px) mais um elemento
    decorativo sem cota, posicionado só pelo prior fraco (px 150). A escala não-uniforme
    entre as duas cotas empurra o prior do elemento para uma posição solucionada antes do
    muro — inversão de ordem clássica, igual ao Guaxindiba."""

    def _vline(proposal_id: str, x: float, label: str) -> VisionProposal:
        return VisionProposal(
            id=proposal_id,
            kind="line",
            geometry=PixelLine(start=PixelPoint(x=x, y=50.0), end=PixelPoint(x=x, y=150.0)),
            algorithm="fixture",
            quality_score=0.9,
            label=label,
        )

    proposals = [
        _vline(FREEFORM_ORDER_REF_PROPOSAL, FREEFORM_ORDER_REF_X, "Referência"),
        _vline(FREEFORM_ORDER_MURO_PROPOSAL, FREEFORM_ORDER_MURO_X, "Muro"),
        _vline(FREEFORM_ORDER_FAR_PROPOSAL, FREEFORM_ORDER_FAR_X, "Extremo distante"),
        _vline(FREEFORM_ORDER_ELEMENTO_PROPOSAL, FREEFORM_ORDER_ELEMENTO_X, "Elemento decorativo"),
    ]
    packet = ReviewPacket(
        dataset_id=DATASET_ID,
        page_number=1,
        image_sha256=DIGEST,
        readings=[
            _reading(
                FREEFORM_ORDER_REF_MURO_READING,
                value="20.00",
                kind="width",
                centre=(int((FREEFORM_ORDER_REF_X + FREEFORM_ORDER_MURO_X) / 2), 40),
            ),
            _reading(
                FREEFORM_ORDER_MURO_FAR_READING,
                value="5.00",
                kind="width",
                centre=(int((FREEFORM_ORDER_MURO_X + FREEFORM_ORDER_FAR_X) / 2), 160),
            ),
        ],
        safety_notes=["Fixture local.", "Revisão humana obrigatória."],
    )
    acceptance = TraceAcceptance(
        acceptance_id="ta_" + "f" * 16,
        reviewer_id="eng-teste",
        reviewer_role="engineer",
        decided_at=datetime(2026, 8, 13, 9, 0, tzinfo=UTC),
        proposal_ids=[
            FREEFORM_ORDER_REF_PROPOSAL,
            FREEFORM_ORDER_MURO_PROPOSAL,
            FREEFORM_ORDER_FAR_PROPOSAL,
            FREEFORM_ORDER_ELEMENTO_PROPOSAL,
        ],
        freeform_proposal_ids=[FREEFORM_ORDER_ELEMENTO_PROPOSAL] if freeform else [],
    )
    return packet, proposals, acceptance


def _freeform_order_associations() -> dict[str, list[str]]:
    return {
        FREEFORM_ORDER_REF_MURO_READING: [
            FREEFORM_ORDER_REF_PROPOSAL,
            FREEFORM_ORDER_MURO_PROPOSAL,
        ],
        FREEFORM_ORDER_MURO_FAR_READING: [
            FREEFORM_ORDER_MURO_PROPOSAL,
            FREEFORM_ORDER_FAR_PROPOSAL,
        ],
    }


def test_elemento_freeform_sem_cota_dispensa_inversao_de_ordem() -> None:
    """O elemento decorativo (sem cota, posição só do prior fraco) inverte a ordem contra
    o muro cotado — mas está declarado `freeform`: quem marcou como desenhado já assumiu a
    posição dele, então a inversão não bloqueia."""
    packet, proposals, acceptance = _freeform_order_fixture(freeform=True)
    result = solve_trace(
        packet,
        proposals,
        acceptance,
        confirmed_associations=_freeform_order_associations(),
        image_width=1200,
        image_height=300,
    )
    order_blockers = [
        blocker for blocker in result.blockers if blocker.startswith("TRACE_BAND_ORDER_INVERTED:")
    ]
    assert not order_blockers, result.blockers
    assert result.status == "solved_unapproved", result.blockers


# `test_sem_freeform_a_mesma_inversao_continua_bloqueando` existia aqui como contraponto de
# `test_elemento_freeform_sem_cota_dispensa_inversao_de_ordem`, provando que a dispensa
# vinha só da declaração `freeform` — não de um afrouxamento geral do check. O E6 introduziu
# esse afrouxamento geral de propósito (dono comum), e a MESMA fixture — decorativo sem
# cota invertendo contra o muro cotado, sem dono comum entre as duas faixas — passou a ser
# exatamente o caso que `test_inversao_entre_elementos_sem_dono_comum_nao_bloqueia` (E6,
# mais abaixo) cobre, com a asserção oposta (não bloqueia). Teste removido por redundância;
# a fixture (`_freeform_order_fixture`, `_freeform_order_associations`) continua em uso.


def test_gravata_autentica_com_dono_comum_nao_e_dispensada_por_outro_freeform_no_aceite() -> None:
    """Defensivo: a gravata autêntica (mesmo elemento, dono comum trivial) continua
    bloqueando mesmo com um terceiro elemento `freeform` no aceite, sem nenhuma relação com
    a violação — a dispensa por `freeform` (E1) e a dispensa por dono comum (E6) são
    critérios independentes, e a presença de QUALQUER freeform na cena não relaxa o
    segundo."""
    packet, proposals, acceptance = _gravata_autentica_fixture()
    decorativo = "vp_" + "f5" * 8
    decorativo_proposal = VisionProposal(
        id=decorativo,
        kind="line",
        geometry=PixelLine(start=PixelPoint(x=800.0, y=800.0), end=PixelPoint(x=850.0, y=850.0)),
        algorithm="fixture",
        quality_score=0.9,
        label="Decorativo isolado",
    )
    result = solve_trace(
        packet,
        [*proposals, decorativo_proposal],
        acceptance.model_copy(
            update={
                "proposal_ids": [*acceptance.proposal_ids, decorativo],
                "freeform_proposal_ids": [decorativo],
            }
        ),
        confirmed_associations={
            GRAVATA_TOTAL_READING: GRAVATA_PROPOSAL,
            GRAVATA_SUB_READING: GRAVATA_PROPOSAL,
        },
        image_width=1000,
        image_height=1000,
    )
    order_blockers = {
        blocker.split(":", maxsplit=1)[1]
        for blocker in result.blockers
        if blocker.startswith("TRACE_BAND_ORDER_INVERTED:")
    }
    assert order_blockers == {GRAVATA_PROPOSAL}, result.blockers


# --- Ordem só acusa faixas com dono em comum (E6, 2026-08-13) --------------------------
#
# Medido no ensaio v5 do job real (grande área x borda do campo; portão sem cota x muro;
# bases de dois patamares fora de escala que resolvem quase flush): depois do E3 a relação
# COTADA entre elementos já é protegida pelo resíduo assinado do `SpanConstraint` — a cena
# espelhada reprova por resíduo, não precisa do check de ordem. O que sobrava era inversão
# entre elementos DISTINTOS sem cota entre si: distorção do croqui na camada `approximate`,
# não defeito do solver. Decisão de produto: só bloquear quando as duas faixas violadas
# compartilham ao menos um `proposal_id` dono; a dispensa por `freeform` (E1) continua
# valendo por cima.


def test_inversao_entre_elementos_sem_dono_comum_nao_bloqueia() -> None:
    """Mesma fixture de `test_sem_freeform_a_mesma_inversao_continua_bloqueando`: o
    elemento decorativo (sem cota, posição só do prior fraco) inverte a ordem contra o
    muro cotado, mas as duas faixas violadas não têm nenhuma junção em comum — nenhum
    `proposal_id` aparece nas duas. Com o critério do E6 isso deixa de bloquear, ainda que
    nenhum dos dois esteja declarado `freeform`. Este teste substitui a garantia daquele
    (a dispensa deixou de vir só da declaração `freeform`); a fixture antiga documenta o
    comportamento anterior ao E6 e passou a depender dele — reportado no handoff."""
    packet, proposals, acceptance = _freeform_order_fixture(freeform=False)
    result = solve_trace(
        packet,
        proposals,
        acceptance,
        confirmed_associations=_freeform_order_associations(),
        image_width=1200,
        image_height=300,
    )
    order_blockers = [
        blocker for blocker in result.blockers if blocker.startswith("TRACE_BAND_ORDER_INVERTED:")
    ]
    assert not order_blockers, result.blockers
    assert result.status == "solved_unapproved", result.blockers


DONO_COMUM_CONNECTOR_PROPOSAL = "vp_" + "c6" * 8


def test_inversao_entre_faixas_com_dono_comum_continua_bloqueando() -> None:
    """Mesma fixture da gravata (`_band_order_fixture`), mais um terceiro elemento — uma
    linha sem cota cujas duas pontas caem exatamente sobre o canto D de `TOTAL_PROPOSAL`
    e o canto B de `SUB_PROPOSAL` (mesmo pixel, então `build_topology` funde cada ponta na
    junção que já existe ali). As duas faixas que a violação aponta passam a ter um dono em
    comum — o conector — mesmo sem o par (total, sub) apontado pela violação ter cota
    direta entre B e D: o compartilhamento é a régua, não o nome do elemento."""
    packet, proposals, acceptance = _band_order_fixture()
    connector = VisionProposal(
        id=DONO_COMUM_CONNECTOR_PROPOSAL,
        kind="line",
        geometry=PixelLine(
            start=PixelPoint(x=BAND_ORDER_D_PX, y=BAND_ORDER_T0),
            end=PixelPoint(x=BAND_ORDER_B_PX, y=BAND_ORDER_T2),
        ),
        algorithm="fixture",
        quality_score=0.9,
        label="Conector sem cota",
    )
    result = solve_trace(
        packet,
        [*proposals, connector],
        acceptance.model_copy(
            update={"proposal_ids": [*acceptance.proposal_ids, DONO_COMUM_CONNECTOR_PROPOSAL]}
        ),
        confirmed_associations={
            BAND_ORDER_TOTAL_READING: BAND_ORDER_TOTAL_PROPOSAL,
            BAND_ORDER_SUB_READING: BAND_ORDER_SUB_PROPOSAL,
        },
        image_width=1000,
        image_height=1000,
    )
    order_blockers = {
        blocker.split(":", maxsplit=1)[1]
        for blocker in result.blockers
        if blocker.startswith("TRACE_BAND_ORDER_INVERTED:")
    }
    assert order_blockers >= {BAND_ORDER_TOTAL_PROPOSAL, BAND_ORDER_SUB_PROPOSAL}, result.blockers


# --- O lado do vão vem do traçado das FAIXAS (Guaxindiba v2, 2026-08-13) ---------------
#
# O DXF real saiu com o campo do lado errado do muro do vizinho e os doze resíduos verdes.
# A cota entrava no solver com o lado dado pela JUNÇÃO representativa da associação, não
# pela FAIXA — e a faixa é a incógnita. Um elemento desenhado torto (dentro dos 12° que a
# regularização absorve) tem a faixa na média das pontas, então a ponta que fica perto do
# recorte da evidência pode estar do outro lado da faixa vizinha. Emitida assim, a
# restrição pede exatamente o espelho, o solver obedece e o resíduo — que é |distância| —
# aprova. Aqui o muro é uma linha inclinada 10,9° cuja faixa (y 365) cai ABAIXO do topo do
# campo (y 300), enquanto a ponta esquerda dele (y 250) fica ACIMA.

SIDE_CAMPO_PROPOSAL = "vp_" + "a1" * 8
SIDE_MURO_PROPOSAL = "vp_" + "b2" * 8
SIDE_ALTURA_READING = "rd_" + "a1" * 8
SIDE_VAO_TOPO_READING = "rd_" + "b2" * 8
SIDE_VAO_FUNDO_READING = "rd_" + "c3" * 8

SIDE_WIDTH, SIDE_HEIGHT = 1600, 1000
SIDE_CAMPO_TOP_PX, SIDE_CAMPO_BOTTOM_PX = 300.0, 700.0


def _side_fixture(
    *, vao_fundo_m: str
) -> tuple[ReviewPacket, list[VisionProposal], TraceAcceptance]:
    """Campo retangular e muro torto, com três cotas confirmadas.

    O muro vai de (200, 250) a (1400, 480): 10,9° do eixo, dentro da tolerância de
    esquadro, então a regularização o achata numa faixa só, em y 365. `vao_fundo_m` é a
    cota do muro até o FUNDO do campo — 13,40 fecha a cadeia do lado traçado
    (6,60 + 13,40 = 20,00) e 26,60 só fecha na cena espelhada.
    """
    proposals = [
        VisionProposal(
            id=SIDE_CAMPO_PROPOSAL,
            kind="contour",
            geometry=_rect(100.0, SIDE_CAMPO_TOP_PX, 1500.0, SIDE_CAMPO_BOTTOM_PX),
            algorithm="fixture",
            quality_score=0.9,
            label="Contorno do campo",
            layer_hint="CAMPO",
        ),
        VisionProposal(
            id=SIDE_MURO_PROPOSAL,
            kind="line",
            geometry=PixelLine(
                start=PixelPoint(x=200.0, y=250.0),
                end=PixelPoint(x=1400.0, y=480.0),
            ),
            algorithm="fixture",
            quality_score=0.9,
            label="Muro do vizinho",
            layer_hint="MURO",
        ),
    ]
    packet = ReviewPacket(
        dataset_id=DATASET_ID,
        page_number=1,
        image_sha256=DIGEST,
        readings=[
            _reading(SIDE_ALTURA_READING, value="20.00", kind="height", centre=(60, 500)),
            _reading(SIDE_VAO_TOPO_READING, value="6.60", kind="height", centre=(800, 285)),
            _reading(SIDE_VAO_FUNDO_READING, value=vao_fundo_m, kind="height", centre=(800, 690)),
        ],
        safety_notes=["Fixture local.", "Revisão humana obrigatória."],
    )
    acceptance = TraceAcceptance(
        acceptance_id="ta_" + "a1" * 8,
        reviewer_id="eng-teste",
        reviewer_role="engineer",
        decided_at=datetime(2026, 8, 13, 12, 30, tzinfo=UTC),
        proposal_ids=[SIDE_CAMPO_PROPOSAL, SIDE_MURO_PROPOSAL],
    )
    return packet, proposals, acceptance


def _side_solve(*, vao_fundo_m: str) -> TraceSolveResult:
    packet, proposals, acceptance = _side_fixture(vao_fundo_m=vao_fundo_m)
    return solve_trace(
        packet,
        proposals,
        acceptance,
        confirmed_associations={
            SIDE_ALTURA_READING: SIDE_CAMPO_PROPOSAL,
            SIDE_VAO_TOPO_READING: [SIDE_MURO_PROPOSAL, SIDE_CAMPO_PROPOSAL],
            SIDE_VAO_FUNDO_READING: [SIDE_MURO_PROPOSAL, SIDE_CAMPO_PROPOSAL],
        },
        image_width=SIDE_WIDTH,
        image_height=SIDE_HEIGHT,
    )


def test_vao_assinado_pelo_tracado_mantem_o_lado_do_desenho() -> None:
    """As três cotas fecham no lado traçado: o muro fica 6,60 m abaixo do topo do campo.

    Antes do sinal vir da faixa, esta mesma folha — cotas coerentes entre si — resolvia em
    conflito, com 4,40 m de resíduo em cada uma das três: a emissão pela junção mandava o
    muro para cima do campo e a cadeia não fechava mais.
    """
    result = _side_solve(vao_fundo_m="13.40")

    assert result.status == "solved_unapproved", result.blockers
    assert all(residual.passed for residual in result.residuals), [
        (residual.code, str(residual.absolute_error_m)) for residual in result.residuals
    ]
    assert result.scene is not None
    campo = _bbox(_entity_of(result.scene, SIDE_CAMPO_PROPOSAL).geometry)
    muro = _entity_of(result.scene, SIDE_MURO_PROPOSAL).geometry
    assert isinstance(muro, LineGeometry)
    # Em CAD o Y já está espelhado: o muro fica ABAIXO do topo do campo, como na folha.
    assert campo[3] - muro.start.y == pytest.approx(6.60, abs=0.01)
    assert muro.start.y - campo[1] == pytest.approx(13.40, abs=0.01)


def test_vao_assinado_expoe_a_cena_espelhada_como_residuo() -> None:
    """A cadeia que só fecha espelhada (26,60 em vez de 13,40) vira resíduo estourado.

    Medido antes desta mudança, com a mesma entrada: os três resíduos verdes (erro da
    ordem de 1e-6) e o muro entregue 6,60 m ACIMA do topo do campo — a cena espelhada,
    invisível para o resíduo, que é absoluto. Só o check de ordem de faixas acusava, e de
    forma cega (nomeando os dois elementos, sem dizer qual cota não fecha).
    """
    result = _side_solve(vao_fundo_m="26.60")

    assert result.status == "conflict", result.blockers
    assert "NUMERIC_RESIDUAL_EXCEEDS_TOLERANCE" in result.blockers
    failed = [residual for residual in result.residuals if not residual.passed]
    assert len(failed) == 3
    # O espelho erra por duas vezes 6,60 repartido pelo mínimo quadrado — não some no |erro|.
    assert all(residual.absolute_error_m > Decimal("1.0") for residual in failed)


# --- Empate no traçado continua absoluto (dente do muro, 2026-08-13) -------------------
#
# O outro lado da mesma regra: duas faixas desenhadas coincidentes e declaradas distintas
# (`keep_apart`) não têm ordem traçada — o gap entre elas é ruído de pixel. Assinar por
# esse ruído inventaria um lado e criaria conflito onde a folha não tem nenhum: a mureta
# do Guaxindiba está desenhada em cima da borda do campo e a cota a põe 3,30 m FORA.

TIE_CAMPO_PROPOSAL = "vp_" + "c1" * 8
TIE_MURETA_PROPOSAL = "vp_" + "d2" * 8
TIE_LARGURA_READING = "rd_" + "c1" * 8
TIE_DENTE_READING = "rd_" + "d2" * 8
TIE_TOTAL_READING = "rd_" + "e3" * 8


def test_empate_no_tracado_segue_a_cadeia_de_cotas_e_nao_o_pixel() -> None:
    """A mureta é desenhada 0,5 px DENTRO da borda do campo e sai 3,30 m fora dela.

    A cadeia com lado (25,90 do campo, 29,20 da borda esquerda até a mureta) é quem decide
    de que lado o empate cai. Assinado pelo ruído do pixel, este mesmo aceite dava
    conflito com 2,20 m de resíduo em cada uma das três cotas — falso positivo puro.
    """
    proposals = [
        VisionProposal(
            id=TIE_CAMPO_PROPOSAL,
            kind="contour",
            geometry=_rect(100.0, 100.0, 500.0, 400.0),
            algorithm="fixture",
            quality_score=0.9,
            label="Contorno do campo",
            layer_hint="CAMPO",
        ),
        VisionProposal(
            id=TIE_MURETA_PROPOSAL,
            kind="line",
            geometry=PixelLine(
                start=PixelPoint(x=499.5, y=120.0),
                end=PixelPoint(x=499.5, y=380.0),
            ),
            algorithm="fixture",
            quality_score=0.9,
            label="Mureta lateral direita",
            layer_hint="MURO",
        ),
    ]
    packet = ReviewPacket(
        dataset_id=DATASET_ID,
        page_number=1,
        image_sha256=DIGEST,
        readings=[
            _reading(TIE_LARGURA_READING, value="25.90", kind="width", centre=(300, 90)),
            _reading(TIE_DENTE_READING, value="3.30", kind="width", centre=(520, 250)),
            _reading(TIE_TOTAL_READING, value="29.20", kind="width", centre=(60, 250)),
        ],
        safety_notes=["Fixture local.", "Revisão humana obrigatória."],
    )
    acceptance = TraceAcceptance(
        acceptance_id="ta_" + "c1" * 8,
        reviewer_id="eng-teste",
        reviewer_role="engineer",
        decided_at=datetime(2026, 8, 13, 12, 30, tzinfo=UTC),
        proposal_ids=[TIE_CAMPO_PROPOSAL, TIE_MURETA_PROPOSAL],
        keep_apart_pairs=[(TIE_CAMPO_PROPOSAL, TIE_MURETA_PROPOSAL)],
    )

    result = solve_trace(
        packet,
        proposals,
        acceptance,
        confirmed_associations={
            TIE_LARGURA_READING: TIE_CAMPO_PROPOSAL,
            TIE_DENTE_READING: [TIE_CAMPO_PROPOSAL, TIE_MURETA_PROPOSAL],
            TIE_TOTAL_READING: [TIE_CAMPO_PROPOSAL, TIE_MURETA_PROPOSAL],
        },
        image_width=1200,
        image_height=800,
    )

    assert result.status == "solved_unapproved", result.blockers
    assert all(residual.passed for residual in result.residuals), [
        (residual.code, str(residual.absolute_error_m)) for residual in result.residuals
    ]
    assert result.scene is not None
    campo = _bbox(_entity_of(result.scene, TIE_CAMPO_PROPOSAL).geometry)
    mureta = _entity_of(result.scene, TIE_MURETA_PROPOSAL).geometry
    assert isinstance(mureta, LineGeometry)
    assert campo[2] - campo[0] == pytest.approx(25.90, abs=0.01)
    assert mureta.start.x - campo[2] == pytest.approx(3.30, abs=0.01)


# --- Vão em par não carrega a ordem dos cliques (E7, 2026-08-13) -----------------------
#
# Defeito medido: a eleição near/far das duas arestas do vão usava só a posição traçada da
# junção representativa. Dois elementos desenhados na MESMA coordenada — o caso que
# `keep_apart` existe para tratar — empatam essa chave, e `sorted`, estável, completava o
# desempate com a posição no array da associação: a ordem em que o revisor clicou. Com o
# empate de faixas a restrição sai sem sinal (`SpanConstraint.signed=False`) e era essa
# ordem que fixava o lado da equação — `[a, b]` e `[b, a]` trocavam os dois elementos de
# lado, arrastavam atrás quem dependia deles e fechavam com os MESMOS resíduos verdes,
# porque o resíduo reportado é absoluto.

PAR_POSTE_NORTE = "vp_" + "a1" * 8
PAR_POSTE_SUL = "vp_" + "b2" * 8
PAR_QUADRA = "vp_" + "c3" * 8
PAR_VAO_READING = "rd_" + "a1" * 8
PAR_QUADRA_READING = "rd_" + "b2" * 8


def _par_proposals() -> list[VisionProposal]:
    """Dois trechos de muro desenhados na mesma coluna e uma quadra com cota própria.

    Os dois postes caem exatamente em x=100 (a folha os desenha alinhados) e estão longe um
    do outro em y, então nenhum vértice funde e cada um fica com a sua faixa — faixas
    distintas, na mesma coordenada traçada. É a assinatura do caso real: par de elementos
    coincidentes no papel mais um terceiro sistema, ligado por outra cota.
    """
    return [
        VisionProposal(
            id=PAR_POSTE_NORTE,
            kind="line",
            geometry=PixelLine(
                start=PixelPoint(x=100.0, y=100.0),
                end=PixelPoint(x=100.0, y=200.0),
            ),
            algorithm="fixture",
            quality_score=0.9,
            label="Trecho de muro norte",
            layer_hint="MURO",
        ),
        VisionProposal(
            id=PAR_POSTE_SUL,
            kind="line",
            geometry=PixelLine(
                start=PixelPoint(x=100.0, y=500.0),
                end=PixelPoint(x=100.0, y=600.0),
            ),
            algorithm="fixture",
            quality_score=0.9,
            label="Trecho de muro sul",
            layer_hint="MURO",
        ),
        VisionProposal(
            id=PAR_QUADRA,
            kind="contour",
            geometry=_rect(300.0, 100.0, 500.0, 300.0),
            algorithm="fixture",
            quality_score=0.9,
            label="Quadra",
            layer_hint="CAMPO",
        ),
    ]


def _par_solve(pair: list[str]) -> TraceSolveResult:
    packet = ReviewPacket(
        dataset_id=DATASET_ID,
        page_number=1,
        image_sha256=DIGEST,
        readings=[
            _reading(PAR_VAO_READING, value="5.00", kind="width", centre=(100, 350)),
            _reading(PAR_QUADRA_READING, value="20.00", kind="width", centre=(400, 90)),
        ],
        safety_notes=["Fixture local.", "Revisão humana obrigatória."],
    )
    acceptance = TraceAcceptance(
        acceptance_id="ta_" + "a1" * 8,
        reviewer_id="eng-teste",
        reviewer_role="engineer",
        decided_at=datetime(2026, 8, 13, 15, 0, tzinfo=UTC),
        proposal_ids=[PAR_POSTE_NORTE, PAR_POSTE_SUL, PAR_QUADRA],
    )
    return solve_trace(
        packet,
        _par_proposals(),
        acceptance,
        confirmed_associations={
            PAR_VAO_READING: pair,
            PAR_QUADRA_READING: PAR_QUADRA,
        },
        image_width=600,
        image_height=700,
    )


def _scene_without_clock_ids(scene: SceneRevision) -> dict[str, object]:
    """A cena inteira menos o que nasce do relógio, não do traçado.

    `Entity.id` cai no default `new_uuid7` para balão e legenda, e `created_at` é o instante
    do solve: dois solves da MESMA entrada já divergem nesses campos. Todo o resto —
    geometria, precisão, layer, provenance, medidas, constraints e issues — é comparado.
    """
    dump = scene.model_dump(mode="json")
    dump.pop("created_at", None)
    entities = dump["entities"]
    assert isinstance(entities, list)
    for entity in entities:
        entity.pop("id", None)
    return dump


def test_vao_em_par_independe_da_ordem_dos_cliques() -> None:
    """Clicar muro→campo ou campo→muro entrega a MESMA cena, byte a byte.

    Antes da chave total de eleição (`_edge_order_key`), inverter o par trocava os dois
    trechos de lado (0,00 m ↔ 5,00 m) e deslocava a quadra ~9 m, com todos os resíduos
    verdes nas duas ordens — nada acusava o defeito no relatório.
    """
    direta = _par_solve([PAR_POSTE_NORTE, PAR_POSTE_SUL])
    invertida = _par_solve([PAR_POSTE_SUL, PAR_POSTE_NORTE])

    assert direta.status == "solved_unapproved", direta.blockers
    assert invertida.status == "solved_unapproved", invertida.blockers
    assert PAR_VAO_READING not in direta.unapplied_reading_ids
    assert direta.blockers == invertida.blockers
    assert direta.unapplied_reading_ids == invertida.unapplied_reading_ids
    assert direta.scene is not None
    assert invertida.scene is not None

    # Os dois trechos ficavam trocados de lado conforme a ordem do par.
    for scene in (direta.scene, invertida.scene):
        norte = _entity_of(scene, PAR_POSTE_NORTE).geometry
        sul = _entity_of(scene, PAR_POSTE_SUL).geometry
        assert isinstance(norte, LineGeometry)
        assert isinstance(sul, LineGeometry)
        assert (norte.start.x, sul.start.x) == pytest.approx((0.0, 5.00), abs=0.01)

    # O par não era a única coisa que a ordem movia: quem se apoiava nos dois elementos
    # deslizava junto, então a comparação é da cena inteira, não só dos dois trechos.
    assert _scene_without_clock_ids(direta.scene) == _scene_without_clock_ids(invertida.scene)
    assert [residual.model_dump() for residual in direta.residuals] == [
        residual.model_dump() for residual in invertida.residuals
    ]


def test_vao_em_par_do_mesmo_solve_e_reprodutivel() -> None:
    """Contraprova da comparação: repetir a MESMA ordem não muda nada na cena.

    Sem isto, um `_scene_without_clock_ids` frouxo demais faria o teste anterior passar
    por acidente.
    """
    primeira = _par_solve([PAR_POSTE_NORTE, PAR_POSTE_SUL])
    segunda = _par_solve([PAR_POSTE_NORTE, PAR_POSTE_SUL])

    assert primeira.scene is not None
    assert segunda.scene is not None
    assert _scene_without_clock_ids(primeira.scene) == _scene_without_clock_ids(segunda.scene)


# --- Cota de raio/diâmetro em círculo (achado do Raul Campelo, 2026-08-12) -------------
#
# Círculo não tem junção e nunca entrou no sistema de faixas: as cotas de diâmetro (9,60 e
# 5,04) viravam notas presas e o círculo saía aproximado. Leitura confirmada de raio ou
# diâmetro com associação simples passa a determinar o círculo — raio da cota, entidade
# `exact`, medida confirmada amarrada e cota diametral (⌀) no ângulo da evidência.

CIRCULO_DIAMETRO_READING = "rd_" + "d1" * 8
CIRCULO_RAIO_READING = "rd_" + "d2" * 8

# Centro do círculo da fixture, em pixels, e um recorte de evidência à direita dele.
CIRCULO_CENTRO_PX = (
    int((CAMPO_LEFT_PX + CAMPO_RIGHT_PX) / 2),
    int((CAMPO_TOP_PX + CAMPO_BOTTOM_PX) / 2),
)
EVIDENCIA_DIREITA_PX = (CIRCULO_CENTRO_PX[0] + 50, CIRCULO_CENTRO_PX[1])
EVIDENCIA_ABAIXO_PX = (CIRCULO_CENTRO_PX[0], CIRCULO_CENTRO_PX[1] + 50)


def _solve_com_cotas_de_circulo(
    cotas: list[tuple[str, str, str, tuple[int, int]]],
) -> TraceSolveResult:
    """A fixture do Guaxindiba com cotas de raio/diâmetro associadas ao círculo central."""
    base = _packet()
    packet = base.model_copy(
        update={
            "readings": [
                *base.readings,
                *(
                    _reading(reading_id, value=value, kind=kind, centre=centre)
                    for reading_id, kind, value, centre in cotas
                ),
            ]
        }
    )
    associations: dict[str, str] = dict(_associations())
    for reading_id, _kind, _value, _centre in cotas:
        associations[reading_id] = CIRCULO_PROPOSAL
    return solve_trace(
        packet,
        _proposals(),
        _acceptance(),
        confirmed_associations=associations,
        image_width=600,
        image_height=700,
        title="CAMPO GUAXINDIBA SINTETICO",
    )


def _cota_diametral(scene: SceneRevision) -> Entity:
    cotas = [entity for entity in scene.entities if entity.kind is EntityKind.DIAMETER_DIMENSION]
    assert len(cotas) == 1
    return cotas[0]


def _medida_de(scene: SceneRevision, reading_id: str) -> Measurement:
    for measurement in scene.measurements:
        if measurement.provenance and reading_id in measurement.provenance.source_ids:
            return measurement
    raise AssertionError(f"medida da leitura não encontrada: {reading_id}")


def test_cota_de_diametro_determina_o_circulo() -> None:
    """O diâmetro escrito manda no raio; o círculo sai exact com a cota ⌀ desenhada."""
    result = _solve_com_cotas_de_circulo(
        [(CIRCULO_DIAMETRO_READING, "diameter", "5.00", EVIDENCIA_DIREITA_PX)]
    )
    assert result.status == "solved_unapproved", result.blockers
    assert result.scene is not None

    circulo = _entity_of(result.scene, CIRCULO_PROPOSAL)
    assert circulo.precision is Precision.EXACT
    assert circulo.layer is not LayerName.APROXIMADO
    assert isinstance(circulo.geometry, CircleGeometry)
    assert circulo.geometry.radius == pytest.approx(2.5)
    assert circulo.id not in result.scene.accepted_approximation_ids
    assert circulo.provenance is not None
    assert circulo.provenance.source_ids[0] == CIRCULO_PROPOSAL
    assert CIRCULO_DIAMETRO_READING in circulo.provenance.source_ids
    assert circulo.provenance.summary_code == "TRACED_CIRCLE_DETERMINED_BY_CONFIRMED_READING"

    medida = _medida_de(result.scene, CIRCULO_DIAMETRO_READING)
    assert medida.entity_id == circulo.id
    assert medida.kind is MeasurementKind.DIAMETER
    assert medida.confirmed
    assert medida.value_si == Decimal("5.00")

    cota = _cota_diametral(result.scene)
    assert cota.layer is LayerName.COTAS
    assert cota.precision is Precision.EXACT
    assert isinstance(cota.geometry, DiameterDimensionGeometry)
    assert cota.geometry.radius == pytest.approx(2.5)
    # A evidência está à direita do centro na folha: a cota atravessa o círculo por ali.
    assert cota.geometry.angle == pytest.approx(0.0, abs=0.05)
    assert cota.geometry.text_override == "⌀ 5.00 m"

    # A leitura foi aplicada: não sobra como não aplicada nem vira nota presa.
    assert CIRCULO_DIAMETRO_READING not in result.unapplied_reading_ids
    assert result.exact_entity_count == 5
    assert result.approximate_entity_count == 1
    # Medida confirmada coerente com a geometria: só falta a aprovação humana.
    assert result.scene.export_errors() == ["SCENE_NOT_APPROVED"]


def test_cota_de_raio_determina_o_circulo_e_e_desenhada_em_diametro() -> None:
    """Raio confirmado entra no cálculo; a cota desenhada continua diametral (⌀)."""
    result = _solve_com_cotas_de_circulo(
        [(CIRCULO_RAIO_READING, "radius", "2.50", EVIDENCIA_DIREITA_PX)]
    )
    assert result.status == "solved_unapproved", result.blockers
    assert result.scene is not None

    circulo = _entity_of(result.scene, CIRCULO_PROPOSAL)
    assert circulo.precision is Precision.EXACT
    assert isinstance(circulo.geometry, CircleGeometry)
    assert circulo.geometry.radius == pytest.approx(2.5)

    medida = _medida_de(result.scene, CIRCULO_RAIO_READING)
    assert medida.kind is MeasurementKind.RADIUS
    assert medida.value_si == Decimal("2.50")

    cota = _cota_diametral(result.scene)
    assert isinstance(cota.geometry, DiameterDimensionGeometry)
    assert cota.geometry.text_override == "⌀ 5.00 m"
    assert result.scene.export_errors() == ["SCENE_NOT_APPROVED"]


def test_duas_cotas_divergentes_no_mesmo_circulo_bloqueiam() -> None:
    """Raio 2,00 e diâmetro 5,00 no mesmo círculo: conflito declarado, cena construída."""
    result = _solve_com_cotas_de_circulo(
        [
            (CIRCULO_RAIO_READING, "radius", "2.00", EVIDENCIA_ABAIXO_PX),
            (CIRCULO_DIAMETRO_READING, "diameter", "5.00", EVIDENCIA_DIREITA_PX),
        ]
    )
    assert result.status == "conflict"
    assert f"TRACE_CIRCLE_READINGS_CONFLICT:{CIRCULO_PROPOSAL}" in result.blockers
    assert result.scene is not None

    circulo = _entity_of(result.scene, CIRCULO_PROPOSAL)
    assert isinstance(circulo.geometry, CircleGeometry)
    # Determinístico: manda a leitura de menor id (…d1d1 antes de …d2d2).
    assert circulo.geometry.radius == pytest.approx(2.5)
    # As duas medidas confirmadas ficam na cena; o portão do core acusa a incompatível.
    assert _medida_de(result.scene, CIRCULO_RAIO_READING).value_si == Decimal("2.00")
    assert _medida_de(result.scene, CIRCULO_DIAMETRO_READING).value_si == Decimal("5.00")
    assert any(error.startswith("MEASUREMENT_MISMATCH") for error in result.scene.export_errors())


def test_export_leva_a_cota_diametral_auditada(tmp_path: Path) -> None:
    """A cota diametral vira DIMENSION diametral de verdade no DXF, com XDATA."""
    result = _solve_com_cotas_de_circulo(
        [(CIRCULO_DIAMETRO_READING, "diameter", "5.00", EVIDENCIA_DIREITA_PX)]
    )
    assert result.scene is not None

    approval = SceneApproval(
        approval_id="ap_" + "5" * 16,
        source_scene_id=result.scene.id,
        reviewer_id="eng-teste",
        reviewer_role="engineer",
        decided_at=datetime(2026, 8, 12, 13, 0, tzinfo=UTC),
        source_evidence_checked=True,
        geometry_checked=True,
        limitations_acknowledged=True,
        statement="Traçado com cota de diâmetro conferido contra o croqui sintético.",
    )
    approved = approve_trace(result, approval)
    export = export_scene_package(approved.scene, tmp_path, package_stem="tracado-circulo")
    assert export.audit.status == "approved"

    document = readfile(export.dxf_path)
    modelspace = document.modelspace()
    dimensions = modelspace.query("DIMENSION")
    # As seis cotas lineares da fixture mais a diametral do círculo.
    assert len(dimensions) == 7
    diametrais = [
        dimension
        for dimension in dimensions
        if isinstance(dimension, Dimension) and dimension.dimtype & 7 == 3
    ]
    assert len(diametrais) == 1
    assert diametrais[0].has_xdata("CROQUITO")
    assert diametrais[0].dxf.layer == "COTAS"

    # A cota pousa onde o croqui a escreveu: a evidência está à direita do centro, e é
    # ali que o texto renderizado fica — não do outro lado do círculo.
    circulo = _entity_of(approved.scene, CIRCULO_PROPOSAL)
    assert isinstance(circulo.geometry, CircleGeometry)
    bloco = document.blocks.get(diametrais[0].dxf.geometry)
    textos = [entidade for entidade in bloco if entidade.dxftype() == "MTEXT"]
    assert len(textos) == 1
    assert textos[0].dxf.insert.x > circulo.geometry.center.x


def test_circulo_em_detalhe_sketch_continua_com_a_cota_como_nota() -> None:
    """Desenho sem escala não é determinado por cota: o ⌀ segue como nota presa."""
    base = _packet()
    packet = base.model_copy(
        update={
            "readings": [
                *base.readings,
                _reading(
                    CIRCULO_DIAMETRO_READING,
                    value="5.00",
                    kind="diameter",
                    centre=EVIDENCIA_DIREITA_PX,
                ),
            ]
        }
    )
    acceptance = _acceptance().model_copy(
        update={
            "detail_groups": [
                TraceDetailGroup(
                    detail_id="S",
                    title="Isométrico do círculo",
                    proposal_ids=[CIRCULO_PROPOSAL],
                    mode="sketch",
                )
            ]
        }
    )
    result = solve_trace(
        packet,
        _proposals(),
        acceptance,
        confirmed_associations={**_associations(), CIRCULO_DIAMETRO_READING: CIRCULO_PROPOSAL},
        image_width=600,
        image_height=700,
    )
    assert result.status == "solved_unapproved", result.blockers
    assert result.scene is not None

    circulo = _entity_of(result.scene, CIRCULO_PROPOSAL)
    assert circulo.precision is Precision.APPROXIMATE
    assert not any(entity.kind is EntityKind.DIAMETER_DIMENSION for entity in result.scene.entities)
    assert any(
        entity.kind is EntityKind.TEXT
        and entity.provenance is not None
        and CIRCULO_DIAMETRO_READING in entity.provenance.source_ids
        for entity in result.scene.entities
    )


# --- Critério de escopo no traçado (paridade com o solver retangular, ADR-0017) --------
#
# A issue crítica do critério declarado no caso nascia só no fluxo retangular: a cena
# traçada saía sem ela e o portão de exportação nunca via o critério.

CRITERIO_CODIGO = "ACC_GUA_001"
CRITERIO_TEXTO = "Perímetro, linha central, círculo, áreas e gols são entidades CAD limpas."


def _solve_com_criterios(
    criteria: Sequence[ScopeCriterion] = (
        ScopeCriterion(code=CRITERIO_CODIGO, text=CRITERIO_TEXTO),
    ),
) -> TraceSolveResult:
    return solve_trace(
        _packet(),
        _proposals(),
        _acceptance(),
        confirmed_associations=_associations(),
        required_criteria=criteria,
        image_width=600,
        image_height=700,
        title="CAMPO GUAXINDIBA SINTETICO",
    )


def _aprovacao(
    scene_id: UUID,
    *,
    covered: Sequence[str] = (),
    acknowledged: Sequence[str] = (),
) -> SceneApproval:
    return SceneApproval(
        approval_id="ap_" + "c" * 16,
        source_scene_id=scene_id,
        reviewer_id="eng-teste",
        reviewer_role="engineer",
        decided_at=datetime(2026, 8, 12, 14, 0, tzinfo=UTC),
        source_evidence_checked=True,
        geometry_checked=True,
        limitations_acknowledged=True,
        covered_criteria=list(covered),
        acknowledged_criteria=list(acknowledged),
        statement="Traçado conferido contra o croqui sintético de fixture do critério.",
    )


def test_criterio_exigido_vira_issue_critica_com_o_texto_do_caso() -> None:
    """A cena traçada carrega o critério do caso com o texto, não com frase genérica."""
    result = _solve_com_criterios()
    assert result.status == "solved_unapproved", result.blockers
    assert result.scene is not None
    assert [criterion.code for criterion in result.required_criteria] == [CRITERIO_CODIGO]

    criterio = next(issue for issue in result.scene.issues if issue.code == CRITERIO_CODIGO)
    assert criterio.severity is IssueSeverity.CRITICAL
    assert criterio.status is IssueStatus.OPEN
    assert criterio.message == CRITERIO_TEXTO
    # Sem declaração humana o portão de exportação continua bloqueando.
    assert f"OPEN_CRITICAL_ISSUE:{CRITERIO_CODIGO}" in result.scene.export_errors()


def test_criterio_sem_texto_cai_na_frase_padrao() -> None:
    result = _solve_com_criterios((ScopeCriterion(code=CRITERIO_CODIGO),))
    assert result.scene is not None
    criterio = next(issue for issue in result.scene.issues if issue.code == CRITERIO_CODIGO)
    assert criterio.message == FALLBACK_CRITERION_MESSAGE


def test_tracado_sem_criterio_declarado_nao_ganha_issue_nova() -> None:
    """As demos sintéticas não declaram critério e seguem exatamente como antes."""
    sem_criterio = _solve()
    com_criterio = _solve_com_criterios()
    assert sem_criterio.scene is not None and com_criterio.scene is not None
    assert sem_criterio.required_criteria == []
    novos = {issue.code for issue in com_criterio.scene.issues} - {
        issue.code for issue in sem_criterio.scene.issues
    }
    assert novos == {CRITERIO_CODIGO}


def test_aprovacao_do_tracado_declara_coberto_e_pendente() -> None:
    """Coberto fecha como `resolved`; reconhecido, como `accepted`; ambos exportam."""
    coberto = _solve_com_criterios()
    assert coberto.scene is not None
    aprovado = approve_trace(coberto, _aprovacao(coberto.scene.id, covered=[CRITERIO_CODIGO]))
    criterio = next(issue for issue in aprovado.scene.issues if issue.code == CRITERIO_CODIGO)
    assert criterio.status is IssueStatus.RESOLVED
    assert aprovado.scene.export_errors() == []

    pendente = _solve_com_criterios()
    assert pendente.scene is not None
    reconhecido = approve_trace(
        pendente, _aprovacao(pendente.scene.id, acknowledged=[CRITERIO_CODIGO])
    )
    assert (
        next(issue for issue in reconhecido.scene.issues if issue.code == CRITERIO_CODIGO).status
        is IssueStatus.ACCEPTED
    )
    assert reconhecido.scene.export_errors() == []


def test_aprovacao_do_tracado_recusa_criterio_nao_declarado_e_codigo_estranho() -> None:
    result = _solve_com_criterios()
    assert result.scene is not None

    with pytest.raises(ValueError, match="blockers"):
        approve_trace(result, _aprovacao(result.scene.id))

    with pytest.raises(ValueError, match="critério de escopo"):
        approve_trace(result, _aprovacao(result.scene.id, covered=["ACC_OUTRO_999"]))

    # Blocker de geometria nunca é declarável: o código não está entre os exigidos.
    with pytest.raises(ValueError, match="critério de escopo"):
        approve_trace(result, _aprovacao(result.scene.id, acknowledged=["MEASUREMENT_MISMATCH"]))
