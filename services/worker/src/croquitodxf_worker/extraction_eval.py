"""Eval comparativa da extração de geometria por modelo, medida contra a tinta do papel.

Sem gabarito não existe recall honesto. O que dá para verificar é se a geometria proposta
cai sobre traço real, se as regiões que fecham no papel fecham na saída, e se os elementos
vieram rotulados. A comparação final entre providers é humana, olhando o diff.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from croquitodxf_worker.io_utils import atomic_write_text
from croquitodxf_worker.providers import (
    GeometryExtractionOutput,
    PromptTask,
    ProviderAdapter,
    build_request,
)
from croquitodxf_worker.vision import (
    PixelPolyline,
    VisionConfig,
    VisionProposal,
    corroborate_with_ink,
    proposals_from_geometry,
    register_to_ink,
)

TRANSMISSION_MAX_DIMENSION = 2400
"""Lado maior da imagem enviada; o provider recusa payload grande demais."""

TRANSMISSION_MAX_BYTES = 3_600_000
"""Limite de ~5 MB dos providers vale sobre o payload **base64**, que cresce um terço.

Medir os bytes binários deixaria passar uma imagem de 4 MB que vira 5,5 MB na transmissão
e é recusada com 400 — depois de o budget já ter sido reservado.
"""


class ExtractionNotAllowlistedError(RuntimeError):
    """O documento não está liberado para sair para um provider externo."""


def prepare_transmission(source: Path) -> tuple[bytes, int, int]:
    """Reduz a página para caber no limite do provider, sem mexer no mapeamento.

    O contrato devolve coordenadas normalizadas e a conversão multiplica pelas dimensões
    **originais**, então reduzir o que trafega não desloca a geometria de volta. Enviar a
    página de 22 MB apenas faria a chamada falhar depois de reservar budget.
    """
    from io import BytesIO

    from PIL import Image

    with Image.open(source) as image:
        original_width, original_height = image.size
        reduced = image.convert("RGB")
        reduced.thumbnail(
            (TRANSMISSION_MAX_DIMENSION, TRANSMISSION_MAX_DIMENSION),
            Image.Resampling.LANCZOS,
        )
        buffer = BytesIO()
        reduced.save(buffer, format="PNG", optimize=True)
        payload = buffer.getvalue()
        if len(payload) > TRANSMISSION_MAX_BYTES:
            buffer = BytesIO()
            reduced.save(buffer, format="JPEG", quality=88)
            payload = buffer.getvalue()
    return payload, original_width, original_height


@dataclass(frozen=True)
class ExtractionCandidate:
    """Um eixo de comparação: provider e modelo por trás do mesmo pedido."""

    name: str
    adapter: ProviderAdapter


class ProposalRegistrationReport(BaseModel):
    """Linha por proposta do antes/depois do registro, para a revisão olhar elemento a elemento.

    A média por eixo esconde o que importa: um ótimo agregado pode subir a taxa e ainda
    assim ter piorado um elemento que já estava certo. Aqui cada proposta declara as três
    coberturas, qual colocação virou base e que ajuste recebeu.
    """

    model_config = ConfigDict(extra="forbid")

    proposal_id: str
    label: str | None = None
    kind: str
    coverage_raw: float = Field(ge=0, le=1)
    coverage_global: float = Field(ge=0, le=1)
    coverage_refined: float = Field(ge=0, le=1)
    base: str
    refinement: str
    centre_shift_px: float = 0.0
    radius_delta_px: float = 0.0
    orientation_delta_degrees: float = 0.0
    # Contorno quase-retangular declara o deslocamento de cada aresta, na ordem topo, base,
    # esquerda e direita. É o que distingue corrigir o TAMANHO do elemento de empurrá-lo
    # inteiro, e sem os quatro números a revisão não consegue conferir o contorno na folha.
    edge_shifts_px: list[float] = Field(default_factory=list)
    # Linha declara quanto cada ponta deslizou ao longo da própria direção, na ordem início e
    # fim. É o que distingue a linha que andou da linha que era comprida demais.
    tip_shifts_px: list[float] = Field(default_factory=list)
    # O refino moveu o elemento por obrigação de ordem, não por ganho de tinta: a colocação
    # de base cruzava um vizinho paralelo já assentado.
    order_constrained: bool = False
    # Nenhuma colocação preservava a ordem traçada. A proposta é incompatível com as
    # vizinhas e isso vai para a revisão em vez de ser resolvido escolhendo um lado.
    order_unresolved: bool = False


class ExtractionArmReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    provider: str
    model_id: str
    prompt_version: str
    element_count: int = Field(ge=0)
    ink_coverage_mean: float = Field(ge=0, le=1)
    corroborated_rate: float = Field(ge=0, le=1)
    closed_region_count: int = Field(ge=0)
    labelled_rate: float = Field(ge=0, le=1)
    layered_rate: float = Field(ge=0, le=1)
    latency_ms: int = Field(ge=0)
    estimated_cost_usd: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    notes: list[str]
    # Só o registro preenche: a eval bruta não tem antes/depois para declarar.
    proposal_registration: list[ProposalRegistrationReport] = Field(default_factory=list)


class ExtractionEvalReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    image_sha256: str
    arms: list[ExtractionArmReport]
    thresholds: dict[str, float]
    passed: bool


def allowlisted_digests() -> frozenset[str]:
    return frozenset(
        digest.strip().lower()
        for digest in os.getenv("CROQUITODXF_AI_EXTRACTION_ALLOWED_DIGESTS", "").split(",")
        if digest.strip()
    )


def bind_page_to_document(manifest_path: Path, page_sha256: str) -> str:
    """Liga o render da página ao documento do manifest e devolve o digest de origem.

    É a metade **estrutural** de `authorize_page`: prova que o PNG que vai ser enviado é
    uma página daquele documento, e nada mais. Ela existe separada porque há mais de uma
    forma de consentimento no repositório — a allowlist por ambiente (`authorize_page`) e o
    ato de upload do próprio orçamentista no servidor local —, e as duas precisam do MESMO
    amarrado página↔documento antes de qualquer byte sair da máquina. Quem dispensa a
    allowlist não pode dispensar este vínculo: sem ele, um PNG largado no diretório viraria
    evidência de um documento que ninguém enviou.
    """
    manifest = json.loads(manifest_path.read_text())
    source_sha256 = str(manifest.get("source_sha256", "")).lower()
    if page_sha256.lower() not in {
        str(page.get("image_sha256", "")).lower() for page in manifest.get("pages", [])
    }:
        raise ExtractionNotAllowlistedError(
            "A imagem não pertence ao manifest informado: o render não pode ser ligado a "
            "um documento autorizado."
        )
    return source_sha256


def authorize_page(manifest_path: Path, page_sha256: str) -> str:
    """Liga o render da página ao documento autorizado e devolve o digest de origem.

    A allowlist vale sobre o **documento**, não sobre um PNG derivado dele: autorizar o
    render permitiria enviar qualquer imagem que alguém colocasse na pasta. É o mesmo
    amarrado que o `seed-review` faz entre evidência e upload.
    """
    source_sha256 = bind_page_to_document(manifest_path, page_sha256)
    if source_sha256 not in allowlisted_digests():
        raise ExtractionNotAllowlistedError(
            f"Documento fora da allowlist de extração ({source_sha256[:12]}…): defina "
            "CROQUITODXF_AI_EXTRACTION_ALLOWED_DIGESTS antes de enviar para um provider "
            "externo."
        )
    return source_sha256


def _coverage_stats(
    proposals: list[VisionProposal], minimum_coverage: float
) -> tuple[float, float]:
    total = len(proposals)
    if not total:
        return 0.0, 0.0
    coverages = [proposal.quality_score for proposal in proposals]
    corroborated = [value for value in coverages if value >= minimum_coverage]
    return round(sum(coverages) / total, 4), round(len(corroborated) / total, 4)


def _arm_report(
    candidate: ExtractionCandidate,
    proposals: list[VisionProposal],
    *,
    execution_provider: str,
    model_id: str,
    prompt_version: str,
    latency_ms: int,
    estimated_cost_usd: float | None,
    input_tokens: int | None,
    output_tokens: int | None,
    notes: list[str],
    minimum_coverage: float,
) -> ExtractionArmReport:
    total = len(proposals)
    ink_coverage_mean, corroborated_rate = _coverage_stats(proposals, minimum_coverage)
    return ExtractionArmReport(
        name=candidate.name,
        provider=execution_provider,
        model_id=model_id,
        prompt_version=prompt_version,
        element_count=total,
        ink_coverage_mean=ink_coverage_mean,
        corroborated_rate=corroborated_rate,
        closed_region_count=sum(
            1
            for proposal in proposals
            if isinstance(proposal.geometry, PixelPolyline) and proposal.geometry.closed
        ),
        labelled_rate=(
            round(sum(1 for item in proposals if item.label) / total, 4) if total else 0.0
        ),
        layered_rate=(
            round(sum(1 for item in proposals if item.layer_hint) / total, 4) if total else 0.0
        ),
        latency_ms=latency_ms,
        estimated_cost_usd=estimated_cost_usd,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        notes=notes,
    )


def run_extraction_eval(
    image_path: Path,
    candidates: list[ExtractionCandidate],
    output_dir: Path,
    *,
    manifest_path: Path,
    config: VisionConfig | None = None,
    minimum_corroborated_rate: float = 0.7,
) -> tuple[ExtractionEvalReport, Path]:
    """Roda o mesmo pedido em cada eixo e mede a saída contra a tinta do próprio croqui."""
    effective_config = config or VisionConfig()
    output_dir.mkdir(parents=True, exist_ok=True)
    source = image_path.resolve(strict=True)
    # A allowlist vale sobre o documento de origem; o lineage registra o que trafegou.
    image_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    authorize_page(manifest_path, image_sha256)

    payload, width, height = prepare_transmission(source)
    request = build_request(
        PromptTask.GEOMETRY_EXTRACTION,
        image_bytes=payload,
        image_sha256=hashlib.sha256(payload).hexdigest(),
        image_width_px=width,
        image_height_px=height,
        region_label="main_plan",
    )
    arms: list[ExtractionArmReport] = []
    for candidate in candidates:
        execution = candidate.adapter.execute(request)
        if not isinstance(execution.output, GeometryExtractionOutput):
            raise ValueError(f"{candidate.name} não devolveu contrato de geometria")
        proposals = proposals_from_geometry(
            execution.output.elements,
            image_digest=image_sha256,
            width=width,
            height=height,
        )
        corroborated, notes = corroborate_with_ink(proposals, source, config=effective_config)
        arms.append(
            _arm_report(
                candidate,
                corroborated,
                execution_provider=execution.provider.value,
                model_id=execution.model_id,
                prompt_version=execution.prompt.prompt_version,
                latency_ms=execution.latency_ms,
                estimated_cost_usd=(
                    float(execution.usage.estimated_cost_usd)
                    if execution.usage.estimated_cost_usd is not None
                    else None
                ),
                input_tokens=execution.usage.input_tokens,
                output_tokens=execution.usage.output_tokens,
                notes=notes,
                minimum_coverage=effective_config.ink_corroboration_min_coverage,
            )
        )
        atomic_write_text(
            output_dir / f"{candidate.name}-proposals.json",
            json.dumps(
                [item.model_dump(mode="json") for item in corroborated],
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )

    thresholds = {"corroborated_rate": minimum_corroborated_rate}
    report = ExtractionEvalReport(
        image_sha256=image_sha256,
        arms=arms,
        thresholds=thresholds,
        # Um eixo que propõe geometria sem tinta por baixo reprova: é o sinal de invenção.
        passed=bool(arms)
        and all(arm.corroborated_rate >= minimum_corroborated_rate for arm in arms),
    )
    report_path = output_dir / "extraction-eval.json"
    atomic_write_text(
        report_path,
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
    )
    return report, report_path


def register_extraction_arms(
    output_dir: Path,
    image_path: Path,
    *,
    config: VisionConfig | None = None,
) -> tuple[ExtractionEvalReport, Path]:
    """Assenta as propostas já pagas sobre a tinta e remede, sem nova chamada externa.

    Modelos de visão acertam a estrutura e erram o registro; `register_to_ink` corrige
    enquadramento (uma transformação global por eixo de comparação) e depois reassenta cada
    elemento sozinho dentro do ajuste que o tipo dele autoriza — sem poder inventar
    geometria. A taxa original fica preservada em nota e a tabela por proposta guarda o
    antes/depois de cada elemento, para o relatório continuar auditável linha a linha.
    """
    effective_config = config or VisionConfig()
    report_path = output_dir / "extraction-eval.json"
    report = ExtractionEvalReport.model_validate(json.loads(report_path.read_text()))
    source = image_path.resolve(strict=True)
    image_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    if image_sha256 != report.image_sha256:
        raise ValueError("imagem não corresponde ao relatório da eval: registro recusado")
    proposals_adapter = TypeAdapter(list[VisionProposal])
    minimum_coverage = effective_config.ink_corroboration_min_coverage
    arms: list[ExtractionArmReport] = []
    for arm in report.arms:
        proposals = proposals_adapter.validate_json(
            (output_dir / f"{arm.name}-proposals.json").read_text()
        )
        registered, registration = register_to_ink(proposals, source, config=effective_config)
        corroborated, notes = corroborate_with_ink(registered, source, config=effective_config)
        atomic_write_text(
            output_dir / f"{arm.name}-registered.json",
            json.dumps(
                [item.model_dump(mode="json") for item in corroborated],
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )
        ink_coverage_mean, corroborated_rate = _coverage_stats(corroborated, minimum_coverage)
        refined_count = sum(1 for item in registration.elements if item.refinement != "none")
        constrained_count = sum(1 for item in registration.elements if item.order_constrained)
        unresolved = [item.proposal_id for item in registration.elements if item.order_unresolved]
        arms.append(
            arm.model_copy(
                update={
                    "ink_coverage_mean": ink_coverage_mean,
                    "corroborated_rate": corroborated_rate,
                    "notes": [
                        *notes,
                        f"CORROBORATED_BEFORE_REGISTRATION:{arm.corroborated_rate}",
                        # `rot` é o ângulo realmente aplicado: quarto de volta mais o
                        # desvio fino. Registrar só o quarto esconderia a folha torta.
                        "REGISTERED:"
                        f"rot={round(registration.total_rotation_degrees, 4)};"
                        f"sx={round(registration.scale_x, 4)};"
                        f"sy={round(registration.scale_y, 4)};"
                        f"dx={round(registration.offset_x, 2)};"
                        f"dy={round(registration.offset_y, 2)}",
                        "REFINED:"
                        f"global={registration.coverage_after};"
                        f"refined={registration.coverage_refined};"
                        f"moved={refined_count}/{len(registration.elements)}",
                        # A ordem traçada é invariante do registro: quantos elementos a
                        # ordem obrigou a mover e quais ficaram sem colocação compatível.
                        "ORDER_GUARD:"
                        f"relocated={constrained_count}/{len(registration.elements)};"
                        f"unresolved={len(unresolved)}"
                        + (f":{','.join(unresolved)}" if unresolved else ""),
                    ],
                    "proposal_registration": [
                        ProposalRegistrationReport(
                            proposal_id=element.proposal_id,
                            label=element.label,
                            kind=element.kind,
                            coverage_raw=element.coverage_raw,
                            coverage_global=element.coverage_global,
                            coverage_refined=element.coverage_refined,
                            base=element.base,
                            refinement=element.refinement,
                            centre_shift_px=element.centre_shift_px,
                            radius_delta_px=element.radius_delta_px,
                            orientation_delta_degrees=element.orientation_delta_degrees,
                            # Vazio quando o ajuste não foi por aresta: quatro zeros num
                            # círculo sugeririam uma busca que não houve.
                            edge_shifts_px=(
                                list(element.edge_shifts_px)
                                if element.refinement == "edges"
                                else []
                            ),
                            tip_shifts_px=(
                                list(element.tip_shifts_px) if element.refinement == "tips" else []
                            ),
                            order_constrained=element.order_constrained,
                            order_unresolved=element.order_unresolved,
                        )
                        for element in registration.elements
                    ],
                }
            )
        )
    minimum_rate = report.thresholds.get("corroborated_rate", 0.7)
    updated = ExtractionEvalReport(
        image_sha256=report.image_sha256,
        arms=arms,
        thresholds=report.thresholds,
        passed=bool(arms) and all(arm.corroborated_rate >= minimum_rate for arm in arms),
    )
    atomic_write_text(
        report_path,
        json.dumps(updated.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
    )
    return updated, report_path
