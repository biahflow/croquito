# Contexto de medição de obra: do boletim canônico à planilha MAPÃO

Status: Proposed  
Responsável: Product / Engineering  
Última revisão: 2026-08-14

Este documento é a referência canônica do contexto delimitado `valuation`
(`packages/valuation/src/croquito_valuation/` e
`services/worker/src/croquito_worker/valuation/`, CLI `croquito-valuation`).

Medição de obra pública é um problema diferente de croqui → DXF: a entrada é planilha e
catálogo de preços, a saída é boletim de medição, e o erro que interessa é de centavo,
não de milímetro. Por isso ela vive em um contexto próprio, com vocabulário próprio,
sem tocar o scene graph ([ADR-0016](../adr/0016-valuation-bounded-context.md)).

## Glossário pt ↔ en

| Português (obra) | Inglês (código) | O que é |
|---|---|---|
| Medição | `Valuation` | O que foi executado num período, por obra |
| Período de medição | `period_number` / `reference_label` | Ordem e rótulo do período medido |
| Boletim de medição (BM) | `WorksiteBulletin` | Itens medidos de uma obra, com total |
| Linha do boletim | `BulletinLine` | Item, código, unidade, preço, quantidade, total |
| Memória de cálculo | `CalcSheet` | Como a quantidade de um item foi obtida |
| Bloco de cálculo | `CalcBlock` | Um trecho medido: operandos, deduções, subtotal |
| Parcela / operando | `CalcOperand` | Valor impresso com rótulo ("PERÍMETRO") |
| Desconto de vãos | `deductions` | Área/extensão descontada do bloco |
| Catálogo de preços | `PriceCatalog` | Tabela de referência importada (SCO) |
| Código SCO | `code` / `ScoCodeParts` | `AD04050050(/)`: família, subgrupo, grupo, item, variante |
| Família / subgrupo | `family_*` / `subgroup_*` | Cabeçalhos que classificam o item na tabela |
| Obra | `worksite_key` / `worksite_name` | Intervenção medida |
| Template da planilha | `WorkbookTemplate` | Layout da pasta descrito como dado |
| Célula fixada | `PinnedCell` | Total gravado literal por divergência de truncamento |
| Planilha Geral | `ContractWorkbook` | Consolidado do contrato: todo código, todo período já lançado |
| Linha contratual | `ContractLine` | Um código no consolidado: contratado, vigente, acumulado, saldo |
| Medição lançada | `PeriodProgress` | Par QUANTIDADE\|VALOR de um período já registrado na linha |
| RE-RA | `Amendment` / `AmendmentLine` | Revisão contratual: delta com sinal por código, ou item novo |
| Acumulado | `accumulated_quantity` / `accumulated_amount` | Soma do que já foi medido do código em todos os períodos |
| Saldo | `balance_quantity` | Quanto ainda cabe do código: vigente menos acumulado |
| Aprovação | `ValuationApproval` | Aprovação nominal amarrada por digest ao conteúdo aprovado |
| Decisão do orçamentista | `ReviewerDecision` | Ato humano rastreável: quem, quando, confirma ou rejeita |
| Levantamento de quantitativos (takeoff) | `TakeoffPacket` / `TakeoffItem` | Legenda quantificada da prancha, do estado observado (`proposed`/`ambiguous`) ao confirmado pelo orçamentista |
| Prancha | `plate_id` / `PlateEvidence` | Desenho do projetista com a legenda já quantificada; âncora de evidência do item de takeoff |
| Sugestão de código | `CodeSuggestion` / `CodeCandidate` | Shortlist lexical determinística por item confirmado; observação, nunca decisão |
| Confirmação de código | `CodeAssignment` | Ato humano rastreável que liga item confirmado a código do catálogo (ou o rejeita) |
| Plano de cálculo | `CalcPlan` / `CalcBlockPlan` | Decomposição declarada da quantidade confirmada em operandos da memória |
| Dossiê do aditivo | `AmendmentDossier` / `AmendmentDossierItem` | Itens confirmados no takeoff cujo código foi rejeitado, com a justificativa humana; instrui o pedido de RE-RA e nunca precifica |
| Origem de preço | `PriceOrigin` | Fonte da cotação de um catálogo: `sco`, `emop` ou `composition`; um catálogo carrega uma origem só |
| Catálogo EMOP | `EmopCatalogLayout` / `read_emop_catalog` | Tabela estadual paga (assinatura GRE, .DBF) importada com layout como dado; vale só pré-licitação |
| Composição de custo | `CostComposition` / `CompositionLine` | Preço que o orçamentista monta por coeficientes (mão de obra, insumo, equipamento); compilada a catálogo `origin=composition` |
| Orçamento-base | `Estimate` / `EstimateLine` | Orçamento de pré-licitação com cascata de fontes declarada e proveniência por linha; sem contrato, saldo ou aprovação de medição |
| Cascata de fontes | `ensure_price_cascade` / `CatalogSource` | Ordem de catálogos declarada por quem monta o orçamento (nunca em código); uma fonte por origem |

