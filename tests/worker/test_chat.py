"""Contexto e conferência de referências de um turno de conversa da revisão.

As duas funções são puras: o que o modelo recebe é sempre o mesmo para o mesmo turno, e o
que ele devolve só é aceito quando cada id citado existe no snapshot da revisão-base.
"""

from __future__ import annotations

import json

from croquitodxf_worker.chat import (
    CHAT_CONTEXT_VERSION,
    build_chat_text_payload,
    chat_unknown_references,
    note_target_proposal_id,
)
from croquitodxf_worker.providers import (
    CHAT_NOTE_TARGET_PATTERN,
    ReviewChatOutput,
)
from croquitodxf_worker.tracing import GENERAL_NOTE_TARGET, LEGEND_NOTE_PREFIX
from tests.bundles import (
    HEIGHT_PROPOSAL_ID,
    HEIGHT_READING_ID,
    WIDTH_PROPOSAL_ID,
    WIDTH_READING_ID,
    build_packet,
    build_proposals,
)

DATASET_ID = "synthetic-chat-v1"
DIGEST = "e" * 64


def _packet_readings() -> list:  # type: ignore[type-arg]
    return build_packet(dataset_id=DATASET_ID, digest=DIGEST).readings


def _answer(**overrides: object) -> ReviewChatOutput:
    payload: dict[str, object] = {
        "answer_kind": "answer",
        "answer_text": "Confira o recorte da evidência antes de confirmar.",
        "proposed_acts": [],
    }
    payload.update(overrides)
    return ReviewChatOutput.model_validate({"task": "review-chat", **payload})


def test_payload_carries_the_raw_text_and_no_identity() -> None:
    readings = _packet_readings()
    proposals = build_proposals(dataset_id=DATASET_ID, digest=DIGEST).proposals

    payload = json.loads(
        build_chat_text_payload(
            question="Essa cota mede a borda do campo?",
            readings=[readings[0]],
            proposals=[proposals[0]],
        )
    )

    assert payload["context_version"] == CHAT_CONTEXT_VERSION
    assert payload["question"] == "Essa cota mede a borda do campo?"
    # `raw_text` literal: normalizar aqui faria o modelo conversar sobre um número que
    # ninguém escreveu na folha.
    assert payload["readings"] == [
        {
            "id": WIDTH_READING_ID,
            "raw_text": "25.90 m",
            "kind": "width",
            "status": "proposed",
            "unit": "m",
        }
    ]
    assert payload["proposals"] == [{"id": WIDTH_PROPOSAL_ID, "kind": "line", "label": None}]
    # Nada de identidade nem de storage viaja com a evidência.
    serialised = json.dumps(payload, ensure_ascii=False)
    for forbidden in ("tenant", "job", "http", "reviewer", "decision"):
        assert forbidden not in serialised.lower()


def test_payload_is_deterministic_and_deduplicates_anchors() -> None:
    readings = _packet_readings()

    first = build_chat_text_payload(question="q", readings=[readings[0]], proposals=[])
    repeated = build_chat_text_payload(
        question="q", readings=[readings[0], readings[0]], proposals=[]
    )
    other_order = build_chat_text_payload(
        question="q", readings=[readings[1], readings[0]], proposals=[]
    )

    assert first == build_chat_text_payload(question="q", readings=[readings[0]], proposals=[])
    # Duplicata some; a ordem declarada pelo profissional é preservada, porque é ela que
    # carrega a ênfase da pergunta.
    assert repeated == first
    assert json.loads(other_order)["readings"][0]["id"] == HEIGHT_READING_ID


def test_note_target_resolution_matches_the_trace_vocabulary() -> None:
    assert note_target_proposal_id(GENERAL_NOTE_TARGET) is None
    assert note_target_proposal_id(f"{LEGEND_NOTE_PREFIX}{WIDTH_PROPOSAL_ID}") == WIDTH_PROPOSAL_ID
    assert note_target_proposal_id(f"{WIDTH_PROPOSAL_ID}#v") == WIDTH_PROPOSAL_ID
    # O padrão do contrato de provider aceita exatamente as formas que o traçado declara.
    assert GENERAL_NOTE_TARGET in CHAT_NOTE_TARGET_PATTERN
    assert LEGEND_NOTE_PREFIX in CHAT_NOTE_TARGET_PATTERN


def test_unknown_references_are_reported_for_every_act_shape() -> None:
    answer = _answer(
        proposed_acts=[
            {
                "act": "trace_association",
                "reading_id": WIDTH_READING_ID,
                "target": [WIDTH_PROPOSAL_ID, "vp_9999999999999999"],
            },
            {
                "act": "keep_apart",
                "first": HEIGHT_PROPOSAL_ID,
                "second": "vp_8888888888888888",
            },
            {
                "act": "note_association",
                "reading_id": "rd_9999999999999999",
                "target": f"{LEGEND_NOTE_PREFIX}{WIDTH_PROPOSAL_ID}",
            },
        ]
    )

    unknown = chat_unknown_references(
        answer,
        reading_ids={WIDTH_READING_ID, HEIGHT_READING_ID},
        proposal_ids={WIDTH_PROPOSAL_ID, HEIGHT_PROPOSAL_ID},
    )

    assert unknown == ["rd_9999999999999999", "vp_8888888888888888", "vp_9999999999999999"]


def test_known_references_and_acts_without_ids_are_accepted() -> None:
    answer = _answer(
        proposed_acts=[
            {
                "act": "reading_decision",
                "reading_id": WIDTH_READING_ID,
                "action": "confirm",
                "association_proposal_id": WIDTH_PROPOSAL_ID,
                "justification_draft": "Cota conferida na evidência.",
            },
            {"act": "note_association", "reading_id": HEIGHT_READING_ID, "target": "carimbo"},
            {"act": "pending_note", "text": "Falta a cota do vão do portão."},
        ]
    )

    assert (
        chat_unknown_references(
            answer,
            reading_ids={WIDTH_READING_ID, HEIGHT_READING_ID},
            proposal_ids={WIDTH_PROPOSAL_ID},
        )
        == []
    )
