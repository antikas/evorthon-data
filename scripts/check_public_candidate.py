#!/usr/bin/env python3
"""One public command: establish tools, validate, build, install and inspect."""
# evorthon-implements: EVD-README-035
from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from evorthon_data.public_boundary import (
    FIXTURE_TREE,
    candidate_files,
    checkout_rewrite_findings,
    fixture_gate_findings,
    scan_candidate,
    validate_inventory,
    write_inventory,
)
from evorthon_data.runtime_adapters import validate_runtime_adapters


def run(command: list[str], *, cwd: pathlib.Path, env: dict[str, str]) -> None:
    result = subprocess.run(command, cwd=cwd, text=True, env=env, check=False)
    if result.returncode:
        raise SystemExit(result.returncode)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scan-only", action="store_true")
    parser.add_argument("--finalize", action="store_true")
    parser.add_argument("--source-commit", default="unknown")
    parser.add_argument("--allow-provisional", action="store_true")
    args = parser.parse_args()
    required = ("README.md", "LICENSE", "PUBLIC-INVENTORY.json", "PUBLIC-LEAKAGE-POLICY.json", "pyproject.toml")
    missing = [name for name in required if not (ROOT / name).exists()]
    if missing:
        raise SystemExit("public candidate missing: " + ", ".join(missing))
    if not (ROOT / "LICENSE").read_text(encoding="utf-8").startswith("MIT License"):
        raise SystemExit("public candidate license is not MIT")
    adapter_failures = validate_runtime_adapters(ROOT)
    if adapter_failures:
        raise SystemExit("broken runtime adapter:\n" + "\n".join(adapter_failures))
    findings = scan_candidate(ROOT)
    if findings:
        raise SystemExit("public leakage detected:\n" + "\n".join(findings))
    # A candidate holds only what a projection took, so every fixture it holds
    # is a projected one and is read against the same declaration the export
    # gated on.
    held = sorted(path.relative_to(ROOT).as_posix() for path in candidate_files(ROOT / FIXTURE_TREE))
    gate = fixture_gate_findings(ROOT, held)
    if gate:
        raise SystemExit("fixture declaration gate:\n" + "\n".join(gate))
    # A candidate declares one attribute over all of its own files, so a text
    # file carrying a carriage return holds bytes no clone reproduces. It is
    # read before the inventory is written or validated, so an inventory is
    # never finalized over bytes a checkout would rewrite.
    rewritten = checkout_rewrite_findings(ROOT)
    if rewritten:
        raise SystemExit("public candidate holds bytes a checkout would rewrite:\n" + "\n".join(rewritten))
    if args.finalize:
        write_inventory(ROOT, args.source_commit, provisional=False)
    try:
        validate_inventory(ROOT, require_final=not args.allow_provisional)
    except ValueError as refusal:
        raise SystemExit(f"public candidate refused: {refusal}") from None
    if args.scan_only:
        print(json.dumps({"status": "green", "tree": "final" if args.finalize else "checked"}, sort_keys=True))
        return 0
    uv = shutil.which("uv")
    if not uv:
        raise SystemExit("the public check requires uv; install it before running this command")
    with tempfile.TemporaryDirectory(prefix="evorthon-public-") as temporary:
        environment = pathlib.Path(temporary) / "venv"
        command_env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PIP_DISABLE_PIP_VERSION_CHECK": "1"}
        run([uv, "venv", "--native-tls", "--seed", "--python", "3.11", str(environment)], cwd=ROOT, env=command_env)
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        env = command_env
        run([uv, "pip", "install", "--native-tls", "--python", str(python), ".[test]"], cwd=ROOT, env=env)
        run([str(python), "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=ROOT, env=env)
        wheel_dir = pathlib.Path(temporary) / "wheel"; wheel_dir.mkdir()
        run([uv, "build", "--native-tls", "--wheel", "--out-dir", str(wheel_dir)], cwd=ROOT, env=env)
        wheel = next(wheel_dir.glob("evorthon_data-*.whl"))
        with zipfile.ZipFile(wheel) as archive:
            metadata = next(name for name in archive.namelist() if name.endswith("METADATA"))
            licence = next(name for name in archive.namelist() if name.endswith("LICENSE"))
            if "License: MIT" not in archive.read(metadata).decode("utf-8") or not archive.read(licence).decode("utf-8").startswith("MIT License"):
                raise SystemExit("wheel does not carry the MIT metadata and licence payload")
        install = pathlib.Path(temporary) / "install"
        run([uv, "venv", "--native-tls", "--seed", "--python", "3.11", str(install)], cwd=ROOT, env=env)
        install_python = install / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        run([uv, "pip", "install", "--native-tls", "--python", str(install_python), "--no-deps", str(wheel)], cwd=ROOT, env=env)
        command_path = shutil.which("evorthon-data", path=str(install_python.parent))
        if not command_path:
            raise SystemExit("installed public entry point is not discoverable")
        run([command_path, "diagnose"], cwd=ROOT, env={**env, "PATH": str(install_python.parent) + os.pathsep + os.environ.get("PATH", "")})
    print("public candidate self-check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
