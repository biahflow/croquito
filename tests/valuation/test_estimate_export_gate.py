"""O portão de exportação do ORÇAMENTO falha fechado: sem assinatura válida, nada é
despachado.

Ele é irmão do portão da medição (`test_export_gate.py`) e deliberadamente mais curto: não
recebe `ContractWorkbook`, e por isso não tem — nem pode ganhar por cópia — os códigos de
saldo, período e código no contrato. Antes da licitação nenhum desses conceitos existe
(ADR-0027), e é a assinatura sem contrato que mantém essa fronteira de pé (ADR-0046,
decisão 3).
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal, get_args

import pytest
from pydantic import ValidationError

from croquito_valuation.errors import ValuationValidationError, valuation_error_codes
from croquito_valuation.estimate import (
    CatalogSource,
    Estimate,
    EstimateApproval,
    EstimateApproverDecision,
    EstimateLine,
)
from croquito_valuation.models import (
    CalcBlock,
    CalcOperand,
    CalcRecipe,
    CalcSheet,
    PriceOrigin,
    ReviewerDecision,
)
from croquito_valuation.rounding import money_trunc

_WORKSITE_KEY = "praca-sintetica-portao"
_CODE = "AD04050050(/)"
_CATALOG_DIGEST = "c" * 64
_REFERENCE_MONTH = "2026-04"
_SOURCE_LABEL = "SCO SINTETICO (fixture)"
_UNIT_PRICE = Decimal("10.00")
_BDI_PERCENT = Decimal("20.00")


def _calc_sheet(quantity: Decimal) -> CalcSheet:
    return CalcSheet(
        worksite_key=_WORKSITE_KEY,
        item_number="1",
        blocks=[
            CalcBlock(
                label="MEDIDA DIRETA",
                recipe=CalcRecipe.DIRECT_QUANTITY,
                operands=[CalcOperand(name="QUANTIDADE", value=quantity)],
                subtotal=quantity,
            )
        ],
        total_quantity=quantity,
    )


def _estimate(*, quantity: str = "5.00") -> Estimate:
    amount = Decimal(quantity)
    unit_price_with_bdi = money_trunc(_UNIT_PRICE * (1 + _BDI_PERCENT / 100))
    total = money_trunc(amount * unit_price_with_bdi)
    line = EstimateLine(
        item_number="1",
        code=_CODE,
        description="PISO INTERTRAVADO SINTETICO 6CM",
        unit="m2",
        unit_price=_UNIT_PRICE,
        unit_price_with_bdi=unit_price_with_bdi,
        quantity=amount,
        total=total,
        price_origin=PriceOrigin.SCO,
        catalog_sha256=_CATALOG_DIGEST,
        reference_month=_REFERENCE_MONTH,
        source_label=_SOURCE_LABEL,
    )
    return Estimate(
        worksite_key=_WORKSITE_KEY,
        worksite_name="PRACA SINTETICA PORTAO",
        plate_id="praca-sintetica-portao-prancha-01",
        page_number=1,
        image_sha256="a" * 64,
        source_pdf_sha256="b" * 64,
        bdi_percent=_BDI_PERCENT,
        cascade=[
            CatalogSource(
                origin=PriceOrigin.SCO,
                source_sha256=_CATALOG_DIGEST,
                reference_month=_REFERENCE_MONTH,
                source_label=_SOURCE_LABEL,
            )
        ],
        lines=[line],
        calc_sheets=[_calc_sheet(amount)],
        total_amount_without_bdi=money_trunc(amount * _UNIT_PRICE),
        total_amount=total,
        safety_notes=[
            "Orçamento-base sintético de teste: não é medição e não tem contrato.",
            "Cada linha declara a origem do preço; conferir a data-base antes de usar.",
        ],
    )


def _approved(
    estimate: Estimate,
    *,
    action: Literal["confirm", "reject"] = "confirm",
    digest: str | None = None,
) -> Estimate:
    approval = EstimateApproval(
        decision=EstimateApproverDecision(
            decision_id="ed_0123456789abcdef",
            action=action,
            approver_id="aprovador-sintetico",
            approver_role="aprovador",
            decided_at=datetime(2026, 4, 30, 12, 0, tzinfo=UTC),
        ),
        estimate_digest=estimate.content_digest() if digest is None else digest,
    )
    payload = estimate.model_dump()
    payload["approval"] = approval.model_dump()
    return Estimate.model_validate(payload)


def test_an_approved_estimate_has_no_export_errors() -> None:
    estimate = _approved(_estimate())

    assert estimate.export_errors() == []
    estimate.ensure_exportable()


def test_an_estimate_without_approval_is_blocked() -> None:
    assert _estimate().export_errors() == ["ESTIMATE_NOT_APPROVED"]


def test_a_rejected_decision_is_blocked() -> None:
    estimate = _approved(_estimate(), action="reject")

    assert estimate.export_errors() == ["ESTIMATE_APPROVAL_REJECTED"]


def test_an_approval_of_a_previous_content_is_blocked() -> None:
    """Remontar depois de assinado não invalida a assinatura em silêncio: ela fica caduca,
    os dois digests divergem e o despacho recusa até um ato novo (ADR-0046, decisão 8)."""
    signed = _approved(_estimate())
    stale_digest = signed.content_digest()
    edited = _approved(_estimate(quantity="6.00"), digest=stale_digest)

    assert edited.approval is not None
    assert edited.approval.estimate_digest != edited.content_digest()
    assert edited.export_errors() == ["APPROVAL_CONTENT_MISMATCH"]


def test_ensure_exportable_raises_with_the_whole_list() -> None:
    with pytest.raises(ValuationValidationError) as raised:
        _estimate().ensure_exportable()

    assert raised.value.code == "ESTIMATE_EXPORT_BLOCKED"
    assert raised.value.details["errors"] == ["ESTIMATE_NOT_APPROVED"]


def test_content_digest_ignores_the_approval_it_authorizes() -> None:
    """Assinar não muda o que foi assinado: o digest gravado no ato continua conferindo."""
    estimate = _estimate()
    signed = _approved(estimate)

    assert signed.approval is not None
    assert signed.content_digest() == estimate.content_digest()
    assert signed.approval.estimate_digest == signed.content_digest()


def test_the_estimate_gate_does_not_take_a_contract() -> None:
    """A assinatura é o que impede o portão contratual da medição de entrar aqui por cópia.

    Sem `ContractWorkbook` — nem opcional —, os códigos de saldo, período e código no
    contrato não têm por onde chegar a este lado da fronteira (ADR-0027; ADR-0046).
    """
    assert list(inspect.signature(Estimate.export_errors).parameters) == ["self"]
    assert list(inspect.signature(Estimate.ensure_exportable).parameters) == ["self"]


def test_the_new_role_did_not_leak_into_the_valuation_vocabulary() -> None:
    """O tipo é próprio, não reuso (ADR-0046, decisão 4): a medição não conhece `aprovador`
    e o orçamento não conhece `orcamentista`."""
    assert get_args(ReviewerDecision.model_fields["reviewer_role"].annotation) == ("orcamentista",)
    assert get_args(EstimateApproverDecision.model_fields["approver_role"].annotation) == (
        "aprovador",
    )


def test_a_decision_without_timezone_is_refused() -> None:
    with pytest.raises(ValidationError) as raised:
        EstimateApproverDecision(
            decision_id="ed_0123456789abcdef",
            action="confirm",
            approver_id="aprovador-sintetico",
            approver_role="aprovador",
            decided_at=datetime(2026, 4, 30, 12, 0),
        )

    assert valuation_error_codes(raised.value) == ["ESTIMATE_DECISION_TIMESTAMP_NAIVE"]


def test_the_signed_estimate_survives_a_json_round_trip() -> None:
    signed = _approved(_estimate())

    reread = Estimate.model_validate_json(signed.model_dump_json())

    assert reread.approval == signed.approval
    assert reread.content_digest() == signed.content_digest()
    assert reread.export_errors() == []
