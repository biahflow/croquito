# Project Context

Status: Accepted
Responsável: Engineering / Product
Última revisão: 2026-08-17

## Objetivo e precedência

Este documento é o ponto de entrada operacional do Croquito na Engineering OS. As regras
globais são carregadas pelo `AGENTS.md` da raiz e têm precedência junto com os guardrails
do projeto. Este contexto referencia as fontes existentes; não as duplica nem enfraquece.

## Fontes canônicas do projeto

| Assunto | Fonte |
| --- | --- |
| Trabalho planejado | [Roadmap](../product/ROADMAP.md) |
| Estado, riscos e evidências resumidas | [Status](../STATUS.md), vista derivada |
| Especificação de produto | [PRD](../product/PRD.md), [FDD](../product/FDD.md), [Acceptance Criteria](../product/ACCEPTANCE_CRITERIA.md) e [NFR](../product/NFR.md) |
| Arquitetura e interfaces | [Architecture](../architecture/SYSTEM_ARCHITECTURE.md), contratos e [ADR index](../adr/README.md) |
| Roteiro de contexto | [Documentation Index](../INDEX.md) |
| Instruções locais | [Root AGENTS](../../AGENTS.md) e o `AGENTS.md` mais próximo do escopo |

O documento detalhado de cada ADR é a fonte de decisão; o índice é a visão de navegação
e deve permanecer sincronizado. Conflito entre os dois é `SOURCE_OF_TRUTH_CONFLICT` e
exige decisão humana antes de ser resolvido.

## Intake, lifecycle e artefatos

`docs/product/ROADMAP.md` é o equivalente aprovado de `ROADMAP.md`. Ele é a única fonte
canônica de trabalho ainda não especificado. `docs/STATUS.md` não seleciona trabalho nem
define a conclusão de uma feature.

Para trabalho novo selecionado por humano, use a convenção abaixo:

```text
docs/features/<feature-id>/
├── feature.md
├── plan.md
├── evidence.md
└── tasks/                 # quando os contratos por tarefa melhorarem a clareza
```

O item do roadmap registra ID estável, prioridade, estado e o link para `feature.md`
quando ele existir. Os estados são os da Engineering OS: `BACKLOG`, `READY_FOR_SPEC`,
`SPEC_IN_PROGRESS`, `READY_FOR_PLANNING`, `PLANNING`, `READY_FOR_BUILD`,
`IN_PROGRESS`, `READY_FOR_REVIEW`, `READY_FOR_HUMAN_REVIEW`, `DONE`, `BLOCKED` e
`CANCELLED`.

Marcos anteriores não precisam ser retroativamente reescritos como features. Um agente
pode identificar itens elegíveis, mas não escolher prioridade, iniciar implementação ou
mudar estado sem autorização humana.

## Papéis e evidências

Aplicam-se integralmente os contratos globais da Engineering OS para Planner, Builder e
Reviewer. O Planner produz `FEATURE EXECUTION PLAN`; cada Builder preserva seu próprio
`BUILD REPORT`; e o Reviewer avalia o pacote de evidências
`BASELINE → CHANGE → FINAL` e termina em um dos estados previstos no contrato global.

`evidence.md` consolida referências estáveis ao contrato, plano, Task Contracts,
baseline, relatórios de build, validação, diff/commits, desvios do plano, riscos e
decisões humanas. Ele não substitui as fontes de evidência atribuídas a cada Builder.

## Perfis de validação conhecidos

| Perfil | Comando/fonte | Uso |
| --- | --- | --- |
| Setup | `make setup` | bootstrap local documentado |
| Qualidade | `make check` | lint, format, tipos, contratos, docs, build e Terraform fmt |
| Testes | `make test` | pytest e testes TypeScript |
| Evals sintéticas | `make vision-eval`, `make solver-eval` e evals de valuation | mudanças de IA/CV/solver/medição conforme escopo |
| Demo | `make demo` | vertical slice sintético |
| Infraestrutura | `terraform -chdir=infra init -backend=false` e `terraform -chdir=infra validate` | validação sem apply |
| CI | [`.github/workflows/quality.yml`](../../.github/workflows/quality.yml) | os profiles acima, num portão só; chamado por `ci.yml` no PR e por `deploy-hml.yml` antes de publicar |

Os detalhes, pré-requisitos e limites de cada comando permanecem em
[Local Development](LOCAL_DEVELOPMENT.md), no [Makefile](../../Makefile) e nos runbooks.
Nenhum perfil autoriza deploy, mutação de infraestrutura, envio externo de dados ou
chamadas pagas sem os gates definidos no `AGENTS.md`.

## Estado e escopo da adoção

A adoção da Engineering OS está em `ADOPTION_IN_PROGRESS`. A decisão humana de
2026-08-17 aprova somente os seis artefatos de contexto e workflow desta migração:
`AGENTS.md`, `docs/INDEX.md`, `docs/STATUS.md`, `docs/product/ROADMAP.md`, este
Project Context e `docs/features/README.md`.

Esta decisão não aprova, altera ou ratifica o status de ADRs; não seleciona feature;
não autoriza planejamento, implementação, deploy ou mudança de produção; e não
substitui nenhum gate futuro da Engineering OS ou do projeto.
