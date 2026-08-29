"""`QuantitySource` (F-047 T4): a quantidade da cena aprovada atravessa a fronteira.

O teste central deste arquivo é o que oferece `418,12` dos DOIS lados sem identidade e exige
que o adaptador **não** case: número igual não é identidade, e casar por ele seria a
associação por proximidade que o ADR-0058 rejeita com todas as letras.

Os testes de integração exportam uma cena de verdade pelo `export_scene_package` do worker —
a única forma de provar que a quantidade nasce do portão de exportação que já existe, e não
de um CSV fabricado no teste. Importar o worker aqui é o que outros testes de `tests/valuation`
já fazem (`test_chain_demo.py`, `builders.py`); a proibição do ADR-0016 é ao pacote
`croquito_valuation` depender do worker, e o módulo sob teste não depende.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from croquito_core.errors import DomainValidationError
from croquito_core.ids import new_uuid7
from croquito_core.models import (
    CircleGeometry,
    Entity,
    EntityKind,
    LayerName,
    LineGeometry,
    Point2D,
    Precision,
    Provenance,
    SceneRevision,
)
from croquito_valuation.errors import ValuationValidationError, valuation_error_codes
from croquito_valuation.models import ReviewerDecision
from croquito_valuation.quantity_source import (
    QuantityDimension,
    QuantityResolution,
    QuantitySource,
    QuantityUnresolvedReason,
    parse_scene_quantities,
)
from croquito_valuation.takeoff import (
    TAKEOFF_SCHEMA_VERSION,
    TakeoffItem,
    TakeoffItemStatus,
    TakeoffPacket,
)
from croquito_worker.dxf import export_scene_package

_DIGEST = "a" * 64
_PDF_DIGEST = "b" * 64
_ITEM = "ti_0000000000000001"
_PROVENANCE = Provenance(
    source_type="synthetic_test",
    source_ids=["fixture:f-047-t4"],
    summary_code="TEST_FIXTURE",
)


def _item(
    *,
    item_id: str = _ITEM,
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


def _csv(
    rows: list[dict[str, str]],
    *,
    with_identity: bool = True,
) -> str:
    columns = ["entity_id"]
    if with_identity:
        columns.append("element_ref")
    columns += ["layer", "kind", "precision", "length_m", "perimeter_m", "area_m2"]
    lines = [",".join(columns)]
    for row in rows:
        lines.append(",".join(row.get(column, "") for column in columns))
    return "\n".join(lines) + "\n"


def _scene_row(
    *,
    element_ref: str = "EL-000100",
    precision: str = "exact",
    area_m2: str = "418.120000",
    length_m: str = "",
    perimeter_m: str = "",
    entity_id: str = "3f0f0f0f-0000-0000-0000-000000000001",
) -> dict[str, str]:
    return {
        "entity_id": entity_id,
        "element_ref": element_ref,
        "layer": "PATAMAR",
        "kind": "polyline",
        "precision": precision,
        "length_m": length_m,
        "perimeter_m": perimeter_m,
        "area_m2": area_m2,
    }


# ---------------------------------------------------------------------------
# O teste central: número igual não é identidade.
# ---------------------------------------------------------------------------


def test_o_mesmo_418_12_dos_dois_lados_sem_identidade_nao_casa() -> None:
    """F-047 T4, critério 2 — a rejeição central do ADR-0058.

    A cena tem 418,12 m². A legenda tem 418,12 m². Nenhum dos dois declarou identidade. O
    adaptador NÃO casa: casar por número igual erra em silêncio no dia em que dois elementos
    têm a mesma área, ou em que a leitura tem um dígito trocado.
    """
    source = QuantitySource.from_csv_text(_csv([_scene_row(element_ref="", area_m2="418.120000")]))
    item = _item(element_ref=None, unit="m2", quantity=None)

    resolution = source.resolve(item)

    assert resolution.resolved is False
    assert resolution.reason is QuantityUnresolvedReason.ITEM_WITHOUT_ELEMENT_REF
    assert resolution.quantity is None
    # O número está lá, dos dois lados, e continua não bastando.
    assert source.rows[0].area_m2 == Decimal("418.120000")
    assert "418,12" in item.raw_text
    with pytest.raises(ValuationValidationError) as raised:
        source.feed(item)
    assert raised.value.code == "QUANTITY_SOURCE_UNRESOLVED"


def test_identidade_so_na_cena_tambem_nao_casa() -> None:
    """Meio elo é elo nenhum: a cena declarou, a legenda não."""
    source = QuantitySource.from_csv_text(_csv([_scene_row()]))

    resolution = source.resolve(_item(element_ref=None))

    assert resolution.reason is QuantityUnresolvedReason.ITEM_WITHOUT_ELEMENT_REF


def test_identidade_so_na_legenda_devolve_o_motivo_em_vez_de_palpitar() -> None:
    """F-047 T4, critério 1: ausência de par é estado legível, com o motivo nomeado."""
    source = QuantitySource.from_csv_text(_csv([_scene_row(element_ref="EL-000900")]))

    resolution = source.resolve(_item(element_ref="EL-000100"))

    assert resolution.resolved is False
    assert resolution.element_ref == "EL-000100"
    assert resolution.reason is QuantityUnresolvedReason.ELEMENT_REF_ABSENT_FROM_SCENE


def test_croqui_sem_a_coluna_de_identidade_e_lido_sem_erro_e_nao_resolve_nada() -> None:
    """Sem nenhuma identidade declarada, o CSV de sempre é formato válido — e não casa."""
    source = QuantitySource.from_csv_text(_csv([_scene_row()], with_identity=False))

    assert len(source.rows) == 1
    assert source.rows[0].element_ref is None
    assert source.row_for("EL-000100") is None
    assert source.resolve(_item()).reason is QuantityUnresolvedReason.ELEMENT_REF_ABSENT_FROM_SCENE


# ---------------------------------------------------------------------------
# Resolução por identidade, precisão e unidade.
# ---------------------------------------------------------------------------


def test_identidade_nos_dois_lados_resolve_a_quantidade_com_a_precisao_da_origem() -> None:
    """F-047 T4, critérios 1 e 4: o elo declarado resolve, e a precisão vem da cena."""
    source = QuantitySource.from_csv_text(_csv([_scene_row(precision="exact")]))

    resolution = source.resolve(_item())

    assert resolution.resolved is True
    assert resolution.quantity == Decimal("418.120000")
    assert resolution.unit == "m2"
    assert resolution.dimension is QuantityDimension.AREA
    assert resolution.precision is Precision.EXACT
    assert resolution.reason is None


def test_derived_atravessa_como_derived_e_nunca_e_promovido_a_exact() -> None:
    """F-047 T4, critério 4: agrupar, atravessar e alimentar nunca promovem precisão."""
    source = QuantitySource.from_csv_text(_csv([_scene_row(precision="derived")]))

    fed = source.feed(_item())

    # A cena disse `derived`; a medição recebe `derived`. Não há caminho que devolva
    # `exact` de uma linha que nasceu derivada.
    assert source.rows[0].precision is Precision.DERIVED
    assert fed.scene_precision is Precision.DERIVED
    assert source.resolve(_item()).precision is Precision.DERIVED


@pytest.mark.parametrize("precision", ["approximate", "unresolved"])
def test_approximate_e_unresolved_nunca_viram_quantidade(precision: str) -> None:
    """F-047 T4, critério 5, na leitura direta do CSV."""
    source = QuantitySource.from_csv_text(_csv([_scene_row(precision=precision)]))

    resolution = source.resolve(_item())

    assert resolution.resolved is False
    assert resolution.reason is QuantityUnresolvedReason.PRECISION_NOT_ELIGIBLE
    assert resolution.precision is Precision(precision)


def test_linha_de_area_nao_alimenta_item_em_metro() -> None:
    """F-047 T4, critério 6: a unidade tem de bater, e a recusa é nomeada."""
    source = QuantitySource.from_csv_text(_csv([_scene_row(area_m2="418.120000")]))

    resolution = source.resolve(_item(unit="m"))

    assert resolution.reason is QuantityUnresolvedReason.UNIT_MISMATCH


def test_linha_de_comprimento_nao_alimenta_item_em_metro_quadrado() -> None:
    """F-047 T4, critério 6, no sentido inverso: nada de converter metro em m²."""
    source = QuantitySource.from_csv_text(_csv([_scene_row(area_m2="", length_m="42.500000")]))

    resolution = source.resolve(_item(unit="m2"))

    assert resolution.reason is QuantityUnresolvedReason.UNIT_MISMATCH


def test_item_em_metro_aceita_comprimento_e_tambem_perimetro() -> None:
    """Alambrado traçado como linha mede comprimento; fechado, mede perímetro."""
    aberto = QuantitySource.from_csv_text(_csv([_scene_row(area_m2="", length_m="42.500000")]))
    fechado = QuantitySource.from_csv_text(
        _csv([_scene_row(area_m2="120.000000", perimeter_m="44.000000")])
    )

    assert aberto.resolve(_item(unit="m")).quantity == Decimal("42.500000")
    assert fechado.resolve(_item(unit="m")).quantity == Decimal("44.000000")
    assert fechado.resolve(_item(unit="m2")).quantity == Decimal("120.000000")


def test_comprimento_e_perimetro_juntos_recusam_em_vez_de_somar() -> None:
    """Somar traço com perímetro inventaria qual dos dois a legenda mede."""
    source = QuantitySource.from_csv_text(
        _csv([_scene_row(area_m2="", length_m="10.000000", perimeter_m="44.000000")])
    )

    assert source.resolve(_item(unit="m")).reason is QuantityUnresolvedReason.LENGTH_AMBIGUOUS


@pytest.mark.parametrize("unit", ["un", "m3", "mes"])
def test_unidade_que_a_cena_nao_produz_recusa_com_codigo_proprio(unit: str) -> None:
    """Contagem, volume e tempo não têm grandeza na cena: recusa, nunca conversão."""
    source = QuantitySource.from_csv_text(_csv([_scene_row()]))

    resolution = source.resolve(_item(unit=unit))

    assert resolution.reason is QuantityUnresolvedReason.UNIT_NOT_DERIVABLE_FROM_SCENE


def test_unidade_escrita_como_m2_com_expoente_normaliza_igual_ao_catalogo() -> None:
    """`m²` e `m2` são a mesma unidade — a normalização é a única do pacote."""
    source = QuantitySource.from_csv_text(_csv([_scene_row()]))

    assert source.resolve(_item(unit="m²")).quantity == Decimal("418.120000")
    assert source.resolve(_item(unit="ml")).reason is QuantityUnresolvedReason.UNIT_MISMATCH


def test_linha_sem_grandeza_nenhuma_recusa_por_quantidade_ausente() -> None:
    source = QuantitySource.from_csv_text(_csv([_scene_row(area_m2="")]))

    assert source.resolve(_item()).reason is QuantityUnresolvedReason.QUANTITY_ABSENT


def test_grandeza_zerada_nao_vira_quantidade_de_medicao() -> None:
    source = QuantitySource.from_csv_text(_csv([_scene_row(area_m2="0.000000")]))

    assert source.resolve(_item()).reason is QuantityUnresolvedReason.QUANTITY_NOT_POSITIVE


def test_identidade_repetida_no_csv_e_recusa_explicita() -> None:
    """F-047 T4, critério 8: depois do agrupamento da T3 não deveria haver duas linhas.

    Havendo, o adaptador recusa o arquivo — nunca "pega a primeira" nem soma por conta.
    """
    with pytest.raises(ValuationValidationError) as raised:
        QuantitySource.from_csv_text(
            _csv(
                [
                    _scene_row(entity_id="uuid-a"),
                    _scene_row(entity_id="uuid-b", area_m2="99.000000"),
                ]
            )
        )

    assert raised.value.code == "QUANTITY_SOURCE_DUPLICATE_ELEMENT_REF"
    assert raised.value.details["element_ref"] == "EL-000100"


def test_resolve_all_preserva_a_ordem_recebida() -> None:
    source = QuantitySource.from_csv_text(_csv([_scene_row()]))
    items = [_item(), _item(item_id="ti_0000000000000002", element_ref=None)]

    resolutions = source.resolve_all(items)

    assert [resolution.item_id for resolution in resolutions] == [item.id for item in items]
    assert [resolution.resolved for resolution in resolutions] == [True, False]


# ---------------------------------------------------------------------------
# Leitura do CSV: falha fechada.
# ---------------------------------------------------------------------------


def test_csv_sem_cabecalho_e_recusado() -> None:
    with pytest.raises(ValuationValidationError) as raised:
        parse_scene_quantities("")

    assert raised.value.code == "QUANTITY_SOURCE_CSV_INVALID"


def test_csv_com_coluna_desconhecida_ou_faltando_e_recusado() -> None:
    faltando = "entity_id,layer,kind,precision\nx,PATAMAR,polyline,exact\n"
    desconhecida = _csv([_scene_row()]).replace("layer", "camada", 1)

    for text in (faltando, desconhecida):
        with pytest.raises(ValuationValidationError) as raised:
            parse_scene_quantities(text)
        assert raised.value.code == "QUANTITY_SOURCE_CSV_INVALID"


def test_precisao_fora_do_vocabulario_do_nucleo_e_recusada() -> None:
    with pytest.raises(ValuationValidationError) as raised:
        parse_scene_quantities(_csv([_scene_row(precision="quase")]))

    assert raised.value.code == "QUANTITY_SOURCE_CSV_INVALID"


def test_grandeza_ilegivel_e_recusada_com_a_coluna_e_a_linha() -> None:
    with pytest.raises(ValuationValidationError) as raised:
        parse_scene_quantities(_csv([_scene_row(area_m2="quatrocentos")]))

    assert raised.value.code == "QUANTITY_SOURCE_CSV_INVALID"
    assert raised.value.details["column"] == "area_m2"
    assert raised.value.details["line"] == 2


def test_grandeza_e_lida_do_texto_e_nao_por_float() -> None:
    """`Decimal("0.1")` do texto, não `Decimal(0.1)` do binário."""
    rows = parse_scene_quantities(_csv([_scene_row(area_m2="0.100000")]))

    assert rows[0].area_m2 == Decimal("0.100000")
    assert str(rows[0].area_m2) == "0.100000"


# ---------------------------------------------------------------------------
# A travessia: `feed` alimenta o item, com limites.
# ---------------------------------------------------------------------------


def test_feed_alimenta_o_item_ambiguo_e_ele_continua_esperando_decisao_humana() -> None:
    """F-047 T4, critério 3: a quantidade da cena é PROPOSTA com origem declarada."""
    source = QuantitySource.from_csv_text(_csv([_scene_row()]))
    item = _item(status=TakeoffItemStatus.AMBIGUOUS)

    fed = source.feed(item)

    assert fed.quantity == Decimal("418.120000")
    assert fed.source == "scene_graph"
    assert fed.scene_precision is Precision.EXACT
    assert fed.element_ref == "EL-000100"
    assert fed.status is TakeoffItemStatus.PROPOSED
    assert fed.decision is None
    # Cópia: o item de entrada não muda.
    assert item.quantity is None
    assert item.source == "legend_extraction"


def test_feed_nao_sobrescreve_a_quantidade_lida_na_legenda() -> None:
    """ADR-0058 decisão 6: nenhuma origem apaga a outra; divergir é diagnóstico (T5)."""
    source = QuantitySource.from_csv_text(_csv([_scene_row()]))
    item = _item(status=TakeoffItemStatus.PROPOSED, quantity=Decimal("400.00"))

    with pytest.raises(ValuationValidationError) as raised:
        source.feed(item)

    assert raised.value.code == "QUANTITY_SOURCE_ITEM_ALREADY_QUANTIFIED"


def test_feed_recusa_item_ja_revisado() -> None:
    source = QuantitySource.from_csv_text(_csv([_scene_row()]))
    rejected = _item(
        status=TakeoffItemStatus.REJECTED,
        decision=ReviewerDecision(
            decision_id="vd_0123456789abcdef",
            action="reject",
            reviewer_id="orcamentista-sintetico",
            reviewer_role="orcamentista",
            decided_at=datetime(2026, 2, 1, 12, 0, tzinfo=UTC),
        ),
    )

    with pytest.raises(ValuationValidationError) as raised:
        source.feed(rejected)

    assert raised.value.code == "TAKEOFF_ITEM_ALREADY_REVIEWED"


# ---------------------------------------------------------------------------
# O contrato do `TakeoffItem`: aditivo, e fechado onde precisa.
# ---------------------------------------------------------------------------


def test_item_de_legenda_continua_exatamente_como_hoje() -> None:
    """F-047 T4, critério 7: sem `source = scene_graph`, nada muda."""
    item = _item(status=TakeoffItemStatus.PROPOSED, quantity=Decimal("418.12"))

    assert item.source == "legend_extraction"
    assert item.scene_precision is None
    assert item.quantity == Decimal("418.12")


def test_o_contrato_de_takeoff_subiu_e_continua_aceitando_a_versao_anterior() -> None:
    """F-047 T4, critério 3: a subida é aditiva (e continuou sendo na T5 e na T5b, em
    `1.3.0`)."""
    assert TAKEOFF_SCHEMA_VERSION == "1.3.0"
    payload = {
        "plate_id": "praca-sintetica-norte-prancha-01",
        "page_number": 1,
        "image_sha256": _DIGEST,
        "source_pdf_sha256": _PDF_DIGEST,
        "items": [_item(status=TakeoffItemStatus.PROPOSED).model_dump()],
        "safety_notes": [
            "Extração automática da legenda; quantidade não confirmada.",
            "Decisão do orçamentista obrigatória antes de qualquer boletim.",
        ],
    }

    antigo = TakeoffPacket.model_validate({**payload, "schema_version": "1.0.0"})
    intermediario = TakeoffPacket.model_validate({**payload, "schema_version": "1.1.0"})
    novo = TakeoffPacket.model_validate(payload)

    assert antigo.schema_version == "1.0.0"
    assert intermediario.schema_version == "1.1.0"
    assert novo.schema_version == "1.3.0"
    assert antigo.items[0].element_ref == "EL-000100"
    assert antigo.items[0].scene_divergence is None


def test_item_da_cena_exige_identidade_e_precisao() -> None:
    with pytest.raises(ValidationError) as sem_ref:
        _item(source="scene_graph", element_ref=None, scene_precision=Precision.EXACT)
    with pytest.raises(ValidationError) as sem_precisao:
        _item(source="scene_graph", scene_precision=None)

    assert valuation_error_codes(sem_ref.value) == ["TAKEOFF_ITEM_SCENE_WITHOUT_ELEMENT_REF"]
    assert valuation_error_codes(sem_precisao.value) == ["TAKEOFF_ITEM_SCENE_WITHOUT_PRECISION"]


@pytest.mark.parametrize("precision", [Precision.APPROXIMATE, Precision.UNRESOLVED])
def test_item_da_cena_recusa_precisao_inelegivel_no_proprio_contrato(
    precision: Precision,
) -> None:
    """F-047 T4, critério 5: `approximate` não é representável como quantidade da cena."""
    with pytest.raises(ValidationError) as raised:
        _item(source="scene_graph", scene_precision=precision)

    assert valuation_error_codes(raised.value) == ["TAKEOFF_ITEM_SCENE_PRECISION_NOT_ELIGIBLE"]


def test_precisao_de_cena_em_item_de_legenda_e_recusada() -> None:
    with pytest.raises(ValidationError) as raised:
        _item(source="legend_extraction", scene_precision=Precision.EXACT)

    assert valuation_error_codes(raised.value) == [
        "TAKEOFF_ITEM_SCENE_PRECISION_WITHOUT_SCENE_SOURCE"
    ]


def test_resolucao_recusada_nunca_carrega_quantidade() -> None:
    with pytest.raises(ValidationError) as raised:
        QuantityResolution(
            item_id=_ITEM,
            element_ref="EL-000100",
            resolved=False,
            quantity=Decimal("418.12"),
            reason=QuantityUnresolvedReason.UNIT_MISMATCH,
        )

    assert valuation_error_codes(raised.value) == ["QUANTITY_RESOLUTION_INCONSISTENT"]


# ---------------------------------------------------------------------------
# Integração com o portão de exportação que já existe.
# ---------------------------------------------------------------------------


def _piso_entity(*, element_ref: str, precision: Precision) -> Entity:
    return Entity(
        kind=EntityKind.CIRCLE,
        layer=LayerName.PATAMAR,
        precision=precision,
        geometry=CircleGeometry(center=Point2D(x=0, y=0), radius=2.0),
        provenance=_PROVENANCE,
        element_ref=element_ref,
    )


def test_a_quantidade_vem_do_csv_que_o_portao_de_exportacao_publicou(tmp_path: Path) -> None:
    """F-047 T4, critério da cena aprovada: o adaptador lê o que o portão deixou passar."""
    entity = _piso_entity(element_ref="EL-000100", precision=Precision.EXACT)
    scene = SceneRevision(job_id=new_uuid7(), version=1, approved=True, entities=[entity])

    result = export_scene_package(scene, tmp_path, package_stem="f-047-t4")
    source = QuantitySource.from_quantities_csv(result.quantities_path)
    resolution = source.resolve(_item(unit="m2"))

    assert resolution.resolved is True
    assert resolution.precision is Precision.EXACT
    assert math.isclose(float(resolution.quantity or 0), math.pi * 4.0, rel_tol=1e-6)


def test_cena_nao_aprovada_nao_produz_csv_e_portanto_nao_produz_quantidade(
    tmp_path: Path,
) -> None:
    """Nenhum caminho novo contorna o portão: sem export, não há de onde ler."""
    entity = _piso_entity(element_ref="EL-000100", precision=Precision.EXACT)
    scene = SceneRevision(job_id=new_uuid7(), version=1, approved=False, entities=[entity])

    with pytest.raises(DomainValidationError, match="SCENE_NOT_APPROVED"):
        export_scene_package(scene, tmp_path)

    assert not (tmp_path / "quantitativos.csv").exists()


def test_aproximacao_aceita_na_cena_exporta_e_ainda_assim_nao_alimenta_a_medicao(
    tmp_path: Path,
) -> None:
    """F-047 T4, critério 5, na sua forma mais dura (emenda humana ao ADR-0058).

    A cena registrou o aceite de aproximação — o portão de exportação deixa passar e o DXF é
    publicado. A medição continua recusando: o carimbo de aproximação sobrevive à tela e
    morre na planilha, onde o número vira uma linha de R$.
    """
    entity = _piso_entity(element_ref="EL-000100", precision=Precision.APPROXIMATE)
    scene = SceneRevision(
        job_id=new_uuid7(),
        version=1,
        approved=True,
        accepted_approximation_ids={entity.id},
        entities=[entity],
    )

    result = export_scene_package(scene, tmp_path, package_stem="f-047-t4-aprox")
    source = QuantitySource.from_quantities_csv(result.quantities_path)

    assert scene.export_errors() == []  # o aceite de fato liberou a exportação
    assert source.rows[0].precision is Precision.APPROXIMATE
    resolution = source.resolve(_item(unit="m2"))
    assert resolution.resolved is False
    assert resolution.reason is QuantityUnresolvedReason.PRECISION_NOT_ELIGIBLE
    with pytest.raises(ValuationValidationError) as raised:
        source.feed(_item(unit="m2"))
    assert raised.value.code == "QUANTITY_SOURCE_UNRESOLVED"


def test_dois_elementos_com_o_mesmo_rotulo_nunca_casam_pelo_rotulo(tmp_path: Path) -> None:
    """F-047 T2b, critério 5 — a prova mais dura do rótulo: NADA casa por ele.

    Dois elementos da cena aprovada carregam exatamente o mesmo nome legível ("Alambrado da
    quadra") e refs diferentes. Eles continuam sendo dois elementos, com quantidades próprias,
    e o `QuantitySource` resolve cada item pelo `element_ref` — que é o único elo. O rótulo
    nem sequer atravessa a fronteira: ele não é coluna do `quantitativos.csv`, porque a
    medição não tem o que fazer com um texto livre que não identifica nada.
    """
    primeiro = Entity(
        kind=EntityKind.LINE,
        layer=LayerName.ALAMBRADO,
        precision=Precision.EXACT,
        geometry=LineGeometry(start=Point2D(x=0, y=0), end=Point2D(x=10, y=0)),
        provenance=_PROVENANCE,
        element_ref="EL-000100",
    )
    segundo = Entity(
        kind=EntityKind.LINE,
        layer=LayerName.ALAMBRADO,
        precision=Precision.EXACT,
        geometry=LineGeometry(start=Point2D(x=0, y=5), end=Point2D(x=25, y=5)),
        provenance=_PROVENANCE,
        element_ref="EL-000200",
    )
    scene = SceneRevision(
        job_id=new_uuid7(),
        version=1,
        approved=True,
        entities=[primeiro, segundo],
        element_labels={
            "EL-000100": "Alambrado da quadra",
            "EL-000200": "Alambrado da quadra",
        },
    )

    result = export_scene_package(scene, tmp_path, package_stem="f-047-t2b-rotulo")
    csv_text = result.quantities_path.read_text(encoding="utf-8")
    source = QuantitySource.from_quantities_csv(result.quantities_path)

    # O rótulo não viaja para a medição: nem coluna, nem valor.
    assert "Alambrado" not in csv_text
    assert "label" not in csv_text.splitlines()[0]
    # Dois elementos, duas linhas, duas quantidades — o nome igual não fundiu nada.
    assert sorted(row.element_ref or "" for row in source.rows) == ["EL-000100", "EL-000200"]
    um = source.resolve(_item(item_id="ti_0000000000000001", element_ref="EL-000100", unit="m"))
    outro = source.resolve(_item(item_id="ti_0000000000000002", element_ref="EL-000200", unit="m"))
    assert um.resolved is True and outro.resolved is True
    assert math.isclose(float(um.quantity or 0), 10.0, rel_tol=1e-6)
    assert math.isclose(float(outro.quantity or 0), 25.0, rel_tol=1e-6)
    # E um item que só sabe o nome, sem identidade, continua sem par: rótulo não é elo.
    sem_identidade = source.resolve(_item(element_ref=None, unit="m"))
    assert sem_identidade.resolved is False
    assert sem_identidade.reason is QuantityUnresolvedReason.ITEM_WITHOUT_ELEMENT_REF


def test_grupo_de_tracos_da_t3_atravessa_como_um_unico_elemento(tmp_path: Path) -> None:
    """O agrupamento por elemento da T3 é o que o adaptador consome: uma linha, um item."""
    muro_a = Entity(
        kind=EntityKind.LINE,
        layer=LayerName.MURO,
        precision=Precision.EXACT,
        geometry=LineGeometry(start=Point2D(x=0, y=0), end=Point2D(x=10, y=0)),
        provenance=_PROVENANCE,
        element_ref="EL-000200",
    )
    muro_b = Entity(
        kind=EntityKind.LINE,
        layer=LayerName.MURO,
        precision=Precision.DERIVED,
        geometry=LineGeometry(start=Point2D(x=10, y=0), end=Point2D(x=10, y=5)),
        element_ref="EL-000200",
    )
    scene = SceneRevision(job_id=new_uuid7(), version=1, approved=True, entities=[muro_a, muro_b])

    result = export_scene_package(scene, tmp_path, package_stem="f-047-t4-grupo")
    source = QuantitySource.from_quantities_csv(result.quantities_path)
    resolution = source.resolve(_item(element_ref="EL-000200", unit="m"))

    assert resolution.resolved is True
    assert math.isclose(float(resolution.quantity or 0), 15.0, rel_tol=1e-6)
    # A pior precisão do grupo atravessa; agrupar nunca promove.
    assert resolution.precision is Precision.DERIVED
