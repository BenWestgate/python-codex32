# fmt: off
"""Enumerate bounded alignments; correction.py performs every symbol repair."""
# ruff: noqa: I001
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, replace
from itertools import combinations
from math import comb
from time import monotonic

from codex32.bech32 import CHARSET, _checksum_for_encoded_length, _validate_single_case_ascii
from codex32.correction import CorrectionCandidate, CorrectionContext, CorrectionEdit
from codex32.correction import _FixedCorrector, _allowed, _capture_volume, _correct_fixed, _primary
from codex32.errors import CodexError
_FALSE_BOUND_DENOMINATOR = 100_000
_REDUCTION_CACHE_LIMIT = 20_000
_THRESHOLDS = frozenset(CHARSET.index(value) for value in "023456789")
_SECRET_INDEX = CHARSET.index("s")
@dataclass(frozen=True, slots=True)
class _StructuralClass:
    inserted: int
    omitted: int
    unit: int = 1

    @property
    def delta(self) -> int:
        return self.unit * (self.inserted - self.omitted)

    @property
    def erasures(self) -> int:
        return self.unit * self.omitted
@dataclass(frozen=True, slots=True)
class _Variant:
    symbols: tuple[int, ...]
    missing: frozenset[int]
    deleted: tuple[tuple[int, str], ...]
    unknowns: tuple[tuple[int, str], ...]
    erasure_indices: tuple[int, ...]
