"""O estágio de refino pago: janela de candidatos, fatiamento por payload e lineage.

A shortlist publicada tem 15 candidatos por item e o contrato de saída do prompt
(`ScoItemRefinementOutput.ranked_codes`) aceita 10, então o refino manda uma JANELA por
item; e como 15 itens com janela de 10 não cabem num `text_payload` só, ele fatia os itens
em lotes — uma chamada paga por lote. Os dois números são medidos contra os contratos que
os originam, e o fatiamento é verificado pelo que ele NÃO pode mudar: a shortlist
publicada.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from croquito_valuation.assignment import (
    CodeSuggestionSet,
    suggest_codes,
)
from croquito_valuation.errors import ValuationValidationError
from croquito_valuation.models import (
    PriceCatalog,
    PriceCatalogEntry,
    ReviewerDecision,
)
from croquito_valuation.takeoff import (
    PlateBox,
    PlateEvidence,
    TakeoffItem,
    TakeoffItemStatus,
    TakeoffPacket,
)
from croquito_worker.providers import (
    ProviderExecution,
    ProviderName,
    ProviderRequest,
    ProviderUsage,
    ScoItemRefinementOutput,
    ScoRefinementOutput,
)
from croquito_worker.valuation.sco_suggestion import (
    TEXT_PAYLOAD_MAX_LENGTH,
    TRANSMITTED_CANDIDATE_WINDOW,
    build_refinement_payload,
    refine_code_suggestions,
)

_PLATE_ID = "praca-sintetica-refino-prancha-01"
_DIGEST = "a" * 64
_PDF_DIGEST = "b" * 64
_CATALOG_DIGEST = "c" * 64
_MODEL_ID = "fixture-sco-rerank-lote-v1"
_CALL_COST = Decimal("0.0300")

# Descrição no comprimento em que o corte de transmissão a deixa: é ela que faz o payload
# de uma prancha real não caber numa chamada só.
_DESCRIPTION_LENGTH = 400


def _evidence() -> PlateEvidence:
    return PlateEvidence(
        plate_id=_PLATE_ID,
        page_number=1,
        image_sha256=_DIGEST,
        bbox=PlateBox(left=10, top=10, right=500, bottom=40),
    )


def _item(index: int) -> TakeoffItem:
    label = f"ALAMBRADO GALVANIZADO TIPO {index:02d}"
    return TakeoffItem(
        id=f"ti_{index:016d}",
        evidence=_evidence(),
        raw_text=f"{label} 10.00 m",
        label=label,
        quantity=Decimal("10.00"),
        unit="m",
        source="legend_extraction",
        extractor="legend-extractor-sintetico",
        extractor_version="1.0.0",
        status=TakeoffItemStatus.CONFIRMED,
        decision=ReviewerDecision(
            decision_id="vd_0123456789abcdef",
            action="confirm",
            reviewer_id="orcamentista-sintetico",
            reviewer_role="orcamentista",
            decided_at=datetime(2026, 2, 1, 12, 0, tzinfo=UTC),
        ),
    )


def _catalog() -> PriceCatalog:
    """Vinte códigos elegíveis com descrição longa — a shortlist corta em 15 por item."""
    entries = []
    for index in range(1, 21):
        head = f"ALAMBRADO GALVANIZADO TIPO {index:02d} "
        entries.append(
            PriceCatalogEntry(
                code=f"CE0410{index:04d}(/)",
                description=head + "X" * (_DESCRIPTION_LENGTH - len(head)),
                unit="m",
                unit_price=Decimal("50.00"),
                family_code="CE",
                family_name="CERCAS SINTETICAS",
                subgroup_code="CE0410",
                subgroup_name="ALAMBRADOS SINTETICOS",
            )
        )
    return PriceCatalog(
        source_label="CATALOGO SINTETICO",
        reference_month="2026-01",
        source_sha256=_CATALOG_DIGEST,
        entries=entries,
    )


def _packet(item_count: int) -> TakeoffPacket:
    return TakeoffPacket(
        plate_id=_PLATE_ID,
        page_number=1,
        image_sha256=_DIGEST,
        source_pdf_sha256=_PDF_DIGEST,
        items=[_item(index) for index in range(1, item_count + 1)],
        safety_notes=[
            "Extração automática da legenda; quantidade não confirmada.",
            "Decisão do orçamentista obrigatória antes de qualquer boletim.",
            "Sugestão é observação; confirmação de código é ato humano.",
        ],
    )


def _plate(item_count: int) -> tuple[TakeoffPacket, CodeSuggestionSet]:
    packet = _packet(item_count)
    suggestions = suggest_codes(packet, _catalog())
    assert len(suggestions.suggestions) == item_count
    assert all(len(item.candidates) == 15 for item in suggestions.suggestions)
    return packet, suggestions


def _window(suggestions: CodeSuggestionSet, item_id: str) -> list[str]:
    suggestion = next(item for item in suggestions.suggestions if item.item_id == item_id)
    return [c.code for c in suggestion.candidates[:TRANSMITTED_CANDIDATE_WINDOW]]


def _published(suggestions: CodeSuggestionSet) -> dict[str, list[str]]:
    return {
        suggestion.item_id: [candidate.code for candidate in suggestion.candidates]
        for suggestion in suggestions.suggestions
    }


@dataclass(slots=True)
class _ReversingAdapter:
    """Provider offline que inverte a janela dos itens QUE O LOTE PERGUNTOU, e só eles.

    Ele lê o payload como um provider real leria: quem responde sobre item que não foi
    enviado está inventando resposta, e o estágio recusa isso. Guarda cada payload para que
    o teste possa medir o fatiamento sem espiar o interior do módulo.
    """

    payloads: list[str] = field(default_factory=list)

    def execute(self, request: ProviderRequest) -> ProviderExecution:
        self.payloads.append(request.text_payload or "")
        payload = json.loads(request.text_payload or '{"items":[]}')
        return ProviderExecution(
            provider=ProviderName.ANTHROPIC,
            model_id=_MODEL_ID,
            prompt=request.prompt,
            input_digest=request.image_sha256,
            latency_ms=11,
            usage=ProviderUsage(
                input_tokens=1000, output_tokens=200, estimated_cost_usd=_CALL_COST
            ),
            output=ScoRefinementOutput(
                items=[
                    ScoItemRefinementOutput(
                        item_id=str(entry["item_id"]),
                        ranked_codes=list(reversed([str(c["code"]) for c in entry["candidates"]])),
                        rationale="fixture de teste: janela invertida",
                    )
                    for entry in payload["items"]
                ]
            ),
        )


@dataclass(slots=True)
class _OutOfBatchAdapter:
    """Provider que responde sobre um item que não estava no lote — recusa fechada."""

    intruder_id: str

    def execute(self, request: ProviderRequest) -> ProviderExecution:
        return ProviderExecution(
            provider=ProviderName.ANTHROPIC,
            model_id=_MODEL_ID,
            prompt=request.prompt,
            input_digest=request.image_sha256,
            latency_ms=11,
            output=ScoRefinementOutput(
                items=[
                    ScoItemRefinementOutput(
                        item_id=self.intruder_id,
                        ranked_codes=["CE04100001(/)"],
                        rationale="fixture inválida: item fora do lote",
                    )
                ]
            ),
        )


# --------------------------------------------------------------------------------------
# Os dois tetos, medidos contra os contratos que os originam
# --------------------------------------------------------------------------------------


def test_the_window_never_exceeds_what_the_prompt_contract_can_answer() -> None:
    """A janela acompanha o `max_length` de `ranked_codes`; se o contrato subir, olha-se lá."""
    ranked_codes = ScoItemRefinementOutput.model_fields["ranked_codes"]
    limits = [
        constraint.max_length
        for constraint in ranked_codes.metadata
        if getattr(constraint, "max_length", None) is not None
    ]

    assert limits == [TRANSMITTED_CANDIDATE_WINDOW]


def test_the_payload_ceiling_mirrors_the_provider_request_contract() -> None:
    text_payload = ProviderRequest.model_fields["text_payload"]
    limits = [
        constraint.max_length
        for constraint in text_payload.metadata
        if getattr(constraint, "max_length", None) is not None
    ]

    assert limits == [TEXT_PAYLOAD_MAX_LENGTH]


# --------------------------------------------------------------------------------------
# Janela: só o prefixo viaja
# --------------------------------------------------------------------------------------


def test_the_payload_carries_only_the_window_of_each_item() -> None:
    """A cauda da shortlist não é transmitida: o provider não teria como devolvê-la."""
    packet, suggestions = _plate(1)

    payload = json.loads(build_refinement_payload(packet, suggestions))

    entry = payload["items"][0]
    assert [c["code"] for c in entry["candidates"]] == _window(suggestions, entry["item_id"])
    assert len(entry["candidates"]) == TRANSMITTED_CANDIDATE_WINDOW


def test_the_refinement_reorders_the_window_and_keeps_the_tail_published() -> None:
    packet, suggestions = _plate(2)

    result = refine_code_suggestions(packet, suggestions, _ReversingAdapter())

    before, after = _published(suggestions), _published(result.suggestions)
    for item_id, codes in before.items():
        head, tail = codes[:TRANSMITTED_CANDIDATE_WINDOW], codes[TRANSMITTED_CANDIDATE_WINDOW:]
        assert after[item_id] == [*reversed(head), *tail]
        assert sorted(after[item_id]) == sorted(codes)


# --------------------------------------------------------------------------------------
# Fatiamento: mais chamadas pagas, mesmo resultado
# --------------------------------------------------------------------------------------


def test_a_real_sized_plate_is_refined_in_several_paid_calls() -> None:
    """Quinze itens com janela de 10 não cabem num payload só; o custo sobe e é declarado."""
    packet, suggestions = _plate(15)
    adapter = _ReversingAdapter()

    result = refine_code_suggestions(packet, suggestions, adapter)

    assert result.call_count > 1
    assert len(adapter.payloads) == result.call_count
    assert all(len(payload) <= TEXT_PAYLOAD_MAX_LENGTH for payload in adapter.payloads)
    # Cada item foi perguntado exatamente uma vez, e todos foram perguntados.
    asked = [
        str(entry["item_id"])
        for payload in adapter.payloads
        for entry in json.loads(payload)["items"]
    ]
    assert sorted(asked) == sorted(item.item_id for item in suggestions.suggestions)


def test_the_number_of_batches_does_not_change_the_published_shortlist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A divisão é detalhe de transporte: mudar o tamanho do lote não muda o artefato.

    A comparação é entre duas divisões diferentes da MESMA prancha, e não contra uma
    chamada única, porque uma chamada única para 15 itens é justamente o que o
    `ProviderRequest` recusa — foi esse estouro que motivou o fatiamento.
    """
    packet, suggestions = _plate(15)

    default_batches = refine_code_suggestions(packet, suggestions, _ReversingAdapter())
    assert default_batches.call_count > 1

    # Teto rebaixado o bastante para caber um item por chamada, e nenhum a mais.
    monkeypatch.setattr("croquito_worker.valuation.sco_suggestion.TEXT_PAYLOAD_MAX_LENGTH", 6000)
    one_per_call = refine_code_suggestions(packet, suggestions, _ReversingAdapter())

    assert one_per_call.call_count == len(suggestions.suggestions)
    assert one_per_call.call_count != default_batches.call_count
    assert _published(one_per_call.suggestions) == _published(default_batches.suggestions)
    assert one_per_call.suggestions.model_dump() == default_batches.suggestions.model_dump()


