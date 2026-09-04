"""Build a non-exportable review snapshot from explicitly injected provider fixtures."""

from __future__ import annotations

import hashlib
import logging
import math
import tempfile
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Final

from PIL import Image

from croquito_core.models import MeasurementKind, UnitCode
from croquito_worker.association import AssociationSet, associate_readings
from croquito_worker.page_orientation import (
    predominant_rotation,
    rotate_image_upright,
    rotate_normalized_box,
)
from croquito_worker.providers import (
    GeometryExtractionOutput,
    MeasurementExtractionOutput,
    MeasurementReadingOutput,
    NormalizedBox,
    OcrLineOutput,
    OcrOutput,
    PageSurveyOutput,
    PromptTask,
    ProviderAdapter,
    ProviderExecution,
    ProviderExecutionError,
    ProviderFailureCode,
    ProviderName,
    ProviderRequest,
    ProviderSuite,
    SurveyRegion,
    build_request,
)
from croquito_worker.review import (
    DimensionReading,
    EvidenceRegion,
    PixelBox,
    ProviderLineage,
    ReadingStatus,
    RegionCandidate,
    ReviewPacket,
)
from croquito_worker.vision import (
    VisionProposalSet,
    corroborate_with_ink,
    proposals_from_geometry,
    register_to_ink,
)

logger = logging.getLogger("croquito_worker.provider_review")


def _log_ocr_unavailable(failure_code: str) -> None:
    """Nomeia o motivo da degradação do OCR; a nota do pacote diz só que ela aconteceu.

    Sai apenas o código da falha (ou `ARM_NOT_CONFIGURED` quando o braço nem existe na
    suite). Nunca imagem, texto lido, cota ou credencial.
    """
    logger.warning(
        "ocr_unavailable failure_code=%s",
        failure_code,
        extra={"failure_code": failure_code},
    )


def _log_openai_arm_not_configured() -> None:
    """Diz ao operador que o braço OpenAI está DESLIGADO por configuração, não caído.

    O pacote traz `PROVIDER_FALLBACK_SINGLE_EXTRACTOR_ANTHROPIC` tanto quando a contraparte
    falha quanto quando ela nem existe na suite. Sem este rastro, "desligado por decisão
    humana" e "quebrou em produção" seriam a mesma linha no log — foi assim que o braço OCR
    atravessou um HML inteiro sem ninguém notar. Sai só o nome do braço e o motivo; nunca
    imagem, texto lido, cota ou credencial.
    """
    logger.warning(
        "provider_arm_unavailable arm=%s reason=%s",
        "openai",
        "ARM_NOT_CONFIGURED",
        extra={"arm": "openai", "reason": "ARM_NOT_CONFIGURED"},
    )


class ProviderContractError(ValueError):
    """A fixture or provider result violated the deterministic review boundary."""


@dataclass(frozen=True)
class ProviderReviewSnapshot:
    packet: ReviewPacket
    associations: AssociationSet
    proposals: VisionProposalSet
    source_image_bytes: bytes
    applied_rotation_ccw_degrees: int = 0
    """Quarto de volta anti-horário aplicado à página antes de qualquer chamada de modelo.

    Zero quando a folha já estava em pé, quando o OCR não opinou e quando o voto ficou
    indeciso. Diferente de zero significa que `source_image_bytes` NÃO são os bytes do
    preview recebido: são os bytes girados, e é sobre eles que o digest do pacote, as
    caixas das leituras, as propostas e a tela da revisão estão escritos.
    """

    executions: tuple[ProviderExecution, ...] = ()
    """Toda chamada de provider CONCLUÍDA nesta montagem, na ordem em que retornou.

    Existe para que quem persiste o resultado (`local_queue`) emita um
    `croquito.ai.call_executed.v1` por chamada, na mesma transação da revisão — este
    módulo não faz I/O e não conhece banco, então ele registra e não publica.

    Carrega só execuções que retornaram: a chamada que levantou `ProviderExecutionError`
    não produziu `ProviderExecution` e não vira evento nesta fatia. O `failure_code` do
    catálogo v1 fica reservado para quando o insumo da falha estiver modelado; hoje ela
    aparece nas notas de segurança do pacote e no log do operador, não no barramento.
    """


def _lineage(execution: ProviderExecution) -> ProviderLineage:
    return ProviderLineage(
        provider=execution.provider.value,
        model_id=execution.model_id,
        prompt_id=execution.prompt.prompt_id,
        prompt_version=execution.prompt.prompt_version,
        prompt_hash=execution.prompt.template_hash,
        schema_version=execution.prompt.schema_version,
        input_digest=execution.input_digest,
        latency_ms=execution.latency_ms,
        raw_response_ref=execution.raw_response_ref,
        input_tokens=execution.usage.input_tokens,
        output_tokens=execution.usage.output_tokens,
        estimated_cost_usd=execution.usage.estimated_cost_usd,
    )


