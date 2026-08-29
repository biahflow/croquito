"""Núcleo de aplicação da rodada de medição: o que a rota decide antes de existir HTTP.

Este módulo é a camada de aplicação de `/v1/valuation-rounds` (ADR-0028) **sem** FastAPI:
nada aqui recebe `Request`, monta `Response` ou conhece código de status por si só. O que
mora aqui é o que precisa ser testável sem subir a aplicação — leitura da cabeça da
rodada, o append da revisão nova, o estado por etapa que a tela lê, as precondições da
cadeia, as duas fronteiras de artefato (catálogo lido do object store, URL assinada de
leitura privada) e as duas saídas derivadas da etapa de código (shortlist e busca), que
chamam os módulos puros do worker com o que a rodada de `/v1` tem — e só com isso.

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
import json
import os
import tempfile
import threading
import zipfile
from collections import OrderedDict
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Any, Final, Protocol, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from croquito_api.database import (
    ValuationRoundPlateRecord,
    ValuationRoundRecord,
    ValuationRoundRevisionRecord,
)
from croquito_core.ids import new_uuid7
from croquito_valuation.assignment import (
    LLM_RERANK_SUFFIX,
    CodeAssignmentSet,
    CodeSuggestionSet,
)
from croquito_valuation.calc_matrix import CalcMatrix
from croquito_valuation.canonical import AuditReport, audit_workbook
from croquito_valuation.catalog import default_domain_synonyms, default_legend_noise
from croquito_valuation.contract import ContractLine, ContractWorkbook
from croquito_valuation.errors import ValuationValidationError
from croquito_valuation.models import (
    PriceCatalog,
    ReviewerDecision,
    Valuation,
    ValuationApproval,
)
from croquito_valuation.quantity_source import QuantitySource
from croquito_valuation.takeoff import TakeoffItem, TakeoffPacket
from croquito_valuation.template import WorkbookTemplate
from croquito_valuation.workbook_writer import write_valuation_workbook
from croquito_valuation.worksite_calc import WorksitePlateInput
from croquito_valuation.worksite_takeoff import (
    TakeoffItemAddress,
    TakeoffItemIdentityLink,
    WorksiteTakeoff,
    build_worksite_takeoff,
)
from croquito_worker.valuation.catalog_search import (
    SEMANTIC_UNAVAILABLE_MESSAGE,
    SemanticArm,
    require_query_terms,
    search_catalog,
)
from croquito_worker.valuation.round_extraction import (
    TAKEOFF_OVERLAY_DIGEST,
    TAKEOFF_OVERLAY_PACKET_DIGEST,
    TAKEOFF_OVERLAY_REF,
    plate_ref_key,
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
from croquito_worker.valuation.suggestions import (
    SemanticArmTelemetry,
    compute_suggestions,
    query_cache_path_for_model,
    require_reviewed_takeoff,
)

ROUND_STAGE_NOT_READY: Final = "ROUND_STAGE_NOT_READY"
REVISION_CONFLICT: Final = "REVISION_CONFLICT"
CATALOG_REQUIRED: Final = "CATALOG_REQUIRED"
CATALOG_QUERY_EMPTY: Final = "CATALOG_QUERY_EMPTY"
TAKEOFF_REVIEW_INCOMPLETE: Final = "TAKEOFF_REVIEW_INCOMPLETE"
SUGGESTIONS_ALREADY_REFINED: Final = "SUGGESTIONS_ALREADY_REFINED"
VALUATION_WORKBOOK_AUDIT_FAILED: Final = "VALUATION_WORKBOOK_AUDIT_FAILED"
ROUND_PLATE_ALREADY_PRESENT: Final = "ROUND_PLATE_ALREADY_PRESENT"
"""A folha já está na praça: mesma origem, mesma página.

O código não muda de nome porque não mudou de assunto — ele sempre quis dizer "esta prancha
já está aqui". O que mudou foi a praça: a SEGUNDA folha deixou de ser a mesma coisa que a
folha repetida (F-046, ADR-0057)."""

ROUND_PLATE_LIMIT_REACHED: Final = "ROUND_PLATE_LIMIT_REACHED"

ROUND_PLATE_PAGES_REQUIRED: Final = "ROUND_PLATE_PAGES_REQUIRED"
"""O lote chegou sem escolha nenhuma — nem página para promover, nem folha para extrair.

Recusa, e não "não faz nada": o ato em lote existe justamente porque a escolha é explícita e
nada vem marcado por padrão (pacote de design, decisão 3). Um lote vazio respondido com `200`
faria a tela parecer que promoveu algo."""

ROUND_PLATE_NOT_FOUND: Final = "ROUND_PLATE_NOT_FOUND"
"""A folha nomeada não é desta praça. `404` de recurso, e não recusa de estado."""

EXTRACTION_IN_PROGRESS: Final = "EXTRACTION_IN_PROGRESS"
"""Já existe extração em voo nesta folha. Mesmo código que a rota singular sempre usou."""

WORKSITE_PLATE_LIMIT: Final = 12
"""Teto de folhas por praça.

Existe porque cada folha é uma extração PAGA a mais, e um teto declarado é a diferença entre
um custo que o orçamentista escolhe e um que ele descobre depois. Doze é generoso para a
praça real — planta geral, detalhes e cortes — e continua sendo um número para ser mexido com
medida na mão, não uma verdade sobre o mundo."""

SCENE_LINK_REQUIRED: Final = "SCENE_LINK_REQUIRED"
"""A rodada não declarou o croqui aprovado que a alimenta (F-047 T4b)."""
SCENE_LINK_SCENE_NOT_APPROVED: Final = "SCENE_LINK_SCENE_NOT_APPROVED"
"""O croqui citado não tem cena aprovada; sem aprovação não há pacote de onde ler."""
SCENE_LINK_EXPORT_REQUIRED: Final = "SCENE_LINK_EXPORT_REQUIRED"
"""O croqui citado tem cena aprovada mas nenhum pacote de exportação publicado."""
SCENE_PACKAGE_REQUIRED: Final = "SCENE_PACKAGE_REQUIRED"
"""O pacote citado pelo elo não está utilizável agora (objeto sumido, ilegível, sem o
quantitativo, ou export que deixou de estar completo)."""

BULLETIN_WORKBOOK_REF: Final = "bulletin_workbook"
"""Chave do `.xlsx` publicado, em `artifact_refs_json`. Nunca uma URL assinada."""

BULLETIN_WORKBOOK_DIGEST: Final = "bulletin_workbook_sha256"
"""Digest dos BYTES da planilha publicada, em `artifact_digests_json`."""

BULLETIN_WORKBOOK_CONTENT_TYPE: Final = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

STAGE_CREATED: Final = "created"
STAGE_PLATE: Final = "plate"
STAGE_EXTRACTION: Final = "extraction"
STAGE_TAKEOFF: Final = "takeoff"
STAGE_CODE_ASSIGNMENTS: Final = "code_assignments"
STAGE_BULLETIN: Final = "bulletin"
STAGE_DOSSIER: Final = "amendment_dossier"
STAGE_WORKSITE: Final = "worksite"
"""A praça: as folhas da rodada e o que a orçamentista declarou por cima delas (F-046)."""

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
    "calc_matrix_json",
    "amendment_dossier_json",
    "extraction_lineage_json",
    "worksite_plate_packets_json",
    "worksite_plate_registrations_json",
    "worksite_plate_suggestions_json",
    "worksite_plate_assignments_json",
    "worksite_identity_links_json",
    "scene_link_json",
)
"""Colunas JSON de artefato; ausentes são `NULL`, e `NULL` é "a etapa não aconteceu".

`worksite_identity_links_json` guarda uma LISTA e não um objeto — é a única aqui —, e por
isso não sai em `_artifact_digests` nem passa por `require_document`. Ela está nesta tupla
pelo que a tupla governa de verdade: o que `append_revision` carrega para a revisão
seguinte. Coluna fora daqui é coluna que some no próximo ato, e vínculo declarado que some
é a pior falha possível desta feature."""

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


def bulletin_workbook_audit_failed(audit: AuditReport) -> RoundRefusal:
    """Auditoria de round-trip reprovada: nada é publicado e a recusa é estável.

    Só os CÓDIGOS dos achados viajam. `AuditFinding` carrega `expected`/`found`, que são
    preço, quantidade e total da obra do cliente — devolvê-los numa mensagem de erro
    publicaria justamente o conteúdo que a planilha existe para entregar por URL assinada.

    É `500` pelo mesmo motivo do gêmeo do orçamento-base
    (`estimate_rounds.workbook_audit_failed`): a planilha é render determinístico da medição
    que o próprio servidor acabou de reler e revalidar, e a única leitura honesta de um
    arquivo que não confere consigo mesmo é que o servidor falhou em produzi-lo.
    """
    return RoundRefusal(
        500,
        VALUATION_WORKBOOK_AUDIT_FAILED,
        "a planilha do boletim não confere com a medição aprovada; nada foi publicado",
        {
            "finding_codes": sorted({finding.code for finding in audit.findings}),
            "finding_count": len(audit.findings),
        },
    )


def require_reviewed_packet(packet: TakeoffPacket) -> None:
    """Shortlist só sobre takeoff inteiramente revisado (`409 TAKEOFF_REVIEW_INCOMPLETE`).

    Quem recusa continua sendo `require_reviewed_takeoff`, do módulo que o servidor de
    medição também usa: aqui só a recusa muda de vocabulário, porque em `/v1` "falta revisar
    o takeoff" é ORDEM da cadeia — o orçamentista tem o que fazer para sair dela — e não
    invariante violada. Computar sobre pacote meio revisado congelaria uma shortlist sem os
    itens que ainda vão ser confirmados, e a leitura seguinte serviria esse artefato
    incompleto sem recalcular.
    """
    try:
        require_reviewed_takeoff(packet)
    except ValuationValidationError as error:
        raise RoundRefusal(409, TAKEOFF_REVIEW_INCOMPLETE, error.message, error.details) from error


def require_search_terms(query: str) -> tuple[str, ...]:
    """Palavras utilizáveis da consulta (`422 CATALOG_QUERY_EMPTY`), antes de qualquer busca.

    Espelha `require_reviewed_packet`: a recusa é a do módulo compartilhado
    (`require_query_terms`), com o código estável de `/v1` no lugar do vocabulário do
    servidor local. É `422` e não `409` porque o que está errado é o pedido, não a etapa da
    rodada — nada que o orçamentista decida na cadeia faz `-` virar uma busca.
    """
    try:
        return require_query_terms(query)
    except ValuationValidationError as error:
        raise RoundRefusal(422, CATALOG_QUERY_EMPTY, error.message, error.details) from error


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


def matrix_of(revision: ValuationRoundRevisionRecord | None) -> CalcMatrix | None:
    """A `CalcMatrix` gravada nesta revisão (ADR-0053), ou `None` no regime legado.

    Espelho de `assignments_of`: relê o artefato guardado no build, com a guarda de ciclo do
    próprio `CalcMatrix` rodando de novo na leitura. `NULL` é código único por item."""
    if revision is None or revision.calc_matrix_json is None:
        return None
    return CalcMatrix.model_validate(revision.calc_matrix_json)


def require_takeoff_packet(revision: ValuationRoundRevisionRecord | None) -> TakeoffPacket:
    """O pacote de takeoff publicado, ou a recusa de etapa fora de ordem."""
    packet = takeoff_packet_of(revision)
    if packet is None:
        raise stage_not_ready(
            STAGE_TAKEOFF, detail="a rodada ainda não tem pacote de takeoff publicado"
        )
    return packet


class PlateIdentity(Protocol):
    """O que basta para nomear a chave de artefato de uma folha: posição e identidade.

    Existe para que a folha GRAVADA (`ValuationRoundPlateRecord`) e a folha resolvida
    (`PlateRef`) nomeiem a mesma chave pelo mesmo caminho — sem que este módulo precise
    escolher uma das duas nem duplicar a regra do sufixo.
    """

    @property
    def position(self) -> int: ...

    @property
    def plate_id(self) -> str: ...


def plate_artifact_name(base: str, plate: PlateIdentity | None) -> str:
    """Nome da chave DESTA folha em `artifact_refs_json`/`artifact_digests_json`.

    Uma regra só, e ela vive no worker (`plate_ref_key`): quem ESCREVE o mapa é o comando de
    fila e quem o LÊ é a rota, e duas convenções escritas em lados opostos passariam nos
    testes de cada lado deixando a tela servir a imagem da folha errada.

    `plate=None` é a folha de sempre — a primeira, sem sufixo —, e é isso que faz toda leitura
    que não nomeia folha continuar lendo exatamente o que lia antes da praça.
    """
    if plate is None:
        return base
    return plate_ref_key(base, position=plate.position, plate_id=plate.plate_id)


def takeoff_overlay_ref(
    revision: ValuationRoundRevisionRecord | None,
    plate: ValuationRoundPlateRecord | None = None,
) -> str | None:
    """Chave do PNG do overlay gravada na revisão, ou `None` quando não há desenho."""
    if revision is None:
        return None
    key = (revision.artifact_refs_json or {}).get(plate_artifact_name(TAKEOFF_OVERLAY_REF, plate))
    return key if isinstance(key, str) and key else None


def require_takeoff_overlay(
    revision: ValuationRoundRevisionRecord | None,
    plate: ValuationRoundPlateRecord | None = None,
) -> str:
    """A chave do overlay publicado, ou a recusa de etapa fora de ordem.

    Overlay e pacote nascem no MESMO ato da extração, então rodada sem overlay é rodada
    sem extração publicada — etapa fora de ordem, e não artefato perdido. Vale por FOLHA
    desde a F-046: a folha ainda não extraída da praça está na mesma situação que a rodada
    de uma folha antes da extração.
    """
    key = takeoff_overlay_ref(revision, plate)
    if key is None:
        raise stage_not_ready(
            STAGE_TAKEOFF, detail="a rodada ainda não tem overlay do takeoff publicado"
        )
    return key


def takeoff_overlay_state(
    revision: ValuationRoundRevisionRecord | None,
    *,
    packet_sha256: str,
    plate: ValuationRoundPlateRecord | None = None,
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
    origin = digests.get(plate_artifact_name(TAKEOFF_OVERLAY_PACKET_DIGEST, plate))
    return {
        "present": takeoff_overlay_ref(revision, plate) is not None,
        "image_sha256": digests.get(plate_artifact_name(TAKEOFF_OVERLAY_DIGEST, plate)),
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


SEMANTIC_ARM_ABSENT: Final = (
    f"{SEMANTIC_UNAVAILABLE_MESSAGE}: a shortlist gravada é léxica; o braço semântico roda "
    "no recálculo explícito"
)
"""Motivo declarado do braço semântico onde ele NÃO é sequer tentado.

