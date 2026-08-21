# F-029 — Evidência de execução

Handoff de revisão da feature
[F-029](feature.md) · [plan.md](plan.md) · Task Contracts em [tasks/](tasks/).
Este documento referencia evidência-fonte; não a substitui.

## Baseline (antes de qualquer task)

- `main` limpa de código; working tree com as mudanças de documentação desta
  rodada ainda não commitadas (spec F-029, plano, tasks, ADR-0041 `Proposed`,
  ROADMAP/STATUS) — intencionais, preservadas pelas tasks.
- `make check` verde em 2026-08-21, rodado duas vezes na sessão de
  spec/planejamento (inclui `check_docs`, ruff, mypy strict, drift de
  contratos, build web, terraform fmt).
- `make test` não exercitado isoladamente antes da T1 nesta sessão; a suíte
  entra como portão da própria T1 e qualquer falha preexistente descoberta
  ali será registrada aqui como baseline, não atribuída à task.
- Nenhuma falha preexistente conhecida.

## Designação de harness (fora do plano, por task)

```text
HARNESS ASSIGNMENT
task_id: T1
harness: Claude Code / subagente implementador-sonnet (modelo fixado)
assigned_by: Daniel (método global de delegação do usuário — escada validada
  em 2026-08-12: tarefa bem delimitada com oráculo de testes → sonnet)
rationale: módulo novo, escopo fechado, testes como oráculo; revisão linha a
  linha pelo modelo principal da sessão na entrega
```

```text
HARNESS ASSIGNMENT
task_id: T5
harness: Claude Code / subagente implementador-opus (modelo fixado)
assigned_by: Daniel (método global de delegação do usuário)
rationale: integração em CroquiApp.tsx (arquivo grande vivo, 5.784 linhas)
  — degrau opus da escada, como T2/T4
```

```text
HARNESS ASSIGNMENT
task_id: T3
harness: Claude Code / subagente implementador-sonnet (modelo fixado)
assigned_by: Daniel (método global de delegação do usuário)
rationale: eval e relatório com molde claro (vision_eval.py), escopo
  fechado e oráculo de testes — degrau sonnet da escada
```

```text
HARNESS ASSIGNMENT
task_id: T4
harness: Claude Code / subagente implementador-opus (modelo fixado)
assigned_by: Daniel (método global de delegação do usuário)
rationale: toca o invariante fail-closed (ADR-0041), múltiplos pontos
  (review.py, local_queue.py, dxf.py, main.py) e fecha a lacuna do shadow
  na revisão 1 — risco alto do plano exige o degrau opus
```

```text
HARNESS ASSIGNMENT
task_id: T2
harness: Claude Code / subagente implementador-opus (modelo fixado)
assigned_by: Daniel (método global de delegação do usuário)
rationale: integração em main.py (arquivo grande vivo, ~5.800 linhas na
  área de review), migração 0007 e replay idempotente — degrau opus da
  escada; revisão linha a linha pelo modelo principal na entrega
```

Demais tasks: designadas no momento da execução, registradas aqui.

## T1 — sinais e confianças — CONCLUÍDA (2026-08-21)

- Status do Builder: `BUILD_COMPLETE` (BUILD REPORT completo emitido pelo
  subagente na sessão; síntese abaixo, atribuição preservada —
  implementador-sonnet).
- Arquivos: `association.py` (campos aditivos `orientation_alignment`,
  `association_confidence`; helpers de orientação; score pós-ranking com
  margem sobre os irmãos top-N), `association_confidence.py` (novo — duas
  confianças, pesos nomeados, `shadow_decisions` puro com `ShadowChoice`),
  `tests/worker/test_association_confidence.py` (novo, 15 testes),
  `tests/api/openapi.snapshot.json` (regenerado).
- Portões (executados pelo Builder e re-verificados pelo revisor da sessão):
  `make check` verde; pytest dos dois arquivos de teste verde (17 testes);
  `make test` verde (1803 pytest + 853 vitest).
- Revisão linha a linha (modelo da sessão): 1 `CODE_FINDING` MEDIUM —
  `ShadowDecision` não registrava a escolha (proposal) do corte hipotético,
  só os reading_ids; recomputar o argmax na calibração reabriria o desempate
  a uma ordem de lista sem contrato. Corrigido pelo Builder na mesma rodada
  (`ShadowChoice` + desempate determinístico por `proposal_id`, teste de
  empate incluído). `feedback_iterations = 1`. Aceita.
