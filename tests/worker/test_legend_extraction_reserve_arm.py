"""Braço de RESERVA da extração de legenda: desligado por padrão, nomeado quando degrada.

O oráculo central deste arquivo é o do padrão: **sem a variável de ambiente, nada muda**.
O pacote sai com exatamente as três notas de sempre, na ordem de sempre, e a falha do braço
escolhido propaga como sempre propagou — sem nota de degradação, porque não houve troca de
braço para registrar.

Quando a reserva existe, a regra é a mesma do caminho do croqui
(`provider_review._execute_with_fallback`), copiada de propósito para as duas jornadas não
divergirem: falha permanente degrada, `BUDGET_EXCEEDED` não (o teto é do job, e a segunda
chamada consumiria o mesmo teto sem chance de sucesso), e quem respondeu no lugar do braço
escolhido fica NOMEADO numa nota de segurança do pacote — degradação silenciosa faria a
revisão ler o takeoff como se o braço homologado tivesse lido a prancha.

Nada aqui sai da máquina: os dois braços são fixtures, e o gate de forma do braço de
reserva é exercido com a fábrica real, que recusa antes de qualquer chamada.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from PIL import Image

from croquito_valuation.errors import ValuationValidationError
from croquito_worker.providers import (
    FixtureProviderAdapter,
    LegendExtractionOutput,
    LegendRowOutput,
    NormalizedBox,
    PromptTask,
    ProviderExecution,
    ProviderExecutionError,
    ProviderFailureCode,
    ProviderName,
    ProviderRequest,
)
from croquito_worker.valuation.legend_extraction import (
    LEGEND_EXTRACTION_SAFETY_NOTES,
    LegendExtractionResult,
    build_legend_request,
    execute_legend_request,
    legend_fallback_note,
    run_legend_extraction,
)
from croquito_worker.valuation.round_extraction import (
    EXTRACTION_RESERVE_ARM_ENV,
    build_extraction_reserve_adapter,
    extraction_reserve_arm_spec,
)

ALLOWLIST = "CROQUITO_AI_EXTRACTION_ALLOWED_DIGESTS"

_PLATE_ID = "prancha-de-reserva-01"
_IMAGE_WIDTH = 400
_IMAGE_HEIGHT = 200
_DOCUMENT_DIGEST = "d" * 64

_PRIMARY_MODEL_ID = "fixture-legend-primario-v1"
_RESERVE_MODEL_ID = "fixture-legend-reserva-v1"

_RESERVE_NOTE = "PROVIDER_FALLBACK_LEGEND_EXTRACTION_OPENAI"
"""A nota que este arquivo inteiro existe para prender: ela nomeia o PROVIDER que
respondeu, não o que foi escolhido."""


# --------------------------------------------------------------------------------------
# Fixtures offline: dois braços de provider e a prancha mínima que o gate exige
# --------------------------------------------------------------------------------------


def _legend_output() -> LegendExtractionOutput:
    """Transcrição fabricada de uma linha legível; nenhuma prancha de cliente é lida."""
    return LegendExtractionOutput(
        rows=[
            LegendRowOutput(
                raw_text="PISO INTERTRAVADO SINTETICO 61,20 M2",
                label="PISO INTERTRAVADO SINTETICO",
                quantity_text="61,20",
                unit_text="M2",
                bbox=NormalizedBox(left=0.1, top=0.2, right=0.9, bottom=0.4),
                legibility="clear",
            )
        ]
    )


@dataclass
class _CountingAdapter:
    """Braço fixture que CONTA execuções: é a contagem que prova quem foi chamado."""

    inner: FixtureProviderAdapter
    calls: list[str] = field(default_factory=list)

    def execute(self, request: ProviderRequest) -> ProviderExecution:
        self.calls.append(request.task.value)
        return self.inner.execute(request)


@dataclass
class _FailingAdapter:
    """Braço que falha em definitivo; a contagem prova que ele chegou a ser tentado."""

    code: ProviderFailureCode = ProviderFailureCode.TIMEOUT
    calls: list[str] = field(default_factory=list)

    def execute(self, request: ProviderRequest) -> ProviderExecution:
        self.calls.append(request.task.value)
        raise ProviderExecutionError(self.code)


def _adapter(provider: ProviderName, model_id: str) -> _CountingAdapter:
    return _CountingAdapter(
        inner=FixtureProviderAdapter(
            provider=provider,
            model_id=model_id,
            outputs={PromptTask.LEGEND_EXTRACTION: _legend_output()},
        )
    )


def _primary() -> _CountingAdapter:
    return _adapter(ProviderName.ANTHROPIC, _PRIMARY_MODEL_ID)


def _reserve() -> _CountingAdapter:
    """Reserva num provider DIFERENTE do primário: é o que torna a nota verificável."""
    return _adapter(ProviderName.OPENAI, _RESERVE_MODEL_ID)


@pytest.fixture
def plate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """PNG sintético mais o manifest e a allowlist que o gate de consentimento exige."""
    image = tmp_path / "prancha.png"
    Image.new("RGB", (_IMAGE_WIDTH, _IMAGE_HEIGHT), "white").save(image, format="PNG")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "source_sha256": _DOCUMENT_DIGEST,
                "pages": [{"image_sha256": hashlib.sha256(image.read_bytes()).hexdigest()}],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(ALLOWLIST, _DOCUMENT_DIGEST)
    return image, manifest


def _run(
    plate: tuple[Path, Path],
    adapter: _CountingAdapter | _FailingAdapter,
    reserve: _CountingAdapter | _FailingAdapter | None = None,
) -> LegendExtractionResult:
    image, manifest = plate
    return run_legend_extraction(
        image, manifest, adapter, plate_id=_PLATE_ID, page_number=1, reserve=reserve
    )


# --------------------------------------------------------------------------------------
# Reserva desligada: o padrão, e o teste que mais importa
# --------------------------------------------------------------------------------------


def test_sem_reserva_o_pacote_traz_exatamente_as_notas_de_sempre(
    plate: tuple[Path, Path],
) -> None:
    """O padrão não muda um byte do pacote: as três notas fixas, na ordem em que sempre saíram."""
    result = _run(plate, _primary())

    assert result.packet.safety_notes == list(LEGEND_EXTRACTION_SAFETY_NOTES)
    assert len(result.packet.safety_notes) == 3
    assert not any(note.startswith("PROVIDER_FALLBACK") for note in result.packet.safety_notes)


def test_sem_reserva_a_falha_do_primario_propaga_sem_nenhuma_nota(
    plate: tuple[Path, Path],
) -> None:
    """Reserva desligada é o estado de antes desta mudança: a recusa continua fechada."""
    primary = _FailingAdapter()

    with pytest.raises(ProviderExecutionError) as raised:
        _run(plate, primary)

    assert raised.value.code is ProviderFailureCode.TIMEOUT
    assert primary.calls == [PromptTask.LEGEND_EXTRACTION.value]


def test_a_variavel_ausente_ou_vazia_significa_reserva_nenhuma(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(EXTRACTION_RESERVE_ARM_ENV, raising=False)
    assert extraction_reserve_arm_spec() is None
    assert build_extraction_reserve_adapter() is None

    monkeypatch.setenv(EXTRACTION_RESERVE_ARM_ENV, "   ")
    assert extraction_reserve_arm_spec() is None
    assert build_extraction_reserve_adapter() is None


# --------------------------------------------------------------------------------------
# Reserva ligada: degrada, nomeia quem respondeu, e não degrada quando não deve
# --------------------------------------------------------------------------------------


def test_a_reserva_responde_e_o_pacote_nomeia_o_provider_que_de_fato_leu(
    plate: tuple[Path, Path],
) -> None:
    """Degradação declarada: nota com o provider da reserva e `extractor` do mesmo braço."""
    primary = _FailingAdapter(code=ProviderFailureCode.UNAVAILABLE)
    reserve = _reserve()

    result = _run(plate, primary, reserve)

    assert primary.calls == [PromptTask.LEGEND_EXTRACTION.value]
    assert reserve.calls == [PromptTask.LEGEND_EXTRACTION.value]
    assert result.packet.safety_notes == [*LEGEND_EXTRACTION_SAFETY_NOTES, _RESERVE_NOTE]
    # Quem responde é quem assina: `extractor` e lineage saem do braço que leu a prancha.
    assert result.packet.items[0].extractor == f"openai:{_RESERVE_MODEL_ID}"
    assert result.execution.provider is ProviderName.OPENAI
    assert result.execution.model_id == _RESERVE_MODEL_ID


def test_o_primario_bem_sucedido_nunca_encosta_na_reserva(plate: tuple[Path, Path]) -> None:
    primary = _primary()
    reserve = _reserve()

    result = _run(plate, primary, reserve)

    assert primary.calls == [PromptTask.LEGEND_EXTRACTION.value]
    assert reserve.calls == []
    assert result.packet.safety_notes == list(LEGEND_EXTRACTION_SAFETY_NOTES)
    assert result.packet.items[0].extractor == f"anthropic:{_PRIMARY_MODEL_ID}"


def test_teto_de_gasto_estourado_nao_gasta_o_mesmo_teto_na_reserva(
    plate: tuple[Path, Path],
) -> None:
    """`BUDGET_EXCEEDED` não descreve o braço: descreve o teto do job, que a reserva divide."""
    primary = _FailingAdapter(code=ProviderFailureCode.BUDGET_EXCEEDED)
    reserve = _reserve()

    with pytest.raises(ProviderExecutionError) as raised:
        _run(plate, primary, reserve)

    assert raised.value.code is ProviderFailureCode.BUDGET_EXCEEDED
    assert reserve.calls == []


def test_com_os_dois_bracos_no_chao_quem_propaga_e_a_falha_da_reserva(
    plate: tuple[Path, Path],
) -> None:
    """A última tentativa é a que descreve o desfecho; nenhum pacote nasce."""
    primary = _FailingAdapter(code=ProviderFailureCode.TIMEOUT)
    reserve = _FailingAdapter(code=ProviderFailureCode.REFUSED)

    with pytest.raises(ProviderExecutionError) as raised:
        _run(plate, primary, reserve)

    assert raised.value.code is ProviderFailureCode.REFUSED
    assert primary.calls == [PromptTask.LEGEND_EXTRACTION.value]
    assert reserve.calls == [PromptTask.LEGEND_EXTRACTION.value]


@pytest.mark.parametrize(
    ("provider", "expected"),
    [
        (ProviderName.OPENAI, "PROVIDER_FALLBACK_LEGEND_EXTRACTION_OPENAI"),
        (ProviderName.ANTHROPIC, "PROVIDER_FALLBACK_LEGEND_EXTRACTION_ANTHROPIC"),
        (ProviderName.GEMINI, "PROVIDER_FALLBACK_LEGEND_EXTRACTION_GEMINI"),
    ],
)
def test_a_nota_nomeia_o_provider_em_maiusculas(provider: ProviderName, expected: str) -> None:
    assert legend_fallback_note(provider) == expected


def test_o_helper_devolve_lista_vazia_de_notas_quando_ninguem_degradou(
    plate: tuple[Path, Path],
) -> None:
    """Contrato do helper compartilhado, exercido sem passar pelo gate de consentimento."""
    image, _manifest = plate
    request, _width, _height = build_legend_request(image)

    execution, notes = execute_legend_request(request, _primary(), _reserve())

    assert notes == ()
    assert execution.provider is ProviderName.ANTHROPIC


# --------------------------------------------------------------------------------------
# Braço de reserva mal declarado: recusa antes de qualquer chamada
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "arm_spec",
    [
        "lixo",
        "luna=",
        "=openai:gpt-5.6-luna",
        "luna=openai",
        "luna=:gpt-5.6-luna",
    ],
)
def test_reserva_com_forma_invalida_recusa_em_vez_de_ser_ignorada(
    arm_spec: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reserva mal escrita e descartada em silêncio é pior que reserva nenhuma."""
    monkeypatch.setenv(EXTRACTION_RESERVE_ARM_ENV, arm_spec)

    with pytest.raises(ValuationValidationError) as raised:
        build_extraction_reserve_adapter()

    assert raised.value.code == "LOCAL_EXTRACTION_ARM_INVALID"


