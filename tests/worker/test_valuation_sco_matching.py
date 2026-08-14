"""Retrieval híbrido de código SCO (M7 Fase 2): índice, kNN, fusão, cache e shortlist.

Nenhum teste aqui chama provider: o índice é o FABRICADO (`sco_matching_fixtures`) ou vem
de um adapter de embeddings dublê, e os caminhos de recusa param antes da rede — sem teto
de gasto, sem credencial, índice de outro catálogo, cache de outro modelo e consulta sem
vetor. O que importa em cada recusa é o que **não** aparece no diretório da rodada.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from croquitodxf_valuation.assignment import (
    SCO_HYBRID_SUGGESTER_VERSION,
    SCO_SUGGESTER_VERSION,
    CodeSuggestionSet,
    SuggestionConfig,
)
from croquitodxf_valuation.catalog import (
    DomainSynonyms,
    LegendNoiseList,
    StemIdfTable,
    build_stem_idf_table,
    default_domain_synonyms,
    default_legend_noise,
    query_coverage_score,
    query_covered_only_by_noise,
    read_price_catalog,
    weighted_query_coverage_score,
)
from croquitodxf_valuation.errors import ValuationValidationError, valuation_error_codes
from croquitodxf_valuation.models import PriceCatalog, PriceCatalogEntry
from croquitodxf_valuation.takeoff import load_takeoff_packet
from croquitodxf_valuation.template import default_template
from croquitodxf_worker.providers import (
    EmbeddingsExecution,
    ProviderName,
    ProviderUsage,
)
from croquitodxf_worker.valuation import sco_matching
from croquitodxf_worker.valuation.cli import (
    CATALOG_FILENAME,
    CODE_SUGGESTIONS_FILENAME,
    SEMANTIC_DISABLED_BY_FLAG,
    TAKEOFF_PACKET_FILENAME,
    main,
)
from croquitodxf_worker.valuation.sco_matching import (
    CATALOG_INDEX_FILENAME,
    INDEX_TEXT_RECIPE,
    QUERY_CACHE_FILENAME,
    RRF_K,
    CatalogEmbeddingIndex,
    bind_index_to_catalog,
    build_catalog_index,
    build_hybrid_code_suggestions,
    catalog_index_text,
    fuse_arms,
    hybrid_candidates,
    index_document,
    load_query_cache,
    load_semantic_index,
    normalize_query_text,
    read_catalog_index,
    resolve_query_vectors,
    semantic_topk,
)
from croquitodxf_worker.valuation.sco_matching_fixtures import (
    FIXTURE_EMBEDDINGS_DIMS,
    FIXTURE_EMBEDDINGS_MODEL,
    fixture_catalog_index,
    fixture_semantic_index,
    fixture_vector,
)
from croquitodxf_worker.valuation.synthetic import (
    SYNTHETIC_CONTRACT_SOURCE_LABEL,
    SYNTHETIC_REFERENCE_MONTH,
    build_synthetic_previous_mapao,
)

BUDGET_ENV = "CROQUITODXF_AI_MAX_ESTIMATED_COST_USD"
KEY_ENV = "CROQUITODXF_OPENAI_API_KEY"


@dataclass
class _FixtureEmbeddingsAdapter:
    """Adapter de embeddings determinístico: os mesmos vetores fabricados do índice fixture.

    Ele conta as chamadas de propósito — o cache de consulta só vale alguma coisa se uma
    segunda rodada com o mesmo rótulo não chamar de novo.
    """

    calls: list[list[str]] = field(default_factory=list)
    dims: int = FIXTURE_EMBEDDINGS_DIMS

    def embed(self, texts: Sequence[str]) -> EmbeddingsExecution:
        batch = list(texts)
        self.calls.append(batch)
        return EmbeddingsExecution(
            provider=ProviderName.OPENAI,
            model_id=FIXTURE_EMBEDDINGS_MODEL,
            input_count=len(batch),
            input_digest=hashlib.sha256(str(batch).encode()).hexdigest(),
            dims=self.dims,
            latency_ms=1,
            usage=ProviderUsage(input_tokens=len(batch)),
            vectors=tuple(fixture_vector(text, dims=self.dims) for text in batch),
        )


@pytest.fixture(scope="module")
def catalog(tmp_path_factory: pytest.TempPathFactory) -> PriceCatalog:
    root = tmp_path_factory.mktemp("matching-catalog")
    return read_price_catalog(
        build_synthetic_previous_mapao(root / "previous-mapao.xlsx"),
        default_template(),
        source_label=SYNTHETIC_CONTRACT_SOURCE_LABEL,
        reference_month=SYNTHETIC_REFERENCE_MONTH,
    )


# --------------------------------------------------------------------------------------
# Braço léxico: cobertura da consulta
# --------------------------------------------------------------------------------------


def test_coverage_ignores_the_length_of_the_description() -> None:
    """O achado que motivou a Fase 2: descrição longa deixa de ser punida."""
    curta = query_coverage_score("PISO INTERTRAVADO", "Piso intertravado.")
    longa = query_coverage_score(
        "PISO INTERTRAVADO",
        "Piso intertravado com peças de concreto vibro-prensadas de 35MPa, espessura de "
        "6cm, inclusive compactação, corte de blocos, colchão de areia e rejuntamento, "
        "conforme as normas NBR 9780 e NBR 9781.",
    )

    assert curta == longa == 1.0


def test_coverage_is_the_fraction_of_query_stems_present() -> None:
    assert query_coverage_score("piso intertravado", "Piso cimentado.") == 0.5
    assert query_coverage_score("piso intertravado", "Plantio de grama.") == 0.0


def test_an_empty_query_covers_nothing() -> None:
    assert query_coverage_score("", "Piso intertravado.") == 0.0
    assert query_coverage_score("- /", "Piso intertravado.") == 0.0
    assert query_coverage_score("piso", "") == 0.0


def test_weighted_coverage_pays_more_for_the_rare_word(catalog: PriceCatalog) -> None:
    """O achado da rodada 2.1: cobrir a palavra comum não pode valer o mesmo que a rara.

    No catálogo sintético "piso" aparece em várias descrições e "intertravado" em uma só.
    Cobrindo uma palavra cada, os dois lados empatam em 0,5 na fração simples; a ponderada
    põe na frente quem cobriu a palavra que identifica o item.
    """
    idf = build_stem_idf_table([entry.description for entry in catalog.entries])
    query = "piso intertravado"
    comum = "PISO EMBORRACHADO SINTETICO"
    rara = "REVESTIMENTO INTERTRAVADO"

    assert query_coverage_score(query, comum) == query_coverage_score(query, rara)
    assert weighted_query_coverage_score(query, rara, idf=idf) > weighted_query_coverage_score(
        query, comum, idf=idf
    )


def test_weighted_coverage_of_an_empty_query_is_zero(catalog: PriceCatalog) -> None:
    idf = build_stem_idf_table([entry.description for entry in catalog.entries])

    assert weighted_query_coverage_score("", "Piso intertravado.", idf=idf) == 0.0
    assert weighted_query_coverage_score("piso", "", idf=idf) == 0.0


def test_the_idf_table_is_built_once_per_catalog(
    catalog: PriceCatalog, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Construir a tabela varre o catálogo inteiro; refazê-la por consulta inviabilizaria a
    busca na tela."""
    builds: list[int] = []

    def counted(
        descriptions: Sequence[str], *, synonyms: DomainSynonyms | None = None
    ) -> StemIdfTable:
        builds.append(len(descriptions))
        return build_stem_idf_table(descriptions, synonyms=synonyms)

    monkeypatch.setattr(sco_matching, "build_stem_idf_table", counted)
    monkeypatch.setattr(sco_matching, "_IDF_CACHE", {})

    sco_matching.catalog_idf_table(catalog)
    sco_matching.catalog_idf_table(catalog)

    assert builds == [len(catalog.entries)]


