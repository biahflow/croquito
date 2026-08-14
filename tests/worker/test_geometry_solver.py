import math

import pytest

from croquitodxf_worker.geometry_solver import (
    AxisBands,
    BandSeparation,
    SpanConstraint,
    band_order_violations,
    band_positions,
    estimate_scale,
    regularise,
    solve_axis,
    solve_geometry,
)
from croquitodxf_worker.topology import (
    JUNCTION_TOLERANCE_RATIO,
    Junction,
    Topology,
    VertexRef,
    build_topology,
    junction_positions,
    rebuild_all,
)
from croquitodxf_worker.vision import PixelLine, PixelPoint, PixelPolyline, VisionProposal

WIDTH, HEIGHT = 2000, 2000
TOUCH_PX = math.hypot(WIDTH, HEIGHT) * JUNCTION_TOLERANCE_RATIO
"""A tolerância de encosto é a mesma com que `build_topology` funde vértices (28,3 px aqui).

Produção passa exatamente este valor (`tracing._solve_group_geometry`); os testes usam a
mesma conta para não inventarem um limiar próprio.
"""


def _polyline(
    identifier: str, points: list[tuple[float, float]], *, closed: bool = True
) -> VisionProposal:
    return VisionProposal(
        id=identifier,
        kind="contour",
        geometry=PixelPolyline(points=[PixelPoint(x=x, y=y) for x, y in points], closed=closed),
        algorithm="test",
        quality_score=1.0,
    )


def _line(identifier: str, start: tuple[float, float], end: tuple[float, float]) -> VisionProposal:
    return VisionProposal(
        id=identifier,
        kind="line",
        geometry=PixelLine(
            start=PixelPoint(x=start[0], y=start[1]),
            end=PixelPoint(x=end[0], y=end[1]),
        ),
        algorithm="test",
        quality_score=1.0,
    )


def _topology(*proposals: VisionProposal) -> Topology:
    return build_topology(list(proposals), image_width=WIDTH, image_height=HEIGHT)


# Quadrilátero fora de esquadro, como sai de um croqui à mão: lados que deviam ser
# paralelos abrem alguns graus e os comprimentos não batem entre si.
SKEWED = [(100.0, 100.0), (900.0, 130.0), (880.0, 700.0), (120.0, 660.0)]


def test_an_almost_horizontal_edge_binds_its_two_ends_to_one_band() -> None:
    topology = _topology(_polyline("vp_" + "1" * 16, SKEWED))

    bands = regularise(topology)

    assert bands.x_band_count == 2, "duas verticais viram duas faixas de x"
    assert bands.y_band_count == 2, "duas horizontais viram duas faixas de y"


def test_a_real_diagonal_is_not_straightened() -> None:
    """Endireitar um traço proposital destruiria informação do levantamento."""
    triangle = _polyline("vp_" + "2" * 16, [(100.0, 100.0), (900.0, 100.0), (900.0, 900.0)])

    bands = regularise(triangle_topology := _topology(triangle))

    # A hipotenusa tem 45°: não junta nem x nem y, então sobram três faixas em cada eixo.
    assert len(triangle_topology.junctions) == 3
    assert bands.x_band_count == 2  # só a vertical uniu duas junções
    assert bands.y_band_count == 2  # só a horizontal uniu duas junções


def test_regularisation_moves_nothing_by_itself() -> None:
    """Separar 'quem anda junto' de 'para onde' deixa cada metade testável sozinha."""
    topology = _topology(_polyline("vp_" + "3" * 16, SKEWED))

    regularise(topology)

    assert junction_positions(topology) == {
        junction.id: (junction.x, junction.y) for junction in topology.junctions
    }


