"""Validação de token OIDC compartilhada; nenhum serviço reimplementa o decode.

Mora no core porque o worker não importa a API (a dependência corre no sentido oposto)
e os dois lados precisam da mesma leitura de claims quando o transporte for push HTTP.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import jwt

#: Caminho JWKS do Keycloak; outro provedor entra aqui como parâmetro, não como fork.
JWKS_PATH = "/protocol/openid-connect/certs"


@dataclass(frozen=True, slots=True)
class OidcIdentity:
    """Identidade derivada apenas de claims assinados."""

    subject: str
    tenant_id: str
    roles: frozenset[str]
    preferred_username: str | None = None


class OidcTokenError(Exception):
    """Recusa de token com código estável; a mensagem nunca carrega o token."""

    def __init__(self, code: str = "INVALID_TOKEN") -> None:
        self.code = code
        super().__init__(code)


@lru_cache(maxsize=8)
def jwks_client_for(issuer: str) -> jwt.PyJWKClient:
    """Um cliente JWKS por issuer.

    Criar o cliente a cada request refazia o download do JWKS a cada chamada
    autenticada; o cache de chaves do próprio PyJWT resolve isso dentro do cliente.
    """
    return jwt.PyJWKClient(f"{issuer.rstrip('/')}{JWKS_PATH}", cache_keys=True)


def validate_bearer_token(
    token: str,
    *,
    issuer: str,
    audience: str,
    jwks_client: jwt.PyJWKClient | None = None,
) -> OidcIdentity:
    """Valida assinatura, issuer e audience, e devolve só o que veio assinado."""
    client = jwks_client if jwks_client is not None else jwks_client_for(issuer)
    try:
        signing_key = client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=audience,
            issuer=issuer,
        )
    except jwt.PyJWTError as error:
        raise OidcTokenError() from error
    return identity_from_claims(payload)


def identity_from_claims(payload: dict[str, Any]) -> OidcIdentity:
    """Lê `sub`, `tenant_id` e `realm_access.roles`; qualquer forma inesperada recusa."""
    subject = payload.get("sub")
    tenant_id = payload.get("tenant_id")
    realm_access = payload.get("realm_access")
    roles = realm_access.get("roles", []) if isinstance(realm_access, dict) else []
    preferred_username = payload.get("preferred_username")
    if not isinstance(subject, str) or not all(isinstance(role, str) for role in roles):
        raise OidcTokenError()
    if not isinstance(tenant_id, str):
        # Conta AUTENTICADA porém sem vínculo de tenant — o cenário do ADR-0033 (conta
        # criada sem o atributo, ou recriada sem ele; incidente real de 2026-08-19).
        # Código próprio para a casca distinguir "sua conta não tem organização" de
        # "token inválido": o primeiro se resolve com um administrador, o segundo com
        # um novo login — misturá-los produz loop de retentativa sem saída.
        raise OidcTokenError("TOKEN_WITHOUT_TENANT")
    return OidcIdentity(
        subject=subject,
        tenant_id=tenant_id,
        roles=frozenset(roles),
        preferred_username=(preferred_username if isinstance(preferred_username, str) else None),
    )
