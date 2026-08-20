# T2 — BUILD REPORT

Task Contract: [T2-teto-web.md](T2-teto-web.md) · Plano: [plan.md](../plan.md) ·
Harness: Claude Code (Opus 5) · Árvore: `croquito-specs`, branch `f-027-especificacao`,
sem commit.

```text
BUILD REPORT

Status: BUILD_COMPLETE

Files changed:
  - apps/web/src/orcamento/teto.ts (novo, 154 linhas) — derivação pura do bloco do teto:
    estado a partir de `over`, restante/excedente como texto do servidor e o percentual
    (único número calculado na tela) em `BigInt`, truncado na segunda casa
  - apps/web/src/orcamento/teto.test.ts (novo, 161 linhas) — 15 testes do módulo puro
  - apps/web/src/orcamento/api.ts (+90/-4) — `EstimateTarget`, `EstimateTargetState`
    (quatro chaves OPCIONAIS), `target_amount`/`target_label` na listagem, bloco no
    `EstimateState` e no `EstimateResponse`, `postTarget` com recusa local
  - apps/web/src/orcamento/requests.ts (+85/-4) — `tetoAmountError` (vazio serve, zero e
    texto ilegível recusam com frases distintas), `targetFields` (uma definição para as
    duas rotas), `targetBody`, teto opcional em `createEstimateBody`
  - apps/web/src/orcamento/labels.ts (+107) — frases do bloco, da faixa e dos campos;
    `tetoEtiqueta`/`tetoClasse`; `ESTIMATE_TARGET_INVALID` na tabela de recusas
  - apps/web/src/orcamento/styles.css (+177) — `.coluna-empilhada`, `.teto-consumo` nos
    três estados, `.teto-linhas`/`.teto-valor`/`.teto-resultado`, `.teto-consequencia` e
    `.teto-faixa`; NENHUMA cor nova (só `#3c2708`, `#6b3a06`, `#b47512`, `#fbe6c2` e
    tokens que a folha já usava)
  - apps/web/src/orcamento/OrcamentoApp.tsx (+468/-45) — quatro componentes exportados
    (`BlocoConsumoDoTeto`, `FaixaTetoEstourado`, `PainelTetoDaVerba`,
    `LinhaTetoDaRodada`), campos de teto na abertura com recusa local, `gravarTeto`,
    coluna empilhada BDI+teto na montagem, faixa fora da etapa visível, e o conserto
    declarado `.topbar-meta` → `.dica`
  - apps/web/src/orcamento/OrcamentoApp.test.tsx (+280) — 15 testes novos dos quatro
    componentes e do estado inicial da rodada
  - apps/web/src/orcamento/api.test.ts (+42) — transporte do `POST .../target`
  - apps/web/src/orcamento/requests.test.ts (+99) — corpos e recusa local do teto
  - docs/features/F-027-modo-teto-orcamento-invertido/tasks/T2-build-report.md (este
    arquivo)

Validation executed:
  - make check → exit 0 (ruff check "All checks passed"; ruff format 425 arquivos;
    mypy strict "no issues found in 195 source files"; check_docs 253 arquivos +
    paridade de lifecycle; schema_export --check; contracts:check; tsc -b + vite build;
    terraform fmt -check)
  - npm --workspace @croquito/web run test → exit 0; 40 arquivos, 737 testes
    (baseline 693 → +44)
  - make test → exit 0; pytest 1705 passed, 13 skipped; vitest 737 passed
    (baseline pytest 1704/13 — o +1 é o e2e que a T3 acrescentou em paralelo)

Validation skipped: nenhuma dos perfis exigidos. Não foram executados
  `make smoke-local` nem `npm --workspace @croquito/web run smoke:headless` — os dois
  exigem stack Docker + Keycloak locais, estão fora do CI e fora da Validation do
  contrato.

Unavailable capabilities: none

