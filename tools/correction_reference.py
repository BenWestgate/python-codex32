"""Reference-only structural helpers used by tests and correction benchmarks."""

from collections.abc import Iterator
from itertools import combinations

from codex32.indel import (
    _CLASSES,
    _alignment_counts,
    _StructuralClass,
    _Variant,
    _view_variant,
    _views,
)

_REDUCED_CLASSES = tuple(shape for shape in _CLASSES if shape.unit == 4 or shape.distance <= 3)


def _alignment_count(
    shape: _StructuralClass,
    observed_length: int,
    target_length: int,
    immutable_length: int,
) -> int:
    return sum(_alignment_counts(shape, "q" * observed_length, target_length, immutable_length).values())


def _reductions(
    values: tuple[int, ...],
    characters: str,
    count: int,
    offset: int,
) -> Iterator[tuple[tuple[int, ...], tuple[tuple[int, str], ...]]]:
    for deleted in combinations(range(len(values)), count):
        removed = frozenset(deleted)
        kept = tuple(index for index in range(len(values)) if index not in removed)
        retained = tuple(values[index] for index in kept)
        position = 0
        for kept_index in kept:
            while values[position] != values[kept_index]:
                position += 1
            if position != kept_index:
                break
            position += 1
        else:
            edits = tuple((offset + index, characters[index]) for index in deleted)
            yield retained, edits


def _variants(
    text: str, target: int, shape: _StructuralClass, immutable: int, prefix_length: int = 3
) -> Iterator[_Variant]:
    for view in _views(text, target, shape, immutable, prefix_length):
        yield _view_variant(view, text, prefix_length)
