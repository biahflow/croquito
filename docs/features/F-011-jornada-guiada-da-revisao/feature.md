# F-011 — Jornada guiada da revisão

## Status

`DONE`

> **Encerrada por ato humano em 2026-08-23, sem nunca ter tido plano nem tasks**, porque a
> auditoria daquele dia encontrou o que ela pedia **já no ar** — e já no ar quando ela foi
> registrada.
>
> Este contrato existe para registrar o encerramento, não para especificar trabalho. Ele é
> escrito depois do fato, e diz isso.

## Classification

`NO_INTERFACE_CHANGE` — nenhuma superfície nasce daqui. A que responde ao pedido já existia.

## Problem

Registrada em 2026-08-19, por seleção humana, na primeira revisão da porta nova: o
responsável queria a experiência da revisão como **jornada guiada** — a próxima tarefa
habilitando só quando a atual é cumprida, no lugar de um formulário aberto.

## O que a auditoria de 2026-08-23 encontrou

`apps/web/src/journey.ts` já entregava exatamente isso:

- `deriveJourney` deriva quatro etapas — **Decisões → Traçado → Aprovação → Exportação**;
- `JourneyStepStatus` tem `blocked`, e a etapa bloqueada carrega `blockedReason` **em língua
  de obra** ("faltam 3 leituras por decidir"), não um código;
- `activeStep` é a primeira etapa em aberto e **nunca** cai numa bloqueada;
- `apps/web/src/CroquiApp.tsx` mostra uma etapa por vez, e o comentário em `:1638` registra a
  regra: "Etapa bloqueada nunca abre, nem por um clique que envelheceu";
- o módulo é puro e testado sem DOM, porque "os motivos de bloqueio são frases de obra e
  precisam ser testáveis".

O `deriveJourney` entrou na tela em **2026-08-17** (`01e5340`, F-003 T14–T16) — **dois dias
antes** de esta feature ser registrada.

Nada foi implementado para fechá-la. O que fechou foi a conferência.

## Acceptance Criteria

Verificados por leitura do código em 2026-08-23, não por execução de tarefa:

1. A revisão apresenta uma etapa por vez, e não todas ao mesmo tempo. ✅
   `CroquiApp.tsx`, `visibleStep`.
2. Etapa cujo pré-requisito não foi cumprido fica indisponível. ✅ `status: "blocked"`.
3. O bloqueio diz o porquê, em linguagem do domínio. ✅ `blockedReason`.
4. A tela espelha o servidor e não reimplementa o portão. ✅ O docstring do módulo declara:
   "A máquina de estados real é do servidor; esta derivação apenas ESPELHA o que a página já
   carregou (…) Nenhum gate daqui substitui os guards da API".

## Out of Scope

- **Uma cota por vez dentro da etapa Decisões.** Hoje a etapa mostra todas as leituras juntas.
  Isso **não** foi pedido nesta feature e foi explicitamente separado dela no ato de
  encerramento (decisão humana de 2026-08-23). Vira trabalho novo só com seleção humana nova.

## Human Gates

**Encerramento**: exercido por ato humano em 2026-08-23, sobre a auditoria acima.

## O que fica de lição

Esta feature consumiu um ID e apareceu por quatro dias como trabalho aberto sem sê-lo. A
regra que teria evitado isso é a mesma já registrada noutro lugar do processo: **conferir se
o artefato existe antes de propor**. Um item de roadmap nascido de uma impressão de tela vale
uma leitura do código antes de virar linha.

## References

- [Roadmap](../../product/ROADMAP.md) — a linha da F-011 e a auditoria de 2026-08-23
- `apps/web/src/journey.ts`, `apps/web/src/CroquiApp.tsx`