Vocabulário proibido neste contexto, porque já significa outra coisa no repositório:
`Measurement*` (cota do scene graph), `*Budget*` (teto de gasto de IA em `providers.py`)
e `Job` (job do pipeline de cena).

## Fluxo dos comandos da cadeia

| # | Comando | O que faz | Marco |
|---|---|---|---|
| 1 | `import-workbook` | Importa catálogo e consolidado do MAPÃO preservando o original | **M2** |
| 2 | `extract-legend` | Gera a prancha sintética e extrai a legenda quantificada dela por fixture; a leitura de prancha real de cliente é o comando pago `extract-legend-real`, atrás de teto de gasto e allowlist do documento | **M3** / real **M5** |
| 3 | `review-takeoff` | Aplica as decisões do orçamentista sobre o pacote de takeoff, item a item, com recusa fechada de re-decisão | **M3** |
| 4 | `suggest-codes` | Shortlist lexical determinística de código SCO por item confirmado (observação, nunca decisão); com `--refine-arm NOME=PROVIDER:MODELO` a mesma shortlist é **reordenada e anotada** por provider pago, nunca substituída | **M4** / refino **M5** |
| 5 | `confirm-codes` | Orçamentista confirma ou rejeita código item a item, fail-closed e sem re-decisão | **M4** |
| 6 | `build-calc` | Monta memória de cálculo e boletim canônicos da obra a partir do takeoff confirmado + códigos confirmados (medição sem aprovação) | **M4** |
| 7 | `export-valuation` | Render auditado em xlsx, atrás do portão de aprovação e saldo | **M2** |
| 8 | `build-amendment-dossier` | Materializa o dossiê do aditivo (RE-RA) a partir das rejeições de código de itens confirmados; artefato de fechamento da rodada, nunca precifica | **M8** |
| 9 | `import-compositions` | Compila as composições manuais (`CompositionSet`, preço sempre recomputado) num catálogo `origin=composition` amarrado por digest à fonte | **M8** |
| 10 | `build-estimate` | Monta o orçamento-base de pré-licitação sobre a cascata de `--catalog` declarada, com proveniência por linha e item sem preço declarado | **M8** |

`suggest-codes` e `confirm-codes` aceitam `--catalog` repetível desde o M8: com um
catálogo é a medição de sempre (nenhum comportamento mudou); com vários é o
orçamento-base — cada candidato e cada confirmação citam a fonte, o consolidado
contratual é proibido (`ESTIMATE_CASCADE_CONTRACT_FORBIDDEN`), o braço semântico degrada
declaradamente para lexical (`SEMANTIC_CASCADE_UNSUPPORTED`) e o refino pago recusa
(`SUGGEST_REFINE_CASCADE_UNSUPPORTED`) em vez de misturar fontes num payload. A demo
determinística da cadeia é `make valuation-estimate-demo`, com golden próprio.

Ao lado do `import-workbook` completo existe `import-catalog`: lê só a aba de catálogo e
publica só `catalog.json` + `catalog-import-report.json` (com `consolidado:
"not_imported"` explícito no relatório). Ele nunca abre a PLANILHA GERAL nem a aba de
RE-RA, então nunca vê nem contorna o portão semântico do consolidado
(`CONTRACT_SEMANTICS_DIVERGENT`) — o catálogo é dado de referência para
`suggest-codes`/`confirm-codes`/`build-calc`, mas medição real exportável continua
exigindo o `import-workbook` completo.

Na mesma família existe `import-emop` (M8): lê o catálogo EMOP de um arquivo `.DBF`
(dBASE III, leitor mínimo interno) com o layout inteiro declarado como dado
(`EmopCatalogLayout`: campos, encoding, regex do código, data-base) e publica
`catalog.json` com `origin=emop` + `emop-import-report.json`. O catálogo digital EMOP
real é **pago** (assinatura GRE); nada dele existe no repositório — a fixture é
sintética e o formato real fecha como dado no layout quando o arquivo existir. Cada
importação gera um catálogo novo amarrado por digest com `reference_month` próprio;
não existe troca silenciosa de preço. Esse catálogo **nunca** entra na cadeia da
medição licitada (ver invariante abaixo)
([ADR-0027](../adr/0027-price-source-provenance-and-bid-boundary.md)).

Ao lado do `extract-legend` por fixture existe o caminho **pago** da mesma etapa:
`extract-legend-real` lê a legenda de uma prancha de cliente com um provider externo. Ele
não substitui o comando offline nem muda a natureza do resultado — todo item continua
nascendo `proposed` ou `ambiguous`, e o pacote sai com o overlay de revisão obrigatória. O
que ele acrescenta é a cadeia de autorização: braço `NOME=PROVIDER:MODELO` real, teto de
gasto em `CROQUITO_AI_MAX_ESTIMATED_COST_USD`, manifest do `croquito-demo ingest` e o
documento na allowlist `CROQUITO_AI_EXTRACTION_ALLOWED_DIGESTS`.

