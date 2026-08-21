"""Cadeia completa: upload autenticado até o pacote CAD auditado.

O teste exercita API e worker sobre o mesmo banco e o mesmo storage, incluindo o envelope
real publicado na fila. Nenhuma etapa é pulada: sem decisão humana não há cena, sem
reconhecimento explícito não há aprovação e sem auditoria aprovada não há pacote.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from croquito_api.config import ApiSettings
from croquito_api.database import Database
from croquito_api.main import create_app
from croquito_worker.association_confidence import CONFIDENCE_SCORE_VERSION
from croquito_worker.criteria import ScopeCriterion
from croquito_worker.local_queue import LocalQueueWorker, LocalWorkerSettings
from croquito_worker.review_seed import SeedInputs, seed_review
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
