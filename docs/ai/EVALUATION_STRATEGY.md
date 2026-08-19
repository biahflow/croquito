# Estratégia de avaliação

Status: Accepted for MVP  
Responsável: AI Engineering / Domain Reviewer  
Última revisão: 2026-08-13

## Objetivo

Medir se o sistema reduz trabalho sem introduzir erro técnico confiante. Uma média
única de “acurácia” é insuficiente.

## Conjuntos

- Golden: Guaxindiba, Toca e Raul Campelo, aprovados pelo domínio.
- Regression: todas as 16 páginas, com expectativas de estágio e falha segura.
- Synthetic: números, unidades, rotações, baixo contraste e conflitos gerados sem
  dados de clientes.

## Métricas

### Extração

- Exact match de `raw_text` normalizado.
- Numeric field accuracy.
- Unit accuracy.
- Target association accuracy.
- Region recall.
- Schema compliance.

### Segurança de decisão

- False-confident error rate: medida errada auto-confirmada.
- Unresolved recall: ambiguidades corretamente bloqueadas.
- Invented measurement count: meta zero.
- Hidden assumption count: meta zero.

### Geometria/CAD

- Confirmed dimension preservation: meta 100%.
- Topology validity.
- Entity/layer correctness.
- DXF audit success.
- Approximate entities corretamente rotuladas.

### Produto

- Tempo até primeiro rascunho.
- Tempo e ações de revisão.
- Percentual de entidades aceitas sem edição.
- Custo por página e por aprovação.

## Gates de mudança de IA

Uma mudança pode avançar quando:

1. Schema compliance permanece 100% nos golden cases.
2. Invented measurement e hidden assumption permanecem zero.
3. False-confident errors não aumentam.
4. Nenhum golden criterion regride.
5. Ganhos e perdas de custo/latência estão registrados.
6. Domain reviewer aprova diffs materiais.

Uma melhoria média não compensa regressão crítica em caso difícil.

## Execução

- Evals determinísticas e fixtures sintéticas rodam em CI.
- Evals com APIs pagas rodam sob autorização, em pipeline separado e com budget.
- Responses são cacheadas por digest para comparação reproduzível durante a
  janela autorizada.
- Cada run grava dataset version, model IDs, prompt hashes, code revision e métricas.

## Relatório

Comparações mostram baseline/candidate por caso e por campo, com links para diffs
internos autorizados. Nenhum relatório público contém imagens ou textos reais.

## Baseline inicial

A baseline é criada antes de otimizar prompts. Resultados sem gabarito de domínio
são marcados “observational” e não podem sustentar alegação de precisão.

## Gate atual de propostas CV

`make vision-eval` gera uma folha sintética com quatro bordas e círculo de centro
conhecido. O gate exige:

- recall de linhas maior ou igual a 75%;
- recall e precisão de candidato de círculo iguais a 100%;
- `unresolved_rate=100%`;
- `non_exportable_rate=100%`.

A baseline corrente passa com 100% em todos esses itens. Esse resultado mede
somente a fixture sintética. Nos documentos reais, os resultados continuam
`observational_only` até existir gabarito aprovado pelo domínio.

## Gate atual de revisão e solver

`make solver-eval` cobre uma fixture retangular com largura, altura e raio
conhecidos. O gate exige:

- bloqueio da revisão antes da aprovação;
- aprovação ligada ao UUID exato do rascunho;
- nova revisão após aprovação;
- resíduos métricos iguais a zero;
- auditoria DXF aprovada;
- registro de aprovação dentro do ZIP.

O gate corrente passa em todos os checks. Ele valida contratos e geometria
determinística, não a transcrição automática nem precisão nos casos reais.

## Gate do degrau em contorno (extração de geometria)

`make extraction-eval-degrau` mede a extração de geometria (`geometry-extraction`) sobre
uma fixture sintética com um contorno em degrau: dois trechos paralelos em offsets
diferentes, ligados por um jogo perpendicular curto — a forma que motivou a `2.0.2`
([Prompt Contracts](PROMPT_CONTRACTS.md)).

### Dois modos, um só caminho de código

- **Offline (CI).** O braço fixture valida mecanismo e métrica sem chamar nenhum
  provider — o harness da fixture determinística é entregue por uma tarefa própria do
  plano, em paralelo a esta; `make extraction-eval-degrau` é o comando de referência.
  Ele mede se o degrau vira uma única `polyline` com os vértices do jogo, não duas
  `line` retas nem uma reta achatada.
- **Pago (local).** Sobre o mesmo mecanismo, com o modelo real atrás do teto de gasto
  autorizado — mede o que o modelo de verdade devolve, não a fixture.

### Honestidade

O modo fixture valida mecanismo e contrato, não precisão de leitura em prancha ou
documento real: é o teto artificial da métrica, não evidência de desempenho de modelo
algum. `geometry-extraction@2.0.2` foi **avaliado e promovido**: a rodada paga comparativa
contra o baseline `2.0.1`, com aprovação humana explícita, está registrada em
[Model Routing — Eval comparativa executada (degrau em muro de contorno,
geometry-extraction@2.0.2, 2026-08-19)](MODEL_ROUTING.md).

### Registro antes da corroboração (2026-08-19)