Fora da cadeia existem duas ferramentas de diagnóstico **local**, que nunca rodam no CI e
não escrevem nos arquivos analisados. `parity` abre uma pasta que o sistema não gerou duas
vezes (fórmulas e valores em cache) e responde se o número mostrado é o número que a
fórmula calcula (`make valuation-parity PREVIOUS=<caminho.xlsx>`). `compare-bulletin`
(`make valuation-compare`) é a peça do aceite do M5: casa o boletim gerado de uma obra
(pelo `valuation.json`, a fonte de verdade canônica) com a aba de BM real do cliente
(valores em cache, layout declarado pelo template como dado), código a código e centavo a
centavo, sem tolerância — divergência sai na classe certa (quantidade, preço, total de
linha, total da obra, código ausente de um lado) e `zero_cent` só é verdadeiro quando
nada aponta dinheiro diferente. Exit 0 zero centavo, 1 divergência relatada, 2 recusa
fechada; o roteiro completo do aceite real está no
[runbook da Toca](../operations/RUNBOOK_VALUATION_TOCA_ACCEPTANCE.md).

A homologação humana da cadeia tem superfície própria desde o M6: `serve` sobe o
**servidor local de homologação** (`local_server.py`,
[ADR-0020](../adr/0020-local-homologation-server-for-valuation.md)) sobre um diretório
de rodada, e o app `apps/medicao` é a tela da orçamentista — revisão do takeoff,
confirmação de código com busca no catálogo e boletim. O servidor embrulha as mesmas
funções de domínio fail-closed do CLI (recusa atravessa com código estável e nunca grava
artefato), carimba `reviewer_id`/`decided_at` no lado servidor (`--reviewer` na
inicialização; o corpo das requisições recusa identidade) e cobre localmente a lacuna de
`base_version` com guarda otimista por digest de arquivo (`LOCAL_STATE_MOVED`).
Ferramenta local declarada: sem autenticação, bind default 127.0.0.1, nunca produção.
Desde a rodada de homologação real, o servidor também recebe a prancha do projetista
(`POST /plates`: PDF → ingestão local 200 DPI → **extração paga automática e
assíncrona**, decisão do usuário de 2026-08-13) — com teto de gasto por env no start
como freio duro, o ato de upload como consentimento do documento (digest registrado no
lineage), braço fixado no vencedor da eval e falha visível com re-disparo explícito; o
refino pago de código continua exclusivo do CLI
([ADR-0020](../adr/0020-local-homologation-server-for-valuation.md)). `serve --catalog
<catalog.json>` (ou `CROQUITO_MEDICAO_CATALOG`) provê o catálogo de preços a uma
rodada nova na subida do servidor — validado e copiado para dentro da rodada, nunca
sobrescrevendo o catálogo de uma rodada existente (as confirmações de código já feitas
se apoiam nele); o banner do `serve` declara catálogo e disponibilidade da extração.
Recalcular a shortlist já gravada (`POST /suggestions/recompute`) é gesto do orçamentista,
com o digest-base citado como as demais mutações, e recusa fechado
(`LOCAL_SUGGESTIONS_REFINED`) quando ela carrega refino pago — recalcular descartaria o
lineage da chamada, e refinar de novo continua sendo comando do CLI.

`serve --hosted` ([ADR-0026](../adr/0026-medicao-hospedada-sessao-autenticada-minima.md)) é
o **modo hospedado** do mesmo servidor, e o único que pode subir fora da máquina do
operador: toda rota da rodada exige Bearer JWT do mesmo realm da sessão de cena (validador
compartilhado `croquito_core.oidc`, sem tocar em `croquito_api`) com o papel `orcamentista`,
o `reviewer_id` carimbado na decisão vem do claim assinado (`preferred_username`, com `sub`
como fallback) em vez da flag, o CORS sai das origens declaradas no ambiente
(`CROQUITO_MEDICAO_OIDC_ISSUER`, `CROQUITO_MEDICAO_OIDC_AUDIENCE`,
`CROQUITO_MEDICAO_WEB_ORIGINS` — ausência recusa a subida) e `GET /healthz` é a única rota
sem sessão, para o probe do host. Nenhuma regra de domínio muda entre os modos: as mesmas
funções fail-closed, os mesmos nomes de artefato, a mesma guarda por digest. Sem a flag, o
comportamento local do ADR-0020 é idêntico ao que sempre foi, inclusive o aviso ao expor a
porta em outra interface. No volume da rodada hospedada (bucket montado por FUSE), a
publicação de artefato troca `temporário + rename` por escrita direta quando
`CROQUITO_IO_DIRECT_WRITE` está ligada — lá o `rename` é copy+delete e não é a operação
atômica, enquanto o fechamento do arquivo é; desligada (o default), a escrita local não
muda.

