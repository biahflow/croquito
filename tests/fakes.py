"""Dublês coerentes de storage e fila, compartilhados por toda a suíte.

O storage guarda bytes por chave e deriva o checksum do que foi realmente gravado, de modo
que os dois lados da verificação de upload — `head_upload` na API e o digest recalculado
pelo worker — não possam divergir silenciosamente numa fixture.
"""

from __future__ import annotations

import base64
import hashlib
import json
from collections import deque
from dataclasses import dataclass
from io import BytesIO
from typing import Any, cast

import fitz
from botocore.exceptions import ClientError

from croquito_api.storage import UploadedObject


@dataclass(frozen=True, slots=True)
class StoredObject:
    body: bytes
    content_type: str


class FakeObjectStore:
    """Serves both the API boundary (`ArtifactStore`) and the worker's boto3 S3 client."""

    def __init__(self) -> None:
        self.objects: dict[str, StoredObject] = {}
        self.puts: list[dict[str, Any]] = []

    def put_direct(
        self, *, object_key: str, body: bytes, content_type: str = "application/pdf"
    ) -> None:
        """Simulates the browser's direct PUT against the presigned URL."""
        self.objects[object_key] = StoredObject(body=body, content_type=content_type)

    def body(self, object_key: str) -> bytes:
        return self.objects[object_key].body

    # --- API boundary ------------------------------------------------------------------
    def presign_upload(
        self, *, object_key: str, checksum_sha256: str, content_type: str = "application/pdf"
    ) -> str:
        return f"https://storage.invalid/{object_key}?checksum={checksum_sha256}"

    def read_object(self, *, object_key: str, max_bytes: int) -> bytes | None:
        """Leitura limitada do objeto, como o `ArtifactStore`: um byte a mais que o teto."""
        stored = self.objects.get(object_key)
        if stored is None:
            return None
        return stored.body[: max_bytes + 1]

    def head_upload(self, *, object_key: str) -> UploadedObject | None:
        stored = self.objects.get(object_key)
        if stored is None:
            return None
        return UploadedObject(
            content_length=len(stored.body),
            content_type=stored.content_type,
            checksum_sha256=base64.b64encode(hashlib.sha256(stored.body).digest()).decode("ascii"),
        )

    def presign_private_read(self, *, object_key: str) -> str:
        return f"https://storage.invalid/{object_key}?temporary=true"

    # --- worker boundary ---------------------------------------------------------------
    def get_object(self, **kwargs: Any) -> dict[str, Any]:
        stored = self.objects.get(str(kwargs["Key"]))
        if stored is None:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        return {"Body": BytesIO(stored.body)}

    def put_object(self, **kwargs: Any) -> None:
        raw = kwargs["Body"]
        payload = cast(bytes, raw if isinstance(raw, bytes) else raw.read())
        self.objects[str(kwargs["Key"])] = StoredObject(
            body=payload,
            content_type=str(kwargs.get("ContentType", "application/octet-stream")),
        )
        self.puts.append({**kwargs, "Body": payload})


class FakeQueue:
    """One queue serving the API's `send_message` and the worker's receive/delete."""

    def __init__(self) -> None:
        self.messages: deque[dict[str, str]] = deque()
        self.delivered: list[dict[str, str]] = []
        self.deleted: list[str] = []
        self._receipts = 0

    def send_message(self, **kwargs: Any) -> None:
        self._receipts += 1
        self.messages.append(
            {"Body": str(kwargs["MessageBody"]), "ReceiptHandle": f"receipt-{self._receipts}"}
        )

    def receive_message(self, **_kwargs: Any) -> dict[str, list[dict[str, str]]]:
        if not self.messages:
            return {}
        message = self.messages.popleft()
        self.delivered.append(message)
        return {"Messages": [message]}

    def delete_message(self, **kwargs: Any) -> None:
        self.deleted.append(str(kwargs["ReceiptHandle"]))

    def commands(self) -> list[str]:
        """Commands published so far, in order, as the worker would read them."""
        return [str(json.loads(message["Body"]).get("command")) for message in self.delivered]


@dataclass
class FakePublishFuture:
    """Futuro do publisher Pub/Sub; a falha combinada aparece só em `result()`."""

    message_id: str = "fake-message-id"
    failure: BaseException | None = None

    def result(self, timeout: float | None = None) -> str:
        if self.failure is not None:
            raise self.failure
        return self.message_id


class FakePublisher:
    """Publisher Pub/Sub de teste: registra `(topic, data)` e falha sob demanda.

    As duas falhas são distintas de propósito: o cliente real recusa algumas publicações
    na chamada e reporta as demais no futuro, e o adaptador precisa traduzir as duas.
    """

    def __init__(
        self,
        *,
        publish_failure: BaseException | None = None,
        result_failure: BaseException | None = None,
    ) -> None:
        self.published: list[tuple[str, bytes]] = []
        self.publish_failure = publish_failure
        self.result_failure = result_failure

    def publish(self, topic: str, data: bytes) -> FakePublishFuture:
        if self.publish_failure is not None:
            raise self.publish_failure
        self.published.append((topic, data))
        return FakePublishFuture(failure=self.result_failure)

    def bodies(self) -> list[bytes]:
        """Corpos publicados, na ordem, como o worker os leria."""
        return [data for _topic, data in self.published]


def synthetic_pdf() -> bytes:
    """A one-page PDF that passes every deterministic upload guardrail."""
    document = fitz.open()
    document.new_page()
    content = document.tobytes()
    document.close()
    return cast(bytes, content)
