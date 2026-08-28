# Matriz de rastreabilidade

Status: Active  
Responsável: Product / Engineering / QA  
Última revisão: 2026-08-25

## Requisitos funcionais

| Requisito | Design/contrato | Decisão | Verificação |
|---|---|---|---|
| FR-001, FR-002 | FDD Upload; API uploads/jobs | ADR-0002/0012 | ACC-001; integration upload |
| FR-003 | FDD seleção de página; Data Flow | ADR-0005 | ACC-002; region tests |
| FR-004, FR-005 | Model Routing; Prompt Contracts | ADR-0004 | provider contract/evals |
| FR-006, FR-007 | Consensus Engine | ADR-0004/0010 | numeric/association evals |
| FR-008 | Domain Model | ADR-0005 | invariant/solver tests |
| FR-009 | FDD revisão; HITL | ADR-0006 | ACC-005/006; E2E review |
| FR-010 | API approve; Export workflow | ADR-0006 | ACC-007; approval tests |
| FR-011 | DXF Output Spec | ADR-0007 | ACC-008/009/010; CAD tests |
| FR-012, FR-013 | Data Retention | ADR-0008 | ACC-011; lifecycle test |
| FR-014 | Prompt Change Protocol | ADR-0010 | metadata contract test |

## NFRs

| Requisito | Design/controle | Verificação |
|---|---|---|
| NFR-PERF-001, NFR-PERF-002 | Processing Workflows/AWS | timed golden; 5-job load |
| NFR-PERF-003 | FDD/Canvas architecture | browser performance |
| NFR-PERF-004 | API presign | integration |
| NFR-REL-001, NFR-REL-002 | ADR-0003/workflows | idempotency/fault injection |
| NFR-REL-003 | DXF audit | export tests |
| NFR-REL-004 | Failure Modes | provider fault tests |
| NFR-REL-005 | Observability | availability dashboard |
| NFR-SEC-001 | Threat Model/API/ADR-0012 | authz negative tests |
| NFR-SEC-002, NFR-SEC-003 | AWS Deployment | infra/integration checks |
| NFR-SEC-004 | Retention | lifecycle test |
| NFR-SEC-005 | Logging policy | log scan |
| NFR-SEC-006 | Threat Model | malicious PDF tests |
| NFR-QUAL-001, NFR-QUAL-002 | Scene/DXF specs | golden/invariant tests |
| NFR-QUAL-003, NFR-QUAL-004 | ADR-0010/evals | contract + eval gate |
| NFR-QUAL-005 | Domain Model | subdetermination tests |
| NFR-OPS-001, NFR-OPS-002 | Observability/Cost Control | dashboard/budget checks |
| NFR-OPS-003, NFR-OPS-004 | Deploy/Incident docs | drills/process audit |

## Critérios globais de aceite

| Critério | Design/contrato | Verificação |
|---|---|---|
| ACC-001 | FDD autenticação/upload/processamento; API | E2E upload + reload |
| ACC-002 | FDD seleção de página | regression page classification |
| ACC-003 | Domain Model `ProviderReading` | evidence contract test |
| ACC-004 | Consensus Engine | disagreement unit tests/evals |
| ACC-005 | API review decisions; FDD review | authenticated review E2E |
| ACC-006 | Domain Model precision | underdetermination tests |
| ACC-007 | API approve; HITL | critical issue approval test |
| ACC-008 | DXF Output Spec | CAD contract tests |
| ACC-009 | DXF Output Spec audit | reopen/audit tests |
| ACC-010 | DXF package spec | export integration test |
| ACC-011 | Data Retention | delete/lifecycle test |
| ACC-012 | NFR capacity; Workflows | 5-job load test |
| ACC-013 | FDD revisão; API calibração/propostas; Domain Model | calibração/proposta API e unit tests |
| ACC-014 | ADR-0022; API `review/rectifications`; Domain Model invariantes | `tests/worker/test_review_rectification.py`, `tests/api/test_api.py`, `tests/e2e/test_full_flow.py` |
| ACC-015 | ADR-0023; API `chat-sessions`/`turns`; FDD conversa da revisão | `tests/api/test_api.py`, `tests/worker/test_chat_worker.py`, `apps/web/src/chat.test.ts` |

## Medição de obra

