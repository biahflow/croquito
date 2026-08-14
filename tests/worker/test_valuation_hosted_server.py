"""Modo hospedado do servidor de medição (ADR-0026): quem entra, e quem fica no artefato.

Estes testes cobrem a única coisa que o modo hospedado muda — a porta de entrada e a
ORIGEM da identidade —, sobre o mesmo diretório de rodada que o CLI produz. O domínio, os
nomes de artefato e as guardas continuam sendo os de `test_valuation_local_server.py`; o
que se prova aqui é que:

- rota de rodada sem sessão válida não é atendida, e nada é gravado;
- papel `orcamentista` é exigido antes da rota;
- o `reviewer_id` que sobra no artefato é o do TOKEN, e não uma constante do processo —
  dois tokens diferentes deixam duas assinaturas diferentes na mesma rodada;
- `GET /healthz` responde sem token (é o probe do host), e é a ÚNICA rota assim;
- o servidor local continua sem autenticação nenhuma (regressão do ADR-0020).

Nada aqui toca a rede: o validador compartilhado (`croquito_core.oidc`) é substituído por
uma tabela de tokens sintéticos, então nenhum JWKS é buscado e nenhum realm precisa existir.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any, Final

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from croquito_core.oidc import OidcIdentity, OidcTokenError
from croquito_worker.valuation import hosted_auth
from croquito_worker.valuation import local_server as local_server_module
from croquito_worker.valuation.cli import TAKEOFF_PACKET_FILENAME
from croquito_worker.valuation.cli import main as cli_main
from croquito_worker.valuation.hosted_auth import (
    HOSTED_OIDC_AUDIENCE_ENV,
    HOSTED_OIDC_ISSUER_ENV,
    HOSTED_WEB_ORIGINS_ENV,
    REVIEWER_ROLE,
    HostedSettings,
    hosted_settings_from_env,
    parse_web_origins,
)
from croquito_worker.valuation.local_server import create_hosted_app, create_local_app

ISSUER: Final = "https://croquito-hml.exemplo.test/auth/realms/croquito"
AUDIENCE: Final = "croquito-web"
WEB_ORIGIN: Final = "https://croquito-hml.exemplo.test"

ORCAMENTISTA_TOKEN: Final = "token-da-orcamentista"
SEM_ROTULO_TOKEN: Final = "token-sem-preferred-username"
OUTRA_ORCAMENTISTA_TOKEN: Final = "token-da-segunda-orcamentista"
PROJETISTA_TOKEN: Final = "token-de-quem-nao-decide-medicao"

ORCAMENTISTA: Final = "orcamentista.hml"
OUTRA_ORCAMENTISTA: Final = "segunda.orcamentista.hml"
SUBJECT_SEM_ROTULO: Final = "0192f7d6-0000-7000-8000-00000000abcd"

_IDENTITIES: Final[Mapping[str, OidcIdentity]] = {
    ORCAMENTISTA_TOKEN: OidcIdentity(
        subject="0192f7d6-0000-7000-8000-000000000001",
        tenant_id="tenant-hml",
        roles=frozenset({REVIEWER_ROLE, "reviewer"}),
        preferred_username=ORCAMENTISTA,
    ),
    OUTRA_ORCAMENTISTA_TOKEN: OidcIdentity(
        subject="0192f7d6-0000-7000-8000-000000000002",
        tenant_id="tenant-hml",
        roles=frozenset({REVIEWER_ROLE}),
        preferred_username=OUTRA_ORCAMENTISTA,
    ),
    SEM_ROTULO_TOKEN: OidcIdentity(
        subject=SUBJECT_SEM_ROTULO,
        tenant_id="tenant-hml",
        roles=frozenset({REVIEWER_ROLE}),
        preferred_username=None,
    ),
    PROJETISTA_TOKEN: OidcIdentity(
        subject="0192f7d6-0000-7000-8000-000000000003",
        tenant_id="tenant-hml",
        roles=frozenset({"reviewer", "approver"}),
        preferred_username="projetista.hml",
    ),
}


def _fake_validate_bearer_token(
    token: str, *, issuer: str, audience: str, jwks_client: Any = None
) -> OidcIdentity:
    """Validador sintético: mesma assinatura, mesma recusa, zero rede.

    Ele confere issuer e audience de propósito — é a prova de que o app os fixou na subida
    do processo e não os aceita da requisição.
    """
    assert issuer == ISSUER
    assert audience == AUDIENCE
    found = _IDENTITIES.get(token)
    if found is None:
        raise OidcTokenError()
    return found


def _snapshot(root: Path) -> dict[str, str]:
    """Digest de cada arquivo da rodada; recusa de sessão não pode mover nenhum deles."""
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.iterdir())
        if path.is_file()
    }


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _first_confirmable_item(client: TestClient) -> str:
    """Id do primeiro item proposto com quantidade lida; confirmar esse não exige nota."""
    packet = client.get("/takeoff", headers=_bearer(ORCAMENTISTA_TOKEN)).json()["packet"]
    return str(
        next(
            item["id"]
            for item in packet["items"]
            if item["status"] == "proposed" and item["quantity"] is not None
        )
    )


@pytest.fixture(autouse=True)
def offline_validator(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hosted_auth, "validate_bearer_token", _fake_validate_bearer_token)


@pytest.fixture(scope="module")
def prepared_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Rodada recém-extraída pelo comando real do CLI, sem nenhuma decisão."""
    root = tmp_path_factory.mktemp("valuation-hosted")
    assert cli_main(["extract-legend", "--output", str(root)]) == 0
    return root


