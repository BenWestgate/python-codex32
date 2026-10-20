"""Install the built wheel without dependencies and run the installed-wheel verifier."""

from __future__ import annotations

import argparse
import os
import subprocess
import tempfile
import venv
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wheel", type=Path)
    arguments = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if arguments.wheel is None:
        wheels = tuple((root / "dist").glob("codex32-*.whl"))
        if len(wheels) != 1:
            raise RuntimeError(f"expected exactly one codex32 wheel, found {len(wheels)}")
        wheel = wheels[0]
    else:
        wheel = arguments.wheel.resolve()
        if not wheel.is_file():
            raise FileNotFoundError(wheel)

    with tempfile.TemporaryDirectory(prefix="codex32-wheel-") as temporary:
        environment = Path(temporary)
        venv.EnvBuilder(with_pip=True).create(environment)
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--no-deps",
                str(wheel),
            ],
            check=True,
        )
        subprocess.run(
            [str(python), str(root / "tools" / "verify_installed_wheel.py")],
            check=True,
            cwd=temporary,
        )


if __name__ == "__main__":
    main()
