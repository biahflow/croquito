# F-035 T1 — A aprovação no domínio, e o portão que o CLI também obedece

feature_id: F-035
task_id: T1
parent_plan: ../plan.md
role: builder

## Goal

O `Estimate` passa a carregar uma aprovação nominal amarrada por digest, e ganha portão de
exportação **próprio**. A cadeia offline (`make valuation-estimate-demo`) continua fechando,
agora com aprovação sintética — como a da medição já faz.

Nenhuma rota é tocada aqui. Esta task entrega o domínio; quem o expõe é a T2.

## Leia antes de editar

- [`AGENTS.md`](../../../../AGENTS.md) na raiz.
- [ADR-0046](../../../adr/0046-aprovacao-do-orcamento-base.md) (`Accepted`) — as decisões
  **1, 3, 4 e 8** governam esta task.
- [Feature contract](../feature.md), escopos 1 e 5, e `Constraints`.

## Scope

1. **Tipo de decisão próprio**, em `packages/valuation/src/croquito_valuation/estimate.py`.

   **Não reuse `ReviewerDecision`** e **não amplie o `Literal` dele**: `reviewer_role` é
   `Literal["orcamentista"]` (`models.py:372`), e ampliá-lo faria um papel do orçamento
   aparecer no vocabulário da medição (ADR-0046, decisão 4). O molde a copiar é a **forma**
   de `ReviewerDecision` (`models.py:361-385`) e `ValuationApproval` (`models.py:388-396`),
   incluindo o validador de fuso horário. O prefixo do `decision_id` é próprio.

2. **`Estimate.approval`**, opcional, default `None` — no molde de `Valuation.approval`
   (`models.py:415`). `schema_version` sobe de `"2.1.0"` (`estimate.py:59`).

3. **`Estimate.content_digest()`** — molde exato de `Valuation.content_digest()`
   (`models.py:492-500`): SHA-256 do dump canônico **excluindo `approval`**. É isso que faz
   assinar não mudar o que foi assinado, e o digest continuar conferindo depois do ato.

4. **`Estimate.export_errors()` / `ensure_exportable()`**, com código de bloqueio próprio.

   **Sem `ContractWorkbook`.** `Valuation.export_errors()` recebe o contrato por parâmetro
   (`models.py:502`) para conferir saldo, período e código; nada disso existe deste lado da
   fronteira, e é a assinatura sem contrato que mantém o ADR-0027 de pé. Copie **só** o
   bloco de aprovação (`models.py:505-512`): não aprovado, aprovação de recusa, e digest que
   não confere com o conteúdo atual.

5. **Aprovação sintética na demo.** `run_estimate_demo`
   (`services/worker/src/croquito_worker/valuation/cli.py:1785-1889`) monta o orçamento e
   chama `run_export_estimate_workbook` em **1865-1867**, sem etapa intermediária. Com o
   portão existindo, isso passa a falhar.

   O molde está no irmão: `run_valuation_demo` injeta `build_synthetic_approval` em
   **1106-1108** antes de `ensure_exportable` em **1109**. Escreva o equivalente para o
   orçamento, no mesmo arquivo de `build_synthetic_approval`
   (`worker/valuation/synthetic.py:814-834`), com identidade e instante **fixos** — a demo é
   determinística e o golden depende disso.

6. **`tests/valuation/test_estimate_workbook.py:285`** também chama
   `run_export_estimate_workbook` e vai encontrar o portão. Ajuste.

7. **Goldens regravados**: `tests/valuation/golden/estimate-demo.canonical.json` (o campo
   novo e a versão de schema). O diff deve ser **só isso** — um diff maior é sinal de que
   algo mais mudou, e aí **pare e reporte**.

## Out of scope

- **Qualquer arquivo em `services/api/`** — as rotas são a T2. Não crie `approve_estimate`
  nem toque em `estimate_rounds.py`.
- **Qualquer arquivo em `apps/web/`.**
- **Qualquer mudança na cadeia de medição**: `Valuation`, `ReviewerDecision`,
  `ValuationApproval` e `VALUATION_EXPORT_BLOCKED` ficam intocados.
- O escritor e o auditor da planilha (`estimate_workbook.py`).

## Uma frase que está certa — não a "corrija"

O ADR manda corrigir as afirmações de que o orçamento é "sem aprovação": o docstring do
**módulo** (`estimate.py:23-26`) e o da **classe** (`estimate.py:158`). Os dois mudam.

Mas `_ESTIMATE_SAFETY_NOTES` (`estimate.py:63-70`) diz que o orçamento "não passa pelo portão
de exportação **da medição**" — e isso **continua verdadeiro** depois desta task: o portão
novo é próprio, não recebe `ContractWorkbook` e não conhece saldo, período nem contrato.
Mexer nela trocaria uma frase correta por uma errada, e a frase está no golden.

## Acceptance criteria

1. `Estimate` sem aprovação **não** é exportável; com aprovação válida, é.
2. Aprovar **não muda** `content_digest()` — o digest gravado na aprovação continua
   conferindo com o do orçamento logo depois do ato.
3. Mudar qualquer campo do orçamento depois de assinado faz os dois digests divergirem, e o
   portão passa a recusar com o código de conteúdo divergente.
4. `Estimate.ensure_exportable()` **não** aceita `ContractWorkbook` — nem opcional. Os
   códigos de saldo, período e contrato não existem deste lado.
5. `make valuation-estimate-demo` verde, com a aprovação sintética.
6. Golden do orçamento regravado com diff **só** do campo novo e da versão de schema.
7. Baseline: `make check` e `make test` verdes antes e depois.

## Pitfalls

- `packages/valuation` não pode passar a depender do worker nem do scene graph (ADR-0016).
- Erros de domínio são estruturados (`ValuationValidationError`); não faça parsing de string
  de exceção.
- A demo é **determinística**: identidade e instante da aprovação sintética são fixos, como
  em `build_synthetic_approval`. Um `datetime.now()` ali quebraria o golden a cada execução.
- `model_dump(mode="json")` é o que o `content_digest` da medição usa — a canonicalização
  precisa ser a mesma, ou dois digests do mesmo conteúdo divergiriam.

## Validation

```bash
make check
make test
make valuation-estimate-demo
uv run pytest tests/valuation/ -q
```

## Report

Encerre com o `BUILD REPORT` completo do contrato do Builder — todos os campos presentes,
`none` onde não houver entradas. Se um portão reprovar em área que você não tocou, **pare e
reporte**; não conserte área alheia.
