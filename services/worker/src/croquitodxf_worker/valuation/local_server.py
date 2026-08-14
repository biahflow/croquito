"""Servidor **local** de homologação da medição: HTTP fino sobre o domínio fail-closed.

Ele existe para que o ato do orçamentista — revisar o takeoff, confirmar código, montar o
boletim — aconteça numa tela em vez de num lote de JSON escrito à mão. Nenhuma regra de
negócio nova mora aqui: cada rota carrega os artefatos que o CLI gravou, chama a MESMA
função de domínio que o comando equivalente chama (`apply_takeoff_decisions`,
`build_code_suggestions`, `apply_code_assignments`, `build_worksite_valuation`) e publica
o resultado com os mesmos nomes de arquivo e a mesma escrita atômica. Recusa do domínio
atravessa intacta, com o código estável, e **não** grava artefato — como no CLI.

Limites declarados, não escondidos:

- É ferramenta **local**, da família do `parity`: bind padrão em `127.0.0.1`, CORS restrito
  à UI local e **sem autenticação**. A identidade do revisor vem da flag de inicialização
  (`--reviewer`), não de token: quem sobe o processo declara quem está decidindo. Sessão
  autenticada de verdade é marco futuro, com ADR próprio.
- Chama provider em **uma** operação e só nela: a extração da legenda que o upload da
  prancha dispara (`POST /plates`), por decisão registrada do usuário em 2026-08-13. Os
  freios do CLI continuam todos de pé — teto de gasto obrigatório por variável de ambiente
  do processo (sem teto a extração fica `unavailable` e visível, e **nunca** é tentada),
  braço fixado no vencedor da eval paga, lineage e custo gravados na rodada, falha exibida
  no estado em vez de silêncio. O que muda é a FORMA do consentimento: no CLI ele é a
  allowlist de digests que o operador declara; aqui é o próprio ato de subir o PDF na tela,
  com o digest do arquivo enviado registrado no estado e no `extraction-lineage.json`
  (ver `_authorize_uploaded_page`). Refino pago de código continua fora daqui: é comando
  do CLI.
- O `decided_at` de toda decisão é o relógio do **servidor** e o `decision_id` continua
  derivado no domínio. Os modelos de request recusam `reviewer_id`, `decided_at` e
  `decision_id` no corpo (`extra="forbid"`): identidade e carimbo não são dados de entrada.

Guarda otimista local (substituto declarado do `base_version`): toda resposta que entrega
um artefato mutável leva o sha256 dos bytes do arquivo (`packet_sha256`,
`assignments_sha256`), e toda mutação exige o digest-base correspondente. Divergência
recusa com `LOCAL_STATE_MOVED` (409) e os dois digests em `details`, sem gravar nada. É a
mesma semântica do `REVISION_CONFLICT` da API de cena, com meios locais: a lacuna de
versionamento/pinagem do pacote de takeoff é declarada em
`docs/architecture/VALUATION_CONTEXT.md` ("O id do item de takeoff é determinístico pela
prancha, não pela revisão") e este servidor a cobre **no diretório da rodada** — ele não a
resolve no domínio.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Annotated, Final, Literal

import uvicorn
from fastapi import FastAPI, File, Query, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.requests import Request

from croquitodxf_valuation.assignment import (
    LLM_RERANK_SUFFIX,
    CodeAssignmentBatch,
    CodeAssignmentInput,
    CodeAssignmentSet,
    CodeSuggestionSet,
    apply_code_assignments,
)
from croquitodxf_valuation.calc import CalcPlan, build_worksite_valuation
from croquitodxf_valuation.catalog import (
    DomainSynonyms,
    LegendNoiseList,
    default_legend_noise,
    expand_terms,
    file_sha256,
    lexical_similarity,
    lexical_stems,
    lexical_tokens,
    weighted_query_coverage_score,
)
from croquitodxf_valuation.contract import ContractWorkbook
from croquitodxf_valuation.errors import ValuationValidationError, valuation_errors
from croquitodxf_valuation.models import (
    SHA256_PATTERN,
    PriceCatalog,
    PriceCatalogEntry,
    Valuation,
)
from croquitodxf_valuation.takeoff import (
    TakeoffDecisionBatch,
    TakeoffDecisionInput,
    TakeoffItem,
    TakeoffItemStatus,
    TakeoffPacket,
    apply_takeoff_decisions,
)
from croquitodxf_worker.extraction_eval import (
    ExtractionNotAllowlistedError,
    bind_page_to_document,
)
from croquitodxf_worker.ingest import PdfManifest, ingest_pdf
from croquitodxf_worker.io_utils import atomic_write_bytes, atomic_write_text
from croquitodxf_worker.providers import (
    EmbeddingsAdapter,
    LegendExtractionOutput,
    ProviderAdapter,
    ProviderExecution,
    ProviderExecutionError,
    ProviderFailureCode,
    build_extraction_arm,
)
from croquitodxf_worker.valuation.cli import (
    CALC_PLAN_FILENAME,
    CATALOG_FILENAME,
    CODE_ASSIGNMENTS_FILENAME,
    CODE_SUGGESTIONS_FILENAME,
    CONTRACT_FILENAME,
    TAKEOFF_OVERLAY_FILENAME,
    TAKEOFF_PACKET_FILENAME,
    TAKEOFF_REGISTRATION_REPORT_FILENAME,
    VALUATION_FILENAME,
    load_round_synonyms,
)
from croquitodxf_worker.valuation.legend_extraction import (
    LegendExtractionResult,
    build_legend_request,
    extractor_label,
    takeoff_packet_from_legend,
)
from croquitodxf_worker.valuation.legend_registration import (
    LegendRegistrationReport,
    register_legend_bboxes,
)
from croquitodxf_worker.valuation.plate import PLATE_IMAGE_FILENAME
from croquitodxf_worker.valuation.sco_matching import (
    CATALOG_INDEX_FILENAME,
    QUERY_CACHE_FILENAME,
    SEMANTIC_DEGRADABLE_CODES,
    SemanticIndex,
    bind_index_to_catalog,
    build_hybrid_code_suggestions,
    catalog_idf_table,
    embeddings_adapter_or_reason,
    fuse_arms,
    load_semantic_index,
    normalize_query_text,
    read_catalog_index,
    resolve_query_vectors,
    semantic_topk,
)
from croquitodxf_worker.valuation.sco_suggestion import build_code_suggestions
from croquitodxf_worker.valuation.takeoff_overlay import (
    render_takeoff_overlay,
    save_takeoff_overlay,
)

LOCAL_SERVER_VERSION: Final = "local-valuation-server-v1"

LOCAL_WEB_ORIGINS: Final[tuple[str, ...]] = (
    "http://localhost:5174",
    "http://127.0.0.1:5174",
)
"""Origens da UI local de homologação (Fase B). Nada além delas fala com este servidor."""

REVIEWER_ROLE: Final = "orcamentista"
"""Único papel deste contexto; ele não vem do corpo da requisição."""

CATALOG_SEARCH_DEFAULT_LIMIT: Final = 20
CATALOG_SEARCH_MAX_LIMIT: Final = 50

CATALOG_SEARCH_MIN_PREFIX: Final = 4
"""Comprimento mínimo do lado que serve de prefixo no casamento da busca.

Abaixo disso, prefixo vira coincidência: `pis` traria `piscina` para quem procura piso.
Igualdade de palavra continua valendo em qualquer comprimento."""

_OVERLAY_SKIPPED_NOTE: Final = (
    "overlay não regravado: a imagem da prancha do pacote não está no diretório da "
    "rodada; um overlay antigo, se existir, está desatualizado."
)

_NO_STORE: Final = {"Cache-Control": "no-store"}
"""Overlay e prancha mudam a cada decisão; cache de navegador mostraria estado velho."""

PLATE_PDF_FILENAME: Final = "prancha-origem.pdf"
"""PDF do projetista como ele chegou. Artefato local, fora do Git, retenção de 7 dias."""

PLATE_MANIFEST_FILENAME: Final = "manifest.json"
"""Manifest da ingestão: amarra a página promovida ao documento que o revisor enviou."""

EXTRACTION_LINEAGE_FILENAME: Final = "extraction-lineage.json"
"""Lineage local da chamada paga: provider, modelo, prompt, tokens, custo e consentimento."""

MAX_PLATE_PDF_BYTES: Final = 50 * 1024 * 1024
"""Teto do upload. Prancha de projetista real fica bem abaixo; acima disso é engano."""

PLATE_INGEST_DPI: Final = 200
PLATE_INGEST_ROLE: Final = "legenda-quantificada"
PLATE_PAGE_NUMBER: Final = 1
"""Uma rodada é uma prancha, e a prancha é a página 1.

PDF com mais páginas não é recusado nem lido às escondidas: a página 1 é promovida e a
contagem vai declarada no estado, para o orçamentista saber o que ficou de fora."""

MEDICAO_EXTRACTION_ARM: Final = "sonnet=anthropic:claude-sonnet-5"
"""Braço pago da extração automática: o vencedor da eval paga de 2026-08-13.

