# F-030 — O levantamento de campo na jornada de revisão: a foto e a medida

## Status

`READY_FOR_BUILD`

> Selecionada por decisão humana de 2026-08-23, saindo de `READY_FOR_SPEC`. Estava registrada
> sem contrato desde 2026-08-21, quando nasceu por seleção humana na sessão da
> [F-029](../F-029-auto-associacao-confianca/feature.md).
>
> **A feature foi ampliada por decisão humana no mesmo dia**, depois de uma pergunta que
> mudou o recorte: *as fotos ajudam o sistema a identificar melhor as cotas?* A resposta é
> não — foto não tem escala. Mas a pergunta expôs que o levantamento produz **duas** coisas,
> e que a outra, a medida de trena, **toca a cota diretamente**. As duas estavam presas no
> mesmo lugar, e agora saem juntas. Ver **Problem** e **Split**.
>
> Duas escolhas humanas de 2026-08-23 já fixadas: as fotos chegam **pelos dois caminhos**
> (vínculo com o levantamento e upload avulso), e a **classificação por IA entra**.
>
> **Os dois gates humanos foram cumpridos em 2026-08-23**, em atos separados: o
> [ADR-0049](../../adr/0049-evidencia-de-campo-na-revisao-do-escritorio.md) foi **aceito** e o
> **Design Approval Package** foi **aprovado na revisão 3** — a revisão 2 foi a primeira
> aprovada e a autorização de implementação incorporou as decisões finais. Ver **Human Gates**.
>
> O plano foi aprovado para execução no mesmo dia. A emenda 1 do ADR-0049 e a revisão 3 do
> Design Approval Package registram as decisões finais de interação, cardinalidade,
> observação fora da cena e divergência sem classificação. Os oito Task Contracts estão em
> [tasks/](tasks/).

## Classification

`INTERFACE_CHANGE` — a evidência de campo passa a existir na tela de revisão do croqui, ao
lado da decisão de leitura, e ganha upload próprio. Superfície nova, percebida por humano.

## Priority

`HIGH` — hoje existe trabalho pago rodando cujo resultado **ninguém consegue ler**, evidência
de campo que **ninguém consegue ver**, e uma medida real da obra que **não corrobora nada**.
As três já custaram e não rendem até esta feature.

## Problem

### O levantamento produz duas coisas, e elas respondem perguntas diferentes

```text
FOTO      responde "o que é"       muro × alambrado, portão × detalhe
          NÃO responde "quanto"    não tem escala; nenhuma dimensão vem dela

TRENA     responde "quanto mede"   valor real, medido no local pelo técnico
          NÃO é a cota da prancha  é testemunha dela, e pode contradizê-la
```

Confundir as duas é o defeito caro. A foto vale no takeoff — que código SCO entra no
orçamento — e não na leitura da cota. A medida de campo toca a cota, e é exatamente por isso
que ela é perigosa: é **outra fonte**, não uma confirmação.

### O que a F-032 já entregou, e o registro anterior não sabia

O roadmap descrevia esta feature como "upload + storage + retenção + chamada paga". Três
dessas quatro coisas já existem, e verificáveis:

- as fotos chegam ao servidor com digest e ficam em `survey_media_records`, **já ancoradas** a
  ponto, elemento ou nota pelo `MediaAnchor` (`packages/core/src/croquito_core/field.py:115`);
- o worker as analisa em `services/worker/src/croquito_worker/survey_photo_analysis.py`:
  passe offline de qualidade sempre e passe **pago** condicional que lê o que está *escrito*
  na foto;
- as medidas existem como `Measurement` no `SurveyPacket`, com `value_mm` inteiro, `kind`,
  `instrument` e `status` (`draft` | `confirmed`);
- `GET /v1/surveys/{id}` já lê com papel de escritório, e o docstring diz por quê: "o
  escritório consulta o que veio do campo antes de transformá-lo em observação do pipeline".

### O que falta, e é onde o valor está preso

1. **A foto não pode ser vista.** `SurveyMediaState`
   (`services/api/src/croquito_api/main.py:1669`) devolve `sha256`, `mime_type` e `status`,
   sem URL — "a tela precisa saber se a foto chegou, não onde ela está guardada".
