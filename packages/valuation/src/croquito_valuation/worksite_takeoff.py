"""O consolidado da praça: várias pranchas, uma legenda quantificada só (F-046, ADR-0057).

Uma praça grande não cabe numa folha — vem em planta geral, folhas de detalhe e cortes —,
mas a legenda quantificada é da OBRA, não de cada folha. O ADR-0057 decide que a prancha
continua a unidade de evidência (`TakeoffPacket` não muda, `TAKEOFF_EVIDENCE_MISMATCH`
continua recusando item de outra folha dentro do pacote) e que a praça é um CONSOLIDADO
por cima, que referencia pacotes sem absorvê-los (decisões 1-2). Este módulo é esse
consolidado: `WorksiteTakeoff` lista os pacotes da praça por prancha e por digest, e não
contém nenhum `TakeoffItem`.

Duas coisas atravessam a praça e precisam de forma própria:

- a identidade do item, que só é única DENTRO do pacote (`ti_...` pode colidir entre duas
  folhas): o par `(plate_id, item_id)` (`TakeoffItemAddress`) promove a chave que já vive
  na evidência do item, em vez de inventar uma nova (decisão 5);
- a fusão de duas leituras do MESMO elemento físico em folhas diferentes, que nunca é
  automática — nem por rótulo, nem por unidade, nem por proximidade. É sempre um ato
  humano declarado (`TakeoffItemIdentityLink`), no mesmo idioma do reajuste
  (`contract.PriceAdjustment`) e da RE-RA (`contract.Amendment`): autor, instante com fuso,
  nota, e qual das duas leituras é "a parcela que fica" — a que governa a quantidade
  quando as duas divergirem. Sem essa declaração, as duas leituras contam como dois itens;
  o fail-closed erra para o lado de somar demais, e visivelmente (decisão 4).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import datetime
from typing import Final, Literal

from pydantic import Field, model_validator

from croquito_valuation.errors import ValuationValidationError
from croquito_valuation.models import (
    SHA256_PATTERN,
    TAKEOFF_ITEM_ID_PATTERN,
    WORKSITE_KEY_PATTERN,
    ValuationContractModel,
)
from croquito_valuation.takeoff import TakeoffPacket

WORKSITE_TAKEOFF_SCHEMA_VERSION: Final = "1.0.0"


def takeoff_packet_digest(packet: TakeoffPacket) -> str:
    """SHA-256 do conteúdo canônico de um pacote de takeoff.

    Função livre, não método de `TakeoffPacket`: o ADR-0057 (decisão 8) proíbe o pacote de
    ganhar campo ou comportamento nesta feature — nenhum artefato já assinado pode mudar de
    digest por causa da praça. A âncora que o consolidado guarda vive aqui, ao lado de quem
    a produz e de quem a confere.
    """
    canonical = json.dumps(
        packet.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class WorksitePlateReference(ValuationContractModel):
    """Uma folha da praça, referenciada por prancha e pelo digest do pacote extraído.

    O digest é o que garante que a referência não aponta silenciosamente para outro
    conteúdo da mesma prancha — reextração, edição do pacote — sem que ninguém tenha
    atualizado o consolidado (`WORKSITE_PACKET_DIGEST_MISMATCH` em
    `ensure_worksite_matches_packets`).
    """

    plate_id: str = Field(min_length=1, max_length=64)
    packet_digest: str = Field(pattern=SHA256_PATTERN)


class TakeoffItemAddress(ValuationContractModel):
    """Identidade de um item de takeoff que atravessa a praça: o par `(plate_id, item_id)`.

    `item_id` (`ti_...`) só é único DENTRO do pacote (`TakeoffPacket.validate_references`);
    dois pacotes de folhas diferentes podem cunhar o mesmo id. `plate_id` já viaja na
    evidência do item (`PlateEvidence.plate_id`) — o par promove a chave que já existe em
    vez de inventar uma global (ADR-0057, decisão 5, que rejeita explicitamente essa
    alternativa).
    """

    plate_id: str = Field(min_length=1, max_length=64)
    item_id: str = Field(pattern=TAKEOFF_ITEM_ID_PATTERN)


class TakeoffItemIdentityLink(ValuationContractModel):
    """Ato humano: duas leituras de folhas diferentes são o MESMO elemento físico.

    `kept` é "a parcela que fica" — a leitura que governa a quantidade quando as duas
    leituras divergirem. `discarded` continua gravada e visível no consolidado; só deixa de
    contar para o total. Nunca nasce de semelhança de rótulo, unidade ou proximidade — só
    da declaração (ADR-0057, decisão 4), por isso todo campo de procedência é obrigatório
    aqui, e não opcional-depois-exigido como em `contract.Amendment`: não existe vínculo
    histórico lido de planilha para este tipo, então não há compatibilidade a preservar.
    """

    kept: TakeoffItemAddress
    discarded: TakeoffItemAddress
    declared_by: str | None = Field(default=None, min_length=1, max_length=120)
    declared_at: datetime | None = None
    note: str | None = Field(default=None, min_length=1, max_length=300)

    @model_validator(mode="after")
    def validate_provenance(self) -> TakeoffItemIdentityLink:
        if self.declared_by is None or self.declared_at is None or self.note is None:
            raise ValuationValidationError(
                "WORKSITE_LINK_INCOMPLETE",
                "vínculo de identidade exige autor, instante com fuso horário e nota",
                {
                    "kept": f"{self.kept.plate_id}:{self.kept.item_id}",
                    "discarded": f"{self.discarded.plate_id}:{self.discarded.item_id}",
                },
            )
        if self.declared_at.tzinfo is None or self.declared_at.utcoffset() is None:
            raise ValuationValidationError(
                "WORKSITE_LINK_INCOMPLETE",
                "vínculo de identidade exige instante com fuso horário",
                {"declared_at": self.declared_at.isoformat()},
            )
        return self

    @model_validator(mode="after")
    def validate_same_plate(self) -> TakeoffItemIdentityLink:
        if self.kept.plate_id == self.discarded.plate_id:
            raise ValuationValidationError(
                "WORKSITE_LINK_SAME_PLATE",
                "vínculo de identidade é entre pranchas diferentes; dentro da mesma folha "
                "o item_id já é único e não há o que fundir",
                {
                    "plate_id": self.kept.plate_id,
                    "kept_item_id": self.kept.item_id,
                    "discarded_item_id": self.discarded.item_id,
                },
            )
        return self


class WorksiteTakeoff(ValuationContractModel):
    """O consolidado da praça: soma pacotes de takeoff por composição, nunca os absorve.

    Espelha o padrão do consolidado contratual (`contract.ContractWorkbook`) e do
    reajuste/RE-RA declarados (`contract.PriceAdjustment`, `contract.Amendment`): um
    agregado que referencia artefatos autocontidos em vez de reescrevê-los. `plates` só
    guarda `(plate_id, digest)` — nenhum `TakeoffItem` mora aqui; quem precisa do conteúdo
    real carrega os pacotes e confere com `ensure_worksite_matches_packets`.
    """

    schema_version: Literal["1.0.0"] = WORKSITE_TAKEOFF_SCHEMA_VERSION
    worksite_key: str = Field(pattern=WORKSITE_KEY_PATTERN)
    plates: list[WorksitePlateReference] = Field(min_length=1)
    identity_links: list[TakeoffItemIdentityLink] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_plates(self) -> WorksiteTakeoff:
        plate_ids = [plate.plate_id for plate in self.plates]
        duplicated = sorted({p for p in plate_ids if plate_ids.count(p) > 1})
        if duplicated:
            raise ValuationValidationError(
                "WORKSITE_DUPLICATE_PLATE",
                "a mesma prancha aparece mais de uma vez no consolidado",
                {"plate_ids": duplicated},
            )
        return self

    @model_validator(mode="after")
    def validate_link_targets_known(self) -> WorksiteTakeoff:
        known_plate_ids = {plate.plate_id for plate in self.plates}
        unknown: list[str] = []
        for link in self.identity_links:
            for address in (link.kept, link.discarded):
                if address.plate_id not in known_plate_ids:
                    unknown.append(f"{address.plate_id}:{address.item_id}")
        if unknown:
            raise ValuationValidationError(
                "WORKSITE_LINK_UNKNOWN_TARGET",
                "vínculo de identidade aponta para prancha que não está no consolidado",
                {"addresses": sorted(set(unknown))},
            )
        return self

    @model_validator(mode="after")
    def validate_no_link_chain(self) -> WorksiteTakeoff:
        """Recusa cadeia (A≡B e B≡C) em vez de reduzir a um grupo.

        Um vínculo é um ato humano sobre DUAS pontas; um terceiro elemento não herda a
        fusão por transitividade. Se B é "a parcela que fica" de A e, num outro vínculo, B
        é a leitura descartada em favor de C, o sistema não sabe se a orçamentista quis
        dizer que A, B e C são o mesmo elemento com C valendo — o que exigiria um vínculo
        DIRETO entre A e C que ninguém declarou — ou se são dois vínculos independentes que
        colidiram em B por engano. Reduzir a um grupo automaticamente seria inferir uma
        declaração que não existe, o oposto do invariante do produto (nunca funde por
        semelhança/proximidade); recusar é fail-closed e pede a declaração direta que falta.
        A mesma regra recusa duas leituras descartadas a favor de dois vencedores diferentes
        ("B absorvido por A" e "B absorvido por C"): uma leitura só pode ser absorvida por
        UM item.
        """
        discarded_keys = [
            (link.discarded.plate_id, link.discarded.item_id) for link in self.identity_links
        ]
        kept_keys = {(link.kept.plate_id, link.kept.item_id) for link in self.identity_links}
        repeated_discarded = {key for key in discarded_keys if discarded_keys.count(key) > 1}
        conflicting = repeated_discarded | (kept_keys & set(discarded_keys))
        if conflicting:
            raise ValuationValidationError(
                "WORKSITE_LINK_CHAIN_NOT_SUPPORTED",
                "vínculos de identidade não podem formar cadeia: uma leitura descartada só "
                "pode ser absorvida por um item, e não pode também ser a parcela que fica de "
                "outro vínculo; declare o vínculo direto entre as duas pontas em vez de "
                "encadear",
                {"addresses": sorted(f"{p}:{i}" for p, i in conflicting)},
            )
        return self

    def discarded_addresses(self) -> frozenset[tuple[str, str]]:
        """Endereços `(plate_id, item_id)` que não contam: a parcela que NÃO fica.

        Usado por quem monta o boletim da praça (fora do escopo desta tarefa) para excluir
        a leitura absorvida por um vínculo de identidade sem contar duas vezes. Devolve um
        `frozenset`: a ordem em que os vínculos foram declarados nunca muda o resultado.
        """
        return frozenset(
            (link.discarded.plate_id, link.discarded.item_id) for link in self.identity_links
        )


def _ensure_links_target_known_items(
    worksite: WorksiteTakeoff, packets: Sequence[TakeoffPacket]
) -> None:
    """Confere que todo endereço de vínculo aponta para um item que existe de verdade.

    `WorksiteTakeoff.validate_link_targets_known` já recusa prancha fora do consolidado
    sozinho, sem precisar do conteúdo dos pacotes; esta função vai um nível mais fundo e
    confere o `item_id` dentro do pacote real — só possível com os pacotes em mãos.
    """
    items_by_plate = {packet.plate_id: {item.id for item in packet.items} for packet in packets}
    unknown: set[str] = set()
    for link in worksite.identity_links:
        for address in (link.kept, link.discarded):
            if address.item_id not in items_by_plate.get(address.plate_id, set()):
                unknown.add(f"{address.plate_id}:{address.item_id}")
    if unknown:
        raise ValuationValidationError(
            "WORKSITE_LINK_UNKNOWN_TARGET",
            "vínculo de identidade aponta para item que não existe no pacote da prancha",
            {"addresses": sorted(unknown)},
        )


def build_worksite_takeoff(
    worksite_key: str,
    packets: Sequence[TakeoffPacket],
    identity_links: Sequence[TakeoffItemIdentityLink] = (),
) -> WorksiteTakeoff:
    """Monta o consolidado da praça a partir dos pacotes de takeoff já extraídos.

    O digest de cada referência nasce do pacote em mãos — não há outra fonte de verdade
    sobre "qual é o conteúdo desta prancha" além do próprio pacote recém-lido. Um vínculo
    de identidade que aponte para item inexistente nos pacotes recebidos é recusado aqui,
    na montagem, em vez de só no consumo.
    """
    plates = [
        WorksitePlateReference(
            plate_id=packet.plate_id, packet_digest=takeoff_packet_digest(packet)
        )
        for packet in packets
    ]
    worksite = WorksiteTakeoff(
        worksite_key=worksite_key, plates=plates, identity_links=list(identity_links)
    )
    _ensure_links_target_known_items(worksite, packets)
    return worksite


def ensure_worksite_matches_packets(
    worksite: WorksiteTakeoff, packets: Sequence[TakeoffPacket]
) -> None:
    """Confere um consolidado já existente contra pacotes recarregados (ex.: de storage).

    Três recusas, na ordem em que uma releitura pode falhar: prancha referenciada sem
    pacote correspondente entre os recarregados (`WORKSITE_PACKET_MISSING`), pacote presente
    mas cujo conteúdo mudou desde a referência — reextração, edição
    (`WORKSITE_PACKET_DIGEST_MISMATCH`) —, e vínculo de identidade cujo alvo não existe em
    pacote nenhum (`WORKSITE_LINK_UNKNOWN_TARGET`).
    """
    packets_by_plate = {packet.plate_id: packet for packet in packets}
    for reference in worksite.plates:
        packet = packets_by_plate.get(reference.plate_id)
        if packet is None:
            raise ValuationValidationError(
                "WORKSITE_PACKET_MISSING",
                "consolidado referencia prancha sem pacote correspondente entre os recebidos",
                {"plate_id": reference.plate_id},
            )
        digest = takeoff_packet_digest(packet)
        if digest != reference.packet_digest:
            raise ValuationValidationError(
                "WORKSITE_PACKET_DIGEST_MISMATCH",
                "o conteúdo do pacote referenciado não confere com o digest do consolidado",
                {
                    "plate_id": reference.plate_id,
                    "expected": reference.packet_digest,
                    "actual": digest,
                },
            )
    _ensure_links_target_known_items(worksite, packets)
