"""Configuração explícita da API; segredos nunca são versionados."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _enabled(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes"}


@dataclass(frozen=True, slots=True)
class ApiSettings:
    database_url: str
    artifact_bucket: str
    aws_region: str
    aws_endpoint_url: str | None
    queue_url: str | None
    oidc_issuer: str | None
    oidc_audience: str | None
    web_origin: str
    allow_test_tokens: bool
    real_providers_enabled: bool = False
    ai_max_estimated_cost_usd: str | None = None

    @property
    def web_origins(self) -> list[str]:
        origins = [origin.strip() for origin in self.web_origin.split(",") if origin.strip()]
        if self.aws_endpoint_url and self.aws_endpoint_url.startswith(
            ("http://localhost", "http://127.0.0.1")
        ):
            for local_origin in ("http://localhost:5173", "http://127.0.0.1:5173"):
                if local_origin not in origins:
                    origins.append(local_origin)
        return origins

    @classmethod
    def from_environment(cls) -> ApiSettings:
        return cls(
            database_url=os.getenv(
                "CROQUITO_DATABASE_URL",
                "sqlite+pysqlite:///./output/croquito-local.db",
            ),
            artifact_bucket=os.getenv("CROQUITO_ARTIFACT_BUCKET", "croquito-local-artifacts"),
            aws_region=os.getenv("AWS_REGION", "sa-east-1"),
            aws_endpoint_url=os.getenv("CROQUITO_AWS_ENDPOINT_URL") or None,
            queue_url=os.getenv("CROQUITO_PROCESSING_QUEUE_URL") or None,
            oidc_issuer=os.getenv("CROQUITO_OIDC_ISSUER") or None,
            oidc_audience=os.getenv("CROQUITO_OIDC_AUDIENCE") or None,
            web_origin=os.getenv("CROQUITO_WEB_ORIGIN", "http://localhost:5173"),
            allow_test_tokens=_enabled("CROQUITO_ALLOW_TEST_TOKENS"),
            real_providers_enabled=_enabled("CROQUITO_REAL_PROVIDERS_ENABLED"),
            ai_max_estimated_cost_usd=os.getenv("CROQUITO_AI_MAX_ESTIMATED_COST_USD") or None,
        )
