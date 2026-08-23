"""Disponibilidade de jornada: ambiente, tenant e papel, sem depender de HTTP nem de banco.

As três perguntas compõem NESTA ordem (F-034):

```text
AMBIENTE  a jornada existe aqui?     ->  estado declarado em `ApiSettings`
TENANT    este cliente tem acesso?   ->  entitlement, consultado só quando `pilot`
PESSOA    este usuário tem o papel?  ->  papéis do JWT, exatamente como hoje
```

Este módulo é a parte pura: tipos, o mapa de prefixo -> jornada e as funções de decisão.
Ele não importa `config`, `database` nem `fastapi`, para que a regra seja testável sem
subir aplicação e para que `config` possa importá-lo sem ciclo.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping
from typing import Final, Literal, get_args

#: As jornadas que o produto liga e desliga por ambiente. A Plataforma não entra: ela já é
#: governada por papel (`platform_operator`) e é onde esta disponibilidade é administrada.
Journey = Literal["croqui", "medicao", "orcamento"]

#: `enabled` para todos os tenants; `pilot` só para quem tem entitlement; `disabled` para
#: ninguém. Três estados em vez de um booleano é o que evita o padrão falho de precisar
#: ligar a jornada para TODOS só para liberá-la a um cliente piloto.
JourneyAvailability = Literal["enabled", "pilot", "disabled"]

#: Ordem estável de apresentação: é a ordem em que `GET /v1/me` devolve `journeys`.
JOURNEYS: Final[tuple[Journey, ...]] = get_args(Journey)

JOURNEY_AVAILABILITIES: Final[tuple[JourneyAvailability, ...]] = get_args(JourneyAvailability)

#: Papéis profissionais que decidem leitura no croqui, em ordem de precedência — a mesma
#: lista que `_reviewer_role` (`main.py`) percorre para nomear o papel na decisão. Vive aqui
#: para que exista UMA fonte: a resolução da jornada e o portão da rota não podem discordar
#: sobre quem é revisor.
CROQUI_REVIEWER_ROLES: Final[tuple[str, ...]] = ("engineer", "architect", "domain_reviewer")

#: O papel exigido em toda rota de medição e de orçamento. É o valor de
#: `croquito_worker.valuation.round_view.REVIEWER_ROLE`, repetido aqui como literal para não
#: arrastar o pacote do worker para dentro de `config`; `tests/api/test_journeys.py` reprova
#: se os dois divergirem.
VALUATION_REVIEWER_ROLE: Final = "orcamentista"

#: Quem ASSINA o orçamento-base, e nunca quem o montou (ADR-0046, decisão 5). Na cadeia real
#: a assinatura é do gestor, do lado da prefeitura, e o nome do papel nomeia o ATO e não o
#: cargo, para não presumir que todo tenant tenha "gestor" na sua estrutura. É papel próprio
#: do orçamento: a medição não o conhece, porque lá quem mede e quem assina são a mesma
#: função profissional.
ESTIMATE_APPROVER_ROLE: Final = "aprovador"

#: Papéis que abrem cada jornada. Espelha o portão que cada rota já aplica hoje.
#:
#: `orcamento` tem DOIS porque a F-035 separou assinar de montar: o aprovador precisa abrir a
#: jornada para ver o que assina, e sem isso o papel novo não alcançaria a tela onde o ato
#: acontece. Abrir a jornada não é poder mutá-la — cada rota continua exigindo o seu papel, e
#: a mutação da cadeia segue exclusiva do `orcamentista`.
JOURNEY_ROLES: Final[Mapping[Journey, frozenset[str]]] = {
    "croqui": frozenset(CROQUI_REVIEWER_ROLES),
    "medicao": frozenset({VALUATION_REVIEWER_ROLE}),
    "orcamento": frozenset({VALUATION_REVIEWER_ROLE, ESTIMATE_APPROVER_ROLE}),
}

#: Prefixo de rota -> jornada dona. O portão entra UMA vez, por prefixo, e não nas 57 rotas:
#: replicar a checagem rota a rota é o jeito conhecido de uma rota nova nascer sem portão.
JOURNEY_ROUTE_PREFIXES: Final[Mapping[str, Journey]] = {
    "/v1/jobs": "croqui",
    "/v1/uploads": "croqui",
    "/v1/projects": "croqui",
    "/v1/valuation-rounds": "medicao",
    "/v1/estimate-rounds": "orcamento",
}

#: Prefixos que não pertencem a jornada nenhuma, declarados explicitamente. Não é a mesma
#: coisa que "não classificado": `unclassified_v1_paths` distingue os dois, e é isso que
#: impede uma rota futura de ficar sem portão por esquecimento.
JOURNEYLESS_ROUTE_PREFIXES: Final[frozenset[str]] = frozenset(
    # `/v1/surveys` é do app de campo (F-032), que não é uma das três jornadas da SPA e tem
    # papel próprio: a disponibilidade da F-034 não o governa. Se um dia governar, ele vira
    # jornada aqui — e essa é decisão humana, não consequência de merge.
    # `/v1/metrics` é o resumo do TENANT, atravessando as jornadas (F-031) — não pertence a
    # nenhuma. O que é de uma jornada já entra por ela: `/v1/jobs/{id}/metrics` cai em
    # `/v1/jobs` e portanto no croqui. E note que `/v1/meta` NÃO reivindica `/v1/metrics`:
    # é para isso que `_matches` casa segmento inteiro.
    {"/v1/me", "/v1/meta", "/v1/metrics", "/v1/schemas", "/v1/platform", "/v1/surveys"}
)


def _matches(path: str, prefix: str) -> bool:
    """Casa o prefixo inteiro, nunca um pedaço de segmento.

    Sem a segunda condição, `/v1/me` reivindicaria `/v1/metrics` e uma rota de jornada
    futura entraria como "fora de jornada" só por causa do nome.
    """
    return path == prefix or path.startswith(f"{prefix}/")


def journey_of_path(path: str) -> Journey | None:
    """Jornada dona do caminho; `None` para caminho fora de jornada OU não classificado.

    O portão trata os dois casos igual de propósito: ele não inventa recusa para um prefixo
    que ninguém classificou. Quem cobra a classificação é `unclassified_v1_paths`.
    """
    for prefix, journey in JOURNEY_ROUTE_PREFIXES.items():
        if _matches(path, prefix):
            return journey
    return None


def unclassified_v1_paths(paths: Iterable[str]) -> list[str]:
    """Caminhos `/v1/` que nenhum prefixo — de jornada ou fora dela — reivindica."""
    return sorted(
        {
            path
            for path in paths
            if path.startswith("/v1")
            and journey_of_path(path) is None
            and not any(_matches(path, prefix) for prefix in JOURNEYLESS_ROUTE_PREFIXES)
        }
    )


def journey_reachable(state: JourneyAvailability, *, entitled: bool) -> bool:
    """Ambiente e tenant: as duas perguntas que NÃO dependem do papel de quem chama.

    É o que o portão das rotas aplica. O papel continua sendo exigido por cada rota, com o
    código de erro que ela já usa hoje — a disponibilidade antecede o papel, não o
    substitui.
    """
    if state == "enabled":
        return True
    if state == "pilot":
        return entitled
    return False


def pilot_journeys(availability: Mapping[Journey, JourneyAvailability]) -> tuple[Journey, ...]:
    """Jornadas em `pilot`. Sem nenhuma, ninguém precisa consultar entitlement."""
    return tuple(journey for journey in JOURNEYS if availability[journey] == "pilot")


def resolve_journeys(
    *,
    availability: Mapping[Journey, JourneyAvailability],
    entitled: Collection[Journey],
    roles: Collection[str],
) -> tuple[Journey, ...]:
    """As três perguntas, na ordem, para um principal — o que `GET /v1/me` devolve.

    `entitled` já vem resolvido pelo chamador (só faz sentido para jornadas em `pilot`);
    esta função não fala com banco nenhum.
    """
    entitled_journeys = frozenset(entitled)
    principal_roles = frozenset(roles)
    return tuple(
        journey
        for journey in JOURNEYS
        if journey_reachable(availability[journey], entitled=journey in entitled_journeys)
        and bool(JOURNEY_ROLES[journey] & principal_roles)
    )
