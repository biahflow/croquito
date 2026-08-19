# T5 — BUILD REPORT

> Este relatório incorpora a emenda ao contrato da T5, decidida com o usuário em
> 2026-08-19: os VALORES das duas chaves (OpenAI, Anthropic) entram pela esteira do
> repo irmão (GitHub Actions secret → `TF_VAR_*` → `secret_data_wo` write-only), não
> mais por `gcloud secrets versions add` manual. A versão anterior deste relatório
> (BUILD_COMPLETE do contrato original, sem a emenda) foi substituída por esta.

```text
BUILD REPORT

Status: BUILD_COMPLETE
Files changed:
  - /Users/danielcampos/workspace/daniel/croquito/.github/workflows/deploy-hml.yml
    (não commitado) — bloco da API: acrescenta CROQUITO_REAL_PROVIDERS_ENABLED=true
    a --set-env-vars (linha ~151). Bloco do worker: acrescenta
    CROQUITO_OPENAI_API_KEY e CROQUITO_ANTHROPIC_API_KEY a --set-secrets (linha
    ~181), e CROQUITO_REAL_PROVIDERS_ENABLED=true, CROQUITO_AI_MAX_ESTIMATED_COST_USD=5.00,
    CROQUITO_OPENAI_MODEL=gpt-5.6-terra, CROQUITO_ANTHROPIC_MODEL=claude-opus-5,
    CROQUITO_AI_EXTRACTION_ALLOWED_DIGESTS= (vazio) a --set-env-vars (linha ~182);
    comentário novo acima do passo "Publica o worker" explicando o kill switch
    (flag=false desliga) e o teto por invocação (reentrega do Pub/Sub multiplica).
    Não tocado pela emenda.

  - /Users/danielcampos/workspace/daniel/infra/envs/hml/croquito/main.tf
    (repo irmão, branch feat/croquito-hml-providers, NÃO commitado — diff fica na
    árvore de trabalho para o humano revisar/commitar) —
      1. resource "google_project_service" "vision" habilitando
         vision.googleapis.com, com disable_on_destroy = false e comentário
         registrando que não existia padrão local de google_project_service neste
         repositório (grep vazio antes desta mudança) — ver "Desvios conscientes".
         Não tocado pela emenda.
      2. lifecycle_rule { condition { age = 7 } action { type = "Delete" } } no
         google_storage_bucket.artifacts — a regra de expiração de 7 dias
         prometida em docs/security/DATA_RETENTION.md do croquito não existia no
         bucket croquito-hml-artifacts. Não tocado pela emenda.
      3. Dois secrets novos no mapa module.secrets.secrets:
         "croquito-hml-openai-api-key" e "croquito-hml-anthropic-api-key", cada
         um com acessores = [google_service_account.worker.email] (só a SA do
         worker). ALTERADO pela emenda: o comentário foi reescrito (não são mais
         casca-com-ato-manual; explica a origem write-only pela esteira) e o
         bloco module.secrets ganhou valores_wo/valores_wo_versions ligando os
         dois secrets a var.openai_api_key/var.anthropic_api_key e
         var.providers_api_key_version.

  - /Users/danielcampos/workspace/daniel/infra/envs/hml/croquito/variables.tf
    (repo irmão, mesma branch, NÃO commitado) — NOVO por esta emenda:
    variable "openai_api_key" e variable "anthropic_api_key" (string, sensitive,
    SEM default — plan/apply falham fail-closed se TF_VAR_openai_api_key /
    TF_VAR_anthropic_api_key não existirem); variable "providers_api_key_version"
    (number, default = 1) como gatilho de rotação write-only compartilhado pelas
    duas chaves.

  - /Users/danielcampos/workspace/daniel/infra/modules/secret-manager/main.tf
    (repo irmão, mesma branch, NÃO commitado) — NOVO por esta emenda, mudança
    ADITIVA: local com_valor_wo; resource
    google_secret_manager_secret_version.corrente_wo usando secret_data_wo +
    secret_data_wo_version (mesma troca segura de "corrente": create_before_destroy
    + deletion_policy=DISABLE), for_each em local.com_valor_wo. Nenhum recurso
    existente foi alterado.

  - /Users/danielcampos/workspace/daniel/infra/modules/secret-manager/variables.tf
    (repo irmão, mesma branch, NÃO commitado) — NOVO por esta emenda: variable
    "valores_wo" (map(string), sensitive, default {}) com duas validations —
    toda chave precisa existir em var.secrets, e nenhuma chave pode estar
    simultaneamente em var.valores e var.valores_wo (setintersection == 0);
    variable "valores_wo_versions" (map(number), default {}) com validation
    exigindo entrada correspondente para toda chave em var.valores_wo. var.valores
    existente não foi tocado.

  - /Users/danielcampos/workspace/daniel/infra/modules/secret-manager/README.md
    (repo irmão, mesma branch, NÃO commitado) — atualizado por esta emenda: a
    seção "O valor fica no state" e a tabela de "Divisão de propriedade" agora
    documentam valores_wo/valores_wo_versions como caminho implementado (o texto
    anterior dizia "este módulo não o expõe... quando precisar, é acréscimo
    aditivo" — ficou desatualizado no instante em que a emenda implementou
    exatamente esse acréscimo; corrigido para não deixar código e doc do próprio
    módulo divergentes). Acrescentado exemplo de uso e nota sobre exigência de
    Terraform >= 1.11 para write-only.

  - /Users/danielcampos/workspace/daniel/infra/.github/workflows/plan.yml
    (repo irmão, mesma branch, NÃO commitado) — NOVO por esta emenda:
    TF_VAR_openai_api_key e TF_VAR_anthropic_api_key acrescentados ao env: do
    job `plan` (nível de job, não por-stack — mesmo padrão exato de
    NEON_API_KEY, que também está nesse nível porque o job roda em matriz e o
    env extra é inócuo para os stacks que não declaram essas variáveis).

  - /Users/danielcampos/workspace/daniel/infra/.github/workflows/apply.yml
    (repo irmão, mesma branch, NÃO commitado) — NOVO por esta emenda:
    TF_VAR_openai_api_key e TF_VAR_anthropic_api_key acrescentados ao env: do
    job `hml_croquito` (apply.yml tem um job por stack, ao contrário de
    plan.yml; mesmo padrão de NEON_API_KEY nesse mesmo job).

  - /Users/danielcampos/workspace/daniel/croquito/docs/features/F-009-suite-hospedada-sem-aws/tasks/T5-build-report.md
    (este arquivo) — reescrito para refletir a emenda.

Validation executed:
  full: make check (repo croquito) — reprovou em uv run ruff check . (F821, 9
    erros) e em uv run mypy (1 erro), ambos 100% dentro de arquivos fora do
    escopo desta task e não tocados por ela: tests/worker/test_providers.py,
    services/worker/src/croquito_worker/providers.py,
    services/worker/src/croquito_worker/provider_review.py,
    services/worker/src/croquito_worker/local_queue.py,
    services/api/src/croquito_api/main.py. `git diff --stat` confirma que
    nenhum desses arquivos foi alterado por este build (só
    .github/workflows/deploy-hml.yml no meu diff do repo croquito); esses cinco
    arquivos estavam modificados e não commitados na árvore ANTES desta
    execução — trabalho da task T1 em paralelo no mesmo working tree, confirmado
    pela instrução de lançamento ("T1 roda em paralelo nesses arquivos").
    `make check` interrompe no primeiro alvo que falha (ruff check), então os
    alvos seguintes do Makefile nunca rodaram sob o `make check` completo; para
    não deixar a validação sem sinal, executei os componentes individuais
    manualmente e todos passaram:
      - uv run ruff format --check . → "344 files already formatted" (exit 0)
      - uv run mypy [...] → 1 erro, em tests/worker/test_providers.py:683
        (fora de escopo, mesma área de T1)
      - uv run python scripts/check_docs.py → verde (182 arquivos Markdown após
        a reescrita deste relatório, paridade de lifecycle verificada)
      - uv run python -m croquito_core.schema_export --check-dir
        packages/contracts → exit 0, sem drift
      - npm run contracts:check → exit 0
      - npm run web:check (tsc -b && vite build) → build limpo, exit 0
      - make infra-check (terraform fmt -check -recursive infra/ local) → exit
        0, nada a formatar (infra/ local, dentro do repo croquito, não foi
        tocado — é diretório diferente do repo irmão)
    Nenhum desses componentes tem relação com deploy-hml.yml nem com o repo
    irmão; a única falha real de `make check` (ruff+mypy) está inteiramente em
    território de T1. Não reexecutado após a emenda porque a emenda só tocou o
    repo irmão.

  infra (contrato original + emenda, repo irmão):
    - terraform -chdir=envs/hml/croquito fmt -check -diff → saída vazia (exit 0)
    - terraform fmt -check -recursive -diff (repositório infra inteiro, para
      cobrir também modules/secret-manager/ e confirmar que a emenda não
      desalinhou nada em outro stack) → saída vazia (exit 0)
    - terraform -chdir=envs/hml/croquito init -backend=false -input=false → após
      remover .terraform/ local (diretório de trabalho gerado, listado em
      .gitignore, continha estado de backend GCS obsoleto que fazia o init com
      -backend=false tentar reconciliar contra o bucket remoto e falhar por
      oauth2/reauth) → "Terraform has been successfully initialized!"
    - terraform -chdir=envs/hml/croquito validate → "Success! The configuration
      is valid." — validate passa mesmo SEM TF_VAR_openai_api_key/
      TF_VAR_anthropic_api_key no ambiente (variável sem default só é exigida em
      plan/apply, não em validate); nenhum valor de segredo foi necessário para
      este portão.
    - modules/secret-manager validado isoladamente (init -backend=false +
      validate, provider google 6.50.0 igual ao lock do stack) → "Success! The
      configuration is valid." — confirma que google_secret_manager_secret_version
      aceita secret_data_wo/secret_data_wo_version nessa versão do provider
      (schema válido, não é suposição).
    - terraform fmt (module e stack) rodado antes do fmt -check para corrigir
      alinhamento de `=` no bloco novo de corrente_wo; fmt -check ficou limpo
      depois.

  paridade da esteira (sem execução, leitura): plan.yml e apply.yml validados
  como YAML sintaticamente correto (`yaml.safe_load`); TF_VAR_openai_api_key /
  TF_VAR_anthropic_api_key adicionados no mesmo job e no mesmo nível que
  NEON_API_KEY em cada um dos dois workflows, por leitura comparada linha a
  linha — não executei o workflow (não há runner local para Actions neste
  ambiente).

  grep de segredo/token no diff dos dois repos: `git diff | grep -iE
  "sk-[a-zA-Z0-9]{10,}|AKIA[0-9A-Z]{10,}|-----BEGIN|ghp_[a-zA-Z0-9]|xox[baprs]-"`
  — sem ocorrências em nenhum dos dois repositórios, incluindo depois da
  emenda; só nomes de secret, nomes de variável Terraform e nomes de GitHub
  Actions secret (CROQUITO_OPENAI_API_KEY, CROQUITO_ANTHROPIC_API_KEY) aparecem
  no diff — nunca um valor.

  git diff --stat (repo irmão, pós-emenda): 7 arquivos —
  .github/workflows/apply.yml (+6), .github/workflows/plan.yml (+6),
  envs/hml/croquito/main.tf (+66/-0), envs/hml/croquito/variables.tf (+32),
  modules/secret-manager/README.md (+49/-14 linhas reescritas),
  modules/secret-manager/main.tf (+29), modules/secret-manager/variables.tf
  (+54). Nenhum outro stack (envs/hml/wif, envs/hml/servicos, envs/hml/rede,
  envs/hml/eliseu-demo, envs/hml/croquito-edge, envs/global/dns, envs/prd/wif)
  nem modules/cloud-run-service, modules/github-wif foram tocados.

Validation skipped: none

Unavailable capabilities: none

Assumptions:
  - "a partir de main" no contrato original foi lido como origin/main atualizado
    (0577c68), não a branch local `fix/hml-schemas-separados` em que o repo
    irmão estava checked out no início desta task; a branch
    feat/croquito-hml-providers foi criada com `git checkout -b ... origin/main`.
  - Cloud Vision (document text detection) não exige role de IAM adicional além
    de a SA de runtime existir no projeto com a API habilitada — confirmado por
    ausência de doc contrária e por não haver binding de recurso equivalente ao
    de Storage/Secret Manager para essa API.
  - `CROQUITO_REAL_PROVIDERS_ENABLED=true` também no bloco da API (não só no
    worker) foi mantido como pedido no contrato original, confirmado por grep em
    services/api/src/croquito_api/config.py:83 e main.py:1172, que mostram a API
    lendo essa flag.
  - Emenda: "uma variável de versão com default 1 para o gatilho de rotação" foi
    lida como UMA variável COMPARTILHADA pelas duas chaves
    (providers_api_key_version), não duas variáveis independentes — decisão de
    design, não ambiguidade resolvida por acaso: rotacionar as duas chaves juntas
    é o caso comum (troca de fornecedor de secrets do GH, rotação de higiene), e
    a divisão em duas variáveis fica como acréscimo aditivo se algum dia for
    preciso rotacionar uma sem a outra.
  - Emenda: a variável de gatilho não tem `sensitive = true` (é só um inteiro de
    controle, não o segredo) — decisão consistente com o próprio design do
    módulo, que já trata secret_data_wo_version como não-sensível.
  - Emenda: mantive `var.valores_wo`/`var.valores_wo_versions` como parâmetros
    de nível de módulo (não escondidos atrás de uma variável estruturada única),
    espelhando a forma de `var.valores`/`var.secrets` já existente — não inventei
    um formato novo de configuração.

Remaining risks:
  - `make check` completo do repo croquito não pôde terminar verde nesta
    execução porque T1 está com edições não commitadas em andamento no mesmo
    working tree; não é risco introduzido por T5/pela emenda (a emenda nem
    tocou o repo croquito além deste relatório). Recomendo reexecutar
    `make check` completo depois que T1 concluir.
  - O bucket croquito-hml-artifacts guarda todos os artefatos do ambiente, não
    só respostas de provider; a lifecycle_rule de 7 dias vale para o bucket
    inteiro. Não alterado pela emenda; risco já registrado antes dela.
  - `google_project_service.vision` é o primeiro recurso desse tipo em todo o
    repositório biahflow/infra; um humano deve confirmar que é o padrão
    desejado. Não alterado pela emenda.
  - A emenda cria dependência de dois GitHub Actions secrets NOVOS no repo
    biahflow/infra (CROQUITO_OPENAI_API_KEY, CROQUITO_ANTHROPIC_API_KEY) que
    ainda NÃO existem — até serem criados, um `terraform plan` real do stack
    hml_croquito nesta branch falhará (variável sem default e sem valor
    fornecido). Isso é o comportamento fail-closed pretendido, não um defeito,
    mas é bloqueante para o primeiro plan/apply até o ato humano do item abaixo.
  - `var.valores_wo` grava o valor write-only "nesta" versão do secret; se
    alguém rodar `terraform plan/apply` sem que os dois GH secrets estejam
    setados, o Terraform vai tentar usar string vazia como valor (GitHub Actions
    resolve secret ausente para string vazia, não falha o job) — a variável
    Terraform em si não tem default e falharia primeiro por "variável não
    definida" SE ninguém a alimentar, mas como plan.yml/apply.yml sempre
    definem TF_VAR_* (mesmo que vazio, se o GH secret não existir), o Terraform
    veria um valor vazio válido em vez de erro. Ou seja: o fail-closed do lado
    Terraform (sem default) só protege contra "secret nunca foi setado no
    workflow"; não protege sozinho contra "GH secret existe mas está vazio". Um
    humano deve confirmar, ao criar os secrets, que o valor não fica vazio —
    registrado aqui porque não é óbvio à primeira leitura do design.
  - Módulo secret-manager ganhou dois blocos de validação novos
    (`valores`/`valores_wo` mutuamente exclusivos); como nenhum outro stack usa
    o módulo hoje (confirmado por grep), o risco de quebrar um consumidor
    existente é zero nesta janela — mas vale registrar para quando um segundo
    stack passar a consumir o módulo.
  - Nenhum `terraform plan` foi executado (proibido pelo contrato e pela
    emenda); o plano — incluindo a leitura de qualquer drift pré-existente —
    fica para o humano.

Human decisions required:
  - Criar os dois GitHub Actions secrets no repositório biahflow/infra:
    `gh secret set CROQUITO_OPENAI_API_KEY --repo biahflow/infra` e
    `gh secret set CROQUITO_ANTHROPIC_API_KEY --repo biahflow/infra` — ato
    humano que SUBSTITUI o `gcloud secrets versions add` manual do runbook
    original; nenhum comando `gcloud` de segredo é mais necessário para estas
    duas chaves.
  - Revisar e commitar o diff em /Users/danielcampos/workspace/daniel/infra
    (branch feat/croquito-hml-providers), depois abrir PR.
  - Rodar `terraform plan` (via PR, workflow plan.yml) e confirmar que os dois
    TF_VAR_* chegam com valor não vazio antes de mergear/aplicar.
  - `terraform apply` (via merge, workflow apply.yml) — fora deste contrato.
  - Confirmar que google_project_service.vision é o padrão aceito para futuras
    APIs no repositório, dado que não havia precedente.
  - Merge do PR em biahflow/croquito com a mudança em deploy-hml.yml — o merge
    é o próprio ato de deploy (ADR-0025/0031).
  - Reexecutar `make check` completo no repo croquito depois que a task T1
    terminar.
```