Ele é constante e não flag de rota justamente porque trocar de modelo é mudança de IA —
exige eval comparativa e plano de rollback (`docs/ai/MODEL_ROUTING.md`). A variável de
ambiente abaixo existe para a próxima rodada de eval, não para escolher modelo por gosto.
"""

EXTRACTION_ARM_ENV: Final = "CROQUITODXF_MEDICAO_EXTRACTION_ARM"
AI_BUDGET_ENV: Final = "CROQUITODXF_AI_MAX_ESTIMATED_COST_USD"

_PROVIDER_CREDENTIAL_ENV: Final[Mapping[str, str]] = {
    "anthropic": "CROQUITODXF_ANTHROPIC_API_KEY",
    "openai": "CROQUITODXF_OPENAI_API_KEY",
}
"""Credencial exigida por provider. O Bedrock fica de fora porque a cadeia do boto3 não é
uma variável só; a ausência dela vira `unavailable` pela recusa da própria fábrica."""

ExtractionStatus = Literal["idle", "running", "done", "failed", "unavailable"]
"""Etapa `extracao` do estado. `unavailable` é servidor sem teto/credencial — nunca
chamou; `failed` é chamada que aconteceu e não fechou. Os dois são visíveis na tela."""

_EXTRACTION_MESSAGES: Final[Mapping[str, str]] = {
    "no_plate": "nenhuma prancha enviada nesta rodada",
    "ingested": "prancha ingerida; a extração automática ainda não foi disparada",
    "running": "extração automática em andamento; chamada paga configurada no servidor",
    "done": "extração concluída; todo item nasce para a revisão do orçamentista",
}

_NO_BUDGET_MESSAGE: Final = (
    "extração automática indisponível: teto de gasto não configurado no servidor"
)
_NO_CREDENTIAL_MESSAGE: Final = (
    "extração automática indisponível: credencial do provider não configurada no servidor"
)
_ARM_MISCONFIGURED_MESSAGE: Final = (
    "extração automática indisponível: braço pago mal configurado no servidor"
)
_FIXTURE_ARM_MESSAGE: Final = (
    "extração automática indisponível: braço fixture não publica pacote de rodada"
)
_ALREADY_HAS_PLATE_MESSAGE: Final = (
    "esta rodada já tem prancha; uma rodada é uma prancha. Para enviar outra, suba o "
    "servidor com `serve --root` apontando para um diretório novo"
)


def _now() -> datetime:
    """Carimbo do servidor. Seam de teste: o relógio nunca vem do cliente."""
    return datetime.now(UTC)


def _document(model: BaseModel) -> str:
    """JSON do modelo no MESMO formato do CLI (`cli._document`): `Decimal` sai como texto.

    O formato precisa ser idêntico byte a byte ao do CLI: os dois escrevem no mesmo
    diretório de rodada, e um artefato gravado aqui é lido lá pelo comando seguinte.
    """
    return model.model_dump_json(indent=2) + "\n"


def _serialize(payload: dict[str, object]) -> str:
    """Relatório em JSON no MESMO formato do CLI (`cli._serialize`), pelo mesmo motivo."""
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _digest_of(document: str) -> str:
    return hashlib.sha256(document.encode("utf-8")).hexdigest()


class LocalServerRefusal(Exception):
    """Recusa do servidor local com status HTTP declarado e erro de domínio dentro.

    O corpo da resposta é sempre o mesmo formato — `code`, `detail`, `details` —, venha o
    erro do domínio (422) ou do próprio servidor (404 de artefato ausente, 409 de guarda
    otimista).
    """

    def __init__(self, status_code: int, error: ValuationValidationError) -> None:
        self.status_code = status_code
        self.error = error
        super().__init__(str(error))


def _artifact_missing(filename: str) -> LocalServerRefusal:
    return LocalServerRefusal(
        404,
        ValuationValidationError(
            "LOCAL_ARTIFACT_MISSING",
            "artefato de entrada ausente no diretório da rodada",
            {"artifact": filename},
        ),
    )


def _state_moved(filename: str, *, base: str, current: str) -> LocalServerRefusal:
    return LocalServerRefusal(
        409,
        ValuationValidationError(
            "LOCAL_STATE_MOVED",
            "o artefato mudou depois da leitura; recarregue antes de decidir de novo",
            {"artifact": filename, "base_sha256": base, "current_sha256": current},
        ),
    )


def _guard(filename: str, *, base: str, current: str) -> None:
    """Guarda otimista: decisão só entra sobre o estado que o cliente realmente leu."""
    if base != current:
        raise _state_moved(filename, base=base, current=current)


def _round_already_has_plate(reason: str) -> LocalServerRefusal:
    """Segunda prancha na mesma rodada: recusa fechada com o caminho da rodada nova.

    Aceitar a segunda sobrescreveria a evidência de decisões já tomadas — e, num diretório
    onde o pacote existe, também custaria outra chamada paga por engano.
    """
    return LocalServerRefusal(
        409,
        ValuationValidationError(
            "LOCAL_ROUND_ALREADY_HAS_PLATE",
            _ALREADY_HAS_PLATE_MESSAGE,
            {"reason": reason},
        ),
    )


def _upload_invalid(reason: str, details: dict[str, object] | None = None) -> LocalServerRefusal:
    """Arquivo que não é prancha: recusado antes de qualquer escrita ou renderização."""
    return LocalServerRefusal(
        422,
        ValuationValidationError(
            "LOCAL_UPLOAD_INVALID",
            "o arquivo enviado não é um PDF de prancha aceitável",
            {"reason": reason, **(details or {})},
        ),
    )


def _extraction_busy() -> LocalServerRefusal:
    """Uma extração paga por vez neste processo — a segunda seria gasto duplicado."""
    return LocalServerRefusal(
        409,
        ValuationValidationError(
            "LOCAL_EXTRACTION_BUSY",
            "já existe uma extração automática em andamento nesta rodada",
            {},
        ),
    )


def _domain_error(error: ValidationError) -> ValuationValidationError:
    """Recupera o erro de domínio embrulhado numa `ValidationError`; espelho de
    `cli._refused_payload`, que faz a mesma tradução para o stdout dos comandos."""
    domain = valuation_errors(error)
    if domain:
        return domain[0]
    return ValuationValidationError(
        "MODEL_VALIDATION_FAILED",
        "o documento não corresponde ao contrato do modelo",
        {
            "errors": [
                {"loc": ".".join(str(part) for part in line["loc"]), "type": line["type"]}
                for line in error.errors()
            ]
        },
    )


def _problem(status_code: int, error: ValuationValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        media_type="application/problem+json",
        content={"code": error.code, "detail": error.message, "details": error.details},
    )


class _LocalRequest(BaseModel):
    """Corpo aceito pelo servidor local.

    `extra="forbid"` é o que impede o cliente de carimbar identidade ou horário: um corpo
    com `reviewer_id`, `reviewer_role`, `decided_at` ou `decision_id` é 422 do Pydantic,
    não um campo silenciosamente ignorado.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class TakeoffDecisionRequest(_LocalRequest):
    """Decisão do orçamentista sobre um item do takeoff.

    `quantity` viaja como texto porque dinheiro e quantidade são `Decimal` exatos neste
    contexto: um `float` de JSON já teria perdido a escala escrita antes de chegar aqui.
    """

    item_id: str
    action: Literal["confirm", "reject"]
    quantity: str | None = None
    unit: str | None = None
    note: str | None = None
    item_note: str | None = None
    base_packet_sha256: str = Field(pattern=SHA256_PATTERN)


class CodeDecisionRequest(_LocalRequest):
    """Confirmação ou rejeição do código SCO de um item já confirmado no takeoff."""

    item_id: str
    action: Literal["confirm", "reject"]
    code: str | None = None
    note: str | None = None
    base_assignments_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)


class SuggestionsRecomputeRequest(_LocalRequest):
    """Pedido de recompute explícito da shortlist de sugestões de código.

    Mesmo protocolo de digest-base de `CodeDecisionRequest`: `None` só é aceito quando a
    rodada ainda não tem `code-suggestions.json` — arquivo existente sem digest citado é
    recusa, como em `POST /codes/decisions`.
    """

    base_suggestions_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)


class CalcBuildRequest(_LocalRequest):
    """Identificação da obra e do período medido; o resto vem dos artefatos da rodada."""

    worksite_key: str
    worksite_name: str
    period_number: int
    reference_label: str
    address: str | None = None
    contract_label: str | None = None


def _parse_quantity(raw_quantity: str | None) -> Decimal | None:
    """`Decimal` da quantidade informada pelo revisor; texto ilegível recusa em vez de virar
    número aproximado."""
    if raw_quantity is None:
        return None
    try:
        return Decimal(raw_quantity)
    except InvalidOperation as error:
        raise ValuationValidationError(
            "LOCAL_QUANTITY_INVALID",
            "quantidade informada não é um número decimal exato",
            {"quantity": raw_quantity},
        ) from error


def _review_status(packet: TakeoffPacket) -> str:
    """Espelho de `cli._review_status`."""
    return "review_required" if packet.pending_items() else "complete"


def _takeoff_counts(packet: TakeoffPacket) -> dict[str, int]:
    """Espelho de `cli._takeoff_counts`: sempre as quatro chaves — zero é informação."""
    counts = {status.value: 0 for status in TakeoffItemStatus}
    for item in packet.items:
        counts[item.status.value] += 1
    return {"items": len(packet.items), **counts, "pending": len(packet.pending_items())}


ANCHOR_REGISTERED: Final = "registered"
ANCHOR_RAW: Final = "raw"

_REGISTERED_METHODS: Final[frozenset[str]] = frozenset({"rulings", "text_bands"})
"""Métodos de registro que sustentam uma âncora declarada confiável.

`none` fica de fora de propósito: é o desfecho em que nenhuma transformação passou no
gate e o que foi assentado veio do casamento residual travado. Ele é honesto no domínio,
mas não é promessa suficiente para desenhar um retângulo em cima da prancha."""


def _registered_item_ids(run: _Run) -> frozenset[str]:
    """Itens cujo bbox foi reassentado por um método de registro confiável.

    Leitura fail-closed: relatório ausente, ilegível, sem `method` declarado ou com
    `method` fora do conjunto confiável devolve conjunto **vazio** — todo item volta como
    `raw`. O motivo é o defeito real da homologação: retângulo desenhado sobre a prancha é
    lido pela revisora como "o número foi lido aqui", e âncora deslizada engana com a
    autoridade de um desenho. Na dúvida, a tela precisa poder dizer que não sabe.
    """
    found = run.read(TAKEOFF_REGISTRATION_REPORT_FILENAME)
    if found is None:
        return frozenset()
    try:
        report = json.loads(found[0])
    except json.JSONDecodeError:
        return frozenset()
    if not isinstance(report, dict) or str(report.get("method", "")) not in _REGISTERED_METHODS:
        return frozenset()
    adjusted = report.get("adjusted")
    if not isinstance(adjusted, list):
        return frozenset()
    return frozenset(
        entry["item_id"]
        for entry in adjusted
        if isinstance(entry, dict) and isinstance(entry.get("item_id"), str)
    )


def _anchored_packet(packet: TakeoffPacket, registered: frozenset[str]) -> dict[str, object]:
    """Pacote como a tela o recebe, com a âncora de cada item declarada ao lado dele.

    A junção é de **leitura**: o `takeoff-packet.json` em disco não ganha campo nenhum e o
    domínio não muda. Por isso `packet_sha256` continua sendo o digest dos bytes do
    arquivo — não desta resposta —, e é ele que a guarda otimista compara na decisão
    seguinte.
    """
    document: dict[str, object] = packet.model_dump(mode="json")
    items = document.get("items")
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                anchored = ANCHOR_REGISTERED if item.get("id") in registered else ANCHOR_RAW
                item["anchor"] = anchored
    return document


def _anchor_counts(packet: TakeoffPacket, registered: frozenset[str]) -> dict[str, int]:
    """Quantos itens a tela pode ancorar com garantia e quantos não — zero é informação."""
    matched = sum(1 for item in packet.items if item.id in registered)
    return {"anchors_registered": matched, "anchors_raw": len(packet.items) - matched}


def _item_payload(item: TakeoffItem) -> dict[str, object]:
    """Item de takeoff como a tela o lista; `quantity` sai como texto, nunca como float."""
    return {
        "item_id": item.id,
        "label": item.label,
        "raw_text": item.raw_text,
        "quantity": None if item.quantity is None else str(item.quantity),
        "unit": item.unit,
        "note": item.note,
        "status": item.status.value,
    }


@dataclass(frozen=True, slots=True)
class _ExtractionSnapshot:
    """Foto do estado da extração paga da rodada, servida pelo `/state`."""

    status: ExtractionStatus
    error_code: str | None = None
    message: str | None = None
    details: dict[str, object] | None = None
    execution: dict[str, object] | None = None
    consented_source_sha256: str | None = None


class _ExtractionTracker:
    """Estado vivo da extração paga, compartilhado entre a rota e a thread de fundo.

    O lock existe para uma coisa só e é a que importa: `claim()` é atômico, então duas
    requisições nunca disparam duas chamadas pagas sobre a mesma rodada. É memória de
    processo, e isso é declarado — servidor reiniciado esquece o que estava rodando, e o
    `/state` reconstrói o desfecho a partir do diretório (extração que fechou deixou
    lineage; a que não fechou não deixou artefato nenhum).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._snapshot = _ExtractionSnapshot(status="idle")

    def snapshot(self) -> _ExtractionSnapshot:
        with self._lock:
            return self._snapshot

    def is_running(self) -> bool:
        with self._lock:
            return self._snapshot.status == "running"

    def claim(self, *, consented_source_sha256: str) -> bool:
        """Reserva a rodada para UMA extração; `False` quando já existe uma em andamento."""
        with self._lock:
            if self._snapshot.status == "running":
                return False
            self._snapshot = _ExtractionSnapshot(
                status="running",
                message=_EXTRACTION_MESSAGES["running"],
                consented_source_sha256=consented_source_sha256,
            )
            return True

    def settle(self, snapshot: _ExtractionSnapshot) -> None:
        """Fecha a etapa com um desfecho declarado — `done`, `failed` ou `unavailable`."""
        with self._lock:
            self._snapshot = snapshot


class _IndexCache:
    """Índice de embeddings carregado uma vez por processo, revalidado a cada uso.

    Existe por um custo medido, não por elegância: o índice do catálogo real tem 40 MB e a
    tela consulta o `/state` em polling. Decodificar 4.964 x 1.536 float32 a cada requisição
    tornaria a etapa mais cara da tela justamente a que só informa disponibilidade.

    A chave de revalidação é `(mtime_ns, tamanho)` do arquivo mais o digest do catálogo
    corrente: arquivo trocado na rodada recarrega, e catálogo trocado força a reconferência
    do vínculo (que recusa, se o índice for de outro catálogo) em vez de servir o vínculo
    antigo. É cache de leitura de artefato local — não de decisão.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._key: tuple[int, int, str] | None = None
        self._index: SemanticIndex | None = None

    def load(self, path: Path, catalog: PriceCatalog) -> SemanticIndex:
        stat = path.stat()
        key = (stat.st_mtime_ns, stat.st_size, catalog.source_sha256)
        with self._lock:
            if self._key == key and self._index is not None:
                return self._index
        index = load_semantic_index(path, catalog)
        with self._lock:
            self._key, self._index = key, index
        return index


