# ADR-0030: Overlay do takeoff reconstruído na fila, não no request path

Status: Accepted  
Data: 2026-08-17  
Responsável: Engineering

## Contexto

O overlay do takeoff é o PNG que mostra ao orçamentista **de onde cada número foi lido**: balões
numerados sobre a prancha, coluna de legenda ao lado, cor por estado do item
(`services/worker/src/croquito_worker/valuation/takeoff_overlay.py`). Ele é desenho em pixels
sobre o render da página, feito com PIL, e o digest da imagem é conferido contra o pacote antes
de qualquer traço.

No servidor de medição, cada decisão do orçamentista republica pacote **e** overlay no mesmo ato
(`local_server.py:1439-1478`): o overlay é renderizado em memória antes de qualquer escrita, para
que uma recusa de digest ou de bbox deixe o diretório intacto. A seção "Medição de obra" do
[API Contract](../architecture/API_CONTRACT.md), escrita a partir desse comportamento, herdou a
frase "a resposta traz a rodada em versão nova, com o pacote regravado e o overlay atualizado".

Levar essa frase ao pé da letra para `/v1` custa mais do que ela aparenta. Na API, a página
promovida não é um arquivo em disco: é blob no object store. Uma decisão de item passaria a

- **ler** o PNG promovido — alguns MB por decisão — pelo `ArtifactStore`, cujo `read_object`
  declara o oposto em texto (`services/api/src/croquito_api/storage.py:86-95`): "Só artefato
  PEQUENO de aplicação passa por aqui... Byte de cliente (PDF da prancha, PNG promovido) continua
  saindo por URL assinada: a API não faz streaming de conteúdo";
- **escrever** blob, operação que o `ArtifactStore` não tem e nunca teve: a fronteira de storage
  da API assina, lê artefato pequeno e confere cabeçalho — quem grava byte de cliente é o worker;
- **renderizar** com PIL dentro do request path, contra a regra de que a API "autentica, autoriza
  e coordena lifecycle — não renderiza PDF, não chama modelos e não gera DXF no request path".

O trabalho já existe do outro lado da fila, pronto e testado: `_extract_valuation_plate`
(`services/worker/src/croquito_worker/local_queue.py:1471`) renderiza exatamente esse overlay com
`render_takeoff_overlay` e o publica com `_put_round_png` sob o prefixo do tenant, junto do PNG
promovido, na mesma revisão em que publica o pacote.

O [ADR-0028](0028-medicao-na-api-v1-autenticada.md) decidiu **como o overlay sai** (D5: URL
assinada de curta duração, nunca bytes no request path) e não decidiu **quem o reconstrói** depois
de uma decisão. É essa lacuna que este ADR fecha.

## Decisão

**O overlay do takeoff é reconstruído por comando de fila, e a decisão do orçamentista nunca
espera por ele.**

1. `POST /v1/valuation-rounds/{round_id}/takeoff/decisions` grava a revisão nova com o pacote
   revisado, avança a versão da rodada e **enfileira** o re-render. O envelope segue o formato já
   estabelecido pela extração — roteado por comando, sem `job_id`, porque o
   [ADR-0016](0016-valuation-bounded-context.md) não admite `Job` no vocabulário da medição:

   ```json
   {"command": "rerender_takeoff_overlay", "round_id": "...", "tenant_id": "...", "packet_sha256": "..."}
   ```

2. **O overlay declara sua própria idade, sem coluna nova.** O mapa `artifact_digests_json` da
   revisão passa a carregar o digest do pacote que originou o overlay
   (`takeoff_overlay_packet_sha256`). Overlay é *vencido* quando esse valor difere do digest do
   pacote corrente — estado derivado, calculado na leitura, que não pode divergir do que a
   revisão realmente contém.

3. `GET /v1/valuation-rounds/{round_id}/takeoff/overlay` continua devolvendo JSON com URL
   assinada (D5 do ADR-0028 permanece inteiro) e passa a declarar `stale` e o digest de origem.
   **Overlay vencido não é erro**: a rota devolve `200` com o overlay anterior e a marca. Esconder
   a divergência seria pior do que mostrá-la — e, como em todo o produto, o estado não pode
   depender só de cor.

