# ADR-0020: Servidor local de homologação para o contexto de medição

Status: Accepted
Data: 2026-08-13  
Responsável: Product / Engineering

## Contexto

A cadeia de medição (M1–M5 do contexto `valuation`) é CLI-first: o estado de uma rodada
é um diretório de artefatos JSON atômicos, sem API, banco ou tipos TS. A homologação do
fluxo, porém, é ato da orçamentista do domínio — e ela homologa por uma tela, não por
JSON editado à mão. A sessão autenticada completa (rotas `/v1`, PostgreSQL, S3, papel
`orcamentista` no Keycloak, contratos TS gerados) é o destino de produto, mas custa um
marco grande, e a rodada real do Campo do Toca já está pronta para homologação hoje.

Duas lacunas declaradas pesam na decisão: o contexto não tem concorrência otimista
(`base_version`) — [Valuation Context](../architecture/VALUATION_CONTEXT.md) registra
que esse mecanismo pertence à futura sessão autenticada — e a identidade do revisor no
CLI é campo do JSON de entrada, enquanto a API de cena a deriva do JWT.

## Decisão

O M6 entrega a homologação por um **servidor local fino**
(`croquito-valuation serve`, `local_server.py`) mais um app web dedicado
(`apps/medicao`), com os seguintes limites, todos deliberados:

- O servidor **embrulha as mesmas funções de domínio fail-closed do CLI** — nenhuma
  regra de negócio nova; recusa do domínio atravessa com código estável e nunca grava
  artefato.
- **Ferramenta local, nunca produção**: sem autenticação, bind default em `127.0.0.1`,
  CORS restrito à origem local do app; expor em outra interface imprime aviso. É a
  mesma família do `parity`: instrumento do operador sobre a própria máquina.
- **Identidade por flag de inicialização** (`--reviewer`): o servidor carimba
  `reviewer_id`, `reviewer_role="orcamentista"` e `decided_at` (UTC do servidor); o
  corpo das requisições recusa esses campos (`extra="forbid"`). `decision_id` continua
  derivado no domínio.
- **Guarda otimista por digest de arquivo** (`LOCAL_STATE_MOVED`, 409): toda mutação
  exige o sha256 do artefato que o cliente leu. É o substituto local e declarado do
  `base_version` — cobre o caso real (duas abas), não resolve a lacuna no domínio, que
  permanece registrada para a sessão autenticada.
- O servidor chama provider para **uma única operação**: a extração de legenda
  disparada pelo upload da prancha (`POST /plates`), automática e assíncrona, **sem
  aprovação por clique — decisão explícita do usuário em 2026-08-13**. Os freios que
  permanecem: teto de gasto por variável de ambiente no start do servidor (sem teto, a
  extração fica `unavailable` visível e a prancha ainda entra na rodada); o
  consentimento sobre o documento é o **próprio ato de upload** — o vínculo
  página↔documento por digest continua obrigatório (`bind_page_to_document`) e o digest
  consentido é registrado no estado e no `extraction-lineage.json`; braço fixado no
  vencedor da eval comparativa (Sonnet; braço `fixture` é recusado); falha é exibida
  fail-closed com re-disparo explícito (`POST /plates/extract`), nunca retry silencioso
  além da política transitória do adapter. O **refino pago de código continua exclusivo
  do CLI**, atrás da allowlist por ambiente.
- O app `apps/medicao` **nunca calcula dinheiro**: todo total exibido vem do servidor,
  recomputado pelos validadores do modelo (regra do FDD).

## Alternativas

- **Sessão autenticada completa já no M6** — rejeitada por custo/latência de
  homologação: exigiria tabelas novas, ~7 rotas, extensão do pipeline de contratos,
  papel e usuário no realm, comandos de fila; a homologação real ficaria meses distante.
  Continua sendo o destino: as telas e módulos puros do `apps/medicao` migram; o
  servidor local é descartável por construção.
- **Editar os JSONs à mão / homologar pelo CLI** — rejeitada: a decisão da orçamentista
  ficaria mediada por outra pessoa (quem digita), enfraquecendo exatamente o ato humano
  que a homologação existe para registrar.
- **UI dentro de `apps/web`** — rejeitada: o app de cena é um monólito de ~4.000 linhas
  sem router, acoplado à API autenticada; misturar as duas superfícies confundiria
  fronteiras e estabilidade.

## Consequências

### Positivas

- Homologação da rodada real da Toca em dias, com decisão item a item rastreável
  (identidade fixa do processo, carimbo do servidor, `decision_id` do domínio).
- As regras de UX do FDD (nada pré-marcado, total só recomputado, código sugerido é
  pendência) ganham a primeira implementação de tela, reutilizável na sessão
  autenticada.
- A lacuna de `base_version` ganha cobertura local honesta sem inventar schema novo no
  domínio.

### Negativas

- Duas superfícies de contrato temporárias (rotas locais × `/v1` autenticada); as rotas
  locais não entram no [API Contract](../architecture/API_CONTRACT.md), que permanece
  exclusivo da API autenticada — o contrato local vive no docstring do módulo e nos
  testes.
- Sem multiusuário e sem auditoria central: aceitável apenas porque o escopo é
  homologação local pelo próprio operador, nunca operação de tenant.

## Riscos e mitigação

- **Deriva de escopo (servidor local virar "produção de fato")** — mitigado pelo limite
  escrito (este ADR + docstring + aviso de rede) e pela ausência deliberada de
  autenticação/tenant: o dia em que houver segundo usuário é o dia da sessão
  autenticada.
- **Divergência entre UI local e futura UI autenticada** — mitigado por concentrar
  comportamento nos módulos puros testados do app e nas funções de domínio; o servidor
  é só transporte.
- **Concorrência entre CLI e servidor sobre o mesmo diretório** — mitigado pela guarda
  de digest e pela escrita atômica; corrida residual entre processos é aceita e
  documentada (TOCTOU fora do caso de uso).
