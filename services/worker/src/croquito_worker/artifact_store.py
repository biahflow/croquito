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
    #: SSE-S3 gerenciada pelo bucket. Desligar só é correto onde o storage já criptografa
    #: em repouso por padrão e recusa o header (interoperabilidade GCS).
    sse: bool = True

    def put_export_package(self, *, tenant_id: str, job_id: str, export_id: str, path: Path) -> str:
        key = f"tenants/{tenant_id}/jobs/{job_id}/exports/{export_id}/croquito.zip"
        with path.open("rb") as package:
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=package,
                ContentType="application/zip",
                **({"ServerSideEncryption": "AES256"} if self.sse else {}),
            )
        return key
