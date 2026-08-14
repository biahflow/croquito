# ADR-0010: Versionamento de prompts, modelos e respostas

Status: Accepted  
Data: 2026-08-10  
Responsável: AI Engineering / Platform

## Contexto

Aliases e comportamento de modelos mudam. Sem versionamento não é possível
reproduzir uma leitura, comparar regressão ou explicar um DXF.

## Decisão

Registrar prompt semantic version/hash, model ID efetivo, provider, schema version,
pipeline version e input digest em cada reading. Respostas brutas permanecem
somente durante a retenção; dados normalizados preservam lineage necessário.

## Alternativas

- Guardar apenas alias atual: rejeitado por baixa reprodutibilidade.
- Guardar payload bruto indefinidamente: rejeitado por privacidade.

## Consequências

- Evals e incidentes conseguem reconstruir contexto.
- Mudança de prompt exige protocolo e rollback.
- Schema precisa suportar migração de metadata.

## Riscos e mitigação

Model ID não disponível no provider: registrar alias, response metadata e timestamp
sem alegar snapshot inexistente.

