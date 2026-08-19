"""`identity_from_claims`: a fronteira que decide quem a API reconhece.

O caso do tenant ausente tem código próprio porque a resposta certa do cliente é
diferente: token inválido pede novo login; conta sem tenant pede um administrador —
misturá-los produziu o loop silencioso do incidente de 2026-08-19 em homologação.
"""

import pytest

from croquito_core.oidc import OidcTokenError, identity_from_claims


def _claims(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "sub": "user-1",
        "tenant_id": "tenant-x",
        "realm_access": {"roles": ["engineer"]},
        "preferred_username": "daniel",
    }
    base.update(overrides)
    return base


def test_claims_completos_viram_identidade() -> None:
    identity = identity_from_claims(_claims())

    assert identity.subject == "user-1"
    assert identity.tenant_id == "tenant-x"
    assert identity.roles == frozenset({"engineer"})
    assert identity.preferred_username == "daniel"


def test_tenant_ausente_recusa_com_codigo_proprio() -> None:
    claims = _claims()
    del claims["tenant_id"]

    with pytest.raises(OidcTokenError) as excinfo:
        identity_from_claims(claims)

    assert excinfo.value.code == "TOKEN_WITHOUT_TENANT"


def test_tenant_com_forma_errada_recusa_com_codigo_proprio() -> None:
    with pytest.raises(OidcTokenError) as excinfo:
        identity_from_claims(_claims(tenant_id=123))

    assert excinfo.value.code == "TOKEN_WITHOUT_TENANT"


def test_sub_ausente_continua_token_invalido() -> None:
    claims = _claims()
    del claims["sub"]

    with pytest.raises(OidcTokenError) as excinfo:
        identity_from_claims(claims)

    assert excinfo.value.code == "INVALID_TOKEN"


def test_papel_com_forma_errada_continua_token_invalido() -> None:
    with pytest.raises(OidcTokenError) as excinfo:
        identity_from_claims(_claims(realm_access={"roles": ["engineer", 7]}))

    assert excinfo.value.code == "INVALID_TOKEN"


def test_realm_access_ausente_vira_identidade_sem_papeis() -> None:
    claims = _claims()
    del claims["realm_access"]

    identity = identity_from_claims(claims)

    assert identity.roles == frozenset()


def test_jwks_client_busca_pela_url_dedicada_quando_ha_uma() -> None:
    """A URL de busca separa DE ONDE as chaves vêm de QUEM emitiu (Cloudflare na frente
    do host público bloqueia cliente não-navegador — incidente de 2026-08-19)."""
    from croquito_core.oidc import jwks_client_for

    publico = jwks_client_for("https://exemplo.invalid/realms/x")
    interno = jwks_client_for(
        "https://exemplo.invalid/realms/x",
        "https://interno.invalid/realms/x/protocol/openid-connect/certs",
    )

    assert publico.uri == "https://exemplo.invalid/realms/x/protocol/openid-connect/certs"
    assert interno.uri == "https://interno.invalid/realms/x/protocol/openid-connect/certs"
    assert publico is not interno
