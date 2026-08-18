"""Núcleo de aplicação da rodada de medição: o que a rota decide antes de existir HTTP.

Este módulo é a camada de aplicação de `/v1/valuation-rounds` (ADR-0028) **sem** FastAPI:
nada aqui recebe `Request`, monta `Response` ou conhece código de status por si só. O que
mora aqui é o que precisa ser testável sem subir a aplicação — leitura da cabeça da
rodada, o append da revisão nova, o estado por etapa que a tela lê, as precondições da
cadeia e as duas fronteiras de artefato (catálogo lido do object store, URL assinada de
leitura privada).

Três regras atravessam tudo o que sai daqui:

- **Toda query da rodada filtra por `tenant_id` no MESMO `where` do `id`.** Rodada de
  outro tenant não é "sem permissão", é inexistente — e é o `where` que garante isso, não
  uma conferência posterior que alguém pode esquecer de escrever.
- **Nada é atualizado no lugar (ADR-0028 D2).** Mutação copia as colunas JSON da cabeça e
  grava linha nova; o que o ato não mudou viaja idêntico.
- **`base_version` é o contador de ATO HUMANO da rodada (D3).** `ValuationRound.version` é
  o token de concorrência otimista e só avança em ato humano; a `version` da revisão é a
  posição na cadeia append-only e avança sempre, inclusive quando um artefato DERIVADO
  (a shortlist de código) é persistido sem decisão humana. Os dois contadores nascem
  iguais e podem divergir depois — divergência declarada, para que um `GET` que recalcula
  a shortlist nunca invalide o `base_version` que o orçamentista tem na tela.
"""

from __future__ import annotations

import copy
import hashlib
import threading
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final, Protocol

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from croquito_api.database import ValuationRoundRecord, ValuationRoundRevisionRecord
from croquito_core.ids import new_uuid7
from croquito_valuation.assignment import CodeAssignmentSet
from croquito_valuation.errors import ValuationValidationError
from croquito_valuation.models import PriceCatalog
from croquito_valuation.takeoff import TakeoffPacket
from croquito_worker.valuation.round_extraction import (
    TAKEOFF_OVERLAY_DIGEST,
    TAKEOFF_OVERLAY_PACKET_DIGEST,
    TAKEOFF_OVERLAY_REF,
)

# Reexport explícito: o digest canônico de artefato JSON mora do lado do worker porque quem
# o ESCREVE (o comando de fila) e quem o COMPARA (a rota) são processos diferentes — duas
# serializações escritas em lados opostos passariam nos testes de cada um e deixariam o
# overlay permanentemente vencido. Quem lê a rodada continua importando daqui.
from croquito_worker.valuation.round_extraction import document_digest as document_digest
from croquito_worker.valuation.round_view import (
    REVIEWER_ROLE,
    anchor_counts,
    count_status,
    pending_code_items,
    registered_item_ids,
    review_status,
    takeoff_counts,
)

ROUND_STAGE_NOT_READY: Final = "ROUND_STAGE_NOT_READY"
REVISION_CONFLICT: Final = "REVISION_CONFLICT"
CATALOG_REQUIRED: Final = "CATALOG_REQUIRED"

STAGE_CREATED: Final = "created"
STAGE_PLATE: Final = "plate"
STAGE_EXTRACTION: Final = "extraction"
STAGE_TAKEOFF: Final = "takeoff"
STAGE_CODE_ASSIGNMENTS: Final = "code_assignments"
STAGE_BULLETIN: Final = "bulletin"
STAGE_DOSSIER: Final = "amendment_dossier"

CATALOG_MAX_BYTES: Final = 32 * 1024 * 1024
"""Teto de leitura do catálogo instalado.

O catálogo real do SCO tem 2,4 MB; o presign aceita objeto de até 100 MB. Ler sem teto
poria no request path da API um objeto do tamanho que o cliente quisesse — o teto é a
diferença entre um artefato de aplicação e um blob, e blob sai por URL assinada."""

CATALOG_CACHE_MAX_ENTRIES: Final = 4
"""Quantos catálogos decodificados o processo guarda ao mesmo tempo.

Um só (o arranjo do `_IndexCache` do servidor de medição) bastaria para uma rodada e
degradaria para zero acerto com duas telas abertas em rodadas diferentes, que é o caso
normal de um tenant com mais de uma obra. Quatro é o compromisso declarado entre isso e a
memória do processo, e o número existe para ser mexido com medida na mão."""

