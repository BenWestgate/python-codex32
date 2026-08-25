# fmt: off
"""Electronic generation for ``ms`` and Core Lightning share sets."""
# ruff: noqa: I001

import secrets
from collections.abc import Sequence
from collections.abc import Set as AbstractSet

from codex32._bip32 import fingerprint_from_seed
from codex32.bech32 import CHARSET, _convert_bits, _u5_to_chars
from codex32.bip93 import IDX_SORT, CoreLightningSecret, Header, MasterSeed, Secret, Share
from codex32.bip93 import _from_parts, _has_generation_padding, _payload_padding, derive_share, recover_secret
from codex32.errors import CodexError, HeaderCollision, InvalidIdentifier, InvalidLength
from codex32.errors import InvalidShareSelection, InvalidThreshold
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
    if not isinstance(values, str) and (isinstance(values, AbstractSet) or not isinstance(values, Sequence)):
        raise TypeError("indices must be an ordered sequence")
    count = len(values)
    if count > 31:
        raise InvalidShareSelection("at most 31 shares may be requested")
    copied: tuple[object, ...] = tuple(values[position] for position in range(count))
    normalized = tuple(_index(value) for value in copied)
    if len(set(normalized)) != len(normalized):
        raise InvalidShareSelection("output indices must be distinct")
    return normalized

