"""Static evidence that printable recovery materials preserve the intended separation."""

import re
from pathlib import Path

_ROOT = Path(__file__).parents[1]
_DOCS = _ROOT / "docs" / "user"


def test_share_card_is_printable_complete_and_contains_no_wallet_identifier() -> None:
    card = (_DOCS / "recovery-card.html").read_text().lower()

    assert "@page" in card and "size: letter" in card
    assert card.count('class="group"') == 32
    for required in (
        "bip93/codex32",
        "threshold",
        "four-character identifier",
        "share index",
        "wallet policy",
        "protected codex32 text",
        "offline recovery",
        "manual fallback",
        "watch-only",
    ):
        assert required in card
    assert "fingerprint" not in card and "receiving address" not in card
    assert "network:" not in card


def test_wallet_record_has_verification_metadata_but_no_secret_fields() -> None:
    record = (_DOCS / "wallet-verification-record.html").read_text().lower()

    for required in (
        "master fingerprint",
        "account number",
        "derivation",
        "multisig",
        "coordinator",
        "cosigner",
        "fresh initialization",
        "watch-only verification",
        "approximate creation / earliest-use date",
    ):
        assert required in record
    assert "cosigner trusted contacts:" in record
    assert "network:" not in record
    assert "known receiving address" not in record
    assert "first address" not in record
    assert "public keys" not in record
    assert "never write a seed, share" in record
    assert "protected codex32 text" not in record


def test_guide_uses_tails_one_shot_qr_workflow() -> None:
    guide = (_DOCS / "guide.md").read_text()

    for obsolete in ("qrencode", "tr -d", "head -n", "ANSIUTF8", "UTF8"):
        assert obsolete not in guide
    assert "listdescriptors | jq -c" in guide and "next_index}]' | qr" in guide
    assert "codex32 wallet multisig-xpub | qr" in guide
    assert "zbarcam --raw --oneshot |" in guide


def test_guide_grades_fresh_setup_before_recovery_and_keeps_qr_public() -> None:
    guide = (_DOCS / "guide.md").read_text()
    guide_prose = " ".join(guide.split())

    assert guide.index("Recommended: dedicated online spending wallet") < guide.index(
        "More protection: online watch-only wallet"
    )
    assert guide.index("### 3. Make a Bitcoin Core wallet") < guide.index(
        "## Recover an existing or inherited wallet"
    )
    assert "`codex32 create 2` produces three shares" in guide
    assert "one can be lost" in guide
    assert "`codex32 create 3` produces five shares" in guide
    assert "`codex32 create 4cash --shares 7` produces seven `cash` shares" in guide
    assert "Write each result on a new recovery card and press Enter" in guide_prose
    assert "clears the terminal and its saved scrollback" in guide_prose
    assert "displays only what you entered" in guide_prose
    assert "does not reveal or apply the expected text" in guide_prose
    assert "reports how many cards you have confirmed" in guide_prose
    assert "If there is more than one, choose by number" in guide_prose
    assert "codex32 waits and continues automatically" in guide_prose
    assert 'walletpassphrase "YOUR PASSPHRASE" 5' in guide
    assert "Bitcoin Core spending wallet initialized." in guide
    assert "initialized and verified" not in guide
    assert "approximate\ncreation / earliest-use date" in guide
    assert "descriptor timestamp on a recovery\ncard" in guide
    assert "codex32 wallet bitcoin-core watch-only --timestamp 0" in guide
    assert "codex32 wallet bitcoin-core restore --timestamp 0" in guide
    assert "bitcoin-core restore --timestamp 0 |" not in guide
    assert "bitcoin-core restore --timestamp 0 | qr" not in guide
    assert "zbarcam --raw --oneshot > unsigned.psbt" in guide
    assert "zbarcam --raw --oneshot > signed.psbt" in guide


