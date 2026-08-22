"""Disponibilidade de jornada por ambiente e por tenant (F-034, fatia 1).

Três blocos, na ordem em que a regra é composta:

1. a decisão pura (`croquito_api.journeys`), sem app e sem banco;
2. a configuração, que recusa valor inválido na SUBIDA da aplicação;
3. o portão nas rotas e a lista resolvida em `GET /v1/me`.

O último teste do arquivo é o que impede uma rota futura de nascer sem portão: ele percorre
as rotas publicadas e reprova qualquer prefixo `/v1/` que ninguém tenha classificado — nem
como jornada, nem como explicitamente fora de jornada.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from croquito_api.config import ApiSettings, JourneyAvailabilitySettings
from croquito_api.database import Database, TenantJourneyEntitlementRecord
from croquito_api.journeys import (
    JOURNEY_ROLES,
    JOURNEY_ROUTE_PREFIXES,
    JOURNEYLESS_ROUTE_PREFIXES,
    JOURNEYS,
    Journey,
    JourneyAvailability,
    journey_of_path,
    pilot_journeys,
    resolve_journeys,
    unclassified_v1_paths,
)
from croquito_api.main import create_app
from croquito_api.openapi_export import snapshot_text
from croquito_core.errors import DomainValidationError
from croquito_core.ids import new_uuid7
from croquito_worker.valuation.round_view import REVIEWER_ROLE
from tests.fakes import FakeObjectStore

#: Uma rota real por jornada, escolhida entre as que NÃO exigem papel além do da jornada:
#: assim uma recusa observada é do portão de disponibilidade, e não de outra precondição.
ROUTE_OF: dict[Journey, str] = {
    "croqui": "/v1/projects",
    "medicao": "/v1/valuation-rounds",
    "orcamento": "/v1/estimate-rounds",
}

#: Papel que abre cada jornada hoje. Espelho de `JOURNEY_ROLES`, escrito à mão para que o
#: teste não passe por construção quando a regra mudar.
ROLE_OF: dict[Journey, str] = {
    "croqui": "engineer",
    "medicao": "orcamentista",
    "orcamento": "orcamentista",
}

ALL_ENABLED: dict[Journey, JourneyAvailability] = {journey: "enabled" for journey in JOURNEYS}


def _app(
    tmp_path: Path, *, journeys: JourneyAvailabilitySettings | None = None
) -> tuple[TestClient, Database]:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'journeys.db'}"
    database = Database(database_url)
    database.create_schema()
    settings = ApiSettings(
        database_url=database_url,
        artifact_bucket="croquito-test-artifacts",
        aws_region="sa-east-1",
        aws_endpoint_url="http://localhost:4566",
        queue_url=None,
        oidc_issuer=None,
        oidc_audience=None,
        web_origin="http://localhost:5173",
        allow_test_tokens=True,
        journeys=journeys or JourneyAvailabilitySettings(),
    )
    app = create_app(settings=settings, database=database)
    app.state.artifact_store = FakeObjectStore()
    return TestClient(app), database


def _headers(tenant: str, roles: str) -> dict[str, str]:
    return {"Authorization": f"Bearer test:{tenant}:reviewer:{roles}"}


def _only_disabled(journey: Journey) -> JourneyAvailabilitySettings:
    """Desliga uma jornada e deixa as outras duas como estão por padrão."""
    if journey == "croqui":
        return JourneyAvailabilitySettings(croqui="disabled")
    if journey == "medicao":
        return JourneyAvailabilitySettings(medicao="disabled")
    return JourneyAvailabilitySettings(orcamento="disabled")


def _grant(database: Database, *, tenant_id: str, journey: Journey, status: str = "ACTIVE") -> None:
    now = datetime.now(UTC)
    with database.sessions() as session:
        session.add(
            TenantJourneyEntitlementRecord(
                id=str(new_uuid7()),
                tenant_id=tenant_id,
                journey=journey,
                status=status,
                agreement_reference="ctr-piloto-v1",
                authorized_by="platform-operator",
                authorized_at=now,
                revoked_at=None if status == "ACTIVE" else now,
                updated_at=now,
            )
        )
        session.commit()


# --------------------------------------------------------------------------------------
# 1. A decisão pura


def test_resolucao_sem_configuracao_declarada_depende_so_do_papel() -> None:
    """O padrão `enabled` nas três reduz a resolução ao portão de papel que já existia."""
    assert resolve_journeys(availability=ALL_ENABLED, entitled=(), roles=["engineer"]) == (
        "croqui",
    )
    assert resolve_journeys(availability=ALL_ENABLED, entitled=(), roles=["architect"]) == (
        "croqui",
    )
    assert resolve_journeys(availability=ALL_ENABLED, entitled=(), roles=["domain_reviewer"]) == (
        "croqui",
    )
    assert resolve_journeys(availability=ALL_ENABLED, entitled=(), roles=["orcamentista"]) == (
        "medicao",
        "orcamento",
    )
    assert (
        resolve_journeys(availability=ALL_ENABLED, entitled=(), roles=["platform_operator"]) == ()
    )
    assert resolve_journeys(availability=ALL_ENABLED, entitled=(), roles=[]) == ()


def test_resolucao_compoe_ambiente_tenant_e_papel_nesta_ordem() -> None:
    """Ambiente derruba tenant e papel; tenant derruba papel. A ordem é o contrato."""
    availability: dict[Journey, JourneyAvailability] = {
        "croqui": "disabled",
        "medicao": "pilot",
        "orcamento": "enabled",
    }

    # Papel completo, mas o croqui não existe aqui e a medição não foi autorizada.
    assert resolve_journeys(
        availability=availability, entitled=(), roles=["engineer", "orcamentista"]
    ) == ("orcamento",)
    # Entitlement da medição abre a medição — e não abre o croqui, que é `disabled`.
    croqui_e_medicao: tuple[Journey, ...] = ("medicao", "croqui")
    assert resolve_journeys(
        availability=availability,
        entitled=croqui_e_medicao,
        roles=["engineer", "orcamentista"],
    ) == ("medicao", "orcamento")
    # Sem o papel, nem entitlement nem ambiente bastam.
    somente_medicao: tuple[Journey, ...] = ("medicao",)
    assert (
        resolve_journeys(availability=availability, entitled=somente_medicao, roles=["engineer"])
        == ()
    )


def test_pilot_journeys_lista_so_o_que_precisa_de_consulta() -> None:
    assert pilot_journeys(ALL_ENABLED) == ()
    assert pilot_journeys({**ALL_ENABLED, "croqui": "pilot", "medicao": "disabled"}) == ("croqui",)


def test_papeis_da_jornada_espelham_os_portoes_que_as_rotas_ja_aplicam() -> None:
    """Drift guard: esta feature NÃO muda quem autoriza o quê.

    `medicao` e `orcamento` usam o mesmo papel que `_require_valuation_reviewer` exige, cuja
    fonte é o worker; `croqui` usa os três papéis profissionais de `_reviewer_role`.
    """
    assert JOURNEY_ROLES["medicao"] == frozenset({REVIEWER_ROLE})
    assert JOURNEY_ROLES["orcamento"] == frozenset({REVIEWER_ROLE})
    assert JOURNEY_ROLES["croqui"] == frozenset({"engineer", "architect", "domain_reviewer"})


def test_prefixo_casa_segmento_inteiro_e_nunca_pedaco_de_nome() -> None:
    assert journey_of_path("/v1/jobs") == "croqui"
    assert journey_of_path("/v1/jobs/abc/review/decisions") == "croqui"
    assert journey_of_path("/v1/valuation-rounds/abc/bulletin") == "medicao"
    assert journey_of_path("/v1/estimate-rounds/abc/estimate") == "orcamento"
    # Fora de jornada e não classificado devolvem o mesmo `None`; quem separa os dois é
    # `unclassified_v1_paths`.
    assert journey_of_path("/v1/me") is None
    assert journey_of_path("/v1/inventada") is None
    # `/v1/me` não pode reivindicar um caminho que apenas começa com as mesmas letras.
    assert unclassified_v1_paths(["/v1/metricas"]) == ["/v1/metricas"]
    assert unclassified_v1_paths(["/v1/meta", "/v1/schemas/scene", "/v1/jobs"]) == []


# --------------------------------------------------------------------------------------
# 2. A configuração


def test_valor_invalido_de_jornada_recusa_na_subida_do_app(monkeypatch: Any) -> None:
    """Recusa ao construir a aplicação, não no primeiro request da jornada errada."""
    monkeypatch.setenv("CROQUITO_JOURNEY_CROQUI", "talvez")

    with pytest.raises(DomainValidationError) as error:
        create_app()

    assert "CROQUITO_JOURNEY_CROQUI" in error.value.errors[0]
    assert "talvez" in error.value.errors[0]


def test_ambiente_sem_variavel_declarada_deixa_as_tres_jornadas_ligadas(monkeypatch: Any) -> None:
    for journey in JOURNEYS:
        monkeypatch.delenv(f"CROQUITO_JOURNEY_{journey.upper()}", raising=False)

    resolved = JourneyAvailabilitySettings.from_environment()

    assert resolved == JourneyAvailabilitySettings()
    assert resolved.as_mapping() == ALL_ENABLED
    assert ApiSettings.from_environment().journeys == JourneyAvailabilitySettings()


def test_cada_jornada_le_a_propria_variavel(monkeypatch: Any) -> None:
    monkeypatch.setenv("CROQUITO_JOURNEY_CROQUI", "disabled")
    monkeypatch.setenv("CROQUITO_JOURNEY_MEDICAO", "pilot")
    monkeypatch.delenv("CROQUITO_JOURNEY_ORCAMENTO", raising=False)

    resolved = JourneyAvailabilitySettings.from_environment()

    assert resolved.state_of("croqui") == "disabled"
    assert resolved.state_of("medicao") == "pilot"
    assert resolved.state_of("orcamento") == "enabled"


# --------------------------------------------------------------------------------------
# 3. O portão nas rotas e a lista em `GET /v1/me`


@pytest.mark.parametrize("journey", JOURNEYS)
def test_sem_configuracao_declarada_a_rota_da_jornada_responde_como_hoje(
    tmp_path: Path, journey: Journey
) -> None:
    client, _ = _app(tmp_path)

    response = client.get(ROUTE_OF[journey], headers=_headers("tenant-a", ROLE_OF[journey]))

    assert response.status_code == 200


@pytest.mark.parametrize("journey", JOURNEYS)
def test_jornada_disabled_recusa_403_com_codigo_estavel_mesmo_com_papel_valido(
    tmp_path: Path, journey: Journey
) -> None:
    client, _ = _app(tmp_path, journeys=_only_disabled(journey))

    response = client.get(ROUTE_OF[journey], headers=_headers("tenant-a", ROLE_OF[journey]))

    assert response.status_code == 403
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "JOURNEY_UNAVAILABLE"
    # A recusa não vaza detalhe interno: nem o estado do ambiente, nem a existência de
    # piloto, nem resposta bruta de nada.
    assert "pilot" not in json.dumps(response.json())


def test_jornada_disabled_recusa_sem_consultar_o_banco(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`disabled` é definitivo: nenhum entitlement muda a resposta, então não se pergunta.

    Importa porque `disabled` é justamente o estado que segue recebendo tráfego — link
    antigo, aba aberta, bundle velho da SPA. Uma sessão aberta por requisição recusada é
    custo puro num caminho cujo resultado já está decidido, e some em silêncio se ninguém
    fixar.
    """
    client, database = _app(tmp_path, journeys=_only_disabled("medicao"))
    aberturas = 0
    original = database.sessions

    def contando(*args: Any, **kwargs: Any) -> Any:
        nonlocal aberturas
        aberturas += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(database, "sessions", contando)

    response = client.get(ROUTE_OF["medicao"], headers=_headers("tenant-a", ROLE_OF["medicao"]))

    assert response.status_code == 403
    assert response.json()["code"] == "JOURNEY_UNAVAILABLE"
    assert aberturas == 0