2. **A análise é escrita e nunca lida.** O artefato vive em
   `tenants/{tenant}/surveys/{survey}/analysis/{sha256}.json` e **nenhuma rota o serve**.
   Inclui o resultado do passe pago: dinheiro gasto em leitura que não chega a ninguém.
3. **A medida de campo não corrobora nada.** Ela morre na cena de campo, que ninguém abre. A
   cota da prancha continua sendo lida sem nenhuma testemunha independente — e quando a
   prancha está errada, ninguém descobre antes do DXF.
4. **A jornada do escritório não alcança o levantamento.** `survey_export.py` diz com todas as
   letras que o `job_id` da cena de campo é um namespace e que "**não existe `JobRecord`
   correspondente**: a integração destas observações na jornada do escritório é fatia futura
   (…relação com F-030)". É esta feature que foi nomeada ali.

### E o legado, que é a maior parte do que existe

Decisão humana de 2026-08-23: **melhorar a geometria das cotas dos levantamentos legados é
prioridade**. Legado é o que não passou pelo app — Guaxindiba, Toca e Raul Campelo vieram
assim. Ele não tem `SurveyPacket`, não tem `MediaAnchor` e não tem `Measurement`: tem um PDF
de croqui e, quando muito, fotos soltas no telefone de quem foi a campo.

Isso muda duas coisas no recorte. O **upload avulso** deixa de ser extra para caso raro e vira
porta principal, nascendo na mesma fatia do vínculo. E o número medido em campo, que no legado
não existe como dado, **existe escrito**: no visor da trena fotografado, no bilhete a mão. O
passe pago que a F-032 já roda lê exatamente isso — "placa, bilhete a mão, visor de trena" —,
e é por ali que a testemunha do legado entra.

## Desired Outcome

Quem revisa no escritório vê a foto que o técnico tirou, ancorada onde ele a ancorou, com a
qualidade e a leitura que o servidor já apurou — e vê, ao lado da cota que está confirmando,
o que a trena mediu no mesmo trecho.

Quando os dois números discordam, o revisor sabe **antes** do DXF. E nada disso decide por
ele: a foto não mede, a trena não é cota, e quem confirma continua sendo pessoa.

## Scope

### Split em três fatias (decisão humana de 2026-08-23)

- **Fatia 1 — ver, pelas duas portas.** A evidência de campo na revisão, vinda tanto do
  levantamento vinculado (foto ancorada, análise, medidas confirmadas) quanto do **upload
  avulso**, que é a porta do levantamento legado. URL assinada da mídia para papel de
  escritório e leitura do artefato de análise que já existe. Nenhuma chamada paga nova: é a
  fatia que destrava o que já foi pago.
- **Fatia 2 — testemunhar.** Associar um valor medido a uma leitura da prancha, por ato
  humano explícito, e mostrar os dois lado a lado com a diferença. Duas fontes de testemunha:
  a `Measurement` confirmada do app, e o **valor lido em foto** — visor de trena, bilhete,
  anotação —, que no legado precisa de confirmação humana do valor **antes** de poder ser
  associado. É a fatia que toca a cota.
- **Fatia 3 — classificar.** Provider multimodal que propõe **o que é** e corrobora
  topologia. `PromptTask` própria, contrato de prompt, rota no Model Routing, eval com gate e
  custo declarado. O que a F-032 faz hoje é ler **texto escrito** na foto, o que é outra
  tarefa.

As fatias 2 e 3 dependem da 1: sem lugar na tela onde a evidência aparece, não há onde pôr
nem a testemunha nem a classificação.

### Invariantes que atravessam as três

Nenhuma é negociável, e todas já são regra do sistema:

- **Foto não tem escala, logo não tem medida.** Nada vindo de foto vira `Measurement`
  confirmada, `Entity` métrica ou `Precision.EXACT`.
- **Medida de campo é testemunha, nunca leitura.** Não confirma cota, não promove precisão,
  não alimenta o solver e não substitui `HumanDecision`. `survey_export.py` já dizia por quê:
  "medida de trena é evidência de campo, não cota lida de prancha".
