# Portions of interpolation arithmetic are derived from rust-codex32 (BSD-3-Clause).
"""Immutable BIP93 artifacts, parsing, recovery, and share derivation."""

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import islice

from codex32.bech32 import (
    CHARSET,
    _chars_to_u5,
    _u5_to_chars,
    bech32_decode,
    bech32_encode,
    bech32_verify_checksum,
    convertbits,
)
from codex32.checksums import _CODEX32, _CODEX32_LONG, _Checksum, _crc_pad
from codex32.errors import (
    DuplicateShareIndex,
    ExistingTargetIndex,
    InvalidChecksum,
    InvalidIdentifier,
    InvalidLength,
    InvalidShareIndex,
    InvalidTargetIndex,
    InvalidThreshold,
    MismatchedHrp,
    MismatchedIdentifier,
    MismatchedPayloadLength,
    MismatchedThreshold,
    SecretInRecoverySet,
    WrongShareCount,
)
from codex32.gf32 import _inverse as _gf32_inverse
from codex32.gf32 import _multiply as _gf32_multiply

IDX_SORT = "sacdefghjklmnpqrtuvwxyz023456789"

# BIP93 master seeds: the "ms" HRP with one of six seed sizes (bytes, payload, text).
MS = "ms"
_MS_SIZES = ((16, 26, 48), (20, 32, 54), (24, 39, 61), (28, 45, 67), (32, 52, 74), (64, 103, 127))
SEED_BYTE_LENGTHS, DEFAULT_SEED_BYTES = tuple(size[0] for size in _MS_SIZES), 16
TEXT_LENGTHS = tuple(size[2] for size in _MS_SIZES)


def _payload_length(byte_length: int) -> int:
    return (byte_length * 8 + 4) // 5


def _text_length(byte_length: int) -> int:
    payload_length = _payload_length(byte_length)
    return payload_length + (22 if payload_length + 22 <= 91 else 24)


def _validate_ms_length(hrp: str, text_length: int) -> None:
    if hrp == MS and text_length not in TEXT_LENGTHS:
        raise InvalidLength(
            f"This input has {text_length} characters. A Bitcoin master-seed backup must have "
            "exactly 48, 54, 61, 67, 74, or 127 characters."
        )


def _header(threshold: object, identifier: object, index: object) -> str:
    """Return a normalized six-character BIP93 header, or raise why it is invalid."""
    if isinstance(threshold, bool) or not isinstance(threshold, int) or threshold not in (0, *range(2, 10)):
        raise InvalidThreshold("threshold must be 0 or an integer from 2 through 9")
    if (
        not isinstance(identifier, str)
        or len(identifier) != 4
        or any(c not in CHARSET for c in identifier.lower())
    ):
        raise InvalidIdentifier("identifier must be exactly four Bech32 symbols")
    if not isinstance(index, str) or len(index) != 1 or index.lower() not in CHARSET:
        raise InvalidShareIndex("share index must be one Bech32 symbol")
    if threshold == 0 and index.lower() != "s":
        raise InvalidShareIndex("An unshared secret (threshold 0) must use S as its index.")
    return f"{threshold}{identifier}{index}".lower()


def _checksum_for_encoded_length(hrp: str, encoded_length: int) -> _Checksum:
    expanded_length = 2 * len(hrp) + 1 + encoded_length
    if expanded_length <= 93:
        return _CODEX32
    if expanded_length < 96:
        raise InvalidLength("expanded codex32 lengths 94 and 95 are invalid")
    if expanded_length <= 1023:
        return _CODEX32_LONG
    raise InvalidLength("expanded codex32 codeword exceeds 1023 symbols")


def _decode_codex32(text: str) -> tuple[str, tuple[int, ...], _Checksum]:
    hrp, encoded = bech32_decode(text)
    if len(hrp) + 1 + len(encoded) < 21:
        raise InvalidLength("codex32 string must contain at least 21 characters")
    checksum = _checksum_for_encoded_length(hrp, len(encoded))
    body = tuple(encoded[: -checksum.length])
    if len(body) < 6:
        raise InvalidLength("codex32 header must contain six symbols")
    header = _u5_to_chars(body[:6])
    if header[0] not in "023456789":
        raise InvalidThreshold(f"The threshold must be 0 or a number from 2 through 9; found {header[0]!r}.")
    _header(int(header[0]), header[1:5], header[5])
    if not bech32_verify_checksum(hrp, encoded, checksum):
        raise InvalidChecksum("The checksum does not match.")
    _validate_ms_length(hrp, len(text))
    return hrp, tuple(encoded), checksum


