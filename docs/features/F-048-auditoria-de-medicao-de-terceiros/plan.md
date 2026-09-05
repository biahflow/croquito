# F-048 — Plano de execução

feature_id: F-048
goal: uma pessoa de fora sobe uma medição de terceiro e recebe o relatório de furos — o
que não fecha, de que classe, em qual linha e por quanto —, sem precisar ter projeto,
prancha, contrato ou rodada no croquito.

Gates cumpridos antes deste plano: prioridade `HIGH` (2026-09-05), unknown 2 respondido
(**produto avulso**, 2026-09-05) e [Design Approval Package](mock/README.md) **aprovado na
revisão 1** (2026-09-05). Este plano decompõe o que aqueles artefatos decidiram; ele não
reabre nenhuma decisão deles.

## assumptions

- Os três motores existem e são determinísticos: `check_parity`
  (`services/worker/.../valuation/parity.py:343`), `compare_bulletin` +
  `read_bulletin_lines` (`bulletin_compare.py:290`, `:205`) e `diagnose_contract` +
  `read_contract_parse` (`contract_diagnosis.py:553`, `workbook_reader.py:996`). **Nenhum
  deles muda de comportamento nesta feature** — é o critério de aceite 4 do contrato.
- A auditoria é avulsa: nenhuma tarefa aqui cria projeto, prancha, contrato ou rodada.
- Nenhuma chamada paga de IA em ponto nenhum: os três motores são determinísticos.

## risks

- **A tentação de mexer no motor.** Os três já produziram achados reais e têm goldens; um
  ajuste "pequeno" para caber na jornada nova invalidaria a evidência que dá valor à
  feature. Mitigação: os motores entram como dependência, e a T2 tem teste que prova que os
  goldens seguem byte-idênticos.
- **Relatório que assusta sem informar.** O dossiê real do MAPÃO tinha 3.086 achados em 10
  classes; despejá-los cru é pior do que não auditar. Mitigação: a hierarquia por
  consequência do pacote aprovado, e a T2 só emite classe que o pacote desenhou.
- **Auditoria que não se pode reconferir.** Mitigação: T3, com digest do arquivo e
  proveniência por id (o precedente é a Emenda 1 do ADR-0060, F-042: id, não só versão).

## PLANNING_FINDING — a peça que o contrato não previu

O mapeamento do terreno encontrou **duas lacunas** entre o que o contrato assume e o que o
código faz. Nenhuma delas invalida a feature; as duas mudam o tamanho dela, e a primeira
exige decisão humana **antes do build**.

### 1 · `ARCHITECTURE_DECISION_REQUIRED` — de que layout é a planilha que entra

Os três motores exigem um `WorkbookTemplate` **obrigatório**, e nenhum adivinha layout — é
decisão de projeto, não omissão. E a API nunca recebeu um: toda chamada hospedada usa
`default_template()` (`main.py:16269`, `:16539`, `:19097`, `:14059`); um template real só
existe como JSON local passado por `--template` no CLI.

O precedente pesa: no M2.1 (2026-08-12), fazer o MAPÃO real do cliente importar **exigiu
autorar um template**, e a regra registrada foi "cada divergência do arquivo real virou
dado de template, sem exceção em código". Ou seja: planilha de terceiro com layout
desconhecido **não é lida** sem alguém descrever o layout dela.

Três caminhos, e a escolha é do dono:

| Caminho | O que entrega | O que custa |
| --- | --- | --- |
| **(a) Só o layout conhecido** | A auditoria aceita arquivos no padrão que o croquito já lê (SCO-Rio/prefeitura). Serve ao mercado-alvo, onde o layout se repete entre obras | Recusa arquivo de layout novo — e a recusa precisa dizer isso por extenso, não "arquivo inválido" |
| **(b) Template como artefato de plataforma** | Qualquer layout, com um template autorado por cliente e publicado como o acervo da F-037 | Feature própria: rota, tabela, tela e o ofício de autorar template |
| **(c) Descobrir o layout** | Nada a autorar | Contradiz a decisão de projeto dos leitores e produz achado errado em silêncio — **não recomendado** |

**Recomendação: (a) nesta fatia, com (b) declarado como fatia seguinte.** A frase do
contrato — "alcança quem ainda não é cliente" — continua verdadeira para quem trabalha no
mesmo padrão de prefeitura, que é o mercado que a estratégia comercial nomeia. O plano
abaixo assume (a); se o dono escolher (b), a T1 muda de tamanho e uma tarefa nova entra.

### 2 · O comparador não serve ao avulso como está

`compare_bulletin` compara um `Valuation` **gerado pelo croquito** contra um
`ReferenceBulletin` lido de planilha — e `ContractWorkbook` e `ReferenceBulletin` nunca são
usados juntos em lugar nenhum do código. No modo avulso não existe `Valuation`.

