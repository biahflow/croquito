# Piloto de paridade de harness

Status: Active
Responsável: Engineering
Última revisão: 2026-08-18

A Engineering OS sustenta que um Task Contract portável, executado por qualquer harness,
produz a mesma evidência e para nos mesmos gates
([`execution.md`](../../engineering-os/workflows/execution.md)). Neste repositório essa
máquina nunca tinha sido ligada: todo o trabalho de F-001 a F-008 rodou num único harness.
Este diretório é o exercício deliberado dessa superfície, por decisão humana de 2026-08-18.

| Artefato | Papel |
|---|---|
| [task.md](task.md) | O Task Contract portável (PARITY-001), no formato do [template global](../../engineering-os/templates/task.md) |
| [assignment.md](assignment.md) | O `HARNESS ASSIGNMENT` — ato humano designando o Codex — e o roteiro do operador |
| [build-report-codex.md](build-report-codex.md) | O `BUILD REPORT` do executor, gravado por ele ao final da execução (r2, 2026-08-18) |
| [review.md](review.md) | A revisão somente leitura com a comparação de evidência — `REVIEW_PASS` (2026-08-18) |

O resultado que interessa não é a mudança em si (um bullet de documentação) — é a resposta a
três perguntas: o contrato bastou sem conversa? A evidência saiu no mesmo formato comparável?
Os gates seguraram o executor nos mesmos lugares? Falha em qualquer uma é achado sobre o
contrato ou os adapters, e é registrada em vez de contornada.

## Achados

**A-1 (2026-08-18, primeira tentativa — contrato r1): critério insatisfazível, devolvido.**
O executor designado leu o contrato, montou o baseline e **parou antes de editar**: o critério
de aceite 4 exigia que `git diff --stat` mostrasse o arquivo novo do relatório, mas arquivo
não rastreado não aparece em `git diff`, e o contrato ao mesmo tempo proibia mexer no índice.
`TASK_CONTRACT_NOT_PORTABLE` — defeito do contrato, não do executor. O comportamento foi o
prescrito: devolver em vez de resolver por conversa ou de encenar o critério com `git add -N`.
A devolução formal do executor está preservada verbatim em
[return-r1-codex.md](return-r1-codex.md); a primeira alternativa que ele propôs é a adotada.
Conserto na revisão r2 do [contrato](task.md), feito no repositório, visível. É o primeiro
resultado material do piloto: o gate de portabilidade morde.

**A-2 (2026-08-18, observação de adapter): o executor leu a camada global pelo bootstrap
pessoal, não pelo espelho pinado.** Os caminhos acessados foram os absolutos do checkout vivo
do operador (`~/workspace/engineeringOS/...`), como o adapter instala — e não
`docs/engineering-os/`. Hoje os dois estão no mesmo commit (`2d0d09d`), então nenhuma regra
divergiu; mas se a origem andar sem ressincronização, um executor com bootstrap e um sem
bootstrap leriam regras diferentes. Registrado como risco de adapter a observar; a mitigação
já existe (o espelho pinado é a referência normativa do repo, ADR-0034).

**Nota de ambiente (não é achado de contrato):** o sandbox do executor não tinha permissão em
`~/.cache/uv`; a saída foi `UV_CACHE_DIR` temporário, com os mesmos comandos do contrato. Os
portões (`check_docs`, `make check`) rodaram e passaram no baseline.
