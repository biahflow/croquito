"""Handler `transcribe_survey_audio` (F-032, T13): nota de voz → rascunho de transcrição.

O que estes testes protegem:

- **a via paga não sai de graça nem por engano**: sem caminho habilitado o passe é
  `skipped_disabled`; com fixture injetada mas sem entitlement contratual ativo é
  `skipped_no_entitlement` — e, nos dois casos, o contador do adapter fica em ZERO. Nenhum
  teste desta suíte chama a Groq, a OpenAI ou qualquer rede;
- **o artefato existe mesmo quando a transcrição não acontece**: metadados, vínculo com a
  nota e o motivo do desfecho ficam gravados, de modo que ligar a chave e reprocessar seja
  um caminho e não uma adivinhação;
- **o rascunho é rascunho**: `status` é sempre `draft`, nada vira medida, nada é confirmado
  e `survey_records`/`survey_media_records` saem da execução exatamente como entraram;
- **o vínculo com a nota é conveniência, não condição**: áudio órfão e snapshot ilegível
  viram aviso estruturado, nunca perda da transcrição;
- **erros estruturados**: mídia de outro tenant, mídia não confirmada, container não
  suportado e bytes ausentes param com código estável;
- **idempotência**: reprocessar reescreve a MESMA chave, derivada do digest do áudio;
- **log sem conteúdo**: id opaco, desfecho, contagens e duração — nunca o que foi dito.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest

from croquito_api.database import (
    Database,
    SurveyMediaRecord,
    SurveyRecord,
    TenantAiProcessingEntitlementRecord,
)
from croquito_core.field import SurveyPacket
from croquito_worker.local_queue import (
    LocalQueueWorker,
    LocalWorkerSettings,
    UnroutableMessageError,
)
from croquito_worker.providers import (
    PROMPT_SPECS,
    AudioTranscriptionOutput,
    PromptTask,
    ProviderExecution,
    ProviderExecutionError,
    ProviderFailureCode,
    ProviderName,
    ProviderRequest,
    ProviderSuite,
    ProviderUsage,
)
from croquito_worker.survey_transcription import (
    NOTE_NOT_FOUND,
    SNAPSHOT_UNREADABLE,
    TRANSCRIPT_SCHEMA,
    SurveyTranscriptionError,
)
from tests.fakes import FakeObjectStore, FakeQueue

TENANT_ID = "tenant-campo"
OTHER_TENANT_ID = "tenant-vizinho"
SURVEY_ID = "00000000-0000-7000-8000-0000000009f0"
MEDIA_ID = "00000000-0000-7000-8000-00000000ac01"
NOTE_ID = "obs-1"
INSTANT = "2026-08-21T12:00:00Z"

AUDIO_BYTES = b"croquito-synthetic-audio::nota-de-voz" * 3
"""Bytes sintéticos: nada neste caminho decodifica áudio, e gravação de gente não é fixture."""

TRANSCRIPT_TEXT = "O muro do fundo tem 12,40 m e o degrau é de 0,18 m."


def _packet(*, sha256: str, with_note: bool = True) -> dict[str, Any]:
    """Snapshot mínimo VALIDADO pelo contrato: pacote real, não uma forma parecida com ele."""
    packet: dict[str, Any] = {
        "survey_id": SURVEY_ID,
        "name": "Praça sintética",
        "order_id": "ordem-sintetica-1",
        "device_id": "device-campo-1",
        "created_at": INSTANT,
        "updated_at": INSTANT,
        "points": [{"id": "p1", "x_mm": 0, "y_mm": 0, "created_at": INSTANT}],
        "segments": [],
        "measurements": [],
        "media_anchors": [],
        "elements": [],
        "observations": (
            [
                {
                    "id": NOTE_ID,
                    "text": "",
                    "point_id": "p1",
                    "element_id": None,
                    "audio_media_ref": {
                        "sha256": sha256,
                        "mime_type": "audio/webm",
                        "byte_size": len(AUDIO_BYTES),
                    },
                    "created_at": INSTANT,
                }
            ]
            if with_note
            else []
        ),
        "gps_fixes": [],
        "arrival_context": None,
        "status": "concluded",
        "waivers": [],
        "operations": [],
    }
    return SurveyPacket.model_validate(packet).model_dump(mode="json")


def _transcript_key(sha256: str) -> str:
    return f"tenants/{TENANT_ID}/surveys/{SURVEY_ID}/transcripts/{sha256}.json"


@dataclass
class CountingAdapter:
    """Adapter de teste que CONTA chamadas — o oráculo de "nada pago aconteceu"."""

    provider: ProviderName = ProviderName.GROQ
    model_id: str = "whisper-large-v3-turbo"
    text: str = TRANSCRIPT_TEXT
    failure: ProviderFailureCode | None = None
    calls: list[ProviderRequest] = field(default_factory=list)

    def execute(self, request: ProviderRequest) -> ProviderExecution:
        self.calls.append(request)
        if self.failure is not None:
            raise ProviderExecutionError(self.failure)
        return ProviderExecution(
            provider=self.provider,
            model_id=self.model_id,
            prompt=request.prompt,
            input_digest=request.image_sha256,
            latency_ms=9,
            usage=ProviderUsage(estimated_cost_usd=Decimal("0.01")),
            raw_response_ref=f"tenants/{TENANT_ID}/surveys/{SURVEY_ID}/providers/raw.json",
            output=AudioTranscriptionOutput(text=self.text, language="portuguese", duration_s=4.5),
        )


@dataclass
class ForbiddenAdapter:
    """Braço de VISÃO da suite: chamá-lo daqui seria a transcrição usando o provider errado."""

    def execute(self, request: ProviderRequest) -> ProviderExecution:
        raise AssertionError(f"braço de visão chamado pela transcrição: {request.task}")


def _suite(
    primary: CountingAdapter | None = None,
    fallback: CountingAdapter | None = None,
    *,
    with_primary: bool = True,
) -> ProviderSuite:
    return ProviderSuite(
        anthropic=ForbiddenAdapter(),
        transcription=(primary or CountingAdapter()) if with_primary else None,
        transcription_fallback=fallback,
    )


def _seed(
    tmp_path: Path,
    *,
    audio: bytes = AUDIO_BYTES,
    tenant_id: str = TENANT_ID,
    media_status: str = "CONFIRMED",
    mime_type: str = "audio/webm",
    entitlement_status: str | None = None,
    store_bytes: bool = True,
    snapshot: dict[str, Any] | None = None,
    with_note: bool = True,
) -> tuple[str, FakeObjectStore, str]:
    """Banco + storage com uma nota de voz confirmada; devolve `(url, storage, sha256)`."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    sha256 = hashlib.sha256(audio).hexdigest()
    object_key = f"tenants/{tenant_id}/surveys/{SURVEY_ID}/media/{sha256}"
    database_url = f"sqlite+pysqlite:///{tmp_path / 'survey-audio.db'}"
    database = Database(database_url)
    database.create_schema()
    with database.sessions.begin() as session:
        session.add(
            SurveyRecord(
                id=SURVEY_ID,
                tenant_id=tenant_id,
                name="Praça sintética",
                order_ref="ordem-sintetica-1",
                status="OPEN",
                version=3,
                snapshot_json=(
                    _packet(sha256=sha256, with_note=with_note) if snapshot is None else snapshot
                ),
            )
        )
        session.flush()
        session.add(
            SurveyMediaRecord(
                id=MEDIA_ID,
                tenant_id=tenant_id,
                survey_id=SURVEY_ID,
                sha256=sha256,
                mime_type=mime_type,
                byte_size=len(audio),
                object_key=object_key,
                status=media_status,
            )
        )
        if entitlement_status is not None:
            session.add(
                TenantAiProcessingEntitlementRecord(
                    id="entitlement-1",
                    tenant_id=tenant_id,
                    status=entitlement_status,
                    agreement_reference="contrato-sintetico-1",
                    authorized_by="platform-operator",
                    authorized_at=datetime.now(UTC),
                )
            )
    storage = FakeObjectStore()
    if store_bytes:
        storage.put_direct(object_key=object_key, body=audio, content_type=mime_type)
    return database_url, storage, sha256


