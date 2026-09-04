"""Traçado em lote: da extração aceita à cena métrica, com a cota mandando.

O croqui de mão é fora de escala por natureza — no Guaxindiba o patamar cotado em
14,50 m está desenhado com menos da metade disso. Projetar pixels calibrados reproduz
fielmente essa distorção; o engenheiro quer o desenho que o croqui tentava descrever.

Este módulo liga as peças que já existem, nesta ordem:

1. `topology.build_topology` transforma as propostas aceitas num grafo de junções.
2. `geometry_solver.regularise` agrupa junções em faixas ortogonais (remove anisotropia
   e esquadro torto sem mexer em quem liga com quem).
3. Cada leitura confirmada **com associação explícita** vira um `SpanConstraint`; a
   associação continua obrigatória — proximidade em pixels nunca é associação. A cota
   manda na distância e o LADO vem do traçado: a restrição é assinada pela ordem traçada
   das duas faixas, então a solução espelhada erra por duas vezes a cota em vez de fechar
   verde (o resíduo reportado é absoluto).
4. `geometry_solver.solve_geometry` resolve as coordenadas em metros: onde há cota, ela
   manda; onde não há, o traçado responde.
5. O eixo Y é espelhado ao final: pixel cresce para baixo, DXF cresce para cima. A
   `SimilarityTransform` é incapaz de espelhar (determinante sempre positivo) — este foi
   o defeito que entregou um Guaxindiba de cabeça para baixo, e aqui ele vira regra fixa.

Precisão declarada, nunca inventada: entidade cujas distâncias internas são todas
cotadas sai `exact`; o resto permanece `approximate` na layer `APROXIMADO`, aceito em
lote por uma pessoa identificada. Nada contorna `ensure_exportable`.

Identidade transportada, nunca cunhada aqui: a entidade criada a partir de proposta que
uma pessoa declarou ser um elemento na revisão de leitura nasce com o `element_ref` e o
rótulo dela (ADR-0063, decisão 2). O traçado não declara identidade nenhuma — ele carrega
para a cena o que já foi afirmado uma etapa antes, e o ato pós-cena continua valendo para
o que a revisão não identificou, no mesmo contador.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from itertools import combinations
from pathlib import Path
from typing import Any, Final, Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from croquito_core.models import (
    ELEMENT_LABEL_MAX_LENGTH,
    ELEMENT_REF_PATTERN,
    CircleGeometry,
    Constraint,
    DiameterDimensionGeometry,
    DimensionGeometry,
    Entity,
    EntityKind,
    Issue,
    IssueSeverity,
    LayerName,
    LineGeometry,
    Measurement,
    MeasurementKind,
    Point2D,
    PolylineGeometry,
    Precision,
    Provenance,
    SceneRevision,
    TextGeometry,
    UnitCode,
)
from croquito_worker.criteria import (
    ScopeCriterion,
    apply_criteria_declarations,
    scope_criteria_issues,
)
from croquito_worker.dimension_annotation import NOTE_SOURCE_TYPE
from croquito_worker.element_labels import (
    boxes_overlap,
    dimension_text_height,
    estimated_width,
    place_labels,
)
from croquito_worker.geometry_solver import (
    AxisBands,
    BandSeparation,
    SolvedGeometry,
    SpanConstraint,
    band_positions,
    regularise,
    solve_geometry,
)
from croquito_worker.io_utils import atomic_write_text
from croquito_worker.rectangle_solver import SolverResidual
from croquito_worker.review import (
    DimensionReading,
    ReadingStatus,
    ReviewPacket,
    SceneApproval,
)
from croquito_worker.topology import JUNCTION_TOLERANCE_RATIO, Topology, build_topology
from croquito_worker.vision import (
    PixelCircle,
    PixelLine,
    PixelPoint,
    PixelPolyline,
    VisionProposal,
)

TRACER_VERSION: Final = "trace-solver-v1"

GENERAL_NOTE_TARGET: Final = "carimbo"
"""Alvo de nota que não ancora em elemento: vira nota geral, acima do título da prancha."""

LEGEND_NOTE_PREFIX: Final = "legenda:"
"""Alvo de nota que vai para a linha de legenda do elemento, em vez de flutuar no desenho.

Serve para especificação que polui perto do elemento (Portão 1,0 x 2,05 disputando
espaço com o muro): no desenho ficam só a cota e o balão; o texto viaja com o nome."""

CAD_FONT_SAFETY = 1.35
"""Folga da caixa de colisão de texto: a fonte do CAD é mais larga que a estimativa."""

SHORT_NOTE_MAX_CHARS = 10
SHORT_NOTE_HEIGHT_RATIO = 0.6
"""Nota curta (h=0,20…) é informação secundária: fonte menor polui menos a prancha."""

NOTE_TEXT_HEIGHT_RATIO = 0.8
"""Altura das notas ancoradas em relação ao texto de cota."""

TRACE_SOURCE_TYPE = "batch_accepted_trace+geometry-solver"
"""Provenance de geometria traçada aceita em lote e resolvida pelo motor de cotas."""

SPAN_SOURCE_TYPE = "human_confirmed_reading+explicit_association"
"""Mesma origem que o solver retangular usa para cota confirmada e associada."""

NOTE_HEIGHT_RATIO = 0.014
"""Altura das notas do carimbo como fração da diagonal do desenho."""

TITLE_HEIGHT_RATIO = 0.035
"""Altura do título do carimbo como fração da diagonal do desenho."""


class TraceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)


class TraceDetailGroup(TraceModel):
    """Detalhe do croqui resolvido independente da planta (painel, arquibancada).

    O croqui desenha detalhes fora de escala ao lado da planta; num traçado único as
    cotas deles explodiriam sobre a planta. Cada grupo tem topologia, escala e origem
    próprias e é desenhado numa coluna de detalhes com moldura e título. `solve` faz a
    cota mandar dentro do grupo (elevações ortogonais); `sketch` mantém o desenho como
    está na escala da planta, sempre `approximate`, e as cotas do grupo viram notas.
    """

    detail_id: str = Field(pattern=r"^[A-Z][A-Z0-9]{0,7}$")
    title: str = Field(min_length=1, max_length=120)
    proposal_ids: list[str] = Field(min_length=1)
    mode: Literal["solve", "sketch"] = "solve"


class KeepApartPair(TraceModel):
    """Par mantido separado com o eixo da separação declarado.

    Formato aditivo: `["vp_a", "vp_b"]` continua valendo e significa os dois eixos. O eixo
    existe porque o problema costuma ser de um só: no Guaxindiba a mureta e o patamar
    precisam ficar em faixas X distintas (é o dente de 3,30/4,80 que a folha cota), mas o
    encontro VERTICAL da base da mureta com a base do campo é legítimo — separar também em
    Y soltou o sistema do muro inteiro e ele deslizou 14,5 m para baixo do campo.
    """

    first: str = Field(min_length=1)
    second: str = Field(min_length=1)
    # `None` mantém o significado histórico: separa nos dois eixos.
    axis: Literal["x", "y"] | None = None


def keep_apart_proposal_ids(pair: tuple[str, str] | KeepApartPair) -> tuple[str, str]:
    """Os dois elementos de um par, seja qual for o formato declarado."""
    if isinstance(pair, KeepApartPair):
        return (pair.first, pair.second)
    return pair


class TraceAcceptance(TraceModel):
    """Aceite em lote do traçado, por uma pessoa identificada.

    É o ato humano que a regra de export exige para geometria `approximate`: quem aceitou,
    quando, e exatamente quais propostas. Sem ele o traçado não vira cena.
    """

    acceptance_id: str = Field(pattern=r"^ta_[a-f0-9]{16}$")
    reviewer_id: str = Field(min_length=1, max_length=120)
    reviewer_role: Literal["engineer", "architect", "domain_reviewer"]
    decided_at: datetime
    note: str | None = Field(default=None, max_length=500)
    proposal_ids: list[str] = Field(min_length=1)
    # Regiões que a folha marca como hachuradas (ex.: área vegetativa). Declaração
    # humana, nunca inferência de rótulo.
    hatch_proposal_ids: list[str] = Field(default_factory=list)
    # Pares de elementos desenhados coincidentes que o revisor declara distintos
    # (borda do patamar sobre a mureta): os vértices deles nunca se fundem na topologia.
    # `["vp_a", "vp_b"]` separa nos dois eixos; a forma objeto declara o eixo do problema.
    keep_apart_pairs: list[tuple[str, str] | KeepApartPair] = Field(default_factory=list)
    # Elementos aceitos que dispensam balão e legenda (marcações padrão de campo:
    # áreas, meia-luas, traves…) — a geometria entra, o nome não polui a prancha.
    unlabelled_proposal_ids: list[str] = Field(default_factory=list)
    # Elementos declarados intencionalmente não-ortogonais (limite do lote que converge
    # para a rua): a regularização não agrupa as arestas deles em faixas — o contorno
    # segue como desenhado e cada cota de afastamento ancora no vértice mais próximo da
    # evidência. Declaração de quem conhece o lugar, nunca inferência de ângulo.
    freeform_proposal_ids: list[str] = Field(default_factory=list)
    # Detalhes do croqui resolvidos independentes da planta, cada um com escala própria.
    detail_groups: list[TraceDetailGroup] = Field(default_factory=list)

    @field_validator("decided_at")
    @classmethod
    def validate_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("decided_at exige timezone")
        return value

    @model_validator(mode="after")
    def validate_ids(self) -> TraceAcceptance:
        if len(self.proposal_ids) != len(set(self.proposal_ids)):
            raise ValueError("proposta aceita em duplicidade")
        if not set(self.hatch_proposal_ids) <= set(self.proposal_ids):
            raise ValueError("hachura só pode marcar proposta aceita")
        for pair in self.keep_apart_pairs:
            first, second = keep_apart_proposal_ids(pair)
            if first == second:
                raise ValueError("keep_apart exige dois elementos distintos")
            if first not in self.proposal_ids or second not in self.proposal_ids:
                raise ValueError("keep_apart só pode separar propostas aceitas")
        if not set(self.unlabelled_proposal_ids) <= set(self.proposal_ids):
            raise ValueError("unlabelled só pode marcar proposta aceita")
        if not set(self.freeform_proposal_ids) <= set(self.proposal_ids):
            raise ValueError("freeform só pode marcar proposta aceita")
        detail_ids = [group.detail_id for group in self.detail_groups]
        if len(detail_ids) != len(set(detail_ids)):
            raise ValueError("detail_id de grupo de detalhe em duplicidade")
        grouped: set[str] = set()
        for group in self.detail_groups:
            members = set(group.proposal_ids)
            if not members <= set(self.proposal_ids):
                raise ValueError("grupo de detalhe só pode conter proposta aceita")
            if members & grouped:
                raise ValueError("proposta em mais de um grupo de detalhe")
            grouped |= members
        if grouped and not (set(self.proposal_ids) - grouped):
            raise ValueError("a planta principal não pode ficar vazia: todo aceite em grupos")
        return self

    def keep_apart_separations(self) -> list[BandSeparation]:
        """Os pares como a regularização os usa: com o eixo declarado (ou os dois)."""
        return [
            BandSeparation(pair.first, pair.second, pair.axis)
            if isinstance(pair, KeepApartPair)
            else BandSeparation(*pair)
            for pair in self.keep_apart_pairs
        ]


class TraceElementDeclaration(TraceModel):
    """Uma identidade de elemento declarada na REVISÃO, sobre propostas (ADR-0063, D1/D2).

    Chega ao traçado já cunhada: o `element_ref` nasceu no ato humano da revisão
    (`POST /v1/jobs/{job_id}/review/elements`), no namespace único do job — o mesmo contador
    do ato pós-cena do ADR-0058. O traçado não cunha, não infere e não nomeia; ele
    TRANSPORTA para a entidade o que uma pessoa já afirmou sobre a proposta.

    A entrada revogada continua na lista da revisão com `status="revoked"`, porque o ref sai
    de circulação e o histórico não pode perder o que foi afirmado. O transporte a ignora:
    devolver à cena a identidade que alguém desfez seria desfazer o ato humano em silêncio.
    """

    element_ref: str = Field(pattern=ELEMENT_REF_PATTERN)
    label: str | None = Field(default=None, max_length=ELEMENT_LABEL_MAX_LENGTH)
    proposal_ids: list[str] = Field(default_factory=list)
    status: Literal["active", "revoked"] = "active"


def element_declarations_from_review(
    rows: Iterable[Mapping[str, Any]],
) -> list[TraceElementDeclaration]:
    """As declarações gravadas na revisão, na forma que o traçado consome.

    A linha persistida carrega também o rastro do ato (quem declarou, com que papel, quando,
    e o mesmo para a revogação); o transporte não precisa de nada disso, e `TraceModel`
    proíbe campo extra de propósito. Ler campo a campo aqui mantém a forma persistida
    conhecida num lugar só, em vez de espalhá-la pelo worker.

    Entrada malformada estoura: o worker do traçado transforma a exceção em
    `TRACE_SOLVE_FAILED` consultável, e falhar fechado é melhor do que descartar em silêncio
    a identidade que alguém declarou.
    """
    return [
        TraceElementDeclaration(
            element_ref=row["element_ref"],
            label=row.get("label"),
            proposal_ids=list(row.get("proposal_ids") or []),
            status=row.get("status", "active"),
        )
        for row in rows
    ]


TraceUnappliedCause = Literal[
    "TRACE_SPAN_VALUE_OR_DECISION_MISSING",
    "TRACE_SPAN_AXIS_UNDECLARED",
    "TRACE_SPAN_EDGE_NOT_FOUND",
    "TRACE_SPAN_SAME_BAND",
    "TRACE_TARGET_AS_DRAWN",
    "TRACE_SPAN_NOT_ORTHOGONAL",
    "TRACE_NOTE_ZERO_LENGTH",
    "TRACE_NOTE_UNSUPPORTED_GEOMETRY",
]
"""Os motivos pelos quais uma leitura confirmada e associada não virou vão nem nota.

