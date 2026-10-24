"""Check CoreEntropy against an isolated Bitcoin Core 32 regtest node on Linux.

Covers repeated draws, interruption by real signals while each Core call is in flight (in this process and
through the CLI in a terminal), the warning when no RAM folder exists, and removal of every temporary wallet.
Only throwaway regtest keys are drawn; nothing is printed but the checks.

Run from a checkout; the CLI checks need codex32 installed:

    python -m pip install --require-hashes -r requirements/cli-build-dependencies.txt
    python -m pip install --no-build-isolation --no-deps .
    PYTHONPATH=src python tools/bitcoin_core_entropy.py --bitcoind BIN/bitcoind --bitcoin-cli BIN/bitcoin-cli
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import pty
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import patch

from codex32._bitcoin_core import BitcoinCore, BitcoinCoreError, CoreEntropy

_CREATE = "import sys; from codex32.cli import ms_main; sys.exit(ms_main(['create', '2', '--indices', 'ac']))"
_results: list[bool] = []


def _check(name: str, ok: bool, detail: object = "") -> None:
    _results.append(ok)
    print(("PASS  " if ok else "FAIL  ") + name + (f" ({detail})" if detail and not ok else ""), flush=True)


def _signal_on(mark: Path, pid: int, number: int) -> Callable[[], bool]:
    """Send ``number`` to ``pid`` once ``mark`` appears; the returned call says whether it was sent."""
    sent: list[bool] = []

    def wait() -> None:
        deadline = time.monotonic() + 60
        while not mark.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        if mark.exists():
            os.kill(pid, number)
            sent.append(True)

    thread = threading.Thread(target=wait, daemon=True)
    thread.start()
    return lambda: thread.join() or bool(sent)


def _run_cli(mark: Path, number: int) -> tuple[int, str, bool]:
    """Run ``ms32 create`` in a terminal, send ``number`` mid-draw, and return its exit code and output."""
    pid, terminal = pty.fork()
    if pid == 0:
        os.execv(sys.executable, [sys.executable, "-c", _CREATE])
    sent, output = _signal_on(mark, pid, number), bytearray()

    def drain() -> None:
        while True:
            try:
                chunk = os.read(terminal, 4096)
            except OSError:
                return
            if not chunk:
                return
            output.extend(chunk)

    reader = threading.Thread(target=drain, daemon=True)
    reader.start()
    status = os.waitpid(pid, 0)[1]
    reader.join(5)
    os.close(terminal)
    return os.waitstatus_to_exitcode(status), output.decode(errors="replace"), sent()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bitcoind", default="bitcoind")
    parser.add_argument("--bitcoin-cli", default="bitcoin-cli")
    arguments = parser.parse_args()
    cli = shutil.which(arguments.bitcoin_cli)
    if cli is None:
        raise RuntimeError("bitcoin-cli was not found")

    with tempfile.TemporaryDirectory(prefix="codex32-entropy-") as temporary:
        root = Path(temporary)
        datadir, mark, wrapper_dir, disk = root / "core", root / "mark", root / "wrapper", root / "disk"
        for folder in (datadir, wrapper_dir, disk):
            folder.mkdir()
        daemon = subprocess.Popen(
            [arguments.bitcoind, "-regtest", f"-datadir={datadir}", "-listen=0", "-printtoconsole=0"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        # The wrapper holds the first call to $HOLD_METHOD just before or after Core runs it ($HOLD_WHEN) and
        # touches the mark, so a signal lands while that call is in flight.
        wrapper = wrapper_dir / "bitcoin-cli"
        wrapper.write_text(
            "#!/bin/sh\n"
            f'case " $* " in *" ${{HOLD_METHOD:-none}} "*) [ -e {mark} ] || hold=1;; esac\n'
            f'if [ -n "$hold" ] && [ "$HOLD_WHEN" = before ]; then touch {mark}; sleep 5; fi\n'
            f'{shlex.quote(cli)} {shlex.quote(f"-datadir={datadir}")} "$@"; status=$?\n'
            f'if [ -n "$hold" ] && [ "$HOLD_WHEN" = after ]; then touch {mark}; sleep 5; fi\n'
            "exit $status\n"
        )
        wrapper.chmod(0o700)
        os.environ["PATH"] = f"{wrapper_dir}{os.pathsep}{os.environ['PATH']}"

        def rpc(*rpc_arguments: str, wallet: str | None = None) -> Any:
            command = [cli, "-regtest", f"-datadir={datadir}", "-rpcwait", "-rpcwaittimeout=30"]
            command += [f"-rpcwallet={wallet}"] if wallet else []
            result = subprocess.run([*command, *rpc_arguments], capture_output=True, text=True, check=False)
            if result.returncode:
                raise RuntimeError(result.stderr.strip())
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError:
                return result.stdout.strip()

        def leftovers() -> list[str]:
            loaded = [name for name in rpc("listwallets") if "codex32-" in name]
            return sorted(glob.glob("/dev/shm/codex32-*")) + sorted(glob.glob(f"{disk}/*")) + loaded

        def hold(method: str = "", when: str = "") -> None:
            mark.unlink(missing_ok=True)
            os.environ.update(HOLD_METHOD=method or "none", HOLD_WHEN=when)

        try:
            rpc("getblockchaininfo")
            core = BitcoinCore.connect()
            passphrases, created, locked, methods = list[str](), list[str](), list[bool](), list[str]()
            core_rpc = BitcoinCore._rpc

            def watched(self: BitcoinCore, *rpc_arguments: str, **options: Any) -> Any:
                methods.append(rpc_arguments[rpc_arguments[0] == "-named"])
                if methods[-1] == "createwallet":
                    created.append(rpc_arguments[2].removeprefix("wallet_name="))
                if methods[-1] == "unloadwallet":
                    locked.append(rpc("getwalletinfo", wallet=rpc_arguments[1])["unlocked_until"] == 0)
                return core_rpc(self, *rpc_arguments, **options)

            def entropy(tell: Callable[[str], None] = lambda _message: None) -> CoreEntropy:
                passphrases.append((source := CoreEntropy(core, tell))._passphrase)
                return source

            # Repeated draws, each from its own encrypted RAM wallet that is gone before the bytes return.
            told, draws, removed, sizes = list[str](), list[bytes](), list[bool](), (16, 16, 32, 64, 1, 16)
            source = entropy(told.append)
            with patch.object(BitcoinCore, "_rpc", watched):
                for size in sizes:
                    draws.append(source(size))
                    gone = not os.path.exists(os.path.dirname(created[-1]))
                    removed.append(gone and created[-1] not in rpc("listwallets"))
            _check("draws return the requested lengths", [len(data) for data in draws] == list(sizes))
            _check("each draw used a new wallet in /dev/shm", len(set(created)) == len(sizes))
            _check("each wallet was locked before it was unloaded", len(locked) == len(sizes) and all(locked))
            _check("each wallet was removed before its bytes returned", all(removed))
            _check("a 64-byte draw took two keys", methods.count("addhdkey") == len(sizes) + 1)
            _check("all draws differ, with no disk warning", len(set(draws)) == len(sizes) and not told)

            # A real SIGINT in this process while each Core call is in flight.
            for method, when in (
                ("createwallet", "after"),
                ("walletpassphrase", "before"),
                ("addhdkey", "after"),
                ("gethdkeys", "before"),
                ("walletlock", "after"),
                ("unloadwallet", "after"),
                ("unloadwallet", "before"),
            ):
                hold(method, when)
                sent, outcome = _signal_on(mark, os.getpid(), signal.SIGINT), "returned"
                try:
                    entropy()(16)
                except (KeyboardInterrupt, BitcoinCoreError) as error:
                    outcome = str(error) or type(error).__name__
                hold()
                if (method, when) != ("unloadwallet", "before"):
                    left = leftovers()
                    ok = outcome == "KeyboardInterrupt" and not left
                    _check(f"SIGINT {when} {method} leaves nothing", sent() and ok, f"{outcome}; {left}")
                    continue
                # Core never ran unloadwallet, so its wallet stays loaded and creation must stop and say so.
                stuck = [name for name in rpc("listwallets") if "codex32-" in name]
                ok = (
                    "Restart Core to unload it" in outcome
                    and "creation stopped" in outcome
                    and len(stuck) == 1
                )
                _check(
                    "SIGINT before unloadwallet stops creation and says to restart Core",
                    sent() and ok,
                    outcome,
                )
                for name in stuck:
                    rpc("unloadwallet", name)
                _check("that wallet's deleted folder stays deleted once Core unloads it", not leftovers())

            # The real CLI in a terminal, stopped mid-draw by each signal it turns into Ctrl-C.
            for number, method, when in (
                (signal.SIGTERM, "addhdkey", "before"),
                (signal.SIGHUP, "gethdkeys", "after"),
                (signal.SIGINT, "createwallet", "after"),
            ):
                hold(method, when)
                code, output, sent_signal = _run_cli(mark, number)
                hold()
                left = leftovers()
                ok = (
                    code == 130
                    and "Mark every card from this incomplete creation void" in output
                    and not left
                )
                name = signal.Signals(number).name
                _check(
                    f"CLI {name} {when} {method} voids the cards and leaves nothing",
                    sent_signal and ok,
                    f"exit {code}; {left}; {output[-300:]!r}",
                )

            # Without a RAM folder: one warning naming the disk folder, and each wallet deleted from disk.
            told, emptied, created[:] = [], [], []
            source, isdir = entropy(told.append), os.path.isdir
            with (
                patch("os.path.isdir", lambda path: path != "/dev/shm" and isdir(path)),
                patch.object(tempfile, "tempdir", str(disk)),
                patch.object(BitcoinCore, "_rpc", watched),
            ):
                for _ in range(3):
                    source(16)
                    emptied.append(not os.listdir(disk))
            on_disk = len(created) == 3 and all(wallet.startswith(f"{disk}/codex32-") for wallet in created)
            _check("without /dev/shm the wallets were made on disk", on_disk)
            warned = len(told) == 1 and f"on disk in {disk}" in told[0] and "TMPDIR" in told[0]
            _check("without /dev/shm one warning names the folder and the fix", warned, told)
            _check("without /dev/shm each wallet was deleted before its bytes returned", all(emptied))

            log = (datadir / "regtest" / "debug.log").read_text(errors="replace")
            secret = "tprv" in log or any(passphrase in log for passphrase in passphrases)
            _check(
                "Core's debug.log names the wallets but holds no key or passphrase",
                "codex32-" in log and not secret,
            )
            _check("nothing is left anywhere", not leftovers(), leftovers())
        finally:
            subprocess.run([cli, "-regtest", f"-datadir={datadir}", "stop"], capture_output=True, check=False)
            daemon.wait(60)
    print(f"{sum(_results)} of {len(_results)} checks passed")
    return 0 if all(_results) else 1


if __name__ == "__main__":
    sys.exit(main())
