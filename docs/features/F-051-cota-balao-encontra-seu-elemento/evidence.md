# F-051 — Evidência

Feature: [A cota-balão encontra seu elemento](feature.md)
Estado: `READY_FOR_HUMAN_REVIEW` — as sete tarefas estão na `main`; falta o **gate 3**, o
aceite contra o croqui real
Data: 2026-09-04

Este documento consolida a evidência das sete tarefas da F-051, **com atribuição por
tarefa**: cada linha aponta o PR, o commit de merge na `main` e o que aquela tarefa mudou.
Os relatórios de cada builder ficaram nas sessões que os produziram; o que está aqui é o que
o repositório carrega e que qualquer pessoa pode reconferir — não é um relatório fundido, e
não reescreve o que cada builder afirmou.

## Gates humanos

| Gate | Estado |
| --- | --- |
| `ARCHITECTURE_DECISION_REQUIRED` | ✅ [ADR-0063](../../adr/0063-identidade-de-elemento-nasce-na-revisao.md) **aceito por ato humano em 2026-09-04** (Daniel Campos, pelo chat) — PR [#150](https://github.com/biahflow/croquito/pull/150) |
| `DESIGN_APPROVAL_REQUIRED` | ✅ **Aprovado por ato humano em 2026-09-04**, revisão 1 ([`mock/README.md`](mock/README.md)), com duas leituras confirmadas no mesmo ato: rótulo de elemento único por job na revisão, e revogação que não desfaz associação já confirmada |
| Merge de cada PR | ✅ os sete PRs de execução foram mergeados por ato humano (tabela abaixo) |
| **Gate 3 — aceite contra o caso real do Toca** | ⏳ **Pendente.** É ato do dono, com o [roteiro](evidencia/ROTEIRO-GATE-3.md) desta tarefa em mãos. A feature **não é `DONE` sem ele** |

## O que foi entregue, por tarefa

| # | Tarefa | PR | Merge | O que mudou | Testes novos |
| --- | --- | --- | --- | --- | --- |
| — | [DAP revisão 1](mock/README.md) | [#157](https://github.com/biahflow/croquito/pull/157) | `cbd0197` | o pacote de design com os nove estados, aprovado pelo dono | — |
| — | Aceite do DAP transcrito + [plano congelado](plan.md) | [#158](https://github.com/biahflow/croquito/pull/158) | `fc42c2b` | `PLAN_VALID`, 7 tarefas, contratos em [`tasks/`](tasks) | — |
| T1 | [O hint estruturado sobrevive até a leitura](tasks/T1-o-hint-estruturado.md) | [#162](https://github.com/biahflow/croquito/pull/162) | `ab94dc1` | `DimensionReading.target_entity_label`; `provider_review.py` e `transcription.py` deixam de achatar; o comando de decisão grava o campo; `ReviewPacket.schema_version` `1.1.0` → `1.2.0` | 4 pytest (`test_api.py`, `test_providers.py`, `test_transcription.py`) |
| T2 | [O ato de declarar elemento na revisão](tasks/T2-o-ato-de-declarar-na-revisao.md) | [#161](https://github.com/biahflow/croquito/pull/161) | `a28151d` | `POST /v1/jobs/{id}/review/elements` (+ `labels`, `revocations`), coluna JSON aditiva em `ReviewRevisionRecord`, migração `0031`, namespace de `element_ref` único por job | 24 pytest (`test_review_element_identity.py`, `test_review_refresh.py`) |
| T3 | [As sugestões assistidas da revisão](tasks/T3-sugestoes-da-revisao.md) | [#165](https://github.com/biahflow/croquito/pull/165) | `ccc19bd` | `review_element_suggestions.py` (produtor sobre `VisionProposalSet`), `GET .../review/elements/suggestions`, recusa com motivo, migração `0032` | 19 pytest (`test_review_element_suggestions.py` na API e no worker) |
| T4 | [A candidata por identidade, cunhada no ato](tasks/T4-candidata-por-identidade.md) | [#167](https://github.com/biahflow/croquito/pull/167) | `6fc90ef` | `relation="element_identity"`, `element_identity_matching.py` (a normalização declarada — Unknown 1 do contrato), `rederive_element_identity_candidates` chamada nos cinco atos; portão de confirmação intocado | 28 pytest (`test_element_identity_matching.py`, `test_association.py`, `test_review_element_identity_candidates.py`) |
| T5 | [O traçado transporta a identidade](tasks/T5-transporte-no-tracado.md) | [#164](https://github.com/biahflow/croquito/pull/164) | `3f9c957` | `tracing.py` cria a entidade já com `element_ref`/rótulo; `SceneRevision.element_labels` alimentado pelo traçado; `ELEMENT_REF_LAYER_MISMATCH` tratado como caso de teste | 10 pytest (`test_tracing.py`, `test_trace_solve_worker.py`, `test_full_flow.py`) |
| T6 | [A tela da revisão](tasks/T6-tela-da-revisao.md) | [#169](https://github.com/biahflow/croquito/pull/169) | `0aa07c0` | chip do hint, painel `reviewElementIdentityPanel.tsx`, `<optgroup>` "Pela identidade" no seletor, `GET .../review/elements` (o `PLAN_DEVIATION` do plano, resolvido com rota própria) | 6 pytest + 50 vitest (`reviewElementIdentity.test.ts`, `reviewElementIdentityPanel.test.tsx`, `CroquiApp.test.tsx`) |
| T7 | [Evidência de navegador e o caso real](tasks/T7-evidencia-e-o-caso-real.md) | — (esta entrega) | — | as dez capturas de [`evidencia/`](evidencia), o e2e da cadeia inteira, este documento e o [roteiro do gate 3](evidencia/ROTEIRO-GATE-3.md) | 1 pytest e2e (`test_a_cota_balao_com_hint_vira_restricao_e_a_orfa_segue_como_hoje`) |

Dois consertos de CI entraram **no meio da execução**, e não são da F-051: eles consertavam
a `quality` da `main`, que já estava vermelha por causa da
[issue #163](https://github.com/biahflow/croquito/issues/163) (âncora do `preview.png`
dependente de plataforma) — [#166](https://github.com/biahflow/croquito/pull/166) (`8275d7f`)
e [#168](https://github.com/biahflow/croquito/pull/168) (`1d3218c`). Também no meio,
[#159](https://github.com/biahflow/croquito/pull/159) (`c47f955`) tirou o deploy de HML do
merge na `main`.

## Critérios de aceite do contrato

| # | Critério | O que o prova |
| --- | --- | --- |
| 1 | No caso real do Toca, a leitura `C=56m` com hint "B" ganha candidata por identidade, é confirmável pelo portão de sempre e **entra no solver** como constraint | ⏳ **Só o gate 3 fecha este.** O mecanismo está provado em fixture sintética ponta a ponta: `tests/e2e/test_full_flow.py::test_a_cota_balao_com_hint_vira_restricao_e_a_orfa_segue_como_hoje` (o portão recusa a confirmação **antes** da declaração, e depois dela a cota-balão aparece em `applied_spans` com `axis="x"` e `value_m=25,90`), e no navegador nas capturas [01](evidencia/01-a-cota-balao-sem-elemento.png), [04](evidencia/04-candidata-por-identidade.png), [05](evidencia/05-confirmada-pelo-portao.png) e [09](evidencia/09-o-tracado-resolvido.png) — esta última com "3 cotas conferidas contra a geometria", que são três porque a cota-balão entrou |
| 2 | Leitura com hint que não casa: comportamento de hoje, sem candidata nova | Mesmo e2e (a leitura com hint "E" sai da declaração sem nenhuma candidata, e o conjunto das de proximidade fica idêntico ao de antes) + `tests/api/test_review_element_identity_candidates.py`. **Na tela**: [06](evidencia/06-o-hint-que-nao-casa.png), com a frase "Nenhum elemento declarado tem o rótulo 'E' — nenhuma candidata nova", e [08](evidencia/08-a-orfa-sem-vao.png), onde ela segue "anotação da folha — sem vão" |
| 3 | Declaração é humana: nenhuma identidade nasce sem ato, e a sugestão recusada não reaparece confirmada | `tests/api/test_review_element_identity.py` e `test_review_element_suggestions.py` (recusa com motivo, um único caminho de escrita). **Na tela**: [02](evidencia/02-o-ato-de-declarar.png) (o `element_ref` em campo somente-leitura, "cunhada no ato pelo servidor") e [03](evidencia/03-o-elemento-declarado.png) (carimbo por papel e instante) |
| 4 | A entidade criada pelo traçado a partir de proposta identificada carrega `element_ref` e rótulo na cena aprovada; o quantitativo da F-047 agrupa por ele | `tests/e2e/test_full_flow.py::test_element_identity_declared_on_the_review_travels_through_the_trace` (T5) e o e2e novo da T7. **Na tela**: [10](evidencia/10-a-cena-com-a-identidade.png) — `◇ EL-001 · B · camada DETALHES · 2 entidades · exata · → alimenta a medição`, no painel de identidade da cena que a F-047 já lia |
| 5 | Contratos regenerados sem drift; `make check`/`make test` verdes; evidência de navegador (`BROWSER_REQUIRED`) | Evidência de navegador: [`evidencia/`](evidencia) e o [README](evidencia/README.md). Portões: seção abaixo — `make test` **verde**; `make check` **vermelho por defeito preexistente e alheio**, registrado na [issue #171](https://github.com/biahflow/croquito/issues/171) |

## Portões da T7

**Baseline registrado antes de qualquer edição**, na `main` em `0aa07c0`:

| Portão | Baseline (antes) | Depois da T7 |
| --- | --- | --- |
| `make check` | ❌ **vermelho** — `tests/core/test_scene.py:501: error: Value of type "object" is not indexable [index]`, 1 erro em 333 arquivos. Idêntico no CI da `main` (corrida `33923674576`) | ❌ **o mesmo erro, na mesma linha** — nada foi acrescentado nem consertado |
| `make test` | ✅ verde — 3406 pytest (17 pulados), 1836 vitest do web, 261 do app de campo | ✅ verde — 3407 pytest (17 pulados), mesmos vitest |
| `uv run pytest tests/e2e -x` | ✅ verde | ✅ verde |
| `uv run python scripts/check_docs.py` | ✅ verde | ✅ verde |

O vermelho do `make check` **é anterior à T7 e é de outra área**: nasceu no PR
[#168](https://github.com/biahflow/croquito/pull/168), o "parte 2" do conserto da issue #163,
e deixou a `quality` da `main` vermelha nos dois merges seguintes. A T7 **não o consertou** —
`tests/core/test_scene.py` não é escopo desta tarefa — e abriu a
[issue #171](https://github.com/biahflow/croquito/issues/171) com a reprodução local e a do
CI. É defeito de tipagem em arquivo de teste: `make test` está verde, e nem a API nem a tela
são afetadas.

## Achados registrados no caminho da feature

| Issue | Estado | Relação com a F-051 |
| --- | --- | --- |
| [#160](https://github.com/biahflow/croquito/issues/160) — `refresh-proposals` apaga a correção humana de forma (F-018) em silêncio | **Aberta** | Preexistente, avistada três vezes durante a execução. Não é da F-051 e não foi consertada por ela |
| [#163](https://github.com/biahflow/croquito/issues/163) — âncoras dependentes de plataforma na auditoria | **Fechada** | Deixava a `quality` da `main` vermelha; consertada em duas partes (#166 e #168) durante a execução da F-051 |
| [#171](https://github.com/biahflow/croquito/issues/171) — mypy reprova em `tests/core/test_scene.py:501` | **Aberta** | Aberta **por esta tarefa**, ao registrar o baseline. Regressão do conserto anterior; mantém a `quality` da `main` vermelha |

## Riscos remanescentes

- **O critério 1 continua provado só em fixture.** O e2e e as capturas usam a mesma cadeia do
  produto, mas o número, o desenho e o hint são inventados. O que o croqui real do Campo da
  Toca pode expor — e que a fixture não expõe — está escrito no
  [roteiro do gate 3](evidencia/ROTEIRO-GATE-3.md), na tabela "o que pode dar errado": o
  `C=56,00` real é o **fecho** do elemento, e o traçado amarra vão, não perímetro. Se for
  esse o desfecho, é achado novo, não falha desta feature.
- **O pacote real foi extraído antes da T1**, então a leitura provavelmente chega com
  `target_entity_label` vazio: o gate 3 passa por corrigir o hint pela decisão, que é ato
  previsto (T1/T4) mas ainda não exercido contra dado real.
- **Sugestão assistida com sugestões de verdade** não foi vista em navegador: as propostas da
  fixture sintética não têm rótulo do modelo, então só o estado vazio do painel foi
  fotografado.
- **A `quality` da `main` segue vermelha** enquanto a #171 não for tratada; até lá nenhum
  trabalho fecha o portão completo, e o controle é o `make test`.
