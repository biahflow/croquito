"""Sessão autenticada mínima do servidor de medição hospedado (ADR-0026).

O servidor de medição nasceu **local** e sem autenticação (ADR-0020): quem sobe o processo
declara quem decide (`--reviewer`). Este módulo é o que troca essa origem quando o servidor
sai da máquina do operador — e **só** ela: nenhuma regra de domínio mora aqui.

Três decisões do ADR-0026 estão escritas neste arquivo:

- **Uma identidade só no ambiente.** A validação é a do validador compartilhado
  (`croquito_core.oidc`), contra o MESMO realm da sessão de cena. Este módulo não importa
  `croquito_api` — a dependência entre os dois serviços corre no sentido oposto —, e por
  isso a medição hospedada não ganha fornecedor de identidade próprio nem lista de usuários
  própria.
- **Papel `orcamentista` exigido**, como claim de realm: quem revisa takeoff e confirma
  código não é quem aprova cena.
- **`reviewer_id` derivado do token** (`preferred_username` como rótulo legível, `sub` como
  fallback). O carimbo continua sendo do servidor; o que muda é a origem — claim assinado
  em vez de argumento de processo.

A recusa sai no MESMO envelope das demais recusas do servidor (`code`, `detail`, `details`
em `application/problem+json`), com códigos estáveis, e nunca ecoa o token: `details` só
carrega o que é seguro dizer em voz alta (nome da variável ausente, comprimento inválido).
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Annotated, Final

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.requests import Request

from croquito_core.oidc import OidcIdentity, OidcTokenError, validate_bearer_token
from croquito_valuation.errors import ValuationValidationError

REVIEWER_ROLE: Final = "orcamentista"
"""Único papel deste contexto; ele não vem do corpo da requisição.

