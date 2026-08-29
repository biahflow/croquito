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
import json
import os
import re
import shutil
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from pydantic import ValidationError

from croquito_valuation.catalog import file_sha256
from croquito_valuation.errors import ValuationValidationError
from croquito_worker.extraction_eval import ExtractionNotAllowlistedError, bind_page_to_document
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
    execute_legend_request,
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
"""A página da PRIMEIRA folha da praça no caminho de sempre: a página 1.

Desde a F-046 ela não é mais a única página que vira prancha — a promoção recebe QUAL página
promover (`promote_page`), e quem escolhe é o humano, em lote e sem nada marcado por padrão.
Esta constante segue existindo porque a praça de uma folha é o caso da vida real, e é ela que
mantém esse caso byte-idêntico (ADR-0057, decisão 8).

PDF com mais páginas continua não sendo recusado nem lido às escondidas: a contagem vai
declarada no estado — desde a F-046 por FOLHA, e não só na raiz —, para o orçamentista saber
o que ficou de fora."""

MEDICAO_EXTRACTION_ARM: Final = "sonnet=anthropic:claude-sonnet-5"
"""Braço pago da extração automática: o vencedor da eval paga de 2026-08-13.

Ele é constante e não flag de rota justamente porque trocar de modelo é mudança de IA —
exige eval comparativa e plano de rollback (`docs/ai/MODEL_ROUTING.md`). A variável de
ambiente abaixo existe para a próxima rodada de eval, não para escolher modelo por gosto.
"""

EXTRACTION_ARM_ENV: Final = "CROQUITO_MEDICAO_EXTRACTION_ARM"
AI_BUDGET_ENV: Final = "CROQUITO_AI_MAX_ESTIMATED_COST_USD"

EXTRACTION_RESERVE_ARM_ENV: Final = "CROQUITO_EXTRACTION_RESERVE_ARM"
"""Braço de RESERVA da extração de legenda, na forma `NOME=PROVIDER:MODELO`.

Vazio por padrão, e vazio significa reserva nenhuma: a falha do braço escolhido propaga
exatamente como propagava antes de existir degradação neste caminho. Ligar a reserva é
mudança de IA (`docs/ai/MODEL_ROUTING.md`) e por isso é ato declarado de quem opera, nunca
um default.

O nome não diz "MEDICAO" porque a legenda quantificada é a MESMA tarefa de prompt nas duas
jornadas — medição e orçamento-base compartilham handler, adapter e pacote. Uma reserva que
valesse só para uma delas seria degradação pela metade, e a outra descobriria isso na
primeira falha do fornecedor."""

PLATE_PAGE_ABSENT_CODE: Final = "LOCAL_PLATE_PAGE_ABSENT"
"""A página escolhida não existe no PDF enviado.

Recusa da FOLHA, e não do documento: um PDF de N páginas continua sendo aceito inteiro
(ADR-0057), e o que se recusa aqui é promover a página 9 de um PDF de 3. Código próprio, e
não `LOCAL_UPLOAD_INVALID`, porque o desfecho vira `extraction_failure_code` DAQUELA folha e
o orçamentista precisa distinguir "o arquivo não presta" de "essa página não existe"."""

PLATE_IMAGE_REF: Final = "plate_image_key"
TAKEOFF_OVERLAY_REF: Final = "takeoff_overlay_key"
"""Nomes das chaves de objeto na revisão da rodada (`artifact_refs_json`).

Moram aqui, e não em cada lado, porque quem ESCREVE (o comando de fila do worker) e quem
LÊ (a rota que assina a URL) são processos diferentes: um nome divergente não quebraria
teste nenhum dos dois lados isoladamente e apareceria como imagem que nunca carrega."""

PLATE_IMAGE_DIGEST: Final = "plate_image_sha256"
TAKEOFF_OVERLAY_DIGEST: Final = "takeoff_overlay_sha256"

