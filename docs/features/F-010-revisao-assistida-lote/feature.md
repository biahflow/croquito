# F-010 — Revisão assistida em lote (fatia 1: anotações sugeridas)

## Status

`DONE`

> F-010 nasceu no Roadmap na rodada da F-009 como "revisão assistida em lote (a
> definir em contrato)". A fatia 1 foi selecionada por decisão humana de
> 2026-08-20, na revisão da V17 do Guaxindiba: com ~8 leituras chegando
> pré-classificadas como anotação (F-021), o revisor pediu "o sistema traz
> filtrado em lote e eu passo o olho e confirmo — não quero uma a uma". A
> fronteira é dele: lote SÓ para as sugeridas como anotação; cota de chão
> continua individual porque cada uma declara associação e eixo próprios.

> Fatia 1 **commitada na `main`** em `e617129` (painel de lote na etapa de decisões).
> O único gate pendente era o deploy pela esteira; **a entrega foi aceita por ato
> humano em 2026-08-25** (Daniel Campos), confirmando deploy realizado. Este flip
> reconcilia o roadmap, que ficara em `READY_FOR_HUMAN_REVIEW`.

## Classification

Não é `INTERFACE_CHANGE` de superfície nova — acrescenta um painel de lote na
etapa de decisões existente, no padrão visual do lote de propostas que já existe.

## Priority

`HIGH` — multiplica o ganho da F-021 na revisão real; a V17 é o teste de aceitação.

## Problem

A F-021 pré-classifica, mas a confirmação continua leitura a leitura: recorte,
justificativa, clique — ~8 vezes por prancha para um grupo homogêneo com o mesmo
destino. A API já aceita 1-50 decisões atômicas por chamada com justificativa por
item (`SubmitReviewDecisionsRequest`, main.py:364-366; handler 2700-2894); quem
restringe a 1 é o front. O precedente de UX e de semântica (justificativa única
do lote replicada por item) já existe no lote de propostas.

## Desired Outcome

Na etapa de decisões, as leituras sugeridas como anotação chegam pré-marcadas ☑
num painel de lote; o revisor desmarca o que discordar, escreve UMA justificativa
nas suas palavras e clica "Confirmar N como anotação". Cada leitura grava a sua
`HumanDecision` individual com essa palavra — auditável uma a uma como hoje. O
gate humano não muda de natureza; muda a granularidade do gesto, por escolha do
revisor.

## Scope (fatia 1)

Só `apps/web` + docs — nenhuma mudança de API:

1. `api.ts`: `submitReviewDecision` generalizada para lista (1..50).
2. Módulo puro `readingBatch.ts`: `suggestedAnnotationIds` +
   `buildAnnotationBatch` (justificativa replicada por item; sem
   `association_proposal_id`), com testes.
3. `CroquiApp.tsx`: checkbox por linha sugerida sem decisão (linha reestruturada
   — button aninhado é inválido), painel de lote no padrão `batch-controls`,
   pré-marcação semeada por versão da revisão, envio, conflito e toast.
4. FDD: parágrafo do lote na seção da decisão.

## Scope (fatia 2 — ⚠ segunda testemunha, selecionada em 2026-08-20)

Caso fundador: na V17 a extração leu `24,75` onde a folha diz `19,75`; o Document
AI leu certo e o pacote carregava `READING_9_OCR_EVIDENCE_MISSING` — nota
posicional, invisível na UI. O erro atravessou solve, aprovação e export, e caiu
só na conferência visual do DXF.

1. Worker: `DimensionReading.ocr_corroborated: bool | None` (True = OCR viu o
   mesmo texto na região; False = OCR rodou e não viu; None = braço
   ausente/falhou). Registro de nascimento da observação — retificação não o
   reescreve. Notas posicionais intactas.
2. Web: `ocrWitnessHint` em labels (frase só para False; silêncio para
   True/None); chip "⚠ sem 2ª testemunha" na linha da lista; frase completa no
   painel de decisão junto aos demais hints.
3. Docs: API_CONTRACT (tri-estado e semântica), MODEL_ROUTING (uma frase), FDD.

## Out of Scope (fatias futuras, explícitas)

- Fatia 3 candidata: sugerir o valor que o OCR leu ("a folha parece dizer
  19,75") — exige levar as linhas de OCR ao pacote.
- Rebaixar status por corroboração (calibração de auto-pass; precisa de mais
  rodadas).
- Re-corroborar o valor corrigido na retificação.

- Lote de REJEIÇÃO e lote de cotas de chão.
- Auto-pass calibrado por confiança (o ">90% automático" — depende de dado das
  rodadas reais e da F-023).
- Nota presa pré-apontada pelo candidato geométrico (anotada para F-011).
- Campo de rastreio de lote em `HumanDecision` (correlação por
  `review_revision_id` compartilhado atende à fatia).

## Acceptance Criteria

1. `make check` e `npm --workspace @croquito/web run test` verdes.
2. Testes puros de `readingBatch` cobrindo: sugeridas sem decisão entram,
   decididas/sem sugestão não; lote replica a justificativa; vazio e >50
   recusados.
3. Payload por item idêntico ao da confirmação individual de anotação
   (`action: "confirm"`, `annotation: true`, sem associação).
4. `REVISION_CONFLICT` no lote recarrega e preserva a seleção para reenvio.
5. Fluxo individual, chatPrefill e retificação intocados.

## Human Gates

Plano aprovado em 2026-08-20 (sessão da seleção). Deploy pela esteira.
