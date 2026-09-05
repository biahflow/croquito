# F-051 — Evidência

Feature: [A cota-balão encontra seu elemento](feature.md)
Estado: `DONE` — **gate 3 cumprido com achado em 2026-09-05** (seção ao fim deste documento)
Data: 2026-09-04 · gate 3 em 2026-09-05

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
| **Gate 3 — aceite contra o caso real do Toca** | ✅ **Cumprido com achado em 2026-09-05** (Daniel Campos, pelo chat: "gate cumprido com achado"). A execução do roteiro foi delegada à bancada pelo dono, o veredito é dele; o achado é a [issue #174](https://github.com/biahflow/croquito/issues/174). Seção própria ao fim deste documento |

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
| 1 | No caso real do Toca, a leitura `C=56m` com hint "B" ganha candidata por identidade, é confirmável pelo portão de sempre e **entra no solver** como constraint | ✅ **Provado contra o croqui real no gate 3** (2026-09-05, seção ao fim): `EL-001 "B"` declarado sobre a proposta do fecho, candidata por identidade oferecida e confirmada, blocker `EXPLICIT_ASSOCIATION_REQUIRED` limpo, e a `C=56` em `applied_spans` — após o keep_apart da disputa 55×56, **"56,00 amarra 0,00 → 56,00", exata**. Antes do gate, o mecanismo já estava provado em fixture sintética ponta a ponta: `tests/e2e/test_full_flow.py::test_a_cota_balao_com_hint_vira_restricao_e_a_orfa_segue_como_hoje` (o portão recusa a confirmação **antes** da declaração, e depois dela a cota-balão aparece em `applied_spans` com `axis="x"` e `value_m=25,90`), e no navegador nas capturas [01](evidencia/01-a-cota-balao-sem-elemento.png), [04](evidencia/04-candidata-por-identidade.png), [05](evidencia/05-confirmada-pelo-portao.png) e [09](evidencia/09-o-tracado-resolvido.png) — esta última com "3 cotas conferidas contra a geometria", que são três porque a cota-balão entrou |
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
| [#174](https://github.com/biahflow/croquito/issues/174) — cota de balão em elemento inclinado é projetada no eixo (fecho×vão) | **Aberta** | Aberta **pelo gate 3**: é o achado com que o gate foi dado como cumprido. O risco estava pré-registrado no roteiro; o mecanismo de vão é anterior à F-051 |

## Riscos remanescentes

- ~~**O critério 1 continua provado só em fixture.**~~ **Resolvido pelo gate 3** (seção
  abaixo): o critério foi provado contra o croqui real, e o desfecho previsto na tabela "o
  que pode dar errado" do [roteiro](evidencia/ROTEIRO-GATE-3.md) aconteceu na forma
  projetiva — virou a [issue #174](https://github.com/biahflow/croquito/issues/174), achado
  do mecanismo de vão, não falha desta feature.
- ~~**O pacote real foi extraído antes da T1**~~ — confirmado e **exercido no gate 3**: a
  leitura chegou com `target_entity_label` vazio e a correção do hint pela decisão (T1/T4)
  funcionou contra dado real, recunhando as candidatas.
- **A identidade na cena (critério 4) segue provada só em fixture.** O solve real terminou
  `conflict` por disputa pré-existente alheia à F-051 (o trio `1,25/0,45/0,70` da
  arquibancada 2), então nenhuma cena nova nasceu do job real e o `◇ EL-001` não foi visto
  na aprovação real — está provado no e2e e na captura 10 sintética.
- **Sugestão assistida com sugestões de verdade** não foi vista em navegador: as propostas da
  fixture sintética não têm rótulo do modelo, então só o estado vazio do painel foi
  fotografado.
- **A `quality` da `main` segue vermelha** enquanto a #171 não for tratada; até lá nenhum
  trabalho fecha o portão completo, e o controle é o `make test`.

## Human Gate 3 — o aceite contra o croqui real (2026-09-05)

**Cumprido com achado por ato humano em 2026-09-05** (Daniel Campos, pelo chat: "gate
cumprido com achado"). O dono delegou à bancada a execução das etapas 1–6 do
[roteiro](evidencia/ROTEIRO-GATE-3.md) — Chromium via Playwright, sessão OIDC real como
`engenheiro.local`, contra o job `01a068ef-db34-7891-a7ef-d61fbaf30ea5` no stack local
(banco `croquito_toca`; API em `127.0.0.1:8010` porque a 8000 estava com outro projeto) —
e exerceu o veredito sobre o desfecho relatado. Backup do banco feito antes de qualquer
ato; nenhum provider pago chamado; nada fora do job foi tocado.

O que cada etapa produziu, na ordem do roteiro:

1. **Declarar o elemento.** `EL-001 "B"` cunhado pelo servidor sobre a única proposta que
   desenha o fecho inclinado da área de lazer (`vp_ce0c597027e463c8`, "⑰ linha
   horizontal · 1228 px"), identificada por reconstrução geométrica do croqui — o fecho
   liga as pontas dos lados A (+12) e C (+1) depois do lado B — e sem nenhum fragmento
   colinear concorrente. Ato sobre a revisão v9.
2. **O hint.** Como o roteiro previu, o pacote é pré-T1 e o chip não existia
   (`target_entity_label` vazio). A correção pela própria decisão ("B" no campo do balão,
   retificação gravada, v10) fez o chip aparecer e o servidor recunhar as candidatas.
3. **A candidata por identidade.** O grupo `Pela identidade — ◇ EL-001 · B` surgiu acima
   das candidatas de proximidade (nº 66, nº 31 e ⑤ — as erradas, que eram o motivo do
   `annotation=true` original), com a relação por extenso e o `field-hint` do casamento.
4. **O portão de sempre.** "Corrigir decisão registrada", justificativa escrita, decisão
   com autor e instante (v11); associação `rd_5d2c7d3e66ec4aaa → vp_ce0c597027e463c8`
   registrada. O blocker `EXPLICIT_ASSOCIATION_REQUIRED:rd_5d2c…`, residual desde a
   revisão conjunta de 2026-09-03, **limpou**.
5. **Traçado.** A `C=56` saiu de "anotação da folha — sem vão" para **"mede a forma ⑰"**;
   aceite com 16 formas (as 15 que as cotas confirmadas já mediam + o fecho).
6. **O solver — onde o gate se decidiu.** A `C=56` **entrou como constraint** e conta
   entre as cotas conferidas. Primeiro solve (`01a07097…`): o risco pré-registrado
   **fecho×vão** se materializou na forma projetiva — o vão amarra por projeção no eixo, o
   fecho inclinado (√(55²+11²) ≈ 56,07) projetado no X vira ≈ a largura, e `"55,00" e
   "C= 56 m"` disputaram o mesmo vão (`contested_spans`; solver rachou em 55,50; as duas
   0,5 m fora, contra tolerância de 0,5). O consultor ofereceu na própria disputa o ato
   desenhado para isso — **"Manter as duas separadas"** (keep_apart com eixo), que não
   altera nenhum valor escrito e declara a verdade do domínio: largura e fecho são
   elementos distintos de projeção coincidente. No re-aceite (`01a07098…`):
   **"56,00 amarra 0,00 → 56,00 m na horizontal"** e "55,00 amarra 0,29 → 55,29", ambas
   exatas, e a disputa sumiu.

O solve permaneceu `conflict` por causa de disputa **pré-existente e alheia à F-051** — o
trio `1,25/0,45/0,70` (arquibancada 2) disputando o mesmo vão de um contorno, pior erro
0,45 m — mais seis avisos `TRACE_SPAN_NOT_ORTHOGONAL` de cotas amarradas a formas
inclinadas do CV. Por isso nenhuma cena nova nasceu do job real, e a metade "a identidade
chega à cena" (critério 4) segue provada pela fixture sintética. Corrigir o trio exigiria
reabrir decisões da revisão conjunta do oráculo, fora do escopo do gate.

O achado virou a [issue #174](https://github.com/biahflow/croquito/issues/174), como a
tabela "o que pode dar errado" do próprio roteiro prescreve: *a identidade e a candidata
continuam válidas — o que faltou é o significado geométrico do número, que nenhuma parte
desta feature promete*.

Rastros verificáveis: revisões v9–v11 e os solves `01a07094…`/`01a07097…`/`01a07098…` no
banco local `croquito_toca`; 19 capturas e os scripts das fases em `output/f051-gate3/`
(retenção local de 7 dias — as capturas contêm recortes do croqui real e **não** são
versionadas, pela regra de dados de cliente). De passagem, a bancada drenou ~39 mensagens
velhas de `rerender_estimate_takeoff_overlay` que represavam a fila local de outra rodada.
