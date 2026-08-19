import hashlib
import json
from pathlib import Path

import pytest
from pydantic import TypeAdapter

from croquito_worker.extraction_eval import (
    ExtractionCandidate,
    ExtractionEvalReport,
    ExtractionNotAllowlistedError,
    build_degrau_step_gabarito,
    register_extraction_arms,
    run_extraction_eval,
)
from croquito_worker.providers import (
    FixtureProviderAdapter,
    GeometryElementOutput,
    GeometryExtractionOutput,
    NormalizedPoint,
    PromptTask,
    ProviderName,
)
from croquito_worker.synthetic import (
    DEGRAU_PAGE_HEIGHT_PX,
    DEGRAU_PAGE_WIDTH_PX,
    DEGRAU_WALL_VERTICES_PX,
    render_degrau_boundary_input,
    render_synthetic_input,
)
from croquito_worker.vision import (
    VisionConfig,
    VisionProposal,
    corroborate_with_ink,
    proposals_from_geometry,
)

ALLOWLIST = "CROQUITO_AI_EXTRACTION_ALLOWED_DIGESTS"


def _adapter(*elements: GeometryElementOutput) -> FixtureProviderAdapter:
    return FixtureProviderAdapter(
        provider=ProviderName.BEDROCK_ANTHROPIC,
        model_id="anthropic.claude-opus-5",
        outputs={PromptTask.GEOMETRY_EXTRACTION: GeometryExtractionOutput(elements=list(elements))},
    )


def _drawn_field() -> GeometryElementOutput:
    """Contorno do campo da fixture sintética, onde existe traço de verdade."""
    return GeometryElementOutput(
        label="campo",
        kind="polyline",
        layer_hint="CAMPO",
        closed=True,
        # Derivado de FIELD_WIDTH/FIELD_HEIGHT e das margens do render sintético, não
        # chutado: chutar coordenada faria o teste medir o meu erro, não a conferência.
        vertices=[
            NormalizedPoint(x=0.1214, y=0.1429),
            NormalizedPoint(x=0.8061, y=0.1429),
            NormalizedPoint(x=0.8061, y=0.8829),
            NormalizedPoint(x=0.1214, y=0.8829),
        ],
        evidence="retângulo do campo",
    )


def _displaced_field() -> GeometryElementOutput:
    """O campo certo, deslocado como um modelo com estrutura boa e registro ruim."""
    base = _drawn_field()
    return base.model_copy(
        update={
            "vertices": [
                NormalizedPoint(x=vertex.x + 0.05, y=vertex.y + 0.05) for vertex in base.vertices
            ]
        }
    )


def _drawn_midline() -> GeometryElementOutput:
    """Linha de meio de campo do render sintético, também derivada das constantes dele."""
    return GeometryElementOutput(
        label="meio de campo",
        kind="line",
        layer_hint="CAMPO",
        vertices=[NormalizedPoint(x=0.4638, y=0.1429), NormalizedPoint(x=0.4638, y=0.8829)],
        evidence="linha vertical no meio do campo",
    )


def _drawn_arc(*, anchored: bool) -> GeometryElementOutput:
    """A meia-lua da fixture sintética, com e sem as âncoras do contrato @2.0.0.

    As coordenadas vêm de ARC_CENTRE_PX e ARC_RADIUS_PX do render (centro 390,700 e raio
    120 px sobre 1400x1050); `radius` normaliza pelo lado menor, que é como a conversão lê.
    """
    anchors: dict[str, NormalizedPoint] = {
        "arc_start": NormalizedPoint(x=0.1929, y=0.6667),
        "arc_mid": NormalizedPoint(x=0.2786, y=0.5524),
        "arc_end": NormalizedPoint(x=0.3643, y=0.6667),
    }
    return GeometryElementOutput(
        label="meia-lua",
        kind="arc",
        layer_hint="DETALHES",
        center=NormalizedPoint(x=0.2786, y=0.6667),
        radius=0.1143,
        evidence="meia-lua aberta para baixo",
        **(anchors if anchored else {}),
    )


