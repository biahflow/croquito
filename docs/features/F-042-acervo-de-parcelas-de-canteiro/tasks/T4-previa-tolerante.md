# F-042 T4 — A pré-visualização mostra o que está bloqueado, em vez de recusar

- **feature_id**: F-042
- **task_id**: T4
- **role**: builder
- **depends_on**: [T1, T2]
- **required_capabilities**: READ, WRITE (`packages/valuation`, `services/api`, `tests/`), VALIDATE
- **risk**: MÉDIO — muda comportamento já construído e testado; a falha fechada do apply não pode ser tocada.
- **relative_effort**: M

## O defeito que esta task corrige

O Design Approval Package aprovado promete, na recusa de parâmetro faltante: *"Declare os
dois, **ou remova na pré-visualização** as parcelas que os citam."*

Essa saída **não existe**. A pré-visualização recusa fechado quando falta parâmetro, então
não há pré-visualização de onde remover. Se um acervo de 24 parcelas cita um parâmetro que
apenas 2 delas usam, e a orçamentista não tem esse parâmetro, **não há caminho** para aplicar
as outras 22.

O mesmo beco existe para o código ausente do catálogo: a saída é remover a parcela, e a
recusa impede chegar à lista.

**Decisão do dono, 2026-08-28**: a pré-visualização deixa de recusar e passa a **mostrar todas
as parcelas, marcando as bloqueadas**. Pré-visualização é leitura e não materializa nada; a
falha fechada continua **inteira** no apply.

## Scope

### 1. Domínio (`packages/valuation/src/croquito_valuation/site_setup.py`)

`SiteSetupPreviewRow` passa a distinguir a linha calculável da bloqueada:

- `quantity: Decimal | None` — `None` quando a linha não pôde ser calculada;
- `missing_parameters: tuple[str, ...]` — os parâmetros que **esta** parcela cita e que não
  foram declarados, em ordem estável;
- `code_absent: bool` — o código desta parcela não está em `available_codes`;
- os operandos continuam saindo, com o valor resolvido quando há, e identificando o parâmetro
  quando falta. Escolha a forma (por exemplo, `value: Decimal | None` mais `parameter: str | None`
  numa linha de operando própria da pré-visualização) e documente o motivo — não reaproveite
  `CalcOperand` se isso obrigar a inventar um valor que ninguém declarou.

`preview_site_setup_kit` **não levanta mais** `SITE_SETUP_PARAMETER_MISSING` nem
`SITE_SETUP_CODE_ABSENT`. Ela continua levantando `SITE_SETUP_UNKNOWN_PARCEL` (erro de quem
chama, não estado do trabalho).

**`apply_site_setup_kit` fica exatamente como está.** Falha fechada total, nomeando todos os
faltantes, nada materializado parcialmente. Se você se pegar afrouxando o apply, parou no
lugar errado — a assimetria entre as duas funções **é** a feature.

Escreva essa assimetria na docstring do módulo, com o motivo: prever não é aplicar.

### 2. API (`services/api/src/croquito_api/`)

**`POST /v1/estimate-rounds/{id}/site-setup/preview`** deixa de recusar por parâmetro
faltante e por código ausente. Resposta:

```json
{"round_id": "...", "version": 12, "kit_id": "...", "kit_version": "...",
 "rows": [{"parcel_id": "ss_...", "code": "AD19050500(/)", "label": "WC QUIMICO",
           "operands": [{"name": "QTD", "value": "1", "unit": null, "parameter": null},
                        {"name": "MESES", "value": null, "unit": "meses", "parameter": "prazo_meses"}],
           "quantity": null,
           "missing_parameters": ["prazo_meses"],
           "code_absent": false}],
 "excluded_parcel_ids": [],
 "blocked_parcel_ids": ["ss_..."]}
```

`blocked_parcel_ids` é a lista das parcelas **não excluídas** que não podem nascer — é o que a
tela usa para dizer o que falta sem recalcular a regra. Parcela excluída **nunca** entra em
`blocked_parcel_ids`, mesmo bloqueada: ela não vai nascer de qualquer jeito.

**`POST .../site-setup/apply` continua recusando fechado**, com as mesmas mensagens e códigos.
Nenhum teste de recusa do apply pode ser afrouxado.

### 3. Rota nova: a matriz gravada, para a tela poder hidratar

**`GET /v1/estimate-rounds/{round_id}/calc-matrix`** — leitura pura, não avança versão, não
grava:

```json
{"round_id": "...", "version": 12, "calc_matrix": {...} | null}
```

`null` é o regime legado (revisão sem matriz). O documento sai **como está gravado**,
revalidado por `CalcMatrix.model_validate` na leitura, no mesmo desenho de `load_kit`
(`site_setup_kits.py`) — o artefato passa pelo validador de novo toda vez que sai do banco.

Isso existe porque hoje a matriz **não sai em resposta nenhuma**: a tela monta o rascunho, o
manda no build, e depois de um recarregamento ela não tem como saber o que já está gravado —
o que faz montar o orçamento apagar do banco o que o acervo aplicou. A T5 consome esta rota.

Papel: o mesmo da leitura da etapa de códigos.

### 4. Testes

- pré-visualização com parâmetro faltante devolve **todas** as linhas, marca as bloqueadas,
  e as não bloqueadas trazem quantidade calculada;
- pré-visualização com código fora do catálogo marca `code_absent` e **não** recusa;
- parcela excluída e bloqueada **não** entra em `blocked_parcel_ids`;
- o **apply** com o mesmo estado continua recusando, nomeando todos os faltantes, sem gravar
  nada — a assimetria provada por teste, lado a lado;
- `GET .../calc-matrix` devolve a matriz gravada, devolve `null` no regime legado, não avança
  versão, e não é visível a outro tenant;
- os testes existentes de `apply` continuam passando **sem edição**.

## Out of Scope

- `apps/web` (é a T5, em worktree paralela).
- Mudar o merge do apply, a fronteira de tenant ou qualquer coisa da T2 além da rota de
  preview.
- Rota de escrita nova.

## Acceptance Criteria

1. A pré-visualização nunca recusa por parâmetro faltante ou código ausente; ela marca.
2. O apply recusa fechado exatamente como antes, com os mesmos códigos.
3. `blocked_parcel_ids` ignora as parcelas excluídas.
4. `GET .../calc-matrix` devolve o que está gravado, revalidado, sem efeito colateral.
5. Nenhum teste existente editado. Se precisar, PARE e reporte.

## Validation

```bash
cd /Users/danielcampos/workspace/daniel/croquito-int-api
uv run pytest tests/valuation/test_site_setup.py tests/api/test_site_setup_kits.py -q
make check
make test
```

## Armadilhas verificadas

- `preview_site_setup_kit` e `apply_site_setup_kit` hoje **compartilham** a validação por
  `_resolve_selected_parcels`. Separá-las é o cerne desta task, e a parte comum que sobrar não
  pode reintroduzir a recusa no caminho da prévia.
- Decimais atravessam a fronteira HTTP **como string**; `quantity` ausente é `null`, nunca
  `"0"` — zero é um valor, ausência não.
- `make check` roda o gate de paridade do OpenAPI: rota nova exige `docs/architecture/API_CONTRACT.md`
  atualizado e `make openapi-snapshot`.