def test_a_synonym_counts_as_present() -> None:
    """`refletor` é coberto por uma descrição que só escreve `projetor`."""
    synonyms = default_domain_synonyms()
    descricao = "Projetor PRJ-01, modelo IP-67, para lâmpada a vapor de sódio."

    assert query_coverage_score("refletor", descricao) == 0.0
    assert query_coverage_score("refletor", descricao, synonyms=synonyms) == 1.0


# --------------------------------------------------------------------------------------
# Lista de ruído de legenda (rodada 2.2 do M7) — amortecimento, nunca remoção
# --------------------------------------------------------------------------------------


def test_weighted_coverage_with_noise_ranks_the_service_word_above_the_state_word() -> None:
    """Cenário REFLETOR/EXISTENTE em miniatura: sem `noise`, a palavra de ESTADO rara (peso
    IDF maior) vence a palavra de SERVIÇO — o defeito medido na docstring de
    `weighted_query_coverage_score`. Com `noise`, o amortecimento inverte a ordem."""
    idf = StemIdfTable(weights={"refletor": 1.0, "existente": 3.0}, default_weight=1.0)
    noise = LegendNoiseList(version="v1", terms=["existente"])
    query = "REFLETOR EXISTENTE"
    servico = "Substituição do refletor da quadra."
    estado = "Pintura de muro existente."

    sem_noise_servico = weighted_query_coverage_score(query, servico, idf=idf)
    sem_noise_estado = weighted_query_coverage_score(query, estado, idf=idf)
    assert sem_noise_estado > sem_noise_servico

    com_noise_servico = weighted_query_coverage_score(query, servico, idf=idf, noise=noise)
    com_noise_estado = weighted_query_coverage_score(query, estado, idf=idf, noise=noise)
    assert com_noise_servico > com_noise_estado


