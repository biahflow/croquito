# F-032 — Evidence (fatia 0)

Consolidação da execução da fatia 0 (T1 — scaffold do `apps/field`). Handoff de
revisão para o gate humano; não substitui os artefatos-fonte.

## Baseline

`make check && make test` na worktree `../croquito-f032`, branch
`f-032-app-levantamento-campo` (base `main@5148f80`, docs da F-032 já commitados em
`809aed4`), em 2026-08-21: **verdes** — ruff/format/mypy (203 arquivos), check_docs
(288 md), contratos sem drift, web build, pytest **1785 passed / 13 skipped**, vitest
web **853 passed**. Nenhuma falha preexistente conhecida.

## Execução — T1 (Builder: implementador-sonnet, harness Claude Code)

`PRIMARY_EXECUTION_EVIDENCE`: BUILD REPORT completo entregue pelo Builder em
2026-08-21 com `Status: BUILD_COMPLETE`; transcrito em resumo aqui, com atribuição
preservada — Builder implementador-sonnet, tarefa
[T1](tasks/T1-scaffold-apps-field.md):

- Files changed: `package.json` raiz (workspace + scripts `field:*`), `Makefile`
  (`field:check` no `check`, `field:test` no `test`), `package-lock.json`, e
  `apps/field/**` novo (package.json, tsconfig, vite.config com VitePWA+Tailwind,
  index.html, icon.svg, `src/domain/types.ts`, `src/storage/{SurveyRepository,
  DexieSurveyRepository}.ts` + testes, `src/outbox/{types,outbox}.ts` + testes,
  `src/ui/FieldShell.tsx`, `src/main.tsx`, `styles.css`, `testSetup.ts`, AGENTS.md).
- Validation executed (pelo Builder): `npm run field:check` (dist com `sw.js` e
  `manifest.webmanifest`), `npm run field:test` (9 testes novos), `make check` e
  `make test` completos, grep de pureza do domínio, `git status` dentro do escopo.
- Validation skipped: none. Unavailable capabilities: none.
- Assumptions relevantes: versões novas fixadas nas atuais do registry (dexie ^4.4.5,
  vite-plugin-pwa ^1.3.0, tailwindcss ^4.3.3, fake-indexeddb ^6.2.5); porta dev 5174;
  `FieldShell` usa survey fixo `survey-scaffold` (shell descartável).
- Remaining risks declarados: `FieldShell` sem teste automatizado de interação (padrão
  igual ao de `apps/web`); matriz de aparelhos/iOS fora desta fatia.
- Human decisions required: none. Nenhum commit pelo Builder (COMMIT forbidden).

## Revisão (modelo principal da sessão, linha a linha do diff)

- `REVIEW_FINDINGS` → corrigido na própria rodada, antes do commit:
  - **CODE_FINDING (HIGH)**: `FieldShell.recordOperation` calculava o próximo `seq`
    sobre `getPendingOperations` (que exclui `acked`) — depois de um ack a sequência
    regrediria e reutilizaria `seq` já emitidos, quebrando a semântica "crescente por
    device" de que a sincronização futura depende. Condição: qualquer ack seguido de
    nova operação. Correção: método `listOperations` (histórico completo, ordenado)
    na interface e na implementação Dexie; `FieldShell` calcula `nextSeq` sobre o
    histórico completo filtrado por `device_id`; teste de regressão novo em
    `outbox.test.ts` ("não regride depois de um ack").
- Demais achados: nenhum. Makefile/package.json mínimos; `.gitignore` já cobre
  `dist/` e `*.tsbuildinfo`; testes de storage com reabertura real do banco e
  inspeção interna no ack; AGENTS.md consistente com ADR-0043.

## Validação final (pós-correção, 2026-08-21)

- `npm run field:test`: **10 passed** (9 do Builder + 1 da correção).
- `npm run field:check`: verde, `dist/` com service worker e manifest.
- `make check`/`make test` completos: verdes na árvore final (a correção toca somente
  TypeScript de `apps/field`, invisível a ruff/mypy/pytest/check_docs; os perfis do
  app novo foram reexecutados sobre o código corrigido).

## Execução — T2 (Builder: implementador-sonnet, harness Claude Code)

Plano "MVP local, fatias 1–3" ([plan.md](plan.md)), tarefa
[T2](tasks/T2-motor-dominio-validacao.md). `PRIMARY_EXECUTION_EVIDENCE`: BUILD REPORT
completo entregue em 2026-08-21, `Status: BUILD_COMPLETE`; resumo com atribuição
preservada:

