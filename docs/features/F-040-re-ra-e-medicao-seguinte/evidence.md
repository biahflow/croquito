# F-040 — Evidência

Feature: [RE-RA declarada e a medição seguinte](feature.md)  
Estado: `IN_PROGRESS` — a T6 fechou três desvios do pacote de design que a captura expôs e a
T7 devolveu a conta da prévia ao servidor; pende a **recaptura** dos estados novos
(`BROWSER_REQUIRED`)  
Data: 2026-08-27 (evidência de navegador em 2026-08-28; correção do registro, T6 e T7 em
2026-08-28)

> **Correção do registro.** Este documento afirmou, em 2026-08-28, que a feature estava
> completa e que "nenhum critério de aceite" continuava em aberto. Era falso. A própria captura
> de navegador que ele registra expôs que **três decisões do
> [Design Approval Package](mock/README.md) aprovado** não estavam no código — as decisões 1, 4
> e 6 —, e o documento chamou de "desvio declarado" apenas uma delas. A
> [T6](tasks/T6-a-porta-da-medicao-seguinte.md) fecha as três. Pacote aprovado é contrato da
> superfície: uma feature com decisão aprovada e não construída não está `DONE`.

## Gates humanos

| Gate | Estado |
| --- | --- |
| `ARCHITECTURE_DECISION_REQUIRED` | ✅ [ADR-0056](../../adr/0056-re-ra-declarada-e-o-consolidado-da-medicao-seguinte.md) **aceito por ato humano em 2026-08-27** (Daniel Campos) |
| `DESIGN_APPROVAL_REQUIRED` | ✅ **Aprovado por ato humano em 2026-08-27** (Daniel Campos), revisão 1 ([mock/README.md](mock/README.md)) |
| `browser-runtime-validation` (`BROWSER_REQUIRED`) | ⚠️ **parcial** — quatro estados capturados em 2026-08-28 contra o stack local, mas a **recaptura dos estados que a T6 acrescentou** (a porta, a herança e a prévia) está pendente |

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

### T6 — o que a captura mostrou que faltava

| Arquivo | O que é |
| --- | --- |
| `apps/web/src/medicao/previa.ts` (+ `previa.test.ts`) | Aritmética exata em texto (`BigInt`, semântica de `Decimal`), a herança da rodada anterior, a prévia da RE-RA e os códigos a resolver no catálogo |
| `apps/web/src/medicao/MedicaoApp.tsx` | A origem da rodada vira escolha de **três** portas; “Abrir a medição n+1” leva à abertura em vez de criar a rodada; `HerancaDaRodadaAnterior` e `PreviaDaReRa`; a RE-RA declarável nas duas portas contratadas |
| `apps/web/src/medicao/styles.css` | Sem cor nova: reaproveita a tabela e o selo petróleo da RE-RA |
| `apps/web/src/medicao/requests.test.ts` | A RE-RA viajando junto de `previous_round_id` |
| `tests/api/test_valuation_round_from_estimate.py` | `test_a_medicao_seguinte_nasce_re_ratificada`: fixa o comportamento **já existente** do servidor e serve de oráculo aos números da prévia |

### T7 — a prévia deixa o cliente e vira rota

| Arquivo | O que é |
| --- | --- |
| `services/api/.../main.py` | `POST /v1/valuation-round-previews` (somente leitura), `ValuationRoundPreviewRequest/Line/Response`, e a extração de `_contracted_valuation_origin` + `_apply_declared_acts` de dentro de `_resolve_valuation_origin` — as duas funções que a criação e a prévia passam a compartilhar |
| `tests/api/test_valuation_round_preview.py` (13) | O par prévia × rodada criada, a ausência de escrita, o medido do período, o item novo materializado e as recusas idênticas às da criação |
| `docs/architecture/API_CONTRACT.md`, `tests/api/openapi.snapshot.json` | A rota documentada e o snapshot regenerado (**aditivo**: 270 linhas inseridas, nenhuma removida) |
| `apps/web/src/medicao/api.ts`, `requests.ts` (+ testes) | `previewRound` e `roundPreviewBody`: `POST` de leitura, sem `Idempotency-Key` e sem `base_version` |
| `apps/web/src/medicao/previa.ts` (+ `previa.test.ts`) | **Perde a aritmética.** Sobra o que perguntar (`pedidoDaPrevia`), o estado da projeção (`EstadoDaPrevia`), o que é declaração (`linhasDeclaradas`) e a pontuação do sinal (`efeitoEmPtBr`) |
| `apps/web/src/medicao/MedicaoApp.tsx` (+ testes) | Os dois componentes passam a exibir a resposta do servidor, com debounce, cancelamento da projeção anterior e os estados “projetando” e “não consegui projetar” |

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
| 11 | Evidência renderizada da tela real (`BROWSER_REQUIRED`) | ⚠️ quatro estados capturados da tela real contra o stack local em 2026-08-28 — ver abaixo; a **recaptura** dos estados da T6 está pendente |
| 12 | A medição seguinte passa pela abertura, com herança e prévia antes de gravar (T6) | `previa.test.ts`, `MedicaoApp.test.tsx` (`HerancaDaRodadaAnterior`, `PreviaDaReRa`), `requests.test.ts` |
| 13 | A prévia é calculada pelo **servidor**, pelo mesmo caminho da criação (T7) | `test_valuation_round_preview.py::test_a_previa_devolve_os_mesmos_numeros_da_rodada_criada` (mesmo corpo às duas rotas) e `::test_a_previa_nao_grava_nada`; `grep -rn "BigInt\|reduce(" apps/web/src/medicao/previa.ts` não devolve aritmética |

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

