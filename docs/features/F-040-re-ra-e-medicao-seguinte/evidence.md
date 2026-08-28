# F-040 — Evidência

Feature: [RE-RA declarada e a medição seguinte](feature.md)  
Estado: `DONE` — evidência de navegador capturada; nenhum critério de aceite em aberto  
Data: 2026-08-27 (evidência de navegador em 2026-08-28)

## Gates humanos

| Gate | Estado |
| --- | --- |
| `ARCHITECTURE_DECISION_REQUIRED` | ✅ [ADR-0056](../../adr/0056-re-ra-declarada-e-o-consolidado-da-medicao-seguinte.md) **aceito por ato humano em 2026-08-27** (Daniel Campos) |
| `DESIGN_APPROVAL_REQUIRED` | ✅ **Aprovado por ato humano em 2026-08-27** (Daniel Campos), revisão 1 ([mock/README.md](mock/README.md)) |
| `browser-runtime-validation` (`BROWSER_REQUIRED`) | ✅ **capturada em 2026-08-28** contra o stack local — ver "Evidência de navegador" abaixo |

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
| 11 | Evidência renderizada da tela real (`BROWSER_REQUIRED`) | ✅ quatro estados capturados da tela real contra o stack local em 2026-08-28 — ver abaixo |

## Evidência de navegador

Classificação: `BROWSER_REQUIRED` (a F-040 é `INTERFACE_CHANGE`).

Capturada em **2026-08-28** contra o stack local (`make dev-services` + `make db-init` +
`make dev`), com sessão OIDC real no Keycloak local (`orcamentista.local`, tenant
`tenant-local`) e navegação determinística em Chromium — nenhuma tela é mock, e nenhum passo
da captura dependeu de modelo. O dado é **sintético**: os códigos, quantidades e preços são os
do pacote de design aprovado (`PJ14100500(/)` a 62,40, `PJ14150203(A)` a 148,20, 783,86 m²
contratados em cada; item novo `PJ25400100(B)`), semeados como orçamento assinado sintético e
como medição do período 1 aprovada. Nenhum documento de cliente entrou no ambiente.

| Arquivo | Estado | O que a imagem prova |
| --- | --- | --- |
| [`evidencia/01-declarar-re-ra.png`](evidencia/01-declarar-re-ra.png) | A declaração da RE-RA na abertura | A abertura a partir do orçamento assinado aceita a declaração com nome curto (`1ª RE-RA`), citação da publicação (`Processo 123/2026 · DO de 14/08/2026`) e o efeito **com sinal** código a código (`+120.00`, `-83.86`, `+45.00`), com o terceiro marcado como **item novo** — e não existe campo onde escrever a quantidade vigente. |
| [`evidencia/02-memoria-contratado-vigente.png`](evidencia/02-memoria-contratado-vigente.png) | A memória: contratado → vigente → saldo | A rodada nasceu já re-ratificada, com o selo **re-ratificada** por escrito, a declaração carimbada com autor e citação, e a conta visível: 783,86 → **903,86**, 783,86 → **700,00**, e o item novo 0,00 → **45,00** materializado do catálogo contratual. O contratado não se moveu. |
| [`evidencia/03-porta-medicao-seguinte.png`](evidencia/03-porta-medicao-seguinte.png) | A porta da medição seguinte | A rodada do período 1 **aprovada** aparece na lista com o selo `aprovada` e com o botão **“Abrir a medição 2”** ao lado de “Abrir rodada” — o período é calculado da rodada anterior, não digitado. Rodada não aprovada não recebe o botão. |
| [`evidencia/04-sem-re-ra.png`](evidencia/04-sem-re-ra.png) | O controle: rodada sem RE-RA | A mesma abertura, sem declaração nenhuma, no mesmo lugar da tela: o contratado vem do orçamento assinado (2 códigos, sem o item novo) e **nenhum segundo número de quantidade aparece** — sem RE-RA, o vigente É o contratado, e a tela não fala de re-ratificação. |

As imagens são frozen evidence da revisão sob revisão: elas mostram a `main` com os PRs #109,
#112 e #113 já integrados.

## Desvios declarados

1. **O controle não imprime duas colunas iguais.** A decisão 4 do pacote de design pede que,
   sem RE-RA, contratado e vigente repitam o mesmo número de propósito. O implementado espelha
   `ReajusteDeclarado`: sem declaração, o bloco inteiro não aparece
   (`apps/web/src/medicao/MedicaoApp.tsx`, `ReRatificacaoDeclarada`). A ausência de RE-RA já é
   **declarada** na resposta da rodada (`amendments: []`), e repetir o mesmo número em duas
   colunas numa tela onde não há diferença alguma a mostrar seria ruído. **É desvio de decisão
   aprovada** e fica registrado como tal: se a coluna repetida for desejada, é mudança pequena
   e o pacote vira revisão 2.
2. **A prévia antes de gravar (estado 04 do pacote) não foi entregue nesta feature** e,
   portanto, não é capturada aqui: a T5 entregou a declaração, a memória e a porta da medição
   seguinte. O efeito código a código aparece **depois** de gravar, na memória (imagem 02).
3. **A declaração é carimbada com o `sub` do principal**, não com um nome legível — é o que a
   API grava em `declared_by` (identidade do servidor, nunca do corpo). Na imagem 02 isso
   aparece como o UUID do usuário sintético local. Copy e apresentação da autoria não estavam
   cobertas pela aprovação do pacote.

## Riscos remanescentes

- Nenhuma medição real com contrato re-ratificado foi feita: o primeiro uso é o teste de
  verdade, e é o aceite que a [issue #100](https://github.com/biahflow/croquito/issues/100)
  registra.
- A RE-RA continua **digitada**: o sistema não confere o teor da publicação. A mitigação
  implementada é exigir a citação junto do efeito, e carimbar autor e instante.
- RE-RA retroativa que reescreva período já lançado permanece fora, por decisão do ADR-0055
  (decisão 6).

## Decisões humanas pendentes

- Aceite numa medição real com contrato re-ratificado (o aceite de código da issue #100
  ocorreu em 2026-08-28).
- Decidir se o controle sem RE-RA deve imprimir contratado e vigente repetidos (desvio 1).
