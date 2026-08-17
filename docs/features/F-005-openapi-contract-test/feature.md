# F-005 — Gate de contrato da API: snapshot de OpenAPI e paridade com o API Contract

## Status

`READY_FOR_SPEC`

> Selecionada em 2026-08-17 como piloto do primeiro ciclo Planner → Builder → Reviewer com
> os dois harnesses. A entrada correspondente no [roadmap canônico](../../product/ROADMAP.md)
> ainda não existe; passa a `READY_FOR_PLANNING` quando ela for criada e este contrato for
> aprovado.

## Priority

`HIGH` — não por valor de produto, mas porque é um gate declarado obrigatório e ausente, e
[F-003](../F-003-medicao-v1-migration/feature.md) vai acrescentar rotas confiando nele.

## Problem

Duas fontes canônicas exigem um gate de contrato que não existe:

- A [Testing Strategy](../../engineering/TESTING_STRATEGY.md), na seção "Contrato", exige
  "OpenAPI snapshots/breaking changes".
- O [API Contract](../../architecture/API_CONTRACT.md), na seção "Compatibilidade", declara
  que "OpenAPI gerado deve ser comparado em CI para detectar breaking changes".

Não há teste algum: `tests/api/` contém `test_api.py`, `test_pubsub_queue.py` e
`test_storage_flavor.py`, e nenhum deles inspeciona o documento OpenAPI da aplicação.

O gate documental também não cobre a lacuna. `scripts/check_docs.py` valida apenas links
inexistentes e blocos de código não fechados; ele não verifica que uma rota exposta por
`services/api/src/croquito_api/main.py` apareça no API Contract.

A consequência é verificável: hoje uma rota nova, ou a remoção de um campo de resposta,
atravessa `make check` e `make test` sem que nada acuse a divergência entre a API real e o
contrato publicado. Isso vale igualmente para agente e para humano.

## Desired Outcome

Uma mudança incompatível na superfície `/v1`, ou uma rota que não esteja no API Contract,
falha em `make test` com uma mensagem que diz o que divergiu e como proceder.

## Scope

- Um snapshot versionado do documento OpenAPI da aplicação, gerado a partir da própria
  aplicação FastAPI, e um teste que compara o documento gerado com o snapshot.
- Um caminho explícito e documentado para atualizar o snapshot quando a mudança for
  intencional. A atualização deve ser um ato deliberado e visível no diff, nunca automática.
- Um teste que verifica que cada rota `/v1` exposta pela aplicação aparece no
  [API Contract](../../architecture/API_CONTRACT.md), e que o contrato não descreve rota `/v1`
  inexistente na aplicação.
- Mensagens de falha que nomeiem o caminho e o método divergentes, para que a falha seja
  acionável sem leitura do teste.
- Registro do gate na [Testing Strategy](../../engineering/TESTING_STRATEGY.md), tornando a
  exigência existente rastreável ao teste que a cumpre.

## Out of Scope

- Alterar qualquer rota, modelo, resposta ou comportamento da API. Esta feature observa a
  superfície; não a muda.
- Classificar automaticamente o que é *breaking* versus aditivo. O snapshot detecta
  divergência; a leitura da compatibilidade permanece humana, conforme a seção
  "Compatibilidade" do API Contract.
- Rotas de medição, que não existem em `/v1` e pertencem a
  [F-002](../F-002-medicao-v1-contract/feature.md) e
  [F-003](../F-003-medicao-v1-migration/feature.md).
- Estender `croquito_core.schema_export` ou o pipeline de contratos TypeScript.
- Corrigir divergências que o novo gate revelar. Se o primeiro snapshot expuser rota fora do
  contrato, isso é `BASELINE`: registre como achado e trate em trabalho próprio, com decisão
  humana. Corrigir aqui seria ampliar escopo em silêncio.
- Alterar `scripts/check_docs.py` além do necessário, se for necessário.

## Acceptance Criteria

- Existe teste que falha quando o documento OpenAPI gerado difere do snapshot versionado, e
  passa quando são iguais. Ambas as direções são demonstradas.
- Existe teste que falha quando uma rota `/v1` da aplicação não está no API Contract, e
  quando o API Contract descreve rota `/v1` que a aplicação não expõe. Ambas as direções são
  demonstradas.
- As mensagens de falha nomeiam caminho e método; uma mensagem que só diga "snapshot
  divergente" reprova o critério.
