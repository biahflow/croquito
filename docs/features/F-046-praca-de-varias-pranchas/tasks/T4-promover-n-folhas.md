# F-046 · T4 — Promover N folhas: seleção explícita, em lote

Feature: [F-046](../feature.md) · Plano: [plan.md](../plan.md) · Estado: **Pendente**

## Objetivo

Deixar o humano escolher quais páginas de um PDF (ou quais PDFs) viram pranchas da praça, em um
ato em lote, sem promoção automática e com o custo declarado antes.

## Escopo

- `services/worker/src/croquito_worker/valuation/round_extraction.py`
- `services/worker/src/croquito_worker/valuation/cli.py`
- `services/api/src/croquito_api/main.py` (o disparo da extração por folha)
- `tests/worker/`, `tests/api/`

## Fora de escopo

- Alinhamento geométrico entre folhas; OCR novo; provider novo
- Promover todas as páginas automaticamente — recusado por decisão do pacote de design

## Critérios de aceite

1. `promote_first_page` deixa de ser o único caminho: a promoção passa a receber **quais**
   páginas promover, e nenhuma vem marcada por padrão.
2. PDF com N páginas continua não sendo recusado, e a contagem continua declarada no estado.
3. Cada folha promovida vira seu próprio `TakeoffPacket`, com `plate_id`, `page_number` e
   `image_sha256` próprios, e `TAKEOFF_EVIDENCE_MISMATCH` segue intacto dentro de cada pacote.
4. O custo da extração é apurado **por folha** e o lote informa quantas folhas serão extraídas
   antes de executar; o teto por rodada continua valendo.
5. Extração de folha que falha não derruba as demais, e a folha fica com estado próprio.
6. Rodada de uma folha continua percorrendo o mesmo caminho de hoje.

## Validação

`uv run pytest tests/worker tests/api` verde; `make check` verde. Nenhuma chamada paga nos
testes — fixtures offline.