def test_jornada_disabled_some_da_lista_de_me(tmp_path: Path) -> None:
    client, _ = _app(tmp_path, journeys=JourneyAvailabilitySettings(croqui="disabled"))

    response = client.get("/v1/me", headers=_headers("tenant-a", "engineer,orcamentista"))

    assert response.status_code == 200
    assert response.json()["journeys"] == ["medicao", "orcamento"]


def test_piloto_abre_para_o_tenant_autorizado_e_recusa_igual_para_os_demais(
    tmp_path: Path,
) -> None:
    """Sem entitlement e com entitlement revogado precisam ser INDISTINGUÍVEIS de `disabled`.

    É o que impede alguém de descobrir, pela diferença entre duas recusas, que existe um
    piloto do qual o seu tenant não faz parte.
    """
    client, database = _app(tmp_path, journeys=JourneyAvailabilitySettings(croqui="pilot"))
    _grant(database, tenant_id="tenant-piloto", journey="croqui")
    _grant(database, tenant_id="tenant-revogado", journey="croqui", status="REVOKED")

    autorizado = client.get("/v1/projects", headers=_headers("tenant-piloto", "engineer"))
    sem_entitlement = client.get("/v1/projects", headers=_headers("tenant-sem", "engineer"))
    revogado = client.get("/v1/projects", headers=_headers("tenant-revogado", "engineer"))

    assert autorizado.status_code == 200
    assert sem_entitlement.status_code == 403
    assert revogado.status_code == 403
    assert sem_entitlement.json()["code"] == revogado.json()["code"] == "JOURNEY_UNAVAILABLE"
    assert sem_entitlement.json()["detail"] == revogado.json()["detail"]

    # A mesma composição aparece em `/v1/me`, e um tenant não vê a jornada do outro.
    entitled_me = client.get("/v1/me", headers=_headers("tenant-piloto", "engineer"))
    other_me = client.get("/v1/me", headers=_headers("tenant-sem", "engineer"))
    assert entitled_me.json()["journeys"] == ["croqui"]
    assert other_me.json()["journeys"] == []


