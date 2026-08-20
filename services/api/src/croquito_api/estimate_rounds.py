"""Núcleo de aplicação da rodada de orçamento-base: o que a rota decide antes de existir HTTP.

Este módulo é para `/v1/estimate-rounds` o que `valuation_rounds.py` é para
`/v1/valuation-rounds` — camada de aplicação **sem** FastAPI: nada aqui recebe `Request`,
monta `Response` ou conhece código de status por si só. As três regras que atravessam o
módulo da medição valem idênticas aqui, e por isso o que é literalmente o mesmo é
IMPORTADO de lá (`RoundRefusal`, `CatalogCache`, `read_catalog`, `require_search_terms`, os
rótulos de etapa) em vez de copiado; o que muda de tabela — as consultas, o append da
revisão e o estado que a tela lê — é o que mora aqui:

- **Toda query da rodada filtra por `tenant_id` no MESMO `where` do `id`.**
- **Nada é atualizado no lugar.** Mutação copia as colunas JSON da cabeça e grava linha
  nova; o que o ato não mudou viaja idêntico.
- **`base_version` é o contador de ATO HUMANO da rodada.** A `version` da revisão é a
  posição na cadeia append-only e avança sempre, inclusive quando um artefato DERIVADO
  (a shortlist de código) é persistido sem decisão humana.

O que este contexto tem e o da medição não tem é a **cascata**: a rodada de orçamento-base
guarda uma LISTA ORDENADA de fontes de preço, e a ordem é dado, não código (ADR-0027). Ela
decide qual fonte aparece primeiro na shortlist e na busca, e por isso reordená-la muda o
que o orçamentista vê na etapa seguinte — sem que nada seja recalculado escondido. Uma
origem só entra uma vez: duas fontes da mesma origem fariam "o preço veio da EMOP" deixar
de identificar de qual arquivo ele veio (`ESTIMATE_CASCADE_ORIGIN_DUPLICATE`).

O que este contexto NÃO tem, de propósito: contrato, saldo, período e aprovação. Nada
disso existe antes da licitação, e o `Estimate` não passa — nem tenta passar — pelo portão
de exportação da medição.
"""

from __future__ import annotations

import copy
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Final

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from croquito_api.database import EstimateRoundRecord, EstimateRoundRevisionRecord
from croquito_api.valuation_rounds import (
    SEMANTIC_ARM_ABSENT,
    STAGE_CODE_ASSIGNMENTS,
    STAGE_CREATED,
    STAGE_PLATE,
    STAGE_TAKEOFF,
    CatalogCache,
    RoundArtifactStore,
    RoundRefusal,
    catalog_required,
    document_digest,
    read_catalog,
    require_search_terms,
    stage_not_ready,
)
from croquito_core.ids import new_uuid7
from croquito_valuation.assignment import (
    CodeAssignmentSet,
    CodeSuggestionSet,
    suggest_codes_over_cascade,
)
from croquito_valuation.catalog import default_domain_synonyms, default_legend_noise
from croquito_valuation.errors import ValuationValidationError
from croquito_valuation.estimate import Estimate
from croquito_valuation.estimate_workbook import (
    EstimateAuditReport,
    audit_estimate_workbook,
    write_estimate_workbook,
)
from croquito_valuation.models import PriceCatalog
from croquito_valuation.takeoff import TakeoffPacket
from croquito_valuation.template import WorkbookTemplate
from croquito_worker.valuation.catalog_search import search_catalog
from croquito_worker.valuation.round_extraction import (
    TAKEOFF_OVERLAY_DIGEST,
    TAKEOFF_OVERLAY_PACKET_DIGEST,
    TAKEOFF_OVERLAY_REF,
)
from croquito_worker.valuation.round_view import (
    REVIEWER_ROLE,
    anchor_counts,
    count_status,
    pending_code_items,
    registered_item_ids,
    review_status,
    takeoff_counts,
)

ESTIMATE_CASCADE_ORIGIN_DUPLICATE: Final = "ESTIMATE_CASCADE_ORIGIN_DUPLICATE"
ESTIMATE_CASCADE_ORDER_INVALID: Final = "ESTIMATE_CASCADE_ORDER_INVALID"
ESTIMATE_CASCADE_LOCKED: Final = "ESTIMATE_CASCADE_LOCKED"
ESTIMATE_WORKBOOK_AUDIT_FAILED: Final = "ESTIMATE_WORKBOOK_AUDIT_FAILED"
ESTIMATE_BDI_INVALID: Final = "ESTIMATE_BDI_INVALID"

