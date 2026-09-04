"""Exercise codex32 wallet integration against an isolated Bitcoin Core regtest."""

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
    parser.add_argument("--codex32", default="codex32", help="installed codex32 executable")
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
        base = [real_cli, "-regtest", f"-datadir={datadir}"]

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
            for name, private_keys in (("miner", True), ("watch", False), ("signer", True), ("now", False)):
                rpc(
                    "-named",
                    "createwallet",
                    f"wallet_name={name}",
                    f"disable_private_keys={'false' if private_keys else 'true'}",
                    f"blank={'false' if name == 'miner' else 'true'}",
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
            public = core_descriptors(secret, testnet=True, timestamp=0)
            private = core_descriptors(secret, testnet=True, private=True, timestamp=0)
            recent = core_descriptors(secret, testnet=True, timestamp="now")
            for records, wallet in ((public, "watch"), (private, "signer"), (recent, "now")):
                imported = rpc("importdescriptors", wallet=wallet, stdin=json.dumps(records) + "\n")
                if not all(item["success"] for item in imported):
                    raise RuntimeError(f"descriptor import failed for {wallet}")

            rpc(
                "-named",
                "createwallet",
                "wallet_name=fresh",
                "disable_private_keys=false",
                "blank=true",
                "descriptors=true",
            )
            rpc("encryptwallet", wallet="fresh", stdin=passphrase + "\n")
            fresh_unlocked = _run(
                [*base, "-rpcwallet=fresh", "-stdinwalletpassphrase", "walletpassphrase", "120"],
                stdin=passphrase + "\n",
            )
            if fresh_unlocked.returncode:
                raise RuntimeError(fresh_unlocked.stderr.strip())
            wrapper_directory = datadir / "wrapper"
            wrapper_directory.mkdir()
            wrapper = wrapper_directory / "bitcoin-cli"
            wrapper.write_text(
                f'#!/bin/sh\nexec {shlex.quote(real_cli)} {shlex.quote(f"-datadir={datadir}")} "$@"\n'
            )
            wrapper.chmod(0o700)
            os.environ["PATH"] = str(wrapper_directory) + os.pathsep + os.environ.get("PATH", "")
            client = BitcoinCore.connect()
            answers = iter(("yes",))
            if client.initialize(secret, lambda _prompt: next(answers), lambda _message: None) != "fresh":
                raise RuntimeError("automatic initialization selected the wrong wallet")
            if rpc("getwalletinfo", wallet="fresh")["unlocked_until"] != 0:
                raise RuntimeError("automatic initialization did not relock the wallet")

            accepted = rpc("listdescriptors", wallet="fresh")["descriptors"]
            public_fields = ("desc", "timestamp", "active", "internal", "range", "next_index")
            accepted_public = [{key: item[key] for key in public_fields if key in item} for item in accepted]
            rpc(
                "-named",
                "createwallet",
                "wallet_name=fresh-watch",
                "disable_private_keys=true",
                "blank=true",
                "descriptors=true",
            )
            imported = rpc(
                "importdescriptors", wallet="fresh-watch", stdin=json.dumps(accepted_public) + "\n"
            )
            if not all(item["success"] for item in imported):
                raise RuntimeError("accepted public descriptor reimport failed")

            watch_address = rpc("getnewaddress", wallet="watch")
            signer_address = rpc("getnewaddress", wallet="signer")
            if watch_address != signer_address:
                raise RuntimeError("watch-only and private descriptors derived different addresses")
            fresh_address = rpc("getnewaddress", wallet="fresh")
            if fresh_address != rpc("getnewaddress", wallet="fresh-watch"):
                raise RuntimeError("automatic private/public wallets derived different addresses")
            rpc("sendtoaddress", watch_address, "1", wallet="miner")
            rpc("generatetoaddress", "1", miner_address)
            if rpc("getbalance", wallet="watch") != 1 or rpc("getbalance", wallet="signer") != 1:
                raise RuntimeError("imported wallets did not discover the funded output")
            if rpc("getbalance", wallet="fresh") != 1 or rpc("getbalance", wallet="fresh-watch") != 1:
                raise RuntimeError("automatic private/public wallets did not discover the funded output")

            denied = _run(
                [*base, "-rpcwallet=watch", "sendtoaddress", miner_address, "0.1"],
            )
            if denied.returncode == 0:
                raise RuntimeError("watch-only wallet unexpectedly signed a transaction")
            txid = rpc("sendtoaddress", miner_address, "0.5", wallet="signer")
            rpc("generatetoaddress", "1", miner_address)
            if rpc("gettransaction", txid, wallet="signer")["confirmations"] < 1:
                raise RuntimeError("signed transaction was not broadcast and confirmed")
            rpc("sendtoaddress", rpc("getnewaddress", wallet="fresh"), "1", wallet="miner")
            rpc("generatetoaddress", "1", miner_address)
            fresh_unlocked = _run(
                [*base, "-rpcwallet=fresh", "-stdinwalletpassphrase", "walletpassphrase", "120"],
                stdin=passphrase + "\n",
            )
            if fresh_unlocked.returncode:
                raise RuntimeError(fresh_unlocked.stderr.strip())
            fresh_txid = rpc("sendtoaddress", miner_address, "0.5", wallet="fresh")
            rpc("generatetoaddress", "1", miner_address)
            if rpc("gettransaction", fresh_txid, wallet="fresh")["confirmations"] < 1:
                raise RuntimeError("automatically initialized wallet did not spend")
            rpc("walletlock", wallet="fresh")
            rpc("walletlock", wallet="signer")
            if rpc("getwalletinfo", wallet="signer")["unlocked_until"] != 0:
                raise RuntimeError("private restore wallet did not relock")

            mainnet = core_descriptors(secret, timestamp=0)
            multisig = _run([arguments.codex32, "wallet", "multisig-xpub", "--testnet"], stdin=_SEED + "\n")
            if "xpub" not in json.dumps(mainnet) or "tpub" not in json.dumps(public):
                raise RuntimeError("mainnet/testnet descriptor versions were not separated")
            if multisig.returncode or "/48h/1h/0h/2h]tpub" not in multisig.stdout:
                raise RuntimeError("BIP48 coordinator export was malformed")
            print(json.dumps({"bitcoin_core": rpc("getnetworkinfo")["subversion"], "status": "pass"}))
        finally:
            _run([*base, "stop"])
            try:
                daemon.wait(timeout=30)
            except subprocess.TimeoutExpired:
                daemon.terminate()
                daemon.wait(timeout=10)


if __name__ == "__main__":
    main()
