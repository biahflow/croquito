# ADR-0025: Homologação hospedada em GCP (Cloud Run)

Status: Accepted  
Data: 2026-08-14  
Responsável: Platform / Engineering

## Contexto

O desenho de produção aceito é AWS gerenciada em `sa-east-1`
([ADR-0002](0002-aws-managed-architecture.md),
[AWS Deployment](../architecture/AWS_DEPLOYMENT.md)) e **nunca foi aplicado**: não existe
nenhum recurso AWS real. Tudo o que foi validado até aqui rodou na máquina do
desenvolvedor — Docker local com LocalStack, PostgreSQL e Keycloak — inclusive os atos
humanos reais (29 decisões de leitura, aprovação técnica, DXF aberto no AutoCAD) e a
homologação da medição pelo servidor local ([ADR-0020](0020-local-homologation-server-for-valuation.md)).

A demanda nova não é de escala nem de disponibilidade: é de **acesso**. O ciclo seguinte
depende de pessoas que não estão nesta máquina — a orçamentista do domínio e um segundo
profissional de engenharia — usando o produto por navegador, sem clonar repositório e sem
depender de alguém que digite por elas. O ADR-0020 já havia escrito a fronteira: "o dia em
que houver segundo usuário é o dia da sessão autenticada".

Três forças delimitam a decisão:

- **Custo.** Homologação não pode carregar custo fixo relevante. O ambiente precisa
  escalar a zero onde der, e o que não escala a zero precisa ser justificado item a item.
- **Infraestrutura que já existe.** A organização que opera este produto já roda GCP
  (`biahflow-hml`, `us-east1`), com Workload Identity Federation sem chave de conta de
  serviço, registro de imagens e esteira de deploy provados em dois outros repositórios.
  Aplicar o desenho AWS do ADR-0002 seria começar do zero — VPC, ECS, Step Functions, RDS,
  conta, faturamento — para responder "a pessoa consegue usar?", que não é a pergunta que
  aquele desenho existe para responder.
- **Portabilidade já paga.** O código não é AWS-nativo: storage e fila estão atrás de
  interfaces internas, e as bordas mínimas de outro provedor (flavor de storage, transporte
  de fila, validador OIDC compartilhado) já entraram com teste próprio.

## Decisão

A **homologação** roda em GCP, no projeto `biahflow-hml` (`us-east1`), com cinco serviços
Cloud Run atrás de um host público único. Isto decide onde a homologação roda; **não**
decide onde a produção roda.

1. **Host público único e same-origin.** `https://croquito-hml.biahflow.ai` (borda
   Cloudflare *proxied*, que dá CDN e WAF do plano gratuito) chega no serviço
   `croquito-web-hml` — nginx, o único com ingress público. Ele serve `/revisao/` e
   `/medicao/` (as duas SPAs) e faz proxy de `/api/`, `/auth/` e `/medicao/api/`. Os outros
   quatro serviços têm ingress interno. Uma origem só significa nenhuma configuração de
   CORS de terceiros, cookie e token no mesmo host, e uma superfície pública para vigiar.
2. **Storage: Cloud Storage pela interoperabilidade S3/HMAC**, escolhido por flavor
   (`CROQUITO_STORAGE_FLAVOR=gcs`). O presign continua SigV4 path-style; o que a API XML do
   GCS não aceita — `x-amz-checksum-sha256` no PUT e SSE-S3 — é desligado pelo flavor, não
   por bifurcação do caminho de upload. O digest do documento continua obrigatório: ele
   deixa de viajar dentro da assinatura e passa a ser recalculado sobre os bytes gravados,
   como o worker já fazia.
3. **Fila: Pub/Sub em modo push** para `POST /pubsub` do worker, com o mesmo envelope de
   comando do adaptador SQS; o tópico configurado é o que escolhe o transporte. A
   autorização da entrega é a IAM do Cloud Run (`roles/run.invoker` na conta de serviço da
   subscription), verificada antes de a requisição chegar ao processo.
