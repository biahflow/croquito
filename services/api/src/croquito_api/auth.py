"""Autenticação OIDC desacoplada de qualquer nuvem específica."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from croquito_core.oidc import OidcTokenError, validate_bearer_token

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
        try:
            identity = validate_bearer_token(token, issuer=self.issuer, audience=self.audience)
        except OidcTokenError as error:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail={"code": error.code}
            ) from error
        return Principal(
            subject=identity.subject,
            tenant_id=identity.tenant_id,
            roles=identity.roles,
        )

    @staticmethod
    def _test_principal(token: str) -> Principal:
        parts = token.split(":", 3)
        if len(parts) != 4 or not all(parts[1:3]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail={"code": "INVALID_TOKEN"}
            )
        roles = frozenset(role for role in parts[3].split(",") if role)
        return Principal(subject=parts[2], tenant_id=parts[1], roles=roles)


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
    # O validador compartilhado já traduz falha de PyJWT em 401; a rede continua aqui
    # para qualquer autenticador injetado que ainda propague o erro cru da biblioteca.
    except jwt.PyJWTError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail={"code": "INVALID_TOKEN"}
        ) from error