REVISION_DOCUMENT_COLUMNS: Final[tuple[str, ...]] = (
    "takeoff_packet_json",
    "takeoff_registration_json",
    "code_suggestions_json",
    "code_assignments_json",
    "valuation_json",
    "amendment_dossier_json",
    "extraction_lineage_json",
)
"""Colunas JSON de artefato; ausentes são `NULL`, e `NULL` é "a etapa não aconteceu"."""

REVISION_MAP_COLUMNS: Final[tuple[str, ...]] = ("artifact_refs_json", "artifact_digests_json")
"""Colunas de mapa; ausentes são `{}`, nunca `NULL` (é o default da coluna)."""

REVISION_COLUMNS: Final[tuple[str, ...]] = REVISION_DOCUMENT_COLUMNS + REVISION_MAP_COLUMNS


class RoundArtifactStore(Protocol):
    """A fatia do object store que a rodada usa; o vendor não entra neste módulo."""

    def read_object(self, *, object_key: str, max_bytes: int) -> bytes | None: ...

    def presign_private_read(self, *, object_key: str) -> str: ...


class RoundRefusal(Exception):
    """Precondição da rodada recusada, com o código estável de `/v1` e o status que vale.

    O status HTTP viaja aqui pelo mesmo motivo do `LocalServerRefusal` do servidor de
    medição: a precondição é que sabe se ela é conflito de estado (409) ou coisa
    inexistente (404), e espalhar essa tradução por cada rota seria multiplicar a chance de
    duas rotas responderem diferente para a mesma causa. Carregar um inteiro não é falar
    HTTP: nada aqui monta resposta, nem depende de FastAPI para existir.
    """

    def __init__(
        self,
        http_status: int,
        code: str,
        detail: str,
        details: Mapping[str, object] | None = None,
    ) -> None:
        self.http_status = http_status
        self.code = code
        self.detail = detail
        self.details: dict[str, object] = dict(details or {})
        super().__init__(f"{code}: {detail}")


def stage_not_ready(stage: str, *, detail: str) -> RoundRefusal:
    """Etapa anterior da cadeia ausente — ordem, não inexistência (ADR-0028 D4)."""
    return RoundRefusal(409, ROUND_STAGE_NOT_READY, detail, {"stage": stage})


def revision_conflict(*, base_version: int, current_version: int) -> RoundRefusal:
    return RoundRefusal(
        409,
        REVISION_CONFLICT,
        "a rodada mudou depois da leitura; recarregue antes de decidir de novo",
        {"base_version": base_version, "current_version": current_version},
    )


def catalog_required(reason: str, details: Mapping[str, object] | None = None) -> RoundRefusal:
    """Catálogo instalado que não está utilizável agora: configuração, não cadeia.

    A rodada nasce com catálogo por construção (`catalog_object_key` é `NOT NULL`), então
    o que este código nomeia é o objeto sumido do store, o digest divergente do instalado
    e o conteúdo que deixou de validar — nunca "a rodada não tem catálogo".
    """
    return RoundRefusal(409, CATALOG_REQUIRED, reason, details)


def load_round(session: Session, *, round_id: str, tenant_id: str) -> ValuationRoundRecord | None:
    """A rodada do tenant, ou `None`. Rodada de outro tenant é indistinguível de ausente."""
    return session.scalar(
        select(ValuationRoundRecord).where(
            ValuationRoundRecord.id == round_id,
            ValuationRoundRecord.tenant_id == tenant_id,
        )
    )


def head_revision(
    session: Session, *, round_id: str, tenant_id: str
) -> ValuationRoundRevisionRecord | None:
    """A revisão de maior `version` da rodada, ou `None` quando ela ainda não tem nenhuma.

    A rodada recém-criada não tem revisão: a primeira nasce do primeiro artefato. Por isso
    o retorno é opcional e as guardas de etapa tratam `None` como etapa ausente, e não como
    erro de servidor.
    """
    return session.scalar(
        select(ValuationRoundRevisionRecord)
        .where(
            ValuationRoundRevisionRecord.round_id == round_id,
            ValuationRoundRevisionRecord.tenant_id == tenant_id,
        )
        .order_by(ValuationRoundRevisionRecord.version.desc())
        .limit(1)
    )


def require_base_version(round_record: ValuationRoundRecord, base_version: int) -> None:
    """Concorrência otimista da rodada: um contador só para toda a cadeia (D3)."""
    if round_record.version != base_version:
        raise revision_conflict(base_version=base_version, current_version=round_record.version)


