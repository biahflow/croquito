# ADR-0019: Refino determinístico de observação cria nova revisão de leitura

Status: Accepted
Data: 2026-08-12
Responsável: Engineering / AI

## Contexto

O registro fino de propostas v2 (`register-extraction`, handoff R1) produz geometria de
visão computacional melhor sob os MESMOS ids `vp_…` — a tinta da página não muda, só a
precisão com que o detector a lê. Até aqui não existia caminho para essa geometria
melhor entrar num job que já tem revisão em andamento: `seed-review` recusa fechado
qualquer job que já carregue uma `review_revisions`
(`REVIEW_ALREADY_EXISTS`, `services/worker/src/croquitodxf_worker/review_seed.py:180-188`;
`review_store.py` grava a revisão 1 com `insert_review_revision_v1`, hard-coded para
`version = 1`). Um job real pode ter dezenas de revisões, dezenas de decisões humanas
imutáveis (`HumanDecision` presas às leituras) e um mapa
`selected_associations_json` de `reading_id → vp_id` já confirmado por um profissional.

A segurança do problema já estava mapeada antes da implementação:

- Uma entidade aceita copia a geometria da proposta POR VALOR no momento do aceite
  (`proposal_calibration.py:approximate_entity_from_proposal`); depois disso ela é
  imutável e nenhum refino de proposta a alcança.
- O traçado em lote (`solve-trace`) recomputa a topologia a cada execução a partir do
  `proposals_json` da revisão-base corrente (`local_queue.py`); um refino só vale para o
  PRÓXIMO aceite, nunca reabre um aceite já feito.
- Os candidatos de associação (`associations_json`) nascem sempre offline
  (`associate_readings`, `association.py`) e são recomputados, nunca copiados, sempre
  que a geometria de origem muda.
- A evidência (bbox, recorte, digest) das leituras vive no `ReviewPacket`, independente
  do snapshot de propostas — refinar propostas não toca a evidência.
- A calibração pixel→metro já tinha semântica pronta de revalidação e supersessão
  (`_revalidate_calibration` na API, issue crítica `CALIBRATION_SUPERSEDED`): um drift
  acima da tolerância nunca reprojeta a entidade aceita, só bloqueia o export com uma
  issue explícita até o profissional recalibrar.

Faltava só o mecanismo que aplica um refino de propostas a um job vivo sem violar
nenhuma dessas garantias.

## Decisão

Um novo comando de worker, `refresh-proposals` (`review_refresh.py`), aceita um
`VisionProposalSet` refinado e cria uma **nova revisão de leitura** (`version = atual +
1`, `parent_review_id = atual.id`) — nunca sobrescreve a revisão vigente. A revisão nova
copia byte a byte o `packet_json` (leituras e decisões humanas), o
`proposal_decisions_json`, o `evidence_refs_json` e os demais campos que não dependem da
geometria de propostas. Só muda o que depende dela:

- `proposals_json` passa a ser o snapshot refinado;
- `associations_json` é RECOMPUTADO com `associate_readings` contra a evidência da
  revisão vigente — nunca copiado;
- `calibration_json`, quando havia calibração ativa, é revalidado pela MESMA regra que
  a API usa nas decisões de leitura (`croquitodxf_worker.proposal_calibration.
  revalidate_calibration`, movida de `services/api/src/croquitodxf_api/main.py` para o
  worker e reusada de lá pelos dois lados). Se o drift ultrapassa a tolerância, a
  calibração é descartada na revisão nova e a cena corrente ganha uma nova revisão só
  para carregar a issue crítica `CALIBRATION_SUPERSEDED` — a entidade já aceita nunca é
  reprojetada nem apagada.

O comando recusa fechado (matriz completa em `review_refresh.py`) sempre que: o job não
existe ou não é do tenant; o job não tem revisão (`REVIEW_MISSING` — job sem revisão usa
`seed-review`, não este comando); o digest da imagem diverge do arquivo ou do snapshot
vigente; dataset/página divergem; o CONJUNTO de ids `vp_…` não é bijetivo com o vigente
(qualquer adição, remoção ou duplicata); ou uma associação já confirmada por um
profissional (`selected_associations_json`) deixa de existir entre os candidatos
recomputados. Rodar o comando duas vezes com o mesmo arquivo refinado é idempotente: a
segunda execução recusa com `REFRESH_ALREADY_APPLIED` e não cria revisão.

