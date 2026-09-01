"""Bitcoin master-seed profile rules and validated secret type."""

from __future__ import annotations

from typing import Any

from bip32 import BIP32 as BIP32Node  # type: ignore[import-untyped]
from bip32 import InvalidInputError

from codex32.bech32 import convertbits
from codex32.bip93 import Header, Secret, _from_parts
from codex32.checksums import _crc_pad
from codex32.errors import CodexError, InvalidLength
from codex32.profiles import Profile

_SIZES = ((16, 26, 48), (20, 32, 54), (24, 39, 61), (28, 45, 67), (32, 52, 74), (64, 103, 127))
SEED_BYTE_LENGTHS, DEFAULT_SEED_BYTES = tuple(size[0] for size in _SIZES), 16
_PAYLOAD_LENGTHS = tuple(size[1] for size in _SIZES)


def _payload_length(byte_length: int) -> int:
    return (byte_length * 8 + 4) // 5


def _text_length(byte_length: int) -> int:
    payload_length = _payload_length(byte_length)
    return payload_length + (22 if payload_length + 22 <= 91 else 24)


TEXT_LENGTHS = tuple(size[2] for size in _SIZES)


def _payload_padding(secret: MasterSeed) -> int:
    padding_bits = (len(secret.payload_symbols) * 5) % 8
    return secret.payload_symbols[-1] & ((1 << padding_bits) - 1) if padding_bits else 0


def _has_generation_padding(secret: MasterSeed) -> bool:
    return _payload_padding(secret) == _crc_pad(secret.seed_bytes)


def _bip32_node(seed: bytes, *, testnet: bool = False) -> Any:
    try:
        return BIP32Node.from_seed(seed, "test" if testnet else "main")
    except InvalidInputError as error:
        raise CodexError("master seed does not form a valid BIP32 root") from error


def _fingerprint_from_seed(seed: bytes) -> bytes:
    return _bip32_node(seed).get_fingerprint()  # type: ignore[no-any-return]


class MasterSeed(Secret):
    """A validated BIP93 ``ms`` secret."""

    __slots__ = ()

    @property
    def seed_bytes(self) -> bytes:
        """Return the BIP32 master-seed bytes represented by S."""
        return bytes(convertbits(self.payload_symbols, 5, 8, pad=False, accept_any_padding=True))

    @classmethod
    def from_seed(cls, seed_bytes: bytes, *, identifier: str, threshold: int = 0) -> MasterSeed:
        """Encode a supported BIP93 master seed as S with generation-only CRC padding."""
        if not isinstance(seed_bytes, bytes):
            raise TypeError("seed_bytes must be bytes")
        if len(seed_bytes) not in SEED_BYTE_LENGTHS:
            raise InvalidLength("master seed must contain 16, 20, 24, 28, 32, or 64 bytes")
        payload = tuple(convertbits(seed_bytes, 8, 5, pad=True, pad_value=_crc_pad(seed_bytes)))
        artifact = _from_parts(Profile.MS, Header(threshold, identifier, "s"), payload)
        assert isinstance(artifact, MasterSeed)
        return artifact


class _Ms32Rules:
    profile, label, secret_type = Profile.MS, "Bitcoin master seed", MasterSeed
    completion_error: str | None = None
    basis_secret_type: type[Secret] | None = None
    basis_error = ""

    def validate_text_length(self, text_length: int) -> None:
        if text_length not in TEXT_LENGTHS:
            raise InvalidLength(
                f"This input has {text_length} characters. A Bitcoin master-seed backup must have "
                "exactly 48, 54, 61, 67, 74, or 127 characters."
            )

    def validate_payload_length(self, payload_length: int) -> None:
        if payload_length not in _PAYLOAD_LENGTHS:
            raise InvalidLength(
                "This input has the wrong length for a Bitcoin master-seed backup; expected a "
                "16-, 20-, 24-, 28-, 32-, or 64-byte seed."
            )

    def validate_payload(self, _payload: tuple[int, ...], _index: str) -> None:
        pass


RULES = _Ms32Rules()
