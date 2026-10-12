"""Separação fina por processamento de sinal (sem rede neural).

Usada na segunda passada do modo Detalhado, sobre stems que já vieram
isolados pelos modelos:

* **Guitarras** — divide o stem de guitarra em 4 partes que, somadas,
  reconstroem o stem original:

  - ``guitarra_1`` / ``guitarra_2``: o que soa *diferente* em cada lado do
    estéreo — tipicamente a base gravada duas vezes (uma tomada em cada lado)
    ou guitarras abertas em L/R;
  - ``guitarra_solo``: a melodia principal que está no centro, rastreada nota
    a nota (pYIN) e extraída pelos seus harmônicos;
  - ``guitarra_base``: o resto do centro (acordes, graves, ataques).

  É uma *estimativa*: duas guitarras tocando juntas no centro, ou solo e base
  na mesma faixa de notas, continuam se misturando.

* **Bateria** — divide em bumbo, caixa/tons e pratos por faixas de frequência
  com transições suaves.

As máscaras sempre somam 1, então nada do áudio original é perdido: somar as
partes devolve o stem de entrada.
"""

from __future__ import annotations

import numpy as np
from scipy.ndimage import uniform_filter, uniform_filter1d
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


def _center_similarity(spec: np.ndarray) -> np.ndarray:
    """Quanto cada célula tempo-frequência parece *uma única fonte no centro* (0..1).

    Uma guitarra posta no centro chega idêntica aos dois canais: mesma fase.
    Uma base gravada duas vezes (uma tomada de cada lado) pode ter o mesmo
    volume dos dois lados, mas nunca a mesma fase — as tomadas têm pequenas
    diferenças de tempo. Por isso usamos a parte *real* da correlação cruzada
    normalizada (≈ cosseno da diferença de fase), com média local de 3 bins x
    7 quadros; o volume sozinho não distingue os dois casos.
    """
    left, right = spec[0], spec[1]
    cross = left * np.conj(right)
    size = (3, 7)
    cross_s = uniform_filter(cross.real, size) + 1j * uniform_filter(cross.imag, size)
    p_l = uniform_filter(np.abs(left) ** 2, size)
    p_r = uniform_filter(np.abs(right) ** 2, size)
    return np.clip(cross_s.real / np.sqrt(p_l * p_r + 1e-12), 0.0, 1.0)


def _melody_mask(center: np.ndarray, freqs: np.ndarray, sr: int, n_frames: int) -> np.ndarray:
    """Máscara com os harmônicos da melodia principal (o solo) no sinal central.

    Rastreia a nota mais forte quadro a quadro (pYIN) e marca a frequência
    fundamental e seus harmônicos. Só vale nos trechos em que essa melodia
    domina o som do centro — assim o topo dos acordes da base não vira "solo"
    nos trechos sem solo.
    """
    import librosa

    from scipy.signal import butter, sosfiltfilt

    target_sr = 22050  # com hop 512 a 22.05 kHz, cada quadro do pYIN = um quadro do STFT
    # Tira os graves antes de detectar as notas: os acordes da base confundem o
    # pYIN (medido: 70% de acerto sem filtro x 98% com filtro em 220 Hz).
    highpass = butter(4, 220.0, "highpass", fs=sr, output="sos")
    mono = librosa.resample(sosfiltfilt(highpass, center.mean(axis=0)), orig_sr=sr, target_sr=target_sr)
    f0, _, voiced_prob = librosa.pyin(
        mono, fmin=150.0, fmax=1400.0, sr=target_sr, frame_length=2048, hop_length=HOP * target_sr // sr,
        fill_na=np.nan,
    )
    t = min(n_frames, len(f0))
    f0 = np.nan_to_num(f0[:t], nan=0.0).astype(np.float32)
    voiced = np.nan_to_num(voiced_prob[:t]).astype(np.float32)

    mask = np.zeros((len(freqs), n_frames), dtype=np.float32)
    active = f0 > 0
    if not active.any():
        return mask
    f = freqs[:, None]
    f0_safe = np.where(active, f0, 1.0)[None, :]
    k = np.maximum(1.0, np.round(f / f0_safe))  # harmônico mais próximo de cada bin
    dist = np.abs(f - k * f0_safe)
    sigma = np.maximum(15.0, 0.02 * k * f0_safe)  # tolera vibrato e bends
    harmonic = np.exp(-0.5 * (dist / sigma) ** 2) * (f >= 0.8 * f0_safe)
    mask[:, :t] = harmonic * (active * voiced)[None, :]
    return mask


def split_guitar(audio: np.ndarray, sr: int, progress: ProgressFn = no_progress) -> dict[str, np.ndarray]:
    """Divide o stem de guitarra em guitarra_1/2 (lados) e solo/base (centro).

    1. Fase + panorama separam o que é *uma* fonte no centro do que é
       diferente em cada lado (bases dobradas, guitarras abertas em L/R).
       O que não é centro vai, canal por canal, para Guitarra 1 (esquerda) e
       Guitarra 2 (direita).
    2. No centro, a melodia principal é rastreada; seus harmônicos viram
       "Guitarra solo" e o resto (acordes, graves) vira "Guitarra base".
    """
    n = audio.shape[1]
    freqs, spec = _stft(audio, sr)
    progress(0.1)

    mag_l, mag_r = np.abs(spec[0]), np.abs(spec[1])
    pan = uniform_filter((mag_r - mag_l) / (mag_r + mag_l + 1e-9), size=(3, 5))
    similarity = _center_similarity(spec)
    w_center = (_ramp(similarity, 0.5, 0.85) * (1.0 - _ramp(np.abs(pan), 0.35, 0.75))).astype(np.float32)
    center = spec * w_center
    sides = spec - center
    progress(0.3)

    center_audio = _istft(center, sr, n)
    melody = _melody_mask(center_audio, freqs, sr, spec.shape[-1])
    progress(0.8)

    # Só conta como solo onde a melodia carrega boa parte da energia do centro
    # acima de 250 Hz (média de ~0,3 s) — abaixo disso a base domina e
    # mascararia o solo. E nunca abaixo de ~150 Hz (graves são da base).
    energy = (np.abs(center[0]) ** 2 + np.abs(center[1]) ** 2) * (freqs >= 250.0)[:, None]
    share = (energy * melody).sum(axis=0) / (energy.sum(axis=0) + 1e-9)
    gate = _ramp(uniform_filter1d(share, size=13), 0.12, 0.3)
    w_solo = melody * gate[None, :] * _ramp(freqs, 120.0, 180.0)[:, None]
    solo = center * w_solo

    zeros = np.zeros_like(sides[0])
    out = {
        "guitarra_1": _istft(np.stack([sides[0], zeros]), sr, n),
        "guitarra_2": _istft(np.stack([zeros, sides[1]]), sr, n),
        "guitarra_solo": _istft(solo, sr, n),
        "guitarra_base": _istft(center - solo, sr, n),
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
