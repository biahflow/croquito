# F-029 — Auto-associação de cotas por confiança calibrada (experimento local)

## Status

`DONE`

> **Aceite humano em 2026-08-28**, sobre o pacote de revisão em [evidence.md](evidence.md).
> Dívida declarada, não exercida: rodada local com a flag ligada no stack docker,
> calibração com os 7 PDFs reais (`make association-calibration`) e a escolha do threshold
> operacional a partir do relatório de calibração.
>
> T1–T5 executadas, revisadas linha a linha e integradas em 2026-08-21
> ([evidência](evidence.md)).

> Trilha de gates da mesma data: plano aprovado em sessão ([plan.md](plan.md),
> Task Contracts em [tasks/](tasks/)),
> [ADR-0041](../../adr/0041-decisao-de-ator-maquina-atras-de-flag-local.md)
> aceito (gate do T4), mock da vista de exceções aprovado (gate do T5) e os
> sete PDFs de calibração fornecidos em `output/levantamentos-calibracao/`.

> Especificada em 2026-08-21, por seleção humana, na conversa que comparou o
> produto com uma proposta externa de "Dimension Association Engine". As três
> decisões de escopo foram tomadas pelo usuário na mesma sessão: o modo
> automático cobre **leitura + associação**; a fatia 2 da
> [F-023](../F-023-survey-quality-score/feature.md) (score calibrado com
> V14–V17) é **absorvida** por esta feature; a calibração usa Guaxindiba real,
> fixtures sintéticas e PDFs adicionais de levantamentos fornecidos pelo
> usuário. Validação **exclusivamente local** (stack docker-compose), sem
> deploy em HML/GCP.

## Classification

Não é `INTERFACE_CHANGE` de superfície nova — precedente das F-023/F-025: a
mudança de tela entra na revisão existente, nos padrões visuais estabelecidos
(badges de linha, `batch-controls`, contadores). Gate humano específico: um
mock simples da vista de exceções antes da task web (padrão das rodadas
F-025/F-027).

## Priority

`HIGH` — selecionada pelo usuário em 2026-08-21 como próximo experimento de
produto, à frente do benchmark de OCR (Mistral/Gemini, condicionado à V17).

## Problem

O gargalo humano da revisão não é ler a cota — é dizer **a qual segmento cada
cota pertence**. Hoje 100% das leituras exigem toque humano duplo: a decisão
da leitura (`HumanDecision`) e a associação explícita `reading_id →
proposal_id` que o solver exige (`rectangle_solver.py` gera
`EXPLICIT_ASSOCIATION_REQUIRED` por leitura sem associação). O
[STATUS](../../STATUS.md) registra textualmente: associação determinística
"sem autoassociação, confirmação ou exportação".

Os sinais para decidir com confiança já existem espalhados e não são somados:

- a associação ranqueia só por `pixel_distance` e `visual_quality_score`
  (`association.py`) — sem orientação do texto, sem corroboração de OCR, sem
  campo de confiança;
- o fechamento de cadeias (`dimension_closure.py`, ligado pela fatia 1 da
  F-023) corrobora leituras e não alimenta associação;
- o solver sabe quando uma associação fecha a geometria (resíduos) e esse
  feedback não retorna como sinal;
- as rodadas reais V14–V17 do Guaxindiba são amostras de calibração já pagas
  e sem consumidor para este fim.

E não existe métrica: nenhuma eval mede taxa de associação correta
(`vision_eval.py` mede recall de propostas; `solver_eval.py` injeta
associações hardcoded).

## Desired Outcome

Três fatias, nesta ordem.

### Fatia 1 — score de confiança por cota (absorve a fatia 2 da F-023)

- Candidato de associação ganha sinais tipados novos além dos atuais:
  orientação do texto da cota vs. direção do segmento, corroboração de OCR
  (a confiança de leitura do braço de extração), participação em cadeia que
  fecha (`dimension_closure`), e feedback do solver quando disponível
  (resíduo da leitura aplicada).
- Duas confianças **distintas e nomeadas**, ambas determinísticas em 0–1:
  `reading_confidence` ("li 7,35 corretamente?") e `association_confidence`
  ("sei a qual segmento 7,35 pertence?"). Associar errado é o erro perigoso;
  as duas nunca se fundem num número só.
- **Modo shadow sempre computado**: a cada revisão, o pipeline registra o que
  TERIA auto-decidido em cada threshold, sem decidir nada. O registro é
  comparável às decisões humanas reais da mesma revisão — é a base de
  calibração e continua existindo depois que o modo automático ligar.

### Fatia 2 — métricas e eval

- `auto_association_rate` (cotas corretamente auto-associáveis / total) e
  `review_rate` (cotas que exigiram humano / total) como métricas de primeira
  classe do relatório de revisão.
- Eval determinística nova com make target, no molde do `vision-eval`:
  fixtures sintéticas versionadas, gate no CI local com **zero**
  auto-associação errada no conjunto sintético.
- Relatório de calibração sobre os dados reais (replay das revisões do
  Guaxindiba + PDFs de levantamentos fornecidos pelo usuário em
  `output/levantamentos-calibracao/`): tabela threshold × (auto_rate, erro)
  para o usuário escolher o corte. Local, fora do CI, dados nunca
  versionados, retenção de 7 dias.

