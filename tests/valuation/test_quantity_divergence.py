"""Divergência entre cena e legenda (F-047 T5): mostra as duas e recusa fechar.

O teste central deste arquivo é o das BORDAS da tolerância. A tolerância é o número que
alguém escolheu — `maior(1% da legenda, 0,01)` —, e o aceite humano de 2026-08-28 fixou
também o lado da comparação: diferença **exatamente igual** à tolerância não abre. Um
`>=` no lugar do `>` passaria em qualquer teste de "muito diferente abre" e erraria
exatamente na borda, que é onde o produto foi decidido.

Os três casos de borda pedidos no contrato da tarefa estão aqui, cada um num teste próprio:
exatamente 1%, exatamente 0,01, e o caso em que o piso é maior que 1% (legenda `0,80` com
cena `0,81`, onde 1% seria `0,008`).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

import pytest
from pydantic import ValidationError

from croquito_core.models import Precision
from croquito_valuation.assignment import (
    CodeAssignmentBatch,
    CodeAssignmentInput,
    CodeAssignmentSet,
    ItemPackageClosureInput,
    apply_code_assignments,
)
from croquito_valuation.calc import build_worksite_bulletin
from croquito_valuation.errors import ValuationValidationError, valuation_error_codes
from croquito_valuation.models import (
    PriceCatalog,
    PriceCatalogEntry,
    ReviewerDecision,
)
from croquito_valuation.quantity_divergence import (
    QUANTITY_DIVERGENCE_ABSOLUTE_FLOOR,
    QUANTITY_DIVERGENCE_RELATIVE_TOLERANCE,
    DivergenceChoice,
    LegendQuantityOrigin,
    QuantityDivergence,
    SceneQuantityOrigin,
    ToleranceBound,
    quantities_diverge,
    quantity_divergence_ratio,
    quantity_divergence_tolerance,
    quantity_divergence_tolerance_breakdown,
)
from croquito_valuation.quantity_source import QuantitySource
from croquito_valuation.takeoff import (
    PlateBox,
    PlateEvidence,
    TakeoffDivergenceResolutionInput,
    TakeoffItem,
    TakeoffItemStatus,
    TakeoffPacket,
    apply_divergence_resolution,
)

_PLATE_ID = "praca-sintetica-norte-prancha-01"
_DIGEST = "a" * 64
_PDF_DIGEST = "b" * 64
_CATALOG_DIGEST = "c" * 64
_ITEM = "ti_0000000000000001"
_ELEMENT = "EL-000100"
_CODE = "CE04100010(/)"
_REVIEWER = "orcamentista-sintetico"
_READ_AT = datetime(2026, 8, 27, 14, 30, tzinfo=UTC)
_RESOLVED_AT = datetime(2026, 8, 28, 9, 15, tzinfo=UTC)
_SCENE_REVISION = "0192f1a0-0000-7000-8000-000000000001"


def _decision(action: Literal["confirm", "reject"] = "confirm") -> ReviewerDecision:
    return ReviewerDecision(
        decision_id="vd_0123456789abcdef",
        action=action,
        reviewer_id=_REVIEWER,
        reviewer_role="orcamentista",
        decided_at=_READ_AT,
    )


def _item(
    *,
    item_id: str = _ITEM,
    element_ref: str | None = _ELEMENT,
    unit: str = "m",
    quantity: Decimal | None = Decimal("100.00"),
    status: TakeoffItemStatus = TakeoffItemStatus.CONFIRMED,
    decided: bool = True,
    label: str = "ALAMBRADO GALVANIZADO",
) -> TakeoffItem:
    return TakeoffItem(
        id=item_id,
        evidence=PlateEvidence(
            plate_id=_PLATE_ID,
            page_number=1,
            image_sha256=_DIGEST,
            bbox=PlateBox(left=10, top=10, right=110, bottom=60),
        ),
        raw_text=f"{label} {quantity} {unit}",
        label=label,
        quantity=quantity,
        unit=unit,
        source="legend_extraction",
        extractor="legend-extractor-sintetico",
        extractor_version="1.0.0",
        status=status,
        decision=_decision() if decided else None,
        element_ref=element_ref,
    )


def _packet(items: list[TakeoffItem] | None = None) -> TakeoffPacket:
    return TakeoffPacket(
        plate_id=_PLATE_ID,
        page_number=1,
        image_sha256=_DIGEST,
        source_pdf_sha256=_PDF_DIGEST,
        items=items if items is not None else [_item()],
        safety_notes=[
            "Extração automática da legenda; quantidade não confirmada.",
            "Decisão do orçamentista obrigatória antes de qualquer boletim.",
        ],
    )


def _source(
    *,
    length_m: str = "101.00",
    precision: str = "exact",
    element_ref: str = _ELEMENT,
    scene_revision_id: str | None = _SCENE_REVISION,
) -> QuantitySource:
    text = (
        "entity_id,element_ref,layer,kind,precision,length_m,perimeter_m,area_m2\n"
        f"3f0f0f0f-0000-0000-0000-000000000001,{element_ref},MURO,line,"
        f"{precision},{length_m},,\n"
    )
    return QuantitySource.from_csv_text(text, scene_revision_id=scene_revision_id)


def _catalog() -> PriceCatalog:
    return PriceCatalog(
        source_label="CATALOGO SINTETICO",
        reference_month="2026-01",
        source_sha256=_CATALOG_DIGEST,
        entries=[
            PriceCatalogEntry(
                code=_CODE,
                description="ALAMBRADO GALVANIZADO",
                unit="m",
                unit_price=Decimal("50.00"),
                family_code="CE",
                family_name="CERCAS SINTETICAS",
                subgroup_code="CE0410",
                subgroup_name="ALAMBRADOS SINTETICOS",
            )
        ],
    )


def _confirmed_assignments(packet: TakeoffPacket) -> CodeAssignmentSet:
    """Confirma o código do item e fecha o pacote — o estado normal antes do boletim."""
    return apply_code_assignments(
        packet,
        CodeAssignmentBatch(
            assignments=[
                CodeAssignmentInput(
                    item_id=_ITEM,
                    action="confirm",
                    code=_CODE,
                    reviewer_id=_REVIEWER,
                    reviewer_role="orcamentista",
                    decided_at=_READ_AT,
                )
            ],
            closures=[
                ItemPackageClosureInput(
                    item_id=_ITEM,
                    reviewer_id=_REVIEWER,
                    reviewer_role="orcamentista",
                    decided_at=_READ_AT,
                )
            ],
        ),
        _catalog(),
    )


# ---------------------------------------------------------------------------
# As bordas da tolerância: o teste central desta tarefa.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("legenda", "esperada"),
    [
        # 1% manda quando é maior que o piso.
        (Decimal("100.00"), Decimal("1.0000")),
        (Decimal("418.12"), Decimal("4.1812")),
        # Empate exato: 1% de 1,00 É 0,01.
        (Decimal("1.00"), Decimal("0.01")),
        # O piso manda quando 1% seria menor que um centavo.
        (Decimal("0.80"), Decimal("0.01")),
        (Decimal("0.10"), Decimal("0.01")),
    ],
)
def test_a_tolerancia_e_o_maior_entre_um_por_cento_e_o_piso(
    legenda: Decimal, esperada: Decimal
) -> None:
    """Critério 1: a tolerância é constante nomeada, e a conta é `maior(1%, 0,01)`."""
    assert Decimal("0.01") == QUANTITY_DIVERGENCE_RELATIVE_TOLERANCE
    assert Decimal("0.01") == QUANTITY_DIVERGENCE_ABSOLUTE_FLOOR
    assert quantity_divergence_tolerance(legenda) == esperada


def test_diferenca_exatamente_igual_a_um_por_cento_nao_abre() -> None:
    """Borda 1 (critério 1 e 2): exatamente 1% ainda é igual. `>`, nunca `>=`."""
    item = _item(quantity=Decimal("100.00"))
    assert _source(length_m="101.00").divergence_for(item) is None
    assert (
        quantities_diverge(scene_quantity=Decimal("101.00"), legend_quantity=Decimal("100.00"))
        is False
    )


def test_um_centavo_acima_de_um_por_cento_abre() -> None:
    """Critério 2: um centavo acima da tolerância abre — o outro lado da mesma borda."""
    item = _item(quantity=Decimal("100.00"))
    divergence = _source(length_m="101.01").divergence_for(item)

    assert divergence is not None
    assert divergence.difference == Decimal("1.01")
    assert divergence.tolerance == Decimal("1.00")
    assert divergence.is_open is True


def test_diferenca_exatamente_igual_ao_piso_nao_abre() -> None:
    """Borda 2 (critério 1): exatamente 0,01, no ponto em que 1% e o piso empatam."""
    item = _item(quantity=Decimal("1.00"))
    assert quantity_divergence_tolerance(Decimal("1.00")) == Decimal("0.01")
    assert _source(length_m="1.01").divergence_for(item) is None
    assert _source(length_m="1.02").divergence_for(item) is not None


def test_o_piso_segura_o_item_miudo_quando_um_por_cento_seria_menor() -> None:
    """Borda 3 (critério 1): legenda `0,80` com cena `0,81`.

    1% de 0,80 é 0,008 — menor que o centavo que a planilha sabe escrever. Sem o piso, um
    alambrado de oitenta centímetros abriria divergência por arredondamento puro.
    """
    item = _item(quantity=Decimal("0.80"))
    assert quantity_divergence_tolerance(Decimal("0.80")) == Decimal("0.01")
    assert _source(length_m="0.81").divergence_for(item) is None
    # E o piso não é uma anistia geral: dois centavos acima ainda abre.
    aberta = _source(length_m="0.82").divergence_for(item)
    assert aberta is not None
    assert aberta.difference == Decimal("0.02")


def test_a_cena_menor_que_a_legenda_abre_do_mesmo_jeito() -> None:
    """A divergência é distância, não sinal: a cena pode ser a menor das duas."""
    item = _item(quantity=Decimal("100.00"))
    divergence = _source(length_m="98.00").divergence_for(item)

    assert divergence is not None
    assert divergence.difference == Decimal("2.00")


# ---------------------------------------------------------------------------
# A issue: os dois números, as duas origens, a diferença.
# ---------------------------------------------------------------------------


def test_a_issue_carrega_os_dois_numeros_as_duas_origens_e_a_diferenca() -> None:
    """Critério 3: nada aqui é resumo — os dois lados viajam inteiros."""
    item = _item(quantity=Decimal("100.00"))
    divergence = _source(length_m="110.00", precision="derived").divergence_for(item)

    assert divergence is not None
    # A cena: quantidade, identidade, precisão declarada e a revisão de onde saiu.
    assert divergence.scene.quantity == Decimal("110.00")
    assert divergence.scene.element_ref == _ELEMENT
    assert divergence.scene.precision is Precision.DERIVED
    assert divergence.scene.scene_revision_id == _SCENE_REVISION
    # A legenda: quantidade, quem leu (extrator e revisor) e quando foi decidida.
    assert divergence.legend.quantity == Decimal("100.00")
    assert divergence.legend.source == "legend_extraction"
    assert divergence.legend.extractor == "legend-extractor-sintetico"
    assert divergence.legend.extractor_version == "1.0.0"
    assert divergence.legend.read_by == _REVIEWER
    assert divergence.legend.read_at == _READ_AT
    # E a diferença, com a tolerância que ela furou.
    assert divergence.difference == Decimal("10.00")
    assert divergence.tolerance == Decimal("1.0000")


def test_item_ainda_sem_decisao_declara_a_leitura_sem_inventar_um_instante_humano() -> None:
    """Sem decisão do orçamentista, `read_by`/`read_at` ficam vazios — e é o correto."""
    item = _item(status=TakeoffItemStatus.PROPOSED, decided=False)
    divergence = _source(length_m="110.00").divergence_for(item)

    assert divergence is not None
    assert divergence.legend.read_by is None
    assert divergence.legend.read_at is None
    assert divergence.legend.extractor == "legend-extractor-sintetico"


def test_a_issue_e_gravada_no_item_sem_mexer_na_quantidade_da_legenda() -> None:
    """Decisão 6: nenhuma origem apaga a outra. A cena não sobrescreve a legenda."""
    item = _item(quantity=Decimal("100.00"))
    gravado = _source(length_m="110.00").record_divergence(item)

    assert gravado is not item
    assert item.scene_divergence is None  # o item de entrada não foi mutado
    assert gravado.quantity == Decimal("100.00")
    assert gravado.source == "legend_extraction"
    assert gravado.scene_divergence is not None
    assert gravado.scene_divergence.scene.quantity == Decimal("110.00")


def test_regravar_a_divergencia_e_recusado() -> None:
    item = _source(length_m="110.00").record_divergence(_item())
    with pytest.raises(ValuationValidationError) as raised:
        _source(length_m="120.00").record_divergence(item)

    assert raised.value.code == "QUANTITY_DIVERGENCE_ALREADY_RECORDED"


# ---------------------------------------------------------------------------
# Critério 6: cena `approximate` não gera divergência.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("precision", ["approximate", "unresolved"])
def test_cena_inelegivel_nao_gera_divergencia(precision: str) -> None:
    """Critério 6: o que não alimenta também não compara.

    Uma cena `approximate` que diverge 10% da legenda não abre issue nenhuma, porque a issue
    não teria decisão possível: escolher "a cena" promoveria a precisão que o pipeline
    proíbe do croqui até o DXF, e escolher "a legenda" seria o estado que já existe.
    """
    item = _item(quantity=Decimal("100.00"))
    source = _source(length_m="110.00", precision=precision)

    assert source.resolve(item).resolved is False
    assert source.divergence_for(item) is None
    assert source.record_divergence(item) is item


def test_o_modelo_da_issue_recusa_precisao_inelegivel_no_proprio_contrato() -> None:
    """Defesa em profundidade: nem construída à mão a issue aceita `approximate`."""
    with pytest.raises(ValidationError) as raised:
        SceneQuantityOrigin(
            quantity=Decimal("110.00"),
            element_ref=_ELEMENT,
            precision=Precision.APPROXIMATE,
        )

    assert valuation_error_codes(raised.value) == ["QUANTITY_DIVERGENCE_PRECISION_NOT_ELIGIBLE"]


# ---------------------------------------------------------------------------
# Critério 7: sem quantidade da cena, nada muda.
# ---------------------------------------------------------------------------


def test_sem_quantidade_da_cena_o_item_da_legenda_segue_como_hoje() -> None:
    """Critério 7 (não-regressão): o item de legenda puro atravessa a cadeia inteira."""
    item = _item(quantity=Decimal("100.00"))
    # A cena existe, mas não conhece este elemento.
    source = _source(length_m="110.00", element_ref="EL-000999")

    assert source.divergence_for(item) is None
    assert source.record_divergence(item) is item

    packet = _packet([item])
    assignments = _confirmed_assignments(packet)
    resultado = build_worksite_bulletin(
        packet,
        assignments,
        _catalog(),
        worksite_key="praca-sintetica",
        worksite_name="PRACA SINTETICA",
    )

    assert [linha.quantity for linha in resultado.bulletin.lines] == [Decimal("100.00")]


def test_item_sem_identidade_de_elemento_nunca_diverge() -> None:
    """Sem `element_ref` na legenda não há elo, e sem elo não há o que comparar."""
    item = _item(element_ref=None, quantity=Decimal("100.00"))
    assert _source(length_m="110.00").divergence_for(item) is None


def test_item_ja_alimentado_pela_cena_nao_diverge_de_si_mesmo() -> None:
    """Item cuja quantidade NASCEU da cena não tem leitura de legenda com que divergir."""
    item = TakeoffItem.model_validate(
        {
            **_item(quantity=Decimal("110.00")).model_dump(),
            "source": "scene_graph",
            "scene_precision": Precision.EXACT,
        }
    )
    assert _source(length_m="110.00").divergence_for(item) is None


# ---------------------------------------------------------------------------
# Critério 4: o item não fecha com a divergência aberta.
# ---------------------------------------------------------------------------


def test_item_com_divergencia_aberta_nao_fecha_o_pacote() -> None:
    """Critério 4: o fechamento de pacote da F-038 recusa com código nomeado."""
    item = _source(length_m="110.00").record_divergence(_item())
    packet = _packet([item])

    with pytest.raises(ValuationValidationError) as raised:
        apply_code_assignments(
            packet,
            CodeAssignmentBatch(
                assignments=[
                    CodeAssignmentInput(
                        item_id=_ITEM,
                        action="confirm",
                        code=_CODE,
                        reviewer_id=_REVIEWER,
                        reviewer_role="orcamentista",
                        decided_at=_READ_AT,
                    )
                ],
                closures=[
                    ItemPackageClosureInput(
                        item_id=_ITEM,
                        reviewer_id=_REVIEWER,
                        reviewer_role="orcamentista",
                        decided_at=_READ_AT,
                    )
                ],
            ),
            _catalog(),
        )

    assert raised.value.code == "ASSIGNMENT_QUANTITY_DIVERGENCE_OPEN"
    assert raised.value.details == {"item_ids": [_ITEM]}


def test_confirmar_codigo_continua_permitido_com_a_divergencia_aberta() -> None:
    """A recusa é do FECHAMENTO, não da etapa inteira.

    Saber qual serviço precifica o elemento não depende de quanto ele mede, e travar a
    confirmação de código pararia trabalho que a divergência não invalida.
    """
    item = _source(length_m="110.00").record_divergence(_item())
    assignments = apply_code_assignments(
        _packet([item]),
        CodeAssignmentBatch(
            assignments=[
                CodeAssignmentInput(
                    item_id=_ITEM,
                    action="confirm",
                    code=_CODE,
                    reviewer_id=_REVIEWER,
                    reviewer_role="orcamentista",
                    decided_at=_READ_AT,
                )
            ]
        ),
        _catalog(),
    )

    assert assignments.confirmed_codes_by_item() == {_ITEM: (_CODE,)}
    assert assignments.open_package_item_ids() == frozenset({_ITEM})


def test_o_boletim_recusa_a_divergencia_que_nasceu_depois_do_fechamento() -> None:
    """Critério 4, a metade que o fechamento sozinho não cobre.

    A cena é aprovada quando é aprovada: o pacote pode já estar fechado quando o segundo
    número aparece. Por isso o boletim tem portão próprio, e não confia no da etapa anterior.
    """
    limpo = _packet([_item()])
    assignments = _confirmed_assignments(limpo)  # fechado ANTES da divergência existir

    divergente = _packet([_source(length_m="110.00").record_divergence(_item())])
    with pytest.raises(ValuationValidationError) as raised:
        build_worksite_bulletin(
            divergente,
            assignments,
            _catalog(),
            worksite_key="praca-sintetica",
            worksite_name="PRACA SINTETICA",
        )

    assert raised.value.code == "CALC_QUANTITY_DIVERGENCE_OPEN"
    assert raised.value.details == {"item_ids": [_ITEM]}


def test_resolvida_a_divergencia_o_pacote_fecha_e_o_boletim_sai() -> None:
    """O portão é a divergência ABERTA, e ele abre quando o humano decide."""
    packet = _packet([_source(length_m="110.00").record_divergence(_item())])
    resolvido = apply_divergence_resolution(
        packet,
        TakeoffDivergenceResolutionInput(
            item_id=_ITEM,
            choice=DivergenceChoice.SCENE,
            reviewer_id=_REVIEWER,
            reviewer_role="orcamentista",
            resolved_at=_RESOLVED_AT,
        ),
    )

    assignments = _confirmed_assignments(resolvido)
    resultado = build_worksite_bulletin(
        resolvido,
        assignments,
        _catalog(),
        worksite_key="praca-sintetica",
        worksite_name="PRACA SINTETICA",
    )

    assert [linha.quantity for linha in resultado.bulletin.lines] == [Decimal("110.00")]
    assert resolvido.open_divergence_item_ids() == frozenset()


# ---------------------------------------------------------------------------
# Critério 5: resolver é decisão humana registrada; o preterido continua gravado.
# ---------------------------------------------------------------------------


def test_escolher_a_cena_registra_autor_e_instante_e_guarda_o_numero_preterido() -> None:
    """Critério 5, escolhendo a cena."""
    packet = _packet([_source(length_m="110.00").record_divergence(_item())])
    resolvido = apply_divergence_resolution(
        packet,
        TakeoffDivergenceResolutionInput(
            item_id=_ITEM,
            choice=DivergenceChoice.SCENE,
            reviewer_id=_REVIEWER,
            reviewer_role="orcamentista",
            resolved_at=_RESOLVED_AT,
            note="Conferido em campo: a legenda estava desatualizada.",
        ),
    )

    item = resolvido.items[0]
    divergence = item.scene_divergence
    assert divergence is not None
    assert divergence.resolution is not None
    assert divergence.resolution.reviewer_id == _REVIEWER
    assert divergence.resolution.resolved_at == _RESOLVED_AT
    assert divergence.resolution.choice is DivergenceChoice.SCENE
    # O escolhido vale; o preterido continua gravado e recuperável.
    assert item.quantity == Decimal("110.00")
    assert divergence.chosen_quantity == Decimal("110.00")
    assert divergence.superseded_quantity == Decimal("100.00")
    assert divergence.legend.quantity == Decimal("100.00")
    # E a origem do item passa a declarar de onde o número veio.
    assert item.source == "scene_graph"
    assert item.scene_precision is Precision.EXACT
    # O pacote de entrada não foi tocado.
    assert packet.items[0].quantity == Decimal("100.00")


def test_escolher_a_legenda_mantem_a_origem_e_guarda_o_numero_da_cena() -> None:
    """Critério 5, escolhendo a legenda: o item continua sendo o que sempre foi."""
    packet = _packet([_source(length_m="110.00").record_divergence(_item())])
    resolvido = apply_divergence_resolution(
        packet,
        TakeoffDivergenceResolutionInput(
            item_id=_ITEM,
            choice=DivergenceChoice.LEGEND,
            reviewer_id=_REVIEWER,
            reviewer_role="orcamentista",
            resolved_at=_RESOLVED_AT,
        ),
    )

    item = resolvido.items[0]
    divergence = item.scene_divergence
    assert divergence is not None
    assert item.quantity == Decimal("100.00")
    assert item.source == "legend_extraction"
    assert item.scene_precision is None
    assert divergence.superseded_quantity == Decimal("110.00")
    assert divergence.scene.quantity == Decimal("110.00")


def test_nao_existe_uma_terceira_quantidade_a_escolher() -> None:
    """Decisão 7: "nenhuma das duas" não é oferecida, e o contrato tem só dois valores."""
    assert [choice.value for choice in DivergenceChoice] == ["scene", "legend"]
    with pytest.raises(ValidationError):
        TakeoffDivergenceResolutionInput(
            item_id=_ITEM,
            choice="outra",
            reviewer_id=_REVIEWER,
            reviewer_role="orcamentista",
            resolved_at=_RESOLVED_AT,
        )


def test_re_resolver_a_mesma_divergencia_e_recusado() -> None:
    packet = _packet([_source(length_m="110.00").record_divergence(_item())])
    resolucao = TakeoffDivergenceResolutionInput(
        item_id=_ITEM,
        choice=DivergenceChoice.LEGEND,
        reviewer_id=_REVIEWER,
        reviewer_role="orcamentista",
        resolved_at=_RESOLVED_AT,
    )
    resolvido = apply_divergence_resolution(packet, resolucao)

    with pytest.raises(ValuationValidationError) as raised:
        apply_divergence_resolution(resolvido, resolucao)

    assert raised.value.code == "TAKEOFF_DIVERGENCE_ALREADY_RESOLVED"


def test_resolver_item_sem_divergencia_e_item_desconhecido_sao_recusas_distintas() -> None:
    packet = _packet([_item()])

    with pytest.raises(ValuationValidationError) as sem_divergencia:
        apply_divergence_resolution(
            packet,
            TakeoffDivergenceResolutionInput(
                item_id=_ITEM,
                choice=DivergenceChoice.SCENE,
                reviewer_id=_REVIEWER,
                reviewer_role="orcamentista",
                resolved_at=_RESOLVED_AT,
            ),
        )
    with pytest.raises(ValuationValidationError) as desconhecido:
        apply_divergence_resolution(
            packet,
            TakeoffDivergenceResolutionInput(
                item_id="ti_ffffffffffffffff",
                choice=DivergenceChoice.SCENE,
                reviewer_id=_REVIEWER,
                reviewer_role="orcamentista",
                resolved_at=_RESOLVED_AT,
            ),
        )

    assert sem_divergencia.value.code == "TAKEOFF_DIVERGENCE_ABSENT"
    assert desconhecido.value.code == "TAKEOFF_DIVERGENCE_UNKNOWN_ITEM"


def test_a_resolucao_exige_instante_com_fuso() -> None:
    with pytest.raises(ValidationError) as raised:
        TakeoffDivergenceResolutionInput(
            item_id=_ITEM,
            choice=DivergenceChoice.SCENE,
            reviewer_id=_REVIEWER,
            reviewer_role="orcamentista",
            resolved_at=datetime(2026, 8, 28, 9, 15),
        )

    assert valuation_error_codes(raised.value) == ["TAKEOFF_DIVERGENCE_TIMESTAMP_NAIVE"]


# ---------------------------------------------------------------------------
# Invariantes do modelo: a issue é a conta, não um rótulo colado por fora.
# ---------------------------------------------------------------------------


def _origins() -> tuple[SceneQuantityOrigin, LegendQuantityOrigin]:
    return (
        SceneQuantityOrigin(
            quantity=Decimal("101.00"),
            element_ref=_ELEMENT,
            precision=Precision.EXACT,
        ),
        LegendQuantityOrigin(
            quantity=Decimal("100.00"),
            source="legend_extraction",
            extractor="legend-extractor-sintetico",
            extractor_version="1.0.0",
        ),
    )


def test_a_issue_nao_existe_dentro_da_tolerancia_nem_construida_a_mao() -> None:
    """A borda vale também para quem monta a issue sem passar pelo detector."""
    scene, legend = _origins()
    with pytest.raises(ValidationError) as raised:
        QuantityDivergence(
            scene=scene,
            legend=legend,
            difference=Decimal("1.00"),
            tolerance=Decimal("1.0000"),
        )

    assert valuation_error_codes(raised.value) == ["QUANTITY_DIVERGENCE_WITHIN_TOLERANCE"]


def test_diferenca_ou_tolerancia_declaradas_fora_da_conta_sao_recusadas() -> None:
    scene, legend = _origins()
    with pytest.raises(ValidationError) as diferenca:
        QuantityDivergence(
            scene=scene,
            legend=legend,
            difference=Decimal("5.00"),
            tolerance=Decimal("1.0000"),
        )
    with pytest.raises(ValidationError) as tolerancia:
        QuantityDivergence(
            scene=scene,
            legend=legend,
            difference=Decimal("1.00"),
            tolerance=Decimal("0.50"),
        )

    assert valuation_error_codes(diferenca.value) == ["QUANTITY_DIVERGENCE_DIFFERENCE_MISMATCH"]
    assert valuation_error_codes(tolerancia.value) == ["QUANTITY_DIVERGENCE_TOLERANCE_MISMATCH"]


def test_o_item_nao_pode_mentir_sobre_a_quantidade_que_a_divergencia_declara() -> None:
    """Aberta, vale a legenda; nenhuma quantidade fora disso é estado alcançável."""
    item = _source(length_m="110.00").record_divergence(_item())
    with pytest.raises(ValidationError) as raised:
        TakeoffItem.model_validate({**item.model_dump(), "quantity": Decimal("105.00")})

    assert valuation_error_codes(raised.value) == ["TAKEOFF_ITEM_DIVERGENCE_QUANTITY_MISMATCH"]


def test_a_divergencia_gravada_precisa_ser_a_do_elemento_do_item() -> None:
    item = _source(length_m="110.00").record_divergence(_item())
    with pytest.raises(ValidationError) as raised:
        TakeoffItem.model_validate({**item.model_dump(), "element_ref": "EL-000999"})

    assert valuation_error_codes(raised.value) == ["TAKEOFF_ITEM_DIVERGENCE_ELEMENT_REF_MISMATCH"]


# ---------------------------------------------------------------------------
# F-047 T5b: a conta da tolerância chega pronta — parcela, piso, vencedora e razão.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("legenda", "esperada_relativa", "esperado_piso", "esperada_vencedora"),
    [
        # 1% manda quando é maior que o piso.
        (Decimal("100.00"), Decimal("1.0000"), Decimal("0.01"), ToleranceBound.RELATIVE),
        # Empate exato: 1% de 1,00 É 0,01 — a relativa vence o empate.
        (Decimal("1.00"), Decimal("0.01"), Decimal("0.01"), ToleranceBound.RELATIVE),
        # O piso manda quando 1% seria menor que um centavo.
        (Decimal("0.80"), Decimal("0.0080"), Decimal("0.01"), ToleranceBound.ABSOLUTE_FLOOR),
    ],
)
def test_o_breakdown_expoe_as_duas_parcelas_e_quem_governou(
    legenda: Decimal,
    esperada_relativa: Decimal,
    esperado_piso: Decimal,
    esperada_vencedora: ToleranceBound,
) -> None:
    """Critérios 1 e 2 da T5b: a parcela de 1%, o piso e quem venceu, sem a tela comparar."""
    breakdown = quantity_divergence_tolerance_breakdown(legenda)
    assert breakdown.relative_tolerance == esperada_relativa
    assert breakdown.absolute_floor == esperado_piso
    assert breakdown.tolerance_bound is esperada_vencedora
    assert breakdown.tolerance == max(esperada_relativa, esperado_piso)
    # A função antiga continua sendo a mesma conta — nunca uma segunda derivação.
    assert quantity_divergence_tolerance(legenda) == breakdown.tolerance


def test_a_razao_e_indefinida_quando_a_legenda_e_zero() -> None:
    """Critério 4: a razão não existe quando a legenda é zero — sem dividir por zero.

    `LegendQuantityOrigin.quantity` já exige `gt=0`, então o modelo nunca chega a este
    caso; a função pura precisa se defender por conta própria, não pela constraint de
    outro model.
    """
    assert (
        quantity_divergence_ratio(difference=Decimal("1.00"), legend_quantity=Decimal("0")) is None
    )


def test_a_razao_bate_com_o_estado_06_do_pacote_de_design() -> None:
    """A razão é a mesma conta do estado 06 do pacote aprovado: 16,55 / 385,00 = 4,30%."""
    assert quantity_divergence_ratio(
        difference=Decimal("16.55"), legend_quantity=Decimal("385.00")
    ) == Decimal("4.30")


def test_os_campos_novos_da_divergencia_batem_com_o_breakdown() -> None:
    """A divergência de verdade carrega a parcela, o piso, quem governou e a razão — a
    mesma conta que abriu a issue, não uma segunda derivação."""
    item = _item(quantity=Decimal("100.00"))
    divergence = _source(length_m="110.00").divergence_for(item)

    assert divergence is not None
    assert divergence.relative_tolerance == Decimal("1.0000")
    assert divergence.absolute_floor == Decimal("0.01")
    assert divergence.tolerance_bound is ToleranceBound.RELATIVE
    assert divergence.legend_ratio == Decimal("10.00")


def test_divergencia_gravada_antes_desta_mudanca_continua_legivel() -> None:
    """Critério 3: uma divergência sem os campos novos lê sem erro, e eles chegam `None`."""
    item = _item(quantity=Decimal("100.00"))
    divergence = _source(length_m="110.00").divergence_for(item)
    assert divergence is not None

    legado = divergence.model_dump(mode="json")
    for campo in ("relative_tolerance", "absolute_floor", "tolerance_bound", "legend_ratio"):
        del legado[campo]

    relido = QuantityDivergence.model_validate(legado)
    assert relido.relative_tolerance is None
    assert relido.absolute_floor is None
    assert relido.tolerance_bound is None
    assert relido.legend_ratio is None
    assert relido.difference == divergence.difference
    assert relido.tolerance == divergence.tolerance


def test_parcela_piso_vencedora_ou_razao_fora_da_conta_sao_recusadas() -> None:
    """Os quatro campos novos são conferidos como `difference`/`tolerance`: declarar um
    valor que não é o recomputado é recusado, nunca aceito como rótulo colado por fora.

    Usa uma dupla de origens PRÓPRIA (não `_origins()`, que fica bem na borda da
    tolerância) para garantir que a diferença passe da tolerância antes de qualquer
    checagem dos campos novos.
    """
    scene = SceneQuantityOrigin(
        quantity=Decimal("110.00"), element_ref=_ELEMENT, precision=Precision.EXACT
    )
    legend = LegendQuantityOrigin(
        quantity=Decimal("100.00"),
        source="legend_extraction",
        extractor="legend-extractor-sintetico",
        extractor_version="1.0.0",
    )
    base = {
        "scene": scene,
        "legend": legend,
        "difference": Decimal("10.00"),
        "tolerance": Decimal("1.0000"),
    }

    with pytest.raises(ValidationError) as relativa:
        QuantityDivergence(**base, relative_tolerance=Decimal("2.00"))
    with pytest.raises(ValidationError) as piso:
        QuantityDivergence(**base, absolute_floor=Decimal("0.02"))
    with pytest.raises(ValidationError) as vencedora:
        QuantityDivergence(**base, tolerance_bound=ToleranceBound.ABSOLUTE_FLOOR)
    with pytest.raises(ValidationError) as razao:
        QuantityDivergence(**base, legend_ratio=Decimal("999.00"))

    assert valuation_error_codes(relativa.value) == ["QUANTITY_DIVERGENCE_RELATIVE_MISMATCH"]
    assert valuation_error_codes(piso.value) == ["QUANTITY_DIVERGENCE_FLOOR_MISMATCH"]
    assert valuation_error_codes(vencedora.value) == ["QUANTITY_DIVERGENCE_BOUND_MISMATCH"]
    assert valuation_error_codes(razao.value) == ["QUANTITY_DIVERGENCE_RATIO_MISMATCH"]


def test_o_pacote_lista_os_itens_divergentes_e_os_que_ainda_esperam_decisao() -> None:
    divergente = _source(length_m="110.00").record_divergence(_item())
    limpo = _item(item_id="ti_0000000000000002", element_ref="EL-000200")
    packet = _packet([divergente, limpo])

    assert [item.id for item in packet.divergent_items()] == [_ITEM]
    assert packet.open_divergence_item_ids() == frozenset({_ITEM})

    resolvido = apply_divergence_resolution(
        packet,
        TakeoffDivergenceResolutionInput(
            item_id=_ITEM,
            choice=DivergenceChoice.LEGEND,
            reviewer_id=_REVIEWER,
            reviewer_role="orcamentista",
            resolved_at=_RESOLVED_AT,
        ),
    )

    assert [item.id for item in resolvido.divergent_items()] == [_ITEM]
    assert resolvido.open_divergence_item_ids() == frozenset()