A sugestão e a busca de código usam o **matcher híbrido** do M7
([ADR-0021](../adr/0021-hybrid-sco-code-retrieval.md)): braço léxico (radicais +
sinônimos de domínio **como dado**, cobertura da consulta ponderada por IDF) fundido
por RRF com braço semântico (embeddings do catálogo — dado público SCO — em índice
local amarrado por digest e receita, gerado por `index-catalog`; kNN em numpy).
Invariantes: candidato sempre com `origin` e scores declarados; embeddings nunca
confirmam nada; sem chave/teto/índice a busca degrada para o léxico funcional com o
motivo declarado; o chamador pode fixar o braço léxico puro
(`GET /catalog/search?arm=lexical`, motivo em `semantic_notes`), que é como a tela local
consulta a cada tecla — nenhum vetor resolvido, nenhuma escrita de `query-cache.json`;
e a qualidade é gate de eval (golden com `recall@20 = 100%` no
catálogo real, oráculo por família onde o rótulo não discrimina a variante — ver
[Evaluation Strategy](../ai/EVALUATION_STRATEGY.md)).

Também fora da cadeia: `takeoff-demo` percorre prancha sintética, extração e revisão num
só comando, para demonstração determinística; `extraction-eval`
(`make valuation-extraction-eval`) é o gate dos **dois estágios pagos** — mede recall da
legenda, acurácia de quantidade e top-1/top-3 do refino de código ao lado da baseline
lexical, e exercita os gates de gasto, de allowlist e de permutação da shortlist. Sem
`--arm` ela roda o braço fixture embutido, offline e sem custo (é assim que o CI a roda);
com `--arm` a rodada é paga e local, e a comparação entre modelos é decisão humana sobre o
relatório ([Evaluation Strategy](../ai/EVALUATION_STRATEGY.md)); `takeoff-eval`
(`make valuation-eval`) é o gate do takeoff — mede o recall da legenda contra o gabarito da
prancha sintética e exercita de verdade os invariantes do fluxo de revisão (nenhum item
nasce confirmado, re-decisão recusada, confirmação de ambíguo sem quantidade recusada,
prancha adulterada depois de gerada recusada). Como as evals de visão e do solver do
croqui, as duas validam a fixture e o **contrato** do fluxo, não precisão de extração numa
prancha real de cliente.

O M1 entregou o trecho final da cadeia sem IA (catálogo sintético → medição canônica →
planilha → auditoria de round-trip). O M2 fecha as duas pontas desse trecho: importação do
consolidado contratual com RE-RA, consolidação multi-obra na PLANILHA GERAL, portão de
aprovação e saldo, e exportação que falha fechada. O M3 abriu o começo da cadeia — extração
da legenda quantificada por fixture sintética e revisão do orçamentista. O M4 fecha o
**meio** da cadeia, inteiramente offline: sugestão lexical de código, confirmação
fail-closed e o boletim/memória que nascem do takeoff confirmado. `croquito-valuation
demo` (`make valuation-demo`) percorre a cadeia inteira sobre fixture sintética, do MAPÃO
anterior à pasta auditada, com a quarta obra nascendo da prancha. O M5 abre as duas vias
pagas — extração de prancha real de cliente e refino da sugestão de código —, ambas atrás
de teto de gasto e allowlist, com gate próprio (`make valuation-extraction-eval`) que roda
offline no CI, e entrega o comparador do aceite (`compare-bulletin`). A comparação paga
entre modelos sobre a prancha sintética foi executada em 2026-08-13 com autorização
explícita de gasto: o Sonnet aprovou as duas tarefas e é o braço da rodada real; o
registro completo, incluindo as reprovações do Opus, está em
[Model Routing](../ai/MODEL_ROUTING.md). O que permanece pendente do M5 são os atos sobre
documento real da Toca — extração paga da prancha do projetista, revisão e confirmação
reais do orçamentista e o `compare-bulletin` contra o BM real com zero centavo —,
roteirizados no [runbook](../operations/RUNBOOK_VALUATION_TOCA_ACCEPTANCE.md). A sugestão
lexical continua sendo o fallback permanente, com ou sem provider.

## Invariantes

- **Dinheiro trunca, quantidade arredonda.** Todo valor monetário é `TRUNC(x,2)` em
  `Decimal` (`money_trunc`); quantidade é `ROUND(x,2)` (`quantity_round`). O par
  1,15 × 10,30 vale 11,84 — arredondar daria 11,85, e a diferença é dívida com o
  erário. `float` nunca entra: os modelos recusam `DECIMAL_FROM_FLOAT`.
- **O JSON é a fonte de verdade; a planilha é render auditado.** Gera, reabre, recomputa
  e compara centavo a centavo. Divergência não publica (`audit.status == "divergent"`
  faz o comando sair com 1).
