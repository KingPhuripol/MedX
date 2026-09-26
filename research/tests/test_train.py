"""S9-A09..A12, A14, A17: CPU dry runs, checkpoints, modality dropout provenance, offline/CPU guards."""

from __future__ import annotations

import io
import json
import math
import random
from collections import Counter

import pytest
import torch

from research.train import launcher, models
from research.train.data import (DROPPED, IMAGE, REPORT, Collator, ModalityPolicy, SyntheticCaseDataset,
                                 decide_modalities)
from research.train.trainer import (CheckpointError, batch_for_step, load_checkpoint, make_optimizer, policy_from_config, save_checkpoint,
                                    train_steps)

from .conftest import CONFIGS, DRYRUN_MANIFESTS, load_cfg, load_json


def _setup(stage: str):
    cfg = load_cfg(stage)
    dry = cfg["dry_run"]
    ds = dry["dataset"]
    model = models.build_model(cfg, dry_run=True)
    dataset = SyntheticCaseDataset(ds["n"], tuple(dry["volume_shape"]), dry["backbone"]["vocab_size"], cfg["seed"],
                                   prompt_len=ds["prompt_len"], report_len=ds["report_len"], target_len=ds["target_len"],
                                   modalities=tuple(ds["modalities"]))
    collator = Collator(policy_from_config(cfg), cfg["train"]["seq_len"])
    optimizer = make_optimizer(model, cfg["train"]["lr"])
    return cfg, model, optimizer, dataset, collator


def _run(stage_setup, start, end):
    cfg, model, opt, dataset, collator = stage_setup
    return train_steps(model, opt, dataset, collator, seed=cfg["seed"], start_step=start, end_step=end,
                       micro_batch=cfg["train"]["micro_batch"])


def _snapshot(module: torch.nn.Module) -> dict[str, torch.Tensor]:
    return {n: p.detach().clone() for n, p in module.named_parameters()}


def test_stage2_dry_run():
    setup = _setup("stage2")
    _, model, *_ = setup
    assert sum(p.numel() for p in model.parameters()) <= 2_000_000
    before_bb, before_enc, before_con = _snapshot(model.backbone), _snapshot(model.encoder), _snapshot(model.connector)
    losses = _run(setup, 0, 3)
    assert len(losses) == 3 and all(math.isfinite(x) for x in losses)
    assert all(torch.equal(before_bb[n], p) for n, p in model.backbone.named_parameters())
    assert all(torch.equal(before_enc[n], p) for n, p in model.encoder.named_parameters())
    changed = [n for n, p in model.connector.named_parameters() if not torch.equal(before_con[n], p)]
    assert changed and set(changed) == set(before_con)
    assert {n for n, p in model.named_parameters() if p.requires_grad} == {f"connector.{n}" for n in before_con}


@pytest.mark.parametrize("shape", [(8, 32, 32), (12, 16, 24)], ids=["shapeA", "shapeB"])
def test_connector_fixed_token_count(shape):
    cfg = load_cfg("stage2")
    model = models.build_model(cfg, dry_run=True)
    vol = torch.randn(2, 1, *shape)
    with torch.no_grad():
        patches = model.encoder(vol)
        out = model.connector(patches)
    assert out.shape == (2, cfg["dry_run"]["connector"]["n_query"], model.backbone.config.hidden_size)


def test_connector_fixed_token_count_differs_in_patches():
    model = models.build_model(load_cfg("stage2"), dry_run=True)
    with torch.no_grad():
        a = model.encoder(torch.randn(1, 1, 8, 32, 32)).shape[1]
        b = model.encoder(torch.randn(1, 1, 12, 16, 24)).shape[1]
    assert a != b  # the two shapes really give different patch counts


def test_stage3_dry_run():
    setup = _setup("stage3")
    _, model, *_ = setup
    assert sum(p.numel() for p in model.parameters()) <= 2_000_000
    before = _snapshot(model)
    losses = _run(setup, 0, 3)
    assert len(losses) == 3 and all(math.isfinite(x) for x in losses)
    lora = [n for n in before if "lora_" in n]
    base_bb = [n for n in before if n.startswith("backbone.") and "lora_" not in n]
    con = [n for n in before if n.startswith("connector.")]
    params = dict(model.named_parameters())
    assert lora and all(not torch.equal(before[n], params[n]) for n in lora)
    assert all(not torch.equal(before[n], params[n]) for n in con)
    assert all(torch.equal(before[n], params[n]) for n in base_bb)
    assert all(torch.equal(before[n], params[n]) for n in before if n.startswith("encoder."))
    peft_trainable, _ = model.backbone.get_nb_trainable_parameters()
    n_con = sum(p.numel() for p in model.connector.parameters())
    assert sum(p.numel() for p in model.parameters() if p.requires_grad) == peft_trainable + n_con


