# ADR-0053: A relação entre elemento da prancha e serviço do catálogo é N:N, com parcela por par

Status: Accepted  
Data: 2026-08-25 (aceito por ato humano na mesma data)  
Responsável: Product / Engineering

## Contexto

O sistema assume, desde o M4, que **um item de legenda vira um código de catálogo**. A
premissa está no tipo (`CodeAssignment.code: str | None`,
[assignment.py:968](../../packages/valuation/src/croquito_valuation/assignment.py)), no
validador que proíbe dois vínculos para o mesmo item (`validate_unique_items`,
`ASSIGNMENT_DUPLICATE_ITEM`), no builder que gera **uma** `EstimateLine` por item
(`build_worksite_estimate`) e no oráculo (`tests/valuation/golden/matcher-golden-v1.json`,
onde cada caso é `label + unit → expected.code`).

O orçamento real da Praça Campo do Toca — o padrão que a prefeitura envia à empresa antes
da obra, sobre a tabela SCO-PCRJ de Outubro/2023 — refuta a premissa em duas direções, e a
refutação é verificável na própria fórmula da planilha.

**Um elemento dispara vários serviços.** `PISO EM CONCRETO`, 418,12 m² medidos uma única
vez, alimenta seis itens: preparo de solo `MT14150050(A)`, base de saibro `BP04050350(/)`,
tela soldada `ET39050109(/)`, pavimento rígido `BP09100050(B)`, limpeza `SC34150200(/)` e
polimento `SC29100100(A)` — os dois últimos sobre 170 m² dos 418,12. A célula do
`BP09100050(B)` é literalmente `=F107`: uma referência à área digitada no bloco do saibro.

**Um serviço recebe parcelas de vários elementos.** `BP04050350(/)` soma `CAMPO DE FUTEBOL`
+ `PISO EM CONCRETO` (418,12) + `PAVIMENTO INTERTRAVADO` (59,34) + `FORRAÇÃO EM GRAMA`
(1,28) = 478,74 m².

O caso mais caro do arquivo foi confirmado pela orçamentista em 2026-08-25 e é o que fecha
a questão: `PJ14150203(A)` ("Alambrado para campo de esporte") entra como a **estrutura
tubular** — os postes e a armação que dão fixação — e `PJ14100500(/)` entra como a **tela**
que essa estrutura prende. Duas partes físicas do mesmo elemento, ambas medidas pela mesma
área de fachada (783,86 m²), somando R$ 399.651,01 — **62% do orçamento da obra**.

Isso contradiz uma premissa registrada: o [ROADMAP](../product/ROADMAP.md) afirma que "a
escolha certa é o código de *execução*, não o de mero fornecimento". No arquivo real os dois
entram, e não por engano — são coisas diferentes.

O conceito de pacote de serviços **não existe em nenhum documento do repositório**: `grep`
por "pacote de serviço", "múltiplos códigos" e "vários códigos" em `docs/` não retorna nada.

### O que já está pronto para receber a mudança

`CalcSheet` **já é indexada pelo `item_number` da linha do boletim**, não pelo item de
takeoff: os validadores conferem 1:1 entre memória e **linha**
([estimate.py:374](../../packages/valuation/src/croquito_valuation/estimate.py),
[models.py:270](../../packages/valuation/src/croquito_valuation/models.py)). Somado a
`CalcBlock.label` (o rótulo da parcela) e a `CalcRecipe` — que já tem `length_times_width`,
`perimeter_times_height`, `qty_times_months` e `days_times_hours`, as mesmas grandezas do
arquivo real —, **a matriz elemento × serviço já existe na forma; falta o eixo das parcelas
ter nome**. A aritmética de `expected_subtotal` e `validate_total_quantity` não muda.

## Decisão

1. **A memória é a matriz.** `CalcBlock` ganha `source_item_id` **ao lado** do `label`,
   nunca no lugar dele: `label` é o texto que o escritor imprime na planilha e que o auditor
   de round-trip relê; trocá-lo por um identificador apagaria a redação humana.
   `source_item_id` é o elo que a máquina confere.