def test_weighted_coverage_without_noise_is_unchanged() -> None:
    """Regressão: sem `noise` (o caminho de produção hoje, ver `LEGEND_NOISE_DAMP_FACTOR`),
    o resultado é idêntico ao existente antes desta rodada — a palavra de ESTADO pesa
    cheio, sem amortecimento nenhum."""
    idf = StemIdfTable(weights={"refletor": 1.0, "existente": 3.0}, default_weight=1.0)
    query = "REFLETOR EXISTENTE"
    estado = "Pintura de muro existente."

    assert weighted_query_coverage_score(query, estado, idf=idf) == 0.75
    assert weighted_query_coverage_score(
        query, estado, idf=idf, noise=None
    ) == weighted_query_coverage_score(query, estado, idf=idf)


def test_noise_damping_looks_at_the_original_stem_not_the_synonym_expansion() -> None:
    """Um sinônimo que expande o radical legítimo da consulta para um termo de ruído não faz
    esse radical ser amortecido — a regra olha o radical ORIGINAL, nunca o grupo expandido."""
    synonyms = DomainSynonyms(version="v1", terms={"farol": ["existente"]})
    noise = LegendNoiseList(version="v1", terms=["existente"])
    idf = StemIdfTable(weights={"farol": 1.0, "existente": 5.0, "quadra": 2.0}, default_weight=1.0)
    query = "farol quadra"
    description = "Substituição de existente."

    score = weighted_query_coverage_score(
        query, description, idf=idf, synonyms=synonyms, noise=noise
    )

    # "farol" (radical original) não é termo de ruído, então o grupo dele ({"farol",
    # "existente"}, peso 5.0 = o membro mais discriminativo) NÃO é amortecido, mesmo
    # contendo "existente". Só o grupo de "quadra" (não coberto) entra no total sem ele:
    # 5.0 coberto / (5.0 + 2.0) total = 0.7143. Um amortecimento indevido do grupo do
    # "farol" (para 5.0 * 0.25 = 1.25) daria 1.25 / 3.25 = 0.3846.
    assert score == 0.7143


def test_default_legend_noise_covers_the_two_measured_forms() -> None:
    """O seed mínimo cobre as duas medições citadas na docstring: "existente" e "a ser
    recuperar"."""
    noise = default_legend_noise()

    assert noise.noise_stems() >= {"existente", "ser", "recuperar"}


