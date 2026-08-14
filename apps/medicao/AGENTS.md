# AGENTS — apps/medicao

Estende o [AGENTS.md](../../AGENTS.md) da raiz. Leia também
[Valuation Context](../../docs/architecture/VALUATION_CONTEXT.md), a seção "Medição de
obra" do [FDD](../../docs/product/FDD.md) e o
[ADR-0020](../../docs/adr/0020-local-homologation-server-for-valuation.md).

## Boundary

Este app é a UI **local de homologação** da medição: apresenta a rodada, a revisão do
takeoff, a confirmação de código e o boletim, falando só com o servidor local
(`croquitodxf-valuation serve`). Ele não calcula dinheiro, não decide código, não chama
provider e não conhece a API `/v1` autenticada — quando a sessão autenticada da medição
existir, as telas e módulos puros migram; o client local é descartável.

## Regras

- React + TypeScript strict + Vite; sem lib de router, estado global, canvas ou UI kit.
- Todo texto visível em português do Brasil; identificadores em inglês.
- A tela **nunca** soma, multiplica ou arredonda dinheiro/quantidade: exibe as strings
  decimais que o servidor mandou (`format.ts` só troca pontuação, e é testado nisso).
- Mutações sempre citam o digest-base (`base_packet_sha256`/`base_assignments_sha256`)
  e nunca carregam `reviewer_id`, `reviewer_role`, `decided_at` ou `decision_id` — o
  servidor recusa e o client não tenta.
- Decisão é por item; nada nasce pré-marcado; "confirmar tudo" não existe.
- Cor nunca é o único indicador (estado por extenso + forma no SVG); erro é persistente
  (`role="alert"`), sucesso pode expirar; `LOCAL_STATE_MOVED` preserva o formulário e
  oferece recarregar.
- Chamada que grava artefato no servidor só por gesto explícito do usuário (ex.: o
  cálculo da shortlist fica atrás de botão que declara o que será gravado).
- Nenhum dado de obra em `localStorage`; nada de telemetry com conteúdo de catálogo ou
  medição.

## Testes mínimos

Módulos puros com `*.test.ts` irmão (vitest, environment node): derivação de etapas,
parsing do envelope de erro (incl. `LOCAL_STATE_MOVED`), formatação pt-BR com
round-trip textual, heurística fornecimento×execução com frases reais do catálogo,
viewport. `App.test.tsx` SSR estático do estado sem servidor, sem dados fabricados.

## Conclusão de mudança

Mudança de comportamento atualiza a seção de medição do FDD e os critérios VAL-*;
mudança no contrato do servidor local é feita primeiro em
`services/worker/src/croquitodxf_worker/valuation/local_server.py` (testes lá) e só
depois refletida aqui.