@pytest.fixture
def root(prepared_root: Path, tmp_path: Path) -> Path:
    destination = tmp_path / "run"
    shutil.copytree(prepared_root, destination)
    return destination


@pytest.fixture
def hosted_app(root: Path) -> FastAPI:
    return create_hosted_app(root, issuer=ISSUER, audience=AUDIENCE, allowed_origins=[WEB_ORIGIN])


@pytest.fixture
def client(hosted_app: FastAPI) -> Iterator[TestClient]:
    yield TestClient(hosted_app)


def test_a_route_without_a_bearer_token_is_refused_and_writes_nothing(
    client: TestClient, root: Path
) -> None:
    before = _snapshot(root)

    response = client.get("/state")

    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "HOSTED_SESSION_REQUIRED"
    assert _snapshot(root) == before


def test_a_token_the_validator_refuses_is_an_invalid_session(client: TestClient) -> None:
    response = client.get("/state", headers=_bearer("token-que-nao-existe"))

    assert response.status_code == 401
    assert response.json()["code"] == "HOSTED_SESSION_INVALID"


def test_another_authorization_scheme_is_not_a_session(client: TestClient) -> None:
    response = client.get("/state", headers={"Authorization": "Basic bXVpdG8tc2VjcmV0bw=="})

    assert response.status_code == 401
    assert response.json()["code"] == "HOSTED_SESSION_REQUIRED"


def test_a_valid_token_without_the_reviewer_role_is_refused(client: TestClient, root: Path) -> None:
    """Quem revisa cena não decide medição: o papel é a separação, e ela é 403, não 401."""
    before = _snapshot(root)

    response = client.get("/state", headers=_bearer(PROJETISTA_TOKEN))

    assert response.status_code == 403
    payload = response.json()
    assert payload["code"] == "HOSTED_ROLE_REQUIRED"
    assert payload["details"]["required_role"] == REVIEWER_ROLE
    assert _snapshot(root) == before


def test_a_refusal_never_echoes_the_token(client: TestClient) -> None:
    response = client.get("/state", headers=_bearer("token-que-nao-existe"))

    assert "token-que-nao-existe" not in response.text


def test_the_state_reports_the_reviewer_of_the_token(client: TestClient) -> None:
    payload = client.get("/state", headers=_bearer(ORCAMENTISTA_TOKEN)).json()

    assert payload["reviewer_id"] == ORCAMENTISTA
    assert payload["reviewer_role"] == REVIEWER_ROLE
    assert payload["takeoff"]["review_status"] == "review_required"


def test_the_subject_is_the_reviewer_when_the_token_has_no_label(client: TestClient) -> None:
    payload = client.get("/state", headers=_bearer(SEM_ROTULO_TOKEN)).json()

    assert payload["reviewer_id"] == SUBJECT_SEM_ROTULO


