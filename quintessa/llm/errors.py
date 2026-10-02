class LLMError(Exception):
    """Base class for adapter errors."""


class RetryableLLMError(LLMError):
    """Rate limits, overload, timeouts, 5xx: worth retrying the same model."""


class FatalLLMError(LLMError):
    """Bad request, auth, unknown model: move on to the next model."""


class RefusalError(LLMError):
    """The model declined. Move on to the next model."""


class InvalidOutputError(LLMError):
    """The model returned something that is not JSON matching the schema."""


class LLMUnavailableError(LLMError):
    """Every model in the chain failed."""

    def __init__(self, failures: list[str]):
        super().__init__("all models failed: " + "; ".join(failures))
        self.failures = failures