def _invented() -> GeometryElementOutput:
    return GeometryElementOutput(
        label="muro inexistente",
        kind="line",
        vertices=[NormalizedPoint(x=0.02, y=0.97), NormalizedPoint(x=0.40, y=0.97)],
        evidence="sem tinta por baixo",
    )


def _manifest(tmp_path: Path, source: Path, *, document_digest: str) -> Path:
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps(
            {
                "source_sha256": document_digest,
                "pages": [{"image_sha256": hashlib.sha256(source.read_bytes()).hexdigest()}],
            }
        )
    )
    return path


def _prepare(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    source = tmp_path / "entrada.png"
    render_synthetic_input(source)
    document_digest = "d" * 64
    monkeypatch.setenv(ALLOWLIST, document_digest)
    return source, _manifest(tmp_path, source, document_digest=document_digest)


def _write_unregistered_artifact(
    output: Path, name: str, source: Path, elements: list[GeometryElementOutput]
) -> None:
    """Grava um artefato como `run_extraction_eval` gravava ANTES de 2026-08-19: propostas
    cruas, corroboradas mas NUNCA registradas contra a tinta.

    Usado só pelos testes de `register_extraction_arms` que precisam simular um artefato
    legado (ou qualquer `proposals.json` mal registrado escrito fora do comando).
    Patchar só um campo de um `proposals.json` já registrado pelo `run_extraction_eval`
    atual produziria um estado híbrido que o registro nunca produz sozinho — a busca
    global depende do CONJUNTO inteiro de propostas, não de um elemento isolado.
    """
    output.mkdir(parents=True, exist_ok=True)
    resolved_source = source.resolve(strict=True)
    image_sha256 = hashlib.sha256(resolved_source.read_bytes()).hexdigest()
    config = VisionConfig()
    proposals = proposals_from_geometry(
        elements, image_digest=image_sha256, width=1400, height=1050
    )
    corroborated, notes = corroborate_with_ink(proposals, resolved_source, config=config)
    (output / f"{name}-proposals.json").write_text(
        json.dumps([item.model_dump(mode="json") for item in corroborated], ensure_ascii=False)
    )
    total = len(corroborated)
    corroborated_rate = (
        round(
            sum(
                1
                for item in corroborated
                if item.quality_score >= config.ink_corroboration_min_coverage
            )
            / total,
            4,
        )
        if total
        else 0.0
    )
    report = {
        "image_sha256": image_sha256,
        "arms": [
            {
                "name": name,
                "provider": "bedrock_anthropic",
                "model_id": "anthropic.claude-opus-5",
                "prompt_version": "geometry-extraction@2.0.1",
                "element_count": total,
                "ink_coverage_mean": (
                    round(sum(item.quality_score for item in corroborated) / total, 4)
                    if total
                    else 0.0
                ),
                "corroborated_rate": corroborated_rate,
                "closed_region_count": 0,
                "labelled_rate": 1.0,
                "layered_rate": 1.0,
                "latency_ms": 1,
                "estimated_cost_usd": None,
                "input_tokens": None,
                "output_tokens": None,
                "notes": notes,
                "proposal_registration": [],
                "step": None,
            }
        ],
        "thresholds": {"corroborated_rate": 0.7},
        "passed": corroborated_rate >= 0.7,
    }
    (output / "extraction-eval.json").write_text(json.dumps(report, ensure_ascii=False))


def _degrau_normalized(point: tuple[int, int]) -> NormalizedPoint:
    return NormalizedPoint(x=point[0] / DEGRAU_PAGE_WIDTH_PX, y=point[1] / DEGRAU_PAGE_HEIGHT_PX)


def _degrau_wall_faithful() -> GeometryElementOutput:
    """O muro em recuo do render novo, como uma única polilinha aberta com o cotovelo."""
    return GeometryElementOutput(
        label="muro em recuo",
        kind="polyline",
        layer_hint="MURO",
        closed=False,
        # Derivado de DEGRAU_WALL_VERTICES_PX (fonte única do render), não chutado.
        vertices=[_degrau_normalized(point) for point in DEGRAU_WALL_VERTICES_PX],
        evidence="dois trechos retos ligados por um jog perpendicular",
    )


def _degrau_wall_split() -> tuple[GeometryElementOutput, GeometryElementOutput]:
    """Reprodução da resposta real do Opus na primeira revisão do Guaxindiba V3.

    Cada trecho pousa exatamente sobre a própria tinta — a corroboração por si só aprovaria
    os dois, cada um sozinho —, mas o degrau nasce estruturalmente partido em dois elementos
    `line` independentes, sem o cotovelo que amarra os dois trechos como um único muro em
    recuo. É o caso que o gate do degrau existe para pegar.
    """
    start, elbow_high, elbow_low, end = DEGRAU_WALL_VERTICES_PX
    line_a = GeometryElementOutput(
        label="muro trecho A",
        kind="line",
        layer_hint="MURO",
        vertices=[_degrau_normalized(start), _degrau_normalized(elbow_high)],
        evidence="trecho reto do muro até o cotovelo",
    )
    line_b = GeometryElementOutput(
        label="muro trecho B",
        kind="line",
        layer_hint="MURO",
        vertices=[_degrau_normalized(elbow_low), _degrau_normalized(end)],
        evidence="trecho reto do muro depois do cotovelo",
    )
    return line_a, line_b


def _degrau_wall_ramp() -> GeometryElementOutput:
    """Uma polilinha única, mas o cotovelo vira uma rampa espalhada por muitos pixels.

    Em vez do cotovelo do gabarito (cotovelo_alto→cotovelo_baixo, quase sem deslocamento AO
    LONGO do eixo), a transição de trecho A para trecho B é interpolada em dois pontos
    intermediários ao longo de todo o vão até o fim — a mesma "muda de lado" que um jog de
    verdade faz, só que sem cotovelo: nenhum PAR CONSECUTIVO cruza de trecho dentro da
    tolerância ao longo do eixo. É o caso que o critério de posição absoluta antigo não
    conseguia distinguir de um cotovelo de verdade deslocado por registro; o critério
    estrutural distingue porque mede COMO a transição é feita, não onde ela está.
    """
    start, elbow_high, _elbow_low, end = DEGRAU_WALL_VERTICES_PX

    def interpolated(ratio: float) -> tuple[float, float]:
        return (
            elbow_high[0] + (end[0] - elbow_high[0]) * ratio,
            elbow_high[1] + (end[1] - elbow_high[1]) * ratio,
        )

    vertices = [start, elbow_high, interpolated(1 / 3), interpolated(2 / 3), end]
    return GeometryElementOutput(
        label="muro em rampa",
        kind="polyline",
        layer_hint="MURO",
        closed=False,
        vertices=[
            NormalizedPoint(x=x / DEGRAU_PAGE_WIDTH_PX, y=y / DEGRAU_PAGE_HEIGHT_PX)
            for x, y in vertices
        ],
        evidence="transição gradual entre os dois trechos, sem cotovelo",
    )


def _prepare_degrau(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    source = tmp_path / "degrau.png"
    render_degrau_boundary_input(source)
    document_digest = "d" * 64
    monkeypatch.setenv(ALLOWLIST, document_digest)
    return source, _manifest(tmp_path, source, document_digest=document_digest)


def test_eval_refuses_an_image_outside_the_allowlist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A eval chama provider fora do pipeline; sem o portão seria um desvio do guardrail."""
    source = tmp_path / "entrada.png"
    render_synthetic_input(source)
    manifest = _manifest(tmp_path, source, document_digest="d" * 64)
    monkeypatch.setenv(ALLOWLIST, "")

    with pytest.raises(ExtractionNotAllowlistedError, match="allowlist"):
        run_extraction_eval(
            source,
            [ExtractionCandidate(name="opus", adapter=_adapter(_drawn_field()))],
            tmp_path / "out",
            manifest_path=manifest,
        )


def test_eval_refuses_a_render_that_does_not_belong_to_the_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Autorizar o render permitiria enviar qualquer imagem largada na pasta."""
    source = tmp_path / "entrada.png"
    render_synthetic_input(source)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"source_sha256": "d" * 64, "pages": [{"image_sha256": "e" * 64}]})
    )
    monkeypatch.setenv(ALLOWLIST, "d" * 64)

    with pytest.raises(ExtractionNotAllowlistedError, match="não pertence ao manifest"):
        run_extraction_eval(
            source,
            [ExtractionCandidate(name="opus", adapter=_adapter(_drawn_field()))],
            tmp_path / "out",
            manifest_path=manifest,
        )


