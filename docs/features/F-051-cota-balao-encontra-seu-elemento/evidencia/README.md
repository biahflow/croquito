# F-051 — Evidência de navegador

Feature: [A cota-balão encontra seu elemento](../feature.md) · Tarefa:
[T7](../tasks/T7-evidencia-e-o-caso-real.md) · Data: **2026-09-04**

Esta é a validação `BROWSER_REQUIRED` do critério de aceite 5 do contrato: os estados que o
[Design Approval Package aprovado](../mock/README.md) desenhou, **exercidos de verdade** na
tela que a T6 entregou, contra o stack local em Docker — PostgreSQL, floci e Keycloak reais,
API em `uvicorn`, SPA em `vite`, login pela porta do Keycloak.

**Dado 100% sintético.** Nenhum croqui, prancha, legenda ou medição de cliente foi aberto,
usado ou capturado. A prancha é o PDF sintético de `tests/fakes.py` e o pacote de revisão é o
bundle sintético de `tests/bundles.py`, com as duas cotas-balão que a T7 acrescentou.

O **gate 3 da feature** — o aceite contra o job real do Campo da Toca — **não é isto**, e
continua pendente: é ato do dono, com o roteiro de [`ROTEIRO-GATE-3.md`](ROTEIRO-GATE-3.md)
em mãos.

## A fixture, e por que ela fecha

Duas leituras novas no bundle sintético, as duas escritas longe do que medem:

| Leitura | Texto | Hint estruturado | O que acontece |
| --- | --- | --- | --- |
| `rd_5555…` | `C=25,90 m` (largura) | `B` | casa com o elemento "B" declarado → candidata por identidade → restrição do solver |
| `rd_6666…` | `h=4,40 m` (altura) | `E` | não casa com elemento nenhum → **a tela de hoje**, sem candidata nova |

Nenhuma das duas nasce com candidata de proximidade: elas entram no pacote na lista das
**não associadas**, que é onde o associador as deixa. O `25,90` fecha porque é a mesma
largura que o retângulo sintético do repositório já tem (`25,90 × 21,75`) — a cota-balão
mede o alambrado que as duas linhas propostas desenham, e o resíduo dá `0,000 m`.

## As capturas

Chromium via Playwright 1.62.1, viewport **1440 px**, `deviceScaleFactor` 2, `locale`
`pt-BR`, autenticado como **`engenheiro.local`** (papel `engineer`) pelo Keycloak local.
Cada imagem é o recorte do painel que ela documenta; **nenhuma foi editada**. Zero erros de
console na corrida inteira.

