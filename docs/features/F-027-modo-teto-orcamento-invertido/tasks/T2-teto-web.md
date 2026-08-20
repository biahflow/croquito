# T2 — Web: teto, consumo e estouro na jornada do orçamento

Task Contract derivado do [plano válido](../plan.md). Autossuficiente: assuma o Core,
este contrato, o [Design Approval Package aprovado (rev. 1)](../mock/README.md) —
composição vinculante, texto é rascunho — o
[ADR-0040](../../../adr/0040-teto-de-verba-do-orcamento-base.md) e o repositório.

## Identity

```text
feature_id: F-027
task_id: T2
parent_plan: docs/features/F-027-modo-teto-orcamento-invertido/plan.md
depends_on: [T1]
```

## Goal

As seis telas do mock aprovado, na jornada do orçamento: declarar o teto na abertura,
editar no painel da etapa BDI, consumo em três estados, estouro como aviso permanente
em âmbar SEM botão — e o conserto declarado do defeito de legibilidade que o mock
expôs.

## Baseline

T1 integrado na branch; `make check`, `make test` e
`npm --workspace @croquito/web run test` verdes.

## Scope

Em `apps/web/src/orcamento/` (o payload é o que T1 publicou — leia o diff dele):

- `api.ts`: campos opcionais de criação; `postTarget(accessToken, roundId,
  baseVersion, targetAmount, targetLabel?)`; tipos do bloco derivado
  `{target, consumed, remaining, over}`.
- `OrcamentoApp.tsx`:
  - abertura: dois campos opcionais (valor + demanda), vazio = caminho normal sem
    aviso; `0,00` recusado NA TELA com a frase do mock ("zero não é 'sem teto'") e
    botão indisponível — mesmo desenho de recusa local que o BDI já usa;
  - painel "Teto da verba" na etapa BDI/montagem (ao lado do BDI), sempre presente
    em rodada aberta — vazio quando sem teto (recusa mais barata do caderno,
    escrita no mock);
  - bloco de consumo DENTRO da "Prévia do orçamento", colado ao Total geral: dentro
    do teto (verde, % e restante), limite exato (mesmo estado, palavra dizendo "não
    é estouro"), estourado (âmbar);
  - faixa "TETO ESTOURADO" de largura inteira, âmbar, SEM NENHUM botão, presente em
    TODA etapa da rodada enquanto `over` — com quanto passou em valor e %, e as
    três frases do mock (nada recusado; nenhuma linha removida; pedir verba é
    caminho legítimo);
  - linha do teto na lista de orçamentos SÓ em rodada com teto;
  - **conserto declarado** (achado do mock, defeito pré-existente da F-020):
    metadados da lista "Orçamentos do tenant" (`OrcamentoApp.tsx:1125-1144`) trocam
    `.topbar-meta` por `.dica` — uma linha, registrada no BUILD REPORT.
- `labels.ts`/`errors.ts`: `ESTIMATE_TARGET_INVALID` + frases do bloco (rascunho do
  mock).
- `styles.css` do diretório: composições novas do mock (faixa, bloco de consumo)
  sobre tokens existentes — NENHUMA cor nova (o âmbar já existe na folha).
- Testes vitest: três estados do bloco; recusa de zero na tela; faixa presente em
  etapa ≠ BDI quando `over`; rodada sem teto sem bloco nem linha na lista.

## Out of scope

- `medicao/`, croqui, backend, copy definitiva, remoção de teto, qualquer outro
  ajuste visual além do conserto declarado.

## Acceptance criteria

1. `make check` e `npm --workspace @croquito/web run test` verdes.
2. Bloco de estouro sem nenhum botão; limite exato sem cor própria, dito por
   extenso.
3. Rodada sem teto idêntica a hoje (teste prova).
4. Nenhuma cor nova (diff prova).

## Validation

```bash
make check
npm --workspace @croquito/web run test
```

## Required capabilities

READ, WRITE, VALIDATE. Sem COMMIT: deixe o diff na árvore.

## Report

`BUILD REPORT` completo em
docs/features/F-027-modo-teto-orcamento-invertido/tasks/T2-build-report.md.
