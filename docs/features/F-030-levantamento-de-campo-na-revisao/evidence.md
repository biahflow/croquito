# F-030 — Evidência de execução

Estado: `DONE` — **aceita por ato humano em 2026-09-05**; integrada na `main` desde
2026-08-25 pelo [PR #29](https://github.com/biahflow/croquito/pull/29).

Review Evidence Package da F-030 (levantamento de campo na revisão do escritório). Fontes
primárias: os BUILD REPORTs de cada task em [`tasks/`](tasks/), os commits da branch
`feat/f-030-t5-t7` e os logs de portões da sessão.

> **Nota de 2026-09-05**: o texto abaixo foi escrito na sessão de execução e dizia "branch
> local, sem push". A integração aconteceu logo depois (PR #29, 2026-08-25, inclusive o
> ADR-0051 e a retenção por classe no Terraform), mas este documento e o roadmap não foram
> atualizados — a auditoria do fecho recuperou a corrente de commits pelos SHAs dos BUILD
> REPORTs e conferiu, arquivo a arquivo, que tudo está na `main`. As seções ao fim registram
> a evidência de navegador, a revisão e o aceite.

## Contexto de execução

- ADR-0049 e o Design Approval Package revisão 3 aceitos por ato humano em 2026-08-23 são
  premissa, não escolha das tasks. Ordem contratada `T1 → T2 → (T3, T4, T6) → (T5, T7) → T8`.
- Nenhum provider pago foi ligado nesta rodada. As fontes de IA continuam desligadas
  (`CROQUITO_REAL_PROVIDERS_ENABLED=false`); onde a classificação é exercida, o artefato em
  `DRAFT` é injetado offline, sem chamada de rede.
- Branch local `feat/f-030-t5-t7`, **sem push**. O rollout em HML é ato humano posterior.

## BASELINE

`make check` verde (até `infra-check`, ver nota) e `make test` verde antes das edições de T5.
Falha preexistente conhecida: `terraform fmt -check` não roda porque o binário `terraform`
não está instalado no ambiente — nenhuma task da F-030 toca `infra/`. Skips esperados:
`tests/api/test_migrations.py` exige `CROQUITO_TEST_POSTGRES_URL` (PostgreSQL real).

## Execução por task

| Task | Entrega | Commit | Report |
|---|---|---|---|
| T1 | vínculo job↔levantamento e `GET /field-evidence` | `618d24f` | [T1](tasks/T1-build-report.md) |
| T2 | foto avulsa (presign/confirm) e leitura sob demanda | `769394a` | [T2](tasks/T2-build-report.md) |
| T3 | painel de evidência de campo na web | `c46de85` | [T3](tasks/T3-build-report.md) |
| T4 | testemunhas no servidor (duas fontes, diferença neutra) | `bce14ab` | [T4](tasks/T4-build-report.md) |
| T6 | classificação por IA sob demanda + eval com gate | `12491f1`, `5fe0dc7` | [T6](tasks/T6-build-report.md) |
| T5 | testemunhas empilhadas na revisão web (dois atos do legado) | `4753e01` | [T5](tasks/T5-build-report.md) |
| T7 | observação humana sobre a classificação, fora da cena | `b39a118` | [T7](tasks/T7-build-report.md) |
| T8 | e2e da jornada; rollout pendente de atos humanos | (nesta entrega) | [T8](tasks/T8-build-report.md) |

## Portões locais (T5, T7, T8 desta sessão)

- `npm --workspace @croquito/web run test` — 1134 passed; `run build` — exit 0.
- `make check` — ruff, mypy strict (257 fontes, cache limpo), `check_docs`, drift de
  contratos e build web/field verdes; para apenas no `terraform fmt` ausente.
- `make test` — suíte completa verde (pytest + vitest); o e2e novo
  `test_field_evidence_e_observacao_coexistem_com_a_exportacao` incluído.
- Snapshot OpenAPI regenerado para a rota nova de T7; `test_openapi_contract` verde.
- Revisão adversarial da diff de T5/T7: nenhum defeito de correção.

## Invariantes provados

- Testemunha nunca vira cota: a diferença é número neutro, sem `status`/`agrees`/alerta; nada
  promove precisão (T4, T5 e o e2e).
- Associação é ato humano explícito; nenhum caminho a infere de âncora, `kind`, proximidade
  ou valor.
