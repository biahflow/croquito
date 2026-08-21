# Task Contract — F-032 / T15: checagem de qualidade de foto no aparelho (prancha 7b, DAP rev.2)

- Feature: F-032 — [feature.md](../feature.md)
- Plano pai: [plan-sync.md](../plan-sync.md) (tarefa T15)
- Depende de: T7 (nenhuma dependência de T8/T9 — módulo local puro + UI).
- **GATE HUMANO PRÉVIO: prancha 7b da DAP rev.2 aprovada** (mock/README.md,
  seção "Registro de aprovação — revisão 2"). O módulo puro pode ser construído
  antes; a INTEGRAÇÃO de UI não inicia sem o registro preenchido.
- Baseline declarada: portões verdes no HEAD corrente (evidence-sync.md).

## Goal

Aviso de qualidade calculado NO APARELHO na hora da captura (sem rede, sem
provider): nitidez (variância de Laplaciano) e exposição (histograma) sobre a
foto recém-capturada; aviso escrito e NÃO bloqueante (7b) — "Refazer a foto"
(primária) × "Manter assim mesmo". A escolha "manter" nunca vira erro depois.

## Contexto verificado (ler antes de editar)

- `mock/campo.html` seção `#s7`, figura 7b + `mock/README.md` rev.2 — card da
  foto com tag `warn` escrita, banner explicando que a verificação é local e
  nada bloqueia, dois botões. Estados não mudam; copy pode ajustar.
- `apps/field/src/photos/media.ts` — `captureFile` (hash antes de qualquer
  processamento) e o fluxo de captura na UI (`ui/` — onde a foto ancorada e a
  foto de acesso são capturadas, T6/T4).
- Implementação de imagem no navegador: `createImageBitmap` + canvas 2D
  (`getImageData` em resolução REDUZIDA — ex.: lado maior ≤512px — para não
  travar aparelho fraco; documentar a redução como decisão de custo).
- NFR: resposta ao toque ≤100ms — o cálculo roda após a captura (não no tap) e
  pode levar algumas centenas de ms; mostrar o card imediatamente e preencher a
  avaliação quando pronta (estado "avaliando…" escrito) é aceitável dentro da
  7b.

## Comportamento exigido

1. Módulo puro `apps/field/src/photos/quality.ts`: `assessPhotoQuality(data:
   ImageData) → {sharpness: number, exposure: {clippedHighlights: number,
   clippedShadows: number}, verdict: "ok" | "blurry" | "under" | "over",
   reasons: string[]}` — luma → Laplaciano 3×3 → variância; frações de pixels
   estourados/esmagados por limiar. CONSTANTES nomeadas e documentadas como
   heurística inicial (calibração é trabalho do piloto, não regra de negócio);
   determinístico e coberto por teste com imagens sintéticas geradas em código
   (nítida×borrada×estourada×escura) — sem fixture binária.
2. Wrapper de captura: `evaluateCapturedPhoto(blob)` decodifica em resolução
   reduzida e chama o módulo puro; falha de decodificação NUNCA bloqueia a
   foto (avaliação vira "indisponível", registrada só em memória de tela).
3. UI (7b, nas DUAS capturas — foto ancorada e foto de acesso): após capturar,
   card com tag de veredito escrita quando não-ok, banner explicativo, botões
   "Refazer a foto" (primária) e "Manter assim mesmo". Refazer descarta a
   captura atual (que ainda não foi ancorada) e reabre a câmera; manter segue o
   fluxo existente. Foto ok não ganha interstício — segue direto como hoje
   (a 7b só aparece quando há aviso). O veredito NÃO é persistido no domínio
   nesta fatia (nada no `Survey`/outbox) — é orientação do momento; registrar
   essa decisão no report.
4. Testes: módulo puro (vereditos e limiares nas 4 imagens sintéticas + caso
   limítrofe); wrapper com blob indecodificável; viewModel/fluxo — aviso só
   quando não-ok, refazer descarta sem persistir, manter persiste exatamente
   como o fluxo atual (regressão dos testes de T6 verdes).

## Out of scope (não tocar)

- Rede, providers, `services/**` (a análise servidor-side é T14 e já cobre o
  lado do escritório), `packages/**`.
- Persistir veredito no domínio/outbox; bloquear captura; auto-descarte.
- Enquadramento/detecção de conteúdo (só nitidez+exposição nesta fatia).

## Validação (comandos reais, nesta ordem)

```bash
cd /Users/danielcampos/workspace/daniel/croquito-f032
npm --workspace @croquito/field run test -- --run
npm --workspace @croquito/field run check
make check
make test
```

## Gates nomeados

- DAP rev.2 (7b) aprovada antes da integração de UI; módulo puro pode nascer
  antes, mas a tarefa só é entregue completa com o gate satisfeito.
- COMMIT forbidden.

## Report

`BUILD REPORT` completo, incluindo os limiares iniciais escolhidos (com a
marcação de heurística-a-calibrar) e o custo medido da avaliação (ms em imagem
típica reduzida).
