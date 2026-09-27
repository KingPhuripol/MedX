"""CLI: ``python -m eval_i2 {manifests,run,summary}`` (slice i2).

Exit codes: 0 ok; 2 refused (hash mismatch, ledger, unfrozen test, existing outputs: nothing written);
3 invalid input. System Evaluation on synthetic data — not clinical performance.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from eval.errors import RunRefused
from eval.manifest import ManifestError

from . import pipeline, protocol
from .summary import BANNER


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m eval_i2", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("manifests", help="write i2-cg-vs-sp-{dev,test}-v1 from gold memberships (no system run)")
    r = sub.add_parser("run", help="run one split: both arms -> S8r runner -> i2 summary")
    r.add_argument("--split", required=True, choices=protocol.SPLITS)
    r.add_argument("--ledger-dir", default=None, help="default: $EVAL_LEDGER_DIR or eval/ledger")
    s = sub.add_parser("summary", help="rebuild i2_summary.{json,md} from the per-split outputs")
    for a in (m, r, s):
        a.add_argument("--dataset", type=Path, default=pipeline.DEFAULT_DATASET)
        a.add_argument("--manifest-dir", type=Path, default=protocol.MANIFEST_DIR)
        a.add_argument("--out-root", type=Path, default=pipeline.OUT_ROOT)
    m.add_argument("--n-boot", type=int, default=protocol.N_BOOT)
    args = p.parse_args(argv)
    try:
        if args.cmd == "manifests":
            for path in pipeline.make_manifests(args.dataset, args.manifest_dir, args.n_boot):
                print(f"wrote {path}")
        elif args.cmd == "run":
            out = pipeline.run_split(args.split, args.dataset, args.manifest_dir, args.out_root, args.ledger_dir)
            print(f"{BANNER}\nwrote {out} and {out.parent}/i2_summary.{{json,md}}")
        else:
            pipeline.write_summary(args.out_root)
            print(f"wrote {args.out_root}/i2_summary.{{json,md}}")
    except RunRefused as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 2
    except (ManifestError, ValueError, OSError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