def _fixed_batch(setup):
    cfg, _, _, dataset, collator = setup
    batch = batch_for_step(dataset, collator, cfg["seed"], 999, cfg["train"]["micro_batch"])
    batch.pop("decisions")
    return batch


@pytest.mark.parametrize("stage", ["stage2", "stage3"])
def test_checkpoint_roundtrip(stage, tmp_path):
    a = _setup(stage)
    _run(a, 0, 2)
    path = save_checkpoint(a[1], a[2], 2, tmp_path / "ckpt")
    b = _setup(stage)
    assert load_checkpoint(b[1], b[2], path) == 2
    batch = _fixed_batch(a)
    a[1].eval(), b[1].eval()
    with torch.no_grad():
        assert torch.equal(a[1](**batch), b[1](**batch))
        patches = a[1].encoder(batch["volumes"])
        assert torch.equal(a[1].connector(patches), b[1].connector(patches))


@pytest.mark.parametrize("stage", ["stage2", "stage3"])
def test_resume_matches_uninterrupted(stage, tmp_path):
    full = _run(_setup(stage), 0, 4)
    first = _setup(stage)
    part1 = _run(first, 0, 2)
    path = save_checkpoint(first[1], first[2], 2, tmp_path / "step-2")
    resumed = _setup(stage)
    start = load_checkpoint(resumed[1], resumed[2], path)
    part2 = _run(resumed, start, 4)
    assert part1 + part2 == full


@pytest.mark.parametrize("stage", ["stage2", "stage3"])
def test_checkpoint_excludes_frozen_weights(stage, tmp_path):
    setup = _setup(stage)
    _, model, opt, *_ = setup
    _run(setup, 0, 1)
    path = save_checkpoint(model, opt, 1, tmp_path / "ckpt")
    buf = io.BytesIO()
    torch.save(model.state_dict(), buf)
    ckpt_bytes = (path / "trainable.pt").stat().st_size
    full_bytes = len(buf.getvalue())
    assert ckpt_bytes < 0.05 * full_bytes, (ckpt_bytes, full_bytes)
    saved = torch.load(path / "trainable.pt", weights_only=True)["trainable"]
    frozen = {n for n, p in model.named_parameters() if not p.requires_grad}
    assert frozen and not (set(saved) & frozen)
    with pytest.raises(CheckpointError):
        save_checkpoint(model, opt, 1, path)  # never overwrites


def _samples(n=1000, modalities=("ct", "cxr"), seed=7):
    return SyntheticCaseDataset(n, (4, 8, 8), 64, seed, modalities=modalities)


def test_modality_dropout_rate():
    p = {"ct": 0.3, "cxr": 0.6}
    policy = ModalityPolicy(dropout_p=p, report_substitution=True)
    rng = random.Random(123)
    ds = _samples()
    counts = Counter()
    for i in range(len(ds)):
        for m, d in decide_modalities(ds[i], policy, rng).items():
            counts[m] += d != IMAGE
    for m, pm in p.items():
        assert abs(counts[m] / len(ds) - pm) <= 0.05, (m, counts[m] / len(ds))


def test_no_report_substitution_when_report_is_label():
    policy = ModalityPolicy(dropout_p={"ct": 0.5, "cxr": 0.5}, report_substitution=True)
    rng = random.Random(5)
    ds = _samples()
    sub_when_label, sub_otherwise = 0, 0
    for i in range(len(ds)):
        s = ds[i]
        for m, d in decide_modalities(s, policy, rng).items():
            if d == REPORT:
                if s["images"][m]["report_ref"] == s["label_source"]:
                    sub_when_label += 1
                else:
                    sub_otherwise += 1
    assert sub_when_label == 0 and sub_otherwise > 0
    # Through the collator as well (the enforcement point), for the whole dataset.
    collator = Collator(policy, seq_len=64)
    rng = random.Random(9)
    for start in range(0, len(ds), 50):
        batch = [ds[i] for i in range(start, start + 50)]
        out = collator(batch, rng)
        for s, d in zip(batch, out["decisions"]):
            assert not any(v == REPORT and s["images"][m]["report_ref"] == s["label_source"] for m, v in d.items())


def test_required_modality_kept():
    ds = _samples(n=1000, modalities=("ct",))
    rng = random.Random(3)
    for substitution in (True, False):
        policy = ModalityPolicy(dropout_p={"ct": 1.0}, report_substitution=substitution)
        seen = Counter()
        for i in range(len(ds)):
            s = dict(ds[i], required_modalities=["ct"])
            d = decide_modalities(s, policy, rng)["ct"]
            assert d != DROPPED
            if s["label_source"] == s["images"]["ct"]["report_ref"]:
                assert d == IMAGE  # its report is the label: keep the image, never the report
            seen[d] += 1
        assert seen[IMAGE] > 0
        assert (seen[REPORT] > 0) == substitution


