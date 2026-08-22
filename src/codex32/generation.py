"""Electronic generation for BIP93 master seeds and share sets."""

import secrets
from collections.abc import Sequence
from collections.abc import Set as AbstractSet

from bip32 import BIP32, InvalidInputError

from codex32.bech32 import CHARSET, _convert_bits, _u5_to_chars
from codex32.bip93 import (
    IDX_SORT,
    Header,
    MasterSeed,
    Share,
    _from_parts,
    _has_generation_padding,
    derive_share,
    recover_secret,
)
from codex32.errors import (
    CodexError,
    HeaderCollision,
    InvalidIdentifier,
    InvalidLength,
    InvalidShareSelection,
    InvalidThreshold,
)
from codex32.profiles import Profile

ORDINARY_INDICES = tuple(IDX_SORT[1:])


def _threshold(value: object, *, allow_zero: bool = True) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidThreshold("threshold must be an integer")
    permitted = (0, *range(2, 10)) if allow_zero else tuple(range(2, 10))
    if value not in permitted:
        prefix = "0 or " if allow_zero else ""
        raise InvalidThreshold(f"threshold must be {prefix}2 through 9")
    return value


def _identifier(value: object) -> str:
    if not isinstance(value, str):
        raise InvalidIdentifier("identifier must be str")
    value = value.lower()
    if len(value) != 4 or any(character not in CHARSET for character in value):
        raise InvalidIdentifier("identifier must be four Bech32 symbols")
    return value


def _index(value: object) -> str:
    if not isinstance(value, str) or len(value) != 1:
        raise InvalidShareSelection("each output index must be one Bech32 symbol")
    value = value.lower()
    if value not in ORDINARY_INDICES:
        raise InvalidShareSelection("output indices must be ordinary non-S symbols")
    return value


def _indices(values: Sequence[str] | str) -> tuple[str, ...]:
    if isinstance(values, str):
        copied: tuple[object, ...] = tuple(values)
    else:
        if isinstance(values, AbstractSet) or not isinstance(values, Sequence):
            raise TypeError("indices must be an ordered sequence")
        if len(values) > 31:
            raise InvalidShareSelection("at most 31 shares may be requested")
        copied = tuple(values[position] for position in range(len(values)))
    normalized = tuple(_index(value) for value in copied)
    if len(normalized) > 31 or len(set(normalized)) != len(normalized):
        raise InvalidShareSelection("output indices must be distinct")
    return normalized


def _selection(
    threshold: int,
    share_count: object,
    indices: Sequence[str] | str | None,
) -> tuple[int | None, tuple[str, ...] | None]:
    if threshold == 0:
        if share_count is not None or indices is not None:
            raise InvalidShareSelection("threshold zero does not accept share selectors")
        return None, None
    if (share_count is None) == (indices is None):
        raise InvalidShareSelection("choose exactly one of share_count or indices")
    if share_count is not None:
        if isinstance(share_count, bool) or not isinstance(share_count, int):
            raise InvalidShareSelection("share_count must be an integer")
        if not threshold <= share_count <= 31:
            raise InvalidShareSelection(
                f"share_count must be from threshold {threshold} through 31"
            )
        return share_count, None
    assert indices is not None
    selected = _indices(indices)
    if len(selected) < threshold:
        raise InvalidShareSelection(f"at least {threshold} indices are required")
    return None, selected


def _random_identifier() -> str:
    return _u5_to_chars(tuple(value & 31 for value in secrets.token_bytes(4)))


def _fingerprint_identifier(seed: bytes) -> str:
    try:
        fingerprint = BIP32.from_seed(seed).get_fingerprint()
    except InvalidInputError as error:
        raise CodexError("master seed does not form a valid BIP32 root") from error
    symbols = _convert_bits(fingerprint, 8, 5, pad=True)
    return _u5_to_chars(tuple(symbols[:4]))


def _masks(
    threshold: int,
    identifier: str,
    payload_length: int,
    count: int,
) -> tuple[Share, ...]:
    """Draw every mask symbol for one basis in one OS-random call."""
    random_bytes = secrets.token_bytes(count * payload_length)
    symbols = tuple(value & 31 for value in random_bytes)
    result = []
    for position in range(count):
        start = position * payload_length
        artifact = _from_parts(
            Profile.MS,
            Header(threshold, identifier, ORDINARY_INDICES[position]),
            symbols[start : start + payload_length],
        )
        assert isinstance(artifact, Share)
        result.append(artifact)
    return tuple(result)


