"""Small command-line adapter for codex32-native workflows."""

import json
import sys

import click
from bip32 import BIP32

from codex32 import (
    Header,
    HeaderCollision,
    MasterSeed,
    Profile,
    Secret,
    Share,
    complete_checksum,
    core_descriptors,
    derive_share,
    generate_master_seed,
    master_xprv,
    multisig_account_xpub,
    parse_codex32,
    recover_secret,
    split_secret,
)
from codex32.correction import (
    _correct_fixed,
    _FixedCorrectionSuccess,
    correct_worksheet_residue,
)
from codex32.errors import CodexError, InvalidCorrectionInput

Artifact = Share | Secret
_MAX_INPUT = 9 * 1025


def _stdin(limit: int = _MAX_INPUT) -> str:
    value = sys.stdin.read(limit + 1)
    if len(value) > limit:
        raise click.BadParameter("Input is too long.", param_hint="stdin")
    return value


def _text(prompt: str, *, optional: bool = False) -> str:
    value = (
        click.prompt(prompt, default="", show_default=False)
        if sys.stdin.isatty()
        else _stdin()
    )
    value = "".join(value.split())
    if not value and not optional:
        raise click.BadParameter("Input must not be empty.", param_hint="stdin")
    return value


def _parse(value: str) -> Artifact:
    try:
        return parse_codex32(value)
    except CodexError as error:
        raise click.BadParameter(str(error), param_hint="stdin") from error


def _artifacts(*, sequential: bool) -> list[Artifact]:
    if not sys.stdin.isatty():
        tokens = _stdin().split()
        if not tokens:
            raise click.BadParameter("Input must not be empty.", param_hint="stdin")
        if len(tokens) > 9:
            raise click.BadParameter("At most nine artifacts are accepted.", param_hint="stdin")
        return [_parse(token) for token in tokens]

    first = _parse(click.prompt("codex32 string"))
    if not sequential or isinstance(first, Secret):
        return [first]
    prefix = f"{first.profile.value}1{first.header.threshold}{first.header.identifier}"
    result: list[Artifact] = [first]
    for number in range(2, first.header.threshold + 1):
        entered = click.prompt(
            f"share {number}/{first.header.threshold} after {prefix}"
        )
        result.append(_parse(entered if "1" in entered else prefix + entered))
    return result


def _secret(artifacts: list[Artifact]) -> Secret:
    if len(artifacts) == 1 and isinstance(artifacts[0], Secret):
        return artifacts[0]
    if not all(isinstance(artifact, Share) for artifact in artifacts):
        raise click.BadParameter("Recovery accepts ordinary shares only.", param_hint="stdin")
    try:
        return recover_secret([item for item in artifacts if isinstance(item, Share)])
    except CodexError as error:
        raise click.BadParameter(str(error), param_hint="stdin") from error


def _master_seed() -> MasterSeed:
    value = _secret(_artifacts(sequential=True))
    if not isinstance(value, MasterSeed):
        raise click.UsageError("Wallet commands accept only ms secrets.")
    return value


def _group(text: str) -> str:
    upper = text.upper()
    return " ".join(upper[start : start + 4] for start in range(0, len(upper), 4))


def _render(artifact: Artifact, pretty: bool) -> str:
    if not pretty:
        return artifact.text
    header = artifact.header
    lines = [
        f"Profile: {artifact.profile.value}",
        f"Threshold: {header.threshold}",
        f"Identifier: {header.identifier.upper()}",
        f"Index: {header.index.upper()}",
    ]
    if isinstance(artifact, MasterSeed):
        fingerprint = BIP32.from_seed(artifact.seed_bytes).get_fingerprint().hex()
        lines.append(f"Master fingerprint: {fingerprint.upper()}")
    lines.extend(("", _group(artifact.text)))
    return "\n".join(lines)


def _emit(artifact: Artifact, pretty: bool, *, err: bool = False) -> None:
    click.echo(_render(artifact, pretty), err=err)


@click.group()
@click.version_option(package_name="codex32", prog_name="codex32")
def cli() -> None:
    """Verify, share, recover, generate, and correct codex32 backups."""


@cli.command()
def verify() -> None:
    """Verify codex32 strings without deriving wallet keys."""
    for artifact in _artifacts(sequential=False):
        kind = "secret" if isinstance(artifact, Secret) else "share"
        click.echo(f"valid {artifact.profile.value} {kind}: {artifact.header}")


