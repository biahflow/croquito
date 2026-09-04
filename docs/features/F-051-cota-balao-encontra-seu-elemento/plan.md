# F-051 — Plano de implementação

Gates cumpridos em 2026-09-04, ambos por ato humano (Daniel Campos):
[ADR-0063](../../adr/0063-identidade-de-elemento-nasce-na-revisao.md) **aceito** e
[Design Approval Package](mock/README.md) revisão 1 **aprovado**, com duas leituras
confirmadas no mesmo ato: **rótulo de elemento único por job na revisão**, e **revogação que
não desfaz associação já confirmada**.

## A ordem é ditada pelo ato — e o merge acontece no ato

Duas descobertas de código dimensionam este plano (verificadas em 2026-09-04, com linhas):

1. **As candidatas de associação são persistidas, e a API nunca recomputa.** O
   `AssociationSet` nasce no worker (`associate_readings`, chamado só por
   `provider_review.py:855`, `cli.py:1073-1084` e `review_refresh.py:165`) e vive em
   `associations_json`; o portão `_apply_association_rules` (`main.py:6611-6652`) valida
   contra o que está persistido. Logo a candidata por identidade **nasce e morre no ato**
   (declarar/revogar/renomear/corrigir hint), por função pura chamada pelas próprias rotas de
   mutação — sem rota de recompute nova e sem tocar o ranking de proximidade.
2. **O molde da F-047 T6 não é reaproveitável 1:1.** `propose_element_groups`
   (`croquito_core/element_proposals.py:187`) opera sobre `SceneRevision` — pós-solve. A
   sugestão assistida da revisão precisa de um produtor novo, sobre `VisionProposalSet` — que
   já carrega o rótulo do modelo (`vision.py:114`, `label: str | None`).

Por isso o ato (T2) vem primeiro e sozinho no caminho crítico: sugestão (T3), candidata (T4)
e transporte (T5) são todos consumidores dele. O hint (T1) é a única tarefa sem dependência —
e sem consumidor até a T4, com o controle de sempre: pacote existente valida sem mudança de
comportamento. A tela (T6) vem depois das três APIs; a evidência de navegador e o caso real
fecham (T7).

## Tarefas

| # | Tarefa | Depende de | Esforço |
|---|---|---|---|
| T1 | [O hint estruturado sobrevive até a leitura](tasks/T1-o-hint-estruturado.md) | — | M |
| T2 | [O ato de declarar elemento na revisão](tasks/T2-o-ato-de-declarar-na-revisao.md) | — | L |
| T3 | [As sugestões assistidas da revisão](tasks/T3-sugestoes-da-revisao.md) | T2 | M |
| T4 | [A candidata por identidade, cunhada no ato](tasks/T4-candidata-por-identidade.md) | T1, T2 | M |
| T5 | [O traçado transporta a identidade](tasks/T5-transporte-no-tracado.md) | T2 | M |
| T6 | [A tela da revisão](tasks/T6-tela-da-revisao.md) | T2, T3, T4 | L |
| T7 | [Evidência de navegador e o caso real](tasks/T7-evidencia-e-o-caso-real.md) | T5, T6 | S |

Ordem: `(T1 ∥ T2) → (T3 ∥ T5) → T4 → T6 → T7`.

- **Paralelismo genuíno**: T1 ∥ T2 (pacote no worker × ato na API) e T3 ∥ T5 (produtor+rotas ×
  `tracing.py`).
- **PARALLELISM_RISK registrado**: T1, T2, T3 e T4 tocam `main.py` (o monólito de rotas). T1
  toca só os modelos de comando de decisão (`:1073`, `:1106`, `:8948`, `:9199`); T2/T3/T4
  acrescentam rotas e merge. Regiões distintas, arquivo único: se executarem em paralelo, em
  worktrees separadas, o rebase é de vizinhança; a resolução recomendada é o mesmo builder
  para T3 → T4, na ordem.
- **Caminho crítico**: `T2 → T3 → T4 → T6 → T7` (L + M + M + L + S) — T3 antes de T4 pela
  resolução do risco acima, não por dependência lógica.

## O que atravessa todas as tarefas

- **Sem declaração e sem hint casando, tudo responde como hoje.** É critério de aceite de
  cada tarefa, não só do controle: pacote existente valida (T1), rotas novas não mudam as
  velhas (T2/T3), `associations_json` sem elemento declarado sai byte a byte igual (T4),
  cena sem proposta identificada é a de hoje (T5), tela sem feature é a tela de hoje (T6).
- **Candidata é observação**: `unresolved`/`export=false`, ranqueia e nunca confirma. O
  portão único (`_apply_association_rules`) não muda em tarefa nenhuma.
- **`element_ref` nunca digitado, nunca inferido, nunca reaproveitado** (ADR-0058/0063);
  namespace único por job — colisão é defeito, não caso.
- **Rótulo único por job na revisão** e **revogação que não desfaz associação confirmada** —
  as duas leituras confirmadas no aceite do DAP são critérios da T2.
