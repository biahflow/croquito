# F-046 — Evidência

Feature: [A praça de várias pranchas](feature.md)
Estado: `READY_FOR_REVIEW`
Data: 2026-08-29 (segunda rodada de captura, depois do PR #127)

Esta é a evidência da [T6](tasks/T6-evidencia-de-navegador.md), a validação de navegador da
feature (`BROWSER_REQUIRED`, critério de aceite 12). Ela foi produzida contra o stack local
em Docker — PostgreSQL, floci e Keycloak reais, API em `uvicorn` e a SPA em `vite` —, com
dado **100% sintético**: nenhuma prancha, legenda, praça ou medição de cliente foi usada,
aberta ou capturada, e **nenhuma chamada paga a provider aconteceu**.

A primeira captura desta feature registrou um **achado bloqueante**: o boletim vencido não
se declarava vencido e a tela não oferecia remontá-lo, o que tornava a ordem do pacote de
design aprovado impercorrível numa rodada só. O achado foi **resolvido pelo PR #127**, e
este documento é a captura refeita: o percurso inteiro — montar, ver a dupla contagem,
declarar a identidade, ver o boletim se declarar vencido, remontar, ver o total novo —
agora acontece **numa rodada só**, e está fotografado assim.

## Gates humanos

| Gate | Estado |
| --- | --- |
| `ARCHITECTURE_DECISION_REQUIRED` | ✅ [ADR-0057](../../adr/0057-multiplas-pranchas-por-praca-na-extracao-de-legenda.md) **aceito por ato humano em 2026-08-28**, com os quatro pontos confirmados sem emenda |
| `ARCHITECTURE_DECISION_REQUIRED` (segunda ordem, nascida na T2) | ✅ [ADR-0062](../../adr/0062-a-deriva-de-centavo-entre-folhas-da-praca.md) — a GERAL governa o centavo da praça — **aceito por ato humano em 2026-08-29** |
| `DESIGN_APPROVAL_REQUIRED` | ✅ [Design Approval Package](mock/README.md) revisão 1 **aprovado por ato humano em 2026-08-28**, inclusive a decisão 9 ("a parcela que fica"), que nasceu ao desenhar |
| Teto de gasto da extração | ✅ **Decisão humana de 2026-08-29**: o teto continua **por chamada**, com a contagem de folhas declarada antes e o `WORKSITE_PLATE_LIMIT` de 12 por praça ([plan.md](plan.md), "O teto de gasto continua por chamada") |
| Merge do PR e o aceite da [issue #101](https://github.com/biahflow/croquito/issues/101), numa praça real | ⏳ **Pendente** — é ato humano, e é a única coisa que falta |

## O que foi entregue, por tarefa

| # | Tarefa | Onde |
| --- | --- | --- |
| T1 | [O consolidado da praça e o vínculo de identidade no domínio](tasks/T1-consolidado-e-vinculo-no-dominio.md) | `packages/valuation/src/croquito_valuation/worksite_takeoff.py` |
| T2 | [O boletim da praça: união dos conjuntos e a parcela fundida](tasks/T2-boletim-da-praca.md) | `packages/valuation/src/croquito_valuation/worksite_calc.py`, `calc_matrix.py`, `calc.py` |
| T2b | [O centavo da praça: a GERAL governa a deriva](tasks/T2b-centavo-da-praca.md) | `packages/valuation/src/croquito_valuation/workbook_writer.py`, `canonical.py`, `template.py` |
| T3 | [Persistência e rotas `/v1` da praça](tasks/T3-persistencia-e-rotas.md) | `services/api/src/croquito_api/valuation_rounds.py`, `database.py`, `main.py`, migrações `0024`–`0026`, [API Contract](../../architecture/API_CONTRACT.md) |
| T4 | [Promover N folhas: seleção explícita, em lote](tasks/T4-promover-n-folhas.md) | `services/api/src/croquito_api/main.py` (`POST .../plates`, `.../plates/extractions`), `services/worker/src/croquito_worker/local_queue.py`, `valuation/round_extraction.py` |
| T5 | [A tela da praça](tasks/T5-tela-da-praca.md) | `apps/web/src/medicao/praca.ts`, `MedicaoApp.tsx`, `etapas.ts`, `api.ts`, `requests.ts`, `styles.css` |
| T5c | O boletim vencido se declara vencido e pode ser remontado (PR #127) — nascida do achado bloqueante desta evidência, e por isso **sem contrato próprio no [plan.md](plan.md)** | `services/api/src/croquito_api/valuation_rounds.py` (`bulletin_sources_digest`, `bulletin_sources_state`), `main.py`, `apps/web/src/medicao/MedicaoApp.tsx` (`BannerBoletimVencido`), `etapas.ts`, `labels.ts` |
| T6 | Esta evidência | [`evidencia/`](evidencia) e este arquivo |

## Critérios de aceite do contrato

| # | Critério | O que o prova |
| --- | --- | --- |
| 1 | Rodada com duas pranchas produz dois `TakeoffPacket` íntegros, e `TAKEOFF_EVIDENCE_MISMATCH` continua recusando item de outra folha | `tests/valuation/test_worksite_takeoff.py::test_build_lists_plates_by_id_and_digest_without_items`; `tests/e2e/test_valuation_worksite_v1_chain.py`. **Exercido de ponta a ponta**: as três folhas da rodada nova têm pacotes com digests distintos — `6bdb354d122e`, `fdbaba4c2da0` e `d34f858279dd` no bloco "Folhas do consolidado" de [`04-item-repetido.png`](evidencia/04-item-repetido.png) e [`06-depois-da-fusao.png`](evidencia/06-depois-da-fusao.png) |
| 2 | `WorksiteTakeoff` referencia os pacotes por `plate_id` + digest e recusa digest que não confere | `::test_packet_digest_mismatch_is_refused_on_revalidation`, `::test_missing_packet_is_refused_on_revalidation`, `::test_duplicate_plate_id_is_refused`. **Na tela**: [`06-depois-da-fusao.png`](evidencia/06-depois-da-fusao.png) abre com "Folhas do consolidado" — as três folhas, cada uma com o digest do seu pacote, sob o `sha256 3d707f1dc1d5` do consolidado — e com a frase "O consolidado **não contém itens**" |
| 3 | Rodada de **uma** prancha responde byte a byte como hoje | `tests/valuation/test_worksite_calc.py::test_single_plate_worksite_is_byte_identical_to_the_single_plate_valuation`, `::test_single_plate_worksite_keeps_the_worksite_key_and_name_without_suffix`, `::test_a_single_plate_worksite_keeps_the_sheet_names_it_has_today`; `tests/api/test_valuation_worksite_calc.py::test_o_calc_de_uma_folha_continua_byte_a_byte_o_boletim_de_hoje`; `tests/api/test_valuation_worksite.py::test_a_praca_de_uma_folha_continua_respondendo_como_hoje`. **Na tela**: [`08-praca-de-uma-folha.png`](evidencia/08-praca-de-uma-folha.png) — etapa `Prancha` no singular, sem faixa de folhas, sem etapa `Praça`, sem "folha 1 de 1" |
| 4 | Item repetido entre folhas conta uma vez **por leitura** enquanto não houver declaração, e a memória mostra as parcelas com suas folhas | `tests/valuation/test_worksite_calc.py::test_without_a_declaration_the_repeated_item_contributes_twice_from_named_plates`, `::test_identical_looking_items_in_different_plates_count_as_two_without_a_link`. **Na tela**: [`04-item-repetido.png`](evidencia/04-item-repetido.png) — `AD04050060(/)` aparece com `61,20 m²` nas três folhas, o total da praça é `R$ 65.175,00` (3 × `R$ 21.725,00`), e o aviso diz que "duas leituras do mesmo elemento em folhas diferentes **contam as duas**" |
| 5 | Declarado o vínculo, o total cai para uma parcela, a declaração aparece com autor e instante, e o boletim é reproduzível | `::test_declared_fusion_counts_once_and_keeps_the_discarded_reading_in_the_memory`, `::test_fusion_uses_the_kept_quantity_and_reports_the_difference`; `tests/api/test_valuation_worksite_codes.py::test_o_item_fundido_contribui_uma_parcela_so_no_boletim_da_praca`. **Na tela, e agora na mesma rodada da captura 04**: [`06-depois-da-fusao.png`](evidencia/06-depois-da-fusao.png) — total `R$ 59.055,00` (= `65.175,00 − 6.120,00`), folha 2 com o item em `0,00` e a memória dizendo `FUNDIDA NA FOLHA rodada-…`, e o carimbo `≡ identidade declarada` com autor, instante e nota |
| 6 | Vínculo sem autor, sem instante ou entre itens da **mesma** folha é recusado com código nomeado | `tests/valuation/test_worksite_takeoff.py::test_link_between_items_of_the_same_plate_is_refused`, `::test_link_missing_provenance_is_refused`; `tests/api/test_valuation_worksite.py::test_o_vinculo_dentro_da_mesma_folha_recusa_com_o_codigo_do_dominio`, `::test_o_corpo_nao_pode_carimbar_quem_declarou`. **Na tela**, a recusa da mesma folha é antecipada antes da viagem (`recusaDoVinculo` em `apps/web/src/medicao/praca.ts`) e o autor/instante nunca saem do cliente — em [`06-depois-da-fusao.png`](evidencia/06-depois-da-fusao.png) os dois são do servidor. ⚠️ A recusa **não foi fotografada**: ver "O que NÃO foi exercido" |
| 7 | Colisão de `item_id` entre pacotes não confunde nada | `tests/valuation/test_worksite_takeoff.py::test_same_item_id_minted_in_two_plates_are_not_confused`; `tests/valuation/test_worksite_calc.py::test_the_same_item_id_on_two_plates_is_two_elements_until_declared`. **Na tela**, a chave inteira aparece sempre: [`05-declarar-identidade.png`](evidencia/05-declarar-identidade.png) mostra `rodada-…44f5a3 · ti_e623aa6c45401282` ao lado de `rodada-…44f5a3-f2 · ti_836e23c81455b06b`. ⚠️ A colisão em si **não foi semeada** — as folhas da captura cunharam ids diferentes |
| 8 | Item `proposed`/`ambiguous` em qualquer folha bloqueia o boletim da praça, com o erro apontando **qual** folha | `tests/valuation/test_worksite_calc.py::test_pending_item_in_any_plate_blocks_the_worksite_bulletin`; `tests/api/test_valuation_worksite_calc.py::test_o_calc_da_praca_recusa_folha_pendente_nomeando_qual`; `tests/api/test_valuation_worksite.py::test_a_praca_sem_folha_extraida_nao_fecha_e_diz_qual_falta`. **Na tela**: [`07-recusa-folha-pendente.png`](evidencia/07-recusa-folha-pendente.png) — "Bloqueada porque falta terminar folha 2 de 3 — `…-f2`; folha 3 de 3 — `…-f3`", repetida nas três etapas que a recusa trava |
| 9 | Fechamento de pacote de serviços é por `(plate_id, item_id)`; item fundido é fechado uma vez | `tests/valuation/test_worksite_calc.py::test_fused_item_does_not_need_a_package_closure_of_its_own`, `::test_fusion_in_the_matrix_regime_zeroes_only_the_fused_contribution`; `tests/api/test_valuation_worksite_codes.py::test_a_decisao_de_codigo_da_folha_2_nao_toca_o_conjunto_da_folha_1`, `::test_o_desfazer_alcanca_a_folha_2_e_reabre_o_pacote_dela`. **Exercido**: as três folhas da rodada nova foram codificadas e fechadas uma a uma, cada uma com `plate_id` no corpo |
| 10 | Planilha da praça no gabarito, com a PLANILHA GERAL consolidando por código e o guardrail de arredondamento verde | `tests/valuation/test_worksite_calc.py::test_the_general_sheet_consolidates_the_worksite_total_by_code`, `::test_the_workbook_plans_a_worksite_with_a_declared_fusion`, `::test_a_worksite_with_a_real_name_reaches_the_workbook`; `tests/api/test_valuation_consolidation.py::test_a_deriva_de_centavo_declarada_chega_ao_cliente` (ADR-0062). ⚠️ **A exportação do `.xlsx` não foi exercida no navegador**: ver "O que NÃO foi exercido" |
| 11 | `make check` e `make test` verdes; snapshot de OpenAPI aditivo | Portões abaixo; `tests/api/test_openapi_contract.py` é o gate do snapshot |
| 12 | Evidência renderizada da tela real (`BROWSER_REQUIRED`) | Este documento e as nove capturas — **os oito estados do pacote aprovado foram alcançados**, e o caminho do pacote (montar → dupla contagem → declarar → total novo) agora é **percorrível numa rodada só**, com o estado novo do #127 fotografado no meio dele |

## As capturas

Todas do navegador real (Chromium via Playwright, viewport de 1440 px, `deviceScaleFactor`
2) contra o stack local, autenticado pelo Keycloak local com `orcamentista.local` — o papel
`orcamentista`, que é o desta jornada.

A praça sintética é **PRACA NOVA AURORA**, `praca-nova-aurora`, com três folhas vindas de um
PDF de quatro páginas: a prancha sintética do repositório (`render_synthetic_plate`) com a
página duplicada. As três folhas leem, portanto, a **mesma** legenda — que é o caso mais
exigente para o consolidado, porque sem vínculo declarado tudo conta três vezes.

As capturas vêm de **três rodadas**, e cada imagem diz de qual pelo `plate_id` visível nela:

- `rodada-01a04ead-…44f5a3` — **a rodada desta segunda captura**, semeada contra a `main`
  com o #127 dentro. É dela que vêm as capturas 04, 05, 05b e 06, que são o percurso
  contínuo do pacote aprovado, **numa sessão de navegador só**.
- `rodada-01a04e62-…572a7` — a rodada da primeira captura, no estado intermediário (folha 1
  revisada, folha 2 pendente, folha 3 na fila). Dela vêm, **reaproveitadas sem alteração**,
  as capturas 01, 02, 03 e 07: elas fotografam estados que o #127 não tocou, e refazê-las
  produziria a mesma tela com outro UUID.
- `rodada-01a04e69-…195ab4` — a praça de **uma** folha, o controle. Dela vem a captura 08,
  também reaproveitada.

O rótulo da medição difere entre as duas praças de três folhas (`MEDICAO NOVA AURORA
01/2026` na primeira, `MEDICAO PRACA AURORA 01/2026` na segunda) porque são rodadas
distintas, abertas em sessões distintas. A praça, o catálogo, a prancha e as três folhas são
os mesmos por construção.

| Arquivo | Rodada | O que prova |
| --- | --- | --- |
| [`01-a-praca-e-suas-folhas.png`](evidencia/01-a-praca-e-suas-folhas.png) | `…572a7` | A faixa de cartões com as três folhas, o foco marcado (`▸ em foco` + barra à esquerda) e o estado de cada folha por **texto e forma**: `✓ extraída e revisada`, `▲ pendente de revisão`, `◐ em extração`. A etapa `Praça` existe na faixa de etapas, e `Pranchas` está no plural |
| [`02-acrescentar-folhas.png`](evidencia/02-acrescentar-folhas.png) | `…572a7` | O lote de promoção: o texto declara que "nenhuma vem marcada por padrão", as páginas 1–3 aparecem desabilitadas com "já é folha desta praça", e com a página 4 marcada o botão passa a dizer **"Acrescentar 1 folha à praça"**. Logo abaixo, o lote da leitura paga continua com nada marcado e o botão sem número — os dois lotes na mesma imagem |
| [`03-folha-em-revisao.png`](evidencia/03-folha-em-revisao.png) | `…572a7` | A folha 2 em foco: cabeçalho "Prancha e legenda — **folha 2 de 3**", a imagem **daquela** folha com as marcações dela sobre ela, "Itens da legenda — folha 2 de 3" citando `…-f2` e o pacote `796a3cb53298`, e os sete itens `proposto`/`ambíguo` da folha ainda não revisada |
| [`04-item-repetido.png`](evidencia/04-item-repetido.png) | `…44f5a3` | **Passo 1 do percurso.** Boletim montado na tela e o mesmo serviço contando uma vez **por leitura**: `AD04050060(/)` com `61,20 m²` nas três folhas, total da praça `R$ 65.175,00`, boletim `sha256 ecf8e35a6493`, e o aviso de que sem declaração humana as leituras "contam as duas". Nenhum vínculo declarado ainda |
| [`05-declarar-identidade.png`](evidencia/05-declarar-identidade.png) | `…44f5a3` | **Passo 2.** A declaração par a par: "A parcela que fica" e "A leitura absorvida", cada lado com folha e leitura escolhidas explicitamente, a chave inteira `(plate_id, item_id)` dos dois, a **prévia do servidor** (`122,40 m²` → `61,20 m²`) e a nota obrigatória antes do botão "Declarar identidade" |
| [`05b-boletim-vencido-e-remontagem.png`](evidencia/05b-boletim-vencido-e-remontagem.png) | `…44f5a3` | **Passo 3, e o estado que o #127 criou.** Declarada a identidade (versão 45), a etapa Boletim diz por extenso "Boletim vencido: a rodada mudou depois de a medição ser montada; monte o boletim de novo", oferece **"Montar o boletim de novo"** ao lado do aviso, declara que "os números abaixo são os da montagem anterior e continuam gravados como estão", e a faixa de etapas mostra `Boletim · em aberto` — não mais `concluída` |
| [`06-depois-da-fusao.png`](evidencia/06-depois-da-fusao.png) | `…44f5a3` | **Passo 4.** A etapa `Praça` depois de remontar: "Folhas do consolidado" com as três folhas e o digest de cada pacote sob o consolidado `3d707f1dc1d5`, o total `R$ 59.055,00`, boletim novo `sha256 1296d6d3bbbe`, a folha 2 com o item em `0,00`/`R$ 0,00` e a memória dizendo `FUNDIDA NA FOLHA rodada-…`, e o vínculo carimbado com `≡ identidade declarada`, autor, instante e nota |
| [`07-recusa-folha-pendente.png`](evidencia/07-recusa-folha-pendente.png) | `…572a7` | A recusa nomeando **qual** folha: "Bloqueada porque falta terminar folha 2 de 3 — `…-f2`; folha 3 de 3 — `…-f3`", nas três etapas que ela trava (Praça, Boletim, Aprovação) |
| [`08-praca-de-uma-folha.png`](evidencia/08-praca-de-uma-folha.png) | `…195ab4` | O controle: praça de uma folha, com a etapa `Prancha` no singular, sem faixa de folhas, sem etapa `Praça` e sem "folha 1 de 1" — idêntica à tela de antes da feature |

## O achado bloqueante da primeira captura, e o conserto

**Estado: resolvido pelo PR #127.** A primeira captura desta feature registrou, como
`BLOCKER`, que declarar uma identidade sobre uma praça cujo boletim já fora montado deixava
a orçamentista com um total maior do que o que ela acabara de declarar: o boletim gravado
não refletia a fusão, a tela não dizia que ele estava vencido e não oferecia remontá-lo —
apesar de o próprio toast da declaração mandar remontar. A rota `POST .../calc` sempre
aceitou; o buraco era da tela.

O que o #127 acrescentou, e que esta captura exerce:

- **O servidor passou a declarar o vencimento.** `bulletin_sources_digest` carimba, no ato
  que monta a medição, o digest das fontes que a geraram; `bulletin_sources_state`
  recalcula esse digest na leitura e devolve `stale` no bloco `bulletin` do estado da
  rodada (`services/api/src/croquito_api/valuation_rounds.py`). O vencimento é uma
  **relação entre dois instantes**, e não uma dedução da tela.
- **A tela passou a dizer e a oferecer.** `BannerBoletimVencido`
  (`apps/web/src/medicao/MedicaoApp.tsx`) escreve o estado por extenso e põe o botão
  "Montar o boletim de novo" ao lado; `etapas.ts` deixou de marcar a etapa `Boletim` como
  `done` enquanto ela estiver vencida, e a etapa de aprovação também não fecha.
- **Rodada montada antes da feature não é declarada vencida.** Sem o carimbo do passado,
  `bulletin_sources_state` devolve `stale: false` e mostra os dois digests — afirmar
  "vencido" sem o fato que o sustenta seria a mesma invenção que o bloco existe para
  evitar. É por isso que a rodada `…572a7`, semeada na primeira captura, **não** serviu
  para fotografar o estado novo, e uma rodada nova foi semeada.

Verificação do desfecho, na própria rodada da captura, depois de remontar:

```bash
curl -s -H "Authorization: Bearer test:tenant-local:orcamentista.local:orcamentista" \
  http://127.0.0.1:8000/v1/valuation-rounds/01a04ead-289b-7631-825a-61ec0044f5a3 \
  | python3 -c 'import json,sys; b=json.load(sys.stdin)["bulletin"]; print(b["stale"], b["sources_digest"] == b["current_sources_digest"])'
# False True  — o boletim gravado voltou a descrever esta praça
```

**Consequência para a evidência**: a ordem do pacote aprovado — montar o boletim, ver a
dupla contagem, declarar a identidade, ver o total novo — é agora **percorrível numa rodada
só**, e as capturas 04, 05, 05b e 06 são exatamente essa sequência, na mesma rodada
`01a04ead-…44f5a3` e na mesma sessão de navegador. Os números se fecham na própria imagem:
`65.175,00 − 6.120,00 = 59.055,00`.

## Observações que não são defeito

- **`WORKSITE_NAME_DOES_NOT_FIT_SHEET` passou a chegar cedo.** Na primeira captura, a
  recusa do nome comprido só aparecia na montagem do boletim — depois de revisar e
  codificar as N folhas. O #127 levou a mesma recusa para a **abertura** da rodada, que é
  onde o nome é digitado, e a tela passou a escrever a dica do teto ao lado do campo "Nome
  da obra" (`DICA_NOME_DA_OBRA`, visível na abertura). A rodada desta captura nasceu com um
  nome que cabe, então a recusa não aparece nas imagens.
- **O overlay das âncoras da folha 2+ é declarado vencido, em palavra.** Em
  [`03-folha-em-revisao.png`](evidencia/03-folha-em-revisao.png) a tela escreve que "o
  desenho das âncoras desta folha (folha 2 de 3) não é refeito depois de uma decisão: o
  re-render em fila ainda é o da primeira folha da praça". É dívida **declarada** pela T5, no
  idioma do [ADR-0030](../../adr/0030-overlay-do-takeoff-reconstruido-na-fila.md), não um
  defeito escondido.

## Como o estado foi semeado

Tudo sintético, e pelas **mesmas rotas `/v1` que a tela chama** — nenhuma etapa avançou por
escrita direta no banco. A rodada nova foi semeada num banco PostgreSQL **criado para esta
captura** (`croquito_f046_r2`), ao lado do banco de desenvolvimento e do banco da primeira
captura, nenhum dos dois tocado.

1. **Catálogo e rodada** — `POST /v1/uploads/presign` + `PUT` real na URL assinada (floci) e
   `POST /v1/valuation-rounds` com o catálogo sintético de cinco códigos.
2. **Folhas** — a prancha sintética do repositório (`render_synthetic_plate`) com a página
   duplicada quatro vezes, enviada por presign, e `POST .../plates` promovendo as páginas 1,
   2 e 3 **em lote**. A página 4 ficou de fora de propósito, para que o lote de promoção
   tivesse o que oferecer (é o que a captura 02, da primeira rodada, mostra).
3. **Extração** — `POST .../plates/extractions`, consumida por um `LocalQueueWorker`
   construído **com o adapter de fixture** (`legend_fixture_adapter`), o mesmo seam do e2e
   `tests/e2e/test_valuation_worksite_v1_chain.py`.
4. **Revisão e códigos** — `POST .../takeoff/decisions`, `.../code-assignments/decisions` e
   `.../code-assignments/closures`, uma folha de cada vez, com `plate_id` no corpo, usando as
   decisões sintéticas do repositório (`build_demo_takeoff_decisions`,
   `build_demo_code_assignments`).
5. **Boletim, declaração, vencimento e remontagem** — feitos **no navegador**, pelos botões
   da tela, numa sessão só: "Montar boletim e memória", os quatro seletores do vínculo, "Ver
   o efeito no total antes de declarar", "Declarar identidade" e, no estado que o #127
   criou, "Montar o boletim de novo".

Nenhum provider pago foi chamado em nenhum ponto: `CROQUITO_REAL_PROVIDERS_ENABLED` continuou
`false` e o adapter da extração foi o de fixture, injetado pelo processo do worker.

## O que NÃO foi exercido

- **Nenhuma praça real atravessou.** A praça, as três folhas e os sete itens são fixture
  inventada. O aceite da issue #101 pede uma praça de verdade, de mais de uma prancha; isso
  continua pendente e é ato humano.
- **A rodada paga não foi autorizada e não aconteceu.** A extração das folhas entrou
  pelo adapter de fixture; nenhuma legenda foi lida por provider. O que a evidência prova do
  custo é o que a **tela declara** antes de gastar (o número de folhas no botão), não o gasto.
- **As três folhas têm a mesma legenda**, porque são a mesma página duplicada. A dupla
  contagem aparece, portanto, **triplicada**, e a declaração par a par remove **uma** parcela
  das três — o que também prova que a fusão é par a par, e não uma deduplicação em massa. O
  pacote aprovado desenhou duas folhas compartilhando um item; a captura mostra o mesmo
  mecanismo com três.
- **A colisão de `item_id` entre pacotes não foi semeada.** As folhas da captura cunharam ids
  diferentes; o critério 7 continua provado só por teste.
- **As recusas de vínculo não foram fotografadas.** `WORKSITE_LINK_SAME_PLATE` e o vínculo
  incompleto têm teste e antecipação na tela (`recusaDoVinculo`), mas nenhuma imagem.
- **A exportação da planilha da praça não foi exercida no navegador.** A etapa "Aprovação e
  exportação" ficou em aberto: nenhuma aprovação nominal foi dada e nenhum `.xlsx` foi
  gerado. O critério 10 está provado por teste, não por arquivo.
- **O vencimento sobre uma medição APROVADA não foi fotografado.** `BannerBoletimVencido`
  escreve uma frase a mais quando há aprovação em vigor (`REMONTAR_CADUCA_A_APROVACAO`), e
  ela tem teste (`apps/web/src/medicao/boletimVencido.test.tsx`,
  `tests/api/test_valuation_bulletin_staleness.py`); como nenhuma aprovação nominal foi dada
  nesta rodada, a imagem 05b mostra o banner **sem** essa frase.
- **A extração que falha não foi exercida.** O estado `✕ extração falhou` de `praca.ts` não
  aparece em nenhuma captura.
- **Nada foi exercido em homologação.** Toda a evidência é do stack local, e as migrações
  `0024`–`0026` foram aplicadas apenas nos bancos locais criados para as duas rodadas de
  captura (`croquito_f046` e `croquito_f046_r2`), ao lado do banco de desenvolvimento, que
  não foi tocado.
- **A recusa de folha pendente foi vista pela etapa, não pelo `POST .../calc`.** A tela
  desabilita "Abrir praça" enquanto a praça não fecha, então o erro
  `WORKSITE_TAKEOFF_PLATE_PENDING` do servidor não chegou a ser disparado pelo navegador;
  o que a captura 07 mostra é a recusa derivada, com as folhas nomeadas.

## Portões

| Portão | Resultado |
| --- | --- |
| `uv run python scripts/check_docs.py` | verde — 535 arquivos Markdown, paridade de lifecycle verificada |
| `make check` | verde (`exit 0`) — ruff, `ruff format --check`, mypy strict, `check_docs`, drift de contratos (`schema_export --check` + `contracts:check`), build do web, build do app de campo, `terraform fmt` |
| `make test` | verde (`exit 0`) — 3015 pytest (17 pulados), 1556 vitest do web, 261 do app de campo |

**Baseline**: nada em `apps/web/`, `services/` ou `packages/` foi alterado por esta tarefa —
o diff é só `docs/features/F-046-praca-de-varias-pranchas/`.

## Riscos remanescentes

- O padrão do boletim vencido está resolvido para os atos que mudam as fontes da medição
  (`BULLETIN_SOURCE_COLUMNS` + folhas + rótulos da obra + catálogo). Um ato futuro que mude o
  boletim **sem** passar por essas fontes voltaria a produzir o defeito em silêncio: a lista
  é a fronteira, e ela precisa crescer junto com o que alimenta a medição.
- O teto de folhas por praça (`WORKSITE_PLATE_LIMIT` = 12) não foi exercido: a captura tem
  três folhas e o aviso de quantas ainda cabem, nunca a recusa.
- O desempenho da etapa `Praça` com muitas folhas não foi medido: a tela renderiza o boletim e
  a memória **de cada folha** numa página só, e com 12 folhas isso é quatro vezes o que a
  captura mostra.
