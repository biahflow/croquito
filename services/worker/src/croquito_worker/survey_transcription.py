"""Transcrição da nota de voz de campo (F-032, T13): rascunho ao lado do áudio, nunca no lugar.

A nota que o técnico gravou na praça chega aqui depois do `confirm` da mídia (T8) e produz um
ARTEFATO DE TRANSCRIÇÃO. Três invariantes governam o módulo inteiro:

1. **o áudio continua sendo a evidência.** A transcrição nasce e permanece `status: "draft"`;
   nada aqui substitui, apaga ou reescreve a gravação, e o escritório revisa o texto com o
   áudio ao lado. Por isso não há confirmação nesta fatia: a superfície que mostra o rascunho
   ao revisor é trabalho posterior (a prancha 7c da DAP rev.2 mostra só "em processamento");
2. **nada do levantamento é mutado.** `survey_records` e `survey_media_records` são lidos; o
   texto sai num objeto próprio, em chave estável derivada do digest do áudio — reprocessar a
   mesma mensagem sobrescreve o mesmo objeto, como na análise de foto (T14) e no export (T11);
3. **o passe pago é condicional e o artefato é incondicional.** Sem caminho pago habilitado,
   sem entitlement contratual do tenant ou sem braço configurado, o artefato é gravado assim
   mesmo, com `provider_pass` dizendo o que aconteceu e `transcript: null`. Ligar a chave
   depois e reprocessar é o caminho de retomada — e o artefato já gravado diz que ele é
   possível, em vez de deixar o operador adivinhar se houve tentativa.

Diferença estrutural em relação à T14, e vale nomeá-la: a análise de foto tem um passe OFFLINE
que sempre roda (nitidez, exposição). Aqui não existe equivalente honesto — não há medida
determinística que se possa extrair de uma gravação sem transcrevê-la, e inventar uma
(duração, nível de áudio) daria ao artefato uma aparência de conteúdo que ele não teria. Sem
provider, o artefato é metadado e nada mais.

Qual fornecedor transcreve é CONFIGURAÇÃO (`CROQUITO_TRANSCRIPTION_PRIMARY`/`_FALLBACK`), com
default provisório Groq `whisper-large-v3-turbo`: a decisão de fornecedor foi humana, mas qual
modelo fica de primário sai da eval comparativa (`transcription_eval`), ainda pendente de
rodada paga.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from croquito_worker.providers import (
    AudioTranscriptionOutput,
    PromptTask,
    ProviderAdapter,
    ProviderExecution,
    ProviderExecutionError,
    ProviderFailureCode,
    RetryingProviderAdapter,
    build_audio_request,
)
from croquito_worker.survey_export import SURVEY_MEDIA_CONFIRMED

# `ProviderPass` é importado da análise de foto, e não redefinido aqui, de propósito: os cinco
# estados são o MESMO vocabulário de desfecho de passe pago que a T14 estabeleceu, e duas
# cópias divergiriam no primeiro estado novo — um artefato passaria a dizer `failed_permanent`
# e o outro continuaria com quatro estados, sem que nada quebrasse para avisar.
from croquito_worker.survey_photo_analysis import ProviderPass

TRANSCRIPT_SCHEMA: Final = "survey-transcript/1"
"""Identidade do artefato gravado. Consumidor novo lê isto antes de qualquer campo."""

TRANSCRIPT_STATUS_DRAFT: Final = "draft"
"""Único valor possível de `status` nesta fatia; confirmação é ato humano em fatia futura."""

SUPPORTED_AUDIO_MIME_TYPES: Final = frozenset({"audio/webm", "audio/mp4"})
"""Os dois containers que o app grava (T12): webm/opus no Android, mp4/aac no iPhone."""

NOTE_NOT_FOUND: Final = "TRANSCRIPT_NOTE_NOT_FOUND"
"""Áudio confirmado que nenhuma observação do snapshot reivindica.

