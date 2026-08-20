# T3 — BUILD REPORT

Formato canônico de [`docs/engineering-os/agents/builder.md`](../../../engineering-os/agents/builder.md).
Executado na branch `f-020-orcamento-web` (worktree isolado), sobre a árvore com os diffs
não commitados de T1 e T2. Nenhum commit foi criado: o diff fica na árvore.

```text
BUILD REPORT

Status: BUILD_COMPLETE
Files changed: services/api/src/croquito_api/database.py,
  services/api/src/croquito_api/estimate_rounds.py (novo),
  services/api/src/croquito_api/migrations/versions/0003_orcamento_estimate_rounds.py (novo),
  services/api/src/croquito_api/main.py,
  services/api/src/croquito_api/storage.py,
  services/api/src/croquito_api/pubsub_queue.py,
  services/api/src/croquito_api/valuation_rounds.py,
  tests/api/test_estimate_round_routes.py (novo),
  tests/api/openapi.snapshot.json,
  tests/fakes.py,
  docs/architecture/API_CONTRACT.md
Validation executed: make check (exit 0); make test (exit 0, 1678 passed / 13 skipped +
  web 581 passed em 32 arquivos); uv run pytest tests/api/test_estimate_round_routes.py
  -x -q (26 passed); uv run pytest tests/api/test_openapi_contract.py
  tests/api/test_migrations.py (13 passed, 10 skipped)
Validation skipped: tests/api/test_migrations.py — as 10 asserções marcadas
  `requires_postgres`, entre elas o gate de drift do ADR-0029
  (`test_baseline_nao_diverge_dos_modelos`) e
  `test_medicao_nasce_depois_da_baseline_com_o_indice_da_listagem`. Elas exigem
  `CROQUITO_TEST_POSTGRES_URL`. Tentei provisionar um PostgreSQL descartável
  (`docker run --rm postgres:17-alpine` em 127.0.0.1:55432); o contêiner subiu, mas o
  daemon do Docker parou de responder logo em seguida (`docker ps` não retorna) e a porta
  passou a recusar conexão, então o gate NÃO foi exercido. O CI define a variável e
  cobre estas asserções.
Unavailable capabilities: none (READ, WRITE e VALIDATE disponíveis; a única validação não
  executada depende de serviço externo indisponível na máquina, não de capacidade negada)
Assumptions: (1) o worker que consome os comandos de fila do orçamento
  (`extract_estimate_plate`, `rerender_estimate_takeoff_overlay`) é trabalho posterior —
  o escopo de T3 não inclui `services/worker`; (2) `make db-revision` (autogenerate)
  também exige banco, então a `0003` foi escrita à mão espelhando a `0002`, que é o que o
  contrato pede ("revisada à mão, forward-only"); (3) ADR-0038 segue `Proposed` — as
  decisões 1-6 foram usadas como especificação, o aceite continua sendo gate humano.
Remaining risks: (1) gate de drift do ADR-0029 não exercido localmente — se a `0003`
  divergir de `Base.metadata`, quem acusa é o CI; (2) a montagem do orçamento RENDERIZA e
  AUDITA a planilha dentro do request path, o que tensiona a fronteira declarada em
  `services/api/AGENTS.md` ("a API não renderiza PDF, não chama modelos e não gera DXF no
  request path") — foi feito assim porque o contrato de T3 manda ("escreve e audita via T2
  fail-closed, publica o .xlsx"); é render determinístico de dezenas de linhas, sem
  provider e sem I/O externo além do PUT, mas é candidato natural a virar comando de fila
  quando o orçamento real crescer; (3) se o commit da revisão perder a corrida otimista
  depois do PUT, o `.xlsx` fica órfão no bucket — inerte, porque a chave é derivada do
  digest do orçamento e nada a alcança sem a revisão, mas conta como lixo a expirar por
  retenção.
Human decisions required: aceite do ADR-0038; revisão linha a linha deste diff pelo modelo
  principal (aritmética de dinheiro e fronteira de dados); merge e deploy.
```