4. **Identidade: Keycloak hospedado em subpath `/auth`**, banco no mesmo Postgres
   gerenciado (schema próprio), realm importado **sem nenhum usuário**. Usuário real nasce
   por ato humano no console de administração
   ([HML_KEYCLOAK](../operations/HML_KEYCLOAK.md)). O
   [ADR-0011](0011-oidc-portable-identity.md) segue valendo: a aplicação depende do
   contrato OIDC, não do fornecedor.
5. **Banco: PostgreSQL serverless (Neon)** para a API e para o Keycloak. O compute suspende
   por ociosidade, o que é o comportamento desejado no custo e exige `pool_pre_ping` do lado
   da aplicação. O schema é criado pelo **bootstrap aditivo** (`croquito_api.bootstrap`,
   `create_all` mais colunas declaradas) executado como Cloud Run job **antes** de cada
   revisão da API. Isso é uma lacuna declarada, não uma solução: um runner de migrations
   revisadas continua sendo requisito de produção, e o bootstrap não sabe alterar nem
   remover nada.
6. **Uma imagem Python para quatro processos** (API, worker, medição e job de banco), mais
   uma imagem para o Keycloak e uma para o nginx. Os quatro processos rodam o mesmo código e
   divergem apenas em `command`/`args`; imagens separadas fariam a pergunta "qual revisão do
   worker corresponde a esta da API?" deixar de ter resposta trivial.
7. **Deploy só por esteira, com WIF e imagem por SHA.** Nenhuma chave de conta de serviço
   existe (a organização proíbe criá-las), então não há caminho de publicação a partir de
   uma máquina de desenvolvimento. A esteira é dona da imagem e do container (comando,
   variáveis, segredos, volumes); a casca dos serviços (ingress, IAM, instâncias, domínio)
   é dona de si mesma fora dela.

## Alternativas

- **Aplicar agora o desenho AWS do ADR-0002.** Rejeitada para homologação, e por isso este
  ADR **não substitui o ADR-0002**: o desenho AWS de `sa-east-1` continua documentado como
  alvo de produção e a decisão de produção fica **aberta**. Aplicá-lo hoje custaria conta,
  rede, ECS, Step Functions e RDS para responder uma pergunta de usabilidade — e a
  experiência de operar o produto hospedado é justamente o que falta para decidir produção
  com informação.
- **Abstração multi-cloud completa** (porta e adaptador para storage, fila, identidade e
  orquestração). Rejeitada: seria uma camada permanente, com custo de manutenção em cada
  mudança, para um segundo provedor que talvez nunca exista. O que entrou é o mínimo
  mensurável — um flavor de storage, um transporte de fila, um validador OIDC compartilhado
  —, cada um com teste próprio e nenhum deles no caminho de decisão do domínio.
- **Manter apenas a homologação local do ADR-0020.** Rejeitada pela razão que o próprio
  ADR-0020 antecipou: com um segundo usuário, "instale o repositório e rode o servidor"
  passa a ser o gargalo do ciclo, e a decisão da orçamentista voltaria a ser mediada por
  quem digita.
- **Docker Compose numa VM.** Rejeitada: seria uma segunda infraestrutura a manter (TLS,
  patch, backup, reinício) sem esteira, sem rollback por revisão e sem escala a zero.
- **Cloud Run jobs disparados por Cloud Scheduler no lugar do Pub/Sub push.** Rejeitada:
  transformaria uma fila de comandos idempotentes com reentrega em um agendamento, e o
  worker já tem o contrato de fila implementado e testado.

## Consequências

### Positivas

- O ciclo de validação deixa de exigir a máquina do desenvolvedor: engenheiro e
  orçamentista abrem uma URL.
- O rollback vira operação de segundos e sem build (`update-traffic` para a revisão
  anterior), porque toda imagem é imutável e endereçada pelo SHA do commit.
- A portabilidade deixou de ser afirmação e virou fato medido: o mesmo código roda em dois
  provedores de objeto e dois transportes de fila, com o domínio intocado.
- Custo próximo de zero em repouso: quatro dos cinco serviços escalam a zero e o banco
  suspende.

### Negativas

- **Dado de cliente passa a viver fora da máquina do operador**, em `us-east1` (EUA) — não
  em `sa-east-1`, como o desenho de produção prevê. Enquanto o ambiente for de homologação
  isso é aceitável apenas com material autorizado caso a caso; a retenção de sete dias
  precisa ser aplicada no ciclo de vida do bucket, e não há garantia de residência no
  Brasil ([Privacy and LGPD](../security/PRIVACY_LGPD.md),
  [Data Retention](../security/DATA_RETENTION.md)).
