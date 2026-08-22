# Portions of interpolation arithmetic are derived from rust-codex32 (BSD-3-Clause).
"""Immutable BIP93 artifacts, parsing, recovery, and share derivation."""

from collections.abc import Sequence
from dataclasses import dataclass

from codex32.bech32 import (
    CHARSET,
    _chars_to_u5,
    _convert_bits,
    _decode,
    _encode,
    _parse,
    _payload_bytes,
    _u5_to_chars,
)
from codex32.checksums import _crc_pad
from codex32.errors import (
    DuplicateShareIndex,
    ExistingTargetIndex,
    InvalidIdentifier,
    InvalidLength,
    InvalidShareIndex,
    InvalidShareSet,
    InvalidTargetIndex,
    InvalidThreshold,
    MismatchedIdentifier,
    MismatchedPayloadLength,
    MismatchedProfile,
    MismatchedThreshold,
    SecretInRecoverySet,
    WrongShareCount,
)
from codex32.gf32 import _inverse as _gf32_inverse
from codex32.gf32 import _multiply as _gf32_multiply
from codex32.profiles import Profile, _profile_spec

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
            raise InvalidShareIndex("threshold 0 requires share index S")
        object.__setattr__(self, "identifier", identifier)
        object.__setattr__(self, "index", index)

    @classmethod
    def _from_symbols(cls, symbols: tuple[int, ...]) -> "Header":
        if len(symbols) != 6:
            raise InvalidLength("codex32 header must contain six symbols")
        text = _u5_to_chars(symbols)
        if text[0] not in "023456789":
            raise InvalidThreshold(f"invalid threshold symbol {text[0]!r}")
        return cls(int(text[0]), text[1:5], text[5])

    @property
    def _symbols(self) -> tuple[int, ...]:
        """Return normalized header symbols for internal algebra."""
        return tuple(_chars_to_u5(f"{self.threshold}{self.identifier}{self.index}"))


@dataclass(frozen=True, slots=True, init=False)
class _Artifact:
    _text: str
    _header: Header
    _profile: Profile
    _payload_symbols: tuple[int, ...]

    def __init__(
        self,
        text: str,
        header: Header,
        profile: Profile,
        payload_symbols: tuple[int, ...],
        *,
        _token: object,
    ) -> None:
        if _token is not _CONSTRUCTION_TOKEN:
            raise TypeError("codex32 artifacts must be created by the public factories")
        object.__setattr__(self, "_text", text)
        object.__setattr__(self, "_header", header)
        object.__setattr__(self, "_profile", profile)
        object.__setattr__(self, "_payload_symbols", payload_symbols)

    @property
    def text(self) -> str:
        """Return the validated codex32 string, preserving parsed case."""
        return self._text

    @property
    def header(self) -> Header:
        return self._header

    @property
    def profile(self) -> Profile:
        return self._profile

    @property
    def payload_symbols(self) -> tuple[int, ...]:
        return self._payload_symbols

    def __str__(self) -> str:
        return self._text

    def __len__(self) -> int:
        return len(self._text)


class Share(_Artifact):
    """An ordinary uniformly random codex32 share with symbol semantics only."""

    __slots__ = ()


class Secret(_Artifact):
    """Base type for profile-specific S artifacts."""

    __slots__ = ()


class MasterSeed(Secret):
    """A validated BIP93 ``ms`` secret."""

    __slots__ = ()

    @property
    def seed_bytes(self) -> bytes:
        seed, _padding, _padding_bits = _payload_bytes(self.payload_symbols)
        return seed

    @classmethod
    def from_seed(
        cls,
        seed_bytes: bytes,
        *,
        identifier: str,
        threshold: int = 0,
    ) -> "MasterSeed":
        if not isinstance(seed_bytes, bytes):
            raise TypeError("seed_bytes must be bytes")
        if not 16 <= len(seed_bytes) <= 64:
            raise InvalidLength("master seed must contain 16 through 64 bytes")
        header = Header(threshold, identifier, "s")
        payload = tuple(
            _convert_bits(
                seed_bytes,
                8,
                5,
                pad=True,
                pad_value=_crc_pad(seed_bytes),
            )
        )
        artifact = _from_parts(Profile.MS, header, payload)
        assert isinstance(artifact, MasterSeed)
        return artifact


