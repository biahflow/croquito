# F-023 — Survey Quality Score

## Status

`IN_PROGRESS`

> Especificada em 2026-08-20 (sessão de especificação, decisão humana na mesma
> sessão: rodada cobre spec + fatia 1, e a fatia 1 inclui a declaração humana
> de cadeia). Fatia 1 em execução.

## Classification

Não é `INTERFACE_CHANGE` de superfície nova — precedente da F-025: a fatia 1
entra na tela de revisão existente, nos padrões visuais estabelecidos
(`issue-panel`, `batch-hint`, badges de linha como `ocr-warning`,
`batch-controls`). Sem Design Approval Package.

## Priority

`HIGH` — segunda da fila combinada decidida em 2026-08-20
(F-025 → F-023 → F-019/F-018).

## Problem

O sistema já sabe quando o levantamento não sustenta o desenho — blockers do
solver, leituras não aplicadas com causa (F-025), resíduos, corroboração de
OCR — mas não devolve isso como avaliação do levantamento com recomendações de
campo ("meça a diagonal A–C"). As rodadas reais V14–V17 do Guaxindiba
mostraram que cada gargalo era do levantamento/funil, nunca erro de leitura do
modelo: o produto tinha os sinais e não os somava.

Um dos sinais já está inteiro e parado: o motor de fechamento de cadeias de
cotas (`services/worker/src/croquito_worker/dimension_closure.py`) — aritmética
`Decimal` sobre leituras confirmadas, tolerância pela meia-casa escrita,
anti-ruído medido no croqui real (busca livre dá 4 fechamentos e 213
quase-fechamentos; por isso só sugere o que fecha) — é código completo e
testado (golden 25,90 = 12,49 + 9,55 + 3,86) sem nenhum chamador: nem CLI, nem
API, nem tela. O revisor não vê nem as somas que fecham (corroboração de
graça) nem tem onde declarar a cadeia que o croqui afirma (o total escrito e
suas parcelas) para o produto conferir e avisar quando não fecha.

## Desired Outcome

Fatia 1 (esta rodada): o fechamento de cadeias vira sinal vivo na revisão.

- A resposta de review traz as cadeias que **fecham** entre as leituras
  confirmadas (sugestões, teto 12, só cota de planta) — o revisor vê
  "12,49 + 9,55 + 3,86 = 25,90 · confere" e as leituras participantes ganham
  um indício fraco de corroboração ("Σ fecha" — pista, não prova).
- O revisor pode **declarar** uma cadeia (total + ≥2 parcelas entre as
  confirmadas): ato humano com autoria, persistido na revisão de review. A
  cadeia declarada é re-conferida a cada leitura da revisão; mismatch vira
  aviso `DIMENSION_CHAIN_MISMATCH` (WARNING) visível na tela — nunca blocker,
  nunca trava export ("o croqui pode estar certo com a cota faltando").
  Cadeia cuja leitura foi retificada não some: aparece como `stale`
  (`CHAIN_READING_SUPERSEDED`).
- O CLI ganha `check-chains` (sugestão e verificação declarada), servindo à
  calibração com os pacotes reais V14–V17 sem depender da API.

Fatias ≥2 (fora desta rodada): o score agregado do levantamento — nota +
recomendações de campo acionáveis, agregando blockers, causas da F-025,
resíduos, corroboração de OCR e fechamento de cadeias — calibrado com as
amostras reais V14–V17. A declaração de cadeia desta fatia é insumo direto.

## Scope

Duas tasks, contrato aditivo (fatia 1):

1. **T1 — backend**: coluna `declared_chains_json` + migração aditiva 0006;
   `ReviewResponse.suggested_chains` (on-the-fly) e `.declared_chains`
   (re-verificadas); rota `POST /v1/jobs/{job_id}/review/chains`
   (declare/retract, `Idempotency-Key`, `base_version`); CLI `check-chains`;
   snapshot OpenAPI; testes API + worker.
2. **T2 — web**: tipos em `api.ts`; `chainSumLabel`/`chainCorroboratedReadingIds`
   em `labels.ts`; seção "Somas de cotas" na revisão com declaração/retração e
   avisos de mismatch/stale; badge "Σ fecha" na linha da leitura; testes
   vitest; asserção e2e.

## Out of Scope

- Score agregado e recomendações de campo (fatias ≥2 — o coração da F-023,
  depois da calibração com V14–V17).
- Promoção de cadeia a `Constraint` de cena (o docstring do motor exige ato
  próprio e contrato próprio; nenhuma cadeia toca geometria nesta fatia).
- Unificação com a conferência geométrica LSQ do `tracing.py` (o 6,60 fecha
  com 19,75+8,60−21,75 como constraint — mecanismo irmão, intocado).
- Mudança em `dimension_closure.py` e seus testes (só ganham chamadores).
- Qualquer mudança no portão `SceneRevision.export_errors()` ou em `blockers`
  (WARNING de cadeia nunca vira bloqueio).
- F-019/F-018; etiquetas da F-011.

## Acceptance Criteria

1. `make check` e `make test` verdes; `tests/e2e/test_full_flow.py` verde.
2. `GET /v1/jobs/{id}/review` devolve `suggested_chains` (lista, vazia sem
   confirmadas que fecham) e `declared_chains` com status
   `closes | mismatch | stale`; respostas idempotentes gravadas antes dos
   campos fazem replay sem quebrar.
3. Declarar cadeia válida que não fecha responde 200 com `mismatch` + issue
   WARNING `DIMENSION_CHAIN_MISMATCH`, e `blockers` fica inalterado; declaração
   malformada responde 422 problem+json `CHAIN_INVALID`; retração remove;
   retificação de leitura participante muda o status para `stale` sem apagar a
   cadeia.
4. Na tela: seção "Somas de cotas" com sugestões e declaradas (aviso de
   mismatch/stale nunca escondido, cor nunca é o único indicador), texto fixo
   de cautela sobre coincidência aritmética, badge "Σ fecha" nas leituras
   participantes, declaração por seleção de total + parcelas e retração por
   botão — tudo com `base_version` e `Idempotency-Key` como as demais
   mutações.
5. `croquito-demo check-chains` cobre os dois modos com exit codes 0/1/2 e
   `safety_status: observational_only` no modo sugestão.
6. Snapshot OpenAPI regenerado deliberadamente (`make openapi-snapshot`);
   API_CONTRACT.md atualizado; ROADMAP/STATUS refletem a rodada.

## Human Gates

Escopo da rodada e inclusão da declaração de cadeia decididos pelo usuário em
2026-08-20 (aprovação do plano da sessão). Aplicação da migração 0006 no
ambiente hospedado (junto das 0004/0005 pendentes) e push/deploy são atos do
usuário.