O tipo é fechado aqui dentro (o mypy acusa código inventado no ponto do descarte) e
aberto no modelo (`UnappliedReadingReport.cause` é `str` com o mesmo padrão de
`Issue.code`): um registro gravado com um código de ontem continua legível amanhã.
"""

UNAPPLIED_CAUSE_MESSAGES: Final[dict[str, str]] = {
    "TRACE_SPAN_VALUE_OR_DECISION_MISSING": (
        "a leitura chegou sem valor em metros ou sem decisão humana completa"
    ),
    "TRACE_SPAN_AXIS_UNDECLARED": (
        "o vão não declara eixo (largura ou altura), e sem ele não há distância a amarrar"
    ),
    "TRACE_SPAN_EDGE_NOT_FOUND": (
        "nenhuma aresta perpendicular ao eixo foi encontrada para uma das âncoras do vão"
    ),
    "TRACE_SPAN_SAME_BAND": (
        "as duas âncoras caíram na mesma faixa, então não há duas incógnitas para amarrar"
    ),
    "TRACE_TARGET_AS_DRAWN": (
        "o alvo está aceito como desenhado; cota de elemento único não amarra em forma livre"
    ),
    "TRACE_SPAN_NOT_ORTHOGONAL": (
        "o elemento não tem segmento ortogonal compatível com o eixo da cota"
    ),
    "TRACE_NOTE_ZERO_LENGTH": "o segmento âncora da nota tem comprimento zero no desenho",
    "TRACE_NOTE_UNSUPPORTED_GEOMETRY": "a geometria do alvo não suporta nota ancorada",
}
"""Frase curta por código, para a mensagem da `Issue` que o revisor lê na cena."""


class UnappliedReadingReport(TraceModel):
    """Uma leitura confirmada que não virou vão, com o MOTIVO no ponto do descarte.

    Só o id não diz o que fazer: "não pôde virar vão ortogonal" cabe em várias situações
    diferentes, e cada uma tem um conserto diferente (declarar o eixo, declarar
    `keep_apart`, tirar o alvo de `freeform`…). O código nasce onde a decisão é tomada,
    nunca reconstruído depois por quem só tem o id.
    """

    reading_id: str
    # Mesmo padrão de `Issue.code`: código estável, nunca frase.
    cause: str = Field(pattern=r"^[A-Z0-9_]{3,64}$")
    target_proposal_ids: list[str] = Field(default_factory=list)


class ContestedSpan(TraceModel):
    """Duas ou mais cotas confirmadas prometendo distâncias diferentes para o MESMO vão.

    Diagnóstico, não portão: quem decide o desfecho continua sendo o resíduo
    (`NUMERIC_RESIDUAL_EXCEEDS_TOLERANCE`). O que faltava era o par nomeado — o revisor
    via cinco resíduos estourados e nenhum deles dizia quais duas leituras disputam a
    mesma incógnita.
    """

    axis: Literal["x", "y"]
    reading_ids: list[str] = Field(min_length=2)
    # Mesma ordem de `reading_ids`: o valor que cada leitura promete para o vão.
    values_m: list[Decimal] = Field(min_length=2)
    proposal_ids: list[str] = Field(default_factory=list)


class AppliedSpanReport(TraceModel):
    """Onde, em metros da prancha, a cota aplicada ancorou.

    `start_m`/`end_m` são a coordenada ao longo do eixo da cota no frame CAD (origem no
    canto inferior esquerdo), com `start_m <= end_m`. É o que permite dizer "esta cota
    amarra daqui até ali" sem reabrir o DXF.
    """

    reading_id: str
    axis: Literal["x", "y"]
    value_m: Decimal
    start_m: float
    end_m: float
    proposal_id: str
    second_proposal_id: str | None = None
    gap: bool = False


class TraceSolveResult(TraceModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    solver_version: Literal["trace-solver-v1"] = TRACER_VERSION
    status: Literal["solved_unapproved", "review_required", "conflict"]
    dataset_id: str
    feature_id: str
    blockers: list[str]
    unapplied_reading_ids: list[str]
    residuals: list[SolverResidual]
    exact_entity_count: int = Field(ge=0)
    approximate_entity_count: int = Field(ge=0)
    note_count: int = Field(default=0, ge=0)
    # Escala da planta principal; cada grupo de detalhe tem a própria escala abaixo.
    scale_m_per_px: float | None = None
    detail_group_scales: dict[str, float] = Field(default_factory=dict)
    scene: SceneRevision | None = None
    # Critérios de escopo declarados no caso; são os únicos códigos que a aprovação pode
    # declarar cobertos ou reconhecer como pendentes.
    required_criteria: list[ScopeCriterion] = Field(default_factory=list)
    safety_notes: list[str] = Field(min_length=2)
    # Diagnóstico do traçado, aditivo: `unapplied_reading_ids` continua sendo a lista de
    # ids, na mesma ordem, e estes três campos dizem POR QUE, QUEM DISPUTA e ONDE ANCOROU.
    unapplied_readings: list[UnappliedReadingReport] = Field(default_factory=list)
    contested_spans: list[ContestedSpan] = Field(default_factory=list)
    applied_spans: list[AppliedSpanReport] = Field(default_factory=list)


class ApprovedTraceRevision(TraceModel):
    approval: SceneApproval
    source_scene_id: UUID
    scene: SceneRevision


class DerivedDimensionRequest(TraceModel):
    """Pedido do revisor para cotar um trecho desenhado com o valor da geometria resolvida.

    O 1,50 do recuo da mureta não está escrito na folha — é consequência de 4,80 e 3,30
    confirmados. A cota sai `derived`: o número vem do solver, não de leitura humana.
    """

    proposal_id: str = Field(min_length=1)
    near_x_px: float = Field(ge=0)
    near_y_px: float = Field(ge=0)
    # Texto exibido em vez do valor medido (vão de portão: "3,60 x 3,90"). Apresentação
    # declarada pelo revisor; a geometria continua sendo a do trecho desenhado.
    text: str | None = Field(default=None, max_length=100)


class _AppliedSpan(TraceModel):
    reading_id: str
    decision_id: str
    proposal_id: str
    axis: Literal["x", "y"]
    first_junction: int
    second_junction: int
    value_m: Decimal
    written_decimals: int
    raw_text: str
    unit: UnitCode
    # Vão entre dois elementos: a cota mede a distância entre faixas de propostas
    # distintas, e a DIMENSION é desenhada na posição do recorte da evidência.
    gap: bool = False
    second_proposal_id: str | None = None
    evidence_x_px: float = 0.0
    evidence_y_px: float = 0.0


class _AppliedCircle(TraceModel):
    """Leitura confirmada de raio/diâmetro que determina um círculo aceito.

    Círculo não tem junção e nunca participa do sistema de faixas: sem isto a cota de
    diâmetro do croqui (o 9,60 do Raul Campelo) ficava como não aplicada e virava nota.
    """

    reading_id: str
    decision_id: str
    proposal_id: str
    # RADIUS ou DIAMETER, como o revisor confirmou: decide o valor da `Measurement`.
    kind: MeasurementKind
    radius_m: Decimal
    # Valor da leitura em metros, como escrito na folha (raio ou diâmetro, conforme kind).
    value_m: Decimal
    written_decimals: int
    raw_text: str
    unit: UnitCode
    evidence_x_px: float
    evidence_y_px: float


CIRCLE_DIMENSION_KINDS: Final = frozenset({MeasurementKind.RADIUS, MeasurementKind.DIAMETER})
"""Kinds confirmados que determinam um círculo; o resto continua sem eixo em círculo."""


def _uuid(dataset_id: str, feature_id: str, suffix: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"croquito:{dataset_id}:{feature_id}:{suffix}")


def _value_m(reading: DimensionReading) -> Decimal | None:
    if reading.value_si is None:
        return None
    if reading.unit is UnitCode.MILLIMETRE:
        return reading.value_si * Decimal("0.001")
    return reading.value_si


def _junction_map(topology: Topology) -> dict[tuple[str, int], int]:
    mapping: dict[tuple[str, int], int] = {}
    for junction in topology.junctions:
        for member in junction.members:
            mapping[(member.proposal_id, member.vertex_index)] = junction.id
    return mapping


def _proposal_junctions(
    proposal: VisionProposal, junction_of: dict[tuple[str, int], int]
) -> list[int]:
    geometry = proposal.geometry
    if isinstance(geometry, PixelLine):
        count = 2
    elif isinstance(geometry, PixelPolyline):
        count = len(geometry.points)
    else:
        return []
    return [junction_of[(proposal.id, index)] for index in range(count)]


def _segment_distance(point: tuple[float, float], start: PixelPoint, end: PixelPoint) -> float:
    delta_x, delta_y = end.x - start.x, end.y - start.y
    length_squared = delta_x * delta_x + delta_y * delta_y
    if length_squared < 1e-12:
        return math.hypot(point[0] - start.x, point[1] - start.y)
    progress = ((point[0] - start.x) * delta_x + (point[1] - start.y) * delta_y) / length_squared
    progress = min(1.0, max(0.0, progress))
    return math.hypot(
        point[0] - (start.x + progress * delta_x),
        point[1] - (start.y + progress * delta_y),
    )


def _candidate_segments(
    proposal: VisionProposal,
    junctions: Sequence[int],
    evidence_centre: tuple[float, float],
) -> list[tuple[int, int]]:
    """Segmentos da proposta, do mais próximo ao mais distante do recorte da leitura.

    Para linha só existe um. Para polilinha, a associação aponta o elemento inteiro e o
    recorte da evidência — que o revisor viu e confirmou — indica o trecho.
    """
    geometry = proposal.geometry
    if isinstance(geometry, PixelLine):
        return [(junctions[0], junctions[1])]
    if not isinstance(geometry, PixelPolyline):
        return []
    points = geometry.points
    pairs = [(index, index + 1) for index in range(len(points) - 1)]
    if geometry.closed and len(points) >= 3:
        pairs.append((len(points) - 1, 0))
    ranked = sorted(
        pairs,
        key=lambda pair: _segment_distance(evidence_centre, points[pair[0]], points[pair[1]]),
    )
    return [(junctions[start_index], junctions[end_index]) for start_index, end_index in ranked]


def _required_axis(reading: DimensionReading) -> Literal["x", "y"] | None:
    """Eixo que a decisão humana declara: width mede horizontal, height mede vertical.

    O `kind` é parte do que o revisor confirma — usá-lo não é palpite. A cota escrita no
    meio do vão fica longe do segmento que mede (o "3,30" do recuo da mureta encosta na
    parede vertical), e sem essa declaração o segmento mais próximo venceria no eixo errado.
    """
    if reading.kind is MeasurementKind.WIDTH:
        return "x"
    if reading.kind is MeasurementKind.HEIGHT:
        return "y"
    return None


def _gap_edge(
    proposal: VisionProposal,
    junction_of: dict[tuple[str, int], int],
    bands: AxisBands,
    topology: Topology,
    centre: tuple[float, float],
    axis: Literal["x", "y"],
    *,
    freeform: bool = False,
) -> tuple[int, int, float] | None:
    """Junção, faixa e posição traçada da aresta do elemento perpendicular ao vão.

    Elemento declarado como desenhado (`freeform`) não tem aresta em faixa — cada vértice
    guarda a própria coordenada. A âncora passa a ser o vértice mais próximo do recorte:
    é o que permite três afastamentos distintos ao longo de um limite não-paralelo.
    """
    junctions = _proposal_junctions(proposal, junction_of)
    if not junctions:
        return None
    if freeform:
        nearest = min(
            junctions,
            key=lambda item: math.hypot(
                topology.junction(item).x - centre[0], topology.junction(item).y - centre[1]
            ),
        )
        if axis == "y":
            return (nearest, bands.y_band_of[nearest], topology.junction(nearest).y)
        return (nearest, bands.x_band_of[nearest], topology.junction(nearest).x)
    for first, second in _candidate_segments(proposal, junctions, centre):
        if first == second:
            continue
        if axis == "y":
            if (
                bands.y_band_of[first] == bands.y_band_of[second]
                and bands.x_band_of[first] != bands.x_band_of[second]
            ):
                return (first, bands.y_band_of[first], topology.junction(first).y)
        elif (
            bands.x_band_of[first] == bands.x_band_of[second]
            and bands.y_band_of[first] != bands.y_band_of[second]
        ):
            return (first, bands.x_band_of[first], topology.junction(first).x)
    return None


def _edge_order_key(
    edge: tuple[int, int, float], traced_bands: Mapping[int, float]
) -> tuple[float, float, int]:
    """Ordem near/far das duas arestas de um vão, decidida inteiramente pelo desenho.

    A eleição usava a posição traçada da junção representativa e mais nada. Duas arestas na
    MESMA coordenada — dois elementos desenhados um sobre o outro, que é exatamente o caso
    que `keep_apart` existe para tratar — empatam essa chave, e `sorted`, sendo estável,
    completava o desempate com a POSIÇÃO NO ARRAY da associação: a ordem em que o revisor
    clicou as duas formas. Ordem de clique não é declaração, e ali ela virava semântica —
    saía daqui como a ordem `first_band → second_band` da restrição e, no empate de faixas
    (`SpanConstraint.signed=False`, onde `_band_span_constraint` não tem gap traçado para
    reordenar), era ela quem fixava o sinal da equação no LSQ. Os dois elementos trocavam de
    lado conforme a ordem do par, o resto do desenho deslizava atrás e tudo fechava com os
    mesmos resíduos verdes, porque o resíduo reportado é absoluto.

    A chave passa a ser total e vem toda do traçado: posição da junção, depois posição da
    FAIXA — a incógnita do solver, o mesmo critério com que `_band_span_constraint` assina a
    restrição (princípio 3 do `TRACE_STAGE`) — e, por fim, o id da faixa, que a
    regularização deriva da topologia. O id desempata sempre: aresta de faixa igual já saiu
    como leitura não aplicada antes de chegar aqui, então as duas faixas são distintas por
    construção. Empate de verdade continua sem lado honesto no desenho; o que muda é que o
    lado arbitrado vem da topologia, nunca do clique.
    """
    return (edge[2], traced_bands[edge[1]], edge[1])


def _band_span_constraint(
    *,
    axis: Literal["x", "y"],
    first_band: int,
    second_band: int,
    value_m: float,
    source_id: str,
    traced_bands: Mapping[int, float],
    tie_tolerance_px: float,
) -> SpanConstraint:
    """A restrição com o LADO que o traçado declarou entre as duas faixas.

    A cota manda na distância; o lado vem do traçado — e o traçado que vale aqui é o das
    duas FAIXAS, não o das duas junções representativas. A distinção é o defeito: a junção
    escolhida é uma ponta da aresta e a faixa é a média das junções que ela reúne, então
    uma aresta inclinada (ou uma polilinha refinada, cujo vértice fica longe da faixa em
    que caiu) põe as duas em ordens opostas. A faixa é a incógnita do solver; ordenar pela
    junção emitia uma equação que contradizia a própria ordem traçada — e como o resíduo
    é absoluto, a cena saía espelhada com todos os resíduos verdes.

    Empate — gap traçado menor que a tolerância de agrupamento, que é o caso dos elementos
    desenhados coincidentes e declarados distintos (`keep_apart`) — sai sem sinal: a folha
    não diz de que lado, e escolher por ruído de pixel seria inventar. Ver `SpanConstraint`.
    """
    gap_px = traced_bands[second_band] - traced_bands[first_band]
    if abs(gap_px) < tie_tolerance_px:
        return SpanConstraint(
            axis=axis,
            first_band=first_band,
            second_band=second_band,
            value_m=value_m,
            source_id=source_id,
            signed=False,
        )
    ordered = (second_band, first_band) if gap_px < 0.0 else (first_band, second_band)
    return SpanConstraint(
        axis=axis,
        first_band=ordered[0],
        second_band=ordered[1],
        value_m=value_m,
        source_id=source_id,
    )


def _parse_declared_association(
    association: Mapping[str, object],
) -> tuple[str, list[tuple[tuple[float, float], tuple[float, float]]]] | None:
    """Valida o formato objeto de associação: elemento + pares de âncoras por vão."""
    if set(association) != {"proposal_id", "spans_px"}:
        return None
    proposal_id = association.get("proposal_id")
    raw_spans = association.get("spans_px")
    if not isinstance(proposal_id, str) or not isinstance(raw_spans, list) or not raw_spans:
        return None
    pairs: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for raw_pair in raw_spans:
        if not isinstance(raw_pair, list) or len(raw_pair) != 2:
            return None
        points: list[tuple[float, float]] = []
        for raw_point in raw_pair:
            if (
                not isinstance(raw_point, list)
                or len(raw_point) != 2
                or not all(
                    isinstance(value, int | float) and not isinstance(value, bool)
                    for value in raw_point
                )
            ):
                return None
            points.append((float(raw_point[0]), float(raw_point[1])))
        pairs.append((points[0], points[1]))
    return proposal_id, pairs


def _span_from_reading(
    reading: DimensionReading,
    targets: Sequence[VisionProposal],
    junction_of: dict[tuple[str, int], int],
    topology: Topology,
    bands: AxisBands,
    *,
    traced_x: Mapping[int, float],
    traced_y: Mapping[int, float],
    tie_tolerance_px: float,
    declared_spans_px: Sequence[tuple[tuple[float, float], tuple[float, float]]] = (),
    freeform_ids: frozenset[str] = frozenset(),
) -> list[tuple[SpanConstraint, _AppliedSpan]] | TraceUnappliedCause:
    """Converte uma leitura confirmada e associada em restrição(ões) e vão(s) desenhado(s).

    Falha devolve o CÓDIGO da causa, não `None`: o motivo é conhecido exatamente aqui, no
    ponto do descarte, e reconstruí-lo depois a partir do id da leitura seria adivinhação.

    `traced_x`/`traced_y` são as posições traçadas das FAIXAS (não das junções): é delas
    que sai o lado de cada restrição, em `_band_span_constraint`. A ordem das junções em
    `_AppliedSpan` continua vindo do desenho, porque ela serve à cota desenhada e ao
    resíduo — que é absoluto e não depende de qual ponta vem primeiro.

    `targets` chega na ordem em que o revisor clicou as formas, e essa ordem não é
    declaração nenhuma: toda eleição daqui para baixo sai por `_edge_order_key`, chave
    total do traçado. O mesmo vale para a ordem das âncoras de um vão declarado.
    """
    value = _value_m(reading)
    if value is None or reading.decision is None:
        return "TRACE_SPAN_VALUE_OR_DECISION_MISSING"
    box = reading.evidence.bbox
    centre = ((box.left + box.right) / 2, (box.top + box.bottom) / 2)
    required_axis = _required_axis(reading)

    if declared_spans_px:
        # Vão declarado entre duas arestas do mesmo elemento: o número da folha mede um
        # trecho interno (altura do rebaixo, comprimento do trecho recortado) que nenhuma
        # aresta única carrega. O revisor declara um par de âncoras em pixel por vão; cada
        # âncora elege a aresta perpendicular mais próxima e a cota amarra as duas faixas.
        # Todas as âncoras resolvem ou a leitura inteira fica como não aplicada.
        if required_axis is None:
            return "TRACE_SPAN_AXIS_UNDECLARED"
        proposal = targets[0]
        freeform = proposal.id in freeform_ids
        traced_axis = traced_x if required_axis == "x" else traced_y
        outcomes: list[tuple[SpanConstraint, _AppliedSpan]] = []
        for anchor_a, anchor_b in declared_spans_px:
            edge_a = _gap_edge(
                proposal, junction_of, bands, topology, anchor_a, required_axis, freeform=freeform
            )
            edge_b = _gap_edge(
                proposal, junction_of, bands, topology, anchor_b, required_axis, freeform=freeform
            )
            if edge_a is None or edge_b is None:
                return "TRACE_SPAN_EDGE_NOT_FOUND"
            if edge_a[1] == edge_b[1]:
                return "TRACE_SPAN_SAME_BAND"
            # Mesma eleição do vão em par, mesmo motivo: a ordem em que o revisor declarou
            # as duas âncoras do trecho não pode decidir nada (`_edge_order_key`).
            near_edge, far_edge = sorted(
                (edge_a, edge_b), key=lambda edge: _edge_order_key(edge, traced_axis)
            )
            midpoint = (
                (anchor_a[0] + anchor_b[0]) / 2,
                (anchor_a[1] + anchor_b[1]) / 2,
            )
            outcomes.append(
                (
                    _band_span_constraint(
                        axis=required_axis,
                        first_band=near_edge[1],
                        second_band=far_edge[1],
                        value_m=float(value),
                        source_id=reading.id,
                        traced_bands=traced_axis,
                        tie_tolerance_px=tie_tolerance_px,
                    ),
                    _AppliedSpan(
                        reading_id=reading.id,
                        decision_id=reading.decision.decision_id,
                        proposal_id=proposal.id,
                        axis=required_axis,
                        first_junction=near_edge[0],
                        second_junction=far_edge[0],
                        value_m=value,
                        written_decimals=reading.written_decimals,
                        raw_text=reading.raw_text,
                        unit=reading.unit,
                        gap=True,
                        evidence_x_px=midpoint[0],
                        evidence_y_px=midpoint[1],
                    ),
                )
            )
        return outcomes

    if len(targets) == 2:
        # Vão entre dois elementos: exige eixo declarado pelo revisor (width/height) —
        # sem ele não há como saber que distância entre as duas arestas a cota promete.
        if required_axis is None:
            return "TRACE_SPAN_AXIS_UNDECLARED"
        edges = [
            _gap_edge(
                proposal,
                junction_of,
                bands,
                topology,
                centre,
                required_axis,
                freeform=proposal.id in freeform_ids,
            )
            for proposal in targets
        ]
        first_edge, second_edge = edges[0], edges[1]
        if first_edge is None or second_edge is None:
            return "TRACE_SPAN_EDGE_NOT_FOUND"
        if first_edge[1] == second_edge[1]:
            return "TRACE_SPAN_SAME_BAND"
        # A posição do elemento no par é ordem de clique, não declaração: a eleição
        # near/far sai por chave total do traçado (`_edge_order_key`), nunca pelo array.
        traced_axis = traced_x if required_axis == "x" else traced_y
        ordered = sorted(
            [(first_edge, targets[0]), (second_edge, targets[1])],
            key=lambda item: _edge_order_key(item[0], traced_axis),
        )
        (near_edge, near_proposal), (far_edge, far_proposal) = ordered
        constraint = _band_span_constraint(
            axis=required_axis,
            first_band=near_edge[1],
            second_band=far_edge[1],
            value_m=float(value),
            source_id=reading.id,
            traced_bands=traced_axis,
            tie_tolerance_px=tie_tolerance_px,
        )
        applied = _AppliedSpan(
            reading_id=reading.id,
            decision_id=reading.decision.decision_id,
            proposal_id=near_proposal.id,
            axis=required_axis,
            first_junction=near_edge[0],
            second_junction=far_edge[0],
            value_m=value,
            written_decimals=reading.written_decimals,
            raw_text=reading.raw_text,
            unit=reading.unit,
            gap=True,
            second_proposal_id=far_proposal.id,
            evidence_x_px=centre[0],
            evidence_y_px=centre[1],
        )
        return [(constraint, applied)]

    proposal = targets[0]
    if proposal.id in freeform_ids:
        # Elemento aceito "como desenhado" não tem faixa por aresta — cada vértice guarda a
        # própria coordenada —, então uma cota de elemento único nunca teria duas incógnitas
        # ortogonais para amarrar. Dizer isso aqui, e não deixar o laço de segmentos morrer
        # em "não ortogonal", é a diferença entre o revisor tirar o alvo de `freeform` (ou
        # declarar o vão por âncoras) e ficar procurando um esquadro que não é o problema.
        return "TRACE_TARGET_AS_DRAWN"
    junctions = _proposal_junctions(proposal, junction_of)
    if not junctions:
        return "TRACE_SPAN_NOT_ORTHOGONAL"
    chosen: tuple[int, int, Literal["x", "y"]] | None = None
    for first, second in _candidate_segments(proposal, junctions, centre):
        if first == second:
            continue
        same_row = bands.y_band_of[first] == bands.y_band_of[second]
        same_column = bands.x_band_of[first] == bands.x_band_of[second]
        if same_row == same_column:
            # Diagonal (ou degenerado): o sistema de faixas só carrega vãos ortogonais.
            continue
        segment_axis: Literal["x", "y"] = "x" if same_row else "y"
        if required_axis is not None and segment_axis != required_axis:
            continue
        chosen = (first, second, segment_axis)
        break
    if chosen is None:
        return "TRACE_SPAN_NOT_ORTHOGONAL"
    first, second, axis = chosen
    band_of = bands.x_band_of if axis == "x" else bands.y_band_of
    position = {
        junction.id: (junction.x if axis == "x" else junction.y) for junction in topology.junctions
    }
    if position[first] > position[second]:
        first, second = second, first
    constraint = _band_span_constraint(
        axis=axis,
        first_band=band_of[first],
        second_band=band_of[second],
        value_m=float(value),
        source_id=reading.id,
        traced_bands=traced_x if axis == "x" else traced_y,
        tie_tolerance_px=tie_tolerance_px,
    )
    applied = _AppliedSpan(
        reading_id=reading.id,
        decision_id=reading.decision.decision_id,
        proposal_id=proposal.id,
        axis=axis,
        first_junction=first,
        second_junction=second,
        value_m=value,
        written_decimals=reading.written_decimals,
        raw_text=reading.raw_text,
        unit=reading.unit,
        evidence_x_px=centre[0],
        evidence_y_px=centre[1],
    )
    return [(constraint, applied)]


def _circle_from_reading(reading: DimensionReading, proposal_id: str) -> _AppliedCircle | None:
    value = _value_m(reading)
    if value is None or reading.decision is None:
        return None
    box = reading.evidence.bbox
    return _AppliedCircle(
        reading_id=reading.id,
        decision_id=reading.decision.decision_id,
        proposal_id=proposal_id,
        kind=reading.kind,
        # Diâmetro escrito vira raio aqui e em lugar nenhum mais: a cota continua sendo
        # o diâmetro na `Measurement` e no texto, a geometria é que pede o raio.
        radius_m=value / 2 if reading.kind is MeasurementKind.DIAMETER else value,
        value_m=value,
        written_decimals=reading.written_decimals,
        raw_text=reading.raw_text,
        unit=reading.unit,
        evidence_x_px=(box.left + box.right) / 2,
        evidence_y_px=(box.top + box.bottom) / 2,
    )


def _take_circle_readings(
    span_targets: dict[str, list[str]],
    *,
    readings: Mapping[str, DimensionReading],
    proposal_by_id: Mapping[str, VisionProposal],
    declared_spans: Mapping[str, Sequence[object]],
) -> tuple[list[_AppliedCircle], dict[str, Decimal], list[str]]:
    """Retira de `span_targets` as cotas de raio/diâmetro que determinam um círculo.

    Alvo único, proposta círculo e `kind` confirmado de raio ou diâmetro: a cota manda no
    raio, e a leitura sai do sistema de faixas — não chega ao solver nem a `unapplied`.
    Vão entre dois elementos e vão declarado em pixels continuam fora: nenhum dos dois
    mede o círculo. Devolve também os blockers de leituras que discordam do mesmo círculo.
    """
    applied: list[_AppliedCircle] = []
    for reading_id in sorted(span_targets):
        targets = span_targets[reading_id]
        if len(targets) != 1 or reading_id in declared_spans:
            continue
        reading = readings[reading_id]
        if reading.kind not in CIRCLE_DIMENSION_KINDS:
            continue
        proposal = proposal_by_id[targets[0]]
        if not isinstance(proposal.geometry, PixelCircle):
            continue
        circle = _circle_from_reading(reading, proposal.id)
        if circle is None:
            continue
        applied.append(circle)
        del span_targets[reading_id]

    by_proposal: dict[str, list[_AppliedCircle]] = {}
    for circle in applied:
        by_proposal.setdefault(circle.proposal_id, []).append(circle)
    radius_by_proposal: dict[str, Decimal] = {}
    conflicts: list[str] = []
    for proposal_id, circles in sorted(by_proposal.items()):
        ordered = sorted(circles, key=lambda item: item.reading_id)
        # Duas leituras sobre o mesmo círculo: a geometria fica com a de menor id (o
        # traçado precisa ser determinístico) e a divergência vira blocker — as duas
        # `Measurement` continuam na cena para o portão do core acusar a incompatível.
        radius_by_proposal[proposal_id] = ordered[0].radius_m
        for first, second in combinations(ordered, 2):
            tolerance = max(
                _written_tolerance_m(first.written_decimals, first.unit),
                _written_tolerance_m(second.written_decimals, second.unit),
            )
            if abs(first.radius_m - second.radius_m) > tolerance:
                conflicts.append(f"TRACE_CIRCLE_READINGS_CONFLICT:{proposal_id}")
                break
    return applied, radius_by_proposal, conflicts


def _layer_for(proposal: VisionProposal, *, exact: bool) -> LayerName:
    if not exact:
        # Aproximação mora na layer própria: a separação visual é o que mantém honesta
        # a convivência de cota exata com traçado de pixel no mesmo desenho.
        return LayerName.APROXIMADO
    hint = (proposal.layer_hint or "").strip().upper()
    try:
        return LayerName(hint)
    except ValueError:
        return LayerName.DETALHES


def _note_position(
    mid: Point2D,
    unit: tuple[float, float],
    normal: tuple[float, float],
    outward_sign: float,
    *,
    width: float,
    height: float,
    obstacles: Sequence[tuple[float, float, float, float]],
) -> tuple[float, float, tuple[float, float, float, float]]:
    """Vaga para a nota, sem desgarrá-la do elemento que ela nomeia.

    Só aumentar o afastamento perpendicular expulsava a nota da vizinhança (o
    `Portão 1,0 x 2,05` subiu até o topo da folha fugindo da cota `1.00 m`). A escada
    aqui desliza ao longo do próprio elemento antes de se afastar, e tenta o lado de
    dentro antes de ir parar longe. Primeiro candidato livre vence; o fallback é a
    posição base — sobrepor perto ainda informa mais do que flutuar longe.
    """

    def box_at(centre_x: float, centre_y: float) -> tuple[float, float, float, float]:
        # Nota girada tem caixa alta; deitada, caixa larga (aproximação por eixo).
        if abs(unit[0]) >= abs(unit[1]):
            return (
                centre_x - width / 2,
                centre_y - height,
                centre_x + width / 2,
                centre_y + height,
            )
        return (centre_x - height, centre_y - width / 2, centre_x + height, centre_y + width / 2)

    fallback: tuple[float, float, tuple[float, float, float, float]] | None = None
    for side in (outward_sign, -outward_sign):
        for step in range(4):
            distance = height * 1.2 + step * height * 2.2
            for lateral in (0.0, 0.35, -0.35, 0.7, -0.7):
                centre_x = mid.x + unit[0] * lateral * width + normal[0] * side * distance
                centre_y = mid.y + unit[1] * lateral * width + normal[1] * side * distance
                candidate = box_at(centre_x, centre_y)
                if fallback is None:
                    fallback = (centre_x, centre_y, candidate)
                if not any(boxes_overlap(candidate, other) for other in obstacles):
                    return (centre_x, centre_y, candidate)
    assert fallback is not None
    return fallback


def _written_tolerance_m(written_decimals: int, unit: UnitCode) -> Decimal:
    """Metade da última casa escrita: a precisão que a própria folha declara."""
    tolerance = Decimal(1).scaleb(-written_decimals) / 2
    if unit is UnitCode.MILLIMETRE:
        tolerance *= Decimal("0.001")
    return max(Decimal("0.000001"), tolerance)


def _span_tolerance_m(span: _AppliedSpan) -> Decimal:
    return _written_tolerance_m(span.written_decimals, span.unit)


@dataclass
class _GroupState:
    """Contexto geométrico de um grupo resolvido (planta ou detalhe).

    `build_topology` renumera junções a cada chamada, então `junction_of` e
    `cad_position` de grupos distintos vivem em espaços de ids diferentes — o estado
    é sempre consultado por grupo, nunca fundido num dict global.
    """

    topology: Topology
    bands: AxisBands
    junction_of: dict[tuple[str, int], int]
    # `None` em grupo sketch: o desenho fica como está, nada é "determinado" por cota.
    solved: SolvedGeometry | None
    scale_m_per_px: float
    cad_position: dict[int, Point2D]
    # Afins pixel→prancha por eixo (a, b): coordenada = a*px + b. O espelho de Y e a
    # origem já estão embutidos; transladar o grupo é somar em `b`.
    x_map: tuple[float, float]
    y_map: tuple[float, float]
    radius_scale: float
    # Centro do bbox do grupo em coordenadas finais: é o "para dentro" das cotas e notas
    # do próprio grupo — o centro da planta viraria cota do lado errado num detalhe.
    centre: tuple[float, float] = (0.0, 0.0)

    def cad_point(self, point: PixelPoint) -> Point2D:
        return Point2D(
            x=self.x_map[0] * point.x + self.x_map[1],
            y=self.y_map[0] * point.y + self.y_map[1],
        )

    def translate(self, dx: float, dy: float) -> None:
        self.cad_position = {
            junction_id: Point2D(x=point.x + dx, y=point.y + dy)
            for junction_id, point in self.cad_position.items()
        }
        self.x_map = (self.x_map[0], self.x_map[1] + dx)
        self.y_map = (self.y_map[0], self.y_map[1] + dy)


def _band_is_exclusively_freeform(
    topology: Topology, band_of: Mapping[int, int], band: int, freeform_ids: frozenset[str]
) -> bool:
    """Toda junção da faixa pertence só a propostas freeform (faixa mista não conta).

    Por design a regularização já dá faixa própria a cada vértice freeform
    (`geometry_solver.regularise`), então a mistura não deveria acontecer — mas checar de
    novo aqui evita depender silenciosamente disso se a topologia mudar.
    """
    members = [
        member
        for junction in topology.junctions
        if band_of[junction.id] == band
        for member in junction.members
    ]
    return bool(members) and all(member.proposal_id in freeform_ids for member in members)


def _band_owners(topology: Topology, band_of: Mapping[int, int], band: int) -> set[str]:
    """`proposal_id` de toda junção que cai na faixa, no eixo já escolhido pelo chamador."""
    return {
        member.proposal_id
        for junction in topology.junctions
        if band_of[junction.id] == band
        for member in junction.members
    }


def _order_violation_proposals(state: _GroupState, freeform_ids: frozenset[str]) -> set[str]:
    """Propostas donas das junções dos pares de faixas com ordem invertida.

    Grupo `sketch` (`state.solved is None`) não passa por `solve_geometry` e não tem
    `band_order_violations` — devolve vazio, o check é só do que foi resolvido por cota.

    Duas dispensas, nessa ordem:

    - Uma das duas faixas pertence só a elementos declarados `freeform`: quem marca um
      elemento como desenhado já assumiu a posição desenhada dele, então a ordem dele
      contra o resto não é um defeito do traçado a bloquear.
    - As duas faixas não compartilham nenhum `proposal_id` dono: a GRAVATA nasceu para o
      auto-cruzamento de UM elemento (toda faixa dele carrega o mesmo dono, então a
      partilha nunca falta); relação COTADA entre dois elementos já tem o lado garantido
      pelo resíduo assinado do `SpanConstraint` (E3); sobra a inversão entre elementos
      DISTINTOS sem cota entre si, que é distorção do croqui na camada `approximate`, não
      defeito do solver a bloquear (achado do ensaio v5 do job real, 2026-08-13: grande
      área x borda de campo, portão sem cota x muro, bases de dois patamares fora de
      escala). O compartilhamento é a régua — um terceiro elemento presente nas duas
      faixas ainda conta, mesmo sem cota direta entre o par violado.

    Em ambos os casos a inversão entre faixas normais com dono em comum continua
    acusando.
    """
    if state.solved is None:
        return set()
    proposals: set[str] = set()
    for violation in state.solved.band_order_violations:
        band_of = state.bands.x_band_of if violation.axis == "x" else state.bands.y_band_of
        target_bands = {violation.first_band, violation.second_band}
        if any(
            _band_is_exclusively_freeform(state.topology, band_of, band, freeform_ids)
            for band in target_bands
        ):
            continue
        first_owners = _band_owners(state.topology, band_of, violation.first_band)
        second_owners = _band_owners(state.topology, band_of, violation.second_band)
        if first_owners.isdisjoint(second_owners):
            continue
        for junction in state.topology.junctions:
            if band_of[junction.id] in target_bands:
                proposals.update(member.proposal_id for member in junction.members)
    return proposals


def _state_bbox(
    state: _GroupState, members: Sequence[VisionProposal]
) -> tuple[float, float, float, float]:
    xs = [point.x for point in state.cad_position.values()]
    ys = [point.y for point in state.cad_position.values()]
    # Círculos não têm junção; sem eles um grupo só de círculos teria bbox vazio.
    for member in members:
        if isinstance(member.geometry, PixelCircle):
            centre = state.cad_point(member.geometry.center)
            radius = member.geometry.radius * state.radius_scale
            xs += [centre.x - radius, centre.x + radius]
            ys += [centre.y - radius, centre.y + radius]
    if not xs:
        return (0.0, 0.0, 0.0, 0.0)
    return (min(xs), min(ys), max(xs), max(ys))


def _members_pixel_bbox(
    members: Sequence[VisionProposal],
) -> tuple[float, float, float, float] | None:
    xs: list[float] = []
    ys: list[float] = []
    for member in members:
        geometry = member.geometry
        if isinstance(geometry, PixelLine):
            xs += [geometry.start.x, geometry.end.x]
            ys += [geometry.start.y, geometry.end.y]
        elif isinstance(geometry, PixelPolyline):
            xs += [point.x for point in geometry.points]
            ys += [point.y for point in geometry.points]
        elif isinstance(geometry, PixelCircle):
            xs += [geometry.center.x - geometry.radius, geometry.center.x + geometry.radius]
            ys += [geometry.center.y - geometry.radius, geometry.center.y + geometry.radius]
    if not xs:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


def _group_tolerance_ratio(
    members: Sequence[VisionProposal], image_width: int, image_height: int
) -> float:
    """Tolerância de fusão proporcional ao bbox do grupo, não à folha inteira.

    Um painel pequeno num canto da folha fundiria vértices que não se tocam se a
    tolerância continuasse sendo 1% da diagonal da imagem.
    """
    bbox = _members_pixel_bbox(members)
    image_diagonal = math.hypot(image_width, image_height)
    if bbox is None or image_diagonal < 1e-9:
        return JUNCTION_TOLERANCE_RATIO
    group_diagonal = math.hypot(bbox[2] - bbox[0], bbox[3] - bbox[1])
    if group_diagonal < 1e-9:
        return JUNCTION_TOLERANCE_RATIO
    return JUNCTION_TOLERANCE_RATIO * group_diagonal / image_diagonal


def _vertex_pairs(separations: Sequence[BandSeparation]) -> list[tuple[str, str]]:
    """Os pares como a topologia os usa: sem eixo.

    Vértice fundido é um ponto só e amarraria os dois eixos de uma vez, então declarar o
    eixo do problema afrouxa a faixa, nunca a fusão.
    """
    return [(pair.first, pair.second) for pair in separations]


def _sketch_group_geometry(
    members: Sequence[VisionProposal],
    *,
    keep_apart: Sequence[BandSeparation],
    image_width: int,
    image_height: int,
    tolerance_ratio: float,
    plan_scale_m_per_px: float,
) -> _GroupState:
    """Grupo `sketch`: o desenho como está na folha, projetado pela escala da planta.

    Nada é resolvido nem determinado — isométricos e croquis livres não têm bandas
    ortogonais honestas. A escala uniforme é a única legítima que a folha tem (a da
    planta); espelho de Y e origem local seguem a mesma convenção dos grupos resolvidos.
    Por isso o encosto também não entra aqui: nenhuma faixa move nada num sketch, e
    amarrar junções que ninguém vai deslocar só mudaria contagem.
    """
    topology = build_topology(
        members,
        image_width=image_width,
        image_height=image_height,
        tolerance_ratio=tolerance_ratio,
        keep_apart=_vertex_pairs(keep_apart),
    )
    junction_of = _junction_map(topology)
    bbox = _members_pixel_bbox(members) or (0.0, 0.0, 0.0, 0.0)
    scale = plan_scale_m_per_px
    min_px_x, max_px_y = bbox[0], bbox[3]
    cad_position = {
        junction.id: Point2D(
            x=(junction.x - min_px_x) * scale,
            y=(max_px_y - junction.y) * scale,
        )
        for junction in topology.junctions
    }
    return _GroupState(
        topology=topology,
        bands=regularise(topology, keep_apart=keep_apart),
        junction_of=junction_of,
        solved=None,
        scale_m_per_px=scale,
        cad_position=cad_position,
        x_map=(scale, -min_px_x * scale),
        y_map=(-scale, max_px_y * scale),
        radius_scale=scale,
    )


def _contested_spans(
    outcomes: Sequence[tuple[SpanConstraint, _AppliedSpan]],
) -> list[ContestedSpan]:
    """Nomeia, par a par, as leituras que prometem distâncias diferentes para o mesmo vão.

    O critério é o do próprio sistema de faixas: duas restrições que ligam o MESMO par de
    faixas no mesmo eixo disputam uma única incógnita. Quando os valores escritos divergem
    por mais do que a tolerância da cota mais grosseira envolvida, o LSQ vai ceder para
    algum lugar entre elas e estourar os resíduos — e é aqui que se sabe quem discorda com
    quem, informação que o resíduo sozinho não carrega.

    `first_band`/`second_band` já vêm na ordem traçada (`_band_span_constraint`), então o
    par é estável e não depende da ordem em que as leituras foram emitidas. Isto é
    diagnóstico: não cria blocker, não muda status, não mexe no solver.
    """
    grouped: dict[tuple[str, int, int], list[tuple[SpanConstraint, _AppliedSpan]]] = {}
    for constraint, applied in outcomes:
        key = (constraint.axis, constraint.first_band, constraint.second_band)
        grouped.setdefault(key, []).append((constraint, applied))

    contested: list[ContestedSpan] = []
    for _key, members in sorted(grouped.items()):
        # O eixo sai do vão desenhado (já tipado), não da string da restrição.
        axis = members[0][1].axis
        value_of: dict[str, Decimal] = {}
        proposal_ids: set[str] = set()
        tolerance = Decimal(0)
        for constraint, applied in members:
            value_of.setdefault(constraint.source_id, applied.value_m)
            proposal_ids.add(applied.proposal_id)
            if applied.second_proposal_id is not None:
                proposal_ids.add(applied.second_proposal_id)
            tolerance = max(tolerance, _span_tolerance_m(applied))
        if len(value_of) < 2:
            continue
        values = list(value_of.values())
        if max(values) - min(values) <= tolerance:
            continue
        reading_ids = sorted(value_of)
        contested.append(
            ContestedSpan(
                axis=axis,
                reading_ids=reading_ids,
                values_m=[value_of[reading_id] for reading_id in reading_ids],
                proposal_ids=sorted(proposal_ids),
            )
        )
    return contested


def _solve_group_geometry(
    group_proposals: Sequence[VisionProposal],
    *,
    readings: Mapping[str, DimensionReading],
    span_targets: Mapping[str, list[str]],
    proposal_by_id: Mapping[str, VisionProposal],
    keep_apart: Sequence[BandSeparation],
    image_width: int,
    image_height: int,
    tolerance_ratio: float = JUNCTION_TOLERANCE_RATIO,
    declared_spans: Mapping[str, list[tuple[tuple[float, float], tuple[float, float]]]]
    | None = None,
    freeform_ids: frozenset[str] = frozenset(),
) -> tuple[
    _GroupState | None,
    list[SpanConstraint],
    list[_AppliedSpan],
    list[UnappliedReadingReport],
    list[ContestedSpan],
]:
    """Resolve a geometria de um grupo: topologia, bandas, cotas e espelho para CAD.

    Devolve estado `None` quando nenhuma cota confirmada alcança o grupo — o chamador
    decide o blocker; `unapplied` sobrevive para o relatório mesmo nesse caso.

    Os vãos em disputa saem daqui, e não do agregado do chamador, porque o id de faixa é
    local ao grupo: comparar faixas de grupos distintos acusaria disputa entre cotas que
    nunca partilharam incógnita.
    """
    topology = build_topology(
        group_proposals,
        image_width=image_width,
        image_height=image_height,
        tolerance_ratio=tolerance_ratio,
        keep_apart=_vertex_pairs(keep_apart),
    )
    # Mesma tolerância (em px) que `build_topology` usou para fundir junções deste grupo.
    # Serve a dois usos, pelo mesmo motivo — é o limiar de "isto se toca no papel": o
    # encosto de uma junção na aresta de outro elemento (que a fusão de vértices não vê,
    # porque lá não há vértice) e o empate de ordem, que não pode acusar par que a fusão
    # já considera coincidente.
    touch_tolerance_px = math.hypot(image_width, image_height) * tolerance_ratio
    # Os mesmos pares que a topologia usa para não fundir vértices: a faixa é a variável
    # do solver, então agrupar os dois lados numa faixa refaria o vínculo que a declaração
    # desfez, com os vértices ainda separados.
    bands = regularise(
        topology,
        freeform_proposal_ids=freeform_ids,
        keep_apart=keep_apart,
        touch_tolerance_px=touch_tolerance_px,
    )
    junction_of = _junction_map(topology)
    order_tie_tolerance_px = touch_tolerance_px
    # A mesma tolerância decide o empate na emissão da restrição: par de faixas desenhadas
    # coincidentes não tem lado, então a cota entre elas vale em módulo (`SpanConstraint`).
    traced_x, traced_y = band_positions(topology, bands)

    constraints: list[SpanConstraint] = []
    applied_spans: list[_AppliedSpan] = []
    unapplied: list[UnappliedReadingReport] = []
    span_outcomes: list[tuple[SpanConstraint, _AppliedSpan]] = []
    for reading_id, targets in sorted(span_targets.items()):
        outcomes = _span_from_reading(
            readings[reading_id],
            [proposal_by_id[proposal_id] for proposal_id in targets],
            junction_of,
            topology,
            bands,
            traced_x=traced_x,
            traced_y=traced_y,
            tie_tolerance_px=order_tie_tolerance_px,
            declared_spans_px=(declared_spans or {}).get(reading_id, []),
            freeform_ids=freeform_ids,
        )
        if isinstance(outcomes, str):
            unapplied.append(
                UnappliedReadingReport(
                    reading_id=reading_id,
                    cause=outcomes,
                    target_proposal_ids=list(targets),
                )
            )
            continue
        for constraint, applied in outcomes:
            constraints.append(constraint)
            applied_spans.append(applied)
            span_outcomes.append((constraint, applied))

    contested = _contested_spans(span_outcomes)

    solved = solve_geometry(
        topology, bands, constraints, order_tie_tolerance_px=order_tie_tolerance_px
    )
    if solved is None:
        return None, constraints, applied_spans, unapplied, contested

    # Espelhamento imagem→CAD: pixel cresce para baixo, o desenho cresce para cima.
    # Normalizar para origem (0,0) no canto inferior esquerdo remove translações
    # arbitrárias do ajuste e dá ao engenheiro a origem que o carimbo declara.
    min_x = min(position[0] for position in solved.positions_m.values())
    max_y = max(position[1] for position in solved.positions_m.values())
    cad_position: dict[int, Point2D] = {
        junction_id: Point2D(x=position[0] - min_x, y=max_y - position[1])
        for junction_id, position in solved.positions_m.items()
    }
    scale_x, offset_x = solved.x_transform
    scale_y, offset_y = solved.y_transform
    state = _GroupState(
        topology=topology,
        bands=bands,
        junction_of=junction_of,
        solved=solved,
        scale_m_per_px=solved.scale_m_per_px,
        cad_position=cad_position,
        x_map=(scale_x, offset_x - min_x),
        y_map=(-scale_y, max_y - offset_y),
        radius_scale=(abs(scale_x) + abs(scale_y)) / 2,
    )
    return state, constraints, applied_spans, unapplied, contested


def solve_trace(
    packet: ReviewPacket,
    proposals: Sequence[VisionProposal],
    acceptance: TraceAcceptance,
    *,
    confirmed_associations: Mapping[str, str | list[str] | Mapping[str, object]],
    note_associations: Mapping[str, str] | None = None,
    derived_dimension_requests: Sequence[DerivedDimensionRequest] = (),
    dimension_texts: Mapping[str, str] | None = None,
    element_declarations: Sequence[TraceElementDeclaration] = (),
    required_criteria: Sequence[ScopeCriterion] = (),
    image_width: int,
    image_height: int,
    feature_id: str = "tracado",
    title: str | None = None,
) -> TraceSolveResult:
    safety_notes = [
        "Pixels e proporções visuais não definem escala nem medida.",
        "Cota confirmada tem precedência sobre o traçado; o resto permanece aproximado.",
        "O resultado solucionado permanece não aprovado até revisão profissional da cena.",
    ]
    proposal_by_id = {proposal.id: proposal for proposal in proposals}
    blockers: list[str] = []
    for proposal_id in acceptance.proposal_ids:
        if proposal_id not in proposal_by_id:
            blockers.append(f"ACCEPTED_PROPOSAL_NOT_FOUND:{proposal_id}")

    # Um proposal_id mede um segmento do elemento; dois medem o vão entre dois elementos;
    # o formato objeto declara vãos entre duas arestas do mesmo elemento, com um par de
    # âncoras em pixel por vão — é como a folha cota a altura de um rebaixo interno.
    span_targets: dict[str, list[str]] = {}
    declared_spans: dict[str, list[tuple[tuple[float, float], tuple[float, float]]]] = {}
    for reading_id, association in confirmed_associations.items():
        if isinstance(association, Mapping):
            parsed = _parse_declared_association(association)
            if parsed is None:
                blockers.append(f"TRACE_ASSOCIATION_INVALID:{reading_id}")
                continue
            proposal_id, anchor_pairs = parsed
            span_targets[reading_id] = [proposal_id]
            declared_spans[reading_id] = anchor_pairs
            continue
        targets = [association] if isinstance(association, str) else list(association)
        if len(targets) not in {1, 2} or len(set(targets)) != len(targets):
            blockers.append(f"TRACE_ASSOCIATION_INVALID:{reading_id}")
            continue
        span_targets[reading_id] = targets
    notes_by_reading = dict(note_associations or {})

    readings = {reading.id: reading for reading in packet.readings}
    accepted_ids = set(acceptance.proposal_ids)
    # "" é a planta principal; qualquer outra chave é o detail_id do grupo dono.
    group_of: dict[str, str] = {proposal_id: "" for proposal_id in acceptance.proposal_ids}
    for detail_group in acceptance.detail_groups:
        for proposal_id in detail_group.proposal_ids:
            group_of[proposal_id] = detail_group.detail_id
    sketch_group_ids = {
        detail_group.detail_id
        for detail_group in acceptance.detail_groups
        if detail_group.mode == "sketch"
    }
    for reading_id in sorted(span_targets):
        targets = span_targets[reading_id]
        touched = {group_of[proposal_id] for proposal_id in targets if proposal_id in group_of}
        if not (touched & sketch_group_ids):
            continue
        if len(targets) == 2:
            blockers.append(f"TRACE_GAP_ON_SKETCH_DETAIL:{reading_id}")
            continue
        # Cota associada a desenho sem escala vira nota presa ao elemento: restringir um
        # sketch mentiria; o número da folha continua visível onde foi escrito.
        notes_by_reading.setdefault(reading_id, targets[0])
        del span_targets[reading_id]
        declared_spans.pop(reading_id, None)
    for request in derived_dimension_requests:
        if group_of.get(request.proposal_id) in sketch_group_ids:
            # Medir desenho sem escala e chamar de `derived` mentiria sobre a origem.
            blockers.append(f"DERIVED_DIMENSION_ON_SKETCH_DETAIL:{request.proposal_id}")

    def _note_target_proposals(target: str) -> list[str]:
        if target == GENERAL_NOTE_TARGET:
            return []
        if target.startswith(LEGEND_NOTE_PREFIX):
            return [target[len(LEGEND_NOTE_PREFIX) :]]
        # Sufixo "#v"/"#h" é dica de orientação do segmento âncora, não parte do id.
        return [target.partition("#")[0]]

    referenced = [
        *((reading_id, targets) for reading_id, targets in sorted(span_targets.items())),
        *(
            (reading_id, _note_target_proposals(proposal_id))
            for reading_id, proposal_id in sorted(notes_by_reading.items())
        ),
    ]
    for request in derived_dimension_requests:
        if request.proposal_id not in accepted_ids:
            blockers.append(f"DERIVED_DIMENSION_TARGET_NOT_ACCEPTED:{request.proposal_id}")
    display_texts = dict(dimension_texts or {})
    for reading_id in display_texts:
        if reading_id not in span_targets:
            blockers.append(f"DIMENSION_TEXT_WITHOUT_SPAN:{reading_id}")
    for reading_id, targets in referenced:
        reading = readings.get(reading_id)
        if reading is None:
            blockers.append(f"TRACE_READING_NOT_FOUND:{reading_id}")
            continue
        if reading.status is not ReadingStatus.CONFIRMED or reading.decision is None:
            blockers.append(f"TRACE_HUMAN_CONFIRMATION_REQUIRED:{reading_id}")
        for proposal_id in targets:
            if proposal_id not in accepted_ids:
                blockers.append(f"ASSOCIATED_PROPOSAL_NOT_ACCEPTED:{reading_id}")
        if reading_id in span_targets:
            # Vão entre grupos não tem sentido: as topologias são independentes e as
            # bandas vivem em espaços distintos — não existe distância a restringir.
            groups_touched = {
                group_of[proposal_id] for proposal_id in targets if proposal_id in group_of
            }
            if len(groups_touched) > 1:
                blockers.append(f"TRACE_ASSOCIATION_CROSSES_DETAIL_GROUP:{reading_id}")

    if blockers:
        return TraceSolveResult(
            status="review_required",
            dataset_id=packet.dataset_id,
            feature_id=feature_id,
            blockers=blockers,
            unapplied_reading_ids=[],
            residuals=[],
            exact_entity_count=0,
            approximate_entity_count=0,
            required_criteria=list(required_criteria),
            safety_notes=safety_notes,
        )

    accepted = [proposal_by_id[proposal_id] for proposal_id in acceptance.proposal_ids]
    # A cota de raio/diâmetro determina o círculo e sai daqui antes das faixas: círculo
    # não tem junção, então o vão ortogonal nunca a alcançaria.
    applied_circles, circle_radius, circle_conflicts = _take_circle_readings(
        span_targets,
        readings=readings,
        proposal_by_id=proposal_by_id,
        declared_spans=declared_spans,
    )
    circle_sources: dict[str, list[str]] = {}
    for circle in sorted(applied_circles, key=lambda item: item.reading_id):
        circle_sources.setdefault(circle.proposal_id, []).extend(
            [circle.reading_id, circle.decision_id]
        )
    span_targets_by_group: dict[str, dict[str, list[str]]] = {}
    for reading_id, targets in span_targets.items():
        span_targets_by_group.setdefault(group_of[targets[0]], {})[reading_id] = targets

    freeform_ids = frozenset(acceptance.freeform_proposal_ids)
    plan_proposals = [proposal for proposal in accepted if group_of[proposal.id] == ""]
    plan_state, _plan_constraints, applied_spans, unapplied, contested_spans = (
        _solve_group_geometry(
            plan_proposals,
            readings=readings,
            span_targets=span_targets_by_group.get("", {}),
            proposal_by_id=proposal_by_id,
            keep_apart=acceptance.keep_apart_separations(),
            image_width=image_width,
            image_height=image_height,
            declared_spans=declared_spans,
            freeform_ids=freeform_ids,
        )
    )
    if plan_state is None:
        return TraceSolveResult(
            status="review_required",
            dataset_id=packet.dataset_id,
            feature_id=feature_id,
            blockers=["NO_CONFIRMED_MEASUREMENT_REACHES_TRACE"],
            unapplied_reading_ids=[report.reading_id for report in unapplied],
            unapplied_readings=unapplied,
            residuals=[],
            exact_entity_count=0,
            approximate_entity_count=0,
            required_criteria=list(required_criteria),
            safety_notes=safety_notes,
        )

    _state_of: dict[str, _GroupState] = {proposal.id: plan_state for proposal in plan_proposals}
    detail_states: dict[str, _GroupState] = {}
    group_members: dict[str, list[VisionProposal]] = {}
    for detail_group in acceptance.detail_groups:
        members = [proposal_by_id[proposal_id] for proposal_id in detail_group.proposal_ids]
        group_members[detail_group.detail_id] = members
        group_tolerance = _group_tolerance_ratio(members, image_width, image_height)
        if detail_group.mode == "sketch":
            detail_state = _sketch_group_geometry(
                members,
                keep_apart=acceptance.keep_apart_separations(),
                image_width=image_width,
                image_height=image_height,
                tolerance_ratio=group_tolerance,
                plan_scale_m_per_px=plan_state.scale_m_per_px,
            )
        else:
            (
                maybe_state,
                _detail_constraints,
                detail_spans,
                detail_unapplied,
                detail_contested,
            ) = _solve_group_geometry(
                members,
                readings=readings,
                span_targets=span_targets_by_group.get(detail_group.detail_id, {}),
                proposal_by_id=proposal_by_id,
                keep_apart=acceptance.keep_apart_separations(),
                image_width=image_width,
                image_height=image_height,
                tolerance_ratio=group_tolerance,
                declared_spans=declared_spans,
                freeform_ids=freeform_ids,
            )
            if maybe_state is None:
                return TraceSolveResult(
                    status="review_required",
                    dataset_id=packet.dataset_id,
                    feature_id=feature_id,
                    blockers=[f"DETAIL_GROUP_WITHOUT_APPLIED_READING:{detail_group.detail_id}"],
                    unapplied_reading_ids=[
                        report.reading_id for report in (*unapplied, *detail_unapplied)
                    ],
                    unapplied_readings=[*unapplied, *detail_unapplied],
                    residuals=[],
                    exact_entity_count=0,
                    approximate_entity_count=0,
                    required_criteria=list(required_criteria),
                    safety_notes=safety_notes,
                )
            detail_state = maybe_state
            applied_spans.extend(detail_spans)
            unapplied.extend(detail_unapplied)
            contested_spans.extend(detail_contested)
        detail_states[detail_group.detail_id] = detail_state
        for member in members:
            _state_of[member.id] = detail_state

    # Coluna de detalhes entre a planta e a legenda: cada grupo é transladado antes de
    # existir qualquer entidade, então todo o downstream (cotas, notas, obstáculos,
    # legenda, carimbo) opera num único espaço final da prancha.
    plan_bbox = _state_bbox(plan_state, plan_proposals)
    plan_state.centre = (
        (plan_bbox[0] + plan_bbox[2]) / 2,
        (plan_bbox[1] + plan_bbox[3]) / 2,
    )
    plan_diagonal = math.hypot(plan_bbox[2] - plan_bbox[0], plan_bbox[3] - plan_bbox[1])
    detail_bboxes: dict[str, tuple[float, float, float, float]] = {}
    column_x = plan_bbox[2] + plan_diagonal * 0.18
    column_top = plan_bbox[3]
    # As cotas, notas e o título transbordam o bbox da geometria do grupo, e a moldura
    # cresce com eles depois — o vão entre grupos precisa reservar essa folga agora,
    # senão molduras vizinhas se sobrepõem. Seis alturas de texto cobrem o pior caso
    # observado (cota empilhada + nota + título).
    annotation_allowance = dimension_text_height(plan_diagonal) * 6
    for detail_group in acceptance.detail_groups:
        detail_state = detail_states[detail_group.detail_id]
        members = group_members[detail_group.detail_id]
        local_bbox = _state_bbox(detail_state, members)
        group_diagonal = math.hypot(local_bbox[2] - local_bbox[0], local_bbox[3] - local_bbox[1])
        dx = column_x - local_bbox[0]
        dy = (column_top - annotation_allowance) - local_bbox[3]
        detail_state.translate(dx, dy)
        placed_bbox = (
            local_bbox[0] + dx,
            local_bbox[1] + dy,
            local_bbox[2] + dx,
            local_bbox[3] + dy,
        )
        detail_bboxes[detail_group.detail_id] = placed_bbox
        detail_state.centre = (
            (placed_bbox[0] + placed_bbox[2]) / 2,
            (placed_bbox[1] + placed_bbox[3]) / 2,
        )
        column_top = placed_bbox[1] - group_diagonal * 0.3 - annotation_allowance

    entities: list[Entity] = []
    issues: list[Issue] = []
    accepted_approximations: set[UUID] = set()
    entity_by_proposal: dict[str, Entity] = {}
    labelled: list[tuple[Entity, str]] = []
    # Nota com alvo "legenda:<id>": o texto confirmado viaja na linha de legenda do
    # elemento, e nada flutua no desenho além da cota e do balão.
    legend_note_texts: dict[str, list[str]] = {}
    for reading_id, note_target in sorted(notes_by_reading.items()):
        if note_target.startswith(LEGEND_NOTE_PREFIX):
            legend_note_texts.setdefault(note_target[len(LEGEND_NOTE_PREFIX) :], []).append(
                readings[reading_id].raw_text[:200]
            )
    exact_count = 0
    approximate_count = 0
    hatch_ids = set(acceptance.hatch_proposal_ids)

    # ADR-0063, decisão 2: o traçado TRANSPORTA a identidade declarada na revisão sobre
    # propostas. Só as ATIVAS viajam, e só as das propostas que o aceite em lote incluiu —
    # proposta declarada e depois não aceita não vira entidade, e um rótulo apontando para
    # ref que nenhuma entidade usa é órfão, que `SceneRevision` recusa
    # (`ELEMENT_LABEL_UNKNOWN_REF`).
    element_ref_of_proposal: dict[str, str] = {}
    label_of_element: dict[str, str] = {}
    for declaration in element_declarations:
        if declaration.status != "active":
            continue
        if declaration.label is not None:
            label_of_element[declaration.element_ref] = declaration.label
        for declared_id in declaration.proposal_ids:
            if declared_id not in accepted_ids:
                continue
            previous = element_ref_of_proposal.get(declared_id)
            if previous is not None and previous != declaration.element_ref:
                # A API recusa isso no ato (`ELEMENT_ALREADY_DECLARED`): mover proposta de um
                # elemento para outro são dois atos. Se chegou aqui, a revisão está corrompida
                # e eleger um dos dois refs em silêncio daria identidade errada a geometria
                # real — o traçado recusa em vez de escolher.
                blockers.append(f"TRACE_ELEMENT_DECLARATION_CONFLICT:{declared_id}")
                continue
            element_ref_of_proposal[declared_id] = declaration.element_ref
    proposals_of_element: dict[str, list[str]] = {}
    for declared_id, declared_ref in element_ref_of_proposal.items():
        proposals_of_element.setdefault(declared_ref, []).append(declared_id)

    # A camada nasce por proposta, mas a cena exige camada ÚNICA por `element_ref`
    # (`ELEMENT_REF_LAYER_MISMATCH`, `SceneRevision.validate_references`). Quem declarou o
    # elemento na revisão não tinha como saber em que camada cada proposta cairia: isso só se
    # decide aqui, quando o solver diz quais distâncias ficaram determinadas. Então o traçado
    # harmoniza — se as propostas do elemento discordam de camada, o elemento inteiro é
    # desenhado em `APROXIMADO`, a única camada que não afirma natureza nenhuma e que nunca
    # promove traçado de pixel a camada semântica. Eleger uma das camadas semânticas
    # discordantes seria o traçado afirmando "isto é muro" sobre o que ninguém afirmou.
    layer_of_proposal: dict[str, LayerName] = {}
    exact_of_proposal: dict[str, bool] = {}
    junctions_of_proposal: dict[str, list[int]] = {}
    for proposal in accepted:
        state = _state_of[proposal.id]
        junctions = _proposal_junctions(proposal, state.junction_of)
        junctions_of_proposal[proposal.id] = junctions
        exact = (
            state.solved is not None
            and bool(junctions)
            and state.solved.junctions_are_determined(state.bands, junctions)
        )
        exact_of_proposal[proposal.id] = exact
        if isinstance(proposal.geometry, PixelLine | PixelPolyline):
            layer_of_proposal[proposal.id] = _layer_for(proposal, exact=exact)
        elif proposal.id in circle_radius:
            layer_of_proposal[proposal.id] = _layer_for(proposal, exact=True)
        else:
            layer_of_proposal[proposal.id] = LayerName.APROXIMADO
    harmonised_elements = [
        element_ref
        for element_ref, member_ids in sorted(proposals_of_element.items())
        if len({layer_of_proposal[member_id] for member_id in member_ids}) > 1
    ]
    for element_ref in harmonised_elements:
        for member_id in proposals_of_element[element_ref]:
            layer_of_proposal[member_id] = LayerName.APROXIMADO

    for proposal in accepted:
        geometry = proposal.geometry
        state = _state_of[proposal.id]
        detail_key = group_of[proposal.id]
        detail_tag = [f"detail:{detail_key}"] if detail_key else []
        junctions = junctions_of_proposal[proposal.id]
        exact = exact_of_proposal[proposal.id]
        layer = layer_of_proposal[proposal.id]
        element_ref_of_entity = element_ref_of_proposal.get(proposal.id)
        precision = Precision.EXACT if exact else Precision.APPROXIMATE
        if state.solved is None:
            summary_code = "DETAIL_SKETCH_AS_DRAWN"
        elif exact:
            summary_code = "TRACED_SPAN_DETERMINED_BY_CONFIRMED_READINGS"
        else:
            summary_code = "TRACED_BATCH_ACCEPTED_APPROXIMATE"
        provenance = Provenance(
            source_type=TRACE_SOURCE_TYPE,
            source_ids=[proposal.id, acceptance.acceptance_id, *detail_tag],
            summary_code=summary_code,
        )
        entity_id = _uuid(packet.dataset_id, feature_id, f"proposal:{proposal.id}")
        if isinstance(geometry, PixelLine):
            entity = Entity(
                id=entity_id,
                kind=EntityKind.LINE,
                layer=layer,
                precision=precision,
                geometry=LineGeometry(
                    start=state.cad_position[junctions[0]],
                    end=state.cad_position[junctions[1]],
                ),
                provenance=provenance,
                element_ref=element_ref_of_entity,
            )
        elif isinstance(geometry, PixelPolyline):
            entity = Entity(
                id=entity_id,
                kind=EntityKind.POLYLINE,
                layer=layer,
                precision=precision,
                geometry=PolylineGeometry(
                    points=[state.cad_position[junction] for junction in junctions],
                    closed=geometry.closed,
                ),
                provenance=provenance,
                fill="hatch" if proposal.id in hatch_ids and geometry.closed else "none",
                element_ref=element_ref_of_entity,
            )
            if proposal.id in hatch_ids and not geometry.closed:
                blockers.append(f"HATCH_TARGET_NOT_CLOSED:{proposal.id}")
        elif proposal.id in circle_radius:
            # Cota confirmada de raio/diâmetro manda no círculo, como manda no vão: o
            # raio vem da folha e a entidade sai `exact`. O centro continua vindo do
            # traçado — é a posição, não a medida, que o croqui distorce.
            entity = Entity(
                id=entity_id,
                kind=EntityKind.CIRCLE,
                layer=layer,
                precision=Precision.EXACT,
                geometry=CircleGeometry(
                    center=state.cad_point(geometry.center),
                    radius=float(circle_radius[proposal.id]),
                ),
                provenance=Provenance(
                    source_type=TRACE_SOURCE_TYPE,
                    source_ids=[
                        proposal.id,
                        *circle_sources.get(proposal.id, []),
                        acceptance.acceptance_id,
                        *detail_tag,
                    ],
                    summary_code="TRACED_CIRCLE_DETERMINED_BY_CONFIRMED_READING",
                ),
                element_ref=element_ref_of_entity,
            )
        else:
            # Círculo sem leitura confirmada de raio/diâmetro permanece círculo com raio
            # pela escala média dos eixos: a distorção é do papel, não do objeto — e
            # permanece `approximate`, nunca promovido.
            entity = Entity(
                id=entity_id,
                kind=EntityKind.CIRCLE,
                layer=layer,
                precision=Precision.APPROXIMATE,
                geometry=CircleGeometry(
                    center=state.cad_point(geometry.center),
                    radius=geometry.radius * state.radius_scale,
                ),
                provenance=provenance,
                element_ref=element_ref_of_entity,
            )
        if entity.precision is Precision.APPROXIMATE:
            accepted_approximations.add(entity.id)
            approximate_count += 1
        else:
            exact_count += 1
        entities.append(entity)
        entity_by_proposal[proposal.id] = entity
        display_label = proposal.label or ""
        if proposal.id in legend_note_texts:
            spec = " | ".join(legend_note_texts[proposal.id])
            display_label = f"{display_label} — {spec}" if display_label else spec
        if display_label and proposal.id not in acceptance.unlabelled_proposal_ids:
            labelled.append((entity, display_label))

    for element_ref in harmonised_elements:
        # Rebaixar camada em silêncio é o tipo de mudança que ninguém vê na prancha e todo
        # mundo herda: a harmonização vira aviso na cena, com as entidades do elemento
        # nomeadas. Aviso, não crítica — o desenho continua exportável, e quem revisa decide
        # se prefere declarar um elemento por camada.
        issues.append(
            Issue(
                id=_uuid(packet.dataset_id, feature_id, f"issue:element-layer:{element_ref}"),
                code="ELEMENT_LAYER_HARMONISED",
                severity=IssueSeverity.WARNING,
                message=(
                    f"Elemento {element_ref}: as propostas declaradas caíram em camadas "
                    "diferentes no traçado; o elemento inteiro foi desenhado em APROXIMADO."
                ),
                entity_ids=[
                    entity_by_proposal[member_id].id
                    for member_id in proposals_of_element[element_ref]
                ],
            )
        )

    measurements: list[Measurement] = []
    scene_constraints: list[Constraint] = []
    residuals: list[SolverResidual] = []
    dimension_entities: list[Entity] = []
    dimension_obstacles: list[tuple[float, float, float, float]] = []
    # Caixas colocadas por grupo de detalhe: dimensionam a moldura depois. A colisão em
    # si continua na lista global — com tudo já transladado, colisão entre grupos é real.
    group_boxes: dict[str, list[tuple[float, float, float, float]]] = {
        detail_group.detail_id: [] for detail_group in acceptance.detail_groups
    }
    # A tipografia da prancha segue a planta: um detalhe na coluna à direita não pode
    # inflar a diagonal e mudar a altura de todos os textos.
    plan_entities = [
        entity_by_proposal[proposal.id]
        for proposal in plan_proposals
        if proposal.id in entity_by_proposal
    ]
    trace_extent = _extent(plan_entities)
    trace_diagonal = (
        math.hypot(trace_extent[2] - trace_extent[0], trace_extent[3] - trace_extent[1])
        if trace_extent is not None
        else 0.0
    )
    # "Para fora" é medido do centro da extensão, não do centroide de junções: a
    # densidade de vértices das marcações puxaria o centroide e viraria cota para dentro.
    if trace_extent is not None:
        centroid_x = (trace_extent[0] + trace_extent[2]) / 2
        centroid_y = (trace_extent[1] + trace_extent[3]) / 2
    else:
        centroid_x, centroid_y = plan_state.centre
    plan_state.centre = (centroid_x, centroid_y)
    dim_text_height = dimension_text_height(trace_diagonal)

    # Uma leitura com vãos declarados aplica o mesmo valor em mais de um trecho (as duas
    # pontas cheias do painel); cada ocorrência precisa de constraint e DIMENSION próprias.
    span_occurrences: dict[str, int] = {}
    applied_span_reports: list[AppliedSpanReport] = []
    for span in applied_spans:
        occurrence = span_occurrences.get(span.reading_id, 0)
        span_occurrences[span.reading_id] = occurrence + 1
        occurrence_suffix = "" if occurrence == 0 else f":{occurrence}"
        span_state = _state_of[span.proposal_id]
        span_group = group_of[span.proposal_id]
        span_centre_x, span_centre_y = span_state.centre
        if span.gap:
            # O vão é medido entre as duas faixas, na vertical/horizontal do recorte que
            # o revisor confirmou — as junções representativas podem estar deslocadas.
            evidence = span_state.cad_point(PixelPoint(x=span.evidence_x_px, y=span.evidence_y_px))
            near = span_state.cad_position[span.first_junction]
            far = span_state.cad_position[span.second_junction]
            if span.axis == "y":
                first = Point2D(x=evidence.x, y=min(near.y, far.y))
                second = Point2D(x=evidence.x, y=max(near.y, far.y))
            else:
                first = Point2D(x=min(near.x, far.x), y=evidence.y)
                second = Point2D(x=max(near.x, far.x), y=evidence.y)
        else:
            first = span_state.cad_position[span.first_junction]
            second = span_state.cad_position[span.second_junction]
        # Onde a cota ancorou, em metros da prancha: as duas pontas ao longo do eixo dela.
        # `first`/`second` já estão no frame CAD (origem no canto inferior esquerdo), e o
        # relatório sai ordenado porque "de onde até onde" não depende de qual ponta o
        # traçado elegeu primeiro.
        span_anchor_a = first.x if span.axis == "x" else first.y
        span_anchor_b = second.x if span.axis == "x" else second.y
        applied_span_reports.append(
            AppliedSpanReport(
                reading_id=span.reading_id,
                axis=span.axis,
                value_m=span.value_m,
                start_m=min(span_anchor_a, span_anchor_b),
                end_m=max(span_anchor_a, span_anchor_b),
                proposal_id=span.proposal_id,
                second_proposal_id=span.second_proposal_id,
                gap=span.gap,
            )
        )
        actual = math.hypot(second.x - first.x, second.y - first.y)
        tolerance = _span_tolerance_m(span)
        residual = SolverResidual(
            code=f"{'GAP' if span.gap else 'SPAN'}_RESIDUAL_{span.axis.upper()}",
            expected_m=span.value_m,
            actual_m=Decimal(str(round(actual, 9))),
            absolute_error_m=abs(span.value_m - Decimal(str(round(actual, 9)))),
            tolerance_m=tolerance,
            passed=abs(span.value_m - Decimal(str(round(actual, 9)))) <= tolerance,
        )
        residuals.append(residual)

        target = entity_by_proposal[span.proposal_id]
        span_source_ids = [span.reading_id, span.decision_id, span.proposal_id]
        if span.second_proposal_id is not None:
            span_source_ids.append(span.second_proposal_id)
        span_provenance = Provenance(
            source_type=SPAN_SOURCE_TYPE,
            source_ids=span_source_ids,
            summary_code=(
                "CONFIRMED_READING_OVER_ELEMENT_GAP"
                if span.gap
                else "CONFIRMED_READING_OVER_TRACED_SPAN"
            ),
        )
        if not span.gap:
            # Vão entre elementos não é medida de uma entidade só; fica como constraint.
            measurements.append(
                Measurement(
                    id=_uuid(packet.dataset_id, feature_id, f"measurement:{span.reading_id}"),
                    entity_id=target.id,
                    kind=readings[span.reading_id].kind,
                    raw_text=span.raw_text,
                    value_si=span.value_m,
                    unit=UnitCode.METRE,
                    written_decimals=span.written_decimals,
                    confirmed=True,
                    provenance=span_provenance,
                )
            )
        constraint_entity_ids = [target.id]
        if span.second_proposal_id is not None:
            constraint_entity_ids.append(entity_by_proposal[span.second_proposal_id].id)
        scene_constraints.append(
            Constraint(
                id=_uuid(
                    packet.dataset_id,
                    feature_id,
                    f"constraint:{span.reading_id}{occurrence_suffix}",
                ),
                kind="element_gap_from_confirmed_reading"
                if span.gap
                else "axis_span_from_confirmed_reading",
                entity_ids=constraint_entity_ids,
                tolerance=float(tolerance),
                hard=True,
                satisfied=residual.passed,
            )
        )

        # A cota desenhada afasta-se do miolo do desenho, nunca por cima dele.
        direction_x = (second.x - first.x) / actual if actual > 1e-9 else 1.0
        direction_y = (second.y - first.y) / actual if actual > 1e-9 else 0.0
        normal_x, normal_y = -direction_y, direction_x
        mid_x, mid_y = (first.x + second.x) / 2, (first.y + second.y) / 2
        away = (mid_x - span_centre_x) * normal_x + (mid_y - span_centre_y) * normal_y
        sign = 1.0 if away >= 0 else -1.0
        offset = max(1.0, actual * 0.08)
        # O revisor pode declarar o texto exibido (vão de portão mostra "1,0 x 2,05");
        # a medida real continua na geometria e no resíduo — o texto é apresentação.
        dimension_text = display_texts.get(span.reading_id, f"{span.value_m} m")
        half_width = estimated_width(dimension_text, dim_text_height) * 0.6 * CAD_FONT_SAFETY

        # Cotas do mesmo lado empilham: afasta em degraus até o texto ter faixa livre.
        # O texto da cota não fica do lado da base: com `dimtad=1` ele senta sempre
        # acima da linha na direção de leitura — +y na horizontal, -x na vertical
        # (ângulo normalizado para +90 lê de baixo para cima). A caixa segue o render.
        text_obstacle = (0.0, 0.0, 0.0, 0.0)
        for _ in range(7):
            if span.axis == "y":
                line_x = first.x + normal_x * offset * sign
                centre_x = line_x - dim_text_height
                text_obstacle = (
                    centre_x - dim_text_height,
                    mid_y - half_width,
                    centre_x + dim_text_height,
                    mid_y + half_width,
                )
            else:
                line_y = first.y + normal_y * offset * sign
                centre_y = line_y + dim_text_height
                text_obstacle = (
                    mid_x - half_width,
                    centre_y - dim_text_height,
                    mid_x + half_width,
                    centre_y + dim_text_height,
                )
            if not any(boxes_overlap(text_obstacle, other) for other in dimension_obstacles):
                break
            offset += dim_text_height * 2.2
        dimension_obstacles.append(text_obstacle)
        if span_group:
            group_boxes[span_group].append(text_obstacle)
        # As linhas de extensão da cota também ocupam a folha: registrar faixas finas
        # ao longo delas impede que texto de outra cota ou nota pouse em cima.
        extension_dx = normal_x * offset * sign
        extension_dy = normal_y * offset * sign
        for extension_point in (first, second):
            extension_box = (
                min(extension_point.x, extension_point.x + extension_dx) - 0.12,
                min(extension_point.y, extension_point.y + extension_dy) - 0.12,
                max(extension_point.x, extension_point.x + extension_dx) + 0.12,
                max(extension_point.y, extension_point.y + extension_dy) + 0.12,
            )
            dimension_obstacles.append(extension_box)
            if span_group:
                group_boxes[span_group].append(extension_box)

        dimension_entities.append(
            Entity(
                id=_uuid(
                    packet.dataset_id, feature_id, f"dimension:{span.reading_id}{occurrence_suffix}"
                ),
                kind=EntityKind.DIMENSION,
                layer=LayerName.COTAS,
                precision=Precision.EXACT,
                geometry=DimensionGeometry(
                    first=first,
                    second=second,
                    base=Point2D(
                        x=first.x + normal_x * offset * sign,
                        y=first.y + normal_y * offset * sign,
                    ),
                    text_override=dimension_text,
                ),
                provenance=span_provenance,
            )
        )

    # Cota de raio/diâmetro sobre círculo: o raio já saiu da folha no ramo da entidade;
    # aqui a leitura vira medida confirmada amarrada ao círculo e cota diametral (⌀)
    # desenhada no ângulo em que o croqui a escreveu — a evidência decide a posição.
    for circle in sorted(applied_circles, key=lambda item: item.reading_id):
        circle_entity = entity_by_proposal[circle.proposal_id]
        circle_geometry = circle_entity.geometry
        if not isinstance(circle_geometry, CircleGeometry):  # pragma: no cover - só círculo
            continue
        circle_state = _state_of[circle.proposal_id]
        circle_group = group_of[circle.proposal_id]
        circle_provenance = Provenance(
            source_type=SPAN_SOURCE_TYPE,
            source_ids=[circle.reading_id, circle.decision_id, circle.proposal_id],
            summary_code="CONFIRMED_READING_OVER_CIRCLE",
        )
        # `kind` da leitura, valor como escrito: `_measured_value` do core devolve raio
        # ou diâmetro conforme o kind, e é essa coerência que o portão de export confere.
        measurements.append(
            Measurement(
                id=_uuid(packet.dataset_id, feature_id, f"measurement:{circle.reading_id}"),
                entity_id=circle_entity.id,
                kind=circle.kind,
                raw_text=circle.raw_text,
                value_si=circle.value_m,
                unit=UnitCode.METRE,
                written_decimals=circle.written_decimals,
                confirmed=True,
                provenance=circle_provenance,
            )
        )
        circle_centre = circle_geometry.center
        evidence_cad = circle_state.cad_point(
            PixelPoint(x=circle.evidence_x_px, y=circle.evidence_y_px)
        )
        circle_angle = math.atan2(
            evidence_cad.y - circle_centre.y, evidence_cad.x - circle_centre.x
        )
        diameter_m = (
            circle.value_m if circle.kind is MeasurementKind.DIAMETER else circle.value_m * 2
        )
        circle_text = display_texts.get(circle.reading_id, f"⌀ {diameter_m} m")
        # O texto da cota diametral pousa fora do círculo, na direção da evidência: a
        # caixa vira obstáculo para notas e balões, mas a cota não desvia de ninguém.
        text_distance = circle_geometry.radius + dim_text_height * 1.5
        text_centre_x = circle_centre.x + math.cos(circle_angle) * text_distance
        text_centre_y = circle_centre.y + math.sin(circle_angle) * text_distance
        half_width = estimated_width(circle_text, dim_text_height) * 0.6 * CAD_FONT_SAFETY
        circle_text_box = (
            text_centre_x - half_width,
            text_centre_y - dim_text_height,
            text_centre_x + half_width,
            text_centre_y + dim_text_height,
        )
        dimension_obstacles.append(circle_text_box)
        if circle_group:
            group_boxes[circle_group].append(circle_text_box)
        dimension_entities.append(
            Entity(
                id=_uuid(packet.dataset_id, feature_id, f"dimension:{circle.reading_id}"),
                kind=EntityKind.DIAMETER_DIMENSION,
                layer=LayerName.COTAS,
                precision=Precision.EXACT,
                geometry=DiameterDimensionGeometry(
                    center=Point2D(x=circle_centre.x, y=circle_centre.y),
                    radius=circle_geometry.radius,
                    angle=circle_angle,
                    text_override=circle_text,
                ),
                provenance=circle_provenance,
            )
        )

    # Cota derivada: o revisor pede a medida de um trecho desenhado (o 1,50 do recuo),
    # e o número sai da geometria resolvida — `derived`, nunca fingindo leitura da folha.
    for request in derived_dimension_requests:
        request_proposal = proposal_by_id[request.proposal_id]
        request_state = _state_of[request.proposal_id]
        request_group = group_of[request.proposal_id]
        request_centre_x, request_centre_y = request_state.centre
        request_junctions = _proposal_junctions(request_proposal, request_state.junction_of)
        request_segments = _candidate_segments(
            request_proposal, request_junctions, (request.near_x_px, request.near_y_px)
        )
        derived_pair: tuple[Point2D, Point2D] | None = None
        if request_segments and request_segments[0][0] != request_segments[0][1]:
            derived_pair = (
                request_state.cad_position[request_segments[0][0]],
                request_state.cad_position[request_segments[0][1]],
            )
        if derived_pair is None:
            issues.append(
                Issue(
                    id=_uuid(
                        packet.dataset_id,
                        feature_id,
                        f"issue:derived:{request.proposal_id}:{request.near_x_px}",
                    ),
                    code="DERIVED_DIMENSION_NOT_APPLIED",
                    severity=IssueSeverity.WARNING,
                    message=(
                        f"O pedido de cota derivada sobre {request.proposal_id} não achou "
                        "segmento mensurável perto do ponto indicado."
                    ),
                )
            )
            continue
        first, second = derived_pair
        actual = math.hypot(second.x - first.x, second.y - first.y)
        if actual < 1e-9:
            continue
        direction_x = (second.x - first.x) / actual
        direction_y = (second.y - first.y) / actual
        normal_x, normal_y = -direction_y, direction_x
        mid_x, mid_y = (first.x + second.x) / 2, (first.y + second.y) / 2
        away = (mid_x - request_centre_x) * normal_x + (mid_y - request_centre_y) * normal_y
        sign = 1.0 if away >= 0 else -1.0
        offset = max(1.0, actual * 0.08)
        dimension_text = request.text or f"{actual:.2f} m"
        half_width = estimated_width(dimension_text, dim_text_height) * 0.6 * CAD_FONT_SAFETY
        text_obstacle = (0.0, 0.0, 0.0, 0.0)
        vertical = abs(direction_y) > abs(direction_x)
        for _ in range(7):
            if vertical:
                line_x = first.x + normal_x * offset * sign
                centre_x = line_x - dim_text_height
                text_obstacle = (
                    centre_x - dim_text_height,
                    mid_y - half_width,
                    centre_x + dim_text_height,
                    mid_y + half_width,
                )
            else:
                line_y = first.y + normal_y * offset * sign
                centre_y = line_y + dim_text_height
                text_obstacle = (
                    mid_x - half_width,
                    centre_y - dim_text_height,
                    mid_x + half_width,
                    centre_y + dim_text_height,
                )
            if not any(boxes_overlap(text_obstacle, other) for other in dimension_obstacles):
                break
            offset += dim_text_height * 2.2
        dimension_obstacles.append(text_obstacle)
        if request_group:
            group_boxes[request_group].append(text_obstacle)
        # As linhas de extensão da cota também ocupam a folha: registrar faixas finas
        # ao longo delas impede que texto de outra cota ou nota pouse em cima.
        extension_dx = normal_x * offset * sign
        extension_dy = normal_y * offset * sign
        for extension_point in (first, second):
            extension_box = (
                min(extension_point.x, extension_point.x + extension_dx) - 0.12,
                min(extension_point.y, extension_point.y + extension_dy) - 0.12,
                max(extension_point.x, extension_point.x + extension_dx) + 0.12,
                max(extension_point.y, extension_point.y + extension_dy) + 0.12,
            )
            dimension_obstacles.append(extension_box)
            if request_group:
                group_boxes[request_group].append(extension_box)
        dimension_entities.append(
            Entity(
                id=_uuid(
                    packet.dataset_id,
                    feature_id,
                    f"derived-dimension:{request.proposal_id}:{request.near_x_px}",
                ),
                kind=EntityKind.DIMENSION,
                layer=LayerName.COTAS,
                precision=Precision.DERIVED,
                geometry=DimensionGeometry(
                    first=first,
                    second=second,
                    base=Point2D(
                        x=first.x + normal_x * offset * sign,
                        y=first.y + normal_y * offset * sign,
                    ),
                    text_override=dimension_text,
                ),
                provenance=Provenance(
                    source_type=TRACER_VERSION,
                    source_ids=[request.proposal_id, acceptance.acceptance_id],
                    summary_code="DERIVED_SPAN_DIMENSIONED",
                ),
            )
        )

    # Anotações confirmadas (h=, Portão NxM, traves…): altura e especificação não
    # existem em planta — viram texto preso ao elemento, como um projetista anotaria.
    note_entities: list[Entity] = []
    general_notes: list[tuple[str, str, Provenance]] = []
    for reading_id, note_proposal_id in sorted(notes_by_reading.items()):
        note_reading = readings[reading_id]
        note_decision = note_reading.decision
        assert note_decision is not None  # garantido pela validação de blockers
        if note_proposal_id == GENERAL_NOTE_TARGET:
            # Nota geral (tela aérea…): descreve o conjunto, não uma aresta — vai para
            # o carimbo, acima do título, em vez de flutuar sobre o desenho.
            general_notes.append(
                (
                    reading_id,
                    note_reading.raw_text[:500],
                    Provenance(
                        source_type=NOTE_SOURCE_TYPE,
                        source_ids=[reading_id, note_decision.decision_id],
                        summary_code="CONFIRMED_READING_AS_GENERAL_NOTE",
                    ),
                )
            )
            continue
        if note_proposal_id.startswith(LEGEND_NOTE_PREFIX):
            # Já anexada à linha de legenda do elemento; nada flutua no desenho.
            continue
        base_target, _, orientation_hint = note_proposal_id.partition("#")
        note_proposal = proposal_by_id[base_target]
        note_state = _state_of[base_target]
        note_group = group_of[base_target]
        note_centre_x, note_centre_y = note_state.centre
        note_bbox = note_reading.evidence.bbox
        note_centre = (
            (note_bbox.left + note_bbox.right) / 2,
            (note_bbox.top + note_bbox.bottom) / 2,
        )
        note_junctions = _proposal_junctions(note_proposal, note_state.junction_of)
        note_segments = _candidate_segments(note_proposal, note_junctions, note_centre)
        if orientation_hint in {"v", "h"}:
            # O revisor declara em que aresta a marcação prende (o h= da entrada fica
            # na linha vertical do vão, mesmo que a horizontal esteja mais perto).
            note_segments = [
                (first_j, second_j)
                for first_j, second_j in note_segments
                if (
                    abs(note_state.cad_position[second_j].y - note_state.cad_position[first_j].y)
                    >= abs(note_state.cad_position[second_j].x - note_state.cad_position[first_j].x)
                )
                == (orientation_hint == "v")
            ]
        if note_segments and note_segments[0][0] != note_segments[0][1]:
            anchor_a = note_state.cad_position[note_segments[0][0]]
            anchor_b = note_state.cad_position[note_segments[0][1]]
            length = math.hypot(anchor_b.x - anchor_a.x, anchor_b.y - anchor_a.y)
            if length < 1e-9:
                unapplied.append(
                    UnappliedReadingReport(
                        reading_id=reading_id,
                        cause="TRACE_NOTE_ZERO_LENGTH",
                        target_proposal_ids=[base_target],
                    )
                )
                continue
            unit_x = (anchor_b.x - anchor_a.x) / length
            unit_y = (anchor_b.y - anchor_a.y) / length
            # A nota pousa onde o croqui a escreveu: projeção da evidência sobre o
            # segmento (limitada para não cair fora dele), não no ponto médio.
            evidence_cad = note_state.cad_point(PixelPoint(x=note_centre[0], y=note_centre[1]))
            along = (
                (evidence_cad.x - anchor_a.x) * (anchor_b.x - anchor_a.x)
                + (evidence_cad.y - anchor_a.y) * (anchor_b.y - anchor_a.y)
            ) / (length * length)
            along = min(0.92, max(0.08, along))
            note_mid = Point2D(
                x=anchor_a.x + (anchor_b.x - anchor_a.x) * along,
                y=anchor_a.y + (anchor_b.y - anchor_a.y) * along,
            )
        elif isinstance(note_proposal.geometry, PixelCircle):
            circle_centre = note_state.cad_point(note_proposal.geometry.center)
            note_mid = Point2D(
                x=circle_centre.x,
                y=circle_centre.y + note_proposal.geometry.radius * note_state.radius_scale,
            )
            unit_x, unit_y = 1.0, 0.0
        else:
            unapplied.append(
                UnappliedReadingReport(
                    reading_id=reading_id,
                    cause="TRACE_NOTE_UNSUPPORTED_GEOMETRY",
                    target_proposal_ids=[base_target],
                )
            )
            continue

        rotation = math.atan2(unit_y, unit_x)
        # Nunca de cabeça para baixo: meio giro não muda a direção do elemento.
        if rotation > math.pi / 2:
            rotation -= math.pi
            unit_x, unit_y = -unit_x, -unit_y
        elif rotation <= -math.pi / 2:
            rotation += math.pi
            unit_x, unit_y = -unit_x, -unit_y
        note_normal_x, note_normal_y = -unit_y, unit_x
        note_away = (note_mid.x - note_centre_x) * note_normal_x + (
            note_mid.y - note_centre_y
        ) * note_normal_y
        note_sign = 1.0 if note_away >= 0 else -1.0

        note_text = note_reading.raw_text[:500]
        short_note = len(note_text) <= SHORT_NOTE_MAX_CHARS
        note_height = dim_text_height * (
            SHORT_NOTE_HEIGHT_RATIO if short_note else NOTE_TEXT_HEIGHT_RATIO
        )
        note_width = estimated_width(note_text, note_height)
        note_cx, note_cy, note_box_placed = _note_position(
            note_mid,
            (unit_x, unit_y),
            (note_normal_x, note_normal_y),
            # Marcação curta (h=…) fica do lado de dentro, como no croqui da entrada.
            -note_sign if short_note else note_sign,
            # A caixa leva a folga de fonte de CAD; a inserção usa a largura estimada.
            width=note_width * CAD_FONT_SAFETY,
            height=note_height,
            obstacles=dimension_obstacles,
        )
        dimension_obstacles.append(note_box_placed)
        if note_group:
            group_boxes[note_group].append(note_box_placed)

        if short_note:
            # O "risco" do croqui: um traço vermelho ligando a marcação ao ponto da
            # linha a que ela se refere. Vermelho = layer COTAS; anotação, não medida.
            tick_provenance = Provenance(
                source_type=NOTE_SOURCE_TYPE,
                source_ids=[reading_id, note_decision.decision_id, base_target],
                summary_code="NOTE_LEADER_TICK",
            )
            note_entities.append(
                Entity(
                    id=_uuid(packet.dataset_id, feature_id, f"note-tick:{reading_id}"),
                    kind=EntityKind.LINE,
                    layer=LayerName.COTAS,
                    precision=Precision.DERIVED,
                    geometry=LineGeometry(
                        start=note_mid,
                        end=Point2D(
                            x=note_mid.x + (note_cx - note_mid.x) * 0.75,
                            y=note_mid.y + (note_cy - note_mid.y) * 0.75,
                        ),
                    ),
                    provenance=tick_provenance,
                )
            )

        note_entities.append(
            Entity(
                id=_uuid(packet.dataset_id, feature_id, f"note:{reading_id}"),
                kind=EntityKind.TEXT,
                layer=LayerName.TEXTOS,
                precision=Precision.EXACT,
                geometry=TextGeometry(
                    insertion=Point2D(
                        x=note_cx - unit_x * note_width / 2 + unit_y * note_height / 2,
                        y=note_cy - unit_y * note_width / 2 - unit_x * note_height / 2,
                    ),
                    text=note_text,
                    height=note_height,
                    rotation=rotation,
                ),
                provenance=Provenance(
                    source_type=NOTE_SOURCE_TYPE,
                    source_ids=[reading_id, note_decision.decision_id, base_target],
                    summary_code="CONFIRMED_READING_AS_NOTE",
                ),
            )
        )

    if any(not residual.passed for residual in residuals):
        blockers.append("NUMERIC_RESIDUAL_EXCEEDS_TOLERANCE")

    # Inversão de ordem espacial de faixas: o mesmo defeito da Toca (2026-08-12) pego cedo
    # e nomeado, em vez de só a "gravata" que o auditor de export acusa tarde e sem dizer
    # qual forma. Cota manda em distância, nunca em ordem — inversão entre faixas
    # determinadas por cota confirmada acusa igual.
    order_violation_proposals: set[str] = _order_violation_proposals(plan_state, freeform_ids)
    for detail_state in detail_states.values():
        order_violation_proposals |= _order_violation_proposals(detail_state, freeform_ids)
    for proposal_id in sorted(order_violation_proposals):
        blockers.append(f"TRACE_BAND_ORDER_INVERTED:{proposal_id}")

    # Duas cotas confirmadas dando medidas diferentes para o mesmo círculo: a cena é
    # construída (o revisor precisa ver as duas), mas o traçado sai em conflito.
    blockers.extend(circle_conflicts)

    for report in unapplied:
        # A causa vem do ponto do descarte; o código da issue não muda (o consumidor dela
        # continua o mesmo), só a frase deixa de ser fixa e passa a dizer o que consertar.
        cause_phrase = UNAPPLIED_CAUSE_MESSAGES.get(
            report.cause, "o traçado não encontrou vão ortogonal para a leitura"
        )
        issues.append(
            Issue(
                id=_uuid(packet.dataset_id, feature_id, f"issue:unapplied:{report.reading_id}"),
                code="CONFIRMED_READING_NOT_APPLIED",
                severity=IssueSeverity.WARNING,
                message=(
                    f"A leitura confirmada {report.reading_id} "
                    f"({readings[report.reading_id].raw_text!r}) não pôde virar vão ortogonal "
                    f"no traçado ({report.cause}): {cause_phrase}. A geometria correspondente "
                    "permanece aproximada — conferir."
                ),
            )
        )
    if approximate_count:
        issues.append(
            Issue(
                id=_uuid(packet.dataset_id, feature_id, "issue:approximate"),
                code="TRACED_GEOMETRY_APPROXIMATE",
                severity=IssueSeverity.INFO,
                message=(
                    f"{approximate_count} entidade(s) permanecem aproximadas na layer "
                    f"APROXIMADO, aceitas em lote por {acceptance.reviewer_id} "
                    f"({acceptance.acceptance_id}). Nenhuma virou exata sem cota."
                ),
            )
        )

    entities.extend(dimension_entities)
    entities.extend(note_entities)

    # Moldura e título de cada detalhe, dimensionados pelo que o grupo realmente ocupa
    # (geometria + cotas + notas). São Entity normais — a auditoria exige XDATA e
    # contagem 1:1 — e as caixas viram obstáculo antes do carimbo, cujo `clear_below`
    # já o empurra para baixo da coluna de detalhes sem código novo.
    for detail_group in acceptance.detail_groups:
        placed_bbox = detail_bboxes[detail_group.detail_id]
        boxes = [placed_bbox, *group_boxes[detail_group.detail_id]]
        group_diagonal = math.hypot(
            placed_bbox[2] - placed_bbox[0], placed_bbox[3] - placed_bbox[1]
        )
        pad = max(0.5, group_diagonal * 0.05)
        frame_box = (
            min(box[0] for box in boxes) - pad,
            min(box[1] for box in boxes) - pad,
            max(box[2] for box in boxes) + pad,
            max(box[3] for box in boxes) + pad,
        )
        frame_provenance_ids = [acceptance.acceptance_id, f"detail:{detail_group.detail_id}"]
        entities.append(
            Entity(
                id=_uuid(packet.dataset_id, feature_id, f"detail-frame:{detail_group.detail_id}"),
                kind=EntityKind.POLYLINE,
                layer=LayerName.DETALHES,
                precision=Precision.DERIVED,
                geometry=PolylineGeometry(
                    points=[
                        Point2D(x=frame_box[0], y=frame_box[1]),
                        Point2D(x=frame_box[2], y=frame_box[1]),
                        Point2D(x=frame_box[2], y=frame_box[3]),
                        Point2D(x=frame_box[0], y=frame_box[3]),
                    ],
                    closed=True,
                ),
                provenance=Provenance(
                    source_type=TRACE_SOURCE_TYPE,
                    source_ids=frame_provenance_ids,
                    summary_code="DETAIL_FRAME",
                ),
            )
        )
        title_suffix = " (SEM ESCALA)" if detail_group.mode == "sketch" else ""
        detail_title = f"DETALHE {detail_group.detail_id} — {detail_group.title}{title_suffix}"
        title_insertion = Point2D(x=frame_box[0], y=frame_box[3] + dim_text_height * 0.5)
        entities.append(
            Entity(
                id=_uuid(packet.dataset_id, feature_id, f"detail-title:{detail_group.detail_id}"),
                kind=EntityKind.TEXT,
                layer=LayerName.TEXTOS,
                precision=Precision.DERIVED,
                geometry=TextGeometry(
                    insertion=title_insertion,
                    text=detail_title,
                    height=dim_text_height,
                    rotation=0.0,
                ),
                provenance=Provenance(
                    source_type=TRACE_SOURCE_TYPE,
                    source_ids=frame_provenance_ids,
                    summary_code="DETAIL_TITLE",
                ),
            )
        )
        dimension_obstacles.append(frame_box)
        dimension_obstacles.append(
            (
                title_insertion.x,
                title_insertion.y,
                title_insertion.x + estimated_width(detail_title, dim_text_height),
                title_insertion.y + dim_text_height,
            )
        )

    # Carimbo antes dos rótulos: as caixas das linhas dele viram obstáculo, e o desvio
    # dos balões passa a respeitar cota e carimbo — texto nunca por cima de texto.
    title_entities = _title_block(
        entities,
        dataset_id=packet.dataset_id,
        feature_id=feature_id,
        title=title or packet.dataset_id.upper(),
        unapplied=[readings[report.reading_id] for report in unapplied],
        approximate_count=approximate_count,
        general_notes=general_notes,
        # O carimbo começa abaixo de tudo que as cotas e notas já ocupam sob o desenho.
        clear_below=min(
            (box[1] for box in dimension_obstacles),
            default=None,
        ),
    )
    annotation_obstacles = list(dimension_obstacles)
    for title_entity in title_entities:
        title_geometry = title_entity.geometry
        if isinstance(title_geometry, TextGeometry):
            annotation_obstacles.append(
                (
                    title_geometry.insertion.x,
                    title_geometry.insertion.y,
                    title_geometry.insertion.x
                    + estimated_width(title_geometry.text, title_geometry.height),
                    title_geometry.insertion.y + title_geometry.height,
                )
            )
    entities.extend(
        place_labels(
            labelled,
            scene_entities=[
                entity
                for entity in entities
                if entity.kind
                not in {EntityKind.TEXT, EntityKind.DIMENSION, EntityKind.DIAMETER_DIMENSION}
            ],
            obstacles=annotation_obstacles,
            source_ids=[acceptance.acceptance_id],
            height_reference=plan_entities,
        )
    )
    entities.extend(title_entities)

    blocker_issues = [
        Issue(
            id=_uuid(packet.dataset_id, feature_id, f"issue:blocker:{blocker}"),
            code=blocker.split(":", maxsplit=1)[0],
            severity=IssueSeverity.CRITICAL,
            message=blocker,
        )
        for blocker in blockers
    ]
    # Toda cena traçada carrega o critério declarado no caso, igual à cena do solver
    # retangular: sem a issue o portão de exportação nunca veria o critério.
    criteria_issues = scope_criteria_issues(
        [criterion.code for criterion in required_criteria],
        {
            criterion.code: criterion.text
            for criterion in required_criteria
            if criterion.text is not None
        },
        id_factory=lambda code: _uuid(packet.dataset_id, feature_id, f"issue:criterion:{code}"),
    )

    scene = SceneRevision(
        id=_uuid(packet.dataset_id, feature_id, "scene-draft"),
        job_id=_uuid(packet.dataset_id, feature_id, "job"),
        version=1,
        created_at=datetime.now(UTC),
        approved=False,
        accepted_approximation_ids=accepted_approximations,
        entities=entities,
        measurements=measurements,
        constraints=scene_constraints,
        issues=[*issues, *blocker_issues, *criteria_issues],
        # Só o rótulo de elemento que alguma entidade desta cena de fato usa: o de uma
        # declaração cujas propostas ficaram todas fora do aceite não nomeia nada aqui, e
        # `SceneRevision` recusa rótulo órfão (`ELEMENT_LABEL_UNKNOWN_REF`).
        element_labels={
            element_ref: label
            for element_ref, label in sorted(label_of_element.items())
            if element_ref in proposals_of_element
        },
    )
    status: Literal["solved_unapproved", "conflict"] = (
        "conflict" if blockers else "solved_unapproved"
    )
    return TraceSolveResult(
        status=status,
        dataset_id=packet.dataset_id,
        feature_id=feature_id,
        blockers=blockers,
        unapplied_reading_ids=[report.reading_id for report in unapplied],
        unapplied_readings=unapplied,
        contested_spans=contested_spans,
        applied_spans=applied_span_reports,
        residuals=residuals,
        exact_entity_count=exact_count,
        approximate_entity_count=approximate_count,
        note_count=sum(1 for entity in note_entities if entity.kind is EntityKind.TEXT)
        + len(general_notes),
        scale_m_per_px=plan_state.scale_m_per_px,
        detail_group_scales={
            detail_id: state.scale_m_per_px for detail_id, state in detail_states.items()
        },
        scene=scene,
        required_criteria=list(required_criteria),
        safety_notes=safety_notes,
    )


def _extent(entities: Sequence[Entity]) -> tuple[float, float, float, float] | None:
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
        elif isinstance(geometry, CircleGeometry):
            xs += [geometry.center.x - geometry.radius, geometry.center.x + geometry.radius]
            ys += [geometry.center.y - geometry.radius, geometry.center.y + geometry.radius]
    if not xs or not ys:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


def _title_block(
    entities: Sequence[Entity],
    *,
    dataset_id: str,
    feature_id: str,
    title: str,
    unapplied: Sequence[DimensionReading],
    approximate_count: int,
    general_notes: Sequence[tuple[str, str, Provenance]] = (),
    clear_below: float | None = None,
) -> list[Entity]:
    """Carimbo com título, unidade, origem e hipóteses — legível sem abrir o CAD.

    O preview do pacote é o único artefato que uma pessoa lê sem AutoCAD; até aqui ele
    não dizia nem de que cena era. As hipóteses continuam em `hipoteses.json`, mas as
    que afetam a leitura do desenho ganham uma linha no próprio desenho. Notas gerais
    confirmadas (tela aérea…) entram acima do título, com respiro para não encavalar.
    """
    extent = _extent(entities)
    if extent is None:
        return []
    min_x, min_y, max_x, max_y = extent
    diagonal = math.hypot(max_x - min_x, max_y - min_y)
    title_height = max(0.6, diagonal * TITLE_HEIGHT_RATIO)
    note_height = max(0.3, diagonal * NOTE_HEIGHT_RATIO)

    title_provenance = Provenance(
        source_type=TRACER_VERSION,
        source_ids=[dataset_id],
        summary_code="TRACE_TITLE_BLOCK",
    )
    # (sufixo de id, texto, altura, provenance, precisão)
    lines: list[tuple[str, str, float, Provenance, Precision]] = []
    for reading_id, text, provenance in general_notes:
        lines.append((f"note-geral:{reading_id}", text, note_height, provenance, Precision.EXACT))
    lines.append(("title:0", title, title_height, title_provenance, Precision.DERIVED))
    lines.append(
        (
            "title:1",
            "TRACADO DE CROQUI | UNIDADE: METRO | ORIGEM (0,0) NO CANTO INFERIOR ESQUERDO",
            note_height,
            title_provenance,
            Precision.DERIVED,
        )
    )
    lines.append(
        (
            "title:2",
            "COTAS CONFIRMADAS MANDAM NA GEOMETRIA; LAYER APROXIMADO PERMANECE APROXIMADA "
            f"({approximate_count} ELEMENTO(S)).",
            note_height,
            title_provenance,
            Precision.DERIVED,
        )
    )
    for index, reading in enumerate(unapplied):
        lines.append(
            (
                f"title:unapplied:{index}",
                f"COTA CONFIRMADA NAO APLICADA AO TRACADO: {reading.raw_text} - CONFERIR.",
                note_height,
                title_provenance,
                Precision.DERIVED,
            )
        )

    block: list[Entity] = []
    floor = min_y if clear_below is None else min(min_y, clear_below)
    cursor = floor - note_height * 2
    last_general_suffix = f"note-geral:{general_notes[-1][0]}" if general_notes else None
    for suffix, text, height, provenance, precision in lines:
        block.append(
            Entity(
                id=_uuid(dataset_id, feature_id, suffix),
                kind=EntityKind.TEXT,
                layer=LayerName.TEXTOS,
                precision=precision,
                geometry=TextGeometry(
                    insertion=Point2D(x=min_x, y=cursor - height),
                    text=text[:500],
                    height=height,
                    rotation=0.0,
                ),
                provenance=provenance,
            )
        )
        cursor -= height * 1.8
        if suffix == last_general_suffix:
            # Respiro extra entre as notas gerais e o título, para não encavalar.
            cursor -= title_height * 1.2
    return block


def write_trace_result(result: TraceSolveResult, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = output_dir / "trace-result.json"
    serialized = json.dumps(
        result.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    atomic_write_text(result_path, f"{serialized}\n")
    return result_path


def approve_trace(result: TraceSolveResult, approval: SceneApproval) -> ApprovedTraceRevision:
    """Aprova o traçado aplicando a declaração por critério antes do portão de exportação.

    Critério declarado coberto fecha como `RESOLVED`, reconhecido como pendente fecha como
    `ACCEPTED` e o que não foi declarado continua `OPEN` — o export segue falhando fechado.
    """
    if result.status != "solved_unapproved" or result.scene is None:
        raise ValueError("somente traçado sem blockers pode ser aprovado")
    if approval.source_scene_id != result.scene.id:
        raise ValueError("aprovação aponta para outra revisão")
    declarable = {criterion.code for criterion in result.required_criteria}
    declared = {*approval.covered_criteria, *approval.acknowledged_criteria}
    if not declared <= declarable:
        raise ValueError("somente critério de escopo declarado no caso pode ser declarado")
    declared_scene = result.scene.model_copy(
        update={
            "issues": apply_criteria_declarations(
                result.scene.issues,
                covered=approval.covered_criteria,
                acknowledged=approval.acknowledged_criteria,
            )
        }
    )
    preapproval_errors = [
        error for error in declared_scene.export_errors() if error != "SCENE_NOT_APPROVED"
    ]
    if preapproval_errors:
        raise ValueError(f"revisão contém blockers de exportação: {preapproval_errors}")
    approved_scene = declared_scene.model_copy(
        deep=True,
        update={
            "id": uuid5(
                NAMESPACE_URL,
                f"croquito:{result.scene.id}:{approval.approval_id}:approved",
            ),
            "version": result.scene.version + 1,
            "created_at": approval.decided_at,
            "approved": True,
        },
    )
    approved_scene.ensure_exportable()
    return ApprovedTraceRevision(
        approval=approval,
        source_scene_id=result.scene.id,
        scene=approved_scene,
    )


def write_approved_trace_revision(
    approved: ApprovedTraceRevision, output_dir: Path
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    scene_path = output_dir / "scene-approved.json"
    approval_path = output_dir / "aprovacao.json"
    scene_json = json.dumps(
        approved.scene.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    approval_json = json.dumps(
        {
            "source_scene_id": str(approved.source_scene_id),
            **approved.approval.model_dump(mode="json"),
        },
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    atomic_write_text(scene_path, f"{scene_json}\n")
    atomic_write_text(approval_path, f"{approval_json}\n")
    return scene_path, approval_path
