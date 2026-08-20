# T6 — BUILD REPORT

Task Contract: [T6-worker-consumo.md](T6-worker-consumo.md) · Feature: F-020 ·
Harness: Claude Code (implementador-opus) · Worktree: `croquito-f020`, branch
`f-020-orcamento-web`, sem commit.

## BUILD REPORT

```text
Status: BUILD_COMPLETE
Files changed: services/worker/src/croquito_worker/local_queue.py (modificado);
  tests/worker/test_estimate_extraction_worker.py (novo)
Validation executed: make check (exit 0); make test (exit 0, 1690 passed / 13 skipped
  pytest + 581 passed vitest); uv run pytest tests/worker/test_estimate_extraction_worker.py
  tests/worker/test_valuation_extraction_worker.py -x -q (24 passed); verificação por
  mutação do espelho (2 mutações, ambas detectadas pelo teste novo)
Validation skipped: none
Unavailable capabilities: none
Assumptions: (1) os blobs da rodada de orçamento moram sob
  `tenants/{tenant}/estimate-rounds/{round_id}/`, o mesmo prefixo que a rota da API já usa
  para a planilha publicada e o mesmo que `tests/api/test_estimate_round_routes.py`
  escreve em `PLATE_IMAGE_REF`; (2) o braço pago injetável (`valuation_extraction_adapter`)
  serve as duas cadeias, porque a legenda quantificada é a MESMA tarefa de prompt e um
  segundo seam só criaria a chance de um deles ficar sem o gate de teto de gasto;
  (3) os códigos de falha (`PROVIDER_EXECUTION_FAILED`, `LOCAL_UPLOAD_INVALID`,
  `VALUATION_EXTRACTION_FAILED`, …) são os mesmos nas duas cadeias
Remaining risks: (1) comentário desatualizado em services/api (fora do escopo desta task,
  ver "Divergência de documentação"); (2) nenhuma cobertura e2e do braço do orçamento —
  é a T5 que a consome
Human decisions required: aplicar (ou não) a correção do comentário de
  services/api/src/croquito_api/main.py:1128-1131, que continua afirmando que o worker não
  consome `extract_estimate_plate`
```

## Baseline

Medido na árvore ANTES de qualquer edição, com os diffs de T1–T3 já presentes:

| Comando | Resultado |
|---|---|
| `make check` | exit 0 |
| `make test` | exit 0 — pytest 1678 passed, 13 skipped; vitest 581 passed (32 arquivos) |

Nenhuma falha preexistente. Os 12 testes a mais no estado final são os do arquivo novo.

## Arquivos alterados

| Arquivo | Por quê |
|---|---|
| `services/worker/src/croquito_worker/local_queue.py` | Roteia `extract_estimate_plate` e `rerender_estimate_takeoff_overlay` e executa os dois sobre `estimate_rounds`/`estimate_round_revisions`, reusando o caminho da medição parametrizado por cadeia (`RoundChain`) em vez de duplicá-lo. |
| `tests/worker/test_estimate_extraction_worker.py` (novo) | Oráculo dos dois comandos novos e da não regressão do despacho; semeia as DUAS tabelas com o mesmo `round_id` para provar que nenhum comando lê a cadeia errada. |

## O desenho: a diferença virou dado, não cópia

O contrato pedia espelho "com as diferenças estritamente necessárias" e proibia duplicar
blocos longos. As duas cadeias fazem o mesmo trabalho e diferem em quatro coisas: tabela
raiz, tabela de revisões, conjunto de colunas JSON da revisão e prefixo dos blobs. Isso
está declarado numa `RoundChain` congelada (`VALUATION_ROUND_CHAIN`, `ESTIMATE_ROUND_CHAIN`)
e os handlers passaram a receber a cadeia como primeiro argumento:

