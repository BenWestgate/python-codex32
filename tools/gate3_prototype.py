"""Bounded Gate 3 alignment prototype and benchmark harness."""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable, Iterator
from itertools import combinations
from time import perf_counter

from codex32.correction import _correct_fixed
from codex32.profiles import Profile
from tools.gate3_capture import Shape, supported_shapes


def _unique(values: Iterable[str]) -> Iterator[str]:
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            yield value


def _delete(text: str, count: int, burst: bool) -> Iterator[str]:
    if not count:
        yield text
        return
    selections: Iterable[tuple[int, ...]]
    if burst:
        selections = (tuple(range(start, start + count)) for start in range(len(text) - count + 1))
    else:
        selections = combinations(range(len(text)), count)
    yield from _unique(
        "".join(character for index, character in enumerate(text) if index not in selected)
        for selected in selections
    )


def _insert_erasures(text: str, count: int, burst: bool) -> Iterator[str]:
    if not count:
        yield text
        return
    target_length = len(text) + count
    if burst:
        for start in range(len(text) + 1):
            yield text[:start] + "?" * count + text[start:]
        return
    yield from _unique(
        _merge_erasures(text, frozenset(selected)) for selected in combinations(range(target_length), count)
    )


def _merge_erasures(text: str, selected: frozenset[int]) -> str:
    source = iter(text)
    return "".join("?" if index in selected else next(source) for index in range(len(text) + len(selected)))


def _character_candidates(text: str, prefix: str, shape: Shape) -> Iterator[str]:
    body = text[len(prefix) :]
    yield from (
        text[: len(prefix)] + candidate
        for reduced in _delete(body, shape.inserted, shape.burst)
        for candidate in _insert_erasures(reduced, shape.omitted, shape.burst)
    )


def _group_candidates(text: str, prefix: str, target_length: int, shape: Shape) -> Iterator[str]:
    groups = text.split()
    if not groups or not groups[0].lower().startswith(prefix) or any(len(group) > 4 for group in groups):
        return
    tail = groups[-1] if len(groups[-1]) < 4 else ""
    full = groups[1:-1] if tail else groups[1:]
    inserted = shape.inserted // 4
    omitted = shape.omitted // 4
    selections: Iterable[tuple[int, ...]]
    if shape.burst and inserted:
        selections = (tuple(range(start, start + inserted)) for start in range(len(full) - inserted + 1))
    else:
        selections = combinations(range(len(full)), inserted)
    target_full = sum(start >= len(prefix) for start in range(0, target_length - 3, 4))
    for selected in selections:
        reduced = [group for index, group in enumerate(full) if index not in selected]
        if len(reduced) + omitted != target_full:
            continue
        if shape.burst and omitted:
            placements = (tuple(range(start, start + omitted)) for start in range(len(reduced) + 1))
        else:
            placements = combinations(range(target_full), omitted)
        for placement in placements:
            iterator = iter(reduced)
            restored = ["????" if index in placement else next(iterator) for index in range(target_full)]
            yield groups[0] + "".join(restored) + tail


def candidates(text: str, profile: Profile, target_length: int, shape: Shape) -> Iterator[str]:
    prefix = f"{profile.value}1"
    normalized = "".join(text.split())
    if len(normalized) - target_length != shape.delta:
        return
    values = (
        _group_candidates(text, prefix, target_length, shape)
        if shape.grouped
        else _character_candidates(normalized, prefix, shape)
    )
    yield from _unique(values)


def benchmark(text: str, profile: Profile, target_length: int, shape: Shape) -> dict[str, object]:
    started = perf_counter()
    checked = 0
    results: set[str] = set()
    for candidate in candidates(text, profile, target_length, shape):
        checked += 1
        result = _correct_fixed(candidate, suspected_profile=profile)
        if result is not None:
            results.add(result.artifact.text)
    elapsed = perf_counter() - started
    return {
        "shape": shape.name,
        "checked": checked,
        "results": sorted(results),
        "seconds": elapsed,
        "candidates_per_second": checked / elapsed if elapsed else 0.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("shape", choices=tuple(shape.name for shape in supported_shapes()))
    parser.add_argument("text")
    parser.add_argument("--profile", type=Profile, default=Profile.MS)
    parser.add_argument("--length", type=int, required=True)
    arguments = parser.parse_args()
    shape = next(item for item in supported_shapes() if item.name == arguments.shape)
    print(json.dumps(benchmark(arguments.text, arguments.profile, arguments.length, shape), indent=2))


if __name__ == "__main__":
    main()
