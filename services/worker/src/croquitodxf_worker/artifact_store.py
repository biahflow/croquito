"""Publicação do pacote CAD no object store privado do tenant."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class WorkerArtifactStore:
    """Writes audited export packages under the job's private seven-day lifecycle prefix."""

    client: Any
    bucket: str

    def put_export_package(self, *, tenant_id: str, job_id: str, export_id: str, path: Path) -> str:
        key = f"tenants/{tenant_id}/jobs/{job_id}/exports/{export_id}/croquitodxf.zip"
        with path.open("rb") as package:
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=package,
                ContentType="application/zip",
                ServerSideEncryption="AES256",
            )
        return key
