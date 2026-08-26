"""Interface de linha de comando da medição de obra.

Convenções, iguais às dos demais comandos do worker:

- `0` sucesso;
- `1` divergência — para `export-valuation`/`demo` a pasta auditada divergente **não** é
  publicada; para `parity`/`compare-bulletin` o relatório da divergência é publicado
  normalmente, porque relatar é o próprio propósito das duas ferramentas;
- `2` recusa fechada, com um JSON `{"refused": <código>, ...}` no stdout.

`parity` e `compare-bulletin` são ferramentas **locais** de diagnóstico, fora da cadeia
de medição e fora do CI: comparam um arquivo real do cliente contra uma referência (o
próprio arquivo, no caso do `parity`; o `valuation.json` gerado, no caso do
`compare-bulletin`) e nunca escrevem no arquivo analisado.

A recusa **semântica** da importação (`CONTRACT_SEMANTICS_DIVERGENT`) sai com 2 como
qualquer outra e não publica artefato nenhum, mas grava um arquivo a mais: o dossiê
completo do recomputo (`import-diagnosis.json`), com todas as divergências do histórico
publicado. O stdout leva só o resumo por classe — o arquivo real produz milhares de
achados. O dossiê descreve; ele não aceita nada nem destrava a importação.

Todo comando de planilha aceita `--template <json>`: o layout da pasta é dado, não
código, e é assim que o MAPÃO real de um cliente entra sem tocar em nada aqui. Sem a
opção vale o `default_template()`, que é o layout sintético versionado no repositório.

Os comandos de takeoff (`extract-legend`, `review-takeoff`, `takeoff-demo`) cobrem o
começo da cadeia — a legenda quantificada da prancha do projetista. Eles são **offline**:
a extração que eles usam é a fixture sintética, que gera a prancha e extrai dela no mesmo
comando. Nenhum item nasce confirmado; a decisão do orçamentista é o que transforma
observação em quantitativo.

`register-takeoff` é o espelho do `register-extraction` da geometria, para a legenda:
reprocessa um pacote de takeoff **já publicado**, reassentando o bbox de cada item contra
a tinta da prancha (`croquito_worker.valuation.legend_registration`), sem nova chamada
paga e sem tocar no conteúdo lido. Pacote com algum item já decidido é recusado — mover a
âncora depois de uma decisão reescreveria o que o orçamentista viu.

O meio da cadeia liga o quantitativo revisado ao contrato, também offline e em três atos
separados: `suggest-codes` produz a shortlist lexical determinística (observação, nunca
decisão), `confirm-codes` registra a confirmação fail-closed do orçamentista e
`build-calc` monta boletim e memória de cálculo da obra. O `valuation.json` do
`build-calc` sai **sem aprovação**: aprovar e exportar continuam sendo atos à parte
(`export-valuation`).

Dois caminhos são **pagos** e ficam atrás de gate explícito: `extract-legend-real` lê a
prancha de cliente com um provider, e `suggest-codes --refine-arm` reordena a shortlist
lexical com um provider. Os dois exigem braço `NOME=PROVIDER:MODELO` real (o provider
`fixture` é recusado: comando de produção não publica observação fabricada), teto de gasto
em variável de ambiente e — na extração — o documento na allowlist. Os dois falham
fechados: recusa de gate ou falha de provider sai com 2 e **nenhum** artefato é gravado,
nem a versão lexical. Quem quer a lexical roda `suggest-codes` sem a flag, e é isso que
mantém a via determinística como fallback permanente e honesto.

`serve` não é um elo da cadeia: é a mesma cadeia por HTTP, para o orçamentista homologar
numa tela em vez de escrever lote de JSON à mão. Ele sobe um servidor **local** sobre um
diretório de rodada (`croquito_worker.valuation.local_server`), chama as mesmas funções
de domínio dos comandos acima, grava com os mesmos nomes de arquivo e nunca chama provider.
Como o `parity`, é ferramenta local: bind em `127.0.0.1` e sem autenticação.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ValidationError

from croquito_valuation.amendment_dossier import AmendmentDossier, build_amendment_dossier
from croquito_valuation.assignment import (
    CodeAssignmentBatch,
    CodeAssignmentSet,
    CodeSuggestionSet,
    SuggestionRefinement,
    apply_code_assignments,
    apply_code_assignments_over_cascade,
    ensure_price_cascade,
)
from croquito_valuation.bulletin_compare import compare_bulletin, read_bulletin_lines
from croquito_valuation.calc import (
    CalcBuildResult,
    CalcPlan,
    build_worksite_bulletin,
    build_worksite_valuation,
)
from croquito_valuation.calc_matrix import CalcMatrix
from croquito_valuation.canonical import AuditReport, audit_workbook
from croquito_valuation.catalog import (
    UNIT_ALIASES,
    DomainSynonyms,
    default_domain_synonyms,
    default_legend_noise,
    file_sha256,
    read_price_catalog,
)
from croquito_valuation.composition import CompositionSet, compile_compositions
from croquito_valuation.contract import ContractWorkbook
from croquito_valuation.contract_diagnosis import ContractSemanticsError
from croquito_valuation.emop import (
    EmopCatalogLayout,
    read_emop_catalog,
    read_emop_catalog_with_report,
)
from croquito_valuation.errors import ValuationValidationError, valuation_errors
from croquito_valuation.estimate import Estimate, build_worksite_estimate
from croquito_valuation.estimate_workbook import (
    EstimateAuditReport,
    audit_estimate_workbook,
    write_estimate_workbook,
)
from croquito_valuation.models import PriceCatalog, Valuation
from croquito_valuation.sicro import SicroCatalogLayout, read_sicro_catalog_with_report
from croquito_valuation.sinapi import SinapiCatalogLayout, read_sinapi_catalog_with_report
from croquito_valuation.takeoff import (
    TakeoffDecisionBatch,
    TakeoffDecisionInput,
    TakeoffItemStatus,
    TakeoffPacket,
    apply_takeoff_decisions,
    load_takeoff_packet,
)
from croquito_valuation.template import WorkbookTemplate, default_template
from croquito_valuation.workbook_reader import (
    ContractImportNotes,
    read_contract_workbook,
    read_contract_workbook_with_notes,
)
from croquito_valuation.workbook_writer import WriteReport, write_valuation_workbook
from croquito_worker.extraction_eval import ExtractionNotAllowlistedError
from croquito_worker.io_utils import atomic_write_text
from croquito_worker.providers import (
    EmbeddingsExecution,
    ProviderAdapter,
    ProviderExecution,
    ProviderExecutionError,
    build_embeddings_adapter,
    build_extraction_arm,
)
from croquito_worker.valuation.emop_fixture import emop_fixture_layout, write_emop_dbf
from croquito_worker.valuation.estimate_fixture import (
    SYNTHETIC_ESTIMATE_BDI_PERCENT,
    SYNTHETIC_ESTIMATE_WORKSITE_ADDRESS,
    SYNTHETIC_ESTIMATE_WORKSITE_KEY,
    SYNTHETIC_ESTIMATE_WORKSITE_NAME,
    build_demo_estimate_assignments,
    build_synthetic_composition_set,
)
from croquito_worker.valuation.extraction_eval import (
    ValuationExtractionEvalReport,
    run_valuation_extraction_eval,
)
from croquito_worker.valuation.legend_extraction import run_legend_extraction
from croquito_worker.valuation.legend_registration import (
    LegendRegistrationReport,
    register_legend_bboxes,
    restore_raw_bboxes,
)
from croquito_worker.valuation.parity import check_parity
from croquito_worker.valuation.plate import PlateArtifacts, render_synthetic_plate
from croquito_worker.valuation.sco_matching import (
    CATALOG_INDEX_FILENAME,
    INDEX_TEXT_RECIPE,
    QUERY_CACHE_FILENAME,
    SEMANTIC_INDEX_MISSING,
    SEMANTIC_UNAVAILABLE_PREFIX,
    CatalogIndexBuild,
    build_catalog_index,
    build_hybrid_code_suggestions,
    embeddings_adapter_or_reason,
    index_document,
    load_semantic_index,
    read_catalog_index,
    resolve_query_vectors,
)
from croquito_worker.valuation.sco_suggestion import (
    build_cascade_code_suggestions,
    build_code_suggestions,
    refine_code_suggestions,
)
from croquito_worker.valuation.synthetic import (
    SYNTHETIC_CATALOG_LABEL,
    SYNTHETIC_CONTRACT_LABEL,
    SYNTHETIC_CONTRACT_SOURCE_LABEL,
    SYNTHETIC_REFERENCE_MONTH,
    SYNTHETIC_TAKEOFF_AMBIGUOUS_NOTE,
    SYNTHETIC_TAKEOFF_AMBIGUOUS_QUANTITY,
    SYNTHETIC_TAKEOFF_DECIDED_AT,
    SYNTHETIC_TAKEOFF_REVIEWER,
    SYNTHETIC_TAKEOFF_WORKSITE_ADDRESS,
    SYNTHETIC_TAKEOFF_WORKSITE_KEY,
    SYNTHETIC_TAKEOFF_WORKSITE_NAME,
    build_demo_calc_plan,
    build_demo_code_assignments,
    build_demo_takeoff_decisions,
    build_synthetic_approval,
    build_synthetic_catalog_workbook,
    build_synthetic_estimate_approval,
    build_synthetic_multi_valuation,
    build_synthetic_previous_mapao,
)
from croquito_worker.valuation.takeoff_eval import run_takeoff_eval
from croquito_worker.valuation.takeoff_fixture import extract_takeoff_fixture
from croquito_worker.valuation.takeoff_overlay import (
    render_takeoff_overlay,
    save_takeoff_overlay,
)

PREVIOUS_MAPAO_FILENAME = "previous-mapao.xlsx"
CATALOG_FILENAME = "catalog.json"
CONTRACT_FILENAME = "contract-workbook.json"
IMPORT_REPORT_FILENAME = "import-report.json"
IMPORT_DIAGNOSIS_FILENAME = "import-diagnosis.json"
CATALOG_IMPORT_REPORT_FILENAME = "catalog-import-report.json"
EMOP_IMPORT_REPORT_FILENAME = "emop-import-report.json"
SINAPI_IMPORT_REPORT_FILENAME = "sinapi-import-report.json"
SICRO_IMPORT_REPORT_FILENAME = "sicro-import-report.json"
COMPOSITIONS_FILENAME = "compositions.json"
COMPOSITIONS_IMPORT_REPORT_FILENAME = "compositions-import-report.json"
ESTIMATE_FILENAME = "estimate.json"
WORKBOOK_FILENAME = "medicao.xlsx"
VALUATION_FILENAME = "valuation.json"
AUDIT_FILENAME = "audit.json"
PARITY_REPORT_FILENAME = "parity-report.json"
BULLETIN_COMPARE_REPORT_FILENAME = "bulletin-compare.json"
TAKEOFF_PACKET_FILENAME = "takeoff-packet.json"
TAKEOFF_OVERLAY_FILENAME = "takeoff-overlay.png"
TAKEOFF_DECISIONS_FILENAME = "takeoff-decisions.json"
TAKEOFF_REGISTRATION_REPORT_FILENAME = "takeoff-registration.json"
CODE_SUGGESTIONS_FILENAME = "code-suggestions.json"
CODE_ASSIGNMENT_DECISIONS_FILENAME = "code-assignment-decisions.json"
CODE_ASSIGNMENTS_FILENAME = "code-assignments.json"
CALC_PLAN_FILENAME = "calc-plan.json"
CALC_MATRIX_FILENAME = "calc-matrix.json"
AMENDMENT_DOSSIER_FILENAME = "amendment-dossier.json"
ESTIMATE_DEMO_SCO_SOURCE_FILENAME = "sco-catalogo-sintetico.xlsx"
ESTIMATE_DEMO_EMOP_SOURCE_FILENAME = "emop-catalogo-sintetico.dbf"
CATALOG_SCO_FILENAME = "catalog-sco.json"
CATALOG_EMOP_FILENAME = "catalog-emop.json"
CATALOG_COMPOSITION_FILENAME = "catalog-composition.json"
"""Nomes da demo do orçamento-base: um catálogo por fonte, nunca um `catalog.json` só.

