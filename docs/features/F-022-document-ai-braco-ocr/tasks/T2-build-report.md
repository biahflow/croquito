# T2 — Build Report

Relatório do Builder para a task `F-022-T2`, no formato exigido pelo
[contrato do Builder](../../../engineering-os/agents/builder.md).

```text
BUILD REPORT

Status: BUILD_COMPLETE

Files changed:
  - docs/ai/MODEL_ROUTING.md
    Linha do header e tabela de rotas (OCR auxiliar) passam a citar o braço `ocr` montável
    como Cloud Vision (default) ou Document AI por `CROQUITO_DOCAI_PROCESSOR`, com pointer ao
    ADR-0037; parágrafo de `providers_json` e "Estado de implementação local" (85-99)
    descrevem a escolha por configuração, autenticação por ADC comum aos dois, e registram
    explicitamente que nenhum processador está provisionado até esta revisão; seção de
    falhas (linha ~138) passa a citar os dois fornecedores possíveis e o campo `provider` do
    log de falha que T1 introduziu.
  - docs/operations/HML.md
    Header e seção "Providers de IA" (259-294) passam a descrever o braço `ocr` como
    Cloud Vision hoje / Document AI por configuração; bloco novo lista os dois atos de infra
    pendentes (habilitar `documentai.googleapis.com` + provisionar processador em
    `biahflow/infra`; definir `CROQUITO_DOCAI_PROCESSOR` no serviço) como PENDENTES, sem
    afirmar que existem.
  - docs/operations/RUNBOOK_PROCESSING_FAILURES.md
    Seção "Textract failure" (28-32) substituída por "Falha do braço OCR", descrevendo o
    comportamento real: `OCR_UNAVAILABLE` (braço ausente/falha permanente),
    `READING_{n}_OCR_EVIDENCE_MISSING` por leitura, `BUDGET_EXCEEDED` propagando, e os dois
    vendors possíveis (Cloud Vision hoje, Document AI por config — ADR-0037).
  - docs/security/AI_VENDOR_RISK.md
    Tabela de fornecedores (7-13) passa a listar Anthropic, OpenAI e Google Cloud
    Vision/Document AI (a suite real); AWS Bedrock/Textract saem da tabela ativa para uma nota
    de histórico apontando ADR-0002/ADR-0035. Data de revisão atualizada.
  - docs/security/PRIVACY_LGPD.md
    Lista de suboperadores (52-56) passa a refletir a suite real (Anthropic direto, OpenAI
    direto, Google Cloud Vision/Document AI) com AWS restrito a S3/RDS; nota de histórico
    qualifica Textract/Bedrock como desenho do ADR-0002 nunca exercido pela suite hospedada
    (ADR-0035). Nenhuma cláusula contratual nova foi inventada — só a lista de fornecedores
    de fato integrados. Data de revisão atualizada.
  - AGENTS.md
    Linha 90: "Textract ajuda a localizar e transcrever, mas não determina geometria." vira
    "O OCR auxiliar corrobora leitura e transcrição, mas não determina geometria." (regra sem
    vendor fixo). Data de revisão do documento atualizada.
  - docs/STATUS.md
    Linha 93 (bloco "Adapters reais locais"): frase nova registra que o braço `ocr` ganhou um
    segundo adapter real (Document AI, ADR-0037) sem alterar as afirmações já existentes sobre
    Bedrock/Textract, e deixa explícito que nenhum processador está provisionado. Linha 762
    ("Textract como OCR auxiliar", em "Decisões aceitas") vira a descrição real — Cloud Vision
    por padrão, Document AI por configuração — apontando ADR-0035 D3 e ADR-0037, ambos citados
    como `Proposed`.

Validation executed:
  BASELINE (antes desta task, com os diffs de F-021 T1+T2 e F-022 T1 na árvore):
    - `git status` confirmou os 14 arquivos modificados/untracked pré-existentes preservados
      integralmente antes de qualquer edição (apps/web/*, docs/adr/README.md,
      docs/ai/PROMPT_CONTRACTS.md, docs/architecture/API_CONTRACT.md, docs/product/FDD.md,
      docs/product/ROADMAP.md, services/worker/src/croquito_worker/{provider_review,
      providers,review}.py, tests/api/openapi.snapshot.json, tests/worker/test_providers.py,
      docs/adr/0037-*, docs/features/F-021-*, docs/features/F-022-*).
  FINAL (depois desta task):
    - `make check` → exit 0: ruff check/format (376 arquivos formatados), mypy strict
      (187 arquivos, sem issues), `scripts/check_docs.py` ("212 arquivos Markdown, paridade de
      lifecycle verificada" — inclui todos os links relativos novos desta task), drift de
      contratos (schema_export --check-dir e contracts:check), `web:check` (tsc -b + vite
      build), `infra-check` (terraform fmt -check).
  Nenhuma falha preexistente encontrada; nenhuma falha nova introduzida.

Validation skipped: none

Unavailable capabilities: none
  (READ, WRITE e VALIDATE exercidos; COMMIT não foi solicitado — o diff fica na árvore, como
  o contrato manda.)

Assumptions:
  - "Última revisão" no header de cada doc tocado foi atualizada para 2026-08-20 com uma nota
    curta do que mudou, seguindo o padrão já usado nos outros documentos do repositório
    (ex.: MODEL_ROUTING.md, HML.md antes desta task).
  - docs/STATUS.md linha 969 (narrativa da F-009 sobre "ocr (Cloud Vision...)") e o header
    geral do documento (linhas 5-9) são registro histórico de uma revisão anterior — fora das
    linhas explicitamente escopadas (89-93, 762) — e não foram tocados.

Remaining risks:
  - Nenhum processador Document AI existe hoje; toda a documentação nova descreve capacidade
    condicional (`CROQUITO_DOCAI_PROCESSOR`), nunca estado ativo — mas a revisão humana deve
    confirmar que a leitura corrente não sugere o contrário em nenhum trecho.
  - O eval comparativo pago entre Cloud Vision e Document AI (mencionado como gate de
    promoção no ADR-0037) não rodou; nenhum documento novo afirma o contrário.
  - ADR-0035 e ADR-0037 continuam `Proposed` — os textos novos citam essas ADRs sem afirmar
    aceitação, mas descrevem comportamento de código já mergeado (T1); a aceitação formal das
    ADRs segue como ato humano separado.

Human decisions required:
  - Aceite do ADR-0037 (hoje `Proposed`) — já registrado como pendência em T1, reafirmado
    aqui.
  - Provisionamento do processador Document AI no GCP e definição de
    `CROQUITO_DOCAI_PROCESSOR` em HML — ato de infraestrutura/deploy fora do código,
    detalhado no bloco novo de docs/operations/HML.md.
  - Eval comparativo pago (chamada paga em massa) antes de promover o braço Document AI.
```

