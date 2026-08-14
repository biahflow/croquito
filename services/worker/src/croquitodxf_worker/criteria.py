"""Critério de escopo do caso: código, texto e a issue crítica que o representa.

O mesmo critério atravessa a semeadura da evidência, os dois motores de geometria
(retangular e traçado) e a aprovação. Construir a issue num lugar só é o que impede um
caminho novo até o DXF nascer sem o portão do critério (ADR-0017).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Collection, Mapping, Sequence
from typing import Final
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from croquitodxf_core.models import Issue, IssueSeverity, IssueStatus

CRITERION_CODE_PATTERN = r"^[A-Z0-9_]{3,64}$"
"""Código de máquina do critério; é o mesmo formato que `Issue.code` impõe."""

CRITERION_PATTERN: Final = re.compile(CRITERION_CODE_PATTERN)

CRITERION_TEXT_MAX_CHARS: Final = 500
"""Limite de `Issue.message`: o texto do critério vira a mensagem da issue."""

FALLBACK_CRITERION_MESSAGE = "Critério do caso ainda não está coberto pela cena métrica."
"""Mensagem de quem não tem texto: revisão semeada antes de o texto viajar."""


class CriterionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ScopeCriterion(CriterionModel):
    """Critério de cobertura declarado quando a evidência do caso foi carregada."""

    code: str = Field(pattern=CRITERION_CODE_PATTERN)
    text: str | None = Field(default=None, min_length=1, max_length=CRITERION_TEXT_MAX_CHARS)


class ScopeCriterionError(ValueError):
    """Declaração de critério fora do contrato; carrega o código estável de recusa."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def parse_criterion_declaration(value: str) -> ScopeCriterion:
    """Lê `CODE` ou `CODE=Texto do critério`; o texto pode conter `=`."""
    code, separator, text = value.partition("=")
    code = code.strip()
    if not CRITERION_PATTERN.fullmatch(code):
        raise ScopeCriterionError("INVALID_CRITERION_CODE")
    if not separator:
        return ScopeCriterion(code=code)
    stripped = text.strip()
    if not 1 <= len(stripped) <= CRITERION_TEXT_MAX_CHARS:
        raise ScopeCriterionError("INVALID_CRITERION_TEXT")
    return ScopeCriterion(code=code, text=stripped)


def criterion_message(code: str, texts: Mapping[str, str]) -> str:
    """Texto declarado no caso; sem ele, a frase padrão — nunca o código cru sozinho."""
    return texts.get(code) or FALLBACK_CRITERION_MESSAGE


def scope_criteria_issues(
    codes: Sequence[str],
    texts: Mapping[str, str],
    *,
    id_factory: Callable[[str], UUID] | None = None,
) -> list[Issue]:
    """Uma issue crítica aberta por critério exigido, com o texto do caso quando existe.

    `id_factory` serve ao traçado, cujas issues têm id determinístico por cena; o fluxo
    retangular deixa o id ser gerado pelo contrato.
    """
    issues: list[Issue] = []
    for code in codes:
        message = criterion_message(code, texts)
        if id_factory is None:
            issues.append(Issue(code=code, severity=IssueSeverity.CRITICAL, message=message))
            continue
        issues.append(
            Issue(
                id=id_factory(code),
                code=code,
                severity=IssueSeverity.CRITICAL,
                message=message,
            )
        )
    return issues


def apply_criteria_declarations(
    issues: Sequence[Issue],
    *,
    covered: Collection[str],
    acknowledged: Collection[str],
) -> list[Issue]:
    """Coberto pela cena vira `RESOLVED`; pendente reconhecido vira `ACCEPTED`.

    Issue não declarada é devolvida intacta: critério exigido sem declaração continua
    `OPEN` e o portão de exportação segue bloqueando.
    """
    declared: list[Issue] = []
    for issue in issues:
        if issue.code in covered:
            declared.append(issue.model_copy(update={"status": IssueStatus.RESOLVED}))
        elif issue.code in acknowledged:
            declared.append(issue.model_copy(update={"status": IssueStatus.ACCEPTED}))
        else:
            declared.append(issue)
    return declared
