# F-051 · T7 — Evidência de navegador e o caso real

Feature: [F-051](../feature.md) · Plano: [plan.md](../plan.md) · Estado: **Entregue**  
`feature_id: F-051` · `task_id: T7` · `depends_on: T5, T6`

## Objetivo

Fechar a feature com as duas provas que o contrato exige: a evidência de navegador da tela
nova (`BROWSER_REQUIRED`, critério 5) e a cadeia completa do caso da cota-balão exercitada de
ponta a ponta — preparando o material do **gate 3** (aceite humano contra o job real do
Toca), que é ato do dono, não desta tarefa.

## Escopo

- Evidência de navegador sobre o stack local (`make dev-services && make db-init && make
  dev`), com fixture sintética no padrão do corpus: leitura com hint "B", elemento declarado,
  candidata por identidade, confirmação pelo portão, traçado, cena com `element_ref`.
  Capturas + passos gravados em `evidencia/` da feature (padrão F-047).
- Cobertura e2e in-process do caminho feliz e do critério 2 (hint "E" sem casamento) no molde
  de `tests/e2e/test_full_flow.py`.
- Registro em `evidence.md` da feature (baseline, builders, validações, PRs).

## Fora de escopo

- O aceite humano do caso real (gate 3) — esta tarefa **prepara** o roteiro e o ambiente;
  quem aceita é o dono, sobre o job `01a068ef` local dele.
- Corrigir defeitos achados fora do escopo da F-051 — abrir issue, não consertar em silêncio.

## Critérios de aceite

1. Evidência de navegador mostra, em sequência: o hint na leitura, a declaração do elemento,
   o grupo "Pela identidade" no seletor, a confirmação, e a cena com a entidade identificada
   — os estados do DAP exercidos de verdade, não os do mock.
2. E2e prova o critério 1 do contrato em fixture sintética: a leitura com hint casando entra
   no solver como constraint (resíduo na resposta do traçado), e a entidade da cena carrega
   ref e rótulo.
3. E2e prova o critério 2: hint sem casamento → comportamento de hoje.
4. `evidence.md` consolidado com atribuição por tarefa (sem fundir builders).

## Validação

```text
baseline: make check && make test verdes na main (registrar o resultado real antes de mudar)
required: uv run pytest tests/e2e -x
required: make check && make test
```

## Human gates

- **Gate 3 da F-051**: aceite final contra o caso real do Toca (critério 1 do contrato) —
  ato do dono, com o roteiro desta tarefa em mãos. A feature não é `DONE` sem ele.

## Resultado

Entregue em 2026-09-04.

**Dez capturas** em [`evidencia/`](../evidencia/README.md), do stack local com login real de
Keycloak, exercendo a sequência inteira do DAP sobre fixture sintética: o hint na leitura, o
seletor que só tem "anotação" antes da identidade, o ato de declarar, o `EL-001` cunhado com
carimbo por papel, o `<optgroup>` "Pela identidade" com as duas propostas, a confirmação pelo
portão de sempre, o hint "E" que não casa (com a frase que diz o que falta), a cota-balão
amarrada a uma forma no traçado, a órfã sem vão, o resíduo com **três** cotas conferidas, e a
cena nascendo com `◇ EL-001 · B · → alimenta a medição`. Zero erros de console.

**Um e2e novo**, `test_a_cota_balao_com_hint_vira_restricao_e_a_orfa_segue_como_hoje`, no
molde de `tests/e2e/test_full_flow.py`: ele **estende** o da T5 em vez de repeti-lo — prova a
relação causal que faltava (o portão **recusa** a confirmação da cota-balão antes da
declaração e a aceita depois), leva a cota até `applied_spans` com eixo e valor, e carrega o
controle do critério 2 na mesma corrida (a leitura com hint "E" não ganha candidata, e o
conjunto das de proximidade sai idêntico). `tests/bundles.py` ganhou o parâmetro `balloons`,
desligado por padrão.

**O roteiro do gate 3** ([`ROTEIRO-GATE-3.md`](../evidencia/ROTEIRO-GATE-3.md)) foi validado
passo a passo contra a fixture — cada etapa aponta a captura que a mostra. Ele registra, como
risco declarado, que o `C=56,00` real é o **fecho** do elemento e o traçado amarra vão: se o
solver recusar a cota, é achado novo, não falha do caminho da identidade.

**Desvios conscientes**, os dois de registro e declarados aqui: (1) os contratos da T2 e da
T5 diziam "Pendente" com o código já mergeado na `main` — corrigidos para "Entregue" junto
deste consolidado, porque um `evidence.md` com atribuição por tarefa não pode citar como
pendente o que a `main` carrega; (2) o `make check` estava **vermelho no baseline** por
`tests/core/test_scene.py:501` (mypy), regressão do PR #168 — **não foi consertado** (área
alheia) e virou a [issue #171](https://github.com/biahflow/croquito/issues/171).
