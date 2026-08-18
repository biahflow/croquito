# F-003 — Pacote de evidências

Status: `DONE`
Data: 2026-08-18
Responsável: Engineering

A medição de obra deixou de ter duas superfícies de contrato. A cadeia opera sobre a API `/v1`
autenticada, as telas vivem em `apps/web` e o modo hospedado saiu do repositório — mudou a
superfície, não o produto.

## 1. Contrato e decisão

- [ADR-0028](../../adr/0028-medicao-na-api-v1-autenticada.md) (`Accepted`, 2026-08-17) fixou
  entidade raiz, persistência, `base_version`, códigos de erro e destino das telas.
- [ADR-0030](../../adr/0030-overlay-do-takeoff-reconstruido-na-fila.md) (`Accepted`, 2026-08-17)
  nasceu **durante a execução**: o API Contract herdara do servidor de medição a promessa de
  devolver "o overlay atualizado" junto da decisão, e cumpri-la exigiria ler o PNG promovido e
  gravar blob pela fronteira de storage da API — que declara em texto não fazer nem uma coisa nem
  outra — com render PIL no request path. O re-render passou para a fila.
- A seção "Medição de obra" do [API Contract](../../architecture/API_CONTRACT.md) descreve as 18
  rotas e **deixou de ser pendente**: o aviso "decidido, não implementado" saiu e os sete códigos
  que esperavam à parte entraram na lista obrigatória.

## 2. Autorização humana

| Decisão | Data |
| --- | --- |
| Plano de execução e escopo integral numa rodada | 2026-08-17 |
| Nenhuma migração das rodadas do bucket de homologação | 2026-08-17 |
| Shortlist persistida sem avançar a versão da rodada | 2026-08-17 |
| Braço semântico da busca atrás do entitlement contratual | 2026-08-17 |
| `period_number`, `address` e `contract_label` como atributos da rodada | 2026-08-17 |
| Remoção alcança código, esteira e borda — serviço remoto fica para ato humano | 2026-08-18 |
| Overlay do takeoff reconstruído na fila, e não no request path | 2026-08-18 |

## 3. Baseline e resultado

| Portão | Antes (2026-08-17) | Depois |
| --- | --- | --- |
| `uv run pytest` | 1.298 | 1.426 |
| vitest | 346 (`apps/web`) + 127 (`apps/medicao`) | 522, num workspace só |
| `apps/medicao` | workspace próprio | removido; jornada em `apps/web/src/medicao/` |
| Rotas `/v1` de medição | 0 | 18, publicadas no OpenAPI |

A queda de 36 testes Python na remoção do modo hospedado é esperada e está explicada: 22 do
arquivo de teste do servidor hospedado, 14 que exercitavam a escrita direta do FUSE.

`tests/worker/test_valuation_local_server.py` terminou a feature **sem uma linha alterada**, com
seus 89 testes verdes. Era o oráculo de não-regressão da migração inteira: é ele que separa
remover a ponte de remover o produto.

## 4. Superfície entregue

18 rotas sob `/v1/valuation-rounds`, na ordem da cadeia: criar e listar rodada; estado; prancha
(associar, ler, enfileirar extração); takeoff (ler, overlay, decidir); códigos (shortlist,
recompute, busca no catálogo, conjunto, decidir); boletim (construir, ler); dossiê do aditivo
(construir, ler).

Dois comandos de fila, ambos sem `job_id` porque `Job` é vocabulário proibido neste contexto
(ADR-0016): `extract_valuation_plate` e `rerender_takeoff_overlay`.

## 5. Achados da revisão, corrigidos antes do commit

1. **Corrida de blob no re-render do overlay** (T9). O worker conferia o pacote antes do render,
   mas gravava o PNG numa chave fixa depois de um render que leva segundos. Uma decisão publicada
   nesse intervalo faria a URL assinada servir o desenho do pacote anterior enquanto a revisão
   declara outro digest — divergência que nenhuma leitura posterior detectaria. Fechado com
   reconferência entre o render e a escrita, e teste que força a corrida.
2. **`details.code` mentia** (T10). O envelope montava `{"code": error.code, **error.details}`, e
   os detalhes das invariantes de código trazem a chave `code` com o **código SCO recusado**: o
   cliente lia `"CE04100010(/)"` onde o contrato promete o nome da invariante.
3. **Corrida na cadeia de revisões virava `500`** (T10). A guarda de `base_version` é conferida em
   memória, então duas mutações que leram a mesma versão passavam as duas e disputavam a mesma
   posição da cadeia; a perdedora saía como erro de servidor. Passou a ser `409`, como nas rotas
   de revisão do croqui. Na leitura que calcula a shortlist — onde a tela faz polling e
   concorrência é o caso normal — perder a corrida serve o artefato do vencedor.
4. **`worksite_key` sem padrão na criação** (T11). A chave é imutável na rodada e o domínio a
   exige no boletim: sem a guarda, uma rodada nasceria válida com `PRAÇA X` e só quebraria no
   `POST .../calc`, quando a única saída seria abrir rodada nova.

## 6. Dívidas conhecidas, declaradas e não corrigidas

- **O boletim não declara idade.** Se o takeoff ou os códigos mudarem depois do `POST .../calc`,
  o `GET .../bulletin` continua servindo o boletim anterior como corrente, sem a marca `stale`
  que o overlay ganhou no ADR-0030. A técnica seria a mesma (digest de origem gravado na revisão,
  comparado na leitura); nem o ADR-0028 nem o servidor de medição pediam isso, e ampliar
  funcionalidade estava fora do escopo desta feature.
- **Respostas cujo corpo é o artefato do domínio aparecem no OpenAPI como objeto livre.** As
  contagens do takeoff nascem de `TakeoffItemStatus`, e fixá-las como campos faria a API deixar
  de mostrar um status novo sem que nenhum teste reclamasse. O tipo canônico do artefato é o
  gerado em `@croquito/contracts`, que é de onde a tela consome; o que sobrou escrito à mão no
  front são os envelopes de resposta.
- **`arm=hybrid` responde `503` mesmo com entitlement.** O braço semântico depende de um índice
  de embeddings de 39 MB que é artefato do CLI local, e nenhuma rota de `/v1` o publica — esta
  feature não migra dado nenhum. Estado honesto e declarado, em vez de léxico fingindo ser
  híbrido. Publicar índice na rodada seria feature nova.
- **`MedicaoApp` ainda aceita `session: User | null`** e mantém a tela interna de não
  autenticado, que a casca já barra. Defesa em profundidade inalcançável; apertar a prop seria
  simplificação legítima.

## 7. Atos humanos pendentes (T27)

Nada disso é código, e nenhum deles foi executado por esta feature:

- remover o serviço Cloud Run `croquito-medicao-hml`, o bucket `croquito-hml-rounds` e a conta de
  serviço correspondente. A esteira já não os publica;
- conceder o papel `orcamentista` no realm de homologação
  ([HML_KEYCLOAK](../../operations/HML_KEYCLOAK.md));
- o primeiro deploy com a borda sem `/medicao/api/`;
- a **homologação real da orçamentista** sobre uma medição de verdade, que esta migração não
  substitui e que continua sendo a prova que falta ao produto.

A rodada que estiver no bucket de homologação **não é migrada por ninguém** — decisão humana de
2026-08-17. Ela permanece reproduzível pelo CLI `croquito-valuation` e pelo servidor local do
[ADR-0020](../../adr/0020-local-homologation-server-for-valuation.md), que sobreviveram intactos.
