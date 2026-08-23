# F-011 — Evidência de encerramento

feature_id: F-011
status: `DONE` (encerrada por ato humano em 2026-08-23)
data deste pacote: 2026-08-23

> Este não é um pacote de execução: **nada foi implementado para esta feature**. É o registro
> da conferência que a encerrou, e a evidência é o código que já cumpria o pedido antes de a
> feature existir.

## 1. Gates humanos

| Gate | Estado |
| --- | --- |
| Seleção | Exercida em 2026-08-19 |
| Planejamento | **Nunca ocorreu** — não há `plan.md` nem Task Contract |
| **Encerramento** | **Exercido por ato humano em 2026-08-23**, sobre a auditoria da seção 3 |

O ato de encerramento decidiu explicitamente uma segunda coisa: que "uma cota por vez dentro
da etapa Decisões" **não** era o que esta feature pedia, e fica fora dela.

## 2. Baseline

Não se aplica: nenhuma mudança foi feita. `make check` e `make test` seguem verdes no HEAD, e
o commit que fecha esta feature toca somente documentação.

## 3. A conferência

Feita por leitura de código em 2026-08-23, pelo modelo da sessão.

| O que a F-011 pedia | Onde já estava |
| --- | --- |
| Etapas em vez de formulário aberto | `apps/web/src/journey.ts`, `deriveJourney` → `Decisões → Traçado → Aprovação → Exportação` |
| Próxima etapa só habilita quando a atual é cumprida | `JourneyStepStatus = "blocked" \| "available" \| "done"`; `activeStep` é a primeira em aberto e nunca é bloqueada |
| O bloqueio explicado | `blockedReason`, em língua de obra — o docstring exige: "os motivos de bloqueio são frases de obra e precisam ser testáveis sem DOM e sem rede" |
| Uma etapa por vez na tela | `apps/web/src/CroquiApp.tsx`, `visibleStep`; `:1638` — "Etapa bloqueada nunca abre, nem por um clique que envelheceu" |

### A data é o achado

```text
2026-08-17  01e5340  feat(web): casca de duas jornadas e fronteira de rota (F-003 T14/T15/T16)
                     → deriveJourney passa a ser chamado em CroquiApp.tsx
2026-08-19           F-011 é registrada no roadmap pedindo isso
```

A feature nasceu **dois dias depois** de o pedido já ter sido atendido.

## 4. Validação

Nenhuma executada para esta feature, porque nenhuma mudança de código foi feita. A validação
que sustenta o comportamento é a que já existe para o módulo: `journey.ts` é puro e coberto
por vitest, e a jornada aparece em `CroquiApp.test.tsx`.

## 5. Riscos remanescentes

- **A etapa Decisões continua mostrando todas as cotas de uma vez.** Está declarado fora de
  escopo por decisão humana do mesmo ato, e não é dívida oculta: está escrito no contrato.
- **Nenhum outro.** Não há código novo, migração, rota ou artefato para carregar risco.

## 6. Decisões humanas pendentes

Nenhuma. O encerramento foi o último ato.
