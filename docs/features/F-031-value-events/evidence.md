# F-031 — Evidência de execução (fatia 1)

Review Evidence Package da fatia 1, na forma do EOS. Fontes primárias: os BUILD
REPORTs de cada task (transcritos abaixo por referência), os commits da branch
`feat/f-031-value-events` e os logs de portões da sessão principal.

## Contexto de execução

- Worktree isolado `croquito-f031`, branch `feat/f-031-value-events` criada de
  `main@5148f80` em 2026-08-21. Decisão do usuário: incremento de plataforma,
  **sem merge/push nesta rodada** — não entra no MVP.
- Outra sessão trabalhava no checkout principal (F-029) durante toda a rodada;
  nada aqui tocou aquele checkout.
- Harness: Claude Code; escada de delegação `implementador-sonnet` (T1, T5) e
  `implementador-opus` (T2, T3, T4); spec e revisão linha a linha pela sessão
  principal (Fable).

## BASELINE

`make check` exit 0 e `make test` exit 0 no worktree limpo em `51d4138` (antes
de qualquer edição de código), registrados pela sessão principal em 2026-08-21
~08:00. Falhas preexistentes: nenhuma; skips esperados: testes de
`test_migrations.py` que exigem `CROQUITO_TEST_POSTGRES_URL`.

## Execução por task

### T1 — job_stage_events + custo no lineage (commit 429c518)

- Builder: implementador-sonnet. Status: BUILD_COMPLETE.
- Validação final: pytest verde, make check exit 0, make test exit 0.
- Achado da revisão da sessão principal: `created_at` do worker via
  `CURRENT_TIMESTAMP` divergiria em forma do da API. Corrigido com
  `bindparam(..., type_=DateTime(timezone=True))`; o builder provou
  empiricamente que a correção ingênua (bind cru) inverteria a divergência.
- Nota de processo: o builder encerrou um turno "aguardando teste em
  background"; a validação final foi cobrada e entregue em foreground.

### T2 — outbox domain_events + publicador + relay (commit 09a847a)

- Builder: implementador-opus. Status: BUILD_COMPLETE.
- Validação final: pytest 1825+853 verdes, make check exit 0, make test exit 0;
  EXTRA: migrações e INSERT cru validados contra PostgreSQL 17 descartável
  (container removido; nenhuma infra criada).
- Desvios conscientes aceitos na revisão: export.completed/failed emitidos
  (catálogo prevalece sobre enumeração do §2); duration_ms do export ausente
  (origem sem resolução confiável); failure_code de ai.call_executed reservado;
  CROQUITO_DOMAIN_EVENTS_TOPIC no settings do worker; delta negativo → None;
  domain_events.job_id sem FK (fato publicado não é filho do job).
- Revisão da sessão principal: aprovada sem achado novo.

### T3 — read-model de métricas (commit f820438)

- Builder: implementador-opus (retomado após queda de API sem perda de
  contexto). Status: BUILD_COMPLETE.
- Validação final: pytest 1840+853 verdes, make check exit 0, make test exit 0;
  snapshot OpenAPI regenerado deliberadamente, diff puramente aditivo.
- Achado do próprio builder, aceito na revisão: dedup de lineage por conteúdo
  canônico (sem ele, o custo publicaria N× o gasto real numa folha de N
  leituras). Trade-off declarado: duas execuções idênticas em todos os campos
  contam uma (subestimar > multiplicar).
- PLAN_DEVIATION documental: o caminho da rota no feature.md divergia do Task
  Contract (erro de spec da sessão principal); feature.md corrigido no mesmo
  commit — prevaleceu `GET /v1/jobs/{job_id}/metrics`.
- `decisions_total` = confirm+correct+reject; retificações contadas à parte
  (decisão do builder, aceita e documentada em PRIMARY_DECISION_ACTIONS).

### T5 — logging estruturado (commit a2ab427)

- Builder: implementador-sonnet. Status: BUILD_COMPLETE.
- Validação dupla: builder rodou pytest 2x, make check (mypy 212 arquivos,
  0 erros) e make test (1847+853) em foreground; a sessão principal re-rodou
  os três portões de forma independente — todos exit 0.
- Risco declarado e aceito: push_server.py não chama configure_logging por
  conta própria (fora do mapa do contrato).
- Nota de processo: novo turno encerrado "aguardando background" — a partir da
  T4, a cláusula de validação em foreground virou padrão no prompt de
  delegação.

### T4 — touch time real no web (commit e5d70bc)

- Builder: implementador-opus. Status: BUILD_COMPLETE.
- Validação final do builder: pytest 306/10 skips em tests/api, vitest 43
  arquivos/864 verdes, make check exit 0, make test exit 0 (1852+864);
  EXTRA: test_migrations.py contra PostgreSQL 17 do compose local — 12
  passed, 0 skipped, serviço derrubado ao fim.
- Desvios conscientes aceitos na revisão: (1) aprovação de cena sem
  interaction_ms (escapatória prevista no contrato: sem coluna natural, e o
  catálogo v1 de scene.approved.v1 não prevê o campo — confirmar na
  integração); (2) interaction_ms excluído do hash de idempotência
  (obrigatório para replay compatível; exclude=set() provado idêntico ao
  hash antigo nas demais rotas); (3) restart do cronômetro por troca de
  review_id em vez de zerar no submit (envio falho não perde a medida).
- Revisão da sessão principal: aprovada sem achado novo (cronômetro puro
  correto: monotônico, pausa em aba oculta, trecho negativo clampado,
  revisão aberta em segundo plano nasce pausada).
- Risco declarado: interaction_ms é autorrelato do cliente — serve a
  métrica, nunca a cobrança ou portão; o fio do hook em CroquiApp.tsx não
  tem teste automatizado (suíte da tela é SSR estático) — verificável no
  smoke headless local.

## Portões finais da fatia

`make check` e `make test` re-executados pela sessão principal na árvore
completa (6 commits, e5d70bc): exit 0 nos dois (pytest completo verde + vitest 43 arquivos/864 testes), 2026-08-21 ~13h.

## PLAN_DEVIATIONS

1. Caminho da rota de métricas (T3, acima) — resolvido na rodada.
2. Migração de interaction_ms movida da 0009 para a 0010 (plano aprovado
   previa na 0009; separar por task manteve migração e task 1:1).
3. ROADMAP/README de ADRs receberam linhas mínimas apesar do desvio declarado
   de "não tocar docs compartilhados": o check_docs exige feature no roadmap e
   ADR no índice — conflito de merge de uma linha aceito.

## Riscos remanescentes (consolidados dos reports)

- domain_events cresce sem poda (ADR-0042, consequência aceita).
- summary é O(n) em jobs do período, sem paginação; jobs sem índice composto
  (tenant_id, created_at).
- Chamada de provider que falhou não vira evento (custo publicado é o das
  concluídas).
- Cobertura automatizada do caminho SQL cru do worker na outbox é SQLite;
  PostgreSQL foi verificado manualmente na T2.
- Numeração de migrações 0008-0010 colide com a 0007 da F-029 — resolução no
  rebase de integração (documentado nos cabeçalhos das migrações).

## Decisões humanas pendentes (gates)

1. Aceite do ADR-0042 (Proposed; broker Pub/Sub decidido em sessão).
2. Integração da branch: rebase pós-F-029, renumeração de migrações, sync de
   ROADMAP/STATUS.
3. Provisionamento do tópico Pub/Sub como código e migrações 0008-0010 no
   hosted.
4. Push/deploy (fora desta rodada por decisão do usuário).
