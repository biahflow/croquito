# ADR-0041: Decisão de ator-máquina no fluxo de revisão — atrás de flag local, com proveniência inconfundível

Status: Accepted  
Data: 2026-08-21 (aceito por ato humano na mesma data)  
Responsável: Product / Engineering

## Contexto

O invariante central do pipeline é fail-closed: leitura sem decisão completa
retorna `review_required` e não cria cena métrica; o solver exige associação
explícita `reading_id → proposal_id` mesmo para leitura confirmada. Hoje 100%
das leituras exigem toque humano duplo (decisão + associação), e a
[F-029](../features/F-029-auto-associacao-confianca/feature.md) — decisão de
produto do usuário em 2026-08-21 — quer testar localmente a tese "confiança
alta → cota entra sem toque humano", medindo antes (shadow + calibração com
os sete levantamentos reais) e só então ligando.

O modelo de decisão atual é `HumanDecision`
(`services/worker/src/croquito_worker/review.py:72-97`): `action`
confirm/reject, `reviewer_id`, `reviewer_role`
(`Literal["engineer","architect","domain_reviewer"]`, sempre derivado do JWT
em `main.py:_reviewer_role`, nunca do body), `decided_at` timezone-aware,
retificação por `rectifies_decision_id` (ADR-0022). A pergunta deste ADR:
**que forma tem uma decisão que não foi tomada por uma pessoa**, sem
enfraquecer proveniência, retificação nem o portão de export.

## Decisão

1. **Campo discriminador aditivo, não tipo novo.** O modelo de decisão ganha
   `actor: Literal["human", "system"]` com default `"human"`. Toda decisão já
   persistida permanece válida sem migração de dados; todo consumidor que não
   conhece o campo continua funcionando. O nome da classe não muda nesta
   rodada (renome é churn de contrato sem ganho semântico; o campo é a
   semântica).
2. **Decisão de sistema tem identidade estável e versionada — e não tem
   papel profissional.** `actor="system"` exige `reviewer_id` no formato
   `system:auto-association@<versão do score>` e `decided_at` do servidor.
   `reviewer_role` vira condicional: obrigatório quando `actor="human"`
   (semântica atual intacta), **proibido** quando `actor="system"`. Papel
   profissional é atributo de pessoa, derivado do JWT; sistema tem
   identidade e versão, não papel — fabricar um papel para a máquina
   contaminaria toda autorização que itera papéis.
3. **Sistema só confirma; nunca rejeita, nunca retifica.** `actor="system"`
   é válido apenas com `action="confirm"` e `rectifies_decision_id=None`.
   Rejeitar uma leitura e corrigir uma decisão são julgamentos humanos.
   A recíproca vale: humano retifica decisão de sistema pelo caminho
   existente do ADR-0022, sem mudança de contrato.
4. **Sistema nunca sobrescreve nem redecide.** Auto-decisão só nasce sobre
   leitura sem decisão alguma. `READING_ALREADY_DECIDED` cobre o sistema
   como cobre gente.
5. **Dupla chave para existir.** Decisão de sistema só pode ser criada
   quando `CROQUITO_AUTO_ASSOCIATION_ENABLED=true` (leitura estrita;
   ausente = desligado — ligar é ato declarado) **e**
   `CROQUITO_AUTO_ASSOCIATION_THRESHOLD` explícito (0–1, sem default no
   código: o threshold operacional é escolhido por humano a partir do
   relatório de calibração). Flag ligada sem threshold é erro de
   configuração, nunca um valor inventado. A `note` da decisão registra
   threshold vigente e as duas confianças no momento do ato.
6. **Proveniência atravessa até o papel.** Toda resposta de API que exibe a
   decisão exibe o ator; a auditoria do export (`auditoria.json`) lista
   nominalmente cada leitura auto-decidida com valor, associação,
   confidências e threshold. O portão `SceneRevision.export_errors()` não
   muda: o que muda é quem pode ter autoria de uma decisão, nunca o que uma
   cena precisa ter para exportar.
7. **Escopo de ambiente é contratual.** Nesta feature a flag só é ligada em
   ambiente local (docker-compose). Nenhum manifesto de deploy a inclui;
   ligar em ambiente hospedado exige decisão humana futura e revisão deste
   ADR.

## Alternativas

- **Tipo irmão `AutoDecision`** — rejeitada: duplicaria o tratamento em
  validação de estado, solver, API, retificação e telas; dois tipos para o
  mesmo lugar semântico ("a leitura foi decidida") é exatamente a divergência
  que o discriminador evita.
- **Valor novo em `reviewer_role` (ex. `"system_auto"`)** — rejeitada:
  conflacionaria papel profissional (atributo de pessoa, derivado do JWT)
  com natureza do ator; todo código que itera papéis para autorização
  passaria a precisar excluir o sistema.
- **Auto-decisão como "sugestão pré-aceita" sem decisão persistida**
  (a tela confirmaria em lote) — rejeitada para o experimento: é o desenho
  da F-010 (pré-aceite por tripla concordância) e não testa a tese que o
  usuário quer validar — a cota entrar sem toque humano. A F-010 permanece
  como caminho alternativo se a calibração reprovar a tese.
- **Threshold com default de fábrica** — rejeitada: um número de corte sem
  base nos dados reais é exatamente o tipo de decisão silenciosa que o
  fail-closed existe para impedir.

## Consequências

- Mudança de contrato OpenAPI (campo `actor` nas respostas que carregam
  decisão) com snapshot regenerado deliberadamente; o scene schema
  (`croquito_core.models`) não muda, salvo se a listagem nominal da
  auditoria exigir campo novo em `Provenance` — nesse caso `make contracts`
  entra com justificativa no BUILD REPORT (risco previsto no plano da
  F-029).
- `reviewer_role` passa de obrigatório a condicional no modelo de decisão —
  validação nova cobre os dois ramos; nenhum dado persistido viola o modelo
  novo (todo registro existente é `actor="human"` por default com papel
  presente).
- O experimento fica reversível por natureza: flag desligada = comportamento
  bit a bit de hoje; auto-decisões persistidas permanecem legíveis e
  retificáveis como qualquer decisão.
- Aceite deste ADR é gate de entrada do T4 do
  [plano da F-029](../features/F-029-auto-associacao-confianca/plan.md).
