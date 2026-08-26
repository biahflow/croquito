"""Dossiê do aditivo: instrumento do pedido de aditivo de contrato (RE-RA).

Em obra LICITADA, item confirmado no takeoff que não tem código no SCO/contrato não pode
ser precificado por fora: o caminho é aditivo de contrato (RE-RA). Este módulo materializa
o dossiê que instrui esse pedido — ele consome o `CodeAssignmentSet` cruzado com
`TakeoffPacket.confirmed_items()` e devolve, para cada rejeição de código, o item e a
justificativa da rejeição (a `decision.note` do orçamentista).

Distinção crucial, herdada da correção de domínio da orçamentista (`docs/product/ROADMAP.md`):
rejeição na revisão do TAKEOFF (item não é medido — ex.: área de intervenção) não é
aditivo. Aditivo é a rejeição na CONFIRMAÇÃO DE CÓDIGO (`CodeAssignment.status ==
"rejected"`) de um item que está CONFIRMADO no takeoff — só esse cruzamento entra aqui.

O dossiê é artefato de FECHAMENTO da rodada, complemento do boletim (`calc.py`): ele
exige que todo item confirmado no takeoff tenha assignment no conjunto, do mesmo jeito que
`build_worksite_bulletin` exige (`CALC_ASSIGNMENT_MISSING`) — nunca é foto parcial da
rodada.

Por construção, nenhum modelo deste módulo tem campo de preço: o dossiê instrui o pedido de
aditivo, nunca precifica, e nunca cria nem altera `Amendment`/RE-RA (`ADR-0018`, leitura
apenas) — o ato de solicitar o aditivo à prefeitura é humano e contratual, fora deste
sistema.
"""

from __future__ import annotations

from typing import Final, Literal

from pydantic import Field, model_validator

from croquito_valuation.assignment import CodeAssignmentSet
from croquito_valuation.errors import ValuationValidationError
from croquito_valuation.models import (
    SHA256_PATTERN,
    ExactDecimal,
    ReviewerDecision,
    ValuationContractModel,
)
from croquito_valuation.takeoff import PlateEvidence, TakeoffPacket

AMENDMENT_DOSSIER_SCHEMA_VERSION: Final = "1.0.0"

_ITEM_ID_PATTERN: Final = r"^ti_[a-f0-9]{16}$"

_AMENDMENT_DOSSIER_SAFETY_NOTES: Final = (
    "O dossiê não precifica nenhum item e não cria nem altera Amendment/RE-RA.",
    "A solicitação do aditivo à prefeitura é ato contratual humano, fora deste sistema.",
)


class AmendmentDossierItem(ValuationContractModel):
    """Um item confirmado no takeoff cujo código foi rejeitado: candidato a aditivo.

    Nenhum campo de preço existe aqui, por construção: o dossiê instrui o pedido de
    aditivo, nunca o precifica. `justification` é a `decision.note` da rejeição de
    código, nunca inventada; `item_note` é a anotação que já acompanhava o item na
    legenda (ex.: `h=1.00m`), distinta da justificativa da rejeição.
    """

    item_id: str = Field(pattern=_ITEM_ID_PATTERN)
    label: str = Field(min_length=1, max_length=200)
    raw_text: str = Field(min_length=1, max_length=300)
    quantity: ExactDecimal = Field(gt=0)
    unit: str = Field(min_length=1, max_length=20)
    item_note: str | None = Field(default=None, max_length=300)
    justification: str = Field(min_length=1, max_length=500)
    decision: ReviewerDecision
    evidence: PlateEvidence

    @model_validator(mode="after")
    def validate_decision_consistency(self) -> AmendmentDossierItem:
        if self.decision.action != "reject" or self.decision.note != self.justification:
            raise ValuationValidationError(
                "AMENDMENT_DOSSIER_ITEM_STATE_INVALID",
                "item de dossiê exige decisão de rejeição com justificativa igual à nota",
                {"item_id": self.item_id},
            )
        return self


class AmendmentDossier(ValuationContractModel):
    """Dossiê do aditivo de uma prancha.

    Lista `items` vazia é desfecho normal: uma rodada sem nenhuma rejeição de código não
    tem aditivo, e isso não é uma condição de erro.
    """

    schema_version: Literal["1.0.0"] = AMENDMENT_DOSSIER_SCHEMA_VERSION
    plate_id: str = Field(min_length=1, max_length=64)
    page_number: int = Field(ge=1)
    image_sha256: str = Field(pattern=SHA256_PATTERN)
    source_pdf_sha256: str = Field(pattern=SHA256_PATTERN)
    catalog_sha256: str = Field(pattern=SHA256_PATTERN)
    contract_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    items: list[AmendmentDossierItem]
    safety_notes: list[str] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_unique_items(self) -> AmendmentDossier:
        item_ids = [item.item_id for item in self.items]
        duplicated = sorted({item_id for item_id in item_ids if item_ids.count(item_id) > 1})
        if duplicated:
            raise ValuationValidationError(
                "AMENDMENT_DOSSIER_DUPLICATE_ITEM",
                "há mais de um item de dossiê para o mesmo item de takeoff",
                {"item_ids": duplicated},
            )
        return self


