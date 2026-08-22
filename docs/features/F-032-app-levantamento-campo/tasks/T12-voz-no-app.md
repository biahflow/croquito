# Task Contract — F-032 / T12: nota de voz offline no app (prancha 7a, DAP rev.2)

- Feature: F-032 — [feature.md](../feature.md)
- Plano pai: [plan-sync.md](../plan-sync.md) (tarefa T12)
- Depende de: T7 (contrato com `audio_media_ref` já provisionado), T9 (SyncEngine
  com categoria `audio` reservada), T10 (identidade — não bloqueia gravação).
- **GATE HUMANO PRÉVIO: prancha 7a da DAP rev.2 aprovada** (mock/README.md,
  seção "Registro de aprovação — revisão 2"). NÃO iniciar sem esse registro
  preenchido.
- Baseline declarada: portões verdes no HEAD corrente (evidence-sync.md).

## Goal

Nota de observação por voz gravada 100% offline: MediaRecorder → blob na tabela
`media` (sha256, como foto), ancorada a ponto/elemento via `ObservationNote` com
`audio_media_ref`, sincronizada como mídia de categoria `audio` (o backend já
aceita `audio/webm`/`audio/mp4` e publica `transcribe_survey_audio` no confirm).
A transcrição em si é T13; aqui o áudio só viaja.

## Contexto verificado (ler antes de editar)

- `docs/features/F-032-app-levantamento-campo/mock/campo.html` seção `#s7`,
  figura 7a + `mock/README.md` rev.2 — a superfície aprovada: card com âncora
  declarada, "Gravando… 0:12", Parar/Cancelar, banner de destino da transcrição.
  Textos podem ser ajustados (copy não é fixada), estados não.
- `apps/field/src/photos/media.ts` (`captureFile`/`buildMediaRecord` — hash antes
  de tudo) e `photos/quota.ts` — o caminho da foto a ESPELHAR para áudio.
- `apps/field/src/storage/SurveyRepository.ts` — `MediaRecord` é agnóstico de
  tipo (blob+mime); NENHUMA migração Dexie necessária.
- `apps/field/src/domain/types.ts` — `ObservationNote` (hoje só texto; o
  comentário "voz fora do MVP" cai). Comando novo/estendido em
  `domain/commands.ts` para nota com áudio (módulo puro, testável).
- `apps/field/src/sync/engine.ts` (`planMedia`) e `sync/contract.ts`
  (`toSurveyPacket`) — a categoria `audio` existe com total 0; o mapeamento
  precisa passar `audio_media_ref` resolvido (T7 deixou o campo viajando
  `undefined`; agora passa a resolver via `mediaIndex`).
- Codecs: `MediaRecorder.isTypeSupported` — Android/Chrome grava `audio/webm`
  (opus); iOS/Safari grava `audio/mp4` (aac). Registrar o mime REAL no
  `MediaRecord`; nunca transcodificar no aparelho.
- `apps/field/AGENTS.md` — persistência antes do feedback visual; blob nunca em
  estado React; rede só em `src/sync/`.

## Comportamento exigido

1. Módulo `apps/field/src/voice/` (espelho de `photos/`): `recordAudio` sobre
   MediaRecorder com escolha de mime por `isTypeSupported` (webm/opus →
   mp4/aac → erro claro se nenhum), timer, parar/cancelar; `buildMediaRecord`
   reutilizado (sha256 do blob final). Cancelar não grava NADA (7a).
2. Domínio: `ObservationNote` ganha `audio_media_ref?` (aditivo); comando de
   adicionar observação aceita áudio-com-ou-sem-texto (nota só de áudio é
   válida; nota vazia — sem texto e sem áudio — continua inválida). Regras no
   módulo puro com testes.
3. UI (somente a superfície da 7a): no fluxo "Observação" existente, opção de
   gravar; card de gravação com âncora escrita, timer, Parar (dark) / Cancelar;
   banner informativo do destino da transcrição. Estado sempre escrito; alvos
   ≥48px; funciona offline por inteiro.
4. Sync: `toSurveyPacket` resolve `audio_media_ref` pelo `mediaIndex`;
   `planMedia` inclui os áudios na categoria `audio` (total > 0 quando houver);
   presign/PUT/confirm seguem o caminho existente sem mudança de engine.
5. Testes (vitest): mime por suporte (fakes de MediaRecorder); cancelar não
   persiste; nota só-áudio válida e nota vazia inválida; round-trip do pacote
   com `audio_media_ref` (estende `contract.test.ts`); `planMedia` com áudio;
   quota/aviso como nas fotos.

## Out of scope (não tocar)

- Transcrição (T13), providers, `services/**`, `packages/**` além do já gerado
  (se o contrato Pydantic precisar de ajuste, PARE e reporte — T7 já
  provisionou o campo; regenerar contratos não deve ser necessário).
- Reprodução/player elaborado (um `<audio>` nativo simples é aceitável se a
  prancha 7a aprovada o mostrar; nada além).
- Desfoque/edição, voz-para-comando, Web Speech.

## Validação (comandos reais, nesta ordem)

```bash
cd /Users/danielcampos/workspace/daniel/croquito-f032
npm --workspace @croquito/field run test -- --run
npm --workspace @croquito/field run check
make check
make test
```

## Gates nomeados

- DAP rev.2 (7a) aprovada ANTES de iniciar — verificar o registro em
  mock/README.md; se ausente, BUILD_BLOCKED.
- COMMIT forbidden.

## Report

`BUILD REPORT` completo, incluindo os mimes efetivamente suportados na matriz
(webm/mp4), e o que ficou reservado para T13 (estado de transcrição, 7c).
