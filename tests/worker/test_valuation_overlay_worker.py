"""Comando de fila `rerender_takeoff_overlay` (F-003 T9, ADR-0030).

O overlay é o desenho que mostra ao orçamentista DE ONDE cada número foi lido, e ele é
reconstruído fora do request path depois de cada decisão. O que este arquivo protege não é
o desenho — isso é assunto de `test_valuation_takeoff_overlay.py` — e sim as três recusas
que separam um artefato honesto de um enganoso:

- comando com pacote defasado é DESCARTADO, porque gravar aqui poria um overlay velho por
  cima do que a decisão seguinte já mandou desenhar;
- rodada sem prancha promovida e imagem que não confere com o pacote não viram desenho: o
  overlay simplesmente continua vencido, e a decisão do orçamentista continua válida;
- a revisão nova carrega TODOS os documentos da cabeça e **não** avança a versão da
  rodada, porque re-render é artefato derivado e não ato humano.

Nenhuma chamada paga acontece aqui: o re-render é determinístico e não toca provider.
"""

from __future__ import annotations

import hashlib
import io
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from PIL import Image
from sqlalchemy import select

from croquito_api.database import (
    Database,
    UploadRecord,
    ValuationRoundRecord,
    ValuationRoundRevisionRecord,
)
from croquito_core.ids import new_uuid7
from croquito_worker.local_queue import (
    VALUATION_OVERLAY_VERSION,
    LocalQueueWorker,
    LocalWorkerSettings,
    UnroutableMessageError,
)
from croquito_worker.valuation.round_extraction import (
    PLATE_IMAGE_DIGEST,
    PLATE_IMAGE_REF,
    TAKEOFF_OVERLAY_DIGEST,
    TAKEOFF_OVERLAY_PACKET_DIGEST,
    TAKEOFF_OVERLAY_REF,
    document_digest,
)
from tests.fakes import FakeObjectStore, FakeQueue

TENANT_ID = "tenant-medicao"
OTHER_TENANT = "tenant-intruso"
ROUND_ID = "00000000-0000-7000-8000-000000000911"
ITEM_ID = "ti_00000000000000b1"
PLATE_KEY = f"tenants/{TENANT_ID}/valuation-rounds/{ROUND_ID}/plate/page-001.png"
OVERLAY_KEY = f"tenants/{TENANT_ID}/valuation-rounds/{ROUND_ID}/takeoff/overlay.png"
_STALE_OVERLAY_DIGEST = "e" * 64
_PREVIOUS_PACKET_DIGEST = "f" * 64


def _plate_png() -> bytes:
    """Página sintética da prancha; nenhuma imagem de cliente entra no Git."""
    image = Image.new("RGB", (900, 1200), "white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _packet_document(*, image_sha256: str, status: str = "confirmed") -> dict[str, Any]:
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
                "status": status,
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


def _seed(
    tmp_path: Path,
    *,
    packet: dict[str, Any],
    plate_ref: bool = True,
) -> tuple[Database, str]:
    """Rodada com pacote publicado e overlay do pacote ANTERIOR — o estado pós-decisão."""
    database_url = f"sqlite+pysqlite:///{tmp_path / 'medicao.db'}"
    database = Database(database_url)
    database.create_schema()
    now = datetime.now(UTC)
    refs = {TAKEOFF_OVERLAY_REF: OVERLAY_KEY}
    if plate_ref:
        refs[PLATE_IMAGE_REF] = PLATE_KEY
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
                version=4,
                catalog_upload_id="upload-catalogo",
                catalog_object_key=f"tenants/{TENANT_ID}/uploads/upload-catalogo/catalogo.json",
                catalog_source_sha256="c" * 64,
                catalog_summary_json={"entries": 1},
                extraction_status="done",
                extraction_updated_at=now,
                created_by="orcamentista-sintetica",
            )
        )
        session.flush()
        session.add(
            ValuationRoundRevisionRecord(
                id=str(new_uuid7()),
                tenant_id=TENANT_ID,
                round_id=ROUND_ID,
                version=2,
                created_by="orcamentista-sintetica",
                takeoff_packet_json=packet,
                takeoff_registration_json={"method": "rulings", "adjusted": [{"item_id": ITEM_ID}]},
                extraction_lineage_json={"worker_version": "valuation-extraction-v1"},
                artifact_refs_json=refs,
                artifact_digests_json={
                    PLATE_IMAGE_DIGEST: str(packet["image_sha256"]),
                    TAKEOFF_OVERLAY_DIGEST: _STALE_OVERLAY_DIGEST,
                    TAKEOFF_OVERLAY_PACKET_DIGEST: _PREVIOUS_PACKET_DIGEST,
                },
            )
        )
    return database, database_url


def _worker(database_url: str, *, plate: bytes | None) -> tuple[LocalQueueWorker, FakeObjectStore]:
    worker = LocalQueueWorker(
        LocalWorkerSettings(
            database_url=database_url,
            queue_url="http://localstack/queue",
            aws_region="sa-east-1",
            aws_endpoint_url="http://localstack",
        )
    )
    storage = FakeObjectStore()
    if plate is not None:
        storage.put_direct(object_key=PLATE_KEY, body=plate, content_type="image/png")
    worker.s3_client = storage
    return worker, storage