def test_an_item_that_does_not_fit_a_payload_by_itself_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cortar um item pela metade seria esconder candidato do modelo; recusa fechada."""
    packet, suggestions = _plate(2)
    monkeypatch.setattr("croquito_worker.valuation.sco_suggestion.TEXT_PAYLOAD_MAX_LENGTH", 100)

    with pytest.raises(ValuationValidationError) as raised:
        refine_code_suggestions(packet, suggestions, _ReversingAdapter())

    assert raised.value.code == "REFINEMENT_ITEM_TOO_LARGE"


def test_a_refinement_answering_about_an_item_outside_its_batch_is_refused() -> None:
    packet, suggestions = _plate(15)
    intruder = suggestions.suggestions[-1].item_id

    with pytest.raises(ValuationValidationError) as raised:
        refine_code_suggestions(packet, suggestions, _OutOfBatchAdapter(intruder_id=intruder))

    assert raised.value.code == "REFINEMENT_UNKNOWN_ITEM"


# --------------------------------------------------------------------------------------
# Lineage: quanto custou e quantas chamadas
# --------------------------------------------------------------------------------------


def test_the_result_declares_the_total_cost_and_the_number_of_paid_calls() -> None:
    """Custo de uma prancha fatiada é a soma dos lotes, não o do primeiro."""
    packet, suggestions = _plate(15)

    result = refine_code_suggestions(packet, suggestions, _ReversingAdapter())

    assert result.call_count == len(result.executions) > 1
    assert result.estimated_cost_usd == _CALL_COST * result.call_count


def test_the_lineage_digest_covers_the_whole_payload_not_the_first_batch() -> None:
    """O digest identifica a ENTRADA do estágio, e é estável se o tamanho do lote mudar."""
    packet, suggestions = _plate(15)
    adapter = _ReversingAdapter()

    result = refine_code_suggestions(packet, suggestions, adapter)

    lineage = result.suggestions.refinement
    assert lineage is not None
    expected = hashlib.sha256(
        build_refinement_payload(packet, suggestions).encode("utf-8")
    ).hexdigest()
    assert lineage.input_digest == expected
    assert lineage.input_digest != result.executions[0].input_digest
    assert lineage.model_id == _MODEL_ID


def test_with_a_single_batch_the_lineage_digest_is_the_digest_of_that_call() -> None:
    """Regressão do caminho de sempre: com um lote, o lineage é bit a bit o de antes."""
    packet, suggestions = _plate(1)

    result = refine_code_suggestions(packet, suggestions, _ReversingAdapter())

    lineage = result.suggestions.refinement
    assert lineage is not None
    assert result.call_count == 1
    assert lineage.input_digest == result.executions[0].input_digest


def test_a_plate_without_any_shortlist_still_pays_exactly_one_call() -> None:
    """Decisão preservada: conjunto sem item continua declarando que passou pelo refino.

    Um lote vazio parece desperdício, mas é o comportamento que sempre existiu — quem pediu
    `--refine-arm` pagou a chamada, e o artefato tem de dizer isso em vez de sair como
    shortlist determinística.
    """
    packet = _packet(1)
    suggestions = CodeSuggestionSet(
        plate_id=_PLATE_ID,
        page_number=1,
        image_sha256=_DIGEST,
        catalog_sha256=_CATALOG_DIGEST,
        suggestions=[],
        unmatched_item_ids=[item.id for item in packet.items],
        safety_notes=[
            "Sugestão é observação; confirmação de código é ato humano.",
            "Item sem candidato exige busca manual no catálogo.",
            "A ordem vem da via léxica e não mede preço.",
        ],
    )

    result = refine_code_suggestions(packet, suggestions, _ReversingAdapter())

    assert result.call_count == 1
    assert result.suggestions.refinement is not None
    assert result.suggestions.suggestions == []
