"""Core Lightning HSM-secret profile rules and validated secret type."""

from __future__ import annotations

from codex32.bech32 import convertbits
from codex32.bip93 import Header, Secret
from codex32.errors import InvalidLength, InvalidThreshold
from codex32.profiles import Profile

PAYLOAD_LENGTH, TEXT_LENGTH = 52, 74


class CoreLightningSecret(Secret):
    """A validated 32-byte Core Lightning HSM secret."""

    __slots__ = ()

    @property
    def secret_bytes(self) -> bytes:
        """Return the 32-byte Core Lightning HSM secret represented by S."""
        return bytes(convertbits(self.payload_symbols, 5, 8, pad=False, accept_any_padding=True))


class _Cl32Rules:
    profile, label = Profile.CL, "Core Lightning HSM secret"
    secret_type = CoreLightningSecret
    basis_secret_type: type[Secret] | None = None
    basis_error = ""

    def validate_text_length(self, text_length: int) -> None:
        if text_length != TEXT_LENGTH:
            raise InvalidLength(
                f"This input has {text_length} characters. A Core Lightning HSM secret backup "
                f"must have exactly {TEXT_LENGTH}."
            )

    def validate_payload_length(self, payload_length: int) -> None:
        if payload_length != PAYLOAD_LENGTH:
            raise InvalidLength(
                "This input has the wrong length for a Core Lightning HSM secret backup; "
                f"expected a {TEXT_LENGTH}-character codex32 string."
            )

    def validate_payload(self, _payload: tuple[int, ...], header: Header) -> None:
        # Core Lightning rejects shares and shared S strings, so neither is a CL backup.
        if header.threshold != 0:
            raise InvalidThreshold("A Core Lightning HSM secret backup must be unshared, with threshold 0.")


RULES = _Cl32Rules()
