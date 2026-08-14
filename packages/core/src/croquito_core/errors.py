"""Erros públicos do domínio."""


class DomainValidationError(ValueError):
    """Indica que uma cena não satisfaz os invariantes de domínio."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))
