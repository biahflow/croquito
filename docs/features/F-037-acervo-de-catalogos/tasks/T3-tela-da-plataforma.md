# F-037 T3 — Administrar o acervo na jornada de Plataforma

feature_id: F-037
task_id: T3
parent_plan: ../plan.md
role: builder
depends_on: T1

## Goal

O operador da plataforma vê o acervo, publica uma tabela e retira uma de circulação, pela
jornada de Plataforma — conforme a revisão 1 aprovada do
[Design Approval Package](../mock/README.md), telas 7 e 8.

## Leia antes de editar

- [`AGENTS.md`](../../../../AGENTS.md) na raiz e `apps/web/AGENTS.md`.
- [mock/README.md](../mock/README.md) — **inclusive a seção "Divergências apuradas"**, que
  governa esta task (ver abaixo).
- [`mock/acervo.html`](../mock/acervo.html) e as capturas `07-plataforma-acervo.png` e
  `08-publicar-tabela.png`.

## A divergência que governa esta task

**O mock desenha abas; a tela real não tem abas.** `PlatformApp.tsx` (810 linhas) não tem
mecanismo de aba nenhum: é composição por `<section className="authenticated-workspace">`
**empilhada**, uma por assunto — autorização de IA (linhas 296-418) e disponibilidade de
jornada (`DisponibilidadeDeJornada`, definido em 654-810, montado como filho do Fragment na
linha 423).

**Siga o padrão que existe.** O acervo vira uma **terceira seção empilhada**: componente
próprio, com sua própria `<section>`, seu próprio `useState`/`carregar`, seu próprio
`AlertaPersistente` (o componente já existe, linhas 76-82) e seu próprio toast — exatamente
como `DisponibilidadeDeJornada` faz. Monte-o como terceiro filho do Fragment de
`PlatformApp`, depois da linha 423, com um comentário de proveniência de decisão de design
no mesmo estilo do que há nas linhas 420-423.

**Não introduza abas.** O conteúdo aprovado entra inteiro; a fita de abas foi invenção do
mock e está registrada como divergência.

## Scope

1. **Seção "Acervo de tabelas de referência"** em `apps/web/src/plataforma/`:
   - lista das tabelas publicadas, com nome, origem, data-base, contagem de itens, digest
     curto, quem publicou e quando;
   - linha **fora de circulação** com a marca escrita e a contagem de rodadas que ainda a
     referenciam — ela continua visível, porque apagá-la esconderia o que aconteceu;
   - ato de retirar de circulação;
   - publicação: arquivo do catálogo normalizado + nome de exibição, com a frase que explica
     que origem, data-base e contagem vêm de dentro do arquivo;
   - recusa de republicar o mesmo conteúdo, traduzida do código estável do servidor.

2. **`api.ts`**: funções no padrão do arquivo (255 linhas) — `apiJson` de `../api`, nunca
   `fetch` direto; construtor de corpo **puro e separado** da chamada de rede, como
   `entitlementBody` (100-106) e `journeyEntitlementBody` (211-219); helper de path com
   `encodeURIComponent`, como `entitlementPath` (108-112); `Idempotency-Key` com
   `crypto.randomUUID()` nas mutações, como `setEntitlement` (143-159).

3. **`labels.ts`**: copy nova e as entradas novas em `MENSAGENS_POR_CODIGO` (linhas 59-74)
   para os códigos estáveis que a T1 entregou. `errorMessage` devolve `null` para código
   desconhecido (linhas 80-82) — **mantenha isso**: a tela nunca inventa frase para código
   que não conhece.

4. **Testes** em `apps/web/src/plataforma/`, no padrão dos existentes.

## Out of scope

- Qualquer arquivo em `services/` — o servidor é T1 e T2.
- Qualquer arquivo em `apps/web/src/orcamento/` — é a T4.
- Introduzir navegação por abas na Plataforma.
- O bloco **reservado** do mock (tela 9, atualização automática).

## Acceptance criteria

1. A seção corresponde à revisão 1 aprovada nas telas 7 e 8, com a divergência das abas
   resolvida como acima — **conferida renderizando a tela real**, não comparando com o
   recorte de CSS do mock. Foi assim que a F-034 achou três divergências que o recorte
   escondia.
2. Cor nunca é o único indicador: a linha fora de circulação carrega a **palavra**.
3. Erro de código desconhecido não vira frase inventada.
4. A seção só aparece para quem tem `platform_operator` — a condição já existe em
   `App.tsx:202-211`; não a duplique com regra própria.
5. `npm run web:check` e os testes de `apps/web` verdes.

## Pitfalls

- A SPA **não decide autorização**: ela mostra o que o servidor devolveu. Se o servidor
  recusa, a tela traduz a recusa — não a antecipa com regra própria.
- Digest aparece truncado na tela, com o valor inteiro no `title` — padrão já usado em
  `orcamento` (`shortDigest`).
- Nenhuma URL assinada e nenhum conteúdo de catálogo em log.
- TypeScript é `strict`; tipos vêm de `@croquito/contracts` quando existirem.

## Validation

```bash
npm --workspace @croquito/web run test
npm run web:check
```

## Report

Encerre com o `BUILD REPORT` completo do contrato do Builder — todos os campos presentes,
`none` onde não houver entradas. Se um portão reprovar em área que você não tocou, **pare e
reporte**; não conserte área alheia.
