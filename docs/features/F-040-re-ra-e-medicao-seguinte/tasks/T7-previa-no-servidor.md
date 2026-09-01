# F-040 · T7 — A prévia é do servidor, não do cliente

Feature: [F-040](../feature.md) · Plano: [plan.md](../plan.md) · Estado: **Entregue**

## Por que esta tarefa existe

Ela não nasce de requisito novo nem de defeito do implementador. Nasce de uma **decisão de
orquestração errada na T6**: o handoff daquela tarefa mandou calcular a prévia da RE-RA **no
cliente**. O implementador entregou o que foi pedido, com aritmética exata em texto sobre
`BigInt`, e sinalizou a tensão honestamente — a T6 registrou a coisa como “exceção declarada à
regra”.

A regra, porém, não admite exceção declarada por quem implementa nem por quem orquestra. Ela
está escrita no [AGENTS.md do web](../../../../apps/web/AGENTS.md), na seção de regras da
jornada de medição, e é **regra de produto**:

> A tela **nunca** soma, multiplica ou arredonda dinheiro/quantidade: exibe as strings
> decimais que o servidor mandou (`format.ts` só troca pontuação, e é testado nisso).

O critério de aceite VAL-07 a cita. Instrução de projeto não é enfraquecida por decisão de
orquestração: `AGENTS.md` de subdiretório acrescenta regras e nunca as enfraquece, e nenhum
spec de tarefa está acima disso.

E a regra não é cerimônia. Para projetar no navegador, a T6 precisou **rederivar por fora duas
grandezas que nenhuma leitura expunha**:

| Grandeza | Como a T6 a obtinha | Por que isso é duplicação de domínio |
| --- | --- | --- |
| acumulado da rodada `n+1` | `vigente − saldo` do read-model, mais o medido do período | é a definição de `ContractWorkbook.current_balance_quantity` reescrita em TypeScript |
| medido no período que fechou | soma das linhas de **todas as obras** de `GET /bulletin` | é o que `_origin_from_previous_round` faz no servidor, reescrito no cliente |

Duas implementações da mesma conta, em duas linguagens, sem nada acusando quando uma delas
mudasse. O par de testes que a T6 montou (`previa.test.ts` ↔ o teste de API) protegia os
**números do caso sintético**, não a identidade das contas: bastava um caso que o par não
cobrisse para a tela mostrar um número plausível e errado.

## Objetivo

Mover o cálculo da prévia — e o da herança da rodada anterior — para o servidor, **mantendo a
mesma tela** que o [pacote de design aprovado](../mock/README.md) desenhou: contratado → efeito
declarado → vigente → saldo novo, código a código, antes de gravar.

## Escopo

- `services/api/src/croquito_api/main.py`: a rota `POST /v1/valuation-round-previews`, os
  modelos de entrada e saída, e a **separação** de `_resolve_valuation_origin` em
  `_contracted_valuation_origin` (as duas portas contratadas) e `_apply_declared_acts`
  (reajuste e RE-RA sobre o consolidado). A criação da rodada continua chamando as mesmas duas.
- `apps/web/src/medicao/api.ts` e `requests.ts`: `previewRound` e `roundPreviewBody`.
- `apps/web/src/medicao/previa.ts`: perde a aritmética; passa a decidir **o que perguntar,
  quando perguntar e o que exibir**.
- `apps/web/src/medicao/MedicaoApp.tsx`: os dois componentes passam a receber a resposta do
  servidor, com estados de carregamento e de indisponibilidade.
- `docs/architecture/API_CONTRACT.md` e o snapshot de OpenAPI (aditivo).
- Testes: `tests/api/test_valuation_round_preview.py` (novo), `previa.test.ts`,
  `MedicaoApp.test.tsx`, `api.test.ts`, `requests.test.ts`.

## O que faz a prévia não poder divergir da criação

Não é disciplina: é estrutura. As duas partem das **mesmas duas funções**.

```text
POST /v1/valuation-rounds          POST /v1/valuation-round-previews
        │                                       │
        ├── _contracted_valuation_origin ───────┤   (as duas portas contratadas)
        ├── _apply_declared_acts ───────────────┤   (reajuste + RE-RA, na ordem declarada)
        │                                       │
   grava a rodada                        lê e devolve; nada é gravado
```

`test_a_previa_devolve_os_mesmos_numeros_da_rodada_criada` manda o mesmo corpo para as duas
rotas e compara linha a linha. Se um dia alguém duplicar o caminho, é ali que aparece.

## Fora de escopo

- Mudar o que a **criação** da rodada faz. Ela não muda: a refatoração é de extração, e os
  testes que já existiam continuam passando sem alteração.
- O reajuste na porta da medição seguinte (superfície da F-039).
- O `declared_by` legível — hoje sai o `sub` do JWT; dívida conhecida, registrada em
  [evidence.md](../evidence.md).
- Recaptura das telas (`BROWSER_REQUIRED`), que é a tarefa seguinte.

## Critérios de aceite

1. Existe rota de prévia, **somente leitura**: sem `Idempotency-Key`, sem `base_version`, sem
   revisão nova e sem tocar `contract_workbook_json`.
2. A prévia e a rodada realmente criada devolvem **os mesmos números** para a mesma entrada,
   provado por teste.
3. Item novo aparece com descrição, unidade e preço **materializados do catálogo contratual**;
   código ausente do catálogo devolve a **mesma recusa** que a criação
   (`AMENDMENT_NEW_ITEM_CODE_MISSING`, `CATALOG_REQUIRED`), e não um erro genérico.
4. `tenant_id` sempre do JWT; erro em `application/problem+json` com código estável; snapshot de
   OpenAPI **aditivo**.
5. `grep -rn "BigInt\|reduce(" apps/web/src/medicao/previa.ts` não devolve aritmética de
   quantidade; `format.ts` continua só trocando pontuação.
6. A tela continua idêntica ao pacote aprovado — inclusive a coluna “Vigente hoje” que a T6
   acrescentou por correção, agora vinda do servidor.
7. Estados de carregamento e de erro existem e são legíveis; prévia indisponível **não** impede
   declarar — ela informa, e a tela diz que não conseguiu projetar.

## Validação

`uv run pytest tests/api tests/valuation`, `npm --workspace @croquito/web run test`,
`make check` e `make test` verdes.
