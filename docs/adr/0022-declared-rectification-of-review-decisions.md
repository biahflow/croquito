# ADR-0022: Correção declarada de decisão de revisão

Status: Accepted  
Data: 2026-08-13  
Responsável: Domain / Backend / Frontend

## Contexto

Decisão de leitura é imutável desde o primeiro dia: `apply_reading_decisions`
(`services/worker/src/croquitodxf_worker/review.py`) recusa fechado qualquer leitura já
`confirmed` ou `rejected`, e a API devolvia 422 para a segunda tentativa. A regra existe
para uma razão boa — uma decisão sobrescrita apagaria a única evidência do que o
profissional decidiu e sobre qual geometria — mas ela deixava um caminho só para o erro
humano: refazer o job inteiro.

O custo apareceu no caso real. No Campo do Guaxindiba (v1 → v2), treze leituras foram
confirmadas com o eixo trocado (largura onde a folha cota altura). Corrigir significou
semear a evidência de novo, decidir tudo de novo e perder as decisões corretas do mesmo
lote — trabalho humano descartado por um erro de transcrição em três delas.

O que falta não é afrouxar a imutabilidade: é dar à correção o mesmo estatuto que a
decisão já tem — ato humano identificado, justificado, versionado e auditável.

## Decisão

A correção de uma decisão registrada é um **ato humano novo**, não uma edição.

- O domínio ganha `rectify_reading_decisions` (função nova; `apply_reading_decisions`
  mantém o comportamento e continua recusando redecisão). Ela produz um pacote novo em
  que a leitura carrega outra `HumanDecision`, com id próprio e
  `rectifies_decision_id` apontando **nominalmente** a decisão substituída.
- A API expõe `POST /v1/jobs/{job_id}/review/rectifications`, que cria uma **revisão de
  leitura nova** (`version + 1`, `parent_review_id` da corrente), exatamente como a
  decisão normal. A revisão anterior — com a decisão errada — permanece intacta no banco
  como evidência histórica, e o índice append-only `review_decisions` ganha uma linha
  nova (`rectify_confirm`/`rectify_reject`) citando a anterior.
- A leitura **nunca volta a `proposed`**. Ela permanece decidida; o que muda é qual
  decisão é a vigente.
- A **associação é sempre redeclarada** pelo comando. A tela pré-preenche a associação
  vigente, mas o envio é explícito: uma correção que herdasse a associação em silêncio
  reafirmaria uma ligação proposta↔cota que ninguém reconferiu.
- A cascata é **invalidar para frente**. Uma correção nunca é recusada por dependência
  geométrica e nunca toca aprovação ou pacote já publicados. Quando a cena mais recente
  ainda se apoia na decisão corrigida — entidade ou medida cuja `provenance.source_ids`
  cita o `decision_id` antigo e que não foi recomputada no mesmo request — nasce uma
  **cena nova, não aprovada**, com a geometria copiada intacta e a issue crítica
  `READING_DECISION_SUPERSEDED` listando as entidades afetadas. O export fica bloqueado
  até o profissional refazer o traçado daquela parte.
- Quando existe pedido de solver retangular, o re-solve roda pelo mesmo caminho da
  decisão normal (`_resolve_scene_after_review_change`, compartilhado pelos dois
  endpoints). Nesse caso a cena nova já nasce recomputada a partir do pacote corrigido, e
  a supersessão só alcança o que sobrou preso à decisão antiga. Um request produz **uma
  única cena nova**, mesmo quando `CALIBRATION_SUPERSEDED` e `READING_DECISION_SUPERSEDED`
  ocorrem juntas.

Matriz de recusas, todas fail-closed e sem escrever nada:

| Situação | Código | HTTP |
|---|---|---|
| Leitura ainda não decidida | `READING_NOT_DECIDED` | 422 |
| Alvo citado não é a decisão vigente | `RECTIFICATION_TARGET_STALE` | 409 |
| Correção idêntica ao registro vigente | `RECTIFICATION_ALREADY_APPLIED` | 422 |
| `base_version` vencida ou escrita concorrente | `REVISION_CONFLICT` | 409 |
| Leitura fora do pacote, associação fora dos candidatos, anotação com associação | `DOMAIN_VALIDATION_FAILED` | 422 |
| Papel sem elegibilidade profissional | `FORBIDDEN` | 403 |
| Job de outro tenant | `NOT_FOUND` | 404 |