Acontece de verdade e não é erro: o `confirm` da mídia e a conclusão do levantamento são atos
distintos, então o áudio pode chegar antes de o snapshot que o cita ser consolidado — ou a
nota pode ter sido apagada no aparelho depois de a mídia subir. A transcrição continua, o
vínculo fica vazio, e o aviso estruturado diz por quê.
"""

SNAPSHOT_UNREADABLE: Final = "TRANSCRIPT_SNAPSHOT_UNREADABLE"
"""Snapshot que não dá para percorrer. Vira aviso, não recusa: o áudio existe e é confirmado,
e perder a transcrição por causa da forma do snapshot puniria a evidência pelo índice."""

FALLBACK_NOTE_PREFIX: Final = "PROVIDER_FALLBACK_AUDIO_TRANSCRIPTION_"
"""Prefixo da nota que registra a troca de braço; o sufixo é quem realmente respondeu."""


class SurveyTranscriptionError(ValueError):
    """Recusa determinística da transcrição de um áudio, com código estável.

    É `ValueError` como as demais recusas do despacho: o consumidor não apaga a mensagem
    quando o handler levanta, e reprocessar depois de corrigir a causa (mídia confirmada,
    bytes que chegaram ao storage) é o caminho de retomada.
    """

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


@dataclass(frozen=True, slots=True)
class SurveyAudioMedia:
    """A mídia como o banco a conhece, já validada como áudio confirmado deste tenant."""

    id: str
    sha256: str
    mime_type: str
    byte_size: int
    object_key: str


@dataclass(frozen=True, slots=True)
class TranscriptionPassResult:
    """O que o passe de transcrição produziu — inclusive quando não produziu nada."""

    outcome: ProviderPass
    execution: ProviderExecution | None = None
    failure_code: str | None = None
    notes: tuple[str, ...] = ()

    @property
    def output(self) -> AudioTranscriptionOutput | None:
        if self.execution is None:
            return None
        output = self.execution.output
        return output if isinstance(output, AudioTranscriptionOutput) else None


def survey_transcript_object_key(*, tenant_id: str, survey_id: str, sha256: str) -> str:
    """Chave ESTÁVEL da transcrição: um áudio, um objeto, reprocessamento sobrescreve."""
    return f"tenants/{tenant_id}/surveys/{survey_id}/transcripts/{sha256}.json"


def audio_media(row: Mapping[Any, Any] | None) -> SurveyAudioMedia:
    """Valida a linha de `survey_media_records` como áudio transcritível.

    A consulta que produz a linha já é escopada por tenant, então `None` aqui cobre os dois
    casos que o chamador não precisa distinguir: mídia que não existe e mídia de outro
    tenant. Distingui-los na resposta seria contar a quem perguntou que o id existe noutro
    lugar.

    `Mapping[Any, Any]` porque a linha chega como `RowMapping` do SQLAlchemy, cuja chave não
    é `str` para o type checker; este módulo não conhece o driver de banco.
    """
    if row is None:
        raise SurveyTranscriptionError(
            "SURVEY_AUDIO_MEDIA_NOT_FOUND", "mídia inexistente neste levantamento"
        )
    status = str(row["status"])
    if status != SURVEY_MEDIA_CONFIRMED:
        raise SurveyTranscriptionError(
            "SURVEY_AUDIO_MEDIA_NOT_CONFIRMED", "mídia ainda não confirmada"
        )
    mime_type = str(row["mime_type"])
    if mime_type not in SUPPORTED_AUDIO_MIME_TYPES:
        # Container fora da lista para ANTES de sair da máquina: o fornecedor decodifica pelo
        # tipo declarado, e mandar o que ele não aceita gastaria uma chamada para receber 400.
        raise SurveyTranscriptionError(
            "SURVEY_AUDIO_MEDIA_UNSUPPORTED_MIME", "container de áudio não suportado"
        )
    return SurveyAudioMedia(
        id=str(row["id"]),
        sha256=str(row["sha256"]),
        mime_type=mime_type,
        byte_size=int(row["byte_size"]),
        object_key=str(row["object_key"]),
    )


def locate_note(snapshot: object, *, sha256: str) -> tuple[str | None, tuple[str, ...]]:
    """Acha, no snapshot do levantamento, a observação dona deste áudio.

    Percorre a estrutura como `Mapping` em vez de validar `SurveyPacket`: o vínculo é
    conveniência para o escritório, e um snapshot que não satisfaça o contrato inteiro (uma
    versão futura do pacote, um campo novo) não deve custar a transcrição de um áudio que
    existe e está confirmado. Quem exige o contrato completo é o export (T11), que produz
    geometria; aqui o preço do rigor seria alto e o ganho, nenhum.

    Devolve `(note_id | None, avisos)`. Nunca levanta: toda ausência vira aviso estruturado.
    """
    if not isinstance(snapshot, Mapping):
        return None, (SNAPSHOT_UNREADABLE,)
    observations = snapshot.get("observations")
    if not isinstance(observations, Sequence) or isinstance(observations, str | bytes):
        return None, (SNAPSHOT_UNREADABLE,)
    for observation in observations:
        if not isinstance(observation, Mapping):
            continue
        reference = observation.get("audio_media_ref")
        if not isinstance(reference, Mapping):
            continue
        if reference.get("sha256") != sha256:
            continue
        note_id = observation.get("id")
        if isinstance(note_id, str) and note_id:
            return note_id, ()
        # Observação que cita o áudio mas não tem id utilizável: o vínculo não existe, e
        # inventá-lo seria pior do que não tê-lo.
        return None, (NOTE_NOT_FOUND,)
    return None, (NOTE_NOT_FOUND,)


def run_transcription_pass(
    primary: ProviderAdapter | None,
    fallback: ProviderAdapter | None,
    *,
    audio_bytes: bytes,
    mime_type: str,
) -> TranscriptionPassResult:
    """Executa a transcrição no braço primário, com o reserva declarado.

    A política de fallback é a MESMA das demais tarefas de escolha simples do roteamento
    (`survey_photo_analysis.run_provider_pass`): falha transitória já foi esgotada pelo
    `RetryingProviderAdapter` antes de chegar aqui; `BUDGET_EXCEEDED` descreve o teto
    compartilhado e não o braço, então nunca aciona o reserva; e `fallback=None` (braço
    desligado por configuração, que é o default até a eval decidir) propaga a falha do
    primário sem nota nenhuma — não houve troca de braço para registrar.

    `primary=None` é braço não configurado (sem chave), e é desfecho PULADO, não falha: a
    nota de voz continua íntegra no pacote e a transcrição pode acontecer depois.

    A exceção não sobe: o artefato é gravado de qualquer forma, dizendo o que aconteceu.
    """
    if primary is None:
        return TranscriptionPassResult(outcome=ProviderPass.SKIPPED_DISABLED)
    request = build_audio_request(
        PromptTask.AUDIO_TRANSCRIPTION, audio_bytes=audio_bytes, audio_mime_type=mime_type
    )
    notes: tuple[str, ...] = ()
    try:
        try:
            execution = primary.execute(request)
        except ProviderExecutionError as error:
            if error.code is ProviderFailureCode.BUDGET_EXCEEDED or fallback is None:
                raise
            execution = fallback.execute(request)
            notes = (f"{FALLBACK_NOTE_PREFIX}{execution.provider.value.upper()}",)
    except ProviderExecutionError as error:
        outcome = (
            ProviderPass.FAILED_TRANSIENT
            # `RetryingProviderAdapter.RETRYABLE` é a mesma lista que o wrapper já esgotou; a
            # distinção continua valendo aqui para dizer ao operador se REPROCESSAR a
            # mensagem adianta alguma coisa.
            if error.code in RetryingProviderAdapter.RETRYABLE
            else ProviderPass.FAILED_PERMANENT
        )
        return TranscriptionPassResult(outcome=outcome, failure_code=error.code.value)
    if not isinstance(execution.output, AudioTranscriptionOutput):
        # Inalcançável pelo contrato de `ProviderExecution` (prompt e saída são conferidos na
        # construção); a guarda existe para que a saída de outra tarefa nunca seja gravada
        # como transcrição se aquele validador afrouxar.
        return TranscriptionPassResult(
            outcome=ProviderPass.FAILED_PERMANENT,
            failure_code=ProviderFailureCode.INVALID_SCHEMA.value,
        )
    return TranscriptionPassResult(outcome=ProviderPass.DONE, execution=execution, notes=notes)


def _lineage(execution: ProviderExecution | None) -> dict[str, Any] | None:
    """Lineage da chamada sem a saída: quem respondeu, sob qual política, a que custo.

    O texto viaja em `transcript`; repeti-lo aqui criaria duas cópias da mesma transcrição no
    mesmo arquivo, e a resposta BRUTA (com segmentos e timestamps) continua só no raw-store
    protegido, referenciada por `raw_response_ref`.
    """
    if execution is None:
        return None
    document = execution.model_dump(mode="json")
    document.pop("output", None)
    return document


def build_transcript_document(
    *,
    tenant_id: str,
    survey_id: str,
    media: SurveyAudioMedia,
    note_id: str | None,
    provider: TranscriptionPassResult,
    notes: Sequence[str] = (),
) -> dict[str, Any]:
    """Monta o artefato de transcrição. Função pura: quem grava é o handler da fila."""
    output = provider.output
    execution = provider.execution
    transcript = (
        None
        if output is None or execution is None
        else {
            "text": output.text,
            "language": output.language,
            # O modelo fica DENTRO do rascunho, além do lineage, porque é ele que dá sentido
            # ao texto para quem revisa: dois modelos transcrevem a mesma gravação de formas
            # diferentes, e a eval comparativa existe justamente por causa disso.
            "model": execution.model_id,
            "duration_s": output.duration_s,
        }
    )
    return {
        "schema": TRANSCRIPT_SCHEMA,
        "tenant_id": tenant_id,
        "survey_id": survey_id,
        "media_id": media.id,
        # Digest e tipo bastam para o escritório reencontrar o áudio pelo índice de anexos
        # (`attachments.json`); a chave do objeto não é repetida aqui, e URL assinada nunca
        # entra em artefato.
        "media": {"sha256": media.sha256, "mime_type": media.mime_type},
        "note_id": note_id,
        "provider_pass": provider.outcome.value,
        "provider_failure_code": provider.failure_code,
        "provider_notes": list(provider.notes),
        "transcript": transcript,
        "notes": list(notes),
        "lineage": _lineage(provider.execution),
        # Sempre `draft`, sem exceção e sem caminho que mude isso nesta fatia.
        "status": TRANSCRIPT_STATUS_DRAFT,
    }


def transcript_counts(document: Mapping[str, Any]) -> dict[str, int]:
    """Contagens para log: números e nada do que foi dito."""
    transcript = document["transcript"]
    return {
        "characters": 0 if transcript is None else len(transcript["text"]),
        "notes": len(document["notes"]),
    }