A cascata é dado ordenado e cada fonte é um arquivo próprio — juntar as três num arquivo
com o nome padrão apagaria a fronteira que o `ADR-0027` existe para manter visível."""

SYNONYMS_FILENAME = "synonyms.json"
"""Sinônimos de domínio opcionais da rodada (`DomainSynonyms`). Quando o diretório da
rodada não tem este arquivo, `load_round_synonyms` cai no seed empacotado
(`default_domain_synonyms`) — a rodada nunca fica sem sinônimo algum."""

LOCAL_SERVER_DEFAULT_HOST = "127.0.0.1"
LOCAL_SERVER_DEFAULT_PORT = 8801
"""Padrões do `serve`: ferramenta local, então o bind não sai da máquina sem `--host`."""

_PENDING_WORKBOOK_FILENAME = ".medicao-pendente.xlsx"
"""Nome do arquivo antes da auditoria: oculto, temporário e com a extensão que o openpyxl
reabre. Só vira `medicao.xlsx` depois que a auditoria de round-trip aprova."""

ESTIMATE_WORKBOOK_FILENAME = "orcamento.xlsx"
ESTIMATE_WORKBOOK_AUDIT_FILENAME = "orcamento-audit.json"
_PENDING_ESTIMATE_WORKBOOK_FILENAME = ".orcamento-pendente.xlsx"
"""Mesmo desenho do par acima (ADR-0038), para a planilha do orçamento-base."""


@dataclass(frozen=True, slots=True)
class ValuationImportResult:
    """Artefatos e modelos produzidos pela importação do MAPÃO do cliente."""

    catalog_path: Path
    contract_path: Path
    report_path: Path
    template: WorkbookTemplate
    catalog: PriceCatalog
    contract: ContractWorkbook
    notes: ContractImportNotes
    report: dict[str, object]


@dataclass(frozen=True, slots=True)
class ValuationCatalogImportResult:
    """Artefatos produzidos pela importação isolada do catálogo de preços.

    Sem `contract`/`notes`: este comando nunca lê o consolidado, então não há o que
    carregar sobre ele. `report` já traz o campo `consolidado: "not_imported"`.
    """

    catalog_path: Path
    report_path: Path
    template: WorkbookTemplate
    catalog: PriceCatalog
    report: dict[str, object]


@dataclass(frozen=True, slots=True)
class ValuationEmopImportResult:
    """Artefatos produzidos pela importação isolada do catálogo EMOP (.DBF).

    Sem `template`: o layout do EMOP é `EmopCatalogLayout`, não `WorkbookTemplate` — o
    catálogo EMOP nunca vem de uma planilha do MAPÃO. `catalog.origin` sai sempre
    `PriceOrigin.EMOP`; é esse dado que os guardrails da cadeia licitada
    (`BULLETIN_PRICE_ORIGIN_FORBIDDEN`) usam para recusar este catálogo em
    `build-calc`/`export-valuation`.
    """

    catalog_path: Path
    report_path: Path
    layout: EmopCatalogLayout
    catalog: PriceCatalog
    report: dict[str, object]


@dataclass(frozen=True, slots=True)
class ValuationSinapiImportResult:
    """Artefatos produzidos pela importação isolada do catálogo SINAPI (.xlsx).

    Espelho de `ValuationEmopImportResult`: sem `template` (o layout da SINAPI é
    `SinapiCatalogLayout`, não `WorkbookTemplate`). `catalog.origin` sai sempre
    `PriceOrigin.SINAPI`; é esse dado que os guardrails da cadeia licitada
    (`BULLETIN_PRICE_ORIGIN_FORBIDDEN`) usam para recusar este catálogo em
    `build-calc`/`export-valuation`.
    """

    catalog_path: Path
    report_path: Path
    layout: SinapiCatalogLayout
    catalog: PriceCatalog
    report: dict[str, object]


@dataclass(frozen=True, slots=True)
class ValuationSicroImportResult:
    """Artefatos produzidos pela importação isolada do catálogo SICRO (.xlsx).

    Espelho de `ValuationEmopImportResult`: sem `template` (o layout da SICRO é
    `SicroCatalogLayout`, não `WorkbookTemplate`). `catalog.origin` sai sempre
    `PriceOrigin.SICRO`; é esse dado que os guardrails da cadeia licitada
    (`BULLETIN_PRICE_ORIGIN_FORBIDDEN`) usam para recusar este catálogo em
    `build-calc`/`export-valuation`.
    """

    catalog_path: Path
    report_path: Path
    layout: SicroCatalogLayout
    catalog: PriceCatalog
    report: dict[str, object]


@dataclass(frozen=True, slots=True)
class ValuationCompositionImportResult:
    """Artefatos produzidos pela compilação das composições manuais em catálogo.

    Sem `template` e sem `layout`: composição não vem de planilha nem de .DBF, ela É o
    documento canônico de entrada. `catalog.origin` sai sempre `PriceOrigin.COMPOSITION`, e
    é esse dado que o guardrail da medição licitada (`BULLETIN_PRICE_ORIGIN_FORBIDDEN`) usa
    para recusar este catálogo em `build-calc`/`export-valuation`.
    """

    catalog_path: Path
    report_path: Path
    composition_set: CompositionSet
    catalog: PriceCatalog
    report: dict[str, object]


@dataclass(frozen=True, slots=True)
class BuildEstimateResult:
    """Orçamento-base de uma obra montado sobre a cascata, sem contrato e ainda não assinado.

    Montar não é aprovar (ADR-0046): `build-estimate` devolve o orçamento sem `approval`, e
    é a aprovação nominal — ato próprio — que abre o portão de exportação.
    """

    estimate: Estimate
    estimate_path: Path


@dataclass(frozen=True, slots=True)
class EstimateDemoResult:
    """Cadeia do orçamento-base percorrida ponta a ponta sobre a prancha sintética.

    `cascade` sai na ordem em que as fontes foram declaradas — é ela que o orçamento
    publicado carrega no manifesto e que dá sentido à proveniência de cada linha.
    """

    plate: PlateArtifacts
    packet: TakeoffPacket
    packet_path: Path
    takeoff_decisions_path: Path
    cascade: tuple[PriceCatalog, ...]
    catalog_paths: tuple[Path, ...]
    suggestions_path: Path
    assignment_decisions_path: Path
    assignments_path: Path
    assignments: CodeAssignmentSet
    calc_plan_path: Path
    compositions_path: Path
    estimate: Estimate
    estimate_path: Path
    workbook_path: Path | None
    workbook_audit: EstimateAuditReport
    workbook_audit_path: Path


@dataclass(frozen=True, slots=True)
class ValuationDemoResult:
    """Artefatos produzidos pela demonstração determinística da cadeia completa.

    Os campos do takeoff descrevem a quarta obra da medição, a que nasce da prancha
    sintética: prancha, pacote revisado, sugestão, confirmação de código e plano de
    cálculo — cada ato com o seu artefato, na ordem em que foi praticado.
    """

    previous_path: Path
    catalog_path: Path
    contract_path: Path
    workbook_path: Path
    valuation_path: Path
    audit_path: Path
    plate: PlateArtifacts
    takeoff_packet: TakeoffPacket
    takeoff_packet_path: Path
    takeoff_decisions_path: Path
    suggestions_path: Path
    assignment_decisions_path: Path
    assignments_path: Path
    calc_plan_path: Path
    takeoff_build: CalcBuildResult
    template: WorkbookTemplate
    catalog: PriceCatalog
    contract: ContractWorkbook
    valuation: Valuation
    write_report: WriteReport
    audit: AuditReport


@dataclass(frozen=True, slots=True)
class TakeoffExtractionResult:
    """Prancha sintética gerada e o pacote de takeoff extraído dela."""

    plate: PlateArtifacts
    packet: TakeoffPacket
    packet_path: Path
    overlay_path: Path


@dataclass(frozen=True, slots=True)
class TakeoffReviewResult:
    """Pacote revisado e os artefatos publicados pela revisão."""

    packet: TakeoffPacket
    packet_path: Path
    overlay_path: Path | None


@dataclass(frozen=True, slots=True)
class TakeoffRegistrationResult:
    """Pacote reassentado, o relatório do ajuste e os três artefatos publicados."""

    packet: TakeoffPacket
    registration: LegendRegistrationReport
    packet_path: Path
    overlay_path: Path
    report_path: Path


@dataclass(frozen=True, slots=True)
class CodeSuggestionResult:
    """Shortlist de códigos e o artefato publicado com ela.

    `refinement_executions` só tem entrada quando o refino pago rodou: vazio, o artefato é
    a shortlist lexical determinística, e é o próprio `suggester_version` do arquivo que
    conta qual das duas foi publicada. É uma tupla porque o refino fatia os itens em lotes
    que caibam no payload do provider — uma chamada paga por lote —, e o comando precisa
    imprimir o custo TOTAL, não o da primeira.

    `matching` e `semantic_reason` contam a outra dimensão: se a shortlist foi montada com
    o braço semântico (`hybrid`) ou só com o léxico (`lexical`) e, neste caso, por quê —
    índice ausente, teto de gasto ausente ou `--no-semantic`. Degradação declarada, nunca
    silenciosa. `lexical` aqui é o braço léxico da MESMA via de fusão, sem a perna paga;
    a via Dice (`lexical-sco-suggester-v1`) só sobrevive na cascata do orçamento-base.
    """

    suggestions: CodeSuggestionSet
    suggestions_path: Path
    refinement_executions: tuple[ProviderExecution, ...] = ()
    matching: str = "lexical"
    semantic_reason: str | None = None
    embedded_queries: int = 0
    embeddings_execution: EmbeddingsExecution | None = None


@dataclass(frozen=True, slots=True)
class IndexCatalogResult:
    """Índice de embeddings do catálogo: o que foi construído, reusado ou substituído.

    `build` é `None` quando o índice já existia para o mesmo catálogo — nesse caso nenhuma
    chamada paga aconteceu, e é por isso que custo e tokens não existem no relatório.
    """

    build: CatalogIndexBuild | None
    index_path: Path
    status: str
    model_id: str
    item_count: int
    dims: int


@dataclass(frozen=True, slots=True)
class RealLegendExtractionResult:
    """Legenda extraída de uma prancha real por provider, com lineage e artefatos."""

    packet: TakeoffPacket
    execution: ProviderExecution
    source_sha256: str
    packet_path: Path
    overlay_path: Path


@dataclass(frozen=True, slots=True)
class CodeAssignmentResult:
    """Confirmações de código do orçamentista e o artefato publicado com elas."""

    assignments: CodeAssignmentSet
    assignments_path: Path


@dataclass(frozen=True, slots=True)
class BuildCalcResult:
    """Medição de uma obra montada do takeoff confirmado, ainda sem aprovação."""

    valuation: Valuation
    valuation_path: Path
    excluded_item_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BuildAmendmentDossierResult:
    """Dossiê do aditivo montado do takeoff confirmado e das confirmações de código."""

    dossier: AmendmentDossier
    dossier_path: Path


@dataclass(frozen=True, slots=True)
class TakeoffDemoResult:
    """Cadeia de takeoff percorrida ponta a ponta sobre a prancha sintética."""

    plate: PlateArtifacts
    proposed: TakeoffPacket
    reviewed: TakeoffPacket
    decisions_path: Path
    packet_path: Path
    overlay_path: Path


def _serialize(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _document(model: BaseModel) -> str:
    """JSON do modelo pelo próprio Pydantic: `Decimal` sai como texto, nunca como float."""
    return model.model_dump_json(indent=2) + "\n"


def _print(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def _load_template(path: Path | None) -> WorkbookTemplate:
    """Template informado como dado; sem `--template`, o layout sintético padrão."""
    if path is None:
        return default_template()
    return WorkbookTemplate.model_validate_json(path.read_text(encoding="utf-8"))


def _refused_payload(error: Exception) -> dict[str, object]:
    """Recusa fechada em formato estável: código de domínio, mensagem e detalhes.

    Um invariante quebrado dentro de um validador do Pydantic chega encapsulado numa
    `ValidationError`; o código de domínio original é recuperado em vez de perdido, para
    que quem chama continue lendo `refused` e não texto de exceção.
    """
    if isinstance(error, ValuationValidationError):
        return {"refused": error.code, "message": error.message, "details": error.details}
    if isinstance(error, ValidationError):
        domain = valuation_errors(error)
        if domain:
            first = domain[0]
            return {"refused": first.code, "message": first.message, "details": first.details}
        return {
            "refused": "MODEL_VALIDATION_FAILED",
            "message": "o documento não corresponde ao contrato do modelo",
            "details": {
                "errors": [
                    {
                        "loc": ".".join(str(part) for part in line["loc"]),
                        "type": line["type"],
                    }
                    for line in error.errors()
                ]
            },
        }
    raise error  # pragma: no cover - só chamado com os dois tipos acima


def _provider_refusal(error: ProviderExecutionError) -> dict[str, object]:
    """Falha de provider em comando pago: recusa fechada, sem publicar nada pela metade.

    O código de falha do adapter (`TIMEOUT`, `BUDGET_EXCEEDED`, `INVALID_SCHEMA`…) vai em
    `details` e nunca a resposta bruta: payload de provider não volta para o cliente.
    """
    return {
        "refused": "PROVIDER_EXECUTION_FAILED",
        "message": "chamada ao provider falhou; nenhum artefato foi publicado",
        "details": {"code": error.code.value},
    }


def _build_paid_arm(arm_spec: str) -> tuple[str, str, ProviderAdapter]:
    """Traduz `NOME=PROVIDER:MODELO` no adapter pago, já com retry e teto de gasto.

    Três recusas fechadas antes de qualquer chamada: forma inválida do braço, provider
    `fixture` (observação fabricada não vira artefato de produção — fixture é coisa de eval
    e de teste) e ausência do teto de gasto obrigatório, que é a `ValueError` da fábrica
    traduzida para código estável.
    """
    name, separator, target = arm_spec.partition("=")
    provider, model_separator, model_id = target.partition(":")
    if not name or not separator or not provider or not model_separator or not model_id:
        raise ValuationValidationError(
            "REFINE_ARM_INVALID",
            "braço deve ter a forma NOME=PROVIDER:MODELO",
            {"arm": arm_spec},
        )
    if provider == "fixture":
        raise ValuationValidationError(
            "REFINE_ARM_FIXTURE_FORBIDDEN",
            "comando pago não aceita provider fixture; observação fabricada não é artefato",
            {"arm": arm_spec},
        )
    try:
        adapter = build_extraction_arm(provider=provider, model_id=model_id)
    except ValueError as error:
        raise ValuationValidationError(
            "REFINE_ARM_UNAVAILABLE",
            "braço pago indisponível; confira teto de gasto e credenciais do provider",
            {"arm": arm_spec, "reason": str(error)},
        ) from error
    return name, model_id, adapter


def _build_refine_arm(arm_spec: str) -> tuple[str, str, ProviderAdapter]:
    """Braço do refino de código. Seam próprio: o teste do caminho feliz o monkeypatcha."""
    return _build_paid_arm(arm_spec)


def _build_legend_arm(arm_spec: str) -> tuple[str, str, ProviderAdapter]:
    """Braço da extração de legenda. Seam próprio, pelo mesmo motivo do refino."""
    return _build_paid_arm(arm_spec)


def _unknown_units(catalog: PriceCatalog, contract: ContractWorkbook) -> list[str]:
    """Unidades normalizadas que nenhum alias do módulo reconhece — revisão humana."""
    known = set(UNIT_ALIASES.values())
    units = {entry.unit for entry in catalog.entries}
    units.update(line.unit for line in contract.lines)
    return sorted(unit for unit in units if unit not in known)


def _notes_payload(notes: ContractImportNotes) -> dict[str, object]:
    """O que a leitura observou sem recusar, em forma de relatório.

    Nada aqui alterou o consolidado: são as observações que o orçamentista precisa ver —
    a medição que falta na numeração, a linha separadora pulada, a célula cujo cache de
    fórmula chegou com ruído de ponto flutuante, o código fora da tabela SCO aceito por
    padrão extra do template e a linha de seção pulada na aba da prefeitura (com o
    subtotal de grupo ignorado, quando a linha carregava um).
    """
    return {
        "period_numbers": list(notes.period_numbers),
        "period_gaps": list(notes.period_gaps),
        "separator_rows": {
            "rows": list(notes.separator_rows),
            "count": len(notes.separator_rows),
        },
        "normalized": {
            "count": notes.normalized_count,
            "truncated": notes.normalized_truncated,
            "cells": [cell.as_details() for cell in notes.normalized_cells],
        },
        "extra_codes": [{"row": row, "code": code} for row, code in notes.extra_code_rows],
        "amendment_section_rows": {
            "count": len(notes.amendment_section_rows),
            "rows": [
                {
                    "row": row,
                    "ignored_subtotal": None if subtotal is None else str(subtotal),
                }
                for row, subtotal in notes.amendment_section_rows
            ],
        },
    }


def run_import_workbook(
    input_path: Path,
    output_dir: Path,
    template: WorkbookTemplate,
    *,
    source_label: str,
    reference_month: str,
    contract_label: str | None,
) -> ValuationImportResult:
    """Importa catálogo e consolidado do MESMO arquivo, sem tocar no original.

    O MAPÃO real embute a tabela de preços na própria pasta do contrato, então as duas
    leituras são feitas sobre o mesmo caminho. Nada é gravado antes das duas terminarem:
    uma importação que falha não deixa artefato pela metade — nem o catálogo, que é lido
    primeiro e só é publicado depois que o consolidado passou.
    """
    catalog = read_price_catalog(
        input_path,
        template,
        source_label=source_label,
        reference_month=reference_month,
    )
    contract, notes = read_contract_workbook_with_notes(
        input_path,
        template,
        source_label=source_label,
        contract_label=contract_label,
    )
    report: dict[str, object] = {
        "source_sha256": contract.source_sha256,
        "catalog_entries": len(catalog.entries),
        "contract_lines": len(contract.lines),
        "period_count": contract.period_count,
        "amendments": len(contract.amendments),
        "unknown_units": _unknown_units(catalog, contract),
        "notes": _notes_payload(notes),
    }
    catalog_path = output_dir / CATALOG_FILENAME
    contract_path = output_dir / CONTRACT_FILENAME
    report_path = output_dir / IMPORT_REPORT_FILENAME
    atomic_write_text(catalog_path, _document(catalog))
    atomic_write_text(contract_path, _document(contract))
    atomic_write_text(report_path, _serialize(report))
    return ValuationImportResult(
        catalog_path=catalog_path,
        contract_path=contract_path,
        report_path=report_path,
        template=template,
        catalog=catalog,
        contract=contract,
        notes=notes,
        report=report,
    )


def run_import_catalog(
    input_path: Path,
    output_dir: Path,
    template: WorkbookTemplate,
    *,
    source_label: str,
    reference_month: str,
) -> ValuationCatalogImportResult:
    """Importa só a aba de catálogo do MAPÃO, sem tocar nas abas do consolidado.

    Reusa a mesma leitura de `run_import_workbook` (`read_price_catalog`), mas nunca
    chama `read_contract_workbook_with_notes`: nenhuma aba do consolidado é aberta, então
    este comando nunca vê nem o portão semântico (`CONTRACT_SEMANTICS_DIVERGENT`) nem o
    dossiê que ele produz — uma recusa aqui é sempre de layout do catálogo em si.
    O relatório declara, com todas as letras, que o consolidado não foi importado e que
    `contract-workbook.json` não é gerado por este caminho.
    """
    catalog = read_price_catalog(
        input_path,
        template,
        source_label=source_label,
        reference_month=reference_month,
    )
    report: dict[str, object] = {
        "source_sha256": catalog.source_sha256,
        "template_label": template.label,
        "catalog_entries": len(catalog.entries),
        "family_count": len({entry.family_code for entry in catalog.entries}),
        "subgroup_count": len({entry.subgroup_code for entry in catalog.entries}),
        "consolidado": "not_imported",
        "note": (
            "catálogo publicado isoladamente: este comando NÃO valida acumulado nem "
            "saldo do consolidado e NÃO produz contract-workbook.json. Medição real "
            "exportável continua exigindo `import-workbook` completo, atrás do portão "
            "semântico do consolidado."
        ),
    }
    catalog_path = output_dir / CATALOG_FILENAME
    report_path = output_dir / CATALOG_IMPORT_REPORT_FILENAME
    atomic_write_text(catalog_path, _document(catalog))
    atomic_write_text(report_path, _serialize(report))
    return ValuationCatalogImportResult(
        catalog_path=catalog_path,
        report_path=report_path,
        template=template,
        catalog=catalog,
        report=report,
    )


def run_import_emop(
    input_path: Path,
    output_dir: Path,
    layout: EmopCatalogLayout,
) -> ValuationEmopImportResult:
    """Importa o catálogo EMOP (.DBF) offline, sem tocar em nada da cadeia da medição.

    O catálogo publicado nasce com `origin=PriceOrigin.EMOP`. Nenhum guardrail é
    contornado por este comando: `BULLETIN_PRICE_ORIGIN_FORBIDDEN` (`calc.py`,
    `workbook_writer.py`) continua recusando este catálogo em `build-calc` e
    `export-valuation` — a cadeia SCO → EMOP → composição só vale pré-licitação
    (orçamento-base, fase futura). O catálogo digital EMOP real é pago (assinatura GRE);
    não existe layout default aqui, `--layout` é sempre obrigatório.
    """
    catalog, notes = read_emop_catalog_with_report(input_path, layout)
    report: dict[str, object] = {
        "source_sha256": catalog.source_sha256,
        "layout_label": layout.source_label,
        "catalog_entries": len(catalog.entries),
        "family_count": len({entry.family_code for entry in catalog.entries}),
        "subgroup_count": len({entry.subgroup_code for entry in catalog.entries}),
        "deleted_records": {
            "count": notes.deleted_count,
            "rows": list(notes.deleted_rows),
        },
        "consolidado": "not_imported",
        "note": (
            "catálogo EMOP importado isoladamente, origin=emop: a cadeia da medição "
            "licitada nunca aceita este catálogo (BULLETIN_PRICE_ORIGIN_FORBIDDEN); a "
            "cadeia SCO -> EMOP -> composição vale só pré-licitação (fase futura). Este "
            "comando NÃO produz contract-workbook.json."
        ),
    }
    catalog_path = output_dir / CATALOG_FILENAME
    report_path = output_dir / EMOP_IMPORT_REPORT_FILENAME
    atomic_write_text(catalog_path, _document(catalog))
    atomic_write_text(report_path, _serialize(report))
    return ValuationEmopImportResult(
        catalog_path=catalog_path,
        report_path=report_path,
        layout=layout,
        catalog=catalog,
        report=report,
    )


def run_import_sinapi(
    input_path: Path,
    output_dir: Path,
    layout: SinapiCatalogLayout,
) -> ValuationSinapiImportResult:
    """Importa o catálogo SINAPI (.xlsx) offline, sem tocar em nada da cadeia da medição.

    Espelho de `run_import_emop` (ADR-0039, decisão 2). O catálogo publicado nasce com
    `origin=PriceOrigin.SINAPI`. Nenhum guardrail é contornado por este comando:
    `BULLETIN_PRICE_ORIGIN_FORBIDDEN` (`calc.py`, `workbook_writer.py`) continua recusando
    este catálogo em `build-calc` e `export-valuation` — a cadeia SCO → EMOP → SINAPI →
    SICRO → composição só vale pré-licitação (orçamento-base, fase futura). A tabela SINAPI
    real é pública, mas não existe layout default aqui, `--layout` é sempre obrigatório.
    """
    catalog, notes = read_sinapi_catalog_with_report(input_path, layout)
    report: dict[str, object] = {
        "source_sha256": catalog.source_sha256,
        "layout_label": layout.source_label,
        "catalog_entries": len(catalog.entries),
        "family_count": len({entry.family_code for entry in catalog.entries}),
        "subgroup_count": len({entry.subgroup_code for entry in catalog.entries}),
        "blank_rows": {
            "count": notes.blank_row_count,
            "rows": list(notes.blank_rows),
        },
        "consolidado": "not_imported",
        "note": (
            "catálogo SINAPI importado isoladamente, origin=sinapi: a cadeia da medição "
            "licitada nunca aceita este catálogo (BULLETIN_PRICE_ORIGIN_FORBIDDEN); a "
            "cadeia SCO -> EMOP -> SINAPI -> SICRO -> composição vale só pré-licitação "
            "(fase futura). Este comando NÃO produz contract-workbook.json."
        ),
    }
    catalog_path = output_dir / CATALOG_FILENAME
    report_path = output_dir / SINAPI_IMPORT_REPORT_FILENAME
    atomic_write_text(catalog_path, _document(catalog))
    atomic_write_text(report_path, _serialize(report))
    return ValuationSinapiImportResult(
        catalog_path=catalog_path,
        report_path=report_path,
        layout=layout,
        catalog=catalog,
        report=report,
    )


def run_import_sicro(
    input_path: Path,
    output_dir: Path,
    layout: SicroCatalogLayout,
) -> ValuationSicroImportResult:
    """Importa o catálogo SICRO (.xlsx) offline, sem tocar em nada da cadeia da medição.

    Espelho de `run_import_emop` (ADR-0039, decisão 2). O catálogo publicado nasce com
    `origin=PriceOrigin.SICRO`. Nenhum guardrail é contornado por este comando:
    `BULLETIN_PRICE_ORIGIN_FORBIDDEN` (`calc.py`, `workbook_writer.py`) continua recusando
    este catálogo em `build-calc` e `export-valuation` — a cadeia SCO → EMOP → SINAPI →
    SICRO → composição só vale pré-licitação (orçamento-base, fase futura). A tabela SICRO
    real é pública, mas não existe layout default aqui, `--layout` é sempre obrigatório.
    """
    catalog, notes = read_sicro_catalog_with_report(input_path, layout)
    report: dict[str, object] = {
        "source_sha256": catalog.source_sha256,
        "layout_label": layout.source_label,
        "catalog_entries": len(catalog.entries),
        "family_count": len({entry.family_code for entry in catalog.entries}),
        "subgroup_count": len({entry.subgroup_code for entry in catalog.entries}),
        "blank_rows": {
            "count": notes.blank_row_count,
            "rows": list(notes.blank_rows),
        },
        "consolidado": "not_imported",
        "note": (
            "catálogo SICRO importado isoladamente, origin=sicro: a cadeia da medição "
            "licitada nunca aceita este catálogo (BULLETIN_PRICE_ORIGIN_FORBIDDEN); a "
            "cadeia SCO -> EMOP -> SINAPI -> SICRO -> composição vale só pré-licitação "
            "(fase futura). Este comando NÃO produz contract-workbook.json."
        ),
    }
    catalog_path = output_dir / CATALOG_FILENAME
    report_path = output_dir / SICRO_IMPORT_REPORT_FILENAME
    atomic_write_text(catalog_path, _document(catalog))
    atomic_write_text(report_path, _serialize(report))
    return ValuationSicroImportResult(
        catalog_path=catalog_path,
        report_path=report_path,
        layout=layout,
        catalog=catalog,
        report=report,
    )


def run_import_compositions(input_path: Path, output_dir: Path) -> ValuationCompositionImportResult:
    """Compila as composições manuais do orçamentista num catálogo `origin=composition`.

    A entrada é o documento canônico `CompositionSet` (não há planilha a interpretar aqui:
    a composição nasce estruturada). O preço unitário de cada composição é **recomputado**
    na validação do modelo — divergência recusa (`COMPOSITION_TOTAL_MISMATCH`) e nada é
    publicado. O catálogo publicado fica amarrado por digest ao arquivo de origem, e
    reimportar o mesmo arquivo devolve o mesmo id.

    Como o `import-emop`, este comando não contorna nenhum guardrail: a cadeia da medição
    licitada continua recusando este catálogo (`BULLETIN_PRICE_ORIGIN_FORBIDDEN`); a
    cascata SCO → EMOP → composição vale só pré-licitação (`ADR-0027`).
    """
    composition_set = CompositionSet.model_validate_json(input_path.read_text(encoding="utf-8"))
    source_sha256 = file_sha256(input_path)
    catalog = compile_compositions(composition_set, source_sha256=source_sha256)
    line_kinds: dict[str, int] = {}
    for composition in composition_set.compositions:
        for line in composition.lines:
            line_kinds[line.kind] = line_kinds.get(line.kind, 0) + 1
    report: dict[str, object] = {
        "source_sha256": source_sha256,
        "source_label": composition_set.source_label,
        "reference_month": composition_set.reference_month,
        "compositions": len(composition_set.compositions),
        "composition_lines": dict(sorted(line_kinds.items())),
        "catalog_entries": len(catalog.entries),
        "consolidado": "not_imported",
        "note": (
            "composições compiladas em catálogo origin=composition: a cadeia da medição "
            "licitada nunca aceita este catálogo (BULLETIN_PRICE_ORIGIN_FORBIDDEN); a "
            "cascata SCO -> EMOP -> composição vale só pré-licitação (build-estimate). "
            "Este comando NÃO produz contract-workbook.json."
        ),
    }
    catalog_path = output_dir / CATALOG_FILENAME
    report_path = output_dir / COMPOSITIONS_IMPORT_REPORT_FILENAME
    atomic_write_text(catalog_path, _document(catalog))
    atomic_write_text(report_path, _serialize(report))
    return ValuationCompositionImportResult(
        catalog_path=catalog_path,
        report_path=report_path,
        composition_set=composition_set,
        catalog=catalog,
        report=report,
    )


def run_export_valuation(
    valuation: Valuation,
    contract: ContractWorkbook,
    catalog: PriceCatalog,
    template: WorkbookTemplate,
    output_dir: Path,
) -> tuple[Path | None, AuditReport]:
    """Grava a pasta em nome temporário e só a publica com a auditoria aprovada.

    O portão de exportação já correu antes daqui. Este passo cobre o outro lado do risco:
    uma pasta que a auditoria de round-trip reprova não pode chegar ao cliente, então ela
    é gravada com nome temporário, conferida e removida em vez de renomeada.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    pending_path = output_dir / _PENDING_WORKBOOK_FILENAME
    workbook_path = output_dir / WORKBOOK_FILENAME
    try:
        write_valuation_workbook(valuation, catalog, template, pending_path, contract)
        audit = audit_workbook(pending_path, valuation, catalog, template, contract)
        if audit.status != "ok":
            return None, audit
        os.replace(pending_path, workbook_path)
        return workbook_path, audit
    finally:
        pending_path.unlink(missing_ok=True)


