# T2 — BUILD REPORT

Task Contract: [T2-web-sugestao.md](T2-web-sugestao.md) · Plano pai: [plan.md](../plan.md)
Harness: Claude Code (execução em 2026-08-20). Sem commit: o diff fica na árvore.

## Baseline registrada antes da mudança

- Branch `main`. Árvore já suja no início, com mudanças alheias a esta task:
  `apps/web/src/CroquiApp.tsx` (rótulo "Traçado do desenho", aviso de opcional no aceite
  em lote, efeito `openedTraceStepRef`), `docs/adr/README.md`, `docs/product/ROADMAP.md`
  e artefatos não rastreados de F-021/F-022. Os três blocos de `CroquiApp.tsx` foram
  lidos por `git diff` antes de qualquer edição e estão intactos no diff final.
- `npm --workspace @croquito/web run test`: 32 arquivos, **576 testes verdes**.
- T1 corre em paralelo e já alterou `services/worker/src/croquito_worker/review.py`,
  `provider_review.py`, `tests/worker/test_providers.py` e `docs/ai/PROMPT_CONTRACTS.md`.
  `make check` global, portanto, não é oráculo desta task.

```text
BUILD REPORT

Status: BUILD_COMPLETE
Files changed:
  - apps/web/src/api.ts — `ReviewReading` ganha `annotation_suggested?: boolean`
    (sinal observado do pipeline, opcional para pacote persistido antigo continuar válido).
  - apps/web/src/labels.ts — `ELEVATION_PATTERN` (/\bh\s*=/i) e
    `suggestedAnnotationHint(reading)`, no molde documentado de `suggestedAxisHint`:
    campo do modelo → frase do modelo; padrão `h=` no `raw_text` → frase do texto;
    senão `null`.
  - apps/web/src/labels.test.ts — cinco casos novos de `suggestedAnnotationHint`.
  - apps/web/src/CroquiApp.tsx — import de `suggestedAnnotationHint`; função pura de
    módulo `initialAssociationValue(reading, firstCandidateId)`; uso dela no reset de
    `loadReview` e no efeito de troca de leitura; frase da sugestão junto ao select
    "Associação explícita", com a mesma apresentação textual do `suggestedAxisHint`.
  - docs/architecture/API_CONTRACT.md — `annotation_suggested` documentado no shape da
    leitura do pacote, na seção `GET /v1/jobs/{job_id}/review`.
Validation executed:
  - `npm --workspace @croquito/web run test` → 32 arquivos, 581 testes verdes
    (576 do baseline + 5 novos).
  - `npm run web:check` (`tsc -b && vite build`) → verde, build em 516 ms.
  - `uv run python scripts/check_docs.py` → "Documentação válida: 209 arquivos Markdown,
    paridade de lifecycle verificada."
  - `uv run python -m croquito_core.schema_export --check-dir packages/contracts` → sem
    drift; `npm run contracts:check` → verde; `make infra-check` → verde.
  - `make check` → **reprova antes do fim**, em `uv run ruff format --check .`, no
    arquivo `tests/worker/test_providers.py:652` (formatação de uma expressão ternária).
    Arquivo é da task T1, em execução paralela; nenhuma linha dele é desta task e ele
    NÃO foi consertado aqui, conforme a regra de não mexer em área alheia.
Validation skipped:
  - `make test` (pytest completo) — reprovaria/passaria por conta do trabalho de T1 em
    `services/worker` e `tests/worker`, fora do escopo desta task; o oráculo de T2 é a
    suíte do web, executada e verde. Os passos de `make check` posteriores ao ruff format
    foram executados individualmente (listados acima) para separar o que é desta task do
    que é da T1.
Unavailable capabilities: none
Assumptions:
  - `annotation_suggested` chega do backend com o nome e a semântica fixados no
    `plan.md` (T1 entrega o campo em `DimensionReading`); T2 não coordenou com T1, só
    obedeceu ao plano. Se T1 não concluir, o campo simplesmente nunca vem `true` e a
    heurística de texto continua funcionando sozinha.
  - "Leitura sem decisão registrada" é `reading.decision == null`. Verificado contra o
    validador `DimensionReading.validate_review_state` (`services/worker/.../review.py`):
    leitura não revisada não pode carregar decisão, e confirmada/rejeitada exige uma.
  - O web não tem ESLint; o portão de tipo é `tsc -b` com `noEmit`, então a assinatura
    exportada com o alias local `Reading` não gera problema de declaração.
Remaining risks:
  - `apps/web/src/CroquiApp.tsx` é arquivo grande vivo com diff alheio na mesma árvore;
    o diff final foi conferido bloco a bloco, mas o merge com T1 nunca foi exercitado em
    conjunto — a integração final (`make check` + `make test` com os dois diffs) continua
    pendente e é do orquestrador.
  - A heurística `h=` é client-side e não reprocessa nada: pacote antigo passa a nascer
    com anotação pré-selecionada sem que o servidor tenha dito isso. Mitigação: a frase
    declara a origem da sugestão, e o portão humano (justificativa obrigatória, seleção
    trocável) permanece intacto.
  - `docs/product/FDD.md` NÃO foi atualizado (ver "Human decisions required").
Human decisions required:
  - O `AGENTS.md` da raiz manda atualizar o FDD e os critérios de aceite em mudança de
    comportamento, e esta task muda comportamento visível (a associação passa a nascer
    pré-selecionada em certas leituras). Nem o contrato T2 nem o `plan.md` colocam
    `docs/product/FDD.md` no escopo de qualquer das duas tasks. Não ampliei escopo por
    conta própria: fica a decisão de acrescentar ao FDD (seção da decisão de leitura) a
    frase da sugestão e a reafirmação do portão humano. Nenhum documento canônico foi
    contrariado — verificado: o FDD só promete que a **justificativa** nunca vem
    pré-preenchida (preservado), e "nada nasce pré-marcado" é regra da jornada de
    medição, não do croqui, cujo select já pré-selecionava o primeiro candidato.
```

