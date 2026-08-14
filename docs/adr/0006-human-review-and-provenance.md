# ADR-0006: Revisão humana e provenance obrigatórias

Status: Accepted  
Data: 2026-08-10  
Responsável: Product / Domain / AI

## Contexto

Alguns croquis não possuem dados suficientes para geometria única. O sistema não
pode transformar ambiguidade em falsa precisão.

## Decisão

Exportação exige revisão aprovada. Cada medida, constraint e entidade registra
origem. `unresolved` relevante bloqueia; `approximate` exige aceitação explícita.

## Alternativas

- Export automático com score: rejeitado por confiança não calibrada.
- Redesenho completo na UI: rejeitado por destruir a proposta de valor.

## Consequências

- Usuário assume somente decisões materiais.
- Revisões são imutáveis e auditáveis.
- Métrica principal inclui tempo até aprovação.

## Riscos e mitigação

Fadiga de revisão: ordenar issues por impacto, reanalisar recortes e medir ações.

