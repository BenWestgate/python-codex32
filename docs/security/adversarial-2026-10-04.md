# Supplied adversarial reviews: finding disposition

This is a traceability snapshot, not a release approval. The supplied reviews
examined `reviewability-v1` at `c118a83`; the branch now points to
`5325eb7543e8545b321b0512b38c896b1e269ece`. Unmerged fixes are identified by PR,
not by similarly named sibling branches. Issue
[#20](https://github.com/BenWestgate/python-codex32/issues/20) tracks audit closure;
[#38](https://github.com/BenWestgate/python-codex32/issues/38) owns integration and
the final reviewer handoff.

## Inputs and qualifications

The four supplied files are identified by their SHA-256 hashes. D means DeepSeek,
G means GLM, K means Kimi, and C means the consolidated report.

| File | SHA-256 |
|---|---|
| `codex32-review-DeepSeek_V4.1_Flash.md` | `94398728d93643e609987930c7fb38ea37b828fab9071d61aa1c255e5316450a` |
| `codex32-review-GLM5.3_Flash.md` | `01569d9c3a6fbd1aae6f3a92d523ce9cafb50a66d16c56e91b1ff87030f5af11` |
| `codex32-review-KimiK3_High.md` | `139ac9366b6f4c72f33b3d17e649e88d68e266c19345102084883aa850ab2977` |
| `consolidated-review.md` | `458e647b7cd14f27f71809fdc1b240c8fd4b3cfbfb06e2005b0eb0a4d6767ea9` |

The originals qualify several claims more narrowly than the consolidation:

- Kimi calls the Core requirement consistent with the threat model and asks for
  a documentation hint. GLM recommends a warning-only fallback. The maintainer
  chose Core-backed fingerprint checks for `ms32`; generic `codex32` is the
  offline fallback. This is an intentional boundary with a UX/documentation gap.
- Kimi reviewed live Core and GUI paths statically. Its restore recommendation
  exceeded the then-current operator-comparison contract. The accepted release
  requirement is now verification before mutation for accident safety, using
  an independent record or the explicit no-record confirmation. Malicious share
  replacement and encrypted descriptors remain separate human-planned work in
  [#55](https://github.com/BenWestgate/python-codex32/issues/55).
- Kimi distinguishes accidental `repr()` disclosure from deliberate `str()`
  export. The accepted project contract redacts both; `.text` is explicit export.
- The consolidation's shared-baseline table does not prove each original ran
  every listed command. In particular, only Kimi explicitly records the BCH
  constant verifier. Historical reviewer claims are not new validation evidence.
- The consolidation calls the setup defect independently found by two reviews
  in its summary, although all three originals contain it.
- GLM's secondary dependency-install ordering claim did not reproduce with pip's
  normal build isolation. The Astra-placeholder claim is stale. Neither justifies
  a new defect issue; the unwanted repository configuration was removed anyway.

## Numbered findings

“Merged” below means present on the branch identified above. “PR” means a focused
patch exists but still needs human integration. Duplicate IDs share one row.

| Consolidated ID | Original sources | Assessment and current coverage |
|---|---|---|
| BL1 | D-B1, G-1, K-F4 | Confirmed developer-install defect; #3/#6 and merged #7 remove the test-only `bip32`/secp256k1 dependency. #115 corrects contributor setup. |
| BL2 | D-B2 | Confirmed missing BSD notice; merged #15 includes `LICENSES` in wheel and sdist. |
| H1 | K-F2 | Confirmed default-rendering leak; #22 and merged #25 redact `str()` and `repr()`, including nested correction candidates. |
| H2 | K-F3 | Accepted accident-safety gate; #26/#30, CLI #57/#80/#81, GUI #118. #81 verifies existing seeds before replacement cards; #80 distinguishes an unavailable Bails check. #55 is a separate planning issue, not a missing v1 PR. |
| H3 | K-F1 | Confirmed HRP-boundary defect; #32/#33 enforce 83 characters in parsing and correction contexts. Generalized-HRP draft vectors at `BenWestgate/bips` PR #2, commit `01374bf`, explicitly allow 83 and reject 84; 1023 is the expanded-codeword bound. |
| M1 | G-2 | Confirmed standalone mixed-case regression; #37 and merged #42, including the required-preflight seed preservation follow-up. Interactive recovery already interpreted case. |
| M2 | G-3, K-F9 | Intentional Core boundary; #99 fixes misleading Core diagnostics/preflight. This change documents the generic offline fallback. Do not introduce Python secp256k1 or silently discard fingerprints. |
| M3 | K-F6 | Intended switch to a supplied complete S, with missing notice; #95 announces it after partial share entry. Rejecting S would change the chosen behavior. |
| M4 | D-D4, G-4 | Confirmed review-process gap; #38 requires the final `docs/developer/reviewing.md`, pinned candidate, reading order, reproducible evidence, GUI scope, and human integration order. This snapshot supplies finding provenance but does not replace that frozen-tip handoff. |
| M5 | D-D3 | Confirmed inherited contributor boilerplate; focused #115 replaces it and restores licensing/attribution terms. |
| M6 | D-D1 | Confirmed historical measurements presented as current; focused #116 labels the `6802d86` snapshot and raw evidence. Re-running a benchmark cannot reproduce that host's old measurements. |
| M7 | D process notes, K-F5 | Optimized tests and constant verification are in merged #47/#40. Dormant fuzz harnesses remain deferred until an engine, corpus, and budget are selected; no claimed fuzzing result is inferred from their presence. |
| M8 | K-F7 | Partially fixed by merged #16 for supplied raw bytes. The existing-secret ceremony still bypassed root validation; #125 and focused PR #126 cover the remaining API path. Parsing remains format validation; CL secrets have no BIP32 requirement. |
| M9 | K-F8 | Intentional stricter threshold grammar: `1` is rejected even for S. The API guide now records this reference-decoder divergence. |
| L1 | D-C3 | Confirmed exit-status collision; #39 and merged #45 distinguish valid `0`, emitted suggestion `1`, usage/input syntax `2`, and no usable suggestion `3`. Suggestions remain nonzero. |
| L2 | D-C1/C2, G-6 | Confirmed unreachable guards/always-false field; merged #46 removes the original findings. #105 removes the later redundant recovery/search paths. |
| L3 | D-C5 | No demonstrated input-validation bypass: current asserts narrow internal types/state after explicit validation. The API guide states the boundary; optimized CI guards it. No blanket assert replacement is warranted. |
| L4 | D-D6 | Intentional historical benchmark evidence, retained by merged #14; #116 labels its age and limits. No fresh timing guarantee follows from it. |
| L5 | D process notes, K-F9 | Maintainer-authorized library cap is `<5200`; GUI is separately `<2250` in #118. The API guide defines recursive nonblank/non-comment counting, including docstrings, and names the enforcement test. |
| L6 | D-D5 | Human integration/authorship work in #38. Preserve dependent PR history until the maintainer settles the stack and performs any required rewrite/squash. |

## Nits and secondary claims

| Finding | Sources | Disposition |
|---|---|---|
| Package export count says 25 instead of 24 | D-D2 | #64 removes obsolete `core_descriptors`; #53 documents the resulting 23-name package surface and supported module-level vector helpers. The public API regression rejects the removed export. |
| Test fake accepts obsolete `private=` | D-C4 | One-line #117 makes `_FakeBitcoinCore.initialize` match the production call shape. |
| Stale `MANIFEST.in` provenance exclusion | D notes, K-F9 | Already removed on the current branch (`d6a9f99`); keep `MANIFEST.in` because it still selects license, test, tool, and documentation files for the sdist. |
| Ignored provenance/plans | D notes | Intentional local-only unfinished work stays under the ignored `docs/planning/` path. This finished security audit ledger lives in `docs/security/`; #23 records the earlier audit verdict. #38 links the local cleanup checklist for agents. |
| Beta classifier with an rc version | G-6 | A maturity classifier and prerelease version are separate metadata; no demonstrated defect. Final stable metadata belongs to artifact qualification #5/#52. |
| Extra blank line in `pyproject.toml` | G-6 | No longer present on the current branch. |
| Repository Codex overrides | D notes | #41 and merged #48 remove the configuration. Whether the old named model exists is no longer relevant to the fix. |
| Core RC documentation links | D notes | #93 points to the maintained offline-signing tutorial, as chosen by the maintainer. Stable/signed-RC monitoring is separate from audit closure. |
| Budget-test discoverability | K-F9 | Direct test pointer added to the API guide; #38's final handoff must also name both library and GUI checks. No test-file move is needed. |
| User-facing vector helpers require underscores | G-5 | #49/#53 expose the required codec/checksum helpers at their owning modules and document internal couplings. Further architecture work is explicitly separate. |
| Stale/overlapping branch names | D notes | Use PR numbers and commit IDs as provenance. Pruning branches is housekeeping and does not establish or invalidate a fix. |
| Dependency-install ordering | G-1 secondary note, C rejected claims | Not reproduced under ordinary pip build isolation; no new issue. |

## Verification and remaining release work

On 2026-10-04, GitHub reported successful checks and a Codex review tied to the
current commit for #12/#13/#33, #52/#53/#57/#59/#64, #80/#81/#93/#95/#97/#99/#105,
#115/#116/#117/#126, and the focused GUI #66/#77/#78/#118/#119 changes. These include
clearly disclosed Codex-generated reviews posted through the maintainer's
account; they are not human approvals or proof of an independent Claude review.
The PR #65 parent has a real open refresh-mode finding fixed by stacked #66;
review and integrate them together. GitHub's “blocked” status can also reflect
signature/authorship or branch rules even when checks pass.

Focused local checks at #103 commit `2924f5f` passed for default rendering,
record mismatch before wallet calls, hidden fingerprint, recordless decline and
acceptance, fresh creation, existing creation, and supplied-byte root rejection.
The complete PR #103 security diff scan at behavioral parent `d9ce204`, against
`115f2c2`, found no reportable finding; its later commit changes documentation
only. These checks do not prove the later existing-secret API root path fixed.

#93 and #97 were updated after new reviews: the offline boot USB is distinct
from the PSBT transfer medium; the FAQ distinguishes unshared fingerprint-derived
identifiers and carries #96's identical 256-bit card so its link resolves. Their
current heads now have green Python-package CI and current-head Codex ACKs; #93's
inline finding is resolved and #97's two follow-up findings are resolved.

The remaining order is the live #38 stack: restore and Core UX, foundation/API,
audit/release support, user documentation, then the GUI replay. The new #125 root
fix in #126 must be included before freeze. #115/#116/#117 supply the mechanical
cleanup; this patch supplies the remaining contract clarifications. The local
ignored `docs/planning/v1-pre-review-cleanup.md` is a working checklist, not a
shipped report.

Human review/integration and required signatures remain. The final candidate
must then receive the pinned reviewer handoff, artifact qualification, Tails
rendering/manual GUI-to-Core checks, and a fresh adversarial pass covering the
library, CLI, GUI, and recovery documentation. Until those succeed, “all
material validated findings resolved in the release candidate” is unproven.