Assumptions:
  1. O percentual é calculado NA TELA. O payload da T1 não o traz, e o Design Approval
     Package deixa a escolha explícita ("no servidor, junto do bloco, ou na tela, a partir
     dos dois valores já truncados"), fixando só que a tela nunca recomputa dinheiro. O
     percentual é razão, não dinheiro; mesmo assim ele não passa por `float`: os dois lados
     viram `BigInt` exatos e a divisão trunca na segunda casa, como o domínio trunca no
     centavo. Dinheiro (teto, consumo, restante, excedente) sai como o servidor escreveu —
     a única operação aplicada a um valor em reais é tirar o sinal de menos do restante
     negativo, que é troca de notação.
  2. Truncar, não arredondar: `91996.44 / 95000.00` sai "96,83%" e o mock mostra "96,84%".
     Os valores do mock são declarados ilustrativos; a escolha segue a disciplina de
     truncamento do domínio.
  3. O estado escrito vem SEMPRE de `over` (servidor), nunca de uma comparação refeita na
     tela — inclusive no limite exato, que é "dentro do teto" com outra palavra.
  4. `errors.ts` não mudou: `ESTIMATE_TARGET_INVALID` chega como `code` de topo do
     `RoundRefusal` (`_round_refusal_problem` em `main.py`), então a tabela de
     `labels.ts` já basta. O contrato citava "labels.ts/errors.ts" como par.
  5. Gravar o teto usa o `submitting` compartilhado da jornada (como todas as outras
     mutações), então "Gravando…" também desabilita o painel durante uma montagem em voo.
  6. O campo do teto é pré-preenchido pela leitura da rodada SÓ enquanto ninguém escreveu
     nele (mesma forma funcional do BDI) — é o que preserva o valor digitado no `409`.

Remaining risks:
  1. "Faixa presente em TODA etapa" é garantida por ESTRUTURA (um único ponto de render,
     fora do `switch` de etapa; `FaixaTetoEstourado` não recebe etapa nenhuma) e não por
     teste de integração: o vitest do repositório roda em `environment: "node"`, sem DOM,
     e `renderToStaticMarkup` não executa efeitos — não há como montar a vista da rodada
     com estado vindo do servidor. Coberto: a faixa renderiza no estouro, some nos demais
     estados (limite exato incluído), não tem botão nenhum, e a rodada aberta sem estado
     lido não mostra vestígio de teto em etapa nenhuma. Um teste que pegue alguém movendo
     a faixa para dentro de uma etapa exigiria ambiente DOM — decisão fora do escopo.
  2. `parseDecimalInput` (compartilhado com BDI e quantidade) lê "85.000" como notação do
     servidor, ou seja R$ 85,00 — não como 85 mil. Comportamento pré-existente e
     documentado do módulo; no teto ele fica visível na hora (o painel mostra "R$ 85,00").
     Não alterado: mexer nele mudaria BDI e quantidade, fora do escopo.
  3. Se a leitura observacional do orçamento montado falhar mas o estado da rodada trouxer
     consumo, a prévia diz "nenhum orçamento montado ainda" com o bloco do teto ao lado. O
     bloco vem da leitura AUTORITATIVA (o estado da rodada); a prévia é que vem da
     observacional.
  4. Copy: todo texto é rascunho do mock, e o pacote registra que a copy final continua
     sendo gate humano aberto — sobretudo as três consequências do estouro.

Human decisions required:
  - Copy final dos textos do teto (gate aberto no Design Approval Package).
  - Remover o teto de uma rodada que já o tem: continua sem ato, sem botão e sem rota,
    como o ADR-0040 e o pacote deixaram.
  - Merge/publicação da branch (represados, conforme os human_gates do plano).

Desvios conscientes do contrato:
  1. **Módulo novo `teto.ts` + `teto.test.ts`.** O contrato lista `api.ts`,
     `OrcamentoApp.tsx`, `labels.ts`/`errors.ts`, `styles.css` e testes vitest dentro de
     `apps/web/src/orcamento/`. A derivação pura ganhou módulo próprio, no mesmo padrão de
     `cascata.ts`, `etapas.ts` e `overlay.ts`: é onde a regra fica testável sem DOM e sem
     rede, e é o que mantém `OrcamentoApp.tsx` (2.4k linhas) sem aritmética. Dentro do
     diretório do escopo.
  2. **Quatro componentes exportados** em vez de JSX inline. Mesma razão do precedente
     (`SeloFonte`, `EstadoExtracao`, `BannerOrcamentoMudou`): com vitest em `node`, só o
     que é componente exportado tem oráculo.
  3. **Duas frases de recusa do teto, não uma.** O mock mostra textos diferentes para
     `0,00` (abertura) e para texto ilegível (painel); as causas e as saídas são
     diferentes, e as duas frases são as do mock.
  4. **Terceira consequência do estouro:** a vírgula entrou no trecho em negrito
     ("…caminho legítimo,") para o parágrafo fechar sem espaço solto. Texto é rascunho.

Fora de escopo, observado e NÃO implementado:
  - `docs/product/FDD.md` não ganhou o comportamento do teto na seção do orçamento-base. O
    plano congelado não tem task de documentação de produto (T1 = API, T2 = web,
    T3 = e2e) e o contrato desta task lista só `apps/web/src/orcamento/` — fica para a
    integração da feature decidir.
  - `apps/web/AGENTS.md` não descreve a jornada `src/orcamento/` (só croqui, medição e
    plataforma). Lacuna herdada da F-020, não tocada aqui.
  - A recusa mais barata do caderno (painel "Teto da verba" recolhido atrás de um link em
    rodada sem teto) segue como questão aberta do pacote: o painel aparece sempre.
  - Ambiente DOM para o vitest do web (ver risco 1) — decisão de infraestrutura de teste,
    com efeito sobre as três jornadas.

Baseline → final:
  - BASELINE (na árvore com o diff da T1, antes de qualquer edição minha):
    `make check` exit 0; `npm --workspace @croquito/web run test` 693 testes verdes.
  - FINAL: `make check` exit 0; vitest 737 verdes; `make test` exit 0 (pytest 1705/13).
  - Reprovação transitória registrada: numa execução intermediária de `make test`,
    `tests/worker/test_valuation_local_server.py::test_a_second_extraction_while_one_runs_is_refused_as_busy`
    falhou com `FileNotFoundError` num `.takeoff-overlay.<aleatório>.png` temporário. Área
    NÃO tocada por esta task (worker/servidor local de medição, Python). Confirmado
    intermitente: o teste passa isolado (2 execuções) e a suíte completa passou nas duas
    execuções seguintes. Nada foi consertado nessa área.
```
