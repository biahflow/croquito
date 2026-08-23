# ADR-0049: A foto de campo entra na revisão pelo job da prancha, e nunca no scene graph

Status: Proposed  
Data: 2026-08-23  
Responsável: Product / Engineering

## Contexto

A [F-032](../features/F-032-app-levantamento-campo/feature.md)
([ADR-0043](0043-app-de-campo-pwa-offline-first.md)) entregou o levantamento de campo: o
técnico fotografa na praça, a foto sobe com digest, fica em `survey_media_records` **já
ancorada** a ponto, elemento ou nota (`MediaAnchor`), e o worker a analisa em
`services/worker/src/croquito_worker/survey_photo_analysis.py` — passe offline de qualidade
sempre, passe pago condicional que lê o que está **escrito** na foto.

Três coisas ficaram sem destino, e são o que a
[F-030](../features/F-030-fotos-do-levantamento-na-revisao/feature.md) precisa decidir:

1. **A foto não pode ser vista pelo escritório.** `SurveyMediaState` (`main.py:1669`)
   devolve `sha256`, `mime_type` e `status`, sem URL — "a tela precisa saber se a foto
   chegou, não onde ela está guardada".
2. **A análise é escrita e nenhuma rota a lê.** O artefato mora em
   `tenants/{tenant}/surveys/{survey}/analysis/{sha256}.json` e não há caminho até ele.
   Inclui o resultado do passe **pago**.
3. **Não existe caminho do levantamento até a jornada de revisão.**
   `services/worker/src/croquito_worker/survey_export.py` diz por escrito que o `job_id` da
   cena de campo é um identificador de namespace e que "**não existe `JobRecord`
   correspondente**: a integração destas observações na jornada do escritório é fatia futura
   (…relação com F-030)".

O obstáculo concreto do item 3 é uma coluna: `jobs.upload_id` é `ForeignKey("uploads.id")`,
`NOT NULL` e `UNIQUE` (`database.py:77`). **Não existe job sem PDF.** Qualquer caminho do
levantamento até a revisão passa por decidir isso.

E há uma pergunta de fundo, que a decisão 2 responde: o que a foto pode virar. Foto de obra
não tem escala. Ela responde "o que é" — muro × alambrado, portão × detalhe — e não responde
"quanto mede". O scene graph inteiro está construído sobre essa distinção
([ADR-0005](0005-canonical-scene-graph.md), [ADR-0006](0006-human-review-and-provenance.md)).

## Decisão

1. **A foto chega à revisão pelo job da prancha, e nenhum job nasce sem PDF.**
   `jobs.upload_id` continua `NOT NULL UNIQUE`. O vínculo é entre o **levantamento** e o
   **job que já existe**, criado a partir do PDF da prancha daquela obra. É o que a cadeia
   real faz: levantamento → croqui → CAD → prancha → PDF → job. A foto é evidência **sobre a
   mesma praça** que a prancha desenha, e a revisão dessa prancha é onde a pergunta "o que é"
   aparece.

2. **Nada vindo de foto entra no `SceneRevision`.** Nem `Entity`, nem `Measurement`, nem
   `Precision.EXACT`, nem `approximate` — nenhuma precisão, porque não há grandeza. É a mesma
   linha que `survey_export.py` já traça ao mandar mídia, notas, GPS e waivers para
   `attachments.json` "para não entrar na cena como se fosse desenho". A foto é vista na
   revisão e não viaja na cena.

3. **O que o humano conclui da foto vira nota de revisão, que já existe.**
   `POST /v1/jobs/{job_id}/review/notes` é o registro de "isto é alambrado, não muro": ato
   humano, rastreável, no vocabulário que a revisão já tem. Nenhuma estrutura nova para
   guardar conclusão de foto, e nenhuma conclusão de máquina gravada sem humano.

4. **O vínculo é muitos-para-muitos, em tabela própria.** Uma praça levantada uma vez pode
   virar duas pranchas; uma prancha pode cobrir dois levantamentos. Coluna em `jobs` ou em
   `survey_records` mentiria sobre a cardinalidade na primeira obra grande. A tabela guarda
   quem vinculou e quando — vincular é ato, não consequência.

5. **A URL assinada da mídia é emitida sob o papel de quem já pode ler o levantamento**, e só
   para mídia `CONFIRMED`. `_require_survey_reader` já admite campo e escritório; mídia
   `PRESIGNED` é bytes que ninguém conferiu, e assinar URL para ela seria oferecer conteúdo
   sem digest validado. URL assinada nunca entra em log, como nas demais.

6. **A análise que já existe passa a ser lida, e nada é reprocessado para isso.** A rota
   serve o artefato como ele está: qualidade sempre; a leitura paga **só quando houve passe
   pago**, e declarada como pulada quando não houve. Ausência de análise é estado honesto.
   Reprocessar levantamento concluído em massa é chamada paga em massa, e continua exigindo
   aprovação humana própria.

7. **A classificação por IA é tarefa nova, sob demanda, e nasce rascunho.** É `PromptTask`
   própria — o que existe hoje lê texto escrito na foto, que é outra coisa —, roda no worker,
   nunca no request path, e **nunca dispara pelo vínculo**: alguém pede. Exige os dois
   portões de sempre (`CROQUITO_REAL_PROVIDERS_ENABLED` e entitlement contratual do tenant,
   [ADR-0012](0012-contractual-ai-processing-entitlements.md)/
   [ADR-0036](0036-autorizacao-de-ia-contratual-sem-allowlist-documental.md)), teto de custo
   declarado, lineage de prompt e modelo por proposta, e eval com gate antes da primeira
   rodada paga ([ADR-0009](0009-golden-dataset-and-evaluation-gates.md)). O que ela produz é
   proposta a confirmar pela decisão 3.

