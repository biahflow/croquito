from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from croquito_core.models import MeasurementKind, UnitCode
from croquito_worker.association import (
    AssociationSet,
    ElementIdentity,
    active_element_identities,
    associate_readings,
    rederive_element_identity_candidates,
)
from croquito_worker.review import (
    DimensionReading,
    EvidenceRegion,
    PixelBox,
    ReadingStatus,
    ReviewPacket,
)
from croquito_worker.vision import (
    PixelCircle,
    PixelLine,
    PixelPoint,
    VisionProposal,
    VisionProposalSet,
)

IMAGE_DIGEST = "a" * 64


def _packet() -> ReviewPacket:
    return ReviewPacket(
        dataset_id="association-fixture-v1",
        page_number=1,
        image_sha256=IMAGE_DIGEST,
        readings=[
            DimensionReading(
                id="rd_1111111111111111",
                evidence=EvidenceRegion(
                    dataset_id="association-fixture-v1",
                    page_number=1,
                    image_sha256=IMAGE_DIGEST,
                    bbox=PixelBox(left=45, top=10, right=55, bottom=20),
                ),
                raw_text="10,00 m",
                value_si=Decimal("10.00"),
                unit=UnitCode.METRE,
                kind=MeasurementKind.WIDTH,
                written_decimals=2,
                target_hint="linha superior",
                extractor="fixture",
                extractor_version="v1",
                status=ReadingStatus.PROPOSED,
            )
        ],
        safety_notes=["fixture", "revisão humana obrigatória"],
    )


def _proposals(*, image_digest: str = IMAGE_DIGEST) -> VisionProposalSet:
    return VisionProposalSet(
        dataset_id="association-fixture-v1",
        page_number=1,
        image_sha256=image_digest,
        image_width_px=100,
        image_height_px=100,
        configured_limits={"line": 10, "circle": 10, "contour": 10},
        limit_reached=[],
        proposals=[
            VisionProposal(
                id="vp_1111111111111111",
                kind="line",
                geometry=PixelLine(
                    start=PixelPoint(x=0, y=15),
                    end=PixelPoint(x=100, y=15),
                ),
                algorithm="fixture",
                quality_score=0.9,
            ),
            VisionProposal(
                id="vp_2222222222222222",
                kind="circle",
                geometry=PixelCircle(center=PixelPoint(x=80, y=80), radius=10),
                algorithm="fixture",
                quality_score=0.99,
            ),
        ],
        safety_notes=["fixture", "unresolved", "non-exportable"],
    )


def test_association_ranks_nearby_line_without_confirming_it() -> None:
    associations = associate_readings(_packet(), _proposals())

    assert associations.unassociated_reading_ids == []
    assert len(associations.candidates) == 1
    candidate = associations.candidates[0]
    assert candidate.reading_id == "rd_1111111111111111"
    assert candidate.proposal_id == "vp_1111111111111111"
    assert candidate.relation == "nearest_geometry"
    assert candidate.pixel_distance == 0
    assert candidate.precision == "unresolved"
    assert candidate.export is False


def test_association_refuses_mismatched_evidence_digest() -> None:
    with pytest.raises(ValueError, match="digest"):
        associate_readings(_packet(), _proposals(image_digest="b" * 64))


# --------------------------------------------------------------------------------------
# F-051 T4 — a candidata por identidade, reconstruída a cada ato (ADR-0063, decisão 3)
#
# A cota-balão é a medida escrita LONGE do elemento, ligada a ele por uma letra. A fixture
# abaixo é esse caso e não outro: a leitura do balão fica no meio da folha, o elemento "B"
# fica no canto oposto — a mais de 1200 px, quatro vezes o alcance do funil de proximidade.
# Nenhuma candidata por identidade nasce de distância aqui; todas nascem do ato humano.
# --------------------------------------------------------------------------------------

LINHA_VIZINHA = "vp_1111111111111111"
CIRCULO_VIZINHO = "vp_2222222222222222"
GRADE_B_TRECHO_1 = "vp_3333333333333333"
GRADE_B_TRECHO_2 = "vp_4444444444444444"
GRADE_C = "vp_5555555555555555"

