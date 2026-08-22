"""Levantamento de campo sincronizado → observações do pipeline (F-032, T11).

O técnico conclui o levantamento na PWA (ADR-0043), a API grava o pacote consolidado e
publica `export_survey`; este módulo transforma esse pacote em **observação**, nunca em
geometria resolvida:

- a cena produzida é uma `SceneRevision` com `approved=False`, toda entidade
  `approximate`/`unresolved` e `export=False` — os portões de
  `SceneRevision.export_errors()` continuam segurando o artefato, e `Precision.EXACT`
  não nasce aqui (medida de trena é evidência de campo, não cota lida de prancha);
- o `job_id` da cena é um identificador de NAMESPACE de cena de campo. **Não existe
  `JobRecord` correspondente**: a integração destas observações na jornada do escritório
  é fatia futura (decisão registrada em `plan-sync.md`, relação com F-030). Nada aqui
  cria `JobRecord`/`RevisionRecord` nem toca o schema do banco;
- o que não é geometria (mídia ancorada, notas, contexto de chegada, GPS, waivers e as
  medidas sem correspondente no scene graph) viaja num índice separado,
  `attachments.json`, para não entrar na cena como se fosse desenho.

Convenção de eixo, a MESMA de `tracing.py` ("cota manda", espelho de Y): o levantamento
usa coordenadas de tela, onde `y_mm` cresce para BAIXO; a cena métrica cresce para cima,
então `y_m = -y_mm / 1000`. Ao contrário de `tracing.solve_trace`, nada é normalizado
para o canto inferior esquerdo: a origem do levantamento é local e declarada pelo próprio
técnico (`apps/field/src/domain/types.ts`), e movê-la aqui perderia a única referência que
ele registrou.

Milímetro é sempre `int` no pacote de campo, então `value_si` é `Decimal(value_mm) /
Decimal(1000)` — exato, sem passar por `float` em momento algum.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Final
from uuid import UUID, uuid5

from croquito_core.field import (
    ArrivalContext,
    MeasurementStatus,
    ObservationNote,
    SurveyPacket,
    SurveyPoint,
)
from croquito_core.field import Measurement as FieldMeasurement
from croquito_core.field import MeasurementKind as FieldMeasurementKind
from croquito_core.models import (
    Entity,
    EntityKind,
    Issue,
    IssueSeverity,
    IssueStatus,
    LayerName,
    LineGeometry,
    Measurement,
    MeasurementKind,
    Point2D,
    Precision,
    Provenance,
    SceneRevision,
    UnitCode,
)

ATTACHMENTS_SCHEMA_VERSION: Final = "1.0.0"

MM_PER_METRE: Final = Decimal(1000)

FIELD_SOURCE_TYPE: Final = "field_survey"
"""`Provenance.source_type` de tudo que nasce de um levantamento de campo."""

FIELD_SUMMARY_CODE: Final = "FIELD_SURVEY"
FIELD_CONFIRMED_SUMMARY_CODE: Final = "FIELD_CONFIRMED"
"""Só medida que o técnico confirmou em campo carrega este código."""

FIELD_SCENE_NAMESPACE: Final = UUID("64179538-5c9a-4aa4-92bd-892fcd5e583c")
"""Namespace das cenas de campo, usado só quando o `survey_id` não é um UUID.

