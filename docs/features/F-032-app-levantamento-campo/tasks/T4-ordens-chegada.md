# T4 — Ordens de levantamento e chegada ao local (pranchas 1–2 do DAP)

## Identity

```text
feature_id: F-032
task_id: T4
parent_plan: docs/features/F-032-app-levantamento-campo/plan.md (plano "MVP local, fatias 1–3")
depends_on: T2 (motor), T3 (telas de coleta — já entregues e commitadas)
```

## Goal

Dar porta de entrada ao app: lista de ordens de levantamento (prancha 1) com fixture
local sintética, fluxo de chegada ao local (prancha 2) que registra o contexto do dia
(instrumento, referência física, GPS como localização), e navegação
ordens → chegada → coleta, com um levantamento por ordem. Tudo local, sem rede.

## Scope

- `apps/field/src/orders/**` (novo): tipos, fixture, lógica de estado da ordem.
- `apps/field/src/domain/**`: extensão mínima — `Survey.order_id?`,
  `Survey.context?: ArrivalContext { instrument, reference_note, gps?: { lat, lng,
  accuracy_m } | "unavailable", arrived_at }` e comando puro `recordArrival` (erro
  `EMPTY_TEXT` para referência vazia; instrumento de lista fechada + "outro") com
  testes no padrão de `commands.test.ts`.
- `apps/field/src/ui/**`: telas novas (OrdersScreen, ArrivalScreen), navegação no
  FieldApp (estado, sem lib de rota), subtítulo do MeasureScreen usando o instrumento
  do contexto quando existir (substitui "não informado").
- `apps/field/src/main.tsx` se preciso.

## Out of Scope

- Rede/download real: a fixture é o "servidor". "Baixar para usar offline" cria o
  levantamento local da ordem (instantâneo) — funcionalmente honesto no MVP local; o
  estado "não baixada + botão desabilitado offline" da prancha 1b permanece na
  composição via `navigator.onLine`.
- Foto do acesso real (T6): o item aparece no checklist como pendente e o botão
  "Tirar foto do acesso" fica desabilitado com "(em breve)".
- Conclusão (T5), `src/storage/**`, `src/outbox/**` (usar `applyCommand` existente),
  `services/**`, `docs/**`. Não tocar `validation.ts` (o checklist entra via
  `requiredItems` que a UI monta).
- Desvio visual material das pranchas 1–2 → gate humano, parar e reportar.

## Especificação

1. **Fixture** (`orders/fixture.ts`): 3 ordens sintéticas espelhando a prancha 1
   (Guaxindiba — completa, 14 itens; Campo do Toca — academia + calçadas, 9 itens;
   Raul Campelo), cada uma com `checklist: Array<{ id, label, required }>` incluindo
   `foto-acesso` obrigatório. Nada de dado real.
2. **Estado da ordem** derivado, não duplicado: "baixada" = existe survey local com
   `order_id` da ordem; "concluída" fica para T5 (não inventar campo agora).
3. **OrdersScreen** (prancha 1): cartões com etiqueta de estado ESCRITA (tag ok/
   neutra), banner informativo no offline (1b) e estado vazio (1c) — este último só
   aparece se a fixture estiver vazia; manter o texto da prancha.
4. **ArrivalScreen** (prancha 2): segmented de instrumento (Trena laser / Trena
   comum / Outro), campo de referência física, item de checklist do GPS —
   `navigator.geolocation` com timeout curto; sucesso vira check ok com coordenadas e
   "±Xm · serve para achar a obra, não para medir"; negado/indisponível vira item
   escrito "Localização não disponível — siga sem ela" SEM bloquear; item
   "Foto do acesso principal — pendente" com botão desabilitado "(em breve)";
   "Começar a coleta" chama `recordArrival` via `applyCommand` e navega para a
   coleta. Reabrir uma ordem com chegada já registrada vai direto à coleta.
5. **requiredItems**: a tela de coleta passa a chamar `validateSurvey` com
   `requiredItems` montados do checklist da ordem (por ora: `foto-acesso` sempre
   `satisfied: false`; demais itens `satisfied: true` — a materialização item a item
   é de fatias futuras e NÃO deve virar UI nova aqui).
6. **Navegação**: FieldApp ganha o estado de tela raiz (orders | arrival | collect…),
   um survey por ordem (`survey-<order_id>`); o survey avulso `survey-local` de T3
   deixa de ser criado (dado antigo pode ser ignorado; sem migração).

## Acceptance Criteria

1. `npm run field:test` exit 0 com testes novos de `recordArrival` (sucesso, texto
   vazio, GPS indisponível) e da derivação de estado da ordem.
2. `npm run field:check`, `make check`, `make test` exit 0.
3. Roteiro manual descrito no report: abrir app → lista com 3 ordens → "Baixar" numa
   ordem → "Abrir levantamento" → chegada (instrumento + referência) → "Começar a
   coleta" → coleta funciona como em T3 e o subtítulo de medir mostra o instrumento;
   reload volta direto à coleta da ordem aberta (ou à lista, com a ordem "Baixada").
4. `grep -rn "fetch(\|axios\|WebSocket" apps/field/src/` sem retorno.
5. `git status --porcelain` só no escopo declarado.

## Validation

```text
baseline: make check && make test verdes na branch (commit 6ea09a4 + docs); field: 94.
required: unit: npm run field:test
required: typecheck+build: npm run field:check
required: monorepo: make check && make test
```

## Required Capabilities

```text
READ: repositório; DAP ../mock/ (pranchas 1–2); src/domain e src/ui como entregues
WRITE: escopo declarado
VALIDATE: comandos acima
COMMIT: forbidden
```

## Context to Read First

`../mock/campo.html` + `01-ordens.png`/`02-chegada.png`; `../feature.md`;
`apps/field/AGENTS.md`; `src/ui/FieldApp.tsx` (fila serial e `apply(build)` — todo
comando novo passa por ali); `src/domain/commands.ts` (padrão de comando e teste).

## Known Risks

- Duplicar estado da ordem em vez de derivá-lo do survey.
- Bloquear a chegada quando o GPS falha — a regra é o contrário (nunca bloqueia).
- Gravar chegada fora do `applyCommand` (toda mutação é comando).
- Portão reprovando em área não tocada → BUILD_BLOCKED.

## Human Gates

Desvio material das pranchas 1–2; qualquer campo novo de checklist além do descrito.

## Reporting

BUILD REPORT completo de `docs/engineering-os/agents/builder.md`, com o roteiro manual
executado.