def build_amendment_dossier(
    packet: TakeoffPacket, assignments: CodeAssignmentSet
) -> AmendmentDossier:
    """Constrói o dossiê do aditivo a partir do takeoff confirmado e das confirmações de código.

    Fail-closed, na ordem: divergência de pacote entre `packet` e `assignments`,
    assignment de item que não está confirmado no takeoff, item confirmado no takeoff sem
    assignment no conjunto (o dossiê é artefato de fechamento, nunca foto parcial) e, só
    então, rejeição de código sem justificativa (`decision.note`) registrada.

    Itens do dossiê saem na ordem dos itens do pacote; o cabeçalho copia os digests do
    pacote (`source_pdf_sha256`) e do conjunto de assignments (`catalog_sha256`,
    `contract_sha256`) — este builder não recebe catálogo nem contrato, então não há
    verificação adicional a fazer contra eles.
    """
    if (
        assignments.plate_id != packet.plate_id
        or assignments.page_number != packet.page_number
        or assignments.image_sha256 != packet.image_sha256
    ):
        raise ValuationValidationError(
            "AMENDMENT_DOSSIER_PACKET_MISMATCH",
            "conjunto de assignments pertence a outra prancha",
            {
                "expected_plate_id": packet.plate_id,
                "expected_page_number": packet.page_number,
                "expected_image_sha256": packet.image_sha256,
                "assignments_plate_id": assignments.plate_id,
                "assignments_page_number": assignments.page_number,
                "assignments_image_sha256": assignments.image_sha256,
            },
        )

    confirmed_items = packet.confirmed_items()
    confirmed_by_id = {item.id: item for item in confirmed_items}
    confirmed_ids = set(confirmed_by_id)
    assignment_ids = {assignment.item_id for assignment in assignments.assignments}

    unknown_ids = sorted(assignment_ids - confirmed_ids)
    if unknown_ids:
        raise ValuationValidationError(
            "AMENDMENT_DOSSIER_UNKNOWN_ITEM",
            "assignment aponta para item desconhecido ou não confirmado no pacote",
            {"item_ids": unknown_ids},
        )

    missing_ids = sorted(confirmed_ids - assignment_ids)
    if missing_ids:
        raise ValuationValidationError(
            "AMENDMENT_DOSSIER_ASSIGNMENTS_INCOMPLETE",
            "item confirmado no takeoff não possui confirmação de código; o dossiê é "
            "artefato de fechamento da rodada e não publica foto parcial",
            {"item_ids": missing_ids},
        )

    # Indexa só as REJEIÇÕES, e não "o assignment do item".
    #
    # Era um dict `{item_id: assignment}` sobre a lista inteira, que sob a cardinalidade N:N
    # ficaria com o último vínculo do item e descartaria os outros em silêncio. Aqui o efeito
    # seria pior do que perder uma linha: um elemento com códigos confirmados poderia ser
    # lido como rejeitado — ou o contrário —, e o dossiê pediria aditivo de serviço que já
    # está precificado.
    #
    # Candidato a aditivo é o item cujo ÚNICO vínculo é uma rejeição, que é o que o código
    # sempre quis dizer. `ASSIGNMENT_REJECT_WITH_CONFIRMED` garante que rejeição e
    # confirmação não coexistam para o mesmo item, então a leitura é sempre unívoca.
    rejections_by_item = {
        assignment.item_id: assignment
        for assignment in assignments.assignments
        if assignment.status == "rejected"
    }

    missing_justification = sorted(
        item.id
        for item in confirmed_items
        if item.id in rejections_by_item and rejections_by_item[item.id].decision.note is None
    )
    if missing_justification:
        raise ValuationValidationError(
            "AMENDMENT_DOSSIER_JUSTIFICATION_MISSING",
            "rejeição de código sem nota do orçamentista não pode virar item de dossiê",
            {"item_ids": missing_justification},
        )

    items: list[AmendmentDossierItem] = []
    for item in confirmed_items:
        assignment = rejections_by_item.get(item.id)
        if assignment is None:
            continue
        assert item.quantity is not None  # garantido por TakeoffItem confirmado
        note = assignment.decision.note
        assert note is not None  # garantido pela checagem acima (JUSTIFICATION_MISSING)
        items.append(
            AmendmentDossierItem(
                item_id=item.id,
                label=item.label,
                raw_text=item.raw_text,
                quantity=item.quantity,
                unit=item.unit,
                item_note=item.note,
                justification=note,
                decision=assignment.decision,
                evidence=item.evidence,
            )
        )

    return AmendmentDossier(
        plate_id=packet.plate_id,
        page_number=packet.page_number,
        image_sha256=packet.image_sha256,
        source_pdf_sha256=packet.source_pdf_sha256,
        catalog_sha256=assignments.catalog_sha256,
        contract_sha256=assignments.contract_sha256,
        items=items,
        safety_notes=list(_AMENDMENT_DOSSIER_SAFETY_NOTES),
    )
