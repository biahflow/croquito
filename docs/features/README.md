# Artefatos de feature

Status: Accepted
Responsável: Engineering / Product
Última revisão: 2026-08-18

Este diretório recebe somente artefatos de trabalho futuro selecionado por humano. A
convenção, lifecycle, responsabilidades e perfis de validação estão no
[Project Context](../engineering/PROJECT_CONTEXT.md).

Para cada feature, crie `docs/features/<feature-id>/feature.md` a partir do
[template de feature](../engineering-os/templates/feature.md) da camada global pinada. Não
converta retrospectivamente marcos já concluídos, nem crie uma feature sem seleção humana no
roadmap canônico.

A cadeia completa da convenção, por decisão humana de 2026-08-18, é:

1. `feature.md` — o que a feature precisa entregar
   ([template](../engineering-os/templates/feature.md)).
2. `plan.md` — como o Planner decompõe a feature aceita
   ([template](../engineering-os/templates/plan.md)).
3. `tasks/<task-id>.md` — **um Task Contract por task do plano**
   ([template](../engineering-os/templates/task.md)), obrigatório da F-007 em diante.
4. Um Builder por contrato, sem dois executores sobre o mesmo escopo.
5. `evidence.md` — o pacote de revisão, referenciando um `BUILD REPORT` por task
   ([template](../engineering-os/templates/evidence.md)).
