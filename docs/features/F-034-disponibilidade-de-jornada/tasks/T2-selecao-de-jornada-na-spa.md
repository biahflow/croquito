# F-034 T2 — A SPA renderiza a lista de jornadas que o servidor resolveu

feature_id: F-034
task_id: T2
parent_plan: ../plan.md
role: builder
depends_on: T1

## Goal

O seletor de jornadas passa a mostrar exatamente as jornadas que `GET /v1/me` devolveu, sem
recalcular papel no navegador.

## Scope

1. **`JourneySwitch`** (`apps/web/src/App.tsx:111-165`) renderiza um botão por jornada
   presente na lista recebida. **Não renderizar** quando ausente — nunca desabilitar, nunca
   esconder por CSS. É o mecanismo já em produção para a aba Plataforma, e o comentário de
   decisão em `App.tsx:138-144`, que hoje justifica o oposto, precisa ser substituído pelo
   registro da decisão nova e sua data.
2. **A aba Plataforma continua governada por papel** (`platform_operator`), não pela lista
   de jornadas: ela não é uma jornada, é onde a disponibilidade é administrada.
3. **Aterrissagem padrão**: hoje `readRoute` cai em `croqui` quando não há parâmetro
   (`route.ts:152`), o que mandaria para uma jornada indisponível quem não a tem. A abertura
   sem parâmetro passa a escolher a primeira jornada disponível da lista.
4. **Lista vazia**: nenhuma aba, **mais** aviso escrito dizendo que a conta não tem jornada
   liberada e a quem pedir acesso. Reusar `app-alert` com `role="alert"`, já usado para o
   `sessionNotice` (`App.tsx` ~532-542). Tela muda sem explicação é o que não pode acontecer.

## Out of scope

- Qualquer arquivo em `services/` — o contrato vem pronto da T1.
- **`apps/web/src/plataforma/api.ts`**: o tipo `Journey` e o campo `Me.journeys` já
  existem lá (PLAN_DEVIATION registrada no plano). Importe; não edite o arquivo — ele
  é da T3, que corre em paralelo.
- Qualquer lógica de papel no navegador: a SPA não decide, ela renderiza.
- **Guarda de rota**: quem digita a URL de uma jornada indisponível continua montando a
  jornada e lendo o `403` por extenso, exatamente como a Plataforma já faz
  (`App.tsx:566-569`). Barrar no cliente trocaria uma frase legível por tela em branco.
- A seção de administração por tenant — é a T3.

## Acceptance criteria

1. Lista com as três jornadas: seletor idêntico ao de hoje.
2. Lista com uma só: só ela aparece, e a abertura sem parâmetro cai nela.
3. Lista vazia: nenhuma aba e o aviso escrito visível, com `role="alert"`.
4. Falha ao ler `/v1/me`: fail-closed, nenhuma jornada oferecida — é o que já acontece
   hoje com papéis (`setRoles([])`).
5. Testes de `App.test.tsx` (bloco "seletor de jornadas", 88-173) atualizados; o
   `"Orçamento é o terceiro botão, sem depender de papel nenhum"` (linha 113) inverte de
   propósito e o novo nome deve dizer o que passou a valer.
6. `npm --workspace @croquito/web run test` e `run check` verdes.

## Pitfalls

- `renderToStaticMarkup(<App />)` cai sempre no regime sem sessão: teste a regra no
  `JourneySwitch`, que é exportado justamente para isso.
- Não introduza constante de papel no front: com a lista pronta do servidor, ela não é mais
  necessária, e deixá-la seria duas fontes de verdade.
- Cor nunca é o único indicador; o aviso é texto.

## Validation

```bash
npm --workspace @croquito/web run test
npm --workspace @croquito/web run check
```
