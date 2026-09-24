"""Install a built distribution in isolation and run the installed-package verifier."""

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
    parser.add_argument("--artifact", type=Path)
    arguments = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if arguments.wheel is not None and arguments.artifact is not None:
        parser.error("choose only one of --wheel or --artifact")
    requested = arguments.artifact or arguments.wheel
    if requested is None:
        wheels = tuple((root / "dist").glob("codex32-*.whl"))
        if len(wheels) != 1:
            raise RuntimeError(f"expected exactly one codex32 wheel, found {len(wheels)}")
        artifact = wheels[0]
    else:
        artifact = requested.resolve()
        if not artifact.is_file():
            raise FileNotFoundError(artifact)
        if artifact.suffix != ".whl" and not artifact.name.endswith(".tar.gz"):
            raise ValueError("artifact must be a wheel or .tar.gz source distribution")

    with tempfile.TemporaryDirectory(prefix="codex32-wheel-") as temporary:
        environment = Path(temporary)
        venv.EnvBuilder(with_pip=True).create(environment)
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        clean_env = os.environ.copy()
        clean_env.pop("PYTHONPATH", None)
        clean_env["PYTHONNOUSERSITE"] = "1"
        if artifact.name.endswith(".tar.gz"):
            subprocess.run(
                [
                    str(python),
                    "-m",
                    "pip",
                    "install",
                    "--disable-pip-version-check",
                    "--require-hashes",
                    "-r",
                    str(root / "requirements" / "cli-build-dependencies.txt"),
                ],
                check=True,
                env=clean_env,
            )
        subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--no-deps",
                "--no-build-isolation",
                str(artifact),
            ],
            check=True,
            env=clean_env,
        )
        subprocess.run(
            [str(python), str(root / "tools" / "verify_installed_wheel.py")],
            check=True,
            cwd=temporary,
            env=clean_env,
        )


if __name__ == "__main__":
    main()