Dois caminhos usam esta frase, e nos dois ela é verdade por decisão, não por falta:

- o `GET` da shortlist, que não pode pagar nada (ADR-0054 D7). A shortlist gravada na
  primeira leitura é léxica, e a híbrida exige o recompute — que é ato humano, com
  `Idempotency-Key` e `base_version`;
- a busca do catálogo, que é `GET` pelo mesmo motivo.

Ela não é mais o motivo do RECOMPUTE: lá o braço é tentado de verdade, e o que se declara é
o que aconteceu com cada fonte (`croquito_api.semantic_arm`)."""

_NO_QUERY_CACHE: Final = Path(os.devnull)
"""Cache de vetores inexistente, passado a `compute_suggestions` para ser NÃO usado.

Segue vivo porque segue existindo caminho que NÃO paga: o `GET` da shortlist chama o
cálculo sem braço semântico (`semantic=None`), e o cache é insumo da via paga, não artefato
de decisão. O dispositivo nulo está aqui para que esse caminho não escreva em lugar nenhum
— e, mesmo se tentasse, `adapter=None` recusa a consulta ausente em vez de embuti-la.

O recompute **não** o usa: lá o cache é um diretório temporário do próprio ato, descartado
ao sair (ADR-0054, emenda de 2026-08-28)."""


def suggestions_of(revision: ValuationRoundRevisionRecord | None) -> CodeSuggestionSet | None:
    """Shortlist gravada, ou `None` quando ela não existe **ou não valida mais**.

    Ilegível conta como ausente de propósito, e só para quem PERGUNTA pelo conteúdo: é
    assim que a guarda de refino pago (`require_unrefined_suggestions`) deixa o recompute
    curar um artefato corrompido, em vez de recusá-lo para sempre por causa de um campo que
    ninguém consegue ler. Quem SERVE a shortlist não passa por aqui: lá, artefato ilegível
    é recusa, porque a tela não pode renderizar o que o domínio não valida.
    """
    if revision is None or revision.code_suggestions_json is None:
        return None
    try:
        return CodeSuggestionSet.model_validate(revision.code_suggestions_json)
    except (ValuationValidationError, ValidationError):
        return None


def require_unrefined_suggestions(suggestions: CodeSuggestionSet | None) -> None:
    """Recusa recalcular por caminho determinístico uma shortlist com refino pago.

    Recalcular descartaria o lineage da chamada paga — quem respondeu, com qual modelo e
    sob qual prompt —, e esse lineage é a única prova de por que a ordem publicada é aquela.
    O critério é o sufixo que o próprio domínio carimba no `suggester_version`; refinar de
    novo continua sendo comando do CLI.
    """
    if suggestions is None or not suggestions.suggester_version.endswith(LLM_RERANK_SUFFIX):
        return
    raise RoundRefusal(
        409,
        SUGGESTIONS_ALREADY_REFINED,
        "a shortlist já carrega refino pago; recalcular descartaria o lineage da chamada",
        {"suggester_version": suggestions.suggester_version},
    )


def compute_round_suggestions(
    packet: TakeoffPacket, catalog: PriceCatalog, *, semantic: SemanticArm | None = None
) -> tuple[CodeSuggestionSet, list[str], SemanticArmTelemetry]:
    """Shortlist recalculada do zero pelo algoritmo corrente, com ou sem o braço pago.

    Mesmo cálculo do servidor de medição (`compute_suggestions`), com as duas coisas que na
    rodada de `/v1` só podem ser estas: sinônimos do seed empacotado (não há `synonyms.json`
    de diretório) e consolidado contratual ausente — a rodada guarda catálogo, não contrato.
    A revisão completa do takeoff é precondição e continua sendo conferida lá dentro.

    `semantic=None` é o caminho que **não paga nada**, e é o do `GET` (ADR-0054 D7): nenhum
    índice é procurado, nenhum rótulo é embutido, o cache de consulta é o dispositivo nulo e
    a nota diz que a shortlist gravada é léxica até o recálculo. É a invariante que protege
    a leitura de virar chamada paga, e ela tem teste próprio.

    Com um `SemanticArm` montado (é o recompute quem o monta, por
    `croquito_api.semantic_arm`), o braço roda: os rótulos dos itens confirmados são
    embutidos numa chamada paga pequena e a fusão ganha a vizinhança semântica. O cache de
    vetores é um **diretório temporário do ato**, descartado ao sair — decisão de fronteira
    de dado registrada na emenda de 2026-08-28 do ADR-0054, e explicada onde ele é criado.

    A terceira saída é a telemetria do gasto, que o recompute registra no evento e no log.
    """
    if semantic is None or semantic.index is None:
        # Sem braço, ou com braço sem índice, nenhum vetor de consulta é resolvido: o cálculo
        # nem chega ao cache. O dispositivo nulo é o que declara isso — abrir um diretório
        # temporário aqui prometeria uma escrita que não acontece.
        return compute_suggestions(
            packet,
            catalog,
            None,
            default_domain_synonyms(),
            semantic=semantic or SemanticArm(None, None, "unavailable", SEMANTIC_ARM_ABSENT),
            query_cache_path=_NO_QUERY_CACHE,
        )
    with tempfile.TemporaryDirectory(prefix="croquito-query-vectors-") as directory:
        # O cache de vetores de consulta VIVE E MORRE dentro deste ato, por decisão humana
        # de 2026-08-28 (ADR-0054, emenda). A razão é fronteira de dado, não custo: o índice
        # do catálogo é dado PÚBLICO da plataforma — por isso ele é publicado e cacheado no
        # processo —, enquanto o vetor de um rótulo é derivado de TEXTO DO CLIENTE.
        # Persisti-lo (objeto sob `tenants/`, coluna na revisão, qualquer coisa) criaria uma
        # classe nova de dado privado para governar, com retenção, isolamento e ciclo de
        # vida próprios, em troca de poupar centésimos de centavo num ato humano raro.
        # Recompute repetido repaga, e isso é o preço aceito. NÃO "otimize" persistindo:
        # essa mudança é de arquitetura de dado, e o lugar dela é o ADR.
        return compute_suggestions(
            packet,
            catalog,
            None,
            default_domain_synonyms(),
            semantic=semantic,
            query_cache_path=query_cache_path_for_model(Path(directory), semantic.index.model_id),
        )


def search_round_catalog(catalog: PriceCatalog, query: str, limit: int) -> dict[str, Any]:
    """Busca léxica pura no catálogo instalado (decisão humana de 2026-08-17).

    O léxico é o padrão de `/v1` e o único braço que esta função conhece: o híbrido depende
    de índice publicado na rodada e de entitlement contratual, e quem confere as duas coisas
    é a rota — nunca esta função, que jamais resolve vetor nem toca provider. O motivo do
    braço ausente viaja na resposta (`semantic_notes`), como no servidor de medição: a busca
    nunca degrada em silêncio.
    """
    require_search_terms(query)
    return search_catalog(
        catalog,
        query,
        limit,
        default_domain_synonyms(),
        noise=default_legend_noise(),
        semantic=None,
        query_vec=None,
        semantic_warning=SEMANTIC_ARM_ABSENT,
    )


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


def require_plate_object_key(plates: Sequence[ValuationRoundPlateRecord]) -> str:
    """Chave do PDF da PRIMEIRA folha; praça sem folha nenhuma é etapa fora de ordem."""
    if not plates:
        raise stage_not_ready(STAGE_PLATE, detail="a rodada ainda não tem prancha associada")
    return plates[0].object_key


@dataclass(frozen=True, slots=True)
class PlateRef:
    """Uma folha da praça, com a origem e a identidade que o pacote dela vai carregar.

    Desde a F-046 a folha é linha de `valuation_round_plates` e não mais quatro colunas
    escalares da rodada — `page_count` incluído, apurado por folha desde a T4: duas folhas
    podem vir de PDFs diferentes, e a contagem da raiz descreveria o documento de uma delas
    como se fosse o das outras.
    """

    plate_id: str
    position: int
    upload_id: str
    object_key: str
    source_sha256: str
    page_number: int
    page_count: int | None


def resolve_plate(
    plates: Sequence[ValuationRoundPlateRecord], plate_id: str | None = None
) -> ValuationRoundPlateRecord:
    """A folha NOMEADA da praça, ou a primeira quando ninguém a nomeou (F-046 T4c).

    Uma resolução só, para todas as leituras por folha: sem ela cada rota decidiria por conta
    própria o que fazer com uma folha desconhecida, e duas rotas responderiam diferente para a
    mesma causa.

    Ausência de nome é a leitura de sempre — a primeira folha —, e é isso que mantém a rodada
    de uma folha e toda tela que ainda não conhece a praça respondendo exatamente como hoje.
    Nome que não é desta praça é `404 ROUND_PLATE_NOT_FOUND`: recurso inexistente, e não
    ordem da cadeia. Praça sem folha nenhuma continua sendo ordem (`ROUND_STAGE_NOT_READY`).
    """
    if not plates:
        raise stage_not_ready(STAGE_PLATE, detail="a rodada ainda não tem prancha associada")
    if plate_id is None:
        return plates[0]
    for plate in plates:
        if plate.plate_id == plate_id:
            return plate
    raise RoundRefusal(
        404,
        ROUND_PLATE_NOT_FOUND,
        "folha inexistente nesta praça",
        {"plate_ids": [plate_id]},
    )


def require_plate(
    plates: Sequence[ValuationRoundPlateRecord], plate_id: str | None = None
) -> PlateRef:
    """A folha nomeada da praça — a PRIMEIRA quando ninguém a nomeou —, ou a recusa de ordem.

    Desde a F-046 a rodada tem N folhas. Sem `plate_id` a resposta é a da PRIMEIRA folha —
    a que a rodada de uma folha sempre teve, e a que o disparo da extração singular continua
    usando; com `plate_id`, é a folha nomeada (T4c). Rodada sem folha nenhuma é ordem da
    cadeia (`ROUND_STAGE_NOT_READY`), nunca ausência de recurso; folha nomeada que não é
    desta praça, ao contrário, é `404`.

    Folha sem `upload_id` é recusada junto com a folha ausente, e não devolvida pela metade:
    a coluna é anulável só porque o espelho escalar que ela substitui também era, e uma folha
    meio associada é estado que a rota não sabe produzir — ninguém deve ter de tratá-lo.

    A rodada não entra mais por parâmetro: desde a T4 nenhum campo da folha vem da raiz, e um
    argumento não usado chamado `round_record` faria parecer que ainda vem.
    """
    chosen = resolve_plate(plates, plate_id)
    if chosen.upload_id is None:
        raise stage_not_ready(STAGE_PLATE, detail="a rodada ainda não tem prancha associada")
    return PlateRef(
        plate_id=chosen.plate_id,
        position=chosen.position,
        upload_id=chosen.upload_id,
        object_key=chosen.object_key,
        source_sha256=chosen.source_sha256,
        page_number=chosen.page_number,
        page_count=chosen.page_count,
    )


def round_plates(
    session: Session, *, round_id: str, tenant_id: str
) -> list[ValuationRoundPlateRecord]:
    """As folhas da praça, na ordem em que foram acrescentadas.

    `tenant_id` entra no MESMO `where` do `round_id`, como em toda query deste módulo: folha
    de rodada de outro tenant é inexistente, e é o `where` que garante isso.
    """
    return list(
        session.scalars(
            select(ValuationRoundPlateRecord)
            .where(
                ValuationRoundPlateRecord.round_id == round_id,
                ValuationRoundPlateRecord.tenant_id == tenant_id,
            )
            .order_by(ValuationRoundPlateRecord.position)
        )
    )


def mint_plate_id(*, round_id: str, position: int) -> str:
    """A `plate_id` de uma folha nova, cunhada no ato de acrescentá-la.

    A primeira folha é `rodada-{round_id}` — exatamente o que `round_extraction.dataset_id`
    cunha hoje a partir do nome do diretório de trabalho —, e é isso que mantém a rodada de
    uma folha byte-idêntica (ADR-0057, decisão 8). O sufixo `-f{posição}` só nasce com a
    segunda folha, porque é só aí que duas folhas precisam se distinguir.

    O identificador cabe no contrato do manifest de ingestão (`[a-z0-9][a-z0-9-]{2,63}`):
    `rodada-` mais um UUID são 43 caracteres, e o sufixo mais longo cabe folgado no teto.
    """
    return f"rodada-{round_id}" if position == 1 else f"rodada-{round_id}-f{position}"


def append_round_plate(
    session: Session,
    *,
    round_record: ValuationRoundRecord,
    plates: Sequence[ValuationRoundPlateRecord],
    upload_id: str,
    object_key: str,
    source_sha256: str,
    created_by: str,
    page_number: int = 1,
) -> ValuationRoundPlateRecord:
    """Acrescenta uma folha à praça, recusando a folha REPETIDA e o excesso de folhas.

    Duas recusas, e nenhuma delas é "a rodada já tem prancha": a segunda folha é o caso
    normal desta feature. `ROUND_PLATE_ALREADY_PRESENT` passa a nomear só o que ele sempre
    quis dizer — esta folha já está na praça —, e a igualdade é de ORIGEM: mesmo digest do
    PDF e mesma página. Nome de arquivo e id de upload diferentes não fazem duas folhas de um
    mesmo desenho.

    O espelho escalar da PRIMEIRA folha (`plate_upload_id`, `plate_object_key`,
    `plate_source_sha256`) continua sendo escrito enquanto o comando de fila da extração o
    ler: é a metade `expand` do expand/contract (`services/api/AGENTS.md`), e removê-lo é
    trabalho posterior, com aprovação humana explícita.
    """
    if len(plates) >= WORKSITE_PLATE_LIMIT:
        raise RoundRefusal(
            409,
            ROUND_PLATE_LIMIT_REACHED,
            "a praça atingiu o limite de folhas por rodada",
            {"limit": WORKSITE_PLATE_LIMIT},
        )
    digest = source_sha256.lower()
    for existing in plates:
        if existing.source_sha256 == digest and existing.page_number == page_number:
            raise RoundRefusal(
                409,
                ROUND_PLATE_ALREADY_PRESENT,
                "esta folha já está na praça: mesma origem e mesma página",
                {"plate_id": existing.plate_id, "page_number": page_number},
            )
    position = len(plates) + 1
    record = ValuationRoundPlateRecord(
        id=str(new_uuid7()),
        tenant_id=round_record.tenant_id,
        round_id=round_record.id,
        plate_id=mint_plate_id(round_id=round_record.id, position=position),
        position=position,
        upload_id=upload_id,
        object_key=object_key,
        source_sha256=digest,
        page_number=page_number,
        created_by=created_by,
    )
    session.add(record)
    if position == 1:
        round_record.plate_upload_id = upload_id
        round_record.plate_object_key = object_key
        round_record.plate_source_sha256 = digest
    return record


def append_round_plates(
    session: Session,
    *,
    round_record: ValuationRoundRecord,
    plates: Sequence[ValuationRoundPlateRecord],
    upload_id: str,
    object_key: str,
    source_sha256: str,
    created_by: str,
    page_numbers: Sequence[int],
) -> list[ValuationRoundPlateRecord]:
    """Acrescenta N folhas de UM documento à praça, num ato só (F-046 T4).

    O lote é o ato porque a seleção é o ato: a orçamentista marca as páginas que viram folha
    e confirma uma vez. Um ato por página faria a praça de seis folhas custar seis idas ao
    mesmo diálogo, e promover todas as páginas automaticamente encheria a praça de quadro de
    áreas e carimbo — as duas alternativas foram recusadas no pacote de design aprovado.

    **Nada vem marcado por padrão**: `page_numbers` é exigido, não tem valor implícito e uma
    lista vazia é recusa (`ROUND_PLATE_PAGES_REQUIRED`). Página repetida DENTRO do lote também
    é recusa: ela seria a mesma folha duas vezes, que é o que `ROUND_PLATE_ALREADY_PRESENT`
    sempre quis impedir, só que dentro de um mesmo clique.

    Tudo ou nada. As duas recusas de tamanho — o teto da praça e as repetições — são apuradas
    sobre o lote INTEIRO antes de a primeira folha ser criada. Um lote meio aplicado deixaria a
    orçamentista com uma praça que ela não pediu e uma conta de extração que ela não escolheu.

    Este módulo não valida a EXISTÊNCIA da página no PDF, e a omissão é decisão: a API não
    renderiza documento (`services/api/AGENTS.md`), então quem descobre que a página 9 não
    existe é a ingestão, no worker, e o desfecho fica na folha
    (`LOCAL_PLATE_PAGE_ABSENT`) sem derrubar as demais.
    """
    pages = list(page_numbers)
    if not pages:
        raise RoundRefusal(
            422,
            ROUND_PLATE_PAGES_REQUIRED,
            "escolha ao menos uma página do documento para virar folha da praça",
            {},
        )
    repeated = sorted({page for page in pages if pages.count(page) > 1})
    if repeated:
        raise RoundRefusal(
            409,
            ROUND_PLATE_ALREADY_PRESENT,
            "a mesma página foi escolhida mais de uma vez no lote",
            {"page_numbers": repeated},
        )
    if len(plates) + len(pages) > WORKSITE_PLATE_LIMIT:
        raise RoundRefusal(
            409,
            ROUND_PLATE_LIMIT_REACHED,
            "a praça atingiu o limite de folhas por rodada",
            {"limit": WORKSITE_PLATE_LIMIT, "present": len(plates), "requested": len(pages)},
        )
    appended: list[ValuationRoundPlateRecord] = []
    current = list(plates)
    for page_number in pages:
        record = append_round_plate(
            session,
            round_record=round_record,
            plates=current,
            upload_id=upload_id,
            object_key=object_key,
            source_sha256=source_sha256,
            created_by=created_by,
            page_number=page_number,
        )
        current.append(record)
        appended.append(record)
    return appended


def extracted_plate_ids(
    revision: ValuationRoundRevisionRecord | None,
    plates: Sequence[ValuationRoundPlateRecord],
) -> set[str]:
    """Folhas que JÁ têm pacote publicado, lidas por PRESENÇA e sem revalidar o documento.

    `worksite_packets` valida cada pacote para poder somá-los; aqui a pergunta é outra — "há
    algo gravado nesta folha?" —, e responder por validação faria um pacote antigo que deixou
    de validar liberar uma segunda extração paga em cima da evidência que já existe. A recusa
    de re-extrair protege exatamente esse caso, então ela não pode depender do documento estar
    perfeito.

    A folha de posição 1 é a de `takeoff_packet_json`, pela mesma divisão que o worker usa
    para escrever; as demais são as chaves do mapa.
    """
    if revision is None:
        return set()
    extracted = {str(plate_id) for plate_id in (revision.worksite_plate_packets_json or {})}
    if revision.takeoff_packet_json is not None:
        first = next((plate for plate in plates if plate.position == 1), None)
        if first is not None:
            extracted.add(first.plate_id)
    return extracted


def queue_plate_extractions(
    round_record: ValuationRoundRecord,
    plates: Sequence[ValuationRoundPlateRecord],
    extracted: Collection[str],
    *,
    plate_ids: Sequence[str],
    extraction_id: str,
    requested_by: str,
    now: datetime,
) -> list[ValuationRoundPlateRecord]:
    """Marca como `queued` as folhas ESCOLHIDAS, e devolve exatamente quais.

    O lote informa quantas folhas serão extraídas ANTES de qualquer coisa sair da máquina:
    quem chama recebe a lista de volta e a publica na resposta, e é essa lista que diz ao
    orçamentista quantas chamadas pagas ele acabou de autorizar. O custo por folha não pode
    aparecer só na fatura (pacote de design, decisão 4).

    Nada vem marcado por padrão aqui também: `plate_ids` é exigido e cada id tem de ser uma
    folha DESTA praça. Folha que já tem pacote extraído é recusada nominalmente — re-extrair
    apagaria a evidência sobre a qual as decisões já foram tomadas —, e folha com extração em
    voo é recusada pelo mesmo motivo de sempre: ninguém paga duas vezes pela mesma leitura.

    Tudo ou nada, como o lote de folhas: as recusas são apuradas sobre o lote inteiro antes de
    a primeira folha ser marcada. Meia autorização é a pior das três respostas possíveis.
    """
    if not plate_ids:
        raise RoundRefusal(
            422,
            ROUND_PLATE_PAGES_REQUIRED,
            "escolha ao menos uma folha da praça para extrair",
            {},
        )
    by_id = {plate.plate_id: plate for plate in plates}
    unknown = sorted({plate_id for plate_id in plate_ids if plate_id not in by_id})
    if unknown:
        raise RoundRefusal(
            404,
            ROUND_PLATE_NOT_FOUND,
            "folha inexistente nesta praça",
            {"plate_ids": unknown},
        )
    repeated = sorted({value for value in plate_ids if list(plate_ids).count(value) > 1})
    if repeated:
        raise RoundRefusal(
            409,
            ROUND_PLATE_ALREADY_PRESENT,
            "a mesma folha foi escolhida mais de uma vez no lote",
            {"plate_ids": repeated},
        )
    published = sorted({plate_id for plate_id in plate_ids if plate_id in extracted})
    if published:
        raise RoundRefusal(
            409,
            ROUND_PLATE_ALREADY_PRESENT,
            "a folha já tem pacote de takeoff publicado",
            {"plate_ids": published},
        )
    running = sorted(
        {
            plate_id
            for plate_id in plate_ids
            if by_id[plate_id].extraction_status in ("queued", "running")
        }
    )
    if running:
        raise RoundRefusal(
            409,
            EXTRACTION_IN_PROGRESS,
            "já existe uma extração em andamento nesta folha",
            {"plate_ids": running},
        )
    queued: list[ValuationRoundPlateRecord] = []
    for plate_id in plate_ids:
        plate = by_id[plate_id]
        plate.extraction_id = extraction_id
        plate.extraction_status = "queued"
        plate.extraction_failure_code = None
        plate.extraction_requested_by = requested_by
        plate.extraction_updated_at = now
        queued.append(plate)
    # A raiz continua respondendo pela rodada porque é o que a tela de hoje lê; o estado
    # verdadeiro é o das folhas, e o worker reescreve este espelho a cada desfecho.
    round_record.extraction_id = extraction_id
    round_record.extraction_status = "queued"
    round_record.extraction_failure_code = None
    round_record.extraction_requested_by = requested_by
    round_record.extraction_updated_at = now
    return queued


def worksite_packets(
    revision: ValuationRoundRevisionRecord | None,
) -> dict[str, TakeoffPacket]:
    """Os pacotes de takeoff da praça, indexados pela `plate_id` que cada um DECLARA.

    A primeira folha continua em `takeoff_packet_json` e as demais em
    `worksite_plate_packets_json` — a divisão que mantém a rodada de uma folha byte-idêntica.
    O índice sai do próprio pacote, e não da chave do mapa nem da posição da folha: é o
    pacote que sabe de qual folha ele é, e casar por posição faria uma folha reordenada
    responder pelos itens de outra.
    """
    packets: dict[str, TakeoffPacket] = {}
    first = takeoff_packet_of(revision)
    if first is not None:
        packets[first.plate_id] = first
    stored = None if revision is None else revision.worksite_plate_packets_json
    for document in (stored or {}).values():
        packet = TakeoffPacket.model_validate(document)
        packets[packet.plate_id] = packet
    return packets


def plate_registrations(
    revision: ValuationRoundRevisionRecord | None,
) -> dict[str, Mapping[str, Any]]:
    """Relatórios do registro fino de bbox por folha, indexados pela `plate_id` (F-046 T4).

    Mesma divisão dos pacotes, pelo mesmo motivo: a primeira folha continua em
    `takeoff_registration_json` e as demais no mapa próprio. A `plate_id` da primeira sai do
    PACOTE dela, e não da folha gravada — é o pacote que diz de qual folha o relatório é, e
    casar por posição faria uma praça reordenada declarar âncora confiável no lugar errado.

    Documento gravado, lido sem revalidar: `registered_item_ids` já é fail-closed diante de
    relatório sem método declarado, e derrubar a praça inteira por um relatório estranho seria
    trocar uma âncora `raw` por uma tela em branco.
    """
    reports: dict[str, Mapping[str, Any]] = {}
    if revision is None:
        return reports
    first = takeoff_packet_of(revision)
    if first is not None and isinstance(revision.takeoff_registration_json, Mapping):
        reports[first.plate_id] = revision.takeoff_registration_json
    for plate_id, document in (revision.worksite_plate_registrations_json or {}).items():
        if isinstance(document, Mapping):
            reports[str(plate_id)] = document
    return reports


def require_plate_packet(
    revision: ValuationRoundRevisionRecord | None,
    plate: ValuationRoundPlateRecord,
) -> TakeoffPacket:
    """O pacote de takeoff DESTA folha, ou a recusa de etapa fora de ordem (F-046 T4c).

    Irmã de `require_takeoff_packet`, com a mesma recusa e o mesmo significado: folha da praça
    ainda não extraída é ordem da cadeia, e não recurso perdido. O índice é o de
    `worksite_packets` — a `plate_id` que o PACOTE declara —, para que a leitura por folha não
    invente um segundo jeito de casar pacote com prancha.

    A primeira folha passa pelo mesmo caminho e devolve exatamente o pacote de
    `takeoff_packet_json`, byte a byte: `worksite_packets` a lê de lá.
    """
    packet = worksite_packets(revision).get(plate.plate_id)
    if packet is None:
        raise stage_not_ready(
            STAGE_TAKEOFF, detail="a folha ainda não tem pacote de takeoff publicado"
        )
    return packet


def plate_packet_document(
    revision: ValuationRoundRevisionRecord | None,
    plate: ValuationRoundPlateRecord,
) -> Mapping[str, Any]:
    """O documento GRAVADO do pacote desta folha, sem revalidar — a origem do digest.

    O digest tem de ser o do que está no banco, e não o de uma reserialização do modelo: é por
    ele que a tela sabe se o pacote que ela tem na mão ainda é o corrente, e é ele que a rota
    do overlay compara com o pacote que originou o desenho.
    """
    if plate.position <= 1:
        return require_document(
            revision,
            "takeoff_packet_json",
            stage=STAGE_TAKEOFF,
            detail="a rodada ainda não tem pacote de takeoff publicado",
        )
    stored = None if revision is None else revision.worksite_plate_packets_json
    document = (stored or {}).get(plate.plate_id)
    if document is None:
        raise stage_not_ready(
            STAGE_TAKEOFF, detail="a folha ainda não tem pacote de takeoff publicado"
        )
    return dict(document)


def plate_packet_changes(
    revision: ValuationRoundRevisionRecord | None,
    plate: ValuationRoundPlateRecord | None,
    document: Mapping[str, Any],
) -> dict[str, Any]:
    """As colunas que a revisão nova recebe ao publicar o pacote revisado DESTA folha.

    A divisão é a que a T3 fixou e que o worker escreve: a primeira folha em
    `takeoff_packet_json`, as demais no mapa por `plate_id`. Escrever pelo mesmo caminho é o
    que faz a rodada de uma folha continuar gravando exatamente a mesma coluna de sempre —
    `plate=None` é a folha de sempre, e nem chega a olhar a praça.

    O mapa inteiro é reescrito porque `append_revision` substitui a coluna, não a funde: as
    folhas que este ato não tocou viajam idênticas, copiadas da cabeça.
    """
    if plate is None or plate.position <= 1:
        return {"takeoff_packet_json": dict(document)}
    stored = None if revision is None else revision.worksite_plate_packets_json
    return {"worksite_plate_packets_json": {**(stored or {}), plate.plate_id: dict(document)}}


def plate_registration(
    revision: ValuationRoundRevisionRecord | None,
    plate: ValuationRoundPlateRecord,
) -> Mapping[str, Any] | None:
    """O relatório de registro fino DESTA folha; é ele que separa âncora `registered` de `raw`."""
    return plate_registrations(revision).get(plate.plate_id)


def _is_first_plate(plate: ValuationRoundPlateRecord | None) -> bool:
    """A folha de sempre — a primeira, ou nenhuma folha nomeada.

    Uma regra só, porque ela decide em qual COLUNA cada etapa por folha lê e escreve, e duas
    escritas dessa condição em lados opostos fariam uma rota gravar num lugar e a outra ler
    do outro. `None` é a leitura que não nomeia folha, e ela é a primeira por definição.
    """
    return plate is None or plate.position <= 1


def plate_assignments(
    revision: ValuationRoundRevisionRecord | None,
) -> dict[str, CodeAssignmentSet]:
    """Os conjuntos de código da praça, indexados pela `plate_id` que cada um DECLARA.

    Espelho exato de `worksite_packets`, e pelo mesmo motivo: a primeira folha continua em
    `code_assignments_json` e as demais em `worksite_plate_assignments_json` — a divisão que
    mantém a praça de uma folha byte-idêntica (ADR-0057, decisão 8).

    O índice sai do próprio conjunto, e não da chave do mapa nem da posição da folha: é o
    conjunto que sabe de qual prancha ele é (`CodeAssignmentSet.plate_id`), e casar por
    posição faria uma praça reordenada medir uma folha com os códigos de outra — que é
    exatamente o que `CALC_ASSIGNMENT_PACKET_MISMATCH` existe para impedir.
    """
    sets: dict[str, CodeAssignmentSet] = {}
    first = assignments_of(revision)
    if first is not None:
        sets[first.plate_id] = first
    stored = None if revision is None else revision.worksite_plate_assignments_json
    for document in (stored or {}).values():
        assignments = CodeAssignmentSet.model_validate(document)
        sets[assignments.plate_id] = assignments
    return sets


def assignments_for_plate(
    revision: ValuationRoundRevisionRecord | None,
    plate: ValuationRoundPlateRecord | None,
) -> CodeAssignmentSet | None:
    """O conjunto de código DESTA folha, ou `None` quando ela ainda não tem decisão nenhuma.

    `plate=None` é a folha de sempre e devolve exatamente `assignments_of` — byte a byte o
    que a rodada de uma folha sempre leu, sem sequer olhar o mapa das demais.

    Conjunto ausente **não** é erro: a folha extraída e revisada sem nenhuma decisão de código
    é o estado normal de quem acabou de chegar nesta etapa.
    """
    if _is_first_plate(plate):
        return assignments_of(revision)
    stored = None if revision is None else revision.worksite_plate_assignments_json
    document = (stored or {}).get(cast(ValuationRoundPlateRecord, plate).plate_id)
    return None if document is None else CodeAssignmentSet.model_validate(document)


def assignments_document_for_plate(
    revision: ValuationRoundRevisionRecord | None,
    plate: ValuationRoundPlateRecord | None,
) -> dict[str, Any] | None:
    """O documento GRAVADO do conjunto desta folha, sem revalidar — a origem do digest.

    Espelha `plate_packet_document` e existe pelo mesmo motivo: o digest tem de ser o do que
    está no banco, e não o de uma reserialização do modelo, senão a tela não consegue dizer se
    o conjunto que ela tem na mão ainda é o corrente.
    """
    if _is_first_plate(plate):
        return None if revision is None else revision.code_assignments_json
    stored = None if revision is None else revision.worksite_plate_assignments_json
    document = (stored or {}).get(cast(ValuationRoundPlateRecord, plate).plate_id)
    return None if document is None else dict(document)


def plate_assignments_changes(
    revision: ValuationRoundRevisionRecord | None,
    plate: ValuationRoundPlateRecord | None,
    document: Mapping[str, Any],
) -> dict[str, Any]:
    """As colunas que a revisão nova recebe ao gravar o conjunto de código DESTA folha.

    Espelho de `plate_packet_changes`: a primeira folha em `code_assignments_json`, as demais
    no mapa por `plate_id`. `plate=None` é a folha de sempre e nem chega a olhar a praça, que é
    o que faz a rodada de uma folha continuar gravando exatamente a mesma coluna.

    O mapa inteiro é reescrito porque `append_revision` substitui a coluna, não a funde: as
    folhas que este ato não tocou viajam idênticas, copiadas da cabeça.
    """
    if _is_first_plate(plate):
        return {"code_assignments_json": dict(document)}
    stored = None if revision is None else revision.worksite_plate_assignments_json
    key = cast(ValuationRoundPlateRecord, plate).plate_id
    return {"worksite_plate_assignments_json": {**(stored or {}), key: dict(document)}}


def suggestions_document_for_plate(
    revision: ValuationRoundRevisionRecord | None,
    plate: ValuationRoundPlateRecord | None,
) -> dict[str, Any] | None:
    """A shortlist GRAVADA desta folha, sem revalidar; `None` é "ainda não foi calculada".

    A shortlist é observação por ITEM, e os itens são os do pacote de UMA folha: servir a da
    primeira folha sob o cabeçalho da segunda ofereceria códigos para elementos que não estão
    naquela prancha. Por isso ela é por folha, e não da rodada.
    """
    if _is_first_plate(plate):
        return None if revision is None else revision.code_suggestions_json
    stored = None if revision is None else revision.worksite_plate_suggestions_json
    document = (stored or {}).get(cast(ValuationRoundPlateRecord, plate).plate_id)
    return None if document is None else dict(document)


def plate_suggestions_changes(
    revision: ValuationRoundRevisionRecord | None,
    plate: ValuationRoundPlateRecord | None,
    document: Mapping[str, Any],
) -> dict[str, Any]:
    """As colunas que a revisão nova recebe ao gravar a shortlist DESTA folha."""
    if _is_first_plate(plate):
        return {"code_suggestions_json": dict(document)}
    stored = None if revision is None else revision.worksite_plate_suggestions_json
    key = cast(ValuationRoundPlateRecord, plate).plate_id
    return {"worksite_plate_suggestions_json": {**(stored or {}), key: dict(document)}}


def identity_links_of(
    revision: ValuationRoundRevisionRecord | None,
) -> list[TakeoffItemIdentityLink]:
    """Os vínculos de identidade declarados nesta revisão, revalidados na leitura."""
    stored = None if revision is None else revision.worksite_identity_links_json
    return [TakeoffItemIdentityLink.model_validate(document) for document in (stored or [])]


def pending_worksite_plates(
    plates: Sequence[ValuationRoundPlateRecord], packets: Mapping[str, TakeoffPacket]
) -> list[str]:
    """Folhas da praça que ainda não têm pacote extraído, na ordem da praça."""
    return [plate.plate_id for plate in plates if plate.plate_id not in packets]


def require_worksite_takeoff(
    round_record: ValuationRoundRecord,
    revision: ValuationRoundRevisionRecord | None,
    plates: Sequence[ValuationRoundPlateRecord],
    *,
    identity_links: Sequence[TakeoffItemIdentityLink] | None = None,
) -> WorksiteTakeoff:
    """O consolidado da praça, montado a partir das folhas gravadas e dos pacotes delas.

    O consolidado é DERIVADO, nunca gravado: as folhas estão na tabela filha, os pacotes na
    revisão e os vínculos na revisão, e um quarto lugar guardando a soma dos três só poderia
    envelhecer em silêncio — bastaria acrescentar uma folha para o consolidado gravado passar
    a descrever uma praça que não existe mais.

    Falha fechado, na ordem em que a praça pode não estar pronta: praça sem folha nenhuma e
    folha sem pacote extraído são etapa fora de ordem (`ROUND_STAGE_NOT_READY`), nomeando
    QUAIS folhas faltam. Depois disso quem recusa é o domínio (`build_worksite_takeoff`), com
    os códigos que a T1 fixou.
    """
    if not plates:
        raise stage_not_ready(STAGE_PLATE, detail="a rodada ainda não tem prancha associada")
    packets = worksite_packets(revision)
    pending = pending_worksite_plates(plates, packets)
    if pending:
        raise RoundRefusal(
            409,
            ROUND_STAGE_NOT_READY,
            "a praça só fecha com todas as folhas extraídas",
            {"stage": STAGE_WORKSITE, "pending_plate_ids": pending},
        )
    links = identity_links_of(revision) if identity_links is None else list(identity_links)
    return build_worksite_takeoff(
        round_record.worksite_key,
        [packets[plate.plate_id] for plate in plates],
        links,
    )


def declared_identity_link(
    *,
    kept: tuple[str, str],
    discarded: tuple[str, str],
    note: str,
    declared_by: str,
    declared_at: datetime,
) -> TakeoffItemIdentityLink:
    """O vínculo como o servidor o carimba: autor e instante nunca vêm do corpo.

    O corpo declara O QUE é o mesmo elemento; quem declarou e quando é identidade do
    principal autenticado e relógio do servidor, como em toda decisão desta cadeia.
    """
    return TakeoffItemIdentityLink(
        kept=TakeoffItemAddress(plate_id=kept[0], item_id=kept[1]),
        discarded=TakeoffItemAddress(plate_id=discarded[0], item_id=discarded[1]),
        declared_by=declared_by,
        declared_at=declared_at,
        note=note,
    )


NO_CODE_DECISIONS_NOTES: Final = (
    "Conjunto derivado e nunca gravado: esta folha da praça não tem decisão de código "
    "nenhuma registrada.",
    "Nada aqui foi confirmado por ninguém; ele existe só para que o portão do boletim nomeie "
    "os itens que faltam decidir, em vez de recusar a praça sem dizer onde.",
)
"""Ressalvas do conjunto VAZIO de códigos de uma folha. Ver `no_code_decisions`."""


def no_code_decisions(packet: TakeoffPacket, catalog: PriceCatalog) -> CodeAssignmentSet:
    """O conjunto de códigos de uma folha que ainda não tem NENHUMA decisão registrada.

    Existe por uma razão de ordem, não de conveniência. Desde a T4d cada folha TEM onde
    guardar o conjunto dela (`worksite_plate_assignments_json`), mas a folha extraída e
    revisada em que ninguém decidiu código nenhum continua sendo estado normal — e o boletim
    da praça exige um conjunto POR folha para poder ser montado. Recusar aqui, do lado da
    rota, adiantaria a recusa e trocaria os códigos do domínio pelos desta camada.

    Com o conjunto vazio, quem recusa continua sendo `build_worksite_takeoff_bulletins`, na
    ordem dele: folha pendente de revisão sai como `WORKSITE_TAKEOFF_PLATE_PENDING` (o portão
    da praça, que vem primeiro), e folha revisada sem código sai como `CALC_ASSIGNMENT_MISSING`
    NOMEANDO os itens. As duas respostas são as que o orçamentista precisa — nenhuma delas é
    um boletim pela metade.

    Ele **nunca é persistido** e nunca sai numa resposta: é insumo do builder, vive dentro de
    uma chamada e morre nela. As ressalvas dizem exatamente isso, para que um conjunto vazio
    que vazasse para algum lugar não pudesse ser lido como decisão de ninguém.
    """
    return CodeAssignmentSet(
        plate_id=packet.plate_id,
        page_number=packet.page_number,
        image_sha256=packet.image_sha256,
        catalog_sha256=catalog.source_sha256,
        assignments=[],
        safety_notes=list(NO_CODE_DECISIONS_NOTES),
    )


def worksite_plate_inputs(
    revision: ValuationRoundRevisionRecord | None,
    plates: Sequence[ValuationRoundPlateRecord],
    *,
    catalog: PriceCatalog,
    first_assignments: CodeAssignmentSet,
    calc_matrix: CalcMatrix | None,
) -> list[WorksitePlateInput]:
    """O que cada folha da praça leva ao boletim, na ordem da praça (F-046 T4c/T4d).

    Cada folha entra com o conjunto de códigos DELA — é o que a decisão 6 do ADR-0057 chama de
    consumir a UNIÃO dos conjuntos: `CodeAssignmentSet` continua sendo por prancha, e o
    boletim da praça é montado com um por folha. A primeira folha entra com o conjunto que a
    rota já tem em mãos (`first_assignments`), e por isso a praça de UMA folha sai byte a byte
    igual à de sempre.

    Folha ainda sem decisão nenhuma entra com `no_code_decisions`, e não é recusada aqui: quem
    recusa continua sendo o domínio, na ordem dele e nomeando os itens que faltam
    (`CALC_ASSIGNMENT_MISSING`). Adiantar a recusa nesta camada trocaria os códigos do domínio
    pelos daqui.

    A matriz posta no build fica só na primeira folha, e não é espalhada pelas outras: a
    `CalcMatrix` cita `source_item_id` de UM pacote (ADR-0053), e repeti-la nas demais faria
    cada folha ser cobrada por uma memória escrita sobre os itens de outra.

    **Pressupõe `require_worksite_takeoff` já chamado**: é ele que garante que toda folha da
    praça tem pacote, e por isso a indexação abaixo não trata ausência. Chamar esta função
    antes dele levantaria `KeyError` em vez da recusa `ROUND_STAGE_NOT_READY` que nomeia as
    folhas que faltam.
    """
    packets = worksite_packets(revision)
    decided = plate_assignments(revision)
    inputs: list[WorksitePlateInput] = []
    for plate in plates:
        packet = packets[plate.plate_id]
        first = plate.position <= 1
        stored = decided.get(plate.plate_id)
        # `is None` explícito, e não `or`: um conjunto sem nenhuma decisão dentro é um conjunto
        # que EXISTE, e trocá-lo pelo derivado apagaria as ressalvas que o orçamentista gravou.
        assignments = (
            first_assignments
            if first
            else (no_code_decisions(packet, catalog) if stored is None else stored)
        )
        inputs.append(
            WorksitePlateInput(
                packet=packet,
                assignments=assignments,
                calc_matrix=calc_matrix if first else None,
            )
        )
    return inputs


def _parcel_payload(plate_id: str, item: TakeoffItem) -> dict[str, Any]:
    """Uma leitura da praça como a prévia da fusão a mostra, com o decimal como TEXTO.

    Quantidade é `Decimal` exato neste contexto (ADR-0016): um número de JSON devolveria ao
    cliente um binário aproximado da casa decimal escrita na legenda. Quantidade ausente é
    `null`, nunca `"0"` — zero é um valor, ausência não.
    """
    return {
        "plate_id": plate_id,
        "item_id": item.id,
        "label": item.label,
        "unit": item.unit,
        "status": item.status.value,
        "quantity": None if item.quantity is None else str(item.quantity),
    }


def identity_link_preview(
    worksite: WorksiteTakeoff,
    packets: Mapping[str, TakeoffPacket],
    *,
    kept: TakeoffItemAddress,
    discarded: TakeoffItemAddress,
) -> dict[str, Any]:
    """O efeito da fusão declarada no total da praça, ANTES de qualquer gravação (F-046 T4c).

    A conta é do servidor, e é por isso que esta rota existe: a tela não soma
    (`apps/web/AGENTS.md`), e sem uma prévia calculada aqui a orçamentista só descobriria o
    efeito do vínculo depois de declará-lo — que é exatamente a decisão que o pacote de design
    quis tornar informada.

    O que a fusão faz ao total é uma coisa só e é aritmética: a leitura absorvida deixa de
    contar, e a que fica governa (ADR-0057 D4). Então `total_before` é a soma das duas leituras
    e `total_after` é a quantidade da que fica.

    **Unidade divergente não é somada.** Duas leituras em `m2` e `m` não têm soma, e imprimir
    uma seria fabricar um número com aparência de conta. Nesse caso os dois totais saem `null`
    com `unit_mismatch = true`, e as duas parcelas continuam à vista para que a orçamentista
    veja o que declarou. O mesmo vale para leitura ainda sem quantidade.

    `worksite` já chega montado COM o vínculo candidato, então as recusas da T1 — vínculo dentro
    da mesma folha, alvo inexistente, cadeia de vínculos — já aconteceram antes daqui: a prévia
    nunca pode dizer "pode" para o que a declaração recusaria.
    """
    kept_item = _packet_item(packets, kept)
    discarded_item = _packet_item(packets, discarded)
    quantities = (kept_item.quantity, discarded_item.quantity)
    comparable = kept_item.unit == discarded_item.unit and None not in quantities
    total_before = (
        None
        if not comparable
        else str(cast(Decimal, kept_item.quantity) + cast(Decimal, discarded_item.quantity))
    )
    total_after = None if not comparable else str(kept_item.quantity)
    return {
        "worksite_key": worksite.worksite_key,
        "kept": _parcel_payload(kept.plate_id, kept_item),
        "discarded": _parcel_payload(discarded.plate_id, discarded_item),
        "unit_mismatch": kept_item.unit != discarded_item.unit,
        "total_before": total_before,
        "total_after": total_after,
    }


def _packet_item(packets: Mapping[str, TakeoffPacket], address: TakeoffItemAddress) -> TakeoffItem:
    """O item apontado pelo endereço da praça; a existência já foi conferida pelo consolidado."""
    for item in packets[address.plate_id].items:
        if item.id == address.item_id:
            return item
    raise ValuationValidationError(  # pragma: no cover - `build_worksite_takeoff` já recusou
        "WORKSITE_LINK_UNKNOWN_TARGET",
        "vínculo de identidade aponta para item que não existe no pacote da prancha",
        {"addresses": [f"{address.plate_id}:{address.item_id}"]},
    )


def worksite_state(
    round_record: ValuationRoundRecord,
    revision: ValuationRoundRevisionRecord | None,
    plates: Sequence[ValuationRoundPlateRecord],
) -> dict[str, Any]:
    """A praça como a tela a lê: as folhas, o estado de cada uma e o consolidado.

    Leitura TOLERANTE, como o resto do estado da rodada: consolidado que não monta sai
    ausente com o código da recusa, e não derruba a tela. Quem recusa de verdade é a
    declaração do vínculo e o boletim, que é onde a resposta importa.

    A tolerância cobre também o artefato gravado que deixou de validar — a mesma regra que
    `readable_valuation` já segue: ele sai como AUSENTE, com o código dizendo por quê, em vez
    de derrubar a praça inteira antes de o orçamentista chegar nela.
    """
    unreadable: str | None = None
    try:
        packets = worksite_packets(revision)
        links = identity_links_of(revision)
    except ValidationError:
        packets, links = {}, []
        unreadable = "DOMAIN_VALIDATION_FAILED"
    registrations = plate_registrations(revision)
    sheets: list[dict[str, Any]] = []
    for plate in plates:
        packet = packets.get(plate.plate_id)
        registered = (
            frozenset[str]()
            if packet is None
            else registered_item_ids(registrations.get(plate.plate_id))
        )
        sheets.append(
            {
                "plate_id": plate.plate_id,
                "position": plate.position,
                "source_sha256": plate.source_sha256,
                "page_number": plate.page_number,
                # Por folha desde a T4: duas folhas podem vir de PDFs diferentes, e a
                # contagem da raiz descreveria o documento de uma como se fosse o das outras.
                "page_count": plate.page_count,
                # O estado da extração é DA FOLHA (T4). A raiz continua tendo o dela, agora
                # derivado destes: é isso que faz uma folha que falha não derrubar as demais.
                "extraction_status": plate.extraction_status,
                "extraction_failure_code": plate.extraction_failure_code,
                "extraction_updated_at": (
                    None
                    if plate.extraction_updated_at is None
                    else plate.extraction_updated_at.isoformat()
                ),
                "takeoff_present": packet is not None,
                "packet_sha256": (
                    None if packet is None else document_digest(packet.model_dump(mode="json"))
                ),
                "review_status": None if packet is None else review_status(packet),
                "item_count": None if packet is None else len(packet.items),
                "pending_items": None if packet is None else len(packet.pending_items()),
                **({} if packet is None else anchor_counts(packet, registered)),
            }
        )
    consolidated: dict[str, Any] = {
        "present": False,
        "worksite_takeoff_sha256": None,
        "document": None,
        "pending_plate_ids": pending_worksite_plates(plates, packets),
        "refusal_code": None,
    }
    if unreadable is not None:
        consolidated["refusal_code"] = unreadable
    else:
        try:
            worksite = require_worksite_takeoff(round_record, revision, plates)
        except RoundRefusal as refusal:
            consolidated["refusal_code"] = refusal.code
        except ValuationValidationError as error:
            consolidated["refusal_code"] = error.code
        else:
            document = worksite.model_dump(mode="json")
            consolidated["present"] = True
            consolidated["document"] = document
            consolidated["worksite_takeoff_sha256"] = document_digest(document)
    return {
        "round_id": round_record.id,
        "version": round_record.version,
        "worksite_key": round_record.worksite_key,
        "worksite_name": round_record.worksite_name,
        "plate_limit": WORKSITE_PLATE_LIMIT,
        "plates": sheets,
        "identity_links": [link.model_dump(mode="json") for link in links],
        "consolidated": consolidated,
    }


def current_stage(
    round_record: ValuationRoundRecord,
    revision: ValuationRoundRevisionRecord | None,
    *,
    has_plate: bool,
) -> str:
    """Etapa mais avançada que a rodada alcançou, para a linha da listagem.

    `has_plate` entra por parâmetro porque a folha virou tabela filha (F-046) e a listagem
    não pode fazer uma query por linha: quem lista carrega a presença de folha das rodadas da
    página de uma vez só e passa a resposta para cá.

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
    if has_plate:
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


