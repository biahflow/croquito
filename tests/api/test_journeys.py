"""Disponibilidade de jornada por ambiente e por tenant (F-034, fatias 1 e 2).

Quatro blocos, na ordem em que a regra é composta:

1. a decisão pura (`croquito_api.journeys`), sem app e sem banco;
2. a configuração, que recusa valor inválido na SUBIDA da aplicação;
3. o portão nas rotas e a lista resolvida em `GET /v1/me`;
4. a administração do entitlement pela plataforma (T3): conceder, revogar e listar.

O teste que fecha o bloco 3 é o que impede uma rota futura de nascer sem portão: ele
percorre as rotas publicadas e reprova qualquer prefixo `/v1/` que ninguém tenha
classificado — nem como jornada, nem como explicitamente fora de jornada.
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
    ESTIMATE_APPROVER_ROLE,
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
    """Drift guard: quem ABRE a jornada é exatamente quem alguma rota dela deixa entrar.

    `medicao` tem um papel só, o de `_require_valuation_reviewer`, cuja fonte é o worker;
    `croqui` usa os três papéis profissionais de `_reviewer_role`.

    `orcamento` tem DOIS desde a F-035: `_require_estimate_reader` deixa o `aprovador` ler as
    rotas do orçamento, porque quem assina precisa ver o que assina. Abrir a jornada não é
    poder mutá-la — quem cobra isso rota a rota é
    `test_com_so_o_papel_aprovador_a_leitura_passa_e_toda_mutacao_recusa`.
    """
    assert JOURNEY_ROLES["medicao"] == frozenset({REVIEWER_ROLE})
    assert JOURNEY_ROLES["orcamento"] == frozenset({REVIEWER_ROLE, ESTIMATE_APPROVER_ROLE})
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


# --------------------------------------------------------------------------------------
# 4. A administração do entitlement pela plataforma (T3)


#: Caminho da rota que concede e revoga; o par (tenant, jornada) vive na URL, nunca no corpo.
def _entitlement_path(tenant_id: str, journey: Journey) -> str:
    return f"/v1/platform/tenants/{tenant_id}/journey-entitlements/{journey}"


def _operator(key: str) -> dict[str, str]:
    """Cabeçalhos de um `platform_operator` agindo sobre OUTRO tenant, com chave por gesto."""
    return {**_headers("platform", "platform_operator"), "Idempotency-Key": key}


def test_conceder_registra_contrato_autor_e_data_e_aparece_na_listagem(tmp_path: Path) -> None:
    client, _ = _app(tmp_path, journeys=JourneyAvailabilitySettings(orcamento="pilot"))

    granted = client.put(
        _entitlement_path("tenant-scalle", "orcamento"),
        headers=_operator("conceder-orcamento"),
        json={"enabled": True, "agreement_reference": "contrato 05/2024 — aditivo 3"},
    )

    assert granted.status_code == 200
    body = granted.json()
    assert body["tenant_id"] == "tenant-scalle"
    assert body["journey"] == "orcamento"
    assert body["enabled"] is True
    assert body["agreement_reference"] == "contrato 05/2024 — aditivo 3"
    assert body["authorized_by"] == "reviewer"
    assert body["authorized_at"] is not None
    assert body["revoked_at"] is None
    # Nada de linha bruta de banco: `id` e `updated_at` não são superfície pública.
    assert set(body) == {
        "tenant_id",
        "journey",
        "enabled",
        "agreement_reference",
        "authorized_by",
        "authorized_at",
        "revoked_at",
    }

    listing = client.get("/v1/platform/journeys", headers=_headers("platform", "platform_operator"))
    assert listing.status_code == 200
    listed = listing.json()["entitlements"]
    assert len(listed) == 1
    # `authorized_at` é comparado sem o fuso: `DateTime(timezone=True)` volta ingênuo do
    # SQLite dos testes e com fuso do PostgreSQL hospedado. É a mesma característica do
    # entitlement de IA, e não uma diferença desta rota.
    assert {key: value for key, value in listed[0].items() if key != "authorized_at"} == {
        key: value for key, value in body.items() if key != "authorized_at"
    }
    assert listed[0]["authorized_at"].rstrip("Z") == body["authorized_at"].rstrip("Z")


def test_revogar_carimba_a_data_e_mantem_a_linha_na_lista(tmp_path: Path) -> None:
    """Revogar NÃO apaga: a linha fica, com o contrato e o autor do ato original."""
    client, _ = _app(tmp_path, journeys=JourneyAvailabilitySettings(orcamento="pilot"))
    client.put(
        _entitlement_path("tenant-scalle", "orcamento"),
        headers=_operator("conceder"),
        json={"enabled": True, "agreement_reference": "piloto interno"},
    )

    revoked = client.put(
        _entitlement_path("tenant-scalle", "orcamento"),
        headers=_operator("revogar"),
        json={"enabled": False},
    )

    assert revoked.status_code == 200
    assert revoked.json()["enabled"] is False
    assert revoked.json()["revoked_at"] is not None
    assert revoked.json()["agreement_reference"] == "piloto interno"
    assert revoked.json()["authorized_by"] == "reviewer"

    listing = client.get("/v1/platform/journeys", headers=_headers("platform", "platform_operator"))
    assert [entry["tenant_id"] for entry in listing.json()["entitlements"]] == ["tenant-scalle"]
    assert listing.json()["entitlements"][0]["enabled"] is False


@pytest.mark.parametrize("state", ["enabled", "disabled"])
def test_conceder_fora_do_piloto_recusa_com_codigo_estavel_e_nao_grava_nada(
    tmp_path: Path, state: JourneyAvailability
) -> None:
    """Autorizar onde não tem efeito é recusado ANTES de escrever.

    Sem esta recusa o registro criado passaria a valer sozinho, sem ato novo, no dia em que
    o ambiente declarasse a jornada `pilot`.
    """
    client, database = _app(tmp_path, journeys=JourneyAvailabilitySettings(medicao=state))

    refused = client.put(
        _entitlement_path("tenant-scalle", "medicao"),
        headers=_operator("conceder-fora-do-piloto"),
        json={"enabled": True, "agreement_reference": "contrato 05/2024"},
    )

    assert refused.status_code == 409
    assert refused.headers["content-type"].startswith("application/problem+json")
    assert refused.json()["code"] == "JOURNEY_NOT_IN_PILOT"
    # A tela compõe a frase por extenso a partir destes dois fatos declarados.
    assert refused.json()["detail"]["details"] == {"journey": "medicao", "state": state}
    with database.sessions() as session:
        assert session.query(TenantJourneyEntitlementRecord).count() == 0
    listing = client.get("/v1/platform/journeys", headers=_headers("platform", "platform_operator"))
    assert listing.json()["entitlements"] == []


def test_revogar_continua_permitido_depois_que_a_jornada_saiu_do_piloto(tmp_path: Path) -> None:
    """A recusa é só de conceder.

    Uma autorização criada durante o piloto precisa poder ser encerrada depois que a
    jornada foi liberada para todos — senão ela ficaria ativa esperando o próximo piloto.
    """
    client, database = _app(tmp_path, journeys=JourneyAvailabilitySettings(orcamento="pilot"))
    client.put(
        _entitlement_path("tenant-scalle", "orcamento"),
        headers=_operator("conceder"),
        json={"enabled": True, "agreement_reference": "piloto interno"},
    )
    # O ambiente liberou a jornada para todos depois do piloto.
    liberado, _ = _app(tmp_path, journeys=JourneyAvailabilitySettings(orcamento="enabled"))

    revoked = liberado.put(
        _entitlement_path("tenant-scalle", "orcamento"),
        headers=_operator("revogar-fora-do-piloto"),
        json={"enabled": False},
    )

    assert revoked.status_code == 200
    assert revoked.json()["enabled"] is False
    with database.sessions() as session:
        record = session.query(TenantJourneyEntitlementRecord).one()
        assert record.status == "REVOKED"


def test_conceder_sem_referencia_de_contrato_recusa_sem_gravar(tmp_path: Path) -> None:
    client, database = _app(tmp_path, journeys=JourneyAvailabilitySettings(orcamento="pilot"))

    refused = client.put(
        _entitlement_path("tenant-scalle", "orcamento"),
        headers=_operator("conceder-sem-contrato"),
        json={"enabled": True},
    )

    assert refused.status_code == 422
    assert refused.json()["code"] == "AGREEMENT_REFERENCE_REQUIRED"
    with database.sessions() as session:
        assert session.query(TenantJourneyEntitlementRecord).count() == 0


def test_revogar_o_que_nunca_foi_concedido_e_404(tmp_path: Path) -> None:
    client, _ = _app(tmp_path, journeys=JourneyAvailabilitySettings(orcamento="pilot"))

    response = client.put(
        _entitlement_path("tenant-sem-nada", "orcamento"),
        headers=_operator("revogar-inexistente"),
        json={"enabled": False},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_administrar_jornada_exige_platform_operator(tmp_path: Path) -> None:
    """`403` para quem não tem o papel — na leitura e na escrita, inclusive no próprio tenant."""
    client, database = _app(tmp_path, journeys=JourneyAvailabilitySettings(orcamento="pilot"))

    listing = client.get("/v1/platform/journeys", headers=_headers("tenant-scalle", "orcamentista"))
    write = client.put(
        _entitlement_path("tenant-scalle", "orcamento"),
        headers={
            **_headers("tenant-scalle", "orcamentista"),
            "Idempotency-Key": "tentativa-sem-papel",
        },
        json={"enabled": True, "agreement_reference": "contrato 05/2024"},
    )

    assert listing.status_code == 403
    assert listing.json()["code"] == "FORBIDDEN"
    assert write.status_code == 403
    assert write.json()["code"] == "FORBIDDEN"
    with database.sessions() as session:
        assert session.query(TenantJourneyEntitlementRecord).count() == 0


def test_conceder_exige_chave_de_idempotencia_e_repete_a_mesma_resposta(tmp_path: Path) -> None:
    client, database = _app(tmp_path, journeys=JourneyAvailabilitySettings(orcamento="pilot"))
    path = _entitlement_path("tenant-scalle", "orcamento")
    payload = {"enabled": True, "agreement_reference": "contrato 05/2024"}

    sem_chave = client.put(path, headers=_headers("platform", "platform_operator"), json=payload)
    primeira = client.put(path, headers=_operator("mesma-chave"), json=payload)
    replay = client.put(path, headers=_operator("mesma-chave"), json=payload)

    assert sem_chave.status_code == 400
    assert primeira.status_code == 200
    assert replay.json() == primeira.json()
    with database.sessions() as session:
        assert session.query(TenantJourneyEntitlementRecord).count() == 1


def test_listagem_mostra_o_estado_das_tres_jornadas_e_nao_oferece_como_edita_lo(
    tmp_path: Path,
) -> None:
    """O estado é leitura: existe na resposta e não existe rota publicada que o escreva."""
    client, _ = _app(
        tmp_path,
        journeys=JourneyAvailabilitySettings(
            croqui="disabled", medicao="enabled", orcamento="pilot"
        ),
    )

    listing = client.get("/v1/platform/journeys", headers=_headers("platform", "platform_operator"))

    assert listing.status_code == 200
    assert listing.json()["journeys"] == [
        {"journey": "croqui", "state": "disabled"},
        {"journey": "medicao", "state": "enabled"},
        {"journey": "orcamento", "state": "pilot"},
    ]
    document: dict[str, Any] = json.loads(snapshot_text())
    escritas = {
        method
        for path, operations in document["paths"].items()
        if path == "/v1/platform/journeys"
        for method in operations
    }
    assert escritas == {"get"}


def test_listagem_ordena_por_tenant_e_jornada(tmp_path: Path) -> None:
    client, database = _app(
        tmp_path, journeys=JourneyAvailabilitySettings(croqui="pilot", orcamento="pilot")
    )
    _grant(database, tenant_id="tenant-z", journey="orcamento")
    _grant(database, tenant_id="tenant-a", journey="orcamento")
    _grant(database, tenant_id="tenant-a", journey="croqui")

    listing = client.get("/v1/platform/journeys", headers=_headers("platform", "platform_operator"))

    assert [(entry["tenant_id"], entry["journey"]) for entry in listing.json()["entitlements"]] == [
        ("tenant-a", "croqui"),
        ("tenant-a", "orcamento"),
        ("tenant-z", "orcamento"),
    ]


def test_conceder_e_revogar_mudam_o_que_o_tenant_ve_em_me(tmp_path: Path) -> None:
    """Ponta a ponta: o ato da plataforma é o que abre e fecha a jornada para o cliente."""
    client, _ = _app(tmp_path, journeys=JourneyAvailabilitySettings(orcamento="pilot"))
    cliente = _headers("tenant-scalle", "orcamentista")

    antes = client.get("/v1/me", headers=cliente)
    assert antes.json()["journeys"] == ["medicao"]
    assert client.get("/v1/estimate-rounds", headers=cliente).status_code == 403

    client.put(
        _entitlement_path("tenant-scalle", "orcamento"),
        headers=_operator("abrir"),
        json={"enabled": True, "agreement_reference": "contrato 05/2024"},
    )

    depois = client.get("/v1/me", headers=cliente)
    assert depois.json()["journeys"] == ["medicao", "orcamento"]
    assert client.get("/v1/estimate-rounds", headers=cliente).status_code == 200

    client.put(
        _entitlement_path("tenant-scalle", "orcamento"),
        headers=_operator("fechar"),
        json={"enabled": False},
    )

    revogado = client.get("/v1/me", headers=cliente)
    assert revogado.json()["journeys"] == ["medicao"]
    assert client.get("/v1/estimate-rounds", headers=cliente).status_code == 403


def test_jornada_desconhecida_na_rota_nao_chega_a_gravar(tmp_path: Path) -> None:
    client, database = _app(tmp_path, journeys=JourneyAvailabilitySettings(orcamento="pilot"))

    response = client.put(
        "/v1/platform/tenants/tenant-scalle/journey-entitlements/plataforma",
        headers=_operator("jornada-inexistente"),
        json={"enabled": True, "agreement_reference": "contrato 05/2024"},
    )

    assert response.status_code == 422
    with database.sessions() as session:
        assert session.query(TenantJourneyEntitlementRecord).count() == 0
