"""Resolve coordenadas a partir das cotas, usando o traçado só como estrutura.

O croqui do Guaxindiba está ~32% fora de esquadro. Enquanto as coordenadas saírem de pixel
calibrado, o DXF herda essa distorção inteira — e afinar o encaixe na tinta só deixa o
desenho mais fiel a um papel torto. O engenheiro não quer uma cópia fiel da distorção;
quer o desenho que o croqui tentava descrever.

`STATUS.md` já define o tratamento do risco nº 1 como "cotas e constraints têm precedência
sobre pixels", e o princípio 2 do `AI_FIRST_PRINCIPLES.md` diz que "o geometry engine
resolve coordenadas e constraints". Isto aqui é esse motor; até agora quem resolvia
coordenada era a calibração de pixel.

## Como

Em duas etapas, ambas determinísticas:

1. **Regularização retilínea.** Aresta quase horizontal declara que suas duas junções
   têm o mesmo `y`; quase vertical, o mesmo `x`. Junção que encosta no meio da aresta de
   outro elemento entra na faixa daquela aresta pela mesma tolerância com que a topologia
   funde vértices. Isso agrupa as junções em *faixas* de coordenada. É o que remove a
   anisotropia e o esquadro torto de uma vez, sem mexer em quem liga com quem — a
   topologia sai intacta.

2. **Posicionamento por cota.** Cada faixa vira uma incógnita por eixo. Uma cota confirmada
   entre duas faixas é uma equação `c_j - c_i = valor`, com peso alto, e o sinal dessa
   equação é a ordem TRAÇADA das duas faixas (`SpanConstraint`): a cota manda na distância,
   o lado vem do traçado. A posição traçada de cada faixa entra como equação fraca, só para
   determinar o que nenhuma cota alcança. Mínimos quadrados resolve as duas famílias
   juntas: onde há cota, ela manda; onde não há, o traçado responde.

`generalizar o retângulo` é literalmente isto: `rectangle_solver.solve_rectangle` já
constrói `(0,0) → (w,0) → (w,h) → (0,h)` das cotas confirmadas, mas só sabe quatro arestas.
Aqui a mesma ideia vale para qualquer topologia.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from itertools import pairwise
from typing import Final, NamedTuple

from pydantic import BaseModel, ConfigDict, Field

from .topology import Topology

AXIS_TOLERANCE_DEGREES = 12.0
"""Até quantos graus de um eixo uma aresta ainda é considerada ortogonal.

Traço à mão raramente passa disso quando a intenção era reta; acima, o desvio costuma ser
proposital — uma diagonal de fato, que endireitar destruiria.
"""

PRIOR_WEIGHT = 1e-6
"""Peso da posição traçada perante uma cota confirmada.

Minúsculo de propósito, e o valor importa. A regra do projeto é que a cota tem precedência
sobre o pixel — precedência **exata**, não um meio-termo ponderado. Com peso 0,02 um vão
cotado em 21,75 m saía 21,64: o traçado disputava e ganhava 11 cm.

O prior existe só para dois fins: tornar o sistema não-singular e posicionar faixa que
nenhuma cota alcança. Nesse peso ele resolve as duas coisas e desloca um vão determinado na
ordem de micrômetros. Zerar deixaria singular; subir devolve a disputa.
"""

BAND_ORDER_EPSILON_M: Final = 1e-6
"""Folga de ruído numérico ao comparar gaps resolvidos contra zero.