@cli.command(name="secret")
@click.option("--pretty", is_flag=True, help="Group output for transcription.")
def secret_command(pretty: bool) -> None:
    """Recover and print S from exactly k ordinary shares."""
    _emit(_secret(_artifacts(sequential=True)), pretty)


@cli.command(name="share")
@click.argument("index")
@click.option("--pretty", is_flag=True, help="Group output for transcription.")
def share_command(index: str, pretty: bool) -> None:
    """Derive one fresh ordinary share at INDEX."""
    artifacts = _artifacts(sequential=True)
    if artifacts[0].profile in (Profile.BIP39_12W, Profile.BIP39_24W):
        raise click.UsageError("BIP39 share derivation is API-only.")
    try:
        derived = derive_share(artifacts, index)
    except CodexError as error:
        raise click.ClickException(str(error)) from error
    _emit(derived, pretty)


def _creation_header(value: str | None) -> tuple[Profile, Header | None]:
    if value is None:
        return Profile.MS, None
    lowered = value.lower()
    if lowered != value and value.upper() != value:
        raise click.BadParameter("Header must use one case.", param_hint="HEADER")
    if "1" in lowered:
        hrp, header = lowered.rsplit("1", 1)
        try:
            profile = Profile(hrp)
        except ValueError as error:
            raise click.BadParameter("Unknown prefix.", param_hint="HEADER") from error
    else:
        profile, header = Profile.MS, lowered
    if len(header) != 5 or header[0] not in "023456789":
        raise click.BadParameter(
            "Header must be threshold plus four identifier symbols.",
            param_hint="HEADER",
        )
    try:
        return profile, Header(int(header[0]), header[1:], "s")
    except CodexError as error:
        raise click.BadParameter(str(error), param_hint="HEADER") from error


def _creation_source() -> bytes | Artifact | None:
    value = _text("raw hexadecimal seed or existing S", optional=True)
    if not value:
        return None
    if any(character.isspace() for character in value):
        raise click.BadParameter("Create accepts one source only.", param_hint="stdin")
    try:
        return bytes.fromhex(value)
    except ValueError:
        return _parse(value)


@cli.command()
@click.argument("header", required=False)
@click.option("--bytes", "byte_length", type=click.IntRange(16, 64))
@click.option("--shares", type=click.IntRange(2, 31))
@click.option("--indices")
@click.option("--pretty", is_flag=True, help="Group output for transcription.")
def create(
    header: str | None,
    byte_length: int | None,
    shares: int | None,
    indices: str | None,
    pretty: bool,
) -> None:
    """Create ms; HEADER is threshold+identifier, optionally prefixed by ms1."""
    profile, parsed_header = _creation_header(header)
    if profile is not Profile.MS:
        raise click.UsageError(
            "Fresh cl and BIP39 secrets are not generated by this reference CLI."
        )
    if shares is not None and indices is not None:
        raise click.UsageError("--shares and --indices are mutually exclusive.")
    source = _creation_source()
    if source is not None and byte_length is not None:
        raise click.UsageError("--bytes applies only to fresh generation.")
    if isinstance(source, (Share, Secret)) and not isinstance(source, MasterSeed):
        raise click.UsageError("Create accepts only raw bytes or one ms secret S.")
    if isinstance(source, bytes) and parsed_header is None:
        raise click.UsageError("Raw seeds require an explicit HEADER.")
    if isinstance(source, MasterSeed) and parsed_header is None:
        raise click.UsageError("Re-sharing requires a new explicit HEADER.")

    threshold = 0 if parsed_header is None else parsed_header.threshold
    identifier = None if parsed_header is None else parsed_header.identifier
    if threshold and shares is None and indices is None:
        shares = max(5, threshold)
    try:
        if isinstance(source, MasterSeed):
            if threshold == 0:
                raise click.UsageError("An existing secret is already complete.")
            assert identifier is not None
            secret, outputs = split_secret(
                source,
                threshold,
                identifier=identifier,
                share_count=shares,
                indices=indices,
            )
        else:
            secret, outputs = generate_master_seed(
                source,
                byte_length=byte_length,
                threshold=threshold,
                identifier=identifier,
                share_count=shares,
                indices=indices,
            )
    except HeaderCollision as error:
        raise click.ClickException(f"{error}; choose another HEADER.") from error
    except CodexError as error:
        raise click.ClickException(str(error)) from error
    for artifact in (secret,) if threshold == 0 else outputs:
        _emit(artifact, pretty)


