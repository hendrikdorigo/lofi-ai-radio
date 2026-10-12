"""Geração dos arquivos para download e das prévias transpostas.

Tudo é gerado sob demanda e guardado em ``exports/`` (cache): pedir o mesmo
arquivo duas vezes não reprocessa nada.
"""

from __future__ import annotations

import hashlib
import json
import threading
import zipfile
from pathlib import Path

import numpy as np

from . import audio_io
from .config import settings
from .jobs import Job

MAX_SEMITONES = 12
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock_for(path: Path) -> threading.Lock:
    """Um lock por arquivo de saída: dois pedidos iguais não geram o arquivo duas vezes."""
    with _locks_guard:
        return _locks.setdefault(str(path), threading.Lock())


def _check(job: Job, stem: str | None = None, fmt: str | None = None, semitones: int = 0) -> None:
    if job.status != "concluido":
        raise ValueError("Esta música ainda não terminou de ser processada.")
    if stem is not None and stem not in job.stem_names():
        raise ValueError(f"Stem inexistente: {stem}")
    if fmt is not None and fmt not in audio_io.EXPORT_FORMATS:
        raise ValueError(f"Formato inválido: {fmt}. Use: {', '.join(audio_io.EXPORT_FORMATS)}")
    if abs(semitones) > MAX_SEMITONES:
        raise ValueError(f"Transposição deve ficar entre -{MAX_SEMITONES} e +{MAX_SEMITONES} semitons.")


def _suffix(semitones: int) -> str:
    return f"_tom{semitones:+d}" if semitones else ""


def _load_stem(job: Job, stem: str, semitones: int) -> np.ndarray:
    audio = audio_io.read_wav(job.dir / "stems" / f"{stem}.wav")
    return audio_io.pitch_shift(audio, semitones)


def preview_path(job: Job, stem: str, semitones: int = 0) -> Path:
    """MP3 leve para o player. Com transposição, gera (e guarda) na primeira chamada."""
    _check(job, stem, semitones=semitones)
    path = job.dir / "previews" / f"{stem}{_suffix(semitones)}.mp3"
    with _lock_for(path):
        if not path.exists():
            audio = _load_stem(job, stem, semitones)
            tmp = path.with_suffix(".tmp.mp3")
            audio_io.encode_mp3(audio, tmp, settings.sample_rate, settings.preview_bitrate)
            tmp.replace(path)
    return path


def peaks(job: Job) -> dict:
    path = job.dir / "peaks.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def stem_file(job: Job, stem: str, fmt: str, semitones: int = 0) -> tuple[Path, str]:
    """Arquivo de um stem no formato pedido. Devolve (caminho, nome para download)."""
    _check(job, stem, fmt, semitones)
    ext = audio_io.EXPORT_FORMATS[fmt]["ext"]
    path = job.dir / "exports" / f"{stem}{_suffix(semitones)}_{fmt}.{ext}"
    with _lock_for(path):
        if not path.exists():
            _write_atomic(path, lambda tmp: audio_io.export_audio(_load_stem(job, stem, semitones), tmp, fmt))
    return path, f"{job.title} - {stem}{_suffix(semitones)}.{ext}"


def zip_all(job: Job, fmt: str, semitones: int = 0) -> tuple[Path, str]:
    """ZIP com todos os stems no formato pedido."""
    _check(job, fmt=fmt, semitones=semitones)
    path = job.dir / "exports" / f"todos{_suffix(semitones)}_{fmt}.zip"
    with _lock_for(path):
        if not path.exists():
            files = [stem_file(job, s, fmt, semitones) for s in job.stem_names()]

            def build(tmp: Path) -> None:
                # Áudio já é comprimido (MP3/FLAC); ZIP_STORED é bem mais rápido.
                with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED) as zf:
                    for file_path, name in files:
                        zf.write(file_path, arcname=name)

            _write_atomic(path, build)
    return path, f"{job.title} - stems{_suffix(semitones)}.zip"


def mix(job: Job, gains: dict[str, float], fmt: str, semitones: int = 0) -> tuple[Path, str]:
    """Mix personalizado: soma só os stems pedidos, cada um com seu volume (0..1.5)."""
    _check(job, fmt=fmt, semitones=semitones)
    active = {s: float(g) for s, g in gains.items() if s in job.stem_names() and float(g) > 0}
    if not active:
        raise ValueError("Nenhum canal ativo para mixar. Desmute pelo menos um stem.")
    active = {s: min(g, 1.5) for s, g in active.items()}

    key = hashlib.sha1(json.dumps([sorted(active.items()), fmt, semitones]).encode()).hexdigest()[:10]
    ext = audio_io.EXPORT_FORMATS[fmt]["ext"]
    path = job.dir / "exports" / f"mix_{key}.{ext}"
    with _lock_for(path):
        if not path.exists():
            total = None
            for stem, gain in active.items():
                audio = audio_io.read_wav(job.dir / "stems" / f"{stem}.wav") * gain
                total = audio if total is None else total + audio
            total = audio_io.protect_clipping(audio_io.pitch_shift(total, semitones))
            _write_atomic(path, lambda tmp: audio_io.export_audio(total, tmp, fmt))
    return path, f"{job.title} - mix personalizado{_suffix(semitones)}.{ext}"


def _write_atomic(path: Path, writer) -> None:
    """Escreve num arquivo temporário e renomeia: nunca serve arquivo pela metade."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".tmp_{path.name}")
    writer(tmp)
    tmp.replace(path)
