# ADR-0005: Canonical Scene Graph

Status: Accepted  
Data: 2026-08-10  
Responsável: Architecture / Geometry

## Contexto

Respostas de modelos, pixels e DXF têm representações incompatíveis. Gerar CAD
diretamente de um JSON de LLM perderia provenance e tornaria revisão frágil.

## Decisão

Criar scene graph versionado com regions, readings, measurements, entities,
constraints, issues e precision. O scene graph aprovado é a única entrada do
exportador DXF.

## Alternativas

- JSON específico de provider: rejeitado por lock-in e semântica instável.
- DXF como banco intermediário: rejeitado por revisão e diff difíceis.

## Consequências

- Solver e export são determinísticos e testáveis.
- UI edita operações de domínio, não entidades DXF diretamente.
- Exige schema, migração e validação de invariantes.

## Riscos e mitigação

Modelo excessivamente genérico: limitar tipos ao MVP e evoluir por versões.