## Desvios conscientes do contrato

1. **`docs/STATUS.md` linha 93 recebeu frase nova em vez de reescrever a frase existente.**
   O contrato pede "corrija só onde o texto afirma presente"; a frase original sobre
   Bedrock/Textract ("permanecem desligados por padrão e não foram chamados neste
   repositório") continua verdadeira e não fala de OCR/GCP — não havia nada de falso ali para
   corrigir. Acrescentei uma frase nova, factual e com pointer a ADR-0035/ADR-0037, em vez de
   reescrever a existente, para não tocar uma afirmação que já estava correta.
2. **`docs/STATUS.md` linha 969 (narrativa da F-009 sobre o braço `ocr`) não foi tocada.**
   Está fora das linhas 89-93/762 explicitamente escopadas pelo contrato e é registro
   histórico de uma revisão anterior do documento — mesma lógica de "seções de época NÃO são
   reescritas" aplicada por analogia, mesmo não estando dentro de uma seção nomeada "época".
3. **AGENTS.md e RUNBOOK_PROCESSING_FAILURES.md tiveram o header "Última revisão" atualizado**
   além da frase citada no contrato, porque o critério de aceite 3 ("Datas de 'última revisão'
   atualizadas onde o documento as carrega") se aplica a todo documento tocado, não só aos
   citados explicitamente na Scope com número de linha.

## Oportunidades vistas e NÃO implementadas (fora de escopo)

- `docs/STATUS.md` linhas 5-9 (header geral) e 962-975 (narrativa completa da F-009) não
  mencionam Document AI/F-022 — atualizar o resumo executivo do topo do documento para citar
  F-022 é uma decisão editorial maior que o "corrija só onde afirma presente" deste contrato
  autoriza; deixo para uma task de STATUS.md dedicada, se o usuário quiser.
- `docs/product/ROADMAP.md` linhas 89/93 e 116/118/244/373 (menções a Textract) são
  explicitamente fora de escopo (registro de época) — não tocadas.
- ADR-0002 e ADR-0004 são imutáveis por contrato — não tocados.
- Nenhuma mudança de código, teste ou Makefile foi feita — fora de escopo desta task.
