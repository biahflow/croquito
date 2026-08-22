# T6 — Fotos ancoradas à geometria

## Identity

```text
feature_id: F-032
task_id: T6
parent_plan: docs/features/F-032-app-levantamento-campo/plan.md (plano "MVP local, fatias 1–3")
depends_on: T3, T4 (entregues); executa após T5 na mesma branch
```

## Goal

Foto de campo capturada pelo aparelho, com hash SHA-256, blob guardado localmente
atrás do repositório e âncora explícita a um ponto ou elemento do levantamento
(comando `addPhotoAnchor` já existente no motor); o 📷 aparece no desenho e a "foto do
acesso" da chegada (T4) passa a funcionar e a satisfazer o item do checklist.

## Scope

- `apps/field/src/photos/**` (novo): captura via `<input type="file"
  accept="image/*" capture="environment">`, hash SHA-256 com `crypto.subtle.digest`,
  helpers puros testáveis (hash de bytes conhecidos, montagem do registro).
- `apps/field/src/storage/**`: extensão da interface e do Dexie — tabela `media`
  (`MediaRecord { id, sha256, mime_type, byte_size, blob: Blob, created_at }`),
  métodos `saveMedia`/`getMedia`; testes com fake-indexeddb (roundtrip, sha
  persistido). Dado local nunca apagado (sem delete).
- `apps/field/src/ui/**`: fluxo "Foto ancorada" habilitado no AddMenu — escolher
  âncora (tocar num ponto do desenho; elemento fica para quando existir catálogo),
  capturar, confirmar; `local_media_ref` = id do MediaRecord; "Tirar foto do acesso"
  da chegada habilitada, ancorando ao contexto: usar o primeiro ponto se existir,
  senão gravar mídia e satisfazer o item do checklist `foto-acesso` derivando de
  "existe mídia de acesso para a ordem" (campo `access_media_ref?` no
  `ArrivalContext` via extensão mínima do domínio + comando novo pequeno OU reuso de
  `recordArrival` — decisão do Builder, documentada).
- `apps/field/src/domain/**`: só a extensão mínima do parágrafo acima, com teste.

## Out of Scope

- Upload/sync, desfoque, IA sobre fotos, galeria/visualizador (o 📷 no desenho não
  abre a foto nesta fatia — registrar como reservado), compressão derivada, quota
  management (apenas aviso escrito se `navigator.storage.estimate` acusar <50 MB
  livres — um banner, nada além), `services/**`, `docs/**`.

## Acceptance Criteria

1. `npm run field:test` exit 0 com testes novos: SHA-256 de bytes conhecidos bate com
   o valor esperado; MediaRecord roundtrip no Dexie; item `foto-acesso` satisfeito
   após foto do acesso.
2. `npm run field:check`, `make check`, `make test` exit 0.
3. Roteiro manual no report (pode usar arquivo de imagem no lugar da câmera no
   desktop): anexar foto a um ponto → 📷 no desenho; reload preserva; foto do acesso
   na chegada satisfaz o checklist; warning `ELEMENT_WITHOUT_PHOTO` continua vindo só
   do motor.
4. `git status --porcelain` só no escopo declarado.

## Validation

```text
baseline: make check && make test verdes na branch após T5 revisada e commitada (o
  modelo principal registra o commit no handoff).
required: unit: npm run field:test
required: typecheck+build: npm run field:check
required: monorepo: make check && make test
```

## Required Capabilities

```text
READ: repositório; DAP ../mock/; storage/domínio/UI como entregues
WRITE: escopo declarado
VALIDATE: comandos acima
COMMIT: forbidden
```

## Context to Read First

`../feature.md` (fotos com SHA-256; nunca foto em log); `apps/field/AGENTS.md`;
`src/storage/` (interface e padrão de teste); `src/ui/FieldApp.tsx` (fila,
apply(build)); `src/domain/commands.ts` (`addPhotoAnchor`).

## Known Risks

- Blob fora do repositório (localStorage/base64 em estado React) — proibido; mídia
  vive no IndexedDB atrás da interface.
- Logar conteúdo/URL de foto — proibido pela convenção do repositório.
- Registrar âncora sem passar por comando/applyCommand.

## Human Gates

Qualquer superfície de galeria/visualização (fora desta fatia); desvio material do
DAP.

## Reporting

BUILD REPORT completo, com o roteiro manual executado.
