"""Descobre quais vértices do traçado são o mesmo canto.

A extração é instruída a fazer vértices que se encontram no papel compartilharem
coordenada, e o schema carrega isso. Mas daí em diante o sistema achatava a informação:
a associação reduzia a proposta a uma distância escalar e a amarração de cota reescalava
cada linha em torno do próprio centro, separando cantos que eram um só. Polígono aberto no
DXF é consequência disso, não do traçado.

Aqui a adjacência vira estrutura explícita: um `Junction` é um canto do desenho, e as
arestas dizem quem liga a quem. Com isso, mover um canto move tudo que o encosta — que é a
diferença entre editar um desenho e editar uma pilha de segmentos soltos.

Trabalha em pixels, antes de qualquer escala: é topologia, não medida.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence

from pydantic import BaseModel, ConfigDict, Field

from .vision import PixelLine, PixelPoint, PixelPolyline, VisionProposal

JUNCTION_TOLERANCE_RATIO = 0.010
"""Raio de fusão como fração da diagonal da imagem.

O traço à mão tem espessura e a coordenada do modelo é aproximada, então cantos que se
encontram no papel chegam próximos, não idênticos. Largo demais funde elementos vizinhos;
estreito demais mantém o canto partido, que é o defeito que este módulo existe para curar.
"""


class TopologyModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class VertexRef(TopologyModel):
    proposal_id: str
    vertex_index: int = Field(ge=0)


class Junction(TopologyModel):
    """Um canto do desenho, e todos os vértices de traçado que caem nele."""

    id: int = Field(ge=0)
    x: float
    y: float
    members: tuple[VertexRef, ...] = Field(min_length=1)

    @property
    def shared(self) -> bool:
        """Verdadeiro quando mais de um elemento encosta aqui."""
        return len({member.proposal_id for member in self.members}) > 1


class Edge(TopologyModel):
    """Um segmento de traçado, já expresso entre junções."""

    proposal_id: str
    segment_index: int = Field(ge=0)
    start: int = Field(ge=0)
    end: int = Field(ge=0)


class Topology(TopologyModel):
    junctions: tuple[Junction, ...] = ()
    edges: tuple[Edge, ...] = ()

    def junction(self, identifier: int) -> Junction:
        return self.junctions[identifier]

    def edges_at(self, junction_id: int) -> tuple[Edge, ...]:
        return tuple(edge for edge in self.edges if junction_id in (edge.start, edge.end))

    @property
    def shared_junction_count(self) -> int:
        return sum(1 for junction in self.junctions if junction.shared)


class _UnionFind:
    def __init__(self, size: int) -> None:
        self._parent = list(range(size))

    def find(self, item: int) -> int:
        while self._parent[item] != item:
            self._parent[item] = self._parent[self._parent[item]]
            item = self._parent[item]
        return item

    def union(self, first: int, second: int) -> None:
        root_first, root_second = self.find(first), self.find(second)
        if root_first != root_second:
            self._parent[max(root_first, root_second)] = min(root_first, root_second)


def _vertices(proposal: VisionProposal) -> list[tuple[float, float]]:
    """Vértices do traçado, na ordem em que formam segmentos.

    Círculo fica de fora: não tem canto, e forçá-lo a um vértice inventaria adjacência.
    """
    geometry = proposal.geometry
    if isinstance(geometry, PixelLine):
        return [(geometry.start.x, geometry.start.y), (geometry.end.x, geometry.end.y)]
    if isinstance(geometry, PixelPolyline):
        return [(point.x, point.y) for point in geometry.points]
    return []


def _segments(proposal: VisionProposal, count: int) -> list[tuple[int, int]]:
    pairs = [(index, index + 1) for index in range(count - 1)]
    geometry = proposal.geometry
    if isinstance(geometry, PixelPolyline) and geometry.closed and count >= 3:
        pairs.append((count - 1, 0))
    return pairs


def build_topology(
    proposals: Sequence[VisionProposal],
    *,
    image_width: int,
    image_height: int,
    tolerance_ratio: float = JUNCTION_TOLERANCE_RATIO,
    keep_apart: Sequence[tuple[str, str]] = (),
) -> Topology:
    """Funde vértices próximos em junções e reexprime os segmentos entre elas.

    Dois vértices do **mesmo** elemento nunca se fundem: um elemento pequeno inteiro dentro
    da tolerância — marca de pênalti, degrau — colapsaria num ponto e desapareceria do
    desenho. Fechamento de polilinha já é representado pelo segmento de retorno, não pela
    fusão do primeiro vértice com o último.

    `keep_apart` lista pares de elementos que uma pessoa declarou distintos apesar de
    desenhados coincidentes — no Guaxindiba, a borda do patamar direito e a mureta estão
    uma sobre a outra na folha, mas as cotas as põem a 3,30 m de distância. Fundi-las
    tornaria o sistema de cotas insolúvel; separá-las é decisão de quem conhece o lugar,
    nunca palpite do detector.
    """
    tolerance = math.hypot(image_width, image_height) * tolerance_ratio
    keep_apart_set = {frozenset(pair) for pair in keep_apart}

    owners: list[str] = []
    vertex_index_of: list[int] = []
    points: list[tuple[float, float]] = []
    spans: list[tuple[VisionProposal, list[int]]] = []
    for proposal in proposals:
        vertices = _vertices(proposal)
        if len(vertices) < 2:
            continue
        indices: list[int] = []
        for vertex_index, vertex in enumerate(vertices):
            indices.append(len(points))
            points.append(vertex)
            owners.append(proposal.id)
            vertex_index_of.append(vertex_index)
        spans.append((proposal, indices))

    union = _UnionFind(len(points))
    # Donos por raiz: a separação declarada vale para o grupo inteiro, não só para o
    # par direto — um terceiro elemento no mesmo canto não pode servir de ponte.
    root_owners: dict[int, set[str]] = {index: {owners[index]} for index in range(len(points))}

    def union_allowed(root_first: int, root_second: int) -> bool:
        for pair in keep_apart_set:
            first_owner, second_owner = tuple(pair)
            if (
                first_owner in root_owners[root_first] and second_owner in root_owners[root_second]
            ) or (
                second_owner in root_owners[root_first] and first_owner in root_owners[root_second]
            ):
                return False
        return True

    for first in range(len(points)):
        for second in range(first + 1, len(points)):
            if owners[first] == owners[second]:
                continue
            if math.dist(points[first], points[second]) > tolerance:
                continue
            root_first, root_second = union.find(first), union.find(second)
            if root_first == root_second or not union_allowed(root_first, root_second):
                continue
            merged_owners = root_owners[root_first] | root_owners[root_second]
            union.union(first, second)
            root_owners[union.find(first)] = merged_owners

    groups: dict[int, list[int]] = {}
    for index in range(len(points)):
        groups.setdefault(union.find(index), []).append(index)

    junction_of: dict[int, int] = {}
    junctions: list[Junction] = []
    for identifier, (_root, members) in enumerate(sorted(groups.items())):
        for member in members:
            junction_of[member] = identifier
        junctions.append(
            Junction(
                id=identifier,
                x=sum(points[member][0] for member in members) / len(members),
                y=sum(points[member][1] for member in members) / len(members),
                members=tuple(
                    VertexRef(proposal_id=owners[member], vertex_index=vertex_index_of[member])
                    for member in members
                ),
            )
        )

    edges: list[Edge] = []
    for proposal, indices in spans:
        for segment_index, (start, end) in enumerate(_segments(proposal, len(indices))):
            first, second = junction_of[indices[start]], junction_of[indices[end]]
            if first != second:
                edges.append(
                    Edge(
                        proposal_id=proposal.id,
                        segment_index=segment_index,
                        start=first,
                        end=second,
                    )
                )

    return Topology(junctions=tuple(junctions), edges=tuple(edges))


def junction_positions(topology: Topology) -> dict[int, tuple[float, float]]:
    return {junction.id: (junction.x, junction.y) for junction in topology.junctions}


def rebuild_proposal(
    proposal: VisionProposal,
    topology: Topology,
    positions: dict[int, tuple[float, float]],
) -> VisionProposal:
    """Reescreve a geometria de um elemento a partir das posições das junções.

    É o caminho de volta: o solver move junções, e todo elemento que encosta nelas segue
    junto. Sem isto, mover um canto abriria o polígono vizinho — o defeito de origem.
    """
    vertex_junction: dict[int, int] = {}
    for junction in topology.junctions:
        for member in junction.members:
            if member.proposal_id == proposal.id:
                vertex_junction[member.vertex_index] = junction.id

    geometry = proposal.geometry
    if isinstance(geometry, PixelLine):
        start = positions.get(vertex_junction.get(0, -1))
        end = positions.get(vertex_junction.get(1, -1))
        if start is None or end is None:
            return proposal
        return proposal.model_copy(
            update={
                "geometry": PixelLine(
                    start=_point(start),
                    end=_point(end),
                )
            }
        )
    if isinstance(geometry, PixelPolyline):
        moved = []
        for index in range(len(geometry.points)):
            position = positions.get(vertex_junction.get(index, -1))
            if position is None:
                moved.append(geometry.points[index])
            else:
                moved.append(_point(position))
        return proposal.model_copy(
            update={"geometry": geometry.model_copy(update={"points": moved})}
        )
    return proposal


def _point(position: tuple[float, float]) -> PixelPoint:
    # Coordenada de pixel não é negativa no contrato; o solver pode empurrar um canto para
    # fora da folha, e recortar em zero é preferível a estourar a validação.
    return PixelPoint(x=max(0.0, position[0]), y=max(0.0, position[1]))


def rebuild_all(
    proposals: Iterable[VisionProposal],
    topology: Topology,
    positions: dict[int, tuple[float, float]],
) -> list[VisionProposal]:
    return [rebuild_proposal(proposal, topology, positions) for proposal in proposals]