`run_extraction_eval` passou a rodar `register_to_ink` sobre as propostas ANTES de
`corroborate_with_ink`, na mesma ordem e config que
`provider_review.build_provider_review_snapshot` usa na cadeia real — **sempre**, não só
neste gate do degrau. Sem isso a eval media deslocamento GLOBAL de enquadramento do
modelo (a folha inteira ancorada alguns pixels fora do canônico), não a forma proposta; a
produção corrige esse deslocamento antes de qualquer leitura chegar à revisão humana, e
um gate que não registra reprova algo que o usuário final nunca vê. Achado real: a
primeira rodada paga do gate do degrau devolveu o muro estruturalmente certo
(`geometry-extraction@2.0.2`) com `corroborated_rate=0.5` sem registro — abaixo da
tolerância de tinta de 9 px por causa de ~12 px de deslocamento global — e
`step_preserved=True`/`corroborated_rate=1.0` depois de registrar.

**Números de `corroborated_rate`/`ink_coverage_mean` de antes desta mudança não são
comparáveis aos de depois.** As rodadas históricas registradas em
[Model Routing](MODEL_ROUTING.md) foram medidas sem este registro prévio; uma promoção ou
rejeição de modelo que dependa desse número precisa ser remedida sob o pipeline atual
antes de ser comparada a um resultado novo.

## Gate do matcher de código SCO (medição, M7)

O casamento item→código tem golden set próprio
(`tests/valuation/golden/matcher-golden-v1.json`): rótulos reais da Toca + gabarito
sintético, com dois gates independentes — `lexical_gate` (mede o fallback permanente) e
`hybrid_gate` (`recall@20 = 100%` no matcher híbrido,
[ADR-0021](../adr/0021-hybrid-sco-code-retrieval.md)). Casos cuja variante não é
discriminável pelo rótulo usam oráculo por **família** de códigos com `family_reason` e
`human_choice` — o matcher responde pela família; a variante é decisão humana com a
prancha. Os ranks por braço (léxico, semântico, fundido) ficam fixados no golden:
piorar um rank conhecido reprova o teste. A parte real do golden roda local-only
(`skipif` sem o catálogo real, como o `parity`); o CI mede a parte sintética. Resultado
vigente no catálogo real: 12/12, contra 4/12 do léxico puro — a tabela completa vive em
[Model Routing](MODEL_ROUTING.md).

## Gate atual da extração de legenda e do refino de código (medição)

`make valuation-extraction-eval` avalia os dois estágios pagos do contexto de medição
sobre a mesma prancha sintética: a **extração da legenda quantificada** e o **refino da
shortlist de código SCO**. O relatório
(`output/valuation-extraction-eval/valuation-extraction-eval.json`) traz um bloco por
braço, os checks de gate e o veredito `passed`.

### Dois modos, um só caminho de código

- **Offline (CI).** Sem `--arm`, a eval roda o braço fixture embutido, cujas saídas de
  provider derivam das mesmas constantes que desenham a prancha (`SYNTHETIC_LEGEND_ROWS`)
  e do mesmo gabarito de código do `demo`. Nada sai da máquina e nada é cobrado.
- **Pago (local).** Com `--arm nome=provider:modelo` (repetível), os braços reais entram
  pela mesma fábrica dos demais comandos pagos, que exige
  `CROQUITO_AI_MAX_ESTIMATED_COST_USD`. Nenhum teste roda nesse modo, e a comparação
  entre modelos é decisão humana sobre o relatório.

Os dois modos passam pelo mesmo mapeamento observação→takeoff e pelo mesmo refino do
domínio. O que muda é quem responde ao pedido.

### Métricas por braço

- `legend_recall`: fração das linhas do gabarito reproduzidas com rótulo, unidade e
  quantidade — a linha ilegível só casa com item ambíguo **sem** quantidade. O rótulo casa
  na forma pura **ou** na impressa (na prancha ele vem colado à nota, `ALAMBRADO SINTETICO
  (h=1,20m)`): transcrever o que está no papel é acerto, não erro, e a eval não pode punir
  fidelidade. O gate do M3 (`make valuation-eval`) segue estrito no rótulo puro, porque lá
  o extrator é a fixture do próprio repositório.
- `quantity_accuracy`: fração das linhas legíveis cuja quantidade saiu exata.
- `sco_top1` / `sco_top3`: acerto do código confirmado no gabarito, depois do refino.
- `lexical_sco_top1` / `lexical_sco_top3`: a mesma medida **sem** refino, no mesmo
  relatório. Refino que não supera a baseline lexical não justifica a chamada paga.
- Custo, tokens e latência de cada estágio, mais o `suggester_version` publicado.

### Checks de gate (exercitados, não descritos)

- `no_item_born_confirmed`: nenhum item nasce confirmado na extração.
- `all_items_matched_gabarito`: todo item extraído corresponde a uma linha do gabarito.
  Um item que não corresponde não é revisado nem medido — ele reprova aqui, em vez de a
  eval decidir sozinha o que ele seria.
- `real_arm_without_budget_refused`: sem teto de gasto declarado, a fábrica de braço pago
  recusa antes de qualquer chamada.
- `tampered_image_refused`: página que não pertence ao manifest não é autorizada.
- `refinement_outside_shortlist_refused`: refino que devolve código fora da shortlist
  recusa com `REFINEMENT_CODES_MISMATCH` — o provider reordena, nunca substitui.

Thresholds do gate: `legend_recall = 1.0` e `sco_top1 = 1.0`. Eles valem para todo braço,
inclusive o real; aprovar ou não um modelo pago continua sendo decisão humana registrada.

### Honestidade

O modo fixture valida **mecanismo e contrato**: que o mapeamento não perde linha, que a
dúvida vira item ambíguo sem quantidade, que o refino só permuta e que os gates de gasto e
de allowlist recusam o que prometem recusar. Ele **não** mede precisão de leitura de
prancha real de cliente — o braço fixture é o teto artificial da métrica, não evidência de
desempenho. Precisão só sai da rodada paga, sobre documento autorizado, com o custo
registrado.