def test_query_covered_only_by_noise_flags_the_state_only_match() -> None:
    """A definição de "junk" que decidiu a calibração: descrição que cobre RUÍDO e nenhum
    radical de SERVIÇO da consulta."""
    noise = LegendNoiseList(version="v1", terms=["existente"])
    query = "REFLETOR EXISTENTE"

    assert query_covered_only_by_noise(query, "Pintura de muro existente.", noise=noise)
    assert not query_covered_only_by_noise(
        query, "Substituição do refletor da quadra.", noise=noise
    )
    # Cobrir os dois (serviço E ruído) não é junk — o item também fala do serviço.
    assert not query_covered_only_by_noise(
        query, "Substituição do refletor existente da quadra.", noise=noise
    )


def test_query_covered_only_by_noise_is_always_false_without_noise() -> None:
    """Sem `noise`, não existe distinção de ruído: nunca classifica como junk."""
    query = "REFLETOR EXISTENTE"

    assert not query_covered_only_by_noise(query, "Pintura de muro existente.")


# --------------------------------------------------------------------------------------
# Índice do catálogo
# --------------------------------------------------------------------------------------


def test_the_index_text_carries_code_description_and_unit(catalog: PriceCatalog) -> None:
    entry = catalog.entries[0]

    assert catalog_index_text(entry) == f"{entry.code} {entry.description} ({entry.unit})"


def test_building_the_index_batches_and_normalises_every_vector(catalog: PriceCatalog) -> None:
    adapter = _FixtureEmbeddingsAdapter()

    build = build_catalog_index(catalog, adapter)

    assert build.item_count == len(catalog.entries)
    assert build.batch_count == 1
    assert build.index.dims == FIXTURE_EMBEDDINGS_DIMS
    assert build.index.catalog_sha256 == catalog.source_sha256
    assert len(build.index.batch_digests) == build.batch_count
    semantic = bind_index_to_catalog(build.index, "d" * 64, catalog)
    norms = [float((row @ row) ** 0.5) for row in semantic.matrix]
    assert all(abs(norm - 1.0) < 1e-5 for norm in norms)


def test_an_index_of_another_catalog_is_refused_on_load(catalog: PriceCatalog) -> None:
    other = catalog.model_copy(update={"source_sha256": "e" * 64})

    with pytest.raises(ValuationValidationError) as error:
        bind_index_to_catalog(fixture_catalog_index(catalog), "d" * 64, other)

    assert error.value.code == "INDEX_CATALOG_MISMATCH"


def test_an_index_of_another_text_recipe_is_refused_on_load(catalog: PriceCatalog) -> None:
    """Índice construído com outro texto por item não é comparável; ele recusa em vez de
    degradar a busca em silêncio."""
    other_recipe = fixture_catalog_index(catalog).model_copy(
        update={"text_recipe": "description-unit-v2"}
    )

    with pytest.raises(ValuationValidationError) as error:
        bind_index_to_catalog(other_recipe, "d" * 64, catalog)

    assert error.value.code == "INDEX_TEXT_RECIPE_MISMATCH"


