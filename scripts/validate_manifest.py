#!/usr/bin/env python3
"""Validate experiment manifests (schema + tier/approval semantics). Exit 0 only if all are valid.

    python3 scripts/validate_manifest.py research/manifests/*.json
    python3 scripts/validate_manifest.py --approval-sha research/manifests/<id>.json

`--approval-sha` prints the manifest content hash (canonical JSON without approval/status/result)
that a human writes into the `manifest_sha256` field of a ```approval record in docs/DECISIONS.md.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.manifest_validation import approval_sha256, loads_strict, validate_path  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("manifests", nargs="+", type=Path)
    parser.add_argument("--approval-sha", action="store_true",
                        help="print the approval hash of each manifest instead of validating")
    args = parser.parse_args(argv)
    if args.approval_sha:
        for path in args.manifests:
            try:
                manifest = loads_strict(path.read_text(encoding="utf-8"))
                if not isinstance(manifest, dict):
                    raise ValueError("manifest is not a JSON object")
            except (OSError, ValueError) as exc:
                print(f"cannot read manifest {path}: {exc}", file=sys.stderr)
                return 1
            digest = approval_sha256(manifest)
            print(digest if len(args.manifests) == 1 else f"{digest}  {path}")
        return 0
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
