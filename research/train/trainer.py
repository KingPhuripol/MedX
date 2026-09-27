"""Training loop and trainable-only checkpointing with bit-identical CPU resume.

Data order and collator randomness are pure functions of (seed, step), so resuming from a checkpoint
needs only the trainable tensors, the optimizer state, the RNG state and the step.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from pathlib import Path
from typing import Any

import torch
from torch import nn

from research.train.data import Collator, ModalityPolicy

CKPT_FILE = "trainable.pt"
META_FILE = "meta.json"


class NonFiniteLossError(RuntimeError):
    """Stop rule: NaN/Inf loss. The run stops; diagnostics are preserved by the caller."""


class CheckpointError(RuntimeError):
    """Corrupt checkpoint, or a checkpoint that does not match the frozen base it is loaded into."""


def trainable_named(model: nn.Module) -> list[tuple[str, nn.Parameter]]:
    return sorted(((n, p) for n, p in model.named_parameters() if p.requires_grad), key=lambda x: x[0])


def frozen_fingerprint(model: nn.Module) -> str:
    """sha256 over frozen parameters: resume must use the exact same base weights."""
    h = hashlib.sha256()
    for name, p in sorted(model.named_parameters(), key=lambda x: x[0]):
        if not p.requires_grad:
            h.update(name.encode())
            h.update(p.detach().contiguous().cpu().numpy().tobytes())
    return h.hexdigest()


def make_optimizer(model: nn.Module, lr: float) -> torch.optim.Optimizer:
    return torch.optim.AdamW([p for _, p in trainable_named(model)], lr=lr, weight_decay=0.0)


def batch_for_step(dataset, collator: Collator, seed: int, step: int, micro_batch: int) -> dict[str, Any]:
    g = torch.Generator().manual_seed(seed * 7919 + step)
    idx = torch.randperm(len(dataset), generator=g)[:micro_batch].tolist()
    return collator([dataset[i] for i in idx], random.Random(seed * 1_000_003 + step))


def train_steps(model, optimizer, dataset, collator: Collator, *, seed: int, start_step: int, end_step: int,
                micro_batch: int, ckpt_dir: Path | None = None, ckpt_every: int | None = None,
                config_sha256: str = "") -> list[float]:
    """Run steps [start_step, end_step). Returns the loss of each step."""
    losses: list[float] = []
    model.train()
    for step in range(start_step, end_step):
        batch = batch_for_step(dataset, collator, seed, step, micro_batch)
        batch.pop("decisions")
        loss = model(**batch)
        if not math.isfinite(loss.item()):
            raise NonFiniteLossError(f"non-finite loss {loss.item()} at step {step}")
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_([p for _, p in trainable_named(model)], 1.0)
        optimizer.step()
        losses.append(loss.item())
        done = step + 1
        if ckpt_dir is not None and ckpt_every and done % ckpt_every == 0:
            save_checkpoint(model, optimizer, done, Path(ckpt_dir) / f"step-{done:06d}", config_sha256=config_sha256)
    return losses


def save_checkpoint(model: nn.Module, optimizer: torch.optim.Optimizer, step: int, path: Path, *,
                    config_sha256: str = "") -> Path:
    """Save trainable state only (connector + LoRA), optimizer, RNG and step. Refuses to overwrite."""
    path = Path(path)
    if path.exists():
        raise CheckpointError(f"refusing to overwrite existing checkpoint {path}")
    path.mkdir(parents=True)
    state = {
        "trainable": {n: p.detach().clone() for n, p in trainable_named(model)},
        "optimizer": optimizer.state_dict(),
        "torch_rng": torch.get_rng_state(),
        "step": step,
    }
    torch.save(state, path / CKPT_FILE)
    meta = {
        "step": step,
        "sha256": hashlib.sha256((path / CKPT_FILE).read_bytes()).hexdigest(),
        "base_fingerprint": frozen_fingerprint(model),
        "config_sha256": config_sha256,
        "trainable_names": [n for n, _ in trainable_named(model)],
    }
    (path / META_FILE).write_text(json.dumps(meta, indent=2) + "\n")
    return path


def load_checkpoint(model: nn.Module, optimizer: torch.optim.Optimizer | None, path: Path) -> int:
    """Load a checkpoint into a freshly built model; verify checksum and frozen-base fingerprint."""
    path = Path(path)
    meta = json.loads((path / META_FILE).read_text())
    blob = (path / CKPT_FILE).read_bytes()
    if hashlib.sha256(blob).hexdigest() != meta["sha256"]:
        raise CheckpointError(f"checksum mismatch in {path / CKPT_FILE}")
    if frozen_fingerprint(model) != meta["base_fingerprint"]:
        raise CheckpointError("frozen base weights differ from the ones the checkpoint was trained on")
    state = torch.load(path / CKPT_FILE, weights_only=True)
    params = dict(trainable_named(model))
    if set(params) != set(state["trainable"]):
        raise CheckpointError("trainable parameter names differ between checkpoint and model")
    with torch.no_grad():
        for name, tensor in state["trainable"].items():
            params[name].copy_(tensor)
    if optimizer is not None:
        optimizer.load_state_dict(state["optimizer"])
    torch.set_rng_state(state["torch_rng"])
    return int(state["step"])


def policy_from_config(cfg: dict[str, Any]) -> ModalityPolicy:
    return ModalityPolicy(dropout_p=dict(cfg.get("modality_dropout") or {}),
                          report_substitution=bool(cfg.get("report_substitution", False)))
