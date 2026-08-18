# PARITY-001 — Governança do INDEX aponta o processo de ADR, sem reformulá-lo

Este é um Task Contract no formato do
[template da camada global pinada](../../engineering-os/templates/task.md). Ele é
autossuficiente: assuma que o executor tem o Core (vendorizado em
[`docs/engineering-os/`](../../engineering-os/PROVENANCE.md)), este contrato e o repositório —
e nada mais. Nenhuma memória de sessão anterior, nenhum acesso a quem o escreveu.

## Identity

```text
feature_id: none (tarefa de governança, fora de feature)
task_id: PARITY-001
parent_plan: none — autorizada por decisão humana de 2026-08-18, registrada em
             docs/engineering/parity-pilot/assignment.md
depends_on: none
```

## Goal

A seção `## Governança` de `docs/INDEX.md` deixa de reformular a regra de imutabilidade de
ADR — que tem fonte única em `docs/adr/README.md` — e passa a apontar para o processo. Após a
mudança, nenhuma formulação da regra de imutabilidade existe em `docs/INDEX.md`, e a seção
continua cobrindo o mesmo assunto por link.

## Scope

Pode alterar:

- `docs/INDEX.md` — somente a seção `## Governança` (o primeiro bullet, "ADR aceito é
  imutável; substitua por novo ADR.", vira uma remissão ao
  [processo de ADR](../../adr/README.md); os demais bullets permanecem) e a linha
  `Última revisão:` do cabeçalho.
- `docs/engineering/parity-pilot/build-report-codex.md` — arquivo novo onde você grava o seu
  `BUILD REPORT` final (conteúdo idêntico ao do relatório com que encerra a resposta).

## Out of Scope

- Qualquer outra seção de `docs/INDEX.md` (rotas de leitura, fontes canônicas, catálogo).
- `docs/adr/README.md`, `AGENTS.md`, `CONTRIBUTING.md`, `CLAUDE.md` — a fonte única do
  processo de ADR não é tocada.
- `docs/engineering-os/` — espelho pinado; nunca editado à mão.
- `docs/engineering/TRACEABILITY.md` — há lacunas conhecidas (ADRs 0031–0034 ausentes);
  é adiamento declarado, deixe como está.
- Qualquer melhoria adjacente que você notar em outros documentos: anote no relatório em
  "Remaining risks" ou "Assumptions", não execute.

## Acceptance Criteria

1. `grep -n "imutável" docs/INDEX.md` não retorna nenhuma linha (checado por grep).
2. A seção `## Governança` contém um bullet remetendo ao processo de ADR com link relativo
   válido para `adr/README.md` (checado por leitura e pelo validador de links do item 3).
3. `uv run python scripts/check_docs.py` termina com exit 0 (checado pela execução).
4. `git diff --stat` mostra exatamente um arquivo modificado (`docs/INDEX.md`) e um arquivo
   novo (`docs/engineering/parity-pilot/build-report-codex.md`) (checado pela execução).

## Validation

```text
baseline: uv run python scripts/check_docs.py  → exit 0 no commit base deste contrato
          make check                            → exit 0 no commit base deste contrato
required: docs:  uv run python scripts/check_docs.py
          full:  make check
```

Não invente comando. Se um comando exigido não puder rodar, não o trate como opcional:
encerre como `BUILDER_VALIDATION_BLOCKED`, liste o check em `Validation skipped` com o motivo
e nomeie `VALIDATE` em `Unavailable capabilities`, como exige o
[contrato do Builder](../../engineering-os/agents/builder.md).

## Required Capabilities

```text
READ:     o repositório inteiro (docs/ em particular)
WRITE:    docs/INDEX.md e docs/engineering/parity-pilot/build-report-codex.md, somente
VALIDATE: uv run python scripts/check_docs.py; make check
COMMIT:   forbidden — a entrega é o diff na árvore de trabalho mais o BUILD REPORT
```

## Context to Read First

1. `AGENTS.md` (raiz) — regras do repositório.
2. `docs/adr/README.md` — o processo de ADR que a seção passa a referenciar.
3. `docs/INDEX.md` — o alvo, por inteiro, antes de editar.
4. [`docs/engineering-os/agents/builder.md`](../../engineering-os/agents/builder.md) — o
   formato exigido do `BUILD REPORT`.

## Known Risks

- Editar além do bullet: a seção Governança tem outros bullets corretos; o escopo é um bullet
  e a data de revisão. Um diff maior que isso é sinal de desvio.
- Quebrar o link relativo: `docs/INDEX.md` referencia `adr/README.md` relativo a `docs/`;
  o validador de links pega, rode-o antes de encerrar.
- `make check` é o portão completo do projeto (lint, tipos, contratos, build web, terraform
  fmt); ele deve passar já no baseline — se falhar em área não tocada por esta tarefa, pare e
  reporte em vez de consertar área alheia.

## Human Gates

- Nenhuma decisão humana dentro do escopo.
- Commit, push e merge são atos humanos fora deste contrato (COMMIT: forbidden).

## Reporting

Encerre com o `BUILD REPORT` completo exigido pelo
[contrato do Builder](../../engineering-os/agents/builder.md) — todos os campos presentes,
`none` onde vazio — e grave o mesmo conteúdo em
`docs/engineering/parity-pilot/build-report-codex.md`.
