# F-037 T6 — Presign próprio da plataforma, para o acervo não depender da jornada do croqui

feature_id: F-037
task_id: T6
parent_plan: ../plan.md
role: builder
depends_on: T1

## Goal

O operador da plataforma passa a subir o `catalog.json` por um presign **sob
`/v1/platform`**, sem atravessar a jornada do croqui. O acervo deixa de ficar sem como ser
alimentado num ambiente onde o croqui esteja desligado.

## O defeito que esta task fecha

Achado na revisão da T1 e **decidido por ato humano em 2026-08-22**.

O portão de disponibilidade da [F-034](../../F-034-disponibilidade-de-jornada/feature.md) é
dependência do router — entra uma vez para toda rota (`main.py:3575-3614`) — e
`/v1/uploads` cai no prefixo `croqui` (`journeys.py:57-63`). A T1 fez o operador publicar
subindo o arquivo por `POST /v1/uploads/presign`, então:

- com o croqui `disabled`, `POST /v1/uploads/presign` responde `403 JOURNEY_UNAVAILABLE`;
- com o croqui `pilot` e o tenant do operador sem entitlement, idem.

Nos dois casos o `platform_operator` não consegue publicar, e o acervo fica vazio sem que
nada indique por quê. **Não é hipótese remota**: o croqui é justamente o módulo que a F-034
nasceu para poder desligar — "hoje o Croqui", na narrativa do roadmap.

**A saída recusada, e por quê:** classificar `/v1/uploads` como sem jornada resolveria isto
enfraquecendo a F-034 — o presign do croqui é do croqui, e tirá-lo do portão para atender um
caso de plataforma trocaria um defeito por outro, maior e mais silencioso.

## Scope

1. **`POST /v1/platform/reference-catalogs/presign`** (nome final é seu), no molde exato de
   `presign_upload` (`main.py:4423-4489`): mesma sequência de idempotência, mesmo
   `UploadRecord`, mesmo cálculo de checksum, mesma diferença de header entre `s3` e `gcs`
   (linhas 4460-4462), mesma auditoria.

   Duas diferenças, e só elas:
   - **papel**: `_require_platform_operator` (`main.py:2628`) **antes de qualquer coisa**,
     no lugar do principal autenticado genérico;
   - **tipo fixo**: `application/json` (`CATALOG_CONTENT_TYPE`), não recebido do corpo. O
     acervo publica catálogo normalizado e nada mais.

2. **O `UploadRecord` continua sendo do tenant do operador**, sob
   `tenants/{tenant_id}/uploads/...`. Isto é deliberado e **não** deve mudar: a área de
   upload é do operador enquanto o arquivo ainda não foi validado; ele só vira objeto do
   acervo depois que `publish_reference_catalog` o lê, confere o digest e o grava sob o
   prefixo da plataforma. Subir direto para o prefixo do acervo colocaria no acervo um
   arquivo que ninguém validou.

3. **A rota de publicação passa a exigir um upload feito por este caminho** — ou continua
   aceitando qualquer upload JSON do tenant do operador? Decida e **escreva a razão**: a
   segunda é mais simples e não abre nada (o operador é quem sobe e quem publica, e
   `_require_valuation_upload` já filtra por tenant); a primeira é mais estrita e evita que
   um `platform_operator` publique por engano um catálogo que ele havia subido para uma
   rodada. Recomendação: manter aceitando, e registrar por quê.

4. **Documentação**: a seção "Acervo de catálogos de referência" do
   [API Contract](../../../architecture/API_CONTRACT.md) ganha a rota nova, e a descrição de
   `POST /v1/platform/reference-catalogs` deixa de mandar usar "o presign de sempre".

5. **Snapshot de OpenAPI** regenerado por `make openapi-snapshot`.

## Out of scope

- Qualquer arquivo em `apps/web/` — a tela é a T3, que passa a chamar esta rota.
- Mudar `JOURNEY_ROUTE_PREFIXES`, `JOURNEYLESS_ROUTE_PREFIXES` ou o portão de jornada.
  **Nada em `journeys.py` muda.**
- Mudar `POST /v1/uploads/presign`, que continua sendo do croqui.
- Migrar publicações já feitas.

## Acceptance criteria

1. **O teste que prova o defeito fechado**: com o croqui `disabled`, o operador publica no
   acervo do começo ao fim — presign, PUT e publicação — sem receber `JOURNEY_UNAVAILABLE`.
   `tests/api/test_journeys.py` mostra como montar o app com jornada indisponível
   (`JourneyAvailabilitySettings`, linha 581).
2. Com o croqui `disabled`, `POST /v1/uploads/presign` **continua** recusando — a F-034 não
   foi enfraquecida.
3. A rota nova exige `platform_operator` antes de qualquer lookup; quem não tem recebe
   `403` e não descobre nada.
4. Tipo diferente de `application/json` não é aceito.
5. Idempotência, auditoria e o header de checksum por perfil de storage funcionam como no
   presign de origem.
6. Baseline: `make check` e `make test` verdes antes e depois.

## Pitfalls

- Não duplique a lógica de presign copiando e colando o corpo inteiro se der para extrair o
  trecho comum; mas **não refatore `presign_upload` a ponto de mudar o comportamento dele** —
  ele serve o croqui e está no caminho quente da jornada mais usada.
- O header `x-amz-checksum-sha256` entra na assinatura só no S3; enviá-lo ao GCS faz o PUT
  falhar (comentário em `main.py:4461`).
- `_safe_filename` existe e trata nome de arquivo; reuse.
- Nenhuma URL assinada em log ou auditoria (ADR-0028 D5).

## Validation

```bash
make check
make test
uv run pytest tests/api/test_reference_catalogs.py tests/api/test_journeys.py -q
```

## Report

Encerre com o `BUILD REPORT` completo do contrato do Builder — todos os campos presentes,
`none` onde não houver entradas. Se um portão reprovar em área que você não tocou, **pare e
reporte**; não conserte área alheia.
