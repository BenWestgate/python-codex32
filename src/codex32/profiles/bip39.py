"""Migration-only BIP39 profile rules and validated secret type."""

import hashlib
from dataclasses import dataclass

from codex32.bip93 import Secret
from codex32.errors import (
    InvalidBip39Checksum,
    InvalidLength,
    InvalidPadding,
)
from codex32.profiles import Profile


class Bip39Secret(Secret):
    """Migration-only BIP39 S artifact without entropy or mnemonic access."""

    __slots__ = ()


@dataclass(frozen=True, slots=True)
class _Bip39Rules:
    profile: Profile
    label: str
    text_length: int
    payload_length: int
    entropy_bits: int
    checksum_bits: int
    outer_padding: int
    secret_type = Bip39Secret
    completion_error = "checksum completion is not available for BIP39 worksheet profiles"
    basis_secret_type: type[Secret] | None = Bip39Secret
    basis_error = "BIP39 basis did not imply a valid BIP39 secret"

    def validate_text_length(self, text_length: int) -> None:
        if text_length != self.text_length:
            raise InvalidLength(
                f"This input has {text_length} characters. A {self.label} backup must have "
                f"exactly {self.text_length}."
            )

    def validate_payload_length(self, payload_length: int) -> None:
        if payload_length != self.payload_length:
            article = "an" if self.text_length == 82 else "a"
            raise InvalidLength(
                f"This input has the wrong length for a {self.label} backup; expected {article} "
                f"{self.text_length}-character codex32 string."
            )

    def validate_payload(self, symbols: tuple[int, ...], index: str) -> None:
        if index != "s":
            return
        value = 0
        for symbol in symbols:
            value = value << 5 | symbol
        if value & ((1 << self.outer_padding) - 1):
            raise InvalidPadding("BIP39 S requires zero outer u5 padding")
        semantic = value >> self.outer_padding
        embedded = semantic & ((1 << self.checksum_bits) - 1)
        entropy = semantic >> self.checksum_bits
        entropy_bytes = entropy.to_bytes(self.entropy_bits // 8)
        expected = hashlib.sha256(entropy_bytes).digest()[0] >> (8 - self.checksum_bits)
        if embedded != expected:
            raise InvalidBip39Checksum("embedded BIP39 entropy checksum is invalid")


BIP39_12W_RULES = _Bip39Rules(Profile.BIP39_12W, "12-word BIP39 worksheet", 56, 27, 128, 4, 3)
BIP39_24W_RULES = _Bip39Rules(Profile.BIP39_24W, "24-word BIP39 worksheet", 82, 53, 256, 8, 1)