COTA_VIZINHA = "rd_1111111111111111"
COTA_BALAO = "rd_2222222222222222"
COTA_SOLTA = "rd_3333333333333333"


def _reading(
    reading_id: str,
    *,
    bbox: PixelBox,
    entity_label: str | None = None,
) -> DimensionReading:
    return DimensionReading(
        id=reading_id,
        evidence=EvidenceRegion(
            dataset_id="association-fixture-v1",
            page_number=1,
            image_sha256=IMAGE_DIGEST,
            bbox=bbox,
        ),
        raw_text="10,00 m",
        value_si=Decimal("10.00"),
        unit=UnitCode.METRE,
        kind=MeasurementKind.WIDTH,
        written_decimals=2,
        target_hint="cota de folha",
        target_entity_label=entity_label,
        extractor="fixture",
        extractor_version="v1",
        status=ReadingStatus.PROPOSED,
    )


def _line(proposal_id: str, *, y: float, quality: float | None = 0.9) -> VisionProposal:
    return VisionProposal(
        id=proposal_id,
        kind="line",
        geometry=PixelLine(start=PixelPoint(x=0, y=y), end=PixelPoint(x=100, y=y)),
        algorithm="fixture",
        quality_score=quality,
    )


def _far_line(proposal_id: str, *, y: float, quality: float | None = 0.9) -> VisionProposal:
    return VisionProposal(
        id=proposal_id,
        kind="line",
        geometry=PixelLine(start=PixelPoint(x=900, y=y), end=PixelPoint(x=1000, y=y)),
        algorithm="fixture",
        quality_score=quality,
    )


def _balloon_packet(
    *, balloon_label: str | None = "B", loose_label: str | None = "E"
) -> ReviewPacket:
    return ReviewPacket(
        dataset_id="association-fixture-v1",
        page_number=1,
        image_sha256=IMAGE_DIGEST,
        readings=[
            _reading(COTA_VIZINHA, bbox=PixelBox(left=45, top=10, right=55, bottom=20)),
            _reading(
                COTA_BALAO,
                bbox=PixelBox(left=45, top=40, right=55, bottom=50),
                entity_label=balloon_label,
            ),
            _reading(
                COTA_SOLTA,
                bbox=PixelBox(left=500, top=500, right=510, bottom=510),
                entity_label=loose_label,
            ),
        ],
        safety_notes=["fixture", "revisão humana obrigatória"],
    )


def _balloon_proposals(*, grade_c_quality: float | None = 0.9) -> VisionProposalSet:
    return VisionProposalSet(
        dataset_id="association-fixture-v1",
        page_number=1,
        image_sha256=IMAGE_DIGEST,
        image_width_px=1000,
        image_height_px=1000,
        configured_limits={"line": 10, "circle": 10, "contour": 10},
        limit_reached=[],
        proposals=[
            _line(LINHA_VIZINHA, y=15),
            VisionProposal(
                id=CIRCULO_VIZINHO,
                kind="circle",
                geometry=PixelCircle(center=PixelPoint(x=80, y=80), radius=10),
                algorithm="fixture",
                quality_score=0.99,
            ),
            _far_line(GRADE_B_TRECHO_1, y=900),
            _far_line(GRADE_B_TRECHO_2, y=950),
            _line(GRADE_C, y=990, quality=grade_c_quality),
        ],
        safety_notes=["fixture", "unresolved", "non-exportable"],
    )


def _identity_pairs(associations: AssociationSet) -> list[tuple[str, str]]:
    return [
        (candidate.reading_id, candidate.proposal_id)
        for candidate in associations.candidates
        if candidate.relation == "element_identity"
    ]


def _proximity(associations: AssociationSet) -> list[dict[str, Any]]:
    return [
        candidate.model_dump(mode="json")
        for candidate in associations.candidates
        if candidate.relation != "element_identity"
    ]


def _declaracao(
    element_ref: str,
    *,
    label: str | None,
    proposal_ids: list[str],
    status: str = "active",
) -> dict[str, Any]:
    """A linha como a revisão a grava (`element_declarations_json`), inclusive o rastro."""
    return {
        "element_ref": element_ref,
        "label": label,
        "proposal_ids": proposal_ids,
        "status": status,
        "declared_by": "reviewer",
        "declared_role": "engineer",
        "declared_at": "2026-09-04T20:00:00+00:00",
    }


