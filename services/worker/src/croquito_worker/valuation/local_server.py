"""Servidor de homologação da medição: HTTP fino sobre o domínio fail-closed.

Ele existe para que o ato do orçamentista — revisar o takeoff, confirmar código, montar o
boletim — aconteça numa tela em vez de num lote de JSON escrito à mão. Nenhuma regra de
negócio nova mora aqui: cada rota carrega os artefatos que o CLI gravou, chama a MESMA
função de domínio que o comando equivalente chama (`apply_takeoff_decisions`,
`build_code_suggestions`, `apply_code_assignments`, `build_worksite_valuation`) e publica
o resultado com os mesmos nomes de arquivo e a mesma escrita atômica. Recusa do domínio
atravessa intacta, com o código estável, e **não** grava artefato — como no CLI.

O que mora aqui é o ADAPTADOR DE DISCO da rodada: `_Run` (os nomes padrão dos artefatos),
as recusas com status HTTP, o disparo da extração paga e as rotas. A lógica que não
depende do diretório saiu para módulos próprios, para poder ser reusada pela migração da
medição para a API `/v1` (ADR-0028) sem arrastar o servidor junto: `round_view` (payloads
sobre os modelos), `catalog_search` (busca no catálogo), `round_extraction` (upload,
ingestão e extração paga sobre um `workdir`) e `suggestions` (cálculo da shortlist).
Nenhum deles importa `fastapi` nem conhece `_Run`.

Um modo só: `create_local_app` é o servidor **local** do ADR-0020, da família do `parity`
— bind padrão em `127.0.0.1`, CORS restrito à UI local e **sem autenticação**. A identidade
do revisor vem da flag de inicialização (`--reviewer`), não de token: quem sobe o processo
declara quem está decidindo. Expor esta porta em outra interface publica uma ferramenta sem
autenticação, e por isso o CLI avisa.

Houve um segundo modo, hospedado e autenticado (ADR-0026), que serviu de ponte enquanto a
medição não tinha rotas `/v1`. Ele foi removido com a migração (ADR-0028): quem sobe fora da
máquina do operador é a API autenticada, não este servidor.

Limites declarados, não escondidos:
- Chama provider em **uma** operação e só nela: a extração da legenda que o upload da
  prancha dispara (`POST /plates`), por decisão registrada do usuário em 2026-08-13. Os
  freios do CLI continuam todos de pé — teto de gasto obrigatório por variável de ambiente
  do processo (sem teto a extração fica `unavailable` e visível, e **nunca** é tentada),
  braço fixado no vencedor da eval paga, lineage e custo gravados na rodada, falha exibida
  no estado em vez de silêncio. O que muda é a FORMA do consentimento: no CLI ele é a
  allowlist de digests que o operador declara; aqui é o próprio ato de subir o PDF na tela,
  com o digest do arquivo enviado registrado no estado e no `extraction-lineage.json`
  (ver `round_extraction.authorize_uploaded_page`). Refino pago de código continua fora
  daqui: é comando do CLI.
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
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Final, Literal

import uvicorn
from fastapi import APIRouter, FastAPI, File, Query, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.requests import Request

from croquito_valuation.amendment_dossier import AmendmentDossier, build_amendment_dossier
from croquito_valuation.assignment import (
    LLM_RERANK_SUFFIX,
    CodeAssignmentBatch,
    CodeAssignmentInput,
    CodeAssignmentSet,
    CodeSuggestionSet,
    ItemPackageClosureInput,
    apply_code_assignments,
)
from croquito_valuation.calc import CalcPlan, build_worksite_valuation
from croquito_valuation.catalog import (
    DomainSynonyms,
    default_legend_noise,
    file_sha256,
)
from croquito_valuation.contract import ContractWorkbook
from croquito_valuation.errors import ValuationValidationError, valuation_errors
from croquito_valuation.models import SHA256_PATTERN, PriceCatalog, Valuation
from croquito_valuation.takeoff import (
    TakeoffDecisionBatch,
    TakeoffDecisionInput,
    TakeoffPacket,
    apply_takeoff_decisions,
)
from croquito_worker.extraction_eval import ExtractionNotAllowlistedError
from croquito_worker.ingest import PdfManifest
from croquito_worker.io_utils import atomic_write_text
from croquito_worker.providers import ProviderAdapter, ProviderExecutionError
from croquito_worker.valuation.catalog_search import (
    CATALOG_SEARCH_DEFAULT_LIMIT,
    CATALOG_SEARCH_MAX_LIMIT,
    SEMANTIC_AVAILABLE_MESSAGE,
    SEMANTIC_LIMITED_MESSAGE,
    SEMANTIC_UNAVAILABLE_MESSAGE,
    SemanticArm,
)
from croquito_worker.valuation.catalog_search import (
    require_query_terms as _require_query_terms,
)
from croquito_worker.valuation.catalog_search import (
    search_catalog as _catalog_search,
)
from croquito_worker.valuation.cli import (
    AMENDMENT_DOSSIER_FILENAME,
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
from croquito_worker.valuation.legend_extraction import LegendExtractionResult
from croquito_worker.valuation.plate import PLATE_IMAGE_FILENAME
from croquito_worker.valuation.round_extraction import (
    ARM_UNAVAILABLE_MESSAGE,
    MAX_PLATE_PDF_BYTES,
    PLATE_PAGE_NUMBER,
    extract_legend_from_upload,
    ingest_plate_upload,
    upload_invalid,
)

# Reexportados com nome explícito: são os nomes que o CLI, os testes e a UI já liam deste
# módulo antes de a ingestão da prancha virar `round_extraction`.
from croquito_worker.valuation.round_extraction import (
    MEDICAO_EXTRACTION_ARM as MEDICAO_EXTRACTION_ARM,
)
from croquito_worker.valuation.round_extraction import (
    PLATE_MANIFEST_FILENAME as PLATE_MANIFEST_FILENAME,
)
from croquito_worker.valuation.round_extraction import (
    PLATE_PDF_FILENAME as PLATE_PDF_FILENAME,
)
from croquito_worker.valuation.round_extraction import (
    build_extraction_adapter as _build_extraction_adapter,
)
from croquito_worker.valuation.round_extraction import (
    execution_payload as _execution_payload,
)
from croquito_worker.valuation.round_extraction import (
    extraction_arm_spec as _extraction_arm_spec,
)
from croquito_worker.valuation.round_extraction import (
    extraction_reserve_arm_spec as _extraction_reserve_arm_spec,
)
from croquito_worker.valuation.round_extraction import (
    extraction_unavailable as _extraction_unavailable,
)
from croquito_worker.valuation.round_extraction import (
    registration_payload as _registration_payload,
)
from croquito_worker.valuation.round_view import (
    REVIEWER_ID_MAX_LENGTH as REVIEWER_ID_MAX_LENGTH,
)
from croquito_worker.valuation.round_view import REVIEWER_ROLE as REVIEWER_ROLE
from croquito_worker.valuation.round_view import anchor_counts as _anchor_counts
from croquito_worker.valuation.round_view import anchored_packet as _anchored_packet
from croquito_worker.valuation.round_view import count_status as _count_status
from croquito_worker.valuation.round_view import item_payload as _item_payload
from croquito_worker.valuation.round_view import matching_of as _matching_of
from croquito_worker.valuation.round_view import parse_quantity as _parse_quantity
from croquito_worker.valuation.round_view import pending_code_items as _pending_code_items
from croquito_worker.valuation.round_view import registered_item_ids
from croquito_worker.valuation.round_view import review_status as _review_status
from croquito_worker.valuation.round_view import takeoff_counts as _takeoff_counts
from croquito_worker.valuation.sco_matching import (
    CATALOG_INDEX_FILENAME,
    QUERY_CACHE_FILENAME,
    SEMANTIC_DEGRADABLE_CODES,
    SemanticIndex,
    bind_index_to_catalog,
    embeddings_adapter_or_reason,
    load_semantic_index,
    normalize_query_text,
    read_catalog_index,
    resolve_query_vectors,
)
from croquito_worker.valuation.suggestions import compute_suggestions, require_reviewed_takeoff
from croquito_worker.valuation.takeoff_overlay import (
    render_takeoff_overlay,
    save_takeoff_overlay,
)

LOCAL_SERVER_VERSION: Final = "local-valuation-server-v1"

LOCAL_WEB_ORIGINS: Final[tuple[str, ...]] = (
    "http://localhost:5174",
    "http://127.0.0.1:5174",
)
"""Origens da UI local de homologação (Fase B). Nada além delas fala com este servidor."""

_OVERLAY_SKIPPED_NOTE: Final = (
    "overlay não regravado: a imagem da prancha do pacote não está no diretório da "
    "rodada; um overlay antigo, se existir, está desatualizado."
)

_NO_STORE: Final = {"Cache-Control": "no-store"}
"""Overlay e prancha mudam a cada decisão; cache de navegador mostraria estado velho."""

EXTRACTION_LINEAGE_FILENAME: Final = "extraction-lineage.json"
"""Lineage local da chamada paga: provider, modelo, prompt, tokens, custo e consentimento."""

ExtractionStatus = Literal["idle", "running", "done", "failed", "unavailable"]
"""Etapa `extracao` do estado. `unavailable` é servidor sem teto/credencial — nunca
chamou; `failed` é chamada que aconteceu e não fechou. Os dois são visíveis na tela."""

_EXTRACTION_MESSAGES: Final[Mapping[str, str]] = {
    "no_plate": "nenhuma prancha enviada nesta rodada",
    "ingested": "prancha ingerida; a extração automática ainda não foi disparada",
    "running": "extração automática em andamento; chamada paga configurada no servidor",
    "done": "extração concluída; todo item nasce para a revisão do orçamentista",
}

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
    """Arquivo que não é prancha: recusado antes de qualquer escrita ou renderização.

    A recusa é a MESMA que a ingestão levanta (`round_extraction.upload_invalid`), só que
    embrulhada no envelope do servidor. Os dois desfechos são idênticos no fio — 422,
    `application/problem+json`, mesmo `code`, `detail` e `details` —, porque o handler de
    `ValuationValidationError` deste app responde exatamente como o de recusa.
    """
    return LocalServerRefusal(422, upload_invalid(reason, details))


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


class ItemPackageClosureRequest(_LocalRequest):
    """Pedido de fechamento do pacote de serviços de um item.

    Mesmo protocolo de digest-base de `CodeDecisionRequest`: o fechamento acumula sobre o
    conjunto anterior e por isso precisa citar o que leu.
    """

    item_id: str
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


def _registration_report(run: _Run) -> Mapping[str, Any] | None:
    """Relatório do registro fino da rodada, ou `None` quando não há um legível.

    Ilegível conta como ausente de propósito: quem decide o que fazer com a falta é
    `round_view.registered_item_ids`, e lá a resposta é fail-closed — nenhum item ganha
    âncora declarada confiável.
    """
    found = run.read(TAKEOFF_REGISTRATION_REPORT_FILENAME)
    if found is None:
        return None
    try:
        report = json.loads(found[0])
    except json.JSONDecodeError:
        return None
    return report if isinstance(report, dict) else None


def _registered_item_ids(run: _Run) -> frozenset[str]:
    """Itens ancorados com garantia nesta rodada; adaptador de disco de `round_view`."""
    return registered_item_ids(_registration_report(run))


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
    """Identidade fixa de quem decide durante toda a vida do processo (ADR-0020).

    Ela é do PROCESSO, não da requisição: quem sobe o servidor declara quem está decidindo
    (`--reviewer`), e trocar de revisor é subir outro processo."""

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
            if candidate != named and _digest_of_settled_file(candidate) == packet.image_sha256
        ]
        return matches[0] if len(matches) == 1 else None


def _digest_of_settled_file(candidate: Path) -> str | None:
    """Digest do arquivo, ou `None` quando ele não é um arquivo publicado.

    Duas armadilhas concretas, e as duas já morderam:

    1. **`Path.glob` não é o glob do shell.** O `*` do `pathlib` casa arquivo começado por
       ponto, e o escritor atômico de overlay (`save_takeoff_overlay`) cria exatamente
       `.{stem}.xxxxxx.png` antes do `os.replace`. Sem filtrar, a listagem enxerga o
       temporário de outra thread.
    2. **O temporário some entre listar e ler.** Mesmo filtrando, qualquer arquivo pode
       desaparecer nesse intervalo, e um `FileNotFoundError` aqui derrubava a rodada
       inteira por causa de uma corrida com uma publicação alheia.

    Arquivo que sumiu ou que ainda está sendo escrito nunca é a evidência de um takeoff
    publicado — a evidência é estável por construção. Devolver `None` é dizer isso, em vez
    de tratar a corrida como erro de domínio.
    """
    if candidate.name.startswith("."):
        return None
    try:
        return file_sha256(candidate)
    except OSError:
        return None


SEMANTIC_NOT_REQUESTED_MESSAGE: Final = (
    "busca semântica não solicitada nesta consulta (arm=lexical)"
)
"""Nota de `GET /catalog/search?arm=lexical`: o braço fixável pede explicitamente o
léxico puro, então nenhum vetor é resolvido — zero chamada de embedding e zero escrita
de `query-cache.json`, mesmo quando a rodada tem índice, teto de gasto e credencial."""


def _semantic_state(run: _Run, catalog: PriceCatalog) -> SemanticArm:
    """Índice e via de embeddings da rodada, com o motivo quando algum deles falta.

    Índice ilegível ou de outro catálogo **não** derruba a tela: vira indisponibilidade
    declarada, com o código de domínio no motivo. A recusa fechada de verdade acontece no
    CLI, que é quem publica artefato; aqui o custo de recusar seria o orçamentista sem
    busca nenhuma por causa de um arquivo velho no diretório.
    """
    index_path = run.path(CATALOG_INDEX_FILENAME)
    if not index_path.is_file():
        return SemanticArm(None, None, "unavailable", f"{SEMANTIC_UNAVAILABLE_MESSAGE}: sem índice")
    try:
        index = run.index_cache.load(index_path, catalog)
    except (ValuationValidationError, ValidationError) as error:
        domain = error if isinstance(error, ValuationValidationError) else _domain_error(error)
        return SemanticArm(
            None,
            None,
            "unavailable",
            f"{SEMANTIC_UNAVAILABLE_MESSAGE}: índice recusado ({domain.code})",
        )
    adapter, reason = embeddings_adapter_or_reason()
    if adapter is None:
        return SemanticArm(index, None, "limited", f"{SEMANTIC_LIMITED_MESSAGE}: {reason}")
    return SemanticArm(
        index, adapter, "available", f"{SEMANTIC_AVAILABLE_MESSAGE}: {index.model_id}"
    )


def _semantic_query_vector(
    run: _Run, semantic: SemanticArm, query: str
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


# --------------------------------------------------------------------------------------
# Prancha do projetista: upload, ingestão local e extração paga automática
# --------------------------------------------------------------------------------------

_MULTI_PAGE_NOTE: Final = (
    "PDF com {pages} páginas: só a página 1 virou prancha desta rodada; as demais não "
    "foram lidas nem enviadas"
)


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


def _extraction_reserve_adapter() -> ProviderAdapter | None:
    """Braço de reserva deste servidor, ou `None` — que é o padrão, sem a env declarada.

    Passa pelo MESMO `_build_extraction_adapter` do braço primário de propósito: é o seam
    que a suíte troca, então a reserva também nunca chama nada externo em teste, e as
    recusas do braço (forma inválida, `fixture`, teto de gasto ou credencial ausente)
    valem iguais para ela.
    """
    arm_spec = _extraction_reserve_arm_spec()
    if arm_spec is None:
        return None
    _name, _model_id, adapter = _build_extraction_adapter(arm_spec)
    return adapter


def _extract_legend_from_upload(
    run: _Run,
    manifest: PdfManifest,
    adapter: ProviderAdapter,
    reserve: ProviderAdapter | None = None,
) -> LegendExtractionResult:
    """Extração da legenda da prancha consentida, no diretório desta rodada.

    Adaptador de disco de `round_extraction.extract_legend_from_upload`, que não conhece a
    rodada do servidor. O nome privado continua aqui porque é o seam que a suíte troca:
    nenhuma chamada externa acontece nos testes.
    """
    return extract_legend_from_upload(run.root, manifest, adapter, reserve)


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
    run: _Run,
    manifest: PdfManifest,
    adapter: ProviderAdapter,
    arm_spec: str,
    reserve: ProviderAdapter | None = None,
) -> None:
    """Corpo da thread de extração: sempre termina com um desfecho declarado.

    Ela não levanta para fora: qualquer exceção vira estado `failed` no `/state`. Falha
    não publica artefato nenhum, e PDF, PNG e manifest continuam na rodada — é isso que
    permite `POST /plates/extract` re-tentar sem reenviar o documento.
    """
    consented = manifest.source_sha256
    try:
        result = _extract_legend_from_upload(run, manifest, adapter, reserve)
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
        # A reserva é montada ANTES da thread, pelo mesmo motivo do braço primário: uma
        # reserva mal declarada tem de aparecer como `unavailable` na tela agora, enquanto
        # o operador ainda pode corrigir a variável, e não no meio de uma degradação.
        reserve = _extraction_reserve_adapter()
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
                ARM_UNAVAILABLE_MESSAGE,
                {"arm": arm_spec, "error": type(error).__name__},
            ),
            manifest,
        )
    if not run.extraction.claim(consented_source_sha256=manifest.source_sha256):
        raise _extraction_busy()
    threading.Thread(
        target=_run_extraction,
        args=(run, manifest, adapter, arm_spec, reserve),
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

CATALOG_SOURCE_ENV: Final = "CROQUITO_MEDICAO_CATALOG"
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

    O `reviewer_id` exibido é o do processo: a tela mostra quem vai assinar a próxima
    decisão, e neste servidor quem assina é quem subiu o processo (`--reviewer`).

    O `valuation.json` entra aqui só por presença e digest: revalidá-lo é papel do
    `GET /bulletin`, e uma medição ilegível não pode derrubar a tela inteira antes de o
    orçamentista sequer chegar nela.
    """
    packet_found = run.read(TAKEOFF_PACKET_FILENAME)
    packet = None if packet_found is None else TakeoffPacket.model_validate_json(packet_found[0])
    assignments_found = run.assignments()
    suggestions_digest = run.digest(CODE_SUGGESTIONS_FILENAME)
    valuation_digest = run.digest(VALUATION_FILENAME)
    dossier_digest = run.digest(AMENDMENT_DOSSIER_FILENAME)

    artifacts: dict[str, str] = {}
    for filename in (
        TAKEOFF_PACKET_FILENAME,
        CATALOG_FILENAME,
        CONTRACT_FILENAME,
        CODE_SUGGESTIONS_FILENAME,
        CODE_ASSIGNMENTS_FILENAME,
        CALC_PLAN_FILENAME,
        VALUATION_FILENAME,
        AMENDMENT_DOSSIER_FILENAME,
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
        "dossier": {"present": dossier_digest is not None, "dossier_sha256": dossier_digest},
    }


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
    congelaria em disco uma shortlist sem os itens que ainda vão ser confirmados. A guarda
    é conferida aqui, antes de carregar catálogo e contrato, para que a recusa que o
    orçamentista vê seja a revisão incompleta — e não a falta de outro artefato.
    """
    packet, _digest = run.require_packet()
    require_reviewed_takeoff(packet)
    catalog = run.require_catalog()
    computed, notes = compute_suggestions(
        packet,
        catalog,
        run.contract(),
        run.synonyms(),
        semantic=_semantic_state(run, catalog),
        query_cache_path=run.path(QUERY_CACHE_FILENAME),
    )
    document = _document(computed)
    atomic_write_text(run.path(CODE_SUGGESTIONS_FILENAME), document)
    return {
        "suggestions": computed.model_dump(mode="json"),
        "suggestions_sha256": _digest_of(document),
        "computed": True,
        "matching": _matching_of(computed),
        "semantic_notes": notes,
    }


def _round_root(root: Path) -> Path:
    """Diretório da rodada, resolvido e conferido; ausência recusa antes de qualquer rota."""
    resolved = root.expanduser().resolve()
    if not resolved.is_dir():
        raise ValuationValidationError(
            "LOCAL_ROOT_MISSING",
            "diretório da rodada não existe; aponte --root para a saída de um comando",
            {"root": str(resolved)},
        )
    return resolved


def _build_app(run: _Run, *, origins: Sequence[str]) -> FastAPI:
    """Monta o app e as rotas sobre um diretório de rodada já resolvido.

    `origins` alimenta o CORS: só a UI local fala com esta porta. Não há segunda porta de
    entrada e não há sessão — quem decide é a identidade do processo (`run.reviewer_id`), e
    é dela que sai todo `reviewer_id` carimbado.
    """
    application = FastAPI(
        title="Croquito — homologação local da medição",
        version="0.1.0",
        description=(
            "Ferramenta LOCAL de homologação: sem autenticação, sem provider e sem AWS. "
            "Serve e muta os artefatos de um diretório de rodada pelas mesmas funções de "
            "domínio que o CLI `croquito-valuation` usa."
        ),
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(origins),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    router = APIRouter()

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

    @router.get("/state", tags=["state"])
    async def read_state() -> dict[str, object]:
        return _state_payload(run)

    @router.get("/takeoff", tags=["takeoff"])
    async def read_takeoff() -> dict[str, object]:
        """Pacote da rodada com a âncora de cada item declarada (`registered` | `raw`)."""
        packet, digest = run.require_packet()
        registered = _registered_item_ids(run)
        return {
            "packet": _anchored_packet(packet, registered),
            "packet_sha256": digest,
            **_anchor_counts(packet, registered),
        }

    @router.get("/images/plate", tags=["images"])
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

    @router.get("/images/overlay", tags=["images"])
    async def read_overlay_image() -> FileResponse:
        overlay_path = run.path(TAKEOFF_OVERLAY_FILENAME)
        if not overlay_path.is_file():
            raise _artifact_missing(TAKEOFF_OVERLAY_FILENAME)
        return FileResponse(overlay_path, media_type="image/png", headers=_NO_STORE)

    @router.post("/plates", status_code=202, tags=["plates"])
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
        manifest = ingest_plate_upload(run.root, filename=file.filename, payload=payload)
        _trigger_extraction(run, manifest)
        return _state_payload(run)

    @router.post("/plates/extract", status_code=202, tags=["plates"])
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

    @router.post("/takeoff/decisions", tags=["takeoff"])
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

    @router.get("/suggestions", tags=["codes"])
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

    @router.post("/suggestions/recompute", tags=["codes"])
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

    @router.get("/catalog/search", tags=["codes"])
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

    @router.get("/codes", tags=["codes"])
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

    def _guarded_assignments(base: str | None) -> tuple[CodeAssignmentSet, str] | None:
        """Conjunto corrente, conferido contra o digest-base que o cliente diz ter lido.

        Compartilhado pelos dois atos que acumulam sobre ele — a decisão de código e o
        fechamento de pacote —, porque o protocolo de concorrência é o mesmo: quem escreve
        precisa provar que leu a versão que está lá.
        """
        found = run.assignments()
        if found is None and base is not None:
            raise LocalServerRefusal(
                409,
                ValuationValidationError(
                    "LOCAL_BASE_DIGEST_UNEXPECTED",
                    "ainda não existe conjunto de confirmações; não há digest-base a citar",
                    {"artifact": CODE_ASSIGNMENTS_FILENAME},
                ),
            )
        if found is not None:
            if base is None:
                raise LocalServerRefusal(
                    409,
                    ValuationValidationError(
                        "LOCAL_BASE_DIGEST_REQUIRED",
                        "já existe conjunto de confirmações; informe o digest-base lido",
                        {
                            "artifact": CODE_ASSIGNMENTS_FILENAME,
                            "current_sha256": found[1],
                        },
                    ),
                )
            _guard(CODE_ASSIGNMENTS_FILENAME, base=base, current=found[1])
        return found

    def _assignments_response(
        packet: TakeoffPacket, assignments: CodeAssignmentSet, document: str
    ) -> dict[str, object]:
        return {
            "assignments": assignments.model_dump(mode="json"),
            "assignments_sha256": _digest_of(document),
            "confirmed": _count_status(assignments, "confirmed"),
            "rejected": _count_status(assignments, "rejected"),
            "closed": len(assignments.closed_item_ids()),
            "pending_items": [
                _item_payload(item) for item in _pending_code_items(packet, assignments)
            ],
        }

    @router.post("/codes/decisions", tags=["codes"])
    async def decide_item_code(payload: CodeDecisionRequest) -> dict[str, object]:
        """Confirma ou rejeita o código de UM item, acumulando sobre o conjunto anterior.

        Acumular item a item é a semântica do `--previous` do `confirm-codes`: o domínio
        recusa re-decisão (`ASSIGNMENT_ITEM_ALREADY_DECIDED`) e é ele quem carrega adiante
        as confirmações já registradas.
        """
        packet, _digest = run.require_packet()
        assignments_found = _guarded_assignments(payload.base_assignments_sha256)

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
        return _assignments_response(packet, assignments, document)

    @router.post("/codes/closures", tags=["codes"])
    async def close_item_package(payload: ItemPackageClosureRequest) -> dict[str, object]:
        """Declara COMPLETO o pacote de serviços de um item.

        O irmão local da rota `/v1/.../code-assignments/closures`, pelo mesmo motivo: com a
        cardinalidade N:N, confirmar um código não diz que o elemento acabou, e sem este ato
        `calc/build` recusaria em `CALC_PACKAGE_NOT_CLOSED`. Rejeição fecha o item sozinha.
        """
        packet, _digest = run.require_packet()
        assignments_found = _guarded_assignments(payload.base_assignments_sha256)
        catalog = run.require_catalog()
        batch = CodeAssignmentBatch(
            closures=[
                ItemPackageClosureInput(
                    item_id=payload.item_id,
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
        return _assignments_response(packet, assignments, document)

    @router.post("/calc/build", tags=["bulletin"])
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

    @router.get("/bulletin", tags=["bulletin"])
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

    @router.post("/dossier/build", tags=["bulletin"])
    async def build_dossier() -> dict[str, object]:
        """Monta o dossiê do aditivo a partir do takeoff confirmado e das confirmações de código.

        Espelho de `POST /calc/build`: o dossiê é o outro artefato de FECHAMENTO da rodada,
        nascido dos MESMOS dois artefatos-base (`takeoff-packet.json`,
        `code-assignments.json`). Ele nunca precifica e nunca cria ou altera
        `Amendment`/RE-RA (ADR-0018, leitura apenas). Como `POST /calc/build`, esta rota
        não tem guarda de digest-base própria: ela sempre reconstrói do estado ATUAL dos
        dois artefatos de origem, os mesmos que o boletim já lê sem guarda — recalcular
        sobrescreve `amendment-dossier.json` com o resultado corrente.
        """
        packet, _digest = run.require_packet()
        assignments_found = run.assignments()
        if assignments_found is None:
            raise _artifact_missing(CODE_ASSIGNMENTS_FILENAME)
        dossier = build_amendment_dossier(packet, assignments_found[0])
        document = _document(dossier)
        atomic_write_text(run.path(AMENDMENT_DOSSIER_FILENAME), document)
        return {
            "dossier": dossier.model_dump(mode="json"),
            "dossier_sha256": _digest_of(document),
            "item_count": len(dossier.items),
        }

    @router.get("/dossier", tags=["bulletin"])
    async def read_dossier() -> dict[str, object]:
        """Dossiê gravado, revalidado na leitura: espelho de `GET /bulletin`.

        Arquivo que não passa na revalidação é 422 — a tela nunca renderiza dossiê
        inválido; ausente é 404, como todo artefato de entrada desta rodada.
        """
        text, digest = run.require(AMENDMENT_DOSSIER_FILENAME)
        dossier = AmendmentDossier.model_validate_json(text)
        return {
            "dossier": dossier.model_dump(mode="json"),
            "dossier_sha256": digest,
            "item_count": len(dossier.items),
        }

    application.include_router(router)
    return application


def create_local_app(root: Path, reviewer_id: str) -> FastAPI:
    """Monta o servidor local sobre um diretório de rodada já produzido pelo CLI.

    `reviewer_id` é a identidade de quem decide durante toda a vida do processo: ela entra
    em cada `ReviewerDecision` gravada, ao lado do relógio do servidor. Trocar de revisor é
    subir outro processo, não mandar outro campo.
    """
    resolved = _round_root(root)
    cleaned_reviewer = reviewer_id.strip()
    if not 1 <= len(cleaned_reviewer) <= REVIEWER_ID_MAX_LENGTH:
        raise ValuationValidationError(
            "LOCAL_REVIEWER_INVALID",
            "identidade do revisor deve ter de 1 a 120 caracteres",
            {"length": len(cleaned_reviewer)},
        )
    run = _Run(root=resolved, reviewer_id=cleaned_reviewer)
    # A identidade é do PROCESSO: ela não olha a requisição, e é por isso que expor esta
    # porta fora de 127.0.0.1 faz o servidor avisar (`LOCAL_SERVER_EXPOSED`).
    return _build_app(run, origins=LOCAL_WEB_ORIGINS)


def run_local_server(application: FastAPI, *, host: str, port: int) -> None:
    """Sobe o servidor. `uvicorn` registra método, rota, status e duração — nunca conteúdo
    de artefato: as rotas não carregam descrição, quantidade nem identificador de cliente."""
    uvicorn.run(application, host=host, port=port, log_level="info")
