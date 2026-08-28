# F-042 T3 — A tela: escolher acervo, declarar parâmetros, pré-visualizar, aplicar

- **feature_id**: F-042
- **task_id**: T3
- **role**: builder
- **depends_on**: [T1, T2 (contrato de API, fixado abaixo)]
- **required_capabilities**: READ, WRITE (`apps/web/src/orcamento`), VALIDATE
- **risk**: MÉDIO-ALTO — `OrcamentoApp.tsx` é arquivo vivo e enorme.
- **relative_effort**: L

## O gate de design está cumprido

O **Design Approval Package revisão 1 foi aprovado por ato humano em 2026-08-28** (Daniel
Campos). Ele é a especificação visual desta task e **não é negociável durante a
implementação**:

- rendição: `docs/features/F-042-acervo-de-parcelas-de-canteiro/mock/acervo-de-parcelas-de-canteiro.html`
- registro, decisões, proveniência e o que ficou aberto: `mock/README.md`

Os arquivos do pacote **não estão nesta branch** (vivem em `docs/f042-f044-design-approval`).
Abra-os a partir de `/Users/danielcampos/workspace/daniel/croquito-daps/docs/features/F-042-acervo-de-parcelas-de-canteiro/mock/`
— leitura apenas, jamais edite nada lá.

As nove decisões do pacote valem como requisito. As que mais moldam o código:

1. painel próprio na etapa **Códigos**, irmão da lista de elementos — não aba, não tela nova;
2. **três passos obrigatórios** (acervo → parâmetros → prévia). **Não existe caminho que
   aplique sem passar pela prévia**;
3. a prévia mostra a **conta** (operandos nomeados), não só a quantidade;
4. parâmetro nasce **vazio**, nunca inferido nem pré-preenchido;
5. recusa de parâmetro faltante nomeia **todos** e nada é aplicado;
6. remoção é por parcela, a removida fica **visível e riscada**, e é reversível até aplicar;
7. parcela do acervo carrega selo de origem distinguindo **por texto** ("do acervo v1" x
   "autorada à mão"), nunca só por cor;
8. reaplicar substitui as do mesmo acervo e nunca toca as autoradas à mão;
9. código ausente do catálogo é recusa por extenso, nomeando o código.

## Contrato de API (fixado — a T2 implementa exatamente isto)

A T2 roda em paralelo, em outra worktree. **Programe contra este contrato**; se a T2 divergir,
a correção é dela, não sua.

```
GET  /v1/estimate-rounds/{id}/site-setup-kits
  → {"round_id","version","kits":[{"kit_id","name","kit_version","origin":"platform"|"tenant",
       "source_label","parcel_count",
       "parameters":[{"name","unit":string|null,"cited_by":number}],"created_at"}]}

POST /v1/estimate-rounds/{id}/site-setup/preview      (não avança versão, não grava)
  body {"kit_id","parameters":{"<nome>":"<decimal string>"},"excluded_parcel_ids":[...]}
  → {"round_id","version","kit_id","kit_version",
     "rows":[{"parcel_id","code","label",
              "operands":[{"name","value":"<decimal string>","unit":string|null}],
              "quantity":"<decimal string>"}],
     "excluded_parcel_ids":[...]}

POST /v1/estimate-rounds/{id}/site-setup/apply        (ato humano, avança versão)
  body {"base_version","kit_id","parameters","excluded_parcel_ids"}  + Idempotency-Key
  → a revisão nova, no mesmo formato que a jornada já usa depois de um ato
```

Recusas chegam em `application/problem+json` com os códigos estáveis:

- `SITE_SETUP_PARAMETER_MISSING` — `details.parameters` é a lista **de todos** os faltantes;
- `SITE_SETUP_CODE_ABSENT` — `details.codes` é a lista dos códigos ausentes;
- `SITE_SETUP_UNKNOWN_PARCEL`, `SITE_SETUP_OPERAND_*`, mais os já existentes da jornada
  (`REVISION_CONFLICT` etc.).

Todo decimal atravessa a fronteira **como string**. Não converta para `number` para
armazenar, exibir ou reenviar — só para formatar.

## Scope

