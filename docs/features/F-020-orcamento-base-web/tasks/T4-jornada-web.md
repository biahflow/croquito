# T4 — Terceira jornada "Orçamento" na SPA

Task Contract no formato do template global (`docs/engineering-os/templates/task.md`),
derivado do [plano válido](../plan.md). Autossuficiente: assuma o Core, este
contrato, o [Design Approval Package aprovado (revisão 1)](../mock/README.md) e o
repositório. O design aprovado é vinculante na composição; TODO texto é proposta
(copy final é gate humano aberto — use o texto do mock como rascunho, não como
aprovado).

## Identity

```text
feature_id: F-020
task_id: T4
parent_plan: docs/features/F-020-orcamento-base-web/plan.md
depends_on: [T1, T3]
```

## Goal

A orçamentista alcança o orçamento-base pelo produto: terceira jornada no seletor,
rota própria, cadeia inteira (abertura → cascata → prancha/extração → revisão do
takeoff → códigos com fonte → BDI e montagem → planilha) consumindo as rotas
`/v1/estimate-rounds*` de T3 e os tipos gerados de T1.

## Baseline

T1 e T3 integrados na branch; `make check`, `make test` e
`npm --workspace @croquito/web run test` verdes.

## Scope

Em `apps/web/src/route.ts` (155 linhas):

- `Route` (linha 33-36) ganha `{kind: "orcamento"; roundId: string | null}` com
  parâmetro `ORCAMENTO_PARAM = "orcamento"`. Precedência documentada passa a
  `job > rodada > orcamento > plataforma` (`readRoute` 117-134, `routeSearch`
  141-154, comentário 109-115 atualizado). `entryRedirect` (83-107) não muda.

Em `apps/web/src/App.tsx`:

- Terceiro botão no seletor de jornadas (padrão dos existentes, linhas ~123-140,
  com `aria-current`), renderização condicional de `OrcamentoApp` no switch de
  `route.kind` (linhas ~523-536).

Diretório novo `apps/web/src/orcamento/` — espelho ESTRUTURAL de `src/medicao/`
(leia `api.ts` 1-26 e `etapas.ts` 1-14 antes; as invariantes valem aqui):

- `api.ts`: cliente das rotas de T3 (nomes/paths/payloads estão no contrato T3 —
  não invente rota). Identidade/carimbo nunca viajam do cliente; toda mutação
  cita `base_version` + `Idempotency-Key`; `Decimal` sempre string (o
  `bdi_percent` viaja como string). Tipos de domínio de `@croquito/contracts`
  (`Estimate` gerado por T1) — nunca redigitados.
- `etapas.ts`: etapas como espelho do estado do servidor (`current_stage` de T3),
  nunca máquina de estados própria.
- `errors.ts` + labels: tradução por tabela dos códigos novos
  (`ESTIMATE_CASCADE_ORIGIN_DUPLICATE`, `ESTIMATE_LINE_BDI_MISMATCH`,
  `ROUND_STAGE_NOT_READY`, `REVISION_CONFLICT`, …) no padrão de
  `medicao/errors.ts` (32-69) — nunca mensagem inventada, banner próprio para 409.
- `OrcamentoApp.tsx`: as telas e estados do pacote aprovado — abertura (lista,
  vazio, carregando, erro), cascata numerada e reordenável (a ordem é a regra),
  prancha/extração (cinco estados), revisão do takeoff, códigos com selo de
  fonte por candidato (origem + posição na cascata), BDI e montagem (percentual
  único; BDI por grupo NÃO é renderizado — nem controle desligado), planilha
  (auditoria ok / reprovada como TELA dizendo "nada foi publicado"), 403 sem
  nomear papel, 409 e recusa de domínio traduzida.
- Linha fixa declarando o momento da jornada (o aviso permanente do orçamento:
  preço vem da cascata; nada daqui alcança um boletim). SÓ no orçamento — o
  pacote diz "o da medição continua o que já é": não toque em `src/medicao/`.
- `styles.css` do diretório: composição sobre os tokens e classes existentes de
  `apps/web/src/styles.css` e da folha da medição. NENHUMA cor nova (proveniência
  do pacote aprovado). Cor nunca é o único indicador; warnings críticos não são
  escondidos. Piso desktop de 1180px igual à casca das jornadas.
- Acessibilidade que o mock não sustenta e é requisito de implementação
  declarado: ordem de foco, navegação por teclado, rótulos de leitor de tela.

Testes (vitest, padrão dos vizinhos):

- `route.test.ts` (ou equivalente existente): precedência com o parâmetro novo.
- tradução de erros dos códigos novos.
- componente(s) chave da jornada: cascata recusando origem repetida (banner
  traduzido), tela de auditoria reprovada, BDI aceito só como string decimal.

## Out of scope

- `src/medicao/`, `CroquiApp.tsx`, `capture.ts`, `trace.ts`, `chat.ts`,
  `journey.ts` (máquina do croqui) — intocados.
- Backend, contratos, CLI.
- Escala tipográfica/espaçamento/raio nova (decisão com artefato próprio — não
  entra de carona; use os valores que a folha da medição já usa).
- BDI por grupo e ponte croqui→orçamento.

## Acceptance criteria

1. `make check` (inclui build web) e `npm --workspace @croquito/web run test`
   verdes.
2. As três jornadas alternam pelo seletor sem recarregar estado uma da outra;
   deep-link `?orcamento=<id>` abre a jornada certa.
3. Nenhuma cor nova no CSS (diff prova); nenhum tipo de domínio redigitado à mão.
4. Estados de erro do pacote aprovado presentes: 403 sem nome de papel, 409 com
   banner próprio, recusa de domínio traduzida, auditoria reprovada como tela.

## Validation

```bash
make check
npm --workspace @croquito/web run test
```

## Required capabilities

READ, WRITE, VALIDATE. Sem COMMIT: deixe o diff na árvore.

## Report

`BUILD REPORT` completo, gravado em
docs/features/F-020-orcamento-base-web/tasks/T4-build-report.md.