@dataclass(frozen=True, slots=True)
class _Run:
    """Diretório de uma rodada do CLI, lido pelos NOMES PADRÃO dos comandos.

    Nenhuma rota recebe caminho: o cliente escolhe a etapa, nunca o arquivo. Isso é o que
    torna travessia de diretório impossível por construção, em vez de filtrada.
    """

    root: Path
    reviewer_id: str
    extraction: _ExtractionTracker = field(default_factory=_ExtractionTracker)
    index_cache: _IndexCache = field(default_factory=_IndexCache)

    def path(self, filename: str) -> Path:
        return self.root / filename

    def read(self, filename: str) -> tuple[str, str] | None:
        """Texto e digest dos bytes do artefato, ou `None` quando ele não está na rodada."""
        path = self.path(filename)
        if not path.is_file():
            return None
        data = path.read_bytes()
        return data.decode("utf-8"), hashlib.sha256(data).hexdigest()

    def require(self, filename: str) -> tuple[str, str]:
        found = self.read(filename)
        if found is None:
            raise _artifact_missing(filename)
        return found

    def digest(self, filename: str) -> str | None:
        found = self.read(filename)
        return None if found is None else found[1]

    def require_packet(self) -> tuple[TakeoffPacket, str]:
        text, digest = self.require(TAKEOFF_PACKET_FILENAME)
        return TakeoffPacket.model_validate_json(text), digest

    def require_catalog(self) -> PriceCatalog:
        text, _digest = self.require(CATALOG_FILENAME)
        return PriceCatalog.model_validate_json(text)

    def contract(self) -> ContractWorkbook | None:
        """Consolidado contratual é opcional aqui, como é no domínio."""
        found = self.read(CONTRACT_FILENAME)
        return None if found is None else ContractWorkbook.model_validate_json(found[0])

    def calc_plan(self) -> CalcPlan | None:
        found = self.read(CALC_PLAN_FILENAME)
        return None if found is None else CalcPlan.model_validate_json(found[0])

    def synonyms(self) -> DomainSynonyms:
        """Sinônimos de domínio da rodada: `synonyms.json` do diretório se existir, senão o
        seed empacotado (`load_round_synonyms`). Nunca `None` — a busca e a sugestão sempre
        têm uma tabela para consultar."""
        return load_round_synonyms(self.root)

    def assignments(self) -> tuple[CodeAssignmentSet, str] | None:
        found = self.read(CODE_ASSIGNMENTS_FILENAME)
        if found is None:
            return None
        return CodeAssignmentSet.model_validate_json(found[0]), found[1]

    def plate_manifest(self) -> PdfManifest | None:
        """Manifest da ingestão da rodada, ou `None` quando não há prancha ingerida.

        Manifest ilegível conta como ausente de propósito: um arquivo editado à mão no
        diretório não pode derrubar a tela inteira — ele derruba só a etapa que depende
        dele, e a rota que precisa mesmo do vínculo (a extração) recusa fechada.
        """
        found = self.read(PLATE_MANIFEST_FILENAME)
        if found is None:
            return None
        try:
            return PdfManifest.model_validate_json(found[0])
        except ValidationError:
            return None

    def promoted_page(self, manifest: PdfManifest) -> Path | None:
        """Página promovida da ingestão, conferida contra o digest que o manifest declara."""
        page = manifest.pages[PLATE_PAGE_NUMBER - 1]
        path = self.path(page.render_file)
        if not path.is_file() or file_sha256(path) != page.image_sha256:
            return None
        return path

    def plate_image(self, packet: TakeoffPacket) -> Path | None:
        """Imagem da prancha do pacote, resolvida pelo digest — o nome é só a primeira pista.

        A rodada sintética grava `prancha.png`; a rodada de prancha real chega com o nome
        de página do ingest (`page-001.png`). Quem decide é o `image_sha256` do pacote:
        arquivo com o nome certo e conteúdo errado não é a evidência daquele takeoff, e um
        overlay desenhado sobre ele mentiria sobre onde o número foi lido.
        """
        named = self.path(PLATE_IMAGE_FILENAME)
        if named.is_file() and file_sha256(named) == packet.image_sha256:
            return named
        matches = [
            candidate
            for candidate in sorted(self.root.glob("*.png"))
            if candidate != named and file_sha256(candidate) == packet.image_sha256
        ]
        return matches[0] if len(matches) == 1 else None


def _pending_code_items(
    packet: TakeoffPacket, assignments: CodeAssignmentSet | None
) -> list[TakeoffItem]:
    """Itens confirmados no takeoff que ainda não receberam decisão de código."""
    decided = set() if assignments is None else {item.item_id for item in assignments.assignments}
    return [item for item in packet.confirmed_items() if item.id not in decided]


def _term_matches_description(term: str, tokens: frozenset[str]) -> bool:
    """Um termo da busca casa com a descrição por PALAVRA, nunca por pedaço de palavra.

    Igualdade sempre vale. Prefixo vale nos dois sentidos — "grama" acha "gramado" e
    "gramado" acha "grama" — a partir de `CATALOG_SEARCH_MIN_PREFIX` caracteres do lado
    que serve de prefixo, que é o que separa flexão de palavra de coincidência de letras.

    O piso existe por causa do defeito real da homologação: "gramado" trazia
    "**pro**gramado**r** de computador", porque a busca casava substring sem fronteira de
    palavra. Substring deixou de ser critério — "gramado" não é token de "programador",
    e nenhum dos dois é prefixo do outro.
    """
    if term in tokens:
        return True
    if len(term) < CATALOG_SEARCH_MIN_PREFIX:
        return False
    return any(
        token.startswith(term)
        or (len(token) >= CATALOG_SEARCH_MIN_PREFIX and term.startswith(token))
        for token in tokens
    )


def _matching_of(suggestions: CodeSuggestionSet) -> str:
    """`hybrid` ou `lexical` derivado do próprio conjunto, nunca do estado do processo.

    Derivar do artefato é o que faz a resposta continuar verdadeira quando ela vem do
    arquivo gravado por outra sessão — inclusive uma que tinha teto de gasto e esta não
    tem."""
    return "hybrid" if suggestions.semantic is not None else "lexical"


def _require_query_terms(query: str) -> tuple[str, ...]:
    """Palavras utilizáveis da busca; consulta sem nenhuma recusa ANTES de qualquer gasto.

    A ordem importa: a rota valida a consulta antes de pedir vetor, senão um `-` digitado
    por engano viraria chamada paga só para ser recusado logo depois.
    """
    terms = lexical_tokens(query)
    if not terms:
        raise ValuationValidationError(
            "LOCAL_SEARCH_QUERY_EMPTY",
            "busca exige ao menos uma palavra com dois caracteres ou mais",
            {"query": query},
        )
    return terms


SEMANTIC_AVAILABLE_MESSAGE: Final = "busca semântica disponível"
SEMANTIC_LIMITED_MESSAGE: Final = "busca semântica limitada às consultas já embutidas"
SEMANTIC_UNAVAILABLE_MESSAGE: Final = "busca semântica indisponível"
"""Prefixos das três situações do braço semântico, sempre com o motivo colado.

Nenhuma delas é erro: a tela continua funcionando com o braço léxico. O que não pode
acontecer é a busca piorar sem ninguém saber por quê — daí o motivo viajar no `/state`, na
resposta da busca e no banner do `serve`."""

SEMANTIC_NOT_REQUESTED_MESSAGE: Final = (
    "busca semântica não solicitada nesta consulta (arm=lexical)"
)
"""Nota de `GET /catalog/search?arm=lexical`: o braço fixável pede explicitamente o
léxico puro, então nenhum vetor é resolvido — zero chamada de embedding e zero escrita
de `query-cache.json`, mesmo quando a rodada tem índice, teto de gasto e credencial."""

SemanticStatus = Literal["available", "limited", "unavailable"]


@dataclass(frozen=True, slots=True)
class _Semantic:
    """Situação do braço semântico da rodada, resolvida a cada requisição.

    `index` presente e `adapter` ausente é o estado `limited`: consulta já embutida no
    cache continua respondendo pelo híbrido, consulta nova cai no léxico com aviso. É o
    estado de um servidor sem teto de gasto rodando sobre uma rodada que já foi indexada —
    útil de verdade, e por isso não é tratado como indisponível.
    """

    index: SemanticIndex | None
    adapter: EmbeddingsAdapter | None
    status: SemanticStatus
    message: str

    def payload(self) -> dict[str, object]:
        return {
            "status": self.status,
            "message": self.message,
            "index_present": self.index is not None,
            "model_id": None if self.index is None else self.index.model_id,
        }


def _semantic_state(run: _Run, catalog: PriceCatalog) -> _Semantic:
    """Índice e via de embeddings da rodada, com o motivo quando algum deles falta.

    Índice ilegível ou de outro catálogo **não** derruba a tela: vira indisponibilidade
    declarada, com o código de domínio no motivo. A recusa fechada de verdade acontece no
    CLI, que é quem publica artefato; aqui o custo de recusar seria o orçamentista sem
    busca nenhuma por causa de um arquivo velho no diretório.
    """
    index_path = run.path(CATALOG_INDEX_FILENAME)
    if not index_path.is_file():
        return _Semantic(None, None, "unavailable", f"{SEMANTIC_UNAVAILABLE_MESSAGE}: sem índice")
    try:
        index = run.index_cache.load(index_path, catalog)
    except (ValuationValidationError, ValidationError) as error:
        domain = error if isinstance(error, ValuationValidationError) else _domain_error(error)
        return _Semantic(
            None,
            None,
            "unavailable",
            f"{SEMANTIC_UNAVAILABLE_MESSAGE}: índice recusado ({domain.code})",
        )
    adapter, reason = embeddings_adapter_or_reason()
    if adapter is None:
        return _Semantic(index, None, "limited", f"{SEMANTIC_LIMITED_MESSAGE}: {reason}")
    return _Semantic(index, adapter, "available", f"{SEMANTIC_AVAILABLE_MESSAGE}: {index.model_id}")


def _semantic_query_vector(
    run: _Run, semantic: _Semantic, query: str
) -> tuple[tuple[float, ...] | None, str | None]:
    """Vetor da consulta pelo cache da rodada, pagando só pelo que ainda não existe.

    Devolve `(None, aviso)` quando o braço semântico não pôde responder ESTA consulta —
    falta de teto de gasto, cache de outro modelo, falha do provider. O aviso vai para a
    resposta da busca; a busca segue pelo léxico, nunca quebra.
    """
    if semantic.index is None:
        return None, semantic.message
    try:
        resolved = resolve_query_vectors(
            [query],
            index=semantic.index,
            cache_path=run.path(QUERY_CACHE_FILENAME),
            adapter=semantic.adapter,
        )
    except ValuationValidationError as error:
        if error.code not in SEMANTIC_DEGRADABLE_CODES:
            raise
        return None, f"{SEMANTIC_UNAVAILABLE_MESSAGE}: {error.code}"
    except ProviderExecutionError as error:
        return None, f"{SEMANTIC_UNAVAILABLE_MESSAGE}: provider {error.code.value}"
    return resolved.by_query.get(normalize_query_text(query)), None


def _result_payload(
    entry: PriceCatalogEntry,
    *,
    origin: str,
    coverage: float,
    semantic_score: float | None,
) -> dict[str, object]:
    """Um resultado da busca com a evidência de por que ele está ali.

    A descrição volta **inteira**: é ela que diz se o código é de execução ou de mero
    fornecimento, e cortá-la esconderia justamente a diferença que o orçamentista precisa
    ver.
    """
    return {
        "code": entry.code,
        "unit": entry.unit,
        "unit_price": str(entry.unit_price),
        "description": entry.description,
        "origin": origin,
        "lexical_score": coverage,
        "semantic_score": semantic_score,
    }