1. **`apps/web/src/orcamento/api.ts` + `requests.ts`**: as três chamadas acima, no padrão dos
   vizinhos (token, `base_version`, `Idempotency-Key`, tratamento de `problem+json`).
2. **`apps/web/src/orcamento/acervo.ts` (novo)**: módulo puro com os tipos espelho e a lógica
   de tela — estado dos três passos, exclusões, e o que habilita avançar. Puro e testável,
   no molde de `matrix.ts`. **Nenhum cálculo de quantidade acontece aqui**: a quantidade vem
   do servidor, que a computa pelo mesmo caminho da matriz. Reimplementar a conta no
   navegador criaria uma segunda aritmética.
3. **`apps/web/src/orcamento/errors.ts`**: as recusas novas, com texto que **nomeia** o que
   falta (parâmetros, códigos), no padrão do arquivo.
4. **`OrcamentoApp.tsx`**: o painel "Parcelas de canteiro" na etapa `codigos`, o fluxo dos
   três passos, a prévia com remoção individual, o selo de origem na matriz e a reaplicação.
   Encoste no que já existe: o estado `contribuicoes`
   (`Record<string, CalcContributionDraft>`), `assembleCalcMatrix`, e o bloco de autoria de
   contribuição. Preserve o comportamento atual de quem não usa acervo.
5. **`apps/web/src/orcamento/styles.css`**: a família `--acervo*` do pacote de design
   (azul-ardósia `#3a5f8f`, soft `#eef3fa`, line `#b9cde6`, ink `#24405f`). Respeite as
   regras da folha (`apps/web/src/styles.css:13-22`): `--accent` só em preenchimento, verde
   como texto é `--accent-text`, `--muted` nunca é texto pequeno vivo.
6. **Testes** em `acervo.test.ts` (lógica pura) e em `OrcamentoApp.test.tsx` (integração da
   etapa), no padrão dos existentes. Cobrir: os três passos; não há caminho que pule a
   prévia; a recusa que nomeia todos os parâmetros; a recusa de código; remoção que não
   altera as demais e é reversível; o selo de origem distinguindo por texto.

## Out of Scope

- **A autoria de acervo** (estado 09 do pacote de design): fica para a T4. Nesta task o botão
  **não existe** — o pacote proíbe desenhar controle inerte.
- `services/`, `packages/` e migrações.
- Qualquer estado que o pacote de design marcou como **não incluído** (acervo vazio, recusa
  de autoria): eles dependem de questão aberta e **não podem ser resolvidos por um agente**.
  Se a lista de acervos vier vazia, mostre a etapa como está hoje, sem inventar frase nova —
  e reporte isso como pendência.

## Acceptance Criteria

1. Não existe caminho na tela que aplique o acervo sem passar pela pré-visualização.
2. A prévia mostra os operandos nomeados de cada parcela, não só a quantidade.
3. Os campos de parâmetro nascem vazios e trazem a unidade e o "citado por N parcelas".
4. A recusa de parâmetro faltante nomeia **todos** os faltantes; a de código nomeia o código.
5. Parcela removida aparece riscada e volta com um clique; remover uma não altera as demais.
6. Origem da parcela é distinguível **sem cor** (texto no selo).
7. `npm --workspace @croquito/web run test` e o build passam; nenhuma regressão nos testes
   existentes de `OrcamentoApp.test.tsx`.

## Validation

```bash
cd /Users/danielcampos/workspace/daniel/croquito-f042-web
npm --workspace @croquito/web run test
make check
make test
```

## Armadilhas verificadas

- `matrix.ts` é espelho **à mão** do domínio Python e **não** é contrato gerado
  (`matrix.ts:16-17`). Se você acrescentar o campo de proveniência ao espelho, ele precisa
  casar com `CalcContribution.kit_origin` (`{kit_version, parcel_id}`), que é **opcional**.
- `assembleCalcMatrix` devolve `null` quando não há contribuição nenhuma — é o regime legado,
  e não pode quebrar.
- Edições são operations allowlisted com `base_version`; a tela não resolve geometria nem
  decide consenso.
- Cor nunca é o único indicador de precisão ou de estado; warning crítico nunca é escondido.
- Documentação e mensagens de domínio em **português**; identificadores em inglês.
- `make check` valida todo link relativo de Markdown do repositório, inclusive deste arquivo.
