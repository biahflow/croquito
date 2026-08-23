# F-030 — Plano de execução

feature_id: F-030  
goal: a evidência de campo — foto e medida — chega à revisão do escritório, pelas duas portas
(levantamento vinculado e upload avulso do legado), e a medida vira **testemunha** da cota da
prancha sem nunca virar cota.

assumptions:
- O [ADR-0049](../../adr/0049-evidencia-de-campo-na-revisao-do-escritorio.md) foi aceito e o
  Design Approval Package está aprovado na **revisão 3**, ambos por ato humano em 2026-08-23.
  As dezesseis decisões do ADR são premissa deste plano, não escolha das tasks.
- **A evidência de campo sai numa rota própria, não dentro de `ReviewResponse`.** Aquele
  modelo já é grande e volta em toda mutação da revisão; pendurar fotos nele faria cada
  decisão de leitura pagar o custo de um bloco que ela não usa. `GET /v1/jobs/{id}/field-evidence`.
- **A testemunha é persistida na revisão de leitura, no molde de `declared_chains`** (F-023):
  observacional, com `base_review_version`, fora de `blockers`. É o precedente exato — uma
  declaração humana que acompanha a leitura sem entrar na cena — e reusá-lo evita inventar um
  terceiro lugar para guardar observação.
- A ancoragem da foto **avulsa** é declarada pelo revisor: não houve técnico para ancorá-la, e
  o produto não a infere.

risks:
- **A testemunha ser tomada por cota.** É o risco central da feature: dois números na mesma
  tela, e o de baixo é da trena. Mitigação: a origem viaja escrita ao lado de cada número, e
  a T4 entrega teste negativo de que nada promove precisão.
- **Divergência falsa por associação errada** treina o revisor a ignorar o aviso, que é pior
  que não ter aviso. Mitigação: a associação é ato humano explícito (ADR-0049, decisão 5), com
  teste negativo de que nenhum caminho a infere.
- **Custo pago disparado sem intenção.** Mitigação: a fatia 3 nunca dispara pelo vínculo, e a
  primeira rodada paga é ato humano separado.
- `main.py` e `CroquiApp.tsx` são arquivos grandes e vivos. Mitigação: a rota nova entra num
  lugar só, e a tela ganha componentes exportados e testáveis, no molde da T3 da F-036.

## Decisão de tolerância

O ADR-0049 decisão 7 diz que, **sem calibração, o produto mostra a diferença sem classificá-la**.
O pacote de design aprovado, no estado 6, mostra a divergência com a veste de alerta — o que
exige classificar.

Decisão humana de 2026-08-23: nenhuma tolerância será inventada nesta feature. A T4 declara o
mecanismo por `kind`, mas não escreve limiar. A T5 mostra os dois valores e a diferença sem
estado de concordância, discordância ou alerta até existir calibração com dado real.