- Files changed: `src/domain/types.ts` (justification, ObservationNote,
  CommandResult, par do ângulo, âncora ponto-ou-elemento), `src/domain/commands.ts`
  (9 comandos puros), `src/domain/validation.ts` (validateSurvey/summarize/
  canConclude), `commands.test.ts` (28) + `validation.test.ts` (20); dois ajustes de
  typecheck fora do escopo nuclear (literal `observations: []` em FieldShell e num
  helper de teste), previstos pelo contrato.
- Validation executed: field:test 58, field:check, make check, make test completos —
  verdes; grep de pureza sem retorno. Skipped: none. Capabilities: none faltando.
- Assumptions declaradas: INVALID_MM reaproveitado para value_mm; EMPTY_TEXT para
  textos vazios; "todos os pontos referenciados devem existir"; level/drop com ≥1
  ponto; OPEN_PERIMETER dispara em grafo vazio; primeira medida do par alimenta o
  triângulo (divergência é responsabilidade exclusiva de MEASUREMENT_DIVERGENCE).
- Remaining risks declarados: PhotoAnchor.point_id agora opcional (T3 ciente); pilha
  de undo vive fora do Survey (orquestração de T3/T5); hasCycle sem verificação de
  desempenho a 2.000 elementos.

### Revisão T2 (modelo principal, linha a linha)

- `REVIEW_FINDINGS` → corrigido antes do commit:
  - **CODE_FINDING (HIGH)**: `closePerimeter` não checava se as duas pontas abertas
    já estavam ligadas entre si — no grafo "anel fechado + segmento solto A–B", fechar
    duplicaria A–B, violando a regra de `addSegment` e quebrando a premissa de grafo
    simples do `hasCycle`. Correção: guard `segmentExistsForPair` com
    `PERIMETER_AMBIGUOUS` e mensagem própria; teste de regressão novo.
- Assumptions do Builder revisadas e aceitas; observação registrada (não bloqueante):
  `DANGLING_REFERENCE` não cobre `observations` (fora da tabela do contrato) e
  `closePerimeter` com 0 pontas abertas responde `PERIMETER_AMBIGUOUS` genérico — a
  UI de T3 pode especializar a copy.
- Validação final pós-correção: field:test **59 passed**, field:check verde,
  `make check` e `make test` completos verdes (EXIT=0).

## Execução — T3 (Builder: implementador-opus, harness Claude Code)

Plano "MVP local, fatias 1–3" ([plan.md](plan.md)), tarefa
[T3](tasks/T3-telas-coleta-medida.md). `PRIMARY_EXECUTION_EVIDENCE`: BUILD REPORT
completo entregue em 2026-08-21, `Status: BUILD_COMPLETE`; resumo com atribuição
preservada:

- Files changed: FieldShell removido; novos `outbox/applyCommand.ts` (+testes),
  `ui/viewModel.ts` (+28 testes puros), `ui/FieldApp.tsx` (orquestração, pilha de
  undo fora do Survey), `ui/SurveyCanvas.tsx`, `CollectScreen`, `AddMenu`,
  `MeasureScreen`, `DivergenceScreen`, `TextEntryScreen`, `AppBar`, `notice.ts`,
  `device.ts`; `styles.css` com tokens do DAP em `@theme` + primitivas; `main.tsx`.
- Validation executed: field:test 92, field:check, make check, make test completos,
  grep sem rede, escopo confirmado; roteiro manual do critério 3 executado em
  Chromium 390×780 com capturas (pontos→segmentos→fechar→medir→reload persistindo→
  offline→undo→divergência 4b com justificativa; dump do IndexedDB com seq 1..15
  contíguos, nada removido). Skipped: none.
- Assumptions: tolerância 50 mm nomeada até T4; mundo 24×31,5 m; rótulo Sx por ordem
  de criação; cota exibida = primeira medida confirmada do par.
- Desvios conscientes declarados (1–3, 7–8: instrument "não informado" até T4;
  curva/elemento/foto "(em breve)"; copy "texto" sem voz; primitivas em
  @layer components; SURVEY_ID survey-local) e três adições de composição (4–6:
  TextEntryScreen com primitivas aprovadas, escapes "Cancelar", rótulo de cota girado
  ao longo do segmento) levantadas como gate humano de design.

### Revisão T3 (modelo principal, linha a linha)

