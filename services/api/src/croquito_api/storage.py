"""S3 boundary for private artifacts; vendor details do not leak into routes."""

from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from typing import Any, cast

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

    def presign_upload(self, *, object_key: str, checksum_sha256: str, content_type: str) -> str:
        """Assina o PUT do tipo declarado; o `ContentType` entra na assinatura.

        O tipo é parâmetro porque a rodada de medição instala um catálogo JSON pelo mesmo
        presign (ADR-0028 D6 tratou só da prancha), e o cliente envia no PUT exatamente os
        headers devolvidos. Quem decide quais tipos existem é a rota, que já os valida
        contra a extensão do arquivo antes de chegar aqui.
        """
        params: dict[str, Any] = {
            "Bucket": self.bucket,
            "Key": object_key,
            "ContentType": content_type,
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

    def read_object(self, *, object_key: str, max_bytes: int) -> bytes | None:
        """Bytes de um objeto privado, limitados, ou `None` quando ele não está no store.

        Só artefato PEQUENO de aplicação passa por aqui — hoje, o catálogo de preços
        instalado na rodada de medição. Byte de cliente (PDF da prancha, PNG promovido)
        continua saindo por URL assinada: a API não faz streaming de conteúdo.

        A leitura pede um byte a mais que o teto de propósito: é assim que quem chama
        distingue "objeto do tamanho esperado" de "objeto maior que o limite" sem ter
        carregado o excesso na memória do processo.
        """
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=object_key)
        except (BotoCoreError, ClientError):
            return None
        body: Any = response.get("Body")
        if body is None:  # pragma: no cover - resposta fora do contrato do S3
            return None
        # O fechamento é explícito porque a leitura para no teto e deixa o resto do corpo
        # pendurado: sem ele, a conexão só volta ao pool quando o coletor passar.
        with closing(body):
            return cast(bytes, body.read(max_bytes + 1))

    def write_object(self, *, object_key: str, body: bytes, content_type: str) -> None:
        """Grava um artefato PEQUENO de aplicação; quem monta a chave decide o prefixo.

        Contraparte de `read_object`, e com o mesmo limite de intenção: aqui passa só o
        artefato determinístico que a API acabou de montar e auditar — a planilha do
        orçamento-base sob o prefixo do tenant (ADR-0038) e o `catalog.json` que o operador
        publica no acervo da plataforma, sob o prefixo próprio dele, FORA de `tenants/`
        (ADR-0047 decisão 1). Byte que veio do cliente continua entrando por
        `presign_upload`: a API não recebe upload no request path.

        Esta classe não conhece tenant, e por isso não é ela que isola nada — o isolamento é
        convenção de quem monta a chave, e as guardas que assinam URL o conferem por
        prefixo, uma a uma.

        A gravação acontece DEPOIS do portão de auditoria de quem chama; este método não
        sabe auditar nada, e é justamente por isso que ele não pode ser o lugar onde alguém
        decida publicar.
        """
        self.client.put_object(
            Bucket=self.bucket,
            Key=object_key,
            Body=body,
            ContentType=content_type,
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
