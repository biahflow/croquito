# F-003 — Migração da medição para a API `/v1` autenticada

## Status

`READY_FOR_PLANNING`

> Esta feature esteve `BLOCKED` por [F-002](../F-002-medicao-v1-contract/feature.md) enquanto
> o desenho de rota, persistência e `base_version` não existia em fonte versionada: um plano
> produzido antes disso conteria decisões arquiteturais que o Planner não tem autoridade para
> tomar.
>
> O desbloqueio ocorreu em 2026-08-17, com a **aceitação humana** do
> [ADR-0028](../../adr/0028-medicao-na-api-v1-autenticada.md), que satisfaz o portão
> "aceitação do ADR de F-002 antes de qualquer planejamento". A entrada no
> [roadmap canônico](../../product/ROADMAP.md) existe desde a mesma data.
>
> Os demais portões humanos continuam de pé e são de **execução**, não de planejamento: a
> decisão sobre o runner de migrations revisadas antes de qualquer tabela (lacuna registrada
> no [ADR-0025](../../adr/0025-homologacao-em-gcp-cloud-run.md)), a remoção do serviço
> hospedado e da rota de borda, e qualquer alteração de realm Keycloak. Planejar é permitido;
> criar tabela, mexer em produção ou tocar realm, não.

## Priority

`HIGH` (seleção humana de 2026-08-17)

## Problem

A medição hospedada é uma ponte declarada, com custos aceitos e data de validade. O
[ADR-0026](../../adr/0026-medicao-hospedada-sessao-autenticada-minima.md) registra os
custos nominalmente: uma rodada por ambiente, no máximo uma instância porque o FUSE não
oferece lock, ausência de `base_version` real, rotas fora do API Contract, ausência de
multi-tenant, e "código que existirá até a sessão autenticada completa e depois será
removido — dívida com data".

Enquanto a ponte existe, o produto tem duas superfícies de contrato, uma delas exposta na
internet, e dois usuários simultâneos disputam o mesmo diretório. O
[ADR-0020](../../adr/0020-local-homologation-server-for-valuation.md) fixa a condição de
saída: "o dia em que houver segundo usuário é o dia da sessão autenticada".

## Desired Outcome

A medição opera sobre a API `/v1` autenticada, com tabelas próprias, concorrência otimista
real, contratos TypeScript gerados e papel `orcamentista` no realm — e o modo hospedado é
removido, não desativado.

## Scope

Conhecido hoje, sujeito ao desenho que F-002 produzir:

- Rotas `/v1` equivalentes às rotas de rodada do servidor de medição
  (`services/worker/src/croquito_worker/valuation/local_server.py`), conforme o inventário
  apurado por [F-002](../F-002-medicao-v1-contract/feature.md), com os mecanismos que toda
  rota `/v1` tem e as rotas locais não: `Idempotency-Key` em mutação e
  `application/problem+json` com `request_id` e `retryable`.
- Tabelas de medição em `services/api/src/croquito_api/database.py`, com `tenant_id`
  indexado e filtro por `principal.tenant_id` em toda query.
- `base_version` real substituindo a guarda por digest (`packet_sha256`,
  `assignments_sha256`), com `409 REVISION_CONFLICT` no lugar de `LOCAL_STATE_MOVED`.
- Papel `orcamentista` exigido pelas rotas de medição e presente no realm de
  desenvolvimento local (`keycloak/croquito-realm.json`), onde hoje não existe.
- Contratos TypeScript gerados para os modelos de `packages/valuation`, substituindo os
  tipos escritos à mão em `apps/medicao/src/api.ts`.
- Migração das telas e dos módulos puros de `apps/medicao` (`etapas.ts`, `format.ts`,
  `labels.ts`, `inclusoes.ts`, `busca.ts`, `execucao.ts`, `viewport.ts`) para consumir
  `/v1`, no destino que F-002 decidir.
- Despacho assíncrono da extração paga pelo mecanismo de fila da API, em lugar da thread
  do próprio servidor, respeitando a proibição de chamar modelo no request path.
- Remoção do modo hospedado: `create_hosted_app`, `hosted_auth.py`, o serviço Cloud Run
  `croquito-medicao-hml`, a rota de borda `/medicao/api/` e a variável
  `CROQUITO_IO_DIRECT_WRITE`.

## Out of Scope

- Reabrir qualquer decisão de F-002.
- Remover o servidor **local** do ADR-0020, que permanece válido para a máquina do
  operador e não foi substituído.
- Alterar regra de domínio, nome de artefato, gramática de fórmula ou semântica monetária:
  o [ADR-0016](../../adr/0016-valuation-bounded-context.md) fixa `TRUNC(x,2)` para dinheiro,
  `ROUND(x,2)` para quantidade e recusa `float` na fronteira.
- Ampliar funcionalidade da medição. Esta feature muda a superfície, não o produto.
- Deploy, mutação de infraestrutura ou remoção de serviço em ambiente remoto sem
  aprovação explícita.

