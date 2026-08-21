"""Harness da eval comparativa de transcrição (F-032, T13).

A eval é o instrumento que vai escolher primário e reserva entre `Groq·whisper-large-v3`,
`Groq·whisper-large-v3-turbo` e o braço de transcrição da OpenAI. Estes testes não medem
fornecedor nenhum — todos os braços aqui são GRAVADOS. O que eles protegem é o instrumento:

- **as métricas discriminam**: erro de precisão escrita, medida perdida e medida trocada
  produzem números diferentes, cada um pela métrica que deveria enxergá-lo. Uma métrica que
  não distingue não serviria para escolher fornecedor;
- **a ordem de peso vale**: fidelidade de medida manda; WER menor não promove um braço que
  perdeu número;
- **nada sai da máquina**: os braços contam chamadas, e a contagem é o oráculo;
- **o relatório não carrega texto**: numa rodada paga os clipes são voz de gente real, e o
  artefato de qualidade não pode ser por onde a evidência vaza.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

from croquito_worker.providers import (
    PromptTask,
    ProviderName,
    build_audio_request,
)
from croquito_worker.transcription_eval import (
    RecordedTranscriptionAdapter,
    TranscriptionArm,
    TranscriptionClip,
    recorded_arms,
    run_transcription_eval,
    synthetic_corpus,
)

WEBM = "audio/webm"
MP4 = "audio/mp4"


def _clip(clip_id: str, truth: str, mime_type: str = WEBM) -> TranscriptionClip:
    return TranscriptionClip(
        clip_id=clip_id,
        device="android" if mime_type == WEBM else "iphone",
        mime_type=mime_type,
        truth_text=truth,
        audio_bytes=f"sintetico::{clip_id}".encode(),
    )


def _digest(clip: TranscriptionClip) -> str:
    return build_audio_request(
        PromptTask.AUDIO_TRANSCRIPTION,
        audio_bytes=clip.audio_bytes,
        audio_mime_type=clip.mime_type,
    ).image_sha256


def _arm(arm_id: str, clips: list[TranscriptionClip], hypotheses: list[str]) -> TranscriptionArm:
    return TranscriptionArm(
        arm_id=arm_id,
        adapter=RecordedTranscriptionAdapter(
            provider=ProviderName.GROQ,
            model_id="gravado",
            responses={
                _digest(clip): hypothesis
                for clip, hypothesis in zip(clips, hypotheses, strict=True)
            },
        ),
        provider=ProviderName.GROQ.value,
        model_id="gravado",
    )


def _metrics(report: Any, arm_id: str) -> Any:
    return next(arm for arm in report.arms if arm.arm_id == arm_id)


def test_a_eval_offline_passa_e_elege_o_braco_exato(tmp_path: Path) -> None:
    """Gate do CI: o braço sem erro pontua perfeito e os erros injetados são detectados."""
    report, path = run_transcription_eval(tmp_path)

    assert report.passed is True
    assert report.gate_findings == []
    assert report.mode == "offline-fake"
    assert report.leader == "groq-whisper-large-v3"
    assert report.clip_count == len(synthetic_corpus())
    assert report.ranking_criteria == ["measure_recall", "wer", "cer"]
    # O modo offline NUNCA resolve a pendência: promover exige a rodada paga.
    assert report.pending_paid_round is True
    assert json.loads(path.read_text(encoding="utf-8"))["leader"] == "groq-whisper-large-v3"


def test_cada_braco_gravado_e_chamado_uma_vez_por_clipe(tmp_path: Path) -> None:
    """A contagem é o oráculo de que a eval offline não fala com fornecedor nenhum."""
    corpus = synthetic_corpus()
    arms = recorded_arms(corpus)

    report, _ = run_transcription_eval(tmp_path, corpus=corpus, arms=arms)

    for arm in arms:
        adapter = cast(RecordedTranscriptionAdapter, arm.adapter)
        assert adapter.calls == len(corpus)
    assert all(metrics.failures == 0 for metrics in report.arms)


def test_o_relatorio_nao_carrega_transcricao_nem_verdade(tmp_path: Path) -> None:
    """Métricas e mais nada: o relatório de qualidade não é por onde a voz vaza."""
    corpus = synthetic_corpus()

    _, path = run_transcription_eval(tmp_path, corpus=corpus)

    serialized = path.read_text(encoding="utf-8")
    for clip in corpus:
        assert clip.truth_text not in serialized
        # Nem em pedaços: nenhuma frase do corpus aparece no artefato.
        assert clip.truth_text.split(" ", 3)[-1] not in serialized


def test_precisao_escrita_perdida_derruba_a_fidelidade_sem_virar_erro_de_escuta(
    tmp_path: Path,
) -> None:
    """`12,4` por `12,40` é o mesmo valor com outra precisão — e o repositório separa os dois."""
    clips = [_clip("c1", "O muro tem 12,40 m.")]

    report, _ = run_transcription_eval(
        tmp_path,
        corpus=clips,
        arms=[
            _arm("exato", clips, ["O muro tem 12,40 m."]),
            _arm("precisao", clips, ["O muro tem 12,4 m."]),
        ],
        mode="paid",
    )

    exato = _metrics(report, "exato")
    precisao = _metrics(report, "precisao")
    assert (exato.measure_recall, exato.written_precision_mismatches) == (1.0, 0)
    assert (precisao.measure_recall, precisao.written_precision_mismatches) == (0.0, 1)
    assert report.leader == "exato"


def test_separador_decimal_de_teclado_diferente_nao_e_erro(tmp_path: Path) -> None:
    """`12.40` e `12,40` são a mesma medida escrita; a normalização é só do separador."""
    clips = [_clip("c1", "O muro tem 12,40 m.")]

    report, _ = run_transcription_eval(
        tmp_path, corpus=clips, arms=[_arm("ponto", clips, ["O muro tem 12.40 m."])], mode="paid"
    )

    assert _metrics(report, "ponto").measure_recall == 1.0


def test_medida_inventada_derruba_a_precisao_sem_derrubar_o_recall(tmp_path: Path) -> None:
    """Número que ninguém falou é o erro mais caro; ele precisa aparecer em `precision`."""
    clips = [_clip("c1", "O muro tem 12,40 m.")]

    report, _ = run_transcription_eval(
        tmp_path,
        corpus=clips,
        arms=[_arm("inventor", clips, ["O muro tem 12,40 m e 3,00 m."])],
        mode="paid",
    )

    inventor = _metrics(report, "inventor")
    assert inventor.measure_recall == 1.0
    assert inventor.measure_precision == 0.5


def test_a_fidelidade_de_medida_manda_sobre_o_wer(tmp_path: Path) -> None:
    """Um braço com texto quase perfeito e número errado NÃO lidera sobre um número certo."""
    clips = [_clip("c1", "O muro do fundo tem 12,40 m de comprimento total.")]

    report, _ = run_transcription_eval(
        tmp_path,
        corpus=clips,
        arms=[
            # Erra duas palavras, acerta o número.
            _arm("numero-certo", clips, ["O muro de fundos tem 12,40 m de comprimento total."]),
            # Acerta todas as palavras menos o número.
            _arm("numero-errado", clips, ["O muro do fundo tem 12,04 m de comprimento total."]),
        ],
        mode="paid",
    )

    certo = _metrics(report, "numero-certo")
    errado = _metrics(report, "numero-errado")
    assert certo.wer > errado.wer
    assert certo.measure_recall > errado.measure_recall
    assert report.leader == "numero-certo"


def test_o_relatorio_separa_os_dois_containers_do_piloto(tmp_path: Path) -> None:
    """Android e iPhone gravam codecs diferentes; um braço pode ser bom num e ruim no outro."""
    clips = [_clip("android", "Tem 12,40 m.", WEBM), _clip("iphone", "Tem 7,05 m.", MP4)]

    report, _ = run_transcription_eval(
        tmp_path,
        corpus=clips,
        arms=[_arm("desigual", clips, ["Tem 12,40 m.", "Tem sete metros."])],
        mode="paid",
    )

    por_container = _metrics(report, "desigual").by_container
    assert por_container[WEBM].measure_recall == 1.0
    assert por_container[MP4].measure_recall == 0.0
    assert (por_container[WEBM].clips, por_container[MP4].clips) == (1, 1)


def test_braco_que_nao_responde_conta_como_falha_e_nao_como_acerto(tmp_path: Path) -> None:
    """Fornecedor que recusa metade dos clipes já disse algo sobre si; a eval registra."""
    clips = [_clip("c1", "Tem 12,40 m."), _clip("c2", "Tem 7,05 m.")]
    arm = TranscriptionArm(
        arm_id="mudo",
        adapter=RecordedTranscriptionAdapter(
            provider=ProviderName.GROQ,
            model_id="gravado",
            responses={_digest(clips[0]): "Tem 12,40 m."},
        ),
        provider=ProviderName.GROQ.value,
        model_id="gravado",
    )

    report, _ = run_transcription_eval(tmp_path, corpus=clips, arms=[arm], mode="paid")

    mudo = _metrics(report, "mudo")
    assert (mudo.calls, mudo.clips, mudo.failures) == (2, 1, 1)


def test_transcricao_vazia_nao_e_contada_como_medida_certa(tmp_path: Path) -> None:
    """Silêncio é resposta legítima do provider, mas não é acerto de medida."""
    clips = [_clip("c1", "Tem 12,40 m.")]

    report, _ = run_transcription_eval(
        tmp_path, corpus=clips, arms=[_arm("silencio", clips, [""])], mode="paid"
    )

    silencio = _metrics(report, "silencio")
    assert silencio.measure_recall == 0.0
    assert silencio.wer == 1.0


def test_a_rodada_paga_sem_corpus_e_recusada_pela_linha_de_comando(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Gastar dinheiro para produzir texto que ninguém pode conferir é recusa, não default."""
    from croquito_worker.cli import main

    monkeypatch.setattr(
        "sys.argv",
        ["croquito-demo", "transcription-eval", "--output", str(tmp_path), "--live"],
    )

    assert main() == 2

    assert json.loads(capsys.readouterr().out)["refused"] == "LIVE_REQUIRES_CORPUS"
    assert list(tmp_path.iterdir()) == []