def test_a_confirmed_dimension_wins_over_the_traced_position() -> None:
    """A regra do projeto: cota tem precedência sobre pixel."""
    topology = _topology(_polyline("vp_" + "4" * 16, SKEWED))
    bands = regularise(topology)
    traced_x, _traced_y = band_positions(topology, bands)
    left, right = sorted(traced_x, key=lambda band: traced_x[band])

    solved = solve_axis(
        traced_x,
        [
            SpanConstraint(
                axis="x", first_band=left, second_band=right, value_m=25.90, source_id="rd_1"
            )
        ],
        prior_scale=25.90 / abs(traced_x[right] - traced_x[left]),
    )

    assert solved[right] - solved[left] == pytest.approx(25.90, abs=1e-4)


def test_a_band_no_dimension_reaches_still_gets_a_position() -> None:
    """Sem a equação fraca do traçado o sistema ficaria indeterminado nessas faixas."""
    traced = {0: 0.0, 1: 400.0, 2: 800.0}

    solved = solve_axis(
        traced,
        [SpanConstraint(axis="x", first_band=0, second_band=2, value_m=20.0, source_id="rd_1")],
        prior_scale=20.0 / 800.0,
    )

    assert solved[2] - solved[0] == pytest.approx(20.0, abs=1e-4)
    assert solved[1] == pytest.approx(10.0, abs=0.5), "a faixa do meio segue o traçado"


def test_the_origin_is_pinned_so_translation_is_not_a_free_solution() -> None:
    traced = {0: 300.0, 1: 700.0}

    solved = solve_axis(
        traced,
        [SpanConstraint(axis="x", first_band=0, second_band=1, value_m=10.0, source_id="rd_1")],
        prior_scale=0.025,
    )

    assert solved[0] == pytest.approx(0.0, abs=1e-4)
    assert solved[1] == pytest.approx(10.0, abs=1e-4)


def test_two_conflicting_dimensions_are_split_instead_of_one_silently_winning() -> None:
    """Mínimos quadrados reparte o erro; escolher uma escondería o conflito do revisor."""
    traced = {0: 0.0, 1: 1000.0}

    solved = solve_axis(
        traced,
        [
            SpanConstraint(axis="x", first_band=0, second_band=1, value_m=10.0, source_id="a"),
            SpanConstraint(axis="x", first_band=0, second_band=1, value_m=12.0, source_id="b"),
        ],
        prior_scale=0.011,
    )

    assert 10.0 < solved[1] - solved[0] < 12.0


def test_scale_comes_from_the_median_so_one_bad_association_does_not_govern() -> None:
    traced = {0: 0.0, 1: 100.0, 2: 200.0, 3: 300.0}
    good = [
        SpanConstraint(axis="x", first_band=0, second_band=1, value_m=10.0, source_id="a"),
        SpanConstraint(axis="x", first_band=1, second_band=2, value_m=10.0, source_id="b"),
        SpanConstraint(axis="x", first_band=2, second_band=3, value_m=10.0, source_id="c"),
    ]
    poisoned = [
        *good,
        SpanConstraint(axis="x", first_band=0, second_band=3, value_m=900.0, source_id="ruim"),
    ]

    assert estimate_scale(traced, good) == pytest.approx(0.1)
    assert estimate_scale(traced, poisoned) == pytest.approx(0.1, abs=0.02)


def test_scale_is_absent_when_no_dimension_spans_a_known_band() -> None:
    assert estimate_scale({0: 0.0, 1: 100.0}, []) is None


