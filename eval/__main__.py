"""CLI: ``python -m eval {freeze,run,demo}``. Research prototype - not for clinical use."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .manifest import Ledger, ManifestError, freeze
from .metrics import MissingPredictionError
from .runner import RunRefused, run

EXAMPLES = Path(__file__).resolve().parent / "examples"
EXIT_REFUSED = 2
EXIT_INVALID = 3


def _ledger(args: argparse.Namespace) -> Ledger:
    return Ledger(args.ledger_dir)


def cmd_freeze(args: argparse.Namespace) -> int:
    entry = freeze(args.manifest, _ledger(args))
    print(json.dumps(entry, sort_keys=True))
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    res = run(args.manifest, args.predictions, args.out, args.comparator, _ledger(args))
    print(f"wrote results.json/.md/.html to {args.out} ({len(res['rows'])} metric rows)")
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    """Freeze the toy test manifest into an isolated ledger under OUT, then run it with comparators."""
    out = Path(args.out)
    ledger = Ledger(out / "ledger")
    manifest = EXAMPLES / "toy_manifest_test.json"
    freeze(manifest, ledger)
    res = run(manifest, EXAMPLES / "toy_predictions.jsonl", out, EXAMPLES / "toy_comparator.jsonl", ledger)
    items = sorted({r["item"] for r in res["rows"]})
    print(f"demo: {len(res['rows'])} metric rows across {len(items)} Table 3.2 items -> {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m eval", description=__doc__)
    p.add_argument("--ledger-dir", default=None, help="ledger directory (default: $EVAL_LEDGER_DIR or eval/ledger)")
    sub = p.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("freeze", help="validate a manifest and append its hash to the frozen ledger")
    f.add_argument("manifest")
    f.set_defaults(fn=cmd_freeze)
    r = sub.add_parser("run", help="score predictions against a manifest")
    r.add_argument("--manifest", required=True)
    r.add_argument("--predictions", required=True)
    r.add_argument("--comparator", default=None)
    r.add_argument("--out", required=True)
    r.set_defaults(fn=cmd_run)
    d = sub.add_parser("demo", help="toy end-to-end report (synthetic data)")
    d.add_argument("--out", required=True)
    d.set_defaults(fn=cmd_demo)
    args = p.parse_args(argv)
    try:
        return args.fn(args)
    except RunRefused as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return EXIT_REFUSED
    except (ManifestError, MissingPredictionError, ValueError, OSError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return EXIT_INVALID


if __name__ == "__main__":
    sys.exit(main())
