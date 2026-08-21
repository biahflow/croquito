# ADR-0043: App de levantamento de campo como PWA offline-first no monorepo

Status: Proposed  
Data: 2026-08-21  
Responsável: Architecture

## Contexto

A F-032 cria a superfície de coleta do técnico em campo: um app mobile que substitui o
papel por coleta estruturada, funcionando 100% offline (praças sem sinal), produzindo
medidas sempre vinculadas à geometria e fotos ancoradas, e sincronizando quando houver
rede. É a primeira superfície do produto com requisito duro de offline e a primeira
fora do par SPA (`apps/web`) + API (`croquito_api`).

Forças em jogo:

- O repositório já tem: monorepo com npm workspaces, pipeline de contratos
  Pydantic → JSON Schema → TS (`make contracts`), FastAPI com OIDC/tenant do JWT,
  `Idempotency-Key`, `base_version` e presign GCS (flavor `gcs` em
  `services/api/src/croquito_api/storage.py`), Pub/Sub no hospedado (ADR-0025), e o
  scene graph como única fonte geométrica (ADR-0005/0006).
- Uma proposta externa avaliada na sessão de 2026-08-21 sugeria API NestJS nova,
  PostGIS, repositórios separados e infra AWS — tudo divergente do que está de pé.
- A homologação em curso não pode ser tocada; a esteira `deploy-hml` dispara em push
  na `main`.

## Decisão

1. O app de campo vive no monorepo como workspace novo `apps/field` — PWA React 19 +
   Vite + TypeScript strict + `vite-plugin-pwa`/Workbox, coberto por `make check` e
   `make test` como os demais workspaces. Não reverte a D9 do ADR-0028: aquela decisão
   unifica as jornadas autenticadas do escritório numa SPA; o campo é superfície nova,
   com requisitos (offline, instalável, aparelho do técnico) que a SPA do escritório
   não tem, e deploy próprio.
2. Offline-first com outbox: o banco local do app é a fonte de trabalho (IndexedDB via
   Dexie), toda ação persiste localmente antes da confirmação visual, e a
   sincronização envia operações idempotentes (`operation_id` único casando com o
   `Idempotency-Key` da API). Dado local nunca é apagado antes do ack do servidor.
   A persistência fica atrás da interface `SurveyRepository`, permitindo trocar Dexie
   por SQLite/Capacitor sem reescrever o domínio; o empacotamento nativo é evolução
   prevista, não parte desta decisão.
3. A geometria do levantamento é um modelo estruturado serializável (coordenadas em mm
   inteiros, origem/orientação locais; lat/long separada como referência geográfica) e
   é a fonte oficial do app; o canvas é SVG nativo e faz somente rendering/interação —
   o mesmo princípio de `apps/web`. O pacote exportado entra no pipeline como
   **observações** (`unresolved`/`approximate` com provenance), sujeitas aos portões
   existentes do scene graph; o app não cria caminho novo até geometria exata ou DXF.
4. O backend é extensão da `croquito_api` (rotas `/v1/surveys` em fatia futura), com
   mídia via presign GCS e processamento assíncrono via fila existente. Nenhum serviço
   novo, nenhuma stack de backend nova, nenhum banco geoespacial.
5. Estilização com Tailwind v4 em `apps/field` (decisão do usuário em 2026-08-21):
   superfície nova com design próprio de campo (poucos controles, grandes, alto
   contraste). A divergência com o CSS puro de `apps/web` fica registrada aqui e não
   autoriza reestilizar `apps/web`.

## Alternativas

- **API nova em NestJS/Fastify com SDK gerado de OpenAPI** — rejeitada: a FastAPI
  existente já provê auth multitenant, idempotência (essencial ao outbox),
  concorrência otimista e presign GCS; uma segunda stack de backend duplicaria
  operação, observabilidade e migrações sem ganho funcional.
- **PostGIS como fonte geométrica no banco** — rejeitada: criaria segunda fonte de
  verdade competindo com o scene graph e suas invariantes (precision/provenance/
  portão de export); a validação que importa é de domínio, feita em Python; o único
  uso espacial previsível (localizar a praça) é um ponto lat/long que PostgreSQL puro
  atende. Se um dia houver consulta espacial de verdade (mapa/raio), será ADR novo.
- **Repositório separado para o app de campo** — rejeitada: perderia o pipeline de
  contratos gerados, os portões (`make check`/`make test`) e a governança (ADRs,
  lifecycle); o isolamento da homologação é dado por branch/worktree, não por repo.
- **Canvas com Konva** — rejeitada por ora: SVG nativo é o padrão deliberado do repo,
  atende o NFR (2.000 elementos, pan/zoom fluido com transform em grupo) e mantém um
  paradigma só; reavaliar apenas se o profiling nos aparelhos homologados reprovar.
- **App nativo/Capacitor desde já** — adiada: PWA valida o produto com custo menor; a
  interface de repositório preserva o caminho de empacotamento sem reescrita.

## Consequências

### Positivas

- Reuso integral de auth, contratos, portões e esteira já existentes; nenhuma stack
  nova de backend para operar.
- A ambiguidade passa a ser bloqueada na coleta (validação em campo), reduzindo
  retrabalho de revisão e retorno a campo; o pipeline recebe observações estruturadas
  em vez de papel interpretado.
- Troca futura de persistência (SQLite/Capacitor) sem reescrever domínio.

### Negativas

- PWA depende de quota/persistência do navegador (mitigação: armazenamento
  persistente solicitado, aviso de espaço, matriz de aparelhos homologada).
- Terceiro workspace aumenta a superfície de build/CI do monorepo.
- Tailwind v4 introduz uma segunda convenção de estilização no repositório,
  circunscrita a `apps/field`.

## Riscos e mitigação

| Risco | Mitigação |
|---|---|
| Navegador limpa IndexedDB com dados não sincronizados | `navigator.storage.persist()`, indicador de pendências, nunca apagar antes de ack; SQLite/Capacitor como plano B validado pela interface |
| Sincronização duplica ou perde operações | outbox com `operation_id` idempotente casando com `Idempotency-Key`; retentativa com backoff; ack explícito |
| Modelo do app diverge do scene graph | pacote exportado entra como observação sujeita aos portões existentes; contrato gerado pelo pipeline `make contracts` na fatia de sincronização |
| Performance de SVG em aparelho fraco | NFR medido na matriz homologada; pan/zoom por transform de grupo; Konva como fallback documentado |

## Rastreabilidade

- Requirements: NFRs de campo declarados no
  [Feature Contract da F-032](../features/F-032-app-levantamento-campo/feature.md)
  (seção Constraints); IDs formais de NFR a registrar quando a fatia de superfície for
  planejada.
- Supersedes: none
- Superseded by: none
