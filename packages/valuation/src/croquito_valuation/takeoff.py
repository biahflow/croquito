"""Contrato de takeoff (quantitativo da legenda) e decisão do orçamentista.

A prancha do projetista chega com a legenda já quantificada (pisos em m², alambrados em
m com altura anotada, mobiliário em unidades, área de intervenção). A extração dessa
legenda produz *observações* — `TakeoffItem`s sempre `proposed` ou `ambiguous` — que só
viram quantitativo com uma decisão humana rastreável (`ReviewerDecision`).

Este módulo é um espelho deliberado de `ReviewPacket`/`DimensionReading`
(`croquito_worker.review`): mesma forma de pacote de revisão, mesmo ciclo
proposed/ambiguous → confirmed/rejected, mesma aplicação imutável de decisões. O
`ADR-0016` proíbe importar do worker; a duplicação de forma é proposital, como já
acontece com `ReviewerDecision` frente a `HumanDecision` — o que se repete é o formato
do ato de revisão, não o significado dele.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Final, Literal

from pydantic import Field, field_validator, model_validator

from croquito_core.models import ELEMENT_REF_PATTERN, Precision
from croquito_valuation.errors import ValuationValidationError
from croquito_valuation.models import (
    SCENE_ELIGIBLE_PRECISIONS,
    SHA256_PATTERN,
    ExactDecimal,
    ReviewerDecision,
    ValuationContractModel,
)
from croquito_valuation.quantity_divergence import (
    DivergenceChoice,
    QuantityDivergence,
    QuantityDivergenceResolution,
)

TAKEOFF_SCHEMA_VERSION: Final = "1.3.0"
"""1.3.0 (F-047 T5b) acrescenta em `scene_divergence`: `relative_tolerance`, `absolute_floor`,
`tolerance_bound` e `legend_ratio` — a mesma conta da tolerância por extenso que a T5 já
fazia, pronta para a tela mostrar sem dividir nada no navegador.

1.2.0 (F-047 T5) acrescenta `scene_divergence`: os dois números do mesmo elemento, as
duas origens e a diferença que furou a tolerância.