## Por que não é "sobrescrever evidência"

`seed-review` recusa job com revisão porque sobrescrever a primeira leitura de um job
apagaria a única evidência do que o profissional decidiu. `refresh-proposals` não tem
esse risco: a revisão anterior permanece intocada no banco, intacta como evidência
histórica e como `parent_review_id` da nova. O refino em si é uma derivação
determinística da mesma tinta — mesmo algoritmo de detecção, evidência de origem
inalterada, ids preservados — não uma nova observação nem uma reinterpretação humana.
Ele é auditável (o antes/depois de `quality_score` por proposta viaja na saída do
comando) e acontece estritamente ANTES da revisão humana daquele snapshot: nenhuma
decisão, nenhuma associação confirmada e nenhuma entidade aceita é alterada — só
recomputada quando depende diretamente da geometria de propostas, e travada atrás de
uma issue crítica quando a recomputação não fecha.

## Alternativas

- Editar `proposals_json` in place na revisão vigente: rejeitado. Quebraria a
  imutabilidade de revisão que sustenta toda a auditoria do domínio (ADR-0006) e
  tornaria decisões/associações confirmadas silenciosamente inconsistentes com a
  geometria que as originou.
- Reprojetar automaticamente as entidades já aceitas com a geometria refinada:
  rejeitado. Um aceite é um ato humano sobre uma geometria específica
  (`HUMAN_ACCEPTED_PROPOSAL_SOURCE_TYPE`); mover essa geometria sem novo aceite
  inventaria consentimento.
- Duplicar a lógica de revalidação de calibração no worker: rejeitado. Duas
  implementações do mesmo teste de deriva divergiriam silenciosamente; a lógica foi
  movida para `croquitodxf_worker.proposal_calibration` (dependência que a API já tinha)
  e reusada por referência nos dois lados.

## Consequências

### Positivas

- Geometria de visão melhor entra em jobs vivos sem reprocessar a revisão inteira nem
  perder decisão humana.
- Associação e calibração nunca ficam desalinhadas da geometria de propostas vigente:
  ou recomputam limpo, ou o comando recusa/bloqueia explicitamente.
- Auditoria simétrica ao `seed-review`: recusa fechada, nada escrito ao recusar, saída
  com antes/depois.

### Negativas

- Um refino que muda a geometria de uma proposta já com associação confirmada pode
  recusar (`REFRESH_BREAKS_SELECTED_ASSOCIATION`) e exigir nova decisão de associação
  do profissional — comportamento intencional, não um defeito a contornar.
- O comando é CLI-only nesta rodada; expor por rota HTTP fica para quando o fluxo de
  refino ganhar acionamento pela sessão autenticada.

## Riscos e mitigação

| Risco | Mitigação |
|---|---|
| Refino altera proposta usada por associação já confirmada | `REFRESH_BREAKS_SELECTED_ASSOCIATION` recusa fechado antes de escrever |
| Calibração sobrevive com drift não detectado | Mesma regra e tolerância da API (`CALIBRATION_DRIFT_TOLERANCE_M`), agora com uma única implementação |
| Execução repetida do mesmo arquivo cria revisões redundantes | `REFRESH_ALREADY_APPLIED` compara o snapshot proposto ao vigente byte a byte |
| Regressão silenciosa ao mover `_revalidate_calibration` para o worker | Testes novos em `tests/worker/test_review_refresh.py` e suíte completa de `tests/api/test_api.py` cobrindo `CALIBRATION_SUPERSEDED` continuam verdes |

## Rastreabilidade

- Requirements: relacionado a ADR-0006 (revisão humana e provenance obrigatórias) e
  ADR-0005 (scene graph canônico).
- Supersedes: none
- Superseded by: none
