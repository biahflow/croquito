"""Prancha do projetista: validação do upload, ingestão local e extração paga da legenda.

Aqui mora o que acontece ENTRE o arquivo que o orçamentista enviou e o pacote de takeoff
que a tela revisa: recusar o que não é prancha, promover a página 1 com o manifest da
ingestão, montar o braço pago e extrair a legenda com o consentimento amarrado ao
documento enviado. O diretório de trabalho é um `Path` explícito (`workdir`) — este módulo
não conhece a rodada do servidor local, e por isso serve igual ao adaptador que vier
depois (a API `/v1`, ADR-0028).

Os freios da chamada paga são todos declarados e ficam DESTE lado:

- sem teto de gasto no ambiente do processo (`AI_BUDGET_ENV`) a extração é `unavailable` e
  **nunca** é tentada — a pré-checagem roda antes de qualquer byte sair da máquina;
- braço `fixture` é recusado: observação fabricada não vira pacote de rodada;
- o consentimento é o upload, e o digest do documento enviado é amarrado à página
  renderizada (`authorize_uploaded_page`), então um PNG largado no diretório não vira
  evidência de um documento que ninguém enviou.

Recusa sai como `ValuationValidationError` com o código estável de sempre; quem traduz
para HTTP é o adaptador.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Final

from croquito_valuation.catalog import file_sha256
from croquito_valuation.errors import ValuationValidationError
from croquito_worker.extraction_eval import bind_page_to_document
from croquito_worker.ingest import PdfManifest, ingest_pdf
from croquito_worker.io_utils import atomic_write_bytes
from croquito_worker.providers import (
    LegendExtractionOutput,
    ProviderAdapter,
    ProviderExecution,
    ProviderExecutionError,
    ProviderFailureCode,
    build_extraction_arm,
)
from croquito_worker.valuation.legend_extraction import (
    LegendExtractionResult,
    build_legend_request,
    extractor_label,
    takeoff_packet_from_legend,
)
from croquito_worker.valuation.legend_registration import (
    LegendRegistrationReport,
    register_legend_bboxes,
)

PLATE_PDF_FILENAME: Final = "prancha-origem.pdf"
"""PDF do projetista como ele chegou. Artefato local, fora do Git, retenção de 7 dias."""

PLATE_MANIFEST_FILENAME: Final = "manifest.json"
"""Manifest da ingestão: amarra a página promovida ao documento que o revisor enviou."""

MAX_PLATE_PDF_BYTES: Final = 50 * 1024 * 1024
"""Teto do upload. Prancha de projetista real fica bem abaixo; acima disso é engano."""

PLATE_INGEST_DPI: Final = 200
PLATE_INGEST_ROLE: Final = "legenda-quantificada"
PLATE_PAGE_NUMBER: Final = 1
"""Uma rodada é uma prancha, e a prancha é a página 1.

PDF com mais páginas não é recusado nem lido às escondidas: a página 1 é promovida e a
contagem vai declarada no estado, para o orçamentista saber o que ficou de fora."""

MEDICAO_EXTRACTION_ARM: Final = "sonnet=anthropic:claude-sonnet-5"
"""Braço pago da extração automática: o vencedor da eval paga de 2026-08-13.