def read_catalog(
    store: RoundArtifactStore,
    *,
    object_key: str,
    digest: str,
    cache: CatalogCache,
    details: Mapping[str, object],
) -> PriceCatalog:
    """Um catálogo instalado, lido do object store, conferido contra o digest e validado.

    O digest manda duas vezes: é a chave do cache e é o que os bytes lidos têm de
    reproduzir. Objeto ausente, maior que o teto, com digest divergente ou que deixou de
    validar recusam com `CATALOG_REQUIRED` — o catálogo foi validado no ato que o
    instalou, então uma falha aqui é do ambiente, não do ato.

    Recebe `object_key` e `digest` soltos, e não o registro da rodada, porque as duas
    cadeias que instalam catálogo guardam essa referência em lugares diferentes: a medição
    numa coluna própria da raiz e o orçamento-base numa posição da cascata. O que é
    idêntico nas duas — teto de leitura, conferência de digest, validação de domínio e
    cache por digest — mora aqui uma vez só. `details` viaja para a recusa para que ela
    continue nomeando a rodada de quem chamou.
    """
    cached = cache.get(digest)
    if cached is not None:
        return cached

    payload = store.read_object(object_key=object_key, max_bytes=CATALOG_MAX_BYTES)
    if payload is None:
        raise catalog_required(
            "o catálogo instalado nesta rodada não está disponível no armazenamento",
            details,
        )
    if len(payload) > CATALOG_MAX_BYTES:
        raise catalog_required(
            "o catálogo instalado nesta rodada excede o limite de leitura",
            {**details, "max_bytes": CATALOG_MAX_BYTES},
        )
    if hashlib.sha256(payload).hexdigest() != digest:
        raise catalog_required(
            "o catálogo armazenado diverge do digest instalado na rodada",
            details,
        )
    try:
        catalog = PriceCatalog.model_validate_json(payload)
    except ValuationValidationError as error:
        raise catalog_required(
            "o catálogo instalado nesta rodada não pôde ser lido",
            {**details, "reason": error.code},
        ) from error
    except ValidationError as error:
        raise catalog_required(
            "o catálogo instalado nesta rodada não pôde ser lido",
            {**details, "reason": "MODEL_VALIDATION_FAILED"},
        ) from error
    cache.put(digest, catalog)
    return catalog


