"""``python -m casegraph inspect <graph.json>``: print one line per node and every edge.

``python -m casegraph run-s1r --dataset <dir> --splits train,dev [--replay] [--no-cache] [--out summary.json]``:
compile, execute, replay and regenerate the Case Graph over S1r decision points (slice i2). Never the test split
outside the frozen evaluation run.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .export import import_graph, inspect_lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="casegraph")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_inspect = sub.add_parser("inspect", help="print the nodes and edges of an exported graph")
    p_inspect.add_argument("path", type=Path)
    p_run = sub.add_parser("run-s1r", help="compile/execute/replay the Case Graph over S1r case x T")
    p_run.add_argument("--dataset", type=Path, required=True)
    p_run.add_argument("--splits", default="train,dev")
    p_run.add_argument("--replay", action="store_true", help="replay every executed graph (always on)")
    p_run.add_argument("--no-cache", action="store_true", help="also re-execute into an empty Output Store")
    p_run.add_argument("--allow-test", action="store_true", help="only for the frozen evaluation run")
    p_run.add_argument("--out", type=Path, help="write the deterministic summary (without timing) here")
    args = parser.parse_args(argv)
    if args.cmd == "inspect":
        graph = import_graph(args.path.read_bytes())
        print("\n".join(inspect_lines(graph)))
        return 0
    import json

    from .run_s1r import run

    splits = [s for s in args.splits.split(",") if s]
    if "test" in splits and not args.allow_test:
        parser.error("the test split runs only inside the frozen evaluation run (--allow-test)")
    summary = run(args.dataset, splits, replay_check=True, no_cache=args.no_cache)
    text = json.dumps({k: v for k, v in summary.items() if k != "timing"}, ensure_ascii=False, indent=1,
                      sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    print(json.dumps({"timing": summary["timing"]}, ensure_ascii=False))
    return 0 if summary["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
