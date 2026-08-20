# F-027 — Evidência de execução

Consolidação no formato do template global. Cada `tasks/T*-build-report.md` é
`PRIMARY_EXECUTION_EVIDENCE` da sua task.

## Contexto

- Feature Contract: [feature.md](feature.md) (`INTERFACE_CHANGE`).
- ADR: [ADR-0040](../../adr/0040-teto-de-verba-do-orcamento-base.md), **Accepted por
  ato humano em 2026-08-20** — na mesma decisão que aprovou a revisão 1 do
  [Design Approval Package](mock/README.md) (estouro em âmbar sem botão, mantido).
- Plano: [plan.md](plan.md) — T1 → (T2 ∥ T3).
- Execução: 2026-08-20, branch `f-027-especificacao`, worktree `croquito-specs`.
  Merge REPRESADO por decisão humana da mesma data.

## Baseline

`make check` e `make test` verdes na árvore commitada da branch antes de T1.

## Tasks e Build Reports

| Task | Contrato | Build Report | Status | Executor |
|---|---|---|---|---|
| T1 — teto na rodada: colunas, migração 0004, rotas, payload derivado | [T1](tasks/T1-teto-api.md) | [report](tasks/T1-build-report.md) | BUILD_COMPLETE | implementador-sonnet |
| T2 — telas do mock + conserto declarado de legibilidade | [T2](tasks/T2-teto-web.md) | [report](tasks/T2-build-report.md) | BUILD_COMPLETE | implementador-opus |
| T3 — e2e do teto pela cadeia `/v1` | [T3](tasks/T3-teto-e2e.md) | [report](tasks/T3-build-report.md) | BUILD_COMPLETE | implementador-sonnet |

Estado final integrado na branch (portões de T2 sobre a árvore com os três diffs):
`make check` exit 0; pytest **1705 passed / 13 skipped**; vitest **737 passed**
(baseline 693). e2e: 17 passed. **Suíte de migrações 12/12 em Postgres real**
(container descartável), incluindo a primeira migração incremental (`0004`,
`ALTER TABLE`) — primeira execução integral verde dessa suíte desde a 0003.

## Achados da execução (além do escopo pedido, ambos com evidência)

1. **Falha pré-existente na main** (desde a migração 0003/F-020, invisível com o
   quality gate desligado): `test_medicao_nasce_depois_da_baseline_com_o_indice_da_listagem`
   não contemplava as tabelas do orçamento. **Corrigida nesta branch** com prova em
   Postgres real (1 failed → 12 passed).
2. **Asserção ampla demais** em `test_banco_anterior_ao_runner_e_carimbado` (proibia
   qualquer `ALTER` quando a invariante real é "baseline intocada") — estreitada para
   verificar o ALVO do `ALTER`/`DROP` contra `BASELINE_TABLES`, com comentário.
3. **Defeito de legibilidade pré-existente da F-020** (metadados da lista com tinta do
   topbar escuro sobre painel claro), exposto pelo mock — **consertado em T2** como
   troca declarada `.topbar-meta` → `.dica` (3 linhas).

## Revisão (modelo principal da sessão)

- T1: linha a linha no caminho do dinheiro derivado — `parse_target_amount`
  fail-closed (zero não é "sem teto"), `target_state` lê `total_amount` como está e
  compara estrito (limite exato `over: false`), migração 0004 no padrão, estreitamento
  do teste de migração com invariante preservada. Complementos pedidos na revisão e
  entregues: teto na listagem (Tela 1 do mock) e o fix da falha pré-existente.
- T2: spot-check — `teto.ts` deriva sem recomputar dinheiro (única conta é a RAZÃO
  percentual, em BigInt truncado; a palavra do estado vem sempre de `over`), faixa de
  estouro sem botão renderizada fora do switch de etapa, nenhuma cor nova (verificado
  contra HEAD). Riscos declarados aceitos (cobertura estrutural da faixa; percentual
  truncado "96,83%" onde o mock ilustrava arredondado).
- T3: cenário aditivo com valores exatos; limite exato exercido editando o teto para o
  total real; cadeia sem teto intacta com asserção de ausência.

## Plan deviations

Nenhum no nível do plano. Desvios conscientes por task nos Build Reports (edição
justificada de `test_migrations.py` por consequência direta do contrato;
`String(32)` no valor; módulo `teto.ts` próprio; percentual na tela — caminho previsto
pelo pacote aprovado).

## Gates humanos

1. Seleção (2026-08-20) — exercida. 2. ADR-0040 — **aceito em 2026-08-20**.
3. Design rev. 1 — **aprovado em 2026-08-20**. 4. **Merge — represado; pendente.**
5. Copy final — pendente (declarado no pacote).