- **A testemunha declara a sua origem.** Trena confirmada em campo e número que um modelo leu
  numa foto não têm o mesmo peso, e a tela não pode fazê-los parecer iguais. O valor lido em
  foto é rascunho até um humano confirmá-lo, e só então pode ser associado.
- **A associação testemunha ↔ leitura é ato humano explícito**, nunca inferida de rótulo,
  `kind`, proximidade ou semelhança de valor. É a mesma regra que o solver já aplica a
  proposta e cota: "proximidade em pixels nunca é associação implícita".
- **Divergência é aviso, nunca veto.** Não entra em `blockers` e não impede exportação —
  mesmo tratamento que `suggested_chains` e `declared_chains` já recebem.
- **Classificação é observação, nunca decisão.** Nasce rascunho a confirmar por humano e a
  conclusão fica no snapshot da revisão, fora da `SceneRevision`.
- **Fora do score determinístico da F-029** — decisão registrada no roadmap em 2026-08-21.
- **`vision.py` não roda sobre foto de praça.** O motivo está escrito em
  `survey_photo_analysis.py`.
- **Chamada paga exige os dois portões de sempre**: `CROQUITO_REAL_PROVIDERS_ENABLED` e
  entitlement contratual ativo do tenant.
- **Log nunca leva imagem nem texto integral** — id opaco, etapa, duração, custo e contagem.

## Out of Scope

- **Medida a partir de foto**, por qualquer técnica — fotogrametria, referência de objeto
  conhecido, escala declarada pelo técnico. É a fronteira da feature, não uma limitação
  temporária.
- **Confirmar cota automaticamente porque a trena bateu.** Rejeitado no ADR-0049:
  transformaria testemunha em decisão, premiaria o caso fácil e deixaria o difícil como está.
- **Reprocessar levantamento já concluído** para gerar análise que não existe: é chamada paga
  em massa, que exige aprovação humana própria.
- **Alterar o levantamento pelo escritório.** `GET /v1/surveys/{id}` lê e não escreve, e
  continua assim: corrigir campo é ato de campo.
- **Áudio e transcrição.** A F-032 já os trata; trazê-los para a revisão é feature própria.
- **PDF como documento de evidência.** Decisão humana de 2026-08-23: a evidência avulsa é
  **imagem**. O croqui legado em PDF continua entrando pelo caminho normal de job. O motivo
  de não bastar "aceitar PDF também" está no risco da **circularidade** abaixo.
- **Sintetizar `SurveyPacket`, `MediaAnchor` ou `Measurement` a partir do croqui legado.**
  Daria simetria com o app, e criaria um **segundo modelo geométrico** ao lado do
  `SceneRevision`, que é a única fonte geométrica do produto. `SurveyPacket` é formato de
  captura em campo, não um segundo lugar para guardar geometria; extrair do croqui já é o que
  o pipeline do croqui faz, e o resultado continua caindo no scene graph.
- **Calibrar as tolerâncias de divergência** com dado real — o mecanismo entra aqui, o valor
  se calibra depois (ADR-0049 decisão 7).
- Retenção diferenciada por tipo de artefato — ver Unknown 4.

## Acceptance Criteria

1. `make check` e `make test` verdes; goldens intocados.
2. Jornada de revisão **sem** levantamento vinculado se comporta exatamente como hoje.
3. A URL assinada da mídia só é emitida para papel de escritório ou de campo do **mesmo
   tenant**, e nunca aparece em log; mídia `PRESIGNED` não ganha URL.
4. A análise já gravada é lida e exibida com o que ela de fato tem — qualidade sempre, leitura
   paga só quando houve passe pago, declarada como pulada quando não houve. Ausência de
   análise é estado honesto, não erro.
5. Só medida de campo `confirmed` é oferecida como testemunha; `draft` não aparece. Valor
   lido em foto só se torna testemunha **depois** de um humano confirmar o valor — dois atos,
   e há teste que prova que o primeiro sozinho não basta.
6. Associar testemunha a uma leitura é ato humano explícito, e **nenhum caminho** a infere de
   proximidade, rótulo, `kind` ou valor — coberto por teste negativo.
