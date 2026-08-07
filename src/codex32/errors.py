"""codex32 / Bech32 / descriptor encoding and usage errors."""


class CodexError(Exception):
    """Base class for all codex32 / Bech32 errors."""

    def __init__(self, extra: str | None = None) -> None:
        self.extra = extra
        super().__init__(extra)

    def __str__(self) -> str:
        return str(self.extra) if self.extra else ""


class InvalidChar(CodexError):
    """Raised when an input string contains a character not permitted by the context."""


class SeparatorNotFound(CodexError):
    """Raised when a separator character is missing from an input string."""


class InvalidChecksum(CodexError):
    """Raised when a checksum verification fails."""
