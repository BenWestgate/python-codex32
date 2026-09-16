"""CLI scheduling and conservative proofs that preserve candidate ranking."""

from collections import Counter
from collections.abc import Callable, Iterator, Sequence
from dataclasses import replace
from time import monotonic

from codex32._alignment import _View
from codex32.bech32 import CHARSET
from codex32.correction import CorrectionCandidate, _primary
from codex32.indel import _FIXED, _search_fixed, _search_target, _StructuralClass, _Target

_Layer = tuple[int, _StructuralClass, int, int]


class _Expired(Exception):
    pass


def _check_deadline(deadline: float) -> None:
    if monotonic() >= deadline:
        raise _Expired


def _tier(shape: _StructuralClass) -> int:
    if len(shape.operations) == 1:
        return 0
    return 1 if shape.inserted == shape.omitted == 1 and len(shape.operations) == 2 else 2


def _covered_candidates(
    state: _Target,
    shape: _StructuralClass,
    erasures: int,
    substitutions: int,
    fixed: CorrectionCandidate | None,
    results: Sequence[CorrectionCandidate],
) -> tuple[CorrectionCandidate, ...] | None:
    """None means discovery is needed; a tuple contains every possible survivor."""
    if len(state.text) != state.target:
        return None
    observed = state.text[state.immutable :].lower()
    explicit = sum(c not in CHARSET for c in observed)
    # With no surviving unknowns, the inserted slot must be removed again.
    # Adjacent swaps can move it only locally; each affects at most two
    # original positions. A distant swap could instead relocate a character.
    if (shape.inserted or shape.omitted) and not (
        shape.unit == 1
        and shape.inserted == shape.omitted == 1
        and not shape.distant
        and erasures == explicit == 0
    ):
        return None
    changed = shape.unit * (2 * (shape.adjacent + shape.distant) + shape.corrupted) + substitutions
    if explicit + 2 * changed <= 8:
        # Fixed BCH was completed first, including a failed/ineligible result.
        return () if fixed is None else (fixed,)
    for candidate in results:
        if candidate.artifact.hrp != state.context.hrp or len(candidate.artifact.text) != state.target:
            continue
        known_distance = sum(
            a in CHARSET and a != b
            for a, b in zip(observed, candidate.artifact.text[state.immutable :].lower())
        )
        if explicit + known_distance + changed < 9:
            return (candidate,)
    return None


def _known_swaps(
    state: _Target,
    shape: _StructuralClass,
    substitutions: int,
    candidate: CorrectionCandidate,
    deadline: float,
) -> Iterator[_View]:
    """Enumerate only swap scripts that could explain this known artifact."""
    source = tuple(CHARSET.index(c.lower()) for c in state.text[state.base :])
    target = tuple(CHARSET.index(c.lower()) for c in candidate.artifact.text[state.base :])
    boundary = state.immutable - state.base
    initial = _View(source, ((0, len(source)),), len(source))
    seen: set[tuple[tuple[int, ...], tuple[str, ...]]] = set()

    def walk(
        view: _View, values: tuple[int, ...], operations: tuple[str, ...], distance: int
    ) -> Iterator[_View]:
        _check_deadline(deadline)
        if distance > 2 * len(operations) + substitutions:
            return
        key = values, operations
        if key in seen:
            return
        if len(seen) < 4096:
            seen.add(key)
        if not operations:
            if distance == substitutions:
                yield view
            return
        for operation in dict.fromkeys(operations):
            index = operations.index(operation)
            rest = operations[:index] + operations[index + 1 :]
            for left in range(boundary, len(values)):
                _check_deadline(deadline)
                rights = (
                    range(left + 1, min(left + 2, len(values)))
                    if operation == "AT"
                    else range(left + 2, len(values))
                )
                for right in rights:
                    if values[left] == values[right]:
                        continue
                    changed = distance - (values[left] != target[left]) - (values[right] != target[right])
                    changed += (values[right] != target[left]) + (values[left] != target[right])
                    if changed > 2 * len(rest) + substitutions:
                        continue
                    swapped = list(values)
                    swapped[left], swapped[right] = swapped[right], swapped[left]
                    yield from walk(view.swap(left, right, 1), tuple(swapped), rest, changed)

    yield from walk(initial, source, shape.operations, sum(a != b for a, b in zip(source, target)))


