"""Separação fina por processamento de sinal (sem rede neural).

Usada na segunda passada do modo Detalhado, sobre stems que já vieram
isolados pelos modelos:

* **Guitarras** — divide o stem de guitarra em 4 partes que, somadas,
  reconstroem o stem original:

  - ``guitarra_1``: o que está panoramizado à esquerda;
  - ``guitarra_2``: o que está panoramizado à direita;
  - ``guitarra_solo``: o que está no centro e é sustentado/melódico;
  - ``guitarra_base``: o que está no centro e é percussivo/rítmico (palhetadas
    abafadas, ataques) ou muito grave.

  Em mixagens de metal (Avenged Sevenfold, Metallica, Iron Maiden...) as bases
  costumam ser gravadas duas vezes e abertas em L/R, e solos/duetos ficam no
  centro ou abertos em L/R. É uma *estimativa*: quando duas guitarras ocupam a
  mesma posição no estéreo, elas não se separam por aqui.

* **Bateria** — divide em bumbo, caixa/tons e pratos por faixas de frequência
  com transições suaves.

As máscaras sempre somam 1, então nada do áudio original é perdido: somar as
partes devolve o stem de entrada.
"""

from __future__ import annotations

import numpy as np
from scipy.ndimage import uniform_filter
from scipy.signal import istft, stft

from . import ProgressFn, no_progress

N_FFT = 4096
HOP = 1024


def _ramp(x: np.ndarray, start: float, end: float) -> np.ndarray:
    """0 antes de ``start``, 1 depois de ``end`` e transição linear no meio."""
    return np.clip((x - start) / (end - start), 0.0, 1.0)


def _stft(audio: np.ndarray, sr: int):
    freqs, _, spec = stft(audio.astype(np.float32), fs=sr, nperseg=N_FFT, noverlap=N_FFT - HOP)
    return freqs.astype(np.float32), spec


def _istft(spec: np.ndarray, sr: int, length: int) -> np.ndarray:
    _, out = istft(spec, fs=sr, nperseg=N_FFT, noverlap=N_FFT - HOP)
    out = out[..., :length]
    if out.shape[-1] < length:
        out = np.pad(out, ((0, 0), (0, length - out.shape[-1])))
    return out.astype(np.float32)


def stereo_width(audio: np.ndarray) -> float:
    """0 = mono, ~1 = canais totalmente diferentes. Útil para avisar o usuário."""
    left, right = audio[0], audio[1]
    energy = float(np.sum(left**2) + np.sum(right**2)) + 1e-12
    side = float(np.sum((left - right) ** 2)) / 2
    return min(1.0, side / (energy / 2))


def split_guitar(audio: np.ndarray, sr: int, progress: ProgressFn = no_progress) -> dict[str, np.ndarray]:
    """Divide o stem de guitarra em guitarra_1/2 (L/R) e solo/base (centro)."""
    import librosa

    n = audio.shape[1]
    freqs, spec = _stft(audio, sr)
    progress(0.2)

    mag_l, mag_r = np.abs(spec[0]), np.abs(spec[1])
    # Índice de panorama por célula tempo-frequência: -1 esquerda, 0 centro, +1 direita.
    pan = (mag_r - mag_l) / (mag_r + mag_l + 1e-9)
    # Suaviza para reduzir artefatos "metálicos" (musical noise).
    pan = uniform_filter(pan, size=(3, 5))

    w_left = _ramp(-pan, 0.25, 0.6)
    w_right = _ramp(pan, 0.25, 0.6)
    w_center = 1.0 - w_left - w_right
    progress(0.4)

    # No centro, separa harmônico (notas sustentadas = solo) de percussivo (base).
    center_mag = (mag_l + mag_r) * 0.5 * w_center
    mask_h, _ = librosa.decompose.hpss(center_mag, kernel_size=(17, 31), mask=True, margin=1.0)
    progress(0.7)

    # Graves (< ~150 Hz) quase sempre são da base (chugs na corda solta).
    register = _ramp(freqs, 150.0, 400.0)[:, None]
    w_solo = w_center * mask_h * register
    w_base = w_center - w_solo

    out = {
        "guitarra_1": _istft(spec * w_left, sr, n),
        "guitarra_2": _istft(spec * w_right, sr, n),
        "guitarra_solo": _istft(spec * w_solo, sr, n),
        "guitarra_base": _istft(spec * w_base, sr, n),
    }
    progress(1.0)
    return out


def split_drums(audio: np.ndarray, sr: int, progress: ProgressFn = no_progress) -> dict[str, np.ndarray]:
    """Divide a bateria em bumbo, caixa/tons e pratos por bandas de frequência."""
    n = audio.shape[1]
    freqs, spec = _stft(audio, sr)
    progress(0.4)

    kick = 1.0 - _ramp(freqs, 90.0, 180.0)
    cymbals = _ramp(freqs, 4500.0, 7500.0)
    snare = 1.0 - kick - cymbals

    out = {
        "bumbo": _istft(spec * kick[:, None], sr, n),
        "caixa": _istft(spec * snare[:, None], sr, n),
        "pratos": _istft(spec * cymbals[:, None], sr, n),
    }
    progress(1.0)
    return out
