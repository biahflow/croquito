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
| `build-report-codex.md` | O `BUILD REPORT` do executor, gravado por ele ao final (não existe até a execução) |
| `review.md` | A comparação de evidência, escrita na revisão somente leitura (não existe até a revisão) |

O resultado que interessa não é a mudança em si (um bullet de documentação) — é a resposta a
três perguntas: o contrato bastou sem conversa? A evidência saiu no mesmo formato comparável?
Os gates seguraram o executor nos mesmos lugares? Falha em qualquer uma é achado sobre o
contrato ou os adapters, e é registrada em vez de contornada.
