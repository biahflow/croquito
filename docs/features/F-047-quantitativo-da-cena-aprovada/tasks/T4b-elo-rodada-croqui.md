# F-047 · T4b — O elo entre a rodada de medição e o croqui aprovado

Feature: [F-047](../feature.md) · Plano: [plan.md](../plan.md) · Estado: **Entregue**

## Por que existe

A T5 fechou a divergência e expôs a lacuna que impedia a feature de existir ponta a ponta:
**ninguém criava divergência pela `/v1`**. `QuantitySource` e `record_divergence` estavam
prontos e testados, mas nada confrontava o `quantitativos.csv` da cena aprovada com o takeoff
da rodada — faltava o elo rodada ↔ job de croqui. Sem ele, tudo o que a feature construiu só
era exercitável sobre pacote semeado em teste.

## Mecanismo decidido

O elo é **ato humano explícito**, nunca inferido. Não se liga rodada a croqui por
`worksite_key` igual, por data próxima ou por qualquer semelhança — é a mesma regra que o
produto aplica em toda parte: proximidade nunca é associação implícita.

## Critérios de aceite

1. Declarar o elo é ato registrado (autor do JWT, instante do servidor), append-only.
2. Só aceita job do mesmo tenant, com cena **aprovada** e pacote exportado — sem isso não há
   `quantitativos.csv` de onde ler.
3. Trocar o elo é outro ato declarado; nunca edição silenciosa.
4. Com o elo, o confronto alimenta o item sem quantidade e **grava divergência** quando já
   havia a da legenda e a diferença passa da tolerância.
5. Item sem `element_ref`, ou com cena `approximate`/`unresolved`, não recebe nada, e o motivo
   é legível.
6. O confronto é idempotente e respeita resolução já tomada.
7. Rodada sem elo responde como hoje.

## Resultado

Entregue em 2026-08-29. O elo cita `export_id` + `scene_revision_id` + `dxf_sha256`, e não só o
job: um job pode ter várias revisões aprovadas, e sem isso não se saberia **qual** pacote
alimentou a medição. O confronto não grava revisão quando nada muda — gravar faria toda
releitura avançar a versão por um ato que não houve, invalidando o formulário aberto na tela.
Como o pacote só é publicado depois de `ensure_exportable` e da auditoria do DXF, a rota herda
o portão de exportação em vez de duplicá-lo.
