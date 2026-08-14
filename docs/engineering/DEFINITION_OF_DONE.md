# Definition of Done

Status: Accepted  
Responsável: Engineering / Product  
Última revisão: 2026-08-10

Uma mudança está pronta quando todos os itens aplicáveis foram atendidos.

## Produto e contrato

- Critério de aceite está explícito e passou.
- Estados de sucesso, vazio, erro e retry foram tratados.
- Interface/API/domain schema estão consistentes.
- Não há suposição de geometria escondida.

## Código

- Tipagem, lint e format passam.
- Erros são estruturados e retryability é explícita.
- Operações são idempotentes quando assíncronas.
- Dados sensíveis não aparecem em log.
- Nova dependência passou pela policy.

## Testes

- Unitários e casos negativos cobrem comportamento novo.
- Integração cobre boundaries afetados.
- CAD audit cobre mudança geométrica.
- Evals cobrem mudança de IA.
- Regressão relevante passou.

## Operação

- Métrica/log/trace suficientes para diagnosticar falha.
- Alarmes e runbooks foram atualizados quando necessário.
- Migração, compatibilidade e rollback foram avaliados.
- Impacto de custo foi registrado.

## Documentação

- Fonte canônica e traceability foram atualizadas.
- ADR/RFC existe quando necessário.
- `AGENTS.md` não ficou desatualizado.
- `docs/STATUS.md` reflete mudança de marco.

## Segurança

- Auth/tenant boundaries foram testados.
- Dados e retenção permanecem conformes.
- Nenhum segredo ou documento real foi commitado.