def test_a_skewed_sketch_comes_out_orthogonal_with_the_dimensions_honoured() -> None:
    """O caso que motiva o módulo, ponta a ponta."""
    field = _polyline("vp_" + "5" * 16, SKEWED)
    topology = _topology(field)
    bands = regularise(topology)
    traced_x, traced_y = band_positions(topology, bands)
    left, right = sorted(traced_x, key=lambda band: traced_x[band])
    bottom, top = sorted(traced_y, key=lambda band: traced_y[band])
    constraints = [
        SpanConstraint(
            axis="x", first_band=left, second_band=right, value_m=25.90, source_id="rd_w"
        ),
        SpanConstraint(
            axis="y", first_band=bottom, second_band=top, value_m=21.75, source_id="rd_h"
        ),
    ]
    scale = estimate_scale(traced_x, constraints[:1])
    assert scale is not None

    solved_x = solve_axis(traced_x, constraints[:1], prior_scale=scale)
    solved_y = solve_axis(traced_y, constraints[1:], prior_scale=scale)
    positions = {
        junction.id: (
            solved_x[bands.x_band_of[junction.id]],
            solved_y[bands.y_band_of[junction.id]],
        )
        for junction in topology.junctions
    }
    rebuilt = rebuild_all([field], topology, positions)

    geometry = rebuilt[0].geometry
    assert isinstance(geometry, PixelPolyline)
    xs = sorted({round(point.x, 6) for point in geometry.points})
    ys = sorted({round(point.y, 6) for point in geometry.points})
    assert len(xs) == 2 and len(ys) == 2, "o quadrilátero torto saiu retangular"
    # Décimo de milímetro: a regularização de Tikhonov deixa um resíduo da ordem de
    # micrômetros num vão determinado (2,8e-7 relativo aqui). Zerá-lo exigiria resolver o
    # subespaço determinado à parte, complexidade que nenhum desenho de obra aproveita.
    assert xs[1] - xs[0] == pytest.approx(25.90, abs=1e-4)
    assert ys[1] - ys[0] == pytest.approx(21.75, abs=1e-4)
    for index in range(4):
        start = geometry.points[index]
        end = geometry.points[(index + 1) % 4]
        angle = math.degrees(math.atan2(abs(end.y - start.y), abs(end.x - start.x)))
        assert angle in (pytest.approx(0.0), pytest.approx(90.0))


# --- keep_apart também vale para as faixas (Guaxindiba v2, 2026-08-13) -----------------
#
# `build_topology` já mantinha os vértices separados, mas a faixa é a variável do solver:
# duas junções separadas na MESMA faixa continuam amarradas uma à outra. No job real a
# faixa vertical da direita reunia mureta, muro e patamar por uma ponte da faixa
# vegetativa, e a cadeia dos patamares disputava com o recuo declarado a mesma incógnita.

MURETA = "vp_" + "a1" * 8
PATAMAR = "vp_" + "b2" * 8
VEGETATIVA = "vp_" + "c3" * 8


def _coincident_pair_bridged_by_a_third() -> list[VisionProposal]:
    """Duas verticais desenhadas quase coincidentes e um terceiro elemento no meio.

    As pontas de baixo ficam a 600 px uma da outra (nunca fundem), mas a vegetativa
    encosta nas duas — 5,4 px de uma, 4,5 px da outra, dentro da tolerância de fusão — e é
    por ela que a faixa se propagava de um lado ao outro.
    """
    return [
        _line(MURETA, (1000.0, 100.0), (1000.0, 900.0)),
        _line(PATAMAR, (1012.0, 700.0), (1012.0, 1500.0)),
        _line(VEGETATIVA, (1005.0, 902.0), (1008.0, 1498.0)),
    ]


def _bands_of(topology: Topology, bands: AxisBands, proposal_id: str) -> set[int]:
    return {
        bands.x_band_of[junction.id]
        for junction in topology.junctions
        for member in junction.members
        if member.proposal_id == proposal_id
    }


def test_keep_apart_impede_que_um_terceiro_faca_ponte_entre_duas_faixas() -> None:
    """A separação declarada vale para a faixa, não só para o vértice.

    Sem os pares a mesma topologia devolve uma faixa só — é o que prova que a separação
    vem da declaração humana e não de um limiar de proximidade.
    """
    pair = [(MURETA, PATAMAR)]
    topology = build_topology(
        _coincident_pair_bridged_by_a_third(),
        image_width=WIDTH,
        image_height=HEIGHT,
        keep_apart=pair,
    )

    fused = regularise(topology)
    separated = regularise(topology, keep_apart=pair)

    assert fused.x_band_count == 1, "sem os pares, a ponte da vegetativa reúne tudo numa faixa"
    assert separated.x_band_count == 2
    assert not _bands_of(topology, separated, MURETA) & _bands_of(topology, separated, PATAMAR)
    # O terceiro não é excluído: cada ponta dele adere ao lado em que já encostava.
    assert _bands_of(topology, separated, VEGETATIVA) == {0, 1}


