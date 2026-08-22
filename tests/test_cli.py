"""End-to-end tests for CLI command routing."""

from click.testing import CliRunner
from data.bip93_vectors import (
    VECTOR_1,
    VECTOR_2,
    VECTOR_3,
    VECTOR_4,
    VECTOR_5,
)
from data.sharing_vectors import SHARING_VECTORS
from test_bip39 import BIP39_12W_ZERO

from codex32 import (
    CoreLightningSecret,
    MasterSeed,
    Share,
    parse_codex32,
    recover_secret,
)
from codex32.cli import cli


def _invoke(args: list[str], *strings: str):
    return CliRunner().invoke(cli, args, input="\n".join(strings) + "\n")


def _assert_private_master_key(vector: dict[str, str], *strings: str) -> None:
    result = _invoke(["xprv"], *strings)

    assert result.exit_code == 0
    assert result.output.strip().endswith(vector["xprv"])


def _assert_checksum(vector: dict[str, str]) -> None:
    string = parse_codex32(vector["secret_s"])
    checksum_length = 15 if len(string.payload_symbols) + 6 > 80 else 13
    worksheet_data = string.text[:-checksum_length]
    for args, input_value in (
        (["checksum"], worksheet_data),
        (["checksum"], worksheet_data[3:]),
        (["checksum", worksheet_data[:9]], worksheet_data[9:]),
        (["checksum", worksheet_data[3:9]], worksheet_data[9:]),
    ):
        result = _invoke(args, input_value)

        assert result.exit_code == 0
        assert "DANGER:" in result.output
        assert ("Enter the header first" in result.output) == (len(args) == 1)
        assert "permanent loss of funds" in result.output
        assert result.output.strip().endswith(vector["secret_s"].lower())


def test_bip93_vector_1_cli_unshared_secret():
    """Decode and checksum the official 128-bit unshared secret."""
    verified = _invoke(["verify"], VECTOR_1["secret_s"])

    assert verified.exit_code == 0
    assert "Valid codex32 secret with header: ms10tests" in verified.output
    assert "xpub" not in verified.output
    _assert_private_master_key(VECTOR_1, VECTOR_1["secret_s"])
    _assert_checksum(
        {
            **VECTOR_1,
            "share_idx": VECTOR_1["share_index"],
        }
    )


def test_bip93_vector_2_cli_derive_and_recover():
    """Derive D and recover the official 2-of-N secret and master key."""
    shares = (VECTOR_2["share_A"], VECTOR_2["share_C"])
    derived = _invoke(["share", "D"], *shares)
    secret = _invoke(["secret"], *shares)

    assert derived.exit_code == 0
    assert derived.output.strip().endswith(VECTOR_2["derived_D"])
    assert secret.exit_code == 0
    assert secret.output.strip().endswith(VECTOR_2["secret_S"])
    _assert_private_master_key(VECTOR_2, *shares)


def test_bip93_vector_3_cli_derive_and_recover():
    """Derive three shares and recover the official 3-of-N master key."""
    basis = (VECTOR_3["secret_s"], VECTOR_3["share_a"], VECTOR_3["share_c"])
    for index in "def":
        result = _invoke(["share", index], *basis)
        assert result.exit_code == 0
        assert result.output.strip().endswith(VECTOR_3[f"derived_{index}"])
    _assert_private_master_key(
        VECTOR_3,
        VECTOR_3["share_a"],
        VECTOR_3["share_c"],
        VECTOR_3["derived_d"],
    )


def test_bip93_vector_4_cli_256_bit_secret():
    """Recover the official 256-bit unshared master key."""
    vector = {
        **VECTOR_4,
        "k": "0",
        "identifier": "leet",
        "share_idx": "s",
        "payload": VECTOR_4["secret_s"][9:-13],
    }
    _assert_private_master_key(vector, vector["secret_s"])


def test_bip93_vector_5_cli_long_uppercase_secret():
    """Recover the official uppercase 512-bit unshared master key."""
    _assert_private_master_key(VECTOR_5, VECTOR_5["secret_s"])


def test_pretty_is_accepted_on_either_side_of_subcommands():
    """Create and checksum accept --pretty before or after the command."""
    share = parse_codex32(VECTOR_2["share_A"])
    checksum_length = 15 if len(share.payload_symbols) + 6 > 80 else 13
    cases = (
        (
            ["checksum", share.text[:9]],
            share.text[9:-checksum_length],
            ("Threshold Scheme:    2-of-N", "codex32 Identifier:  NAME"),
        ),
        (
            ["create", "--threshold", "0", "--identifier", "test"],
            bytes(range(16)).hex(),
            ("Threshold Scheme:    Unshared", "Master Fingerprint:"),
        ),
    )
    for command_args, input_value, expected_output in cases:
        for before_command in (True, False):
            args = (
                ["--pretty", *command_args]
                if before_command
                else [*command_args, "--pretty"]
            )
            result = CliRunner().invoke(
                cli,
                args,
                input=input_value + "\n",
            )

            assert result.exit_code == 0
            assert all(value in result.output for value in expected_output)


