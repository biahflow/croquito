import math
from itertools import combinations

import pytest

from croquito_core.models import (
    CircleGeometry,
    DimensionGeometry,
    Entity,
    EntityKind,
    LayerName,
    LineGeometry,
    Point2D,
    PolylineGeometry,
    Precision,
    Provenance,
    TextGeometry,
)
from croquito_worker.element_labels import (
    BALLOON_SUMMARY_CODE,
    LABEL_SUMMARY_CODE,
    LEGEND_SUMMARY_CODE,
    MAX_LABEL_CHARS,
    MIN_LABEL_HEIGHT_M,
    _closest_boundary_point,
    _contains_point,
    estimated_width,
    geometry_anchor,
    label_entities,
    label_entity,
    label_height_for,
    place_labels,
)


def _provenance() -> Provenance:
    return Provenance(
        source_type="vision_proposal_calibrated",
        source_ids=["vp_1"],
        summary_code="TRACED_PROPOSAL",
    )


def _polyline(points: list[tuple[float, float]], *, closed: bool = True) -> Entity:
    return Entity(
        kind=EntityKind.POLYLINE,
        layer=LayerName.CAMPO,
        precision=Precision.APPROXIMATE,
        geometry=PolylineGeometry(points=[Point2D(x=x, y=y) for x, y in points], closed=closed),
        provenance=_provenance(),
    )


def _line(start: tuple[float, float], end: tuple[float, float]) -> Entity:
    return Entity(
        kind=EntityKind.LINE,
        layer=LayerName.MURO,
        precision=Precision.APPROXIMATE,
        geometry=LineGeometry(
            start=Point2D(x=start[0], y=start[1]), end=Point2D(x=end[0], y=end[1])
        ),
        provenance=_provenance(),
    )


FIELD = [(0.0, 0.0), (25.9, 0.0), (25.9, 21.75), (0.0, 21.75)]


def _centre(label: Entity) -> tuple[float, float]:
    """O TEXT do DXF ancora pela esquerda; o que importa é onde o texto fica centrado."""
    assert isinstance(label.geometry, TextGeometry)
    geometry = label.geometry
    return (
        geometry.insertion.x + estimated_width(geometry.text, geometry.height) / 2,
        geometry.insertion.y + geometry.height / 2,
    )


def test_label_lands_on_the_area_centre_of_a_closed_region() -> None:
    entity = _polyline(FIELD)

    label = label_entity(entity, "campo sintético", height=0.4, source_ids=["job-1"])

    assert label is not None
    assert _centre(label) == pytest.approx((25.9 / 2, 21.75 / 2))


def test_uneven_vertex_density_does_not_drag_the_label_off_centre() -> None:
    """Média dos vértices poria a etiqueta onde o traçado tem mais detalhe, não no meio."""
    detailed = _polyline(
        [
            (0.0, 0.0),
            (5.0, 0.0),
            (6.0, 0.0),
            (7.0, 0.0),
            (8.0, 0.0),
            (20.0, 0.0),
            (20.0, 10.0),
            (0.0, 10.0),
        ]
    )

    label = label_entity(detailed, "patamar", height=0.4, source_ids=[])

    assert label is not None
    assert isinstance(label.geometry, TextGeometry)
    assert isinstance(detailed.geometry, PolylineGeometry)
    vertices = detailed.geometry.points
    vertex_mean_x = sum(point.x for point in vertices) / len(vertices)
    assert vertex_mean_x < 9.0  # a média mente: puxa para o aglomerado
    assert _centre(label)[0] == pytest.approx(10.0, abs=0.01)


def test_open_polyline_gets_the_label_halfway_along_its_own_path() -> None:
    wall = _polyline([(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)], closed=False)

    label = label_entity(wall, "muro vizinho", height=0.4, source_ids=[])

    assert label is not None
    assert _centre(label) == pytest.approx((10.0, 0.0))


def test_label_is_derived_and_never_demands_an_approximation_decision() -> None:
    """`approximate` obrigaria o revisor a aceitar cada etiqueta para poder exportar."""
    label = label_entity(_polyline(FIELD), "campo", height=0.4, source_ids=["job-1"])

    assert label is not None
    assert label.precision is Precision.DERIVED
    assert label.layer is LayerName.TEXTOS
    assert label.provenance is not None
    assert label.provenance.summary_code == LABEL_SUMMARY_CODE


def test_a_long_label_is_truncated_instead_of_flooding_the_drawing() -> None:
    label = label_entity(_polyline(FIELD), "muro " * 40, height=0.4, source_ids=[])

    assert label is not None
    assert isinstance(label.geometry, TextGeometry)
    assert len(label.geometry.text) <= MAX_LABEL_CHARS


def test_blank_label_produces_nothing() -> None:
    assert label_entity(_polyline(FIELD), "   ", height=0.4, source_ids=[]) is None


