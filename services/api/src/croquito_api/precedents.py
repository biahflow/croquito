"""Índice de precedentes de código na fronteira da API: as duas fontes e a consulta.

Camada de aplicação sem FastAPI, como `site_setup_kits.py` e `estimate_rounds.py`: nada aqui
recebe `Request`, monta `Response` nem conhece código de status por si só. A normalização do
rótulo e o contrato do pacote de semeadura são da T1 e vivem em
`croquito_valuation.precedent`; nada disso é reimplementado aqui.

O índice existe porque a shortlist recomeça do zero em toda praça, e o dado bom já está no
banco: a F-038 gravou os pares `(item, código)` confirmados, e a medição do Human Gate 1 da
F-044 mostrou que 80% dos rótulos reaparecem entre praças, com 96,1% dos repetidos trazendo
pacote idêntico ou contido. **Precedente é observação, nunca decisão** — quem lê isto (a T3)
oferece, e o clique continua sendo da orçamentista.

Quatro invariantes atravessam este módulo:

- **precedente nunca atravessa tenant**. A cláusula está escrita UMA vez
  (`visible_observations`), e diferente do acervo de canteiro não há origem de plataforma: o
  histórico de decisões de um escritório mostrado a outro seria vazar a forma de trabalhar de
  um cliente para um concorrente;
- **a chave é `(rótulo normalizado, fonte de preço)`**, nunca o rótulo sozinho (decisão 4 do
  escopo da feature). Sugerir código que não existe na tabela vigente é pior que não sugerir
  nada;
- **a contagem de praças não infla**. É o número que a tela mostra como argumento de
  autoridade, e por isso refechar o mesmo pacote e reingerir a mesma praça são idempotentes,
  e praça semeada que colide com rodada real é recusa nomeada;
- **a consulta não escreve nem paga nada**. É `SELECT` sobre o que já está gravado; o `GET`
  da shortlist continua sem custo e sem avançar a versão da rodada (ADR-0054 D7).

Rótulo de legenda é texto de cliente: ele entra em coluna de banco (o mesmo dado que
`takeoff_packet_json` já guarda) e **nunca** em log estruturado nem em auditoria.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from croquito_api.database import EstimateRoundRecord, PrecedentObservationRecord
from croquito_api.valuation_rounds import RoundRefusal
from croquito_core.ids import new_uuid7
from croquito_valuation.assignment import CodeAssignmentSet
from croquito_valuation.catalog import normalize_unit
from croquito_valuation.models import PriceCatalog
from croquito_valuation.precedent import (
    PRICE_SOURCE_UNDECLARED,
    NormalizationStrategy,
    PrecedentSeedPacket,
    normalize_label,
)
from croquito_valuation.takeoff import TakeoffItem, TakeoffPacket

PRECEDENT_SEED_WORKSITE_CONFLICT: Final = "PRECEDENT_SEED_WORKSITE_CONFLICT"
PRECEDENT_SEED_STRATEGY_UNSUPPORTED: Final = "PRECEDENT_SEED_STRATEGY_UNSUPPORTED"
PRECEDENT_SEED_NORMALIZATION_MISMATCH: Final = "PRECEDENT_SEED_NORMALIZATION_MISMATCH"

SOURCE_ROUND: Final = "round"
"""Observação nascida do fechamento de pacote de um item, na rodada do próprio sistema."""

SOURCE_SEED: Final = "seed"
"""Observação semeada a partir de um orçamento passado, por `POST /v1/precedents/seed`."""

INDEX_NORMALIZATION_STRATEGY: Final = NormalizationStrategy.FOLDED
"""A estratégia de normalização do índice, e a única cujas linhas a consulta devolve.

