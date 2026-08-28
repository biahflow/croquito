# F-042 T2 — Persistência do acervo e as rotas da rodada

- **feature_id**: F-042
- **task_id**: T2
- **role**: builder
- **depends_on**: [T1]
- **required_capabilities**: READ, WRITE (`services/api`, `tests/api`, `tests/e2e`), VALIDATE
- **risk**: ALTO — `main.py` é arquivo vivo e enorme; migração nova; fronteira de tenant.
- **relative_effort**: L

## Gates já cumpridos

- **ADR-0060 `Accepted` em 2026-08-28** (Daniel Campos): o acervo tem **duas origens e um
  contrato de leitura só** — acervo de plataforma (sem `tenant_id`, publicado por
  `platform_operator`, molde da F-037) e acervo do tenant (com `tenant_id`). Promoção de
  tenant para plataforma é ato humano; **não** há seed empacotado.
- **Design Approval Package revisão 1 aprovado em 2026-08-28**. A tela é a T3; esta task
  entrega o que ela consome.

O motor já existe e está commitado nesta branch: `packages/valuation/src/croquito_valuation/site_setup.py`
(`SiteSetupKit`, `apply_site_setup_kit`, `preview_site_setup_kit`, `load_site_setup_kit`).
**Não reimplemente nada dele, e não o altere** — se precisar de algo que ele não oferece,
pare e reporte.

## Scope

### 1. Persistência

Tabela nova para o acervo, com as duas origens do ADR-0060. `tenant_id` **anulável**: nulo é
acervo de plataforma, preenchido é acervo do tenant. Documente na docstring do modelo que
essa é a codificação da decisão do ADR, e que a consulta **sempre** filtra
`tenant_id IS NULL OR tenant_id = :tenant`.

- Colunas mínimas: `id`, `tenant_id` (nullable, index), `name`, `kit_version`,
  `source_label`, `document_json` (o `SiteSetupKit` serializado), `document_sha256`,
  `withdrawn_at` (nullable, molde da retirada de circulação da F-037), `created_by`,
  `created_at`.
- Unicidade: `(tenant_id, name, kit_version)`. Publicar a mesma versão duas vezes é recusa,
  não sobrescrita — acervo é imutável, como o catálogo de referência.
- Migração Alembic nova. **Confira o número da última migração no diretório antes de
  numerar** e siga a sequência; não presuma.

### 2. Rotas

Todas em `create_app()` (`main.py`), como closures, no padrão do arquivo. `tenant_id` vem
**sempre** do JWT, nunca do body. Erros em `application/problem+json` com códigos estáveis.

**a) `POST /v1/platform/site-setup-kits`** — publica acervo de plataforma.
Exige `platform_operator` (`_require_platform_operator`, verificado **antes** de qualquer
lookup, como a F-037 faz). Body: `{name, document}` onde `document` é o `SiteSetupKit` cru.
Valide com `load_site_setup_kit`/`SiteSetupKit.model_validate` e devolva erro de domínio como
`422 DOMAIN_VALIDATION_FAILED` — nunca deixe virar erro de parsing do FastAPI (é o mesmo
desenho de `BuildEstimateRequest.calc_matrix`, `main.py:2045-2051`).

**b) `GET /v1/platform/site-setup-kits`** e **`POST /v1/platform/site-setup-kits/{id}/withdraw`**
— listar e retirar de circulação, espelhando as rotas de `reference-catalogs`.

**c) `GET /v1/estimate-rounds/{round_id}/site-setup-kits`** — o que esta rodada pode aplicar:
acervos de plataforma em circulação **mais** os do tenant. Resposta:

```json
{"round_id": "...", "version": 12,
 "kits": [{"kit_id": "...", "name": "...", "kit_version": "...", "origin": "platform",
           "source_label": "...", "parcel_count": 24,
           "parameters": [{"name": "prazo_meses", "unit": "meses", "cited_by": 6}],
           "created_at": "..."}]}
```

`parameters` sai de `SiteSetupKit.parameter_names()` mais a contagem de parcelas que citam
cada um (a tela mostra "citado por 6 parcelas"). `unit` é a unidade do **primeiro** operando
que cita o parâmetro; quando os operandos discordam da unidade, devolva `null` em vez de
escolher um — e não recuse por isso.

**d) `POST /v1/estimate-rounds/{round_id}/site-setup/preview`** — a pré-visualização.
Body: `{"kit_id": "...", "parameters": {"prazo_meses": "2"}, "excluded_parcel_ids": []}`.
**Não** avança a versão da rodada e **não** grava nada — é leitura, como o `GET` da shortlist
(ADR-0054 D7). Sem `base_version`, sem `Idempotency-Key`.

Resposta:
```json
{"round_id": "...", "version": 12, "kit_id": "...", "kit_version": "...",
 "rows": [{"parcel_id": "ss_...", "code": "AD19050500(/)", "label": "WC QUIMICO",
           "operands": [{"name": "QTD", "value": "1", "unit": null},
                        {"name": "MESES", "value": "2", "unit": "meses"}],
           "quantity": "2.00"}],
 "excluded_parcel_ids": []}
```

