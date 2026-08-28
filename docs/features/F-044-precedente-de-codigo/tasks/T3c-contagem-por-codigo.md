# F-044 T3c — A contagem de praças por código, à vista (tela)

- **feature_id**: F-044
- **task_id**: T3c
- **role**: builder
- **depends_on**: [T3a, T3b]
- **required_capabilities**: READ, WRITE (`apps/web/src/orcamento`, `docs/features/F-044-*/mock`), VALIDATE
- **risk**: BAIXO — nada de API, nada de dado novo: o campo já atravessa a fronteira desde a T3a.
- **relative_effort**: XS

## Por que existe

A T3a devolve `worksite_count` em dois níveis — do rótulo e **de cada código** — e o contrato
dela registrou a consequência numa linha: *"a tela mostra o do rótulo no cabeçalho"*. É essa
linha que esta task desfaz.

Um pacote de 4 praças pode conter um código que só 1 delas usou. Como o aceite é do pacote
inteiro em um clique (decisão 4 do pacote de design), esse código entra com a mesma autoridade
dos outros — e a feature declara temer exatamente isso:

> **Propagar erro com autoridade.** O precedente diz "você já fez assim", o que é um argumento
> forte. […] A contagem de praças ao lado é o controle mínimo.

O controle mínimo existia só para o rótulo. Esta task o estende ao código, que é a unidade que
de fato vai ser gravada.

## O pacote de design é a especificação

**Design Approval Package revisão 2**, estado 6 e decisão 8:
[`../mock/README.md`](../mock/README.md) e
[`../mock/precedente-de-codigo.html`](../mock/precedente-de-codigo.html).

A regra, em uma frase: **quando algum código do pacote vem de menos praças que o rótulo, todos
os cartões escrevem a contagem própria e o minoritário leva selo âmbar; quando o pacote é
unânime, nenhum cartão repete o que o cabeçalho já disse.**

## Scope

1. `precedente.ts` — `codigoMinoritario`, `contagemDeMinoritarios`, `pacoteUnanime` e
   `minoritarioNaConfirmacao`; `ConfirmacaoDoPrecedente` passa a carregar `worksiteCount` do
   rótulo, para que a lista de confirmação marque sem voltar ao precedente.
2. `labels.ts` — `frasePracasDoCodigo` ("em 1 das 4 praças") e `frasePacoteNaoUnanime`.
3. `OrcamentoApp.tsx` — o selo no cartão do bloco, o aviso âmbar antes do botão, e a mesma
   marca repetida na linha da lista de confirmação.
4. `styles.css` — `.selo-precedente-parcial` e `.aviso-precedente-parcial`, no âmbar que a
   folha já usa. **Nenhuma cor nova.**
5. Testes em `precedente.test.tsx`.

## Out of Scope

- **API, índice, migração**: o dado já vem pronto (`codes[].worksite_count`).
- **Limiar** (unknown 3): a marca é relativa ao rótulo e não fixa número nenhum.
- **Retirar o minoritário do aceite**: mudaria a decisão 4 do pacote e é revisão nova, com a
  evidência de que a marca sozinha não bastou.
- **Reordenar os códigos**: a ordem já vem do mais repetido para o menos, e é da T3a.

## Acceptance Criteria

1. Pacote não unânime: **todos** os cartões trazem a fração; só o minoritário leva o âmbar.
2. Pacote unânime: nenhum cartão traz contagem, e a tela é a da revisão 1.
3. O aviso diz quantos códigos são e que eles entram junto no aceite.
4. A marca se repete na lista de confirmação, e só na linha do minoritário.
5. O aceite continua sendo do pacote inteiro, em um pedido só: nada é desabilitado nem removido.
6. A distinção não é só cor: a fração vai escrita dentro do selo.
7. Nenhum teste existente afrouxado.

## Validation

```bash
npm --workspace @croquito/web run test -- src/orcamento/precedente.test.tsx
make check
make test
```
