"""Separação com Demucs (Meta) — htdemucs (4 stems) e htdemucs_6s (6 stems)."""

from __future__ import annotations

import threading
from types import SimpleNamespace

import numpy as np

from ..device import get_device
from ..stems import DEMUCS_NAMES
from . import ProgressFn, no_progress, tqdm_reporter

_models: dict[str, object] = {}
_lock = threading.Lock()


def _get_model(name: str):
    """Carrega (e mantém em memória) um modelo Demucs. Baixa os pesos na 1ª vez."""
    with _lock:
        if name not in _models:
            from demucs.pretrained import get_model

            model = get_model(name)
            model.eval()
            _models[name] = model
        return _models[name]


def separate(audio: np.ndarray, model_name: str, progress: ProgressFn = no_progress) -> dict[str, np.ndarray]:
    """Separa ``audio`` (2, n) e devolve ``{nome_stemsplit: array}``."""
    import torch
    import demucs.apply as demucs_apply

    model = _get_model(model_name)
    device = get_device()

    wav = torch.from_numpy(audio).float()
    # Normalização recomendada pelo Demucs (média/desvio do mix mono).
    ref = wav.mean(0)
    mean, std = ref.mean(), ref.std() + 1e-8
    wav = (wav - mean) / std

    # O Demucs com "bag of models" chama apply_model várias vezes; o callback
    # recebe a fração de cada passada, então ponderamos por número de modelos.
    n_models = len(getattr(model, "models", [model]))
    state = {"done": 0, "last": 0.0}

    def on_chunk(frac: float) -> None:
        if frac < state["last"]:  # começou outro modelo do "bag"
            state["done"] += 1
        state["last"] = frac
        progress(min(1.0, (state["done"] + frac) / n_models))

    # ``demucs.apply`` chama ``tqdm.tqdm(blocos)``; trocamos para reportar progresso.
    original_tqdm = demucs_apply.tqdm
    demucs_apply.tqdm = SimpleNamespace(tqdm=tqdm_reporter(on_chunk))
    try:
        with torch.no_grad():
            out = demucs_apply.apply_model(
                model, wav[None], device=device, shifts=1, split=True, overlap=0.25, progress=True,
            )[0]
    finally:
        demucs_apply.tqdm = original_tqdm

    out = out * std + mean
    result: dict[str, np.ndarray] = {}
    for source_name, tensor in zip(model.sources, out):
        name = DEMUCS_NAMES.get(source_name, source_name)
        result[name] = tensor.cpu().numpy().astype(np.float32)
    progress(1.0)
    return result
