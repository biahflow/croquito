# Instruções para agentes — field

Estas regras estendem o [AGENTS.md](../../AGENTS.md) da raiz. Leia também
[ADR-0043](../../docs/adr/0043-app-de-campo-pwa-offline-first.md) — as decisões que este
workspace materializa — e o
[Feature Contract da F-032](../../docs/features/F-032-app-levantamento-campo/feature.md).

## Boundary

`apps/field` é a PWA offline-first do técnico em campo (ADR-0043). Ela coleta pontos,
segmentos, medidas e fotos ancoradas localmente; não resolve geometria exata, não decide
consenso e não substitui o scene graph — o pacote exportado entra no pipeline como
observação (`unresolved`/`approximate`), sujeita aos portões existentes.

## Regras

- `src/domain/` é a fonte oficial do levantamento, nunca o canvas: tipos serializáveis
  puros, sem import de `react` nem de `dexie`. Se um tipo de domínio precisar de um
  helper de UI ou storage, o helper fica fora de `src/domain/`.
- O desenho é `<svg>` nativo, sem biblioteca de canvas: rendering/interação somente,
  igual ao princípio de `apps/web`.
- Coordenadas e medidas em **milímetros inteiros** — nunca float, nunca outra unidade
  sem uma tarefa nova que decida a conversão.
- Toda ação do usuário persiste localmente via `SurveyRepository` **antes** do feedback
  visual (antes de atualizar o estado de React). Isto não é estilo, é a garantia de que
  uma ação em campo sobrevive a fechar o app no meio.
- Dado local nunca é apagado — nem depois do `ack`. `acknowledge` e a resolução de
  conflito só mudam `status` (`local` → `pending` → `acked`, ou `superseded` quando o
  técnico aceita a versão do escritório); nenhuma linha do outbox e nenhuma mídia é
  removida, e não existe `deleteMedia`/`deleteOperation` no `SurveyRepository`.
- **Transporte de rede é autorizado exclusivamente em `src/sync/`** (F-032, T9), e
  dentro dele apenas em `src/sync/apiClient.ts`, que é o único módulo com `fetch`.
  Nenhum outro diretório do workspace — `src/domain/`, `src/outbox/`, `src/storage/`,
  `src/ui/`, `src/photos/` — pode chamar `fetch`/`axios`/WebSocket, direta ou
  indiretamente: quem precisa falar com a API consome a fachada de `src/sync`. O motor
  (`src/sync/engine.ts`) recebe o cliente injetado, e é assim que os testes exercem a
  sincronização inteira sem rede real.
- Sem `VITE_CROQUITO_API_BASE_URL` o app opera em **modo local**: nada de rede sai do
  aparelho, a coleta funciona igual e o painel diz isso por escrito. Nenhum caminho de
  coleta pode quebrar por causa de env ausente ou servidor indisponível.
- Mídia sobe DEPOIS dos metadados (prancha 6a) e sempre por identidade de conteúdo
  (`sha256`), nunca pela referência local. Conflito é apresentado ao técnico (prancha
  6b), nunca resolvido em silêncio.
- Nunca registrar em log (nem devolver à UI) URL assinada, token, digest de arquivo ou
  conteúdo de mídia — a regra da raiz vale igual aqui, e o caminho de rede é onde ela é
  mais fácil de violar.
- Tailwind v4 é restrito a `apps/field` (ADR-0043, D5): não é precedente para
  reestilizar `apps/web`, que continua em CSS puro.
- Código e identificadores em inglês; todo texto visível em português do Brasil.

## Conclusão

Mudança de comportamento do levantamento atualiza o Feature Contract da F-032 e seus
critérios de aceite; mudança de domínio serializável que vier a virar contrato de
sincronização passa primeiro por `make contracts`, quando essa fatia existir.