def _reading_id(image_sha256: str, position: int) -> str:
    return f"rd_{hashlib.sha256(f'{image_sha256}:{position}'.encode()).hexdigest()[:16]}"


def _region_id(image_sha256: str, position: int) -> str:
    return f"rg_{hashlib.sha256(f'{image_sha256}:region:{position}'.encode()).hexdigest()[:16]}"


def _region_candidate(image_sha256: str, position: int, region: SurveyRegion) -> RegionCandidate:
    return RegionCandidate(
        id=_region_id(image_sha256, position),
        kind=region.kind,
        label=region.label,
        evidence=region.evidence,
        polygon=[(point.x, point.y) for point in region.polygon],
    )


def _pixel_box(
    *, left: float, top: float, right: float, bottom: float, width: int, height: int
) -> PixelBox:
    return PixelBox(
        left=max(0, int(left * width)),
        top=max(0, int(top * height)),
        right=min(width, max(1, int(right * width))),
        bottom=min(height, max(1, int(bottom * height))),
    )


def _measurement_kind(kind: str) -> MeasurementKind:
    try:
        return MeasurementKind(kind)
    except ValueError as error:
        raise ProviderContractError(f"tipo de medida fora do review packet: {kind}") from error


def _unit(unit: str) -> UnitCode:
    if unit == "m":
        return UnitCode.METRE
    if unit == "mm":
        return UnitCode.MILLIMETRE
    raise ProviderContractError(f"unidade fora do review packet: {unit}")


def _measurement_output(execution: ProviderExecution, label: str) -> MeasurementExtractionOutput:
    if not isinstance(execution.output, MeasurementExtractionOutput):
        raise ProviderContractError(f"{label} não retornou leituras de medida")
    return execution.output


def _execute_with_fallback(
    primary: ProviderAdapter,
    secondary: ProviderAdapter | None,
    request: ProviderRequest,
    notes: list[str],
    note_code: str,
) -> ProviderExecution:
    """Executa no braço primário e só degrada para o reserva depois de falha permanente.

    A degradação nunca é silenciosa: `note_code` entra nas notas de segurança do pacote,
    porque uma tarefa atendida pelo reserva é evidência de outra procedência — esconder a
    troca faria a revisão humana ler o pacote como se o braço escolhido tivesse respondido.

    Falha transitória não chega aqui: quem esgota retentativa é o `RetryingProviderAdapter`,
    e o que este helper recebe já é a exceção final. `BUDGET_EXCEEDED` também não descreve o
    braço, e sim o teto compartilhado do job: a chamada de reserva consumiria o mesmo teto
    sem chance nenhuma de sucesso, então re-levanta antes de qualquer tentativa.

    `secondary=None` é o braço reserva desligado por configuração: a falha do primário
    propaga exatamente como propaga quando os dois braços falham, e **nenhuma** nota de
    fallback é criada — não houve troca de braço para registrar, e uma nota dizendo o
    contrário faria a revisão procurar uma segunda procedência que não existe.
    """
    try:
        return primary.execute(request)
    except ProviderExecutionError as error:
        if error.code is ProviderFailureCode.BUDGET_EXCEEDED or secondary is None:
            raise
        execution = secondary.execute(request)
        notes.append(note_code)
        return execution


def _normalize_ocr_text(text: str) -> str:
    """Normalização mínima e nomeada para comparar leitura x linha de OCR.

    `strip` + colapso de espaços múltiplos + vírgula decimal -> ponto. Não mexe em caixa
    nem em pontuação fora do separador decimal: o alvo é a variação de digitação/OCR de
    número ("3,50" vs "3.50"), não correspondência aproximada de texto livre — isso
    esconderia falso-confirmado atrás de uma normalização agressiva demais.
    """
    return " ".join(text.strip().split()).replace(",", ".")


def _normalized_boxes_intersect(a: NormalizedBox, b: NormalizedBox) -> bool:
    """Interseção qualquer, nunca containment: texto rotacionado pelo OCR ainda deve bater
    contra a bbox de evidência da leitura (risco conhecido da T3)."""
    return a.left < b.right and b.left < a.right and a.top < b.bottom and b.top < a.bottom


def _reading_confirmed_by_ocr(
    observation: MeasurementReadingOutput, ocr_lines: Sequence[OcrLineOutput]
) -> bool:
    """Confirma uma leitura contra o que o OCR encontrou na mesma região da folha.

    Match textual normalizado **e** interseção espacial de bbox: texto repetido em dois
    pontos da prancha (a mesma cota redesenhada, por exemplo) não pode confirmar só pelo
    texto — é exatamente o falso-confirmado que o risco conhecido da T3 descreve. `bbox`
    é campo obrigatório de `MeasurementReadingOutput` neste contrato (nunca ausente), então
    o caminho "sem bbox, só texto conta" previsto na task não tem estado alcançável aqui e
    não foi implementado; um `if` morto sem forma de testar seria pior do que documentá-lo.
    """
    normalized_reading = _normalize_ocr_text(observation.raw_text)
    return any(
        _normalize_ocr_text(line.raw_text) == normalized_reading
        and _normalized_boxes_intersect(observation.bbox, line.bbox)
        for line in ocr_lines
    )


