# F-037 — Evidência de execução

feature_id: F-037
status: `READY_FOR_HUMAN_REVIEW`
data: 2026-08-22

## 1. Gates humanos exercidos

| Gate | Estado |
| --- | --- |
| Seleção | Exercida em 2026-08-22 |
| **ADR-0047** | **Aceito por ato humano em 2026-08-22** ([ADR-0047](../../adr/0047-acervo-de-catalogos-da-plataforma.md), `Accepted`) |
| **Design Approval Package** | **Aprovado por ato humano em 2026-08-22**, revisão 1 ([mock/README.md](mock/README.md)) |
| Confirmação de que SCO-Rio pode ser distribuída pela plataforma | **Pendente** — não bloqueia o código, decide o conteúdo inicial do acervo |
| Publicação dos arquivos reais | **Pendente** — ato do operador, pós-deploy |
| Merge e deploy | **Pendente** |

## 2. Baseline

`make check` e `make test` verdes antes da primeira mudança. Nenhuma falha preexistente
registrada, e nenhuma foi introduzida.

## 3. Tasks executadas

Seis tasks, todas por `implementador-opus` exceto a T5 (`implementador-sonnet`). O
`BUILD REPORT` de cada uma é a evidência primária da sua execução e foi preservado na
sessão de orquestração; o resumo abaixo não o substitui.

| Task | Entrega | Status |
| --- | --- | --- |
| T1 | Tabela `reference_catalogs` (migração `0014`), objeto fora de `tenants/`, três rotas de plataforma | `BUILD_COMPLETE` |
| T2 | Listagem sob a rodada filtrada pelo regime, instalação a partir do acervo, procedência na `CascadeEntry` | `BUILD_COMPLETE` |
| T6 | Presign próprio da plataforma (`PLAN_DEVIATION`, ver §5) | `BUILD_COMPLETE` |
| T3 | Seção do acervo na jornada de Plataforma | `BUILD_COMPLETE` |
| T4 | Escolha da tabela na cascata do orçamento | `BUILD_COMPLETE` |
| T5 | e2e da cadeia pelo acervo e da equivalência entre os dois caminhos | `BUILD_COMPLETE` |

## 4. Validação integrada

Executada pelo revisor no checkout completo, **sem trabalho em voo**:

```text
make check   → exit 0  (ruff check/format, mypy strict, check_docs, drift de contratos,
                        build web + field, terraform fmt)
make test    → exit 0  (pytest 2318 passed / 10 skipped; vitest web 1018; vitest field 261)
```

Além disso, durante a revisão de cada task, executados de forma independente do relatório do
executor: `ruff`, `mypy strict` (243→244 arquivos), `tests/api`, `tests/e2e` e a suíte
Python completa. O snapshot de OpenAPI foi conferido como **só de adição** na T1.

A T1 executou o gate de migrations contra **PostgreSQL real**
(`CROQUITO_TEST_POSTGRES_URL`), que fica *skipped* sem a variável: ele apanhou uma
divergência em `test_medicao_nasce_depois_da_baseline_com_o_indice_da_listagem` que só
apareceria no CI.

## 5. Desvios de plano

**`PLAN_DEVIATION` — T6 acrescentada**, registrada em [plan.md](plan.md). A revisão da T1
apurou que publicar dependia de `POST /v1/uploads/presign`, que cai no prefixo `croqui` de
`JOURNEY_ROUTE_PREFIXES`; com o croqui `disabled` — o próprio caso de uso da F-034 — o
acervo ficaria sem como ser alimentado. Decisão humana de 2026-08-22: presign próprio sob
`/v1/platform`. A alternativa de classificar `/v1/uploads` como sem jornada foi **recusada**
por enfraquecer a F-034. O teste que fecha o defeito prova os dois lados no mesmo ambiente.

## 6. Achados da revisão linha a linha

Feita pelo modelo da sessão, relendo o diff e re-executando os portões — não confiando no
relatório do executor.

1. **Defeito corrigido: dois toasts sobrepostos.** O Task Contract da T3 afirmou que
   `DisponibilidadeDeJornada` tem toast de sucesso; **ela não tem**. A afirmação era falsa e
   produziu uma segunda faixa `position: fixed` no mesmo canto (`.app-toast`,
   `styles.css:811-815`), que se sobreporia à da seção vizinha. Corrigido na revisão: a
   confirmação passa a ser a releitura da lista, e um teste fixa a decisão. **O erro foi do
   contrato, não do executor.**
2. **Verificado e correto**: o digest que endereça o objeto do acervo é conferido contra os
   bytes reais (`_read_catalog_object`) antes de virar chave, em todos os perfis de storage.
   Sem isso, dois conteúdos poderiam colidir na mesma chave e um sobrescreveria o outro.
3. **Verificado e correto**: a refatoração de `presign_upload` (T6) não alterou o
   comportamento do caminho do croqui — mesmo `expires_at`, mesmo `sha256.lower()`, mesmo
   header de checksum condicional ao perfil S3.
4. **Acima do contrato, mantido**: a procedência que contradiz o identificador de fonte
   gravado **recusa na leitura** em vez de acreditar no rótulo (T2); e `origin_allowed_under_regime`
   é formulação única, usada pela instalação e pela listagem, para as duas não divergirem.

## 7. Divergências do pacote de design aprovado

Nove, todas registradas em [mock/README.md](mock/README.md), separadas entre as apuradas no
planejamento (1-3) e na implementação (4-9). As de maior consequência:

- **Sem abas na Plataforma** — a tela real compõe seções empilhadas; o mock inventou a fita
  de abas. Fixado por teste que afirma ausência de `role="tab"`.
- **A contagem "3 rodadas ainda a referenciam" não existe e não foi fabricada** — nenhuma
  rota devolve esse número. A linha fora de circulação mostra a palavra e a data; um teste
  negativo fixa a ausência. Fechar isso exige rota nova e é fatia própria.

## 8. Riscos remanescentes

- **Primeira tabela sem `tenant_id`.** A condição que a sustenta é verificada por teste, que
  também afirma que ela é a **única** — uma segunda tabela global quebra o teste.
- **Operação contínua nova**: alguém publica a data-base nova, ou o acervo envelhece. A
  data-base é exibida na escolha, então um catálogo velho é visível na tela.
- **Questão aberta 2 do pacote** (muitas data-bases da mesma tabela deixando a lista longa)
  segue sem tratamento, como o plano previu.
- **Cascata instalada antes da feature** depende do fallback de ausência de procedência —
  coberto por teste, e some quando não houver mais cascata antiga.
- **Auditoria de instalação não registra qual tabela do acervo foi escolhida** (o ato já não
  tinha `details`). Apontado pela T2, fora do escopo dela.

## 9. Decisões humanas pendentes

1. Confirmar se o SCO-Rio pode ser distribuído pela plataforma (decide o conteúdo inicial).
2. **SINAPI e SICRO precisam ser baixados manualmente** — apurado em 2026-08-22 que a Caixa
   responde `429` a download automatizado e o DNIT monta a listagem por JavaScript. O
   `catalog.json` do SCO-Rio 07/2026 já está importado localmente
   (`output/sco-rio-2026-07/`, 4.865 entradas, desonerado e onerado).
3. A **copy** das telas novas segue fora da aprovação da revisão 1, por declaração explícita
   do registro.
4. Merge, deploy e aplicação da migração `0014` no hospedado.
5. Publicação dos arquivos reais no acervo em homologação.