def test_faixas_do_keep_apart_nao_dependem_da_ordem_das_propostas() -> None:
    """O desempate é por posição, não pela ordem em que o aceite listou os elementos."""
    pair = [(MURETA, PATAMAR)]
    proposals = _coincident_pair_bridged_by_a_third()

    partitions = []
    for ordered in (proposals, list(reversed(proposals)), [proposals[2], *proposals[:2]]):
        topology = build_topology(ordered, image_width=WIDTH, image_height=HEIGHT, keep_apart=pair)
        bands = regularise(topology, keep_apart=pair)
        grouped: dict[int, set[tuple[str, int]]] = {}
        for junction in topology.junctions:
            for member in junction.members:
                grouped.setdefault(bands.x_band_of[junction.id], set()).add(
                    (member.proposal_id, member.vertex_index)
                )
        partitions.append({frozenset(members) for members in grouped.values()})

    assert partitions[0] == partitions[1] == partitions[2]


# --- Encosto no meio de aresta (Guaxindiba v2, 2026-08-13) ----------------------------
#
# A topologia funde vértice com vértice e a regularização agrupa por aresta desenhada. Um
# endpoint que pousa no MEIO da aresta de outro elemento não tem vizinho nenhum e ficava
# solto: no DXF real a linha de meio de campo vazou 5,12 m pelo fundo do campo e as áreas
# saíram para fora da lateral, todas a poucos pixels do traço em que se apoiam.

TOUCH_CAMPO = "vp_" + "d4" * 8
TOUCH_MEIO = "vp_" + "e5" * 8
TOUCH_FORA = "vp_" + "f6" * 8
TOUCH_AREA = "vp_" + "a7" * 8

# Campo 800x800 px; a linha de meio encosta no topo e no fundo a 20 px de cada, a 400 px
# de qualquer canto (nenhum vértice funde: a fusão precisaria de 28,3 px).
CAMPO_RECT = [(100.0, 100.0), (900.0, 100.0), (900.0, 900.0), (100.0, 900.0)]


def _y_bands_of(topology: Topology, bands: AxisBands, proposal_id: str) -> set[int]:
    return {
        bands.y_band_of[junction.id]
        for junction in topology.junctions
        for member in junction.members
        if member.proposal_id == proposal_id
    }


def test_encosto_no_meio_de_aresta_amarra_a_faixa_do_eixo() -> None:
    """A linha de meio: encosta no topo e no fundo do campo, sem vértice vizinho nenhum."""
    campo = _polyline(TOUCH_CAMPO, CAMPO_RECT)
    meio = _line(TOUCH_MEIO, (500.0, 120.0), (500.0, 880.0))
    topology = _topology(campo, meio)

    solto = regularise(topology)
    amarrado = regularise(topology, touch_tolerance_px=TOUCH_PX)

    assert not _y_bands_of(topology, solto, TOUCH_MEIO) & _y_bands_of(topology, solto, TOUCH_CAMPO)
    # Sem tolerância declarada nada encosta: quem chama decide, e o valor é o da fusão.
    assert solto.y_band_count == 4
    assert _y_bands_of(topology, amarrado, TOUCH_MEIO) == _y_bands_of(
        topology, amarrado, TOUCH_CAMPO
    )
    assert amarrado.y_band_count == 2
    # Encostar em Y não inventa faixa em X: a linha de meio continua onde foi desenhada.
    assert amarrado.x_band_count == 3