## Rotas publicadas

Todas sob papel `orcamentista` (`_require_valuation_reviewer`, primeira linha de cada
handler, inclusive nos `GET`), `tenant_id` do JWT, `Idempotency-Key` em todo `POST`,
`base_version` em toda mutação e `problem+json` com código estável.

| Método | Path |
|---|---|
| POST | `/v1/estimate-rounds` |
| GET | `/v1/estimate-rounds` |
| GET | `/v1/estimate-rounds/{round_id}` |
| POST | `/v1/estimate-rounds/{round_id}/catalogs` |
| POST | `/v1/estimate-rounds/{round_id}/catalogs/order` |
| POST | `/v1/estimate-rounds/{round_id}/plate` |
| GET | `/v1/estimate-rounds/{round_id}/plate` |
| POST | `/v1/estimate-rounds/{round_id}/plate/extractions` |
| GET | `/v1/estimate-rounds/{round_id}/takeoff` |
| GET | `/v1/estimate-rounds/{round_id}/takeoff/overlay` |
| POST | `/v1/estimate-rounds/{round_id}/takeoff/decisions` |
| GET | `/v1/estimate-rounds/{round_id}/code-suggestions` |
| POST | `/v1/estimate-rounds/{round_id}/code-suggestions/recompute` |
| GET | `/v1/estimate-rounds/{round_id}/catalog/search` |
| GET | `/v1/estimate-rounds/{round_id}/code-assignments` |
| POST | `/v1/estimate-rounds/{round_id}/code-assignments/decisions` |
| POST | `/v1/estimate-rounds/{round_id}/estimate` |
| GET | `/v1/estimate-rounds/{round_id}/estimate` |

18 operações, todas ADIÇÃO no snapshot OpenAPI: nenhuma operação existente foi removida ou
alterada e nenhum schema de `components` mudou (conferido por comparação de operações e
schemas entre `HEAD` e o snapshot regenerado; as linhas `-` do diff textual são
reordenação alfabética do JSON).

## Arquivos alterados, com o porquê

| Arquivo | Por quê |
|---|---|
| `services/api/src/croquito_api/database.py` | `EstimateRoundRecord` e `EstimateRoundRevisionRecord`, espelhos das tabelas da medição com `catalog_cascade_json` no lugar do catálogo único e sem os artefatos que não existem na pré-licitação. |
| `services/api/src/croquito_api/migrations/versions/0003_orcamento_estimate_rounds.py` | Revisão forward-only que cria as duas tabelas e os índices; escrita à mão, com docstring explicando o que difere da `0002`. |
| `services/api/src/croquito_api/estimate_rounds.py` | Camada de aplicação sem FastAPI: consultas escopadas por tenant, append-only, precondições de etapa, cascata (instalar, reordenar, ler), shortlist e busca sobre a cascata, portão fail-closed da planilha e o estado por etapa que a tela lê. |
| `services/api/src/croquito_api/main.py` | As 18 rotas ao FINAL do arquivo, os modelos de contrato novos, dois comandos de fila do orçamento e a generalização do cursor de listagem. |
| `services/api/src/croquito_api/storage.py` | `write_object`: não havia caminho de escrita no boundary do object store, e publicar o `.xlsx` exige um. |
| `services/api/src/croquito_api/pubsub_queue.py` | Os mesmos dois comandos no transporte Pub/Sub, com corpo idêntico ao do SQS. |
| `services/api/src/croquito_api/valuation_rounds.py` | Extração de `read_catalog` de dentro de `load_catalog` (sem mudança de comportamento), para o orçamento reusar leitura, conferência de digest, validação e cache em vez de copiá-los. |
| `tests/api/test_estimate_round_routes.py` | 26 testes de rota, incluindo toda a cobertura mínima nomeada no contrato. |
| `tests/api/openapi.snapshot.json` | Regenerado por `make openapi-snapshot` (ato deliberado). |
| `tests/fakes.py` | `FakeObjectStore.write_object`, contraparte do método novo do boundary. |
| `docs/architecture/API_CONTRACT.md` | Seção "Orçamento-base de obra" com as 18 rotas — **obrigatório**: `tests/api/test_openapi_contract.py` reprova rota exposta e não documentada. |

