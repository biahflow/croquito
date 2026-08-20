# T2 — "Somas de cotas" na tela de revisão: sugestões, declaração e avisos

Task Contract derivado do [plano](../plan.md). Autossuficiente.

## Identity

```text
feature_id: F-023
task_id: T2
parent_plan: docs/features/F-023-survey-quality-score/plan.md
depends_on: [T1]
```

## Goal

O revisor vê, junto às leituras, as somas de cotas que fecham (sugestões) e as
cadeias que ele declarou (com aviso visível quando não fecham ou quando uma
leitura foi retificada), pode declarar total + parcelas entre as confirmadas e
retratar uma declaração. Leituras participantes de soma que fecha ganham um
indício fraco ("Σ fecha"). Nada disso confirma nem trava nada.

## Baseline

`main` com T1 integrada (contrato novo da API no ar). Antes de editar, rode e
registre: `npm --workspace @croquito/web run test` (esperado verde).

## Mapa verificado (leia antes de editar)

- Tipos: `apps/web/src/api.ts` — type `Review` l.115 (escrito à mão; espelha
  `ReviewResponse` da API); comentário-padrão de campo opcional por replay em
  `annotation_suggested` (~l.55-58); helpers de mutação com `Idempotency-Key`
  e `base_version` no mesmo arquivo (siga o molde da rota de decisions).
- Labels: `apps/web/src/labels.ts` — formatação é função pura testável;
  `formatDecimal` existente; testes em `labels.test.ts`.
- Tela: `apps/web/src/CroquiApp.tsx` — `review-list` termina ~l.3164 (a seção
  nova entra logo depois, antes do painel de `safety_notes`); badges de linha
  em `review-row-status` l.3153-3159 (molde: `ocr-warning`); seleção de
  leitura via `setSelectedReadingId`; moldes de interação em lote
  (`batch-controls`, F-010) e do consultor (F-025). O slot `trace-status`
  (l.4312+) é do traçado — NÃO usar para as cadeias.
- CSS: `apps/web/src/styles.css` — espelhar `.ocr-warning` se precisar de cor
  (cor nunca é o único indicador).

## Contrato da API (entregue pela T1)

`Review` ganha `suggested_chains?` e `declared_chains?` (opcionais — replay
antigo pode vir sem eles):

```ts
type ChainTerm = { reading_id: string; value_m: string; raw_text: string };
type DimensionChain = {
  total: ChainTerm; parts: ChainTerm[];
  residual_m: string; tolerance_m: string;
};
type DeclaredChain = {
  chain_id: string; declared_by: string; declared_at: string;
  chain: DimensionChain | null;
  status: "closes" | "mismatch" | "stale";
  issue: { code: string; severity: string; message: string } | null;
};
```

(Confirme os nomes exatos contra o snapshot OpenAPI regenerado pela T1 antes
de digitar os tipos.) Mutação: `POST /v1/jobs/{job_id}/review/chains` com
`{base_version, action: "declare" | "retract", total_id?, part_ids?,
chain_id?}`, `Idempotency-Key` obrigatória; devolve o `Review` novo. Erros:
422 `CHAIN_INVALID`, 404 `CHAIN_NOT_FOUND`, conflito otimista padrão.

## Scope (comportamento)

1. **`api.ts`**: tipos acima + helper `postReviewChains(...)` no molde das
   mutações existentes.
2. **`labels.ts`** (+ testes): `chainSumLabel(chain, status?)` →
   `"12,49 + 9,55 + 3,86 = 25,90 · confere (folga 0,015 m)"` e variante de
   mismatch com o resíduo em metros (vírgula decimal via `formatDecimal`);
   `chainCorroboratedReadingIds(chains)` → `Set<string>` com total + parcelas
   apenas das cadeias que fecham (sugeridas e declaradas `closes`).
3. **`CroquiApp.tsx`** — seção "Somas de cotas" logo após a `review-list`
   (renderiza se houver cadeia sugerida OU declarada OU modo de declaração
   ativo):
   - Declaradas primeiro: `chainSumLabel` + autoria; `mismatch`/`stale` com o
     aviso do `issue` SEMPRE visível (texto + código cru, nunca só cor, nunca
     escondido); botão "Retirar" por linha → `retract`.
   - Sugeridas depois, com o texto fixo de cautela (classe `batch-hint`):
     "Coincidência aritmética é comum; use como pista, não como prova".
   - Clicar num termo de cadeia chama `setSelectedReadingId(reading_id)`.
   - **Declarar**: botão "Declarar cadeia" entra em modo de seleção sobre as
     leituras confirmadas (primeiro clique define o total, seguintes marcam
     parcelas; mínimo 2; permitir desmarcar; Confirmar/Cancelar no molde
     `batch-controls`) → `postReviewChains` com `base_version` corrente;
     sucesso substitui o review em estado; `CHAIN_INVALID` exibido como as
     demais falhas de mutação. Nenhuma submissão automática.
   - Badge `Σ fecha` (`<small class="chain-hint">`) em `review-row-status`
     quando `reading.id ∈ chainCorroboratedReadingIds` — copy fraca de
     propósito; o badge não confirma nada.
4. **Testes** (`labels.test.ts`, `CroquiApp.test.tsx`): fixture com os campos
   → seção renderiza (declaradas + sugeridas + badges); fixture sem os campos
   (`undefined`) → seção ausente, sem crash; fluxo de declaração feliz
   (seleção → POST → review atualizado) e erro `CHAIN_INVALID` exibido;
   retract; mismatch/stale visíveis.

## Out of Scope

`services/**` (contrato é o da T1 — se divergir do snapshot, PARE e reporte,
não conserte a API); score agregado/recomendações (fatias ≥2); qualquer efeito
das cadeias sobre decisão/aprovação/export; `trace-status` e o consultor
F-025; polling/seleção existentes não podem regredir.

## Acceptance Criteria

1. Os 4 grupos de teste do Scope passam; suites existentes intactas.
2. Review sem os campos novos (replay antigo) renderiza como hoje, sem crash
   e sem seção vazia.
3. Aviso de mismatch/stale nunca escondido; cor nunca é o único indicador.
4. `make check` (inclui build web) e
   `npm --workspace @croquito/web run test` verdes.

## Validation

```bash
npm --workspace @croquito/web run test
make check
```

## Report

Termine com o `BUILD REPORT` completo do contrato do Builder (todos os campos;
`none` explícito onde vazio).
