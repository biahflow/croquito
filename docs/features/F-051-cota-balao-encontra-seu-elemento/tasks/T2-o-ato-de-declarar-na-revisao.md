# F-051 · T2 — O ato de declarar elemento na revisão

Feature: [F-051](../feature.md) · Plano: [plan.md](../plan.md) · Estado: **Pendente**  
`feature_id: F-051` · `task_id: T2` · `depends_on: —`

## Objetivo

O mesmo ato do ADR-0058, uma etapa antes: um humano declara que um conjunto de **propostas de
geometria** é um elemento; o sistema cunha `EL-NNN` no namespace único do job; renomear e
revogar são atos declarados. Tudo no idioma das rotas de identidade da cena (F-047 T2), que
são o molde direto.

## Escopo

- **Persistência**: coluna JSON aditiva (ex. `element_declarations_json`) em
  `ReviewRevisionRecord` (`services/api/src/croquito_api/database.py:595-685`) + migração
  forward-only. A coluna entra em `_carried_review_context` (`main.py:5883-5895`) e é herdada
  nas 9 montagens de revisão (`main.py:8984, 9273, 9488, 10006, 10206, 10435, 10652, 10826,
  10956`); entra também na semente do worker (`review_store.py:88-221`,
  `insert_review_revision_v1`) e no clone de `insert_next_review_revision`
  (`review_store.py:224-300`) — vazia na semente, preservada no clone.
- **Rotas novas** (molde `main.py:11240-11568`): declarar / revogar / renomear elemento **da
  revisão**, com `proposal_ids` (validados contra o snapshot `proposals_json`, como a rota de
  traçado faz em `main.py:12139-12169`) no lugar de `entity_ids`; `base_version` +
  `Idempotency-Key` + `problem+json` como toda mutação; papel de revisão obrigatório;
  `element_ref` no payload é recusado (`ELEMENT_REF_NOT_ASSIGNABLE`, como `:11259-11265`).
- **Namespace único**: `_next_element_ref` (`main.py:5772-5803`) passa a varrer também as
  declarações da revisão do job, além das cenas.
- Trio de superfície: `openapi.snapshot.json`, `API_CONTRACT.md`, `apps/web/src/api.ts`
  (tipos manuais, molde `api.ts:1146-1233`).
- Testes no molde de `tests/api/test_element_identity.py` (cunhagem sequencial `:258`,
  concorrência `:472`, idempotência `:429`, `base_version` `:461`, papel `:543`).

## Fora de escopo

- Sugestões assistidas (T3), candidatas (T4), transporte (T5), tela (T6).
- Mudar as rotas de identidade da **cena** — continuam valendo para o pós-solve, no mesmo
  contador.
- Desfazer associações ao revogar (leitura confirmada no aceite do DAP: **revogar não desfaz
  associação confirmada** — corrigir associação é a retificação de decisão que já existe).

## Critérios de aceite

1. Declarar sobre 2 propostas cunha `EL-NNN` sequencial ao namespace do job (se a cena já tem
   `EL-001`, a revisão cunha `EL-002` — e vice-versa); teste dos dois sentidos.
2. **Rótulo único por job na revisão** (leitura confirmada no aceite do DAP): declarar um
   segundo elemento com rótulo já usado é recusado com código estável apontando o existente.
3. Declarar exige ≥1 `proposal_id` existente no snapshot; declaração sem proposta é recusada
   (o caminho do balão sem proposta continua `annotation=true`).
4. Renomear e revogar são atos registrados (autor por papel, instante, revisão); a identidade
   revogada não sai do histórico e o ref não é reaproveitado; revogar **não** altera
   `selected_associations_json`.
5. Toda revisão sucessora criada por outros atos herda as declarações intactas
   (`_carried_review_context`); teste que exercita um ato não relacionado e confere a herança.
6. Sem declaração nenhuma, todas as rotas existentes respondem byte a byte como hoje.
7. Snapshot de OpenAPI aditivo; `API_CONTRACT.md` atualizado.

## Validação

```text
baseline: make check && make test verdes na main (registrar o resultado real antes de mudar)
required: uv run pytest tests/api -x
required: make check && make test
```

## Riscos conhecidos

- A colisão de contador entre revisão e cena é resolvida pela varredura dupla + concorrência
  otimista de cada lado — o teste de concorrência precisa cobrir o sentido cruzado
  (declaração na revisão × declaração na cena no mesmo job).
- Migração: banco com revisões existentes ganha coluna nula — leitura tolerante a `NULL` (o
  mesmo padrão das colunas F-030).

## Human gates

Nenhum interno à tarefa; os dois já exercidos (ADR-0063, DAP rev.1) cobrem as decisões.