def _unchecksummed(header: str | None, payload: str) -> tuple[Profile, str]:
    value = (header or "") + payload
    lowered = value.lower()
    if "1" in lowered:
        hrp = lowered.rsplit("1", 1)[0]
        try:
            profile = Profile(hrp)
        except ValueError as error:
            raise click.BadParameter("Unknown prefix.", param_hint="HEADER") from error
        text = value
    else:
        profile, text = Profile.MS, "ms1" + value
    if profile not in (Profile.MS, Profile.CL):
        raise click.UsageError("Checksum completion is limited to ms and cl.")
    body = text[text.rfind("1") + 1 :]
    allowed = (26, 52) if profile is Profile.MS else (52,)
    if len(body) < 6 or len(body) - 6 not in allowed:
        lengths = "128 or 256 bits" if profile is Profile.MS else "32 bytes"
        raise click.UsageError(f"{profile.value} checksum input must encode {lengths}.")
    return profile, text


@cli.command()
@click.argument("header", required=False)
@click.option("--pretty", is_flag=True, help="Group output for transcription.")
def checksum(header: str | None, pretty: bool) -> None:
    """Complete a published ms worksheet or fixed-size cl checksum."""
    _profile, text = _unchecksummed(header, _text("worksheet payload"))
    click.echo("DANGER: checksum completion does not create entropy.", err=True)
    try:
        artifact = complete_checksum(text)
    except CodexError as error:
        raise click.ClickException(str(error)) from error
    _emit(artifact, pretty)


@cli.command()
@click.option("--residue", is_flag=True, help="Correct a 13/15-symbol residue.")
@click.option("--erasure", "erasures", type=click.IntRange(min=1), multiple=True)
@click.option(
    "--prefix",
    type=click.Choice(("ms", "cl"), case_sensitive=False),
    default="ms",
    show_default=True,
)
@click.option("--pretty", is_flag=True, help="Group output for transcription.")
@click.pass_context
def correct(
    ctx: click.Context,
    residue: bool,
    erasures: tuple[int, ...],
    prefix: str,
    pretty: bool,
) -> None:
    """Suggest fixed-length substitutions/erasures or correct a residue."""
    value = _text("damaged string or residue")
    if residue:
        try:
            result = correct_worksheet_residue(
                value, erasure_indices=tuple(position - 1 for position in erasures)
            )
        except InvalidCorrectionInput as error:
            raise click.UsageError(str(error)) from error
        if result is None:
            raise click.ClickException("Unable to determine a unique correction.")
        if not result:
            click.echo("No errors found. Residue is correct.")
        for correction in result:
            click.echo(
                f"Add {correction.addend} to reverse position "
                f"{correction.reverse_index + 1}."
            )
        return
    if erasures:
        raise click.UsageError("--erasure requires --residue.")
    fixed = _correct_fixed(value, suspected_profile=Profile(prefix.lower()))
    if not isinstance(fixed, _FixedCorrectionSuccess):
        raise click.ClickException(fixed.detail)
    if not fixed.addends:
        click.echo("No errors found. String is valid.")
        return
    click.echo(
        "Warning: checksum-valid correction suggestion; verify against the backup.",
        err=True,
    )
    _emit(fixed.artifact, pretty, err=True)
    ctx.exit(1)


@cli.command()
@click.option("--testnet", is_flag=True)
def xprv(testnet: bool) -> None:
    """Print the BIP32 master extended private key for ms S."""
    click.echo(master_xprv(_master_seed(), testnet=testnet))


@cli.command()
@click.option("--account", type=click.IntRange(0, 2**31 - 1), default=0)
@click.option("--testnet", is_flag=True)
def xpub(account: int, testnet: bool) -> None:
    """Print a BIP48 native-SegWit coordinator account xpub."""
    click.echo(
        multisig_account_xpub(
            _master_seed(),
            account=account,
            testnet=testnet,
        )
    )


@cli.command()
@click.option("--account", type=click.IntRange(0, 2**31 - 1), default=0)
@click.option("--timestamp", type=click.IntRange(min=0), default=0)
@click.option("--testnet", is_flag=True)
@click.option("--private", is_flag=True, help="Include the root xprv.")
def descriptors(account: int, timestamp: int, testnet: bool, private: bool) -> None:
    """Print fixed Bitcoin Core single-key descriptor records as JSON."""
    if private:
        click.echo(
            "Warning: private descriptors contain the root xprv and grant root authority.",
            err=True,
        )
    records = core_descriptors(
        _master_seed(),
        account=account,
        testnet=testnet,
        private=private,
        timestamp=timestamp,
    )
    click.echo(json.dumps(records, indent=2))