| Antes | Depois |
|---|---|
| `_handle_valuation_extraction` | `_handle_round_extraction(chain, …)` |
| `_extract_valuation_plate` | `_extract_round_plate(chain, …)` |
| `_publish_valuation_extraction` | `_publish_round_extraction(chain, …)` |
| `_settle_valuation_extraction` | `_settle_round_extraction(chain, …)` |
| `_current_takeoff_head` / `_publish_takeoff_overlay` / `_handle_takeoff_overlay_rerender` | idem, com `chain` |
| `_REVISION_HEAD_COLUMNS` (constante) | `RoundChain.head_columns` |
| `INSERT` escrito à mão em dois lugares | `_insert_round_revision(connection, chain, …)` |

`document_columns` é a lista completa e ordenada das colunas JSON da revisão e alimenta ao
mesmo tempo o `SELECT` da cabeça e o `INSERT` da revisão nova — os dois não podem mais
discordar sobre o que uma revisão carrega. O `_render_round_overlay` ficou intacto na
assinatura porque `test_valuation_overlay_worker.py` o monkeypatcha.

Zero mudança de comportamento na medição: as únicas linhas dos handlers antigos que mudaram
são as que trocaram um literal por um campo da cadeia. Para a cadeia da medição os literais
resultantes são idênticos aos anteriores (`valuation_rounds`,
`valuation_round_revisions`, `valuation-extraction-v1`, `valuation-overlay-v1`,
`plate_image_object_key`, `takeoff_overlay_object_key`, e as mesmas mensagens de recusa,
via `RoundChain.label = "medição"`).

## Testes novos (12, em `tests/worker/test_estimate_extraction_worker.py`)

Todos com a fixture sintética escrita no próprio teste; nenhum documento de cliente, nenhuma
chamada externa. A semeadura cria a rodada de orçamento **e** uma rodada de medição de mesmo
`round_id`, que é a única forma de um teste enxergar um comando lendo a tabela errada.

| Teste | O que cobre |
|---|---|
| `…publica_pacote_overlay_e_lineage_numa_revisao` | Caminho feliz: `done`, `plate_page_count`, `version` da rodada 1→2, revisão v1 com `takeoff_packet_json`/`takeoff_registration_json`, autor `estimate-extraction-v1`, refs/digests sob `estimate-rounds/`, `TAKEOFF_OVERLAY_PACKET_DIGEST` do pacote recém-extraído, lineage sem resposta bruta — e a rodada de medição intocada |
| `…entrega_o_envelope_do_orcamento_sem_job_id` | O comando chega pelo transporte (`run_once`) e é roteado antes da guarda de `job_id` |
| `…chamam_o_provider_uma_vez` | Reentrega do mesmo envelope não repaga o provider (claim atômico) |
| `…falha_do_provider_declara_o_codigo_e_nao_publica_nada` | `failed` + `PROVIDER_EXECUTION_FAILED`, sem revisão, sem blob, `version` intacta |
| `…prancha_divergente_do_digest_consentido_recusa` | `LOCAL_UPLOAD_INVALID` antes de qualquer chamada paga |
| `…extracao_de_outro_tenant_nao_e_reivindicada` | O claim exige o tenant do JWT |
| `…comando_da_medicao_continua_indo_para_a_cadeia_da_medicao` | Não regressão do despacho: o comando antigo publica na tabela antiga, e os blobs vão para `valuation-rounds/` |
| `…rerender_do_orcamento_publica_overlay_sem_avancar_a_versao` | Revisão nova carrega TUDO da cabeça (inclusive `estimate_json`, a coluna que só existe nesta cadeia) e a versão da rodada não anda |
| `…pacote_defasado_no_envelope_e_descartado` | Comando obsoleto é descartado em silêncio, sem gravar PNG |
| `…rodada_de_outro_tenant_nao_e_redesenhada` | Isolamento por tenant no re-render |
| `…envelope_de_extracao…nao_e_roteavel` / `…envelope_de_overlay…nao_e_roteavel` | Corpo malformado levanta `UnroutableMessageError` |

### Verificação por mutação (o teste é detector, não decoração)