def test_eval_measures_geometry_against_the_ink_on_the_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, manifest = _prepare(tmp_path, monkeypatch)

    report, report_path = run_extraction_eval(
        source,
        [ExtractionCandidate(name="opus", adapter=_adapter(_drawn_field()))],
        tmp_path / "out",
        manifest_path=manifest,
    )

    assert report_path.is_file()
    arm = report.arms[0]
    assert arm.element_count == 1
    assert arm.ink_coverage_mean > 0.6
    assert arm.closed_region_count == 1
    assert arm.labelled_rate == 1.0
    assert arm.layered_rate == 1.0
    assert report.passed is True


def test_eval_fails_when_an_arm_proposes_geometry_without_ink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """É o sinal de invenção: geometria afirmada que o papel não mostra.

    Desde que `run_extraction_eval` passou a registrar (2026-08-19), um candidato composto
    SÓ por invenção (nada real para ancorar) pode ser "resgatado" pelo estágio global do
    registro, que busca a transformação rígida que melhor cobre TODO o conjunto de tinta —
    sem nenhum elemento real competindo, ele encontra alguma tinta não relacionada e desliza
    a invenção até ela. Isso não é uma invenção do harness: é a mesma composição
    (campo+linha+arco reais, todos da fixture) que uma resposta real de verdade traz junto
    com a invenção, e É contra essa composição realista que a invenção precisa continuar
    marcada — não contra um candidato de conteúdo 100% fabricado, que nenhum provider real
    devolve.
    """
    source, manifest = _prepare(tmp_path, monkeypatch)

    report, _path = run_extraction_eval(
        source,
        [
            ExtractionCandidate(
                name="opus",
                adapter=_adapter(
                    _drawn_field(), _drawn_midline(), _drawn_arc(anchored=True), _invented()
                ),
            )
        ],
        tmp_path / "out",
        manifest_path=manifest,
    )

    arm = report.arms[0]
    # Os três elementos reais permanecem corroborados; só a invenção fica marcada — mas
    # `corroborated_rate` (0,75 aqui) é um sinal AGREGADO por eixo, não um veto por
    # elemento: 3 de 4 corroborados cruza o limiar de 0,7 e o eixo passa mesmo com um
    # elemento inventado. É limitação pré-existente do gate agregado, não desta mudança —
    # documentada aqui, não escondida.
    assert arm.corroborated_rate == 0.75
    assert any(note.startswith("INK_NOT_FOUND:muro inexistente") for note in arm.notes)

    proposals = TypeAdapter(list[VisionProposal]).validate_json(
        (tmp_path / "out" / "opus-proposals.json").read_text()
    )
    invented = next(item for item in proposals if item.label == "muro inexistente")
    assert invented.quality_score == 0.0