Ele é constante e não flag de rota justamente porque trocar de modelo é mudança de IA —
exige eval comparativa e plano de rollback (`docs/ai/MODEL_ROUTING.md`). A variável de
ambiente abaixo existe para a próxima rodada de eval, não para escolher modelo por gosto.
"""

EXTRACTION_ARM_ENV: Final = "CROQUITO_MEDICAO_EXTRACTION_ARM"
AI_BUDGET_ENV: Final = "CROQUITO_AI_MAX_ESTIMATED_COST_USD"

_PROVIDER_CREDENTIAL_ENV: Final[Mapping[str, str]] = {
    "anthropic": "CROQUITO_ANTHROPIC_API_KEY",
    "openai": "CROQUITO_OPENAI_API_KEY",
}
"""Credencial exigida por provider. O Bedrock fica de fora porque a cadeia do boto3 não é
uma variável só; a ausência dela vira `unavailable` pela recusa da própria fábrica."""

_FALLBACK_DATASET_ID: Final = "prancha-local"

NO_BUDGET_MESSAGE: Final = (
    "extração automática indisponível: teto de gasto não configurado no servidor"
)
NO_CREDENTIAL_MESSAGE: Final = (
    "extração automática indisponível: credencial do provider não configurada no servidor"
)
ARM_MISCONFIGURED_MESSAGE: Final = (
    "extração automática indisponível: braço pago mal configurado no servidor"
)
FIXTURE_ARM_MESSAGE: Final = (
    "extração automática indisponível: braço fixture não publica pacote de rodada"
)
ARM_UNAVAILABLE_MESSAGE: Final = (
    "extração automática indisponível: teto de gasto ou credencial do provider recusados "
    "pelo servidor"
)


def upload_invalid(
    reason: str, details: dict[str, object] | None = None
) -> ValuationValidationError:
    """Arquivo que não é prancha: recusado antes de qualquer escrita ou renderização."""
    return ValuationValidationError(
        "LOCAL_UPLOAD_INVALID",
        "o arquivo enviado não é um PDF de prancha aceitável",
        {"reason": reason, **(details or {})},
    )


def dataset_id(workdir: Path) -> str:
    """Identificador da rodada para a ingestão, derivado do nome do diretório.

    O manifest tem contrato fechado para esse campo (`[a-z0-9][a-z0-9-]{2,63}`), então nome
    de pasta com acento, espaço ou maiúscula vira slug. Nome que não sobrevive à
    normalização cai num rótulo declarado em vez de derrubar o upload do orçamentista — é
    o mesmo identificador que vai para `plate_id`, e ele identifica a rodada, não o cliente.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", workdir.name.lower()).strip("-")[:64]
    return slug if re.fullmatch(r"[a-z0-9][a-z0-9-]{2,63}", slug) else _FALLBACK_DATASET_ID


def promote_first_page(workdir: Path, pdf_path: Path) -> PdfManifest:
    """Renderiza o PDF num temporário da rodada e promove a página 1 mais o manifest.

    Renderizar fora do lugar final e mover depois é o que impede a rodada de ficar com
    meia prancha: só entram no diretório o PNG da página que o manifest declara e o
    próprio manifest. O resto da ingestão (contact sheet, demais páginas) é descartado —
    esta rodada é de uma prancha só.
    """
    workspace = Path(tempfile.mkdtemp(dir=workdir, prefix=".prancha-ingest-"))
    try:
        # A tradução cobre a RENDERIZAÇÃO e só ela: `ValuationValidationError` é um
        # `ValueError`, então uma recusa já formada aqui dentro seria reembrulhada com o
        # motivo trocado se o `except` alcançasse o resto do corpo.
        try:
            manifest, manifest_path = ingest_pdf(
                pdf_path,
                workspace,
                dataset_id=dataset_id(workdir),
                role=PLATE_INGEST_ROLE,
                dpi=PLATE_INGEST_DPI,
            )
        except (ValueError, RuntimeError) as error:
            # PDF protegido por senha, sem páginas ou ilegível para o renderizador.
            raise upload_invalid(str(error)[:200], {"stage": "ingest"}) from error
        page = manifest.pages[PLATE_PAGE_NUMBER - 1]
        rendered = manifest_path.parent / page.render_file
        if file_sha256(rendered) != page.image_sha256:  # pragma: no cover - ingestão coerente
            raise upload_invalid("a página renderizada não confere com o manifest da ingestão")
        os.replace(rendered, workdir / page.render_file)
        os.replace(manifest_path, workdir / PLATE_MANIFEST_FILENAME)
        return manifest
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def ingest_plate_upload(workdir: Path, *, filename: str | None, payload: bytes) -> PdfManifest:
    """Grava a prancha enviada e devolve o manifest da ingestão.

    Validação antes de qualquer escrita (extensão, tamanho e assinatura do arquivo) e
    desfazimento depois de qualquer falha: ingestão que não fecha remove o PDF, e a rodada
    volta a ser exatamente o que era antes do clique.
    """
    name = (filename or "").strip()
    if not name.lower().endswith(".pdf"):
        raise upload_invalid("o arquivo precisa ser um PDF (.pdf)", {"filename": name})
    if not payload:
        raise upload_invalid("arquivo vazio")
    if not payload.startswith(b"%PDF-"):
        raise upload_invalid("assinatura de PDF ausente no início do arquivo")

    pdf_path = workdir / PLATE_PDF_FILENAME
    atomic_write_bytes(pdf_path, payload)
    try:
        return promote_first_page(workdir, pdf_path)
    except Exception:
        pdf_path.unlink(missing_ok=True)
        raise


