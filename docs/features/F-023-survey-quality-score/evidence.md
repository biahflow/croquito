# F-023 — Evidência da fatia 1

Rodada de 2026-08-20 (sessão de especificação + execução). Baseline `88a717b`
(main limpa); integração direta na main (portão de quality desligado na rodada,
registrado em STATUS). Commits: spec `b0b3339`, T1 `1e1ac28`, T2 `1f7e80a`.

## Baseline

- T1 (antes de editar): `pytest tests/api tests/worker/test_cli.py
  tests/worker/test_dimension_closure.py` → 287 passed, 10 skipped.
- T2 (antes de editar): `npm --workspace @croquito/web run test` → 822 passed.
- Nenhuma falha preexistente registrada.

## BUILD REPORT — T1 (backend), executor implementador-opus

```text
Status: BUILD_COMPLETE
Files changed: services/api/src/croquito_api/{database.py, main.py,
  migrations/versions/0006_review_declared_chains.py (novo)};
  services/worker/src/croquito_worker/{cli.py, review_store.py, local_queue.py,
  review_refresh.py}; docs/architecture/API_CONTRACT.md;
  tests/api/{openapi.snapshot.json, test_api.py};
  tests/worker/{test_cli.py, test_review_refresh.py, test_trace_solve_worker.py};
  tests/e2e/test_full_flow.py
Validation executed: baseline acima; make check verde; uv run pytest final
  1788 passed/10 skipped; vitest 822; make openapi-snapshot com diff revisado
  + test_openapi_contract 11 passed; tests/api/test_migrations.py contra
  PostgreSQL 17 real (container descartável) 12 passed, incluindo o gate de
  drift da baseline e a adoção da 0006
Validation skipped: none
Unavailable capabilities: none
Assumptions: chain_id = sha256 canônico truncado (molde ap_/rd_); part_ids com
  pattern rd_ por item e chain_id sem pattern (id desconhecido é sempre 404);
  mensagem de stale é constante estável; a rota carrega trace_acceptance_json
  verbatim; DeclaredChainResponse expõe só os 6 campos do contrato
Remaining risks: custo de suggest_chains no request path cresce ~n^5 (12
  leituras→5 ms; 30→578 ms; 40→2,6 s) sem teto de leituras no pacote;
  Issue.id das issues de mismatch/stale nasce novo a cada leitura (resposta não
  é byte-idêntica entre GETs); server_default da 0006 é fase EXPAND; migração
  não aplicada em ambiente hospedado
Human decisions required: aplicar a 0006 no hosted antes/junto do deploy;
  aceitar os desvios conscientes (API_CONTRACT.md exigido pelo gate de rotas;
  carry-forward nos INSERTs SQL brutos do worker fora do mapa do contrato)
```

## BUILD REPORT — T2 (web), executor implementador-opus

```text
Status: BUILD_COMPLETE
Files changed: apps/web/src/{api.ts, labels.ts, labels.test.ts, CroquiApp.tsx,
  CroquiApp.test.tsx, styles.css}
Validation executed: baseline acima; vitest final 853 passed (+31); make check
  verde; make test verde (pytest 1788/10 + vitest 853); tipos conferidos contra
  o snapshot OpenAPI e main.py antes de digitar; inspeção visual do HTML
  renderizado da seção
Validation skipped: none
Unavailable capabilities: DOM/eventos no vitest (environment node, sem jsdom) —
  não é portão do projeto; fluxo testado pelas peças que o decidem
  (toggleChainTerm, chainDraftIssue, postReviewChains com fetch dublado,
  renderização estática) e CHAIN_INVALID pelo caminho real do AppAlert
Assumptions: elegível a termo = confirmada com value_si (autoridade continua o
  verify_chain do servidor); decimais exibidos como string do servidor
Remaining risks: autoria exibida em UTC como o registro de decisão; sem clique
  real de navegador (smoke headless local não estendido); lista pode ficar
  longa com 12 sugestões (teto do servidor), sem paginação
Human decisions required: aceitar os desvios conscientes (não arredondar os
  decimais do servidor — formatDecimal transformaria 0,015 em 0,02 e resíduo
  pequeno em 0,00; seção renderiza também quando há ≥3 confirmadas para o botão
  Declarar não ficar inalcançável; chainCorroboratedReadingIds recebe o review;
  chainStatusLabel e o rótulo "total/parcela da cadeia" por extenso para o
  aviso não depender de cor)
```

## Revisão (sessão principal, linha a linha)

- T1: diff completo lido (API, banco, migração, worker, CLI, testes);
  re-execução independente de `ruff check` + pytest das áreas tocadas (198
  testes, verde). Os três desvios conscientes foram julgados corretos e
  necessários — em particular o carry-forward nos INSERTs SQL brutos
  (`review_store.py`, `local_queue.py`), que o grep do Task Contract não
  alcançava e sem o qual a declaração evaporaria no refresh/trace-solve.
- T2: diff completo lido; re-execução independente de vitest (853) e
  `make check`. Os quatro desvios conscientes aceitos como melhorias.
- Nenhum PLAN_DEVIATION além dos desvios conscientes acima (escopo de arquivos
  da T1 ampliado por necessidade verificada; registrado nos relatórios).

## Riscos remanescentes e atos humanos pendentes

1. **Aplicar a migração 0006 no hosted** (junto das 0004/0005 ainda pendentes)
   antes ou junto do deploy — a coluna é NOT NULL e os INSERTs já a citam.
2. **Push/deploy** (dispara o pipeline) — ato do usuário.
3. Custo de `suggest_chains` com pacotes grandes: mitigação futura registrada
   (degradar `max_terms` acima de um teto de cotas), não implementada.
4. Aceitação real: declarar a cadeia do Guaxindiba (25,90 = 12,49+9,55+3,86)
   na revisão de uma rodada real e calibrar com V14–V17 via
   `croquito-demo check-chains` — insumo da fatia 2 (score agregado).
