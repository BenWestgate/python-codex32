"""Enumerate bounded alignments; correction.py performs every symbol repair."""

from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, replace
from itertools import combinations, groupby
from math import comb, factorial
from time import monotonic

from codex32._alignment import _IncrementalSyndromes, _View
from codex32.bech32 import CHARSET, _validate_single_case_ascii
from codex32.bip93 import _checksum_for_encoded_length
from codex32.correction import (
    CorrectionCandidate,
    CorrectionContext,
    CorrectionEdit,
    _allowed,
    _capture_mass,
    _capture_volume,
    _correct_fixed,
    _FixedCorrector,
    _primary,
)
from codex32.errors import CodexError

_FALSE_BOUND_DENOMINATOR = 1
_THRESHOLDS = frozenset(CHARSET.index(value) for value in "023456789")
_SECRET_INDEX = CHARSET.index("s")


@dataclass(frozen=True, slots=True)
class _StructuralClass:
    inserted: int
    omitted: int
    unit: int = 1
    adjacent: int = 0
    distant: int = 0
    corrupted: int = 0

    @property
    def distance(self) -> int:
        return self.inserted + self.omitted + self.adjacent + 2 * self.distant + self.corrupted

    @property
    def operations(self) -> tuple[str, ...]:
        return (
            ("I",) * self.inserted
            + ("O",) * self.omitted
            + ("AT",) * self.adjacent
            + ("T",) * self.distant
            + ("GS",) * self.corrupted
        )

    @property
    def delta(self) -> int:
        return self.unit * (self.inserted - self.omitted)

    @property
    def erasures(self) -> int:
        return self.unit * (self.omitted + self.corrupted)


@dataclass(frozen=True, slots=True)
class _Variant:
    symbols: tuple[int, ...]
    missing: frozenset[int]
    deleted: tuple[tuple[int, str], ...]
    unknowns: tuple[tuple[int, str], ...]
    erasure_indices: tuple[int, ...]


_FIXED = _StructuralClass(0, 0)


