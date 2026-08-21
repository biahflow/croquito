"""Eval comparativa dos braços de transcrição (F-032, T13).

A decisão de FORNECEDOR foi humana (Groq, 2026-08-21). A decisão de qual braço é primário e
qual é reserva **não** foi tomada e não deve ser tomada por palpite: ela sai da comparação
entre `Groq·whisper-large-v3`, `Groq·whisper-large-v3-turbo` e o braço de transcrição da
OpenAI, medida sobre gravações reais de campo. Este módulo é o instrumento dessa comparação,
e ele existe antes da rodada paga de propósito — um harness escrito depois do resultado tende
a medir o que confirma a escolha já feita.

Ordem de peso das métricas, decidida pelo que estraga o trabalho do escritório:

1. **fidelidade de números e medidas faladas.** É o que a nota de voz carrega de crítico:
   "doze vírgula quarenta" transcrito como "12,4" ou como "doze e quarenta" custa uma
   conferência humana contra o áudio, e transcrito como "12,04" custa uma medida errada. A
   comparação preserva a PRECISÃO ESCRITA (`12,40` ≠ `12,4`), como todo o resto do repositório;
2. **WER/CER em pt-BR.** Qualidade geral do texto, normalizada (caixa, pontuação, espaços);
3. **container.** `webm/opus` (Android) contra `mp4/aac` (iPhone), porque um braço pode ser
   melhor num codec e pior no outro — e o piloto tem os dois aparelhos.

Dois modos, e a diferença entre eles é um ato humano:

- **offline** (`make transcription-eval`, CI): corpus sintético e adapters GRAVADOS. Nenhuma
  chave, nenhuma rede, nenhum centavo. O que ele prova não é qual fornecedor é melhor — é que
  o harness e as métricas funcionam: o gate exige que o braço exato pontue perfeito e que os
  braços com erro INJETADO sejam efetivamente detectados por cada métrica. Uma métrica que
  não distingue não serviria para escolher fornecedor nenhum;
- **pago** (`--live`, com `--corpus`): os mesmos braços reais, sobre clipes gravados pelo
  usuário (10 a 15, Android e iPhone, com a verdade escrita à mão). É ato humano separado —
  exige chaves, teto de gasto e aprovação de custo — e o resultado dele promove primário e
  reserva em `docs/ai/MODEL_ROUTING.md`, pelo mesmo protocolo das evals anteriores.

O relatório carrega SÓ métricas. Nem transcrição, nem trecho, nem verdade de referência: numa
rodada paga os clipes são voz de gente real numa praça real, e um relatório com o texto dentro
seria a evidência vazando pelo artefato de qualidade.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from croquito_worker.io_utils import atomic_write_text
from croquito_worker.providers import (
    AudioTranscriptionOutput,
    PromptTask,
    ProviderAdapter,
    ProviderExecution,
    ProviderExecutionError,
    ProviderFailureCode,
    ProviderName,
    ProviderRequest,
    build_audio_request,
)

SYNTHETIC_CORPUS_ID: Final = "synthetic-transcription-v1"

WEBM: Final = "audio/webm"
MP4: Final = "audio/mp4"

#: Token de medida: número com separador decimal opcional. É deliberadamente CEGO a unidade —
#: o que precisa bater é o número escrito, e a unidade falada varia ("metros", "m", "cm") sem
#: que isso torne a medida errada.
_MEASURE_PATTERN: Final = re.compile(r"\d+(?:[.,]\d+)?")

_WORD_PATTERN: Final = re.compile(r"[0-9a-zà-ÿ]+(?:[.,]\d+)?")


@dataclass(frozen=True, slots=True)
class TranscriptionClip:
    """Um clipe do corpus: o áudio, o container e a transcrição-verdade.

    `audio_bytes` no modo offline é um blob determinístico, não uma gravação: nenhum adapter
    do modo offline decodifica áudio, e versionar som de gente no repositório é justamente o
    que as regras de dados proíbem. No modo pago os bytes vêm do arquivo que o usuário gravou,
    que mora fora do repositório.
    """

    clip_id: str
    device: str
    mime_type: str
    truth_text: str
    audio_bytes: bytes


@dataclass
class RecordedTranscriptionAdapter:
    """Braço GRAVADO: devolve uma resposta fixa por clipe e CONTA as chamadas.

    Implementa `ProviderAdapter` como qualquer braço real, de modo que o modo offline exercite
    o mesmo caminho de request/execução do modo pago. A contagem é o oráculo do teste de que
    nada saiu para a rede: um braço gravado com `calls` diferente do número de clipes denuncia
    o harness antes de ele denunciar um fornecedor.
    """

    provider: ProviderName
    model_id: str
    #: `input_digest` (sha256 do áudio) → texto transcrito gravado.
    responses: Mapping[str, str]
    calls: int = 0

    def execute(self, request: ProviderRequest) -> ProviderExecution:
        self.calls += 1
        recorded = self.responses.get(request.image_sha256)
        if recorded is None:
            # Clipe sem resposta gravada: o braço "não respondeu", e a eval conta isso como
            # falha do braço em vez de fingir uma transcrição vazia.
            raise ProviderExecutionError(ProviderFailureCode.UNAVAILABLE)
        return ProviderExecution(
            provider=self.provider,
            model_id=self.model_id,
            prompt=request.prompt,
            input_digest=request.image_sha256,
            latency_ms=1,
            output=AudioTranscriptionOutput(text=recorded, language="portuguese"),
        )


@dataclass(frozen=True, slots=True)
class TranscriptionArm:
    """Um eixo da comparação: um adapter, um rótulo estável e o modelo que ele fala."""

    arm_id: str
    adapter: ProviderAdapter
    provider: str
    model_id: str


class ContainerMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clips: int = Field(ge=0)
    measure_recall: float = Field(ge=0, le=1)
    wer: float = Field(ge=0)
    cer: float = Field(ge=0)


class ArmMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    arm_id: str
    provider: str
    model_id: str
    calls: int = Field(ge=0)
    clips: int = Field(ge=0)
    failures: int = Field(ge=0)
    measure_recall: float = Field(ge=0, le=1)
    measure_precision: float = Field(ge=0, le=1)
    #: Medidas que o braço acertou em valor mas errou na PRECISÃO ESCRITA (12,4 por 12,40).
    #: Separadas porque a causa e a correção são outras: não é erro de escuta, é formatação.
    written_precision_mismatches: int = Field(ge=0)
    wer: float = Field(ge=0)
    cer: float = Field(ge=0)
    by_container: dict[str, ContainerMetrics]


class TranscriptionEvalReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    corpus_id: str
    mode: Literal["offline-fake", "paid"]
    clip_count: int = Field(ge=0)
    arms: list[ArmMetrics]
    #: Braço que lidera pela ordem de peso declarada. No modo offline ele NÃO promove nada:
    #: promover primário/reserva exige a rodada paga sobre gravações reais.
    leader: str | None
    ranking_criteria: list[str]
    pending_paid_round: bool
    passed: bool
    gate_findings: list[str]


def _normalize(text: str) -> str:
    """Normaliza para WER/CER: caixa, pontuação e espaços — acento PRESERVADO.

    Tirar acento facilitaria a vida do braço que erra acentuação, e em pt-BR isso muda palavra
    ("e"/"é"). O que sai são apenas os separadores e a pontuação de frase; o separador decimal
    dentro de um número sobrevive, porque é ele que distingue 12,40 de 1240.
    """
    lowered = unicodedata.normalize("NFC", text).lower()
    return " ".join(_WORD_PATTERN.findall(lowered))


def _measures(text: str) -> list[str]:
    """Medidas escritas no texto, normalizadas só no separador decimal.

    `12,40` e `12.40` são a mesma medida escrita com a convenção de teclados diferentes;
    `12,4` **não** é a mesma coisa, e é por isso que o valor sai como string e não como
    `Decimal` normalizado: o zero à direita é informação, do mesmo jeito que na cota escrita
    numa prancha.
    """
    found: list[str] = []
    for raw in _MEASURE_PATTERN.findall(text):
        candidate = raw.replace(",", ".")
        try:
            Decimal(candidate)
        except InvalidOperation:  # pragma: no cover - o padrão já garante o formato
            continue
        found.append(candidate)
    return found


def _levenshtein(source: Sequence[str], target: Sequence[str]) -> int:
    """Distância de edição clássica, usada por WER (tokens) e CER (caracteres)."""
    if not source:
        return len(target)
    if not target:
        return len(source)
    previous = list(range(len(target) + 1))
    for source_index, source_item in enumerate(source, start=1):
        current = [source_index]
        for target_index, target_item in enumerate(target, start=1):
            current.append(
                min(
                    previous[target_index] + 1,
                    current[target_index - 1] + 1,
                    previous[target_index - 1] + (source_item != target_item),
                )
            )
        previous = current
    return previous[-1]


@dataclass
class _Tally:
    """Acumulador de um braço (ou de um container dentro dele)."""

    clips: int = 0
    truth_measures: int = 0
    hypothesis_measures: int = 0
    matched_measures: int = 0
    precision_mismatches: int = 0
    truth_words: int = 0
    word_errors: int = 0
    truth_chars: int = 0
    char_errors: int = 0
    failures: int = 0

    def add(self, *, truth: str, hypothesis: str) -> None:
        self.clips += 1
        truth_measures = _measures(truth)
        hypothesis_measures = _measures(hypothesis)
        self.truth_measures += len(truth_measures)
        self.hypothesis_measures += len(hypothesis_measures)
        remaining = list(hypothesis_measures)
        unmatched: list[str] = []
        for measure in truth_measures:
            if measure in remaining:
                remaining.remove(measure)
                self.matched_measures += 1
            else:
                unmatched.append(measure)
        # Segunda passada só sobre o que não bateu exatamente: um número certo escrito com
        # outra precisão é um achado próprio, não um acerto e não um erro qualquer.
        for measure in unmatched:
            same_value = next(
                (candidate for candidate in remaining if Decimal(candidate) == Decimal(measure)),
                None,
            )
            if same_value is not None:
                remaining.remove(same_value)
                self.precision_mismatches += 1
        truth_words = _normalize(truth).split()
        hypothesis_words = _normalize(hypothesis).split()
        self.truth_words += len(truth_words)
        self.word_errors += _levenshtein(truth_words, hypothesis_words)
        truth_chars = _normalize(truth)
        hypothesis_chars = _normalize(hypothesis)
        self.truth_chars += len(truth_chars)
        self.char_errors += _levenshtein(list(truth_chars), list(hypothesis_chars))

    @property
    def measure_recall(self) -> float:
        return 1.0 if not self.truth_measures else self.matched_measures / self.truth_measures

    @property
    def measure_precision(self) -> float:
        if not self.hypothesis_measures:
            return 1.0 if not self.truth_measures else 0.0
        return self.matched_measures / self.hypothesis_measures

    @property
    def wer(self) -> float:
        return 0.0 if not self.truth_words else self.word_errors / self.truth_words

    @property
    def cer(self) -> float:
        return 0.0 if not self.truth_chars else self.char_errors / self.truth_chars


def _drop_written_precision(text: str) -> str:
    """Perturbação gravada: o braço acerta o número e perde o zero à direita (12,40 → 12,4)."""
    return re.sub(r"(\d+,\d*[1-9])0\b", r"\1", text, count=1)


def _lose_first_measure(text: str) -> str:
    """Perturbação gravada: o braço não escuta a medida e declara trecho inaudível."""
    return _MEASURE_PATTERN.sub("inaudível", text, count=1)


def synthetic_corpus() -> tuple[TranscriptionClip, ...]:
    """Corpus sintético: seis notas de voz plausíveis, três por container.

    As frases são inventadas por este repositório e descrevem uma praça sintética — nenhuma
    delas foi dita por ninguém. Os bytes são determinísticos e derivados do `clip_id`: no modo
    offline eles só precisam existir, ter digest estável e viajar pelo mesmo caminho de request
    que uma gravação real percorreria.
    """
    scripts: tuple[tuple[str, str, str], ...] = (
        (
            "clip-android-1",
            WEBM,
            "O muro do fundo tem 12,40 m de comprimento e 1,80 m de altura.",
        ),
        (
            "clip-android-2",
            WEBM,
            "Do poste até a mureta deu 7,05 m; o piso está solto num trecho de 2,30 m.",
        ),
        (
            "clip-android-3",
            WEBM,
            "A quadra mede 25,90 m por 15,20 m e o alambrado é de 4,00 m.",
        ),
        (
            "clip-iphone-1",
            MP4,
            "O banco de concreto tem 1,60 m e está a 3,45 m do canteiro.",
        ),
        (
            "clip-iphone-2",
            MP4,
            "Aqui tem um degrau de 0,18 m que não está no projeto.",
        ),
        (
            "clip-iphone-3",
            MP4,
            "A calçada nova precisa de 18,75 m de meio-fio do lado da rua.",
        ),
    )
    return tuple(
        TranscriptionClip(
            clip_id=clip_id,
            device="android" if mime_type == WEBM else "iphone",
            mime_type=mime_type,
            truth_text=truth,
            audio_bytes=f"croquito-synthetic-audio::{clip_id}".encode() * 8,
        )
        for clip_id, mime_type, truth in scripts
    )


def recorded_arms(corpus: Sequence[TranscriptionClip]) -> tuple[TranscriptionArm, ...]:
    """Os três eixos da comparação, GRAVADOS, com erros injetados de tipos diferentes.

    Cada braço carrega um erro que uma métrica diferente precisa enxergar: o primeiro não erra
    (piso da comparação), o segundo perde precisão escrita sem perder o valor, o terceiro perde
    a medida inteira. Os rótulos são os dos braços reais porque é a mesma comparação que a
    rodada paga vai fazer — mas os NÚMEROS deste modo não dizem nada sobre os fornecedores.
    """
    digests = {
        clip.clip_id: build_audio_request(
            PromptTask.AUDIO_TRANSCRIPTION,
            audio_bytes=clip.audio_bytes,
            audio_mime_type=clip.mime_type,
        ).image_sha256
        for clip in corpus
    }
    exact = {digests[clip.clip_id]: clip.truth_text for clip in corpus}
    precision_loss = {
        digests[clip.clip_id]: _drop_written_precision(clip.truth_text) for clip in corpus
    }
    measure_loss = {digests[clip.clip_id]: _lose_first_measure(clip.truth_text) for clip in corpus}
    return (
        TranscriptionArm(
            arm_id="groq-whisper-large-v3",
            adapter=RecordedTranscriptionAdapter(
                provider=ProviderName.GROQ, model_id="whisper-large-v3", responses=exact
            ),
            provider=ProviderName.GROQ.value,
            model_id="whisper-large-v3",
        ),
        TranscriptionArm(
            arm_id="groq-whisper-large-v3-turbo",
            adapter=RecordedTranscriptionAdapter(
                provider=ProviderName.GROQ,
                model_id="whisper-large-v3-turbo",
                responses=precision_loss,
            ),
            provider=ProviderName.GROQ.value,
            model_id="whisper-large-v3-turbo",
        ),
        TranscriptionArm(
            arm_id="openai-transcription",
            adapter=RecordedTranscriptionAdapter(
                provider=ProviderName.OPENAI, model_id="whisper-1", responses=measure_loss
            ),
            provider=ProviderName.OPENAI.value,
            model_id="whisper-1",
        ),
    )


def _measure_arm(arm: TranscriptionArm, corpus: Sequence[TranscriptionClip]) -> ArmMetrics:
    total = _Tally()
    per_container: dict[str, _Tally] = {}
    for clip in corpus:
        request = build_audio_request(
            PromptTask.AUDIO_TRANSCRIPTION,
            audio_bytes=clip.audio_bytes,
            audio_mime_type=clip.mime_type,
        )
        container = per_container.setdefault(clip.mime_type, _Tally())
        try:
            execution = arm.adapter.execute(request)
        except ProviderExecutionError:
            # Falha de braço é DADO da comparação, não interrupção: um fornecedor que recusa
            # metade dos clipes já disse algo sobre si mesmo.
            total.failures += 1
            container.failures += 1
            continue
        output = execution.output
        hypothesis = output.text if isinstance(output, AudioTranscriptionOutput) else ""
        total.add(truth=clip.truth_text, hypothesis=hypothesis)
        container.add(truth=clip.truth_text, hypothesis=hypothesis)
    calls = getattr(arm.adapter, "calls", len(corpus))
    return ArmMetrics(
        arm_id=arm.arm_id,
        provider=arm.provider,
        model_id=arm.model_id,
        calls=int(calls),
        clips=total.clips,
        failures=total.failures,
        measure_recall=total.measure_recall,
        measure_precision=total.measure_precision,
        written_precision_mismatches=total.precision_mismatches,
        wer=total.wer,
        cer=total.cer,
        by_container={
            mime_type: ContainerMetrics(
                clips=tally.clips,
                measure_recall=tally.measure_recall,
                wer=tally.wer,
                cer=tally.cer,
            )
            for mime_type, tally in sorted(per_container.items())
        },
    )


RANKING_CRITERIA: Final = ("measure_recall", "wer", "cer")
"""Ordem de peso do desempate, e ela não é negociável na leitura do relatório: um braço com
WER menor e fidelidade de medida pior NÃO lidera."""


def _leader(arms: Sequence[ArmMetrics]) -> str | None:
    if not arms:
        return None
    ranked = sorted(arms, key=lambda arm: (-arm.measure_recall, arm.wer, arm.cer, arm.arm_id))
    return ranked[0].arm_id


def _offline_gate(arms: Sequence[ArmMetrics], *, clip_count: int) -> list[str]:
    """Gate do modo offline: o harness precisa provar que as métricas DISCRIMINAM.

    Não há nada de fornecedor a aprovar aqui — as respostas são gravadas. O que se verifica é
    que o braço exato pontua perfeito, que cada erro injetado é detectado pela métrica que
    deveria detectá-lo, e que cada braço foi chamado uma vez por clipe.
    """
    findings: list[str] = []
    by_id = {arm.arm_id: arm for arm in arms}
    exact = by_id.get("groq-whisper-large-v3")
    precision = by_id.get("groq-whisper-large-v3-turbo")
    lost = by_id.get("openai-transcription")
    if exact is None or precision is None or lost is None:
        return ["ARMS_MISSING"]
    for arm in arms:
        if arm.calls != clip_count or arm.clips != clip_count or arm.failures:
            findings.append(f"ARM_CALLS_MISMATCH:{arm.arm_id}")
        if len(arm.by_container) != 2:
            findings.append(f"ARM_CONTAINER_COVERAGE:{arm.arm_id}")
    if exact.measure_recall != 1.0 or exact.wer != 0.0 or exact.cer != 0.0:
        findings.append("EXACT_ARM_NOT_PERFECT")
    if precision.measure_recall >= 1.0:
        findings.append("PRECISION_LOSS_UNDETECTED")
    if precision.written_precision_mismatches == 0:
        findings.append("PRECISION_MISMATCH_UNCOUNTED")
    if lost.measure_recall >= precision.measure_recall:
        findings.append("MEASURE_LOSS_NOT_WORSE")
    if lost.wer <= 0.0:
        findings.append("MEASURE_LOSS_WER_UNDETECTED")
    if _leader(arms) != exact.arm_id:
        findings.append("LEADER_NOT_EXACT_ARM")
    return findings


def run_transcription_eval(
    output_dir: Path,
    *,
    corpus: Sequence[TranscriptionClip] | None = None,
    arms: Sequence[TranscriptionArm] | None = None,
    mode: Literal["offline-fake", "paid"] = "offline-fake",
    corpus_id: str = SYNTHETIC_CORPUS_ID,
) -> tuple[TranscriptionEvalReport, Path]:
    """Roda a comparação e grava o relatório. Sem argumentos, é o modo offline determinístico."""
    output_dir.mkdir(parents=True, exist_ok=True)
    clips = tuple(corpus) if corpus is not None else synthetic_corpus()
    axes = tuple(arms) if arms is not None else recorded_arms(clips)
    measured = [_measure_arm(arm, clips) for arm in axes]
    findings = _offline_gate(measured, clip_count=len(clips)) if mode == "offline-fake" else []
    report = TranscriptionEvalReport(
        corpus_id=corpus_id,
        mode=mode,
        clip_count=len(clips),
        arms=measured,
        leader=_leader(measured),
        ranking_criteria=list(RANKING_CRITERIA),
        # A promoção de primário/reserva continua PENDENTE enquanto a rodada paga não
        # acontecer; o modo offline nunca pode marcar esta bandeira como resolvida.
        pending_paid_round=mode != "paid",
        passed=not findings,
        gate_findings=findings,
    )
    report_path = output_dir / "transcription-eval.json"
    serialized: str = json.dumps(
        report.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True
    )
    atomic_write_text(report_path, f"{serialized}\n")
    return report, report_path


def load_corpus(manifest_path: Path) -> tuple[TranscriptionClip, ...]:
    """Carrega o corpus da rodada paga a partir de um manifesto local.

    O manifesto e os áudios moram FORA do repositório (regras de dados: gravação de gente não
    é fixture versionada). Formato:

    ```json
    {"corpus_id": "campo-2026-08", "clips": [
      {"clip_id": "c1", "device": "android", "mime_type": "audio/webm",
       "audio_path": "clips/c1.webm", "truth_text": "..."}
    ]}
    ```

    `audio_path` é relativo ao diretório do manifesto.
    """
    document: Any = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(document, Mapping):
        raise ValueError("manifesto de corpus inválido: objeto esperado na raiz")
    entries = document.get("clips")
    if not isinstance(entries, list) or not entries:
        raise ValueError("manifesto de corpus sem clipes")
    base = manifest_path.parent
    clips: list[TranscriptionClip] = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            raise ValueError("clipe de corpus inválido")
        mime_type = str(entry["mime_type"])
        if mime_type not in {WEBM, MP4}:
            raise ValueError(f"container não suportado no corpus: {mime_type}")
        audio_path = base / str(entry["audio_path"])
        clips.append(
            TranscriptionClip(
                clip_id=str(entry["clip_id"]),
                device=str(entry.get("device", "unknown")),
                mime_type=mime_type,
                truth_text=str(entry["truth_text"]),
                audio_bytes=audio_path.read_bytes(),
            )
        )
    return tuple(clips)


@dataclass(frozen=True, slots=True)
class LiveArmSpec:
    """Um eixo da rodada PAGA: fornecedor e modelo, nomeados explicitamente."""

    arm_id: str
    vendor: str
    model_id: str


DEFAULT_LIVE_ARMS: Final[tuple[LiveArmSpec, ...]] = (
    LiveArmSpec("groq-whisper-large-v3", ProviderName.GROQ.value, "whisper-large-v3"),
    LiveArmSpec("groq-whisper-large-v3-turbo", ProviderName.GROQ.value, "whisper-large-v3-turbo"),
    LiveArmSpec("openai-transcription", ProviderName.OPENAI.value, "whisper-1"),
)
"""Os três eixos da comparação decidida com o usuário em 2026-08-21."""


def build_live_arms(
    specs: Sequence[LiveArmSpec] = DEFAULT_LIVE_ARMS,
) -> tuple[TranscriptionArm, ...]:
    """Monta os braços REAIS da rodada paga, sob o teto de gasto declarado no ambiente.

    Recusa limpa e antecipada: sem `CROQUITO_AI_MAX_ESTIMATED_COST_USD` válido ou sem a chave
    do fornecedor de um eixo, levanta antes de qualquer chamada. Nenhum teste deste repositório
    chega aqui — a rodada paga é ato humano, com aprovação de custo.
    """
    import os

    from croquito_worker.providers import (
        DEFAULT_TRANSCRIPTION_CALL_COST_USD,
        TRANSCRIPTION_CALL_COST_ENV,
        CostBudget,
        build_transcription_arm,
    )

    try:
        budget = CostBudget(Decimal(os.environ["CROQUITO_AI_MAX_ESTIMATED_COST_USD"]))
        call_cost = Decimal(
            os.getenv(TRANSCRIPTION_CALL_COST_ENV, DEFAULT_TRANSCRIPTION_CALL_COST_USD)
        )
    except (KeyError, ArithmeticError) as error:
        raise ValueError("Budget de IA explícito e válido é obrigatório") from error
    if budget.limit_usd <= 0 or call_cost < 0:
        raise ValueError("Budget e estimativas de IA devem ser positivos")
    built: list[TranscriptionArm] = []
    for spec in specs:
        adapter = build_transcription_arm(
            spec.vendor,
            budget=budget,
            estimated_cost_usd=call_cost,
            model_id=spec.model_id,
        )
        if adapter is None:
            raise ValueError(f"chave ausente para o eixo {spec.arm_id} ({spec.vendor})")
        built.append(
            TranscriptionArm(
                arm_id=spec.arm_id,
                adapter=adapter,
                provider=spec.vendor,
                model_id=spec.model_id,
            )
        )
    return tuple(built)


__all__ = [
    "DEFAULT_LIVE_ARMS",
    "RANKING_CRITERIA",
    "SYNTHETIC_CORPUS_ID",
    "ArmMetrics",
    "ContainerMetrics",
    "LiveArmSpec",
    "RecordedTranscriptionAdapter",
    "TranscriptionArm",
    "TranscriptionClip",
    "TranscriptionEvalReport",
    "build_live_arms",
    "load_corpus",
    "recorded_arms",
    "run_transcription_eval",
    "synthetic_corpus",
]
