# T2 — BUILD REPORT

```text
BUILD REPORT

Status: BUILD_COMPLETE

Files changed:
  - services/worker/src/croquito_worker/review.py
    (DimensionReading ganha `ocr_corroborated: bool | None = None`, registro de
    nascimento no molde de `annotation_suggested`; default None preserva pacote
    persistido antigo)
  - services/worker/src/croquito_worker/provider_review.py
    (o laço passa a calcular `confirmed = _reading_confirmed_by_ocr(...) if ocr_ran
    else None` UMA vez por leitura e usa o mesmo valor na nota posicional existente,
    que ficou byte-idêntica, e no novo `ocr_corroborated=confirmed` do construtor de
    DimensionReading)
  - tests/worker/test_providers.py
    (3 asserções novas nos testes existentes de corroboração: match confirma
    `ocr_corroborated is True`, decoy sem casar confirma `False`, braço ausente
    confirma `None` para todas as leituras do pacote — nenhum teste novo criado,
    reaproveitados os três cenários já existentes por pedido implícito do contrato
    de "asserção explícita num dos testes existentes ou novo")
  - apps/web/src/api.ts
    (`ReviewReading.ocr_corroborated?: boolean | null`, comentário no molde do
    campo vizinho)
  - apps/web/src/labels.ts
    (`ocrWitnessHint(reading): string | null`, molde de `suggestedAnnotationHint`:
    fala só em `false`, silêncio em `true`/`null`/ausente)
  - apps/web/src/labels.test.ts
    (import de `ocrWitnessHint` + `describe("ocrWitnessHint")` com 4 casos: false,
    true, null, campo ausente)
  - apps/web/src/CroquiApp.tsx
    (import de `ocrWitnessHint`; linha da lista ganha `<small className="ocr-warning">`
    só quando `reading.ocr_corroborated === false`, envolvida junto do rótulo de
    status num `<span className="review-row-status">` para preservar as 3 colunas do
    grid `.review-row` — ver desvio consciente #1; painel de decisão ganha o bloco de
    `ocrWitnessHint(selectedReading)` logo após o de `suggestedAnnotationHint`, mesmo
    `<label>`, mesma classe `.field-hint`)
  - apps/web/src/styles.css
    (`.review-row-status` — flex column mínimo para acomodar o rótulo de status +
    aviso sem quebrar o grid de 3 colunas da linha; `.ocr-warning` reaproveita o
    vermelho já usado em `.status-dot.rejected` (#b42318) em vez de inventar token
    novo — ver desvio consciente #2)
  - tests/api/openapi.snapshot.json
    (regenerado via `make openapi-snapshot`; diff aditivo puro — só o novo campo
    `ocr_corroborated` no schema de DimensionReading)
  - docs/architecture/API_CONTRACT.md
    (parágrafo novo descrevendo o tri-estado de `ocr_corroborated`, a semântica de
    nascimento/não-recálculo e o caso fundador da V17, logo após o parágrafo de
    `annotation_suggested` e antes do de `target_hint`)
  - docs/ai/MODEL_ROUTING.md
    (uma frase no bloco de degradação de OCR: a corroboração por leitura agora
    também chega ao revisor como campo do pacote, não só na nota posicional)
  - docs/product/FDD.md
    (um parágrafo na seção de decisão de leitura, entre o lote de anotações e
    "Corrigir uma decisão já registrada": chip na lista + frase no painel, nunca
    bloqueia)
  - docs/features/F-010-revisao-assistida-lote/tasks/T2-build-report.md
    (este relatório)

Validation executed:
  - uv run pytest tests/worker/test_providers.py -x -q → 145 passed
  - make check (ruff check, ruff format --check, mypy strict, check_docs.py,
    schema_export --check-dir, contracts:check, web:check [tsc -b + vite build],
    infra-check [terraform fmt -check]) → todos verdes
  - make test (pytest raiz: 1698 passed, 10 skipped; npm web:test/vitest: 697
    passed em 39 arquivos) → todos verdes
  - npm --workspace @croquito/web run test → 697 passed (39 arquivos), incluído
    acima, listado também em separado por constar explicitamente na Validation do
    contrato
  - make provider-contract-demo → status human_review_required, 3 leituras;
    conferido manualmente que review-packet.json grava `ocr_corroborated: true`
    nas 3 leituras da fixture sintética (o OCR sintético confirma as três)

Validation skipped: none

Unavailable capabilities: none

Assumptions:
  - "asserção explícita num dos testes existentes ou novo" para as notas
    posicionais foi satisfeita reaproveitando os testes já existentes
    (test_ocr_corroboration_confirms_matching_readings,
    test_ocr_corroboration_flags_reading_without_spatial_evidence,
    test_ocr_corroboration_missing_arm_adds_a_single_note), que já continham
    asserções byte-idênticas sobre as notas antes desta mudança — não criei
    testes novos de nota porque os existentes já cobrem os três estados e uma
    duplicação não agregaria oráculo novo.
  - O tri-estado do campo web (`boolean | null | undefined`) segue o TypeScript
    já usado por `annotation_suggested`/campos opcionais vizinhos do contrato,
    sem normalizar `undefined` para `null` no cliente — decisão consistente com
    o resto de api.ts.

Remaining risks:
  - Nenhum identificado dentro do escopo da task. A F-010 completa (T1+T2) ainda
    não teve a aceitação real da revisão V17 citada no plano
    (human_gates: "aceitação real na revisão da V17"), que segue pendente de ato
    humano fora do escopo desta task.

Human decisions required:
  - Aceite do orquestrador/usuário sobre este diff antes do commit (BUILD REPORT
    não commita — combinado no contrato: "Sem COMMIT, o orquestrador commita com
    lista explícita de arquivos").
  - Aceitação real na revisão da V17 (human_gates do plan.md), fora do escopo
    desta task.
```