def _classes(unit: int, depth: int) -> tuple[_StructuralClass, ...]:
    return tuple(
        shape
        for inserted in range(depth + 1)
        for omitted in range(depth + 1)
        for adjacent in range(depth + 1)
        for distant in range(depth // 2 + 1)
        for corrupted in range(depth + 1 if unit == 4 else 1)
        if 0
        < (shape := _StructuralClass(inserted, omitted, unit, adjacent, distant, corrupted)).distance
        <= depth
    )


_CHARACTER_CLASSES = _classes(1, 4)
_GROUP_CLASSES = _classes(4, 2)
_CLASSES = (_FIXED, *_CHARACTER_CLASSES, *_GROUP_CLASSES)
# Compatibility for older offline tools; public search uses the full class set.
_REDUCED_CLASSES = tuple(shape for shape in _CLASSES if shape.unit == 4 or shape.distance <= 3)


def _group_boundary(immutable_length: int) -> int:
    return 4 * ((immutable_length + 3) // 4)


def _alignment_counts(
    shape: _StructuralClass, text: str, target_length: int, immutable_length: int
) -> dict[int, int]:
    explicit = sum(character.lower() not in CHARSET for character in text[immutable_length:])
    if shape == _FIXED:
        return {explicit: 1}
    if shape.adjacent or shape.distant or shape.corrupted:
        # Every ordered script is charged, including overlaps and duplicate results.
        # The largest intermediate domain bounds every operation's choices.
        width = shape.unit
        boundary = immutable_length if width == 1 else _group_boundary(immutable_length)
        units = max(0, (len(text) - boundary) // width) + shape.omitted
        choices = {
            "I": units,
            "O": units + 1,
            "AT": max(0, units - 1),
            "T": max(0, (units - 1) * (units - 2) // 2),
            "GS": units,
        }
        scripts = factorial(len(shape.operations))
        for operation in set(shape.operations):
            count = shape.operations.count(operation)
            scripts = scripts // factorial(count)
        for operation in shape.operations:
            scripts *= choices[operation]
        # Erasures can be moved, deleted, or overlap a corrupted group. Each
        # attainable total is conservatively charged the entire script bound.
        minimum = max(
            0, max(explicit + width * shape.omitted, width if shape.corrupted else 0) - width * shape.inserted
        )
        maximum = min(8, explicit + shape.erasures)
        return {total - shape.erasures: scripts for total in range(minimum, maximum + 1)}

    if shape.unit == 1:
        observed, target = (
            len(text) - immutable_length,
            target_length - immutable_length,
        )
        if min(observed, target) < 0:
            return {}
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
    if min(target_groups, observed_groups) < 0 or group_end > len(text):
        return {}
    group_explicit = tuple(
        sum(character.lower() not in CHARSET for character in text[start : start + 4])
        for start in range(boundary, group_end, 4)
    )
    outside = explicit - sum(group_explicit)
    counts: dict[int, int] = {}
    omitted = comb(target_groups, shape.omitted)
    for deleted in combinations(range(observed_groups), shape.inserted):
        remaining = outside + sum(count for index, count in enumerate(group_explicit) if index not in deleted)
        counts[remaining] = counts.get(remaining, 0) + omitted
    return counts


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


def _views(text: str, target: int, shape: _StructuralClass, immutable: int, base: int) -> Iterator[_View]:
    source = tuple(CHARSET.find(char.lower()) for char in text[base:])
    initial = _View(source, ((0, len(source)),), len(source))
    boundary = (immutable if shape.unit == 1 else _group_boundary(immutable)) - base
    width = shape.unit
    if not (shape.adjacent or shape.distant or shape.corrupted):
        observed_units = (len(source) - boundary) // width
        target_units = (target - base - boundary) // width
        for deleted in combinations(range(observed_units), shape.inserted):
            # Canonical deletion within a run of equal units; no retained-body allocation.
            if any(
                i
                and i - 1 not in deleted
                and source[boundary + width * (i - 1) : boundary + width * i]
                == source[boundary + width * i : boundary + width * (i + 1)]
                for i in deleted
            ):
                continue
            reduced = initial
            for index in reversed(deleted):
                reduced = reduced.splice(boundary + width * index, width, 0)
            for omitted in combinations(range(target_units), shape.omitted):
                view = reduced
                for index in omitted:
                    view = view.splice(boundary + width * index, 0, width)
                yield view
        return

    def walk(view: _View, operations: tuple[str, ...]) -> Iterator[_View]:
        if not operations:
            yield view
            return
        units = (len(view) - boundary) // width
        for operation in dict.fromkeys(operations):
            index = operations.index(operation)
            rest = operations[:index] + operations[index + 1 :]
            if operation in ("I", "O", "GS"):
                for unit in range(units + (operation == "O")):
                    position = boundary + width * unit
                    yield from walk(
                        view.mask(position, width)
                        if operation == "GS"
                        else view.splice(
                            position, 0 if operation == "O" else width, 0 if operation == "I" else width
                        ),
                        rest,
                    )
            else:
                for left in range(units):
                    rights = (
                        range(left + 1, min(left + 2, units)) if operation == "AT" else range(left + 2, units)
                    )
                    for right in rights:
                        p, q = boundary + width * left, boundary + width * right
                        if all(view[p + i] == view[q + i] for i in range(width)):
                            continue
                        yield from walk(
                            view.swap(boundary + width * left, boundary + width * right, width), rest
                        )

    yield from walk(initial, shape.operations)


def _view_variant(view: _View, text: str, base: int) -> _Variant:
    """Materialize edit diagnostics only after a BCH hypothesis survives."""
    explicit = tuple(i for i, value in enumerate(view.source) if value < 0)
    unknown = tuple(view.unknown_positions(explicit))
    kept = {i for start, size in view.spans if start >= 0 for i in range(start, start + size)}
    return _Variant(
        tuple(view),
        frozenset(base + p for p, source in unknown if source < 0),
        tuple((base + i, text[base + i]) for i in range(len(view.source)) if i not in kept),
        tuple((p, text[base + source]) for p, source in unknown if source >= 0),
        tuple(sorted(len(view) - p - 1 for p, _ in unknown)),
    )


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


def _prepare(
    context: CorrectionContext, damaged_text: str, classes: Sequence[_StructuralClass]
) -> _Target | None:
    normalized = _normalize(context, damaged_text)
    if normalized is None:
        return None
    text, immutable = normalized
    target = context.expected_length
    assert target is not None
    shapes = tuple(shape for shape in classes if shape.delta == len(text) - target)
    counts = {
        shape: {
            remaining: count
            for remaining, count in _alignment_counts(shape, text, target, immutable).items()
            if count
        }
        for shape in shapes
    }
    base = len(context.hrp) + 1
    degree = _checksum_for_encoded_length(context.hrp, target - base).length
    return _Target(context, text, immutable, target, base, degree, counts)


def _layers(
    state: _Target,
) -> Iterator[tuple[int, int, tuple[int, _StructuralClass, int, int]]]:
    for shape, counts in state.counts.items():
        for remaining, alignments in counts.items():
            erasures = shape.erasures + remaining
            capacities = _capacities(erasures, state.degree)
            if shape == _FIXED and 8 < erasures <= state.degree:
                positions = tuple(
                    i for i, c in enumerate(state.text[state.immutable :]) if c.lower() not in CHARSET
                )
                if positions == tuple(range(positions[0], positions[-1] + 1)):
                    capacities = range(1)
            for substitutions in capacities:
                volume = alignments * _capture_volume(state.target - state.immutable, erasures, substitutions)
                yield (
                    volume,
                    5 * state.degree,
                    (
                        state.target,
                        shape,
                        remaining,
                        substitutions,
                    ),
                )


def _frontier(
    states: Sequence[_Target], primary: frozenset[int]
) -> dict[tuple[int, _StructuralClass, int, int], int]:
    layers = tuple(layer for state in states for layer in _layers(state))
    maximum = max((bits for _volume, bits, _key in layers), default=0)
    admitted: dict[tuple[int, _StructuralClass, int, int], int] = {}
    cumulative = 0

    def add(
        pool: Sequence[tuple[int, int, tuple[int, _StructuralClass, int, int]]],
    ) -> None:
        nonlocal cumulative
        for _rank, grouped in groupby(sorted(pool, key=lambda item: item[0]), key=lambda item: item[0]):
            batch = tuple(grouped)
            increment = sum(volume << (maximum - bits) for volume, bits, _key in batch)
            if _FALSE_BOUND_DENOMINATOR * (cumulative + increment) > 1 << maximum:
                break
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
    fixed: CorrectionCandidate,
    variant: _Variant,
    alignments: int,
    observed_length: int,
    target_length: int,
) -> CorrectionCandidate:
    missing_indices = frozenset(target_length - position - 1 for position in variant.missing)
    edits = tuple(
        (
            replace(edit, kind="insertion", observed="")
            if edit.kind == "erasure" and edit.reverse_index in missing_indices
            else edit
        )
        for edit in fixed.edits
    )
    edits += tuple(
        CorrectionEdit("deletion", observed_length - position - 1, character, "")
        for position, character in variant.deleted
    )
    return replace(
        fixed,
        edits=tuple(sorted(edits, key=lambda edit: edit.reverse_index)),
        capture_volume=alignments * fixed.capture_volume,
    )


def _normalize(context: CorrectionContext, damaged_text: str) -> tuple[str, int] | None:
    target = context.expected_length
    assert target is not None
    if len(damaged_text) > 2 * (target + 8):
        return None
    text = damaged_text.replace(" ", "")
    if len(text) > target + 8:
        return None
    try:
        _validate_single_case_ascii(text)
    except CodexError:
        return None
    prefix = context.immutable_prefix or f"{context.hrp}1"
    matches = text.startswith(prefix) if context.immutable_prefix else text.lower().startswith(prefix)
    if not matches or not target - 8 <= len(text) <= target + 8:
        return None
    return text, len(prefix)


def _keep(results: dict[str, CorrectionCandidate], candidate: CorrectionCandidate) -> None:
    key = candidate.artifact.text.lower()
    current = results.get(key)
    rank = candidate.capture_volume, candidate.addend_hamming_weight
    if current is None or rank < (
        current.capture_volume,
        current.addend_hamming_weight,
    ):
        results[key] = candidate


def _search_fixed(
    state: _Target,
    frontier: dict[tuple[int, _StructuralClass, int, int], int],
    results: dict[str, CorrectionCandidate],
    allowed: Callable[[CorrectionCandidate], bool] | None = None,
) -> CorrectionCandidate | None:
    fixed = _correct_fixed(
        state.text,
        suspected_profile=state.context.hrp,
        immutable_prefix=state.context.immutable_prefix,
    )
    if fixed is None or not _allowed(state.context, fixed) or allowed is not None and not allowed(fixed):
        return None
    substitutions = sum(edit.kind == "substitution" for edit in fixed.edits)
    if (state.target, _FIXED, fixed.erasures_filled, substitutions) in frontier:
        _keep(results, fixed)
    # Retain the witness even if its fixed explanation was not admitted: a
    # cheaper structural explanation may still qualify under the same ledger.
    return fixed


def _search_target(
    state: _Target,
    frontier: dict[tuple[int, _StructuralClass, int, int], int],
    results: dict[str, CorrectionCandidate],
    deadline: float | None,
    *,
    allowed: Callable[[CorrectionCandidate], bool] | None = None,
    views: Iterator[_View] | None = None,
) -> bool:
    context, text = state.context, state.text
    excluded = frozenset(CHARSET.index(value.lower()) for value in context.excluded_indices)
    if _FIXED in state.counts:
        _search_fixed(state, frontier, results, allowed)
    layers = sorted(
        (
            (volume, shape, remaining, substitutions)
            for (target, shape, remaining, substitutions), volume in frontier.items()
            if target == state.target and shape in state.counts and shape != _FIXED
        ),
        key=lambda layer: layer[0],
    )
    solvers: dict[int, _FixedCorrector] = {}
    source = tuple(CHARSET.find(char.lower()) for char in text[state.base :])
    explicit = tuple(i for i, value in enumerate(source) if value < 0)
    incremental: _IncrementalSyndromes | None = None
    for volume, shape, active_remaining, limit in layers:
        best = min((item.capture_volume for item in results.values()), default=None)
        if best is not None and volume > best:
            break
        if deadline is not None and monotonic() >= deadline:
            return False
        if limit not in solvers:
            solvers[limit] = _FixedCorrector(
                context.hrp,
                state.target - state.base,
                text.isupper(),
                limit,
                state.immutable - state.base,
            )
        solver = solvers[limit]
        if incremental is None:
            incremental = _IncrementalSyndromes(solver.alignment, source)
        alignments = (
            _views(text, state.target, shape, state.immutable, state.base) if views is None else views
        )
        for number, view in enumerate(alignments):
            if number % 32 == 0 and deadline is not None and monotonic() >= deadline:
                return False
            unknown = tuple(view.unknown_positions(explicit))
            remaining = len(unknown) - shape.erasures
            if remaining != active_remaining or _required_header_substitutions(view, excluded) > limit:
                continue
            erasures = tuple(sorted(len(view) - p - 1 for p, _ in unknown))
            fixed = solver.correct(
                view,
                tuple((p, text[state.base + source]) for p, source in unknown if source >= 0),
                erasures,
                incremental.packed(view),
            )
            if fixed is None or not _allowed(context, fixed) or allowed is not None and not allowed(fixed):
                continue
            substitutions = sum(edit.kind == "substitution" for edit in fixed.edits)
            key = (state.target, shape, remaining, substitutions)
            if substitutions != limit:
                continue
            candidate = _adapt(
                fixed,
                _view_variant(view, text, state.base),
                state.counts[shape][remaining],
                len(text),
                state.target,
            )
            if shape.adjacent or shape.distant:
                # Compare retained source order, excluding shifts caused by indels.
                ordered = iter(
                    sorted(i for start, size in view.spans if start >= 0 for i in range(start, start + size))
                )
                offset = 0
                moved: list[CorrectionEdit] = []
                for source_position, size in view.spans:
                    if source_position >= 0:
                        for i in range(size):
                            observed_position = next(ordered)
                            if source_position + i != observed_position:
                                moved.append(
                                    CorrectionEdit(
                                        "transposition",
                                        len(view) - offset - i - 1,
                                        text[state.base + observed_position],
                                        candidate.artifact.text[state.base + offset + i],
                                    )
                                )
                    offset += size
                candidate = replace(candidate, edits=candidate.edits + tuple(moved))
            if candidate.capture_volume == frontier[key]:
                _keep(results, candidate)
    return True


def _search_many(
    contexts: Sequence[CorrectionContext],
    damaged_text: str,
    *,
    primary: frozenset[int],
    reduced: frozenset[int] = frozenset(),
    deadline: float | None = None,
    max_character_depth: int = 4,
    competitors: bool = False,
    allowed: Callable[[CorrectionCandidate], bool] | None = None,
    capture_layers: list[tuple[int, int]] | None = None,
) -> tuple[tuple[CorrectionCandidate, ...], bool]:
    deadline = monotonic() + 10 if deadline is None else deadline
    states = tuple(
        state
        for context in contexts
        if (
            state := _prepare(
                context,
                damaged_text,
                _CLASSES,
            )
        )
        is not None
    )
    frontier = _frontier(states, primary)
    layers_accounted = [] if capture_layers is None else capture_layers
    widths = {state.target: 5 * state.degree for state in states}
    layers_accounted.extend((volume, widths[key[0]]) for key, volume in frontier.items())

    def finish(
        candidates: tuple[CorrectionCandidate, ...], complete: bool
    ) -> tuple[tuple[CorrectionCandidate, ...], bool]:
        annotated = []
        for candidate in candidates:
            volume, bits = _capture_mass(layers_accounted, candidate.capture_volume)
            annotated.append(replace(candidate, cumulative_capture_volume=volume, capture_space_bits=bits))
        return tuple(annotated), complete

    if competitors:
        from codex32._competitors import _search_competitors

        return finish(*_search_competitors(states, frontier, deadline, allowed))
    results: dict[str, CorrectionCandidate] = {}
    # One global admission ledger, then fixed, required, and optional work.
    # The minimum supported public sphere is A<=2 / G<=2; deeper cutoffs
    # require completed worst-case public-profile benchmark evidence.
    for phase in (0, 1, 2):
        for original in states:
            counts = {
                shape: values
                for shape, values in original.counts.items()
                if (shape.unit == 4 or shape.distance <= max_character_depth)
                and (0 if shape == _FIXED else 1 if shape.unit == 4 or shape.distance <= 2 else 2) == phase
            }
            if not counts:
                continue
            layers = [
                volume
                for (target, shape, _remaining, _substitutions), volume in frontier.items()
                if target == original.target and shape in counts
            ]
            best = min((c.capture_volume for c in results.values()), default=None)
            if not layers or best is not None and min(layers) > best:
                continue
            state = replace(original, counts=counts)
            if not _search_target(state, frontier, results, deadline):
                candidates = _primary(tuple(results.values()))
                if phase < 2 or len(candidates) != 1:
                    return (), False
                return finish((replace(candidates[0], search_complete=False),), False)
    return finish(_primary(tuple(results.values())), True)