7. Com testemunha associada, a leitura mostra os dois valores e a diferença; a divergência
   **não** entra em `blockers` e **não** impede exportação — coberto por teste.
8. Testemunha não promove precisão: leitura sem `HumanDecision` completo continua devolvendo
   `review_required`, e nada vira `exact` por causa dela — teste negativo explícito.
9. Foto avulsa percorre presign → confirm → exibição com o mesmo rigor de digest do upload de
   prancha, recusa tipo fora da lista, e aparece na revisão **com a mesma composição** da foto
   do levantamento — a diferença é a âncora ser declarada pelo revisor, e isso fica escrito.
10. A classificação da fatia 3 nasce rascunho, com lineage de prompt e modelo por proposta, e
    nenhuma delas altera cena, precisão, blocker ou exportação sem ato humano.
11. Nenhum caminho novo produz medida a partir de foto — teste negativo explícito.
12. Eval da fatia 3 com gate declarado antes da primeira rodada paga, no molde de
    [Evaluation Strategy](../../ai/EVALUATION_STRATEGY.md).
13. As telas correspondem à revisão aprovada do Design Approval Package.

## Constraints

- `tenant_id` sempre do JWT; evidência de outro tenant é `404`, não `403`.
- Fail-closed: análise ilegível, digest divergente ou mídia não confirmada não são exibidas
  como se estivessem boas.
- Custo declarado e limitado, no molde de `CROQUITO_AI_MAX_ESTIMATED_COST_USD`.
- A ancoragem exibida é a que o campo registrou; o escritório não reancora por inferência.
- Tolerância de divergência é **nomeada e declarada por `kind`** — nunca número mágico no meio
  do código. Sem calibração, o produto mostra a diferença e não a classifica.
- Cor nunca é o único indicador.

## Dependencies

- [F-032](../F-032-app-levantamento-campo/feature.md) e o
  [ADR-0043](../../adr/0043-app-de-campo-pwa-offline-first.md) — a foto, a âncora, a análise e
  a medida vêm de lá. Entregue, em `READY_FOR_HUMAN_REVIEW`.
- [F-012](../F-012-operacao-saas-autorizacao-ia/feature.md) e o
  [ADR-0036](../../adr/0036-autorizacao-de-ia-contratual-sem-allowlist-documental.md) — o
  entitlement de IA por tenant é o portão da fatia 3.
- [F-029](../F-029-auto-associacao-confianca/feature.md) — a fronteira com o score
  determinístico é declarada contra ela.

## Unknowns

Os três primeiros foram **decididos** pelo
[ADR-0049](../../adr/0049-evidencia-de-campo-na-revisao-do-escritorio.md), aceito por ato
humano em 2026-08-23. Ficam registrados com a pergunta original e o que a decisão respondeu.

1. **Como o levantamento alcança a jornada do escritório.** `jobs.upload_id` é `NOT NULL` e
   `UNIQUE` (`database.py:77`): não existe job sem PDF.
   → **Decidido** — ADR-0049, decisões 1 e 11: vínculo a um job de prancha que já existe, em tabela
   muitos-para-muitos. Job sem PDF abriria a revisão vazia, porque `ReviewPacket` é recorte de
   prancha.
2. **O que a medida de campo pode fazer com a cota.** Corroborar? Confirmar? Bloquear?
   → **Decidido** — ADR-0049, decisões 4, 5 e 6: testemunha observacional, associada por ato humano
   explícito, e divergência é **aviso** que não entra em `blockers`. Confirmação automática
   por tolerância foi explicitamente rejeitada.
3. **A classificação entra no scene graph ou fica fora?**
   → **Decidido** — ADR-0049, decisões 2 e 3 e emenda 1: fora — e o que o humano conclui vira
   **observação versionada da revisão**, em rota própria. `Issue` foi recusado porque participa
   do portão de exportação; o endpoint antigo de nota também foi recusado porque altera a cena.
