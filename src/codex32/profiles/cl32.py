"""Core Lightning HSM-secret profile rules and validated secret type."""

from __future__ import annotations

from codex32.bech32 import convertbits
from codex32.bip93 import Header, Secret, _from_parts
from codex32.errors import InvalidLength
from codex32.profiles import Profile

SECRET_BYTES, PAYLOAD_LENGTH, TEXT_LENGTH = 32, 52, 74


def _has_generation_padding(secret: CoreLightningSecret) -> bool:
    return secret.payload_symbols[-1] & 15 == 0


class CoreLightningSecret(Secret):
    """A validated 32-byte Core Lightning HSM secret."""

    __slots__ = ()

    @property
    def secret_bytes(self) -> bytes:
        """Return the 32-byte Core Lightning HSM secret represented by S."""
        return bytes(convertbits(self.payload_symbols, 5, 8, pad=False, accept_any_padding=True))


def _secret_from_bytes(
    secret_bytes: bytes,
    identifier: str,
    threshold: int = 0,
) -> CoreLightningSecret:
    if not isinstance(secret_bytes, bytes):
        raise TypeError("secret_bytes must be bytes")
    if len(secret_bytes) != SECRET_BYTES:
        raise InvalidLength("Core Lightning secrets must contain exactly 32 bytes")
    payload = tuple(convertbits(secret_bytes, 8, 5, pad=True, pad_value=0))
    artifact = _from_parts(Profile.CL, Header(threshold, identifier, "s"), payload)
    assert isinstance(artifact, CoreLightningSecret)
    return artifact


class _Cl32Rules:
    profile, label = Profile.CL, "Core Lightning HSM secret"
    secret_type = CoreLightningSecret
    completion_error: str | None = None
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

    def validate_payload(self, _payload: tuple[int, ...], _index: str) -> None:
        pass


RULES = _Cl32Rules()
