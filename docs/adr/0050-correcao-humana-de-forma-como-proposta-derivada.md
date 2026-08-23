# ADR-0050: A correção humana de forma é proposta derivada, num conjunto de proveniência própria

Status: Proposed  
Data: 2026-08-23  
Responsável: Product / Engineering

## Contexto

A [F-018](../features/F-018-edicao-de-forma-da-proposta/feature.md) nasceu de um caso real: na
primeira revisão em nuvem do Guaxindiba V3, o muro com recuo **4,80 → 3,30** chegou
**fragmentado** da extração paga — duas `line` retas sob `geometry-extraction@2.0.1`, no lugar
de uma forma com o recuo. A revisora viu o erro na tela e não tinha o que fazer com ele.

`DecideProposalRequest` (`services/api/src/croquito_api/main.py:774`) aceita duas ações:
`accept` e `reject`. A proposta é imutável desde que nasce, e a única coisa que o humano
decide sobre ela é **se** ela entra — nunca **qual é a forma dela**. O único caminho de
correção era trocar o prompt e rerodar o provider pago: conserta aquele caso mudando o
comportamento de todos os outros, custa dinheiro e leva minutos.

A imutabilidade não é acidente. Proposta é **observação de máquina**, e observação não se
adultera: é dela que sai a única medida objetiva de quanto o modelo erra, e portanto o insumo
de qualquer melhoria de prompt. Então a saída não pode ser "deixar editar". Tem de ser outra
coisa, que preserve a observação.

O contrato da F-018 marcou duas perguntas como decisão deste ADR:

1. a forma corrigida é um `VisionProposal` com origem nova, ou um tipo próprio?
2. a união de fragmentos preserva os originais, ou os consome?

### O que já existe e decide metade do problema

`VisionProposalSet` (`services/worker/src/croquito_worker/vision.py:118`) **já é o lugar da
proveniência**: `detector_version` é um `Literal` de dois valores — `opencv-proposals-v1` e
`provider-geometry-extraction-v1` —, e o comentário ao lado diz o que ele significa: "o
conjunto declara quem o produziu (…) Cada proposta segue carregando o próprio `algorithm`;
nada aqui muda os invariantes (`unresolved`, export=false)".

Ou seja: o produto já sabe declarar de onde uma forma veio, e já sabe fazer isso **sem** que a
declaração afrouxe invariante nenhum.

## Decisão

1. **A forma corrigida é um `VisionProposal`, num `VisionProposalSet` de proveniência
   própria.** `detector_version` ganha um terceiro valor, `human-correction-v1`. Não se cria
   um tipo paralelo.

   A razão é o custo a jusante: associação, calibração e solver consomem `VisionProposal`, e
   um segundo tipo obrigaria cada um deles a tratar dois formatos — duplicando, em dois
   lugares, os invariantes `unresolved` e `export=false` que **nunca** podem divergir. A
   proveniência já tem casa; usá-la é mais barato e mais seguro do que abrir outra.

2. **`quality_score` passa a ser opcional, e na correção humana é ausente.** Hoje é
   `float = Field(ge=0, le=1)`, obrigatório. Ele mede confiança de detector; para uma forma
   que uma pessoa desenhou não existe número honesto a pôr ali — e preencher `1.0` seria
   afirmar certeza máxima justamente onde não houve medição nenhuma.

   Vira `float | None = None`, aditivo, no mesmo idioma que `arc_angles_observed` já usa nesse
   módulo: "ausência é exatamente o que ele declara — ninguém observou". Quem ordena por
   qualidade passa a tratar `None` explicitamente, o que é o comportamento correto: correção
   humana não se ordena contra confiança de máquina.

   Isso muda o snapshot de OpenAPI, porque `VisionProposalSet` viaja em `ReviewResponse`. É
   mudança **aditiva** — campo que era obrigatório passa a admitir ausência —, e ela é visível
   por construção no diff do snapshot.

3. **`derived_from` é obrigatório e não vazio na correção.** A correção declara de quais
   propostas ela nasceu. Sem isso ela não é correção: é desenho livre, e desenho livre é CAD,
   não revisão. É esta obrigação que impede a feature de virar um editor de geometria dentro
   do navegador.

4. **Os fragmentos originais são preservados, e "consumido" é derivado, não gravado.** Um
   fragmento citado no `derived_from` de alguma correção é, por definição, superado — e a tela
   pode recolhê-lo a partir disso. Nenhum estado novo é gravado no fragmento: a relação já
   contém a informação, e um campo redundante é um campo que pode divergir da relação que ele
   duplica.

   Preservar é o que mantém a comparação máquina × humano viva. Consumir limparia a tela e
   apagaria exatamente o dado que motivou a feature.

5. **A correção não pode optar por sair dos invariantes.** `precision` continua
   `Literal["unresolved"]` e `export` continua `Literal[False]`. Uma forma desenhada à mão
   chega no máximo a `approximate`, pelo mesmo caminho de qualquer outra — calibração —, e
   **nunca** a `exact`: dimensão exata nasce de cota confirmada, e essa regra não tem exceção
   para vértice arrastado com capricho.

