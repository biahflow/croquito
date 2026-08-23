# F-035 T3 — A etapa "Aprovação e despacho" na jornada do orçamento

feature_id: F-035
task_id: T3
parent_plan: ../plan.md
role: builder
depends_on: T2

## Goal

A jornada do orçamento ganha o ato de assinar, com o peso de ato: dois passos explícitos, a
identidade da sessão mostrada e nunca digitável, o registro do que foi assinado, a
caducidade visível e o despacho como consequência — não como link que aparece porque um
arquivo existe.

Conforme a **revisão 1** do [Design Approval Package](../mock/README.md), aprovada por ato
humano em 2026-08-22 — telas 1 a 9 de [`aprovacao.html`](../mock/aprovacao.html).

## Leia antes de editar

- [`AGENTS.md`](../../../../AGENTS.md) na raiz e `apps/web/AGENTS.md`.
- [mock/README.md](../mock/README.md) **inteiro**, incluindo as sete decisões que o pacote
  carrega e as duas questões abertas.
- [`mock/aprovacao.html`](../mock/aprovacao.html) e as capturas `01` a `09`.

## A decisão que a aprovação do pacote fechou

A etapa **"Planilha" é substituída por "Aprovação e despacho"**, não acrescentada. A barra
de etapas do mock tem seis, e "Planilha" não está entre elas: com a T2 no ar, a planilha
deixa de existir antes do despacho, e uma etapa sobre um arquivo que ainda não existe não
tem o que mostrar. Isso fecha o unknown 1 do contrato.

## O que a T2 já entregou e você vai consumir

- `POST .../estimate` **só monta**; `POST .../estimate/approve` assina;
  `POST .../estimate/export` despacha.
- `GET .../estimate` devolve o bloco `approval` (`approved`, quem, quando, os dois digests,
  `stale`), e o estado da rodada ganhou o bloco no padrão de bloco-ausente-é-chave-ausente.
- Recusas com código estável, inclusive a de auto-aprovação.

Confira a forma exata em `docs/architecture/API_CONTRACT.md`, que a T2 atualizou.

## Scope

### 1. A etapa

`apps/web/src/orcamento/etapas.ts`: `planilha` → `aprovacao`, título "Aprovação e despacho".

O resumo lê **`approved` e `stale` juntos**, no molde de `resumoDaAprovacao`
(`apps/web/src/medicao/etapas.ts:152-162`): na aprovação caduca os dois valem ao mesmo
tempo, e um resumo que lesse só `approved` diria "aprovado" sobre um orçamento que o
despacho já vai recusar. A ordem das perguntas é a do desenho aprovado — **caduca primeiro**.

### 2. O ato e o registro

`OrcamentoApp.tsx`, espelhando `MedicaoApp.tsx:526-717` e o CSS de
`apps/web/src/medicao/styles.css:894-1050`:

- **`AtoDeAprovacao`** — dois passos explícitos. O primeiro lista as consequências por
  extenso; o segundo repete a consequência sobre o âmbar de atenção. Não é "tem certeza?"
  vazio.
- **`RegistroDaAprovacao`** — quem, quando, sobre qual conteúdo. Na caducidade, os **dois
  digests lado a lado**, e a **palavra** ("Aprovação caduca") é a marca — o tracejado âmbar
  é redundância dela.
- **A identidade é mostrada, nunca digitável.** Não existe campo de nome: o texto diz que o
  servidor lê a identidade do token e recusa qualquer nome vindo do cliente.

### 3. Os estados que faltam

- **Auto-aprovação recusada** (tela 6): a mensagem nomeia quem montou e diz que acumular
  papéis não contorna — porque a primeira reação de quem é recusado é procurar o papel que
  falta.
- **Sem o papel de aprovador** (tela 7): lê o estado, não opera o ato.
- **Despacho em curso** (tela 8): passo a passo **escrito**, não barra de progresso — três
  dos quatro passos acontecem antes de existir arquivo, e uma barra esconderia isso. E a
  faixa de auditoria reprovada afirma por extenso que **nada foi publicado** e que a
  aprovação continua válida.
- **Despachado** (tela 9): só aqui o link da planilha existe, com o digest ao lado.

### 4. Transporte e rótulos

`api.ts` ganha o tipo do bloco `approval` e as duas chamadas, no molde de
`medicao/api.ts:178-186` e `727-737` — corpo só `base_version`. `labels.ts` ganha a copy e
as entradas dos códigos estáveis novos; código desconhecido continua sem virar frase
inventada.

## Out of scope

- **Qualquer arquivo em `services/`** — o servidor é a T2, já entregue.
- **Qualquer arquivo em `tests/e2e/`** — é a T4.
- O bloco **reservado** do mock (tela 10: envio por e-mail/Drive).
- A jornada de medição: `MedicaoApp.tsx` é molde de leitura, não alvo de edição.

## Acceptance criteria

1. A etapa substitui "Planilha" e o resumo lê `approved` e `stale` juntos, com a caducidade
   perguntada primeiro.
2. O ato tem dois passos, e a identidade da sessão aparece sem campo de nome.
3. Na caducidade, os dois digests aparecem e a **palavra** marca o estado — cor não é o
   único indicador.
4. O link da planilha só existe depois do despacho.
5. A recusa de auto-aprovação explica a regra, não só nega.
6. As telas correspondem à revisão 1 aprovada, **conferidas renderizando a tela real com a
   folha de estilo do projeto** — não comparando com o recorte de CSS do mock. Foi assim que
   a F-034 achou três divergências que o recorte escondia, e a T3 da F-037 achou o selo
   caindo na linha errada.
7. A SPA não decide autorização: ela mostra o que o servidor devolveu e traduz a recusa.
8. `npm run web:check` e os testes de `apps/web` verdes; `make check` verde.

## Pitfalls

- `OrcamentoApp.tsx` tem ~3,2 mil linhas e é arquivo vivo: mude o que a etapa exige, não
  aproveite para reorganizar o resto.
- **Não invente dado que o servidor não manda.** Se o mock mostrar algo que nenhuma rota
  devolve, mostre o estado sem aquilo e **reporte** — foi o que a T3 da F-037 fez com a
  contagem de rodadas, e é o comportamento certo.
- Digest truncado na tela, valor inteiro no `title` (`shortDigest`).
- TypeScript é `strict`; tipos gerados vêm de `@croquito/contracts`.
- Nenhuma URL assinada em log.

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