@dataclass(frozen=True, slots=True)
class Codex32String:
    """A validated codex32 share or secret; ``.s`` is the explicit serialized value.

    Every other attribute is read from ``s``. ``str()`` and ``repr()`` are
    deliberately redacted so accidental logging or interpolation does not
    disclose recovery material.
    """

    s: str

    def __post_init__(self) -> None:
        _decode_codex32(self.s)

    @property
    def hrp(self) -> str:
        return self.s.rpartition("1")[0].lower()

    @property
    def _data_part(self) -> str:
        return self.s.rpartition("1")[2].lower()

    @property
    def k(self) -> str:
        return self._data_part[0]

    @property
    def ident(self) -> str:
        return self._data_part[1:5]

    @property
    def share_idx(self) -> str:
        return self._data_part[5]

    @property
    def payload(self) -> str:
        return self._data_part[6 : -len(self.checksum)]

    @property
    def checksum(self) -> str:
        return self._data_part[-_checksum_for_encoded_length(self.hrp, len(self._data_part)).length :]

    def __str__(self) -> str:
        return f"<{type(self).__name__}: redacted>"

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<redacted>)"

    def __len__(self) -> int:
        return len(self.s)


class MasterSeed(Codex32String):
    """A validated BIP93 master seed: an ``ms`` secret with index S."""

    __slots__ = ()

    def __post_init__(self) -> None:
        Codex32String.__post_init__(self)
        if self.hrp != MS or self.share_idx != "s":
            raise TypeError("a master seed must be an ms secret with share index S")

    @property
    def data(self) -> bytes:
        """Return the BIP32 master-seed bytes."""
        return bytes(convertbits(_chars_to_u5(self.payload), 5, 8, pad=False, accept_any_padding=True))

    @classmethod
    def from_seed(cls, data: bytes, *, identifier: str, threshold: int = 0) -> "MasterSeed":
        """Encode a supported BIP93 master seed with generation-only CRC padding."""
        if not isinstance(data, bytes):
            raise TypeError("data must be bytes")
        if len(data) not in SEED_BYTE_LENGTHS:
            raise InvalidLength("master seed must contain 16, 20, 24, 28, 32, or 64 bytes")
        payload = tuple(convertbits(data, 8, 5, pad=True, pad_value=_crc_pad(data)))
        return cls(_from_parts(MS, _header(threshold, identifier, "s"), payload).s)


def _has_generation_padding(secret: MasterSeed) -> bool:
    payload = _chars_to_u5(secret.payload)
    padding_bits = (len(payload) * 5) % 8
    padding = payload[-1] & ((1 << padding_bits) - 1) if padding_bits else 0
    return padding == _crc_pad(secret.data)


def parse_codex32(text: str) -> Codex32String:
    """Validate one codex32 string; an ms secret is returned as a MasterSeed."""
    secret = Codex32String(text)
    return MasterSeed(text) if secret.hrp == MS and secret.share_idx == "s" else secret


def _from_parts(hrp: str, header: str, payload: Sequence[int], *, uppercase: bool = False) -> Codex32String:
    normalized_hrp = hrp.lower()
    body = [*_chars_to_u5(header), *payload]
    expanded_body_length = 2 * len(normalized_hrp) + 1 + len(body)
    checksum = _CODEX32 if expanded_body_length <= 80 else _CODEX32_LONG
    # Validate the completed generic codeword, including the 94/95 gap.
    _checksum_for_encoded_length(normalized_hrp, len(body) + checksum.length)
    text = bech32_encode(normalized_hrp, body, checksum)
    return parse_codex32(text.upper() if uppercase else text)


def _lagrange_weights(points: tuple[int, ...], target: int) -> tuple[int, ...]:
    weights: list[int] = []
    for position, point in enumerate(points):
        weight = 1
        for other_position, other in enumerate(points):
            if position == other_position:
                continue
            weight = _gf32_multiply(weight, target ^ other)
            weight = _gf32_multiply(weight, _gf32_inverse(point ^ other))
        weights.append(weight)
    return tuple(weights)