READING_MATCH_MAX_CENTER_DISTANCE: Final = 0.05
"""Distância máxima, em coordenadas normalizadas, entre os centros de duas leituras pareadas.

Medida na primeira prancha real com os dois braços vivos (V6, 2026-08-19): a âncora leu 36
cotas, a contraparte 24, e o pareamento POR POSIÇÃO acertou 0 de 36 — cada braço varre a
folha na sua ordem, então o índice não descreve nada. O que descreve é o lugar: dois braços
lendo a MESMA cota recortam quase o mesmo pedaço da página, e a diferença entre os recortes
é de poucos por cento; duas cotas DIFERENTES da mesma prancha quase nunca ficam a menos de
5% de distância uma da outra — e quando ficam, o guloso escolhe a mais próxima.

5% é do espaço normalizado, que é anisotrópico: numa página larga o mesmo número vale mais
milímetros na horizontal do que na vertical. É tolerância de pareamento, não de medida —
nenhum valor é arredondado por causa dela, e par casado com valor diferente vira divergência
explícita, nunca acordo.
"""


def _bbox_center(box: NormalizedBox) -> tuple[float, float]:
    return ((box.left + box.right) / 2, (box.top + box.bottom) / 2)


def _center_distance(a: NormalizedBox, b: NormalizedBox) -> float:
    (ax, ay), (bx, by) = _bbox_center(a), _bbox_center(b)
    return math.hypot(ax - bx, ay - by)


def pair_readings_by_evidence(
    anchor: Sequence[MeasurementReadingOutput],
    counterpart: Sequence[MeasurementReadingOutput],
) -> list[tuple[MeasurementReadingOutput, MeasurementReadingOutput | None]]:
    """Casa leitura de âncora com leitura de contraparte pelo LUGAR na folha, não pela ordem.

    Guloso do par mais próximo primeiro, um-para-um: o melhor par global é fechado, os dois
    lados saem do jogo, e repete-se com o que sobrou. Assim a decisão não depende da ordem em
    que os braços listaram as cotas — que é justamente a variável que o pareamento posicional
    confundia com identidade.

    Devolve UMA entrada por leitura da âncora, na ordem da âncora, com `None` quando nada
    ficou dentro de `READING_MATCH_MAX_CENTER_DISTANCE`. Leitura da contraparte sem par não
    aparece aqui: a âncora manda no pacote, e o que só o outro braço viu é contado como
    sobra pelo chamador. Função pura: não lê provider, não decide status e não altera nada.
    """
    candidates = sorted(
        (
            (_center_distance(first.bbox, second.bbox), i, j)
            for i, first in enumerate(anchor)
            for j, second in enumerate(counterpart)
            if _center_distance(first.bbox, second.bbox) <= READING_MATCH_MAX_CENTER_DISTANCE
        ),
        # Empate resolvido pela ordem das listas: pareamento precisa ser determinístico.
        key=lambda candidate: (candidate[0], candidate[1], candidate[2]),
    )
    matched: dict[int, int] = {}
    taken: set[int] = set()
    for _distance, i, j in candidates:
        if i in matched or j in taken:
            continue
        matched[i] = j
        taken.add(j)
    return [
        (reading, counterpart[matched[i]] if i in matched else None)
        for i, reading in enumerate(anchor)
    ]


def _unit_abstention(
    observation: MeasurementReadingOutput, counterpart: MeasurementReadingOutput | None
) -> bool:
    """A contraparte não escreveu unidade e a âncora escreveu: abstenção, não contradição.

    Só este sentido conta. Âncora `unknown` contra contraparte concreta NÃO é abstenção aqui,
    e nem chega a importar: `_unit` recusa `unknown`, então a leitura da âncora sai do laço
    com `READING_{n}_UNSUPPORTED_UNIT_OR_KIND` e nunca vira `DimensionReading` — a unidade que
    fica no pacote é sempre a da âncora, e ela precisa ser concreta.
    """
    return (
        counterpart is not None and counterpart.unit == "unknown" and observation.unit != "unknown"
    )