def _catalog_search(
    catalog: PriceCatalog,
    query: str,
    limit: int,
    synonyms: DomainSynonyms | None = None,
    *,
    noise: LegendNoiseList | None = None,
    semantic: _Semantic | None = None,
    query_vec: Sequence[float] | None = None,
    semantic_warning: str | None = None,
) -> dict[str, object]:
    """Busca determinística por palavra-chave sobre o catálogo, ordenada por relevância.

    Normalização é a mesma da sugestão lexical (`lexical_tokens`: NFKD sem acento,
    `casefold`, tokens de dois caracteres ou mais), então a tela e o ranking enxergam o
    texto do mesmo jeito. Um item casa quando **todas** as palavras da busca casam com
    palavras da descrição (`_term_matches_description`) — ou quando o código começa por
    uma delas, que é como se procura `AD0405` direto. Com `synonyms`, cada palavra da busca
    ganha um GRUPO de equivalentes (`expand_terms`): o casamento por palavra passa a valer
    se QUALQUER termo do grupo casar, então uma busca por "refletor" também encontra
    catálogo escrito só com "projetor" — mas continua exigindo uma correspondência por
    palavra ORIGINAL da busca (nenhum termo expandido relaxa a exigência das demais).

    A ordem do braço léxico é por COBERTURA PONDERADA da consulta
    (`weighted_query_coverage_score`, o mesmo scorer do braço léxico da shortlist), com
    `lexical_similarity` desempatando e o código fechando o desempate. A cobertura entrou
    no lugar do Dice puro por causa do achado medido na Fase 1 do M7: o Dice pune a
    descrição longa, e no catálogo real isso empurrava o código certo para o rank 346
    porque a descrição dele é um parágrafo. O peso por IDF veio depois, na 2.1, porque
    cobrir a palavra comum não pode valer o mesmo que cobrir a rara. Devolver na ordem do
    catálogo, como antes de tudo isso, escondia o item certo atrás de homônimos: a página é
    cortada em `limit` **depois** do ranking. `total_matches` continua contando o conjunto
    casado por palavra. Com `noise` (rodada 2.2), o peso de um radical de ESTADO da legenda
    ("existente", "a ser recuperar") é amortecido na cobertura ponderada — não muda quem
    entra na página, mas limpa a COMPOSIÇÃO dela: "REFLETOR EXISTENTE" caiu de 10/20 para
    0/20 itens cujo único mérito era conter "existente" (ver
    `tests/valuation/golden/matcher-golden-v1.json`, `note_phase_2_2`).

    Com `query_vec` (a rodada tem índice, teto de gasto e credencial), a lista casada por
    palavra vira UM braço e o kNN semântico vira o outro, fundidos por RRF: a resposta sai
    com `matching: "hybrid"`, cada resultado declara de qual braço veio (`origin`) e um
    código que nenhuma palavra da busca casa pode aparecer, que é o ponto do braço
    semântico. Sem vetor, `matching: "lexical"` e o motivo vai em `semantic_notes` — a
    busca nunca quebra por causa do braço pago.

    `expanded_terms` só aparece na resposta quando a expansão acrescentou algum termo — é
    o que deixa visível, por exemplo, que "refletor" virou também "projetor".
    """
    terms = _require_query_terms(query)
    # `expand_terms` casa GRUPOS de sinônimo por radical (`lexical_stems`), não pela grafia
    # crua — "alambrado" só bate o grupo porque o radical dele é "alambra". Por isso a
    # expansão é feita PALAVRA A PALAVRA (nunca com a frase inteira de uma vez): assim a
    # origem de cada termo expandido fica sem ambiguidade — é sempre a palavra da busca que
    # acabou de ser expandida, nunca uma mistura das várias palavras digitadas.
    term_groups: dict[str, tuple[str, ...]] = {}
    combined_origins: dict[str, set[str]] = {}
    for term in terms:
        term_stem = lexical_stems(term)
        term_expansion = expand_terms(term_stem, synonyms)
        extras = [candidate for candidate in term_expansion.terms if candidate not in term_stem]
        term_groups[term] = (term, *extras)
        for extra_term, sources in term_expansion.origins.items():
            combined_origins.setdefault(extra_term, set()).update(sources)

    matches: list[tuple[float, float, str]] = []
    coverage_by_code: dict[str, float] = {}
    entries_by_code = {entry.code: entry for entry in catalog.entries}
    idf = catalog_idf_table(catalog, synonyms)
    for entry in catalog.entries:
        tokens = frozenset(lexical_tokens(entry.description))
        code = "".join(lexical_tokens(entry.code))
        by_description = all(
            any(_term_matches_description(candidate, tokens) for candidate in term_groups[term])
            for term in terms
        )
        by_code = any(code.startswith(term) for term in terms)
        if not (by_description or by_code):
            continue
        coverage = weighted_query_coverage_score(
            query, entry.description, idf=idf, synonyms=synonyms, noise=noise
        )
        coverage_by_code[entry.code] = coverage
        matches.append(
            (
                coverage,
                lexical_similarity(query, entry.description, synonyms=synonyms),
                entry.code,
            )
        )
    matches.sort(key=lambda found: (-found[0], -found[1], found[2]))
    lexical_codes = [code for _coverage, _similarity, code in matches[:limit]]

    notes = [] if semantic_warning is None else [semantic_warning]
    results: list[dict[str, object]]
    semantic_scored: list[tuple[str, float]] = []
    if semantic is not None and semantic.index is not None and query_vec is not None:
        semantic_scored = semantic_topk(query_vec, semantic.index, limit)
        matching = "hybrid"
        results = []
        for fused in fuse_arms(lexical_codes, semantic_scored, k=limit):
            found = entries_by_code.get(fused.code)
            if found is None:  # pragma: no cover - índice amarrado ao catálogo por digest
                continue
            # O resultado que veio só do braço semântico não passou pelo filtro por palavra,
            # então a cobertura dele ainda não foi medida; devolver 0.0 sem medir seria dizer
            # que ele não tem nenhuma palavra da busca, o que nem sempre é verdade.
            if fused.code not in coverage_by_code:
                coverage_by_code[fused.code] = weighted_query_coverage_score(
                    query, found.description, idf=idf, synonyms=synonyms, noise=noise
                )
            results.append(
                _result_payload(
                    found,
                    origin=fused.origin,
                    coverage=coverage_by_code[fused.code],
                    semantic_score=fused.semantic_score,
                )
            )
    else:
        matching = "lexical"
        results = [
            _result_payload(
                entries_by_code[code],
                origin="lexical",
                coverage=coverage_by_code.get(code, 0.0),
                semantic_score=None,
            )
            for code in lexical_codes
        ]

    result: dict[str, object] = {
        "query": query,
        "terms": list(terms),
        "limit": limit,
        "matching": matching,
        "total_matches": len(matches),
        "semantic_matches": len(semantic_scored),
        "semantic_notes": notes,
        "results": results,
    }
    if combined_origins:
        result["expanded_terms"] = {
            term: sorted(sources) for term, sources in combined_origins.items()
        }
    return result


# --------------------------------------------------------------------------------------
# Prancha do projetista: upload, ingestão local e extração paga automática
# --------------------------------------------------------------------------------------

_FALLBACK_DATASET_ID: Final = "prancha-local"

_MULTI_PAGE_NOTE: Final = (
    "PDF com {pages} páginas: só a página 1 virou prancha desta rodada; as demais não "
    "foram lidas nem enviadas"
)

_ARM_UNAVAILABLE_MESSAGE: Final = (
    "extração automática indisponível: teto de gasto ou credencial do provider recusados "
    "pelo servidor"
)