TAKEOFF_OVERLAY_PACKET_DIGEST: Final = "takeoff_overlay_packet_sha256"
"""Digest do pacote de takeoff que ORIGINOU o overlay desenhado (ADR-0030).

O overlay declara a própria idade sem coluna nova: ele está *vencido* quando este valor
difere do digest do pacote corrente da rodada. A comparação é feita na LEITURA, e por isso
o valor nunca é gravado como "vencido" em lugar nenhum — estado derivado que se pode
gravar é estado que se pode divergir do que a revisão realmente contém."""


def document_digest(document: Mapping[str, Any]) -> str:
    """Digest estável de um artefato guardado em coluna JSON da revisão.

    Mora neste módulo pelo mesmo motivo dos nomes de chave acima, e com mais força: quem
    ESCREVE `takeoff_overlay_packet_sha256` (o comando de fila do worker) e quem o COMPARA
    com o pacote corrente (a rota que serve o overlay) são processos diferentes. Duas
    serializações canônicas escritas em lados opostos passariam nos testes de cada lado e
    deixariam o overlay permanentemente vencido em produção.

    A serialização é canônica — chaves ordenadas, sem espaço supérfluo — justamente para
    que o mesmo conteúdo dê sempre o mesmo digest, independente da ordem em que o banco
    devolveu as chaves.
    """
    encoded = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def round_object_prefix(*, tenant_id: str, round_id: str) -> str:
    """Prefixo dos blobs da rodada; sempre sob `tenants/{tenant_id}/` (ADR-0028 D2)."""
    return f"tenants/{tenant_id}/valuation-rounds/{round_id}"


def plate_image_object_key(
    *, tenant_id: str, round_id: str, position: int = 1, page_number: int = PLATE_PAGE_NUMBER
) -> str:
    """PNG da página promovida — a imagem que a tela vê por URL assinada (D5).

    A PRIMEIRA folha da praça mantém a chave de sempre; da segunda em diante o segmento
    `f{posição}` separa as folhas (F-046). Sem essa separação a folha 2 sobrescreveria o PNG
    da folha 1 no object store, e a praça perderia a evidência de uma das duas — silenciosa e
    irreversivelmente, porque o digest gravado continuaria apontando para a chave certa.
    """
    prefix = f"{round_object_prefix(tenant_id=tenant_id, round_id=round_id)}/plate"
    sheet = "" if position <= 1 else f"/f{position}"
    return f"{prefix}{sheet}/page-{page_number:03d}.png"


def takeoff_overlay_object_key(*, tenant_id: str, round_id: str, position: int = 1) -> str:
    """Overlay da folha. Um overlay POR folha, nunca da praça (ADR-0057, decisão 3)."""
    prefix = round_object_prefix(tenant_id=tenant_id, round_id=round_id)
    sheet = "" if position <= 1 else f"/f{position}"
    return f"{prefix}/takeoff{sheet}/overlay.png"


def plate_ref_key(base: str, *, position: int, plate_id: str) -> str:
    """Nome da chave de artefato de UMA folha dentro dos mapas da revisão.

    `artifact_refs_json` e `artifact_digests_json` são mapas planos por revisão, e a praça
    tem N folhas: sem sufixo, a folha 2 sobrescreveria a referência da folha 1 e a tela
    passaria a servir a imagem errada com o digest errado.

    A primeira folha fica SEM sufixo, com o nome exato de sempre — é isso que mantém a praça
    de uma folha byte-idêntica e o que faz a rota da prancha continuar lendo `plate_image_key`
    sem saber que a praça existe. Uma regra só, num lugar só, porque quem ESCREVE (o comando
    de fila) e quem LÊ (a rota) são processos diferentes.
    """
    return base if position <= 1 else f"{base}:{plate_id}"


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