- **Nada de total informado sem recomputo.** Subtotal de bloco, quantidade da memória,
  total de linha e total da obra são recalculados pelos validadores; divergência vira
  erro com código estável (`CALC_SUBTOTAL_MISMATCH`, `CALC_TOTAL_MISMATCH`,
  `LINE_TOTAL_MISMATCH`, `BULLETIN_TOTAL_MISMATCH`).
- **Memória 1:1 com o boletim.** Toda linha tem memória de cálculo e a quantidade
  impressa é a recomputada dos blocos (`VALUATION_CALC_SHEET_MISMATCH`,
  `VALUATION_QUANTITY_MISMATCH`).
- **Template é dado, não código.** Nome de aba, colunas, rótulos e formatos vivem no
  `WorkbookTemplate`. O template real de cada cliente fica fora do Git; o repositório só
  versiona o `default_template()` e fixtures sintéticas.
- **A pasta é autocontida — sem `VLOOKUP`.** Descrição, unidade e preço são literais no
  arquivo, porque a planilha circula por e-mail sem o catálogo. O preço impresso, ainda
  assim, é conferido contra o catálogo importado na escrita e na auditoria.
- **Célula fixada é declarada.** Quando o produto em ponto flutuante divergiria do
  cálculo exato, o total é gravado literal em vez de fórmula e a célula aparece em
  `pinned_cells` no relatório e no `audit.json`. O critério é conservador: na dúvida,
  fixa.
- **Linha ilegível não é ignorada.** Importar catálogo com código fora do formato SCO ou
  preço não interpretável falha com `ROW_UNPARSEABLE` apontando aba e linha.
- **O layout do arquivo real é dado, não exceção no código.** O template declara a
  hierarquia do catálogo (família e nível intermediário em colunas próprias, ou tudo na
  coluna de código), a escala decimal das quantidades e a ausência da coluna de vigente.
  Sem a coluna, o vigente é derivado (`contratual + Σ RE-RA do código`) em vez de
  adivinhado, e a derivação é declarada em cada achado do dossiê. O mesmo vale para o que
  o catálogo publicado intercala entre os itens: `note_prefixes` declara a nota editorial
  ("Nota: As marcas indicadas…"), que passa a ser pulada, e `unpriced_markers` declara o
  texto que substitui o preço quando não há cotação publicada — esse item fica **fora** do
  catálogo em vez de entrar com preço zero, porque preço zero é preço e ausência de preço
  não é. Texto não declarado continua sendo `ROW_UNPARSEABLE`.
- **Código contratual fora da tabela SCO só entra por padrão declarado no template.** O
  contrato real mede item com código nu (`IE00040849`: duas letras e oito dígitos, sem
  variante), ausente do catálogo publicado. O modelo garante só a estrutura
  (`CONTRACT_CODE_PATTERN`, superset de `SCO_CODE_PATTERN`); qual forma nua uma importação
  aceita é o `WorkbookTemplate` quem declara (`extra_code_patterns`/`matches_extra_code`),
  e o leitor revalida cada código aceito contra o superset estrutural antes de aceitar —
  um padrão extra frouxo demais nunca injeta identidade fora da estrutura. O catálogo
  (`PriceCatalogEntry.code`) continua estrito: só o código SCO completo tem preço
  publicado.
- **Linha de seção da aba da prefeitura é layout, não item.** A aba MAPÃO - PREFEITURA às
  vezes traz linha cujo nome de seção (`LAZER / PAISAGISMO`) ocupa a própria coluna de
  código. Quando o código não é aceito e os blocos de RE-RA da linha (reduzida, acrescida,
  item novo) não carregam nenhum valor, ela é pulada como layout e contada em
  `amendment_section_rows`, junto com o subtotal ignorado da coluna de vigente quando
  houver um. Por padrão essa coluna também precisa estar vazia para a linha contar como
  seção; um layout real observado tem a linha que abre um grupo carregando ali o subtotal
  do próprio grupo em vez de ficar em branco — como essa coluna é usada de verdade para
  reconciliar o vigente por código no resto da aba, o template declara esse caso por
  opt-in (`AmendmentLayout.section_rows_carry_group_subtotal`, `False` por padrão) em vez
  de o código presumir por conta própria; ligada, o subtotal não bloqueia o skip e ainda
  assim é sempre registrado, nunca descartado em silêncio. Linha com valor num bloco de
  RE-RA continua recusando como ilegível de qualquer forma, com a flag ligada ou não.
- **O número da medição vem do rótulo, não da posição.** `11ª MEDIÇÃO - COMPLEMENTAR` é a
  11ª; a numeração pode ter buraco (13ª → 15ª) e o buraco é dado — `period_numbers` e
  `period_gaps` vão para as notas da importação. Cabeçalho com numeração decrescente é
  layout que o leitor não entende (`PERIOD_HEADER_UNPARSEABLE`).