def test_entitlement_de_uma_jornada_nao_abre_outra(tmp_path: Path) -> None:
    client, database = _app(
        tmp_path, journeys=JourneyAvailabilitySettings(croqui="pilot", medicao="pilot")
    )
    _grant(database, tenant_id="tenant-a", journey="croqui")

    croqui = client.get("/v1/projects", headers=_headers("tenant-a", "engineer,orcamentista"))
    medicao = client.get(
        "/v1/valuation-rounds", headers=_headers("tenant-a", "engineer,orcamentista")
    )

    assert croqui.status_code == 200
    assert medicao.status_code == 403
    assert medicao.json()["code"] == "JOURNEY_UNAVAILABLE"


def test_papel_ausente_continua_recusando_como_hoje(tmp_path: Path) -> None:
    """A lista de jornadas ANTECEDE o portão de papel; não o substitui.

    Com a jornada disponível, quem não tem o papel recebe o mesmo `403 FORBIDDEN` de sempre,
    e não o código novo — o motivo da recusa continua sendo o que realmente aconteceu.
    """
    client, _ = _app(tmp_path)

    response = client.get("/v1/valuation-rounds", headers=_headers("tenant-a", "engineer"))

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


def test_requisicao_sem_credencial_continua_401_mesmo_com_a_jornada_indisponivel(
    tmp_path: Path,
) -> None:
    """O portão não fabrica recusa de autenticação: sem principal não há tenant a resolver."""
    client, _ = _app(tmp_path, journeys=JourneyAvailabilitySettings(croqui="disabled"))

    response = client.get("/v1/projects")

    assert response.status_code == 401