def _worker(
    database_url: str, storage: FakeObjectStore, *, suite: ProviderSuite | None = None
) -> LocalQueueWorker:
    worker = LocalQueueWorker(
        LocalWorkerSettings(
            database_url=database_url,
            queue_url="http://localstack/queue",
            aws_region="sa-east-1",
            aws_endpoint_url="http://localstack",
        ),
        provider_suite=suite,
    )
    worker.client = FakeQueue()
    worker.s3_client = storage
    return worker


def _message(**overrides: Any) -> dict[str, Any]:
    """O corpo EXATO publicado pelo `confirm` de mídia de áudio (`services/api`)."""
    return {
        "command": "transcribe_survey_audio",
        "survey_id": SURVEY_ID,
        "media_id": MEDIA_ID,
        "tenant_id": TENANT_ID,
        **overrides,
    }


def _run(
    tmp_path: Path, *, suite: ProviderSuite | None = None, **seed: Any
) -> tuple[dict[str, Any], FakeObjectStore, LocalQueueWorker]:
    database_url, storage, sha256 = _seed(tmp_path, **seed)
    worker = _worker(database_url, storage, suite=suite)
    assert worker.dispatch(_message()) == 1
    document = cast(dict[str, Any], json.loads(storage.body(_transcript_key(sha256))))
    return document, storage, worker