| Mutação aplicada em `local_queue.py` | Resultado |
|---|---|
| `estimate_json` removido de `document_columns` | 1 falha (`…rerender_do_orcamento…`), exatamente o apagamento silencioso do orçamento montado |
| `revisions_table` da cadeia de orçamento apontando para `valuation_round_revisions` + chave de blob do prefixo da medição | 6 falhas |

Arquivo restaurado byte a byte depois de cada mutação (`diff` limpo contra a cópia).

## Portões

| Comando | Saída |
|---|---|
| `make check` | exit 0 — ruff check/format, mypy strict (192 arquivos, sem erro), check_docs, drift de contratos, build web, `terraform fmt -check` |
| `make test` | exit 0 — pytest **1690 passed, 13 skipped** (baseline 1678+12 novos); vitest **581 passed** (32 arquivos) |
| `uv run pytest tests/worker/test_estimate_extraction_worker.py tests/worker/test_valuation_extraction_worker.py -x -q` | 24 passed |
| `uv run pytest tests/worker/test_valuation_extraction_worker.py tests/worker/test_valuation_overlay_worker.py -q` | 22 passed — os testes da medição, **sem nenhuma alteração neles**, sobre o código refatorado |

## Desvios conscientes do contrato

1. **Refatoração em vez de espelho literal.** O contrato autorizava ("extraia função
   compartilhada quando a diferença for só a tabela"); o efeito é que o diff de
   `local_queue.py` toca linhas dos handlers da medição. Critério de aceite 3 continua
   satisfeito: toda linha alterada é troca de literal por campo da cadeia, e os testes
   existentes da medição (não editados) provam o comportamento idêntico.
2. **Seam único do adapter pago.** Não criei `estimate_extraction_adapter`; a injeção
   continua sendo `valuation_extraction_adapter`, agora documentada como seam das duas
   cadeias. Motivo: a tarefa de prompt é a mesma e um segundo ponto de injeção poderia
   nascer sem o gate de teto de gasto. Impacto na T5: o e2e do orçamento injeta a fixture
   pelo mesmo kwarg.
3. **Chaves de blob do orçamento definidas em `local_queue.py`**, e não ao lado das da
   medição em `valuation/round_extraction.py`, para não sair do escopo de arquivos do
   contrato. Alternativa melhor a considerar fora desta task: mover
   `_estimate_plate_image_object_key`/`_estimate_takeoff_overlay_object_key` para
   `round_extraction.py`, junto do módulo que documenta por que nomes de chave moram num
   lugar só.

## Divergência de documentação encontrada e NÃO corrigida (fora de escopo)

`services/api/src/croquito_api/main.py:1128-1131`
(`InlineProcessingQueue.enqueue_estimate_plate_extraction`) ainda afirma:

> "O braço do worker que consome este comando é trabalho posterior (F-020 não o inclui);
> até lá o despacho o trata como mensagem não roteável, que é o desfecho seguro."

Depois desta task a frase é falsa. O contrato exclui `services/api/` do escopo, então não
editei: registro aqui para decisão do orquestrador. Correção sugerida: trocar as duas
frases por "O braço do worker que consome este comando é o `dispatch` de
`local_queue.py` (F-020 T6)."

## Oportunidades vistas e NÃO implementadas

- `docs/features/F-020-orcamento-base-web/feature.md` e a `plan.md` registram o consumo do
  worker como pendência; atualizá-los é ato do orquestrador ao fechar a feature.
- O envelope das quatro rotas de rodada (`round_id` + `extraction_id`/`packet_sha256`)
  poderia virar um decodificador declarado, em vez de dois blocos de `isinstance` no
  `dispatch`. Fora do escopo e sem ganho de comportamento.
- `_render_round_overlay` lê o PNG promovido sem teto de bytes (comentário existente
  justifica: o objeto foi escrito pelo próprio worker). Continua verdadeiro para a cadeia
  de orçamento; nada a fazer, mas vale registrar que a justificativa agora cobre dois
  produtores.
