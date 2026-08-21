# F-029 / T3 — Eval de associação com gate + relatório de calibração

- Feature: [F-029](../feature.md) · Plano: [plan.md](../plan.md)
- Papel: builder · Esforço relativo: M · Depende de: T1, T2
- Pode rodar em paralelo com T4 (grupo declarado no plano; áreas disjuntas)

## Objetivo

Duas ferramentas novas no CLI `croquito-demo`: `association-eval` (gate
determinístico sobre fixture sintética — zero auto-associação errada) e
`calibration-report` (replay local das revisões com decisão humana: shadow ×
verdade, tabela threshold × taxa × erro). O relatório instrui a escolha
humana do threshold; a ferramenta nunca escolhe.

## Fontes a ler antes de editar

- `AGENTS.md` (raiz) e `services/worker/AGENTS.md`.
- `services/worker/src/croquito_worker/vision_eval.py` — molde inteiro:
  `VisionEvalReport` (21-33), fixture programática via
  `croquito_worker.synthetic` (não há pasta de fixtures estáticas — a
  fixture nasce em código), thresholds hard-coded (135-141), `passed` como
  AND (152-158), report JSON (160-167).
- `services/worker/src/croquito_worker/cli.py` — registro de subparser
  (28-32) e despacho (680-683) do `vision-eval`, como molde.
- `Makefile` — alvos `vision-eval` (87-88) e `solver-eval` (93-94).
- `services/worker/src/croquito_worker/association_confidence.py` (T1) e a
  coluna shadow (T2).
- `services/worker/src/croquito_worker/solver_eval.py` (151-155) — para
  entender o que ELE não mede (associações hardcoded) e não repetir.

## Escopo

1. `association-eval`: fixture sintética programática com gabarito de
   associação conhecido (incluindo pelo menos um caso ambíguo por proximidade
   e um por orientação); roda propostas → leituras → score de T1; gate:
   **zero** associação errada acima do threshold do gate + recall mínimo
   declarado; report JSON + `passed`; exit code ≠ 0 quando reprova.
2. `calibration-report`: lê as revisões locais (banco do stack via
   `CROQUITO_DATABASE_URL`, mesmo caminho de leitura da API) que tenham
   decisão humana E shadow gravado; emite tabela threshold ×
   (auto_association_rate, review_rate, taxa de erro contra a decisão
   humana) em JSON + texto legível; nunca escreve nas revisões; dados reais
   ficam em `output/` (fora do Git, retenção 7 dias).
3. Make targets: `association-eval` (entra no fluxo de evals padrão) e
   `association-calibration` (local, NUNCA CI — mesmo padrão do
   `valuation-parity`).
4. Testes: gate reprova quando uma associação errada passa; relatório sobre
   fixture de banco em memória com decisões conhecidas; determinismo.

## Fora de escopo

Chamadas pagas; escolha de threshold; qualquer decisão automática; CI com
dados reais; mudança em `vision_eval.py`/`solver_eval.py`.

## Critérios de aceite

1. `make association-eval` verde na fixture sintética; sabotagem da fixture
   (associação errada plantada) reprova — coberto por teste.
2. `calibration-report` produz a tabela threshold × taxa × erro sobre
   revisões locais e recusa com mensagem clara quando não há revisão com
   decisão humana + shadow.
3. Exit codes: 0 aprovado, 1 reprovado, 2 entrada inválida (padrão do CLI).
4. `make check` e `make test` verdes.

## Baseline

`main` com T1+T2 integradas, portões verdes. Falha nova em área não tocada:
parar e reportar.

## Validação (comandos reais)

```bash
make check
make association-eval
uv run pytest tests/worker/test_association_eval.py
make test
```

## Gates e relatório

A escolha do threshold a partir do relatório é gate humano REGISTRADO NO
PLANO, fora desta task. Encerrar com `BUILD REPORT` completo
(`docs/engineering-os/agents/builder.md`).
