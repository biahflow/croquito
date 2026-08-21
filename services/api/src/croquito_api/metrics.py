"""Read-model de valor: cycle time, ato humano e custo de IA derivados do que já existe.

Camada de aplicação de `/v1/jobs/{job_id}/metrics` e `/v1/metrics/summary` (F-031 T3),
**sem** FastAPI, no mesmo molde de `valuation_rounds.py`: nada aqui recebe `Request`, monta
`Response` ou conhece código de status. É isso que permite ao `croquito-demo value-report`
produzir o MESMO documento que a rota, direto do banco e sem autenticação — um segundo
cálculo, escrito à parte para o CLI, seria a garantia de que os dois números divergiriam.

Três regras atravessam tudo o que sai daqui:

- **Nada é persistido.** Toda linha deste módulo lê fatos que outro ato já gravou
  (`job_stage_events`, `review_decisions`, `chat_turns`, lineage do pacote). Métrica
  materializada envelheceria em silêncio quando o fato de origem fosse corrigido.
- **Taxa com denominador zero é `None`, nunca `0.0`.** "Nenhuma decisão ainda" e "nenhuma
  correção sobre as decisões que houve" são estados diferentes, e um `0.0` no lugar do
  ausente faria o dashboard afirmar qualidade que ninguém mediu.
- **Toda query filtra por `tenant_id` no MESMO `where` do `job_id`/`round_id`.** O
  isolamento não depende de o chamador ter lembrado de conferir depois.

O que este módulo NÃO faz: `automation.auto_association_rate` e `automation.review_rate`
saem `None` de propósito — os valores reais são da F-029, e emitir um número inventado
antes dela seria pior que declarar a ausência.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator, Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Final

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from croquito_api.database import (
    ChatTurnRecord,
    EstimateRoundRecord,
    EstimateRoundRevisionRecord,
    JobRecord,
    JobStageEventRecord,
    ReviewDecisionRecord,
    ReviewRevisionRecord,
    ValuationRoundRecord,
    ValuationRoundRevisionRecord,
)

#: As ações de decisão de leitura que são ato humano PRIMÁRIO sobre a proposta da máquina
#: (`main.ReviewDecisionCommand.action`). A retificação (`rectify_confirm`/`rectify_reject`)
#: fica deliberadamente FORA desta lista e é contada em `rectifications`: ela corrige o
#: registro de uma pessoa, não a proposta de um modelo, e somá-la aqui inflaria o
#: denominador de `correction_rate` com atos que não são sobre a máquina.
PRIMARY_DECISION_ACTIONS: Final[tuple[str, ...]] = ("confirm", "correct", "reject")

#: Prefixo das ações de retificação gravadas por `POST .../review/rectifications`.
RECTIFICATION_ACTION_PREFIX: Final = "rectify_"

#: Casas decimais das taxas publicadas. Sem arredondar, `1/3` sairia como
#: `0.3333333333333333` — ruído de binário flutuante apresentado como precisão de medida.
RATE_DECIMAL_PLACES: Final = 6

COMPLETED_JOB_STATUS: Final = "COMPLETED"
FAILED_JOB_STATUS: Final = "FAILED"


class MetricsPeriodError(ValueError):
    """O período pedido não é legível ou está invertido; quem chama traduz em 422."""


def _as_utc(value: datetime) -> datetime:
    """Reancora em UTC o instante que o SQLite devolve naive.

    O `bind_processor` do `DATETIME` do SQLite descarta o offset na gravação, então a mesma
    coluna volta naive ali e aware no PostgreSQL (`timestamptz`). Subtrair um naive de um
    aware levantaria `TypeError` no meio de uma rota de leitura; reancorar recupera o mesmo
    instante, porque os dois escritores (API por ORM, worker por SQL cru) gravam UTC.
    """
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _duration_ms(started_at: datetime | None, finished_at: datetime | None) -> int | None:
    """Intervalo em milissegundos, ou `None` quando ele não é mensurável.

    Espelha `croquito_worker.local_queue._duration_ms`, inclusive na recusa do delta
    NEGATIVO: API e worker são processos diferentes e podem ter relógios em desacordo.
    Publicar negativo envenenaria o cycle time do consumidor e publicar zero inventaria uma
    medida que ninguém fez — `None` é a única resposta honesta para "não medido".
    """
    if started_at is None or finished_at is None:
        return None
    elapsed = (_as_utc(finished_at) - _as_utc(started_at)).total_seconds() * 1000
    return int(elapsed) if elapsed >= 0 else None


def _rate(numerator: int, denominator: int) -> float | None:
    """Taxa arredondada, `None` quando não há denominador. Nunca divide por zero."""
    if denominator <= 0:
        return None
    return round(numerator / denominator, RATE_DECIMAL_PLACES)


def _decimal(value: object) -> Decimal | None:
    """Lê custo gravado como TEXTO decimal; valor ilegível é ausência, nunca zero.

    O custo viaja como string em `chat_turns.estimated_cost_usd` e no lineage justamente
    porque `float` perde centavo em soma — e é somando que o portal calcula custo por
    transação. Um texto que não é decimal (linha antiga, escrita por caminho que já não
    existe) não pode virar `0` em silêncio: some da conta e a conta continua declarada.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str):
        try:
            return Decimal(value)
        except InvalidOperation:
            return None
    return None


