# F-030 — Fotos do levantamento na jornada de revisão

## Status

`BLOCKED`

> Selecionada por decisão humana de 2026-08-23, saindo de `READY_FOR_SPEC`. Estava
> registrada sem contrato desde 2026-08-21, quando nasceu por seleção humana na sessão da
> [F-029](../F-029-auto-associacao-confianca/feature.md).
>
> A especificação encontrou a feature **menor do que o registro anterior supunha em três
> quartos, e maior num**: a [F-032](../F-032-app-levantamento-campo/feature.md) já entregou
> armazenamento, ancoragem e o passe de análise. Ver **Problem**.
>
> Duas escolhas humanas de 2026-08-23 fixaram o recorte e estão em `Split`: as fotos chegam
> **pelos dois caminhos** — vínculo com o levantamento e upload avulso —, e a
> **classificação por IA entra**, não fica só o "ver e decidir".
>
> Dois gates humanos precedem o planejamento e são o que a mantém `BLOCKED`. Ver
> **Human Gates**.

## Classification

`INTERFACE_CHANGE` — a foto passa a existir na tela de revisão do croqui, ao lado da decisão
de leitura, e ganha upload próprio. Superfície nova, percebida por humano.

## Priority

`HIGH` — hoje existe trabalho pago rodando cujo resultado **ninguém consegue ler**, e
evidência de campo que **ninguém consegue ver**. As duas coisas já custaram e não rendem
nada até esta feature.

## Problem

### O que a F-032 já entregou, e o registro anterior não sabia

O roadmap descrevia a F-030 como "upload + storage + retenção + chamada paga". Três dessas
quatro coisas já existem, e verificáveis:

- as fotos chegam ao servidor com digest e ficam em `survey_media_records`, **já ancoradas** a
  ponto, elemento ou nota pelo `MediaAnchor` (`packages/core/src/croquito_core/field.py:115`);
- o worker as analisa em `services/worker/src/croquito_worker/survey_photo_analysis.py`:
  passe offline de qualidade sempre (nitidez, exposição, dimensões) e passe **pago**
  condicional que lê o que está *escrito* na foto — placa, bilhete, visor de trena;
- o índice `attachments.json` (`survey_export.py`) já carrega mídia ancorada, notas, GPS,
  contexto de chegada e waivers, deliberadamente **fora** da cena, "para não entrar como se
  fosse desenho";
- `GET /v1/surveys/{id}` já lê com papel de escritório, e o docstring diz por quê: "o
  escritório consulta o que veio do campo antes de transformá-lo em observação do pipeline".

### O que falta, e é onde o valor está preso

1. **A foto não pode ser vista.** `SurveyMediaState`
   (`services/api/src/croquito_api/main.py:1669`) devolve `sha256`, `mime_type` e `status`,
   sem URL — "a tela precisa saber se a foto chegou, não onde ela está guardada". O
   escritório sabe que a foto existe e não a abre.
2. **A análise é escrita e nunca lida.** O artefato vive em
   `tenants/{tenant}/surveys/{survey}/analysis/{sha256}.json` e **nenhuma rota o serve**.
   Inclui o resultado do passe pago: dinheiro gasto em leitura que não chega a ninguém.
3. **A jornada do escritório não alcança o levantamento.** `survey_export.py` diz com todas
   as letras que o `job_id` da cena de campo é um namespace e que "**não existe `JobRecord`
   correspondente**: a integração destas observações na jornada do escritório é fatia futura
   (…relação com F-030)". É esta feature que foi nomeada ali.

### E a pergunta que a foto responde

Foto resolve **"o que é"** — muro × alambrado, portão × detalhe, piso × canteiro — que é
exatamente a dúvida que hoje o revisor resolve por memória ou telefonema. O que ela **não**
faz é medir: sem escala não há dimensão, e essa fronteira é o que mantém o scene graph de pé.

## Desired Outcome

Quem revisa no escritório vê a foto que o técnico tirou, ancorada onde ele a ancorou, com a
qualidade e a leitura que o servidor já apurou — e, quando a classificação estiver ligada,
com a proposta de "o que é" ao lado, sempre como rascunho a confirmar.

Nada disso vira medida, geometria ou decisão automática.

## Scope

### Split em três fatias (decisão humana de 2026-08-23)

- **Fatia 1 — ver.** O vínculo entre a jornada de revisão e o levantamento, a URL assinada
  da mídia para papel de escritório, e a leitura do artefato de análise que já existe.
  Nenhuma chamada paga nova: é a fatia que destrava o que já foi pago.
- **Fatia 2 — subir.** Upload de foto avulsa na própria jornada de revisão, para a obra que
  não teve levantamento pelo app. Storage, digest e retenção próprios, no molde do upload de
  prancha.