def test_encosto_exige_a_juncao_dentro_da_extensao_da_aresta() -> None:
    """Perto da reta que contém a aresta, mas fora do vão dela, não é encosto.

    Sem esta condição qualquer elemento na mesma altura da folha entraria na faixa —
    proximidade de coordenada não é encontro de traço.
    """
    campo = _polyline(TOUCH_CAMPO, CAMPO_RECT)
    # Mesmo y das pontas, 100 px à direita do fim da aresta (a tolerância é 28,3 px).
    fora = _line(TOUCH_FORA, (1000.0, 120.0), (1000.0, 880.0))
    topology = _topology(campo, fora)

    bands = regularise(topology, touch_tolerance_px=TOUCH_PX)

    assert not _y_bands_of(topology, bands, TOUCH_FORA) & _y_bands_of(topology, bands, TOUCH_CAMPO)


def test_lado_desenhado_sobre_a_lateral_de_outro_elemento_partilha_a_faixa_x() -> None:
    """A linha de gol da grande área, desenhada sobre a lateral do campo."""
    campo = _polyline(TOUCH_CAMPO, CAMPO_RECT)
    area = _polyline(TOUCH_AREA, [(898.0, 300.0), (700.0, 300.0), (700.0, 600.0), (898.0, 600.0)])
    topology = _topology(campo, area)

    bands = regularise(topology, touch_tolerance_px=TOUCH_PX)

    lateral = {
        bands.x_band_of[junction.id]
        for junction in topology.junctions
        for member in junction.members
        if member.proposal_id == TOUCH_CAMPO and junction.x > 500
    }
    linha_de_gol = {
        bands.x_band_of[junction.id]
        for junction in topology.junctions
        for member in junction.members
        if member.proposal_id == TOUCH_AREA and junction.x > 800
    }
    assert linha_de_gol == lateral


def test_encosto_entre_lados_de_um_par_mantido_separado_e_recusado() -> None:
    """Encosto é candidata como qualquer outra: a declaração humana recusa igual."""
    campo = _polyline(TOUCH_CAMPO, CAMPO_RECT)
    area = _polyline(TOUCH_AREA, [(898.0, 300.0), (700.0, 300.0), (700.0, 600.0), (898.0, 600.0)])
    pair = [(TOUCH_CAMPO, TOUCH_AREA)]
    topology = build_topology(
        [campo, area], image_width=WIDTH, image_height=HEIGHT, keep_apart=pair
    )

    bands = regularise(topology, keep_apart=pair, touch_tolerance_px=TOUCH_PX)

    assert not _bands_of(topology, bands, TOUCH_CAMPO) & _bands_of(topology, bands, TOUCH_AREA)


# --- keep_apart por eixo (Guaxindiba v2, 2026-08-13) -----------------------------------
#
# O par mureta↔patamar foi declarado pelo problema HORIZONTAL do dente (3,30/4,80), mas
# separava também na vertical o encontro legítimo da base da mureta com a base do campo —
# e o sistema do muro deslizou 14,5 m para baixo no DXF real.

AXIS_CAMPO = "vp_" + "b8" * 8
AXIS_MURETA = "vp_" + "c9" * 8
AXIS_PATAMAR = "vp_" + "da" * 8


def _axis_case() -> list[VisionProposal]:
    """Mureta coincidente em X com a borda do patamar, e as duas encostando na base do campo.

    A mureta corre a 12 px da borda esquerda do patamar (encosto em X, o problema que o
    revisor declara) e a ponta dela pousa 5 px acima da base do campo, que o patamar
    também encosta 10 px abaixo (encontro em Y, legítimo).
    """
    return [
        _polyline(AXIS_CAMPO, [(200.0, 200.0), (1600.0, 200.0), (1600.0, 900.0), (200.0, 900.0)]),
        _line(AXIS_MURETA, (1000.0, 905.0), (1000.0, 1400.0)),
        _polyline(
            AXIS_PATAMAR,
            [(1012.0, 910.0), (1500.0, 910.0), (1500.0, 1400.0), (1012.0, 1400.0)],
        ),
    ]


