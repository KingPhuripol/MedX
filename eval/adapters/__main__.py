"""CLI: ``python -m eval.adapters {manifests,run,summary,render-mapping}`` (slice e1).

Exit codes: 0 ok; 2 refused (hash mismatch, ledger, unfrozen test, existing outputs: nothing written);
3 invalid input. Research prototype - not for clinical use.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from eval.errors import RunRefused
from eval.manifest import ManifestError

from . import pipeline, protocol
from .inputs import InputIntegrityError
from .mapping import BANNER, MAPPING_MD_PATH, render_md


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m eval.adapters", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("manifests", help="write the 4 e1 manifests from gold + train-only comparators (no system run)")
    r = sub.add_parser("run", help="run one split end to end (S3 -> S4 -> S8r runner -> e1 summary)")
    r.add_argument("--split", required=True, choices=pipeline.SPLITS)
    r.add_argument("--ledger-dir", default=None, help="default: $EVAL_LEDGER_DIR or eval/ledger")
    s = sub.add_parser("summary", help="rebuild e1_summary.{json,md} from the per-split outputs")
    for a in (m, r, s):
        a.add_argument("--dataset", type=Path, default=pipeline.DEFAULT_DATASET)
        a.add_argument("--manifest-dir", type=Path, default=protocol.MANIFEST_DIR)
        a.add_argument("--out-root", type=Path, default=pipeline.OUT_ROOT)
    m.add_argument("--n-boot", type=int, default=protocol.N_BOOT)
    sub.add_parser("render-mapping", help="write e1_mapping_v1.md from e1_mapping_v1.json")
    args = p.parse_args(argv)
    try:
        if args.cmd == "manifests":
            for path in pipeline.make_manifests(args.dataset, args.manifest_dir, args.n_boot):
                print(f"wrote {path}")
        elif args.cmd == "run":
            out = pipeline.run_split(args.split, args.dataset, args.manifest_dir, args.out_root, args.ledger_dir)
            print(f"{BANNER}\nwrote {out} and {out.parent}/e1_summary.{{json,md}}")
        elif args.cmd == "summary":
            pipeline.write_summary(args.out_root)
            print(f"wrote {args.out_root}/e1_summary.{{json,md}}")
        else:
            MAPPING_MD_PATH.write_text(render_md(), encoding="utf-8")
            print(f"wrote {MAPPING_MD_PATH}")
    except RunRefused as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 2
    except (ManifestError, InputIntegrityError, ValueError, OSError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
