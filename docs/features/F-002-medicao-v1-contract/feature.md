# F-002 — Contrato `/v1` da medição

## Status

`READY_FOR_PLANNING`

> Contrato aprovado pela decisão humana de 2026-08-17, registrada na
> [seção 10 de evidence.md de F-001](../F-001-roadmap-clarification/evidence.md). A entrada
> correspondente no [roadmap canônico](../../product/ROADMAP.md) ainda não existe e é
> pré-requisito para o planejamento: sem ela, o Planner não tem fonte canônica de seleção.

## Priority

`HIGH` (seleção humana de 2026-08-17)

## Problem

O [Status](../../STATUS.md) declara a medição hospedada como **ponte, não destino**, e
nomeia o destino: "migração da medição para a API `/v1` autenticada (tabelas próprias,
contratos TS gerados, concorrência otimista real, papel `orcamentista` no realm)". Nenhuma
fonte versionada descreve **como** essa API deve ser.

Um Planner que recebesse hoje "migre a medição para `/v1`" não teria como decompor o
trabalho sem tomar decisões arquiteturais que não lhe pertencem. As lacunas são concretas
e verificáveis:

- Não há desenho de rota. O vocabulário proibido do
  [ADR-0016](../../adr/0016-valuation-bounded-context.md) exclui `Job`, o que impede
  pendurar a medição em `/v1/jobs/{job_id}/...` — o padrão da maioria das rotas atuais de
  `services/api`. Há precedentes versionados de raiz não-`Job` no mesmo arquivo
  (`/v1/projects` e `/v1/platform/tenants/{tenant_id}/...`), mas nenhum foi decidido para a
  medição: não existe decisão sobre entidade raiz, path base ou nome.
- Não há esquema relacional. Hoje o estado da rodada é um diretório de artefatos JSON
  (`services/worker/src/croquito_worker/valuation/cli.py`); nenhuma fonte diz se
  `TakeoffPacket` e `CodeAssignmentSet` viram coluna JSON imutável, no padrão de
  `ReviewRevisionRecord`, ou tabelas normalizadas.
- Não há semântica de `base_version` para a medição. O
  [ADR-0026](../../adr/0026-medicao-hospedada-sessao-autenticada-minima.md) declara que a
  lacuna pertence a este marco, e nada define se a versão pertence à rodada, ao pacote de
  takeoff ou a cada artefato.
- O pipeline de contratos TS é mono-modelo: `croquito_core.schema_export` exporta apenas
  `SceneRevision`, e `packages/valuation` não expõe nenhum JSON Schema. Os ~40 tipos de
  `apps/medicao/src/api.ts` são escritos à mão.
- Não há decisão sobre onde as telas passam a viver. O
  [ADR-0020](../../adr/0020-local-homologation-server-for-valuation.md) rejeitou `apps/web`
  no M6 pelo estado daquele app naquele momento, não como regra permanente.

Especificar a implementação antes dessas decisões seria `Invented Specification`.

## Desired Outcome

Um ADR aceito e uma seção versionada do [API Contract](../../architecture/API_CONTRACT.md)
que, juntos, tornem a migração planejável: um Planner consegue decompor o trabalho e um
Builder consegue implementar uma rota sem escolher desenho.

## Scope

- Redigir um **rascunho de ADR** que decida, com alternativas consideradas e
  consequências: entidade raiz e path base das rotas de medição sob `/v1`; forma de
  persistência dos artefatos de rodada; semântica de `base_version`; mapeamento dos
  códigos de erro locais (`LOCAL_STATE_MOVED`, `HOSTED_*`, `TAKEOFF_*`, `CALC_*`) para os
  códigos obrigatórios do API Contract; tratamento de imagem binária (`GET /images/plate`,
  `GET /images/overlay`) sob a regra de URL assinada; conversão do `POST /plates`
  multipart para o padrão presign; despacho assíncrono da extração paga; escopo de tenant
  para a rodada; e destino das telas de `apps/medicao`.
- Redigir a seção de medição do API Contract correspondente às decisões do rascunho,
  incluindo os códigos de erro na tabela de códigos obrigatórios.
- Propor o desenho de extensão de `croquito_core.schema_export` e `packages/contracts` de
  mono-modelo para múltiplos modelos, sem implementá-lo.
- Registrar o inventário verificável das rotas de rodada do servidor de medição — as
  declaradas no `router` de
  `services/worker/src/croquito_worker/valuation/local_server.py`, excluído o `/healthz` do
  app hospedado, que é sonda de saúde e não rota de domínio — e, para cada uma, a rota `/v1`
  proposta ou a decisão de não migrá-la. A contagem é apurada pelo Builder a partir do
  arquivo, não afirmada por este contrato.
- Declarar a condição de remoção do modo hospedado, que o
  [ADR-0026](../../adr/0026-medicao-hospedada-sessao-autenticada-minima.md) descreve como
  "dívida com data".

## Out of Scope

- Aceitar o ADR. Um agente redige o rascunho; a aceitação é ato humano.
- Qualquer alteração em código, esquema de banco, rota, realm Keycloak, infraestrutura,
  CI/CD ou estado remoto.