Mora aqui, e não no `local_server`, porque no modo hospedado ele é claim de realm exigido
antes da rota — e o servidor local o importa de volta para carimbar a decisão. Uma
constante, dois modos: o papel gravado no artefato é o mesmo que o token precisa provar.
"""

REVIEWER_ID_MAX_LENGTH: Final = 120
"""Mesmo limite do `--reviewer` do modo local; a identidade muda de origem, não de forma."""

HOSTED_OIDC_ISSUER_ENV: Final = "CROQUITO_MEDICAO_OIDC_ISSUER"
HOSTED_OIDC_AUDIENCE_ENV: Final = "CROQUITO_MEDICAO_OIDC_AUDIENCE"
HOSTED_WEB_ORIGINS_ENV: Final = "CROQUITO_MEDICAO_WEB_ORIGINS"
"""Origens da UI hospedada, separadas por vírgula."""

_BEARER_SCHEME: Final = HTTPBearer(auto_error=False)
"""`auto_error=False`: a recusa é escrita aqui, no envelope do servidor de medição."""

HOSTED_REVIEWER_ATTR: Final = "hosted_reviewer"
"""Chave em `request.state` onde a dependency deposita a identidade da requisição."""


@dataclass(frozen=True, slots=True)
class HostedReviewer:
    """Quem está decidindo nesta requisição, derivado só de claims assinados."""

    reviewer_id: str
    tenant_id: str
    roles: frozenset[str]


class HostedSessionRefusal(Exception):
    """Recusa de sessão com status HTTP declarado e erro de domínio dentro.

    Espelha `local_server.LocalServerRefusal` de propósito: o cliente lê `code`, `detail` e
    `details` do mesmo jeito, venha a recusa do domínio ou da porta de entrada.
    """

    def __init__(self, status_code: int, error: ValuationValidationError) -> None:
        self.status_code = status_code
        self.error = error
        super().__init__(str(error))


def _session_required(reason: str) -> HostedSessionRefusal:
    """Sem token utilizável não há requisição: 401 antes de qualquer leitura da rodada."""
    return HostedSessionRefusal(
        401,
        ValuationValidationError(
            "HOSTED_SESSION_REQUIRED",
            "esta rota exige sessão autenticada; entre no ambiente e tente de novo",
            {"reason": reason},
        ),
    )


def _session_invalid(code: str) -> HostedSessionRefusal:
    """Token apresentado e recusado pelo validador — assinatura, issuer, audience, prazo."""
    return HostedSessionRefusal(
        401,
        ValuationValidationError(
            "HOSTED_SESSION_INVALID",
            "a sessão não pôde ser validada; entre de novo",
            {"reason": code},
        ),
    )


def _role_required(roles: frozenset[str]) -> HostedSessionRefusal:
    """Token válido de quem não decide medição: 403, e o papel exigido dito por extenso."""
    return HostedSessionRefusal(
        403,
        ValuationValidationError(
            "HOSTED_ROLE_REQUIRED",
            f"esta rota exige o papel {REVIEWER_ROLE}; peça a quem administra o ambiente",
            {"required_role": REVIEWER_ROLE, "roles": sorted(roles)},
        ),
    )


def reviewer_id_from_identity(identity: OidcIdentity) -> str:
    """Identidade legível de quem decide: `preferred_username`, com `sub` como fallback.

    O rótulo vai para dentro do artefato, ao lado do papel e do relógio do servidor, então
    ele passa pela MESMA regra de forma do `--reviewer` local. Claim fora dela recusa a
    sessão em vez de virar carimbo truncado: o que fica gravado tem de ser o que foi
    assinado.
    """
    label = (identity.preferred_username or "").strip()
    chosen = label or identity.subject.strip()
    if not 1 <= len(chosen) <= REVIEWER_ID_MAX_LENGTH:
        raise HostedSessionRefusal(
            401,
            ValuationValidationError(
                "HOSTED_REVIEWER_INVALID",
                "a identidade do token não serve de carimbo de decisão",
                {"length": len(chosen)},
            ),
        )
    return chosen


def build_reviewer_dependency(*, issuer: str, audience: str) -> Callable[..., HostedReviewer]:
    """Dependency que só deixa passar quem provou ser orçamentista deste realm.

    O issuer e a audience são fixados na subida do processo (nunca vêm da requisição), e o
    resultado é depositado em `request.state` para que as rotas que CARIMBAM decisão leiam a
    identidade da requisição corrente — nunca uma identidade de processo.
    """

    def require_reviewer(
        request: Request,
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_BEARER_SCHEME)],
    ) -> HostedReviewer:
        if credentials is None:
            raise _session_required("cabeçalho Authorization: Bearer ausente")
        if credentials.scheme.lower() != "bearer":
            raise _session_required("esquema de autorização não suportado")
        try:
            identity = validate_bearer_token(
                credentials.credentials, issuer=issuer, audience=audience
            )
        except OidcTokenError as error:
            raise _session_invalid(error.code) from error
        if REVIEWER_ROLE not in identity.roles:
            raise _role_required(identity.roles)
        reviewer = HostedReviewer(
            reviewer_id=reviewer_id_from_identity(identity),
            tenant_id=identity.tenant_id,
            roles=identity.roles,
        )
        setattr(request.state, HOSTED_REVIEWER_ATTR, reviewer)
        return reviewer

    return require_reviewer


def hosted_reviewer_id(request: Request) -> str:
    """Identidade posta pela dependency nesta requisição; ausência recusa fechada.

    Ela nunca deveria faltar — a dependency é global no app hospedado. Se faltar, a causa é
    uma rota registrada fora dela, e o desfecho seguro é recusar: melhor 401 do que gravar
    uma decisão sem dono.
    """
    reviewer = getattr(request.state, HOSTED_REVIEWER_ATTR, None)
    if not isinstance(reviewer, HostedReviewer):
        raise _session_required("rota sem sessão resolvida")
    return reviewer.reviewer_id


@dataclass(frozen=True, slots=True)
class HostedSettings:
    """Configuração do modo hospedado, lida do ambiente na subida do processo."""

    issuer: str
    audience: str
    allowed_origins: tuple[str, ...]


def hosted_settings_from_env(environ: Mapping[str, str] | None = None) -> HostedSettings:
    """Issuer, audience e origens da web declarados no ambiente; ausência recusa.

    Fail-closed é o ponto: um default silencioso aqui subiria um servidor hospedado sem
    validar nada, que é exatamente o desfecho que o modo explícito existe para impedir.
    """
    values: Mapping[str, str] = os.environ if environ is None else environ
    issuer = values.get(HOSTED_OIDC_ISSUER_ENV, "").strip()
    audience = values.get(HOSTED_OIDC_AUDIENCE_ENV, "").strip()
    origins = parse_web_origins(values.get(HOSTED_WEB_ORIGINS_ENV, ""))
    missing = [
        name
        for name, value in (
            (HOSTED_OIDC_ISSUER_ENV, issuer),
            (HOSTED_OIDC_AUDIENCE_ENV, audience),
            (HOSTED_WEB_ORIGINS_ENV, ",".join(origins)),
        )
        if not value
    ]
    if missing:
        raise ValuationValidationError(
            "HOSTED_CONFIG_MISSING",
            "modo hospedado exige issuer, audience e origens da web declarados no ambiente",
            {"missing_env": missing},
        )
    return HostedSettings(issuer=issuer, audience=audience, allowed_origins=origins)


def parse_web_origins(raw: str) -> tuple[str, ...]:
    """Origens separadas por vírgula, sem entrada vazia e sem espaço nas pontas."""
    parsed: Sequence[str] = [part.strip() for part in raw.split(",")]
    return tuple(origin for origin in parsed if origin)
