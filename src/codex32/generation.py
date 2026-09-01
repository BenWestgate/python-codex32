# fmt: off
"""Electronic generation for ``ms`` and Core Lightning share sets."""
# ruff: noqa: I001
from __future__ import annotations
import secrets
from collections.abc import Sequence, Set as AbstractSet
from dataclasses import dataclass
from typing import Never, SupportsIndex, cast
from codex32.bech32 import CHARSET, _u5_to_chars, convertbits
from codex32.bip93 import IDX_SORT, Header, Secret, Share, _from_parts, derive_share, recover_secret
from codex32.errors import CeremonyStateError, CodexError, HeaderCollision, InvalidIdentifier, InvalidLength, InvalidShareSelection, InvalidThreshold
from codex32.profiles import Profile
from codex32.profiles.cl32 import PAYLOAD_LENGTH as CL_PAYLOAD_LENGTH
from codex32.profiles.cl32 import CoreLightningSecret, _has_generation_padding as _cl_padding, _secret_from_bytes
from codex32.profiles.ms32 import DEFAULT_SEED_BYTES, SEED_BYTE_LENGTHS, MasterSeed, _fingerprint_from_seed, _has_generation_padding as _ms_padding, _payload_length
ORDINARY_INDICES = tuple(IDX_SORT[1:])
@dataclass(frozen=True, slots=True)
class ConfirmationResult:
    """Result of comparing a pending card with its re-entered text."""
    accepted: bool
    mismatched_groups: tuple[int, ...] = ()
def _threshold(value: object, *, allow_zero: bool = True) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidThreshold("threshold must be an integer")
    if value not in ((0, *range(2, 10)) if allow_zero else tuple(range(2, 10))):
        raise InvalidThreshold(f"threshold must be {'0 or ' if allow_zero else ''}2 through 9")
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
    if len(values) > 31:
        raise InvalidShareSelection("at most 31 shares may be requested")
    copied: tuple[object, ...] = tuple(values[position] for position in range(len(values)))
    normalized = tuple(_index(value) for value in copied)
    if len(set(normalized)) != len(normalized):
        raise InvalidShareSelection("output indices must be distinct")
    return normalized
def _selection(threshold: int, share_count: object, indices: Sequence[str] | str | None) -> tuple[str, ...]:
    if (share_count is None) == (indices is None):
        raise InvalidShareSelection("choose exactly one of share_count or indices")
    if share_count is not None:
        if isinstance(share_count, bool) or not isinstance(share_count, int):
            raise InvalidShareSelection("share_count must be an integer")
        if not threshold <= share_count <= 31:
            raise InvalidShareSelection(f"share_count must be from threshold {threshold} through 31")
        return tuple(secrets.SystemRandom().sample(ORDINARY_INDICES, share_count))
    assert indices is not None
    selected = _indices(indices)
    if len(selected) < threshold:
        raise InvalidShareSelection(f"at least {threshold} indices are required")
    return selected
def _random_identifier() -> str:
    return _u5_to_chars(tuple(value & 31 for value in secrets.token_bytes(4)))
def _fingerprint_identifier(seed: bytes) -> str:
    return _u5_to_chars(tuple(convertbits(_fingerprint_from_seed(seed), 8, 5, pad=True)[:4]))
def _random_share(profile: Profile, threshold: int, identifier: str, index: str, length: int) -> Share:
    symbols = tuple(value & 31 for value in secrets.token_bytes(length))
    artifact = _from_parts(profile, Header(threshold, identifier, index), symbols)
    assert isinstance(artifact, Share)
    return artifact