- **Fatia 3 — classificar.** Provider multimodal que propõe **o que é** e corrobora
  topologia. É trabalho de IA novo: `PromptTask` própria, contrato de prompt, rota no
  Model Routing, eval com gate e custo declarado. O que a F-032 faz hoje é ler **texto
  escrito** na foto, o que é outra tarefa.

A ordem é essa e as fatias 2 e 3 dependem da 1: sem lugar na tela onde a foto aparece, não há
onde pôr nem a foto avulsa nem a classificação.

### Invariantes que atravessam as três

Nenhuma delas é negociável e todas já são regra do sistema, não invenção deste contrato:

- **Foto não tem escala, logo não tem medida.** Nada vindo de foto vira `Measurement`
  confirmada, `Entity` métrica ou `Precision.EXACT`. É a mesma linha que `survey_export.py`
  já traça para a medida de trena.
- **Classificação é observação, nunca decisão.** Entra como rascunho a confirmar por humano,
  como toda leitura de provider no produto.
- **Fora do score determinístico da F-029** — decisão registrada no roadmap em 2026-08-21:
  o score mede o que é determinístico, e foto não é.
- **`vision.py` não roda sobre foto de praça.** O motivo está escrito em
  `survey_photo_analysis.py`: Hough e contorno adaptativo foram calibrados para tinta sobre
  papel, e o que encontram numa foto de obra é sombra de grade e junta de piso — "proposta
  ruim não é proposta barata".
- **Chamada paga exige os dois portões de sempre**: `CROQUITO_REAL_PROVIDERS_ENABLED` no
  ambiente e entitlement contratual ativo do tenant. Upload normal não chama provider.
- **Log nunca leva imagem nem texto integral** — id opaco, etapa, duração, custo e contagem.

## Out of Scope

- **Medida a partir de foto**, por qualquer técnica — fotogrametria, referência de objeto
  conhecido, escala declarada pelo técnico. É a fronteira da feature, não uma limitação
  temporária.
- **Reprocessar levantamento já concluído** para gerar análise que não existe: a análise é
  publicada na confirmação da mídia, e refazê-la em massa é chamada paga em massa, que exige
  aprovação humana própria.
- **Alterar o levantamento pelo escritório.** `GET /v1/surveys/{id}` lê e não escreve, e
  continua assim: corrigir campo é ato de campo.
- **Áudio e transcrição.** A F-032 já os trata; esta feature é sobre foto.
- **Mudar o que a F-032 analisa** (leitura de texto escrito na foto).
- Retenção diferenciada por tipo de artefato — ver Unknown 4, que a nomeia sem resolvê-la.

## Acceptance Criteria

1. `make check` e `make test` verdes; goldens intocados.
2. Jornada de revisão **sem** levantamento vinculado se comporta exatamente como hoje.
3. A URL assinada da mídia só é emitida para papel de escritório ou de campo do **mesmo
   tenant**, e nunca aparece em log; mídia `PRESIGNED` (bytes ainda não confirmados) não
   ganha URL.
4. A análise já gravada é lida e exibida com o que ela de fato tem — qualidade sempre, e a
   leitura paga **só quando houve passe pago**, declarada como pulada quando não houve.
   Ausência de análise é estado honesto na tela, não erro.
5. Foto avulsa da fatia 2 percorre presign → confirm → exibição com o mesmo rigor de digest
   do upload de prancha, e recusa tipo fora da lista.
6. A classificação da fatia 3 nasce como rascunho, com lineage de prompt e modelo por
   proposta, e **nenhuma** delas altera cena, precisão, blocker ou exportação sem ato humano.
7. Nenhum caminho novo produz medida a partir de foto — coberto por teste negativo explícito,
   não por ausência de código.
8. Eval da fatia 3 com gate declarado antes da primeira rodada paga, no molde de
   [Evaluation Strategy](../../ai/EVALUATION_STRATEGY.md).
9. As telas correspondem à revisão aprovada do Design Approval Package.

## Constraints

- `tenant_id` sempre do JWT; mídia de outro tenant é `404`, não `403`.
- Fail-closed: análise ilegível, digest divergente ou mídia não confirmada não são exibidas
  como se estivessem boas.
- Custo declarado e limitado, no molde de `CROQUITO_AI_MAX_ESTIMATED_COST_USD`.
- A ancoragem exibida é a que o campo registrou; o escritório não reancora por inferência.
- Cor nunca é o único indicador — vale para qualidade de foto como já vale para precisão.

## Dependencies

