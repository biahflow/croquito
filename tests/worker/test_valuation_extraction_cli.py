"""Wiring dos comandos pagos do M5: `suggest-codes --refine-arm`, `extract-legend-real` e
o gate `extraction-eval`.

Nenhum teste aqui chama provider de verdade: o caminho feliz monkeypatcha a fábrica de
braço e injeta um `FixtureProviderAdapter`, e os caminhos de recusa param antes da rede —
provider `fixture` proibido, teto de gasto ausente, página fora do manifest, documento fora
da allowlist e falha do adapter. Como no resto da medição, o que importa na recusa é o que
**não** aparece no diretório de saída.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from croquito_valuation.assignment import (
    SCO_LEXICAL_IDF_SUGGESTER_VERSION,
    SCO_REFINED_LEXICAL_IDF_SUGGESTER_VERSION,
    SCO_REFINED_SUGGESTER_VERSION,
    CodeSuggestion,
    CodeSuggestionSet,
)
from croquito_valuation.catalog import default_domain_synonyms, default_legend_noise
from croquito_valuation.contract import ContractWorkbook
from croquito_valuation.models import PriceCatalog
from croquito_valuation.takeoff import TakeoffItemStatus, load_takeoff_packet
from croquito_worker.providers import (
    FixtureProviderAdapter,
    LegendExtractionOutput,
    LegendRowOutput,
    NormalizedBox,
    PromptTask,
    ProviderAdapter,
    ProviderExecution,
    ProviderExecutionError,
    ProviderFailureCode,
    ProviderName,
    ProviderRequest,
    ScoItemRefinementOutput,
    ScoRefinementOutput,
)
from croquito_worker.valuation import cli as valuation_cli
from croquito_worker.valuation.cli import (
    CATALOG_FILENAME,
    CODE_SUGGESTIONS_FILENAME,
    CONTRACT_FILENAME,
    TAKEOFF_OVERLAY_FILENAME,
    TAKEOFF_PACKET_FILENAME,
    main,
)
from croquito_worker.valuation.extraction_eval import REPORT_FILENAME
from croquito_worker.valuation.legend_extraction import LEGEND_EXTRACTION_SAFETY_NOTES
from croquito_worker.valuation.plate import PLATE_IMAGE_FILENAME
from croquito_worker.valuation.sco_matching import build_hybrid_code_suggestions
from croquito_worker.valuation.sco_suggestion import TRANSMITTED_CANDIDATE_WINDOW
from croquito_worker.valuation.synthetic import build_synthetic_previous_mapao

ALLOWLIST = "CROQUITO_AI_EXTRACTION_ALLOWED_DIGESTS"
BUDGET = "CROQUITO_AI_MAX_ESTIMATED_COST_USD"
PROVIDER_KEYS = ("CROQUITO_ANTHROPIC_API_KEY", "CROQUITO_OPENAI_API_KEY")

_REAL_ARM = "sonnet=anthropic:claude-sonnet-5"
_FIXTURE_ARM = "fabricado=fixture:qualquer-modelo"
_RESERVE_ARM = "luna=openai:gpt-5.6-luna"
_RESERVE_MODEL_ID = "fixture-legend-reserva-v1"
_RESERVE_NOTE = "PROVIDER_FALLBACK_LEGEND_EXTRACTION_OPENAI"
_PLATE_ID = "prancha-cliente-de-teste"

_FIXTURE_MODEL_ID = "fixture-rerank-v1"


def _stdout(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    return dict(json.loads(lines[-1]))


def _is_empty(directory: Path) -> bool:
    return not directory.exists() or list(directory.iterdir()) == []


@dataclass(frozen=True, slots=True)
class Workspace:
    """Catálogo, consolidado e pacote revisado prontos, produzidos pelos comandos reais."""

    root: Path
    catalog_path: Path
    contract_path: Path
    packet_path: Path
    image_path: Path


@pytest.fixture(scope="module")
def workspace(tmp_path_factory: pytest.TempPathFactory) -> Workspace:
    """Roda uma vez por módulo: importar o MAPÃO e gerar a prancha são os passos caros."""
    root = tmp_path_factory.mktemp("valuation-paid")
    previous_path = build_synthetic_previous_mapao(root / "previous-mapao.xlsx")
    import_dir = root / "import"
    import_argv = ["import-workbook", "--input", str(previous_path), "--output", str(import_dir)]
    assert main(import_argv) == 0
    takeoff_dir = root / "takeoff"
    assert main(["takeoff-demo", "--output", str(takeoff_dir)]) == 0
    return Workspace(
        root=root,
        catalog_path=import_dir / CATALOG_FILENAME,
        contract_path=import_dir / CONTRACT_FILENAME,
        packet_path=takeoff_dir / TAKEOFF_PACKET_FILENAME,
        image_path=takeoff_dir / PLATE_IMAGE_FILENAME,
    )


def _suggest_argv(workspace: Workspace, output_dir: Path, *, refine_arm: str | None) -> list[str]:
    argv = [
        "suggest-codes",
        "--packet",
        str(workspace.packet_path),
        "--catalog",
        str(workspace.catalog_path),
        "--contract",
        str(workspace.contract_path),
        "--output",
        str(output_dir),
    ]
    if refine_arm is not None:
        argv += ["--refine-arm", refine_arm]
    return argv


def _lexical_suggestions(workspace: Workspace) -> CodeSuggestionSet:
    """A shortlist que a via determinística produz sem índice, calculada fora da CLI.

    `run_suggest_codes` carrega sinônimos de `synonyms.json` do diretório de saída se
    existir, senão o seed empacotado (`load_round_synonyms`); os testes deste arquivo usam
    um `--output` novo a cada rodada, sem `synonyms.json`, então a referência aqui precisa
    do mesmo seed para não divergir do que a CLI de fato publica (Fase 1 do M7).

    Desde 2026-08-21 a via sem índice é o braço léxico por cobertura ponderada, não a Dice:
    o oráculo reproduz a chamada do comando inteira, com `noise=default_legend_noise()`
    junto — sem ele a shortlist divergiria em silêncio.
    """
    return build_hybrid_code_suggestions(
        load_takeoff_packet(workspace.packet_path),
        PriceCatalog.model_validate_json(workspace.catalog_path.read_text(encoding="utf-8")),
        ContractWorkbook.model_validate_json(workspace.contract_path.read_text(encoding="utf-8")),
        synonyms=default_domain_synonyms(),
        noise=default_legend_noise(),
    )


def _window(suggestion: CodeSuggestion) -> list[str]:
    """Os candidatos de um item que o refino de fato recebe — a cauda não é transmitida."""
    return [c.code for c in suggestion.candidates[:TRANSMITTED_CANDIDATE_WINDOW]]


def _reversed_refinement(suggestions: CodeSuggestionSet) -> ScoRefinementOutput:
    """Permutação válida e visível: a JANELA de cada item devolvida ao contrário.

    Inverter a shortlist inteira deixou de ser resposta possível quando a shortlist passou
    a ter 15 candidatos: `ranked_codes` aceita no máximo 10, e é isso que o estágio envia.
    """
    return ScoRefinementOutput(
        items=[
            ScoItemRefinementOutput(
                item_id=suggestion.item_id,
                ranked_codes=list(reversed(_window(suggestion))),
                rationale="fixture de teste: shortlist invertida",
                flags=["ordem-invertida"],
            )
            for suggestion in suggestions.suggestions
        ]
    )


def _refinement_adapter(suggestions: CodeSuggestionSet) -> FixtureProviderAdapter:
    return FixtureProviderAdapter(
        provider=ProviderName.ANTHROPIC,
        model_id=_FIXTURE_MODEL_ID,
        outputs={PromptTask.SCO_REFINEMENT: _reversed_refinement(suggestions)},
    )


@dataclass(frozen=True, slots=True)
class _FailingAdapter:
    """Braço que falha como um provider fora do ar; nada deve ser publicado depois dele."""

    code: ProviderFailureCode

    def execute(self, request: ProviderRequest) -> ProviderExecution:
        raise ProviderExecutionError(self.code)


def _patch_arm(
    monkeypatch: pytest.MonkeyPatch, name: str, adapter: ProviderAdapter, model_id: str
) -> None:
    monkeypatch.setattr(
        valuation_cli,
        name,
        lambda arm_spec: (arm_spec.partition("=")[0], model_id, adapter),
    )


def _forbid_real_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Garante que uma recusa de gate seja recusa mesmo na máquina de quem tem credencial."""
    monkeypatch.delenv(BUDGET, raising=False)
    for key in PROVIDER_KEYS:
        monkeypatch.delenv(key, raising=False)