def test_readme_opens_with_the_primary_user_workflow() -> None:
    readme = (_ROOT / "README.md").read_text()

    introduction = readme[: readme.index("## Install")]
    assert "paper-backup format for Bitcoin master seeds" in introduction
    assert "private\nrecovery secret from which a Bitcoin wallet derives its keys" in introduction
    assert "an unshared master-seed backup or an M-of-N shared backup" in introduction
    assert "any M of the N paper shares can recover the master seed" in introduction
    assert "set up a user-created blank Bitcoin Core wallet from a new or existing" in introduction
    assert "This is not a Bitcoin wallet" in introduction
    assert "Use it on a trusted computer" in introduction
    assert "codex32\nmakes no network connection" in introduction
    assert "local Bitcoin Core\ninstance through `bitcoin-cli`" in introduction
    assert "Use it offline" not in introduction
    assert "other codex32 applications" not in introduction

    start = readme.index("## Start here")
    maintenance = readme.index("## Recovery and maintenance")
    developers = readme.index("## For developers and reviewers")
    assert start < maintenance < developers
    assert "To install the project with its pinned\ndependencies" in readme
    assert "run these commands from the project folder:" in readme
    assert "```bash\ncodex32 create 2\n```" in readme[start:maintenance]
    prerequisite = "Start Bitcoin Core 30 or newer with local RPC enabled"
    assert prerequisite in readme[start:maintenance]
    assert readme.index(prerequisite, start, maintenance) < readme.index(
        "codex32 create 2", start, maintenance
    )
    assert "add or replace shares for an existing backup" in introduction
    assert "This creates three shares with a random identifier" in readme[start:maintenance]
    assert "Any two recover the seed, so\none can be lost" in readme[start:maintenance]
    assert "codex32 create 3cash --shares 6" in readme[start:maintenance]
    assert (
        "Once the shares are confirmed, codex32 initializes the\nuser-created blank Bitcoin Core wallet"
        in readme
    )
    assert "codex32 detects and\nreports the local Bitcoin Core network" in readme[start:maintenance]
    assert "bitcoin-qt -signet -server" in readme[start:maintenance]
    assert readme.index("bitcoin-qt -signet -server") < readme.index("codex32 create 2")
    assert "user-created blank Bitcoin Core wallet" in " ".join(readme[start:maintenance].split())
    assert "[user guide](docs/user/guide.md)" in readme[start:maintenance]
    for command in ("codex32 check", "codex32 secret", "codex32 share d", "codex32 correct"):
        assert command in readme[maintenance:developers]
    assert "never put recovery text on the command line" in readme[maintenance:developers]
    assert "Do not type recovery text" not in readme[start:maintenance]
    assert "codex32 wallet multisig-xpub" not in readme
    assert "## Common commands" not in readme


