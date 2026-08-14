# ADR-0007: DXF como saída primária do MVP

Status: Accepted  
Data: 2026-08-10  
Responsável: Product / CAD Engineering

## Contexto

DXF pode ser criado e auditado com `ezdxf`. DWG adiciona dependência proprietária,
licenciamento e conversão sem melhorar a prova central de geometria.

## Decisão

Entregar DXF R2018 em metros, com layers, entidades nativas, XDATA mínima,
auditoria e preview. Adiar DWG até decisão comercial/licenciamento.

## Alternativas

- DXF + DWG no MVP: rejeitado pelo desvio de escopo.
- SVG: útil como preview, insuficiente como entrega CAD.

## Consequências

- Resultado técnico verificável e portátil.
- Demonstração deve explicar que AutoCAD abre DXF diretamente.
- DWG permanece no roadmap e exige novo ADR.

## Riscos e mitigação

Cliente exigir DWG: converter de forma controlada fora do produto apenas como
demonstração, sem prometer feature.

