"""Cria/atualiza no Keycloak LOCAL os usuários dos perfis que não vêm no realm importado.

O realm local (`keycloak/croquito-realm.json`) já traz `engenheiro.local`,
`orcamentista.local` e `aprovador.local`. Este seed cobre a lacuna: `cad_operator`,
`platform_operator`, `field_technician`, `architect` e `domain_reviewer` — os três
últimos nem existem como role no realm, então o script cria a role antes de atribuí-la.

É idempotente: usuário existente é atualizado (atributos, papéis e senha), nunca
duplicado. Rode depois de `make dev-services`. Como o Keycloak local não tem volume
persistente, as contas somem no `make down-services` — rode de novo após recriar o realm.

Credencial e endpoint são exclusivamente locais e batem com `docker-compose.local.yml`;
sobrescreva por env se seu compose divergir. Este é um utilitário de desenvolvimento e
não deve apontar para nenhum Keycloak que não seja o da sua máquina.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

KEYCLOAK_URL = os.getenv("CROQUITO_KEYCLOAK_URL", "http://localhost:8083").rstrip("/")
REALM = os.getenv("CROQUITO_KEYCLOAK_REALM", "croquito")
ADMIN_USER = os.getenv("CROQUITO_KEYCLOAK_ADMIN", "local-admin")
ADMIN_PASSWORD = os.getenv("CROQUITO_KEYCLOAK_ADMIN_PASSWORD", "local-admin-only")
TENANT = os.getenv("CROQUITO_SEED_TENANT", "tenant-local")
PASSWORD = os.getenv("CROQUITO_SEED_PASSWORD", "local-dev-only")

# username, firstName, lastName, papéis. Só os perfis sem usuário no realm importado.
SEED_USERS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("cad.local", "Cad", "Local", ("cad_operator",)),
    ("operador.local", "Operador", "Plataforma", ("platform_operator",)),
    ("tecnico.local", "Tecnico", "Campo", ("field_technician",)),
    ("arquiteto.local", "Arquiteto", "Local", ("architect",)),
    ("revisor.local", "Revisor", "Dominio", ("domain_reviewer",)),
)


def _request(method: str, url: str, token: str | None = None, body: object = None) -> bytes:
    data = None if body is None else json.dumps(body).encode()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request) as response:
        return response.read()


def _admin_token() -> str:
    url = f"{KEYCLOAK_URL}/realms/master/protocol/openid-connect/token"
    form = urllib.parse.urlencode(
        {
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": ADMIN_USER,
            "password": ADMIN_PASSWORD,
        }
    ).encode()
    request = urllib.request.Request(
        url, data=form, headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read())["access_token"]


def _ensure_role(token: str, role: str) -> None:
    url = f"{KEYCLOAK_URL}/admin/realms/{REALM}/roles/{role}"
    try:
        _request("GET", url, token)
        return
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
    _request("POST", f"{KEYCLOAK_URL}/admin/realms/{REALM}/roles", token, {"name": role})
    print(f"  · role criada: {role}")


def _user_id(token: str, username: str) -> str | None:
    query = urllib.parse.urlencode({"username": username, "exact": "true"})
    found = json.loads(_request("GET", f"{KEYCLOAK_URL}/admin/realms/{REALM}/users?{query}", token))
    return found[0]["id"] if found else None


def _upsert_user(token: str, username: str, first: str, last: str) -> str:
    payload = {
        "username": username,
        "enabled": True,
        # Nome e e-mail preenchidos e verificados: perfil incompleto dispara o VERIFY_PROFILE
        # do Keycloak 26 e trava o login (mesma lição do usuário de fumaça do HML).
        "email": f"{username}@example.invalid",
        "firstName": first,
        "lastName": last,
        "emailVerified": True,
        "attributes": {"tenant_id": [TENANT]},
    }
    existing = _user_id(token, username)
    if existing is None:
        _request("POST", f"{KEYCLOAK_URL}/admin/realms/{REALM}/users", token, payload)
        existing = _user_id(token, username)
        if existing is None:
            raise RuntimeError(f"usuário {username} não apareceu após a criação")
        print(f"  · criado: {username}")
    else:
        _request("PUT", f"{KEYCLOAK_URL}/admin/realms/{REALM}/users/{existing}", token, payload)
        print(f"  · atualizado: {username}")
    return existing


def _set_password(token: str, user_id: str) -> None:
    url = f"{KEYCLOAK_URL}/admin/realms/{REALM}/users/{user_id}/reset-password"
    _request("PUT", url, token, {"type": "password", "value": PASSWORD, "temporary": False})


def _assign_roles(token: str, user_id: str, roles: tuple[str, ...]) -> None:
    reps = [
        json.loads(_request("GET", f"{KEYCLOAK_URL}/admin/realms/{REALM}/roles/{role}", token))
        for role in roles
    ]
    url = f"{KEYCLOAK_URL}/admin/realms/{REALM}/users/{user_id}/role-mappings/realm"
    _request("POST", url, token, reps)


def main() -> int:
    try:
        token = _admin_token()
    except urllib.error.URLError as error:
        print(
            f"não consegui falar com o Keycloak em {KEYCLOAK_URL}: {error}\n"
            "suba os serviços primeiro com `make dev-services`.",
            file=sys.stderr,
        )
        return 1

    roles_needed = {role for _, _, _, roles in SEED_USERS for role in roles}
    print(f"garantindo {len(roles_needed)} roles no realm {REALM}")
    for role in sorted(roles_needed):
        _ensure_role(token, role)

    print(f"semeando {len(SEED_USERS)} usuários (tenant {TENANT}, senha {PASSWORD})")
    for username, first, last, roles in SEED_USERS:
        user_id = _upsert_user(token, username, first, last)
        _set_password(token, user_id)
        _assign_roles(token, user_id, roles)

    print("pronto. logue no browser com qualquer um deles (senha local-dev-only).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
