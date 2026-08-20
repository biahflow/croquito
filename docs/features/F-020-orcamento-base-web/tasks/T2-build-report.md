# BUILD REPORT — F-020 / T2 — Escritor `.xlsx` do orçamento-base e auditor próprio

```text
Status: BUILD_COMPLETE

Files changed:
  - packages/valuation/src/croquito_valuation/template.py
      EstimateColumns (as sete colunas do boletim + source/FONTE +
      unit_price_with_bdi/VALOR UNIT. C/ BDI, letras A..I) e EstimateLayout
      (título, header_row, labels do bloco de identificação, do bloco de
      totais e do bloco de itens sem preço) novos; WorkbookTemplate ganha o
      campo opcional `estimate: EstimateLayout | None = None` e
      validate_sheet_names passa a incluir estimate.sheet_name na checagem de
      colisão quando declarado; default_template() passa a preencher a seção
      com as colunas A(ITEM)..I(TOTAL) — escopo do contrato T2, seção
      "aditiva e opcional" (nada da forma existente do template mudou).

  - packages/valuation/src/croquito_valuation/estimate_workbook.py (novo)
      Módulo adaptador (não generalização) do escritor/auditor da medição:
      plan_estimate_workbook (plano célula a célula, com pinned cells para
      divergência de truncamento em ponto flutuante, igual à medição),
      write_estimate_workbook (openpyxl + gravação atômica) e
      audit_estimate_workbook (reabre com openpyxl, reusa
      canonical.canonicalize_workbook como biblioteca do avaliador de
      fórmulas da gramática fechada, compara célula a célula com uma
      comparação própria — sem estender canonical.audit_workbook, que exige
      Valuation/WorksiteBulletin) — escopo central do contrato T2.

  - services/worker/src/croquito_worker/valuation/cli.py
      Import de EstimateAuditReport/audit_estimate_workbook/
      write_estimate_workbook; constantes ESTIMATE_WORKBOOK_FILENAME
      ("orcamento.xlsx"), ESTIMATE_WORKBOOK_AUDIT_FILENAME e
      _PENDING_ESTIMATE_WORKBOOK_FILENAME; EstimateDemoResult ganha
      workbook_path (Path | None), workbook_audit e workbook_audit_path;
      run_export_estimate_workbook (novo) espelha run_export_valuation
      exatamente (nome pendente -> auditoria -> os.replace só com status
      "ok" -> pendente removido no finally); run_estimate_demo passa a
      exportar a planilha depois de gravar o estimate.json;
      _estimate_audit_failure_payload (novo, espelha
      _audit_failure_payload) e _command_estimate_demo passam a reportar
      workbook/workbook_sha256/workbook_audit no sucesso e o payload de
      falha da auditoria quando workbook_path é None — escopo do contrato T2
      ("estimate-demo passa a também exportar a planilha com o portão
      fail-closed no desenho EXATO de run_export_valuation").

  - tests/valuation/test_estimate_workbook.py (novo)
      6 testes sobre um Estimate sintético próprio (duas linhas, mesmo preço
      unitário, BDI 10%, desenhado para que a diferença dos totais truncados
      diverja de TRUNC(percentual sobre o total) — prova a decisão 4 do
      ADR-0038): colunas/labels novas + FONTE por linha; bloco de totais
      (TOTAL SEM BDI, BDI como diferença dos truncados via fórmula
      "=I12-I10", TOTAL GERAL); item sem preço no próprio bloco sem nenhuma
      célula de preço; auditoria limpa no caminho feliz; célula adulterada
      (tamper_cell) derruba a própria célula E o total que a referencia,
      status "divergent"; run_export_estimate_workbook não publica nada
      quando a auditoria (monkeypatchada) diverge, e o pendente não sobra no
      diretório.

  - tests/valuation/test_canonical_golden.py
      Import de default_template + GOLDEN_ESTIMATE_WORKBOOK_PATH; 3 testes
      novos espelhando o mecanismo M1/M8 já existente: golden bate byte a
      byte (test_estimate_workbook_canonical_matches_the_versioned_golden),
      idempotência de conteúdo lógico em duas execuções do
      estimate-demo (test_estimate_workbook_is_idempotent_in_logical_content,
      espelha test_synthetic_workbook_is_idempotent_in_logical_content) e um
      teste de asserções fixando as colunas novas e o bloco de totais do
      golden (test_the_estimate_workbook_golden_carries_the_new_columns_and_the_bdi_totals)
      — escopo do contrato T2.

  - tests/valuation/golden/estimate-workbook.canonical.json (novo)
      Gerado pelo caminho oficial (run_estimate_demo + canonicalize_workbook,
      mesmo json.dumps(indent=2, ensure_ascii=False, sort_keys=True) dos
      goldens existentes) — canônico da planilha do orçamento-base da fixture
      determinística (5 linhas, 3 origens, 1 item sem preço).

Validation executed:
  - uv run ruff check . -> All checks passed!
  - uv run ruff format --check . -> 389 files already formatted
  - uv run mypy packages/core/src packages/valuation/src services/api/src
    services/worker/src tests -> Success: no issues found in 189 source files
  - uv run python scripts/check_docs.py -> Documentação válida: 223 arquivos
    Markdown, paridade de lifecycle verificada.
  - uv run python -m croquito_core.schema_export --check-dir packages/contracts
    -> ok (sem drift; T2 não mexeu em SceneRevision/Estimate)
  - npm run contracts:check -> ok
  - npm run web:check (tsc -b && vite build) -> build ok
  - make infra-check (terraform fmt -check -recursive infra) -> ok
  - make check (comando completo) -> todos os passos acima em sequência, verde
  - make test (uv run pytest + npm run web:test) -> 1652 passed, 13 skipped,
    47 warnings (125.39s) + 32 arquivos / 581 testes web passed
  - uv run pytest tests/valuation/test_estimate_workbook.py
    tests/valuation/test_canonical_golden.py
    tests/valuation/test_writer_roundtrip.py -x -q -> 36 passed
  - uv run pytest tests/valuation -q -> toda a suíte de valuation verde
    (mesma contagem incluída no make test acima)
  - make valuation-demo -> exit 0, status "ok", 524 células conferidas, 0
    findings, total_amount "38859.46" (boletim intacto)
  - make valuation-estimate-demo -> exit 0, status "ok", workbook
    "output/valuation-estimate-demo/orcamento.xlsx" publicado,
    workbook_audit "output/valuation-estimate-demo/orcamento-audit.json",
    total_amount "71516.83" (igual ao golden do estimate.json que T1 já
    fixava)

Validation skipped: none

Unavailable capabilities: none

Assumptions:
  - Ordem das colunas do orçamento (A Item, B Cód., C FONTE, D Descrição, E
    Un, F Valor unit., G Valor unit. c/ BDI, H Quant., I Total) segue a
    disposição do mock/orcamento.html (Tela 7); o Design Approval Package
    aprova só o CONJUNTO e os NOMES das duas colunas novas (FONTE, VALOR
    UNIT. C/ BDI), listando "forma do escritor e do auditor de planilha"
    como explicitamente NÃO aprovada — a posição exata é decisão minha,
    baixo risco por seguir o material já revisado.
  - Copy do bloco de totais/itens sem preço ("TOTAL SEM BDI", "BDI (X%)",
    "TOTAL GERAL", "ITENS SEM PREÇO NA CASCATA") é texto meu, não aprovado
    ("Copy final" está na lista do que a Tela 7 explicitamente não aprova) —
    aceitável para T2 porque a task entrega o motor, não a superfície final;
    fica sujeito a revisão de copy antes de qualquer exposição a usuário.
  - Célula FONTE imprime `f"{origin.upper()} {reference_month}"` (ex.: "SCO
    2026-04") em vez de um rótulo humano fabricado (a mock usa "Composição",
    mas o enum PriceOrigin só tem "composition" em inglês/minúsculo); preferi
    derivar direto do dado a inventar vocabulário novo.
  - Aba do orçamento não imprime plate_id/page_number/image_sha256/
    source_pdf_sha256 nem a lista completa da cascata (a mock mostra "Fonte
    1/2/3" com sha256 truncado e "Emitido em" no cabeçalho); Estimate não tem
    campo de timestamp de emissão, e nenhum desses dados está na lista de
    conteúdo que o contrato pede ("uma linha por EstimateLine ... bloco de
    itens sem preço ... BDI declarado uma vez ... valor do BDI"). Mantive o
    escopo estrito ao que o contrato listou.
  - `write_estimate_workbook`/`audit_estimate_workbook` e as classes de
    célula/plano/relatório são cópias deliberadas do desenho de
    workbook_writer.py, não imports de nomes privados de outro módulo — seguindo
    o precedente já existente no próprio repositório (`_sha256` duplicado
    entre workbook_writer.py e canonical.py). O único ponto de reuso
    explícito é `canonical.canonicalize_workbook` (função pública), que é
    onde vive o mini-avaliador da gramática fechada de fórmulas
    (GRAMMAR_PATTERNS) — a comparação célula a célula em si é própria, como
    o contrato exige ("não estenda audit_workbook da medição").
  - Quando `estimate.unpriced_item_ids` é vazio, nenhum cabeçalho "ITENS SEM
    PREÇO NA CASCATA" é impresso (em vez de um bloco vazio com só o
    cabeçalho) — decisão de projeto não coberta por teste dedicado.

Remaining risks:
  - Copy final (rótulos do bloco de totais e do bloco de itens sem preço)
    ainda não foi validada com o produto/negócio — ver "Assumptions" acima.
  - Nenhum teste cobre explicitamente `estimate.unpriced_item_ids == []`
    (nenhum bloco impresso); o comportamento é intencional mas não está
    fixado por golden nem por teste unitário dedicado.
  - `run_export_estimate_workbook`/`_command_estimate_demo` não têm teste que
    force uma divergência END-TO-END a partir de dado real adulterado no
    disco (só via monkeypatch do auditor) — o teste que tampera célula real
    prova a detecção (audit_estimate_workbook), e o teste de monkeypatch
    prova o gate (run_export_estimate_workbook); os dois juntos cobrem o
    critério de aceite 3, mas não há um teste único que amarre as duas
    pontas com um arquivo genuinamente adulterado passando pelo gate
    completo.

Human decisions required: none — nenhum gate de produção, migração
destrutiva, chamada paga em massa, envio a serviço externo ou mudança de
retenção/fornecedor foi exercido nesta task.
```

