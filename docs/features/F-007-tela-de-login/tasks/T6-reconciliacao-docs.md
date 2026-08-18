# T6 — A documentação operacional descreve o mapa novo

Task Contract no formato do [template global](../../../engineering-os/templates/task.md),
derivado do [plano válido](../plan.md). Autossuficiente.

## Identity

```text
feature_id: F-007
task_id: T6
parent_plan: docs/features/F-007-tela-de-login/plan.md
depends_on: [T1]
```

## Goal

`docs/operations/HML.md` descreve o mapa de rotas novo (raiz → `/login`) e a fumaça manual
inclui a raiz; nenhuma outra página de `docs/` segue afirmando o mapa antigo. É a
"reconciliação documental" do [Feature Contract](../feature.md) — a lição da F-006 (HML.md
afirmando um ambiente que não respondia) vale para rotas também.

## Scope

- `docs/operations/HML.md`: seção do mapa de rotas atualizada (`/` → 302 `/login`;
  `/login` → SPA; demais rotas inalteradas); a seção de fumaça manual ganha o `curl` da
  raiz e de `/login`, no padrão dos curls existentes.
- Varredura: `grep -rn "revisao" docs/ --include='*.md'` procurando afirmações do mapa
  antigo ("a raiz redireciona para /revisao/") fora de registros históricos; corrigir só
  descrições **vigentes** — evidências datadas (evidence.md, STATUS histórico, ADRs) não se
  reescrevem.

## Out of Scope

- `docs/STATUS.md` e `docs/product/ROADMAP.md` — transições de estado são do workflow.
- ADRs e `evidence.md` de qualquer feature — registros datados são imutáveis.
- `deploy/nginx.conf` (T1), código, testes.
- `docs/engineering-os/` — espelho pinado, nunca editado à mão.

## Acceptance Criteria

1. HML.md descreve o mapa novo e a fumaça manual cobre `/` e `/login` (checado por
   leitura).
2. A varredura do Scope está no relatório: cada ocorrência encontrada, com a decisão
   (corrigida por ser descrição vigente / preservada por ser registro histórico) (checado
   por leitura do relatório).
3. `make check` verde — o `check_docs.py` valida links e paridade (checado pela execução).

## Validation

```text
baseline: make check → verde com T1 integrada
required: docs: uv run python scripts/check_docs.py
          full: make check
```

## Required Capabilities

```text
READ:     docs/ e deploy/nginx.conf (para transcrever o mapa real)
WRITE:    docs/operations/HML.md e, se a varredura apontar, outras páginas de docs com
          descrição vigente do mapa antigo — nunca registros históricos
VALIDATE: make check
COMMIT:   forbidden
```

## Context to Read First

1. `AGENTS.md` (raiz) e `CLAUDE.md`.
2. `deploy/nginx.conf` pós-T1 — o cabeçalho é a fonte do mapa a transcrever.
3. `docs/operations/HML.md` por inteiro.

## Known Risks

- Reescrever registro histórico achando que é descrição vigente — na dúvida, preserve e
  reporte.

## Human Gates

- Nenhum dentro do escopo.

## Reporting

Encerre com o `BUILD REPORT` completo do
[contrato do Builder](../../../engineering-os/agents/builder.md) e grave o mesmo conteúdo em
`docs/features/F-007-tela-de-login/tasks/T6-build-report.md`.
