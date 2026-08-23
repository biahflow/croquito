# Critérios de aceite do MVP

Status: Accepted for MVP  
Responsável: Product / Domain Reviewer  
Última revisão: 2026-08-17

## Critérios globais

| ID | Critério |
|---|---|
| ACC-001 | Usuário convidado envia PDF e acompanha um job sem perder estado ao recarregar. |
| ACC-002 | Página nunca é descartada somente por baixa cobertura de tinta. |
| ACC-003 | Cada leitura mostra texto original, região e provedores. |
| ACC-004 | Divergência numérica impede confirmação automática. |
| ACC-005 | Usuário corrige medida e cria nova revisão rastreável. |
| ACC-006 | Entidade subdeterminada fica `unresolved` ou é aceita como `approximate`. |
| ACC-007 | Aprovação é bloqueada por issue crítica. |
| ACC-008 | DXF usa unidades, layers e entidades definidas na especificação. |
| ACC-009 | DXF reabre sem erro e a auditoria não encontra corrupção. |
| ACC-010 | ZIP contém DXF, preview, auditoria, quantitativos e hipóteses. |
| ACC-011 | Exclusão remove acesso imediatamente e artefatos expiram em sete dias. |
| ACC-012 | Cinco jobs simultâneos preservam isolamento e idempotência. |
| ACC-013 | Profissional calibra proposta CV contra cena métrica, aceita ou rejeita-a de forma rastreável e nunca a promove a `exact`. |
| ACC-014 | Decisão de leitura já registrada é corrigida por ato declarado: a anterior permanece legível na revisão em que foi tomada, a leitura não volta a proposta, a associação é redeclarada e a geometria que dependia dela fica bloqueada por issue crítica até ser refeita — sem tocar aprovação ou pacote publicados ([ADR-0022](../adr/0022-declared-rectification-of-review-decisions.md)). |
| ACC-015 | Rascunho do agente de conversa nunca vira ato: "Usar este rascunho" apenas pré-preenche o formulário existente — com a justificativa editável e o valor escrito vindo do pacote, nunca do texto do agente —, leitura já decidida não é oferecida e o envio continua sendo o comando humano ([ADR-0023](../adr/0023-review-chat-as-an-observational-agent.md)). |

## Medição de obra (planilha MAPÃO)

