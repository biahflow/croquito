# F-038 — O item de legenda é um pacote de serviços, não um código

## Status

`IN_PROGRESS`

> Nasce em 2026-08-25, da leitura do orçamento real que a prefeitura envia à empresa antes
> da obra (Praça Campo do Toca, SCO-PCRJ Out/2023). O dono do produto trouxe o arquivo
> perguntando se dava para entender a relação entre a legenda da prancha e os itens do SCO;
> a resposta refutou uma premissa que estava no código desde o M4.
>
> **Os dois gates humanos foram cumpridos.** O
> [ADR-0053](../../adr/0053-cardinalidade-n-n-elemento-servico.md) foi **aceito por ato
> humano em 2026-08-25**, e o **Design Approval Package** foi **aprovado por ato humano em
> 2026-08-26**, revisão 1 ([mock/README.md](mock/README.md)).
>
> **As doze tarefas estão entregues e mergeadas na `main`**, cada uma com os portões
> verdes, mais o desdobramento da decisão 6 (#96, parcela `PARTIAL` com nota e teto). O
> epic (#71) fechou em 2026-08-26 e nenhuma issue da feature segue aberta. A revisão 2 do
> Design Approval Package — autoria de matriz e declaração `PARTIAL` — foi **aprovada por
> ato humano em 2026-08-26** ([mock/rev2/README.md](mock/rev2/README.md)).
>
> **O que falta não é código, e por isso o status não é `DONE`**: a extração e o aceite
> reais do pacote do Campo do Toca pela orçamentista, com a planilha como oráculo do
> golden. `DONE` é decisão humana, não consequência de merge.
>
> Princípio desta feature, fixado pelo dono do produto: **a planilha é a fonte da verdade**.
> Em qualquer dúvida de modelagem, regra ou preço, o comportamento do arquivo manda —
> inclusive sobre o que os documentos deste repositório afirmam.

## Classification

`INTERFACE_CHANGE` — muda a etapa `codigos` da jornada do orçamento
(`apps/web/src/orcamento/OrcamentoApp.tsx`), onde hoje a escolha é de **um** código por item
e passa a ser a montagem de um pacote, com um ato novo de fechamento. Exige Design Approval
Package aprovado antes do planejamento, conforme
[design-approval](../../engineering-os/workflows/design-approval.md).

## Priority

`HIGH` — é a diferença entre o produto representar o trabalho da orçamentista e representar
uma simplificação que ela contorna fora do sistema. Enquanto durar, todo orçamento montado
aqui precisa ser reescrito à mão para virar o que a prefeitura recebe.

## Problem

### A premissa 1:1 está no tipo, no validador e no oráculo

`CodeAssignment.code` é `str | None`
([assignment.py](../../../packages/valuation/src/croquito_valuation/assignment.py));
`validate_unique_items` recusa dois vínculos para o mesmo item com
`ASSIGNMENT_DUPLICATE_ITEM`; `build_worksite_estimate` gera **uma** `EstimateLine` por item;
e `tests/valuation/golden/matcher-golden-v1.json` codifica cada caso como
`label + unit → expected.code`.

### O arquivo real refuta a premissa nas duas direções

**Um elemento dispara vários serviços.** `PISO EM CONCRETO`, 418,12 m² medidos uma única
vez, alimenta seis itens: preparo de solo, base de saibro, tela soldada, pavimento rígido,
limpeza e polimento — os dois últimos sobre 170 m² dos 418,12. A fórmula prova o vínculo: a
célula do pavimento rígido é literalmente `=F107`, referência à área digitada no bloco do
saibro.

**Um serviço recebe parcelas de vários elementos.** `BP04050350(/)` soma `CAMPO DE FUTEBOL`
+ `PISO EM CONCRETO` (418,12) + `PAVIMENTO INTERTRAVADO` (59,34) + `FORRAÇÃO EM GRAMA`
(1,28) = 478,74 m².

O caso mais caro do arquivo foi confirmado pela orçamentista: `PJ14150203(A)` entra como a
**estrutura tubular** — os postes e a armação que dão fixação — e `PJ14100500(/)` como a
**tela** que ela prende. Duas partes físicas do mesmo elemento, mesma área de fachada
(783,86 m²), somando R$ 399.651,01: **62% do orçamento da obra**.

### O que isso contradiz no próprio repositório

O [ROADMAP](../../product/ROADMAP.md) afirma que "a escolha certa é o código de *execução*,
não o de mero fornecimento". No arquivo real os dois entram, e não por engano. A correção
do texto é tarefa própria (#84).

## Desired Outcome

A orçamentista monta, para cada elemento da prancha, o pacote de serviços que ele dispara —
com a parcela de quantidade de cada par — e o sistema produz o orçamento que a prefeitura
recebe, inclusive o capítulo de transporte, que passa a ser derivado em vez de redigitado.

## Scope

1. **A memória é a matriz.** `CalcBlock` ganha `source_item_id` ao lado do `label`, mais
   `basis` e `derived_from_code`. **Entregue (#75).**
2. **A identidade da confirmação é o par `(item_id, code)`**, com fechamento explícito de
   pacote. Sem ele, item com um de seis códigos pareceria pronto. **Entregue (#77)**, ponta
   a ponta: domínio, rotas `/v1`, CLI, servidor local e as duas telas.
3. **A linha do orçamento agrupa por código**, com uma `CalcSheet` por linha e um bloco por
   elemento contribuinte. **Entregue (#78)**: os builders passaram a iterar serviços, não
   itens.
4. **Dependência entre serviços** resolvida no build e materializada como operando literal,
   com recusa de ciclo. Dado e cálculo **entregues (#83)**; a integração, **entregue
   (#76)** — `CalcMatrix` com ordem topológica e recusa por extenso
   (`CALC_MATRIX_DEPENDENCY_CYCLE`, `CALC_MATRIX_SELF_DEPENDENCY`).
5. **A base de preço é a da planilha** (Out/2023), nunca a de jul/2026. **Entregue (#73).**
6. **O digest de aprovação sobrevive à mudança**, governado pela versão declarada.
   **Entregue (#74).**
7. **A tela monta o pacote e mostra a memória** — que não existia na jornada do orçamento,
   só na de medição. **Entregue (#81)**, com a declaração `PARTIAL` no desdobramento
   (#96).

## Out of Scope

- Inferir o pacote por IA. A shortlist continua por item; o que muda é quantos códigos o
  humano escolhe dela. Um suggester de pilha construtiva é marco próprio, com seed curável
  e gate próprio.
- Refino pago de pacote: `apply_refinement` é permutação exata de uma shortlist, e
  `REFINEMENT_CODES_MISMATCH` existe para proibir o modelo acrescentar códigos.
- Aditivo parcial (elemento com pacote incompleto por falta de um código no contrato).
- Reconciliação retroativa de rodadas na versão anterior.
- Mudar `PriceOrigin` ou a fronteira licitada × pré-licitação do
  [ADR-0027](../../adr/0027-price-source-provenance-and-bid-boundary.md).

## Acceptance Criteria

O oráculo é o arquivo, não a intuição:

- `PISO EM CONCRETO` gera **seis** linhas de orçamento, não uma.
- `BP04050350(/)` fecha em **478,74 m²** somando quatro parcelas rotuladas.
- `BP09100050(B)` fecha em **418,12 m²**.
- `TC04100050(/)` produz **365,86 t.dam** para o pavimento rígido sem digitação. *(gate já
  verde em #83.)*
- Rodada gravada na versão anterior relê com resultado byte-idêntico, e seu digest de
  aprovação não se move. *(gate já verde em #74.)*
- Item com pacote aberto aparece como **pendente**, nunca como pronto.

## Constraints

- Blobs JSON append-only: compatibilidade sai por `Literal` alargado, não por migração de
  dado.
- O digest de conteúdo sustenta a aprovação nominal; sob o
  [ADR-0048](../../adr/0048-consolidado-contratual-do-orcamento-assinado.md) o orçamento
  assinado é consolidado contratual, e mover esse digest invalida um contrato.
- O vocabulário de fórmulas da memória é **aberto**: 45 formas distintas e 43 termos de
  operando no arquivo real, 21 deles de ocorrência única. Enum fechado de grandezas não
  sobrevive ao dado.
- Dado de cliente não é versionado: artefatos derivados da planilha ficam em `output/`.

## Dependencies

- [ADR-0053](../../adr/0053-cardinalidade-n-n-elemento-servico.md) — aceito.
- [ADR-0027](../../adr/0027-price-source-provenance-and-bid-boundary.md) e
  [ADR-0045](../../adr/0045-terceiro-estado-demanda-sob-contrato.md) — seguem válidos; a
  primeira rodada sob a cardinalidade nova é no regime de demanda sob contrato.
- [ADR-0048](../../adr/0048-consolidado-contratual-do-orcamento-assinado.md) — é o que
  torna o digest um contrato.

## Unknowns

1. **A distância de 3,5 dam que multiplica o transporte é do contrato ou do canteiro de cada
   praça?** Modelada como fator sobrescrutível por obra, para não travar a entrega enquanto
   a orçamentista não responde.
2. **Seis materiais da tabela de derivação não têm código** no contrato desta obra —
   resíduo de um template mais amplo. Declarados em `unmapped_labels`; curá-los precisa da
   orçamentista.
3. **O BDI do arquivo tem um furo de cálculo confirmado**: o total soma custo sem BDI e o
   rodapé divide por 1,18, sendo o BDI real 18,178%. Não replicar.

## Risks

| Risco | Mitigação |
|---|---|
| Digest quebrado invalida orçamento assinado | Poda declarada por versão, implementada e provada antes de qualquer campo novo (#74) |
| Fechamento esquecido produz boletim parcial em silêncio | `CALC_PACKAGE_NOT_CLOSED` fail-closed |
| Parcela parcial tratada como derivável inventa número | `PARTIAL` é declarada com nota obrigatória (`CALC_PARTIAL_NOTE_REQUIRED`, na leitura da célula) e conferida contra o teto do elemento no build (`CALC_PARTIAL_EXCEEDS_ITEM`); nunca recomputada (#96) |
| Regime anterior vazando muda resultado de rodada existente | Regime declarado pelo `schema_version` do artefato; goldens byte-idênticos são o gate |
| Matcher invisivelmente pior no mundo do pacote | Medido e publicado no golden como gap conhecido |

## Human Gates

| Gate | Estado |
|---|---|
| ADR-0053 aceito | **Cumprido em 2026-08-25** (Daniel Campos) |
| Design Approval Package aprovado | **Cumprido em 2026-08-26** (Daniel Campos), revisão 1 |

## References

- [ADR-0053](../../adr/0053-cardinalidade-n-n-elemento-servico.md)
- [Design Approval Package](mock/README.md)
- [Valuation Context](../../architecture/VALUATION_CONTEXT.md)
- [Roadmap](../../product/ROADMAP.md) · [Status](../../STATUS.md)