def test_audio_confirmado_produz_artefato_mesmo_sem_passe_pago(tmp_path: Path) -> None:
    """Caminho padrão do produto: providers desligados, artefato gravado do mesmo jeito.

    Sem ele, ligar a chave depois exigiria descobrir quais áudios já haviam passado por aqui.
    """
    document, storage, _ = _run(tmp_path)

    key = next(key for key in storage.objects if "/transcripts/" in key)
    assert key.startswith(f"tenants/{TENANT_ID}/surveys/{SURVEY_ID}/transcripts/")
    assert key.endswith(".json")
    assert storage.objects[key].content_type == "application/json"
    assert document["schema"] == TRANSCRIPT_SCHEMA
    assert document["media_id"] == MEDIA_ID
    assert document["media"]["mime_type"] == "audio/webm"
    # A chave do objeto do áudio não é repetida no artefato, e URL assinada nunca aparece.
    assert "object_key" not in document["media"]
    assert document["note_id"] == NOTE_ID
    assert document["provider_pass"] == "skipped_disabled"
    assert document["provider_failure_code"] is None
    assert document["transcript"] is None
    assert document["lineage"] is None
    assert document["status"] == "draft"


def test_sem_entitlement_o_passe_e_pulado_sem_chamar_provider(tmp_path: Path) -> None:
    """Fixture injetada NÃO dispensa o portão: a evidência aqui é a voz de um técnico."""
    primary = CountingAdapter()
    fallback = CountingAdapter(provider=ProviderName.OPENAI, model_id="whisper-1")

    document, _, _ = _run(tmp_path, suite=_suite(primary, fallback))

    assert document["provider_pass"] == "skipped_no_entitlement"
    assert document["transcript"] is None
    assert document["lineage"] is None
    # O oráculo da tarefa: nenhuma chamada, nem para o braço primário nem para o reserva.
    assert (len(primary.calls), len(fallback.calls)) == (0, 0)
    # E o vínculo com a nota, que é offline, aconteceu do mesmo jeito.
    assert document["note_id"] == NOTE_ID


def test_entitlement_revogado_tambem_pula_o_passe(tmp_path: Path) -> None:
    """Só `ACTIVE` autoriza; entitlement revogado é o mesmo que não ter."""
    primary = CountingAdapter()

    document, _, _ = _run(tmp_path, suite=_suite(primary), entitlement_status="REVOKED")

    assert document["provider_pass"] == "skipped_no_entitlement"
    assert primary.calls == []


def test_sem_braco_configurado_o_passe_e_pulado_com_entitlement_ativo(tmp_path: Path) -> None:
    """Conta do fornecedor é ato do usuário: sem braço, o passe é PULADO, nunca uma falha."""
    document, _, _ = _run(tmp_path, suite=_suite(with_primary=False), entitlement_status="ACTIVE")

    assert document["provider_pass"] == "skipped_disabled"
    assert document["provider_failure_code"] is None
    assert document["transcript"] is None


