"""Eval da extração paga de legenda e do refino de código SCO, com gate e modo offline.

Espelho de `takeoff_eval`, um degrau adiante: lá o extrator é a fixture do próprio
repositório; aqui o extrator é um **braço de provider**, e o mesmo relatório mede os dois
estágios pagos do M5 sobre a mesma prancha sintética — a extração da legenda e o refino da
shortlist de código.

Dois modos, um só caminho de código:

- **offline (CI)**: sem `--arm`, roda o braço fixture embutido (`legend_fixtures`), que
  deriva a transcrição das MESMAS constantes que desenham a prancha. Nada sai da máquina e
  nada é cobrado.
- **pago (local, Fase D)**: com `--arm nome=provider:modelo`, os braços reais entram pela
  fábrica `build_extraction_arm`, que exige teto de gasto explícito em variável de
  ambiente. Nenhum teste roda nesse modo.

Honestidade, na mesma linha da eval de visão sintética: **o modo fixture valida mecanismo
e contrato, não precisão**. Recall 1.0 do braço fixture significa que o mapeamento
observação→takeoff não perdeu nada e que os gates recusam o que prometem recusar; não diz
nada sobre a leitura de uma prancha real de cliente. Só a rodada paga responde isso.

O que a eval NÃO faz é se autoautorizar: ela não escreve digest nenhum na allowlist de
extração. O gate de allowlist é exercitado do lado da recusa — imagem adulterada não passa
por `authorize_page` —, e o braço real continua tendo de ser autorizado por quem paga.

Correspondência item↔gabarito: um braço real transcreve o rótulo **como impresso**, e na
prancha o rótulo anda colado à nota (`ALAMBRADO SINTETICO (h=1,20m)`). Transcrição fiel ao
papel não pode ser punida no recall nem derrubar a revisão sintética, então esta eval casa
o item pelo rótulo puro **ou** pelo impresso (`gabarito_row_for`). O gate do M3
(`takeoff_eval`) continua estrito no rótulo puro de propósito: lá o extrator é a fixture do
repositório, que escreve o rótulo que ela mesma desenhou, e afrouxar aquele critério
esconderia regressão da fixture. O que os dois compartilham é a comparação de **valores**
(`matches_gabarito`): unidade, quantidade e a exigência de item ambíguo sem quantidade na
linha ilegível.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from croquitodxf_valuation.assignment import CodeSuggestionSet, SuggestionConfig
from croquitodxf_valuation.catalog import read_price_catalog
from croquitodxf_valuation.contract import ContractWorkbook
from croquitodxf_valuation.errors import ValuationValidationError
from croquitodxf_valuation.models import PriceCatalog
from croquitodxf_valuation.takeoff import (
    TakeoffDecisionBatch,
    TakeoffDecisionInput,
    TakeoffItem,
    TakeoffItemStatus,
    TakeoffPacket,
    apply_takeoff_decisions,
)
from croquitodxf_valuation.template import default_template
from croquitodxf_valuation.workbook_reader import read_contract_workbook
from croquitodxf_worker.extraction_eval import ExtractionNotAllowlistedError, authorize_page
from croquitodxf_worker.io_utils import atomic_write_text
from croquitodxf_worker.providers import (
    LegendExtractionOutput,
    ProviderAdapter,
    ProviderExecution,
    build_extraction_arm,
)
from croquitodxf_worker.valuation.legend_extraction import (
    build_legend_request,
    extractor_label,
    takeoff_packet_from_legend,
)
from croquitodxf_worker.valuation.legend_fixtures import (
    FIXTURE_ARM_NAME,
    invalid_refinement_fixture_adapter,
    legend_fixture_adapter,
    refinement_fixture_adapter,
)
from croquitodxf_worker.valuation.plate import (
    SYNTHETIC_LEGEND_ROWS,
    LegendRow,
    PlateArtifacts,
    render_synthetic_plate,
)
from croquitodxf_worker.valuation.sco_matching import (
    build_hybrid_code_suggestions,
    normalize_query_text,
)
from croquitodxf_worker.valuation.sco_matching_fixtures import (
    fixture_semantic_index,
    fixture_vector,
)
from croquitodxf_worker.valuation.sco_suggestion import (
    build_code_suggestions,
    refine_code_suggestions,
)
from croquitodxf_worker.valuation.synthetic import (
    DEMO_EXPECTED_CODE_BY_LABEL,
    SYNTHETIC_CONTRACT_LABEL,
    SYNTHETIC_CONTRACT_SOURCE_LABEL,
    SYNTHETIC_REFERENCE_MONTH,
    SYNTHETIC_TAKEOFF_AMBIGUOUS_NOTE,
    SYNTHETIC_TAKEOFF_AMBIGUOUS_QUANTITY,
    build_demo_takeoff_decisions,
    build_synthetic_previous_mapao,
)
from croquitodxf_worker.valuation.takeoff_eval import matches_gabarito
from croquitodxf_worker.valuation.takeoff_fixture import extract_takeoff_fixture

REPORT_FILENAME: Final = "valuation-extraction-eval.json"
MANIFEST_FILENAME: Final = "plate-manifest.json"
PREVIOUS_MAPAO_FILENAME: Final = "previous-mapao.xlsx"

BUDGET_ENV: Final = "CROQUITODXF_AI_MAX_ESTIMATED_COST_USD"
_PROBE_PROVIDER: Final = "anthropic"
_PROBE_MODEL_ID: Final = "anthropic.claude-sonnet-5"

_TAMPERED_DIGEST: Final = "f" * 64

FIXTURE_NOTE: Final = (
    "Braço fixture: mede mecanismo e contrato sobre prancha sintética, não precisão de "
    "leitura de prancha real."
)

_REVIEW_SUPPLIED_QUANTITY_NOTE: Final = (
    "quantidade não lida pela extração; informada pelo revisor sintético a partir do "
    "gabarito da prancha"
)


class ArmReport(BaseModel):
    """Um eixo de comparação, com as métricas dos dois estágios pagos e o custo de cada um."""

    model_config = ConfigDict(extra="forbid")

    name: str
    provider: str
    model_id: str
    prompt_version: str
    refinement_model_id: str
    refinement_prompt_version: str
    item_count: int = Field(ge=0)
    proposed_count: int = Field(ge=0)
    ambiguous_count: int = Field(ge=0)
    legend_recall: float = Field(ge=0, le=1)
    quantity_accuracy: float = Field(ge=0, le=1)
    sco_top1: float = Field(ge=0, le=1)
    sco_top3: float = Field(ge=0, le=1)
    lexical_sco_top1: float = Field(ge=0, le=1)
    lexical_sco_top3: float = Field(ge=0, le=1)
    suggester_version: str
    legend_latency_ms: int = Field(ge=0)
    refinement_latency_ms: int = Field(ge=0)
    estimated_cost_usd: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    notes: list[str]


MATCHER_HYBRID_NOTE: Final = (
    "Variante híbrida medida com índice de embeddings FABRICADO (saco de radicais por "
    "hash, sem rede): ela exercita fusão e contrato, não mede qualidade semântica. A "
    "medida real é o golden contra o catálogo do cliente com índice pago."
)


class ValuationExtractionEvalReport(BaseModel):
    """`matcher_recall_at_20`/`matcher_top1`/`matcher_top3` (M7 Fase 1) medem o matcher
    léxico determinístico sobre a parte sintética — braço fixture, offline, o mesmo
    gabarito de `DEMO_EXPECTED_CODE_BY_LABEL` — e são independentes de qual braço pago
    rodou; `sco_top1`/`sco_top3`/`lexical_sco_top1`/`lexical_sco_top3` de `ArmReport`
    continuam medindo o refino pago por braço, cortado em 3 candidatos (o que
    `SuggestionConfig` publica por padrão).

    `matcher_hybrid_*` (M7 Fase 2) repete as mesmas três medidas pela shortlist HÍBRIDA
    sobre um índice fabricado — ver `MATCHER_HYBRID_NOTE`. Elas ficam **fora** do
    `thresholds` e do `passed` de propósito: gatear uma métrica de vetor fabricado daria a
    impressão de que a busca semântica foi validada aqui, e ela não foi."""

    model_config = ConfigDict(extra="forbid")

    plate_id: str
    image_sha256: str
    arms: list[ArmReport]
    matcher_recall_at_20: float = Field(ge=0, le=1)
    matcher_top1: float = Field(ge=0, le=1)
    matcher_top3: float = Field(ge=0, le=1)
    matcher_hybrid_recall_at_20: float = Field(ge=0, le=1)
    matcher_hybrid_top1: float = Field(ge=0, le=1)
    matcher_hybrid_top3: float = Field(ge=0, le=1)
    matcher_hybrid_index_model: str
    matcher_hybrid_note: str = MATCHER_HYBRID_NOTE
    checks: dict[str, bool]
    thresholds: dict[str, float]
    passed: bool


RefinementAdapterFactory = Callable[[CodeSuggestionSet, Mapping[str, str]], ProviderAdapter]


@dataclass(frozen=True, slots=True)
class ExtractionArm:
    """Um braço da eval: quem extrai a legenda e quem refina a shortlist que ela gerou.

    O refino chega como **fábrica**, não como adapter pronto, porque a fixture só consegue
    permutar uma shortlist que já existe — e a shortlist só existe depois da extração. Para
    um braço real a fábrica ignora os argumentos e devolve sempre o mesmo adapter: os dois
    estágios são o mesmo modelo.
    """

    name: str
    legend_adapter: ProviderAdapter
    refinement_adapter: RefinementAdapterFactory


def build_real_arm(specification: str) -> ExtractionArm:
    """Traduz `NOME=PROVIDER:MODELO` num braço pago; a fábrica exige teto de gasto."""
    name, _, target = specification.partition("=")
    provider, _, model_id = target.partition(":")
    adapter = build_extraction_arm(provider=provider, model_id=model_id)
    return ExtractionArm(
        name=name,
        legend_adapter=adapter,
        refinement_adapter=lambda _suggestions, _labels: adapter,
    )


def fixture_arm(plate: PlateArtifacts) -> ExtractionArm:
    """Braço offline embutido: transcrição perfeita da prancha e refino pelo gabarito."""
    return ExtractionArm(
        name=FIXTURE_ARM_NAME,
        legend_adapter=legend_fixture_adapter(plate),
        refinement_adapter=lambda suggestions, labels: refinement_fixture_adapter(
            suggestions, labels, DEMO_EXPECTED_CODE_BY_LABEL
        ),
    )


def _write_plate_manifest(output_dir: Path, plate: PlateArtifacts) -> Path:
    """Manifest da prancha sintética, no formato que `croquitodxf-demo ingest` publica.

    Existe para que o gate de allowlist seja exercitado sobre um manifest de verdade, e não
    sobre um dublê: a checagem negativa da eval usa exatamente a função que o comando pago
    usa.
    """
    manifest_path = output_dir / MANIFEST_FILENAME
    atomic_write_text(
        manifest_path,
        json.dumps(
            {
                "source_sha256": plate.pdf_sha256,
                "pages": [{"number": plate.page_number, "image_sha256": plate.image_sha256}],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    return manifest_path


def gabarito_row_for(item: TakeoffItem) -> LegendRow | None:
    """Linha do gabarito que o item extraído descreve, pelo rótulo puro **ou** pelo impresso.

    Ponto único de correspondência item↔gabarito da eval, usado igualmente pelo braço
    fixture e pelo real. Existe porque a prancha imprime o rótulo com a nota colada
    (`ALAMBRADO SINTETICO (h=1,20m)`) e um modelo que transcreve o que está no papel está
    **certo** — punir isso mediria a fidelidade da transcrição ao contrário. Rótulo que não
    corresponde a nenhuma linha devolve `None` e vira item não casado, nunca um casamento
    por aproximação.
    """
    label = item.label.strip()
    for row in SYNTHETIC_LEGEND_ROWS:
        if label in {row.label.strip(), row.plate_label.strip()}:
            return row
    return None


def _reproduces_gabarito(item: TakeoffItem, row: LegendRow) -> bool:
    """Valores do item batem com a linha, pelo MESMO critério do gate do M3.

    O rótulo já foi reconciliado por `gabarito_row_for`; o item é comparado sob o rótulo
    puro para que unidade, quantidade e a exigência de item ambíguo sem quantidade na linha
    ilegível continuem sendo exatamente as de `matches_gabarito`. Duas definições de
    "casou" divergiriam com o tempo, e uma das duas passaria a mentir.
    """
    return matches_gabarito(row, item.model_copy(update={"label": row.label}))


def _legend_recall(packet: TakeoffPacket) -> float:
    """Fração das linhas do gabarito reproduzidas pelo pacote extraído."""
    matched = sum(
        any(
            gabarito_row_for(item) is row and _reproduces_gabarito(item, row)
            for item in packet.items
        )
        for row in SYNTHETIC_LEGEND_ROWS
    )
    return round(matched / len(SYNTHETIC_LEGEND_ROWS), 4)


def _quantity_accuracy(packet: TakeoffPacket) -> float:
    """Fração das linhas legíveis do gabarito cuja quantidade saiu exata da extração."""
    legible = [row for row in SYNTHETIC_LEGEND_ROWS if row.quantity is not None]
    matched = sum(
        any(
            gabarito_row_for(item) is row and item.quantity == row.quantity for item in packet.items
        )
        for row in legible
    )
    return round(matched / len(legible), 4)


def _supplied_quantity(row: LegendRow) -> tuple[Decimal, str]:
    """Quantidade que o revisor sintético informa quando a extração não trouxe número.

    Duas origens, ambas atos declarados do revisor e nenhuma derivada da imagem:

    - linha **legível** no gabarito que o braço não conseguiu quantificar → a quantidade do
      gabarito. Isso não esconde o defeito da extração: o `legend_recall` já contou a linha
      como não reproduzida antes de a revisão acontecer;
    - a linha **ilegível** da prancha, que não tem quantidade no gabarito por construção →
      a mesma quantidade que o `demo` informa (`SYNTHETIC_TAKEOFF_AMBIGUOUS_QUANTITY`), que
      não é lida de lugar nenhum de propósito.
    """
    if row.quantity is None:
        return SYNTHETIC_TAKEOFF_AMBIGUOUS_QUANTITY, SYNTHETIC_TAKEOFF_AMBIGUOUS_NOTE
    return row.quantity, _REVIEW_SUPPLIED_QUANTITY_NOTE


def _demo_review_policy(plate: PlateArtifacts) -> dict[str, TakeoffDecisionInput]:
    """A revisão do `demo`, indexada pelo rótulo do gabarito em vez de pelo id do item.

    A política do revisor sintético não é reimplementada aqui — ela é **lida** do demo
    sobre o pacote canônico da própria prancha (`extract_takeoff_fixture`), que traz os
    rótulos puros. Reescrevê-la faria a eval divergir do demo em silêncio: a decisão do
    alambrado, por exemplo, não é só "confirmar" — ela converte metro linear em m² (48,75 m x
    h=1,20 m = 58,50 m²), e é essa unidade que o oráculo de código do demo espera. Perder
    a conversão derrubaria o top-1 do braço fixture sem que nada na extração tivesse
    piorado.

    O que a eval faz por conta própria é só **a quem** aplicar cada decisão: por linha do
    gabarito casada, não por rótulo exato.
    """
    reference = extract_takeoff_fixture(plate)
    labels_by_item = {item.id: item.label for item in reference.items}
    return {
        labels_by_item[decision.item_id]: decision
        for decision in build_demo_takeoff_decisions(reference).decisions
    }


def _synthetic_review(
    packet: TakeoffPacket, plate: PlateArtifacts
) -> tuple[TakeoffDecisionBatch, list[str]]:
    """Aplica a revisão do demo ao pacote extraído, casando por gabarito, não por rótulo exato.

    `build_demo_takeoff_decisions` sozinho não serve: ele procura o item pelo rótulo exato
    do gabarito e recusa (`SYNTHETIC_LABEL_UNKNOWN`) uma transcrição fiel ao rótulo impresso
    na prancha. Aqui a política dele é reaproveitada item a item, endereçada pela linha que
    `gabarito_row_for` casou.

    Uma regra a mais, que o demo não precisa ter porque a fixture nunca falha: item que a
    extração **não conseguiu quantificar** e para o qual o demo não informa quantidade é
    confirmado com a quantidade que `_supplied_quantity` declara. Isso não maquia o defeito
    da extração — `legend_recall` e `quantity_accuracy` já o contaram antes da revisão —, é
    o que permite a rodada seguir até medir o estágio seguinte.

    Itens sem linha correspondente não recebem decisão nenhuma: eles saem na lista devolvida
    e reprovam o check `all_items_matched_gabarito`, em vez de derrubar a rodada.
    """
    policy_by_label = _demo_review_policy(plate)
    decisions: list[TakeoffDecisionInput] = []
    unmatched_item_ids: list[str] = []
    for item in packet.pending_items():
        row = gabarito_row_for(item)
        if row is None:
            unmatched_item_ids.append(item.id)
            continue
        policy = policy_by_label.get(row.label)
        if policy is None:
            raise ValuationValidationError(
                "EVAL_REVIEW_POLICY_MISSING",
                "linha do gabarito sem decisão declarada no revisor sintético do demo",
                {"label": row.label},
            )
        quantity, note = policy.quantity, policy.note
        if policy.action == "confirm" and quantity is None and item.quantity is None:
            quantity, note = _supplied_quantity(row)
        decisions.append(
            TakeoffDecisionInput(
                item_id=item.id,
                action=policy.action,
                reviewer_id=policy.reviewer_id,
                reviewer_role=policy.reviewer_role,
                decided_at=policy.decided_at,
                quantity=quantity,
                unit=policy.unit,
                note=note,
            )
        )
    if not decisions:
        raise ValuationValidationError(
            "EVAL_NO_ITEM_MATCHED_GABARITO",
            "nenhum item extraído corresponde a uma linha do gabarito; não há o que revisar",
            {"item_ids": unmatched_item_ids},
        )
    return TakeoffDecisionBatch(decisions=decisions), unmatched_item_ids


def _sco_hit_rates(
    suggestions: CodeSuggestionSet,
    labels_by_item: Mapping[str, str],
    expected_code_by_label: Mapping[str, str],
) -> tuple[float, float]:
    """Top-1 e top-3 da shortlist contra o gabarito de código do demo.

    O denominador é o dos itens **com** código no gabarito: item que o orçamentista
    sintético rejeitou não tem resposta certa, e contá-lo como erro puniria o suggester por
    uma decisão humana.
    """
    scored = [
        (suggestion, expected_code_by_label[labels_by_item[suggestion.item_id]])
        for suggestion in suggestions.suggestions
        if labels_by_item.get(suggestion.item_id, "") in expected_code_by_label
    ]
    if not scored:
        return 0.0, 0.0
    top1 = sum(1 for suggestion, code in scored if suggestion.candidates[0].code == code)
    top3 = sum(
        1
        for suggestion, code in scored
        if code in [candidate.code for candidate in suggestion.candidates[:3]]
    )
    return round(top1 / len(scored), 4), round(top3 / len(scored), 4)


_MATCHER_RECALL_CANDIDATES: Final = 20
"""Profundidade do gate `matcher_recall_at_20` (M7 Fase 1): o mesmo k do golden set
(`tests/valuation/test_matcher_golden.py`), bem além dos 3 candidatos que
`SuggestionConfig` publica por padrão — o gate mede se o matcher léxico PERDE o código
certo, não se ele o coloca em primeiro."""


def _matcher_rates(
    suggestions20: CodeSuggestionSet,
    labels_by_item: Mapping[str, str],
    expected_code_by_label: Mapping[str, str],
) -> tuple[float, float, float]:
    """recall@20, top-1 e top-3 do matcher léxico contra o gabarito sintético de código.

    `suggestions20` precisa vir de uma sugestão calculada com
    `SuggestionConfig(max_candidates_per_item=20)` — o resto é o mesmo casamento de
    `_sco_hit_rates`, com o denominador restrito aos itens que o gabarito confirma com
    código."""
    scored = [
        (suggestion, expected_code_by_label[labels_by_item[suggestion.item_id]])
        for suggestion in suggestions20.suggestions
        if labels_by_item.get(suggestion.item_id, "") in expected_code_by_label
    ]
    if not scored:
        return 0.0, 0.0, 0.0
    depth = _MATCHER_RECALL_CANDIDATES
    recall20 = sum(
        1
        for suggestion, code in scored
        if code in [candidate.code for candidate in suggestion.candidates[:depth]]
    )
    top1 = sum(1 for suggestion, code in scored if suggestion.candidates[0].code == code)
    top3 = sum(
        1
        for suggestion, code in scored
        if code in [candidate.code for candidate in suggestion.candidates[:3]]
    )
    denominator = len(scored)
    return (
        round(recall20 / denominator, 4),
        round(top1 / denominator, 4),
        round(top3 / denominator, 4),
    )


def _check_real_arm_without_budget_refused() -> bool:
    """Sem teto de gasto declarado, a fábrica de braço pago recusa antes de qualquer chamada.

    A variável é removida do ambiente durante a checagem e devolvida em seguida: exercitar
    o gate de verdade vale mais do que descrevê-lo, e a rodada paga não pode perder o teto
    que o operador configurou.
    """
    previous = os.environ.pop(BUDGET_ENV, None)
    try:
        build_extraction_arm(provider=_PROBE_PROVIDER, model_id=_PROBE_MODEL_ID)
    except ValueError:
        return True
    else:
        return False
    finally:
        if previous is not None:
            os.environ[BUDGET_ENV] = previous


def _check_tampered_image_refused(manifest_path: Path) -> bool:
    """Página que não está no manifest não é autorizada, mesmo com o documento na allowlist."""
    try:
        authorize_page(manifest_path, _TAMPERED_DIGEST)
    except ExtractionNotAllowlistedError:
        return True
    return False


def _check_refinement_outside_shortlist_refused(
    packet: TakeoffPacket, suggestions: CodeSuggestionSet
) -> bool:
    """Refino que injeta código fora da shortlist recusa com `REFINEMENT_CODES_MISMATCH`."""
    try:
        refine_code_suggestions(
            packet, suggestions, invalid_refinement_fixture_adapter(suggestions)
        )
    except ValuationValidationError as error:
        return error.code == "REFINEMENT_CODES_MISMATCH"
    return False


def _usage_total(executions: Sequence[ProviderExecution], field: str) -> int | None:
    values = [getattr(execution.usage, field) for execution in executions]
    known = [value for value in values if value is not None]
    return sum(known) if known else None


def _cost_total(executions: Sequence[ProviderExecution]) -> float | None:
    known = [
        execution.usage.estimated_cost_usd
        for execution in executions
        if execution.usage.estimated_cost_usd is not None
    ]
    return float(sum(known)) if known else None


def _write_document(path: Path, model: BaseModel) -> Path:
    atomic_write_text(path, model.model_dump_json(indent=2) + "\n")
    return path


@dataclass(frozen=True, slots=True)
class _ArmOutcome:
    report: ArmReport
    packet: TakeoffPacket
    reviewed: TakeoffPacket
    lexical: CodeSuggestionSet
    unmatched_item_ids: tuple[str, ...]


def _run_arm(
    arm: ExtractionArm,
    plate: PlateArtifacts,
    catalog: PriceCatalog,
    contract: ContractWorkbook,
    output_dir: Path,
) -> _ArmOutcome:
    """Percorre com um braço os dois estágios pagos, pelo caminho de código do comando real."""
    request, width, height = build_legend_request(plate.image_path)
    legend_execution = arm.legend_adapter.execute(request)
    legend_output = legend_execution.output
    if not isinstance(legend_output, LegendExtractionOutput):  # pragma: no cover - contrato
        raise ValuationValidationError(
            "LEGEND_CONTRACT_MISMATCH",
            "braço não devolveu o contrato de extração de legenda",
            {"arm": arm.name},
        )
    packet = takeoff_packet_from_legend(
        legend_output,
        plate_id=plate.plate_id,
        page_number=plate.page_number,
        image_sha256=plate.image_sha256,
        source_pdf_sha256=plate.pdf_sha256,
        image_width=width,
        image_height=height,
        extractor=extractor_label(legend_execution.provider.value, legend_execution.model_id),
        extractor_version=legend_execution.prompt.prompt_version,
    )
    _write_document(output_dir / f"{arm.name}-takeoff-packet.json", packet)

    batch, unmatched_item_ids = _synthetic_review(packet, plate)
    reviewed = apply_takeoff_decisions(packet, batch)
    # O oráculo de código é indexado pelo rótulo do GABARITO: com o rótulo impresso a chave
    # não bateria e o hit-rate mediria a transcrição, não a sugestão.
    labels_by_item = {
        item.id: row.label for item in reviewed.items if (row := gabarito_row_for(item)) is not None
    }
    lexical = build_code_suggestions(reviewed, catalog, contract)
    refinement = refine_code_suggestions(
        reviewed, lexical, arm.refinement_adapter(lexical, labels_by_item)
    )
    _write_document(output_dir / f"{arm.name}-code-suggestions.json", refinement.suggestions)

    sco_top1, sco_top3 = _sco_hit_rates(
        refinement.suggestions, labels_by_item, DEMO_EXPECTED_CODE_BY_LABEL
    )
    lexical_top1, lexical_top3 = _sco_hit_rates(
        lexical, labels_by_item, DEMO_EXPECTED_CODE_BY_LABEL
    )
    executions = (legend_execution, refinement.execution)
    report = ArmReport(
        name=arm.name,
        provider=legend_execution.provider.value,
        model_id=legend_execution.model_id,
        prompt_version=legend_execution.prompt.prompt_version,
        refinement_model_id=refinement.execution.model_id,
        refinement_prompt_version=refinement.execution.prompt.prompt_version,
        item_count=len(packet.items),
        proposed_count=sum(1 for item in packet.items if item.status is TakeoffItemStatus.PROPOSED),
        ambiguous_count=sum(
            1 for item in packet.items if item.status is TakeoffItemStatus.AMBIGUOUS
        ),
        legend_recall=_legend_recall(packet),
        quantity_accuracy=_quantity_accuracy(packet),
        sco_top1=sco_top1,
        sco_top3=sco_top3,
        lexical_sco_top1=lexical_top1,
        lexical_sco_top3=lexical_top3,
        suggester_version=refinement.suggestions.suggester_version,
        legend_latency_ms=legend_execution.latency_ms,
        refinement_latency_ms=refinement.execution.latency_ms,
        estimated_cost_usd=_cost_total(executions),
        input_tokens=_usage_total(executions, "input_tokens"),
        output_tokens=_usage_total(executions, "output_tokens"),
        notes=[FIXTURE_NOTE] if arm.name == FIXTURE_ARM_NAME else [],
    )
    return _ArmOutcome(
        report=report,
        packet=packet,
        reviewed=reviewed,
        lexical=lexical,
        unmatched_item_ids=tuple(unmatched_item_ids),
    )


def run_valuation_extraction_eval(
    output_dir: Path,
    arm_specifications: Sequence[str] | None = None,
) -> tuple[ValuationExtractionEvalReport, Path]:
    """Gera a prancha, roda cada braço nos dois estágios pagos e exercita os gates.

    Sem `--arm` o único braço é o fixture, e a rodada inteira é offline. Com braços reais a
    fábrica exige teto de gasto e a rodada é paga — as métricas e os thresholds são os
    mesmos, porque quem decide aprovação de modelo é a revisão humana da Fase D, não este
    arquivo.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    plate = render_synthetic_plate(output_dir)
    manifest_path = _write_plate_manifest(output_dir, plate)

    template = default_template()
    previous_path = build_synthetic_previous_mapao(output_dir / PREVIOUS_MAPAO_FILENAME)
    catalog = read_price_catalog(
        previous_path,
        template,
        source_label=SYNTHETIC_CONTRACT_SOURCE_LABEL,
        reference_month=SYNTHETIC_REFERENCE_MONTH,
    )
    contract = read_contract_workbook(
        previous_path,
        template,
        source_label=SYNTHETIC_CONTRACT_SOURCE_LABEL,
        contract_label=SYNTHETIC_CONTRACT_LABEL,
    )

    arms: list[ExtractionArm]
    if arm_specifications:
        arms = [build_real_arm(specification) for specification in arm_specifications]
    else:
        arms = [fixture_arm(plate)]

    outcomes = [_run_arm(arm, plate, catalog, contract, output_dir) for arm in arms]

    first = outcomes[0]
    # Métricas do matcher léxico determinístico (M7 Fase 1), sobre a parte sintética —
    # independentes de qual braço pago rodou: usam sempre o primeiro braço (o fixture,
    # offline, quando `--arm` não foi passado) e um top-20 calculado à parte do que
    # `_run_arm` publica (que fica em 3 candidatos, o padrão de `SuggestionConfig`).
    matcher_labels_by_item = {
        item.id: row.label
        for item in first.reviewed.items
        if (row := gabarito_row_for(item)) is not None
    }
    matcher_suggestions_top20 = build_code_suggestions(
        first.reviewed,
        catalog,
        contract,
        config=SuggestionConfig(max_candidates_per_item=_MATCHER_RECALL_CANDIDATES),
    )
    matcher_recall_at_20, matcher_top1, matcher_top3 = _matcher_rates(
        matcher_suggestions_top20, matcher_labels_by_item, DEMO_EXPECTED_CODE_BY_LABEL
    )
    # Variante híbrida (M7 Fase 2) sobre índice FABRICADO: exercita a fusão e o contrato do
    # índice dentro do CI, sem rede e sem custo. Ela não é gate — ver `MATCHER_HYBRID_NOTE`.
    fixture_index = fixture_semantic_index(catalog)
    matcher_hybrid_top20 = build_hybrid_code_suggestions(
        first.reviewed,
        catalog,
        contract,
        index=fixture_index,
        query_vectors={
            normalize_query_text(item.label): fixture_vector(item.label)
            for item in first.reviewed.confirmed_items()
        },
        config=SuggestionConfig(max_candidates_per_item=_MATCHER_RECALL_CANDIDATES),
    )
    hybrid_recall_at_20, hybrid_top1, hybrid_top3 = _matcher_rates(
        matcher_hybrid_top20, matcher_labels_by_item, DEMO_EXPECTED_CODE_BY_LABEL
    )

    checks = {
        "no_item_born_confirmed": all(
            item.status in {TakeoffItemStatus.PROPOSED, TakeoffItemStatus.AMBIGUOUS}
            for outcome in outcomes
            for item in outcome.packet.items
        ),
        # Item que nenhuma linha do gabarito descreve não é medido nem revisado: a rodada
        # continua e reprova aqui, em vez de a eval decidir sozinha o que ele seria.
        "all_items_matched_gabarito": not any(outcome.unmatched_item_ids for outcome in outcomes),
        "real_arm_without_budget_refused": _check_real_arm_without_budget_refused(),
        "tampered_image_refused": _check_tampered_image_refused(manifest_path),
        "refinement_outside_shortlist_refused": _check_refinement_outside_shortlist_refused(
            first.reviewed, first.lexical
        ),
    }

    thresholds = {
        "legend_recall": 1.0,
        "sco_top1": 1.0,
        "matcher_recall_at_20": 1.0,
    }
    report = ValuationExtractionEvalReport(
        plate_id=plate.plate_id,
        image_sha256=plate.image_sha256,
        arms=[outcome.report for outcome in outcomes],
        matcher_recall_at_20=matcher_recall_at_20,
        matcher_top1=matcher_top1,
        matcher_top3=matcher_top3,
        matcher_hybrid_recall_at_20=hybrid_recall_at_20,
        matcher_hybrid_top1=hybrid_top1,
        matcher_hybrid_top3=hybrid_top3,
        matcher_hybrid_index_model=fixture_index.model_id,
        checks=checks,
        thresholds=thresholds,
        passed=bool(outcomes)
        and all(checks.values())
        and matcher_recall_at_20 >= thresholds["matcher_recall_at_20"]
        and all(
            outcome.report.legend_recall >= thresholds["legend_recall"]
            and outcome.report.sco_top1 >= thresholds["sco_top1"]
            for outcome in outcomes
        ),
    )
    report_path = output_dir / REPORT_FILENAME
    atomic_write_text(
        report_path,
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
    )
    return report, report_path