## Acceptance Criteria

A serem completados após F-002. Os critérios abaixo são os que as fontes atuais já
sustentam:

- Toda rota nova aparece no [API Contract](../../architecture/API_CONTRACT.md) e no teste de
  compatibilidade de OpenAPI, se ele existir até então.
- Testes negativos exigidos pela
  [Testing Strategy](../../engineering/TESTING_STRATEGY.md) para cada rota nova: IDOR entre
  tenants, JWT inválido e expirado, idempotência, conflito de revisão, ownership e expiração
  de URL assinada.
- Objeto de outro tenant devolve `404`, não `403`, conforme o padrão já estabelecido em
  `tests/api/test_api.py`.
- Nenhuma decisão passa a aceitar `reviewer_id`, `reviewer_role`, `decided_at` ou
  `decision_id` no corpo da requisição.
- A tela não calcula dinheiro em nenhum ponto, conforme
  `apps/medicao/AGENTS.md` e ADR-0020.
- Os invariantes de recomputo permanecem com os mesmos códigos:
  `CALC_SUBTOTAL_MISMATCH`, `CALC_TOTAL_MISMATCH`, `LINE_TOTAL_MISMATCH`,
  `BULLETIN_TOTAL_MISMATCH`; decisão de takeoff permanece imutável com
  `TAKEOFF_ITEM_ALREADY_REVIEWED`.
- O guardrail `BULLETIN_PRICE_ORIGIN_FORBIDDEN` continua fechando a medição licitada.
- `make check` e `make test` passam, com o baseline de contagem de testes registrado antes
  da mudança.
- Ao fim, `grep -rn "hosted"` no escopo da medição não encontra código vivo do modo
  hospedado.

## Constraints

- Adicionar tabelas hoje passaria pelo bootstrap aditivo de
  `services/api/src/croquito_api/bootstrap.py`, que "não sabe alterar nem remover nada". O
  [ADR-0025](../../adr/0025-homologacao-em-gcp-cloud-run.md) registra o runner de migrations
  revisadas como requisito de produção **em falta**. Esta feature não pode introduzir
  esquema de produção sem que essa lacuna seja resolvida ou explicitamente aceita por
  decisão humana.
- Migrations em expand/contract com rolling deploy, conforme `services/api/AGENTS.md`.
- Deploy só pela esteira com imagem por SHA; não existe caminho a partir de máquina de
  desenvolvimento.
- A homologação real pela orçamentista sobre a rodada da Toca é ato humano pendente e não
  é substituída por esta migração.

## Dependencies

- [F-002](../F-002-medicao-v1-contract/feature.md) — bloqueante.
- Runner de migrations revisadas (lacuna do ADR-0025) — precisa de decisão antes de
  qualquer tabela de produção.
- Teste de compatibilidade de OpenAPI, exigido pela Testing Strategy e pelo API Contract e
  hoje ausente em `tests/api/`.
- Concessão do papel `orcamentista`, procedimento em
  [HML_KEYCLOAK](../../operations/HML_KEYCLOAK.md).

## Unknowns

As mesmas cinco desconhecidas de F-002, mais:

- Volume e esforço. Nenhuma fonte versionada quantifica este marco no estado atual; o
  "~7 rotas" do ADR-0020 antecede M6, M7 e M8.
- Se a remoção do modo hospedado ocorre no mesmo marco da migração ou em um posterior, e o
  que acontece com a rodada em homologação durante a transição.

## Risks

- Migrar superfície e mudar comportamento no mesmo trabalho, tornando a regressão
  indistinguível da mudança pretendida.
- Perder o carimbo de identidade do servidor ao reimplementar as rotas.
- Introduzir esquema sem caminho de migration revisada, exportando dívida para produção.
- Remover o modo hospedado antes de a orçamentista concluir a homologação em curso.
- Reescrever os módulos puros de `apps/medicao` em vez de movê-los, perdendo os testes que
  hoje os cobrem.

## Human Gates

- Aprovação deste contrato e criação de sua entrada no roadmap canônico.
- Aceitação do ADR de F-002 antes de qualquer planejamento.
- Decisão sobre o runner de migrations antes de qualquer tabela.
- Remoção do serviço hospedado e da rota de borda: mudança de produção.
- Alteração de realm Keycloak em qualquer ambiente compartilhado.

## References

- [Status](../../STATUS.md) — "Contexto de transição da medição hospedada"
- [ADR-0020](../../adr/0020-local-homologation-server-for-valuation.md),
  [ADR-0025](../../adr/0025-homologacao-em-gcp-cloud-run.md),
  [ADR-0026](../../adr/0026-medicao-hospedada-sessao-autenticada-minima.md)
- [Valuation Context](../../architecture/VALUATION_CONTEXT.md)
- [Definition of Done](../../engineering/DEFINITION_OF_DONE.md)