def promote_page(workdir: Path, pdf_path: Path, *, page_number: int) -> PdfManifest:
    """Renderiza o PDF num temporário da rodada e promove UMA página mais o manifest.

    Renderizar fora do lugar final e mover depois é o que impede a rodada de ficar com
    meia prancha: só entram no diretório o PNG da página que o manifest declara e o
    próprio manifest. O resto da ingestão (contact sheet, demais páginas) é descartado —
    cada folha da praça é uma página, e é a página que este ato promove.

    `page_number` é EXPLÍCITO e sem valor padrão desde a F-046: quem escolhe quais páginas
    viram folha da praça é o humano, em lote, e nada vem marcado por padrão. Página fora do
    documento é recusa nomeada (`LOCAL_PLATE_PAGE_ABSENT`) — e recusa da folha, não do PDF,
    que continua aceito com as N páginas que tiver.
    """
    if page_number < 1:
        raise ValuationValidationError(
            PLATE_PAGE_ABSENT_CODE,
            "a página escolhida não existe no PDF enviado",
            {"page_number": page_number},
        )
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
        if page_number > manifest.page_count:
            raise ValuationValidationError(
                PLATE_PAGE_ABSENT_CODE,
                "a página escolhida não existe no PDF enviado",
                {"page_number": page_number, "page_count": manifest.page_count},
            )
        page = manifest.pages[page_number - 1]
        rendered = manifest_path.parent / page.render_file
        if file_sha256(rendered) != page.image_sha256:  # pragma: no cover - ingestão coerente
            raise upload_invalid("a página renderizada não confere com o manifest da ingestão")
        os.replace(rendered, workdir / page.render_file)
        os.replace(manifest_path, workdir / PLATE_MANIFEST_FILENAME)
        return manifest
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def ingest_plate_upload(
    workdir: Path, *, filename: str | None, payload: bytes, page_number: int
) -> PdfManifest:
    """Grava a prancha enviada e devolve o manifest da ingestão.

    Validação antes de qualquer escrita (extensão, tamanho e assinatura do arquivo) e
    desfazimento depois de qualquer falha: ingestão que não fecha remove o PDF, e a rodada
    volta a ser exatamente o que era antes do clique.

    `page_number` diz QUAL página do documento vira esta folha, e não tem valor padrão de
    propósito (F-046): um padrão silencioso aqui reintroduziria a promoção automática que o
    pacote de design recusou nominalmente.
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
        return promote_page(workdir, pdf_path, page_number=page_number)
    except Exception:
        pdf_path.unlink(missing_ok=True)
        raise


def extraction_arm_spec() -> str:
    """Braço pago em uso. A env é o escape declarado para a próxima eval comparativa."""
    return os.environ.get(EXTRACTION_ARM_ENV, "").strip() or MEDICAO_EXTRACTION_ARM


def extraction_reserve_arm_spec() -> str | None:
    """Braço de reserva configurado, ou `None` quando não há reserva nenhuma.

    Ausente e vazio são a mesma coisa — reserva desligada — e é esse o padrão. O que esta
    função **não** faz é interpretar um valor estranho: quem valida a forma é
    `build_extraction_adapter`, e ele recusa (`LOCAL_EXTRACTION_ARM_INVALID`) em vez de
    ignorar. Mesma disciplina de `providers._openai_arm_enabled`: uma reserva mal escrita
    e silenciosamente descartada é pior que reserva nenhuma, porque o operador acha que
    tem degradação e só descobre que não tem no dia em que o fornecedor cai.
    """
    return os.environ.get(EXTRACTION_RESERVE_ARM_ENV, "").strip() or None


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


def build_extraction_reserve_adapter() -> ProviderAdapter | None:
    """Monta o braço de reserva declarado no ambiente, ou devolve `None` quando não há um.

    Um só lugar constrói a reserva das duas jornadas, pelo mesmo motivo de
    `LocalQueueWorker._valuation_extraction_adapter` ser único: um segundo ponto de
    montagem criaria a chance de uma das cadeias degradar sem os gates de teto de gasto e
    credencial que `build_extraction_adapter` aplica — e sem a recusa de forma inválida.

    Reserva declarada e inconstruível **recusa a extração inteira**, em vez de degradar
    para "sem reserva": quem escreveu a variável espera degradação, e descobrir no dia da
    queda que ela nunca existiu é pior que falhar agora. O preço dessa escolha é que uma
    reserva mal configurada derruba um primário que funcionaria — e é justamente por isso
    que o erro precisa dizer QUAL braço está errado. `build_extraction_adapter` levanta os
    mesmos três códigos para os dois papéis, então aqui a recusa é reetiquetada com
    `role: "reserva"` e o nome da variável; sem isso o operador lê `LOCAL_EXTRACTION_*` e
    vai depurar o braço primário, que está são.
    """
    arm_spec = extraction_reserve_arm_spec()
    if arm_spec is None:
        return None
    try:
        _name, _model_id, adapter = build_extraction_adapter(arm_spec)
    except ValuationValidationError as error:
        raise ValuationValidationError(
            error.code,
            error.message,
            {**error.details, "role": "reserva", "env": EXTRACTION_RESERVE_ARM_ENV},
        ) from error
    return adapter


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
    workdir: Path,
    manifest: PdfManifest,
    adapter: ProviderAdapter,
    reserve: ProviderAdapter | None = None,
    *,
    plate_id: str,
    page_number: int,
) -> LegendExtractionResult:
    """Extrai a legenda da prancha consentida pelo upload.

    Compõe as MESMAS peças de `legend_extraction.run_legend_extraction` — pedido,
    chamada (com a MESMA degradação, `execute_legend_request`), mapeamento
    observação→takeoff e registro fino do bbox contra a tinta — trocando **só** o portão de
    consentimento (`authorize_uploaded_page` no lugar de `authorize_page`). O caminho pago
    do CLI fica intocado; a parity entre as duas montagens é prendida por teste, para que
    elas não possam divergir em silêncio.

    `reserve` é o braço de degradação, desligado por padrão (`None`) — quem o monta a
    partir do ambiente é `build_extraction_reserve_adapter`, no chamador.

    `plate_id` e `page_number` são exigidos e não têm padrão (F-046): eles são a IDENTIDADE
    da folha dentro da praça e viajam para dentro do pacote, onde `TAKEOFF_EVIDENCE_MISMATCH`
    os cobra item a item. Um padrão silencioso aqui deixaria a folha 3 publicar um pacote que
    se declara página 1 — evidência apontando para a folha errada, que é exatamente o que o
    pacote existe para impedir.
    """
    page = manifest.pages[page_number - 1]
    image_path = (workdir / page.render_file).resolve(strict=True)
    image_sha256 = hashlib.sha256(image_path.read_bytes()).hexdigest()
    source_sha256 = authorize_uploaded_page(workdir / PLATE_MANIFEST_FILENAME, image_sha256)

    request, width, height = build_legend_request(image_path)
    execution, fallback_notes = execute_legend_request(request, adapter, reserve)
    output = execution.output
    if not isinstance(output, LegendExtractionOutput):  # pragma: no cover - contrato do adapter
        raise ProviderExecutionError(ProviderFailureCode.INVALID_SCHEMA)
    packet = takeoff_packet_from_legend(
        output,
        plate_id=plate_id,
        page_number=page_number,
        image_sha256=image_sha256,
        source_pdf_sha256=source_sha256,
        image_width=width,
        image_height=height,
        extractor=extractor_label(execution.provider.value, execution.model_id),
        extractor_version=execution.prompt.prompt_version,
        extra_safety_notes=fallback_notes,
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


EXTRACTION_FAILED_CODE: Final = "VALUATION_EXTRACTION_FAILED"
"""Desfecho de quem falhou fora das famílias conhecidas. Nunca some em silêncio."""


def extraction_failure_code(error: BaseException) -> str:
    """Código estável do desfecho de uma extração que não publicou nada.

    Só o CÓDIGO sai daqui: a mensagem da exceção pode carregar trecho da prancha, e o que a
    rodada guarda em `extraction_failure_code` é lido pela tela e pelo log. A classificação
    espelha a do servidor de medição (`local_server._extraction_failure`), com o mesmo
    princípio: falha desconhecida vira código declarado, nunca estado indefinido.
    """
    if isinstance(error, ProviderExecutionError):
        return "PROVIDER_EXECUTION_FAILED"
    if isinstance(error, ExtractionNotAllowlistedError):
        return "EXTRACTION_PAGE_NOT_BOUND"
    if isinstance(error, ValuationValidationError):
        return error.code
    if isinstance(error, ValidationError):
        return "MODEL_VALIDATION_FAILED"
    return EXTRACTION_FAILED_CODE


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