def test_com_entitlement_ativo_o_rascunho_e_o_lineage_entram_no_artefato(
    tmp_path: Path,
) -> None:
    """Uma chamada, transcrição como rascunho e lineage completo de quem respondeu."""
    primary = CountingAdapter()

    document, _, _ = _run(tmp_path, suite=_suite(primary), entitlement_status="ACTIVE")

    assert len(primary.calls) == 1
    request = primary.calls[0]
    assert request.task is PromptTask.AUDIO_TRANSCRIPTION
    # A evidência que viajou é o áudio, com o container declarado — nunca imagem nem texto.
    assert request.audio_bytes == AUDIO_BYTES
    assert request.audio_mime_type == "audio/webm"
    assert request.image_sha256 == hashlib.sha256(AUDIO_BYTES).hexdigest()
    assert document["provider_pass"] == "done"
    assert document["provider_notes"] == []
    assert document["transcript"] == {
        "text": TRANSCRIPT_TEXT,
        "language": "portuguese",
        "model": "whisper-large-v3-turbo",
        "duration_s": 4.5,
    }
    lineage = document["lineage"]
    assert lineage["provider"] == "groq"
    assert lineage["prompt"]["prompt_version"] == "audio-transcription@1.0.0"
    assert lineage["prompt"]["template_hash"] == (
        PROMPT_SPECS[PromptTask.AUDIO_TRANSCRIPTION].template_hash
    )
    assert lineage["input_digest"] == request.image_sha256
    assert lineage["usage"]["estimated_cost_usd"] == "0.01"
    # A resposta bruta só existe por referência ao raw-store protegido.
    assert lineage["raw_response_ref"].endswith("raw.json")
    assert "output" not in lineage


def test_a_transcricao_nunca_nasce_confirmada_nem_vira_medida(tmp_path: Path) -> None:
    """Rascunho é rascunho: sem status confirmado, sem valor, sem unidade, sem alvo."""
    document, _, _ = _run(tmp_path, suite=_suite(), entitlement_status="ACTIVE")

    assert document["status"] == "draft"
    transcript = document["transcript"]
    assert not {"value", "unit", "measurement", "confirmed", "status"} & set(transcript)


def test_audio_orfao_produz_artefato_sem_note_id_e_com_aviso(tmp_path: Path) -> None:
    """Áudio confirmado que nenhuma observação reivindica: transcreve, avisa, não inventa."""
    document, _, _ = _run(tmp_path, with_note=False)

    assert document["note_id"] is None
    assert document["notes"] == [NOTE_NOT_FOUND]
    assert document["schema"] == TRANSCRIPT_SCHEMA


def test_snapshot_ilegivel_vira_aviso_e_nao_impede_a_transcricao(tmp_path: Path) -> None:
    """O áudio existe e está confirmado; puni-lo pelo índice seria perder a evidência."""
    document, _, _ = _run(tmp_path, snapshot={"survey_id": SURVEY_ID})

    assert document["note_id"] is None
    assert document["notes"] == [SNAPSHOT_UNREADABLE]


def test_falha_transitoria_do_provider_fica_registrada(tmp_path: Path) -> None:
    """A via paga cai, o artefato diz que reprocessar adianta, e o handler não explode."""
    primary = CountingAdapter(failure=ProviderFailureCode.TIMEOUT)

    document, _, _ = _run(tmp_path, suite=_suite(primary), entitlement_status="ACTIVE")

    assert document["provider_pass"] == "failed_transient"
    assert document["provider_failure_code"] == "TIMEOUT"
    assert document["transcript"] is None
    assert document["note_id"] == NOTE_ID


def test_falha_permanente_e_registrada_como_permanente(tmp_path: Path) -> None:
    """Credencial recusada não melhora com reentrega, e o artefato não finge que melhora."""
    primary = CountingAdapter(failure=ProviderFailureCode.REFUSED)

    document, _, _ = _run(tmp_path, suite=_suite(primary), entitlement_status="ACTIVE")

    assert document["provider_pass"] == "failed_permanent"
    assert document["provider_failure_code"] == "REFUSED"


