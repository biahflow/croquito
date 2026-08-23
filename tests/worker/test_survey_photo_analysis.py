"""Handler `analyze_survey_photo` (F-032, T14): foto de campo → artefato de análise.

O que estes testes protegem:

- **o passe offline é incondicional**: qualidade e metadados saem sempre, mesmo quando a via
  paga está desligada, sem entitlement ou quebrada;
- **a via paga não sai de graça nem por engano**: sem caminho habilitado o passe é
  `skipped_disabled`; com fixture injetada mas sem entitlement contratual ativo é
  `skipped_no_entitlement` — e, nos dois casos, o contador do adapter fica em ZERO. Nenhum
  teste desta suíte chama provider real;
- **falha de provider não apaga a análise**: transitória e permanente ficam registradas no
  artefato, com o passe offline intacto, e a troca para o braço reserva nunca é silenciosa;
- **nada é confirmado e nada é mutado**: leitura de foto vira rascunho no artefato, e
  `survey_records`/`survey_media_records` saem da execução exatamente como entraram;
- **erros estruturados**: mídia de outro tenant, mídia não confirmada, mídia que não é
  imagem, bytes ausentes e imagem indecodificável param com código estável;
- **idempotência**: reprocessar reescreve a MESMA chave, derivada do digest da foto.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import cv2
import numpy as np
import pytest

from croquito_api.database import (
    Database,
    SurveyMediaRecord,
    SurveyRecord,
    TenantAiProcessingEntitlementRecord,
)
from croquito_worker.local_queue import (
    LocalQueueWorker,
    LocalWorkerSettings,
    UnroutableMessageError,
)
from croquito_worker.providers import (
    PROMPT_SPECS,
    FieldPhotoReadingOutput,
    FieldPhotoReadingsOutput,
    PromptTask,
    ProviderExecution,
    ProviderExecutionError,
    ProviderFailureCode,
    ProviderName,
    ProviderRequest,
    ProviderSuite,
    ProviderUsage,
)
from croquito_worker.survey_photo_analysis import (
    ANALYSIS_SCHEMA,
    SurveyPhotoAnalysisError,
)
from tests.fakes import FakeObjectStore, FakeQueue

TENANT_ID = "tenant-campo"
OTHER_TENANT_ID = "tenant-vizinho"
SURVEY_ID = "00000000-0000-7000-8000-0000000009f0"
MEDIA_ID = "00000000-0000-7000-8000-00000000ab01"
AUDIO_MEDIA_ID = "00000000-0000-7000-8000-00000000ab02"


def _encode(image: np.ndarray) -> bytes:
    """PNG sintético; nenhuma fixture binária de cliente entra no repositório."""
    stored, buffer = cv2.imencode(".png", image)
    assert stored
    payload: bytes = buffer.tobytes()
    return payload


def _checkerboard(*, width: int = 1024, height: int = 768, square: int = 64) -> np.ndarray:
    """Tabuleiro de bordas duras: muita variância de Laplaciano, exposição no meio."""
    rows = np.arange(height)[:, None] // square
    columns = np.arange(width)[None, :] // square
    mono = np.where((rows + columns) % 2 == 0, 215, 40).astype(np.uint8)
    return np.dstack([mono] * 3)


def sharp_photo() -> bytes:
    return _encode(_checkerboard())


def blurred_photo() -> bytes:
    return _encode(cv2.GaussianBlur(_checkerboard(), (51, 51), 0))


def overexposed_photo() -> bytes:
    image = np.full((768, 1024, 3), 253, dtype=np.uint8)
    image[:100, :100] = 10
    return _encode(image)


def underexposed_photo() -> bytes:
    image = np.full((768, 1024, 3), 2, dtype=np.uint8)
    image[:200, :200] = 200
    return _encode(image)


def _analysis_key(sha256: str) -> str:
    return f"tenants/{TENANT_ID}/surveys/{SURVEY_ID}/analysis/{sha256}.json"


def _readings_output() -> FieldPhotoReadingsOutput:
    """Saída de fixture: uma placa transcrita e uma abstenção declarada."""
    return FieldPhotoReadingsOutput(
        readings=[
            FieldPhotoReadingOutput(
                raw_text="PRAÇA MUNICIPAL — 12,00 m",
                kind_hint="sign",
                value_hint=Decimal("12.00"),
                unit_hint="m",
                target_hint="muro do fundo",
                confidence="medium",
            )
        ],
        notes=["Segunda placa cortada pela borda da foto; não transcrita."],
    )


@dataclass
class CountingAdapter:
    """Adapter de teste que CONTA chamadas — o oráculo de "nada pago aconteceu"."""

    provider: ProviderName = ProviderName.ANTHROPIC
    model_id: str = "fixture-claude-v1"
    output: FieldPhotoReadingsOutput = field(default_factory=_readings_output)
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
            latency_ms=7,
            usage=ProviderUsage(
                input_tokens=1200, output_tokens=90, estimated_cost_usd=Decimal("0.01")
            ),
            raw_response_ref=f"tenants/{TENANT_ID}/surveys/{SURVEY_ID}/providers/raw.json",
            output=self.output,
        )


def _suite(
    primary: CountingAdapter | None = None, secondary: CountingAdapter | None = None
) -> ProviderSuite:
    return ProviderSuite(anthropic=primary or CountingAdapter(), openai=secondary)


def _seed(
    tmp_path: Path,
    *,
    photo: bytes | None = None,
    tenant_id: str = TENANT_ID,
    media_status: str = "CONFIRMED",
    mime_type: str = "image/jpeg",
    entitlement_status: str | None = None,
    store_bytes: bool = True,
) -> tuple[str, FakeObjectStore, str]:
    """Banco + storage com uma foto confirmada; devolve `(url, storage, sha256)`."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    payload = sharp_photo() if photo is None else photo
    sha256 = hashlib.sha256(payload).hexdigest()
    object_key = f"tenants/{tenant_id}/surveys/{SURVEY_ID}/media/{sha256}"
    database_url = f"sqlite+pysqlite:///{tmp_path / 'survey-photo.db'}"
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
                snapshot_json={"survey_id": SURVEY_ID},
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
                byte_size=len(payload),
                object_key=object_key,
                status=media_status,
            )
        )
        session.add(
            SurveyMediaRecord(
                id=AUDIO_MEDIA_ID,
                tenant_id=tenant_id,
                survey_id=SURVEY_ID,
                sha256=hashlib.sha256(b"audio sintetico").hexdigest(),
                mime_type="audio/webm",
                byte_size=15,
                object_key=f"tenants/{tenant_id}/surveys/{SURVEY_ID}/media/audio",
                status="CONFIRMED",
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
        storage.put_direct(object_key=object_key, body=payload, content_type=mime_type)
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
    """O corpo EXATO publicado por `enqueue_survey_photo_analysis` (`services/api`)."""
    return {
        "command": "analyze_survey_photo",
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
    document = cast(dict[str, Any], json.loads(storage.body(_analysis_key(sha256))))
    return document, storage, worker


def test_foto_confirmada_produz_artefato_de_analise_sem_passe_pago(tmp_path: Path) -> None:
    """Caminho padrão do produto: providers desligados, análise offline mesmo assim."""
    document, storage, _ = _run(tmp_path)

    key = next(key for key in storage.objects if "/analysis/" in key)
    assert key.startswith(f"tenants/{TENANT_ID}/surveys/{SURVEY_ID}/analysis/")
    assert key.endswith(".json")
    assert storage.objects[key].content_type == "application/json"
    assert document["schema"] == ANALYSIS_SCHEMA
    assert document["media_id"] == MEDIA_ID
    assert document["media"]["mime_type"] == "image/jpeg"
    # A chave do objeto da foto não é repetida no artefato, e URL assinada nunca aparece.
    assert "object_key" not in document["media"]
    assert document["quality"]["width_px"] == 1024
    assert document["quality"]["height_px"] == 768
    assert document["quality"]["findings"] == []
    assert document["quality"]["sharpness_laplacian_variance"] > 100
    assert document["provider_pass"] == "skipped_disabled"
    assert document["provider_failure_code"] is None
    assert document["readings"] == []
    assert document["notes"] == []
    assert document["lineage"] is None


def test_qualidade_separa_nitida_de_borrada_de_estourada_de_escura(tmp_path: Path) -> None:
    """Os quatro achados de triagem, cada um sobre uma foto sintética própria."""
    nitida, _, _ = _run(tmp_path / "a")
    borrada, _, _ = _run(tmp_path / "b", photo=blurred_photo())
    estourada, _, _ = _run(tmp_path / "c", photo=overexposed_photo())
    escura, _, _ = _run(tmp_path / "d", photo=underexposed_photo())
    pequena, _, _ = _run(tmp_path / "e", photo=_encode(_checkerboard(width=320, height=240)))

    assert nitida["quality"]["findings"] == []
    assert borrada["quality"]["findings"] == ["PHOTO_LOW_SHARPNESS"]
    assert borrada["quality"]["sharpness_laplacian_variance"] < 100
    assert "PHOTO_OVEREXPOSED" in estourada["quality"]["findings"]
    assert estourada["quality"]["overexposed_fraction"] > 0.15
    assert "PHOTO_UNDEREXPOSED" in escura["quality"]["findings"]
    assert escura["quality"]["mean_luma"] < 40
    assert pequena["quality"]["findings"] == ["PHOTO_LOW_RESOLUTION"]
    # Os limiares viajam junto: recalibrar depois não deixa artefato órfão de critério.
    assert nitida["quality"]["thresholds"]["sharpness_min_variance"] == 100.0


def test_sem_entitlement_o_passe_pago_e_pulado_sem_chamar_provider(tmp_path: Path) -> None:
    """Fixture injetada NÃO dispensa o portão: a evidência aqui é foto de cliente."""
    primary = CountingAdapter()
    secondary = CountingAdapter(provider=ProviderName.OPENAI, model_id="fixture-openai-v1")

    document, _, _ = _run(tmp_path, suite=_suite(primary, secondary))

    assert document["provider_pass"] == "skipped_no_entitlement"
    assert document["readings"] == []
    assert document["lineage"] is None
    # O oráculo da tarefa: nenhuma chamada, nem para o braço primário nem para o reserva.
    assert (len(primary.calls), len(secondary.calls)) == (0, 0)
    # E o passe offline aconteceu do mesmo jeito.
    assert document["quality"]["width_px"] == 1024


def test_entitlement_revogado_tambem_pula_o_passe_pago(tmp_path: Path) -> None:
    """Só `ACTIVE` autoriza; entitlement revogado é o mesmo que não ter."""
    primary = CountingAdapter()

    document, _, _ = _run(tmp_path, suite=_suite(primary), entitlement_status="REVOKED")

    assert document["provider_pass"] == "skipped_no_entitlement"
    assert primary.calls == []


def test_com_entitlement_ativo_as_leituras_e_o_lineage_entram_no_artefato(
    tmp_path: Path,
) -> None:
    """Uma chamada, leituras como rascunho e lineage completo do que respondeu."""
    primary = CountingAdapter()

    document, _, _ = _run(tmp_path, suite=_suite(primary), entitlement_status="ACTIVE")

    assert len(primary.calls) == 1
    request = primary.calls[0]
    assert request.task is PromptTask.FIELD_PHOTO_READING
    # Tarefa de visão: a imagem viaja com as dimensões medidas pelo passe offline.
    assert (request.image_width_px, request.image_height_px) == (1024, 768)
    assert document["provider_pass"] == "done"
    assert document["provider_notes"] == []
    assert len(document["readings"]) == 1
    assert document["readings"][0] | {"id": "ignored"} == {
        "id": "ignored",
        "raw_text": "PRAÇA MUNICIPAL — 12,00 m",
        "kind_hint": "sign",
        "value_hint": "12.00",
        "unit_hint": "m",
        "target_hint": "muro do fundo",
        "confidence": "medium",
    }
    assert document["readings"][0]["id"].startswith("fpr_")
    assert document["notes"] == ["Segunda placa cortada pela borda da foto; não transcrita."]
    lineage = document["lineage"]
    assert lineage["provider"] == "anthropic"
    assert lineage["model_id"] == "fixture-claude-v1"
    assert lineage["prompt"]["prompt_version"] == "field-photo-reading@1.0.0"
    assert lineage["prompt"]["template_hash"] == (
        PROMPT_SPECS[PromptTask.FIELD_PHOTO_READING].template_hash
    )
    assert lineage["input_digest"] == request.image_sha256
    assert lineage["usage"]["estimated_cost_usd"] == "0.01"
    # A resposta bruta só existe por referência ao raw-store protegido.
    assert lineage["raw_response_ref"].endswith("raw.json")
    assert "output" not in lineage


def test_leitura_de_foto_nao_carrega_coordenada_nem_confirmacao(tmp_path: Path) -> None:
    """Rascunho é rascunho: sem bbox, sem status confirmado, sem alvo do levantamento."""
    document, _, _ = _run(tmp_path, suite=_suite(CountingAdapter()), entitlement_status="ACTIVE")

    reading = document["readings"][0]
    assert not {"bbox", "polygon", "x", "y", "confirmed", "status"} & set(reading)
    # `target_hint` é o que a PLACA diz, texto livre — nunca o id de um ponto ou elemento.
    assert reading["target_hint"] == "muro do fundo"


def test_falha_transitoria_do_provider_preserva_a_analise_offline(tmp_path: Path) -> None:
    """A via paga cai, a foto continua analisada, e o artefato diz que reprocessar adianta."""
    primary = CountingAdapter(failure=ProviderFailureCode.TIMEOUT)

    document, _, _ = _run(tmp_path, suite=_suite(primary), entitlement_status="ACTIVE")

    assert document["provider_pass"] == "failed_transient"
    assert document["provider_failure_code"] == "TIMEOUT"
    assert document["readings"] == []
    assert document["lineage"] is None
    assert document["quality"]["sharpness_laplacian_variance"] > 100


def test_falha_permanente_e_registrada_como_permanente(tmp_path: Path) -> None:
    """Schema recusado não melhora com reentrega, e o artefato não finge que melhora."""
    primary = CountingAdapter(failure=ProviderFailureCode.INVALID_SCHEMA)

    document, _, _ = _run(tmp_path, suite=_suite(primary), entitlement_status="ACTIVE")

    assert document["provider_pass"] == "failed_permanent"
    assert document["provider_failure_code"] == "INVALID_SCHEMA"
    assert len(primary.calls) == 1


def test_teto_de_gasto_estourado_nunca_aciona_o_braco_reserva(tmp_path: Path) -> None:
    """O teto é da rodada, não do braço: tentar o reserva gastaria mais sem chance nenhuma."""
    primary = CountingAdapter(failure=ProviderFailureCode.BUDGET_EXCEEDED)
    secondary = CountingAdapter(provider=ProviderName.OPENAI, model_id="fixture-openai-v1")

    document, _, _ = _run(tmp_path, suite=_suite(primary, secondary), entitlement_status="ACTIVE")

    assert document["provider_pass"] == "failed_permanent"
    assert document["provider_failure_code"] == "BUDGET_EXCEEDED"
    assert secondary.calls == []


def test_braco_reserva_assume_e_a_troca_fica_registrada(tmp_path: Path) -> None:
    """Degradação nunca é silenciosa: quem respondeu está no lineage e a troca, na nota."""
    primary = CountingAdapter(failure=ProviderFailureCode.REFUSED)
    secondary = CountingAdapter(provider=ProviderName.OPENAI, model_id="fixture-openai-v1")

    document, _, _ = _run(tmp_path, suite=_suite(primary, secondary), entitlement_status="ACTIVE")

    assert document["provider_pass"] == "done"
    assert document["provider_notes"] == ["PROVIDER_FALLBACK_FIELD_PHOTO_READING_OPENAI"]
    assert document["lineage"]["provider"] == "openai"
    assert (len(primary.calls), len(secondary.calls)) == (1, 1)


def test_sem_braco_reserva_a_falha_do_primario_nao_inventa_nota(tmp_path: Path) -> None:
    """`openai=None` é braço desligado por configuração: não houve troca a registrar."""
    primary = CountingAdapter(failure=ProviderFailureCode.REFUSED)

    document, _, _ = _run(tmp_path, suite=_suite(primary), entitlement_status="ACTIVE")

    assert document["provider_pass"] == "failed_permanent"
    assert document["provider_notes"] == []


def test_nada_do_levantamento_e_mutado_pela_analise(tmp_path: Path) -> None:
    """A análise é observação lateral: nenhuma linha do levantamento muda de estado."""
    database_url, storage, sha256 = _seed(tmp_path, entitlement_status="ACTIVE")
    worker = _worker(database_url, storage, suite=_suite())

    assert worker.dispatch(_message()) == 1

    database = Database(database_url)
    with database.sessions() as session:
        survey = session.get(SurveyRecord, {"tenant_id": TENANT_ID, "id": SURVEY_ID})
        media = session.get(SurveyMediaRecord, MEDIA_ID)
        assert survey is not None and media is not None
        assert (survey.status, survey.version) == ("OPEN", 3)
        assert survey.snapshot_json == {"survey_id": SURVEY_ID}
        assert (media.status, media.sha256) == ("CONFIRMED", sha256)
        photo_key = media.object_key
    # Só o artefato de análise foi escrito; a foto original continua onde estava.
    assert sorted(storage.objects) == sorted([photo_key, _analysis_key(sha256)])


def test_reprocessar_a_mesma_mensagem_reescreve_a_mesma_chave(tmp_path: Path) -> None:
    """Reentrega é normal na fila: a chave vem do digest da foto e nada acumula."""
    database_url, storage, sha256 = _seed(tmp_path)
    worker = _worker(database_url, storage)

    assert worker.dispatch(_message()) == 1
    primeiro = storage.body(_analysis_key(sha256))
    assert worker.dispatch(_message()) == 1

    assert len([key for key in storage.objects if "/analysis/" in key]) == 1
    assert json.loads(storage.body(_analysis_key(sha256))) == json.loads(primeiro)


def test_midia_de_outro_tenant_nao_e_encontrada(tmp_path: Path) -> None:
    """Escopo por tenant em toda consulta: o mesmo id noutro tenant não existe aqui."""
    database_url, storage, _ = _seed(tmp_path, tenant_id=OTHER_TENANT_ID)
    worker = _worker(database_url, storage)

    with pytest.raises(SurveyPhotoAnalysisError) as error:
        worker.dispatch(_message())

    assert error.value.code == "SURVEY_PHOTO_MEDIA_NOT_FOUND"
    assert [key for key in storage.objects if "/analysis/" in key] == []


def test_midia_ainda_nao_confirmada_nao_e_analisada(tmp_path: Path) -> None:
    """Defesa em profundidade: só o `confirm` publica o comando, e o worker confere."""
    database_url, storage, _ = _seed(tmp_path, media_status="PRESIGNED")
    worker = _worker(database_url, storage)

    with pytest.raises(SurveyPhotoAnalysisError) as error:
        worker.dispatch(_message())

    assert error.value.code == "SURVEY_PHOTO_MEDIA_NOT_CONFIRMED"


def test_midia_que_nao_e_imagem_para_com_erro_estruturado(tmp_path: Path) -> None:
    """Áudio chega por outro comando (T13); aqui é recusa nomeada, não decodificação torta."""
    database_url, storage, _ = _seed(tmp_path, mime_type="audio/webm")
    worker = _worker(database_url, storage)

    with pytest.raises(SurveyPhotoAnalysisError) as error:
        worker.dispatch(_message())

    assert error.value.code == "SURVEY_PHOTO_MEDIA_NOT_IMAGE"


def test_bytes_ausentes_no_storage_param_com_erro_estruturado(tmp_path: Path) -> None:
    """Metadado confirmado sem objeto: recusa nomeada, e a retomada é reprocessar depois."""
    database_url, storage, _ = _seed(tmp_path, store_bytes=False)
    worker = _worker(database_url, storage)

    with pytest.raises(SurveyPhotoAnalysisError) as error:
        worker.dispatch(_message())

    assert error.value.code == "SURVEY_PHOTO_BYTES_MISSING"


def test_imagem_indecodificavel_para_com_erro_estruturado(tmp_path: Path) -> None:
    """Bytes que não são imagem não viram análise vazia disfarçada de análise feita."""
    database_url, storage, _ = _seed(tmp_path, photo=b"nao sou uma imagem")
    worker = _worker(database_url, storage)

    with pytest.raises(SurveyPhotoAnalysisError) as error:
        worker.dispatch(_message())

    assert error.value.code == "SURVEY_PHOTO_UNDECODABLE"
    assert [key for key in storage.objects if "/analysis/" in key] == []


def test_mensagem_sem_media_id_nao_e_roteavel(tmp_path: Path) -> None:
    """Envelope quebrado é defeito do publicador; reentregar daria o mesmo resultado."""
    database_url, storage, _ = _seed(tmp_path)
    worker = _worker(database_url, storage)

    with pytest.raises(UnroutableMessageError):
        worker.dispatch(
            {"command": "analyze_survey_photo", "survey_id": SURVEY_ID, "tenant_id": TENANT_ID}
        )


def test_consumo_pela_fila_usa_o_corpo_publicado_pela_api(tmp_path: Path) -> None:
    """O comando chega pelo transporte, sem `job_id`, e é reconhecido pelo despacho."""
    database_url, storage, sha256 = _seed(tmp_path)
    worker = _worker(database_url, storage)
    queue = cast(FakeQueue, worker.client)
    queue.send_message(MessageBody=json.dumps(_message()))

    assert worker.run_once() == 1

    assert queue.commands() == ["analyze_survey_photo"]
    assert _analysis_key(sha256) in storage.objects


def test_log_carrega_contagens_e_nenhum_conteudo_da_foto(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Log de operação: id opaco, desfecho, contagens e duração — nada do que a foto mostra."""
    database_url, storage, sha256 = _seed(tmp_path, entitlement_status="ACTIVE")
    worker = _worker(database_url, storage, suite=_suite())

    with caplog.at_level("INFO", logger="croquito_worker.local_queue"):
        worker.dispatch(_message())

    registro = next(
        record
        for record in caplog.records
        if record.message.startswith("survey_photo_analysis_completed")
    )
    assert registro.stage == "SURVEY_PHOTO_ANALYSIS"  # type: ignore[attr-defined]
    assert registro.provider_pass == "done"  # type: ignore[attr-defined]
    assert registro.readings == 1  # type: ignore[attr-defined]
    assert registro.findings == 0  # type: ignore[attr-defined]
    assert isinstance(registro.duration_ms, int)  # type: ignore[attr-defined]
    linha = registro.getMessage()
    for proibido in ["PRAÇA MUNICIPAL", "12,00", "muro do fundo", sha256]:
        assert proibido not in linha
