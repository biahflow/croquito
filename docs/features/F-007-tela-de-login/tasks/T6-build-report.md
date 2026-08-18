BUILD REPORT

Status: BUILD_COMPLETE
Files changed: docs/operations/HML.md; docs/operations/HML_KEYCLOAK.md; este relatório em docs/features/F-007-tela-de-login/tasks/T6-build-report.md.
Validation executed: BASELINE — make check (PASS). CHANGE — grep -rn "revisao" docs/ --include='*.md' (PASS; varredura registrada abaixo); git diff --check (PASS). `uv run python scripts/check_docs.py` sem cache alternativo foi inicialmente bloqueado por permissão no cache global do uv; a repetição com `UV_CACHE_DIR=/private/tmp/uv-cache-croquito` passou (PASS). FINAL — UV_CACHE_DIR=/private/tmp/uv-cache-croquito uv run python scripts/check_docs.py (PASS); UV_CACHE_DIR=/private/tmp/uv-cache-croquito make check (PASS).
Validation skipped: none
Unavailable capabilities: none
Assumptions: o cabeçalho pós-T1 de deploy/nginx.conf é a fonte do mapa operacional; a fumaça automatizada de quatro rotas permanece no escopo T5, então T6 documenta separadamente os curls manuais de / e /login; registros históricos, ADRs, contratos, planos, STATUS.md e ROADMAP.md foram preservados.
Remaining risks: none introduced by T6. A atualização da fumaça automatizada para / e /login permanece atribuída à T5, conforme o plano.
Human decisions required: none

Varredura `grep -rn "revisao" docs/ --include='*.md'` — cada ocorrência encontrada e decisão:

- `docs/adr/0032-porta-de-entrada-e-estado-sem-sessao.md:10,22,23,33,47,49,50,57,62,81,96,126,138,142` — preservadas; são o ADR aceito, contendo baseline, decisão, alternativas e riscos, e não devem ser reescritas.
- `docs/adr/0025-homologacao-em-gcp-cloud-run.md:45` — preservada; ADR aceito e registro arquitetural anterior.
- `docs/STATUS.md:874` — preservada; ocorrência datada no status derivado/histórico.
- `docs/features/F-001-roadmap-clarification/evidence.md:261` — preservada; evidência histórica.
- `docs/features/F-007-tela-de-login/tasks/T6-reconciliacao-docs.md:27,28` — preservadas; o próprio Task Contract define a varredura e o tratamento de registros históricos.
- `docs/features/F-007-tela-de-login/tasks/T3-build-report.md:52` — preservada; BUILD REPORT histórico.
- `docs/features/F-007-tela-de-login/tasks/T2-build-report.md:67,87` — preservadas; BUILD REPORT histórico.
- `docs/features/F-007-tela-de-login/tasks/T1-borda-login.md:19,26,29,48,49,51` — preservadas; Task Contract histórico/contratual da T1.
- `docs/features/F-007-tela-de-login/tasks/T1-build-report.md:8,11` — preservadas; BUILD REPORT histórico.
- `docs/features/F-007-tela-de-login/tasks/T5-rede-de-smoke.md:31` — preservada; Task Contract da T5.
- `docs/features/F-007-tela-de-login/tasks/T2-estado-login-e-rebote.md:20,22,36,41,42,43,96` — preservadas; Task Contract da T2.
- `docs/features/F-007-tela-de-login/plan.md:20,39,46,49,64,65,164,196` — preservadas; plano congelado da feature.
- `docs/features/F-007-tela-de-login/feature.md:31,69,70,80,81,118,121,122,124,126,141,143,148,184,193,199` — preservadas; Feature Contract aceito, incluindo baseline e decisões de rota.
- `docs/features/F-006-hml-conserto/evidence.md:15,306,321,409` — preservadas; evidência histórica de F-006.
- `docs/features/F-004-migrations-runner/evidence.md:156` — preservada; ocorrência em nome de teste dentro de evidência histórica, não afirmação de mapa.
- `docs/product/ROADMAP.md:73,275` — preservadas; registro de seleção/baseline e evidência datada, além de ROADMAP explicitamente fora do escopo T6.
- `docs/operations/HML.md:24,25,220,228,232,242` — reconciliadas para o mapa vigente: `/login` é a porta, `/revisao/` continua a SPA, os assets permanecem sob `/revisao/` e `/medicao/` continua redirecionando para `/revisao/?rodada=`.

O acesso operacional vigente em `docs/operations/HML_KEYCLOAK.md` também foi corrigido de `/revisao/` para `/login`; por isso a ocorrência antiga não permanece na varredura pós-mudança.
