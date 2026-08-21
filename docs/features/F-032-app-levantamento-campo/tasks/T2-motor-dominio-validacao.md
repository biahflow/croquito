# T2 — Motor de domínio e validação de campo (`src/domain`)

## Identity

```text
feature_id: F-032
task_id: T2
parent_plan: docs/features/F-032-app-levantamento-campo/plan.md (plano "MVP local, fatias 1–3")
depends_on: none
```

## Goal

Transformar `apps/field/src/domain/` no motor puro do levantamento: comandos de coleta
que produzem novo estado + operação de outbox, e um motor de validação que reproduz as
regras da prancha 5 do
[Design Approval Package aprovado](../mock/README.md). Tudo função pura, serializável,
sem import de React/Dexie, com testes densos — este motor é o que T3/T5 renderizam.

## Scope

Pode criar/alterar somente:

- `apps/field/src/domain/**` (tipos, comandos, validação, testes).

Se um tipo existente precisar de campo novo (ex.: `justification` em `Measurement`),
alterá-lo aqui é escopo desta tarefa; ajustar chamadas existentes em
`src/ui/FieldShell.tsx`/`src/storage` só se o typecheck quebrar, na menor mudança
possível (o shell é descartável e será substituído em T3).

## Out of Scope

- Qualquer UI nova, storage, outbox (além de tipos), rede, `services/**`, `docs/**`.
- Modelo de ordem de levantamento/checklist configurável (T4) — o motor recebe os
  itens obrigatórios como parâmetro, não conhece a origem.
- Geometria métrica "de verdade" (solver): as posições `x_mm/y_mm` dos pontos são
  posição de **croqui** (desenho), não medida; nenhuma validação pode tratá-las como
  verdade métrica. A verdade métrica são as `Measurement` declaradas.

## Especificação

### 1. Tipos (evoluir `types.ts`)

- `Measurement` ganha `justification?: string` (usada quando uma divergência ou
  pendência é mantida com motivo) — demais campos como estão.
- Novo `ObservationNote { id, text, point_id?, element_id?, created_at }` (voz fora do
  MVP; só texto). `Survey` ganha `observations: ObservationNote[]`.
- Novo tipo de resultado de comando:
  `CommandResult = { ok: true; survey: Survey; operation: { type: string; payload: Record<string, unknown> } } | { ok: false; error: { code: string; message: string } }`
  — mensagens em português, códigos estáveis em SCREAMING_SNAKE (padrão de erro
  estruturado do repositório; nunca parsing de string).

### 2. Comandos (`commands.ts`) — todos puros `(survey, args, nowIso) => CommandResult`

| Comando | Regra |
| --- | --- |
| `addPoint` | acrescenta ponto (mm inteiros; rejeitar não-inteiro com `INVALID_MM`) |
| `addSegment` | exige dois pontos existentes e distintos (`UNKNOWN_POINT`, `DEGENERATE_SEGMENT`); rejeita segmento duplicado (mesmo par, qualquer ordem) com `DUPLICATE_SEGMENT` |
| `closePerimeter` | com <3 pontos usados falha `PERIMETER_TOO_SMALL`; senão acrescenta o segmento que liga as duas pontas abertas (pontos de grau 1); se não houver exatamente duas pontas abertas, falha `PERIMETER_AMBIGUOUS` com mensagem explicando |
| `addElement` | exige ≥1 ponto existente (`ELEMENT_WITHOUT_POINT`) |
| `addMeasurement` | vínculo obrigatório: `length`/`diagonal` exigem par de pontos existentes; `width`/`height`/`radius` exigem `element_id` OU par de pontos; `level`/`drop` exigem ponto(s); `angle` exige dois segmentos referenciáveis por par de pontos — se o vínculo exigido faltar, `MEASUREMENT_UNLINKED`. `value_mm` inteiro > 0 |
| `addObservation` | texto não vazio |
| `justifyMeasurement` | grava `justification` (texto não vazio) numa `Measurement` existente (`UNKNOWN_MEASUREMENT` se não existir) — é o "Registrar motivo e manter as duas" da prancha 4b |
| `addPhotoAnchor` | ponto OU elemento existente (`ANCHOR_UNLINKED`) |
| `undoLast` | desfaz o último comando aplicado, devolvendo o estado anterior; a operação emitida é `command.undo` com o id do que foi desfeito. Implementar por reconstrução ou inverso estrutural — decisão do Builder, documentada em comentário; o critério é o teste de ida-e-volta |

Cada comando bem-sucedido também atualiza `updated_at` e emite `operation.payload`
serializável com os argumentos (o transporte é de T-futura; aqui só a forma).