def _readings_agree(
    observation: MeasurementReadingOutput, counterpart: MeasurementReadingOutput | None
) -> bool:
    """Concordância entre um par casado: mesmo valor, e unidade compatível — nada além disso.

    `kind` fica de fora de propósito. No V6 o mesmo 25,90 saiu `length` num braço e `width`
    no outro: mesmo lugar, mesmo número, mesma unidade — a mesma cota, com rótulo diferente.
    Deixar a classificação derrubar a concordância transformava divergência de vocabulário em
    divergência de medida (a divergência vira nota `READING_{n}_KIND_DIVERGENCE`, e o `kind`
    da âncora prevalece). `target_hint` sai pelo mesmo motivo, e mais forte ainda: é texto
    livre, dois braços quase nunca o escrevem igual.

    O valor é comparado como `Decimal`, que o contrato já produz tanto de string quanto de
    número, e cuja igualdade é numérica: "25,90" e 25.9 são o mesmo valor. Nenhuma tolerância
    é aplicada ao número — medida não é arredondada aqui. `None` nunca concorda: ausência de
    valor não é acordo sobre valor.

    **Abstenção de unidade não é contradição** (V11, 2026-08-19, primeira prancha real com os
    dois braços vivos). O croqui não escreve unidade em cota nenhuma; o prompt manda "use
    unknown or null when evidence is absent" e o Sol obedece à risca — declarou `unit`
    `"unknown"` nas 9 leituras —, enquanto o Claude infere `m` da convenção de obra. Exigir
    unidade IGUAL fazia a contraparte calada derrubar 7 pares cujo VALOR concordava, e o
    pacote saiu com zero leitura `proposed`. Quem não escreveu unidade não afirmou outra
    unidade: com o mesmo valor, o par concorda, e a nota `READING_{n}_UNIT_ABSTENTION`
    registra que o valor tem duas testemunhas e a unidade tem uma.

    Isso não afrouxa a comparação de unidades escritas: `m` contra `cm` continua divergência
    (`READING_{n}_PROVIDER_DISAGREEMENT`, leitura ambígua), porque aí os dois braços
    afirmaram, e afirmaram coisas diferentes. Dois `unknown` seguem concordando como qualquer
    par de unidades iguais.
    """
    if counterpart is None:
        return False
    if observation.normalized_value is None or counterpart.normalized_value is None:
        return False
    if observation.unit != counterpart.unit and not _unit_abstention(observation, counterpart):
        return False
    return Decimal(observation.normalized_value) == Decimal(counterpart.normalized_value)


def _execute_page_ocr(
    suite: ProviderSuite,
    *,
    image_bytes: bytes,
    image_sha256: str,
    width: int,
    height: int,
    executions: list[ProviderExecution],
) -> tuple[list[OcrLineOutput], bool]:
    """Roda o braço de OCR uma vez sobre a página como ela chegou, e devolve o que ele leu.

    Uma chamada por snapshot: o resultado serve à decisão de orientação **e** à
    corroboração das leituras mais adiante. Duas chamadas custariam duas vezes para
    responder a mesma pergunta.

    O tratamento de falha é o que já valia para a corroboração: `BUDGET_EXCEEDED` propaga
    (descreve o teto do job, não o braço); qualquer outra falha permanente degrada com log
    de operador e `ocr_ran=False`, sem nota — a nota `OCR_UNAVAILABLE` continua sendo
    decidida lá na frente, onde se sabe se havia leitura para conferir.

    O `input_digest` desta execução é o digest da folha COMO CHEGOU, mesmo quando a página
    é girada logo depois: foi essa imagem que saiu para o provider, e o lineage descreve o
    que foi enviado, não o que veio a ser a evidência.
    """
    if suite.ocr is None:
        # Braço ausente e braço que falhou são a mesma degradação para o revisor; só o log
        # distingue os dois. O aviso sai uma vez por snapshot, como o do braço OpenAI.
        _log_ocr_unavailable("ARM_NOT_CONFIGURED")
        return [], False
    try:
        execution = suite.ocr.execute(
            build_request(
                PromptTask.OCR,
                image_bytes=image_bytes,
                image_sha256=image_sha256,
                image_width_px=width,
                image_height_px=height,
                region_label="main_plan",
            )
        )
    except ProviderExecutionError as error:
        if error.code is ProviderFailureCode.BUDGET_EXCEEDED:
            raise
        _log_ocr_unavailable(error.code.value)
        return [], False
    executions.append(execution)
    if not isinstance(execution.output, OcrOutput):
        raise ProviderContractError("OCR não retornou contrato de OCR")
    return list(execution.output.lines), True


@contextmanager
def _ink_source(image_path: Path, image_bytes: bytes, applied_rotation: int) -> Iterator[Path]:
    """Caminho da imagem que a corroboração de tinta deve ler.

    `register_to_ink`/`corroborate_with_ink` leem do disco, e a folha girada só existe em
    memória. Sem este desvio, as propostas — que o modelo produziu olhando a folha em pé —
    seriam medidas contra a tinta da folha deitada, e todo elemento sairia sem corroboração.
    Sem rotação, o arquivo original é usado como sempre e nada é copiado.
    """
    if applied_rotation == 0:
        yield image_path
        return
    with tempfile.NamedTemporaryFile(suffix=".png") as rotated_file:
        rotated_file.write(image_bytes)
        rotated_file.flush()
        yield Path(rotated_file.name)


