"""Portões do contrato de pacote de levantamento de campo (F-032, T7).

Espelha o padrão de `tests/core/test_schema_export.py`: confere presença no manifesto de
contratos e as validações do modelo Pydantic que o mapeamento de `apps/field` depende
(mm nunca negativo onde vale a regra, sha256 malformado rejeitado, seq >= 1).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from croquito_core.field import (
    SURVEY_SCHEMA_VERSION,
    Measurement,
    MeasurementKind,
    MeasurementStatus,
    MediaAnchor,
    MediaRef,
    ObservationNote,
    Segment,
    SurveyOperation,
    SurveyPacket,
    SurveyPoint,
    SurveyStatus,
)
from croquito_core.schema_export import DEFAULT_MANIFEST

NOW = datetime(2026, 8, 21, 12, 0, 0, tzinfo=UTC)

VALID_SHA256 = "a" * 64


def _media_ref(sha256: str = VALID_SHA256) -> MediaRef:
    return MediaRef(sha256=sha256, mime_type="image/jpeg", byte_size=1024)


def _minimal_packet(**overrides: Any) -> SurveyPacket:
    fields: dict[str, Any] = {
        "survey_id": "survey-1",
        "name": "Praça de teste",
        "device_id": "device-1",
        "created_at": NOW,
        "updated_at": NOW,
        "status": SurveyStatus.COLLECTING,
    }
    fields.update(overrides)
    return SurveyPacket(**fields)


def test_manifesto_registra_survey_packet() -> None:
    entries = json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
    entry = next((e for e in entries if e["model"] == "SurveyPacket"), None)

    assert entry is not None, "SurveyPacket ausente de contracts.manifest.json"
    assert entry["module"] == "croquito_core.field"
    assert entry["version_attr"] == "SURVEY_SCHEMA_VERSION"
    assert entry["schema"] == "schemas/survey-packet.schema.json"
    assert entry["typescript"] == "src/survey-packet.generated.ts"


def test_versao_do_schema_e_string_estavel() -> None:
    assert SURVEY_SCHEMA_VERSION == "1.0.0"


def test_survey_point_aceita_coordenada_negativa() -> None:
    """x_mm/y_mm são relativos a uma origem local arbitrária — negativo é válido."""
    point = SurveyPoint(id="p1", x_mm=-3200, y_mm=0, created_at=NOW)

    assert point.x_mm == -3200


def test_survey_point_rejeita_coordenada_fora_do_limite_sensato() -> None:
    with pytest.raises(ValidationError):
        SurveyPoint(id="p1", x_mm=10_000_000, y_mm=0, created_at=NOW)


def test_measurement_rejeita_value_mm_negativo() -> None:
    """Diferente de x_mm/y_mm, uma medida nunca é negativa."""
    with pytest.raises(ValidationError):
        Measurement(
            id="m1",
            value_mm=-10,
            kind=MeasurementKind.LENGTH,
            instrument="trena",
            status=MeasurementStatus.CONFIRMED,
            created_at=NOW,
        )


def test_measurement_aceita_value_mm_zero() -> None:
    measurement = Measurement(
        id="m1",
        value_mm=0,
        kind=MeasurementKind.LEVEL,
        instrument="nível",
        status=MeasurementStatus.DRAFT,
        created_at=NOW,
    )

    assert measurement.value_mm == 0


def test_media_ref_rejeita_sha256_malformado() -> None:
    with pytest.raises(ValidationError, match="sha256"):
        MediaRef(sha256="not-a-hash", mime_type="image/jpeg", byte_size=10)


@pytest.mark.parametrize(
    "malformado",
    [
        "a" * 63,  # curto demais
        "a" * 65,  # longo demais
        "A" * 64,  # maiúsculo não é hex minúsculo
        "g" * 64,  # fora do alfabeto hex
    ],
)
def test_media_ref_rejeita_variacoes_de_sha256_invalido(malformado: str) -> None:
    with pytest.raises(ValidationError):
        MediaRef(sha256=malformado, mime_type="image/jpeg", byte_size=10)


def test_media_ref_aceita_sha256_valido() -> None:
    ref = _media_ref()

    assert ref.sha256 == VALID_SHA256


def test_media_anchor_carrega_media_ref_estruturado() -> None:
    anchor = MediaAnchor(id="ph1", media_ref=_media_ref(), point_id="p1", created_at=NOW)

    assert anchor.media_ref.sha256 == VALID_SHA256


def test_survey_operation_rejeita_seq_zero() -> None:
    with pytest.raises(ValidationError):
        SurveyOperation(
            operation_id="op1",
            device_id="device-1",
            survey_id="survey-1",
            seq=0,
            type="point.add",
            payload={},
            created_at=NOW,
        )


def test_survey_operation_aceita_seq_a_partir_de_um() -> None:
    operation = SurveyOperation(
        operation_id="op1",
        device_id="device-1",
        survey_id="survey-1",
        seq=1,
        type="point.add",
        payload={"point": {"id": "p1"}},
        created_at=NOW,
    )

    assert operation.seq == 1


def test_survey_operation_nao_aceita_campo_status() -> None:
    """Espelho de `SurveyOperation` do outbox sem `status`: reconhecimento é estado
    local do app, nunca viaja no pacote (`ContractModel` usa `extra=\"forbid\"`)."""
    with pytest.raises(ValidationError):
        SurveyOperation.model_validate(
            {
                "operation_id": "op1",
                "device_id": "device-1",
                "survey_id": "survey-1",
                "seq": 1,
                "type": "point.add",
                "payload": {},
                "status": "acked",
                "created_at": NOW,
            }
        )


def test_survey_packet_nao_tem_campo_tenant() -> None:
    """Tenant vem sempre do JWT, nunca do corpo do pacote."""
    with pytest.raises(ValidationError):
        _minimal_packet(tenant_id="tenant-1")


def test_survey_packet_minimo_e_valido() -> None:
    packet = _minimal_packet()

    assert packet.points == []
    assert packet.waivers == []
    assert packet.operations == []
    assert packet.arrival_context is None


def test_survey_packet_rejeita_operacao_de_outro_survey() -> None:
    operacao_alheia = SurveyOperation(
        operation_id="op1",
        device_id="device-1",
        survey_id="outro-survey",
        seq=1,
        type="point.add",
        payload={},
        created_at=NOW,
    )

    with pytest.raises(ValidationError, match="outro survey"):
        _minimal_packet(operations=[operacao_alheia])


def test_survey_packet_aceita_operacao_do_mesmo_survey() -> None:
    operacao = SurveyOperation(
        operation_id="op1",
        device_id="device-1",
        survey_id="survey-1",
        seq=1,
        type="point.add",
        payload={},
        created_at=NOW,
    )

    packet = _minimal_packet(operations=[operacao])

    assert packet.operations == [operacao]


def test_segment_exige_ids_nao_vazios() -> None:
    with pytest.raises(ValidationError):
        Segment(id="", from_point_id="p1", to_point_id="p2", created_at=NOW)


def test_observacao_so_de_voz_e_valida() -> None:
    """Prancha 7a (DAP rev.2, aprovada): nota só-áudio viaja com texto vazio."""
    nota = ObservationNote(id="o1", text="", audio_media_ref=_media_ref(), created_at=NOW)

    assert nota.text == ""
    assert nota.audio_media_ref is not None


def test_observacao_vazia_sem_texto_e_sem_audio_e_recusada() -> None:
    """Mesma regra EMPTY_TEXT do domínio do app: nota sem nada não registra nada."""
    with pytest.raises(ValidationError):
        ObservationNote(id="o1", text="   ", created_at=NOW)


def test_observacao_com_texto_e_audio_e_valida() -> None:
    nota = ObservationNote(
        id="o1", text="degrau solto na escada", audio_media_ref=_media_ref(), created_at=NOW
    )

    assert nota.text and nota.audio_media_ref is not None
