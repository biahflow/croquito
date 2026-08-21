"""Modo automático local: dupla chave, forma do ator-máquina e o que ele pode decidir.

O que estes testes protegem é o ADR-0041: ligar é ato declarado, o corte nunca tem
default, o sistema só confirma leitura que ninguém decidiu, e a decisão dele é
inconfundível com a de uma pessoa.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from croquito_core.models import MeasurementKind, UnitCode
from croquito_worker.association import AssociationCandidate, AssociationSet
from croquito_worker.association_confidence import CONFIDENCE_SCORE_VERSION
from croquito_worker.auto_association import (
    AUTO_ASSOCIATION_ENABLED_ENV,
    AUTO_ASSOCIATION_THRESHOLD_ENV,
    AutoAssociationConfigError,
    AutoAssociationMode,
    apply_auto_association,
    auto_association_mode,
    system_reviewer_id,
)
from croquito_worker.review import (
    DimensionReading,
    EvidenceRegion,
    HumanDecision,
    PixelBox,
    ReadingStatus,
    ReviewPacket,
)

DIGEST = "a" * 64

# Sem leitura confirmada não há cadeia nenhuma, então o sinal de cadeia fica neutro e a
# confiança de leitura da revisão 1 só depende do OCR e da presença de valor:
# corroborada = 0,85; sem braço de OCR = 0,65.
CORROBORATED_READING_CONFIDENCE = 0.85
NEUTRAL_READING_CONFIDENCE = 0.65


def _reading(
    index: int,
    *,
    value: str | None = "10.00",
    ocr_corroborated: bool | None = True,
    decision: HumanDecision | None = None,
    kind: MeasurementKind = MeasurementKind.WIDTH,
    annotation_suggested: bool = False,
) -> DimensionReading:
    """Leitura da fixture. `kind` e `annotation_suggested` mantêm o default do tier 1.

    Os dois parâmetros nasceram na T6 e não mexem em nenhum caso da T4: sem declaração,
    a leitura continua sendo a cota de planta `width` sem sinal de anotação que os testes
    do tier de dupla testemunha sempre usaram.
    """
    status = ReadingStatus.PROPOSED
    if decision is not None:
        status = ReadingStatus.CONFIRMED if decision.action == "confirm" else ReadingStatus.REJECTED
    return DimensionReading(
        id=f"rd_{index:016x}",
        evidence=EvidenceRegion(
            dataset_id="fixture-v1",
            page_number=1,
            image_sha256=DIGEST,
            bbox=PixelBox(left=index * 20, top=5, right=index * 20 + 20, bottom=15),
        ),
        raw_text=f"{value or '?'} m",
        value_si=Decimal(value) if value is not None else None,
        unit=UnitCode.METRE,
        kind=kind,
        written_decimals=2,
        target_hint="trecho",
        extractor="fixture",
        extractor_version="v1",
        annotation_suggested=annotation_suggested,
        ocr_corroborated=ocr_corroborated,
        status=status,
        decision=decision,
    )


def _packet(*readings: DimensionReading) -> ReviewPacket:
    return ReviewPacket(
        dataset_id="fixture-v1",
        page_number=1,
        image_sha256=DIGEST,
        readings=list(readings),
        safety_notes=["fixture", "revisão humana obrigatória"],
    )


def _candidate(reading_id: str, proposal_id: str, confidence: float) -> AssociationCandidate:
    return AssociationCandidate(
        reading_id=reading_id,
        proposal_id=proposal_id,
        proposal_kind="line",
        relation="nearest_geometry",
        pixel_distance=1.0,
        proximity_score=0.9,
        visual_quality_score=0.9,
        orientation_alignment=0.9,
        association_confidence=confidence,
    )


def _associations(*candidates: AssociationCandidate) -> AssociationSet:
    return AssociationSet(
        dataset_id="fixture-v1",
        page_number=1,
        image_sha256=DIGEST,
        candidates=list(candidates),
        unassociated_reading_ids=[],
        safety_notes=["pixels", "não confirma", "não exporta"],
    )


# --- dupla chave --------------------------------------------------------------------


def test_flag_ausente_deixa_o_modo_desligado() -> None:
    """Ausente é DESLIGADO — o oposto deliberado do braço OpenAI: ligar é ato declarado."""
    assert auto_association_mode({}) is None
    assert auto_association_mode({AUTO_ASSOCIATION_THRESHOLD_ENV: "0.7"}) is None
    assert auto_association_mode({AUTO_ASSOCIATION_ENABLED_ENV: "false"}) is None


def test_flag_ligada_sem_threshold_recusa_e_nao_ativa_o_modo() -> None:
    """Corte é escolha humana a partir da calibração; a falta dele nunca vira um default."""
    with pytest.raises(AutoAssociationConfigError) as refusal:
        auto_association_mode({AUTO_ASSOCIATION_ENABLED_ENV: "true"})

    assert AUTO_ASSOCIATION_THRESHOLD_ENV in str(refusal.value)


@pytest.mark.parametrize("raw", ["", "  ", "alto", "1.5", "-0.1", "0,7"])
def test_threshold_invalido_recusa_em_vez_de_escolher_um_numero(raw: str) -> None:
    with pytest.raises(AutoAssociationConfigError):
        auto_association_mode(
            {AUTO_ASSOCIATION_ENABLED_ENV: "true", AUTO_ASSOCIATION_THRESHOLD_ENV: raw}
        )


@pytest.mark.parametrize("raw", ["1", "yes", "sim", "0", "TRUE!"])
def test_valor_estranho_na_flag_e_erro_nunca_um_modo(raw: str) -> None:
    with pytest.raises(AutoAssociationConfigError):
        auto_association_mode({AUTO_ASSOCIATION_ENABLED_ENV: raw})


def test_flag_ligada_com_corte_explicito_liga_o_modo_nos_dois_eixos() -> None:
    mode = auto_association_mode(
        {AUTO_ASSOCIATION_ENABLED_ENV: "TRUE", AUTO_ASSOCIATION_THRESHOLD_ENV: " 0.7 "}
    )

    assert mode == AutoAssociationMode(threshold=0.7)
    assert mode.confidence_threshold.reading_threshold == 0.7
    assert mode.confidence_threshold.association_threshold == 0.7


# --- forma do ator-máquina ----------------------------------------------------------


def test_identidade_do_ator_maquina_carrega_a_versao_do_score() -> None:
    assert system_reviewer_id() == f"system:auto-association@{CONFIDENCE_SCORE_VERSION}"


def test_decisao_humana_gravada_antes_do_campo_continua_valida_e_e_humana() -> None:
    """Campo aditivo: pacote persistido sem `actor` é lido como decisão de pessoa."""
    decision = HumanDecision.model_validate(
        {
            "decision_id": "hd_" + "1" * 16,
            "action": "confirm",
            "reviewer_id": "eng-01",
            "reviewer_role": "engineer",
            "decided_at": datetime.now(UTC).isoformat(),
        }
    )

    assert decision.actor == "human"


def test_decisao_humana_sem_papel_profissional_e_recusada() -> None:
    with pytest.raises(ValidationError, match="papel profissional"):
        HumanDecision(
            decision_id="hd_" + "1" * 16,
            action="confirm",
            reviewer_id="eng-01",
            decided_at=datetime.now(UTC),
        )


def test_decisao_de_sistema_nao_tem_papel_profissional() -> None:
    """Papel é atributo de pessoa; fabricar um para a máquina contaminaria autorização."""
    with pytest.raises(ValidationError, match="papel profissional"):
        HumanDecision(
            decision_id="hd_" + "1" * 16,
            action="confirm",
            actor="system",
            reviewer_id=system_reviewer_id(),
            reviewer_role="engineer",
            decided_at=datetime.now(UTC),
        )


def test_decisao_de_sistema_exige_identidade_versionada() -> None:
    with pytest.raises(ValidationError, match="identidade versionada"):
        HumanDecision(
            decision_id="hd_" + "1" * 16,
            action="confirm",
            actor="system",
            reviewer_id="robo",
            decided_at=datetime.now(UTC),
        )


def test_sistema_nunca_rejeita_e_nunca_retifica() -> None:
    with pytest.raises(ValidationError, match="só confirma"):
        HumanDecision(
            decision_id="hd_" + "1" * 16,
            action="reject",
            actor="system",
            reviewer_id=system_reviewer_id(),
            decided_at=datetime.now(UTC),
        )
    with pytest.raises(ValidationError, match="nunca retifica"):
        HumanDecision(
            decision_id="hd_" + "1" * 16,
            action="confirm",
            actor="system",
            reviewer_id=system_reviewer_id(),
            decided_at=datetime.now(UTC),
            note="tentativa de correção automática",
            rectifies_decision_id="hd_" + "2" * 16,
        )


# --- aplicação ----------------------------------------------------------------------


def test_auto_decisao_exige_os_dois_eixos_acima_do_corte() -> None:
    """Leitura ótima com associação ambígua não entra: associar errado é o erro invisível."""
    confident = _reading(1, ocr_corroborated=True)
    ambiguous = _reading(2, ocr_corroborated=True)
    unread = _reading(3, ocr_corroborated=None)
    packet = _packet(confident, ambiguous, unread)
    associations = _associations(
        _candidate(confident.id, "vp_1111111111111111", 0.9),
        _candidate(ambiguous.id, "vp_2222222222222222", 0.4),
        _candidate(unread.id, "vp_3333333333333333", 0.9),
    )

    outcome = apply_auto_association(packet, associations, mode=AutoAssociationMode(threshold=0.7))

    assert [decision.reading_id for decision in outcome.decisions] == [confident.id]
    assert outcome.selected_associations == {confident.id: "vp_1111111111111111"}
    decided = {reading.id: reading for reading in outcome.packet.readings}
    assert decided[confident.id].status is ReadingStatus.CONFIRMED
    assert decided[ambiguous.id].status is ReadingStatus.PROPOSED
    assert decided[ambiguous.id].decision is None
    # A leitura sem corroboração de OCR fica abaixo do corte de LEITURA mesmo com
    # associação ótima: as duas confianças nunca se fundem numa só.
    assert decided[unread.id].decision is None


def test_a_decisao_de_sistema_registra_corte_e_as_duas_confiancas() -> None:
    reading = _reading(1, ocr_corroborated=True)
    packet = _packet(reading)
    associations = _associations(_candidate(reading.id, "vp_1111111111111111", 0.9))
    stamped_at = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)

    outcome = apply_auto_association(
        packet,
        associations,
        mode=AutoAssociationMode(threshold=0.7),
        decided_at=stamped_at,
    )

    decision = outcome.packet.readings[0].decision
    assert decision is not None
    assert decision.actor == "system"
    assert decision.action == "confirm"
    assert decision.reviewer_role is None
    assert decision.reviewer_id == system_reviewer_id()
    assert decision.decided_at == stamped_at
    assert decision.note is not None
    assert "0.7" in decision.note
    assert str(CORROBORATED_READING_CONFIDENCE) in decision.note
    assert "0.9" in decision.note
    assert CONFIDENCE_SCORE_VERSION in decision.note
    recorded = outcome.decisions[0]
    assert recorded.decision_id == decision.decision_id
    assert recorded.reading_confidence == CORROBORATED_READING_CONFIDENCE
    assert recorded.association_confidence == 0.9
    assert recorded.threshold == 0.7
    assert recorded.score_version == CONFIDENCE_SCORE_VERSION


def test_auto_decisao_nunca_toca_leitura_ja_decidida() -> None:
    """`READING_ALREADY_DECIDED` vale para a máquina como vale para gente."""
    human_decision = HumanDecision(
        decision_id="hd_" + "9" * 16,
        action="confirm",
        reviewer_id="eng-01",
        reviewer_role="engineer",
        decided_at=datetime.now(UTC),
        note="Conferida na evidência.",
    )
    decided = _reading(1, decision=human_decision)
    packet = _packet(decided)
    associations = _associations(_candidate(decided.id, "vp_1111111111111111", 0.99))

    outcome = apply_auto_association(packet, associations, mode=AutoAssociationMode(threshold=0.5))

    assert outcome.decisions == ()
    assert outcome.selected_associations == {}
    assert outcome.packet is packet
    assert outcome.packet.readings[0].decision == human_decision


def test_leitura_sem_valor_nunca_e_auto_decidida() -> None:
    """Sem medida não há o que confirmar, e inventar uma é o que o pipeline impede."""
    reading = _reading(1, value=None, ocr_corroborated=True)
    packet = _packet(reading)
    associations = _associations(_candidate(reading.id, "vp_1111111111111111", 0.99))

    outcome = apply_auto_association(packet, associations, mode=AutoAssociationMode(threshold=0.0))

    assert outcome.decisions == ()
    assert outcome.packet.readings[0].decision is None


def test_leitura_sem_candidato_nunca_e_auto_decidida() -> None:
    reading = _reading(1, ocr_corroborated=True)
    packet = _packet(reading)

    outcome = apply_auto_association(
        packet, _associations(), mode=AutoAssociationMode(threshold=0.0)
    )

    assert outcome.decisions == ()
    assert outcome.selected_associations == {}


def test_a_escolha_do_candidato_e_a_mesma_do_shadow_inclusive_no_desempate() -> None:
    """Recomputar o ranking por outro caminho faria o registro divergir do ato."""
    reading = _reading(1, ocr_corroborated=True)
    packet = _packet(reading)
    associations = _associations(
        _candidate(reading.id, "vp_ffffffffffffffff", 0.9),
        _candidate(reading.id, "vp_1111111111111111", 0.9),
    )

    outcome = apply_auto_association(packet, associations, mode=AutoAssociationMode(threshold=0.5))

    assert outcome.selected_associations == {reading.id: "vp_1111111111111111"}


def test_o_ato_nao_reescreve_a_medida_lida() -> None:
    """Máquina confirma o que está escrito; corrigir o escrito continua sendo ato humano."""
    reading = _reading(1, ocr_corroborated=True)
    packet = _packet(reading)
    associations = _associations(_candidate(reading.id, "vp_1111111111111111", 0.9))

    outcome = apply_auto_association(packet, associations, mode=AutoAssociationMode(threshold=0.5))

    decided = outcome.packet.readings[0]
    assert decided.value_si == reading.value_si
    assert decided.raw_text == reading.raw_text
    assert decided.unit == reading.unit
    assert decided.kind == reading.kind
    assert decided.target_hint == reading.target_hint
    # O pacote de entrada não é mutado: o ato produz um pacote novo.
    assert packet.readings[0].decision is None


def test_reaplicar_o_modo_sobre_o_pacote_ja_decidido_nao_decide_de_novo() -> None:
    reading = _reading(1, ocr_corroborated=True)
    packet = _packet(reading)
    associations = _associations(_candidate(reading.id, "vp_1111111111111111", 0.9))
    mode = AutoAssociationMode(threshold=0.5)

    first = apply_auto_association(packet, associations, mode=mode)
    second = apply_auto_association(first.packet, associations, mode=mode)

    assert len(first.decisions) == 1
    assert second.decisions == ()
    assert second.packet.readings[0].decision == first.packet.readings[0].decision


def test_corte_acima_do_teto_da_revisao_1_nao_decide_nada() -> None:
    """Na revisão 1 nada está confirmado, então o sinal de cadeia é sempre neutro.

    O teto da confiança de leitura ali é 0,85 (OCR corroborado + valor presente + cadeia
    neutra). Um corte acima disso é válido e simplesmente não auto-decide nada — o modo
    fica ligado sem efeito, que é o comportamento conservador correto.
    """
    reading = _reading(1, ocr_corroborated=True)
    packet = _packet(reading)
    associations = _associations(_candidate(reading.id, "vp_1111111111111111", 0.99))

    outcome = apply_auto_association(packet, associations, mode=AutoAssociationMode(threshold=0.9))

    assert outcome.decisions == ()
    assert NEUTRAL_READING_CONFIDENCE < CORROBORATED_READING_CONFIDENCE < 0.9


# --- tier de anotação (ADR-0044) ----------------------------------------------------

# Leitura sem corroboração de OCR fica em 0,45 na revisão 1 (braço rodou e não achou):
# abaixo de qualquer corte operacional, e é justamente esse o caso que o tier de anotação
# existe para resolver sem cobrar o preço de uma cota.
SINGLE_WITNESS_READING_CONFIDENCE = 0.45


def test_elevacao_de_testemunha_unica_entra_confirmada_e_sem_elemento() -> None:
    """`h=…` entra como a anotação da folha do ato humano: confirmada, sem vínculo.

    É a emenda 1a do ADR-0044. O que faz esta decisão ser barata é justamente NÃO haver
    associação: sem entrada em `selected_associations`, nenhuma restrição de geometria
    nasce dela em caminho nenhum de solve.
    """
    elevation = _reading(1, kind=MeasurementKind.HEIGHT, ocr_corroborated=False)
    packet = _packet(elevation)
    associations = _associations(_candidate(elevation.id, "vp_1111111111111111", 0.9))

    outcome = apply_auto_association(packet, associations, mode=AutoAssociationMode(threshold=0.6))

    recorded = outcome.decisions[0]
    assert recorded.tier == "anotacao"
    assert recorded.reading_confidence == SINGLE_WITNESS_READING_CONFIDENCE
    # Nenhum vínculo; o candidato viaja como observação, com a confiança dele.
    assert recorded.proposal_id is None
    assert recorded.probable_proposal_id == "vp_1111111111111111"
    assert recorded.association_confidence == 0.9
    assert outcome.selected_associations == {}
    decision = outcome.packet.readings[0].decision
    assert decision is not None
    assert decision.actor == "system"
    assert decision.auto_tier == "anotacao"
    assert decision.note is not None
    assert decision.note.startswith("Anotação automática")
    assert "SEM elemento associado" in decision.note
    # A `note` registra a confiança de leitura E declara que ela não foi exigida.
    assert "0.45" in decision.note
    assert "não exigida" in decision.note
    # O elemento provável é dica escrita, e a frase diz que não virou vínculo.
    assert "Elemento provável: vp_1111111111111111" in decision.note
    assert "nenhum vínculo foi gravado" in decision.note


def test_anotacao_automatica_entra_mesmo_com_associacao_fraca_ou_sem_candidato() -> None:
    """Sem vínculo, não há eixo de associação a exigir: o texto vale como texto.

    Antes da emenda 1a a confiança de associação era um portão do tier; ela deixou de
    ser, porque não existe mais associação para errar. Ela continua GRAVADA como
    observação — inclusive quando é baixa, e ausente quando não há candidato nenhum.
    """
    fraca = _reading(1, kind=MeasurementKind.HEIGHT, ocr_corroborated=False)
    sozinha = _reading(2, kind=MeasurementKind.HEIGHT, ocr_corroborated=False)
    packet = _packet(fraca, sozinha)
    associations = _associations(_candidate(fraca.id, "vp_1111111111111111", 0.1))

    outcome = apply_auto_association(packet, associations, mode=AutoAssociationMode(threshold=0.6))

    by_reading = {decision.reading_id: decision for decision in outcome.decisions}
    assert set(by_reading) == {fraca.id, sozinha.id}
    assert by_reading[fraca.id].probable_proposal_id == "vp_1111111111111111"
    assert by_reading[fraca.id].association_confidence == 0.1
    # Sem candidato: nem elemento provável, nem confiança inventada.
    assert by_reading[sozinha.id].probable_proposal_id is None
    assert by_reading[sozinha.id].association_confidence is None
    sem_candidato = outcome.packet.readings[1].decision
    assert sem_candidato is not None
    assert sem_candidato.note is not None
    assert "Sem candidato de elemento" in sem_candidato.note
    assert outcome.selected_associations == {}


@pytest.mark.parametrize(
    "kind",
    [
        MeasurementKind.LENGTH,
        MeasurementKind.WIDTH,
        MeasurementKind.RADIUS,
        MeasurementKind.DIAMETER,
        MeasurementKind.ANGLE,
        MeasurementKind.AREA,
    ],
)
def test_cota_de_planta_nunca_vaza_pelo_tier_de_anotacao(kind: MeasurementKind) -> None:
    """Teste de NÃO-VAZAMENTO: associação altíssima e leitura fraca não bastam.

    É a garantia central do ADR-0044 (D2). Cota de planta continua exigindo as duas
    testemunhas, com qualquer confiança de associação — inclusive 0,99.
    """
    plan_reading = _reading(1, kind=kind, ocr_corroborated=False)
    packet = _packet(plan_reading)
    associations = _associations(_candidate(plan_reading.id, "vp_1111111111111111", 0.99))

    outcome = apply_auto_association(packet, associations, mode=AutoAssociationMode(threshold=0.6))

    assert outcome.decisions == ()
    assert outcome.packet.readings[0].decision is None


def test_sinal_note_do_provider_entra_mesmo_com_o_kind_neutro_que_o_extrator_grava() -> None:
    """`kind="note"` completo chega ao pacote como `length` + `annotation_suggested`.

    É `provider_review` quem neutraliza o kind ("recado da folha, não cota"). Se a lista
    de kinds do D2 fosse lida antes do sinal, esta metade do ADR-0044 D1 seria código
    morto: nenhuma anotação do provider chega com kind fora daquela lista.
    """
    note = _reading(
        1,
        kind=MeasurementKind.LENGTH,
        annotation_suggested=True,
        ocr_corroborated=False,
    )
    packet = _packet(note)
    associations = _associations(_candidate(note.id, "vp_1111111111111111", 0.9))

    outcome = apply_auto_association(packet, associations, mode=AutoAssociationMode(threshold=0.6))

    assert [decision.tier for decision in outcome.decisions] == ["anotacao"]


def test_leitura_designada_pelo_solver_nunca_entra_pelo_tier_de_anotacao() -> None:
    """O pedido do solver DESIGNA geometria de planta, mesmo quando o kind é `height`.

    `rectangle_solver` aceita `height` como o lado vertical do retângulo e o publica com
    precisão exata: ali o erro alcança a geometria, e o fundamento do tier não vale.
    """
    side = _reading(1, kind=MeasurementKind.HEIGHT, ocr_corroborated=False)
    packet = _packet(side)
    associations = _associations(_candidate(side.id, "vp_1111111111111111", 0.9))

    outcome = apply_auto_association(
        packet,
        associations,
        mode=AutoAssociationMode(threshold=0.6),
        plan_geometry_reading_ids=frozenset({side.id}),
    )

    assert outcome.decisions == ()


def test_elevacao_com_duas_testemunhas_entra_pelo_tier_mais_forte() -> None:
    """Passando nos dois eixos, a leitura entra pela regra forte e o registro diz qual foi."""
    elevation = _reading(1, kind=MeasurementKind.HEIGHT, ocr_corroborated=True)
    packet = _packet(elevation)
    associations = _associations(_candidate(elevation.id, "vp_1111111111111111", 0.9))

    outcome = apply_auto_association(packet, associations, mode=AutoAssociationMode(threshold=0.6))

    recorded = outcome.decisions[0]
    assert recorded.tier == "cota"
    decision = outcome.packet.readings[0].decision
    assert decision is not None
    assert decision.auto_tier == "cota"
    # A `note` do tier de dupla testemunha é a mesma palavra por palavra desde a T4.
    assert decision.note is not None
    assert decision.note.startswith("Decisão automática de associação")


def test_os_dois_tiers_convivem_na_mesma_revisao_sem_se_contaminar() -> None:
    cota = _reading(1, ocr_corroborated=True)
    anotacao = _reading(2, kind=MeasurementKind.HEIGHT, ocr_corroborated=False)
    planta_fraca = _reading(3, ocr_corroborated=False)
    packet = _packet(cota, anotacao, planta_fraca)
    associations = _associations(
        _candidate(cota.id, "vp_1111111111111111", 0.9),
        _candidate(anotacao.id, "vp_2222222222222222", 0.9),
        _candidate(planta_fraca.id, "vp_3333333333333333", 0.99),
    )

    outcome = apply_auto_association(packet, associations, mode=AutoAssociationMode(threshold=0.6))

    assert {decision.reading_id: decision.tier for decision in outcome.decisions} == {
        cota.id: "cota",
        anotacao.id: "anotacao",
    }
    # A cota de planta de testemunha única continua sendo exceção para uma pessoa.
    decided = {reading.id: reading for reading in outcome.packet.readings}
    assert decided[planta_fraca.id].decision is None
    assert planta_fraca.id not in outcome.selected_associations


def test_o_tier_de_anotacao_nao_reclassifica_a_leitura() -> None:
    """ADR-0044 D2: o que muda é o critério de elegibilidade, nunca o conteúdo."""
    elevation = _reading(1, kind=MeasurementKind.HEIGHT, ocr_corroborated=False)
    packet = _packet(elevation)
    associations = _associations(_candidate(elevation.id, "vp_1111111111111111", 0.9))

    outcome = apply_auto_association(packet, associations, mode=AutoAssociationMode(threshold=0.6))

    decided = outcome.packet.readings[0]
    assert decided.kind is MeasurementKind.HEIGHT
    assert decided.value_si == elevation.value_si
    assert decided.raw_text == elevation.raw_text
    assert decided.unit == elevation.unit
    assert decided.annotation_suggested == elevation.annotation_suggested


def test_decisao_humana_nunca_carrega_tier_de_decisao_automatica() -> None:
    with pytest.raises(ValidationError, match="tier de decisão automática"):
        HumanDecision(
            decision_id="hd_" + "1" * 16,
            action="confirm",
            reviewer_id="eng-01",
            reviewer_role="engineer",
            decided_at=datetime.now(UTC),
            auto_tier="anotacao",
        )


def test_decisao_de_sistema_gravada_antes_do_tier_e_lida_como_cota() -> None:
    """Replay de registro da T4: era o único tier que existia, e essa é a verdade sobre ela."""
    decision = HumanDecision.model_validate(
        {
            "decision_id": "hd_" + "1" * 16,
            "action": "confirm",
            "actor": "system",
            "reviewer_id": system_reviewer_id(),
            "decided_at": datetime.now(UTC).isoformat(),
        }
    )

    assert decision.auto_tier == "cota"
