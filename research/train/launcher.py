"""Single entrypoint: python -m research.train --config <yaml> --manifest <json> [--dry-run] [--deepspeed]

Order of operations (each step exits non-zero before the next one on failure):
1. validate the manifest with the same code as scripts/validate_manifest.py;
2. check the manifest references this config (path + sha256 already verified) and stage;
3. enforce the tier: --dry-run needs a Tier-0 manifest, runs on CPU only and builds a tiny model
   (<= 2M parameters) from config; a Tier-0 manifest never runs on CUDA;
4. only then build the model, train, checkpoint, and write run metadata.

Slice s9 implements the dry run only. Tier >= 1 execution is out of scope; Tier 3/4 additionally
needs a dated human approval in docs/DECISIONS.md (checked by the validator).
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_ROOT = ROOT / "research" / "train" / "outputs"
MAX_DRY_RUN_PARAMS = 2_000_000

EXIT_INVALID = 2
EXIT_FAILED = 3
EXIT_INTERRUPTED = 130


class LaunchRefused(RuntimeError):
    """The launcher refuses to start (tier, device, config mismatch)."""


def _offline_cpu_env() -> None:
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"


def select_device(tier: int, requested: str):
    """Tier 0 is CPU only, whatever torch.cuda.is_available() says."""
    import torch

    if tier == 0:
        if requested != "cpu":
            raise LaunchRefused(f"tier 0 runs on CPU only; config requests device {requested!r}")
        return torch.device("cpu")
    raise LaunchRefused("slice s9 implements only the Tier-0 CPU dry run")


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=30, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def environment() -> dict[str, Any]:
    import peft
    import torch
    import transformers

    return {
        "python": sys.version.split()[0], "platform": platform.platform(), "torch": torch.__version__,
        "transformers": transformers.__version__, "peft": peft.__version__, "device": "cpu",
        "git_revision": _git("rev-parse", "HEAD").strip() or "unknown",
    }


def unique_run_dir(output_root: Path, experiment_id: str) -> Path:
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    for i in range(1000):
        path = Path(output_root) / (f"{experiment_id}-{stamp}" + ("" if i == 0 else f"-{i}"))
        try:
            path.mkdir(parents=True, exist_ok=False)
            return path
        except FileExistsError:
            continue
    raise LaunchRefused("could not create a unique run directory")


def _write_json(path: Path, obj: dict[str, Any]) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def preflight(config_path: Path, manifest_path: Path, dry_run: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate everything that does not need a model. Raises LaunchRefused with a specific message."""
    import yaml

    from research.manifest_validation import validate_path

    errors = validate_path(manifest_path)
    if errors:
        raise LaunchRefused("manifest invalid:\n- " + "\n- ".join(errors))
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    if (ROOT / manifest["code"]["config_path"]).resolve() != Path(config_path).resolve():
        raise LaunchRefused(f"--config {config_path} is not the config the manifest pins ({manifest['code']['config_path']})")
    cfg = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    if cfg["stage"] != manifest["model"]["stage"]:
        raise LaunchRefused(f"config stage {cfg['stage']} != manifest stage {manifest['model']['stage']}")
    if cfg["seed"] != manifest["training"]["seed"]:
        raise LaunchRefused(f"config seed {cfg['seed']} != manifest seed {manifest['training']['seed']}")
    if dry_run and manifest["run_tier"] != 0:
        raise LaunchRefused(f"--dry-run requires a Tier-0 manifest (manifest tier {manifest['run_tier']})")
    if dry_run and manifest["data"]["data_class"] != "synthetic":
        raise LaunchRefused("--dry-run accepts only data_class synthetic")
    return manifest, cfg