- O procedimento de atualização do snapshot está documentado onde quem o encontra ao ver a
  falha vai olhar, e a atualização produz diff revisável.
- O baseline é registrado antes da mudança: contagem de testes de `make test` e resultado de
  `make check`. Falha preexistente registrada não é atribuída a esta feature.
- `make check` e `make test` passam ao fim, com a nova contagem registrada.
- Se o gate revelar divergência preexistente entre aplicação e contrato, ela é registrada
  como achado de baseline com caminho e método, sem ser corrigida aqui.
- `git status --short` não mostra alteração em `services/api/src/croquito_api/main.py` a não
  ser que o plano aprovado a preveja e justifique.

## Constraints

- `testpaths = ["tests"]` e `addopts = "-q --strict-markers --disable-warnings"` em
  `pyproject.toml`: o teste roda sob a configuração existente, sem marcador novo não
  declarado.
- `mypy` roda em modo estrito sobre `tests` em `make check`.
- Fixtures sintéticas; nenhum dado real, nenhum segredo, nenhuma chamada externa ou paga.
- O teste não pode depender de serviço de pé: `make test` roda sem `make dev-services`.
- Nenhuma dependência nova sem revisão de licença, manutenção e superfície de risco,
  conforme o [AGENTS.md](../../../AGENTS.md) da raiz e a
  [Dependency Policy](../../engineering/DEPENDENCY_POLICY.md).

## Dependencies

- Nenhuma bloqueante. Esta feature foi escolhida como piloto por isso.
- [F-001](../F-001-roadmap-clarification/feature.md) precisa estar versionada antes que a
  entrada de roadmap desta feature seja criada, para não misturar escopos no mesmo diff de
  `docs/product/ROADMAP.md`.

## Unknowns

- Onde o snapshot deve viver: `tests/api/`, um diretório de fixtures, ou `docs/`. Não há
  precedente de snapshot de OpenAPI no repositório; há o precedente de contrato gerado em
  `packages/contracts/scene.schema.json`, com `--check` em `make check`, que pode servir de
  modelo mas não é decisão tomada.
- Se a paridade com o API Contract se expressa melhor como teste em `tests/api/` ou como
  verificação em `scripts/check_docs.py`. Os dois lugares têm argumento; a escolha pertence
  ao plano.
- Quantas divergências preexistentes o gate vai revelar. Nenhuma fonte versionada permite
  prever, e o número não pode ser afirmado antes de o teste existir.

## Risks

- Snapshot instável por ordenação não determinística ou por versão de dependência, gerando
  falha que não corresponde a mudança de contrato. Um gate que falha sem motivo é desligado.
- Regenerar o snapshot para "fazer o teste passar", anulando o propósito do gate. É o modo
  de falha mais provável, e vale tanto para agente quanto para humano.
- Corrigir divergência preexistente dentro desta feature, misturando a criação do gate com a
  limpeza que ele revela.
- Acoplar o teste de paridade à formatação do Markdown do API Contract, tornando-o frágil a
  reescritas editoriais legítimas.

## Human Gates

- Aprovação deste contrato e criação de sua entrada no roadmap canônico.
- Decisão sobre qualquer divergência preexistente que o gate revelar: o que é bug de
  documentação e o que é rota que não deveria existir não é escolha de agente.
- Aprovação de dependência nova, se o plano propuser alguma.

## Nota de piloto

Esta feature foi selecionada para o primeiro ciclo com os dois harnesses porque tem duas
frentes plausivelmente independentes — o snapshot de OpenAPI e a paridade com o API Contract —
que tocam arquivos diferentes e podem ser executadas em paralelo. Se o Planner confirmar essa
independência, as duas tarefas resultantes permitem atribuir uma a cada harness e comparar os
dois `BUILD REPORT` lado a lado, conforme
`workflows/execution.md` da Engineering OS.

Essa nota é contexto de processo. Ela não autoriza paralelismo: a decisão é do plano, e
sobreposição incompatível deve ser registrada como `PARALLELISM_RISK`, não contornada porque o
piloto seria mais interessante em paralelo.

## References

- [Testing Strategy](../../engineering/TESTING_STRATEGY.md) — seção "Contrato"
- [API Contract](../../architecture/API_CONTRACT.md) — seção "Compatibilidade"
- [Definition of Done](../../engineering/DEFINITION_OF_DONE.md)
- [Project Context](../../engineering/PROJECT_CONTEXT.md) — perfis de validação
- `services/api/AGENTS.md` — regras de fronteira e testes mínimos exigidos