def test_teto_de_gasto_estourado_nunca_aciona_o_braco_reserva(tmp_path: Path) -> None:
    """O teto é da rodada, não do braço: tentar o reserva gastaria mais sem chance nenhuma."""
    primary = CountingAdapter(failure=ProviderFailureCode.BUDGET_EXCEEDED)
    fallback = CountingAdapter(provider=ProviderName.OPENAI, model_id="whisper-1")

    document, _, _ = _run(tmp_path, suite=_suite(primary, fallback), entitlement_status="ACTIVE")

    assert document["provider_pass"] == "failed_permanent"
    assert document["provider_failure_code"] == "BUDGET_EXCEEDED"
    assert fallback.calls == []


def test_braco_reserva_assume_e_a_troca_fica_registrada(tmp_path: Path) -> None:
    """Degradação nunca é silenciosa: quem respondeu está no lineage e a troca, na nota."""
    primary = CountingAdapter(failure=ProviderFailureCode.UNAVAILABLE)
    fallback = CountingAdapter(
        provider=ProviderName.OPENAI, model_id="whisper-1", text="Muro do fundo, 12,40 m."
    )

    document, _, _ = _run(tmp_path, suite=_suite(primary, fallback), entitlement_status="ACTIVE")

    assert document["provider_pass"] == "done"
    assert document["provider_notes"] == ["PROVIDER_FALLBACK_AUDIO_TRANSCRIPTION_OPENAI"]
    assert document["lineage"]["provider"] == "openai"
    assert document["transcript"]["model"] == "whisper-1"
    assert (len(primary.calls), len(fallback.calls)) == (1, 1)


def test_sem_braco_reserva_a_falha_do_primario_nao_inventa_nota(tmp_path: Path) -> None:
    """`transcription_fallback=None` é o default: não houve troca de braço a registrar."""
    primary = CountingAdapter(failure=ProviderFailureCode.UNAVAILABLE)

    document, _, _ = _run(tmp_path, suite=_suite(primary), entitlement_status="ACTIVE")

    assert document["provider_pass"] == "failed_transient"
    assert document["provider_notes"] == []


def test_nada_do_levantamento_e_mutado_pela_transcricao(tmp_path: Path) -> None:
    """A transcrição é observação lateral: nenhuma linha do levantamento muda de estado."""
    database_url, storage, sha256 = _seed(tmp_path, entitlement_status="ACTIVE")
    snapshot_antes = _packet(sha256=sha256)
    worker = _worker(database_url, storage, suite=_suite())

    assert worker.dispatch(_message()) == 1

    database = Database(database_url)
    with database.sessions() as session:
        survey = session.get(SurveyRecord, {"tenant_id": TENANT_ID, "id": SURVEY_ID})
        media = session.get(SurveyMediaRecord, MEDIA_ID)
        assert survey is not None and media is not None
        assert (survey.status, survey.version) == ("OPEN", 3)
        assert survey.snapshot_json == snapshot_antes
        assert (media.status, media.sha256) == ("CONFIRMED", sha256)
        audio_key = media.object_key
    # Só o artefato de transcrição foi escrito; o áudio original continua onde estava.
    assert sorted(storage.objects) == sorted([audio_key, _transcript_key(sha256)])


def test_reprocessar_a_mesma_mensagem_reescreve_a_mesma_chave(tmp_path: Path) -> None:
    """Reentrega é normal na fila: a chave vem do digest do áudio e nada acumula."""
    database_url, storage, sha256 = _seed(tmp_path)
    worker = _worker(database_url, storage)

    assert worker.dispatch(_message()) == 1
    primeiro = storage.body(_transcript_key(sha256))
    assert worker.dispatch(_message()) == 1

    assert len([key for key in storage.objects if "/transcripts/" in key]) == 1
    assert json.loads(storage.body(_transcript_key(sha256))) == json.loads(primeiro)


