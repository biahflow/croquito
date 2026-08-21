"""Comando de fila `extract_valuation_plate` (F-003 T8): a extração paga fora do request.

O ponto caro deste arquivo é o claim: a extração é uma chamada PAGA, e uma fila entrega a
mesma mensagem mais de uma vez por construção. Por isso o oráculo central não é o pacote
publicado — é a CONTAGEM de chamadas ao adapter depois de duas entregas idênticas.

Nenhuma chamada externa acontece aqui: o braço pago é injetado como fixture pelo mesmo seam
que a `ProviderSuite` da ingestão usa, e o teste sem injeção prova o contrário — sem teto de
gasto declarado no ambiente, a extração falha declarada em vez de tentar.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pymupdf
import pytest
from sqlalchemy import select

from croquito_api.database import (
    Database,
    UploadRecord,
    ValuationRoundRecord,
    ValuationRoundRevisionRecord,
)
from croquito_worker.local_queue import (
    LocalQueueWorker,
    LocalWorkerSettings,
    UnroutableMessageError,
)
from croquito_worker.providers import (
    FixtureProviderAdapter,
    LegendExtractionOutput,
    LegendRowOutput,
    NormalizedBox,
    PromptTask,
    ProviderExecution,
    ProviderExecutionError,
    ProviderFailureCode,
    ProviderName,
    ProviderRequest,
)
from croquito_worker.valuation import round_extraction
from croquito_worker.valuation.legend_extraction import LEGEND_EXTRACTION_SAFETY_NOTES
from croquito_worker.valuation.round_extraction import (
    AI_BUDGET_ENV,
    EXTRACTION_RESERVE_ARM_ENV,
    PLATE_IMAGE_DIGEST,
    PLATE_IMAGE_REF,
    TAKEOFF_OVERLAY_DIGEST,
    TAKEOFF_OVERLAY_PACKET_DIGEST,
    TAKEOFF_OVERLAY_REF,
    document_digest,
)
from tests.fakes import FakeObjectStore, FakeQueue

TENANT_ID = "tenant-medicao"
ROUND_ID = "00000000-0000-7000-8000-000000000901"
EXTRACTION_ID = "00000000-0000-7000-8000-000000000902"
PLATE_KEY = f"tenants/{TENANT_ID}/uploads/upload-prancha/prancha.pdf"
_FIXTURE_MODEL_ID = "fixture-legend-v1"
_ANTHROPIC_KEY_ENV = "CROQUITO_ANTHROPIC_API_KEY"
_RESERVE_MODEL_ID = "fixture-legend-reserva-v1"
_RESERVE_ARM_SPEC = "luna=openai:gpt-5.6-luna"
_RESERVE_NOTE = "PROVIDER_FALLBACK_LEGEND_EXTRACTION_OPENAI"


def _plate_pdf() -> bytes:
    """Prancha sintética escrita no próprio teste; nenhum documento de cliente no Git."""
    document = pymupdf.open()
    try:
        page = document.new_page(width=595, height=842)
        page.insert_text((60, 120), "PRANCHA SINTETICA DE TESTE", fontsize=14)
        page.insert_text((60, 160), "PISO INTERTRAVADO SINTETICO 61,20 M2", fontsize=12)
        page.insert_text((60, 190), "PISO EMBORRACHADO SINTETICO --- M2", fontsize=12)
        return bytes(document.tobytes())
    finally:
        document.close()


def _legend_output() -> LegendExtractionOutput:
    """Transcrição fabricada das duas linhas da prancha: uma legível, uma ilegível."""
    return LegendExtractionOutput(
        rows=[
            LegendRowOutput(
                raw_text="PISO INTERTRAVADO SINTETICO 61,20 M2",
                label="PISO INTERTRAVADO SINTETICO",
                quantity_text="61,20",
                unit_text="M2",
                bbox=NormalizedBox(left=0.09, top=0.175, right=0.62, bottom=0.20),
                legibility="clear",
            ),
            LegendRowOutput(
                raw_text="PISO EMBORRACHADO SINTETICO --- M2",
                label="PISO EMBORRACHADO SINTETICO",
                quantity_text=None,
                unit_text="M2",
                bbox=NormalizedBox(left=0.09, top=0.21, right=0.62, bottom=0.235),
                legibility="illegible",
            ),
        ],
        page_notes=["fixture de teste; nenhuma prancha de cliente foi lida"],
    )


@dataclass
class _CountingAdapter:
    """Braço fixture que CONTA execuções: é ele que prova que a reentrega não repaga."""

    inner: FixtureProviderAdapter
    calls: list[str] = field(default_factory=list)

    def execute(self, request: ProviderRequest) -> ProviderExecution:
        self.calls.append(request.task.value)
        return self.inner.execute(request)


@dataclass(frozen=True, slots=True)
class _FailingAdapter:
    """Braço que falha como provider fora do ar; depois dele nada pode ser publicado."""

    code: ProviderFailureCode = ProviderFailureCode.TIMEOUT

    def execute(self, request: ProviderRequest) -> ProviderExecution:
        raise ProviderExecutionError(self.code)


def _counting_adapter() -> _CountingAdapter:
    return _CountingAdapter(
        inner=FixtureProviderAdapter(
            provider=ProviderName.ANTHROPIC,
            model_id=_FIXTURE_MODEL_ID,
            outputs={PromptTask.LEGEND_EXTRACTION: _legend_output()},
        )
    )


def _reserve_adapter() -> _CountingAdapter:
    """Braço de reserva fixture, num provider DIFERENTE: é o que torna a nota verificável."""
    return _CountingAdapter(
        inner=FixtureProviderAdapter(
            provider=ProviderName.OPENAI,
            model_id=_RESERVE_MODEL_ID,
            outputs={PromptTask.LEGEND_EXTRACTION: _legend_output()},
        )
    )


def _install_reserve(monkeypatch: pytest.MonkeyPatch, adapter: Any) -> None:
    """Declara a reserva no ambiente e troca só a FÁBRICA: nada sai da máquina no teste.

    O caminho exercido é o real — a env é lida, a forma do braço é validada e o adapter é
    montado por `round_extraction.build_extraction_adapter` —, e é essa fábrica que a
    suíte substitui, exatamente como o braço primário é injetado no worker.
    """
    monkeypatch.setenv(EXTRACTION_RESERVE_ARM_ENV, _RESERVE_ARM_SPEC)

    def _factory(arm_spec: str) -> tuple[str, str, Any]:
        assert arm_spec == _RESERVE_ARM_SPEC
        return "luna", _RESERVE_MODEL_ID, adapter

    monkeypatch.setattr(round_extraction, "build_extraction_adapter", _factory)


def _seed(
    tmp_path: Path, *, plate: bytes, extraction_status: str = "queued"
) -> tuple[Database, str]:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'medicao.db'}"
    database = Database(database_url)
    database.create_schema()
    now = datetime.now(UTC)
    with database.sessions.begin() as session:
        session.add(
            UploadRecord(
                id="upload-catalogo",
                tenant_id=TENANT_ID,
                object_key=f"tenants/{TENANT_ID}/uploads/upload-catalogo/catalogo.json",
                filename="catalogo.json",
                content_type="application/json",
                size_bytes=64,
                sha256="c" * 64,
            )
        )
        session.add(
            UploadRecord(
                id="upload-prancha",
                tenant_id=TENANT_ID,
                object_key=PLATE_KEY,
                filename="prancha.pdf",
                content_type="application/pdf",
                size_bytes=len(plate),
                sha256=hashlib.sha256(plate).hexdigest(),
            )
        )
        session.flush()
        session.add(
            ValuationRoundRecord(
                id=ROUND_ID,
                tenant_id=TENANT_ID,
                worksite_key="praca-sintetica-norte",
                worksite_name="PRACA SINTETICA NORTE",
                reference_label="MEDICAO 01/2026",
                period_number=1,
                status="OPEN",
                version=1,
                catalog_upload_id="upload-catalogo",
                catalog_object_key=f"tenants/{TENANT_ID}/uploads/upload-catalogo/catalogo.json",
                catalog_source_sha256="c" * 64,
                catalog_summary_json={"entries": 1},
                plate_upload_id="upload-prancha",
                plate_object_key=PLATE_KEY,
                plate_source_sha256=hashlib.sha256(plate).hexdigest(),
                extraction_id=EXTRACTION_ID,
                extraction_status=extraction_status,
                extraction_requested_by="orcamentista-sintetica",
                extraction_updated_at=now,
                created_by="orcamentista-sintetica",
            )
        )
    return database, database_url


def _worker(
    database_url: str, *, adapter: Any | None, stored: bytes | None
) -> tuple[LocalQueueWorker, FakeObjectStore]:
    worker = LocalQueueWorker(
        LocalWorkerSettings(
            database_url=database_url,
            queue_url="http://localstack/queue",
            aws_region="sa-east-1",
            aws_endpoint_url="http://localstack",
        ),
        valuation_extraction_adapter=adapter,
    )
    storage = FakeObjectStore()
    if stored is not None:
        storage.put_direct(object_key=PLATE_KEY, body=stored)
    worker.s3_client = storage
    return worker, storage


def _message(**overrides: Any) -> dict[str, Any]:
    return {
        "command": "extract_valuation_plate",
        "round_id": ROUND_ID,
        "extraction_id": EXTRACTION_ID,
        "tenant_id": TENANT_ID,
        **overrides,
    }


def _round(database: Database) -> ValuationRoundRecord:
    with database.sessions() as session:
        record = session.get(ValuationRoundRecord, ROUND_ID)
        assert record is not None
        return record


def _revisions(database: Database) -> list[ValuationRoundRevisionRecord]:
    with database.sessions() as session:
        return list(session.scalars(select(ValuationRoundRevisionRecord)))


# --- caminho feliz ----------------------------------------------------------------------


def test_a_extracao_publica_pacote_overlay_e_lineage_numa_revisao(tmp_path: Path) -> None:
    plate = _plate_pdf()
    database, database_url = _seed(tmp_path, plate=plate)
    adapter = _counting_adapter()
    worker, storage = _worker(database_url, adapter=adapter, stored=plate)

    assert worker.dispatch(_message()) == 1

    record = _round(database)
    assert record.extraction_status == "done"
    assert record.extraction_failure_code is None
    assert record.plate_page_count == 1
    # A publicação é ato do sistema sobre a cadeia e avança o contador único da rodada.
    assert record.version == 2
    revisions = _revisions(database)
    assert len(revisions) == 1
    revision = revisions[0]
    assert revision.version == 1
    assert revision.takeoff_packet_json is not None
    assert revision.takeoff_registration_json is not None
    assert revision.code_assignments_json is None
    packet = revision.takeoff_packet_json
    assert packet["plate_id"] == f"rodada-{ROUND_ID}"
    assert len(packet["items"]) == 2

    plate_key = f"tenants/{TENANT_ID}/valuation-rounds/{ROUND_ID}/plate/page-001.png"
    overlay_key = f"tenants/{TENANT_ID}/valuation-rounds/{ROUND_ID}/takeoff/overlay.png"
    assert revision.artifact_refs_json == {
        PLATE_IMAGE_REF: plate_key,
        TAKEOFF_OVERLAY_REF: overlay_key,
    }
    assert revision.artifact_digests_json[PLATE_IMAGE_DIGEST] == packet["image_sha256"]
    assert (
        revision.artifact_digests_json[TAKEOFF_OVERLAY_DIGEST]
        == hashlib.sha256(storage.body(overlay_key)).hexdigest()
    )
    # O overlay nasce do pacote recém-extraído e declara isso: sem esta chave ele nasceria
    # marcado como vencido na rota que o serve (ADR-0030).
    assert revision.artifact_digests_json[TAKEOFF_OVERLAY_PACKET_DIGEST] == document_digest(packet)
    assert [put["ContentType"] for put in storage.puts] == ["image/png", "image/png"]
    assert all(put["ServerSideEncryption"] == "AES256" for put in storage.puts)

    lineage = revision.extraction_lineage_json
    assert lineage is not None
    assert lineage["execution"]["model_id"] == _FIXTURE_MODEL_ID
    assert lineage["consented_source_sha256"] == hashlib.sha256(plate).hexdigest()
    # Lineage é custo e proveniência, nunca a resposta bruta nem o texto da prancha.
    assert "raw" not in json.dumps(lineage).lower()


def test_o_transporte_entrega_o_envelope_sem_job_id(tmp_path: Path) -> None:
    """O despacho roteia por comando ANTES de exigir `job_id` (ADR-0016)."""
    plate = _plate_pdf()
    database, database_url = _seed(tmp_path, plate=plate)
    worker, _storage = _worker(database_url, adapter=_counting_adapter(), stored=plate)
    queue = FakeQueue()
    queue.send_message(MessageBody=json.dumps(_message()))
    worker.client = queue

    assert worker.run_once() == 1

    assert _round(database).extraction_status == "done"
    assert queue.deleted == ["receipt-1"]


# --- entrega repetida e o claim atômico -------------------------------------------------


def test_duas_entregas_do_mesmo_envelope_chamam_o_provider_uma_vez(tmp_path: Path) -> None:
    plate = _plate_pdf()
    database, database_url = _seed(tmp_path, plate=plate)
    adapter = _counting_adapter()
    worker, storage = _worker(database_url, adapter=adapter, stored=plate)

    assert worker.dispatch(_message()) == 1
    assert worker.dispatch(_message()) == 1

    assert adapter.calls == [PromptTask.LEGEND_EXTRACTION.value]
    assert len(_revisions(database)) == 1
    assert len(storage.puts) == 2
    assert _round(database).version == 2


def test_extracao_fora_da_fila_nao_e_reivindicada(tmp_path: Path) -> None:
    """`idle` não é comando pendente: ack sem trabalho, e nada é pago."""
    plate = _plate_pdf()
    database, database_url = _seed(tmp_path, plate=plate, extraction_status="idle")
    adapter = _counting_adapter()
    worker, _storage = _worker(database_url, adapter=adapter, stored=plate)

    assert worker.dispatch(_message()) == 1

    assert adapter.calls == []
    assert _revisions(database) == []
    assert _round(database).extraction_status == "idle"


def test_extracao_de_outro_tenant_nao_e_reivindicada(tmp_path: Path) -> None:
    plate = _plate_pdf()
    database, database_url = _seed(tmp_path, plate=plate)
    adapter = _counting_adapter()
    worker, _storage = _worker(database_url, adapter=adapter, stored=plate)

    assert worker.dispatch(_message(tenant_id="tenant-intruso")) == 1

    assert adapter.calls == []
    assert _round(database).extraction_status == "queued"


def test_identificador_de_extracao_antigo_nao_reivindica_a_rodada(tmp_path: Path) -> None:
    """Envelope de uma extração anterior não sequestra a extração corrente."""
    plate = _plate_pdf()
    database, database_url = _seed(tmp_path, plate=plate)
    adapter = _counting_adapter()
    worker, _storage = _worker(database_url, adapter=adapter, stored=plate)

    assert worker.dispatch(_message(extraction_id="00000000-0000-7000-8000-0000000009ff")) == 1

    assert adapter.calls == []
    assert _round(database).extraction_status == "queued"


# --- desfechos declarados ---------------------------------------------------------------


def test_falha_do_provider_declara_o_codigo_e_nao_publica_nada(tmp_path: Path) -> None:
    plate = _plate_pdf()
    database, database_url = _seed(tmp_path, plate=plate)
    worker, storage = _worker(database_url, adapter=_FailingAdapter(), stored=plate)

    assert worker.dispatch(_message()) == 1

    record = _round(database)
    assert record.extraction_status == "failed"
    assert record.extraction_failure_code == "PROVIDER_EXECUTION_FAILED"
    assert record.version == 1
    assert _revisions(database) == []
    assert storage.puts == []


def test_prancha_divergente_do_digest_consentido_recusa(tmp_path: Path) -> None:
    """O digest declarado no presign é o que o orçamentista consentiu enviar."""
    plate = _plate_pdf()
    database, database_url = _seed(tmp_path, plate=plate)
    adapter = _counting_adapter()
    worker, _storage = _worker(database_url, adapter=adapter, stored=_plate_pdf())

    assert worker.dispatch(_message()) == 1

    record = _round(database)
    assert record.extraction_status == "failed"
    assert record.extraction_failure_code == "LOCAL_UPLOAD_INVALID"
    assert adapter.calls == []
    assert _revisions(database) == []


def test_prancha_ausente_do_armazenamento_falha_declarada(tmp_path: Path) -> None:
    plate = _plate_pdf()
    database, database_url = _seed(tmp_path, plate=plate)
    worker, _storage = _worker(database_url, adapter=_counting_adapter(), stored=None)

    assert worker.dispatch(_message()) == 1

    record = _round(database)
    assert record.extraction_status == "failed"
    assert record.extraction_failure_code == "VALUATION_EXTRACTION_FAILED"
    assert _revisions(database) == []


def test_sem_teto_de_gasto_a_extracao_falha_antes_de_qualquer_chamada(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sem adapter injetado o gate de ambiente vale integralmente, e ele é fail-closed."""
    monkeypatch.delenv(AI_BUDGET_ENV, raising=False)
    monkeypatch.delenv(_ANTHROPIC_KEY_ENV, raising=False)
    plate = _plate_pdf()
    database, database_url = _seed(tmp_path, plate=plate)
    worker, storage = _worker(database_url, adapter=None, stored=plate)

    assert worker.dispatch(_message()) == 1

    record = _round(database)
    assert record.extraction_status == "failed"
    assert record.extraction_failure_code == "LOCAL_EXTRACTION_UNAVAILABLE"
    assert storage.puts == []


