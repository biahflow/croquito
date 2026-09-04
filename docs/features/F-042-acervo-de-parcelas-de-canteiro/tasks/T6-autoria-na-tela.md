# F-042 T6 — A autoria de acervo na tela (estado 09 do pacote)

- **feature_id**: F-042
- **task_id**: T6
- **role**: builder
- **depends_on**: [T2 (a rota de autoria), T5 (a leitura da matriz gravada)]
- **required_capabilities**: READ, WRITE (`apps/web/src/orcamento`), VALIDATE
- **risk**: MÉDIO — `OrcamentoApp.tsx` vivo; a rota já existia e não muda.
- **relative_effort**: M
- **validation**: `BROWSER_REQUIRED` — é `INTERFACE_CHANGE` e o estado 09 precisa ser lido
  renderizado, não só descrito.

## O que existia e o que faltava

A rota **já existia sem consumidor** desde a T2:
`POST /v1/estimate-rounds/{round_id}/site-setup/kits` (`author_estimate_site_setup_kit`).
Ela grava um acervo DO TENANT a partir das contribuições `STANDALONE` da revisão corrente, e é
o Human Gate 4 da feature exercido pela API — o primeiro acervo é autorado por gente.

O que faltava era o caminho da orçamentista até ela: o **estado 09** do
[pacote de design aprovado](../mock/README.md) (revisão 2, 2026-08-28).

## Contrato de API (não muda nesta task)

```text
POST .../site-setup/kits   (Idempotency-Key + base_version)
 corpo: {"base_version": int, "name": str(3..200), "kit_version": str(1..40),
         "parameter_bindings": {"<índice>.<operando>": "<parâmetro>"}}
 201  → SiteSetupKitResponse (kit_id, name, kit_version, origin, source_label,
                              parcel_count, document_sha256, available, created_by,
                              created_at, withdrawn_at)
 409 ROUND_STAGE_NOT_READY | 422 SITE_SETUP_KIT_EMPTY
 422 SITE_SETUP_BINDING_INVALID (details.bindings) | 409 SITE_SETUP_KIT_ALREADY_PUBLISHED
 409 REVISION_CONFLICT
```

A rodada **não muda**: nenhuma revisão nasce e o contador dela não avança.

## Scope

1. **Transporte** (`api.ts` + `requests.ts`): `postAuthorSiteSetupKit`, no molde das vizinhas —
   `Idempotency-Key` do transporte, `base_version` no corpo, decimal irrelevante aqui porque a
   autoria não leva número nenhum.
2. **Módulo puro** (`acervoAutoria.ts`): a enumeração das parcelas `STANDALONE` da matriz
   **gravada** na ordem do servidor (espelho de `standalone_contributions`), o estado do
   formulário, a derivação da lista de parâmetros e o corpo do pedido.
3. **Tela** (`OrcamentoApp.tsx`): `FormularioDeAutoriaDeAcervo`, fiel ao estado 09, e o ato
   "Guardar como acervo" no painel de canteiro.
4. **Testes**: módulo puro, transporte, classificação da recusa e componente.
5. **Evidência de navegador**: o estado 09 real, em `evidencia/`.

## Fora de escopo

- `kit_id` em `SiteSetupOrigin` (dívida declarada; exige emenda ao ADR-0060).
- Deduções na pré-visualização (dívida declarada).
- Autoria de acervo **de plataforma** — é ato do operador, por outra rota.
- Qualquer mudança na API.

## As três decisões que esta task tomou

**1. O índice do binding sai da matriz GRAVADA, lida no ato de abrir.** `parameter_bindings`
cita `"<índice da parcela standalone>.<nome do operando>"`, e esse índice é a posição na
enumeração do **servidor**. O rascunho da tela pode ter parcela ainda não montada, e um índice
deslocado ligaria o parâmetro ao operando errado — o acervo nascendo errado sem ninguém ver.
A tela lê matriz e `base_version` na **mesma** resposta de `GET .../calc-matrix` e grava contra
ela: rodada que andar no meio devolve `409`, não um acervo torto.

**2. A declaração por operando é adição consciente ao pacote.** O estado 09 desenha o aviso
("Confira o que virou parâmetro") e a **lista resultante**, mas não o gesto de declarar. Sem
ele não há o que conferir, e a rota recusa adivinhar — `1 × 2` pode ser "uma unidade por dois
meses" ou "duas placas de um metro", e todo operando não citado vira constante. A declaração
foi posta exatamente onde o aviso aponta, com o campo nascendo vazio (decisão 4 do pacote) e
"em branco" significando "fica constante".

**3. Só acervo do próprio tenant ganha versão nova.** A rota grava sempre um acervo do tenant;
"versionar" um de plataforma criaria um homônimo — bifurcação com aparência de continuação, e
a fronteira do ADR-0060 existe para não borrar isso.

## Desvio de escopo registrado

A evidência de navegador achou uma **tela em branco** vinda da T5 (`kit_origin: null` do fio
desreferenciado na hidratação). Ela derrubava a etapa de códigos em qualquer rodada com
contribuição autorada à mão na matriz gravada, e era o bloqueio direto desta evidência.
Corrigida aqui, com regressão. Ver [`plan.md`](../plan.md) e [`evidence.md`](../evidence.md).

## Acceptance criteria

1. O estado 09 renderiza fiel ao pacote: dois painéis, contagem por origem, aviso âmbar,
   lista de parâmetros com o selo "novo" e os dois controles.
2. Acervo novo e versão nova produzem o corpo correto, com os bindings declarados.
3. A recusa do servidor aparece por extenso, e a de binding marca os campos que ela nomeia.
4. O sucesso diz nome, versão e contagem, e a lista de acervos é relida.
5. Nada nasce pré-marcado, e nenhum número vira parâmetro sem alguém o nomear.

## Comandos de verificação

```bash
npm --workspace @croquito/web run test
make check
make test
```
