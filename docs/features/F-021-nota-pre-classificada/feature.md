# F-021 — Nota pré-classificada na decisão da leitura

## Status

`DONE`

> Selecionada por decisão humana de 2026-08-20, durante a segunda revisão real do
> Guaxindiba: das dez leituras do pacote, oito eram grandezas de elevação (`h=`,
> mureta, traves, portão) que o revisor precisou reclassificar uma a uma como
> "Anotação da folha", sendo que o contrato do provider já classifica leitura como
> `note` e o texto `h=` já declara elevação. O usuário aprovou transformar esses dois
> sinais em sugestão pré-preenchida, mantendo o portão humano.

> Executada em 2026-08-20 (T1 worker + T2 web, builds completos, revisão do
> orquestrador linha a linha, portões integrados verdes) e **commitada na `main`** em
> `2711b5d` (worker + web + docs + testes + evidência). A **entrega foi aceita por ato
> humano** na série V14→V17 do Guaxindiba, registrada em `35bf5fa`
> ("aceitação real de F-021/F-022/F-024"); o `STATUS.md` já a descrevia em produção.
> Este flip apenas reconcilia o estado do roadmap, que ficara em
> `READY_FOR_HUMAN_REVIEW` depois do commit.

## Classification

Não é `INTERFACE_CHANGE`: nenhuma superfície nova — a sugestão entra no formulário de
decisão existente, no mesmo padrão do `suggestedAxisHint` que já existe
(`apps/web/src/labels.ts:275-292`). Sem Design Approval Package.

## Priority

`HIGH` — é o maior corte de gesto manual por real investido na revisão do croqui, e a
próxima revisão real (upload novo do Guaxindiba) é o teste de aceitação natural.

## Problem

Dois sinais que o pipeline já produz são descartados antes de chegar ao revisor:

1. **`kind="note"` do provider morre no worker.** O contrato de extração
   (`measurement-extraction@1.1.1`, `providers.py:318-330`) emite `note` para leitura
   que é recado, mas `_measurement_kind()` (`provider_review.py:141-145`) só aceita o
   enum `MeasurementKind` do core — `note` vira
   `READING_{n}_UNSUPPORTED_UNIT_OR_KIND` e a leitura sai do pacote.
2. **O padrão `h=` chega ao revisor sem nenhuma dica.** Leituras como
   `muro Vizinho h=3,80` chegam como `height` e o formulário de decisão pré-seleciona
   o primeiro candidato geométrico (`CroquiApp.tsx`, `loadReview`), induzindo ao erro
   que trava a exportação com `MEASUREMENT_MISMATCH` — o revisor precisa saber
   escolher "Anotação da folha" sozinho, oito vezes por prancha.

## Desired Outcome

Na decisão de uma leitura que o pipeline reconhece como recado (sinal do modelo ou
padrão `h=`/elevação no texto), o formulário chega com "Anotação da folha — não mede
um elemento" pré-selecionada e uma frase dizendo por quê. O revisor confere a
evidência, escreve a justificativa e confirma — ou discorda e troca. Nenhuma decisão
é tomada sem humano; muda só quem digita a hipótese inicial.

## Scope

1. **Worker** — leitura `kind="note"` completa (com valor e `target_hint`) deixa de
   ser descartada: entra no pacote com `kind` neutro (`length`) e um campo novo
   `annotation_suggested: bool = False` em `DimensionReading`
   (`services/worker/src/croquito_worker/review.py:116-145`), ligado quando o sinal
   veio do modelo. Leitura `note` sem valor continua descartada (nota de segurança
   própria, distinta da atual). `ReviewPacket` não entra no manifesto de contratos
   gerados (verificado: serialização é o Pydantic da rota, `contracts.manifest.json`
   não o lista) — sem `make contracts`.
2. **Web (sinal do modelo)** — `ReviewReading` (`apps/web/src/api.ts:46-60`) ganha
   `annotation_suggested?: boolean`; quando verdadeiro, a decisão nasce com
   `ANNOTATION_OPTION` pré-selecionada e a frase "sugestão: anotação da folha (o
   modelo leu como recado, não como cota)".
3. **Web (padrão de texto, client-side)** — heurística em `labels.ts` no molde de
   `suggestedAxisHint`: `raw_text` que casa com padrão de elevação (`h=`, `h =`,
   variações com prefixo de elemento) produz a mesma pré-seleção com frase própria
   ("sugestão: anotação da folha (o texto declara altura de elemento)"). **Vale para
   pacote já processado** — o job atual do Guaxindiba se beneficia sem reprocessar.
4. **Precedência e recuo** — sugestão nunca sobrescreve decisão registrada nem
   rascunho da conversa (o efeito de pré-preenchimento do chat continua vencendo,
   `CroquiApp.tsx`); trocar a seleção manualmente desliga a sugestão para aquela
   leitura na sessão.
5. **Docs** — `docs/ai/PROMPT_CONTRACTS.md` passa a dizer o destino real de
   `note`/`count`/`unknown` (hoje omite que são descartados);
   `docs/architecture/API_CONTRACT.md` documenta o campo novo do pacote.

## Out of Scope

- Confirmar automaticamente qualquer leitura (o portão humano é invariante).
- `count`/`unknown` do provider (continuam descartados como hoje, agora documentados).
- Sugerir o alvo da nota presa na etapa de traçado (fica para a rodada seguinte, com
  F-018/F-019).
- Mudar prompt/versão de `measurement-extraction` (o sinal já existe na 1.1.1).
- Colisão de vocabulário com `kind: "note"` de `apps/web/src/capture.ts:36-47`
  (conceito do traçado): não renomear nada lá; o campo novo usa outro nome
  (`annotation_suggested`) justamente para não colidir.

## Acceptance Criteria

1. `make check` e `make test` verdes.
2. Teste novo no worker: extração com `kind="note"` completa produz leitura com
   `annotation_suggested=true` e kind `length`; sem valor, é descartada com a nota
   nova; `count`/`unknown` seguem descartados com
   `READING_{n}_UNSUPPORTED_UNIT_OR_KIND` (hoje só há cobertura indireta de `count`
   em `tests/worker/test_transcription.py:299-338`).
3. Teste novo no web: leitura com `annotation_suggested` nasce com
   `ANNOTATION_OPTION` selecionada e frase visível; leitura `h=3,80` sem o campo
   também; leitura `25,90` sem padrão não ganha sugestão; decisão registrada e
   rascunho do chat nunca são sobrescritos.
4. O payload da decisão confirmada com a sugestão aceita é o mesmo de hoje
   (`annotation: true`, sem `association_proposal_id`) — nenhum campo novo no comando.
5. Snapshot OpenAPI: mudança aditiva apenas.

## Constraints

- O texto é o indicador; cor só reforça (convenção do web).
- A regra da API não muda: anotação com `association_proposal_id` continua 422.
- Frases de sugestão em português, no vocabulário já usado ("anotação da folha").

## Dependencies

Nenhuma externa. Independente de F-022 (Document AI).

## Human Gates

- Aprovação do plano de execução antes do build (processo padrão).
- Nenhum gate de produção: sem migração, sem chamada paga, sem infra.
