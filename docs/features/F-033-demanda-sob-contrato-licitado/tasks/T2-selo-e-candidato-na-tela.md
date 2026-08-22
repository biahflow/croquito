# F-033 T2 — Selo do regime, declaração e candidato a aditivo na tela

feature_id: F-033
task_id: T2
parent_plan: ../plan.md
role: builder
depends_on: T1

## Goal

A jornada do orçamento mostra em que regime a rodada está, permite declarar que ela corre
sob contrato licitado, e lê o item rejeitado como candidato a aditivo — para a orçamentista
não descobrir a regra pelo erro.

## Design aprovado — vinculante

Revisão 1, aprovada por ato humano em 2026-08-22: [`../mock/README.md`](../mock/README.md) e
[`../mock/regime.html`](../mock/regime.html), com **oito** capturas congeladas
(`01-cabecalho-regime.png` … `08-reservado.png`). Abra o HTML e as imagens. A tela deve
corresponder a essa revisão; divergir dela é revisão nova e **não é decisão do builder** — se
algo não couber, PARE e reporte.

Conferir contra as **capturas**, não contra o recorte de CSS do HTML: o mock carrega um
recorte da folha, e foi exatamente aí que a T3 da F-034 achou três divergências reais
(última label esticando a linha, lista de chips no lugar de linhas, verde vindo de outra
classe). Renderize com a folha real e compare.

## O que a T1 já publicou

`GET /v1/estimate-rounds/{id}` traz, **só quando há regime**, o bloco:

```json
"regime": {
  "value": "contracted_demand",
  "allowed_cascade_origins": ["sco"],
  "amendment_candidates": 0
}
```

Ausente = pré-licitação, cascata livre, tela de hoje. `POST .../regime` declara
(`base_version` + `Idempotency-Key`). Três recusas com código estável:
`ESTIMATE_CASCADE_ORIGIN_FORBIDDEN` (instalação), `ESTIMATE_REGIME_CASCADE_DIRTY`
(declaração com fonte proibida instalada) e `ESTIMATE_REGIME_IRREVERSIBLE` (mão única).

## Scope

1. **Tipos e cliente** em `apps/web/src/orcamento/api.ts`: o bloco do regime no molde de
   `EstimateTargetState` (linha 115) dentro de `EstimateState` (linha 249), e a função da
   rota nova no molde da do teto (linha 639).
2. **Selo em DOIS lugares**, como o pacote decide: cabeçalho da rodada
   (`OrcamentoApp.tsx:1649-1701`) e painel da Cascata (`OrcamentoApp.tsx:1784+`). Um selo só
   no topo faria a recusa parecer arbitrária a quem está na aba.
3. **Declarar o regime**: ato próprio, no molde do painel do teto — não caixa de marcar
   escondida. A recusa de cascata suja aparece por extenso, e a tela diz que remover a fonte
   é o caminho.
4. **Candidato a aditivo**: na etapa de códigos (`OrcamentoApp.tsx:2119+`, lista em
   2144-2168), o item já listado como rejeitado passa a ler "candidato a aditivo" **quando a
   rodada está sob o regime**. É mudança de rótulo sobre dado que já existe —
   `labels.ts::assignmentStatusLabel` (linha 308) é o ponto.
5. **Rodada sem regime**: nenhuma peça nova. A tela de hoje, exatamente.
6. `etapas.ts` (`derivarEtapas`, 152-317; etapa `codigos` em 240-268) só muda se o resumo de
   uma etapa precisar citar o regime. A derivação espelha o estado lido e **nunca** substitui
   gate do servidor.

## Out of scope

- Qualquer arquivo em `services/` — o contrato vem pronto da T1.
- O bloco **reservado** do mock (tela 8): amarrar a rodada a um contrato real e conferir
  data-base/desconto. É a lacuna que o ADR-0045 nomeia e deixa aberta.
- Contador de candidatos no cabeçalho: é questão em aberto do pacote e o mock mostra o sinal
  **só na lista**. O número está publicado em `amendment_candidates`; usá-lo no cabeçalho
  seria decidir a questão, e não é sua.
- Botão de voltar para pré-licitação: o regime é mão única e o servidor recusa. Não ofereça
  o que não existe.

## Acceptance criteria

1. Rodada sem regime: tela idêntica à de hoje, provado por teste.
2. Sob o regime: selo no cabeçalho e no painel da Cascata; a cascata oferece só `sco`.
3. Declarar com cascata suja mostra a recusa por extenso, e a cascata não muda na tela.
4. Item rejeitado sob o regime lê "candidato a aditivo"; sem o regime, segue lendo o que lê
   hoje.
5. A tela corresponde à revisão 1 aprovada, conferida contra as capturas.
6. `npm --workspace @croquito/web run test` e `run check` verdes.

## Pitfalls

- Cor nunca é o único indicador: todo estado tem texto ao lado (regra do CSS da jornada).
- Não recalcule regra no navegador: `allowed_cascade_origins` vem do servidor justamente
  para a tela não guardar a própria cópia e descobrir a divergência numa recusa.
- A copy do mock é **proposta** — o registro de aprovação diz que texto não foi aprovado.
  Use a do mock e sinalize no relatório que segue pendente.

## Validation

```bash
npm --workspace @croquito/web run test
npm --workspace @croquito/web run check
```
