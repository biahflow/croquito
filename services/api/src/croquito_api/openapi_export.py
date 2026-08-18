"""Exporta o snapshot versionado do documento OpenAPI da API."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from croquito_api.config import ApiSettings
from croquito_api.database import Database
from croquito_api.main import create_app


def snapshot_text() -> str:
    """Serializa o documento OpenAPI gerado a partir de settings fixos e sintéticos.

    `ApiSettings` é construído aqui explicitamente, nunca por `ApiSettings.from_environment()`.
    `create_app()` tem dois ramos condicionais por configuração — o backend de fila
    (`main.py:1471-1475`, escolhido por `pubsub_topic`) e o header de checksum do upload
    (`main.py:1676-1678`, escolhido por `storage_flavor`) — e nenhum dos dois altera o
    documento OpenAPI: ambos só trocam qual cliente de nuvem é construído por trás da mesma
    forma de rota. Se este exportador lesse o ambiente do desenvolvedor, o artefato versionado
    (`tests/api/openapi.snapshot.json`) poderia carregar um bucket, endpoint ou tópico reais só
    porque quem gerou o snapshot tinha `.env.local` carregado. Settings fixos tornam o snapshot
    reprodutível e livres de qualquer dado de ambiente ou segredo.
    """
    settings = ApiSettings(
        database_url="sqlite+pysqlite:///:memory:",
        artifact_bucket="croquito-openapi-snapshot",
        aws_region="sa-east-1",
        aws_endpoint_url=None,
        queue_url=None,
        oidc_issuer=None,
        oidc_audience=None,
        web_origin="http://localhost:5173",
        allow_test_tokens=False,
        real_providers_enabled=False,
        ai_max_estimated_cost_usd=None,
        storage_flavor="s3",
        pubsub_topic=None,
    )
    database = Database(settings.database_url)
    app = create_app(settings=settings, database=database)
    document = app.openapi()
    return f"{json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True)}\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    # Sem `--check`: o gate de paridade/drift vive em `tests/api/test_openapi_contract.py`,
    # não neste script. Dois gates independentes comparando o mesmo documento poderiam
    # discordar entre si (por exemplo, se um dia divergirem em versão de dependência ou em
    # ambiente de execução), e um gate duplicado é só mais um jeito do teste real ser
    # ignorado. `make openapi-snapshot` escreve; `make test` compara.
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(snapshot_text(), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
