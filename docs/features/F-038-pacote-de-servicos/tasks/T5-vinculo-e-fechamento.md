# F-038 T5 — Vínculo com chave `(item_id, code)` e fechamento de pacote

Issue: [#77](https://github.com/biahflow/croquito/issues/77) · Estado: **em execução**

## Goal

Trocar a identidade da confirmação de código: de `item_id` para o par `(item_id, code)`. É
onde a cardinalidade do [ADR-0053](../../../adr/0053-cardinalidade-n-n-elemento-servico.md)
deixa de ser texto e vira tipo.

A troca cria, no mesmo ato, o problema que esta tarefa tem que resolver junto: hoje "a
orçamentista terminou este item?" se responde por "existe assignment para o item". Com N:N,
um item com um de seis códigos **pareceria pronto** e produziria boletim parcial em
silêncio. Por isso o par vem acompanhado do **fechamento explícito de pacote**.

## Leia antes de editar

- [ADR-0053](../../../adr/0053-cardinalidade-n-n-elemento-servico.md), decisão 2 (a
  identidade é o par, com fechamento) e a consequência declarada sobre a regra de unidade.
- [mock/README.md](../mock/README.md), decisões 1, 2, 4 e 5 — a interface aprovada. As
  decisões 3 (memória de cálculo na tela do orçamento) e 6 (parcela parcial declarada)
  dependem da matriz e **não** são desta tarefa.
- `packages/valuation/src/croquito_valuation/assignment.py` — `CodeAssignmentSet`,
  `CodeAssignmentBatch`, `_ensure_batch_decidable`, `_confirmed_assignment`, os dois
  `apply_code_assignments*`.

## Mapa verificado

A premissa 1:1 está em sete lugares, não em um:

| Lugar | Linha | O que afirma |
|---|---|---|
| `CodeAssignmentSet.validate_unique_items` | `assignment.py:1009` | um assignment por item |
| `CodeAssignmentBatch.validate_unique_items` | `assignment.py:945` | uma decisão por item por lote |
| `_ensure_batch_decidable` | `assignment.py:1118` | re-decisão do **item** recusa |
| `apply_code_assignments` | `assignment.py:1220` | `{input.item_id: input}` — um input por item |
| `apply_code_assignments_over_cascade` | `assignment.py:1315` | idem |
| `_confirmed_assignment` | `assignment.py:1165` | unidade divergente sem nota recusa sempre |
| `CodeAssignmentSet.schema_version` | `assignment.py:1000` | `Literal["1.0.0"]` |

**Os três builders quebrariam em silêncio.** `calc.py:213`, `estimate.py:543` e
`amendment_dossier.py:166` montam `{a.item_id: a for a in assignments.assignments}` — dict
que descarta todos menos o último assignment do item, sem avisar ninguém.

**"Pendente" é decidido no servidor.** Nenhum dos dois apps web tem lógica cliente de
pendência: `OrcamentoApp.tsx:3024` e `MedicaoApp.tsx:1626` fazem só
`codes?.pending_items ?? []`. A lista nasce em `round_view.pending_code_items`
(`round_view.py:140`). Fazer o pacote aberto aparecer como pendente é mudança de seis
linhas ali, e a tela herda o comportamento.

**Nada disso move `vd_`.** `_assignment_decision_id` (`assignment.py:1037`) já digere `code`
no payload: o par produz ids distintos sem uma linha de mudança. É propriedade a verificar,
não a construir.

## Scope

1. **Regime declarado pelo artefato.** `schema_version: Literal["1.0.0", "2.0.0"]`, com a
   constante em `"2.0.0"`. `1.0.0` mantém unicidade por item e proíbe `closures`, com
   comportamento byte-idêntico ao de hoje; `2.0.0` exige o par e admite fechamento.
2. **`ItemPackageClosure`** no conjunto e `ItemPackageClosureInput` no lote, com
   `_closure_decision_id` discriminado por `"kind": "package_closure"`.
3. **Códigos de erro**: `ASSIGNMENT_DUPLICATE_PAIR`, `ASSIGNMENT_REJECT_WITH_CONFIRMED`,
   `ASSIGNMENT_ITEM_ALREADY_CLOSED`, `ASSIGNMENT_DUPLICATE_CLOSURE`,
   `ASSIGNMENT_CLOSURE_WITHOUT_ASSIGNMENT`, `ASSIGNMENT_CLOSURE_NOT_SUPPORTED`,
   `ASSIGNMENT_BATCH_EMPTY`, `CALC_PACKAGE_NOT_CLOSED`, `ESTIMATE_PACKAGE_NOT_CLOSED`.
   `ASSIGNMENT_DUPLICATE_ITEM` e `ASSIGNMENT_ITEM_ALREADY_DECIDED` ficam, com significado
   novo no regime novo.
4. **Portão temporário nos builders**: `CALC_PACKAGE_NOT_SUPPORTED` /
   `ESTIMATE_PACKAGE_NOT_SUPPORTED` enquanto T4/T6 não os ensinam a iterar serviços.
5. **Regra de unidade** restrita ao item de código único.
6. **Rotas** `POST .../code-assignments/closures` nas duas jornadas, CLI, servidor local,
   fixtures demo, e a tela montando o pacote e fechando-o.

## Out of scope

- `CalcMatrix` e contribuição por par — são #76.
- Builders iterando serviços — é #78, e é o que remove o portão temporário.
- Memória de cálculo na jornada do orçamento e parcela parcial declarada — dependem da
  matriz (#81 sobre #76/#78).
- Migração `0019_calc_matrix` — é #80.

## Acceptance criteria

- Conjunto `1.0.0` relê e produz boletim byte-idêntico.
- Par duplicado recusa; item com pacote aberto recusa no boletim em `2.0.0`.
- Nenhum `vd_` histórico se move.
- Item recebe dois códigos em dois lotes, segue **pendente** entre eles, e só sai de
  `pending_items` depois do fechamento.
- `git diff --stat tests/valuation/golden` vazio.
- `make check` e `make test` verdes.

## Pitfalls

**O dict `{item_id: assignment}` é o inimigo.** Ele não falha: escolhe o último e segue.
Cada um dos três precisa virar índice de lista com recusa explícita.

**A regra de unidade não pode virar ruído.** Sob pacote, um elemento em m² alimenta
serviços em m³, kg e m; recusar sempre faria a orçamentista parar de ler a nota. Mas
afrouxar demais esconderia o erro real do regime espelho. Vale a regra do ADR: recusa quando
o item tem **exatamente um** código confirmado. Consequência aceita: um pacote montado em
lotes sucessivos passa por esse estado no primeiro lote, e ali a recusa ainda se aplica.

**Fechar por construção não é fabricar ato humano.** Ao carregar adiante assignments de um
conjunto `1.0.0`, o fechamento reusa a `ReviewerDecision` que já existe em cada assignment.
Sob `1.0.0` aquela confirmação *era* o fechamento — um código era o pacote inteiro. Inventar
uma decisão nova ali seria assinar no lugar de alguém.

**`closes_package: bool` na confirmação é a modelagem errada.** A rota posta uma decisão por
request; um pacote de seis nasce em seis atos. A flag exigiria saber de antemão qual é a
última.

## Validation

```bash
uv run pytest tests/valuation/test_assignment.py
uv run pytest tests/valuation/test_calc.py tests/valuation/test_estimate.py tests/valuation/test_amendment_dossier.py
uv run pytest tests/api tests/e2e tests/worker -k valuation
npm run web:check && npm run web:test
make openapi-snapshot && make contracts && make check && make test
make valuation-demo && make valuation-estimate-demo
git diff --stat tests/valuation/golden   # precisa sair vazio
```

## Report

*(preenchido ao encerrar)*
