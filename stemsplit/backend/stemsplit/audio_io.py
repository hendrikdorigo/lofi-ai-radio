"""Leitura e escrita de áudio.

Todo áudio circula internamente como ``numpy.ndarray`` float32 no formato
``(canais, amostras)``, sempre estéreo e em 44.1 kHz. A decodificação usa o
ffmpeg, que lê praticamente qualquer formato (MP3, WAV, FLAC, M4A...).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

from .config import settings


class AudioError(RuntimeError):
    """Erro de leitura/escrita de áudio com mensagem amigável."""


def require_ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise AudioError("ffmpeg não encontrado. Instale o ffmpeg e tente novamente.")
    return path


def load_audio(path: str | Path, sr: int | None = None) -> np.ndarray:
    """Decodifica qualquer arquivo de áudio para float32 estéreo ``(2, n)``."""
    sr = sr or settings.sample_rate
    cmd = [
        require_ffmpeg(), "-v", "error", "-nostdin", "-i", str(path),
        "-vn", "-ac", "2", "-ar", str(sr), "-f", "f32le", "-",
    ]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        msg = proc.stderr.decode(errors="ignore").strip().splitlines()
        raise AudioError(f"Não consegui ler o arquivo de áudio: {msg[-1] if msg else 'erro desconhecido'}")
    data = np.frombuffer(proc.stdout, dtype=np.float32)
    if data.size == 0:
        raise AudioError("O arquivo não contém áudio.")
    return data.reshape(-1, 2).T.copy()


def save_wav_float(path: str | Path, audio: np.ndarray, sr: int | None = None) -> Path:
    """Salva o stem 'mestre' em WAV float32 (sem perda e sem risco de clipping)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, np.ascontiguousarray(audio.T), sr or settings.sample_rate, subtype="FLOAT")
    return path


def read_wav(path: str | Path) -> np.ndarray:
    data, _ = sf.read(str(path), dtype="float32", always_2d=True)
    return data.T.copy()


# --------------------------------------------------------------------------
# Exportação nos formatos que o usuário escolhe
# --------------------------------------------------------------------------

EXPORT_FORMATS = {
    "wav16": {"ext": "wav", "label": "WAV 16 bits"},
    "wav24": {"ext": "wav", "label": "WAV 24 bits"},
    "flac": {"ext": "flac", "label": "FLAC"},
    "mp3": {"ext": "mp3", "label": "MP3 320 kbps"},
}


def protect_clipping(audio: np.ndarray) -> np.ndarray:
    """Se o pico passar de 0 dBFS (comum ao somar stems num mix), reduz o ganho do todo."""
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    if peak > 0.999:
        audio = audio * (0.999 / peak)
    return audio


def export_audio(audio: np.ndarray, dest: str | Path, fmt: str, sr: int | None = None) -> Path:
    """Grava ``audio`` em ``dest`` no formato pedido (wav16, wav24, flac, mp3)."""
    if fmt not in EXPORT_FORMATS:
        raise AudioError(f"Formato desconhecido: {fmt}")
    sr = sr or settings.sample_rate
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Clip duro (não normaliza) para não alterar o equilíbrio entre stems.
    # Mixes passam antes por protect_clipping().
    audio = np.clip(audio, -1.0, 1.0)
    frames = np.ascontiguousarray(audio.T)

    if fmt == "wav16":
        sf.write(dest, frames, sr, subtype="PCM_16")
    elif fmt == "wav24":
        sf.write(dest, frames, sr, subtype="PCM_24")
    elif fmt == "flac":
        sf.write(dest, frames, sr, subtype="PCM_24", format="FLAC")
    elif fmt == "mp3":
        encode_mp3(audio, dest, sr, bitrate="320k")
    return dest


def encode_mp3(audio: np.ndarray, dest: str | Path, sr: int, bitrate: str) -> Path:
    """Codifica MP3 CBR via ffmpeg (libmp3lame), alimentando PCM pelo stdin."""
    cmd = [
        require_ffmpeg(), "-v", "error", "-nostdin", "-y",
        "-f", "f32le", "-ar", str(sr), "-ac", "2", "-i", "-",
        "-codec:a", "libmp3lame", "-b:a", bitrate, str(dest),
    ]
    pcm = np.ascontiguousarray(np.clip(audio, -1.0, 1.0).T, dtype=np.float32).tobytes()
    proc = subprocess.run(cmd, input=pcm, capture_output=True)
    if proc.returncode != 0:
        raise AudioError("Falha ao gerar MP3: " + proc.stderr.decode(errors="ignore")[-300:])
    return Path(dest)


def pitch_shift(audio: np.ndarray, semitones: int, sr: int | None = None) -> np.ndarray:
    """Transpõe o tom sem alterar a duração, usando o filtro rubberband do ffmpeg.

    Se o ffmpeg não tiver rubberband compilado, cai para o librosa (qualidade menor).
    """
    if semitones == 0:
        return audio
    sr = sr or settings.sample_rate
    ratio = 2 ** (semitones / 12)
    cmd = [
        require_ffmpeg(), "-v", "error", "-nostdin",
        "-f", "f32le", "-ar", str(sr), "-ac", "2", "-i", "-",
        "-af", f"rubberband=pitch={ratio:.6f}:pitchq=quality:transients=crisp",
        "-f", "f32le", "-ar", str(sr), "-ac", "2", "-",
    ]
    pcm = np.ascontiguousarray(audio.T, dtype=np.float32).tobytes()
    proc = subprocess.run(cmd, input=pcm, capture_output=True)
    if proc.returncode == 0 and proc.stdout:
        out = np.frombuffer(proc.stdout, dtype=np.float32).reshape(-1, 2).T
        n = audio.shape[1]
        return np.pad(out, ((0, 0), (0, max(0, n - out.shape[1]))))[:, :n].copy()

    import librosa  # fallback mais lento

    return np.stack([librosa.effects.pitch_shift(ch, sr=sr, n_steps=semitones) for ch in audio]).astype(np.float32)


def compute_peaks(audio: np.ndarray, points: int = 1200) -> list[float]:
    """Resumo da forma de onda (pico por bloco, 0..1) para desenhar no navegador."""
    mono = np.max(np.abs(audio), axis=0)
    if mono.size == 0:
        return [0.0] * points
    block = max(1, mono.size // points)
    trimmed = mono[: block * (mono.size // block)].reshape(-1, block)
    peaks = trimmed.max(axis=1)
    return [round(float(p), 4) for p in np.clip(peaks, 0, 1)]