STAGE_CATALOGS: Final = "catalogs"
STAGE_ESTIMATE: Final = "estimate"

ESTIMATE_WORKBOOK_REF: Final = "estimate_workbook"
"""Chave do `.xlsx` publicado, em `artifact_refs_json`. Nunca uma URL assinada."""

ESTIMATE_WORKBOOK_DIGEST: Final = "estimate_workbook_sha256"
"""Digest dos BYTES da planilha publicada, em `artifact_digests_json`."""

ESTIMATE_WORKBOOK_CONTENT_TYPE: Final = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

REVISION_DOCUMENT_COLUMNS: Final[tuple[str, ...]] = (
    "takeoff_packet_json",
    "takeoff_registration_json",
    "code_suggestions_json",
    "code_assignments_json",
    "estimate_json",
    "extraction_lineage_json",
)
"""Colunas JSON de artefato; ausentes são `NULL`, e `NULL` é "a etapa não aconteceu"."""

REVISION_MAP_COLUMNS: Final[tuple[str, ...]] = ("artifact_refs_json", "artifact_digests_json")
"""Colunas de mapa; ausentes são `{}`, nunca `NULL` (é o default da coluna)."""

REVISION_COLUMNS: Final[tuple[str, ...]] = REVISION_DOCUMENT_COLUMNS + REVISION_MAP_COLUMNS

_CASCADE_ENTRY_FIELDS: Final[tuple[str, ...]] = (
    "upload_id",
    "object_key",
    "object_sha256",
    "source_sha256",
    "origin",
    "reference_month",
    "source_label",
)


# --- recusas ------------------------------------------------------------------------------


def cascade_origin_duplicate(origin: str) -> RoundRefusal:
    """Origem já presente na cascata: o mesmo código do domínio, na fronteira de `/v1`.

    O nome é o de `ensure_price_cascade`/`Estimate.validate_cascade` de propósito. Recusar
    a instalação aqui, e não na montagem, é o que impede uma rodada de acumular decisões de
    código sobre uma cascata que nunca poderá virar orçamento.
    """
    return RoundRefusal(
        409,
        ESTIMATE_CASCADE_ORIGIN_DUPLICATE,
        "a cascata já tem um catálogo desta origem; a origem deixaria de identificar a "
        "fonte do preço de cada linha",
        {"origin": origin},
    )


def cascade_order_invalid(detail: str, details: Mapping[str, object]) -> RoundRefusal:
    """Reordenação que não é uma PERMUTAÇÃO da cascata instalada.

    A rota de ordem só reordena: acrescentar, remover ou repetir fonte por aqui seria
    instalar catálogo por uma porta que não lê nem valida catálogo nenhum.
    """
    return RoundRefusal(422, ESTIMATE_CASCADE_ORDER_INVALID, detail, details)


def workbook_audit_failed(audit: EstimateAuditReport) -> RoundRefusal:
    """Auditoria de round-trip reprovada: nada é publicado e a recusa é estável.

    Só os CÓDIGOS dos achados viajam. `EstimateAuditFinding` carrega `expected`/`found`,
    que são preço e quantidade do cliente — devolvê-los numa mensagem de erro publicaria
    justamente o conteúdo que a planilha existe para entregar por URL assinada.

    É `500` porque a divergência não é do pedido: a planilha é render determinístico do
    `Estimate` que o próprio servidor acabou de montar, e a única leitura honesta de um
    arquivo que não confere consigo mesmo é que o servidor falhou em produzi-lo.
    """
    return RoundRefusal(
        500,
        ESTIMATE_WORKBOOK_AUDIT_FAILED,
        "a planilha do orçamento não confere com o orçamento montado; nada foi publicado",
        {
            "finding_codes": sorted({finding.code for finding in audit.findings}),
            "finding_count": len(audit.findings),
        },
    )


def parse_bdi_percent(raw: str) -> Decimal:
    """`Decimal` do BDI informado; texto ilegível recusa em vez de virar número aproximado.

    O BDI viaja como TEXTO pelo mesmo motivo da quantidade do takeoff (ADR-0038, decisão
    2): ele é `ExactDecimal` no domínio, que recusa `float`, e um número de JSON já teria
    passado por binário antes de chegar aqui.
    """
    try:
        percent = Decimal(raw)
    except InvalidOperation as error:
        raise RoundRefusal(
            422,
            ESTIMATE_BDI_INVALID,
            "o BDI informado não é um número decimal exato",
            {},
        ) from error
    if not percent.is_finite() or percent < 0:
        raise RoundRefusal(
            422,
            ESTIMATE_BDI_INVALID,
            "o BDI do orçamento é um percentual finito e não negativo",
            {},
        )
    return percent