def _dataset_id(root: Path) -> str:
    """Identificador da rodada para a ingestão, derivado do nome do diretório.

    O manifest tem contrato fechado para esse campo (`[a-z0-9][a-z0-9-]{2,63}`), então nome
    de pasta com acento, espaço ou maiúscula vira slug. Nome que não sobrevive à
    normalização cai num rótulo declarado em vez de derrubar o upload do orçamentista — é
    o mesmo identificador que vai para `plate_id`, e ele identifica a rodada, não o cliente.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", root.name.lower()).strip("-")[:64]
    return slug if re.fullmatch(r"[a-z0-9][a-z0-9-]{2,63}", slug) else _FALLBACK_DATASET_ID


async def _read_upload(file: UploadFile) -> bytes:
    """Lê o upload em pedaços e para no teto declarado.

    O corte acontece **durante** a leitura: um arquivo gigante nunca chega inteiro à
    memória do processo só para ser recusado no fim.
    """
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_PLATE_PDF_BYTES:
            raise _upload_invalid(
                "arquivo acima do limite de upload da prancha",
                {"max_bytes": MAX_PLATE_PDF_BYTES},
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _promote_first_page(run: _Run, pdf_path: Path) -> PdfManifest:
    """Renderiza o PDF num temporário da rodada e promove a página 1 mais o manifest.

    Renderizar fora do lugar final e mover depois é o que impede a rodada de ficar com
    meia prancha: só entram no diretório o PNG da página que o manifest declara e o
    próprio manifest. O resto da ingestão (contact sheet, demais páginas) é descartado —
    esta rodada é de uma prancha só.
    """
    workspace = Path(tempfile.mkdtemp(dir=run.root, prefix=".prancha-ingest-"))
    try:
        manifest, manifest_path = ingest_pdf(
            pdf_path,
            workspace,
            dataset_id=_dataset_id(run.root),
            role=PLATE_INGEST_ROLE,
            dpi=PLATE_INGEST_DPI,
        )
        page = manifest.pages[PLATE_PAGE_NUMBER - 1]
        rendered = manifest_path.parent / page.render_file
        if file_sha256(rendered) != page.image_sha256:  # pragma: no cover - ingestão coerente
            raise _upload_invalid("a página renderizada não confere com o manifest da ingestão")
        os.replace(rendered, run.path(page.render_file))
        os.replace(manifest_path, run.path(PLATE_MANIFEST_FILENAME))
        return manifest
    except (ValueError, RuntimeError) as error:
        # PDF protegido por senha, sem páginas ou ilegível para o renderizador.
        raise _upload_invalid(str(error)[:200], {"stage": "ingest"}) from error
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def _ingest_plate_upload(run: _Run, *, filename: str | None, payload: bytes) -> PdfManifest:
    """Grava a prancha enviada e devolve o manifest da ingestão.

    Validação antes de qualquer escrita (extensão, tamanho e assinatura do arquivo) e
    desfazimento depois de qualquer falha: ingestão que não fecha remove o PDF, e a rodada
    volta a ser exatamente o que era antes do clique.
    """
    name = (filename or "").strip()
    if not name.lower().endswith(".pdf"):
        raise _upload_invalid("o arquivo precisa ser um PDF (.pdf)", {"filename": name})
    if not payload:
        raise _upload_invalid("arquivo vazio")
    if not payload.startswith(b"%PDF-"):
        raise _upload_invalid("assinatura de PDF ausente no início do arquivo")

    pdf_path = run.path(PLATE_PDF_FILENAME)
    atomic_write_bytes(pdf_path, payload)
    try:
        return _promote_first_page(run, pdf_path)
    except Exception:
        pdf_path.unlink(missing_ok=True)
        raise


def _extraction_arm_spec() -> str:
    """Braço pago em uso. A env é o escape declarado para a próxima eval comparativa."""
    return os.environ.get(EXTRACTION_ARM_ENV, "").strip() or MEDICAO_EXTRACTION_ARM


def _missing_extraction_envs(arm_spec: str) -> list[str]:
    """Variáveis obrigatórias que faltam para a extração paga poder sequer começar."""
    provider = arm_spec.partition("=")[2].partition(":")[0]
    required = [AI_BUDGET_ENV]
    credential = _PROVIDER_CREDENTIAL_ENV.get(provider)
    if credential is not None:
        required.append(credential)
    return [name for name in required if not os.environ.get(name, "").strip()]


def _extraction_unavailable(arm_spec: str) -> ValuationValidationError | None:
    """Motivo de a extração paga não poder ser tentada, ou `None` quando ela pode.

    É esta pré-checagem que garante o freio principal: **nunca** existe tentativa sem teto
    de gasto declarado no ambiente do servidor. Ela roda antes da thread e antes de
    qualquer byte sair da máquina, e o que ela devolve vira estado visível na tela.
    """
    missing = _missing_extraction_envs(arm_spec)
    if not missing:
        return None
    return ValuationValidationError(
        "LOCAL_EXTRACTION_UNAVAILABLE",
        _NO_BUDGET_MESSAGE if AI_BUDGET_ENV in missing else _NO_CREDENTIAL_MESSAGE,
        {"missing_env": missing, "arm": arm_spec},
    )


def _build_extraction_adapter(arm_spec: str) -> tuple[str, str, ProviderAdapter]:
    """Monta o braço pago `NOME=PROVIDER:MODELO` da extração automática.

    Espelho de `cli._build_paid_arm` com os códigos deste servidor: forma inválida e
    provider `fixture` recusam antes de qualquer rede — observação fabricada não vira
    pacote de rodada —, e a `ValueError` de `build_extraction_arm` (teto de gasto ausente
    ou credencial faltando) vira recusa de domínio em vez de erro de servidor.

    É também o seam de teste do módulo: o teste troca esta fábrica por um adapter fixture,
    e nenhuma chamada externa acontece na suíte.
    """
    name, separator, target = arm_spec.partition("=")
    provider, model_separator, model_id = target.partition(":")
    if not name or not separator or not provider or not model_separator or not model_id:
        raise ValuationValidationError(
            "LOCAL_EXTRACTION_ARM_INVALID",
            _ARM_MISCONFIGURED_MESSAGE,
            {"arm": arm_spec},
        )
    if provider == "fixture":
        raise ValuationValidationError(
            "LOCAL_EXTRACTION_ARM_FIXTURE_FORBIDDEN",
            _FIXTURE_ARM_MESSAGE,
            {"arm": arm_spec},
        )
    try:
        adapter = build_extraction_arm(provider=provider, model_id=model_id)
    except ValueError as error:
        raise ValuationValidationError(
            "LOCAL_EXTRACTION_UNAVAILABLE",
            _ARM_UNAVAILABLE_MESSAGE,
            {"arm": arm_spec, "reason": str(error)},
        ) from error
    return name, model_id, adapter


def _authorize_uploaded_page(manifest_path: Path, page_sha256: str) -> str:
    """Autoriza a página consentida pelo upload e devolve o digest do documento.

    A allowlist global (`CROQUITODXF_AI_EXTRACTION_ALLOWED_DIGESTS`) **não se aplica a este
    fluxo**, e a dispensa é decisão registrada, não esquecimento: naquela via o
    consentimento é a variável de ambiente que um operador declara antes de mandar o
    documento de um cliente para fora; nesta via o consentimento é o próprio ato do
    orçamentista de subir a prancha na tela, e o digest nasce do arquivo que ele acabou de
    enviar — ele vai para o estado e para o `extraction-lineage.json`, onde fica auditável.
    Dispensar a allowlist não dispensa o outro amarrado, e por isso ele continua aqui: a
    imagem enviada tem de ser a página que o manifest da ingestão declara
    (`bind_page_to_document`), senão um PNG largado no diretório viraria evidência de um
    documento que ninguém enviou.
    """
    return bind_page_to_document(manifest_path, page_sha256)


def _extract_legend_from_upload(
    run: _Run, manifest: PdfManifest, adapter: ProviderAdapter
) -> LegendExtractionResult:
    """Extrai a legenda da prancha consentida pelo upload.

    Compõe as MESMAS peças de `legend_extraction.run_legend_extraction` — pedido,
    chamada, mapeamento observação→takeoff e registro fino do bbox contra a tinta —
    trocando **só** o portão de consentimento (`_authorize_uploaded_page` no lugar de
    `authorize_page`). O caminho pago do CLI fica intocado; a parity entre as duas
    montagens é prendida por teste, para que elas não possam divergir em silêncio.
    """
    page = manifest.pages[PLATE_PAGE_NUMBER - 1]
    image_path = run.path(page.render_file).resolve(strict=True)
    image_sha256 = hashlib.sha256(image_path.read_bytes()).hexdigest()
    source_sha256 = _authorize_uploaded_page(run.path(PLATE_MANIFEST_FILENAME), image_sha256)

    request, width, height = build_legend_request(image_path)
    execution = adapter.execute(request)
    output = execution.output
    if not isinstance(output, LegendExtractionOutput):  # pragma: no cover - contrato do adapter
        raise ProviderExecutionError(ProviderFailureCode.INVALID_SCHEMA)
    packet = takeoff_packet_from_legend(
        output,
        plate_id=_dataset_id(run.root),
        page_number=PLATE_PAGE_NUMBER,
        image_sha256=image_sha256,
        source_pdf_sha256=source_sha256,
        image_width=width,
        image_height=height,
        extractor=extractor_label(execution.provider.value, execution.model_id),
        extractor_version=execution.prompt.prompt_version,
    )
    registered, registration = register_legend_bboxes(image_path, packet)
    return LegendExtractionResult(
        packet=registered,
        execution=execution,
        source_sha256=source_sha256,
        registration=registration,
    )


def _execution_payload(execution: ProviderExecution) -> dict[str, object]:
    """Lineage e custo de uma chamada paga. Espelho de `cli._execution_payload`.

    IDs, versão de prompt, tokens, custo e latência — nunca a resposta bruta nem o que foi
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


def _registration_payload(registration: LegendRegistrationReport) -> dict[str, object]:
    """Relatório do registro fino no mesmo formato de `cli.run_register_takeoff`.

    `method` viaja junto porque é ele que decide se a âncora de um item pode ser
    declarada confiável para a tela (`_registered_item_ids`): relatório sem método
    declarado não sustenta retângulo desenhado sobre a prancha.
    """
    return {
        "adjusted": registration.adjusted,
        "unmatched_item_ids": registration.unmatched_item_ids,
        "band_count": registration.band_count,
        "method": registration.method,
        "global_scale": registration.global_scale,
        "global_shift_px": registration.global_shift_px,
        "shift_score": registration.shift_score,
        "shift_confidence": registration.shift_confidence,
    }


def _publish_extraction(
    run: _Run, result: LegendExtractionResult, *, arm_spec: str, image_path: Path
) -> dict[str, object]:
    """Publica pacote, overlay, relatório do registro e lineage; devolve o bloco de execução.

    A ordem é a do `cli._publish_takeoff`: o overlay é renderizado em memória **antes** de
    qualquer escrita, então uma prancha que não bate deixa a rodada intacta e a extração
    inteira aparece como `failed`. Pacote publicado sem overlay não é meio-caminho
    aceitável: é o overlay que mostra ao orçamentista de onde cada número foi lido.
    """
    overlay = render_takeoff_overlay(image_path, result.packet)
    execution = _execution_payload(result.execution)
    lineage: dict[str, object] = {
        "server_version": LOCAL_SERVER_VERSION,
        "arm": arm_spec,
        "plate_id": result.packet.plate_id,
        "page_number": result.packet.page_number,
        "image_sha256": result.packet.image_sha256,
        "consented_source_sha256": result.source_sha256,
        "consent": "upload da prancha pelo orçamentista no servidor local de homologação",
        "extracted_at": _now().isoformat(),
        "execution": execution,
    }
    atomic_write_text(run.path(TAKEOFF_PACKET_FILENAME), _document(result.packet))
    save_takeoff_overlay(overlay, run.path(TAKEOFF_OVERLAY_FILENAME))
    atomic_write_text(
        run.path(TAKEOFF_REGISTRATION_REPORT_FILENAME),
        _serialize(_registration_payload(result.registration)),
    )
    atomic_write_text(run.path(EXTRACTION_LINEAGE_FILENAME), _serialize(lineage))
    return execution


def _extraction_failure(error: Exception, *, consented_source_sha256: str) -> _ExtractionSnapshot:
    """Traduz a exceção da thread num estado visível, com o código estável de cada família.

    Nenhuma falha some: o que não é erro conhecido vira `LOCAL_EXTRACTION_FAILED` com o
    nome da classe, porque thread que morre em silêncio deixaria a tela girando para
    sempre — e o orçamentista pensando que a extração ainda vem.
    """
    if isinstance(error, ProviderExecutionError):
        return _ExtractionSnapshot(
            status="failed",
            error_code="PROVIDER_EXECUTION_FAILED",
            message="a chamada ao provider falhou; nenhum artefato foi publicado",
            details={"code": error.code.value},
            consented_source_sha256=consented_source_sha256,
        )
    if isinstance(error, ExtractionNotAllowlistedError):
        return _ExtractionSnapshot(
            status="failed",
            error_code="EXTRACTION_PAGE_NOT_BOUND",
            message=(
                "a imagem da prancha não é a página que o manifest da rodada declara; "
                "nada foi enviado"
            ),
            consented_source_sha256=consented_source_sha256,
        )
    domain = error if isinstance(error, ValuationValidationError) else None
    if isinstance(error, ValidationError):
        domain = _domain_error(error)
    if domain is not None:
        return _ExtractionSnapshot(
            status="failed",
            error_code=domain.code,
            message=domain.message,
            details=domain.details,
            consented_source_sha256=consented_source_sha256,
        )
    return _ExtractionSnapshot(
        status="failed",
        error_code="LOCAL_EXTRACTION_FAILED",
        message="a extração automática falhou; nenhum artefato foi publicado",
        details={"error": type(error).__name__},
        consented_source_sha256=consented_source_sha256,
    )


def _run_extraction(
    run: _Run, manifest: PdfManifest, adapter: ProviderAdapter, arm_spec: str
) -> None:
    """Corpo da thread de extração: sempre termina com um desfecho declarado.

    Ela não levanta para fora: qualquer exceção vira estado `failed` no `/state`. Falha
    não publica artefato nenhum, e PDF, PNG e manifest continuam na rodada — é isso que
    permite `POST /plates/extract` re-tentar sem reenviar o documento.
    """
    consented = manifest.source_sha256
    try:
        result = _extract_legend_from_upload(run, manifest, adapter)
        execution = _publish_extraction(
            run,
            result,
            arm_spec=arm_spec,
            image_path=run.path(manifest.pages[PLATE_PAGE_NUMBER - 1].render_file),
        )
    except Exception as error:
        run.extraction.settle(_extraction_failure(error, consented_source_sha256=consented))
        return
    run.extraction.settle(
        _ExtractionSnapshot(
            status="done",
            message=_EXTRACTION_MESSAGES["done"],
            execution=execution,
            consented_source_sha256=result.source_sha256,
        )
    )


def _record_unavailable(
    run: _Run, error: ValuationValidationError, manifest: PdfManifest
) -> ValuationValidationError:
    """Registra no estado que a extração não pôde nem começar, e devolve o motivo."""
    run.extraction.settle(
        _ExtractionSnapshot(
            status="unavailable",
            error_code=error.code,
            message=error.message,
            details=error.details,
            consented_source_sha256=manifest.source_sha256,
        )
    )
    return error


def _trigger_extraction(run: _Run, manifest: PdfManifest) -> ValuationValidationError | None:
    """Dispara a extração paga em thread e volta na hora; `None` quando ela começou.

    Quando não dá para começar — servidor sem teto de gasto, sem credencial ou com braço
    mal configurado —, o motivo vira estado `unavailable` e é devolvido a quem chamou. O
    upload continua valendo (a prancha fica na rodada, e a extração pela CLI continua
    possível), e o re-disparo é sempre um ato explícito, nunca uma tentativa às escondidas.
    """
    if run.extraction.is_running():
        raise _extraction_busy()
    arm_spec = _extraction_arm_spec()
    unavailable = _extraction_unavailable(arm_spec)
    if unavailable is not None:
        return _record_unavailable(run, unavailable, manifest)
    try:
        _name, _model_id, adapter = _build_extraction_adapter(arm_spec)
    except ValuationValidationError as error:
        return _record_unavailable(run, error, manifest)
    except Exception as error:
        # SDK do provider que nem chega a subir (região ausente, credencial malformada): a
        # rodada não cai por isso. A prancha já está ingerida e "indisponível" é exatamente
        # o que o estado tem a dizer — 500 aqui esconderia a causa do orçamentista.
        return _record_unavailable(
            run,
            ValuationValidationError(
                "LOCAL_EXTRACTION_UNAVAILABLE",
                _ARM_UNAVAILABLE_MESSAGE,
                {"arm": arm_spec, "error": type(error).__name__},
            ),
            manifest,
        )
    if not run.extraction.claim(consented_source_sha256=manifest.source_sha256):
        raise _extraction_busy()
    threading.Thread(
        target=_run_extraction,
        args=(run, manifest, adapter, arm_spec),
        name="medicao-extracao",
        daemon=True,
    ).start()
    return None


