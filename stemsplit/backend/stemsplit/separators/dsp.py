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


# Faixa de notas considerada para melodias de guitarra (Ré#3 a ~Fá6).
F0_MIN, F0_MAX = 150.0, 1400.0
_CANDIDATES = F0_MIN * 2 ** (np.arange(int(72 * np.log2(F0_MAX / F0_MIN)) + 1) / 72)  # 1/6 de semitom


def _salience(logmag: np.ndarray, freqs: np.ndarray) -> np.ndarray:
    """Força de cada nota candidata em cada quadro: soma (ponderada) dos seus 8 harmônicos.

    Mais robusta que o pYIN quando há acordes por baixo (medido em teste
    sintético: 100% x 70% de notas certas).
    """
    from scipy.ndimage import maximum_filter1d

    spread = maximum_filter1d(logmag, size=3, axis=0)  # tolera ±1 bin de desafinação
    bin_hz = freqs[1]
    sal = np.zeros((len(_CANDIDATES), logmag.shape[1]), dtype=np.float32)
    for h in range(1, 9):
        bins = np.round(h * _CANDIDATES / bin_hz).astype(int)
        ok = bins < len(freqs)
        sal[ok] += (0.84 ** (h - 1)) * spread[bins[ok]]
    return sal


def _harmonic_mask(freqs: np.ndarray, f0: np.ndarray) -> np.ndarray:
    """Máscara (bins x quadros) com a fundamental e os harmônicos de ``f0`` (0 = sem nota)."""
    active = f0 > 0
    f = freqs[:, None]
    f0_safe = np.where(active, f0, 1.0)[None, :]
    k = np.maximum(1.0, np.round(f / f0_safe))  # harmônico mais próximo de cada bin
    dist = np.abs(f - k * f0_safe)
    sigma = np.maximum(15.0, 0.02 * k * f0_safe)  # tolera vibrato e bends
    mask = np.exp(-0.5 * (dist / sigma) ** 2) * (f >= 0.8 * f0_safe)
    return (mask * active[None, :]).astype(np.float32)


def _smooth_track(f0: np.ndarray) -> np.ndarray:
    """Remove saltos isolados de um quadro (mediana de 5 quadros, em escala de semitons)."""
    from scipy.signal import medfilt

    log = np.where(f0 > 0, np.log2(np.maximum(f0, 1e-6)), 0.0)
    smooth = medfilt(log, 5)
    return np.where((f0 > 0) & (smooth > 0), 2 ** smooth, 0.0)


