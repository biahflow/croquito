"""Extração da legenda quantificada de uma prancha **real**, atrás dos gates de gasto.

É o par pago do `takeoff_fixture`: lá a fixture só lê a prancha que ela mesma desenhou;
aqui um provider lê a prancha do projetista. O que não muda é a natureza do resultado —
observação. Todo item nasce `proposed` ou `ambiguous`, nenhum nasce `confirmed`, e a
decisão do orçamentista continua sendo o que transforma legenda em quantitativo.

A ordem dos atos é deliberada: **gate primeiro, rede depois**. O digest do PNG é ligado ao
documento autorizado por `authorize_page` (a mesma allowlist da extração de geometria)
antes de qualquer byte sair da máquina; imagem que não pertence ao manifest, ou documento
fora da allowlist, recusa sem chamar provider nenhum.

O mapeamento `LegendRowOutput` → `TakeoffItem` (`takeoff_packet_from_legend`) é função
pura e é a peça auditável deste módulo: ela decide, sem provider e sem rede, o que vira
quantidade e o que vira dúvida. Ela nunca inventa: quantidade que não casa com a gramática
pt-BR, unidade que o catálogo não reconhece, rótulo ausente ou linha declarada ilegível
produzem item **ambíguo e sem quantidade** em vez de um número plausível.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Final

from croquito_valuation.catalog import UNIT_ALIASES, normalize_unit, parse_money
from croquito_valuation.errors import ValuationValidationError
from croquito_valuation.takeoff import (
    PlateBox,
    PlateEvidence,
    TakeoffItem,
    TakeoffItemStatus,
    TakeoffPacket,
)
from croquito_worker.extraction_eval import authorize_page, prepare_transmission
from croquito_worker.providers import (
    LegendExtractionOutput,
    LegendRowOutput,
    NormalizedBox,
    PromptTask,
    ProviderAdapter,
    ProviderExecution,
    ProviderExecutionError,
    ProviderFailureCode,
    ProviderRequest,
    build_request,
)
from croquito_worker.valuation.legend_registration import (
    LegendRegistrationReport,
    register_legend_bboxes,
)

LEGEND_SOURCE: Final = "legend_extraction"
UNKNOWN_UNIT: Final = "unknown"
"""Unidade de um item cuja legenda não trouxe unidade nenhuma.

O campo `unit` do domínio é obrigatório (1..20), então a ausência precisa de uma forma
escrita. Ela é declarada em vez de adivinhada — e um item nessa condição nasce
`ambiguous`, porque unidade ausente é justamente o que o orçamentista tem de resolver."""

MAX_LABEL_LENGTH: Final = 200
MAX_EXTRACTOR_LENGTH: Final = 80

LEGEND_EXTRACTION_SAFETY_NOTES: Final[tuple[str, ...]] = (
    "Extração de legenda por provider externo; nenhuma quantidade foi confirmada.",
    "Decisão do orçamentista obrigatória antes de qualquer quantitativo.",
    "Linha ilegível, unidade desconhecida ou quantidade não interpretável nasce ambígua "
    "e sem quantidade.",
)

_KNOWN_UNITS: Final[frozenset[str]] = frozenset(UNIT_ALIASES.values())

_PT_BR_QUANTITY_PATTERN: Final = re.compile(r"^\d{1,3}(?:\.\d{3})+(?:,\d+)?$|^\d+(?:,\d+)?$")
"""Gramática fechada da quantidade escrita em português: `1.234,50`, `61,20`, `4`.

