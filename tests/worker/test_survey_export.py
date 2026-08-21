"""Handler `export_survey` (F-032, T11): pacote de campo → observações do pipeline.

O que estes testes protegem, além do caminho feliz:

- **o portão continua fechado**: a cena produzida NÃO é exportável, nasce sem aprovação,
  sem entidade marcada para export e sem `exact`; e uma medida confirmada que não bate com
  a geometria observada é apanhada por `export_errors()`, não silenciada;
- **nada de geometria inventada**: medida sem segmento observado entre os pontos citados
  (ou ancorada em elemento) vira anexo e issue, nunca associação por proximidade; kind sem
  correspondente fiel no scene graph também;
- **unidade e eixo**: mm inteiro vira metro por `Decimal`, sem contaminação de `float`, e
  o eixo Y é espelhado como no resto do pipeline (tela desce, desenho sobe);
- **defesa em profundidade**: levantamento não concluído, mídia ainda não confirmada e
  snapshot fora do contrato param com código estável, mesmo que a rota já tenha checado;
- **idempotência**: reprocessar a mesma mensagem reescreve os MESMOS dois objetos.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest

from croquito_api.database import (
    Database,
    SurveyMediaRecord,
    SurveyOperationRecord,
    SurveyRecord,
)
from croquito_core.field import SurveyPacket
from croquito_core.models import IssueSeverity, IssueStatus, Precision, SceneRevision
from croquito_worker.local_queue import (
    LocalQueueWorker,
    LocalWorkerSettings,
    UnroutableMessageError,
)
from croquito_worker.survey_export import SurveyExportError
from tests.fakes import FakeObjectStore, FakeQueue

TENANT_ID = "tenant-campo"
OTHER_TENANT_ID = "tenant-vizinho"
SURVEY_ID = "00000000-0000-7000-8000-0000000009f0"
DEVICE_ID = "device-campo-1"
INSTANT = "2026-08-21T12:00:00Z"

SCENE_KEY = f"tenants/{TENANT_ID}/surveys/{SURVEY_ID}/export/scene.json"
ATTACHMENTS_KEY = f"tenants/{TENANT_ID}/surveys/{SURVEY_ID}/export/attachments.json"

PHOTO_SHA256 = hashlib.sha256(b"foto sintetica").hexdigest()
AUDIO_SHA256 = hashlib.sha256(b"audio sintetico").hexdigest()
ACCESS_SHA256 = hashlib.sha256(b"foto do acesso").hexdigest()


def _media_ref(sha256: str, mime_type: str, byte_size: int) -> dict[str, Any]:
    return {"sha256": sha256, "mime_type": mime_type, "byte_size": byte_size}


def _point(point_id: str, x_mm: int, y_mm: int) -> dict[str, Any]:
    return {"id": point_id, "x_mm": x_mm, "y_mm": y_mm, "created_at": INSTANT}


def _segment(segment_id: str, from_point_id: str, to_point_id: str) -> dict[str, Any]:
    return {
        "id": segment_id,
        "from_point_id": from_point_id,
        "to_point_id": to_point_id,
        "created_at": INSTANT,
    }


def _measurement(
    measurement_id: str,
    *,
    value_mm: int,
    kind: str = "length",
    status: str = "confirmed",
    from_point_id: str | None = None,
    to_point_id: str | None = None,
    element_id: str | None = None,
    instrument: str = "Trena laser",
) -> dict[str, Any]:
    return {
        "id": measurement_id,
        "value_mm": value_mm,
        "kind": kind,
        "from_point_id": from_point_id,
        "to_point_id": to_point_id,
        "second_from_point_id": None,
        "second_to_point_id": None,
        "element_id": element_id,
        "instrument": instrument,
        "status": status,
        "justification": None,
        "created_at": INSTANT,
    }


def _packet(**overrides: Any) -> dict[str, Any]:
    """Levantamento sintético completo, validado pelo contrato antes de virar snapshot.

    A prancha sintética é um "L": dois segmentos ligando três pontos, mais um ponto solto
    que o técnico marcou sem ligar a nada.
    """
    packet: dict[str, Any] = {
        "survey_id": SURVEY_ID,
        "name": "Praça sintética",
        "order_id": "ordem-sintetica-1",
        "device_id": DEVICE_ID,
        "created_at": INSTANT,
        "updated_at": INSTANT,
        "points": [
            _point("p1", 0, 0),
            _point("p2", 5000, 0),
            _point("p3", 5000, 3000),
            _point("p4", 1000, 1000),
        ],
        "segments": [_segment("s1", "p1", "p2"), _segment("s2", "p2", "p3")],
        "measurements": [
            _measurement("m1", value_mm=5000, from_point_id="p1", to_point_id="p2"),
            _measurement("m2", value_mm=3010, status="draft", from_point_id="p2", to_point_id="p3"),
            _measurement("m3", value_mm=90, kind="angle", from_point_id="p1", to_point_id="p2"),
            _measurement("m4", value_mm=150, kind="level", element_id="e1"),
            _measurement("m5", value_mm=2000, from_point_id="p1", to_point_id="p4"),
        ],
        "media_anchors": [
            {
                "id": "ma-1",
                "media_ref": _media_ref(PHOTO_SHA256, "image/jpeg", 14),
                "point_id": "p1",
                "element_id": None,
                "note_id": None,
                "created_at": INSTANT,
            }
        ],
        "elements": [
            {"id": "e1", "label": "Banco de concreto", "point_ids": ["p4"], "created_at": INSTANT}
        ],
        "observations": [
            {
                "id": "obs-1",
                "text": "Piso trincado junto ao acesso.",
                "point_id": "p1",
                "element_id": None,
                "audio_media_ref": _media_ref(AUDIO_SHA256, "audio/webm", 15),
                "created_at": INSTANT,
            }
        ],
        "gps_fixes": [{"lat": -22.9, "lng": -43.2, "accuracy_m": 8.0}],
        "arrival_context": {
            "instrument": "Trena laser",
            "reference_note": "Portão da rua principal.",
            "gps": {"lat": -22.9, "lng": -43.2, "accuracy_m": 8.0},
            "access_media_ref": _media_ref(ACCESS_SHA256, "image/jpeg", 14),
            "arrived_at": INSTANT,
        },
        "status": "concluded",
        "waivers": [
            {
                "id": "w1",
                "finding_code": "REQUIRED_ITEM_PENDING",
                "ref_key": "foto-acesso",
                "justification": "Acesso lateral interditado pela obra.",
                "created_at": INSTANT,
            }
        ],
        "operations": [],
    }
    packet.update(overrides)
    # Validar aqui garante que a fixture é um pacote real, não uma forma parecida.
    return SurveyPacket.model_validate(packet).model_dump(mode="json")


def _operations() -> list[dict[str, Any]]:
    """Histórico do outbox na forma que o app publica: `{"<objeto>": {..., "id": ...}}`."""
    return [
        {"id": "op-1", "seq": 1, "type": "point.add", "payload": {"point": {"id": "p1"}}},
        {"id": "op-2", "seq": 2, "type": "point.add", "payload": {"point": {"id": "p2"}}},
        {"id": "op-3", "seq": 3, "type": "segment.add", "payload": {"segment": {"id": "s1"}}},
        {
            "id": "op-4",
            "seq": 4,
            "type": "measurement.add",
            "payload": {"measurement": {"id": "m1"}},
        },
        {"id": "op-5", "seq": 5, "type": "survey.conclude", "payload": {}},
    ]


def _seed(
    tmp_path: Path,
    *,
    status: str = "COMPLETED",
    snapshot: dict[str, Any] | None = None,
    media_status: str = "CONFIRMED",
    tenant_id: str = TENANT_ID,
) -> str:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'survey-export.db'}"
    database = Database(database_url)
    database.create_schema()
    with database.sessions.begin() as session:
        session.add(
            SurveyRecord(
                id=SURVEY_ID,
                tenant_id=tenant_id,
                name="Praça sintética",
                order_ref="ordem-sintetica-1",
                status=status,
                version=3,
                snapshot_json=snapshot if snapshot is not None else _packet(),
            )
        )
        session.flush()
        for index, (sha256, mime_type, size) in enumerate(
            [
                (PHOTO_SHA256, "image/jpeg", 14),
                (AUDIO_SHA256, "audio/webm", 15),
                (ACCESS_SHA256, "image/jpeg", 14),
            ]
        ):
            session.add(
                SurveyMediaRecord(
                    id=f"media-{index}",
                    tenant_id=tenant_id,
                    survey_id=SURVEY_ID,
                    sha256=sha256,
                    mime_type=mime_type,
                    byte_size=size,
                    object_key=f"tenants/{tenant_id}/surveys/{SURVEY_ID}/media/{sha256}",
                    status=media_status,
                )
            )
        for operation in _operations():
            session.add(
                SurveyOperationRecord(
                    id=str(operation["id"]),
                    tenant_id=tenant_id,
                    survey_id=SURVEY_ID,
                    device_id=DEVICE_ID,
                    seq=int(cast(int, operation["seq"])),
                    type=str(operation["type"]),
                    payload_json=operation["payload"],
                    created_at=datetime.now(UTC),
                )
            )
    return database_url


def _worker(database_url: str) -> tuple[LocalQueueWorker, FakeObjectStore]:
    worker = LocalQueueWorker(
        LocalWorkerSettings(
            database_url=database_url,
            queue_url="http://localstack/queue",
            aws_region="sa-east-1",
            aws_endpoint_url="http://localstack",
        )
    )
    queue = FakeQueue()
    worker.client = queue
    storage = FakeObjectStore()
    worker.s3_client = storage
    return worker, storage


def _message(**overrides: Any) -> dict[str, Any]:
    """O corpo EXATO publicado por `enqueue_survey_export` (`services/api`)."""
    return {
        "command": "export_survey",
        "survey_id": SURVEY_ID,
        "tenant_id": TENANT_ID,
        **overrides,
    }


def _run(tmp_path: Path, **seed: Any) -> tuple[FakeObjectStore, LocalQueueWorker]:
    worker, storage = _worker(_seed(tmp_path, **seed))
    assert worker.dispatch(_message()) == 1
    return storage, worker


def _scene(storage: FakeObjectStore) -> SceneRevision:
    """Relê a cena pelo contrato: o que o teste inspeciona é o artefato gravado."""
    return SceneRevision.model_validate(json.loads(storage.body(SCENE_KEY)))


def _attachments(storage: FakeObjectStore) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(storage.body(ATTACHMENTS_KEY)))


def test_levantamento_concluido_vira_cena_de_observacao_e_indice_de_anexos(
    tmp_path: Path,
) -> None:
    """Caminho feliz: dois artefatos em chave estável, geometria só dos segmentos."""
    storage, _ = _run(tmp_path)

    assert sorted(storage.objects) == [ATTACHMENTS_KEY, SCENE_KEY]
    assert storage.objects[SCENE_KEY].content_type == "application/json"
    scene = _scene(storage)
    # O `job_id` é namespace de cena de campo; não existe `JobRecord` com este id.
    assert scene.job_id == UUID(SURVEY_ID)
    assert scene.version == 1
    assert [entity.kind.value for entity in scene.entities] == ["line", "line"]
    # s1 tem medida confirmada; s2 só tem rascunho e continua sem resolução.
    assert [entity.precision for entity in scene.entities] == [
        Precision.APPROXIMATE,
        Precision.UNRESOLVED,
    ]
    assert [entity.layer.value for entity in scene.entities] == ["APROXIMADO", "REVISAO"]
    assert [measurement.confirmed for measurement in scene.measurements] == [True, False]
    attachments = _attachments(storage)
    assert attachments["scene_object_key"] == SCENE_KEY
    assert {entry["role"] for entry in attachments["media"]} == {
        "media_anchor",
        "observation_audio",
        "arrival_access",
    }
    assert attachments["media"][0]["object_key"] == (
        f"tenants/{TENANT_ID}/surveys/{SURVEY_ID}/media/{PHOTO_SHA256}"
    )
    assert [note["id"] for note in attachments["notes"]] == ["obs-1"]
    assert attachments["elements"] == [
        {"id": "e1", "label": "Banco de concreto", "point_ids": ["p4"]}
    ]
    assert attachments["arrival_context"]["reference_note"] == "Portão da rua principal."
    assert attachments["gps_fixes"] == [{"lat": -22.9, "lng": -43.2, "accuracy_m": 8.0}]


def test_a_cena_de_campo_nao_e_exportavel(tmp_path: Path) -> None:
    """Fail-closed: o portão do scene graph segura o artefato produzido aqui.

    Duas afirmações distintas. A primeira é sobre o artefato como ele é gravado: nenhuma
    entidade sai em CAD (`export=False`), então o portão para na aprovação ausente. A
    segunda é o contrafactual que prova por que o resto do portão também seguraria: com
    `approved` e `export` forçados a `True` — o que este módulo NUNCA escreve — aparecem
    `UNRESOLVED_ENTITY` e `APPROXIMATION_NOT_ACCEPTED`, porque a observação de campo não
    passa de `approximate` e ninguém aceitou aproximação alguma.
    """
    storage, _ = _run(tmp_path)
    scene = _scene(storage)

    assert scene.approved is False
    assert scene.accepted_approximation_ids == set()
    assert all(entity.export is False for entity in scene.entities)
    assert all(entity.precision is not Precision.EXACT for entity in scene.entities)
    assert scene.export_errors() == ["SCENE_NOT_APPROVED"]

    forced = SceneRevision.model_validate(
        {
            **json.loads(storage.body(SCENE_KEY)),
            "approved": True,
            "entities": [
                {**entity, "export": True}
                for entity in json.loads(storage.body(SCENE_KEY))["entities"]
            ],
        }
    )
    errors = forced.export_errors()
    assert any(error.startswith("UNRESOLVED_ENTITY:") for error in errors)
    assert any(error.startswith("APPROXIMATION_NOT_ACCEPTED:") for error in errors)


def test_medida_confirmada_divergente_da_geometria_e_apanhada_pelo_portao(
    tmp_path: Path,
) -> None:
    """Trena e croqui discordando viram `MEASUREMENT_MISMATCH`, não conciliação silenciosa."""
    snapshot = _packet(
        measurements=[
            _measurement("m1", value_mm=4900, from_point_id="p1", to_point_id="p2"),
        ]
    )
    storage, _ = _run(tmp_path, snapshot=snapshot)

    scene = _scene(storage)
    assert [error.split(":")[0] for error in scene.export_errors()] == [
        "SCENE_NOT_APPROVED",
        "MEASUREMENT_MISMATCH",
    ]


def test_milimetro_vira_metro_com_eixo_y_espelhado_e_decimal_exato(tmp_path: Path) -> None:
    """mm inteiro → metro: Y espelhado (tela desce, desenho sobe) e `Decimal` sem float."""
    snapshot = _packet(
        measurements=[
            _measurement("m2", value_mm=1234, status="draft", from_point_id="p2", to_point_id="p3")
        ]
    )
    storage, _ = _run(tmp_path, snapshot=snapshot)

    scene = _scene(storage)
    primeiro, segundo = scene.entities
    assert (primeiro.geometry.start.x, primeiro.geometry.start.y) == (0.0, 0.0)  # type: ignore[union-attr]
    assert (primeiro.geometry.end.x, primeiro.geometry.end.y) == (5.0, 0.0)  # type: ignore[union-attr]
    # p3 = (5000, 3000) na tela; na cena, Y cresce para cima.
    assert (segundo.geometry.end.x, segundo.geometry.end.y) == (5.0, -3.0)  # type: ignore[union-attr]
    # O documento gravado carrega o decimal escrito, não a aproximação binária de 1,234.
    assert json.loads(storage.body(SCENE_KEY))["measurements"][0]["value_si"] == "1.234"
    assert scene.measurements[0].value_si == Decimal("1.234")
    assert scene.measurements[0].raw_text == "1234 mm"
    assert scene.measurements[0].unit.value == "m"


def test_observacao_sem_geometria_vira_issue_e_anexo(tmp_path: Path) -> None:
    """Nada é descartado em silêncio, e nada vira geometria por proximidade."""
    storage, _ = _run(tmp_path)

    scene = _scene(storage)
    codes = [issue.code for issue in scene.issues]
    assert codes.count("FIELD_POINT_WITHOUT_SEGMENT") == 1  # p4, marcado e não ligado
    assert codes.count("FIELD_ANGLE_UNIT_UNDECIDED") == 1  # m3, unidade indecisa em campo
    assert codes.count("FIELD_MEASUREMENT_NOT_PLANIMETRIC") == 1  # m4, cota de nível
    assert codes.count("FIELD_MEASUREMENT_WITHOUT_SEGMENT") == 1  # m5, sem segmento p1→p4
    assert all(issue.severity is not IssueSeverity.CRITICAL for issue in scene.issues)
    assert all(issue.status is IssueStatus.OPEN for issue in scene.issues)
    preservadas = _attachments(storage)["measurements_without_scene_entry"]
    assert {entry["id"] for entry in preservadas} == {"m3", "m4", "m5"}
    assert {entry["value_mm"] for entry in preservadas} == {90, 150, 2000}
    # A medida ancorada em elemento não foi amarrada a segmento nenhum.
    assert all(entry["reason_code"] for entry in preservadas)


def test_waiver_de_conclusao_vira_issue_nao_critica(tmp_path: Path) -> None:
    """A pendência que o técnico manteve chega ao escritório visível e em aberto."""
    storage, _ = _run(tmp_path)

    scene = _scene(storage)
    waiver_issues = [
        issue for issue in scene.issues if issue.code == "FIELD_WAIVER_REQUIRED_ITEM_PENDING"
    ]
    assert len(waiver_issues) == 1
    assert waiver_issues[0].severity is IssueSeverity.WARNING
    assert waiver_issues[0].status is IssueStatus.OPEN
    assert _attachments(storage)["waivers"][0]["issue_code"] == (
        "FIELD_WAIVER_REQUIRED_ITEM_PENDING"
    )


def test_provenance_amarra_a_observacao_ao_levantamento_e_a_operacao_de_origem(
    tmp_path: Path,
) -> None:
    """Toda entidade e medida diz de onde veio: levantamento, aparelho, objeto e operação."""
    storage, _ = _run(tmp_path)

    scene = _scene(storage)
    provenance = scene.entities[0].provenance
    assert provenance is not None
    assert provenance.source_type == "field_survey"
    assert provenance.source_ids == [SURVEY_ID, DEVICE_ID, "s1", "op-3"]
    assert provenance.summary_code == "FIELD_SURVEY"
    confirmada, rascunho = scene.measurements
    assert confirmada.provenance is not None
    assert confirmada.provenance.summary_code == "FIELD_CONFIRMED"
    assert confirmada.provenance.source_ids == [SURVEY_ID, DEVICE_ID, "m1", "op-4"]
    assert rascunho.provenance is not None
    # `m2` não tem operação no histórico sintético: a provenance encolhe, não inventa id.
    assert rascunho.provenance.source_ids == [SURVEY_ID, DEVICE_ID, "m2"]


def test_reprocessar_a_mesma_mensagem_reescreve_os_mesmos_objetos(tmp_path: Path) -> None:
    """Reentrega é normal na fila: a chave é estável e nada acumula."""
    worker, storage = _worker(_seed(tmp_path))

    assert worker.dispatch(_message()) == 1
    primeiro = storage.body(SCENE_KEY)
    assert worker.dispatch(_message()) == 1

    assert sorted(storage.objects) == [ATTACHMENTS_KEY, SCENE_KEY]
    assert len(storage.puts) == 4
    segundo = _scene(storage)
    assert len(segundo.entities) == len(SceneRevision.model_validate(json.loads(primeiro)).entities)


def test_levantamento_ainda_aberto_nao_exporta(tmp_path: Path) -> None:
    """Defesa em profundidade: a rota já checou, e o worker checa de novo."""
    worker, storage = _worker(_seed(tmp_path, status="OPEN"))

    with pytest.raises(SurveyExportError) as error:
        worker.dispatch(_message())

    assert error.value.code == "SURVEY_NOT_COMPLETED"
    assert storage.objects == {}


def test_midia_referenciada_sem_confirmacao_nao_exporta(tmp_path: Path) -> None:
    """Foto que ainda está no aparelho não vira anexo de artefato publicado."""
    worker, storage = _worker(_seed(tmp_path, media_status="PRESIGNED"))

    with pytest.raises(SurveyExportError) as error:
        worker.dispatch(_message())

    assert error.value.code == "SURVEY_MEDIA_PENDING"
    assert storage.objects == {}


def test_snapshot_fora_do_contrato_para_com_erro_estruturado(tmp_path: Path) -> None:
    """Snapshot corrompido é erro nomeado, não exceção de parsing vazando do Pydantic."""
    worker, storage = _worker(_seed(tmp_path, snapshot={"survey_id": SURVEY_ID, "points": "nao"}))

    with pytest.raises(SurveyExportError) as error:
        worker.dispatch(_message())

    assert error.value.code == "SURVEY_SNAPSHOT_INVALID"
    assert storage.objects == {}


def test_snapshot_de_outro_levantamento_para_com_erro_estruturado(tmp_path: Path) -> None:
    """A raiz e o pacote têm de falar do mesmo levantamento."""
    worker, _ = _worker(_seed(tmp_path, snapshot=_packet(survey_id="outro-levantamento")))

    with pytest.raises(SurveyExportError) as error:
        worker.dispatch(_message())

    assert error.value.code == "SURVEY_SNAPSHOT_INVALID"


def test_levantamento_de_outro_tenant_nao_e_encontrado(tmp_path: Path) -> None:
    """Escopo por tenant em toda consulta: o mesmo id noutro tenant não existe aqui."""
    worker, storage = _worker(_seed(tmp_path, tenant_id=OTHER_TENANT_ID))

    with pytest.raises(SurveyExportError) as error:
        worker.dispatch(_message())

    assert error.value.code == "SURVEY_NOT_FOUND"
    assert storage.objects == {}


def test_mensagem_sem_survey_id_nao_e_roteavel(tmp_path: Path) -> None:
    """Envelope quebrado é defeito do publicador; reentregar daria o mesmo resultado."""
    worker, _ = _worker(_seed(tmp_path))

    with pytest.raises(UnroutableMessageError):
        worker.dispatch({"command": "export_survey", "tenant_id": TENANT_ID})


def test_log_carrega_contagens_e_nenhum_dado_de_campo(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Log de operação: id opaco, estágio, contagens e duração — nada do que foi coletado."""
    worker, _ = _worker(_seed(tmp_path))

    with caplog.at_level("INFO", logger="croquito_worker.local_queue"):
        worker.dispatch(_message())

    registro = next(
        record for record in caplog.records if record.message.startswith("survey_export_completed")
    )
    assert registro.stage == "SURVEY_EXPORT"  # type: ignore[attr-defined]
    assert registro.entities == 2  # type: ignore[attr-defined]
    assert registro.measurements == 2  # type: ignore[attr-defined]
    assert registro.media == 3  # type: ignore[attr-defined]
    assert isinstance(registro.duration_ms, int)  # type: ignore[attr-defined]
    linha = registro.getMessage()
    for proibido in ["Praça", "Piso trincado", "5000", "-22.9", PHOTO_SHA256]:
        assert proibido not in linha


def test_consumo_pela_fila_usa_o_corpo_publicado_pela_api(tmp_path: Path) -> None:
    """O comando chega pelo transporte, sem `job_id`, e é reconhecido pelo despacho."""
    worker, storage = _worker(_seed(tmp_path))
    queue = cast(FakeQueue, worker.client)
    queue.send_message(MessageBody=json.dumps(_message()))

    assert worker.run_once() == 1

    assert queue.commands() == ["export_survey"]
    assert sorted(storage.objects) == [ATTACHMENTS_KEY, SCENE_KEY]
