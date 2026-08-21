# F-032 — App de levantamento de campo (PWA offline-first)

## Status

`READY_FOR_HUMAN_REVIEW`

MVP local completo em 2026-08-21: fatia 0 (T1 scaffold) e o plano "MVP local, fatias
1–3" (T2 motor, T3 coleta/medida, T4 ordens/chegada, T5 conclusão, T6 fotos)
executados, revisados linha a linha e commitados na branch
`f-032-app-levantamento-campo`, com portões completos verdes — evidência consolidada
em [evidence.md](evidence.md). Pendem os atos humanos: decisão de merge/push (dispara
a esteira `deploy-hml`) e, depois, o plano próprio da fatia de sincronização
(`/v1/surveys`, prancha 6), que devolve a feature a `PLANNING`.

## Priority

`HIGH` (seleção humana de 2026-08-21)

## Problem

O levantamento de campo nasce em papel: o técnico desenha o croqui à mão, anota cotas
soltas e fotografa sem vínculo com o desenho. Todo o pipeline do croquito existe para
interpretar esse papel (ingestão → OpenCV → revisão de cotas → associação → solver), e
a ambiguidade que ele combate nasce na coleta: cota manuscrita sem par de pontos
declarado, medida de conferência ausente, foto que não se sabe de qual elemento é,
perímetro que não fecha — descobertos só no escritório, quando corrigir exige voltar à
praça. A F-023 (Survey Quality Score) mede essa qualidade a posteriori; nada hoje a
garante a priori.

## Desired Outcome

O técnico coleta num app mobile (PWA) que funciona 100% offline e transforma o
levantamento em coleta estruturada e guiada:

- toda medida nasce respondendo **quanto mede, entre quais pontos, de qual elemento,
  como foi medida e qual evidência comprova** — com técnico, data/hora e status;
- validações geométricas rodam ainda no local (perímetro aberto, segmento sem medida,
  diagonal incompatível, foto não vinculada), bloqueando conclusão com erro crítico;
- o resultado é um **pacote estruturado** (geometria vetorial + medidas + fotos
  ancoradas + histórico) que entra no pipeline existente como **observações**
  (`unresolved`/`approximate` com provenance), tornando a revisão e o DXF muito mais
  determinísticos;
- menos retorno a campo por informação faltante; papel vira contingência e, ao fim da
  transição, é substituído (estágios: piloto híbrido → digital oficial → paperless).

## Scope

Feature completa (fatiada; cada fatia com plano próprio):

1. **Fatia 0 — scaffold técnico** (esta rodada, T1): workspace `apps/field` no
   monorepo com PWA React+Vite+TS strict, Tailwind v4, modelo de domínio serializável
   (coordenadas em mm inteiros), persistência local IndexedDB/Dexie atrás da interface
   `SurveyRepository`, esqueleto de outbox de operações e shell mínimo de UI que prova
   ação → persistência → undo e indicador de offline. Sem telas finais, sem backend.
2. Ordem de levantamento pré-baixada (escopo, checklist, referências) e abertura
   integral offline.
3. Construção de geometria por comandos (pontos, segmentos, fechar perímetro, curvas)
   com cota nascendo vinculada a pontos/segmentos; biblioteca de elementos (calçada,
   meio-fio, escada com propriedades, academia etc.).
4. Tipos de medida (comprimento, diagonal, largura, raio, nível, desnível, altura,
   ângulo) com confirmação dupla para valores críticos e tolerância declarada.
5. Validação geométrica em campo com estados verde/amarelo/vermelho/cinza e conclusão
   bloqueada por erro crítico (pendência não crítica exige justificativa).
6. Fotos ancoradas a ponto/segmento/área/objeto, com hash SHA-256 do original.
7. Sincronização por outbox idempotente contra a `croquito_api` (rotas `/v1/surveys`,
   presign GCS para mídia) e export do pacote estruturado para o motor.

## Out of Scope

- Empacotamento Capacitor/SQLite (a interface `SurveyRepository` já nasce preparada
  para essa troca; a decisão de empacotar é gate futuro).
- Integração Bluetooth com trena laser, LiDAR, AR.
- Entrada por voz.
- IA/visão computacional sobre as fotos coletadas (correlata à F-030 — fotos na
  jornada de revisão — que segue feature separada).
- Substituição oficial do papel: o MVP opera em piloto híbrido; declarar o app fonte
  oficial é decisão humana posterior, com matriz de aparelhos homologada.
- Qualquer mudança em `services/**` nesta fatia 0 (as rotas `/v1/surveys` são fatia
  futura, planejada pelo ciclo normal).

## Acceptance Criteria

Da fatia 0 (verificáveis nesta rodada):

1. `apps/field` existe como workspace npm; `make check` e `make test` cobrem o app
   novo (`field:check` = `tsc -b && vite build`, `field:test` = vitest) e passam.
2. A PWA instala service worker e manifest; com o navegador em modo offline o app
   continua operando e exibe indicador de offline.
3. Uma ação de domínio (adicionar ponto) persiste em IndexedDB antes da confirmação
   visual; fechar e reabrir a aba preserva o dado; undo remove o último ponto.
4. O modelo de domínio é serializável, usa mm inteiros e não importa nada de UI; a
   fonte oficial é o modelo, nunca o canvas (regra registrada em
   `apps/field/AGENTS.md`).
