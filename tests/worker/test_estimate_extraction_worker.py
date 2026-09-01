"""Comandos de fila da rodada de ORÇAMENTO-BASE (F-020 T6): `extract_estimate_plate` e
`rerender_estimate_takeoff_overlay`.

Espelho de `test_valuation_extraction_worker.py` e `test_valuation_overlay_worker.py`, com
um oráculo a mais que só existe porque agora há DUAS cadeias de rodada: as duas tabelas são
semeadas com o MESMO `round_id`, e cada teste prova que o comando mexeu numa e não encostou
na outra. Envelope ambíguo que fizesse o worker encontrar uma rodada de mesmo id na tabela
errada publicaria o pacote de um cliente na cadeia errada, e nenhum teste de um lado só
enxergaria isso.

Nenhuma chamada externa acontece aqui: o braço pago é injetado como fixture pelo mesmo seam
da medição, e o re-render do overlay é determinístico e não toca provider.
"""

from __future__ import annotations

import hashlib
import io
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pymupdf
import pytest
from PIL import Image
from sqlalchemy import select

from croquito_api.database import (
    Database,
    EstimateRoundRecord,
    EstimateRoundRevisionRecord,
    UploadRecord,
    ValuationRoundPlateRecord,
    ValuationRoundRecord,
    ValuationRoundRevisionRecord,
)
from croquito_core.ids import new_uuid7
from croquito_worker.local_queue import (
    ESTIMATE_EXTRACTION_VERSION,
    ESTIMATE_OVERLAY_VERSION,
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
    EXTRACTION_RESERVE_ARM_ENV,
    PLATE_IMAGE_DIGEST,
    PLATE_IMAGE_REF,
    TAKEOFF_OVERLAY_DIGEST,
    TAKEOFF_OVERLAY_PACKET_DIGEST,
    TAKEOFF_OVERLAY_REF,
    document_digest,
)
from tests.fakes import FakeObjectStore, FakeQueue

TENANT_ID = "tenant-orcamento"
ROUND_ID = "00000000-0000-7000-8000-000000000921"
EXTRACTION_ID = "00000000-0000-7000-8000-000000000922"
ITEM_ID = "ti_00000000000000c1"
PLATE_UPLOAD_KEY = f"tenants/{TENANT_ID}/uploads/upload-prancha/prancha.pdf"
ESTIMATE_PLATE_KEY = f"tenants/{TENANT_ID}/estimate-rounds/{ROUND_ID}/plate/page-001.png"
ESTIMATE_OVERLAY_KEY = f"tenants/{TENANT_ID}/estimate-rounds/{ROUND_ID}/takeoff/overlay.png"
_FIXTURE_MODEL_ID = "fixture-legend-v1"
_RESERVE_MODEL_ID = "fixture-legend-reserva-v1"
_RESERVE_ARM_SPEC = "luna=openai:gpt-5.6-luna"
_RESERVE_NOTE = "PROVIDER_FALLBACK_LEGEND_EXTRACTION_OPENAI"
_BUILT_BY = "orcamentista-que-montou"
"""Subject de quem MONTOU o orçamento; é contra ele que a aprovação compara (F-035)."""
_STALE_OVERLAY_DIGEST = "e" * 64
_PREVIOUS_PACKET_DIGEST = "f" * 64


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


