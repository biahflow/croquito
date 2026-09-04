"""F-051 T3: o produtor determinístico de sugestões assistidas na revisão (ADR-0063).

O que estes testes protegem, em uma frase cada: o mesmo `VisionProposalSet` produz sempre
as mesmas sugestões, na mesma ordem; proposta sem rótulo (ou com rótulo vazio) nunca é
sugerida; proposta já coberta por declaração ativa nunca é sugerida; um grupo de uma única
proposta rotulada é sugestão válida; um rótulo ERRADO de propósito ainda é sugerido —
sugerir não é confirmar, quem decide é o revisor; e sem rótulo nenhum a lista vem vazia.
"""

from __future__ import annotations

from croquito_core.ids import new_uuid7
from croquito_worker.review_element_suggestions import suggest_review_elements
from croquito_worker.vision import PixelLine, PixelPoint, VisionProposal, VisionProposalSet

JOB_ID = new_uuid7()


def _proposal(id_: str, *, label: str | None) -> VisionProposal:
    return VisionProposal(
        id=id_,
        kind="line",
        geometry=PixelLine(start=PixelPoint(x=0, y=0), end=PixelPoint(x=10, y=0)),
        algorithm="fixture",
        quality_score=0.9,
        label=label,
    )


def _set(proposals: list[VisionProposal]) -> VisionProposalSet:
    return VisionProposalSet(
        dataset_id="fixture",
        page_number=1,
        image_sha256="a" * 64,
        image_width_px=100,
        image_height_px=100,
        configured_limits={"line": 80, "circle": 16, "contour": 16},
        limit_reached=[],
        proposals=proposals,
        safety_notes=["fixture", "pixels", "não exportável"],
    )


def test_mesmo_conjunto_produz_sempre_as_mesmas_sugestoes_na_mesma_ordem() -> None:
    proposals = _set(
        [
            _proposal("vp_1111111111111111", label="C"),
            _proposal("vp_2222222222222222", label="B"),
            _proposal("vp_3333333333333333", label="B"),
        ]
    )

    first = suggest_review_elements(proposals, job_id=JOB_ID)
    second = suggest_review_elements(proposals, job_id=JOB_ID)

    assert first == second
    assert [suggestion.label for suggestion in first] == ["C", "B"]
    assert first[0].proposal_ids == ("vp_1111111111111111",)
    assert first[1].proposal_ids == ("vp_2222222222222222", "vp_3333333333333333")
    assert all(suggestion.suggestion_id.startswith("els_") for suggestion in first)


def test_proposta_sem_rotulo_nunca_e_sugerida() -> None:
    proposals = _set(
        [
            _proposal("vp_1111111111111111", label=None),
            _proposal("vp_2222222222222222", label=""),
        ]
    )

    assert suggest_review_elements(proposals, job_id=JOB_ID) == []


def test_proposta_ja_coberta_por_declaracao_ativa_nunca_e_sugerida() -> None:
    proposals = _set(
        [
            _proposal("vp_1111111111111111", label="B"),
            _proposal("vp_2222222222222222", label="B"),
        ]
    )

    suggestions = suggest_review_elements(
        proposals, job_id=JOB_ID, declared_proposal_ids={"vp_1111111111111111"}
    )

    assert len(suggestions) == 1
    assert suggestions[0].proposal_ids == ("vp_2222222222222222",)


def test_todas_as_propostas_do_rotulo_ja_declaradas_some_o_grupo_inteiro() -> None:
    proposals = _set([_proposal("vp_1111111111111111", label="B")])

    suggestions = suggest_review_elements(
        proposals, job_id=JOB_ID, declared_proposal_ids={"vp_1111111111111111"}
    )

    assert suggestions == []


def test_grupo_de_uma_unica_proposta_e_sugestao_valida() -> None:
    proposals = _set([_proposal("vp_1111111111111111", label="poste")])

    suggestions = suggest_review_elements(proposals, job_id=JOB_ID)

    assert len(suggestions) == 1
    assert suggestions[0].label == "poste"
    assert suggestions[0].proposal_ids == ("vp_1111111111111111",)


def test_rotulo_errado_de_proposito_ainda_e_sugerido_pois_sugerir_nao_e_confirmar() -> None:
    """A «grade B» é, na verdade, o balão C espelhado — o produtor não sabe disso.

    Sugerir é assistido, não autoridade: o produtor devolve o rótulo do jeito que o modelo
    escreveu, errado e tudo. É o revisor quem recusa (rota de recusa, testada em
    `tests/api/test_review_element_suggestions.py`), nunca o produtor que filtra por conta
    própria.
    """
    proposals = _set([_proposal("vp_1111111111111111", label="B")])

    suggestions = suggest_review_elements(proposals, job_id=JOB_ID)

    assert len(suggestions) == 1
    assert suggestions[0].label == "B"


def test_sem_rotulo_nenhum_a_lista_vem_vazia() -> None:
    proposals = _set(
        [
            _proposal("vp_1111111111111111", label=None),
            _proposal("vp_2222222222222222", label=None),
        ]
    )

    assert suggest_review_elements(proposals, job_id=JOB_ID) == []


def test_id_da_sugestao_depende_do_job_alem_do_conjunto_de_propostas() -> None:
    """`VisionProposal.id` só é único DENTRO de um job; o id da sugestão inclui o job."""
    proposals = _set([_proposal("vp_1111111111111111", label="B")])
    other_job = new_uuid7()

    first = suggest_review_elements(proposals, job_id=JOB_ID)[0]
    second = suggest_review_elements(proposals, job_id=other_job)[0]

    assert first.suggestion_id != second.suggestion_id
