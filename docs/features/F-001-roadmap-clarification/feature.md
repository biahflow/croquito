# F-001 — Clarificação do roadmap canônico e ambientes

## Status

`DONE`

> Decisão humana de 2026-08-17 registrada na
> [seção 10 de evidence.md](evidence.md). Passava a `DONE` quando o resultado de `make check`
> fosse registrado; a decisão humana não substitui evidência determinística.
>
> **Fechada em 2026-08-17** ([seção 11](evidence.md)): `make check` exit 0 registrado, o que fecha
> o achado E3; as 34 chaves do inventário reconferidas por script contra o commit base e contra o
> roadmap do HEAD, sem divergência; a divergência de estado entre o roadmap e este contrato
> resolvida. A verificação de estado remoto do GCP autorizada pela decisão 5 foi executada e
> preencheu o terceiro eixo da reconciliação — com uma divergência entre a afirmação documental de
> [HML](../../operations/HML.md) e o estado observado, registrada como achado e deixada para
> trabalho próprio.

## Priority

`HIGH`

## Problem

O roadmap canônico contém bullets de naturezas distintas sem classificação uniforme. A
documentação descreve AWS como alvo de produção e GCP como homologação hospedada, o que
exige leitura baseada em evidências e sem inferência sobre estado remoto.

## Desired Outcome

Um roadmap canônico auditável, no qual cada bullet do inventário congelado esteja
classificado com sua evidência, e uma reconciliação factual entre AWS, GCP e
desenvolvimento local.

## Scope

- Tratar cada bullet Markdown do inventário congelado no `plan.md` como uma unidade
  independente de classificação.
- Produzir em `docs/product/ROADMAP.md` uma tabela com `item`, `classificação`,
  `evidência` e `observação`.
- Usar uma das classificações: `IMPLEMENTADO`, `EM OPERAÇÃO/HOMOLOGAÇÃO`,
  `PLANEJADO`, `HISTÓRICO`, `EXCLUÍDO` ou `UNKNOWN` quando a evidência for insuficiente.
- Reconciliar AWS, GCP e desenvolvimento local por meio de código, infraestrutura
  versionada, ADRs e documentação operacional.
- Manter `docs/product/ROADMAP.md` como única fonte canônica de roadmap/backlog e
  `docs/STATUS.md` como vista derivada.

### Rodada R1 (autorizada em 2026-08-17)

- Reproduzir cada bullet do inventário congelado com o texto integral e o título exato da
  seção de origem, preservando todos os qualificadores.
- Definir no roadmap o vocabulário de classificação, sem reclassificar item algum.
- Separar na reconciliação de ambientes três eixos: configuração versionada, afirmação
  documental e estado remoto verificado.
- Criar `evidence.md` preservando `BASELINE → CHANGE → FINAL`, a revisão da rodada R0 e
  esta autorização.

## Out of Scope

- Alterar código, infraestrutura, configuração, CI/CD, ADRs, Git state ou estado remoto.
- Inferir que um workflow ou configuração versionada comprova um deploy ativo.
- Selecionar ou implementar qualquer outra feature.
- Criar Task Contracts.
- Reclassificar qualquer item por preferência do agente; divergência entre evidência e
  classificação é registrada, não resolvida por conta própria.

`evidence.md` esteve fora de escopo na rodada R0 e entrou em escopo na rodada R1 por
autorização humana explícita de 2026-08-17 — a expansão de escopo exigida pela Definition
of Done está registrada em [evidence.md](evidence.md).

## Acceptance Criteria

- Cada item do inventário congelado aparece exatamente uma vez na tabela.
- Cada linha contém `item`, `classificação`, `evidência` e `observação`.
- `UNKNOWN` identifica a lacuna de evidência sem sugerir uma classificação provável.
- A reconciliação declara, com referências, AWS como desenho-alvo de produção, GCP/Cloud
  Run como caminho documentado de homologação hospedada e Docker, PostgreSQL, LocalStack
  e Keycloak como ambiente local documentado.
- A reconciliação distingue configuração no repositório, afirmação documental e estado
  remoto efetivamente verificado.
- Nenhuma alteração é proposta para status de ADR, código ou infraestrutura.

### Critérios adicionais da rodada R1

- Cada chave do inventário reproduz o bullet integral e o título exato da seção, conferível
  automaticamente contra `git show HEAD:docs/product/ROADMAP.md`.
- O vocabulário de classificação está definido no roadmap e foi conferido contra as 34
  linhas sem alterar nenhuma classificação; a distribuição permanece a de R0.
- Onde um mecanismo citado por um bullet foi parcialmente entregue, a observação declara o
  fato com a fonte, e a classificação permanece a que o bullet completo sustenta.
- A reconciliação declara os três eixos para AWS, GCP e ambiente local, e registra que
  nenhuma verificação remota foi executada.
- `evidence.md` preserva a revisão da rodada R0 com atribuição e o desfecho de cada
  achado.

## Constraints

- ADRs são somente fontes de evidência nesta feature; seus status não são alterados nem
  ratificados.
- Não inventar prioridade, lifecycle, estado operacional ou evidência humana ausente.
- Preservar marcos históricos e itens excluídos sem convertê-los automaticamente em
  Features.
- `STATUS.md` não pode se tornar fonte independente de prioridade ou lifecycle.

## Dependencies

- [Roadmap](../../product/ROADMAP.md)
- [Status](../../STATUS.md)
- [AWS Deployment](../../architecture/AWS_DEPLOYMENT.md)
- [HML](../../operations/HML.md)
- [ADR-0002](../../adr/0002-aws-managed-architecture.md)
- [ADR-0025](../../adr/0025-homologacao-em-gcp-cloud-run.md)
- [ADR-0026](../../adr/0026-medicao-hospedada-sessao-autenticada-minima.md)
- `infra/` e `.github/workflows/deploy-hml.yml`

## Unknowns

- Estado operacional remoto atual do ambiente GCP.
- Quais itens `PLANEJADO` serão selecionados futuramente por humano.

## Risks

- Confundir configuração de deploy com serviço ativo.
- Confundir entrega em código com homologação humana concluída.
- Reinterpretar ADRs ou marcos históricos sem evidência.

## Human Gates

- Aprovação posterior da tabela de classificação e da reconciliação AWS/GCP.
- Seleção humana de qualquer item `PLANEJADO` antes de novo Feature Contract ou execução.
- Aprovação da rodada R1 e das decisões pendentes registradas em [evidence.md](evidence.md),
  em especial se o M6 satisfaz o item 22 do inventário.
- Autorização própria, ainda inexistente, para qualquer verificação de estado remoto.

## References

- [Project Context](../../engineering/PROJECT_CONTEXT.md)
- [Roadmap](../../product/ROADMAP.md)
- [Status](../../STATUS.md)
- [AWS Deployment](../../architecture/AWS_DEPLOYMENT.md)
- [HML](../../operations/HML.md)
- [ADR-0002](../../adr/0002-aws-managed-architecture.md)
- [ADR-0025](../../adr/0025-homologacao-em-gcp-cloud-run.md)
- [ADR-0026](../../adr/0026-medicao-hospedada-sessao-autenticada-minima.md)