5. O esqueleto de outbox registra operações com `operation_id`, `device_id` e
   sequência, com estados local → pendente → ack, sem transporte real.

Da feature completa (verificáveis nas fatias futuras, herdando os NFRs abaixo):

6. Um levantamento completo é coletável 100% offline e o pacote exportado é consumido
   pelo pipeline como observações, sem criar geometria exata fora dos portões do scene
   graph.
7. O app impede conclusão com erro crítico de validação geométrica.
8. Nenhuma foto ou coordenada aparece em log (convenção vigente do repositório).

## Constraints

- **Invariantes do scene graph valem inteiros**: o app produz observações; dimensão
  exata nunca deriva de pixels/canvas; associação é sempre explícita; export
  fail-closed. Nada no app cria um segundo modelo geométrico autoritativo.
- **NFRs de campo (baseline mensurável para as fatias de superfície):** 100% da
  coleta offline; ≥72h offline; zero perda de ação confirmada (persistir antes do
  sucesso na tela); autosave sem botão "Salvar"; abertura offline ≤2s p95 nos
  aparelhos homologados; resposta ao toque ≤100ms; alvos de toque ≥48×48px; alto
  contraste para sol; WCAG 2.2 AA como referência; 2.000 elementos de geometria sem
  degradação crítica; nunca apagar dado local antes de ack do servidor.
- **Piloto Android-first** com matriz de aparelhos homologada (não "todos os
  celulares"); GPS é referência geográfica, nunca medição.
- Stack e fronteiras conforme [ADR-0043](../../adr/0043-app-de-campo-pwa-offline-first.md)
  (Proposed): monorepo `apps/field`, backend por extensão da `croquito_api`, GCP
  (GCS + Pub/Sub) — sem serviço novo, sem PostGIS.
- Desenvolvimento em branch/worktree separada até decisão humana de merge; a
  homologação em curso não é tocada.

## Dependencies

- `croquito_api` (auth OIDC com tenant do JWT, `Idempotency-Key`, `base_version`,
  presign GCS) — as rotas `/v1/surveys` são extensão futura dela.
- Pipeline de contratos `make contracts` (Pydantic → JSON Schema → TS) para o pacote
  do levantamento nas fatias de sincronização.
- Keycloak/OIDC existente para login (com tolerância a expiração offline nas fatias
  de superfície).
- Relação com [F-030](../../product/ROADMAP.md) (fotos na revisão): o app de campo
  produz fotos já ancoradas à geometria, que futuramente alimentam aquela jornada.

## Unknowns

- Origem da "ordem de levantamento": quem a cria e onde (relação com a Relação de
  Praças do fluxo comercial) — a definir no design da fatia 2.
- Formato exato do pacote exportado (espelho do `ReviewPacket`/`TakeoffPacket` ou
  contrato novo) — decisão da fatia de sincronização, junto com as rotas.
- Matriz de aparelhos do piloto (modelos Android reais dos técnicos).
- Se tablet+caneta entra no piloto ou só celular.

## Risks

- PWA e IndexedDB estão sujeitos a quota/limpeza do navegador; mitigação: pedido de
  armazenamento persistente, aviso de espaço, e interface de repositório pronta para
  SQLite/Capacitor se o piloto provar necessidade.
- Superfície nova de UI sem design aprovado pode contaminar as fatias seguintes;
  mitigação: gate de Design Approval antes de planejar telas (o shell da fatia 0 é
  explicitamente descartável).
- Colisão de IDs entre sessões paralelas (já ocorrida nesta rodada: F-029/F-030/F-031
  reivindicados em outras sessões) — o ID F-032 foi verificado contra a main, o
  checkout compartilhado e a branch `feat/f-031-value-events` em 2026-08-21.

## Human Gates

1. ~~Aceite do [ADR-0043](../../adr/0043-app-de-campo-pwa-offline-first.md)~~ —
   **satisfeito**: aceito por ato humano de Daniel Campos em 2026-08-21.
2. ~~Design Approval Package da superfície do técnico~~ — **satisfeito**:
   [revisão 1 do pacote](mock/README.md) aprovada por ato humano de Daniel Campos em
   2026-08-21. Revisão nova do pacote exige aprovação nova; o scaffold da fatia 0
   continua fora da superfície aprovada.
3. Decisão de merge da branch `f-032-app-levantamento-campo` (merge na main dispara a
   esteira de deploy).
4. Declaração de início do piloto híbrido e, depois, da promoção do app a fonte
   oficial do levantamento.

## References

- [ADR-0043 — App de campo como PWA offline-first](../../adr/0043-app-de-campo-pwa-offline-first.md)
- [ADR-0028 — Medição na API `/v1` autenticada](../../adr/0028-medicao-na-api-v1-autenticada.md) (D9: jornadas do escritório numa SPA — o campo é superfície nova, não reversão)
- [ADR-0005 — Scene graph canônico](../../adr/0005-canonical-scene-graph.md) e
  [ADR-0006 — HITL e provenance](../../adr/0006-human-review-and-provenance.md)
- [Plano de execução da fatia 0](plan.md) e [Task Contract T1](tasks/T1-scaffold-apps-field.md)
- [F-023 — Survey Quality Score](../F-023-survey-quality-score/feature.md) (mede hoje a qualidade que esta feature passa a garantir na origem)
- [Operação da homologação GCP](../../operations/HML.md)