- `PLAN_DEVIATION` (consciente, aprovado na revisão): regeneração de
  `tests/api/openapi.snapshot.json`, não prevista no Task Contract de T1 —
  os campos aditivos em `AssociationCandidate` mudam mecanicamente o schema
  exposto porque `AssociationSet` já é campo de resposta da API. Isolado por
  stash: diff restrito às duas propriedades novas, nenhuma rota/operação.
  Antecipou parte do snapshot que T2 faria de qualquer forma.
- Riscos declarados que seguem abertos: pesos não calibrados (propósito das
  fatias 2/3); eixo dominante do bbox como aproximação de orientação
  (horizontal/vertical puro — cota rotacionada pode ser subestimada; a
  calibração de T3 mede se o sinal ajuda ou atrapalha).

## T2 — shadow persistido e API — CONCLUÍDA (2026-08-21)

- Status do Builder: `BUILD_COMPLETE` (implementador-opus; BUILD REPORT
  completo emitido na sessão, síntese abaixo com atribuição preservada).
- Arquivos: migração `0007_review_confidence_shadow.py` (coluna JSON
  aditiva, molde 0006, forward-only, server_default também no modelo pelo
  INSERT coluna a coluna do worker); `database.py`; `main.py` (grade fixa
  6×6 de thresholds com ponto de referência 0,95/0,95 — o MAIS conservador,
  nunca recomendação; cômputo nos 8 pontos de gravação; `_carried_...`
  recomputa em vez de copiar, com justificativa de pureza); modelos de
  resposta observacionais com `default_factory` (replay pré-campos coberto);
  `API_CONTRACT.md`; snapshot OpenAPI; 7 testes novos em `test_api.py`.
- Portões: `make check` verde; `pytest tests/api` verde; `make test` verde
  (1810 + 853); migrações contra PostgreSQL 17 real descartável (12 passed,
  incluindo drift e forward-only da 0007).
- Revisão linha a linha (modelo da sessão): 2 `CODE_FINDING` MEDIUM, ambos
  corrigidos na mesma rodada — (1) cadeia declarada `mismatch` passou a
  penalizar as participantes (arbitragem da sessão sobre achado do próprio
  Builder: declarada afirma completude, sugerida é descoberta incompleta —
  critérios diferentes de propósito, fundamento no docstring de
  `_confidence_chains`; `stale` volta ao neutro); (2) `score_version`
  carimbado em todo shadow gravado (`CONFIDENCE_SCORE_VERSION = "1.0.0"`),
  para a calibração nunca misturar pesos de versões diferentes.
  `feedback_iterations = 1`. Aceita.
- Achado transferido ao T4 (registrado pelo Builder): a revisão 1, escrita
  pelo worker (`review_store.insert_review_revision_v1`, SQL cru), fica sem
  shadow — exatamente onde o modo automático agirá; T4 fecha a lacuna.
- Correção de contrato: o caminho `docs/engineering/API_CONTRACT.md` no
  Task Contract estava errado; o real é `docs/architecture/API_CONTRACT.md`
  (atualizado pelo Builder, registrado aqui como errata do contrato).

## T3 — eval e calibração — CONCLUÍDA (2026-08-21)

- Status do Builder: `BUILD_COMPLETE` (implementador-sonnet; BUILD REPORT
  completo emitido na sessão, atribuição preservada).
- Entregas: `association_eval.py` (gate determinístico — fixture sintética
  em código com gabarito de 5 casos, zero erro acima do corte 0,8 + recall
  1,0; `association-eval.json`; exit 0/1) e `calibration_report.py`
  (local, nunca CI — replay de `review_revisions`: verdade = decisão HUMANA
  vigente pós-retificações, medida contra o shadow da revisão ANTERIOR ao
  nascimento da decisão; tabela por ponto da grade com auto_rate,
  review_rate, erro de associação e erro de leitura, agrupada por
  score_version; exit 2 sem dado elegível); CLI `association-eval` e
  `calibration-report`; make targets `association-eval` e
  `association-calibration`; 8 testes.
- Portões: `make check`, `make association-eval` (passed=true),
  pytest do arquivo (8), `make test` completo — verdes, re-verificados.