def load_catalog(
    store: RoundArtifactStore,
    round_record: ValuationRoundRecord,
    *,
    cache: CatalogCache = CATALOG_CACHE,
) -> PriceCatalog:
    """O catálogo instalado na rodada de medição, lido do store e validado pelo domínio."""
    return read_catalog(
        store,
        object_key=round_record.catalog_object_key,
        digest=round_record.catalog_source_sha256,
        cache=cache,
        details={"round_id": round_record.id},
    )


# --- o elo com o croqui aprovado (F-047 T4b) ----------------------------------------------


SCENE_PACKAGE_MAX_BYTES: Final = 32 * 1024 * 1024
"""Teto de leitura do pacote de exportação do croqui.

Mesmo teto e mesma razão do catálogo instalado: o `.zip` é artefato de APLICAÇÃO — DXF,
preview, auditoria e o `quantitativos.csv` que esta rodada vem buscar —, e um objeto sem
teto no request path da API é um blob, que sai por URL assinada e não por leitura. O pacote
real do croqui tem centenas de KB; o teto existe para nomear a fronteira, não para caber
justo."""

SCENE_QUANTITIES_MEMBER: Final = "quantitativos.csv"
"""O membro do pacote que carrega a quantidade auditada da cena. É `croquito_worker.dxf.
export_scene_package` quem o escreve, com este nome exato, depois de `ensure_exportable` e
da auditoria do DXF."""

