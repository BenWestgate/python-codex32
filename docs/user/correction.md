# Repairing a damaged codex32 backup

Use `check` first. If the text is invalid, `correct` can suggest repairs, but a
suggestion is not proof that it is the card you intended. Compare every
suggested character with the physical recovery card before accepting it.

For Bitcoin master-seed backups, use `ms32 check` and `ms32 correct`. The
generic `codex32 check` and `codex32 correct` commands provide the same codex32
repair machinery without Bitcoin Core fingerprint ranking.

## What `correct` can repair

Correction combines two different kinds of work. Their limits are separate.

### Wrong or unreadable characters at the right positions

Once the text is aligned to a valid codex32 length, the checksum can repair a
mixture of unreadable positions and wrong-but-valid codex32 characters. If
`E` positions are treated as unreadable/erased and `S` positions contain the
wrong codex32 character, the fixed-position BCH repair budget is:

```text
E + 2*S <= 8
```

Examples within that budget include eight unreadable positions, four wrong
characters, or four unreadable positions plus two wrong characters.

This bound is about characters that occupy the correct positions. It does not
mean that eight characters may have been physically omitted from the text.
Missing or extra characters first consume the structural-alignment budget
below.

### Missing, extra, or transposed characters

The character-level alignment search is bounded by:

```text
extra + missing + adjacent_transpositions + 2*distant_transpositions <= 4
```

A distant transposition costs two alignment units because it moves two
positions. After an alignment is proposed, any resulting unknown positions
must still fit the checksum-repair budget above.

The display-group search applies the same idea to four-character groups, with
a smaller budget:

```text
extra_groups + missing_groups + adjacent_group_transpositions
    + 2*distant_group_transpositions + corrupted_groups <= 2
```

A corrupted group is treated as four unknown character positions for checksum
repair. Thus the group search can identify at most two such groups, and the
checksum still decides whether their contents can be reconstructed.

### Consecutive trailing unknown positions

There is one intentionally different use case: completing a run of characters
whose positions are already known but whose values are unknown. For a normal
codex32 checksum, the final 13 positions may be entered as `?`; a
long-checksum string can use 15. The correction tests pin both cases.

These are **unknown positions, not deleted characters**. Do not remove the last
13 or 15 characters from a damaged card and ask codex32 to invent replacements.
If characters are physically missing, use the structural correction path and
its four-character alignment budget.

## What `correct` cannot establish

A valid checksum does not authenticate the wallet or prove that a suggested
repair matches the original paper backup. In particular, correction cannot:

- prove that cards with different identifiers or lengths belong together;
- turn a checksum match into independent wallet-identity evidence;
- safely choose among multiple plausible repairs without operator evidence;
- exceed the bounded alignment/checksum search merely because one candidate
  looks plausible; or
- recover arbitrary damage after the search deadline has expired.

For `ms32`, a separate wallet record and the recovered master fingerprint are
used for accident detection during restore. They are not part of the checksum
strength itself.

## Best-effort and incomplete searches

The correction search has a ten-second computation budget. If it finds a
candidate but does not finish the full bounded search, the CLI labels the
result **best effort / search incomplete**. Treat that as a candidate to check
against the paper, not as a unique correction.

If no repair is offered, recheck the transcription, spacing, case, identifier,
and expected backup length before assuming the physical card is beyond
recovery. Keep the observed text; deleting characters to force a new valid
checksum can lock a transcription mistake into a different valid string.

Never put a secret or share in shell command arguments. Run `ms32 correct` or
`codex32 correct` first, then enter the damaged text at the prompt.