def _related(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """True quando ``b`` é oitava/harmônico de ``a`` (eco da mesma nota, não outra voz)."""
    ratio = np.log2(np.maximum(b, 1e-6) / np.maximum(a, 1e-6))
    hits = np.zeros_like(ratio, dtype=bool)
    for r in (-2.0, -1.0, 0.0, 1.0, 2.0, np.log2(3), -np.log2(3)):
        hits |= np.abs(ratio - r) * 1200 < 60
    return hits


def _log_magnitude(mag: np.ndarray, freqs: np.ndarray) -> np.ndarray:
    mag = mag * (freqs >= 200.0)[:, None]  # graves: território da base
    return np.log1p(mag / (mag.max() + 1e-9) * 1000).astype(np.float32)


def _presence(peak: np.ndarray, start: float = 1.5, end: float = 4.0) -> np.ndarray:
    """0..1 por quadro: quanto a nota detectada se destaca do "fundo" da região.

    O fundo é o percentil 20 da força ao longo da música (os trechos só com
    base); um solo entrando eleva a força bem acima dele. Média de ~0,3 s.
    """
    smooth = uniform_filter1d(peak, size=13)
    return _ramp(smooth - np.percentile(smooth, 20), start, end)


def _region_melodies(mag: np.ndarray, freqs: np.ndarray, voices: int) -> list[tuple[np.ndarray, np.ndarray]]:
    """Até ``voices`` melodias simultâneas numa região: lista de (f0 por quadro, presença 0..1).

    Acha a nota mais forte; depois apaga os harmônicos dela e procura outra
    nota forte que não seja oitava/harmônico da primeira (a 2ª voz do dueto).
    """
    logmag = _log_magnitude(mag, freqs)
    sal1 = _salience(logmag, freqs)
    f0a, peak_a = _CANDIDATES[sal1.argmax(axis=0)], sal1.max(axis=0)
    lines = [(_smooth_track(f0a), _presence(peak_a))]
    if voices > 1:
        sal2 = _salience(logmag * (1.0 - _harmonic_mask(freqs, f0a)), freqs)
        f0b, peak_b = _CANDIDATES[sal2.argmax(axis=0)], sal2.max(axis=0)
        valid = (peak_b > 0.55 * peak_a) & ~_related(f0a, f0b)
        lines.append((_smooth_track(np.where(valid, f0b, 0.0)), _presence(peak_b) * valid))
    return lines


def split_guitar(audio: np.ndarray, sr: int, progress: ProgressFn = no_progress) -> dict[str, np.ndarray]:
    """Divide o stem de guitarra em solo, dueto (2ª voz) e base esquerda/direita/centro.

    1. Separa as regiões do estéreo pela fase entre os canais: *uma* fonte no
       centro x o que é diferente em cada lado (bases dobradas, duetos abertos).
    2. Procura melodias em cada região: até duas no centro (dueto/harmonia no
       centro) e uma em cada lado (dueto aberto em L/R, como é comum no metal).
       Procurar por região evita que os acordes da base, que vêm dos lados,
       atrapalhem a detecção no centro (medido: 1-59% x 75-100% de notas certas).
    3. Em cada instante, a melodia ativa mais aguda vira "Guitarra solo" e a
       segunda, "Guitarra dueto" — cada uma na sua posição original no estéreo.
    4. O que sobra é base: "Base centro", "Base esquerda" e "Base direita".
    As partes somadas reconstroem a entrada.
    """
    n = audio.shape[1]
    freqs, spec = _stft(audio, sr)
    progress(0.1)

    mag_l, mag_r = np.abs(spec[0]), np.abs(spec[1])
    pan = uniform_filter((mag_r - mag_l) / (mag_r + mag_l + 1e-9), size=(3, 5))
    w_center = _ramp(_center_similarity(spec), 0.5, 0.85) * (1.0 - _ramp(np.abs(pan), 0.35, 0.75))
    zeros = np.zeros_like(spec[0])
    center = spec * w_center
    sides = spec - center
    regions = {
        "centro": center,
        "esquerda": np.stack([sides[0], zeros]),
        "direita": np.stack([zeros, sides[1]]),
    }
    progress(0.3)

    lowcut = _ramp(freqs, 120.0, 180.0)[:, None]
    lines = []  # (região, f0, máscara)
    for name, region in regions.items():
        mag = np.abs(region).sum(axis=0)
        found = _region_melodies(mag, freqs, voices=2 if name == "centro" else 1)
        masks = [_harmonic_mask(freqs, f0) * gate[None, :] * lowcut for f0, gate in found]
        total = np.maximum(1.0, sum(masks))  # 2 vozes na mesma região dividem a energia
        for (f0, gate), mask in zip(found, masks):
            lines.append((name, np.where(gate > 0.5, f0, 0.0), mask / total))
    progress(0.7)

    # Em cada quadro: a melodia ativa mais aguda é o solo; a segunda, o dueto.
    pitches = np.stack([f0 for _, f0, _ in lines])  # linhas x quadros
    order = np.argsort(-pitches, axis=0)
    rank = np.empty_like(order)
    np.put_along_axis(rank, order, np.arange(len(lines))[:, None].repeat(pitches.shape[1], 1), axis=0)
    solo = np.zeros_like(spec)
    duet = np.zeros_like(spec)
    leads = {name: np.zeros_like(spec) for name in regions}
    for i, (name, f0, mask) in enumerate(lines):
        part = regions[name] * mask
        is_solo = ((rank[i] == 0) & (f0 > 0))[None, None, :]
        is_duet = ((rank[i] == 1) & (f0 > 0))[None, None, :]
        solo += part * is_solo
        duet += part * is_duet
        leads[name] += part * (is_solo | is_duet)

    out = {
        "guitarra_solo": _istft(solo, sr, n),
        "guitarra_dueto": _istft(duet, sr, n),
        "guitarra_base": _istft(regions["centro"] - leads["centro"], sr, n),
        "guitarra_1": _istft(regions["esquerda"] - leads["esquerda"], sr, n),
        "guitarra_2": _istft(regions["direita"] - leads["direita"], sr, n),
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