_FIXED = _StructuralClass(0, 0)
_CHARACTER_CLASSES = tuple(
    _StructuralClass(inserted, total - inserted)
    for total in range(1, 5) for inserted in range(total + 1)
)
_GROUP_CLASSES = tuple(
    _StructuralClass(inserted, total - inserted, 4)
    for total in range(1, 3) for inserted in range(total + 1)
)
_CLASSES = (_FIXED, *_CHARACTER_CLASSES, *_GROUP_CLASSES)
def _group_boundary(immutable_length: int) -> int:
    return 4 * ((immutable_length + 3) // 4)
def _alignment_count(
    shape: _StructuralClass, observed_length: int, target_length: int,
    immutable_length: int,
) -> int:
    if shape == _FIXED:
        return 1
    if shape.unit == 1:
        observed = observed_length - immutable_length
        target = target_length - immutable_length
    else:
        boundary = _group_boundary(immutable_length)
        observed = (observed_length - boundary) // 4
        target = (target_length - boundary) // 4
    if min(observed, target) < 0:
        return 0
    return comb(observed, shape.inserted) * comb(target, shape.omitted)
def _reductions(
    values: tuple[int, ...], characters: str, count: int, offset: int,
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
def _insert(values: tuple[int, ...], positions: Sequence[int], width: int) -> tuple[int, ...]:
    result = values
    for position in positions:
        result = result[: width * position] + (-1,) * width + result[width * position :]
    return result
def _insert_text(text: str, positions: Sequence[int], width: int) -> str:
    for position in positions:
        text = text[: width * position] + "?" * width + text[width * position :]
    return text
def _variant(
    values: tuple[int, ...], missing: frozenset[int], deleted: tuple[tuple[int, str], ...],
    base_length: int, characters: str,
) -> _Variant:
    body = values[base_length:]
    missing_body = frozenset(position - base_length for position in missing)
    unknowns = tuple(
        (position, characters[base_length + position])
        for position, value in enumerate(body)
        if value < 0 and position not in missing_body
    )
    erasures = tuple(index for index, value in enumerate(reversed(body)) if value < 0)
    return _Variant(body, missing, deleted, unknowns, erasures)
def _character_variants(
    text: str, target: int, shape: _StructuralClass, immutable: int, base: int,
) -> Iterator[_Variant]:
    locked = tuple(CHARSET.find(char.lower()) for char in text[:immutable])
    characters = text[immutable:]
    values = tuple(CHARSET.find(char.lower()) for char in characters)
    reductions = _reductions(values, characters, shape.inserted, immutable)
    cached = tuple(reductions) if comb(len(values), shape.inserted) <= _REDUCTION_CACHE_LIMIT else None
    mutable_target = target - immutable
    for omitted in combinations(range(mutable_target), shape.omitted):
        missing = frozenset(immutable + position for position in omitted)
        erasures = tuple(target - position - 1 for position in sorted(missing, reverse=True))
        active = cached if cached is not None else _reductions(
            values, characters, shape.inserted, immutable,
        )
        for retained, deleted in active:
            aligned = locked + _insert(retained, omitted, 1)
            if -1 not in values:
                yield _Variant(aligned[base:], missing, deleted, (), erasures)
            else:
                removed = frozenset(position - immutable for position, _value in deleted)
                retained_text = "".join(
                    value for index, value in enumerate(characters) if index not in removed
                )
                aligned_text = text[:immutable] + _insert_text(retained_text, omitted, 1)
                yield _variant(aligned, missing, deleted, base, aligned_text)
def _group_variants(
    text: str, target: int, shape: _StructuralClass, immutable: int, base: int,
) -> Iterator[_Variant]:
    boundary = _group_boundary(immutable)
    target_groups = (target - boundary) // 4
    observed_groups = target_groups + shape.inserted - shape.omitted
    group_end = boundary + 4 * observed_groups
    head = tuple(CHARSET.find(char.lower()) for char in text[:boundary])
    tail = tuple(CHARSET.find(char.lower()) for char in text[group_end:])
    group_text = text[boundary:group_end]
    groups = tuple(
        tuple(CHARSET.find(char.lower()) for char in group_text[start : start + 4])
        for start in range(0, len(group_text), 4)
    )
    reductions: list[tuple[tuple[int, ...], tuple[tuple[int, str], ...]]] = []
    seen: set[tuple[tuple[int, ...], ...]] = set()
    for deleted_groups in combinations(range(len(groups)), shape.inserted):
        removed = frozenset(deleted_groups)
        retained_groups = tuple(group for index, group in enumerate(groups) if index not in removed)
        if retained_groups in seen:
            continue
        seen.add(retained_groups)
        deleted = tuple(
            (boundary + 4 * group + offset, group_text[4 * group + offset])
            for group in deleted_groups for offset in range(4)
        )
        reductions.append((sum(retained_groups, ()), deleted))
    for omitted_groups in combinations(range(target_groups), shape.omitted):
        missing = frozenset(
            boundary + 4 * group + offset
            for group in omitted_groups for offset in range(4)
        )
        erasures = tuple(target - position - 1 for position in sorted(missing, reverse=True))
        for retained, deleted in reductions:
            aligned = head + _insert(retained, omitted_groups, 4) + tail
            if all(value >= 0 for value in aligned):
                yield _Variant(aligned[base:], missing, deleted, (), erasures)
            else:
                removed = frozenset(position for position, _value in deleted)
                retained_text = "".join(
                    value for position, value in enumerate(text[boundary:group_end], boundary)
                    if position not in removed
                )
                aligned_text = (
                    text[:boundary] + _insert_text(retained_text, omitted_groups, 4) + text[group_end:]
                )
                yield _variant(aligned, missing, deleted, base, aligned_text)
def _variants(
    text: str, target: int, shape: _StructuralClass, immutable: int,
    prefix_length: int = 3,
) -> Iterator[_Variant]:
    generator = _character_variants if shape.unit == 1 else _group_variants
    yield from generator(text, target, shape, immutable, prefix_length)
def _remaining_explicit_counts(shape: _StructuralClass, explicit: int) -> range:
    if shape == _FIXED:
        return range(explicit, explicit + 1)
    return range(max(0, explicit - shape.unit * shape.inserted), explicit + 1)
def _capacities(erasures: int, _degree: int) -> range:
    return range((8 - erasures) // 2 + 1) if erasures <= 8 else range(0)
def _volumes(
    shape: _StructuralClass, alignments: int, mutable: int, explicit: int, degree: int,
) -> Iterator[int]:
    for remaining in _remaining_explicit_counts(shape, explicit):
        erasures = shape.erasures + remaining
        capacities = range(1) if shape == _FIXED and 8 < erasures <= degree else _capacities(
            erasures, degree,
        )
        for substitutions in capacities:
            yield alignments * _capture_volume(mutable, erasures, substitutions)
def _safe(
    rank: int, classes: Sequence[_StructuralClass], counts: dict[_StructuralClass, int],
    mutable: int, explicit: int, degree: int,
) -> bool:
    cumulative = sum(
        volume for shape in classes
        for volume in _volumes(shape, counts[shape], mutable, explicit, degree)
        if volume <= rank
    )
    return _FALSE_BOUND_DENOMINATOR * cumulative < 1 << (5 * degree)
def _required_header_substitutions(symbols: Sequence[int], excluded: frozenset[int]) -> int:
    if len(symbols) < 6:
        return 9
    threshold, index = symbols[0], symbols[5]
    required = int(threshold >= 0 and threshold not in _THRESHOLDS)
    required += index >= 0 and (index in excluded or threshold == 0 and index != _SECRET_INDEX)
    return required
def _adapt(
    fixed: CorrectionCandidate, variant: _Variant, alignments: int, observed_length: int,
    target_length: int,
) -> CorrectionCandidate:
    missing_indices = frozenset(target_length - position - 1 for position in variant.missing)
    edits = tuple(
        replace(edit, kind="insertion", observed="")
        if edit.kind == "erasure" and edit.reverse_index in missing_indices else edit
        for edit in fixed.edits
    )
    edits += tuple(
        CorrectionEdit("deletion", observed_length - position - 1, character, "")
        for position, character in variant.deleted
    )
    return replace(fixed, edits=tuple(sorted(edits, key=lambda edit: edit.reverse_index)),
                   capture_volume=alignments * fixed.capture_volume)
def _normalize(context: CorrectionContext, damaged_text: str) -> tuple[str, int] | None:
    target = context.expected_length
    assert target is not None
    if len(damaged_text) > 2 * (target + 8):
        return None
    text = damaged_text.replace(" ", "")
    try:
        _validate_single_case_ascii(text, max_length=target + 8)
    except CodexError:
        return None
    prefix = context.immutable_prefix or f"{context.profile.value}1"
    matches = text.startswith(prefix) if context.immutable_prefix else text.lower().startswith(prefix)
    if not matches or not target - 8 <= len(text) <= target + 8:
        return None
    return text, len(prefix)
def _has_consecutive_ambiguity(
    context: CorrectionContext, damaged_text: str, deadline: float | None,
) -> bool:
    """Prove that an extra-only alignment plus a fixed erasure burst is ambiguous."""
    normalized = _normalize(context, damaged_text)
    if normalized is None:
        return False
    text, immutable = normalized
    target = context.expected_length
    assert target is not None
    base = len(context.profile.value) + 1
    shapes = tuple(
        shape for shape in _CLASSES
        if shape != _FIXED and not shape.erasures and shape.delta == len(text) - target
    )
    degree = _checksum_for_encoded_length(context.profile.value, target - base).length
    solver = _FixedCorrector(context.profile, target - base, text.isupper(), None, immutable - base)
    results: set[str] = set()
    for shape in sorted(shapes, key=lambda item: item.unit == 1):
        for variant in _variants(text, target, shape, immutable, base):
            if deadline is not None and monotonic() >= deadline:
                return False
            positions = variant.erasure_indices
            if not 8 < len(positions) <= degree or positions != tuple(range(positions[0], positions[-1] + 1)):
                continue
            fixed = solver.correct(variant.symbols, variant.unknowns, variant.erasure_indices)
            if fixed is not None and _allowed(context, fixed):
                results.add(fixed.artifact.text.lower())
                if len(results) > 1:
                    return True
    return False

def _search(
    context: CorrectionContext, damaged_text: str, *, deadline: float | None = None,
) -> tuple[tuple[CorrectionCandidate, ...], bool]:
    normalized = _normalize(context, damaged_text)
    if normalized is None:
        return (), True
    text, immutable = normalized
    target = context.expected_length
    assert target is not None
    base_length = len(context.profile.value) + 1
    delta = len(text) - target
    shapes = tuple(shape for shape in _CLASSES if shape.delta == delta)
    counts = {shape: _alignment_count(shape, len(text), target, immutable) for shape in shapes}
    mutable = target - immutable
    explicit = sum(character.lower() not in CHARSET for character in text[immutable:])
    checksum = _checksum_for_encoded_length(context.profile.value, target - base_length)
    degree = checksum.length
    excluded = frozenset(CHARSET.index(value.lower()) for value in context.excluded_indices)
    results: dict[str, CorrectionCandidate] = {}

    if _FIXED in shapes:
        fixed = _correct_fixed(text, suspected_profile=context.profile,
                               immutable_prefix=context.immutable_prefix)
        positions = tuple(
            index for index, character in enumerate(text[immutable:])
            if character.lower() not in CHARSET
        )
        consecutive = not positions or positions == tuple(range(positions[0], positions[-1] + 1))
        if fixed is not None and _allowed(context, fixed):
            if 8 < fixed.erasures_filled <= degree and consecutive:
                return (fixed,), True
            if fixed.erasures_filled <= 8 and _safe(
                fixed.capture_volume, shapes, counts, mutable, explicit, degree,
            ):
                results[fixed.artifact.text.lower()] = fixed

    structural = [shape for shape in shapes if shape != _FIXED and counts[shape]]
    floors = {
        shape: min(_volumes(shape, counts[shape], mutable, explicit, degree), default=0)
        for shape in structural
    }
    structural.sort(key=lambda shape: (floors[shape], shape.unit, shape.inserted))
    solvers: dict[int, _FixedCorrector] = {}
    for shape in structural:
        best = min((item.capture_volume for item in results.values()), default=None)
        if best is not None and floors[shape] > best:
            break
        possible = sorted(set(_volumes(shape, counts[shape], mutable, explicit, degree)))
        allowed = [rank for rank in possible if (best is None or rank <= best) and _safe(
            rank, shapes, counts, mutable, explicit, degree,
        )]
        if not allowed:
            continue
        if deadline is not None and monotonic() >= deadline:
            return _primary(tuple(results.values())), False
        max_rank = max(allowed)
        max_substitutions = max(
            substitution
            for remaining in _remaining_explicit_counts(shape, explicit)
            for substitution in _capacities(shape.erasures + remaining, degree)
            if counts[shape] * _capture_volume(
                mutable, shape.erasures + remaining, substitution,
            ) <= max_rank
        )
        solver = solvers.setdefault(
            max_substitutions,
            _FixedCorrector(context.profile, target - base_length, text.isupper(), max_substitutions,
                            immutable - base_length),
        )
        for variant in _variants(text, target, shape, immutable, base_length):
            remaining = len(variant.unknowns)
            total_erasures = shape.erasures + remaining
            capacity = max(_capacities(total_erasures, degree), default=-1)
            if capacity < 0:
                continue
            limit = max(
                (
                    substitution for substitution in range(min(max_substitutions, capacity) + 1)
                    if counts[shape] * _capture_volume(
                        mutable, total_erasures, substitution,
                    ) <= max_rank
                ),
                default=-1,
            )
            if limit < 0:
                continue
            if _required_header_substitutions(variant.symbols, excluded) > limit:
                continue
            active = solver if limit == max_substitutions else solvers.setdefault(
                limit, _FixedCorrector(context.profile, target - base_length, text.isupper(), limit,
                                       immutable - base_length),
            )
            fixed = active.correct(variant.symbols, variant.unknowns, variant.erasure_indices)
            if fixed is None or not _allowed(context, fixed):
                continue
            candidate = _adapt(fixed, variant, counts[shape], len(text), target)
            if candidate.capture_volume > max_rank or not _safe(
                candidate.capture_volume, shapes, counts, mutable, explicit, degree,
            ):
                continue
            key = candidate.artifact.text.lower()
            current = results.get(key)
            rank = candidate.capture_volume, candidate.addend_hamming_weight
            if current is None or rank < (current.capture_volume, current.addend_hamming_weight):
                results[key] = candidate
    return _primary(tuple(results.values())), True