def _read_lineage(run: _Run) -> dict[str, object] | None:
    """Lineage gravado da última extração concluída nesta rodada, se houver um legível."""
    found = run.read(EXTRACTION_LINEAGE_FILENAME)
    if found is None:
        return None
    try:
        parsed = json.loads(found[0])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _snapshot_from_disk(run: _Run, manifest: PdfManifest | None) -> _ExtractionSnapshot:
    """Desfecho reconstruído do diretório quando a memória do processo não tem nada a dizer.

    Lineage gravado significa extração concluída — inclusive por um processo anterior. Sem
    ele, a falta de teto/credencial já é declarada como `unavailable` na abertura da tela,
    para o orçamentista não descobrir isso só depois de subir a prancha.
    """
    lineage = _read_lineage(run)
    if lineage is not None:
        execution = lineage.get("execution")
        consented = lineage.get("consented_source_sha256")
        return _ExtractionSnapshot(
            status="done",
            message=_EXTRACTION_MESSAGES["done"],
            execution=execution if isinstance(execution, dict) else None,
            consented_source_sha256=consented if isinstance(consented, str) else None,
        )
    unavailable = _extraction_unavailable(_extraction_arm_spec())
    if unavailable is not None:
        return _ExtractionSnapshot(
            status="unavailable",
            error_code=unavailable.code,
            message=unavailable.message,
            details=unavailable.details,
        )
    return _ExtractionSnapshot(
        status="idle",
        message=_EXTRACTION_MESSAGES["ingested" if manifest is not None else "no_plate"],
    )


def _extraction_payload(run: _Run) -> dict[str, object]:
    """Etapa `extracao` do estado: o que a chamada paga fez, está fazendo ou não pôde fazer.

    A contagem de páginas do manifest viaja junto porque a limitação é declarada, não
    escondida: a rodada leu a página 1 e o orçamentista precisa saber quantas o documento
    tinha.
    """
    manifest = run.plate_manifest()
    snapshot = run.extraction.snapshot()
    if snapshot.status == "idle":
        snapshot = _snapshot_from_disk(run, manifest)
    notes = (
        [_MULTI_PAGE_NOTE.format(pages=manifest.page_count)]
        if manifest is not None and manifest.page_count > 1
        else []
    )
    return {
        "status": snapshot.status,
        "error_code": snapshot.error_code,
        "message": snapshot.message,
        "details": snapshot.details,
        "execution": snapshot.execution,
        "consented_source_sha256": snapshot.consented_source_sha256,
        "arm": _extraction_arm_spec(),
        "plate_pdf_present": run.path(PLATE_PDF_FILENAME).is_file(),
        "pages": None if manifest is None else manifest.page_count,
        "page_number": PLATE_PAGE_NUMBER,
        "notes": notes,
    }


# --------------------------------------------------------------------------------------
# Preparo da rodada no start do servidor: catálogo de preços e aviso da extração
# --------------------------------------------------------------------------------------

CATALOG_SOURCE_ENV: Final = "CROQUITODXF_MEDICAO_CATALOG"
"""Alternativa à flag `--catalog`. A flag vence: quem digita o comando manda."""

CATALOG_NOTES: Final[Mapping[str, str]] = {
    "installed": "catálogo de preços copiado para a rodada",
    "preserved": "catálogo da rodada preservado; a fonte informada foi ignorada",
    "present": "catálogo da rodada presente",
    "missing": "rodada sem catálogo de preços — use --catalog",
}
"""Avisos do banner do `serve`. Eles são a única forma de o operador saber, antes de abrir
a tela, que a referência do catálogo não vai ter o que mostrar."""

EXTRACTION_AVAILABLE_NOTE: Final = "disponível"


def catalog_source(flag: str | None) -> Path | None:
    """Fonte do catálogo declarada para esta rodada; a flag vence a variável de ambiente."""
    raw = (flag or os.environ.get(CATALOG_SOURCE_ENV, "")).strip()
    return Path(raw).expanduser() if raw else None


def install_round_catalog(root: Path, source: Path | None) -> str:
    """Instala o catálogo de preços na rodada quando ela ainda não tem um; devolve o aviso.

    Rodada nascida de upload não passou pelo `import-workbook`, então ela não tem
    `catalog.json` — e sem ele a referência do catálogo na tela não teria o que mostrar e
    a confirmação de código não teria contra o que validar. A cópia acontece uma vez, no
    start, e o arquivo passa a ser **da rodada**: digest estável no `/state`, como qualquer
    outro artefato.

    Catálogo que já está na rodada nunca é sobrescrito, nem com `--catalog` apontando para
    outro arquivo: ele é a evidência de preço sobre a qual as confirmações de código foram
    feitas, e trocá-lo por baixo de decisões já registradas mudaria o boletim sem ninguém
    ter decidido nada. A fonte é ignorada com aviso, não em silêncio.

    O arquivo é validado antes de entrar (`PriceCatalog`) e copiado **literal**: o que a
    rodada guarda é o mesmo documento que o operador conferiu, não uma reserialização.
    """
    target = root / CATALOG_FILENAME
    if target.is_file():
        return CATALOG_NOTES["preserved" if source is not None else "present"]
    if source is None:
        return CATALOG_NOTES["missing"]
    try:
        document = source.read_text(encoding="utf-8")
        PriceCatalog.model_validate_json(document)
    except (OSError, UnicodeDecodeError) as error:
        raise ValuationValidationError(
            "LOCAL_CATALOG_INVALID",
            "catálogo de preços informado não pôde ser lido",
            {"catalog": str(source), "reason": type(error).__name__},
        ) from error
    except ValuationValidationError as error:
        raise ValuationValidationError(
            "LOCAL_CATALOG_INVALID",
            "arquivo informado não é um catálogo de preços válido",
            {"catalog": str(source), "reason": error.code},
        ) from error
    except ValidationError as error:
        raise ValuationValidationError(
            "LOCAL_CATALOG_INVALID",
            "arquivo informado não é um catálogo de preços válido",
            {"catalog": str(source), "reason": _domain_error(error).code},
        ) from error
    atomic_write_text(target, document)
    return CATALOG_NOTES["installed"]


CATALOG_INDEX_NOTES: Final[Mapping[str, str]] = {
    "installed": "índice de embeddings do catálogo copiado para a rodada",
    "preserved": "índice da rodada preservado; o índice da fonte foi ignorado",
    "present": "índice de embeddings da rodada presente",
    "missing": "fonte informada não tem índice ao lado; rode `index-catalog`",
    "no_source": "rodada sem índice de embeddings — a busca fica só lexical",
    "mismatch": "índice da fonte pertence a outro catálogo; não foi copiado",
}


def install_round_catalog_index(root: Path, source: Path | None) -> str:
    """Copia o índice de embeddings que estiver ao lado do catálogo-fonte; devolve o aviso.

    Mesma regra do catálogo, pelo mesmo motivo: índice já presente na rodada **nunca** é
    sobrescrito — ele é a evidência sobre a qual as shortlists foram montadas. E ele só
    entra se pertencer ao catálogo QUE A RODADA TEM: copiar um índice de outro catálogo
    apenas adiaria a recusa da carga para a primeira busca do orçamentista.
    """
    target = root / CATALOG_INDEX_FILENAME
    if target.is_file():
        return CATALOG_INDEX_NOTES["preserved" if source is not None else "present"]
    if source is None:
        return CATALOG_INDEX_NOTES["no_source"]
    candidate = source.parent / CATALOG_INDEX_FILENAME
    round_catalog = root / CATALOG_FILENAME
    if not candidate.is_file() or not round_catalog.is_file():
        return CATALOG_INDEX_NOTES["missing"]
    try:
        catalog = PriceCatalog.model_validate_json(round_catalog.read_text(encoding="utf-8"))
        document = candidate.read_text(encoding="utf-8")
        index, digest = read_catalog_index(candidate)
        bind_index_to_catalog(index, digest, catalog)
    except (OSError, UnicodeDecodeError, ValuationValidationError, ValidationError):
        return CATALOG_INDEX_NOTES["mismatch"]
    atomic_write_text(target, document)
    return CATALOG_INDEX_NOTES["installed"]


def extraction_banner_note() -> str:
    """Disponibilidade da extração paga no start, pela MESMA pré-checagem do `/state`.

    Reusar `_extraction_unavailable` é o que impede o banner de prometer no start algo que
    a tela vai negar depois — e é no start que o operador ainda pode exportar a variável
    que falta.
    """
    arm_spec = _extraction_arm_spec()
    unavailable = _extraction_unavailable(arm_spec)
    if unavailable is None:
        return f"{EXTRACTION_AVAILABLE_NOTE} ({arm_spec})"
    return unavailable.message


def _state_payload(run: _Run) -> dict[str, object]:
    """Etapas da rodada derivadas da EXISTÊNCIA dos artefatos, com os digests atuais.

    O `valuation.json` entra aqui só por presença e digest: revalidá-lo é papel do
    `GET /bulletin`, e uma medição ilegível não pode derrubar a tela inteira antes de o
    orçamentista sequer chegar nela.
    """
    packet_found = run.read(TAKEOFF_PACKET_FILENAME)
    packet = None if packet_found is None else TakeoffPacket.model_validate_json(packet_found[0])
    assignments_found = run.assignments()
    suggestions_digest = run.digest(CODE_SUGGESTIONS_FILENAME)
    valuation_digest = run.digest(VALUATION_FILENAME)

    artifacts: dict[str, str] = {}
    for filename in (
        TAKEOFF_PACKET_FILENAME,
        CATALOG_FILENAME,
        CONTRACT_FILENAME,
        CODE_SUGGESTIONS_FILENAME,
        CODE_ASSIGNMENTS_FILENAME,
        CALC_PLAN_FILENAME,
        VALUATION_FILENAME,
    ):
        digest = run.digest(filename)
        if digest is not None:
            artifacts[filename] = digest

    takeoff: dict[str, object] = {"present": packet is not None}
    if packet is not None and packet_found is not None:
        takeoff.update(
            {
                "packet_sha256": packet_found[1],
                "plate_id": packet.plate_id,
                "page_number": packet.page_number,
                "review_status": _review_status(packet),
                **_takeoff_counts(packet),
                **_anchor_counts(packet, _registered_item_ids(run)),
            }
        )

    assignment_set = None if assignments_found is None else assignments_found[0]
    codes: dict[str, object] = {
        "suggestions_present": suggestions_digest is not None,
        "suggestions_sha256": suggestions_digest,
        "assignments_present": assignment_set is not None,
        "assignments_sha256": None if assignments_found is None else assignments_found[1],
        "confirmed": 0 if assignment_set is None else _count_status(assignment_set, "confirmed"),
        "rejected": 0 if assignment_set is None else _count_status(assignment_set, "rejected"),
        "pending": (None if packet is None else len(_pending_code_items(packet, assignment_set))),
    }

    plate_image = None if packet is None else run.plate_image(packet)
    overlay_path = run.path(TAKEOFF_OVERLAY_FILENAME)
    return {
        "server_version": LOCAL_SERVER_VERSION,
        "root": str(run.root),
        "reviewer_id": run.reviewer_id,
        "reviewer_role": REVIEWER_ROLE,
        "artifacts": artifacts,
        "busca_semantica": _semantic_payload(run),
        "images": {
            "plate": {
                "present": plate_image is not None,
                "filename": None if plate_image is None else plate_image.name,
            },
            "overlay": {"present": overlay_path.is_file()},
        },
        "extracao": _extraction_payload(run),
        "takeoff": takeoff,
        "codes": codes,
        "bulletin": {"present": valuation_digest is not None, "valuation_sha256": valuation_digest},
    }