Fora dela nada é convertido. O ponto só é separador de milhar quando agrupa exatamente
três dígitos; `1.5` não casa e vira dúvida em vez de virar 1,5 ou 15 — ler um número de
duas formas possíveis é o erro que este módulo existe para não cometer. A conversão em si
continua sendo a do pacote de medição (`parse_money`), depois de a gramática já ter
decidido o que cada ponto significa.
"""


@dataclass(frozen=True, slots=True)
class LegendExtractionResult:
    """Pacote extraído, lineage da chamada e o documento autorizado que a originou.

    `packet` já é o pacote **registrado** — `registration` é só o relatório de auditoria
    do ajuste (o que mudou, o que ficou intocado); republicar não exige rodar de novo."""

    packet: TakeoffPacket
    execution: ProviderExecution
    source_sha256: str
    registration: LegendRegistrationReport


def parse_legend_quantity(quantity_text: str | None) -> Decimal | None:
    """Converte a quantidade escrita na legenda; devolve `None` quando não dá para ler.

    `None` significa "não sei", nunca zero: quantidade ausente, fora da gramática pt-BR ou
    não positiva não vira número — vira item ambíguo, para o orçamentista informar.
    """
    cleaned = (quantity_text or "").strip()
    if not _PT_BR_QUANTITY_PATTERN.match(cleaned):
        return None
    try:
        value = parse_money(cleaned.replace(".", ""))
    except ValuationValidationError:  # pragma: no cover - a gramática já garante a forma
        return None
    return value if value > 0 else None


def normalized_legend_unit(unit_text: str | None) -> tuple[str, bool]:
    """Unidade do item e se ela foi reconhecida pela tabela do catálogo.

    Unidade reconhecida vira a forma normalizada (`M2` → `m2`). Não reconhecida é
    preservada **literal** — o que estava escrito na prancha continua legível para o
    revisor — e não reconhecida nem escrita vira `unknown`. Nos dois casos o item nasce
    ambíguo: unidade que o catálogo não conhece não sustenta comparação de unidade.
    """
    literal = (unit_text or "").strip()
    if not literal:
        return UNKNOWN_UNIT, False
    normalized = normalize_unit(literal)
    if normalized in _KNOWN_UNITS:
        return normalized, True
    return literal, False


def _clamp(value: int, lowest: int, highest: int) -> int:
    return max(lowest, min(highest, value))


def _plate_box(box: NormalizedBox, *, image_width: int, image_height: int) -> PlateBox:
    """Converte o bbox normalizado do provider para pixels da imagem original.

    O recorte é preso aos limites da imagem porque coordenada normalizada devolvida com
    ruído (1.0000001) não pode apontar para fora do papel. Retângulo que colapsa depois do
    clamp não é corrigido: `PlateBox` recusa, e a recusa é o comportamento certo — âncora
    de evidência sem área não mostra onde o número foi lido.
    """
    return PlateBox(
        left=_clamp(round(box.left * image_width), 0, image_width),
        top=_clamp(round(box.top * image_height), 0, image_height),
        right=_clamp(round(box.right * image_width), 0, image_width),
        bottom=_clamp(round(box.bottom * image_height), 0, image_height),
    )


def legend_item_id(plate_id: str, index: int, raw_text: str) -> str:
    """Id determinístico da linha: prancha, posição e texto lido.

    O índice entra porque prancha real repete rótulo (dois trechos do mesmo piso em linhas
    separadas). Ele desambigua sem inventar identidade: a mesma prancha lida duas vezes
    pelo mesmo modelo produz os mesmos ids.
    """
    digest = hashlib.sha256(f"{plate_id}:{index}:{raw_text}".encode()).hexdigest()[:16]
    return f"ti_{digest}"


def extractor_label(provider: str, model_id: str) -> str:
    """Rótulo do extrator gravado em cada item, no limite de 80 caracteres do domínio.

    É rótulo, não lineage: o lineage completo (modelo devolvido, prompt, tokens, custo)
    vive no `ProviderExecution` que o comando reporta. Model id absurdamente longo é
    cortado aqui em vez de derrubar uma extração já paga.
    """
    return f"{provider}:{model_id}"[:MAX_EXTRACTOR_LENGTH]


def _takeoff_item(
    row: LegendRowOutput,
    index: int,
    *,
    plate_id: str,
    page_number: int,
    image_sha256: str,
    image_width: int,
    image_height: int,
    extractor: str,
    extractor_version: str,
) -> TakeoffItem:
    quantity = parse_legend_quantity(row.quantity_text)
    unit, unit_known = normalized_legend_unit(row.unit_text)
    label = (row.label or "").strip()
    proposed = bool(label) and quantity is not None and unit_known and row.legibility == "clear"
    return TakeoffItem(
        id=legend_item_id(plate_id, index, row.raw_text),
        evidence=PlateEvidence(
            plate_id=plate_id,
            page_number=page_number,
            image_sha256=image_sha256,
            bbox=_plate_box(row.bbox, image_width=image_width, image_height=image_height),
        ),
        raw_text=row.raw_text,
        # Sem rótulo lido, o texto da linha inteira é o que existe de identificação; o item
        # nasce ambíguo justamente por isso.
        label=(label or row.raw_text)[:MAX_LABEL_LENGTH],
        # Item ambíguo não pode carregar quantidade (`TAKEOFF_ITEM_AMBIGUOUS_WITH_QUANTITY`):
        # a leitura só vira número quando tudo na linha foi lido com clareza.
        quantity=quantity if proposed else None,
        unit=unit,
        source=LEGEND_SOURCE,
        extractor=extractor,
        extractor_version=extractor_version,
        status=TakeoffItemStatus.PROPOSED if proposed else TakeoffItemStatus.AMBIGUOUS,
    )


def takeoff_packet_from_legend(
    output: LegendExtractionOutput,
    *,
    plate_id: str,
    page_number: int,
    image_sha256: str,
    source_pdf_sha256: str,
    image_width: int,
    image_height: int,
    extractor: str,
    extractor_version: str,
) -> TakeoffPacket:
    """Traduz a transcrição do provider em pacote de takeoff, sem rede e sem provider.

    Regra única de estado: `PROPOSED` exige rótulo lido, quantidade dentro da gramática
    pt-BR, unidade reconhecida pelo catálogo e legibilidade `clear`. Qualquer dúvida em
    qualquer um dos quatro produz `AMBIGUOUS` **sem quantidade**. `CONFIRMED` não é
    alcançável por este caminho: confirmar é ato do orçamentista.
    """
    if not output.rows:
        raise ValuationValidationError(
            "LEGEND_EXTRACTION_EMPTY",
            "extração não devolveu nenhuma linha de legenda; nada é publicado",
            {"plate_id": plate_id, "page_number": page_number},
        )
    items = [
        _takeoff_item(
            row,
            index,
            plate_id=plate_id,
            page_number=page_number,
            image_sha256=image_sha256,
            image_width=image_width,
            image_height=image_height,
            extractor=extractor,
            extractor_version=extractor_version,
        )
        for index, row in enumerate(output.rows)
    ]
    return TakeoffPacket(
        plate_id=plate_id,
        page_number=page_number,
        image_sha256=image_sha256,
        source_pdf_sha256=source_pdf_sha256,
        items=items,
        safety_notes=list(LEGEND_EXTRACTION_SAFETY_NOTES),
    )


def build_legend_request(source: Path) -> tuple[ProviderRequest, int, int]:
    """Prepara a chamada de extração e devolve também as dimensões **originais** da página.

    O que trafega é a página reduzida ao limite do provider (`prepare_transmission`), mas o
    que mede o bbox de volta são as dimensões originais: a resposta é normalizada, então
    encolher o que sai não desloca o recorte. É a mesma preparação da eval de geometria,
    reusada em vez de recopiada.
    """
    payload, width, height = prepare_transmission(source)
    request = build_request(
        PromptTask.LEGEND_EXTRACTION,
        image_bytes=payload,
        image_sha256=hashlib.sha256(payload).hexdigest(),
        image_width_px=width,
        image_height_px=height,
        region_label="legend",
    )
    return request, width, height


def run_legend_extraction(
    image_path: Path,
    manifest_path: Path,
    adapter: ProviderAdapter,
    *,
    plate_id: str,
    page_number: int,
) -> LegendExtractionResult:
    """Autoriza a página, envia a prancha ao provider e devolve o pacote proposto e registrado.

    O digest gravado no pacote é o do **PNG em disco**, não o da imagem reduzida que
    trafega: a evidência do orçamentista é a página que ele tem, e o mapeamento de bbox
    usa as dimensões originais justamente para que reduzir o que sai não desloque o
    recorte. `source_pdf_sha256` é o documento que a allowlist autorizou, devolvido por
    `authorize_page` — é ele que amarra o pacote ao PDF de origem.

    O último passo é o registro fino (`register_legend_bboxes`): o VLM devolveu, na
    rodada real da Toca, bboxes de linha sistematicamente deslocados da própria tinta.
    O pacote aqui nunca tem item decidido (acabou de nascer), então o registro nunca é
    recusado por decisão; sem faixa de texto nenhuma detectada (caso degenerado), ele
    devolve o pacote como veio, com todo item em `unmatched_item_ids`.
    """
    source = image_path.resolve(strict=True)
    image_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    source_sha256 = authorize_page(manifest_path, image_sha256)

    request, width, height = build_legend_request(source)
    execution = adapter.execute(request)
    output = execution.output
    if not isinstance(output, LegendExtractionOutput):  # pragma: no cover - contrato do adapter
        raise ProviderExecutionError(ProviderFailureCode.INVALID_SCHEMA)

    packet = takeoff_packet_from_legend(
        output,
        plate_id=plate_id,
        page_number=page_number,
        image_sha256=image_sha256,
        source_pdf_sha256=source_sha256,
        image_width=width,
        image_height=height,
        extractor=extractor_label(execution.provider.value, execution.model_id),
        extractor_version=execution.prompt.prompt_version,
    )
    registered_packet, registration = register_legend_bboxes(source, packet)
    return LegendExtractionResult(
        packet=registered_packet,
        execution=execution,
        source_sha256=source_sha256,
        registration=registration,
    )