def _positive_int(value: object) -> int:
    """Contagem de tokens vinda de coluna/JSON opcional; ausente ou inválida vale 0."""
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return value if value > 0 else 0


class _AiCost:
    """Acumulador de custo de IA: chamadas, tokens e dólares exatos.

    `Decimal` do início ao fim e string na saída, pela mesma razão que a coluna é texto.
    """

    __slots__ = ("calls", "cost", "input_tokens", "output_tokens")

    def __init__(self) -> None:
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.cost = Decimal("0")

    def add(
        self,
        *,
        input_tokens: object,
        output_tokens: object,
        estimated_cost_usd: object,
    ) -> None:
        self.calls += 1
        self.input_tokens += _positive_int(input_tokens)
        self.output_tokens += _positive_int(output_tokens)
        cost = _decimal(estimated_cost_usd)
        if cost is not None and cost > 0:
            self.cost += cost

    def merge(self, other: _AiCost) -> None:
        self.calls += other.calls
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cost += other.cost

    def document(self) -> dict[str, Any]:
        return {
            "calls": self.calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "estimated_cost_usd": str(self.cost),
        }


def _distinct(entries: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """Deduplica lineage por conteúdo canônico. É o que impede multiplicar o custo.

    UMA chamada de provider produz o pacote INTEIRO, e `provider_review` anexa a MESMA
    lista de `ProviderLineage` a CADA leitura (`provider_review.py:554-558`). Somar por
    leitura multiplicaria o custo real pelo número de cotas da folha — numa prancha com 36
    leituras, o custo publicado seria 36 vezes o gasto. A mesma armadilha existe na cadeia
    de medição: a revisão append-only carrega `extraction_lineage_json` da cabeça para a
    frente, então o mesmo lineage aparece em toda revisão posterior.

    A chave é o conteúdo INTEIRO da entrada, não um par escolhido a dedo: `latency_ms` e
    `raw_response_ref` separam duas execuções reais do mesmo prompt sobre a mesma entrada.
    Duas execuções idênticas em TODOS os campos são indistinguíveis a partir do que ficou
    gravado, e contá-las como uma subestima — subestimar custo é o erro tolerável aqui;
    multiplicá-lo por dezenas não é.
    """
    seen: dict[str, Mapping[str, Any]] = {}
    for entry in entries:
        key = json.dumps(entry, sort_keys=True, ensure_ascii=False, default=str)
        seen.setdefault(key, entry)
    return list(seen.values())


def _packet_lineage(packet: Mapping[str, Any] | None) -> Iterator[Mapping[str, Any]]:
    """Percorre `readings[].provider_lineage[]` do pacote persistido, sem revalidá-lo.

    Leitura defensiva de propósito: `packet_json` é documento gravado e pode ter nascido
    antes de qualquer campo desta fatia. Validar com `ReviewPacket` aqui faria uma rota de
    LEITURA de métrica falhar por causa de um pacote antigo que a tela de revisão continua
    abrindo sem problema.
    """
    if not isinstance(packet, Mapping):
        return
    readings = packet.get("readings")
    if not isinstance(readings, Sequence) or isinstance(readings, str | bytes):
        return
    for reading in readings:
        if not isinstance(reading, Mapping):
            continue
        lineage = reading.get("provider_lineage")
        if not isinstance(lineage, Sequence) or isinstance(lineage, str | bytes):
            continue
        for entry in lineage:
            if isinstance(entry, Mapping):
                yield entry


def _latest_review_packet(session: Session, job: JobRecord) -> Mapping[str, Any] | None:
    """Pacote da revisão de leitura CORRENTE do job.

    Só a corrente: a cadeia de revisões é append-only e cada ato humano copia o pacote
    inteiro para a linha nova, então varrer todas somaria o mesmo lineage tantas vezes
    quantas decisões a folha recebeu.
    """
    packet = session.scalar(
        select(ReviewRevisionRecord.packet_json)
        .where(
            ReviewRevisionRecord.job_id == job.id,
            ReviewRevisionRecord.tenant_id == job.tenant_id,
        )
        .order_by(ReviewRevisionRecord.version.desc())
    )
    return packet if isinstance(packet, Mapping) else None


def _cycle_document(session: Session, job: JobRecord) -> dict[str, Any]:
    """Cycle time por etapa a partir de `job_stage_events`.

    A duração de uma etapa é o intervalo até a transição SEGUINTE — por isso a última
    linha sai sem `duration_ms`: a etapa corrente está aberta e ninguém sabe quando ela
    termina. `total_ms` conta da criação do job até a última transição registrada.

    O desempate por `id` não é enfeite: `id` é UUIDv7, monotônico por construção, e duas
    transições podem cair no mesmo microssegundo — sem ele a ordem das etapas dependeria do
    plano de execução do banco.
    """
    events = list(
        session.scalars(
            select(JobStageEventRecord)
            .where(
                JobStageEventRecord.job_id == job.id,
                JobStageEventRecord.tenant_id == job.tenant_id,
            )
            .order_by(JobStageEventRecord.created_at, JobStageEventRecord.id)
        )
    )
    stages: list[dict[str, Any]] = []
    for position, event in enumerate(events):
        following = events[position + 1] if position + 1 < len(events) else None
        stages.append(
            {
                "stage": event.to_stage,
                "status": event.to_status,
                "duration_ms": (
                    None
                    if following is None
                    else _duration_ms(event.created_at, following.created_at)
                ),
            }
        )
    total_ms = None if not events else _duration_ms(job.created_at, events[-1].created_at)
    return {"total_ms": total_ms, "stages": stages}


def _human_document(session: Session, job: JobRecord) -> dict[str, Any]:
    """Atos humanos do job: revisões, decisões por desfecho e correção declarada.

    `decisions_total` é a soma exata de `confirmed + corrected + rejected`, e nada mais:
    manter a identidade permite conferir a conta de fora. `rectifications` fica ao lado, e
    não dentro — ver `PRIMARY_DECISION_ACTIONS`.
    """
    review_revisions = session.scalar(
        select(func.count())
        .select_from(ReviewRevisionRecord)
        .where(
            ReviewRevisionRecord.job_id == job.id,
            ReviewRevisionRecord.tenant_id == job.tenant_id,
        )
    )
    actions = list(
        session.scalars(
            select(ReviewDecisionRecord.action).where(
                ReviewDecisionRecord.job_id == job.id,
                ReviewDecisionRecord.tenant_id == job.tenant_id,
            )
        )
    )
    counts = {action: 0 for action in PRIMARY_DECISION_ACTIONS}
    rectifications = 0
    for action in actions:
        if action in counts:
            counts[action] += 1
        elif action.startswith(RECTIFICATION_ACTION_PREFIX):
            rectifications += 1
    corrected = counts["correct"]
    # A soma é sobre a lista fechada, e não sobre as linhas: uma ação nova que a API
    # passasse a gravar não entraria no denominador em silêncio — apareceria como
    # divergência entre `decisions_total` e o que a revisão registrou.
    decisions_total = sum(counts.values())
    return {
        "review_revisions": int(review_revisions or 0),
        "decisions_total": decisions_total,
        "confirmed": counts["confirm"],
        "corrected": corrected,
        "rejected": counts["reject"],
        "correction_rate": _rate(corrected, decisions_total),
        "rectifications": rectifications,
        # Touch time real é a T4 desta feature; até ela existir, `null` diz "não medido" —
        # que é a verdade. Derivar duração de `created_at` de decisões consecutivas seria
        # medir o intervalo entre envios, não o tempo que a pessoa passou na tela.
        "interaction_ms_total": None,
    }


def _job_ai_cost(session: Session, job: JobRecord) -> _AiCost:
    """Custo de IA do job: turnos de conversa + lineage do pacote de revisão corrente.

    Um turno conta como chamada quando gravou `provider` — é esse campo que o worker
    preenche exatamente quando houve execução real (`local_queue._write_chat_turn_result`),
    inclusive na recusa. Turno `QUEUED` que nunca chamou ninguém não entra na conta.
    """
    cost = _AiCost()
    turns = session.scalars(
        select(ChatTurnRecord).where(
            ChatTurnRecord.job_id == job.id,
            ChatTurnRecord.tenant_id == job.tenant_id,
        )
    )
    for turn in turns:
        if turn.provider is None:
            continue
        cost.add(
            input_tokens=turn.input_tokens,
            output_tokens=turn.output_tokens,
            estimated_cost_usd=turn.estimated_cost_usd,
        )
    for entry in _distinct(_packet_lineage(_latest_review_packet(session, job))):
        cost.add(
            input_tokens=entry.get("input_tokens"),
            output_tokens=entry.get("output_tokens"),
            estimated_cost_usd=entry.get("estimated_cost_usd"),
        )
    return cost


def compute_job_metrics(session: Session, job: JobRecord) -> dict[str, Any]:
    """Documento de métricas de UM job, pronto para virar JSON sem conversão.

    Recebe o `JobRecord` já carregado, e não um par `(job_id, tenant_id)`, de propósito: é
    quem carrega que aplica o escopo de tenant, e a rota faz isso no mesmo `where` das
    vizinhas (job de outro tenant é inexistente, `404`). O CLI carrega pelo id e usa o
    tenant da própria linha. Assim não existe nesta assinatura um `tenant_id=None` que
    signifique "sem filtro" e que alguém possa passar de dentro de uma rota.
    """
    return {
        "job_id": job.id,
        "cycle": _cycle_document(session, job),
        "human": _human_document(session, job),
        # Placeholders declarados: os valores reais são da F-029 (auto-associação por
        # confiança). Enquanto ela não aterrissa, o campo existe no contrato e diz `null`.
        "automation": {"auto_association_rate": None, "review_rate": None},
        "ai_cost": _job_ai_cost(session, job).document(),
    }


def parse_period_bound(value: str | None, *, field: str) -> datetime | None:
    """Lê um limite de período ISO 8601 e o normaliza para UTC.

    Naive é lido como UTC (o contrato da API diz que timestamp é UTC); com offset, é
    CONVERTIDO para UTC antes de virar bind — sem isso, no SQLite o `bind_processor`
    descartaria o offset e `2026-08-21T00:00:00-03:00` compararia como meia-noite UTC,
    errando o recorte em três horas sem nenhum sintoma.
    """
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise MetricsPeriodError(f"{field} não é um instante ISO 8601 válido") from error
    return parsed.astimezone(UTC) if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _round_extraction_cost(
    session: Session,
    *,
    tenant_id: str,
    round_ids: Sequence[str],
    revision_model: type[ValuationRoundRevisionRecord] | type[EstimateRoundRevisionRecord],
) -> _AiCost:
    """Custo das extrações pagas de uma cadeia de rodadas, deduplicado por execução.

    Varre TODAS as revisões das rodadas do recorte, e não só a cabeça: uma rodada extraída
    duas vezes guarda o lineage antigo na revisão anterior, e ler só a cabeça perderia a
    primeira chamada paga. O que impede a contagem dupla do lineage carregado adiante é o
    `_distinct`, não a escolha da linha.
    """
    cost = _AiCost()
    if not round_ids:
        return cost
    lineages = session.scalars(
        select(revision_model.extraction_lineage_json).where(
            revision_model.round_id.in_(round_ids),
            revision_model.tenant_id == tenant_id,
        )
    )
    executions = [
        lineage["execution"]
        for lineage in lineages
        if isinstance(lineage, Mapping) and isinstance(lineage.get("execution"), Mapping)
    ]
    for execution in _distinct(executions):
        cost.add(
            input_tokens=execution.get("input_tokens"),
            output_tokens=execution.get("output_tokens"),
            estimated_cost_usd=execution.get("estimated_cost_usd"),
        )
    return cost


def _average(values: Sequence[int]) -> int | None:
    """Média inteira em ms; `None` quando nada foi medido — nunca zero por vazio."""
    if not values:
        return None
    return round(sum(values) / len(values))


def compute_tenant_summary(
    session: Session,
    *,
    tenant_id: str,
    period_start: datetime | None,
    period_end: datetime | None,
) -> dict[str, Any]:
    """Agregado do tenant no período, recortado por `created_at` do job e da rodada.

    O agregado é a soma dos MESMOS documentos que `/v1/jobs/{id}/metrics` devolve, job a
    job. É deliberadamente mais caro do que uma query de agregação: uma segunda expressão
    do cálculo poderia divergir da rota por job, e é exatamente essa divergência que faria
    o dashboard e a auditoria de um job contarem histórias diferentes. Rota de relatório,
    não de request path quente.
    """
    query = select(JobRecord).where(JobRecord.tenant_id == tenant_id)
    if period_start is not None:
        query = query.where(JobRecord.created_at >= period_start)
    if period_end is not None:
        query = query.where(JobRecord.created_at <= period_end)
    jobs = list(session.scalars(query.order_by(JobRecord.created_at, JobRecord.id)))

    jobs_completed = 0
    jobs_failed = 0
    cycle_totals: list[int] = []
    correction_rates: list[float] = []
    ai_cost = _AiCost()
    for job in jobs:
        if job.status == COMPLETED_JOB_STATUS:
            jobs_completed += 1
        elif job.status == FAILED_JOB_STATUS:
            jobs_failed += 1
        metrics = compute_job_metrics(session, job)
        total_ms = metrics["cycle"]["total_ms"]
        if isinstance(total_ms, int):
            cycle_totals.append(total_ms)
        correction_rate = metrics["human"]["correction_rate"]
        if isinstance(correction_rate, float):
            correction_rates.append(correction_rate)
        ai_cost.merge(_job_ai_cost(session, job))

    valuation_ids = _round_ids(
        session,
        model=ValuationRoundRecord,
        tenant_id=tenant_id,
        period_start=period_start,
        period_end=period_end,
    )
    estimate_ids = _round_ids(
        session,
        model=EstimateRoundRecord,
        tenant_id=tenant_id,
        period_start=period_start,
        period_end=period_end,
    )
    rounds_cost = _round_extraction_cost(
        session,
        tenant_id=tenant_id,
        round_ids=valuation_ids,
        revision_model=ValuationRoundRevisionRecord,
    )
    rounds_cost.merge(
        _round_extraction_cost(
            session,
            tenant_id=tenant_id,
            round_ids=estimate_ids,
            revision_model=EstimateRoundRevisionRecord,
        )
    )

    return {
        "period": {
            "from": None if period_start is None else period_start.isoformat(),
            "to": None if period_end is None else period_end.isoformat(),
        },
        "jobs_total": len(jobs),
        "jobs_completed": jobs_completed,
        "jobs_failed": jobs_failed,
        # Denominador declarado ao lado da média: sem ele, "0.25" não diz se veio de quatro
        # decisões de um job ou de centenas espalhadas por muitos.
        "jobs_with_decisions": len(correction_rates),
        "avg_cycle_total_ms": _average(cycle_totals),
        "avg_correction_rate": (
            None
            if not correction_rates
            else round(sum(correction_rates) / len(correction_rates), RATE_DECIMAL_PLACES)
        ),
        "ai_cost": ai_cost.document(),
        "valuation_rounds_total": len(valuation_ids),
        "estimate_rounds_total": len(estimate_ids),
        "rounds_ai_cost": rounds_cost.document(),
    }


def _round_ids(
    session: Session,
    *,
    model: type[ValuationRoundRecord] | type[EstimateRoundRecord],
    tenant_id: str,
    period_start: datetime | None,
    period_end: datetime | None,
) -> list[str]:
    """Ids das rodadas do tenant criadas no recorte; serve as duas cadeias sem duplicar."""
    query = select(model.id).where(model.tenant_id == tenant_id)
    if period_start is not None:
        query = query.where(model.created_at >= period_start)
    if period_end is not None:
        query = query.where(model.created_at <= period_end)
    return list(session.scalars(query))