| ID | Critério |
|---|---|
| VAL-01 | Planilha de medição do cliente é importada com o layout declarado como dado, sem perder ou reescrever célula do original. Entregue no M2 sintético (`import-workbook`) e estendida no M2.1 ao layout do MAPÃO real, com o que a leitura observou no bloco `notes` do `import-report.json` e a recusa semântica agregada em `import-diagnosis.json`. Evidência em `tests/valuation/test_workbook_reader.py`, `tests/valuation/test_contract_diagnosis.py`, `tests/valuation/test_catalog.py` e `tests/worker/test_valuation_cli.py`. |
| VAL-02 | Associação item → código SCO é proposta por modelo e confirmada por orçamentista; nenhum código é atribuído em silêncio. A etapa anterior da cadeia — legenda quantificada extraída da prancha e revisada pelo orçamentista — tem mecanismo desde o M3 (`extract-legend`/`review-takeoff`, gate `make valuation-eval`), com a mesma disciplina `proposed`/`ambiguous` → `confirmed` sem decisão silenciosa. Entregue no M4: sugestão lexical determinística (`suggest-codes`) + confirmação fail-closed (`confirm-codes`) + memória/boletim (`build-calc`), com evidência em `tests/valuation/test_assignment.py`, `tests/valuation/test_calc.py`, `tests/valuation/test_chain_demo.py` e `tests/e2e/test_valuation_full_chain.py`. O refino por **modelo pago** foi entregue no M5 (`suggest-codes --refine-arm`): o provider só reordena e anota a shortlist lexical (permutação exata, fail-closed), a eval paga sintética de 2026-08-13 aprovou o Sonnet como braço das duas tarefas ([Model Routing](../ai/MODEL_ROUTING.md)) e a evidência mecânica está em `tests/valuation/test_assignment.py`, `tests/worker/test_valuation_extraction_cli.py` e `tests/worker/test_valuation_extraction_eval.py`. |
| VAL-03 | A planilha gerada, reaberta e recalculada, é idêntica ao JSON canônico centavo a centavo; divergência não publica. Entregue no M1 e coberto por `tests/valuation/`. |
| VAL-04 | A PLANILHA GERAL consolida as obras e fecha com a soma dos boletins, com acumulado e saldo por item. Entregue no M2 sintético, com evidência no round-trip da GERAL (`tests/valuation/test_writer_roundtrip.py`) e no golden M4 (`tests/valuation/golden/valuation-demo-m4.canonical.json`), que substituiu o golden M2 quando o M4 estendeu os dados sintéticos. |
| VAL-05 | Medição só é exportada ao cliente após aprovação nominal do orçamentista responsável. Mecanismo entregue no M2 (`export_errors`/`ensure_exportable` e aprovação amarrada por digest); desde a [F-028](../features/F-028-boletim-medicao-web/feature.md) (2026-08-20) o ato e a exportação auditada existem pelas rotas `/v1` e pela jornada web — exportar sem aprovação válida é recusa de rota (`VALUATION_EXPORT_BLOCKED`), e recalcular preserva a aprovação anterior como caduca (`APPROVAL_CONTENT_MISMATCH`). O ato nominal sobre medição real permanece pendente (ato do usuário, pós-deploy). |
| VAL-07 | A orçamentista homologa a cadeia de medição pela jornada autenticada de `apps/web` sobre a API `/v1` ([ADR-0028](../adr/0028-medicao-na-api-v1-autenticada.md), entregue em [F-003](../features/F-003-medicao-v1-migration/feature.md)): a rodada é recurso — ela lista, abre e cria rodada, subindo o catálogo pelo presign —, a decisão é por item, nada nasce pré-marcado, identidade e horário são do servidor, o total aparece só quando recomputado pelo domínio, e item sem código vira candidato a aditivo. Mutação cita `base_version` e manda `Idempotency-Key`; `409 REVISION_CONFLICT` preserva o formulário e oferece recarregar. O overlay do takeoff é reconstruído fora do request path ([ADR-0030](../adr/0030-overlay-do-takeoff-reconstruido-na-fila.md)) e, enquanto o desenho é do pacote anterior, a tela declara isso em palavra. A busca de código é léxica na digitação e o braço híbrido é pago, atrás do entitlement contratual — nunca léxico fingindo ser híbrido. A shortlist gravada é recalculável (`POST .../code-suggestions/recompute`) e recusa fechado quando carrega refino pago (`SUGGESTIONS_ALREADY_REFINED`). Evidência: `tests/e2e/test_valuation_v1_chain.py` (cadeia inteira por HTTP), `tests/api/test_valuation_round_routes.py` e os testes de `apps/web/src/medicao/`. O servidor local do [ADR-0020](../adr/0020-local-homologation-server-for-valuation.md) continua válido como ferramenta do operador (`tests/worker/test_valuation_local_server.py`). A homologação real pela orçamentista do domínio permanece pendente como ato humano. |
| VAL-06 | O BM gerado de uma obra confere com o BM real do cliente centavo a centavo: `compare-bulletin` casa código a código sem tolerância e `zero_cent` só é verdadeiro sem nenhum diff numérico nem código ausente de um lado. Mecanismo entregue no M5 com evidência em `tests/valuation/test_bulletin_compare.py` e `tests/worker/test_valuation_compare_cli.py`; o aceite real da Toca (extração paga da prancha do projetista, revisão e confirmação reais do orçamentista, comparação com zero centavo) permanece pendente, roteirizado em [RUNBOOK_VALUATION_TOCA_ACCEPTANCE](../operations/RUNBOOK_VALUATION_TOCA_ACCEPTANCE.md). |
| VAL-08 | Em obra licitada, item confirmado no takeoff cujo código foi rejeitado vira item do **dossiê do aditivo** (RE-RA), com a nota da rejeição como justificativa obrigatória. O dossiê é artefato de fechamento da rodada (decisão de código pendente recusa `AMENDMENT_DOSSIER_ASSIGNMENTS_INCOMPLETE`), não carrega campo de preço por construção e não cria nem altera RE-RA — instrui a conversa com a prefeitura. Mecanismo entregue no M8 fase A (`build_amendment_dossier`, CLI `build-amendment-dossier`, rotas locais `POST /dossier/build` + `GET /dossier`, seção da tela com o dossiê do servidor e a lista do cliente rebaixada a prévia), com evidência em `tests/valuation/test_amendment_dossier.py`, `tests/worker/test_valuation_local_server.py`, `tests/e2e/test_valuation_full_chain.py` e nos testes de `apps/medicao` ([ADR-0027](../adr/0027-price-source-provenance-and-bid-boundary.md)). |
| VAL-11 | O orçamento só é despachado depois de **aprovado nominalmente por quem não o montou**. Montar deixou de publicar: `POST .../estimate` monta, `POST .../estimate/approve` assina (papel `aprovador`) e `POST .../estimate/export` publica atrás de portão fail-closed do domínio (`Estimate.ensure_exportable()`, sem `ContractWorkbook` — saldo, período e contrato não existem deste lado da fronteira). A segregação é de identidade, não de papel: quem montou recebe `403 ESTIMATE_SELF_APPROVAL_FORBIDDEN` mesmo acumulando os dois papéis, e a recusa não devolve o subject de quem montou. A assinatura é amarrada ao `content_digest()`, que **exclui a própria aprovação** — assinar não muda o que foi assinado —, e remontar torna-a **caduca** (`stale`, dois digests) em vez de apagá-la, com o despacho recusando `APPROVAL_CONTENT_MISMATCH` até um ato novo. Despachar é do `orcamentista`: assinar é assumir o conteúdo, despachar é operar o envio. Mecanismo entregue na [F-035](../features/F-035-aprovacao-do-orcamento/feature.md) (2026-08-23, [ADR-0046](../adr/0046-aprovacao-do-orcamento-base.md)), com evidência em `tests/valuation/test_estimate_export_gate.py`, `tests/api/test_estimate_round_routes.py`, `tests/e2e/test_estimate_rounds_v1.py`, `tests/e2e/test_reference_catalog_chain.py` e nos testes de `apps/web/src/orcamento/`. O ato nominal sobre um orçamento real permanece pendente (ato do usuário, pós-deploy). |
| VAL-10 | A tabela de preços do orçamento é **escolhida de uma lista publicada pela plataforma**, não obtida e enviada como arquivo pelo cliente. Publicar é ato de `platform_operator` e vale para todos os tenants; cada publicação é imutável e endereçada pelo digest do arquivo (data-base nova é entrada nova, nunca substituição — `REFERENCE_CATALOG_ALREADY_PUBLISHED`), e retirar de circulação não apaga linha nem objeto, porque a rodada que já a citou continua funcionando. A plataforma não distribui o que não pode distribuir: `emop` (paga) e `composition` (do cliente) recusam a publicação com `REFERENCE_CATALOG_ORIGIN_NOT_PUBLISHABLE` e continuam entrando pelo upload de quem tem a licença. A cascata declara a **procedência** de cada fonte (`DO ACERVO` / `TABELA PRÓPRIA`), que é quem publicou o arquivo e não de onde o preço vem — e quem publicou não muda o que o arquivo diz: o orçamento montado sobre o acervo é linha a linha idêntico ao montado sobre o mesmo arquivo enviado pelo cliente. O registro do acervo é a única tabela do schema sem `tenant_id` ([ADR-0047](../adr/0047-acervo-de-catalogos-da-plataforma.md)), o objeto vive fora de `tenants/` e **nenhuma rota assina URL dele**. Mecanismo entregue na [F-037](../features/F-037-acervo-de-catalogos/feature.md) (2026-08-22), com evidência em `tests/api/test_reference_catalogs.py`, `tests/api/test_estimate_round_routes.py`, `tests/e2e/test_reference_catalog_chain.py` e nos testes de `apps/web/src/plataforma/` e `apps/web/src/orcamento/`. A publicação dos arquivos reais em homologação permanece pendente (ato do operador, pós-deploy). |
| VAL-09 | O orçamento-base de **pré-licitação** nasce de uma cascata de fontes declarada como dado (a ordem dos `--catalog` do comando, nunca "SCO primeiro" em código) com **proveniência por linha**: cada linha do `Estimate` declara origem (`sco`/`emop`/`composition`), digest do catálogo e data-base do preço, e a releitura recusa linha que aponte fonte fora da cascata. A confirmação de código cita a fonte (`ASSIGNMENT_CATALOG_REQUIRED`); item sem preço em fonte alguma sai declarado em `unpriced_item_ids`, nunca precificado por semelhança; a medição licitada segue recusando qualquer catálogo não-SCO (`BULLETIN_PRICE_ORIGIN_FORBIDDEN`). Mecanismo entregue no M8 fase B (`import-emop`, `import-compositions`, `suggest-codes`/`confirm-codes` com cascata, `build-estimate`, demo `make valuation-estimate-demo` com golden), com evidência em `tests/valuation/test_emop.py`, `tests/valuation/test_composition.py`, `tests/valuation/test_estimate.py`, `tests/valuation/test_assignment.py`, `tests/valuation/test_canonical_golden.py` e `tests/e2e/test_valuation_full_chain.py` ([ADR-0027](../adr/0027-price-source-provenance-and-bid-boundary.md)). |