def run_export_estimate_workbook(
    estimate: Estimate, template: WorkbookTemplate, output_dir: Path
) -> tuple[Path | None, EstimateAuditReport]:
    """Grava a planilha do orçamento-base em nome pendente e só a publica com a auditoria
    aprovada — o mesmo desenho de `run_export_valuation` (ADR-0038): nome temporário,
    auditoria de round-trip e só então `os.replace`; falha do auditor não publica nada e
    o pendente é removido no `finally`.

    O portão de aprovação do DOMÍNIO corre aqui, antes de qualquer escrita (ADR-0046,
    decisão 3): orçamento sem aprovação nominal válida não vira arquivo nenhum, nem
    temporário. É o que faz o CLI obedecer à mesma regra que a API, em vez de haver duas
    verdades sobre o mesmo artefato. Ao contrário do irmão da medição, o portão daqui não
    recebe contrato: saldo e período não existem deste lado da fronteira.
    """
    estimate.ensure_exportable()
    output_dir.mkdir(parents=True, exist_ok=True)
    pending_path = output_dir / _PENDING_ESTIMATE_WORKBOOK_FILENAME
    workbook_path = output_dir / ESTIMATE_WORKBOOK_FILENAME
    try:
        write_estimate_workbook(estimate, template, pending_path)
        audit = audit_estimate_workbook(pending_path, estimate, template)
        if audit.status != "ok":
            return None, audit
        os.replace(pending_path, workbook_path)
        return workbook_path, audit
    finally:
        pending_path.unlink(missing_ok=True)


def run_valuation_demo(output_dir: Path) -> ValuationDemoResult:
    """Percorre a cadeia completa sobre fixture sintética, da prancha à pasta auditada.

    MAPÃO anterior sintético → catálogo e consolidado importados do mesmo arquivo →
    prancha sintética → extração da legenda → revisão do orçamentista → sugestão lexical
    de código → confirmação de código → boletim e memória da quarta obra → medição do
    período seguinte com as quatro obras → aprovação nominal sintética → portão de
    exportação → pasta consolidada → auditoria de round-trip.

    Os artefatos do meio da cadeia (decisões, pacote revisado, sugestões, confirmações e
    plano de cálculo) são gravados assim que são produzidos, como o MAPÃO anterior: são
    insumos e evidência do ato, não a pasta publicada. Só os quatro JSONs finais esperam
    a auditoria aprovar.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
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

    plate = render_synthetic_plate(output_dir)
    proposed = extract_takeoff_fixture(plate)
    decisions = build_demo_takeoff_decisions(proposed)
    takeoff_decisions_path = output_dir / TAKEOFF_DECISIONS_FILENAME
    atomic_write_text(takeoff_decisions_path, _document(decisions))
    reviewed = apply_takeoff_decisions(proposed, decisions)
    takeoff_packet_path, _ = _publish_takeoff(reviewed, plate.image_path, output_dir)

    suggestions = build_code_suggestions(reviewed, catalog, contract)
    suggestions_path = output_dir / CODE_SUGGESTIONS_FILENAME
    atomic_write_text(suggestions_path, _document(suggestions))

    assignment_batch = build_demo_code_assignments(reviewed)
    assignment_decisions_path = output_dir / CODE_ASSIGNMENT_DECISIONS_FILENAME
    atomic_write_text(assignment_decisions_path, _document(assignment_batch))
    assignments = apply_code_assignments(reviewed, assignment_batch, catalog, contract)
    assignments_path = output_dir / CODE_ASSIGNMENTS_FILENAME
    atomic_write_text(assignments_path, _document(assignments))

    calc_plan = build_demo_calc_plan(reviewed)
    calc_plan_path = output_dir / CALC_PLAN_FILENAME
    atomic_write_text(calc_plan_path, _document(calc_plan))
    takeoff_build = build_worksite_bulletin(
        reviewed,
        assignments,
        catalog,
        worksite_key=SYNTHETIC_TAKEOFF_WORKSITE_KEY,
        worksite_name=SYNTHETIC_TAKEOFF_WORKSITE_NAME,
        address=SYNTHETIC_TAKEOFF_WORKSITE_ADDRESS,
        contract_label=SYNTHETIC_CONTRACT_LABEL,
        calc_plan=calc_plan,
    )

    valuation = build_synthetic_approval(
        build_synthetic_multi_valuation(contract, catalog, takeoff=takeoff_build)
    )
    valuation.ensure_exportable(contract)
    workbook_path = output_dir / WORKBOOK_FILENAME
    write_report = write_valuation_workbook(valuation, catalog, template, workbook_path, contract)
    audit = audit_workbook(workbook_path, valuation, catalog, template, contract)
    catalog_path = output_dir / CATALOG_FILENAME
    contract_path = output_dir / CONTRACT_FILENAME
    valuation_path = output_dir / VALUATION_FILENAME
    audit_path = output_dir / AUDIT_FILENAME
    if audit.status == "ok":
        atomic_write_text(catalog_path, _document(catalog))
        atomic_write_text(contract_path, _document(contract))
        atomic_write_text(valuation_path, _document(valuation))
        atomic_write_text(audit_path, _serialize(audit.model_dump(mode="json")))
    return ValuationDemoResult(
        previous_path=previous_path,
        catalog_path=catalog_path,
        contract_path=contract_path,
        workbook_path=workbook_path,
        valuation_path=valuation_path,
        audit_path=audit_path,
        plate=plate,
        takeoff_packet=reviewed,
        takeoff_packet_path=takeoff_packet_path,
        takeoff_decisions_path=takeoff_decisions_path,
        suggestions_path=suggestions_path,
        assignment_decisions_path=assignment_decisions_path,
        assignments_path=assignments_path,
        calc_plan_path=calc_plan_path,
        takeoff_build=takeoff_build,
        template=template,
        catalog=catalog,
        contract=contract,
        valuation=valuation,
        write_report=write_report,
        audit=audit,
    )


def _write_takeoff_packet(packet: TakeoffPacket, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    packet_path = output_dir / TAKEOFF_PACKET_FILENAME
    atomic_write_text(packet_path, _document(packet))
    return packet_path


def _publish_takeoff(
    packet: TakeoffPacket, image_path: Path, output_dir: Path
) -> tuple[Path, Path]:
    """Grava pacote e overlay do takeoff.

    O overlay é renderizado **antes** de qualquer escrita: digest que não bate recusa com
    o diretório de saída intacto, como acontece com a importação que falha.
    """
    overlay = render_takeoff_overlay(image_path, packet)
    packet_path = _write_takeoff_packet(packet, output_dir)
    return packet_path, save_takeoff_overlay(overlay, output_dir / TAKEOFF_OVERLAY_FILENAME)


def _takeoff_counts(packet: TakeoffPacket) -> dict[str, int]:
    """Contagem por estado, sempre com as quatro chaves — zero é informação."""
    counts = {status.value: 0 for status in TakeoffItemStatus}
    for item in packet.items:
        counts[item.status.value] += 1
    return {"items": len(packet.items), **counts, "pending": len(packet.pending_items())}


def _review_status(packet: TakeoffPacket) -> str:
    return "review_required" if packet.pending_items() else "complete"


def run_extract_legend(output_dir: Path) -> TakeoffExtractionResult:
    """Gera a prancha sintética e extrai a legenda dela, no mesmo comando.

    O par gerar+extrair é indivisível: a fixture só sabe ler a prancha que ela desenhou, e
    aceitar um PDF arbitrário aqui seria fabricar observação sobre documento real. A
    extração de prancha de cliente é marco futuro, com provider, entitlement contratual e
    teto de gasto — nada disso existe neste comando.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    plate = render_synthetic_plate(output_dir)
    packet = extract_takeoff_fixture(plate)
    packet_path, overlay_path = _publish_takeoff(packet, plate.image_path, output_dir)
    return TakeoffExtractionResult(
        plate=plate,
        packet=packet,
        packet_path=packet_path,
        overlay_path=overlay_path,
    )


def run_review_takeoff(
    packet_path: Path,
    decisions_path: Path,
    output_dir: Path,
    image_path: Path | None,
) -> TakeoffReviewResult:
    """Aplica o lote de decisões do orçamentista e publica a revisão do pacote."""
    packet = load_takeoff_packet(packet_path)
    batch = TakeoffDecisionBatch.model_validate_json(decisions_path.read_text(encoding="utf-8"))
    reviewed = apply_takeoff_decisions(packet, batch)
    if image_path is None:
        published_path, overlay_path = _write_takeoff_packet(reviewed, output_dir), None
    else:
        published_path, overlay_path = _publish_takeoff(reviewed, image_path, output_dir)
    return TakeoffReviewResult(
        packet=reviewed,
        packet_path=published_path,
        overlay_path=overlay_path,
    )