def _competitor_views(
    state: _Target,
    key: _Layer,
    fixed: CorrectionCandidate | None,
    results: Sequence[CorrectionCandidate],
    deadline: float,
) -> Iterator[_View] | None:
    _, shape, remaining, substitutions = key
    erasures = shape.erasures + remaining
    covered = _covered_candidates(state, shape, erasures, substitutions, fixed, results)
    if covered is None:
        return None
    if not covered:
        return iter(())
    candidate = covered[0]
    distance = sum(
        a in CHARSET and a != b
        for a, b in zip(
            state.text[state.immutable :].lower(), candidate.artifact.text[state.immutable :].lower()
        )
    )
    if distance > shape.unit * (2 * (shape.adjacent + shape.distant) + shape.corrupted) + substitutions:
        return iter(())
    if not shape.corrupted:
        observed = Counter(c for c in state.text[state.immutable :].lower() if c in CHARSET)
        target = Counter(candidate.artifact.text[state.immutable :].lower())
        if sum((observed - target).values()) > substitutions:
            return iter(())
    if shape.unit == 1 and not (shape.inserted or shape.omitted) and erasures == 0:
        return _known_swaps(state, shape, substitutions, candidate, deadline)
    # Discovery coverage alone is insufficient: retain scoring work when its
    # effect on the known candidate's volume/Hamming rank is not yet established.
    return None


def _duplicate_layer(key: _Layer, completed: set[_Layer]) -> bool:
    target, shape, remaining, substitutions = key
    erasures = shape.erasures + remaining
    if shape.unit == 4 and shape.corrupted == 2 and erasures < 8:
        # Two different groups would mask at least eight positions.
        simpler = replace(shape, corrupted=1)
    elif shape.unit == 4 and shape.corrupted == shape.inserted == 1 and erasures == 0:
        simpler = replace(shape, corrupted=0)
    else:
        return False
    return (target, simpler, erasures - simpler.erasures, substitutions) in completed


def _search_competitors(
    states: Sequence[_Target],
    frontier: dict[_Layer, int],
    deadline: float,
    allowed: Callable[[CorrectionCandidate], bool] | None,
) -> tuple[tuple[CorrectionCandidate, ...], bool]:
    results: dict[str, CorrectionCandidate] = {}
    fixed: dict[int, CorrectionCandidate | None] = {}
    completed: set[_Layer] = set()
    try:
        for state in states:
            if _FIXED in state.counts:
                _check_deadline(deadline)
                fixed[state.target] = _search_fixed(state, frontier, results, allowed)
        targets = {state.target: state for state in states}
        layers = sorted(
            (key for key in frontier if key[1] != _FIXED),
            key=lambda key: (_tier(key[1]), frontier[key]),
        )
        for key in layers:
            volume = frontier[key]
            if results and volume > min(c.capture_volume for c in results.values()):
                continue
            _check_deadline(deadline)
            if _duplicate_layer(key, completed):
                continue
            target, shape, _, _ = key
            state = targets[target]
            views = _competitor_views(state, key, fixed.get(target), tuple(results.values()), deadline)
            if not _search_target(
                replace(state, counts={shape: state.counts[shape]}),
                {key: volume},
                results,
                deadline,
                allowed=allowed,
                views=views,
            ):
                raise _Expired
            completed.add(key)
    except _Expired:
        candidates = _primary(tuple(results.values()))
        return ((replace(candidates[0], search_complete=False),) if len(candidates) == 1 else ()), False
    return _primary(tuple(results.values())), True
