"""S3 boundary for private artifacts; vendor details do not leak into routes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from croquito_api.config import ApiSettings, StorageFlavor


@dataclass(frozen=True, slots=True)
class UploadedObject:
    content_length: int
    content_type: str
    #: `None` quando o storage não devolve checksum próprio (interop GCS): a integridade
    #: do PDF continua sendo verificada pelo worker, que recalcula o sha256 dos bytes.
    checksum_sha256: str | None


class ArtifactStore:
    def __init__(self, settings: ApiSettings) -> None:
        self.bucket = settings.artifact_bucket
        self.flavor: StorageFlavor = settings.storage_flavor
        self.client: Any = boto3.client(
            "s3",
            region_name=settings.aws_region,
            endpoint_url=settings.aws_endpoint_url,
            config=(
                # A interoperabilidade XML do GCS assina SigV4, mas só aceita a URL
                # path-style; virtual-host com o bucket no domínio não resolve lá.
                Config(signature_version="s3v4", s3={"addressing_style": "path"})
                if settings.storage_flavor == "gcs"
                else Config(signature_version="s3v4")
            ),
        )

    def presign_pdf_upload(self, *, object_key: str, checksum_sha256: str) -> str:
        params: dict[str, Any] = {
            "Bucket": self.bucket,
            "Key": object_key,
            "ContentType": "application/pdf",
        }
        if self.flavor == "s3":
            # `x-amz-checksum-sha256` amarra o digest declarado à própria assinatura. O
            # GCS rejeita o header, então lá o digest é conferido pelo worker.
            params["ChecksumSHA256"] = checksum_sha256
        return str(
            self.client.generate_presigned_url(
                "put_object",
                Params=params,
                ExpiresIn=900,
            )
        )

    def head_upload(self, *, object_key: str) -> UploadedObject | None:
        head: dict[str, Any] = {"Bucket": self.bucket, "Key": object_key}
        if self.flavor == "s3":
            head["ChecksumMode"] = "ENABLED"
        try:
            response = self.client.head_object(**head)
        except (BotoCoreError, ClientError):
            return None
        length = response.get("ContentLength")
        content_type = response.get("ContentType")
        checksum = response.get("ChecksumSHA256") if self.flavor == "s3" else None
        if not isinstance(length, int) or not isinstance(content_type, str):
            return None
        return UploadedObject(
            content_length=length,
            content_type=content_type,
            checksum_sha256=checksum if isinstance(checksum, str) else None,
        )

    def presign_private_read(self, *, object_key: str) -> str:
        """Returns a short-lived URL only after the route has checked ownership."""
        return str(
            self.client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": object_key},
                ExpiresIn=900,
            )
        )