O prior fraco e a segunda passada deixam resíduo da ordem de micrômetros mesmo num vão
determinado (ver `PRIOR_WEIGHT`); sem esta folga esse ruído virasse falsa inversão.
"""


class SolverModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AxisBands(SolverModel):
    """Junções agrupadas por coordenada compartilhada, um agrupamento por eixo."""

    x_band_of: dict[int, int]
    y_band_of: dict[int, int]

    @property
    def x_band_count(self) -> int:
        return len(set(self.x_band_of.values()))

    @property
    def y_band_count(self) -> int:
        return len(set(self.y_band_of.values()))


class SpanConstraint(SolverModel):
    """Uma distância conhecida entre duas faixas do mesmo eixo, com o lado do traçado.

    Cota manda na distância; o LADO vem do traçado — o mesmo princípio do check de ordem
    (`BandOrderViolation`), aplicado dentro da restrição. `first_band` é a faixa que vem
    antes na ordem **traçada** (posição em pixel menor) e `second_band` a que vem depois,
    de modo que a equação levada ao LSQ é `second - first = +value_m` no espaço de
    solução. Esse espaço é y-down como a imagem: o espelho de Y para CAD acontece depois,
    em `tracing`, sobre a solução inteira, e por isso não afeta este sinal.

    Sem o sinal a restrição valeria |distância| e a solução espelhada — o muro do outro
    lado do campo — fecharia com resíduo ZERO, porque o resíduo reportado é absoluto. Com
    ele, a espelhada erra por duas vezes o valor e aparece como resíduo estourado na cota que
    discorda, em vez de virar polilinha torta lá no export.

    `signed=False` é a exceção do empate: duas faixas cujo gap traçado é menor que a
    tolerância de agrupamento (elementos desenhados coincidentes, declarados distintos por
    `keep_apart`) não têm ordem significativa entre si, e fixar um lado por ruído de pixel
    inventaria informação que o desenho não tem. Nesse caso a restrição volta a valer em
    módulo: o lado é decidido pelo resto do sistema — mesma exceção do check de ordem.
    """

    axis: str = Field(pattern="^[xy]$")
    first_band: int
    second_band: int
    value_m: float = Field(gt=0)
    source_id: str
    signed: bool = True
    """A ordem `first_band → second_band` é a ordem traçada, e o LSQ deve respeitá-la."""


class BandOrderViolation(SolverModel):
    """Um par de faixas adjacentes no traçado cuja solução inverteu a ordem espacial.

    O prior fraco (`PRIOR_WEIGHT`) existe para posicionar faixa sem cota, não para
    decidir de que lado do desenho ela cai — e a segunda passada de prior pode, em
    croqui bem fora de escala, empurrar uma faixa para o lado errado de uma vizinha. O
    sintoma final é polilinha fechada auto-intersectada ("gravata"), que o auditor de
    export só pega tarde; isto aqui é o mesmo defeito pego cedo e nomeado.
    """

    axis: str = Field(pattern="^[xy]$")
    first_band: int
    """Faixa que vinha antes no traçado (posição em pixel menor)."""
    second_band: int
    """Faixa que a solução mandou para trás da anterior."""
    traced_gap_px: float
    solved_gap_m: float
    """Negativo: é o que caracteriza a inversão (`solved[second] - solved[first]`)."""


class _UnionFind:
    def __init__(self, items: Sequence[int]) -> None:
        self._parent = dict.fromkeys(items)
        for item in items:
            self._parent[item] = item

    def find(self, item: int) -> int:
        parent = self._parent[item]
        assert parent is not None
        while parent != item:
            item = parent
            parent = self._parent[item]
            assert parent is not None
        return item

    def union(self, first: int, second: int) -> None:
        root_first, root_second = self.find(first), self.find(second)
        if root_first != root_second:
            self._parent[max(root_first, root_second)] = min(root_first, root_second)

    def groups(self) -> dict[int, int]:
        roots = sorted({self.find(item) for item in self._parent})
        index = {root: position for position, root in enumerate(roots)}
        return {item: index[self.find(item)] for item in self._parent}


class BandSeparation(NamedTuple):
    """Par de elementos declarados distintos, e em que eixo a separação de faixas vale.

    `axis=None` separa nos dois eixos (o formato histórico do aceite). Declarar um eixo
    resolve o caso do dente do muro: a mureta e o patamar precisam ficar em faixas X
    distintas (o recuo horizontal de 3,30/4,80 é o que a folha cota), mas o encontro
    VERTICAL entre a base da mureta e a base do campo é legítimo e amarrá-lo é o que
    mantém o muro no lugar. Separar os dois eixos por causa de um problema de um só
    soltava o sistema do muro inteiro (Guaxindiba v2, 2026-08-13: ~14,5 m de deslize).

    A fusão de VÉRTICES na topologia continua impedida em qualquer caso: vértice fundido
    é um ponto só, e amarraria os dois eixos de uma vez.
    """

    first: str
    second: str
    axis: str | None = None


class _BandUnion(NamedTuple):
    """Candidata a faixa: duas junções que a mesma coordenada de eixo manda andar juntas.

    Vem de dois mecanismos, medidos na mesma unidade (pixels de desalinhamento com o eixo
    agrupado) e varridos na mesma ordem: a aresta quase ortogonal, que manda suas duas
    pontas partilharem coordenada, e o **encosto** de `_touch_unions`.

    A chave de varredura vem à frente dos ids de propósito, para `sorted` produzir
    diretamente a ordem documentada em `regularise`.
    """

    deviation_px: float
    """Desalinhamento com o eixo agrupado — zero é alinhamento perfeito.

    Na aresta é o quanto ela desvia do eixo de ponta a ponta; no encosto é a distância
    perpendicular da junção à aresta em que ela pousa.
    """
    axis_position_px: float
    """Posição média das duas junções no eixo que está sendo agrupado."""
    cross_position_px: float
    """Posição média no outro eixo; só desempata."""
    first: int
    second: int


class _AxisEdge(NamedTuple):
    """Aresta quase ortogonal, com a extensão que ela cobre no eixo transversal.

    É o que uma junção precisa para saber se encosta *no meio* dela, e não apenas perto
    da reta infinita que a contém.
    """

    proposal_id: str
    axis_position_px: float
    cross_min_px: float
    cross_max_px: float
    ends: tuple[int, int]


def _touch_unions(
    topology: Topology,
    edges: Sequence[_AxisEdge],
    owners_of: Mapping[int, frozenset[str]],
    *,
    horizontal: bool,
    tolerance_px: float,
    excluded_owners: frozenset[str],
) -> list[_BandUnion]:
    """Candidatas de encosto: junção que pousa no meio da aresta de OUTRO elemento.

    A topologia funde vértice com vértice, e a regularização agrupa faixa por aresta —
    então um endpoint que encosta no meio de uma aresta perpendicular de outro elemento
    não tem vizinho nenhum e fica solto. Foi o defeito medido no DXF do Guaxindiba v2
    (2026-08-13): a linha de meio de campo vazou 5,12 m pelo fundo do campo e as áreas
    saíram para fora da lateral, todas a poucos pixels do traço em que se apoiam.

    A junção entra como candidata a partilhar a faixa das junções daquela aresta quando
    (a) a coordenada dela no eixo agrupado dista menos que `tolerance_px` da coordenada da
    aresta e (b) a coordenada transversal cai dentro da extensão da aresta, com a mesma
    folga. A tolerância é a mesma com que `build_topology` funde vértices: encosto e fusão
    são o mesmo julgamento de "isto se toca no papel", em pontos diferentes do traço.

    Elemento `freeform` fica de fora dos dois lados — nem gera nem recebe encosto: a
    posição desenhada dele é declaração do revisor, e um encontro casual não pode
    arrastá-la.

    Custo O(junções vezes arestas ortogonais) por eixo. A cena de uma folha tem centenas de
    cada, não milhares; indexar por faixa de coordenada só valeria a pena numa ordem de
    grandeza acima desta.
    """
    if tolerance_px <= 0.0:
        return []
    unions: list[_BandUnion] = []
    for junction in topology.junctions:
        owners = owners_of[junction.id]
        if owners & excluded_owners:
            continue
        axis_position = junction.y if horizontal else junction.x
        cross_position = junction.x if horizontal else junction.y
        for edge in edges:
            if edge.proposal_id in owners:
                continue
            deviation = abs(axis_position - edge.axis_position_px)
            if deviation >= tolerance_px:
                continue
            if not (
                edge.cross_min_px - tolerance_px
                <= cross_position
                <= edge.cross_max_px + tolerance_px
            ):
                continue
            for end in edge.ends:
                other = topology.junction(end)
                other_axis = other.y if horizontal else other.x
                other_cross = other.x if horizontal else other.y
                unions.append(
                    _BandUnion(
                        deviation,
                        (axis_position + other_axis) / 2,
                        (cross_position + other_cross) / 2,
                        min(junction.id, end),
                        max(junction.id, end),
                    )
                )
    return unions


def _group_bands(
    identifiers: Sequence[int],
    owners_of: Mapping[int, frozenset[str]],
    candidates: Sequence[_BandUnion],
    apart_from: Mapping[str, frozenset[str]],
) -> dict[int, int]:
    """Aplica as candidatas de um eixo, recusando a que juntaria dois lados separados.

    Os donos são acumulados por raiz, como em `build_topology`: a separação declarada vale
    para o grupo inteiro, não só para o par direto — um terceiro elemento no meio não pode
    servir de ponte entre os dois lados.
    """
    union = _UnionFind(identifiers)
    root_owners = {identifier: owners_of[identifier] for identifier in identifiers}
    for candidate in sorted(candidates):
        root_first, root_second = union.find(candidate.first), union.find(candidate.second)
        if root_first == root_second:
            continue
        owners_first, owners_second = root_owners[root_first], root_owners[root_second]
        if any(owners_second & apart_from.get(owner, frozenset()) for owner in owners_first):
            continue
        merged = owners_first | owners_second
        union.union(candidate.first, candidate.second)
        root_owners[union.find(candidate.first)] = merged
    return union.groups()


def regularise(
    topology: Topology,
    *,
    angle_tolerance_degrees: float = AXIS_TOLERANCE_DEGREES,
    freeform_proposal_ids: frozenset[str] = frozenset(),
    keep_apart: Sequence[tuple[str, str] | BandSeparation] = (),
    touch_tolerance_px: float = 0.0,
) -> AxisBands:
    """Agrupa junções que uma aresta quase ortogonal obriga a partilhar coordenada.

    Não desloca nada: só declara quem tem de andar junto. O deslocamento acontece quando
    a faixa recebe um valor, o que mantém regularização e posicionamento separáveis e
    testáveis um sem o outro.

    `freeform_proposal_ids` lista elementos que uma pessoa declarou intencionalmente
    não-ortogonais (limite de lote que converge para a rua): as arestas deles não agrupam
    faixas, cada vértice guarda a própria coordenada e o desenho segue como traçado —
    cotável por âncora de vértice, nunca endireitado à força.

    `keep_apart` são os mesmos pares que `build_topology` recebe, e valem aqui pelo mesmo
    motivo: a faixa é a variável do solver, então dois elementos declarados distintos que
    caíssem na mesma faixa continuariam amarrados um ao outro mesmo com os vértices
    separados. Foi o defeito medido no Guaxindiba v2 (2026-08-13) — a faixa vertical da
    direita reunia mureta, muro e patamar por uma ponte da faixa vegetativa, e a cadeia dos
    patamares (9,55+3,86+12,49) disputava com o recuo de 3,30 a MESMA incógnita, espalhando
    o conflito em cinco resíduos de 0,66 m. Nenhuma faixa, no(s) eixo(s) declarado(s) do
    par, pode reunir junções cujos donos contenham os dois lados. Par sem eixo (`axis=None`,
    o formato histórico) separa nos dois. Junção de terceiro continua agrupando com qualquer
    um dos lados — a separação é do par, não do vizinho.

    `touch_tolerance_px` liga as candidatas de **encosto** (`_touch_unions`): junção que
    pousa no meio da aresta de outro elemento partilha a faixa daquela aresta. Zero desliga
    — quem chama sem tolerância só agrupa por aresta desenhada.

    Ordem de varredura (o desempate, quando a mesma faixa-candidata atrai os dois lados de
    um par): as candidatas — de aresta e de encosto, na mesma varredura — são aplicadas da
    mais bem alinhada com o eixo para a mais torta (desvio perpendicular crescente),
    desempatando por posição no eixo agrupado, posição no eixo transversal e, por fim, pelos
    ids das duas junções. Assim quem fica de fora é sempre a candidata mais torta do
    conflito, e o terceiro elemento adere ao lado que já uniu. Sem par declarado a ordem é
    irrelevante — componente conexo não depende da ordem das uniões —, então esta regra só
    decide o caso em conflito.
    """
    identifiers = [junction.id for junction in topology.junctions]
    owners_of = {
        junction.id: frozenset(member.proposal_id for member in junction.members)
        for junction in topology.junctions
    }
    apart_x: dict[str, set[str]] = {}
    apart_y: dict[str, set[str]] = {}
    for item in keep_apart:
        separation = item if isinstance(item, BandSeparation) else BandSeparation(*item)
        for axis, apart_from in (("x", apart_x), ("y", apart_y)):
            if separation.axis not in (None, axis):
                continue
            apart_from.setdefault(separation.first, set()).add(separation.second)
            apart_from.setdefault(separation.second, set()).add(separation.first)
    separated_x = {owner: frozenset(others) for owner, others in apart_x.items()}
    separated_y = {owner: frozenset(others) for owner, others in apart_y.items()}
    tolerance = math.radians(angle_tolerance_degrees)

    horizontal: list[_BandUnion] = []
    vertical: list[_BandUnion] = []
    horizontal_edges: list[_AxisEdge] = []
    vertical_edges: list[_AxisEdge] = []
    for edge in topology.edges:
        if edge.proposal_id in freeform_proposal_ids:
            continue
        start, end = topology.junction(edge.start), topology.junction(edge.end)
        delta_x, delta_y = end.x - start.x, end.y - start.y
        if math.isclose(delta_x, 0.0) and math.isclose(delta_y, 0.0):
            continue
        angle = math.atan2(abs(delta_y), abs(delta_x))
        middle_x, middle_y = (start.x + end.x) / 2, (start.y + end.y) / 2
        ends = (min(edge.start, edge.end), max(edge.start, edge.end))
        if angle <= tolerance:
            # Quase horizontal: as duas pontas partilham y.
            horizontal.append(_BandUnion(abs(delta_y), middle_y, middle_x, *ends))
            horizontal_edges.append(
                _AxisEdge(
                    edge.proposal_id,
                    middle_y,
                    min(start.x, end.x),
                    max(start.x, end.x),
                    ends,
                )
            )
        elif angle >= math.pi / 2 - tolerance:
            # Quase vertical: as duas pontas partilham x.
            vertical.append(_BandUnion(abs(delta_x), middle_x, middle_y, *ends))
            vertical_edges.append(
                _AxisEdge(
                    edge.proposal_id,
                    middle_x,
                    min(start.y, end.y),
                    max(start.y, end.y),
                    ends,
                )
            )

    vertical.extend(
        _touch_unions(
            topology,
            vertical_edges,
            owners_of,
            horizontal=False,
            tolerance_px=touch_tolerance_px,
            excluded_owners=freeform_proposal_ids,
        )
    )
    horizontal.extend(
        _touch_unions(
            topology,
            horizontal_edges,
            owners_of,
            horizontal=True,
            tolerance_px=touch_tolerance_px,
            excluded_owners=freeform_proposal_ids,
        )
    )

    return AxisBands(
        x_band_of=_group_bands(identifiers, owners_of, vertical, separated_x),
        y_band_of=_group_bands(identifiers, owners_of, horizontal, separated_y),
    )


def band_positions(
    topology: Topology, bands: AxisBands
) -> tuple[dict[int, float], dict[int, float]]:
    """Posição traçada de cada faixa: a média das junções que ela reúne."""
    x_members: dict[int, list[float]] = {}
    y_members: dict[int, list[float]] = {}
    for junction in topology.junctions:
        x_members.setdefault(bands.x_band_of[junction.id], []).append(junction.x)
        y_members.setdefault(bands.y_band_of[junction.id], []).append(junction.y)
    return (
        {band: sum(values) / len(values) for band, values in x_members.items()},
        {band: sum(values) / len(values) for band, values in y_members.items()},
    )


def band_order_violations(
    traced: dict[int, float],
    solved: dict[int, float],
    *,
    axis: str,
    tie_tolerance_px: float,
) -> tuple[BandOrderViolation, ...]:
    """Faixas adjacentes no traçado cuja solução inverteu a ordem espacial.

    Pares adjacentes na ordem traçada bastam: qualquer permutação de mais de duas faixas
    produz ao menos uma inversão entre vizinhas. Par cujo gap traçado é menor que
    `tie_tolerance_px` é pulado — faixas desenhadas coincidentes (`keep_apart`) não têm
    ordem significativa entre si, e acusar seria falso positivo.
    """
    ordered = sorted(traced, key=lambda band: traced[band])
    violations: list[BandOrderViolation] = []
    for first, second in pairwise(ordered):
        traced_gap = traced[second] - traced[first]
        if traced_gap < tie_tolerance_px:
            continue
        solved_gap = solved[second] - solved[first]
        if solved_gap < -BAND_ORDER_EPSILON_M:
            violations.append(
                BandOrderViolation(
                    axis=axis,
                    first_band=first,
                    second_band=second,
                    traced_gap_px=traced_gap,
                    solved_gap_m=solved_gap,
                )
            )
    return tuple(violations)


def _solve_least_squares(matrix: list[list[float]], vector: list[float]) -> list[float]:
    """Elimination de Gauss com pivoteamento parcial sobre as equações normais."""
    size = len(matrix)
    augmented = [[*row, vector[index]] for index, row in enumerate(matrix)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) < 1e-12:
            continue
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column] / augmented[column][column]
            for position in range(column, size + 1):
                augmented[row][position] -= factor * augmented[column][position]
    solution = []
    for index in range(size):
        diagonal = augmented[index][index]
        solution.append(augmented[index][size] / diagonal if abs(diagonal) > 1e-12 else 0.0)
    return solution


def solve_axis(
    traced: dict[int, float],
    constraints: Sequence[SpanConstraint],
    *,
    prior_scale: float,
    prior_weight: float = PRIOR_WEIGHT,
    prior_targets: dict[int, float] | None = None,
    orientation: Mapping[int, float] | None = None,
) -> dict[int, float]:
    """Resolve as coordenadas de um eixo em metros.

    A âncora é a faixa de menor coordenada traçada, fixada em zero: o sistema só conhece
    diferenças, e sem uma origem qualquer translação seria solução igualmente válida.

    Cada restrição entra assinada: `second - first = +value_m`, com a ordem que o traçado
    declarou (ver `SpanConstraint`). Uma solução espelhada erra essa equação pelo dobro
    do valor e não sobrevive ao mínimo quadrado enquanto houver alternativa.

    `prior_targets` substitui o alvo do prior (origem + escala global) por posições já
    corrigidas — é a segunda passada de `solve_geometry`, que reposiciona faixas sem cota
    usando a transformação ajustada da primeira solução.

    `orientation` é o lado que uma restrição SEM sinal (`signed=False`, empate no traçado)
    deve seguir: as posições que as restrições COM sinal resolvem sozinhas
    (`_tie_orientation`). Assim o empate nunca puxa o desenho por ruído de pixel — ele
    acompanha o lado que o resto das cotas já decidiu, que é o que "valer em módulo"
    significa dentro de um sistema linear.
    """
    bands = sorted(traced)
    if not bands:
        return {}
    index_of = {band: position for position, band in enumerate(bands)}
    size = len(bands)
    normal = [[0.0] * size for _ in range(size)]
    right = [0.0] * size

    def add_equation(coefficients: dict[int, float], target: float, weight: float) -> None:
        items = [(index_of[band], value) for band, value in coefficients.items()]
        for row, row_value in items:
            for column, column_value in items:
                normal[row][column] += weight * row_value * column_value
            right[row] += weight * row_value * target

    origin = min(bands, key=lambda band: traced[band])
    origin_target = prior_targets[origin] if prior_targets is not None else 0.0
    add_equation({origin: 1.0}, origin_target, 1.0)

    for constraint in constraints:
        if constraint.first_band not in index_of or constraint.second_band not in index_of:
            continue
        first, second = constraint.first_band, constraint.second_band
        if not constraint.signed and orientation is not None:
            estimated = orientation.get(second, 0.0) - orientation.get(first, 0.0)
            # A folga é a mesma do check de ordem: empate que o resto do sistema também
            # deixou coincidente mantém a ordem emitida, em vez de girar com o ruído.
            if estimated < -BAND_ORDER_EPSILON_M:
                first, second = second, first
        add_equation({second: 1.0, first: -1.0}, constraint.value_m, 1.0)

    for band, position in traced.items():
        target = (
            prior_targets[band]
            if prior_targets is not None
            else (position - traced[origin]) * prior_scale
        )
        add_equation({band: 1.0}, target, prior_weight)

    solution = _solve_least_squares(normal, right)
    return {band: solution[index_of[band]] for band in bands}


def _tie_orientation(
    traced: dict[int, float],
    constraints: Sequence[SpanConstraint],
    *,
    scale: float,
    prior_weight: float,
) -> dict[int, float] | None:
    """De que lado o resto do sistema põe cada faixa, para orientar os empates.

    Só existe quando há restrição sem sinal no eixo (`SpanConstraint.signed=False`), e
    roda com as demais — as que têm lado. É a leitura honesta de "a ordem entre estas duas
    faixas não vem do desenho": vem do que as outras cotas já resolveram. Devolve `None`
    quando não há empate nenhum, e aí nada muda no caminho normal.
    """
    if all(constraint.signed for constraint in constraints):
        return None
    signed = [constraint for constraint in constraints if constraint.signed]
    return solve_axis(traced, signed, prior_scale=scale, prior_weight=prior_weight)


def constraint_components(
    traced: dict[int, float], constraints: Sequence[SpanConstraint]
) -> dict[int, int]:
    """Agrupa faixas que cotas confirmadas amarram umas às outras.

    O critério é *distância mútua conhecida*, não posição absoluta. Amarrar à origem seria
    o teste errado — o desenho inteiro flutua em relação a uma origem arbitrária, e as duas
    bordas de um campo cotado em 25,90 m têm distância determinada mesmo que ninguém saiba
    onde o campo cai dentro do lote. Testar contra a origem devolvia zero entidade `exact`
    num desenho cujo campo estava inteiramente cotado.
    """
    union = _UnionFind(sorted(traced))
    for constraint in constraints:
        if constraint.first_band in traced and constraint.second_band in traced:
            union.union(constraint.first_band, constraint.second_band)
    return union.groups()


def determined_bands(traced: dict[int, float], constraints: Sequence[SpanConstraint]) -> set[int]:
    """Faixas cuja distância a alguma outra faixa vem de cota confirmada.

    Serve para não mentir na precisão: só o que a cota determina pode sair `exact`. Faixa
    sozinha no seu componente não é determinada — nenhuma medida a alcança, e a posição
    dela veio do traçado.
    """
    components = constraint_components(traced, constraints)
    sizes: dict[int, int] = {}
    for component in components.values():
        sizes[component] = sizes.get(component, 0) + 1
    return {band for band, component in components.items() if sizes[component] > 1}


def fit_axis_transform(traced: dict[int, float], solved: dict[int, float]) -> tuple[float, float]:
    """Escala e deslocamento que melhor levam o traçado à solução, num eixo.

    Elemento sem junção — círculo, sobretudo — não participa do sistema de faixas. Em vez
    de deixá-lo para trás no espaço de pixels, ele viaja por esta transformação, que é a
    leitura da solução no mesmo espírito de "uma transformação para o que não tem
    informação melhor".
    """
    shared = [band for band in traced if band in solved]
    if len(shared) < 2:
        return (1.0, 0.0)
    mean_traced = sum(traced[band] for band in shared) / len(shared)
    mean_solved = sum(solved[band] for band in shared) / len(shared)
    covariance = sum((traced[band] - mean_traced) * (solved[band] - mean_solved) for band in shared)
    variance = sum((traced[band] - mean_traced) ** 2 for band in shared)
    if variance < 1e-12:
        return (1.0, mean_solved - mean_traced)
    scale = covariance / variance
    return (scale, mean_solved - scale * mean_traced)


def estimate_scale(traced: dict[int, float], constraints: Sequence[SpanConstraint]) -> float | None:
    """Metros por pixel, pela mediana do que as cotas confirmadas já dizem.

    Mediana e não média: uma associação errada distorce a média e passa a governar todas as
    faixas que nenhuma cota alcança.
    """
    ratios: list[float] = []
    for constraint in constraints:
        first, second = traced.get(constraint.first_band), traced.get(constraint.second_band)
        if first is None or second is None:
            continue
        distance = abs(second - first)
        if distance > 1e-9:
            ratios.append(constraint.value_m / distance)
    if not ratios:
        return None
    ratios.sort()
    middle = len(ratios) // 2
    if len(ratios) % 2:
        return ratios[middle]
    return (ratios[middle - 1] + ratios[middle]) / 2


class SolvedGeometry(SolverModel):
    """Resultado do motor: onde cada junção foi parar, e o que a cota de fato determinou."""

    positions_m: dict[int, tuple[float, float]]
    determined_x: frozenset[int]
    determined_y: frozenset[int]
    x_component_of: dict[int, int]
    y_component_of: dict[int, int]
    x_transform: tuple[float, float]
    y_transform: tuple[float, float]
    scale_m_per_px: float
    band_order_violations: tuple[BandOrderViolation, ...] = ()

    def junctions_are_determined(self, bands: AxisBands, junction_ids: Sequence[int]) -> bool:
        """Toda distância interna a este conjunto de junções vem de cota confirmada?

        Exige um único componente por eixo: duas faixas determinadas em componentes
        diferentes têm cada uma a sua medida, mas a distância *entre* elas continua vindo
        do traçado — e uma entidade que as atravessa não é exata.
        """
        if not junction_ids:
            return False
        x_bands = {bands.x_band_of[item] for item in junction_ids}
        y_bands = {bands.y_band_of[item] for item in junction_ids}
        if not x_bands <= self.determined_x or not y_bands <= self.determined_y:
            return False
        return (
            len({self.x_component_of[band] for band in x_bands}) == 1
            and len({self.y_component_of[band] for band in y_bands}) == 1
        )


def solve_geometry(
    topology: Topology,
    bands: AxisBands,
    constraints: Sequence[SpanConstraint],
    *,
    prior_weight: float = PRIOR_WEIGHT,
    order_tie_tolerance_px: float = 0.0,
) -> SolvedGeometry | None:
    """Roda os dois eixos e devolve as junções em metros.

    Devolve `None` quando nenhuma cota confirmada alcança o desenho: sem uma medida sequer
    não existe escala, e inventar uma produziria um DXF em unidade fictícia — pior do que
    não entregar, porque parece pronto.
    """
    traced_x, traced_y = band_positions(topology, bands)
    constraints_x = [item for item in constraints if item.axis == "x"]
    constraints_y = [item for item in constraints if item.axis == "y"]

    scale = estimate_scale(traced_x, constraints_x) or estimate_scale(traced_y, constraints_y)
    if scale is None:
        return None

    # Lado dos empates: quem decide é o RESTO do sistema, então a passada de orientação
    # roda só com as restrições que têm lado. Incluir o próprio empate aqui o faria
    # confirmar a ordem arbitrária com que foi emitido — e um par declarado distinto
    # (dente do muro) cairia do lado de dentro do elemento vizinho, contra a cadeia de
    # cotas que já diz onde ele está. Sem nenhuma cota com lado alcançando o par, as duas
    # faixas ficam coincidentes também aqui e a ordem emitida permanece.
    orientation_x = _tie_orientation(
        traced_x, constraints_x, scale=scale, prior_weight=prior_weight
    )
    orientation_y = _tie_orientation(
        traced_y, constraints_y, scale=scale, prior_weight=prior_weight
    )

    solved_x = solve_axis(
        traced_x,
        constraints_x,
        prior_scale=scale,
        prior_weight=prior_weight,
        orientation=orientation_x,
    )
    solved_y = solve_axis(
        traced_y,
        constraints_y,
        prior_scale=scale,
        prior_weight=prior_weight,
        orientation=orientation_y,
    )

    # Segunda passada: o prior da primeira ancora na origem com escala global, e um croqui
    # fora de escala por região deixa faixa sem cota flutuando longe (a linha de meio do
    # Guaxindiba vazava 2,6 m acima do campo). Reposicionar o prior pela transformação
    # ajustada traçado→solução centra o que não tem cota onde o desenho resolvido espera,
    # sem disputar com nenhuma cota — o peso continua minúsculo.
    for axis_traced, axis_constraints, axis_orientation, solved in (
        (traced_x, constraints_x, orientation_x, solved_x),
        (traced_y, constraints_y, orientation_y, solved_y),
    ):
        fitted_scale, fitted_offset = fit_axis_transform(axis_traced, solved)
        targets = {
            band: fitted_scale * position + fitted_offset for band, position in axis_traced.items()
        }
        refined = solve_axis(
            axis_traced,
            axis_constraints,
            prior_scale=scale,
            prior_weight=prior_weight,
            prior_targets=targets,
            # O lado dos empates é decidido uma vez, antes das duas passadas.
            orientation=axis_orientation,
        )
        solved.update(refined)

    # Inversão de ordem espacial: mínimos quadrados com prior fraco pode mandar uma faixa
    # não-cotada (ou determinada por cota confirmada) para o lado errado de uma vizinha —
    # ver `BandOrderViolation`. Verificado com as posições finais das duas passadas.
    order_violations = (
        *band_order_violations(
            traced_x, solved_x, axis="x", tie_tolerance_px=order_tie_tolerance_px
        ),
        *band_order_violations(
            traced_y, solved_y, axis="y", tie_tolerance_px=order_tie_tolerance_px
        ),
    )

    return SolvedGeometry(
        positions_m={
            junction.id: (
                solved_x[bands.x_band_of[junction.id]],
                solved_y[bands.y_band_of[junction.id]],
            )
            for junction in topology.junctions
        },
        determined_x=frozenset(determined_bands(traced_x, constraints_x)),
        determined_y=frozenset(determined_bands(traced_y, constraints_y)),
        x_component_of=constraint_components(traced_x, constraints_x),
        y_component_of=constraint_components(traced_y, constraints_y),
        x_transform=fit_axis_transform(traced_x, solved_x),
        y_transform=fit_axis_transform(traced_y, solved_y),
        band_order_violations=order_violations,
        scale_m_per_px=scale,
    )
