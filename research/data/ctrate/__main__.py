"""python -m research.data.ctrate {plan-download,prepare,verify,build,audit}"""

from __future__ import annotations

import argparse
import json
import sys

from . import access
from .audit import run_audit
from .build import build
from .split import DEFAULT_SEED, DEV_FRACTION


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m research.data.ctrate", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("plan-download")
    p = sub.add_parser("prepare")
    p.add_argument("--target", default="data/raw/ctrate")
    p.add_argument("--approval")
    p.add_argument("--accept-terms", action="store_true")
    p.add_argument("--execute", action="store_true")
    p = sub.add_parser("verify")
    p.add_argument("root")
    p.add_argument("--volumes", action="store_true")
    p = sub.add_parser("build")
    p.add_argument("--raw", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p.add_argument("--dev-fraction", type=float, default=DEV_FRACTION)
    p.add_argument("--unseal-test", action="store_true", help="final evaluation only")
    p = sub.add_parser("audit")
    p.add_argument("build_dir")
    a = ap.parse_args(argv)
    if a.cmd == "plan-download":
        print(access.plan_download())
        return 0
    if a.cmd == "prepare":
        try:
            out = access.prepare(a.target, approval=a.approval, accept_terms=a.accept_terms, execute=a.execute)
        except access.RefusedError as exc:
            print(f"REFUSED: {exc}", file=sys.stderr)
            return 2
        print("\n".join(out) if isinstance(out, list) and not a.execute else " ".join(out))
        return 0
    if a.cmd == "verify":
        rep = access.verify(a.root, volumes=a.volumes)
        print(json.dumps({k: v for k, v in rep.items() if k != "files"}, indent=2))
        return 0 if rep["status"] == "PASS" else 1
    if a.cmd == "build":
        m = build(a.raw, a.out, seed=a.seed, dev_fraction=a.dev_fraction, unseal_test=a.unseal_test)
        print(json.dumps({"tree_sha256": m["tree_sha256"], "counts": m["counts"], "unsealed_test": m["unsealed_test"]},
                         indent=2, sort_keys=True))
        return 0
    rep = run_audit(a.build_dir)
    print(json.dumps(rep, indent=2, ensure_ascii=False))
    return 0 if rep["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
