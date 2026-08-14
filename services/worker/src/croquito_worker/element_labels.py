"""Escreve no desenho o nome que o modelo deu a cada elemento.

A extração já devolve `label` por elemento ("grande área esquerda", "muro vizinho"), e até
aqui esse nome servia só para escolher a layer — o DXF saía com a geometria certa e sem uma
palavra. Quem abre o arquivo no CAD vê linhas anônimas e precisa reconstruir de cabeça o
que cada uma é, que é exatamente o trabalho que o produto existe para poupar.

O rótulo é `derived`: o texto vem de extração conferida, e o ponto onde ele pousa não
carrega alegação métrica — ninguém mede um rótulo. Por isso ele não entra na conta de
aproximação aceita nem pede decisão do revisor.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from itertools import pairwise

from croquito_core.models import (
    ArcGeometry,
    CircleGeometry,
    Entity,
    EntityKind,
    Geometry,
    LayerName,
    LineGeometry,
    Point2D,
    PolylineGeometry,
    Precision,
    Provenance,
    SplineGeometry,
    TextGeometry,
)

LABEL_SOURCE_TYPE = "geometry_extraction_label"
"""Provenance de um rótulo escrito a partir do nome dado pela extração."""

LABEL_SUMMARY_CODE = "ELEMENT_LABEL_FROM_EXTRACTION"

MIN_LABEL_HEIGHT_M = 0.20
"""Piso de altura do texto, em metros. Abaixo disso o CAD não renderiza legível."""

LABEL_HEIGHT_RATIO = 0.012
"""Altura do texto como fração da diagonal do desenho."""

MAX_LABEL_CHARS = 80
"""Rótulo é etiqueta, não descrição: o que passa disso polui a planta.

80 e não 60: a linha de legenda pode carregar a especificação confirmada do elemento
("Portão superior direito — Portão 1,0 x 2,05"), e a coluna da legenda tem espaço."""

GLYPH_WIDTH_RATIO = 0.55
"""Largura média de caractere como fração da altura, no estilo padrão do DXF.

Estimativa, não medida: o CAD escolhe a fonte na abertura. Serve para centralizar e para
detectar sobreposição, dois usos que toleram erro de alguns por cento.
"""

LINE_PITCH_RATIO = 1.6
"""Passo vertical ao empilhar rótulos que colidem, em alturas de texto."""

MAX_DECLUTTER_STEPS = 8
"""Tentativas de desviar antes de aceitar a sobreposição.