SCENE_QUANTITIES_MAX_BYTES: Final = 4 * 1024 * 1024
"""Teto do CSV DESCOMPACTADO, conferido no cabeçalho do zip antes de descomprimir qualquer
byte. O pacote é escrito pelo nosso worker sob o prefixo do tenant, mas ler o tamanho
declarado antes de expandir custa nada e é a diferença entre um limite e uma esperança."""


class SceneLink(BaseModel):
    """O croqui aprovado que alimenta esta rodada de medição — ato humano declarado.

    O elo **nunca** é inferido. Nem por `worksite_key` igual, nem por proximidade de data,
    nem por qualquer semelhança entre a obra da rodada e o nome do projeto: é a mesma regra
    que o produto aplica em toda parte, e a rejeição central do
    `docs/adr/0058-quantitativo-derivado-do-scene-graph-e-identidade-de-elemento.md` —
    proximidade não é associação. Quem mede declara qual croqui manda.

    O elo cita o EXPORT, e não só o job: o `quantitativos.csv` é conteúdo de um pacote
    publicado a partir de uma revisão aprovada específica, e um job pode ter mais de um. Um
    export novo (nova aprovação, novo traçado) **não** muda o elo sozinho — mudar é outro ato
    declarado, com autor e instante, pela mesma rota.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    job_id: str = Field(min_length=1, max_length=36)
    scene_revision_id: str = Field(min_length=1, max_length=36)
    export_id: str = Field(min_length=1, max_length=36)
    dxf_sha256: str | None = Field(default=None, min_length=64, max_length=64)
    """Digest do DXF auditado do pacote citado, quando o export o declarou. Viaja para que
    a auditoria saiba QUAL desenho alimentou a medição, e não só de qual job ele veio."""
    declared_by: str = Field(min_length=1, max_length=128)
    declared_at: datetime


def scene_link_of(revision: ValuationRoundRevisionRecord | None) -> SceneLink | None:
    """O elo declarado nesta revisão da rodada, ou `None` quando ninguém o declarou."""
    if revision is None or revision.scene_link_json is None:
        return None
    return SceneLink.model_validate(revision.scene_link_json)


def require_scene_link(revision: ValuationRoundRevisionRecord | None) -> SceneLink:
    """O elo declarado, ou a recusa de etapa fora de ordem.

    Rodada sem elo não é rodada quebrada: é rodada que ninguém ligou a croqui nenhum, e
    responde exatamente como sempre respondeu (F-047 T4b, critério 7). Por isso a recusa tem
    código próprio e é `409`: falta um ATO — declarar o croqui —, e não um artefato perdido.
    """
    link = scene_link_of(revision)
    if link is None:
        raise RoundRefusal(
            409,
            SCENE_LINK_REQUIRED,
            "a rodada ainda não declarou o croqui aprovado que a alimenta",
            {},
        )
    return link


def scene_package_required(
    reason: str, details: Mapping[str, object] | None = None
) -> RoundRefusal:
    """Pacote citado pelo elo que não está utilizável agora: ambiente, não cadeia.

    Espelha `catalog_required`: o pacote foi conferido no ato que declarou o elo, então uma
    falha aqui é objeto sumido do store, export que deixou de estar completo ou conteúdo que
    não é o que este leitor sabe ler — nunca "a rodada não tem croqui".
    """
    return RoundRefusal(409, SCENE_PACKAGE_REQUIRED, reason, details)


def read_scene_quantities(
    store: RoundArtifactStore,
    *,
    object_key: str,
    scene_revision_id: str,
    details: Mapping[str, object],
) -> QuantitySource:
    """O `quantitativos.csv` do pacote publicado, lido do object store e tipado.

    Este é o caminho inteiro, e não há outro: `export_artifacts.package_object_key` -> bytes
    do `.zip` sob o prefixo do tenant -> membro `quantitativos.csv` -> `QuantitySource`. A
    API não reimplementa o portão de exportação nem reabre DXF nenhum; ela lê o arquivo que
    o portão já deixou passar (ADR-0058, decisão 7).

    Falha fechada em toda etapa: objeto ausente, maior que o teto, zip ilegível, membro
    ausente ou maior que o teto recusam com `SCENE_PACKAGE_REQUIRED`; CSV fora do contrato de
    colunas recusa com o código do domínio (`QUANTITY_SOURCE_CSV_INVALID`), que é o do
    módulo que sabe o que é um quantitativo.
    """
    payload = store.read_object(object_key=object_key, max_bytes=SCENE_PACKAGE_MAX_BYTES)
    if payload is None:
        raise scene_package_required(
            "o pacote do croqui citado por esta rodada não está disponível no armazenamento",
            details,
        )
    if len(payload) > SCENE_PACKAGE_MAX_BYTES:
        raise scene_package_required(
            "o pacote do croqui citado por esta rodada excede o limite de leitura",
            {**details, "max_bytes": SCENE_PACKAGE_MAX_BYTES},
        )
    try:
        with zipfile.ZipFile(BytesIO(payload)) as archive:
            try:
                member = archive.getinfo(SCENE_QUANTITIES_MEMBER)
            except KeyError as error:
                raise scene_package_required(
                    "o pacote do croqui citado não traz o quantitativo da cena",
                    {**details, "member": SCENE_QUANTITIES_MEMBER},
                ) from error
            if member.file_size > SCENE_QUANTITIES_MAX_BYTES:
                raise scene_package_required(
                    "o quantitativo da cena excede o limite de leitura",
                    {**details, "max_bytes": SCENE_QUANTITIES_MAX_BYTES},
                )
            text = archive.read(member).decode("utf-8")
    except (zipfile.BadZipFile, UnicodeDecodeError) as error:
        raise scene_package_required(
            "o pacote do croqui citado por esta rodada não pôde ser lido",
            details,
        ) from error
    return QuantitySource.from_csv_text(text, scene_revision_id=scene_revision_id)


# --- aprovação nominal e planilha publicada -----------------------------------------------


APPROVAL_ACTION: Final = "confirm"
"""A única decisão que a rota de aprovação escreve.

