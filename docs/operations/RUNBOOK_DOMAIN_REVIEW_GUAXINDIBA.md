# Runbook: primeira revisão profissional do Guaxindiba

Status: Active  
Responsável: Domain Reviewer / Engineering  
Última revisão: 2026-08-10

## Objetivo e limite

Preparar e conduzir a primeira sessão autenticada de revisão técnica do golden
autorizado Campo do Guaxindiba, preservando a evidência privada e a
rastreabilidade das decisões, até a aprovação técnica e a exportação do DXF
auditado.

Este runbook **não autoriza chamar provedores externos** nem antecipa qualquer
decisão: aprovação e exportação só ocorrem depois de a revisão cumprir todos os
blockers de geometria, e o reconhecimento de critério de escopo é um ato nominal do
profissional que assina, nunca um passo automático.

## Pré-condições e segurança

- O responsável pelo tenant confirma que o job pertence ao tenant e que o
  conjunto autorizado permanece somente no storage local protegido; PDF,
  renders, previews e URLs assinadas não entram no Git, tickets ou logs.
- Um `tenant_admin` cria uma conta OIDC nominativa para o profissional e lhe
  atribui o atributo `tenant_id` correto e o papel `engineer`. A conta seed local
  não deve ser reutilizada, salvo se representar formalmente o mesmo revisor.
- O revisor confirma que está habilitado a tomar a decisão técnica e que vê a
  evidência original protegida. A aplicação deriva identidade, papel e horário
  do JWT e do servidor; nunca os receba ou escolha no browser.
- Registre fora do repositório, em local de acesso controlado, somente o ID
  lógico do job, o revisor, o papel, data/hora, UUID/versão de revisão e
  ressalvas. Não copie medidas, texto bruto, imagens, previews, JWTs, URLs ou
  chaves de objeto.
- Pare a sessão se a conta não for nominativa/elegível, se o tenant não for
  confirmado ou se a evidência exibida não corresponder ao trabalho autorizado.

## Preflight local

1. Confirme que a configuração local aponta apenas para PostgreSQL, LocalStack
   e Keycloak locais, conforme `.env.local`. Não adicione credenciais de
   provedores nem habilite chamadas externas.
2. Suba e valide os serviços locais com `make dev-services` e
   `docker compose -f docker-compose.local.yml ps`; inicialize o banco com
   `make db-init` quando necessário.
3. Inicie API, web e, somente se o job ainda estiver aguardando processamento,
   o worker local (`make dev`, `make dev-worker`). O worker local não cria
   observações nem exporta DXF.
4. O **responsável pelo tenant** — nunca o revisor — faz o upload autenticado do PDF
   autorizado e, depois que o worker mover o job para `REVIEW_REQUIRED`, executa
   `croquitodxf-demo seed-review` ligando o pacote ao job, conforme o
   [guia de desenvolvimento local](../engineering/LOCAL_DEVELOPMENT.md). O pacote local
   do Guaxindiba já satisfaz todas as validações do comando: os quatro digests de imagem
   coincidem, as três leituras do solver existem e têm candidato de associação, e nenhuma
   traz decisão. O comando recusa qualquer divergência entre o pacote e o upload; uma
   recusa é condição de parada e não deve ser contornada editando arquivos.

   O documento autorizado precisa estar em storage local protegido antes da sessão. Manter
   o PDF na pasta de downloads do operador não atende essa condição, ainda que o digest
   confira.
5. Faça login no web app usando a conta nominativa. Abra o `job_id` fornecido
   pelo responsável pelo tenant, sem expô-lo fora do registro controlado.
6. Verifique que a revisão abre para o tenant atual e que imagem e overlay usam
   o mesmo zoom. `JOB_NOT_READY`, `404 NOT_FOUND`, erro de login ou ausência de
   preview são condições de parada: diagnostique ownership, estado do job ou
   expiração sem tentar uma decisão.

## Condução da sessão

1. Comece pelos blockers críticos e revise uma leitura por vez: texto original,
   recorte de evidência, tipo, unidade e alternativas de associação.
2. Para confirmar ou corrigir, selecione um candidato de associação da própria
   leitura e inclua uma justificativa baseada na evidência protegida. Corrigir
   altera apenas a nova revisão; a proposta original permanece histórica.
