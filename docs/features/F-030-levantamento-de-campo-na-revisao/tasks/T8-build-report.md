# T8 — BUILD REPORT

Relatório do Builder para o [Task Contract T8](T8-e2e-e-rollout.md) da
[F-030](../feature.md). Executado na branch `feat/f-030-t5-t7`, sem push.

```text
BUILD REPORT

Status: BUILD_COMPLETE (parte local/e2e) — ROLLOUT_PENDING_HUMAN_GATES

Files changed:
  - tests/e2e/test_full_flow.py
    Novo e2e test_field_evidence_e_observacao_coexistem_com_a_exportacao: a jornada leva uma
    cota confirmada a receber duas testemunhas com diferença NEUTRA (survey_measurement +
    photo_reading, +0,03 m e -0,05 m), uma observação humana sobre a classificação por IA
    (fora da cena, com source/lineage copiados do artefato), e prova que a cena não muda
    (id/versão/blockers idênticos) e que aprovação + exportação seguem fechando o pacote
    auditado apesar da divergência. Usa as rotas reais (/field-evidence, /review/witnesses,
    /review/field-observations, /values, /approve, /exports); o único provider é offline.

Validation executed:
  - pytest tests/e2e/test_full_flow.py ............ exit 0 (9 passed, o novo e2e incluído)
  - make check ................................... green até infra-check (ruff, mypy strict
    257 fontes com cache limpo, check_docs, drift de contratos, build web/field). O passo
    `terraform fmt -check` não roda: binário terraform ausente no ambiente.
  - make test (suíte completa) ................... rodada final registrada abaixo.
  - npm --workspace @croquito/web run test ....... exit 0 (1134 passed)

Validation skipped:
  - terraform fmt / plan / apply — binário ausente no ambiente e, além disso, o apply em HML
    é human gate (revisão do plano do repo externo antes do apply).
  - test_migrations.py em PostgreSQL real — exige CROQUITO_TEST_POSTGRES_URL; skip esperado
    no SQLite local, como nas demais tasks.

Unavailable capabilities:
  - terraform CLI; PostgreSQL de teste; repo externo biahflow/infra; GitHub Actions/HML;
    consentimento de gasto e o corpus humano de seis fotos rotuladas.

Human gates / rollout NÃO executados (exigem ato humano ou sistema externo):
  1. Rodada real paga única (6 fotos rotuladas fora do Git, teto US$ 5) com o candidato T6.
     Depende do corpus humano e da autorização de gasto — AC2 não pode ser satisfeito por
     agente. O gate offline e a eval determinística de T6 já existem.
  2. Infra em biahflow/infra: retenção por prefixo preservando surveys/ e
     jobs/*/field-evidence/, branch/PR, terraform plan revisado e apply em HML (AC3/AC4).
  3. Push único da main, acompanhamento do deploy-hml e smoke autenticado em HML (AC5/AC6).
  4. evidence.md/roadmap/STATUS/Feature Contract em READY_FOR_HUMAN_REVIEW e o aceite humano
     de DONE — dependem de 1–3.

Assumptions:
  - A divergência das testemunhas e a observação são observacionais: nenhuma entra em
    blockers, e o e2e prova a invariância da cena e a exportação bem-sucedida — a leitura
    literal de "exportação permanece possível" do escopo.
  - As fontes pagas continuam desligadas; o e2e injeta o artefato de classificação em DRAFT,
    sem chamar provider, no mesmo molde dos testes de T6/T7.

Remaining risks:
  - Publicar após um gate pago falho, misturar SHAs no HML ou marcar DONE sem aceite humano
    — todos fora do que foi executado aqui, e listados como gates acima.

Human decisions required:
  - Fornecer o corpus de seis fotos/rótulos e autorizar a rodada paga (≤ US$ 5).
  - Revisar o terraform plan do repo externo antes do apply em HML.
  - Aceitar DONE após a entrega em HML.
```
