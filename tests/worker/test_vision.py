import math
from itertools import pairwise
from pathlib import Path
from typing import Literal

import numpy as np
import pytest
from numpy.typing import NDArray
from PIL import Image, ImageDraw

from croquitodxf_worker import vision
from croquitodxf_worker.providers import GeometryElementOutput, NormalizedPoint
from croquitodxf_worker.synthetic import render_synthetic_input
from croquitodxf_worker.vision import (
    ARC_SAMPLES,
    EDGE_MIN_EXTENT_RATIO,
    EDGE_ORTHOGONALITY_TOLERANCE_DEGREES,
    EDGE_SHIFT_EXTENT_RATIO,
    EDGE_SHIFT_MAX_SPAN_RATIO,
    ELEMENT_SHIFT_MAX_SPAN_RATIO,
    GEOMETRY_EXTRACTION_ALGORITHM,
    ElementRegistration,
    PixelCircle,
    PixelGeometryValue,
    PixelLine,
    PixelPoint,
    PixelPolyline,
    VisionConfig,
    VisionProposal,
    VisionProposalSet,
    corroborate_with_ink,
    detect_proposals,
    proposals_from_geometry,
    register_to_ink,
    write_proposal_artifacts,
)
from croquitodxf_worker.vision_eval import run_synthetic_vision_eval


def test_synthetic_vision_eval_passes(tmp_path: Path) -> None:
    report, report_path = run_synthetic_vision_eval(tmp_path)

    assert report.passed is True
    assert report.line_recall >= 0.75
    assert report.circle_recall == 1.0
    assert report.circle_candidate_precision == 1.0
    assert report.unresolved_rate == 1.0
    assert report.non_exportable_rate == 1.0
    assert report_path.is_file()


def test_proposals_are_deterministic_and_non_exportable(tmp_path: Path) -> None:
    image_path = tmp_path / "fixture.png"
    render_synthetic_input(image_path)

    first = detect_proposals(image_path, dataset_id="fixture-v1", page_number=1)
    second = detect_proposals(image_path, dataset_id="fixture-v1", page_number=1)

    assert first == second
    assert first.proposals
    assert all(proposal.precision == "unresolved" for proposal in first.proposals)
    assert all(proposal.export is False for proposal in first.proposals)
    assert first.limit_reached == []


def test_blank_page_is_safe_and_writes_overlay(tmp_path: Path) -> None:
    image_path = tmp_path / "blank.png"
    Image.new("RGB", (900, 700), "white").save(image_path)

    proposals, proposals_path, overlay_path = write_proposal_artifacts(
        image_path,
        tmp_path / "result",
        dataset_id="blank-v1",
        page_number=1,
    )

    assert proposals.proposals == []
    assert proposals.limit_reached == []
    assert proposals_path.is_file()
    assert overlay_path.is_file()


def _element(**overrides: object) -> GeometryElementOutput:
    base: dict[str, object] = {
        "label": "muro norte",
        "kind": "line",
        "vertices": [NormalizedPoint(x=0.1, y=0.2), NormalizedPoint(x=0.9, y=0.2)],
        "evidence": "traço contínuo",
    }
    return GeometryElementOutput.model_validate(base | overrides)


def test_geometry_conversion_keeps_the_observation_non_exportable() -> None:
    """Mudar quem observou não muda o que a observação vale."""
    proposals = proposals_from_geometry([_element()], image_digest="a" * 64, width=1000, height=500)

    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal.precision == "unresolved"
    assert proposal.export is False
    assert proposal.algorithm == GEOMETRY_EXTRACTION_ALGORITHM
    assert isinstance(proposal.geometry, PixelLine)
    assert proposal.geometry.start.x == pytest.approx(100)
    assert proposal.geometry.end.y == pytest.approx(100)


def test_geometry_conversion_carries_label_and_layer() -> None:
    proposals = proposals_from_geometry(
        [_element(layer_hint="MURO")], image_digest="a" * 64, width=100, height=100
    )

    assert proposals[0].label == "muro norte"
    assert proposals[0].layer_hint == "MURO"


def test_unknown_layer_becomes_absent_instead_of_the_literal_word() -> None:
    """`unknown` é ausência de informação; gravá-la como rótulo seria ruído na layer."""
    proposals = proposals_from_geometry([_element()], image_digest="a" * 64, width=100, height=100)

    assert proposals[0].layer_hint is None


def test_open_polyline_survives_conversion_without_being_closed() -> None:
    """Fechar um muro aberto inventaria um polígono que ninguém desenhou."""
    element = _element(
        kind="polyline",
        closed=False,
        vertices=[
            NormalizedPoint(x=0.1, y=0.1),
            NormalizedPoint(x=0.5, y=0.1),
            NormalizedPoint(x=0.5, y=0.6),
        ],
    )

    proposals = proposals_from_geometry([element], image_digest="a" * 64, width=100, height=100)

    assert isinstance(proposals[0].geometry, PixelPolyline)
    assert proposals[0].geometry.closed is False


def test_arc_is_sampled_instead_of_being_promoted_to_a_full_circle() -> None:
    """Sem âncoras a abertura é FABRICADA: meia-volta 0..π, e a proposta declara isso.

    É o contrato anterior ao `geometry-extraction@2.0.0` e continua sendo o caminho de um
    modelo que não enxergou as duas pontas. A flag em falso é o que autoriza o registro a
    reconquistar a orientação varrendo a volta inteira, em vez de lapidar um chute.
    """
    element = _element(
        kind="arc",
        vertices=[],
        center=NormalizedPoint(x=0.5, y=0.5),
        radius=0.2,
    )

    proposals = proposals_from_geometry([element], image_digest="a" * 64, width=200, height=200)

    geometry = proposals[0].geometry
    assert isinstance(geometry, PixelPolyline)
    assert geometry.closed is False
    assert proposals[0].kind == "contour"
    assert proposals[0].arc_angles_observed is False
    assert (geometry.points[0].x, geometry.points[0].y) == pytest.approx((140.0, 100.0))
    assert (geometry.points[-1].x, geometry.points[-1].y) == pytest.approx((60.0, 100.0))


def _anchored_arc(**overrides: object) -> GeometryElementOutput:
    """Arco do contrato @2.0.0 sobre uma página 200x200: meia-lua aberta para baixo."""
    base: dict[str, object] = {
        "kind": "arc",
        "vertices": [],
        "center": NormalizedPoint(x=0.5, y=0.5),
        "radius": 0.2,
        "arc_start": NormalizedPoint(x=0.3, y=0.5),
        "arc_mid": NormalizedPoint(x=0.5, y=0.3),
        "arc_end": NormalizedPoint(x=0.7, y=0.5),
    }
    return _element(**(base | overrides))


def test_arc_anchors_replace_the_fabricated_half_turn() -> None:
    """As pontas saem onde a tinta foi vista, e a amostra passa pelo lado do ponto do meio.

    O `arc_mid` é o que resolve arco maior contra arco menor: as duas pontas sozinhas admitem os
    dois sentidos, e escolher um deles por convenção seria inventar metade da observação.
    """
    proposals = proposals_from_geometry(
        [_anchored_arc()], image_digest="a" * 64, width=200, height=200
    )

    proposal = proposals[0]
    geometry = proposal.geometry
    assert isinstance(geometry, PixelPolyline)
    assert geometry.closed is False
    assert proposal.arc_angles_observed is True
    assert (geometry.points[0].x, geometry.points[0].y) == pytest.approx((60.0, 100.0))
    assert (geometry.points[-1].x, geometry.points[-1].y) == pytest.approx((140.0, 100.0))
    # Passa por cima (o lado do `arc_mid`), não por baixo: é o sentido observado.
    assert all(point.y <= 100.0 + 1e-6 for point in geometry.points)
    # Nenhuma amostra cai exatamente no topo (24 pontos não incluem o meio do intervalo),
    # mas a mais alta encosta no raio: a curva sobe até onde o `arc_mid` apontou.
    assert min(point.y for point in geometry.points) == pytest.approx(60.0, abs=0.5)


def test_arc_without_centre_derives_the_circumcircle_from_its_anchors() -> None:
    """Medido na eval real: Opus reportou só as âncoras das meias-luas do Guaxindiba.

    Três pontos determinam o círculo; o centro e o raio saem do circuncírculo em pixels e
    a curva amostrada tem que pousar exatamente onde pousaria com o par declarado."""
    element = _anchored_arc(center=None, radius=None)

    proposals = proposals_from_geometry([element], image_digest="a" * 64, width=200, height=200)

    assert len(proposals) == 1
    proposal = proposals[0]
    geometry = proposal.geometry
    assert isinstance(geometry, PixelPolyline)
    assert proposal.arc_angles_observed is True
    # As âncoras do helper estão sobre o círculo (100,100)-r40: o circuncírculo é ele.
    assert (geometry.points[0].x, geometry.points[0].y) == pytest.approx((60.0, 100.0))
    assert (geometry.points[-1].x, geometry.points[-1].y) == pytest.approx((140.0, 100.0))
    for sample in geometry.points:
        assert math.dist((sample.x, sample.y), (100.0, 100.0)) == pytest.approx(40.0, abs=1e-6)


def test_arc_with_collinear_anchors_and_no_centre_is_skipped() -> None:
    """Colineares não determinam círculo; sem par observado, fabricar seria tinta inventada."""
    element = _anchored_arc(
        center=None,
        radius=None,
        arc_start=NormalizedPoint(x=0.2, y=0.5),
        arc_mid=NormalizedPoint(x=0.5, y=0.5),
        arc_end=NormalizedPoint(x=0.8, y=0.5),
    )

    proposals = proposals_from_geometry([element], image_digest="a" * 64, width=200, height=200)

    assert proposals == []