- Implementar rota, tabela, migration, contrato TS gerado ou tela.
- Alterar o status de qualquer ADR existente.
- Reabrir decisões já fixadas: o contexto delimitado do
  [ADR-0016](../../adr/0016-valuation-bounded-context.md), a identidade OIDC portável do
  [ADR-0011](../../adr/0011-oidc-portable-identity.md), a separação de papéis do
  [ADR-0026](../../adr/0026-medicao-hospedada-sessao-autenticada-minima.md) e o
  [ADR-0020](../../adr/0020-local-homologation-server-for-valuation.md), que permanece
  válido para a máquina do operador.
- Decidir prioridade de produto ou selecionar qualquer outro item.

## Acceptance Criteria

- O rascunho de ADR existe em `docs/adr/`, no formato de
  [ADR_TEMPLATE](../../templates/ADR_TEMPLATE.md), com status `Proposed` e nunca
  `Accepted` por agente.
- Cada uma das nove decisões listadas no Scope aparece nomeadamente no rascunho, com
  alternativas consideradas e consequências. Uma decisão sem alternativa registrada
  reprova o critério.
- Cada rota de rodada declarada no `router` de `local_server.py` aparece no inventário
  exatamente uma vez, com o caminho de arquivo e a linha de origem citados, e com destino
  declarado. O inventário registra sua própria contagem apurada e a confere contra o arquivo;
  nenhuma contagem é herdada de outro documento.
- Cada código de erro proposto aparece na seção "Códigos obrigatórios" do API Contract.
- Nenhuma decisão do rascunho contradiz o ADR-0011, o ADR-0016, o ADR-0020 ou o ADR-0026;
  onde houver tensão aparente, ela é registrada como tensão, não resolvida em silêncio.
- `make check` passa, incluindo `python scripts/check_docs.py` — links e blocos de código
  fechados.
- `git status --short` mostra alteração somente em `docs/`.
- O rascunho declara explicitamente o que **não** decide, e nomeia cada item como decisão
  ainda pendente.

## Constraints

- ADR aceito é imutável; uma decisão que contrarie um ADR aceito exige novo ADR com
  `Supersedes`, conforme o [AGENTS.md](../../../AGENTS.md) da raiz.
- O vocabulário proibido do ADR-0016 (`Measurement*`, `*Budget*`, `Job`) vale para os
  nomes de rota, tabela e modelo propostos.
- O carimbo de identidade é sempre do servidor; o corpo da requisição recusa
  `reviewer_id`, `reviewer_role`, `decided_at` e `decision_id`.
- Tenant deriva do JWT, nunca do corpo.
- Nenhum número de esforço, prazo ou contagem de rota pode ser afirmado sem fonte
  versionada. O "~7 rotas" do ADR-0020 antecede M6, M7 e M8 e não descreve o estado atual.

## Dependencies

- [F-001](../F-001-roadmap-clarification/feature.md) — precisa estar versionada e com suas
  decisões humanas registradas antes que este contrato receba entrada de roadmap, para não
  misturar escopos no mesmo diff de `docs/product/ROADMAP.md`.
- [ADR-0011](../../adr/0011-oidc-portable-identity.md),
  [ADR-0016](../../adr/0016-valuation-bounded-context.md),
  [ADR-0020](../../adr/0020-local-homologation-server-for-valuation.md),
  [ADR-0025](../../adr/0025-homologacao-em-gcp-cloud-run.md),
  [ADR-0026](../../adr/0026-medicao-hospedada-sessao-autenticada-minima.md)
- [API Contract](../../architecture/API_CONTRACT.md),
  [Valuation Context](../../architecture/VALUATION_CONTEXT.md)
- `services/api/src/croquito_api/{main.py,database.py,auth.py}`,
  `services/worker/src/croquito_worker/valuation/local_server.py`,
  `packages/core/src/croquito_core/schema_export.py`

## Unknowns

Registradas como desconhecidas, não respondidas por este contrato:

- Se a migração cria as rotas de medição dentro de `apps/web`, mantém `apps/medicao`
  apontando para `/v1`, ou cria um terceiro app.
- Como as rodadas existentes no bucket de homologação passam ao banco: importação,
  reprocessamento, ou nenhuma migração de dados.
- O que acontece com o CLI de medição, hoje único caminho do refino pago de código.
- Se a medição usa `croquito-web` como client/audience OIDC ou ganha client próprio.
- Se o papel `orcamentista`, hoje presente apenas em `keycloak/croquito-hml-realm.json`,
  entra no realm de desenvolvimento local nesta feature ou em outra.

## Risks

- Decidir por conveniência de implementação uma questão que pertence ao contexto
  delimitado, em especial o nome da entidade raiz.
- Produzir um ADR que descreva a implementação em vez da decisão, deixando o Planner sem
  fronteira e o Builder sem liberdade legítima.
- Tratar o "~7 rotas" do ADR-0020 como estimativa corrente.
- Registrar como decidido algo que o rascunho apenas presume.

## Human Gates

- Aceitação do ADR. Um agente nunca move um ADR de `Proposed` para `Accepted`.
- Aprovação deste contrato e criação de sua entrada no roadmap canônico.
- Decisão sobre o destino das telas de `apps/medicao`, que altera a fronteira entre apps.
- Decisão sobre escopo de tenant da rodada, que tem consequência de isolamento de dados.

## References

- [Project Context](../../engineering/PROJECT_CONTEXT.md)
- [Status](../../STATUS.md) — "Contexto de transição da medição hospedada"
- [Roadmap](../../product/ROADMAP.md) — item 22 do inventário F-001
- [Testing Strategy](../../engineering/TESTING_STRATEGY.md),
  [Definition of Done](../../engineering/DEFINITION_OF_DONE.md)