def run_register_takeoff(
    packet_path: Path, image_path: Path, output_dir: Path, *, restore_raw: bool = False
) -> TakeoffRegistrationResult:
    """Reprocessa um pacote de takeoff já publicado, reassentando o bbox de cada item.

    Espelho do `register-extraction` da geometria: sem chamada paga, determinístico, e
    fail-closed antes de qualquer escrita — pacote com item já decidido ou imagem cujo
    digest diverge do pacote é recusado por `register_legend_bboxes`, e nada é gravado.

    `restore_raw=True` reverte antes o pacote para o BRUTO, usando os `before` do
    `takeoff-registration.json` que já existe ao lado de `packet_path` (a mesma rodada
    anterior que produziu o `packet_path` de entrada) — permite reprocessar do zero, com
    um pipeline mais novo, sem nova chamada paga. Sem esse relatório ali, recusa fechado
    (`REGISTRATION_RESTORE_RAW_REPORT_MISSING`): não há bruto nenhum pra restaurar. A
    recusa por item decidido (`REGISTRATION_AFTER_DECISION`) vale igual, e é checada antes
    de qualquer restauração — mover a âncora depois de uma decisão reescreveria o que o
    orçamentista viu, restaurando ou não.
    """
    packet = load_takeoff_packet(packet_path)
    if restore_raw:
        previous_report_path = packet_path.parent / TAKEOFF_REGISTRATION_REPORT_FILENAME
        if not previous_report_path.is_file():
            raise ValuationValidationError(
                "REGISTRATION_RESTORE_RAW_REPORT_MISSING",
                "--restore-raw exige um takeoff-registration.json de uma rodada anterior "
                "ao lado do pacote, com os `before` a restaurar",
                {"packet": str(packet_path), "expected_report": str(previous_report_path)},
            )
        previous_report = json.loads(previous_report_path.read_text(encoding="utf-8"))
        packet = restore_raw_bboxes(packet, previous_report.get("adjusted", []))
    registered, registration = register_legend_bboxes(image_path, packet)
    packet_path_out, overlay_path = _publish_takeoff(registered, image_path, output_dir)
    report_path = output_dir / TAKEOFF_REGISTRATION_REPORT_FILENAME
    atomic_write_text(
        report_path,
        _serialize(
            {
                "adjusted": registration.adjusted,
                "unmatched_item_ids": registration.unmatched_item_ids,
                "band_count": registration.band_count,
                "method": registration.method,
                "global_scale": registration.global_scale,
                "global_shift_px": registration.global_shift_px,
                "shift_score": registration.shift_score,
                "shift_confidence": registration.shift_confidence,
            }
        ),
    )
    return TakeoffRegistrationResult(
        packet=registered,
        registration=registration,
        packet_path=packet_path_out,
        overlay_path=overlay_path,
        report_path=report_path,
    )


def build_synthetic_takeoff_decisions(packet: TakeoffPacket) -> TakeoffDecisionBatch:
    """Decisões do orçamentista sintético sobre todo item pendente da prancha.

    O item `proposed` é confirmado com a quantidade que a legenda trazia; o `ambiguous`
    só fecha porque o revisor informa uma quantidade — a extração continua sem tê-la.
    """
    return TakeoffDecisionBatch(
        decisions=[
            TakeoffDecisionInput(
                item_id=item.id,
                action="confirm",
                reviewer_id=SYNTHETIC_TAKEOFF_REVIEWER,
                reviewer_role="orcamentista",
                decided_at=SYNTHETIC_TAKEOFF_DECIDED_AT,
                quantity=(
                    SYNTHETIC_TAKEOFF_AMBIGUOUS_QUANTITY
                    if item.status is TakeoffItemStatus.AMBIGUOUS
                    else None
                ),
                note=(
                    SYNTHETIC_TAKEOFF_AMBIGUOUS_NOTE
                    if item.status is TakeoffItemStatus.AMBIGUOUS
                    else None
                ),
            )
            for item in packet.pending_items()
        ]
    )


def run_takeoff_demo(output_dir: Path) -> TakeoffDemoResult:
    """Percorre a cadeia do takeoff: prancha sintética, extração, revisão e overlay final.

    O lote de decisões é gravado junto (`takeoff-decisions.json`) para que a mesma revisão
    possa ser refeita à mão com `review-takeoff` — e para que fique visível que o pacote
    final não nasceu confirmado: ele foi decidido.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    plate = render_synthetic_plate(output_dir)
    proposed = extract_takeoff_fixture(plate)
    batch = build_synthetic_takeoff_decisions(proposed)
    decisions_path = output_dir / TAKEOFF_DECISIONS_FILENAME
    atomic_write_text(decisions_path, _document(batch))
    reviewed = apply_takeoff_decisions(proposed, batch)
    packet_path, overlay_path = _publish_takeoff(reviewed, plate.image_path, output_dir)
    return TakeoffDemoResult(
        plate=plate,
        proposed=proposed,
        reviewed=reviewed,
        decisions_path=decisions_path,
        packet_path=packet_path,
        overlay_path=overlay_path,
    )


def _load_catalog(path: Path) -> PriceCatalog:
    return PriceCatalog.model_validate_json(path.read_text(encoding="utf-8"))


def _load_cascade(paths: Sequence[Path]) -> tuple[PriceCatalog, ...]:
    """Cascata de fontes na ORDEM em que os `--catalog` foram declarados.

    A ordem é dado do comando, não preferência do código (`ADR-0027`); o portão do domínio
    (`ensure_price_cascade`) recusa cascata vazia ou com duas fontes da mesma origem.
    """
    cascade = tuple(_load_catalog(path) for path in paths)
    ensure_price_cascade(cascade)
    return cascade


def _load_contract(path: Path | None) -> ContractWorkbook | None:
    """Consolidado contratual é opcional na sugestão e na confirmação, como no domínio."""
    if path is None:
        return None
    return ContractWorkbook.model_validate_json(path.read_text(encoding="utf-8"))


def load_round_synonyms(round_dir: Path) -> DomainSynonyms:
    """Sinônimos de domínio da rodada: `synonyms.json` do diretório se existir, senão o seed.

    Espelho de `_load_contract` para um dado opcional — a diferença é que aqui SEMPRE existe
    uma tabela (o seed empacotado nunca falta), então o chamador não precisa tratar `None`.
    """
    path = round_dir / SYNONYMS_FILENAME
    if path.is_file():
        return DomainSynonyms.model_validate_json(path.read_text(encoding="utf-8"))
    return default_domain_synonyms()


SEMANTIC_DISABLED_BY_FLAG: Final = "braço semântico desligado por --no-semantic"
"""Motivo da degradação quando o operador dispensa a perna paga.

A mensagem continua exata depois de 2026-08-21: o que a flag desliga é o BRAÇO semântico,
e a shortlist sai da mesma via de fusão com o braço léxico sozinho
(`SCO_LEXICAL_IDF_SUGGESTER_VERSION`) — antes ela caía numa via diferente, a Dice."""

SEMANTIC_CASCADE_UNSUPPORTED: Final = (
    "braço semântico não cobre cascata de fontes; o índice de embeddings é de um catálogo só"
)
"""Degradação DECLARADA da sugestão com mais de um `--catalog` (orçamento-base).

