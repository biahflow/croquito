# ADR-0049: A evidência de campo entra na revisão pelo job da prancha; foto não mede e medida de trena não é cota

Status: Accepted  
Data: 2026-08-23 (aceito por ato humano na mesma data)  
Responsável: Product / Engineering

## Contexto

A [F-032](../features/F-032-app-levantamento-campo/feature.md)
([ADR-0043](0043-app-de-campo-pwa-offline-first.md)) entregou o levantamento de campo. O
técnico na praça produz duas coisas de naturezas diferentes, e a distinção entre elas é o que
este ADR existe para fixar:

- **fotos**, que sobem com digest, ficam em `survey_media_records` **já ancoradas** a ponto,
  elemento ou nota (`MediaAnchor`), e são analisadas pelo worker
  (`services/worker/src/croquito_worker/survey_photo_analysis.py`) — passe offline de
  qualidade sempre, passe pago condicional que lê o que está **escrito** na foto;
- **medidas**, que são `Measurement` no `SurveyPacket` (`croquito_core.field`), com
  `value_mm` inteiro, `kind`, `instrument`, `status` (`draft` | `confirmed`) e ancoragem a
  pontos ou elemento. É a trena.

Nenhuma das duas alcança a jornada de revisão do escritório.
`services/worker/src/croquito_worker/survey_export.py` diz por escrito que o `job_id` da cena
de campo é um identificador de namespace e que "**não existe `JobRecord` correspondente**: a
integração destas observações na jornada do escritório é fatia futura (…relação com F-030)".

Quatro lacunas concretas, todas verificáveis:

1. **A foto não pode ser vista.** `SurveyMediaState` (`main.py:1669`) devolve `sha256`,
   `mime_type` e `status`, sem URL — "a tela precisa saber se a foto chegou, não onde ela
   está guardada".
2. **A análise é escrita e nenhuma rota a lê.** O artefato mora em
   `tenants/{tenant}/surveys/{survey}/analysis/{sha256}.json`. Inclui o resultado do passe
   **pago**.
3. **A medida de campo não corrobora nada.** Ela existe, com valor real em milímetros, e
   morre na cena de campo — que ninguém abre.
4. **O levantamento legado não tem porta nenhuma.** Sem app, não há pacote, âncora nem
   medida: há um PDF de croqui e fotos soltas. E é dele que vieram Guaxindiba, Toca e Raul
   Campelo.

O obstáculo comum é uma coluna: `jobs.upload_id` é `ForeignKey("uploads.id")`, `NOT NULL` e
`UNIQUE` (`database.py:77`). **Não existe job sem PDF.**

### As duas perguntas que a evidência de campo responde, e que não são a mesma

Esta é a distinção que o ADR fixa, porque confundi-la é o defeito caro:

```text
FOTO      responde "o que é"       muro × alambrado, portão × detalhe
          NÃO responde "quanto"    não tem escala; nenhuma dimensão vem dela

TRENA     responde "quanto mede"   valor real, medido no local
          NÃO é a cota da prancha  é testemunha dela, e pode contradizê-la
```

A foto tem valor no takeoff — que código SCO entra no orçamento — e não na leitura da cota.
Já a medida de campo toca a cota diretamente, e é justamente aí que ela é perigosa: ela é
**outra fonte**, não uma confirmação. `survey_export.py` já traçou a linha ao dizer que
`Precision.EXACT` não nasce ali, porque "medida de trena é evidência de campo, não cota lida
de prancha".

O valor real da medida de campo não é confirmar: é **discordar**. Se a prancha diz 19,75 e a
trena diz 12,40 no mesmo trecho, alguém precisa saber antes do DXF.

### O levantamento legado, que não passou pelo app

Decisão humana de 2026-08-23: **melhorar a geometria das cotas dos levantamentos legados é
prioridade**, e eles são a maioria do que existe hoje — Guaxindiba, Toca e Raul Campelo
vieram assim. Legado não tem `SurveyPacket`, não tem `MediaAnchor` e não tem `Measurement`:
tem um PDF de croqui e, quando muito, fotos soltas no telefone de quem foi a campo.

Duas consequências para o desenho:

- o caminho do **upload avulso** não é um extra para o caso raro; é a porta principal desses
  levantamentos, e precisa nascer junto com a do vínculo, não depois;
- o número medido em campo **existe**, só que escrito: no visor da trena fotografado, no
  bilhete a mão, na anotação sobre o croqui. E o passe pago que a F-032 já roda lê exatamente
  isso — "placa, bilhete a mão, visor de trena". A testemunha do legado entra por essa porta.

## Decisão