- **Normalização é declarada e sub-centavo.** O ruído de ponto flutuante do cache de
  fórmula (`107,44999999999996`) é absorvido só abaixo de um milionésimo e cada célula
  absorvida aparece nas notas com o antes e o depois; casa a mais do que o template
  declara é recusa (`NUMBER_SCALE_UNSUPPORTED`). Deriva de centavo sobrevive de propósito
  e vai morrer no recomputo. Linha separadora (sem texto, só o zero em cache das fórmulas)
  é pulada, contada e reportada — não é item ilegível.
- **A chave do consolidado é grupo+código.** O mesmo código SCO aparece em grupos
  diferentes no contrato real; a unicidade é do par, e quem cita um código repetido sem
  dizer o grupo recebe `CODE_AMBIGUOUS_IN_CONTRACT`. Nenhuma linha é escolhida em silêncio.
- **Recusa semântica traz o mapa inteiro, não a primeira violação.** Drift do histórico já
  publicado recusa a importação com `CONTRACT_SEMANTICS_DIVERGENT` e grava
  `import-diagnosis.json`: todas as divergências recomputadas de uma vez, com o código
  estável de cada classe (`PERIOD_AMOUNT_MISMATCH`, `CONTRACT_ACCUMULATED_MISMATCH`,
  `CONTRACT_BALANCE_MISMATCH`, `CONTRACT_BALANCE_NEGATIVE`, `CONTRACT_NEGATIVE_VALUE`,
  `CONTRACT_DUPLICATE_ITEM`/`CODE`, `AMENDMENT_*`, `GENERAL_AMENDED_DIVERGENT`,
  `CODE_AMBIGUOUS_IN_CONTRACT`), a célula exata e os dois números. Falha de **layout**
  continua recusando sem dossiê, e recusa **nenhuma** publica catálogo, consolidado ou
  relatório. O dossiê **descreve**: não existe mecanismo de aceite de divergência, e qual
  divergência do histórico a prefeitura reconhece como correta é a decisão humana pendente
  do [ADR-0018](../adr/0018-valuation-consolidation-and-balance-semantics.md).
- **Nada é publicado sem aprovação nominal e sem saldo.** O portão
  (`Valuation.export_errors`/`ensure_exportable`) recusa medição sem aprovação, com
  aprovação rejeitada, com digest que não bate com o conteúdo
  (`APPROVAL_CONTENT_MISMATCH`), fora da sequência de períodos
  (`PERIOD_NOT_SEQUENTIAL`), com código fora do consolidado (`CODE_NOT_IN_CONTRACT`), com
  preço ou unidade divergindo do contrato e com quantidade acima do saldo
  (`BALANCE_EXCEEDED`).
- **Aprovação é nominal e amarrada por digest.** `ValuationApproval` guarda o SHA-256 do
  conteúdo aprovado; qualquer edição posterior invalida a aprovação no portão. Aprovar um
  conteúdo e exportar outro é o erro que o modelo existe para impedir.
- **RE-RA é só leitura.** O módulo reconcilia o efeito declarado de cada revisão sobre o
  código (`vigente = contratual + Σ deltas`) e a carrega adiante na pasta gerada, mas não
  cria nem altera aditivo. Vigente divergindo entre a PLANILHA GERAL e a aba da prefeitura
  recusa a importação, com a divergência classificada como `GENERAL_AMENDED_DIVERGENT` no
  dossiê ([ADR-0018](../adr/0018-valuation-consolidation-and-balance-semantics.md)).
- **A medição licitada só aceita preço do SCO.** `PriceCatalog`/`PriceCatalogEntry`
  carregam `origin` (`sco` | `emop` | `composition`, default `sco` — artefatos M1–M7
  releem sem migração); um catálogo é uma fonte só (`CATALOG_ORIGIN_MIXED`) e a forma
  do código é validada pela origem (`CATALOG_CODE_INVALID_FOR_ORIGIN`).
  `build_worksite_bulletin` e o escritor da planilha recusam catálogo de origem
  diferente de `sco` (`BULLETIN_PRICE_ORIGIN_FORBIDDEN`): item fora do contrato vira
  dossiê de aditivo, nunca preço de outra tabela — a cadeia SCO → EMOP → composição
  vale só pré-licitação
  ([ADR-0027](../adr/0027-price-source-provenance-and-bid-boundary.md)).
- **O orçamento-base declara a fonte de cada preço.** A cascata é dado (ordem declarada
  por quem monta o orçamento; origem duplicada recusa `ESTIMATE_CASCADE_ORIGIN_DUPLICATE`),
  toda confirmação cita o catálogo de onde o código veio (`ASSIGNMENT_CATALOG_REQUIRED` /
  `ASSIGNMENT_CATALOG_UNKNOWN`) e cada `EstimateLine` carrega origem, digest e data-base —
  a releitura recusa linha apontando fonte fora da cascata
  (`ESTIMATE_LINE_SOURCE_UNKNOWN`). Item sem preço em fonte alguma sai declarado em
  `unpriced_item_ids` (candidato a composição nova), nunca precificado por semelhança. O
  preço unitário de composição é sempre recomputado com truncamento conservador por linha
  (`COMPOSITION_TOTAL_MISMATCH`)
  ([ADR-0027](../adr/0027-price-source-provenance-and-bid-boundary.md)).