| # | Arquivo | O que prova |
| --- | --- | --- |
| 01 | [`01-a-cota-balao-sem-elemento.png`](01-a-cota-balao-sem-elemento.png) | **O problema, na tela.** A leitura traz o chip tracejado `elemento (hint do modelo): B` — o hint deixou de ser achatado (T1) —, e o seletor de associação tem, além do "Selecione um candidato", **uma única opção**: "Anotação da folha — não mede um elemento". Sem identidade declarada, a única saída honesta é a que não constrange geometria nenhuma |
| 02 | [`02-o-ato-de-declarar.png`](02-o-ato-de-declarar.png) | **O ato humano, antes de assinar.** Duas propostas marcadas à mão, o rótulo "B" escrito, a justificativa obrigatória preenchida, e o campo do `element_ref` **somente-leitura** dizendo "cunhada no ato pelo servidor". O painel de sugestões diz por escrito que não tem o que sugerir — o modelo não rotulou proposta nenhuma nesta fixture —, e a declaração manual segue sendo o caminho completo |
| 03 | [`03-o-elemento-declarado.png`](03-o-elemento-declarado.png) | **O `EL-001` cunhado**, com carimbo por **papel** (`engineer`), instante e a versão da revisão sobre a qual o ato caiu; ao lado, "Renomear rótulo" e "Revogar identidade" como atos próprios |
| 04 | [`04-candidata-por-identidade.png`](04-candidata-por-identidade.png) | **A candidata por identidade** no mesmo `<select>` de sempre, num `<optgroup>` rotulado por escrito — `Pela identidade — ◇ EL-001 · B` —, com as duas propostas do elemento e a relação por extenso. Sem score, sem distância. Abaixo, o `field-hint` diz **por que** ela está ali: "O hint 'B' casa com o elemento declarado ◇ EL-001 · B — as propostas dele entram como candidatas pela identidade, independente de distância" |
| 05 | [`05-confirmada-pelo-portao.png`](05-confirmada-pelo-portao.png) | **A confirmação pelo portão de sempre**: decisão registrada com autor, instante e a justificativa escrita, e "Corrigir decisão registrada" no lugar dos botões — nenhum caminho novo de escrita foi aberto |
| 06 | [`06-o-hint-que-nao-casa.png`](06-o-hint-que-nao-casa.png) | **O critério de aceite 2, escrito na tela.** A leitura com hint `E` mostra o chip do hint, **nenhum grupo "Pela identidade"** (nem vazio), o seletor com a única opção de hoje, e a frase que diz o que falta: "Nenhum elemento declarado tem o rótulo 'E' — nenhuma candidata nova. O hint fica visível, esperando ou uma declaração ou uma correção" |
| 07 | [`07-o-balao-amarrado-a-forma.png`](07-o-balao-amarrado-a-forma.png) | Na etapa do traçado, a cota-balão aparece como cota que **mede a forma ① linha horizontal · 30 px** — deixou de ser nota solta |
| 08 | [`08-a-orfa-sem-vao.png`](08-a-orfa-sem-vao.png) | A cota-balão órfã, na mesma lista, continua "anotação da folha — **sem vão**": o custo do caminho de hoje, intocado para quem não tem elemento declarado |
| 09 | [`09-o-tracado-resolvido.png`](09-o-tracado-resolvido.png) | **O resíduo.** "Traçado resolvido — 3 elementos exatos e 0 aproximados" e "**3 cotas** conferidas contra a geometria; a pior diferença foi 0,000 m no trecho medido na horizontal, dentro da tolerância de 0,005 m". São três porque a cota-balão entrou: sem ela seriam duas, e a lista abaixo mostra as duas amarrações horizontais de `25,90` — a de perto e a do balão |
| 10 | [`10-a-cena-com-a-identidade.png`](10-a-cena-com-a-identidade.png) | **O elo fechado.** Na etapa de aprovação, a cena nasceu com `◇ EL-001 · B · camada DETALHES · 2 entidades · exata · → alimenta a medição`. Ninguém redigitou a letra do balão em lugar nenhum: ela viajou da revisão para a cena pelo traçado |

### O único artifício de rendição, declarado

Nas capturas 01, 04 e 06 o `<select>` nativo foi aberto para a foto com `size="6"`, porque
um `<select>` fechado não mostra as opções numa imagem estática. É o **mesmo controle**,
com as mesmas opções: nada do estado da revisão muda por causa disso, e é o mesmo artifício
que o pacote de design declarou. A prova literal, tirada do DOM da própria página, está
abaixo — e é o `outerHTML` do controle real, não uma reconstrução.

Antes da declaração (capturas 01 e 06 têm exatamente esta lista):

```html
<select><option value="">Selecione um candidato</option><option value="annotation:no-element">Anotação da folha — não mede um elemento</option></select>
```

Depois do ato de declarar (captura 04):

```html
<select><option value="">Selecione um candidato</option><option value="annotation:no-element">Anotação da folha — não mede um elemento</option><optgroup label="Pela identidade — ◇ EL-001 · B"><option value="vp_1111111111111111">① linha horizontal · 30 px · identidade declarada do elemento</option><option value="vp_2222222222222222">② linha vertical · 20 px · identidade declarada do elemento</option></optgroup></select>
```

## Como o estado foi semeado

Tudo pelo caminho de produção, e o mais próximo possível do que o dono faria:

1. **Croqui** — `POST /v1/uploads/presign` → `PUT` real na URL assinada do floci →
   `POST /v1/jobs` → o worker local consome a ingestão → `seed_review` do pacote sintético
   com as duas cotas-balão. A semeadura usa token de teste porque o realm local desabilita
   direct access grants e não existe token fora do navegador; **tudo o que a evidência
   fotografa foi feito no navegador, com o token real do Keycloak**.