def append_revision(
    session: Session,
    *,
    round_record: ValuationRoundRecord,
    created_by: str,
    changes: Mapping[str, Any],
    advance_version: bool = True,
) -> ValuationRoundRevisionRecord:
    """Grava a revisão nova copiando a cabeça e sobrescrevendo só o que o ato mudou.

    `advance_version=False` é o caminho do artefato DERIVADO (a shortlist de código,
    decisão humana de 2026-08-17): a linha entra na cadeia append-only, mas o token de
    concorrência da rodada não anda — senão um `GET` que recalcula a shortlist faria a
    próxima decisão do orçamentista devolver `409` por algo que ele não fez.

    O valor carregado da cabeça é copiado em profundidade de propósito: duas linhas ORM
    apontando para o mesmo `dict` compartilhariam mutação e destruiriam a imutabilidade que
    a tabela existe para garantir.
    """
    unknown = sorted(set(changes) - set(REVISION_COLUMNS))
    if unknown:
        # Erro de programação, não de domínio: nome de coluna vem do código, nunca do
        # cliente. Falhar alto aqui é o que impede um ato de gravar em silêncio menos do
        # que ele pensa estar gravando.
        raise ValueError(f"coluna de revisão desconhecida: {', '.join(unknown)}")

    head = head_revision(session, round_id=round_record.id, tenant_id=round_record.tenant_id)
    carried: dict[str, Any] = {}
    for column in REVISION_COLUMNS:
        if column in changes:
            carried[column] = changes[column]
            continue
        default: Any = {} if column in REVISION_MAP_COLUMNS else None
        carried[column] = default if head is None else copy.deepcopy(getattr(head, column))

    revision = ValuationRoundRevisionRecord(
        id=str(new_uuid7()),
        tenant_id=round_record.tenant_id,
        round_id=round_record.id,
        version=1 if head is None else head.version + 1,
        parent_revision_id=None if head is None else head.id,
        created_by=created_by,
        **carried,
    )
    session.add(revision)
    if advance_version:
        round_record.version += 1
    return revision


def takeoff_packet_of(revision: ValuationRoundRevisionRecord | None) -> TakeoffPacket | None:
    if revision is None or revision.takeoff_packet_json is None:
        return None
    return TakeoffPacket.model_validate(revision.takeoff_packet_json)


def assignments_of(revision: ValuationRoundRevisionRecord | None) -> CodeAssignmentSet | None:
    if revision is None or revision.code_assignments_json is None:
        return None
    return CodeAssignmentSet.model_validate(revision.code_assignments_json)


def require_takeoff_packet(revision: ValuationRoundRevisionRecord | None) -> TakeoffPacket:
    """O pacote de takeoff publicado, ou a recusa de etapa fora de ordem."""
    packet = takeoff_packet_of(revision)
    if packet is None:
        raise stage_not_ready(
            STAGE_TAKEOFF, detail="a rodada ainda não tem pacote de takeoff publicado"
        )
    return packet


def takeoff_overlay_ref(revision: ValuationRoundRevisionRecord | None) -> str | None:
    """Chave do PNG do overlay gravada na revisão, ou `None` quando não há desenho."""
    if revision is None:
        return None
    key = (revision.artifact_refs_json or {}).get(TAKEOFF_OVERLAY_REF)
    return key if isinstance(key, str) and key else None


def require_takeoff_overlay(revision: ValuationRoundRevisionRecord | None) -> str:
    """A chave do overlay publicado, ou a recusa de etapa fora de ordem.

    Overlay e pacote nascem no MESMO ato da extração, então rodada sem overlay é rodada
    sem extração publicada — etapa fora de ordem, e não artefato perdido.
    """
    key = takeoff_overlay_ref(revision)
    if key is None:
        raise stage_not_ready(
            STAGE_TAKEOFF, detail="a rodada ainda não tem overlay do takeoff publicado"
        )
    return key