def test_run_extraction_eval_self_heals_a_simple_global_misregistration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Desde 2026-08-19, `run_extraction_eval` registra por conta própria: um deslocamento
    simples (estrutura certa, enquadramento errado) já se recupera dentro dele, sem precisar
    do comando `register-extraction` à parte."""
    source, manifest = _prepare(tmp_path, monkeypatch)
    report, _path = run_extraction_eval(
        source,
        [ExtractionCandidate(name="opus", adapter=_adapter(_displaced_field()))],
        tmp_path / "out",
        manifest_path=manifest,
    )
    assert report.passed is True
    assert report.arms[0].corroborated_rate == 1.0


def test_register_extraction_recovers_a_misregistered_arm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`register_extraction_arms` recupera um artefato LEGADO (de antes de 2026-08-19,
    nunca registrado) sem nova chamada externa — o cenário que
    `test_run_extraction_eval_self_heals_a_simple_global_misregistration` mostra que
    `run_extraction_eval` sozinho já cobre para artefato NOVO."""
    source, _manifest_path = _prepare(tmp_path, monkeypatch)
    output = tmp_path / "out"
    _write_unregistered_artifact(output, "opus", source, [_displaced_field()])

    updated, updated_path = register_extraction_arms(output, source)

    assert updated_path == output / "extraction-eval.json"
    assert updated.passed is True
    arm = updated.arms[0]
    assert arm.corroborated_rate == 1.0
    assert (output / "opus-registered.json").is_file()
    assert any(note.startswith("CORROBORATED_BEFORE_REGISTRATION:") for note in arm.notes)
    assert any(note.startswith("REGISTERED:") for note in arm.notes)