def extraction_arm_spec() -> str:
    """Braço pago em uso. A env é o escape declarado para a próxima eval comparativa."""
    return os.environ.get(EXTRACTION_ARM_ENV, "").strip() or MEDICAO_EXTRACTION_ARM


def missing_extraction_envs(arm_spec: str) -> list[str]:
    """Variáveis obrigatórias que faltam para a extração paga poder sequer começar."""
    provider = arm_spec.partition("=")[2].partition(":")[0]
    required = [AI_BUDGET_ENV]
    credential = _PROVIDER_CREDENTIAL_ENV.get(provider)
    if credential is not None:
        required.append(credential)
    return [name for name in required if not os.environ.get(name, "").strip()]


def extraction_unavailable(arm_spec: str) -> ValuationValidationError | None:
    """Motivo de a extração paga não poder ser tentada, ou `None` quando ela pode.

    É esta pré-checagem que garante o freio principal: **nunca** existe tentativa sem teto
    de gasto declarado no ambiente do servidor. Ela roda antes da thread e antes de
    qualquer byte sair da máquina, e o que ela devolve vira estado visível na tela.
    """
    missing = missing_extraction_envs(arm_spec)
    if not missing:
        return None
    return ValuationValidationError(
        "LOCAL_EXTRACTION_UNAVAILABLE",
        NO_BUDGET_MESSAGE if AI_BUDGET_ENV in missing else NO_CREDENTIAL_MESSAGE,
        {"missing_env": missing, "arm": arm_spec},
    )


def build_extraction_adapter(arm_spec: str) -> tuple[str, str, ProviderAdapter]:
    """Monta o braço pago `NOME=PROVIDER:MODELO` da extração automática.

    Espelho de `cli._build_paid_arm` com os códigos deste servidor: forma inválida e
    provider `fixture` recusam antes de qualquer rede — observação fabricada não vira
    pacote de rodada —, e a `ValueError` de `build_extraction_arm` (teto de gasto ausente
    ou credencial faltando) vira recusa de domínio em vez de erro de servidor.

    É também o seam de teste do módulo: o teste troca esta fábrica por um adapter fixture,
    e nenhuma chamada externa acontece na suíte.
    """
    name, separator, target = arm_spec.partition("=")
    provider, model_separator, model_id = target.partition(":")
    if not name or not separator or not provider or not model_separator or not model_id:
        raise ValuationValidationError(
            "LOCAL_EXTRACTION_ARM_INVALID",
            ARM_MISCONFIGURED_MESSAGE,
            {"arm": arm_spec},
        )
    if provider == "fixture":
        raise ValuationValidationError(
            "LOCAL_EXTRACTION_ARM_FIXTURE_FORBIDDEN",
            FIXTURE_ARM_MESSAGE,
            {"arm": arm_spec},
        )
    try:
        adapter = build_extraction_arm(provider=provider, model_id=model_id)
    except ValueError as error:
        raise ValuationValidationError(
            "LOCAL_EXTRACTION_UNAVAILABLE",
            ARM_UNAVAILABLE_MESSAGE,
            {"arm": arm_spec, "reason": str(error)},
        ) from error
    return name, model_id, adapter