def _plate_png() -> bytes:
    """Página promovida sintética, para o re-render do overlay."""
    image = Image.new("RGB", (900, 1200), "white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


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


def _packet_document(*, image_sha256: str) -> dict[str, Any]:
    """Pacote com um item decidido, como ele fica depois da decisão do orçamentista."""
    return {
        "schema_version": "1.0.0",
        "plate_id": f"rodada-{ROUND_ID}",
        "page_number": 1,
        "image_sha256": image_sha256,
        "source_pdf_sha256": "b" * 64,
        "items": [
            {
                "id": ITEM_ID,
                "evidence": {
                    "plate_id": f"rodada-{ROUND_ID}",
                    "page_number": 1,
                    "image_sha256": image_sha256,
                    "bbox": {"left": 60.0, "top": 100.0, "right": 460.0, "bottom": 140.0},
                },
                "raw_text": "ALAMBRADO GALVANIZADO 10,00 m",
                "label": "ALAMBRADO GALVANIZADO",
                "quantity": "10.00",
                "unit": "m",
                "source": "legend_extraction",
                "extractor": "legend-extractor-sintetico",
                "extractor_version": "1.0.0",
                "status": "confirmed",
                "decision": {
                    "decision_id": "vd_0123456789abcdef",
                    "action": "confirm",
                    "reviewer_id": "orcamentista-sintetica",
                    "reviewer_role": "orcamentista",
                    "decided_at": "2026-08-17T12:00:00+00:00",
                    "note": None,
                },
            }
        ],
        "safety_notes": [
            "Extração automática da legenda; quantidade não confirmada.",
            "Decisão do orçamentista obrigatória antes de qualquer boletim.",
        ],
    }


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


def _seed(tmp_path: Path, *, plate: bytes) -> tuple[Database, str]:
    """Rodada de orçamento em fila e rodada de medição de MESMO id, também em fila.

    As duas existem no mesmo banco de propósito: é a única maneira de um teste enxergar um
    comando que leia a tabela errada.
    """
    database_url = f"sqlite+pysqlite:///{tmp_path / 'orcamento.db'}"
    database = Database(database_url)
    database.create_schema()
    now = datetime.now(UTC)
    catalog_key = f"tenants/{TENANT_ID}/uploads/upload-catalogo/catalogo.json"
    with database.sessions.begin() as session:
        session.add(
            UploadRecord(
                id="upload-catalogo",
                tenant_id=TENANT_ID,
                object_key=catalog_key,
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
                object_key=PLATE_UPLOAD_KEY,
                filename="prancha.pdf",
                content_type="application/pdf",
                size_bytes=len(plate),
                sha256=hashlib.sha256(plate).hexdigest(),
            )
        )
        session.flush()
        session.add(
            EstimateRoundRecord(
                id=ROUND_ID,
                tenant_id=TENANT_ID,
                worksite_key="praca-sintetica-norte",
                worksite_name="PRACA SINTETICA NORTE",
                reference_label="ORCAMENTO-BASE SINTETICO",
                status="OPEN",
                version=1,
                catalog_cascade_json=[],
                plate_upload_id="upload-prancha",
                plate_object_key=PLATE_UPLOAD_KEY,
                plate_source_sha256=hashlib.sha256(plate).hexdigest(),
                extraction_id=EXTRACTION_ID,
                extraction_status="queued",
                extraction_requested_by="orcamentista-sintetica",
                extraction_updated_at=now,
                created_by="orcamentista-sintetica",
            )
        )
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
                catalog_object_key=catalog_key,
                catalog_source_sha256="c" * 64,
                catalog_summary_json={"entries": 1},
                plate_upload_id="upload-prancha",
                plate_object_key=PLATE_UPLOAD_KEY,
                plate_source_sha256=hashlib.sha256(plate).hexdigest(),
                extraction_id=EXTRACTION_ID,
                extraction_status="queued",
                extraction_requested_by="orcamentista-sintetica",
                extraction_updated_at=now,
                created_by="orcamentista-sintetica",
            )
        )
        session.flush()
        # A folha da praça: desde a F-046 T4 é DELA que a extração da medição lê a origem, e
        # as colunas escalares acima seguem só como espelho. Sem esta linha o comando da
        # medição não teria o que reivindicar — que é exatamente o que este arquivo prova ao
        # rodar o comando da medição contra a cadeia certa.
        session.add(
            ValuationRoundPlateRecord(
                id="plate-medicao-1",
                tenant_id=TENANT_ID,
                round_id=ROUND_ID,
                plate_id=f"rodada-{ROUND_ID}",
                position=1,
                upload_id="upload-prancha",
                object_key=PLATE_UPLOAD_KEY,
                source_sha256=hashlib.sha256(plate).hexdigest(),
                page_number=1,
                extraction_id=EXTRACTION_ID,
                extraction_status="queued",
                extraction_requested_by="orcamentista-sintetica",
                extraction_updated_at=now,
                created_by="orcamentista-sintetica",
            )
        )
    return database, database_url