O índice de embeddings é construído por catálogo (`index-catalog`), então não existe
vizinhança semântica sobre a cascata inteira sem uma rodada paga nova por fonte. Em vez de
inventar essa chamada, a shortlist sai lexical e o motivo viaja no relatório — a mesma
regra do índice ausente e do teto de gasto ausente."""


def run_index_catalog(catalog_path: Path, output_dir: Path) -> IndexCatalogResult:
    """Constrói o índice de embeddings de um catálogo — comando PAGO, uma vez por catálogo.

    Idempotente por digest E por receita de texto: índice já presente para o mesmo catálogo
    **e** construído com o mesmo texto por item é reusado sem nenhuma chamada, porque a
    segunda construção só gastaria de novo para produzir o mesmo vizinho. Índice de outro
    catálogo, ou da receita antiga, é substituído (é lixo para a rodada corrente) e o
    relatório diz que foi.
    """
    catalog = _load_catalog(catalog_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    index_path = output_dir / CATALOG_INDEX_FILENAME
    replaced = False
    if index_path.is_file():
        existing, _digest = read_catalog_index(index_path)
        if (
            existing.catalog_sha256 == catalog.source_sha256
            and existing.text_recipe == INDEX_TEXT_RECIPE
        ):
            return IndexCatalogResult(
                build=None,
                index_path=index_path,
                status="reused",
                model_id=existing.model_id,
                item_count=len(existing.codes),
                dims=existing.dims,
            )
        replaced = True
    try:
        adapter = build_embeddings_adapter()
    except ValueError as error:
        raise ValuationValidationError(
            "INDEX_EMBEDDINGS_UNAVAILABLE",
            "via de embeddings indisponível; confira teto de gasto e credencial do provider",
            {"reason": str(error)},
        ) from error
    build = build_catalog_index(catalog, adapter)
    atomic_write_text(index_path, index_document(build.index))
    return IndexCatalogResult(
        build=build,
        index_path=index_path,
        status="replaced" if replaced else "created",
        model_id=build.index.model_id,
        item_count=build.item_count,
        dims=build.index.dims,
    )


def run_suggest_codes(
    packet_path: Path,
    catalog_paths: Sequence[Path],
    contract_path: Path | None,
    output_dir: Path,
    *,
    refine_arm: str | None = None,
    semantic: bool = True,
) -> CodeSuggestionResult:
    """Sugere códigos do catálogo para os itens confirmados e publica a shortlist.

    Observação, não decisão: o artefato existe para o orçamentista escolher, e item sem
    candidato elegível sai declarado em `unmatched_item_ids` em vez de receber um palpite.

    Sinônimos de domínio vêm de `synonyms.json` em `output_dir` se existir (o mesmo
    diretório onde os demais artefatos da rodada moram), senão do seed empacotado
    (`load_round_synonyms`) — a shortlist lexical nunca fica sem tabela de sinônimo. A lista
    de ruído de legenda (`default_legend_noise()`, rodada 2.2) sempre vem do seed
    empacotado — sem override por rodada — e amortece o braço léxico da fusão híbrida.

    O braço semântico entra quando as três condições existem: índice do catálogo na rodada
    (`catalog-embeddings.json`), teto de gasto e credencial no ambiente. Faltando qualquer
    uma, a MESMA via monta a shortlist sem essa perna (braço léxico por cobertura
    ponderada) e o motivo viaja no resultado. Índice que não pertence ao catálogo informado
    é RECUSA, não degradação: quem rodou o comando apontou para uma rodada com índice velho
    e precisa saber disso.

    Com `refine_arm`, a shortlist (lexical ou híbrida) é montada primeiro e depois
    **reordenada** por um provider pago; o que se publica é a versão refinada, e o
    `suggester_version` mais o bloco `refinement` do artefato contam essa história. A
    escrita acontece só no fim: se o refino recusar ou o provider falhar, o diretório de
    saída fica intacto — publicar a lexical em silêncio faria o comando mentir sobre o que
    foi feito.

    Com mais de um `--catalog` (a cascata do orçamento-base) a shortlist abrange todas as
    fontes na ordem declarada e cada candidato diz de qual veio. As duas vias PAGAS ficam
    de fora desse caminho: o braço semântico degrada declaradamente para lexical
    (`SEMANTIC_CASCADE_UNSUPPORTED`, porque o índice é de um catálogo só) e o refino é
    recusado (`SUGGEST_REFINE_CASCADE_UNSUPPORTED`) em vez de mandar um payload de fontes
    misturadas para um provider treinado a reordenar shortlist de uma tabela.
    """
    packet = load_takeoff_packet(packet_path)
    cascade = _load_cascade(catalog_paths)
    contract = _load_contract(contract_path)
    synonyms = load_round_synonyms(output_dir)
    index_path = output_dir / CATALOG_INDEX_FILENAME

    matching = "lexical"
    semantic_reason: str | None = None
    embeddings_execution: EmbeddingsExecution | None = None
    embedded_queries = 0
    suggestions: CodeSuggestionSet | None = None

    if len(cascade) > 1:
        if refine_arm is not None:
            raise ValuationValidationError(
                "SUGGEST_REFINE_CASCADE_UNSUPPORTED",
                "refino pago não cobre cascata de fontes; rode a shortlist determinística "
                "ou refine uma fonte por vez",
                {"catalogs": len(cascade)},
            )
        suggestions = build_cascade_code_suggestions(packet, cascade, synonyms=synonyms)
        semantic_reason = SEMANTIC_CASCADE_UNSUPPORTED
        suggestions_path = output_dir / CODE_SUGGESTIONS_FILENAME
        atomic_write_text(suggestions_path, _document(suggestions))
        return CodeSuggestionResult(
            suggestions=suggestions,
            suggestions_path=suggestions_path,
            matching=matching,
            semantic_reason=semantic_reason,
        )

    catalog = cascade[0]
    if not semantic:
        semantic_reason = SEMANTIC_DISABLED_BY_FLAG
    elif not index_path.is_file():
        semantic_reason = SEMANTIC_INDEX_MISSING
    else:
        index = load_semantic_index(index_path, catalog)
        adapter, adapter_reason = embeddings_adapter_or_reason()
        labels = [item.label for item in packet.confirmed_items()]
        try:
            resolved = resolve_query_vectors(
                labels,
                index=index,
                cache_path=output_dir / QUERY_CACHE_FILENAME,
                adapter=adapter,
            )
        except ValuationValidationError as error:
            if error.code != "SEMANTIC_QUERY_NOT_CACHED":
                raise
            semantic_reason = adapter_reason or SEMANTIC_UNAVAILABLE_PREFIX
        else:
            suggestions = build_hybrid_code_suggestions(
                packet,
                catalog,
                contract,
                index=index,
                query_vectors=resolved.by_query,
                synonyms=synonyms,
                noise=default_legend_noise(),
            )
            matching = "hybrid"
            embeddings_execution = resolved.execution
            embedded_queries = resolved.embedded_count

    if suggestions is None:
        # Degradar é rodar a MESMA via com um braço a menos (`index=None`), não trocar de
        # algoritmo: `--no-semantic` significa "sem a perna semântica". Ver
        # `SCO_LEXICAL_IDF_SUGGESTER_VERSION` para a medição que tirou a via Dice daqui.
        suggestions = build_hybrid_code_suggestions(
            packet,
            catalog,
            contract,
            synonyms=synonyms,
            noise=default_legend_noise(),
        )
    refinement_executions: tuple[ProviderExecution, ...] = ()
    if refine_arm is not None:
        _name, _model_id, adapter_refine = _build_refine_arm(refine_arm)
        refinement = refine_code_suggestions(packet, suggestions, adapter_refine)
        suggestions, refinement_executions = refinement.suggestions, refinement.executions
    suggestions_path = output_dir / CODE_SUGGESTIONS_FILENAME
    atomic_write_text(suggestions_path, _document(suggestions))
    return CodeSuggestionResult(
        suggestions=suggestions,
        suggestions_path=suggestions_path,
        refinement_executions=refinement_executions,
        matching=matching,
        semantic_reason=semantic_reason,
        embedded_queries=embedded_queries,
        embeddings_execution=embeddings_execution,
    )


def run_extract_legend_real(
    image_path: Path,
    manifest_path: Path,
    output_dir: Path,
    *,
    arm_spec: str,
    plate_id: str,
    page_number: int,
    reserve_arm_spec: str | None = None,
) -> RealLegendExtractionResult:
    """Extrai a legenda de uma prancha real com provider pago e publica o pacote proposto.

    A ordem é a do comando de produção: braço (teto de gasto) → allowlist do documento →
    chamada → mapeamento → publicação. Nada é gravado antes de a extração inteira ter dado
    certo, e nenhum item nasce confirmado — o pacote sai `review_required` e o overlay sai
    com o banner de revisão obrigatória.

    `reserve_arm_spec` é opcional e passa pelos MESMOS gates do braço escolhido: ele é
    montado ANTES da chamada, então braço de reserva mal escrito recusa o comando inteiro
    em vez de virar surpresa no meio da degradação. Sem ele não existe reserva, e a falha
    do braço escolhido continua sendo a recusa fechada de sempre.
    """
    _name, _model_id, adapter = _build_legend_arm(arm_spec)
    reserve: ProviderAdapter | None = None
    if reserve_arm_spec is not None:
        _reserve_name, _reserve_model_id, reserve = _build_legend_arm(reserve_arm_spec)
    extraction = run_legend_extraction(
        image_path,
        manifest_path,
        adapter,
        plate_id=plate_id,
        page_number=page_number,
        reserve=reserve,
    )
    packet_path, overlay_path = _publish_takeoff(extraction.packet, image_path, output_dir)
    return RealLegendExtractionResult(
        packet=extraction.packet,
        execution=extraction.execution,
        source_sha256=extraction.source_sha256,
        packet_path=packet_path,
        overlay_path=overlay_path,
    )


def run_confirm_codes(
    packet_path: Path,
    decisions_path: Path,
    catalog_paths: Sequence[Path],
    contract_path: Path | None,
    previous_path: Path | None,
    output_dir: Path,
) -> CodeAssignmentResult:
    """Aplica as confirmações de código do orçamentista e publica o conjunto imutável.

    Com `--previous`, o conjunto anterior é carregado adiante e re-decisão sobre item já
    decidido é recusada pelo domínio — a confirmação não é sobrescrita aqui.

    Com um `--catalog` é a confirmação da medição de sempre. Com mais de um, é a do
    orçamento-base: cada confirmação precisa citar de qual fonte veio o código
    (`ASSIGNMENT_CATALOG_REQUIRED`) e o consolidado contratual passa a ser **proibido**
    (`ESTIMATE_CASCADE_CONTRACT_FORBIDDEN`) — contrato é da obra licitada, e lá a cascata
    não existe (`ADR-0027`).
    """
    packet = load_takeoff_packet(packet_path)
    batch = CodeAssignmentBatch.model_validate_json(decisions_path.read_text(encoding="utf-8"))
    cascade = _load_cascade(catalog_paths)
    contract = _load_contract(contract_path)
    previous = (
        None
        if previous_path is None
        else CodeAssignmentSet.model_validate_json(previous_path.read_text(encoding="utf-8"))
    )
    if len(cascade) > 1:
        if contract is not None:
            raise ValuationValidationError(
                "ESTIMATE_CASCADE_CONTRACT_FORBIDDEN",
                "consolidado contratual é da cadeia licitada; o orçamento-base com cascata "
                "de fontes não tem contrato",
                {"catalogs": len(cascade)},
            )
        assignments = apply_code_assignments_over_cascade(packet, batch, cascade, previous=previous)
    else:
        assignments = apply_code_assignments(packet, batch, cascade[0], contract, previous=previous)
    assignments_path = output_dir / CODE_ASSIGNMENTS_FILENAME
    atomic_write_text(assignments_path, _document(assignments))
    return CodeAssignmentResult(assignments=assignments, assignments_path=assignments_path)


def _excluded_item_ids(packet: TakeoffPacket, assignments: CodeAssignmentSet) -> tuple[str, ...]:
    """Itens confirmados no takeoff cujo código o orçamentista rejeitou.

    Projeção do que já está gravado nos dois artefatos, na mesma ordem de
    `CalcBuildResult.excluded_item_ids` (a do pacote): nenhuma regra do domínio é
    reimplementada aqui — quem decide o que entra no boletim continua sendo o builder.
    """
    rejected = {
        assignment.item_id
        for assignment in assignments.assignments
        if assignment.status == "rejected"
    }
    return tuple(item.id for item in packet.confirmed_items() if item.id in rejected)


def _load_calc_plan_and_matrix(
    calc_plan_path: Path | None, calc_matrix_path: Path | None
) -> tuple[CalcPlan | None, CalcMatrix | None]:
    """Lê plano (por item) e matriz (por serviço) de memória; declarar os dois é recusa.

    `CalcPlan` é o regime indexado por item e `CalcMatrix` o regime N:N indexado por serviço
    (ADR-0053): são duas memórias mutuamente exclusivas para o mesmo build, e o domínio não
    funde uma com a outra. Pedir as duas é `CALC_PLAN_AND_MATRIX_DECLARED`, recusado aqui
    antes de tocar o builder.
    """
    if calc_plan_path is not None and calc_matrix_path is not None:
        raise ValuationValidationError(
            "CALC_PLAN_AND_MATRIX_DECLARED",
            "plano de cálculo por item e matriz de contribuições por serviço não convivem "
            "no mesmo build",
            {"calc_plan": str(calc_plan_path), "calc_matrix": str(calc_matrix_path)},
        )
    calc_plan = (
        None
        if calc_plan_path is None
        else CalcPlan.model_validate_json(calc_plan_path.read_text(encoding="utf-8"))
    )
    calc_matrix = (
        None
        if calc_matrix_path is None
        else CalcMatrix.model_validate_json(calc_matrix_path.read_text(encoding="utf-8"))
    )
    return calc_plan, calc_matrix


def run_build_calc(
    packet_path: Path,
    assignments_path: Path,
    catalog_path: Path,
    output_dir: Path,
    *,
    worksite_key: str,
    worksite_name: str,
    period_number: int,
    reference_label: str,
    address: str | None,
    contract_label: str | None,
    calc_plan_path: Path | None,
    calc_matrix_path: Path | None,
) -> BuildCalcResult:
    """Monta boletim e memória de cálculo da obra e grava a medição **sem aprovação**.

    Aprovar e exportar continuam sendo atos separados: este comando só transforma
    quantitativo confirmado com código confirmado em medição de um período.
    """
    packet = load_takeoff_packet(packet_path)
    assignments = CodeAssignmentSet.model_validate_json(
        assignments_path.read_text(encoding="utf-8")
    )
    catalog = _load_catalog(catalog_path)
    calc_plan, calc_matrix = _load_calc_plan_and_matrix(calc_plan_path, calc_matrix_path)
    valuation = build_worksite_valuation(
        packet,
        assignments,
        catalog,
        worksite_key=worksite_key,
        worksite_name=worksite_name,
        period_number=period_number,
        reference_label=reference_label,
        address=address,
        contract_label=contract_label,
        calc_plan=calc_plan,
        calc_matrix=calc_matrix,
    )
    valuation_path = output_dir / VALUATION_FILENAME
    atomic_write_text(valuation_path, _document(valuation))
    return BuildCalcResult(
        valuation=valuation,
        valuation_path=valuation_path,
        excluded_item_ids=_excluded_item_ids(packet, assignments),
    )


def run_build_amendment_dossier(
    packet_path: Path,
    assignments_path: Path,
    output_dir: Path,
) -> BuildAmendmentDossierResult:
    """Monta o dossiê do aditivo a partir do takeoff confirmado e das confirmações de código.

    O dossiê instrui o pedido de aditivo de contrato (RE-RA); ele nunca precifica e nunca
    cria ou altera `Amendment`. Fail-closed: qualquer recusa não publica nenhum artefato,
    nem parcial.
    """
    packet = load_takeoff_packet(packet_path)
    assignments = CodeAssignmentSet.model_validate_json(
        assignments_path.read_text(encoding="utf-8")
    )
    dossier = build_amendment_dossier(packet, assignments)
    dossier_path = output_dir / AMENDMENT_DOSSIER_FILENAME
    atomic_write_text(dossier_path, _document(dossier))
    return BuildAmendmentDossierResult(dossier=dossier, dossier_path=dossier_path)


def run_build_estimate(
    packet_path: Path,
    assignments_path: Path,
    catalog_paths: Sequence[Path],
    output_dir: Path,
    *,
    worksite_key: str,
    worksite_name: str,
    bdi_percent: Decimal,
    address: str | None,
    calc_plan_path: Path | None,
    calc_matrix_path: Path | None,
) -> BuildEstimateResult:
    """Monta o orçamento-base da obra sobre a cascata declarada e publica `estimate.json`.

    Irmão de `build-calc` do outro lado da fronteira: aqui não há período, contrato, saldo
    nem aprovação — nada disso existe antes da licitação. O que existe é a proveniência por
    linha (origem, catálogo e data-base) e a lista declarada de itens que nenhuma fonte
    precificou. Recusa fechada não publica nada.
    """
    packet = load_takeoff_packet(packet_path)
    assignments = CodeAssignmentSet.model_validate_json(
        assignments_path.read_text(encoding="utf-8")
    )
    cascade = _load_cascade(catalog_paths)
    calc_plan, calc_matrix = _load_calc_plan_and_matrix(calc_plan_path, calc_matrix_path)
    result = build_worksite_estimate(
        packet,
        assignments,
        cascade,
        worksite_key=worksite_key,
        worksite_name=worksite_name,
        bdi_percent=bdi_percent,
        address=address,
        calc_plan=calc_plan,
        calc_matrix=calc_matrix,
    )
    estimate_path = output_dir / ESTIMATE_FILENAME
    atomic_write_text(estimate_path, _document(result.estimate))
    return BuildEstimateResult(estimate=result.estimate, estimate_path=estimate_path)


def run_estimate_demo(output_dir: Path) -> EstimateDemoResult:
    """Percorre a cadeia do orçamento-base sobre a fixture sintética, com as três origens.

    Catálogo SCO sintético (planilha) + catálogo EMOP sintético (.DBF, pelo importador
    real) + composição manual compilada → prancha sintética → extração da legenda →
    revisão do orçamentista → shortlist lexical sobre a cascata → confirmação de código
    citando a fonte de cada item → orçamento-base → aprovação nominal sintética → portão de
    exportação → planilha auditada.

    A aprovação não é enfeite da demonstração: desde o ADR-0046 o portão do domínio recusa
    despachar orçamento sem assinatura, e é o mesmo portão que a API invoca. Quem assina é
    o aprovador sintético, que não é o orçamentista que montou.

    Determinística de ponta a ponta: os digests das três fontes e o da imagem da prancha se
    repetem a cada execução, e as decisões humanas sintéticas têm data fixa. O único digest
    que não se repete é o do PDF (o pymupdf grava identificadores novos a cada `save`), e é
    por isso que o golden do orçamento fixa a estrutura e as relações, não aquele byte.

    Cada fonte é publicada no seu próprio `catalog-*.json`: juntar as três apagaria a
    fronteira licitada x pré-licitação dentro do artefato.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    sco_source_path = build_synthetic_catalog_workbook(
        output_dir / ESTIMATE_DEMO_SCO_SOURCE_FILENAME
    )
    sco_catalog = read_price_catalog(
        sco_source_path,
        default_template(),
        source_label=SYNTHETIC_CATALOG_LABEL,
        reference_month=SYNTHETIC_REFERENCE_MONTH,
    )
    emop_source_path = write_emop_dbf(output_dir / ESTIMATE_DEMO_EMOP_SOURCE_FILENAME)
    emop_catalog = read_emop_catalog(emop_source_path, emop_fixture_layout())
    compositions_path = output_dir / COMPOSITIONS_FILENAME
    composition_set = build_synthetic_composition_set()
    atomic_write_text(compositions_path, _document(composition_set))
    composition_catalog = compile_compositions(
        composition_set, source_sha256=file_sha256(compositions_path)
    )

    cascade = (sco_catalog, emop_catalog, composition_catalog)
    catalog_paths = (
        output_dir / CATALOG_SCO_FILENAME,
        output_dir / CATALOG_EMOP_FILENAME,
        output_dir / CATALOG_COMPOSITION_FILENAME,
    )
    for catalog, catalog_path in zip(cascade, catalog_paths, strict=True):
        atomic_write_text(catalog_path, _document(catalog))

    plate = render_synthetic_plate(output_dir)
    proposed = extract_takeoff_fixture(plate)
    decisions = build_demo_takeoff_decisions(proposed)
    takeoff_decisions_path = output_dir / TAKEOFF_DECISIONS_FILENAME
    atomic_write_text(takeoff_decisions_path, _document(decisions))
    reviewed = apply_takeoff_decisions(proposed, decisions)
    packet_path, _ = _publish_takeoff(reviewed, plate.image_path, output_dir)

    suggestions = build_cascade_code_suggestions(reviewed, cascade)
    suggestions_path = output_dir / CODE_SUGGESTIONS_FILENAME
    atomic_write_text(suggestions_path, _document(suggestions))

    assignment_batch = build_demo_estimate_assignments(reviewed, cascade)
    assignment_decisions_path = output_dir / CODE_ASSIGNMENT_DECISIONS_FILENAME
    atomic_write_text(assignment_decisions_path, _document(assignment_batch))
    assignments = apply_code_assignments_over_cascade(reviewed, assignment_batch, cascade)
    assignments_path = output_dir / CODE_ASSIGNMENTS_FILENAME
    atomic_write_text(assignments_path, _document(assignments))

    calc_plan = build_demo_calc_plan(reviewed)
    calc_plan_path = output_dir / CALC_PLAN_FILENAME
    atomic_write_text(calc_plan_path, _document(calc_plan))
    result = build_worksite_estimate(
        reviewed,
        assignments,
        cascade,
        worksite_key=SYNTHETIC_ESTIMATE_WORKSITE_KEY,
        worksite_name=SYNTHETIC_ESTIMATE_WORKSITE_NAME,
        bdi_percent=SYNTHETIC_ESTIMATE_BDI_PERCENT,
        address=SYNTHETIC_ESTIMATE_WORKSITE_ADDRESS,
        calc_plan=calc_plan,
    )
    estimate = build_synthetic_estimate_approval(result.estimate)
    estimate_path = output_dir / ESTIMATE_FILENAME
    atomic_write_text(estimate_path, _document(estimate))

    workbook_path, workbook_audit = run_export_estimate_workbook(
        estimate, default_template(), output_dir
    )
    workbook_audit_path = output_dir / ESTIMATE_WORKBOOK_AUDIT_FILENAME
    atomic_write_text(workbook_audit_path, _serialize(workbook_audit.model_dump(mode="json")))

    return EstimateDemoResult(
        plate=plate,
        packet=reviewed,
        packet_path=packet_path,
        takeoff_decisions_path=takeoff_decisions_path,
        cascade=cascade,
        catalog_paths=catalog_paths,
        suggestions_path=suggestions_path,
        assignment_decisions_path=assignment_decisions_path,
        assignments_path=assignments_path,
        assignments=assignments,
        calc_plan_path=calc_plan_path,
        compositions_path=compositions_path,
        estimate=estimate,
        estimate_path=estimate_path,
        workbook_path=workbook_path,
        workbook_audit=workbook_audit,
        workbook_audit_path=workbook_audit_path,
    )


def _audit_failure_payload(workbook_path: Path, audit: AuditReport) -> dict[str, object]:
    return {
        "status": audit.status,
        "workbook": str(workbook_path),
        "findings": [finding.model_dump(mode="json") for finding in audit.findings],
    }


def _estimate_audit_failure_payload(
    workbook_path: Path, audit: EstimateAuditReport
) -> dict[str, object]:
    return {
        "status": audit.status,
        "workbook": str(workbook_path),
        "findings": [finding.model_dump(mode="json") for finding in audit.findings],
    }


def _write_import_diagnosis(
    output_dir: Path, template: WorkbookTemplate, error: ContractSemanticsError
) -> Path:
    """Grava o dossiê da recusa semântica; ele é o único artefato de uma recusa dessas."""
    diagnosis_path = output_dir / IMPORT_DIAGNOSIS_FILENAME
    atomic_write_text(
        diagnosis_path,
        _serialize(
            {
                "refused": error.code,
                "source_sha256": error.source_sha256,
                "template_label": template.label,
                "summary": dict(error.diagnosis.summary),
                "finding_count": len(error.diagnosis.findings),
                "findings": error.diagnosis.as_details(),
            }
        ),
    )
    return diagnosis_path


def _command_import_workbook(args: argparse.Namespace) -> int:
    output_dir = Path(args.output)
    try:
        template = _load_template(args.template)
    except (ValuationValidationError, ValidationError) as error:
        _print(_refused_payload(error))
        return 2
    try:
        result = run_import_workbook(
            Path(args.input),
            output_dir,
            template,
            source_label=args.source_label,
            reference_month=args.reference_month,
            contract_label=args.contract_label,
        )
    except ContractSemanticsError as error:
        diagnosis_path = _write_import_diagnosis(output_dir, template, error)
        _print(
            {
                "refused": error.code,
                "summary": dict(error.diagnosis.summary),
                "finding_count": len(error.diagnosis.findings),
                "diagnosis": str(diagnosis_path),
            }
        )
        return 2
    except (ValuationValidationError, ValidationError) as error:
        _print(_refused_payload(error))
        return 2
    _print(
        {
            "input": str(args.input),
            "catalog": str(result.catalog_path),
            "contract": str(result.contract_path),
            "report": str(result.report_path),
            **result.report,
        }
    )
    return 0


def _command_import_catalog(args: argparse.Namespace) -> int:
    output_dir = Path(args.output)
    try:
        template = _load_template(args.template)
    except (ValuationValidationError, ValidationError) as error:
        _print(_refused_payload(error))
        return 2
    try:
        result = run_import_catalog(
            Path(args.input),
            output_dir,
            template,
            source_label=args.source_label,
            reference_month=args.reference_month,
        )
    except (ValuationValidationError, ValidationError) as error:
        _print(_refused_payload(error))
        return 2
    _print(
        {
            "input": str(args.input),
            "catalog": str(result.catalog_path),
            "report": str(result.report_path),
            **result.report,
        }
    )
    return 0


def _command_import_emop(args: argparse.Namespace) -> int:
    try:
        layout = EmopCatalogLayout.model_validate_json(
            Path(args.layout).read_text(encoding="utf-8")
        )
    except (ValuationValidationError, ValidationError) as error:
        _print(_refused_payload(error))
        return 2
    output_dir = Path(args.output)
    try:
        result = run_import_emop(Path(args.input), output_dir, layout)
    except (ValuationValidationError, ValidationError) as error:
        _print(_refused_payload(error))
        return 2
    _print(
        {
            "input": str(args.input),
            "catalog": str(result.catalog_path),
            "report": str(result.report_path),
            **result.report,
        }
    )
    return 0


def _command_import_sinapi(args: argparse.Namespace) -> int:
    try:
        layout = SinapiCatalogLayout.model_validate_json(
            Path(args.layout).read_text(encoding="utf-8")
        )
    except (ValuationValidationError, ValidationError) as error:
        _print(_refused_payload(error))
        return 2
    output_dir = Path(args.output)
    try:
        result = run_import_sinapi(Path(args.input), output_dir, layout)
    except (ValuationValidationError, ValidationError) as error:
        _print(_refused_payload(error))
        return 2
    _print(
        {
            "input": str(args.input),
            "catalog": str(result.catalog_path),
            "report": str(result.report_path),
            **result.report,
        }
    )
    return 0


def _command_import_sicro(args: argparse.Namespace) -> int:
    try:
        layout = SicroCatalogLayout.model_validate_json(
            Path(args.layout).read_text(encoding="utf-8")
        )
    except (ValuationValidationError, ValidationError) as error:
        _print(_refused_payload(error))
        return 2
    output_dir = Path(args.output)
    try:
        result = run_import_sicro(Path(args.input), output_dir, layout)
    except (ValuationValidationError, ValidationError) as error:
        _print(_refused_payload(error))
        return 2
    _print(
        {
            "input": str(args.input),
            "catalog": str(result.catalog_path),
            "report": str(result.report_path),
            **result.report,
        }
    )
    return 0


