# F-037 T4 — A escolha da tabela na cascata do orçamento

feature_id: F-037
task_id: T4
parent_plan: ../plan.md
role: builder
depends_on: T2

## Goal

A orçamentista escolhe a tabela de preços de uma lista, em vez de obter e subir um arquivo.
O upload continua existindo como **alternativa nomeada**, para quem tem tabela própria —
conforme a revisão 1 aprovada do [Design Approval Package](../mock/README.md), telas 2 a 6.

## Leia antes de editar

- [`AGENTS.md`](../../../../AGENTS.md) na raiz e `apps/web/AGENTS.md`.
- [mock/README.md](../mock/README.md), **inclusive "Divergências apuradas"**.
- [`mock/acervo.html`](../mock/acervo.html) e as capturas 02 a 06.

## Mapa verificado

- **Seção da cascata**: `apps/web/src/orcamento/OrcamentoApp.tsx:1980-2100`.
  - 1980-1983 cabeçalho — usa `<div className="painel-cabecalho"><h2>`, **não** `eyebrow`
    (divergência 2 do mock; siga a tela real);
  - 1984-1994 dica por regime + `<SeloRegime variante="claro" />` quando `sobContrato`;
  - 1995-1997 aviso de cascata travada;
  - 1998-2065 a lista `<ol className="cascata">`, cada `<li>` com posição, `SeloFonte`,
    contagem, digest curto e os botões Subir/Descer/Remover;
  - 2066-2099 o `<form>` de instalação, com o `<input type="file">` (2087) e o botão (2094).
- **`instalarCatalogo`**: linhas 1133-1153 — `uploadCatalog` (1140) → `installCatalog`
  (1141) → `aplicarVersao` (1142).
- **Estado `catalogFile`**: linha 862.
- **`api.ts`** (943 linhas): `uploadCatalog` 585-590, `installCatalog` 718-729, tipo
  `CascadeEntry` 206-218, `EstimateState` 288-310.

## Scope

1. **A lista como caminho principal** (tela 2): seletor com nome, origem, data-base e
   contagem, lido da rota que a T2 entregou. O botão instala a escolha.

2. **A alternativa nomeada** (tela 3): link que troca o painel para o formulário de arquivo,
   dizendo **para quem** serve — tabela própria, a do contrato ou a EMOP licenciada. O
   caminho de upload que existe hoje (1133-1153, 2066-2099) é preservado inteiro; ele só
   deixa de ser a primeira coisa que aparece.

3. **Procedência na cascata** (tela 4): cada `<li>` da lista instalada ganha a marca de
   `DO ACERVO` / `TABELA PRÓPRIA`, lida do campo que a T2 acrescentou à `CascadeEntry`.
   Entrada sem o campo (cascata instalada antes da feature) lê como tabela própria.

4. **Filtro sob regime** (tela 5): a lista já vem filtrada do servidor. A tela **não
   reimplementa** a regra — ela mostra o que recebeu e explica por escrito por que as outras
   não aparecem, no espírito de `origensAceitasNaCascata` (`orcamento/labels.ts:64`), que já
   lê a regra do servidor em vez de guardar cópia.

5. **Acervo vazio** (tela 6): estado, não erro. Afirma que a plataforma ainda não publicou e
   oferece o caminho do arquivo.

6. **Rótulos** em `orcamento/labels.ts` e **testes** em `apps/web/src/orcamento/`.

## Out of scope

- Qualquer arquivo em `services/` — o servidor é T1 e T2.
- Qualquer arquivo em `apps/web/src/plataforma/` — é a T3.
- O bloco **reservado** do mock (tela 9, atualização automática).
- Mudar as regras da cascata (ordem, remoção, trava) — só muda de onde a fonte vem.

## Acceptance criteria

1. As telas correspondem à revisão 1 aprovada (telas 2 a 6), **conferidas renderizando a
   tela real com a folha de estilo do projeto** — não comparando com o recorte de CSS do
   mock. Foi assim que a F-034 achou três divergências que o recorte escondia.
2. O caminho de upload continua funcionando exatamente como hoje, provado por teste que
   estende os existentes sem enfraquecê-los.
3. Cor nunca é o único indicador da procedência: a marca é a **palavra**.
4. Cascata instalada antes da feature continua legível, sem marca de acervo.
5. A tela não guarda cópia da regra do regime — o filtro vem do servidor.
6. `npm run web:check` e os testes de `apps/web` verdes.

## Pitfalls

- `OrcamentoApp.tsx` tem 2.842 linhas e é arquivo vivo: mude a seção 1980-2100 e o que ela
  exige, não aproveite para reorganizar o resto.
- A SPA **não decide autorização** nem consenso; etapas são espelho do estado do servidor.
- Digest truncado com o valor inteiro no `title`, como já se faz (`shortDigest`).
- TypeScript é `strict`; tipos gerados vêm de `@croquito/contracts`.
- Nenhuma URL assinada e nenhum conteúdo de catálogo em log.

## Validation

```bash
npm --workspace @croquito/web run test
npm run web:check
```

## Report

Encerre com o `BUILD REPORT` completo do contrato do Builder — todos os campos presentes,
`none` onde não houver entradas. Se um portão reprovar em área que você não tocou, **pare e
reporte**; não conserte área alheia.