def _message(**overrides: Any) -> dict[str, Any]:
    return {
        "command": "rerender_takeoff_overlay",
        "round_id": ROUND_ID,
        "tenant_id": TENANT_ID,
        "packet_sha256": "",
        **overrides,
    }


def _revisions(database: Database) -> list[ValuationRoundRevisionRecord]:
    with database.sessions() as session:
        return list(
            session.scalars(
                select(ValuationRoundRevisionRecord).order_by(ValuationRoundRevisionRecord.version)
            )
        )


def _round(database: Database) -> ValuationRoundRecord:
    with database.sessions() as session:
        record = session.get(ValuationRoundRecord, ROUND_ID)
        assert record is not None
        return record


@pytest.fixture
def plate() -> bytes:
    return _plate_png()


# --- caminho feliz ----------------------------------------------------------------------


def test_o_rerender_publica_overlay_novo_sem_avancar_a_versao_da_rodada(
    tmp_path: Path, plate: bytes
) -> None:
    packet = _packet_document(image_sha256=hashlib.sha256(plate).hexdigest())
    digest = document_digest(packet)
    database, database_url = _seed(tmp_path, packet=packet)
    worker, storage = _worker(database_url, plate=plate)

    assert worker.dispatch(_message(packet_sha256=digest)) == 1

    revisions = _revisions(database)
    assert [revision.version for revision in revisions] == [2, 3]
    published = revisions[1]
    assert published.created_by == VALUATION_OVERLAY_VERSION
    assert published.parent_revision_id == revisions[0].id
    # Só os digests do overlay mudam; todo o resto da cabeça viaja idêntico.
    assert published.takeoff_packet_json == packet
    assert published.takeoff_registration_json == revisions[0].takeoff_registration_json
    assert published.extraction_lineage_json == revisions[0].extraction_lineage_json
    assert published.artifact_refs_json == revisions[0].artifact_refs_json
    overlay_bytes = storage.body(OVERLAY_KEY)
    assert published.artifact_digests_json == {
        PLATE_IMAGE_DIGEST: packet["image_sha256"],
        TAKEOFF_OVERLAY_DIGEST: hashlib.sha256(overlay_bytes).hexdigest(),
        TAKEOFF_OVERLAY_PACKET_DIGEST: digest,
    }
    assert [put["ContentType"] for put in storage.puts] == ["image/png"]
    assert all(put["ServerSideEncryption"] == "AES256" for put in storage.puts)
    # Re-render é artefato derivado: o contador de ato humano da rodada não anda.
    assert _round(database).version == 4


def test_o_transporte_entrega_o_envelope_sem_job_id(tmp_path: Path, plate: bytes) -> None:
    """O despacho roteia por comando ANTES de exigir `job_id` (ADR-0016)."""
    packet = _packet_document(image_sha256=hashlib.sha256(plate).hexdigest())
    database, database_url = _seed(tmp_path, packet=packet)
    worker, _storage = _worker(database_url, plate=plate)
    queue = FakeQueue()
    queue.send_message(MessageBody=json.dumps(_message(packet_sha256=document_digest(packet))))
    worker.client = queue

    assert worker.run_once() == 1

    assert len(_revisions(database)) == 2
    assert queue.deleted == ["receipt-1"]


def test_reentrega_do_mesmo_comando_nao_acrescenta_revisao(tmp_path: Path, plate: bytes) -> None:
    """O desenho é determinístico: a segunda entrega grava os mesmos bytes e nada muda."""
    packet = _packet_document(image_sha256=hashlib.sha256(plate).hexdigest())
    digest = document_digest(packet)
    database, database_url = _seed(tmp_path, packet=packet)
    worker, storage = _worker(database_url, plate=plate)

    assert worker.dispatch(_message(packet_sha256=digest)) == 1
    first = storage.body(OVERLAY_KEY)
    assert worker.dispatch(_message(packet_sha256=digest)) == 1

    assert storage.body(OVERLAY_KEY) == first
    assert [revision.version for revision in _revisions(database)] == [2, 3]


# --- descartes silenciosos --------------------------------------------------------------


def test_pacote_defasado_no_envelope_e_descartado_sem_gravar_overlay(
    tmp_path: Path, plate: bytes
) -> None:
    """Outra decisão já veio depois e já enfileirou o comando dela; este é obsoleto."""
    packet = _packet_document(image_sha256=hashlib.sha256(plate).hexdigest())
    database, database_url = _seed(tmp_path, packet=packet)
    worker, storage = _worker(database_url, plate=plate)

    assert worker.dispatch(_message(packet_sha256=_PREVIOUS_PACKET_DIGEST)) == 1

    assert storage.puts == []
    assert len(_revisions(database)) == 1
    assert _revisions(database)[0].artifact_digests_json[TAKEOFF_OVERLAY_PACKET_DIGEST] == (
        _PREVIOUS_PACKET_DIGEST
    )