4. **Fila indisponível não derruba a decisão.** A decisão do orçamentista já está durável quando o
   comando é publicado; falha de transporte deixa o overlay vencido e o comando repetível, sem
   `503`. Isso difere da extração de propósito: lá o `202` *é* o enfileiramento, e sem fila não há
   ato; aqui o ato é a decisão, e o overlay é consequência dela.

5. O re-render **não é chamada paga**: é determinístico, roda sobre o PNG já promovido e não toca
   provider. Não passa pelo entitlement contratual do
   [ADR-0012](0012-contractual-ai-processing-entitlements.md) e não tem lineage de modelo.

O servidor local do [ADR-0020](0020-local-homologation-server-for-valuation.md) **não é tocado**:
lá o overlay continua síncrono, porque lá o render escreve num diretório de disco e não há fila.
As duas superfícies divergem nesse ponto enquanto conviverem — e a que sai é a antiga.

## Alternativas

**Render síncrono na rota, fiel à frase herdada.** Exigiria dar escrita de blob ao
`ArtifactStore` e admitir o PNG promovido no `read_object`, revogando em código duas regras
escritas à mão para impedir exatamente isso, e poria PIL e alguns MB de imagem no caminho de cada
item decidido — dezenas por rodada. Recusada por custo desproporcional a um artefato que é
**observacional**: o overlay não decide nada, ilustra o que já foi decidido.

**Render preguiçoso no `GET` do overlay, com cache por digest do pacote.** Tira o custo do caminho
da decisão, mas ainda precisa de escrita na fronteira da API e transforma uma leitura barata numa
leitura de latência imprevisível — a primeira tela a abrir depois de uma decisão paga por todas.

**Não regravar overlay nenhum.** Recusada: sem overlay o orçamentista perde a única visão de onde
cada número foi lido, que é a razão de o artefato existir.

## Consequências

- A tela acompanha o overlay por polling do estado da rodada, mecanismo que ela já usa para a
  extração — não há padrão novo de cliente.
- A frase "o overlay atualizado" sai do API Contract e é substituída pelo estado explícito; a
  seção da rota de decisão e a do overlay declaram o comportamento novo.
- O worker ganha um segundo comando de medição. `dispatch` já roteia por comando antes de exigir
  `job_id`, então o envelope novo entra sem tocar o roteamento.
- Em máquina de desenvolvimento sem worker, o overlay fica visivelmente vencido em vez de
  silenciosamente errado — o que é o resultado desejado.
- Um teste passa a provar que decisão com fila indisponível **não** falha e deixa o overlay
  vencido, e outro que overlay vencido nunca é servido como se fosse do pacote corrente.

## Riscos e mitigação

| Risco | Mitigação |
|---|---|
| Overlay vencido para sempre porque ninguém consome a fila | Estado explícito na rodada e na rota; o comando é idempotente e repetível a qualquer momento |
| Overlay de outro pacote servido como se fosse do corrente | O digest de origem viaja no mapa de digests e a comparação é feita na leitura, não gravada como verdade |
| Overlay de outra imagem | Preservada a conferência que o `render_takeoff_overlay` já faz do digest da imagem contra o pacote, antes de qualquer traço |
| Duas entregas do mesmo comando gastarem trabalho em dobro | Re-render é determinístico e a segunda entrega grava bytes idênticos; não há efeito colateral a proteger, ao contrário da extração paga |

## Rastreabilidade

- Requirements: fecha lacuna deixada pelo
  [ADR-0028](0028-medicao-na-api-v1-autenticada.md), que decidiu como a imagem sai (D5) e que a
  extração é comando de fila (D7), mas não quem reconstrói o overlay depois de uma decisão. O
  ADR-0028 **não** é substituído: tudo o que ele decide continua valendo. Preserva o
  [ADR-0020](0020-local-homologation-server-for-valuation.md), cujo servidor local segue
  síncrono. Execução em
  [F-003](../features/F-003-medicao-v1-migration/feature.md), tarefa T9.
- Supersedes: none
- Superseded by: none
