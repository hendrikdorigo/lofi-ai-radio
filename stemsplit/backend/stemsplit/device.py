"""Escolha do dispositivo de processamento (GPU CUDA, Apple MPS ou CPU)."""

from __future__ import annotations

from functools import lru_cache

from .config import settings


@lru_cache(maxsize=1)
def get_device() -> str:
    wanted = settings.device.lower()
    try:
        import torch
    except ImportError:  # pragma: no cover - torch é dependência obrigatória
        return "cpu"

    if wanted == "auto":
        if torch.cuda.is_available():
            return "cuda"
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return "mps"
        return "cpu"
    if wanted == "cuda" and not torch.cuda.is_available():
        print("[StemSplit] CUDA pedida mas não disponível — usando CPU.")
        return "cpu"
    return wanted


def device_label() -> str:
    dev = get_device()
    if dev == "cuda":
        import torch

        return f"GPU ({torch.cuda.get_device_name(0)})"
    return {"mps": "GPU Apple (MPS)", "cpu": "CPU"}.get(dev, dev)