def _command_import_compositions(args: argparse.Namespace) -> int:
    output_dir = Path(args.output)
    try:
        result = run_import_compositions(Path(args.input), output_dir)
    except (ValuationValidationError, ValidationError) as error:
        _print(_refused_payload(error))
        return 2
    _print(
        {
            "input": str(args.input),
            "catalog": str(result.catalog_path),
            "report": str(result.report_path),
            **result.report,
        }
    )
    return 0


def _command_export_valuation(args: argparse.Namespace) -> int:
    output_dir = Path(args.output)
    try:
        template = _load_template(args.template)
        valuation = Valuation.model_validate_json(Path(args.valuation).read_text(encoding="utf-8"))
        contract = ContractWorkbook.model_validate_json(
            Path(args.contract).read_text(encoding="utf-8")
        )
        catalog = PriceCatalog.model_validate_json(Path(args.catalog).read_text(encoding="utf-8"))
    except (ValuationValidationError, ValidationError) as error:
        _print(_refused_payload(error))
        return 2

    try:
        valuation.ensure_exportable(contract)
    except ValuationValidationError as error:
        _print(
            {
                "refused": error.code,
                "message": error.message,
                "errors": error.details.get("errors", []),
            }
        )
        return 2

    try:
        workbook_path, audit = run_export_valuation(
            valuation, contract, catalog, template, output_dir
        )
    except (ValuationValidationError, ValidationError) as error:
        _print(_refused_payload(error))
        return 2

    audit_path = output_dir / AUDIT_FILENAME
    atomic_write_text(audit_path, _serialize(audit.model_dump(mode="json")))
    if workbook_path is None:
        _print(
            {
                **_audit_failure_payload(output_dir / WORKBOOK_FILENAME, audit),
                "published": False,
                "audit": str(audit_path),
            }
        )
        return 1
    _print(
        {
            "status": audit.status,
            "workbook": str(workbook_path),
            "workbook_sha256": audit.workbook_sha256,
            "audit": str(audit_path),
            "worksites": [worksite.worksite_key for worksite in audit.worksites],
            "general_sheet": audit.general_sheet,
            "amendment_sheet": audit.amendment_sheet,
            "checked_cells": audit.checked_cells,
            "formula_cells": audit.formula_cells,
            "pinned_cells": len(audit.pinned_cells),
            "total_amount": str(audit.total_amount),
        }
    )
    return 0


def _command_demo(args: argparse.Namespace) -> int:
    result = run_valuation_demo(Path(args.output))
    if result.audit.status != "ok":
        _print(_audit_failure_payload(result.workbook_path, result.audit))
        return 1
    _print(
        {
            "status": result.audit.status,
            "previous_mapao": str(result.previous_path),
            "catalog": str(result.catalog_path),
            "catalog_entries": len(result.catalog.entries),
            "contract": str(result.contract_path),
            "contract_lines": len(result.contract.lines),
            "period_number": result.valuation.period_number,
            "workbook": str(result.workbook_path),
            "valuation": str(result.valuation_path),
            "audit": str(result.audit_path),
            "workbook_sha256": result.audit.workbook_sha256,
            "worksites": [
                {
                    "worksite_key": worksite.worksite_key,
                    "bulletin_sheet": worksite.bulletin_sheet,
                    "memory_sheet": worksite.memory_sheet,
                    "total_amount": str(worksite.total_amount),
                }
                for worksite in result.audit.worksites
            ],
            "general_sheet": result.audit.general_sheet,
            "amendment_sheet": result.audit.amendment_sheet,
            "checked_cells": result.audit.checked_cells,
            "formula_cells": result.audit.formula_cells,
            "pinned_cells": len(result.audit.pinned_cells),
            "total_amount": str(result.valuation.total_amount),
            "takeoff": {
                "packet": str(result.takeoff_packet_path),
                "decisions": str(result.takeoff_decisions_path),
                "suggestions": str(result.suggestions_path),
                "assignment_decisions": str(result.assignment_decisions_path),
                "assignments": str(result.assignments_path),
                "calc_plan": str(result.calc_plan_path),
                **_takeoff_counts(result.takeoff_packet),
                "excluded": list(result.takeoff_build.excluded_item_ids),
            },
        }
    )
    return 0


def _command_parity(args: argparse.Namespace) -> int:
    output_dir = Path(args.output)
    try:
        template = _load_template(args.template)
        report = check_parity(Path(args.previous), template)
    except (ValuationValidationError, ValidationError) as error:
        _print(_refused_payload(error))
        return 2
    report_path = output_dir / PARITY_REPORT_FILENAME
    atomic_write_text(report_path, _serialize(report.model_dump(mode="json")))
    _print(
        {
            "workbook": str(args.previous),
            "workbook_sha256": report.workbook_sha256,
            "report": str(report_path),
            "formulas": report.formulas,
            "verified": report.verified,
            "divergent": report.divergent,
            "foreign": report.foreign,
            "cache_missing": report.cache_missing,
            "sheets": [sheet.model_dump(mode="json") for sheet in report.sheets],
        }
    )
    return 1 if report.divergent else 0


def _command_compare_bulletin(args: argparse.Namespace) -> int:
    output_dir = Path(args.output)
    try:
        template = _load_template(args.template)
        valuation = Valuation.model_validate_json(Path(args.valuation).read_text(encoding="utf-8"))
        reference = read_bulletin_lines(Path(args.reference), template, sheet_name=args.sheet)
        report = compare_bulletin(valuation, args.worksite, reference)
    except (ValuationValidationError, ValidationError) as error:
        _print(_refused_payload(error))
        return 2
    report_path = output_dir / BULLETIN_COMPARE_REPORT_FILENAME
    payload = report.model_dump(mode="json")
    payload["reference"] = {
        "workbook_sha256": reference.workbook_sha256,
        "sheet_name": reference.sheet_name,
        "declared_total": str(reference.declared_total),
        "declared_total_cell": reference.declared_total_ref,
        "lines": len(reference.lines),
        "skipped_rows": list(reference.skipped_rows),
    }
    atomic_write_text(report_path, _serialize(payload))
    _print(
        {
            "worksite_key": report.worksite_key,
            "valuation": str(args.valuation),
            "reference": str(args.reference),
            "sheet": args.sheet,
            "workbook_sha256": reference.workbook_sha256,
            "report": str(report_path),
            "zero_cent": report.zero_cent,
            "missing_in_reference": len(report.missing_in_reference),
            "missing_in_generated": len(report.missing_in_generated),
            "quantity_diffs": len(report.quantity_diffs),
            "unit_price_diffs": len(report.unit_price_diffs),
            "line_total_diffs": len(report.line_total_diffs),
            "bulletin_total_diff": report.bulletin_total_diff is not None,
            "unit_notes": len(report.unit_notes),
            "skipped_rows": len(reference.skipped_rows),
        }
    )
    return 0 if report.zero_cent else 1


def _command_extract_legend(args: argparse.Namespace) -> int:
    output_dir = Path(args.output)
    try:
        result = run_extract_legend(output_dir)
    except (ValuationValidationError, ValidationError) as error:
        _print(_refused_payload(error))
        return 2
    _print(
        {
            "plate_id": result.packet.plate_id,
            "page_number": result.packet.page_number,
            "pdf": str(result.plate.pdf_path),
            "image": str(result.plate.image_path),
            "pdf_sha256": result.packet.source_pdf_sha256,
            "image_sha256": result.packet.image_sha256,
            "packet": str(result.packet_path),
            "overlay": str(result.overlay_path),
            "extractor": result.packet.items[0].extractor,
            "review_status": _review_status(result.packet),
            **_takeoff_counts(result.packet),
        }
    )
    return 0


def _command_review_takeoff(args: argparse.Namespace) -> int:
    try:
        result = run_review_takeoff(
            Path(args.packet),
            Path(args.decisions),
            Path(args.output),
            None if args.image is None else Path(args.image),
        )
    except (ValuationValidationError, ValidationError) as error:
        _print(_refused_payload(error))
        return 2
    _print(
        {
            "plate_id": result.packet.plate_id,
            "packet": str(result.packet_path),
            "overlay": None if result.overlay_path is None else str(result.overlay_path),
            "review_status": _review_status(result.packet),
            **_takeoff_counts(result.packet),
        }
    )
    return 0


def _command_register_takeoff(args: argparse.Namespace) -> int:
    try:
        result = run_register_takeoff(
            Path(args.packet),
            Path(args.image),
            Path(args.output),
            restore_raw=args.restore_raw,
        )
    except (ValuationValidationError, ValidationError) as error:
        _print(_refused_payload(error))
        return 2
    _print(
        {
            "plate_id": result.packet.plate_id,
            "packet": str(result.packet_path),
            "overlay": str(result.overlay_path),
            "report": str(result.report_path),
            "band_count": result.registration.band_count,
            "adjusted": len(result.registration.adjusted),
            "unmatched": len(result.registration.unmatched_item_ids),
            "method": result.registration.method,
            "global_scale": result.registration.global_scale,
            "global_shift_px": result.registration.global_shift_px,
            "shift_score": result.registration.shift_score,
            "shift_confidence": result.registration.shift_confidence,
        }
    )
    return 0


def _command_takeoff_demo(args: argparse.Namespace) -> int:
    try:
        result = run_takeoff_demo(Path(args.output))
    except (ValuationValidationError, ValidationError) as error:
        _print(_refused_payload(error))
        return 2
    _print(
        {
            "plate_id": result.reviewed.plate_id,
            "pdf": str(result.plate.pdf_path),
            "image": str(result.plate.image_path),
            "decisions": str(result.decisions_path),
            "packet": str(result.packet_path),
            "overlay": str(result.overlay_path),
            "reviewer_id": SYNTHETIC_TAKEOFF_REVIEWER,
            "proposed_pending": len(result.proposed.pending_items()),
            "review_status": _review_status(result.reviewed),
            **_takeoff_counts(result.reviewed),
        }
    )
    return 0


def _execution_payload(execution: ProviderExecution) -> dict[str, object]:
    """Lineage e custo de uma chamada paga, no formato que os comandos imprimem.

    IDs, versão de prompt, tokens, custo e latência — nunca a resposta bruta nem o texto
    enviado.
    """
    usage = execution.usage
    return {
        "provider": execution.provider.value,
        "model_id": execution.model_id,
        "prompt_version": execution.prompt.prompt_version,
        "input_digest": execution.input_digest,
        "latency_ms": execution.latency_ms,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "estimated_cost_usd": (
            None if usage.estimated_cost_usd is None else str(usage.estimated_cost_usd)
        ),
    }


def _refinement_payload(
    executions: Sequence[ProviderExecution], lineage: SuggestionRefinement
) -> dict[str, object]:
    """Lineage e custo do ESTÁGIO de refino, somando os lotes que ele precisou pagar.

    `calls` existe para que uma prancha que custou quatro chamadas não seja lida como se
    tivesse custado uma; tokens, custo e latência são os TOTAIS. `input_digest` é o do
    payload inteiro, o mesmo que o artefato gravou — com um lote só ele coincide com o
    `input_digest` da chamada, como sempre coincidiu.
    """
    costs = [
        execution.usage.estimated_cost_usd
        for execution in executions
        if execution.usage.estimated_cost_usd is not None
    ]
    return {
        "provider": executions[0].provider.value,
        "model_id": executions[0].model_id,
        "prompt_version": executions[0].prompt.prompt_version,
        "input_digest": lineage.input_digest,
        "calls": len(executions),
        "latency_ms": sum(execution.latency_ms for execution in executions),
        "input_tokens": _usage_total(executions, "input_tokens"),
        "output_tokens": _usage_total(executions, "output_tokens"),
        "estimated_cost_usd": str(sum(costs, Decimal(0))) if costs else None,
    }


def _usage_total(executions: Sequence[ProviderExecution], field: str) -> int | None:
    """Soma um contador de uso entre chamadas; `None` quando nenhuma delas o declarou."""
    known = [
        value for execution in executions if (value := getattr(execution.usage, field)) is not None
    ]
    return sum(known) if known else None


def _embeddings_payload(execution: EmbeddingsExecution | None) -> dict[str, object]:
    """Lineage da via de embeddings; vazio quando o cache respondeu tudo e nada foi pago.

    Não há `prompt_version` aqui de propósito: embedding não tem prompt, e o que identifica
    a chamada é `{model_id, input_count, input_digest}`.
    """
    if execution is None:
        return {}
    return {
        "provider": execution.provider.value,
        "embeddings_model_id": execution.model_id,
        "input_count": execution.input_count,
        "input_digest": execution.input_digest,
        "latency_ms": execution.latency_ms,
        "input_tokens": execution.usage.input_tokens,
        "estimated_cost_usd": (
            None
            if execution.usage.estimated_cost_usd is None
            else str(execution.usage.estimated_cost_usd)
        ),
    }


def _command_suggest_codes(args: argparse.Namespace) -> int:
    try:
        result = run_suggest_codes(
            Path(args.packet),
            _catalog_paths(args),
            None if args.contract is None else Path(args.contract),
            Path(args.output),
            refine_arm=args.refine_arm,
            semantic=not args.no_semantic,
        )
    except (ValuationValidationError, ValidationError) as error:
        _print(_refused_payload(error))
        return 2
    except ProviderExecutionError as error:
        _print(_provider_refusal(error))
        return 2
    payload: dict[str, object] = {
        "status": "ok",
        "plate_id": result.suggestions.plate_id,
        "suggester_version": result.suggestions.suggester_version,
        "matching": result.matching,
        "suggestions": len(result.suggestions.suggestions),
        "unmatched": len(result.suggestions.unmatched_item_ids),
        "output": str(result.suggestions_path),
    }
    if result.semantic_reason is not None:
        payload["semantic_reason"] = result.semantic_reason
    if result.matching == "hybrid":
        semantic = result.suggestions.semantic
        payload["semantic"] = {
            "model_id": None if semantic is None else semantic.model_id,
            "embedded_queries": result.embedded_queries,
            **_embeddings_payload(result.embeddings_execution),
        }
    lineage = result.suggestions.refinement
    if result.refinement_executions and lineage is not None:
        payload["refinement"] = {
            "arm": args.refine_arm,
            **_refinement_payload(result.refinement_executions, lineage),
        }
    _print(payload)
    return 0


def _command_index_catalog(args: argparse.Namespace) -> int:
    try:
        result = run_index_catalog(Path(args.catalog), _index_output_dir(args))
    except (ValuationValidationError, ValidationError) as error:
        _print(_refused_payload(error))
        return 2
    except ProviderExecutionError as error:
        _print(_provider_refusal(error))
        return 2
    payload: dict[str, object] = {
        "status": result.status,
        "model_id": result.model_id,
        "items": result.item_count,
        "dims": result.dims,
        "output": str(result.index_path),
    }
    if result.build is not None:
        payload["batches"] = result.build.batch_count
        payload["input_tokens"] = result.build.input_tokens
        payload["estimated_cost_usd"] = result.build.estimated_cost_usd
        payload["latency_ms"] = result.build.latency_ms
    _print(payload)
    return 0


def _index_output_dir(args: argparse.Namespace) -> Path:
    """Onde o índice é gravado: `--output` quando informado, senão ao lado do catálogo.

    O padrão existe porque o índice pertence ao catálogo que o originou — separá-los é o
    caminho mais curto para carregar um índice velho num catálogo novo (o que a carga
    recusa, mas depois de o operador já ter perdido tempo)."""
    if args.output is not None:
        return Path(args.output)
    return Path(args.catalog).expanduser().resolve().parent


def _command_extract_legend_real(args: argparse.Namespace) -> int:
    try:
        result = run_extract_legend_real(
            Path(args.image),
            Path(args.manifest),
            Path(args.output),
            arm_spec=args.arm,
            plate_id=args.plate_id,
            page_number=args.page_number,
            reserve_arm_spec=args.reserve_arm,
        )
    except (ValuationValidationError, ValidationError) as error:
        _print(_refused_payload(error))
        return 2
    except ExtractionNotAllowlistedError as error:
        _print({"refused": "EXTRACTION_NOT_ALLOWLISTED", "message": str(error)})
        return 2
    except ProviderExecutionError as error:
        _print(_provider_refusal(error))
        return 2
    _print(
        {
            "plate_id": result.packet.plate_id,
            "page_number": result.packet.page_number,
            "image": str(args.image),
            "image_sha256": result.packet.image_sha256,
            "source_sha256": result.source_sha256,
            "packet": str(result.packet_path),
            "overlay": str(result.overlay_path),
            "extractor": result.packet.items[0].extractor,
            "extractor_version": result.packet.items[0].extractor_version,
            "review_status": _review_status(result.packet),
            **_takeoff_counts(result.packet),
            "extraction": _execution_payload(result.execution),
        }
    )
    return 0


def _extraction_eval_payload(
    report: ValuationExtractionEvalReport, report_path: Path
) -> dict[str, object]:
    return {
        "plate_id": report.plate_id,
        "arms": [
            {
                "name": arm.name,
                "provider": arm.provider,
                "model_id": arm.model_id,
                "items": arm.item_count,
                "legend_recall": arm.legend_recall,
                "quantity_accuracy": arm.quantity_accuracy,
                "sco_top1": arm.sco_top1,
                "sco_top3": arm.sco_top3,
                "lexical_sco_top1": arm.lexical_sco_top1,
                "lexical_sco_top3": arm.lexical_sco_top3,
                "estimated_cost_usd": arm.estimated_cost_usd,
            }
            for arm in report.arms
        ],
        "checks": report.checks,
        "passed": report.passed,
        "report": str(report_path),
    }


