"""Exercise installed codex32 wallet exports against an isolated Bitcoin Core regtest."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

# Frozen public BIP93 vector material; it has never controlled a funded wallet.
_SEED = "ms10testsxxxxxxxxxxxxxxxxxxxxxxxxxx4nzvca9cmczlw"


def _run(command: list[str], *, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, input=stdin, text=True, capture_output=True, check=False)


def _exports(executable: str, *, private: bool = False, now: bool = False) -> list[dict[str, Any]]:
    mode = "restore" if private else "watch-only"
    command = [executable, "wallet", "bitcoin-core", mode, "--testnet"]
    if now:
        command.extend(("--timestamp", "now"))
    result = _run(command, stdin=_SEED + "\n")
    if result.returncode:
        raise RuntimeError(result.stderr.strip())
    return json.loads(result.stdout)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--codex32", default="codex32", help="installed codex32 executable")
    parser.add_argument("--bitcoind", default="bitcoind")
    parser.add_argument("--bitcoin-cli", default="bitcoin-cli")
    arguments = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="codex32-core-") as temporary:
        datadir = Path(temporary)
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
        base = [arguments.bitcoin_cli, "-regtest", f"-datadir={datadir}"]

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

            passphrase = "gate4-regtest-only"
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

            public = _exports(arguments.codex32)
            private = _exports(arguments.codex32, private=True)
            recent = _exports(arguments.codex32, now=True)
            for records, wallet in ((public, "watch"), (private, "signer"), (recent, "now")):
                imported = rpc("importdescriptors", wallet=wallet, stdin=json.dumps(records) + "\n")
                if not all(item["success"] for item in imported):
                    raise RuntimeError(f"descriptor import failed for {wallet}")

            watch_address = rpc("getnewaddress", wallet="watch")
            signer_address = rpc("getnewaddress", wallet="signer")
            if watch_address != signer_address:
                raise RuntimeError("watch-only and private descriptors derived different addresses")
            rpc("sendtoaddress", watch_address, "1", wallet="miner")
            rpc("generatetoaddress", "1", miner_address)
            if rpc("getbalance", wallet="watch") != 1 or rpc("getbalance", wallet="signer") != 1:
                raise RuntimeError("imported wallets did not discover the funded output")

            denied = _run(
                [*base, "-rpcwallet=watch", "sendtoaddress", miner_address, "0.1"],
            )
            if denied.returncode == 0:
                raise RuntimeError("watch-only wallet unexpectedly signed a transaction")
            txid = rpc("sendtoaddress", miner_address, "0.5", wallet="signer")
            rpc("generatetoaddress", "1", miner_address)
            if rpc("gettransaction", txid, wallet="signer")["confirmations"] < 1:
                raise RuntimeError("signed transaction was not broadcast and confirmed")
            rpc("walletlock", wallet="signer")
            if rpc("getwalletinfo", wallet="signer")["unlocked_until"] != 0:
                raise RuntimeError("private restore wallet did not relock")

            mainnet = _run([arguments.codex32, "wallet", "bitcoin-core", "watch-only"], stdin=_SEED + "\n")
            multisig = _run([arguments.codex32, "wallet", "multisig-xpub", "--testnet"], stdin=_SEED + "\n")
            if mainnet.returncode or "xpub" not in mainnet.stdout or "tpub" not in json.dumps(public):
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
