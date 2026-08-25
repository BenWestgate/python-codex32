"""Measure the complete production Gate 3 search without candidate shortcuts."""

from __future__ import annotations

import argparse
import json
import platform
import tracemalloc
from random import Random
from time import perf_counter

from codex32.bech32 import CHARSET
from codex32.correction import CorrectionContext
from codex32.indel import (
    _CHARACTER_CLASSES,
    _alignment_count,
    _required_header_substitutions,
    _search,
    _variants,
)
from codex32.profiles import Profile

DELTAS = (-8, -4, -3, -2, -1, 0, 1, 2, 3, 4, 8)


def _damaged_text(length: int, immutable_prefix: str, delta: int) -> str:
    random = Random(0)
    return immutable_prefix + "".join(
        random.choice(CHARSET) for _ in range(length + delta - len(immutable_prefix))
    )


def _mixed_counts(
    context: CorrectionContext,
    text: str,
) -> dict[str, int | float]:
    shape = next(item for item in _CHARACTER_CLASSES if (item.inserted, item.omitted) == (2, 2))
    target = context.expected_length or 0
    immutable = len(context.immutable_prefix or "ms1")
    started = perf_counter()
    generated = fixed_calls = 0
    for variant in _variants(text, target, shape, immutable, 3):
        generated += 1
        fixed_calls += _required_header_substitutions(variant.symbols, frozenset()) <= 1
    seconds = perf_counter() - started
    raw = _alignment_count(shape, len(text), target, immutable)
    return {
        "raw_alignments": raw,
        "generated_alignments": generated,
        "deduplicated_alignments": raw - generated,
        "header_pruned": generated - fixed_calls,
        "fixed_correction_calls": fixed_calls,
        "generation_seconds": seconds,
        "generated_per_second": generated / seconds,
    }


def benchmark(
    length: int,
    immutable_prefix: str,
    *,
    delta: int,
    memory: bool,
) -> dict[str, object]:
    context = CorrectionContext(Profile.MS, length, immutable_prefix)
    damaged = _damaged_text(length, immutable_prefix, delta)
    counts = _mixed_counts(context, damaged) if delta == 0 else {}
    if memory:
        tracemalloc.start()
    started = perf_counter()
    candidates, complete = _search(context, damaged, deadline=None)
    seconds = perf_counter() - started
    peak = tracemalloc.get_traced_memory()[1] if memory else None
    if memory:
        tracemalloc.stop()
    if not complete or candidates:
        raise RuntimeError("benchmark workload did not complete without candidates")
    fixed_calls = int(counts.get("fixed_correction_calls", 0))
    return {
        "system": platform.platform(),
        "python": platform.python_version(),
        "length": length,
        "delta": delta,
        "immutable_prefix": immutable_prefix,
        **counts,
        "complete_search_seconds": seconds,
        "fixed_calls_per_second": fixed_calls / seconds if fixed_calls else None,
        "peak_traced_bytes": peak,
        "complete": complete,
        "result_count": len(candidates),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--length", type=int, default=48)
    parser.add_argument("--immutable-prefix", default="ms1")
    parser.add_argument("--delta", type=int, choices=DELTAS, default=0)
    parser.add_argument("--all-deltas", action="store_true")
    parser.add_argument("--memory", action="store_true")
    arguments = parser.parse_args()
    deltas = DELTAS if arguments.all_deltas else (arguments.delta,)
    print(
        json.dumps(
            [
                benchmark(
                    arguments.length,
                    arguments.immutable_prefix,
                    delta=delta,
                    memory=arguments.memory,
                )
                for delta in deltas
            ],
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