2. **A identidade da confirmação passa a ser o par `(item_id, code)`**, com **fechamento
   explícito de pacote** (`ItemPackageClosure`). Sem o fechamento, um item com um de seis
   códigos confirmados pareceria pronto e produziria boletim parcial em silêncio — a classe
   de erro que este repositório recusa por princípio. O regime é declarado pelo
   `schema_version` do próprio artefato: `1.0.0` mantém o comportamento 1:1 de hoje,
   byte-idêntico; `2.0.0` exige o par e o fechamento. Propriedade verificada:
   `_assignment_decision_id` já digere `code`, então **nenhum `vd_` histórico se move**.

3. **Cinco bases de contribuição, em enum fechado** (`ContributionBasis`): `FULL` (espelho),
   `DERIVED` (geometria), `PARTIAL`, `DEPENDENT` (vem de outro serviço) e `STANDALONE`
   (canteiro, sem origem geométrica). `PARTIAL` é o ponto de honestidade do desenho: os
   170 m² de limpeza **não são deriváveis** dos 418,12 por aritmética nenhuma — são
   declarados, com nota obrigatória e teto `≤ quantidade do item`, e nunca recomputados.
   `basis` nasce `None` ("não declarado") em artefato antigo, jamais com um default que
   afirme algo que ninguém declarou.

4. **Dependência entre serviços é resolvida no build e materializada como operando
   literal.** O transporte é `quantidade(outro código) × massa específica × distância`; o
   `CalcBlock` que chega à memória é inteiramente literal, preservando o invariante de que a
   pasta é autocontida — sem `VLOOKUP` — e a gramática fechada do escritor, que não tem
   forma para referência cruzada entre abas. Ciclo recusa **na leitura do artefato**, e a
   ordem topológica define a ordem de numeração das linhas.

5. **O digest de conteúdo é computado conforme a versão que o artefato declara.** É a
   decisão mais importante deste ADR, e a razão de ela existir está abaixo.

6. **O retrieval não muda nesta decisão.** `CodeSuggestionSet` exige uma sugestão por item,
   não um candidato por item: a shortlist continua sendo "os melhores códigos para este
   rótulo", e o que muda é quantos o humano escolhe dela. O suggester de pacote — que
   proporia a pilha construtiva inteira — é marco próprio, com seed curável e gate próprio.

### O risco que a decisão 5 endereça

`Estimate.content_digest()` e `Valuation.content_digest()` fazem
`json.dumps(model_dump(mode="json", exclude={"approval"}))`. `calc_sheets` entra no payload.
Um campo opcional novo em `CalcBlock` insere `"source_item_id": null` e **muda o digest de
artefatos já assinados**, que passariam a devolver `APPROVAL_CONTENT_MISMATCH`.

Isso não é um teste vermelho: pelo [ADR-0048](0048-consolidado-contratual-do-orcamento-assinado.md),
o orçamento assinado **é** o consolidado contratual da medição sob demanda contratada.
Quebrar o digest invalida um contrato.

O mecanismo já está implementado e provado (`versioned_content_digest`, `models.py`): a poda
é declarada por versão, com teste que simula o campo futuro e confirma que sem a poda as
âncoras reprovam e com ela passam.

## Alternativas

- **`codes: list[str]` no `CodeAssignment`** — rejeitada: empilha uma lista sem representar
  a **parcela de quantidade por par**, que é justamente o dado que a planilha carrega. Os
  170 m² de limpeza dentro dos 418,12 não teriam onde morar.
- **Manter 1:1 e resolver a fusão no escritor da planilha** — rejeitada: esconde a relação
  no render, onde não há validação nem contrato, e o produto continuaria incapaz de sugerir
  ou conferir um pacote.
