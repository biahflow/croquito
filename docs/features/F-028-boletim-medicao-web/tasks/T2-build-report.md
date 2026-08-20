# T2 — BUILD REPORT

Relatório do Builder para o [Task Contract T2](T2-etapa-web.md) da
[F-028](../feature.md), executado sobre o [Design Approval Package aprovado
(rev. 1)](../mock/README.md). Worktree `croquito-f025`, branch `f-025-boletim-web`, sem
commit — o diff está na árvore, ao lado do de T1 (rotas) e do de T3 (e2e), que não foram
tocados.

```text
BUILD REPORT

Status: BUILD_COMPLETE

Files changed:
  - apps/web/src/medicao/etapas.ts
    `EtapaId` ganha "aprovacao" depois de "boletim" (título "Aprovação e exportação");
    `derivarEtapas` deriva os três estados da etapa nova lendo `approved` e `stale`
    JUNTOS; a frase antecipatória "Medição gravada nesta rodada, sem aprovação." sai.
  - apps/web/src/medicao/api.ts
    `ApprovalState` e `RoundStateBulletin` (bloco de aprovação + planilha publicada);
    `BulletinResponse` ganha `approval`/`workbook_present`/`workbook_sha256`/
    `workbook_url`; `postApprove` e `postBulletinExport`, ambos só com `base_version`.
  - apps/web/src/medicao/errors.ts
    `isForbidden`, `isWorkbookAuditFailure`, `workbookAuditFindings` (molde de
    `orcamento/errors.ts`), `exportBlockedViolations` + tipo `ExportViolation` (separa
    `CODIGO:parte:parte` da lista de `VALUATION_EXPORT_BLOCKED`); `recusaDeMutacao` ganha
    o campo `auditoria`.
  - apps/web/src/medicao/labels.ts
    Traduções dos 9 códigos do portão pedidos no contrato + 9 códigos de achado da
    auditoria (`CELL_*`, `SHEET_*`, `CATALOG_*`); `violationDetailLine` (nomeia as partes
    que o domínio escreve depois do código); constantes `MENSAGEM_APROVACAO_CADUCA`,
    `MENSAGEM_MEDICAO_APROVADA`, `AVISO_EXPORTACAO_FAIL_CLOSED`,
    `MENSAGEM_AUDITORIA_REPROVADA`, `MENSAGEM_SEM_ACESSO`.
  - apps/web/src/medicao/MedicaoApp.tsx
    Componentes novos `AtoDeAprovacao` (dois atos explícitos), `RegistroDaAprovacao`
    (registrada e caduca, com os dois digests), `ProgressoExportacao` (quatro passos
    escritos), `TelaAuditoriaReprovada` e `PainelSemAcesso` (403 sem nomear papel);
    handlers `aprovarMedicao` e `exportarBoletim`; a seção da etapa nova; o toast do
    `/calc` passa a dizer o estado real da aprovação.
  - apps/web/src/medicao/styles.css
    Composições novas do pacote aprovado (`.ato*`, `.registro*`, `.digest-par`,
    `.progresso`, `.passo-estado`) e dois separadores de bloco (`.violacoes`,
    `.exportacao`) no molde de `.confirmados`. Nenhuma cor nova — os quatro hexes usados
    (#b47512, #6b3a06, #3c2708, #fbe6c2) já viviam nesta folha.
  - apps/web/src/medicao/etapas.test.ts
    Fixture do estado ganha o bloco de aprovação; testes da etapa nova.
  - apps/web/src/medicao/errors.test.ts
    403, auditoria reprovada e violações do portão.
  - apps/web/src/medicao/labels.test.ts
    Traduções novas, `violationDetailLine` e os avisos da etapa.
  - apps/web/src/medicao/api.test.ts
    Corpo e cabeçalhos das duas rotas novas; leitura do boletim com aprovação, planilha
    e URL assinada; aprovação caduca; recusa do portão.
  - apps/web/src/medicao/MedicaoApp.test.tsx
    Render estático dos cinco componentes novos, incluindo os três estados do ato.

Validation executed:
  - make check ................................................. exit 0
    ruff check/format (422 arquivos), mypy strict (194 arquivos, "Success"), check_docs
    (251 Markdown, paridade de lifecycle), schema_export --check, contracts:check,
    web:check (tsc -b && vite build, 76 módulos), terraform fmt -check.
  - npm --workspace @croquito/web run test ..................... 39 arquivos, 729 testes
    (baseline 693 → +36 testes novos), 0 falhas.
  - make test .................................................. exit 0
    pytest: 1709 passed, 13 skipped. vitest: 39 arquivos, 729 testes.
  - npx tsc -b apps/web ........................................ exit 0

  BASELINE (árvore com o diff de T1, antes de qualquer edição minha):
  `npm --workspace @croquito/web run test` = 39 arquivos, 693 testes, 0 falhas — medido
  nesta execução. `make check` e `make test` verdes com T1, conforme declarado no handoff
  e reconfirmados ao final. Nenhuma reprovação preexistente; nenhuma reprovação nova.
  O pytest final tem 1709 e não 1708 porque a T3 (paralela, `tests/e2e/`) integrou o
  teste dela na árvore durante esta execução — não é meu, e nenhum arquivo fora de
  `apps/web/src/medicao/` foi tocado por mim.

Validation skipped: none

Unavailable capabilities: none

Assumptions:
  - O contrato entre T1 e T2 é o bloco `approval` publicado no `GET .../bulletin` e no
    estado da rodada; a tela nunca deriva aprovação por conta própria e nunca decide
    autorização — ela espelha.
  - `current_digest` (conteúdo, exclui a aprovação) e `valuation_sha256` (documento
    gravado) são digests DIFERENTES no payload real. A tela mostra o do conteúdo, porque
    é ele que a aprovação amarra; no mock os dois aparecem como o mesmo número.
  - Sem biblioteca de interação no projeto (só `renderToStaticMarkup`), o fluxo dos dois
    atos é provado renderizando os três estados do componente `AtoDeAprovacao`
    (repouso / confirmação pedida / gravando), não por clique.

Remaining risks:
  - Planilha publicada por uma revisão anterior continua com `workbook_present: true`
    depois de um recálculo. A tela não oferece o download (a aprovação está caduca e o
    bloco de exportação nem é renderizado), mas também não diz que existe arquivo velho
    na rodada. Declarado, não implementado — é copy/desenho novo.
  - `ERROR_MESSAGES.FORBIDDEN` da jornada de medição continua nomeando "orçamentista",
    enquanto a etapa nova usa a mensagem sem papel do pacote aprovado. As duas convivem;
    unificá-las é decisão de copy, fora de escopo.

Human decisions required:
  - **FDD e VAL-05 não foram atualizados.** `apps/web/AGENTS.md` manda que mudança de
    comportamento na jornada de medição atualize a seção de medição do FDD e os critérios
    VAL-*, e nenhum Task Contract da F-028 recebeu esse escopo (T1 ficou com o
    API_CONTRACT; T2 tem lista fechada que não inclui docs de produto). Não ampliei o
    escopo em silêncio: fica como ato pendente da feature, junto com ROADMAP/STATUS.
  - Copy final da etapa (todo texto do pacote é rascunho declarado) — lista abaixo.
  - Revisão linha a linha do desvio 1 (a observação do mock não existe na tela, porque a
    rota de T1 não aceita nota).
```