### Fatia 3 — modo automático local atrás de flag

- `CROQUITO_AUTO_ASSOCIATION_ENABLED` (flag do worker, padrão `false`).
  Nesta feature ela só é ligada em ambiente local; qualquer ambiente
  hospedado fica explicitamente fora.
- Com a flag ligada e acima do threshold aprovado pelo usuário: a leitura
  recebe decisão de **ator-máquina** (extensão do modelo de decisão — ver
  ADR-0041, a especificar) e a associação vira explícita para o solver. A
  proveniência distingue sempre decisão humana de decisão automática.
- A tela de revisão mostra só exceções: contadores
  `auto-associadas / revisão necessária / não resolvidas`, badge visível na
  linha auto-decidida (cor nunca é o único indicador), e qualquer
  auto-decisão pode ser desfeita/retificada pelo caminho de retificação
  existente (ADR-0022).
- A auditoria do export (`auditoria.json`/`hipoteses.json`) lista
  nominalmente toda cota que entrou sem toque humano. O portão
  `SceneRevision.export_errors()` permanece o único caminho até DXF; nada
  contorna o auditor.

### Decisão de arquitetura embutida

O invariante fail-closed ("leitura sem `HumanDecision` completo →
`review_required`") passa a admitir, atrás de flag e com proveniência de
ator-máquina, decisão automática acima de threshold calibrado. É mudança de
contrato em `croquito_core.models` (variante de ator na decisão ou tipo irmão
`AutoDecision`) → `make contracts` regenera schema e TypeScript. A decisão
nasce como **ADR-0041**, com aceite humano como gate antes da fatia 3.

## Scope

- Sinais e score nos módulos de associação do worker (`association.py` e
  vizinhos), com campos tipados novos no modelo — mudança aditiva de
  contrato.
- Shadow log persistido por revisão de review (comparável às decisões
  humanas).
- Eval nova + make target + relatório de calibração (CLI, no molde das evals
  existentes).
- Flag do worker, decisão de ator-máquina (ADR-0041), integração com o
  solver (associação explícita) e com a auditoria do export.
- Tela de revisão: contadores, badge de auto-decisão e filtro de exceções
  sobre os padrões visuais existentes.
- ADR-0041 escrito e submetido a aceite.

## Out of Scope

- Ligar a flag em HML/produção, deploy GCP, migração no hosted — qualquer
  ato de ambiente hospedado.
- Benchmark Mistral OCR / Gemini (feature própria, condicionada ao resultado
  da V17 do Document AI).
- Edição de forma na UI (F-018) e preview visual da cena (F-019).
- "Recomendações de campo acionáveis" da F-023 (nota agregada do
  levantamento com recomendações continua como fatia futura da F-023; só o
  score calibrado com V14–V17 migra para cá).
- Fotos do levantamento na revisão (vira F-030, registrada no roadmap).
- Qualquer mudança de comportamento com a flag desligada: pipeline, exit
  codes, telas e exports idênticos aos de hoje, bit a bit.
- Mudança em `dimension_closure.py` (só é consumido como sinal).

## Acceptance Criteria

1. `make check` e `make test` verdes; drift de contratos zero;
   `tests/e2e/test_full_flow.py` verde.
2. Com a flag desligada (default), nenhuma mudança observável: smoke local
   (`make smoke-local`) e portões passam sem diferença de comportamento.
3. Toda leitura e todo candidato de associação carregam
   `reading_confidence`/`association_confidence` determinísticos; rodar duas
   vezes sobre o mesmo pacote produz os mesmos números.
4. Shadow log existe para toda revisão, mesmo com flag desligada, e nunca
   altera decisão, cena ou export.
5. Eval sintética nova passa com **zero** auto-associação errada; o gate
   falha se uma associação errada ficar acima do threshold do gate.
6. Replay dos dados reais gera o relatório threshold × (auto_rate, erro);
   o threshold operacional é escolhido pelo usuário a partir dele, nunca
   default do código.
7. Com a flag ligada no stack local: PDF → job → revisão exibindo só
   exceções → aprovação → DXF auditado, com toda cota auto-decidida listada
   nominalmente na auditoria do pacote e com proveniência de ator-máquina na
   revisão.
8. Auto-decisão é retificável pelo caminho de retificação existente e nunca
   sobrescreve decisão humana anterior.
9. ADR-0041 escrito; snapshot OpenAPI regenerado deliberadamente se rota
   mudar; ROADMAP/STATUS refletem a rodada.

## Human Gates

1. Aprovação do spec — exercida em sessão em 2026-08-21 (aprovação do plano
   da sessão com as três decisões de escopo).
2. Aceite do ADR-0041 (decisão de ator-máquina) antes da fatia 3.
3. Aprovação do threshold operacional a partir do relatório de calibração.
4. Aprovação de um mock simples da vista de exceções antes da task web.
5. Ligar a flag em qualquer ambiente hospedado é decisão futura, fora deste
   contrato.
6. Fornecimento dos PDFs de calibração (`output/levantamentos-calibracao/`)
   é ato do usuário.
