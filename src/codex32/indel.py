# fmt: off
"""Enumerate bounded alignments; correction.py performs every symbol repair."""
# ruff: noqa: I001
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, replace
from itertools import combinations, groupby
from math import comb
from time import monotonic

from codex32.bech32 import CHARSET, _validate_single_case_ascii
from codex32.bip93 import _checksum_for_encoded_length
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
_REDUCED_CLASSES = (
    _FIXED,
    *(shape for shape in _CHARACTER_CLASSES if shape.inserted + shape.omitted <= 3),
    *(shape for shape in _GROUP_CLASSES if shape.inserted + shape.omitted <= 2),
)
def _group_boundary(immutable_length: int) -> int:
    return 4 * ((immutable_length + 3) // 4)
def _alignment_counts(shape: _StructuralClass, text: str, target_length: int,
                      immutable_length: int) -> dict[int, int]:
    explicit = sum(character.lower() not in CHARSET for character in text[immutable_length:])
    if shape == _FIXED: return {explicit: 1}
    if shape.unit == 1:
        observed, target = len(text) - immutable_length, target_length - immutable_length
        if min(observed, target) < 0: return {}
        known = observed - explicit
        omitted = comb(target, shape.omitted)
        return {
            explicit - deleted: comb(explicit, deleted) * comb(known, shape.inserted - deleted) * omitted
            for deleted in range(max(0, shape.inserted - known), min(shape.inserted, explicit) + 1)
        }
    boundary = _group_boundary(immutable_length)
    target_groups = (target_length - boundary) // 4
    observed_groups = target_groups + shape.inserted - shape.omitted
    group_end = boundary + 4 * observed_groups
    if min(target_groups, observed_groups) < 0 or group_end > len(text): return {}
    group_explicit = tuple(
        sum(character.lower() not in CHARSET for character in text[start : start + 4])
        for start in range(boundary, group_end, 4)
    )
    outside = explicit - sum(group_explicit)
    counts: dict[int, int] = {}
    omitted = comb(target_groups, shape.omitted)
    for deleted in combinations(range(observed_groups), shape.inserted):
        remaining = outside + sum(count for index, count in enumerate(group_explicit)
                                  if index not in deleted)
        counts[remaining] = counts.get(remaining, 0) + omitted
    return counts
def _alignment_count(shape: _StructuralClass, observed_length: int, target_length: int,
                     immutable_length: int) -> int:
    return sum(_alignment_counts(shape, "q" * observed_length, target_length, immutable_length).values())
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
def _capacities(erasures: int, _degree: int) -> range:
    return range((8 - erasures) // 2 + 1) if erasures <= 8 else range(0)
@dataclass(frozen=True, slots=True)
class _Target:
    context: CorrectionContext
    text: str
    immutable: int
    target: int
    base: int
    degree: int
    counts: dict[_StructuralClass, dict[int, int]]
def _prepare(context: CorrectionContext, damaged_text: str,
             classes: Sequence[_StructuralClass]) -> _Target | None:
    normalized = _normalize(context, damaged_text)
    if normalized is None: return None
    text, immutable = normalized
    target = context.expected_length
    assert target is not None
    shapes = tuple(shape for shape in classes if shape.delta == len(text) - target)
    counts = {shape: {remaining: count for remaining, count in
                     _alignment_counts(shape, text, target, immutable).items() if count}
              for shape in shapes}
    base = len(context.profile.value) + 1
    degree = _checksum_for_encoded_length(context.profile.value, target - base).length
    return _Target(context, text, immutable, target, base, degree, counts)

def _layers(state: _Target) -> Iterator[tuple[int, int, tuple[int, _StructuralClass, int, int]]]:
    for shape, counts in state.counts.items():
        for remaining, alignments in counts.items():
            erasures = shape.erasures + remaining
            for substitutions in _capacities(erasures, state.degree):
                volume = alignments * _capture_volume(state.target - state.immutable, erasures,
                                                       substitutions)
                yield volume, 5 * state.degree, (state.target, shape, remaining, substitutions)
def _frontier(states: Sequence[_Target], primary: frozenset[int]
              ) -> dict[tuple[int, _StructuralClass, int, int], int]:
    layers = tuple(layer for state in states for layer in _layers(state))
    maximum = max((bits for _volume, bits, _key in layers), default=0)
    admitted: dict[tuple[int, _StructuralClass, int, int], int] = {}
    cumulative = 0
    def add(pool: Sequence[tuple[int, int, tuple[int, _StructuralClass, int, int]]]) -> None:
        nonlocal cumulative
        for _rank, grouped in groupby(sorted(pool, key=lambda item: item[0]), key=lambda item: item[0]):
            batch = tuple(grouped)
            increment = sum(volume << (maximum - bits) for volume, bits, _key in batch)
            if _FALSE_BOUND_DENOMINATOR * (cumulative + increment) >= 1 << maximum: break
            cumulative += increment
            admitted.update((key, volume) for volume, _bits, key in batch)
    add(tuple(layer for layer in layers if layer[2][0] in primary))
    add(tuple(layer for layer in layers if layer[2][0] not in primary))
    return admitted
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
    if len(damaged_text) > 2 * (target + 8): return None
    text = damaged_text.replace(" ", "")
    if len(text) > target + 8: return None
    try:
        _validate_single_case_ascii(text)
    except CodexError:
        return None
    prefix = context.immutable_prefix or f"{context.profile.value}1"
    matches = text.startswith(prefix) if context.immutable_prefix else text.lower().startswith(prefix)
    if not matches or not target - 8 <= len(text) <= target + 8: return None
    return text, len(prefix)
def _keep(results: dict[str, CorrectionCandidate], candidate: CorrectionCandidate) -> None:
    key = candidate.artifact.text.lower()
    current = results.get(key)
    rank = candidate.capture_volume, candidate.addend_hamming_weight
    if current is None or rank < (current.capture_volume, current.addend_hamming_weight): results[key] = candidate
def _search_target(state: _Target, frontier: dict[tuple[int, _StructuralClass, int, int], int],
                   results: dict[str, CorrectionCandidate], deadline: float | None) -> bool:
    context, text = state.context, state.text
    excluded = frozenset(CHARSET.index(value.lower()) for value in context.excluded_indices)
    if _FIXED in state.counts:
        fixed = _correct_fixed(text, suspected_profile=context.profile,
                               immutable_prefix=context.immutable_prefix)
        positions = tuple(index for index, character in enumerate(text[state.immutable:])
                          if character.lower() not in CHARSET)
        consecutive = not positions or positions == tuple(range(positions[0], positions[-1] + 1))
        if fixed is not None and _allowed(context, fixed):
            substitutions = sum(edit.kind == "substitution" for edit in fixed.edits)
            key = (state.target, _FIXED, fixed.erasures_filled, substitutions)
            if key in frontier or 8 < fixed.erasures_filled <= state.degree and consecutive:
                _keep(results, fixed)
    entries = {shape: tuple((remaining, substitutions, volume) for
               (target, active, remaining, substitutions), volume in frontier.items()
               if target == state.target and active == shape)
               for shape in state.counts if shape != _FIXED}
    structural = [shape for shape, values in entries.items() if values]
    floors = {shape: min(value[2] for value in entries[shape]) for shape in structural}
    structural.sort(key=lambda shape: (floors[shape], shape.unit, shape.inserted))
    solvers: dict[int, _FixedCorrector] = {}
    for shape in structural:
        best = min((item.capture_volume for item in results.values()), default=None)
        if best is not None and floors[shape] > best: continue
        if deadline is not None and monotonic() >= deadline: return False
        limits = {
            remaining: max(substitution for active, substitution, _volume in entries[shape]
                           if active == remaining)
            for remaining in state.counts[shape]
            if any(active == remaining for active, _substitution, _volume in entries[shape])}
        for variant in _variants(text, state.target, shape, state.immutable, state.base):
            remaining = len(variant.unknowns)
            limit = limits.get(remaining, -1)
            if _required_header_substitutions(variant.symbols, excluded) > limit: continue
            solver = solvers.setdefault(limit, _FixedCorrector(
                context.profile, state.target - state.base, text.isupper(), limit,
                state.immutable - state.base))
            fixed = solver.correct(variant.symbols, variant.unknowns, variant.erasure_indices)
            if fixed is None or not _allowed(context, fixed): continue
            substitutions = sum(edit.kind == "substitution" for edit in fixed.edits)
            key = (state.target, shape, remaining, substitutions)
            if key not in frontier: continue
            candidate = _adapt(fixed, variant, state.counts[shape][remaining], len(text), state.target)
            if candidate.capture_volume == frontier[key]:
                _keep(results, candidate)
    return True
def _search_many(contexts: Sequence[CorrectionContext], damaged_text: str, *,
                 primary: frozenset[int], reduced: frozenset[int] = frozenset(),
                 deadline: float | None = None) -> tuple[tuple[CorrectionCandidate, ...], bool]:
    states = tuple(state for context in contexts if (state := _prepare(
        context, damaged_text, _REDUCED_CLASSES if context.expected_length in reduced else _CLASSES))
        is not None)
    frontier = _frontier(states, primary)
    results: dict[str, CorrectionCandidate] = {}
    for state in states:
        target_layers = [volume for (target, _shape, _remaining, _substitutions), volume
                         in frontier.items() if target == state.target]
        positions = tuple(i for i, char in enumerate(state.text[state.immutable:]) if char.lower() not in CHARSET)
        burst = (_FIXED in state.counts and 8 < len(positions) <= state.degree and positions == tuple(range(positions[0], positions[-1] + 1)))
        if not target_layers and not burst: continue
        best = min((item.capture_volume for item in results.values()), default=None)
        if best is not None and target_layers and min(target_layers) > best and not burst:
            continue
        if not _search_target(state, frontier, results, deadline):
            return _primary(tuple(results.values())), False
    return _primary(tuple(results.values())), True
def _consecutive_witnesses(contexts: Sequence[CorrectionContext], damaged_text: str, *,
                           reduced: frozenset[int] = frozenset(), deadline: float | None = None
                           ) -> tuple[frozenset[str], bool]:
    results: set[str] = set()
    for context in contexts:
        classes = _REDUCED_CLASSES if context.expected_length in reduced else _CLASSES
        state = _prepare(context, damaged_text, classes)
        if state is None: continue
        shapes = tuple(shape for shape in state.counts if not shape.erasures)
        solver = _FixedCorrector(context.profile, state.target - state.base, state.text.isupper(),
                                 None, state.immutable - state.base)
        for shape in shapes:
            if deadline is not None and monotonic() >= deadline: return frozenset(results), False
            variants = _variants(state.text, state.target, shape, state.immutable, state.base)
            for variant in variants:
                positions = variant.erasure_indices
                consecutive = positions and positions == tuple(range(positions[0], positions[-1] + 1))
                if not 8 < len(positions) <= state.degree or not consecutive: continue
                fixed = solver.correct(variant.symbols, variant.unknowns, positions)
                if fixed is not None and _allowed(context, fixed):
                    results.add(fixed.artifact.text.lower())
                    if len(results) > 1:
                        return frozenset(results), True
    return frozenset(results), True
