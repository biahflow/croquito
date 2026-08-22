# F-034 T1 — Disponibilidade resolvida no servidor

feature_id: F-034
task_id: T1
parent_plan: ../plan.md
role: builder

## Goal

Resolver, no servidor, quais jornadas cada principal pode abrir — ambiente, depois tenant,
depois papel — e aplicar essa resolução nas rotas e em `GET /v1/me`.

## Scope

1. **Estados por jornada, no ambiente.** Três valores: `enabled`, `pilot`, `disabled`.
   Jornadas: `croqui`, `medicao`, `orcamento`. Lidos em `config.py` (prefixo `CROQUITO_`,
   como todo o resto). Padrão `enabled`. Valor inválido **recusa na subida**, não no
   primeiro request — o molde é `auto_association_mode()`, chamado no construtor de
   `LocalQueueWorker` justamente para configuração incoerente não virar ciclo de reentrega.
2. **Entitlement por tenant e jornada.** Tabela nova no molde exato de
   `TenantAiProcessingEntitlementRecord` (`database.py:88-102`): `id`, `tenant_id`,
   `journey`, `status`, `agreement_reference`, `authorized_by`, `authorized_at`,
   `revoked_at`, `updated_at`; unicidade por (`tenant_id`, `journey`). Consultada **apenas**
   quando o estado do ambiente é `pilot`.
3. **Migração `0008`**, forward-only, no molde da `0004_estimate_round_target.py`
   (`downgrade()` levanta `NotImplementedError`). Última migração na `main` é a `0007`.
4. **Resolução.** Função pura de decisão, testável sem app: dado o estado do ambiente, o
   entitlement e os papéis, devolve a lista de jornadas. Papéis (espelham o backend de
   hoje, não invente): `croqui` exige `engineer`, `architect` **ou** `domain_reviewer`
   (`main.py:1612`); `medicao` e `orcamento` exigem `orcamentista`
   (`_require_valuation_reviewer`, `main.py:1649-1661`).
5. **Portão nas rotas, em UM lugar.** Mapa de prefixo → jornada, aplicado na montagem do
   app: `/v1/jobs`, `/v1/uploads`, `/v1/projects` → `croqui`; `/v1/valuation-rounds` →
   `medicao`; `/v1/estimate-rounds` → `orcamento`. Fora de jornada, explicitamente:
   `/v1/me`, `/v1/meta`, `/v1/schemas`, `/v1/platform`. Jornada indisponível recusa `403`
   com código estável novo, em `application/problem+json`, como o resto da API.
   **Não** replique a checagem nas 57 rotas.
6. **`GET /v1/me`** (`main.py:2846-2857`) passa a devolver `journeys`, já resolvidas.
   Mantém o que devolve hoje.
7. **Snapshot de OpenAPI** regenerado (`make openapi-snapshot`) — `/v1/me` mudou de forma.

## Out of scope

- Qualquer arquivo em `apps/web/` (é a T2).
- A tela de administração do entitlement — é a fatia 2, `BLOCKED` por gate de design.
- Criar rota para conceder/revogar entitlement (idem fatia 2).
- Mudar quais papéis autorizam o quê.
- Qualquer regra de preço, cascata, medição ou cena.

## Acceptance criteria

1. Ambiente sem nenhuma variável declarada: comportamento idêntico ao de hoje, provado por
   teste que estende os existentes sem enfraquecê-los.
2. `disabled`: rota da jornada recusa `403` com o código estável mesmo com papel válido, e
   `journeys` não a lista.
3. `pilot`: tenant com entitlement `ACTIVE` abre; tenant sem entitlement, e tenant com
   entitlement revogado, recebem a **mesma** recusa da `disabled`.
4. Papel ausente continua recusando como hoje — a lista de jornadas não substitui o portão
   de papel de cada rota, ela o antecede.
5. Valor inválido de configuração recusa na subida do app.
6. Teste que percorre as rotas publicadas e falha se algum prefixo `/v1/` não estiver
   classificado (nem como jornada, nem como fora de jornada). É o que impede uma rota
   futura de nascer sem portão.
7. `make check` e `make test` verdes; goldens intocados.

## Pitfalls

- `tenant_id` vem **sempre** do JWT, nunca do corpo (`auth.py`).
- Não faça parsing de string de exceção: erros de domínio são estruturados
  (`DomainValidationError`) e os da API usam códigos estáveis.
- A recusa não pode vazar resposta bruta nem detalhe interno.
- `Decimal`/dinheiro não entram aqui; nada nesta task toca valor.
- O snapshot de OpenAPI é ato deliberado: regenere pelo alvo do Makefile, não à mão.

## Validation

```bash
make check
make test
uv run pytest tests/api -q
```

## Required capabilities

READ, WRITE (apenas o escopo acima), VALIDATE.