2. **Declaração, confirmação e traçado** — no navegador: os cliques das capturas 02 a 08,
   incluindo o aceite em lote do traçado, que a API enfileira e o worker local resolve.
3. **Aprovação** — a etapa 3 foi aberta para ler a identidade transportada (captura 10);
   a assinatura e o export não foram exercidos, porque não é o que esta feature muda.

Nenhum provider pago foi chamado em ponto nenhum: `CROQUITO_REAL_PROVIDERS_ENABLED`
permaneceu `false` e as chaves ficaram vazias.

## O ambiente, e o que ele NÃO tocou

O stack local do dono (projeto compose `croquito-local`, portas 5432/4566/8083) tem **dados
reais** — o job do Campo da Toca — e **não foi tocado**: nenhum `make db-init`, nenhum
`make down-services`, nenhum container dele parado ou reiniciado.

A evidência subiu um stack **paralelo e isolado**:

| Peça | Onde |
| --- | --- |
| Projeto compose | `croquito-f051` (volumes `croquito-f051_postgres-data` e `croquito-f051_floci-data`, criados e destruídos por esta tarefa) |
| PostgreSQL | `127.0.0.1:5442` — banco novo, migrações `0001 → 0032` aplicadas do zero |
| floci (emulador AWS) | `127.0.0.1:4576` |
| Keycloak | `127.0.0.1:8093` |
| API | `uvicorn` em `127.0.0.1:8010` (a 8000 está ocupada por outro projeto na máquina) |
| SPA | `vite` em `localhost:5173` |

Os arquivos de andaime — o override de compose, o script de semeadura, o laço do worker e o
roteiro do Playwright — ficaram em `output/`, que é ignorado pelo Git e tem retenção local
de sete dias. Ao fim da captura, **só** o stack `croquito-f051` foi derrubado, com os
volumes que ele mesmo criou.

> **Nota para a próxima captura:** os dois `.env.local` do andaime (o da raiz e o de
> `apps/web/`) precisam ser **apagados ao fim**. O `apps/web/.env.local` é lido pelo
> `vitest`, e um `VITE_API_BASE_URL` apontando para a porta da captura reprova onze testes
> de `src/orcamento/` que conferem a URL padrão — aconteceu nesta rodada, entre a captura e o
> portão, e o `make test` só ficou verde depois de removê-los.

## O que NÃO foi exercido

- **Nenhum croqui real atravessou.** A praça, a prancha e as cinco leituras são fixture
  inventada. O critério de aceite 1 do contrato fala do job do Campo da Toca, e é o gate 3
  que o exerce — ato do dono.
- **A sugestão assistida com sugestões de verdade.** As propostas do bundle sintético não
  têm rótulo do modelo, então o painel aparece na sua forma vazia (que é um estado desenhado
  no DAP, e está na captura 02). O caminho "semear a seleção a partir da sugestão" e a
  recusa com motivo têm teste (`tests/api/test_review_element_suggestions.py`,
  `apps/web/src/reviewElementIdentityPanel.test.tsx`), não imagem.
- **Renomear e revogar identidade na tela.** Os dois botões aparecem na captura 03; os atos
  não foram executados no navegador. Têm teste de API e de tela.
- **As recusas** (rótulo duplicado, proposta fora do snapshot, papel insuficiente, conflito
  de `base_version`) — todas com teste, nenhuma fotografada.
- **Corrigir o hint pela decisão** (o campo "Elemento do balão — corrigir o hint do modelo"
  aparece nas capturas 04 e 06, preenchido com o valor lido) não foi usado para trocar o
  rótulo e recunhar as candidatas; isso tem teste na T4.
- **Aprovação, export e o quantitativo da F-047** sobre esta cena: a captura 10 mostra a
  identidade na cena e o selo "→ alimenta a medição", mas o `quantitativos.csv` e a
  medição não foram gerados nesta corrida.
- **Nada foi exercido em homologação.** O ambiente de HML está derrubado por decisão do
  dono; toda a evidência é do stack local.