## Os três desvios do pacote aprovado, e como a T6 os fecha

A captura de navegador de 2026-08-28 expôs que **três decisões do
[Design Approval Package](mock/README.md) revisão 1**, aprovado por ato humano em 2026-08-27,
não estavam no código. O registro anterior nomeava só uma delas.

| # | Decisão aprovada | O que a T5 deixou | O que a T6 entrega |
| --- | --- | --- | --- |
| 1 | Decisão 1 — a medição seguinte é uma das **duas portas da abertura**, não uma tela separada | um botão na lista de rodadas que criava a rodada **na hora**, com o formulário vazio | o botão leva à abertura com origem, período e `previous_round_id` resolvidos; nenhuma rodada é criada antes do submit |
| 2 | Decisão 4 — a **herança é mostrada antes de qualquer declaração** | nada: não havia tela entre o clique e a rodada criada | `HerancaDaRodadaAnterior`: contratado, vigente, medido no período, acumulado e saldo, código a código — e, sem RE-RA, contratado e vigente repetindo o mesmo número de propósito |
| 3 | Decisão 6 — a **prévia mostra o efeito código a código antes de gravar** | nada: o efeito só aparecia **depois** de gravar, na memória | `PreviaDaReRa`: contratado → vigente hoje → efeito → vigente novo → acumulado → saldo novo, antes do `POST` |

O desvio 1 tinha uma **consequência funcional** que o registro anterior não viu: como o caminho
da medição seguinte não passava pela abertura, não havia como declarar uma RE-RA na medição
seguinte pela tela, embora a API sempre tenha aceitado `previous_round_id` junto de
`amendment`. Re-ratificação é o que acontece **entre** medições — no período 1 não há o que
re-ratificar (ADR-0056, contexto) —, então o caminho principal da feature estava inalcançável
pela interface.

Sobre a decisão 4 na MEMÓRIA (e não na herança): ali o implementado continua espelhando
`ReajusteDeclarado` — sem declaração, o bloco inteiro não aparece. A ausência de RE-RA já é
declarada na resposta (`amendments: []`), e a repetição de propósito passou a existir onde a
decisão 4 a pede, que é a herança antes de declarar. Se a coluna repetida também for desejada
na memória, é mudança pequena e o pacote vira revisão 2.

## Desvios que permanecem

1. **A declaração é carimbada com o `sub` do principal**, não com um nome legível — é o que a
   API grava em `declared_by` (identidade do servidor, nunca do corpo). Na imagem 02 isso
   aparece como o UUID do usuário sintético local. Copy e apresentação da autoria não estavam
   cobertas pela aprovação do pacote.
2. **A evidência de navegador dos estados novos não foi recapturada.** As quatro imagens acima
   são da revisão anterior e não mostram a porta nova, a herança nem a prévia. A recaptura é
   tarefa própria e é condição para a feature voltar a `READY_FOR_HUMAN_REVIEW`.

### Resolvidos pela T7

O desvio que a T6 registrou como "exceção declarada à regra" — **a prévia calculada no
cliente** — deixou de ser dívida. A [T7](tasks/T7-previa-no-servidor.md) o fecha, e fecha junto
a lacuna irmã que a T6 tinha listado.

| Era | Passou a ser |
| --- | --- |
| A prévia é calculada no cliente, com aritmética exata em texto sobre `BigInt`, e a T6 chamou isso de exceção declarada à regra "a tela nunca soma" | A conta é do servidor, em `POST /v1/valuation-round-previews`. `previa.ts` não tem mais aritmética: sobrou chamada, estado e exibição, e a regra do `apps/web/AGENTS.md` volta a valer sem exceção |
| Duas identidades do domínio rederivadas no navegador: o acumulado (`vigente − saldo`) e o medido do período (soma das linhas de `GET /bulletin`) | Nenhuma. `accumulated_quantity` e `measured_quantity` vêm por código na resposta da prévia, produzidos pelo mesmo caminho que grava o consolidado |
| Os números da prévia protegidos por um par de testes que fixava **o caso sintético** dos dois lados | Protegidos pela **estrutura**: prévia e criação chamam `_contracted_valuation_origin` e `_apply_declared_acts`, e um teste manda o mesmo corpo às duas rotas |
| A prévia não existia na abertura a partir do **orçamento assinado**, porque o cliente não recebia o contratado código a código nessa porta | Existe nas duas portas contratadas: quem projeta é o servidor, e ele conhece o contratado do orçamento assinado tão bem quanto o da rodada anterior. O limite que motivava a lacuna deixou de existir |

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
  ocorreu em 2026-08-28, **antes** de os três desvios do pacote serem vistos).
- Decidir se a MEMÓRIA sem RE-RA deve imprimir contratado e vigente repetidos — na herança da
  medição seguinte a repetição de propósito já existe, desde a T6.