tasks:
  - id: T1
    role: builder
    goal: o vínculo job ↔ levantamento e a evidência legível pelo escritório
    scope: migração `0017` com a tabela de vínculo (muitos-para-muitos, com autor e data);
      rotas de vincular, desvincular e ler; `GET /v1/jobs/{id}/field-evidence` servindo fotos
      com URL assinada (só `CONFIRMED`), a análise já gravada e as medidas `confirmed`;
      snapshot de OpenAPI; testes de API.
    out_of_scope: `apps/web`; upload avulso (T2); testemunha (T4); qualquer chamada paga.
    depends_on: []
    validation: make check, make test, tests/api/test_migrations.py com PostgreSQL real
    relative_effort: L

  - id: T2
    role: builder
    goal: foto avulsa na revisão, que é a porta do levantamento legado
    scope: presign e confirm no molde do upload de prancha, com âncora declarada pelo revisor;
      a foto avulsa entra na mesma resposta da T1, com a mesma composição; leitura textual
      avulsa reutiliza `FIELD_PHOTO_READING` somente quando alguém pede.
    out_of_scope: `apps/web`; PDF como evidência (recusado no contrato); chamada automática.
    depends_on: [T1]
    validation: make check, make test
    relative_effort: M

  - id: T3
    role: builder
    goal: a evidência de campo na tela da revisão
    scope: `apps/web/src/` — painel "Evidência de campo" com fotos ancoradas, qualidade,
      leitura, o ato de vincular e o de subir avulsa, modal com abertura do original, filtro
      manual por âncora e os estados de vazio, carregando, sem análise, recusa e sem papel,
      correspondendo à **revisão 3** aprovada.
    out_of_scope: `services/`; a testemunha (T5); decidir autorização no navegador.
    depends_on: [T2]
    validation: npm --workspace @croquito/web run test, make check
    relative_effort: L

  - id: T4
    role: builder
    goal: a testemunha da cota no servidor
    scope: associação explícita leitura ↔ valor medido, persistida na revisão de leitura no
      molde de `declared_chains`; as duas fontes (medida `confirmed` do app; valor lido em
      foto, que exige confirmação humana do valor ANTES de poder ser associado); a diferença
      calculada na leitura; várias testemunhas; tolerância nomeada por `kind` sem valor;
      testes negativos de que nada
      promove precisão e de que nenhum caminho infere associação.
    out_of_scope: `apps/web`; entrar em `blockers`; qualquer promoção de precisão.
    depends_on: [T2]
    relative_effort: L
    validation: make check, make test

  - id: T5
    role: builder
    goal: a testemunha ao lado da cota, na tela
    scope: o confronto dos dois valores com a origem de cada um, a diferença, o caminho do
      legado (confirmar o valor lido, depois associar), testemunhas empilhadas e diferença
      neutra, correspondendo à revisão 3.
    out_of_scope: `services/`.
    depends_on: [T3, T4]
    relative_effort: M
    validation: npm --workspace @croquito/web run test, make check

  - id: T6
    role: builder
    goal: a classificação por IA, sob demanda
    scope: `PromptTask` própria, adapter e comando de fila no worker; contrato de prompt, rota
      no Model Routing e eval com gate; teto de custo e lineage por proposta; a rota que pede
      a classificação, nunca automática.
    out_of_scope: `apps/web`; rodar a primeira chamada paga, que é ato humano separado.
    depends_on: [T2]
    relative_effort: L
    validation: make check, make test, eval com gate declarado

  - id: T7
    role: builder
    goal: a proposta da IA na tela, e o ato que a registra
    scope: rota de observação versionada fora da cena; bloco de rascunho com lineage e o ato
      que grava ou descarta a conclusão em `field_observations_json`, correspondendo ao
      estado 8.
    out_of_scope: `SceneRevision`, `Issue`, blockers e endpoint antigo de nota da cena.
    depends_on: [T6, T3]
    relative_effort: M
    validation: npm --workspace @croquito/web run test, make check

  - id: T8
    role: builder
    goal: e2e da evidência de campo na revisão
    scope: `tests/e2e/` — levantamento vinculado a um job, foto e medida legíveis pelo
      escritório, testemunha associada, e a prova de que a divergência **não** impede a
      exportação.
    out_of_scope: mudar comportamento entregue por T1–T7.
    depends_on: [T5, T7]
    relative_effort: M
    validation: make test

parallel_groups: T3, T4 e T6 depois de T2; T5 depende de T3+T4 e T7 de T3+T6.
critical_path: T1 → T2 → T3/T4/T6 → T5/T7 → T8.
integration_strategy: commits separados por task na `main`, com revisão linha a linha entre
  elas; nenhuma task encerra com portão vermelho.
human_gates: ADR-0049 e Design Approval Package revisão 3 aceitos; tolerância decidida como
  não classificada. A rodada paga foi autorizada até US$ 5,00, mas só roda depois do gate
  offline e do recebimento das seis fotos rotuladas. A migração `0017` no hospedado e o apply
  da retenção continuam atos de rollout.

## Nota de processo

A F-036 executou T2, T3 e T4 **sem Task Contract próprio**, apenas com o plano. A convenção
([docs/features/README.md](../README.md)) exige um por task desde a F-007, e o lapso é meu.
Aqui cada task ganha o seu antes de ser executada, em `tasks/`.