def test_reserva_fixture_e_recusada_como_o_braco_primario(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Observação fabricada não vira pacote de rodada — nem pela porta da reserva."""
    monkeypatch.setenv(EXTRACTION_RESERVE_ARM_ENV, "falso=fixture:qualquer")

    with pytest.raises(ValuationValidationError) as raised:
        build_extraction_reserve_adapter()

    assert raised.value.code == "LOCAL_EXTRACTION_ARM_FIXTURE_FORBIDDEN"


@pytest.mark.parametrize(
    ("arm_spec", "code"),
    [
        ("lixo", "LOCAL_EXTRACTION_ARM_INVALID"),
        ("falso=fixture:qualquer", "LOCAL_EXTRACTION_ARM_FIXTURE_FORBIDDEN"),
    ],
)
def test_a_recusa_da_reserva_diz_que_o_braco_errado_e_a_reserva(
    arm_spec: str, code: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sem o papel no erro, o operador depura o braço primário, que está são.

    `build_extraction_adapter` levanta os mesmos códigos para os dois papéis, e uma
    reserva inconstruível derruba a extração inteira — inclusive quando o primário
    funcionaria. Quem lê o erro precisa saber, sem consultar memória, qual dos dois braços
    está mal configurado e qual variável mexer.
    """
    monkeypatch.setenv(EXTRACTION_RESERVE_ARM_ENV, arm_spec)

    with pytest.raises(ValuationValidationError) as raised:
        build_extraction_reserve_adapter()

    assert raised.value.code == code
    assert raised.value.details["role"] == "reserva"
    assert raised.value.details["env"] == EXTRACTION_RESERVE_ARM_ENV
    assert raised.value.details["arm"] == arm_spec