class CoreLightningSecret(Secret):
    """A validated 32-byte Core Lightning HSM secret."""

    __slots__ = ()

    @property
    def secret_bytes(self) -> bytes:
        secret, _padding, _padding_bits = _payload_bytes(self.payload_symbols)
        return secret

    @classmethod
    def from_secret_bytes(
        cls,
        secret_bytes: bytes,
        *,
        identifier: str,
        threshold: int = 0,
    ) -> "CoreLightningSecret":
        if not isinstance(secret_bytes, bytes):
            raise TypeError("secret_bytes must be bytes")
        if len(secret_bytes) != 32:
            raise InvalidLength("Core Lightning secrets must contain exactly 32 bytes")
        header = Header(threshold, identifier, "s")
        payload = tuple(
            _convert_bits(secret_bytes, 8, 5, pad=True, pad_value=0)
        )
        artifact = _from_parts(Profile.CL, header, payload)
        assert isinstance(artifact, CoreLightningSecret)
        return artifact


class Bip39Secret(Secret):
    """Migration-only BIP39 S artifact without entropy or mnemonic access."""

    __slots__ = ()


def _validate_payload(
    profile: Profile, header: Header, payload: tuple[int, ...]
) -> None:
    _profile_spec(profile).validate_payload_length(len(payload))
    if profile is Profile.MS:
        seed, _padding, _padding_bits = _payload_bytes(payload)
        if not 16 <= len(seed) <= 64:
            raise InvalidLength("master seed must contain 16 through 64 bytes")
    elif profile is Profile.CL:
        secret, _padding, _padding_bits = _payload_bytes(payload)
        if len(secret) != 32:
            raise InvalidLength("Core Lightning secret must contain exactly 32 bytes")
    elif header.index == "s":
        # The SHA dependency is isolated from normal ms/cl imports and execution.
        from codex32.bip39 import _validate_bip39_secret

        _validate_bip39_secret(profile, payload)


def _artifact(
    text: str, profile: Profile, header: Header, payload: tuple[int, ...]
) -> Share | Secret:
    artifact_type: type[_Artifact]
    if header.index != "s":
        artifact_type = Share
    elif profile is Profile.MS:
        artifact_type = MasterSeed
    elif profile is Profile.CL:
        artifact_type = CoreLightningSecret
    else:
        artifact_type = Bip39Secret
    return artifact_type(text, header, profile, payload, _token=_CONSTRUCTION_TOKEN)


def parse_codex32(text: str) -> Share | Secret:
    """Parse a registered profile into a validated immutable artifact."""
    hrp, encoded, checksum = _decode(text)
    profile_spec = _profile_spec(hrp)
    body = encoded[: -checksum.length]
    header = Header._from_symbols(body[:6])
    payload = body[6:]
    _validate_payload(profile_spec.profile, header, payload)
    return _artifact(text, profile_spec.profile, header, payload)


def _from_parts(
    profile: Profile,
    header: Header,
    payload: tuple[int, ...],
    *,
    uppercase: bool = False,
) -> Share | Secret:
    _validate_payload(profile, header, payload)
    body = (*header._symbols, *payload)
    text = _encode(profile.value, body)
    return parse_codex32(text.upper() if uppercase else text)


def complete_checksum(unchecksummed_text: str) -> Share | Secret:
    """Complete a validated ``ms`` or ``cl`` symbol string."""
    hrp, body_values = _parse(unchecksummed_text)
    profile_spec = _profile_spec(hrp)
    profile_spec.require_completion()
    body = tuple(body_values)
    profile_spec.validate_payload_length(len(body) - 6)
    header = Header._from_symbols(body[:6])
    payload = body[6:]
    _validate_payload(profile_spec.profile, header, payload)
    return _from_parts(
        profile_spec.profile,
        header,
        payload,
        uppercase=unchecksummed_text.isupper(),
    )