O domínio aceita `reject` em `ReviewerDecision`, e a recusa registrada da medição continua
sem existir no produto: o Design Approval Package da F-028 não a desenha porque ninguém
decidiu o que ela destrava na tela. Nada é desenhado como "reservado", e nada é escrito
aqui como reservado."""


def _approval_decision_id(*, reviewer_id: str, decided_at: datetime, valuation_digest: str) -> str:
    """Id determinístico do ato, no molde de `_decision_id` do takeoff (prefixo `vd_`).

    Deriva do que o ato É — quem decidiu, quando, sobre qual conteúdo —, e não de um
    contador ou de um relógio próprio: dois processos que registrassem o mesmo ato
    produziriam o mesmo id, e um id que muda sem o ato mudar não identifica nada.
    """
    canonical = json.dumps(
        {
            "action": APPROVAL_ACTION,
            "reviewer_id": reviewer_id,
            "reviewer_role": REVIEWER_ROLE,
            "decided_at": decided_at.isoformat(),
            "valuation_digest": valuation_digest,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"vd_{hashlib.sha256(canonical.encode()).hexdigest()[:16]}"


def approve_valuation(valuation: Valuation, *, reviewer_id: str, decided_at: datetime) -> Valuation:
    """A MESMA medição com a aprovação nominal embutida, amarrada por digest ao conteúdo.

    O vínculo é o `content_digest()` do próprio domínio, que exclui `approval` do cálculo
    (`models.py`): aprovar não muda o conteúdo aprovado, e por isso o digest gravado
    continua conferindo com o da medição depois do ato. Qualquer ato POSTERIOR que reescreva
    a medição faz os dois divergirem, e é o portão de exportação — nunca esta função — que
    lê essa divergência como `APPROVAL_CONTENT_MISMATCH`.

    Identidade e instante são do SERVIDOR: `reviewer_id` é o subject do JWT e `decided_at` é
    o relógio do processo. Nenhum dos dois viaja no corpo (critério 3 da F-028), e por isso
    esta função os recebe por parâmetro nomeado em vez de aceitar uma decisão pronta.

    A cópia não revalida a medição de propósito: quem entra aqui já foi revalidado pela
    leitura (`Valuation.model_validate`), o único campo que muda é `approval`, e nenhuma
    invariante de boletim ou memória de cálculo depende dele.
    """
    valuation_digest = valuation.content_digest()
    approval = ValuationApproval(
        decision=ReviewerDecision(
            decision_id=_approval_decision_id(
                reviewer_id=reviewer_id,
                decided_at=decided_at,
                valuation_digest=valuation_digest,
            ),
            action=APPROVAL_ACTION,
            reviewer_id=reviewer_id,
            reviewer_role=REVIEWER_ROLE,
            decided_at=decided_at,
        ),
        valuation_digest=valuation_digest,
    )
    return valuation.model_copy(update={"approval": approval})


def approval_state(valuation: Valuation | None) -> dict[str, Any]:
    """O bloco de aprovação que a tela lê, com a caducidade DERIVADA na leitura.

    `stale` nunca é gravado, pela mesma razão do `takeoff_overlay_state`: ele é a relação
    entre dois digests que só existe no instante da leitura. Aprovação caduca é o estado que
    o desenho aprovado da F-028 mostra por extenso — os dois digests lado a lado e uma única
    saída, aprovar de novo —, e escondê-lo faria a tela oferecer uma exportação que a rota já
    sabe que vai recusar com `APPROVAL_CONTENT_MISMATCH`.

    `approved` é `True` só para a decisão `confirm`. Uma decisão de recusa (que só o CLI
    escreve) mantém quem decidiu e quando visíveis e `approved` falso: o portão do domínio a
    recusa com `VALUATION_APPROVAL_REJECTED`, e a leitura não pode chamar de aprovada uma
    medição que a exportação recusa.

    Medição ilegível chega aqui como `None` e sai como não aprovada — a tela prefere duvidar
    a afirmar, e nenhuma exportação nasce de um artefato que não valida.
    """
    approval = None if valuation is None else valuation.approval
    if valuation is None or approval is None:
        return {
            "approved": False,
            "approved_by": None,
            "approved_at": None,
            "approved_digest": None,
            "current_digest": None if valuation is None else valuation.content_digest(),
            "stale": False,
        }
    current_digest = valuation.content_digest()
    return {
        "approved": approval.decision.action == APPROVAL_ACTION,
        "approved_by": approval.decision.reviewer_id,
        "approved_at": approval.decision.decided_at.isoformat(),
        "approved_digest": approval.valuation_digest,
        "current_digest": current_digest,
        "stale": approval.valuation_digest != current_digest,
    }


def readable_valuation(revision: ValuationRoundRevisionRecord | None) -> Valuation | None:
    """A medição gravada, ou `None` quando ela não existe **ou não valida mais**.

    Espelha `suggestions_of`: o estado por etapa não pode derrubar a tela inteira por causa
    de um artefato que deixou de validar, e quem SERVE o boletim (`GET .../bulletin`) não
    passa por aqui — lá, artefato ilegível é `422`, porque a tela não renderiza medição que
    o domínio não valida.
    """
    if revision is None or revision.valuation_json is None:
        return None
    try:
        return Valuation.model_validate(dict(revision.valuation_json))
    except (ValuationValidationError, ValidationError):
        return None


def carry_approval_forward(valuation: Valuation, previous: Valuation | None) -> Valuation:
    """Leva a aprovação anterior adiante na medição recém-montada. Preservar NÃO é aprovar.

    A aprovação carregada continua apontando para o digest ANTIGO, e a medição nova tem outro
    conteúdo — ela nasce, portanto, CADUCA por construção, e o portão de exportação a recusa
    com `APPROVAL_CONTENT_MISMATCH`. Em momento algum ela autoriza o conteúdo novo: o que ela
    faz é manter visível que uma aprovação existiu e deixou de cobrir o que está na tela.

    Descartá-la seria perder essa informação em silêncio. O orçamentista que recalculasse
    depois de aprovar veria "não aprovada", como se ninguém nunca tivesse assinado, e a tela
    não teria como oferecer a única saída correta — aprovar de novo, ciente de que o conteúdo
    mudou. É o estado de aprovação caduca do desenho aprovado da F-028.

    Nada disso é decisão do DOMÍNIO: `build_worksite_valuation` continua montando medição sem
    aprovação nenhuma, que é o certo para uma função que só sabe calcular. Quem tem a
    revisão anterior em mãos, e portanto pode responder "houve aprovação antes?", é a rota.

    Medição anterior ilegível chega aqui como `None` e nada é carregado: uma aprovação que
    não se consegue reler não é uma aprovação que se possa afirmar que existiu.
    """
    if previous is None or previous.approval is None:
        return valuation
    return valuation.model_copy(update={"approval": previous.approval})


GATE_CONTRACT_GROUP_LABEL: Final = "MEDICAO CORRENTE"
GATE_CONTRACT_SOURCE_LABEL: Final = (
    "medição corrente: a rodada de /v1 não importa consolidado contratual"
)


def bulletin_export_contract(valuation: Valuation) -> ContractWorkbook:
    """O consolidado que a rodada de `/v1` TEM para oferecer ao portão de exportação.

    `Valuation.ensure_exportable()` exige um `ContractWorkbook` porque o saldo contratual
    mora nele, e não na medição. A cadeia de `/v1` não importa consolidado nenhum: ela
    instala um catálogo de preços na criação da rodada e monta o boletim com ele
    (`POST .../calc`, `calc_plan=None`). Não existe rota, coluna nem artefato de onde tirar
    contratado, acumulado e saldo — e inventar esses números para "passar" no portão seria
    exatamente a fraude que o portão existe para impedir.

    Então este consolidado declara só o que a rodada sabe: os códigos que a medição
    corrente mede, pelo preço e pela unidade que a própria medição registrou, com saldo igual
    ao que está sendo medido e os períodos anteriores ao dela. A consequência é declarada, e
    não escondida:

    - `PERIOD_NOT_SEQUENTIAL`, `BALANCE_EXCEEDED`, `CODE_NOT_IN_CONTRACT`,
      `CODE_AMBIGUOUS_IN_CONTRACT`, `LINE_PRICE_NOT_IN_CONTRACT` e
      `LINE_UNIT_NOT_IN_CONTRACT` **não podem disparar** por aqui. A rodada não tem o fato
      que os alimentaria, e um código que nunca dispara é honesto quando está escrito; o
      perigoso é o que finge conferir.
    - o que continua valendo integralmente é a APROVAÇÃO — `VALUATION_NOT_APPROVED`,
      `VALUATION_APPROVAL_REJECTED` e `APPROVAL_CONTENT_MISMATCH` —, que é o que a F-028
      transforma em recusa de rota (VAL-05).
    - a conferência entre o boletim e o catálogo instalado não se perde: ela acontece no
      AUDITOR, que compara cada preço impresso com `catalog.entry_for(code)` e reprova com
      `CATALOG_PRICE_MISMATCH`/`CATALOG_CODE_MISSING` — e auditoria reprovada não publica.

    Este objeto é insumo do portão e de mais nada: ele nunca é persistido, nunca vai para a
    planilha (que é escrita com `contract=None`, porque a rodada não tem PLANILHA GERAL nem
    RE-RA a imprimir) e nunca volta ao cliente. `source_sha256` é o digest do conteúdo da
    própria medição, para que a origem do consolidado seja legível a quem o encontrar.

    Trazer saldo de verdade para `/v1` é importar o consolidado contratual — trabalho de
    marco próprio, com rota, coluna e ADR, e não de um parâmetro montado dentro de uma rota.
    """
    measured: dict[str, Decimal] = {}
    priced: dict[str, tuple[str, Decimal, str]] = {}
    for bulletin in valuation.bulletins:
        for line in bulletin.lines:
            measured[line.code] = measured.get(line.code, Decimal("0.00")) + line.quantity
            priced.setdefault(line.code, (line.unit, line.unit_price, line.description))
    lines: list[ContractLine] = []
    for index, code in enumerate(sorted(measured), start=1):
        unit, unit_price, description = priced[code]
        quantity = measured[code]
        lines.append(
            ContractLine(
                group_label=GATE_CONTRACT_GROUP_LABEL,
                item_number=str(index),
                code=code,
                description=description,
                unit=unit,
                unit_price=unit_price,
                contract_quantity=quantity,
                amended_quantity=quantity,
                periods=[],
                accumulated_quantity=Decimal("0.00"),
                accumulated_amount=Decimal("0.00"),
                balance_quantity=quantity,
            )
        )
    return ContractWorkbook(
        source_label=GATE_CONTRACT_SOURCE_LABEL,
        source_sha256=valuation.content_digest(),
        period_numbers=list(range(1, valuation.period_number)),
        lines=lines,
    )


@dataclass(frozen=True, slots=True)
class RenderedBulletinWorkbook:
    """A planilha do boletim já auditada, ainda em memória: bytes e o laudo que a aprovou."""

    body: bytes
    audit: AuditReport


def render_valuation_workbook(
    valuation: Valuation,
    catalog: PriceCatalog,
    template: WorkbookTemplate,
    contract: ContractWorkbook | None = None,
) -> RenderedBulletinWorkbook:
    """Grava a pasta num arquivo temporário, reabre, audita e só então devolve os bytes.

    Mesmo desenho fail-closed de `run_export_valuation` no worker e de
    `estimate_rounds.render_estimate_workbook`: o arquivo nasce em nome pendente — aqui, num
    diretório temporário que morre com a chamada — e a auditoria de round-trip é quem decide
    se ele existe para alguém. Nada chega ao object store antes disso, e auditoria reprovada
    não publica.

    A API não importa o CLI: o gate é replicado com as funções do pacote `valuation`, porque
    o comando de fila e a rota são processos diferentes e um importar o outro faria a
    fronteira de `services/` depender do CLI.

    `contract` acompanha a assinatura do escritor e do auditor e é `None` na rodada de `/v1`,
    que não tem consolidado a imprimir; ver `bulletin_export_contract`.
    """
    with tempfile.TemporaryDirectory(prefix="croquito-bulletin-") as directory:
        path = Path(directory) / "boletim.xlsx"
        write_valuation_workbook(valuation, catalog, template, path, contract)
        audit = audit_workbook(path, valuation, catalog, template, contract)
        if audit.status != "ok":
            raise bulletin_workbook_audit_failed(audit)
        return RenderedBulletinWorkbook(body=path.read_bytes(), audit=audit)


def bulletin_workbook_key(*, tenant_id: str, round_id: str, valuation_sha256: str) -> str:
    """Chave do `.xlsx` sob o prefixo do tenant, endereçada pelo digest da medição.

    Endereçar pelo conteúdo — e não por um nome fixo — é o que impede uma exportação nova de
    sobrescrever a planilha que a revisão anterior ainda referencia: cada revisão aponta para
    o boletim que ela publicou, e uma URL assinada emitida antes continua servindo exatamente
    o que foi auditado quando foi emitida.
    """
    return f"tenants/{tenant_id}/valuation-rounds/{round_id}/bulletin/{valuation_sha256}.xlsx"


def bulletin_workbook_ref(revision: ValuationRoundRevisionRecord | None) -> str | None:
    """Chave do `.xlsx` publicado gravada na revisão, ou `None` quando não há planilha."""
    if revision is None:
        return None
    key = (revision.artifact_refs_json or {}).get(BULLETIN_WORKBOOK_REF)
    return key if isinstance(key, str) and key else None


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


def _contracted_state(round_record: ValuationRoundRecord) -> dict[str, Any]:
    """O regime de conferência da rodada, e o que ele custa quando não há origem assinada.

    `signed` é o único caso em que os seis guardrails contratuais podem disparar. `none` é o
    estado de sempre, e ele é DECLARADO em vez de deduzido pela ausência de um campo: quem lê
    a rodada precisa saber que ali não se confere saldo, e não descobrir isso por omissão.

    A contagem de linhas e o total não revalidam o consolidado — é leitura de estado, e um
    consolidado ilegível não pode derrubar a tela inteira. Quem revalida é o portão de
    exportação, que é onde a resposta importa.
    """
    stored = round_record.contract_workbook_json
    if round_record.estimate_round_id is None or stored is None:
        return {"origin": "none", "estimate_round_id": None, "estimate_digest": None}
    lines = stored.get("lines")
    return {
        "origin": "signed_estimate",
        "estimate_round_id": round_record.estimate_round_id,
        "estimate_digest": round_record.estimate_digest,
        "code_count": len(lines) if isinstance(lines, list) else None,
        # Reajustes declarados na abertura (F-039). Lista vazia é ausência de reajuste, que é
        # a verdade sobre a rodada — e não um campo que some, porque a tela precisa distinguir
        # "não reajustou" de "não sei".
        "price_adjustments": _declared_adjustments(stored),
        "prices": _contracted_prices(stored),
        # RE-RA declaradas na abertura (F-040). Lista vazia é ausência de re-ratificação, que
        # é a verdade sobre a rodada — mesma disciplina do reajuste.
        "amendments": _declared_amendments(stored),
        "quantities": _contracted_quantities(stored),
    }


def _declared_adjustments(stored: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Os reajustes como foram declarados, sem revalidar o consolidado.

    Leitura de estado não pode derrubar a tela por causa de um consolidado ilegível — mesma
    razão do resto desta função. Quem revalida é o portão de exportação.
    """
    declarados = stored.get("adjustments")
    if not isinstance(declarados, list):
        return []
    return [item for item in declarados if isinstance(item, dict)]


