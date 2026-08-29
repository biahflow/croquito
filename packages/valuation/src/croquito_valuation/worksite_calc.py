"""O boletim da praça: a união dos conjuntos de código das folhas (F-046, ADR-0057).

A praça grande vem em planta geral, folhas de detalhe e cortes, e a legenda quantificada é
da OBRA. O consolidado (`worksite_takeoff.py`) já diz quais folhas compõem a praça e quais
leituras foram declaradas o mesmo elemento físico; este módulo é quem transforma isso em
medição: **um boletim por folha**, e o total da praça saindo da consolidação por código
entre boletins que a PLANILHA GERAL já faz desde o M2 (`workbook_writer._measured_by_code`).

Por que um boletim por folha, e não um boletim só com tudo somado:

- `Valuation` já admite N boletins com `worksite_key` distinto e amarra cada memória de
  cálculo ao par `(worksite_key, item_number)`. O domínio nunca precisou de um produtor de
  vários boletins — ele foi escrito para várias OBRAS numa medição —, e a praça de várias
  folhas é a mesma forma com outro sentido: o que a folha tem de próprio (numeração,
  memória, aba na pasta) continua sendo dela.
- A memória fica dizendo de qual folha veio cada parcela sem inventar campo nenhum: a
  parcela mora na memória da folha onde a leitura foi feita, e o total da praça é
  reproduzível somando as folhas por código.
- A alternativa — fundir tudo num boletim e renumerar — apagaria a folha de origem da
  parcela justamente no artefato que a orçamentista lê para conferir o número.

Praça de UMA folha é caso da vida real, não caso degenerado, e responde exatamente como
hoje: a chave e o nome do boletim são os da praça, sem sufixo, e o resultado é
byte-idêntico ao de `calc.build_worksite_valuation` (ADR-0057, decisão 8). O sufixo `-pN`
só nasce quando existe a segunda folha, porque é só aí que duas chaves precisam se
distinguir.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from croquito_valuation.assignment import CodeAssignmentSet
from croquito_valuation.calc import CalcBuildResult, CalcPlan, build_worksite_bulletin
from croquito_valuation.calc_matrix import CalcMatrix
from croquito_valuation.errors import ValuationValidationError
from croquito_valuation.models import (
    WORKSITE_KEY_PATTERN,
    CalcSheet,
    PriceCatalog,
    Valuation,
    WorksiteBulletin,
)
from croquito_valuation.takeoff import TakeoffItem, TakeoffItemStatus, TakeoffPacket
from croquito_valuation.template import WorkbookTemplate, default_template
from croquito_valuation.worksite_takeoff import (
    TakeoffItemAddress,
    WorksiteTakeoff,
    ensure_worksite_matches_packets,
)

MAX_WORKSITE_NAME_LENGTH: Final = 120
"""Espelho de `WorksiteBulletin.worksite_name`; o nome derivado da folha não pode passar."""

_WORKSITE_SAFETY_NOTES: Final = (
    "O boletim da praça é a união dos conjuntos de código das folhas do consolidado; "
    "nenhuma folha mede a praça sozinha.",
    "Leitura fundida por declaração conta uma vez, pela parcela que fica; a leitura "
    "absorvida continua impressa na memória da folha onde foi lida, com subtotal zero.",
)


@dataclass(frozen=True, slots=True)
class WorksitePlateInput:
    """O que uma folha traz para o boletim da praça: o pacote e o que foi decidido sobre ele.

    `calc_plan` e `calc_matrix` são por folha porque a memória é por folha — a orçamentista
    monta a matriz olhando uma prancha, e o ADR-0057 (decisão 1) mantém a prancha como
    unidade de evidência e de revisão. O consolidado não tem memória própria.
    """

    packet: TakeoffPacket
    assignments: CodeAssignmentSet
    calc_plan: CalcPlan | None = None
    calc_matrix: CalcMatrix | None = None


@dataclass(frozen=True, slots=True)
class WorksitePlateBulletin:
    """O boletim de uma folha da praça, com a folha de onde ele veio nomeada."""

    plate_id: str
    build: CalcBuildResult

    @property
    def bulletin(self) -> WorksiteBulletin:
        return self.build.bulletin

    @property
    def calc_sheets(self) -> tuple[CalcSheet, ...]:
        return self.build.calc_sheets

    @property
    def worksite_key(self) -> str:
        """A chave do boletim desta folha; é ela que amarra as memórias na medição."""
        return self.build.bulletin.worksite_key


@dataclass(frozen=True, slots=True)
class TakeoffItemFusion:
    """Uma fusão declarada, já resolvida contra os pacotes: quem fica, quem sai, e quanto.

    Existe para que a divergência entre as duas leituras seja um DADO, e não uma descoberta
    de quem for conferir o total. Quantidades diferentes não são erro (ADR-0057, decisão 4:
    `kept` é a leitura que governa); são informação que a tela e o relatório precisam
    mostrar, porque uma diferença grande costuma significar que a orçamentista fundiu duas
    leituras que não eram o mesmo elemento.
    """

    kept: TakeoffItemAddress
    discarded: TakeoffItemAddress
    kept_quantity: Decimal
    discarded_quantity: Decimal

    @property
    def difference(self) -> Decimal:
        """Quanto a leitura que fica difere da absorvida; positivo quando `kept` é maior."""
        return self.kept_quantity - self.discarded_quantity


@dataclass(frozen=True, slots=True)
class WorksiteTakeoffBuildResult:
    """Boletins e memórias da praça inteira, na ordem das folhas do consolidado."""

    worksite_key: str
    plates: tuple[WorksitePlateBulletin, ...]
    fusions: tuple[TakeoffItemFusion, ...]
    safety_notes: tuple[str, ...]

    @property
    def bulletins(self) -> list[WorksiteBulletin]:
        return [plate.bulletin for plate in self.plates]

    @property
    def calc_sheets(self) -> list[CalcSheet]:
        return [sheet for plate in self.plates for sheet in plate.calc_sheets]

    @property
    def total_amount(self) -> Decimal:
        """Total da praça: soma dos totais já truncados de cada folha, sem truncar de novo."""
        return sum((plate.bulletin.total_amount for plate in self.plates), Decimal("0.00"))


def _ensure_unique_plate_inputs(plates: Sequence[WorksitePlateInput]) -> None:
    """Duas entradas para a mesma folha calariam uma das duas ao indexar por `plate_id`."""
    plate_ids = [plate.packet.plate_id for plate in plates]
    duplicated = sorted({p for p in plate_ids if plate_ids.count(p) > 1})
    if duplicated:
        raise ValuationValidationError(
            "WORKSITE_TAKEOFF_DUPLICATE_PLATE",
            "a mesma prancha foi entregue mais de uma vez para o boletim da praça",
            {"plate_ids": duplicated},
        )


def _ensure_no_extra_plates(
    worksite: WorksiteTakeoff, plates: Sequence[WorksitePlateInput]
) -> None:
    """Pacote que não está no consolidado não entra no boletim, mesmo estando revisado.

    O consolidado é quem declara de quais folhas a praça é feita; aceitar uma folha a mais
    porque ela chegou junto mediria uma praça que ninguém compôs — o irmão exato da folha a
    menos que `WORKSITE_PACKET_MISSING` recusa do outro lado.
    """
    known = {reference.plate_id for reference in worksite.plates}
    unknown = sorted({p.packet.plate_id for p in plates} - known)
    if unknown:
        raise ValuationValidationError(
            "WORKSITE_TAKEOFF_PLATE_UNKNOWN",
            "pacote de prancha que não está no consolidado da praça",
            {"plate_ids": unknown, "worksite_key": worksite.worksite_key},
        )


def _ensure_no_pending_plate(inputs: Mapping[str, WorksitePlateInput]) -> None:
    """Praça não fecha com folha pendente (ADR-0057, decisão 7).

    Uma folha a menos é meia praça, e meia praça somada parece uma praça inteira. O erro
    nomeia QUAIS folhas estão pendentes e quantos itens faltam em cada uma, porque o que a
    orçamentista precisa saber é para onde voltar — não que "algo" está pendente.
    """
    pending = {
        plate_id: len(plate.packet.pending_items())
        for plate_id, plate in inputs.items()
        if plate.packet.pending_items()
    }
    if pending:
        raise ValuationValidationError(
            "WORKSITE_TAKEOFF_PLATE_PENDING",
            "a praça não fecha com folha pendente de revisão; item proposto ou ambíguo em "
            "qualquer prancha do consolidado bloqueia o boletim da obra",
            {
                "plate_ids": sorted(pending),
                "pending_by_plate": {key: pending[key] for key in sorted(pending)},
            },
        )


def _item_at(inputs: Mapping[str, WorksitePlateInput], address: TakeoffItemAddress) -> TakeoffItem:
    """O item apontado por um endereço do consolidado; a existência já foi conferida."""
    packet = inputs[address.plate_id].packet
    for item in packet.items:
        if item.id == address.item_id:
            return item
    raise ValuationValidationError(  # pragma: no cover - `ensure_worksite_matches_packets`
        "WORKSITE_LINK_UNKNOWN_TARGET",
        "vínculo de identidade aponta para item que não existe no pacote da prancha",
        {"addresses": [f"{address.plate_id}:{address.item_id}"]},
    )


def _resolve_fusions(
    worksite: WorksiteTakeoff, inputs: Mapping[str, WorksitePlateInput]
) -> tuple[TakeoffItemFusion, ...]:
    """Resolve cada vínculo contra os pacotes e recusa fusão sobre leitura não confirmada.

    As duas pontas precisam estar CONFIRMADAS. Fundir sobre uma leitura rejeitada perderia
    quantidade em silêncio pelos dois lados: se a parcela que fica foi rejeitada, ela não
    vira linha nenhuma, e a leitura absorvida — que continuaria zerada — deixaria a praça
    sem o elemento inteiro. Rejeitar uma leitura duplicada já é a forma de dizer que ela não
    conta; para isso não é preciso declarar identidade.
    """
    fusions: list[TakeoffItemFusion] = []
    unconfirmed: list[str] = []
    for link in worksite.identity_links:
        kept = _item_at(inputs, link.kept)
        discarded = _item_at(inputs, link.discarded)
        for address, item in ((link.kept, kept), (link.discarded, discarded)):
            if item.status is not TakeoffItemStatus.CONFIRMED:
                unconfirmed.append(f"{address.plate_id}:{address.item_id}")
        if kept.quantity is None or discarded.quantity is None:
            continue
        fusions.append(
            TakeoffItemFusion(
                kept=link.kept,
                discarded=link.discarded,
                kept_quantity=kept.quantity,
                discarded_quantity=discarded.quantity,
            )
        )
    if unconfirmed:
        raise ValuationValidationError(
            "WORKSITE_TAKEOFF_LINK_TARGET_NOT_CONFIRMED",
            "vínculo de identidade exige as duas leituras confirmadas pelo orçamentista",
            {"addresses": sorted(set(unconfirmed))},
        )
    return tuple(fusions)


def _fused_into_by_plate(worksite: WorksiteTakeoff) -> dict[str, dict[str, str]]:
    """Por folha, quais leituras dela foram absorvidas e por qual folha.

    O resolver de memória (`calc_matrix`) enxerga uma folha por vez e só conhece `item_id`;
    é aqui que o par `(plate_id, item_id)` do consolidado vira o `item_id` daquela folha.
    """
    fused: dict[str, dict[str, str]] = {}
    for link in worksite.identity_links:
        plate = fused.setdefault(link.discarded.plate_id, {})
        plate[link.discarded.item_id] = link.kept.plate_id
    return fused


def _plate_labels(
    *,
    worksite_key: str,
    worksite_name: str,
    position: int,
    single: bool,
    template: WorkbookTemplate,
) -> tuple[str, str]:
    """Chave e nome do boletim de uma folha.

    Com uma folha só, a praça É a folha: chave e nome passam intactos, e é isso que mantém a
    rodada de prancha única byte-idêntica à de hoje. Com mais de uma, cada folha precisa de
    chave própria (`Valuation` recusa boletim repetido por obra) e de nome próprio (a pasta
    nomeia a aba BM/MEMÓRIA pelo nome da obra, e duas abas homônimas se sobrescreveriam).

    O rótulo da aba nasce nesta função, e é aqui que ele é conferido contra o TEMPLATE.
    Conferindo só na hora de publicar o `.xlsx` — como era até a F-046 T4f —, a praça de
    nome longo era montada, servida e aprovada para reprovar no ato mais caro e último da
    cadeia, quando ao humano já não resta senão refazer. `sheet_worksite_label` recusa
    apenas o que não cabe nem na forma curta, e a recusa diz o teto.
    """
    if single:
        key, name = worksite_key, worksite_name
    else:
        key = f"{worksite_key}-p{position}"
        name = f"{worksite_name} P{position}"
        if re.fullmatch(WORKSITE_KEY_PATTERN, key) is None:
            raise ValuationValidationError(
                "WORKSITE_TAKEOFF_PLATE_LABEL_TOO_LONG",
                "a chave derivada da folha não cabe no formato de chave de obra; encurte a "
                "chave da praça",
                {"worksite_key": worksite_key, "derived": key},
            )
        if len(name) > MAX_WORKSITE_NAME_LENGTH:
            raise ValuationValidationError(
                "WORKSITE_TAKEOFF_PLATE_LABEL_TOO_LONG",
                "o nome derivado da folha ultrapassa o limite de nome de obra; encurte o "
                "nome da praça",
                {"worksite_name": worksite_name, "derived_length": len(name)},
            )
    # Chamada pelo efeito: o rótulo é do escritor, o que interessa aqui é a recusa.
    template.sheet_worksite_label(name)
    return key, name


def build_worksite_takeoff_bulletins(
    worksite: WorksiteTakeoff,
    plates: Sequence[WorksitePlateInput],
    catalog: PriceCatalog,
    *,
    worksite_name: str,
    address: str | None = None,
    contract_label: str | None = None,
    template: WorkbookTemplate | None = None,
) -> WorksiteTakeoffBuildResult:
    """Monta o boletim de cada folha da praça, com a fusão declarada já aplicada.

    A chave da obra vem do CONSOLIDADO (`worksite.worksite_key`) e não por parâmetro: quem
    declarou de quais folhas a praça é feita já declarou qual praça é.

    `template` é o layout em que esta praça será PUBLICADA, e entra aqui só para que o
    rótulo da aba de cada folha seja conferido onde ele nasce (`_plate_labels`). Omitido,
    é o `default_template()` — o mesmo que a rota de exportação usa hoje.

    Fail-closed, na ordem em que uma praça pode estar errada: folha entregue duas vezes,
    folha do consolidado sem pacote ou com pacote de outro conteúdo (digest), pacote a mais
    que ninguém consolidou, folha pendente de revisão, e vínculo de identidade sobre leitura
    não confirmada. Só então cada folha vira boletim — e as recusas de folha
    (`CALC_ASSIGNMENT_MISSING`, `CALC_PACKAGE_NOT_CLOSED`, `CALC_PLAN_QUANTITY_MISMATCH`,
    `BULLETIN_PRICE_ORIGIN_FORBIDDEN`) continuam valendo, uma folha de cada vez, sem cópia.
    """
    _ensure_unique_plate_inputs(plates)
    ensure_worksite_matches_packets(worksite, [plate.packet for plate in plates])
    _ensure_no_extra_plates(worksite, plates)
    inputs = {plate.packet.plate_id: plate for plate in plates}
    _ensure_no_pending_plate(inputs)
    fusions = _resolve_fusions(worksite, inputs)

    fused_into = _fused_into_by_plate(worksite)
    layout = default_template() if template is None else template
    single = len(worksite.plates) == 1
    built: list[WorksitePlateBulletin] = []
    for position, reference in enumerate(worksite.plates, start=1):
        plate = inputs[reference.plate_id]
        plate_key, plate_name = _plate_labels(
            worksite_key=worksite.worksite_key,
            worksite_name=worksite_name,
            position=position,
            single=single,
            template=layout,
        )
        build = build_worksite_bulletin(
            plate.packet,
            plate.assignments,
            catalog,
            worksite_key=plate_key,
            worksite_name=plate_name,
            address=address,
            contract_label=contract_label,
            calc_plan=plate.calc_plan,
            calc_matrix=plate.calc_matrix,
            fused_into=fused_into.get(reference.plate_id, {}),
        )
        built.append(WorksitePlateBulletin(plate_id=reference.plate_id, build=build))

    return WorksiteTakeoffBuildResult(
        worksite_key=worksite.worksite_key,
        plates=tuple(built),
        fusions=fusions,
        safety_notes=_WORKSITE_SAFETY_NOTES + built[0].build.safety_notes,
    )


def build_worksite_takeoff_valuation(
    worksite: WorksiteTakeoff,
    plates: Sequence[WorksitePlateInput],
    catalog: PriceCatalog,
    *,
    worksite_name: str,
    period_number: int,
    reference_label: str,
    address: str | None = None,
    contract_label: str | None = None,
    template: WorkbookTemplate | None = None,
) -> Valuation:
    """A medição de um período da praça inteira, sem aprovação.

    Irmã de `calc.build_worksite_valuation`, com a mesma fronteira: aprovação nominal é ato
    humano posterior (`ValuationApproval`) e não é responsabilidade de builder nenhum.
    """
    result = build_worksite_takeoff_bulletins(
        worksite,
        plates,
        catalog,
        worksite_name=worksite_name,
        address=address,
        contract_label=contract_label,
        template=template,
    )
    return Valuation(
        period_number=period_number,
        reference_label=reference_label,
        bulletins=result.bulletins,
        calc_sheets=result.calc_sheets,
    )
