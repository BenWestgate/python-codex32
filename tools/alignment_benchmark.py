"""Separate synthetic BCH-body measurements from valid public-profile depth evidence.

Run --public for end-to-end cutoff evidence, or --kernel for synthetic body
lengths 40/66/93/127/1015/1023. A truncated row is never guarantee evidence.
Timing and traced-memory runs are separate because tracing changes throughput.
"""

from __future__ import annotations

import argparse
import json
import platform
import tracemalloc
from itertools import islice
from random import Random
from time import monotonic, perf_counter

from codex32._alignment import _IncrementalSyndromes
from codex32.bech32 import CHARSET, bech32_hrp_expand
from codex32.bip93 import checksum_for_encoded_length
from codex32.correction import (
    _LONG_SPEC,
    _SHORT_SPEC,
    CorrectionContext,
    _bch_syndrome_corrections,
    _gf1024_mul,
    _horner,
    _syndrome_alignment,
    _validate_context,
    _word_roots,
)
from codex32.indel import _CLASSES, _FIXED, _alignment_counts, _frontier, _prepare, _search_many, _views
from codex32.profiles import Profile

BODY_LENGTHS = (40, 66, 93, 127, 1015, 1023)
PUBLIC_LENGTHS = {
    Profile.MS: (48, 54, 61, 67, 74, 127),
    Profile.CL: (74,),
    Profile.BIP39_12W: (56,),
    Profile.BIP39_24W: (82,),
}
DELTAS = (-8, -4, -3, -2, -1, 0, 1, 2, 3, 4, 8)