def _seed_input(seed_bytes: bytes | None, byte_length: int | None) -> tuple[bytes | None, int]:
    if seed_bytes is not None:
        if not isinstance(seed_bytes, bytes):
            raise TypeError("seed_bytes must be bytes")
        if byte_length is not None:
            raise InvalidLength("byte_length cannot accompany seed_bytes")
        if len(seed_bytes) not in SEED_BYTE_LENGTHS:
            raise InvalidLength("master seed must contain 16, 20, 24, 28, 32, or 64 bytes")
        return seed_bytes, len(seed_bytes)
    length = DEFAULT_SEED_BYTES if byte_length is None else byte_length
    if isinstance(length, bool) or not isinstance(length, int) or length not in SEED_BYTE_LENGTHS:
        raise InvalidLength("byte_length must be 16, 20, 24, 28, 32, or 64")
    return None, length
def generate_master_seed(seed_bytes: bytes | None = None, *, byte_length: int | None = None,
                         identifier: str | None = None) -> MasterSeed:
    """Generate or encode one unshared ``ms`` secret."""
    supplied, length = _seed_input(seed_bytes, byte_length)
    if supplied is not None:
        identifier = _random_identifier() if identifier is None else _identifier(identifier)
        return MasterSeed.from_seed(supplied, identifier=identifier)
    while True:
        fresh = secrets.token_bytes(length)
        try:
            default_identifier = _fingerprint_identifier(fresh)
        except CodexError:
            continue
        identifier = default_identifier if identifier is None else _identifier(identifier)
        return MasterSeed.from_seed(fresh, identifier=identifier)
def generate_core_lightning_secret(secret_bytes: bytes | None = None, *,
                                   identifier: str | None = None) -> CoreLightningSecret:
    """Generate or encode one unshared Core Lightning HSM secret."""
    identifier = _random_identifier() if identifier is None else _identifier(identifier)
    return _secret_from_bytes(
        secrets.token_bytes(32) if secret_bytes is None else secret_bytes, identifier
    )
