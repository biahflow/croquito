# F-051 · T4 — A candidata por identidade, cunhada no ato

Feature: [F-051](../feature.md) · Plano: [plan.md](../plan.md) · Estado: **Pendente**  
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