- Duas infraestruturas descritas em documentação ao mesmo tempo (AWS alvo de produção, GCP
  homologação real). O risco de alguém ler a errada é real e é mitigado por nota no topo do
  documento AWS e por [HML](../operations/HML.md) como fonte única do ambiente hospedado.
- O ambiente não valida o desenho de produção: Step Functions, Fargate, RDS e KMS
  continuam sem nenhuma execução real.
- O Keycloak não escala a zero de forma útil (subida de dezenas de segundos), então ele é o
  único custo fixo relevante do ambiente.
- O `bootstrap` aditivo em ambiente hospedado é dívida assumida: qualquer mudança de coluna
  que exija alteração ou remoção não tem caminho automatizado hoje.

## Riscos e mitigação

| Risco | Mitigação |
|---|---|
| Volume GCS por FUSE não é POSIX (sem lock, listagem eventualmente consistente, custo por operação) e o servidor de medição grava arquivo | Uma instância no máximo e uma rodada por ambiente; escrita atômica e guarda otimista por digest que o contexto já tem; limite registrado no [ADR-0026](0026-medicao-hospedada-sessao-autenticada-minima.md) |
| Cold start do Keycloak derrubar o login | Imagem `--optimized` (build fixado na imagem), sonda de subida folgada (20s + 24 × 10s) e instância quente no serviço de auth — o custo fixo declarado acima |
| Presign por interoperabilidade divergir do S3 (checksum e SSE recusados) | Diferença isolada em `CROQUITO_STORAGE_FLAVOR`, com teste por flavor; o digest continua obrigatório e é recalculado sobre os bytes gravados |
| Reentrega do Pub/Sub duplicar comando | Os handlers do worker já são idempotentes por claim atômico; envelope inválido é descartado com `200` e motivo em log, falha legítima devolve `500` e a entrega volta |
| Banco suspenso derrubar a primeira requisição | `pool_pre_ping=True` no engine da API; o Keycloak tem pool próprio com validação equivalente |
| Deploy de aplicação alterar a forma da infraestrutura | A esteira só troca imagem e o que depende dela; ingress, IAM, instâncias e domínio ficam fora dela |
| Documento de cliente subir para ambiente hospedado sem autorização | Ambiente de homologação, com material autorizado caso a caso e retenção de sete dias; a regra de dados do repositório continua valendo e nada de cliente entra no Git |
| Divergência entre o schema criado pelo bootstrap e o que a API espera | O job roda **antes** da revisão nova e falha fecha o deploy; a criação é aditiva e não destrutiva |

## Rollback

Duas camadas, nesta ordem:

1. **Imediato, sem build**: `gcloud run services update-traffic <serviço> --region us-east1
   --to-revisions=<revisão-anterior>=100`. Toda revisão carrega a imagem do SHA que a gerou,
   então voltar é apontar.
2. **Definitivo**: `git revert` do commit e novo deploy. O commit é autocontido (imagens,
   esteira, realm e documentos juntos).

Reverter o ambiente inteiro é apagar os serviços; nada no repositório depende deles, e o
caminho local (`make dev-services`, `make db-init`, `make dev`) continua sendo o ambiente
de desenvolvimento.

## Rastreabilidade

- Requirements: relacionado a [ADR-0002](0002-aws-managed-architecture.md) (desenho AWS de
  produção, **não substituído** — a decisão de produção permanece aberta),
  [ADR-0011](0011-oidc-portable-identity.md) (identidade OIDC portável),
  [ADR-0013](0013-export-worker-and-artifact-registry.md) e
  [ADR-0015](0015-trace-solve-worker-and-registry.md) (comandos assíncronos que passam a
  correr por Pub/Sub) e [ADR-0026](0026-medicao-hospedada-sessao-autenticada-minima.md).
- Operação: [HML](../operations/HML.md) e [HML_KEYCLOAK](../operations/HML_KEYCLOAK.md).
- Supersedes: none
- Superseded by: none