def test_arc_window_is_measured_in_pixels_and_not_in_the_normalised_space() -> None:
    """Página não quadrada: o espaço normalizado é anisotrópico e torce todo ângulo.

    Com 400x100, dividir x pela largura e y pela altura encolhe o eixo horizontal quatro
    vezes mais que o vertical. Um ângulo tirado dali poria as pontas do arco longe da tinta
    que o modelo apontou; medir em pixels é o que mantém a ponta onde ela foi vista.
    """
    start_px, mid_px, end_px = (182.68, 40.0), (200.0, 30.0), (217.32, 60.0)
    element = _anchored_arc(
        arc_start=NormalizedPoint(x=start_px[0] / 400, y=start_px[1] / 100),
        arc_mid=NormalizedPoint(x=mid_px[0] / 400, y=mid_px[1] / 100),
        arc_end=NormalizedPoint(x=end_px[0] / 400, y=end_px[1] / 100),
    )

    proposals = proposals_from_geometry([element], image_digest="a" * 64, width=400, height=100)

    geometry = proposals[0].geometry
    assert isinstance(geometry, PixelPolyline)
    assert proposals[0].arc_angles_observed is True
    assert math.dist((geometry.points[0].x, geometry.points[0].y), start_px) < 1.0
    assert math.dist((geometry.points[-1].x, geometry.points[-1].y), end_px) < 1.0
    # A amostra não cai exatamente sobre o `arc_mid`, mas passa rente a ele — a folga é o
    # espaçamento de `ARC_SAMPLES`, não erro de projeção.
    assert min(math.dist((point.x, point.y), mid_px) for point in geometry.points) < 2.0


@pytest.mark.parametrize(
    ("case", "overrides"),
    [
        (
            "varredura menor que o passo da busca",
            {
                "arc_start": NormalizedPoint(x=0.7, y=0.5),
                "arc_mid": NormalizedPoint(x=0.6999, y=0.507),
                "arc_end": NormalizedPoint(x=0.6995, y=0.514),
            },
        ),
        ("âncora sobre o centro", {"arc_mid": NormalizedPoint(x=0.5, y=0.5)}),
    ],
)
def test_degenerate_arc_anchors_fall_back_to_the_fabricated_window(
    case: str, overrides: dict[str, object]
) -> None:
    """Âncora degenerada não é observação: vira o chute declarado, não um toco de arco.

    Três pontos dentro da espessura do traço, ou um deles sobre o próprio centro, não
    descrevem abertura nenhuma. Usá-los assim mesmo produziria uma forma que ninguém
    desenhou — e, pior, marcada como observada, o que travaria o registro em ±15°.
    """
    proposals = proposals_from_geometry(
        [_anchored_arc(**overrides)], image_digest="a" * 64, width=200, height=200
    )

    proposal = proposals[0]
    geometry = proposal.geometry
    assert isinstance(geometry, PixelPolyline)
    assert proposal.arc_angles_observed is False, case
    assert (geometry.points[0].x, geometry.points[0].y) == pytest.approx((140.0, 100.0))
    assert (geometry.points[-1].x, geometry.points[-1].y) == pytest.approx((60.0, 100.0))


def test_ink_corroboration_separates_drawn_geometry_from_invention(tmp_path: Path) -> None:
    """A defesa determinística contra alucinação: papel sem tinta reprova o elemento."""
    source = tmp_path / "entrada.png"
    render_synthetic_input(source)
    with Image.open(source) as image:
        width, height = image.size
    drawn = detect_proposals(source, dataset_id="fixture", page_number=1).proposals[0]
    invented = _element(
        label="muro que não existe",
        kind="line",
        vertices=[NormalizedPoint(x=0.02, y=0.97), NormalizedPoint(x=0.30, y=0.97)],
    )
    candidates = [
        drawn,
        *proposals_from_geometry([invented], image_digest="a" * 64, width=width, height=height),
    ]

    corroborated, notes = corroborate_with_ink(candidates, source)

    assert corroborated[0].quality_score > 0.6
    assert corroborated[1].quality_score < 0.6
    assert "INK_NOT_FOUND:muro que não existe" in notes
    # Rebaixa, não descarta: esconder a invenção seria pior do que mostrá-la ao revisor.
    assert len(corroborated) == len(candidates)


def test_ink_corroboration_keeps_the_proposal_identity_stable(tmp_path: Path) -> None:
    """O id deriva da geometria; conferir não pode deslocar nada a jusante."""
    source = tmp_path / "entrada.png"
    render_synthetic_input(source)
    proposals = detect_proposals(source, dataset_id="fixture", page_number=1).proposals[:3]

    corroborated, _notes = corroborate_with_ink(proposals, source)

    assert [item.id for item in corroborated] == [item.id for item in proposals]


def test_registration_recovers_a_systematic_offset(tmp_path: Path) -> None:
    """Modelo de visão acerta a estrutura e erra o enquadramento; isso é corrigível."""
    source = tmp_path / "entrada.png"
    render_synthetic_input(source)
    drawn = detect_proposals(source, dataset_id="fixture", page_number=1).proposals[:6]
    displaced = [
        item.model_copy(
            update={
                "geometry": PixelLine(
                    start=PixelPoint(x=item.geometry.start.x + 40, y=item.geometry.start.y + 60),
                    end=PixelPoint(x=item.geometry.end.x + 40, y=item.geometry.end.y + 60),
                )
            }
        )
        for item in drawn
        if isinstance(item.geometry, PixelLine)
    ]

    registered, registration = register_to_ink(displaced, source)

    assert registration.coverage_after > registration.coverage_before
    assert registration.moved is True
    corroborated, _notes = corroborate_with_ink(registered, source)
    assert sum(1 for item in corroborated if item.quality_score >= 0.6) > 0


def test_registration_moves_the_whole_set_and_never_reshapes_one_element(
    tmp_path: Path,
) -> None:
    """Uma transformação só para todos: corrige enquadramento sem poder inventar forma."""
    source = tmp_path / "entrada.png"
    render_synthetic_input(source)
    original = [
        item
        for item in detect_proposals(source, dataset_id="fixture", page_number=1).proposals
        if isinstance(item.geometry, PixelLine)
    ][:4]

    registered, registration = register_to_ink(original, source)

    for before, after in zip(original, registered, strict=True):
        assert isinstance(before.geometry, PixelLine)
        assert isinstance(after.geometry, PixelLine)
        length_before = math.hypot(
            before.geometry.end.x - before.geometry.start.x,
            before.geometry.end.y - before.geometry.start.y,
        )
        length_after = math.hypot(
            after.geometry.end.x - after.geometry.start.x,
            after.geometry.end.y - after.geometry.start.y,
        )
        # Comprimento só muda pela escala global, idêntica para todos os elementos.
        expected = length_before * (registration.scale_x + registration.scale_y) / 2
        assert length_after == pytest.approx(expected, rel=0.15)


def test_registration_on_an_empty_set_is_a_no_op(tmp_path: Path) -> None:
    source = tmp_path / "entrada.png"
    render_synthetic_input(source)

    registered, registration = register_to_ink([], source)

    assert registered == []
    assert registration.scale_x == 1.0
    assert registration.moved is False


def test_registration_recovers_a_quarter_turn(tmp_path: Path) -> None:
    """Um modelo descreve a planta na orientação em que a lê; o croqui pode estar deitado."""
    source = tmp_path / "entrada.png"
    render_synthetic_input(source)
    drawn = [
        item
        for item in detect_proposals(source, dataset_id="fixture", page_number=1).proposals
        if isinstance(item.geometry, PixelLine)
    ][:6]
    lines = [item.geometry for item in drawn if isinstance(item.geometry, PixelLine)]
    centre_x = sum((item.start.x + item.end.x) / 2 for item in lines) / len(lines)
    centre_y = sum((item.start.y + item.end.y) / 2 for item in lines) / len(lines)

    def turned(x: float, y: float) -> PixelPoint:
        return PixelPoint(
            x=max(0.0, centre_x - (y - centre_y)), y=max(0.0, centre_y + (x - centre_x))
        )

    rotated = [
        item.model_copy(
            update={
                "geometry": PixelLine(
                    start=turned(line.start.x, line.start.y),
                    end=turned(line.end.x, line.end.y),
                )
            }
        )
        for item, line in zip(drawn, lines, strict=True)
    ]

    _registered, registration = register_to_ink(rotated, source)

    assert registration.rotation_degrees in {90, 270}
    assert registration.coverage_after > registration.coverage_before


SHEET_SIZE = (2400, 1800)
RECTANGLE = (300, 300, 2100, 1500)
CIRCLE_CENTRE = (1200.0, 900.0)
CIRCLE_RADIUS = 260.0
ARC_CENTRE = (700.0, 1560.0)
ARC_RADIUS = 180.0
ISOLATED_LINE = ((1300.0, 1700.0), (2100.0, 1700.0))

RECTANGLE_ID = "vp_" + "a" * 16
CIRCLE_ID = "vp_" + "b" * 16
ARC_ID = "vp_" + "c" * 16
LINE_ID = "vp_" + "d" * 16