def _count_status(assignments: CodeAssignmentSet, status: str) -> int:
    return sum(1 for assignment in assignments.assignments if assignment.status == status)


def _semantic_payload(run: _Run) -> dict[str, object]:
    """Etapa `busca_semantica` do estado: disponível, limitada ao cache ou indisponível.

    Rodada sem catálogo não tem contra o que amarrar índice nenhum, e isso é dito com
    essas palavras em vez de virar "indisponível" sem causa. Como o resto do `/state`, é
    informativo: nada aqui bloqueia a tela.
    """
    found = run.read(CATALOG_FILENAME)
    if found is None:
        return {
            "status": "unavailable",
            "message": f"{SEMANTIC_UNAVAILABLE_MESSAGE}: rodada sem catálogo de preços",
            "index_present": run.path(CATALOG_INDEX_FILENAME).is_file(),
            "model_id": None,
        }
    return _semantic_state(run, PriceCatalog.model_validate_json(found[0])).payload()


def _compute_suggestions_response(run: _Run) -> dict[str, object]:
    """Recomputa a shortlist do zero e publica, sobrescrevendo o arquivo da rodada.

    Corpo extraído de `GET /suggestions` para ser compartilhado com
    `POST /suggestions/recompute`: os dois pagam a MESMA via de embeddings (cache da
    rodada, nunca chamada dobrada) e escrevem com o mesmo `atomic_write_text`, sem backup
    — o arquivo anterior não é preservado, porque a garantia de não perder trabalho é o
    digest-base que a rota de recompute exige antes de chegar aqui.

    Pending do takeoff continua bloqueando os dois: computar sobre revisão incompleta
    congelaria em disco uma shortlist sem os itens que ainda vão ser confirmados.
    """
    packet, _digest = run.require_packet()
    pending = packet.pending_items()
    if pending:
        raise ValuationValidationError(
            "LOCAL_TAKEOFF_REVIEW_INCOMPLETE",
            "sugestão de código exige a revisão do takeoff concluída",
            {"pending_item_ids": [item.id for item in pending]},
        )
    catalog = run.require_catalog()
    contract = run.contract()
    synonyms = run.synonyms()
    semantic = _semantic_state(run, catalog)
    computed: CodeSuggestionSet | None = None
    notes: list[str] = []
    if semantic.index is None:
        notes.append(semantic.message)
    else:
        try:
            resolved = resolve_query_vectors(
                [item.label for item in packet.confirmed_items()],
                index=semantic.index,
                cache_path=run.path(QUERY_CACHE_FILENAME),
                adapter=semantic.adapter,
            )
            computed = build_hybrid_code_suggestions(
                packet,
                catalog,
                contract,
                index=semantic.index,
                query_vectors=resolved.by_query,
                synonyms=synonyms,
                noise=default_legend_noise(),
            )
        except ValuationValidationError as error:
            if error.code not in SEMANTIC_DEGRADABLE_CODES:
                raise
            notes.append(f"{SEMANTIC_UNAVAILABLE_MESSAGE}: {error.code}")
        except ProviderExecutionError as error:
            notes.append(f"{SEMANTIC_UNAVAILABLE_MESSAGE}: provider {error.code.value}")
    if computed is None:
        computed = build_code_suggestions(packet, catalog, contract, synonyms=synonyms)
    document = _document(computed)
    atomic_write_text(run.path(CODE_SUGGESTIONS_FILENAME), document)
    return {
        "suggestions": computed.model_dump(mode="json"),
        "suggestions_sha256": _digest_of(document),
        "computed": True,
        "matching": _matching_of(computed),
        "semantic_notes": notes,
    }