# --- braço de reserva (jornada da MEDIÇÃO) ------------------------------------------------


def test_sem_a_env_de_reserva_o_worker_nao_monta_reserva_nenhuma(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O padrão: a fábrica de braço não é sequer tocada, e o pacote sai com as notas de sempre."""
    monkeypatch.delenv(EXTRACTION_RESERVE_ARM_ENV, raising=False)

    def _never(arm_spec: str) -> tuple[str, str, Any]:
        raise AssertionError(f"reserva montada sem a env declarada: {arm_spec}")

    monkeypatch.setattr(round_extraction, "build_extraction_adapter", _never)
    plate = _plate_pdf()
    database, database_url = _seed(tmp_path, plate=plate)
    worker, _storage = _worker(database_url, adapter=_counting_adapter(), stored=plate)

    assert worker.dispatch(_message()) == 1

    assert _round(database).extraction_status == "done"
    packet = _revisions(database)[0].takeoff_packet_json
    assert packet is not None
    assert packet["safety_notes"] == list(LEGEND_EXTRACTION_SAFETY_NOTES)


def test_a_reserva_atende_a_medicao_e_o_pacote_publicado_nomeia_quem_leu(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reserve = _reserve_adapter()
    _install_reserve(monkeypatch, reserve)
    plate = _plate_pdf()
    database, database_url = _seed(tmp_path, plate=plate)
    worker, storage = _worker(database_url, adapter=_FailingAdapter(), stored=plate)

    assert worker.dispatch(_message()) == 1

    record = _round(database)
    assert record.extraction_status == "done"
    assert reserve.calls == [PromptTask.LEGEND_EXTRACTION.value]
    packet = _revisions(database)[0].takeoff_packet_json
    assert packet is not None
    assert packet["safety_notes"] == [*LEGEND_EXTRACTION_SAFETY_NOTES, _RESERVE_NOTE]
    assert all(item["extractor"] == f"openai:{_RESERVE_MODEL_ID}" for item in packet["items"])
    lineage = _revisions(database)[0].extraction_lineage_json
    assert lineage is not None
    # O lineage é do braço que REALMENTE respondeu; o `arm` continua nomeando o escolhido.
    assert lineage["execution"]["provider"] == "openai"
    assert lineage["execution"]["model_id"] == _RESERVE_MODEL_ID
    assert len(storage.puts) == 2


def test_reserva_mal_declarada_recusa_a_extracao_antes_de_qualquer_chamada(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reserva ignorada em silêncio faria o operador achar que tem degradação e não ter."""
    monkeypatch.setenv(EXTRACTION_RESERVE_ARM_ENV, "lixo")
    plate = _plate_pdf()
    database, database_url = _seed(tmp_path, plate=plate)
    adapter = _counting_adapter()
    worker, storage = _worker(database_url, adapter=adapter, stored=plate)

    assert worker.dispatch(_message()) == 1

    record = _round(database)
    assert record.extraction_status == "failed"
    assert record.extraction_failure_code == "LOCAL_EXTRACTION_ARM_INVALID"
    assert adapter.calls == []
    assert _revisions(database) == []
    assert storage.puts == []


def test_com_os_dois_bracos_no_chao_a_medicao_nao_publica_nada(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reserve = _FailingAdapter(code=ProviderFailureCode.REFUSED)
    _install_reserve(monkeypatch, reserve)
    plate = _plate_pdf()
    database, database_url = _seed(tmp_path, plate=plate)
    worker, storage = _worker(database_url, adapter=_FailingAdapter(), stored=plate)

    assert worker.dispatch(_message()) == 1

    record = _round(database)
    assert record.extraction_status == "failed"
    assert record.extraction_failure_code == "PROVIDER_EXECUTION_FAILED"
    assert _revisions(database) == []
    assert storage.puts == []


# --- envelope --------------------------------------------------------------------------


def test_envelope_de_medicao_incompleto_nao_e_roteavel(tmp_path: Path) -> None:
    plate = _plate_pdf()
    _database, database_url = _seed(tmp_path, plate=plate)
    worker, _storage = _worker(database_url, adapter=_counting_adapter(), stored=plate)

    with pytest.raises(UnroutableMessageError):
        worker.dispatch({"command": "extract_valuation_plate", "tenant_id": TENANT_ID})


def test_os_comandos_do_croqui_continuam_exigindo_job_id(tmp_path: Path) -> None:
    """A reordenação do despacho não afrouxa a guarda dos quatro comandos existentes."""
    plate = _plate_pdf()
    _database, database_url = _seed(tmp_path, plate=plate)
    worker, _storage = _worker(database_url, adapter=_counting_adapter(), stored=plate)

    for command in (
        "process_upload",
        "export_scene_package",
        "solve_trace_scene",
        "answer_chat_turn",
    ):
        with pytest.raises(UnroutableMessageError):
            worker.dispatch({"command": command, "tenant_id": TENANT_ID})