## Desvios conscientes do desenho aprovado

O pacote é vinculante na COMPOSIÇÃO; o texto é rascunho e o próprio README declara que
"ordem de foco, navegação por teclado, rótulos para leitor de tela e o comportamento de
espera enquanto a exportação corre" são da implementação. Os desvios abaixo são de
conteúdo, não de composição.

1. **Não há campo de observação.** O mock desenha um `textarea` "Observação (opcional)"
   no ato e uma linha "Observação" no registro. `ApproveValuationRequest` (T1) recusa
   qualquer campo além de `base_version`, e a própria docstring declara por que a nota não
   entra. Um campo que não viaja prometeria um efeito jurídico que ele não tem — a tela
   não o oferece.
2. **O registro não mostra `decision_id`.** O bloco `approval` do payload publica
   `approved`, `approved_by`, `approved_at`, `approved_digest`, `current_digest` e
   `stale`; o id da decisão não sai da API. Mostrar o que não veio exigiria inventá-lo.
3. **Os quatro passos não progridem sozinhos.** Eles correm dentro de uma chamada só, e o
   cliente não observa em qual o servidor está. O que a tela sabe é o DESFECHO, e é o que
   ela diz: "no servidor" nos quatro enquanto a chamada está em voo; "feito" nos quatro
   quando publicou; "feito / feito / reprovado / não iniciado" quando a auditoria recusou.
   Fingir a progressão do mock seria inventar estado.
4. **A tabela da auditoria reprovada tem código e frase, não aba/célula/esperado/
   encontrado.** A rota devolve só `finding_codes` — decisão de T1, para não publicar
   preço, quantidade e total da obra numa mensagem de erro. A tela declara essa ausência
   por extenso em vez de deixar colunas vazias parecendo defeito.
5. **O 403 sem nomear papel vale na etapa nova.** `PainelSemAcesso` e `MENSAGEM_SEM_ACESSO`
   seguem o pacote; a tradução `FORBIDDEN` do resto da jornada (que cita "orçamentista")
   é texto pré-existente coberto por teste, e copy definitiva está fora de escopo.
