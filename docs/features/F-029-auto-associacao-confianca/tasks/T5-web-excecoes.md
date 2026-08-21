# F-029 / T5 — Revisão web só de exceções

- Feature: [F-029](../feature.md) · Plano: [plan.md](../plan.md)
- Papel: builder · Esforço relativo: M · Depende de: T4
- **GATE ANTES DE INICIAR: mock simples da vista de exceções aprovado por
  ato humano** (registrado no plano). Sem o aceite, reportar bloqueio.

## Objetivo

A tela de revisão passa a dar visão de exceções quando existem
auto-decisões: contadores `auto-associadas / revisão necessária / não
resolvidas`, badge visível na linha auto-decidida e filtro para ver só o que
precisa de humano. Sem auto-decisões (flag desligada no backend), a tela é
idêntica à de hoje.

## Fontes a ler antes de editar

- `AGENTS.md` (raiz) e `apps/web/AGENTS.md`.
- `apps/web/src/CroquiApp.tsx` — arquivo único da tela (5784 linhas);
  padrões a reusar: badge "Σ fecha" (linha ~601), `chain-panel` (~682),
  `batch-controls` (~751, ~3437, ~3993), `ocr-warning` (~3567, ~3744),
  consumo de campos opcionais da review com `?? []` (~3588-3589).
- `apps/web/src/api.ts` e `apps/web/src/labels.ts` — tipos e rótulos da
  jornada de croqui (as árvores `medicao/`, `orcamento/`, `plataforma/` não
  são desta jornada).
- Campos novos da ReviewResponse (T2/T4): confidências, shadow, métricas e
  proveniência de ator-máquina na decisão.
- Mock aprovado (referência anexada ao evidence da feature na aprovação).

## Escopo

1. Tipos em `api.ts` para os campos novos (opcionais — resposta antiga sem
   eles continua válida).
2. `labels.ts`: rótulos em português de obra para contadores, badge de
   auto-decisão e filtro.
3. Tela: contadores no topo da revisão; badge na linha auto-decidida com
   texto + ícone (cor nunca é o único indicador — invariante do repo);
   filtro "só exceções" (padrão dos `batch-controls` existentes); a linha
   auto-decidida exibe a proveniência de máquina e a ação de retificar
   continua acessível nela.
4. Avisos críticos nunca escondidos pelo filtro: blockers e issues críticas
   aparecem mesmo com "só exceções" ativo.
5. Testes vitest: contadores com/sem auto-decisões; filtro não esconde
   blocker; resposta sem os campos novos renderiza como hoje; badge presente
   e acessível (aria).

## Fora de escopo

Redesenho da tela; edição de forma (F-018); preview da cena (F-019);
qualquer mudança de backend; auto-aprovação de qualquer coisa.

## Critérios de aceite

1. Com resposta sem campos novos: tela idêntica à atual (teste).
2. Com auto-decisões: contadores corretos, badge em toda linha
   auto-decidida, filtro funcional, retificação acessível, blockers sempre
   visíveis.
3. `make check` (inclui `tsc -b` + build) e testes vitest verdes.
4. Conformidade visual com o mock aprovado registrada no BUILD REPORT
   (desvios conscientes listados).

## Baseline

`main` com T4 integrada, portões verdes, mock aprovado. Falha nova em área
não tocada: parar e reportar.

## Validação (comandos reais)

```bash
make check
npm --workspace @croquito/web run test
make test
```

## Gates e relatório

Mock aprovado é pré-condição de entrada. Encerrar com `BUILD REPORT`
completo (`docs/engineering-os/agents/builder.md`).
