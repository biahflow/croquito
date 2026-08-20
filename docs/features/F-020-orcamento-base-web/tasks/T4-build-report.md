# T4 — BUILD REPORT

Formato canônico da Engineering OS ([`agents/builder.md`](../../../engineering-os/agents/builder.md)).
Este documento é `PRIMARY_EXECUTION_EVIDENCE` da task T4 da feature F-020.

```text
BUILD REPORT

Status: BUILD_COMPLETE
```

## Files changed

Árvore: `f-020-orcamento-web` (worktree isolado), sem commit — o diff fica na árvore.

### Casca e fronteira de jornadas (alterados)

| Arquivo | Por quê |
| --- | --- |
| `apps/web/src/route.ts` | `Route` ganha `{kind: "orcamento"; roundId: string \| null}` e `ORCAMENTO_PARAM = "orcamento"`; precedência documentada e implementada passa a `job > rodada > orcamento > plataforma`. `entryRedirect` intocado. |
| `apps/web/src/App.tsx` | Terceiro botão do seletor (`aria-current`), `ORCAMENTO_ROOT`, `handleOpenEstimate` (escreve `?orcamento=<id>` com `replaceState`) e o ramo de render de `OrcamentoApp` no switch de `route.kind`. |
| `apps/web/src/styles.css` | Uma linha: `@import "./orcamento/styles.css";` ao lado do import da folha da medição — sem ela a folha da jornada nova é código morto. Desvio declarado abaixo. |
| `apps/web/src/route.test.ts` | Precedência com o parâmetro novo, forma canônica e round-trip. |
| `apps/web/src/App.test.tsx` | Terceiro botão no seletor, `aria-current` da jornada nova, e a asserção de ausência de casca sem sessão passa a citar o botão pela forma exata (`>Orçamento<`). |

### Jornada nova (`apps/web/src/orcamento/`, criados)

| Arquivo | Por quê |
| --- | --- |
| `api.ts` | Cliente das 17 rotas `/v1/estimate-rounds*` que T3 publicou. Tipos de domínio importados de `@croquito/contracts` (`Estimate`, `TakeoffPacket`, `CodeSuggestionSet`, `CodeAssignmentSet`); escrito à mão só o envelope da API. |
| `requests.ts` | Construtores puros de corpo: `base_version` sempre, identidade/carimbo nunca, campo vazio omitido, `catalog_sha256` na confirmação e proibido na rejeição, `bdi_percent` só como string decimal. |
| `format.ts` | Exibição pt-BR sem aritmética e `parseDecimalInput` (notação, nunca valor). Cópia deliberada de `medicao/format.ts` — jornadas não se importam entre si. |
| `etapas.ts` | Etapas como espelho do estado servido pela rodada (cascata → prancha → revisão → códigos → montagem → planilha), com o motivo do bloqueio em língua de obra. |
| `cascata.ts` | Reordenação como permutação COMPLETA (a rota exige a lista inteira) e resolução da fonte citada por digest. |
| `labels.ts` | Tradução por tabela dos códigos estáveis, incluindo os novos (`ESTIMATE_CASCADE_*`, `ESTIMATE_LINE_*`, `ASSIGNMENT_CATALOG_*`, `ESTIMATE_WORKBOOK_AUDIT_FAILED`), rótulos de origem/posição e a linha fixa da jornada. |
| `errors.ts` | Classificação das recusas: `409` com banner próprio, `403` com tela própria, auditoria reprovada como tela, `AbortError` que não é falha de rede. |
| `overlay.ts` | Idade do overlay em palavra (ADR-0030). Cópia deliberada de `medicao/images.ts`. |
| `OrcamentoApp.tsx` | As telas e estados do pacote aprovado, com `SeloFonte`, `SemPrecoNaCascata`, `EstadoExtracao`, `OverlayDoTakeoff`, `BannerOrcamentoMudou`, `PainelSemAcesso` e `TelaAuditoriaReprovada` exportados para teste. |
| `styles.css` | Composição sobre os tokens e classes existentes, aninhada em `.jornada-orcamento`. Zero cor nova (prova abaixo). |

### Testes novos (criados)

