# T5 — Conclusão com bloqueio por crítico (prancha 5 do DAP)

## Identity

```text
feature_id: F-032
task_id: T5
parent_plan: docs/features/F-032-app-levantamento-campo/plan.md (plano "MVP local, fatias 1–3")
depends_on: T3, T4 (entregues e commitadas)
```

## Goal

A tela "Concluir levantamento" da prancha 5: a lista escrita dos findings do motor com
o semáforo, crítico bloqueando a conclusão com o motivo no rótulo do botão, pendência
não crítica mantida com justificativa registrada, e a conclusão marcando o
levantamento como concluído localmente (refletindo na lista de ordens, prancha 1a
"Concluída").

## Scope

- `apps/field/src/domain/**`: extensão mínima — `Survey.status: "collecting" |
  "concluded"` (default `collecting`; surveys persistidos sem o campo leem como
  `collecting`), `Survey.waivers: Waiver[]` (`{ id, finding_code, ref_key,
  justification, created_at }`), comandos puros `waiveFinding` (erro `EMPTY_TEXT`;
  `UNKNOWN_FINDING_REF` não existe — o waiver referencia código+ref, não valida
  contra findings correntes, que mudam) e `concludeSurvey` (falha
  `CANNOT_CONCLUDE` se houver finding critical nos findings passados como argumento;
  falha `ALREADY_CONCLUDED` se já concluído), com testes no padrão existente.
- `apps/field/src/ui/**`: tela ConcludeScreen; entrada a partir da coleta (botão/rota
  no fluxo existente sem redesenhar a bottombar — usar o menu Adicionar OU um chip do
  banner, a escolha menos invasiva à prancha 3a, declarada no report); navegação de
  cada item crítico de segmento para a coleta com o segmento selecionado; badge
  "Concluída" derivada de `status` na OrdersScreen; coleta em survey concluído vira
  somente leitura simples (comandos bloqueados com aviso escrito — sem tela nova).
- Textos como na prancha 5 (estado escrito, área derivada NÃO entra — não existe no
  motor; não inventar).

## Out of Scope

- Envio/sync do pacote (o banner "será enviado quando houver conexão" da prancha 5b
  vira "guardado neste aparelho; o envio chega com a sincronização" — copy não é
  aprovada pelo DAP, manter o espírito).
- Reabrir levantamento concluído (decisão futura; não criar comando de reabertura).
- `validateSurvey`/regras novas; `src/storage/**`; `services/**`; `docs/**`.

## Especificação

1. **ConcludeScreen**: findings do motor renderizados como os cards da prancha 5
   (crítico/atenção/ok pelo semáforo, sempre escritos). Critical de segmento
   (`SEGMENT_WITHOUT_MEASUREMENT`) navega para a coleta com o segmento selecionado ao
   toque. Warning mostra a justificativa do waiver quando existir; sem waiver, ação
   "Justificar" abre a TextEntryScreen existente e grava via `waiveFinding`
   (`ref_key` = primeiro ref do finding, ou o código quando sem refs).
2. **Botão Concluir**: desabilitado com "Concluir (N itens críticos abertos)" quando
   houver critical; habilitado chama `concludeSurvey` via `applyCommand` e volta às
   ordens com a ordem marcada "Concluída".
3. **Resumo**: usar `summarize` do motor ("X de Y medidas confirmadas · perímetro…")
   — nada recalculado na UI.

## Acceptance Criteria

1. `npm run field:test` exit 0 com testes novos de `waiveFinding`, `concludeSurvey`
   (bloqueio com critical, dupla conclusão) e status default de survey antigo.
2. `npm run field:check`, `make check`, `make test` exit 0.
3. Roteiro manual no report: com um segmento sem medida → Concluir bloqueado com
   motivo no rótulo e toque no crítico levando ao segmento; medir → warning de foto
   justificada via TextEntry → Concluir habilitado → ordem aparece "Concluída" na
   lista; reload preserva tudo; coleta do survey concluído recusa comandos com aviso.
4. `git status --porcelain` só no escopo declarado.

## Validation

```text
baseline: make check && make test verdes na branch após T4 revisada e commitada (o
  modelo principal registra o commit no handoff); field: contagem do momento.
required: unit: npm run field:test
required: typecheck+build: npm run field:check
required: monorepo: make check && make test
```

## Required Capabilities

```text
READ: repositório; DAP ../mock/ (prancha 5); domínio e UI como entregues
WRITE: escopo declarado
VALIDATE: comandos acima
COMMIT: forbidden
```

## Context to Read First

`../mock/campo.html` + `05-conclusao.png`; `src/domain/validation.ts` (findings e
summarize); `src/ui/FieldApp.tsx` (fila, apply(build), modos); `src/ui/
TextEntryScreen.tsx` (reuso).

## Known Risks

- Recriar regra de validação ou "área derivada" na UI — proibido; renderizar o motor.
- Concluir sem passar por comando/applyCommand.
- Esquecer retrocompatibilidade de surveys persistidos sem `status`/`waivers`.

## Human Gates

Desvio material da prancha 5; reabertura de concluído (não implementar).

## Reporting

BUILD REPORT completo, com o roteiro manual executado.
