# Portions of interpolation arithmetic are derived from rust-codex32 (BSD-3-Clause).
"""Immutable BIP93 artifacts, parsing, recovery, and share derivation."""

from collections.abc import Sequence
from dataclasses import dataclass

from codex32.bech32 import (
    CHARSET,
    _chars_to_u5,
    _u5_to_chars,
    bech32_decode,
    bech32_encode,
    bech32_verify_checksum,
)
from codex32.checksums import _CODEX32, _CODEX32_LONG, _Checksum
from codex32.errors import (
    DuplicateShareIndex,
    ExistingTargetIndex,
    InvalidChecksum,
    InvalidIdentifier,
    InvalidLength,
    InvalidShareIndex,
    InvalidShareSet,
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
from codex32.profiles import Profile, _optional_profile_rules, _profile_rules, _ProfileRules

IDX_SORT = "sacdefghjklmnpqrtuvwxyz023456789"
_CONSTRUCTION_TOKEN = object()


@dataclass(frozen=True, slots=True)
class Header:
    """Normalized immutable BIP93 header."""

    threshold: int
    identifier: str
    index: str

    def __post_init__(self) -> None:
        if isinstance(self.threshold, bool) or self.threshold not in (0, *range(2, 10)):
            raise InvalidThreshold("threshold must be 0 or an integer from 2 through 9")
        if not isinstance(self.identifier, str):
            raise InvalidIdentifier("identifier must be str")
        identifier = self.identifier.lower()
        if len(identifier) != 4 or any(character not in CHARSET for character in identifier):
            raise InvalidIdentifier("identifier must be exactly four Bech32 symbols")
        if not isinstance(self.index, str):
            raise InvalidShareIndex("share index must be str")
        index = self.index.lower()
        if len(index) != 1 or index not in CHARSET:
            raise InvalidShareIndex("share index must be one Bech32 symbol")
        if self.threshold == 0 and index != "s":
            raise InvalidShareIndex("An unshared secret (threshold 0) must use S as its index.")
        object.__setattr__(self, "identifier", identifier)
        object.__setattr__(self, "index", index)

    @classmethod
    def _from_symbols(cls, symbols: tuple[int, ...]) -> "Header":
        if len(symbols) != 6:
            raise InvalidLength("codex32 header must contain six symbols")
        text = _u5_to_chars(symbols)
        if text[0] not in "023456789":
            raise InvalidThreshold(
                f"The threshold must be 0 or a number from 2 through 9; found {text[0]!r}."
            )
        return cls(int(text[0]), text[1:5], text[5])

    @property
    def _symbols(self) -> tuple[int, ...]:
        return tuple(_chars_to_u5(f"{self.threshold}{self.identifier}{self.index}"))


def _checksum_for_encoded_length(hrp: str, encoded_length: int) -> _Checksum:
    expanded_length = 2 * len(hrp) + 1 + encoded_length
    if expanded_length <= 93:
        return _CODEX32
    if expanded_length < 96:
        raise InvalidLength("expanded codex32 lengths 94 and 95 are invalid")
    if expanded_length <= 1023:
        return _CODEX32_LONG
    raise InvalidLength("expanded codex32 codeword exceeds 1023 symbols")


def _decode_codex32(text: str) -> tuple[str, _ProfileRules | None, tuple[int, ...], _Checksum]:
    hrp, encoded = bech32_decode(text)
    if len(hrp) > 83:
        raise InvalidLength(f"human-readable part exceeds 83 characters ({len(hrp)})")
    if len(hrp) + 1 + len(encoded) < 21:
        raise InvalidLength("codex32 string must contain at least 21 characters")
    checksum = _checksum_for_encoded_length(hrp, len(encoded))
    body = tuple(encoded[: -checksum.length])
    Header._from_symbols(body[:6])
    if not bech32_verify_checksum(hrp, encoded, checksum):
        raise InvalidChecksum(f"invalid {checksum.kind} checksum")
    profile_rules = _optional_profile_rules(hrp)
    if profile_rules is not None:
        profile_rules.validate_text_length(len(text))
        profile_rules.validate_payload_length(len(body) - 6)
    return hrp, profile_rules, tuple(encoded), checksum


@dataclass(frozen=True, slots=True, init=False)
class _Artifact:
    text: str
    header: Header
    hrp: str
    profile: Profile | None
    payload_symbols: tuple[int, ...]

    def __init__(
        self,
        text: str,
        header: Header,
        hrp: str,
        profile: Profile | None,
        payload_symbols: tuple[int, ...],
        *,
        _token: object,
    ) -> None:
        if _token is not _CONSTRUCTION_TOKEN:
            raise TypeError("codex32 artifacts must be created by the public factories")
        object.__setattr__(self, "text", text)
        object.__setattr__(self, "header", header)
        object.__setattr__(self, "hrp", hrp)
        object.__setattr__(self, "profile", profile)
        object.__setattr__(self, "payload_symbols", payload_symbols)

    def __str__(self) -> str:
        return self.text

    def __len__(self) -> int:
        return len(self.text)


class Share(_Artifact):
    __slots__ = ()


class Secret(_Artifact):
    __slots__ = ()


def _validate_payload(profile: Profile, header: Header, payload: tuple[int, ...]) -> None:
    rules = _profile_rules(profile)
    rules.validate_payload_length(len(payload))
    rules.validate_payload(payload, header.index)


def _artifact(
    text: str,
    hrp: str,
    profile: Profile | None,
    header: Header,
    payload: tuple[int, ...],
) -> Share | Secret:
    rules = _optional_profile_rules(hrp)
    artifact_type = Share if header.index != "s" else (rules.secret_type if rules is not None else Secret)
    return artifact_type(text, header, hrp, profile, payload, _token=_CONSTRUCTION_TOKEN)


def parse_codex32(text: str) -> Share | Secret:
    """Validate one codex32 string and return an immutable artifact."""
    hrp, profile_rules, encoded, checksum = _decode_codex32(text)
    body = tuple(encoded[: -checksum.length])
    header = Header._from_symbols(body[:6])
    payload = body[6:]
    profile = profile_rules.profile if profile_rules is not None else None
    if profile is not None:
        _validate_payload(profile, header, payload)
    return _artifact(text, hrp, profile, header, payload)


def _from_parts(
    hrp: str | Profile,
    header: Header,
    payload: tuple[int, ...],
    *,
    uppercase: bool = False,
) -> Share | Secret:
    normalized_hrp = hrp.value if isinstance(hrp, Profile) else hrp.lower()
    rules = _optional_profile_rules(normalized_hrp)
    if rules is not None:
        _validate_payload(rules.profile, header, payload)
    body = [*header._symbols, *payload]
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
    artifacts: tuple[Share | Secret, ...]
    hrp: str
    profile: Profile | None
    threshold: int
    identifier: str
    tails: tuple[tuple[int, ...], ...]
    uppercase: bool

    @property
    def indices(self) -> tuple[str, ...]:
        return tuple(item.header.index for item in self.artifacts)


def _bounded_artifacts(
    artifacts: Sequence[Share | Secret],
) -> tuple[Share | Secret, ...]:
    if isinstance(artifacts, (str, bytes, bytearray)):
        raise TypeError("share inputs must be validated artifacts, not text")
    try:
        count = len(artifacts)
    except TypeError as error:
        raise TypeError("share inputs must be a Sequence of artifacts") from error
    if count == 0 or count > 9:
        raise WrongShareCount("a share set must contain between 1 and 9 artifacts")
    try:
        copied = tuple(artifacts[position] for position in range(count))
    except IndexError as error:
        raise TypeError("share input Sequence changed length while being read") from error
    if not all(isinstance(item, _Artifact) for item in copied):
        raise TypeError("all share inputs must be validated codex32 artifacts")
    return copied


def _artifact_tail(artifact: Share | Secret) -> tuple[tuple[int, ...], int, int]:
    hrp, profile_rules, encoded, checksum = _decode_codex32(artifact.text)
    profile = profile_rules.profile if profile_rules is not None else None
    if hrp != artifact.hrp or profile is not artifact.profile:
        raise InvalidShareSet("artifact text and validated application prefix disagree")
    return tuple(encoded[6:]), checksum.length, len(encoded)


def _validate_share_set(artifacts: Sequence[Share | Secret], *, require_exact: bool = True) -> _ShareSet:
    copied = _bounded_artifacts(artifacts)
    first = copied[0]
    threshold = first.header.threshold
    if threshold not in range(2, 10):
        raise MismatchedThreshold("linear sharing requires threshold 2 through 9")
    if len(copied) > threshold or (require_exact and len(copied) != threshold):
        raise WrongShareCount(f"threshold is {threshold}, but {len(copied)} artifacts were supplied")
    first_tail, checksum_length, encoded_length = _artifact_tail(first)
    tails = [first_tail]
    indices = [first.header.index]
    for item in copied[1:]:
        if item.hrp != first.hrp:
            raise MismatchedHrp(f"{first.hrp} and {item.hrp} cannot be combined")
        if item.header.threshold != threshold:
            raise MismatchedThreshold("share thresholds do not match")
        if item.header.identifier != first.header.identifier:
            raise MismatchedIdentifier("share identifiers do not match")
        tail, item_checksum_length, item_encoded_length = _artifact_tail(item)
        item_shape = (
            len(item.payload_symbols),
            item_checksum_length,
            item_encoded_length,
        )
        if item_shape != (len(first.payload_symbols), checksum_length, encoded_length):
            raise MismatchedPayloadLength("share payload/checksum lengths do not match")
        tails.append(tail)
        indices.append(item.header.index)
    if len(set(indices)) != len(indices):
        raise DuplicateShareIndex("share indices must be distinct")
    return _ShareSet(
        copied,
        first.hrp,
        first.profile,
        threshold,
        first.header.identifier,
        tuple(tails),
        all(item.text.isupper() for item in copied),
    )


def _validate_recovery_prefix(shares: Sequence[Share | Secret]) -> None:
    share_set = _validate_share_set(shares, require_exact=False)
    if any(isinstance(item, Secret) for item in share_set.artifacts):
        raise SecretInRecoverySet("recovery accepts ordinary shares only")


def _validate_basis_prefix(basis: Sequence[Share | Secret]) -> None:
    _validate_share_set(basis, require_exact=False)


def _interpolate_tail(share_set: _ShareSet, target: str) -> Share | Secret:
    points = tuple(CHARSET.index(index) for index in share_set.indices)
    weights = _lagrange_weights(points, CHARSET.index(target))
    result: list[int] = []
    for column in range(len(share_set.tails[0])):
        value = 0
        for row, weight in zip(share_set.tails, weights, strict=True):
            value ^= _gf32_multiply(weight, row[column])
        result.append(value)
    header = Header(share_set.threshold, share_set.identifier, target)
    text = f"{share_set.hrp}1{_u5_to_chars((*header._symbols, *result))}"
    return parse_codex32(text.upper() if share_set.uppercase else text)


def recover_secret(shares: Sequence[Share]) -> Secret:
    """Recover S from exactly k compatible, distinct ordinary shares."""
    share_set = _validate_share_set(shares)
    if any(isinstance(item, Secret) for item in share_set.artifacts):
        raise SecretInRecoverySet("recovery accepts ordinary shares only")
    recovered = _interpolate_tail(share_set, "s")
    if not isinstance(recovered, Secret):
        raise InvalidShareSet("interpolation did not produce a secret")
    return recovered


def _normalize_target(value: object, *, label: str) -> str:
    if not isinstance(value, str):
        raise InvalidTargetIndex(f"{label} must be one Bech32 symbol")
    normalized = value.lower()
    if len(normalized) != 1 or normalized not in CHARSET or normalized == "s":
        raise InvalidTargetIndex(f"{label} must be one of {IDX_SORT[1:].upper()}")
    return normalized


def derive_share(basis: Sequence[Share | Secret], fresh_index: str) -> Share:
    """Interpolate one additional ordinary share at a previously unused index."""
    share_set = _validate_share_set(basis)
    target = _normalize_target(fresh_index, label="fresh_index")
    if target in share_set.indices:
        raise ExistingTargetIndex(f"Choose a different share index; {target.upper()} was already supplied.")
    profile_rules = _optional_profile_rules(share_set.hrp)
    if profile_rules is not None and profile_rules.basis_secret_type is not None:
        implied_secret = _interpolate_tail(share_set, "s")
        if not isinstance(implied_secret, Secret):
            raise InvalidShareSet("interpolation did not produce a secret")
        if not isinstance(implied_secret, profile_rules.basis_secret_type):
            raise InvalidShareSet(profile_rules.basis_error)
    derived = _interpolate_tail(share_set, target)
    if not isinstance(derived, Share):
        raise InvalidShareSet("interpolation did not produce an ordinary share")
    return derived
