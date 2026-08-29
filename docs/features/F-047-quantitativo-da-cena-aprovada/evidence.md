# F-047 — Evidência

Feature: O quantitativo nasce da cena aprovada (`docs/features/F-047-quantitativo-da-cena-aprovada/feature.md`)
Estado: `READY_FOR_REVIEW` — com **um achado bloqueante** registrado abaixo
Data: 2026-08-29

Esta é a evidência da **T8**, a validação de navegador da feature (`BROWSER_REQUIRED`,
critério de aceite 11). Ela foi produzida contra o stack local em Docker — PostgreSQL,
floci e Keycloak reais, API em `uvicorn` e a SPA em `vite` —, com dado **100% sintético**:
nenhum croqui, prancha, legenda ou medição de cliente foi usado, aberto ou capturado.

> As referências ao `feature.md`, ao `plan.md`, aos Task Contracts e ao pacote de design
> aparecem como caminho escrito, não como link: esses arquivos vivem na `main` e ainda não
> estão na branch de integração desta feature. Depois da integração eles viram links.

## Gates humanos

| Gate | Estado |
| --- | --- |
| `ARCHITECTURE_DECISION_REQUIRED` | ✅ [ADR-0058](../../adr/0058-quantitativo-derivado-do-scene-graph-e-identidade-de-elemento.md) **aceito por ato humano em 2026-08-28**, com a emenda da decisão 4 (só `exact` e `derived` alimentam a medição) e a tolerância da decisão 6 nomeada |
| `DESIGN_APPROVAL_REQUIRED` | ✅ **Aprovado por ato humano em 2026-08-28**, revisão 1 (`mock/README.md`), com duas confirmações no mesmo ato: a borda exata da tolerância não abre issue (`>`, nunca `>=`), e a proposta assistida de agrupamento entra nesta feature |
| Merge do PR e aceite da [issue #102](https://github.com/biahflow/croquito/issues/102) | ⏳ **Pendente** — e o achado bloqueante abaixo precisa ser resolvido antes |

## O que foi entregue, por tarefa

| # | Tarefa | Onde |
| --- | --- | --- |
| T1 | `element_ref` na entidade e o contrato gerado | `packages/core/src/croquito_core/models.py`, `packages/contracts/scene.schema.json`, `packages/contracts/src/scene.generated.ts` |
| T2 | O ato humano de identidade na revisão | `POST /v1/jobs/{job_id}/elements`, `.../revocations`, documentadas no [API Contract](../../architecture/API_CONTRACT.md) |
| T2b | O rótulo legível ao lado da identidade | `SceneRevision.element_labels`, `POST /v1/jobs/{job_id}/elements/labels`, `apps/web/src/elementIdentityPanel.tsx` |
| T3 | `quantitativos.csv` com identidade e agrupamento por elemento | `services/worker/src/croquito_worker/dxf.py`, [DXF Output Spec](../../architecture/DXF_OUTPUT_SPEC.md) |
| T3b | Polilinha aberta contribui comprimento | `services/worker/src/croquito_worker/dxf.py` |
| T4 | `QuantitySource`: a quantidade atravessa a fronteira | `packages/valuation/src/croquito_valuation/quantity_source.py`, `takeoff.py` |
| T4b | O elo declarado entre a rodada e o croqui aprovado | `POST /v1/valuation-rounds/{round_id}/scene-link` e `.../takeoff/scene-quantities`, `scene_confrontation.py`, migração `0024` |
| T5 | Divergência: tolerância nomeada, issue e bloqueio | `packages/valuation/src/croquito_valuation/quantity_divergence.py`, `POST .../takeoff/divergences/resolutions` |
| T5b | A conta da tolerância chega pronta do servidor | `quantity_divergence.py` (parcelas e razão gravadas), `apps/web/src/medicao/MedicaoApp.tsx` |
| T6 | A proposta assistida de agrupamento | `packages/core/src/croquito_core/element_proposals.py`, `GET /v1/jobs/{job_id}/elements/proposals`, migração `0023` |
| T7a | Tela da revisão: a identidade do elemento | `apps/web/src/elementIdentityPanel.tsx`, `elementIdentity.ts`, `CroquiApp.tsx` |
| T7b | Tela da medição: a quantidade da cena e a divergência | `apps/web/src/medicao/MedicaoApp.tsx`, `medicao/cena.ts` |
| T8 | Esta evidência | `docs/features/F-047-quantitativo-da-cena-aprovada/evidencia/` e este arquivo |

## Critérios de aceite do contrato

| # | Critério | O que o prova |
| --- | --- | --- |
| 1 | `Entity.element_ref` existe, é opcional, sobrevive à revisão da aprovação e está no schema e nos tipos gerados | `tests/core/test_scene.py::test_element_ref_is_optional_and_coexists_with_id_and_label` e `::test_element_ref_survives_the_new_revision_created_on_approval`; o drift check de `make check`. **Exercido também de ponta a ponta**: a cena aprovada da captura tem `EL-001`, `EL-002` e `EL-003`, declarados na revisão v3–v5 e ainda presentes na revisão v6 que a aprovação criou |
| 2 | Cena **sem** `element_ref` produz `quantitativos.csv` e DXF iguais aos de hoje | `tests/core/test_scene.py::test_scene_without_element_ref_produces_the_same_export_package_as_before` e `tests/worker/test_dxf.py::test_croqui_sem_element_ref_nao_ganha_a_coluna` |
| 3 | Identidade proposta nasce `unresolved` e não alimenta quantidade sem decisão humana | `tests/api/test_element_proposals.py::test_listagem_devolve_proposta_rotulada_unresolved_nunca_identidade` e `::test_proposta_nao_confirmada_nao_alimenta_quantidade_nenhuma`. **Na tela**: [`01-proposta-e-ato.png`](evidencia/01-proposta-e-ato.png), onde a proposta aparece com o selo `⚙ proposta · unresolved` e o motivo escrito, ao lado do elemento que só existe porque alguém assinou |
| 4 | `QuantitySource` resolve pela identidade; sem `element_ref` de algum lado **não** resolve e diz o motivo | `tests/valuation/test_quantity_source.py::test_o_mesmo_418_12_dos_dois_lados_sem_identidade_nao_casa`, `::test_identidade_so_na_cena_tambem_nao_casa`, `::test_identidade_so_na_legenda_devolve_o_motivo_em_vez_de_palpitar`. **Na tela**: [`06-sem-par.png`](evidencia/06-sem-par.png) — o item "MEIO-FIO DE CONCRETO (TRECHO 2)" traz `51,80 m`, o **mesmo número** que a cena ofereceu ao EL-001, e mesmo assim não casa: "Número igual não é identidade" |
| 5 | Entidade `approximate` nunca vira quantidade de `TakeoffItem`, nem sob aceite | `tests/valuation/test_quantity_divergence.py::test_cena_inelegivel_nao_gera_divergencia` e `::test_o_modelo_da_issue_recusa_precisao_inelegivel_no_proprio_contrato`. **Na tela**, nas duas jornadas: [`02-aproximada-nao-alimenta.png`](evidencia/02-aproximada-nao-alimenta.png) (o croqui diz "✕ não alimenta a medição" com o motivo por extenso) e [`06-sem-par.png`](evidencia/06-sem-par.png) (a medição diz "a linha da cena é aproximada ou não resolvida: não alimenta a medição e também não compara"). O EL-003 da captura foi aceito como aproximação na aprovação e **ainda assim** não atravessou |
| 6 | `TakeoffItem` com `source = scene_graph` carrega a precisão de origem e o `element_ref` | `tests/valuation/test_quantity_source.py`; contrato de takeoff em `packages/contracts/schemas/takeoff-packet.schema.json`. **Na tela**: [`03-quantidade-da-cena.png`](evidencia/03-quantidade-da-cena.png) — `◇ EL-001`, `origem: cena aprovada · revisão 01a04df5-…`, `precisão de origem: exata` |
| 7 | Divergência igual à tolerância não abre; fora dela abre com os dois números, as duas origens e a diferença; o item não fecha; resolvê-la é decisão humana registrada | Borda: `tests/valuation/test_quantity_divergence.py::test_diferenca_exatamente_igual_a_um_por_cento_nao_abre` e `::test_um_centavo_acima_de_um_por_cento_abre`. Bloqueio: `::test_item_com_divergencia_aberta_nao_fecha_o_pacote`. Resolução: `::test_escolher_a_cena_registra_autor_e_instante_e_guarda_o_numero_preterido`. **Na tela**: [`04-divergencia.png`](evidencia/04-divergencia.png). ⚠️ **A metade final — "resolvê-la é decisão humana registrada" — NÃO foi exercida no navegador**: ver o achado bloqueante abaixo |
| 8 | A tolerância é constante nomeada e testada nas bordas | `::test_a_tolerancia_e_o_maior_entre_um_por_cento_e_o_piso`, `::test_diferenca_exatamente_igual_ao_piso_nao_abre`, `::test_o_piso_segura_o_item_miudo_quando_um_por_cento_seria_menor`. **Na tela**, a conta chega pronta do servidor: `1% × 42,00 m = 0,4200 m · piso de unidade = 0,01 m · tolerância = 0,4200 m (1% mandou)` em [`04-divergencia.png`](evidencia/04-divergencia.png) |
| 9 | Cena não aprovada, `unresolved`, aproximação sem aceite ou issue crítica continuam barrando o export — e com ele a quantidade | `tests/core/test_scene.py::test_export_gate_does_not_change_behaviour_because_of_element_ref`. **Exercido**: a quantidade da captura só existiu depois de `POST /v1/jobs/{id}/approve` e de o worker publicar o pacote com auditoria `approved`; o elo da rodada cita `export_id` e `dxf_sha256` do pacote publicado |
| 10 | `make check` e `make test` verdes; snapshot de OpenAPI aditivo | Portões abaixo |
| 11 | Evidência renderizada (`BROWSER_REQUIRED`) | Este documento e as seis capturas — **cinco dos seis estados provados**, o sexto bloqueado pelo defeito abaixo |

## As capturas

Todas do navegador real (Chromium, 1280–1440 px de largura, `deviceScaleFactor` 2) contra
o stack local, autenticado pelo Keycloak local — `engenheiro.local` na jornada do croqui e
`orcamentista.local` na da medição, cada papel na sua jornada.

| Arquivo | O que prova |
| --- | --- |
| [`01-proposta-e-ato.png`](evidencia/01-proposta-e-ato.png) | O sistema **propõe** (`⚙ proposta · unresolved`, com o sinal que gerou a proposta escrito) e o humano **declara**: o carimbo diz quem, quando e sobre qual revisão da cena, e o elemento nasce com `◇ EL-001`, o rótulo "Meio-fio do passeio" e o selo "→ alimenta a medição" |
| [`02-aproximada-nao-alimenta.png`](evidencia/02-aproximada-nao-alimenta.png) | O EL-003, `approximate`, marcado "✕ não alimenta a medição" com o motivo por extenso na tela — ao lado de dois elementos `exact` que alimentam |
| [`03-quantidade-da-cena.png`](evidencia/03-quantidade-da-cena.png) | O item alimentado pela cena: origem, revisão e precisão visíveis, **nenhum campo de quantidade**, e "Editar quantidade" desabilitado **e visível**, com a razão ao lado |
| [`04-divergencia.png`](evidencia/04-divergencia.png) | Os dois números lado a lado (cena `43,500000 m`, legenda `42,00 m`), a diferença `1,500000 m`, a conta da tolerância vinda do servidor por extenso, e o item bloqueado — "este item não fecha enquanto ninguém escolher qual das duas origens vale" |
| [`05-resolucao-bloqueada.png`](evidencia/05-resolucao-bloqueada.png) | **Não é o estado aprovado 07 do pacote de design.** É o ponto exato em que a jornada para: a escolha feita ("Vale a cena"), o motivo escrito, "Nenhuma das duas" indisponível com a razão ao lado — e a recusa que volta do servidor. Ver o achado bloqueante |
| [`06-sem-par.png`](evidencia/06-sem-par.png) | O relatório do confronto, item a item: 1 alimentado, 1 divergência gravada, 3 sem mudança — cada ausência dizendo **de que lado** falta a identidade, inclusive o caso do número igual (`51,80`) que não casa |

## Achado bloqueante: a resolução da divergência falha em PostgreSQL

**Severidade: `BLOCKER`.** `POST /v1/valuation-rounds/{round_id}/takeoff/divergences/resolutions`
responde `500` em PostgreSQL — e portanto em homologação e em produção. A tela mostra
"Failed to fetch" e a divergência **nunca** é resolvida.

A causa é o comprimento da chave de idempotência da operação:

- `services/api/src/croquito_api/main.py:12708` monta
  `operation = f"valuation-rounds.takeoff-divergence-resolutions:{round_id}"` — 48
  caracteres de prefixo mais 36 do UUID da rodada = **84 caracteres**;
- `services/api/src/croquito_api/database.py:901` declara
  `operation: Mapped[str] = mapped_column(String(80))`, e
  `services/api/src/croquito_api/migrations/versions/0001_baseline.py:49` cria a coluna
  como `sa.String(length=80)`.

O `INSERT` em `idempotency_records` estoura com
`psycopg.errors.StringDataRightTruncation: value too long for type character varying(80)`.

**Por que a suíte não pegou**: `tests/api/test_valuation_round_routes.py:117` monta o
`Database` em `sqlite+pysqlite`, e o SQLite **não aplica** o limite de `VARCHAR`. A rota é
a única da `/v1` cuja operação passa de 80 caracteres — as vizinhas (`takeoff-decisions:`,
`scene-quantities:`, `scene-link:`, `amendment-dossier:`) ficam entre 69 e 74.

Reprodução independente do navegador, contra o Postgres local:

```bash
curl -s -o /dev/null -w '%{http_code}\n' -X POST \
  -H "Authorization: Bearer test:tenant-local:seed-f047:orcamentista" \
  -H "Idempotency-Key: prova-do-defeito-1" -H "Content-Type: application/json" \
  -d '{"base_version":4,"item_id":"ti_00000000000000d1","choice":"scene","note":"Prova."}' \
  http://127.0.0.1:8000/v1/valuation-rounds/<round_id>/takeoff/divergences/resolutions
# 500
```

**O conserto não foi feito aqui, de propósito**: o Task Contract da T8 proíbe alterar
código de produção para viabilizar a captura, e a correção — encurtar a operação ou alargar
a coluna por migração forward-only — muda contrato de persistência e pertence à T5, com
revisão própria. Fica registrado como o achado que a T8 existe para produzir.

## Como o estado foi semeado

Tudo sintético, e o mais próximo possível do caminho real:

1. **Croqui** — a cadeia inteira pelas rotas da `/v1`, na mesma sequência de
   `scripts/smoke_local.py`: presign real → `PUT` na URL assinada → `POST /v1/jobs` →
   worker local consome a ingestão → `seed_review` do pacote sintético → decisões de
   leitura → calibração → aceite da proposta aproximada.
2. **Identidade** — declarada **no navegador**, pela tela: duas confirmações de proposta
   assistida (EL-001 e EL-002) e uma declaração manual da polilinha `approximate` (EL-003).
3. **Aprovação e pacote** — `POST /v1/jobs/{id}/approve` com a aproximação aceita, depois
   `POST /v1/jobs/{id}/exports`; o worker publicou o `.zip` com auditoria `approved`. O
   `quantitativos.csv` saiu com a coluna nova e as linhas agrupadas por elemento:
   `EL-001` = `51,80 m`, `EL-002` = `43,50 m`, `EL-003` = `approximate`.
4. **Medição** — rodada criada por `POST /v1/valuation-rounds` com catálogo sintético; o
   **pacote de takeoff foi gravado direto na revisão da rodada**, exatamente como
   `tests/api/test_valuation_round_routes.py::_publish_takeoff` faz, porque a extração de
   legenda é chamada **paga** e a T8 não tem autorização para gastá-la. Cinco itens
   desenhados para cobrir os cinco desfechos: sem quantidade com identidade (`fed`),
   quantidade divergente (`divergence_recorded`), número igual sem identidade, identidade
   de elemento aproximado, e identidade que não existe na cena.
5. **Elo e confronto** — `POST .../scene-link` pela API e o **confronto disparado na
   tela**, pelo botão "Confrontar o takeoff com a cena aprovada".

Nenhum provider pago foi chamado em nenhum ponto: `CROQUITO_REAL_PROVIDERS_ENABLED`
permaneceu `false` e as chaves ficaram vazias.

## O que NÃO foi exercido

- **Nenhum croqui real atravessou.** A praça, a prancha, a legenda e os cinco itens são
  fixture inventada para esta captura. O aceite da issue #102 pede um croqui de verdade
  cuja quantidade chegue à medição sem redigitação; isso continua pendente e é ato humano.
- **A resolução da divergência nunca foi registrada**, em lugar nenhum desta sessão — nem
  pela tela, nem pela API. O estado 07 do pacote de design (o número preterido gravado ao
  lado do escolhido) permanece **provado só por teste unitário sobre SQLite**.
- **A rodada paga não foi autorizada e não aconteceu**: o pacote de takeoff é escrito, não
  extraído; nenhuma leitura de legenda por provider foi executada.
- **A imagem da prancha não foi publicada** na rodada sintética, e as capturas da medição
  mostram o aviso honesto que a tela dá nesse caso. O overlay das âncoras, por
  consequência, também não foi exercido.
- **O estado 09 do pacote (o controle)** — croqui e medição sem identidade declarada,
  idênticos aos de hoje — não foi capturado no navegador; ele está coberto por teste
  (`test_scene_without_element_ref_produces_the_same_export_package_as_before` e
  `test_croqui_sem_element_ref_nao_ganha_a_coluna`), não por imagem.
- **Nada foi exercido em homologação.** Toda a evidência é do stack local; as migrações
  `0023` e `0024` foram aplicadas apenas no banco local.
- **Revogar e renomear identidade** (`.../elements/revocations`, `.../elements/labels`) têm
  teste, mas não foram exercidos na tela.

## Portões

| Portão | Resultado |
| --- | --- |
| `uv run python scripts/check_docs.py` | verde — 511 arquivos Markdown, paridade de lifecycle verificada |
| `make check` | verde (`exit 0`) — ruff, mypy strict, `check_docs`, drift de contratos, build do web, `terraform fmt` |
| `make test` | verde (`exit 0`) — 3039 pytest (13 pulados), 1600 vitest do web, 261 do app de campo |

**Baseline registrado**: a primeira execução de `make test` nesta máquina reprovou com 2
falhas e 372 erros de `setup`, todos com a mesma causa — `OSError: could not create
numbered dir` — porque o volume estava com 776 MiB livres (100% de capacidade). Nenhum era
regressão: os dois testes que falharam passam isolados, e a suíte inteira ficou verde
depois que o diretório temporário da própria execução anterior foi liberado. Fica escrito
porque o sintoma (centenas de erros em áreas não tocadas) não se parece com o que ele é.

## Riscos remanescentes

- O achado bloqueante acima impede declarar a feature pronta para o gate humano: a
  divergência abre e bloqueia o item, mas ninguém consegue resolvê-la fora do SQLite.
- Um limite de `VARCHAR` que só o SQLite ignora é uma classe de defeito, não um caso: a
  suíte de API inteira roda em SQLite, e qualquer coluna estreita se comporta assim.
- O desempenho do confronto sobre um `quantitativos.csv` grande não foi medido; a fixture
  tem cinco linhas.
