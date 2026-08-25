# F-025 — Consultor do traçado

## Status

`DONE`

> T1 e T2 integradas e revisadas na branch `f-025-consultor-tracado` em
> 2026-08-20 ([evidência](evidence.md)) e **mergeadas na `main`** em `d110094`.
> A **aceitação real na prancha do Guaxindiba foi confirmada por ato humano em
> 2026-08-25** (Daniel Campos). Este flip reconcilia o roadmap, que ficara em
> `READY_FOR_HUMAN_REVIEW` após o merge.

> F-025 nasceu no Roadmap em 2026-08-20, na primeira exportação real (V17 do
> Guaxindiba): o aceite travou em "0 exatos, 11 não aplicadas" por três causas
> que o solver conhecia e não contava — formas freeform semeadas por rascunho
> anterior às decisões; associação herdada no vizinho errado da escrita; 1,5 e
> 8,6 disputando o mesmo vão. O diagnóstico foi feito à mão, reproduzindo o
> solve localmente com dados reais. O desenho é do usuário, na mesma sessão:
> "ao clicar em Aceitar traçado, ver esses erros e corrigir".

## Classification

Não é `INTERFACE_CHANGE` de superfície nova — decisão humana de 2026-08-20
(sessão de especificação): o consultor entra na seção `trace-status` que já
existe na etapa de traçado, no padrão visual estabelecido do `blocker-list`
(causa em língua de obra + código cru) e dos botões de lote (`batch-controls`,
F-010). Sem Design Approval Package.

## Priority

`HIGH` — decisão humana de 2026-08-20: primeira da fila combinada
(F-025 → F-023 → F-019/F-018); a prancha final do Guaxindiba é o teste de
aceitação real.

## Problem

Quando uma leitura confirmada não vira vão no traçado, o produto hoje diz só
"Não aplicada: <leitura>" — `TraceSolveResponse.unapplied_reading_ids` é uma
lista plana de IDs. A causa é conhecida no ponto exato do descarte
(`_span_from_reading` tem reading, alvos, topologia e faixas quando decide
retornar `None`), mas não é registrada nem propagada: a única sobra é uma
`Issue` de mensagem fixa, igual para as 11 leituras da V17. Duas cotas
disputando o mesmo vão nem sequer têm detecção nomeada (círculo tem,
`TRACE_CIRCLE_READINGS_CONFLICT`; vão não) — o LSQ reparte o erro e o que
emerge é o blocker agregado `NUMERIC_RESIDUAL_EXCEEDS_TOLERANCE`, sem dizer
quais leituras colidem. E conferir as âncoras de um vão aplicado (o
"19,75 amarra 42,85→23,10" da prancha final) exige hoje inspecionar a cena à
mão. O revisor fica sem causa, sem conserto e sem conferência — o diagnóstico
que custou uma reprodução local inteira era calculável de graça.

Na raiz da causa 1: a semente de flags do rascunho web
(`defaultFlagsForProposal`) decide `freeform` apenas quando a forma entra na
montagem; decisões e associações que chegam depois não re-semeiam, e o flag
errado sobrevive até o solve.

## Desired Outcome

Ao aceitar o traçado, cada leitura não aplicada chega com causa estruturada e
em língua de obra, e as causas com conserto mecânico oferecem o gesto de um
clique — aplicado ao rascunho do aceite, nunca enviado sozinho: tratar a forma
como retangular, amarrar a outro candidato, declarar o eixo, manter formas
separadas, retificar o valor. Vãos em disputa são nomeados par a par. Cada
leitura aplicada mostra as âncoras em metros. O rascunho re-semeia os flags
`freeform` default quando decisões mudam, sem nunca tocar flag alterado à mão.
Diagnóstico 100% determinístico dos dados que o solver já tem — sem IA, sem
mudança de gate: quem assina continua sendo o profissional, pelo mesmo botão.

## Scope

Duas tasks, contrato aditivo:

1. **T1 — worker/API**: causa estruturada por leitura não aplicada
   (`unapplied_readings`), detecção par-a-par de vão em disputa
   (`contested_spans`), âncoras por leitura aplicada (`applied_spans`);
   propagação resultado → registro → `TraceSolveResponse` (campos novos,
   `unapplied_reading_ids` preservado); `Issue`
   `CONFIRMED_READING_NOT_APPLIED` com a frase da causa; migração aditiva.
2. **T2 — web**: painel do consultor na seção `trace-status` (causa em língua
   de obra + código cru + botões de conserto que alteram o `traceDraft` com
   revisão antes do envio); âncoras por leitura aplicada; re-semeadura dos
   flags não tocados à mão (`manualFlagIds` no rascunho e no storage).

## Out of Scope

- A etiqueta "pendente" repetida na lista de propostas do caminho de
  aproximação (registrada para F-011).
- O chat citando o diagnóstico do traçado (fatia futura; os rascunhos tipados
  do ADR-0023 já cobrem o gesto de aplicar sem enviar).
- Qualquer mudança no portão `SceneRevision.export_errors()` ou no
  comportamento do LSQ (repartir o erro entre cotas em conflito continua — o
  consultor nomeia, não esconde).
- Score/fechamento do levantamento (F-023) e preview visual da cena (F-019).
- Auto-aplicação de qualquer conserto sem clique do revisor.

## Acceptance Criteria

1. `make check` e `make test` verdes; `make solver-eval` e
   `tests/e2e/test_full_flow.py` verdes.
2. Nos cenários sintéticos das três causas da V17, `TraceSolveResponse` traz
   causa estruturada por leitura não aplicada, o par em disputa nomeado e as
   âncoras das aplicadas; payload antigo (`unapplied_reading_ids`, blockers)
   inalterado.
3. No web, cada causa aparece em língua de obra com o código cru visível;
   cada conserto de um clique altera apenas o rascunho e exige novo
   "Aceitar traçado" — nenhum caminho novo de escrita ao domínio.
4. Flag `freeform` alterado à mão nunca é re-semeado; não tocado re-semeia
   quando a leitura correspondente é confirmada/associada depois; rascunho
   antigo no storage carrega sem erro.
5. Snapshot OpenAPI regenerado deliberadamente (`make openapi-snapshot`) e
   API_CONTRACT/FDD/TRACE_STAGE atualizados.

## Human Gates

Classificação, prioridade e escopo decididos pelo usuário em 2026-08-20
(sessão de especificação). Merge da branch e aceitação real na prancha final
do Guaxindiba são atos do usuário.
