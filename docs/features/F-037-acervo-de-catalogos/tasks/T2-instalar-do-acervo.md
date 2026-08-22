# F-037 T2 — Instalar na cascata a partir do acervo, com a procedência registrada

feature_id: F-037
task_id: T2
parent_plan: ../plan.md
role: builder
depends_on: T1

## Goal

A rodada de orçamento passa a poder instalar na cascata uma tabela **do acervo**, sem
upload. O caminho do arquivo próprio continua idêntico, e a cascata registra de qual dos
dois a fonte veio.

## Leia antes de editar

- [`AGENTS.md`](../../../../AGENTS.md) na raiz e `services/api/AGENTS.md`.
- [ADR-0047](../../../adr/0047-acervo-de-catalogos-da-plataforma.md), decisões 6 e 7.
- [ADR-0045](../../../adr/0045-terceiro-estado-demanda-sob-contrato.md) — o regime que
  filtra a lista.
- O `plan.md`, seção `planning_findings` — a recomendação sobre onde a listagem vive.

## Scope

1. **Listagem do que está disponível para a rodada.** Recomendação forte do planejamento:
   **sob a rodada**, não global. A rodada conhece o regime e filtra; uma rota global
   obrigaria a tela a reimplementar a regra, que é exatamente o que a F-033 evitou ao
   publicar `allowed_cascade_origins` do servidor (`estimate_rounds.py:111`,
   `REGIME_ALLOWED_ORIGINS`). Papel: o do orçamento (`_require_valuation_reviewer`,
   `main.py:2190`), antes de qualquer lookup.

   Só entra o que está **em circulação**, e sob regime de contrato só o que o regime
   aceita.

2. **`POST /v1/estimate-rounds/{round_id}/catalogs` aceita duas formas de entrada**, nunca
   as duas juntas: `upload_id` (o caminho de hoje, `InstallEstimateCatalogRequest`) **ou** a
   referência ao catálogo do acervo. Corpo com as duas recusa `422` com código estável.

   `_install_catalog` (`main.py:2576-2625`) hoje recebe um `UploadRecord` e está acoplado a
   ele. Refatore para que o caminho comum receba **objeto + digest esperado**, e cada uma
   das duas formas resolva isso à sua maneira: o upload continua passando por
   `_require_valuation_upload` (`main.py:2524-2573`, que filtra por tenant); o acervo
   resolve pela linha de `reference_catalogs`. **O tenant continua sendo filtro do upload** —
   não afrouxe isso.

3. **Procedência na `CascadeEntry`** (`estimate_rounds.py:402-428`): campo novo declarando
   se a fonte veio do acervo ou é tabela própria. `CascadeEntry.payload()` (linhas 430-443)
   passa a expô-lo — ele omite `object_key` e `upload_id` de propósito, e a procedência
   **não** é nenhum dos dois: é o fato de quem publicou o arquivo.

   Cascata instalada **antes** desta feature não tem o campo. Ausência lê como tabela
   própria, que é o que ela é — e nada é reescrito retroativamente.

4. **Todas as regras existentes continuam valendo, sem exceção**:
   `ESTIMATE_CASCADE_ORIGIN_DUPLICATE`, `ESTIMATE_CASCADE_ORIGIN_FORBIDDEN` (regime),
   `ESTIMATE_CASCADE_LOCKED` (trava por decisão de código) e a recusa de `source_sha256`
   duplicado entre origens (`ensure_source_installable`, `estimate_rounds.py:524-556`). Elas
   valem igual para o acervo — a origem é a mesma coisa, mude só de onde o arquivo veio.

5. **Snapshot de OpenAPI** regenerado por `make openapi-snapshot`.

## Out of scope

- Qualquer arquivo em `apps/web/` — são T3 e T4.
- As rotas de administração do acervo — são da T1, já entregues.
- Mudar `signed_artifact_url`, `_preview_urls` ou `_export_response`. O objeto do acervo é
  lido pelo servidor, nunca assinado para o cliente.
- Migrar cascatas já instaladas para o acervo.

## `source_sha256` × `object_sha256` — leia antes de implementar

A distinção está documentada em `estimate_rounds.py:411-424` e **importa aqui**:

- `object_sha256` — digest dos **bytes do JSON** gravado no store; é o que a releitura tem
  de reproduzir.
- `source_sha256` — digest do **arquivo de origem** (o `.xlsx` do SCO, o `.DBF` da EMOP),
  carimbado pelo importador em `PriceCatalog.source_sha256` (`models.py:154`). É a
  identidade do catálogo como o **domínio** a conhece: é ele que a confirmação de código
  cita, que a linha do orçamento carrega e que a reordenação recebe.

Um catálogo instalado do acervo tem os dois, exatamente como um instalado por upload. A
linha do orçamento não muda de forma por causa da procedência — critério 3 abaixo.

## Acceptance criteria

1. Instalar do acervo produz `CascadeEntry` com os mesmos campos de sempre, mais a
   procedência; instalar por upload continua idêntico ao de hoje.
2. Corpo com `upload_id` **e** referência do acervo recusa `422` com código estável, sem
   gravar nada.
3. Um orçamento montado sobre catálogo do acervo é **logicamente idêntico** ao montado
   sobre o mesmo catálogo por upload — mesma proveniência por linha, mesmo `source_sha256`.
   Este é o critério que prova que a procedência é metadado, não regra nova.
4. Sob regime de contrato, a listagem só oferece origem que o regime aceita; instalar o que
   ele não aceita continua recusando com `ESTIMATE_CASCADE_ORIGIN_FORBIDDEN`.
5. Catálogo fora de circulação não aparece na listagem e não instala.
6. Origem duplicada, cascata travada e `source_sha256` duplicado recusam igual, venha a
   fonte de onde vier.
7. Cascata instalada antes desta feature continua legível; ausência de procedência lê como
   tabela própria.
8. Papel do orçamento exigido antes de qualquer lookup na rota nova.
9. Baseline: `make check` e `make test` verdes antes e depois; goldens intocados.

## Pitfalls

- **Não afrouxe o filtro por tenant do upload.** `_require_valuation_upload` filtra por
  `tenant_id`; o acervo é a exceção autorizada, o upload não.
- O snapshot de OpenAPI é ato deliberado: regenere pelo alvo do Makefile.
- `CatalogCache` (`valuation_rounds.py:623`) é por digest e cross-tenant de propósito —
  catálogo do acervo cai nele naturalmente. Não crie cache paralelo.
- Erros de domínio são estruturados; não faça parsing de string de exceção.
- Testes: reuse `_create_round(**overrides)`, `_install_catalog(origin=...)` e
  `_round_with_cascade_and_takeoff` de `tests/api/test_estimate_round_routes.py`.

## Validation

```bash
make check
make test
uv run pytest tests/api/test_estimate_round_routes.py -q
```

## Report

Encerre com o `BUILD REPORT` completo do contrato do Builder — todos os campos presentes,
`none` onde não houver entradas. Se um portão reprovar em área que você não tocou, **pare e
reporte**; não conserte área alheia.