- Observação sobre a classificação viaja em `field_observations_json`, **fora da
  `SceneRevision`**: registrar, corrigir ou descartar não muda cena, digest, blockers, solver
  nem exportação (T7 e o e2e, que aprova e exporta com testemunhas divergentes na cena).

## Rollout — pendente de atos humanos (não executado)

O escopo de rollout de T8 depende de sistemas externos e human gates e **não foi executado**
nesta sessão:

1. Rodada real paga única (seis fotos rotuladas fora do Git, teto US$ 5,00) com o candidato
   T6 — depende do corpus humano e da autorização de gasto. O gate offline e a eval
   determinística de T6 já existem.
2. Infra em `biahflow/infra`: retenção por prefixo preservando `surveys/` e
   `jobs/*/field-evidence/`, branch/PR, `terraform plan` revisado e apply em HML.
3. Push único da `main`, acompanhamento do `deploy-hml` e smoke autenticado em HML.
4. Marcação de `READY_FOR_HUMAN_REVIEW`/`DONE` no roadmap, STATUS e Feature Contract —
   depende de 1–3 e do aceite humano posterior.

Enquanto esses passos não ocorrem, a F-030 permanece **code-complete com rollout pendente**;
nenhum estado de conclusão foi fabricado.

## Evidência de navegador (2026-09-05)

`INTERFACE_CHANGE` com Design Approval Package revisão 3 — a evidência renderizada não
existia, e foi produzida pela bancada delegada pelo dono (Chromium/Playwright, sessão OIDC
real como `engenheiro.local`, banco próprio `croquito_f030`, floci e worker reais, providers
**desligados** — nenhuma chamada paga). A semeadura espelhou o e2e da T8 pelo caminho de
produção: upload do PDF sintético → worker → `seed_review` do bundle amarrado por digest →
três cotas confirmadas → levantamento COMPLETED → foto avulsa por presign/PUT/confirm →
leitura de máquina PROCESSED injetada offline → valor confirmado. Capturas em
`output/f030-fecho/` (retenção local de 7 dias):

1. **O painel "Evidência de campo"**: a foto avulsa com a âncora declarada ("Muro dos
   fundos, junto ao portão"), o filtro por âncora com a frase de que ele não associa nada, o
   **valor confirmado em foto** (25,85 m, "confirmado aqui, associado lá") e a **proposta da
   IA a confirmar** com o lineage por extenso (prompt, schema, provider, modelo).
2. **O vínculo do levantamento pela tela**: "Levantamento vinculado · 1 foto".
3. **As duas testemunhas empilhadas** na cota confirmada de 25,90 — visor fotografado
   25,85 (diferença 0,05) e trena em campo 25,93 (diferença 0,03) — com a copy do pacote
   palavra por palavra: "a diferença é informação neutra […] não confirma a leitura, não
   bloqueia a exportação e não escolhe um valor vencedor". Nenhum estado de
   concordância/alerta, como a decisão de tolerância de 2026-08-23 exige.
4. **A observação humana sobre a classificação** registrada pela tela ("Confirmo: é muro,
   não alambrado") e o estado ativo com "Corrigir observação".

Prova no banco: a revisão corrente carrega **2 testemunhas** (`photo_reading` +
`survey_measurement`) e **1 observação `ACTIVE`** — e o e2e da T8 já provava que nada disso
move a cena nem os blockers.

## Revisão (2026-09-05)

Focada sobre o código integrado: `FieldWitnessResponse` não tem campo de status/concordância
— a diferença é subtração pura, com identidade e relógio do servidor; as fontes são um
`Literal` fechado com `survey_id` obrigatório na medida do app; a associação é ato humano
explícito (nenhum caminho a infere); e a suíte completa (incluindo
`test_review_field_witnesses.py`, `test_review_field_observations.py`,
`test_field_evidence.py` e o e2e) está verde na `main` corrente. **`REVIEW_PASS`**.

## O aceite (2026-09-05)

**Aceita por ato humano em 2026-09-05** (Daniel Campos, pelo chat), com as dívidas
declaradas: a **rodada paga única de classificação** (corpus humano de 6 fotos rotuladas +
autorização ≤ US$ 5), o **apply do Terraform** da retenção por classe (ADR-0051 aceito e
código na `main`; o apply é gate humano) e a **fumaça em HML** (ambiente derrubado por
decisão do dono). São os gates 1–3 que a própria T8 listou; o gate 4 — este documento, o
roadmap e o aceite — fecha aqui.