def _seed_takeoff(tmp_path: Path, *, packet: dict[str, Any]) -> tuple[Database, str]:
    """Rodada de orçamento com pacote publicado e overlay do pacote ANTERIOR."""
    database_url = f"sqlite+pysqlite:///{tmp_path / 'orcamento-overlay.db'}"
    database = Database(database_url)
    database.create_schema()
    with database.sessions.begin() as session:
        session.add(
            EstimateRoundRecord(
                id=ROUND_ID,
                tenant_id=TENANT_ID,
                worksite_key="praca-sintetica-norte",
                worksite_name="PRACA SINTETICA NORTE",
                reference_label="ORCAMENTO-BASE SINTETICO",
                status="OPEN",
                version=4,
                catalog_cascade_json=[],
                extraction_status="done",
                created_by="orcamentista-sintetica",
            )
        )
        session.flush()
        session.add(
            EstimateRoundRevisionRecord(
                id=str(new_uuid7()),
                tenant_id=TENANT_ID,
                round_id=ROUND_ID,
                version=2,
                created_by="orcamentista-sintetica",
                takeoff_packet_json=packet,
                takeoff_registration_json={"method": "rulings", "adjusted": [{"item_id": ITEM_ID}]},
                code_assignments_json={"assignments": [{"item_id": ITEM_ID, "code": "01.001.001"}]},
                estimate_json={"lines": [{"code": "01.001.001", "total": "1234.56"}]},
                estimate_template_json={"template_id": "gabarito-sintetico", "revision": 1},
                estimate_built_by=_BUILT_BY,
                extraction_lineage_json={"worker_version": ESTIMATE_EXTRACTION_VERSION},
                artifact_refs_json={
                    PLATE_IMAGE_REF: ESTIMATE_PLATE_KEY,
                    TAKEOFF_OVERLAY_REF: ESTIMATE_OVERLAY_KEY,
                },
                artifact_digests_json={
                    PLATE_IMAGE_DIGEST: str(packet["image_sha256"]),
                    TAKEOFF_OVERLAY_DIGEST: _STALE_OVERLAY_DIGEST,
                    TAKEOFF_OVERLAY_PACKET_DIGEST: _PREVIOUS_PACKET_DIGEST,
                },
            )
        )
    return database, database_url


