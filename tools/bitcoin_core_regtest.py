"""Exercise codex32 wallet integration against an isolated Bitcoin Core 32 regtest."""

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
from codex32.wallet import core_descriptors

# Frozen public BIP93 vector material; it has never controlled a funded wallet.
_SEED = "ms10testsxxxxxxxxxxxxxxxxxxxxxxxxxx4nzvca9cmczlw"


def _run(command: list[str], *, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, input=stdin, text=True, capture_output=True, check=False)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bitcoind", default="bitcoind")
    parser.add_argument("--bitcoin-cli", default="bitcoin-cli")
    arguments = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="codex32-core-") as temporary:
        datadir = Path(temporary)
        real_cli = shutil.which(arguments.bitcoin_cli)
        if real_cli is None:
            raise RuntimeError("bitcoin-cli was not found")
        daemon = subprocess.Popen(
            [
                arguments.bitcoind,
                "-regtest",
                f"-datadir={datadir}",
                "-server=1",
                "-listen=0",
                "-discover=0",
                "-fallbackfee=0.00001",
                "-printtoconsole=0",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        base = [real_cli, "-regtest", f"-datadir={datadir}", "-rpcconnect=127.0.0.1"]
        wrapper_directory = datadir / "wrapper"
        wrapper_directory.mkdir()
        wrapper = wrapper_directory / "bitcoin-cli"
        wrapper.write_text(
            f'#!/bin/sh\nexec {shlex.quote(real_cli)} {shlex.quote(f"-datadir={datadir}")} "$@"\n'
        )
        wrapper.chmod(0o700)
        os.environ["PATH"] = str(wrapper_directory) + os.pathsep + os.environ.get("PATH", "")

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
            rpc("getblockchaininfo")
            network = rpc("getnetworkinfo")
            if not isinstance(network, dict) or network.get("version", 0) < 320000:
                raise RuntimeError("Bitcoin Core 32 or newer is required")

            rpc(
                "-named",
                "createwallet",
                "wallet_name=miner",
                "disable_private_keys=false",
                "blank=false",
                "descriptors=true",
            )
            rpc(
                "-named",
                "createwallet",
                "wallet_name=signer",
                "disable_private_keys=false",
                "blank=true",
                "descriptors=true",
            )

            passphrase = "regtest-only-passphrase"
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

            miner_address = rpc("getnewaddress", wallet="miner")
            rpc("generatetoaddress", "101", miner_address)

            secret = parse_codex32(_SEED)
            if not isinstance(secret, MasterSeed):
                raise TypeError("synthetic fixture was not a master seed")
            client = BitcoinCore.connect()
            expected_fingerprint = client.fingerprint(secret)
            answers = iter(("yes",))
            if (
                client.initialize(
                    secret,
                    lambda _prompt: next(answers),
                    lambda _message: None,
                    expected_fingerprint=expected_fingerprint,
                    account=0,
                    timestamp=0,
                )
                != "signer"
            ):
                raise RuntimeError("automatic initialization selected the wrong wallet")
            if rpc("getwalletinfo", wallet="signer")["unlocked_until"] != 0:
                raise RuntimeError("automatic initialization did not relock the wallet")

            active = [
                item for item in rpc("listdescriptors", wallet="signer")["descriptors"] if item["active"]
            ]
            if len(active) != 8 or any("tprv" in item["desc"] for item in active):
                raise RuntimeError("Core did not create eight public active descriptors")
            for purpose in (44, 49, 84, 86):
                if sum(f"/{purpose}h/1h/0h]" in item["desc"] for item in active) != 2:
                    raise RuntimeError(f"Core did not create the expected BIP{purpose} account-0 origins")

            signer_address = rpc("getnewaddress", wallet="signer")
            rpc("sendtoaddress", signer_address, "1", wallet="miner")
            rpc("generatetoaddress", "1", miner_address)

            rpc(
                "-named",
                "createwallet",
                "wallet_name=restore",
                "disable_private_keys=false",
                "blank=true",
                "descriptors=true",
            )
            restore_answers = iter(("yes",))
            if (
                client.initialize(
                    secret,
                    lambda _prompt: next(restore_answers),
                    lambda _message: None,
                    expected_fingerprint=expected_fingerprint,
                    account=0,
                    timestamp=0,
                )
                != "restore"
            ):
                raise RuntimeError("recovery initialization selected the wrong wallet")
            recovered_address = rpc("getaddressinfo", signer_address, wallet="restore")
            if not isinstance(recovered_address, dict) or recovered_address.get("ismine") is not True:
                raise RuntimeError("recovered wallet did not recognize the funded signer address")
            if rpc("getbalance", wallet="restore") != 1:
                raise RuntimeError("recovery rescan did not find the funded output")

            spend = rpc("sendtoaddress", miner_address, "0.5", wallet="restore")
            rpc("generatetoaddress", "1", miner_address)
            if rpc("gettransaction", spend, wallet="restore")["confirmations"] < 1:
                raise RuntimeError("recovered wallet did not sign and broadcast")

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
                    expected_fingerprint=expected_fingerprint,
                    account=7,
                    timestamp="now",
                )
                != "account7"
            ):
                raise RuntimeError("account-7 initialization selected the wrong wallet")
            account_active = [
                item for item in rpc("listdescriptors", wallet="account7")["descriptors"] if item["active"]
            ]
            for purpose in (44, 49, 84, 86):
                if sum(f"/{purpose}h/1h/7h]" in item["desc"] for item in account_active) != 2:
                    raise RuntimeError(f"Core did not create the expected BIP{purpose} account-7 origins")

            main_private = core_descriptors(secret, private=True, timestamp=0)
            test_private = core_descriptors(secret, testnet=True, private=True, timestamp=0)
            if "xprv" not in json.dumps(main_private) or "tprv" not in json.dumps(test_private):
                raise RuntimeError("mainnet/test-network root serialization was not separated")

            print(json.dumps({"bitcoin_core": network["subversion"], "status": "pass"}))
        finally:
            _run([*base, "stop"])
            try:
                daemon.wait(timeout=30)
            except subprocess.TimeoutExpired:
                daemon.terminate()
                daemon.wait(timeout=10)


if __name__ == "__main__":
    main()
