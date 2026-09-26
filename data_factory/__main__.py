"""CLI: ``python -m data_factory generate --seed N --out DIR [--splits-only]`` and ``audit --dataset DIR``."""

import argparse
import json
import sys
from pathlib import Path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="data_factory")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate")
    g.add_argument("--seed", type=int, required=True)
    g.add_argument("--out", type=Path, required=True)
    g.add_argument("--splits-only", action="store_true")
    a = sub.add_parser("audit", help="schema, gold separation, identifier scan, manifest hashes")
    a.add_argument("--dataset", type=Path, required=True)
    args = ap.parse_args(argv)
    if args.cmd == "generate":
        from .generate import generate

        m = generate(args.seed, args.out, splits_only=args.splits_only)
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
