# Checklist de revisão

Status: Accepted  
Responsável: Engineering  
Última revisão: 2026-08-10

## Intenção

- [ ] Mudança corresponde ao requisito/issue.
- [ ] Critério de aceite é testável.
- [ ] Escopo não cresceu silenciosamente.

## Produto e domínio

- [ ] Medidas e units preservam texto/evidência.
- [ ] Não há inferência geométrica não registrada.
- [ ] Estados `approximate/unresolved` são honestos.
- [ ] UX oferece recuperação e explica impacto.

## Arquitetura

- [ ] Boundaries e adapters foram respeitados.
- [ ] Operações assíncronas são idempotentes.
- [ ] Schema/API mantém compatibilidade ou migração.
- [ ] ADR/RFC existe quando necessário.

## IA

- [ ] Prompt/model/schema estão versionados.
- [ ] Fallback não é silencioso.
- [ ] Evals e false-confident errors foram revisados.
- [ ] Custos e payload mínimo foram considerados.

## Segurança

- [ ] Tenant e autorização têm testes negativos.
- [ ] Logs não contêm dados sensíveis.
- [ ] Upload/input é tratado como não confiável.
- [ ] Retenção/exclusão permanecem corretas.

## Qualidade

- [ ] Tipagem, lint, testes e builds passam.
- [ ] Falhas e retries possuem casos negativos.
- [ ] Métricas e runbook cobrem comportamento novo.
- [ ] Documentação e traceability estão atualizadas.