def test_checksum_rejects_noncanonical_initial_share_indices():
    """Checksum follows the Book's initial-share index rules."""
    for header in ("0testa", "2tests", "2testd"):
        result = _invoke(["checksum", header], "x" * 26)

        assert result.exit_code != 0
        assert "DANGER" not in result.output
        assert "Consult the Book and check the worksheet." in result.output

    protected_header = _invoke(["checksum"], "ms12tests" + "x" * 26)
    assert protected_header.exit_code != 0
    assert "Consult the Book and check the worksheet." in protected_header.output


def test_bip39_cli_verifies_and_recovers_but_does_not_derive():
    """BIP39 recovery is migration-only; share derivation stays API-only."""
    verified = _invoke(["verify"], BIP39_12W_ZERO)
    direct_secret = _invoke(["secret"], BIP39_12W_ZERO)
    assert verified.exit_code == 0
    assert "Valid codex32 secret with header: bip39_12w10tests" in verified.output
    assert direct_secret.exit_code == 0
    assert direct_secret.output.strip() == BIP39_12W_ZERO

    for profile in ("bip39_12w", "bip39_24w"):
        vector = SHARING_VECTORS[profile]
        shares = (vector["A"], vector["C"])
        recovered = _invoke(["secret"], *shares)
        derived = _invoke(["share", "d"], *shares)
        assert recovered.exit_code == 0
        assert recovered.output.strip() == vector["S"]
        assert derived.exit_code != 0
        assert "not exposed by the CLI" in derived.output

    wallet = _invoke(["xprv"], BIP39_12W_ZERO)
    assert wallet.exit_code != 0
    assert "must be 'ms'" in wallet.output


def _created_artifacts(result, prefix: str):
    return [
        parse_codex32(line)
        for line in result.output.splitlines()
        if line.lower().startswith(f"{prefix}1")
    ]


def test_create_defaults_to_five_randomly_indexed_ms_shares() -> None:
    result = _invoke(["create"])
    artifacts = _created_artifacts(result, "ms")
    assert result.exit_code == 0
    assert "Generated identifier:" in result.output
    assert len(artifacts) == 5
    assert all(isinstance(artifact, Share) for artifact in artifacts)
    assert all(artifact.header.threshold == 2 for artifact in artifacts)
    assert len({artifact.header.index for artifact in artifacts}) == 5
    assert all(artifact.text.islower() for artifact in artifacts)


def test_create_preserves_explicit_index_order() -> None:
    result = _invoke(["create", "--threshold", "3", "--indices", "7CaD"])
    artifacts = _created_artifacts(result, "ms")
    assert result.exit_code == 0
    assert "".join(artifact.header.index for artifact in artifacts) == "7cad"
    assert all(isinstance(artifact, Share) for artifact in artifacts)


def test_create_ms_unshared_length_and_raw_identifier_policy() -> None:
    fresh = _invoke(["create", "--threshold", "0", "--bytes", "47"])
    fresh_artifacts = _created_artifacts(fresh, "ms")
    assert fresh.exit_code == 0
    assert len(fresh_artifacts) == 1
    assert isinstance(fresh_artifacts[0], MasterSeed)
    assert len(fresh_artifacts[0].seed_bytes) == 47

    raw_seed = bytes(range(16))
    rejected = _invoke(["create", "--threshold", "0"], raw_seed.hex())
    accepted = _invoke(
        ["create", "--threshold", "0", "--identifier", "test"],
        raw_seed.hex(),
    )
    accepted_artifacts = _created_artifacts(accepted, "ms")
    assert rejected.exit_code != 0
    assert "Raw hexadecimal seeds require" in rejected.output
    assert accepted.exit_code == 0
    assert len(accepted_artifacts) == 1
    assert isinstance(accepted_artifacts[0], MasterSeed)
    assert accepted_artifacts[0].seed_bytes == raw_seed


def test_create_core_lightning_matrix() -> None:
    missing_identifier = _invoke(["create", "--prefix", "cl", "--threshold", "0"])
    wrong_length = _invoke(
        [
            "create",
            "--prefix",
            "cl",
            "--identifier",
            "peev",
            "--threshold",
            "0",
            "--bytes",
            "31",
        ]
    )
    unshared = _invoke(
        [
            "create",
            "--prefix",
            "cl",
            "--identifier",
            "peev",
            "--threshold",
            "0",
            "--bytes",
            "32",
        ]
    )
    shared = _invoke(
        [
            "create",
            "--prefix",
            "cl",
            "--identifier",
            "peev",
            "--threshold",
            "2",
            "--indices",
            "7a",
        ]
    )
    raw_secret = bytes(range(32))
    raw = _invoke(
        [
            "create",
            "--prefix",
            "cl",
            "--identifier",
            "peev",
            "--threshold",
            "0",
        ],
        raw_secret.hex(),
    )
    assert missing_identifier.exit_code != 0
    assert "requires an explicit" in missing_identifier.output
    assert wrong_length.exit_code != 0
    assert "exactly 32" in wrong_length.output
    unshared_artifacts = _created_artifacts(unshared, "cl")
    assert unshared.exit_code == 0
    assert len(unshared_artifacts) == 1
    assert isinstance(unshared_artifacts[0], CoreLightningSecret)
    raw_artifacts = _created_artifacts(raw, "cl")
    assert raw.exit_code == 0
    assert len(raw_artifacts) == 1
    assert isinstance(raw_artifacts[0], CoreLightningSecret)
    assert raw_artifacts[0].secret_bytes == raw_secret
    shared_artifacts = _created_artifacts(shared, "cl")
    assert shared.exit_code == 0
    assert "".join(item.header.index for item in shared_artifacts) == "7a"
    assert all(isinstance(item, Share) for item in shared_artifacts)