def _render_curved_fixture(path: Path) -> None:
    """Folha sintética com retângulo, círculo, arco e uma linha isolada.

    `render_synthetic_input` não desenha arco, e sem arco não há como provar que o refino
    reajusta raio contra a tinta em vez de apenas empurrar a forma para o lado.
    """
    image = Image.new("RGB", SHEET_SIZE, "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle(RECTANGLE, outline="black", width=6)
    draw.ellipse(
        (
            CIRCLE_CENTRE[0] - CIRCLE_RADIUS,
            CIRCLE_CENTRE[1] - CIRCLE_RADIUS,
            CIRCLE_CENTRE[0] + CIRCLE_RADIUS,
            CIRCLE_CENTRE[1] + CIRCLE_RADIUS,
        ),
        outline="black",
        width=6,
    )
    draw.arc(
        (
            ARC_CENTRE[0] - ARC_RADIUS,
            ARC_CENTRE[1] - ARC_RADIUS,
            ARC_CENTRE[0] + ARC_RADIUS,
            ARC_CENTRE[1] + ARC_RADIUS,
        ),
        0,
        180,
        fill="black",
        width=6,
    )
    draw.line(ISOLATED_LINE, fill="black", width=6)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG")


def _proposal(
    identifier: str,
    geometry: PixelGeometryValue,
    label: str,
    *,
    arc_angles_observed: bool = False,
) -> VisionProposal:
    kind: Literal["line", "circle", "contour"]
    if isinstance(geometry, PixelCircle):
        kind = "circle"
    elif isinstance(geometry, PixelLine):
        kind = "line"
    else:
        kind = "contour"
    return VisionProposal(
        id=identifier,
        kind=kind,
        geometry=geometry,
        algorithm=GEOMETRY_EXTRACTION_ALGORITHM,
        quality_score=0.0,
        label=label,
        arc_angles_observed=arc_angles_observed,
    )


def _rectangle_polyline(shift_x: float = 0.0, shift_y: float = 0.0) -> PixelPolyline:
    left, top, right, bottom = RECTANGLE
    corners = ((left, top), (right, top), (right, bottom), (left, bottom))
    return PixelPolyline(
        points=[PixelPoint(x=x + shift_x, y=y + shift_y) for x, y in corners],
        closed=True,
    )


def _arc_polyline(
    centre: tuple[float, float], radius: float, orientation_degrees: float = 0.0
) -> PixelPolyline:
    """Mesma amostragem que `proposals_from_geometry` aplica a um arco do contrato.

    `orientation_degrees` gira a janela angular. Com 0 sai a meia-volta 0..π que a conversão
    fabrica quando o arco vem sem âncoras — a mesma que aponta para o lado errado no croqui
    real. Quem simula um arco OBSERVADO passa `arc_angles_observed=True` na proposta: a
    forma é a mesma, o que muda é o quanto o registro pode girá-la.
    """
    offset = math.radians(orientation_degrees)
    return PixelPolyline(
        points=[
            PixelPoint(
                x=centre[0] + radius * math.cos(offset + step * math.pi / (ARC_SAMPLES - 1)),
                y=centre[1] + radius * math.sin(offset + step * math.pi / (ARC_SAMPLES - 1)),
            )
            for step in range(ARC_SAMPLES)
        ],
        closed=False,
    )


def _isolated_line(shift_x: float = 0.0, shift_y: float = 0.0) -> PixelLine:
    start, end = ISOLATED_LINE
    return PixelLine(
        start=PixelPoint(x=start[0] + shift_x, y=start[1] + shift_y),
        end=PixelPoint(x=end[0] + shift_x, y=end[1] + shift_y),
    )


def _element_report(
    elements: tuple[ElementRegistration, ...], identifier: str
) -> ElementRegistration:
    return next(item for item in elements if item.proposal_id == identifier)


def test_registration_refits_a_circle_with_the_wrong_centre_and_radius(tmp_path: Path) -> None:
    """Empurrar um círculo de raio errado nunca o assenta; só o re-fit do raio resolve."""
    source = tmp_path / "curvas.png"
    _render_curved_fixture(source)
    proposals = [
        _proposal(RECTANGLE_ID, _rectangle_polyline(), "retângulo"),
        _proposal(ARC_ID, _arc_polyline(ARC_CENTRE, ARC_RADIUS), "meia-lua"),
        _proposal(LINE_ID, _isolated_line(), "linha isolada"),
        _proposal(
            CIRCLE_ID,
            PixelCircle(
                center=PixelPoint(x=CIRCLE_CENTRE[0] + 9, y=CIRCLE_CENTRE[1] - 8),
                radius=CIRCLE_RADIUS * 1.12,
            ),
            "círculo",
        ),
    ]

    registered, registration = register_to_ink(proposals, source)

    report = _element_report(registration.elements, CIRCLE_ID)
    assert report.refinement == "circle"
    # Raio 31 px maior que o traço: nenhuma amostra caía sobre tinta antes do re-fit.
    assert report.coverage_raw == 0.0
    assert report.coverage_refined > report.coverage_global
    circle = registered[3].geometry
    assert isinstance(circle, PixelCircle)
    assert circle.radius == pytest.approx(CIRCLE_RADIUS, abs=20)
    assert math.dist((circle.center.x, circle.center.y), CIRCLE_CENTRE) < 20
    assert [item.id for item in registered] == [item.id for item in proposals]


def test_registration_refits_an_arc_onto_its_own_circle(tmp_path: Path) -> None:
    """Arco com centro e raio errados volta para o traço sem virar círculo inteiro."""
    source = tmp_path / "curvas.png"
    _render_curved_fixture(source)
    proposals = [
        _proposal(RECTANGLE_ID, _rectangle_polyline(), "retângulo"),
        _proposal(
            CIRCLE_ID,
            PixelCircle(
                center=PixelPoint(x=CIRCLE_CENTRE[0], y=CIRCLE_CENTRE[1]), radius=CIRCLE_RADIUS
            ),
            "círculo",
        ),
        _proposal(LINE_ID, _isolated_line(), "linha isolada"),
        _proposal(
            ARC_ID,
            _arc_polyline((ARC_CENTRE[0] + 8, ARC_CENTRE[1] + 7), ARC_RADIUS * 1.12),
            "meia-lua",
        ),
    ]

    registered, registration = register_to_ink(proposals, source)

    report = _element_report(registration.elements, ARC_ID)
    assert report.refinement == "arc"
    assert report.coverage_raw == 0.0
    assert report.coverage_refined > report.coverage_global
    arc = registered[3].geometry
    assert isinstance(arc, PixelPolyline)
    # Continua aberto e com a mesma contagem de vértices: re-amostrar não pode fechar a
    # forma nem inflar a lista de pontos.
    assert arc.closed is False
    assert len(arc.points) == ARC_SAMPLES
    distances = [math.dist((point.x, point.y), ARC_CENTRE) for point in arc.points]
    assert max(distances) < ARC_RADIUS + 20
    assert min(distances) > ARC_RADIUS - 20
    assert [item.id for item in registered] == [item.id for item in proposals]


def test_registration_turns_an_arc_that_points_the_wrong_way(tmp_path: Path) -> None:
    """Orientação FABRICADA na conversão não é observação — logo é ajustável sem limite.

    É o caso do arco sem âncoras: `arc_angles_observed` em falso, porque o modelo omitiu as
    três (ou respondeu sob o contrato anterior ao `geometry-extraction@2.0.0`) e
    `proposals_from_geometry` amostrou a meia-volta 0..π. No Guaxindiba isso pôs as duas
    meias-luas giradas um quarto de volta em relação à tinta. Preservar esse valor seria
    preservar um chute; o que continua preservado é a extensão angular.
    """
    source = tmp_path / "curvas.png"
    _render_curved_fixture(source)
    proposals = [
        _proposal(RECTANGLE_ID, _rectangle_polyline(), "retângulo"),
        _proposal(
            CIRCLE_ID,
            PixelCircle(
                center=PixelPoint(x=CIRCLE_CENTRE[0], y=CIRCLE_CENTRE[1]), radius=CIRCLE_RADIUS
            ),
            "círculo",
        ),
        _proposal(LINE_ID, _isolated_line(), "linha isolada"),
        # A tinta desenha a metade de baixo; a proposta aponta para a direita.
        _proposal(ARC_ID, _arc_polyline(ARC_CENTRE, ARC_RADIUS, -90.0), "meia-lua girada"),
    ]

    registered, registration = register_to_ink(proposals, source)

    report = _element_report(registration.elements, ARC_ID)
    assert report.refinement == "arc"
    assert report.orientation_delta_degrees == pytest.approx(90.0, abs=15.0)
    assert report.coverage_refined >= 0.9
    arc = registered[3].geometry
    assert isinstance(arc, PixelPolyline)
    assert arc.closed is False
    # Extensão angular e contagem de vértices preservadas: só a orientação mudou.
    assert len(arc.points) == ARC_SAMPLES
    distances = [math.dist((point.x, point.y), ARC_CENTRE) for point in arc.points]
    assert max(distances) < ARC_RADIUS + 20
    assert min(distances) > ARC_RADIUS - 20
    # Metade de baixo: toda a amostra caiu do lado da tinta, não do lado do chute.
    assert all(point.y >= ARC_CENTRE[1] - 20 for point in arc.points)
    assert [item.id for item in registered] == [item.id for item in proposals]


def test_registration_polishes_an_observed_arc_instead_of_reconquering_it(
    tmp_path: Path,
) -> None:
    """Orientação observada nas âncoras é evidência: o refino só a lapida contra a tinta.

    O modelo erra o assentamento e alguns graus de leitura são esperados, então a busca
    continua existindo — mas dentro de ±15°, não na volta inteira.
    """
    source = tmp_path / "curvas.png"
    _render_curved_fixture(source)
    proposals = [
        _proposal(RECTANGLE_ID, _rectangle_polyline(), "retângulo"),
        _proposal(
            CIRCLE_ID,
            PixelCircle(
                center=PixelPoint(x=CIRCLE_CENTRE[0], y=CIRCLE_CENTRE[1]), radius=CIRCLE_RADIUS
            ),
            "círculo",
        ),
        _proposal(LINE_ID, _isolated_line(), "linha isolada"),
        _proposal(
            ARC_ID,
            _arc_polyline(ARC_CENTRE, ARC_RADIUS, 10.0),
            "meia-lua observada torta",
            arc_angles_observed=True,
        ),
    ]

    registered, registration = register_to_ink(proposals, source)

    report = _element_report(registration.elements, ARC_ID)
    assert report.refinement == "arc"
    # Gira de volta para a tinta, e nunca mais que a janela. A correção para em -4° e não
    # em -10° porque a tinta satura antes: com a tolerância do halo, a meia-lua já cobre
    # tudo ali, e empate de cobertura fica com a correção MENOR — a busca não persegue um
    # ângulo que a folha não distingue mais.
    assert -vision.ARC_OBSERVED_ORIENTATION_SPAN_DEGREES <= report.orientation_delta_degrees < 0
    assert report.coverage_refined > report.coverage_global
    assert report.coverage_refined >= 0.9
    arc = registered[3].geometry
    assert isinstance(arc, PixelPolyline)
    assert arc.closed is False
    assert len(arc.points) == ARC_SAMPLES
    # A meia-lua de baixo continua sendo a de baixo: o que mudou foram os 10° de leitura.
    assert all(point.y >= ARC_CENTRE[1] - 20 for point in arc.points)


def test_registration_does_not_turn_an_observed_arc_a_quarter_of_a_turn(
    tmp_path: Path,
) -> None:
    """Espelho do arco fabricado: com âncoras, o quarto de volta deixa de estar ao alcance.

    A tinta desenha a metade de baixo e a observação diz metade da direita. Se a busca
    ainda varresse a volta inteira, ela apagaria a evidência em silêncio e ainda declararia
    um giro de 90° — o relatório passaria a contradizer o que o modelo afirmou ter visto.
    A discordância é do revisor: a proposta fica onde foi observada, com pouca tinta por
    baixo, e a conferência a rebaixa em vez de escondê-la.
    """
    source = tmp_path / "curvas.png"
    _render_curved_fixture(source)

    def registered_arc(*, observed: bool) -> tuple[ElementRegistration, PixelPolyline]:
        proposals = [
            _proposal(RECTANGLE_ID, _rectangle_polyline(), "retângulo"),
            _proposal(
                CIRCLE_ID,
                PixelCircle(
                    center=PixelPoint(x=CIRCLE_CENTRE[0], y=CIRCLE_CENTRE[1]), radius=CIRCLE_RADIUS
                ),
                "círculo",
            ),
            _proposal(LINE_ID, _isolated_line(), "linha isolada"),
            # A tinta desenha a metade de baixo; a proposta aponta para a direita.
            _proposal(
                ARC_ID,
                _arc_polyline(ARC_CENTRE, ARC_RADIUS, -90.0),
                "meia-lua girada",
                arc_angles_observed=observed,
            ),
        ]
        registered, registration = register_to_ink(proposals, source)
        geometry = registered[3].geometry
        assert isinstance(geometry, PixelPolyline)
        return _element_report(registration.elements, ARC_ID), geometry

    observed_report, observed_arc = registered_arc(observed=True)
    fabricated_report, fabricated_arc = registered_arc(observed=False)

    # Fabricada: reconquista o quarto de volta e pousa inteira na metade de baixo.
    assert abs(fabricated_report.orientation_delta_degrees) > 45.0
    assert all(point.y >= ARC_CENTRE[1] - 20 for point in fabricated_arc.points)
    # Observada: o giro não passa da janela e a forma continua apontando para a direita.
    assert (
        abs(observed_report.orientation_delta_degrees)
        <= vision.ARC_OBSERVED_ORIENTATION_SPAN_DEGREES
    )
    assert min(point.y for point in observed_arc.points) < ARC_CENTRE[1] - 20
    # E ela sai com menos tinta do que a reconquistada teria: o desacordo entre observação
    # e folha aparece na conferência, em vez de ser resolvido por conta própria.
    assert observed_report.coverage_refined < fabricated_report.coverage_refined


def test_refinement_window_grows_with_the_element_but_stays_capped(tmp_path: Path) -> None:
    """Janela só da página aperta o elemento grande; janela sem teto o solta na folha."""
    source = tmp_path / "curvas.png"
    _render_curved_fixture(source)
    displacement = 35.0
    span = float(max(SHEET_SIZE))
    # Maior que a fração da página (0,5% = 12 px) e menor que o teto (2% = 48 px):
    # só a janela relativa ao próprio elemento alcança esse deslocamento.
    assert span * 0.005 < displacement < span * ELEMENT_SHIFT_MAX_SPAN_RATIO
    proposals = [
        _proposal(RECTANGLE_ID, _rectangle_polyline(displacement, displacement), "retângulo"),
        _proposal(
            CIRCLE_ID,
            PixelCircle(
                center=PixelPoint(x=CIRCLE_CENTRE[0], y=CIRCLE_CENTRE[1]), radius=CIRCLE_RADIUS
            ),
            "círculo",
        ),
        _proposal(ARC_ID, _arc_polyline(ARC_CENTRE, ARC_RADIUS), "meia-lua"),
        _proposal(LINE_ID, _isolated_line(), "linha isolada"),
    ]

    registered, registration = register_to_ink(proposals, source)

    report = _element_report(registration.elements, RECTANGLE_ID)
    # Contorno fechado de quatro arestas quase-ortogonais entra pelo refino POR ARESTA.
    # Quando o elemento só precisa de empurrão, as quatro arestas concordam e o resultado é
    # o mesmo do empurrão rígido — o que muda é que agora ele é auditável aresta a aresta.
    assert report.refinement == "edges"
    # Todas as arestas voltam na mesma direção e o contorno pousa sobre o traço: quando o
    # elemento só precisa de empurrão, a busca por aresta chega ao mesmo lugar que a rígida.
    assert all(shift <= 0.0 for shift in report.edge_shifts_px)
    rectangle = registered[0].geometry
    assert isinstance(rectangle, PixelPolyline)
    assert (
        min(point.x for point in rectangle.points),
        min(point.y for point in rectangle.points),
        max(point.x for point in rectangle.points),
        max(point.y for point in rectangle.points),
    ) == pytest.approx(RECTANGLE, abs=20.0)
    assert report.coverage_refined >= 0.9
    # Andou mais do que a janela antiga (fração da página) permitia: é a janela relativa
    # ao elemento que comprou essa tinta.
    assert report.centre_shift_px > span * 0.005
    # Teto: nenhum elemento pode escorregar para longe e colher tinta que não é dele.
    ceiling = span * EDGE_SHIFT_MAX_SPAN_RATIO * math.sqrt(2)
    assert all(item.centre_shift_px <= ceiling + 1e-6 for item in registration.elements)
    # Mesma entrada, mesma saída: a busca é em grade fixa, sem nada aleatório.
    repeated, _again = register_to_ink(proposals, source)
    assert [item.geometry for item in repeated] == [item.geometry for item in registered]


def test_registration_never_leaves_an_element_below_its_raw_coverage(tmp_path: Path) -> None:
    """O ótimo agregado sacrifica um elemento já certo; o refino é quem devolve o muro."""
    source = tmp_path / "curvas.png"
    _render_curved_fixture(source)
    proposals = [
        _proposal(RECTANGLE_ID, _rectangle_polyline(70, 55), "retângulo deslocado"),
        _proposal(
            CIRCLE_ID,
            PixelCircle(
                center=PixelPoint(x=CIRCLE_CENTRE[0] + 70, y=CIRCLE_CENTRE[1] + 55),
                radius=CIRCLE_RADIUS,
            ),
            "círculo deslocado",
        ),
        _proposal(
            ARC_ID,
            _arc_polyline((ARC_CENTRE[0] + 70, ARC_CENTRE[1] + 55), ARC_RADIUS),
            "meia-lua deslocada",
        ),
        _proposal(LINE_ID, _isolated_line(), "muro já assentado"),
    ]

    registered, registration = register_to_ink(proposals, source)

    wall = _element_report(registration.elements, LINE_ID)
    # O estágio global de fato piora o elemento bom: é o defeito que o refino corrige.
    assert wall.coverage_global < wall.coverage_raw
    assert wall.base == "raw"
    assert wall.coverage_refined >= wall.coverage_raw
    assert all(item.coverage_refined >= item.coverage_raw for item in registration.elements)
    assert [item.id for item in registered] == [item.id for item in proposals]


def test_registration_corrects_a_sheet_that_entered_slightly_crooked(tmp_path: Path) -> None:
    """Giro de poucos graus não é quarto de volta: sem ângulo fino a ponta nunca fecha."""
    source = tmp_path / "curvas.png"
    _render_curved_fixture(source)
    straight = [
        _proposal(RECTANGLE_ID, _rectangle_polyline(), "retângulo"),
        _proposal(LINE_ID, _isolated_line(), "linha isolada"),
    ]
    angle = math.radians(2.0)
    cosine, sine = math.cos(angle), math.sin(angle)
    pivot = (SHEET_SIZE[0] / 2, SHEET_SIZE[1] / 2)

    def turned(x: float, y: float) -> PixelPoint:
        offset_x, offset_y = x - pivot[0], y - pivot[1]
        return PixelPoint(
            x=pivot[0] + offset_x * cosine - offset_y * sine,
            y=pivot[1] + offset_x * sine + offset_y * cosine,
        )

    rotated = [
        straight[0].model_copy(
            update={
                "geometry": PixelPolyline(
                    points=[turned(point.x, point.y) for point in _rectangle_polyline().points],
                    closed=True,
                )
            }
        ),
        straight[1].model_copy(
            update={
                "geometry": PixelLine(
                    start=turned(*ISOLATED_LINE[0]), end=turned(*ISOLATED_LINE[1])
                )
            }
        ),
    ]

    _registered, registration = register_to_ink(rotated, source)

    assert registration.rotation_degrees == 0
    assert registration.total_rotation_degrees == pytest.approx(-2.0, abs=0.6)
    assert registration.coverage_after > registration.coverage_before


ORDER_SHEET = (3000, 2000)
"""Folha grande o bastante para o teto de 2% dar 60 px de janela ao empurrão."""

NEIGHBOUR_INK_Y = 385.0
"""Tinta do muro vizinho: não pertence a nenhuma das duas propostas do caso."""

WALL_BOX = (200.0, 425.0, 2800.0, 1600.0)
"""Contorno do terreno como o modelo propôs: topo 40 px abaixo da tinta do vizinho."""

FIELD_EDGE_Y = 445.0
"""Aresta superior do campo, 20 px abaixo do topo do contorno — a ordem traçada."""

FIELD_INK_Y = 560.0
"""Tinta do campo, longe demais para a janela alcançar: é o aperto do caso real."""

ORDER_FILLERS = tuple(
    (x, y, x + 200.0, y + 200.0) for y in (120.0, 900.0, 1740.0) for x in (60.0, 2740.0)
)
"""Seis quadrados já assentados, espalhados na folha, que prendem o estágio global.

Sem eles o ajuste global escorrega para acertar o elemento solto, e o caso deixaria de
isolar o que se quer testar: o empurrão POR ELEMENTO.
"""

WALL_ID = "vp_" + "a" * 16
FIELD_ID = "vp_" + "b" * 16


def _render_order_fixture(path: Path, *, wall_ink: tuple[float, float, float, float]) -> None:
    """Topo do Guaxindiba em miniatura: duas paralelas próximas e uma tinta que atrai."""
    image = Image.new("RGB", ORDER_SHEET, "white")
    draw = ImageDraw.Draw(image)
    if wall_ink == WALL_BOX:
        draw.line([(300, NEIGHBOUR_INK_Y), (2700, NEIGHBOUR_INK_Y)], fill="black", width=7)
    left, top, right, bottom = wall_ink
    # Três arestas do contorno têm traço; o topo não tem. É o que prende o contorno no
    # lugar: subir para a tinta do vizinho ganharia o topo e perderia a base.
    draw.line([(left, top), (left, bottom), (right, bottom), (right, top)], fill="black", width=7)
    draw.line([(320, FIELD_INK_Y), (2680, FIELD_INK_Y)], fill="black", width=7)
    for box in ORDER_FILLERS:
        draw.rectangle(box, outline="black", width=7)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG")


def _closed_rectangle(box: tuple[float, float, float, float]) -> PixelPolyline:
    left, top, right, bottom = box
    corners = ((left, top), (right, top), (right, bottom), (left, bottom))
    return PixelPolyline(points=[PixelPoint(x=x, y=y) for x, y in corners], closed=True)


def _order_proposals() -> list[VisionProposal]:
    return [
        _proposal(WALL_ID, _closed_rectangle(WALL_BOX), "contorno do terreno"),
        _proposal(
            FIELD_ID,
            PixelLine(
                start=PixelPoint(x=320, y=FIELD_EDGE_Y), end=PixelPoint(x=2680, y=FIELD_EDGE_Y)
            ),
            "aresta superior do campo",
        ),
        *[
            _proposal(
                "vp_" + "0123456789abcdef"[index] * 16, _closed_rectangle(box), f"apoio {index}"
            )
            for index, box in enumerate(ORDER_FILLERS)
        ],
    ]


def _top_of(geometry: PixelGeometryValue) -> float:
    if isinstance(geometry, PixelLine):
        return min(geometry.start.y, geometry.end.y)
    if isinstance(geometry, PixelCircle):
        return geometry.center.y - geometry.radius
    return min(point.y for point in geometry.points)


def _without_order_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    """Desliga a lei da ordem para o mesmo caso provar o defeito que ela existe para impedir."""
    monkeypatch.setattr(
        vision,
        "_order_guard",
        lambda reference, barriers, **_kwargs: vision._OrderGuard(
            limits=tuple((-math.inf, math.inf) for _ in reference)
        ),
    )


def test_refinement_refuses_a_push_that_would_cross_a_parallel_neighbour(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O empurrão não atravessa vizinho paralelo para colher a tinta dele.

    Reprodução mínima do topo do Guaxindiba: a aresta do campo tem a tinta do muro vizinho
    ao alcance da janela e a própria fora dela. Sem a lei ela sobe, pousa na tinta que não é
    dela e termina ACIMA do contorno do terreno — ordem invertida, e o solver, que honra o
    lado do traçado, exporta o campo do lado errado do muro.

    Com o refino por aresta o contorno do terreno deixa de ficar parado: o topo dele é a
    única aresta que a folha não desenha, e uma aresta sem tinta própria adota a paralela
    mais próxima da janela — aqui a linha do campo, 119 px abaixo. A lei continua fazendo o
    trabalho dela, que é o lado: o campo termina ABAIXO do contorno, na própria tinta, e não
    na do vizinho. O deslocamento dessa aresta órfã é limitação declarada do estágio, não
    invariante quebrada.
    """
    source = tmp_path / "ordem.png"
    _render_order_fixture(source, wall_ink=WALL_BOX)
    proposals = _order_proposals()

    _without_order_guard(monkeypatch)
    unguarded, _report = register_to_ink(proposals, source)
    monkeypatch.undo()

    wall_before = _top_of(unguarded[0].geometry)
    field_before = _top_of(unguarded[1].geometry)
    # O defeito: o campo subiu para a tinta do vizinho e passou por cima do contorno.
    assert field_before == pytest.approx(NEIGHBOUR_INK_Y, abs=20.0)
    assert field_before < wall_before

    registered, registration = register_to_ink(proposals, source)

    wall = _element_report(registration.elements, WALL_ID)
    field = _element_report(registration.elements, FIELD_ID)
    assert _top_of(registered[1].geometry) > _top_of(registered[0].geometry)
    # A tinta do vizinho continua sendo a que o campo NÃO pode colher: ele foi para a dele.
    assert _top_of(registered[1].geometry) == pytest.approx(FIELD_INK_Y, abs=20.0)
    assert _top_of(registered[1].geometry) > NEIGHBOUR_INK_Y + 100.0
    assert field.coverage_refined >= field.coverage_raw
    assert wall.coverage_refined >= wall.coverage_raw
    assert all(item.coverage_refined >= item.coverage_raw for item in registration.elements)
    assert all(item.order_unresolved is False for item in registration.elements)

    repeated, _again = register_to_ink(proposals, source)
    assert [item.geometry for item in repeated] == [item.geometry for item in registered]


def test_refinement_returns_an_element_whose_base_already_crossed_a_neighbour(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Quando o vizinho assentado passa por cima da base, o elemento volta para o corredor.

    A colocação de base também é decisão do refino — e no Guaxindiba real ela é o que
    trocou as linhas de tinta, porque bruto e pós-global estão a ~700 px um do outro. Aqui o
    contorno desce para a própria tinta e passa a aresta do campo; deixar o campo na base
    manteria a inversão, então ele é devolvido ao corredor.

    O contorno desce por duas arestas agora, e não como bloco: a base dele vai até a tinta e
    o topo, que a folha não desenha, adota a linha do campo. O que este caso mede não muda —
    o campo é obrigado a sair de cima do vizinho e a declaração `order_constrained` diz que
    quem mandou foi a ordem, não a tinta.
    """
    source = tmp_path / "ordem-base.png"
    lowered = (WALL_BOX[0], WALL_BOX[1] + 45.0, WALL_BOX[2], WALL_BOX[3] + 45.0)
    _render_order_fixture(source, wall_ink=lowered)
    proposals = _order_proposals()

    _without_order_guard(monkeypatch)
    unguarded, _report = register_to_ink(proposals, source)
    monkeypatch.undo()
    assert _top_of(unguarded[1].geometry) < _top_of(unguarded[0].geometry)

    registered, registration = register_to_ink(proposals, source)

    field = _element_report(registration.elements, FIELD_ID)
    assert field.order_constrained is True
    assert field.order_unresolved is False
    # O empurrão é o que a ordem exigiu, e continua declarado em `centre_shift_px` mesmo
    # quando o segundo passo da linha (as pontas) ajusta a extensão depois dele.
    assert field.refinement in {"translation", "tips"}
    assert field.centre_shift_px > 0.0
    assert _top_of(registered[1].geometry) > _top_of(registered[0].geometry)
    # O campo não é solto na folha: ele para na primeira posição que respeita o corredor, e
    # essa posição é a tinta dele — não a do vizinho, 170 px acima.
    assert _top_of(registered[1].geometry) == pytest.approx(FIELD_INK_Y, abs=20.0)
    assert all(item.coverage_refined >= item.coverage_raw for item in registration.elements)


SIZE_SHEET = (3000, 2400)
"""Folha em que o teto por aresta (5% = 150 px) alcança o erro e o rígido (2% = 60 px) não."""

FIELD_INK_BOX = (300.0, 300.0, 2700.0, 1400.0)
"""Tinta do campo. A base dela é onde o patamar encosta: é esse encontro que amarra o traçado."""

TERRACE_BOX = (300.0, 1400.0, 2700.0, 1900.0)
"""Patamar desenhado encostado na base do campo, como no Guaxindiba."""

FIELD_SIZE_ERROR = 130.0
"""Quanto o modelo esticou o campo para baixo: maior que o teto do empurrão rígido.

É a assinatura do defeito real — no Guaxindiba o campo saiu 285 px mais alto que a tinta,
com teto rígido de 134 px. Aqui a proporção é a mesma em miniatura.
"""

ORPHAN_INK = ((2000.0, 2050.0), (1200.0, 2050.0), (1200.0, 2300.0), (2000.0, 2300.0))
"""Caixa cuja aresta DIREITA a folha não desenha: três traços e um lado aberto."""

ORPHAN_BOX = (1170.0, 2020.0, 1970.0, 2270.0)
"""A mesma caixa como o modelo propôs: 30 px acima e à esquerda da tinta."""

SIZE_FILLERS = (
    (100.0, 100.0, 250.0, 250.0),
    (2750.0, 100.0, 250.0 + 2650.0, 250.0),
    (100.0, 2150.0, 250.0, 2300.0),
    (2750.0, 2150.0, 2900.0, 2300.0),
)
"""Apoios já assentados que prendem o estágio global, como em `ORDER_FILLERS`."""

TERRACE_ID = "vp_" + "e" * 16
ORPHAN_ID = "vp_" + "f" * 16


def _render_size_fixture(path: Path) -> None:
    """Campo com a base esticada para dentro do patamar, mais uma caixa de lado aberto."""
    image = Image.new("RGB", SIZE_SHEET, "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle(FIELD_INK_BOX, outline="black", width=7)
    draw.rectangle(TERRACE_BOX, outline="black", width=7)
    draw.line(list(ORPHAN_INK), fill="black", width=7)
    for box in SIZE_FILLERS:
        draw.rectangle(box, outline="black", width=7)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG")


def _size_proposals() -> list[VisionProposal]:
    left, top, right, bottom = FIELD_INK_BOX
    stretched = (left, top, right, bottom + FIELD_SIZE_ERROR)
    return [
        _proposal(RECTANGLE_ID, _closed_rectangle(stretched), "campo esticado"),
        _proposal(TERRACE_ID, _closed_rectangle(TERRACE_BOX), "patamar já certo"),
        _proposal(ORPHAN_ID, _closed_rectangle(ORPHAN_BOX), "caixa de lado aberto"),
        *[
            _proposal("vp_" + "0123456789ab"[index] * 16, _closed_rectangle(box), f"apoio {index}")
            for index, box in enumerate(SIZE_FILLERS)
        ],
    ]


def _bottom_of(geometry: PixelGeometryValue) -> float:
    if isinstance(geometry, PixelLine):
        return max(geometry.start.y, geometry.end.y)
    if isinstance(geometry, PixelCircle):
        return geometry.center.y + geometry.radius
    return max(point.y for point in geometry.points)


def _without_edge_refinement(monkeypatch: pytest.MonkeyPatch) -> None:
    """Desliga o refino por aresta para o mesmo caso mostrar o que o empurrão rígido dava."""
    monkeypatch.setattr(vision, "_rectangular_edges", lambda _geometry: None)


def test_edge_refinement_corrects_a_contour_stretched_past_its_ink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O modelo erra TAMANHO, e empurrão rígido não conserta erro de tamanho.

    Assinatura do campo do Guaxindiba: o topo do contorno está na tinta certa e a base saiu
    esticada para dentro do patamar. Empurrar o elemento inteiro só troca qual das duas
    arestas fica errada — o que a folha pede é que cada uma vá para a própria tinta. Com o
    encontro campo/patamar desfeito o traçado perde a junção que amarra os dois elementos.
    """
    source = tmp_path / "tamanho.png"
    _render_size_fixture(source)
    proposals = _size_proposals()
    terrace_top = TERRACE_BOX[1]

    _without_edge_refinement(monkeypatch)
    rigid, _report = register_to_ink(proposals, source)
    monkeypatch.undo()
    # O antes: só com empurrão rígido a base fica longe demais do patamar para o traçado
    # reconhecer o encontro, e é isso que este refino existe para curar.
    assert _bottom_of(rigid[0].geometry) - terrace_top > 100.0

    registered, registration = register_to_ink(proposals, source)

    report = _element_report(registration.elements, RECTANGLE_ID)
    assert report.refinement == "edges"
    # Topo continua na tinta dele; a base é que sobe. A altura corrige sem girar nada.
    assert report.edge_shifts_px[0] == pytest.approx(0.0, abs=10.0)
    assert report.edge_shifts_px[1] < -FIELD_SIZE_ERROR / 2
    assert _bottom_of(registered[0].geometry) - terrace_top < 25.0
    # A ordem com o vizinho de baixo sobrevive: a base do campo não entra no patamar.
    assert _bottom_of(registered[0].geometry) > _top_of(registered[1].geometry)
    assert all(item.coverage_refined >= item.coverage_raw for item in registration.elements)
    assert all(item.order_unresolved is False for item in registration.elements)
    assert report.coverage_refined > report.coverage_global
    # Mesma entrada, mesma saída: a busca é em grade fixa, sem nada aleatório.
    repeated, _again = register_to_ink(proposals, source)
    assert [item.geometry for item in repeated] == [item.geometry for item in registered]


def test_edge_refinement_leaves_a_contour_that_is_already_right(tmp_path: Path) -> None:
    """Nunca-piora por aresta: sem tinta melhor, a aresta não anda um pixel."""
    source = tmp_path / "tamanho.png"
    _render_size_fixture(source)

    _registered, registration = register_to_ink(_size_proposals(), source)

    report = _element_report(registration.elements, TERRACE_ID)
    assert report.refinement == "none"
    assert report.edge_shifts_px == (0.0, 0.0, 0.0, 0.0)
    assert report.centre_shift_px == 0.0


def test_edge_without_ink_of_its_own_stays_while_the_others_correct(tmp_path: Path) -> None:
    """Lado que a folha não desenhou não é inventado: ele fica, e os três com traço corrigem."""
    source = tmp_path / "tamanho.png"
    _render_size_fixture(source)

    registered, registration = register_to_ink(_size_proposals(), source)

    report = _element_report(registration.elements, ORPHAN_ID)
    assert report.refinement == "edges"
    top, bottom, left, right = report.edge_shifts_px
    # Os três lados desenhados andam na direção da própria tinta, 30 px acima e à esquerda.
    # Param antes dos 30 porque a tinta tem espessura: alcançada a cobertura cheia, o
    # desempate por correção mínima não paga para andar mais.
    assert all(0.0 < shift <= 30.0 for shift in (top, bottom, left))
    # A aresta órfã não tem tinta própria na janela e não sai do lugar.
    assert right == 0.0
    orphan = registered[2].geometry
    assert isinstance(orphan, PixelPolyline)
    assert len(orphan.points) == 4
    assert orphan.closed is True
    assert max(point.x for point in orphan.points) == pytest.approx(ORPHAN_BOX[2], abs=1e-6)


def test_edge_refinement_keeps_the_contour_orthogonal_and_closed(tmp_path: Path) -> None:
    """Deslocar uma aresta translada a reta suporte; ela não gira, e o contorno não abre."""
    source = tmp_path / "tamanho.png"
    _render_size_fixture(source)

    registered, _registration = register_to_ink(_size_proposals(), source)

    before = _size_proposals()[0].geometry
    after = registered[0].geometry
    assert isinstance(before, PixelPolyline)
    assert isinstance(after, PixelPolyline)
    assert after.closed is True
    assert len(after.points) == len(before.points)
    for index in range(4):
        start, end = before.points[index], before.points[(index + 1) % 4]
        moved_start, moved_end = after.points[index], after.points[(index + 1) % 4]
        original = math.atan2(end.y - start.y, end.x - start.x)
        refined = math.atan2(moved_end.y - moved_start.y, moved_end.x - moved_start.x)
        assert refined == pytest.approx(original, abs=1e-9)


def test_edge_refinement_is_declined_when_the_contour_is_not_rectangular(tmp_path: Path) -> None:
    """Contorno que a regularização não chamaria de retângulo segue no empurrão rígido."""
    source = tmp_path / "tamanho.png"
    _render_size_fixture(source)
    left, top, right, bottom = FIELD_INK_BOX
    skewed = PixelPolyline(
        points=[
            PixelPoint(x=left, y=top),
            # Aresta a 45°: fora da tolerância angular, e nenhuma diagonal desenhada à mão
            # deve ser endireitada por um deslocamento perpendicular.
            PixelPoint(x=right, y=top + (right - left)),
            PixelPoint(x=right, y=bottom + FIELD_SIZE_ERROR),
            PixelPoint(x=left, y=bottom),
        ],
        closed=True,
    )
    proposals = [_proposal(RECTANGLE_ID, skewed, "contorno torto"), *_size_proposals()[1:]]

    _registered, registration = register_to_ink(proposals, source)

    report = _element_report(registration.elements, RECTANGLE_ID)
    assert report.refinement in {"none", "translation"}
    assert report.edge_shifts_px == (0.0, 0.0, 0.0, 0.0)


def test_edge_refinement_needs_four_alternating_edges() -> None:
    """Sem alternância não há os quatro papéis para distribuir, e não há refino por aresta."""
    left, top, right, _bottom = FIELD_INK_BOX
    # Três arestas quase horizontais e uma vertical: fechado, quatro vértices e cada aresta
    # dentro da tolerância de eixo, mas não é retângulo torto — é uma fatia, e não há dois
    # papéis verticais para distribuir.
    sliver = PixelPolyline(
        points=[
            PixelPoint(x=left, y=top),
            PixelPoint(x=right, y=top),
            PixelPoint(x=right, y=top + 10.0),
            PixelPoint(x=left + 200.0, y=top + 10.0),
        ],
        closed=True,
    )
    assert vision._rectangular_edges(sliver) is None
    assert vision._rectangular_edges(_closed_rectangle(FIELD_INK_BOX)) is not None
    # Polilinha aberta e contorno de outra contagem de vértices também seguem no rígido.
    assert vision._rectangular_edges(_isolated_line()) is None
    assert (
        vision._rectangular_edges(
            PixelPolyline(points=_closed_rectangle(FIELD_INK_BOX).points[:3], closed=True)
        )
        is None
    )


def test_edge_orthogonality_tolerance_matches_the_trace_regulariser() -> None:
    """A repetição da constante é deliberada (ciclo de import); divergir dela não é.

    Quem decide adiante que um contorno é retangular é `geometry_solver.regularise`. Se o
    refino chamasse de retângulo o que ela trata como diagonal, o estágio corrigiria o
    tamanho de uma forma que o traçado nem vai reconhecer.
    """
    from croquitodxf_worker.geometry_solver import AXIS_TOLERANCE_DEGREES

    assert EDGE_ORTHOGONALITY_TOLERANCE_DEGREES == AXIS_TOLERANCE_DEGREES


def test_edge_refinement_never_flattens_the_element(tmp_path: Path) -> None:
    """Corrigir tamanho é o trabalho; anular o elemento não é.

    Um par de arestas paralelas fechando sobre a mesma tinta daria cobertura perfeita e um
    traço no lugar do contorno — foi o que a faixa de área vegetativa do Guaxindiba fez
    quando o corredor da ordem a empurrou 157 px contra a base do contorno do terreno.
    """
    source = tmp_path / "tamanho.png"
    _render_size_fixture(source)
    registered, registration = register_to_ink(_size_proposals(), source)

    def extents(polyline: PixelPolyline) -> tuple[float, float]:
        xs = [point.x for point in polyline.points]
        ys = [point.y for point in polyline.points]
        return max(xs) - min(xs), max(ys) - min(ys)

    refined = 0
    for item, proposal in zip(registered, _size_proposals(), strict=True):
        if _element_report(registration.elements, item.id).refinement != "edges":
            continue
        assert isinstance(item.geometry, PixelPolyline)
        assert isinstance(proposal.geometry, PixelPolyline)
        refined += 1
        for after, before in zip(extents(item.geometry), extents(proposal.geometry), strict=True):
            assert after >= EDGE_MIN_EXTENT_RATIO * before
    assert refined > 0


def test_edge_window_follows_the_depth_the_edge_crosses(tmp_path: Path) -> None:
    """A janela por aresta é fração da extensão PERPENDICULAR, não da diagonal do elemento.

    Pela diagonal, a caixa de lado aberto (250 px de altura contra 838 px de diagonal)
    ganharia 126 px para a aresta horizontal andar — quase o dobro da profundidade dela — e
    passaria a alcançar a linha de outro elemento. Pela extensão perpendicular ganha 87 px.
    """
    source = tmp_path / "tamanho.png"
    _render_size_fixture(source)
    orphan = _closed_rectangle(ORPHAN_BOX)
    edges = vision._rectangular_edges(orphan)
    assert edges is not None
    span = float(max(SIZE_SHEET))
    height = ORPHAN_BOX[3] - ORPHAN_BOX[1]
    width = ORPHAN_BOX[2] - ORPHAN_BOX[0]

    windows = {edge.feature: vision._edge_window(orphan, edge, span) for edge in edges}

    assert windows[0] == pytest.approx(EDGE_SHIFT_EXTENT_RATIO * height)
    assert windows[1] == windows[0]
    # A largura pediria 280 px; o teto da página corta em 5%, que é o limite declarado.
    assert windows[2] == pytest.approx(span * EDGE_SHIFT_MAX_SPAN_RATIO)
    assert EDGE_SHIFT_EXTENT_RATIO * width > windows[2]


TIP_INK_TOP, TIP_INK_BOTTOM = 400.0, 1300.0
"""Extensão do traço vertical desenhado: é até aqui que uma linha deve ir, e não além."""

LONG_X, EXACT_X, SHORT_X = 900.0, 1500.0, 2100.0

STUB = (260.0, 300.0)
"""Tinta órfã acima da linha comprida: o toco de cota que prende a ponta longe do traço.

É a assinatura do defeito real — no Guaxindiba a ponta de cima da linha de meio de campo
pousou no traço da cota "6,60", 304 px além do fim do traço dela, e o empurrão rígido não
tinha como desfazer isso porque mover a linha inteira estragaria a outra ponta.
"""

LONG_TOP, SHORT_TOP, SHORT_BOTTOM = 280.0, 520.0, 1180.0

TIP_FILLERS = (
    (100.0, 1700.0, 250.0, 1850.0),
    (2750.0, 1700.0, 2900.0, 1850.0),
    (100.0, 2100.0, 250.0, 2250.0),
    (2750.0, 2100.0, 2900.0, 2250.0),
)

LONG_ID = "vp_" + "1" * 16
EXACT_ID = "vp_" + "2" * 16
SHORT_ID = "vp_" + "3" * 16


def _render_tip_fixture(path: Path) -> None:
    """Três traços verticais iguais e um toco de cota acima do primeiro."""
    image = Image.new("RGB", SIZE_SHEET, "white")
    draw = ImageDraw.Draw(image)
    for x in (LONG_X, EXACT_X, SHORT_X):
        draw.line([(x, TIP_INK_TOP), (x, TIP_INK_BOTTOM)], fill="black", width=7)
    draw.line([(LONG_X, STUB[0]), (LONG_X, STUB[1])], fill="black", width=7)
    for box in TIP_FILLERS:
        draw.rectangle(box, outline="black", width=7)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG")


def _vertical(identifier: str, x: float, top: float, bottom: float, label: str) -> VisionProposal:
    return _proposal(
        identifier,
        PixelLine(start=PixelPoint(x=x, y=top), end=PixelPoint(x=x, y=bottom)),
        label,
    )


def _tip_proposals() -> list[VisionProposal]:
    return [
        _vertical(LONG_ID, LONG_X, LONG_TOP, TIP_INK_BOTTOM, "linha comprida demais"),
        _vertical(EXACT_ID, EXACT_X, TIP_INK_TOP, TIP_INK_BOTTOM, "linha já certa"),
        _vertical(SHORT_ID, SHORT_X, SHORT_TOP, SHORT_BOTTOM, "linha curta demais"),
        *[
            _proposal("vp_" + "456789ab"[index] * 16, _closed_rectangle(box), f"apoio {index}")
            for index, box in enumerate(TIP_FILLERS)
        ],
    ]


def _without_tip_refinement(monkeypatch: pytest.MonkeyPatch) -> None:
    """Desliga o deslizamento das pontas para o mesmo caso mostrar o que o rígido dava."""
    monkeypatch.setattr(vision, "_slide_line_tips", lambda pushed, **_kwargs: pushed)


def test_line_tip_shrinks_to_where_its_own_ink_ends(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Empurrão rígido acerta onde a linha está; só a ponta acerta até onde ela vai.

    A ponta de cima está pousada num toco de cota, com um vão sem tinta entre ele e o traço
    de verdade. Mover a linha inteira não resolve — traria a ponta de baixo junto —, e a ponta
    órfã é o que impede o encosto com os elementos vizinhos de fechar no traçado.
    """
    source = tmp_path / "pontas.png"
    _render_tip_fixture(source)
    proposals = _tip_proposals()

    _without_tip_refinement(monkeypatch)
    rigid, _report = register_to_ink(proposals, source)
    monkeypatch.undo()
    # O antes: a ponta continua no toco, longe do começo do traço.
    assert _top_of(rigid[0].geometry) < TIP_INK_TOP - 80.0

    registered, registration = register_to_ink(proposals, source)

    report = _element_report(registration.elements, LONG_ID)
    assert report.refinement == "tips"
    line = registered[0].geometry
    assert isinstance(line, PixelLine)
    # A ponta encolheu até onde a tinta começa; o vão sem tinta não foi atravessado para
    # colher o toco, porque o traço atrás do vão é mais curto que o próprio vão.
    assert _top_of(line) == pytest.approx(TIP_INK_TOP, abs=25.0)
    assert report.tip_shifts_px[0] > 0.0
    # A outra ponta e a direção não pagam pelo erro desta: a linha continua vertical no lugar.
    assert line.start.x == pytest.approx(LONG_X, abs=1e-6)
    assert line.end.x == pytest.approx(LONG_X, abs=1e-6)
    assert _bottom_of(line) == pytest.approx(TIP_INK_BOTTOM, abs=25.0)
    assert report.coverage_refined >= report.coverage_global
    assert all(item.coverage_refined >= item.coverage_raw for item in registration.elements)
    assert all(item.order_unresolved is False for item in registration.elements)
    # Mesma entrada, mesma saída: a busca é em grade fixa, sem nada aleatório.
    repeated, _again = register_to_ink(proposals, source)
    assert [item.geometry for item in repeated] == [item.geometry for item in registered]


def test_line_that_is_already_right_stays_within_the_ink_tolerance(tmp_path: Path) -> None:
    """Linha já assentada não sai do lugar: no máximo encosta na borda da própria tinta.

    O resíduo não é zero e não deveria ser fingido de zero. "Sobre tinta" neste estágio é
    definido com a tolerância da tinta — a mesma que decide corroboração, ordem e encosto —,
    então a ponta pousa na borda desse halo, e não no centro do último traço. O que a regra
    precisa garantir é que ela não vá embora procurar outra linha, e é isso que se mede.
    """
    source = tmp_path / "pontas.png"
    _render_tip_fixture(source)
    tolerance = VisionConfig().ink_corroboration_tolerance_px * max(SIZE_SHEET) / 2200

    registered, registration = register_to_ink(_tip_proposals(), source)

    report = _element_report(registration.elements, EXACT_ID)
    assert all(abs(shift) <= tolerance + 7.0 for shift in report.tip_shifts_px)
    line = registered[1].geometry
    assert isinstance(line, PixelLine)
    assert _top_of(line) == pytest.approx(TIP_INK_TOP, abs=tolerance + 7.0)
    assert _bottom_of(line) == pytest.approx(TIP_INK_BOTTOM, abs=tolerance + 7.0)


def test_line_that_is_too_short_grows_to_the_extent_of_its_ink(tmp_path: Path) -> None:
    """A ponta desliza nos dois sentidos: encurta o que sobra e estica o que falta."""
    source = tmp_path / "pontas.png"
    _render_tip_fixture(source)

    registered, registration = register_to_ink(_tip_proposals(), source)

    report = _element_report(registration.elements, SHORT_ID)
    assert report.refinement == "tips"
    line = registered[2].geometry
    assert isinstance(line, PixelLine)
    assert _top_of(line) == pytest.approx(TIP_INK_TOP, abs=25.0)
    assert _bottom_of(line) == pytest.approx(TIP_INK_BOTTOM, abs=25.0)
    # Esticar é deslizar para fora: início negativo, fim positivo.
    assert report.tip_shifts_px[0] < 0.0
    assert report.tip_shifts_px[1] > 0.0
    assert report.coverage_refined >= report.coverage_global


def test_line_tip_stops_at_the_order_corridor_instead_of_crossing(tmp_path: Path) -> None:
    """A ponta não atravessa vizinho paralelo para alcançar tinta do outro lado dele.

    A tinta desce até 400 e a ponta gostaria de ir até lá. O corredor da ordem, fechado por um
    vizinho já assentado, para em 550: ordem certa com menos tinta vence linha trocada, e vale
    para a ponta exatamente como vale para o elemento inteiro.
    """
    corridor, ink_top = 550.0, 500.0
    line = PixelLine(start=PixelPoint(x=1000.0, y=600.0), end=PixelPoint(x=1200.0, y=1300.0))

    def measure(points: NDArray[np.float64]) -> float:
        rows = points[:, 1]
        return float(((rows >= ink_top) & (rows <= TIP_INK_BOTTOM)).mean())

    def slide(guard: vision._OrderGuard) -> PixelLine:
        # A tinta sintética é uma faixa maciça, sem traço cruzante: nela todo ponto com tinta
        # testemunha um trecho contínuo, então a evidência de trecho é a própria medida.
        result = vision._slide_line_tips(
            vision._Refinement(geometry=line, kind="none"),
            measure=measure,
            runs_along=lambda _direction: measure,
            samples=64,
            span=float(max(SIZE_SHEET)),
            guard=guard,
        )
        assert isinstance(result.geometry, PixelLine)
        return result.geometry

    unbounded = slide(vision._OrderGuard(limits=((-math.inf, math.inf),) * 4))
    # Sem corredor a ponta vai até onde a tinta começa, atravessando o limite: é o movimento
    # que a lei precisa conter.
    assert _top_of(unbounded) == pytest.approx(ink_top, abs=15.0)
    assert _top_of(unbounded) < corridor

    guarded = slide(
        vision._OrderGuard(
            limits=(
                (corridor, math.inf),
                (-math.inf, math.inf),
                (-math.inf, math.inf),
                (-math.inf, math.inf),
            )
        )
    )
    assert _top_of(guarded) >= corridor
    assert _top_of(guarded) < 600.0


def test_line_over_a_longer_stroke_does_not_adopt_the_extent_of_the_stroke(
    tmp_path: Path,
) -> None:
    """Traço que continua além da ponta não diz onde a linha acaba, então a ponta não estica.

    O portão do Guaxindiba é uma abertura de 3,10 m desenhada SOBRE a linha do muro: a tinta
    corre para os dois lados, e a extensão dele é a evidência que ele existe para declarar.
    Esticar até a janela apagaria o vão — e é o que o comprimento útil, sozinho, faria, porque
    cada pixel a mais é tinta coberta.
    """
    source = tmp_path / "pontas.png"
    _render_tip_fixture(source)
    # Um pedaço curto no meio do traço vertical, com tinta sobrando dos dois lados.
    inside = _vertical(LONG_ID, EXACT_X, 700.0, 900.0, "trecho sobre o traço")
    proposals = [inside, *_tip_proposals()[1:]]

    registered, registration = register_to_ink(proposals, source)

    report = _element_report(registration.elements, LONG_ID)
    line = registered[0].geometry
    assert isinstance(line, PixelLine)
    tolerance = VisionConfig().ink_corroboration_tolerance_px * max(SIZE_SHEET) / 2200
    # Pode encostar no halo da tinta; não pode adotar a extensão do traço inteiro.
    assert _top_of(line) >= 700.0 - tolerance - 7.0
    assert _bottom_of(line) <= 900.0 + tolerance + 7.0
    assert all(abs(shift) <= tolerance + 7.0 for shift in report.tip_shifts_px)


CROSS_X = 1500.0
"""Coluna do traço vertical do caso do cruzamento; longe dos apoios da fixture de pontas."""

CROSS_OWN_TOP, CROSS_OWN_BOTTOM = 900.0, 2000.0
"""Extensão da tinta PRÓPRIA da linha: é onde a ponta tem de parar."""

CROSS_STROKE_Y, CROSS_STROKE_THICKNESS = 870.0, 20
"""Risco horizontal que cruza a coluna 30 px antes do run próprio, com 20 px de espessura.

É a assinatura medida no Guaxindiba: a linha de meio de campo encontra o risco do muro pouco
antes da própria tinta, e o halo da tolerância cola os dois numa mancha contínua — o vão de
20 px é menor que duas tolerâncias. Cobertura e comprimento útil não distinguem um do outro,
e a ponta parava na borda de cima da mancha, 44 px acima da tinta que é dela.
"""

CROSS_LINE_TOP = 800.0
"""Ponta de cima da proposta: acima do risco, como o modelo entregou no caso real."""

CROSS_ID = "vp_" + "c" * 16


def _render_crossing_fixture(path: Path) -> None:
    """Um traço vertical, um risco horizontal cruzando pouco acima dele, e os apoios."""
    image = Image.new("RGB", SIZE_SHEET, "white")
    draw = ImageDraw.Draw(image)
    draw.line(
        [(CROSS_X, CROSS_OWN_TOP), (CROSS_X, CROSS_OWN_BOTTOM)],
        fill="black",
        width=7,
    )
    draw.line(
        [(CROSS_X - 500, CROSS_STROKE_Y), (CROSS_X + 500, CROSS_STROKE_Y)],
        fill="black",
        width=CROSS_STROKE_THICKNESS,
    )
    for box in TIP_FILLERS:
        draw.rectangle(box, outline="black", width=7)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG")


def _crossing_proposals() -> list[VisionProposal]:
    return [
        _vertical(CROSS_ID, CROSS_X, CROSS_LINE_TOP, CROSS_OWN_BOTTOM, "linha sobre o risco"),
        *[
            _proposal("vp_" + "456789ab"[index] * 16, _closed_rectangle(box), f"apoio {index}")
            for index, box in enumerate(TIP_FILLERS)
        ],
    ]


def test_line_tip_skips_a_crossing_stroke_and_lands_on_its_own_run(tmp_path: Path) -> None:
    """Risco perpendicular tem tinta e não é fim de linha: a ponta pula e segue até o run.

    Com o halo, o risco e a linha que ele cruza são uma mancha contínua — cobertura e
    comprimento útil só sabem que ali há tinta, e param na primeira borda que encontram. Foi
    o que aconteceu no Guaxindiba: a ponta de cima da linha de meio parou no risco do muro,
    44 px antes da tinta própria, encostou na faixa do muro em vez da do campo e o traçado
    amarrou o 21,75 no lugar errado. A parada só vale onde a tinta se estende NA DIREÇÃO da
    linha por pelo menos o trecho mínimo declarado.
    """
    source = tmp_path / "cruzante.png"
    _render_crossing_fixture(source)
    tolerance = VisionConfig().ink_corroboration_tolerance_px * max(SIZE_SHEET) / 2200
    run = vision.TIP_MIN_INK_RUN_TOLERANCES * tolerance
    stroke_bottom = CROSS_STROKE_Y + CROSS_STROKE_THICKNESS / 2

    registered, registration = register_to_ink(_crossing_proposals(), source)

    report = _element_report(registration.elements, CROSS_ID)
    assert report.refinement == "tips"
    line = registered[0].geometry
    assert isinstance(line, PixelLine)
    # O risco ficou para trás: parar nele (ou no halo dele) é o defeito que a regra impede.
    assert _top_of(line) > stroke_bottom
    # E a ponta parou na tinta própria, não além dela: o resíduo para dentro é o trecho mínimo.
    assert CROSS_OWN_TOP - tolerance <= _top_of(line) <= CROSS_OWN_TOP + run + 3.0
    # A outra ponta e a direção continuam intactas.
    assert _bottom_of(line) == pytest.approx(CROSS_OWN_BOTTOM, abs=run + 3.0)
    assert line.start.x == pytest.approx(CROSS_X, abs=1e-6)
    assert line.end.x == pytest.approx(CROSS_X, abs=1e-6)
    assert all(item.coverage_refined >= item.coverage_raw for item in registration.elements)
    assert all(item.order_unresolved is False for item in registration.elements)
    repeated, _again = register_to_ink(_crossing_proposals(), source)
    assert [item.geometry for item in repeated] == [item.geometry for item in registered]


def test_line_tips_never_shrink_the_line_past_the_extent_floor(tmp_path: Path) -> None:
    """Encolher é corrigir extensão; encolher até sumir seria apagar a observação."""
    source = tmp_path / "pontas.png"
    _render_tip_fixture(source)

    registered, registration = register_to_ink(_tip_proposals(), source)

    for item, proposal in zip(registered, _tip_proposals(), strict=True):
        if _element_report(registration.elements, item.id).refinement != "tips":
            continue
        assert isinstance(item.geometry, PixelLine)
        assert isinstance(proposal.geometry, PixelLine)
        before = math.dist(
            (proposal.geometry.start.x, proposal.geometry.start.y),
            (proposal.geometry.end.x, proposal.geometry.end.y),
        )
        after = math.dist(
            (item.geometry.start.x, item.geometry.start.y),
            (item.geometry.end.x, item.geometry.end.y),
        )
        assert after >= EDGE_MIN_EXTENT_RATIO * before


def test_open_polyline_that_is_not_an_arc_is_never_reshaped(tmp_path: Path) -> None:
    """Reta é o limite de um círculo de raio infinito; re-formá-la inventaria curvatura."""
    source = tmp_path / "curvas.png"
    _render_curved_fixture(source)
    start, end = ISOLATED_LINE
    straight_points = [
        PixelPoint(
            x=start[0] + (end[0] - start[0]) * step / 11 + 6,
            y=start[1] + (end[1] - start[1]) * step / 11 + 5,
        )
        for step in range(12)
    ]
    proposals = [
        _proposal(RECTANGLE_ID, _rectangle_polyline(), "retângulo"),
        _proposal(LINE_ID, PixelPolyline(points=straight_points, closed=False), "muro reto"),
    ]

    registered, registration = register_to_ink(proposals, source)

    report = _element_report(registration.elements, LINE_ID)
    assert report.refinement in {"none", "translation"}
    assert report.radius_delta_px == 0.0
    wall = registered[1].geometry
    assert isinstance(wall, PixelPolyline)
    assert len(wall.points) == len(straight_points)
    # Rígido de verdade: o vetor entre vértices consecutivos sobrevive intacto.
    before = [
        (second.x - first.x, second.y - first.y) for first, second in pairwise(straight_points)
    ]
    after = [(second.x - first.x, second.y - first.y) for first, second in pairwise(wall.points)]
    for (before_x, before_y), (after_x, after_y) in zip(before, after, strict=True):
        assert after_x == pytest.approx(before_x, abs=1e-6)
        assert after_y == pytest.approx(before_y, abs=1e-6)


def _minimal_set(detector_version: str) -> VisionProposalSet:
    return VisionProposalSet.model_validate(
        {
            "dataset_id": "detector-fixture-v1",
            "page_number": 1,
            "image_sha256": "a" * 64,
            "image_width_px": 100,
            "image_height_px": 100,
            "detector_version": detector_version,
            "configured_limits": {"line": 10},
            "limit_reached": [],
            "proposals": [
                VisionProposal(
                    id="vp_1111111111111111",
                    kind="line",
                    geometry=PixelLine(start=PixelPoint(x=0, y=10), end=PixelPoint(x=90, y=10)),
                    algorithm=GEOMETRY_EXTRACTION_ALGORITHM,
                    quality_score=0.9,
                ).model_dump()
            ],
            "safety_notes": ["fixture", "revisão humana obrigatória", "não exportável"],
        }
    )


def test_proposal_set_accepts_the_provider_extraction_detector() -> None:
    """Conjunto vindo da extração de geometria registrada declara a própria origem;
    os invariantes das propostas (unresolved, export=False) não mudam."""
    proposal_set = _minimal_set(GEOMETRY_EXTRACTION_ALGORITHM)
    assert proposal_set.detector_version == GEOMETRY_EXTRACTION_ALGORITHM
    assert all(item.export is False for item in proposal_set.proposals)


def test_proposal_set_refuses_an_unknown_detector() -> None:
    with pytest.raises(ValueError):
        _minimal_set("detector-desconhecido-v9")