Depois disso o rótulo é escrito onde deu: sumir com a etiqueta esconderia o elemento do
engenheiro, e um nome sobreposto ainda é mais informação do que nome nenhum.
"""

BALLOON_SUMMARY_CODE = "ELEMENT_BALLOON"
LEGEND_SUMMARY_CODE = "ELEMENT_LEGEND_ENTRY"

BALLOON_NUMBER_HEIGHT_RATIO = 0.8
"""Altura do número do balão em relação à altura de rótulo do desenho."""

BALLOON_RADIUS_RATIO = 0.75
"""Raio do balão em alturas de número: comporta dois dígitos sem esmagar."""

LEGEND_LINE_PITCH = 1.7
"""Passo vertical entre linhas da legenda, em alturas de texto."""

DIMENSION_TEXT_RATIO = 0.015
"""Altura do texto de cota como fração da diagonal da cena: campo e lote não pedem a mesma."""

MIN_DIMENSION_TEXT_M = 0.25
MAX_DIMENSION_TEXT_M = 1.5


def dimension_text_height(diagonal: float) -> float:
    """Altura de texto de cota proporcional à diagonal do desenho, com piso e teto."""
    return min(MAX_DIMENSION_TEXT_M, max(MIN_DIMENSION_TEXT_M, diagonal * DIMENSION_TEXT_RATIO))


def estimated_width(text: str, height: float) -> float:
    return len(text) * height * GLYPH_WIDTH_RATIO


def _polyline_centroid(points: Sequence[Point2D], *, closed: bool) -> Point2D:
    """Centro de área quando a região fecha; centro do percurso quando não fecha.

    Média simples dos vértices puxaria o rótulo para onde o traçado tem mais detalhe — um
    muro com dez vértices num canto e dois no outro ganharia a etiqueta no canto errado.
    """
    if closed and len(points) >= 3:
        twice_area = 0.0
        centre_x = centre_y = 0.0
        for index, current in enumerate(points):
            following = points[(index + 1) % len(points)]
            cross = current.x * following.y - following.x * current.y
            twice_area += cross
            centre_x += (current.x + following.x) * cross
            centre_y += (current.y + following.y) * cross
        if abs(twice_area) > 1e-12:
            return Point2D(x=centre_x / (3 * twice_area), y=centre_y / (3 * twice_area))
        # Polígono degenerado (área nula) cai no percurso, abaixo.

    total = 0.0
    lengths: list[float] = []
    for start, end in pairwise(points):
        segment = math.hypot(end.x - start.x, end.y - start.y)
        lengths.append(segment)
        total += segment
    if total < 1e-12:
        return points[0]

    walked = 0.0
    for index, segment in enumerate(lengths):
        if walked + segment >= total / 2:
            remaining = (total / 2 - walked) / segment if segment > 1e-12 else 0.0
            start, end = points[index], points[index + 1]
            return Point2D(
                x=start.x + (end.x - start.x) * remaining,
                y=start.y + (end.y - start.y) * remaining,
            )
        walked += segment
    return points[-1]


def geometry_anchor(geometry: Geometry) -> Point2D | None:
    """Onde o rótulo do elemento pousa, ou `None` quando rotular não faz sentido."""
    if isinstance(geometry, LineGeometry):
        return Point2D(
            x=(geometry.start.x + geometry.end.x) / 2,
            y=(geometry.start.y + geometry.end.y) / 2,
        )
    if isinstance(geometry, PolylineGeometry):
        return _polyline_centroid(geometry.points, closed=geometry.closed)
    if isinstance(geometry, CircleGeometry | ArcGeometry):
        return geometry.center
    if isinstance(geometry, SplineGeometry):
        return _polyline_centroid(geometry.fit_points, closed=False)
    # Texto e cota já se explicam; rotular um rótulo só duplicaria palavra na planta.
    return None


def _contains_point(points: Sequence[Point2D], point: Point2D) -> bool:
    """Ponto-em-polígono por ray casting (par/ímpar), sem shapely.

    Convenção padrão half-open em y (`start.y > point.y` difere de `end.y > point.y`):
    um raio horizontal que passa exatamente por um vértice compartilhado por duas arestas
    nunca conta as duas travessias, porque cada vértice pertence ao lado "acima" de uma
    aresta e ao lado "não acima" da outra. Ponto exatamente sobre a borda pode cair para
    qualquer lado da convenção — os casos reais (âncora de outro elemento) ficam bem
    internos ao polígono.
    """
    inside = False
    total = len(points)
    for index in range(total):
        start = points[index]
        end = points[(index + 1) % total]
        crosses = (start.y > point.y) != (end.y > point.y)
        if crosses:
            x_at_point_y = start.x + (point.y - start.y) * (end.x - start.x) / (end.y - start.y)
            if point.x < x_at_point_y:
                inside = not inside
    return inside


def _closest_boundary_point(points: Sequence[Point2D], target: Point2D) -> Point2D:
    """Ponto do perímetro mais próximo de `target`: projeção em cada aresta, clamp em [0,1].

    Percorre as arestas na ordem dos pontos (fechando da última para a primeira, como
    `_polyline_centroid`) e fica com a menor distância. Em empate exato, vence a primeira
    aresta encontrada — determinístico e não depende de tolerância de ponto flutuante.
    """
    total = len(points)
    best_point = points[0]
    best_distance = math.inf
    for index in range(total):
        start = points[index]
        end = points[(index + 1) % total]
        edge_x = end.x - start.x
        edge_y = end.y - start.y
        length_sq = edge_x * edge_x + edge_y * edge_y
        if length_sq < 1e-12:
            candidate = start
        else:
            t = ((target.x - start.x) * edge_x + (target.y - start.y) * edge_y) / length_sq
            t = max(0.0, min(1.0, t))
            candidate = Point2D(x=start.x + edge_x * t, y=start.y + edge_y * t)
        distance = math.hypot(candidate.x - target.x, candidate.y - target.y)
        if distance < best_distance:
            best_distance = distance
            best_point = candidate
    return best_point


def _extent_box(entities: Sequence[Entity]) -> tuple[float, float, float, float] | None:
    xs: list[float] = []
    ys: list[float] = []
    for entity in entities:
        geometry = entity.geometry
        if isinstance(geometry, LineGeometry):
            xs += [geometry.start.x, geometry.end.x]
            ys += [geometry.start.y, geometry.end.y]
        elif isinstance(geometry, PolylineGeometry):
            xs += [point.x for point in geometry.points]
            ys += [point.y for point in geometry.points]
        elif isinstance(geometry, CircleGeometry | ArcGeometry):
            xs += [geometry.center.x - geometry.radius, geometry.center.x + geometry.radius]
            ys += [geometry.center.y - geometry.radius, geometry.center.y + geometry.radius]
        elif isinstance(geometry, SplineGeometry):
            xs += [point.x for point in geometry.fit_points]
            ys += [point.y for point in geometry.fit_points]
    if not xs or not ys:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


def _extent_diagonal(entities: Sequence[Entity]) -> float:
    extent = _extent_box(entities)
    if extent is None:
        return 0.0
    return math.hypot(extent[2] - extent[0], extent[3] - extent[1])


def label_height_for(entities: Sequence[Entity]) -> float:
    """Altura de texto proporcional ao desenho: um campo e um lote não pedem a mesma."""
    return max(MIN_LABEL_HEIGHT_M, _extent_diagonal(entities) * LABEL_HEIGHT_RATIO)


def _fit_text(label: str) -> str | None:
    text = " ".join(label.split())
    if not text:
        return None
    if len(text) > MAX_LABEL_CHARS:
        return text[: MAX_LABEL_CHARS - 1].rstrip() + "…"
    return text


Box = tuple[float, float, float, float]


def _box(insertion: Point2D, text: str, height: float) -> Box:
    return (
        insertion.x,
        insertion.y,
        insertion.x + estimated_width(text, height),
        insertion.y + height,
    )


def _overlaps(first: Box, second: Box) -> bool:
    return not (
        first[2] <= second[0]
        or second[2] <= first[0]
        or first[3] <= second[1]
        or second[3] <= first[1]
    )


def label_entity(
    entity: Entity,
    label: str,
    *,
    height: float,
    source_ids: Sequence[str],
    insertion: Point2D | None = None,
) -> Entity | None:
    """Rótulo de texto para um elemento, ou `None` quando ele não comporta rótulo.

    Sem `insertion`, o texto é centrado no elemento. A entidade `TEXT` do DXF ancora pela
    esquerda, e o contrato não tem campo de alinhamento — então a centralização é feita
    recuando meia largura estimada, o que mantém o schema intocado.
    """
    text = _fit_text(label)
    if text is None:
        return None
    if insertion is None:
        anchor = geometry_anchor(entity.geometry)
        if anchor is None:
            return None
        insertion = Point2D(x=anchor.x - estimated_width(text, height) / 2, y=anchor.y - height / 2)
    return Entity(
        kind=EntityKind.TEXT,
        layer=LayerName.TEXTOS,
        precision=Precision.DERIVED,
        geometry=TextGeometry(insertion=insertion, text=text, height=height, rotation=0.0),
        provenance=Provenance(
            source_type=LABEL_SOURCE_TYPE,
            source_ids=[*source_ids, str(entity.id)][:20],
            summary_code=LABEL_SUMMARY_CODE,
        ),
    )


def _declutter(insertion: Point2D, text: str, height: float, placed: list[Box]) -> Point2D:
    """Afasta o rótulo na vertical até achar espaço livre.

    Marcações concêntricas de um campo — círculo central, meio de campo, marca do pênalti —
    têm centroides quase coincidentes, e sem isto os nomes viram um borrão no meio do
    desenho. Alterna para cima e para baixo para não empurrar a pilha toda para um lado.
    """
    for step in range(MAX_DECLUTTER_STEPS + 1):
        offset = ((step + 1) // 2) * height * LINE_PITCH_RATIO * (1 if step % 2 else -1)
        candidate = Point2D(x=insertion.x, y=insertion.y + offset)
        box = _box(candidate, text, height)
        if not any(_overlaps(box, other) for other in placed):
            placed.append(box)
            return candidate
    placed.append(_box(insertion, text, height))
    return insertion


def label_entities(
    labelled: Sequence[tuple[Entity, str]],
    *,
    scene_entities: Sequence[Entity] | None = None,
    source_ids: Sequence[str] = (),
) -> list[Entity]:
    """Rótulos para os elementos nomeados, sem sobreposição, dimensionados pelo desenho.

    `scene_entities` permite medir a extensão sobre a cena inteira quando só uma parte dela
    é rotulada — senão a altura do texto oscilaria conforme o recorte.

    A ordem de entrada decide quem fica no lugar de origem, então rotular sempre na mesma
    ordem mantém o desenho reproduzível entre execuções.
    """
    reference = (
        list(scene_entities) if scene_entities is not None else [item for item, _ in labelled]
    )
    height = label_height_for(reference)
    placed: list[Box] = []
    labels: list[Entity] = []
    for entity, label in labelled:
        text = _fit_text(label)
        anchor = geometry_anchor(entity.geometry)
        if text is None or anchor is None:
            continue
        centred = Point2D(x=anchor.x - estimated_width(text, height) / 2, y=anchor.y - height / 2)
        created = label_entity(
            entity,
            label,
            height=height,
            source_ids=source_ids,
            insertion=_declutter(centred, text, height, placed),
        )
        if created is not None:
            labels.append(created)
    return labels


def boxes_overlap(first: Box, second: Box) -> bool:
    """Interseção de caixas de texto; público porque cota e rótulo partilham a folha."""
    return _overlaps(first, second)


def _free(box: Box, placed: Sequence[Box]) -> bool:
    return not any(_overlaps(box, other) for other in placed)


_BALLOON_SEARCH_RING = [
    (0, 0),
    (0, 1),
    (1, 0),
    (0, -1),
    (-1, 0),
    (1, 1),
    (-1, 1),
    (1, -1),
    (-1, -1),
    (0, 2),
    (2, 0),
    (0, -2),
    (-2, 0),
    (2, 2),
    (-2, 2),
    (2, -2),
    (-2, -2),
]
"""Ordem determinística de tentativa ao afastar um balão de uma vaga ocupada."""


def _balloon_centre(
    base: tuple[float, float], radius: float, placed: Sequence[Box]
) -> tuple[float, float]:
    pitch = radius * 2.4
    for offset_x, offset_y in _BALLOON_SEARCH_RING:
        centre = (base[0] + offset_x * pitch, base[1] + offset_y * pitch)
        box = (centre[0] - radius, centre[1] - radius, centre[0] + radius, centre[1] + radius)
        if _free(box, placed):
            return centre
    # Último recurso: junto ao elemento. O balão é pequeno; sobrepor um traço ainda é
    # melhor do que um número longe do que ele nomeia.
    return base


def _annotation_provenance(
    summary_code: str, source_ids: Sequence[str], entity: Entity
) -> Provenance:
    return Provenance(
        source_type=LABEL_SOURCE_TYPE,
        source_ids=[*source_ids, str(entity.id)][:20],
        summary_code=summary_code,
    )


def place_labels(
    labelled: Sequence[tuple[Entity, str]],
    *,
    scene_entities: Sequence[Entity] | None = None,
    obstacles: Sequence[Box] = (),
    source_ids: Sequence[str] = (),
    height_reference: Sequence[Entity] | None = None,
) -> list[Entity]:
    """Todo elemento rotulado vira balão numerado junto a ele + linha na legenda.

    A regra veio de prancha real: rótulo pousado no centroide empilha tudo no meio de um
    desenho denso (marcações de campo são concêntricas) e cobre a geometria; nome completo
    escrito dentro da região colidia de outra forma (Guaxindiba, "Patamar de concreto
    esquerdo" — decisão de produto 2026-08-13 aposentou o nome inline em favor de
    consistência keynote). Aqui:

    - todo elemento de `labelled` recebe um balão pequeno (círculo + número) junto a ele,
      com desvio determinístico contra tudo que já ocupa a folha (`obstacles` inclui texto
      de cota e carimbo);
    - os nomes dos balões vão para uma legenda em coluna à direita do desenho.

    Elemento CONTÊINER (polilinha fechada cuja região abrange a âncora de outro elemento —
    o Alambrado do Guaxindiba, que envolve o campo inteiro) é exceção à âncora de centroide:
    pousar o balão no meio da região o esconderia atrás de tudo que ela contém. Nesse caso o
    balão pousa na projeção do centroide sobre a própria borda do polígono — o número nomeia
    o contorno, não o conteúdo. Só `PolylineGeometry` fechada é candidata a contêiner;
    círculo, arco e spline mantêm a âncora de sempre (borda de curva é ambígua sem caso real
    que peça a regra).
    """
    reference = (
        list(scene_entities) if scene_entities is not None else [item for item, _ in labelled]
    )
    reference_anchors = [(item.id, geometry_anchor(item.geometry)) for item in reference]
    # A tipografia segue a planta; a âncora da legenda segue a folha inteira. Sem essa
    # separação, uma coluna de detalhes à direita inflaria a fonte de todos os rótulos.
    height = label_height_for(height_reference if height_reference is not None else reference)
    number_height = height * BALLOON_NUMBER_HEIGHT_RATIO
    radius = number_height * BALLOON_RADIUS_RATIO
    placed: list[Box] = list(obstacles)
    results: list[Entity] = []

    ballooned: list[tuple[Entity, str, Point2D]] = []
    for entity, label in labelled:
        text = _fit_text(label)
        anchor = geometry_anchor(entity.geometry)
        if text is None or anchor is None:
            continue
        geometry = entity.geometry
        if isinstance(geometry, PolylineGeometry) and geometry.closed and len(geometry.points) >= 3:
            is_container = any(
                other_anchor is not None
                and other_id != entity.id
                and _contains_point(geometry.points, other_anchor)
                for other_id, other_anchor in reference_anchors
            )
            if is_container:
                anchor = _closest_boundary_point(geometry.points, anchor)
        ballooned.append((entity, text, anchor))

    legend: list[tuple[int, str]] = []
    for number, (entity, text, anchor) in enumerate(ballooned, start=1):
        base = (anchor.x + radius * 1.8, anchor.y + radius * 1.8)
        centre = _balloon_centre(base, radius, placed)
        placed.append(
            (centre[0] - radius, centre[1] - radius, centre[0] + radius, centre[1] + radius)
        )
        provenance = _annotation_provenance(BALLOON_SUMMARY_CODE, source_ids, entity)
        results.append(
            Entity(
                kind=EntityKind.CIRCLE,
                layer=LayerName.TEXTOS,
                precision=Precision.DERIVED,
                geometry=CircleGeometry(center=Point2D(x=centre[0], y=centre[1]), radius=radius),
                provenance=provenance,
            )
        )
        digits = str(number)
        results.append(
            Entity(
                kind=EntityKind.TEXT,
                layer=LayerName.TEXTOS,
                precision=Precision.DERIVED,
                geometry=TextGeometry(
                    insertion=Point2D(
                        x=centre[0] - estimated_width(digits, number_height) / 2,
                        y=centre[1] - number_height / 2,
                    ),
                    text=digits,
                    height=number_height,
                    rotation=0.0,
                ),
                provenance=provenance,
            )
        )
        legend.append((number, text))

    extent = _extent_box(reference)
    if extent is not None and legend:
        legend_height = height * 0.9
        # A coluna começa depois de tudo que já ocupa a direita da folha — inclusive as
        # caixas de texto de cota, que se estendem além da geometria.
        right_edge = max(extent[2], max((box[2] for box in obstacles), default=extent[2]))
        legend_x = right_edge + height * 2
        legend_y = extent[3] - legend_height
        for number, text in legend:
            entry = f"({number})  {text}"
            results.append(
                Entity(
                    kind=EntityKind.TEXT,
                    layer=LayerName.TEXTOS,
                    precision=Precision.DERIVED,
                    geometry=TextGeometry(
                        insertion=Point2D(x=legend_x, y=legend_y),
                        text=entry[:500],
                        height=legend_height,
                        rotation=0.0,
                    ),
                    provenance=Provenance(
                        source_type=LABEL_SOURCE_TYPE,
                        source_ids=list(source_ids)[:20] or ["legend"],
                        summary_code=LEGEND_SUMMARY_CODE,
                    ),
                )
            )
            legend_y -= legend_height * LEGEND_LINE_PITCH
    return results