def _command_extraction_eval(args: argparse.Namespace) -> int:
    try:
        report, report_path = run_valuation_extraction_eval(Path(args.output), args.arm)
    except (ValuationValidationError, ValidationError) as error:
        _print(_refused_payload(error))
        return 2
    except ValueError as error:
        # `build_extraction_arm` recusa braço real sem teto de gasto ou sem credencial.
        _print({"refused": "REFINE_ARM_UNAVAILABLE", "message": str(error)})
        return 2
    except ProviderExecutionError as error:
        _print(_provider_refusal(error))
        return 2
    _print(_extraction_eval_payload(report, report_path))
    return 0 if report.passed else 1


def _catalog_paths(args: argparse.Namespace) -> tuple[Path, ...]:
    """`--catalog` repetível: a ordem digitada é a ordem da cascata, e nunca é reordenada."""
    return tuple(Path(value) for value in args.catalog)


def _command_confirm_codes(args: argparse.Namespace) -> int:
    try:
        result = run_confirm_codes(
            Path(args.packet),
            Path(args.decisions),
            _catalog_paths(args),
            None if args.contract is None else Path(args.contract),
            None if args.previous is None else Path(args.previous),
            Path(args.output),
        )
    except (ValuationValidationError, ValidationError) as error:
        _print(_refused_payload(error))
        return 2
    assignments = result.assignments.assignments
    _print(
        {
            "status": "ok",
            "plate_id": result.assignments.plate_id,
            "confirmed": sum(1 for item in assignments if item.status == "confirmed"),
            "rejected": sum(1 for item in assignments if item.status == "rejected"),
            # `confirmed` conta PARES e `closed` conta ELEMENTOS com o pacote completo: sob
            # a cardinalidade N:N os dois números divergem, e é `closed` que diz quanto do
            # trabalho acabou.
            "closed": len(result.assignments.closed_item_ids()),
            "output": str(result.assignments_path),
        }
    )
    return 0


def _command_build_calc(args: argparse.Namespace) -> int:
    try:
        result = run_build_calc(
            Path(args.packet),
            Path(args.assignments),
            Path(args.catalog),
            Path(args.output),
            worksite_key=args.worksite_key,
            worksite_name=args.worksite_name,
            period_number=args.period_number,
            reference_label=args.reference_label,
            address=args.address,
            contract_label=args.contract_label,
            calc_plan_path=None if args.calc_plan is None else Path(args.calc_plan),
            calc_matrix_path=None if args.calc_matrix is None else Path(args.calc_matrix),
        )
    except (ValuationValidationError, ValidationError) as error:
        _print(_refused_payload(error))
        return 2
    bulletin = result.valuation.bulletins[0]
    _print(
        {
            "status": "ok",
            "worksite_key": bulletin.worksite_key,
            "period_number": result.valuation.period_number,
            "lines": len(bulletin.lines),
            "excluded": list(result.excluded_item_ids),
            "total_amount": str(result.valuation.total_amount),
            "output": str(result.valuation_path),
        }
    )
    return 0


def _command_build_amendment_dossier(args: argparse.Namespace) -> int:
    try:
        result = run_build_amendment_dossier(
            Path(args.packet),
            Path(args.assignments),
            Path(args.output),
        )
    except (ValuationValidationError, ValidationError) as error:
        _print(_refused_payload(error))
        return 2
    _print(
        {
            "status": "ok",
            "items": len(result.dossier.items),
            "output": str(result.dossier_path),
        }
    )
    return 0


def _estimate_payload(estimate: Estimate) -> dict[str, object]:
    """Resumo do orçamento publicado: quanto, de onde e o que ficou sem preço."""
    by_origin: dict[str, int] = {}
    for line in estimate.lines:
        by_origin[line.price_origin.value] = by_origin.get(line.price_origin.value, 0) + 1
    return {
        "worksite_key": estimate.worksite_key,
        "lines": len(estimate.lines),
        "lines_by_origin": dict(sorted(by_origin.items())),
        "cascade": [source.origin.value for source in estimate.cascade],
        "unpriced": list(estimate.unpriced_item_ids),
        "bdi_percent": str(estimate.bdi_percent),
        "total_amount_without_bdi": str(estimate.total_amount_without_bdi),
        "total_amount": str(estimate.total_amount),
    }


def _command_build_estimate(args: argparse.Namespace) -> int:
    try:
        result = run_build_estimate(
            Path(args.packet),
            Path(args.assignments),
            _catalog_paths(args),
            Path(args.output),
            worksite_key=args.worksite_key,
            worksite_name=args.worksite_name,
            bdi_percent=args.bdi,
            address=args.address,
            calc_plan_path=None if args.calc_plan is None else Path(args.calc_plan),
            calc_matrix_path=None if args.calc_matrix is None else Path(args.calc_matrix),
        )
    except (ValuationValidationError, ValidationError) as error:
        _print(_refused_payload(error))
        return 2
    _print(
        {
            "status": "ok",
            **_estimate_payload(result.estimate),
            "output": str(result.estimate_path),
        }
    )
    return 0


def _command_estimate_demo(args: argparse.Namespace) -> int:
    try:
        result = run_estimate_demo(Path(args.output))
    except (ValuationValidationError, ValidationError) as error:
        _print(_refused_payload(error))
        return 2
    if result.workbook_path is None:
        _print(
            _estimate_audit_failure_payload(
                Path(args.output) / ESTIMATE_WORKBOOK_FILENAME, result.workbook_audit
            )
        )
        return 1
    _print(
        {
            "status": "ok",
            "plate_id": result.packet.plate_id,
            "catalogs": [str(path) for path in result.catalog_paths],
            "compositions": str(result.compositions_path),
            "suggestions": str(result.suggestions_path),
            "assignments": str(result.assignments_path),
            **_estimate_payload(result.estimate),
            "output": str(result.estimate_path),
            "workbook": str(result.workbook_path),
            "workbook_sha256": result.workbook_audit.workbook_sha256,
            "workbook_audit": str(result.workbook_audit_path),
        }
    )
    return 0


def _command_serve(args: argparse.Namespace) -> int:
    """Sobe o servidor LOCAL de homologação sobre um diretório de rodada (ADR-0020).

    O import é tardio de propósito: `local_server` lê deste módulo os nomes padrão dos
    artefatos, então importá-lo no topo fecharia um ciclo — e nenhum outro comando precisa
    pagar o custo de carregar o stack HTTP.

    Houve um segundo modo neste comando, hospedado e autenticado (ADR-0026), removido com a
    migração da medição para a API `/v1` (ADR-0028): identidade por token é a sessão da API,
    não uma flag deste comando.

    O banner declara duas condições que só se descobrem no start e que a tela não tem como
    adivinhar depois: se a rodada tem catálogo de preços e se a extração automática está
    disponível. É o momento em que o operador ainda pode corrigir as duas com uma flag ou
    uma variável de ambiente.
    """
    from croquito_worker.valuation.local_server import (
        LOCAL_WEB_ORIGINS,
        catalog_source,
        create_local_app,
        extraction_banner_note,
        install_round_catalog,
        install_round_catalog_index,
        run_local_server,
    )

    root = Path(args.root)
    try:
        application = create_local_app(root, args.reviewer)
        identity: dict[str, object] = {"identity": "--reviewer", "reviewer_id": args.reviewer}
        origins = list(LOCAL_WEB_ORIGINS)
        resolved_root = root.expanduser().resolve()
        source = catalog_source(args.catalog)
        catalog_note = install_round_catalog(resolved_root, source)
        catalog_index_note = install_round_catalog_index(resolved_root, source)
    except (ValuationValidationError, ValidationError) as error:
        _print(_refused_payload(error))
        return 2
    # O aviso é sobre expor uma porta SEM autenticação, que é o que este servidor é.
    if args.host != LOCAL_SERVER_DEFAULT_HOST:
        _print(
            {
                "warning": "LOCAL_SERVER_EXPOSED",
                "message": (
                    "ferramenta local SEM autenticação exposta fora de 127.0.0.1; qualquer "
                    "um que alcance esta porta decide como o revisor informado"
                ),
                "host": args.host,
                "reviewer_id": args.reviewer,
            }
        )
    _print(
        {
            "status": "serving",
            "mode": "local",
            "root": str(resolved_root),
            **identity,
            "url": f"http://{args.host}:{args.port}",
            "web_origins": origins,
            "catalog": catalog_note,
            "catalog_index": catalog_index_note,
            "extracao": extraction_banner_note(),
        }
    )
    # Único comando que não termina: sem o flush, o aviso e a URL ficariam presos no
    # buffer de stdout enquanto o servidor roda.
    sys.stdout.flush()
    run_local_server(application, host=args.host, port=args.port)
    return 0


def _command_takeoff_eval(args: argparse.Namespace) -> int:
    report, report_path = run_takeoff_eval(Path(args.output))
    _print(
        {
            "plate_id": report.plate_id,
            "extractor": report.extractor,
            "extractor_version": report.extractor_version,
            "item_count": report.item_count,
            "legend_recall": report.legend_recall,
            "checks": report.checks,
            "passed": report.passed,
            "report": str(report_path),
        }
    )
    return 0 if report.passed else 1


def _bdi_percent_type(raw: str) -> Decimal:
    """`Decimal` do `--bdi`; texto ilegível recusa com mensagem amigável de argparse.

    Espelho de `estimate_rounds.parse_bdi_percent` do lado da API: aqui só o que é
    ILEGÍVEL como decimal vira erro de linha de comando — `argparse.ArgumentTypeError`
    termina o comando com mensagem amigável, sem traceback cru de
    `decimal.InvalidOperation`. A semântica aceita não muda: `>= 0` continua sendo
    recusado adiante pelo domínio.
    """
    try:
        return Decimal(raw)
    except InvalidOperation as error:
        raise argparse.ArgumentTypeError(
            f"'{raw}' não é um número decimal exato; escreva o BDI como 25.00"
        ) from error


def _add_template_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--template",
        type=Path,
        default=None,
        help="JSON de WorkbookTemplate; sem ele vale o layout sintético padrão",
    )


def _add_catalog_option(parser: argparse.ArgumentParser) -> None:
    """`--catalog` repetível: um catálogo é a medição; vários são a cascata do orçamento.

    A ORDEM digitada é a cascata (`ADR-0027`), e é por isso que a opção é `append` em vez
    de uma lista com ordenação própria: o comando não reordena o que o orçamentista
    declarou.
    """
    parser.add_argument(
        "--catalog",
        type=Path,
        action="append",
        required=True,
        metavar="CATALOG",
        help=(
            "catalog.json da fonte de preço; repetível para a cascata do orçamento-base "
            "(a ordem digitada é a ordem das fontes). Com um só, é a cadeia da medição"
        ),
    )


