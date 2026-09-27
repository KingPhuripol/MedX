"""``python -m casegraph inspect <graph.json>``: print one line per node and every edge."""

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
    args = parser.parse_args(argv)
    graph = import_graph(args.path.read_bytes())
    print("\n".join(inspect_lines(graph)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