def create_local_app(root: Path, reviewer_id: str) -> FastAPI:
    """Monta o servidor local sobre um diretório de rodada já produzido pelo CLI.

    `reviewer_id` é a identidade de quem decide durante toda a vida do processo: ela entra
    em cada `ReviewerDecision` gravada, ao lado do relógio do servidor. Trocar de revisor é
    subir outro processo, não mandar outro campo.
    """
    resolved = root.expanduser().resolve()
    if not resolved.is_dir():
        raise ValuationValidationError(
            "LOCAL_ROOT_MISSING",
            "diretório da rodada não existe; aponte --root para a saída de um comando",
            {"root": str(resolved)},
        )
    cleaned_reviewer = reviewer_id.strip()
    if not 1 <= len(cleaned_reviewer) <= 120:
        raise ValuationValidationError(
            "LOCAL_REVIEWER_INVALID",
            "identidade do revisor deve ter de 1 a 120 caracteres",
            {"length": len(cleaned_reviewer)},
        )
    run = _Run(root=resolved, reviewer_id=cleaned_reviewer)

    application = FastAPI(
        title="CroquiToDXF — homologação local da medição",
        version="0.1.0",
        description=(
            "Ferramenta LOCAL de homologação: sem autenticação, sem provider e sem AWS. "
            "Serve e muta os artefatos de um diretório de rodada pelas mesmas funções de "
            "domínio que o CLI `croquitodxf-valuation` usa."
        ),
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(LOCAL_WEB_ORIGINS),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @application.exception_handler(LocalServerRefusal)
    async def refusal_handler(_request: Request, exception: LocalServerRefusal) -> JSONResponse:
        return _problem(exception.status_code, exception.error)

    @application.exception_handler(ValuationValidationError)
    async def domain_handler(
        _request: Request, exception: ValuationValidationError
    ) -> JSONResponse:
        return _problem(422, exception)

    @application.exception_handler(ValidationError)
    async def model_handler(_request: Request, exception: ValidationError) -> JSONResponse:
        return _problem(422, _domain_error(exception))

    @application.exception_handler(RequestValidationError)
    async def request_handler(_request: Request, exception: RequestValidationError) -> JSONResponse:
        """Corpo fora do contrato — inclusive `reviewer_id`/`decided_at` proibidos por
        `extra="forbid"`. Só a posição e o tipo do erro voltam: valor de corpo não é eco."""
        return _problem(
            422,
            ValuationValidationError(
                "LOCAL_REQUEST_INVALID",
                "corpo da requisição não corresponde ao contrato da rota",
                {
                    "errors": [
                        {"loc": ".".join(str(part) for part in line["loc"]), "type": line["type"]}
                        for line in exception.errors()
                    ]
                },
            ),
        )

    @application.get("/state", tags=["state"])
    async def read_state() -> dict[str, object]:
        return _state_payload(run)

    @application.get("/takeoff", tags=["takeoff"])
    async def read_takeoff() -> dict[str, object]:
        """Pacote da rodada com a âncora de cada item declarada (`registered` | `raw`)."""
        packet, digest = run.require_packet()
        registered = _registered_item_ids(run)
        return {
            "packet": _anchored_packet(packet, registered),
            "packet_sha256": digest,
            **_anchor_counts(packet, registered),
        }

    @application.get("/images/plate", tags=["images"])
    async def read_plate_image() -> FileResponse:
        packet, _digest = run.require_packet()
        image_path = run.plate_image(packet)
        if image_path is None:
            raise LocalServerRefusal(
                404,
                ValuationValidationError(
                    "LOCAL_ARTIFACT_MISSING",
                    "imagem da prancha do pacote não está no diretório da rodada",
                    {
                        "artifact": PLATE_IMAGE_FILENAME,
                        "expected_image_sha256": packet.image_sha256,
                    },
                ),
            )
        return FileResponse(image_path, media_type="image/png", headers=_NO_STORE)

    @application.get("/images/overlay", tags=["images"])
    async def read_overlay_image() -> FileResponse:
        overlay_path = run.path(TAKEOFF_OVERLAY_FILENAME)
        if not overlay_path.is_file():
            raise _artifact_missing(TAKEOFF_OVERLAY_FILENAME)
        return FileResponse(overlay_path, media_type="image/png", headers=_NO_STORE)

    @application.post("/plates", status_code=202, tags=["plates"])
    async def upload_plate(file: Annotated[UploadFile, File()]) -> dict[str, object]:
        """Recebe o PDF do projetista, ingere a página 1 e dispara a extração paga.

        A resposta é o estado da rodada, devolvido **sem esperar** a chamada paga — quem
        acompanha é o `/state`. O ato de enviar é o consentimento do documento, e é por
        isso que não há segunda pergunta antes do gasto; o freio que continua de pé é o do
        servidor: sem teto de gasto configurado no ambiente, a prancha é ingerida e a
        extração fica `unavailable`, visível, sem nenhuma tentativa.

        A ingestão roda dentro da requisição de propósito: quando a resposta chega, a
        prancha já está na rodada e a tela pode mostrá-la mesmo que a extração falhe
        depois.
        """
        if run.read(TAKEOFF_PACKET_FILENAME) is not None:
            raise _round_already_has_plate("a rodada já tem pacote de takeoff publicado")
        if run.extraction.is_running():
            raise _round_already_has_plate("a rodada já tem uma prancha em processamento")
        payload = await _read_upload(file)
        manifest = _ingest_plate_upload(run, filename=file.filename, payload=payload)
        _trigger_extraction(run, manifest)
        return _state_payload(run)

    @application.post("/plates/extract", status_code=202, tags=["plates"])
    async def extract_plate() -> dict[str, object]:
        """Re-dispara a extração da prancha JÁ ingerida, com a mesma pré-checagem.

        Existe para que falha transitória do provider — ou servidor que subiu sem teto de
        gasto — não obrigue o orçamentista a reenviar o documento. Rodada que já publicou
        pacote não re-extrai: ela é a rodada de uma prancha só, e re-extrair apagaria a
        evidência sobre a qual as decisões estão sendo tomadas.
        """
        if run.read(TAKEOFF_PACKET_FILENAME) is not None:
            raise _round_already_has_plate("a rodada já tem pacote de takeoff publicado")
        manifest = run.plate_manifest()
        if manifest is None:
            raise _artifact_missing(PLATE_MANIFEST_FILENAME)
        if run.promoted_page(manifest) is None:
            raise _artifact_missing(manifest.pages[PLATE_PAGE_NUMBER - 1].render_file)
        unavailable = _trigger_extraction(run, manifest)
        if unavailable is not None:
            raise LocalServerRefusal(409, unavailable)
        return _state_payload(run)

    @application.post("/takeoff/decisions", tags=["takeoff"])
    async def decide_takeoff_item(payload: TakeoffDecisionRequest) -> dict[str, object]:
        """Aplica UMA decisão do orçamentista e republica pacote e overlay.

        A ordem é a de `cli._publish_takeoff`: o overlay é renderizado em memória antes de
        qualquer escrita, então uma recusa de digest ou de bbox deixa o diretório intacto.
        Falta da imagem da prancha **não** invalida a decisão — ela é registrada e o
        retorno declara que o overlay ficou para trás.
        """
        packet, digest = run.require_packet()
        _guard(TAKEOFF_PACKET_FILENAME, base=payload.base_packet_sha256, current=digest)
        decision = TakeoffDecisionInput(
            item_id=payload.item_id,
            action=payload.action,
            reviewer_id=run.reviewer_id,
            reviewer_role=REVIEWER_ROLE,
            decided_at=_now(),
            quantity=_parse_quantity(payload.quantity),
            unit=payload.unit,
            note=payload.note,
            item_note=payload.item_note,
        )
        reviewed = apply_takeoff_decisions(packet, TakeoffDecisionBatch(decisions=[decision]))
        image_path = run.plate_image(reviewed)
        overlay = None if image_path is None else render_takeoff_overlay(image_path, reviewed)

        document = _document(reviewed)
        atomic_write_text(run.path(TAKEOFF_PACKET_FILENAME), document)
        if overlay is not None:
            save_takeoff_overlay(overlay, run.path(TAKEOFF_OVERLAY_FILENAME))
        registered = _registered_item_ids(run)
        return {
            "packet": _anchored_packet(reviewed, registered),
            "packet_sha256": _digest_of(document),
            "review_status": _review_status(reviewed),
            "overlay_written": overlay is not None,
            "notes": [] if overlay is not None else [_OVERLAY_SKIPPED_NOTE],
            **_takeoff_counts(reviewed),
            **_anchor_counts(reviewed, registered),
        }

    @application.get("/suggestions", tags=["codes"])
    async def read_suggestions() -> dict[str, object]:
        """Shortlist dos itens confirmados; calculada uma vez e persistida.

        Ela só é calculada com a revisão do takeoff **completa**: computar sobre um pacote
        meio revisado congelaria em disco uma shortlist sem os itens que ainda vão ser
        confirmados, e a chamada seguinte devolveria esse artefato incompleto.

        Com índice, teto de gasto e credencial na rodada, a shortlist é a **híbrida** —
        fusão do braço léxico com a vizinhança semântica, amortecendo palavras de ESTADO da
        legenda (`default_legend_noise()`, rodada 2.2) — e embutir os rótulos custa uma
        chamada paga pequena, cacheada por rodada. Faltando qualquer um dos três, a
        shortlist é a lexical e o motivo viaja em `semantic_notes`. `matching` é derivado
        do `suggester_version` do próprio conjunto, então ele diz a verdade também quando a
        resposta vem do arquivo já gravado. Refino pago de ordem continua sendo comando do
        CLI; o que este servidor chama é a via de embeddings, e só ela.

        Esta rota **nunca recalcula** um artefato já gravado — ela só o serve. Recompute
        explícito, com guarda de digest-base e proteção do refino pago, é
        `POST /suggestions/recompute`.
        """
        existing = run.read(CODE_SUGGESTIONS_FILENAME)
        if existing is not None:
            suggestions = CodeSuggestionSet.model_validate_json(existing[0])
            return {
                "suggestions": suggestions.model_dump(mode="json"),
                "suggestions_sha256": existing[1],
                "computed": False,
                "matching": _matching_of(suggestions),
                "semantic_notes": [],
            }
        return _compute_suggestions_response(run)

    @application.post("/suggestions/recompute", tags=["codes"])
    async def recompute_suggestions(payload: SuggestionsRecomputeRequest) -> dict[str, object]:
        """Recomputa a shortlist do zero pelo algoritmo corrente, sobrescrevendo o arquivo.

        Guardas nesta ordem — digest primeiro, refino depois:

        1. Sem arquivo na rodada, um `base_suggestions_sha256` citado não tem contra o que
           conferir (`LOCAL_BASE_DIGEST_UNEXPECTED`).
        2. Arquivo presente exige o digest-base lido (`LOCAL_BASE_DIGEST_REQUIRED`), e
           digest divergente do atual é a mesma guarda otimista das outras mutações
           (`LOCAL_STATE_MOVED`).
        3. Só depois de o digest bater, um conjunto que já validou como refinado por
           provider pago (`suggester_version` terminado em `+llm-rerank-v1`) recusa
           (`LOCAL_SUGGESTIONS_REFINED`): recalcular descartaria o lineage da chamada paga,
           e refinar de novo é comando do CLI. Arquivo presente que não valida como
           `CodeSuggestionSet` — corrompido ou editado à mão — **não** cai nesta guarda: o
           recompute é a cura para ele, e a guarda de digest já protegeu a concorrência.

        Sem nenhuma recusa, sobrescreve via `atomic_write_text`, sem backup do artefato
        anterior.
        """
        existing = run.read(CODE_SUGGESTIONS_FILENAME)
        if existing is None and payload.base_suggestions_sha256 is not None:
            raise LocalServerRefusal(
                409,
                ValuationValidationError(
                    "LOCAL_BASE_DIGEST_UNEXPECTED",
                    "ainda não existe shortlist de sugestões; não há digest-base a citar",
                    {"artifact": CODE_SUGGESTIONS_FILENAME},
                ),
            )
        if existing is not None:
            if payload.base_suggestions_sha256 is None:
                raise LocalServerRefusal(
                    409,
                    ValuationValidationError(
                        "LOCAL_BASE_DIGEST_REQUIRED",
                        "já existe shortlist de sugestões; informe o digest-base lido",
                        {
                            "artifact": CODE_SUGGESTIONS_FILENAME,
                            "current_sha256": existing[1],
                        },
                    ),
                )
            _guard(
                CODE_SUGGESTIONS_FILENAME,
                base=payload.base_suggestions_sha256,
                current=existing[1],
            )
            try:
                suggestions = CodeSuggestionSet.model_validate_json(existing[0])
            except ValidationError:
                suggestions = None
            if suggestions is not None and suggestions.suggester_version.endswith(
                LLM_RERANK_SUFFIX
            ):
                raise LocalServerRefusal(
                    409,
                    ValuationValidationError(
                        "LOCAL_SUGGESTIONS_REFINED",
                        "a shortlist já carrega refino pago; recalcular descartaria o "
                        "lineage da chamada. Refine de novo pelo CLI (`suggest-codes "
                        "--refine-arm`).",
                        {"suggester_version": suggestions.suggester_version},
                    ),
                )
        return _compute_suggestions_response(run)

    @application.get("/catalog/search", tags=["codes"])
    async def search_catalog(
        q: Annotated[str, Query(min_length=1, max_length=200)],
        limit: Annotated[
            int, Query(ge=1, le=CATALOG_SEARCH_MAX_LIMIT)
        ] = CATALOG_SEARCH_DEFAULT_LIMIT,
        arm: Annotated[Literal["auto", "lexical"], Query()] = "auto",
    ) -> dict[str, object]:
        """Busca no catálogo, híbrida quando a rodada tem índice, teto de gasto e credencial.

        Consulta nova custa uma chamada paga pequena, cacheada por rodada; consulta
        repetida não custa nada. Qualquer impedimento do braço semântico degrada a busca
        para o léxico **na própria resposta** (`matching` e `semantic_notes`), nunca em
        erro e nunca em silêncio.

        `arm=lexical` fixa o braço léxico puro: nenhum vetor é resolvido, nenhuma chamada
        de embedding acontece e `query-cache.json` não é tocado, mesmo com índice, teto de
        gasto e credencial disponíveis — o motivo vai em `semantic_notes`. Sem `arm` (ou
        `arm=auto`), o comportamento é o de sempre.
        """
        catalog = run.require_catalog()
        _require_query_terms(q)
        if arm == "lexical":
            return _catalog_search(
                catalog,
                q,
                limit,
                run.synonyms(),
                noise=default_legend_noise(),
                semantic=None,
                query_vec=None,
                semantic_warning=SEMANTIC_NOT_REQUESTED_MESSAGE,
            )
        semantic = _semantic_state(run, catalog)
        vector, warning = _semantic_query_vector(run, semantic, q)
        return _catalog_search(
            catalog,
            q,
            limit,
            run.synonyms(),
            noise=default_legend_noise(),
            semantic=semantic,
            query_vec=vector,
            semantic_warning=warning,
        )

    @application.get("/codes", tags=["codes"])
    async def read_codes() -> dict[str, object]:
        packet, _digest = run.require_packet()
        assignments_found = run.assignments()
        assignment_set = None if assignments_found is None else assignments_found[0]
        return {
            "assignments": (
                None if assignment_set is None else assignment_set.model_dump(mode="json")
            ),
            "assignments_sha256": None if assignments_found is None else assignments_found[1],
            "confirmed": (
                0 if assignment_set is None else _count_status(assignment_set, "confirmed")
            ),
            "rejected": (
                0 if assignment_set is None else _count_status(assignment_set, "rejected")
            ),
            "pending_items": [
                _item_payload(item) for item in _pending_code_items(packet, assignment_set)
            ],
        }

    @application.post("/codes/decisions", tags=["codes"])
    async def decide_item_code(payload: CodeDecisionRequest) -> dict[str, object]:
        """Confirma ou rejeita o código de UM item, acumulando sobre o conjunto anterior.

        Acumular item a item é a semântica do `--previous` do `confirm-codes`: o domínio
        recusa re-decisão (`ASSIGNMENT_ITEM_ALREADY_DECIDED`) e é ele quem carrega adiante
        as confirmações já registradas.
        """
        packet, _digest = run.require_packet()
        assignments_found = run.assignments()
        if assignments_found is None and payload.base_assignments_sha256 is not None:
            raise LocalServerRefusal(
                409,
                ValuationValidationError(
                    "LOCAL_BASE_DIGEST_UNEXPECTED",
                    "ainda não existe conjunto de confirmações; não há digest-base a citar",
                    {"artifact": CODE_ASSIGNMENTS_FILENAME},
                ),
            )
        if assignments_found is not None:
            if payload.base_assignments_sha256 is None:
                raise LocalServerRefusal(
                    409,
                    ValuationValidationError(
                        "LOCAL_BASE_DIGEST_REQUIRED",
                        "já existe conjunto de confirmações; informe o digest-base lido",
                        {
                            "artifact": CODE_ASSIGNMENTS_FILENAME,
                            "current_sha256": assignments_found[1],
                        },
                    ),
                )
            _guard(
                CODE_ASSIGNMENTS_FILENAME,
                base=payload.base_assignments_sha256,
                current=assignments_found[1],
            )

        catalog = run.require_catalog()
        batch = CodeAssignmentBatch(
            assignments=[
                CodeAssignmentInput(
                    item_id=payload.item_id,
                    action=payload.action,
                    code=payload.code,
                    reviewer_id=run.reviewer_id,
                    reviewer_role=REVIEWER_ROLE,
                    decided_at=_now(),
                    note=payload.note,
                )
            ]
        )
        assignments = apply_code_assignments(
            packet,
            batch,
            catalog,
            run.contract(),
            previous=None if assignments_found is None else assignments_found[0],
        )
        document = _document(assignments)
        atomic_write_text(run.path(CODE_ASSIGNMENTS_FILENAME), document)
        return {
            "assignments": assignments.model_dump(mode="json"),
            "assignments_sha256": _digest_of(document),
            "confirmed": _count_status(assignments, "confirmed"),
            "rejected": _count_status(assignments, "rejected"),
            "pending_items": [
                _item_payload(item) for item in _pending_code_items(packet, assignments)
            ],
        }

    @application.post("/calc/build", tags=["bulletin"])
    async def build_calc(payload: CalcBuildRequest) -> dict[str, object]:
        """Monta boletim e memória da obra e grava a medição **sem aprovação**.

        Aprovação nominal e exportação continuam sendo atos do CLI, atrás do portão de
        saldo e contrato. `calc-plan.json` entra se estiver na rodada; sem ele cada item
        recebe o bloco de quantidade direta que o domínio gera.
        """
        packet, _digest = run.require_packet()
        assignments_found = run.assignments()
        if assignments_found is None:
            raise _artifact_missing(CODE_ASSIGNMENTS_FILENAME)
        catalog = run.require_catalog()
        valuation = build_worksite_valuation(
            packet,
            assignments_found[0],
            catalog,
            worksite_key=payload.worksite_key,
            worksite_name=payload.worksite_name,
            period_number=payload.period_number,
            reference_label=payload.reference_label,
            address=payload.address,
            contract_label=payload.contract_label,
            calc_plan=run.calc_plan(),
        )
        document = _document(valuation)
        atomic_write_text(run.path(VALUATION_FILENAME), document)
        return {
            "valuation": valuation.model_dump(mode="json"),
            "valuation_sha256": _digest_of(document),
            "total_amount": str(valuation.total_amount),
        }

    @application.get("/bulletin", tags=["bulletin"])
    async def read_bulletin() -> dict[str, object]:
        """Medição gravada, revalidada na leitura: totais recomputados pelos validadores do
        modelo. Arquivo que não passa é 422 — a tela nunca renderiza medição inválida."""
        text, digest = run.require(VALUATION_FILENAME)
        valuation = Valuation.model_validate_json(text)
        return {
            "valuation": valuation.model_dump(mode="json"),
            "valuation_sha256": digest,
            "total_amount": str(valuation.total_amount),
        }

    return application


def run_local_server(application: FastAPI, *, host: str, port: int) -> None:
    """Sobe o servidor. `uvicorn` registra método, rota, status e duração — nunca conteúdo
    de artefato: as rotas não carregam descrição, quantidade nem identificador de cliente."""
    uvicorn.run(application, host=host, port=port, log_level="info")