`folded` porque foi o que a medição sustentou: `exact` e `folded` deram resultado IDÊNTICO
nos três arquivos reais do Human Gate 1, e não há evidência que justifique normalização mais
agressiva neste corpus (`evidence.md`, unknown 2). A conclusão sustentada é a mais fraca —
normalização leve basta AQUI —, e é por isso que a estratégia é gravada com cada observação:
o dia em que ela mudar, as linhas velhas param de ser devolvidas em vez de se misturarem com
as novas. Reindexar é escrever de novo, não conviver com duas normalizações.
"""


# --- fronteira de tenant ------------------------------------------------------------------


def visible_observations(tenant_id: str) -> ColumnElement[bool]:
    """A fronteira de tenant do índice, escrita UMA vez: só o precedente deste tenant.

    Não há a metade "de plataforma" que `site_setup_kits.visible_kits` tem, e a ausência é a
    decisão: acervo de canteiro é receita distribuível, precedente é o histórico de decisões
    de um escritório. Uma consulta nova que não escreva esta cláusula é defeito de
    isolamento, não detalhe de implementação.
    """
    return PrecedentObservationRecord.tenant_id == tenant_id


def index_key(label: str) -> str:
    """O rótulo como o índice o chaveia — a normalização da T1, sob a estratégia vigente.

    Existe para que ninguém precise saber QUAL estratégia o índice usa para conversar com
    ele: quem tem o rótulo cru (a shortlist da T3, a ingestão) chama isto e recebe a chave.
    """
    return normalize_label(label, INDEX_NORMALIZATION_STRATEGY)


# --- consulta (o que a shortlist vai ler) --------------------------------------------------


@dataclass(frozen=True, slots=True)
class PrecedentCode:
    """Um código que o rótulo já disparou, e em quantas praças distintas."""

    code: str
    worksite_count: int


@dataclass(frozen=True, slots=True)
class PrecedentEntry:
    """O precedente de um rótulo sob UMA fonte de preço.

    `worksite_count` é o número de praças distintas em que o rótulo apareceu — o número que a
    tela escreve por extenso ("você já usou isto em N praças"), que é o controle mínimo do
    risco de propagar erro com autoridade. Ele **não** é a soma dos `worksite_count` dos
    códigos: uma praça que usou três códigos do mesmo rótulo conta uma vez aqui e três vezes
    lá, e é assim que o caso `subset` da medição (pacote menor numa praça) fica legível.

    `codes` vem ordenado do mais repetido para o menos, com o código como desempate — ordem
    determinística, e a mesma para duas leituras do mesmo estado.

    `labels_seen` são os rótulos ORIGINAIS que caíram nesta chave, ordenados. A tela mostra
    como o rótulo foi escrito; a chave continua sendo a forma normalizada.
    """

    normalized_label: str
    price_source: str
    worksite_count: int
    codes: tuple[PrecedentCode, ...]
    labels_seen: tuple[str, ...]


def precedents_for(
    session: Session,
    tenant_id: str,
    labels: Iterable[str],
    price_source: str,
) -> dict[str, PrecedentEntry]:
    """O precedente de cada rótulo, sob `price_source` — a consulta que a T3 consome.

    `labels` são rótulos CRUS (o `TakeoffItem.label` que está na tela); a normalização
    acontece aqui, num lugar só. O resultado é chaveado pelo rótulo NORMALIZADO, que é a
    chave do índice — quem precisa voltar ao rótulo cru usa `index_key` para achar a entrada.

    **Rótulo sem precedente simplesmente não aparece no resultado**: uma entrada vazia faria
    a tela desenhar um bloco de precedente que não tem nada dentro, e o pacote de design
    aprovado é explícito em que o bloco não existe nesse caso.

    **Precedente de outra fonte de preço nunca é devolvido**, nem como resto: `price_source`
    é filtro de igualdade, e a string vazia (`PRICE_SOURCE_UNDECLARED`) é uma fonte PRÓPRIA,
    não um curinga. Sugerir código que não existe na tabela vigente é o pior resultado
    possível (decisão 4 do escopo da feature).

    Só lê: nenhum `add`, nenhum `flush`, nenhuma versão de rodada avançada. Não paga nada.
    """
    keys = {index_key(label) for label in labels if label}
    if not keys:
        return {}

    rows = session.execute(
        select(
            PrecedentObservationRecord.label_normalized,
            PrecedentObservationRecord.label_original,
            PrecedentObservationRecord.code,
            PrecedentObservationRecord.worksite_key,
        ).where(
            visible_observations(tenant_id),
            PrecedentObservationRecord.price_source == price_source,
            PrecedentObservationRecord.normalization_strategy == INDEX_NORMALIZATION_STRATEGY.value,
            PrecedentObservationRecord.label_normalized.in_(sorted(keys)),
        )
    ).all()

    worksites_by_label: dict[str, set[str]] = {}
    worksites_by_code: dict[str, dict[str, set[str]]] = {}
    originals_by_label: dict[str, set[str]] = {}
    for label_normalized, label_original, code, worksite_key in rows:
        worksites_by_label.setdefault(label_normalized, set()).add(worksite_key)
        worksites_by_code.setdefault(label_normalized, {}).setdefault(code, set()).add(worksite_key)
        originals_by_label.setdefault(label_normalized, set()).add(label_original)

    entries: dict[str, PrecedentEntry] = {}
    for label_normalized, worksites in worksites_by_label.items():
        codes = tuple(
            PrecedentCode(code=code, worksite_count=len(code_worksites))
            for code, code_worksites in sorted(
                worksites_by_code[label_normalized].items(),
                key=lambda item: (-len(item[1]), item[0]),
            )
        )
        entries[label_normalized] = PrecedentEntry(
            normalized_label=label_normalized,
            price_source=price_source,
            worksite_count=len(worksites),
            codes=codes,
            labels_seen=tuple(sorted(originals_by_label[label_normalized])),
        )
    return entries


def shortlist_precedents(
    entries: Mapping[str, PrecedentEntry],
    items: Sequence[TakeoffItem],
    catalog: PriceCatalog,
) -> list[dict[str, object]]:
    """O bloco `precedents` da shortlist: o precedente de cada item, resolvido no CATÁLOGO.

    O índice guarda só o código; `description`, `unit`, `unit_price`, `unit_compatible` e
    `catalog_sha256` saem daqui exatamente como um candidato da shortlist os traz, porque a
    tela desenha o mesmo cartão para os dois. `unit_price` viaja como TEXTO, pela mesma
    disciplina de todo dinheiro que atravessa a fronteira: é `Decimal` exato, e um número de
    JSON já teria passado por binário.

    Duas omissões, e as duas são a decisão 7 do pacote de design aprovado — *sugerir código
    que não existe na tabela vigente é o pior resultado possível, pior que não sugerir nada*:

    - **código fora do catálogo é omitido**, e a omissão não derruba o resto do bloco: um
      pacote aprendido numa praça cuja tabela tinha seis serviços continua valendo pelos
      cinco que a tabela desta rodada tem;
    - **item cujos códigos saíram todos não aparece**. Bloco vazio não existe: o pacote é
      explícito em que, sem precedente, o bloco não é desenhado — nem vazio, nem desabilitado.

    `worksite_count` do rótulo é o que a consulta mediu e não é recalculado pela omissão: ele
    responde "em quantas praças este rótulo apareceu", que continua verdadeiro mesmo quando
    um dos códigos daquelas praças não está mais na tabela.

    A ordem é a dos itens do pacote de takeoff, e dentro de cada item a que a consulta deu
    (mais repetido primeiro, código como desempate): duas leituras do mesmo estado devolvem a
    mesma lista, byte a byte.
    """
    payload: list[dict[str, object]] = []
    for item in items:
        entry = entries.get(index_key(item.label))
        if entry is None:
            continue
        codes: list[dict[str, object]] = []
        for precedent_code in entry.codes:
            if not catalog.has_code(precedent_code.code):
                continue
            catalog_entry = catalog.entry_for(precedent_code.code)
            codes.append(
                {
                    "code": catalog_entry.code,
                    "worksite_count": precedent_code.worksite_count,
                    "description": catalog_entry.description,
                    "unit": catalog_entry.unit,
                    "unit_price": str(catalog_entry.unit_price),
                    "unit_compatible": normalize_unit(item.unit)
                    == normalize_unit(catalog_entry.unit),
                    "catalog_sha256": catalog.source_sha256,
                }
            )
        if not codes:
            continue
        payload.append(
            {
                "item_id": item.id,
                "normalized_label": entry.normalized_label,
                "worksite_count": entry.worksite_count,
                "codes": codes,
            }
        )
    return payload


# --- gravação (o que as duas fontes compartilham) ------------------------------------------


def _existing_identities(
    session: Session, *, tenant_id: str, worksite_key: str
) -> set[tuple[str, str, str]]:
    """As tuplas `(rótulo normalizado, fonte, código)` que esta praça já tem neste tenant.

    Ler o conjunto de uma vez, em vez de conferir linha a linha, é o que torna a ingestão de
    um pacote inteiro barata e — mais importante — o que evita depender de uma violação de
    unicidade para descobrir a duplicata: uma `IntegrityError` no meio da transação abortaria
    também o ato que a produziu, que na fonte A é o fechamento do pacote de códigos. A
    constraint continua sendo a rede embaixo desta conferência, para a corrida entre duas
    requisições simultâneas.
    """
    rows = session.execute(
        select(
            PrecedentObservationRecord.label_normalized,
            PrecedentObservationRecord.price_source,
            PrecedentObservationRecord.code,
        ).where(
            visible_observations(tenant_id),
            PrecedentObservationRecord.worksite_key == worksite_key,
        )
    ).all()
    return {(label, price_source, code) for label, price_source, code in rows}


@dataclass(frozen=True, slots=True)
class IngestionCounts:
    """O que uma gravação fez: quantas linhas nasceram, quantas já existiam, quantos rótulos.

    `skipped` é a metade que prova a idempotência: reingerir a mesma praça e refechar o mesmo
    pacote devolvem `ingested = 0`, e a contagem de praças não se move.
    """

    ingested: int
    skipped: int
    labels: int


def _record_observations(
    session: Session,
    *,
    tenant_id: str,
    worksite_key: str,
    observations: Sequence[tuple[str, str, str, str]],
    source: str,
    created_by: str,
) -> IngestionCounts:
    """Grava `(rótulo original, rótulo normalizado, fonte de preço, código)` sem duplicar.

    Duplicata dentro do próprio lote conta como pulada, e não como erro: dois blocos da mesma
    planilha com o mesmo rótulo e o mesmo código são o caso normal do pacote N:N, e recusar o
    pacote inteiro por causa deles seria transformar dado legítimo em falha.
    """
    existing = _existing_identities(session, tenant_id=tenant_id, worksite_key=worksite_key)
    now = datetime.now(UTC)
    ingested = 0
    skipped = 0
    for label_original, label_normalized, price_source, code in observations:
        identity = (label_normalized, price_source, code)
        if identity in existing:
            skipped += 1
            continue
        existing.add(identity)
        session.add(
            PrecedentObservationRecord(
                id=str(new_uuid7()),
                tenant_id=tenant_id,
                worksite_key=worksite_key,
                label_normalized=label_normalized,
                label_original=label_original,
                price_source=price_source,
                code=code,
                source=source,
                normalization_strategy=INDEX_NORMALIZATION_STRATEGY.value,
                created_by=created_by,
                created_at=now,
            )
        )
        ingested += 1
    return IngestionCounts(
        ingested=ingested,
        skipped=skipped,
        labels=len({normalized for _, normalized, _, _ in observations}),
    )


# --- fonte A: a rodada do próprio sistema --------------------------------------------------


def observations_from_closure(
    packet: TakeoffPacket, assignments: CodeAssignmentSet, item_id: str
) -> list[tuple[str, str, str, str]]:
    """O que o fechamento do pacote de UM item contribui para o índice.

    Só código **confirmado** com código não nulo entra: rejeição diz que o código não serve
    para aquele elemento, e propagá-la como precedente ensinaria o índice exatamente o
    contrário do que a orçamentista decidiu.

    A fonte de preço vem de `CodeAssignment.catalog_sha256`, que é o dado que a confirmação
    de fato grava — `PriceOrigin` não aparece na confirmação, só do lado da sugestão. A
    ausência (rodada de catálogo único) vira `PRICE_SOURCE_UNDECLARED`, uma chave própria.

    Um item fora do takeoff, ou sem rótulo, não produz nada: sem rótulo não há chave de
    índice, e inventar uma seria pior que não indexar.
    """
    labels = {item.id: item.label for item in packet.items}
    label = labels.get(item_id)
    if label is None:
        return []
    normalized = index_key(label)
    observations: list[tuple[str, str, str, str]] = []
    for assignment in assignments.assignments:
        if assignment.item_id != item_id or assignment.status != "confirmed":
            continue
        if assignment.code is None:  # pragma: no cover - o modelo já exige código no confirmado
            continue
        price_source = assignment.catalog_sha256 or PRICE_SOURCE_UNDECLARED
        observations.append((label, normalized, price_source, assignment.code))
    return observations


def record_closure_precedents(
    session: Session,
    *,
    tenant_id: str,
    worksite_key: str,
    packet: TakeoffPacket,
    assignments: CodeAssignmentSet,
    item_id: str,
    created_by: str,
) -> IngestionCounts:
    """Grava o precedente do item fechado — **efeito do ato**, na mesma transação.

    O fechamento do pacote é o instante em que a orçamentista diz "acabou" para aquele
    elemento, e é por isso que o precedente nasce aqui e não na confirmação de cada código:
    até o fechamento, o pacote pode ainda ganhar um código, e indexar antes ensinaria um
    pacote incompleto.

    Gravar na mesma transação não é detalhe: se o precedente fosse gravado depois, fora dela,
    um fechamento bem-sucedido poderia não ter precedente nenhum, e o índice divergiria em
    silêncio do que a revisão registra. Refechar não duplica — a identidade já existe.
    """
    return _record_observations(
        session,
        tenant_id=tenant_id,
        worksite_key=worksite_key,
        observations=observations_from_closure(packet, assignments, item_id),
        source=SOURCE_ROUND,
        created_by=created_by,
    )


def revoke_closure_precedent(
    session: Session,
    *,
    tenant_id: str,
    worksite_key: str,
    packet: TakeoffPacket,
    item_id: str,
    code: str,
    price_source: str,
) -> int:
    """Apaga a observação que o fechamento desta praça gravou para um par desfeito (F-045).

    É a compensação do ADR-0061 D4, e roda na MESMA transação da revogação: se ela ficasse
    para depois, o índice continuaria ensinando à praça seguinte um código que esta praça
    desfez — com a autoridade de "você já fez assim", que é o argumento mais forte que a
    shortlist tem.

    Duas restrições, e as duas são deliberadas:

    - **só a observação desta praça**, porque a contagem do índice é por praça e o engano de
      uma não desmente as outras;
    - **só a de origem `round`**. Observação semeada de orçamento passado (fonte B) registra
      o que outra praça fez, num arquivo que já existia antes desta rodada; um ato daqui não
      tem autoridade sobre ela. A consequência declarada: se a mesma praça tivesse as duas
      origens — o que a recusa de colisão da semeadura impede —, a semeada sobreviveria.

    Devolve quantas linhas saíram: `0` é resposta legítima e comum, porque o pacote pode
    nunca ter sido fechado, e nesse caso nada foi indexado.

    Sem rótulo não há chave de índice, e um item fora do takeoff não tem rótulo: o retorno é
    `0`, pelo mesmo motivo que `observations_from_closure` não produz nada nesse caso.
    """
    labels = {item.id: item.label for item in packet.items}
    label = labels.get(item_id)
    if label is None:
        return 0
    normalized = index_key(label)
    rows = session.scalars(
        select(PrecedentObservationRecord).where(
            visible_observations(tenant_id),
            PrecedentObservationRecord.worksite_key == worksite_key,
            PrecedentObservationRecord.label_normalized == normalized,
            PrecedentObservationRecord.price_source == price_source,
            PrecedentObservationRecord.code == code,
            PrecedentObservationRecord.source == SOURCE_ROUND,
        )
    ).all()
    for row in rows:
        session.delete(row)
    return len(rows)


# --- fonte B: semeadura de orçamentos passados ---------------------------------------------


def seed_worksite_conflict(worksite_key: str) -> RoundRefusal:
    """Semear uma praça que já é rodada real deste tenant: recusa, nunca mistura.

    As duas origens sob a mesma chave misturariam o histórico importado de uma planilha com o
    que o sistema gravou dos atos da própria orçamentista — dois dados de qualidade
    diferente, indistinguíveis depois. A recusa é do lado da semeadura, e não do fechamento,
    de propósito: semear é importação deliberada, que pode esperar e ser refeita com outra
    chave; fechar o pacote é o ato central da jornada, e travá-lo por causa da contabilidade
    de um índice seria deixar a ferramenta impedir o trabalho.
    """
    return RoundRefusal(
        409,
        PRECEDENT_SEED_WORKSITE_CONFLICT,
        "esta praça já existe como rodada real; semear sobre ela misturaria as duas origens",
        {"worksite_key": worksite_key},
    )


def seed_strategy_unsupported(declared: str) -> RoundRefusal:
    """Pacote normalizado por outra estratégia: recusa, para não misturar duas chaves.

    Um pacote extraído por versão anterior (ou posterior) da ferramenta traria rótulos
    normalizados por outra regra. Ingeri-los ao lado dos atuais criaria um índice com duas
    chaves para o mesmo rótulo, e a metade errada nunca reencontraria nada — falha silenciosa
    e cara de descobrir, exatamente o que a estratégia gravada existe para evitar.
    """
    return RoundRefusal(
        422,
        PRECEDENT_SEED_STRATEGY_UNSUPPORTED,
        "o pacote foi normalizado por uma estratégia diferente da que o índice usa",
        {"declared": declared, "expected": INDEX_NORMALIZATION_STRATEGY.value},
    )


def seed_normalization_mismatch(positions: Sequence[int]) -> RoundRefusal:
    """Normalização do pacote que não bate com a do servidor: recusa nomeando as posições.

    O servidor recalcula a normalização a partir do rótulo original e compara com a que veio
    escrita. Divergência quer dizer que extrator e servidor discordam sobre a chave, e aceitar
    o pacote gravaria observações que jamais seriam reencontradas.

    A recusa nomeia a **posição** da observação no pacote, nunca o rótulo: quem chamou já tem
    o pacote em mãos e acha a linha pela posição, e o rótulo de legenda não precisa dar mais
    uma volta pela fronteira para dizer o que a posição já diz.
    """
    return RoundRefusal(
        422,
        PRECEDENT_SEED_NORMALIZATION_MISMATCH,
        "a normalização declarada no pacote não corresponde à que o índice calcula",
        {"observations": sorted(positions), "strategy": INDEX_NORMALIZATION_STRATEGY.value},
    )


def ensure_seedable(session: Session, *, tenant_id: str, worksite_key: str) -> None:
    """Recusa a semeadura quando a praça já é rodada real deste tenant.

    A conferência é contra `estimate_rounds`, e não só contra as observações já gravadas: uma
    rodada aberta cujo primeiro pacote ainda não foi fechado não tem nenhuma observação, e
    semear sobre ela produziria a mistura assim que o primeiro fechamento acontecesse. A
    segunda metade (observação de origem `round`) cobre o caso simétrico, se um dia existir
    precedente de rodada cuja linha em `estimate_rounds` não esteja mais lá.
    """
    round_record = session.scalar(
        select(EstimateRoundRecord.id).where(
            EstimateRoundRecord.tenant_id == tenant_id,
            EstimateRoundRecord.worksite_key == worksite_key,
        )
    )
    if round_record is not None:
        raise seed_worksite_conflict(worksite_key)

    from_round = session.scalar(
        select(PrecedentObservationRecord.id).where(
            visible_observations(tenant_id),
            PrecedentObservationRecord.worksite_key == worksite_key,
            PrecedentObservationRecord.source == SOURCE_ROUND,
        )
    )
    if from_round is not None:
        raise seed_worksite_conflict(worksite_key)


def ingest_seed_packet(
    session: Session,
    *,
    tenant_id: str,
    packet: PrecedentSeedPacket,
    created_by: str,
) -> IngestionCounts:
    """Ingere um pacote de semeadura, idempotente por `(tenant_id, worksite_key)`.

    Toda conferência corre **antes** de qualquer gravação — estratégia, colisão de praça e
    normalização —, de modo que um pacote recusado não deixa metade de si no índice.

    Reingerir a mesma praça devolve `ingested = 0` e não move a contagem de praças, que é o
    número que a tela mostra como argumento de autoridade.
    """
    if packet.normalization_strategy is not INDEX_NORMALIZATION_STRATEGY:
        raise seed_strategy_unsupported(packet.normalization_strategy.value)

    mismatched = [
        position
        for position, observation in enumerate(packet.observations)
        if index_key(observation.label_original) != observation.label_normalized
    ]
    if mismatched:
        raise seed_normalization_mismatch(mismatched)

    ensure_seedable(session, tenant_id=tenant_id, worksite_key=packet.worksite_key)

    return _record_observations(
        session,
        tenant_id=tenant_id,
        worksite_key=packet.worksite_key,
        observations=[
            (
                observation.label_original,
                observation.label_normalized,
                observation.price_source,
                observation.code,
            )
            for observation in packet.observations
        ],
        source=SOURCE_SEED,
        created_by=created_by,
    )


def seed_payload(worksite_key: str, counts: IngestionCounts) -> Mapping[str, object]:
    """A resposta da ingestão: contagens, e nenhum rótulo de volta pelo fio."""
    return {
        "worksite_key": worksite_key,
        "observations_ingested": counts.ingested,
        "observations_skipped": counts.skipped,
        "labels": counts.labels,
    }
