"""Hash bindings for the e1 manifests (slice e1). Research prototype - not for clinical use.

- dataset: the S1r tree sha, recomputed from the files (every listed file re-hashed, no unlisted file);
- split: sha256 of ``splits.json``;
- mapping: sha256 of ``e1_mapping_v1.json``;
- adapters: sha256 over ``eval/adapters/**/*.py`` (relative path + bytes, sorted).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .mapping import MAPPING_PATH

ADAPTERS_DIR = Path(__file__).resolve().parent


def sha256_file(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def dataset_tree_sha256(dataset: Path) -> tuple[str | None, list[str]]:
    """(recomputed tree sha, integrity errors). The tree sha is None when the manifest is unreadable."""
    ds = Path(dataset)
    try:
        man = json.loads((ds / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return None, [f"manifest.json unreadable: {e}"]
    errors = []
    files: dict[str, str] = {}
    for rel, listed in man["files"].items():
        p = ds / rel
        if not p.is_file():
            errors.append(f"missing file {rel}")
            continue
        files[rel] = sha256_file(p)
        if files[rel] != listed:
            errors.append(f"hash mismatch {rel}")
    for p in sorted(ds.rglob("*")):
        rel = p.relative_to(ds).as_posix()
        if p.is_file() and rel not in man["files"] and rel != "manifest.json" and not rel.endswith("audit_report.json"):
            errors.append(f"unlisted file {rel}")
    text = "".join(f"{k}\t{v}\n" for k, v in files.items())
    text += f"model_inputs_glob\t{man.get('model_inputs_glob')}\naudit_only_globs\t{json.dumps(man.get('audit_only_globs'))}\n"
    tree = hashlib.sha256(text.encode()).hexdigest()
    if tree != man.get("tree_sha256"):
        errors.append("tree_sha256 differs from manifest.json")
    return tree, errors


def split_sha256(dataset: Path) -> str:
    return sha256_file(Path(dataset) / "splits.json")


def mapping_sha256(path: Path | None = None) -> str:
    return sha256_file(path or MAPPING_PATH)


def adapters_sha256(root: Path | None = None) -> str:
    root = root or ADAPTERS_DIR
    h = hashlib.sha256()
    for p in sorted(root.rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        h.update(p.relative_to(root).as_posix().encode() + b"\0" + p.read_bytes() + b"\0")
    return h.hexdigest()


def current(dataset: Path) -> dict[str, str | None]:
    tree, errors = dataset_tree_sha256(dataset)
    return {
        "dataset_tree_sha256": tree if not errors else f"INVALID:{tree}",
        "split_sha256": split_sha256(dataset),
        "mapping_sha256": mapping_sha256(),
        "adapters_sha256": adapters_sha256(),
    }