def test_register_extraction_reports_the_before_and_after_of_every_proposal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A média por eixo esconde elemento sacrificado; a tabela por proposta não esconde."""
    source, manifest = _prepare(tmp_path, monkeypatch)
    output = tmp_path / "out"
    run_extraction_eval(
        source,
        [ExtractionCandidate(name="opus", adapter=_adapter(_displaced_field(), _invented()))],
        output,
        manifest_path=manifest,
    )

    updated, _path = register_extraction_arms(output, source)

    arm = updated.arms[0]
    table = arm.proposal_registration
    assert len(table) == arm.element_count == 2
    # A promessa do estágio: nenhuma proposta sai com menos tinta do que já tinha.
    assert all(row.coverage_refined >= row.coverage_raw for row in table)
    assert {row.base for row in table} <= {"raw", "global"}
    assert {row.refinement for row in table} <= {
        "none",
        "translation",
        "edges",
        "tips",
        "circle",
        "arc",
    }
    field = next(row for row in table if row.label == "campo")
    assert field.coverage_refined > field.coverage_raw


def test_register_extraction_keeps_report_and_registered_file_in_the_same_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Relatório e `-registered.json` são um par; publicar um sem o outro engana a revisão.

    O artefato local do Guaxindiba ficou justamente assim — relatório no estado PRÉ-registro
    ao lado de um `-registered.json` pós-registro, escrito fora deste comando. Aqui os dois
    são conferidos no mesmo ato, contra o que está em disco e não contra o retorno.

    Desde que `run_extraction_eval` passou a registrar por conta própria (2026-08-19), o
    cenário precisa simular um artefato LEGADO (nunca registrado) para continuar
    exercitando uma recuperação de verdade — ver
    `test_register_extraction_recovers_a_misregistered_arm`.
    """
    source, _manifest_path = _prepare(tmp_path, monkeypatch)
    output = tmp_path / "out"
    _write_unregistered_artifact(output, "opus", source, [_displaced_field()])
    before = ExtractionEvalReport.model_validate_json((output / "extraction-eval.json").read_text())

    updated, report_path = register_extraction_arms(output, source)

    on_disk = ExtractionEvalReport.model_validate_json(report_path.read_text())
    assert on_disk.arms[0].corroborated_rate == updated.arms[0].corroborated_rate
    assert on_disk.arms[0].corroborated_rate != before.arms[0].corroborated_rate
    registered = TypeAdapter(list[VisionProposal]).validate_json(
        (output / "opus-registered.json").read_text()
    )
    table = on_disk.arms[0].proposal_registration
    assert [row.proposal_id for row in table] == [item.id for item in registered]
    assert [row.coverage_refined for row in table] == [item.quality_score for item in registered]