| Critério | Design/contrato | Decisão | Verificação |
|---|---|---|---|
| VAL-01 | Valuation Context (`WorkbookTemplate`, `import-workbook`, dossiê de recusa semântica) | ADR-0016/0018 | `tests/valuation/test_workbook_reader.py`; `tests/valuation/test_contract_diagnosis.py`; `tests/worker/test_valuation_cli.py` |
| VAL-02 | Valuation Context (`extract-legend`/`review-takeoff` implementados no M3; `suggest-codes`/`confirm-codes`/`build-calc` implementados no M4 — lexical; refino pago `--refine-arm` e extração real `extract-legend-real` implementados no M5, Sonnet aprovado na eval sintética de 2026-08-13); HITL; Model Routing | ADR-0016/0006 | `tests/valuation/test_takeoff.py`; `tests/worker/test_valuation_takeoff_fixture.py`; `tests/worker/test_valuation_takeoff_cli.py`; `tests/worker/test_valuation_takeoff_eval.py`; `tests/valuation/test_assignment.py`; `tests/valuation/test_calc.py`; `tests/valuation/test_chain_demo.py`; `tests/e2e/test_valuation_full_chain.py`; `tests/worker/test_valuation_extraction_cli.py`; `tests/worker/test_valuation_extraction_eval.py`; `tests/worker/test_valuation_legend_extraction.py` |
| VAL-03 | Valuation Context (gramática fechada, round-trip) | ADR-0016 | `tests/valuation/test_writer_roundtrip.py`; `tests/valuation/test_canonical_golden.py` |
| VAL-04 | Valuation Context (PLANILHA GERAL) | ADR-0016/0018 | `tests/valuation/test_writer_roundtrip.py`; golden M4 em `tests/valuation/test_canonical_golden.py` |
| VAL-05 | Valuation Context (aprovação do orçamentista) | ADR-0016/0006/0018 | `tests/valuation/test_export_gate.py`; `tests/worker/test_valuation_cli.py` |
| VAL-06 | Valuation Context (`compare-bulletin`, aceite Toca por runbook) | ADR-0016/0018 | `tests/valuation/test_bulletin_compare.py`; `tests/worker/test_valuation_compare_cli.py`; aceite real pendente (runbook local, fora do CI) |
| VAL-07 | API Contract "Medição de obra" + jornada de `apps/web/src/medicao/`; Valuation Context; FDD medição | ADR-0016/0028/0030 (servidor local do ADR-0020 segue válido) | `tests/e2e/test_valuation_v1_chain.py`; `tests/api/test_valuation_round_routes.py`; testes de `apps/web/src/medicao/` (vitest); `tests/worker/test_valuation_local_server.py`; homologação real da orçamentista pendente (ato humano) |
| VAL-08 | Valuation Context (`amendment_dossier.py`, `build-amendment-dossier`, rotas `/dossier`); FDD medição | ADR-0027/0018 | `tests/valuation/test_amendment_dossier.py`; `tests/worker/test_valuation_local_server.py`; `tests/e2e/test_valuation_full_chain.py`; testes de `apps/medicao` (vitest) |
| VAL-11 | Aprovação nominal do orçamento (`EstimateApproval`, portão próprio sem contrato, rotas `approve`/`export`, papel `aprovador`, coluna de autor da montagem) | ADR-0046/0027 | `tests/valuation/test_estimate_export_gate.py`; `tests/api/test_estimate_round_routes.py`; `tests/e2e/test_estimate_rounds_v1.py`; testes de `apps/web/src/orcamento/` (vitest); ato nominal real pendente (ato humano) |
| VAL-10 | Acervo de catálogos da plataforma (`reference_catalogs.py`, `ReferenceCatalogRecord`, rotas `/v1/platform/reference-catalogs`, escolha sob a rodada, procedência na `CascadeEntry`) | ADR-0047/0027 | `tests/api/test_reference_catalogs.py`; `tests/api/test_estimate_round_routes.py`; `tests/e2e/test_reference_catalog_chain.py`; testes de `apps/web/src/plataforma/` e `apps/web/src/orcamento/` (vitest); publicação dos arquivos reais em homologação pendente (ato do operador) |
| VAL-12 | Índice de embeddings publicado no acervo e braço semântico no recompute (`index-catalog` do CLI, tabela `reference_catalog_embeddings`, rotas `/v1/platform/reference-catalog-indexes`, resolução por digest, notas de degradação por fonte) | ADR-0054/0021/0047 | `tests/valuation/test_matcher_golden.py` (gate `recall@20 = 100%` do braço híbrido, exige catálogo real + índice + cache locais); `tests/api/test_reference_catalog_indexes.py` (publicação, quatro recusas e teto próprio de leitura); `tests/api/test_migrations.py`; `tests/api/test_estimate_semantic_arm.py` (leitura do índice nas DUAS jornadas: `GET` provado sem chamada paga por adapter que falha se tocado, degradação declarada por fonte, cobertura parcial na cascata, índice recusado na amarração, entitlement que degrada em vez de recusar, e nenhum vetor de consulta persistido); `build_hybrid_code_suggestions_over_cascade` (`sco_matching.py`) e `compute_cascade_suggestions` (`suggestions.py`) são a fiação; a **tela** está em `apps/web/src/orcamento/labels.test.ts` e `OrcamentoApp.test.tsx` (`EstadoDoBracoSemantico`: ler não paga, recalcular pode pagar, braço em palavra e notas do servidor como vieram) e em `apps/web/src/plataforma/` (`api.test.ts`, `labels.test.ts` e `PlatformApp.test.tsx`: listar, publicar e retirar o índice, estado por extenso, os quatro códigos de recusa em português e nenhuma sugestão de que a tela constrói índice); o recompute real contra o índice pago em homologação segue pendente (ato do operador) |
| VAL-13 | Cardinalidade N:N entre elemento da prancha e serviço do catálogo (par `(item_id, code)`, fechamento de pacote, `ContributionBasis`, derivação entre serviços, digest governado pela versão declarada) | ADR-0053/0027/0045/0048 | `tests/valuation/test_content_digest.py` (mecanismo de poda por versão e as duas âncoras de digest anteriores à mudança); `tests/valuation/test_haulage.py` (tabela de derivação de transporte como dado e o gate dos sete casos reais do Campo do Toca); **implementação da cardinalidade em si ainda não começou** — o par, o fechamento e os builders por serviço são fatias próprias (issues #75 a #81) |
| VAL-09 | Valuation Context (`PriceOrigin`, `emop.py`, `composition.py`, `estimate.py`, cascata como dado) | ADR-0027 | `tests/valuation/test_emop.py`; `tests/valuation/test_composition.py`; `tests/valuation/test_estimate.py`; `tests/valuation/test_assignment.py`; golden `estimate-demo` em `tests/valuation/test_canonical_golden.py`; `tests/e2e/test_valuation_full_chain.py` |

## Golden acceptance

| Critério | Design/contrato | Verificação |
|---|---|---|
| ACC-GUA-001, ACC-GUA-002, ACC-GUA-003, ACC-GUA-004 | PRD/FDD/DXF Spec | golden Guaxindiba + CAD/domain approval |
| ACC-TOC-001, ACC-TOC-002, ACC-TOC-003, ACC-TOC-004 | FDD regions; DXF `DETALHES` | golden Toca + region/detail tests |
| ACC-RAU-001, ACC-RAU-002, ACC-RAU-003, ACC-RAU-004, ACC-RAU-005, ACC-RAU-006 | FDD/HITL/DXF Spec | golden Raul + spline/provenance/domain approval |

Atualize esta matriz no mesmo change que cria, remove ou muda um requisito.

## Cobertura executável atual

| Requisito/critério | Evidência executável atual | Estado |
|---|---|---|
| ACC-002 | `tests/worker/test_ingest.py`; nenhuma página é descartada | Parcial |
| ACC-003 | `VisionProposalSet` e `ReviewPacket` preservam origem, bbox, digest e texto | Parcial |
| ACC-004 | `AssociationSet` preserva alternativas e não faz associação irreversível | Parcial |
| ACC-006 | `tests/core/test_scene.py` | Implementado no domínio |
| ACC-008 | `tests/worker/test_dxf.py`; unidades, layers e XDATA | Parcial |
| ACC-009 / NFR-REL-003 | `tests/worker/test_export_worker.py`: reabertura, `ezdxf.audit()` e publicação só após auditoria aprovada | Implementado no fluxo autenticado |
| ACC-010 | conteúdo obrigatório do ZIP conferido no pacote publicado, incluindo `aprovacao.json` | Implementado no fluxo autenticado |
| ACC-005 | `HumanDecision` e nova revisão em `approve_rectangle` | Parcial |
| ACC-005 / NFR-SEC-001 / NFR-REL-001 | `tests/api/test_api.py`: sessão de revisão tenant-scoped, papel derivado do JWT, idempotência, conflito e leitura imutável | Implementado no contrato local |
| ACC-003 / ACC-004 / ACC-006 / ACC-007 | `tests/api/test_api.py` e `tests/worker/test_rectangle_solver.py`: pacote/evidência, associação explícita, ausência de cena sem decisão e cena rascunho não exportável | Parcial, golden real pendente |
| FR-004 / FR-005 / FR-014 / NFR-QUAL-003 / NFR-REL-004 | `tests/worker/test_providers.py` e `tests/worker/test_local_queue.py`: contratos estritos, lineage, faults e snapshot sintético injetado | Implementado offline; providers reais pendentes |
| ACC-001 / NFR-PERF-004 | OIDC, PUT S3 assinado com checksum, job persistente e retomada por projeto/job | Implementado no lifecycle local |
| ACC-007 | solver não exporta rascunho, rejeita conflicts críticos e `POST /approve` exige as três verificações explícitas | Implementado no fluxo autenticado |
| ACC-007 / ACC-GUA-001 / ACC-GUA-002 | declaração nominal por critério de escopo na aprovação — coberto pela cena (`resolved`) × reconhecido como pendente (`accepted`), conjuntos disjuntos e separados no `aprovacao.json`; blocker de geometria nunca é declarável (`tests/api/test_api.py`, `tests/e2e/test_full_flow.py`) | Implementado no contrato; declaração real pendente |
| ACC-007 / ACC-GUA-001 | paridade do critério nos dois motores: a cena traçada carrega a issue crítica com o texto do caso e não exporta sem declaração (`tests/worker/test_tracing.py`, `tests/worker/test_trace_solve_worker.py`, `tests/worker/test_criteria.py`) | Implementado no fluxo autenticado |
| ACC-005 | `tests/worker/test_review_seed.py`: pacote autorizado ligado ao job sem fabricar decisão e recusando divergência de evidência | Implementado no fluxo autenticado |
| ACC-013 / ACC-006 | geometria aceita sobrevive a decisões seguintes; calibração inválida gera `CALIBRATION_SUPERSEDED` em vez de reprojetar | Implementado no fluxo autenticado |
| ACC-014 / ACC-005 | `tests/worker/test_review_rectification.py`, `tests/api/test_api.py` e `tests/e2e/test_full_flow.py`: sucessão declarada de decisão (id novo citando o anterior, revisão nova, decisão anterior preservada), matriz de recusas (`READING_NOT_DECIDED`, `RECTIFICATION_TARGET_STALE`, `RECTIFICATION_ALREADY_APPLIED`, `READING_ALREADY_DECIDED`) e invalidação para frente com `READING_DECISION_SUPERSEDED` sem tocar aprovação nem artefato | Implementado no fluxo autenticado |
| ACC-015 | `apps/web/src/chat.test.ts`: rascunho vira formulário sem carregar medida, leitura já decidida não vira decisão, pendência não trunca nem duplica na nota do aceite; `tests/api/test_api.py` e `tests/worker/test_chat_worker.py` cobrem o lado do servidor | Implementado offline (fixture); via paga pendente |
| ACC-008 / ACC-009 / ACC-010 | `export_artifacts` registra chave, digest e auditoria; download só por URL assinada tenant-scoped | Implementado no fluxo autenticado |
| ACC-013 | `tests/worker/test_proposal_calibration.py` e `tests/api/test_api.py`: anchors, transform, papel, idempotência e entidade approximate | Implementado no contrato local |
| ACC-GUA-003 | propostas de cotas globais com blockers explícitos | Preparado para revisão |
| ACC-TOC-001 / ACC-TOC-003 | review packet separa campo, detalhes e associação pendente | Preparado para revisão |
| ACC-RAU-001 / ACC-RAU-002 / ACC-RAU-005 | review packet não promove contorno ou círculo ambíguos | Preparado para revisão |
| VAL-03 | `tests/valuation/`: truncamento, catálogo, validadores, round-trip centavo a centavo e golden do canônico do `make valuation-demo` | Implementado no M1 sintético |
| VAL-01 | `tests/valuation/test_workbook_reader.py`, `tests/valuation/test_contract_diagnosis.py`, `tests/valuation/test_catalog.py` e `tests/worker/test_valuation_cli.py`: consolidado e catálogo lidos do mesmo arquivo com layout como dado (hierarquia por colunas, nota editorial, item sem cotação), original intacto, notas da leitura no relatório e recusa semântica agregada em dossiê sem publicar artefato | Implementado no M2.1 sintético; aceite do arquivo real bloqueado por decisão de domínio |
| VAL-04 | `tests/valuation/test_writer_roundtrip.py` e o golden M4: PLANILHA GERAL consolidando quatro obras (a quarta nascida do takeoff revisado), código medido em duas, acumulado e saldo vivos, e a GERAL gerada reimportável como base do período seguinte | Implementado no M2 sintético, golden estendido no M4 |
| VAL-05 | `tests/valuation/test_export_gate.py` e `tests/worker/test_valuation_cli.py`: sem aprovação nominal válida, fora da sequência de períodos ou acima do saldo, nenhuma planilha é publicada | Mecanismo implementado; ato nominal real pendente |
| VAL-02 | `tests/valuation/test_takeoff.py`, `tests/worker/test_valuation_takeoff_fixture.py`, `tests/worker/test_valuation_takeoff_cli.py` e `tests/worker/test_valuation_takeoff_eval.py`: legenda quantificada extraída por fixture e revisada pelo orçamentista (`proposed`/`ambiguous` → `confirmed`, re-decisão recusada), com gate `make valuation-eval`; `tests/valuation/test_assignment.py`, `tests/valuation/test_calc.py`, `tests/valuation/test_chain_demo.py` e `tests/e2e/test_valuation_full_chain.py`: sugestão lexical determinística, confirmação fail-closed e boletim/memória do takeoff confirmado, incluindo a cadeia inteira pelos comandos do CLI; `tests/worker/test_valuation_extraction_cli.py`, `tests/worker/test_valuation_extraction_eval.py` e `tests/worker/test_valuation_legend_extraction.py`: refino pago como permutação anotada da shortlist, extração real atrás de teto de gasto e allowlist, e o gate `make valuation-extraction-eval` offline | Implementado no M4 sintético; refino pago e extração real implementados no M5, Sonnet aprovado na eval paga sintética (2026-08-13) |
| VAL-06 | `tests/valuation/test_bulletin_compare.py` e `tests/worker/test_valuation_compare_cli.py`: BM real lido por valores em cache com layout do template, comparação código a código sem tolerância, código duplicado recusado nos dois lados, exit 0/1/2 | Mecanismo implementado no M5; aceite real da Toca pendente (runbook local) |
| VAL-08 | `tests/valuation/test_amendment_dossier.py`: rejeição de código de item confirmado vira item do dossiê com justificativa obrigatória, dossiê vazio é desfecho válido, rodada incompleta recusa, item incoerente recusa por construção e o JSON nunca carrega chave de preço; `tests/worker/test_valuation_local_server.py` e `tests/e2e/test_valuation_full_chain.py`: par `/dossier/build`+`/dossier` com revalidação na leitura e comando `build-amendment-dossier` na cadeia | Implementado no M8 fase A; pedido real de aditivo permanece ato humano |
| VAL-09 | `tests/valuation/test_emop.py` (leitor .DBF fail-closed, layout como dado, fixture fonte-única adulterável), `tests/valuation/test_composition.py` (preço recomputado com truncamento conservador por linha, compilação a catálogo `origin=composition`), `tests/valuation/test_estimate.py` (três origens com proveniência por linha, `unpriced_item_ids`, recusas de cascata/citação, revalidação na releitura), `tests/valuation/test_assignment.py` (retrocompatibilidade M4–M7 e confirmação citando fonte), golden `estimate-demo.canonical.json` e cadeia pelos comandos reais no e2e | Implementado no M8 fase B, offline; importação EMOP real pendente da assinatura GRE (ato comercial) |

"Parcial" significa que o mecanismo existe, mas o aceite do golden case real ou
a integração SaaS ainda não foi concluído.