GRADE_B = _declaracao("EL-001", label="B", proposal_ids=[GRADE_B_TRECHO_1, GRADE_B_TRECHO_2])


def test_declarado_o_elemento_a_cota_balao_ganha_candidata_de_cada_proposta_dele() -> None:
    """Critério 1: DUAS candidatas novas, ALÉM das de proximidade — nunca no lugar delas."""
    packet = _balloon_packet()
    proposals = _balloon_proposals()
    antes = associate_readings(packet, proposals)

    depois = rederive_element_identity_candidates(
        packet=packet,
        proposals=proposals,
        associations=antes,
        identities=active_element_identities([GRADE_B]),
    )

    assert _identity_pairs(antes) == []
    assert _identity_pairs(depois) == [
        (COTA_BALAO, GRADE_B_TRECHO_1),
        (COTA_BALAO, GRADE_B_TRECHO_2),
    ]
    # As candidatas de proximidade saem intactas, com a pontuação que já tinham: nada foi
    # recalculado, reordenado nem substituído.
    assert _proximity(depois) == _proximity(antes)
    assert depois.candidates[: len(antes.candidates)] == antes.candidates


def test_a_candidata_por_identidade_e_observacional_e_carrega_a_distancia_real() -> None:
    packet = _balloon_packet()
    proposals = _balloon_proposals()

    depois = rederive_element_identity_candidates(
        packet=packet,
        proposals=proposals,
        associations=associate_readings(packet, proposals),
        identities=active_element_identities([GRADE_B]),
    )

    candidata = next(c for c in depois.candidates if c.relation == "element_identity")
    assert candidata.precision == "unresolved"
    assert candidata.export is False
    # O funil alcança 254,5 px (18% da diagonal de 1000x1000); o elemento está a ~1205 px.
    assert candidata.pixel_distance > 1200
    assert candidata.proximity_score == 0.0
    # O score da F-029 mede proximidade e margem: ele nada sabe de identidade declarada, e
    # fica neutro para que nenhum corte automático alcance esta candidata.
    assert candidata.association_confidence == 0.0
    assert candidata.visual_quality_score == 0.9
    assert candidata.proposal_kind == "line"


def test_hint_que_nao_casa_com_nada_devolve_o_conjunto_de_entrada_intocado() -> None:
    """Critério 2: sem casamento, o MESMO objeto volta — e o JSON persistido sai verbatim."""
    packet = _balloon_packet(balloon_label="Z")
    proposals = _balloon_proposals()
    antes = associate_readings(packet, proposals)

    depois = rederive_element_identity_candidates(
        packet=packet,
        proposals=proposals,
        associations=antes,
        identities=active_element_identities([GRADE_B]),
    )

    assert depois is antes


def test_sem_declaracao_nenhuma_o_conjunto_volta_intocado() -> None:
    packet = _balloon_packet()
    proposals = _balloon_proposals()
    antes = associate_readings(packet, proposals)

    assert (
        rederive_element_identity_candidates(
            packet=packet, proposals=proposals, associations=antes, identities=[]
        )
        is antes
    )


def test_par_que_ja_e_candidato_por_proximidade_nao_ganha_duplicata() -> None:
    """A leitura cujo vizinho É o elemento declarado continua com uma linha só."""
    packet = _balloon_packet()
    proposals = _balloon_proposals()
    antes = associate_readings(packet, proposals)
    vizinhos = _declaracao(
        "EL-009", label="B", proposal_ids=[LINHA_VIZINHA, CIRCULO_VIZINHO, GRADE_B_TRECHO_1]
    )

    depois = rederive_element_identity_candidates(
        packet=packet,
        proposals=proposals,
        associations=antes,
        identities=active_element_identities([vizinhos]),
    )

    pares_antes = {(c.reading_id, c.proposal_id) for c in antes.candidates}
    assert (COTA_BALAO, LINHA_VIZINHA) in pares_antes
    assert (COTA_BALAO, CIRCULO_VIZINHO) in pares_antes
    # Só o trecho que ainda não era candidato desta leitura entra.
    assert _identity_pairs(depois) == [(COTA_BALAO, GRADE_B_TRECHO_1)]
    assert len(depois.candidates) == len(antes.candidates) + 1


