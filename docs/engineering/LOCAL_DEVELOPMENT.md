# Desenvolvimento local

Status: Active  
Responsável: Engineering  
Última revisão: 2026-08-10

## Pré-requisitos

- Python 3.12 e `uv`.
- Node.js 24 e npm.
- Terraform 1.9 ou superior para validar `infra/`.
- AutoCAD ou viewer CAD somente para aprovação de domínio; não é necessário nos testes.

## Bootstrap e validação

```bash
make setup
make check
make test
```

`make check` executa Ruff, formatação, mypy strict, verificação de drift dos
contratos, build TypeScript e `terraform fmt`. A validação completa da
infraestrutura requer uma vez:

```bash
terraform -chdir=infra init -backend=false
terraform -chdir=infra validate
```

Nenhum desses comandos executa `terraform apply`.

## Vertical slice sintético

```bash
make demo
```

Arquivos em `output/demo`:

- `entrada-sintetica.png`: entrada controlada, sem dado de cliente.
- `scene.json`: revisão canônica aprovada.
- `desenho.dxf`: DXF R2018 com `$INSUNITS=6`.
- `preview.png`: render produzido após reabrir o DXF.
- `auditoria.json`: checks, extents e SHA-256.
- `quantitativos.csv` e `hipoteses.json`.
- `demonstracao-sintetica.zip`: pacote obrigatório de cinco artefatos.

O export falha fechado. Um erro do auditor não publica o ZIP.

## Ingestão privada de PDF

```bash
uv run croquitodxf-demo ingest \
  --input "/caminho/autorizado.pdf" \
  --dataset-id "identificador-logico-v1" \
  --role "golden|regression|evaluation" \
  --output output/pdf \
  --dpi 200
```

O original é somente lido e não é copiado. A saída contém um PNG por página,
contact sheet e `manifest.json` com digest, dimensões, rotação, cobertura de tinta,
quantidade de texto/vetores e sugestão conservadora de página vazia. Uma sugestão
de página vazia nunca elimina a página.

Não versione `output/`. Remova renders de cliente em até sete dias ou antes, se o
trabalho terminar.

## Propostas de visão computacional

Para um dataset já ingerido:

```bash
uv run croquitodxf-demo propose-dataset \
  --manifest output/pdf/identificador-logico-v1/manifest.json
```

Cada página recebe:

- `vision-proposals.json`: candidatos completos em pixels.
- `vision-overlay.png`: subconjunto conservador para revisão visual.
- `vision/summary.json`: contagens, limites atingidos e estado de segurança.
- `vision/contact-sheet.png`: visão geral de todas as páginas.

O estágio não conhece escala, unidade, objeto ou semântica. Linhas de texto e
anotações também podem virar candidatos; por isso o JSON é evidência, não cena CAD.

Execute a avaliação determinística:

```bash
make vision-eval
```

O gate exige recall da geometria conhecida da fixture e garante que 100% das
propostas permaneçam `unresolved` e não exportáveis.

## Revisão de cotas e solver

Um `ReviewPacket` liga transcrições ao digest e ao recorte da imagem. Gere o
overlay, solucione e exporte somente após aprovação explícita:

```bash
uv run croquitodxf-demo review-artifacts \
  --packet /caminho/review-input.json \
  --image output/pdf/caso/page-001.png \
  --output output/pdf/caso/review

uv run croquitodxf-demo solve-rectangle \
  --packet output/pdf/caso/review/review-packet.json \
  --request /caminho/rectangle-request.json \
  --associations /caminho/associacoes-confirmadas.json \
  --output output/pdf/caso/review
```

O retorno `review_required` com código `2` é esperado quando uma cota ainda está
`proposed` ou `ambiguous`. Não edite esse estado para contornar o fluxo: a
confirmação exige um `HumanDecision` completo.

O arquivo de associações é um objeto JSON de `reading_id` para o `proposal_id`
selecionado pelo revisor. Ele é obrigatório mesmo para leituras confirmadas: o
solver não usa proximidade em pixels como associação implícita.