# --- leitura da rodada --------------------------------------------------------------------


def load_round(session: Session, *, round_id: str, tenant_id: str) -> EstimateRoundRecord | None:
    """A rodada do tenant, ou `None`. Rodada de outro tenant é indistinguível de ausente."""
    return session.scalar(
        select(EstimateRoundRecord).where(
            EstimateRoundRecord.id == round_id,
            EstimateRoundRecord.tenant_id == tenant_id,
        )
    )


def head_revision(
    session: Session, *, round_id: str, tenant_id: str
) -> EstimateRoundRevisionRecord | None:
    """A revisão de maior `version` da rodada, ou `None` quando ela ainda não tem nenhuma."""
    return session.scalar(
        select(EstimateRoundRevisionRecord)
        .where(
            EstimateRoundRevisionRecord.round_id == round_id,
            EstimateRoundRevisionRecord.tenant_id == tenant_id,
        )
        .order_by(EstimateRoundRevisionRecord.version.desc())
        .limit(1)
    )


def require_base_version(round_record: EstimateRoundRecord, base_version: int) -> None:
    """Concorrência otimista da rodada: um contador só para toda a cadeia."""
    if round_record.version != base_version:
        raise RoundRefusal(
            409,
            "REVISION_CONFLICT",
            "a rodada mudou depois da leitura; recarregue antes de decidir de novo",
            {"base_version": base_version, "current_version": round_record.version},
        )