def test_reconstruir_duas_vezes_da_exatamente_o_mesmo_conjunto() -> None:
    """Idempotência: é o que permite chamar a reconstrução em TODO ato, sem drift."""
    packet = _balloon_packet()
    proposals = _balloon_proposals()
    identities = active_element_identities([GRADE_B])
    uma_vez = rederive_element_identity_candidates(
        packet=packet,
        proposals=proposals,
        associations=associate_readings(packet, proposals),
        identities=identities,
    )

    duas_vezes = rederive_element_identity_candidates(
        packet=packet, proposals=proposals, associations=uma_vez, identities=identities
    )

    assert duas_vezes is uma_vez


def test_revogar_o_elemento_devolve_o_conjunto_ao_estado_anterior() -> None:
    """Critério 4, primeira metade: candidata por identidade não confirmada some."""
    packet = _balloon_packet()
    proposals = _balloon_proposals()
    antes = associate_readings(packet, proposals)
    com_identidade = rederive_element_identity_candidates(
        packet=packet,
        proposals=proposals,
        associations=antes,
        identities=active_element_identities([GRADE_B]),
    )

    revogado = rederive_element_identity_candidates(
        packet=packet,
        proposals=proposals,
        associations=com_identidade,
        identities=active_element_identities(
            [{**GRADE_B, "status": "revoked", "revoked_role": "engineer"}]
        ),
    )

    assert revogado.model_dump(mode="json") == antes.model_dump(mode="json")


def test_revogar_nao_tira_a_candidata_que_sustenta_associacao_confirmada() -> None:
    """Critério 4, segunda metade — a leitura do DAP aprovado.

    Revogar não desfaz o que uma pessoa confirmou. Tirar a candidata e deixar a associação
    seria o desfazer adiado: a próxima retificação daquela leitura bateria no portão ("a
    associação selecionada não pertence à leitura") e a decisão humana morreria sozinha.
    """
    packet = _balloon_packet()
    proposals = _balloon_proposals()
    com_identidade = rederive_element_identity_candidates(
        packet=packet,
        proposals=proposals,
        associations=associate_readings(packet, proposals),
        identities=active_element_identities([GRADE_B]),
    )

    revogado = rederive_element_identity_candidates(
        packet=packet,
        proposals=proposals,
        associations=com_identidade,
        identities=[],
        confirmed_associations={COTA_BALAO: GRADE_B_TRECHO_1},
    )

    assert _identity_pairs(revogado) == [(COTA_BALAO, GRADE_B_TRECHO_1)]


def test_corrigir_o_hint_da_leitura_recunha_as_candidatas_dela() -> None:
    """Critério 5: o "B" que o modelo leu errado, corrigido para "C", troca de elemento."""
    proposals = _balloon_proposals()
    identities = active_element_identities(
        [GRADE_B, _declaracao("EL-002", label="C", proposal_ids=[GRADE_C])]
    )
    como_lido = _balloon_packet(balloon_label="B")
    com_b = rederive_element_identity_candidates(
        packet=como_lido,
        proposals=proposals,
        associations=associate_readings(como_lido, proposals),
        identities=identities,
    )

    corrigido = _balloon_packet(balloon_label="C")
    com_c = rederive_element_identity_candidates(
        packet=corrigido, proposals=proposals, associations=com_b, identities=identities
    )

    assert _identity_pairs(com_b) == [
        (COTA_BALAO, GRADE_B_TRECHO_1),
        (COTA_BALAO, GRADE_B_TRECHO_2),
    ]
    assert _identity_pairs(com_c) == [(COTA_BALAO, GRADE_C)]