# --------------------------------------------------------------------------------------
# suggest-codes --refine-arm
# --------------------------------------------------------------------------------------


def test_suggest_codes_without_the_flag_publishes_the_lexical_shortlist(
    workspace: Workspace, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Regressão do M4: sem a flag, o artefato é exatamente a shortlist determinística."""
    output_dir = tmp_path / "lexical"

    assert main(_suggest_argv(workspace, output_dir, refine_arm=None)) == 0

    payload = _stdout(capsys)
    assert payload["suggester_version"] == SCO_LEXICAL_IDF_SUGGESTER_VERSION
    assert "refinement" not in payload
    published = CodeSuggestionSet.model_validate_json(
        (output_dir / CODE_SUGGESTIONS_FILENAME).read_text(encoding="utf-8")
    )
    assert published == _lexical_suggestions(workspace)
    assert published.refinement is None
    assert all(
        candidate.refinement_note is None
        for suggestion in published.suggestions
        for candidate in suggestion.candidates
    )


def test_suggest_codes_with_a_refine_arm_publishes_the_reordered_shortlist(
    workspace: Workspace,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    lexical = _lexical_suggestions(workspace)
    _patch_arm(monkeypatch, "_build_refine_arm", _refinement_adapter(lexical), _FIXTURE_MODEL_ID)
    output_dir = tmp_path / "refined"

    assert main(_suggest_argv(workspace, output_dir, refine_arm=_REAL_ARM)) == 0

    published = CodeSuggestionSet.model_validate_json(
        (output_dir / CODE_SUGGESTIONS_FILENAME).read_text(encoding="utf-8")
    )
    assert published.suggester_version == SCO_REFINED_LEXICAL_IDF_SUGGESTER_VERSION
    assert published.refinement is not None
    assert published.refinement.model_id == _FIXTURE_MODEL_ID
    assert published.refinement.prompt_version == "sco-refinement@1.0.2"
    # A ordem publicada é a pedida pelo refino na JANELA, a cauda fica onde a via léxica a
    # pôs, e o conjunto de códigos publicado continua sendo exatamente o mesmo.
    for before, after in zip(lexical.suggestions, published.suggestions, strict=True):
        tail = [c.code for c in before.candidates[TRANSMITTED_CANDIDATE_WINDOW:]]
        assert [c.code for c in after.candidates] == [*reversed(_window(before)), *tail]
        assert sorted(c.code for c in after.candidates) == sorted(c.code for c in before.candidates)
        assert after.candidates[0].refinement_note == (
            "fixture de teste: shortlist invertida | flags: ordem-invertida"
        )
    payload = _stdout(capsys)
    refinement = payload["refinement"]
    assert isinstance(refinement, dict)
    assert refinement["arm"] == _REAL_ARM
    assert refinement["provider"] == "anthropic"
    assert refinement["model_id"] == _FIXTURE_MODEL_ID
    assert set(refinement) >= {
        "estimated_cost_usd",
        "input_tokens",
        "output_tokens",
        "latency_ms",
        "input_digest",
        "calls",
    }
    # O refino fatia os itens em lotes que caibam no payload: quem lê o relatório precisa
    # saber quantas chamadas pagas a prancha custou, não só que "houve refino".
    calls = refinement["calls"]
    assert isinstance(calls, int)
    assert calls >= 1
    assert refinement["input_digest"] == published.refinement.input_digest


def test_suggest_codes_refuses_a_fixture_provider_as_refine_arm(
    workspace: Workspace, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Comando de produção não publica observação fabricada, nem quando quem pede sou eu."""
    output_dir = tmp_path / "fixture-arm"

    exit_code = main(_suggest_argv(workspace, output_dir, refine_arm=_FIXTURE_ARM))

    assert exit_code == 2
    assert _stdout(capsys)["refused"] == "REFINE_ARM_FIXTURE_FORBIDDEN"
    assert _is_empty(output_dir)


@pytest.mark.parametrize("arm", ["sonnet", "sonnet=anthropic", "=anthropic:claude-sonnet-5"])
def test_suggest_codes_refuses_a_malformed_refine_arm(
    workspace: Workspace, tmp_path: Path, capsys: pytest.CaptureFixture[str], arm: str
) -> None:
    output_dir = tmp_path / "malformed"

    exit_code = main(_suggest_argv(workspace, output_dir, refine_arm=arm))

    assert exit_code == 2
    assert _stdout(capsys)["refused"] == "REFINE_ARM_INVALID"
    assert _is_empty(output_dir)


def test_suggest_codes_refuses_a_refine_arm_without_a_spending_cap(
    workspace: Workspace,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Sem teto de gasto declarado a fábrica recusa, e a recusa acontece antes da rede."""
    _forbid_real_providers(monkeypatch)
    output_dir = tmp_path / "no-budget"

    exit_code = main(_suggest_argv(workspace, output_dir, refine_arm=_REAL_ARM))

    assert exit_code == 2
    assert _stdout(capsys)["refused"] == "REFINE_ARM_UNAVAILABLE"
    assert _is_empty(output_dir)


def test_suggest_codes_publishes_nothing_when_the_provider_fails(
    workspace: Workspace,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Nem o lexical: quem quer a shortlist determinística roda o comando sem a flag."""
    _patch_arm(
        monkeypatch,
        "_build_refine_arm",
        _FailingAdapter(ProviderFailureCode.TIMEOUT),
        _FIXTURE_MODEL_ID,
    )
    output_dir = tmp_path / "provider-down"

    exit_code = main(_suggest_argv(workspace, output_dir, refine_arm=_REAL_ARM))

    assert exit_code == 2
    payload = _stdout(capsys)
    assert payload["refused"] == "PROVIDER_EXECUTION_FAILED"
    assert payload["details"] == {"code": "TIMEOUT"}
    assert _is_empty(output_dir)


# --------------------------------------------------------------------------------------
# extract-legend-real
# --------------------------------------------------------------------------------------


def _legend_output() -> LegendExtractionOutput:
    return LegendExtractionOutput(
        rows=[
            LegendRowOutput(
                raw_text="PISO INTERTRAVADO 61,20 M2",
                label="PISO INTERTRAVADO",
                quantity_text="61,20",
                unit_text="M2",
                bbox=NormalizedBox(left=0.60, top=0.20, right=0.95, bottom=0.24),
                legibility="clear",
            ),
            LegendRowOutput(
                raw_text="PISO EMBORRACHADO --- M2",
                label="PISO EMBORRACHADO",
                quantity_text=None,
                unit_text="M2",
                bbox=NormalizedBox(left=0.60, top=0.26, right=0.95, bottom=0.30),
                legibility="illegible",
            ),
        ],
        page_notes=["fixture de teste"],
    )


def _legend_adapter() -> FixtureProviderAdapter:
    return FixtureProviderAdapter(
        provider=ProviderName.ANTHROPIC,
        model_id="fixture-legend-v1",
        outputs={PromptTask.LEGEND_EXTRACTION: _legend_output()},
    )


def _legend_reserve_adapter() -> FixtureProviderAdapter:
    """Reserva num provider DIFERENTE do escolhido: é o que torna a nota verificável."""
    return FixtureProviderAdapter(
        provider=ProviderName.OPENAI,
        model_id=_RESERVE_MODEL_ID,
        outputs={PromptTask.LEGEND_EXTRACTION: _legend_output()},
    )


def _patch_legend_arms(
    monkeypatch: pytest.MonkeyPatch, arms: dict[str, tuple[str, ProviderAdapter]]
) -> None:
    """Fábrica de braço por spec: o `--arm` e o `--reserve-arm` viram adapters diferentes.

    Spec fora do mapa cai na fábrica REAL, e é assim que a recusa de braço de reserva mal
    escrito continua sendo exercida pelo código de produção em vez de pelo dublê.
    """
    original = valuation_cli._build_paid_arm

    def _factory(arm_spec: str) -> tuple[str, str, ProviderAdapter]:
        found = arms.get(arm_spec)
        if found is None:
            return original(arm_spec)
        model_id, adapter = found
        return arm_spec.partition("=")[0], model_id, adapter

    monkeypatch.setattr(valuation_cli, "_build_legend_arm", _factory)


def _manifest(path: Path, *, source_digest: str, page_digest: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"source_sha256": source_digest, "pages": [{"image_sha256": page_digest}]}),
        encoding="utf-8",
    )
    return path


