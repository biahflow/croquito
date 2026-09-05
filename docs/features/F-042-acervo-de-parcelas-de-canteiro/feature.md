# F-042 — O canteiro sai de um acervo parametrizado, não da digitação

## Status

`DONE`

> **Aceita por ato humano em 2026-09-05** (Daniel Campos, pelo chat), com o **gate 4
> cumprido com achado** na mesma data. A bancada delegada pelo dono exerceu o ciclo inteiro
> contra dado real: a praça-bancada do Campo do Toca (catálogo SCO Out/2023 real, matriz
> transcrita da memória do documento) virou a "praça já feita"; a **autoria** nasceu na tela
> — acervo "CANTEIRO PADRÃO — DO CAMPO DO TOCA" v1.0.0, 6 parcelas, `SEMI PERIMETRO` e os
> dois `MESES` citados como parâmetros, o resto constante — e a **aplicação** numa praça
> nova, com parâmetros dela (prazo 3 meses, semiperímetro 98,50), atravessou prévia → apply
> → montagem: as 5 linhas de canteiro nasceram **sem digitação de quantidade**
> (7.387,50 / 3,00 / 3,00 / 2,80 / 468,00), com proveniência `acervo 1.0.0` na matriz.
>
> **O achado do gate**: serviço `STANDALONE` era **imprecificável por construção** — o
> builder do orçamento exigia fonte citada por confirmação de código, o canteiro não tem
> elemento para confirmar, e o apply não grava citação; nenhum teste montava orçamento com
> standalone, então o ROI central da feature nunca tinha virado linha. Reparado no laço da
> revisão ([PR #178](https://github.com/biahflow/croquito/pull/178)): **fonte única na cascata
> resolve sozinha; com mais de uma tabela a recusa continua** (a escolha é da orçamentista);
> parcela de elemento nunca usa o fallback — o portão dela fecha antes, por
> `ESTIMATE_ASSIGNMENT_MISSING`, provado por teste. Registro completo no
> [evidence.md](evidence.md).
>
> Dívida declarada: a autoria e o uso reais **pela orçamentista** seguem como o teste de
> verdade pendente — quais parcelas entram, com que parâmetros e sob que nome é decisão
> dela. Achado menor da bancada: [issue #177](https://github.com/biahflow/croquito/issues/177)
> (chave React duplicada na etapa Códigos).

> Nasce em 2026-08-28, de uma pergunta de ROI do dono do produto: *"o que a gente pode fazer
> no sistema para acelerar a entrega desse documento pelo orçamentista?"*, feita sobre a
> planilha real `ORÇAMENTO PRELIMINAR - PRAÇA CAMPO DO TOCA - REV SEAC` — a mesma praça cuja
> prancha está na rodada de orçamento local.
>
> A intuição inicial era que o gargalo fosse sugerir o código SCO do que está na legenda.
> A medição do documento real mostrou outra coisa, e é ela que justifica esta feature vir
> **antes** daquela: das 43 linhas preenchidas, **24 não têm origem nenhuma na prancha**.
> São canteiro, mão de obra, andaime, transporte e entulho — 56% do preenchimento, sem apoio
> algum hoje, e sem depender de IA nenhuma para resolver.

## Classification

`INTERFACE_CHANGE` — cria superfície nova na etapa de códigos do orçamento: escolher um
acervo, declarar os parâmetros de obra que ele cita, revisar as parcelas que vão nascer e
remover as que não se aplicam antes de aplicar.

## Priority

`HIGH` — é a maior fatia isolada do trabalho (24 de 43 linhas), é determinística, não faz
chamada paga e funciona já na primeira praça, porque o acervo é autorado e não aprendido.

## Problem

A quantidade de cada serviço de canteiro nasce de uma fórmula com parcelas nomeadas cujos
insumos **não estão na legenda da prancha**. Da memória de cálculo do documento real:

- `01.10` aluguel de banheiro químico = `1 × 2 meses`;
- `01.11` container = `1 × 2 meses`;
- `01.30` vigia = `23 dias × 12 h` + `8 dias × 24 h`;
- `01.15` placa de obra = `2,00 × 1,40`;
- `01.5` transporte de andaime = `SEMI PERÍMETRO 132,21 × ALTURA 3`.

Todas se repetem em toda praça, e todas saem de um punhado de parâmetros: prazo de obra,
área de intervenção, semi-perímetro, altura do alambrado. Hoje a orçamentista as digita uma
a uma, a cada praça.

O modelo do domínio **já sabe o que elas são**: `ContributionBasis.STANDALONE`
(`packages/valuation/src/croquito_valuation/models.py:250-252`) está definido como "não tem
origem geométrica: canteiro e administração (placa, container, vigia)". O que falta não é
modelagem — é o acervo. Uma varredura do repositório por `STANDALONE` fora de
`models.py`/`calc_matrix.py` acha apenas testes, o ADR-0053 e o tipo gerado: **não existe
seed, tabela, rota nem biblioteca**, e toda contribuição é autorada do zero por rodada
(`CalcContribution` não tem id, chave nem versão — `calc_matrix.py:56-124`).

O repositório já tratou esse mesmo problema uma vez, para o transporte:
`haulage.py` declara na docstring que a tabela "é propriedade do **contrato**, não da obra" e
que "hoje ela é redigitada a cada praça — 112 linhas", e virou seed versionado
`data/sco-haulage-v1.json`. Não há equivalente para as parcelas de canteiro.

## Desired Outcome

A orçamentista escolhe um acervo, declara meia dúzia de parâmetros da obra e as parcelas de
canteiro nascem materializadas na `CalcMatrix` da rodada, com proveniência — em vez de serem
digitadas de novo a cada praça.

## Scope

1. **Artefato "acervo de parcelas de canteiro"**: conjunto versionado de contribuições
   `STANDALONE` (código do catálogo + `CalcRecipe` + operandos), em que cada operando é
   **constante** ou **referência a um parâmetro de obra nomeado**. Identidade estável e
   versão, no molde do seed de `haulage.py`.
2. **Parâmetros de obra por rodada** (`prazo_meses`, `area_intervencao`, `semi_perimetro`,
   `altura_alambrado`, …), declarados pela orçamentista. O sistema **nunca os infere**:
   aplicar o acervo com parâmetro citado e não declarado é recusa que nomeia o parâmetro
   faltante, e nada é materializado.
3. **Aplicação materializa na `CalcMatrix` existente** — não é caminho paralelo de cálculo.
   As contribuições geradas passam pelas mesmas validações de `calc_matrix.py`
   (`CALC_CONTRIBUTION_STANDALONE_WITH_ITEM` continua valendo: parcela de canteiro não pode
   citar elemento da prancha) e carregam proveniência (`acervo_id`, versão).
4. **Tela**: escolher acervo, preencher parâmetros, **pré-visualizar** as parcelas que vão
   nascer com as quantidades já calculadas, e remover individualmente as que não se aplicam
   antes de aplicar.
5. **Autoria do acervo**: caminho para a orçamentista salvar as parcelas `STANDALONE` de uma
   rodada já feita como acervo novo, ou como versão nova de um acervo existente.

## Out of Scope

- **Inferir o acervo sozinho** de planilha antiga ou de rodadas passadas. O primeiro acervo é
  autorado por gente, a partir de uma praça já feita.
- **Inventar parâmetro.** A prancha imprime "ÁREA DE INTERVENÇÃO = 5.537,46 m²" e capturá-la
  na extração é tentador, mas não verifiquei que esse número alimente qualquer uma das 24
  linhas; enquanto não for verificado, o parâmetro é declarado por gente.
- **Parcelas com origem na prancha** (`FULL`, `DERIVED`, `PARTIAL`, `DEPENDENT`). O acervo é
  só de `STANDALONE`, que por definição não tem `source_item_id`.
- **A tabela de transporte** de `haulage.py`, que já tem seed próprio e outro dono (o
  contrato).

## Acceptance Criteria

1. Aplicar o acervo do Campo do Toca, com os parâmetros reais da obra, reproduz as **24
   linhas `STANDALONE`** da planilha do cliente, com as mesmas quantidades.
2. Parâmetro citado pelo acervo e não declarado na rodada → recusa que **nomeia** o
   parâmetro; nenhuma contribuição é materializada (falha fechada, não parcial).
3. Uma parcela removida na pré-visualização não nasce, e a remoção não altera as demais.
4. Aplicar o mesmo acervo duas vezes com os mesmos parâmetros é idempotente na matriz
   resultante.
5. Nenhuma chamada paga em nenhum ponto do caminho.
6. **Métrica**: linhas preenchidas sem decisão humana no Campo do Toca sobe de **0/43** para
   **~24/43**, registrada em `evidence.md`.

## Constraints

- A `CalcMatrix` continua sendo o único regime de cálculo; o acervo alimenta, não substitui.
- `CalcContribution.basis = STANDALONE` proíbe `source_item_id` por validação já existente
  (`calc_matrix.py:91-96`) — o acervo não pode contorná-la.
- Quantidade é `Decimal` onde a precisão escrita importa, e o subtotal é sempre **computado**,
  nunca declarado (`calc.py:57`).

## Dependencies

- [ADR-0053](../../adr/0053-cardinalidade-n-n-elemento-servico.md) — a matriz elemento ×
  serviço e as cinco bases de contribuição, `STANDALONE` inclusive.
- [ADR-0059](../../adr/0059-item-contratado-fora-da-tabela-sco.md) — **`Accepted` em
  2026-08-28**, alternativa A: sob demanda contratada a fonte de preço passa a ser o
  contrato (origem `contract`), e ele carrega o item fora da tabela SCO.
- [F-038](../F-038-pacote-de-servicos/feature.md) — quem trouxe a `CalcMatrix` para a
  jornada do orçamento.

## Unknowns

1. **Onde o acervo vive**: seed versionado no repositório (como `data/sco-haulage-v1.json`),
   artefato de plataforma (como o acervo de catálogos da F-037), ou dado do tenant. Os três
   têm donos e retenções diferentes. Um acervo de canteiro não contém dado de cliente — é
   receita —, o que aponta para plataforma; decidir na execução, com o motivo escrito.
2. **Se os parâmetros são por rodada ou por praça.** Prazo de obra é da obra; área de
   intervenção é da praça. Pode ser que o conjunto se parta em dois.
3. **Se o acervo é por lote do contrato.** Os três lotes têm listas de código diferentes
   (328/383/112), então um acervo do GRUPO 1 pode citar código que o GRUPO 2 não tem.

## Risks

- **Acervo silenciosamente desatualizado**: catálogo novo pode retirar um código que o acervo
  cita. A aplicação precisa recusar por extenso, nomeando o código ausente, em vez de pular
  a parcela.
- **Parcela materializada que ninguém revisou**: o ganho da feature é justamente não digitar,
  e o risco é a orçamentista aplicar sem olhar. A pré-visualização obrigatória com remoção
  individual é o controle; ela não pode virar um botão de "aplicar tudo" sem passagem pela
  lista.
- **A métrica virar meta**: 24/43 é medida de aceleração, não de acerto. Uma parcela aplicada
  e depois corrigida à mão **não** conta como preenchida sem decisão humana.

## Human Gates

1. **Design Approval Package** — `INTERFACE_CHANGE`: a superfície de escolher acervo,
   declarar parâmetros e pré-visualizar. Revisão 1 **aprovada em 2026-08-28** (Daniel Campos).
   A implementação da tela expôs um beco sem saída no próprio pacote — a recusa oferecia
   "remova na pré-visualização" e acontecia antes de a pré-visualização existir —, e a emenda
   aprovada no mesmo dia produziu a **revisão 2, aprovada na mesma data (2026-08-28)** —
   este item dizia "aguarda aprovação" por dessincronia com o
   [roadmap](../../product/ROADMAP.md), corrigida em 2026-09-05:
   [`mock/README.md`](mock/README.md).
2. ~~Aceite do [ADR-0059](../../adr/0059-item-contratado-fora-da-tabela-sco.md)~~ —
   **cumprido em 2026-08-28** (Daniel Campos), alternativa A.
3. ~~**Decisão do unknown 1** (onde o acervo vive)~~ — virou o
   [ADR-0060](../../adr/0060-onde-vive-o-acervo-de-parcelas-de-canteiro.md), **`Accepted` em
   2026-08-28** (Daniel Campos): plataforma e tenant como duas origens de um contrato de
   leitura só.
4. **Autoria do primeiro acervo** — **cumprido com achado em 2026-09-05** pela bancada
   delegada pelo dono, a partir da praça-bancada real do Campo do Toca (seção do gate 4 no
   [evidence.md](evidence.md)); o veredito é do dono, e a autoria real pela orçamentista
   fica como dívida declarada.

## References

- `packages/valuation/src/croquito_valuation/models.py:226-262` — `ContributionBasis`,
  `CalcRecipe` e `CalcOperand`; `STANDALONE` em `:250-252`.
- `packages/valuation/src/croquito_valuation/calc_matrix.py:56-124` — `CalcContribution` e
  suas validações; `:238-272` — `_materialize`.
- `packages/valuation/src/croquito_valuation/haulage.py:1-30` — o precedente de "redigitado a
  cada praça" virando seed versionado.
- `apps/web/src/orcamento/matrix.ts` — a autoria da matriz do lado da tela, espelho puro do
  domínio Python.