O id do levantamento nasce no aparelho (`crypto.randomUUID`), mas o app já persistiu id
que não é UUID (`survey-local`, do scaffold da fatia 0 — ver `SurveyRecord` em
`services/api/.../database.py`). Derivar por `uuid5` mantém o `job_id` estável entre
reprocessamentos sem recusar o dado legado nem inventar um id novo a cada execução.
"""

SURVEY_MEDIA_CONFIRMED: Final = "CONFIRMED"
SURVEY_COMPLETED: Final = "COMPLETED"

#: Kinds do levantamento com correspondente FIEL no scene graph planimétrico.
_SCENE_MEASUREMENT_KIND: Final[dict[FieldMeasurementKind, MeasurementKind]] = {
    FieldMeasurementKind.LENGTH: MeasurementKind.LENGTH,
    # Diagonal é comprimento entre dois pontos do plano; o `raw_text` preserva a leitura e
    # a provenance aponta para a medida de campo, que continua declarando "diagonal".
    FieldMeasurementKind.DIAGONAL: MeasurementKind.LENGTH,
    FieldMeasurementKind.WIDTH: MeasurementKind.WIDTH,
    FieldMeasurementKind.RADIUS: MeasurementKind.RADIUS,
}

#: Kinds sem correspondente fiel: viram `Issue` INFO e entrada em `attachments.json`, com
#: o motivo. Preferir a abstenção a forçar um kind é a regra do repositório ("nunca
#: invente, arredonde silenciosamente ou complete uma medida ausente", AGENTS.md).
_UNMAPPED_MEASUREMENT_KIND: Final[dict[FieldMeasurementKind, tuple[str, str]]] = {
    # `height`, `level` e `drop` são verticais; o scene graph é planimétrico e usa
    # `MeasurementKind.HEIGHT` para a extensão vertical EM PLANTA (ver `_measured_value`
    # em `croquito_core.models`, que a compara com o comprimento do segmento desenhado).
    # Casar os dois faria uma altura de muro ser conferida contra a distância em planta.
    FieldMeasurementKind.HEIGHT: (
        "FIELD_MEASUREMENT_NOT_PLANIMETRIC",
        "altura medida em campo é vertical e não tem correspondente na cena planimétrica",
    ),
    FieldMeasurementKind.LEVEL: (
        "FIELD_MEASUREMENT_NOT_PLANIMETRIC",
        "cota de nível não tem correspondente na cena planimétrica",
    ),
    FieldMeasurementKind.DROP: (
        "FIELD_MEASUREMENT_NOT_PLANIMETRIC",
        "desnível não tem correspondente na cena planimétrica",
    ),
    # O valor angular ainda viaja em `value_mm` no domínio de campo e a unidade não foi
    # decidida (`apps/field/src/domain/types.ts`). Declarar `rad` ou `deg` aqui seria
    # inventar unidade; `UnitCode` não tem alternativa neutra.
    FieldMeasurementKind.ANGLE: (
        "FIELD_ANGLE_UNIT_UNDECIDED",
        "medida angular sem unidade decidida no domínio de campo",
    ),
}

ISSUE_MEASUREMENT_WITHOUT_SEGMENT: Final = "FIELD_MEASUREMENT_WITHOUT_SEGMENT"
ISSUE_POINT_WITHOUT_SEGMENT: Final = "FIELD_POINT_WITHOUT_SEGMENT"
ISSUE_SEGMENT_WITHOUT_POINT: Final = "FIELD_SEGMENT_WITHOUT_POINT"
ISSUE_WAIVER_PREFIX: Final = "FIELD_WAIVER"

_ISSUE_CODE_MAX: Final = 64
_MESSAGE_MAX: Final = 500


class SurveyExportError(ValueError):
    """Recusa determinística da exportação de um levantamento, com código estável.

    É `ValueError` como as demais recusas do despacho: o consumidor SQS não apaga a
    mensagem quando o handler levanta, e reprocessar depois de corrigir a causa (mídia que
    chegou, conclusão que faltava) é o caminho de retomada.
    """

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


@dataclass(frozen=True, slots=True)
class SurveyMediaObject:
    """Uma mídia do levantamento como o banco a conhece: digest, tipo e chave do objeto."""

    sha256: str
    mime_type: str
    byte_size: int
    object_key: str
    status: str


@dataclass(frozen=True, slots=True)
class SurveyExportArtifacts:
    """Os dois artefatos do levantamento exportado, ainda em memória."""

    scene: SceneRevision
    attachments: dict[str, Any]

    def counts(self) -> dict[str, int]:
        """Contagens para log: números e nada de conteúdo de campo."""
        return {
            "entities": len(self.scene.entities),
            "measurements": len(self.scene.measurements),
            "issues": len(self.scene.issues),
            "media": len(self.attachments["media"]),
            "notes": len(self.attachments["notes"]),
        }


def survey_export_prefix(*, tenant_id: str, survey_id: str) -> str:
    return f"tenants/{tenant_id}/surveys/{survey_id}/export"


def survey_scene_object_key(*, tenant_id: str, survey_id: str) -> str:
    """Chave ESTÁVEL da cena: reprocessar a mesma mensagem sobrescreve o mesmo objeto."""
    return f"{survey_export_prefix(tenant_id=tenant_id, survey_id=survey_id)}/scene.json"


def survey_attachments_object_key(*, tenant_id: str, survey_id: str) -> str:
    """Chave estável do índice de anexos, pela mesma razão da cena."""
    return f"{survey_export_prefix(tenant_id=tenant_id, survey_id=survey_id)}/attachments.json"


def field_scene_job_id(*, tenant_id: str, survey_id: str) -> UUID:
    """Namespace da cena de campo — NÃO é o id de um `JobRecord`, que não existe."""
    try:
        return UUID(survey_id)
    except ValueError:
        return uuid5(FIELD_SCENE_NAMESPACE, f"{tenant_id}:{survey_id}")


def index_origin_operations(
    operations: Iterable[tuple[str, Mapping[str, Any]]],
) -> dict[str, str]:
    """Mapeia o id de cada objeto de campo à operação do outbox que o criou.

    Todo comando do app publica `{"<objeto>": {...,"id": ...}}` (`domain/commands.ts`),
    então uma varredura de um nível encontra a origem sem que o worker precise conhecer o
    vocabulário de tipos de operação. A primeira ocorrência vence: as operações chegam em
    ordem de `seq`, e criar vem antes de corrigir.
    """
    origins: dict[str, str] = {}
    for operation_id, payload in operations:
        for value in payload.values():
            if isinstance(value, Mapping):
                created_id = value.get("id")
                if isinstance(created_id, str):
                    origins.setdefault(created_id, operation_id)
    return origins


def _scene_point(point: SurveyPoint) -> Point2D:
    """mm de tela → metros de cena, com o eixo Y espelhado (pixel desce, desenho sobe)."""
    return Point2D(x=point.x_mm / 1000, y=-point.y_mm / 1000)


def _issue_code(prefix: str, raw: str) -> str:
    """Código de issue a partir de um código de finding do app, sempre no padrão do contrato."""
    normalized = "".join(character if character.isalnum() else "_" for character in raw.upper())
    normalized = "_".join(part for part in normalized.split("_") if part)
    if not normalized:
        return prefix
    return f"{prefix}_{normalized}"[:_ISSUE_CODE_MAX]


def _trim(message: str) -> str:
    return message[:_MESSAGE_MAX]


def _instant(value: datetime) -> str:
    return value.isoformat()


def _media_entry(
    *,
    role: str,
    anchor_id: str | None,
    media: SurveyMediaObject,
    point_id: str | None = None,
    element_id: str | None = None,
    note_id: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Uma linha do índice de anexos: metadado e CHAVE do objeto, nunca URL assinada."""
    return {
        "role": role,
        "anchor_id": anchor_id,
        "sha256": media.sha256,
        "mime_type": media.mime_type,
        "byte_size": media.byte_size,
        "object_key": media.object_key,
        "point_id": point_id,
        "element_id": element_id,
        "note_id": note_id,
        "created_at": created_at,
    }