- **Receita genérica `PRODUCT_OF_OPERANDS`** — rejeitada: `expected_subtotal` já é produto
  menos deduções para qualquer receita, e o enum é documental; uma receita genérica tiraria
  do auditor a capacidade de dizer "este bloco afirma ser perímetro × altura e não é".
- **Default `FULL` para `basis` em artefato antigo** — rejeitada: afirmaria algo que ninguém
  declarou. Um bloco `PERIMETER_TIMES_HEIGHT` do M4 é `DERIVED`, não `FULL`.
- **`exclude_none=True` no digest** — rejeitada: resolveria o campo novo e, de quebra,
  derrubaria `CalcOperand.unit=None`, mudando o digest de tudo que se queria preservar.
- **Migrar as rodadas persistidas para o regime novo** — rejeitada: os blobs
  (`code_assignments_json`, `estimate_json`) são append-only e o `Literal` alargado relê
  tudo. Rodada antiga é um pacote de um serviço só, que é exatamente o que ela é.

## Consequências

### Positivas

- O orçamento passa a representar o que a orçamentista realmente faz, em vez de uma
  simplificação que ela contorna fora do sistema.
- O capítulo de transporte, carga e bota-fora — hoje 112 linhas redigitadas a cada praça —
  torna-se derivável (decisão 4).
- O fechamento de pacote (decisão 2) fecha um buraco que a cardinalidade 1:1 escondia: não
  havia como distinguir "item resolvido" de "item pela metade".

### Negativas

- `CodeAssignmentSet`, `Valuation` e `Estimate` sobem de versão maior, e o contrato `/v1`
  muda em duas rotas.
- A regra de unidade precisa afrouxar no regime de pacote: um elemento em m² alimenta
  legitimamente serviços em m³, kg e m, e a recusa de hoje dispararia sempre. Ela passa a
  valer só quando o item tem exatamente um código confirmado.
- O matcher fica mensuravelmente pior no mundo do pacote antes de ficar melhor: um top-15
  otimizado para "qual código *é* este elemento" não traz códigos de famílias diferentes.
  O gap é publicado como medido, não escondido.

## Riscos e mitigação

| Risco | Mitigação |
|---|---|
| Digest quebrado invalida orçamento assinado que é consolidado contratual (ADR-0048) | Poda declarada por versão, implementada e provada antes de qualquer campo novo |
| Fechamento esquecido produz boletim parcial em silêncio | `CALC_PACKAGE_NOT_CLOSED` fail-closed; nunca inferir "acabou" da presença de um código |
| Parcela parcial tratada como derivável inventa número | `PARTIAL` é declarada, com nota obrigatória e teto; nunca recomputada |
| Regime legado vazando muda resultado de rodada existente | Regime declarado pelo `schema_version` do artefato; goldens M1/M4 byte-idênticos são o gate |
| Fusão retroativa de dois itens legados no mesmo código | Fusão por código só existe no regime `2.0.0` |
| Nota de unidade vira ruído e o orçamentista para de ler | Recusa restrita ao regime de código único |

## Rastreabilidade

- Requirements: F-038
- Supersedes: none
- Superseded by: none

## Emendas

- **[ADR-0027](0027-price-source-provenance-and-bid-boundary.md)** — segue `Accepted` e
  correto. A fronteira licitada × pré-licitação não é tocada:
  `BULLETIN_PRICE_ORIGIN_FORBIDDEN` e o dossiê de aditivo seguem intactos. Este ADR
  acrescenta um eixo — quantos serviços um elemento gera —, não muda de onde vem o preço.
- **[ADR-0045](0045-terceiro-estado-demanda-sob-contrato.md)** — segue `Accepted`. O
  orçamento do Campo do Toca é exatamente o terceiro estado que ele descreve, e é sob esse
  regime que a cardinalidade nova será exercida primeiro.
- **[ADR-0048](0048-consolidado-contratual-do-orcamento-assinado.md)** — não muda, mas é a
  razão de a decisão 5 existir: é ele que faz do digest do orçamento assinado um contrato.
