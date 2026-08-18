# Atribuição de harness — PARITY-001

Registro no formato de `HARNESS ASSIGNMENT` de
[`execution.md`](../../engineering-os/workflows/execution.md). A atribuição é ato humano,
registrada fora do plano; um agente não seleciona o próprio harness.

```text
HARNESS ASSIGNMENT

task_id: PARITY-001
harness: Codex
assigned_by: Daniel Campos (decisão humana de 2026-08-18)
rationale: exercitar, pela primeira vez, a paridade de harness da Engineering OS neste
           repositório — o mesmo Task Contract, executado por um segundo harness, deve
           produzir a mesma evidência (BUILD REPORT) e parar nos mesmos gates. Todo o
           trabalho de F-001 a F-008 rodou em Claude Code; esta tarefa pequena, com oráculo
           determinístico (check_docs + make check), é o piloto de menor risco possível.
```

## Como executar (operador)

1. Garanta a branch/commit combinados (pós-merge do PR desta rodada) e árvore limpa.
2. Abra o Codex na raiz do repositório e peça:
   *"Execute o Task Contract em `docs/engineering/parity-pilot/task.md`. Leia o contrato por
   inteiro antes de editar e encerre com o BUILD REPORT completo."*
3. Não complemente o contrato por conversa: se o Codex precisar de algo que não está escrito
   nele, isso é um achado de portabilidade (`TASK_CONTRACT_NOT_PORTABLE`) — anote e pare.
4. Ao final, confira que `docs/engineering/parity-pilot/build-report-codex.md` existe e que o
   diff está dentro do escopo do contrato. Commit é seu.

## Depois da execução

A revisão (somente leitura) compara o `BUILD REPORT` com o diff e registra a comparação de
evidência em `review.md` — criado na revisão, não antes. Divergência material
entre o que este harness produziu e o que o harness habitual produziria para o mesmo
requisito é achado sobre o contrato ou os adapters, registrado como manda
[`execution.md`](../../engineering-os/workflows/execution.md); não se resolve preferindo o
harness de saída mais bonita.