## Desvios conscientes do spec

1. **Ordem das colunas na aba** (`item, code, source, description, unit, unit_price,
   unit_price_with_bdi, quantity, total`, letras A..I) segue a Tela 7 do mock
   (`orcamento.html`) em vez de anexar as duas colunas novas no fim (`..., total, source,
   unit_price_with_bdi`). O contrato pede "colunas = as do boletim mais duas novas: FONTE
   e VALOR UNIT. C/ BDI" sem fixar posição, e o próprio Design Approval Package deixa
   "forma do escritor e do auditor de planilha" como explicitamente não aprovada — segui o
   material mais próximo do que existe (a rendição visual já revisada) em vez de inventar
   uma ordem nova.
2. **Reuso de `canonicalize_workbook` (função pública) em vez de `_SheetEvaluator` /
   `GRAMMAR_PATTERNS` diretamente** (nomes privados/quase-privados de `canonical.py`): o
   contrato pede reusar "o mini-avaliador de fórmulas de canonical.py ... como
   biblioteca". A função pública já encapsula esse avaliador e reabre o arquivo da mesma
   forma que `audit_workbook` faria — reusá-la evita tanto duplicar a gramática fechada de
   fórmulas quanto acoplar `estimate_workbook.py` a um nome privado de outro módulo.