def _worker(
    database_url: str,
    *,
    adapter: Any | None = None,
    stored: bytes | None = None,
    object_key: str = PLATE_UPLOAD_KEY,
    content_type: str = "application/pdf",
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
        storage.put_direct(object_key=object_key, body=stored, content_type=content_type)
    worker.s3_client = storage
    return worker, storage


def _message(**overrides: Any) -> dict[str, Any]:
    return {
        "command": "extract_estimate_plate",
        "round_id": ROUND_ID,
        "extraction_id": EXTRACTION_ID,
        "tenant_id": TENANT_ID,
        **overrides,
    }


def _overlay_message(**overrides: Any) -> dict[str, Any]:
    return {
        "command": "rerender_estimate_takeoff_overlay",
        "round_id": ROUND_ID,
        "tenant_id": TENANT_ID,
        "packet_sha256": "",
        **overrides,
    }


def _estimate_round(database: Database) -> EstimateRoundRecord:
    with database.sessions() as session:
        record = session.get(EstimateRoundRecord, ROUND_ID)
        assert record is not None
        return record


def _valuation_round(database: Database) -> ValuationRoundRecord:
    with database.sessions() as session:
        record = session.get(ValuationRoundRecord, ROUND_ID)
        assert record is not None
        return record


def _estimate_revisions(database: Database) -> list[EstimateRoundRevisionRecord]:
    with database.sessions() as session:
        return list(
            session.scalars(
                select(EstimateRoundRevisionRecord).order_by(EstimateRoundRevisionRecord.version)
            )
        )


def _valuation_revisions(database: Database) -> list[ValuationRoundRevisionRecord]:
    with database.sessions() as session:
        return list(session.scalars(select(ValuationRoundRevisionRecord)))


# --- extração: caminho feliz -------------------------------------------------------------


def test_a_extracao_do_orcamento_publica_pacote_overlay_e_lineage_numa_revisao(
    tmp_path: Path,
) -> None:
    plate = _plate_pdf()
    database, database_url = _seed(tmp_path, plate=plate)
    adapter = _counting_adapter()
    worker, storage = _worker(database_url, adapter=adapter, stored=plate)

    assert worker.dispatch(_message()) == 1

    record = _estimate_round(database)
    assert record.extraction_status == "done"
    assert record.extraction_failure_code is None
    assert record.plate_page_count == 1
    # A publicação é ato do sistema sobre a cadeia e avança o contador único da rodada.
    assert record.version == 2
    revisions = _estimate_revisions(database)
    assert len(revisions) == 1
    revision = revisions[0]
    assert revision.version == 1
    assert revision.parent_revision_id is None
    assert revision.created_by == ESTIMATE_EXTRACTION_VERSION
    assert revision.takeoff_packet_json is not None
    assert revision.takeoff_registration_json is not None
    assert revision.code_assignments_json is None
    assert revision.estimate_json is None
    packet = revision.takeoff_packet_json
    assert packet["plate_id"] == f"rodada-{ROUND_ID}"
    assert len(packet["items"]) == 2

    # Os blobs nascem sob `estimate-rounds/`, e não sob o prefixo da medição: é o prefixo
    # que a rota do orçamento assina, e escrever no da medição serviria imagem de outra
    # cadeia.
    assert revision.artifact_refs_json == {
        PLATE_IMAGE_REF: ESTIMATE_PLATE_KEY,
        TAKEOFF_OVERLAY_REF: ESTIMATE_OVERLAY_KEY,
    }
    assert revision.artifact_digests_json[PLATE_IMAGE_DIGEST] == packet["image_sha256"]
    assert (
        revision.artifact_digests_json[TAKEOFF_OVERLAY_DIGEST]
        == hashlib.sha256(storage.body(ESTIMATE_OVERLAY_KEY)).hexdigest()
    )
    # O overlay nasce do pacote recém-extraído e declara isso; sem esta chave ele nasceria
    # marcado como vencido na rota que o serve (ADR-0030).
    assert revision.artifact_digests_json[TAKEOFF_OVERLAY_PACKET_DIGEST] == document_digest(packet)
    assert [put["ContentType"] for put in storage.puts] == ["image/png", "image/png"]
    assert all(put["ServerSideEncryption"] == "AES256" for put in storage.puts)

    lineage = revision.extraction_lineage_json
    assert lineage is not None
    assert lineage["worker_version"] == ESTIMATE_EXTRACTION_VERSION
    assert lineage["execution"]["model_id"] == _FIXTURE_MODEL_ID
    assert lineage["consented_source_sha256"] == hashlib.sha256(plate).hexdigest()
    # Lineage é custo e proveniência, nunca a resposta bruta nem o texto da prancha.
    assert "raw" not in json.dumps(lineage).lower()

    # A rodada de medição de MESMO id não foi tocada.
    assert _valuation_round(database).extraction_status == "queued"
    assert _valuation_revisions(database) == []


def test_o_autor_e_o_gabarito_sobrevivem_a_extracao_posterior_ao_build(tmp_path: Path) -> None:
    """`estimate_built_by` e `estimate_template_json` viajam para a revisão da extração.

    A rota da extração só recusa quando já existe uma extração em voo: montar o orçamento
    não fecha a rodada, e extrair de novo é ato normal de quem corrigiu a prancha. Sem estas
    duas colunas na lista do comando de fila, essa segunda extração apagava, sem nenhum ato
    humano, quem montou o orçamento e com qual gabarito a planilha saiu.

    O prejuízo de perder o autor não é auto-aprovação silenciosa — a rota recusa FECHADO com
    `ESTIMATE_APPROVAL_AUTHOR_UNKNOWN` — e sim a orçamentista ter de remontar um orçamento
    que continua correto.

    `estimate_built_by` é escalar, e é por isso que o conserto de `calc_matrix_json` na F-046
    T4 não a alcançou: serializada por `_json_parameter`, a identidade voltaria com aspas de
    JSON dentro da coluna. Por isso a asserção compara com a `str` crua.
    """
    plate = _plate_pdf()
    database, database_url = _seed(tmp_path, plate=plate)
    template = {"template_id": "gabarito-sintetico", "revision": 1}
    with database.sessions.begin() as session:
        session.add(
            EstimateRoundRevisionRecord(
                id=str(new_uuid7()),
                tenant_id=TENANT_ID,
                round_id=ROUND_ID,
                version=1,
                created_by="orcamentista-sintetica",
                estimate_json={"lines": [{"code": "01.001.001", "total": "1234.56"}]},
                estimate_template_json=template,
                estimate_built_by=_BUILT_BY,
                artifact_refs_json={},
                artifact_digests_json={},
            )
        )
    worker, _storage = _worker(database_url, adapter=_counting_adapter(), stored=plate)

    assert worker.dispatch(_message()) == 1

    revisions = _estimate_revisions(database)
    assert [revision.version for revision in revisions] == [1, 2]
    published = revisions[1]
    assert published.estimate_built_by == _BUILT_BY
    assert published.estimate_template_json == template
    # O orçamento montado continua na cabeça: a extração acrescenta pacote, não substitui a
    # cadeia.
    assert published.estimate_json == revisions[0].estimate_json


def test_o_transporte_entrega_o_envelope_do_orcamento_sem_job_id(tmp_path: Path) -> None:
    """O despacho roteia por comando ANTES de exigir `job_id` (ADR-0016)."""
    plate = _plate_pdf()
    database, database_url = _seed(tmp_path, plate=plate)
    worker, _storage = _worker(database_url, adapter=_counting_adapter(), stored=plate)
    queue = FakeQueue()
    queue.send_message(MessageBody=json.dumps(_message()))
    worker.client = queue

    assert worker.run_once() == 1

    assert _estimate_round(database).extraction_status == "done"
    assert queue.deleted == ["receipt-1"]


def test_duas_entregas_do_mesmo_envelope_chamam_o_provider_uma_vez(tmp_path: Path) -> None:
    plate = _plate_pdf()
    database, database_url = _seed(tmp_path, plate=plate)
    adapter = _counting_adapter()
    worker, storage = _worker(database_url, adapter=adapter, stored=plate)

    assert worker.dispatch(_message()) == 1
    assert worker.dispatch(_message()) == 1

    assert adapter.calls == [PromptTask.LEGEND_EXTRACTION.value]
    assert len(_estimate_revisions(database)) == 1
    assert len(storage.puts) == 2
    assert _estimate_round(database).version == 2


# --- extração: desfechos declarados ------------------------------------------------------


def test_falha_do_provider_declara_o_codigo_e_nao_publica_nada(tmp_path: Path) -> None:
    plate = _plate_pdf()
    database, database_url = _seed(tmp_path, plate=plate)
    worker, storage = _worker(database_url, adapter=_FailingAdapter(), stored=plate)

    assert worker.dispatch(_message()) == 1

    record = _estimate_round(database)
    assert record.extraction_status == "failed"
    assert record.extraction_failure_code == "PROVIDER_EXECUTION_FAILED"
    assert record.version == 1
    assert _estimate_revisions(database) == []
    assert storage.puts == []


def test_prancha_divergente_do_digest_consentido_recusa(tmp_path: Path) -> None:
    """O digest declarado no presign é o que o orçamentista consentiu enviar."""
    plate = _plate_pdf()
    database, database_url = _seed(tmp_path, plate=plate)
    adapter = _counting_adapter()
    worker, _storage = _worker(database_url, adapter=adapter, stored=_plate_pdf())

    assert worker.dispatch(_message()) == 1

    record = _estimate_round(database)
    assert record.extraction_status == "failed"
    assert record.extraction_failure_code == "LOCAL_UPLOAD_INVALID"
    assert adapter.calls == []
    assert _estimate_revisions(database) == []


def test_extracao_de_outro_tenant_nao_e_reivindicada(tmp_path: Path) -> None:
    plate = _plate_pdf()
    database, database_url = _seed(tmp_path, plate=plate)
    adapter = _counting_adapter()
    worker, _storage = _worker(database_url, adapter=adapter, stored=plate)

    assert worker.dispatch(_message(tenant_id="tenant-intruso")) == 1

    assert adapter.calls == []
    assert _estimate_round(database).extraction_status == "queued"


# --- braço de reserva (jornada do ORÇAMENTO-BASE) -----------------------------------------
#
# Par obrigatório dos testes de reserva de `test_valuation_extraction_worker.py`: o handler
# de extração é UM só para as duas cadeias, e a variável `CROQUITO_EXTRACTION_RESERVE_ARM`
# não diz "MEDICAO" justamente porque a reserva tem de valer aqui também. Sem este arquivo
# provar a mesma degradação na cadeia do orçamento, uma regressão que ligasse a reserva só
# na medição passaria verde do outro lado.


def test_sem_a_env_de_reserva_o_orcamento_nao_monta_reserva_nenhuma(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(EXTRACTION_RESERVE_ARM_ENV, raising=False)

    def _never(arm_spec: str) -> tuple[str, str, Any]:
        raise AssertionError(f"reserva montada sem a env declarada: {arm_spec}")

    monkeypatch.setattr(round_extraction, "build_extraction_adapter", _never)
    plate = _plate_pdf()
    database, database_url = _seed(tmp_path, plate=plate)
    worker, _storage = _worker(database_url, adapter=_counting_adapter(), stored=plate)

    assert worker.dispatch(_message()) == 1

    assert _estimate_round(database).extraction_status == "done"
    packet = _estimate_revisions(database)[0].takeoff_packet_json
    assert packet is not None
    assert packet["safety_notes"] == list(LEGEND_EXTRACTION_SAFETY_NOTES)


def test_a_reserva_atende_o_orcamento_e_o_pacote_publicado_nomeia_quem_leu(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(EXTRACTION_RESERVE_ARM_ENV, _RESERVE_ARM_SPEC)
    reserve = _reserve_adapter()

    def _factory(arm_spec: str) -> tuple[str, str, Any]:
        assert arm_spec == _RESERVE_ARM_SPEC
        return "luna", _RESERVE_MODEL_ID, reserve

    monkeypatch.setattr(round_extraction, "build_extraction_adapter", _factory)
    plate = _plate_pdf()
    database, database_url = _seed(tmp_path, plate=plate)
    worker, storage = _worker(database_url, adapter=_FailingAdapter(), stored=plate)

    assert worker.dispatch(_message()) == 1

    assert _estimate_round(database).extraction_status == "done"
    assert reserve.calls == [PromptTask.LEGEND_EXTRACTION.value]
    revisions = _estimate_revisions(database)
    assert len(revisions) == 1
    packet = revisions[0].takeoff_packet_json
    assert packet is not None
    assert packet["safety_notes"] == [*LEGEND_EXTRACTION_SAFETY_NOTES, _RESERVE_NOTE]
    assert all(item["extractor"] == f"openai:{_RESERVE_MODEL_ID}" for item in packet["items"])
    assert len(storage.puts) == 2


# --- as duas cadeias não se cruzam -------------------------------------------------------


def test_o_comando_da_medicao_continua_indo_para_a_cadeia_da_medicao(tmp_path: Path) -> None:
    """Não regressão do despacho: o comando antigo publica na tabela antiga, e só nela."""
    plate = _plate_pdf()
    database, database_url = _seed(tmp_path, plate=plate)
    worker, storage = _worker(database_url, adapter=_counting_adapter(), stored=plate)

    assert (
        worker.dispatch(
            {
                "command": "extract_valuation_plate",
                "round_id": ROUND_ID,
                "extraction_id": EXTRACTION_ID,
                "tenant_id": TENANT_ID,
            }
        )
        == 1
    )

    assert _valuation_round(database).extraction_status == "done"
    assert len(_valuation_revisions(database)) == 1
    assert _estimate_round(database).extraction_status == "queued"
    assert _estimate_revisions(database) == []
    # E os blobs foram para o prefixo da medição, não para o do orçamento.
    assert [put["Key"] for put in storage.puts] == [
        f"tenants/{TENANT_ID}/valuation-rounds/{ROUND_ID}/plate/page-001.png",
        f"tenants/{TENANT_ID}/valuation-rounds/{ROUND_ID}/takeoff/overlay.png",
    ]


# --- overlay ----------------------------------------------------------------------------


def test_o_rerender_do_orcamento_publica_overlay_sem_avancar_a_versao_da_rodada(
    tmp_path: Path,
) -> None:
    plate = _plate_png()
    packet = _packet_document(image_sha256=hashlib.sha256(plate).hexdigest())
    digest = document_digest(packet)
    database, database_url = _seed_takeoff(tmp_path, packet=packet)
    worker, storage = _worker(
        database_url, stored=plate, object_key=ESTIMATE_PLATE_KEY, content_type="image/png"
    )

    assert worker.dispatch(_overlay_message(packet_sha256=digest)) == 1

    revisions = _estimate_revisions(database)
    assert [revision.version for revision in revisions] == [2, 3]
    published = revisions[1]
    assert published.created_by == ESTIMATE_OVERLAY_VERSION
    assert published.parent_revision_id == revisions[0].id
    # Só os digests do overlay mudam; TODO o resto da cabeça viaja idêntico — inclusive
    # `estimate_json`, que é a coluna que só existe nesta cadeia. Uma revisão que a
    # esquecesse apagaria o orçamento montado sem nenhum ato humano.
    assert published.takeoff_packet_json == packet
    assert published.takeoff_registration_json == revisions[0].takeoff_registration_json
    assert published.code_assignments_json == revisions[0].code_assignments_json
    assert published.estimate_json == revisions[0].estimate_json
    # O gabarito e o AUTOR do orçamento viajam pelo mesmo motivo, e o segundo não é JSON:
    # ele sai da coluna como `str` e volta a ela como `str`, sem aspas de serialização.
    assert published.estimate_template_json == revisions[0].estimate_template_json
    assert published.estimate_built_by == _BUILT_BY
    assert published.extraction_lineage_json == revisions[0].extraction_lineage_json
    assert published.artifact_refs_json == revisions[0].artifact_refs_json
    overlay_bytes = storage.body(ESTIMATE_OVERLAY_KEY)
    assert published.artifact_digests_json == {
        PLATE_IMAGE_DIGEST: packet["image_sha256"],
        TAKEOFF_OVERLAY_DIGEST: hashlib.sha256(overlay_bytes).hexdigest(),
        TAKEOFF_OVERLAY_PACKET_DIGEST: digest,
    }
    # Re-render é artefato derivado: o contador de ato humano da rodada não anda.
    assert _estimate_round(database).version == 4


def test_pacote_defasado_no_envelope_e_descartado_sem_gravar_overlay(tmp_path: Path) -> None:
    """Outra decisão já veio depois e já enfileirou o comando dela; este é obsoleto."""
    plate = _plate_png()
    packet = _packet_document(image_sha256=hashlib.sha256(plate).hexdigest())
    database, database_url = _seed_takeoff(tmp_path, packet=packet)
    worker, storage = _worker(
        database_url, stored=plate, object_key=ESTIMATE_PLATE_KEY, content_type="image/png"
    )

    assert worker.dispatch(_overlay_message(packet_sha256=_PREVIOUS_PACKET_DIGEST)) == 1

    assert storage.puts == []
    assert len(_estimate_revisions(database)) == 1


def test_rodada_de_outro_tenant_nao_e_redesenhada(tmp_path: Path) -> None:
    plate = _plate_png()
    packet = _packet_document(image_sha256=hashlib.sha256(plate).hexdigest())
    database, database_url = _seed_takeoff(tmp_path, packet=packet)
    worker, storage = _worker(
        database_url, stored=plate, object_key=ESTIMATE_PLATE_KEY, content_type="image/png"
    )

    assert (
        worker.dispatch(
            _overlay_message(packet_sha256=document_digest(packet), tenant_id="tenant-intruso")
        )
        == 1
    )

    assert storage.puts == []
    assert len(_estimate_revisions(database)) == 1


# --- envelope ---------------------------------------------------------------------------


def test_envelope_de_extracao_do_orcamento_incompleto_nao_e_roteavel(tmp_path: Path) -> None:
    plate = _plate_pdf()
    _database, database_url = _seed(tmp_path, plate=plate)
    worker, _storage = _worker(database_url, adapter=_counting_adapter(), stored=plate)

    with pytest.raises(UnroutableMessageError):
        worker.dispatch({"command": "extract_estimate_plate", "tenant_id": TENANT_ID})


def test_envelope_de_overlay_do_orcamento_sem_digest_do_pacote_nao_e_roteavel(
    tmp_path: Path,
) -> None:
    """Sem o digest não há como saber qual pacote o comando manda desenhar."""
    plate = _plate_pdf()
    _database, database_url = _seed(tmp_path, plate=plate)
    worker, _storage = _worker(database_url, adapter=_counting_adapter(), stored=plate)

    with pytest.raises(UnroutableMessageError):
        worker.dispatch(
            {
                "command": "rerender_estimate_takeoff_overlay",
                "round_id": ROUND_ID,
                "tenant_id": TENANT_ID,
            }
        )