def test_security_model_is_concise_normative_and_current() -> None:
    model = (_ROOT / "docs" / "security" / "model.md").read_text()
    invariants_path = _ROOT / "docs" / "security" / "invariants.md"
    invariants = invariants_path.read_text()
    agents = (_ROOT / "AGENTS.md").read_text()
    guide = (_DOCS / "guide.md").read_text()
    api = (_ROOT / "docs" / "developer" / "api.md").read_text()
    invariant_prose = " ".join(invariants.split())
    model_prose = " ".join(model.split())
    guide_prose = " ".join(guide.split())

    assert 120 <= len(model.splitlines()) <= 175
    assert 1400 <= invariants_path.stat().st_size <= 1800
    assert len(re.findall(r"^\d+\. ", invariants, re.MULTILINE)) == 12
    for required in (
        "Headers precede checksums",
        "Outputs are reparsed",
        "separate OS-CSPRNG call",
        "random initial share",
        "original ceremony result",
        "Correction is bounded and fail-closed",
        "Private descriptors exist only in Python memory and child stdin",
        "Bitcoin Core chains are discovered before entropy or recovery input",
        "revalidated before import",
        "no passphrase channel",
        "relocked and verified on every exit path",
        "Only Bitcoin Core descriptor wallets sign with codex32-derived keys",
        "malware-free computers with trusted software",
        "Ethernet, internet, Tor, Wi-Fi, Bluetooth, and cellular",
        "Online Core nodes synchronize",
    ):
        assert required in invariant_prose
    assert "[security invariants](invariants.md)" in model
    for assumption in (
        "keys derived from a codex32 master seed",
        "malware-free and whose other software is trusted",
        "Ethernet, internet, Tor, Wi-Fi, Bluetooth, and cellular",
        "offline codex32 or signing work",
        "networked computer before trusting its balances or history",
    ):
        assert assumption in model_prose
    assert "mandatory\n`docs/security/invariants.md` contract" in agents
    assert "Required Properties" not in agents
    assert "normally networked Bitcoin Core node" in guide
    assert "bitcoin-qt -signet -server" in guide
    assert "codex32 detects and reports the local Bitcoin Core network" in guide_prose
    assert "do not need to change `bitcoin.conf`" in guide_prose
    assert "Trust balances and history only after\nthat finishes" in guide
    assert "QR tools below transport only public\ndescriptors or PSBTs" in guide
    assert "Use the coordinator only to assemble the policy and PSBT" in guide_prose
    assert "Bitcoin Core descriptor wallet as the signer" in guide_prose
    assert "codex32 does not build the signing wallet" in guide_prose
    assert "recursive-include docs *.html *.md" in (_ROOT / "MANIFEST.in").read_text()
    for heading in (
        "## Protected assets and trust boundaries",
        "## Operator assumptions",
        "## Security limitations",
        "## Validated-artifact and parsing controls",
        "## Creation, sharing, and recovery controls",
        "## Correction controls",
        "## Bitcoin Core controls",
        "## Verification map",
    ):
        assert heading in model
    for required in (
        "Only after checksum verification",
        "generates *k* random initial shares",
        "generates and confirms *k−1* random initial shares",
        "new share index not used by its inputs",
        "sharing an existing master seed",
        "original ceremony",
        "strictly below `1e-5`",
        "One eligible wallet is offered directly",
        "explicit chain arguments probe the five standard local networks",
        "Every call uses loopback and the selected chain",
        "immediately before import",
        "expanded before requesting an unlock",
        "exact eight expected public",
        "no passphrase channel",
        "success, failure, state change, or interruption",
    ):
        assert required in model
    for historical in (
        "Gate 3",
        "Severity calibration",
        "Frozen 48-character alignment counts",
        "AMD Ryzen",
        "tracemalloc",
        "158 MB",
        "benchmark",
    ):
        assert historical not in model
    assert "direct share" not in model
    assert "ordinary share" not in model
    assert "ordinary index" not in model
    assert "Only afterward does the HRP select a fixed application profile." in api
    assert "benchmarks are described in the [security model]" not in api


def test_release_workflow_pins_actions_and_publishes_release_artifacts() -> None:
    workflow = (_ROOT / ".github" / "workflows" / "publish.yml").read_text()

    assert "types: [published]" in workflow
    assert 'SOURCE_DATE_EPOCH: "1763060600"' in workflow
    assert "requirements/release-build-dependencies.txt" in workflow
    assert "python -m build --no-isolation" in workflow
    assert 'tar --sort=name --mtime="@${SOURCE_DATE_EPOCH}"' in workflow
    assert "gzip -n" in workflow
    assert 'gh release upload "$GITHUB_REF_NAME" dist/*' in workflow
    assert "id-token: write" in workflow
    uses = re.findall(
        r"uses: ([^\s#]+)",
        "\n".join(path.read_text() for path in (_ROOT / ".github" / "workflows").glob("*.yml")),
    )
    assert uses and all(re.fullmatch(r"[^@]+@[0-9a-f]{40}", use) for use in uses)