Isso **não** é bloqueio: é a T1. A correção que a revisão do pacote de design já aplicou
("a comparação avulsa é entre as camadas do próprio arquivo") vira código aqui — ler o
consolidado (MAPÃO) e o boletim (BM) do mesmo arquivo e confrontá-los. O que não existe é
essa função; os dois leitores existem.

Consequência declarada: `read_bulletin_lines` **exige o nome da aba do BM** como argumento
humano, sem heurística. Sob o caminho (a), o nome vem do template; sob (b), do template
autorado. Em nenhum dos dois o sistema adivinha.

## tasks

  - id: T1
    role: builder
    goal: ler as duas camadas do arquivo do cliente e confrontá-las — a função que não existe
    scope: |
      Módulo novo em `packages/valuation/src/croquito_valuation/` que recebe o caminho da
      planilha e o template, lê o consolidado (`read_contract_parse`) e o boletim
      (`read_bulletin_lines`) do MESMO arquivo, e devolve as divergências entre as duas
      camadas nas classes que `BulletinComparisonReport` já define (código de um lado só,
      quantidade, preço unitário, total de linha, total da obra, nota de unidade).
    out_of_scope: |
      Alterar `compare_bulletin`, `read_bulletin_lines` ou `read_contract_parse`. Rota, API,
      persistência e tela. Qualquer heurística de descoberta de aba ou de layout.
    expected_areas: packages/valuation/src/croquito_valuation/, tests/valuation/
    acceptance_criteria: |
      1. Um arquivo sintético com MAPÃO e BM coerentes devolve "fecha centavo a centavo".
      2. Cada uma das classes de divergência é produzida por um caso próprio.
      3. Arquivo sem a aba do BM recusa com o motivo nomeado, nunca com relatório vazio.
      4. Os goldens de `bulletin_compare` seguem byte-idênticos.
    depends_on: []
    validation: pytest (tests/valuation), make check
    required_capabilities: READ, WRITE, VALIDATE
    risk: a fronteira com `compare_bulletin` — reusar sem alterar exige disciplina
    relative_effort: M

  - id: T2
    role: builder
    goal: o motor da auditoria, que orquestra os três e emite o relatório desenhado
    scope: |
      `AuditReport` como modelo de domínio, com as três classes POR CONSEQUÊNCIA do pacote
      aprovado (dinheiro que não fecha, linha de um lado só, observação) e o veredito
      `zero_cent`. Orquestra `check_parity` + a comparação da T1 + `diagnose_contract`,
      mapeando cada achado técnico para a classe que o pacote desenhou.
    out_of_scope: |
      Classe de achado nova; classificar intenção; tolerância (a comparação é exata);
      corrigir a medição alheia.
    expected_areas: packages/valuation/src/croquito_valuation/, tests/valuation/
    acceptance_criteria: |
      1. O relatório reproduz os achados que os três motores produzem hoje sobre o mesmo
         arquivo, sem inventar nem omitir nenhum.
      2. Arquivo limpo devolve `zero_cent` com a contagem do que foi conferido.
      3. Nenhum motor existente muda de comportamento (goldens byte-idênticos).
      4. `diagnose_contract` passa a ser chamado como diagnóstico SOLICITADO — hoje ele só
         roda como efeito colateral de uma recusa de importação.
    depends_on: [T1]
    validation: pytest, make check
    required_capabilities: READ, WRITE, VALIDATE
    risk: mapear achado técnico para classe de consequência é onde a tradução pode mentir
    relative_effort: M

  - id: T3
    role: builder
    goal: o relatório como artefato reconferível
    scope: |
      Tabela e persistência do relatório com: digest do arquivo auditado, id e nome do
      upload, quem subiu, quando, e o veredito. Proveniência por **id**, não só por rótulo
      ou versão — o precedente é a Emenda 1 do ADR-0060.
    out_of_scope: Rotas, tela, exportação do relatório.
    expected_areas: services/api/src/croquito_api/database.py, migrations/, tests/api/
    acceptance_criteria: |
      1. Reauditar o mesmo arquivo produz o mesmo relatório.
      2. O registro carrega digest, autor e instante; nenhuma coluna deriva de conteúdo de
         cliente (mesmo teste-guarda de `test_reference_catalogs.py`).
      3. Migração forward-only, sem linha migrada.
    depends_on: [T2]
    validation: pytest (tests/api), test_migrations, make check
    required_capabilities: READ, WRITE, VALIDATE
    risk: dado de cliente entrando em coluna indexada
    relative_effort: S

  - id: T4
    role: builder
    goal: as rotas `/v1` da jornada avulsa
    scope: |
      Presign + confirm por digest (molde de `/v1/surveys/.../media`), disparar a auditoria,
      ler o relatório e listar o histórico. Papel próprio, com a decisão de gate que o
      `PLANNING_FINDING` 3 registra.
    out_of_scope: Tela; exportação; qualquer vínculo com projeto/rodada.
    expected_areas: services/api/src/croquito_api/main.py, tests/api/, docs/architecture/API_CONTRACT.md
    acceptance_criteria: |
      1. A jornada inteira funciona sem projeto, prancha, contrato ou rodada.
      2. Arquivo ilegível ou de layout não suportado recusa com motivo por extenso.
      3. Snapshot OpenAPI atualizado; erros com código estável em `problem+json`.
    depends_on: [T3]
    validation: pytest (tests/api), snapshot OpenAPI, make check
    required_capabilities: READ, WRITE, VALIDATE
    risk: acoplar sem querer a uma das três jornadas existentes
    relative_effort: M

  - id: T5
    role: builder
    goal: a tela dos seis estados aprovados
    scope: |
      Jornada nova em `apps/web` (rota, componente e o gate decidido no achado 3), com os
      seis estados do pacote aprovado — inclusive o relatório limpo com o mesmo peso do
      relatório com furos, e a recusa com o motivo por extenso.
    out_of_scope: Redesenhar o que o pacote aprovou; copy final (é gate à parte).
    expected_areas: apps/web/src/, tests do vitest
    acceptance_criteria: |
      1. Os seis estados existem e correspondem ao pacote aprovado.
      2. Cor nunca é o único indicador de classe.
      3. A tela nunca classifica intenção do achado.
    depends_on: [T4]
    validation: vitest, npm run build, make check
    required_capabilities: READ, WRITE, VALIDATE
    risk: `App.tsx` e o roteamento são vivos; a jornada nova não pode mexer nas três atuais
    relative_effort: M

  - id: T6
    role: builder
    goal: exportar o relatório
    scope: O relatório como arquivo que o cliente manda adiante, com digest e proveniência.
    out_of_scope: Formato definitivo se o dono quiser outro; assinatura do documento.
    expected_areas: packages/valuation/, services/api/, apps/web/
    acceptance_criteria: |
      1. O arquivo exportado carrega os mesmos achados que a tela mostra.
      2. Exportar não muda estado nem dispara chamada paga.
    depends_on: [T5]
    validation: pytest, vitest, make check
    required_capabilities: READ, WRITE, VALIDATE
    risk: baixo
    relative_effort: S

  - id: T7
    role: builder
    goal: e2e da jornada e a evidência de navegador
    scope: |
      e2e da cadeia inteira pelas rotas reais (subir → auditar → ler → exportar) e a
      validação `BROWSER_REQUIRED` dos seis estados contra o stack local.
    out_of_scope: Rodada contra arquivo real de cliente (é o aceite, ato humano).
    expected_areas: tests/e2e/, docs/features/F-048-.../evidence.md
    acceptance_criteria: |
      1. e2e verde pelas rotas reais, sem provider pago.
      2. Os seis estados capturados no navegador, com dado sintético.
    depends_on: [T6]
    validation: pytest (tests/e2e), Playwright, make check e make test
    required_capabilities: READ, WRITE, VALIDATE
    risk: baixo
    relative_effort: M

