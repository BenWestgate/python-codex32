# Deliberate divergences and non-goals

These choices are not presented as BIP93 requirements.

| Decision | Reason |
|---|---|
| API and imports support every 16–64-byte `ms` length | BIP93 permits them; closed PR #2077 is research only; fresh CLI generation is deliberately limited to 16 or 32 bytes |
| random electronic output indices | reduces canonical index disclosure; explicit indices preserve requested order |
| generation-only CRC padding | small recovery hint; not validity or share semantics |
| fingerprint identifier only for fresh k=0 | shared sets, raw seeds, re-sharing, and CL generation use random IDs unless explicitly overridden |
| BIP39 profiles are migration-only in CLI | website marks them not recommended; API can recover/derive codex32 only |
| reject existing derivation targets | enforces BIP93's fresh-index wording |
| fixed BCH is the current shipped behavior | a bounded structural adapter ships only if the cuttable Gate 3 passes its completeness, performance, size, and audit conditions |
| private descriptors contain root xprv | matches Bitcoin Core behavior and carries an explicit authority warning |
| no partial-basis completion | unauthenticated points can create incompatible same-header polynomials |

Unknown HRPs, GUI, networking, RPC, secret storage, runtime profiles, BIP39
mnemonics, and arbitrary descriptor parsing are explicit v1 non-goals.
Structural correction is absent today and remains absent in v1 unless the
cuttable gate in [the production-ready plan](production-ready-v1.md) passes.

Pending-standard compatibility, the external BIP32 boundary, identifier
privacy, and Python secret-memory limitations are tracked with controls and
review triggers in the [accepted-risk register](accepted-risks.md).
