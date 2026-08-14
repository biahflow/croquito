"""Smoke fim a fim contra o ambiente local em Docker.

Exercita o que o teste in-process não alcança: presign real com checksum, `head_object`
do S3, envelope real do SQS, Postgres e a publicação do pacote no object store. Usa
somente uma fixture sintética — nunca toca em documento de cliente.

Uso:

    make dev-services && make db-init
    make smoke-local
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen
from uuid import UUID

import boto3
import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.bundles import (
    CIRCLE_PROPOSAL_ID,
    CIRCLE_READING_ID,
    HEIGHT_M,
    HEIGHT_PROPOSAL_ID,
    HEIGHT_READING_ID,
    WIDTH_M,
    WIDTH_PROPOSAL_ID,
    WIDTH_READING_ID,
    write_seed_bundle,
)
from tests.fakes import synthetic_pdf

from croquitodxf_worker.criteria import ScopeCriterion
from croquitodxf_worker.local_queue import (
    LocalQueueWorker,
    LocalWorkerSettings,
)
from croquitodxf_worker.review_seed import SeedInputs, seed_review

API_BASE_URL = os.getenv("CROQUITODXF_SMOKE_API_URL", "http://127.0.0.1:8000")
TENANT = os.getenv("CROQUITODXF_SMOKE_TENANT", "tenant-smoke")
SCOPE_CRITERION = "ACC_SMOKE_001"
SCOPE_CRITERION_TEXT = "Critério sintético do smoke: cobertura declarada da fixture local."
DATASET_ID = "smoke-sintetico-v1"


class SmokeFailure(RuntimeError):
    """A smoke step did not produce the expected local result."""


def _headers(key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer test:{TENANT}:smoke-operator:engineer",
        "Idempotency-Key": key,
        "Content-Type": "application/json",
    }


def _expect(response: httpx.Response, status: int, step: str) -> dict[str, Any]:
    if response.status_code != status:
        raise SmokeFailure(f"{step}: esperado {status}, recebido {response.status_code}")
    payload: Any = response.json()
    if not isinstance(payload, dict):
        raise SmokeFailure(f"{step}: resposta inesperada")
    return payload


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
    raise SmokeFailure("Aresta esperada ausente na cena do solver")


def _preflight() -> LocalWorkerSettings:
    if os.getenv("CROQUITODXF_REAL_PROVIDERS_ENABLED", "").lower() in {"1", "true", "yes"}:
        raise SmokeFailure(
            "Providers reais estão ligados. O smoke não executa chamadas pagas: "
            "desligue CROQUITODXF_REAL_PROVIDERS_ENABLED."
        )
    if os.getenv("CROQUITODXF_ALLOW_TEST_TOKENS", "").lower() not in {"1", "true", "yes"}:
        raise SmokeFailure(
            "O smoke precisa de CROQUITODXF_ALLOW_TEST_TOKENS=true no .env.local: o realm "
            "local desabilita direct access grants e não há token fora do browser."
        )
    return LocalWorkerSettings.from_environment()


def _decisions_payload() -> dict[str, Any]:
    return {
        "base_version": 1,
        "decisions": [
            {
                "reading_id": WIDTH_READING_ID,
                "action": "confirm",
                "justification": "Fixture sintética do smoke local.",
                "association_proposal_id": WIDTH_PROPOSAL_ID,
            },
            {
                "reading_id": HEIGHT_READING_ID,
                "action": "confirm",
                "justification": "Fixture sintética do smoke local.",
                "association_proposal_id": HEIGHT_PROPOSAL_ID,
            },
            {
                "reading_id": CIRCLE_READING_ID,
                "action": "confirm",
                "justification": "Fixture sintética do smoke local.",
                "association_proposal_id": CIRCLE_PROPOSAL_ID,
            },
        ],
    }


def run_smoke(output_dir: Path) -> dict[str, Any]:
    settings = _preflight()
    output_dir.mkdir(parents=True, exist_ok=True)
    pdf = synthetic_pdf()
    source_sha256 = hashlib.sha256(pdf).hexdigest()
    worker = LocalQueueWorker(settings)

    with httpx.Client(base_url=API_BASE_URL, timeout=30.0) as client:
        presign = _expect(
            client.post(
                "/v1/uploads/presign",
                headers=_headers("smoke-presign"),
                json={
                    "filename": "smoke.pdf",
                    "content_type": "application/pdf",
                    "size_bytes": len(pdf),
                    "sha256": source_sha256,
                },
            ),
            200,
            "presign",
        )

        # PUT real na URL assinada: é aqui que o checksum e a política do bucket valem.
        request = Request(presign["url"], data=pdf, method="PUT", headers=dict(presign["headers"]))
        with urlopen(request) as upload_response:
            if upload_response.status not in {200, 204}:
                raise SmokeFailure(f"PUT assinado falhou: {upload_response.status}")

        job = _expect(
            client.post(
                "/v1/jobs",
                headers=_headers("smoke-job"),
                json={
                    "upload_id": presign["upload_id"],
                    "project_name": "Smoke sintético",
                    "default_unit": "m",
                },
            ),
            201,
            "criação do job",
        )
        job_id = str(job["job_id"])

        if worker.run_once() != 1:
            raise SmokeFailure("worker não consumiu a mensagem de ingestão")

        bundle = write_seed_bundle(
            output_dir / "bundle", source_sha256=source_sha256, dataset_id=DATASET_ID
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
                required_criteria=(
                    ScopeCriterion(code=SCOPE_CRITERION, text=SCOPE_CRITERION_TEXT),
                ),
                operator_id="smoke-operator",
            ),
            settings,
        )

        review_endpoint = f"/v1/jobs/{job_id}/review"
        review = _expect(
            client.get(review_endpoint, headers=_headers("smoke-review")),
            200,
            "leitura da revisão",
        )
        if review["required_criteria"] != [{"code": SCOPE_CRITERION, "text": SCOPE_CRITERION_TEXT}]:
            raise SmokeFailure("critério de escopo não chegou com texto na revisão")

        solved = _expect(
            client.post(
                f"{review_endpoint}/decisions",
                headers=_headers("smoke-decisions"),
                json=_decisions_payload(),
            ),
            200,
            "decisões de leitura",
        )
        scene = solved["scene"]
        if scene is None or scene["version"] != 1:
            raise SmokeFailure("solver não criou a cena métrica")

        calibration = _expect(
            client.post(
                f"{review_endpoint}/calibration",
                headers=_headers("smoke-calibration"),
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
            ),
            200,
            "calibração",
        )

        accepted = _expect(
            client.post(
                f"{review_endpoint}/proposals",
                headers=_headers("smoke-accept"),
                json={
                    "base_review_version": 3,
                    "base_scene_version": 1,
                    "proposal_id": CIRCLE_PROPOSAL_ID,
                    "action": "accept",
                    "justification": "Fixture sintética aceita como aproximação.",
                    "calibration_id": calibration["calibration"]["calibration_id"],
                },
            ),
            200,
            "aceite de proposta",
        )
        draft_id = str(accepted["scene"]["id"])
        approximate_id = str(accepted["proposal_decisions"][-1]["entity_id"])

        approved = _expect(
            client.post(
                f"/v1/jobs/{job_id}/approve",
                headers=_headers("smoke-approve"),
                json={
                    "revision_id": draft_id,
                    "accepted_approximations": [approximate_id],
                    # A cena do smoke cobre só o campo principal: o critério é declarado
                    # pendente, nunca coberto.
                    "acknowledged_criteria": [SCOPE_CRITERION],
                    "covered_criteria": [],
                    "source_evidence_checked": True,
                    "geometry_checked": True,
                    "limitations_acknowledged": True,
                    "statement": "Fixture sintética do smoke; nenhum dado real envolvido.",
                },
            ),
            200,
            "aprovação",
        )

        export = _expect(
            client.post(
                f"/v1/jobs/{job_id}/exports",
                headers=_headers("smoke-export"),
                json={"revision_id": approved["id"]},
            ),
            202,
            "solicitação de export",
        )
        if worker.run_once() != 1:
            raise SmokeFailure("worker não consumiu a mensagem de exportação")

        artifact = _expect(
            client.get(
                f"/v1/jobs/{job_id}/exports/{export['export_id']}",
                headers=_headers("smoke-export-read"),
            ),
            200,
            "leitura do artefato",
        )

    report_job_id = str(artifact["job_id"])
    if artifact["status"] != "COMPLETED" or artifact["audit_status"] != "approved":
        raise SmokeFailure(
            f"export não concluiu: {artifact['status']} / {artifact['failure_code']}"
        )
    if not artifact["package_url"]:
        raise SmokeFailure("pacote concluído sem URL assinada")

    # Baixa pela URL assinada e confere o conteúdo publicado.
    with tempfile.TemporaryDirectory() as workspace:
        package_path = Path(workspace) / "croquitodxf.zip"
        with urlopen(str(artifact["package_url"])) as download:
            package_path.write_bytes(download.read())
        with zipfile.ZipFile(package_path) as package:
            names = sorted(package.namelist())
            approval_record = json.loads(package.read("aprovacao.json"))

    expected = [
        "aprovacao.json",
        "auditoria.json",
        "desenho.dxf",
        "hipoteses.json",
        "preview.png",
        "quantitativos.csv",
    ]
    if names != expected:
        raise SmokeFailure(f"pacote incompleto: {names}")
    if approval_record["acknowledged_criteria"] != [SCOPE_CRITERION]:
        raise SmokeFailure("ressalva de escopo ausente no pacote")
    if approval_record["covered_criteria"] != []:
        raise SmokeFailure("pacote declara como coberto um critério que a cena não cobre")

    # Confirma que o objeto está sob o prefixo privado do tenant, com SSE.
    s3: Any = boto3.client(
        "s3",
        region_name=settings.aws_region,
        endpoint_url=settings.aws_endpoint_url,
    )
    package_key = (
        f"tenants/{TENANT}/jobs/{report_job_id}/exports/{artifact['export_id']}/croquitodxf.zip"
    )
    head = s3.head_object(Bucket=settings.artifact_bucket, Key=package_key)
    if head.get("ServerSideEncryption") != "AES256":
        raise SmokeFailure("pacote publicado sem server-side encryption")

    return {
        "job_id": report_job_id,
        "export_id": artifact["export_id"],
        "audit_status": artifact["audit_status"],
        "dxf_sha256": artifact["dxf_sha256"],
        "package_files": names,
        "acknowledged_criteria": approval_record["acknowledged_criteria"],
        "covered_criteria": approval_record["covered_criteria"],
    }


def main() -> int:
    output_dir = Path(os.getenv("CROQUITODXF_SMOKE_OUTPUT", "output/smoke"))
    try:
        report = run_smoke(output_dir)
    except (SmokeFailure, httpx.HTTPError) as error:
        print(json.dumps({"passed": False, "error": str(error)}, ensure_ascii=False))
        return 1
    report_path = output_dir / "smoke-local.json"
    report_path.write_text(
        json.dumps({"passed": True, **report}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"passed": True, **report, "report": str(report_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