def test_midia_de_outro_tenant_nao_e_encontrada(tmp_path: Path) -> None:
    """Escopo por tenant em toda consulta: o mesmo id noutro tenant não existe aqui."""
    database_url, storage, _ = _seed(tmp_path, tenant_id=OTHER_TENANT_ID)
    worker = _worker(database_url, storage)

    with pytest.raises(SurveyTranscriptionError) as error:
        worker.dispatch(_message())

    assert error.value.code == "SURVEY_AUDIO_MEDIA_NOT_FOUND"
    assert [key for key in storage.objects if "/transcripts/" in key] == []


def test_midia_ainda_nao_confirmada_nao_e_transcrita(tmp_path: Path) -> None:
    """Defesa em profundidade: só o `confirm` publica o comando, e o worker confere."""
    database_url, storage, _ = _seed(tmp_path, media_status="PRESIGNED")
    worker = _worker(database_url, storage)

    with pytest.raises(SurveyTranscriptionError) as error:
        worker.dispatch(_message())

    assert error.value.code == "SURVEY_AUDIO_MEDIA_NOT_CONFIRMED"


def test_container_nao_suportado_para_antes_de_gastar_a_chamada(tmp_path: Path) -> None:
    """Foto chega por outro comando (T14); container estranho é recusa nomeada, não 400 pago."""
    database_url, storage, _ = _seed(tmp_path, mime_type="image/jpeg")
    worker = _worker(database_url, storage)

    with pytest.raises(SurveyTranscriptionError) as error:
        worker.dispatch(_message())

    assert error.value.code == "SURVEY_AUDIO_MEDIA_UNSUPPORTED_MIME"


def test_bytes_ausentes_no_storage_param_com_erro_estruturado(tmp_path: Path) -> None:
    """Metadado confirmado sem objeto: recusa nomeada, e a retomada é reprocessar depois."""
    database_url, storage, _ = _seed(tmp_path, store_bytes=False)
    worker = _worker(database_url, storage)

    with pytest.raises(SurveyTranscriptionError) as error:
        worker.dispatch(_message())

    assert error.value.code == "SURVEY_AUDIO_BYTES_MISSING"
    assert [key for key in storage.objects if "/transcripts/" in key] == []


def test_mensagem_sem_media_id_nao_e_roteavel(tmp_path: Path) -> None:
    """Envelope quebrado é defeito do publicador; reentregar daria o mesmo resultado."""
    database_url, storage, _ = _seed(tmp_path)
    worker = _worker(database_url, storage)

    with pytest.raises(UnroutableMessageError):
        worker.dispatch(
            {"command": "transcribe_survey_audio", "survey_id": SURVEY_ID, "tenant_id": TENANT_ID}
        )


def test_consumo_pela_fila_usa_o_corpo_publicado_pela_api(tmp_path: Path) -> None:
    """O comando chega pelo transporte, sem `job_id`, e é reconhecido pelo despacho."""
    database_url, storage, sha256 = _seed(tmp_path)
    worker = _worker(database_url, storage)
    queue = cast(FakeQueue, worker.client)
    queue.send_message(MessageBody=json.dumps(_message()))

    assert worker.run_once() == 1

    assert queue.commands() == ["transcribe_survey_audio"]
    assert _transcript_key(sha256) in storage.objects


def test_log_carrega_contagens_e_nenhum_texto_transcrito(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Log de operação: id opaco, desfecho, contagens e duração — nunca o que foi dito."""
    database_url, storage, sha256 = _seed(tmp_path, entitlement_status="ACTIVE")
    worker = _worker(database_url, storage, suite=_suite())

    with caplog.at_level("INFO", logger="croquito_worker.local_queue"):
        worker.dispatch(_message())

    registro = next(
        record
        for record in caplog.records
        if record.message.startswith("survey_transcription_completed")
    )
    assert registro.stage == "SURVEY_TRANSCRIPTION"  # type: ignore[attr-defined]
    assert registro.provider_pass == "done"  # type: ignore[attr-defined]
    assert registro.characters == len(TRANSCRIPT_TEXT)  # type: ignore[attr-defined]
    assert registro.note_linked is True  # type: ignore[attr-defined]
    assert isinstance(registro.duration_ms, int)  # type: ignore[attr-defined]
    linha = registro.getMessage()
    for proibido in ["muro do fundo", "12,40", "0,18", TRANSCRIPT_TEXT, sha256]:
        assert proibido not in linha
