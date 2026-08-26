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

O que este contexto NÃO tem, de propósito: contrato, saldo e período. Nada disso existe
antes da licitação, e o `Estimate` não passa — nem tenta passar — pelo portão de exportação
da medição, que recebe o contrato por parâmetro.

Aprovação, essa existe e é PRÓPRIA (ADR-0046): montar não publica mais nada, assinar é ato
nominal do papel `aprovador` e despachar é ato do `orcamentista` atrás do portão do domínio
(`Estimate.ensure_exportable()`). É a assinatura sem contrato que mantém a fronteira do
ADR-0027 de pé — saldo, período e código no contrato não têm por onde entrar aqui.
"""

from __future__ import annotations

import copy
import hashlib
import json
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Final

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from croquito_api.database import EstimateRoundRecord, EstimateRoundRevisionRecord
from croquito_api.journeys import ESTIMATE_APPROVER_ROLE
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
from croquito_valuation.calc_matrix import CalcMatrix
from croquito_valuation.catalog import default_domain_synonyms, default_legend_noise
from croquito_valuation.errors import ValuationValidationError
from croquito_valuation.estimate import Estimate, EstimateApproval, EstimateApproverDecision
from croquito_valuation.estimate_workbook import (
    EstimateAuditReport,
    audit_estimate_workbook,
    write_estimate_workbook,
)
from croquito_valuation.models import PriceCatalog, PriceOrigin
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
from croquito_worker.valuation.suggestions import SemanticArmTelemetry

ESTIMATE_CASCADE_ORIGIN_DUPLICATE: Final = "ESTIMATE_CASCADE_ORIGIN_DUPLICATE"
ESTIMATE_CASCADE_ORDER_INVALID: Final = "ESTIMATE_CASCADE_ORDER_INVALID"
ESTIMATE_CASCADE_LOCKED: Final = "ESTIMATE_CASCADE_LOCKED"
ESTIMATE_WORKBOOK_AUDIT_FAILED: Final = "ESTIMATE_WORKBOOK_AUDIT_FAILED"
ESTIMATE_BDI_INVALID: Final = "ESTIMATE_BDI_INVALID"
ESTIMATE_TARGET_INVALID: Final = "ESTIMATE_TARGET_INVALID"
ESTIMATE_CASCADE_ORIGIN_FORBIDDEN: Final = "ESTIMATE_CASCADE_ORIGIN_FORBIDDEN"
ESTIMATE_CATALOG_SOURCE_INVALID: Final = "ESTIMATE_CATALOG_SOURCE_INVALID"
ESTIMATE_REGIME_CASCADE_DIRTY: Final = "ESTIMATE_REGIME_CASCADE_DIRTY"
ESTIMATE_REGIME_IRREVERSIBLE: Final = "ESTIMATE_REGIME_IRREVERSIBLE"
ESTIMATE_SELF_APPROVAL_FORBIDDEN: Final = "ESTIMATE_SELF_APPROVAL_FORBIDDEN"
ESTIMATE_APPROVAL_AUTHOR_UNKNOWN: Final = "ESTIMATE_APPROVAL_AUTHOR_UNKNOWN"

REGIME_CONTRACTED_DEMAND: Final = "contracted_demand"
ESTIMATE_BDI_FORBIDDEN_UNDER_REGIME: Final = "ESTIMATE_BDI_FORBIDDEN_UNDER_REGIME"
"""Único regime GRAVÁVEL (ADR-0045): a demanda orçada dentro de contrato já licitado.

Não há constante para "pré-licitação" porque ela não é um valor: é a ausência de regime.
A fronteira `/v1` aceita a palavra `pre_bid` no corpo só para poder recusá-la com código
estável (`SetEstimateRegimeRequest`), e ela nunca chega a esta camada como algo gravável —
qualquer regime que não seja este recusa em `ensure_regime_declarable`."""

REGIME_ALLOWED_ORIGINS: Final[tuple[str, ...]] = (PriceOrigin.SCO.value,)
"""Origens que a cascata aceita sob o regime. Uma só, e é a tabela contratual (ADR-0045).

Restringir a origem NÃO confere o contrato: garante que o preço veio do SCO, não que veio
da tabela, data-base e desconto daquele contrato. A lacuna está nomeada no ADR-0045."""

PROVENANCE_REFERENCE_CATALOG: Final = "reference_catalog"
"""A fonte veio do acervo da plataforma: alguém publicou aquele arquivo para todos."""

PROVENANCE_TENANT_UPLOAD: Final = "tenant_upload"
"""A fonte é tabela PRÓPRIA do cliente, subida por ele — a EMOP que ele licenciou, o
catálogo de um contrato específico. É o caminho que existia antes da F-037, e por isso é
como se lê a ausência do campo numa cascata instalada antes dela: era o único que havia."""

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
    "calc_matrix_json",
    "extraction_lineage_json",
)
"""Colunas JSON de artefato; ausentes são `NULL`, e `NULL` é "a etapa não aconteceu"."""

REVISION_MAP_COLUMNS: Final[tuple[str, ...]] = ("artifact_refs_json", "artifact_digests_json")
"""Colunas de mapa; ausentes são `{}`, nunca `NULL` (é o default da coluna)."""

REVISION_SCALAR_COLUMNS: Final[tuple[str, ...]] = ("estimate_built_by",)
"""Colunas ESCALARES carregadas adiante; ausentes são `NULL`.