def takeoff_overlay_state(
    revision: ValuationRoundRevisionRecord | None, *, packet_sha256: str
) -> dict[str, Any]:
    """Idade do overlay DERIVADA na leitura, nunca gravada como verdade (ADR-0030).

    O overlay é reconstruído por comando de fila depois de cada decisão, então entre a
    decisão e o desenho novo existe uma janela em que o desenho é do pacote anterior.
    Marcá-la é melhor do que escondê-la: o overlay é a única visão de ONDE cada número foi
    lido, e servi-lo como se fosse do pacote corrente enganaria com a autoridade de um
    desenho.

    Overlay publicado antes deste contrato não declara pacote de origem e sai `stale` —
    desfecho fail-closed de propósito: o próximo re-render o corrige, e até lá a tela
    prefere duvidar a afirmar.
    """
    digests = {} if revision is None else dict(revision.artifact_digests_json or {})
    origin = digests.get(TAKEOFF_OVERLAY_PACKET_DIGEST)
    return {
        "present": takeoff_overlay_ref(revision) is not None,
        "image_sha256": digests.get(TAKEOFF_OVERLAY_DIGEST),
        "overlay_packet_sha256": origin,
        "stale": origin != packet_sha256,
    }


def require_assignments(revision: ValuationRoundRevisionRecord | None) -> CodeAssignmentSet:
    assignments = assignments_of(revision)
    if assignments is None:
        raise stage_not_ready(
            STAGE_CODE_ASSIGNMENTS,
            detail="a rodada ainda não tem decisão de código registrada",
        )
    return assignments


def require_document(
    revision: ValuationRoundRevisionRecord | None, column: str, *, stage: str, detail: str
) -> dict[str, Any]:
    """Artefato JSON de uma etapa, revalidado por quem o consome — aqui só a presença."""
    if column not in REVISION_DOCUMENT_COLUMNS:
        raise ValueError(f"coluna de revisão desconhecida: {column}")
    document = None if revision is None else getattr(revision, column)
    if document is None:
        raise stage_not_ready(stage, detail=detail)
    return dict(document)


def require_plate_object_key(round_record: ValuationRoundRecord) -> str:
    """Chave do PDF da prancha ingerida; rodada sem prancha é etapa fora de ordem."""
    if round_record.plate_object_key is None:
        raise stage_not_ready(STAGE_PLATE, detail="a rodada ainda não tem prancha associada")
    return round_record.plate_object_key


@dataclass(frozen=True, slots=True)
class PlateRef:
    """A prancha associada à rodada, com as três colunas conferidas de uma vez só."""

    upload_id: str
    object_key: str
    source_sha256: str
    page_count: int | None


def require_plate(round_record: ValuationRoundRecord) -> PlateRef:
    """A prancha da rodada, ou a recusa de etapa fora de ordem.

    As três colunas são conferidas JUNTAS de propósito: elas são gravadas no mesmo ato de
    associação, e ler uma delas isolada obrigaria cada chamador a decidir o que fazer com
    uma prancha meio associada — estado que a rota não sabe produzir e que ninguém deve ter
    de tratar duas vezes. `page_count` fica de fora dessa exigência porque só a ingestão da
    página, que é trabalho do worker, o conhece.
    """
    if (
        round_record.plate_object_key is None
        or round_record.plate_upload_id is None
        or round_record.plate_source_sha256 is None
    ):
        raise stage_not_ready(STAGE_PLATE, detail="a rodada ainda não tem prancha associada")
    return PlateRef(
        upload_id=round_record.plate_upload_id,
        object_key=round_record.plate_object_key,
        source_sha256=round_record.plate_source_sha256,
        page_count=round_record.plate_page_count,
    )


def current_stage(
    round_record: ValuationRoundRecord,
    revision: ValuationRoundRevisionRecord | None,
) -> str:
    """Etapa mais avançada que a rodada alcançou, para a linha da listagem.

    É leitura por PRESENÇA de artefato, na ordem da cadeia — o mesmo critério do estado por
    etapa, condensado num rótulo só. A extração não aparece aqui: ela é um estado próprio da
    raiz (`extraction_status`), pode estar em voo enquanto a etapa corrente ainda é a
    prancha, e escondê-la dentro de um rótulo único faria a lista mentir sobre o que a
    rodada está fazendo.
    """
    if revision is not None:
        if revision.amendment_dossier_json is not None:
            return STAGE_DOSSIER
        if revision.valuation_json is not None:
            return STAGE_BULLETIN
        if revision.code_assignments_json is not None:
            return STAGE_CODE_ASSIGNMENTS
        if revision.takeoff_packet_json is not None:
            return STAGE_TAKEOFF
    if round_record.plate_object_key is not None:
        return STAGE_PLATE
    return STAGE_CREATED