def _extract_argv(
    workspace: Workspace,
    manifest: Path,
    output_dir: Path,
    *,
    arm: str,
    reserve_arm: str | None = None,
) -> list[str]:
    return [
        "extract-legend-real",
        "--image",
        str(workspace.image_path),
        "--manifest",
        str(manifest),
        "--arm",
        arm,
        *(() if reserve_arm is None else ("--reserve-arm", reserve_arm)),
        "--plate-id",
        _PLATE_ID,
        "--page-number",
        "1",
        "--output",
        str(output_dir),
    ]


def test_extract_legend_real_publishes_a_packet_bound_to_the_authorised_document(
    workspace: Workspace,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    image_digest = hashlib.sha256(workspace.image_path.read_bytes()).hexdigest()
    document_digest = "d" * 64
    manifest = _manifest(
        tmp_path / "manifest.json", source_digest=document_digest, page_digest=image_digest
    )
    monkeypatch.setenv(ALLOWLIST, document_digest)
    _patch_arm(monkeypatch, "_build_legend_arm", _legend_adapter(), "fixture-legend-v1")
    output_dir = tmp_path / "extract-real"

    assert main(_extract_argv(workspace, manifest, output_dir, arm=_REAL_ARM)) == 0

    payload = _stdout(capsys)
    assert payload["review_status"] == "review_required"
    assert payload["confirmed"] == 0
    assert payload["proposed"] == 1
    assert payload["ambiguous"] == 1
    assert payload["source_sha256"] == document_digest
    assert payload["image_sha256"] == image_digest
    extraction = payload["extraction"]
    assert isinstance(extraction, dict)
    assert extraction["prompt_version"] == "legend-extraction@1.0.1"
    packet = load_takeoff_packet(output_dir / TAKEOFF_PACKET_FILENAME)
    assert packet.plate_id == _PLATE_ID
    assert packet.image_sha256 == image_digest
    assert packet.source_pdf_sha256 == document_digest
    assert packet.confirmed_items() == []
    assert [item.status for item in packet.items] == [
        TakeoffItemStatus.PROPOSED,
        TakeoffItemStatus.AMBIGUOUS,
    ]
    assert (output_dir / TAKEOFF_OVERLAY_FILENAME).is_file()


def test_extract_legend_real_without_a_reserve_arm_publishes_the_usual_safety_notes(
    workspace: Workspace,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sem `--reserve-arm` o pacote é o de sempre: três notas, nenhuma de degradação."""
    image_digest = hashlib.sha256(workspace.image_path.read_bytes()).hexdigest()
    document_digest = "d" * 64
    manifest = _manifest(
        tmp_path / "manifest.json", source_digest=document_digest, page_digest=image_digest
    )
    monkeypatch.setenv(ALLOWLIST, document_digest)
    _patch_arm(monkeypatch, "_build_legend_arm", _legend_adapter(), "fixture-legend-v1")
    output_dir = tmp_path / "sem-reserva"

    assert main(_extract_argv(workspace, manifest, output_dir, arm=_REAL_ARM)) == 0

    packet = load_takeoff_packet(output_dir / TAKEOFF_PACKET_FILENAME)
    assert packet.safety_notes == list(LEGEND_EXTRACTION_SAFETY_NOTES)


def test_extract_legend_real_degrades_to_the_reserve_arm_and_names_who_answered(
    workspace: Workspace,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    image_digest = hashlib.sha256(workspace.image_path.read_bytes()).hexdigest()
    document_digest = "d" * 64
    manifest = _manifest(
        tmp_path / "manifest.json", source_digest=document_digest, page_digest=image_digest
    )
    monkeypatch.setenv(ALLOWLIST, document_digest)
    _patch_legend_arms(
        monkeypatch,
        {
            _REAL_ARM: ("fixture-legend-v1", _FailingAdapter(ProviderFailureCode.UNAVAILABLE)),
            _RESERVE_ARM: (_RESERVE_MODEL_ID, _legend_reserve_adapter()),
        },
    )
    output_dir = tmp_path / "com-reserva"

    exit_code = main(
        _extract_argv(workspace, manifest, output_dir, arm=_REAL_ARM, reserve_arm=_RESERVE_ARM)
    )

    assert exit_code == 0
    packet = load_takeoff_packet(output_dir / TAKEOFF_PACKET_FILENAME)
    assert packet.safety_notes == [*LEGEND_EXTRACTION_SAFETY_NOTES, _RESERVE_NOTE]
    # O braço que respondeu assina o pacote e o lineage; o `--arm` escolhido não.
    assert all(item.extractor == f"openai:{_RESERVE_MODEL_ID}" for item in packet.items)
    payload = _stdout(capsys)
    extraction = payload["extraction"]
    assert isinstance(extraction, dict)
    assert extraction["provider"] == "openai"
    assert extraction["model_id"] == _RESERVE_MODEL_ID
    assert (output_dir / TAKEOFF_OVERLAY_FILENAME).is_file()


def test_extract_legend_real_refuses_a_malformed_reserve_arm_before_calling_anyone(
    workspace: Workspace,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Reserva mal escrita recusa o comando: ignorá-la prometeria degradação inexistente."""
    image_digest = hashlib.sha256(workspace.image_path.read_bytes()).hexdigest()
    manifest = _manifest(
        tmp_path / "manifest.json", source_digest="d" * 64, page_digest=image_digest
    )
    monkeypatch.setenv(ALLOWLIST, "d" * 64)
    primary = _FailingAdapter(ProviderFailureCode.TIMEOUT)
    _patch_legend_arms(monkeypatch, {_REAL_ARM: ("fixture-legend-v1", primary)})
    output_dir = tmp_path / "reserva-invalida"

    exit_code = main(
        _extract_argv(workspace, manifest, output_dir, arm=_REAL_ARM, reserve_arm="lixo")
    )

    assert exit_code == 2
    assert _stdout(capsys)["refused"] == "REFINE_ARM_INVALID"
    assert _is_empty(output_dir)


def test_extract_legend_real_refuses_a_fixture_reserve_arm(
    workspace: Workspace,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Observação fabricada não vira artefato publicado — nem pela porta da reserva."""
    image_digest = hashlib.sha256(workspace.image_path.read_bytes()).hexdigest()
    manifest = _manifest(
        tmp_path / "manifest.json", source_digest="d" * 64, page_digest=image_digest
    )
    monkeypatch.setenv(ALLOWLIST, "d" * 64)
    _patch_legend_arms(monkeypatch, {_REAL_ARM: ("fixture-legend-v1", _legend_adapter())})
    output_dir = tmp_path / "reserva-fixture"

    exit_code = main(
        _extract_argv(workspace, manifest, output_dir, arm=_REAL_ARM, reserve_arm=_FIXTURE_ARM)
    )

    assert exit_code == 2
    assert _stdout(capsys)["refused"] == "REFINE_ARM_FIXTURE_FORBIDDEN"
    assert _is_empty(output_dir)


def test_extract_legend_real_refuses_a_page_outside_the_manifest(
    workspace: Workspace,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    manifest = _manifest(tmp_path / "manifest.json", source_digest="d" * 64, page_digest="e" * 64)
    monkeypatch.setenv(ALLOWLIST, "d" * 64)
    _patch_arm(monkeypatch, "_build_legend_arm", _legend_adapter(), "fixture-legend-v1")
    output_dir = tmp_path / "outside-manifest"

    exit_code = main(_extract_argv(workspace, manifest, output_dir, arm=_REAL_ARM))

    assert exit_code == 2
    assert _stdout(capsys)["refused"] == "EXTRACTION_NOT_ALLOWLISTED"
    assert _is_empty(output_dir)


def test_extract_legend_real_refuses_a_document_outside_the_allowlist(
    workspace: Workspace,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    image_digest = hashlib.sha256(workspace.image_path.read_bytes()).hexdigest()
    manifest = _manifest(
        tmp_path / "manifest.json", source_digest="d" * 64, page_digest=image_digest
    )
    monkeypatch.setenv(ALLOWLIST, "")
    _patch_arm(monkeypatch, "_build_legend_arm", _legend_adapter(), "fixture-legend-v1")
    output_dir = tmp_path / "outside-allowlist"

    exit_code = main(_extract_argv(workspace, manifest, output_dir, arm=_REAL_ARM))

    assert exit_code == 2
    assert _stdout(capsys)["refused"] == "EXTRACTION_NOT_ALLOWLISTED"
    assert _is_empty(output_dir)


def test_extract_legend_real_refuses_a_fixture_provider(
    workspace: Workspace,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    image_digest = hashlib.sha256(workspace.image_path.read_bytes()).hexdigest()
    manifest = _manifest(
        tmp_path / "manifest.json", source_digest="d" * 64, page_digest=image_digest
    )
    monkeypatch.setenv(ALLOWLIST, "d" * 64)
    output_dir = tmp_path / "fixture-provider"

    exit_code = main(_extract_argv(workspace, manifest, output_dir, arm=_FIXTURE_ARM))

    assert exit_code == 2
    assert _stdout(capsys)["refused"] == "REFINE_ARM_FIXTURE_FORBIDDEN"
    assert _is_empty(output_dir)


def test_extract_legend_real_refuses_without_a_spending_cap(
    workspace: Workspace,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    image_digest = hashlib.sha256(workspace.image_path.read_bytes()).hexdigest()
    manifest = _manifest(
        tmp_path / "manifest.json", source_digest="d" * 64, page_digest=image_digest
    )
    monkeypatch.setenv(ALLOWLIST, "d" * 64)
    _forbid_real_providers(monkeypatch)
    output_dir = tmp_path / "no-budget-extract"

    exit_code = main(_extract_argv(workspace, manifest, output_dir, arm=_REAL_ARM))

    assert exit_code == 2
    assert _stdout(capsys)["refused"] == "REFINE_ARM_UNAVAILABLE"
    assert _is_empty(output_dir)


# --------------------------------------------------------------------------------------
# extraction-eval (modo offline)
# --------------------------------------------------------------------------------------


def test_extraction_eval_runs_offline_and_passes_every_gate(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output_dir = tmp_path / "eval"

    exit_code = main(["extraction-eval", "--output", str(output_dir)])

    assert exit_code == 0
    payload = _stdout(capsys)
    assert payload["passed"] is True
    checks = payload["checks"]
    assert isinstance(checks, dict)
    assert checks == {
        "no_item_born_confirmed": True,
        "all_items_matched_gabarito": True,
        "real_arm_without_budget_refused": True,
        "refinement_outside_shortlist_refused": True,
        "tampered_image_refused": True,
    }
    arms = payload["arms"]
    assert isinstance(arms, list)
    arm = dict(arms[0])
    assert arm["name"] == "fixture"
    assert arm["legend_recall"] == 1.0
    assert arm["quantity_accuracy"] == 1.0
    assert arm["sco_top1"] == 1.0
    # O refino ganha da baseline lexical na prancha sintética; é isso que a eval mostra.
    assert arm["lexical_sco_top1"] < arm["sco_top1"]
    assert (output_dir / REPORT_FILENAME).is_file()


def test_extraction_eval_report_records_the_fixture_honesty_note(tmp_path: Path) -> None:
    """Relatório de braço fixture diz, no próprio arquivo, o que ele não mede."""
    output_dir = tmp_path / "eval-notes"

    assert main(["extraction-eval", "--output", str(output_dir)]) == 0

    report = json.loads((output_dir / REPORT_FILENAME).read_text(encoding="utf-8"))
    assert report["arms"][0]["notes"]
    assert "não precisão" in report["arms"][0]["notes"][0]
    assert report["arms"][0]["suggester_version"] == SCO_REFINED_SUGGESTER_VERSION