O M1 entregou o trecho final da cadeia sem IA: importação do catálogo de preços de
referência, medição canônica de uma obra, planilha com BM e MEMÓRIA e auditoria de
round-trip. O M2 fechou as duas pontas desse trecho: importação do consolidado contratual
com RE-RA, consolidação multi-obra na PLANILHA GERAL e portão de aprovação e saldo antes da
exportação. Dinheiro truncado em duas casas e célula fixada por divergência de
truncamento continuam invariantes verificados por teste
([Valuation Context](../architecture/VALUATION_CONTEXT.md),
[ADR-0018](../adr/0018-valuation-consolidation-and-balance-semantics.md)).

## Identificador documental e código de máquina

O ID escrito aqui usa hífen (`ACC-GUA-001`); o código que viaja no sistema usa underscore
(`ACC_GUA_001`), porque `Issue.code` aceita apenas `^[A-Z0-9_]{3,64}$`. É o mesmo critério
com duas grafias, e a conversão é direta. O texto da linha correspondente desta tabela é o
que deve ser declarado no seed (`--required-criteria ACC_GUA_001=<texto>`) para chegar à
tela de revisão e ao pacote entregue
([ADR-0017](../adr/0017-per-criterion-coverage-declaration-and-trace-parity.md)).

## Campo do Guaxindiba — fácil