- **O dossiê do aditivo instrui, nunca precifica.** `build_amendment_dossier` cruza as
  rejeições de código (`CodeAssignment.status == "rejected"`) com os itens confirmados do
  takeoff — rejeição na revisão do takeoff nunca é aditivo — e exige a nota da rejeição
  como justificativa (`AMENDMENT_DOSSIER_JUSTIFICATION_MISSING`). É artefato de
  fechamento: item confirmado sem decisão de código recusa
  (`AMENDMENT_DOSSIER_ASSIGNMENTS_INCOMPLETE`); dossiê sem nenhuma rejeição é vazio e
  válido. Nenhum modelo do dossiê tem campo de preço, por construção, e nada aqui cria ou
  altera `Amendment`
  ([ADR-0027](../adr/0027-price-source-provenance-and-bid-boundary.md)).
- **A GERAL gerada fecha com a soma dos boletins.** O valor consolidado do período é
  `TRUNC(Σ quantidade × preço)` por código. Quando isso não bate com a soma dos totais dos
  boletins — o mesmo código medido em mais de uma obra pode derivar um centavo — o escritor
  recusa com `GENERAL_CONSOLIDATION_MISMATCH` e nenhuma pasta é gerada; a semântica correta
  desse caso está pendente de confirmação com o orçamentista
  ([ADR-0018](../adr/0018-valuation-consolidation-and-balance-semantics.md)).
- **Extração de legenda é observação, nunca decisão.** Todo `TakeoffItem` nasce `proposed`
  ou `ambiguous`; confirmado exige quantidade e `ReviewerDecision` (`TAKEOFF_ITEM_CONFIRMED_INCOMPLETE`
  quando falta uma das duas).
- **A fixture só extrai a prancha que ela mesma desenhou.** `extract_takeoff_fixture` recebe
  o `PlateArtifacts` que `render_synthetic_plate` acabou de gerar, confere o digest do PDF e
  do PNG contra o que foi registrado na geração, e recusa (`TAKEOFF_FIXTURE_ARTIFACT_MISMATCH`)
  se o arquivo mudou entre gerar e extrair — gerar e extrair andam juntos de propósito; nada
  aqui lê prancha de cliente.
- **Decisão do orçamentista sobre o takeoff é imutável; re-decisão recusa.**
  `apply_takeoff_decisions` nunca muta o pacote de entrada e recusa
  (`TAKEOFF_ITEM_ALREADY_REVIEWED`) sobrescrever um item já confirmado ou rejeitado.
- **O id do item de takeoff é determinístico pela prancha, não pela revisão.** O lote de
  decisões referencia itens por `ti_...` derivado de `plate_id` + rótulo. Versionamento e
  pinagem de pacote por revisão — o equivalente ao `base_version` da cena — é da futura
  sessão autenticada; o CLI não tem esse mecanismo, e essa é uma limitação declarada, não
  escondida.
- **Sugestão lexical é observação e fallback permanente.** `suggest_codes` só roda sobre
  itens confirmados, prioriza unidade compatível e presença no contrato, nunca confirma;
  item sem candidato sai em `unmatched_item_ids`. O refino do M5 reordena a shortlist,
  nunca a substitui.
- **Refino pago é permutação da shortlist, e nada além.** `apply_refinement` aceita do
  provider apenas uma ordem que seja **permutação exata** dos códigos que a via lexical
  elegeu para o item, mais uma anotação: código novo, código a mais ou a menos recusa com
  `REFINEMENT_CODES_MISMATCH`, item que não está na shortlist recusa com
  `REFINEMENT_UNKNOWN_ITEM` e justificativa que não cabe no campo recusa com
  `REFINEMENT_NOTE_TOO_LONG` em vez de ser truncada. Preço, unidade, `lexical_score` e
  `status` do candidato continuam sendo o que a via determinística mediu, e o item citado
  que o refino ignora mantém a ordem lexical. O conjunto refinado declara
  `suggester_version` próprio e carrega o lineage da chamada em `refinement` — um sem o
  outro é recusado nos dois sentidos.
- **Comando pago falha fechado, sem consolo.** `extract-legend-real` e
  `suggest-codes --refine-arm` recusam com exit 2 e **nenhum** artefato quando falta teto
  de gasto, quando o documento está fora da allowlist, quando a página não pertence ao
  manifest ou quando o provider falha. No refino isso vale inclusive para a shortlist
  lexical já calculada: publicá-la depois de a chamada paga falhar faria o artefato mentir
  sobre a própria origem. Quem quer a via determinística roda o comando sem a flag.
