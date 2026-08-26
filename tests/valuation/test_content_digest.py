"""O digest de conteúdo é governado pela versão que o artefato declara.

O digest amarra a aprovação nominal ao conteúdo exato aprovado: `export_errors()`
recomputa e devolve `APPROVAL_CONTENT_MISMATCH` quando o conteúdo mudou depois da
assinatura. Isso torna o payload do digest uma superfície de compatibilidade — um campo
novo em qualquer modelo aninhado entraria como `null` e invalidaria artefatos **já
assinados**. Sob o ADR-0048 o orçamento assinado é o consolidado contratual da medição,
então isso não seria um teste vermelho: seria um contrato invalidado.

Estes testes existem para que a mudança de cardinalidade (F-038) não possa fazer isso em
silêncio. Os dois digests-âncora estão fixados como literal de propósito: se um campo novo
vazar para o payload de uma versão antiga, eles reprovam antes de qualquer aprovação real
quebrar.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from croquito_valuation.assignment import CodeAssignment, CodeAssignmentSet
from croquito_valuation.estimate import (
    ESTIMATE_DIGEST_PRUNING,
    ESTIMATE_SCHEMA_VERSION,
    Estimate,
    build_worksite_estimate,
)
from croquito_valuation.models import (
    VALUATION_DIGEST_PRUNING,
    BulletinLine,
    CalcBlock,
    CalcOperand,
    CalcRecipe,
    CalcSheet,
    PriceCatalog,
    PriceCatalogEntry,
    PriceOrigin,
    ReviewerDecision,
    Valuation,
    WorksiteBulletin,
    versioned_content_digest,
)
from croquito_valuation.takeoff import (
    PlateBox,
    PlateEvidence,
    TakeoffItem,
    TakeoffItemStatus,
    TakeoffPacket,
)

# --------------------------------------------------------------------------------------
# o mecanismo
# --------------------------------------------------------------------------------------


def _nested(
    extra: dict[str, object] | None = None, *, operand_extra: dict[str, object] | None = None
) -> dict[str, object]:
    """Payload com a forma que importa: blocos dentro de memórias, ambos em lista."""
    operand: dict[str, object] = {"name": "COMPRIMENTO", "value": "12.50"}
    if operand_extra is not None:
        operand.update(operand_extra)
    block: dict[str, object] = {
        "label": "PASSEIO NORTE",
        "subtotal": "105.00",
        "operands": [dict(operand), dict(operand)],
    }
    if extra is not None:
        block.update(extra)
    return {
        "schema_version": "2.0.0",
        "calc_sheets": [
            {"item_number": "1", "blocks": [dict(block), dict(block)]},
            {"item_number": "2", "blocks": [dict(block)]},
        ],
    }


_PRUNING = {
    "2.0.0": [
        (("calc_sheets", "blocks"), frozenset({"source_item_id", "basis"})),
        (("calc_sheets", "blocks", "operands"), frozenset({"kind"})),
    ]
}


def test_the_declared_version_does_not_see_the_fields_it_never_had() -> None:
    with_new_fields = _nested({"source_item_id": None, "basis": None})

    assert versioned_content_digest(with_new_fields, "2.0.0", _PRUNING) == versioned_content_digest(
        _nested(), "2.0.0", _PRUNING
    )


def test_a_version_prunes_every_level_it_declares() -> None:
    """Uma versão nova toca mais de um nível: campo no bloco e campo no operando dele."""
    with_new_fields = _nested({"source_item_id": None, "basis": None}, operand_extra={"kind": None})

    assert versioned_content_digest(with_new_fields, "2.0.0", _PRUNING) == versioned_content_digest(
        _nested(), "2.0.0", _PRUNING
    )


def test_the_pruning_reaches_every_block_of_every_sheet() -> None:
    """A poda atravessa as duas listas; um bloco esquecido mudaria o digest."""
    partially_pruned = _nested()
    sheets = partially_pruned["calc_sheets"]
    assert isinstance(sheets, list)
    last_sheet = sheets[-1]
    assert isinstance(last_sheet, dict)
    blocks = last_sheet["blocks"]
    assert isinstance(blocks, list)
    blocks[-1]["basis"] = None

    pruned = versioned_content_digest(partially_pruned, "2.0.0", _PRUNING)

    assert pruned == versioned_content_digest(_nested(), "2.0.0", _PRUNING)


def test_the_version_that_knows_the_fields_digests_them() -> None:
    """Poda é por versão declarada: a versão nova digere tudo, inclusive o campo novo."""
    with_new_fields = _nested({"source_item_id": None, "basis": None})
    with_new_fields["schema_version"] = "3.0.0"
    without = _nested()
    without["schema_version"] = "3.0.0"

    assert versioned_content_digest(with_new_fields, "3.0.0", _PRUNING) != versioned_content_digest(
        without, "3.0.0", _PRUNING
    )


def test_a_version_outside_the_map_is_digested_whole() -> None:
    payload = _nested({"source_item_id": None})

    assert versioned_content_digest(payload, "9.9.9", _PRUNING) == versioned_content_digest(
        _nested({"source_item_id": None}), "9.9.9", {}
    )


def test_pruning_an_absent_field_is_not_an_error() -> None:
    """Artefato que nunca teve o campo relê igual; a poda não pode exigir presença."""
    assert versioned_content_digest(_nested(), "2.0.0", _PRUNING) == versioned_content_digest(
        _nested(), "2.0.0", {}
    )


def test_each_artefact_prunes_the_fields_the_matrix_created() -> None:
    """A poda declara exatamente os campos que a cardinalidade N:N acrescentou ao bloco."""
    matrix_fields = frozenset({"source_item_id", "basis", "derived_from_code"})

    assert VALUATION_DIGEST_PRUNING["2.0.0"] == [(("calc_sheets", "blocks"), matrix_fields)]
    assert ESTIMATE_DIGEST_PRUNING["2.2.0"] == [(("calc_sheets", "blocks"), matrix_fields)]


# --------------------------------------------------------------------------------------
# âncoras: o digest de hoje, fixado antes da mudança de cardinalidade
# --------------------------------------------------------------------------------------

_VALUATION_ID = UUID("01920000-0000-7000-8000-000000000001")
_WORKSITE_KEY = "praca-sintetica-norte"

#: Campos que a matriz de contribuições (ADR-0053) acrescentou ao bloco de cálculo.
_MATRIX_FIELDS = ("source_item_id", "basis", "derived_from_code")


def _as_stored_before_the_matrix(payload: dict[str, Any], version: str) -> dict[str, Any]:
    """O artefato como está gravado no banco: sem as chaves que a matriz criou.

    Reler o `model_dump` corrente com a versão trocada não bastaria — ele já traz as chaves
    novas como `null`. O que existe em `valuation_json`/`estimate_json` de toda rodada
    anterior não tem chave nenhuma dessas, e é esse payload que precisa continuar rendendo
    o mesmo digest.
    """
    payload["schema_version"] = version
    for sheet in payload["calc_sheets"]:
        for block in sheet["blocks"]:
            for field in _MATRIX_FIELDS:
                block.pop(field, None)
    return payload


def _valuation() -> Valuation:
    block = CalcBlock(
        label="PASSEIO NORTE",
        recipe=CalcRecipe.LENGTH_TIMES_WIDTH,
        operands=[
            CalcOperand(name="COMPRIMENTO", value=Decimal("12.50"), unit="m"),
            CalcOperand(name="LARGURA", value=Decimal("8.40"), unit="m"),
        ],
        subtotal=Decimal("105.00"),
    )
    line = BulletinLine(
        item_number="1",
        code="AD04050050(/)",
        description="PISO INTERTRAVADO SINTETICO 6CM",
        unit="m2",
        unit_price=Decimal("89.30"),
        quantity=Decimal("105.00"),
        total=Decimal("9376.50"),
    )
    current = Valuation(
        id=_VALUATION_ID,
        period_number=1,
        reference_label="JANEIRO/2026",
        bulletins=[
            WorksiteBulletin(
                worksite_key=_WORKSITE_KEY,
                worksite_name="PRACA SINTETICA NORTE",
                lines=[line],
                total_amount=Decimal("9376.50"),
            )
        ],
        calc_sheets=[
            CalcSheet(
                worksite_key=_WORKSITE_KEY,
                item_number="1",
                blocks=[block],
                total_quantity=Decimal("105.00"),
            )
        ],
    )
    return Valuation.model_validate(
        _as_stored_before_the_matrix(current.model_dump(mode="json"), "2.0.0")
    )


_PLATE_ID = "praca-sintetica-oeste-prancha-01"
_IMAGE_DIGEST = "a" * 64
_PDF_DIGEST = "b" * 64
_SCO_DIGEST = "c" * 64
_SCO_CODE = "AD04050060(/)"
_ITEM_ID = "ti_0000000000000001"
_DECIDED_AT = datetime(2026, 4, 15, 12, 0, tzinfo=UTC)


def _decision(action: Literal["confirm", "reject"] = "confirm") -> ReviewerDecision:
    return ReviewerDecision(
        decision_id=f"vd_{_ITEM_ID[3:]}",
        action=action,
        reviewer_id="orcamentista-sintetico",
        reviewer_role="orcamentista",
        decided_at=_DECIDED_AT,
        note=None,
    )


def _estimate() -> Estimate:
    packet = TakeoffPacket(
        plate_id=_PLATE_ID,
        page_number=1,
        image_sha256=_IMAGE_DIGEST,
        source_pdf_sha256=_PDF_DIGEST,
        items=[
            TakeoffItem(
                id=_ITEM_ID,
                evidence=PlateEvidence(
                    plate_id=_PLATE_ID,
                    page_number=1,
                    image_sha256=_IMAGE_DIGEST,
                    bbox=PlateBox(left=10, top=10, right=110, bottom=60),
                ),
                raw_text="PISO INTERTRAVADO SINTETICO 61.20 m2",
                label="PISO INTERTRAVADO SINTETICO",
                quantity=Decimal("61.20"),
                unit="m2",
                source="legend_extraction",
                extractor="legend-extractor-sintetico",
                extractor_version="1.0.0",
                status=TakeoffItemStatus.CONFIRMED,
                decision=_decision(),
            )
        ],
        safety_notes=[
            "Extração automática da legenda; quantidade não confirmada.",
            "Decisão do orçamentista obrigatória antes de qualquer orçamento.",
        ],
    )
    assignments = CodeAssignmentSet(
        plate_id=_PLATE_ID,
        page_number=1,
        image_sha256=_IMAGE_DIGEST,
        catalog_sha256=_SCO_DIGEST,
        assignments=[
            CodeAssignment(
                item_id=_ITEM_ID,
                status="confirmed",
                code=_SCO_CODE,
                catalog_sha256=_SCO_DIGEST,
                unit_compatible=True,
                decision=_decision(),
            )
        ],
        safety_notes=[
            "Confirmação de código é ato humano rastreável.",
            "A fonte de preço de cada item é a citada na confirmação.",
        ],
    )
    catalog = PriceCatalog(
        source_label="CATALOGO SCO SINTETICO",
        reference_month="2026-01",
        source_sha256=_SCO_DIGEST,
        entries=[
            PriceCatalogEntry(
                code=_SCO_CODE,
                description="PISO INTERTRAVADO SINTETICO 10CM",
                unit="m2",
                unit_price=Decimal("131.20"),
                family_code="XX",
                family_name="FAMILIA SINTETICA",
                subgroup_code="XX01",
                subgroup_name="SUBGRUPO SINTETICO",
                origin=PriceOrigin.SCO,
            )
        ],
        origin=PriceOrigin.SCO,
    )
    current = build_worksite_estimate(
        packet,
        assignments,
        (catalog,),
        worksite_key="praca-sintetica-oeste",
        worksite_name="PRACA SINTETICA OESTE",
        bdi_percent=Decimal("25.00"),
        address="RUA SINTETICA 400",
        calc_plan=None,
    ).estimate
    return Estimate.model_validate(
        _as_stored_before_the_matrix(current.model_dump(mode="json"), "2.2.0")
    )


_VALUATION_DIGEST_BEFORE_F038 = "177a22ac477324cd8d0687293e10439ec42e0f0719b5d458fa27d810337f4346"
_ESTIMATE_DIGEST_BEFORE_F038 = "ba3e7df4f3c18fd9c46c1d8a20d43ce5cec5e87ebb7dce543af43bd20edc3c8e"


def test_the_valuation_digest_is_the_same_it_was_before_the_cardinality_change() -> None:
    assert _valuation().content_digest() == _VALUATION_DIGEST_BEFORE_F038


def test_the_estimate_digest_is_the_same_it_was_before_the_cardinality_change() -> None:
    assert _estimate().content_digest() == _ESTIMATE_DIGEST_BEFORE_F038


def test_the_anchored_artefacts_declare_the_versions_the_anchors_describe() -> None:
    """A âncora só protege enquanto descreve a versão que ela fixou."""
    assert _valuation().schema_version == "2.0.0"
    assert _estimate().schema_version == "2.2.0"


def test_the_artefacts_built_today_declare_the_new_version() -> None:
    """O que nasce agora é da matriz; a âncora descreve o passado, não o presente."""
    from croquito_valuation.models import VALUATION_SCHEMA_VERSION

    assert VALUATION_SCHEMA_VERSION == "3.0.0"
    assert ESTIMATE_SCHEMA_VERSION == "3.0.0"