def public_case(
    profile: Profile,
    displayed: int,
    depth: int,
    unknown: bool,
    delta: int,
    erasures: int,
    frozen: bool,
    seconds: float,
    memory: bool = False,
) -> dict[str, object]:
    hrp = profile.value
    prefix = hrp + "1" + ("2test" if frozen else "")
    random = Random(9001)
    text = hrp + "1" + "".join(random.choice(CHARSET) for _ in range(displayed + delta - len(hrp + "1")))
    # Spread erasures to avoid measuring only the consecutive-erasure shortcut.
    chars = list(text)
    # Keep the unfrozen header valid too: random invalid thresholds would make
    # header pruning artificially improve worst-case no-candidate timings.
    chars[len(hrp + "1") : len(hrp + "1") + 5] = "2test"
    for i in range(erasures):
        chars[len(prefix) + i * (len(text) - len(prefix)) // erasures] = "?"
    text = "".join(chars)
    targets = PUBLIC_LENGTHS[profile] if unknown else (displayed,)
    contexts = tuple(
        CorrectionContext(profile, n, prefix)
        for n in targets
        if abs(n - len(text)) <= 4 or abs(n - len(text)) == 8
    )
    for context in contexts:
        _validate_context(context)
    primary = frozenset(targets)
    if memory:
        tracemalloc.start()
    states = tuple(state for context in contexts if (state := _prepare(context, text, _CLASSES)) is not None)
    frontier = _frontier(states, primary)
    bits = {state.target: state.degree * 5 for state in states}
    mass = sum(volume / 2 ** bits[key[0]] for key, volume in frontier.items())
    started = perf_counter()
    candidates, complete = _search_many(
        contexts, text, primary=primary, deadline=monotonic() + seconds, max_character_depth=depth
    )
    elapsed = perf_counter() - started
    peak = tracemalloc.get_traced_memory()[1] if memory else None
    if memory:
        tracemalloc.stop()
    body = displayed - len(hrp + "1")
    return {
        "kind": "public",
        "profile": hrp,
        "displayed_length": displayed,
        "body_length": body,
        "mutable_body_length": displayed - len(prefix),
        "observed_body_length": len(text) - len(hrp + "1"),
        "target_body_lengths": {str(c.expected_length): c.expected_length - len(hrp + "1") for c in contexts},
        "expanded_length": len(bech32_hrp_expand(hrp)) + body,
        "checksum_symbols": checksum_for_encoded_length(hrp, body).length,
        "unknown": unknown,
        "delta": delta,
        "explicit_erasures": erasures,
        "frozen_header": frozen,
        "character_depth": depth,
        "group_depth": 2,
        "seconds": elapsed,
        "complete": complete,
        "candidates": len(candidates),
        "no_candidate_workload": not candidates,
        "peak_traced_bytes": peak,
        "capture_mass_ceiling": 1,
        "admitted_mass": mass,
        "guarantee_evidence": not memory and complete and not candidates and elapsed < seconds * 0.8,
    }


def kernel_case(
    body: int, depth: int, unknown: bool, group: bool, samples: int, complete_groups: bool = False
) -> dict[str, object]:
    # Explicit synthetic kernel selection: body-period experiments may not form
    # a valid HRP-expanded application string and never select public cutoffs.
    spec = _SHORT_SPEC if body <= _SHORT_SPEC.period else _LONG_SPEC
    hrp = "ms"
    base = len(hrp + "1")
    random = Random(9001)
    source = tuple(random.randrange(32) for _ in range(body))
    text = hrp + "1" + "".join(CHARSET[v] for v in source)
    targets = (
        tuple(
            n
            for n in range(
                max(15, body - (8 if group else depth)),
                min(_LONG_SPEC.period, body + (8 if group else depth)) + 1,
            )
            if not group or (n - body) % 4 == 0
        )
        if unknown
        else (body,)
    )
    shapes = tuple(
        shape
        for shape in _CLASSES
        if shape != _FIXED and (shape.unit == 4 if group else shape.unit == 1 and shape.distance <= depth)
    )
    jobs = [(target, shape) for target in targets for shape in shapes if shape.delta == body - target]
    count = sum(sum(_alignment_counts(shape, text, target + base, base).values()) for target, shape in jobs)
    alignments = {
        n: _IncrementalSyndromes(_syndrome_alignment(_SHORT_SPEC if n <= 93 else _LONG_SPEC, hrp, n), source)
        for n in targets
    }
    structural_mass = sum(
        count * 32 ** (shape.erasures + remaining) / 2 ** (65 if target <= _SHORT_SPEC.period else 75)
        for target, shape in jobs
        for remaining, count in _alignment_counts(shape, text, target + base, base).items()
    )
    generation = syndrome = dedup = memory_peak = retained_allocations = 0.0
    generated = 0
    full_group_seconds = None
    if group and complete_groups:
        # Complete streaming structural/syndrome measurement; no retained sphere.
        started = perf_counter()
        for target, shape in jobs:
            iterator = _views(text, target + base, shape, base, base)
            while True:
                t = perf_counter()
                views = tuple(islice(iterator, 256))
                generation += perf_counter() - t
                if not views:
                    break
                generated += len(views)
                t = perf_counter()
                for view in views:
                    alignments[target].packed(view)
                syndrome += perf_counter() - t
        full_group_seconds = perf_counter() - started
    else:
        for target, shape in jobs:
            t = perf_counter()
            views = tuple(islice(_views(text, target + base, shape, base, base), samples))
            generation += perf_counter() - t
            generated += len(views)
            t = perf_counter()
            for view in views:
                alignments[target].packed(view)
            syndrome += perf_counter() - t
    for target, shape in jobs:
        views = tuple(islice(_views(text, target + base, shape, base, base), samples))
        t = perf_counter()
        unique = {tuple(view) for view in views}
        dedup += perf_counter() - t
        del unique
    tracemalloc.start()
    before = tracemalloc.take_snapshot()
    if jobs:
        target, shape = jobs[0]
        retained = tuple(islice(_views(text, target + base, shape, base, base), samples))
        memory_peak = tracemalloc.get_traced_memory()[1]
        retained_allocations = sum(
            max(0, s.count_diff) for s in tracemalloc.take_snapshot().compare_to(before, "lineno")
        )
        del retained
    tracemalloc.stop()
    bch_rows = []
    alignment = _syndrome_alignment(spec, hrp, body)
    for e in (0, 1, 2, 4, 8):
        for s in range(5):
            if e + 2 * s > 8:
                continue
            erased = list(range(e))
            packed = 0
            for reverse in range(e + s):
                packed ^= alignment[1][body - reverse - 1][reverse + 1]
            syndromes = [(packed >> (10 * i)) & 1023 for i in range(8)]
            t = perf_counter()
            for _ in range(samples):
                _bch_syndrome_corrections(spec, erased, syndromes, body, s)
            seconds = perf_counter() - t
            bch_rows.append(
                {
                    "erasures": e,
                    "substitutions": s,
                    "calls": samples,
                    "seconds": seconds,
                    "calls_per_second": samples / seconds,
                }
            )
    roots = _word_roots(spec, body)
    root_rows = []
    for degree in range(1, 5):
        locator = [1] * (degree + 1)
        t = perf_counter()
        for _ in range(samples):
            for root in roots:
                _horner(locator, root, _gf1024_mul)
        root_rows.append({"locator_degree": degree, "scans": samples, "seconds": perf_counter() - t})
    return {
        "kind": "synthetic_kernel",
        "body_length": body,
        "expanded_length": len(bech32_hrp_expand(hrp)) + body,
        "checksum_symbols": len(spec.generator),
        "period": spec.period,
        "target_body_lengths": targets,
        "target_checksum_symbols": {str(n): 13 if n <= _SHORT_SPEC.period else 15 for n in targets},
        "unknown": unknown,
        "character_depth": None if group else depth,
        "group_depth": 2 if group else None,
        "raw_stratified_upper_bound": count,
        "structural_only_mass": structural_mass,
        "complete_group_structural_seconds": full_group_seconds,
        "generated_hypotheses": generated,
        "sampling_only": not (group and complete_groups),
        "generation_seconds": generation,
        "generation_per_second": generated / generation if generation else 0,
        "syndrome_seconds": syndrome,
        "syndrome_updates_per_second": generated / syndrome if syndrome else 0,
        "full_result_dedup_seconds": dedup,
        "traced_peak_bytes": memory_peak,
        "retained_allocation_count": retained_allocations,
        "bch": bch_rows,
        "root_location": root_rows,
        "guarantee_evidence": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--public", action="store_true")
    mode.add_argument("--kernel", action="store_true")
    parser.add_argument(
        "--lengths",
        type=int,
        nargs="+",
        help="Displayed lengths for --public; BCH body lengths for --kernel.",
    )
    parser.add_argument("--depths", type=int, nargs="+", choices=(2, 3, 4), default=[2, 3, 4])
    parser.add_argument("--deltas", type=int, nargs="+", default=list(DELTAS))
    parser.add_argument("--erasures", type=int, nargs="+", default=[0, 1, 2, 4, 8])
    parser.add_argument("--samples", type=int, default=32)
    parser.add_argument("--complete-groups", action="store_true")
    parser.add_argument("--memory", action="store_true")
    parser.add_argument("--seconds", type=float, default=10)
    args = parser.parse_args()
    print(
        json.dumps(
            {
                "system": platform.platform(),
                "python": platform.python_version(),
                "machine": platform.machine(),
            }
        ),
        flush=True,
    )
    if args.public:
        for profile, lengths in PUBLIC_LENGTHS.items():
            for length in lengths:
                if args.lengths and length not in args.lengths:
                    continue
                for depth in args.depths:
                    for unknown in (False, True):
                        for frozen in (False, True):
                            for delta in args.deltas:
                                for erasures in args.erasures:
                                    print(
                                        json.dumps(
                                            public_case(
                                                profile,
                                                length,
                                                depth,
                                                unknown,
                                                delta,
                                                erasures,
                                                frozen,
                                                args.seconds,
                                                args.memory,
                                            )
                                        ),
                                        flush=True,
                                    )
    else:
        for body in args.lengths or BODY_LENGTHS:
            for unknown in (False, True):
                for depth in args.depths:
                    print(json.dumps(kernel_case(body, depth, unknown, False, args.samples)), flush=True)
                print(
                    json.dumps(kernel_case(body, 2, unknown, True, args.samples, args.complete_groups)),
                    flush=True,
                )


if __name__ == "__main__":
    main()
