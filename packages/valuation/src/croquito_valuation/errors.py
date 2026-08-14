"""Erros estruturados do contexto de medição de obra."""

from __future__ import annotations

from pydantic import ValidationError


class ValuationValidationError(ValueError):
    """Falha de invariante da medição.

    Espelha `croquito_core.errors.DomainValidationError`: código estável em inglês,
    mensagem de domínio em português e detalhes estruturados. Nenhum chamador deve fazer
    parsing da mensagem; use `code` e `details`.
    """

    def __init__(self, code: str, message: str, details: dict[str, object] | None = None) -> None:
        self.code = code
        self.message = message
        self.details: dict[str, object] = dict(details or {})
        super().__init__(f"{code}: {message}")


def valuation_errors(error: ValidationError) -> list[ValuationValidationError]:
    """Extrai os erros de domínio embutidos numa `ValidationError` do Pydantic.

    Um validador de modelo que levanta `ValuationValidationError` é encapsulado pelo
    Pydantic, que preserva a exceção original em `ctx["error"]`. Esta função devolve as
    exceções preservadas para que o chamador continue lendo `code`/`details` em vez de
    interpretar texto.
    """
    found: list[ValuationValidationError] = []
    for line in error.errors():
        context = line.get("ctx")
        if not isinstance(context, dict):
            continue
        original = context.get("error")
        if isinstance(original, ValuationValidationError):
            found.append(original)
    return found


def valuation_error_codes(error: ValidationError) -> list[str]:
    """Códigos de domínio presentes numa `ValidationError`, na ordem de ocorrência."""
    return [item.code for item in valuation_errors(error)]
