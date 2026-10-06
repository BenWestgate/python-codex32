# Security audit status — 2026-10-05

This is a point-in-time release-gate snapshot. It does **not** declare the
audit or release qualification complete.

## Supplied-report disposition

The four supplied review reports are exhaustively mapped by issue
[#127](https://github.com/benwestgate/python-codex32/issues/127) and its
`docs/security/adversarial-2026-10-04.md` ledger. That ledger includes report
hashes, source qualifications, limitations, and the disposition of each
finding. No material validated finding from those reports currently lacks a
tracker and a focused fix or accepted disposition.

The final reviewer-handoff process finding (M4) remains tracked by issue
[#38](https://github.com/benwestgate/python-codex32/issues/38). Its handoff
change must be prepared only after the release-candidate tip is frozen so that
the required commit pins are not stale when reviewers receive them.

## Candidate inputs

At this snapshot, the remaining runtime and security audit pull-request heads
are #33, #57, #105, #99, #80, #81, #95, #126, #130, and #132. Their CI,
review-thread, and AI-assisted-review evidence is recorded in #127. Pull
requests #116 and #117 have the same green, thread-clean status.

Two documentation changes still require their stated final gates:

- #115 includes the contributor-guide correction through commit `2511af8`.
  Its responsible-human authorship/rewrite policy item intentionally remains
  open, and a cancelled-job rerun was still settling at this snapshot.
- #93 is release-documentation follow-up, not a newly discovered audit
  finding. Its maintainer threads were resolved at commit `1dcee71`; its
  exact-head matrix and a current-head Codex review were still settling.

Statuses above are evidence captured on 2026-10-05, not substitutes for
checking the exact integrated candidate.

## Additional release-gate findings

Two findings discovered after the supplied-report audit are tracked
separately and must be present in the frozen candidate:

- #128 / #130 removes an unused unauthenticated descriptor API.
- #129 / #132 prevents `CorrectionEdit` values from being disclosed by
  default rendering.

Both focused fixes had mechanical verification and review at this snapshot.
They are not retroactively attributed to the four supplied reports.

## Required closeout order

Do not run or describe a new full adversarial review before the candidate is
frozen. Closeout proceeds in this order:

1. Responsible humans review, rewrite where policy requires it, and integrate
   the focused changes, including both post-audit release-gate fixes.
2. Freeze the exact library, CLI, GUI, and recovery-documentation candidate.
3. Produce the #38 reviewer handoff with exact commit pins and review order.
4. Run the composed full suite, Bitcoin Core fixture, and exact-artifact
   qualification against the frozen candidate.
5. Perform the GUI and Tails manual qualification.
6. Run a fresh adversarial review across the frozen library, CLI, GUI, and
   recovery documentation.

Only evidence tied to that exact frozen candidate can close these gates.