3. Rejeite falso positivo com justificativa. Não use rejeição para esconder uma
   dúvida geométrica ou preencher uma medida ausente.
4. Aguarde a resposta antes da próxima ação. Se ocorrer `REVISION_CONFLICT`,
   recarregue a revisão, examine a nova versão e decida novamente; nunca reenvie
   uma decisão às cegas. Uma leitura decidida não pode ser sobrescrita.
5. Confirme que cada alteração criou uma nova versão e que o registro controlado
   recebeu apenas os metadados permitidos. A sessão não avança para aprovação ou
   exportação enquanto houver issue crítica, entidade relevante `unresolved` ou
   requisito `ACC-GUA` pendente.

## Encerramento e escalonamento

- Considere o preflight concluído somente quando a conta nominativa, o acesso
  tenant-scoped e a abertura da revisão tiverem sido verificados. A decisão
  profissional continua pendente até o revisor realizar cada ação necessária.
- Após decisões reais, compare a versão retornada, blockers e ressalvas com o
  registro controlado.
- A aprovação técnica é um ato separado e explícito: marque as três verificações,
  reconheça nominalmente cada critério de escopo não coberto e escreva a declaração
  técnica. Reconhecimento de escopo **não** dispensa blocker de geometria — resíduo
  numérico, cota incompatível, aproximação não aceita ou calibração obsoleta continuam
  impedindo a aprovação, e tentar contorná-los é condição de parada.
- Aprovada a revisão, solicite a exportação e aguarde o estado `COMPLETED`. Confira
  `audit_status` e o SHA-256 antes de baixar. Um `FAILED` com `EXPORT_AUDIT_FAILED` não
  publica pacote algum: registre os erros de auditoria e escale.
- Abra o DXF no AutoCAD e registre a evidência de abertura, o UUID da revisão aprovada e
  as ressalvas reconhecidas no registro controlado, fora do repositório.
- Em caso de `403 FORBIDDEN`, corrija o vínculo de papel com o `tenant_admin`; em
  caso de `404`, não tente outro tenant; em caso de `409 JOB_NOT_READY`, aguarde
  o workflow local; em caso de suspeita de exposição, revogue o acesso, pare a
  sessão e siga o processo de incidente.
- Previews expiram e os artefatos locais seguem a retenção máxima de sete dias.
  Ao fim do trabalho, remova-os pelo fluxo de retenção aprovado, sem registrar
  conteúdo em logs ou no repositório.

## Validação do mecanismo

Antes da sessão humana, execute:

```bash
uv run pytest tests/api/test_api.py -k "review or approve or export"
uv run pytest tests/worker/test_rectangle_solver.py tests/worker/test_review_seed.py
uv run pytest tests/worker/test_export_worker.py
uv run pytest tests/e2e/test_full_flow.py
uv run python scripts/check_docs.py
```

Os testes validam isolamento por tenant, papel elegível, idempotência, conflito
de revisão, decisão imutável, associação explícita, preservação da geometria aceita
entre revisões, recusas do seed, contrato de aprovação e publicação do pacote somente
após auditoria aprovada. O teste fim a fim percorre a cadeia inteira, do upload ao pacote
auditado, incluindo o envelope publicado na fila. Eles usam somente fixtures sintéticas e
não substituem a decisão profissional.

Para validar o ambiente local em si — presign assinado, `head_object`, SQS, PostgreSQL e
publicação do pacote — rode também `make smoke-local` conforme o guia de desenvolvimento
local. O smoke usa fixture sintética e nunca toca no documento autorizado.

## Pós-condições

- Nenhuma decisão, aprovação ou DXF real é fabricado por este runbook.
- `docs/STATUS.md` só deixa de indicar a condição como pendente após uma decisão
  profissional realmente persistida na sessão autenticada.
- A abertura no AutoCAD, aprovação de domínio e mudança de marco exigem registro
  separado com ressalvas e atualização de status correspondente.
- O caminho de código para aprovar e exportar existe e está coberto por teste; isso não
  antecipa nenhuma decisão. Nenhum critério de escopo é reconhecido em nome do revisor.
