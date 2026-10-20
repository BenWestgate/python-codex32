"""Small piece tables and shifted syndrome prefixes for bounded alignment."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import overload


@dataclass(frozen=True, slots=True)
class _View(Sequence[int]):
    source: tuple[int, ...]
    spans: tuple[tuple[int, int], ...]
    length: int
    masked: tuple[int, ...] = ()

    def __len__(self) -> int:
        return self.length

    @overload
    def __getitem__(self, index: int) -> int: ...

    @overload
    def __getitem__(self, index: slice) -> tuple[int, ...]: ...

    def __getitem__(self, index: int | slice) -> int | tuple[int, ...]:
        if isinstance(index, slice):
            return tuple(self[i] for i in range(*index.indices(self.length)))
        if index < 0:
            index += self.length
        if not 0 <= index < self.length:
            raise IndexError(index)
        for start, size in self.spans:
            if index < size:
                return -1 if start < 0 or start + index in self.masked else self.source[start + index]
            index -= size
        raise AssertionError("piece table length mismatch")

    def pieces(self, left: int, right: int) -> tuple[tuple[int, int], ...]:
        result = []
        offset = 0
        for start, size in self.spans:
            a, b = max(left, offset), min(right, offset + size)
            if a < b:
                result.append((-1 if start < 0 else start + a - offset, b - a))
            offset += size
        return tuple(result)

    def splice(self, position: int, removed: int, inserted: int) -> _View:
        spans = self.pieces(0, position)
        if inserted:
            spans += ((-1, inserted),)
        spans += self.pieces(position + removed, self.length)
        return _View(self.source, spans, self.length - removed + inserted, self.masked)

    def swap(self, left: int, right: int, width: int) -> _View:
        return _View(
            self.source,
            self.pieces(0, left)
            + self.pieces(right, right + width)
            + self.pieces(left + width, right)
            + self.pieces(left, left + width)
            + self.pieces(right + width, self.length),
            self.length,
            self.masked,
        )

    def mask(self, position: int, width: int) -> _View:
        masked = set(self.masked)
        for start, size in self.pieces(position, position + width):
            if start >= 0:
                masked.update(range(start, start + size))
        return _View(self.source, self.spans, self.length, tuple(sorted(masked)))

    def unknown_positions(self, explicit: tuple[int, ...]) -> Iterator[tuple[int, int]]:
        """Yield (aligned position, source position); -1 marks generated erasures."""
        offset = 0
        for start, size in self.spans:
            if start < 0:
                yield from ((position, -1) for position in range(offset, offset + size))
            else:
                for position in (*explicit, *(i for i in self.masked if i not in explicit)):
                    if start <= position < start + size:
                        yield offset + position - start, position
            offset += size


class _IncrementalSyndromes:
    """Compose unchanged shifted segments and at most four-symbol moved pieces."""

    def __init__(self, alignment: tuple[int, tuple[tuple[int, ...], ...]], source: tuple[int, ...]) -> None:
        self.base, self.effects = alignment
        self.prefixes: dict[int, tuple[int, ...]] = {}
        for shift in range(-8, 9):
            prefix = [0]
            for position, value in enumerate(source):
                target = position + shift
                effect = self.effects[target][value] if 0 <= target < len(self.effects) else 0
                prefix.append(prefix[-1] ^ effect)
            self.prefixes[shift] = tuple(prefix)

    def packed(self, view: _View) -> int:
        result, offset = self.base, 0
        for start, size in view.spans:
            if start >= 0:
                shift = offset - start
                if shift in self.prefixes:
                    prefix = self.prefixes[shift]
                    result ^= prefix[start] ^ prefix[start + size]
                else:
                    # Only moved character/four-character pieces have distant shifts.
                    for index in range(size):
                        result ^= self.effects[offset + index][view.source[start + index]]
                for position in view.masked:
                    if start <= position < start + size:
                        result ^= self.effects[offset + position - start][view.source[position]]
            offset += size
        return result
