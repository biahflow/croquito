"""S3 boundary for private artifacts; vendor details do not leak into routes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from croquitodxf_api.config import ApiSettings


@dataclass(frozen=True, slots=True)
class UploadedObject:
    content_length: int
    content_type: str
    checksum_sha256: str | None


class ArtifactStore:
    def __init__(self, settings: ApiSettings) -> None:
        self.bucket = settings.artifact_bucket
        self.client: Any = boto3.client(
            "s3",
            region_name=settings.aws_region,
            endpoint_url=settings.aws_endpoint_url,
            config=Config(signature_version="s3v4"),
        )

    def presign_pdf_upload(self, *, object_key: str, checksum_sha256: str) -> str:
        return str(
            self.client.generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": self.bucket,
                    "Key": object_key,
                    "ContentType": "application/pdf",
                    "ChecksumSHA256": checksum_sha256,
                },
                ExpiresIn=900,
            )
        )

    def head_upload(self, *, object_key: str) -> UploadedObject | None:
        try:
            response = self.client.head_object(
                Bucket=self.bucket,
                Key=object_key,
                ChecksumMode="ENABLED",
            )
        except (BotoCoreError, ClientError):
            return None
        length = response.get("ContentLength")
        content_type = response.get("ContentType")
        checksum = response.get("ChecksumSHA256")
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
