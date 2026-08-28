# F-045 — Evidência

## Origem

A lacuna foi exposta em 2026-08-28, na conversa sobre a revisão 2 do pacote de design da
[F-044](../F-044-precedente-de-codigo/feature.md). Ao decidir *marcar* o código minoritário,
a pergunta seguinte apareceu sozinha — e se a pessoa aceitar com ele dentro? — e a resposta
verificada foi: não há volta.

O que se conferiu antes de afirmar isso, e vale como linha de base:

- as rotas de `code-assignments` são `GET`, `decisions` e `closures`; **não existe remoção**;
- `_ensure_batch_decidable` recusa re-decidir um par com `ASSIGNMENT_ITEM_ALREADY_DECIDED`;
- não há rollback de revisão em lugar nenhum da `/v1`;
- o **caminho de escape existe e funciona**: a busca da etapa casa por código, não só por
  descrição, e foi testada contra a função real (`catalog_search.search_catalog`) com o
  formato SCO — `'BP09100050(B)'`, `'BP09100050'` e `'bp09100050'` devolvem o mesmo código.
  Recusar o precedente, portanto, custa cliques; aceitar errado custava a praça.

## Human Gates

| Gate | Estado |
| --- | --- |
| [ADR-0061](../../adr/0061-revogacao-de-codigo-confirmado.md) — semântica da revogação | **`Proposed`**, aguardando aceite |
| [Design Approval Package](mock/README.md) revisão 1 | **Aguardando aprovação** |
| Unknown 1 — revogar depois da aprovação do orçamento | **Aberto**; a implementação recusa provisoriamente (ADR-0061 D7) |

A implementação foi autorizada pelo dono na mesma conversa. Nada nela é irreversível: rota
nova, campo do conjunto com default vazio, nenhuma migração.

## O que foi entregue

**Domínio** (`croquito_valuation.assignment`): `CodeAssignmentRevocationInput`,
`CodeAssignmentRevocation`, o campo `revocations` no `CodeAssignmentSet` e
`apply_code_revocation`. O par sai de `assignments`, o registro entra em `revocations`, o
fechamento do item cai, e o mesmo par volta a ser decidível. Regime `1.0.0` recusa.

**API**: `POST /v1/valuation-rounds/{id}/code-assignments/revocations` e a irmã em
`estimate-rounds`, com `Idempotency-Key`, `base_version` e as recusas do domínio. No
orçamento, **um efeito a mais na mesma transação**: `precedents.revoke_closure_precedent`
apaga a observação que o fechamento desta praça gravou para aquele par — só desta praça, só
de origem `round`.

**Tela** (`apps/web/src/orcamento`): `revogacao.ts` (módulo puro), `CaixaDeDesfazerCodigo` e
`ListaDeDesfeitos`, com o motivo obrigatório, as três linhas de efeito, o botão que muda de
nome quando o pacote está fechado, e a lista do que continua desfeito. Nenhuma cor nova.

## Três coisas que a execução descobriu

1. **A aprovação passaria por baixo.** O ADR-0046 amarra a assinatura ao *digest do
   orçamento*, e revogar não remonta o orçamento: o digest continuaria conferindo com os
   códigos já mudados, e o portão de exportação não veria nada. Virou a **D7** do ADR-0061 —
   recusa provisória, fail-closed, reversível com uma linha.
2. **Um par reconfirmado precisa sair da lista de desfeitos da tela**, ainda que o registro
   permaneça no conjunto. Mostrá-lo como desfeito ao lado dele mesmo confirmado diria duas
   coisas contrárias sobre o mesmo código.
3. **`_ensure_same_plate` só existia dentro do caminho do lote.** A revogação não tem lote, e
   a checagem de prancha não podia continuar amarrada ao caminho que a descobriu primeiro:
   foi extraída e passou a valer nos dois.

## Validação

| Portão | Resultado |
| --- | --- |
| `make check` | exit 0 |
| `make test` | 2843 pytest · 1462 web · 261 campo, todos verdes |
| Testes novos | 12 no domínio (`tests/valuation/test_assignment.py`), 9 na API (`tests/api/test_precedents.py`, `test_valuation_round_routes.py`, `test_estimate_round_routes.py`), 11 na tela (`apps/web/src/orcamento/revogacao.test.tsx`) |
| Contrato | `docs/architecture/API_CONTRACT.md` e `tests/api/openapi.snapshot.json` atualizados; o drift guard das rotas de `estimate-rounds` e a lista fechada da medição incluem as duas rotas novas |
| Rendido | os dois componentes renderizados com a folha real do app, conferidos em imagem (caixa com pacote fechado e lista de desfeitos) |

## O que continua aberto

- Os **três gates** da tabela acima.
- **Desfazer a rejeição de um item** — o ato inverso do outro lado, fora do escopo desta
  feature.
- **Rollback de revisão** — outra feature, para outro problema.
- **A tela da medição**: a rota irmã existe e é testada, mas a jornada de medição não recebeu
  a superfície; o pacote de design cobre só o orçamento.
