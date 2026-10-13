"""Electronic master-seed generation and sharing."""

from __future__ import annotations

import secrets
from collections.abc import Callable, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from typing import NoReturn, SupportsIndex, cast

from codex32._bip32 import _valid_root
from codex32.bech32 import CHARSET, _u5_to_chars, convertbits
from codex32.bip93 import (
    DEFAULT_SEED_BYTES,
    IDX_SORT,
    MS,
    SEED_BYTE_LENGTHS,
    Header,
    MasterSeed,
    Secret,
    Share,
    _from_parts,
    _has_generation_padding,
    _payload_length,
    derive_share,
    recover_secret,
)
from codex32.errors import (
    CeremonyStateError,
    CodexError,
    HeaderCollision,
    InvalidIdentifier,
    InvalidLength,
    InvalidShareSelection,
    InvalidThreshold,
)

ORDINARY_INDICES = tuple(IDX_SORT[1:])


@dataclass(frozen=True, slots=True)
class ConfirmationResult:
    """Result of comparing a pending card with its re-entered text."""

    accepted: bool
    mismatched_groups: tuple[int, ...] = ()
    entered_groups: tuple[str, ...] = ()


def _confirmation(text: str, expected: str) -> ConfirmationResult:
    """Compare re-entered text with a card, group by group, allowing shifts."""
    groups, changed = _entered_groups(text, expected)
    return ConfirmationResult(not changed, tuple(index + 1 for index in sorted(changed)), tuple(groups))


def _entered_groups(observed: str, expected: str) -> tuple[list[str], set[int]]:
    # Keep entered tokens whole unless they exactly span complete groups.
    # Unspaced input retains edit/group minimization and edit-order ties.
    positions = [i for i, char in enumerate(observed) if not char.isspace()]
    compact = "".join(observed.split())
    expected = "".join(expected.split()).lower()
    tokens = observed.split()
    grouped = len(tokens) > 1 and compact.lower() != expected
    boundaries = {0}
    splits: set[tuple[int, int]] = set()
    position = 0
    for token in tokens:
        for offset in range(0, len(expected), 4):
            if expected[offset : offset + len(token)] == token.lower() and (
                len(token) % 4 == 0 or offset + len(token) == len(expected)
            ):
                splits.update((position + i, offset + i) for i in range(4, len(token), 4))
        position += len(token)
        boundaries.add(position)
    scores = {0: (0, 0, b"", ())}  # type: dict[int, tuple[int, int, bytes, tuple[int, ...]]]
    for offset in range(0, len(expected), 4):
        canonical = expected[offset : offset + 4]
        following: dict[int, tuple[int, int, bytes, tuple[int, ...]]] = {}
        for start, (edits, disturbed, trace, ends) in scores.items():
            row = [(j, b"\x03" * j) for j in range(len(canonical) + 1)]
            for end in range(start, len(compact) + 1):
                if end > start:
                    current = [(end - start, b"\x02" * (end - start))]
                    for j, char in enumerate(canonical, 1):
                        edit = compact[end - 1].lower() != char
                        current.append(
                            min(
                                (row[j - 1][0] + edit, row[j - 1][1] + bytes([edit])),
                                (row[j][0] + 1, row[j][1] + b"\x02"),
                                (current[j - 1][0] + 1, current[j - 1][1] + b"\x03"),
                            )
                        )
                    row = current
                if grouped and end not in boundaries and (end, offset + len(canonical)) not in splits:
                    continue
                score = (
                    edits + row[-1][0],
                    disturbed + (not grouped and compact[start:end].lower() != canonical),
                    trace + row[-1][1],
                    (*ends, end),
                )
                if end not in following or score < following[end]:
                    following[end] = score
        scores = following
    groups = []
    start = 0
    for end in scores[len(compact)][3]:
        stop = positions[end] if end < len(positions) else len(observed)
        groups.append(observed[start:stop])
        start = stop
    changed = {
        i for i, value in enumerate(groups) if "".join(value.split()).lower() != expected[i * 4 : i * 4 + 4]
    }
    return groups, changed


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


def _fingerprint_identifier(fingerprint: bytes) -> str:
    if not isinstance(fingerprint, bytes):
        raise TypeError("fingerprint must be bytes")
    if len(fingerprint) != 4:
        raise ValueError("fingerprint must contain four bytes")
    return _u5_to_chars(tuple(convertbits(fingerprint, 8, 5, pad=True)[:4]))


def _random_share(threshold: int, identifier: str, index: str, length: int) -> Share:
    symbols = tuple(value & 31 for value in secrets.token_bytes(length))
    artifact = _from_parts(MS, Header(threshold, identifier, index), symbols)
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