6. **Corrigir forma exige decisão de revisor completa** — autor, papel, instante e
   justificativa —, como `accept` e `reject` já exigem. Corrigir a geometria que vai virar
   desenho é decisão de domínio, não ajuste de interface.

7. **Concorrência pelo mecanismo que já existe**: `base_review_version` e
   `base_scene_version`, como as demais mutações da revisão. Duas pessoas corrigindo a mesma
   forma recusam pela versão, não pelo último a salvar.

8. **A comparação máquina × humano fica consultável sem instrumentação nova.** Como o conjunto
   declara `detector_version` e a correção declara `derived_from`, o produto responde "quantas
   formas de `provider-geometry-extraction-v1` precisaram de correção humana" lendo o que já
   está gravado. É o retorno de longo prazo desta decisão, e ele só existe porque a decisão 4
   preserva os originais.

## Alternativas

- **Editar a proposta no lugar** — rejeitada, e é a alternativa óbvia. Apagaria a observação
  da máquina, que é a única medida objetiva do erro do modelo. Depois da primeira correção,
  ninguém mais saberia o que o provider tinha entregado.
- **Tipo próprio para a correção** (`ShapeCorrection` ou equivalente) — rejeitada pelo custo a
  jusante da decisão 1: três consumidores passariam a tratar dois formatos, e os invariantes
  `unresolved`/`export=false` viveriam em dois lugares.
- **`quality_score = 1.0` na correção humana** — rejeitada: afirma certeza máxima onde não
  houve medição. Sentinela que mente é pior que campo ausente.
- **Consumir os fragmentos na união** — rejeitada pela decisão 4.
- **Gravar `superseded_by` no fragmento** — rejeitada: duplica a relação que `derived_from` já
  expressa, e dois lugares que dizem a mesma coisa acabam discordando.
- **Permitir desenhar forma sem proposta de origem** — rejeitada pela decisão 3. É a fronteira
  entre corrigir e desenhar.
- **Deixar a correção promover precisão quando o revisor "tem certeza"** — rejeitada: certeza
  declarada não é cota medida, e o portão de exportação existe justamente para não aceitar a
  primeira no lugar da segunda.

## Consequências

### Positivas

- O caminho mais caro de correção — trocar prompt e rerodar provider pago — deixa de ser o
  único, e some do fluxo normal.
- A observação da máquina sobrevive à correção, e com ela a possibilidade de medir o erro do
  modelo por conjunto e por versão de extração.
- Nenhum consumidor a jusante muda: associação, calibração e solver continuam vendo
  `VisionProposal`.
- Os invariantes ficam num lugar só.

### Negativas

- **`quality_score` opcional é mudança de contrato publicado.** Aparece no diff do snapshot de
  OpenAPI, e todo consumidor que ordenava por ele precisa tratar ausência.
- **A lista de propostas cresce**: cada correção acrescenta uma forma, e os fragmentos
  superados continuam lá. A tela recolhe, mas o dado permanece — é o preço da decisão 4.
- **"Consumido" ser derivado custa uma travessia** da lista de correções para saber se um
  fragmento foi superado. É barato e é correto; um campo gravado seria mais rápido e mentiria
  eventualmente.
- **Corrigir é mais trabalhoso que aceitar**, porque exige justificativa. Deliberado.

## Riscos e mitigação

| Risco | Mitigação |
|---|---|
| Correção virar desenho livre dentro da revisão | Decisão 3: `derived_from` obrigatório e não vazio; sem proposta de origem não há correção |
| Forma corrigida parecer mais confiável que a bruta | Decisão 5: precisão não sobe, e a proveniência viaja no conjunto, visível na tela |
| `quality_score` ausente quebrar consumidor | Aditivo com default; o snapshot de OpenAPI expõe a mudança, e o gate de contrato (F-005) reprova divergência silenciosa |
| Lista poluída por fragmentos superados | Decisão 4: recolhimento é de tela, e o dado fica |
| Duas pessoas corrigindo a mesma forma | Decisão 7: `base_review_version`/`base_scene_version`, o mecanismo que a revisão já usa |
| Alguém "melhorar" a decisão 5 e deixar a correção virar `exact` | Os dois campos permanecem `Literal`, então a tentativa não compila antes de chegar a produção |

## Rastreabilidade

- Feature: [F-018](../features/F-018-edicao-de-forma-da-proposta/feature.md)
- Requirements: FR-008 (modelo de domínio), FR-009 (revisão humana)
- Relacionados: [ADR-0005](0005-canonical-scene-graph.md),
  [ADR-0006](0006-human-review-and-provenance.md),
  [ADR-0019](0019-proposal-refresh-creates-a-new-review-revision.md)
- Supersedes: none
- Superseded by: none
