# T3 — Telas de coleta e medida (pranchas 3–4 do DAP)

## Identity

```text
feature_id: F-032
task_id: T3
parent_plan: docs/features/F-032-app-levantamento-campo/plan.md (plano "MVP local, fatias 1–3")
depends_on: T2
```

## Goal

Substituir o shell descartável por a tela principal de coleta e o fluxo de medida do
[Design Approval Package revisão 1 aprovado](../mock/README.md) (pranchas 3a, 3b, 4a e
4b), renderizando o motor de T2 e persistindo **cada comando** como operação do outbox
via `SurveyRepository`, antes do feedback visual. Tudo local, sem rede.

## Scope

Pode criar/alterar somente:

- `apps/field/src/ui/**` (novas telas/componentes; `FieldShell.tsx` pode ser removido
  ou reescrito);
- `apps/field/src/styles.css` (tokens do DAP via Tailwind v4 `@theme`);
- `apps/field/src/outbox/**` (helper de aplicação comando→persistência→estado, se
  necessário);
- `apps/field/src/main.tsx`;
- `apps/field/index.html` (título/metadata se preciso).

## Out of Scope

- `src/domain/**` — o motor de T2 é dado; lacuna ou defeito nele é reporte
  (`BUILD_BLOCKED` se impedir), nunca conserto por aqui.
- `src/storage/**` (interface e Dexie ficam como estão; métodos novos só se T2 já os
  tiver exigido — se faltar método, reportar).
- Ordens/chegada (T4), conclusão (T5), fotos reais (T6 — o item "Foto ancorada" do
  menu aparece desabilitado com rótulo "em breve"), sincronização, `services/**`,
  `docs/**`.
- Voz: o item de observação é só texto (decisão registrada no DAP, "Entregue ×
  reservado").
- Qualquer desvio visual material do DAP — mudança de composição exige revisão 2
  aprovada; ajuste fino de espaçamento para caber conteúdo real não é material.

## Especificação

### 1. Autoridade visual

As pranchas 3–4 do DAP (`../mock/campo.html` + `03-coleta.png`, `04-medida.png`) são a
autoridade de composição: barra superior escura com pílula Online/Offline e contador
de pendências; desenho SVG dominando a tela; barra inferior Desfazer / ＋ Adicionar
(verde, `--accent` com `--accent-ink`) / Medir; menu Adicionar como lista plana de
botões ≥48px; teclado numérico próprio com vírgula; botão de confirmação que repete a
frase inteira ("Confirmar 7,35 m para S5"). Traduzir os tokens do mock (cores do
DESIGN_SYSTEM + novos aprovados no pacote) para o `@theme` do Tailwind em
`styles.css`; estado sempre escrito além da cor.

### 2. Comportamento

- **Estado da tela = `Survey` do motor + findings de `validateSurvey`** (tolerância
  default 50 mm por enquanto, constante nomeada). O SVG renderiza pontos, segmentos
  (tracejado vermelho + rótulo "Sx · sem medida" quando `SEGMENT_WITHOUT_MEASUREMENT`
  aponta para ele), cotas confirmadas em `--accent-text` com "✓", elementos como área
  suave com rótulo, âncoras de foto como ícone.
- **Aplicar comando**: helper único `applyCommand(repository, survey, result)` — se
  `ok`, grava survey e operação (seq pelo histórico completo por device, padrão já
  corrigido na fatia 0) e SÓ ENTÃO devolve o estado novo para o React; se `!ok`,
  mostra a mensagem estruturada (banner de erro do DAP). Nenhum caminho atualiza tela
  antes de persistir.
- **Adicionar ponto/segmento**: ponto por toque no SVG (coordenada do toque →
  mm inteiros do croqui); segmento por seleção de dois pontos em sequência com
  realce do primeiro selecionado; "Fechar perímetro" chama o comando e mostra o erro
  estruturado quando ambíguo.
- **Medir**: tocar num segmento (ou "Medir" com segmento selecionado) abre a tela da
  prancha 4a; dígitos em mm a partir de metros com vírgula (7,35 m → 7350); confirmar
  aplica `addMeasurement`. Se o motor devolver divergência na validação
  (`MEASUREMENT_DIVERGENCE` daquele vínculo), apresentar a tela 4b: as duas leituras,
  a diferença por extenso, "Medir de novo" e "Registrar motivo e manter as duas"
  (grava `justification` via novo `addMeasurement`… não: a justificativa é campo da
  medida — usar o comando que T2 fornecer para isso; se T2 não fornecer, reportar).
- **Undo**: botão Desfazer chama `undoLast` e persiste como operação, mesmo fluxo.
- **Pendências**: contador na barra = operações não-acked do survey (repositório).
- **Offline**: pílula por `navigator.onLine` + eventos, como no scaffold.

### 3. Testes

- Testes de unidade da lógica de view-model que não exige DOM: conversão
  toque→mm, metros-com-vírgula→mm e volta, montagem da frase de confirmação,
  seleção de par de pontos, mapeamento finding→decoração de segmento.
- `applyCommand`: com repositório Dexie fake-indexeddb, comando ok persiste survey e
  operação ANTES de devolver; comando com erro não persiste nada.
- Padrão do repositório: sem simulação de clique em DOM real (igual `apps/web`);
  comportamento visual verificado por build + verificação manual descrita no report.

## Acceptance Criteria

1. `npm run field:test` exit 0 com os testes novos descritos.
2. `npm run field:check` exit 0; `make check` e `make test` exit 0.
3. `npm run field:dev` (verificação manual do revisor, descrever no report o caminho):
   criar 4 pontos, ligá-los, fechar perímetro, medir 3 segmentos → cotas verdes com ✓
   e o segmento restante tracejado com rótulo; recarregar a página → tudo persiste;
   modo offline do navegador → pílula muda e coleta continua.
4. `grep -rn "fetch(\|axios\|WebSocket" apps/field/src/` sem retorno (sem rede).
5. `git status --porcelain` só no escopo declarado.

## Validation

```text
baseline: make check && make test verdes na branch após a entrega revisada de T2
  (o modelo principal registra o commit exato no handoff).
required: unit: npm run field:test
required: typecheck+build: npm run field:check
required: monorepo: make check && make test
```

## Required Capabilities

```text
READ:     repositório; ../mock/campo.html e capturas; src/domain de T2
WRITE:    escopo declarado acima
VALIDATE: comandos acima
COMMIT:   forbidden
```

## Context to Read First

- `../mock/README.md` + `campo.html` (pranchas 3–4) — autoridade visual.
- `apps/field/src/domain/` inteiro como entregue por T2 (comandos, códigos, findings).
- `apps/field/AGENTS.md` (persistir antes do feedback; canvas nunca é fonte).
- `docs/engineering/DESIGN_SYSTEM.md` (regras do verde e contraste).

## Known Risks

- Deixar estado geométrico só no React/SVG e "salvar depois" — viola a regra central;
  o fluxo é comando → persistência → estado.
- Recriar regra de validação na UI em vez de renderizar findings do motor.
- Tailwind arbitrário fora dos tokens do DAP — os valores vêm do pacote aprovado.
- Se um portão reprovar em área não tocada, parar e reportar.

## Human Gates

- Mudança material de composição visual → parar; exige revisão 2 do DAP.

## Reporting

Terminar com o `BUILD REPORT` completo de `docs/engineering-os/agents/builder.md`,
todos os campos, `none` onde vazio, incluindo o roteiro manual executado do critério 3.