- **Provider `fixture` é proibido em comando de produção.** A fixture existe para eval e
  teste; aceitá-la em `extract-legend-real` ou no `--refine-arm` publicaria observação
  fabricada como se fosse leitura (`REFINE_ARM_FIXTURE_FORBIDDEN`).
- **Extração paga nunca inventa quantidade.** A leitura só vira número quando o rótulo foi
  lido, a quantidade casa com a gramática pt-BR fechada (`1.234,50`, `61,20`, `4`), a
  unidade é reconhecida pelo catálogo e a linha está declarada legível. Qualquer dúvida —
  inclusive um `1.5` que poderia ser 1,5 ou 15 — produz item `ambiguous` **sem**
  quantidade, para o orçamentista informar.
- **Confirmação de código é fail-closed e imutável.** Código fora do catálogo
  (`ASSIGNMENT_CODE_NOT_IN_CATALOG`), fora do contrato (`CODE_NOT_IN_CONTRACT`), ambíguo
  entre grupos (`CODE_AMBIGUOUS_IN_CONTRACT`), unidade incompatível sem nota
  (`ASSIGNMENT_UNIT_INCOMPATIBLE_WITHOUT_NOTE`) e re-decisão
  (`ASSIGNMENT_ITEM_ALREADY_DECIDED`) recusam; o boletim não carrega grupo, então código
  ambíguo recusa em vez de escolher (limitação declarada do v1).
- **A quantidade confirmada manda sobre o plano de cálculo.** O plano só decompõe;
  decomposição que não fecha recusa (`CALC_PLAN_QUANTITY_MISMATCH`), e item confirmado
  sem confirmação de código bloqueia o boletim (`CALC_ASSIGNMENT_MISSING`).

## Gramática fechada de fórmulas

O escritor emite — e o avaliador da auditoria aceita — exatamente seis formas:

1. `=TRUNC(<ref>*<ref>,2)` — total de linha (quantidade × preço) e valor do período na
   PLANILHA GERAL.
2. `=ROUND(PRODUCT(<range>),2)` — subtotal de bloco.
3. `=ROUND(PRODUCT(<range>),2)-<ref>` — subtotal com desconto de vãos.
4. `=SUM(<range>)` — total da obra, total da memória do item e total geral do período.
5. `=SUM(<ref>,<ref>[,<ref>...])` — acumulado da PLANILHA GERAL, cujas células não são
   contíguas: QUANTIDADE e VALOR se alternam ao longo dos pares de medição.
6. `=<ref>-<ref>` — saldo da PLANILHA GERAL (vigente menos acumulado).

Qualquer outra fórmula encontrada no arquivo é `FORMULA_UNSUPPORTED`: a auditoria não
adivinha semântica de planilha. Como no Excel, texto e célula vazia dentro de um
intervalo de `SUM`/`PRODUCT` — ou da lista de refs do `SUM` — não entram na conta; já a
subtração exige os dois operandos numéricos. Números com mais de duas casas decimais são
recusados (`NUMBER_SCALE_UNSUPPORTED`), porque a planilha não os representaria sem perder
o valor exato.

## Layout gerado

A pasta abre pelo consolidado e fecha pelas obras:

- Aba `PLANILHA GERAL`: uma linha por código do contrato, agrupada por grupo, com
  contratado, vigente, preço, os pares QUANTIDADE|VALOR de cada medição anterior copiados
  literais, o par desta medição calculado, ACUMULADO e SALDO como fórmulas vivas e a linha
  `TOTAL GERAL`. As colunas dos pares não são constantes: saem do número de períodos.
- Aba de RE-RA (`MAPÃO - PREFEITURA` no template padrão): os deltas importados de cada
  revisão, carregados adiante junto do vigente declarado por código.
- Um par de abas por obra. `BM {obra}`: título, bloco de identificação (INTERVENÇÃO,
  ENDEREÇO, CONTRATO, MEDIÇÃO), linha de cabeçalho
  `ITEM | COD. | DESCRIÇÃO | UN | VALOR UNIT | QUANT | TOTAL`, uma linha por item e a linha
  `TOTAL DA OBRA`. `MEMÓRIA {obra}`: título, INTERVENÇÃO, cabeçalho das mesmas sete colunas
  e, por item, a linha-resumo seguida dos blocos de cálculo (rótulo, nomes dos operandos,
  valores com subtotal) e da linha `TOTAL` do item.

Sem consolidado contratual informado, a pasta é só o par BM/MEMÓRIA de cada obra — é o que
o M1 gerava.

## Referências

- [ADR-0016](../adr/0016-valuation-bounded-context.md)
- [ADR-0018](../adr/0018-valuation-consolidation-and-balance-semantics.md)
- [Acceptance Criteria](../product/ACCEPTANCE_CRITERIA.md)
- [FDD](../product/FDD.md)
- [Human in the Loop](../ai/HUMAN_IN_THE_LOOP.md)
