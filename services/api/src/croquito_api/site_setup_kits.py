"""Acervo de parcelas de canteiro na fronteira da API: o que a rota decide antes de HTTP.

Camada de aplicação sem FastAPI, como `reference_catalogs.py` e `estimate_rounds.py`: nada
aqui recebe `Request`, monta `Response` nem conhece código de status por si só. O motor do
domínio é `croquito_valuation.site_setup` e não é reimplementado em lugar nenhum deste
módulo — `apply_site_setup_kit` e `preview_site_setup_kit` continuam sendo quem resolve
parâmetro, recusa por extenso e materializa contribuição.

O que mora aqui é o pouco que precisa de UMA fonte deste lado da fronteira (F-042 T2,
ADR-0060):

- **a cláusula de tenant** (`visible_kits`), que é a fronteira do ADR-0060 escrita uma vez:
  `tenant_id IS NULL OR tenant_id = :tenant`. Repetida em cada rota, ela divergiria no dia em
  que uma rota nova esquecesse metade;
- **a semântica de merge** (`merge_site_setup_contributions`), que é o que torna reaplicar o
  mesmo acervo idempotente sem apagar trabalho manual;
- **a autoria** (`author_site_setup_kit`), que converte parcelas `STANDALONE` já feitas em
  acervo, com os parâmetros DECLARADOS por gente — o sistema nunca infere qual número é
  parâmetro;
- os payloads que a tela lê, todos com decimal como **texto** na fronteira HTTP.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from typing import Any, Final

from sqlalchemy import or_
from sqlalchemy.sql.elements import ColumnElement

from croquito_api.database import SiteSetupKitRecord
from croquito_api.valuation_rounds import RoundRefusal, document_digest
from croquito_valuation.calc_matrix import CalcContribution, CalcMatrix, ServiceContributions
from croquito_valuation.models import CalcOperand, ContributionBasis
from croquito_valuation.site_setup import (
    SiteSetupKit,
    SiteSetupOperand,
    SiteSetupParcel,
    SiteSetupPreviewRow,
)

SITE_SETUP_KIT_ALREADY_PUBLISHED: Final = "SITE_SETUP_KIT_ALREADY_PUBLISHED"
SITE_SETUP_KIT_WITHDRAWN: Final = "SITE_SETUP_KIT_WITHDRAWN"
SITE_SETUP_PARAMETER_INVALID: Final = "SITE_SETUP_PARAMETER_INVALID"
SITE_SETUP_BINDING_INVALID: Final = "SITE_SETUP_BINDING_INVALID"
SITE_SETUP_KIT_EMPTY: Final = "SITE_SETUP_KIT_EMPTY"

ORIGIN_PLATFORM: Final = "platform"
"""Acervo publicado pela plataforma, válido para todos os tenants (`tenant_id IS NULL`)."""

ORIGIN_TENANT: Final = "tenant"
"""Acervo autorado pela orçamentista, visível só ao tenant dela."""

_BINDING_KEY_PATTERN: Final = re.compile(r"^(\d+)\.(.+)$")
"""`<índice da contribuição STANDALONE>.<nome do operando>`, o que o corpo da autoria fala."""


# --- fronteira de tenant ------------------------------------------------------------------


def visible_kits(tenant_id: str) -> ColumnElement[bool]:
    """A cláusula do ADR-0060, escrita UMA vez: plataforma **mais** o acervo deste tenant.

    Acervo de plataforma (`tenant_id IS NULL`) é de todos; acervo do tenant é só dele. Nunca
    uma metade sozinha: só a de plataforma esconderia da orçamentista o acervo que ela mesma
    autorou, e a ausência da cláusula mostraria a um tenant o acervo de outro — que é
    exatamente a fronteira que o ADR preserva.
    """
    return or_(SiteSetupKitRecord.tenant_id.is_(None), SiteSetupKitRecord.tenant_id == tenant_id)


def kit_origin(record: SiteSetupKitRecord) -> str:
    """`platform` ou `tenant`, derivado da coluna — nunca gravado como um terceiro campo."""
    return ORIGIN_PLATFORM if record.tenant_id is None else ORIGIN_TENANT


# --- leitura do documento -----------------------------------------------------------------


def load_kit(record: SiteSetupKitRecord) -> SiteSetupKit:
    """O acervo gravado, revalidado na leitura.

    Espelha `matrix_of`/`assignments_of` (`estimate_rounds.py`): o artefato passa pelo
    validador do domínio de novo toda vez que sai do banco, e não só quando entrou.
    """
    return SiteSetupKit.model_validate(record.document_json)


def kit_document_digest(document: Mapping[str, Any]) -> str:
    """Digest canônico do documento do acervo, o mesmo de toda coluna JSON de revisão."""
    return document_digest(document)


def already_published(name: str, kit_version: str) -> RoundRefusal:
    """Mesma `(name, kit_version)` no mesmo acervo: recusa, nunca sobrescrita.

    Acervo é imutável, como o catálogo de referência (ADR-0047 D3): uma rodada que já aplicou
    a versão `1.0.0` cita essa versão nas parcelas que ela materializou, e reescrever o
    conteúdo por baixo mudaria, em silêncio, o que aquelas parcelas dizem ter nascido de.
    Versão nova é linha nova.
    """
    return RoundRefusal(
        409,
        SITE_SETUP_KIT_ALREADY_PUBLISHED,
        "já existe acervo com este nome e versão; acervo é imutável e versão nova é entrada nova",
        {"name": name, "kit_version": kit_version},
    )


def kit_withdrawn(kit_id: str) -> RoundRefusal:
    """Acervo fora de circulação não é aplicável; a linha continua existindo."""
    return RoundRefusal(
        409,
        SITE_SETUP_KIT_WITHDRAWN,
        "este acervo saiu de circulação e não é mais oferecido para aplicação nova",
        {"kit_id": kit_id},
    )


# --- parâmetros de obra -------------------------------------------------------------------


def parse_parameters(raw: Mapping[str, str]) -> dict[str, Decimal]:
    """Os parâmetros declarados pela orçamentista, como `Decimal` exato.

    Viajam como TEXTO pelo mesmo motivo do BDI e da quantidade do takeoff (ADR-0038, decisão
    2): eles alimentam `CalcOperand.value`, que é `ExactDecimal` e recusa `float` — um número
    de JSON já teria passado por binário antes de chegar aqui.

    Texto ilegível, infinito ou negativo recusam **nomeando todos** os parâmetros ruins de uma
    vez, e não o primeiro: quem preencheu meia dúzia de campos precisa saber quais corrigir
    sem descobrir um por requisição. Zero é aceito de propósito — diferente da constante do
    acervo, que é curada e distribuída, o parâmetro é declarado pela orçamentista e conferido
    por ela na pré-visualização, que mostra a conta.
    """
    parsed: dict[str, Decimal] = {}
    invalid: list[str] = []
    for name, value in raw.items():
        try:
            number = Decimal(value)
        except InvalidOperation:
            invalid.append(name)
            continue
        if not number.is_finite() or number < 0:
            invalid.append(name)
            continue
        parsed[name] = number
    if invalid:
        raise RoundRefusal(
            422,
            SITE_SETUP_PARAMETER_INVALID,
            "parâmetro de obra precisa ser um número decimal exato, finito e não negativo",
            {"parameters": sorted(invalid)},
        )
    return parsed


def kit_parameters_payload(kit: SiteSetupKit) -> list[dict[str, Any]]:
    """Os parâmetros que o acervo cita, com unidade e quantas parcelas citam cada um.

    A ordem é a de `SiteSetupKit.parameter_names()` — primeira aparição —, que é a ordem em
    que a tela pede os campos.

    `unit` é a unidade do PRIMEIRO operando que cita o parâmetro. Quando os operandos
    discordam entre si, sai `null` em vez de um dos dois: escolher um faria a tela rotular o
    campo com uma unidade que metade das parcelas desmente. Discordância **não** recusa o
    acervo — ela é dado de autoria, e a pré-visualização mostra a conta de cada parcela com a
    unidade que aquela parcela declarou.
    """
    units: dict[str, list[str | None]] = {}
    citing_parcels: dict[str, set[str]] = {}
    for parcel in kit.parcels:
        for operand in (*parcel.operands, *parcel.deductions):
            if operand.parameter is None:
                continue
            units.setdefault(operand.parameter, []).append(operand.unit)
            citing_parcels.setdefault(operand.parameter, set()).add(parcel.id)
    payload: list[dict[str, Any]] = []
    for name in kit.parameter_names():
        declared = units[name]
        payload.append(
            {
                "name": name,
                "unit": declared[0] if len(set(declared)) == 1 else None,
                "cited_by": len(citing_parcels[name]),
            }
        )
    return payload


# --- payloads que a tela lê ---------------------------------------------------------------


def kit_option_payload(record: SiteSetupKitRecord, kit: SiteSetupKit) -> dict[str, Any]:
    """O acervo como a ESCOLHA da rodada o oferece.

    `created_by` não sai: num acervo de plataforma ele é a identidade de um operador de outro
    tenant, e quem escolhe um acervo não tem por que saber quem o publicou — é a mesma razão
    de `EstimateReferenceCatalogOption` ser mais pobre que `ReferenceCatalogResponse`.
    """
    return {
        "kit_id": record.id,
        "name": record.name,
        "kit_version": record.kit_version,
        "origin": kit_origin(record),
        "source_label": record.source_label,
        "parcel_count": len(kit.parcels),
        "parameters": kit_parameters_payload(kit),
        "created_at": record.created_at,
    }


def preview_row_payload(row: SiteSetupPreviewRow) -> dict[str, Any]:
    """Uma linha da pré-visualização; todo decimal como TEXTO, como no resto da jornada."""
    return {
        "parcel_id": row.parcel_id,
        "code": row.code,
        "label": row.label,
        "operands": [
            {"name": operand.name, "value": str(operand.value), "unit": operand.unit}
            for operand in row.operands
        ],
        "quantity": str(row.quantity),
    }


# --- merge na matriz ----------------------------------------------------------------------


def merge_site_setup_contributions(
    existing: CalcMatrix | None,
    produced: Sequence[ServiceContributions],
    *,
    kit_version: str,
) -> tuple[CalcMatrix, int]:
    """A matriz resultante de aplicar o acervo, e quantas parcelas dele foram substituídas.

    É o coração do apply, e a regra é uma só: **reaplicar substitui apenas as parcelas
    daquele acervo**.

    - toda contribuição cuja `kit_origin.kit_version` seja igual à do acervo aplicado sai —
      são as da aplicação ANTERIOR do mesmo acervo, e mantê-las duplicaria cada parcela a cada
      reaplicação;
    - toda outra contribuição sobrevive INTACTA: a autorada à mão (`kit_origin` nulo) e a de
      OUTRO acervo. Apagar a primeira jogaria fora o trabalho que a feature existe para
      preservar; apagar a segunda faria dois acervos serem mutuamente exclusivos sem que
      ninguém tivesse decidido isso;
    - as parcelas novas entram no serviço que já existe, quando o código já está na matriz, e
      abrem serviço novo no fim quando não está. A ordem dos serviços que já existiam não muda.

    Serviço que fica sem nenhuma contribuição é REMOVIDO, não gravado vazio: `ServiceContributions`
    exige pelo menos uma parcela, e um serviço vazio na matriz seria uma linha de boletim sem
    memória de cálculo.

    A chave do merge é a `kit_version`, e não o `kit_id`, porque é ela que a proveniência de
    cada parcela materializada carrega (`SiteSetupOrigin`, `models.py`) — o motor do domínio é
    quem define isso, e ele não é alterado nesta task. A consequência conhecida está declarada:
    dois acervos DIFERENTES que declarem a mesma `version` são indistinguíveis na matriz, e
    aplicar um substituiria as parcelas do outro.
    """
    kept: list[tuple[str, list[CalcContribution]]] = []
    replaced = 0
    if existing is not None:
        for service in existing.services:
            survivors: list[CalcContribution] = []
            for contribution in service.contributions:
                origin = contribution.kit_origin
                if origin is not None and origin.kit_version == kit_version:
                    replaced += 1
                    continue
                survivors.append(contribution)
            kept.append((service.code, survivors))

    by_code = {code: contributions for code, contributions in kept}
    for service in produced:
        target = by_code.get(service.code)
        if target is None:
            fresh = list(service.contributions)
            kept.append((service.code, fresh))
            by_code[service.code] = fresh
            continue
        target.extend(service.contributions)

    return (
        CalcMatrix(
            services=[
                ServiceContributions(code=code, contributions=contributions)
                for code, contributions in kept
                if contributions
            ]
        ),
        replaced,
    )


# --- autoria do acervo pela orçamentista --------------------------------------------------


def standalone_contributions(matrix: CalcMatrix) -> list[tuple[str, CalcContribution]]:
    """As parcelas `STANDALONE` da matriz, com o código do serviço, na ordem em que ela as tem.

    Essa ordem **é** o índice que os bindings citam: serviços na ordem da matriz e, dentro de
    cada serviço, parcelas na ordem gravada. Contribuição com origem em elemento da prancha não
    entra — o acervo é só de canteiro, por definição da feature.
    """
    return [
        (service.code, contribution)
        for service in matrix.services
        for contribution in service.contributions
        if contribution.basis is ContributionBasis.STANDALONE
    ]


def _parcel_id(*, kit_version: str, index: int, code: str, label: str) -> str:
    """Id estável da parcela DENTRO do acervo, derivado do que ela é.

    Determinístico no molde de `_approval_decision_id` (`estimate_rounds.py`): autorar duas
    vezes o mesmo conteúdo produz o mesmo id, e um id que muda sem o conteúdo mudar não
    identifica nada. O índice entra na chave porque duas parcelas do mesmo código e rótulo são
    legítimas — a planilha real tem `1 x 2 meses` para container e banheiro no mesmo código.
    """
    canonical = json.dumps(
        {"kit_version": kit_version, "index": index, "code": code, "label": label},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"ss_{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:16]}"


def _binding_index(raw: Mapping[str, str], *, contribution_count: int) -> dict[int, dict[str, str]]:
    """Bindings agrupados por contribuição, com a chave conferida antes de qualquer uso.

    Chave que não tem a forma `<índice>.<operando>`, ou cujo índice não existe entre as
    parcelas `STANDALONE` da rodada, recusa NOMEANDO o binding — nunca é ignorada em silêncio.
    Um binding ignorado transformaria um parâmetro que a orçamentista quis declarar numa
    constante congelada, e o acervo nasceria errado sem ninguém ver.
    """
    grouped: dict[int, dict[str, str]] = {}
    invalid: list[str] = []
    for key, parameter in raw.items():
        match = _BINDING_KEY_PATTERN.match(key)
        if match is None:
            invalid.append(key)
            continue
        index = int(match.group(1))
        if index >= contribution_count:
            invalid.append(key)
            continue
        grouped.setdefault(index, {})[match.group(2)] = parameter
    if invalid:
        raise binding_invalid(invalid)
    return grouped


def binding_invalid(bindings: Sequence[str]) -> RoundRefusal:
    """Binding que não aponta para operando existente: recusa que nomeia os bindings."""
    return RoundRefusal(
        422,
        SITE_SETUP_BINDING_INVALID,
        "declaração de parâmetro aponta para operando que a rodada não tem",
        {"bindings": sorted(bindings)},
    )


def author_site_setup_kit(
    matrix: CalcMatrix,
    *,
    kit_version: str,
    source_label: str,
    parameter_bindings: Mapping[str, str],
) -> SiteSetupKit:
    """Converte as parcelas `STANDALONE` da rodada num acervo, com os parâmetros DECLARADOS.

    O sistema **não** infere qual número é parâmetro (é o aviso do estado 09 do Design
    Approval Package): `1 x 2` pode ser "uma unidade por dois meses de obra" ou "duas placas de
    um metro", e adivinhar produziria um acervo que nasce errado e só é descoberto na praça
    seguinte. Todo operando não citado por um binding vira CONSTANTE.

    Um binding vale para o operando **e** para a dedução de mesmo nome dentro da mesma
    contribuição, porque a chave nomeia o operando pelo `name` que a memória imprime, e o
    modelo não distingue os dois espaços de nome. Nome que não existe em nenhum dos dois é
    recusa que nomeia o binding.

    Nada aqui é gravado: a função devolve o `SiteSetupKit` já validado pelo domínio, e quem o
    persiste é a rota.
    """
    contributions = standalone_contributions(matrix)
    if not contributions:
        raise RoundRefusal(
            422,
            SITE_SETUP_KIT_EMPTY,
            "a rodada não tem nenhuma parcela de canteiro para virar acervo",
            {},
        )
    grouped = _binding_index(parameter_bindings, contribution_count=len(contributions))

    # Toda a conferência de binding corre ANTES de qualquer parcela ser construída: falha
    # fechada, como no motor do domínio. Construir primeiro faria um operando inválido de
    # outra parcela recusar antes, e a mensagem falaria de qualquer coisa menos do binding
    # que a orçamentista errou.
    unmatched: list[str] = []
    for index, (_, contribution) in enumerate(contributions):
        names = {operand.name for operand in (*contribution.operands, *contribution.deductions)}
        unmatched.extend(f"{index}.{name}" for name in grouped.get(index, {}) if name not in names)
    if unmatched:
        raise binding_invalid(unmatched)

    parcels = [
        SiteSetupParcel(
            id=_parcel_id(
                kit_version=kit_version, index=index, code=code, label=contribution.label
            ),
            code=code,
            label=contribution.label,
            recipe=contribution.recipe,
            operands=[
                _authored_operand(operand, grouped.get(index, {}))
                for operand in contribution.operands
            ],
            deductions=[
                _authored_operand(operand, grouped.get(index, {}))
                for operand in contribution.deductions
            ],
            note=contribution.note,
        )
        for index, (code, contribution) in enumerate(contributions)
    ]
    return SiteSetupKit(version=kit_version, source_label=source_label, parcels=parcels)


def _authored_operand(operand: CalcOperand, bindings: Mapping[str, str]) -> SiteSetupOperand:
    """Operando citado por binding vira REFERÊNCIA a parâmetro; o resto vira constante."""
    parameter = bindings.get(operand.name)
    if parameter is not None:
        return SiteSetupOperand(name=operand.name, parameter=parameter, unit=operand.unit)
    return SiteSetupOperand(name=operand.name, value=operand.value, unit=operand.unit)


def kit_record_payload(record: SiteSetupKitRecord, kit: SiteSetupKit) -> dict[str, Any]:
    """A linha do acervo como a ADMINISTRAÇÃO da plataforma a lê; o documento não sai daqui.

    O `SiteSetupKit` inteiro seria dezenas de parcelas com rótulo e operando por resposta de
    listagem; quem precisa dele é o preview, que o lê do banco. O que sai aqui é o que
    distingue duas linhas na lista.
    """
    return {
        "kit_id": record.id,
        "name": record.name,
        "kit_version": record.kit_version,
        "origin": kit_origin(record),
        "source_label": record.source_label,
        "parcel_count": len(kit.parcels),
        "document_sha256": record.document_sha256,
        "available": record.withdrawn_at is None,
        "created_by": record.created_by,
        "created_at": record.created_at,
        "withdrawn_at": record.withdrawn_at,
    }
