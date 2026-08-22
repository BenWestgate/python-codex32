# Deliberate divergences and non-goals

These choices are not presented as BIP93 requirements.

| Decision | Reason |
|---|---|
| support every 16–64-byte `ms` length | BIP93 permits them; closed PR #2077 is research only |
| random electronic output indices | reduces canonical index disclosure; explicit indices preserve requested order |
| generation-only CRC padding | small recovery hint; not validity or share semantics |
| fingerprint identifier only for fresh k=0 | shared sets use random IDs; raw seeds and re-sharing require explicit IDs |
| BIP39 profiles are migration-only in CLI | website marks them not recommended; API can recover/derive codex32 only |
| reject existing derivation targets | enforces BIP93's fresh-index wording |
| fixed BCH only | structural search/ranking added excessive unauditable policy and code |
| private descriptors contain root xprv | matches Bitcoin Core behavior and carries an explicit authority warning |
| no partial-basis completion | unauthenticated points can create incompatible same-header polynomials |

Unknown HRPs, GUI, networking, RPC, secret storage, runtime profiles, BIP39
mnemonics, CL generation, structural correction, and arbitrary descriptor
parsing are explicit v1 non-goals.
