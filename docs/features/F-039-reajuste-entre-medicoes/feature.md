# F-039 — Reajuste de preços entre medições

## Status

`READY_FOR_REVIEW`

> Registrada em 2026-08-27, por seleção humana, a partir da
> [issue #99](https://github.com/biahflow/croquito/issues/99). Três decisões de domínio foram
> tomadas por ato humano na abertura, e estão em **Scope** — elas são o que separa esta
> feature de uma especulação.
>
> **Os dois gates humanos foram cumpridos em 2026-08-27.** O
> [ADR-0055](../../adr/0055-reajuste-como-ato-declarado-sobre-o-consolidado.md) foi **aceito** e
> o [Design Approval Package](mock/README.md) revisão 1 foi **aprovado**, ambos por ato humano
> de Daniel Campos na mesma data.
>
> **Implementada em 2026-08-27**, com portões verdes e evidência renderizada da tela real em
> [evidence.md](evidence.md). Dois desvios ficam declarados lá: a emenda do ADR descoberta na
> execução e o fator que não virou coluna da tabela.

## Classification

`INTERFACE_CHANGE` — declarar o reajuste é ato humano novo na abertura da rodada de medição,
e o preço reajustado precisa aparecer na memória de cálculo e no boletim com o fator visível.

## Priority

`HIGH` — obra longa reajusta, e hoje o produto não sabe. O caminho que sobra é reajustar por
fora e digitar o resultado, que é exatamente o que a cadeia existe para não fazer: a partir do
primeiro reajuste, o sistema deixa de ser a fonte do número.

## Problem

### O que existe hoje

Zero. `grep -r reajuste packages services` não devolve nada. Não é implementação parcial a
completar: é ausência inteira.

O preço da medição vem do catálogo instalado na rodada, e sob `contracted_demand` esse
catálogo **é a tabela contratual** ([ADR-0048](../../adr/0048-consolidado-contratual-do-orcamento-assinado.md),
decisão do dono do produto). O consolidado é gravado na abertura e é **imutável na rodada**
(decisão 7 do mesmo ADR). Da segunda medição em diante, ele nasce do orçamento assinado somado
aos períodos já lançados (decisão 8).

Nada disso conhece a passagem do tempo.

### O que quebra quando o contrato reajusta

`Valuation.export_errors` compara o preço do boletim com o do consolidado
(`LINE_PRICE_NOT_IN_CONTRACT`). No dia em que o contrato reajusta, existem só três saídas, e
todas são ruins:

- **medir pelo preço antigo** — o boletim sai por menos do que o contrato paga;
- **medir pelo preço novo com o consolidado velho** — o portão recusa a exportação, e a
  recusa está certa;
- **reajustar por fora e digitar** — o número passa a vir de uma planilha que ninguém audita.

### O que NÃO quebra, e é o que torna a feature viável

`PeriodProgress` guarda **quantidade e valor por período** (`contract.py:77`). O histórico já é
à prova de mudança de preço: `accumulated_amount` é a soma dos períodos, cada um com o dinheiro
que valeu quando foi medido. Nenhum reajuste precisa reescrever passado — e nenhum pode.

## Desired Outcome

Quem abre a rodada de medição declara que o contrato foi reajustado — o **fator**, o **índice**
e o **período de referência** — e a medição sai pelo preço vigente, com o reajuste **visível na
memória**: preço contratado, fator, preço reajustado. As medições já aprovadas não mudam nem um
centavo.

## Scope

### As três decisões de domínio tomadas na abertura

Tomadas por ato humano em 2026-08-27, e registradas aqui porque governam o desenho inteiro:

1. **Duas formas, declaradas por rodada.** Reajuste pode ser um **fator de índice** sobre o
   preço contratado (o mecanismo legal típico da obra licitada) **ou** a instalação de uma
   **nova versão da tabela contratual**, com data-base própria. Contratos reais fazem as
   duas coisas, e o sistema não escolhe por eles.
2. **O fator é digitado agora, com o campo preparado para a tabela depois.** Quem abre a
   rodada informa fator, nome do índice e período de referência; o sistema não busca índice
   em lugar nenhum e **exige a declaração**. O modelo é desenhado para que um importador de
   tabela de índices caiba depois sem quebrar contrato publicado.
3. **Um fator para o contrato inteiro, por enquanto.** Fórmula paramétrica — índices distintos
   para mão de obra e insumos — é extensão declarada, não contradição: fica nomeada no ADR
   como o caminho de crescimento.

### O reajuste é ato declarado, e vive no consolidado

Não é campo de configuração nem cálculo implícito. É uma declaração humana, com autor,
instante, índice, período e fator, gravada com o consolidado da rodada — no mesmo lugar e com a
mesma imutabilidade que ele já tem.

### O passado é intocável

Período já lançado guarda o valor que valeu. O reajuste vale para o período **desta** rodada em
diante; medição aprovada não é recalculada, e o `content_digest` de artefato assinado não se
move por causa dela.

### A memória mostra a conta

Preço contratado, fator declarado com o índice e o período, preço reajustado. Reajuste que a
prefeitura não consegue auditar na memória é reajuste devolvido — e a memória de cálculo é
justamente onde este produto já prova cada número.

## Out of Scope

- **Buscar índice em fonte externa.** Nenhuma chamada de rede, nenhum scraping de IBGE/FGV.
  A tabela de índices importada é a extensão prevista, e é outra feature.
- **Fórmula paramétrica por item.** Ver decisão 3.
- **Reequilíbrio econômico-financeiro.** É outro instituto, com outro fato gerador e outra
  prova; tratá-lo como reajuste seria erro de domínio.
- **Reajustar orçamento-base.** Pré-licitação já resolve preço por versão de tabela com
  data-base própria, e não tem contrato para reajustar.
- **Recalcular medição já aprovada.** Nunca, por decisão — ver `Scope`.

## Acceptance Criteria

1. `make check` e `make test` verdes; goldens intocados.
2. Rodada **sem** reajuste declarado se comporta exatamente como hoje — teste que prova
   ausência de mudança de comportamento e de digest.
3. Reajuste por fator produz preço vigente = `preço contratado × fator`, com o dinheiro
   truncado pela mesma regra do resto da cadeia (nunca arredondado).
4. Reajuste por nova versão da tabela reprecifica as linhas do consolidado a partir dela, e
   recusa fechado quando um código contratado não existe na versão nova.
5. `LINE_PRICE_NOT_IN_CONTRACT` passa a comparar o boletim com o **preço vigente**, e continua
   disparando quando o boletim diverge dele.
6. Período já lançado mantém quantidade **e** valor; `accumulated_amount` continua sendo a soma
   dos períodos, com preços diferentes convivendo na mesma linha — teste com duas medições em
   bases distintas.
7. A declaração do reajuste carrega autor, instante, índice, período de referência e fator, e
   é **imutável** na rodada, como o consolidado.
8. A memória de cálculo mostra preço contratado, fator e preço reajustado; teste lê os três.
9. Fator ausente, ≤ 0, ou declarado sem índice/período recusa na fronteira, com código estável.
10. A tela corresponde à revisão aprovada do Design Approval Package.

## Constraints

- `tenant_id` do JWT; `Idempotency-Key` e `base_version` como toda mutação da rodada.
- `Decimal` exato no fator e nos preços; dinheiro trunca (`money_trunc`), nunca arredonda.
- Nenhum modelo assinado muda de digest por causa desta feature — se mudar, a feature está
  errada.
- Cor nunca é o único indicador de que uma linha está reajustada.
- Nenhuma chamada paga, nenhum provider.

## Dependencies

- [ADR-0048](../../adr/0048-consolidado-contratual-do-orcamento-assinado.md) — o consolidado
  contratual, sua imutabilidade na rodada e o vínculo por digest assinado.
- [ADR-0027](../../adr/0027-price-source-provenance-and-bid-boundary.md) — a fronteira entre
  licitada e pré-licitação, que decide onde o reajuste pode existir.
- [ADR-0045](../../adr/0045-terceiro-estado-demanda-sob-contrato.md) — o regime
  `contracted_demand`.
- `PeriodProgress` (`contract.py:77`) — o par quantidade|valor por período, sem o qual esta
  feature exigiria reescrever histórico.

## Unknowns

1. **A declaração vive na rodada de medição ou no contrato?** Uma rodada é de um período; o
   reajuste é do contrato e vale para vários. Declarar na rodada é simples e imutável;
   declarar no contrato exige um contrato que hoje só existe como consolidado gravado por
   rodada. Decisão do ADR.
2. **Duas formas, um campo ou dois?** Fator e versão de tabela são mecanismos diferentes com
   o mesmo efeito. Modelá-los como um `kind` discriminado ou como dois caminhos separados é
   decisão do ADR.
3. **O que acontece com item novo trazido por RE-RA depois do reajuste** — ele nasce na base
   nova ou na contratada? Interage com a [issue #100](https://github.com/biahflow/croquito/issues/100),
   que ainda não tem contrato; o ADR declara a regra e a issue #100 a respeita.

## Risks

- **Reescrever o passado.** O risco central: um reajuste que recalcule medição aprovada muda
  dinheiro já pago e move digest assinado. Mitigado pela decisão de que o passado é intocável e
  por `PeriodProgress` já guardar valor.
- **Reajuste invisível.** Preço que muda sem a conta ao lado é preço que a prefeitura devolve.
  Critério 8 existe por isso.
- **Fator inventado.** Sem tabela de índices, o número é digitado — e digitado errado ele
  contamina a medição inteira. Mitigação: índice e período obrigatórios junto do fator, para
  que a declaração seja conferível contra a publicação oficial por quem revisa.
- **Confundir com reequilíbrio.** Explicitamente fora de escopo.

## Human Gates

1. **`ARCHITECTURE_DECISION_REQUIRED`** — [ADR-0055](../../adr/0055-reajuste-como-ato-declarado-sobre-o-consolidado.md),
   que decide os três Unknowns.
2. **`DESIGN_APPROVAL_REQUIRED`** — Design Approval Package da declaração do reajuste e da
   memória com a conta visível, conforme
   [design-approval](../../engineering-os/workflows/design-approval.md).

Nenhum agente cumpre nenhum dos dois.

## References

- [Issue #99](https://github.com/biahflow/croquito/issues/99)
- [Roadmap](../../product/ROADMAP.md) — "Próximo — medição além do v1"
- `packages/valuation/src/croquito_valuation/contract.py` — `ContractLine`, `PeriodProgress`
