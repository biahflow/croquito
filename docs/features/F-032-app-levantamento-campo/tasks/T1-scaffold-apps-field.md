# T1 — Scaffold do `apps/field` (PWA offline-first, fatia 0 da F-032)

## Identity

```text
feature_id: F-032
task_id: T1
parent_plan: docs/features/F-032-app-levantamento-campo/plan.md
depends_on: none
```

## Goal

Fundar o workspace `apps/field` como PWA React+Vite offline-first coberta pelos portões
do monorepo (`make check`/`make test`), contendo: modelo de domínio serializável em mm
inteiros, persistência local IndexedDB (Dexie) atrás da interface `SurveyRepository` com
testes, esqueleto de outbox de operações com testes, e um shell mínimo de UI que
demonstra ação → persistência local → undo com indicador de offline. Sem telas finais,
sem chamadas de rede, sem tocar a API.

## Scope

Pode criar/alterar somente:

- `apps/field/**` (diretório novo);
- `package.json` da raiz (acrescentar `"apps/field"` a `workspaces` e os scripts
  `field:dev`, `field:check`, `field:test` espelhando os `web:*`);
- `Makefile` (acrescentar `npm run field:check` ao alvo `check`, logo após
  `npm run web:check`, e `npm run field:test` ao alvo `test`, logo após
  `npm run web:test`);
- `package-lock.json` (efeito do `npm install`).

## Out of Scope

Não tocar, mesmo que note problema adjacente (reportar em vez de corrigir):

- `services/**`, `packages/**`, `apps/web/**`, `infra/**`, `.github/**`, `docker/**`,
  `deploy/**`, `tests/**` (suíte Python), `pyproject.toml`, `uv.lock`;
- `docs/**` — a documentação da F-032 já foi escrita; nenhum doc novo ou editado
  (exceção única: `apps/field/AGENTS.md`, que faz parte do scaffold);
- nenhuma rota, contrato ou schema (`make contracts` não entra nesta tarefa);
- nenhum design final de UI: o shell é declaradamente descartável (gate de Design
  Approval registrado no Feature Contract);
- nenhum transporte de rede no outbox (sem fetch/axios; o ack é simulado em teste);
- nenhum commit.

## Especificação do conteúdo

Inspecionar `apps/web/` primeiro (package.json, tsconfig, vite.config, setup de teste)
e espelhar convenções onde couber. Código e identificadores em inglês; textos de UI em
português.

1. **`apps/field/package.json`** — nome `@croquito/field`, `private`, scripts
   `dev`/`check`/`test` no mesmo molde do web (`check` = `tsc -b && vite build`,
   `test` = `vitest run`). Dependências: `react`/`react-dom` 19, `dexie`. Dev:
   `typescript`, `vite`, `@vitejs/plugin-react`, `vitest`, `vite-plugin-pwa`,
   `tailwindcss` v4 + `@tailwindcss/vite`, `fake-indexeddb` (testes), tipos e ambiente
   de teste DOM no mesmo molde do web.
2. **PWA** — `vite-plugin-pwa` com `registerType: "autoUpdate"`, manifest mínimo
   (nome "croquito campo", `display: standalone`, ícone SVG placeholder gerado no
   próprio repo — nada baixado), precache do shell.
3. **`src/domain/`** — tipos serializáveis puros, sem nenhum import de UI/Dexie:
   `Survey`, `SurveyPoint`, `Segment`, `Measurement`, `PhotoAnchor`, `ElementObject`.
   Coordenadas em **mm inteiros** (documentar no tipo); IDs string; datas ISO UTC.
   `Measurement` carrega `value_mm`, `kind` (length | diagonal | width | radius |
   level | drop | height | angle), `from_point_id`/`to_point_id` opcionais,
   `element_id` opcional, `instrument`, `status` (draft | confirmed).
4. **`src/storage/`** — interface `SurveyRepository` (mínimo: `getSurvey`,
   `saveSurvey`, `appendOperation`, `getPendingOperations`, `acknowledge`) e
   implementação `DexieSurveyRepository`. Testes com `fake-indexeddb`: salvar e
   recuperar survey; operação pendente sobrevive a reabrir o banco; `acknowledge`
   remove da lista de pendências sem apagar o histórico.
5. **`src/outbox/`** — tipo `SurveyOperation` (`operation_id` UUID, `device_id`,
   `survey_id`, `seq` crescente por device, `type`, `payload`, `status`:
   local | pending | acked, `created_at`) e funções puras/sobre o repositório para
   enfileirar e reconhecer. Sem transporte real. Testes: enfileirar preserva ordem de
   `seq`; ack é idempotente (ack duplo não corrompe estado).
