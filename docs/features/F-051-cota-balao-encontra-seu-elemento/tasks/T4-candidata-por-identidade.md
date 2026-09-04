# F-051 · T4 — A candidata por identidade, cunhada no ato

Feature: [F-051](../feature.md) · Plano: [plan.md](../plan.md) · Estado: **Entregue**  
`feature_id: F-051` · `task_id: T4` · `depends_on: T1, T2`

## Objetivo

Leitura cujo `target_entity_label` casa com o rótulo de um elemento declarado ganha candidata
de **todas as propostas daquele elemento**, com `relation="element_identity"`, independente de
distância — observacional como sempre. Achado do planejamento que dimensiona a tarefa: as
candidatas são **persistidas** (`associations_json`) e a API nunca recomputa — então a
candidata por identidade nasce e morre **nos atos** (declarar/revogar/renomear/corrigir
hint), por função pura chamada pelas rotas de mutação da T2 e pela decisão que corrige o
hint (T1).

## Escopo

- `services/worker/src/croquito_worker/association.py:32-50` — `AssociationCandidate.relation`
  (`Literal["nearest_geometry","inside_or_near_circle"]`) ganha `"element_identity"`. Os
  campos observacionais continuam preenchidos com fatos (a distância real em pixels é um
  fato; ela só deixa de ser critério). `AssociationSet.associator_version` **não muda**
  (achado 3 do plano).
- **Função pura de casamento + merge** (em `association.py` ou módulo irmão): dado o pacote,
  as declarações e o `AssociationSet` persistido, devolve o conjunto com as candidatas por
  identidade das leituras afetadas — determinística, sem rede, testável isolada.
- **A normalização mínima do casamento é decidida AQUI** (Unknown 1 do contrato), contra o
  dado do job de referência real: constante nomeada + declarada em código e teste (ex.:
  trim + caixa; **nunca** fuzzy silencioso). A T3 adota a mesma constante.
- Chamadas do merge nos atos da T2 (declare/revoke/relabel) e no comando de decisão que
  corrige `target_entity_label` (T1, `main.py:8948`/`:9199`) — revisão nova, mesmo
  `base_version` de sempre.
- O portão `_apply_association_rules` (`main.py:6611-6652`) **não muda**: candidata na lista
  persistida já é confirmável por construção.
- Testes: molde `tests/worker/test_association.py` (função pura) +
  `tests/api/test_api.py` (ato → candidata aparece; revogação → candidata some;
  confirmada não some do `selected_associations` — coerente com a leitura do DAP).

## Fora de escopo

- Mudar `associate_readings`, o ranking de proximidade ou o associador
  (`pixel-proximity-associator-v1`) — intocados.
- O portão de confirmação — intocado.
- Tela (T6) e transporte (T5).

## Critérios de aceite

1. Declarado o elemento "B" (2 propostas), a leitura com `target_entity_label="B"` ganha
   exatamente 2 candidatas `element_identity`, `unresolved`/`export=false`, **além** das de
   proximidade — nunca no lugar (teste compara o conjunto antes/depois).
2. Leitura com hint que não casa (ex. "E"): conjunto de candidatas byte a byte igual ao de
   hoje (critério de aceite 2 do contrato).
3. Confirmação da candidata por identidade passa pelo portão único e entra em
   `selected_associations` — nenhum caminho novo de escrita.
4. Revogar o elemento remove as candidatas por identidade não confirmadas das leituras
   afetadas e **não** toca associação confirmada (leitura do DAP).
5. Corrigir o hint da leitura recunha as candidatas dela (o "B" errado corrigido para "C"
   troca as candidatas de elemento).
6. A constante de normalização existe, tem nome, e o teste a exercita com as formas do job
   de referência ("B" × "grade B" × "alambrado B" — o que casar e o que não casar fica
   declarado no teste).
7. Job sem declaração nenhuma: `associations_json` resultante de qualquer ato é idêntico ao
   de hoje.

## Validação

```text
baseline: make check && make test verdes na main (registrar o resultado real antes de mudar)
required: uv run pytest tests/worker/test_association.py tests/api -x
required: make check && make test
```

## Riscos conhecidos

- Schema do `AssociationSet` persistido: pacotes velhos validam com o `Literal` estendido
  (aditivo), mas candidata nova em código velho não valida — mesmo fail-closed da T1;
  teste de leitura de `associations_json` legado.
- Se a decisão da normalização contrariar o dado real (formas que deveriam casar e não
  casam), a resposta é **parar e registrar** — a constante é decisão declarada, não ajuste
  silencioso (princípio do contrato).

## Resultado

Entregue em 2026-09-04.

**A normalização decidida (Unknown 1), em duas funções de força deliberadamente diferente**,
num módulo próprio (`croquito_worker/element_identity_matching.py`) para que a diferença
fique escrita num lugar só:

