"""Separação com modelos RoFormer (BS-RoFormer / Mel-Band RoFormer) via ``audio-separator``.

O ``audio-separator`` (projeto open source que reúne os modelos do UVR) trabalha
com arquivos, então gravamos um WAV temporário, separamos e lemos de volta.
"""

from __future__ import annotations

import importlib
import re
import tempfile
import threading
from pathlib import Path

import numpy as np

from ..audio_io import load_audio, save_wav_float
from ..config import settings
from ..device import get_device
from . import ProgressFn, no_progress, tqdm_reporter

_separators: dict[str, object] = {}
_lock = threading.Lock()


class ModelUnavailable(RuntimeError):
    """O modelo não pôde ser carregado (sem internet na 1ª vez, nome errado...)."""


def _overlap() -> int:
    if settings.roformer_overlap.isdigit():
        return max(1, int(settings.roformer_overlap))
    return 2 if get_device() == "cpu" else 8


def _get_separator(model_filename: str, output_dir: Path):
    from audio_separator.separator import Separator

    with _lock:
        sep = _separators.get(model_filename)
        if sep is None:
            sep = Separator(
                model_file_dir=str(settings.models_dir / "audio-separator"),
                output_dir=str(output_dir),
                output_format="WAV",
                log_level=30,  # WARNING: silencia o log detalhado
                mdxc_params={"segment_size": 256, "override_model_segment_size": False,
                             "batch_size": 1, "overlap": _overlap(), "pitch_shift": 0},
            )
            try:
                sep.load_model(model_filename=model_filename)
            except Exception as exc:  # noqa: BLE001 - repassamos com mensagem clara
                raise ModelUnavailable(f"Não foi possível carregar o modelo '{model_filename}': {exc}") from exc
            _separators[model_filename] = sep
        sep.output_dir = str(output_dir)
        # Algumas versões guardam o output_dir também no modelo já carregado.
        if getattr(sep, "model_instance", None) is not None:
            sep.model_instance.output_dir = str(output_dir)
        return sep


# Módulos do audio-separator que usam ``from tqdm import tqdm``.
_TQDM_MODULES = [
    "audio_separator.separator.separator",
    "audio_separator.separator.architectures.mdxc_separator",
    "audio_separator.separator.architectures.mdx_separator",
    "audio_separator.separator.architectures.vr_separator",
]


class _patched_tqdm:
    """Redireciona as barras tqdm do audio-separator para o callback de progresso."""

    def __init__(self, progress: ProgressFn):
        self._fake = tqdm_reporter(progress)
        self._saved: list[tuple[object, object]] = []

    def __enter__(self):
        for name in _TQDM_MODULES:
            try:
                mod = importlib.import_module(name)
            except ImportError:
                continue
            if hasattr(mod, "tqdm"):
                self._saved.append((mod, mod.tqdm))
                mod.tqdm = self._fake
        return self

    def __exit__(self, *_):
        for mod, original in self._saved:
            mod.tqdm = original


def _stem_label(filename: str) -> str:
    """Extrai o rótulo do stem do nome gerado, ex.: 'faixa_(Vocals)_modelo.wav' → 'vocals'."""
    found = re.findall(r"\(([^)]+)\)", Path(filename).name)
    return found[0].strip().lower() if found else Path(filename).stem.lower()


def separate(audio: np.ndarray, model_filename: str, progress: ProgressFn = no_progress) -> dict[str, np.ndarray]:
    """Roda um modelo do audio-separator e devolve ``{rotulo_minusculo: array}``.

    Os rótulos dependem do modelo — tipicamente ``vocals`` e ``instrumental``.
    """
    with tempfile.TemporaryDirectory(prefix="stemsplit_") as tmp:
        tmp_dir = Path(tmp)
        src = save_wav_float(tmp_dir / "entrada.wav", audio)
        out_dir = tmp_dir / "saida"
        out_dir.mkdir()
        with _patched_tqdm(lambda f: None):  # download do modelo: só silencia a barra
            sep = _get_separator(model_filename, out_dir)
        with _patched_tqdm(progress):
            files = sep.separate(str(src))
        result: dict[str, np.ndarray] = {}
        for f in files:
            path = Path(f)
            if not path.is_absolute():
                path = out_dir / path
            result[_stem_label(path.name)] = load_audio(path)
        progress(1.0)
        return result


def split_two(audio: np.ndarray, model_filename: str, primary: str, progress: ProgressFn = no_progress):
    """Separa em (primário, resto). Se o modelo não devolver o 'resto', calcula por subtração."""
    stems = separate(audio, model_filename, progress)
    if primary not in stems:
        raise ModelUnavailable(
            f"O modelo '{model_filename}' não gerou o stem '{primary}' (gerou: {', '.join(stems)})."
        )
    main = _fit_length(stems[primary], audio.shape[1])
    others = [v for k, v in stems.items() if k != primary]
    rest = _fit_length(others[0], audio.shape[1]) if len(others) == 1 else audio - main
    return main, rest


def _fit_length(x: np.ndarray, n: int) -> np.ndarray:
    if x.shape[1] >= n:
        return x[:, :n]
    return np.pad(x, ((0, 0), (0, n - x.shape[1])))