6. **`src/ui/`** — shell de tela única com Tailwind: área de desenho `<svg>` nativa
   ocupando a maior parte, botão grande (≥48px) "Adicionar ponto" que cria um
   `SurveyPoint`, persiste via `SurveyRepository` **antes** do feedback visual e
   renderiza o ponto no SVG; botão "Desfazer" removendo o último ponto (também
   persistido); indicador permanente de offline/online (`navigator.onLine` + eventos)
   e contagem de operações pendentes. Nenhum estado global externo (React puro).
7. **`apps/field/AGENTS.md`** — curto, no molde de `apps/web/AGENTS.md`: a fonte
   oficial é o modelo serializável, nunca o canvas; SVG nativo somente
   rendering/interação; toda ação persiste localmente antes do sucesso visual; dado
   local nunca é apagado antes de ack; mm inteiros; proibido introduzir transporte de
   rede sem tarefa que o autorize; Tailwind restrito a `apps/field`. Links relativos
   válidos (o `check_docs` valida todos os links de Markdown do repositório).

## Acceptance Criteria

1. `npm run field:check` (na raiz) termina com exit 0 — typecheck strict + build; o
   diretório `apps/field/dist/` resultante contém `sw.js` (ou service worker gerado
   pelo vite-plugin-pwa) e `manifest.webmanifest` — verificar com
   `ls apps/field/dist`.
2. `npm run field:test` termina com exit 0, com os testes novos de `src/storage/` e
   `src/outbox/` descritos acima presentes e passando.
3. `make check` termina com exit 0 (todos os workspaces, incluindo o novo).
4. `make test` termina com exit 0 (pytest intacto + vitest dos dois apps).
5. `grep -rl "react\|dexie" apps/field/src/domain/` não retorna nenhum arquivo (o
   domínio não importa UI nem storage).
6. `git status --porcelain` mostra mudanças apenas dentro do escopo declarado
   (apps/field/**, package.json, package-lock.json, Makefile).

## Validation

```text
baseline: make check && make test — verdes na branch f-032-app-levantamento-campo
  (worktree ../croquito-f032) com os docs da F-032 já presentes; nenhuma falha
  preexistente conhecida.
required: lint+typecheck+build: make check
required: unit: make test
required: app novo isolado: npm run field:check && npm run field:test
```

## Required Capabilities

```text
READ:     repositório inteiro (referência: apps/web, Makefile, package.json raiz)
WRITE:    apps/field/**, package.json, package-lock.json, Makefile
VALIDATE: make check, make test, npm run field:check, npm run field:test
COMMIT:   forbidden
```

## Context to Read First

- `AGENTS.md` (raiz) e `apps/web/AGENTS.md` — disciplina de mudança e convenções web;
- `apps/web/package.json`, `apps/web/tsconfig*.json`, `apps/web/vite.config.*` — o
  molde a espelhar;
- `docs/features/F-032-app-levantamento-campo/feature.md` — critérios da fatia 0;
- `docs/adr/0043-app-de-campo-pwa-offline-first.md` — as decisões que este scaffold
  materializa.

## Known Risks

- Mexer em `package.json` raiz/`Makefile` pode quebrar `make check` dos workspaces
  existentes — rodar o portão completo, não só o do app novo.
- `vite-plugin-pwa` e Tailwind v4 têm formas de configuração novas; se a versão
  instalada divergir do esperado, seguir a documentação da versão instalada e
  registrar a diferença no BUILD REPORT em vez de forçar downgrade.
- `fake-indexeddb` precisa ser injetado no ambiente do vitest (setup file); teste que
  passa por acaso no ambiente errado é falha silenciosa — garantir que o teste falha
  se a persistência for removida.
- Se um portão reprovar em área NÃO tocada pela tarefa, parar e reportar
  (`BUILD_BLOCKED`), sem consertar área alheia.

## Human Gates

- Nenhum dentro do escopo. Adjacente: design final de telas (Design Approval Package)
  e rotas `/v1/surveys` estão fora — reportar e parar se o trabalho parecer exigi-los.

## Reporting

Terminar com o `BUILD REPORT` completo exigido pelo contrato do Builder
(`docs/engineering-os/agents/builder.md`), todos os campos presentes, `none` onde
vazio.
