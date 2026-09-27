"""Model components: 3D encoder interface, fixed-token connector, backbone factory, composite model.

Proposal 2.1.2 / 3.3: a 3D encoder (CT-CLIP in the real run) produces a variable number of patch
embeddings; a Perceiver/RadFM-style resampler maps them to exactly `n_query` tokens in the LM hidden
size; the tokens are prepended to the text embeddings of the backbone.
"""

from __future__ import annotations

import abc
from typing import Any

import torch
from torch import nn

# ---------------------------------------------------------------------------------------------------
# 3D encoder
# ---------------------------------------------------------------------------------------------------


class Volume3DEncoder(nn.Module, abc.ABC):
    """Interface: volume (B, 1, D, H, W) -> patch embeddings (B, N_patch, out_dim). Frozen in s9 stages."""

    out_dim: int

    @abc.abstractmethod
    def forward(self, volume: torch.Tensor) -> torch.Tensor: ...


class TinyConv3DEncoder(Volume3DEncoder):
    """CPU stand-in for CT-CLIP: non-overlapping 3D patches -> linear embedding (dry run only)."""

    def __init__(self, out_dim: int, patch: tuple[int, int, int]):
        super().__init__()
        self.out_dim = out_dim
        self.patch = tuple(patch)
        self.proj = nn.Conv3d(1, out_dim, kernel_size=self.patch, stride=self.patch)
        self.norm = nn.LayerNorm(out_dim)

    def forward(self, volume: torch.Tensor) -> torch.Tensor:
        x = self.proj(volume)  # (B, C, d, h, w)
        return self.norm(x.flatten(2).transpose(1, 2))  # (B, N_patch, C)


class CTCLIPEncoder(Volume3DEncoder):
    """Placeholder for the pretrained CT-CLIP image encoder (real weights are out of scope for s9)."""

    def __init__(self, out_dim: int = 512, **_: Any):
        super().__init__()
        self.out_dim = out_dim

    def forward(self, volume: torch.Tensor) -> torch.Tensor:  # pragma: no cover - interface stub
        raise NotImplementedError("CT-CLIP weights are not loaded in slice s9 (dry run uses TinyConv3DEncoder)")


# ---------------------------------------------------------------------------------------------------
# Connector
# ---------------------------------------------------------------------------------------------------


class _ResamplerLayer(nn.Module):
    def __init__(self, d_model: int, n_heads: int):
        super().__init__()
        self.norm_q = nn.LayerNorm(d_model)
        self.norm_kv = nn.LayerNorm(d_model)
        self.attn = nn.MultiheadAttention(d_model, n_heads, batch_first=True)
        self.norm_ff = nn.LayerNorm(d_model)
        self.ff = nn.Sequential(nn.Linear(d_model, 4 * d_model), nn.GELU(), nn.Linear(4 * d_model, d_model))

    def forward(self, q: torch.Tensor, kv: torch.Tensor) -> torch.Tensor:
        kv_n = self.norm_kv(kv)
        q = q + self.attn(self.norm_q(q), kv_n, kv_n, need_weights=False)[0]
        return q + self.ff(self.norm_ff(q))


class FixedTokenConnector(nn.Module):
    """Perceiver/RadFM-style resampler: any number of patches -> exactly `n_query` tokens of size `d_out`.

    Parameter count (implemented once in research.estimate.estimate.connector_params):
    d_in*d + d + n_query*d + n_layers*(12*d^2 + 15*d) + 2*d + d*d_out + d_out.
    """

    def __init__(self, d_in: int, d_model: int, n_query: int, n_layers: int, n_heads: int, d_out: int):
        super().__init__()
        self.n_query = n_query
        self.in_proj = nn.Linear(d_in, d_model)
        self.queries = nn.Parameter(torch.randn(n_query, d_model) * 0.02)
        self.layers = nn.ModuleList(_ResamplerLayer(d_model, n_heads) for _ in range(n_layers))
        self.out_norm = nn.LayerNorm(d_model)
        self.out_proj = nn.Linear(d_model, d_out)

    def forward(self, patches: torch.Tensor) -> torch.Tensor:
        kv = self.in_proj(patches)
        q = self.queries.unsqueeze(0).expand(patches.shape[0], -1, -1)
        for layer in self.layers:
            q = layer(q, kv)
        return self.out_proj(self.out_norm(q))  # (B, n_query, d_out)


# ---------------------------------------------------------------------------------------------------
# Backbone + composite
# ---------------------------------------------------------------------------------------------------


def build_tiny_backbone(backbone_cfg: dict[str, Any]) -> nn.Module:
    """Dry run: an LM built *from config only* through AutoModelForCausalLM (never from_pretrained)."""
    from transformers import AutoConfig, AutoModelForCausalLM

    cfg = dict(backbone_cfg)
    model_type = cfg.pop("model_type")
    config = AutoConfig.for_model(model_type, **cfg)
    return AutoModelForCausalLM.from_config(config)


class CaseModel(nn.Module):
    """3D encoder -> connector -> image tokens prepended to text embeddings -> causal LM loss."""

    def __init__(self, encoder: Volume3DEncoder, connector: FixedTokenConnector, backbone: nn.Module):
        super().__init__()
        self.encoder = encoder
        self.connector = connector
        self.backbone = backbone

    def forward(self, volumes, image_mask, input_ids, attention_mask, labels) -> torch.Tensor:
        with torch.no_grad():  # the 3D encoder is frozen in stages 2 and 3
            patches = self.encoder(volumes)
        img = self.connector(patches) * image_mask[:, None, None].to(patches.dtype)
        txt = self.backbone.get_input_embeddings()(input_ids)
        embeds = torch.cat([img, txt], dim=1)
        n_q = img.shape[1]
        attn = torch.cat([image_mask[:, None].expand(-1, n_q).long(), attention_mask], dim=1)
        ignore = torch.full((labels.shape[0], n_q), -100, dtype=labels.dtype)
        out = self.backbone(inputs_embeds=embeds, attention_mask=attn, labels=torch.cat([ignore, labels], dim=1))
        return out.loss


def build_model(cfg: dict[str, Any], *, dry_run: bool) -> CaseModel:
    """Model factory used by the launcher (tests spy on it to prove invalid manifests never reach it)."""
    if not dry_run:
        raise NotImplementedError("slice s9 builds only the dry-run tiny model; real checkpoints need a Tier-2 run")
    dry = cfg["dry_run"]
    torch.manual_seed(cfg["seed"])
    backbone = build_tiny_backbone(dry["backbone"])
    enc_cfg = dry["encoder3d"]
    encoder = TinyConv3DEncoder(enc_cfg["out_dim"], tuple(enc_cfg["patch"]))
    con = dry["connector"]
    connector = FixedTokenConnector(
        d_in=encoder.out_dim, d_model=con["d_model"], n_query=con["n_query"], n_layers=con["n_layers"],
        n_heads=con["n_heads"], d_out=backbone.config.hidden_size,
    )
    encoder.requires_grad_(False)
    backbone.requires_grad_(False)
    if cfg["stage"] == "stage3_lora":
        from peft import LoraConfig, get_peft_model

        lora = dry["lora"]
        backbone = get_peft_model(
            backbone,
            LoraConfig(r=lora["r"], lora_alpha=lora["alpha"], lora_dropout=0.0, target_modules=list(lora["target_modules"])),
        )
    connector.requires_grad_(True)
    return CaseModel(encoder, connector, backbone)