1. **A evidência de campo chega à revisão pelo job da prancha, e nenhum job nasce sem PDF.**
   `jobs.upload_id` continua `NOT NULL UNIQUE`. O vínculo é entre o **levantamento** e o
   **job que já existe**, criado a partir do PDF da prancha daquela obra. É o que a cadeia
   real faz: levantamento → croqui → CAD → prancha → PDF → job.

2. **Nada vindo de foto entra no `SceneRevision`.** Nem `Entity`, nem `Measurement`, nem
   precisão nenhuma — não há grandeza. É a mesma linha que `survey_export.py` já traça ao
   mandar mídia, notas, GPS e waivers para `attachments.json` "para não entrar na cena como
   se fosse desenho".

3. **O que o humano conclui da foto vira observação da revisão, fora da cena.** A inspeção
   feita durante o planejamento da F-030 mostrou que `POST /v1/jobs/{job_id}/review/notes`
   cria uma anotação dentro da `SceneRevision`; portanto ele não serve para esta decisão sem
   violar D2. A F-030 cria `POST /v1/jobs/{job_id}/review/field-observations` e persiste o
   ato no snapshot versionado da revisão, sem entidade, camada ou alteração geométrica.

4. **A medida de campo entra como TESTEMUNHA da leitura, nunca como leitura.** Ela é
   observacional do começo ao fim: não confirma cota, não promove precisão, não vira
   `Entity`, não alimenta o solver e não substitui `HumanDecision`. Uma leitura sem decisão
   humana completa continua devolvendo `review_required`, com testemunha ou sem.

5. **A associação medida-de-campo ↔ leitura-da-prancha é ato humano explícito.** Nunca
   inferida de rótulo, de `kind`, de proximidade de coordenada ou de semelhança de valor. É a
   mesma regra que o solver já aplica: "o solver exige associação explícita
   `reading_id → proposal_id` mesmo para leituras confirmadas; proximidade em pixels nunca é
   associação implícita". Uma testemunha associada por adivinhação seria pior que testemunha
   nenhuma, porque discordância falsa treina o revisor a ignorar o aviso.

6. **Divergência entre a cota confirmada e a testemunha é AVISO, nunca veto.** Ela não entra
   em `blockers` e não impede exportação — mesmo tratamento que `suggested_chains` e
   `declared_chains` já recebem, onde "divergência de cadeia é aviso para o revisor, nunca
   veto de exportação". Quem decide continua sendo quem assina a aprovação.

7. **A tolerância da divergência é nomeada e declarada por `kind`, nunca número mágico no
   meio do código.** O valor de cada tolerância é calibrado com dado real e pode mudar sem
   mudar este ADR; o que não pode é existir um limiar anônimo. Enquanto não houver
   calibração, o produto mostra os dois valores lado a lado sem classificar a diferença —
   mostrar é útil desde o primeiro dia, classificar sem calibrar não é.

8. **A testemunha tem duas fontes, e a origem de cada uma é declarada.**
   - **`Measurement` do app**, e só a `confirmed`: `draft` é rascunho do técnico no aparelho,
     e promovê-la atribuiria um peso que quem a registrou não deu.
   - **Valor lido em foto** — visor de trena, bilhete, anotação —, que é a porta do
     levantamento **legado**, sem app. Este chega como **rascunho de leitura de máquina** e
     precisa de confirmação humana do valor **antes** de poder ser associado a qualquer
     leitura: são dois atos, e não um.

   As duas viajam com a origem escrita ao lado do número. Uma testemunha de trena confirmada
   em campo e um número que um modelo leu numa foto não têm o mesmo peso, e a tela não pode
   fazê-las parecer iguais.

9. **A classificação por IA é tarefa nova, sob demanda, e nasce rascunho.** É `PromptTask`
   própria — o que existe hoje lê texto escrito na foto, que é outra coisa —, roda no worker,
   e **nunca dispara pelo vínculo**: alguém pede. Exige os dois portões de sempre
   (`CROQUITO_REAL_PROVIDERS_ENABLED` e entitlement contratual do tenant,
   [ADR-0012](0012-contractual-ai-processing-entitlements.md)/
   [ADR-0036](0036-autorizacao-de-ia-contratual-sem-allowlist-documental.md)), teto de custo
   declarado, lineage de prompt e modelo por proposta, e eval com gate antes da primeira
   rodada paga ([ADR-0009](0009-golden-dataset-and-evaluation-gates.md)). Ela propõe **o que
   é** em categoria fechada (`MURO`, `ALAMBRADO`, `PORTAO`, `PATAMAR`, `EQUIPAMENTOS`,
   `DETALHES`, `UNKNOWN`) mais descrição curta livre; nunca propõe quanto mede.

