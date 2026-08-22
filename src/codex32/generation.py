"""Audited electronic generation for registered ``ms`` and ``cl`` profiles.

This module is the sole owner of generation entropy, hidden interpolation
bases, identifier policy, output-index selection, and returned order.  It has
deliberately no injectable random source or deterministic test mode.
"""

import secrets
from collections.abc import Collection, Sequence
from collections.abc import Set as AbstractSet

from bip32 import BIP32, InvalidInputError

from codex32.bech32 import CHARSET, _convert_bits, _u5_to_chars
from codex32.bip93 import (
    IDX_SORT,
    CoreLightningSecret,
    Header,
    MasterSeed,
    Secret,
    Share,
    _from_parts,
    _has_generation_padding,
    _payload_padding,
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

ORDINARY_INDICES: tuple[str, ...] = tuple(IDX_SORT[1:])

_MAX_EXCLUDED_HEADERS = 1024
_TEMPORARY_IDENTIFIER = "qqqq"


def _validated_threshold(threshold: object, *, allow_zero: bool) -> int:
    if isinstance(threshold, bool) or not isinstance(threshold, int):
        raise InvalidThreshold("threshold must be an integer")
    allowed = (0, *range(2, 10)) if allow_zero else tuple(range(2, 10))
    if threshold not in allowed:
        qualifier = "0 or " if allow_zero else ""
        raise InvalidThreshold(f"threshold must be {qualifier}an integer from 2 through 9")
    return threshold


def _validated_identifier(identifier: object) -> str:
    if not isinstance(identifier, str):
        raise InvalidIdentifier("identifier must be str")
    normalized = identifier.lower()
    if len(normalized) != 4 or any(symbol not in CHARSET for symbol in normalized):
        raise InvalidIdentifier("identifier must be exactly four Bech32 symbols")
    return normalized


def _validated_set_header(header: object) -> str:
    if not isinstance(header, str):
        raise InvalidShareSelection("excluded set headers must be strings")
    normalized = header.lower()
    if len(normalized) != 5 or normalized[0] not in "023456789":
        raise InvalidShareSelection(
            "excluded set headers must contain a threshold and four Bech32 symbols"
        )
    if any(symbol not in CHARSET for symbol in normalized[1:]):
        raise InvalidShareSelection(
            "excluded set headers must contain a threshold and four Bech32 symbols"
        )
    return normalized


def _snapshot_excluded_headers(
    excluded_headers: Collection[str],
) -> frozenset[str]:
    """Validate and freeze a bounded caller collection before drawing entropy."""
    if isinstance(excluded_headers, (str, bytes, bytearray)):
        raise TypeError("excluded_headers must be a non-text Collection")
    try:
        count = len(excluded_headers)
        iterator = iter(excluded_headers)
    except TypeError as error:
        raise TypeError("excluded_headers must be a Collection") from error
    if count > _MAX_EXCLUDED_HEADERS:
        raise InvalidShareSelection(
            f"excluded_headers cannot contain more than {_MAX_EXCLUDED_HEADERS} items"
        )
    copied: list[object] = []
    for _position in range(count):
        try:
            copied.append(next(iterator))
        except StopIteration as error:
            raise TypeError("excluded_headers changed size while being read") from error
    sentinel = object()
    if next(iterator, sentinel) is not sentinel:
        raise TypeError("excluded_headers changed size while being read")
    return frozenset(_validated_set_header(item) for item in copied)


def _with_source_header(
    excluded_headers: frozenset[str], source_header: str
) -> frozenset[str]:
    if source_header in excluded_headers:
        return excluded_headers
    if len(excluded_headers) == _MAX_EXCLUDED_HEADERS:
        raise InvalidShareSelection(
            "excluded_headers plus the source set header exceed the 1024-item limit"
        )
    return frozenset((*excluded_headers, source_header))


def _normalized_index(index: object) -> str:
    if not isinstance(index, str):
        raise InvalidShareSelection("each output index must be one Bech32 symbol")
    normalized = index.lower()
    if len(normalized) != 1 or normalized not in ORDINARY_INDICES:
        raise InvalidShareSelection("output indices must be ordinary non-S Bech32 symbols")
    return normalized


def _copied_indices(indices: Sequence[str] | str) -> tuple[str, ...]:
    if isinstance(indices, (bytes, bytearray)):
        raise TypeError("indices must be text or an ordered Sequence of strings")
    if isinstance(indices, str):
        copied: tuple[object, ...] = tuple(indices)
    else:
        if isinstance(indices, AbstractSet) or not isinstance(indices, Sequence):
            raise TypeError("indices must be an ordered Sequence, not a set")
        count = len(indices)
        if count > len(ORDINARY_INDICES):
            raise InvalidShareSelection("at most 31 output indices may be requested")
        try:
            copied = tuple(indices[position] for position in range(count))
        except IndexError as error:
            raise TypeError("indices changed size while being read") from error
        if len(indices) != count:
            raise TypeError("indices changed size while being read")
    if len(copied) > len(ORDINARY_INDICES):
        raise InvalidShareSelection("at most 31 output indices may be requested")
    normalized = tuple(_normalized_index(index) for index in copied)
    if len(set(normalized)) != len(normalized):
        raise InvalidShareSelection("output indices must be distinct")
    return normalized


def _validated_selection(
    threshold: int,
    share_count: object,
    indices: Sequence[str] | str | None,
) -> tuple[int | None, tuple[str, ...] | None]:
    if threshold == 0:
        if share_count is not None or indices is not None:
            raise InvalidShareSelection("threshold zero does not accept share selectors")
        return None, None
    if (share_count is None) == (indices is None):
        raise InvalidShareSelection(
            "shared generation requires exactly one of share_count or indices"
        )
    if share_count is not None:
        if isinstance(share_count, bool) or not isinstance(share_count, int):
            raise InvalidShareSelection("share_count must be an integer")
        if not threshold <= share_count <= len(ORDINARY_INDICES):
            raise InvalidShareSelection(
                f"share_count must be from threshold {threshold} through 31"
            )
        return share_count, None
    assert indices is not None
    normalized = _copied_indices(indices)
    if len(normalized) < threshold:
        raise InvalidShareSelection(
            f"at least threshold {threshold} output indices are required"
        )
    return None, normalized


def _set_header(threshold: int, identifier: str) -> str:
    return f"{threshold}{identifier}"


def _reject_explicit_collision(
    threshold: int,
    identifier: str | None,
    excluded_headers: frozenset[str],
) -> None:
    if identifier is not None and _set_header(threshold, identifier) in excluded_headers:
        raise HeaderCollision(
            f"set header {_set_header(threshold, identifier)!r} is excluded"
        )


def _random_available_identifier(
    threshold: int, excluded_headers: frozenset[str]
) -> str:
    """Draw replacement metadata without touching an accepted secret or basis."""
    while True:
        identifier = _u5_to_chars(tuple(value & 0x1F for value in secrets.token_bytes(4)))
        if _set_header(threshold, identifier) not in excluded_headers:
            return identifier


def _resolve_default_identifier(
    default_identifier: str,
    threshold: int,
    excluded_headers: Collection[str],
) -> str:
    """Retain a derived default unless it collides, then randomize metadata only."""
    normalized_threshold = _validated_threshold(threshold, allow_zero=True)
    normalized_identifier = _validated_identifier(default_identifier)
    exclusions = _snapshot_excluded_headers(excluded_headers)
    if _set_header(normalized_threshold, normalized_identifier) not in exclusions:
        return normalized_identifier
    return _random_available_identifier(normalized_threshold, exclusions)


def _fingerprint_symbols(seed: bytes) -> tuple[int, ...]:
    return tuple(
        _convert_bits(BIP32.from_seed(seed).get_fingerprint(), 8, 5, pad=True)
    )


def _supplied_master_fingerprint(seed: bytes) -> tuple[int, ...]:
    try:
        return _fingerprint_symbols(seed)
    except InvalidInputError as error:
        raise CodexError("the supplied master seed does not form a valid BIP32 root") from error


def _full_fingerprint_identifier(fingerprint: tuple[int, ...]) -> str:
    return _u5_to_chars(fingerprint[:4])


def _reheader(
    artifact: Share | Secret, threshold: int, identifier: str
) -> Share | Secret:
    return _from_parts(
        artifact.profile,
        Header(threshold, identifier, artifact.header.index),
        artifact.payload_symbols,
    )


def _reheader_basis(
    basis: tuple[Share | Secret, ...], threshold: int, identifier: str
) -> tuple[Share | Secret, ...]:
    """Change only public headers/checksums; payload symbols are preserved."""
    return tuple(_reheader(artifact, threshold, identifier) for artifact in basis)


def _random_masks(
    profile: Profile,
    threshold: int,
    identifier: str,
    payload_length: int,
    mask_count: int,
) -> tuple[Share, ...]:
    """Sample all mask symbols for one attempted basis in one CSPRNG call."""
    random_bytes = secrets.token_bytes(mask_count * payload_length)
    symbols = tuple(value & 0x1F for value in random_bytes)
    masks: list[Share] = []
    for position in range(mask_count):
        start = position * payload_length
        payload = symbols[start : start + payload_length]
        artifact = _from_parts(
            profile,
            Header(threshold, identifier, ORDINARY_INDICES[position]),
            payload,
        )
        assert isinstance(artifact, Share)
        masks.append(artifact)
    return tuple(masks)


def _existing_basis(
    secret: MasterSeed | CoreLightningSecret,
    threshold: int,
    identifier: str,
) -> tuple[Share | Secret, ...]:
    reheadered = _reheader(secret, threshold, identifier)
    assert isinstance(reheadered, Secret)
    masks = _random_masks(
        secret.profile,
        threshold,
        identifier,
        len(secret.payload_symbols),
        threshold - 1,
    )
    return (reheadered, *masks)


def _artifact_at(basis: tuple[Share | Secret, ...], index: str) -> Share:
    for artifact in basis:
        if artifact.header.index == index:
            if not isinstance(artifact, Share):
                raise CodexError("ordinary output index unexpectedly selected S")
            return artifact
    return derive_share(basis, index)


def _selected_indices(
    share_count: int | None, explicit_indices: tuple[str, ...] | None
) -> tuple[str, ...]:
    if explicit_indices is not None:
        return explicit_indices
    assert share_count is not None
    return tuple(secrets.SystemRandom().sample(ORDINARY_INDICES, share_count))


def _finalize_shared(
    secret: MasterSeed | CoreLightningSecret,
    basis: tuple[Share | Secret, ...],
    threshold: int,
    identifier: str,
    share_count: int | None,
    explicit_indices: tuple[str, ...] | None,
) -> tuple[MasterSeed | CoreLightningSecret, tuple[Share, ...]]:
    final_secret = _reheader(secret, threshold, identifier)
    if not isinstance(final_secret, (MasterSeed, CoreLightningSecret)):
        raise CodexError("generation did not produce a supported secret")
    final_basis = _reheader_basis(basis, threshold, identifier)
    indices = _selected_indices(share_count, explicit_indices)
    return final_secret, tuple(_artifact_at(final_basis, index) for index in indices)


def _canonical_payload_serialization(
    basis: tuple[Share | Secret, ...], threshold: int
) -> bytes:
    payloads = []
    for index in ORDINARY_INDICES[:threshold]:
        share = _artifact_at(basis, index)
        payloads.append(_u5_to_chars(share.payload_symbols).lower())
    return "".join(payloads).encode("ascii")


def _legacy_shared_identifier(
    master_fingerprint: tuple[int, ...],
    basis: tuple[Share | Secret, ...],
    threshold: int,
) -> str:
    set_fingerprint = _fingerprint_symbols(
        _canonical_payload_serialization(basis, threshold)
    )
    return _u5_to_chars((*master_fingerprint[:2], *set_fingerprint[:2]))


def _validated_master_seed_input(
    seed_bytes: bytes | None, byte_length: int | None
) -> tuple[bytes | None, int]:
    if seed_bytes is not None:
        if not isinstance(seed_bytes, bytes):
            raise TypeError("seed_bytes must be bytes")
        if byte_length is not None:
            raise InvalidLength("byte_length cannot be supplied with seed_bytes")
        if not 16 <= len(seed_bytes) <= 64:
            raise InvalidLength("master seed must contain 16 through 64 bytes")
        return seed_bytes, len(seed_bytes)
    length = 16 if byte_length is None else byte_length
    if isinstance(length, bool) or not isinstance(length, int):
        raise InvalidLength("byte_length must be an integer")
    if not 16 <= length <= 64:
        raise InvalidLength("byte_length must be from 16 through 64")
    return None, length


def generate_master_seed(
    seed_bytes: bytes | None = None,
    *,
    byte_length: int | None = None,
    threshold: int = 0,
    share_count: int | None = None,
    indices: Sequence[str] | str | None = None,
    identifier: str | None = None,
    excluded_headers: Collection[str] = (),
) -> tuple[MasterSeed, tuple[Share, ...]]:
    """Generate or encode an ``ms`` S, optionally producing ordered shares."""
    supplied_seed, length = _validated_master_seed_input(seed_bytes, byte_length)
    threshold = _validated_threshold(threshold, allow_zero=True)
    share_count, explicit_indices = _validated_selection(
        threshold, share_count, indices
    )
    if supplied_seed is not None and identifier is None:
        raise InvalidIdentifier("raw seed bytes require an explicit identifier")
    explicit_identifier = (
        None if identifier is None else _validated_identifier(identifier)
    )
    exclusions = _snapshot_excluded_headers(excluded_headers)
    _reject_explicit_collision(threshold, explicit_identifier, exclusions)
    temporary_identifier = explicit_identifier or _TEMPORARY_IDENTIFIER

    if supplied_seed is not None:
        _supplied_master_fingerprint(supplied_seed)
        secret = MasterSeed.from_seed(
            supplied_seed,
            identifier=temporary_identifier,
            threshold=threshold,
        )
        assert explicit_identifier is not None
        if threshold == 0:
            return secret, ()
        basis = _existing_basis(secret, threshold, temporary_identifier)
        result = _finalize_shared(
            secret,
            basis,
            threshold,
            explicit_identifier,
            share_count,
            explicit_indices,
        )
        assert isinstance(result[0], MasterSeed)
        return result[0], result[1]

    if threshold == 0:
        while True:
            fresh_bytes = secrets.token_bytes(length)
            secret = MasterSeed.from_seed(
                fresh_bytes,
                identifier=temporary_identifier,
                threshold=0,
            )
            try:
                fingerprint = _fingerprint_symbols(fresh_bytes)
            except InvalidInputError:
                continue
            break
        final_identifier = explicit_identifier or _resolve_default_identifier(
            _full_fingerprint_identifier(fingerprint), threshold, exclusions
        )
        final_secret = _reheader(secret, 0, final_identifier)
        assert isinstance(final_secret, MasterSeed)
        return final_secret, ()

    while True:
        fresh_basis = _random_masks(
            Profile.MS,
            threshold,
            temporary_identifier,
            (length * 8 + 4) // 5,
            threshold,
        )
        recovered = recover_secret(fresh_basis)
        if not isinstance(recovered, MasterSeed):
            raise CodexError("fresh ms basis did not recover a master seed")
        if not _has_generation_padding(recovered):
            continue
        try:
            fingerprint = _fingerprint_symbols(recovered.seed_bytes)
        except InvalidInputError:
            continue
        break
    final_identifier = explicit_identifier or _resolve_default_identifier(
        _full_fingerprint_identifier(fingerprint), threshold, exclusions
    )
    result = _finalize_shared(
        recovered,
        fresh_basis,
        threshold,
        final_identifier,
        share_count,
        explicit_indices,
    )
    assert isinstance(result[0], MasterSeed)
    return result[0], result[1]


def generate_core_lightning_secret(
    secret_bytes: bytes | None = None,
    *,
    identifier: str,
    threshold: int = 0,
    share_count: int | None = None,
    indices: Sequence[str] | str | None = None,
    excluded_headers: Collection[str] = (),
) -> tuple[CoreLightningSecret, tuple[Share, ...]]:
    """Generate or encode a fixed-size Core Lightning secret and shares."""
    if secret_bytes is not None:
        if not isinstance(secret_bytes, bytes):
            raise TypeError("secret_bytes must be bytes")
        if len(secret_bytes) != 32:
            raise InvalidLength("Core Lightning secrets must contain exactly 32 bytes")
    threshold = _validated_threshold(threshold, allow_zero=True)
    share_count, explicit_indices = _validated_selection(
        threshold, share_count, indices
    )
    normalized_identifier = _validated_identifier(identifier)
    exclusions = _snapshot_excluded_headers(excluded_headers)
    _reject_explicit_collision(threshold, normalized_identifier, exclusions)

    if secret_bytes is not None:
        secret = CoreLightningSecret.from_secret_bytes(
            secret_bytes,
            identifier=normalized_identifier,
            threshold=threshold,
        )
        if threshold == 0:
            return secret, ()
        basis = _existing_basis(secret, threshold, normalized_identifier)
        result = _finalize_shared(
            secret,
            basis,
            threshold,
            normalized_identifier,
            share_count,
            explicit_indices,
        )
        assert isinstance(result[0], CoreLightningSecret)
        return result[0], result[1]

    if threshold == 0:
        secret = CoreLightningSecret.from_secret_bytes(
            secrets.token_bytes(32),
            identifier=normalized_identifier,
            threshold=0,
        )
        return secret, ()

    while True:
        fresh_basis = _random_masks(
            Profile.CL,
            threshold,
            normalized_identifier,
            52,
            threshold,
        )
        recovered = recover_secret(fresh_basis)
        if not isinstance(recovered, CoreLightningSecret):
            raise CodexError("fresh cl basis did not recover a Core Lightning secret")
        if _payload_padding(recovered) == 0:
            break
    result = _finalize_shared(
        recovered,
        fresh_basis,
        threshold,
        normalized_identifier,
        share_count,
        explicit_indices,
    )
    assert isinstance(result[0], CoreLightningSecret)
    return result[0], result[1]


def split_secret(
    secret: MasterSeed | CoreLightningSecret,
    threshold: int,
    *,
    share_count: int | None = None,
    indices: Sequence[str] | str | None = None,
    identifier: str | None = None,
    excluded_headers: Collection[str] = (),
) -> tuple[MasterSeed | CoreLightningSecret, tuple[Share, ...]]:
    """Split an authenticated S into a new threshold-2-through-9 share set."""
    if not isinstance(secret, (MasterSeed, CoreLightningSecret)):
        raise TypeError("split_secret accepts only MasterSeed or CoreLightningSecret")
    threshold = _validated_threshold(threshold, allow_zero=False)
    share_count, explicit_indices = _validated_selection(
        threshold, share_count, indices
    )
    if isinstance(secret, CoreLightningSecret) and identifier is None:
        raise InvalidIdentifier("Core Lightning share sets require an identifier")
    explicit_identifier = (
        None if identifier is None else _validated_identifier(identifier)
    )
    exclusions = _snapshot_excluded_headers(excluded_headers)
    source_header = _set_header(secret.header.threshold, secret.header.identifier)
    exclusions = _with_source_header(exclusions, source_header)
    _reject_explicit_collision(threshold, explicit_identifier, exclusions)
    temporary_identifier = explicit_identifier or _TEMPORARY_IDENTIFIER

    master_fingerprint: tuple[int, ...] | None = None
    if isinstance(secret, MasterSeed):
        master_fingerprint = _supplied_master_fingerprint(secret.seed_bytes)
    basis = _existing_basis(secret, threshold, temporary_identifier)

    if explicit_identifier is not None:
        final_identifier = explicit_identifier
    else:
        assert master_fingerprint is not None
        try:
            default_identifier = _legacy_shared_identifier(
                master_fingerprint, basis, threshold
            )
        except InvalidInputError:
            # The legacy metadata happens to be an invalid BIP32 seed.  Keep
            # the accepted masks and use independent public metadata instead.
            final_identifier = _random_available_identifier(threshold, exclusions)
        else:
            final_identifier = _resolve_default_identifier(
                default_identifier, threshold, exclusions
            )
    return _finalize_shared(
        secret,
        basis,
        threshold,
        final_identifier,
        share_count,
        explicit_indices,
    )