- `REVIEW_FINDINGS` → corrigido antes do commit:
  - **CODE_FINDING (HIGH — corrida de toque duplo)**: os alvos de toque do canvas não
    eram gateados por `busy` e os handlers construíam o comando com o snapshot do
    momento do toque; dois toques rápidos liam o mesmo estado e o segundo `saveSurvey`
    sobrescrevia o survey sem o ponto do primeiro — perda de ação confirmada (o NFR
    central). Correção: `outbox/serialQueue.ts` (fila serial testada) e `apply`
    refatorado para construir o comando SÓ na vez dele (`build(current)` dentro da
    fila), nos sete call sites. Verificação ao vivo em Chromium: dois cliques com
    delay 0 → 2 pontos persistidos, operações `seq [1,2]`, 2 pontos após reload.
- Observação registrada para a fatia de sync (não bloqueante): `saveSurvey` e
  `appendOperation` não são atômicos — crash entre os dois deixa survey sem operação;
  o transporte real deve embrulhar os dois numa transação Dexie.
- Validação final pós-correção: field:test **94 passed** (92 + 2 da fila),
  field:check verde, `make check` e `make test` completos verdes (pytest 1785, web
  853, field 94).

## Execução — T4 (Builder: implementador-sonnet, harness Claude Code)

Tarefa [T4](tasks/T4-ordens-chegada.md). `PRIMARY_EXECUTION_EVIDENCE`: BUILD REPORT
completo em 2026-08-21, `Status: BUILD_COMPLETE`; resumo com atribuição preservada:

- Files changed: `src/orders/{types,fixture,state,activeOrder}.ts` (+testes), telas
  `OrdersScreen`/`ArrivalScreen`, navegação raiz no `FieldApp`
  (loading|orders|arrival|survey, retomada por ordem ativa em localStorage),
  `recordArrival` no domínio (+3 testes), primitivas `.check`/`.seg` em styles.css só
  com tokens existentes; instrumento da chegada passa a assinar as medidas.
- Validation executed: field 100, field:check, make check/test completos, grep sem
  rede, escopo confirmado; roteiro manual em Chromium com GPS negado exercitando o
  caminho não-bloqueante (baixar→abrir→chegada→coleta→subtítulo com instrumento→
  reload retomando a coleta da ordem). Skipped: none.
- Assumptions honestas: sem técnico inventado (sem auth), sem tamanho de download
  fictício, instrumento como texto livre com lista fechada só na UI.
- Risco declarado: sem navegação de volta às ordens após abrir (chrome novo exigiria
  aprovação visual; fica para fatia futura).

### Revisão T4 (modelo principal, linha a linha)

- `REVIEW_FINDINGS` → corrigido antes do commit:
  - **CODE_FINDING (MEDIUM — omissão de spec não declarada)**: o §5 da Especificação
    (checklist da ordem entrando em `validateSurvey` via `requiredItems`, com
    `foto-acesso` pendente) não foi implementado, e o BUILD REPORT declarou "nenhum
    desvio de comportamento" — sem o item, o warning `REQUIRED_ITEM_PENDING` nunca
    nasce e a tela de conclusão (T5) perderia a pendência de foto. Correção:
    `requiredItemsForOrder` em `orders/state.ts` (+teste sobre as 3 ordens da
    fixture), ligado ao memo de findings do `FieldApp`.
- Demais achados: nenhum; estado da ordem derivado (nunca duplicado), GPS
  não-bloqueante correto, criação de survey no download como exceção documentada.
- Validação final pós-correção: field:test **101 passed**, `make check` e `make test`
  completos verdes (pytest 1785, web 853, field 101).

## Execução — T5 (Builder: implementador-sonnet, harness Claude Code)

Tarefa [T5](tasks/T5-conclusao.md). `PRIMARY_EXECUTION_EVIDENCE`: BUILD REPORT
completo em 2026-08-21, `Status: BUILD_COMPLETE`; resumo com atribuição preservada:

- Files changed: domínio (SurveyStatus/Waiver com leitura retrocompatível via
  `surveyStatus`/`surveyWaivers`; comandos `waiveFinding` e `concludeSurvey` com dupla
  checagem CANNOT_CONCLUDE/ALREADY_CONCLUDED, +9 testes), `ConcludeScreen` (prancha
  5), entrada pelo menu Adicionar (prancha 3a intocada — decisão declarada), prop
  `readOnly` no CollectScreen, badge "Concluída" derivada em `deriveOrderState`,
  `handleConclude` recalculando findings dentro da fila serial (estado fresco).