def test_rotas_fora_de_jornada_seguem_abertas_com_tudo_desligado(tmp_path: Path) -> None:
    """`/v1/me` precisa responder justamente quando não há jornada nenhuma — é como a SPA
    descobre que não tem para onde ir. A plataforma também: ela administra o resto."""
    client, _ = _app(
        tmp_path,
        journeys=JourneyAvailabilitySettings(
            croqui="disabled", medicao="disabled", orcamento="disabled"
        ),
    )

    assert client.get("/healthz").status_code == 200
    assert client.get("/v1/meta").status_code == 200
    assert client.get("/v1/schemas/scene").status_code == 200
    me = client.get("/v1/me", headers=_headers("tenant-a", "engineer,orcamentista"))
    assert me.status_code == 200
    assert me.json()["journeys"] == []
    platform = client.get("/v1/platform/tenants", headers=_headers("platform", "platform_operator"))
    assert platform.status_code == 200


def test_toda_rota_v1_publicada_esta_classificada() -> None:
    """Reprova o prefixo `/v1/` que ninguém classificou — de jornada ou fora dela.

    É o teste que impede uma rota futura de nascer sem portão: publicá-la sem decidir a que
    jornada ela pertence passa a ser falha nomeada, e não silêncio.
    """
    document: dict[str, Any] = json.loads(snapshot_text())
    paths = [path for path in document["paths"] if isinstance(path, str)]

    assert unclassified_v1_paths(paths) == []
    # Nenhum prefixo classificado dos dois jeitos: um caminho não pode ser de jornada e
    # fora de jornada ao mesmo tempo.
    assert set(JOURNEY_ROUTE_PREFIXES) & JOURNEYLESS_ROUTE_PREFIXES == set()