6. **O resumo da etapa mostra o digest do CONTEÚDO.** No payload real ele difere do
   `valuation_sha256` do documento gravado; usar o do documento faria o número do resumo
   não bater com o do ato e com o do registro.
7. **CSS.** As composições novas do pacote entraram na folha da medição; além delas, dois
   separadores de bloco (`.violacoes`, `.exportacao`) com a mesma regra de `.confirmados`,
   porque o painel da etapa concentra o que o mock desenhou em painéis separados.

## Testes novos e o que cobrem

| Arquivo | Teste | O que prova |
|---|---|---|
| `etapas.test.ts` | etapa nova depois de Boletim, com o título aprovado | posição e nome da etapa |
| `etapas.test.ts` | sem medição montada, bloqueada com motivo escrito | bloqueio herda a linguagem da jornada |
| `etapas.test.ts` | bloqueio de etapa anterior é herdado, não reescrito | motivo não é inventado |
| `etapas.test.ts` | montada e não aprovada pede o ato | estado inicial |
| `etapas.test.ts` | aprovada sem planilha continua "em aberto" | aprovar é metade do fechamento |
| `etapas.test.ts` | aprovada com planilha conclui a etapa | fechamento |
| `etapas.test.ts` | **caduca com `approved` e `stale` verdadeiros ao mesmo tempo** | ler só `approved` declararia concluída uma medição que a exportação recusa |
| `etapas.test.ts` | Boletim não fala mais de aprovação | a frase antecipatória saiu |
| `errors.test.ts` | `isForbidden` por código e por status | 403 tem tela própria |
| `errors.test.ts` | auditoria é desfecho próprio, e só os códigos viajam | nada de dinheiro do cliente em erro |
| `errors.test.ts` | `exportBlockedViolations` separa código e partes, na ordem | o portão recusa por todas de uma vez |
| `errors.test.ts` | recusa que não é do portão não vira violação inventada | fail-closed de leitura |
| `labels.test.ts` | todo código do portão e da auditoria tem frase própria | nenhum código cru na tela |
| `labels.test.ts` | nenhuma frase oferece "mesmo assim" | não existe exportar sem aprovar |
| `labels.test.ts` | `violationDetailLine` nomeia as partes; parte sem rótulo sai como veio | sem adivinhação |
| `labels.test.ts` | o 403 da etapa não nomeia papel | decisão de copy não tomada |
| `api.test.ts` | as duas rotas mandam só `base_version` + `Idempotency-Key` | identidade nunca viaja |
| `api.test.ts` | a leitura traz aprovação, planilha e URL assinada; a mutação não | credencial só na leitura |
| `api.test.ts` | aprovação caduca com os dois digests divergentes | contrato T1↔T2 |
| `api.test.ts` | recusa do portão traz `details.errors` | lista de violações |
| `MedicaoApp.test.tsx` | ato em repouso: consequência ANTES do botão (índice no HTML) | ordem, não intenção |
| `MedicaoApp.test.tsx` | identidade mostrada, nenhum `<input>`/`<textarea>` no ato | critério 3 da feature na tela |
| `MedicaoApp.test.tsx` | segundo ato repete a consequência e é o único que confirma | dois atos explícitos |
| `MedicaoApp.test.tsx` | gravando desabilita os dois botões | estado do mock |
| `MedicaoApp.test.tsx` | registro: nunca aprovada não inventa registro | sem fabricação |
| `MedicaoApp.test.tsx` | registro caduco: palavra, dois digests, código, sem "mesmo assim" | estado caduco completo |
| `MedicaoApp.test.tsx` | progresso em voo não finge saber o passo | honestidade de espera |
| `MedicaoApp.test.tsx` | auditoria reprovada diz "nada foi publicado" e não mostra R$ | tela, não rodapé |
| `MedicaoApp.test.tsx` | 403 sem nomear papel | transversal |

## Oportunidades vistas e NÃO implementadas (fora de escopo)

- **FDD / ACCEPTANCE_CRITERIA (VAL-05) / ROADMAP / STATUS** — a feature muda o que o
  produto entrega, e a disciplina do repositório pede a atualização; nenhum Task Contract
  da F-028 a recebeu. Listada acima como decisão humana pendente.
- **Unificar a mensagem de `FORBIDDEN` da medição** com a decisão do pacote (não nomear
  papel) — é copy definitiva e mexe em texto coberto por teste na jornada inteira.
- **Declarar a planilha velha** quando a aprovação caduca depois de uma exportação: hoje a
  tela apenas não a oferece.
- **Reprovar a medição** (`action: "reject"`): o domínio aceita, o produto não desenha, e
  nada foi escrito como "reservado" — a tela só sabe ler uma decisão de recusa que o CLI
  tenha escrito, e a mostra como registro sem aprovação.
