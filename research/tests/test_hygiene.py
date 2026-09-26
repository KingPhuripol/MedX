"""S9-A19: no weights, volumes or large files are tracked; run outputs are ignored."""

from __future__ import annotations

import subprocess

from .conftest import REPO_ROOT

WEIGHT_SUFFIXES = (".safetensors", ".bin", ".pt", ".pth", ".ckpt", ".gguf", ".nii", ".nii.gz", ".dcm", ".npz")
MAX_BYTES = 5 * 1024 * 1024


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, timeout=30, check=True).stdout


def test_no_large_or_weight_files():
    files = [p for p in _git("ls-files", "--cached", "--others", "--exclude-standard", "-z").split("\0") if p]
    assert files
    weights = [f for f in files if f.lower().endswith(WEIGHT_SUFFIXES)]
    large = [f for f in files if (REPO_ROOT / f).is_file() and (REPO_ROOT / f).stat().st_size > MAX_BYTES]
    assert weights == [] and large == []
    gitignore = (REPO_ROOT / ".gitignore").read_text().splitlines()
    assert "research/**/outputs/" in gitignore and "checkpoints/" in gitignore
    for probe in ("research/train/outputs/run-1/checkpoints/step-000002/trainable.pt",
                  "research/train/checkpoints/x.pt"):
        assert _git("check-ignore", probe).strip() == probe
