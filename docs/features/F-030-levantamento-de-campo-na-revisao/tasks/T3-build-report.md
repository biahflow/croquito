# T3 — BUILD REPORT

Relatório do Builder para o [Task Contract T3](T3-painel-de-evidencia-web.md) da
[F-030](../feature.md). Executado diretamente na `main`, sem push. Camada web sobre as
rotas T1/T2 já entregues; nenhum serviço mudou.

```text
BUILD REPORT

Status: BUILD_COMPLETE

Files changed:
  - apps/web/src/api.ts
    Cliente tipado das rotas T1/T2 (tipos escritos à mão, sem contrato REST gerado):
    getFieldEvidence, listCompletedSurveys, linkSurveyToJob/unlinkSurveyFromJob,
    uploadStandaloneFieldPhoto (presign→PUT→confirm com SHA-256) e
    requestFieldPhotoReading. Cada mutação com Idempotency-Key e base_version; a URL
    assinada nunca é persistida.
  - apps/web/src/fieldEvidence.ts
    Lógica pura: rótulo de âncora declarada (nunca inferida), filtro manual por âncora,
    pastilhas de qualidade e de leitura (estado por extenso, cor nunca sozinha), leitura
    textual como rascunho e formatação pt-BR.
  - apps/web/src/fieldEvidencePanel.tsx
    Painel "Evidência de campo" e modal da foto (corpo puro FieldEvidenceBody +
    container FieldEvidencePanel). Estados do DAP rev. 3 no escopo T3: vazio, carregando,
    normal, sem análise/leitura pulada, recusa de IA e sem papel. Modal preserva a
    revisão e oferece "Abrir original" na URL assinada corrente.
  - apps/web/src/CroquiApp.tsx
    Monta o painel na aside da revisão quando há job aberto; import dedicado.
  - apps/web/src/styles.css
    Composições .foto/.fotos, .filtro, .leitura, .acoes, formulários de vínculo e
    upload, e o modal — todas sobre tokens existentes do :root, sem cor nova. Inclui
    .button-secondary citado pelo DAP rev. 3.
  - apps/web/src/fieldEvidence.test.ts
    Lógica pura (âncora, filtro, pastilhas, leituras) e transporte com fetch mockado:
    cada mutação prova Idempotency-Key e base_version; presign→PUT→confirm com SHA-256;
    MIME/âncora recusados antes da rede; REVISION_CONFLICT e SURVEY_NOT_COMPLETED viram
    ApiError com código estável.
  - apps/web/src/fieldEvidencePanel.test.tsx
    Estados renderizados como HTML estático (renderToStaticMarkup): vazio, carregando,
    normal com "foto não mede", sem análise neutro, recusa de IA sem esconder fotos, sem
    papel, e o modal com role=dialog/aria-modal e "Abrir original" na URL corrente.

Validation executed:
  - npm --workspace @croquito/web run test .......... exit 0 (45 files, 1099 passed)
  - npm --workspace @croquito/web run build ......... exit 0 (tsc -b strict + vite build)
  - make check ...................................... exit 0 até infra-check
    Ruff/formatação, mypy strict, check_docs (397 md), schema_export, drift de
    contratos e builds web/field verdes. O gate final `terraform fmt` (make infra-check)
    não roda nesta máquina — terraform não está instalado; é limitação de ambiente, não
    de código, e a T3 não toca infra.
  - make test ....................................... exit 0 (pytest + vitest de todos
    os workspaces; a suíte web nova entra aqui)

Validation skipped: none

Unavailable capabilities:
  - terraform ausente localmente: `make infra-check` (terraform fmt -check) não executa.
    Nenhum arquivo de infra foi tocado; o gate roda no CI.

Assumptions:
  - As respostas REST não têm tipos gerados (só schemas de domínio em @croquito/contracts),
    então os tipos da evidência foram escritos à mão em api.ts espelhando os modelos de
    services/api/src/croquito_api/main.py — o padrão já usado por Review e pela medição.
  - `analysis.quality.findings` e `analysis.readings` são lidos defensivamente (unknown →
    seguro): a tela nunca deriva medida deles.
  - O polling do painel recarrega getFieldEvidence enquanto uma leitura está QUEUED, o
    mesmo padrão do poll silencioso da revisão; cada carga traz URL assinada fresca.

Remaining risks:
  - Testemunhas (T5) e a proposta de classificação por IA (T7) não entram nesta tela por
    escopo; os estados 05-08 do mock ficam para essas tasks.
  - A qualidade da foto é traduzida do passe offline; rótulos de findings ainda não vistos
    caem no genérico "QUALIDADE APURADA" em vez de inventar copy.

Human decisions required: none
```
