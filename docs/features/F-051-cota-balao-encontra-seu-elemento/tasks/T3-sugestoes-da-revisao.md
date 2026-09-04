# F-051 · T3 — As sugestões assistidas da revisão

Feature: [F-051](../feature.md) · Plano: [plan.md](../plan.md) · Estado: **Pendente**  
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
