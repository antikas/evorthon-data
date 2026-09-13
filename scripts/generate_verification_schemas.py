#!/usr/bin/env python3
"""Generate or verify the checked-in verification contract projections."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from evorthon_data.verification.enforcement.schema import schema_projection_drift, write_schema_projections  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail if a committed projection is stale")
    parser.add_argument("--directory", type=Path, default=ROOT / "docs" / "verification" / "schemas")
    args = parser.parse_args()
    if args.check:
        drift = schema_projection_drift(args.directory)
        if drift:
            for path, reason in drift.items():
                print(f"{path}: {reason}")
            return 1
        return 0
    write_schema_projections(args.directory)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
