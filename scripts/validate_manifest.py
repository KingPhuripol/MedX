#!/usr/bin/env python3
"""Validate experiment manifests (schema + tier/approval semantics). Exit 0 only if all are valid.

    python3 scripts/validate_manifest.py research/manifests/*.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.manifest_validation import validate_path  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifests", nargs="+", type=Path)
    args = parser.parse_args(argv)
    failed = False
    for path in args.manifests:
        errors = validate_path(path)
        if errors:
            failed = True
            print(f"INVALID {path}")
            for error in errors:
                print(f"- {error}")
        else:
            print(f"VALID {path}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
