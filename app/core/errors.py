class VerificaAIError(Exception):
    """Base error for expected application failures."""


class InputValidationError(VerificaAIError):
    pass


class UnsafeUrlError(VerificaAIError):
    pass


class RedirectLimitError(VerificaAIError):
    pass


class CollectionError(VerificaAIError):
    pass
