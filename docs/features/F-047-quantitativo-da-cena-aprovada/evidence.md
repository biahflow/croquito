# F-047 — Evidência

Feature: [O quantitativo nasce da cena aprovada](feature.md)
Estado: `READY_FOR_REVIEW`
Data: 2026-08-29 (segunda rodada de captura, depois do PR #124)

Esta é a evidência da [T8](tasks/T8-evidencia-de-navegador.md), a validação de navegador da
feature (`BROWSER_REQUIRED`, critério de aceite 11). Ela foi produzida contra o stack local
em Docker — PostgreSQL, floci e Keycloak reais, API em `uvicorn` e a SPA em `vite` —, com
dado **100% sintético**: nenhum croqui, prancha, legenda ou medição de cliente foi usado,
aberto ou capturado.

A primeira captura desta feature registrou um **achado bloqueante**: a rota que resolve a
divergência respondia `500` em PostgreSQL, porque a chave de idempotência da operação não
cabia na coluna. O achado foi **resolvido pelo PR #124**, e este documento é a captura
refeita: o sexto estado — a resolução registrada, com autor, instante e o número preterido
ainda gravado — deixou de ser dívida e passou a ser imagem.

## Gates humanos

| Gate | Estado |
| --- | --- |
| `ARCHITECTURE_DECISION_REQUIRED` | ✅ [ADR-0058](../../adr/0058-quantitativo-derivado-do-scene-graph-e-identidade-de-elemento.md) **aceito por ato humano em 2026-08-28**, com a emenda da decisão 4 (só `exact` e `derived` alimentam a medição) e a tolerância da decisão 6 nomeada |
| `DESIGN_APPROVAL_REQUIRED` | ✅ **Aprovado por ato humano em 2026-08-28**, revisão 1 ([`mock/README.md`](mock/README.md)), com duas confirmações no mesmo ato: a borda exata da tolerância não abre issue (`>`, nunca `>=`), e a proposta assistida de agrupamento entra nesta feature |
| Merge do PR e aceite da [issue #102](https://github.com/biahflow/croquito/issues/102) | ⏳ **Pendente** — é ato humano, e é a única coisa que falta |

## O que foi entregue, por tarefa

| # | Tarefa | Onde |
| --- | --- | --- |
| T1 | [`element_ref` na entidade e o contrato gerado](tasks/T1-element-ref-na-entidade.md) | `packages/core/src/croquito_core/models.py`, `packages/contracts/scene.schema.json`, `packages/contracts/src/scene.generated.ts` |
| T2 | [O ato humano de identidade na revisão](tasks/T2-ato-de-identidade.md) | `POST /v1/jobs/{job_id}/elements`, `.../revocations`, documentadas no [API Contract](../../architecture/API_CONTRACT.md) |
| T2b | O rótulo legível ao lado da identidade | `SceneRevision.element_labels`, `POST /v1/jobs/{job_id}/elements/labels`, `apps/web/src/elementIdentityPanel.tsx` |
| T3 | [`quantitativos.csv` com identidade e agrupamento por elemento](tasks/T3-csv-por-elemento.md) | `services/worker/src/croquito_worker/dxf.py`, [DXF Output Spec](../../architecture/DXF_OUTPUT_SPEC.md) |
| T3b | [Polilinha aberta contribui comprimento](tasks/T3b-polilinha-aberta.md) | `services/worker/src/croquito_worker/dxf.py` |
| T4 | [`QuantitySource`: a quantidade atravessa a fronteira](tasks/T4-quantity-source.md) | `packages/valuation/src/croquito_valuation/quantity_source.py`, `takeoff.py` |
| T4b | [O elo declarado entre a rodada e o croqui aprovado](tasks/T4b-elo-rodada-croqui.md) | `POST /v1/valuation-rounds/{round_id}/scene-link` e `.../takeoff/scene-quantities`, `scene_confrontation.py`, migração `0028` |
| T5 | [Divergência: tolerância nomeada, issue e bloqueio](tasks/T5-divergencia.md) | `packages/valuation/src/croquito_valuation/quantity_divergence.py`, `POST .../takeoff/divergences/resolutions` |
| T5b | A conta da tolerância chega pronta do servidor | `quantity_divergence.py` (parcelas e razão gravadas), `apps/web/src/medicao/MedicaoApp.tsx` |
| T6 | [A proposta assistida de agrupamento](tasks/T6-proposta-assistida.md) | `packages/core/src/croquito_core/element_proposals.py`, `GET /v1/jobs/{job_id}/elements/proposals`, migração `0027` |
| T7a | [Tela da revisão: a identidade do elemento](tasks/T7-telas.md) | `apps/web/src/elementIdentityPanel.tsx`, `elementIdentity.ts`, `CroquiApp.tsx` |
| T7b | [Tela da medição: a quantidade da cena e a divergência](tasks/T7-telas.md) | `apps/web/src/medicao/MedicaoApp.tsx`, `medicao/cena.ts` |
| — | A chave de idempotência cabe na coluna (PR #124) — nascida do achado bloqueante desta evidência | `services/api/src/croquito_api/database.py`, migração `0023`, portão `tests/api/test_idempotency_operations.py` |
| T8 | Esta evidência | [`evidencia/`](evidencia) e este arquivo |

As migrações desta feature foram **relinearizadas para `0027` e `0028`** depois da F-046; a
primeira captura ainda as chamava de `0023` e `0024`.

## Critérios de aceite do contrato

| # | Critério | O que o prova |
| --- | --- | --- |
| 1 | `Entity.element_ref` existe, é opcional, sobrevive à revisão da aprovação e está no schema e nos tipos gerados | `tests/core/test_scene.py::test_element_ref_is_optional_and_coexists_with_id_and_label` e `::test_element_ref_survives_the_new_revision_created_on_approval`; o drift check de `make check`. **Exercido também de ponta a ponta**: a cena aprovada da segunda captura tem `EL-001`, `EL-002` e `EL-003`, declarados nas revisões v3–v5 e ainda presentes na revisão que a aprovação criou (`01a04ec9-3e2a-…`) |
| 2 | Cena **sem** `element_ref` produz `quantitativos.csv` e DXF iguais aos de hoje | `tests/core/test_scene.py::test_scene_without_element_ref_produces_the_same_export_package_as_before` e `tests/worker/test_dxf.py::test_croqui_sem_element_ref_nao_ganha_a_coluna` |
| 3 | Identidade proposta nasce `unresolved` e não alimenta quantidade sem decisão humana | `tests/api/test_element_proposals.py::test_listagem_devolve_proposta_rotulada_unresolved_nunca_identidade` e `::test_proposta_nao_confirmada_nao_alimenta_quantidade_nenhuma`. **Na tela**: [`01-proposta-e-ato.png`](evidencia/01-proposta-e-ato.png), onde a proposta aparece com o selo `⚙ proposta · unresolved` e o motivo escrito, ao lado do elemento que só existe porque alguém assinou |
| 4 | `QuantitySource` resolve pela identidade; sem `element_ref` de algum lado **não** resolve e diz o motivo | `tests/valuation/test_quantity_source.py::test_o_mesmo_418_12_dos_dois_lados_sem_identidade_nao_casa`, `::test_identidade_so_na_cena_tambem_nao_casa`, `::test_identidade_so_na_legenda_devolve_o_motivo_em_vez_de_palpitar`. **Na tela**: [`06-sem-par.png`](evidencia/06-sem-par.png) — o item "MEIO-FIO DE CONCRETO (TRECHO 2)" traz `51,80 m`, o **mesmo número** que a cena ofereceu ao EL-001, e mesmo assim não casa: "Número igual não é identidade" |
| 5 | Entidade `approximate` nunca vira quantidade de `TakeoffItem`, nem sob aceite | `tests/valuation/test_quantity_divergence.py::test_cena_inelegivel_nao_gera_divergencia` e `::test_o_modelo_da_issue_recusa_precisao_inelegivel_no_proprio_contrato`. **Na tela**, nas duas jornadas: [`02-aproximada-nao-alimenta.png`](evidencia/02-aproximada-nao-alimenta.png) (o croqui diz "✕ não alimenta a medição" com o motivo por extenso) e [`06-sem-par.png`](evidencia/06-sem-par.png) (a medição diz "a linha da cena é aproximada ou não resolvida: não alimenta a medição e também não compara"). O EL-003 foi aceito como aproximação na aprovação e **ainda assim** não atravessou |
| 6 | `TakeoffItem` com `source = scene_graph` carrega a precisão de origem e o `element_ref` | `tests/valuation/test_quantity_source.py`; contrato de takeoff em `packages/contracts/schemas/takeoff-packet.schema.json`. **Na tela**: [`03-quantidade-da-cena.png`](evidencia/03-quantidade-da-cena.png) — `◇ EL-001`, `origem: cena aprovada · revisão …`, `precisão de origem: exata`. O mesmo bloco aparece no topo de [`05-resolucao.png`](evidencia/05-resolucao.png), agora sobre o item que **acabou de sair** da divergência |
| 7 | Divergência igual à tolerância não abre; fora dela abre com os dois números, as duas origens e a diferença; o item não fecha; resolvê-la é decisão humana registrada | Borda: `tests/valuation/test_quantity_divergence.py::test_diferenca_exatamente_igual_a_um_por_cento_nao_abre` e `::test_um_centavo_acima_de_um_por_cento_abre`. Bloqueio: `::test_item_com_divergencia_aberta_nao_fecha_o_pacote`. Resolução: `::test_escolher_a_cena_registra_autor_e_instante_e_guarda_o_numero_preterido`. **Na tela, as duas metades**: [`04-divergencia.png`](evidencia/04-divergencia.png) (aberta e bloqueando) e [`05-resolucao.png`](evidencia/05-resolucao.png) (**resolvida**, com autor, instante, motivo e o número preterido ainda gravado) |
| 8 | A tolerância é constante nomeada e testada nas bordas | `::test_a_tolerancia_e_o_maior_entre_um_por_cento_e_o_piso`, `::test_diferenca_exatamente_igual_ao_piso_nao_abre`, `::test_o_piso_segura_o_item_miudo_quando_um_por_cento_seria_menor`. **Na tela**, a conta chega pronta do servidor: `1% × 42,00 m = 0,4200 m · piso de unidade = 0,01 m · tolerância = 0,4200 m (1% mandou)` em [`04-divergencia.png`](evidencia/04-divergencia.png), e a mesma linha permanece legível depois de resolvida em [`05-resolucao.png`](evidencia/05-resolucao.png) |
| 9 | Cena não aprovada, `unresolved`, aproximação sem aceite ou issue crítica continuam barrando o export — e com ele a quantidade | `tests/core/test_scene.py::test_export_gate_does_not_change_behaviour_because_of_element_ref`. **Exercido**: a quantidade da captura só existiu depois de `POST /v1/jobs/{id}/approve` e de o worker publicar o pacote com auditoria `approved`; o elo da rodada cita `export_id` e `dxf_sha256` do pacote publicado |
| 10 | `make check` e `make test` verdes; snapshot de OpenAPI aditivo | Portões abaixo |
| 11 | Evidência renderizada (`BROWSER_REQUIRED`) | Este documento e as seis capturas — **os seis estados estão provados**, incluindo a resolução, que a primeira captura não conseguiu alcançar |

## As capturas

Todas do navegador real (Chromium via Playwright, 1440 px de largura, `deviceScaleFactor`
2) contra o stack local, autenticado pelo Keycloak local — `engenheiro.local` na jornada do
croqui e `orcamentista.local` na da medição, cada papel na sua jornada.

As capturas vêm de **duas rodadas** de semeadura, e as duas usam a mesma fixture sintética
— o retângulo de `25,90 m × 21,75 m` do repositório (`tests/bundles.py`), a mesma proposta
aproximada aceita e os mesmos cinco itens de legenda. É por isso que os números batem entre
elas: `EL-001` = `51,800000 m` (as duas arestas de 25,90), `EL-002` = `43,500000 m` (as duas
de 21,75), `EL-003` aproximada, e a legenda lendo `42,00 m` no alambrado.

- **Primeira rodada** (cena `01a04df5-3f19-…`): capturas 01, 02, 03, 04 e 06, **reaproveitadas
  sem alteração**. O #124 não tocou nenhum desses estados, e refazê-las produziria a mesma
  tela com outro UUID.
- **Segunda rodada** (croqui `01a04ec9-3d97-…`, cena aprovada `01a04ec9-3e2a-…`, rodada de
  medição `01a04eca-1c00-…`): a captura 05, a que o `500` bloqueava.

| Arquivo | Rodada | O que prova |
| --- | --- | --- |
| [`01-proposta-e-ato.png`](evidencia/01-proposta-e-ato.png) | 1ª | O sistema **propõe** (`⚙ proposta · unresolved`, com o sinal que gerou a proposta escrito) e o humano **declara**: o carimbo diz quem, quando e sobre qual revisão da cena, e o elemento nasce com `◇ EL-001`, o rótulo "Meio-fio do passeio" e o selo "→ alimenta a medição" |
| [`02-aproximada-nao-alimenta.png`](evidencia/02-aproximada-nao-alimenta.png) | 1ª | O EL-003, `approximate`, marcado "✕ não alimenta a medição" com o motivo por extenso na tela — ao lado de dois elementos `exact` que alimentam |
| [`03-quantidade-da-cena.png`](evidencia/03-quantidade-da-cena.png) | 1ª | O item alimentado pela cena: origem, revisão e precisão visíveis, **nenhum campo de quantidade**, e "Editar quantidade" desabilitado **e visível**, com a razão ao lado |
| [`04-divergencia.png`](evidencia/04-divergencia.png) | 1ª | Os dois números lado a lado (cena `43,500000 m`, legenda `42,00 m`), a diferença `1,500000 m`, a conta da tolerância vinda do servidor por extenso, e o item bloqueado — "este item não fecha enquanto ninguém escolher qual das duas origens vale" |
| [`05-resolucao.png`](evidencia/05-resolucao.png) | 2ª | **O estado que o `500` bloqueava.** A divergência **resolvida** pela tela: o selo passou a "divergência resolvida", o carimbo diz quem (o `sub` da sessão `orcamentista.local`), quando (`29/08/2026 15:33`) e o quê ("decidiu que **vale a cena**: 43,500000 m"), o motivo escrito fica à vista, e a linha "Preterida: `42,00 m` · legenda lida — **continua gravada**. Resolver não é sobrescrever: nenhuma origem foi apagada". No topo do mesmo painel, o item já aparece alimentado pela cena, sem campo de quantidade e com "Editar quantidade" indisponível |
| [`06-sem-par.png`](evidencia/06-sem-par.png) | 1ª | O relatório do confronto, item a item: 1 alimentado, 1 divergência gravada, 3 sem mudança — cada ausência dizendo **de que lado** falta a identidade, inclusive o caso do número igual (`51,80`) que não casa |

## O achado bloqueante da primeira captura, e o conserto

**Estado: resolvido pelo PR #124.** A primeira captura registrou, como `BLOCKER`, que
`POST /v1/valuation-rounds/{round_id}/takeoff/divergences/resolutions` respondia `500` em
PostgreSQL — e portanto em homologação e em produção. A causa era o comprimento da chave de
idempotência: a rota monta `valuation-rounds.takeoff-divergence-resolutions:{round_id}`, 84
caracteres, e `idempotency_records.operation` era `VARCHAR(80)`. O `INSERT` estourava com
`StringDataRightTruncation`, e a suíte não pegava porque os testes de API rodam em SQLite,
que **ignora** o limite declarado do `VARCHAR`.

O que o #124 fez, e que esta captura exerce:

- **A coluna passou a caber**: `operation` foi de `80` para `512` (migração `0023`,
  forward-only). O defeito não era só desta rota — **nove** das operações que a API monta
  passavam de 80 caracteres.
- **Um portão impede a recorrência**: `tests/api/test_idempotency_operations.py` enumera
  TODAS as operações do código e reprova quando uma passa da largura da coluna. A largura
  não ficou maior "por precaução" no lugar de ser conferida.

O desfecho na tela é a captura [`05-resolucao.png`](evidencia/05-resolucao.png): a mesma
escolha ("Vale a cena") e o mesmo motivo que antes voltavam como "Failed to fetch" agora
gravam a resolução, e o número preterido continua ao lado do escolhido.

## Como o estado foi semeado

Tudo sintético, e o mais próximo possível do caminho real. A segunda rodada foi semeada num
banco PostgreSQL **criado para esta captura** (`croquito_f047_r2`), ao lado do banco de
desenvolvimento, que não foi tocado.

1. **Croqui** — a cadeia inteira pelas rotas da `/v1`, na mesma sequência de
   `scripts/smoke_local.py`: presign real → `PUT` na URL assinada → `POST /v1/jobs` →
   worker local consome a ingestão → `seed_review` do pacote sintético → decisões de
   leitura → calibração → aceite da proposta aproximada.
2. **Identidade** — três atos de `POST /v1/jobs/{job_id}/elements`, um por elemento, cada um
   criando revisão nova: `EL-001` sobre as duas arestas de 25,90 m ("Meio-fio do passeio"),
   `EL-002` sobre as duas de 21,75 m ("Alambrado da quadra") e `EL-003` sobre a polilinha
   `approximate` ("Canteiro gramado"). **Na primeira rodada esses três atos foram feitos no
   navegador**, e é isso que a captura 01 fotografa; na segunda eles entraram pela mesma
   rota que a tela chama, porque o que a segunda rodada existe para alcançar é a resolução
   da divergência.
3. **Aprovação e pacote** — `POST /v1/jobs/{id}/approve` com a aproximação aceita, depois
   `POST /v1/jobs/{id}/exports`; o worker publicou o `.zip` com auditoria `approved`. O
   `quantitativos.csv` saiu com a coluna nova e as linhas agrupadas por elemento:
   `EL-001` = `51,800000 m` `exact`, `EL-002` = `43,500000 m` `exact`, `EL-003`
   `approximate`.
4. **Medição** — rodada criada por `POST /v1/valuation-rounds` com catálogo sintético; o
   **pacote de takeoff foi gravado direto na revisão da rodada**, exatamente como
   `tests/api/test_valuation_round_routes.py::_publish_takeoff` faz, porque a extração de
   legenda é chamada **paga** e a T8 não tem autorização para gastá-la. Cinco itens
   desenhados para cobrir os cinco desfechos: sem quantidade com identidade (`fed`),
   quantidade divergente (`divergence_recorded`), número igual sem identidade, identidade
   de elemento aproximado, e identidade que não existe na cena.
5. **Elo e confronto** — `POST .../scene-link` pela API e o **confronto disparado na
   tela**, pelo botão "Confrontar o takeoff com a cena aprovada", que respondeu
   "Confronto concluído: 1 alimentado(s) pela cena, 1 divergência(s) gravada(s), 3 sem
   mudança" — o mesmo desfecho da primeira rodada.
6. **Resolução** — feita **no navegador**, no painel de decisão do item: a origem escolhida
   no rádio "Vale a cena", o motivo digitado no campo obrigatório e o botão "Registrar
   decisão".

Nenhum provider pago foi chamado em nenhum ponto: `CROQUITO_REAL_PROVIDERS_ENABLED`
permaneceu `false` e as chaves ficaram vazias.

## O que NÃO foi exercido

- **Nenhum croqui real atravessou.** A praça, a prancha, a legenda e os cinco itens são
  fixture inventada para esta captura. O aceite da issue #102 pede um croqui de verdade
  cuja quantidade chegue à medição sem redigitação; isso continua pendente e é ato humano.
- **A rodada paga não foi autorizada e não aconteceu**: o pacote de takeoff é escrito, não
  extraído; nenhuma leitura de legenda por provider foi executada.
- **"Vale a legenda" não foi fotografada.** A resolução capturada escolheu a cena; o outro
  desfecho tem teste (`tests/valuation/test_quantity_divergence.py`), não imagem. "Nenhuma
  das duas" aparece nas duas capturas como **indisponível**, com a razão ao lado, que é o
  estado desenhado.
- **A imagem da prancha não foi publicada** na rodada sintética, e as capturas da medição
  mostram o aviso honesto que a tela dá nesse caso. O overlay das âncoras, por
  consequência, também não foi exercido.
- **O estado 09 do pacote (o controle)** — croqui e medição sem identidade declarada,
  idênticos aos de hoje — não foi capturado no navegador; ele está coberto por teste
  (`test_scene_without_element_ref_produces_the_same_export_package_as_before` e
  `test_croqui_sem_element_ref_nao_ganha_a_coluna`), não por imagem.
- **Nada foi exercido em homologação.** Toda a evidência é do stack local; as migrações
  `0027` e `0028` foram aplicadas apenas nos bancos locais das duas rodadas de captura.
- **Revogar e renomear identidade** (`.../elements/revocations`, `.../elements/labels`) têm
  teste, mas não foram exercidos na tela.
- **A declaração de identidade pela tela não foi refeita na segunda rodada.** Ela está
  fotografada na captura 01, da primeira; na segunda, os três elementos entraram pela rota
  `POST /v1/jobs/{job_id}/elements`.

## Portões

| Portão | Resultado |
| --- | --- |
| `uv run python scripts/check_docs.py` | verde — 536 arquivos Markdown, paridade de lifecycle verificada |
| `make check` | verde (`exit 0`) — ruff, mypy strict, `check_docs`, drift de contratos, build do web, `terraform fmt` |
| `make test` | verde (`exit 0`) — 3209 pytest (17 pulados), 1688 vitest do web, 261 do app de campo |

**Baseline**: nada em `apps/web/`, `services/` ou `packages/` foi alterado por esta tarefa —
o diff é só `docs/features/F-047-quantitativo-da-cena-aprovada/`.

## Riscos remanescentes

- Um limite de `VARCHAR` que só o SQLite ignora era uma classe de defeito, não um caso; o
  portão do #124 fecha a classe **para a largura de `operation`**. Outras colunas estreitas
  continuam sem portão equivalente, e a suíte de API inteira continua rodando em SQLite.
- O desempenho do confronto sobre um `quantitativos.csv` grande não foi medido; a fixture
  tem cinco linhas.
- A resolução foi exercida sobre **uma** divergência. Uma rodada com muitas divergências
  abertas ao mesmo tempo — e o efeito delas na etapa de códigos e no boletim — não foi
  capturada.