def _basis(
    secret: MasterSeed, threshold: int, identifier: str
) -> tuple[MasterSeed | Share, ...]:
    reheadered = _from_parts(
        Profile.MS,
        Header(threshold, identifier, "s"),
        secret.payload_symbols,
    )
    assert isinstance(reheadered, MasterSeed)
    return (
        reheadered,
        *_masks(threshold, identifier, len(secret.payload_symbols), threshold - 1),
    )


def _output_indices(
    share_count: int | None,
    explicit: tuple[str, ...] | None,
) -> tuple[str, ...]:
    if explicit is not None:
        return explicit
    assert share_count is not None
    return tuple(secrets.SystemRandom().sample(ORDINARY_INDICES, share_count))


def _share_at(basis: tuple[MasterSeed | Share, ...], index: str) -> Share:
    for artifact in basis:
        if artifact.header.index == index:
            assert isinstance(artifact, Share)
            return artifact
    return derive_share(basis, index)


def _finish(
    secret: MasterSeed,
    basis: tuple[MasterSeed | Share, ...],
    share_count: int | None,
    explicit: tuple[str, ...] | None,
) -> tuple[MasterSeed, tuple[Share, ...]]:
    indices = _output_indices(share_count, explicit)
    return secret, tuple(_share_at(basis, index) for index in indices)


def _seed_input(
    seed_bytes: bytes | None, byte_length: int | None
) -> tuple[bytes | None, int]:
    if seed_bytes is not None:
        if not isinstance(seed_bytes, bytes):
            raise TypeError("seed_bytes must be bytes")
        if byte_length is not None:
            raise InvalidLength("byte_length cannot accompany seed_bytes")
        if not 16 <= len(seed_bytes) <= 64:
            raise InvalidLength("master seed must contain 16 through 64 bytes")
        return seed_bytes, len(seed_bytes)
    length = 16 if byte_length is None else byte_length
    if isinstance(length, bool) or not isinstance(length, int) or not 16 <= length <= 64:
        raise InvalidLength("byte_length must be an integer from 16 through 64")
    return None, length


def generate_master_seed(
    seed_bytes: bytes | None = None,
    *,
    byte_length: int | None = None,
    threshold: int = 0,
    share_count: int | None = None,
    indices: Sequence[str] | str | None = None,
    identifier: str | None = None,
) -> tuple[MasterSeed, tuple[Share, ...]]:
    """Create a master seed or a fresh BIP93 share set."""
    supplied, length = _seed_input(seed_bytes, byte_length)
    threshold = _threshold(threshold)
    share_count, explicit = _selection(threshold, share_count, indices)
    if supplied is not None and identifier is None:
        raise InvalidIdentifier("raw seed bytes require an explicit identifier")

    if supplied is not None:
        _fingerprint_identifier(supplied)
        identifier = _identifier(identifier)
        secret = MasterSeed.from_seed(supplied, identifier=identifier, threshold=threshold)
        if threshold == 0:
            return secret, ()
        return _finish(secret, _basis(secret, threshold, identifier), share_count, explicit)

    if threshold == 0:
        while True:
            fresh = secrets.token_bytes(length)
            try:
                default_identifier = _fingerprint_identifier(fresh)
            except CodexError:
                continue
            identifier = default_identifier if identifier is None else _identifier(identifier)
            return MasterSeed.from_seed(fresh, identifier=identifier), ()

    identifier = _random_identifier() if identifier is None else _identifier(identifier)
    payload_length = (length * 8 + 4) // 5
    while True:
        masks = _masks(threshold, identifier, payload_length, threshold)
        recovered = recover_secret(masks)
        assert isinstance(recovered, MasterSeed)
        if not _has_generation_padding(recovered):
            continue
        try:
            _fingerprint_identifier(recovered.seed_bytes)
        except CodexError:
            continue
        return _finish(recovered, masks, share_count, explicit)


def split_secret(
    secret: MasterSeed,
    threshold: int,
    *,
    identifier: str,
    share_count: int | None = None,
    indices: Sequence[str] | str | None = None,
) -> tuple[MasterSeed, tuple[Share, ...]]:
    """Split one parsed master seed under a new explicit set header."""
    if not isinstance(secret, MasterSeed):
        raise TypeError("split_secret accepts only MasterSeed")
    threshold = _threshold(threshold, allow_zero=False)
    identifier = _identifier(identifier)
    if (threshold, identifier) == (secret.header.threshold, secret.header.identifier):
        raise HeaderCollision("new share set must use a different set header")
    share_count, explicit = _selection(threshold, share_count, indices)
    basis = _basis(secret, threshold, identifier)
    reheadered = basis[0]
    assert isinstance(reheadered, MasterSeed)
    return _finish(reheadered, basis, share_count, explicit)