1.1.0 (F-047 T4) tinha acrescentado `element_ref`, `scene_precision` e o terceiro valor de
`source`. As subidas são aditivas e o `Literal` continua aceitando as versões anteriores:
um pacote gravado antes lê sem conversão, com os campos novos ausentes."""


class TakeoffItemStatus(StrEnum):
    """Espelho de `ReadingStatus`: estado de revisão de uma linha da legenda.

    `AMBIGUOUS` é a linha cuja extração identificou o elemento mas não conseguiu ler a
    quantidade — por isso ela nunca carrega `quantity`.
    """

    PROPOSED = "proposed"
    AMBIGUOUS = "ambiguous"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class PlateBox(ValuationContractModel):
    """Espelho de `PixelBox`: recorte em pixels da prancha onde o item foi lido."""

    left: int = Field(ge=0)
    top: int = Field(ge=0)
    right: int = Field(gt=0)
    bottom: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_bounds(self) -> PlateBox:
        if self.right <= self.left or self.bottom <= self.top:
            raise ValuationValidationError(
                "TAKEOFF_BBOX_INVALID",
                "bbox do takeoff deve possuir área positiva",
                {
                    "left": self.left,
                    "top": self.top,
                    "right": self.right,
                    "bottom": self.bottom,
                },
            )
        return self


class PlateEvidence(ValuationContractModel):
    """Espelho de `EvidenceRegion`: âncora da prancha para a linha da legenda lida."""

    plate_id: str = Field(min_length=1, max_length=64)
    page_number: int = Field(ge=1)
    image_sha256: str = Field(pattern=SHA256_PATTERN)
    coordinate_space: Literal["source_image_pixels"] = "source_image_pixels"
    bbox: PlateBox


class TakeoffItem(ValuationContractModel):
    """Uma linha da legenda quantificada, do estado observado ao confirmado pelo orçamentista.

    Espelho de `DimensionReading`. `source` era a porta discriminada reservada no roadmap
    (`docs/product/ROADMAP.md`) para quando o quantitativo pudesse nascer do scene graph
    aprovado em vez da extração de legenda; a F-047 T4 a abriu com `scene_graph`.
    """

    id: str = Field(pattern=r"^ti_[a-f0-9]{16}$")
    evidence: PlateEvidence
    raw_text: str = Field(min_length=1, max_length=300)
    label: str = Field(min_length=1, max_length=200)
    quantity: ExactDecimal | None = Field(default=None, gt=0)
    unit: str = Field(min_length=1, max_length=20)
    source: Literal["legend_extraction", "manual", "scene_graph"]
    extractor: str = Field(min_length=1, max_length=80)
    extractor_version: str = Field(min_length=1, max_length=80)
    note: str | None = Field(default=None, max_length=300)
    status: TakeoffItemStatus
    decision: ReviewerDecision | None = None
    # ADR-0058 decisões 1 e 5: a MESMA identidade dos dois lados da fronteira. É o
    # `Entity.element_ref` da cena, com o mesmo padrão importado do núcleo — repetir a
    # regex aqui deixaria as duas metades do elo divergirem em silêncio. Ausente, o item é
    # o de sempre: lido da legenda por decisão humana.
    element_ref: str | None = Field(default=None, pattern=ELEMENT_REF_PATTERN)
    # ADR-0058 decisão 4: a precisão com que a CENA declarou a grandeza, copiada e nunca
    # promovida. Só existe em item alimentado pela cena, e só em `exact`/`derived`.
    scene_precision: Precision | None = None
    # ADR-0058 decisão 6 (F-047 T5): a divergência entre o número da cena e o lido na
    # legenda. Ela mora NO ITEM, e não num registro à parte, porque é o item que viaja até o
    # fechamento do pacote e até o boletim — os dois lugares que precisam recusar enquanto
    # ela estiver aberta. Um registro paralelo se perderia na primeira revisão nova.
    scene_divergence: QuantityDivergence | None = None

    @model_validator(mode="after")
    def validate_scene_origin(self) -> TakeoffItem:
        """Invariantes do item alimentado pela cena aprovada (ADR-0058, decisões 4, 5 e 8).

        Sem `source = scene_graph` o item responde exatamente como antes desta versão: os
        dois campos novos são opcionais e o validador não exige nada deles.
        """
        if self.source == "scene_graph":
            if self.element_ref is None:
                raise ValuationValidationError(
                    "TAKEOFF_ITEM_SCENE_WITHOUT_ELEMENT_REF",
                    "item alimentado pela cena exige a identidade de elemento declarada",
                    {"id": self.id},
                )
            if self.scene_precision is None:
                raise ValuationValidationError(
                    "TAKEOFF_ITEM_SCENE_WITHOUT_PRECISION",
                    "item alimentado pela cena exige a precisão declarada na origem",
                    {"id": self.id},
                )
            if self.scene_precision not in SCENE_ELIGIBLE_PRECISIONS:
                raise ValuationValidationError(
                    "TAKEOFF_ITEM_SCENE_PRECISION_NOT_ELIGIBLE",
                    "só entidade exact ou derived alimenta quantidade da medição",
                    {"id": self.id, "scene_precision": self.scene_precision.value},
                )
        elif self.scene_precision is not None:
            raise ValuationValidationError(
                "TAKEOFF_ITEM_SCENE_PRECISION_WITHOUT_SCENE_SOURCE",
                "precisão de cena só existe em item cuja origem é a cena aprovada",
                {"id": self.id, "source": self.source},
            )
        return self

    @model_validator(mode="after")
    def validate_divergence(self) -> TakeoffItem:
        """A divergência gravada tem de ser a DESTE item, e o item tem de refletir o estado.

        Enquanto ela está aberta, a quantidade do item é a da legenda: a cena não
        sobrescreve nada (ADR-0058 decisão 6). Resolvida, a quantidade do item é a da origem
        ESCOLHIDA — e o número preterido continua gravado dentro da própria divergência,
        recuperável por quem auditar depois.
        """
        divergence = self.scene_divergence
        if divergence is None:
            return self
        if self.element_ref != divergence.scene.element_ref:
            raise ValuationValidationError(
                "TAKEOFF_ITEM_DIVERGENCE_ELEMENT_REF_MISMATCH",
                "a divergência gravada aponta para outro elemento",
                {
                    "id": self.id,
                    "item_element_ref": self.element_ref,
                    "divergence_element_ref": divergence.scene.element_ref,
                },
            )
        expected = divergence.legend.quantity if divergence.is_open else divergence.chosen_quantity
        if self.quantity is None or self.quantity != expected:
            raise ValuationValidationError(
                "TAKEOFF_ITEM_DIVERGENCE_QUANTITY_MISMATCH",
                (
                    "quantidade do item não é a que a divergência declara: aberta, vale a "
                    "lida na legenda; resolvida, vale a origem escolhida"
                ),
                {
                    "id": self.id,
                    "quantity": None if self.quantity is None else str(self.quantity),
                    "expected": None if expected is None else str(expected),
                },
            )
        return self

    def has_open_divergence(self) -> bool:
        """`True` quando há divergência de quantidade ainda sem decisão humana.

        É a pergunta que o fechamento de pacote (`assignment.py`) e o boletim (`calc.py`)
        fazem antes de deixar o item avançar.
        """
        return self.scene_divergence is not None and self.scene_divergence.is_open

    @model_validator(mode="after")
    def validate_review_state(self) -> TakeoffItem:
        if self.status is TakeoffItemStatus.CONFIRMED:
            if self.quantity is None or self.decision is None:
                raise ValuationValidationError(
                    "TAKEOFF_ITEM_CONFIRMED_INCOMPLETE",
                    "item confirmado exige quantidade e decisão do orçamentista",
                    {"id": self.id},
                )
            if self.decision.action != "confirm":
                raise ValuationValidationError(
                    "TAKEOFF_ITEM_CONFIRMED_INCOMPLETE",
                    "decisão de item confirmado deve ser confirm",
                    {"id": self.id},
                )
        elif self.status is TakeoffItemStatus.REJECTED:
            if self.decision is None or self.decision.action != "reject":
                raise ValuationValidationError(
                    "TAKEOFF_ITEM_REJECTED_WITHOUT_DECISION",
                    "item rejeitado exige decisão do orçamentista reject",
                    {"id": self.id},
                )
        elif self.status is TakeoffItemStatus.AMBIGUOUS:
            if self.decision is not None:
                raise ValuationValidationError(
                    "TAKEOFF_ITEM_UNREVIEWED_WITH_DECISION",
                    "item ainda não revisado não pode carregar decisão do orçamentista",
                    {"id": self.id},
                )
            if self.quantity is not None:
                raise ValuationValidationError(
                    "TAKEOFF_ITEM_AMBIGUOUS_WITH_QUANTITY",
                    "item ambíguo é a linha sem quantidade legível; não pode carregar quantidade",
                    {"id": self.id},
                )
        elif self.decision is not None:
            raise ValuationValidationError(
                "TAKEOFF_ITEM_UNREVIEWED_WITH_DECISION",
                "item ainda não revisado não pode carregar decisão do orçamentista",
                {"id": self.id},
            )
        return self


class TakeoffPacket(ValuationContractModel):
    """Pacote de takeoff de uma prancha: espelho de `ReviewPacket`.

    O JSON canônico é a fonte de verdade da extração; `safety_status` fixo lembra que a
    decisão do orçamentista continua obrigatória e nada aqui é quantitativo aprovado.
    """

    schema_version: Literal["1.0.0", "1.1.0", "1.2.0", "1.3.0"] = TAKEOFF_SCHEMA_VERSION
    plate_id: str = Field(min_length=1, max_length=64)
    page_number: int = Field(ge=1)
    image_sha256: str = Field(pattern=SHA256_PATTERN)
    source_pdf_sha256: str = Field(pattern=SHA256_PATTERN)
    items: list[TakeoffItem] = Field(min_length=1)
    safety_status: Literal["human_review_required"] = "human_review_required"
    safety_notes: list[str] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_references(self) -> TakeoffPacket:
        item_ids = [item.id for item in self.items]
        if len(item_ids) != len(set(item_ids)):
            raise ValuationValidationError(
                "TAKEOFF_DUPLICATE_ITEM_ID",
                "IDs de item de takeoff devem ser únicos",
                {"ids": sorted(item_ids)},
            )
        for item in self.items:
            evidence = item.evidence
            if (
                evidence.plate_id != self.plate_id
                or evidence.page_number != self.page_number
                or evidence.image_sha256 != self.image_sha256
            ):
                raise ValuationValidationError(
                    "TAKEOFF_EVIDENCE_MISMATCH",
                    "evidência do item diverge da prancha do pacote",
                    {
                        "id": item.id,
                        "plate_id": evidence.plate_id,
                        "page_number": evidence.page_number,
                        "image_sha256": evidence.image_sha256,
                    },
                )
        return self

    def pending_items(self) -> list[TakeoffItem]:
        """Itens ainda não decididos pelo orçamentista (`proposed` ou `ambiguous`)."""
        return [
            item
            for item in self.items
            if item.status in {TakeoffItemStatus.PROPOSED, TakeoffItemStatus.AMBIGUOUS}
        ]

    def confirmed_items(self) -> list[TakeoffItem]:
        """Itens confirmados pelo orçamentista."""
        return [item for item in self.items if item.status is TakeoffItemStatus.CONFIRMED]

    def divergent_items(self) -> list[TakeoffItem]:
        """Itens com divergência de quantidade gravada, resolvida ou não."""
        return [item for item in self.items if item.scene_divergence is not None]

    def open_divergence_item_ids(self) -> frozenset[str]:
        """Itens cuja divergência ainda espera decisão humana.

        Mesmo molde de `CodeAssignmentSet.open_package_item_ids`: o conjunto é a pergunta que
        as etapas seguintes fazem antes de deixar o item virar linha de boletim."""
        return frozenset(item.id for item in self.items if item.has_open_divergence())


class TakeoffDecisionInput(ValuationContractModel):
    """Decisão do orçamentista sobre um item de takeoff; espelho de `ReadingDecisionInput`.

    `note` é o comentário do revisor sobre a própria decisão; `item_note` corrige a
    anotação que acompanha o item na legenda (ex.: `h=1.00m`). São campos distintos
    porque respondem a perguntas distintas — um documenta o ato de revisão, o outro
    corrige o dado do item.
    """

    item_id: str = Field(pattern=r"^ti_[a-f0-9]{16}$")
    action: Literal["confirm", "reject"]
    reviewer_id: str = Field(min_length=1, max_length=120)
    reviewer_role: Literal["orcamentista"]
    decided_at: datetime
    note: str | None = Field(default=None, max_length=500)
    raw_text: str | None = Field(default=None, min_length=1, max_length=300)
    label: str | None = Field(default=None, min_length=1, max_length=200)
    quantity: ExactDecimal | None = Field(default=None, gt=0)
    unit: str | None = Field(default=None, min_length=1, max_length=20)
    item_note: str | None = Field(default=None, max_length=300)

    @field_validator("decided_at")
    @classmethod
    def validate_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValuationValidationError(
                "TAKEOFF_DECISION_TIMESTAMP_NAIVE",
                "decisão de takeoff exige data e hora com fuso horário",
                {"decided_at": value.isoformat()},
            )
        return value


class TakeoffDecisionBatch(ValuationContractModel):
    """Espelho de `ReadingDecisionBatch`: no máximo uma decisão por item por lote."""

    decisions: list[TakeoffDecisionInput] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_items(self) -> TakeoffDecisionBatch:
        ids = [decision.item_id for decision in self.decisions]
        if len(ids) != len(set(ids)):
            raise ValuationValidationError(
                "TAKEOFF_DECISION_DUPLICATE_ITEM",
                "um item de takeoff só pode receber uma decisão por lote",
                {"ids": sorted(ids)},
            )
        return self


def _decision_id(item: TakeoffItem, decision: TakeoffDecisionInput) -> str:
    """Id determinístico da decisão: espelho de `_decision_id` do worker, prefixo `vd_`."""
    canonical = json.dumps(
        {
            "item_id": item.id,
            "action": decision.action,
            "reviewer_id": decision.reviewer_id,
            "reviewer_role": decision.reviewer_role,
            "decided_at": decision.decided_at.isoformat(),
            "raw_text": decision.raw_text,
            "label": decision.label,
            "quantity": str(decision.quantity) if decision.quantity is not None else None,
            "unit": decision.unit,
            "item_note": decision.item_note,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"vd_{hashlib.sha256(canonical.encode()).hexdigest()[:16]}"


def apply_takeoff_decisions(
    packet: TakeoffPacket,
    batch: TakeoffDecisionBatch,
) -> TakeoffPacket:
    """Cria um novo pacote imutável de takeoff; nunca altera o pacote de entrada.

    Confirmar um item `ambiguous` exige `quantity` no input: sem ela, a reconstrução do
    item cai no validador de estado e sobe `TAKEOFF_ITEM_CONFIRMED_INCOMPLETE` — o erro
    do modelo, não uma pré-checagem duplicada aqui.
    """
    decisions = {decision.item_id: decision for decision in batch.decisions}
    known_ids = {item.id for item in packet.items}
    unknown_ids = sorted(set(decisions) - known_ids)
    if unknown_ids:
        raise ValuationValidationError(
            "TAKEOFF_DECISION_UNKNOWN_ITEM",
            "decisão aponta para item de takeoff desconhecido",
            {"unknown_ids": unknown_ids},
        )

    updated_items: list[TakeoffItem] = []
    for item in packet.items:
        input_decision = decisions.get(item.id)
        if input_decision is None:
            updated_items.append(item)
            continue
        if item.status in {TakeoffItemStatus.CONFIRMED, TakeoffItemStatus.REJECTED}:
            raise ValuationValidationError(
                "TAKEOFF_ITEM_ALREADY_REVIEWED",
                "item de takeoff já revisado não pode ser sobrescrito",
                {"id": item.id},
            )
        reviewer_decision = ReviewerDecision(
            decision_id=_decision_id(item, input_decision),
            action=input_decision.action,
            reviewer_id=input_decision.reviewer_id,
            reviewer_role=input_decision.reviewer_role,
            decided_at=input_decision.decided_at,
            note=input_decision.note,
        )
        update = {
            "raw_text": input_decision.raw_text or item.raw_text,
            "label": input_decision.label or item.label,
            "quantity": (
                input_decision.quantity if input_decision.quantity is not None else item.quantity
            ),
            "unit": input_decision.unit or item.unit,
            "note": input_decision.item_note or item.note,
            "status": (
                TakeoffItemStatus.CONFIRMED
                if input_decision.action == "confirm"
                else TakeoffItemStatus.REJECTED
            ),
            "decision": reviewer_decision,
        }
        updated_items.append(TakeoffItem.model_validate({**item.model_dump(), **update}))

    return TakeoffPacket.model_validate(
        {
            **packet.model_dump(),
            "items": updated_items,
            "safety_notes": [
                *packet.safety_notes,
                (
                    "Decisões do orçamentista aplicadas; propostas originais permanecem "
                    "no histórico de entrada."
                ),
            ],
        }
    )


class TakeoffDivergenceResolutionInput(ValuationContractModel):
    """Pedido de resolução de UMA divergência: o item e qual dos dois números prevalece.

    Não há campo de quantidade, e a ausência é a decisão: a resolução escolhe entre os dois
    números que já existem (ADR-0058, aceite de 2026-08-28). Corrigir a legenda continua
    sendo decisão de takeoff; corrigir a cena continua sendo traçado e nova aprovação.
    """

    item_id: str = Field(pattern=r"^ti_[a-f0-9]{16}$")
    choice: DivergenceChoice
    reviewer_id: str = Field(min_length=1, max_length=120)
    reviewer_role: Literal["orcamentista"]
    resolved_at: datetime
    note: str | None = Field(default=None, min_length=1, max_length=500)

    @field_validator("resolved_at")
    @classmethod
    def validate_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValuationValidationError(
                "TAKEOFF_DIVERGENCE_TIMESTAMP_NAIVE",
                "resolução de divergência exige data e hora com fuso horário",
                {"resolved_at": value.isoformat()},
            )
        return value


def apply_divergence_resolution(
    packet: TakeoffPacket,
    resolution_input: TakeoffDivergenceResolutionInput,
) -> TakeoffPacket:
    """Cria um novo pacote com a divergência daquele item RESOLVIDA; nunca muta o de entrada.

    Escolher a cena troca também a origem do item (`source = scene_graph`, com a precisão
    que a cena declarou), porque a partir daí o número que vale nasceu de lá — e a planilha
    tem de dizer isso. Escolher a legenda não mexe em origem nenhuma: o item continua sendo
    o que sempre foi.

    Nos dois casos o número preterido **continua gravado** dentro de `scene_divergence`, com
    a origem que o produziu. Resolver é declarar qual prevalece, não apagar o outro.

    Item já revisado (`confirmed`) resolve normalmente: a divergência pode nascer depois da
    confirmação — a cena é aprovada quando é aprovada —, e recusar aqui deixaria o item preso
    entre uma decisão que não pode ser refeita e um boletim que não pode ser montado. Quem
    resolve fica registrado com autor e instante, que é o que a auditoria pede.
    """
    target = next((item for item in packet.items if item.id == resolution_input.item_id), None)
    if target is None:
        raise ValuationValidationError(
            "TAKEOFF_DIVERGENCE_UNKNOWN_ITEM",
            "resolução de divergência aponta para item de takeoff desconhecido",
            {"item_id": resolution_input.item_id},
        )
    divergence = target.scene_divergence
    if divergence is None:
        raise ValuationValidationError(
            "TAKEOFF_DIVERGENCE_ABSENT",
            "este item não tem divergência de quantidade para resolver",
            {"item_id": target.id},
        )
    if not divergence.is_open:
        raise ValuationValidationError(
            "TAKEOFF_DIVERGENCE_ALREADY_RESOLVED",
            "a divergência deste item já foi resolvida; re-resolução é recusada",
            {"item_id": target.id},
        )

    resolved = divergence.model_copy(
        update={
            "resolution": QuantityDivergenceResolution(
                choice=resolution_input.choice,
                reviewer_id=resolution_input.reviewer_id,
                reviewer_role=resolution_input.reviewer_role,
                resolved_at=resolution_input.resolved_at,
                note=resolution_input.note,
            )
        }
    )
    update: dict[str, object] = {
        "scene_divergence": resolved.model_dump(),
        "quantity": resolved.chosen_quantity,
    }
    if resolution_input.choice is DivergenceChoice.SCENE:
        update["source"] = "scene_graph"
        update["scene_precision"] = divergence.scene.precision

    updated_items = [
        TakeoffItem.model_validate({**item.model_dump(), **update})
        if item.id == target.id
        else item
        for item in packet.items
    ]
    return TakeoffPacket.model_validate(
        {
            **packet.model_dump(),
            "items": updated_items,
            "safety_notes": [
                *packet.safety_notes,
                (
                    "Divergência de quantidade resolvida pelo orçamentista; o número "
                    "preterido continua gravado na origem que o produziu."
                ),
            ],
        }
    )


def load_takeoff_packet(path: Path) -> TakeoffPacket:
    """Espelho de `load_review_packet`: lê o pacote de takeoff do JSON canônico."""
    return TakeoffPacket.model_validate_json(path.read_text(encoding="utf-8"))
