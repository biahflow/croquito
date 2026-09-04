# F-044 T3b — O precedente no topo da shortlist (tela)

- **feature_id**: F-044
- **task_id**: T3b
- **role**: builder
- **depends_on**: [T2, T3a (contrato de API, fixado abaixo)]
- **required_capabilities**: READ, WRITE (`apps/web/src/orcamento`), VALIDATE
- **risk**: MÉDIO-ALTO — `OrcamentoApp.tsx` vivo; a etapa de códigos é o coração da jornada.
- **relative_effort**: L

## O pacote de design é a especificação

O **Design Approval Package revisão 1 foi aprovado em 2026-08-28** (Daniel Campos). Ele é a
especificação visual desta task:

- `docs/features/F-044-precedente-de-codigo/mock/precedente-de-codigo.html` — cinco estados
- `docs/features/F-044-precedente-de-codigo/mock/README.md` — as sete decisões e a proveniência

Leia os dois inteiros antes de começar. As sete decisões valem como requisito; as que mais
moldam o código:

1. **bloco próprio ACIMA dos blocos por fonte**, sem reordenar a cascata;
2. **a contagem de praças escrita por extenso** ("Você já usou isto em 4 praças");
3. **um código pode aparecer duas vezes** — no precedente e no bloco da fonte — e isso é
   intencional;
4. **aceite do pacote inteiro em uma revisão só**, com a lista à vista antes de confirmar;
5. **aceitar o precedente não fecha o pacote** — o fechamento continua ato separado;
6. **precedente de uma praça só** é exibido com aviso âmbar por extenso;
7. **precedente de outra fonte de preço não é oferecido, e nem aparece vazio** — quando não
   há, o bloco **não existe**; não desenhe estado vazio nem controle inerte.

## Contrato de API (fixado — a T3a implementa exatamente isto)

```
GET .../code-suggestions   (tudo que já existia continua igual, na mesma ordem)
 → { ...campos de hoje...,
     "precedents": [
       {"item_id": "ti_...", "normalized_label": "piso em concreto", "worksite_count": 4,
        "codes": [{"code": "BP09100050(B)", "worksite_count": 4, "description": "...",
                   "unit": "m2", "unit_price": "118.42", "unit_compatible": true,
                   "catalog_sha256": "..."}]}]}

POST .../code-assignments/decisions
 body: {"base_version": N, "item_id": "ti_...", "action": "confirm",
        "codes": ["BP09100050(B)", "ET39050109(/)"],     // mutuamente exclusivo com "code"
        "catalog_sha256": "..."}                         // 2026-09-04: SEMPRE, ver abaixo
 → a revisão nova, no formato que a jornada já usa
```

Item sem precedente **não aparece** em `precedents`. Código fora do catálogo vigente já vem
omitido pelo servidor. Decimais atravessam como string.

> **Correção de 2026-09-04.** Este contrato **omitia `catalog_sha256`** no aceite de lote, e a
> tela o implementou como escrito: todo aceite em lote voltava `422` e nada gravava, até a
> evidência de navegador expor o caso. A rota sempre exigiu a fonte em **toda** confirmação —
> os N códigos citam a MESMA fonte —, e o
> [API Contract](../../../architecture/API_CONTRACT.md) já a acompanhava; era este contrato de
> task, e a T3a que o espelha, que divergiam. A exclusão mútua é entre `code` e `codes`;
> `catalog_sha256` viaja nos dois.

## Scope

1. **`api.ts`/`requests.ts`**: o campo novo no tipo da resposta da shortlist, e o corpo com
   `codes` para o aceite de lote (mantendo o de `code` singular intacto).
2. **Módulo puro novo** (ou seção em módulo existente, se couber melhor): o estado do bloco de
   precedente e a lista de confirmação, testável sem DOM, no molde de `acervo.ts`/`matrix.ts`.
3. **`OrcamentoApp.tsx`**: o bloco de precedente acima dos blocos por fonte; o selo de
   precedente por item na lista de elementos; a lista de confirmação antes de gravar; o aviso
   do caso de uma praça.
4. **`labels.ts`**: a copy — contagem por extenso, aviso do precedente fraco, e o texto da
   confirmação. Domínio em português.
5. **`styles.css`**: a família `--precedente*` do pacote (índigo `#4a4a9c`, soft `#eeeef8`,
   line `#c2c2e4`, ink `#2f2f6b`). Respeite as regras da folha (`apps/web/src/styles.css:13-22`).
6. **Testes**: bloco aparece com a contagem; **não** aparece sem precedente nem em fonte
   diferente; o código repetido nos dois blocos é esperado; a lista de confirmação mostra o
   que vai ser gravado; confirmar manda **um** pedido com `codes`; aceitar **não** fecha o
   pacote; o aviso de uma praça; e **a cascata continua idêntica** (teste que prova que a
   ordem e o conteúdo dos blocos por fonte não mudaram).

## Out of Scope

- `services/`, `packages/`, migrações.
- Reordenar a cascata ou mexer no que a shortlist já mostra.
- Precedente de quantidade ou de receita de cálculo.
- Limiar de confiabilidade (unknown 3): a tela mostra a contagem e o aviso, e não esconde
  precedente por contagem baixa.

## Acceptance Criteria

1. O bloco aparece acima dos blocos por fonte, com a contagem escrita, e **não** reordena nada.
2. Sem precedente, ou com fonte diferente, o bloco **não existe** — nem vazio, nem desabilitado.
3. Confirmar o pacote manda **um** pedido com os N códigos, e mostra a lista antes.

   > **2026-09-04 — reprovado pela evidência de navegador, e cumprido depois dela.** O pedido
   > saía **sem `catalog_sha256`** e voltava `422`: a lista aparecia, o pedido era um, e nada
   > gravava. A causa é a omissão corrigida no "Contrato de API" acima. Reparo de tela, com a
   > rota intacta; sem fonte convergente o ato deixou de ser oferecido. **Re-verificado no
   > navegador na mesma data**: um pedido, `200`, versão 7 → 8, uma revisão nova, três pares
   > `confirmed` do mesmo elemento, e o pacote continuando em aberto. Ver
   > [`evidence.md`](../evidence.md), *"O desfecho: o reparo, e a re-verificação que ele
   > exigiu"*, e [`evidencia/07b-o-aceite-gravando.png`](../evidencia/07b-o-aceite-gravando.png).

4. Aceitar o precedente não fecha o pacote.
5. Precedente de uma praça traz o aviso por extenso.
6. A distinção do bloco não é só cor (cabeçalho escrito, borda, texto).
7. Nenhum teste existente afrouxado; a cascata provada intacta.

## Validation

```bash
cd /Users/danielcampos/workspace/daniel/croquito-f044-web
npm --workspace @croquito/web run test
make check
make test
```

## Armadilhas verificadas

- O `GET` da shortlist não paga e não avança versão — a tela não pode introduzir um ato ali.
- **Precedente é observação, nunca decisão**: nada é gravado sem o clique de confirmar.
- Decimais como string; não converta para `number` para guardar ou reenviar.
- Cor nunca é o único indicador.
- `matrix.ts` e os módulos puros da etapa são espelhos à mão, não contratos gerados — o
  type-check do web é quem os prende. Um campo com o tipo errado passa no vitest e quebra na
  integração; foi o que aconteceu com `kit_version` na F-042.
- `make check` valida todo link relativo de Markdown, inclusive deste arquivo.
