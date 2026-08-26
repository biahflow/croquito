# F-038 T4 — `CalcMatrix` e dependência sem ciclo

Issue: [#76](https://github.com/biahflow/croquito/issues/76) · Estado: **entregue**

## Goal

Dar forma à matriz elemento x serviço que o [ADR-0053](../../../adr/0053-cardinalidade-n-n-elemento-servico.md)
descreve: um serviço soma parcelas de vários elementos, e o transporte depende da quantidade
de outro serviço. Sem esse modelo e o normalizador, os builders (T6) não têm como iterar
serviços — hoje eles recusam qualquer item com mais de um código
(`CALC_PACKAGE_NOT_SUPPORTED` / `ESTIMATE_PACKAGE_NOT_SUPPORTED`).

## Leia antes de editar

- [ADR-0053](../../../adr/0053-cardinalidade-n-n-elemento-servico.md), decisões 1 e 4.
- T3 (#75): os campos de contribuição já vivem no `CalcBlock`
  (`source_item_id`, `basis`, `derived_from_code`) — a matriz reusa esse invariante.
- T11 (#83): `haulage.haulage_operands` já materializa a quantidade da origem como operando
  literal; a mesma forma que a parcela `DEPENDENT` produz.

## Mapa verificado

`CalcPlan` (`calc.py:67`) é indexado **por item** e é lido de arquivo pelo CLI; estendê-lo
com uma união por eixo exigiria validador `mode="before"` frágil. Fica **intocado**. Nasce
o irmão `calc_matrix.py`, indexado **por serviço**. `resolve_calc_matrix` não é chamado por
ninguém ainda: é a costura que T6 consome ao remover os portões temporários.

## Scope

Módulo novo `packages/valuation/src/croquito_valuation/calc_matrix.py`:

- `CalcContribution`, `ServiceContributions`, `CalcMatrix` + `CALC_MATRIX_SCHEMA_VERSION`.
- Guarda de ciclo **na leitura** (model validator, Kahn sobre `code → depends_on_code`):
  `CALC_MATRIX_SELF_DEPENDENCY`, `CALC_MATRIX_DEPENDENCY_CYCLE`, mais
  `CALC_MATRIX_DUPLICATE_CODE`.
- `resolve_calc_matrix(...) -> ResolvedMatrix`: regime legado byte-idêntico (reusa
  `calc.build_calc_blocks`, sem fusão) e regime da matriz (fusão por código, ordem
  topológica como numeração, parcela `DEPENDENT` materializada com a quantidade resolvida do
  serviço-alvo como operando literal e `derived_from_code` como proveniência).
- Recusas de build espelhadas por prefixo de cadeia (`error_prefix`):
  `{CALC,ESTIMATE}_MATRIX_DEPENDENCY_UNKNOWN` (alvo fora do boletim) e
  `..._UNPRICED` (alvo sem código confirmado).

## Out of scope

- Ligar `resolve_calc_matrix` aos builders e remover os portões `*_PACKAGE_NOT_SUPPORTED`:
  é T6 (#78).
- Persistência/migração `0019_calc_matrix` e rotas `/v1`: T8 (#80). Tela: T9 (#81).
- `CalcMatrix` **não** entra no `Valuation` exportado — por isso `make contracts` gera zero
  diff e os goldens de planilha não se movem.

## Acceptance criteria

- Ciclo A→B→A recusa na **desserialização** do artefato, não só no build.
- Auto-referência recusa.
- Ordem topológica determinística (empate pela primeira aparição).
- Regime legado byte-idêntico ao `build_worksite_bulletin` de hoje.
- `make check` e `make test` verdes.

## Validation

```bash
uv run pytest tests/valuation/test_calc_matrix.py -x
uv run pytest tests/valuation/test_calc.py tests/valuation/test_content_digest.py \
             tests/valuation/test_canonical_golden.py
make contracts   # zero diff em packages/contracts (a matriz é backend-only nesta tarefa)
make check && make test
```

## Report

**Dois desvios do texto da issue, porque a execução de T3/T11 o precede:**

1. **`CalcQuantityKind` não existe.** O exemplo da issue usava
   `CalcOperand(..., kind=CalcQuantityKind.VOLUME)`; T3 decidiu não criar o enum. O operando
   materializado é `CalcOperand(name="QUANTIDADE BP04050350(/)", value=…)`, sem `kind`.
2. **`depends_on_code` materializa em `derived_from_code`.** A issue já previa
   "`derived_from_code` viaja como proveniência": a aresta de dependência (`depends_on_code`,
   que guia o topo-sort) vira o campo de proveniência que T3 criou no `CalcBlock`.

**Reconciliação byte-idêntico x "contribuição FULL":** a issue diz que no regime legado cada
item "vira uma contribuição FULL". Mas o bloco de hoje nasce com `basis=None`; carimbar
`FULL` mudaria o bloco (e exigiria `source_item_id`), quebrando a igualdade. **Byte-idêntico
vence**: o regime legado reusa `calc.build_calc_blocks` sem tocar em `basis`. O "FULL" é a
semântica (a quantidade inteira vai para o único código), não um carimbo no bloco.

**Decisão de escopo — teto de `PARTIAL` adiado para T6.** T3 direcionou a conferência
`PARTIAL ≤ quantidade do item` (e nota obrigatória) a "builder (T4/T6)". Mantida em T6, onde
o builder já itera serviços com o item completo em mãos; T4 fica no aceite literal da issue.