10. **`vision.py` não roda sobre foto de praça.** A razão já está escrita em
    `survey_photo_analysis.py`: Hough e contorno adaptativo foram calibrados para tinta sobre
    papel, e o que encontram numa foto de obra é sombra de grade e junta de piso. Este ADR a
    promove de comentário a decisão.

11. **O vínculo é muitos-para-muitos, em tabela própria.** Uma praça levantada uma vez pode
    virar duas pranchas; uma prancha pode cobrir dois levantamentos. A tabela guarda quem
    vinculou e quando — vincular é ato, não consequência.

12. **A URL assinada da mídia é emitida sob o papel de quem já pode ler o levantamento**, e
    só para mídia `CONFIRMED`. `_require_survey_reader` já admite campo e escritório; mídia
    `PRESIGNED` é bytes que ninguém conferiu. URL assinada nunca entra em log.

13. **A análise que já existe passa a ser lida, e nada é reprocessado para isso.** Qualidade
    sempre; a leitura paga só quando houve passe pago, declarada como pulada quando não
    houve. Ausência de análise é estado honesto. Reprocessar levantamento concluído em massa
    é chamada paga em massa, e continua exigindo aprovação humana própria.

14. **A foto avulsa é caminho de primeira classe, não exceção.** Ela percorre presign →
    confirm com o mesmo rigor de digest e tipo do upload de prancha, e aparece na revisão
    **do mesmo jeito** que a foto do levantamento — com a diferença de que sua âncora é
    declarada pelo revisor, porque não houve técnico para ancorá-la. Se as duas tivessem cara
    diferente, o revisor teria de saber de onde veio para saber no que confiar. É por ela que
    o levantamento legado entra, e por isso ela nasce na mesma fatia do vínculo.

15. **Evidência vinculada a um job não expira antes do job.** Hoje o bucket tem uma regra de
    ciclo de vida única por `artifact_retention_days` (`infra/main.tf:70`), e a revisão pode
    acontecer depois disso. A regra passa a ser por prefixo, e **aplicá-la é ato humano de
    infraestrutura**, com `plan` revisado.

16. **Uma leitura pode carregar várias testemunhas.** Cada associação continua sendo ato
    humano separado, com origem, autoria e instante próprios. A tela as empilha e calcula a
    diferença de cada uma; não resume uma faixa nem escolhe uma testemunha vencedora.

## Emenda 1 — decisões de execução da F-030 (2026-08-23)

Aceita por ato humano na autorização de implementação da F-030. Corrige a referência
incorreta de D3 ao endpoint de nota da cena e fixa as decisões que o Design Approval Package
revisão 2 havia deixado abertas:

- foto amplia em modal dentro da revisão, com ação secundária para abrir o original;
- todas as fotos aparecem por padrão e o filtro por âncora é manual, sem associação inferida;
- múltiplas testemunhas são permitidas e exibidas separadamente;
- enquanto as tolerâncias por `kind` não forem calibradas, a tela mostra somente os dois
  valores e a diferença, sem `concorda`, `discorda` ou veste de alerta;
- a observação humana sobre classificação fica fora da `SceneRevision`.

## Alternativas

- **Job de campo: tornar `upload_id` nulo e criar `JobRecord` para o levantamento** —
  rejeitada. Torna nula uma FK da tabela mais movimentada do produto, e a revisão do croqui é
  construída sobre páginas renderizadas da prancha (`ReviewPacket` é recorte de prancha): um
  job sem prancha abriria a jornada inteira vazia.
- **A medida de campo confirmar a cota automaticamente quando bater dentro da tolerância** —
  rejeitada, e é a alternativa mais tentadora. Ela transformaria uma testemunha em decisão, e
  o produto inteiro é construído sobre o oposto: `HumanDecision` completo, ou
  `review_required`. Além disso premiaria o caso fácil (bateu) e deixaria o difícil (não
  bateu) exatamente como está.
- **A medida de campo entrar como `Measurement` da cena** — rejeitada: ela viraria dado
  geométrico e disputaria com a cota lida, quando o que se quer é justamente comparar as
  duas mantendo a origem de cada uma legível.
- **Associar testemunha por proximidade ou por `kind`** — rejeitada pela decisão 5. É o mesmo
  erro que o solver já se recusa a cometer com proposta e cota.
- **Divergência como blocker de exportação** — rejeitada: a prancha é a fonte contratual do
  desenho, e uma trena discordando dela é informação para o revisor, não veto automático. A
  decisão 6 mantém a autoridade onde ela já está.
- **Classificação entrando como `Issue` da cena** — rejeitada: `Issue` participa do portão de
  exportação (`export_errors()`), e opinião de modelo sobre foto não pode chegar perto de
  decidir se um DXF sai.