| ID | Critério |
|---|---|
| ACC-GUA-001 | Perímetro, linha central, círculo, áreas e gols são entidades CAD limpas. |
| ACC-GUA-002 | Muros, portões e patamares usam layers distintos. |
| ACC-GUA-003 | Cotas confirmadas são numericamente exatas. |
| ACC-GUA-004 | Revisão de um golden run dura no máximo 1 minuto. |

## Campo da Toca — médio

| ID | Critério |
|---|---|
| ACC-TOC-001 | Planta principal e desenhos auxiliares são classificados separadamente. |
| ACC-TOC-002 | Detalhes são blocos/grupo `DETALHES`, sem alterar escala principal. Atendido por `TraceAcceptance.detail_groups`: cada detalhe é resolvido independente (escala própria; `sketch` para desenhos sem escala) e desenhado com moldura em layer `DETALHES` e título, sem blocos/INSERT — ver [Trace Stage](../architecture/TRACE_STAGE.md). |
| ACC-TOC-003 | Acessos, portões e alambrados mantêm associação com suas anotações. |
| ACC-TOC-004 | Revisão de um golden run dura no máximo 3 minutos. |

## Praça Raul Campelo — difícil

| ID | Critério |
|---|---|
| ACC-RAU-001 | Contorno orgânico é spline revisável e marcado `approximate`. |
| ACC-RAU-002 | Círculos e patamares cotados usam `CIRCLE`/`ARC` quando determinados. |
| ACC-RAU-003 | ATI, playground, trailer, quiosque, bancos e equipamentos usam layers/blocos. |
| ACC-RAU-004 | Curvas não apresentam serrilhamento excessivo nem falsa exatidão. |
| ACC-RAU-005 | Relatório explica posições ou curvas não determináveis pelas cotas. |
| ACC-RAU-006 | Revisão de um golden run dura no máximo 5 minutos. |

## Aprovação do domínio

O revisor registra nome/papel, revisão aprovada, data, ressalvas e evidência de
abertura no AutoCAD. A aprovação não significa que o croqui original possui dados
suficientes; significa que o DXF representa corretamente cotas e hipóteses aceitas.