def authorize_uploaded_page(manifest_path: Path, page_sha256: str) -> str:
    """Autoriza a página consentida pelo upload e devolve o digest do documento.

    A allowlist global (`CROQUITO_AI_EXTRACTION_ALLOWED_DIGESTS`) **não se aplica a este
    fluxo**, e a dispensa é decisão registrada, não esquecimento: naquela via o
    consentimento é a variável de ambiente que um operador declara antes de mandar o
    documento de um cliente para fora; nesta via o consentimento é o próprio ato do
    orçamentista de subir a prancha na tela, e o digest nasce do arquivo que ele acabou de
    enviar — ele vai para o estado e para o `extraction-lineage.json`, onde fica auditável.
    Dispensar a allowlist não dispensa o outro amarrado, e por isso ele continua aqui: a
    imagem enviada tem de ser a página que o manifest da ingestão declara
    (`bind_page_to_document`), senão um PNG largado no diretório viraria evidência de um
    documento que ninguém enviou.
    """
    return bind_page_to_document(manifest_path, page_sha256)


def extract_legend_from_upload(
    workdir: Path, manifest: PdfManifest, adapter: ProviderAdapter
) -> LegendExtractionResult:
    """Extrai a legenda da prancha consentida pelo upload.

    Compõe as MESMAS peças de `legend_extraction.run_legend_extraction` — pedido,
    chamada, mapeamento observação→takeoff e registro fino do bbox contra a tinta —
    trocando **só** o portão de consentimento (`authorize_uploaded_page` no lugar de
    `authorize_page`). O caminho pago do CLI fica intocado; a parity entre as duas
    montagens é prendida por teste, para que elas não possam divergir em silêncio.
    """
    page = manifest.pages[PLATE_PAGE_NUMBER - 1]
    image_path = (workdir / page.render_file).resolve(strict=True)
    image_sha256 = hashlib.sha256(image_path.read_bytes()).hexdigest()
    source_sha256 = authorize_uploaded_page(workdir / PLATE_MANIFEST_FILENAME, image_sha256)

    request, width, height = build_legend_request(image_path)
    execution = adapter.execute(request)
    output = execution.output
    if not isinstance(output, LegendExtractionOutput):  # pragma: no cover - contrato do adapter
        raise ProviderExecutionError(ProviderFailureCode.INVALID_SCHEMA)
    packet = takeoff_packet_from_legend(
        output,
        plate_id=dataset_id(workdir),
        page_number=PLATE_PAGE_NUMBER,
        image_sha256=image_sha256,
        source_pdf_sha256=source_sha256,
        image_width=width,
        image_height=height,
        extractor=extractor_label(execution.provider.value, execution.model_id),
        extractor_version=execution.prompt.prompt_version,
    )
    registered, registration = register_legend_bboxes(image_path, packet)
    return LegendExtractionResult(
        packet=registered,
        execution=execution,
        source_sha256=source_sha256,
        registration=registration,
    )


def execution_payload(execution: ProviderExecution) -> dict[str, object]:
    """Lineage e custo de uma chamada paga. Espelho de `cli._execution_payload`.

    IDs, versão de prompt, tokens, custo e latência — nunca a resposta bruta nem o que foi
    enviado.
    """
    usage = execution.usage
    return {
        "provider": execution.provider.value,
        "model_id": execution.model_id,
        "prompt_version": execution.prompt.prompt_version,
        "input_digest": execution.input_digest,
        "latency_ms": execution.latency_ms,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "estimated_cost_usd": (
            None if usage.estimated_cost_usd is None else str(usage.estimated_cost_usd)
        ),
    }


def registration_payload(registration: LegendRegistrationReport) -> dict[str, object]:
    """Relatório do registro fino no mesmo formato de `cli.run_register_takeoff`.

    `method` viaja junto porque é ele que decide se a âncora de um item pode ser
    declarada confiável para a tela (`round_view.registered_item_ids`): relatório sem
    método declarado não sustenta retângulo desenhado sobre a prancha.
    """
    return {
        "adjusted": registration.adjusted,
        "unmatched_item_ids": registration.unmatched_item_ids,
        "band_count": registration.band_count,
        "method": registration.method,
        "global_scale": registration.global_scale,
        "global_shift_px": registration.global_shift_px,
        "shift_score": registration.shift_score,
        "shift_confidence": registration.shift_confidence,
    }