### 3. Validação (`validation.ts`) — `validateSurvey(survey, opts) => Finding[]`

`opts: { toleranceMm: number; requiredItems?: Array<{ id: string; label: string; satisfied: boolean }> }`

`Finding { code, severity: "critical" | "warning", message, refs: string[] }` —
mensagem em português, escrita como na prancha 5 (estado sempre escrito).

| Code | Severidade | Regra |
| --- | --- | --- |
| `OPEN_PERIMETER` | critical | existe ponto usado por segmento com grau 1, ou nenhum ciclo no grafo de segmentos |
| `SEGMENT_WITHOUT_MEASUREMENT` | critical | segmento sem nenhuma `Measurement` `length` confirmada ligando seu par de pontos |
| `TRIANGLE_MISMATCH` | critical | para qualquer trio de pontos com as três distâncias declaradas (medidas `length`/`diagonal` confirmadas), a desigualdade triangular falha além de `toleranceMm` — é a materialização honesta de "diagonal incompatível" sem tratar o desenho como métrica |
| `MEASUREMENT_DIVERGENCE` | critical sem `justification`; warning com | duas medidas confirmadas do mesmo vínculo (mesmo par/elemento e `kind`) com `|Δ| > toleranceMm` |
| `DANGLING_REFERENCE` | critical | segmento/medida/âncora/elemento referenciando id inexistente (integridade) |
| `REQUIRED_ITEM_PENDING` | warning | item de `requiredItems` com `satisfied: false` |
| `ELEMENT_WITHOUT_PHOTO` | warning | elemento sem nenhuma foto ancorada a ele ou a seus pontos |

Mais um sumário `summarize(survey, findings)` com contagens (medidas confirmadas ×
segmentos, críticos, atenções) para a UI da prancha 5. `canConclude(findings)` =
nenhum critical.

### 4. Testes

Vitest cobrindo: cada comando (sucesso + cada código de erro), `undoLast` ida-e-volta
(aplicar N comandos, desfazer N, voltar ao estado inicial campo a campo),
`closePerimeter` nos três desfechos, cada código de validação com caso positivo e
negativo, divergência com e sem justificativa, desigualdade triangular dentro/fora da
tolerância, e `canConclude`.

## Acceptance Criteria

1. `npm run field:test` exit 0, com os testes descritos presentes (mínimo: 1 caso por
   código de erro de comando e por código de finding).
2. `npm run field:check` exit 0.
3. `make check` e `make test` exit 0.
4. `grep -rl "react\|dexie" apps/field/src/domain/` sem retorno (pureza preservada).
5. `git status --porcelain` só dentro do escopo (src/domain/** e, se o typecheck
   exigir, ajuste mínimo em FieldShell/storage).

## Validation

```text
baseline: make check && make test verdes na branch f-032-app-levantamento-campo
  (worktree ../croquito-f032, após commit db95ef3); field: 10 testes passando.
required: unit: npm run field:test
required: typecheck+build: npm run field:check
required: monorepo: make check && make test
```

## Required Capabilities

```text
READ:     repositório (referências: apps/field existente, DAP em ../mock/README.md,
          Feature Contract ../feature.md)
WRITE:    apps/field/src/domain/** (+ ajuste mínimo de typecheck fora, se inevitável)
VALIDATE: comandos acima
COMMIT:   forbidden
```

## Context to Read First

- `../feature.md` (regra central e invariantes) e `../mock/README.md` + capturas
  (prancha 4b e 5 ditam divergência e semáforo).
- `apps/field/AGENTS.md` e `apps/field/src/domain/types.ts` atuais.
- `packages/core/src/croquito_core/errors.py` só como referência do padrão "erro
  estruturado com código estável" (não importar nada de Python).

## Known Risks

- Tratar `x_mm/y_mm` como métrica é o erro conceitual central — a validação usa só
  medidas declaradas.
- `undoLast` com histórico implícito pode virar estado não serializável; o `Survey`
  precisa continuar serializável (se precisar de pilha de estados, ela vive fora do
  `Survey`, em tipo próprio do motor).
- Se um portão reprovar em área não tocada, parar e reportar (`BUILD_BLOCKED`).

## Human Gates

- Nenhum dentro do escopo. Regra de validação nova que não esteja nesta tabela nem no
  Feature Contract não entra — reportar como pergunta, não implementar.

## Reporting

Terminar com o `BUILD REPORT` completo de `docs/engineering-os/agents/builder.md`,
todos os campos, `none` onde vazio.
