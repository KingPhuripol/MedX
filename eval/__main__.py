"""CLI: ``python -m eval {freeze,run,demo,ledger}``. Research prototype - not for clinical use.

Exit codes: 0 ok; 2 refused (RunRefused / LedgerIntegrityError: nothing written); 3 invalid input
(invalid manifest, NaN/Infinity, missing prediction, unreadable file).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .errors import RunRefused
from .manifest import Ledger, ManifestError, freeze
from .metrics import MissingPredictionError
from .runner import run

EXAMPLES = Path(__file__).resolve().parent / "examples"
EXIT_REFUSED = 2
EXIT_INVALID = 3

LEDGER_POLICY = """\
ledger commit policy (see eval/ledger/README.md):
  - ledgers are appended on one integration branch only (main), by a single writer;
  - order: `freeze` -> commit "eval(ledger): freeze <evaluation_id>" (with the manifest),
    then `run` -> commit "eval(ledger): run <evaluation_id>";
  - commits touching eval/ledger/ are never amended, rebased, squashed or force-pushed;
  - a ledger merge conflict is resolved by redoing the other branch's freeze/run on top of main,
    never by editing lines;
  - real data (mimic/hospital) on the test split requires both ledgers committed with no
    uncommitted lines; a remote history rewrite is not detectable locally (residual risk)."""


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
    """Freeze the toy test manifest into an isolated ledger under OUT (initialised if absent), then run it."""
    out = Path(args.out)
    ledger = Ledger(out / "ledger")
    if not ledger.frozen_path.exists() and not ledger.runs_path.exists():
        ledger.init()
    manifest = EXAMPLES / "toy_manifest_test.json"
    freeze(manifest, ledger)
    res = run(manifest, EXAMPLES / "toy_predictions.jsonl", out, EXAMPLES / "toy_comparator.jsonl", ledger)
    items = sorted({r["item"] for r in res["rows"]})
    print(f"demo: {len(res['rows'])} metric rows across {len(items)} Table 3.2 items -> {out}")
    return 0


def cmd_ledger_init(args: argparse.Namespace) -> int:
    lg = _ledger(args)
    lg.init()
    print(f"initialised genesis ledgers in {lg.dir}")
    return 0


def cmd_ledger_verify(args: argparse.Namespace) -> int:
    lg = _ledger(args)
    summary = lg.verify(git_history=args.git_history)
    print(f"ledger OK ({lg.dir}): " + json.dumps(summary, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m eval", description=__doc__, epilog=LEDGER_POLICY,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
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
    lg = sub.add_parser("ledger", help="verify or initialise the hash-chained ledgers", epilog=LEDGER_POLICY,
                        formatter_class=argparse.RawDescriptionHelpFormatter)
    lsub = lg.add_subparsers(dest="ledger_cmd", required=True)
    li = lsub.add_parser("init", help="write genesis ledgers (only on an absent path without git history)",
                         epilog=LEDGER_POLICY, formatter_class=argparse.RawDescriptionHelpFormatter)
    li.add_argument("--ledger-dir", default=argparse.SUPPRESS)
    li.set_defaults(fn=cmd_ledger_init)
    lv = lsub.add_parser("verify", help="verify the hash chain and the git anchor", epilog=LEDGER_POLICY,
                         formatter_class=argparse.RawDescriptionHelpFormatter)
    lv.add_argument("--ledger-dir", default=argparse.SUPPRESS)
    lv.add_argument("--git-history", action="store_true",
                    help="also check that every committed version is a byte prefix of the next")
    lv.set_defaults(fn=cmd_ledger_verify)
    args = p.parse_args(argv)
    try:
        return args.fn(args)
    except ManifestError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return EXIT_INVALID
    except RunRefused as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return EXIT_REFUSED
    except (MissingPredictionError, ValueError, OSError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return EXIT_INVALID


if __name__ == "__main__":
    sys.exit(main())