def _lagrange_weights(points: tuple[int, ...], target: int) -> tuple[int, ...]:
    """Return Lagrange weights in GF(32) for one target coordinate."""
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
    """A completely validated, interpolation-ready set of artifacts."""

    artifacts: tuple[Share | Secret, ...]
    profile: Profile
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
    """Check the public Sequence boundary before copying at most nine items."""
    if isinstance(artifacts, (str, bytes, bytearray)):
        raise TypeError("share inputs must be authenticated artifacts, not text")
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
    """Return payload plus checksum, checksum length, and encoded length."""
    hrp, encoded, checksum = _decode(artifact.text)
    if hrp != artifact.profile.value:
        raise InvalidShareSet("artifact text and authenticated profile disagree")
    return tuple(encoded[6:]), checksum.length, len(encoded)


def _validate_share_set(artifacts: Sequence[Share | Secret]) -> _ShareSet:
    """Validate the common interpolation domain and exact threshold."""
    copied = _bounded_artifacts(artifacts)
    first = copied[0]
    threshold = first.header.threshold
    if threshold not in range(2, 10):
        raise MismatchedThreshold("linear sharing requires threshold 2 through 9")
    if len(copied) != threshold:
        raise WrongShareCount(
            f"threshold is {threshold}, but {len(copied)} artifacts were supplied"
        )
    first_tail, checksum_length, encoded_length = _artifact_tail(first)
    tails = [first_tail]
    indices = [first.header.index]
    for item in copied[1:]:
        if item.profile is not first.profile:
            raise MismatchedProfile(
                f"{first.profile.value} and {item.profile.value} cannot be combined"
            )
        if item.header.threshold != threshold:
            raise MismatchedThreshold("share thresholds do not match")
        if item.header.identifier != first.header.identifier:
            raise MismatchedIdentifier("share identifiers do not match")
        tail, item_checksum_length, item_encoded_length = _artifact_tail(item)
        if (
            len(item.payload_symbols) != len(first.payload_symbols)
            or item_checksum_length != checksum_length
            or item_encoded_length != encoded_length
        ):
            raise MismatchedPayloadLength("share payload/checksum lengths do not match")
        tails.append(tail)
        indices.append(item.header.index)
    if len(set(indices)) != len(indices):
        raise DuplicateShareIndex("share indices must be distinct")
    return _ShareSet(
        copied,
        first.profile,
        threshold,
        first.header.identifier,
        tuple(tails),
        all(item.text.isupper() for item in copied),
    )


def _interpolate_tail(share_set: _ShareSet, target: str) -> Share | Secret:
    """Interpolate payload and checksum together, then reparse the codeword."""
    points = tuple(CHARSET.index(index) for index in share_set.indices)
    weights = _lagrange_weights(points, CHARSET.index(target))
    result: list[int] = []
    for column in range(len(share_set.tails[0])):
        value = 0
        for row, weight in zip(share_set.tails, weights, strict=True):
            value ^= _gf32_multiply(weight, row[column])
        result.append(value)
    header = Header(share_set.threshold, share_set.identifier, target)
    text = (
        f"{share_set.profile.value}1"
        f"{_u5_to_chars((*header._symbols, *result))}"
    )
    return parse_codex32(text.upper() if share_set.uppercase else text)


def recover_secret(shares: Sequence[Share]) -> Secret:
    """Recover S from exactly the declared threshold of ordinary shares."""
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
        raise InvalidTargetIndex(f"{label} must be one ordinary Bech32 index")
    return normalized


def derive_share(
    basis: Sequence[Share | Secret],
    fresh_index: str,
) -> Share:
    """Derive a new ordinary share at a fresh index."""
    share_set = _validate_share_set(basis)
    target = _normalize_target(fresh_index, label="fresh_index")
    if target in share_set.indices:
        raise ExistingTargetIndex(f"index {target.upper()} is already in the basis")
    if share_set.profile in (Profile.BIP39_12W, Profile.BIP39_24W):
        implied_secret = _interpolate_tail(share_set, "s")
        if not isinstance(implied_secret, Bip39Secret):
            raise InvalidShareSet("BIP39 basis did not imply a valid BIP39 secret")
    derived = _interpolate_tail(share_set, target)
    if not isinstance(derived, Share):
        raise InvalidShareSet("interpolation did not produce an ordinary share")
    return derived


def _payload_padding(artifact: MasterSeed | CoreLightningSecret) -> int:
    _data, padding, _padding_bits = _payload_bytes(artifact.payload_symbols)
    return padding


def _has_generation_padding(secret: MasterSeed) -> bool:
    return _payload_padding(secret) == _crc_pad(secret.seed_bytes)