def _axis_bands(separations: list[tuple[str, str] | BandSeparation]) -> tuple[Topology, AxisBands]:
    proposals = _axis_case()
    topology = build_topology(
        proposals,
        image_width=WIDTH,
        image_height=HEIGHT,
        # A separação de vértices não conhece eixo, como em produção.
        keep_apart=[(AXIS_MURETA, AXIS_PATAMAR)],
    )
    return topology, regularise(topology, keep_apart=separations, touch_tolerance_px=TOUCH_PX)


def _y_band_at(topology: Topology, bands: AxisBands, proposal_id: str, near_y: float) -> int:
    candidates = {
        bands.y_band_of[junction.id]
        for junction in topology.junctions
        for member in junction.members
        if member.proposal_id == proposal_id and abs(junction.y - near_y) < 40.0
    }
    assert len(candidates) == 1, candidates
    return candidates.pop()


def test_keep_apart_com_eixo_separa_so_o_eixo_declarado() -> None:
    """Faixas X distintas (o dente) e faixa Y partilhada (o encontro que segura o muro)."""
    topology, bands = _axis_bands([BandSeparation(AXIS_MURETA, AXIS_PATAMAR, "x")])

    assert not _bands_of(topology, bands, AXIS_MURETA) & _bands_of(topology, bands, AXIS_PATAMAR)
    base_do_campo = _y_band_at(topology, bands, AXIS_CAMPO, 900.0)
    assert _y_band_at(topology, bands, AXIS_MURETA, 905.0) == base_do_campo
    assert _y_band_at(topology, bands, AXIS_PATAMAR, 910.0) == base_do_campo


def test_par_legado_sem_eixo_continua_separando_nos_dois() -> None:
    """O formato `["vp_a", "vp_b"]` não muda de significado: separa em X e em Y."""
    topology, bands = _axis_bands([(AXIS_MURETA, AXIS_PATAMAR)])

    assert not _bands_of(topology, bands, AXIS_MURETA) & _bands_of(topology, bands, AXIS_PATAMAR)
    assert not _y_bands_of(topology, bands, AXIS_MURETA) & _y_bands_of(
        topology, bands, AXIS_PATAMAR
    )


def test_faixas_do_encosto_nao_dependem_da_ordem_das_propostas() -> None:
    """Varredura ordenada por desvio: a partição não depende de quem o aceite listou antes."""
    proposals = _axis_case()

    partitions = []
    for ordered in (
        proposals,
        list(reversed(proposals)),
        [proposals[1], proposals[2], *proposals[:1]],
    ):
        topology = build_topology(ordered, image_width=WIDTH, image_height=HEIGHT)
        bands = regularise(topology, touch_tolerance_px=TOUCH_PX)
        grouped: dict[tuple[str, int], set[tuple[str, int]]] = {}
        for junction in topology.junctions:
            for member in junction.members:
                for axis, band_of in (("x", bands.x_band_of), ("y", bands.y_band_of)):
                    grouped.setdefault((axis, band_of[junction.id]), set()).add(
                        (member.proposal_id, member.vertex_index)
                    )
        partitions.append({frozenset(members) for members in grouped.values()})

    assert partitions[0] == partitions[1] == partitions[2]


# --- Inversão de ordem espacial de faixas (lição da Toca, 2026-08-12) ------------------
#
# O prior fraco (`PRIOR_WEIGHT`) e a segunda passada podem mandar uma faixa não-cotada —
# ou até uma faixa determinada por cota confirmada — para o lado errado de uma vizinha.
# O sintoma final é polilinha fechada auto-intersectada ("gravata"), que hoje só o
# auditor de export pega, tarde e opaco. `band_order_violations` é a função pura que
# acusa isso cedo; os testes de `solve_geometry` provam que ela roda de fato.


def _axis_topology(xs: list[float]) -> tuple[Topology, AxisBands]:
    """Topologia mínima: uma junção por posição de eixo x, cada uma sua própria faixa.

    Passa ao largo de `build_topology`/`regularise` de propósito — o alvo aqui é
    `solve_geometry`, não a fusão de vértices (já coberta pelos testes acima).
    """
    junctions = tuple(
        Junction(
            id=index,
            x=x,
            y=0.0,
            members=(VertexRef(proposal_id="vp_" + "0" * 16, vertex_index=index),),
        )
        for index, x in enumerate(xs)
    )
    topology = Topology(junctions=junctions, edges=())
    bands = AxisBands(
        x_band_of=dict(enumerate(range(len(xs)))),
        y_band_of=dict.fromkeys(range(len(xs)), 0),
    )
    return topology, bands