## Desvios conscientes do spec

1. **Estrutura de markup na lista** (`CroquiApp.tsx`, linha da lista): o contrato
   descreve o chip como `<small className="ocr-warning">` "junto ao rótulo de
   status" solto como filho direto do `<button>`. O `<button className="review-row">`
   é hoje `display: grid; grid-template-columns: 12px 1fr auto` com exatamente 3
   filhos (dot, label, status). Adicionar um 4º filho direto quebraria o grid (o
   4º item cairia numa linha implícita nova, desalinhado). Resolvido envolvendo o
   `<small>` de status existente e o novo `<small className="ocr-warning">` num
   `<span className="review-row-status">` só (flex-column), que ocupa a mesma
   3ª coluna `auto` do grid. Efeito visual é o descrito no contrato — chip junto
   ao rótulo de status, mesma linha da leitura — só a estrutura de DOM difere do
   texto literal do spec. Registrado aqui porque é o único ponto onde o markup
   não é byte-a-byte o que o contrato sugeriu.

2. **Cor do aviso**: o contrato não define token de cor; escolhido `#b42318`, o
   mesmo hexadecimal já usado em `.status-dot.rejected`, em vez de inventar uma
   variável `--danger` nova em `:root` (que não existe no design system atual do
   app — só há `--accent*`/`--ink*`/`--line`). Reaproveita cor já em uso pelo
   mesmo motivo (rejeitado = alerta) sem introduzir vocabulário novo de tema.

## Fora de escopo — visto e não implementado

- Rebaixar `status` da leitura por causa de `ocr_corroborated === false` (Out of
  scope explícito do contrato).
- Re-corroborar o valor corrigido após retificação (Out of scope explícito).
- Sugerir o valor lido pelo OCR na tela (Out of scope explícito — "fatia 3
  candidata").
- Lote de leituras sem 2ª testemunha (T1 é sobre lote de anotação; T2 não cria
  lote novo).
- Estilo de badge/pill mais elaborado para o aviso (ex.: fundo colorido, ícone
  SVG): mantido texto + cor mínima, coerente com "cor nunca é o único
  indicador" e com o pedido de CSS "mínimo se necessário".
