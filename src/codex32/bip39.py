"""Isolated validation for migration-only BIP39 codex32 profiles."""

import hashlib

from codex32.errors import InvalidBip39Checksum, InvalidPadding, InvalidPayload
from codex32.profiles import Profile


def _validate_bip39_secret(profile: Profile, symbols: tuple[int, ...]) -> None:
    """Validate outer padding and embedded BIP39 checksum for an S artifact."""
    if profile is Profile.BIP39_12W:
        entropy_bits, checksum_bits, outer_padding = 128, 4, 3
    elif profile is Profile.BIP39_24W:
        entropy_bits, checksum_bits, outer_padding = 256, 8, 1
    else:
        raise InvalidPayload(f"{profile} is not a BIP39 migration profile")

    bits = [(symbol >> bit) & 1 for symbol in symbols for bit in range(4, -1, -1)]
    if any(bits[-outer_padding:]):
        raise InvalidPadding("BIP39 S requires zero outer u5 padding")
    semantic = bits[:-outer_padding]
    entropy = semantic[:entropy_bits]
    embedded = semantic[entropy_bits : entropy_bits + checksum_bits]
    entropy_bytes = bytes(
        sum(entropy[offset + bit] << (7 - bit) for bit in range(8)) for offset in range(0, entropy_bits, 8)
    )
    digest = hashlib.sha256(entropy_bytes).digest()
    expected = [(digest[0] >> (7 - bit)) & 1 for bit in range(checksum_bits)]
    if embedded != expected:
        raise InvalidBip39Checksum("embedded BIP39 entropy checksum is invalid")