- Revisão linha a linha (modelo da sessão): 3 `CODE_FINDING` — 1 HIGH
  corrigido: a verdade da calibração usava o shadow da revisão em que a
  decisão humana nasceu (PÓS-decisão — a própria confirmação pode fechar
  cadeia que corrobora a própria leitura), superestimando auto_rate nos
  cortes altos; passou ao shadow da revisão imediatamente anterior, com
  teste de regressão do caso exato do viés. 2 LOW corrigidos: decisão sem
  campo `actor` tratada como humana (semântica do default), e desempate
  importado de `_best_candidate` em vez de duplicado (eval espelha produção
  por construção). `feedback_iterations = 1`. Aceita.
- Desvios conscientes mantidos (documentados no código): leitura direta de
  `CROQUITO_DATABASE_URL` (o helper exigiria endpoint AWS alheio ao
  relatório); `max_distance_diagonal_ratio` menor na fixture do eval para
  isolamento geométrico auditável.
- Nota de arbitragem pendente de sanity-check humano (declarada pelo
  Builder): denominadores das taxas do relatório (espelham a semântica de
  `_confidence_view` da API) — conferir na primeira rodada com dados reais.

## T4 — modo automático (flag) — CONCLUÍDA (2026-08-21)

- Status do Builder: `BUILD_COMPLETE` (implementador-opus; BUILD REPORT
  completo emitido na sessão, síntese com atribuição preservada).
- Núcleo: `auto_association.py` novo (dupla chave estrita, ausente=desligado;
  threshold sem default; `apply_auto_association` REUSA `shadow_decisions`
  com o corte único — o registro e o ato são a mesma computação, mesmo
  argmax/desempate); `HumanDecision.actor` aditivo com validação condicional
  do ADR-0041 (sistema: identidade versionada por FORMATO, só confirma,
  nunca retifica; humano: papel obrigatório); lacuna da revisão 1 fechada em
  `insert_review_revision_v1` (shadow gravado + auto-decisão no único ponto
  de escrita do worker); blockers recomputados quando houve auto-decisão;
  auditoria do export lista nominalmente cada cota automática
  (`auto_decided_readings` com confidências, corte e score_version);
  `export_errors()` intocado; grade movida de `main.py` para
  `association_confidence.py` (fonte única, docstrings da T2 preservados).
- Portões: `make check` verde; `make test` verde; e2e verde (6 testes,
  incluindo `test_com_o_modo_automatico_local_so_a_excecao_exige_uma_pessoa`
  e `test_uma_auto_decisao_retificada_sai_da_lista_de_cotas_automaticas`);
  re-verificados pelo revisor da sessão (50 testes worker/e2e + make check).
- Revisão linha a linha (modelo da sessão): nenhum finding bloqueante. As 3
  interpretações do ADR foram examinadas e aceitas: (1) identidade do
  sistema validada por formato, não por igualdade com a versão corrente
  (igualdade invalidaria decisões persistidas na recalibração); (2) decisão
  de sistema não entra no índice `review_decisions` (reviewer_role NOT NULL
  + proibição de papel fabricado; a retificação lê do pacote e está coberta
  por teste); (3) shadow da revisão 1 descreve o estado GRAVADO, com as
  confianças do instante do ato preservadas em `auto_decisions` — semântica
  consistente com as revisões da API. `feedback_iterations = 0`. Aceita.
- Dívidas declaradas (seguem abertas, nenhuma bloqueia o experimento local):
  `Provenance.source_type` do scene graph continua
  `human_confirmed_reading+explicit_association` para leitura auto-decidida
  (mudar toca croquito_core/make contracts — obrigatória antes de qualquer
  cogitação de ambiente hospedado, junto da revisão do ADR-0041);
  "endossar" auto-decisão sem alterar nada cai em
  `RECTIFICATION_ALREADY_APPLIED`; com TODAS as leituras auto-decididas a
  cena só nasce após um ato humano (traçado em lote) — beco de jornada, não
  fail-open.
- **Fato para o gate do threshold**: na revisão 1 o teto real de
  `reading_confidence` é **0,85** (nada confirmado ⇒ sinal de cadeia neutro
  0,5). Corte acima de 0,85 liga o modo sem efeito na revisão 1; o efeito
  pleno aparece conforme confirmações fecham cadeias e elevam as demais.
- Registro de ambiente: durante a execução, outra sessão editou
  `packages/valuation/{catalog,sco}.py` e testes correlatos na mesma working
  tree (trabalho alheio, preservado; portões finais verdes com a árvore
  nesse estado).

## T5 — web de exceções — CONCLUÍDA (2026-08-21)

- Status do Builder: `BUILD_COMPLETE` (implementador-opus; BUILD REPORT
  completo emitido na sessão, atribuição preservada).