def test_create_splits_one_existing_ms_secret_with_a_derived_identifier() -> None:
    source = parse_codex32(VECTOR_4["secret_s"])
    assert isinstance(source, MasterSeed)
    result = _invoke(
        ["create", "--threshold", "2", "--indices", "7a"],
        source.text,
    )
    shares = _created_artifacts(result, "ms")
    assert result.exit_code == 0
    assert "Generated identifier:" in result.output
    assert len(shares) == 2
    assert all(isinstance(share, Share) for share in shares)
    assert "".join(share.header.index for share in shares) == "7a"
    recovered = recover_secret(shares)  # type: ignore[arg-type]
    assert recovered.seed_bytes == source.seed_bytes


def test_create_rejects_selector_conflicts_and_has_no_sorting_options() -> None:
    conflict = _invoke(
        ["create", "--threshold", "2", "--shares", "2", "--indices", "ac"]
    )
    unshared_selector = _invoke(["create", "--threshold", "0", "--shares", "1"])
    help_result = _invoke(["create", "--help"])
    assert conflict.exit_code != 0
    assert "mutually exclusive" in conflict.output
    assert unshared_selector.exit_code != 0
    assert "unshared secret" in unshared_selector.output
    assert help_result.exit_code == 0
    assert "--prefix" in help_result.output
    assert "--sort" not in help_result.output
    assert "--exclude-header" not in help_result.output


def test_create_source_header_collision_recommends_another_identifier() -> None:
    source = MasterSeed.from_seed(bytes(range(16)), identifier="test", threshold=2)
    result = _invoke(
        ["create", "--threshold", "2", "--indices", "ac", "--identifier", "test"],
        source.text,
    )
    assert result.exit_code != 0
    assert "set header '2test' is excluded" in result.output
    assert "another --identifier" in result.output


def test_create_rejects_partial_bases_bip39_and_profile_mismatches() -> None:
    partial = _invoke(
        ["create", "--threshold", "2", "--indices", "ac"], VECTOR_2["share_A"]
    )
    multiple = _invoke(
        ["create", "--threshold", "2", "--indices", "ac"],
        VECTOR_2["share_A"],
        VECTOR_2["share_C"],
    )
    bip39 = _invoke(["create", "--threshold", "2", "--indices", "ac"], BIP39_12W_ZERO)
    cl_secret = parse_codex32(SHARING_VECTORS["cl"]["S"])
    mismatch = _invoke(
        ["create", "--threshold", "2", "--indices", "ac"], cl_secret.text
    )
    for result in (partial, multiple):
        assert result.exit_code != 0
        assert "partial" in result.output.lower()
    assert bip39.exit_code != 0
    assert "BIP39 generation" in bip39.output
    assert mismatch.exit_code != 0
    assert "does not match --prefix" in mismatch.output


def test_correct_residue_uses_one_based_reverse_positions() -> None:
    result = _invoke(["correct", "--residue"], "2ppjkw73qdjvc")

    assert result.exit_code == 0
    assert "Add x to reverse position 38." in result.output


def test_correct_residue_is_profile_and_length_agnostic() -> None:
    result = _invoke(["correct", "--residue"], "vass072kvekqd")

    assert result.exit_code == 0
    assert "Add p to reverse position 38." in result.output


def test_correct_residue_erasure_positions_are_one_based() -> None:
    result = _invoke(
        ["correct", "--residue", "--erasure", "38"],
        "2ppjkw73qdjvc",
    )

    assert result.exit_code == 0
    assert "Add x to reverse position 38." in result.output


def test_correct_rejects_legacy_length_and_unscoped_erasure_options() -> None:
    old_length = _invoke(
        ["correct", "--length", "16", "--residue"],
        "2ppjkw73qdjvc",
    )
    unscoped = _invoke(["correct", "--erasure", "1"], VECTOR_1["secret_s"])

    assert old_length.exit_code != 0
    assert "No such option: --length" in old_length.output
    assert unscoped.exit_code != 0
    assert "--erasure requires --residue" in unscoped.output
