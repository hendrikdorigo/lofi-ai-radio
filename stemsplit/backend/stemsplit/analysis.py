"""Detecção automática de BPM e tom (tonalidade) com librosa.

O tom usa o algoritmo de Krumhansl-Schmuckler: compara o cromagrama médio da
música com perfis de tonalidade maior/menor e escolhe o mais correlacionado.
"""

from __future__ import annotations

import numpy as np

NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
NOTES_PT = ["Dó", "Dó#", "Ré", "Ré#", "Mi", "Fá", "Fá#", "Sol", "Sol#", "Lá", "Lá#", "Si"]

# Perfis de Krumhansl-Kessler.
_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

ANALYSIS_SR = 22050
MAX_SECONDS = 180  # analisa no máximo 3 minutos para ser rápido


def _to_mono(audio: np.ndarray, sr: int) -> np.ndarray:
    import librosa

    mono = audio.mean(axis=0) if audio.ndim == 2 else audio
    mono = mono[: sr * MAX_SECONDS]
    return librosa.resample(mono, orig_sr=sr, target_sr=ANALYSIS_SR)


def detect_bpm(mono: np.ndarray) -> float | None:
    import librosa

    tempo, _ = librosa.beat.beat_track(y=mono, sr=ANALYSIS_SR)
    bpm = float(np.atleast_1d(tempo)[0])
    return round(bpm, 1) if bpm > 0 else None


def detect_key(mono: np.ndarray) -> dict | None:
    import librosa

    # Remove a parte percussiva para o cromagrama refletir só as notas.
    harmonic = librosa.effects.harmonic(mono)
    chroma = librosa.feature.chroma_cqt(y=harmonic, sr=ANALYSIS_SR).mean(axis=1)
    if not np.any(chroma):
        return None

    best = None
    for tonic in range(12):
        for scale, profile in (("maior", _MAJOR), ("menor", _MINOR)):
            score = float(np.corrcoef(chroma, np.roll(profile, tonic))[0, 1])
            if best is None or score > best[0]:
                best = (score, tonic, scale)
    score, tonic, scale = best
    suffix = "" if scale == "maior" else "m"
    return {
        "key": f"{NOTES[tonic]}{suffix}",
        "label": f"{NOTES_PT[tonic]} {scale}",
        "confidence": round(max(0.0, score), 2),
    }


def analyze(audio: np.ndarray, sr: int) -> dict:
    """Devolve ``{"bpm", "key", "key_label", "key_confidence", "duration"}``."""
    duration = audio.shape[-1] / sr
    result = {"duration": round(duration, 2), "bpm": None, "key": None, "key_label": None, "key_confidence": None}
    try:
        mono = _to_mono(audio, sr)
        result["bpm"] = detect_bpm(mono)
        key = detect_key(mono)
        if key:
            result.update(key=key["key"], key_label=key["label"], key_confidence=key["confidence"])
    except Exception as exc:  # noqa: BLE001 - análise é um extra, nunca deve derrubar o job
        result["error"] = str(exc)
    return result