def test_decisao_durante_o_render_impede_o_overlay_velho_de_sobrescrever(
    tmp_path: Path, plate: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A chave do overlay é fixa, então gravar tarde mente sobre os bytes servidos.

    O render leva segundos e roda fora de transação. Uma decisão publicada nesse intervalo
    já enfileirou o comando dela; se este ainda gravasse o PNG, a URL assinada passaria a
    servir o desenho do pacote anterior enquanto a revisão declara outro digest — divergência
    que nenhuma leitura posterior detectaria.
    """
    packet = _packet_document(image_sha256=hashlib.sha256(plate).hexdigest())
    database, database_url = _seed(tmp_path, packet=packet)
    worker, storage = _worker(database_url, plate=plate)
    render = worker._render_round_overlay

    def decide_durante_o_render(*args: Any, **kwargs: Any) -> bytes:
        desenho = render(*args, **kwargs)
        seguinte = _packet_document(
            image_sha256=hashlib.sha256(plate).hexdigest(), status="rejected"
        )
        with database.sessions.begin() as session:
            session.add(
                ValuationRoundRevisionRecord(
                    id=str(new_uuid7()),
                    tenant_id=TENANT_ID,
                    round_id=ROUND_ID,
                    version=3,
                    created_by="orcamentista-sintetica",
                    takeoff_packet_json=seguinte,
                    artifact_refs_json={
                        PLATE_IMAGE_REF: PLATE_KEY,
                        TAKEOFF_OVERLAY_REF: OVERLAY_KEY,
                    },
                    artifact_digests_json={TAKEOFF_OVERLAY_PACKET_DIGEST: document_digest(packet)},
                )
            )
        return desenho

    monkeypatch.setattr(worker, "_render_round_overlay", decide_durante_o_render)

    assert worker.dispatch(_message(packet_sha256=document_digest(packet))) == 1

    assert storage.puts == []
    assert [revision.version for revision in _revisions(database)] == [2, 3]


def test_rodada_de_outro_tenant_nao_e_redesenhada(tmp_path: Path, plate: bytes) -> None:
    packet = _packet_document(image_sha256=hashlib.sha256(plate).hexdigest())
    database, database_url = _seed(tmp_path, packet=packet)
    worker, storage = _worker(database_url, plate=plate)

    assert (
        worker.dispatch(_message(packet_sha256=document_digest(packet), tenant_id=OTHER_TENANT))
        == 1
    )

    assert storage.puts == []
    assert len(_revisions(database)) == 1


def test_rodada_sem_prancha_promovida_deixa_o_overlay_vencido(tmp_path: Path, plate: bytes) -> None:
    """Prancha ausente não invalida a decisão: o overlay é que fica para trás."""
    packet = _packet_document(image_sha256=hashlib.sha256(plate).hexdigest())
    database, database_url = _seed(tmp_path, packet=packet, plate_ref=False)
    worker, storage = _worker(database_url, plate=plate)

    assert worker.dispatch(_message(packet_sha256=document_digest(packet))) == 1

    assert storage.puts == []
    assert len(_revisions(database)) == 1


def test_imagem_que_nao_confere_com_o_pacote_nao_vira_overlay(tmp_path: Path, plate: bytes) -> None:
    """Overlay de outra imagem enganaria com a autoridade de um desenho."""
    packet = _packet_document(image_sha256="a" * 64)
    database, database_url = _seed(tmp_path, packet=packet)
    worker, storage = _worker(database_url, plate=plate)

    assert worker.dispatch(_message(packet_sha256=document_digest(packet))) == 1

    assert storage.puts == []
    assert len(_revisions(database)) == 1


def test_rodada_sem_revisao_nenhuma_e_descartada(tmp_path: Path, plate: bytes) -> None:
    packet = _packet_document(image_sha256=hashlib.sha256(plate).hexdigest())
    database, database_url = _seed(tmp_path, packet=packet)
    with database.sessions.begin() as session:
        for revision in session.scalars(select(ValuationRoundRevisionRecord)):
            session.delete(revision)
    worker, storage = _worker(database_url, plate=plate)

    assert worker.dispatch(_message(packet_sha256=document_digest(packet))) == 1

    assert storage.puts == []
    assert _revisions(database) == []


# --- envelope ---------------------------------------------------------------------------


def test_envelope_de_overlay_sem_digest_do_pacote_nao_e_roteavel(
    tmp_path: Path, plate: bytes
) -> None:
    """Sem o digest não há como saber qual pacote o comando manda desenhar."""
    packet = _packet_document(image_sha256=hashlib.sha256(plate).hexdigest())
    _database, database_url = _seed(tmp_path, packet=packet)
    worker, _storage = _worker(database_url, plate=plate)

    with pytest.raises(UnroutableMessageError):
        worker.dispatch(
            {
                "command": "rerender_takeoff_overlay",
                "round_id": ROUND_ID,
                "tenant_id": TENANT_ID,
            }
        )