## Testes novos e o que cobrem

Cobertura mínima do contrato, item a item:

| Exigência do contrato | Teste |
|---|---|
| 403 sem papel em GET e POST | `test_sem_o_papel_toda_rota_recusa_antes_do_lookup` (10 leituras + 9 escritas, inclusive rodada inexistente) |
| POST sem `Idempotency-Key` recusa | `test_post_sem_idempotency_key_recusa` |
| `base_version` velho → 409 `REVISION_CONFLICT` | `test_base_version_velho_recusa_sem_gravar_nada` |
| `Idempotency-Key` reusada com payload diferente → 409 `IDEMPOTENCY_KEY_REUSED` | `test_idempotency_key_reusada_com_outro_comando_recusa` |
| Origem repetida na cascata → `ESTIMATE_CASCADE_ORIGIN_DUPLICATE` | `test_origem_repetida_na_cascata_recusa_com_o_codigo_do_dominio` |
| Caminho feliz até `estimate_json` + planilha publicada | `test_o_caminho_feliz_publica_orcamento_e_planilha_auditada` |
| Auditoria divergente → nada publicado e recusa estável | `test_auditoria_divergente_nao_publica_nada` |
| Reordenação da cascata muda a precificação da sugestão seguinte | `test_reordenar_a_cascata_muda_a_precificacao_da_sugestao_seguinte` |

Além dela: IDOR (`test_rodada_de_outro_tenant_e_404_e_nunca_403`), digest de origem
repetido, permutação incompleta na reordenação, cascata travada depois da decisão de
código, busca sem termo utilizável, etapas fora de ordem, confirmação sem citar fonte,
citação fora da cascata, BDI ilegível e negativo, takeoff com item pendente, prancha
associada uma vez só, extração paga sem provider, URL assinada fora do prefixo do tenant e
o estado/listagem da rodada recém-criada.

O caminho feliz é aritmético de propósito: SCO a R$ 50,00 e EMOP a R$ 40,00, BDI 25%,
total `900.00` sem BDI e `1125.00` com. Se qualquer linha usasse o preço da primeira fonte
da cascata em vez do da fonte citada na decisão, o total daria `1250.00` e o teste
reprovaria.

## Saída resumida de cada portão

```text
make check                                   → exit 0
  ruff check .                               → All checks passed!
  ruff format --check .                      → (sem reformatação pendente)
  mypy (strict, 5 raízes)                    → Success: no issues found in 192 source files
  scripts/check_docs.py                      → ok (valida todo link relativo de Markdown)
  croquito_core.schema_export --check-dir    → ok (sem drift de contratos)
  npm run contracts:check                    → ok
  npm run --workspace @croquito/web check    → tsc -b && vite build ok
  terraform fmt -check -recursive infra      → ok

make test                                    → exit 0
  uv run pytest                              → 1678 passed, 13 skipped (baseline: 1652 passed, 13 skipped)
  npm run web:test                           → Test Files 32 passed, Tests 581 passed (baseline idêntico)

uv run pytest tests/api/test_estimate_round_routes.py -x -q
                                             → 26 passed

uv run pytest tests/api/test_openapi_contract.py tests/api/test_migrations.py
                                             → 13 passed, 10 skipped
                                               (as 10 são `requires_postgres`)
```

Baseline registrado ANTES de qualquer edição, na mesma árvore com T1+T2:
`make check` exit 0 e `make test` com 1652 passed / 13 skipped (pytest) e 581 passed
(vitest). O delta de 26 testes é exatamente o arquivo novo; nenhum teste preexistente
mudou de resultado.

## Desvios conscientes do contrato