- **Classificar automaticamente toda foto ao vincular** — rejeitada: um levantamento com
  quarenta fotos viraria quarenta chamadas pagas que ninguém pediu.
- **Deixar a retenção como está e avisar o usuário** — rejeitada: perder evidência por regra
  de bucket é perda silenciosa.
- **Aceitar PDF como documento de evidência avulsa** — rejeitada por decisão humana de
  2026-08-23, e há razão de desenho por trás: num levantamento legado o croqui de campo **é**
  a fonte da cota, e deixá-lo virar testemunha da leitura que ele próprio produziu faria o
  número testemunhar a si mesmo. Testemunha só vale vinda de documento diferente do que foi
  lido, e distinguir os dois casos com segurança não é trivial. A evidência avulsa fica em
  **imagem**.
- **Sintetizar `SurveyPacket`, `MediaAnchor` e `Measurement` a partir do croqui legado** —
  rejeitada: criaria um segundo modelo geométrico ao lado do `SceneRevision`, que é a única
  fonte geométrica do produto. `SurveyPacket` é formato de captura em campo, e extrair
  geometria do croqui já é o que o pipeline do croqui faz — o resultado continua caindo no
  scene graph, não num modelo paralelo.

## Consequências

### Positivas

- Trabalho já pago passa a render: a análise deixa de ser artefato só de escrita.
- A evidência de campo chega onde a dúvida existe, com a âncora que o técnico registrou.
- **A cota da prancha ganha uma testemunha independente**, e a discordância — que é o caso
  que hoje ninguém vê — passa a aparecer antes do DXF.
- **O levantamento legado é atendido desde a primeira fatia**, pelo upload avulso e pelo
  número escrito na foto, em vez de esperar uma feature que só serviria quem já usa o app.
- O scene graph não muda, e as duas fronteiras ficam escritas em decisão, não em comentário:
  foto não mede, trena não é cota.

### Negativas

- **O levantamento continua sem existir na jornada do escritório por si só**: ele só aparece
  se houver prancha e job. Obra levantada e ainda não desenhada segue invisível ali.
- **Associar testemunha é trabalho manual**, item a item, e o produto não o abrevia por
  adivinhação. É o custo direto da decisão 5.
- **No legado são dois atos, não um**: confirmar o valor que a máquina leu na foto, e só então
  associá-lo a uma leitura. Mais trabalho do que no caminho do app, e é o preço de não deixar
  um número lido por modelo virar testemunha sozinho.
- **Sem tolerância calibrada, o produto mostra a diferença e não a classifica** (decisão 7).
  Menos ajuda no começo, e nenhuma classificação errada.
- **Uma tabela de vínculo a mais**, e dois atos humanos novos na jornada: vincular e associar.
- A classificação por IA nasce sem eval calibrada; até o gate existir, ela não roda pago.

## Riscos e mitigação

| Risco | Mitigação |
|---|---|
| Foto ao lado de uma cota sugerir confirmação de medida | Decisão 2 proíbe qualquer precisão vinda de foto, e o contrato da feature exige teste **negativo** explícito |
| Testemunha ser tomada por cota, e a trena virar a fonte do desenho | Decisões 4 e 6: observacional, sem promoção de precisão, sem blocker; a origem de cada número fica escrita ao lado dele |
| Divergência falsa por associação errada | Decisão 5: associação é ato humano explícito, e desassociar é ato novo |
| Tolerância arbitrária treinar o revisor a ignorar o aviso | Decisão 7: sem calibração, mostra-se a diferença sem classificá-la |
| Classificação plausível e errada (muro × alambrado em contraluz) | Nasce rascunho com lineage; confirmação é ato humano pela decisão 3; eval com gate antes da primeira rodada paga |
| Custo disparado por vínculo | Decisão 9: nunca automático, teto declarado, dois portões de entitlement |
| URL assinada vazando em log ou para outro tenant | Decisão 12 |
| Evidência expirar antes da revisão | Decisão 14, com a ressalva de que o `apply` é ato humano |

## Rastreabilidade

- Feature: [F-030](../features/F-030-levantamento-de-campo-na-revisao/feature.md)
- Requirements: SEC (isolamento por tenant), NFR de custo de IA
- Relacionados: [ADR-0005](0005-canonical-scene-graph.md),
  [ADR-0006](0006-human-review-and-provenance.md),
  [ADR-0009](0009-golden-dataset-and-evaluation-gates.md),
  [ADR-0012](0012-contractual-ai-processing-entitlements.md),
  [ADR-0036](0036-autorizacao-de-ia-contratual-sem-allowlist-documental.md),
  [ADR-0043](0043-app-de-campo-pwa-offline-first.md)
- Supersedes: none
- Superseded by: none
