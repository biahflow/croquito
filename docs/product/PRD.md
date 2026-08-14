# Product Requirements Document

Status: Accepted for MVP  
Responsável: Product  
Última revisão: 2026-08-10

## Visão

CroquiToDXF reduz o tempo entre um levantamento manuscrito e um desenho CAD
utilizável. O sistema produz uma primeira versão técnica, evidencia incertezas e
permite que um profissional corrija apenas o que não pôde ser determinado.

## Problema

Levantamentos de campo chegam como PDFs rasterizados, frequentemente girados,
fora de escala e com anotações manuscritas. Vetorizadores tradicionais copiam o
traço, mas não compreendem cotas, semântica ou restrições. Redesenhar manualmente
consome horas e ainda depende de interpretação humana.

## Usuários

- Engenheiro civil ou arquiteto que valida medidas e hipóteses.
- Desenhista/CADista que precisa de uma base limpa para continuar o projeto.
- Gestor que compara tempo, custo e qualidade do serviço.

## Proposta de valor

- Primeiro DXF em minutos, não horas.
- Medidas e hipóteses rastreáveis até a imagem original.
- Geometria limpa em camadas e entidades CAD nativas.
- Revisão curta focada em divergências reais.

## Requisitos funcionais

| ID | Requisito |
|---|---|
| FR-001 | Usuário convidado cria projeto e envia PDF privado. |
| FR-002 | Sistema valida, renderiza e classifica todas as páginas. |
| FR-003 | Sistema identifica planta principal, detalhes e listas. |
| FR-004 | OpenAI e Claude produzem leituras independentes e estruturadas. |
| FR-005 | Textract registra texto e bounding boxes como evidência auxiliar. |
| FR-006 | Sistema normaliza cotas, unidades, alturas e quantidades. |
| FR-007 | Divergências geram issues e reanálise regional. |
| FR-008 | Sistema constrói scene graph com entidades, medidas e constraints. |
| FR-009 | Usuário revisa cotas, associações, tipos e aproximações. |
| FR-010 | Exportação só ocorre após aprovação de uma revisão imutável. |
| FR-011 | Sistema gera DXF, prévia, auditoria e quantitativos. |
| FR-012 | Usuário exclui projeto e artefatos imediatamente. |
| FR-013 | Artefatos expiram automaticamente após sete dias. |
| FR-014 | Sistema registra versões de modelo, prompt e revisão. |

## Casos de vitrine

### Fácil: Campo do Guaxindiba

Provar reconstrução de campo estruturado, círculo, áreas, muros, portões,
patamares, textos e cotas em camadas.

### Médio: Campo da Toca

Provar separação semântica entre planta principal e desenhos auxiliares, sem
misturar escalas ou coordenadas.

### Difícil: Praça Raul Campelo

Provar tratamento honesto de contorno orgânico, círculos, patamares, equipamentos
e posições parcialmente indeterminadas.

## KPIs do MVP

| ID | Métrica | Meta |
|---|---|---|
| KPI-001 | DXFs dourados aprovados pelo domínio | 3 de 3 |
| KPI-002 | Cotas confirmadas transferidas corretamente | 100% |
| KPI-003 | Primeiro rascunho dos casos de vitrine | até 3 min/página |
| KPI-004 | Revisão fácil/média/difícil | até 1/3/5 min |
| KPI-005 | DXF abre e passa na auditoria | 100% dos exports |
| KPI-006 | Regressão sem crash nas 16 páginas | 100% |
| KPI-007 | Suposições não registradas | zero |

## Fora do escopo

- DWG no MVP.
- Editor CAD completo.
- Garantia de precisão sem revisão.
- Inferência de medida inexistente.
- Plantas 3D, BIM e coordenadas geodésicas.
- Comparador V1/V2.
- Uso público sem convite.

## Restrições

- Dados podem ser processados globalmente em APIs comerciais.
- PDFs reais permanecem fora do Git.
- Um engenheiro/cliente aprova os gabaritos.
- Custo de IA é medido por página e não otimizado antes da baseline.

## Referências

- [FDD](FDD.md)
- [NFR](NFR.md)
- [Acceptance Criteria](ACCEPTANCE_CRITERIA.md)
- [Traceability](../engineering/TRACEABILITY.md)