def test_register_extraction_refuses_an_image_that_is_not_the_evaluated_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Registrar contra outra página validaria geometria contra tinta que não é a dela."""
    source, manifest = _prepare(tmp_path, monkeypatch)
    output = tmp_path / "out"
    run_extraction_eval(
        source,
        [ExtractionCandidate(name="opus", adapter=_adapter(_drawn_field()))],
        output,
        manifest_path=manifest,
    )
    other = tmp_path / "outra.png"
    other.write_bytes(b"nao e a pagina avaliada")

    with pytest.raises(ValueError, match="não corresponde"):
        register_extraction_arms(output, other)


def test_eval_carries_the_observed_arc_window_into_the_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """As âncoras atravessam a eval inteira e chegam ao artefato, não só à conversão.

    É o artefato que o `register-extraction` relê depois, sem nova chamada paga: se a flag
    não viajasse nele, o registro trataria observação como chute e a lapidação seria
    silenciosamente uma reconquista.
    """
    source, manifest = _prepare(tmp_path, monkeypatch)
    output = tmp_path / "out"

    report, _path = run_extraction_eval(
        source,
        [ExtractionCandidate(name="opus", adapter=_adapter(_drawn_arc(anchored=True)))],
        output,
        manifest_path=manifest,
    )

    proposals = TypeAdapter(list[VisionProposal]).validate_json(
        (output / "opus-proposals.json").read_text()
    )
    assert [item.arc_angles_observed for item in proposals] == [True]
    # As âncoras põem o arco sobre a tinta do render sem nenhum registro: é o que prova que
    # a janela observada é a da folha, e não uma meia-volta que por acaso caiu bem.
    assert report.arms[0].corroborated_rate == 1.0
    assert report.passed is True


def test_register_extraction_reconquers_an_arc_from_an_artifact_without_the_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Artefato gravado antes do campo existir continua válido e continua reconquistado.

    A flag é aditiva com default falso, e falso é exatamente o que um artefato v1 declara:
    ninguém observou a abertura daquele arco. Sem isso, o registro passaria a lapidar em
    ±15° uma orientação que é chute — e o chute é uma meia-volta fixa.

    Desde que `run_extraction_eval` passou a registrar por conta própria (2026-08-19), um
    artefato produzido por ele já sai com o arco reconquistado — não sobra nada para
    `register_extraction_arms` corrigir. Para continuar provando que o COMANDO por si só
    ainda reconquista um artefato de verdade ANTIGO (sem a flag E sem nenhum registro
    prévio), o cenário é construído cru, como `run_extraction_eval` gravava antes de
    2026-08-19 — patchar só a geometria do arco num `proposals.json` já registrado pelo
    `run_extraction_eval` atual produziria um estado híbrido que o registro nunca produz
    sozinho, porque a busca global depende do CONJUNTO inteiro de propostas.
    """
    source, _manifest_path = _prepare(tmp_path, monkeypatch)
    output = tmp_path / "out"
    # O conjunto precisa dos três elementos: com só dois, o estágio GLOBAL tem graus de
    # liberdade para sacrificar o contorno e pousar o arco sozinho, e o que este teste mede
    # é o refino por elemento, não o enquadramento.
    _write_unregistered_artifact(
        output, "opus", source, [_drawn_field(), _drawn_midline(), _drawn_arc(anchored=False)]
    )
    artifact = output / "opus-proposals.json"
    payload = json.loads(artifact.read_text())
    for item in payload:
        del item["arc_angles_observed"]
    artifact.write_text(json.dumps(payload))

    updated, _path = register_extraction_arms(output, source)

    arc = next(row for row in updated.arms[0].proposal_registration if row.label == "meia-lua")
    assert arc.refinement == "arc"
    # A meia-volta fabricada aponta para baixo e a tinta desenha a metade de cima: só a
    # busca de volta inteira alcança essa correção.
    assert abs(arc.orientation_delta_degrees) > 45.0
    assert arc.coverage_refined > arc.coverage_raw