O endpoint de decisão passa a recusar redecisão com código próprio,
`READING_ALREADY_DECIDED`, cujo detalhe aponta a correção declarada.

## Por que isto não contradiz o ADR-0006

A imutabilidade do [ADR-0006](0006-human-review-and-provenance.md) é de **revisões**, não
de leituras: "revisões são imutáveis e auditáveis". Nenhuma revisão é alterada aqui —
nem a de leitura, nem a de cena, nem a aprovada. A decisão errada continua legível na
revisão em que foi tomada, com autor, horário e justificativa. O que a correção adiciona
é um sucessor declarado, com autor, horário e justificativa próprios.

É a mesma forma do [ADR-0019](0019-proposal-refresh-creates-a-new-review-revision.md): o
refino de propostas também não edita nada — cria a revisão seguinte e trava atrás de
issue crítica o que deixou de valer, em vez de reprojetar geometria que um humano aceitou.

## Alternativas

- **Sobrescrever a decisão in place**: rejeitado. Apagaria a única evidência do que foi
  decidido e sobre qual geometria, quebrando a auditoria que sustenta a exportação
  (ADR-0006) e deixando a `provenance` das entidades apontando para um `decision_id` que
  já não descreve o que está gravado.
- **Voltar a leitura para `proposed` e decidir de novo**: rejeitado. Perderia o registro
  de que houve decisão e correção, e faria a segunda decisão parecer a primeira. Também
  reabriria os invariantes de estado (`unresolved` relevante, associação obrigatória)
  sobre uma cena que já usa a leitura.
- **Recusar a correção quando a cena já depende da decisão**: rejeitado pelo usuário do
  domínio. É exatamente o caso do Guaxindiba — o erro só aparece depois do desenho, e
  recusar devolveria o profissional ao refazer-tudo que motivou este ADR. Invalidar para
  frente preserva o trabalho e mostra o que precisa ser refeito.
- **Reprojetar automaticamente a geometria que dependia da decisão antiga**: rejeitado,
  pela mesma razão do ADR-0019. Mover geometria aceita por um humano sem novo ato dele
  inventaria consentimento.

## Consequências

### Positivas

- Erro de transcrição custa uma correção declarada, não o job inteiro; as decisões
  corretas do mesmo lote sobrevivem.
- O histórico fica mais rico, não mais pobre: quem lê a auditoria vê a decisão, a
  correção, quem fez cada uma e por quê.
- A cena nunca fica silenciosamente inconsistente com a leitura: ou é recomputada, ou
  carrega issue crítica que bloqueia o export.

### Negativas

- Uma correção sobre cena traçada exige refazer o traçado daquela parte — trabalho real,
  declarado como blocker em vez de escondido.
- A tela precisa mostrar decisão registrada **e** correção sem convidar ao clique fácil:
  a justificativa nasce vazia e a associação é reconfirmada de propósito.

## Riscos e mitigação

| Risco | Mitigação |
|---|---|
| Correção usada como desfazer casual | Justificativa obrigatória, alvo nominal e no-op recusado (`RECTIFICATION_ALREADY_APPLIED`) |
| Duas correções concorrentes sobre a mesma decisão | `base_version` + `RECTIFICATION_TARGET_STALE` + índice único `(review_revision_id, reading_id)` |
| Geometria sustentada por decisão corrigida chegar ao DXF | Varredura de `provenance.source_ids` em entidades **e** medidas, issue crítica em cena nova, `export_errors()` bloqueia |
| Aprovação ou pacote publicados serem alterados | A correção nunca escreve em revisão existente; a cena nova nasce não aprovada e a aprovação da anterior passa a conflitar por versão |
| Identidade histórica de decisão mudar | `rectifies_decision_id` entra no id canônico **somente** quando presente, com teste de regressão byte a byte |

## Rastreabilidade

- Requirements: relacionado a ADR-0006 (revisão humana e provenance obrigatórias) e
  ADR-0019 (refino cria nova revisão de leitura). Nenhum dos dois é substituído.
- Supersedes: none
- Superseded by: none
