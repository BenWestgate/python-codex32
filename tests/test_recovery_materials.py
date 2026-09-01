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
    assert "codex32 wallet bitcoin-core watch-only | qr" in guide
    assert "codex32 wallet multisig-xpub | qr" in guide
    assert "zbarcam --raw --oneshot |" in guide


def test_guide_grades_fresh_setup_before_recovery_and_keeps_qr_public() -> None:
    guide = (_DOCS / "guide.md").read_text()

    assert guide.index("Recommended: dedicated online spending wallet") < guide.index(
        "More protection: online watch-only wallet"
    )
    assert guide.index("### 3. Make a Bitcoin Core wallet") < guide.index(
        "## Recover an existing or inherited wallet"
    )
    assert "approximate\ncreation / earliest-use date" in guide
    assert "descriptor timestamp on a recovery\ncard" in guide
    assert "listdescriptors | jq -c" in guide and "next_index}]' | qr" in guide
    assert "bitcoin-core restore --timestamp 0 |\n  bitcoin-cli" in guide
    assert "bitcoin-core restore --timestamp 0 | qr" not in guide
    assert "zbarcam --raw --oneshot > unsigned.psbt" in guide
    assert "zbarcam --raw --oneshot > signed.psbt" in guide


def test_readme_explains_checksum_correction_and_new_share_sets() -> None:
    readme = (_ROOT / "README.md").read_text()

    assert "Creation adds the codex32 checksum" in readme
    assert "`codex32 check` detects damaged text" in readme
    assert "`codex32 correct` only suggests a repair" in readme
    assert "Shared backups use Shamir secret sharing" in readme
    assert "a new M-of-N share set" in readme


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