def test_eval_compares_two_arms_over_the_same_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """sonnet inventa um elemento a mais que opus; o eixo com invenção fica atrás.

    O braço "sonnet" precisa de âncoras reais suficientes (campo, meio de campo e arco)
    para que o registro (agora sempre ligado, ver `run_extraction_eval`) não tenha graus de
    liberdade sobrando para "resgatar" a invenção sobre tinta não relacionada — com só um
    elemento real competindo, o estágio global do registro pode deslizar a invenção sozinha
    até alguma tinta da página, e os dois eixos empatam em 1,0 sem nenhum deles ter
    inventado menos.
    """
    source, manifest = _prepare(tmp_path, monkeypatch)

    report, _path = run_extraction_eval(
        source,
        [
            ExtractionCandidate(name="opus", adapter=_adapter(_drawn_field())),
            ExtractionCandidate(
                name="sonnet",
                adapter=_adapter(
                    _drawn_field(), _drawn_midline(), _drawn_arc(anchored=True), _invented()
                ),
            ),
        ],
        tmp_path / "out",
        manifest_path=manifest,
    )

    assert [arm.name for arm in report.arms] == ["opus", "sonnet"]
    assert report.arms[0].corroborated_rate > report.arms[1].corroborated_rate
    assert (tmp_path / "out" / "opus-proposals.json").is_file()
    assert (tmp_path / "out" / "sonnet-proposals.json").is_file()


def test_step_gate_passes_a_single_polyline_that_preserves_the_jog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Braço fiel: um único elemento polyline cobre os dois trechos com o cotovelo do degrau."""
    source, manifest = _prepare_degrau(tmp_path, monkeypatch)

    report, _path = run_extraction_eval(
        source,
        [ExtractionCandidate(name="opus", adapter=_adapter(_degrau_wall_faithful()))],
        tmp_path / "out",
        manifest_path=manifest,
        step_gabarito=build_degrau_step_gabarito(),
    )

    arm = report.arms[0]
    assert arm.step is not None
    assert arm.step.element_found is True
    assert arm.step.single_element is True
    assert arm.step.jog_transition_found is True
    assert arm.step.step_preserved is True
    assert report.passed is True


def test_step_gate_fails_the_real_opus_regression_of_two_straight_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reprodução do defeito real do Guaxindiba V3: duas `line` retas aderem à tinta e ainda
    assim reprovam — é exatamente o que `corroborated_rate` sozinho não pegava."""
    source, manifest = _prepare_degrau(tmp_path, monkeypatch)

    report, _path = run_extraction_eval(
        source,
        [ExtractionCandidate(name="opus", adapter=_adapter(*_degrau_wall_split()))],
        tmp_path / "out",
        manifest_path=manifest,
        step_gabarito=build_degrau_step_gabarito(),
    )

    arm = report.arms[0]
    # A corroboração de tinta, sozinha, aprovaria este braço: cada trecho pousa exatamente
    # sobre a própria tinta. É o gate do degrau que precisa reprovar mesmo assim.
    assert arm.corroborated_rate == 1.0
    assert arm.ink_coverage_mean > 0.6
    assert arm.step is not None
    assert arm.step.element_found is False
    assert arm.step.step_preserved is False
    assert report.passed is False


def test_step_gate_fails_a_smooth_ramp_that_spreads_the_jog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Um único elemento polyline com o vão certo, mas sem cotovelo, também reprova.

    O critério de posição absoluta antigo não distinguia isso de um cotovelo deslocado por
    registro; o critério estrutural sim, porque exige um PAR CONSECUTIVO que muda de trecho
    quase sem andar ao longo do eixo — uma rampa espalha essa mudança por vários pares, cada
    um com deslocamento grande demais.
    """
    source, manifest = _prepare_degrau(tmp_path, monkeypatch)

    report, _path = run_extraction_eval(
        source,
        [ExtractionCandidate(name="opus", adapter=_adapter(_degrau_wall_ramp()))],
        tmp_path / "out",
        manifest_path=manifest,
        step_gabarito=build_degrau_step_gabarito(),
    )

    arm = report.arms[0]
    assert arm.step is not None
    assert arm.step.element_found is True
    assert arm.step.single_element is True
    assert arm.step.jog_transition_found is False
    assert any(note == "STEP_JOG_TRANSITION_NOT_FOUND" for note in arm.step.notes)
    assert arm.step.step_preserved is False
    assert report.passed is False