Terceira categoria, e não um apêndice das duas anteriores (F-035, ADR-0046 decisão 6).
`estimate_built_by` é um `str | None`: não é artefato JSON — `_artifact_digests` percorre
`REVISION_DOCUMENT_COLUMNS` e publicaria um digest de identidade no estado da rodada, e
`require_document` passaria a aceitar o nome de uma coluna que não guarda documento — nem é
mapa, cujo default `{}` não faz sentido para um escalar. O que ela compartilha com as duas é
só o carregamento adiante do `append_revision`, e é exatamente isso que a lista declara."""

REVISION_COLUMNS: Final[tuple[str, ...]] = (
    REVISION_DOCUMENT_COLUMNS + REVISION_MAP_COLUMNS + REVISION_SCALAR_COLUMNS
)

_CASCADE_ENTRY_FIELDS: Final[tuple[str, ...]] = (
    "object_key",
    "object_sha256",
    "source_sha256",
    "origin",
    "reference_month",
    "source_label",
)
"""Campos que TODA entrada tem, venha o arquivo de onde vier."""

_CASCADE_SOURCE_FIELDS: Final[tuple[str, ...]] = ("upload_id", "reference_catalog_id")
"""Identificadores de fonte: exatamente UM por entrada, e é ele que diz de onde o arquivo
veio. Entrada anterior à F-037 só tem `upload_id`, e continua satisfazendo a regra."""


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


def cascade_origin_forbidden(origin: str) -> RoundRefusal:
    """Origem fora da tabela contratual numa rodada sob contrato (ADR-0045, decisão 3).

    Recusa na INSTALAÇÃO, no mesmo ponto em que `ESTIMATE_CASCADE_ORIGIN_DUPLICATE` recusa,
    porque é aqui que ainda há o que corrigir. Deixar a fonte entrar levaria o preço dela
    até um orçamento aprovado e uma obra executada, e só a medição recusaria
    (`BULLETIN_PRICE_ORIGIN_FORBIDDEN`) — sobre serviço já feito, quando a única saída é
    aditivo. O guardrail da medição continua existindo; ele deixa de ser o primeiro a ver.
    """
    return RoundRefusal(
        409,
        ESTIMATE_CASCADE_ORIGIN_FORBIDDEN,
        "a rodada corre sob contrato licitado e só aceita preço da tabela contratual; "
        "um preço desta fonte seria recusado na medição, sobre serviço já executado",
        {"origin": origin, "allowed_origins": list(REGIME_ALLOWED_ORIGINS)},
    )


def bdi_required() -> RoundRefusal:
    """Fora do regime o BDI é obrigatório: assumir zero inventaria a decisão da planilha."""
    return RoundRefusal(
        422,
        ESTIMATE_BDI_INVALID,
        "o BDI do orçamento é obrigatório fora da demanda contratada",
        {},
    )


def resolve_bdi_percent(raw: str | None, *, regime: str | None) -> Decimal:
    """O BDI do orçamento, com a regra do regime aplicada num lugar só.

    Sob demanda contratada a tabela contratual já embute o BDI, então:

    - **ausente** vale zero, e é o caminho normal — pedir que alguém digite um número que só
      pode ser zero é fricção sem informação;
    - **declarado não-zero** recusa, porque é a duplicação que o ADR-0048 decisão 3 fecha.
      Zerar em silêncio um número que o orçamentista escreveu mudaria o total sem que
      ninguém soubesse por quê.

    Fora do regime nada muda: o BDI continua obrigatório.
    """
    if raw is None:
        if regime == REGIME_CONTRACTED_DEMAND:
            return Decimal("0")
        raise bdi_required()
    percent = parse_bdi_percent(raw)
    if regime == REGIME_CONTRACTED_DEMAND and percent != 0:
        raise bdi_forbidden_under_regime(percent)
    return percent


def bdi_forbidden_under_regime(bdi_percent: Decimal) -> RoundRefusal:
    """Sob demanda contratada o preço da tabela JÁ embute o BDI; aplicá-lo de novo é erro.

    É a mesma razão que o [ADR-0038](../../../docs/adr/0038-bdi-como-conceito-de-pre-licitacao.md)
    usou para manter o BDI fora da medição — "o preço contratado já embute BDI; aplicá-lo de
    novo é erro de domínio" —, aplicada agora ao orçamento que corre sob o regime. A F-033
    restringiu a cascata a `sco` sem tocar no BDI, e o defeito ficou aberto até o ADR-0048.

    Recusa em vez de zerar em silêncio: o número que o orçamentista digitou é uma declaração,
    e corrigi-la por baixo faria o total mudar sem que ninguém soubesse por quê.
    """
    return RoundRefusal(
        422,
        ESTIMATE_BDI_FORBIDDEN_UNDER_REGIME,
        "sob demanda contratada o preço da tabela contratual já embute o BDI; declare zero",
        {"bdi_percent": str(bdi_percent)},
    )


def regime_cascade_dirty(origins: Sequence[str]) -> RoundRefusal:
    """Declaração recusada enquanto houver fonte proibida instalada (ADR-0045, decisão 4).

    Nada é reescrito e nada é gravado. Aceitar a declaração barrando só as instalações
    futuras deixaria existir rodada "sob contrato" com EMOP dentro — precisamente o estado
    que a decisão torna impossível. A saída é remover a fonte pelo caminho que já existe
    (`POST .../catalogs/remove`), que é ato humano com as suas próprias travas.
    """
    return RoundRefusal(
        409,
        ESTIMATE_REGIME_CASCADE_DIRTY,
        "a cascata tem fonte fora da tabela contratual; remova a fonte antes de declarar "
        "que a rodada corre sob contrato licitado — nada foi gravado",
        {"origins": list(origins), "allowed_origins": list(REGIME_ALLOWED_ORIGINS)},
    )


def regime_irreversible(regime: str, *, current: str | None) -> RoundRefusal:
    """Pré-licitação não é valor declarável: o regime é mão única (decisão humana 2026-08-22).

    Vale para os dois casos, e por isso um código só: rodada já sob contrato não volta
    atrás — voltar devolveria a permissão de instalar a fonte que ela foi impedida de
    instalar, com as decisões de código tomadas sob a outra regra ainda de pé —, e rodada
    sem regime não "declara pré-licitação", porque ausência é a falta do regime, não um
    valor. Enganar-se ao declarar se corrige abrindo outra rodada, não desdizendo esta.
    """
    return RoundRefusal(
        409,
        ESTIMATE_REGIME_IRREVERSIBLE,
        "pré-licitação não é regime declarável: a ausência de regime já é ela, e uma "
        "rodada declarada sob contrato licitado não volta atrás",
        {"requested_regime": regime, "current_regime": current},
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


def parse_target_amount(raw: str) -> Decimal:
    """`Decimal` do teto de verba informado; texto ilegível, infinito ou não positivo recusam.

    "Sem teto" é AUSÊNCIA do campo, nunca zero (ADR-0040, decisão 1): a tela recusa `0,00`
    na declaração, e o servidor recusa aqui com o mesmo código único — zero ou negativo não
    chegam a virar coluna no banco.
    """
    try:
        amount = Decimal(raw)
    except InvalidOperation as error:
        raise RoundRefusal(
            422,
            ESTIMATE_TARGET_INVALID,
            "o teto de verba informado não é um número decimal exato",
            {},
        ) from error
    if not amount.is_finite() or amount <= 0:
        raise RoundRefusal(
            422,
            ESTIMATE_TARGET_INVALID,
            "o teto de verba é um valor decimal finito e maior que zero",
            {},
        )
    return amount


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

    São TRÊS categorias de coluna, não duas: documento (`NULL` quando ausente), mapa (`{}`
    quando ausente) e escalar (`NULL` quando ausente). A terceira nasceu com
    `estimate_built_by` (ADR-0046, decisão 6) porque um `str | None` não é artefato nem
    mapa; o que ele compartilha com os outros é só ser carregado adiante quando o ato não o
    muda, que é o que faz "quem montou" sobreviver a uma aprovação e a uma exportação.
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
    provenance: str
    """De onde veio o ARQUIVO desta fonte: `reference_catalog` (o acervo da plataforma) ou
    `tenant_upload` (tabela própria, subida pelo cliente). É o fato de quem publicou o
    arquivo, e não de onde o preço vem — isso é `origin`. Uma proveniência que não
    distinguisse os dois mentiria sobre a origem do preço (ADR-0047 decisão 7)."""
    upload_id: str | None
    """Preenchido só na tabela própria; `None` quando a fonte veio do acervo."""
    reference_catalog_id: str | None
    """Preenchido só no acervo; `None` quando a fonte é tabela própria do cliente."""
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
        """A entrada como a tela a lê; `object_key` e os dois identificadores de fonte não
        saem daqui.

        A chave do objeto é referência interna do store: publicá-la daria ao cliente o
        endereço de um artefato que ele só pode ler por URL assinada. O que sai é a
        `provenance` — o FATO de quem publicou o arquivo, que a tela mostra ao lado da
        fonte —, e não o identificador do upload ou da linha do acervo que o carrega.
        """
        return {
            "position": self.position,
            "provenance": self.provenance,
            "origin": self.origin,
            "source_sha256": self.source_sha256,
            "reference_month": self.reference_month,
            "source_label": self.source_label,
            "summary": dict(self.summary),
        }


def _entry_provenance(
    raw: Mapping[str, Any], *, source_field: str, round_record: EstimateRoundRecord, position: int
) -> str:
    """A procedência gravada, conferida contra o identificador de fonte que a entrada tem.

    Ausência é o caso legítimo — toda entrada instalada antes da F-037 — e por isso não
    recusa: ela é derivada do identificador presente, que naquelas entradas é sempre o do
    upload. Valor desconhecido, ou que CONTRADIZ o identificador, recusa: rotular a fonte
    com uma procedência que o próprio registro desmente seria mentir sobre quem publicou o
    arquivo, que é justamente o que este campo existe para não deixar acontecer.
    """
    derived = (
        PROVENANCE_REFERENCE_CATALOG
        if source_field == "reference_catalog_id"
        else PROVENANCE_TENANT_UPLOAD
    )
    declared = raw.get("provenance")
    if declared is None:
        return derived
    if declared != derived:
        raise catalog_required(
            "a fonte instalada nesta posição declara uma procedência que o registro não sustenta",
            {"round_id": round_record.id, "position": position},
        )
    return str(declared)


def cascade_entries(round_record: EstimateRoundRecord) -> list[CascadeEntry]:
    """A cascata instalada, na ordem gravada. Lista vazia é a rodada recém-aberta.

    Entrada malformada recusa com `CATALOG_REQUIRED`, e não com erro de servidor: quem
    escreve esta coluna é a rota de instalação, então um registro que não decodifica é
    falha de ambiente (dado adulterado, migração incompleta) e não do ato corrente.

    Entrada instalada ANTES da F-037 não tem `provenance` nem `reference_catalog_id`: ela
    tem `upload_id`, e a ausência lê como tabela própria — que é o que ela é, porque era o
    único caminho que existia. Nada é reescrito retroativamente.
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
        sources = [field for field in _CASCADE_SOURCE_FIELDS if isinstance(raw.get(field), str)]
        if len(sources) != 1:
            raise catalog_required(
                "a fonte instalada nesta posição não declara de onde o arquivo veio",
                {"round_id": round_record.id, "position": position},
            )
        provenance = _entry_provenance(
            raw, source_field=sources[0], round_record=round_record, position=position
        )
        summary = raw.get("summary")
        upload_id = raw.get("upload_id")
        reference_catalog_id = raw.get("reference_catalog_id")
        entries.append(
            CascadeEntry(
                position=position,
                provenance=provenance,
                upload_id=None if upload_id is None else str(upload_id),
                reference_catalog_id=(
                    None if reference_catalog_id is None else str(reference_catalog_id)
                ),
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


def forbidden_cascade_origins(entries: Sequence[CascadeEntry]) -> list[str]:
    """Origens instaladas que o regime não aceita, ordenadas; vazio é cascata limpa."""
    return sorted({entry.origin for entry in entries if entry.origin not in REGIME_ALLOWED_ORIGINS})


def ensure_regime_declarable(
    regime: str, *, current: str | None, entries: Sequence[CascadeEntry]
) -> None:
    """As duas recusas da DECLARAÇÃO do regime (ADR-0045, decisão 4 + mão única do plano).

    A ordem importa: o valor é conferido antes da cascata, porque uma tentativa de voltar
    para pré-licitação é recusada pelo que ela pede, não pelo estado da cascata — e o
    contrário faria a mesma tentativa devolver códigos diferentes conforme o que estivesse
    instalado.

    Serve a criação da rodada e a rota de declaração com a MESMA regra: na criação a
    cascata é vazia por construção, e passar `entries=()` ali é dizer isso, não abrir
    exceção. Nada é gravado por esta função; ela só recusa.
    """
    if regime != REGIME_CONTRACTED_DEMAND:
        raise regime_irreversible(regime, current=current)
    forbidden = forbidden_cascade_origins(entries)
    if forbidden:
        raise regime_cascade_dirty(forbidden)


def origin_allowed_under_regime(origin: str, *, regime: str | None) -> bool:
    """A origem entra na cascata desta rodada? UMA formulação da regra, para dois usos.

    A instalação recusa por ela (`ensure_source_installable`) e a escolha do acervo filtra
    por ela: oferecer na lista uma tabela que a instalação vai recusar é oferecer uma
    recusa. Duas cópias da condição divergiriam no dia em que o regime mudasse, e a tela
    descobriria a divergência num `409`.
    """
    return regime != REGIME_CONTRACTED_DEMAND or origin in REGIME_ALLOWED_ORIGINS


def ensure_source_installable(
    entries: Sequence[CascadeEntry], catalog: PriceCatalog, *, regime: str | None
) -> None:
    """Três recusas antes de instalar: uma do regime e duas sobre identificar a fonte.

    A do regime vem primeiro e é a mais grosseira (ADR-0045, decisão 3): sob contrato
    licitado, fonte fora da tabela contratual não entra de jeito nenhum, seja ela a
    primeira daquela origem ou não. `regime=None` é a rodada de pré-licitação, e para ela
    nada muda — a cascata segue livre, como antes desta decisão.

    A segunda é a do domínio: uma origem por cascata, senão "o preço veio da EMOP" deixa
    de dizer de qual arquivo ele veio.

    A terceira é a que o domínio não tem como ver daqui: dois catálogos de ORIGENS
    diferentes importados do MESMO arquivo de origem teriam o mesmo `source_sha256` — e é
    esse digest que a confirmação de código cita, que a reordenação recebe e que
    `build_worksite_estimate` usa para achar o catálogo. Com dois candidatos, a citação
    passa a apontar para qualquer um dos dois, e nem a reordenação nem o orçamento
    conseguiriam distinguir a fonte. É recusa de instalação porque é aí que o segundo
    aparece; depois já não haveria o que corrigir sem abrir rodada nova.
    """
    if not origin_allowed_under_regime(catalog.origin.value, regime=regime):
        raise cascade_origin_forbidden(catalog.origin.value)
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
    provenance: str,
    upload_id: str | None,
    reference_catalog_id: str | None,
    object_key: str,
    object_sha256: str,
    catalog: PriceCatalog,
    summary: Mapping[str, Any],
) -> dict[str, Any]:
    """A entrada nova da cascata, com os metadados lidos do catálogo já validado.

    O identificador da fonte é gravado no campo do caminho que a instalou, e só nele: a
    entrada do acervo não tem `upload_id` porque não houve upload, e a de tabela própria
    não tem `reference_catalog_id` porque não há linha de acervo. Guardar uma chave vazia
    no campo do outro caminho faria a leitura ter de distinguir "vazio" de "ausente".
    """
    return {
        "provenance": provenance,
        **({} if upload_id is None else {"upload_id": upload_id}),
        **({} if reference_catalog_id is None else {"reference_catalog_id": reference_catalog_id}),
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
    """A entrada de volta na forma gravada; `position` não entra, porque é a ordem da lista.

    A procedência viaja junto: reordenar e remover mexem na cascata, nunca em de onde o
    arquivo de cada fonte veio.
    """
    return {
        "provenance": entry.provenance,
        **({} if entry.upload_id is None else {"upload_id": entry.upload_id}),
        **(
            {}
            if entry.reference_catalog_id is None
            else {"reference_catalog_id": entry.reference_catalog_id}
        ),
        "object_key": entry.object_key,
        "object_sha256": entry.object_sha256,
        "source_sha256": entry.source_sha256,
        "origin": entry.origin,
        "reference_month": entry.reference_month,
        "source_label": entry.source_label,
        "summary": dict(entry.summary),
    }


def removed_cascade(entries: Sequence[CascadeEntry], source_sha256: str) -> list[dict[str, Any]]:
    """A cascata sem a fonte citada; o digest tem de estar entre as fontes instaladas.

    Mesmo código de recusa da reordenação (`ESTIMATE_CASCADE_ORDER_INVALID`) para o mesmo
    motivo: o corpo cita uma fonte que a cascata instalada não reconhece. Não é código
    novo — a rota de ordem já usa esta condição para "o corpo não corresponde às fontes
    instaladas", e remover um digest desconhecido é o mesmo caso.
    """
    if not any(entry.source_sha256 == source_sha256 for entry in entries):
        raise cascade_order_invalid(
            "a fonte informada não está instalada nesta rodada",
            {"expected": [entry.source_sha256 for entry in entries]},
        )
    return [_entry_document(entry) for entry in entries if entry.source_sha256 != source_sha256]


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


def require_cascade_source_unlocked(
    revision: EstimateRoundRevisionRecord | None, source_sha256: str
) -> None:
    """Recusa remover uma fonte que alguma decisão de código já citou.

    Mesmo código de `require_cascade_unlocked` (`ESTIMATE_CASCADE_LOCKED`), mas por FONTE
    em vez de pela cascata inteira: reordenar mexe na posição de TODAS as fontes, então
    qualquer decisão registrada já trava a reordenação; remover só tira UMA fonte, e por
    isso só trava quando a decisão citou justamente essa (`CodeAssignment.catalog_sha256`,
    `assignment.py`). Remover uma fonte que nenhuma decisão usou não invalida nada.
    """
    assignments = assignments_of(revision)
    if assignments is None:
        return
    cited = {
        assignment.catalog_sha256
        for assignment in assignments.assignments
        if assignment.catalog_sha256 is not None
    }
    if source_sha256 in cited:
        raise RoundRefusal(
            409,
            ESTIMATE_CASCADE_LOCKED,
            "esta fonte já foi citada por decisão de código registrada: removê-la "
            "invalidaria as decisões registradas, e apagar decisão do orçamentista não é "
            "ato desta API",
            {"source_sha256": source_sha256},
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


def matrix_of(revision: EstimateRoundRevisionRecord | None) -> CalcMatrix | None:
    """A `CalcMatrix` gravada nesta revisão (ADR-0053), ou `None` no regime legado.

    Espelho de `assignments_of`: relê o artefato guardado no build, com a guarda de ciclo do
    próprio `CalcMatrix` rodando de novo na leitura. `NULL` é código único por item."""
    if revision is None or revision.calc_matrix_json is None:
        return None
    return CalcMatrix.model_validate(revision.calc_matrix_json)


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
) -> tuple[CodeSuggestionSet, list[str], SemanticArmTelemetry]:
    """Shortlist recalculada do zero sobre a CASCATA; nenhuma chamada paga acontece.

    Os candidatos saem na ordem da cascata — todos os da primeira fonte, depois os da
    segunda — porque misturar os blocos por score faria a ordem das fontes, que é decisão
    declarada do orçamentista, ser desempatada por similaridade de texto. O braço semântico
    é declarado indisponível pelo mesmo motivo da medição: nenhuma rota de `/v1` publica
    índice de embeddings.

    A terceira saída é a telemetria do braço semântico. `sources_total` é o tamanho da
    cascata e `sources_with_index` é zero: nenhuma fonte tem índice publicado hoje, então
    nenhuma pagou embedding. É isso que o recompute registra — quantas fontes da cascata
    tinham índice —, e o número passa a ser real quando o índice por fonte (ADR-0054 D5)
    chegar ao caminho hospedado.
    """
    return (
        suggest_codes_over_cascade(packet, cascade, synonyms=default_domain_synonyms()),
        [SEMANTIC_ARM_ABSENT],
        SemanticArmTelemetry.lexical_only(SEMANTIC_ARM_ABSENT, sources_total=len(cascade)),
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


# --- aprovação nominal --------------------------------------------------------------------


APPROVAL_ACTION: Final = "confirm"
"""A única decisão que a rota de aprovação escreve.

`EstimateApproverDecision` aceita `reject` como o irmão da medição, e a recusa registrada
continua sem existir no produto pelo mesmo motivo de lá: ninguém decidiu o que ela destrava
na tela, e o Design Approval Package da F-035 não a desenha. Nada é escrito como reservado.
"""


def _approval_decision_id(*, approver_id: str, decided_at: datetime, estimate_digest: str) -> str:
    """Id determinístico do ato, no molde de `_approval_decision_id` da medição (prefixo
    `ed_`).

    Deriva do que o ato É — quem assinou, quando, sobre qual conteúdo —, e não de um contador
    ou de um relógio próprio: dois processos que registrassem o mesmo ato produziriam o mesmo
    id, e um id que muda sem o ato mudar não identifica nada.
    """
    canonical = json.dumps(
        {
            "action": APPROVAL_ACTION,
            "approver_id": approver_id,
            "approver_role": ESTIMATE_APPROVER_ROLE,
            "decided_at": decided_at.isoformat(),
            "estimate_digest": estimate_digest,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"ed_{hashlib.sha256(canonical.encode()).hexdigest()[:16]}"


def approve_estimate(estimate: Estimate, *, approver_id: str, decided_at: datetime) -> Estimate:
    """O MESMO orçamento com a aprovação nominal embutida, amarrada por digest ao conteúdo.

    O vínculo é o `content_digest()` do próprio domínio, que exclui `approval` do cálculo:
    assinar não muda o que foi assinado, e por isso o digest gravado continua conferindo com
    o do orçamento depois do ato. Qualquer ato POSTERIOR que remonte o orçamento faz os dois
    divergirem, e é o portão de exportação — nunca esta função — que lê essa divergência como
    `APPROVAL_CONTENT_MISMATCH`.

    Identidade e instante são do SERVIDOR: `approver_id` é o subject do JWT e `decided_at` é
    o relógio do processo. Nenhum dos dois viaja no corpo (critério 4 da F-035), e por isso
    esta função os recebe por parâmetro nomeado em vez de aceitar uma decisão pronta.

    A cópia não revalida o orçamento de propósito: quem entra aqui já foi revalidado pela
    leitura (`Estimate.model_validate`), o único campo que muda é `approval`, e nenhuma
    invariante de linha, BDI ou memória de cálculo depende dele.
    """
    estimate_digest = estimate.content_digest()
    approval = EstimateApproval(
        decision=EstimateApproverDecision(
            decision_id=_approval_decision_id(
                approver_id=approver_id,
                decided_at=decided_at,
                estimate_digest=estimate_digest,
            ),
            action=APPROVAL_ACTION,
            approver_id=approver_id,
            approver_role=ESTIMATE_APPROVER_ROLE,
            decided_at=decided_at,
        ),
        estimate_digest=estimate_digest,
    )
    return estimate.model_copy(update={"approval": approval})


def approval_payload(estimate: Estimate) -> dict[str, Any]:
    """O bloco de aprovação que a tela lê, com a caducidade DERIVADA na leitura.

    `stale` nunca é gravado, pela mesma razão da medição: ele é a relação entre dois digests
    que só existe no instante da leitura. Aprovação caduca é o estado que o desenho aprovado
    da F-035 mostra por extenso — os dois digests lado a lado e uma única saída, aprovar de
    novo —, e escondê-lo faria a tela oferecer um despacho que a rota já sabe que vai recusar
    com `APPROVAL_CONTENT_MISMATCH`.
    """
    approval = estimate.approval
    current_digest = estimate.content_digest()
    if approval is None:
        return {
            "approved": False,
            "approved_by": None,
            "approved_at": None,
            "approved_digest": None,
            "current_digest": current_digest,
            "stale": False,
        }
    return {
        "approved": approval.decision.action == APPROVAL_ACTION,
        "approved_by": approval.decision.approver_id,
        "approved_at": approval.decision.decided_at.isoformat(),
        "approved_digest": approval.estimate_digest,
        "current_digest": current_digest,
        "stale": approval.estimate_digest != current_digest,
    }


def approval_state(estimate: Estimate | None) -> dict[str, Any]:
    """Bloco `{approval}` no estado da rodada, no padrão de `target_state`/`regime_state`.

    Sem orçamento legível na cabeça, o dicionário volta VAZIO — a chave não aparece, como o
    teto ausente não aparece. Ausência não é um valor, e devolver `"approval": null` faria a
    tela ter de distinguir "não há orçamento" de "há orçamento sem assinatura", que é
    justamente o que `approved: false` já diz.
    """
    if estimate is None:
        return {}
    return {"approval": approval_payload(estimate)}


def readable_estimate(revision: EstimateRoundRevisionRecord | None) -> Estimate | None:
    """O orçamento gravado, ou `None` quando ele não existe **ou não valida mais**.

    Espelha `readable_valuation`: o estado por etapa não pode derrubar a tela inteira por
    causa de um artefato que deixou de validar, e quem SERVE o orçamento (`GET .../estimate`)
    não passa por aqui — lá, artefato ilegível é `422`, porque ninguém lê orçamento que o
    domínio não valida.
    """
    if revision is None or revision.estimate_json is None:
        return None
    try:
        return Estimate.model_validate(dict(revision.estimate_json))
    except (ValuationValidationError, ValidationError):
        return None


def carry_approval_forward(estimate: Estimate, previous: Estimate | None) -> Estimate:
    """Leva a aprovação anterior adiante no orçamento recém-montado. Preservar NÃO é aprovar.

    A aprovação carregada continua apontando para o digest ANTIGO, e o orçamento novo tem
    outro conteúdo — ele nasce, portanto, CADUCO por construção, e o portão de exportação o
    recusa com `APPROVAL_CONTENT_MISMATCH`. Em momento algum ela autoriza o conteúdo novo: o
    que ela faz é manter visível que uma aprovação existiu e deixou de cobrir o que está na
    tela (ADR-0046, decisão 8).

    Descartá-la seria perder essa informação em silêncio. Quem remontasse depois de assinar
    veria "não aprovado", como se ninguém nunca tivesse assinado, e a tela não teria como
    oferecer a única saída correta — aprovar de novo, ciente de que o conteúdo mudou.

    Nada disso é decisão do DOMÍNIO: `build_worksite_estimate` continua montando orçamento
    sem aprovação nenhuma, que é o certo para uma função que só sabe calcular. Quem tem a
    revisão anterior em mãos, e portanto pode responder "houve aprovação antes?", é a rota.
    """
    if previous is None or previous.approval is None:
        return estimate
    return estimate.model_copy(update={"approval": previous.approval})


def estimate_built_by(revision: EstimateRoundRevisionRecord | None) -> str | None:
    """Quem montou o orçamento da cabeça, ou `None` quando ninguém o montou."""
    if revision is None:
        return None
    author = revision.estimate_built_by
    return author if isinstance(author, str) and author else None


def self_approval_forbidden() -> RoundRefusal:
    """Quem montou o orçamento não o assina (ADR-0046, decisão 6).

    A recusa compara IDENTIDADE, não papel: acumular `orcamentista` e `aprovador` no mesmo
    token não contorna, porque sem isso o papel novo seria cerimônia — bastaria atribuir os
    dois a uma pessoa para a segregação evaporar sem deixar rastro.

    O detalhe não diz quem montou. Devolver o subject de outra pessoa transformaria uma
    recusa de autorização num diretório de usuários do tenant.
    """
    return RoundRefusal(
        403,
        ESTIMATE_SELF_APPROVAL_FORBIDDEN,
        "quem montou o orçamento não pode aprová-lo; a assinatura é de outra pessoa",
        {},
    )


def approval_missing_author() -> RoundRefusal:
    """Orçamento montado sem registro de autor: não há contra quem conferir a segregação.

    É o caso de uma rodada montada antes desta feature, cuja revisão não tem
    `estimate_built_by`. Recusar fechado é a única resposta honesta — aprovar assumindo que
    o autor é outra pessoa seria justamente a auto-aprovação silenciosa que a decisão 6
    proíbe. A saída é remontar o orçamento, que é ato normal da jornada.
    """
    return RoundRefusal(
        409,
        ESTIMATE_APPROVAL_AUTHOR_UNKNOWN,
        "o orçamento da cabeça não registra quem o montou; remonte antes de aprovar",
        {},
    )


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

    O digest que entra aqui é o `content_digest()` do domínio, que EXCLUI a aprovação, e não
    o digest do documento gravado (F-035): a planilha é do conteúdo orçado, e assinar não
    muda esse conteúdo. Com o digest do documento, aprovar mudaria o endereço da mesma
    planilha, e o `.xlsx` publicado depois da assinatura deixaria de ser endereçável pelo que
    foi assinado.
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


def target_state(
    round_record: EstimateRoundRecord,
    revision: EstimateRoundRevisionRecord | None,
) -> dict[str, Any]:
    """Bloco `{target, consumed, remaining, over}` derivado na leitura (ADR-0040, decisão 2).

    Sem teto, o dicionário volta VAZIO — nenhuma das quatro chaves aparece (decisão 6). Com
    teto e sem `estimate_json` na cabeça, só `target` aparece: o consumo depende do
    `total_amount` que só existe depois da montagem. `consumed` é o texto do documento como
    está, e `remaining`/`over` comparam esse texto contra o teto — nada aqui recomputa
    dinheiro; o `total_amount` é lido, nunca refeito.
    """
    if round_record.target_amount is None:
        return {}
    state: dict[str, Any] = {
        "target": {"amount": round_record.target_amount, "label": round_record.target_label}
    }
    document = None if revision is None else revision.estimate_json
    if document is None:
        return state
    consumed_raw = document["total_amount"]
    target_decimal = Decimal(round_record.target_amount)
    consumed_decimal = Decimal(str(consumed_raw))
    state["consumed"] = str(consumed_raw)
    state["remaining"] = str(target_decimal - consumed_decimal)
    # Estrito: o limite exato NÃO é estouro (ADR-0040, decisão 3).
    state["over"] = consumed_decimal > target_decimal
    return state


def regime_state(
    round_record: EstimateRoundRecord,
    assignments: CodeAssignmentSet | None,
) -> dict[str, Any]:
    """Bloco `{regime}` derivado na leitura, no molde do `target_state` (ADR-0045).

    Sem regime declarado, o dicionário volta VAZIO — a chave não aparece, como o teto
    ausente não aparece. Ausência não é um valor, e devolver `{"regime": null}` faria a
    tela ter de distinguir "não declarado" de "declarado como nada".

    `allowed_cascade_origins` sai do servidor porque a regra é do servidor: a tela oferece
    o que a instalação aceitaria, em vez de guardar a sua própria cópia da lista e
    descobrir a divergência numa recusa.

    `amendment_candidates` é `codes.rejected` LIDO SOB O REGIME — o mesmo número, do mesmo
    conjunto, no mesmo instante de leitura, e por isso não pode divergir dele. O que muda é
    o significado: sob contrato, item cuja confirmação de código foi rejeitada é candidato
    a aditivo (ADR-0045, decisão 5). O sinal vem do julgamento de quem revisou — "a
    orçamentista não achou código na tabela contratual" —, nunca de uma conferência contra
    um contrato que o orçamento não modela. Fora do regime a rejeição continua sendo só
    rejeição, e por isso o número não aparece.
    """
    if round_record.pricing_regime is None:
        return {}
    return {
        "regime": {
            "value": round_record.pricing_regime,
            "allowed_cascade_origins": list(REGIME_ALLOWED_ORIGINS),
            "amendment_candidates": (
                0 if assignments is None else count_status(assignments, "rejected")
            ),
        }
    }


def round_state_payload(
    round_record: EstimateRoundRecord,
    revision: EstimateRoundRevisionRecord | None,
) -> dict[str, Any]:
    """Estado da rodada por etapa, espelhando o da medição com a cascata no lugar do catálogo.

    A etapa entra por PRESENÇA e digest; revalidar o orçamento é papel de quem o serve. Um
    orçamento ilegível não pode derrubar a tela inteira antes de o orçamentista sequer
    chegar nele.

    O bloco de aprovação é a única coisa aqui que precisa LER o orçamento, porque o vínculo
    da assinatura é um digest do conteúdo e não uma coluna. A leitura é a tolerante
    (`readable_estimate`): artefato que não valida sai como bloco AUSENTE, e não derruba o
    estado da rodada.
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
        **approval_state(readable_estimate(revision)),
        **target_state(round_record, revision),
        **regime_state(round_record, assignments),
        "created_at": round_record.created_at.isoformat(),
        "updated_at": round_record.updated_at.isoformat(),
    }
