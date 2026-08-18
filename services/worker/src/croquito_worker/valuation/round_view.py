"""Payloads de leitura da rodada de medição, derivados só dos modelos do domínio.

Este módulo é a camada de APRESENTAÇÃO da rodada: dado um `TakeoffPacket` (e, quando o
assunto é código, um `CodeAssignmentSet`), ele devolve os dicionários que a tela lê. Nada
aqui abre arquivo, conhece diretório de rodada ou depende de HTTP — é por isso que ele
serve tanto ao servidor de homologação quanto a qualquer outro adaptador que venha a
publicar a mesma rodada (a migração para a API `/v1`, ADR-0028).

Uma regra atravessa tudo o que sai daqui: `quantity` viaja como TEXTO e zero é
informação. Quantidade é `Decimal` exato neste contexto, e um `float` de JSON já teria
perdido a escala escrita na legenda; contagem ausente esconderia do orçamentista que a
etapa não tem nenhum item naquele estado.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any, Final

from croquito_valuation.assignment import CodeAssignmentSet, CodeSuggestionSet
from croquito_valuation.errors import ValuationValidationError
from croquito_valuation.takeoff import TakeoffItem, TakeoffItemStatus, TakeoffPacket

REVIEWER_ROLE: Final = "orcamentista"
"""Único papel deste contexto; ele não vem do corpo da requisição.

Mora no módulo puro, e não no servidor que o carimba hoje, porque três consumidores
precisam da mesma palavra e só um deles é aquele servidor: o modo hospedado a exige como
claim de realm, o servidor local a grava na decisão, e a sessão autenticada da API `/v1`
passa a exigi-la nas rotas de medição (ADR-0028 D8). Ler daqui é o que impede a API de
importar um módulo de rotas FastAPI só para saber o nome de um papel — e é o que faz a
remoção do modo hospedado não mexer em nenhum dos outros dois."""

REVIEWER_ID_MAX_LENGTH: Final = 120
"""Limite do `--reviewer` do modo local; a identidade muda de origem, não de forma."""

ANCHOR_REGISTERED: Final = "registered"
ANCHOR_RAW: Final = "raw"

_REGISTERED_METHODS: Final[frozenset[str]] = frozenset({"rulings", "text_bands"})
"""Métodos de registro que sustentam uma âncora declarada confiável.

`none` fica de fora de propósito: é o desfecho em que nenhuma transformação passou no
gate e o que foi assentado veio do casamento residual travado. Ele é honesto no domínio,
mas não é promessa suficiente para desenhar um retângulo em cima da prancha."""


def parse_quantity(raw_quantity: str | None) -> Decimal | None:
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


def review_status(packet: TakeoffPacket) -> str:
    """Espelho de `cli._review_status`."""
    return "review_required" if packet.pending_items() else "complete"


def takeoff_counts(packet: TakeoffPacket) -> dict[str, int]:
    """Espelho de `cli._takeoff_counts`: sempre as quatro chaves — zero é informação."""
    counts = {status.value: 0 for status in TakeoffItemStatus}
    for item in packet.items:
        counts[item.status.value] += 1
    return {"items": len(packet.items), **counts, "pending": len(packet.pending_items())}


def registered_item_ids(report: Mapping[str, Any] | None) -> frozenset[str]:
    """Itens cujo bbox foi reassentado por um método de registro confiável.

    Leitura fail-closed: relatório ausente, ilegível, sem `method` declarado ou com
    `method` fora do conjunto confiável devolve conjunto **vazio** — todo item volta como
    `raw`. O motivo é o defeito real da homologação: retângulo desenhado sobre a prancha é
    lido pela revisora como "o número foi lido aqui", e âncora deslizada engana com a
    autoridade de um desenho. Na dúvida, a tela precisa poder dizer que não sabe.

    Quem lê o relatório do disco é o adaptador (o servidor de homologação): relatório
    ausente ou ilegível chega aqui como `None`, e o desfecho é o mesmo conjunto vazio.
    """
    if report is None:
        return frozenset()
    if str(report.get("method", "")) not in _REGISTERED_METHODS:
        return frozenset()
    adjusted = report.get("adjusted")
    if not isinstance(adjusted, list):
        return frozenset()
    return frozenset(
        entry["item_id"]
        for entry in adjusted
        if isinstance(entry, dict) and isinstance(entry.get("item_id"), str)
    )


def anchored_packet(packet: TakeoffPacket, registered: frozenset[str]) -> dict[str, object]:
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


def anchor_counts(packet: TakeoffPacket, registered: frozenset[str]) -> dict[str, int]:
    """Quantos itens a tela pode ancorar com garantia e quantos não — zero é informação."""
    matched = sum(1 for item in packet.items if item.id in registered)
    return {"anchors_registered": matched, "anchors_raw": len(packet.items) - matched}


def item_payload(item: TakeoffItem) -> dict[str, object]:
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


def pending_code_items(
    packet: TakeoffPacket, assignments: CodeAssignmentSet | None
) -> list[TakeoffItem]:
    """Itens confirmados no takeoff que ainda não receberam decisão de código."""
    decided = set() if assignments is None else {item.item_id for item in assignments.assignments}
    return [item for item in packet.confirmed_items() if item.id not in decided]


def count_status(assignments: CodeAssignmentSet, status: str) -> int:
    return sum(1 for assignment in assignments.assignments if assignment.status == status)


def matching_of(suggestions: CodeSuggestionSet) -> str:
    """`hybrid` ou `lexical` derivado do próprio conjunto, nunca do estado do processo.

    Derivar do artefato é o que faz a resposta continuar verdadeira quando ela vem do
    arquivo gravado por outra sessão — inclusive uma que tinha teto de gasto e esta não
    tem."""
    return "hybrid" if suggestions.semantic is not None else "lexical"
