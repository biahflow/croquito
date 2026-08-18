# Devolução da r1 — executor Codex (evidência-fonte)

Status: Evidence
Responsável: Engineering
Última revisão: 2026-08-18

Transcrição literal do documento com que o executor designado (Codex) devolveu o contrato
**r1** sem executá-lo, em 2026-08-18 — a evidência-fonte do achado A-1 do
[README](README.md). Transcrita pelo operador a partir da sessão do executor; os links do
original foram desativados (crases) para o validador de links não os resolver fora de
contexto. A alternativa que o executor lista primeiro é a adotada na revisão r2 do
[contrato](task.md).

```text
# PARITY-001 — Execução bloqueada por contrato não portátil

## Resumo

A execução não deve iniciar. O critério 4 exige que git diff --stat liste um arquivo novo,
mas o Git não inclui arquivos não rastreados nesse comando. O contrato também limita a
escrita aos dois arquivos e proíbe commit; portanto, o critério é inexequível sem alterar o
índice.

## Evidência

- Árvore inicial limpa.
- uv run python scripts/check_docs.py: passou.
- make check: passou.
- git diff --stat: vazio.
- docs/engineering/parity-pilot/build-report-codex.md: ainda não existe.

## Correção necessária no contrato

Escolher uma alternativa antes da execução:

- substituir o critério por validação com git status --short, preservando o índice; ou
- autorizar explicitamente git add -N para o novo relatório; ou
- corrigir o contrato e reatribuir a tarefa.

Conforme escolhido, a tarefa deve ser registrada como TASK_CONTRACT_NOT_PORTABLE e não
reparada durante a execução.

## Execução futura após correção

1. Alterar somente o bullet de Governança para remeter a `docs/adr/README.md`.
2. Manter a data Última revisão: 2026-08-18.
3. Criar o BUILD REPORT completo no arquivo previsto.
4. Executar uv run python scripts/check_docs.py e make check.
5. Conferir o diff e o escopo autorizado.

Nenhum arquivo foi alterado nesta sessão; consequentemente, nenhum BUILD REPORT de execução
foi criado.
```
