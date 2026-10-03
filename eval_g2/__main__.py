"""CLI: ``python -m eval_g2 {manifest,run}``. Exit 2 refused, 3 invalid input. Research prototype - not for clinical use."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from eval.errors import RunRefused
from eval.manifest import ManifestError, check_manifest

from . import pipeline, protocol as P


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m eval_g2", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("manifest", help="write <id>.json + <id>.protocol.json (status DRAFT); no system run")
    r = sub.add_parser("run", help="run one split (test only when FROZEN + frozen in the ledger)")
    for a in (m, r):
        a.add_argument("--dataset", type=Path, required=True)
        a.add_argument("--split", required=True, choices=("dev", "test"))
        a.add_argument("--manifest-dir", type=Path, default=P.MANIFEST_DIR)
    m.add_argument("--n-boot", type=int, default=P.N_BOOT)
    r.add_argument("--out-root", type=Path, default=pipeline.OUT_ROOT)
    r.add_argument("--ledger-dir", default=None, help="default: $EVAL_LEDGER_DIR or eval/ledger")
    args = p.parse_args(argv)
    mp = args.manifest_dir / f"{P.EVALUATION_ID}.json"
    pp = args.manifest_dir / f"{P.EVALUATION_ID}.protocol.json"
    try:
        if args.cmd == "manifest":
            proto = P.build_protocol(args.dataset, args.split)
            man = P.build_manifest(args.dataset, args.split, proto, args.n_boot)
            check_manifest(man)
            P.write_json(pp, proto)
            P.write_json(mp, man)
            print(f"wrote {mp}\nwrote {pp}")
        else:
            out = pipeline.run_split(args.split, args.dataset, mp, pp, args.out_root, args.ledger_dir)
            print(f"{pipeline.BANNER}\nwrote {out}")
    except RunRefused as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 2
    except (ManifestError, ValueError, OSError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