def signed_artifact_url(
    store: RoundArtifactStore, *, object_key: str | None, tenant_id: str
) -> str | None:
    """URL assinada de leitura, **só** para chave sob `tenants/{tenant_id}/`.

    Chave fora do prefixo é tratada como inexistente e o presign nunca é chamado: assinar
    primeiro e conferir depois entregaria uma URL válida de objeto alheio em qualquer
    caminho que esquecesse de olhar o retorno. O `..` é recusado junto porque uma chave com
    ele satisfaz o prefixo por texto e aponta para fora dele em qualquer sistema que
    normalize caminho.

    A URL devolvida nunca vai para log nem para auditoria (ADR-0028 D5).
    """
    if not tenant_id or object_key is None:
        return None
    if not object_key.startswith(f"tenants/{tenant_id}/"):
        return None
    if ".." in object_key.split("/"):
        return None
    return store.presign_private_read(object_key=object_key)


class CatalogCache:
    """Catálogos decodificados por digest, reusados pelo processo inteiro.

    Existe por custo medido, como o `_IndexCache` do servidor de medição: o catálogo real
    tem 2,4 MB de JSON e ~5.000 entradas, a tela da rodada faz polling e a busca de código
    é consultada a cada tecla — decodificar a cada requisição tornaria a etapa mais cara da
    tela justamente a que o orçamentista mais usa.

    A chave é o digest do objeto instalado, e só ele: catálogo trocado é digest diferente,
    logo entrada diferente, logo nunca um catálogo velho servido no lugar do novo. É cache
    de LEITURA de artefato imutável — não de decisão, não de autorização e não de nada que
    dependa de tenant: duas rodadas com o mesmo catálogo compartilham a mesma decodificação
    de propósito, porque o conteúdo é idêntico byte a byte por construção.
    """

    def __init__(self, max_entries: int = CATALOG_CACHE_MAX_ENTRIES) -> None:
        self._lock = threading.Lock()
        self._entries: OrderedDict[str, PriceCatalog] = OrderedDict()
        self._max_entries = max_entries

    def get(self, digest: str) -> PriceCatalog | None:
        with self._lock:
            catalog = self._entries.get(digest)
            if catalog is not None:
                self._entries.move_to_end(digest)
            return catalog

    def put(self, digest: str, catalog: PriceCatalog) -> None:
        with self._lock:
            self._entries[digest] = catalog
            self._entries.move_to_end(digest)
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)


CATALOG_CACHE: Final = CatalogCache()
"""Cache do processo. As funções o recebem por parâmetro para que teste use o seu."""


def load_catalog(
    store: RoundArtifactStore,
    round_record: ValuationRoundRecord,
    *,
    cache: CatalogCache = CATALOG_CACHE,
) -> PriceCatalog:
    """O catálogo instalado na rodada, lido do object store e validado pelo domínio.

    O digest instalado (`catalog_source_sha256`) manda duas vezes: é a chave do cache e é
    o que os bytes lidos têm de reproduzir. Objeto ausente, maior que o teto, com digest
    divergente ou que deixou de validar recusam com `CATALOG_REQUIRED` — o catálogo foi
    validado na criação da rodada, então uma falha aqui é do ambiente, não do ato.
    """
    digest = round_record.catalog_source_sha256
    cached = cache.get(digest)
    if cached is not None:
        return cached

    payload = store.read_object(
        object_key=round_record.catalog_object_key, max_bytes=CATALOG_MAX_BYTES
    )
    if payload is None:
        raise catalog_required(
            "o catálogo instalado nesta rodada não está disponível no armazenamento",
            {"round_id": round_record.id},
        )
    if len(payload) > CATALOG_MAX_BYTES:
        raise catalog_required(
            "o catálogo instalado nesta rodada excede o limite de leitura",
            {"round_id": round_record.id, "max_bytes": CATALOG_MAX_BYTES},
        )
    if hashlib.sha256(payload).hexdigest() != digest:
        raise catalog_required(
            "o catálogo armazenado diverge do digest instalado na rodada",
            {"round_id": round_record.id},
        )
    try:
        catalog = PriceCatalog.model_validate_json(payload)
    except ValuationValidationError as error:
        raise catalog_required(
            "o catálogo instalado nesta rodada não pôde ser lido",
            {"round_id": round_record.id, "reason": error.code},
        ) from error
    except ValidationError as error:
        raise catalog_required(
            "o catálogo instalado nesta rodada não pôde ser lido",
            {"round_id": round_record.id, "reason": "MODEL_VALIDATION_FAILED"},
        ) from error
    cache.put(digest, catalog)
    return catalog