- Validation executed: field 110, make check/test completos verdes; roteiro do
  critério 3 como script determinístico sobre applyCommand+Dexie real (inclusive
  reabertura simulada do banco); gating de UI verificado por leitura de código —
  lacuna declarada honestamente (sem harness de clique no workspace).
- Desvios conscientes: toque em `orders/state.ts` fora do escopo literal (justificado:
  único ponto de derivação de estado, apontado pelo próprio comentário do arquivo);
  badge `tag-ok` em vez do `tag-warn` do mock (sem sync nesta fatia, texto continua o
  portador do significado).

### Revisão T5 (modelo principal, linha a linha + fumaça de navegador)

- `REVIEW_PASS` no código (nenhum finding; desvios aceitos como declarados).
- A lacuna do report (UI não clicada) foi coberta pelo revisor com fumaça em Chromium
  real contra `field:dev`: baixar ordem → chegada → 3 pontos → ligações → fechar
  perímetro → conclusão bloqueada "Concluir (3 itens críticos abertos)" → toque no
  crítico levando ao segmento → 3 medidas de 5,00 m pelo teclado (subtítulo assinado
  "Trena laser") → warning de foto justificado por texto → Concluir habilitado →
  volta às ordens com badge "Concluída" → reabertura em somente leitura (Adicionar
  desabilitado, aviso escrito). Tudo conforme a prancha 5.
- Validação final: `make check` e `make test` completos verdes (pytest 1785, web 853,
  field 110).

## Execução — T6 (Builder: implementador-sonnet, harness Claude Code)

Tarefa [T6](tasks/T6-fotos-ancoradas.md). `PRIMARY_EXECUTION_EVIDENCE`: BUILD REPORT
completo em 2026-08-21, `Status: BUILD_COMPLETE`; resumo com atribuição preservada:

- Files changed: `src/photos/{hash,media,quota}.ts` (+testes, vetores NIST no SHA-256),
  `MediaRecord`+`saveMedia`/`getMedia` na interface e no Dexie (schema v2 com teste de
  migração v1→v2 sem perda; sem delete, por regra), `PhotoAnchorScreen` (captura via
  input nativo `capture=environment`, sem preview — galeria registrada como reservado),
  foto do acesso na chegada satisfazendo o checklist (`requiredItemsForOrder` agora
  deriva de `access_media_ref` no contexto, via reuso documentado de `recordArrival`),
  📷 no desenho, banner de quota <50 MB fail-open.
- Validation executed: field 128 (110+18), make check/test completos, roteiro manual
  Playwright ao vivo (captura → âncora → 📷 → reload persistindo → checklist
  satisfeito). Skipped: none.
- Disciplina verificada: blob gravado ANTES da âncora e a âncora sempre por
  comando/applyCommand; blob nunca em estado React/log.

### Revisão T6 (modelo principal, linha a linha)

- `REVIEW_PASS` — nenhum finding; observação registrada (não bloqueante): foto do
  acesso capturada e abandonada antes de "Começar a coleta" deixa um `MediaRecord`
  órfão (sem referência) — inofensivo no MVP local (nada é apagado por regra) e
  matéria da fatia de sync.
- Validação final: `make check` e `make test` completos verdes (pytest 1785, web 853,
  field 128).

## Decisões humanas registradas (2026-08-21, pós-onda 1)

- As três adições de composição da T3 (tela de digitação de texto com primitivas
  aprovadas; escapes "Cancelar" nos modos sem saída; rótulo de cota girado ao longo do
  segmento) foram declaradas **não materiais** por ato humano de Daniel Campos — o
  [DAP revisão 1](mock/README.md) segue válido, sem revisão 2.
- Onda 2 do plano (T4 ordens+chegada, T5 conclusão, T6 fotos) **autorizada** pelo
  mesmo ato; contratos derivados em tasks/.

## Desvios de plano

- Renumeração F-031→F-032 / ADR-0042→ADR-0043 antes do congelamento do plano
  (colisão com `feat/f-031-value-events`), registrada em [plan.md](plan.md).

## Pendências e gates humanos

1. ~~Aceite do ADR-0043~~ — satisfeito por ato humano de Daniel Campos em 2026-08-21.
2. ~~Design Approval Package~~ — [revisão 1](mock/README.md) aprovada por ato humano
   de Daniel Campos em 2026-08-21.
3. Decisão de merge da branch `f-032-app-levantamento-campo` (merge na main dispara a
   esteira `deploy-hml`).
