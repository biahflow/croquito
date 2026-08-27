"""Cria no emulador AWS LOCAL os recursos que o ambiente de desenvolvimento precisa.

Substitui o antigo `localstack/init/01-bootstrap.sh`, que dependia de dois detalhes
exclusivos do LocalStack: o binário `awslocal` embutido na imagem e o hook
`/etc/localstack/init/ready.d`. O emulador local passou a ser o floci, que não tem
nenhum dos dois — e amarrar o provisionamento à imagem do emulador é justamente o que
tornava a troca cara. Aqui o provisionamento é do REPOSITÓRIO: fala boto3 com o endpoint
configurado, e funciona contra qualquer emulador compatível com S3/SQS/StepFunctions/
Secrets Manager.

É idempotente: recurso que já existe é reconhecido e mantido, nunca recriado nem
duplicado. `make db-init` o executa antes de migrar o schema, e rodá-lo de novo depois de
um `make down-services` é o caminho de recuperar o ambiente.

Só ambiente local: o endpoint vem de `CROQUITO_AWS_ENDPOINT_URL` e o script RECUSA
qualquer endpoint que não seja um laço local, para que nenhum descuido de env aponte este
provisionamento para storage de verdade.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any
from urllib.parse import urlparse

import boto3
from botocore.exceptions import ClientError

ENDPOINT = os.getenv("CROQUITO_AWS_ENDPOINT_URL", "http://127.0.0.1:4566")
#: Mesma variável e mesmo default que `ApiSettings.from_environment` lê para o cliente S3
#: (`AWS_REGION`, `sa-east-1`). Uma segunda fonte de região aqui criaria um bucket numa
#: região e um cliente apontando para outra.
REGION = os.getenv("AWS_REGION", "sa-east-1")
BUCKET = os.getenv("CROQUITO_ARTIFACT_BUCKET", "croquito-local-artifacts")
SECRET_NAME = os.getenv("CROQUITO_LOCAL_SECRET_NAME", "croquito/local/runtime")

#: Origens que podem mandar o PUT assinado da prancha direto no bucket. O default é o par
#: `localhost`/`127.0.0.1` do Vite, e não um deles só: o browser trata os dois como origens
#: distintas, e quem abrir a SPA pelo endereço "errado" veria o upload falhar no preflight.
WEB_ORIGINS = tuple(
    origin.strip()
    for origin in os.getenv(
        "CROQUITO_WEB_ORIGIN", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if origin.strip()
)

PROCESSING_QUEUE = "croquito-local-processing"
DLQ_QUEUE = f"{PROCESSING_QUEUE}-dlq"
STATE_MACHINE = "croquito-local-extraction"

#: Contrato local da extração; o worker local consome a fila. O `Pass` existe para que a
#: máquina exista com a mesma forma do ambiente real, não para executar trabalho aqui.
STATE_MACHINE_DEFINITION = {
    "Comment": "Contrato local da extração; o worker local consome a fila.",
    "StartAt": "QueueStage",
    "States": {"QueueStage": {"Type": "Pass", "Result": {"stage": "VALIDATING"}, "End": True}},
}

LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "0.0.0.0", "host.docker.internal"})


class NotLocalEndpointError(RuntimeError):
    """Endpoint fora do laço local; provisionar ali seria escrever em storage de verdade."""

    def __init__(self, endpoint: str) -> None:
        super().__init__(
            f"CROQUITO_AWS_ENDPOINT_URL={endpoint!r} não é um endpoint local. "
            "Este script provisiona apenas o emulador da sua máquina."
        )


def _require_local_endpoint(endpoint: str) -> None:
    host = urlparse(endpoint).hostname
    if host not in LOCAL_HOSTS:
        raise NotLocalEndpointError(endpoint)


def _client(service: str) -> Any:
    return boto3.client(service, region_name=REGION, endpoint_url=ENDPOINT)


def _ensure_bucket(s3: Any) -> str:
    try:
        s3.head_bucket(Bucket=BUCKET)
        return "bucket já existia"
    except ClientError:
        # `LocationConstraint` é obrigatório FORA de us-east-1 e proibido NELA: mandá-lo em
        # us-east-1 é `InvalidLocationConstraint`. A região local é sa-east-1, mas quem
        # trocar `AWS_REGION` não deve descobrir isso por um erro de bootstrap.
        parametros: dict[str, Any] = {"Bucket": BUCKET}
        if REGION != "us-east-1":
            parametros["CreateBucketConfiguration"] = {"LocationConstraint": REGION}
        s3.create_bucket(**parametros)
        return "bucket criado"


def _ensure_cors(s3: Any) -> str:
    """CORS do bucket, sempre reescrito: ele deriva de `CROQUITO_WEB_ORIGIN`.

    Reescrever em vez de "criar se faltar" é deliberado — mudar a origem no `.env.local` e
    encontrar o CORS antigo no bucket seria uma divergência silenciosa entre o que a API
    aceita e o que o object store aceita, e ela só apareceria no upload do usuário.
    """
    s3.put_bucket_cors(
        Bucket=BUCKET,
        CORSConfiguration={
            "CORSRules": [
                {
                    "AllowedHeaders": ["Content-Type", "x-amz-checksum-sha256"],
                    "AllowedMethods": ["PUT", "HEAD", "GET"],
                    "AllowedOrigins": list(WEB_ORIGINS),
                    "ExposeHeaders": ["ETag"],
                    "MaxAgeSeconds": 300,
                }
            ]
        },
    )
    return f"CORS aplicado para {', '.join(WEB_ORIGINS)}"


def _queue_url(sqs: Any, name: str) -> str | None:
    try:
        return str(sqs.get_queue_url(QueueName=name)["QueueUrl"])
    except ClientError:
        return None


def _ensure_queues(sqs: Any) -> str:
    """Fila de processamento com DLQ ligada por redrive.

    Sem redrive a DLQ fica solta e uma mensagem venenosa reentrega para sempre — foi por
    isso que o bootstrap antigo já criava as duas nesta ordem.
    """
    notas: list[str] = []
    dlq_url = _queue_url(sqs, DLQ_QUEUE)
    if dlq_url is None:
        dlq_url = str(sqs.create_queue(QueueName=DLQ_QUEUE)["QueueUrl"])
        notas.append("DLQ criada")
    else:
        notas.append("DLQ já existia")
    dlq_arn = sqs.get_queue_attributes(QueueUrl=dlq_url, AttributeNames=["QueueArn"])["Attributes"][
        "QueueArn"
    ]
    redrive = json.dumps({"deadLetterTargetArn": dlq_arn, "maxReceiveCount": "5"})
    main_url = _queue_url(sqs, PROCESSING_QUEUE)
    if main_url is None:
        sqs.create_queue(QueueName=PROCESSING_QUEUE, Attributes={"RedrivePolicy": redrive})
        notas.append("fila criada")
    else:
        # Fila existente recebe o redrive de novo: o atributo é o que liga as duas, e uma
        # fila criada à mão sem ele passaria despercebida até a primeira mensagem venenosa.
        sqs.set_queue_attributes(QueueUrl=main_url, Attributes={"RedrivePolicy": redrive})
        notas.append("fila já existia, redrive reafirmado")
    return "; ".join(notas)


def _ensure_secret(secrets: Any) -> str:
    try:
        secrets.describe_secret(SecretId=SECRET_NAME)
        return "secret já existia"
    except ClientError:
        secrets.create_secret(Name=SECRET_NAME, SecretString="{}")
        return "secret criado"


def _ensure_state_machine(sfn: Any) -> str:
    existentes = {
        machine["name"]: machine["stateMachineArn"]
        for machine in sfn.list_state_machines().get("stateMachines", [])
    }
    if STATE_MACHINE in existentes:
        return "state machine já existia"
    sfn.create_state_machine(
        name=STATE_MACHINE,
        roleArn="arn:aws:iam::000000000000:role/croquito-local-workflow",
        definition=json.dumps(STATE_MACHINE_DEFINITION),
    )
    return "state machine criada"


def main() -> int:
    try:
        _require_local_endpoint(ENDPOINT)
    except NotLocalEndpointError as error:
        print(f"recusado: {error}", file=sys.stderr)
        return 2
    passos = [
        ("s3", _ensure_bucket),
        ("s3", _ensure_cors),
        ("sqs", _ensure_queues),
        ("secretsmanager", _ensure_secret),
        ("stepfunctions", _ensure_state_machine),
    ]
    clientes: dict[str, Any] = {}
    for service, passo in passos:
        cliente = clientes.setdefault(service, _client(service))
        print(f"{service}: {passo(cliente)}")
    print(f"recursos locais prontos em {ENDPOINT} (região {REGION})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