def _note_entry(note: ObservationNote) -> dict[str, Any]:
    return {
        "id": note.id,
        "text": note.text,
        "point_id": note.point_id,
        "element_id": note.element_id,
        "audio_sha256": note.audio_media_ref.sha256 if note.audio_media_ref else None,
        "created_at": _instant(note.created_at),
    }


def _arrival_entry(context: ArrivalContext) -> dict[str, Any]:
    gps = context.gps
    return {
        "instrument": context.instrument,
        "reference_note": context.reference_note,
        "gps": gps if isinstance(gps, str) or gps is None else gps.model_dump(mode="json"),
        "access_sha256": (
            context.access_media_ref.sha256 if context.access_media_ref is not None else None
        ),
        "arrived_at": _instant(context.arrived_at),
    }


def _measurement_entry(
    measurement: FieldMeasurement, *, reason_code: str, reason: str
) -> dict[str, Any]:
    """Medida de campo que não virou medida de cena — preservada com o motivo."""
    return {
        "id": measurement.id,
        "kind": measurement.kind.value,
        "value_mm": measurement.value_mm,
        "status": measurement.status.value,
        "instrument": measurement.instrument,
        "justification": measurement.justification,
        "from_point_id": measurement.from_point_id,
        "to_point_id": measurement.to_point_id,
        "second_from_point_id": measurement.second_from_point_id,
        "second_to_point_id": measurement.second_to_point_id,
        "element_id": measurement.element_id,
        "reason_code": reason_code,
        "reason": reason,
        "created_at": _instant(measurement.created_at),
    }