## Desvios conscientes do contrato

1. **Local da documentação no API Contract.** O contrato manda documentar
   `annotation_suggested` "no shape da leitura do pacote (seção da rota de review)" e
   cita a linha ~257, com `"kind": "width"`. Essa linha pertence ao exemplo de
   **entrada** de `POST /v1/jobs/{job_id}/review/rectifications`, não à resposta do
   pacote: documentar ali um campo de resposta seria erro factual. O texto foi escrito na
   seção `GET /v1/jobs/{job_id}/review`, que é a seção da rota de review nomeada pelo
   próprio contrato, com exemplo JSON do `packet.readings`.
2. **Fronteira de palavra no padrão de elevação.** O contrato descreve "`h` (ou `H`)
   seguido de `=` com espaços opcionais". O padrão implementado é `/\bh\s*=/i`: o `\b`
   impede casar dentro de outra palavra (`"largura ph=1"` não é sugestão). É restrição,
   não ampliação; todos os casos exigidos pelo contrato continuam valendo, e o caso extra
   está coberto por teste.
3. **Um teste a mais do que os cinco pedidos.** O caso "25,90 → null" recebeu também
   `"mureta 1,54"` e `"largura ph=1"` no mesmo `it`, para nomear em teste a fronteira que
   o contrato declara fora de escopo.

## Oportunidades vistas e NÃO implementadas (fora de escopo)

- Teste de componente cobrindo a pré-seleção em `CroquiApp.test.tsx`: hoje o arquivo só
  faz `renderToStaticMarkup` sem revisão carregada, e cobrir o efeito exigiria fabricar
  uma revisão inteira — mudança de padrão de teste da jornada, não desta task. O critério
  de aceite 3 pede teste de labels + inspeção do fluxo, e é o que foi entregue.
- O mesmo sinal poderia pré-selecionar a amarração "anotação da folha — sem vão" na etapa
  de traçado. É outro conceito e outro arquivo (`capture.ts`), explicitamente fora de
  escopo.