parallel_groups: nenhum. A cadeia é sequencial por dependência real de dado — T1 produz o
que T2 orquestra, T2 produz o que T3 grava, e assim adiante. Forçar paralelismo aqui
criaria interface inventada entre tarefas que ainda não sabem o que trocam.

critical_path: T1 → T2 → T3 → T4 → T5 → T6 → T7 (é a cadeia inteira; esforço relativo
M, M, S, M, M, S, M).

integration_strategy: uma branch por tarefa, PR por tarefa, na ordem da cadeia. Nenhuma
tarefa toca os três motores; a T4 é a única que mexe em `main.py`, e a T5 a única que mexe
no roteamento da web.

human_gates:
  - **Antes do build**: a decisão do `PLANNING_FINDING` 1 — de que layout é a planilha que
    entra (caminho a, b ou c). O plano assume (a); (b) muda o tamanho da T1 e acrescenta
    tarefa.
  - **Antes da T4**: a decisão do `PLANNING_FINDING` 3 — se a auditoria é a quarta jornada
    (entra no mecanismo da F-034) ou fica fora de jornada, gated por papel, como
    `/v1/platform` e `/v1/surveys`. Hoje `Journey` é um `Literal` de três valores no
    servidor e na web.
  - **Ao fim**: o aceite, com o arquivo real de um cliente — é o que transforma "o mecanismo
    funciona" em "achou dinheiro errado de verdade".

planning_findings: os dois achados acima, mais o terceiro registrado no gate: não existe
quarta jornada hoje, e `Journey` é `Literal["croqui","medicao","orcamento"]` no servidor
(`journeys.py:23`) e na web (`plataforma/api.ts:40`). A alternativa sem tocar nisso é o
padrão de `/v1/surveys` — fora da lista de jornadas, gated só por papel.
