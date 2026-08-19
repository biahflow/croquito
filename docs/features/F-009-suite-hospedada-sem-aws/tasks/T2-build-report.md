# T2 — BUILD REPORT

```text
BUILD REPORT

Status: BUILD_COMPLETE

Files changed:
  - services/worker/src/croquito_worker/provider_review.py — helper `_execute_with_fallback`,
    inversão de âncora (Anthropic primário, OpenAI reserva/contraparte), modo braço único
    com toda leitura `AMBIGUOUS`, notas de fallback no pacote, pacote montado depois da
    geometria para a nota de fallback da geometria chegar às notas de segurança.
  - tests/worker/test_providers.py — 7 testes novos de fallback (8 itens, um parametrizado),
    helpers `_CountingAdapter`/`_fallback_suite`/`_distinct_reading`; teste de lineage dual
    passa a exigir ordem `[anthropic, openai]` e `extractor="anthropic+openai"`; teste de
    região ambígua passa a mutar o braço primário (anthropic), que é quem faz o survey.
  - tests/worker/test_local_queue.py — dois testes existentes que afirmavam a ordem antiga:
    lineage `openai` → `anthropic`; injeção de `BUDGET_EXCEEDED` no survey migrada do braço
    openai para o braço primário anthropic (no openai o survey deixou de ser chamado, e o
    teste passaria a verde por não exercitar nada).

Validation executed:
  - make check → verde (ruff check, ruff format --check, mypy strict, check_docs,
    schema_export --check, contracts:check, tsc -b + vite build, terraform fmt -check).
  - make test → verde: pytest 1463 passed, 10 skipped; vitest 29 arquivos / 529 testes.
  - baseline declarado no contrato (make check/make test verdes após T1) confirmado antes
    da edição pela suíte alvo; as duas reprovações intermediárias em
    tests/worker/test_local_queue.py foram causadas por esta task e estão corrigidas.

Validation skipped: none

Unavailable capabilities: none

Assumptions:
  - `BUDGET_EXCEEDED` re-levanta em QUALQUER braço, inclusive na extração dupla (onde não há
    fallback envolvido): o teto é do job, não do braço, e continuar em modo braço único
    esconderia uma degradação causada por orçamento que `local_queue.py` já trata como falha
    do job (`AI_BUDGET_EXCEEDED`).
  - Quando os dois braços da extração falham, propaga a exceção do SEGUNDO braço (openai);
    o contrato exige propagação, não um código específico.
  - A primeira nota de segurança do pacote passa a ser condicional: em modo braço único ela
    diz "Leitura de um braço único sem comparação; revisão humana é obrigatória." — manter
    "Leituras dos dois providers…" afirmaria uma comparação que não aconteceu. Nenhum teste
    ou consumidor lia essa string (verificado por grep em .py/.ts/.tsx).

Remaining risks:
  - Fallback de survey e de geometria trocam o MODELO que observou a página sem trocar o
    prompt; a nota declara a troca, mas a diferença de qualidade entre os braços só será
    medida com eval comparativa (fora do escopo da T2, sinalizado para T4/F-010).
  - O modo braço único degrada TODA leitura para `AMBIGUOUS`, o que aumenta o trabalho de
    revisão humana num job já degradado. É o comportamento pedido e é conservador.
  - Custo: um fallback dobra o número de chamadas da tarefa afetada dentro do mesmo teto
    compartilhado; a aritmética de teto/timeout continua sendo risco declarado do plano.

Human decisions required: none dentro do escopo (ADR-0035, segredos, entitlement e o
merge/deploy seguem nos gates da feature).
```

## Desvios conscientes do contrato

1. **`tests/worker/test_local_queue.py` foi editado.** O contrato lista em `WRITE` apenas
   `provider_review.py` e `tests/worker/test_providers.py`, mas o `Scope` diz "somente
   `provider_review.py` e testes". Dois testes daquele arquivo afirmavam a ordem antiga
   (lineage ancorado em openai) e injetavam a falha de teto no braço que deixou de ser o
   primário do survey; sem a correção, um deles reprovaria e o outro passaria a verde sem
   exercitar o caminho que descreve. São ajustes de asserção/injeção, não de comportamento.
2. **Ordem de construção do `ReviewPacket`.** O pacote passou a ser montado depois da
   extração de geometria. Sem isso, a nota `PROVIDER_FALLBACK_GEOMETRY_EXTRACTION_OPENAI`
   nasceria depois do pacote e não chegaria às notas de segurança — a matriz do contrato
   exige a nota NO PACOTE. A ordem das chamadas a provider não mudou.

## Oportunidades vistas e NÃO implementadas (fora de escopo)

- `local_queue.py` poderia distinguir, no log estruturado do job, que a revisão saiu
  degradada (contagem de notas `PROVIDER_FALLBACK_*`), hoje isso só aparece no pacote.
- A API não expõe nenhum campo dedicado de degradação; a web mostra as notas de segurança
  como texto. Um marcador explícito de "pacote degradado" ajudaria a revisão.
- O `PROVIDER_READING_COUNT_DISAGREEMENT` continua sendo uma nota de contagem sem dizer
  qual braço leu a mais; nomear o braço tornaria a divergência acionável.