- [F-032](../F-032-app-levantamento-campo/feature.md) e o
  [ADR-0043](../../adr/0043-app-de-campo-pwa-offline-first.md) — a foto, a âncora e a análise
  vêm de lá. Entregue, em `READY_FOR_HUMAN_REVIEW`.
- [F-012](../F-012-operacao-saas-autorizacao-ia/feature.md) e o
  [ADR-0036](../../adr/0036-autorizacao-de-ia-contratual-sem-allowlist-documental.md) — o
  entitlement de IA por tenant é o portão da fatia 3.
- [F-029](../F-029-auto-associacao-confianca/feature.md) — a fronteira com o score
  determinístico é declarada contra ela.

## Unknowns

Os três primeiros são decisão do ADR e **não** são resolvidos neste contrato.

1. **Como o levantamento alcança a jornada do escritório.** `jobs.upload_id` é
   `NOT NULL` e `UNIQUE` (`database.py:77`): não existe job sem PDF. As saídas visíveis são
   criar um job de origem "campo" — o que exige mexer nessa coluna —, vincular o levantamento
   a um job de prancha que já existe, ou uma terceira forma que não seja job. `survey_export.py`
   já nomeou o problema e o deixou para cá.
2. **Um levantamento vale para quantos jobs?** Uma praça levantada uma vez pode virar duas
   pranchas; e uma prancha pode cobrir dois levantamentos. A cardinalidade decide se o
   vínculo é coluna ou tabela.
3. **A classificação entra no scene graph ou fica fora?** `attachments.json` é o precedente
   de "fora, de propósito". Entrar como `Issue`/observação dá visibilidade no lugar onde o
   revisor decide; ficar fora protege a cena de ruído que não é desenho.
4. **Retenção.** O bucket tem expiração única por `artifact_retention_days`
   (`infra/main.tf:70`), então a foto do levantamento morre com o resto. A revisão pode
   acontecer depois disso, e uma evidência que some no meio do trabalho é pior do que uma
   que nunca esteve lá. Decisão de operação e custo, não de código.
5. **Qual modelo e qual prompt** para a fatia 3 — sai no plano dela, com o
   [protocolo de mudança de prompt](../../ai/PROMPT_CHANGE_PROTOCOL.md).

## Risks

- **A foto é convincente e não mede.** O risco central: uma imagem ao lado de uma cota
  sugere confirmação que ela não fornece. Mitigação é de tela e de contrato — a foto aparece
  onde se decide "o que é", nunca "quanto mede", e o critério 7 exige teste negativo.
- **Classificação plausível e errada.** Muro × alambrado é fácil de acertar em foto boa e
  fácil de errar em contraluz. Por isso é rascunho com lineage, e por isso a eval tem gate
  antes da primeira rodada paga.
- **Custo que ninguém pediu.** Levantamento com quarenta fotos vira quarenta chamadas se a
  fatia 3 disparar sozinha. O teto e o entitlement existem; o desenho precisa não os
  contornar.
- **Duas casas para foto de obra** depois da fatia 2 — a do levantamento e a avulsa. Se as
  duas não tiverem a mesma cara na revisão, o revisor terá de saber de qual veio para saber
  no que confiar.
- **Evidência expirada** (Unknown 4).

## Human Gates

1. **`ARCHITECTURE_DECISION_REQUIRED`** — ADR novo, precedendo o planejamento, decidindo os
   Unknowns 1 a 3: como o levantamento entra na jornada do escritório dado que não existe job
   sem PDF, qual a cardinalidade do vínculo, e se a classificação entra no scene graph.
2. **`DESIGN_APPROVAL_REQUIRED`** — Design Approval Package da superfície nova na revisão,
   precedendo o planejamento, conforme
   [design-approval](../../engineering-os/workflows/design-approval.md). A fatia 1 já cria
   superfície: a foto na tela é valor visual novo, e não reuso de um mecanismo aprovado.

Nenhum agente cumpre nenhum dos dois. A primeira rodada paga da fatia 3 é **ato humano de
autorização de gasto**, separado e posterior.

## References

- [ADR-0043 — app de campo PWA offline-first](../../adr/0043-app-de-campo-pwa-offline-first.md)
- [ADR-0036 — autorização de IA contratual](../../adr/0036-autorizacao-de-ia-contratual-sem-allowlist-documental.md)
- [Model Routing](../../ai/MODEL_ROUTING.md), [Prompt Contracts](../../ai/PROMPT_CONTRACTS.md),
  [Evaluation Strategy](../../ai/EVALUATION_STRATEGY.md)
- [Human in the loop](../../ai/HUMAN_IN_THE_LOOP.md)
- [Fluxo do sistema](../../architecture/FLUXO_DO_SISTEMA.md)