- Entregas: tipos aditivos opcionais em `api.ts`; rótulos em língua de obra
  em `labels.ts`; `CroquiApp.tsx` com puros exportados (`exceptionCounts`,
  `visibleReadings`, `isSystemDecided`…) + `ExceptionsBand` (faixa de
  contadores + chip-filtro em dois botões `aria-pressed`), badge
  "⚙ associada pelo sistema · score 1.0.0" com confidência em vírgula
  decimal, retificação pelo caminho existente; 43 testes novos (31 + 12).
- Portões: `make check` verde; vitest 884 (baseline 853); `make test`
  completo verde (1874 pytest + 884 vitest).
- Revisão (modelo da sessão): puros de recorte examinados linha a linha —
  filtro oculta APENAS linha decidida; pendente e linha citada por blocker
  nunca somem; resposta sem os campos novos rende a tela de hoje.
  Zero findings. 5 desvios conscientes do mock aceitos (concordância
  gramatical do contador; dois botões em vez de chip único; leituras
  elegíveis a termo de cadeia em curso permanecem visíveis; identidade
  técnica traduzida — "Confirmada pelo sistema, sem toque humano, com o
  score 1.0.0"; frase de lista vazia). `feedback_iterations = 0`. Aceita.
- Pendências declaradas pelo Builder, assumidas pelo fechamento da feature:
  atualização do FDD (nenhuma task tocou); conferência visual na tela real
  com a flag ligada (sanity-check de execução do gate 4).
- Gate de entrada que estava satisfeito: **mock aprovado por ato humano em
  2026-08-21** (variante A — faixa de contadores no topo
  `⚙ auto-associadas · ⚠ revisão necessária · ✗ não resolvidas` + chip-filtro
  "só exceções"/"todas"; linha auto-decidida permanece na lista com badge
  "⚙ associada pelo sistema", confidência, badge "Σ fecha" quando houver e
  ação Retificar sempre acessível; blockers e issues críticas nunca são
  filtrados). Variante B (seção recolhida) apresentada e recusada.

## Primeira calibração real (2026-08-21, Guaxindiba V1 local)

Jornada completa exercitada no stack docker real: upload → worker →
`seed-review` com o pacote real (29 leituras, associações regeneradas com o
score 1.0.0) → revisão humana integral (flag desligada, de propósito: as
decisões viram verdade) → traçado → aprovação → **export auditado
`approved`**, com `auditoria.json` sem a chave de cotas automáticas
(comportamento correto para revisão 100% humana). Shadow da revisão 1
gravado (36 pontos, score 1.0.0) — lacuna da T4 confirmada fechada em dado
real.

`make association-calibration` sobre 1 job / 29 verdades humanas, score
1.0.0 (relatório em `output/association-calibration/`, retenção 7 dias):

- corte de associação 0,5 → 29 auto, **65,5% de erro de associação**;
- 0,6 → 22 auto, **54,5% de erro**;
- **0,7 → 2 auto, 0% de erro** (auto_rate 6,9%);
- ≥0,8 → nada auto-decidível (teto real observado: 0,79);
- eixo de leitura: nada sobrevive a 0,7 (sem braço de OCR local,
  `ocr_corroborated` fica neutro; cadeias só fecham tarde).

Rodada V3 (mesma data, providers reais LOCAIS pela primeira vez —
autorização de gasto do usuário, teto US$ 6,00, Anthropic + Document AI
via ADC com quota project isolado no worker): 20 leituras, com o sinal de
OCR vivo — 5 corroboradas a 0,85 (25,90; 14,50×2; 8,60; h=3,80) e 15 a
0,45. O corte (0,7; 0,6) auto-decidiria 5. Custos de rodada dentro do teto.
Duas testemunhas operacionais colhidas no caminho: `SSL_CERT_FILE`
obrigatório para o Python do uv (lição do runbook da Toca, reencontrada) e
timeout default de 60s insuficiente para extração de página inteira
(lição da V7, reencontrada) — ambos agora no `.env.local`.

Achado de mecanismo da V3 (candidato ao score 1.1.0): a corroboração de OCR
exige texto IGUAL + interseção de bbox; anotação multi-linha rotacionada
("2 Traves 4″ / h=2,20 / c=3,90") veio como bloco único do braço de
extração e como três linhas do Document AI — os números batem e a
testemunha não fecha. Corroborar por linha/substring normalizada dentro do
bbox recuperaria segunda testemunha legítima sem abrir a porta do
falso-confirmado (validar na eval antes de promover). Registrado aqui; não
implementado nesta rodada.

Leitura honesta: com o score 1.0.0, o ponto de operação seguro é ~(0,6; 0,7)
com **~7% de auto-decisão e zero erro** — muito longe dos "85–95%" da tese
externa que motivou a feature. O sinal espacial puro não separa certo de
errado em croqui denso (confirma a lição da V12). O que sobe o teto é a
fatia de recalibração: sinal de OCR (braço pago), feedback do solver ligado
no instante da decisão, pareamento por sobreposição e repesos → score 1.1.0,
sempre comparado por versão. Base de verdade ainda é 1 PDF — os outros 6
levantamentos ampliam antes de qualquer conclusão.

## T6 — tier de anotação automática (ADR-0044) — CONCLUÍDA (2026-08-21)

- Nasceu da rodada V4 real: o usuário apontou o custo residual das exceções
  de testemunha única; a forma máxima (cota estacionada) foi desenhada,
  custeada e RECUSADA pelo próprio usuário; a forma reduzida virou o
  [ADR-0044](../../adr/0044-triagem-por-testemunha-anotacao-automatica.md)
  (Accepted, com emenda 1a na mesma sessão).
- Builder: o mesmo implementador-opus da T4 (retomado com contexto;
  designação registrada por esta linha). Task Contract em
  [tasks/T6-tier-anotacao.md](tasks/T6-tier-anotacao.md).
- Ciclo de execução com achado de arquitetura: a 1ª entrega implementou a
  letra do ADR (anotação associada) e o Builder PAROU no gate ao provar
  com evidência (tracing.py:1461-1476; main.py `_apply_association_rules`)
  que associação explícita é restrição métrica no traçado e que o ato
  humano de anotação é justamente a confirmação SEM associação. Arbitragem
  da sessão virou a emenda 1a do ADR: o tier espelha o ato humano —
  confirma sem vínculo; o candidato provável viaja como observação
  (`probable_proposal_id` na note/shadow/auditoria). `feedback_iterations
  = 1` (por emenda de contrato, não por defeito do Builder).
- Entrega final: dois laços em `apply_auto_association` (cota → anotação
  sobre o restante), elegibilidade `annotation_suggested` (F-021) OU kind
  fora da lista de planta, nunca leitura designada pelo solver; sem
  exigência de confiança de associação; tela com contador e badge
  "anotação automática" e correção abrindo como anotação (sem "retificar
  associação" inexistente). Testes-chave:
  `test_uma_anotacao_automatica_nunca_vira_restricao_no_tracado` (e2e) e
  `test_a_anotacao_automatica_tem_a_mesma_forma_da_anotacao_declarada_por_gente`.
- Portões: os quatro do contrato verdes (896 vitest); tier 1 byte a byte
  inalterado (testes da T4 sem edição de expectativa); re-verificação da
  sessão (52 testes worker+e2e + spot-check dos laços). Aceita.
- Risco declarado que fica: anotação automática só vira texto na prancha
  quando fixada em `note_associations` no aceite — medir quantas chegam ao
  aceite sem fixação (candidata a atalho no consultor da F-025).

## Desvios de plano

1. `PLAN_DEVIATION` (T1): regeneração do snapshot OpenAPI não prevista no
   Task Contract — consequência mecânica dos campos aditivos; aprovada na
   revisão (detalhe na seção T1).
2. `PLAN_DEVIATION` (grupo paralelo [T3, T4]): executados em SEQUÊNCIA
   (T4 → T3), não em paralelo. Planejado: paralelo por áreas disjuntas.
   Real: os dois builders compartilhariam a mesma working tree com
   mudanças não commitadas (T1+T2+docs; worktree isolado não as veria) e
   portões concorrentes (`make check`/`make test` simultâneos disputam
   caches de mypy/vite). Impacto: só wall-clock; nenhum escopo muda.
   Resolução: sequencial, T4 primeiro por ser o caminho crítico.

## Decisões humanas pendentes

1. ~~Aceite do ADR-0041~~ — **exercido em 2026-08-21**.
2. Escolha do threshold operacional (após relatório da T3).
3. ~~Aprovação do mock da vista de exceções~~ — **exercida em 2026-08-21**
   (variante A, descrita na seção T5).
4. Commit/push da rodada (nada commitado por decisão de sessão).