def _declared_amendments(stored: Mapping[str, Any]) -> list[dict[str, Any]]:
    """As RE-RA como foram declaradas, sem revalidar o consolidado (mesma razão do reajuste)."""
    declaradas = stored.get("amendments")
    if not isinstance(declaradas, list):
        return []
    return [item for item in declaradas if isinstance(item, dict)]


def _contracted_quantities(stored: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Contratado e vigente por código: a conta de quantidade que a memória mostra.

    O vigente é recomputado do consolidado gravado, e não lido de um campo — ele é derivado
    por decisão (ADR-0056, decisão 3). Consolidado que não revalida devolve lista vazia em vez
    de erro, pelo mesmo motivo dos demais campos desta leitura.
    """
    try:
        contract = ContractWorkbook.model_validate(dict(stored))
    except ValidationError:
        return []
    return [
        {
            "code": line.code,
            "item_number": line.item_number,
            "description": line.description,
            "unit": line.unit,
            "contracted_quantity": str(line.contract_quantity),
            "current_quantity": str(contract.current_quantity(line)),
            "current_balance_quantity": str(contract.current_balance_quantity(line)),
            "re_ratified": contract.current_quantity(line) != line.contract_quantity,
        }
        for line in contract.lines
    ]


def _contracted_prices(stored: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Contratado e vigente por código: a conta que a memória mostra.

    O vigente é recomputado aqui a partir do consolidado gravado, e não lido de um campo —
    ele é derivado por decisão (ADR-0055, decisão 3). Consolidado que não revalida devolve
    lista vazia em vez de erro, pelo mesmo motivo dos demais campos desta leitura.
    """
    try:
        contract = ContractWorkbook.model_validate(dict(stored))
    except ValidationError:
        return []
    return [
        {
            "code": line.code,
            "item_number": line.item_number,
            "description": line.description,
            "unit": line.unit,
            "contracted_unit_price": str(line.unit_price),
            "current_unit_price": str(contract.current_unit_price(line)),
            "adjusted": contract.current_unit_price(line) != line.unit_price,
        }
        for line in contract.lines
    ]


def _scene_link_state(revision: ValuationRoundRevisionRecord | None) -> dict[str, Any]:
    """O croqui declarado desta rodada, ou a ausência DECLARADA dele (F-047 T4b).

    `present: false` é informação, não omissão: rodada sem elo é rodada que ninguém ligou a
    croqui nenhum, e a tela precisa dizer isso em vez de deixar o campo sumir. Só ids,
    digest e o carimbo do ato saem daqui — nada do conteúdo do croqui atravessa a fronteira
    da medição por esta leitura.
    """
    link = scene_link_of(revision)
    if link is None:
        return {"present": False}
    return {
        "present": True,
        "job_id": link.job_id,
        "scene_revision_id": link.scene_revision_id,
        "export_id": link.export_id,
        "dxf_sha256": link.dxf_sha256,
        "declared_by": link.declared_by,
        "declared_at": link.declared_at.isoformat(),
    }


def round_state_payload(
    round_record: ValuationRoundRecord,
    revision: ValuationRoundRevisionRecord | None,
    plates: Sequence[ValuationRoundPlateRecord],
) -> dict[str, Any]:
    """Estado da rodada por etapa, espelhando o `/state` do servidor de medição.

    Espelha o conteúdo, não as chaves: o que era diretório (`root`, nome de arquivo) some,
    e as chaves saem em inglês, como todo identificador deste repositório — as duas em
    português do `_state_payload` (`extracao`, `busca_semantica`) eram do servidor local, e
    aqui o consumidor são os tipos gerados de `@croquito/contracts`.

    A etapa entra por PRESENÇA e digest; revalidar boletim ou dossiê é papel de quem os
    serve. Uma medição ilegível não pode derrubar a tela inteira antes de o orçamentista
    sequer chegar nela — a mesma regra que o servidor de medição já segue.

    O bloco de aprovação é a única coisa aqui que precisa LER a medição, porque o vínculo da
    aprovação é um digest do conteúdo e não uma coluna. A leitura é a tolerante
    (`readable_valuation`): artefato que não valida sai como não aprovado, e não derruba o
    estado da rodada.

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
        # Contra o que esta rodada confere (F-036, ADR-0048 decisão 9). Rodada com vínculo e
        # rodada sem vínculo têm garantias diferentes e não podem parecer iguais na tela: sem
        # `estimate_round_id` o consolidado é FABRICADO a partir da própria medição, e saldo,
        # período e código fora do contrato não são verificados.
        "contracted": _contracted_state(round_record),
        "artifacts": digests,
        # A PRIMEIRA folha da praça, que é a folha única da rodada de sempre: este bloco
        # responde exatamente como antes da F-046 para a praça de uma folha. Quantas folhas
        # a praça tem, e o estado de cada uma, é o bloco `worksite` e a rota da praça.
        "plate": {
            "present": bool(plates),
            "source_sha256": plates[0].source_sha256 if plates else None,
            # Da FOLHA desde a T4, e não mais da raiz: o valor é o mesmo para a praça de uma
            # folha (a raiz continua sendo escrita como espelho dela), e passa a ser o certo
            # quando a praça tem mais de uma — a raiz descreveria o PDF da primeira.
            "page_count": plates[0].page_count if plates else None,
        },
        "worksite": {
            "plate_count": len(plates),
            "plate_ids": [plate.plate_id for plate in plates],
            "identity_link_count": len(
                (None if revision is None else revision.worksite_identity_links_json) or []
            ),
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
        "scene_link": _scene_link_state(revision),
        "takeoff": takeoff,
        "codes": codes,
        "bulletin": {
            "present": "valuation_json" in digests,
            "valuation_sha256": digests.get("valuation_json"),
            "workbook_present": bulletin_workbook_ref(revision) is not None,
            "workbook_sha256": digests.get(BULLETIN_WORKBOOK_DIGEST),
            "approval": approval_state(readable_valuation(revision)),
        },
        "dossier": {
            "present": "amendment_dossier_json" in digests,
            "dossier_sha256": digests.get("amendment_dossier_json"),
        },
        "created_at": round_record.created_at.isoformat(),
        "updated_at": round_record.updated_at.isoformat(),
    }
