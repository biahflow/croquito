# T1 — Borda: a raiz leva a /login e /login serve a SPA

Task Contract no formato do [template global](../../../engineering-os/templates/task.md),
derivado do [plano válido](../plan.md). Autossuficiente: assuma o Core (pinado em
`docs/engineering-os/`), este contrato e o repositório — nada mais.

## Identity

```text
feature_id: F-007
task_id: T1
parent_plan: docs/features/F-007-tela-de-login/plan.md
depends_on: none
```

## Goal

`GET /` na borda responde `302` para `/login`; `GET /login` serve o `index.html` da SPA com
os assets resolvendo sob `/revisao/assets/`; e o cabeçalho de `deploy/nginx.conf` descreve o
mapa novo. É o critério de aceite 1 do [Feature Contract](../feature.md) e o D1/D2 do
[ADR-0032](../../../adr/0032-porta-de-entrada-e-estado-sem-sessao.md).

## Scope

- `deploy/nginx.conf`, somente:
  - Linhas 64–67: `location = / { return 302 /revisao/; }` passa a `return 302 /login;`
    (redirect **relativo** — `absolute_redirect off` já está declarado no arquivo porque o
    Cloud Run entrega HTTP na 8080; um `Location` absoluto é o defeito conhecido).
  - Location nova `location = /login` servindo `/revisao/index.html` com as mesmas políticas
    do bloco existente de `index.html` (linhas 137–141): `no-store` e
    `X-Content-Type-Options`, espelhadas, não inventadas.
  - Cabeçalho de rotas (linhas 1–29): reconciliado com o mapa novo (`/` → `/login`,
    `/login` → SPA), mantendo o tom e o formato do comentário existente.

## Out of Scope

- `/api/`, `/auth/`, `/medicao/`, blocos de cache de assets, favicon, fallback 404 — intocados.
- Qualquer arquivo de `apps/web` (o estado `/login` da SPA é a task T2).
- `docs/operations/HML.md` (é a task T6).
- `scripts/smoke_hml.py` (é a task T5).
- Se notar outros pontos do nginx a melhorar, anote no relatório; não execute.

## Acceptance Criteria

1. No container da borda construído do repo, `curl -si http://localhost:<porta>/` responde
   `302` com `Location: /login` relativo (checado pela execução do curl).
2. `curl -si http://localhost:<porta>/login` responde `200` com o HTML da SPA cujos assets
   apontam para `/revisao/assets/` (checado por grep no corpo da resposta).
3. `curl -si http://localhost:<porta>/revisao/` continua servindo a SPA e
   `curl -si http://localhost:<porta>/medicao/` continua respondendo `302` para
   `/revisao/?rodada=` (regressão; checado pela execução).
4. O cabeçalho do arquivo descreve o mapa novo (checado por leitura).
5. `make check` verde (checado pela execução).

## Validation

```text
baseline: make check → verde no commit base deste contrato; docker build do web
          funcional (o workflow deploy-hml já o constrói)
required: full:  make check
          borda: docker build -f docker/web.Dockerfile -t croquito-web-t1 .
                 e curl -si nas quatro rotas do Acceptance contra o container em execução
```

Leia `docker/web.Dockerfile` antes para confirmar porta exposta e onde o `nginx.conf` entra
na imagem. Não invente comando: se a imagem não for construível no seu ambiente, encerre
`BUILDER_VALIDATION_BLOCKED` com o motivo, como exige o
[contrato do Builder](../../../engineering-os/agents/builder.md).

## Required Capabilities

```text
READ:     o repositório (deploy/, docker/, docs/features/F-007-tela-de-login/)
WRITE:    deploy/nginx.conf, somente
VALIDATE: make check; docker build/run + curl
COMMIT:   forbidden — a entrega é o diff na árvore mais o BUILD REPORT
```

## Context to Read First

1. `AGENTS.md` (raiz) e `CLAUDE.md` do repositório.
2. `deploy/nginx.conf` por inteiro — o cabeçalho explica same-origin e o
   `absolute_redirect off`.
3. [ADR-0032](../../../adr/0032-porta-de-entrada-e-estado-sem-sessao.md), D1, D2 e D5.
4. `docker/web.Dockerfile`.

## Known Risks

- `Location` absoluto no redirect novo (quebra atrás do Cloud Run) — o `absolute_redirect
  off` global cobre, mas conferir na resposta real do curl.
- Servir `/login` com `try_files` em vez de location exata pode engolir caminhos que o
  fallback final `location / { return 404; }` deveria recusar — a location é exata (`=`).

## Human Gates

- Nenhum dentro do escopo. Commit, merge e deploy são atos humanos fora deste contrato.

## Reporting

Encerre com o `BUILD REPORT` completo do
[contrato do Builder](../../../engineering-os/agents/builder.md) — todos os campos, `none`
onde vazio — e grave o mesmo conteúdo em
`docs/features/F-007-tela-de-login/tasks/T1-build-report.md`.