def test_text_and_dimension_are_not_labelled() -> None:
    """Rotular um rótulo duplicaria palavra na planta."""
    text = Entity(
        kind=EntityKind.TEXT,
        layer=LayerName.TEXTOS,
        precision=Precision.DERIVED,
        geometry=TextGeometry(insertion=Point2D(x=0, y=0), text="campo", height=0.4),
    )
    dimension = Entity(
        kind=EntityKind.DIMENSION,
        layer=LayerName.COTAS,
        precision=Precision.DERIVED,
        geometry=DimensionGeometry(
            first=Point2D(x=0, y=0), second=Point2D(x=1, y=0), base=Point2D(x=0, y=1)
        ),
    )

    assert geometry_anchor(text.geometry) is None
    assert geometry_anchor(dimension.geometry) is None
    assert label_entity(text, "campo", height=0.4, source_ids=[]) is None


def test_circle_is_labelled_at_its_centre() -> None:
    circle = Entity(
        kind=EntityKind.CIRCLE,
        layer=LayerName.CAMPO,
        precision=Precision.APPROXIMATE,
        geometry=CircleGeometry(center=Point2D(x=12.95, y=10.875), radius=3.0),
        provenance=_provenance(),
    )

    label = label_entity(circle, "círculo central", height=0.4, source_ids=[])

    assert label is not None
    assert _centre(label)[0] == pytest.approx(12.95)


def test_height_scales_with_the_drawing_and_never_goes_below_the_floor() -> None:
    big = label_height_for([_polyline(FIELD)])
    tiny = label_height_for([_line((0.0, 0.0), (0.5, 0.0))])

    assert big == pytest.approx(math.hypot(25.9, 21.75) * 0.012)
    assert tiny == MIN_LABEL_HEIGHT_M


def test_height_is_measured_over_the_scene_not_over_the_labelled_subset() -> None:
    """Senão a etiqueta encolheria só porque o recorte rotulado é pequeno."""
    scene = [_polyline(FIELD), _line((0.0, 0.0), (0.2, 0.0))]

    labels = label_entities([(scene[1], "marca")], scene_entities=scene)

    assert len(labels) == 1
    assert isinstance(labels[0].geometry, TextGeometry)
    assert labels[0].geometry.height == pytest.approx(label_height_for(scene))


def test_concentric_markings_do_not_pile_their_names_on_one_spot() -> None:
    """Círculo central, meio de campo e marca do pênalti têm centroides quase iguais."""
    same_spot = [
        (_polyline(FIELD), "círculo central"),
        (_polyline(FIELD), "linha de meio de campo"),
        (_polyline(FIELD), "marca do pênalti"),
    ]

    labels = label_entities(same_spot)

    boxes = []
    for label in labels:
        assert isinstance(label.geometry, TextGeometry)
        insertion, text, height = (
            label.geometry.insertion,
            label.geometry.text,
            label.geometry.height,
        )
        boxes.append(
            (
                insertion.x,
                insertion.y,
                insertion.x + estimated_width(text, height),
                insertion.y + height,
            )
        )
    for first, second in combinations(boxes, 2):
        apart = (
            first[2] <= second[0]
            or second[2] <= first[0]
            or first[3] <= second[1]
            or second[3] <= first[1]
        )
        assert apart, "dois rótulos ocupando o mesmo retângulo viram borrão no CAD"


def test_a_label_is_never_dropped_just_because_the_spot_is_crowded() -> None:
    """Sumir com a etiqueta esconderia o elemento; sobrepor ainda informa."""
    crowded = [(_polyline(FIELD), f"elemento {index}") for index in range(30)]

    assert len(label_entities(crowded)) == 30


def test_label_is_centred_on_the_element_not_anchored_to_its_right() -> None:
    labels = label_entities([(_polyline(FIELD), "campo sintético")])

    assert _centre(labels[0])[0] == pytest.approx(25.9 / 2)


def test_a_roomy_region_still_gets_a_balloon_not_an_inline_name() -> None:
    """Nome inline foi aposentado em 2026-08-13 (decisão de produto: consistência keynote).

    Antes, uma região fechada grande o bastante para o texto caber com folga recebia o
    nome completo dentro dela; foi exatamente esse caso — o "Patamar de concreto
    esquerdo" do Guaxindiba real — que saiu diferente de todos os outros elementos da
    prancha e motivou a mudança. Agora todo elemento rotulado, região grande ou não,
    segue o mesmo caminho: balão numerado junto ao elemento + linha na legenda.
    """
    huge_region = _polyline([(0.0, 0.0), (200.0, 0.0), (200.0, 200.0), (0.0, 200.0)])

    results = place_labels([(huge_region, "campo")], source_ids=["job-1"])

    assert len(results) == 3  # círculo do balão + número + linha de legenda

    balloons = [entity for entity in results if entity.kind is EntityKind.CIRCLE]
    assert len(balloons) == 1
    assert balloons[0].provenance is not None
    assert balloons[0].provenance.summary_code == BALLOON_SUMMARY_CODE

    legend = [
        entity
        for entity in results
        if entity.provenance is not None and entity.provenance.summary_code == LEGEND_SUMMARY_CODE
    ]
    assert len(legend) == 1
    assert isinstance(legend[0].geometry, TextGeometry)
    assert "campo" in legend[0].geometry.text

    # Nenhum texto carrega o nome completo sozinho — só o número do balão (dígito) e a
    # linha de legenda ("(1)  campo"); o nome inline não existe mais como caminho possível.
    full_name_texts = [
        entity
        for entity in results
        if isinstance(entity.geometry, TextGeometry) and entity.geometry.text == "campo"
    ]
    assert full_name_texts == []