| Arquivo | O que cobre |
| --- | --- |
| `orcamento/api.test.ts` (18) | Caminho de cada rota sob `/v1/estimate-rounds`, `Bearer` sem `Idempotency-Key` na leitura e com ele na mutação, `base_version` em toda mutação, ausência de carimbo de identidade, ausência de `arm` na busca, corpo de abertura sem catálogo/período/contrato, cascata completa na reordenação, `catalog_sha256` na confirmação e ausente na rejeição, BDI como string, `409` e código de domínio dentro de `DOMAIN_VALIDATION_FAILED`. |
| `orcamento/errors.test.ts` (24) | Tradução de 13 códigos novos, código desconhecido devolvido como veio, `403` sem nome de papel, achados da auditoria só como códigos, `409` com banner próprio, `AbortError`. |
| `orcamento/etapas.test.ts` (13) | Espelho do estado do servidor por etapa, ordem da cascata no resumo, motivo da extração (`queued`/`failed`) por `failure_code`, bloqueio de códigos/montagem por pendência, e a diferença entre `estimate.present` e `workbook_present`. |
| `orcamento/cascata.test.ts` (7) | A ordem nova é sempre permutação completa; movimento inexistente devolve `null` (nunca ordem parcial); fonte fora da cascata é `null`. |
| `orcamento/requests.test.ts` (15) | Corpos puros: omissão de vazio, ausência de carimbo, confirmação com fonte, rejeição sem fonte, BDI em string com escala preservada e round-trip textual da formatação. |
| `orcamento/OrcamentoApp.test.tsx` (14) | SSR estático sem sessão e sem orçamento aberto (nenhum dado fabricado), linha fixa da jornada, selo de fonte escrito, item sem preço declarado, banner de `409`, `403` sem papel, auditoria reprovada como tela sem valor de célula, e ausência total do BDI por grupo. |

## Validation executed

| Portão | Comando | Resultado |
| --- | --- | --- |
| Baseline (antes da mudança) | `make check` | exit 0 |
| Baseline (antes da mudança) | `npm --workspace @croquito/web run test` | exit 0 — 682 testes |
| lint + format + typecheck + docs + contratos + build web + terraform fmt | `make check` | **exit 0** — `ruff: All checks passed`; `397 files already formatted`; `mypy: Success: no issues found in 193 source files`; `check_docs: 227 arquivos Markdown, paridade de lifecycle verificada`; `schema_export --check` e `contracts:check` sem drift; `tsc -b && vite build ✓ built in 529ms`; `terraform fmt -check` limpo |
| unit web | `npm --workspace @croquito/web run test` | **exit 0** — 38 arquivos, **683 testes** (91 novos nesta task) |
| unit+integration Python e web | `make test` | **exit 0** — `1690 passed, 13 skipped` (pytest) + 683 (vitest) |

Nenhuma reprovação em área não tocada; nenhuma falha preexistente encontrada no baseline.

Prova mecânica do critério de aceite 3 (nenhuma cor nova):

```bash
comm -23 <(grep -ohE '#[0-9a-fA-F]{3,8}|rgba?\([^)]*\)' orcamento/styles.css | sort -u) \
         <(grep -ohE '#[0-9a-fA-F]{3,8}|rgba?\([^)]*\)' styles.css medicao/styles.css | sort -u)
# saída vazia
```

## Validation skipped

`make smoke-local` e `npm --workspace @croquito/web run smoke:headless` — declarados no repositório
como locais e fora do CI, exigem stack Docker (PostgreSQL, LocalStack, Keycloak) que esta execução
não subiu. Não estavam na seção `Validation` do Task Contract.

## Unavailable capabilities

`COMMIT` — o contrato o retira explicitamente ("Sem COMMIT: deixe o diff na árvore"). O diff está
na árvore, não commitado.

## Assumptions

