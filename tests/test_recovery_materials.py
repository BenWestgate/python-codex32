"""Static evidence that printable recovery materials preserve the intended separation."""

from pathlib import Path

_DOCS = Path(__file__).parents[1] / "docs"


def test_share_card_is_printable_complete_and_contains_no_wallet_identifier() -> None:
    card = (_DOCS / "recovery-card.html").read_text().lower()

    assert "@page" in card and "size: letter" in card
    assert card.count('class="group"') == 32
    for required in (
        "bip93/codex32",
        "threshold",
        "four-character identifier",
        "share index",
        "network",
        "wallet policy",
        "protected codex32 text",
        "offline recovery",
        "manual fallback",
        "watch-only",
    ):
        assert required in card
    assert "fingerprint" not in card and "receiving address" not in card


def test_separate_record_has_verification_metadata_but_no_secret_fields() -> None:
    record = (_DOCS / "wallet-verification-record.html").read_text().lower()

    for required in (
        "master fingerprint",
        "known receiving address",
        "account number",
        "derivation",
        "multisig",
        "coordinator",
        "cosigner",
        "watch-only verification",
    ):
        assert required in record
    assert "never write a seed, share" in record
    assert "protected codex32 text" not in record