@dataclass(frozen=True, slots=True)
class _ShareSet:
    artifacts: tuple[Codex32String, ...]
    hrp: str
    threshold: int
    identifier: str
    tails: tuple[tuple[int, ...], ...]
    uppercase: bool

    @property
    def indices(self) -> tuple[str, ...]:
        return tuple(item.share_idx for item in self.artifacts)


def _artifact_tail(artifact: Codex32String) -> tuple[int, ...]:
    """Return the payload and checksum symbols of already-validated text."""
    return tuple(_chars_to_u5(artifact.payload + artifact.checksum))


def _validate_share_set(artifacts: Sequence[Codex32String], *, require_exact: bool = True) -> _ShareSet:
    copied = tuple(islice(artifacts, 10))  # enough to reject an oversized set
    if not all(isinstance(item, Codex32String) for item in copied):
        raise TypeError("all share inputs must be validated codex32 artifacts")
    if not 1 <= len(copied) <= 9:
        raise WrongShareCount("a share set must contain between 1 and 9 artifacts")
    first = copied[0]
    threshold = int(first.k)
    if threshold not in range(2, 10):
        raise MismatchedThreshold("Only strings with a threshold of 2 through 9 can be combined.")
    if len(copied) > threshold or (require_exact and len(copied) != threshold):
        raise WrongShareCount(f"threshold is {threshold}, but {len(copied)} artifacts were supplied")
    tails = [_artifact_tail(first)]
    indices = [first.share_idx]
    for item in copied[1:]:
        if item.hrp != first.hrp:
            raise MismatchedHrp("These strings are for different applications.")
        if int(item.k) != threshold:
            raise MismatchedThreshold("These strings require different numbers of shares.")
        if item.ident != first.ident:
            raise MismatchedIdentifier("These strings have different identifiers.")
        if len(item.s) != len(first.s):
            raise MismatchedPayloadLength("These strings have different lengths.")
        tails.append(_artifact_tail(item))
        indices.append(item.share_idx)
    if len(set(indices)) != len(indices):
        raise DuplicateShareIndex("That share index was already entered.")
    return _ShareSet(
        copied,
        first.hrp,
        threshold,
        first.ident,
        tuple(tails),
        all(item.s.isupper() for item in copied),
    )


def _validate_recovery_prefix(shares: Sequence[Codex32String]) -> None:
    share_set = _validate_share_set(shares, require_exact=False)
    if "s" in share_set.indices:
        raise SecretInRecoverySet("Enter ordinary shares rather than the shared secret.")


def _interpolate_tail(share_set: _ShareSet, target: str) -> Codex32String:
    points = tuple(CHARSET.index(index) for index in share_set.indices)
    weights = _lagrange_weights(points, CHARSET.index(target))
    result: list[int] = []
    for column in range(len(share_set.tails[0])):
        value = 0
        for row, weight in zip(share_set.tails, weights, strict=True):
            value ^= _gf32_multiply(weight, row[column])
        result.append(value)
    text = f"{share_set.hrp}1{share_set.threshold}{share_set.identifier}{target}{_u5_to_chars(result)}"
    return parse_codex32(text.upper() if share_set.uppercase else text)


def recover_secret(shares: Sequence[Codex32String]) -> Codex32String:
    """Recover S from exactly k compatible, distinct ordinary shares."""
    share_set = _validate_share_set(shares)
    if "s" in share_set.indices:
        raise SecretInRecoverySet("Enter ordinary shares rather than the shared secret.")
    return _interpolate_tail(share_set, "s")


def _normalize_target(value: object, *, label: str) -> str:
    if not isinstance(value, str):
        raise InvalidTargetIndex(f"{label} must be one Bech32 symbol")
    normalized = value.lower()
    if len(normalized) != 1 or normalized not in CHARSET or normalized == "s":
        raise InvalidTargetIndex(f"{label} must be one of {IDX_SORT[1:].upper()}")
    return normalized


def derive_share(basis: Sequence[Codex32String], fresh_index: str) -> Codex32String:
    """Interpolate one additional ordinary share at a previously unused index."""
    share_set = _validate_share_set(basis)
    target = _normalize_target(fresh_index, label="fresh_index")
    if target in share_set.indices:
        raise ExistingTargetIndex(f"Choose a different share index; {target.upper()} was already supplied.")
    return _interpolate_tail(share_set, target)
