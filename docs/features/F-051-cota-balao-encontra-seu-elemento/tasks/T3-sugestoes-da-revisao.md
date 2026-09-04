# F-051 · T3 — As sugestões assistidas da revisão

Feature: [F-051](../feature.md) · Plano: [plan.md](../plan.md) · Estado: **Entregue**  
`feature_id: F-051` · `task_id: T3` · `depends_on: T2`

## Objetivo

Baratear o ato da T2: os rótulos que o modelo deu às propostas de geometria
(`VisionProposal.label`, `vision.py:114`) viram **sugestões** de elemento — que nascem
`unresolved`, não geram candidata nenhuma e não valem nada até alguém declarar. Achado do
planejamento: o produtor da F-047 T6 (`propose_element_groups`,
`croquito_core/element_proposals.py:187`) é **pós-solve** e não serve 1:1 — este produtor é
novo, sobre `VisionProposalSet`, no mesmo espírito.

## Escopo

- **Produtor determinístico novo** (módulo em `packages/core` ou `croquito_worker`, a decidir
  pelo padrão do vizinho `element_proposals.py`): agrupa propostas por rótulo do modelo
  (normalização mínima compartilhada com a T4 quando ela existir; até lá, casamento exato),
  `proposal_id` de sugestão determinístico (molde do hash `element_proposals.py:83-91`, que
  mantém a recusa reconhecível em recomputações), sem provider pago.
- **Rota de leitura** e **rota de recusa com motivo** (molde `main.py:11579-11627` e
  `:11629+`; recusa mínima de 3 caracteres, como `elementIdentity.ts:321-326` espera do lado
  web).
- Propostas já cobertas por declaração existente **não** são sugeridas (molde
  `test_element_proposals.py: test_entidade_ja_identificada_nunca_e_candidata`).
- Trio de superfície: `openapi.snapshot.json`, `API_CONTRACT.md`, `apps/web/src/api.ts`.
- Testes no molde de `tests/core/test_element_proposals.py` (determinismo, ordem estável) e
  `tests/api/test_element_proposals.py` (rota + recusa).

## Fora de escopo

- Declarar automaticamente qualquer coisa — recusado pelo ADR-0063, decisão 1.
- O ato de declarar em si (T2) — confirmar sugestão é **semear** o ato da T2, nunca um
  segundo caminho de escrita.
- Sugestão a partir de leituras/hints (o insumo é o rótulo da **proposta de geometria**).

## Critérios de aceite

1. Mesmo `VisionProposalSet` → mesmas sugestões na mesma ordem (determinismo, teste).
2. Sugestão não confirmada não produz declaração, candidata nem efeito em rota nenhuma —
   teste que lê o job inteiro após gerar sugestões e não vê mudança.
3. Recusa exige motivo por escrito, fica registrada e a sugestão recusada não reaparece em
   recomputação (o id determinístico é o elo).
4. Pelo menos um caso com rótulo errado de propósito (a «grade B» que é o balão C espelhado),
   provando que a sugestão é editável/recusável antes do ato.
5. Sem rótulo nenhum no `VisionProposalSet`, a rota responde vazia e nada mais muda.

## Validação

```text
baseline: make check && make test verdes na main (registrar o resultado real antes de mudar)
required: uv run pytest tests/core tests/api -x
required: make check && make test
```

## Riscos conhecidos

- Rótulos do modelo variam de forma ("B" × "grade B") — este produtor **não** decide a
  normalização sozinho: o agrupamento aqui é por rótulo igual; a constante compartilhada
  nasce na T4 e esta tarefa a adota quando existir (registrar como dependência de constante,
  não de código).

## Resultado

Entregue em 2026-09-04. Produtor novo em
`services/worker/src/croquito_worker/review_element_suggestions.py`
(`suggest_review_elements`), não em `packages/core`: a entrada é `VisionProposalSet`, que
mora em `croquito_worker` — e `packages/core` nunca depende de `croquito_worker` (a direção
é a oposta). Agrupa propostas pelo `label` exato (`_label_group_key`, função nomeada para a
T4 trocar a normalização num lugar só); grupo de UMA proposta já é sugestão válida (o rótulo
é sinal explícito do modelo, diferente dos sinais fracos — procedência/proximidade — de
`element_proposals.py`, que exigem >=2). `suggestion_id` é o hash de `(job_id, proposal_ids)`
(molde `element_proposals._proposal_id`); `job_id` entra no hash porque `VisionProposal.id`
só é único DENTRO de um job.

Duas rotas novas no molde de `GET/POST .../elements/proposals` (F-047 T6), com prefixo
`/review/` (T2): `GET /v1/jobs/{id}/review/elements/suggestions` (leitura aberta ao tenant)
e `POST .../suggestions/{suggestion_id}/rejections` (papel profissional + `Idempotency-Key`
+ motivo ≥3 caracteres). Recusa persiste em `ReviewElementSuggestionRejectionRecord`
(migration `0032`, aditiva/forward-only, gêmea de `element_proposal_rejections`); proposta
já coberta por declaração ATIVA (`element_declarations_json`) não é sugerida, e volta a ser
sugerida se a declaração for revogada. Trio de superfície atualizado: `api.ts`,
`API_CONTRACT.md`, `openapi.snapshot.json` (`make openapi-snapshot`, diff só aditivo).

19 testes novos: 8 em `tests/worker/test_review_element_suggestions.py` (produtor puro —
determinismo/ordem, sem rótulo, já declarada, grupo de 1, rótulo errado de propósito ainda
sugerido, vazio, id depende do job) e 11 em `tests/api/test_review_element_suggestions.py`
(rota + recusa — listagem `unresolved`, nenhum efeito até confirmar, já declarada não
reaparece, rótulo errado recusável sem nada escrito, recusa não reaparece, id nunca
ofertado, papel/idempotência, motivo curto, `PROPOSALS_NOT_READY`, outro tenant).

Dois portões exaustivos existentes precisaram aprender sobre a superfície nova (não são
testes novos, são os mesmos portões da F-047 T6 estendidos): `tests/api/test_idempotency_operations.py`
ganhou `suggestion_id` em `_FIELD_MAX_LENGTHS` (lido da coluna, molde de `proposal_id`) e
`tests/api/test_migrations.py` ganhou `review_element_suggestion_rejections` no conjunto de
tabelas pós-baseline esperadas — os dois reprovavam sem a atualização, achados pela própria
suíte, não por inspeção.

Nenhum desvio do contrato. Migração aplicada e verificada contra `Base.metadata`
(`alembic check` sem diferença) no Postgres local (`croquito-local-postgres`);
`tests/api/test_migrations.py` (16 testes, exige `CROQUITO_TEST_POSTGRES_URL`) verde contra
o mesmo banco.
