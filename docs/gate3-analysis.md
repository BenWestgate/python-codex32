# Gate 3 capture-volume and prototype evidence

Gate 3 ranks structural correction classes by conservative decoder-capture
volume. The checked-in `tools/gate3_capture.py` reproduces the arithmetic using
integers. Runtime ranking must not depend on floating-point logarithms.

## Model

For one exact result class, the conservative volume is:

```text
alignments
* 32 ** (omitted symbols + explicit erasures)
* C(known target symbols, substitutions)
* 31 ** substitutions
```

The alignment term uses combinations rather than ordered edit sequences.
Character alignments choose extra observed characters and missing target
positions. Group alignments use only complete four-character groups after the
immutable HRP and separator. Burst alignments choose contiguous starts.

Classes are compared only with classes compatible with the same observed-minus-
target length. For each rank, the conservative union bound includes every
supported class with volume no greater than that rank. A class is safe only
when:

```text
10_000 * cumulative_volume < 2 ** checksum_bits
```

The checksum space is 65 bits for regular codex32 and 75 bits for Long.
Optional header, share-index, CRC, fingerprint, and profile-semantic filters do
not enlarge the safety envelope.

## Consequences

Twelve unknown symbols cannot satisfy the regular bound: even one fixed
alignment has volume `32**12 == 2**60`, giving `2**60 / 2**65 == 1/32` before
other classes or positions are counted. The former three-omitted-group minimum
is therefore superseded by the capture-volume policy.

At 48 characters, the analysis accepts the zero-substitution nine-character
omission burst and rejects the ten-character burst. It accepts the two-
insertion/two-omission class through two substitutions but rejects its
three-substitution layer. These are arithmetic boundaries, not runtime promises.

## Runtime prototype

`tools/gate3_prototype.py` independently enumerates structural alignments and
passes each resulting fixed-length string to the existing private BCH adapter.
It does not implement checksum or field arithmetic. Its tests cover character
insertion, omission, a balanced pair, two missing groups, and four extra groups.

On the 2026-08-24 development system with Python 3.13:

| Case | Fixed candidates | Time |
|---|---:|---:|
| 48-character, one insertion plus one omission | 990 | 1.5 s |
| 74-character, one insertion plus one omission | 4,757 | 7.3 s |
| 127-character, one insertion plus one omission | 15,252 | 25.9 s |

The timings are feasibility measurements, not stable test thresholds. Runtime
uses a completed-class work counter and an adaptive CLI deadline. It never
accepts an incomplete rank class.

## V1 structural generators

The production adapter may retain these shapes when their exact result class
also passes the cumulative probability bound:

- one or two arbitrary extra characters;
- one or two arbitrary omitted characters;
- one balanced extra-plus-omitted character pair;
- one-sided contiguous character bursts from three through nine characters;
- one through four extra four-character groups;
- one or two omitted four-character groups; and
- one extra plus one omitted four-character group.

Two arbitrary insertions plus two arbitrary omissions require about one million
fixed candidates at 48 characters. Other unequal mixed two-character shapes
also exceed the simple runtime budget. They are excluded from v1 even when a
low-substitution result class passes the probability bound.

The public API completes the retained finite envelope without a deadline. The
CLI checks its deadline between complete classes, using observed work rate to
avoid beginning a class it cannot reasonably finish. Faster machines may search
more classes. The CLI returns only one unique best reconstruction and otherwise
reports failure or ambiguity.