# --- Balão de elemento contêiner (2026-08-13): região fechada que contém outro elemento
# pousa junto à borda, não no centroide. Caso real: balão ② do Alambrado do Guaxindiba
# pousando no meio do campo em vez de junto ao próprio contorno.

REGION = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]


def _balloon_centres(results: list[Entity]) -> list[tuple[float, float]]:
    centres = []
    for entity in results:
        if entity.kind is EntityKind.CIRCLE:
            assert isinstance(entity.geometry, CircleGeometry)
            centres.append((entity.geometry.center.x, entity.geometry.center.y))
    return centres


def test_container_balloon_hugs_the_border_when_another_element_sits_inside() -> None:
    """Balão ② do Alambrado (Guaxindiba real): a região abraça outro elemento e não pode
    pousar no centroide de área — o número precisa nomear o contorno, não o miolo."""
    region = _polyline(REGION)
    inner = _line((20.0, 20.0), (40.0, 40.0))  # ponto médio (30, 30), dentro da região

    results = place_labels(
        [(region, "alambrado")],
        scene_entities=[region, inner],
        source_ids=["job-1"],
    )

    balloons = _balloon_centres(results)
    assert len(balloons) == 1
    centre = balloons[0]
    distance_to_centroid = math.hypot(centre[0] - 50.0, centre[1] - 50.0)
    distance_to_border = min(centre[0], 100.0 - centre[0], centre[1], 100.0 - centre[1])
    assert distance_to_centroid > 30.0, "balão não pode ficar preso no meio do contêiner"
    assert distance_to_border < 5.0, "balão deve pousar junto à borda do polígono"


def test_container_detection_falls_back_to_labelled_without_scene_entities() -> None:
    """Sem `scene_entities`, a referência de contenção é a própria lista `labelled`."""
    region = _polyline(REGION)
    inner = _line((20.0, 20.0), (40.0, 40.0))

    results = place_labels([(region, "alambrado"), (inner, "muro interno")], source_ids=["job-1"])

    balloons = _balloon_centres(results)
    assert len(balloons) == 2
    region_centre, inner_centre = balloons

    distance_to_centroid = math.hypot(region_centre[0] - 50.0, region_centre[1] - 50.0)
    distance_to_border = min(
        region_centre[0], 100.0 - region_centre[0], region_centre[1], 100.0 - region_centre[1]
    )
    assert distance_to_centroid > 30.0
    assert distance_to_border < 5.0

    # O elemento interno não é polilinha fechada: sua âncora continua no ponto médio de
    # sempre, intocada pela regra de contêiner.
    assert math.hypot(inner_centre[0] - 30.0, inner_centre[1] - 30.0) < 5.0


def test_a_region_alone_still_lands_its_balloon_near_the_centroid() -> None:
    """Região fechada sem nada dentro não é contêiner: o balão continua no centro, como hoje."""
    region = _polyline(REGION)

    results = place_labels([(region, "campo")], source_ids=["job-1"])

    balloons = _balloon_centres(results)
    assert len(balloons) == 1
    centre = balloons[0]
    assert math.hypot(centre[0] - 50.0, centre[1] - 50.0) < 5.0


SQUARE = [
    Point2D(x=0.0, y=0.0),
    Point2D(x=10.0, y=0.0),
    Point2D(x=10.0, y=10.0),
    Point2D(x=0.0, y=10.0),
]


def test_contains_point_inside_and_outside() -> None:
    assert _contains_point(SQUARE, Point2D(x=5.0, y=5.0)) is True
    assert _contains_point(SQUARE, Point2D(x=15.0, y=5.0)) is False


def test_contains_point_ray_through_a_shared_vertex_does_not_double_count() -> None:
    """Um raio horizontal exatamente na altura de dois vértices opostos de um losango não
    pode contar as travessias em dobro — a convenção half-open evita isso."""
    diamond = [
        Point2D(x=5.0, y=0.0),
        Point2D(x=10.0, y=5.0),
        Point2D(x=5.0, y=10.0),
        Point2D(x=0.0, y=5.0),
    ]

    assert _contains_point(diamond, Point2D(x=5.0, y=5.0)) is True
    assert _contains_point(diamond, Point2D(x=-1.0, y=5.0)) is False


def test_closest_boundary_point_projects_onto_the_nearest_edge() -> None:
    target = Point2D(x=5.0, y=-3.0)  # abaixo da base do quadrado

    point = _closest_boundary_point(SQUARE, target)

    assert point.x == pytest.approx(5.0)
    assert point.y == pytest.approx(0.0)


def test_closest_boundary_point_clamps_to_the_corner() -> None:
    target = Point2D(x=-5.0, y=-5.0)  # fora, na diagonal do canto (0, 0)

    point = _closest_boundary_point(SQUARE, target)

    assert point.x == pytest.approx(0.0)
    assert point.y == pytest.approx(0.0)