1. **O botão "Orçamento" é incondicional**, como Croqui e Medição. O contrato pede "padrão dos
   existentes"; o pacote aprovado registra que **qual papel autoriza a jornada é decisão humana
   ainda aberta**. Esconder o botão exigiria escolher um papel — decisão que um agente não pode
   tomar. Consequência aceita e declarada: quem não tem o papel vê o botão e lê o `403` traduzido,
   que é o mesmo desenho já adotado para `?plataforma=` ("a jornada é montada pela rota, não pelo
   papel"). A frase do mock "a jornada não aparece no seletor para quem não tem o papel" **não foi
   transcrita**, porque afirmaria a decisão que está aberta.
2. **`roundId: string | null`** (forma pedida pelo contrato) foi lido como: `?orcamento=` vazio →
   `null`; `?orcamento=<id>` → o id. O round-trip das duas formas canônicas está testado.
3. Toda copy é rascunho. O pacote aprovou a composição e registrou que **a copy final é gate humano
   aberto**; os textos daqui são proposta, não texto aprovado.
4. A etapa **Prancha** aparece bloqueada enquanto a cascata está vazia. O servidor **não** recusa
   associar prancha nesse estado: é ordem da jornada (a composição aprovada abre pela cascata), está
   declarada como exceção no cabeçalho de `etapas.ts` e testada como tal, e não impede ato nenhum —
   instalada a fonte, a etapa abre com a prancha já associada.

## Remaining risks

1. **Nenhuma execução contra a API real.** Toda a jornada foi verificada por teste puro e SSR
   estático; o contrato do cliente foi espelhado lendo `main.py`/`estimate_rounds.py` linha a linha,
   não trafegando bytes. A cadeia inteira contra o stack local (`make dev-services` + `make db-init`)
   continua pendente e é o próximo teste que vale a pena.
2. **Duplicação de CSS entre as duas jornadas.** `orcamento/styles.css` copia as regras da folha da
   medição porque aquela está inteira aninhada em `.jornada-medicao` e é intocável nesta task. As
   duas podem divergir sem que nenhum teste reclame; o cabeçalho do arquivo declara qual é a fonte
   (a da medição) e um fatoramento futuro das primitivas comuns resolveria a dívida.
3. **`react-hooks/exhaustive-deps` não é verificado por ferramenta**: o projeto não tem ESLint. As
   dependências dos efeitos foram conferidas à mão (o poll da extração não é reconstruído por tecla
   digitada no campo de BDI — foi defeito encontrado e corrigido na revisão do próprio diff).
4. **Zoom, pan e overlay das bboxes não foram reimplementados.** O pacote aprovado marca essas três
   coisas como fora dele ("espelho não redesenhado; vale o que a medição já faz"). A revisão do
   takeoff aqui mostra a página promovida, o overlay publicado com a idade dele em palavra
   (ADR-0030) e a decisão item a item — sem o canvas com zoom/pan da medição.

## Human decisions required

1. **Qual papel autoriza a jornada de orçamento** (reusar `orcamentista` ou criar um de
   pré-licitação). Enquanto estiver aberta, o botão é incondicional e o `403` não nomeia papel.
2. **Copy final** de toda a jornada. O gate de texto continua aberto por registro do próprio pacote
   aprovado.
3. **Conferência do layout impresso contra o exemplar real da prefeitura** — não alcançável daqui: a
   planilha é produzida pelo servidor, e esta tela só oferece a URL assinada do `.xlsx` auditado.

## Desvios conscientes do contrato

| Onde | O contrato dizia | O que foi feito | Por quê |
| --- | --- | --- | --- |
| `apps/web/src/styles.css` | O mapa de arquivos lista `route.ts`, `App.tsx`, `apps/web/src/orcamento/` e testes | Uma linha a mais: `@import "./orcamento/styles.css";` | A folha da jornada precisa ser alcançada por alguém. O `@import` é o mesmo mecanismo já usado pela medição (linha 4), e é a alteração mínima possível — sem ela o `styles.css` do diretório seria arquivo morto. |
| Etapa "Cascata" do mock | O mock desenha um botão **"Remover"** por fonte | Só "Subir" e "Descer" | T3 **não publicou rota de remoção de catálogo**. O contrato manda "não invente rota", e o pacote marca a contagem/desenho dos catálogos como ilustrativo. A recusa `ESTIMATE_CASCADE_ORIGIN_DUPLICATE` já é traduzida dizendo o caminho real (abrir outro orçamento com a fonte nova). |
| Cabeçalho da jornada | — | `reviewer_role` do estado da rodada **não é renderizado** em lugar nenhum | A decisão aprovada é "o 403 não nomeia papel, porque o papel ainda não foi decidido". Imprimir o papel no cabeçalho — como a medição faz — contornaria essa decisão pela porta dos fundos. |
| Tela 7 do mock (planilha) | Rendição em HTML do `.xlsx`, com letras de coluna e tinta verde nas colunas novas | A tela mostra as linhas recomputadas pelo servidor, o bloco de itens sem preço, os digests e o link de download | O próprio pacote declara: "isto é a rendição do `.xlsx`, não uma tela — a aprovação aqui é do layout impresso". Reproduzir a moldura do caderno no produto seria copiar o artefato de aprovação, que o pacote proíbe ("não copie este HTML"). |

## Oportunidades vistas e NÃO implementadas (fora de escopo)

1. **Fatorar as primitivas comuns das duas folhas** (`.painel`, `.cartao`, `.item`, `.selo`,
   `.banner-*`) para uma camada compartilhada, deixando cada jornada só com o que é dela. Toca
   `src/medicao/styles.css`, fora de escopo.
2. **Fatorar `format.ts` e `images.ts`/`overlay.ts`** para um módulo comum. Hoje a regra do
   `AGENTS.md` de `apps/web` é que jornadas não se importam entre si, e mudá-la é decisão de
   arquitetura, não de implementação.
3. **Rota de remoção de fonte da cascata** em `/v1/estimate-rounds/{id}/catalogs/{digest}` — hoje
   corrigir uma fonte errada exige abrir outro orçamento. É contrato de API (T3), não desta task.
4. **Zoom/pan e bboxes na revisão do takeoff do orçamento**, reusando `viewport.ts` da medição.
   Depende da oportunidade 2 e está fora do pacote aprovado.
5. **Teste de fumaça headless da terceira jornada** (`e2e/smoke-headless.mjs` com `?orcamento=`),
   provando que o deep-link sobrevive ao redirect do OIDC como o `?job` já prova. É local, nunca CI,
   e exige o stack Docker.
