import os
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SR = 44100


@pytest.fixture(autouse=True)
def isolated_dirs(tmp_path, monkeypatch):
    """Cada teste usa pastas de dados/modelos temporárias."""
    from stemsplit import config

    monkeypatch.setattr(config, "settings", config.Settings(data_dir=tmp_path / "data", models_dir=tmp_path / "models"))
    for mod in ("stemsplit.audio_io", "stemsplit.jobs", "stemsplit.export", "stemsplit.api", "stemsplit.pipeline"):
        if mod in sys.modules and hasattr(sys.modules[mod], "settings"):
            monkeypatch.setattr(sys.modules[mod], "settings", config.settings)
    os.environ.setdefault("TORCH_HOME", str(tmp_path / "torch"))
    yield


def tone(freq: float, seconds: float = 2.0, amp: float = 0.3) -> np.ndarray:
    t = np.arange(int(SR * seconds)) / SR
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


@pytest.fixture
def song() -> np.ndarray:
    """Mix estéreo sintético: guitarra à esquerda (A3), à direita (E4), solo no centro (A5)."""
    left = tone(220) + tone(880, amp=0.2)
    right = tone(330) + tone(880, amp=0.2)
    return np.stack([left, right])
