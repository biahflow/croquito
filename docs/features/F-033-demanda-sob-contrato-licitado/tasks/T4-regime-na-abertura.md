# F-033 T4 — O rótulo que não mente e o regime na abertura

feature_id: F-033
task_id: T4
parent_plan: ../plan.md
role: builder
depends_on: T3

## Goal

Três coisas, na jornada do orçamento: a tela para de afirmar um regime onde não há rodada; a
rodada pode nascer já declarada sob contrato; e o card da lista diz o regime antes de a
pessoa abrir.

Conforme a **revisão 2** do [Design Approval Package](../mock/README.md), aprovada por ato
humano em 2026-08-22 — telas 2, 3, 4 e 5 de [`abertura-r2.html`](../mock/abertura-r2.html).

## Leia antes de editar

- [`AGENTS.md`](../../../../AGENTS.md) na raiz e `apps/web/AGENTS.md`.
- [mock/README.md](../mock/README.md), seção **"Revisão 2"** inteira, incluindo as quatro
  decisões que ela carrega.
- [`mock/abertura-r2.html`](../mock/abertura-r2.html) e as capturas `r2-02` a `r2-05`.
- O escopo 6 do [feature contract](../feature.md).

## O problema, para você não otimizar a coisa errada

Na tela de lista **não existe rodada nenhuma**, e mesmo assim o cabeçalho afirma
`ORÇAMENTO-BASE · PRÉ-LICITAÇÃO`. São três telas assim. A tela afirma um regime sobre nada —
e é isso que se conserta aqui, não a estética do cabeçalho.

## Scope

### 1. Rótulo neutro onde não há rodada

`apps/web/src/orcamento/OrcamentoApp.tsx`, linhas **1868, 1885, 1904** — os três
early-returns: sem sessão, sem acesso, nenhum orçamento aberto. O eyebrow passa a
`ORÇAMENTO-BASE`, sem sufixo.

**A faixa âmbar também afirma o momento, e também muda.** `AVISO_ORCAMENTO`
(`labels.ts:31-33`) diz *"Orçamento-base **de pré-licitação**; o preço vem da cascata
declarada…"*. Crie uma constante nova para as telas sem rodada, no espírito do mock: *"O
orçamento-base precifica pela cascata declarada na rodada. Nenhum preço daqui alcança um
boletim de medição."* `AVISO_ORCAMENTO` continua existindo, para a tela **com** rodada em
pré-licitação.

**Não toque nas linhas 2154-2157 nem em 2188** — são a tela *com* rodada, onde o sufixo e a
faixa são verdade e continuam condicionais ao regime.

### 2. Campo Regime no formulário de abertura

Dentro do `<form>` (**2015-2139**), entre a "Demanda de origem" (termina em 2130) e o aviso
final (2131). Molde: o campo Teto (**2096-2116**), com `<label className="campo">`.

- `EMPTY_ESTIMATE_FORM` (**166-174**) ganha o campo, no tipo de `regimeInput`.
- O `<select>` reusa `REGIME_OPCAO_PRE_LICITACAO` e `REGIME_OPCAO_SOB_CONTRATO`
  (`labels.ts:98-99`) — o mesmo padrão de `<select>` já existe em `PainelRegimeDaRodada`
  (**265-277**).
- `criarOrcamento` (**1385-1408**) passa o valor adiante.
- `CreateEstimateDraft` (`api.ts:511-519`) ganha `pricingRegime?`.
- `createEstimateBody` (`requests.ts:100-113`) inclui a chave **só quando houver valor**,
  seguindo o padrão de omissão de `targetFields` (**122-140**): campo vazio devolve `{}`.
  Ausência não é um valor, é a falta dele — e o servidor conta com isso.

**Uma diferença que importa**, e que você não deve copiar do painel de declarar depois: lá,
escolher "pré-licitação" mantém o botão **desabilitado**, porque é onde a rodada já está e
escolher não é ato. **Aqui é o padrão**, e o botão segue ativo — simplesmente não se envia o
campo.

**Três textos ao redor do campo**, e o terceiro é decisão humana de 2026-08-22 que
**diverge do mock**:

