"""`confront_scene_quantities` (F-047 T4b): a cena aprovada passa pelo pacote inteiro.

O que estes testes protegem:

- **o desfecho por item é declarado, inclusive o de não ter havido desfecho**: todo item
  volta no relatório, e o motivo de ele ter ficado intacto é nomeado — a ausência nunca
  responde por "a cena não tinha esse número";
- **repetir é seguro**: confrontar de novo o pacote já confrontado não duplica divergência,
  não realimenta o que já veio da cena e não devolve pacote novo;
- **a borda da tolerância não abre**: diferença exatamente igual à tolerância é concordância,
  e o relatório o diz com os dois números na mão;
- **decisão humana é soberana**: divergência já resolvida não é reconfrontada.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from croquito_core.models import Precision
from croquito_valuation.models import ReviewerDecision
from croquito_valuation.quantity_divergence import DivergenceChoice
from croquito_valuation.quantity_source import QuantitySource, QuantityUnresolvedReason
from croquito_valuation.scene_confrontation import (
    SceneConfrontation,
    SceneConfrontationOutcome,
    SceneConfrontationSkipReason,
    confront_scene_quantities,
)
from croquito_valuation.takeoff import (
    TakeoffDivergenceResolutionInput,
    TakeoffItem,
    TakeoffItemStatus,
    TakeoffPacket,
    apply_divergence_resolution,
)

_DIGEST = "a" * 64
_PDF_DIGEST = "b" * 64
_SCENE_REVISION = "0192f1a0-0000-7000-8000-000000000001"


def _item(
    *,
    item_id: str,
    element_ref: str | None = "EL-000100",
    unit: str = "m2",
    quantity: Decimal | None = None,
    status: TakeoffItemStatus = TakeoffItemStatus.AMBIGUOUS,
    decision: ReviewerDecision | None = None,
    source: str = "legend_extraction",
    scene_precision: Precision | None = None,
) -> TakeoffItem:
    return TakeoffItem.model_validate(
        {
            "id": item_id,
            "evidence": {
                "plate_id": "praca-sintetica-norte-prancha-01",
                "page_number": 1,
                "image_sha256": _DIGEST,
                "bbox": {"left": 10, "top": 10, "right": 110, "bottom": 60},
            },
            "raw_text": "PISO EM CONCRETO 418,12 M2",
            "label": "PISO EM CONCRETO",
            "quantity": quantity,
            "unit": unit,
            "source": source,
            "extractor": "legend-extractor-sintetico",
            "extractor_version": "1.0.0",
            "status": status,
            "decision": decision,
            "element_ref": element_ref,
            "scene_precision": scene_precision,
        }
    )


def _packet(items: list[TakeoffItem]) -> TakeoffPacket:
    return TakeoffPacket(
        plate_id="praca-sintetica-norte-prancha-01",
        page_number=1,
        image_sha256=_DIGEST,
        source_pdf_sha256=_PDF_DIGEST,
        items=items,
        safety_notes=[
            "Extração automática da legenda; quantidade não confirmada.",
            "Decisão do orçamentista obrigatória antes de qualquer boletim.",
        ],
    )


def _source(rows: list[dict[str, str]]) -> QuantitySource:
    columns = ["entity_id", "element_ref", "layer", "kind", "precision", "length_m"]
    columns += ["perimeter_m", "area_m2"]
    lines = [",".join(columns)]
    for row in rows:
        lines.append(",".join(row.get(column, "") for column in columns))
    return QuantitySource.from_csv_text("\n".join(lines) + "\n", scene_revision_id=_SCENE_REVISION)


def _row(
    *,
    element_ref: str = "EL-000100",
    precision: str = "exact",
    area_m2: str = "418.120000",
    entity_id: str = "3f0f0f0f-0000-0000-0000-000000000001",
) -> dict[str, str]:
    return {
        "entity_id": entity_id,
        "element_ref": element_ref,
        "layer": "PATAMAR",
        "kind": "polyline",
        "precision": precision,
        "area_m2": area_m2,
    }


def _confirmed(quantity: Decimal) -> ReviewerDecision:
    return ReviewerDecision(
        decision_id="vd_0000000000000001",
        action="confirm",
        reviewer_id="orcamentista-sintetica",
        reviewer_role="orcamentista",
        decided_at=datetime(2026, 8, 29, 12, 0, tzinfo=UTC),
        note=f"conferido em {quantity}",
    )


def _outcomes(
    confrontation: SceneConfrontation,
) -> dict[str, tuple[str, SceneConfrontationSkipReason | QuantityUnresolvedReason | None]]:
    """Relatório por item, no formato mínimo que os testes leem."""
    return {
        outcome.item_id: (outcome.outcome.value, outcome.reason)
        for outcome in confrontation.outcomes
    }


def test_o_confronto_alimenta_divide_e_explica_cada_item_do_pacote() -> None:
    """F-047 T4b, critérios 4 e 5: os três desfechos num pacote só, e todos declarados."""
    sem_numero = _item(item_id="ti_0000000000000001", element_ref="EL-000100")
    com_legenda = _item(
        item_id="ti_0000000000000002",
        element_ref="EL-000200",
        quantity=Decimal("400.00"),
        status=TakeoffItemStatus.PROPOSED,
    )
    sem_identidade = _item(
        item_id="ti_0000000000000003",
        element_ref=None,
        quantity=Decimal("12.00"),
        status=TakeoffItemStatus.PROPOSED,
    )
    aproximada = _item(item_id="ti_0000000000000004", element_ref="EL-000400")
    source = _source(
        [
            _row(element_ref="EL-000100", area_m2="418.120000"),
            _row(
                element_ref="EL-000200",
                area_m2="418.120000",
                entity_id="3f0f0f0f-0000-0000-0000-000000000002",
            ),
            _row(
                element_ref="EL-000400",
                precision="approximate",
                area_m2="90.000000",
                entity_id="3f0f0f0f-0000-0000-0000-000000000004",
            ),
        ]
    )

    confrontation = confront_scene_quantities(
        _packet([sem_numero, com_legenda, sem_identidade, aproximada]), source
    )

    assert confrontation.changed is True
    assert _outcomes(confrontation) == {
        "ti_0000000000000001": ("fed", None),
        "ti_0000000000000002": ("divergence_recorded", None),
        "ti_0000000000000003": ("unchanged", QuantityUnresolvedReason.ITEM_WITHOUT_ELEMENT_REF),
        "ti_0000000000000004": ("unchanged", QuantityUnresolvedReason.PRECISION_NOT_ELIGIBLE),
    }
    alimentado, divergente, intocado, aproximado = confrontation.packet.items
    # Alimentado: a quantidade da cena com a precisão dela, e ainda esperando decisão.
    assert alimentado.quantity == Decimal("418.120000")
    assert alimentado.source == "scene_graph"
    assert alimentado.scene_precision is Precision.EXACT
    assert alimentado.status is TakeoffItemStatus.PROPOSED
    # Divergente: os DOIS números continuam gravados e ninguém escolheu.
    assert divergente.quantity == Decimal("400.00")
    assert divergente.has_open_divergence()
    assert divergente.scene_divergence is not None
    assert divergente.scene_divergence.scene.quantity == Decimal("418.120000")
    assert divergente.scene_divergence.scene.scene_revision_id == _SCENE_REVISION
    # Os dois intactos continuam byte a byte o que eram.
    assert intocado == sem_identidade
    assert aproximado == aproximada
    assert confrontation.count_of(SceneConfrontationOutcome.FED) == 1
    assert confrontation.count_of(SceneConfrontationOutcome.DIVERGENCE_RECORDED) == 1
    assert confrontation.count_of(SceneConfrontationOutcome.UNCHANGED) == 2


def test_repetir_o_confronto_nao_duplica_nem_reescreve_nada() -> None:
    """F-047 T4b, critério 6: o segundo confronto sobre o mesmo estado é um no-op."""
    packet = _packet(
        [
            _item(item_id="ti_0000000000000001", element_ref="EL-000100"),
            _item(
                item_id="ti_0000000000000002",
                element_ref="EL-000200",
                quantity=Decimal("400.00"),
                status=TakeoffItemStatus.PROPOSED,
            ),
        ]
    )
    source = _source(
        [
            _row(element_ref="EL-000100"),
            _row(element_ref="EL-000200", entity_id="3f0f0f0f-0000-0000-0000-000000000002"),
        ]
    )

    primeiro = confront_scene_quantities(packet, source)
    segundo = confront_scene_quantities(primeiro.packet, source)

    assert segundo.changed is False
    # O pacote volta idêntico — e é o MESMO objeto, porque nada foi reconstruído.
    assert segundo.packet is primeiro.packet
    assert _outcomes(segundo) == {
        "ti_0000000000000001": (
            "unchanged",
            SceneConfrontationSkipReason.ALREADY_FED_FROM_SCENE,
        ),
        "ti_0000000000000002": (
            "unchanged",
            SceneConfrontationSkipReason.DIVERGENCE_ALREADY_RECORDED,
        ),
    }
    # E a divergência gravada na primeira passagem continua exatamente uma.
    assert len(primeiro.packet.divergent_items()) == 1


def test_a_divergencia_ja_resolvida_nao_e_reconfrontada() -> None:
    """A decisão humana é soberana: reconfrontar apagaria a escolha registrada."""
    packet = _packet(
        [
            _item(
                item_id="ti_0000000000000002",
                element_ref="EL-000200",
                quantity=Decimal("400.00"),
                status=TakeoffItemStatus.PROPOSED,
            )
        ]
    )
    source = _source([_row(element_ref="EL-000200")])
    aberta = confront_scene_quantities(packet, source).packet
    resolvida = apply_divergence_resolution(
        aberta,
        TakeoffDivergenceResolutionInput(
            item_id="ti_0000000000000002",
            choice=DivergenceChoice.LEGEND,
            reviewer_id="orcamentista-sintetica",
            reviewer_role="orcamentista",
            resolved_at=datetime(2026, 8, 29, 13, 0, tzinfo=UTC),
        ),
    )

    confrontation = confront_scene_quantities(resolvida, source)

    assert confrontation.changed is False
    assert _outcomes(confrontation) == {
        "ti_0000000000000002": (
            "unchanged",
            SceneConfrontationSkipReason.DIVERGENCE_ALREADY_RECORDED,
        )
    }
    item = confrontation.packet.items[0]
    assert item.scene_divergence is not None
    assert item.scene_divergence.resolution is not None
    assert item.quantity == Decimal("400.00")


def test_a_borda_da_tolerancia_nao_abre_divergencia_e_o_relatorio_diz_por_que() -> None:
    """F-047 T4b, critério 4: igual à tolerância ainda é igual — e é dito, não omitido.

    A legenda leu `400,00`; a tolerância é `maior(1% de 400, 0,01)` = `4,00`. A cena diz
    `404,00`: exatamente a tolerância, e por isso concordância. O relatório traz os dois
    números para que a concordância seja verificável, e não uma ausência.
    """
    packet = _packet(
        [
            _item(
                item_id="ti_0000000000000002",
                element_ref="EL-000200",
                quantity=Decimal("400.00"),
                status=TakeoffItemStatus.PROPOSED,
            )
        ]
    )
    source = _source([_row(element_ref="EL-000200", area_m2="404.000000")])

    confrontation = confront_scene_quantities(packet, source)

    assert confrontation.changed is False
    outcome = confrontation.outcomes[0]
    assert outcome.reason is SceneConfrontationSkipReason.WITHIN_TOLERANCE
    assert outcome.scene_quantity == Decimal("404.000000")
    assert outcome.scene_precision is Precision.EXACT
    assert confrontation.packet.items[0].scene_divergence is None


def test_um_centavo_acima_da_tolerancia_abre() -> None:
    """A contraprova da borda: `404,01` contra `400,00` passa da tolerância e abre."""
    packet = _packet(
        [
            _item(
                item_id="ti_0000000000000002",
                element_ref="EL-000200",
                quantity=Decimal("400.00"),
                status=TakeoffItemStatus.PROPOSED,
            )
        ]
    )
    source = _source([_row(element_ref="EL-000200", area_m2="404.010000")])

    confrontation = confront_scene_quantities(packet, source)

    assert confrontation.changed is True
    assert confrontation.outcomes[0].outcome is SceneConfrontationOutcome.DIVERGENCE_RECORDED
    assert confrontation.packet.items[0].has_open_divergence()


def test_item_rejeitado_nao_e_confrontado() -> None:
    """Linha descartada não vira boletim: confrontá-la abriria divergência que nada destrava."""
    rejeitado = _item(
        item_id="ti_0000000000000005",
        element_ref="EL-000100",
        quantity=Decimal("400.00"),
        status=TakeoffItemStatus.REJECTED,
        decision=ReviewerDecision(
            decision_id="vd_0000000000000002",
            action="reject",
            reviewer_id="orcamentista-sintetica",
            reviewer_role="orcamentista",
            decided_at=datetime(2026, 8, 29, 12, 0, tzinfo=UTC),
        ),
    )
    source = _source([_row(element_ref="EL-000100")])

    confrontation = confront_scene_quantities(_packet([rejeitado]), source)

    assert confrontation.changed is False
    assert confrontation.outcomes[0].reason is SceneConfrontationSkipReason.ITEM_REJECTED


def test_item_confirmado_ainda_diverge_porque_a_cena_pode_ser_aprovada_depois() -> None:
    """Confirmar a legenda não fecha a porta: a cena é aprovada quando é aprovada (T5)."""
    confirmado = _item(
        item_id="ti_0000000000000006",
        element_ref="EL-000100",
        quantity=Decimal("400.00"),
        status=TakeoffItemStatus.CONFIRMED,
        decision=_confirmed(Decimal("400.00")),
    )
    source = _source([_row(element_ref="EL-000100")])

    confrontation = confront_scene_quantities(_packet([confirmado]), source)

    assert confrontation.outcomes[0].outcome is SceneConfrontationOutcome.DIVERGENCE_RECORDED
    item = confrontation.packet.items[0]
    assert item.status is TakeoffItemStatus.CONFIRMED
    assert item.has_open_divergence()


def test_a_cena_sem_a_identidade_do_item_devolve_o_motivo_e_nao_o_palpite() -> None:
    """Identidade só na legenda: a ausência de par é estado legível, nunca casamento."""
    source = _source([_row(element_ref="EL-000900")])

    confrontation = confront_scene_quantities(
        _packet([_item(item_id="ti_0000000000000001", element_ref="EL-000100")]), source
    )

    assert confrontation.changed is False
    assert (
        confrontation.outcomes[0].reason is QuantityUnresolvedReason.ELEMENT_REF_ABSENT_FROM_SCENE
    )


def test_unidade_que_a_cena_nao_produz_recusa_pelo_nome() -> None:
    """Item em `un` não recebe área: a cena não produz contagem, e converter seria inventar."""
    source = _source([_row(element_ref="EL-000100")])

    confrontation = confront_scene_quantities(
        _packet([_item(item_id="ti_0000000000000001", element_ref="EL-000100", unit="un")]),
        source,
    )

    assert (
        confrontation.outcomes[0].reason is QuantityUnresolvedReason.UNIT_NOT_DERIVABLE_FROM_SCENE
    )