def _selection(
    threshold: int, share_count: object, indices: Sequence[str] | str | None
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
            raise InvalidShareSelection(f"share_count must be from threshold {threshold} through 31")
        return share_count, None
    assert indices is not None
    selected = _indices(indices)
    if len(selected) < threshold:
        raise InvalidShareSelection(f"at least {threshold} indices are required")
    return None, selected

def _random_identifier() -> str:
    return _u5_to_chars(tuple(value & 31 for value in secrets.token_bytes(4)))

def _fingerprint_identifier(seed: bytes) -> str:
    symbols = _convert_bits(fingerprint_from_seed(seed), 8, 5, pad=True)
    return _u5_to_chars(tuple(symbols[:4]))

def _masks(
    profile: Profile, threshold: int, identifier: str, payload_length: int, count: int
) -> tuple[Share, ...]:
    random_bytes = secrets.token_bytes(count * payload_length)
    symbols = tuple(value & 31 for value in random_bytes)
    result = []
    for position in range(count):
        start = position * payload_length
        artifact = _from_parts(
            profile,
            Header(threshold, identifier, ORDINARY_INDICES[position]),
            symbols[start : start + payload_length],
        )
        assert isinstance(artifact, Share)
        result.append(artifact)
    return tuple(result)

def _basis(
    secret: MasterSeed | CoreLightningSecret, threshold: int, identifier: str
) -> tuple[Secret | Share, ...]:
    reheadered = _from_parts(secret.profile, Header(threshold, identifier, "s"), secret.payload_symbols)
    assert isinstance(reheadered, Secret)
    masks = _masks(secret.profile, threshold, identifier, len(secret.payload_symbols), threshold - 1)
    return (reheadered, *masks)

def _share_at(basis: tuple[Secret | Share, ...], index: str) -> Share:
    for artifact in basis:
        if artifact.header.index == index:
            assert isinstance(artifact, Share)
            return artifact
    return derive_share(basis, index)

def _finish[SecretT: Secret](
    secret: SecretT,
    basis: tuple[Secret | Share, ...],
    share_count: int | None,
    explicit: tuple[str, ...] | None,
) -> tuple[SecretT, tuple[Share, ...]]:
    if explicit is None:
        assert share_count is not None
        explicit = tuple(secrets.SystemRandom().sample(ORDINARY_INDICES, share_count))
    return secret, tuple(_share_at(basis, index) for index in explicit)

def _fresh_basis(
    profile: Profile, threshold: int, identifier: str, payload_length: int
) -> tuple[MasterSeed | CoreLightningSecret, tuple[Share, ...]]:
    while True:
        masks = _masks(profile, threshold, identifier, payload_length, threshold)
        secret = recover_secret(masks)
        if isinstance(secret, MasterSeed):
            accepted = _has_generation_padding(secret)
        elif isinstance(secret, CoreLightningSecret):
            accepted = _payload_padding(secret) == 0
        else:
            raise CodexError("generation produced an unsupported secret")
        if accepted:
            return secret, masks

def _seed_input(seed_bytes: bytes | None, byte_length: int | None) -> tuple[bytes | None, int]:
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

def _cl_secret(secret_bytes: bytes, identifier: str, threshold: int) -> CoreLightningSecret:
    if not isinstance(secret_bytes, bytes):
        raise TypeError("secret_bytes must be bytes")
    if len(secret_bytes) != 32:
        raise InvalidLength("Core Lightning secrets must contain exactly 32 bytes")
    payload = tuple(_convert_bits(secret_bytes, 8, 5, pad=True, pad_value=0))
    artifact = _from_parts(Profile.CL, Header(threshold, identifier, "s"), payload)
    assert isinstance(artifact, CoreLightningSecret)
    return artifact

def generate_master_seed(
    seed_bytes: bytes | None = None,
    *,
    byte_length: int | None = None,
    threshold: int = 0,
    share_count: int | None = None,
    indices: Sequence[str] | str | None = None,
    identifier: str | None = None,
) -> tuple[MasterSeed, tuple[Share, ...]]:
    """Generate an ``ms`` secret and selected shares directly from OS entropy.

    Only fresh unshared seeds use fingerprint identifiers; other defaults are random.
    """
    supplied, length = _seed_input(seed_bytes, byte_length)
    threshold = _threshold(threshold)
    share_count, explicit = _selection(threshold, share_count, indices)

    if supplied is not None:
        identifier = _random_identifier() if identifier is None else _identifier(identifier)
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
        recovered, masks = _fresh_basis(Profile.MS, threshold, identifier, payload_length)
        assert isinstance(recovered, MasterSeed)
        try:
            _fingerprint_identifier(recovered.seed_bytes)
        except CodexError:
            continue
        return _finish(recovered, masks, share_count, explicit)

def generate_core_lightning_secret(
    secret_bytes: bytes | None = None,
    *,
    identifier: str | None = None,
    threshold: int = 0,
    share_count: int | None = None,
    indices: Sequence[str] | str | None = None,
) -> tuple[CoreLightningSecret, tuple[Share, ...]]:
    """Generate or encode a CL secret, using a random identifier by default."""
    threshold = _threshold(threshold)
    share_count, explicit = _selection(threshold, share_count, indices)
    identifier = _random_identifier() if identifier is None else _identifier(identifier)
    if secret_bytes is not None or threshold == 0:
        secret = _cl_secret(
            secrets.token_bytes(32) if secret_bytes is None else secret_bytes, identifier, threshold
        )
        if threshold == 0:
            return secret, ()
        return _finish(secret, _basis(secret, threshold, identifier), share_count, explicit)
    recovered, masks = _fresh_basis(Profile.CL, threshold, identifier, 52)
    assert isinstance(recovered, CoreLightningSecret)
    return _finish(recovered, masks, share_count, explicit)

def split_secret(
    secret: MasterSeed | CoreLightningSecret,
    threshold: int,
    *,
    identifier: str | None = None,
    share_count: int | None = None,
    indices: Sequence[str] | str | None = None,
) -> tuple[MasterSeed | CoreLightningSecret, tuple[Share, ...]]:
    """Split a validated secret under a new, random-by-default set header."""
    if not isinstance(secret, (MasterSeed, CoreLightningSecret)):
        raise TypeError("split_secret accepts only MasterSeed or CoreLightningSecret")
    threshold = _threshold(threshold, allow_zero=False)
    random_identifier = identifier is None
    identifier = _random_identifier() if random_identifier else _identifier(identifier)
    while (threshold, identifier) == (secret.header.threshold, secret.header.identifier):
        if not random_identifier:
            raise HeaderCollision("new share set must use a different set header")
        identifier = _random_identifier()
    share_count, explicit = _selection(threshold, share_count, indices)
    basis = _basis(secret, threshold, identifier)
    reheadered = basis[0]
    assert isinstance(reheadered, (MasterSeed, CoreLightningSecret))
    return _finish(reheadered, basis, share_count, explicit)
