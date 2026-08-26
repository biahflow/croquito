"""Golden set do matcher de código SCO (M7): recall@20 é GATE, por matcher medido.

`tests/valuation/golden/matcher-golden-v1.json` traz dois grupos de casos, distinguidos
pelo campo `catalog`:

- `synthetic`: roda no CI, contra o mesmo mini-MAPÃO sintético que
  `croquito_worker.valuation.synthetic.build_synthetic_previous_mapao` gera em memória
  (o gabarito é `DEMO_EXPECTED_CODE_BY_LABEL`, já usado por `extraction_eval.py`).
- `real`: roda contra o catálogo REAL do SCO publicado em
  `output/valuation-toca/import/catalog.json` — arquivo local, não versionado (dado da
  prefeitura/cliente), então o teste correspondente usa `skipif` quando ele não existe na
  máquina. É esse grupo que exercita o caso que motivou a Fase 1 do M7: "GRAMADO" sem
  candidato porque "gramado" ≠ "grama" em tokens exatos.

São DOIS matchers medidos sobre o mesmo golden, e por isso dois gates por caso:

- `lexical_gate` (`test_real_catalog_golden_cases_are_recalled_at_20`) mede o matcher
  léxico puro da Fase 1, por `suggest_codes` — a via que continua sendo o fallback
  permanente do produto quando não há índice, teto de gasto ou credencial;
- `hybrid_gate` (`test_real_catalog_hybrid_cases_are_recalled_at_20`) mede o matcher do
  produto desde a Fase 2, por `hybrid_candidates`: fusão RRF entre a cobertura léxica e a
  vizinhança semântica de um índice de embeddings do catálogo real.

O caso que declara só `gate` (sintéticos e casos de aditivo) vale para os dois.

Cada caso também declara `gate` (default `True`): quando `False`, o caso é um GAP
CONHECIDO — o rótulo e o código certo já foram verificados manualmente, mas o matcher
léxico atual (radical + sinônimo + Dice, sem embeddings) não coloca o código no top-20.
A causa medida é sistemática, não um bug pontual: Dice sobre radicais favorece descrições
CURTAS sobre descrições LONGAS quando ambas compartilham uma palavra — o denominador
`|A|+|B|` penaliza o lado verboso, e vários códigos SCO têm descrição de um parágrafo
inteiro. O caso mais notável é "REFLETOR EXISTENTE": o sinônimo `refletor -> projetor`
FUNCIONA de verdade (tira o score de praticamente zero para um valor real, e o topo do
ranking passa a ser uma família inteira de códigos legítimos de projetor/refletor) — só não
é suficiente para colocar o código específico `IP49150409(/)` dentro dos 20 primeiros,
porque a descrição dele é mais longa que a de vários vizinhos da mesma família. É
precisamente a classe de problema que a Fase 2 (retrieval semântico por embeddings + fusão
de ranking) foi desenhada para fechar; os ranks medidos ficam no golden como baseline.

A cadeia inteira fechou: recall@20 do híbrido em **12/12** no catálogo real
(`note_phase_final` no golden), contra 4/12 do léxico puro da Fase 1.

Três casos passaram a ser medidos por FAMÍLIA (`note_family_oracle` no golden): quando o
rótulo da prancha não contém o que distingue o código certo dos irmãos — a altura do
alambrado, ou a escolha entre recuperar o refletor halógeno e substituir por projetor de
iluminação pública —, cobrar a variante exata é cobrar do matcher uma evidência que o texto
não tem. O matcher responde pela família; a variante é decisão de campo da orçamentista.
Isso não afrouxa nada: os outros nove casos seguem exigindo código exato, cada família
declara em `family_reason` o que exclui e por quê (equipamento de outra aplicação, serviço
de manutenção), e o REFLETOR chegou a reprovar em nível de família enquanto o recorte era
só `IP4915` — foi a medição que corrigiu o oráculo, não o contrário.

Cada teste GATEIA (recall@20 == 100%, assert duro) só os casos com o gate do SEU matcher em
`true`. Os casos com gate `false` são medidos e comparados contra o rank já registrado no
golden, para que uma piora futura apareça — mas uma melhora nunca falha o teste.

Top-1/top-3 dos casos gateados com código são medidos e relatados como asserts BRANDOS — o
piso mínimo exigido é o que a rodada realmente alcançou contra o catálogo real, não uma meta
aspiracional (ver `_REAL_TOP1_FLOOR`/`_REAL_TOP3_FLOOR` e os pisos híbridos abaixo).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Final

import pytest

from croquito_valuation.assignment import CodeSuggestion, SuggestionConfig, suggest_codes
from croquito_valuation.catalog import (
    default_domain_synonyms,
    default_legend_noise,
    query_covered_only_by_noise,
    read_price_catalog,
)
from croquito_valuation.models import PriceCatalog, ReviewerDecision
from croquito_valuation.takeoff import (
    PlateBox,
    PlateEvidence,
    TakeoffItem,
    TakeoffItemStatus,
    TakeoffPacket,
)
from croquito_valuation.template import default_template
from croquito_worker.valuation.sco_matching import (
    CATALOG_INDEX_FILENAME,
    QUERY_CACHE_FILENAME,
    hybrid_candidates,
    load_query_cache,
    load_semantic_index,
    normalize_query_text,
    semantic_topk,
)
from croquito_worker.valuation.synthetic import (
    SYNTHETIC_CONTRACT_SOURCE_LABEL,
    SYNTHETIC_REFERENCE_MONTH,
    build_synthetic_previous_mapao,
)

_GOLDEN_PATH: Final = Path(__file__).parent / "golden" / "matcher-golden-v1.json"
_REAL_CATALOG_PATH: Final = (
    Path(__file__).resolve().parents[2] / "output" / "valuation-toca" / "import" / "catalog.json"
)

_PLATE_ID: Final = "matcher-golden-v1"
_IMAGE_DIGEST: Final = "a" * 64
_PDF_DIGEST: Final = "b" * 64
_DECIDED_AT: Final = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)

# Piso REAL alcançado nesta rodada (2026-08-13), medido só sobre os casos `gate: true` com
# código do grupo `real` (PISO EM CONCRETO rank 13, GRAMADO rank 8, GOLA QUADRADA rank 2,
# GANGORRA DUPLA rank 16 — nenhum top-1, um top-3). Calibrado, não aspiracional: se um
# ajuste no léxico piorar este número, o teste reprova e o piso é o que deve ser revisto —
# não o número real da rodada.
_REAL_TOP1_FLOOR: Final = 0.0
_REAL_TOP3_FLOOR: Final = 0.25

_REAL_INDEX_PATH: Final = _REAL_CATALOG_PATH.parent / CATALOG_INDEX_FILENAME
_REAL_CACHE_PATH: Final = _REAL_CATALOG_PATH.parent / QUERY_CACHE_FILENAME

_HYBRID_RECALL_DEPTH: Final = 20

# Piso REAL do matcher híbrido na rodada final (2026-08-13), sobre os 12 casos reais com
# código, TODOS gateados: ranks 0, 14, 11, 14, 1, 2, 0, 10, 0, 3, 5, 9 — três top-1 e cinco
# top-3. Calibrado sobre o que a fusão de fato entregou, não sobre o que se gostaria dela.
_HYBRID_TOP1_FLOOR: Final = 0.25
_HYBRID_TOP3_FLOOR: Final = 0.41


def _golden_cases() -> list[dict[str, object]]:
    payload = json.loads(_GOLDEN_PATH.read_text(encoding="utf-8"))
    cases: list[dict[str, object]] = payload["cases"]
    return cases


def _cases_for(catalog: str) -> list[dict[str, object]]:
    return [case for case in _golden_cases() if case["catalog"] == catalog]


def _package_of(case: dict[str, object]) -> list[dict[str, object]] | None:
    """Lista de elementos do PACOTE (N:N, ADR-0053) quando o caso é da 4ª forma do oráculo,
    `None` caso contrário. Cada elemento é `{code, role, required, basis, quantity, ...}`
    (ver `note_package_cardinality` no golden)."""
    expected = case["expected"]
    assert isinstance(expected, dict)
    package = expected.get("package")
    if package is None:
        return None
    assert isinstance(package, list) and package, "pacote declarado sem nenhum código"
    return [dict(element) for element in package]


def _acceptable_codes(case: dict[str, object]) -> list[str]:
    """Códigos que respondem o caso: um só, a FAMÍLIA inteira quando o rótulo não carrega a
    evidência que separa as variantes (ver `note_family_oracle`), ou a lista de códigos do
    PACOTE quando um elemento dispara vários serviços (ver `note_package_cardinality`)."""
    expected = case["expected"]
    assert isinstance(expected, dict)
    package = _package_of(case)
    if package is not None:
        return [str(element["code"]) for element in package]
    codes = expected.get("codes")
    if isinstance(codes, list):
        assert codes, "família declarada sem nenhum código aceitável"
        return [str(code) for code in codes]
    code = expected.get("code")
    return [] if code is None else [str(code)]


def _best_rank(ranking: Sequence[str], acceptable: Sequence[str]) -> int | None:
    """Melhor posição entre os códigos aceitáveis; `None` quando nenhum deles está na lista."""
    found = [ranking.index(code) for code in acceptable if code in ranking]
    return min(found) if found else None


def _gate_of(case: dict[str, object], key: str) -> bool:
    """Gate do matcher pedido, caindo no `gate` comum quando o caso não distingue os dois.

    Casos sintéticos e casos de aditivo declaram só `gate` porque a resposta certa é a
    mesma para os dois matchers; os casos reais com código declaram `lexical_gate` e
    `hybrid_gate` separados, porque medem coisas diferentes."""
    value = case.get(key, case.get("gate", True))
    assert isinstance(value, bool)
    return value


def _evidence(index: int) -> PlateEvidence:
    return PlateEvidence(
        plate_id=_PLATE_ID,
        page_number=1,
        image_sha256=_IMAGE_DIGEST,
        bbox=PlateBox(left=10, top=10 + index * 20, right=110, bottom=25 + index * 20),
    )


def _decision(index: int) -> ReviewerDecision:
    return ReviewerDecision(
        decision_id=f"vd_{index:016x}",
        action="confirm",
        reviewer_id="orcamentista-golden",
        reviewer_role="orcamentista",
        decided_at=_DECIDED_AT,
    )


def _item(index: int, label: str, unit: str) -> TakeoffItem:
    return TakeoffItem(
        id=f"ti_{index:016x}",
        evidence=_evidence(index),
        raw_text=f"{label} 1 {unit}",
        label=label,
        quantity=Decimal("1"),
        unit=unit,
        source="manual",
        extractor="matcher-golden-fixture",
        extractor_version="1.0.0",
        status=TakeoffItemStatus.CONFIRMED,
        decision=_decision(index),
    )


def _packet(cases: list[dict[str, object]]) -> TakeoffPacket:
    items = [
        _item(index, str(case["label"]), str(case["unit"])) for index, case in enumerate(cases)
    ]
    return TakeoffPacket(
        plate_id=_PLATE_ID,
        page_number=1,
        image_sha256=_IMAGE_DIGEST,
        source_pdf_sha256=_PDF_DIGEST,
        items=items,
        safety_notes=[
            "Golden set do matcher léxico; nenhuma quantidade aqui é medição real.",
            "Itens confirmados artificialmente só para exercitar suggest_codes.",
        ],
    )


def _suggestion_by_item(packet: TakeoffPacket, catalog: PriceCatalog) -> dict[str, CodeSuggestion]:
    """Shortlist de até 20 candidatos por item — o recall@20 do gate, não os 3 publicados
    por padrão em `SuggestionConfig`."""
    result = suggest_codes(
        packet,
        catalog,
        config=SuggestionConfig(max_candidates_per_item=20),
        synonyms=default_domain_synonyms(),
    )
    return {suggestion.item_id: suggestion for suggestion in result.suggestions}


def _assert_gate_cases_are_recalled_at_20(
    cases: list[dict[str, object]], suggestions: dict[str, CodeSuggestion]
) -> tuple[int, int, int]:
    """Recall@20 é assert duro só para casos `lexical_gate: true` com código; devolve
    (top1, top3, n)."""
    top1 = 0
    top3 = 0
    total = 0
    for index, case in enumerate(cases):
        if not _gate_of(case, "lexical_gate"):
            continue
        acceptable = _acceptable_codes(case)
        if not acceptable:
            continue
        total += 1
        item_id = f"ti_{index:016x}"
        suggestion = suggestions.get(item_id)
        candidate_codes = [] if suggestion is None else [c.code for c in suggestion.candidates]
        rank = _best_rank(candidate_codes, acceptable)
        assert rank is not None, (
            f"{case['label']!r}: nenhum código aceitável {acceptable!r} apareceu no top-20 "
            f"({candidate_codes!r})"
        )
        if rank == 0:
            top1 += 1
        if rank < 3:
            top3 += 1
    return top1, top3, total


def _assert_known_gaps_did_not_regress(
    cases: list[dict[str, object]], packet: TakeoffPacket, catalog: PriceCatalog
) -> None:
    """Casos `lexical_gate: false` não são exigidos no top-20, mas o rank registrado no
    golden não pode PIORAR em silêncio — só melhorar ou ficar estável é aceito sem tocar o
    golden."""
    all_ranked = suggest_codes(
        packet,
        catalog,
        config=SuggestionConfig(max_candidates_per_item=len(catalog.entries)),
        synonyms=default_domain_synonyms(),
    )
    by_item = {suggestion.item_id: suggestion for suggestion in all_ranked.suggestions}
    for index, case in enumerate(cases):
        if _gate_of(case, "lexical_gate"):
            continue
        acceptable = _acceptable_codes(case)
        recorded_rank = case.get("known_gap_rank_2026_08_13")
        if not acceptable or recorded_rank is None:
            continue
        assert isinstance(recorded_rank, int)
        item_id = f"ti_{index:016x}"
        suggestion = by_item.get(item_id)
        candidate_codes = [] if suggestion is None else [c.code for c in suggestion.candidates]
        current_rank = _best_rank(candidate_codes, acceptable)
        assert current_rank is not None, (
            f"{case['label']!r}: nenhum código aceitável {acceptable!r} está no ranking "
            f"(antes rank {recorded_rank})"
        )
        assert current_rank <= recorded_rank, (
            f"{case['label']!r}: rank piorou de {recorded_rank} para {current_rank} — "
            "atualize known_gap_rank_2026_08_13 no golden só se a piora for esperada"
        )


def _assert_package_recall_did_not_regress(
    cases: list[dict[str, object]], suggestions: dict[str, CodeSuggestion]
) -> None:
    """MEDIÇÃO-NÃO-GATEADA do oráculo de PACOTE (N:N, ADR-0053).

    Para cada caso de pacote, mede o recall@20 do matcher de CÓDIGO ÚNICO sobre a lista de
    códigos do pacote — quantos dos N serviços que o elemento dispara aparecem no top-20 —
    e compara com o piso `package_recall_2026_08_26` registrado no golden. Espelha
    exatamente o padrão `known_gap_rank`: uma PIORA reprova (o número registrado é o teto de
    regressão), uma melhora nunca reprova e nunca roda no CI (o caso é `catalog: "real"`,
    sob `skipif`). É o gap que o ADR-0053 manda publicar como medido, não esconder: o matcher
    otimizado para "qual código É este elemento" não traz códigos de famílias diferentes, e o
    piso nasce 0.0 (ver `note_package_cardinality`), catraca só para cima quando o suggester
    de pacote entrar."""
    for index, case in enumerate(cases):
        package = _package_of(case)
        if package is None:
            continue
        recorded = case.get("package_recall_2026_08_26")
        assert isinstance(recorded, int | float), (
            f"{case['label']!r}: caso de pacote sem `package_recall_2026_08_26` no golden"
        )
        acceptable = _acceptable_codes(case)
        item_id = f"ti_{index:016x}"
        suggestion = suggestions.get(item_id)
        candidate_codes = [] if suggestion is None else [c.code for c in suggestion.candidates]
        found = sum(1 for code in acceptable if code in candidate_codes)
        recall = found / len(acceptable)
        assert recall + 1e-9 >= recorded, (
            f"{case['label']!r}: recall@20 do pacote caiu de {recorded} para {recall:.4f} "
            f"({found}/{len(acceptable)} códigos no top-20) — atualize "
            "package_recall_2026_08_26 no golden só se a piora for esperada"
        )


def test_synthetic_golden_cases_are_recalled_at_20(tmp_path: Path) -> None:
    cases = _cases_for("synthetic")
    assert cases, "o golden precisa declarar os casos sintéticos do oráculo do M4/M5"

    previous_path = build_synthetic_previous_mapao(tmp_path / "previous-mapao.xlsx")
    catalog = read_price_catalog(
        previous_path,
        default_template(),
        source_label=SYNTHETIC_CONTRACT_SOURCE_LABEL,
        reference_month=SYNTHETIC_REFERENCE_MONTH,
    )

    suggestions = _suggestion_by_item(_packet(cases), catalog)
    top1, top3, total = _assert_gate_cases_are_recalled_at_20(cases, suggestions)

    assert total > 0
    # Catálogo sintético pequeno e descrições quase literais: bem mais forte que o real.
    assert top1 / total >= 0.6
    assert top3 / total >= 0.6


@pytest.mark.skipif(
    not _REAL_CATALOG_PATH.exists(),
    reason=(
        "catálogo real do SCO é local-only (dado do cliente/prefeitura, não versionado); "
        f"ausente em {_REAL_CATALOG_PATH}"
    ),
)
def test_real_catalog_golden_cases_are_recalled_at_20() -> None:
    cases = _cases_for("real")
    assert cases, "o golden precisa declarar os 15 rótulos reais da Toca"

    catalog = PriceCatalog.model_validate_json(_REAL_CATALOG_PATH.read_text(encoding="utf-8"))
    packet = _packet(cases)
    suggestions = _suggestion_by_item(packet, catalog)
    top1, top3, total = _assert_gate_cases_are_recalled_at_20(cases, suggestions)

    assert total > 0
    top1_rate = top1 / total
    top3_rate = top3 / total
    assert top1_rate >= _REAL_TOP1_FLOOR, (
        f"top-1 léxico real caiu para {top1_rate:.2f}, abaixo do piso medido {_REAL_TOP1_FLOOR:.2f}"
    )
    assert top3_rate >= _REAL_TOP3_FLOOR, (
        f"top-3 léxico real caiu para {top3_rate:.2f}, abaixo do piso medido {_REAL_TOP3_FLOOR:.2f}"
    )

    _assert_known_gaps_did_not_regress(cases, packet, catalog)
    _assert_package_recall_did_not_regress(cases, suggestions)


@pytest.mark.skipif(
    not (_REAL_CATALOG_PATH.exists() and _REAL_INDEX_PATH.exists() and _REAL_CACHE_PATH.exists()),
    reason=(
        "o modo híbrido exige o catálogo real MAIS o índice de embeddings e o cache de "
        "consultas da rodada paga, todos local-only e não versionados. Para gerá-los: "
        "`index-catalog --catalog output/valuation-toca/import/catalog.json` (chamada paga, "
        "~US$ 0,01) e depois uma busca por rótulo no `serve` da mesma pasta"
    ),
)
def test_real_catalog_hybrid_cases_are_recalled_at_20() -> None:
    """Gate do matcher do produto (Fase 2) sobre o catálogo real, offline e determinístico.

    Offline porque o índice e o cache de consulta já foram pagos uma vez: o teste não tem
    adapter e uma consulta que faltasse no cache reprovaria em vez de virar chamada — é o
    mesmo `SEMANTIC_QUERY_NOT_CACHED` que o produto usa para nunca gastar às escondidas.

    Passa `noise=default_legend_noise()` desde a rodada 2.2 (2026-08-13): o rank do código
    aceitável não muda (`note_phase_2_2` no golden), mas a COMPOSIÇÃO do top-20 sim — é por
    isso que casos com `hybrid_junk_max` no golden gateiam o junk-count
    (`query_covered_only_by_noise`) além do rank.
    """
    cases = _cases_for("real")
    catalog = PriceCatalog.model_validate_json(_REAL_CATALOG_PATH.read_text(encoding="utf-8"))
    index = load_semantic_index(_REAL_INDEX_PATH, catalog)
    cache = load_query_cache(_REAL_CACHE_PATH, index)
    synonyms = default_domain_synonyms()
    noise = default_legend_noise()
    entries_by_code = {entry.code: entry for entry in catalog.entries}

    top1 = 0
    top3 = 0
    gated = 0
    for case in cases:
        acceptable = _acceptable_codes(case)
        if not acceptable:
            continue
        if _package_of(case) is not None:
            # Pacote (N:N, ADR-0053): medido no braço LÉXICO (catálogo-only), em
            # `_assert_package_recall_did_not_regress`. O híbrido exigiria um vetor de
            # consulta em cache que a rodada paga não gerou para estes rótulos de pacote.
            continue
        label = str(case["label"])
        vector = cache.vectors.get(normalize_query_text(label))
        assert vector is not None, (
            f"{label!r}: cache de consulta da rodada não tem o vetor deste rótulo; refaça a "
            "busca no `serve` da pasta do catálogo real"
        )
        candidates = hybrid_candidates(
            label,
            catalog,
            index=index,
            query_vec=vector,
            synonyms=synonyms,
            noise=noise,
            k=_HYBRID_RECALL_DEPTH,
        )
        codes = [candidate.code for candidate in candidates]
        if _gate_of(case, "hybrid_gate"):
            gated += 1
            rank = _best_rank(codes, acceptable)
            assert rank is not None, (
                f"{label!r}: nenhum código aceitável {acceptable!r} ficou no top-"
                f"{_HYBRID_RECALL_DEPTH} do matcher híbrido ({codes!r})"
            )
            top1 += rank == 0
            top3 += rank < 3
            junk_max = case.get("hybrid_junk_max")
            if junk_max is not None:
                assert isinstance(junk_max, int)
                junk_count = sum(
                    query_covered_only_by_noise(
                        label, entries_by_code[code].description, synonyms=synonyms, noise=noise
                    )
                    for code in codes
                )
                assert junk_count <= junk_max, (
                    f"{label!r}: {junk_count} itens do top-{_HYBRID_RECALL_DEPTH} cobrem só "
                    f"radical de ruído (piso {junk_max}) — amortecimento de ruído regrediu"
                )
            continue
        # Gap declarado da Fase 2: o rank do braço semântico não pode PIORAR em silêncio.
        # O braço léxico já é vigiado pelo teste lexical, e recalculá-lo aqui sobre 4.964
        # descrições dobraria o tempo do gate sem cobrir nada novo.
        recorded = case.get("hybrid_arm_ranks_2026_08_13")
        assert isinstance(recorded, dict)
        ranked = [found for found, _score in semantic_topk(vector, index, len(catalog.entries))]
        current = _best_rank(ranked, acceptable)
        assert current is not None and current <= recorded["semantic"], (
            f"{label!r}: rank semântico piorou de {recorded['semantic']} para {current} — "
            "atualize hybrid_arm_ranks_2026_08_13 no golden só se a piora for esperada"
        )

    assert gated > 0
    assert top1 / gated >= _HYBRID_TOP1_FLOOR, (
        f"top-1 híbrido caiu para {top1 / gated:.2f}, abaixo do piso medido "
        f"{_HYBRID_TOP1_FLOOR:.2f}"
    )
    assert top3 / gated >= _HYBRID_TOP3_FLOOR, (
        f"top-3 híbrido caiu para {top3 / gated:.2f}, abaixo do piso medido "
        f"{_HYBRID_TOP3_FLOOR:.2f}"
    )