def test_each_decision_is_stamped_with_the_reviewer_of_its_own_token(
    client: TestClient, root: Path
) -> None:
    """O carimbo é da REQUISIÇÃO, não do processo: duas sessões, duas assinaturas."""
    packet = client.get("/takeoff", headers=_bearer(ORCAMENTISTA_TOKEN)).json()
    identifiers = [item["id"] for item in packet["packet"]["items"] if item["quantity"]]
    digest = str(packet["packet_sha256"])

    first = client.post(
        "/takeoff/decisions",
        json={"item_id": identifiers[0], "action": "confirm", "base_packet_sha256": digest},
        headers=_bearer(ORCAMENTISTA_TOKEN),
    )
    assert first.status_code == 200, first.json()
    second = client.post(
        "/takeoff/decisions",
        json={
            "item_id": identifiers[1],
            "action": "confirm",
            "base_packet_sha256": str(first.json()["packet_sha256"]),
        },
        headers=_bearer(OUTRA_ORCAMENTISTA_TOKEN),
    )
    assert second.status_code == 200, second.json()

    written = json.loads((root / TAKEOFF_PACKET_FILENAME).read_text(encoding="utf-8"))
    decisions = {
        item["id"]: item["decision"] for item in written["items"] if item["decision"] is not None
    }
    assert decisions[identifiers[0]]["reviewer_id"] == ORCAMENTISTA
    assert decisions[identifiers[1]]["reviewer_id"] == OUTRA_ORCAMENTISTA
    assert {decision["reviewer_role"] for decision in decisions.values()} == {REVIEWER_ROLE}


