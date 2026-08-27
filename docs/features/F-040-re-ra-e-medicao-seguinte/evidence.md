# F-040 — Evidência

Feature: [RE-RA declarada e a medição seguinte](feature.md)  
Estado: `IN_PROGRESS` (evidência de navegador em captura)  
Data: 2026-08-27

## Gates humanos

| Gate | Estado |
| --- | --- |
| `ARCHITECTURE_DECISION_REQUIRED` | ✅ [ADR-0056](../../adr/0056-re-ra-declarada-e-o-consolidado-da-medicao-seguinte.md) **aceito por ato humano em 2026-08-27** (Daniel Campos) |
| `DESIGN_APPROVAL_REQUIRED` | ✅ **Aprovado por ato humano em 2026-08-27** (Daniel Campos), revisão 1 ([mock/README.md](mock/README.md)) |
| `browser-runtime-validation` (`BROWSER_REQUIRED`) | 🟡 em captura — ver "Evidência de navegador" abaixo |

Antes dos dois gates, três **decisões de domínio** foram tomadas por ato humano na abertura:
a RE-RA aprovada (não o pedido com estado), o vigente derivado como o preço, e a abertura da
medição seguinte no escopo.

## O que foi entregue

| Arquivo | O que é |
| --- | --- |
| `packages/valuation/.../contract.py` | `Amendment` com procedência e `ensure_declared`; `AmendmentLine` com item novo materializado; `current_quantity`/`current_balance_quantity` derivados; `amended_quantity`/`balance_quantity` opcionais; `apply_declared_amendment`; `build_next_round_contract`; `schema_version` `4.0.0` |
| `packages/valuation/.../models.py` | `BALANCE_EXCEEDED` passa a comparar com o saldo vigente derivado |
| `packages/valuation/.../workbook_writer.py`, `contract_from_estimate.py` | memória e abertura sobre o vigente derivado |
| `tests/valuation/test_amendment.py` (11) e `test_next_round.py` (4) | procedência, guard, item novo, `apply_declared_amendment`, compat de schema, a medição seguinte |
| `services/api/.../main.py` | `AmendmentRequest`, `_amendment_from_request` (materialização do item novo do catálogo), a origem `previous_round_id` (`_origin_from_previous_round`), e `approved`/`can_open_next` no resumo da rodada |
| `services/api/.../valuation_rounds.py` | `amendments` e `quantities` na leitura da rodada |
| `tests/api/test_valuation_round_from_estimate.py` | declaração de RE-RA, item novo materializado, recusas, a medição seguinte e a marcação de rodada apta |
| `apps/web/src/medicao/reratificacao.ts` (+ testes) | a recusa da forma antes da rede |
| `apps/web/src/medicao/requests.ts`, `api.ts` | `amendmentBody`, a origem `previous_round_id`, e os tipos do read-model |
| `apps/web/src/medicao/MedicaoApp.tsx` | `ReRatificacaoDeclarada` (a conta na memória), `ReRatificacaoFieldset` (a declaração na abertura) e a porta da medição seguinte na lista de rodadas |

## Critérios de aceite

| # | Critério | Como foi verificado |
| --- | --- | --- |
| 1 | `Amendment` recusa declaração sem autor, instante com fuso ou período | `test_amendment.py`: `AMENDMENT_PROVENANCE_MISSING`, `AMENDMENT_TIMESTAMP_NAIVE` |
| 2 | `current_quantity` = contratado + Σ deltas; sem RE-RA, contratado bit a bit | `test_contract_models.py`, `test_amendment.py` |
| 3 | Consolidado `2.0.0`/`3.0.0` continua validando com o vigente que trazia | `test_amendment.py::test_consolidado_gravado_antes_da_feature_continua_validando` |
| 4 | Item novo cria a linha materializada; ausente do catálogo recusa | `test_amendment.py`, `test_valuation_round_from_estimate.py` (`AMENDMENT_NEW_ITEM_CODE_MISSING`) |
| 5 | `amended_quantity` presente e divergente recusa | `AMENDMENT_APPLICATION_MISMATCH` preservado (`test_contract_models.py`) |
| 6 | Declarar RE-RA na abertura grava o consolidado já re-ratificado, imutável | `test_valuation_round_from_estimate.py::test_a_rodada_nasce_re_ratificada...` |
| 7 | Rodada `n+1` soma os períodos, acumulado e saldo `vigente − acumulado` | `test_next_round.py`, `test_valuation_round_from_estimate.py::test_a_medicao_seguinte_nasce...` |
| 8 | Medir acima do vigente novo recusa `BALANCE_EXCEEDED`; abaixo, exporta | `models.py` sobre o saldo derivado; suíte de export |
| 9 | Nenhum digest assinado se move | `Estimate` inalterado; consolidado por parâmetro; snapshot OpenAPI aditivo |
| 10 | `make check` e `make test` verdes | `make check` = 0 (ruff, mypy strict, check_docs, drift, build web; `infra-check` exige terraform ausente no ambiente); `make test` = 0 |
| 11 | Evidência renderizada da tela real (`BROWSER_REQUIRED`) | **Em captura** — ver abaixo |

## Evidência de navegador

Classificação: `BROWSER_REQUIRED` (a F-040 é `INTERFACE_CHANGE`).

Estados a exercer, do pacote de design aprovado:

| Arquivo | Estado |
| --- | --- |
| `evidencia/01-declarar-re-ra.png` | A declaração da RE-RA na abertura (nome, processo, deltas, item novo) |
| `evidencia/02-memoria-contratado-vigente.png` | A memória: contratado → vigente → saldo, com o selo "re-ratificada" |
| `evidencia/03-porta-medicao-seguinte.png` | A rodada aprovada com o selo e o botão "Abrir a medição seguinte" |
| `evidencia/04-sem-re-ra.png` | O controle: rodada sem RE-RA, contratado e vigente iguais |

> Captura contra o stack local (`make dev-services` + `make db-init` + `make dev`), com uma
> rodada aberta a partir de um orçamento assinado sintético. As imagens são frozen evidence da
> revisão sob revisão.