def _artifact_digests(revision: ValuationRoundRevisionRecord | None) -> dict[str, str]:
    """Digest por artefato presente na revisão — o que a tela usa para ver o que mudou."""
    if revision is None:
        return {}
    digests: dict[str, str] = {
        column: document_digest(document)
        for column in REVISION_DOCUMENT_COLUMNS
        if isinstance(document := getattr(revision, column), dict)
    }
    # Os digests de blob (prancha, overlay) já vêm calculados sobre os BYTES do objeto:
    # recalculá-los aqui exigiria ler o blob, que é exatamente o que o D5 tira do request.
    digests.update(revision.artifact_digests_json or {})
    return digests


def round_state_payload(
    round_record: ValuationRoundRecord,
    revision: ValuationRoundRevisionRecord | None,
) -> dict[str, Any]:
    """Estado da rodada por etapa, espelhando o `/state` do servidor de medição.

    Espelha o conteúdo, não as chaves: o que era diretório (`root`, nome de arquivo) some,
    e as chaves saem em inglês, como todo identificador deste repositório — as duas em
    português do `_state_payload` (`extracao`, `busca_semantica`) eram do servidor local, e
    aqui o consumidor são os tipos gerados de `@croquito/contracts`.

    A etapa entra por PRESENÇA e digest; revalidar boletim ou dossiê é papel de quem os
    serve. Uma medição ilegível não pode derrubar a tela inteira antes de o orçamentista
    sequer chegar nela — a mesma regra que o servidor de medição já segue.

    O braço semântico da busca não aparece aqui: no `/v1` ele depende do entitlement
    contratual do tenant (decisão de 2026-08-17), e entitlement é dado da requisição
    autenticada, não da rodada.
    """
    packet = takeoff_packet_of(revision)
    assignments = assignments_of(revision)
    digests = _artifact_digests(revision)

    takeoff: dict[str, Any] = {"present": packet is not None}
    if packet is not None:
        registered = registered_item_ids(
            None if revision is None else revision.takeoff_registration_json
        )
        takeoff.update(
            {
                "packet_sha256": digests.get("takeoff_packet_json"),
                "plate_id": packet.plate_id,
                "page_number": packet.page_number,
                "review_status": review_status(packet),
                **takeoff_counts(packet),
                **anchor_counts(packet, registered),
            }
        )

    codes: dict[str, Any] = {
        "suggestions_present": "code_suggestions_json" in digests,
        "suggestions_sha256": digests.get("code_suggestions_json"),
        "assignments_present": assignments is not None,
        "assignments_sha256": digests.get("code_assignments_json"),
        "confirmed": 0 if assignments is None else count_status(assignments, "confirmed"),
        "rejected": 0 if assignments is None else count_status(assignments, "rejected"),
        "pending": None if packet is None else len(pending_code_items(packet, assignments)),
    }

    return {
        "round_id": round_record.id,
        "version": round_record.version,
        "status": round_record.status,
        "reviewer_role": REVIEWER_ROLE,
        "worksite_key": round_record.worksite_key,
        "worksite_name": round_record.worksite_name,
        "reference_label": round_record.reference_label,
        "period_number": round_record.period_number,
        "address": round_record.address,
        "contract_label": round_record.contract_label,
        "revision_id": None if revision is None else revision.id,
        "revision_version": None if revision is None else revision.version,
        "catalog": {
            "source_sha256": round_record.catalog_source_sha256,
            "summary": dict(round_record.catalog_summary_json or {}),
        },
        "artifacts": digests,
        "plate": {
            "present": round_record.plate_object_key is not None,
            "source_sha256": round_record.plate_source_sha256,
            "page_count": round_record.plate_page_count,
        },
        "extraction": {
            "status": round_record.extraction_status,
            "extraction_id": round_record.extraction_id,
            "failure_code": round_record.extraction_failure_code,
            "lineage_present": "extraction_lineage_json" in digests,
            "updated_at": (
                None
                if round_record.extraction_updated_at is None
                else round_record.extraction_updated_at.isoformat()
            ),
        },
        "takeoff": takeoff,
        "codes": codes,
        "bulletin": {
            "present": "valuation_json" in digests,
            "valuation_sha256": digests.get("valuation_json"),
        },
        "dossier": {
            "present": "amendment_dossier_json" in digests,
            "dossier_sha256": digests.get("amendment_dossier_json"),
        },
        "created_at": round_record.created_at.isoformat(),
        "updated_at": round_record.updated_at.isoformat(),
    }