def _spy_build(monkeypatch):
    built = []
    real = models.build_model

    def spy(cfg, *, dry_run):
        m = real(cfg, dry_run=dry_run)
        built.append(m)
        return m

    monkeypatch.setattr(models, "build_model", spy)
    return built


@pytest.mark.parametrize("stage", ["stage2", "stage3"])
def test_dry_run_offline_cpu_only(stage, tmp_path, monkeypatch):
    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    built = _spy_build(monkeypatch)
    rc = launcher.main(["--config", str(CONFIGS[stage]), "--manifest", str(DRYRUN_MANIFESTS[stage]), "--dry-run",
                        "--output-root", str(tmp_path)])
    assert rc == 0
    assert len(built) == 1 and all(p.device.type == "cpu" for p in built[0].parameters())
    runs = list(tmp_path.glob("dryrun-*/run.json"))
    assert len(runs) == 1
    meta = json.loads(runs[0].read_text())
    assert meta["status"] == "completed" and meta["environment"]["device"] == "cpu" and meta["data_class"] == "synthetic"
    assert len(meta["losses"]) == meta["max_steps"] and all(math.isfinite(x) for x in meta["losses"])
    assert meta["parameters_total"] <= 2_000_000 and len(meta["checkpoints"]) == 2
    import os
    assert os.environ["CUDA_VISIBLE_DEVICES"] == "" and os.environ["HF_HUB_OFFLINE"] == "1"


def test_no_hub_calls_in_dry_run(tmp_path, monkeypatch):
    import huggingface_hub
    import transformers
    from transformers import PreTrainedModel

    calls = []

    def boom(*args, **kwargs):
        calls.append(args)
        raise AssertionError(f"hub access attempted: {args}")

    monkeypatch.setattr(PreTrainedModel, "from_pretrained", classmethod(boom))
    for cls in (transformers.AutoModelForCausalLM, transformers.AutoConfig, transformers.AutoTokenizer):
        monkeypatch.setattr(cls, "from_pretrained", boom)
    monkeypatch.setattr(huggingface_hub, "hf_hub_download", boom)
    monkeypatch.setattr(huggingface_hub, "snapshot_download", boom)
    for stage in ("stage2", "stage3"):
        rc = launcher.main(["--config", str(CONFIGS[stage]), "--manifest", str(DRYRUN_MANIFESTS[stage]), "--dry-run",
                            "--output-root", str(tmp_path / stage)])
        assert rc == 0
    assert calls == []


def _write_manifest(tmp_path, manifest, name="m.json"):
    path = tmp_path / name
    path.write_text(json.dumps(manifest))
    return path


def test_launcher_rejects_before_model_build(tmp_path, monkeypatch, capsys):
    built = _spy_build(monkeypatch)
    m = load_json(DRYRUN_MANIFESTS["stage3"])
    m.update(run_tier=3, experiment_id="tier3-unapproved")
    m["resources"].update(gpu_count=8, max_minutes=600, devices="8x NVIDIA B200")
    rc = launcher.main(["--config", str(CONFIGS["stage3"]), "--manifest", str(_write_manifest(tmp_path, m)),
                        "--output-root", str(tmp_path / "out")])
    assert rc != 0 and built == []
    assert "approval" in capsys.readouterr().err
    assert not (tmp_path / "out").exists()


def test_launcher_refuses_cuda_for_tier0(tmp_path, monkeypatch, capsys):
    built = _spy_build(monkeypatch)
    cfg_text = CONFIGS["stage2"].read_text().replace("device: cpu", "device: cuda")
    cfg_path = tmp_path / "stage2_cuda.yaml"
    cfg_path.write_text(cfg_text)
    from research.manifest_validation import sha256_file

    m = load_json(DRYRUN_MANIFESTS["stage2"])
    m["code"].update(config_path=str(cfg_path), config_sha256=sha256_file(cfg_path))
    rc = launcher.main(["--config", str(cfg_path), "--manifest", str(_write_manifest(tmp_path, m)), "--dry-run",
                        "--output-root", str(tmp_path / "out")])
    assert rc != 0 and built == []
    assert "CPU only" in capsys.readouterr().err


def test_launcher_rejects_dry_run_on_tier2_manifest(tmp_path, monkeypatch):
    built = _spy_build(monkeypatch)
    from .conftest import REPO_ROOT

    manifest = REPO_ROOT / "research" / "manifests" / "smoke-s2-connector-qwen3.8-27b.json"
    rc = launcher.main(["--config", str(CONFIGS["stage2"]), "--manifest", str(manifest), "--dry-run",
                        "--output-root", str(tmp_path)])
    assert rc != 0 and built == []
