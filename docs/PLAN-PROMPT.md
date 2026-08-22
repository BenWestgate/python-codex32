Review this repository against:

- BIP93 [https://github.com/bitcoin/bips/blob/master/bip-0093.mediawiki](https://github.com/bitcoin/bips/blob/master/bip-0093.mediawiki)
- BlockstreamResearch/codex32 docs/wallets.md [https://github.com/BlockstreamResearch/codex32/blob/master/docs/wallets.md](https://github.com/BlockstreamResearch/codex32/blob/master/docs/wallets.md)
- secretcodex32.com book [https://secretcodex32.com/docs/2023-03-07--bw.pdf](https://secretcodex32.com/docs/2023-03-07--bw.pdf)
- secretcodex32.com website [https://secretcodex32.com/](https://secretcodex32.com/)
- BlockstreamResearch/codex32 PR #70 [https://github.com/BlockstreamResearch/codex32/pull/70](https://github.com/BlockstreamResearch/codex32/pull/70)
- Incomplete Rust reference impl[https://github.com/BlockstreamResearch/codex32/tree/master/reference/rust-codex32](https://github.com/BlockstreamResearch/codex32/tree/master/reference/rust-codex32)
- Elements project codex32 impl [https://github.com/search?q=repo%3AElementsProject%2Flightning+codex32&type=code](https://github.com/search?q=repo%3AElementsProject%2Flightning+codex32&type=code)
- [CL — Core Lightning `exposesecret`](https://docs.corelightning.org/reference/exposesecret)
- [B388 — wallet policies](https://github.com/bitcoin/bips/blob/master/bip-0388.mediawiki)

Do not modify the repository during planning.

Develop/update a gated completion plan for making this repository a reasonably
secure, HUMAN auditable, easily human-reviewable reference implementation of BIP93/codex32 and a CLI reference implementing the functionality described by those sources. Later, a GUI will be added but not until the API and CLI are production ready.

First build/update a requirements traceability matrix:

source section
→ normative/functional requirement
→ current code module/function
→ current tests
→ status
→ evidence
→ remaining work

Then report:

Overall implementation status.
CLI coverage and usability gaps.
Security/auditability concerns.
A prioritized remaining-work list.

Pay particular attention to whether the architecture makes the specification-to-code mapping obvious enough for an independent human auditor. Do not infer compliance merely because similarly named functionality exists; verify behavior.

Then divide remaining work into implementation gates.

Each gate must contain:

1. Objective
2. Exact requirements/spec sections covered
3. Files/modules expected to change
4. Tests required
5. Security/invariant considerations
6. Success criteria
7. Verification commands
8. Artifacts/documentation that must be updated
9. Dependencies on previous gates

Order gates so foundational correctness precedes higher-level CLI features.

Important:

- A gate is not complete merely because code was written.
- All success criteria and verification must pass before advancing.
- Existing behavior must not regress.
- Do not weaken tests to make a gate pass.
- Do not silently reinterpret a specification requirement.
- If a requirement is ambiguous, identify the ambiguity explicitly.
- Prefer direct mappings between specification concepts, implementation,
  and tests.
- The gate should always be focused. Avoid super gates which attempt to do too much, are overly large, or overly complex as this makes human review difficult.

Finish with the proposed gates and wait for review. Do not implement yet.

The **local repository root** is at ~/Documents/GitHub/python-codex32 and authorization is granted to run the existing test suite and non-destructive analysis commands. The README.md is WIP and non-authoritative context for requirements or expected behavior. There may be broken/useless tests. particularly in test_cli.py, test_correction.py and test_roundtrip_interpolated.py, correction.py may need to be rewritten from scratch to remove bloat and lack of human reviewability. cli likely needs refactoring to ease human review time and human understanding of the code. It is possible business logic is in cli.py that belongs in the API. Do not duplicate domain logic between interfaces. There may be dead and obsolete code to remove. It was determined that shared and unshared machine generated fresh secrets SHOULD use CRC padding while shares must be uniformly random masks. The shared fresh secrets can use rejection sampling until their CRC is valid. The optimum CRC should be determined, its purpose is to slightly help recovery in the case of a damaged secret.