def test_band_order_violations_flags_a_single_adjacent_inversion() -> None:
    traced = {0: 0.0, 1: 100.0, 2: 200.0}
    solved = {0: 0.0, 1: 5.0, 2: 1.0}

    violations = band_order_violations(traced, solved, axis="x", tie_tolerance_px=0.0)

    assert len(violations) == 1
    violation = violations[0]
    assert (violation.first_band, violation.second_band) == (1, 2)
    assert violation.axis == "x"
    assert violation.solved_gap_m == pytest.approx(-4.0)


def test_band_order_violations_skips_a_traced_tie() -> None:
    """Faixas desenhadas coincidentes (o `keep_apart` do Guaxindiba) não têm ordem
    significativa entre si: acusar seria falso positivo."""
    traced = {0: 0.0, 1: 100.0, 2: 100.5}
    solved = {0: 0.0, 1: 5.0, 2: 1.0}

    violations = band_order_violations(traced, solved, axis="x", tie_tolerance_px=1.0)

    assert violations == ()


def test_band_order_violations_ignores_numeric_noise() -> None:
    """O resíduo de micrômetros que o prior deixa (ver `PRIOR_WEIGHT`) não é inversão."""
    traced = {0: 0.0, 1: 100.0}
    solved = {0: 0.0, 1: -1e-9}

    violations = band_order_violations(traced, solved, axis="x", tie_tolerance_px=0.0)

    assert violations == ()


def test_solve_geometry_reports_an_inversion_the_weak_prior_causes() -> None:
    """Fim a fim: cota apertada entre faixas próximas e cota generosa entre faixas
    distantes, no mesmo eixo, inflam o prior da faixa do meio (sem cota própria) até
    ela ultrapassar a vizinha — o defeito real da Toca, com topologia sintética mínima."""
    topology, bands = _axis_topology([0.0, 10.0, 20.0, 1000.0, 1020.0])
    constraints = [
        SpanConstraint(axis="x", first_band=0, second_band=2, value_m=1.0, source_id="ac"),
        SpanConstraint(axis="x", first_band=3, second_band=4, value_m=5.0, source_id="de"),
    ]

    solved = solve_geometry(topology, bands, constraints)

    assert solved is not None
    assert solved.band_order_violations != ()


# --- O lado da restrição vem do traçado (Guaxindiba v2, 2026-08-13) --------------------
#
# O DXF real saiu com o campo do lado errado do muro e os resíduos todos verdes: o resíduo
# reportado é a distância entre as duas faixas, que é absoluta, então a solução espelhada
# fecha em zero. Quem tem de carregar o lado é a restrição — `second - first = +valor`, na
# ordem TRAÇADA das duas faixas. Empate no traçado é a exceção: aí a ordem não significa
# nada e o lado vem do resto do sistema.


def test_a_span_constraint_carries_the_traced_side() -> None:
    """A mesma cota, com a ordem invertida, resolve espelhada — e o |erro| não vê.

    É o antes/depois do defeito: se a emissão errar o lado (ordenar pela junção
    representativa em vez da faixa), o solver obedece e o resíduo absoluto aprova.
    """
    traced = {0: 0.0, 1: 100.0}

    signed = solve_axis(
        traced,
        [SpanConstraint(axis="y", first_band=0, second_band=1, value_m=6.6, source_id="rd_ok")],
        prior_scale=0.066,
    )
    mirrored = solve_axis(
        traced,
        [SpanConstraint(axis="y", first_band=1, second_band=0, value_m=6.6, source_id="rd_esp")],
        prior_scale=0.066,
    )

    assert signed[1] - signed[0] == pytest.approx(6.6, abs=1e-4)
    assert mirrored[1] - mirrored[0] == pytest.approx(-6.6, abs=1e-4)
    # As duas "passam" no resíduo, que é |distância|: por isso o lado tem de vir do traçado.
    assert abs(mirrored[1] - mirrored[0]) == pytest.approx(abs(signed[1] - signed[0]), abs=1e-4)