4. **Retenção.** O bucket tem expiração única por `artifact_retention_days`
   (`infra/main.tf:70`), então a evidência morre com o resto, e a revisão pode acontecer
   depois.
   → **Decidido** — ADR-0049, decisão 15: regra por prefixo, e **aplicá-la é ato humano de
   infraestrutura**. Até lá a fragilidade permanece.
5. **O valor de cada tolerância de divergência** — sai da calibração com dado real, não deste
   contrato nem do ADR. Até existir, mostra-se a diferença sem classificá-la.
6. **Qual modelo e qual prompt** para a fatia 3 — decidido no plano: tarefa
   `field-photo-classification@1.0.0`, Anthropic `claude-opus-5` como braço primário e
   categoria fechada mais descrição livre, sob o
   [protocolo de mudança de prompt](../../ai/PROMPT_CHANGE_PROTOCOL.md).

## Risks

- **A testemunha ser tomada por cota.** O maior risco da feature ampliada: dois números na
  mesma tela, e o de baixo é da trena. Se a origem de cada um não estiver escrita ao lado
  dele, a medida de campo vira fonte do desenho — que é exatamente o que
  `survey_export.py` recusou fazer.
- **Divergência falsa por associação errada** treina o revisor a ignorar o aviso, que é o
  pior resultado possível: pior que não ter aviso. Daí a associação ser ato humano.
- **Circularidade no legado.** Num levantamento legado o croqui de campo **é** a fonte da
  cota. Se o mesmo documento que produziu a leitura virar testemunha dela, o número testemunha
  a si mesmo: dois campos na tela, uma fonte só, e corroboração falsa. A testemunha só vale
  vinda de documento diferente do que foi lido — o croqui manuscrito contra a prancha em CAD,
  a caderneta, a foto do visor da trena. Mitigação: a origem viaja escrita ao lado do número,
  e o produto não oferece como testemunha o que saiu da própria prancha em revisão.
- **A foto é convincente e não mede.** Uma imagem ao lado de uma cota sugere confirmação que
  ela não fornece. Mitigação é de tela e de contrato, e o critério 11 exige teste negativo.
- **Classificação plausível e errada.** Muro × alambrado é fácil de acertar em foto boa e
  fácil de errar em contraluz. Por isso rascunho com lineage e eval com gate.
- **Custo que ninguém pediu**: quarenta fotos viram quarenta chamadas se a fatia 3 disparar
  sozinha.
- **Duas casas para foto de obra** desde a fatia 1 — a do levantamento e a avulsa.
- **Evidência expirada** (Unknown 4).

## Human Gates

1. **`ARCHITECTURE_DECISION_REQUIRED`** — ✅ **cumprido em 2026-08-23**. O
   [ADR-0049](../../adr/0049-evidencia-de-campo-na-revisao-do-escritorio.md) foi **aceito por
   ato humano**.
2. **`DESIGN_APPROVAL_REQUIRED`** — ✅ **cumprido em 2026-08-23**. O
   [Design Approval Package](mock/README.md) foi **aprovado na revisão 3**. A revisão 2 havia
   sido aprovada antes da autorização de implementação; a 3 incorpora modal, filtro manual,
   múltiplas testemunhas, diferença neutra e observação fora da cena, conforme
   [design-approval](../../engineering-os/workflows/design-approval.md).

A primeira rodada paga da fatia 3 foi autorizada no plano de execução: seis fotos próprias,
uma execução por foto, reserva de US$ 0,75 por chamada e teto absoluto de US$ 5,00. A execução
continua condicionada ao gate offline e ao recebimento do corpus rotulado fora do Git.

## References

- [ADR-0043 — app de campo PWA offline-first](../../adr/0043-app-de-campo-pwa-offline-first.md)
- [ADR-0036 — autorização de IA contratual](../../adr/0036-autorizacao-de-ia-contratual-sem-allowlist-documental.md)
- [Model Routing](../../ai/MODEL_ROUTING.md), [Prompt Contracts](../../ai/PROMPT_CONTRACTS.md),
  [Evaluation Strategy](../../ai/EVALUATION_STRATEGY.md)
- [Human in the loop](../../ai/HUMAN_IN_THE_LOOP.md)
- [Fluxo do sistema](../../architecture/FLUXO_DO_SISTEMA.md)
