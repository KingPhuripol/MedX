"""CLI: ``python -m data_factory generate --seed N --out DIR [--splits-only] [--replace] [--heldout]`` and ``audit --dataset DIR``."""

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def allowed_roots() -> list[str]:
    return [os.path.realpath(REPO / "data"), os.path.realpath(tempfile.gettempdir()), os.path.realpath("/tmp")]


def check_out(out: Path) -> str | None:
    """Return the resolved OUT if it is a strict descendant of an allowed root, else None."""
    real = os.path.realpath(out)
    ok = any(real != root and os.path.commonpath([real, root]) == root for root in allowed_roots())
    return real if ok else None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="data_factory")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate")
    g.add_argument("--seed", type=int, required=True)
    g.add_argument("--out", type=Path, required=True)
    g.add_argument("--splits-only", action="store_true")
    g.add_argument("--replace", action="store_true", help="delete an existing factory dataset at OUT first")
    g.add_argument("--heldout", action="store_true", help="s6r held-out set: 72 patients SYNH-/SYNHE-, test split only")
    a = sub.add_parser("audit", help="schema, gold separation, identifier scan, manifest hashes, snapshot times")
    a.add_argument("--dataset", type=Path, required=True)
    args = ap.parse_args(argv)
    if args.cmd == "generate":
        real = check_out(args.out)  # before anything is created or deleted
        if real is None:
            print(f"refusing OUT={args.out} (resolves to {os.path.realpath(args.out)}): it must be strictly inside "
                  f"one of {allowed_roots()}", file=sys.stderr)
            return 2
        if args.replace and os.path.lexists(real):
            if not os.path.isfile(os.path.join(real, "splits.json")):
                print(f"refusing to replace {real}: not a factory dataset (no splits.json)", file=sys.stderr)
                return 2
            shutil.rmtree(real)
        from .generate import generate

        m = generate(args.seed, Path(real), splits_only=args.splits_only, heldout=args.heldout)
        print(json.dumps({"out": str(args.out), "tree_sha256": m["tree_sha256"] if m else None,
                          "counts": m["counts"] if m else None}, ensure_ascii=False, indent=2))
        return 0
    from .audit import run_audit

    report = run_audit(args.dataset)
    print(json.dumps({k: v for k, v in report.items() if k != "errors"} | {"errors": report["errors"][:20]},
                     ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
