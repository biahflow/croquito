"""Autenticação OIDC desacoplada de qualquer nuvem específica."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True, slots=True)
class Principal:
    subject: str
    tenant_id: str
    roles: frozenset[str]

    def has_role(self, role: str) -> bool:
        return role in self.roles


class OidcAuthenticator:
    def __init__(
        self, *, issuer: str | None, audience: str | None, allow_test_tokens: bool
    ) -> None:
        self.issuer = issuer
        self.audience = audience
        self.allow_test_tokens = allow_test_tokens

    def authenticate(self, token: str) -> Principal:
        if self.allow_test_tokens and token.startswith("test:"):
            return self._test_principal(token)
        if not self.issuer or not self.audience:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": "AUTH_NOT_CONFIGURED"},
            )
        jwks = jwt.PyJWKClient(f"{self.issuer.rstrip('/')}/protocol/openid-connect/certs")
        signing_key = jwks.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=self.audience,
            issuer=self.issuer,
        )
        return self._principal_from_claims(payload)

    @staticmethod
    def _test_principal(token: str) -> Principal:
        parts = token.split(":", 3)
        if len(parts) != 4 or not all(parts[1:3]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail={"code": "INVALID_TOKEN"}
            )
        roles = frozenset(role for role in parts[3].split(",") if role)
        return Principal(subject=parts[2], tenant_id=parts[1], roles=roles)

    @staticmethod
    def _principal_from_claims(payload: dict[str, Any]) -> Principal:
        subject = payload.get("sub")
        tenant_id = payload.get("tenant_id")
        realm_access = payload.get("realm_access")
        roles = realm_access.get("roles", []) if isinstance(realm_access, dict) else []
        if (
            not isinstance(subject, str)
            or not isinstance(tenant_id, str)
            or not all(isinstance(role, str) for role in roles)
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail={"code": "INVALID_TOKEN"}
            )
        return Principal(subject=subject, tenant_id=tenant_id, roles=frozenset(roles))


def require_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> Principal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail={"code": "UNAUTHORIZED"}
        )
    authenticator: OidcAuthenticator = request.app.state.authenticator
    try:
        return authenticator.authenticate(credentials.credentials)
    except jwt.PyJWTError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail={"code": "INVALID_TOKEN"}
        ) from error