def test_a_tie_constraint_follows_the_rest_of_the_system_instead_of_its_emitted_side() -> None:
    """O dente do muro: mureta desenhada em cima da borda do campo, 3,30 m fora dela.

    A cadeia com lado (25,90 do campo e 29,20 até a mureta) diz que a mureta está DEPOIS
    da borda direita. A cota do dente é emitida na ordem oposta — é um empate, e a ordem
    dele é ruído de pixel. Sem sinal, ela acompanha a cadeia e o sistema fecha; assinada
    pelo ruído, criaria um conflito que a folha não tem.
    """
    traced = {0: 0.0, 1: 999.5, 2: 1000.0}
    chain = [
        SpanConstraint(axis="x", first_band=0, second_band=2, value_m=25.90, source_id="largura"),
        SpanConstraint(axis="x", first_band=0, second_band=1, value_m=29.20, source_id="total"),
    ]
    tie = SpanConstraint(
        axis="x", first_band=1, second_band=2, value_m=3.30, source_id="dente", signed=False
    )
    orientation = solve_axis(traced, chain, prior_scale=0.0259)

    solved = solve_axis(traced, [*chain, tie], prior_scale=0.0259, orientation=orientation)
    without_orientation = solve_axis(traced, [*chain, tie], prior_scale=0.0259)

    assert solved[2] - solved[0] == pytest.approx(25.90, abs=1e-4)
    assert solved[1] - solved[0] == pytest.approx(29.20, abs=1e-4)
    assert solved[1] - solved[2] == pytest.approx(3.30, abs=1e-4)
    # Sem a orientação, a ordem emitida (ruído) briga com a cadeia e reparte o erro.
    assert without_orientation[2] - without_orientation[0] != pytest.approx(25.90, abs=0.1)


def test_solve_geometry_orients_a_tie_by_the_constraints_that_have_a_side() -> None:
    """Fim a fim: a passada de orientação roda sem o empate, senão ele confirmaria a
    própria ordem arbitrária."""
    topology, bands = _axis_topology([0.0, 999.5, 1000.0])
    constraints = [
        SpanConstraint(axis="x", first_band=0, second_band=2, value_m=25.90, source_id="largura"),
        SpanConstraint(axis="x", first_band=0, second_band=1, value_m=29.20, source_id="total"),
        SpanConstraint(
            axis="x", first_band=1, second_band=2, value_m=3.30, source_id="dente", signed=False
        ),
    ]

    solved = solve_geometry(topology, bands, constraints)

    assert solved is not None
    positions = {index: position[0] for index, position in solved.positions_m.items()}
    assert positions[2] - positions[0] == pytest.approx(25.90, abs=1e-3)
    assert positions[1] - positions[2] == pytest.approx(3.30, abs=1e-3)


def test_solve_geometry_reports_no_violation_for_a_normal_solve() -> None:
    field = _polyline("vp_" + "6" * 16, SKEWED)
    topology = _topology(field)
    bands = regularise(topology)
    traced_x, traced_y = band_positions(topology, bands)
    left, right = sorted(traced_x, key=lambda band: traced_x[band])
    bottom, top = sorted(traced_y, key=lambda band: traced_y[band])
    constraints = [
        SpanConstraint(
            axis="x", first_band=left, second_band=right, value_m=25.90, source_id="rd_w"
        ),
        SpanConstraint(
            axis="y", first_band=bottom, second_band=top, value_m=21.75, source_id="rd_h"
        ),
    ]

    solved = solve_geometry(topology, bands, constraints)

    assert solved is not None
    assert solved.band_order_violations == ()