- `label_group_key` (**agrupar**, adotado pela T3) — igualdade normalizada,
  `casefold(strip())`. `"Grade B"` agrupa com `"grade b"`; `"grade B"` **não** agrupa com
  `"B"`, porque agrupar afirma que as propostas são a mesma coisa.
- `hint_matches_label` (**casar** hint↔elemento) — igualdade normalizada **ou** o hint como
  palavra inteira do rótulo, tokenizado por espaço e por `—`, `-`, `·`, `:`, `/`. `"B"`
  alcança `"B"`, `"grade B"` e `"B — fecho da área de lazer"`; `"E"` não alcança nada, e
  `"B"` não alcança `"fecho"`. Nunca distância de edição, parecença ou prefixo.

As formas são as reais (hints do provider na issue #139; rótulos humanos do ADR-0063 e do
DAP aprovado) e estão na tabela de `tests/worker/test_element_identity_matching.py`. Dois
elementos que casam com o mesmo hint produzem candidatas dos dois — resultado legítimo, não
empate a desfazer.

**A reconstrução, e não o acréscimo.** `rederive_element_identity_candidates` (função pura
em `association.py`) remove todas as candidatas `element_identity` e as re-deriva das
declarações correntes, com dedupe por `(reading_id, proposal_id)` e candidatas novas
sempre DEPOIS das existentes. Idempotente por construção: chegar ao conjunto de entrada
devolve o **mesmo objeto**, e é essa identidade que faz quem grava copiar o
`associations_json` verbatim. Uma exceção declarada, que é o critério 4: a candidata que
sustenta associação confirmada não é removida — tirá-la deixaria `selected_associations`
apontando para um par fora da lista, e a próxima retificação daquela cota morreria no
portão (o desfazer que a revogação não faz, adiado um turno).

**Cinco pontos de chamada**, todos criando revisão nova como sempre: os três atos de
identidade (por dentro de `_persist_review_element_act`, que passa a gravar as candidatas
derivadas em vez da cópia verbatim) e os dois que corrigem o `target_entity_label` — decisão
e retificação declarada. Nos dois últimos a derivação roda **depois** do portão: ele
continua lendo as candidatas como estavam persistidas, senão o hint corrigido no mesmo envio
confirmaria uma candidata que ninguém viu na tela. `_apply_association_rules`,
`associate_readings`, o ranking de proximidade e `associator_version` ficaram intocados.

Trio de superfície atualizado: `openapi.snapshot.json` (`make openapi-snapshot`, diff só o
valor novo do enum), `API_CONTRACT.md` e `apps/web/src/api.ts` — este último já tipava
`relation` como `string`, então recebeu só o comentário com os três valores.
`FLUXO_DO_SISTEMA.md` ganhou a segunda origem de candidata do funil. **Uma linha a mais que
o contrato não previa**: `labels.ts` ganhou a tradução de `element_identity`, porque a tela
de revisão já escreve a relação de cada candidata e o FDD proíbe enum em inglês para quem
revisa — sem isso, a primeira declaração feita pela API faria a tela mostrar
`element_identity` cru. Como a candidata é APRESENTADA (destaque, ordem, ícone) continua
sendo decisão da T6.

28 funções de teste novas (47 casos, com a tabela parametrizada): 4 em
`tests/worker/test_element_identity_matching.py` (20 formas reais na tabela + a diferença
entre agrupar e casar), 15 em `tests/worker/test_association.py` (função
pura — soma sem substituir, observacionalidade, dedupe, idempotência, revogação com e sem
confirmação, correção de hint, dois elementos com o mesmo hint, ida e volta da lista de não
associadas, proposta fora do snapshot, forma humana sem `quality_score`, conjunto legado),
1 em `tests/worker/test_review_element_suggestions.py` (a T3 adotando a constante) e 8 em
`tests/api/test_review_element_identity_candidates.py` (os cinco atos ponta a ponta, o
portão único, e o controle byte a byte). A fixture `_seed_review_session` ganhou a
cota-balão sintética (`balloon_reading=True`, desligada por padrão).

**Desvio consciente registrado**: em `_persist_review_element_act` o `confidence_shadow_json`
passou a ser computado sobre o conjunto derivado, em vez de `_carried_confidence_shadow`
(que o computa sobre o conjunto da revisão anterior). O shadow descreve os candidatos DA
revisão em que está gravado; deixá-lo apontando para o conjunto antigo criaria uma revisão
internamente incoerente. Com o conjunto intocado os dois caminhos dão exatamente o mesmo
valor — a função é pura sobre as mesmas entradas —, então o controle byte a byte segue
válido. Candidata por identidade nasce com `association_confidence=0.0` e por isso nunca é
escolhida por nenhum corte da grade do shadow nem pelo modo automático (ADR-0041).