def test_dois_elementos_com_o_mesmo_hint_dao_candidata_dos_dois() -> None:
    """ "grade B" e "alambrado B" casam os dois com o balão "B": quem escolhe é o humano.

    Nenhum critério secreto elege um vencedor — a candidata é observação, e desempatar em
    silêncio seria a inferência que o ADR-0063 recusa.
    """
    packet = _balloon_packet()
    proposals = _balloon_proposals()

    depois = rederive_element_identity_candidates(
        packet=packet,
        proposals=proposals,
        associations=associate_readings(packet, proposals),
        identities=active_element_identities(
            [
                _declaracao("EL-001", label="grade B", proposal_ids=[GRADE_B_TRECHO_1]),
                _declaracao("EL-002", label="alambrado B", proposal_ids=[GRADE_B_TRECHO_2]),
            ]
        ),
    )

    assert _identity_pairs(depois) == [
        (COTA_BALAO, GRADE_B_TRECHO_1),
        (COTA_BALAO, GRADE_B_TRECHO_2),
    ]


def test_leitura_sem_vizinho_sai_e_volta_da_lista_de_nao_associadas() -> None:
    packet = _balloon_packet(loose_label="B")
    proposals = _balloon_proposals()
    antes = associate_readings(packet, proposals)
    assert antes.unassociated_reading_ids == [COTA_SOLTA]

    com_identidade = rederive_element_identity_candidates(
        packet=packet,
        proposals=proposals,
        associations=antes,
        identities=active_element_identities([GRADE_B]),
    )
    revogado = rederive_element_identity_candidates(
        packet=packet, proposals=proposals, associations=com_identidade, identities=[]
    )

    assert com_identidade.unassociated_reading_ids == []
    assert revogado.unassociated_reading_ids == [COTA_SOLTA]


def test_declaracao_sem_rotulo_ou_revogada_nao_participa_do_casamento() -> None:
    rows = [
        _declaracao("EL-001", label=None, proposal_ids=[GRADE_B_TRECHO_1]),
        _declaracao("EL-002", label="   ", proposal_ids=[GRADE_B_TRECHO_2]),
        _declaracao("EL-003", label="B", proposal_ids=[GRADE_C], status="revoked"),
        GRADE_B,
    ]

    assert active_element_identities(rows) == [
        ElementIdentity(
            element_ref="EL-001",
            label="B",
            proposal_ids=(GRADE_B_TRECHO_1, GRADE_B_TRECHO_2),
        )
    ]


def test_proposta_fora_do_snapshot_nao_vira_candidata() -> None:
    packet = _balloon_packet()
    proposals = _balloon_proposals()

    depois = rederive_element_identity_candidates(
        packet=packet,
        proposals=proposals,
        associations=associate_readings(packet, proposals),
        identities=active_element_identities(
            [_declaracao("EL-001", label="B", proposal_ids=["vp_ffffffffffffffff"])]
        ),
    )

    assert _identity_pairs(depois) == []


def test_proposta_corrigida_por_pessoa_entra_sem_pontuacao_de_detector() -> None:
    """Forma humana não tem `quality_score` (ADR-0050 D2): o campo obrigatório vira 0.0."""
    packet = _balloon_packet(balloon_label="C")
    proposals = _balloon_proposals(grade_c_quality=None)

    depois = rederive_element_identity_candidates(
        packet=packet,
        proposals=proposals,
        associations=associate_readings(packet, proposals),
        identities=active_element_identities(
            [_declaracao("EL-002", label="C", proposal_ids=[GRADE_C])]
        ),
    )

    candidata = next(c for c in depois.candidates if c.relation == "element_identity")
    assert candidata.visual_quality_score == 0.0


def test_conjunto_legado_sem_candidata_de_identidade_valida_com_o_literal_estendido() -> None:
    """Risco nomeado do contrato: `associations_json` gravado antes da T4 continua abrindo."""
    legado = {
        "dataset_id": "association-fixture-v1",
        "page_number": 1,
        "image_sha256": IMAGE_DIGEST,
        "candidates": [
            {
                "reading_id": COTA_VIZINHA,
                "proposal_id": LINHA_VIZINHA,
                "proposal_kind": "line",
                "relation": "nearest_geometry",
                "pixel_distance": 0.0,
                "proximity_score": 1.0,
                "visual_quality_score": 0.9,
            }
        ],
        "unassociated_reading_ids": [],
        "safety_notes": ["pixels", "não confirma", "não exporta"],
    }

    associations = AssociationSet.model_validate(legado)

    assert associations.candidates[0].relation == "nearest_geometry"
    assert associations.associator_version == "pixel-proximity-associator-v1"