def generate_master_seed(
    seed_bytes: bytes | None = None,
    *,
    byte_length: int | None = None,
    identifier: str | None = None,
    fingerprint: Callable[[bytes], bytes] | None = None,
) -> MasterSeed:
    """Generate or encode one unshared ``ms`` secret."""
    supplied, length = _seed_input(seed_bytes, byte_length)
    if supplied is not None:
        if not _valid_root(supplied):
            raise CodexError("master seed does not form a valid BIP32 root")
        identifier = _random_identifier() if identifier is None else _identifier(identifier)
        return MasterSeed.from_seed(supplied, identifier=identifier)
    if identifier is None and fingerprint is None:
        raise ValueError(
            "fresh unshared master-seed generation requires a fingerprint provider or identifier"
        )
    selected_identifier = _identifier(identifier) if identifier is not None else None
    while True:
        fresh = secrets.token_bytes(length)
        if not _valid_root(fresh):
            continue
        if selected_identifier is not None:
            return MasterSeed.from_seed(fresh, identifier=selected_identifier)
        assert fingerprint is not None
        return MasterSeed.from_seed(fresh, identifier=_fingerprint_identifier(fingerprint(fresh)))


class CreationCeremony:
    """Generate and confirm one shared-backup card at a time."""

    _basis: list[Secret | Share]
    _direct_count: int
    _finished: bool
    _indices: tuple[str, ...]
    _payload_length: int
    _pending: Share | None
    _position: int
    _secret: MasterSeed | None
    _set_identifier: str
    _threshold: int

    def __init__(self) -> None:
        raise TypeError("use a CreationCeremony class constructor")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("creation ceremonies cannot be copied or serialized")

    @classmethod
    def _start(
        cls,
        payload_length: int,
        threshold: int,
        share_count: int | None,
        indices: Sequence[str] | str | None,
        identifier: str,
        secret: MasterSeed | None,
    ) -> CreationCeremony:
        self = object.__new__(cls)
        self._payload_length = payload_length
        self._threshold, self._set_identifier = threshold, identifier
        self._indices = _selection(threshold, share_count, indices)
        self._position, self._pending, self._finished = 0, None, False
        if secret is None:
            self._secret, self._basis, self._direct_count = None, [], threshold
        else:
            reheadered = _from_parts(MS, Header(threshold, identifier, "s"), secret.payload_symbols)
            assert isinstance(reheadered, MasterSeed)
            self._secret, self._basis, self._direct_count = (
                reheadered,
                [reheadered],
                threshold - 1,
            )
        return self

    @classmethod
    def master_seed(
        cls,
        *,
        threshold: int,
        byte_length: int = 16,
        share_count: int | None = None,
        indices: Sequence[str] | str | None = None,
        identifier: str | None = None,
    ) -> CreationCeremony:
        """Start a ceremony for a fresh shared Bitcoin master seed."""
        threshold = _threshold(threshold, allow_zero=False)
        _supplied, byte_length = _seed_input(None, byte_length)
        identifier = _random_identifier() if identifier is None else _identifier(identifier)
        return cls._start(
            _payload_length(byte_length),
            threshold,
            share_count,
            indices,
            identifier,
            None,
        )

    @classmethod
    def from_secret(
        cls,
        secret: MasterSeed,
        *,
        threshold: int,
        share_count: int | None = None,
        indices: Sequence[str] | str | None = None,
        identifier: str | None = None,
    ) -> CreationCeremony:
        """Start a ceremony that shares an existing validated master seed."""
        if not isinstance(secret, MasterSeed):
            raise TypeError("from_secret accepts only MasterSeed")
        threshold = _threshold(threshold, allow_zero=False)
        random_identifier = identifier is None
        identifier = _random_identifier() if random_identifier else _identifier(identifier)
        while (threshold, identifier) == (
            secret.header.threshold,
            secret.header.identifier,
        ):
            if not random_identifier:
                raise HeaderCollision("new share set must use a different set header")
            identifier = _random_identifier()
        return cls._start(
            len(secret.payload_symbols),
            threshold,
            share_count,
            indices,
            identifier,
            secret,
        )

    def _candidate_is_accepted(self, secret: MasterSeed) -> bool:
        return _valid_root(secret.seed_bytes) and _has_generation_padding(secret)

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
                pending = _random_share(
                    self._threshold,
                    self._set_identifier,
                    index,
                    self._payload_length,
                )
                if self._position + 1 < self._direct_count or self._secret is not None:
                    break
                candidate = recover_secret((*cast(list[Share], self._basis), pending))
                assert isinstance(candidate, MasterSeed)
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
        result = _confirmation(text, self._pending.text)
        if not result.accepted:
            return result
        if self._position < self._direct_count:
            self._basis.append(self._pending)
        self._position += 1
        self._pending = None
        return result

    def finish(self) -> MasterSeed:
        """Return the secret after every requested card is confirmed."""
        if self._finished:
            raise CeremonyStateError("this creation ceremony is finished")
        if self._pending is not None or self._position != len(self._indices):
            raise CeremonyStateError("confirm every card before finishing the ceremony")
        secret = self._secret
        assert isinstance(secret, MasterSeed)
        self._finished = True
        self._basis.clear()
        self._indices = ()
        self._secret = None
        return secret
