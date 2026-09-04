"""Cadeia completa: upload autenticado até o pacote CAD auditado.

O teste exercita API e worker sobre o mesmo banco e o mesmo storage, incluindo o envelope
real publicado na fila. Nenhuma etapa é pulada: sem decisão humana não há cena, sem
reconhecimento explícito não há aprovação e sem auditoria aprovada não há pacote.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from croquito_api.config import ApiSettings
from croquito_api.database import (
    Database,
    FieldEvidenceAnalysisRecord,
    JobFieldPhotoRecord,
    SurveyRecord,
)
from croquito_api.main import create_app
from croquito_core.events import DOMAIN_EVENT_TYPES
from croquito_worker.association_confidence import CONFIDENCE_SCORE_VERSION
from croquito_worker.criteria import ScopeCriterion
from croquito_worker.domain_event_publisher import (
    FileDomainEventPublisher,
    drain_domain_events,
)
from croquito_worker.local_queue import LocalQueueWorker, LocalWorkerSettings
from croquito_worker.review_seed import SeedInputs, seed_review
from tests.api.test_field_evidence import _packet as _survey_packet
from tests.bundles import (
    CIRCLE_PROPOSAL_ID,
    CIRCLE_READING_ID,
    ELEVATION_M,
    ELEVATION_PROPOSAL_ID,
    ELEVATION_READING_ID,
    HEIGHT_M,
    HEIGHT_PROPOSAL_ID,
    HEIGHT_READING_ID,
    WIDTH_M,
    WIDTH_PROPOSAL_ID,
    WIDTH_READING_ID,
    write_seed_bundle,
)
from tests.fakes import FakeObjectStore, FakeQueue, synthetic_pdf

TENANT = "tenant-e2e"
QUEUE_URL = "http://localstack/queue"
SCOPE_CRITERION = "ACC_GUA_001"
SCOPE_CRITERION_TEXT = "Perímetro, linha central, círculo, áreas e gols são entidades CAD limpas."


def _headers(key: str, *, tenant: str = TENANT, roles: str = "engineer") -> dict[str, str]:
    return {
        "Authorization": f"Bearer test:{tenant}:eng-e2e:{roles}",
        "Idempotency-Key": key,
    }


def _line_entity_id(
    scene: dict[str, Any], start: tuple[float, float], end: tuple[float, float]
) -> str:
    for entity in scene["entities"]:
        geometry = entity["geometry"]
        if geometry["type"] != "line":
            continue
        current = (
            (geometry["start"]["x"], geometry["start"]["y"]),
            (geometry["end"]["x"], geometry["end"]["y"]),
        )
        if current == (start, end):
            return str(entity["id"])
    raise AssertionError(f"Entidade de linha {start}->{end} ausente na cena do solver.")


@pytest.fixture
def stack(tmp_path: Path) -> tuple[TestClient, LocalQueueWorker, FakeObjectStore, FakeQueue]:
    """API e worker sobre o mesmo SQLite em arquivo, o mesmo storage e a mesma fila."""
    database_url = f"sqlite+pysqlite:///{tmp_path / 'e2e.db'}"
    database = Database(database_url)
    database.create_schema()
    settings = ApiSettings(
        database_url=database_url,
        artifact_bucket="croquito-e2e",
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
    # The real ProcessingQueue is kept, so the published envelope is the production one.
    app.state.queue.client = queue

    worker = LocalQueueWorker(
        LocalWorkerSettings(
            database_url=database_url,
            queue_url=QUEUE_URL,
            aws_region="sa-east-1",
            aws_endpoint_url="http://localhost:4566",
            artifact_bucket="croquito-e2e",
        )
    )
    worker.client = queue
    worker.s3_client = storage
    return TestClient(app), worker, storage, queue


_ENVELOPE_KEYS = {"event_id", "event_type", "tenant_id", "occurred_at", "job_id", "payload"}

#: Nomes que, se aparecessem num payload, seriam conteúdo — e não fato observável.
_FORBIDDEN_PAYLOAD_KEYS = frozenset(
    {
        "raw_text",
        "text",
        "url",
        "package_url",
        "signed_url",
        "token",
        "authorization",
        "image",
        "preview",
        "body",
        "scene",
        "filename",
        "project_name",
        "worksite_name",
        "raw_response_ref",
    }
)


def _assert_domain_events_contract(database_url: str, destino: Path) -> list[dict[str, Any]]:
    """Drena a outbox pelo relay e confere TODO envelope emitido pela cadeia real.

    A conferência é sobre o que a jornada inteira realmente publicou, e não sobre um
    payload montado à mão: um evento novo acrescentado num sítio qualquer do pipeline cai
    aqui automaticamente, que é o único jeito de esta fronteira não apodrecer.
    """
    engine = create_engine(database_url)
    try:
        primeiro = drain_domain_events(engine, FileDomainEventPublisher(destino))
        # Reexecução não republica nada: `published_at` já marcado sai da varredura.
        segundo = drain_domain_events(engine, FileDomainEventPublisher(destino))
    finally:
        engine.dispose()
    assert primeiro.published > 0
    assert primeiro.remaining == 0
    assert (segundo.published, segundo.remaining) == (0, 0)

    envelopes = [json.loads(linha) for linha in destino.read_text(encoding="utf-8").splitlines()]
    assert len(envelopes) == primeiro.published
    for envelope in envelopes:
        assert set(envelope) == _ENVELOPE_KEYS, envelope
        assert envelope["event_type"] in DOMAIN_EVENT_TYPES
        assert envelope["tenant_id"] == TENANT
        # RFC 3339 UTC: o consumidor ordena por entidade com isto.
        assert datetime.fromisoformat(envelope["occurred_at"]).tzinfo is not None
        for chave, valor in envelope["payload"].items():
            assert chave not in _FORBIDDEN_PAYLOAD_KEYS, envelope
            assert valor is None or isinstance(valor, str | int | float | bool), envelope
            if isinstance(valor, str):
                # URL assinada e blob base64 são as duas formas que conteúdo tomaria.
                assert not valor.startswith(("http://", "https://")), envelope
                assert len(valor) <= 120, envelope
    inteiro = json.dumps(envelopes, ensure_ascii=False)
    for conteudo in (f"{WIDTH_M} m", f"{HEIGHT_M} m", "levantamento.pdf", "Caso sintético"):
        assert conteudo not in inteiro, conteudo
    return envelopes


def test_authenticated_flow_reaches_an_audited_package(
    tmp_path: Path,
    stack: tuple[TestClient, LocalQueueWorker, FakeObjectStore, FakeQueue],
) -> None:
    client, worker, storage, queue = stack
    pdf = synthetic_pdf()
    source_sha256 = hashlib.sha256(pdf).hexdigest()

    # 1. Upload autenticado: presign declara o digest real e o browser grava os bytes.
    presign = client.post(
        "/v1/uploads/presign",
        headers=_headers("e2e-presign"),
        json={
            "filename": "levantamento.pdf",
            "content_type": "application/pdf",
            "size_bytes": len(pdf),
            "sha256": source_sha256,
        },
    )
    assert presign.status_code == 200
    storage.put_direct(object_key=presign.json()["object_key"], body=pdf)

    # 2. Job criado e comando publicado na fila.
    created = client.post(
        "/v1/jobs",
        headers=_headers("e2e-job"),
        json={
            "upload_id": presign.json()["upload_id"],
            "project_name": "Caso sintético",
            "default_unit": "m",
        },
    )
    assert created.status_code == 201
    job_id = created.json()["job_id"]
    assert queue.commands() == []

    # 3. Worker valida o PDF e libera a revisão.
    assert worker.run_once() == 1
    assert queue.commands() == ["process_upload"]
    review_endpoint = f"/v1/jobs/{job_id}/review"
    assert client.get(review_endpoint, headers=_headers("e2e-read")).status_code == 409

    # 4. Carga do pacote autorizado, sem nenhuma decisão fabricada.
    bundle = write_seed_bundle(tmp_path / "bundle", source_sha256=source_sha256)
    seeded = seed_review(
        SeedInputs(
            job_id=UUID(job_id),
            tenant_id=TENANT,
            packet_path=bundle["packet"],
            associations_path=bundle["associations"],
            proposals_path=bundle["proposals"],
            rectangle_request_path=bundle["rectangle_request"],
            manifest_path=bundle["manifest"],
            image_path=bundle["image"],
            required_criteria=(ScopeCriterion(code=SCOPE_CRITERION, text=SCOPE_CRITERION_TEXT),),
            operator_id="tenant-admin-e2e",
        ),
        LocalWorkerSettings(
            database_url=f"sqlite+pysqlite:///{tmp_path / 'e2e.db'}",
            queue_url="",
            aws_region="sa-east-1",
            aws_endpoint_url="http://localhost:4566",
            artifact_bucket="croquito-e2e",
        ),
        s3_client=storage,
    )
    assert seeded.review_version == 1

    review = client.get(review_endpoint, headers=_headers("e2e-read-2"))
    assert review.status_code == 200
    assert review.json()["scene"] is None
    assert review.json()["required_criteria"] == [
        {"code": SCOPE_CRITERION, "text": SCOPE_CRITERION_TEXT}
    ]
    assert any("HUMAN_CONFIRMATION_REQUIRED" in item for item in review.json()["blockers"])
    # A conferência de cadeias viaja na mesma resposta desde o começo: sem leitura
    # confirmada as duas listas estão vazias, e nenhuma delas vira blocker.
    assert review.json()["suggested_chains"] == []
    assert review.json()["declared_chains"] == []

    # 5. Decisão humana com associação explícita: só então nasce a cena métrica.
    solved = client.post(
        f"{review_endpoint}/decisions",
        headers=_headers("e2e-decisions"),
        json={
            "base_version": 1,
            "decisions": [
                {
                    "reading_id": WIDTH_READING_ID,
                    "action": "confirm",
                    "justification": "Cota conferida na evidência protegida.",
                    "association_proposal_id": WIDTH_PROPOSAL_ID,
                },
                {
                    "reading_id": HEIGHT_READING_ID,
                    "action": "confirm",
                    "justification": "Cota conferida na evidência protegida.",
                    "association_proposal_id": HEIGHT_PROPOSAL_ID,
                },
                {
                    "reading_id": CIRCLE_READING_ID,
                    "action": "confirm",
                    "justification": "Diâmetro conferido na evidência protegida.",
                    "association_proposal_id": CIRCLE_PROPOSAL_ID,
                },
            ],
        },
    )
    assert solved.status_code == 200
    scene = solved.json()["scene"]
    assert scene["version"] == 1
    assert scene["approved"] is False
    assert SCOPE_CRITERION in solved.json()["blockers"]

    # 6. Calibração ancorada nas próprias arestas do solver.
    width = float(WIDTH_M)
    height = float(HEIGHT_M)
    calibration = client.post(
        f"{review_endpoint}/calibration",
        headers=_headers("e2e-calibration"),
        json={
            "base_review_version": 2,
            "base_scene_version": 1,
            "anchors": [
                {
                    "proposal_id": WIDTH_PROPOSAL_ID,
                    "entity_id": _line_entity_id(scene, (width, 0.0), (0.0, 0.0)),
                    "reversed": True,
                },
                {
                    "proposal_id": HEIGHT_PROPOSAL_ID,
                    "entity_id": _line_entity_id(scene, (0.0, 0.0), (0.0, height)),
                },
            ],
        },
    )
    assert calibration.status_code == 200

    # 7. Aceite de proposta CV: vira geometria approximate rastreável.
    accepted = client.post(
        f"{review_endpoint}/proposals",
        headers=_headers("e2e-accept"),
        json={
            "base_review_version": 3,
            "base_scene_version": 1,
            "proposal_id": CIRCLE_PROPOSAL_ID,
            "action": "accept",
            "justification": "Círculo aceito como hipótese visual revisada.",
            "calibration_id": calibration.json()["calibration"]["calibration_id"],
        },
    )
    assert accepted.status_code == 200
    approximate_id = accepted.json()["proposal_decisions"][-1]["entity_id"]
    draft_id = accepted.json()["scene"]["id"]
    assert accepted.json()["scene"]["version"] == 2

    approval = {
        "revision_id": draft_id,
        "accepted_approximations": [approximate_id],
        "source_evidence_checked": True,
        "geometry_checked": True,
        "limitations_acknowledged": True,
        "statement": "Cena cobre apenas o campo principal conferido na evidência.",
    }

    # 8. Sem reconhecer o critério de escopo, a aprovação falha fechado.
    refused = client.post(
        f"/v1/jobs/{job_id}/approve", headers=_headers("e2e-approve-open"), json=approval
    )
    assert refused.status_code == 422
    assert f"OPEN_CRITICAL_ISSUE:{SCOPE_CRITERION}" in refused.json()["errors"]

    approved = client.post(
        f"/v1/jobs/{job_id}/approve",
        headers=_headers("e2e-approve"),
        json={**approval, "acknowledged_criteria": [SCOPE_CRITERION]},
    )
    assert approved.status_code == 200
    assert approved.json()["approved"] is True
    approved_id = approved.json()["id"]

    # 9. Export: a API só enfileira; o pacote é construído fora do request path.
    requested = client.post(
        f"/v1/jobs/{job_id}/exports",
        headers=_headers("e2e-export"),
        json={"revision_id": approved_id},
    )
    assert requested.status_code == 202
    assert requested.json()["status"] == "QUEUED"
    assert requested.json()["package_url"] is None
    export_id = requested.json()["export_id"]

    assert worker.run_once() == 1
    assert queue.commands() == ["process_upload", "export_scene_package"]

    completed = client.get(
        f"/v1/jobs/{job_id}/exports/{export_id}", headers=_headers("e2e-export-read")
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "COMPLETED"
    assert completed.json()["audit_status"] == "approved"
    assert completed.json()["package_url"] is not None

    # 10. O pacote publicado carrega a auditoria e a ressalva reconhecida.
    package_key = f"tenants/{TENANT}/jobs/{job_id}/exports/{export_id}/croquito.zip"
    with zipfile.ZipFile(BytesIO(storage.body(package_key))) as package:
        assert sorted(package.namelist()) == [
            "aprovacao.json",
            "auditoria.json",
            "desenho.dxf",
            "hipoteses.json",
            "preview.png",
            "quantitativos.csv",
        ]
        audit = json.loads(package.read("auditoria.json"))
        assert audit["status"] == "approved"
        assert audit["dxf_sha256"] == completed.json()["dxf_sha256"]
        approval_record = json.loads(package.read("aprovacao.json"))
        # Os dois atos aparecem separados: aqui a cena não cobre o critério reconhecido.
        assert approval_record["acknowledged_criteria"] == [SCOPE_CRITERION]
        assert approval_record["covered_criteria"] == []
        assert approval_record["limitations_acknowledged"] is True
        assert approval_record["source_scene_id"] == draft_id

    assert cast(str, completed.json()["package_url"]).startswith(
        f"https://storage.invalid/tenants/{TENANT}/"
    )

    # 11. F-031 T2: a mesma jornada deixou a outbox pronta; o relay a drena e todo
    # envelope publicado obedece ao contrato de consumo — inclusive a URL assinada que a
    # resposta acima carrega e que NENHUM evento pode ter levado junto.
    envelopes = _assert_domain_events_contract(
        f"sqlite+pysqlite:///{tmp_path / 'e2e.db'}", tmp_path / "eventos.jsonl"
    )
    tipos = {envelope["event_type"] for envelope in envelopes}
    assert {
        "croquito.job.created.v1",
        "croquito.job.stage_changed.v1",
        "croquito.review.decisions_recorded.v1",
        "croquito.review.calibration_set.v1",
        "croquito.review.proposals_decided.v1",
        "croquito.scene.approved.v1",
        "croquito.export.completed.v1",
    } <= tipos
    # A cadeia inteira é de UM job; os eventos do croqui o nomeiam sem exceção.
    assert {envelope["job_id"] for envelope in envelopes} == {job_id}


def test_a_wrong_decision_is_rectified_and_the_package_still_closes(
    tmp_path: Path,
    stack: tuple[TestClient, LocalQueueWorker, FakeObjectStore, FakeQueue],
) -> None:
    """Perna da correção declarada: decidir errado, corrigir, re-resolver e exportar.

    A decisão errada não é apagada: ela continua na revisão em que foi tomada, e a
    correção é um ato humano novo que cria a revisão seguinte.
    """
    client, worker, storage, queue = stack
    pdf = synthetic_pdf()
    source_sha256 = hashlib.sha256(pdf).hexdigest()

    presign = client.post(
        "/v1/uploads/presign",
        headers=_headers("rectify-presign"),
        json={
            "filename": "levantamento.pdf",
            "content_type": "application/pdf",
            "size_bytes": len(pdf),
            "sha256": source_sha256,
        },
    )
    storage.put_direct(object_key=presign.json()["object_key"], body=pdf)
    created = client.post(
        "/v1/jobs",
        headers=_headers("rectify-job"),
        json={
            "upload_id": presign.json()["upload_id"],
            "project_name": "Correção declarada",
            "default_unit": "m",
        },
    )
    assert created.status_code == 201
    job_id = created.json()["job_id"]
    assert worker.run_once() == 1

    bundle = write_seed_bundle(tmp_path / "rectify-bundle", source_sha256=source_sha256)
    seed_review(
        SeedInputs(
            job_id=UUID(job_id),
            tenant_id=TENANT,
            packet_path=bundle["packet"],
            associations_path=bundle["associations"],
            proposals_path=bundle["proposals"],
            rectangle_request_path=bundle["rectangle_request"],
            manifest_path=bundle["manifest"],
            image_path=bundle["image"],
            required_criteria=(),
            operator_id="tenant-admin-e2e",
        ),
        LocalWorkerSettings(
            database_url=f"sqlite+pysqlite:///{tmp_path / 'e2e.db'}",
            queue_url="",
            aws_region="sa-east-1",
            aws_endpoint_url="http://localhost:4566",
            artifact_bucket="croquito-e2e",
        ),
        s3_client=storage,
    )

    # 1. A largura é confirmada com o valor errado — o erro humano que a correção existe
    # para consertar sem refazer o job inteiro.
    solved = client.post(
        f"/v1/jobs/{job_id}/review/decisions",
        headers=_headers("rectify-decisions"),
        json={
            "base_version": 1,
            "decisions": [
                {
                    "reading_id": WIDTH_READING_ID,
                    "action": "confirm",
                    "justification": "Confirmada como estava escrita na proposta.",
                    "association_proposal_id": WIDTH_PROPOSAL_ID,
                    "raw_text": "12,00",
                    "value_si": "12.00",
                    "unit": "m",
                },
                {
                    "reading_id": HEIGHT_READING_ID,
                    "action": "confirm",
                    "justification": "Cota conferida na evidência protegida.",
                    "association_proposal_id": HEIGHT_PROPOSAL_ID,
                },
                {
                    "reading_id": CIRCLE_READING_ID,
                    "action": "confirm",
                    "justification": "Diâmetro conferido na evidência protegida.",
                    "association_proposal_id": CIRCLE_PROPOSAL_ID,
                },
            ],
        },
    )
    assert solved.status_code == 200
    wrong_scene = solved.json()["scene"]
    assert wrong_scene["version"] == 1
    wrong_decision_id = next(
        reading["decision"]["decision_id"]
        for reading in solved.json()["packet"]["readings"]
        if reading["id"] == WIDTH_READING_ID
    )

    # 2. Uma segunda decisão sobre a mesma leitura é recusada e aponta a correção.
    overwritten = client.post(
        f"/v1/jobs/{job_id}/review/decisions",
        headers=_headers("rectify-overwrite"),
        json={
            "base_version": 2,
            "decisions": [
                {
                    "reading_id": WIDTH_READING_ID,
                    "action": "correct",
                    "justification": "Tentativa de sobrescrever a decisão registrada.",
                    "association_proposal_id": WIDTH_PROPOSAL_ID,
                    "raw_text": "25,90",
                    "value_si": str(WIDTH_M),
                    "unit": "m",
                }
            ],
        },
    )
    assert overwritten.status_code == 422
    assert overwritten.json()["detail"]["code"] == "READING_ALREADY_DECIDED"

    # 3. A correção declarada cria a revisão seguinte e re-resolve a cena.
    rectified = client.post(
        f"/v1/jobs/{job_id}/review/rectifications",
        headers=_headers("rectify-command"),
        json={
            "base_version": 2,
            "rectifications": [
                {
                    "reading_id": WIDTH_READING_ID,
                    "action": "confirm",
                    "rectifies_decision_id": wrong_decision_id,
                    "justification": "O 12,00 é de outra cota; a largura do campo é 25,90.",
                    "association_proposal_id": WIDTH_PROPOSAL_ID,
                    "raw_text": "25,90",
                    "value_si": str(WIDTH_M),
                    "unit": "m",
                }
            ],
        },
    )
    assert rectified.status_code == 200
    body = rectified.json()
    assert body["version"] == 3
    corrected = next(
        reading for reading in body["packet"]["readings"] if reading["id"] == WIDTH_READING_ID
    )
    assert corrected["value_si"] == str(WIDTH_M)
    assert corrected["decision"]["rectifies_decision_id"] == wrong_decision_id
    scene = body["scene"]
    assert scene["version"] == 2
    assert scene["approved"] is False
    assert body["blockers"] == []
    assert _line_entity_id(scene, (float(WIDTH_M), 0.0), (0.0, 0.0))

    # 4. Aprovação e exportação seguem o caminho normal sobre a cena corrigida.
    approved = client.post(
        f"/v1/jobs/{job_id}/approve",
        headers=_headers("rectify-approve"),
        json={
            "revision_id": scene["id"],
            "accepted_approximations": [],
            "source_evidence_checked": True,
            "geometry_checked": True,
            "limitations_acknowledged": True,
            "statement": "Cena conferida depois da correção da cota de largura.",
        },
    )
    assert approved.status_code == 200
    export = client.post(
        f"/v1/jobs/{job_id}/exports",
        headers=_headers("rectify-export"),
        json={"revision_id": approved.json()["id"]},
    )
    assert export.status_code == 202
    assert worker.run_once() == 1
    completed = client.get(
        f"/v1/jobs/{job_id}/exports/{export.json()['export_id']}",
        headers=_headers("rectify-export-read"),
    )
    assert completed.json()["status"] == "COMPLETED"
    assert completed.json()["audit_status"] == "approved"
    assert queue.commands() == ["process_upload", "export_scene_package"]

    # 5. A decisão errada continua consultável na revisão em que foi tomada.
    review = client.get(f"/v1/jobs/{job_id}/review", headers=_headers("rectify-review"))
    assert review.json()["version"] == 3
    assert review.json()["packet"]["readings"][0]["decision"]["decision_id"] != wrong_decision_id


def test_com_o_modo_automatico_local_so_a_excecao_exige_uma_pessoa(
    tmp_path: Path,
    stack: tuple[TestClient, LocalQueueWorker, FakeObjectStore, FakeQueue],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cadeia inteira com a dupla chave do ADR-0041 ligada, como no stack local.

    As cotas acima do corte entram com autoria de máquina; a de associação ambígua segue
    exigindo gente. O portão não muda: sem aprovação humana da cena não há pacote, e o
    pacote publicado nomeia cada cota que entrou sem toque humano.
    """
    monkeypatch.setenv("CROQUITO_AUTO_ASSOCIATION_ENABLED", "true")
    monkeypatch.setenv("CROQUITO_AUTO_ASSOCIATION_THRESHOLD", "0.6")
    client, worker, storage, queue = stack
    pdf = synthetic_pdf()
    source_sha256 = hashlib.sha256(pdf).hexdigest()

    presign = client.post(
        "/v1/uploads/presign",
        headers=_headers("auto-presign"),
        json={
            "filename": "levantamento.pdf",
            "content_type": "application/pdf",
            "size_bytes": len(pdf),
            "sha256": source_sha256,
        },
    )
    storage.put_direct(object_key=presign.json()["object_key"], body=pdf)
    created = client.post(
        "/v1/jobs",
        headers=_headers("auto-job"),
        json={
            "upload_id": presign.json()["upload_id"],
            "project_name": "Auto-associação local",
            "default_unit": "m",
        },
    )
    assert created.status_code == 201
    job_id = created.json()["job_id"]
    assert worker.run_once() == 1

    bundle = write_seed_bundle(
        tmp_path / "auto-bundle",
        source_sha256=source_sha256,
        association_confidences={
            WIDTH_READING_ID: 0.9,
            HEIGHT_READING_ID: 0.9,
            # Ambígua: a cota é legível, mas não se sabe a qual segmento pertence.
            CIRCLE_READING_ID: 0.4,
        },
    )
    seeded = seed_review(
        SeedInputs(
            job_id=UUID(job_id),
            tenant_id=TENANT,
            packet_path=bundle["packet"],
            associations_path=bundle["associations"],
            proposals_path=bundle["proposals"],
            rectangle_request_path=bundle["rectangle_request"],
            manifest_path=bundle["manifest"],
            image_path=bundle["image"],
            required_criteria=(),
            operator_id="tenant-admin-e2e",
        ),
        LocalWorkerSettings(
            database_url=f"sqlite+pysqlite:///{tmp_path / 'e2e.db'}",
            queue_url="",
            aws_region="sa-east-1",
            aws_endpoint_url="http://localhost:4566",
            artifact_bucket="croquito-e2e",
        ),
        s3_client=storage,
    )
    assert set(seeded.auto_decided_reading_ids) == {WIDTH_READING_ID, HEIGHT_READING_ID}

    review = client.get(f"/v1/jobs/{job_id}/review", headers=_headers("auto-read"))
    assert review.status_code == 200
    readings = {reading["id"]: reading for reading in review.json()["packet"]["readings"]}
    assert readings[WIDTH_READING_ID]["decision"]["actor"] == "system"
    assert readings[HEIGHT_READING_ID]["decision"]["actor"] == "system"
    assert readings[CIRCLE_READING_ID]["decision"] is None
    # A revisão só cobra da pessoa o que a máquina não resolveu.
    assert review.json()["blockers"] == [
        f"CENTRE_CIRCLE_HUMAN_CONFIRMATION_REQUIRED:{CIRCLE_READING_ID}",
        f"EXPLICIT_ASSOCIATION_REQUIRED:{CIRCLE_READING_ID}",
    ]

    solved = client.post(
        f"/v1/jobs/{job_id}/review/decisions",
        headers=_headers("auto-decisions"),
        json={
            "base_version": 1,
            "decisions": [
                {
                    "reading_id": CIRCLE_READING_ID,
                    "action": "confirm",
                    "justification": "Diâmetro conferido na evidência protegida.",
                    "association_proposal_id": CIRCLE_PROPOSAL_ID,
                }
            ],
        },
    )
    assert solved.status_code == 200
    assert solved.json()["blockers"] == []
    scene = solved.json()["scene"]
    assert scene["version"] == 1

    approved = client.post(
        f"/v1/jobs/{job_id}/approve",
        headers=_headers("auto-approve"),
        json={
            "revision_id": scene["id"],
            "accepted_approximations": [],
            "source_evidence_checked": True,
            "geometry_checked": True,
            "limitations_acknowledged": True,
            "statement": "Cena conferida, inclusive as cotas que entraram automaticamente.",
        },
    )
    assert approved.status_code == 200
    export = client.post(
        f"/v1/jobs/{job_id}/exports",
        headers=_headers("auto-export"),
        json={"revision_id": approved.json()["id"]},
    )
    assert export.status_code == 202
    export_id = export.json()["export_id"]
    assert worker.run_once() == 1
    completed = client.get(
        f"/v1/jobs/{job_id}/exports/{export_id}", headers=_headers("auto-export-read")
    )
    assert completed.json()["status"] == "COMPLETED"
    assert completed.json()["audit_status"] == "approved"
    assert queue.commands() == ["process_upload", "export_scene_package"]

    package_key = f"tenants/{TENANT}/jobs/{job_id}/exports/{export_id}/croquito.zip"
    with zipfile.ZipFile(BytesIO(storage.body(package_key))) as package:
        audit = json.loads(package.read("auditoria.json"))
    assert audit["status"] == "approved"
    automatic = {item["reading_id"]: item for item in audit["auto_decided_readings"]}
    assert set(automatic) == {WIDTH_READING_ID, HEIGHT_READING_ID}
    assert automatic[WIDTH_READING_ID]["value_si"] == WIDTH_M
    assert automatic[WIDTH_READING_ID]["unit"] == "m"
    assert automatic[WIDTH_READING_ID]["proposal_id"] == WIDTH_PROPOSAL_ID
    assert automatic[WIDTH_READING_ID]["reading_confidence"] == 0.65
    assert automatic[WIDTH_READING_ID]["association_confidence"] == 0.9
    assert automatic[WIDTH_READING_ID]["threshold"] == 0.6
    assert automatic[WIDTH_READING_ID]["score_version"] == CONFIDENCE_SCORE_VERSION
    # A cota que a pessoa decidiu não aparece na lista das automáticas.
    assert CIRCLE_READING_ID not in automatic