Para registrar uma decisão real sem sobrescrever a proposta, forneça um batch de
decisões com `reviewer_id`, papel e timestamp com timezone ao comando
`apply-review`. O formato está documentado em
[Measurement Review and Solver](../ai/MEASUREMENT_REVIEW_AND_SOLVER.md).

Para ranquear geometrias CV próximas de cada recorte de cota, sem confirmar alvo:

```bash
uv run croquitodxf-demo associate-review \
  --packet output/pdf/caso/review/review-packet.json \
  --proposals output/pdf/caso/vision/page-001/vision-proposals.json \
  --output output/pdf/caso/review
```

Veja [Measurement Association](../ai/MEASUREMENT_ASSOCIATION.md). O resultado é
observacional e nunca cria measurement, constraint ou DXF.

Execute o gate sintético ponta a ponta:

```bash
make solver-eval
```

Os artefatos em `output/solver-eval` incluem review packet, overlay, revisão
rascunho, aprovação sintética, DXF, preview, auditoria e ZIP. Dados reais nunca
recebem a aprovação da fixture.

## Serviços locais

```bash
cp .env.local.example .env.local
make dev-services
make db-init
make dev
```

- Web: `http://localhost:5173` ou `http://127.0.0.1:5173`.
- API: `http://localhost:8000`.
- OpenAPI: `http://localhost:8000/docs`.
- Keycloak: `http://localhost:8083`, realm `croquitodxf`.
- LocalStack: `http://localhost:4566` (S3, SQS, Step Functions, EventBridge e
  Secrets Manager).
- PostgreSQL: `127.0.0.1:5432`.

O ambiente usa PostgreSQL real em Docker e LocalStack apenas para APIs AWS. A
credencial seed é exclusivamente local e está no realm importado; nunca a reuse
fora deste ambiente. A API aceita tokens OIDC e não é acoplada a Cognito.
O bucket local aceita PUT assinado somente dessas duas origens, com `Content-Type`
e `x-amz-checksum-sha256`.
Configure ambas em `CROQUITODXF_WEB_ORIGIN`, separadas por vírgula, para que a API
também responda ao browser nos dois endereços.

### Carregar um pacote de revisão autorizado

O worker não gera pacote de revisão a partir do PDF sem OCR e IA, que permanecem
desligados. Para conduzir uma sessão real, o responsável pelo tenant liga um pacote já
preparado localmente ao job criado pelo upload autenticado:

```bash
uv run croquitodxf-demo seed-review \
  --job-id <uuid do job> --tenant-id <tenant> \
  --packet output/pdf/<caso>/review/review-packet.json \
  --associations output/pdf/<caso>/review/association-candidates.json \
  --proposals output/pdf/<caso>/vision/page-001/vision-proposals.json \
  --rectangle-request output/pdf/<caso>/rectangle-request.json \
  --manifest output/pdf/<caso>/manifest.json \
  --image output/pdf/<caso>/page-001.png \
  --required-criteria "ACC_GUA_001=Perímetro, linha central, círculo, áreas e gols são entidades CAD limpas." \
  --operator-id <id lógico do responsável>
```

`--required-criteria` aceita só o código (`ACC_GUA_001`) ou o código e o texto do critério
separados pelo primeiro `=`. Com o texto, é ele que aparece na tela de revisão e vira a
mensagem da issue crítica na cena; sem ele, a frase padrão. O texto é o da linha
correspondente em [Acceptance Criteria](../product/ACCEPTANCE_CRITERIA.md) — o ID
documental usa hífen e o código de máquina, underscore. Repita a opção para declarar mais
de um critério.

O comando é fail-closed e sai com código `2` imprimindo `{"refused": "<CÓDIGO>"}` quando
o job não pertence ao tenant, quando `manifest.source_sha256` não bate com o upload,
quando o digest da página diverge do packet, quando o pacote já contém decisão humana,
quando uma leitura do solver não tem candidato de associação, quando o critério declarado
está fora do contrato (`INVALID_CRITERION_CODE`, `INVALID_CRITERION_TEXT`) ou quando já
existe revisão para o job. Ele **nunca** sobrescreve evidência e nunca fabrica decisão.

