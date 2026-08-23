"""Análise de foto de levantamento de campo (F-032, T14): qualidade sempre, leitura talvez.

A foto que o técnico tirou na praça chega aqui depois do `confirm` da mídia (T8) e produz um
ARTEFATO DE ANÁLISE, nunca uma alteração no levantamento. São duas camadas independentes:

- **passe offline, sempre**: nitidez (variância do Laplaciano), exposição (frações de pixel
  estourado e esmagado) e dimensões. É determinístico, não sai da máquina e não custa nada;
  são as mesmas noções da checagem no aparelho (T15), aplicadas de novo do lado do servidor
  porque a foto pode ter vindo de um aparelho que não as rodou;
- **passe pago, condicional**: leitura por provider de visão do que está ESCRITO na foto —
  placa, bilhete a mão, visor de trena. Só acontece com o caminho pago habilitado E
  entitlement contratual ativo do tenant; sem isso o passe é PULADO e registrado como tal,
  nunca um erro.

Três coisas que este módulo deliberadamente **não** faz:

1. não roda o detector de pranchas (`vision.py`): Hough e contorno adaptativo foram
   calibrados para tinta sobre papel, e o que eles encontram numa foto de praça é sombra de
   grade e junta de piso. Proposta ruim não é proposta barata: ela chega ao revisor com a
   mesma aparência de uma boa;
2. não produz geometria nem coordenada. A leitura de foto não tem `bbox`
   (`FieldPhotoReadingOutput` explica por quê) e nada daqui vira `Entity` ou `Measurement`;
3. não toca `survey_records`, `survey_media_records` nem o pacote consolidado. Toda leitura
   é RASCUNHO a revisar; confirmação continua sendo ato humano no escritório.

O artefato mora em `tenants/{tenant}/surveys/{survey}/analysis/{sha256}.json`, chave estável
derivada do digest da mídia: reprocessar a mesma mensagem sobrescreve o mesmo objeto, como no
export do levantamento (T11), em vez de acumular versões de uma análise da mesma foto.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final

import cv2
import numpy as np

from croquito_worker.providers import (
    FieldPhotoReadingsOutput,
    PromptTask,
    ProviderAdapter,
    ProviderExecution,
    ProviderExecutionError,
    ProviderFailureCode,
    build_request,
)
from croquito_worker.survey_export import SURVEY_MEDIA_CONFIRMED

ANALYSIS_SCHEMA: Final = "survey-photo-analysis/1"
"""Identidade do artefato gravado. Consumidor novo lê isto antes de qualquer campo."""

IMAGE_MIME_PREFIX: Final = "image/"
FIELD_EVIDENCE_READING_SCHEMA: Final = "field-evidence-reading/1"

# --- Limiares da qualidade offline ---------------------------------------------------
#
# São HEURÍSTICAS de triagem, não regra de negócio: nada aqui reprova foto, apaga mídia ou
# bloqueia levantamento — o resultado é um achado no artefato, para o escritório decidir se
# pede outra foto. Os valores vêm da literatura usual de detecção de desfoque e da faixa de
# 8 bits; calibrá-los contra fotos reais de campo é trabalho de eval futura, e mudá-los não
# invalida artefato já gravado (cada um carrega os números medidos, não só o veredito).

SHARPNESS_MIN_VARIANCE: Final = 100.0
"""Abaixo desta variância do Laplaciano a foto é tratada como possivelmente borrada."""

OVEREXPOSED_LEVEL: Final = 250
UNDEREXPOSED_LEVEL: Final = 5
"""Níveis de cinza (0-255) a partir dos quais o pixel é considerado estourado/esmagado."""

OVEREXPOSED_MAX_FRACTION: Final = 0.15
UNDEREXPOSED_MAX_FRACTION: Final = 0.30
"""Frações de pixel estourado/esmagado toleradas antes de virar achado."""

MIN_USEFUL_SIDE_PX: Final = 640
"""Menor lado abaixo do qual texto de placa raramente sobrevive à compressão."""

FINDING_LOW_SHARPNESS: Final = "PHOTO_LOW_SHARPNESS"
FINDING_OVEREXPOSED: Final = "PHOTO_OVEREXPOSED"
FINDING_UNDEREXPOSED: Final = "PHOTO_UNDEREXPOSED"
FINDING_LOW_RESOLUTION: Final = "PHOTO_LOW_RESOLUTION"

FALLBACK_NOTE_OPENAI: Final = "PROVIDER_FALLBACK_FIELD_PHOTO_READING_OPENAI"
"""Registrado no artefato quando o braço reserva respondeu no lugar do primário."""


class SurveyPhotoAnalysisError(ValueError):
    """Recusa determinística da análise de uma foto, com código estável.

    É `ValueError` como as demais recusas do despacho: o consumidor não apaga a mensagem
    quando o handler levanta, e reprocessar depois de corrigir a causa (mídia confirmada,
    bytes que chegaram ao storage) é o caminho de retomada.
    """

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


class ProviderPass(StrEnum):
    """Desfecho do passe pago, sempre registrado no artefato.

    `SKIPPED_*` são estados normais e esperados — providers estão desligados por padrão e o
    entitlement é contratual por tenant. `FAILED_TRANSIENT` diz que reprocessar a mensagem
    pode resolver; `FAILED_PERMANENT` diz que não vai resolver (schema recusado, credencial,
    teto de gasto estourado) e que insistir só gastaria de novo.
    """

    DONE = "done"
    SKIPPED_DISABLED = "skipped_disabled"
    SKIPPED_NO_ENTITLEMENT = "skipped_no_entitlement"
    FAILED_TRANSIENT = "failed_transient"
    FAILED_PERMANENT = "failed_permanent"


#: Falhas cuja retentativa tem chance real de sucesso. Espelha `RetryingProviderAdapter.
#: RETRYABLE`: o que chega aqui já esgotou as tentativas do wrapper, e a distinção continua
#: valendo para dizer ao operador se REPROCESSAR a mensagem adianta alguma coisa.
_TRANSIENT_FAILURES: Final = frozenset(
    {
        ProviderFailureCode.TIMEOUT,
        ProviderFailureCode.RATE_LIMITED,
        ProviderFailureCode.UNAVAILABLE,
    }
)


@dataclass(frozen=True, slots=True)
class SurveyPhotoMedia:
    """A mídia como o banco a conhece, já validada como foto confirmada deste tenant."""

    id: str
    sha256: str
    mime_type: str
    byte_size: int
    object_key: str


@dataclass(frozen=True, slots=True)
class PhotoQuality:
    """Medidas do passe offline. Números primeiro, veredito depois — e nunca só o veredito.

    Guardar `sharpness_laplacian_variance` e as frações ao lado dos achados é o que permite
    recalibrar o limiar mais tarde sem reprocessar foto nenhuma: o artefato antigo continua
    dizendo o que foi medido, mesmo quando a constante que o classificou mudar.
    """

    width_px: int
    height_px: int
    sharpness_laplacian_variance: float
    overexposed_fraction: float
    underexposed_fraction: float
    mean_luma: float
    findings: tuple[str, ...]

    def as_document(self) -> dict[str, Any]:
        return {
            "width_px": self.width_px,
            "height_px": self.height_px,
            # Arredondado na gravação: o dígito 15 de um float de OpenCV depende da versão
            # da BLAS da máquina, e artefato que muda sem a foto mudar confunde diff.
            "sharpness_laplacian_variance": round(self.sharpness_laplacian_variance, 2),
            "overexposed_fraction": round(self.overexposed_fraction, 4),
            "underexposed_fraction": round(self.underexposed_fraction, 4),
            "mean_luma": round(self.mean_luma, 2),
            "findings": list(self.findings),
            "thresholds": {
                "sharpness_min_variance": SHARPNESS_MIN_VARIANCE,
                "overexposed_max_fraction": OVEREXPOSED_MAX_FRACTION,
                "underexposed_max_fraction": UNDEREXPOSED_MAX_FRACTION,
                "min_useful_side_px": MIN_USEFUL_SIDE_PX,
            },
        }


@dataclass(frozen=True, slots=True)
class ProviderPassResult:
    """O que o passe pago produziu — inclusive quando não produziu nada."""

    outcome: ProviderPass
    execution: ProviderExecution | None = None
    failure_code: str | None = None
    notes: tuple[str, ...] = ()

    @property
    def output(self) -> FieldPhotoReadingsOutput | None:
        if self.execution is None:
            return None
        output = self.execution.output
        return output if isinstance(output, FieldPhotoReadingsOutput) else None


def survey_analysis_object_key(*, tenant_id: str, survey_id: str, sha256: str) -> str:
    """Chave ESTÁVEL da análise: uma foto, um objeto, reprocessamento sobrescreve."""
    return f"tenants/{tenant_id}/surveys/{survey_id}/analysis/{sha256}.json"


def photo_media(row: Mapping[Any, Any] | None) -> SurveyPhotoMedia:
    """Valida a linha de `survey_media_records` como foto analisável.

    A consulta que produz a linha já é escopada por tenant, então `None` aqui cobre os dois
    casos que o chamador não precisa distinguir: mídia que não existe e mídia de outro
    tenant. Distingui-los na resposta seria contar a quem perguntou que o id existe noutro
    lugar.

    `Mapping[Any, Any]` porque a linha chega como `RowMapping` do SQLAlchemy, cuja chave não
    é `str` para o type checker; este módulo não conhece o driver de banco.
    """
    if row is None:
        raise SurveyPhotoAnalysisError(
            "SURVEY_PHOTO_MEDIA_NOT_FOUND", "mídia inexistente neste levantamento"
        )
    status = str(row["status"])
    if status != SURVEY_MEDIA_CONFIRMED:
        raise SurveyPhotoAnalysisError(
            "SURVEY_PHOTO_MEDIA_NOT_CONFIRMED", "mídia ainda não confirmada"
        )
    mime_type = str(row["mime_type"])
    if not mime_type.startswith(IMAGE_MIME_PREFIX):
        raise SurveyPhotoAnalysisError(
            "SURVEY_PHOTO_MEDIA_NOT_IMAGE", "mídia do levantamento não é imagem"
        )
    return SurveyPhotoMedia(
        id=str(row["id"]),
        sha256=str(row["sha256"]),
        mime_type=mime_type,
        byte_size=int(row["byte_size"]),
        object_key=str(row["object_key"]),
    )


def analyze_photo_quality(image_bytes: bytes) -> PhotoQuality:
    """Mede nitidez, exposição e tamanho da foto. Determinístico e offline.

    A nitidez é a variância do Laplaciano sobre a luminância — o operador realça bordas, e
    foto borrada tem poucas bordas fortes, então a variância desaba. É triagem, não medida
    física: uma foto legitimamente lisa (parede, céu) também pontua baixo, e por isso o
    achado é aviso, nunca recusa.
    """
    buffer = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if image is None or image.size == 0:
        raise SurveyPhotoAnalysisError(
            "SURVEY_PHOTO_UNDECODABLE", "os bytes da mídia não decodificam como imagem"
        )
    grayscale = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    height, width = (int(grayscale.shape[0]), int(grayscale.shape[1]))
    sharpness = float(cv2.Laplacian(grayscale, cv2.CV_64F).var())
    pixels = float(grayscale.size)
    overexposed = float(np.count_nonzero(grayscale >= OVEREXPOSED_LEVEL)) / pixels
    underexposed = float(np.count_nonzero(grayscale <= UNDEREXPOSED_LEVEL)) / pixels
    mean_luma = float(grayscale.mean())

    findings: list[str] = []
    if sharpness < SHARPNESS_MIN_VARIANCE:
        findings.append(FINDING_LOW_SHARPNESS)
    if overexposed > OVEREXPOSED_MAX_FRACTION:
        findings.append(FINDING_OVEREXPOSED)
    if underexposed > UNDEREXPOSED_MAX_FRACTION:
        findings.append(FINDING_UNDEREXPOSED)
    if min(width, height) < MIN_USEFUL_SIDE_PX:
        findings.append(FINDING_LOW_RESOLUTION)
    return PhotoQuality(
        width_px=width,
        height_px=height,
        sharpness_laplacian_variance=sharpness,
        overexposed_fraction=overexposed,
        underexposed_fraction=underexposed,
        mean_luma=mean_luma,
        findings=tuple(findings),
    )


def run_provider_pass(
    primary: ProviderAdapter,
    secondary: ProviderAdapter | None,
    *,
    image_bytes: bytes,
    quality: PhotoQuality,
) -> ProviderPassResult:
    """Executa a leitura paga da foto no braço primário, com o braço reserva declarado.

    A política de fallback é a MESMA das demais tarefas de escolha simples do roteamento
    (`provider_review._execute_with_fallback`): falha transitória já foi esgotada pelo
    `RetryingProviderAdapter` antes de chegar aqui; `BUDGET_EXCEEDED` descreve o teto
    compartilhado e não o braço, então nunca aciona o reserva; e `secondary=None` (braço
    desligado por configuração) propaga a falha do primário sem nota nenhuma — não houve
    troca de braço para registrar.

    A diferença é o desfecho: aqui a exceção **não** sobe. O passe offline já foi feito e
    perdê-lo por causa da via paga inverteria a prioridade — a foto continua analisada, e o
    artefato diz que a leitura não aconteceu e por quê.

    O digest de lineage é o dos bytes REALMENTE enviados, recalculado aqui, e não o digest
    gravado na linha de mídia: o lineage descreve a chamada, não o que o banco esperava.
    """
    request = build_request(
        PromptTask.FIELD_PHOTO_READING,
        image_bytes=image_bytes,
        image_sha256=hashlib.sha256(image_bytes).hexdigest(),
        image_width_px=quality.width_px,
        image_height_px=quality.height_px,
    )
    notes: tuple[str, ...] = ()
    try:
        try:
            execution = primary.execute(request)
        except ProviderExecutionError as error:
            if error.code is ProviderFailureCode.BUDGET_EXCEEDED or secondary is None:
                raise
            execution = secondary.execute(request)
            notes = (FALLBACK_NOTE_OPENAI,)
    except ProviderExecutionError as error:
        outcome = (
            ProviderPass.FAILED_TRANSIENT
            if error.code in _TRANSIENT_FAILURES
            else ProviderPass.FAILED_PERMANENT
        )
        return ProviderPassResult(outcome=outcome, failure_code=error.code.value)
    if not isinstance(execution.output, FieldPhotoReadingsOutput):
        # Inalcançável pelo contrato de `ProviderExecution` (prompt e saída são conferidos
        # na construção); a guarda existe para que uma saída de outra tarefa nunca seja
        # gravada como leitura de foto se aquele validador afrouxar.
        return ProviderPassResult(
            outcome=ProviderPass.FAILED_PERMANENT,
            failure_code=ProviderFailureCode.INVALID_SCHEMA.value,
        )
    return ProviderPassResult(outcome=ProviderPass.DONE, execution=execution, notes=notes)


def _lineage(execution: ProviderExecution | None) -> dict[str, Any] | None:
    """Lineage da chamada sem a saída: quem respondeu, sob qual prompt, a que custo.

    A saída viaja em `readings`; repeti-la aqui criaria duas cópias da mesma leitura no
    mesmo arquivo, e a resposta BRUTA continua só no raw-store protegido, referenciada por
    `raw_response_ref`.
    """
    if execution is None:
        return None
    document = execution.model_dump(mode="json")
    document.pop("output", None)
    return document


def build_photo_analysis_document(
    *,
    tenant_id: str,
    survey_id: str,
    media: SurveyPhotoMedia,
    quality: PhotoQuality,
    provider: ProviderPassResult,
) -> dict[str, Any]:
    """Monta o artefato de análise. Função pura: quem grava é o handler da fila."""
    output = provider.output
    readings = field_photo_reading_documents(output)
    return {
        "schema": ANALYSIS_SCHEMA,
        "tenant_id": tenant_id,
        "survey_id": survey_id,
        "media_id": media.id,
        # Digest e tipo bastam para o escritório reencontrar a foto pelo índice de anexos
        # (`attachments.json`); a chave do objeto não é repetida aqui, e URL assinada nunca
        # entra em artefato.
        "media": {"sha256": media.sha256, "mime_type": media.mime_type},
        "quality": quality.as_document(),
        "provider_pass": provider.outcome.value,
        "provider_failure_code": provider.failure_code,
        "provider_notes": list(provider.notes),
        # Rascunhos a revisar. Nada aqui está confirmado, associado a ponto/elemento do
        # levantamento, nem vira medida.
        "readings": readings,
        "notes": [] if output is None else list(output.notes),
        "lineage": _lineage(provider.execution),
    }


def field_photo_reading_documents(
    output: FieldPhotoReadingsOutput | None,
) -> list[dict[str, Any]]:
    """Acrescenta identidade determinística sem pedir ao modelo que invente uma.

    O identificador nasce do conteúdo validado e da posição. Reentregar a mesma mensagem
    produz os mesmos ids, inclusive quando duas inscrições iguais aparecem na mesma foto.
    """
    if output is None:
        return []
    documents: list[dict[str, Any]] = []
    for index, reading in enumerate(output.readings):
        payload = reading.model_dump(mode="json")
        canonical = json.dumps(
            {"index": index, "reading": payload},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        payload["id"] = f"fpr_{hashlib.sha256(canonical.encode()).hexdigest()[:24]}"
        documents.append(payload)
    return documents


def build_field_evidence_reading_document(
    *,
    tenant_id: str,
    job_id: str,
    origin: str,
    evidence_id: str,
    media: SurveyPhotoMedia,
    quality: PhotoQuality,
    provider: ProviderPassResult,
) -> dict[str, Any]:
    """Artefato de leitura pedida no job; rascunho sem medida ou geometria."""
    output = provider.output
    return {
        "schema": FIELD_EVIDENCE_READING_SCHEMA,
        "tenant_id": tenant_id,
        "job_id": job_id,
        "origin": origin,
        "evidence_id": evidence_id,
        "media": {"sha256": media.sha256, "mime_type": media.mime_type},
        "quality": quality.as_document(),
        "provider_pass": provider.outcome.value,
        "provider_failure_code": provider.failure_code,
        "provider_notes": list(provider.notes),
        "readings": field_photo_reading_documents(output),
        "notes": [] if output is None else list(output.notes),
        "lineage": _lineage(provider.execution),
    }


def analysis_counts(document: Mapping[str, Any]) -> dict[str, int]:
    """Contagens para log: números e nada de conteúdo da foto."""
    quality = document["quality"]
    return {
        "readings": len(document["readings"]),
        "notes": len(document["notes"]),
        "findings": len(quality["findings"]),
    }
