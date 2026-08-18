# ADR-0016: Medição de obra é um contexto delimitado próprio

Status: Accepted
Data: 2026-08-12  
Responsável: Engineering

## Contexto

O produto existente vai de croqui a DXF: a geometria é a verdade, o `Canonical Scene
Graph` é a fonte, e o erro que importa é de milímetro. A medição de obra pública é outro
problema do mesmo cliente: o orçamentista recebe planilha e catálogo de preços, levanta
quantitativos, associa cada item a um código do catálogo público (SCO), monta memória de
cálculo e emite o boletim de medição (BM) da obra. A entrada é planilha, a saída é
planilha, e o erro que importa é de centavo.

Misturar os dois contextos custaria caro em três frentes:

- **Vocabulário.** `Measurement` já é cota do scene graph, `Budget` já é teto de gasto de
  IA em `providers.py` e `Job` já é o job do pipeline de cena. Reusar essas palavras para
  medição de obra tornaria ambíguo o código mais sensível do repositório.
- **Invariantes.** No scene graph, dimensão exata nunca nasce de pixel. Na medição, o
  invariante equivalente é aritmético: dinheiro trunca em duas casas e nunca arredonda,
  e nenhum total informado vale sem recomputo. São regras diferentes, com portões
  diferentes.
- **Ritmo.** O contexto de cena está no quarto marco, com contratos gerados para
  TypeScript e schema publicado. Amarrar medição ao mesmo `SceneRevision` obrigaria
  regenerar contratos de front-end a cada mudança de planilha.

Também é preciso decidir o que é fonte de verdade: a planilha entregue ao cliente, ou o
dado por trás dela. Planilha é frágil (fórmula quebrada, célula sobrescrita, cópia
divergente) e é o formato que o cliente exige.

## Decisão

Medição de obra é um contexto delimitado próprio, em `packages/valuation`
(domínio puro) e `services/worker/src/croquito_worker/valuation/` (comandos), com
vocabulário próprio e sem dependência do scene graph. O pacote pode depender de
`croquito_core` para ids e utilidades, nunca do worker.

- **O JSON canônico é a fonte de verdade; a planilha é render auditado.** Toda pasta
  gerada é reaberta, tem suas fórmulas recomputadas em `Decimal` por um avaliador
  próprio e é comparada centavo a centavo com o modelo. Divergência não publica.
- **Dinheiro trunca.** Valor monetário usa `TRUNC(x,2)` em `Decimal`; quantidade usa
  `ROUND(x,2)`. `float` é recusado na fronteira dos modelos. Quando o produto em ponto
  flutuante divergiria do cálculo exato, a célula recebe o valor literal em vez da
  fórmula e é declarada em `pinned_cells`.
- **A gramática de fórmulas emitidas é fechada** (`TRUNC`, `ROUND(PRODUCT(...))`,
  `ROUND(PRODUCT(...))-<ref>`, `SUM`) e é a mesma que a auditoria aceita. Fórmula fora
  dela é `FORMULA_UNSUPPORTED`.
- **O layout da planilha é dado** (`WorkbookTemplate`), não constante de código. O
  template real de cada cliente vive fora do Git.
- **IA propõe, humano confirma, export falha fechado.** Vale aqui a mesma regra do
  [ADR-0006](0006-human-review-and-provenance.md): sugestão de código SCO por modelo é
  observação; só decisão humana registrada vira associação, e nenhuma medição vai ao
  cliente sem aprovação nominal do orçamentista responsável (marco seguinte).
- **Vocabulário proibido:** `Measurement*`, `*Budget*` e `Job` não são usados neste
  contexto.

## Alternativas

- **Estender o scene graph com quantitativos.** Rejeitada: acoplaria planilha a
  geometria, forçaria regeneração dos contratos TypeScript a cada mudança de layout e
  contaminaria o vocabulário do módulo mais crítico do repositório.
- **Tratar a planilha como fonte de verdade e só editá-la.** Rejeitada: célula
  sobrescrita ou fórmula quebrada viraria erro silencioso de centavo, e não haveria como
  auditar o que o cliente recebeu contra o que o sistema calculou.
- **Usar `float` e arredondar no fim.** Rejeitada: a planilha do cliente trunca, e
  `1,15 × 10,30` é 11,84 truncado contra 11,85 arredondado. A diferença é dívida com o
  erário multiplicada por milhares de linhas.
- **Escrever a pasta com `VLOOKUP` para o catálogo.** Rejeitada: a planilha circula por
  e-mail sem o catálogo; a pasta precisa ser autocontida. O preço impresso continua
  sendo conferido contra o catálogo importado na escrita e na auditoria.
- **Aceitar qualquer fórmula na auditoria.** Rejeitada: implementar um interpretador de
  planilha é superfície de erro sem fim. Gramática fechada é auditável e recusa o que
  não entende.

## Consequências

### Positivas

- O orçamentista recebe uma pasta que ele reconhece, com fórmulas conferíveis célula a
  célula, e o sistema sabe provar que ela bate com o dado.
- Erro de centavo é impossível de passar silenciosamente: o round-trip compara tudo.
- O contexto evolui sem tocar contratos de cena, schema JSON ou front-end.
- Layout de cliente novo é configuração, não código.

### Negativas

- Duas noções de "revisão humana" convivem no repositório (cota e código SCO), com
  implementações separadas; parte da lógica de aprovação será parecida sem ser
  compartilhada.
- A gramática fechada limita o que a planilha pode conter: qualquer fórmula nova exige
  estender escritor e avaliador no mesmo passo.
- Uma dependência nova (`openpyxl`) entra no runtime, com a superfície de risco de
  leitura de arquivo externo.
- A pasta autocontida duplica descrição e preço em cada linha; catálogo atualizado não
  se propaga a medições já emitidas — o que é correto para medição, mas exige
  reimportação explícita.

## Riscos e mitigação

| Risco | Mitigação |
|---|---|
| Arredondamento silencioso de dinheiro | `money_trunc` em toda a cadeia e teste do par 1,15 × 10,30 |
| Fórmula viva divergindo do valor exato | `trunc_divergence` conservador, célula fixada e declarada na auditoria |
| Planilha entregue divergente do canônico | Round-trip obrigatório; divergência falha o comando sem publicar |
| Catálogo lido errado em silêncio | Linha não classificável falha com `ROW_UNPARSEABLE` (aba e linha) |
| Layout de cliente virando código | `WorkbookTemplate` como dado; template real fora do Git |
| Dado real de cliente no repositório | Fixtures 100% sintéticas; saída só em `output/`, ignorado pelo Git |
| Vocabulário colidindo com o scene graph | Lista de termos proibidos registrada aqui e no contexto |

## Rastreabilidade

- Requirements: VAL-01, VAL-02, VAL-03, VAL-04, VAL-05
- Supersedes: none
- Superseded by: none