1. antes: a pergunta (a demanda corre dentro de contrato já licitado?);
2. depois: a consequência + a mão única;
3. depois: **`DICA_REGIME`** (`labels.ts:88-90`) — "restringir a origem não confere o
   contrato". O mock da revisão 2 não a mostra em lugar nenhum, e quem declarasse pela
   abertura nunca a leria. Ela é a decisão 6 da revisão 1 e a decisão 6 do ADR-0045: como a
   abertura vira o caminho principal, o produto deixaria de dizer o que **não** garante
   justamente no ato que virou o normal.

### 3. Selo do regime no card da lista

`<li className="rodada-linha">` (**1954-1995**): `<SeloRegime variante="claro" />`
(componente em **209-223**) quando `item.pricing_regime` não for nulo. `EstimateSummary`
(`api.ts:170-185`) ganha o campo, que a **T3 já publica no servidor**.

Card sem selo é rodada em pré-licitação. **Nenhuma pastilha nova é inventada** — é o mesmo
selo da revisão 1, num terceiro lugar (decisão 4 do pacote).

### 4. Copy do painel de declarar depois

`PainelRegimeDaRodada` (**239+**, usado em **2405-2413**) permanece **estruturalmente
intacto**. Só a copy muda, para dizer que a rodada foi aberta em pré-licitação e que este é
o caminho de correção — deixa de ser o único caminho, não deixa de ser um caminho.

`DICA_REGIME` **continua aqui**. Ela não migra: passa a existir nos dois lugares.

## Out of scope

- **Qualquer arquivo em `services/`** — o servidor é a T3, já entregue.
- A tela **com** rodada aberta (cabeçalho, aba Cascata, selo do topbar): nada ali muda.
- Reordenar os painéis da aba Cascata. Com a rodada nascendo declarada,
  `ESTIMATE_REGIME_CASCADE_DIRTY` deixa de ser alcançável pelo caminho normal — a recusa
  continua implementada e testada, porque a rodada aberta sem regime ainda chega nela.
- Qualquer mudança de comportamento do regime: ele segue mão única, e isso é do ADR-0045.

## Acceptance criteria

1. Nenhuma das **três** telas sem rodada afirma momento — nem no eyebrow, nem na faixa
   âmbar. Coberto por teste.
2. A tela **com** rodada continua afirmando, e o sufixo troca conforme o regime — o teste
   existente em `OrcamentoApp.test.tsx:609` continua passando **sem ser enfraquecido**.
3. Rodada aberta com o regime escolhido nasce declarada, sem passar pelo painel.
4. O corpo da criação **não** carrega `pricing_regime` quando o regime não foi escolhido.
5. O card mostra o selo só quando a rodada tem regime; sem regime, nenhum selo.
6. `DICA_REGIME` aparece **nos dois lugares**: no campo da abertura e no painel de declarar.
7. As telas correspondem à revisão 2 aprovada, **conferidas renderizando a tela real com a
   folha de estilo do projeto** — não comparando com o recorte de CSS do mock. Foi assim que
   a F-034 achou três divergências que o recorte escondia.
8. `npm run web:check` e os testes de `apps/web` verdes; `make check` verde.

## Pitfalls

- `OrcamentoApp.tsx` tem ~3.144 linhas e é arquivo vivo: mude os pontos listados e o que
  eles exigem, não aproveite para reorganizar o resto.
- A SPA **não decide autorização** nem regra de domínio: ela mostra o que o servidor
  devolveu. O regime continua sendo recusado/aceito pelo servidor.
- Cor nunca é o único indicador: o selo carrega a **palavra**.
- TypeScript é `strict`; `PricingRegime` (`api.ts:134`) é só `"contracted_demand"` — o
  cliente nunca envia `pre_bid`, que o servidor aceita no schema apenas para recusar.
- Testes: `OrcamentoApp.test.tsx` usa `renderToStaticMarkup` (SSR), sem testing-library. As
  asserções das linhas **616-617** cobrem as telas sem rodada e precisam ganhar a
  verificação do rótulo neutro — estenda, não enfraqueça.

## Validation

```bash
npm --workspace @croquito/web run test -- src/orcamento/
npm run web:check
make check
```

## Report

Encerre com o `BUILD REPORT` completo do contrato do Builder — todos os campos presentes,
`none` onde não houver entradas. Se um portão reprovar em área que você não tocou, **pare e
reporte**; não conserte área alheia.
