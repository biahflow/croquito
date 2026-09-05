# F-017 — A trilha de autorização de IA vira tela

## Status

`READY_FOR_SPEC`

> Nasce em 2026-08-19, no inventário SaaS da
> [F-012](../F-012-operacao-saas-autorizacao-ia/feature.md), e **ganha Feature Contract em
> 2026-09-05** por seleção humana.
>
> A auditoria de 2026-08-23 já tinha encolhido esta feature à metade: o **custo por tenant
> foi entregue** pela [F-031](../F-031-value-events/feature.md) — `GET /v1/metrics/summary`
> devolve `ai_cost` e `rounds_ai_cost`. O que resta é a **trilha**: quem autorizou, quando,
> sob qual referência contratual, e quando revogou.

## Classification

`INTERFACE_CHANGE` — realiza o **estado 6** do Design Approval Package da
[F-034](../F-034-disponibilidade-de-jornada/feature.md), que já o desenhou como bloco
**reservado**, com traço tracejado e a nota "torna-se real quando a auditoria do entitlement
virar tela, que é a F-017". O pacote da F-034 é o ponto de partida do desenho — não se
começa do zero.

## Priority

A definir pelo dono. A recomendação é `MEDIUM`: é a feature que responde "quem ligou isso, e
quando" — pergunta que só aparece quando algo já saiu errado, mas que, quando aparece, não
tem outra resposta.

## Problem

Ligar e desligar o processamento de IA de um tenant é ato de plataforma com efeito de
dinheiro: com ele ligado, upload de cliente pode disparar chamada paga. Hoje o ato é
gravado — `audit_events` registra —, mas **não há tela**: a única forma de responder "desde
quando este tenant está autorizado, e quem autorizou" é consulta ao banco.

O desenho já existe e está aprovado como reservado. O que falta é a rota que lê a trilha e o
bloco que a mostra.

## Desired Outcome

Na tela de plataforma, ao lado do estado atual de cada tenant, o histórico completo: cada
autorização e revogação com autor, instante e referência contratual — legível por quem não
tem acesso ao banco.

## Scope

1. **Rota de leitura** da trilha por tenant, sob `platform_operator`, alimentada pelos
   eventos já gravados — sem tabela nova.
2. **O bloco reservado do pacote da F-034 vira real**, no mesmo lugar e com a mesma forma
   que ele desenhou.
3. **Custo ao lado da trilha**: o `ai_cost` da F-031 já existe e responde a outra metade da
   mesma pergunta ("quanto isso custou desde que foi ligado").

## Out of Scope

- Tabela de auditoria nova: os eventos já são gravados, e duplicá-los criaria duas
  verdades.
- Exportar a trilha, alertar sobre gasto ou impor teto por tenant — o teto por invocação já
  existe (F-012) e mudar sua natureza é feature própria.

## Acceptance Criteria

1. A trilha mostra **todos** os atos de autorização e revogação do tenant, do mais recente
   ao mais antigo, com autor, instante e referência contratual.
2. Tenant nunca autorizado mostra a trilha vazia dizendo isso — não uma tela em branco.
3. A rota é leitura pura: nenhum estado muda, nenhuma chamada paga acontece.
4. O bloco corresponde ao estado 6 do pacote aprovado da F-034.

## Unknowns

1. **Se a trilha é só do entitlement de IA ou de todo ato de plataforma** (disponibilidade
   de jornada da F-034, acervo da F-037, índice da F-041). A resposta mais barata é a
   primeira; a mais útil, a segunda — e a segunda muda o desenho do bloco.

## Human Gates

1. **Seleção, prioridade e a resposta do unknown 1** — decisão do dono.
2. **Design Approval Package** — pode ser emenda ao pacote da F-034, já que ele desenhou o
   bloco; não necessariamente pacote novo.

## References

- `docs/features/F-034-disponibilidade-de-jornada/mock/README.md` — o estado 6 reservado.
- `services/api/src/croquito_api/database.py` — `audit_events`.
- `GET /v1/metrics/summary` (F-031) — o custo por tenant, metade já entregue desta feature.
