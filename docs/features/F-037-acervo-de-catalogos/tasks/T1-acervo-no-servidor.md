# F-037 T1 — O acervo existe, administrado pela plataforma e imutável por digest

feature_id: F-037
task_id: T1
parent_plan: ../plan.md
role: builder

## Goal

A plataforma passa a guardar catálogos de preço de referência que valem para **todos** os
tenants: uma tabela publicada uma vez fica disponível para qualquer rodada de orçamento.
Publicar é ato de `platform_operator`; cada publicação é imutável e endereçada por digest.

Esta task entrega o **acervo**. Consumi-lo na cascata é a T2, e nenhuma tela é tocada aqui.

## Leia antes de editar

- [`AGENTS.md`](../../../../AGENTS.md) na raiz e `services/api/AGENTS.md`.
- [ADR-0047](../../../adr/0047-acervo-de-catalogos-da-plataforma.md) (`Accepted`) — é ele
  que autoriza a tabela sem `tenant_id`. As decisões 1, 3, 4, 6, 9 e 11 governam esta task.
- [ADR-0029](../../../adr/0029-runner-de-migrations-revisadas.md) — migrations forward-only.
- [Feature contract](../feature.md), seções `Scope` 1 e 2, e `Constraints`.

## Scope

1. **Migração `0014`**, forward-only no molde de
   `services/api/src/croquito_api/migrations/versions/0012_domain_events.py`
   (`downgrade()` levanta `NotImplementedError`). Cria `reference_catalogs`. A última
   revisão na main é `0013`.

2. **Tabela `reference_catalogs`, SEM `tenant_id`** — a primeira do projeto. A docstring do
   modelo precisa dizer **por quê**, citando a decisão 1 do ADR-0047: catálogo público não
   tem dono, e a condição que sustenta a ausência é que nada ali deriva de conteúdo de
   cliente. Colunas mínimas: identificador, nome de exibição, `origin`, `reference_month`,
   digest do objeto publicado, `source_sha256` (o do arquivo de origem, carimbado pelo
   importador — a distinção está explicada em `estimate_rounds.py:415-424`), contagem de
   entradas, chave do objeto, estado de circulação, quem publicou e quando.

3. **Objeto sob prefixo próprio, fora de `tenants/`.** Endereçado pelo digest do conteúdo,
   como `estimate_workbook_key` (`estimate_rounds.py:1004`) faz para a planilha. Uma função
   dedicada monta a chave; não interpole a string espalhada.

4. **Rotas `/v1/platform/reference-catalogs`** (nome final é seu), no molde exato de
   `PUT /v1/platform/tenants/{tenant_id}/ai-processing-entitlement` (`main.py:3722-3816`):
   `_require_platform_operator` **antes de qualquer lookup**, `Idempotency-Key`,
   `_record_audit`, `session.commit()` por último.

   - **Publicar**: recebe o `catalog.json` já normalizado (via `upload_id` presignado, como
     o catálogo da cascata) e o nome de exibição. Lê e valida com
     `PriceCatalog.model_validate_json`, como `_install_catalog` (`main.py:2576-2625`).
     `origin`, `reference_month`, `source_sha256` e contagem vêm **de dentro do arquivo** —
     nunca do corpo da requisição (decisão 7 do pacote de design: o rótulo não pode
     discordar do conteúdo).
   - **Listar**: o acervo inteiro, incluindo o que está fora de circulação, com quem
     publicou e quando.
   - **Retirar de circulação**: marca estado, **não apaga**. Rodadas antigas referenciam o
     objeto e continuam funcionando.

5. **Republicar o mesmo conteúdo não substitui** (ADR-0047 decisão 3). Digest igual ao de
   uma entrada existente recusa com código estável. Data-base nova é entrada nova.

6. **Auditoria pelo tenant do operador** (ADR-0047 decisão 11): `_record_audit`
   (`main.py:2010`) não aceita tenant nulo, e publicar não tem tenant alvo. Grave o
   `tenant_id` de quem publicou, com o identificador do catálogo nos detalhes.

7. **Snapshot de OpenAPI** regenerado por `make openapi-snapshot`.

## Out of scope

- Qualquer arquivo em `apps/web/` — as telas são T3 e T4.
- A rota de escolha e a instalação a partir do acervo — é a **T2**. Esta task não toca
  `POST /v1/estimate-rounds/{id}/catalogs` nem `ensure_source_installable`.
- **Importar `.xlsx`/`.dbf` no servidor.** ADR-0047 decisão 9: os importadores rodam só no
  CLI. O acervo recebe `catalog.json` já normalizado.
- Baixar tabelas da internet.
- Qualquer mudança na cadeia de medição.

## A guarda de prefixo — leia antes de implementar

Três lugares recusam chave fora de `tenants/{tenant_id}/` por comparação de string:
`signed_artifact_url` (`valuation_rounds.py:601-620`), `_preview_urls` (`main.py:2873`) e
`_export_response` (`main.py:2887`).

**Não os afrouxe, não os generalize e não os contorne.** O objeto do acervo fica fora de
`tenants/` e **nenhuma rota o assina** — o cliente escolhe a tabela, não a baixa (ADR-0047
decisão 6). Recusar é o comportamento correto para uma chave do acervo, e o critério 5
abaixo cobre exatamente isso.

## Acceptance criteria

1. Uma tabela publicada uma vez é legível por rodadas de **tenants diferentes** — provado
   por teste com dois tenants.
2. Publicar o mesmo conteúdo duas vezes recusa com código estável; publicar data-base
   diferente cria entrada nova, e a anterior continua existindo.
3. Retirar de circulação não apaga a linha nem o objeto; o registro continua legível.
4. Publicar, listar e retirar exigem `platform_operator`, verificado **antes** de qualquer
   lookup — quem não tem o papel recebe `403` e não descobre o que existe.
5. `signed_artifact_url` **recusa** uma chave do acervo, e nenhuma rota devolve URL assinada
   de objeto do acervo. Coberto por teste explícito.
6. **Nenhuma coluna de `reference_catalogs` deriva de conteúdo de cliente** — teste que
   verifica a condição da decisão 1 do ADR-0047. Este teste é parte da entrega, não extra.
7. `origin`, `reference_month`, `source_sha256` e contagem vêm do arquivo; um corpo que
   tente informá-los é recusado.
8. Baseline: `make check` e `make test` verdes antes e depois; goldens intocados.

## Pitfalls

- **Não replique `tenant_id` "por segurança"** na tabela nova. A ausência é a decisão, e
  replicar guardaria N cópias de um documento público.
- O snapshot de OpenAPI é ato deliberado: regenere pelo alvo do Makefile, não à mão.
- Erros de domínio são estruturados (`DomainValidationError`); não faça parsing de string de
  exceção.
- `CATALOG_MAX_BYTES` já existe e limita a leitura do catálogo — reuse, não invente outro
  limite.
- Logs nunca carregam conteúdo do catálogo, chave de objeto ou URL assinada.
- Teste de plataforma: o padrão de token está em `tests/api/test_journeys.py:89`
  (`Bearer test:{tenant}:reviewer:{roles}`) e o de recusa por papel em
  `test_administrar_jornada_exige_platform_operator` (linha 579).

## Validation

```bash
make check
make test
uv run pytest tests/api/ -q
```

## Report

Encerre com o `BUILD REPORT` completo do contrato do Builder — todos os campos presentes,
`none` onde não houver entradas. Se um portão reprovar em área que você não tocou, **pare e
reporte**; não conserte área alheia.