def test_index_catalog_rebuilds_when_the_text_recipe_changed(
    catalog: PriceCatalog,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    adapter = _FixtureEmbeddingsAdapter()
    monkeypatch.setattr(
        "croquitodxf_worker.valuation.cli.build_embeddings_adapter", lambda: adapter
    )
    catalog_path = _write_catalog(tmp_path / "rodada", catalog)
    stale = fixture_catalog_index(catalog).model_copy(update={"text_recipe": "description-unit-v2"})
    (catalog_path.parent / CATALOG_INDEX_FILENAME).write_text(
        index_document(stale), encoding="utf-8"
    )

    assert main(["index-catalog", "--catalog", str(catalog_path)]) == 0

    assert _stdout(capsys)["status"] == "replaced"
    assert len(adapter.calls) == 1
    rebuilt, _digest = read_catalog_index(catalog_path.parent / CATALOG_INDEX_FILENAME)
    assert rebuilt.text_recipe == INDEX_TEXT_RECIPE


def test_a_tampered_index_payload_is_refused(catalog: PriceCatalog) -> None:
    document = json.loads(index_document(fixture_catalog_index(catalog)))
    document["dims"] = FIXTURE_EMBEDDINGS_DIMS + 1

    with pytest.raises(ValidationError) as error:
        CatalogEmbeddingIndex.model_validate(document)

    assert valuation_error_codes(error.value) == ["INDEX_PAYLOAD_INVALID"]


# --------------------------------------------------------------------------------------
# kNN e fusão
# --------------------------------------------------------------------------------------


def test_the_nearest_neighbour_of_an_entry_is_the_entry_itself(catalog: PriceCatalog) -> None:
    index = fixture_semantic_index(catalog)
    entry = catalog.entries[2]

    ranked = semantic_topk(fixture_vector(catalog_index_text(entry)), index, 3)

    assert ranked[0][0] == entry.code
    assert ranked[0][1] == pytest.approx(1.0, abs=1e-5)
    assert [score for _code, score in ranked] == sorted(
        (score for _code, score in ranked), reverse=True
    )


def test_a_query_vector_of_the_wrong_size_is_refused(catalog: PriceCatalog) -> None:
    index = fixture_semantic_index(catalog)

    with pytest.raises(ValuationValidationError) as error:
        semantic_topk([0.0, 1.0], index, 3)

    assert error.value.code == "SEMANTIC_QUERY_DIMS_MISMATCH"


def test_fusion_declares_the_arm_of_every_candidate() -> None:
    fused = fuse_arms(["a", "b"], [("b", 0.9), ("c", 0.5)], k=5)

    assert {entry.code: entry.origin for entry in fused} == {
        "b": "both",
        "a": "lexical",
        "c": "semantic",
    }
    assert [entry.fused_rank for entry in fused] == [0, 1, 2]
    # Corroborado nos dois braços vence primeiro lugar num braço só — é o ponto do RRF.
    assert fused[0].code == "b"
    assert fused[0].fused_score == pytest.approx(1 / (RRF_K + 2) + 1 / (RRF_K + 1))
    assert fused[0].semantic_score == pytest.approx(0.9)
    assert next(entry for entry in fused if entry.code == "a").semantic_score is None


def test_fusion_is_deterministic_and_breaks_ties_by_code() -> None:
    first = fuse_arms(["b", "a"], [("a", 0.4), ("b", 0.4)], k=2)
    again = fuse_arms(["b", "a"], [("a", 0.4), ("b", 0.4)], k=2)

    assert [entry.code for entry in first] == [entry.code for entry in again] == ["a", "b"]


def test_without_an_index_the_hybrid_degrades_to_the_coverage_arm(catalog: PriceCatalog) -> None:
    only_lexical = hybrid_candidates("PISO INTERTRAVADO SINTETICO", catalog, k=5)

    assert only_lexical
    assert {candidate.origin for candidate in only_lexical} == {"lexical"}
    assert all(candidate.semantic_score is None for candidate in only_lexical)
    assert all(candidate.lexical_score > 0 for candidate in only_lexical)


def test_the_hybrid_puts_the_expected_code_first_on_the_synthetic_catalog(
    catalog: PriceCatalog,
) -> None:
    index = fixture_semantic_index(catalog)
    label = "PISO INTERTRAVADO SINTETICO"

    candidates = hybrid_candidates(
        label, catalog, index=index, query_vec=fixture_vector(label), k=5
    )

    # O índice fixture é um saco de radicais: ele distingue famílias, não variantes de um
    # mesmo serviço. O que se exige aqui é a fusão funcionando — o código certo na página e
    # corroborado pelos dois braços —, não qualidade semântica (ver `sco_matching_fixtures`).
    assert "AD04050060(/)" in [candidate.code for candidate in candidates]
    assert candidates[0].origin == "both"
    assert candidates[0].fused_rank == 0


def _noise_probe_catalog_entry(code: str, description: str) -> PriceCatalogEntry:
    return PriceCatalogEntry(
        code=code,
        description=description,
        unit="un",
        unit_price=Decimal("10.00"),
        family_code="RF",
        family_name="REFLETORES SINTETICOS",
        subgroup_code="RF0100",
        subgroup_name="REFLETORES",
    )


def test_hybrid_candidates_with_noise_propagates_the_damping() -> None:
    """`hybrid_candidates` sem índice (braço só léxico) muda de ordem com `noise`: o item de
    SERVIÇO ("refletor", comum no catálogo sintético) passa à frente do item cujo único
    mérito é o radical de ESTADO ("existente", raro — e por isso mais pesado no IDF)."""
    target_code = "RF01000100(/)"
    trap_code = "RF01000200(/)"
    catalog = PriceCatalog(
        source_label="CATALOGO SINTETICO RUIDO",
        reference_month="2026-01",
        source_sha256="5" * 64,
        entries=[
            _noise_probe_catalog_entry(target_code, "Manutenção do refletor da quadra."),
            _noise_probe_catalog_entry(trap_code, "Pintura de muro existente."),
            _noise_probe_catalog_entry("RF01000300(/)", "Fornecimento de refletor novo."),
            _noise_probe_catalog_entry("RF01000400(/)", "Instalação de refletor LED."),
        ],
    )
    noise = LegendNoiseList(version="v1", terms=["existente"])
    query = "REFLETOR EXISTENTE"

    without_noise = hybrid_candidates(query, catalog, k=4)
    with_noise = hybrid_candidates(query, catalog, noise=noise, k=4)

    ranks_without = {c.code: c.fused_rank for c in without_noise}
    ranks_with = {c.code: c.fused_rank for c in with_noise}
    assert ranks_without[trap_code] < ranks_without[target_code]  # o defeito medido
    assert ranks_with[target_code] < ranks_with[trap_code]  # o amortecimento corrige


# --------------------------------------------------------------------------------------
# Cache de consulta
# --------------------------------------------------------------------------------------


def test_a_repeated_query_costs_nothing(catalog: PriceCatalog, tmp_path: Path) -> None:
    index = fixture_semantic_index(catalog)
    adapter = _FixtureEmbeddingsAdapter()
    cache_path = tmp_path / QUERY_CACHE_FILENAME

    first = resolve_query_vectors(["GRAMADO"], index=index, cache_path=cache_path, adapter=adapter)
    second = resolve_query_vectors(
        ["GRAMADO", "gramado "], index=index, cache_path=cache_path, adapter=adapter
    )

    assert first.embedded_count == 1
    assert second.embedded_count == 0
    assert second.execution is None
    assert adapter.calls == [["gramado"]]
    assert cache_path.is_file()
    assert set(load_query_cache(cache_path, index).vectors) == {"gramado"}


def test_without_an_adapter_an_uncached_query_is_refused_instead_of_paid(
    catalog: PriceCatalog, tmp_path: Path
) -> None:
    index = fixture_semantic_index(catalog)
    cache_path = tmp_path / QUERY_CACHE_FILENAME

    with pytest.raises(ValuationValidationError) as error:
        resolve_query_vectors(["GRAMADO"], index=index, cache_path=cache_path, adapter=None)

    assert error.value.code == "SEMANTIC_QUERY_NOT_CACHED"
    assert not cache_path.exists()


def test_a_cache_of_another_model_is_refused_instead_of_mixed(
    catalog: PriceCatalog, tmp_path: Path
) -> None:
    index = fixture_semantic_index(catalog)
    cache_path = tmp_path / QUERY_CACHE_FILENAME
    cache_path.write_text(
        json.dumps(
            {
                "schema_version": "query-embeddings-v1",
                "model_id": "outro-modelo",
                "dims": FIXTURE_EMBEDDINGS_DIMS,
                "vectors": {},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValuationValidationError) as error:
        load_query_cache(cache_path, index)

    assert error.value.code == "QUERY_CACHE_MODEL_MISMATCH"


# --------------------------------------------------------------------------------------
# Shortlist híbrida
# --------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def takeoff_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("matching-takeoff")
    assert main(["takeoff-demo", "--output", str(root)]) == 0
    return root


def test_the_hybrid_shortlist_declares_its_semantic_lineage(
    catalog: PriceCatalog, takeoff_dir: Path
) -> None:
    packet = load_takeoff_packet(takeoff_dir / TAKEOFF_PACKET_FILENAME)
    index = fixture_semantic_index(catalog)

    suggestions = build_hybrid_code_suggestions(
        packet,
        catalog,
        None,
        index=index,
        query_vectors={
            normalize_query_text(item.label): fixture_vector(item.label)
            for item in packet.confirmed_items()
        },
        config=SuggestionConfig(max_candidates_per_item=5),
    )

    assert suggestions.suggester_version == SCO_HYBRID_SUGGESTER_VERSION
    assert suggestions.semantic is not None
    assert suggestions.semantic.model_id == FIXTURE_EMBEDDINGS_MODEL
    assert suggestions.semantic.dims == FIXTURE_EMBEDDINGS_DIMS
    assert suggestions.semantic.index_sha256 == index.index_sha256
    assert suggestions.refinement is None
    # A dominância do domínio continua valendo: unidade compatível manda sobre relevância.
    for suggestion in suggestions.suggestions:
        compatible = [candidate.unit_compatible for candidate in suggestion.candidates]
        assert compatible == sorted(compatible, reverse=True)


def test_an_item_without_a_query_vector_refuses_the_whole_hybrid_shortlist(
    catalog: PriceCatalog, takeoff_dir: Path
) -> None:
    packet = load_takeoff_packet(takeoff_dir / TAKEOFF_PACKET_FILENAME)

    with pytest.raises(ValuationValidationError) as error:
        build_hybrid_code_suggestions(
            packet, catalog, None, index=fixture_semantic_index(catalog), query_vectors={}
        )

    assert error.value.code == "SEMANTIC_QUERY_NOT_CACHED"


# --------------------------------------------------------------------------------------
# CLI: index-catalog e suggest-codes
# --------------------------------------------------------------------------------------


def _stdout(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    return dict(json.loads(lines[-1]))


def _write_catalog(directory: Path, catalog: PriceCatalog) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / CATALOG_FILENAME
    path.write_text(catalog.model_dump_json(indent=2), encoding="utf-8")
    return path


def test_index_catalog_without_a_spending_cap_refuses_before_any_call(
    catalog: PriceCatalog,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv(BUDGET_ENV, raising=False)
    monkeypatch.setenv(KEY_ENV, "sk-test")
    catalog_path = _write_catalog(tmp_path / "rodada", catalog)

    assert main(["index-catalog", "--catalog", str(catalog_path)]) == 2

    assert _stdout(capsys)["refused"] == "INDEX_EMBEDDINGS_UNAVAILABLE"
    assert not (catalog_path.parent / CATALOG_INDEX_FILENAME).exists()


def test_index_catalog_without_a_credential_refuses_before_any_call(
    catalog: PriceCatalog,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(BUDGET_ENV, "1.0")
    monkeypatch.delenv(KEY_ENV, raising=False)
    catalog_path = _write_catalog(tmp_path / "rodada", catalog)

    assert main(["index-catalog", "--catalog", str(catalog_path)]) == 2

    assert _stdout(capsys)["refused"] == "INDEX_EMBEDDINGS_UNAVAILABLE"
    assert not (catalog_path.parent / CATALOG_INDEX_FILENAME).exists()


def test_index_catalog_writes_the_index_next_to_the_catalog_and_reuses_it(
    catalog: PriceCatalog,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    adapter = _FixtureEmbeddingsAdapter()
    monkeypatch.setattr(
        "croquitodxf_worker.valuation.cli.build_embeddings_adapter", lambda: adapter
    )
    catalog_path = _write_catalog(tmp_path / "rodada", catalog)

    assert main(["index-catalog", "--catalog", str(catalog_path)]) == 0
    created = _stdout(capsys)
    assert main(["index-catalog", "--catalog", str(catalog_path)]) == 0
    reused = _stdout(capsys)

    assert created["status"] == "created"
    assert created["items"] == len(catalog.entries)
    assert created["dims"] == FIXTURE_EMBEDDINGS_DIMS
    assert created["batches"] == 1
    assert reused["status"] == "reused"
    # Idempotência que protege gasto: a segunda rodada não chamou o provider de novo.
    assert len(adapter.calls) == 1
    index_path = catalog_path.parent / CATALOG_INDEX_FILENAME
    assert load_semantic_index(index_path, catalog).catalog_sha256 == catalog.source_sha256


def test_suggest_codes_uses_the_round_index_when_it_is_there(
    catalog: PriceCatalog,
    takeoff_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    adapter = _FixtureEmbeddingsAdapter()
    monkeypatch.setattr(
        "croquitodxf_worker.valuation.cli.embeddings_adapter_or_reason", lambda: (adapter, None)
    )
    output_dir = tmp_path / "rodada"
    catalog_path = _write_catalog(output_dir, catalog)
    (output_dir / CATALOG_INDEX_FILENAME).write_text(
        index_document(fixture_catalog_index(catalog)), encoding="utf-8"
    )
    argv = [
        "suggest-codes",
        "--packet",
        str(takeoff_dir / TAKEOFF_PACKET_FILENAME),
        "--catalog",
        str(catalog_path),
        "--output",
        str(output_dir),
    ]

    assert main(argv) == 0

    payload = _stdout(capsys)
    assert payload["matching"] == "hybrid"
    assert payload["suggester_version"] == SCO_HYBRID_SUGGESTER_VERSION
    published = CodeSuggestionSet.model_validate_json(
        (output_dir / CODE_SUGGESTIONS_FILENAME).read_text(encoding="utf-8")
    )
    assert published.semantic is not None
    assert (output_dir / QUERY_CACHE_FILENAME).is_file()


def test_no_semantic_forces_the_lexical_shortlist_even_with_an_index(
    catalog: PriceCatalog,
    takeoff_dir: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output_dir = tmp_path / "rodada"
    catalog_path = _write_catalog(output_dir, catalog)
    (output_dir / CATALOG_INDEX_FILENAME).write_text(
        index_document(fixture_catalog_index(catalog)), encoding="utf-8"
    )
    argv = [
        "suggest-codes",
        "--packet",
        str(takeoff_dir / TAKEOFF_PACKET_FILENAME),
        "--catalog",
        str(catalog_path),
        "--output",
        str(output_dir),
        "--no-semantic",
    ]

    assert main(argv) == 0

    payload = _stdout(capsys)
    assert payload["matching"] == "lexical"
    assert payload["semantic_reason"] == SEMANTIC_DISABLED_BY_FLAG
    assert payload["suggester_version"] == SCO_SUGGESTER_VERSION
    assert not (output_dir / QUERY_CACHE_FILENAME).exists()


def test_without_the_index_the_shortlist_is_lexical_with_the_reason(
    catalog: PriceCatalog,
    takeoff_dir: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output_dir = tmp_path / "rodada"
    catalog_path = _write_catalog(output_dir, catalog)
    argv = [
        "suggest-codes",
        "--packet",
        str(takeoff_dir / TAKEOFF_PACKET_FILENAME),
        "--catalog",
        str(catalog_path),
        "--output",
        str(output_dir),
    ]

    assert main(argv) == 0

    payload = _stdout(capsys)
    assert payload["matching"] == "lexical"
    assert "index-catalog" in str(payload["semantic_reason"])


def test_an_index_of_another_catalog_refuses_suggest_codes_instead_of_degrading(
    catalog: PriceCatalog,
    takeoff_dir: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """No comando, índice velho é RECUSA: quem publica artefato precisa saber que apontou
    para a rodada errada. No servidor local a mesma situação vira degradação declarada."""
    output_dir = tmp_path / "rodada"
    catalog_path = _write_catalog(output_dir, catalog)
    other = catalog.model_copy(update={"source_sha256": "f" * 64})
    (output_dir / CATALOG_INDEX_FILENAME).write_text(
        index_document(fixture_catalog_index(other)), encoding="utf-8"
    )
    argv = [
        "suggest-codes",
        "--packet",
        str(takeoff_dir / TAKEOFF_PACKET_FILENAME),
        "--catalog",
        str(catalog_path),
        "--output",
        str(output_dir),
    ]

    assert main(argv) == 2

    assert _stdout(capsys)["refused"] == "INDEX_CATALOG_MISMATCH"
    assert not (output_dir / CODE_SUGGESTIONS_FILENAME).exists()