def test_a_elevacao_entra_como_anotacao_automatica_e_o_pacote_a_nomeia(
    tmp_path: Path,
    stack: tuple[TestClient, LocalQueueWorker, FakeObjectStore, FakeQueue],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Os dois tiers na mesma cadeia, até o ZIP (ADR-0044).

    As cotas de planta entram pela dupla testemunha; a elevação `h=3,80`, que o OCR não
    encontrou, entra pela testemunha única que tem — e o pacote publicado diz, cota a
    cota, por qual regra cada uma entrou.
    """
    monkeypatch.setenv("CROQUITO_AUTO_ASSOCIATION_ENABLED", "true")
    monkeypatch.setenv("CROQUITO_AUTO_ASSOCIATION_THRESHOLD", "0.6")
    client, worker, storage, _queue = stack
    pdf = synthetic_pdf()
    source_sha256 = hashlib.sha256(pdf).hexdigest()

    presign = client.post(
        "/v1/uploads/presign",
        headers=_headers("anotacao-presign"),
        json={
            "filename": "levantamento.pdf",
            "content_type": "application/pdf",
            "size_bytes": len(pdf),
            "sha256": source_sha256,
        },
    )
    storage.put_direct(object_key=presign.json()["object_key"], body=pdf)
    created = client.post(
        "/v1/jobs",
        headers=_headers("anotacao-job"),
        json={
            "upload_id": presign.json()["upload_id"],
            "project_name": "Elevação automática",
            "default_unit": "m",
        },
    )
    job_id = created.json()["job_id"]
    assert worker.run_once() == 1

    bundle = write_seed_bundle(
        tmp_path / "anotacao-bundle",
        source_sha256=source_sha256,
        elevation=True,
        association_confidences={
            WIDTH_READING_ID: 0.9,
            HEIGHT_READING_ID: 0.9,
            CIRCLE_READING_ID: 0.4,
            ELEVATION_READING_ID: 0.9,
        },
    )
    seeded = seed_review(
        SeedInputs(
            job_id=UUID(job_id),
            tenant_id=TENANT,
            packet_path=bundle["packet"],
            associations_path=bundle["associations"],
            proposals_path=bundle["proposals"],
            rectangle_request_path=bundle["rectangle_request"],
            manifest_path=bundle["manifest"],
            image_path=bundle["image"],
            required_criteria=(),
            operator_id="tenant-admin-e2e",
        ),
        LocalWorkerSettings(
            database_url=f"sqlite+pysqlite:///{tmp_path / 'e2e.db'}",
            queue_url="",
            aws_region="sa-east-1",
            aws_endpoint_url="http://localhost:4566",
            artifact_bucket="croquito-e2e",
        ),
        s3_client=storage,
    )
    assert set(seeded.auto_decided_reading_ids) == {
        WIDTH_READING_ID,
        HEIGHT_READING_ID,
        ELEVATION_READING_ID,
    }

    review = client.get(f"/v1/jobs/{job_id}/review", headers=_headers("anotacao-read"))
    readings = {reading["id"]: reading for reading in review.json()["packet"]["readings"]}
    assert readings[WIDTH_READING_ID]["decision"]["auto_tier"] == "cota"
    assert readings[ELEVATION_READING_ID]["decision"]["auto_tier"] == "anotacao"
    # A anotação automática tem a MESMA forma da anotação declarada por uma pessoa:
    # confirmada e ausente do mapa de associações. Só o ator e o tier a distinguem.
    assert readings[ELEVATION_READING_ID]["status"] == "confirmed"
    assert ELEVATION_READING_ID not in review.json()["selected_associations"]
    assert review.json()["selected_associations"] == {
        WIDTH_READING_ID: WIDTH_PROPOSAL_ID,
        HEIGHT_READING_ID: HEIGHT_PROPOSAL_ID,
    }
    # A cota de associação ambígua continua sendo a única a exigir uma pessoa.
    assert readings[CIRCLE_READING_ID]["decision"] is None

    solved = client.post(
        f"/v1/jobs/{job_id}/review/decisions",
        headers=_headers("anotacao-decisions"),
        json={
            "base_version": 1,
            "decisions": [
                {
                    "reading_id": CIRCLE_READING_ID,
                    "action": "confirm",
                    "justification": "Diâmetro conferido na evidência protegida.",
                    "association_proposal_id": CIRCLE_PROPOSAL_ID,
                }
            ],
        },
    )
    assert solved.status_code == 200
    assert solved.json()["blockers"] == []
    approved = client.post(
        f"/v1/jobs/{job_id}/approve",
        headers=_headers("anotacao-approve"),
        json={
            "revision_id": solved.json()["scene"]["id"],
            "accepted_approximations": [],
            "source_evidence_checked": True,
            "geometry_checked": True,
            "limitations_acknowledged": True,
            "statement": "Cena conferida, com a elevação anotada pelo sistema à vista.",
        },
    )
    assert approved.status_code == 200
    export = client.post(
        f"/v1/jobs/{job_id}/exports",
        headers=_headers("anotacao-export"),
        json={"revision_id": approved.json()["id"]},
    )
    export_id = export.json()["export_id"]
    assert worker.run_once() == 1

    package_key = f"tenants/{TENANT}/jobs/{job_id}/exports/{export_id}/croquito.zip"
    with zipfile.ZipFile(BytesIO(storage.body(package_key))) as package:
        audit = json.loads(package.read("auditoria.json"))
    tiers = {item["reading_id"]: item["tier"] for item in audit["auto_decided_readings"]}
    assert tiers == {
        WIDTH_READING_ID: "cota",
        HEIGHT_READING_ID: "cota",
        ELEVATION_READING_ID: "anotacao",
    }
    anotacao = next(
        item
        for item in audit["auto_decided_readings"]
        if item["reading_id"] == ELEVATION_READING_ID
    )
    assert anotacao["raw_text"] == "h=3,80"
    assert anotacao["value_si"] == ELEVATION_M
    # Sem vínculo no pacote publicado, e o elemento provável nomeado como observação.
    assert anotacao["proposal_id"] is None
    assert anotacao["probable_proposal_id"] == ELEVATION_PROPOSAL_ID
    # A confiança de leitura que NÃO foi exigida fica registrada do mesmo jeito.
    assert anotacao["reading_confidence"] == 0.45
    assert anotacao["association_confidence"] == 0.9
    # A cota de planta, essa sim, tem o vínculo gravado.
    cota = next(
        item for item in audit["auto_decided_readings"] if item["reading_id"] == WIDTH_READING_ID
    )
    assert cota["proposal_id"] == WIDTH_PROPOSAL_ID
    assert cota["probable_proposal_id"] is None


def test_uma_auto_decisao_retificada_sai_da_lista_de_cotas_automaticas(
    tmp_path: Path,
    stack: tuple[TestClient, LocalQueueWorker, FakeObjectStore, FakeQueue],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Corrigida por gente, a cota deixa de ser automática — e a auditoria acompanha."""
    monkeypatch.setenv("CROQUITO_AUTO_ASSOCIATION_ENABLED", "true")
    monkeypatch.setenv("CROQUITO_AUTO_ASSOCIATION_THRESHOLD", "0.6")
    client, worker, storage, _queue = stack
    pdf = synthetic_pdf()
    source_sha256 = hashlib.sha256(pdf).hexdigest()

    presign = client.post(
        "/v1/uploads/presign",
        headers=_headers("auto-rectify-presign"),
        json={
            "filename": "levantamento.pdf",
            "content_type": "application/pdf",
            "size_bytes": len(pdf),
            "sha256": source_sha256,
        },
    )
    storage.put_direct(object_key=presign.json()["object_key"], body=pdf)
    created = client.post(
        "/v1/jobs",
        headers=_headers("auto-rectify-job"),
        json={
            "upload_id": presign.json()["upload_id"],
            "project_name": "Correção de auto-decisão",
            "default_unit": "m",
        },
    )
    job_id = created.json()["job_id"]
    assert worker.run_once() == 1
    bundle = write_seed_bundle(
        tmp_path / "auto-rectify-bundle",
        source_sha256=source_sha256,
        association_confidences={
            WIDTH_READING_ID: 0.9,
            HEIGHT_READING_ID: 0.9,
            CIRCLE_READING_ID: 0.9,
        },
    )
    seed_review(
        SeedInputs(
            job_id=UUID(job_id),
            tenant_id=TENANT,
            packet_path=bundle["packet"],
            associations_path=bundle["associations"],
            proposals_path=bundle["proposals"],
            rectangle_request_path=bundle["rectangle_request"],
            manifest_path=bundle["manifest"],
            image_path=bundle["image"],
            required_criteria=(),
            operator_id="tenant-admin-e2e",
        ),
        LocalWorkerSettings(
            database_url=f"sqlite+pysqlite:///{tmp_path / 'e2e.db'}",
            queue_url="",
            aws_region="sa-east-1",
            aws_endpoint_url="http://localhost:4566",
            artifact_bucket="croquito-e2e",
        ),
        s3_client=storage,
    )

    review = client.get(f"/v1/jobs/{job_id}/review", headers=_headers("auto-rectify-read"))
    automatic_decision_id = next(
        reading["decision"]["decision_id"]
        for reading in review.json()["packet"]["readings"]
        if reading["id"] == WIDTH_READING_ID
    )
    rectified = client.post(
        f"/v1/jobs/{job_id}/review/rectifications",
        headers=_headers("auto-rectify-command"),
        json={
            "base_version": 1,
            "rectifications": [
                {
                    "reading_id": WIDTH_READING_ID,
                    "action": "confirm",
                    "rectifies_decision_id": automatic_decision_id,
                    "justification": "A automática confirmou 25,90; na folha a largura é 26,10.",
                    "association_proposal_id": WIDTH_PROPOSAL_ID,
                    "raw_text": "26,10",
                    "value_si": "26.10",
                    "unit": "m",
                }
            ],
        },
    )
    assert rectified.status_code == 200
    corrected = next(
        reading
        for reading in rectified.json()["packet"]["readings"]
        if reading["id"] == WIDTH_READING_ID
    )
    assert corrected["decision"]["actor"] == "human"
    scene = rectified.json()["scene"]
    assert rectified.json()["blockers"] == []

    approved = client.post(
        f"/v1/jobs/{job_id}/approve",
        headers=_headers("auto-rectify-approve"),
        json={
            "revision_id": scene["id"],
            "accepted_approximations": [],
            "source_evidence_checked": True,
            "geometry_checked": True,
            "limitations_acknowledged": True,
            "statement": "Cena conferida depois da correção humana da cota automática.",
        },
    )
    assert approved.status_code == 200
    export = client.post(
        f"/v1/jobs/{job_id}/exports",
        headers=_headers("auto-rectify-export"),
        json={"revision_id": approved.json()["id"]},
    )
    assert export.status_code == 202
    export_id = export.json()["export_id"]
    assert worker.run_once() == 1

    package_key = f"tenants/{TENANT}/jobs/{job_id}/exports/{export_id}/croquito.zip"
    with zipfile.ZipFile(BytesIO(storage.body(package_key))) as package:
        audit = json.loads(package.read("auditoria.json"))
    automatic = {item["reading_id"] for item in audit["auto_decided_readings"]}
    assert WIDTH_READING_ID not in automatic
    assert automatic == {HEIGHT_READING_ID, CIRCLE_READING_ID}


def test_uma_anotacao_automatica_nunca_vira_restricao_no_tracado(
    tmp_path: Path,
    stack: tuple[TestClient, LocalQueueWorker, FakeObjectStore, FakeQueue],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A garantia central da emenda 1a do ADR-0044, medida no solve de verdade.

    O traçado só conhece uma leitura por dois canais: `confirmed_associations`, que vira
    restrição métrica, e as notas declaradas no aceite, que viram texto preso ao elemento.
    A anotação automática não entra em nenhum dos dois — ela fica inerte até uma pessoa
    decidir onde prender o texto. Se um dia ela passar a gravar associação, este teste
    quebra na hora: a elevação apareceria como vão aplicado no eixo Y.
    """
    monkeypatch.setenv("CROQUITO_AUTO_ASSOCIATION_ENABLED", "true")
    monkeypatch.setenv("CROQUITO_AUTO_ASSOCIATION_THRESHOLD", "0.6")
    client, worker, storage, _queue = stack
    pdf = synthetic_pdf()
    source_sha256 = hashlib.sha256(pdf).hexdigest()

    presign = client.post(
        "/v1/uploads/presign",
        headers=_headers("inerte-presign"),
        json={
            "filename": "levantamento.pdf",
            "content_type": "application/pdf",
            "size_bytes": len(pdf),
            "sha256": source_sha256,
        },
    )
    storage.put_direct(object_key=presign.json()["object_key"], body=pdf)
    created = client.post(
        "/v1/jobs",
        headers=_headers("inerte-job"),
        json={
            "upload_id": presign.json()["upload_id"],
            "project_name": "Anotação inerte no traçado",
            "default_unit": "m",
        },
    )
    job_id = created.json()["job_id"]
    assert worker.run_once() == 1
    bundle = write_seed_bundle(
        tmp_path / "inerte-bundle",
        source_sha256=source_sha256,
        elevation=True,
        association_confidences={
            WIDTH_READING_ID: 0.9,
            HEIGHT_READING_ID: 0.9,
            CIRCLE_READING_ID: 0.9,
            ELEVATION_READING_ID: 0.9,
        },
    )
    seed_review(
        SeedInputs(
            job_id=UUID(job_id),
            tenant_id=TENANT,
            packet_path=bundle["packet"],
            associations_path=bundle["associations"],
            proposals_path=bundle["proposals"],
            rectangle_request_path=bundle["rectangle_request"],
            manifest_path=bundle["manifest"],
            image_path=bundle["image"],
            required_criteria=(),
            operator_id="tenant-admin-e2e",
        ),
        LocalWorkerSettings(
            database_url=f"sqlite+pysqlite:///{tmp_path / 'e2e.db'}",
            queue_url="",
            aws_region="sa-east-1",
            aws_endpoint_url="http://localhost:4566",
            artifact_bucket="croquito-e2e",
        ),
        s3_client=storage,
    )

    review = client.get(f"/v1/jobs/{job_id}/review", headers=_headers("inerte-read"))
    assert review.status_code == 200
    body = review.json()
    readings = {reading["id"]: reading for reading in body["packet"]["readings"]}
    assert readings[ELEVATION_READING_ID]["decision"]["auto_tier"] == "anotacao"
    assert ELEVATION_READING_ID not in body["selected_associations"]

    requested = client.post(
        f"/v1/jobs/{job_id}/trace-solves",
        headers=_headers("inerte-accept"),
        json={
            # Sem cena ainda: o traçado é a primeira geometria métrica deste job.
            "base_review_version": body["version"],
            "proposal_ids": [
                WIDTH_PROPOSAL_ID,
                HEIGHT_PROPOSAL_ID,
                CIRCLE_PROPOSAL_ID,
                ELEVATION_PROPOSAL_ID,
            ],
            "unlabelled_proposal_ids": [CIRCLE_PROPOSAL_ID, ELEVATION_PROPOSAL_ID],
            "note": "Traçado aceito em lote pelo profissional identificado.",
            "title": "CAMPO SINTETICO",
        },
    )
    assert requested.status_code == 202
    assert worker.run_once() == 1

    polled = client.get(
        f"/v1/jobs/{job_id}/trace-solves/{requested.json()['trace_solve_id']}",
        headers=_headers("inerte-poll"),
    )
    assert polled.status_code == 200
    solve = polled.json()
    assert solve["status"] == "COMPLETED"
    # As cotas de planta viraram vãos; a elevação não virou nada.
    anchored = {report["reading_id"] for report in solve["applied_spans"]}
    assert WIDTH_READING_ID in anchored
    assert ELEVATION_READING_ID not in anchored
    assert ELEVATION_READING_ID not in solve["unapplied_reading_ids"]
    assert ELEVATION_READING_ID not in {report["reading_id"] for report in solve["contested_spans"]}
    assert not [blocker for blocker in solve["blockers"] if ELEVATION_READING_ID in blocker]
    # E a cena resultante não carrega proveniência da decisão da elevação em entidade
    # nenhuma: ela não participou de geometria.
    scene = client.get(f"/v1/jobs/{job_id}/scene", headers=_headers("inerte-scene")).json()
    elevation_decision_id = readings[ELEVATION_READING_ID]["decision"]["decision_id"]
    for entity in scene["entities"]:
        provenance = entity.get("provenance") or {}
        assert ELEVATION_READING_ID not in provenance.get("source_ids", [])
        assert elevation_decision_id not in provenance.get("source_ids", [])


def test_trace_solve_reaches_a_metric_scene_through_the_queue(
    tmp_path: Path,
    stack: tuple[TestClient, LocalQueueWorker, FakeObjectStore, FakeQueue],
) -> None:
    """Aceite em lote postado na sessão autenticada, resolvido pelo worker, cena consultável."""
    client, worker, storage, queue = stack
    pdf = synthetic_pdf()
    source_sha256 = hashlib.sha256(pdf).hexdigest()

    presign = client.post(
        "/v1/uploads/presign",
        headers=_headers("trace-presign"),
        json={
            "filename": "levantamento.pdf",
            "content_type": "application/pdf",
            "size_bytes": len(pdf),
            "sha256": source_sha256,
        },
    )
    storage.put_direct(object_key=presign.json()["object_key"], body=pdf)
    created = client.post(
        "/v1/jobs",
        headers=_headers("trace-job"),
        json={
            "upload_id": presign.json()["upload_id"],
            "project_name": "Traçado sintético",
            "default_unit": "m",
        },
    )
    assert created.status_code == 201
    job_id = created.json()["job_id"]
    assert worker.run_once() == 1

    bundle = write_seed_bundle(tmp_path / "trace-bundle", source_sha256=source_sha256)
    seed_review(
        SeedInputs(
            job_id=UUID(job_id),
            tenant_id=TENANT,
            packet_path=bundle["packet"],
            associations_path=bundle["associations"],
            proposals_path=bundle["proposals"],
            rectangle_request_path=bundle["rectangle_request"],
            manifest_path=bundle["manifest"],
            image_path=bundle["image"],
            required_criteria=(),
            operator_id="tenant-admin-e2e",
        ),
        LocalWorkerSettings(
            database_url=f"sqlite+pysqlite:///{tmp_path / 'e2e.db'}",
            queue_url="",
            aws_region="sa-east-1",
            aws_endpoint_url="http://localhost:4566",
            artifact_bucket="croquito-e2e",
        ),
        s3_client=storage,
    )

    # Decisão humana com associação explícita: sem ela o traçado não vira cena.
    solved = client.post(
        f"/v1/jobs/{job_id}/review/decisions",
        headers=_headers("trace-decisions"),
        json={
            "base_version": 1,
            "decisions": [
                {
                    "reading_id": WIDTH_READING_ID,
                    "action": "confirm",
                    "justification": "Cota conferida na evidência protegida.",
                    "association_proposal_id": WIDTH_PROPOSAL_ID,
                },
                {
                    "reading_id": HEIGHT_READING_ID,
                    "action": "confirm",
                    "justification": "Cota conferida na evidência protegida.",
                    "association_proposal_id": HEIGHT_PROPOSAL_ID,
                },
                {
                    "reading_id": CIRCLE_READING_ID,
                    "action": "confirm",
                    "justification": "Diâmetro conferido na evidência protegida.",
                    "association_proposal_id": CIRCLE_PROPOSAL_ID,
                },
            ],
        },
    )
    assert solved.status_code == 200
    assert solved.json()["scene"]["version"] == 1

    # A API apenas valida e enfileira o aceite em lote.
    requested = client.post(
        f"/v1/jobs/{job_id}/trace-solves",
        headers=_headers("trace-accept"),
        json={
            "base_review_version": solved.json()["version"],
            "base_scene_version": solved.json()["scene"]["version"],
            "proposal_ids": [WIDTH_PROPOSAL_ID, HEIGHT_PROPOSAL_ID, CIRCLE_PROPOSAL_ID],
            "unlabelled_proposal_ids": [CIRCLE_PROPOSAL_ID],
            "note": "Traçado aceito em lote pelo profissional identificado.",
            "title": "CAMPO SINTETICO",
        },
    )
    assert requested.status_code == 202
    assert requested.json()["status"] == "QUEUED"
    trace_solve_id = requested.json()["trace_solve_id"]

    assert worker.run_once() == 1
    assert queue.commands() == ["process_upload", "solve_trace_scene"]

    polled = client.get(
        f"/v1/jobs/{job_id}/trace-solves/{trace_solve_id}", headers=_headers("trace-poll")
    )
    assert polled.status_code == 200
    body = polled.json()
    assert body["status"] == "COMPLETED"
    assert body["solve_status"] == "solved_unapproved"
    assert body["blockers"] == []
    # As duas linhas e o círculo: a cota de diâmetro confirmada determina o círculo, que
    # sai exato como as linhas cotadas — nada permanece aproximado neste lote.
    assert body["exact_entity_count"] == 3
    assert body["approximate_entity_count"] == 0
    assert body["scale_m_per_px"] > 0
    assert body["unapplied_reading_ids"] == []
    # O diagnóstico do traçado atravessa worker → banco → API: nada aqui ficou por aplicar
    # nem em disputa, e cada cota confirmada diz de onde até onde ancorou, em metros.
    assert body["unapplied_readings"] == []
    assert body["contested_spans"] == []
    ancoras = {report["reading_id"]: report for report in body["applied_spans"]}
    assert set(ancoras) == {WIDTH_READING_ID, HEIGHT_READING_ID}
    for report in ancoras.values():
        assert report["gap"] is False
        assert report["second_proposal_id"] is None
        # Números, não texto: `value_m` chega como número mesmo tendo nascido `Decimal`.
        assert isinstance(report["value_m"], float)
        assert report["end_m"] - report["start_m"] > 0
    assert ancoras[WIDTH_READING_ID]["axis"] == "x"
    assert ancoras[HEIGHT_READING_ID]["axis"] == "y"
    assert body["result_scene_version"] == 2
    assert body["result_review_version"] == 3

    scene = client.get(f"/v1/jobs/{job_id}/scene", headers=_headers("trace-scene"))
    assert scene.status_code == 200
    assert scene.json()["id"] == body["result_scene_revision_id"]
    assert scene.json()["version"] == 2
    assert scene.json()["approved"] is False
    entities = scene.json()["entities"]
    precisions = {entity["precision"] for entity in entities}
    # Precisão declarada por entidade: cota confirmada é exata; carimbo e rótulos, derivados.
    assert "exact" in precisions
    assert "derived" in precisions
    circle = next(entity for entity in entities if entity["kind"] == "circle")
    assert circle["precision"] == "exact"
    # A cota de diâmetro confirmada vira cota diametral desenhada, não nota presa.
    diameter_dimension = next(
        entity for entity in entities if entity["kind"] == "diameter_dimension"
    )
    assert CIRCLE_READING_ID in diameter_dimension["provenance"]["source_ids"]

    review = client.get(f"/v1/jobs/{job_id}/review", headers=_headers("trace-review"))
    assert review.status_code == 200
    assert review.json()["version"] == 3
    assert review.json()["scene"]["id"] == body["result_scene_revision_id"]


def test_element_identity_declared_on_the_review_travels_through_the_trace(
    tmp_path: Path,
    stack: tuple[TestClient, LocalQueueWorker, FakeObjectStore, FakeQueue],
) -> None:
    """Round-trip da identidade (F-051 T5, ADR-0063 decisão 2), pelo caminho de produção.

    Declara "B" sobre duas propostas NA REVISÃO → traçado pela fila → a cena nasce com o
    `element_ref` e o rótulo → o ato de identidade NA CENA cunha o ref seguinte do MESMO
    contador → o re-solve preserva o transporte. É o teste que o risco do contrato pede:
    duas identidades divergindo (a da revisão e a da cena) só aparece com o ciclo inteiro.
    """
    client, worker, storage, _queue = stack
    pdf = synthetic_pdf()
    source_sha256 = hashlib.sha256(pdf).hexdigest()

    presign = client.post(
        "/v1/uploads/presign",
        headers=_headers("identidade-presign"),
        json={
            "filename": "levantamento.pdf",
            "content_type": "application/pdf",
            "size_bytes": len(pdf),
            "sha256": source_sha256,
        },
    )
    storage.put_direct(object_key=presign.json()["object_key"], body=pdf)
    created = client.post(
        "/v1/jobs",
        headers=_headers("identidade-job"),
        json={
            "upload_id": presign.json()["upload_id"],
            "project_name": "Identidade declarada na revisão",
            "default_unit": "m",
        },
    )
    job_id = created.json()["job_id"]
    assert worker.run_once() == 1

    bundle = write_seed_bundle(tmp_path / "identidade-bundle", source_sha256=source_sha256)
    seed_review(
        SeedInputs(
            job_id=UUID(job_id),
            tenant_id=TENANT,
            packet_path=bundle["packet"],
            associations_path=bundle["associations"],
            proposals_path=bundle["proposals"],
            rectangle_request_path=bundle["rectangle_request"],
            manifest_path=bundle["manifest"],
            image_path=bundle["image"],
            required_criteria=(),
            operator_id="tenant-admin-e2e",
        ),
        LocalWorkerSettings(
            database_url=f"sqlite+pysqlite:///{tmp_path / 'e2e.db'}",
            queue_url="",
            aws_region="sa-east-1",
            aws_endpoint_url="http://localhost:4566",
            artifact_bucket="croquito-e2e",
        ),
        s3_client=storage,
    )

    decided = client.post(
        f"/v1/jobs/{job_id}/review/decisions",
        headers=_headers("identidade-decisions"),
        json={
            "base_version": 1,
            "decisions": [
                {
                    "reading_id": WIDTH_READING_ID,
                    "action": "confirm",
                    "justification": "Cota conferida na evidência protegida.",
                    "association_proposal_id": WIDTH_PROPOSAL_ID,
                },
                {
                    "reading_id": HEIGHT_READING_ID,
                    "action": "confirm",
                    "justification": "Cota conferida na evidência protegida.",
                    "association_proposal_id": HEIGHT_PROPOSAL_ID,
                },
                {
                    "reading_id": CIRCLE_READING_ID,
                    "action": "confirm",
                    "justification": "Diâmetro conferido na evidência protegida.",
                    "association_proposal_id": CIRCLE_PROPOSAL_ID,
                },
            ],
        },
    )
    assert decided.status_code == 200

    # O ato humano da revisão: estas DUAS propostas são o elemento "B". O ref é cunhado pelo
    # servidor; o cliente nunca o escolhe.
    declared = client.post(
        f"/v1/jobs/{job_id}/review/elements",
        headers=_headers("identidade-declare"),
        json={
            "base_version": decided.json()["version"],
            "proposal_ids": [WIDTH_PROPOSAL_ID, HEIGHT_PROPOSAL_ID],
            "label": "B",
            "reason": "As duas linhas cotadas são o mesmo alambrado do balão B.",
        },
    )
    assert declared.status_code == 200, declared.json()
    assert declared.json()["element_ref"] == "EL-001"
    review_version = declared.json()["review_version"]

    requested = client.post(
        f"/v1/jobs/{job_id}/trace-solves",
        headers=_headers("identidade-accept"),
        json={
            "base_review_version": review_version,
            "base_scene_version": decided.json()["scene"]["version"],
            "proposal_ids": [WIDTH_PROPOSAL_ID, HEIGHT_PROPOSAL_ID, CIRCLE_PROPOSAL_ID],
            "unlabelled_proposal_ids": [CIRCLE_PROPOSAL_ID],
            "note": "Traçado aceito em lote pelo profissional identificado.",
            "title": "CAMPO SINTETICO",
        },
    )
    assert requested.status_code == 202
    assert worker.run_once() == 1
    solved = client.get(
        f"/v1/jobs/{job_id}/trace-solves/{requested.json()['trace_solve_id']}",
        headers=_headers("identidade-poll"),
    ).json()
    assert solved["status"] == "COMPLETED"
    assert solved["solve_status"] == "solved_unapproved", solved["blockers"]

    # A cena nasce com a identidade: as duas linhas carregam o ref, e o nome legível mora
    # uma vez só, por ref. Ninguém redigitou nada depois do solver.
    scene = client.get(f"/v1/jobs/{job_id}/scene", headers=_headers("identidade-scene")).json()
    refs = {
        entity["id"]: entity["element_ref"]
        for entity in scene["entities"]
        if entity["element_ref"] is not None
    }
    assert len(refs) == 2
    assert set(refs.values()) == {"EL-001"}
    assert scene["element_labels"] == {"EL-001": "B"}
    circle_entity = next(entity for entity in scene["entities"] if entity["kind"] == "circle")
    assert circle_entity["element_ref"] is None

    # O contador é UM por job: o ato pós-cena continua valendo para o que a revisão não
    # identificou, e cunha o PRÓXIMO ref — nunca reaproveita o transportado.
    scene_act = client.post(
        f"/v1/jobs/{job_id}/elements",
        headers=_headers("identidade-scene-act"),
        json={
            "base_version": scene["version"],
            "entity_ids": [circle_entity["id"]],
            "label": "C",
            "reason": "O círculo central é um elemento à parte, declarado sobre a cena.",
        },
    )
    assert scene_act.status_code == 200, scene_act.json()
    assert scene_act.json()["element_ref"] == "EL-002"
    assert scene_act.json()["scene"]["element_labels"] == {"EL-001": "B", "EL-002": "C"}

    # Re-solve sobre a mesma revisão de leitura: a identidade declarada na revisão viaja de
    # novo, sem novo ato humano.
    resolved = client.post(
        f"/v1/jobs/{job_id}/trace-solves",
        headers=_headers("identidade-resolve"),
        json={
            "base_review_version": client.get(
                f"/v1/jobs/{job_id}/review", headers=_headers("identidade-reread")
            ).json()["version"],
            "base_scene_version": scene_act.json()["scene"]["version"],
            "proposal_ids": [WIDTH_PROPOSAL_ID, HEIGHT_PROPOSAL_ID, CIRCLE_PROPOSAL_ID],
            "unlabelled_proposal_ids": [CIRCLE_PROPOSAL_ID],
            "note": "Traçado refeito depois do ato de identidade na cena.",
            "title": "CAMPO SINTETICO",
        },
    )
    assert resolved.status_code == 202
    assert worker.run_once() == 1
    reworked = client.get(
        f"/v1/jobs/{job_id}/trace-solves/{resolved.json()['trace_solve_id']}",
        headers=_headers("identidade-repoll"),
    ).json()
    assert reworked["solve_status"] == "solved_unapproved", reworked["blockers"]

    rescene = client.get(f"/v1/jobs/{job_id}/scene", headers=_headers("identidade-rescene")).json()
    assert rescene["element_labels"] == {"EL-001": "B"}
    assert {
        entity["element_ref"] for entity in rescene["entities"] if entity["element_ref"] is not None
    } == {"EL-001"}
    # O que foi declarado SOBRE A CENA não sobrevive a um re-solve — a cena é refeita das
    # propostas. É exatamente o limite que o ADR-0063 registra ao mover a identidade para a
    # revisão; o ref cunhado lá, porém, nunca volta ao estoque.
    assert "EL-002" not in rescene["element_labels"]
    terceiro = client.post(
        f"/v1/jobs/{job_id}/elements",
        headers=_headers("identidade-terceiro"),
        json={
            "base_version": rescene["version"],
            "entity_ids": [
                next(entity for entity in rescene["entities"] if entity["kind"] == "circle")["id"]
            ],
            "reason": "Cunhagem seguinte não reaproveita ref de elemento revogado nem refeito.",
        },
    )
    assert terceiro.status_code == 200, terceiro.json()
    assert terceiro.json()["element_ref"] == "EL-003"


def test_traced_scene_carries_the_scope_criterion_to_the_audited_package(
    tmp_path: Path,
    stack: tuple[TestClient, LocalQueueWorker, FakeObjectStore, FakeQueue],
) -> None:
    """Paridade do critério no traçado: sem declaração não exporta; coberto fecha o ZIP."""
    client, worker, storage, queue = stack
    pdf = synthetic_pdf()
    source_sha256 = hashlib.sha256(pdf).hexdigest()

    presign = client.post(
        "/v1/uploads/presign",
        headers=_headers("criterion-presign"),
        json={
            "filename": "levantamento.pdf",
            "content_type": "application/pdf",
            "size_bytes": len(pdf),
            "sha256": source_sha256,
        },
    )
    storage.put_direct(object_key=presign.json()["object_key"], body=pdf)
    created = client.post(
        "/v1/jobs",
        headers=_headers("criterion-job"),
        json={
            "upload_id": presign.json()["upload_id"],
            "project_name": "Traçado com critério",
            "default_unit": "m",
        },
    )
    assert created.status_code == 201
    job_id = created.json()["job_id"]
    assert worker.run_once() == 1

    bundle = write_seed_bundle(tmp_path / "criterion-bundle", source_sha256=source_sha256)
    seed_review(
        SeedInputs(
            job_id=UUID(job_id),
            tenant_id=TENANT,
            packet_path=bundle["packet"],
            associations_path=bundle["associations"],
            proposals_path=bundle["proposals"],
            rectangle_request_path=bundle["rectangle_request"],
            manifest_path=bundle["manifest"],
            image_path=bundle["image"],
            required_criteria=(ScopeCriterion(code=SCOPE_CRITERION, text=SCOPE_CRITERION_TEXT),),
            operator_id="tenant-admin-e2e",
        ),
        LocalWorkerSettings(
            database_url=f"sqlite+pysqlite:///{tmp_path / 'e2e.db'}",
            queue_url="",
            aws_region="sa-east-1",
            aws_endpoint_url="http://localhost:4566",
            artifact_bucket="croquito-e2e",
        ),
        s3_client=storage,
    )

    solved = client.post(
        f"/v1/jobs/{job_id}/review/decisions",
        headers=_headers("criterion-decisions"),
        json={
            "base_version": 1,
            "decisions": [
                {
                    "reading_id": WIDTH_READING_ID,
                    "action": "confirm",
                    "justification": "Cota conferida na evidência protegida.",
                    "association_proposal_id": WIDTH_PROPOSAL_ID,
                },
                {
                    "reading_id": HEIGHT_READING_ID,
                    "action": "confirm",
                    "justification": "Cota conferida na evidência protegida.",
                    "association_proposal_id": HEIGHT_PROPOSAL_ID,
                },
                {
                    "reading_id": CIRCLE_READING_ID,
                    "action": "confirm",
                    "justification": "Diâmetro conferido na evidência protegida.",
                    "association_proposal_id": CIRCLE_PROPOSAL_ID,
                },
            ],
        },
    )
    assert solved.status_code == 200

    requested = client.post(
        f"/v1/jobs/{job_id}/trace-solves",
        headers=_headers("criterion-accept"),
        json={
            "base_review_version": solved.json()["version"],
            "base_scene_version": solved.json()["scene"]["version"],
            "proposal_ids": [WIDTH_PROPOSAL_ID, HEIGHT_PROPOSAL_ID, CIRCLE_PROPOSAL_ID],
            "unlabelled_proposal_ids": [CIRCLE_PROPOSAL_ID],
            "note": "Traçado aceito em lote pelo profissional identificado.",
            "title": "CAMPO SINTETICO",
        },
    )
    assert requested.status_code == 202
    assert worker.run_once() == 1

    scene = client.get(f"/v1/jobs/{job_id}/scene", headers=_headers("criterion-scene"))
    assert scene.status_code == 200
    traced = scene.json()
    # A cena traçada nasce com a issue do critério, com o texto do caso.
    criterion_issue = next(issue for issue in traced["issues"] if issue["code"] == SCOPE_CRITERION)
    assert criterion_issue["severity"] == "critical"
    assert criterion_issue["status"] == "open"
    assert criterion_issue["message"] == SCOPE_CRITERION_TEXT

    approval = {
        "revision_id": traced["id"],
        "accepted_approximations": [
            entity["id"] for entity in traced["entities"] if entity["precision"] == "approximate"
        ],
        "source_evidence_checked": True,
        "geometry_checked": True,
        "limitations_acknowledged": True,
        "statement": "Traçado confere com a evidência e cobre o critério declarado no caso.",
    }
    refused = client.post(
        f"/v1/jobs/{job_id}/approve", headers=_headers("criterion-open"), json=approval
    )
    assert refused.status_code == 422
    assert f"OPEN_CRITICAL_ISSUE:{SCOPE_CRITERION}" in refused.json()["errors"]

    approved = client.post(
        f"/v1/jobs/{job_id}/approve",
        headers=_headers("criterion-approve"),
        json={**approval, "covered_criteria": [SCOPE_CRITERION]},
    )
    assert approved.status_code == 200
    assert (
        next(issue for issue in approved.json()["issues"] if issue["code"] == SCOPE_CRITERION)[
            "status"
        ]
        == "resolved"
    )

    export = client.post(
        f"/v1/jobs/{job_id}/exports",
        headers=_headers("criterion-export"),
        json={"revision_id": approved.json()["id"]},
    )
    assert export.status_code == 202
    assert worker.run_once() == 1
    export_id = export.json()["export_id"]
    completed = client.get(
        f"/v1/jobs/{job_id}/exports/{export_id}", headers=_headers("criterion-export-read")
    )
    assert completed.json()["status"] == "COMPLETED"
    assert completed.json()["audit_status"] == "approved"
    assert queue.commands() == [
        "process_upload",
        "solve_trace_scene",
        "export_scene_package",
    ]

    package_key = f"tenants/{TENANT}/jobs/{job_id}/exports/{export_id}/croquito.zip"
    with zipfile.ZipFile(BytesIO(storage.body(package_key))) as package:
        approval_record = json.loads(package.read("aprovacao.json"))
    assert approval_record["covered_criteria"] == [SCOPE_CRITERION]
    assert approval_record["acknowledged_criteria"] == []


# --- F-030 T8: evidência de campo na revisão coexiste com a exportação ---

SURVEY_E2E = "00000000-0000-7000-8000-0000000030aa"
#: Testemunhas com divergência pequena e NEUTRA sobre a mesma cota confirmada (25,90 m).
SURVEY_WITNESS_MM = 25_930  # +0,03 m
PHOTO_WITNESS_MM = 25_850  # -0,05 m
PHOTO_READING_ID = "fpr_evidence"


def _reach_exportable_scene(
    client: TestClient,
    worker: LocalQueueWorker,
    storage: FakeObjectStore,
    tmp_path: Path,
) -> tuple[str, str, str, str]:
    """Percorre upload → decisão → calibração → aceite até uma cena aprovável.

    Devolve `(job_id, review_endpoint, scene_draft_id, approximate_entity_id)`. A cota de
    largura fica confirmada, elegível a receber testemunhas.
    """
    pdf = synthetic_pdf()
    source_sha256 = hashlib.sha256(pdf).hexdigest()
    presign = client.post(
        "/v1/uploads/presign",
        headers=_headers("fe-presign"),
        json={
            "filename": "levantamento.pdf",
            "content_type": "application/pdf",
            "size_bytes": len(pdf),
            "sha256": source_sha256,
        },
    )
    storage.put_direct(object_key=presign.json()["object_key"], body=pdf)
    created = client.post(
        "/v1/jobs",
        headers=_headers("fe-job"),
        json={
            "upload_id": presign.json()["upload_id"],
            "project_name": "Caso sintético de campo",
            "default_unit": "m",
        },
    )
    job_id = created.json()["job_id"]
    assert worker.run_once() == 1
    review_endpoint = f"/v1/jobs/{job_id}/review"

    bundle = write_seed_bundle(tmp_path / "bundle", source_sha256=source_sha256)
    seed_review(
        SeedInputs(
            job_id=UUID(job_id),
            tenant_id=TENANT,
            packet_path=bundle["packet"],
            associations_path=bundle["associations"],
            proposals_path=bundle["proposals"],
            rectangle_request_path=bundle["rectangle_request"],
            manifest_path=bundle["manifest"],
            image_path=bundle["image"],
            required_criteria=(ScopeCriterion(code=SCOPE_CRITERION, text=SCOPE_CRITERION_TEXT),),
            operator_id="tenant-admin-fe",
        ),
        LocalWorkerSettings(
            database_url=f"sqlite+pysqlite:///{tmp_path / 'e2e.db'}",
            queue_url="",
            aws_region="sa-east-1",
            aws_endpoint_url="http://localhost:4566",
            artifact_bucket="croquito-e2e",
        ),
        s3_client=storage,
    )

    solved = client.post(
        f"{review_endpoint}/decisions",
        headers=_headers("fe-decisions"),
        json={
            "base_version": 1,
            "decisions": [
                {
                    "reading_id": WIDTH_READING_ID,
                    "action": "confirm",
                    "justification": "Cota conferida na evidência protegida.",
                    "association_proposal_id": WIDTH_PROPOSAL_ID,
                },
                {
                    "reading_id": HEIGHT_READING_ID,
                    "action": "confirm",
                    "justification": "Cota conferida na evidência protegida.",
                    "association_proposal_id": HEIGHT_PROPOSAL_ID,
                },
                {
                    "reading_id": CIRCLE_READING_ID,
                    "action": "confirm",
                    "justification": "Diâmetro conferido na evidência protegida.",
                    "association_proposal_id": CIRCLE_PROPOSAL_ID,
                },
            ],
        },
    )
    assert solved.status_code == 200
    scene = solved.json()["scene"]
    calibration = client.post(
        f"{review_endpoint}/calibration",
        headers=_headers("fe-calibration"),
        json={
            "base_review_version": 2,
            "base_scene_version": 1,
            "anchors": [
                {
                    "proposal_id": WIDTH_PROPOSAL_ID,
                    "entity_id": _line_entity_id(scene, (float(WIDTH_M), 0.0), (0.0, 0.0)),
                    "reversed": True,
                },
                {
                    "proposal_id": HEIGHT_PROPOSAL_ID,
                    "entity_id": _line_entity_id(scene, (0.0, 0.0), (0.0, float(HEIGHT_M))),
                },
            ],
        },
    )
    assert calibration.status_code == 200
    accepted = client.post(
        f"{review_endpoint}/proposals",
        headers=_headers("fe-accept"),
        json={
            "base_review_version": 3,
            "base_scene_version": 1,
            "proposal_id": CIRCLE_PROPOSAL_ID,
            "action": "accept",
            "justification": "Círculo aceito como hipótese visual revisada.",
            "calibration_id": calibration.json()["calibration"]["calibration_id"],
        },
    )
    assert accepted.status_code == 200
    return (
        job_id,
        review_endpoint,
        accepted.json()["scene"]["id"],
        accepted.json()["proposal_decisions"][-1]["entity_id"],
    )


def _seed_confirmed_survey(client: TestClient, job_id: str) -> None:
    """Levantamento concluído com uma medida confirmada, no molde do app de campo."""
    packet = _survey_packet(SURVEY_E2E)
    packet["measurements"][0]["id"] = "measurement-confirmed"
    packet["measurements"][0]["value_mm"] = SURVEY_WITNESS_MM
    database = cast(Database, cast(Any, client.app).state.database)
    with database.sessions.begin() as session:
        session.add(
            SurveyRecord(
                id=SURVEY_E2E,
                tenant_id=TENANT,
                name="Levantamento da praça",
                order_ref="OS-030-E2E",
                status="COMPLETED",
                version=2,
                snapshot_json=packet,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )


def _upload_standalone_photo(client: TestClient, storage: FakeObjectStore, job_id: str) -> str:
    """Presign → PUT → confirm de uma foto avulsa; devolve o `evidence_id` confirmado."""
    body = b"croquito-e2e::foto-avulsa-do-muro" * 8
    fe_version = client.get(
        f"/v1/jobs/{job_id}/field-evidence", headers=_headers("fe-ev-read")
    ).json()["version"]
    presign = client.post(
        f"/v1/jobs/{job_id}/field-evidence/photos/presign",
        headers=_headers("fe-photo-presign"),
        json={
            "base_version": fe_version,
            "sha256": hashlib.sha256(body).hexdigest(),
            "mime_type": "image/jpeg",
            "byte_size": len(body),
            "anchor_text": "Muro dos fundos, junto ao portão",
        },
    )
    assert presign.status_code == 200
    photo_id = presign.json()["photo_id"]
    database = cast(Database, cast(Any, client.app).state.database)
    with database.sessions() as session:
        record = session.get(JobFieldPhotoRecord, photo_id)
        assert record is not None
        object_key = record.object_key
    storage.put_direct(object_key=object_key, body=body, content_type="image/jpeg")
    confirm = client.post(
        f"/v1/jobs/{job_id}/field-evidence/photos/{photo_id}/confirm",
        headers=_headers("fe-photo-confirm"),
        json={"base_version": presign.json()["version"]},
    )
    assert confirm.status_code == 200
    return str(photo_id)


def _analysis_key(job_id: str, evidence_id: str, task: str) -> str:
    return (
        f"tenants/{TENANT}/jobs/{job_id}/field-evidence/analysis/"
        f"standalone/{evidence_id}/{task}.json"
    )


def _confirm_photo_value(
    client: TestClient, storage: FakeObjectStore, job_id: str, evidence_id: str
) -> str:
    """Ato 1 do legado: leitura de máquina processada e valor confirmado. Devolve o id."""
    database = cast(Database, cast(Any, client.app).state.database)
    key = _analysis_key(job_id, evidence_id, "reading")
    with database.sessions.begin() as session:
        session.add(
            FieldEvidenceAnalysisRecord(
                id="00000000-0000-7000-8000-0000000030b1",
                tenant_id=TENANT,
                job_id=job_id,
                origin="standalone",
                evidence_id=evidence_id,
                task="reading",
                status="PROCESSED",
                artifact_key=key,
                requested_by="eng-e2e",
            )
        )
    storage.put_direct(
        object_key=key,
        body=json.dumps(
            {"schema": "field-evidence-reading/1", "readings": [{"id": PHOTO_READING_ID}]}
        ).encode(),
        content_type="application/json",
    )
    fe_version = client.get(
        f"/v1/jobs/{job_id}/field-evidence", headers=_headers("fe-ev-read-2")
    ).json()["version"]
    confirmed = client.post(
        f"/v1/jobs/{job_id}/field-evidence/photos/standalone/{evidence_id}/values",
        headers=_headers("fe-value"),
        json={
            "base_version": fe_version,
            "source_reading_id": PHOTO_READING_ID,
            "value_mm": PHOTO_WITNESS_MM,
            "kind": "length",
            "raw_text": "25,85 m",
        },
    )
    assert confirmed.status_code == 200
    return str(confirmed.json()["confirmation"]["confirmation_id"])


def _seed_classification_draft(
    client: TestClient, storage: FakeObjectStore, job_id: str, evidence_id: str
) -> None:
    database = cast(Database, cast(Any, client.app).state.database)
    key = _analysis_key(job_id, evidence_id, "classification")
    with database.sessions.begin() as session:
        session.add(
            FieldEvidenceAnalysisRecord(
                id="00000000-0000-7000-8000-0000000030b2",
                tenant_id=TENANT,
                job_id=job_id,
                origin="standalone",
                evidence_id=evidence_id,
                task="classification",
                status="DRAFT",
                artifact_key=key,
                requested_by="eng-e2e",
            )
        )
    storage.put_direct(
        object_key=key,
        body=json.dumps(
            {
                "schema": "field-evidence-classification/1",
                "classification": {
                    "category": "MURO",
                    "description": "Muro de alvenaria com portão à direita.",
                    "topology_notes": ["fecha à direita"],
                    "confidence": "high",
                },
                "lineage": {
                    "provider": "anthropic",
                    "model_id": "claude-opus-5",
                    "prompt": {
                        "prompt_id": "field-photo-classification",
                        "prompt_version": "field-photo-classification@1.0.0",
                        "template_hash": "d" * 64,
                        "schema_version": "1.0.0",
                    },
                },
            }
        ).encode(),
        content_type="application/json",
    )


def _review_version(client: TestClient, review_endpoint: str, key: str) -> int:
    return int(client.get(review_endpoint, headers=_headers(key)).json()["version"])


def test_field_evidence_e_observacao_coexistem_com_a_exportacao(
    tmp_path: Path,
    stack: tuple[TestClient, LocalQueueWorker, FakeObjectStore, FakeQueue],
) -> None:
    """F-030 T8: testemunhas divergentes e observação de campo não impedem o export.

    A jornada leva uma cota confirmada a receber duas testemunhas com diferença neutra e uma
    observação sobre a classificação por IA — tudo fora da cena. A cena não muda por isso, e
    a aprovação e a exportação seguem fechando o pacote auditado.
    """
    client, worker, storage, _queue = stack
    job_id, review_endpoint, scene_draft_id, approximate_id = _reach_exportable_scene(
        client, worker, storage, tmp_path
    )

    # Impressão digital da cena ANTES da evidência de campo: id, versão e blockers.
    before = client.get(review_endpoint, headers=_headers("fe-before")).json()
    scene_before = before["scene"]
    blockers_before = before["blockers"]

    # 1. Levantamento vinculado pela rota real e uma foto avulsa confirmada.
    _seed_confirmed_survey(client, job_id)
    fe_version = client.get(
        f"/v1/jobs/{job_id}/field-evidence", headers=_headers("fe-link-read")
    ).json()["version"]
    linked = client.post(
        f"/v1/jobs/{job_id}/field-evidence/surveys/{SURVEY_E2E}",
        headers=_headers("fe-link"),
        json={"base_version": fe_version},
    )
    assert linked.status_code == 200
    photo_id = _upload_standalone_photo(client, storage, job_id)

    # 2. As duas fontes de testemunha: medida confirmada do app e valor lido em foto.
    confirmation_id = _confirm_photo_value(client, storage, job_id, photo_id)

    survey_witness = client.post(
        f"{review_endpoint}/witnesses",
        headers=_headers("fe-witness-survey"),
        json={
            "base_version": _review_version(client, review_endpoint, "fe-rv-1"),
            "action": "associate",
            "reading_id": WIDTH_READING_ID,
            "source": {
                "type": "survey_measurement",
                "source_id": "measurement-confirmed",
                "survey_id": SURVEY_E2E,
            },
        },
    )
    assert survey_witness.status_code == 200
    photo_witness = client.post(
        f"{review_endpoint}/witnesses",
        headers=_headers("fe-witness-photo"),
        json={
            "base_version": _review_version(client, review_endpoint, "fe-rv-2"),
            "action": "associate",
            "reading_id": WIDTH_READING_ID,
            "source": {"type": "photo_reading", "source_id": confirmation_id},
        },
    )
    assert photo_witness.status_code == 200
    witnesses = photo_witness.json()["field_witnesses"]
    # Duas testemunhas empilhadas na mesma cota, cada diferença um número neutro.
    assert len(witnesses) == 2
    assert {item["difference_mm"] for item in witnesses} == {"30.00", "-50.00"}
    assert all("status" not in item and "agrees" not in item for item in witnesses)
    assert all(item["reading_id"] == WIDTH_READING_ID for item in witnesses)

    # 3. Observação humana sobre a classificação por IA, versionada fora da cena.
    _seed_classification_draft(client, storage, job_id, photo_id)
    recorded = client.post(
        f"{review_endpoint}/field-observations",
        headers=_headers("fe-observe"),
        json={
            "base_version": _review_version(client, review_endpoint, "fe-rv-3"),
            "action": "record",
            "origin": "standalone",
            "evidence_id": photo_id,
            "category": "MURO",
            "description": "Confirmo: é muro, não alambrado.",
        },
    )
    assert recorded.status_code == 200
    observations = recorded.json()["field_observations"]
    assert len(observations) == 1
    assert observations[0]["status"] == "ACTIVE"
    assert observations[0]["category"] == "MURO"
    # A fonte preserva a proposta da IA e o lineage, copiados do artefato pelo servidor.
    assert observations[0]["source"]["model_id"] == "claude-opus-5"
    assert observations[0]["source"]["prompt_version"] == "field-photo-classification@1.0.0"

    # 4. A cena não mudou: mesma id, versão e blockers de antes da evidência de campo.
    after = recorded.json()
    assert after["scene"]["id"] == scene_before["id"] == scene_draft_id
    assert after["scene"]["version"] == scene_before["version"]
    assert after["blockers"] == blockers_before
    # A divergência das testemunhas nunca virou blocker.
    assert not any("WITNESS" in code or "OBSERVATION" in code for code in after["blockers"])

    # 5. Aprovação e exportação seguem fechando o pacote, apesar da divergência.
    approved = client.post(
        f"/v1/jobs/{job_id}/approve",
        headers=_headers("fe-approve"),
        json={
            "revision_id": scene_draft_id,
            "accepted_approximations": [approximate_id],
            "acknowledged_criteria": [SCOPE_CRITERION],
            "source_evidence_checked": True,
            "geometry_checked": True,
            "limitations_acknowledged": True,
            "statement": "Cena cobre o campo principal; a evidência de campo é observacional.",
        },
    )
    assert approved.status_code == 200
    assert approved.json()["approved"] is True
    export = client.post(
        f"/v1/jobs/{job_id}/exports",
        headers=_headers("fe-export"),
        json={"revision_id": approved.json()["id"]},
    )
    assert export.status_code == 202
    assert worker.run_once() == 1
    completed = client.get(
        f"/v1/jobs/{job_id}/exports/{export.json()['export_id']}",
        headers=_headers("fe-export-read"),
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "COMPLETED"
    assert completed.json()["audit_status"] == "approved"
    # O pacote saiu: a evidência de campo divergente não fechou a porta da exportação.
    package_key = (
        f"tenants/{TENANT}/jobs/{job_id}/exports/{export.json()['export_id']}/croquito.zip"
    )
    with zipfile.ZipFile(BytesIO(storage.body(package_key))) as package:
        assert "desenho.dxf" in package.namelist()
