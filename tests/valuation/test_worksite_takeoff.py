"""`WorksiteTakeoff` consolida as pranchas de uma praça sem absorvê-las (F-046, ADR-0057):
referência por `(plate_id, digest)`, identidade por `(plate_id, item_id)` e fusão de
leituras só por vínculo humano declarado — nunca por semelhança de rótulo, unidade ou
proximidade."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from croquito_valuation.errors import (
    ValuationValidationError,
    valuation_error_codes,
    valuation_errors,
)
from croquito_valuation.takeoff import (
    PlateBox,
    PlateEvidence,
    TakeoffItem,
    TakeoffItemStatus,
    TakeoffPacket,
)
from croquito_valuation.worksite_takeoff import (
    TakeoffItemAddress,
    TakeoffItemIdentityLink,
    WorksitePlateReference,
    WorksiteTakeoff,
    build_worksite_takeoff,
    ensure_worksite_matches_packets,
    takeoff_packet_digest,
)

_WORKSITE_KEY = "praca-sintetica-norte"
_PLATE_A = "praca-sintetica-norte-planta-geral"
_PLATE_B = "praca-sintetica-norte-detalhe-01"
_PLATE_C = "praca-sintetica-norte-corte-01"
_DIGEST_A = "a" * 64
_DIGEST_B = "b" * 64
_DIGEST_C = "d" * 64
_PDF_DIGEST = "c" * 64
_ITEM_X = "ti_0000000000000001"
_ITEM_Y = "ti_0000000000000002"
_UNKNOWN_ITEM = "ti_ffffffffffffffff"


def _evidence(*, plate_id: str, image_sha256: str) -> PlateEvidence:
    return PlateEvidence(
        plate_id=plate_id,
        page_number=1,
        image_sha256=image_sha256,
        bbox=PlateBox(left=10, top=10, right=110, bottom=60),
    )


def _item(
    *,
    item_id: str,
    plate_id: str,
    image_sha256: str,
    label: str = "PISO INTERTRAVADO",
    quantity: Decimal = Decimal("105.00"),
    unit: str = "m2",
) -> TakeoffItem:
    return TakeoffItem(
        id=item_id,
        evidence=_evidence(plate_id=plate_id, image_sha256=image_sha256),
        raw_text=f"{label} {quantity} {unit}",
        label=label,
        quantity=quantity,
        unit=unit,
        source="legend_extraction",
        extractor="legend-extractor-sintetico",
        extractor_version="1.0.0",
        status=TakeoffItemStatus.PROPOSED,
    )


def _packet(*, plate_id: str, image_sha256: str, items: list[TakeoffItem]) -> TakeoffPacket:
    return TakeoffPacket(
        plate_id=plate_id,
        page_number=1,
        image_sha256=image_sha256,
        source_pdf_sha256=_PDF_DIGEST,
        items=items,
        safety_notes=[
            "Extração automática da legenda; quantidade não confirmada.",
            "Decisão do orçamentista obrigatória antes de qualquer boletim.",
        ],
    )


def _packet_a(item_id: str = _ITEM_X) -> TakeoffPacket:
    return _packet(
        plate_id=_PLATE_A,
        image_sha256=_DIGEST_A,
        items=[_item(item_id=item_id, plate_id=_PLATE_A, image_sha256=_DIGEST_A)],
    )


def _packet_b(item_id: str = _ITEM_X) -> TakeoffPacket:
    return _packet(
        plate_id=_PLATE_B,
        image_sha256=_DIGEST_B,
        items=[_item(item_id=item_id, plate_id=_PLATE_B, image_sha256=_DIGEST_B)],
    )


def _references() -> list[WorksitePlateReference]:
    return [
        WorksitePlateReference(plate_id=_PLATE_A, packet_digest=_DIGEST_A),
        WorksitePlateReference(plate_id=_PLATE_B, packet_digest=_DIGEST_B),
        WorksitePlateReference(plate_id=_PLATE_C, packet_digest=_DIGEST_C),
    ]


def _link(
    *,
    kept: TakeoffItemAddress,
    discarded: TakeoffItemAddress,
    declared_by: str | None = "orcamentista-sintetico",
    declared_at: datetime | None = datetime(2026, 8, 28, 12, 0, tzinfo=UTC),
    note: str | None = "Mesmo alambrado na planta geral e no detalhe.",
) -> TakeoffItemIdentityLink:
    return TakeoffItemIdentityLink(
        kept=kept,
        discarded=discarded,
        declared_by=declared_by,
        declared_at=declared_at,
        note=note,
    )


# --------------------------------------------------------------------------------------
# Critério 1: consolidado lista referências, nunca itens
# --------------------------------------------------------------------------------------


def test_build_lists_plates_by_id_and_digest_without_items() -> None:
    packet_a, packet_b = _packet_a(), _packet_b(_ITEM_Y)

    worksite = build_worksite_takeoff(_WORKSITE_KEY, [packet_a, packet_b])

    assert worksite.schema_version == "1.0.0"
    assert {plate.plate_id for plate in worksite.plates} == {_PLATE_A, _PLATE_B}
    assert {plate.packet_digest for plate in worksite.plates} == {
        takeoff_packet_digest(packet_a),
        takeoff_packet_digest(packet_b),
    }
    # Não é só "o campo items está vazio": o tipo não tem NENHUM atributo capaz de
    # carregar um TakeoffItem (ADR-0057, decisão 2).
    assert not hasattr(worksite, "items")


# --------------------------------------------------------------------------------------
# Critério 2: digest que não confere e prancha repetida
# --------------------------------------------------------------------------------------


def test_duplicate_plate_id_is_refused() -> None:
    reference = WorksitePlateReference(plate_id=_PLATE_A, packet_digest=_DIGEST_A)

    with pytest.raises(ValidationError) as raised:
        WorksiteTakeoff(worksite_key=_WORKSITE_KEY, plates=[reference, reference])

    assert valuation_error_codes(raised.value) == ["WORKSITE_DUPLICATE_PLATE"]


def test_packet_digest_mismatch_is_refused_on_revalidation() -> None:
    worksite = build_worksite_takeoff(_WORKSITE_KEY, [_packet_a()])
    reextracted = _packet(
        plate_id=_PLATE_A,
        image_sha256=_DIGEST_A,
        items=[_item(item_id=_ITEM_Y, plate_id=_PLATE_A, image_sha256=_DIGEST_A)],
    )

    with pytest.raises(ValuationValidationError) as raised:
        ensure_worksite_matches_packets(worksite, [reextracted])

    assert raised.value.code == "WORKSITE_PACKET_DIGEST_MISMATCH"


def test_missing_packet_is_refused_on_revalidation() -> None:
    worksite = build_worksite_takeoff(_WORKSITE_KEY, [_packet_a()])

    with pytest.raises(ValuationValidationError) as raised:
        ensure_worksite_matches_packets(worksite, [])

    assert raised.value.code == "WORKSITE_PACKET_MISSING"


# --------------------------------------------------------------------------------------
# Critério 3: (plate_id, item_id) nunca confunde item de folhas diferentes com o mesmo id
# --------------------------------------------------------------------------------------


def test_same_item_id_minted_in_two_plates_are_not_confused() -> None:
    packet_a, packet_b = _packet_a(_ITEM_X), _packet_b(_ITEM_X)
    address_a = TakeoffItemAddress(plate_id=_PLATE_A, item_id=_ITEM_X)
    address_b = TakeoffItemAddress(plate_id=_PLATE_B, item_id=_ITEM_X)

    assert address_a != address_b

    link = _link(kept=address_a, discarded=address_b)
    worksite = build_worksite_takeoff(_WORKSITE_KEY, [packet_a, packet_b], [link])

    # Só o endereço declarado como descartado deixa de contar; a contraparte cunhada com o
    # MESMO item_id na outra prancha não é atingida.
    assert worksite.discarded_addresses() == {(_PLATE_B, _ITEM_X)}
    assert (_PLATE_A, _ITEM_X) not in worksite.discarded_addresses()


# --------------------------------------------------------------------------------------
# Critério 4: tipo próprio do vínculo, com procedência e "a parcela que fica"
# --------------------------------------------------------------------------------------


def test_identity_link_carries_kept_reading_and_provenance() -> None:
    link = _link(
        kept=TakeoffItemAddress(plate_id=_PLATE_A, item_id=_ITEM_X),
        discarded=TakeoffItemAddress(plate_id=_PLATE_B, item_id=_ITEM_Y),
    )

    assert link.kept == TakeoffItemAddress(plate_id=_PLATE_A, item_id=_ITEM_X)
    assert link.discarded == TakeoffItemAddress(plate_id=_PLATE_B, item_id=_ITEM_Y)
    assert link.declared_by == "orcamentista-sintetico"
    assert link.declared_at is not None and link.declared_at.tzinfo is not None
    assert link.note


# --------------------------------------------------------------------------------------
# Critério 5: recusas nomeadas do vínculo
# --------------------------------------------------------------------------------------


def test_link_between_items_of_the_same_plate_is_refused() -> None:
    with pytest.raises(ValidationError) as raised:
        _link(
            kept=TakeoffItemAddress(plate_id=_PLATE_A, item_id=_ITEM_X),
            discarded=TakeoffItemAddress(plate_id=_PLATE_A, item_id=_ITEM_Y),
        )

    assert valuation_error_codes(raised.value) == ["WORKSITE_LINK_SAME_PLATE"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"declared_by": None},
        {"note": None},
        {"declared_at": None},
        {"declared_at": datetime(2026, 8, 28, 12, 0)},  # sem fuso horário
    ],
)
def test_link_missing_provenance_is_refused(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError) as raised:
        _link(
            kept=TakeoffItemAddress(plate_id=_PLATE_A, item_id=_ITEM_X),
            discarded=TakeoffItemAddress(plate_id=_PLATE_B, item_id=_ITEM_Y),
            **overrides,  # type: ignore[arg-type]
        )

    assert valuation_error_codes(raised.value) == ["WORKSITE_LINK_INCOMPLETE"]


def test_link_target_plate_outside_consolidated_is_refused() -> None:
    reference = WorksitePlateReference(plate_id=_PLATE_A, packet_digest=_DIGEST_A)
    link = _link(
        kept=TakeoffItemAddress(plate_id=_PLATE_A, item_id=_ITEM_X),
        discarded=TakeoffItemAddress(plate_id="prancha-fora-do-consolidado", item_id=_ITEM_Y),
    )

    with pytest.raises(ValidationError) as raised:
        WorksiteTakeoff(worksite_key=_WORKSITE_KEY, plates=[reference], identity_links=[link])

    assert valuation_error_codes(raised.value) == ["WORKSITE_LINK_UNKNOWN_TARGET"]


def test_link_target_item_missing_from_packet_is_refused_at_build() -> None:
    packet_a, packet_b = _packet_a(_ITEM_X), _packet_b(_ITEM_Y)
    link = _link(
        kept=TakeoffItemAddress(plate_id=_PLATE_A, item_id=_ITEM_X),
        discarded=TakeoffItemAddress(plate_id=_PLATE_B, item_id=_UNKNOWN_ITEM),
    )

    with pytest.raises(ValuationValidationError) as raised:
        build_worksite_takeoff(_WORKSITE_KEY, [packet_a, packet_b], [link])

    assert raised.value.code == "WORKSITE_LINK_UNKNOWN_TARGET"


# --------------------------------------------------------------------------------------
# Critério 6: cadeia de vínculo (A≡B, B≡C) é recusada, e a recusa não depende da ordem
# --------------------------------------------------------------------------------------


def test_identity_link_chain_is_refused_regardless_of_declaration_order() -> None:
    address_a = TakeoffItemAddress(plate_id=_PLATE_A, item_id=_ITEM_X)
    address_b = TakeoffItemAddress(plate_id=_PLATE_B, item_id=_ITEM_X)
    address_c = TakeoffItemAddress(plate_id=_PLATE_C, item_id=_ITEM_X)
    link_ab = _link(kept=address_a, discarded=address_b)
    link_bc = _link(kept=address_b, discarded=address_c)

    details = []
    for ordered_links in ([link_ab, link_bc], [link_bc, link_ab]):
        with pytest.raises(ValidationError) as raised:
            WorksiteTakeoff(
                worksite_key=_WORKSITE_KEY,
                plates=_references(),
                identity_links=ordered_links,
            )
        assert valuation_error_codes(raised.value) == ["WORKSITE_LINK_CHAIN_NOT_SUPPORTED"]
        details.append(valuation_errors(raised.value)[0].details)

    # A mesma cadeia, declarada em ordem inversa, produz a MESMA recusa com o mesmo
    # detalhe — a detecção não depende de qual vínculo a orçamentista digitou primeiro.
    assert details[0] == details[1]


def test_two_links_discarding_the_same_reading_to_different_keepers_is_refused() -> None:
    address_a = TakeoffItemAddress(plate_id=_PLATE_A, item_id=_ITEM_X)
    address_b = TakeoffItemAddress(plate_id=_PLATE_B, item_id=_ITEM_X)
    address_c = TakeoffItemAddress(plate_id=_PLATE_C, item_id=_ITEM_X)
    # B é declarado absorvido por A E por C: dois vencedores para a mesma leitura.
    link_to_a = _link(kept=address_a, discarded=address_b)
    link_to_c = _link(kept=address_c, discarded=address_b)

    with pytest.raises(ValidationError) as raised:
        WorksiteTakeoff(
            worksite_key=_WORKSITE_KEY,
            plates=_references(),
            identity_links=[link_to_a, link_to_c],
        )

    assert valuation_error_codes(raised.value) == ["WORKSITE_LINK_CHAIN_NOT_SUPPORTED"]


def test_fan_in_links_absorbing_two_readings_into_one_keeper_do_not_depend_on_order() -> None:
    address_a = TakeoffItemAddress(plate_id=_PLATE_A, item_id=_ITEM_X)
    address_b = TakeoffItemAddress(plate_id=_PLATE_B, item_id=_ITEM_X)
    address_c = TakeoffItemAddress(plate_id=_PLATE_C, item_id=_ITEM_X)
    link_to_b = _link(kept=address_a, discarded=address_b)
    link_to_c = _link(kept=address_a, discarded=address_c)

    for ordered_links in ([link_to_b, link_to_c], [link_to_c, link_to_b]):
        worksite = WorksiteTakeoff(
            worksite_key=_WORKSITE_KEY,
            plates=_references(),
            identity_links=ordered_links,
        )
        assert worksite.discarded_addresses() == {(_PLATE_B, _ITEM_X), (_PLATE_C, _ITEM_X)}


# --------------------------------------------------------------------------------------
# Critério 7: nada funde por semelhança de rótulo/unidade/quantidade
# --------------------------------------------------------------------------------------


def test_identical_looking_items_in_different_plates_count_as_two_without_a_link() -> None:
    packet_a = _packet_a(_ITEM_X)
    packet_b = _packet_b(_ITEM_Y)  # mesmo rótulo, unidade e quantidade de _item()

    worksite = build_worksite_takeoff(_WORKSITE_KEY, [packet_a, packet_b])

    assert worksite.identity_links == []
    assert worksite.discarded_addresses() == frozenset()
    assert {plate.plate_id for plate in worksite.plates} == {_PLATE_A, _PLATE_B}


# --------------------------------------------------------------------------------------
# Uma verdade só sobre o digest do pacote
# --------------------------------------------------------------------------------------


def test_packet_digest_matches_the_one_the_revision_already_publishes() -> None:
    """O digest do domínio e o que a revisão publica precisam ser o MESMO número.

    `document_digest` (worker) é o que a API já expõe como `packet_sha256` do pacote
    guardado na revisão, e o próprio docstring dele avisa do risco: duas serializações
    canônicas escritas em lados opostos passam nos testes de cada lado e divergem em
    produção. `packages/valuation` não pode importar o worker (direção de dependência), então
    a igualdade não é garantida por construção — é garantida por este teste, que quebra no
    dia em que um dos dois lados mudar a canonicalização.
    """
    from croquito_worker.valuation.round_extraction import document_digest

    packet = _packet_a(_ITEM_X)

    assert takeoff_packet_digest(packet) == document_digest(packet.model_dump(mode="json"))
