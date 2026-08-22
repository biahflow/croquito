"""Rotas `/v1/surveys` (F-032, T8): a sincronização do levantamento de campo.

O que estes testes protegem, além do caminho feliz:

- **reenvio é normal**: rede de campo cai no meio do lote, e o aparelho reenvia. Nem a
  mesma `Idempotency-Key` nem o mesmo `operation_id` com chave nova podem gravar duas
  vezes, mover a versão ou publicar duas mensagens;
- **ordem por aparelho**: buraco ou regressão de `seq` é CONFLITO com o estado do
  servidor (prancha 6b), não erro de contrato e não gravação parcial — o servidor não
  escolhe versão vencedora e não apaga nada;
- **metadado antes da mídia** (prancha 6a): digest que o pacote não referencia não ganha
  URL assinada, para que não exista blob órfão no bucket do tenant;
- **integridade**: mídia divergente do declarado não vira `CONFIRMED` e não publica
  processamento; a publicação acontece na transição, uma única vez;
- **conclusão**: levantamento com mídia pendente não fecha, e fechar publica a exportação
  fora do request path;
- **papel e tenant**: quem não é `field_technician` não escreve; o escritório lê; e
  levantamento de outro tenant é `404`, nunca `403`.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

from botocore.exceptions import BotoCoreError
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from croquito_api.config import ApiSettings
from croquito_api.database import (
    AuditRecord,
    Database,
    SurveyMediaRecord,
    SurveyOperationRecord,
    SurveyRecord,
)
from croquito_api.main import create_app
from tests.fakes import FakeObjectStore, FakeQueue

_TENANT = "tenant-campo"
_SURVEY_ID = "8f1c1b0e-3d3e-4a1c-9a1a-2b3c4d5e6f70"
_DEVICE = "device-a"
_INSTANT = "2026-08-21T12:00:00Z"

PHOTO_BYTES = b"foto sintetica do levantamento"
PHOTO_SHA256 = hashlib.sha256(PHOTO_BYTES).hexdigest()
#: Mesmo TAMANHO da foto, conteúdo diferente: é o que exercita a conferência de digest, e
#: não a de tamanho, que dispararia antes.
CORRUPTED_PHOTO_BYTES = b"foto sintetica do levantament0"

AUDIO_BYTES = b"audio sintetico da observacao"
AUDIO_SHA256 = hashlib.sha256(AUDIO_BYTES).hexdigest()


def _client(tmp_path: Path) -> TestClient:
    database = Database(f"sqlite+pysqlite:///{tmp_path / 'surveys-api.db'}")
    database.create_schema()
    settings = ApiSettings(
        database_url=f"sqlite+pysqlite:///{tmp_path / 'surveys-api.db'}",
        artifact_bucket="croquito-test-artifacts",
        aws_region="sa-east-1",
        aws_endpoint_url="http://localhost:4566",
        queue_url=None,
        oidc_issuer=None,
        oidc_audience=None,
        web_origin="http://localhost:5173",
        allow_test_tokens=True,
    )
    application = create_app(settings=settings, database=database)
    application.state.artifact_store = FakeObjectStore()
    return TestClient(application)


def _headers(
    tenant: str = _TENANT,
    roles: str = "field_technician",
    *,
    key: str = "survey-request-001",
) -> dict[str, str]:
    return {
        "Authorization": f"Bearer test:{tenant}:tecnica-sintetica:{roles}",
        "Idempotency-Key": key,
    }


def _store(client: TestClient) -> FakeObjectStore:
    return cast(FakeObjectStore, cast(Any, client.app).state.artifact_store)


def _database(client: TestClient) -> Database:
    return cast(Database, cast(Any, client.app).state.database)


def _stored_survey(
    session: Session, *, tenant: str = _TENANT, survey_id: str = _SURVEY_ID
) -> SurveyRecord | None:
    """A raiz gravada, citada pela chave COMPOSTA: o `id` sozinho não identifica linha."""
    return session.get(SurveyRecord, {"tenant_id": tenant, "id": survey_id})


def _observed_queue(client: TestClient) -> FakeQueue:
    """Substitui apenas o transporte: o envelope publicado continua sendo o de produção."""
    queue = FakeQueue()
    processing_queue = cast(Any, client.app).state.queue
    processing_queue.queue_url = "http://localstack/queue"
    processing_queue.client = queue
    return queue


def _published_commands(queue: FakeQueue) -> list[str]:
    """Comandos publicados e ainda não consumidos; aqui não há worker para entregá-los."""
    return [str(json.loads(message["Body"])["command"]) for message in queue.messages]


def _media_ref(sha256: str, mime_type: str, byte_size: int) -> dict[str, Any]:
    return {"sha256": sha256, "mime_type": mime_type, "byte_size": byte_size}


def _packet(
    *,
    survey_id: str = _SURVEY_ID,
    status: str = "collecting",
    photo: bool = False,
    audio: bool = False,
) -> dict[str, Any]:
    """Pacote sintético mínimo, na forma exata de `croquito_core.field.SurveyPacket`."""
    anchors: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []
    if photo:
        anchors.append(
            {
                "id": "ma-1",
                "media_ref": _media_ref(PHOTO_SHA256, "image/jpeg", len(PHOTO_BYTES)),
                "point_id": "p1",
                "element_id": None,
                "note_id": None,
                "created_at": _INSTANT,
            }
        )
    if audio:
        observations.append(
            {
                "id": "obs-1",
                "text": "Piso trincado junto ao acesso.",
                "point_id": "p1",
                "element_id": None,
                "audio_media_ref": _media_ref(AUDIO_SHA256, "audio/webm", len(AUDIO_BYTES)),
                "created_at": _INSTANT,
            }
        )
    return {
        "survey_id": survey_id,
        "name": "Praça sintética",
        "order_id": "ordem-sintetica-1",
        "device_id": _DEVICE,
        "created_at": _INSTANT,
        "updated_at": _INSTANT,
        "points": [{"id": "p1", "x_mm": 0, "y_mm": 0, "created_at": _INSTANT}],
        "segments": [],
        "measurements": [],
        "media_anchors": anchors,
        "elements": [],
        "observations": observations,
        "gps_fixes": [],
        "arrival_context": None,
        "status": status,
        "waivers": [],
        "operations": [],
    }


def _operation(
    seq: int,
    *,
    operation_id: str | None = None,
    device_id: str = _DEVICE,
    survey_id: str = _SURVEY_ID,
) -> dict[str, Any]:
    return {
        "operation_id": operation_id or f"op-{device_id}-{seq}",
        "device_id": device_id,
        "survey_id": survey_id,
        "seq": seq,
        "type": "add_point",
        "payload": {"point_id": f"p{seq}"},
        "created_at": _INSTANT,
    }


def _sync(
    client: TestClient,
    *,
    operations: list[dict[str, Any]],
    packet: dict[str, Any] | None = None,
    key: str = "sync-1",
    tenant: str = _TENANT,
    roles: str = "field_technician",
    device_id: str = _DEVICE,
    survey_id: str = _SURVEY_ID,
) -> Any:
    return client.post(
        f"/v1/surveys/{survey_id}/operations",
        headers=_headers(tenant, roles, key=key),
        json={
            "device_id": device_id,
            "survey": packet if packet is not None else _packet(survey_id=survey_id),
            "operations": operations,
        },
    )


def _presign(
    client: TestClient,
    *,
    sha256: str = PHOTO_SHA256,
    mime_type: str = "image/jpeg",
    byte_size: int = len(PHOTO_BYTES),
    key: str = "presign-1",
    tenant: str = _TENANT,
    roles: str = "field_technician",
) -> Any:
    return client.post(
        f"/v1/surveys/{_SURVEY_ID}/media/presign",
        headers=_headers(tenant, roles, key=key),
        json={"sha256": sha256, "mime_type": mime_type, "byte_size": byte_size},
    )


def _upload_photo(client: TestClient, *, body: bytes = PHOTO_BYTES) -> str:
    """Sincroniza a âncora, assina e grava os bytes como o navegador faria no PUT."""
    presign = _presign(client)
    assert presign.status_code == 200
    object_key = str(presign.json()["object_key"])
    _store(client).put_direct(object_key=object_key, body=body, content_type="image/jpeg")
    return object_key


def _confirm(
    client: TestClient,
    *,
    sha256: str = PHOTO_SHA256,
    tenant: str = _TENANT,
    roles: str = "field_technician",
) -> Any:
    return client.post(
        f"/v1/surveys/{_SURVEY_ID}/media/{sha256}/confirm",
        headers=_headers(tenant, roles, key="confirm-1"),
    )


def test_primeira_sincronizacao_cria_o_levantamento_e_reconhece_o_lote(tmp_path: Path) -> None:
    """O levantamento nasce na primeira chamada, com o id que o aparelho gerou offline."""
    client = _client(tmp_path)

    response = _sync(client, operations=[_operation(1), _operation(2)])

    assert response.status_code == 200
    body = response.json()
    assert body["survey_id"] == _SURVEY_ID
    assert body["acked_operation_ids"] == ["op-device-a-1", "op-device-a-2"]
    assert body["version"] == 1
    assert body["last_seq_by_device"] == {_DEVICE: 2}
    with _database(client).sessions() as session:
        record = _stored_survey(session)
        assert record is not None
        assert record.tenant_id == _TENANT
        assert record.status == "OPEN"
        assert record.order_ref == "ordem-sintetica-1"
        # O histórico tem tabela própria e não é copiado para o snapshot: duas fontes da
        # mesma verdade divergiriam no primeiro reenvio.
        assert record.snapshot_json["operations"] == []
        assert record.snapshot_json["survey_id"] == _SURVEY_ID
        stored = list(session.scalars(select(SurveyOperationRecord)))
        assert [operation.seq for operation in stored] == [1, 2]
        assert {operation.tenant_id for operation in stored} == {_TENANT}
        actions = set(session.scalars(select(AuditRecord.action)))
        assert {"SURVEY_CREATED", "SURVEY_OPERATIONS_RECORDED"} <= actions


def test_reenvio_do_mesmo_lote_nao_duplica_operacao_nem_move_a_versao(tmp_path: Path) -> None:
    """Duas formas de reenvio: a mesma chave de idempotência e uma chave nova.

    A primeira é servida pelo registro de idempotência; a segunda chega de fato à rota e é
    reconhecida pelo `operation_id` já gravado. Nenhuma das duas pode regravar operação,
    mover a versão do levantamento ou falhar — reenviar é o comportamento normal do
    outbox, não um erro.
    """
    client = _client(tmp_path)
    lote = [_operation(1), _operation(2)]
    primeira = _sync(client, operations=lote, key="sync-1")
    assert primeira.status_code == 200

    mesma_chave = _sync(client, operations=lote, key="sync-1")
    chave_nova = _sync(client, operations=lote, key="sync-2")

    assert mesma_chave.status_code == 200
    assert mesma_chave.json() == primeira.json()
    assert chave_nova.status_code == 200
    assert chave_nova.json()["version"] == 1
    assert chave_nova.json()["acked_operation_ids"] == ["op-device-a-1", "op-device-a-2"]
    with _database(client).sessions() as session:
        assert len(list(session.scalars(select(SurveyOperationRecord)))) == 2
        record = _stored_survey(session)
        assert record is not None and record.version == 1


def test_lote_seguinte_avanca_a_versao_e_a_sequencia(tmp_path: Path) -> None:
    client = _client(tmp_path)
    _sync(client, operations=[_operation(1)], key="sync-1")

    segundo = _sync(client, operations=[_operation(2), _operation(3)], key="sync-2")

    assert segundo.status_code == 200
    assert segundo.json()["version"] == 2
    assert segundo.json()["last_seq_by_device"] == {_DEVICE: 3}


def test_buraco_na_sequencia_devolve_conflito_com_o_estado_do_servidor(tmp_path: Path) -> None:
    """Prancha 6b: o servidor entrega o que ele tem e deixa a decisão com a pessoa."""
    client = _client(tmp_path)
    _sync(client, operations=[_operation(1), _operation(2)], key="sync-1")

    com_buraco = _sync(client, operations=[_operation(4)], key="sync-2")

    assert com_buraco.status_code == 409
    detail = com_buraco.json()["detail"]
    assert detail["code"] == "SURVEY_CONFLICT"
    assert detail["details"]["server_version"] == 1
    assert detail["details"]["last_seq_by_device"] == {_DEVICE: 2}
    assert detail["details"]["server_snapshot"]["survey_id"] == _SURVEY_ID
    with _database(client).sessions() as session:
        # Recusa não grava lote parcial.
        assert len(list(session.scalars(select(SurveyOperationRecord)))) == 2


def test_regressao_de_sequencia_tambem_e_conflito(tmp_path: Path) -> None:
    """`seq` já consumido por outra operação é regressão, não reenvio: o `operation_id` é
    novo, então não há ack idempotente que o explique."""
    client = _client(tmp_path)
    _sync(client, operations=[_operation(1), _operation(2)], key="sync-1")

    regressao = _sync(client, operations=[_operation(2, operation_id="op-outra")], key="sync-2")

    assert regressao.status_code == 409
    assert regressao.json()["detail"]["code"] == "SURVEY_CONFLICT"


def test_levantamento_concluido_nao_aceita_operacao_nova(tmp_path: Path) -> None:
    client = _client(tmp_path)
    _concluir(client)

    depois = _sync(client, operations=[_operation(3)], key="sync-tarde")

    assert depois.status_code == 409
    assert depois.json()["detail"]["code"] == "SURVEY_CONFLICT"


def test_pacote_de_outro_levantamento_e_recusado_antes_de_tocar_o_banco(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)

    response = _sync(
        client,
        operations=[_operation(1, survey_id="outro-levantamento")],
        packet=_packet(survey_id="outro-levantamento"),
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "SURVEY_PACKET_INVALID"
    with _database(client).sessions() as session:
        assert _stored_survey(session) is None


def test_leitura_devolve_pacote_versao_sequencias_e_midia(tmp_path: Path) -> None:
    client = _client(tmp_path)
    _sync(client, operations=[_operation(1)], packet=_packet(photo=True), key="sync-1")
    _upload_photo(client)

    response = client.get(f"/v1/surveys/{_SURVEY_ID}", headers=_headers())

    assert response.status_code == 200
    body = response.json()
    assert body["version"] == 1
    assert body["status"] == "OPEN"
    assert body["survey"]["survey_id"] == _SURVEY_ID
    assert body["last_seq_by_device"] == {_DEVICE: 1}
    assert body["media"] == [
        {"sha256": PHOTO_SHA256, "mime_type": "image/jpeg", "status": "PRESIGNED"}
    ]


def test_o_escritorio_le_o_levantamento_com_papel_de_revisao(tmp_path: Path) -> None:
    """Quem revisa cota consulta o que veio do campo; escrever continua sendo do técnico."""
    client = _client(tmp_path)
    _sync(client, operations=[_operation(1)], key="sync-1")

    leitura = client.get(f"/v1/surveys/{_SURVEY_ID}", headers=_headers(roles="engineer"))
    escrita = _sync(client, operations=[_operation(2)], roles="engineer", key="sync-2")

    assert leitura.status_code == 200
    assert leitura.json()["survey"]["survey_id"] == _SURVEY_ID
    assert escrita.status_code == 403
    assert escrita.json()["detail"]["code"] == "FORBIDDEN"


def test_papel_sem_relacao_nem_le_nem_escreve(tmp_path: Path) -> None:
    client = _client(tmp_path)
    _sync(client, operations=[_operation(1)], key="sync-1")

    leitura = client.get(f"/v1/surveys/{_SURVEY_ID}", headers=_headers(roles="orcamentista"))

    assert leitura.status_code == 403
    assert leitura.json()["detail"]["code"] == "FORBIDDEN"


def test_levantamento_de_outro_tenant_e_indistinguivel_de_inexistente(tmp_path: Path) -> None:
    client = _client(tmp_path)
    _sync(client, operations=[_operation(1)], key="sync-1")

    leitura = client.get(f"/v1/surveys/{_SURVEY_ID}", headers=_headers(tenant="tenant-vizinho"))
    presign = _presign(client, tenant="tenant-vizinho")
    confirm = _confirm(client, tenant="tenant-vizinho")

    assert leitura.status_code == 404
    assert leitura.json()["detail"]["code"] == "NOT_FOUND"
    assert presign.status_code == 404
    assert confirm.status_code == 404


def test_presign_recusa_midia_que_o_pacote_nao_referencia(tmp_path: Path) -> None:
    """Prancha 6a, metadado antes da mídia: sem âncora não há URL assinada.

    A regra evita blob órfão no bucket do tenant — uma foto cujo digest não está preso a
    nenhum ponto, elemento ou nota do levantamento não tem quem a explique depois.
    """
    client = _client(tmp_path)
    _sync(client, operations=[_operation(1)], packet=_packet(), key="sync-1")

    response = _presign(client)

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "SURVEY_MEDIA_NOT_REFERENCED"
    with _database(client).sessions() as session:
        assert list(session.scalars(select(SurveyMediaRecord))) == []


def test_presign_grava_a_midia_sob_o_prefixo_do_tenant(tmp_path: Path) -> None:
    client = _client(tmp_path)
    _sync(client, operations=[_operation(1)], packet=_packet(photo=True), key="sync-1")

    response = _presign(client)

    assert response.status_code == 200
    body = response.json()
    assert body["object_key"] == (f"tenants/{_TENANT}/surveys/{_SURVEY_ID}/media/{PHOTO_SHA256}")
    assert body["headers"]["Content-Type"] == "image/jpeg"
    assert "x-amz-checksum-sha256" in body["headers"]
    with _database(client).sessions() as session:
        media = session.scalar(select(SurveyMediaRecord))
        assert media is not None
        assert media.status == "PRESIGNED"
        assert media.tenant_id == _TENANT
        audit = session.scalar(
            select(AuditRecord).where(AuditRecord.action == "SURVEY_MEDIA_PRESIGNED")
        )
        assert audit is not None
        # Nenhuma URL assinada entra em auditoria.
        assert "http" not in json.dumps(audit.metadata_json)


def test_confirmacao_recusa_midia_com_integridade_divergente(tmp_path: Path) -> None:
    client = _client(tmp_path)
    _sync(client, operations=[_operation(1)], packet=_packet(photo=True), key="sync-1")
    _upload_photo(client, body=CORRUPTED_PHOTO_BYTES)
    queue = _observed_queue(client)

    response = _confirm(client)

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "SURVEY_MEDIA_DIGEST_MISMATCH"
    assert _published_commands(queue) == []
    with _database(client).sessions() as session:
        media = session.scalar(select(SurveyMediaRecord))
        assert media is not None and media.status == "PRESIGNED"


def test_confirmacao_publica_uma_unica_analise_de_foto(tmp_path: Path) -> None:
    """A publicação acontece na transição `PRESIGNED → CONFIRMED`, e só nela."""
    client = _client(tmp_path)
    _sync(client, operations=[_operation(1)], packet=_packet(photo=True), key="sync-1")
    _upload_photo(client)
    queue = _observed_queue(client)

    primeira = _confirm(client)
    segunda = _confirm(client)

    assert primeira.status_code == 200
    assert primeira.json()["media"] == [
        {"sha256": PHOTO_SHA256, "mime_type": "image/jpeg", "status": "CONFIRMED"}
    ]
    assert segunda.status_code == 200
    assert _published_commands(queue) == ["analyze_survey_photo"]
    envelope = json.loads(queue.messages[0]["Body"])
    assert envelope["survey_id"] == _SURVEY_ID
    assert envelope["tenant_id"] == _TENANT
    # O envelope cita o id opaco da linha, nunca o digest nem a chave do objeto.
    assert set(envelope) == {"command", "survey_id", "media_id", "tenant_id"}


def test_confirmacao_de_audio_publica_a_transcricao(tmp_path: Path) -> None:
    client = _client(tmp_path)
    _sync(client, operations=[_operation(1)], packet=_packet(audio=True), key="sync-1")
    presign = _presign(
        client, sha256=AUDIO_SHA256, mime_type="audio/webm", byte_size=len(AUDIO_BYTES)
    )
    assert presign.status_code == 200
    _store(client).put_direct(
        object_key=str(presign.json()["object_key"]),
        body=AUDIO_BYTES,
        content_type="audio/webm",
    )
    queue = _observed_queue(client)

    response = _confirm(client, sha256=AUDIO_SHA256)

    assert response.status_code == 200
    assert _published_commands(queue) == ["transcribe_survey_audio"]


def test_fila_indisponivel_devolve_a_midia_para_pendente(tmp_path: Path) -> None:
    """Repetir o comando precisa continuar produzindo exatamente uma mensagem."""
    client = _client(tmp_path)
    _sync(client, operations=[_operation(1)], packet=_packet(photo=True), key="sync-1")
    _upload_photo(client)

    class RefusingQueue:
        def send_message(self, **_kwargs: Any) -> None:
            raise BotoCoreError()

    processing_queue = cast(Any, client.app).state.queue
    processing_queue.queue_url = "http://localstack/queue"
    processing_queue.client = RefusingQueue()

    recusada = _confirm(client)

    assert recusada.status_code == 503
    assert recusada.json()["detail"]["code"] == "PROCESSING_UNAVAILABLE"
    with _database(client).sessions() as session:
        media = session.scalar(select(SurveyMediaRecord))
        assert media is not None and media.status == "PRESIGNED"

    queue = _observed_queue(client)
    retomada = _confirm(client)

    assert retomada.status_code == 200
    assert _published_commands(queue) == ["analyze_survey_photo"]


def _concluir(client: TestClient) -> Any:
    """Caminho completo até a conclusão: coleta, foto confirmada e pacote concluído."""
    _sync(client, operations=[_operation(1)], packet=_packet(photo=True), key="sync-1")
    _upload_photo(client)
    assert _confirm(client).status_code == 200
    _sync(
        client,
        operations=[_operation(2)],
        packet=_packet(photo=True, status="concluded"),
        key="sync-2",
    )
    return client.post(
        f"/v1/surveys/{_SURVEY_ID}/complete",
        headers=_headers(key="complete-1"),
        json={"base_version": 2},
    )


def test_conclusao_com_midia_pendente_e_recusada(tmp_path: Path) -> None:
    client = _client(tmp_path)
    _sync(
        client,
        operations=[_operation(1)],
        packet=_packet(photo=True, status="concluded"),
        key="sync-1",
    )
    _presign(client)
    queue = _observed_queue(client)

    response = client.post(
        f"/v1/surveys/{_SURVEY_ID}/complete",
        headers=_headers(key="complete-1"),
        json={"base_version": 1},
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "SURVEY_MEDIA_PENDING"
    assert detail["details"]["pending_sha256"] == [PHOTO_SHA256]
    assert _published_commands(queue) == []
    with _database(client).sessions() as session:
        record = _stored_survey(session)
        assert record is not None and record.status == "OPEN"


def test_conclusao_exige_o_pacote_declarando_a_conclusao(tmp_path: Path) -> None:
    client = _client(tmp_path)
    _sync(client, operations=[_operation(1)], key="sync-1")

    response = client.post(
        f"/v1/surveys/{_SURVEY_ID}/complete",
        headers=_headers(key="complete-1"),
        json={"base_version": 1},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "SURVEY_NOT_CONCLUDED"


def test_conclusao_recusa_versao_defasada(tmp_path: Path) -> None:
    client = _client(tmp_path)
    _sync(
        client,
        operations=[_operation(1)],
        packet=_packet(status="concluded"),
        key="sync-1",
    )

    response = client.post(
        f"/v1/surveys/{_SURVEY_ID}/complete",
        headers=_headers(key="complete-1"),
        json={"base_version": 7},
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "SURVEY_CONFLICT"
    assert detail["details"]["server_version"] == 1


def test_conclusao_fecha_o_levantamento_e_publica_a_exportacao(tmp_path: Path) -> None:
    client = _client(tmp_path)
    queue = _observed_queue(client)

    response = _concluir(client)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "COMPLETED"
    assert body["version"] == 2
    assert _published_commands(queue) == ["analyze_survey_photo", "export_survey"]
    envelope = json.loads(queue.messages[-1]["Body"])
    assert envelope == {
        "command": "export_survey",
        "survey_id": _SURVEY_ID,
        "tenant_id": _TENANT,
    }
    with _database(client).sessions() as session:
        record = _stored_survey(session)
        assert record is not None and record.status == "COMPLETED"
        audit = session.scalar(select(AuditRecord).where(AuditRecord.action == "SURVEY_COMPLETED"))
        assert audit is not None


def test_conclusao_repetida_com_a_mesma_chave_reenfileira_sem_fechar_de_novo(
    tmp_path: Path,
) -> None:
    """Mensagem perdida no transporte precisa de caminho de volta, como em `POST /v1/jobs`."""
    client = _client(tmp_path)
    primeira = _concluir(client)
    assert primeira.status_code == 200
    queue = _observed_queue(client)

    repetida = client.post(
        f"/v1/surveys/{_SURVEY_ID}/complete",
        headers=_headers(key="complete-1"),
        json={"base_version": 2},
    )

    assert repetida.status_code == 200
    assert repetida.json() == primeira.json()
    assert _published_commands(queue) == ["export_survey"]


def test_conclusao_com_chave_nova_recusa_levantamento_ja_fechado(tmp_path: Path) -> None:
    client = _client(tmp_path)
    assert _concluir(client).status_code == 200

    outra = client.post(
        f"/v1/surveys/{_SURVEY_ID}/complete",
        headers=_headers(key="complete-2"),
        json={"base_version": 2},
    )

    assert outra.status_code == 409
    assert outra.json()["detail"]["code"] == "SURVEY_CONFLICT"


def test_o_mesmo_id_de_levantamento_coexiste_em_dois_tenants(tmp_path: Path) -> None:
    """O `id` nasce no aparelho, então a unicidade dele vale DENTRO do tenant.

    Com chave global, o levantamento de um tenant recusaria o identificador escolhido por
    outro — e o app já persistiu id que não é UUID (`survey-local`, do scaffold da fatia
    0), onde a colisão deixa de ser hipótese remota. As chaves compostas por
    `(tenant_id, id)` fazem os dois coexistirem, cada um com a sua própria sequência de
    operações, e nenhum dos dois enxerga o outro.
    """
    client = _client(tmp_path)
    _sync(client, operations=[_operation(1), _operation(2)], key="sync-1")

    vizinho = _sync(client, operations=[_operation(1)], tenant="tenant-vizinho", key="sync-1")

    assert vizinho.status_code == 200
    assert vizinho.json()["last_seq_by_device"] == {_DEVICE: 1}
    # A sequência de um não interfere na do outro, mesmo com `survey_id`, `device_id` e
    # `seq` iguais nas duas linhas.
    assert _sync(client, operations=[_operation(2)], tenant="tenant-vizinho", key="sync-2").json()[
        "last_seq_by_device"
    ] == {_DEVICE: 2}
    dono = client.get(f"/v1/surveys/{_SURVEY_ID}", headers=_headers())
    assert dono.status_code == 200
    assert dono.json()["version"] == 1
    with _database(client).sessions() as session:
        assert _stored_survey(session) is not None
        assert _stored_survey(session, tenant="tenant-vizinho") is not None
        assert len(list(session.scalars(select(SurveyOperationRecord)))) == 4


def test_sincronizacao_exige_idempotency_key(tmp_path: Path) -> None:
    client = _client(tmp_path)

    response = client.post(
        f"/v1/surveys/{_SURVEY_ID}/operations",
        headers={"Authorization": f"Bearer test:{_TENANT}:tecnica:field_technician"},
        json={"device_id": _DEVICE, "survey": _packet(), "operations": []},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"