3. **`_atomic_save`, `_sha256`, `_text`/`_number`/`_formula`/`_checked_number` são cópias
   próprias em `estimate_workbook.py`**, não imports de `workbook_writer.py` (que os
   declara com underscore). O contrato cita `_atomic_save, linha 1234` como parte do
   "desenho a seguir"; segui o desenho gravando a cópia, não o símbolo — mesmo padrão que
   o próprio repositório já usa para `_sha256` (duplicado entre `workbook_writer.py` e
   `canonical.py` antes desta task).

## Oportunidades vistas e NÃO implementadas (fora de escopo)

- Bloco de cabeçalho com a cascata completa (`Fonte 1/2/3`, com origem/data-base/digest de
  cada catálogo) e "Emitido em" — ilustrativos no mock, não pedidos pela lista de conteúdo
  do contrato; `Estimate` também não carrega timestamp de emissão.
- BDI por grupo — reservado por decisão do próprio ADR-0038 (decisão 2) para feature
  futura com ADR aceito; nada aqui o modela.
- Rota de API/tela web que chame `write_estimate_workbook`/`run_export_estimate_workbook`
  — explicitamente fora de escopo do contrato T2 ("API, web, persistência").
- Teste dedicado para `unpriced_item_ids == []` (nenhum bloco impresso) — ver "Remaining
  risks".
- Mensagem de erro amigável para argumentos de CLI mal formados relacionados ao orçamento
  — já registrado como risco remanescente de T1, não voltei a essa área.