class CreationCeremony:
    """Generate and confirm one shared-backup card at a time."""
    _basis: list[Secret | Share]; _direct_count: int; _finished: bool; _indices: tuple[str, ...]
    _payload_length: int; _pending: Share | None; _position: int; _profile: Profile
    _secret: MasterSeed | CoreLightningSecret | None; _set_identifier: str; _threshold: int
    def __init__(self) -> None: raise TypeError("use a CreationCeremony class constructor")
    def __reduce_ex__(self, _protocol: SupportsIndex) -> Never:
        raise TypeError("creation ceremonies cannot be copied or serialized")
    @classmethod
    def _start(cls, profile: Profile, payload_length: int, threshold: int, share_count: int | None,
               indices: Sequence[str] | str | None, identifier: str,
               secret: MasterSeed | CoreLightningSecret | None) -> CreationCeremony:
        self = object.__new__(cls)
        self._profile, self._payload_length = profile, payload_length
        self._threshold, self._set_identifier = threshold, identifier
        self._indices = _selection(threshold, share_count, indices)
        self._position, self._pending, self._finished = 0, None, False
        if secret is None:
            self._secret, self._basis, self._direct_count = None, [], threshold
        else:
            reheadered = _from_parts(profile, Header(threshold, identifier, "s"), secret.payload_symbols)
            assert isinstance(reheadered, (MasterSeed, CoreLightningSecret))
            self._secret, self._basis, self._direct_count = reheadered, [reheadered], threshold - 1
        return self
    @classmethod
    def master_seed(cls, *, threshold: int, byte_length: int = 16, share_count: int | None = None,
                    indices: Sequence[str] | str | None = None,
                    identifier: str | None = None) -> CreationCeremony:
        """Start a ceremony for a fresh shared Bitcoin master seed."""
        threshold = _threshold(threshold, allow_zero=False)
        _supplied, byte_length = _seed_input(None, byte_length)
        identifier = _random_identifier() if identifier is None else _identifier(identifier)
        return cls._start(Profile.MS, _payload_length(byte_length), threshold,
                          share_count, indices, identifier, None)
    @classmethod
    def core_lightning(cls, *, threshold: int, share_count: int | None = None,
                       indices: Sequence[str] | str | None = None,
                       identifier: str | None = None) -> CreationCeremony:
        """Start a ceremony for a fresh shared Core Lightning secret."""
        threshold = _threshold(threshold, allow_zero=False)
        identifier = _random_identifier() if identifier is None else _identifier(identifier)
        return cls._start(
            Profile.CL, CL_PAYLOAD_LENGTH, threshold, share_count, indices, identifier, None
        )
    @classmethod
    def from_secret(cls, secret: MasterSeed | CoreLightningSecret, *, threshold: int,
                    share_count: int | None = None, indices: Sequence[str] | str | None = None,
                    identifier: str | None = None) -> CreationCeremony:
        """Start a ceremony that shares an existing validated secret."""
        if not isinstance(secret, (MasterSeed, CoreLightningSecret)):
            raise TypeError("from_secret accepts only MasterSeed or CoreLightningSecret")
        threshold = _threshold(threshold, allow_zero=False)
        random_identifier = identifier is None
        identifier = _random_identifier() if random_identifier else _identifier(identifier)
        while (threshold, identifier) == (secret.header.threshold, secret.header.identifier):
            if not random_identifier:
                raise HeaderCollision("new share set must use a different set header")
            identifier = _random_identifier()
        return cls._start(secret.profile, len(secret.payload_symbols), threshold,
                          share_count, indices, identifier, secret)
    def _candidate_is_accepted(self, secret: MasterSeed | CoreLightningSecret) -> bool:
        if isinstance(secret, CoreLightningSecret): return _cl_padding(secret)
        try: _fingerprint_from_seed(secret.seed_bytes)
        except CodexError: return False
        return _ms_padding(secret)
    def next_share(self) -> Share:
        """Generate or derive the next card after the previous card is confirmed."""
        if self._finished:
            raise CeremonyStateError("this creation ceremony is finished")
        if self._pending is not None:
            raise CeremonyStateError("confirm the pending card before requesting another")
        if self._position == len(self._indices):
            raise CeremonyStateError("all cards are confirmed; finish the ceremony")
        index = self._indices[self._position]
        if self._position < self._direct_count:
            while True:
                pending = _random_share(self._profile, self._threshold, self._set_identifier,
                                        index, self._payload_length)
                if self._position + 1 < self._direct_count or self._secret is not None:
                    break
                candidate = recover_secret((*cast(list[Share], self._basis), pending))
                assert isinstance(candidate, (MasterSeed, CoreLightningSecret))
                if self._candidate_is_accepted(candidate):
                    self._secret = candidate
                    break
        else:
            pending = derive_share(tuple(self._basis), index)
        self._pending = pending
        return pending
    def confirm(self, text: str) -> ConfirmationResult:
        """Confirm the pending card using independently re-entered text."""
        if self._finished:
            raise CeremonyStateError("this creation ceremony is finished")
        if self._pending is None:
            raise CeremonyStateError("request a card before confirming it")
        if not isinstance(text, str):
            raise TypeError("confirmation text must be str")
        observed = "".join(text.split()).lower()
        expected = self._pending.text.lower()
        mismatched = tuple(group + 1 for group in range((max(len(observed), len(expected)) + 3) // 4)
            if observed[group * 4 : group * 4 + 4] != expected[group * 4 : group * 4 + 4]
        )
        if mismatched:
            return ConfirmationResult(False, mismatched)
        if self._position < self._direct_count:
            self._basis.append(self._pending)
        self._position += 1
        self._pending = None
        return ConfirmationResult(True)
    def finish(self) -> MasterSeed | CoreLightningSecret:
        """Return the secret after every requested card is confirmed."""
        if self._finished:
            raise CeremonyStateError("this creation ceremony is finished")
        if self._pending is not None or self._position != len(self._indices):
            raise CeremonyStateError("confirm every card before finishing the ceremony")
        secret = self._secret
        assert isinstance(secret, (MasterSeed, CoreLightningSecret))
        self._finished = True
        self._basis.clear(); self._indices = (); self._secret = None
        return secret
