# Instruções para agentes — field

Estas regras estendem o [AGENTS.md](../../AGENTS.md) da raiz. Leia também
[ADR-0043](../../docs/adr/0043-app-de-campo-pwa-offline-first.md) — as decisões que este
workspace materializa — e o
[Feature Contract da F-032](../../docs/features/F-032-app-levantamento-campo/feature.md).

## Boundary

`apps/field` é a PWA offline-first do técnico em campo (ADR-0043). Ela coleta pontos,
segmentos, medidas e fotos ancoradas localmente; não resolve geometria exata, não decide
consenso e não substitui o scene graph — o pacote exportado entra no pipeline como
observação (`unresolved`/`approximate`), sujeita aos portões existentes.

## Regras

- `src/domain/` é a fonte oficial do levantamento, nunca o canvas: tipos serializáveis
  puros, sem import de `react` nem de `dexie`. Se um tipo de domínio precisar de um
  helper de UI ou storage, o helper fica fora de `src/domain/`.
- O desenho é `<svg>` nativo, sem biblioteca de canvas: rendering/interação somente,
  igual ao princípio de `apps/web`.
- Coordenadas e medidas em **milímetros inteiros** — nunca float, nunca outra unidade
  sem uma tarefa nova que decida a conversão.
- Toda ação do usuário persiste localmente via `SurveyRepository` **antes** do feedback
  visual (antes de atualizar o estado de React). Isto não é estilo, é a garantia de que
  uma ação em campo sobrevive a fechar o app no meio.
- Dado local nunca é apagado antes do `ack` do servidor — `acknowledge` só muda
  `status`, nunca remove a linha do outbox.
- Proibido introduzir transporte de rede (`fetch`, `axios`, WebSocket) em
  `src/outbox/` ou em qualquer lugar deste workspace sem uma tarefa que autorize
  explicitamente a sincronização — esta fatia é só local.
- Tailwind v4 é restrito a `apps/field` (ADR-0043, D5): não é precedente para
  reestilizar `apps/web`, que continua em CSS puro.
- Código e identificadores em inglês; todo texto visível em português do Brasil.

## Conclusão

Mudança de comportamento do levantamento atualiza o Feature Contract da F-032 e seus
critérios de aceite; mudança de domínio serializável que vier a virar contrato de
sincronização passa primeiro por `make contracts`, quando essa fatia existir.