def test_the_body_still_refuses_identity_and_timestamp(client: TestClient, root: Path) -> None:
    """A identidade passou a vir do token; ela continua não vindo do corpo."""
    before = _snapshot(root)
    digest = client.get("/takeoff", headers=_bearer(ORCAMENTISTA_TOKEN)).json()["packet_sha256"]

    response = client.post(
        "/takeoff/decisions",
        json={
            "item_id": _first_confirmable_item(client),
            "action": "confirm",
            "base_packet_sha256": digest,
            "reviewer_id": "quem-eu-quiser",
        },
        headers=_bearer(ORCAMENTISTA_TOKEN),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "LOCAL_REQUEST_INVALID"
    assert _snapshot(root) == before


def test_the_health_probe_answers_without_a_token(client: TestClient) -> None:
    """O probe do host não tem sessão — e não recebe dado nenhum da rodada."""
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_the_health_probe_is_the_only_route_without_a_session(
    hosted_app: FastAPI, client: TestClient
) -> None:
    """Varredura pelo contrato publicado, e não por uma lista escrita à mão.

    A dependency mora no roteador das rotas de rodada, então uma rota nova registrada fora
    dele nasceria aberta. Este teste é o guarda disso: toda rota do OpenAPI é chamada sem
    token, e a única que pode responder é a prova de vida.
    """
    paths: dict[str, dict[str, object]] = hosted_app.openapi()["paths"]
    assert "/healthz" in paths

    for path, operations in paths.items():
        for method in operations:
            response = client.request(method.upper(), path)
            expected = 200 if path == "/healthz" else 401
            assert response.status_code == expected, (method, path)


def test_the_preflight_allows_the_configured_origin_and_the_session_header(
    client: TestClient,
) -> None:
    """CORS quase decorativo em HML (a tela é same-origin), configurado assim mesmo."""
    response = client.options(
        "/takeoff/decisions",
        headers={
            "Origin": WEB_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == WEB_ORIGIN
    assert "authorization" in response.headers["access-control-allow-headers"].lower()


def test_a_missing_round_directory_refuses_before_any_route(tmp_path: Path) -> None:
    with pytest.raises(Exception) as raised:
        create_hosted_app(
            tmp_path / "nao-existe",
            issuer=ISSUER,
            audience=AUDIENCE,
            allowed_origins=[WEB_ORIGIN],
        )

    assert getattr(raised.value, "code", None) == "LOCAL_ROOT_MISSING"


def test_the_local_app_keeps_no_session_and_no_health_probe(root: Path) -> None:
    """Regressão do ADR-0020: o modo local não ganhou porta de entrada nem rota nova."""
    local = TestClient(create_local_app(root, "orcamentista-de-teste"))

    state = local.get("/state")

    assert state.status_code == 200
    assert state.json()["reviewer_id"] == "orcamentista-de-teste"
    assert local.get("/healthz").status_code == 404


# --------------------------------------------------------------------------------------
# Configuração do modo pelo ambiente e pela linha de comando
# --------------------------------------------------------------------------------------


def test_the_settings_come_from_the_environment_with_the_origins_split(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(HOSTED_OIDC_ISSUER_ENV, ISSUER)
    monkeypatch.setenv(HOSTED_OIDC_AUDIENCE_ENV, AUDIENCE)
    monkeypatch.setenv(HOSTED_WEB_ORIGINS_ENV, f"{WEB_ORIGIN}, https://outra.exemplo.test ")

    settings = hosted_settings_from_env()

    assert settings == HostedSettings(
        issuer=ISSUER,
        audience=AUDIENCE,
        allowed_origins=(WEB_ORIGIN, "https://outra.exemplo.test"),
    )


def test_a_missing_environment_variable_refuses_with_the_names_that_are_missing() -> None:
    with pytest.raises(Exception) as raised:
        hosted_settings_from_env({HOSTED_OIDC_ISSUER_ENV: ISSUER})

    assert getattr(raised.value, "code", None) == "HOSTED_CONFIG_MISSING"
    assert getattr(raised.value, "details", {})["missing_env"] == [
        HOSTED_OIDC_AUDIENCE_ENV,
        HOSTED_WEB_ORIGINS_ENV,
    ]


def test_an_origin_list_of_only_separators_counts_as_absent() -> None:
    assert parse_web_origins(" , ,") == ()

    with pytest.raises(Exception) as raised:
        hosted_settings_from_env(
            {
                HOSTED_OIDC_ISSUER_ENV: ISSUER,
                HOSTED_OIDC_AUDIENCE_ENV: AUDIENCE,
                HOSTED_WEB_ORIGINS_ENV: " , ,",
            }
        )

    assert getattr(raised.value, "details", {})["missing_env"] == [HOSTED_WEB_ORIGINS_ENV]


def _refusal(captured: str) -> dict[str, object]:
    payload: dict[str, object] = json.loads(captured.strip().splitlines()[-1])
    return payload


def test_serve_hosted_without_the_environment_refuses_to_start(
    root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for name in (HOSTED_OIDC_ISSUER_ENV, HOSTED_OIDC_AUDIENCE_ENV, HOSTED_WEB_ORIGINS_ENV):
        monkeypatch.delenv(name, raising=False)

    assert cli_main(["serve", "--root", str(root), "--hosted"]) == 2

    assert _refusal(capsys.readouterr().out)["refused"] == "HOSTED_CONFIG_MISSING"


def test_serve_hosted_refuses_the_reviewer_flag(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Duas origens de identidade no mesmo comando deixaria em aberto qual delas carimba."""
    assert cli_main(["serve", "--root", str(root), "--hosted", "--reviewer", "alguem"]) == 2

    assert _refusal(capsys.readouterr().out)["refused"] == "SERVE_REVIEWER_FORBIDDEN"


def test_serve_local_still_requires_the_reviewer_flag(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli_main(["serve", "--root", str(root)]) == 2

    assert _refusal(capsys.readouterr().out)["refused"] == "SERVE_REVIEWER_REQUIRED"


def test_serve_hosted_announces_the_mode_and_does_not_warn_about_exposure(
    root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """O aviso `LOCAL_SERVER_EXPOSED` é sobre porta sem autenticação; o hospedado tem uma."""
    monkeypatch.setenv(HOSTED_OIDC_ISSUER_ENV, ISSUER)
    monkeypatch.setenv(HOSTED_OIDC_AUDIENCE_ENV, AUDIENCE)
    monkeypatch.setenv(HOSTED_WEB_ORIGINS_ENV, WEB_ORIGIN)
    served: list[tuple[str, int]] = []
    monkeypatch.setattr(
        local_server_module,
        "run_local_server",
        lambda _application, *, host, port: served.append((host, port)),
    )

    assert (
        cli_main(["serve", "--root", str(root), "--hosted", "--host", "0.0.0.0", "--port", "8080"])
        == 0
    )

    output = capsys.readouterr().out
    assert "LOCAL_SERVER_EXPOSED" not in output
    banner = json.loads(output.strip().splitlines()[-1])
    assert banner["mode"] == "hosted"
    assert banner["oidc_issuer"] == ISSUER
    assert banner["oidc_audience"] == AUDIENCE
    assert banner["web_origins"] == [WEB_ORIGIN]
    assert "reviewer_id" not in banner
    assert served == [("0.0.0.0", 8080)]


def test_serve_local_still_warns_when_the_port_leaves_the_machine(
    root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        local_server_module, "run_local_server", lambda _application, *, host, port: None
    )

    assert (
        cli_main(["serve", "--root", str(root), "--reviewer", "alguem", "--host", "0.0.0.0"]) == 0
    )

    lines = capsys.readouterr().out.strip().splitlines()
    warning = json.loads(lines[-2])
    banner = json.loads(lines[-1])
    assert warning["warning"] == "LOCAL_SERVER_EXPOSED"
    assert banner["mode"] == "local"
    assert banner["reviewer_id"] == "alguem"