def _referenced_media_digests(packet: SurveyPacket) -> set[str]:
    """Todo `sha256` citado pelo pacote, nos três lugares em que ele cita mídia.

    Mesma leitura que a rota de conclusão faz antes de publicar o comando (âncora, áudio
    de observação e foto de acesso da chegada); aqui ela é defesa em profundidade — o
    worker não confia em quem publicou a mensagem.
    """
    digests = {anchor.media_ref.sha256 for anchor in packet.media_anchors}
    digests.update(
        note.audio_media_ref.sha256 for note in packet.observations if note.audio_media_ref
    )
    if packet.arrival_context is not None and packet.arrival_context.access_media_ref is not None:
        digests.add(packet.arrival_context.access_media_ref.sha256)
    return digests


def _provenance(
    *, survey_id: str, device_id: str, origin_id: str, operation_id: str | None, summary_code: str
) -> Provenance:
    source_ids = [survey_id, device_id, origin_id]
    if operation_id is not None:
        source_ids.append(operation_id)
    return Provenance(
        source_type=FIELD_SOURCE_TYPE, source_ids=source_ids, summary_code=summary_code
    )


def build_survey_export(
    packet: SurveyPacket,
    *,
    tenant_id: str,
    survey_id: str,
    media: Mapping[str, SurveyMediaObject],
    origin_operations: Mapping[str, str] | None = None,
) -> SurveyExportArtifacts:
    """Monta cena de observações + índice de anexos a partir do pacote consolidado.

    Função determinística e sem I/O: o handler da fila carrega o banco, chama isto e grava
    os dois artefatos. Recusa com `SurveyExportError` quando o pacote descreve outro
    levantamento ou quando alguma mídia citada não chegou confirmada.
    """
    if packet.survey_id != survey_id:
        raise SurveyExportError(
            "SURVEY_SNAPSHOT_INVALID",
            "o pacote consolidado declara outro levantamento",
        )
    pending = sorted(
        digest for digest in _referenced_media_digests(packet) if _pending(digest, media)
    )
    if pending:
        raise SurveyExportError(
            "SURVEY_MEDIA_PENDING",
            f"mídia referenciada sem confirmação: {len(pending)}",
        )

    origins = dict(origin_operations or {})
    device_id = packet.device_id
    point_by_id = {point.id: point for point in packet.points}

    entities: list[Entity] = []
    measurements: list[Measurement] = []
    issues: list[Issue] = []
    unmapped: list[dict[str, Any]] = []

    # 1. Segmento observado → uma reta por segmento. Cadeia de segmentos NÃO vira polilinha
    #    e elemento NÃO vira geometria: o app desenha o elemento como área rotulada em
    #    volta dos pontos (`ui/viewModel.ts`), sem declarar ordem de ligação — encadear
    #    aqui seria topologia inventada, e o pipeline resolve topologia com evidência
    #    (`topology.py`), não com palpite do exportador.
    entity_by_segment: dict[str, Entity] = {}
    segment_by_pair: dict[frozenset[str], str] = {}
    connected_points: set[str] = set()
    for segment in packet.segments:
        start = point_by_id.get(segment.from_point_id)
        end = point_by_id.get(segment.to_point_id)
        if start is None or end is None:
            issues.append(
                Issue(
                    code=ISSUE_SEGMENT_WITHOUT_POINT,
                    severity=IssueSeverity.WARNING,
                    status=IssueStatus.OPEN,
                    message=_trim(
                        f"segmento {segment.id} cita ponto ausente no pacote consolidado"
                    ),
                )
            )
            continue
        connected_points.update({segment.from_point_id, segment.to_point_id})
        segment_by_pair.setdefault(
            frozenset({segment.from_point_id, segment.to_point_id}), segment.id
        )
        entity = Entity(
            kind=EntityKind.LINE,
            # A camada é rótulo de observação, não classificação de elemento: nada aqui
            # sabe se a linha é muro ou alambrado. `REVISAO`/`APROXIMADO` dizem o que a
            # linha É — evidência a revisar, e aproximada quando há medida confirmada.
            layer=LayerName.REVISAO,
            precision=Precision.UNRESOLVED,
            geometry=LineGeometry(start=_scene_point(start), end=_scene_point(end)),
            provenance=_provenance(
                survey_id=survey_id,
                device_id=device_id,
                origin_id=segment.id,
                operation_id=origins.get(segment.id),
                summary_code=FIELD_SUMMARY_CODE,
            ),
            # Observação nunca sai em CAD: o portão de exportação recebe o artefato já
            # marcado, e nenhum caminho deste módulo escreve `True` aqui.
            export=False,
        )
        entities.append(entity)
        entity_by_segment[segment.id] = entity

    # 2. Ponto isolado não vira entidade — não existe geometria de um ponto só no contrato
    #    da cena — mas a observação não se perde: vira issue informativa.
    for point in packet.points:
        if point.id not in connected_points:
            issues.append(
                Issue(
                    code=ISSUE_POINT_WITHOUT_SEGMENT,
                    severity=IssueSeverity.INFO,
                    status=IssueStatus.OPEN,
                    message=_trim(f"ponto {point.id} sem segmento observado"),
                )
            )

    # 3. Medidas: só as que têm kind fiel E segmento observado viram medida de cena.
    for measurement in packet.measurements:
        unmapped_reason = _UNMAPPED_MEASUREMENT_KIND.get(measurement.kind)
        if unmapped_reason is not None:
            code, reason = unmapped_reason
            issues.append(
                Issue(
                    code=code,
                    severity=IssueSeverity.INFO,
                    status=IssueStatus.OPEN,
                    message=_trim(f"medida {measurement.id} preservada em anexo: {reason}"),
                )
            )
            unmapped.append(_measurement_entry(measurement, reason_code=code, reason=reason))
            continue
        segment_id: str | None = None
        if measurement.from_point_id is not None and measurement.to_point_id is not None:
            segment_id = segment_by_pair.get(
                frozenset({measurement.from_point_id, measurement.to_point_id})
            )
        # Medida ancorada em elemento cai aqui de propósito: elemento não tem geometria
        # nesta fatia, e amarrar a medida ao segmento mais próximo seria associação
        # implícita — proibida no pipeline inteiro.
        target = entity_by_segment[segment_id] if segment_id is not None else None
        if target is None:
            reason = (
                "medida sem segmento observado entre os pontos citados;"
                " proximidade não é associação"
            )
            issues.append(
                Issue(
                    code=ISSUE_MEASUREMENT_WITHOUT_SEGMENT,
                    severity=IssueSeverity.INFO,
                    status=IssueStatus.OPEN,
                    message=_trim(f"medida {measurement.id} preservada em anexo: {reason}"),
                )
            )
            unmapped.append(
                _measurement_entry(
                    measurement, reason_code=ISSUE_MEASUREMENT_WITHOUT_SEGMENT, reason=reason
                )
            )
            continue
        confirmed = measurement.status is MeasurementStatus.CONFIRMED
        measurements.append(
            Measurement(
                entity_id=target.id,
                kind=_SCENE_MEASUREMENT_KIND[measurement.kind],
                raw_text=f"{measurement.value_mm} mm",
                # Inteiro em mm: a divisão decimal é exata e nenhum `float` participa.
                value_si=Decimal(measurement.value_mm) / MM_PER_METRE,
                unit=UnitCode.METRE,
                # O escrito em campo tem resolução de milímetro; em metro são 3 casas, e é
                # essa a tolerância que o portão usa ao conferir medida contra geometria.
                written_decimals=3,
                confirmed=confirmed,
                provenance=_provenance(
                    survey_id=survey_id,
                    device_id=device_id,
                    origin_id=measurement.id,
                    operation_id=origins.get(measurement.id),
                    summary_code=(
                        FIELD_CONFIRMED_SUMMARY_CODE if confirmed else FIELD_SUMMARY_CODE
                    ),
                ),
            )
        )
        if confirmed and target.precision is Precision.UNRESOLVED:
            # Coberta por medida confirmada em campo: sobe de `unresolved` para
            # `approximate` e NUNCA além disso — dimensão exata não nasce de levantamento.
            target.precision = Precision.APPROXIMATE
            target.layer = LayerName.APROXIMADO

    # 4. Waiver de conclusão → issue não crítica em aberto: a pendência que o técnico
    #    manteve segue visível no escritório, sem bloquear nada que já estava bloqueado.
    for waiver in packet.waivers:
        issues.append(
            Issue(
                code=_issue_code(ISSUE_WAIVER_PREFIX, waiver.finding_code),
                severity=IssueSeverity.WARNING,
                status=IssueStatus.OPEN,
                message=_trim(
                    f"pendência mantida na conclusão ({waiver.finding_code}/{waiver.ref_key}):"
                    f" {waiver.justification}"
                ),
            )
        )

    scene = SceneRevision(
        job_id=field_scene_job_id(tenant_id=tenant_id, survey_id=survey_id),
        version=1,
        # `approved` e `accepted_approximation_ids` ficam no padrão: aprovação é ato humano
        # sobre uma revisão, e aceite de aproximação também. Este módulo não os escreve.
        entities=entities,
        measurements=measurements,
        issues=issues,
    )

    media_entries: list[dict[str, Any]] = []
    for anchor in packet.media_anchors:
        media_entries.append(
            _media_entry(
                role="media_anchor",
                anchor_id=anchor.id,
                media=media[anchor.media_ref.sha256],
                point_id=anchor.point_id,
                element_id=anchor.element_id,
                note_id=anchor.note_id,
                created_at=_instant(anchor.created_at),
            )
        )
    for note in packet.observations:
        if note.audio_media_ref is not None:
            media_entries.append(
                _media_entry(
                    role="observation_audio",
                    anchor_id=None,
                    media=media[note.audio_media_ref.sha256],
                    point_id=note.point_id,
                    element_id=note.element_id,
                    note_id=note.id,
                    created_at=_instant(note.created_at),
                )
            )
    if packet.arrival_context is not None and packet.arrival_context.access_media_ref is not None:
        media_entries.append(
            _media_entry(
                role="arrival_access",
                anchor_id=None,
                media=media[packet.arrival_context.access_media_ref.sha256],
                created_at=_instant(packet.arrival_context.arrived_at),
            )
        )

    attachments: dict[str, Any] = {
        "schema_version": ATTACHMENTS_SCHEMA_VERSION,
        "tenant_id": tenant_id,
        "survey_id": survey_id,
        "device_id": device_id,
        "name": packet.name,
        "order_id": packet.order_id,
        "scene_id": str(scene.id),
        "scene_job_id": str(scene.job_id),
        "scene_object_key": survey_scene_object_key(tenant_id=tenant_id, survey_id=survey_id),
        "media": media_entries,
        "notes": [_note_entry(note) for note in packet.observations],
        "arrival_context": (
            _arrival_entry(packet.arrival_context) if packet.arrival_context is not None else None
        ),
        "gps_fixes": [fix.model_dump(mode="json") for fix in packet.gps_fixes],
        "elements": [
            {"id": element.id, "label": element.label, "point_ids": list(element.point_ids)}
            for element in packet.elements
        ],
        "waivers": [
            {
                "id": waiver.id,
                "finding_code": waiver.finding_code,
                "ref_key": waiver.ref_key,
                "justification": waiver.justification,
                "issue_code": _issue_code(ISSUE_WAIVER_PREFIX, waiver.finding_code),
            }
            for waiver in packet.waivers
        ],
        # Elemento é agrupamento rotulado, não geometria: fica aqui inteiro, e a medida que
        # depende dele cai em `measurements_without_scene_entry` com o motivo.
        "measurements_without_scene_entry": unmapped,
    }
    return SurveyExportArtifacts(scene=scene, attachments=attachments)


def _pending(digest: str, media: Mapping[str, SurveyMediaObject]) -> bool:
    stored = media.get(digest)
    return stored is None or stored.status != SURVEY_MEDIA_CONFIRMED


def media_objects(rows: Iterable[Mapping[Any, Any]]) -> dict[str, SurveyMediaObject]:
    """Linhas de `survey_media_records` (já escopadas por tenant) indexadas por digest.

    `Mapping[Any, Any]` porque a linha chega como `RowMapping` do SQLAlchemy, cuja chave
    não é `str` para o type checker; este módulo não conhece o driver de banco.
    """
    return {
        str(row["sha256"]): SurveyMediaObject(
            sha256=str(row["sha256"]),
            mime_type=str(row["mime_type"]),
            byte_size=int(row["byte_size"]),
            object_key=str(row["object_key"]),
            status=str(row["status"]),
        )
        for row in rows
    }