8. **`vision.py` não roda sobre foto de praça.** A razão já está escrita em
   `survey_photo_analysis.py`: Hough e contorno adaptativo foram calibrados para tinta sobre
   papel, e o que encontram numa foto de obra é sombra de grade e junta de piso. Este ADR a
   promove de comentário a decisão, para que ninguém a "melhore" depois.

9. **Mídia vinculada a um job não expira antes do job.** Hoje o bucket tem uma regra de ciclo
   de vida única por `artifact_retention_days` (`infra/main.tf:70`), e a revisão pode
   acontecer depois disso — evidência que some no meio do trabalho é pior que evidência que
   nunca esteve lá. A regra passa a ser por prefixo, e **aplicá-la é ato humano de
   infraestrutura**, com `plan` revisado, fora do que esta decisão executa.

10. **Foto avulsa na revisão percorre o caminho da prancha.** O upload direto na jornada de
    croqui, para a obra que não teve levantamento pelo app, usa presign → confirm com o mesmo
    rigor de digest e tipo do upload de prancha, e aparece na tela **do mesmo jeito** que a
    foto do levantamento. Se as duas tivessem cara diferente, o revisor teria de saber de
    onde veio para saber no que confiar.

## Alternativas

- **Job de campo: tornar `upload_id` nulo e criar `JobRecord` para o levantamento** —
  rejeitada. Torna nula uma FK da tabela mais movimentada do produto, e todo caminho que hoje
  supõe um PDF passaria a tratar a ausência dele. Pior: a revisão do croqui é construída sobre
  páginas renderizadas da prancha — `ReviewPacket` é recorte de prancha —, e um job sem
  prancha abriria a jornada inteira vazia. O ganho seria um identificador; o custo, uma
  jornada que não sabe o que mostrar.
- **Nem job: tela separada onde o escritório lê o levantamento** — rejeitada por perder o
  ponto. A foto vale onde a decisão acontece; noutra aba ela é mais um lugar para consultar
  antes de decidir, que é exatamente o telefonema que a feature quer eliminar.
- **Classificação entrando como `Issue` da cena** — rejeitada: `Issue` participa do portão de
  exportação (`export_errors()`), e opinião de modelo sobre foto não pode chegar perto de
  decidir se um DXF sai. A nota de revisão registra o mesmo sem tocar o portão.
- **Classificar automaticamente toda foto ao vincular** — rejeitada: um levantamento com
  quarenta fotos viraria quarenta chamadas pagas que ninguém pediu. Sob demanda mantém o
  gasto ligado a uma intenção.
- **Coluna `survey_id` em `jobs`** — rejeitada pela cardinalidade (decisão 4).
- **Deixar a retenção como está e avisar o usuário** — rejeitada: a evidência é o produto do
  trabalho de campo, e perdê-la por regra de bucket é perda silenciosa.

## Consequências

### Positivas

- Trabalho já pago passa a render: a análise deixa de ser artefato só de escrita.
- A evidência de campo chega onde a dúvida existe, com a âncora que o técnico registrou.
- O scene graph não muda, e a fronteira "foto não mede" fica escrita em decisão, não em
  comentário.
- O caminho da foto avulsa e o da foto de campo convergem na mesma tela.

### Negativas

- **O levantamento continua sem existir na jornada do escritório por si só**: ele só aparece
  se houver prancha e job. Obra levantada e ainda não desenhada segue invisível ali — custo
  aceito, e a saída é a tela do levantamento que já existe.
- **Uma tabela de vínculo a mais**, e um ato humano a mais na jornada (vincular).
- **A regra de retenção por prefixo é mudança de infraestrutura**, que depende de ato humano
  para valer — até lá, a fragilidade da decisão 9 permanece.
- A classificação por IA nasce sem eval calibrada; até o gate existir, ela não roda pago.

## Riscos e mitigação

| Risco | Mitigação |
|---|---|
| Foto ao lado de uma cota sugerir confirmação de medida | Decisão 2 proíbe qualquer precisão vinda de foto, e o contrato da feature exige teste **negativo** explícito, não ausência de código |
| Classificação plausível e errada (muro × alambrado em contraluz) | Nasce rascunho com lineage; confirmação é ato humano pela decisão 3; eval com gate antes da primeira rodada paga |
| Custo disparado por vínculo | Decisão 7: nunca automático, teto declarado, dois portões de entitlement |
| URL assinada vazando em log ou para outro tenant | Decisão 5: papel de leitura do levantamento, mídia confirmada, tenant do JWT, e a regra de log que já vale para as demais |
| Evidência expirar antes da revisão | Decisão 9, com a ressalva de que o `apply` é ato humano |
| Vínculo errado (foto de outra praça) | Vincular é ato humano registrado com autor e data; desfazer é ato novo, não edição |

## Rastreabilidade

- Feature: [F-030](../features/F-030-fotos-do-levantamento-na-revisao/feature.md)
- Requirements: SEC (isolamento por tenant), NFR de custo de IA
- Relacionados: [ADR-0005](0005-canonical-scene-graph.md),
  [ADR-0006](0006-human-review-and-provenance.md),
  [ADR-0009](0009-golden-dataset-and-evaluation-gates.md),
  [ADR-0012](0012-contractual-ai-processing-entitlements.md),
  [ADR-0036](0036-autorizacao-de-ia-contratual-sem-allowlist-documental.md),
  [ADR-0043](0043-app-de-campo-pwa-offline-first.md)
- Supersedes: none
- Superseded by: none
