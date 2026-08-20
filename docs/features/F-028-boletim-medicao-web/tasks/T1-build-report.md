# T1 — BUILD REPORT

Relatório do Builder para o [Task Contract T1](T1-rotas-aprovacao-export.md) da
[F-028](../feature.md). Executado no worktree `croquito-f025`, branch `f-025-boletim-web`,
sem commit — o diff está na árvore.

## Notas de execução

**Bloqueio de ambiente (resolvido).** A primeira tentativa parou no meio: o disco chegou a
zero byte livre e nenhum comando ou escrita pôde ser executado. O estado parcial foi
reportado como `BUILD_BLOCKED`. Com o espaço liberado (~5,3 GiB), a execução foi retomada do
ponto exato onde parou, aproveitando o núcleo já escrito em `valuation_rounds.py`.

**PLAN_DEVIATION (decidida pelo orquestrador).** O Builder reportou que o teste nomeado no
Task Contract — *recalc depois de aprovar → `stale: true` e `APPROVAL_CONTENT_MISMATCH`* —
descrevia um comportamento que o código não tinha, e que torná-lo real exigiria mudar o
`POST .../calc`, listado em *Out of scope*. O orquestrador decidiu que o estado "aprovação
caduca" do Design Approval Package é **vinculante** e autorizou a mudança na rota. Registrada
no plano como `PLAN_DEVIATION`; implementada e coberta nesta mesma task. Detalhe em
[Resolução da PLAN_DEVIATION](#resolução-da-plan_deviation).

```text
BUILD REPORT

Status: BUILD_COMPLETE

Files changed:
  - services/api/src/croquito_api/valuation_rounds.py
    Núcleo da T1: aprovação nominal (`approve_valuation`, `_approval_decision_id`), estado
    de aprovação com caducidade derivada na leitura (`approval_state`), leitura tolerante
    da medição (`readable_valuation`), carry-forward da aprovação anterior
    (`carry_approval_forward`, PLAN_DEVIATION), consolidado derivado do portão
    (`bulletin_export_contract`), render+auditoria fail-closed (`render_valuation_workbook`,
    `RenderedBulletinWorkbook`), endereçamento por digest (`bulletin_workbook_key`,
    `bulletin_workbook_ref`), recusa de auditoria sem vazamento
    (`bulletin_workbook_audit_failed`) e o bloco novo em `round_state_payload`.
  - services/api/src/croquito_api/main.py
    `ApproveValuationRequest`/`ExportBulletinRequest` (corpo só com `base_version`);
    `_bulletin_payload` ganha `workbook_present`/`workbook_sha256`/`approval` e passa a
    receber a revisão; `GET .../bulletin` passa a devolver `workbook_url` montada na hora;
    `POST .../calc` passa a levar adiante a aprovação da cabeça (PLAN_DEVIATION); duas rotas
    novas: `POST .../approve` e `POST .../bulletin/export`.
  - tests/api/test_valuation_round_routes.py
    13 testes novos da F-028 (seção própria ao final) + imports.
  - tests/api/test_openapi_contract.py
    `ROTAS_DE_MEDICAO` passa de 18 para 20 rotas — ato deliberado exigido pela lista fechada.
  - tests/api/openapi.snapshot.json
    Regerado por `make openapi-snapshot`.
  - docs/architecture/API_CONTRACT.md
    As duas rotas novas, os campos novos do `GET .../bulletin` e o carry-forward do `/calc`,
    incluindo o limite declarado do consolidado derivado.

Validation executed:
  - make check ............................................. exit 0
    ruff check/format (todo o repo), mypy strict "Success: no issues found in 194 source
    files", check_docs (blocos e links relativos), schema_export --check, contracts:check,
    web:check (tsc -b && vite build, 76 módulos), terraform fmt -check.
  - make test .............................................. exit 0
    pytest: 1708 passed, 13 skipped. vitest: 39 arquivos, 693 testes.
  - uv run pytest tests/api/test_valuation_round_routes.py -x -q ... exit 0 (101 testes)
  - uv run pytest tests/api/test_openapi_contract.py -q ............ exit 0 (11 testes)
  - make openapi-snapshot .................................. exit 0 (ato deliberado)

  BASELINE (árvore limpa, antes de qualquer edição): make setup exit 0, make check exit 0,
  make test exit 0. Nenhuma reprovação preexistente; nenhuma reprovação nova.

Validation skipped: none

Unavailable capabilities: none

Assumptions:
  - O consolidado contratual não existe na cadeia de /v1. O portão é exercido com o
    consolidado DERIVADO da própria medição (`bulletin_export_contract`), decisão revisada e
    aprovada pelo orquestrador: nada é afrouxado, os códigos de contrato/saldo ficam
    declaradamente inertes, a conferência de preço fica com o auditor
    (`CATALOG_PRICE_MISMATCH`) e a aprovação continua integralmente ativa. O teste
    `test_o_consolidado_derivado_nao_dispara_codigo_de_contrato_nem_afrouxa_a_aprovacao`
    prova o par: no caminho feliz a ÚNICA violação aberta antes do ato é
    `VALUATION_NOT_APPROVED`, e com a aprovação o portão fica limpo.
  - A planilha é escrita e auditada com `contract=None`: a rodada não tem PLANILHA GERAL nem
    RE-RA a imprimir.
  - Exportar avança `version` da rodada, como o `build_estimate` da F-020 — publicar é ato
    humano deliberado.
  - `Valuation.id` é gerado a cada montagem e entra no `content_digest()`, então um recálculo
    sempre produz digest novo: a aprovação levada adiante nasce caduca em qualquer caso,
    inclusive quando nada mais mudou.

Remaining risks:
  - `bulletin_export_contract` numera as linhas do consolidado derivado com `str(index)`, e
    `ITEM_NUMBER_PATTERN` aceita no máximo 3 dígitos: uma medição com mais de 999 códigos
    distintos levantaria erro de validação na montagem do consolidado, não uma recusa de
    domínio legível. Declarado por decisão do orquestrador; não corrigido nesta task.
  - A T2 (web) depende dos campos novos do `GET .../bulletin`; o contrato entre as duas
    tasks é o bloco `approval` documentado no API_CONTRACT.md, incluindo o estado caduco
    (`stale: true` com `approved_by`/`approved_at` preenchidos).

Human decisions required:
  - Revisão linha a linha do diff, em especial `bulletin_export_contract` (ponto onde
    dinheiro e portão se encontram) e `carry_approval_forward` (a PLAN_DEVIATION).
```

## Resolução da PLAN_DEVIATION

**Decisão do orquestrador:** o estado "aprovação caduca" do mock aprovado é vinculante e
deve ser alcançável na jornada real.

**O que foi implementado:** `POST /v1/valuation-rounds/{round_id}/calc` passa a levar adiante
a aprovação da revisão-cabeça. O documento recém-montado por `build_worksite_valuation` é
regravado com o **mesmo** `approval` anterior, que continua apontando para o digest do
conteúdo antigo.

**O domínio não mudou.** `packages/valuation` está intocado: `build_worksite_valuation`
continua produzindo medição sem aprovação nenhuma, que é o certo para uma função que só sabe
calcular. Quem pode responder "houve aprovação antes?" é a rota, que tem a revisão em mãos —
e é lá que a decisão vive, em `carry_approval_forward` (`valuation_rounds.py`), com o
raciocínio escrito na docstring da função e na da rota.

**Preservar não é aprovar.** A aprovação carregada nunca autoriza o conteúdo novo: como o
digest aprovado é o antigo, ela nasce caduca por construção e o portão de exportação a recusa
com `APPROVAL_CONTENT_MISMATCH`. O que ela faz é manter visível que uma aprovação existiu, com
dono e data, e deixou de cobrir o que está na tela — que é exatamente a diferença entre
"caduca" e "nunca aprovada", e o que dá à tela a única saída correta: aprovar de novo.

## Desvios menores (aceitos pelo orquestrador)

1. **Posição das rotas no arquivo.** O contrato pedia "ao FINAL do arquivo"; foram colocadas
   logo após `GET .../bulletin`, mantendo o bloco `/v1/valuation-rounds/*` contíguo — o final
   do arquivo pertence hoje às rotas de `estimate-rounds`.
2. **Remoções no snapshot OpenAPI.** O contrato pedia "diff só de adição". O snapshot tem 188
   adições e **2 remoções**: as `description` do `GET .../bulletin` e do `POST .../calc`, que
   foram ampliadas. É troca de texto de documentação das mesmas rotas — nenhuma mudança de
   caminho, parâmetro, schema ou resposta.

## Testes novos e o que cobrem

| Teste | O que prova |
|---|---|
| `test_a_aprovacao_carimba_a_identidade_do_token_e_amarra_o_digest` | `reviewer_id` = subject do JWT; `version` avança; digest gravado == `content_digest()` |
| `test_o_corpo_da_aprovacao_recusa_qualquer_carimbo_de_identidade` | `reviewer_id` no corpo → `422`; nada gravado |
| `test_a_aprovacao_sem_boletim_construido_e_etapa_fora_de_ordem` | `409 ROUND_STAGE_NOT_READY` |
| `test_a_exportacao_sem_aprovacao_e_recusada_pelo_portao_do_dominio` | `422` + `VALUATION_EXPORT_BLOCKED` + `VALUATION_NOT_APPROVED`; nada publicado |
| `test_o_consolidado_derivado_nao_dispara_codigo_de_contrato_nem_afrouxa_a_aprovacao` | O par que caracteriza a decisão do consolidado derivado |
| `test_o_recalculo_faz_a_aprovacao_caducar_e_a_exportacao_recusa` | **Teste nomeado no contrato**, agora pelo caminho real: `stale: true`, dono e data preservados, os dois digests divergentes, exportação recusada com `APPROVAL_CONTENT_MISMATCH` |
| `test_depois_de_recalcular_exportar_exige_um_ato_novo_de_aprovacao` | Invariante que vale em qualquer desenho: assinatura velha não autoriza conteúdo novo, e aprovar de novo destrava |
| `test_a_aprovacao_caduca_quando_o_conteudo_muda_sob_ela` | Cobertura extra: o portão não depende de como a divergência apareceu (artefato adulterado, fora de qualquer rota) |
| `test_a_exportacao_publica_por_digest_e_a_url_sai_so_na_leitura` | Chave por digest; refs/digests gravados; `workbook_url` só no GET |
| `test_auditoria_divergente_do_boletim_nao_publica_nada` | `500`, só `finding_codes`, nenhum objeto novo, `version` intacta |
| `test_a_exportacao_registra_auditoria_sem_url_assinada_nem_conteudo` | `VALUATION_APPROVED`/`BULLETIN_EXPORTED` sem URL nem valor medido |
| `test_papel_idempotencia_e_concorrencia_valem_nas_duas_rotas_novas` | `403`/`400`/`409 REVISION_CONFLICT` nas DUAS rotas |
| `test_idempotencia_das_rotas_novas_devolve_a_mesma_resposta` | Mesma chave → mesma resposta, sem revisão nova |

## Oportunidades vistas e NÃO implementadas (fora de escopo)

- **Importar consolidado contratual para `/v1`** — destravaria os códigos de saldo e contrato
  do portão, que hoje não têm fato que os alimente. Marco próprio, com rota, coluna e ADR.
- **Recusa nominal da medição** (`action="reject"`) — o domínio a aceita, o produto não a
  desenha; `APPROVAL_ACTION` registra a decisão de não escrevê-la "reservada".
- **Item number acima de 999 no consolidado derivado** — risco declarado acima, mantido por
  decisão do orquestrador.