1. **`EstimateRoundRecord` não tem `period_number` nem `contract_label`.** O contrato pede
   "mesmos campos de identidade" da medição. Período é conceito de medição e contrato é
   conceito de obra licitada; nenhum dos dois existe antes da licitação (ADR-0027), e o
   `Estimate` não os declara. Segui o mesmo princípio que o próprio contrato aplica à
   tabela de revisões ("sem `valuation_json` nem `amendment_dossier_json` — não existem
   neste momento do domínio"). `worksite_key`, `worksite_name`, `reference_label` e
   `address` ficaram.

2. **A entrada da cascata guarda `object_sha256` além dos campos listados.** O contrato
   lista `{upload_id, object_key, source_sha256, origin, reference_month, source_label,
   summary}`. São necessários DOIS digests, e a evidência está no código: o importador
   carimba em `PriceCatalog.source_sha256` o digest do arquivo de ORIGEM (`.xlsx` do SCO,
   `.DBF` da EMOP), enquanto o que sobe pelo presign é o JSON importado. `read_catalog`
   confere os bytes lidos contra o digest do OBJETO, e a confirmação de código, a
   reordenação e `build_worksite_estimate` citam o digest da FONTE. Guardar um só faria a
   releitura recusar todo catálogo real, ou a citação nunca casar. A medição vive a mesma
   distinção — `catalog_source_sha256` na coluna (objeto) e `catalog.source_sha256` no
   domínio.

3. **A busca da cascata devolve `price_origin` + `cascade_position`, não `origin`.** O
   contrato diz "resultado carrega `origin` + posição na cascata". A chave `origin` já
   existe em `result_payload` e nomeia o BRAÇO da busca (`lexical`/`semantic`);
   sobrescrevê-la faria dois significados ocuparem a mesma chave em duas rotas do mesmo
   `/v1`. Cada resultado carrega `price_origin`, `catalog_sha256` e `cascade_position`.

4. **`GET /catalog/search` do orçamento não tem parâmetro `arm`.** O espelho da medição o
   tem, mas lá ele existe para responder `503 PROVIDER_UNAVAILABLE`: o braço híbrido
   depende de índice de embeddings publicado na rodada, e nenhuma rota de `/v1` publica
   esse índice. Expor o parâmetro só para recusá-lo acrescentaria superfície inexistente;
   o motivo do braço ausente continua viajando em `semantic_notes`.

5. **Recusa nova, fora do contrato: `409 ESTIMATE_CASCADE_LOCKED` na reordenação.**
   Achado durante a implementação. `apply_code_assignments_over_cascade` amarra o conjunto
   de decisões ao catálogo CABEÇA da cascata e recusa acumular sobre um conjunto calculado
   com outro (`_ensure_batch_decidable` → `ASSIGNMENT_CATALOG_MISMATCH`,
   `packages/valuation/src/croquito_valuation/assignment.py`). Sem esta guarda, reordenar
   depois de decidir código passaria, e a decisão SEGUINTE — não a reordenação — falharia
   com uma mensagem sobre catálogo que ninguém trocou, sem caminho de volta (não há rota
   que apague decisão). A recusa está no ato que causa o dano. Coberta por
   `test_reordenar_depois_da_decisao_de_codigo_recusa_no_ato`.

6. **Recusa nova: digest de origem repetido na cascata.** Dois catálogos de origens
   DIFERENTES importados do mesmo arquivo teriam o mesmo `source_sha256` — e é esse digest
   que a citação de código, a reordenação e a montagem usam para achar a fonte. Com dois
   candidatos, nenhuma das três distingue. Recusado na instalação, com o mesmo código
   `ESTIMATE_CASCADE_ORIGIN_DUPLICATE`.

7. **`docs/architecture/API_CONTRACT.md` foi editado, fora da lista de escopo do plano.**
   Não é ampliação de escopo: `tests/api/test_openapi_contract.py` exige paridade entre a
   superfície `/v1` exposta e o API Contract, e reprova rota exposta e não documentada. Sem
   esta edição, `make test` falharia.

8. **`services/api/src/croquito_api/valuation_rounds.py` foi editado.** O contrato pede
   reuso por import "em vez de copiar". A leitura de catálogo estava presa ao registro da
   medição, então extraí `read_catalog` de dentro de `load_catalog`, que passou a delegar.
   Nenhuma mudança de comportamento, nenhuma rota e nenhuma tabela da medição tocadas.

9. **`tests/fakes.py` e `storage.py` ganharam `write_object`.** Não havia método de escrita
   no boundary do object store; publicar a planilha exige um. O dublê ganhou a contraparte.

10. **`main.py` ganhou dois comandos de fila (`ProcessingQueue` e `PubSubProcessingQueue`).**
    `POST .../plate/extractions` está na tabela de rotas do contrato e precisa publicar
    comando. Comando PRÓPRIO, e não o da medição com outro `round_id`: os dois lados leem
    tabelas diferentes. O braço do worker fica para trabalho posterior; até lá o despacho
    trata a mensagem como não roteável, que é o desfecho seguro — e a rota já recusa antes
    disso em todo ambiente sem provider configurado.

    **A faixa ~2245-4488 de `main.py`, editada pela sessão paralela de traçado, não foi
    tocada.** Conferido por `git diff -U0`: os hunks começam nas linhas originais 37, 46,
    114, 117, 124, 863, 981, 1350, 1352 e 6290.

## Oportunidades vistas e NÃO implementadas (fora de escopo)

1. **Braço do worker para os comandos do orçamento** (`extract_estimate_plate`,
   `rerender_estimate_takeoff_overlay`): sem ele, a extração paga e o re-render do overlay
   do orçamento não têm consumidor. `services/worker` está fora do escopo de T3.
2. **Montagem da planilha fora do request path**: o desenho de fila que a medição usa para
   o overlay caberia aqui quando o orçamento real crescer.
3. **Rota de remoção de fonte da cascata**: hoje a única saída para uma fonte instalada por
   engano é abrir rodada nova. Combina com a recusa `ESTIMATE_CASCADE_LOCKED` — as duas
   pedem uma decisão de produto sobre desfazer atos da cadeia.
4. **`_commit_valuation_revision` e `_require_valuation_upload` servem as duas cadeias mas
   continuam com nome de medição**: renomeá-los é churn que atravessaria a faixa da sessão
   paralela.
5. **A lista `BASELINE` de `tests/api/test_openapi_contract.py` continua com 5 divergências
   congeladas**: são achados de F-005, com decisão humana pendente sobre qual lado corrigir.
6. **`docs/STATUS.md` não foi atualizado**: o marco só muda quando F-020 fechar, e T3 é uma
   task da feature.

## Pendência de ambiente deixada por esta execução

Ao tentar exercer o gate do ADR-0029 subi um PostgreSQL descartável:

```bash
docker run -d --rm --name croquito-f020-t3-pg \
  -e POSTGRES_DB=croquito -e POSTGRES_USER=croquito -e POSTGRES_PASSWORD=local-dev-only \
  -p 127.0.0.1:55432:5432 postgres:17-alpine
```

O contêiner subiu — a imagem foi baixada e o `run` devolveu o id —, mas o daemon do Docker
parou de responder logo em seguida: `docker ps`, `docker logs` e `docker rm -f` ficaram
pendurados, sem nenhuma saída, e foram interrompidos por timeout. A porta `55432` passou a
recusar conexão, o que sugere que o contêiner já morreu (ele foi criado com `--rm`), mas
NÃO consegui confirmar isso. Fica o registro: quando o Docker voltar, conferir e limpar.

```bash
docker rm -f croquito-f020-t3-pg
```

Nada disso toca o repositório nem os portões — é resíduo de ambiente local. A única
consequência para a entrega é o gate do ADR-0029 declarado em `Validation skipped`.