def append_revision(
    session: Session,
    *,
    round_record: EstimateRoundRecord,
    created_by: str,
    changes: Mapping[str, Any],
    advance_version: bool = True,
) -> EstimateRoundRevisionRecord:
    """Grava a revisão nova copiando a cabeça e sobrescrevendo só o que o ato mudou.

    Espelho do append da medição, inclusive no `advance_version=False` do artefato
    DERIVADO (a shortlist de código): a linha entra na cadeia append-only, mas o token de
    concorrência da rodada não anda — senão um `GET` que recalcula a shortlist faria a
    próxima decisão do orçamentista devolver `409` por algo que ele não fez.

    O valor carregado da cabeça é copiado em profundidade de propósito: duas linhas ORM
    apontando para o mesmo `dict` compartilhariam mutação e destruiriam a imutabilidade que
    a tabela existe para garantir.
    """
    unknown = sorted(set(changes) - set(REVISION_COLUMNS))
    if unknown:
        # Erro de programação, não de domínio: nome de coluna vem do código, nunca do
        # cliente.
        raise ValueError(f"coluna de revisão desconhecida: {', '.join(unknown)}")

    head = head_revision(session, round_id=round_record.id, tenant_id=round_record.tenant_id)
    carried: dict[str, Any] = {}
    for column in REVISION_COLUMNS:
        if column in changes:
            carried[column] = changes[column]
            continue
        default: Any = {} if column in REVISION_MAP_COLUMNS else None
        carried[column] = default if head is None else copy.deepcopy(getattr(head, column))

    revision = EstimateRoundRevisionRecord(
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


# --- cascata de fontes de preço -----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CascadeEntry:
    """Uma fonte de preço instalada na rodada, com a posição que ela ocupa na cascata.

    `position` é derivado da ordem da coluna na leitura, e nunca gravado: a ordem da lista
    **é** a precedência, e guardar um número ao lado dela criaria duas fontes de verdade
    que uma reordenação poderia deixar divergentes.
    """

    position: int
    upload_id: str
    object_key: str
    object_sha256: str
    """Digest dos BYTES do JSON gravado no store; é ele que a releitura tem de reproduzir.

    Não é o mesmo que `source_sha256`, e a diferença é real: o importador carimba em
    `PriceCatalog.source_sha256` o digest do arquivo de ORIGEM (o `.xlsx` do SCO, o `.DBF`
    da EMOP), enquanto o que sobe pelo presign é o JSON importado. Guardar um só dos dois
    obrigaria a escolher entre não conseguir conferir a integridade do objeto lido e não
    conseguir casar a fonte que a decisão de código cita."""
    source_sha256: str
    """Identidade do catálogo como o DOMÍNIO a conhece: é este digest que a confirmação de
    código cita, que a linha do orçamento carrega e que a reordenação recebe."""
    origin: str
    reference_month: str
    source_label: str
    summary: dict[str, Any]

    def payload(self) -> dict[str, Any]:
        """A entrada como a tela a lê; `object_key` e `upload_id` não saem daqui.

        A chave do objeto é referência interna do store: publicá-la daria ao cliente o
        endereço de um artefato que ele só pode ler por URL assinada.
        """
        return {
            "position": self.position,
            "origin": self.origin,
            "source_sha256": self.source_sha256,
            "reference_month": self.reference_month,
            "source_label": self.source_label,
            "summary": dict(self.summary),
        }


def cascade_entries(round_record: EstimateRoundRecord) -> list[CascadeEntry]:
    """A cascata instalada, na ordem gravada. Lista vazia é a rodada recém-aberta.

    Entrada malformada recusa com `CATALOG_REQUIRED`, e não com erro de servidor: quem
    escreve esta coluna é a rota de instalação, então um registro que não decodifica é
    falha de ambiente (dado adulterado, migração incompleta) e não do ato corrente.
    """
    entries: list[CascadeEntry] = []
    for position, raw in enumerate(round_record.catalog_cascade_json or [], start=1):
        if not isinstance(raw, Mapping) or any(
            not isinstance(raw.get(field), str) for field in _CASCADE_ENTRY_FIELDS
        ):
            raise catalog_required(
                "a cascata instalada nesta rodada não pôde ser lida",
                {"round_id": round_record.id, "position": position},
            )
        summary = raw.get("summary")
        entries.append(
            CascadeEntry(
                position=position,
                upload_id=str(raw["upload_id"]),
                object_key=str(raw["object_key"]),
                object_sha256=str(raw["object_sha256"]),
                source_sha256=str(raw["source_sha256"]),
                origin=str(raw["origin"]),
                reference_month=str(raw["reference_month"]),
                source_label=str(raw["source_label"]),
                summary=dict(summary) if isinstance(summary, Mapping) else {},
            )
        )
    return entries


def require_cascade(round_record: EstimateRoundRecord) -> list[CascadeEntry]:
    """A cascata instalada, ou a recusa de etapa fora de ordem.

    Rodada sem fonte nenhuma não é rodada quebrada: é rodada que ainda não chegou lá. Por
    isso `409 ROUND_STAGE_NOT_READY`, e não `CATALOG_REQUIRED` — o orçamentista tem o que
    fazer para sair desse estado.
    """
    entries = cascade_entries(round_record)
    if not entries:
        raise stage_not_ready(
            STAGE_CATALOGS, detail="a rodada ainda não tem catálogo instalado na cascata"
        )
    return entries


def cascade_entry_payload(entries: Sequence[CascadeEntry]) -> list[dict[str, Any]]:
    return [entry.payload() for entry in entries]


def ensure_source_installable(entries: Sequence[CascadeEntry], catalog: PriceCatalog) -> None:
    """Duas recusas antes de instalar, e as duas são sobre identificar a fonte de um preço.

    A primeira é a do domínio: uma origem por cascata, senão "o preço veio da EMOP" deixa
    de dizer de qual arquivo ele veio.

    A segunda é a que o domínio não tem como ver daqui: dois catálogos de ORIGENS
    diferentes importados do MESMO arquivo de origem teriam o mesmo `source_sha256` — e é
    esse digest que a confirmação de código cita, que a reordenação recebe e que
    `build_worksite_estimate` usa para achar o catálogo. Com dois candidatos, a citação
    passa a apontar para qualquer um dos dois, e nem a reordenação nem o orçamento
    conseguiriam distinguir a fonte. É recusa de instalação porque é aí que o segundo
    aparece; depois já não haveria o que corrigir sem abrir rodada nova.
    """
    if any(entry.origin == catalog.origin.value for entry in entries):
        raise cascade_origin_duplicate(catalog.origin.value)
    if any(entry.source_sha256 == catalog.source_sha256 for entry in entries):
        raise RoundRefusal(
            409,
            ESTIMATE_CASCADE_ORIGIN_DUPLICATE,
            "a cascata já tem uma fonte com este digest de origem; o digest deixaria de "
            "identificar de qual catálogo o preço de cada linha veio",
            {"origin": catalog.origin.value},
        )


def installed_entry(
    *,
    upload_id: str,
    object_key: str,
    object_sha256: str,
    catalog: PriceCatalog,
    summary: Mapping[str, Any],
) -> dict[str, Any]:
    """A entrada nova da cascata, com os metadados lidos do catálogo já validado."""
    return {
        "upload_id": upload_id,
        "object_key": object_key,
        "object_sha256": object_sha256,
        "source_sha256": catalog.source_sha256,
        "origin": catalog.origin.value,
        "reference_month": catalog.reference_month,
        "source_label": catalog.source_label,
        "summary": dict(summary),
    }


def reordered_cascade(
    entries: Sequence[CascadeEntry], digests: Sequence[str]
) -> list[dict[str, Any]]:
    """A cascata na ordem pedida; o corpo tem de ser uma PERMUTAÇÃO da cascata instalada.

    Exigir a lista COMPLETA é o que torna a reordenação um ato legível: um corpo parcial
    obrigaria o servidor a inventar onde as fontes omitidas entram, e essa escolha é
    exatamente a que o ADR-0027 tira do código e devolve ao orçamentista.
    """
    installed = [entry.source_sha256 for entry in entries]
    if len(digests) != len(set(digests)):
        raise cascade_order_invalid(
            "a ordem informada repete uma fonte de preço",
            {"expected": installed},
        )
    if sorted(digests) != sorted(installed):
        raise cascade_order_invalid(
            "a ordem informada não corresponde às fontes instaladas nesta rodada",
            {"expected": installed},
        )
    by_digest = {entry.source_sha256: entry for entry in entries}
    return [_entry_document(by_digest[digest]) for digest in digests]


def _entry_document(entry: CascadeEntry) -> dict[str, Any]:
    """A entrada de volta na forma gravada; `position` não entra, porque é a ordem da lista."""
    return {
        "upload_id": entry.upload_id,
        "object_key": entry.object_key,
        "object_sha256": entry.object_sha256,
        "source_sha256": entry.source_sha256,
        "origin": entry.origin,
        "reference_month": entry.reference_month,
        "source_label": entry.source_label,
        "summary": dict(entry.summary),
    }


def require_cascade_unlocked(revision: EstimateRoundRevisionRecord | None) -> None:
    """Recusa reordenar a cascata depois que a rodada já tem decisão de código.

    Não é zelo: é a única leitura que não deixa a rodada travada em silêncio. O domínio
    amarra o conjunto de decisões ao catálogo CABEÇA da cascata
    (`CodeAssignmentSet.catalog_sha256`) e recusa acumular sobre um conjunto calculado com
    outro (`ASSIGNMENT_CATALOG_MISMATCH`, `assignment.py`). Deixar a reordenação passar
    faria a decisão SEGUINTE — não a reordenação — falhar com uma mensagem sobre catálogo
    que ninguém trocou, e sem caminho de volta: não há rota que apague decisão.

    Recusar aqui é a mesma regra do `worksite_key` da medição, aplicada à ordem: uma
    escolha que fica imutável tarde demais tem de ser recusada no ato que a violaria.
    """
    if revision is not None and revision.code_assignments_json is not None:
        raise RoundRefusal(
            409,
            ESTIMATE_CASCADE_LOCKED,
            "a rodada já tem decisão de código: reordenar a cascata invalidaria as "
            "decisões registradas, e apagar decisão do orçamentista não é ato desta API",
            {},
        )


def load_cascade(
    store: RoundArtifactStore,
    round_record: EstimateRoundRecord,
    *,
    cache: CatalogCache,
) -> list[PriceCatalog]:
    """Os catálogos da cascata, NA ORDEM instalada, lidos do store e validados.

    A ordem é o dado que este módulo existe para preservar: quem recebe a lista — a
    shortlist, a busca e a montagem do orçamento — trata a posição como precedência
    declarada, e devolvê-la em qualquer outra ordem mudaria a precificação em silêncio.
    """
    return [
        read_catalog(
            store,
            object_key=entry.object_key,
            digest=entry.object_sha256,
            cache=cache,
            details={"round_id": round_record.id, "position": entry.position},
        )
        for entry in require_cascade(round_record)
    ]


# --- artefatos da cadeia ------------------------------------------------------------------


def takeoff_packet_of(revision: EstimateRoundRevisionRecord | None) -> TakeoffPacket | None:
    if revision is None or revision.takeoff_packet_json is None:
        return None
    return TakeoffPacket.model_validate(revision.takeoff_packet_json)


def assignments_of(revision: EstimateRoundRevisionRecord | None) -> CodeAssignmentSet | None:
    if revision is None or revision.code_assignments_json is None:
        return None
    return CodeAssignmentSet.model_validate(revision.code_assignments_json)


def suggestions_of(revision: EstimateRoundRevisionRecord | None) -> CodeSuggestionSet | None:
    """Shortlist gravada, ou `None` quando ela não existe **ou não valida mais**.

    Ilegível conta como ausente só para quem PERGUNTA pelo conteúdo (a guarda de refino
    pago); quem SERVE a shortlist recusa, porque a tela não pode renderizar o que o domínio
    não valida.
    """
    if revision is None or revision.code_suggestions_json is None:
        return None
    try:
        return CodeSuggestionSet.model_validate(revision.code_suggestions_json)
    except (ValuationValidationError, ValidationError):
        return None


def require_takeoff_packet(revision: EstimateRoundRevisionRecord | None) -> TakeoffPacket:
    """O pacote de takeoff publicado, ou a recusa de etapa fora de ordem."""
    packet = takeoff_packet_of(revision)
    if packet is None:
        raise stage_not_ready(
            STAGE_TAKEOFF, detail="a rodada ainda não tem pacote de takeoff publicado"
        )
    return packet


def require_reviewed_takeoff_stage(packet: TakeoffPacket) -> None:
    """Montagem só sobre takeoff inteiramente revisado — recusa de ORDEM da cadeia.

    Duas rotas recusam a mesma condição com códigos diferentes, e a diferença é
    intencional. Na shortlist de código a recusa é `TAKEOFF_REVIEW_INCOMPLETE`, porque o
    que falha é o CÁLCULO de um artefato derivado sobre um pacote meio revisado. Aqui a
    recusa é `ROUND_STAGE_NOT_READY`, porque o que falta é uma ETAPA da cadeia: montar o
    orçamento com item ainda pendente publicaria um total que ignora, em silêncio, o que o
    orçamentista ainda não decidiu.
    """
    pending = packet.pending_items()
    if pending:
        raise RoundRefusal(
            409,
            "ROUND_STAGE_NOT_READY",
            "a revisão do takeoff ainda não está concluída",
            {"stage": STAGE_TAKEOFF, "pending": len(pending)},
        )


def require_assignments(revision: EstimateRoundRevisionRecord | None) -> CodeAssignmentSet:
    assignments = assignments_of(revision)
    if assignments is None:
        raise stage_not_ready(
            STAGE_CODE_ASSIGNMENTS,
            detail="a rodada ainda não tem decisão de código registrada",
        )
    return assignments


def require_document(
    revision: EstimateRoundRevisionRecord | None, column: str, *, stage: str, detail: str
) -> dict[str, Any]:
    """Artefato JSON de uma etapa, revalidado por quem o consome — aqui só a presença."""
    if column not in REVISION_DOCUMENT_COLUMNS:
        raise ValueError(f"coluna de revisão desconhecida: {column}")
    document = None if revision is None else getattr(revision, column)
    if document is None:
        raise stage_not_ready(stage, detail=detail)
    return dict(document)


def takeoff_overlay_ref(revision: EstimateRoundRevisionRecord | None) -> str | None:
    """Chave do PNG do overlay gravada na revisão, ou `None` quando não há desenho."""
    if revision is None:
        return None
    key = (revision.artifact_refs_json or {}).get(TAKEOFF_OVERLAY_REF)
    return key if isinstance(key, str) and key else None


def require_takeoff_overlay(revision: EstimateRoundRevisionRecord | None) -> str:
    """A chave do overlay publicado, ou a recusa de etapa fora de ordem."""
    key = takeoff_overlay_ref(revision)
    if key is None:
        raise stage_not_ready(
            STAGE_TAKEOFF, detail="a rodada ainda não tem overlay do takeoff publicado"
        )
    return key


def takeoff_overlay_state(
    revision: EstimateRoundRevisionRecord | None, *, packet_sha256: str
) -> dict[str, Any]:
    """Idade do overlay DERIVADA na leitura, nunca gravada como verdade (ADR-0030).

    Overlay publicado sem declarar pacote de origem sai `stale`: desfecho fail-closed de
    propósito, porque a tela prefere duvidar a afirmar.
    """
    digests = {} if revision is None else dict(revision.artifact_digests_json or {})
    origin = digests.get(TAKEOFF_OVERLAY_PACKET_DIGEST)
    return {
        "present": takeoff_overlay_ref(revision) is not None,
        "image_sha256": digests.get(TAKEOFF_OVERLAY_DIGEST),
        "overlay_packet_sha256": origin,
        "stale": origin != packet_sha256,
    }


@dataclass(frozen=True, slots=True)
class PlateRef:
    """A prancha associada à rodada, com as três colunas conferidas de uma vez só."""

    upload_id: str
    object_key: str
    source_sha256: str
    page_count: int | None


def require_plate(round_record: EstimateRoundRecord) -> PlateRef:
    """A prancha da rodada, ou a recusa de etapa fora de ordem.

    As três colunas são conferidas JUNTAS porque são gravadas no mesmo ato: ler uma delas
    isolada obrigaria cada chamador a decidir o que fazer com uma prancha meio associada.
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
    round_record: EstimateRoundRecord,
    revision: EstimateRoundRevisionRecord | None,
) -> str:
    """Etapa mais avançada que a rodada alcançou, para a linha da listagem.

    Leitura por PRESENÇA de artefato, na ordem da cadeia. A extração não aparece aqui: ela
    é estado próprio da raiz e pode estar em voo enquanto a etapa corrente ainda é a
    prancha.
    """
    if revision is not None:
        if revision.estimate_json is not None:
            return STAGE_ESTIMATE
        if revision.code_assignments_json is not None:
            return STAGE_CODE_ASSIGNMENTS
        if revision.takeoff_packet_json is not None:
            return STAGE_TAKEOFF
    if round_record.plate_object_key is not None:
        return STAGE_PLATE
    if round_record.catalog_cascade_json:
        return STAGE_CATALOGS
    return STAGE_CREATED


# --- saídas derivadas da cascata ----------------------------------------------------------


def compute_round_suggestions(
    packet: TakeoffPacket, cascade: Sequence[PriceCatalog]
) -> tuple[CodeSuggestionSet, list[str]]:
    """Shortlist recalculada do zero sobre a CASCATA; nenhuma chamada paga acontece.

    Os candidatos saem na ordem da cascata — todos os da primeira fonte, depois os da
    segunda — porque misturar os blocos por score faria a ordem das fontes, que é decisão
    declarada do orçamentista, ser desempatada por similaridade de texto. O braço semântico
    é declarado indisponível pelo mesmo motivo da medição: nenhuma rota de `/v1` publica
    índice de embeddings.
    """
    return (
        suggest_codes_over_cascade(packet, cascade, synonyms=default_domain_synonyms()),
        [SEMANTIC_ARM_ABSENT],
    )


def search_round_cascade(cascade: Sequence[PriceCatalog], query: str, limit: int) -> dict[str, Any]:
    """Busca léxica sobre a cascata inteira, um bloco por fonte, na ordem instalada.

    Espelha `suggest_codes_over_cascade` na forma e pelo mesmo motivo: o corte de `limit`
    vale POR fonte, de modo que uma tabela não seja espremida para fora da página por outra
    que ficou na frente da cascata, e os blocos saem concatenados na ordem declarada em vez
    de reordenados por score. É por isso que reordenar a cascata muda o que a tela mostra
    na busca seguinte — o efeito é o ponto da ordem ser dado.

    Cada resultado carrega `price_origin`, `catalog_sha256` e `cascade_position`. O campo
    `origin` que `result_payload` já devolve **não** é reusado para isso: lá ele nomeia o
    BRAÇO da busca (`lexical`/`semantic`), e sobrescrevê-lo faria dois significados
    diferentes ocuparem a mesma chave em duas rotas do mesmo `/v1`.
    """
    terms = require_search_terms(query)
    results: list[dict[str, Any]] = []
    total_matches = 0
    expanded: dict[str, list[str]] = {}
    for position, catalog in enumerate(cascade, start=1):
        found = search_catalog(
            catalog,
            query,
            limit,
            default_domain_synonyms(),
            noise=default_legend_noise(),
            semantic=None,
            query_vec=None,
            semantic_warning=None,
        )
        matches = found["total_matches"]
        assert isinstance(matches, int)
        total_matches += matches
        raw_results = found["results"]
        assert isinstance(raw_results, list)
        for result in raw_results:
            assert isinstance(result, dict)
            results.append(
                {
                    **result,
                    "price_origin": catalog.origin.value,
                    "catalog_sha256": catalog.source_sha256,
                    "cascade_position": position,
                }
            )
        raw_expanded = found.get("expanded_terms")
        if isinstance(raw_expanded, dict):
            for term, sources in raw_expanded.items():
                assert isinstance(sources, list)
                expanded.setdefault(str(term), []).extend(str(source) for source in sources)

    payload: dict[str, Any] = {
        "query": query,
        "terms": list(terms),
        "limit": limit,
        "matching": "lexical",
        "total_matches": total_matches,
        "semantic_matches": 0,
        "semantic_notes": [SEMANTIC_ARM_ABSENT],
        "results": results,
    }
    if expanded:
        payload["expanded_terms"] = {
            term: sorted(set(sources)) for term, sources in expanded.items()
        }
    return payload


# --- planilha publicada -------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RenderedEstimateWorkbook:
    """A planilha já auditada, ainda em memória: bytes e o relatório que a aprovou."""

    body: bytes
    audit: EstimateAuditReport


def render_estimate_workbook(
    estimate: Estimate, template: WorkbookTemplate
) -> RenderedEstimateWorkbook:
    """Grava a planilha num arquivo temporário, reabre, audita e só então devolve os bytes.

    Mesmo desenho fail-closed de `run_export_estimate_workbook` no worker (ADR-0038): o
    arquivo nasce em nome pendente — aqui, num diretório temporário que morre com a
    chamada — e a auditoria de round-trip é quem decide se ele existe para alguém. Nada
    chega ao object store antes disso, e auditoria reprovada não publica.

    A API não importa o CLI: o gate é replicado com as funções do pacote `valuation`,
    porque o comando de fila e a rota são processos diferentes e um importar o outro faria
    a fronteira de `services/` depender do CLI.
    """
    with tempfile.TemporaryDirectory(prefix="croquito-estimate-") as directory:
        path = Path(directory) / "orcamento.xlsx"
        write_estimate_workbook(estimate, template, path)
        audit = audit_estimate_workbook(path, estimate, template)
        if audit.status != "ok":
            raise workbook_audit_failed(audit)
        return RenderedEstimateWorkbook(body=path.read_bytes(), audit=audit)


def estimate_workbook_key(*, tenant_id: str, round_id: str, estimate_sha256: str) -> str:
    """Chave do `.xlsx` sob o prefixo do tenant, endereçada pelo digest do orçamento.

    Endereçar pelo conteúdo — e não por um nome fixo — é o que impede uma montagem nova de
    sobrescrever a planilha que a revisão anterior ainda referencia: cada revisão aponta
    para o arquivo do orçamento que ela gravou, e uma URL assinada emitida antes continua
    servindo exatamente o que foi auditado quando foi emitida.
    """
    return f"tenants/{tenant_id}/estimate-rounds/{round_id}/estimate/{estimate_sha256}.xlsx"


def estimate_workbook_ref(revision: EstimateRoundRevisionRecord | None) -> str | None:
    if revision is None:
        return None
    key = (revision.artifact_refs_json or {}).get(ESTIMATE_WORKBOOK_REF)
    return key if isinstance(key, str) and key else None


# --- estado da rodada ---------------------------------------------------------------------


def _artifact_digests(revision: EstimateRoundRevisionRecord | None) -> dict[str, str]:
    """Digest por artefato presente na revisão — o que a tela usa para ver o que mudou."""
    if revision is None:
        return {}
    digests: dict[str, str] = {
        column: document_digest(document)
        for column in REVISION_DOCUMENT_COLUMNS
        if isinstance(document := getattr(revision, column), dict)
    }
    # Os digests de blob (prancha, overlay, planilha) já vêm calculados sobre os BYTES do
    # objeto: recalculá-los aqui exigiria ler o blob dentro do request.
    digests.update(revision.artifact_digests_json or {})
    return digests


def round_state_payload(
    round_record: EstimateRoundRecord,
    revision: EstimateRoundRevisionRecord | None,
) -> dict[str, Any]:
    """Estado da rodada por etapa, espelhando o da medição com a cascata no lugar do catálogo.

    A etapa entra por PRESENÇA e digest; revalidar o orçamento é papel de quem o serve. Um
    orçamento ilegível não pode derrubar a tela inteira antes de o orçamentista sequer
    chegar nele.
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
        "address": round_record.address,
        "revision_id": None if revision is None else revision.id,
        "revision_version": None if revision is None else revision.version,
        "cascade": cascade_entry_payload(cascade_entries(round_record)),
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
        "estimate": {
            "present": "estimate_json" in digests,
            "estimate_sha256": digests.get("estimate_json"),
            "workbook_present": estimate_workbook_ref(revision) is not None,
            "workbook_sha256": digests.get(ESTIMATE_WORKBOOK_DIGEST),
        },
        "created_at": round_record.created_at.isoformat(),
        "updated_at": round_record.updated_at.isoformat(),
    }
