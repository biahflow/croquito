# Revisão da execução — PARITY-001 (r2)

Status: REVIEW_PASS
Responsável: Engineering (Reviewer: Claude Code, somente leitura)
Última revisão: 2026-08-18

Revisão no formato do [contrato de Reviewer](../../engineering-os/agents/reviewer.md), sobre a
execução do [contrato r2](task.md) pelo harness designado no
[assignment](assignment.md) (Codex, atribuído por ato humano de 2026-08-18).

## Pacote de evidência

Completo. Contrato ([task.md](task.md), revisão r2), atribuição
([assignment.md](assignment.md)), devolução da r1 preservada
([return-r1-codex.md](return-r1-codex.md)), baseline declarado no contrato e confirmado pelo
executor (`check_docs` e `make check` verdes antes da mudança, árvore limpa), `BUILD REPORT`
completo do executor ([build-report-codex.md](build-report-codex.md), oito campos presentes) e
o diff na árvore de trabalho.

## Verificação independente do Reviewer

Reexecutada nesta revisão, sem editar nada:

| Critério do contrato | Resultado |
|---|---|
| 1. `grep -n "imutável" docs/INDEX.md` vazio | Confirmado (exit 1, nenhuma ocorrência) |
| 2. Bullet da Governança remete ao processo de ADR com link válido | Confirmado — texto `[ADR README]` apontando `adr/README.md`, relativo correto a `docs/` |
| 3. `uv run python scripts/check_docs.py` exit 0 | Confirmado (157 arquivos, paridade de lifecycle verificada) |
| 4. `git status --porcelain` com exatamente ` M docs/INDEX.md` e `?? .../build-report-codex.md` | Confirmado |
| (portão completo) `make check` | Confirmado verde ponta a ponta |

Diff inspecionado linha a linha: uma única linha alterada em `docs/INDEX.md` (o bullet), fora
de escopo intocado, índice do git não alterado, `COMMIT: forbidden` respeitado.

## Achados

- `CODE_FINDING`: **nenhum**.
- `EVIDENCE_FINDING`: **nenhum**.
- Observação (não bloqueante): o plano do executor continha o caminho `../../adr/README.md`
  (copiado do contexto do contrato); na edição, o executor resolveu sozinho para o relativo
  correto `adr/README.md` e registrou a resolução como assumption no relatório — o
  comportamento desejado, com o raciocínio declarado em vez de silencioso.

## As três perguntas do piloto

1. **O contrato bastou sem conversa?** Na r2, sim: nenhuma pergunta ao operador entre o
   início e o `BUILD_COMPLETE`. A r1 foi devolvida por defeito real do contrato (achado A-1) —
   e a devolução, não a execução, era o comportamento correto ali.
2. **A evidência saiu comparável?** Sim. O `BUILD REPORT` do Codex tem a mesma estrutura, os
   mesmos campos e o mesmo nível de precisão dos relatórios dos Builders do harness habitual
   (inclusive a distinção fina "no matches (expected exit 1)"). Única diferença material de
   execução: o contorno de ambiente `UV_CACHE_DIR` no sandbox, declarado, sem alterar a
   semântica de nenhum comando do contrato.
3. **Os gates seguraram nos mesmos lugares?** Sim. O executor parou no defeito de contrato
   (r1), respeitou `COMMIT: forbidden`, não tocou o índice, não corrigiu área alheia, e as
   validações que ele executou são as mesmas que esta revisão reexecutou com o mesmo
   resultado.

## Resultado

```text
REVIEW_PASS
```

`REVIEW_PASS` não é aprovação humana. Os atos seguintes são do operador: commit do diff do
executor junto com esta revisão, e o registro do desfecho do piloto. O risco A-2 do
[README](README.md) (bootstrap pessoal lê o checkout vivo, não o espelho pinado) permanece
aberto e independe desta execução.
