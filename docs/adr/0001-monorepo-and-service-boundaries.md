# ADR-0001: Monorepo e boundaries de serviços

Status: Accepted  
Data: 2026-08-10  
Responsável: Architecture

## Contexto

Front-end, API, worker e infraestrutura compartilham contratos, mas possuem
runtimes e ciclos de teste diferentes. Um repositório vazio permite definir a
separação antes do código.

## Decisão

Usar monorepo com `apps/web`, `services/api`, `services/worker`, `packages` para
contratos gerados/compartilhados e `infra` para Terraform. Cada boundary tem
`AGENTS.md`, testes próprios e não importa internals de outro runtime.

## Alternativas

- Repositórios separados: rejeitado no MVP pelo custo de coordenar schemas.
- Monólito único Python: rejeitado por acoplar UI, HTTP e processamento pesado.

## Consequências

- Mudança de contrato pode ser validada de ponta a ponta em uma revisão.
- Build e deploy continuam separados.
- CI precisa detectar dependências indevidas entre boundaries.

## Riscos e mitigação

Monorepo virar monólito: impor interfaces, ownership e testes de contrato.