- **Casamento exato, nunca fuzzy silencioso**: a normalização mínima é decidida na T4 com o
  dado do job de referência e fica **declarada** (constante nomeada + teste), não implícita.
- **Toda tarefa de API atualiza o trio de superfície**: `tests/api/openapi.snapshot.json`,
  `docs/architecture/API_CONTRACT.md` e os tipos manuais de `apps/web/src/api.ts` (não há
  drift check para eles — a disciplina é do contrato da tarefa).

## Validação do plano

`PLAN_VALID` — IDs únicos, dependências existentes, DAG acíclico, critérios e validação por
tarefa, paralelismo classificado (um risco registrado com resolução), caminho crítico e
integração declarados. Desvios após o congelamento entram como `PLAN_DEVIATION` aqui.

### Desvios registrados

- **`PLAN_DEVIATION` (T2 → T6, 2026-09-04).** Planejado: a T6 consumiria os tipos das
  APIs novas. Executado: a T2 preservou `GET /review` **byte a byte** (critério 6) e por
  isso não expôs as declarações na leitura — elas saem inteiras só nas respostas dos três
  atos. Impacto: quem carrega a tela do zero não tem por onde ler as identidades
  declaradas. Resolução: a **T6 ganha como escopo explícito a superfície de leitura**
  (rota `GET` própria ou campo aditivo na resposta existente — decisão lá, honrando o
  teste de controle da T2). **Decidido na T6 (2026-09-04): rota `GET` própria**,
  `GET /v1/jobs/{job_id}/review/elements`, com a mesma forma de `declarations` dos três
  atos e as revogadas incluídas. O campo aditivo foi recusado porque mudaria a resposta que
  o critério 6 da T2 congelou byte a byte; a rota nova não toca nela.

## Achados de planejamento

1. **Unknown 2 do contrato, resolvido**: a `ElementDeclaration` persiste como coluna JSON
   aditiva em `ReviewRevisionRecord` (`database.py:595-685`), herdada por
   `_carried_review_context` (`main.py:5883-5895`, usado em 9 montagens de revisão), com
   migração própria. `insert_review_revision_v1` (`review_store.py:88-221`) é a semente do
   worker — as rotas da API constroem o registro diretamente; a coluna nova entra nos dois.
2. **Namespace único**: `_next_element_ref` (`main.py:5772-5803`) deriva o próximo ref
   varrendo só `RevisionRecord.scene`; a T2 o estende para varrer também as declarações da
   revisão do mesmo job. A guarda continua sendo a concorrência otimista de cada lado.
3. **`relation` é `Literal` fechado** (`association.py:32-50`, dois valores) — a T4 o estende
   com `element_identity`; `AssociationSet.associator_version` é `Literal` de valor único
   (`pixel-proximity-associator-v1`) e **não muda**: a procedência da candidata por identidade
   é da própria candidata, não do associador de proximidade.
4. **Os dois achatadores**: `provider_review.py:777-780` (tolera hint ausente) e
   `transcription.py:474` (que **descarta** leitura sem hint em `:431-439` — regra própria,
   preservada). A T1 estrutura o rótulo nos dois caminhos.
5. **Corrigir o hint já é ato previsto**: o comando de decisão aceita e grava `target_hint`
   (`main.py:1073`, `:1106`, `:8948`, `:9199`); a T1 acrescenta o campo estruturado ao mesmo
   comando, e a T4 faz o ato de correção recunhar as candidatas da leitura.
6. **Risco nomeado do transporte**: `ELEMENT_REF_LAYER_MISMATCH` — o invariante "camada única
   por ref" (`models.py:329-345`) pode morder quando propostas de um mesmo elemento declarado
   virarem entidades em camadas distintas no traçado. A T5 o trata como caso de teste, não
   como surpresa.
7. **Contratos**: `ReviewPacket`/`AssociationSet` estão **fora** do manifesto de
   `make contracts` (7 entradas; `scene.schema.json` não muda nesta feature). O versionamento
   é o `ReviewPacket.schema_version` (`review.py:222`, `1.1.0` → `1.2.0` na T1).
8. `ARCHITECTURE_DECISION_REQUIRED`: nenhum — o ADR-0063 cobre as decisões desta feature.
   `DESIGN_APPROVAL_REQUIRED`: cumprido (revisão 1 aprovada em 2026-09-04).

## Integração

Este plano e os contratos de tarefa entram na branch do aceite (PR #158). A execução usa
branch e worktree próprias por tarefa a partir da `main`, não empilhadas (lição registrada
nos planos da F-039/F-040/F-047); T1 muda o `ReviewPacket`, então todo PR roda `make check`
completo (o drift check dos contratos gerados fica verde por não haver mudança de scene — se
ficar vermelho, algo saiu do escopo).

## Human gates

- ADR-0063 e Design Approval: **cumpridos** em 2026-09-04.
- Merge de cada PR: ato humano (portão de sempre).
- **Gate 3 da feature**: aceite final contra o caso real do Toca (critério 1 — o `C = 56,00`
  com hint "B" entrando no solver como constraint), exercido pelo dono sobre a T7.
