"""Exercise codex32 wallet integration against an isolated Bitcoin Core 32 main chain."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from codex32._bitcoin_core import BitcoinCore
from codex32.bip93 import parse_codex32
from codex32.profiles.ms32 import MasterSeed

# Frozen public BIP93 vector material; it has never controlled a funded wallet.
_SEED = "ms10testsxxxxxxxxxxxxxxxxxxxxxxxxxx4nzvca9cmczlw"


def _run(command: list[str], *, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, input=stdin, text=True, capture_output=True, check=False)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bitcoind", default="bitcoind")
    parser.add_argument("--bitcoin-cli", default="bitcoin-cli")
    arguments = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="codex32-core-main-") as temporary:
        datadir = Path(temporary)
        real_cli = shutil.which(arguments.bitcoin_cli)
        if real_cli is None:
            raise RuntimeError("bitcoin-cli was not found")
        daemon = subprocess.Popen(
            [
                arguments.bitcoind,
                "-chain=main",
                f"-datadir={datadir}",
                "-server=1",
                "-listen=0",
                "-discover=0",
                "-dnsseed=0",
                "-fixedseeds=0",
                "-connect=0",
                "-printtoconsole=0",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        base = [real_cli, "-chain=main", f"-datadir={datadir}", "-rpcconnect=127.0.0.1"]
        wrapper_directory = datadir / "wrapper"
        wrapper_directory.mkdir()
        wrapper = wrapper_directory / "bitcoin-cli"
        wrapper.write_text(
            f'#!/bin/sh\nexec {shlex.quote(real_cli)} {shlex.quote(f"-datadir={datadir}")} "$@"\n'
        )
        wrapper.chmod(0o700)
        old_path = os.environ.get("PATH", "")
        os.environ["PATH"] = str(wrapper_directory) + os.pathsep + old_path

        def rpc(*rpc_arguments: str, wallet: str | None = None, stdin: str | None = None) -> Any:
            command = [*base, "-rpcwait", "-rpcwaittimeout=30"]
            if wallet is not None:
                command.append(f"-rpcwallet={wallet}")
            if stdin is not None:
                command.append("-stdin")
            result = _run([*command, *rpc_arguments], stdin=stdin)
            if result.returncode:
                raise RuntimeError(result.stderr.strip())
            output = result.stdout.strip()
            if not output:
                return None
            try:
                return json.loads(output)
            except json.JSONDecodeError:
                return output

        try:
            blockchain = rpc("getblockchaininfo")
            network = rpc("getnetworkinfo")
            if not isinstance(blockchain, dict) or blockchain.get("chain") != "main":
                raise RuntimeError("Bitcoin Core did not start on mainnet")
            if not isinstance(network, dict) or network.get("version", 0) < 320000:
                raise RuntimeError("Bitcoin Core 32 or newer is required")

            rpc(
                "-named",
                "createwallet",
                "wallet_name=signer",
                "disable_private_keys=false",
                "blank=true",
                "descriptors=true",
            )
            passphrase = "main-smoke-only-passphrase"
            rpc("encryptwallet", wallet="signer", stdin=passphrase + "\n")
            unlocked = _run(
                [
                    *base,
                    "-rpcwallet=signer",
                    "-stdinwalletpassphrase",
                    "walletpassphrase",
                    "120",
                ],
                stdin=passphrase + "\n",
            )
            if unlocked.returncode:
                raise RuntimeError(unlocked.stderr.strip())

            secret = parse_codex32(_SEED)
            if not isinstance(secret, MasterSeed):
                raise TypeError("synthetic fixture was not a master seed")
            client = BitcoinCore.connect()
            answers = iter(("yes",))
            if (
                client.initialize(
                    secret,
                    lambda _prompt: next(answers),
                    lambda _message: None,
                    account=0,
                    timestamp=0,
                )
                != "signer"
            ):
                raise RuntimeError("automatic initialization selected the wrong wallet")
            if rpc("getwalletinfo", wallet="signer")["unlocked_until"] != 0:
                raise RuntimeError("automatic initialization did not relock the wallet")
            _verify_origins(rpc("listdescriptors", wallet="signer"), account=0)

            rpc(
                "-named",
                "createwallet",
                "wallet_name=account7",
                "disable_private_keys=false",
                "blank=true",
                "descriptors=true",
            )
            account_answers = iter(("yes",))
            if (
                client.initialize(
                    secret,
                    lambda _prompt: next(account_answers),
                    lambda _message: None,
                    account=7,
                    timestamp="now",
                )
                != "account7"
            ):
                raise RuntimeError("account-7 initialization selected the wrong wallet")
            _verify_origins(rpc("listdescriptors", wallet="account7"), account=7)

            print(
                json.dumps(
                    {
                        "bitcoin_core": network["subversion"],
                        "chain": blockchain["chain"],
                        "account": 7,
                        "status": "pass",
                    }
                )
            )
        finally:
            os.environ["PATH"] = old_path
            _run([*base, "stop"])
            try:
                daemon.wait(timeout=30)
            except subprocess.TimeoutExpired:
                daemon.terminate()
                daemon.wait(timeout=10)


def _verify_origins(listing: Any, *, account: int) -> None:
    if not isinstance(listing, dict):
        raise TypeError("Core did not return a descriptor listing")
    active = [item for item in listing.get("descriptors", ()) if item.get("active")]
    if len(active) != 8 or any("xprv" in item.get("desc", "") for item in active):
        raise RuntimeError("Core did not create eight public active descriptors")
    for purpose in (44, 49, 84, 86):
        if sum(f"/{purpose}h/0h/{account}h]" in item["desc"] for item in active) != 2:
            raise RuntimeError(f"Core did not create the expected BIP{purpose} account-{account} origins")


if __name__ == "__main__":
    main()
