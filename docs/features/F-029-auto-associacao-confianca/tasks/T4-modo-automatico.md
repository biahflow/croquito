# F-029 / T4 — Modo automático local atrás de flag

- Feature: [F-029](../feature.md) · Plano: [plan.md](../plan.md)
- Papel: builder · Esforço relativo: L · Depende de: T1, T2
- **GATE ANTES DE INICIAR: ADR-0041 aceito por ato humano.** Sem o aceite,
  esta task não é elegível — reportar bloqueio, não começar.

## Objetivo

Com `CROQUITO_AUTO_ASSOCIATION_ENABLED=true` E
`CROQUITO_AUTO_ASSOCIATION_THRESHOLD` explícito, leituras cuja
`reading_confidence` E `association_confidence` superam o threshold recebem
decisão de **ator-máquina** (forma exata definida pelo ADR-0041 aceito) e
associação explícita para o solver. Toda auto-decisão é retificável pelo
caminho existente e listada nominalmente na auditoria do export. Com a flag
desligada (default), comportamento bit a bit idêntico ao de hoje.

## Fontes a ler antes de editar

- `AGENTS.md` (raiz), `services/worker/AGENTS.md`, `services/api/AGENTS.md`.
- **ADR-0041 aceito** (`docs/adr/0041-*.md`) — a forma do ator-máquina
  (variante em `HumanDecision` ou tipo irmão) é decisão do ADR, não desta
  task.
- `services/worker/src/croquito_worker/review.py` — `HumanDecision` (72-97:
  `reviewer_role` é `Literal["engineer","architect","domain_reviewer"]`,
  `rectifies_decision_id`), `validate_review_state` (140-154, o invariante
  fail-closed), `rectify_reading_decisions` (472).
- `services/api/src/croquito_api/main.py` — `_reviewer_role(principal)`
  (1568-1577, papel SEMPRE derivado do JWT; auto-decisão não passa por aqui
  — vem do worker, nunca de request), rota de retificação (3345-…).
- `services/api/src/croquito_api/local_queue.py` — `_handle_upload`
  (753-918, onde a revisão nasce), `_handle_export` (966-1062).
- `services/worker/src/croquito_worker/providers.py` — 1790-1810 e
  2792-2810: padrão de leitura estrita de flag (só "true"/"false",
  valor inválido levanta `ValueError`; para ESTA flag, ausente = desligado —
  o oposto do braço OpenAI, e deliberado: ligar é ato declarado).
- `services/worker/src/croquito_worker/dxf.py` — `export_scene_package`
  (529) e a montagem de `auditoria.json`/`hipoteses.json` (541-554).
- `services/worker/src/croquito_worker/rectangle_solver.py` (192-211) e
  `tracing.py` — exigência de associação explícita.

## Escopo

1. Flags: `CROQUITO_AUTO_ASSOCIATION_ENABLED` (default false; leitura
   estrita) e `CROQUITO_AUTO_ASSOCIATION_THRESHOLD` (float 0–1; **sem
   default no código** — flag ligada sem threshold explícito é erro de
   configuração que impede o modo, nunca um valor inventado).
2. Extensão do modelo de decisão conforme o ADR-0041 aceito, com
   proveniência de ator-máquina inconfundível com decisão humana
   (identificador de sistema estável; `decided_at` do servidor).
3. Aplicação: no mesmo estágio que grava a revisão (worker), acima do
   threshold ⇒ decisão automática + `selected_associations` explícita.
   Auto-decisão NUNCA sobrescreve decisão humana existente e nunca decide
   leitura já decidida.
4. Retificação: o caminho existente (`rectifies_decision_id`, ADR-0022)
   cobre auto-decisão sem mudança de contrato da rota.
5. Auditoria: `auditoria.json` (e `hipoteses.json` quando aplicável) listam
   nominalmente cada leitura auto-decidida (id, valor, associação,
   confidências, threshold vigente). `SceneRevision.export_errors()` intacto.
6. Testes: flag desligada ⇒ nenhum efeito (teste explícito de equivalência);
   flag ligada em teste de API/worker ⇒ auto-decisão criada com ator-máquina,
   exceções continuam `review_required`, retificação de auto-decisão
   funciona, auditoria lista; e2e (`tests/e2e/test_full_flow.py`) ganha um
   cenário com flag ligada; smoke local roda com flag desligada sem
   diferença.

## Fora de escopo

Tela (T5); qualquer ambiente hospedado (a flag não entra em nenhum manifesto
de deploy); mudança no portão `export_errors()`; mudança nas rotas de
decisão/retificação além do necessário para exibir proveniência; escolha do
valor do threshold.

## Critérios de aceite

1. Flag desligada: `make test`, `make check`, `make smoke-local` e
   `tests/e2e/test_full_flow.py` sem NENHUMA mudança observável.
2. Flag ligada + threshold explícito, no stack local: PDF → job → revisão com
   auto-decisões de ator-máquina → exceções pendentes → aprovação → DXF
   auditado com a lista nominal das cotas automáticas.
3. Flag ligada sem threshold: recusa com erro de configuração claro; nada é
   decidido.
4. Auto-decisão não sobrescreve humano; retificação cobre auto-decisão;
   proveniência distingue os atores em qualquer resposta que exiba a decisão.
5. Drift de OpenAPI zero ou snapshot regenerado deliberadamente; se
   `croquito_core.models` precisar mudar (ex. Provenance para a auditoria),
   `make contracts` + justificativa no BUILD REPORT — risco previsto no
   plano.

## Baseline

`main` com T1+T2 integradas, portões verdes, ADR-0041 aceito. Falha nova em
área não tocada: parar e reportar.

## Validação (comandos reais)

```bash
make check
make test
uv run pytest tests/e2e/test_full_flow.py
make dev-services && make db-init && make dev-api   # stack local
CROQUITO_ALLOW_TEST_TOKENS=true make smoke-local     # flag DESLIGADA
# rodada manual com flag ligada, documentada no BUILD REPORT:
# CROQUITO_AUTO_ASSOCIATION_ENABLED=true CROQUITO_AUTO_ASSOCIATION_THRESHOLD=<valor de teste>
```

## Gates e relatório

ADR-0041 aceito é pré-condição de entrada. Ligar a flag fora do ambiente
local é proibido por contrato. Encerrar com `BUILD REPORT` completo
(`docs/engineering-os/agents/builder.md`).
