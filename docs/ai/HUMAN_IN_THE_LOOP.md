# Human in the Loop

Status: Accepted for MVP  
Responsável: Product / UX / Domain  
Última revisão: 2026-08-10

## Objetivo

Reservar atenção humana para decisões técnicas que dados e regras não resolvem,
sem transformar a aplicação em um CAD completo.

## Quando bloquear

- Dígitos ou unidades divergentes.
- Associação ambígua entre cota e segmento.
- Geometria subdeterminada.
- Constraint confirmado conflitante.
- Curva sem parâmetros suficientes.
- Entidade relevante `unresolved`.
- Calibração que deixou de valer para a cena atual (`CALIBRATION_SUPERSEDED`): a
  geometria já aceita nunca é reprojetada nem descartada em silêncio; ela é congelada
  atrás de uma issue crítica até o profissional recalibrar e decidir de novo.
- Export audit failed.

## Quando permitir aproximação

- Forma/posição visual sem cota suficiente.
- Contorno orgânico cuja fidelidade é explicitamente visual.
- Símbolo sem localização métrica completa, quando o usuário aceita a posição.

A UI explica impacto e exige ação “Aceitar como aproximado”. A decisão registra
usuário, timestamp, entidade, revisão e evidência exibida.

Critério de escopo — parte do levantamento que a família geométrica implementada ainda
não cobre — é diferente de aproximação. Ele é reconhecido nominalmente na aprovação,
fica registrado no pacote entregue e nunca dispensa um bloqueio de geometria. A lista do
que pode e do que não pode ser reconhecido está no
[ADR-0014](../adr/0014-scope-criteria-acknowledgement-at-approval.md).

## Unidade de revisão

Preferência: uma medida, associação, constraint ou entidade. Evitar perguntas
genéricas como “a página está correta?”.

## Prioridade

1. Critical issues que bloqueiam geometria.
2. Divergências numéricas.
3. Associação e unidade.
4. Aproximações.
5. Warnings informativos.

## Ações e efeitos

| Ação | Efeito |
|---|---|
| Corrigir medida | nova measurement com provenance humana |
| Reassociar | novo link; readings permanecem |
| Confirmar constraint | solver recalcula nova revisão |
| Aceitar aproximação | precision permanece `approximate` |
| Excluir falso positivo | entity candidate é rejeitada, não apagada do histórico |
| Reanalisar região | novas readings ligadas às anteriores |

## Responsabilidade

O sistema apresenta evidência e impacto. O usuário continua responsável pela
aprovação técnica. A exportação inclui ressalvas; não usa linguagem que implique
responsabilidade profissional automática do software.

## Métricas

- Tempo de revisão.
- Ações por issue.
- Reanálises por página.
- Correções por provider/task.
- Issues que retornam após correção.

Métricas não armazenam conteúdo sensível.