def run_dry(cfg: dict[str, Any], manifest: dict[str, Any], config_path: Path, run_dir: Path, argv: list[str]) -> int:
    import torch

    from research.manifest_validation import sha256_file
    from research.train import models
    from research.train.data import Collator, SyntheticCaseDataset
    from research.train.trainer import (CheckpointError, NonFiniteLossError, make_optimizer, policy_from_config,
                                        save_checkpoint, train_steps, trainable_named)

    device = select_device(manifest["run_tier"], cfg.get("device", "cpu"))
    model = models.build_model(cfg, dry_run=True).to(device)
    n_params = sum(p.numel() for p in model.parameters())
    if n_params > MAX_DRY_RUN_PARAMS:
        raise LaunchRefused(f"dry-run model has {n_params} parameters (> {MAX_DRY_RUN_PARAMS})")
    dry, tr = cfg["dry_run"], cfg["train"]
    ds_cfg = dry["dataset"]
    dataset = SyntheticCaseDataset(ds_cfg["n"], tuple(dry["volume_shape"]), dry["backbone"]["vocab_size"], cfg["seed"],
                                   prompt_len=ds_cfg["prompt_len"], report_len=ds_cfg["report_len"],
                                   target_len=ds_cfg["target_len"], modalities=tuple(ds_cfg["modalities"]))
    collator = Collator(policy_from_config(cfg), tr["seq_len"])
    optimizer = make_optimizer(model, tr["lr"])
    config_sha = sha256_file(config_path)
    meta: dict[str, Any] = {
        "experiment_id": manifest["experiment_id"], "run_tier": 0, "stage": cfg["stage"], "data_class": dataset.data_class,
        "command": [sys.executable, "-m", "research.train", *argv], "config_path": str(config_path),
        "config_sha256": config_sha, "seed": cfg["seed"], "environment": environment(),
        "parameters_total": n_params, "parameters_trainable": sum(p.numel() for _, p in trainable_named(model)),
        "max_steps": tr["max_steps"], "micro_batch": tr["micro_batch"], "seq_len": tr["seq_len"],
        "losses": [], "checkpoints": [], "status": "running",
        "note": "Synthetic Tier-0 dry run. Not a measurement of any candidate model. Research prototype, not for clinical use.",
    }
    if _git("status", "--porcelain").strip():
        (run_dir / "code.diff").write_text(_git("diff", "HEAD"), encoding="utf-8")
        meta["code_dirty"] = True
    ckpt_root = run_dir / "checkpoints"
    step, rc = 0, 0
    try:
        while step < tr["max_steps"]:
            meta["losses"] += train_steps(model, optimizer, dataset, collator, seed=cfg["seed"], start_step=step,
                                          end_step=step + 1, micro_batch=tr["micro_batch"])
            step += 1
            if step % tr["ckpt_every"] == 0 or step == tr["max_steps"]:
                path = save_checkpoint(model, optimizer, step, ckpt_root / f"step-{step:06d}", config_sha256=config_sha)
                meta["checkpoints"].append({"step": step, "path": str(path),
                                            "sha256": json.loads((path / "meta.json").read_text())["sha256"]})
        meta["status"] = "completed"
    except NonFiniteLossError as exc:
        meta.update(status="failed", error=str(exc))
        rc = EXIT_FAILED
    except CheckpointError as exc:
        meta.update(status="failed", error=str(exc))
        rc = EXIT_FAILED
    except KeyboardInterrupt:
        path = save_checkpoint(model, optimizer, step, ckpt_root / f"interrupted-step-{step:06d}", config_sha256=config_sha)
        meta["checkpoints"].append({"step": step, "path": str(path), "interrupted": True})
        meta["status"] = "stopped"
        rc = EXIT_INTERRUPTED
    meta["steps_completed"] = step
    _write_json(run_dir / "run.json", meta)
    print(json.dumps({"status": meta["status"], "run_dir": str(run_dir), "losses": meta["losses"]}))
    return rc


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(prog="python -m research.train", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true", help="Tier 0: CPU, tiny model, synthetic data")
    parser.add_argument("--deepspeed", action="store_true", help="real multi-GPU runs only (not in s9)")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args(argv)
    try:
        manifest, cfg = preflight(args.config, args.manifest, args.dry_run)
        if args.dry_run and args.deepspeed:
            raise LaunchRefused("--deepspeed is not allowed with --dry-run")
        if not args.dry_run:
            if args.deepspeed:
                try:
                    import deepspeed  # noqa: F401  (imported only on request; not a test dependency)
                except ImportError as exc:
                    raise LaunchRefused(f"--deepspeed requested but deepspeed is not installed: {exc}") from exc
            raise LaunchRefused("slice s9 implements only --dry-run; Tier >= 1 runs are not launched from this slice")
        select_device(manifest["run_tier"], cfg.get("device", "cpu"))  # refuse before any output or model
        _offline_cpu_env()
        run_dir = unique_run_dir(args.output_root, manifest["experiment_id"])
        return run_dry(cfg, manifest, args.config, run_dir, argv)
    except LaunchRefused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return EXIT_INVALID
