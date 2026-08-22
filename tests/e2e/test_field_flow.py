"""Cadeia completa de campo (F-032, T16): dispositivo → sincronização → fila → worker.

Um único fluxo, in-process e com fakes, prova a fatia de sincronização inteira: o
"dispositivo" simulado monta `SurveyPacket` (`croquito_core.field`) e fala com a API REAL
(`/v1/surveys/...`) sobre o mesmo banco, storage e fila que o worker consome — o mesmo
desenho de `tests/e2e/test_full_flow.py`, aplicado à cadeia de campo. Nenhuma chamada de
rede ou de provider real acontece: os dois braços pagos (visão e transcrição) são adapters
contadores injetados via `ProviderSuite`, reusados de `tests/worker/test_survey_photo_analysis.py`
e `tests/worker/test_survey_transcription.py` em vez de duplicados.

Assertivas nomeadas (ver Task Contract T16):

1. Lote 1 cria o levantamento; reenvio da MESMA `Idempotency-Key` não duplica nada.
2. Conflito de sequência devolve o estado do servidor; a operação `conflict_resolution`
   reancorada fecha sem conflito, espelhando o protocolo de `apps/field/src/sync/engine.ts`
   contra a API real.
3. Prancha 6a: presign de mídia ainda não referenciada é 409; depois do lote que referencia
   foto E áudio, presign + PUT + confirm dos dois publica `analyze_survey_photo` e
   `transcribe_survey_audio` exatamente uma vez cada — reconfirmar não duplica.
4. Conclusão recusada com mídia pendente antes dos confirms; aceita depois, publicando
   `export_survey`.
5. O worker consome as três mensagens via `run_once`: os quatro artefatos existem em chave
   estável, a transcrição é `draft` com `note_id`, e a análise carrega `quality` e as
   leituras do adapter fake.
6. Fail-closed: a cena reexportada revalidada pelo contrato (`SceneRevision.model_validate`)
   tem `export_errors()` não-vazio, nenhuma entidade `exact` e nenhuma `export=True`.
7. Sem entitlement (segundo tenant): as mensagens processam como
   `skipped_no_entitlement`, sem nenhuma chamada nos adapters contadores; o export, que não
   é pago, funciona normalmente.
8. Contagem final dos adapters contadores é exata; nenhuma chamada de rede real acontece
   por construção — os dois braços pagos são fakes injetados.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import select

from croquito_api.config import ApiSettings
from croquito_api.database import (
    Database,
    SurveyOperationRecord,
    TenantAiProcessingEntitlementRecord,
)
from croquito_api.main import create_app
from croquito_core.field import SurveyPacket
from croquito_core.models import Precision, SceneRevision
from croquito_worker.local_queue import LocalQueueWorker, LocalWorkerSettings
from croquito_worker.providers import ProviderSuite
from tests.fakes import FakeObjectStore, FakeQueue
from tests.worker.test_survey_photo_analysis import CountingAdapter as PhotoCountingAdapter
from tests.worker.test_survey_photo_analysis import sharp_photo
from tests.worker.test_survey_transcription import TRANSCRIPT_TEXT
from tests.worker.test_survey_transcription import CountingAdapter as AudioCountingAdapter

QUEUE_URL = "http://localstack/queue"

TENANT_A = "tenant-campo-e2e"
TENANT_B = "tenant-campo-e2e-vizinho"
DEVICE_A = "device-campo-a"
DEVICE_B = "device-campo-b"
SURVEY_A = "00000000-0000-7000-8000-0000000020aa"
SURVEY_B = "00000000-0000-7000-8000-0000000020bb"
INSTANT = "2026-08-21T12:00:00Z"

PHOTO_BYTES = sharp_photo()
PHOTO_SHA256 = hashlib.sha256(PHOTO_BYTES).hexdigest()
AUDIO_BYTES = b"croquito-e2e-campo::nota-de-voz-do-tecnico" * 3
AUDIO_SHA256 = hashlib.sha256(AUDIO_BYTES).hexdigest()

PHOTO_B_BYTES = sharp_photo()
PHOTO_B_SHA256 = hashlib.sha256(PHOTO_B_BYTES).hexdigest()
AUDIO_B_BYTES = b"croquito-e2e-campo::segunda-nota-de-voz" * 3
AUDIO_B_SHA256 = hashlib.sha256(AUDIO_B_BYTES).hexdigest()


def _headers(tenant: str, *, key: str, roles: str = "field_technician") -> dict[str, str]:
    return {
        "Authorization": f"Bearer test:{tenant}:tecnica-e2e:{roles}",
        "Idempotency-Key": key,
    }


def _op(
    seq: int,
    type_: str,
    payload: dict[str, Any],
    *,
    device_id: str = DEVICE_A,
    survey_id: str = SURVEY_A,
) -> dict[str, Any]:
    return {
        "operation_id": f"op-{device_id}-{seq}",
        "device_id": device_id,
        "survey_id": survey_id,
        "seq": seq,
        "type": type_,
        "payload": payload,
        "created_at": INSTANT,
    }


def _media_ref(sha256: str, mime_type: str, byte_size: int) -> dict[str, Any]:
    return {"sha256": sha256, "mime_type": mime_type, "byte_size": byte_size}


def _survey_packet(
    *,
    survey_id: str,
    device_id: str,
    status: str,
    photo_sha256: str | None = None,
    audio_sha256: str | None = None,
) -> dict[str, Any]:
    """Pacote do "dispositivo", montado em Python contra o contrato de `croquito_core.field`.

    Dois pontos ligados por um segmento com medida CONFIRMADA compatível (3 m), uma foto
    ancorada, uma nota SÓ-de-voz com `audio_media_ref`, contexto de chegada e — na
    conclusão — um waiver: o mínimo que exercita os três tipos de mídia e o desfecho
    `concluded` sem inventar geometria extra.
    """
    media_anchors: list[dict[str, Any]] = []
    if photo_sha256 is not None:
        media_anchors.append(
            {
                "id": "ma-1",
                "media_ref": _media_ref(photo_sha256, "image/png", len(PHOTO_BYTES)),
                "point_id": "p1",
                "element_id": None,
                "note_id": None,
                "created_at": INSTANT,
            }
        )
    observations: list[dict[str, Any]] = []
    if audio_sha256 is not None:
        observations.append(
            {
                "id": "obs-1",
                "text": "",
                "point_id": "p1",
                "element_id": None,
                "audio_media_ref": _media_ref(audio_sha256, "audio/webm", len(AUDIO_BYTES)),
                "created_at": INSTANT,
            }
        )
    waivers: list[dict[str, Any]] = []
    if status == "concluded":
        waivers.append(
            {
                "id": "w1",
                "finding_code": "REQUIRED_ITEM_PENDING",
                "ref_key": "foto-extra",
                "justification": "Item extra dispensado pela condição do local.",
                "created_at": INSTANT,
            }
        )
    packet: dict[str, Any] = {
        "survey_id": survey_id,
        "name": "Praça sintética E2E",
        "order_id": "ordem-e2e-1",
        "device_id": device_id,
        "created_at": INSTANT,
        "updated_at": INSTANT,
        "points": [
            {"id": "p1", "x_mm": 0, "y_mm": 0, "created_at": INSTANT},
            {"id": "p2", "x_mm": 3000, "y_mm": 0, "created_at": INSTANT},
        ],
        "segments": [
            {"id": "s1", "from_point_id": "p1", "to_point_id": "p2", "created_at": INSTANT}
        ],
        "measurements": [
            {
                "id": "m1",
                "value_mm": 3000,
                "kind": "length",
                "from_point_id": "p1",
                "to_point_id": "p2",
                "second_from_point_id": None,
                "second_to_point_id": None,
                "element_id": None,
                "instrument": "Trena laser",
                "status": "confirmed",
                "justification": None,
                "created_at": INSTANT,
            }
        ],
        "media_anchors": media_anchors,
        "elements": [],
        "observations": observations,
        "gps_fixes": [{"lat": -22.9, "lng": -43.2, "accuracy_m": 6.0}],
        "arrival_context": {
            "instrument": "Trena laser",
            "reference_note": "Portão principal da praça.",
            "gps": {"lat": -22.9, "lng": -43.2, "accuracy_m": 6.0},
            "access_media_ref": None,
            "arrived_at": INSTANT,
        },
        "status": status,
        "waivers": waivers,
        "operations": [],
    }
    return SurveyPacket.model_validate(packet).model_dump(mode="json")


def _sync(
    client: TestClient,
    *,
    tenant: str,
    survey_id: str,
    device_id: str,
    key: str,
    operations: list[dict[str, Any]],
    packet: dict[str, Any],
) -> Any:
    return client.post(
        f"/v1/surveys/{survey_id}/operations",
        headers=_headers(tenant, key=key),
        json={"device_id": device_id, "survey": packet, "operations": operations},
    )


def _presign(
    client: TestClient,
    *,
    tenant: str,
    survey_id: str,
    sha256: str,
    mime_type: str,
    byte_size: int,
    key: str,
) -> Any:
    return client.post(
        f"/v1/surveys/{survey_id}/media/presign",
        headers=_headers(tenant, key=key),
        json={"sha256": sha256, "mime_type": mime_type, "byte_size": byte_size},
    )


def _confirm(client: TestClient, *, tenant: str, survey_id: str, sha256: str, key: str) -> Any:
    return client.post(
        f"/v1/surveys/{survey_id}/media/{sha256}/confirm",
        headers=_headers(tenant, key=key),
    )


def _complete(
    client: TestClient, *, tenant: str, survey_id: str, base_version: int, key: str
) -> Any:
    return client.post(
        f"/v1/surveys/{survey_id}/complete",
        headers=_headers(tenant, key=key),
        json={"base_version": base_version},
    )


def _published_commands(queue: FakeQueue) -> list[str]:
    """Comandos publicados e ainda não consumidos — o que está na fila, não o que já saiu."""
    return [str(json.loads(message["Body"])["command"]) for message in queue.messages]


def _analysis_key(tenant: str, survey_id: str, sha256: str) -> str:
    return f"tenants/{tenant}/surveys/{survey_id}/analysis/{sha256}.json"


def _transcript_key(tenant: str, survey_id: str, sha256: str) -> str:
    return f"tenants/{tenant}/surveys/{survey_id}/transcripts/{sha256}.json"


def _scene_key(tenant: str, survey_id: str) -> str:
    return f"tenants/{tenant}/surveys/{survey_id}/export/scene.json"


def _attachments_key(tenant: str, survey_id: str) -> str:
    return f"tenants/{tenant}/surveys/{survey_id}/export/attachments.json"


_Stack = tuple[
    TestClient,
    LocalQueueWorker,
    FakeObjectStore,
    FakeQueue,
    Database,
    PhotoCountingAdapter,
    AudioCountingAdapter,
]


def _build_stack(tmp_path: Path) -> _Stack:
    """API e worker sobre o mesmo banco, storage e fila — como `test_full_flow.stack`."""
    database_url = f"sqlite+pysqlite:///{tmp_path / 'field-e2e.db'}"
    database = Database(database_url)
    database.create_schema()
    settings = ApiSettings(
        database_url=database_url,
        artifact_bucket="croquito-e2e-field",
        aws_region="sa-east-1",
        aws_endpoint_url="http://localhost:4566",
        queue_url=QUEUE_URL,
        oidc_issuer=None,
        oidc_audience=None,
        web_origin="http://localhost:5173",
        allow_test_tokens=True,
    )
    app = create_app(settings=settings, database=database)
    storage = FakeObjectStore()
    queue = FakeQueue()
    app.state.artifact_store = storage
    app.state.queue.client = queue

    photo_adapter = PhotoCountingAdapter()
    audio_adapter = AudioCountingAdapter()
    suite = ProviderSuite(anthropic=photo_adapter, transcription=audio_adapter)
    worker = LocalQueueWorker(
        LocalWorkerSettings(
            database_url=database_url,
            queue_url=QUEUE_URL,
            aws_region="sa-east-1",
            aws_endpoint_url="http://localhost:4566",
            artifact_bucket="croquito-e2e-field",
        ),
        provider_suite=suite,
    )
    worker.client = queue
    worker.s3_client = storage
    return TestClient(app), worker, storage, queue, database, photo_adapter, audio_adapter


def test_field_survey_chain_end_to_end(tmp_path: Path) -> None:
    client, worker, storage, queue, database, photo_adapter, audio_adapter = _build_stack(tmp_path)

    # Entitlement ATIVO só para o tenant A — o tenant B (assertiva 7) nunca ganha um.
    with database.sessions.begin() as session:
        session.add(
            TenantAiProcessingEntitlementRecord(
                id="entitlement-e2e-a",
                tenant_id=TENANT_A,
                status="ACTIVE",
                agreement_reference="contrato-e2e-1",
                authorized_by="platform-operator",
                authorized_at=datetime.now(UTC),
            )
        )

    # ------------------------------------------------------------------------------------
    # Assertiva 1: lote 1 cria o levantamento; reenvio da mesma chave não duplica nada.
    # ------------------------------------------------------------------------------------
    packet_collecting = _survey_packet(survey_id=SURVEY_A, device_id=DEVICE_A, status="collecting")
    primeiro = _sync(
        client,
        tenant=TENANT_A,
        survey_id=SURVEY_A,
        device_id=DEVICE_A,
        key="req-1",
        operations=[
            _op(1, "add_point", {"point_id": "p1"}),
            _op(2, "add_point", {"point_id": "p2"}),
        ],
        packet=packet_collecting,
    )
    assert primeiro.status_code == 200
    assert primeiro.json()["version"] == 1
    assert primeiro.json()["last_seq_by_device"] == {DEVICE_A: 2}
    assert primeiro.json()["acked_operation_ids"] == [
        f"op-{DEVICE_A}-1",
        f"op-{DEVICE_A}-2",
    ]

    reenvio = _sync(
        client,
        tenant=TENANT_A,
        survey_id=SURVEY_A,
        device_id=DEVICE_A,
        key="req-1",
        operations=[
            _op(1, "add_point", {"point_id": "p1"}),
            _op(2, "add_point", {"point_id": "p2"}),
        ],
        packet=packet_collecting,
    )
    assert reenvio.status_code == 200
    assert reenvio.json() == primeiro.json()
    with database.sessions() as session:
        rows = list(
            session.scalars(
                select(SurveyOperationRecord).where(
                    SurveyOperationRecord.survey_id == SURVEY_A,
                    SurveyOperationRecord.tenant_id == TENANT_A,
                )
            )
        )
        assert len(rows) == 2

    # ------------------------------------------------------------------------------------
    # Assertiva 2: buraco de sequência é conflito; `conflict_resolution` reancorado fecha.
    # ------------------------------------------------------------------------------------
    conflito = _sync(
        client,
        tenant=TENANT_A,
        survey_id=SURVEY_A,
        device_id=DEVICE_A,
        key="req-conflict",
        operations=[_op(5, "add_segment", {"segment_id": "s1"})],
        packet=packet_collecting,
    )
    assert conflito.status_code == 409
    detail = conflito.json()["detail"]
    assert detail["code"] == "SURVEY_CONFLICT"
    assert detail["details"]["server_version"] == 1
    assert detail["details"]["last_seq_by_device"] == {DEVICE_A: 2}

    resolucao = _sync(
        client,
        tenant=TENANT_A,
        survey_id=SURVEY_A,
        device_id=DEVICE_A,
        key="req-resolve",
        operations=[
            _op(
                3,
                "conflict_resolution",
                {
                    "decision": "keep_local",
                    "justification": (
                        "O técnico manteve a versão levantada em campo; a versão do "
                        "escritório foi recusada na tela de conflito."
                    ),
                    "server_version": 1,
                    "server_last_seq": 2,
                    "superseded_operation_ids": [],
                },
            )
        ],
        packet=packet_collecting,
    )
    assert resolucao.status_code == 200
    assert resolucao.json()["version"] == 2
    assert resolucao.json()["last_seq_by_device"] == {DEVICE_A: 3}

    # ------------------------------------------------------------------------------------
    # Assertiva 3: prancha 6a — mídia não referenciada é 409 antes do lote que a referencia.
    # ------------------------------------------------------------------------------------
    presign_cedo = _presign(
        client,
        tenant=TENANT_A,
        survey_id=SURVEY_A,
        sha256=PHOTO_SHA256,
        mime_type="image/png",
        byte_size=len(PHOTO_BYTES),
        key="presign-cedo",
    )
    assert presign_cedo.status_code == 409
    assert presign_cedo.json()["detail"]["code"] == "SURVEY_MEDIA_NOT_REFERENCED"

    packet_com_midia = _survey_packet(
        survey_id=SURVEY_A,
        device_id=DEVICE_A,
        status="collecting",
        photo_sha256=PHOTO_SHA256,
        audio_sha256=AUDIO_SHA256,
    )
    lote_midia = _sync(
        client,
        tenant=TENANT_A,
        survey_id=SURVEY_A,
        device_id=DEVICE_A,
        key="req-media",
        operations=[_op(4, "add_media_anchor", {"anchor_id": "ma-1"})],
        packet=packet_com_midia,
    )
    assert lote_midia.status_code == 200
    assert lote_midia.json()["version"] == 3
    assert lote_midia.json()["last_seq_by_device"] == {DEVICE_A: 4}

    presign_foto = _presign(
        client,
        tenant=TENANT_A,
        survey_id=SURVEY_A,
        sha256=PHOTO_SHA256,
        mime_type="image/png",
        byte_size=len(PHOTO_BYTES),
        key="presign-foto",
    )
    assert presign_foto.status_code == 200
    storage.put_direct(
        object_key=presign_foto.json()["object_key"], body=PHOTO_BYTES, content_type="image/png"
    )
    presign_audio = _presign(
        client,
        tenant=TENANT_A,
        survey_id=SURVEY_A,
        sha256=AUDIO_SHA256,
        mime_type="audio/webm",
        byte_size=len(AUDIO_BYTES),
        key="presign-audio",
    )
    assert presign_audio.status_code == 200
    storage.put_direct(
        object_key=presign_audio.json()["object_key"], body=AUDIO_BYTES, content_type="audio/webm"
    )

    # ------------------------------------------------------------------------------------
    # Assertiva 4: conclusão recusada com mídia pendente; aceita depois dos dois confirms.
    # ------------------------------------------------------------------------------------
    packet_concluido = _survey_packet(
        survey_id=SURVEY_A,
        device_id=DEVICE_A,
        status="concluded",
        photo_sha256=PHOTO_SHA256,
        audio_sha256=AUDIO_SHA256,
    )
    lote_conclusao = _sync(
        client,
        tenant=TENANT_A,
        survey_id=SURVEY_A,
        device_id=DEVICE_A,
        key="req-conclude",
        operations=[_op(5, "conclude_survey", {})],
        packet=packet_concluido,
    )
    assert lote_conclusao.status_code == 200
    assert lote_conclusao.json()["version"] == 4
    assert lote_conclusao.json()["last_seq_by_device"] == {DEVICE_A: 5}

    complete_key = f"complete:{SURVEY_A}:4"
    recusada = _complete(
        client, tenant=TENANT_A, survey_id=SURVEY_A, base_version=4, key=complete_key
    )
    assert recusada.status_code == 409
    detail = recusada.json()["detail"]
    assert detail["code"] == "SURVEY_MEDIA_PENDING"
    assert sorted(detail["details"]["pending_sha256"]) == sorted([PHOTO_SHA256, AUDIO_SHA256])
    assert _published_commands(queue) == []

    confirmar_foto_1 = _confirm(
        client, tenant=TENANT_A, survey_id=SURVEY_A, sha256=PHOTO_SHA256, key="confirm-foto-1"
    )
    assert confirmar_foto_1.status_code == 200
    assert _published_commands(queue) == ["analyze_survey_photo"]
    # Reconfirmar não duplica a publicação.
    confirmar_foto_2 = _confirm(
        client, tenant=TENANT_A, survey_id=SURVEY_A, sha256=PHOTO_SHA256, key="confirm-foto-2"
    )
    assert confirmar_foto_2.status_code == 200
    assert _published_commands(queue) == ["analyze_survey_photo"]

    confirmar_audio_1 = _confirm(
        client, tenant=TENANT_A, survey_id=SURVEY_A, sha256=AUDIO_SHA256, key="confirm-audio-1"
    )
    assert confirmar_audio_1.status_code == 200
    assert _published_commands(queue) == ["analyze_survey_photo", "transcribe_survey_audio"]
    confirmar_audio_2 = _confirm(
        client, tenant=TENANT_A, survey_id=SURVEY_A, sha256=AUDIO_SHA256, key="confirm-audio-2"
    )
    assert confirmar_audio_2.status_code == 200
    assert _published_commands(queue) == ["analyze_survey_photo", "transcribe_survey_audio"]

    aceita = _complete(
        client, tenant=TENANT_A, survey_id=SURVEY_A, base_version=4, key=complete_key
    )
    assert aceita.status_code == 200
    assert aceita.json()["status"] == "COMPLETED"
    assert _published_commands(queue) == [
        "analyze_survey_photo",
        "transcribe_survey_audio",
        "export_survey",
    ]

    # ------------------------------------------------------------------------------------
    # Assertiva 5: o worker consome as três mensagens; os quatro artefatos existem.
    # ------------------------------------------------------------------------------------
    assert worker.run_once() == 1
    assert worker.run_once() == 1
    assert worker.run_once() == 1
    assert queue.commands() == [
        "analyze_survey_photo",
        "transcribe_survey_audio",
        "export_survey",
    ]

    analysis = json.loads(storage.body(_analysis_key(TENANT_A, SURVEY_A, PHOTO_SHA256)))
    assert analysis["provider_pass"] == "done"
    assert analysis["quality"]["width_px"] == 1024
    assert analysis["quality"]["height_px"] == 768
    assert analysis["readings"] == [
        {
            "raw_text": "PRAÇA MUNICIPAL — 12,00 m",
            "kind_hint": "sign",
            "value_hint": "12.00",
            "unit_hint": "m",
            "target_hint": "muro do fundo",
            "confidence": "medium",
        }
    ]

    transcript = json.loads(storage.body(_transcript_key(TENANT_A, SURVEY_A, AUDIO_SHA256)))
    assert transcript["status"] == "draft"
    assert transcript["note_id"] == "obs-1"
    assert transcript["provider_pass"] == "done"
    assert transcript["transcript"]["text"] == TRANSCRIPT_TEXT

    assert _scene_key(TENANT_A, SURVEY_A) in storage.objects
    assert _attachments_key(TENANT_A, SURVEY_A) in storage.objects

    # ------------------------------------------------------------------------------------
    # Assertiva 6: fail-closed — a cena revalidada não é exportável.
    # ------------------------------------------------------------------------------------
    scene_document = json.loads(storage.body(_scene_key(TENANT_A, SURVEY_A)))
    scene = SceneRevision.model_validate(scene_document)
    assert scene.job_id == UUID(SURVEY_A)
    assert scene.approved is False
    assert scene.export_errors() == ["SCENE_NOT_APPROVED"]
    assert all(entity.precision is not Precision.EXACT for entity in scene.entities)
    assert all(entity.export is False for entity in scene.entities)

    # ------------------------------------------------------------------------------------
    # Assertiva 7: sem entitlement, o segundo tenant processa sem chamar os adapters.
    # ------------------------------------------------------------------------------------
    packet_b = _survey_packet(
        survey_id=SURVEY_B,
        device_id=DEVICE_B,
        status="concluded",
        photo_sha256=PHOTO_B_SHA256,
        audio_sha256=AUDIO_B_SHA256,
    )
    lote_b = _sync(
        client,
        tenant=TENANT_B,
        survey_id=SURVEY_B,
        device_id=DEVICE_B,
        key="req-b-1",
        operations=[
            _op(1, "add_point", {"point_id": "p1"}, device_id=DEVICE_B, survey_id=SURVEY_B)
        ],
        packet=packet_b,
    )
    assert lote_b.status_code == 200
    assert lote_b.json()["version"] == 1

    presign_foto_b = _presign(
        client,
        tenant=TENANT_B,
        survey_id=SURVEY_B,
        sha256=PHOTO_B_SHA256,
        mime_type="image/png",
        byte_size=len(PHOTO_B_BYTES),
        key="presign-foto-b",
    )
    assert presign_foto_b.status_code == 200
    storage.put_direct(
        object_key=presign_foto_b.json()["object_key"], body=PHOTO_B_BYTES, content_type="image/png"
    )
    presign_audio_b = _presign(
        client,
        tenant=TENANT_B,
        survey_id=SURVEY_B,
        sha256=AUDIO_B_SHA256,
        mime_type="audio/webm",
        byte_size=len(AUDIO_B_BYTES),
        key="presign-audio-b",
    )
    assert presign_audio_b.status_code == 200
    storage.put_direct(
        object_key=presign_audio_b.json()["object_key"],
        body=AUDIO_B_BYTES,
        content_type="audio/webm",
    )

    assert (
        _confirm(
            client, tenant=TENANT_B, survey_id=SURVEY_B, sha256=PHOTO_B_SHA256, key="confirm-foto-b"
        ).status_code
        == 200
    )
    assert (
        _confirm(
            client,
            tenant=TENANT_B,
            survey_id=SURVEY_B,
            sha256=AUDIO_B_SHA256,
            key="confirm-audio-b",
        ).status_code
        == 200
    )
    completa_b = _complete(
        client,
        tenant=TENANT_B,
        survey_id=SURVEY_B,
        base_version=1,
        key=f"complete:{SURVEY_B}:1",
    )
    assert completa_b.status_code == 200
    assert _published_commands(queue) == [
        "analyze_survey_photo",
        "transcribe_survey_audio",
        "export_survey",
    ]

    assert worker.run_once() == 1
    assert worker.run_once() == 1
    assert worker.run_once() == 1
    assert queue.commands() == [
        "analyze_survey_photo",
        "transcribe_survey_audio",
        "export_survey",
        "analyze_survey_photo",
        "transcribe_survey_audio",
        "export_survey",
    ]

    analysis_b = json.loads(storage.body(_analysis_key(TENANT_B, SURVEY_B, PHOTO_B_SHA256)))
    assert analysis_b["provider_pass"] == "skipped_no_entitlement"
    assert analysis_b["readings"] == []
    transcript_b = json.loads(storage.body(_transcript_key(TENANT_B, SURVEY_B, AUDIO_B_SHA256)))
    assert transcript_b["provider_pass"] == "skipped_no_entitlement"
    assert transcript_b["transcript"] is None
    # O export não é pago: funciona normalmente mesmo sem entitlement nenhum.
    assert _scene_key(TENANT_B, SURVEY_B) in storage.objects
    assert _attachments_key(TENANT_B, SURVEY_B) in storage.objects

    # ------------------------------------------------------------------------------------
    # Assertiva 8: contagem final exata — o tenant B não somou nenhuma chamada paga.
    # ------------------------------------------------------------------------------------
    assert len(photo_adapter.calls) == 1
    assert len(audio_adapter.calls) == 1