Os arquivos de entrada ficam em `output/`, que é ignorado pelo Git. Não versione nenhum
deles.

### Smoke fim a fim contra o stack local

```bash
make dev-services && make db-init
make dev-api            # em outro terminal
CROQUITODXF_ALLOW_TEST_TOKENS=true make smoke-local
```

O smoke usa **somente fixture sintética** e percorre presign assinado, PUT com checksum,
job, fila, seed, decisões, solver, calibração, aceite, aprovação, exportação e download do
ZIP pela URL assinada. Ele cobre o que o teste in-process não alcança: assinatura real do
S3, `head_object` com checksum, envelope do SQS, PostgreSQL e `JSONB`.

Ele recusa antes de escrever qualquer coisa se `CROQUITODXF_REAL_PROVIDERS_ENABLED`
estiver ligado, e exige `CROQUITODXF_ALLOW_TEST_TOKENS=true` porque o realm local
desabilita direct access grants — não há token fora do browser. Mantenha o opt-in ligado
apenas durante o smoke.

### Consumir a fila local

```bash
make dev-worker
```

A fila carrega dois comandos: `process_upload`, que valida o PDF e move o job para
`REVIEW_REQUIRED`, e `export_scene_package`, que gera o pacote CAD de uma revisão
aprovada. Execute o comando uma vez por mensagem.

### Aprovar e exportar

Depois de confirmar as leituras com associação explícita, calibrar e decidir as
propostas, a tela de revisão permite a aprovação técnica: três verificações explícitas,
o reconhecimento nominal dos critérios de escopo não cobertos e uma declaração de 20 a
500 caracteres. Nada é pré-marcado, e os motivos de bloqueio ficam visíveis.

Aprovada a revisão, "Exportar DXF" enfileira o comando; o worker gera, reabre, audita,
renderiza e só publica o ZIP se a auditoria aprovar. O download sai por URL assinada de
curta duração, com `audit_status` e SHA-256 exibidos ao lado.

O worker valida o envelope da fila, mantém o escopo de tenant e reabre o PDF em
arquivo temporário: assinatura, digest, estrutura, até 50 páginas e 100 MP por
página a 200 DPI. Só então persiste a transição para `REVIEW_REQUIRED`. Esta
primeira versão não chama provedores de IA, não deduz medidas e não cria DXF; a
revisão permanece uma cena stub bloqueada até o próximo slice.

## Contratos

Pydantic é a fonte de verdade. Depois de alterar `SceneRevision`:

```bash
make contracts
make check
```

Não edite manualmente `packages/contracts/scene.schema.json` ou
`packages/contracts/src/scene.generated.ts`.

## Limites de segurança

- Não configure chaves em `.env`; use perfil AWS ou secret manager.
- Não execute modelos pagos sem entitlement contratual ativo para o tenant.
- Não transforme proposta de CV em medida exata.
- Não execute `terraform apply` sem plano e aprovação.
- Não adicione PDFs, renders, DXFs reais ou respostas brutas de provedores ao Git.
- Não use `seed-review` para contornar a ausência de evidência: ele recusa qualquer
  divergência entre o pacote e o upload do tenant.
- Um volume local criado antes do índice único de `scene_revisions` pode ter versões
  duplicadas. Se `make db-init` falhar ao criar `uq_scene_version`, recrie o banco local
  com `make down-services` seguido de `make dev-services` em volume limpo.
- O Keycloak local não tem volume persistente: contas nominativas criadas na console
  desaparecem no `make down-services`. Só o realm importado sobrevive.
- O LocalStack roda com `PERSISTENCE=0`. Ao reiniciá-lo, S3 e SQS voltam vazios enquanto
  o PostgreSQL persiste — jobs e artefatos passam a apontar para objetos inexistentes.
  Nesse caso, recrie também o volume do banco.