def build_provider_review_snapshot(
    image_path: Path,
    *,
    dataset_id: str,
    suite: ProviderSuite,
) -> ProviderReviewSnapshot:
    """Execute the fixture path without granting any provider result geometric authority."""
    source_image_bytes = image_path.read_bytes()
    image_sha256 = hashlib.sha256(source_image_bytes).hexdigest()
    with Image.open(image_path) as source_image:
        width, height = source_image.size

    # Anthropic é o braço primário de toda tarefa com escolha; OpenAI é o reserva e a
    # contraparte da comparação. As notas de fallback acompanham o pacote até o fim,
    # inclusive quando a página nem chega à extração. Com o braço reserva desligado por
    # configuração (`openai=None`), toda tarefa roda só no primário: não há reserva para
    # assumir survey/geometria e não há contraparte para comparar a medida.
    openai_arm = suite.openai
    if openai_arm is None:
        # Uma vez por snapshot, e não por tarefa: o braço desligado atravessa survey,
        # extração e geometria, e repetir o aviso três vezes transformaria uma decisão de
        # configuração em ruído de log.
        _log_openai_arm_not_configured()
    fallback_notes: list[str] = []
    # Toda execução concluída é anotada aqui, imediatamente depois de retornar, para que o
    # caller emita um evento por chamada. Anotar no ponto de retorno (e não no fim) é o que
    # faz o registro sobreviver aos caminhos que devolvem o snapshot mais cedo.
    executions: list[ProviderExecution] = []
    # O OCR é a PRIMEIRA chamada do snapshot porque é ele que diz se a folha está deitada,
    # e a folha precisa estar em pé antes de qualquer modelo olhar para ela. O preço dessa
    # ordem é declarado: o OCR passou a rodar mesmo quando o job morre antes da extração —
    # página com classificação ambígua, ou sem leitura nenhuma — o que custa ~US$ 0,0015
    # por página que antes não custava nada. É o preço de decidir a orientação antes de
    # qualquer chamada de LLM, que custa duas ordens de grandeza mais.
    ocr_lines, ocr_ran = _execute_page_ocr(
        suite,
        image_bytes=source_image_bytes,
        image_sha256=image_sha256,
        width=width,
        height=height,
        executions=executions,
    )
    rotation_notes: list[str] = []
    applied_rotation = 0
    if ocr_ran:
        vote = predominant_rotation(ocr_lines)
        if vote.decided and vote.rotation_ccw_degrees != 0:
            applied_rotation = vote.rotation_ccw_degrees
            # A partir daqui a folha girada É a evidência: o digest, as dimensões, o que
            # todo braço recebe, o que a corroboração de tinta mede e o que a revisão
            # humana vê. Nenhum consumidor transforma coordenada — eles leem a mesma
            # imagem, como já liam.
            source_image_bytes, width, height = rotate_image_upright(
                source_image_bytes, applied_rotation
            )
            image_sha256 = hashlib.sha256(source_image_bytes).hexdigest()
            # As linhas do OCR foram lidas na folha deitada; a corroboração compara a bbox
            # delas com a bbox das leituras, que virão do modelo já no espaço girado.
            ocr_lines = [
                line.model_copy(update={"bbox": rotate_normalized_box(line.bbox, applied_rotation)})
                for line in ocr_lines
            ]
            rotation_notes.append(f"PAGE_ROTATED_{applied_rotation}CCW_FROM_OCR_ORIENTATION")

    def request(task: PromptTask) -> ProviderRequest:
        return build_request(
            task,
            image_bytes=source_image_bytes,
            image_sha256=image_sha256,
            image_width_px=width,
            image_height_px=height,
            region_label="main_plan",
        )

    survey = _execute_with_fallback(
        suite.anthropic,
        openai_arm,
        request(PromptTask.PAGE_SURVEY),
        fallback_notes,
        "PROVIDER_FALLBACK_PAGE_SURVEY_OPENAI",
    )
    executions.append(survey)
    if not isinstance(survey.output, PageSurveyOutput) or not survey.output.regions:
        raise ProviderContractError("page survey não retornou região utilizável")
    region_candidates = [
        _region_candidate(image_sha256, position, region)
        for position, region in enumerate(survey.output.regions, start=1)
    ]
    main_plans = [region for region in region_candidates if region.kind == "main_plan"]
    if len(main_plans) != 1:
        packet = ReviewPacket(
            dataset_id=dataset_id,
            page_number=1,
            image_sha256=image_sha256,
            region_candidates=region_candidates,
            readings=[],
            safety_notes=[
                "REGION_CLASSIFICATION_REQUIRED",
                "Nenhuma região foi escolhida automaticamente para extração externa.",
                *rotation_notes,
                *fallback_notes,
            ],
        )
        return ProviderReviewSnapshot(
            packet=packet,
            associations=AssociationSet(
                dataset_id=dataset_id,
                page_number=1,
                image_sha256=image_sha256,
                candidates=[],
                unassociated_reading_ids=[],
                safety_notes=[
                    *packet.safety_notes,
                    "Associações não são calculadas antes da classificação humana.",
                ],
            ),
            proposals=VisionProposalSet(
                dataset_id=dataset_id,
                page_number=1,
                image_sha256=image_sha256,
                image_width_px=width,
                image_height_px=height,
                configured_limits={"line": 80, "circle": 16, "contour": 16},
                limit_reached=[],
                proposals=[],
                safety_notes=[
                    *packet.safety_notes,
                    "Propostas geométricas não são promovidas antes da classificação humana.",
                ],
            ),
            # A folha girada é o que o humano vai classificar: devolver aqui os bytes
            # originais faria a tela mostrar deitada a mesma página que o survey leu em pé.
            source_image_bytes=source_image_bytes,
            applied_rotation_ccw_degrees=applied_rotation,
            executions=tuple(executions),
        )
    # Os dois braços são chamados de propósito: a extração dupla é a comparação. Por isso
    # a captura é individual, e não pelo helper de fallback — um braço caído degrada o
    # modo, não substitui o outro. Com o braço reserva desligado, a contraparte nem é
    # chamada: braço ausente não gasta teto nem produz observação.
    extraction_request = request(PromptTask.MEASUREMENT_EXTRACTION)
    anthropic_extraction: ProviderExecution | None
    openai_extraction: ProviderExecution | None
    try:
        anthropic_extraction = suite.anthropic.execute(extraction_request)
    except ProviderExecutionError as error:
        # Engolir a falha aqui só faz sentido quando existe contraparte para virar âncora.
        # Sem ela, o erro do único braço vivo propaga já, e o job volta para reentrega.
        if error.code is ProviderFailureCode.BUDGET_EXCEEDED or openai_arm is None:
            raise
        anthropic_extraction = None
    else:
        executions.append(anthropic_extraction)
    if openai_arm is None:
        openai_extraction = None
    else:
        try:
            openai_extraction = openai_arm.execute(extraction_request)
        except ProviderExecutionError as error:
            # Sem nenhum sobrevivente não existe leitura observada: reentregar o job é mais
            # honesto do que devolver um pacote de revisão vazio como se a página não
            # tivesse cota nenhuma.
            if error.code is ProviderFailureCode.BUDGET_EXCEEDED or anthropic_extraction is None:
                raise
            openai_extraction = None
        else:
            executions.append(openai_extraction)
    anchor: ProviderExecution
    counterpart_execution: ProviderExecution | None
    if anthropic_extraction is not None:
        anchor = anthropic_extraction
        anchor_output = _measurement_output(anthropic_extraction, "Claude")
        counterpart_execution = openai_extraction
        counterpart_output = (
            _measurement_output(openai_extraction, "OpenAI")
            if openai_extraction is not None
            else None
        )
    elif openai_extraction is not None:
        anchor = openai_extraction
        anchor_output = _measurement_output(openai_extraction, "OpenAI")
        counterpart_execution = None
        counterpart_output = None
    else:
        raise ProviderContractError("nenhum braço de extração sobreviveu")
    dual = counterpart_execution is not None and counterpart_output is not None
    readings: list[DimensionReading] = []
    safety_notes = [
        "Leituras dos dois providers são observações; revisão humana é obrigatória."
        if dual
        else "Leitura de um braço único sem comparação; revisão humana é obrigatória.",
        "Nenhuma leitura cria geometria métrica ou libera exportação.",
        *rotation_notes,
        *fallback_notes,
    ]
    if not dual:
        # Sem contraparte não existe leitura concordante: a nota nomeia quem respondeu e
        # toda leitura nasce ambígua mais abaixo. Contraparte caída e contraparte desligada
        # por configuração produzem a MESMA nota de propósito — para a revisão humana, o
        # que muda o valor da leitura é ter uma testemunha só, não o motivo disso; o motivo
        # está no log do operador (`provider_arm_unavailable`).
        safety_notes.append(
            "PROVIDER_FALLBACK_SINGLE_EXTRACTOR_ANTHROPIC"
            if anchor.provider is ProviderName.ANTHROPIC
            else "PROVIDER_FALLBACK_SINGLE_EXTRACTOR_OPENAI"
        )
    counterpart_readings = counterpart_output.readings if counterpart_output is not None else []
    if dual and len(anchor_output.readings) != len(counterpart_readings):
        safety_notes.append("PROVIDER_READING_COUNT_DISAGREEMENT")
    # Pareamento por evidência espacial. O índice da lista nunca foi identidade de cota: cada
    # braço varre a folha na sua ordem, e no V6 o pareamento posicional acertou 0 de 36.
    pairs: list[tuple[MeasurementReadingOutput, MeasurementReadingOutput | None]] = (
        pair_readings_by_evidence(anchor_output.readings, counterpart_readings)
        if dual
        else [(reading, None) for reading in anchor_output.readings]
    )
    unmatched_counterparts = len(counterpart_readings) - sum(
        1 for _, matched in pairs if matched is not None
    )
    if dual and unmatched_counterparts:
        # O pacote é da âncora: cota que só a contraparte viu não entra. Mas o revisor
        # precisa saber quantas ficaram de fora — silêncio aqui vira folha meio lida.
        safety_notes.append(f"PROVIDER_UNMATCHED_COUNTERPART_READINGS:{unmatched_counterparts}")
    # A proveniência precisa dizer quem realmente leu. Um rótulo fixo, ou o par mesmo com
    # um braço caído, esconderia que a leitura saiu de uma única observação.
    if counterpart_execution is None:
        extractor = anchor.provider.value
        extractor_version = anchor.model_id
        lineage = [_lineage(anchor)]
    else:
        extractor = f"{anchor.provider.value}+{counterpart_execution.provider.value}"
        extractor_version = f"{anchor.model_id}+{counterpart_execution.model_id}"
        lineage = [_lineage(anchor), _lineage(counterpart_execution)]
    # Corroboração por OCR determinístico: reusa a ÚNICA execução do começo do snapshot —
    # a mesma que decidiu a orientação —, então nenhuma chamada paga é repetida aqui. As
    # linhas já estão no espaço da folha vigente (giradas junto com a página quando ela
    # girou), que é o mesmo espaço das bboxes que o modelo devolveu.
    #
    # A nota, essa sim, continua condicionada à existência de leitura para conferir: sem
    # leitura não há conferência que tenha deixado de acontecer. `suite.ocr is None` e
    # falha permanente do OCR têm o MESMO tratamento (nota única `OCR_UNAVAILABLE`, pacote
    # segue normal); o motivo de cada um está no log do operador, emitido lá no começo.
    if anchor_output.readings and not ocr_ran:
        safety_notes.append("OCR_UNAVAILABLE")
    for position, (observation, counterpart) in enumerate(pairs, start=1):
        if observation.normalized_value is None:
            # Recado sem valor é insumo da rodada seguinte (quantos "note" o modelo
            # emitiu sem número), não o mesmo silêncio do caso geral incompleto.
            safety_notes.append(
                f"READING_{position}_NOTE_WITHOUT_VALUE"
                if observation.kind == "note"
                else f"READING_{position}_INCOMPLETE"
            )
            continue
        if observation.target_hint is None:
            # Hint é dica de leitura, não amarração: a associação explícita do revisor usa
            # candidatos por proximidade (association.py), nunca o hint. Valor presente
            # entra no pacote como status ambíguo normal; a nota avisa a ausência em vez
            # de descartar a leitura (F-024).
            safety_notes.append(f"READING_{position}_WITHOUT_TARGET_HINT")
        target_hint = observation.target_hint
        annotation_suggested = observation.kind == "note"
        try:
            unit = _unit(observation.unit)
            # kind="note" completo é recado da folha, não cota: o eixo é irrelevante
            # para anotação, e LENGTH é o kind neutro que nunca cria constraint sem
            # eixo no traçado. count/unknown seguem rejeitados por _measurement_kind.
            kind = (
                MeasurementKind.LENGTH
                if annotation_suggested
                else _measurement_kind(observation.kind)
            )
        except ProviderContractError:
            safety_notes.append(f"READING_{position}_UNSUPPORTED_UNIT_OR_KIND")
            continue
        # Sem par não há corroboração: a leitura da âncora segue sozinha e ambígua, como
        # já valia quando a contraparte não existia naquela posição.
        disagreed = dual and not _readings_agree(observation, counterpart)
        if disagreed:
            safety_notes.append(f"READING_{position}_PROVIDER_DISAGREEMENT")
        elif dual and counterpart is not None and counterpart.kind != observation.kind:
            # Mesmo lugar, mesmo valor, unidade compatível e rótulo diferente: a cota é a
            # mesma e o `kind` da âncora prevalece, mas a divergência de classificação fica
            # visível.
            safety_notes.append(f"READING_{position}_KIND_DIVERGENCE")
        if dual and not disagreed and _unit_abstention(observation, counterpart):
            # Nota própria, fora do encadeamento acima de propósito: ela não substitui a
            # divergência de `kind`, coexiste com ela. O par concordou, mas quem leu a
            # unidade foi só a âncora — o revisor precisa ver o valor com duas testemunhas
            # e a unidade com uma.
            safety_notes.append(f"READING_{position}_UNIT_ABSTENTION")
        # Calculada uma vez por leitura e usada nas duas saídas (nota posicional e campo
        # da leitura): None quando o braço não rodou (ausente ou falhou), nunca recalculada
        # depois — ver `_reading_confirmed_by_ocr` para o critério de match.
        confirmed = _reading_confirmed_by_ocr(observation, ocr_lines) if ocr_ran else None
        if ocr_ran:
            # Confirmada ou não, a nota é o dado — o status NUNCA é rebaixado por falha de
            # OCR (rotação, normalização): calibrar o status a partir disso é da F-010, não
            # desta entrega.
            safety_notes.append(
                f"READING_{position}_OCR_CONFIRMED"
                if confirmed
                else f"READING_{position}_OCR_EVIDENCE_MISSING"
            )
        readings.append(
            DimensionReading(
                id=_reading_id(image_sha256, position),
                evidence=EvidenceRegion(
                    dataset_id=dataset_id,
                    page_number=1,
                    image_sha256=image_sha256,
                    bbox=_pixel_box(
                        left=observation.bbox.left,
                        top=observation.bbox.top,
                        right=observation.bbox.right,
                        bottom=observation.bbox.bottom,
                        width=width,
                        height=height,
                    ),
                ),
                raw_text=observation.raw_text,
                value_si=Decimal(observation.normalized_value),
                unit=unit,
                kind=kind,
                written_decimals=observation.written_precision,
                target_hint=(
                    f"{target_hint.entity_label}: {target_hint.feature}"
                    if target_hint is not None
                    else None
                ),
                extractor=extractor,
                extractor_version=extractor_version,
                provider_lineage=lineage,
                annotation_suggested=annotation_suggested,
                ocr_corroborated=confirmed,
                # Sem comparação dupla não existe leitura `proposed`: o que um único braço
                # entrega é observação sem corroboração, e a revisão precisa ver isso.
                status=(
                    ReadingStatus.AMBIGUOUS
                    if not dual or observation.legibility != "clear" or disagreed
                    else ReadingStatus.PROPOSED
                ),
            )
        )
    # Geometria vem do modelo, não da bbox do texto. Fabricar linha a partir do recorte
    # de uma cota nunca foi observação do desenho: era um marcador com forma de geometria.
    # O pacote só é montado depois dela para que a nota de fallback da geometria chegue às
    # notas de segurança em vez de morrer no caminho.
    geometry_execution = _execute_with_fallback(
        suite.anthropic,
        openai_arm,
        request(PromptTask.GEOMETRY_EXTRACTION),
        safety_notes,
        "PROVIDER_FALLBACK_GEOMETRY_EXTRACTION_OPENAI",
    )
    executions.append(geometry_execution)
    if not isinstance(geometry_execution.output, GeometryExtractionOutput):
        raise ProviderContractError("extração de geometria não retornou contrato de geometria")
    proposals_list = proposals_from_geometry(
        geometry_execution.output.elements,
        image_digest=image_sha256,
        width=width,
        height=height,
    )
    proposal_notes = [
        "Geometria proposta por modelo; nenhuma medida vem dela.",
        "Toda proposta continua unresolved e não exportável até decisão humana.",
        "Seleção humana exige calibração explícita antes de criar rascunho approximate.",
    ]
    if proposals_list:
        # Registro assenta o conjunto e depois cada elemento sobre a tinta; a conferência
        # mede o que sobrou. A nota declara os três estágios: esconder o refino faria a
        # revisão acreditar que só houve deslocamento global.
        with _ink_source(image_path, source_image_bytes, applied_rotation) as ink_path:
            proposals_list, registration = register_to_ink(proposals_list, ink_path)
            proposals_list, ink_notes = corroborate_with_ink(proposals_list, ink_path)
        proposal_notes.append(
            f"INK_REGISTRATION:{registration.coverage_before:.3f}"
            f"->{registration.coverage_after:.3f}"
            f"->{registration.coverage_refined:.3f}"
        )
        proposal_notes.extend(ink_notes)
    proposals = VisionProposalSet(
        dataset_id=dataset_id,
        page_number=1,
        image_sha256=image_sha256,
        image_width_px=width,
        image_height_px=height,
        configured_limits={"line": 80, "circle": 16, "contour": 16},
        limit_reached=[],
        proposals=proposals_list,
        safety_notes=proposal_notes,
    )
    packet = ReviewPacket(
        dataset_id=dataset_id,
        page_number=1,
        image_sha256=image_sha256,
        region_candidates=region_candidates,
        readings=readings,
        safety_notes=safety_notes,
    )
    # Associação por proximidade real entre o recorte da cota e a geometria observada,
    # em vez do par sintético 1:1 que a fabricação produzia.
    associations = associate_readings(packet, proposals)
    return ProviderReviewSnapshot(
        packet=packet,
        associations=associations,
        proposals=proposals,
        source_image_bytes=source_image_bytes,
        applied_rotation_ccw_degrees=applied_rotation,
        executions=tuple(executions),
    )