def build_parser() -> argparse.ArgumentParser:
    """Parser dos comandos da cadeia de medição e das ferramentas fora dela.

    Na ordem da cadeia: importação do MAPÃO anterior, takeoff da prancha, sugestão e
    confirmação de código, boletim e memória, exportação auditada. Fora da cadeia ficam a
    demonstração determinística, a paridade local e o gate do takeoff.
    """
    parser = argparse.ArgumentParser(prog="croquito-valuation")
    subcommands = parser.add_subparsers(dest="command", required=True)

    import_workbook = subcommands.add_parser(
        "import-workbook",
        help="importa catálogo e consolidado contratual do MAPÃO, sem escrever no original",
    )
    import_workbook.add_argument("--input", type=Path, required=True)
    import_workbook.add_argument("--output", type=Path, required=True)
    _add_template_option(import_workbook)
    import_workbook.add_argument(
        "--source-label",
        default=SYNTHETIC_CONTRACT_SOURCE_LABEL,
        help="rótulo do arquivo de origem; o padrão descreve a fixture sintética",
    )
    import_workbook.add_argument(
        "--reference-month",
        default=SYNTHETIC_REFERENCE_MONTH,
        help="mês de referência do catálogo importado, no formato AAAA-MM",
    )
    import_workbook.add_argument(
        "--contract-label",
        default=SYNTHETIC_CONTRACT_LABEL,
        help="rótulo do contrato ao qual o consolidado pertence",
    )

    import_catalog = subcommands.add_parser(
        "import-catalog",
        help=(
            "importa só o catálogo de preços do MAPÃO, sem tocar no consolidado nem no "
            "portão semântico dele"
        ),
        description=(
            "Lê SÓ a aba de catálogo e publica SÓ catalog.json + catalog-import-report.json. "
            "Nunca abre a PLANILHA GERAL nem a aba de RE-RA, então nunca vê nem contorna o "
            "portão semântico do consolidado (CONTRACT_SEMANTICS_DIVERGENT). O relatório "
            'declara `consolidado: "not_imported"`: medição real exportável continua '
            "exigindo `import-workbook` completo."
        ),
    )
    import_catalog.add_argument("--input", type=Path, required=True)
    import_catalog.add_argument("--output", type=Path, required=True)
    _add_template_option(import_catalog)
    import_catalog.add_argument(
        "--source-label",
        default=SYNTHETIC_CONTRACT_SOURCE_LABEL,
        help="rótulo do arquivo de origem; o padrão descreve a fixture sintética",
    )
    import_catalog.add_argument(
        "--reference-month",
        default=SYNTHETIC_REFERENCE_MONTH,
        help="mês de referência do catálogo importado, no formato AAAA-MM",
    )

    import_emop = subcommands.add_parser(
        "import-emop",
        help="importa o catálogo EMOP (.DBF) offline; origin=emop nunca entra na medição",
        description=(
            "Lê uma tabela .DBF (dBASE III) do catálogo EMOP a partir de um layout "
            "declarado (--layout, obrigatório: o catálogo digital EMOP é pago e não "
            "existe layout default real neste repositório). Publica SÓ catalog.json "
            "(origin=emop) + emop-import-report.json. O guardrail "
            "BULLETIN_PRICE_ORIGIN_FORBIDDEN recusa este catálogo em "
            "build-calc/export-valuation: a cadeia SCO -> EMOP -> composição vale só "
            "pré-licitação (fase futura)."
        ),
    )
    import_emop.add_argument("--input", type=Path, required=True)
    import_emop.add_argument("--layout", type=Path, required=True)
    import_emop.add_argument("--output", type=Path, required=True)

    import_sinapi = subcommands.add_parser(
        "import-sinapi",
        help="importa o catálogo SINAPI (.xlsx) offline; origin=sinapi nunca entra na medição",
        description=(
            "Lê uma planilha .xlsx da tabela SINAPI a partir de um layout declarado "
            "(--layout, obrigatório: nenhum layout default real existe neste "
            "repositório). Publica SÓ catalog.json (origin=sinapi) + "
            "sinapi-import-report.json. O guardrail BULLETIN_PRICE_ORIGIN_FORBIDDEN "
            "recusa este catálogo em build-calc/export-valuation: a cadeia SCO -> EMOP -> "
            "SINAPI -> SICRO -> composição vale só pré-licitação (fase futura)."
        ),
    )
    import_sinapi.add_argument("--input", type=Path, required=True)
    import_sinapi.add_argument("--layout", type=Path, required=True)
    import_sinapi.add_argument("--output", type=Path, required=True)

    import_sicro = subcommands.add_parser(
        "import-sicro",
        help="importa o catálogo SICRO (.xlsx) offline; origin=sicro nunca entra na medição",
        description=(
            "Lê uma planilha .xlsx da tabela SICRO a partir de um layout declarado "
            "(--layout, obrigatório: nenhum layout default real existe neste "
            "repositório). Publica SÓ catalog.json (origin=sicro) + "
            "sicro-import-report.json. O guardrail BULLETIN_PRICE_ORIGIN_FORBIDDEN "
            "recusa este catálogo em build-calc/export-valuation: a cadeia SCO -> EMOP -> "
            "SINAPI -> SICRO -> composição vale só pré-licitação (fase futura)."
        ),
    )
    import_sicro.add_argument("--input", type=Path, required=True)
    import_sicro.add_argument("--layout", type=Path, required=True)
    import_sicro.add_argument("--output", type=Path, required=True)

    import_compositions = subcommands.add_parser(
        "import-compositions",
        help="compila composições manuais em catálogo origin=composition; nunca entra na medição",
        description=(
            "Lê um CompositionSet (JSON canônico: linhas de mão de obra, insumo e "
            "equipamento com coeficiente) e publica SÓ catalog.json (origin=composition) + "
            "compositions-import-report.json. O preço unitário de cada composição é "
            "recomputado — soma truncada linha a linha — e divergência recusa "
            "(COMPOSITION_TOTAL_MISMATCH) sem publicar nada. O guardrail "
            "BULLETIN_PRICE_ORIGIN_FORBIDDEN recusa este catálogo em "
            "build-calc/export-valuation: composição vale só pré-licitação."
        ),
    )
    import_compositions.add_argument("--input", type=Path, required=True)
    import_compositions.add_argument("--output", type=Path, required=True)

    export_valuation = subcommands.add_parser(
        "export-valuation",
        help="exporta a medição aprovada em pasta auditada; recusa fechada não publica",
    )
    export_valuation.add_argument("--valuation", type=Path, required=True)
    export_valuation.add_argument("--contract", type=Path, required=True)
    export_valuation.add_argument("--catalog", type=Path, required=True)
    export_valuation.add_argument("--output", type=Path, required=True)
    _add_template_option(export_valuation)

    demo = subcommands.add_parser(
        "demo",
        help="percorre a cadeia sintética completa: MAPÃO anterior, medição e auditoria",
    )
    demo.add_argument("--output", type=Path, required=True)

    parity = subcommands.add_parser(
        "parity",
        help="diagnóstico local: confere fórmula contra valor em cache de uma pasta externa",
    )
    parity.add_argument("--previous", type=Path, required=True)
    parity.add_argument("--output", type=Path, required=True)
    _add_template_option(parity)

    compare_bulletin_command = subcommands.add_parser(
        "compare-bulletin",
        help="diagnóstico local: compara o BM gerado (JSON) com o BM real do cliente",
        description=(
            "Ferramenta LOCAL de diagnóstico, fora do CI, da mesma família do `parity`: "
            "não recusa nem publica nada, só relata. Lê o boletim gerado do "
            "`valuation.json` (a fonte de verdade; o xlsx gerado já é provado idêntico a "
            "ele pela auditoria de round-trip) e o BM real do cliente com valores em "
            "cache (`data_only=True`), e compara centavo a centavo por código, sem "
            "tolerância. Nunca escreve no arquivo do cliente."
        ),
    )
    compare_bulletin_command.add_argument("--valuation", type=Path, required=True)
    compare_bulletin_command.add_argument("--worksite", required=True)
    compare_bulletin_command.add_argument("--reference", type=Path, required=True)
    compare_bulletin_command.add_argument(
        "--sheet", required=True, help="nome da aba do BM na planilha real do cliente"
    )
    compare_bulletin_command.add_argument("--output", type=Path, required=True)
    _add_template_option(compare_bulletin_command)

    extract_legend = subcommands.add_parser(
        "extract-legend",
        help="gera a prancha sintética e extrai a legenda quantificada dela",
        description=(
            "Neste marco a única extração que existe é a fixture sintética, então o "
            "comando gera a prancha e extrai dela no mesmo passo. Não existe --input de "
            "propósito: aceitar prancha arbitrária seria fabricar observação sobre "
            "documento real. A extração de prancha de cliente é marco futuro, com "
            "provider, entitlement contratual e teto de gasto."
        ),
    )
    extract_legend.add_argument("--output", type=Path, required=True)

    review_takeoff = subcommands.add_parser(
        "review-takeoff",
        help="aplica decisões do orçamentista sobre o pacote de takeoff",
    )
    review_takeoff.add_argument("--packet", type=Path, required=True)
    review_takeoff.add_argument("--decisions", type=Path, required=True)
    review_takeoff.add_argument("--output", type=Path, required=True)
    review_takeoff.add_argument(
        "--image",
        type=Path,
        default=None,
        help="render da prancha; com ele o overlay é regravado, conferindo o digest",
    )

    register_takeoff = subcommands.add_parser(
        "register-takeoff",
        help="reassenta os bboxes de um pacote de takeoff já extraído contra a tinta",
        description=(
            "Espelho do `register-extraction` da geometria, para a legenda: reprocessa "
            "um pacote de takeoff já publicado, sem nova chamada paga, corrigindo o "
            "assentamento do bbox de cada item contra a tinta da prancha — nunca o "
            "conteúdo lido. Pacote com algum item já decidido pelo orçamentista é "
            "recusado (REGISTRATION_AFTER_DECISION): mover a âncora de evidência depois "
            "de uma decisão reescreveria o que o revisor viu. Publica o pacote "
            "reassentado, o overlay re-renderizado e o relatório do ajuste. Com "
            "--restore-raw, restaura o pacote pro bruto (before do relatório de uma "
            "rodada anterior) antes de registrar de novo."
        ),
    )
    register_takeoff.add_argument("--packet", type=Path, required=True)
    register_takeoff.add_argument("--image", type=Path, required=True)
    register_takeoff.add_argument("--output", type=Path, required=True)
    register_takeoff.add_argument(
        "--restore-raw",
        action="store_true",
        help=(
            "restaura o pacote pro bruto (os `before` do takeoff-registration.json ao "
            "lado de --packet) antes de registrar de novo — reprocessa do zero com um "
            "pipeline mais novo, sem nova chamada paga"
        ),
    )

    takeoff_demo = subcommands.add_parser(
        "takeoff-demo",
        help="percorre a cadeia do takeoff: prancha sintética, extração e revisão",
    )
    takeoff_demo.add_argument("--output", type=Path, required=True)

    suggest_codes_command = subcommands.add_parser(
        "suggest-codes",
        help="sugere códigos do catálogo para os itens confirmados; observação, não decisão",
    )
    suggest_codes_command.add_argument("--packet", type=Path, required=True)
    _add_catalog_option(suggest_codes_command)
    suggest_codes_command.add_argument(
        "--contract",
        type=Path,
        default=None,
        help="consolidado contratual; com ele o candidato contratado sobe na ordem",
    )
    suggest_codes_command.add_argument("--output", type=Path, required=True)
    suggest_codes_command.add_argument(
        "--refine-arm",
        default=None,
        metavar="NOME=PROVIDER:MODELO",
        help=(
            "braço pago que REORDENA a shortlist lexical, ex.: "
            "sonnet=anthropic:claude-sonnet-5. Exige teto de gasto; provider fixture é "
            "recusado. Sem a flag, a shortlist é a lexical determinística"
        ),
    )
    suggest_codes_command.add_argument(
        "--no-semantic",
        action="store_true",
        help=(
            "desliga a perna semântica mesmo com índice de embeddings na rodada; a "
            "shortlist continua sendo montada pela mesma via, só com o braço léxico. Sem "
            "a flag, o braço semântico entra quando existirem índice, teto de gasto e "
            "credencial; faltando qualquer um, a shortlist sai léxica com o motivo "
            "declarado no relatório"
        ),
    )

    index_catalog = subcommands.add_parser(
        "index-catalog",
        help="constrói o índice de embeddings do catálogo; comando PAGO, uma vez por catálogo",
        description=(
            "Comando PAGO: envia o texto de cada item do catálogo (código, descrição e "
            "unidade) para o provider de embeddings, em lotes. Exige teto de gasto em "
            "CROQUITO_AI_MAX_ESTIMATED_COST_USD e CROQUITO_OPENAI_API_KEY. O índice "
            "fica amarrado ao digest do catálogo e é gravado ao lado dele por padrão; "
            "índice já existente para o MESMO catálogo é reusado sem nenhuma chamada."
        ),
    )
    index_catalog.add_argument("--catalog", type=Path, required=True)
    index_catalog.add_argument(
        "--output",
        type=Path,
        default=None,
        help="diretório do índice; sem ele, o mesmo diretório do catálogo",
    )

    confirm_codes_command = subcommands.add_parser(
        "confirm-codes",
        help="registra a confirmação de código do orçamentista; recusa fechada não publica",
    )
    confirm_codes_command.add_argument("--packet", type=Path, required=True)
    confirm_codes_command.add_argument("--decisions", type=Path, required=True)
    _add_catalog_option(confirm_codes_command)
    confirm_codes_command.add_argument(
        "--contract",
        type=Path,
        default=None,
        help="consolidado contratual; com ele o código fora do contrato é recusado",
    )
    confirm_codes_command.add_argument(
        "--previous",
        type=Path,
        default=None,
        help="confirmações anteriores; re-decisão sobre item já decidido é recusada",
    )
    confirm_codes_command.add_argument("--output", type=Path, required=True)

    build_calc_command = subcommands.add_parser(
        "build-calc",
        help="monta boletim e memória da obra a partir do takeoff confirmado, sem aprovação",
    )
    build_calc_command.add_argument("--packet", type=Path, required=True)
    build_calc_command.add_argument("--assignments", type=Path, required=True)
    build_calc_command.add_argument("--catalog", type=Path, required=True)
    build_calc_command.add_argument("--worksite-key", required=True)
    build_calc_command.add_argument("--worksite-name", required=True)
    build_calc_command.add_argument("--period-number", type=int, required=True)
    build_calc_command.add_argument("--reference-label", required=True)
    build_calc_command.add_argument("--address", default=None)
    build_calc_command.add_argument("--contract-label", default=None)
    build_calc_command.add_argument(
        "--calc-plan",
        type=Path,
        default=None,
        help="plano de memória por item; sem ele cada item recebe quantidade direta",
    )
    build_calc_command.add_argument(
        "--calc-matrix",
        type=Path,
        default=None,
        help=(
            "matriz de contribuições por serviço (ADR-0053); funde por código e resolve "
            "dependência. Mutuamente exclusiva com --calc-plan"
        ),
    )
    build_calc_command.add_argument("--output", type=Path, required=True)

    build_estimate_command = subcommands.add_parser(
        "build-estimate",
        help="monta o orçamento-base da obra sobre a cascata de fontes; PRÉ-licitação",
        description=(
            "Irmão do `build-calc` do outro lado da fronteira do ADR-0027: monta o "
            "orçamento-base de PRÉ-licitação, com proveniência por linha (origem, catálogo "
            "e data-base) e a lista declarada de itens que nenhuma fonte precificou. A "
            "ordem dos --catalog é a cascata; duas fontes da mesma origem recusam. Sem "
            "contrato, sem saldo, sem período e sem aprovação — nada disso existe antes da "
            "licitação, e o estimate.json publicado NÃO é medição."
        ),
    )
    build_estimate_command.add_argument("--packet", type=Path, required=True)
    build_estimate_command.add_argument("--assignments", type=Path, required=True)
    _add_catalog_option(build_estimate_command)
    build_estimate_command.add_argument("--worksite-key", required=True)
    build_estimate_command.add_argument("--worksite-name", required=True)
    build_estimate_command.add_argument(
        "--bdi",
        type=_bdi_percent_type,
        required=True,
        help="percentual único de BDI do orçamento (ADR-0038), ex.: 25.00",
    )
    build_estimate_command.add_argument("--address", default=None)
    build_estimate_command.add_argument(
        "--calc-plan",
        type=Path,
        default=None,
        help="plano de memória por item; sem ele cada item recebe quantidade direta",
    )
    build_estimate_command.add_argument(
        "--calc-matrix",
        type=Path,
        default=None,
        help=(
            "matriz de contribuições por serviço (ADR-0053); funde por código e resolve "
            "dependência. Mutuamente exclusiva com --calc-plan"
        ),
    )
    build_estimate_command.add_argument("--output", type=Path, required=True)

    estimate_demo = subcommands.add_parser(
        "estimate-demo",
        help="percorre a cadeia do orçamento-base sintético com as três origens de preço",
        description=(
            "Demonstração determinística da cadeia de PRÉ-licitação: catálogo SCO "
            "sintético, catálogo EMOP sintético (.DBF, pelo importador real) e uma "
            "composição manual compilada formam a cascata; a prancha sintética entra pelo "
            "mesmo caminho do `demo`. O estimate.json publicado tem linha de cada origem e "
            "um item declarado em unpriced_item_ids. Nenhum dado de cliente e nenhuma "
            "chamada paga."
        ),
    )
    estimate_demo.add_argument("--output", type=Path, required=True)

    build_amendment_dossier_command = subcommands.add_parser(
        "build-amendment-dossier",
        help="monta o dossiê do aditivo (RE-RA) a partir das rejeições de código; nunca precifica",
    )
    build_amendment_dossier_command.add_argument("--packet", type=Path, required=True)
    build_amendment_dossier_command.add_argument("--assignments", type=Path, required=True)
    build_amendment_dossier_command.add_argument("--output", type=Path, required=True)

    extract_legend_real = subcommands.add_parser(
        "extract-legend-real",
        help="extrai a legenda de uma prancha real com provider pago; recusa fora do gate",
        description=(
            "Comando PAGO: envia a página para um provider externo. Exige braço "
            "NOME=PROVIDER:MODELO real (fixture é recusado), teto de gasto em "
            "CROQUITO_AI_MAX_ESTIMATED_COST_USD e o documento na allowlist de "
            "CROQUITO_AI_EXTRACTION_ALLOWED_DIGESTS. O manifest é o do comando "
            "`croquito-demo ingest`, e a imagem precisa pertencer a ele. Nenhum item "
            "nasce confirmado: o pacote sai para revisão do orçamentista."
        ),
    )
    extract_legend_real.add_argument("--image", type=Path, required=True)
    extract_legend_real.add_argument("--manifest", type=Path, required=True)
    extract_legend_real.add_argument(
        "--arm",
        required=True,
        metavar="NOME=PROVIDER:MODELO",
        help="braço pago da extração, ex.: sonnet=anthropic:claude-sonnet-5",
    )
    extract_legend_real.add_argument(
        "--reserve-arm",
        default=None,
        metavar="NOME=PROVIDER:MODELO",
        help=(
            "braço de RESERVA, opcional: só é chamado depois de falha permanente do "
            "--arm, e a degradação vai nomeada numa nota de segurança do pacote"
        ),
    )
    extract_legend_real.add_argument("--plate-id", required=True)
    extract_legend_real.add_argument("--page-number", type=int, default=1)
    extract_legend_real.add_argument("--output", type=Path, required=True)

    serve = subcommands.add_parser(
        "serve",
        help="sobe a UI LOCAL de homologação sobre um diretório de rodada",
        description=(
            "Servidor LOCAL de homologação da medição, da família do `parity` (ADR-0020). "
            "Ele embrulha as mesmas funções de domínio dos comandos (`review-takeoff`, "
            "`suggest-codes`, `confirm-codes`, `build-calc`) sobre os artefatos que já "
            "estão em --root, com os nomes padrão. Sem autenticação, bind padrão em "
            "127.0.0.1 e identidade de quem decide vinda de --reviewer — expor em outro "
            "host publica a ferramenta sem autenticação. Homologação com sessão é a API "
            "`/v1` autenticada (ADR-0028), não este comando."
        ),
    )
    serve.add_argument("--root", type=Path, required=True)
    serve.add_argument(
        "--reviewer",
        required=True,
        help="identidade do orçamentista que decide nesta sessão; vai em cada decisão",
    )
    serve.add_argument("--host", default=LOCAL_SERVER_DEFAULT_HOST)
    serve.add_argument("--port", type=int, default=LOCAL_SERVER_DEFAULT_PORT)
    serve.add_argument(
        "--catalog",
        default=None,
        help=(
            "catalog.json a instalar na rodada quando ela ainda não tem um (rodada que "
            "nasceu de upload não passou pelo import-workbook). Alternativa: a variável "
            "CROQUITO_MEDICAO_CATALOG; a flag vence. Catálogo já presente na rodada "
            "nunca é sobrescrito."
        ),
    )

    takeoff_eval = subcommands.add_parser(
        "takeoff-eval",
        help="gate determinístico do takeoff: recall de legenda e contrato do fluxo de revisão",
    )
    takeoff_eval.add_argument("--output", type=Path, required=True)

    extraction_eval = subcommands.add_parser(
        "extraction-eval",
        help="gate da extração paga de legenda e do refino de código; sem --arm roda offline",
        description=(
            "Sem --arm a eval roda o braço fixture embutido: offline, determinística e "
            "sem custo, é o modo do CI. Com --arm (repetível) ela compara braços reais e "
            "a rodada é PAGA, exigindo teto de gasto. O relatório traz, por braço, recall "
            "da legenda, acurácia de quantidade e top-1/top-3 de código do refino ao lado "
            "da baseline lexical."
        ),
    )
    extraction_eval.add_argument("--output", type=Path, required=True)
    extraction_eval.add_argument(
        "--arm",
        action="append",
        default=[],
        metavar="NOME=PROVIDER:MODELO",
        help="braço real a comparar; sem nenhum, roda o braço fixture offline",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "import-workbook":
        return _command_import_workbook(args)
    if args.command == "import-catalog":
        return _command_import_catalog(args)
    if args.command == "import-emop":
        return _command_import_emop(args)
    if args.command == "import-sinapi":
        return _command_import_sinapi(args)
    if args.command == "import-sicro":
        return _command_import_sicro(args)
    if args.command == "import-compositions":
        return _command_import_compositions(args)
    if args.command == "export-valuation":
        return _command_export_valuation(args)
    if args.command == "demo":
        return _command_demo(args)
    if args.command == "parity":
        return _command_parity(args)
    if args.command == "compare-bulletin":
        return _command_compare_bulletin(args)
    if args.command == "extract-legend":
        return _command_extract_legend(args)
    if args.command == "review-takeoff":
        return _command_review_takeoff(args)
    if args.command == "register-takeoff":
        return _command_register_takeoff(args)
    if args.command == "takeoff-demo":
        return _command_takeoff_demo(args)
    if args.command == "suggest-codes":
        return _command_suggest_codes(args)
    if args.command == "index-catalog":
        return _command_index_catalog(args)
    if args.command == "confirm-codes":
        return _command_confirm_codes(args)
    if args.command == "build-calc":
        return _command_build_calc(args)
    if args.command == "build-estimate":
        return _command_build_estimate(args)
    if args.command == "estimate-demo":
        return _command_estimate_demo(args)
    if args.command == "build-amendment-dossier":
        return _command_build_amendment_dossier(args)
    if args.command == "extract-legend-real":
        return _command_extract_legend_real(args)
    if args.command == "serve":
        return _command_serve(args)
    if args.command == "takeoff-eval":
        return _command_takeoff_eval(args)
    if args.command == "extraction-eval":
        return _command_extraction_eval(args)
    return 2