Decimais **sempre como string** na fronteira HTTP, como o resto da jornada faz.
`available_codes` é montado a partir do catálogo da cascata da rodada e passado a
`preview_site_setup_kit`, para que o código ausente recuse aqui e não só no apply.

**e) `POST /v1/estimate-rounds/{round_id}/site-setup/apply`** — materializa na matriz.
Body: `{"base_version": 12, "kit_id": ..., "parameters": ..., "excluded_parcel_ids": [...]}`,
aceita `Idempotency-Key`, exige `base_version` (`require_base_version`), avança a versão
(ato humano) e grava revisão nova append-only.

Semântica de merge, que é o coração desta rota:

- lê a `calc_matrix_json` da revisão corrente (pode ser `NULL` — regime legado; nesse caso a
  matriz nasce das contribuições geradas);
- **remove** as contribuições cuja `kit_origin.kit_version` seja igual à do acervo aplicado —
  são as da aplicação anterior **do mesmo acervo**;
- **preserva intactas** todas as demais: as autoradas à mão (`kit_origin` nulo) e as de
  **outros** acervos;
- insere as novas;
- grava a `CalcMatrix` resultante validada.

Isso é o que torna reaplicar idempotente (critério 4 da feature) sem apagar trabalho manual.
Escreva essa regra na docstring da rota, e teste os três casos.

**f) `POST /v1/estimate-rounds/{round_id}/site-setup/kits`** — autoria pela orçamentista.
Grava acervo **do tenant** a partir das contribuições `STANDALONE` da revisão corrente.
Body: `{"base_version": N, "name": "...", "kit_version": "...", "parameter_bindings": {...}}`,
onde `parameter_bindings` mapeia `"<contribution_index>.<operand_name>" -> "<parametro>"`,
dizendo **quais operandos viram parâmetro** — o resto vira constante.

O sistema **não** infere qual número é parâmetro (é o aviso do estado 09 do DAP). Binding que
aponte para operando inexistente é recusa nomeando o binding. Contribuição não-`STANDALONE`
nunca entra.

### 3. Testes

`tests/api/` no padrão do arquivo vizinho de rodadas de orçamento. Cobrir:

- lista da rodada traz acervo de plataforma **e** do tenant, e **nunca** o de outro tenant
  (é a fronteira do ADR-0060 — teste explícito, com dois tenants);
- acervo retirado de circulação não aparece;
- publicar exige `platform_operator`; sem o papel, recusa **antes** de qualquer lookup;
- publicar a mesma `(name, kit_version)` duas vezes é recusa;
- preview não avança versão e não grava revisão;
- preview e apply recusam parâmetro faltante nomeando todos, e código fora do catálogo da
  cascata nomeando o código, em `problem+json`;
- apply grava revisão nova, avança versão, respeita `base_version` (conflito → 409) e
  `Idempotency-Key`;
- **reaplicar o mesmo acervo não duplica**; **preserva** contribuição autorada à mão; e
  **preserva** contribuição de outro acervo;
- autoria grava só `STANDALONE`, respeita os bindings e recusa binding inválido.

## Out of Scope

- `apps/web` (é a T3, em worktree paralela).
- Alterar `site_setup.py`, `calc_matrix.py` ou qualquer coisa de `packages/valuation`.
- Promoção de acervo de tenant para plataforma (ato humano previsto no ADR-0060, sem rota
  nesta task).
- Seed/acervo real do Campo do Toca — é dado, entra por publicação.

## Acceptance Criteria

1. Um acervo de tenant nunca é visível a outro tenant, e isso está provado por teste.
2. Preview não grava nada e não avança versão.
3. As duas recusas chegam ao cliente nomeando o que falta, em `problem+json`.
4. Reaplicar o mesmo acervo com os mesmos parâmetros deixa a matriz idêntica; contribuição
   manual e de outro acervo sobrevivem.
5. A matriz gravada passa por `CalcMatrix.model_validate` — nenhuma validação de domínio é
   contornada.
6. Nenhuma chamada paga em nenhuma rota.

## Validation

```bash
cd /Users/danielcampos/workspace/daniel/croquito-f042-api
uv run pytest tests/api -q
make check
make test
```

## Armadilhas verificadas

- `tenant_id` vem do JWT (`auth.py`), nunca do body — regra do `CLAUDE.md`.
- Revisões são **append-only**: nova linha por ato, `UniqueConstraint(round_id, version)`;
  conflito de versão vira `409 REVISION_CONFLICT` (`main.py:3884-3902`).
- `EstimateRoundRecord.version` é o contador único de toda a cadeia da rodada, e **só ato
  humano o incrementa** — preview não incrementa.
- Resposta bruta de provider nunca volta ao cliente; aqui não há provider nenhum.
- Logs aceitam IDs opacos, stage, duração, status e código de erro. **Nunca** rótulo, nome de
  parâmetro com valor, ou o documento do acervo.
- `make check` valida todo link relativo de Markdown do repositório, inclusive deste arquivo.
