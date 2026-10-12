import numpy as np

from conftest import SR, tone
from stemsplit import analysis, audio_io
from stemsplit.separators import dsp


def _energy(x: np.ndarray) -> float:
    return float(np.mean(x**2))


GUITAR_KEYS = {"guitarra_1", "guitarra_2", "guitarra_solo", "guitarra_dueto", "guitarra_base"}


def test_split_guitar_reconstructs_input(song):
    parts = dsp.split_guitar(song, SR)
    assert set(parts) == GUITAR_KEYS
    total = sum(parts.values())
    # As máscaras somam 1: a soma das partes reconstrói o stem original.
    assert np.max(np.abs(total - song)) < 1e-3


def _chords(seconds: float = 6.0) -> np.ndarray:
    """Base sintética: power chords graves e distorcidos (o "fundo" da música)."""
    t = np.arange(int(SR * seconds)) / SR
    x = np.tanh(3 * (np.sin(2 * np.pi * 82.4 * t) + np.sin(2 * np.pi * 123.5 * t)))
    return (0.2 * x).astype(np.float32)


def _with_melody_after(base: np.ndarray, freq: float, start: float) -> np.ndarray:
    """Acrescenta uma nota de guitarra (timbre rico em harmônicos) a partir de ``start``."""
    t = np.arange(base.size) / SR
    note = sum(np.sin(2 * np.pi * k * freq * t) / k for k in range(1, 9))
    return (base + 0.2 * np.tanh(2 * note) * (t > start)).astype(np.float32)


def _band_energy(x: np.ndarray, freq: float) -> float:
    spectrum = np.abs(np.fft.rfft(x.mean(axis=0)))
    freqs = np.fft.rfftfreq(x.shape[1], 1 / SR)
    return float(spectrum[np.abs(freqs - freq) < 5].sum() ** 2)


def test_split_guitar_center_duet_goes_to_solo_and_duet():
    base = _chords()
    mono = _with_melody_after(_with_melody_after(base, 880.0, 2.0), 698.5, 2.0)  # terça maior
    p = dsp.split_guitar(np.stack([mono, mono]), SR)
    assert _band_energy(p["guitarra_solo"], 880.0) > 5 * _band_energy(p["guitarra_dueto"], 880.0)
    assert _band_energy(p["guitarra_dueto"], 698.5) > 5 * _band_energy(p["guitarra_solo"], 698.5)


def test_split_guitar_keeps_sides_in_their_channel():
    left = _with_melody_after(_chords(), 880.0, 2.0)
    p = dsp.split_guitar(np.stack([left, np.zeros_like(left)]), SR)
    for name, part in p.items():
        assert _energy(part[1:]) < 1e-6 * _energy(left), name  # nada vaza para a direita
    assert _band_energy(p["guitarra_solo"], 880.0) > _band_energy(p["guitarra_1"], 880.0)


def test_split_drums_bands():
    kick = np.stack([tone(55), tone(55)])
    parts = dsp.split_drums(kick, SR)
    assert _energy(parts["bumbo"]) > 0.95 * _energy(kick)
    total = sum(parts.values())
    assert np.max(np.abs(total - kick)) < 1e-3


def test_stereo_width():
    mono = np.stack([tone(440), tone(440)])
    assert dsp.stereo_width(mono) < 0.01
    assert dsp.stereo_width(np.stack([tone(440), -tone(440)])) > 0.9


def test_export_and_load_roundtrip(tmp_path, song):
    for fmt in audio_io.EXPORT_FORMATS:
        dest = tmp_path / f"x.{audio_io.EXPORT_FORMATS[fmt]['ext']}"
        audio_io.export_audio(song, dest, fmt)
        back = audio_io.load_audio(dest)
        assert back.shape[0] == 2
        assert abs(back.shape[1] - song.shape[1]) < SR * 0.1


def test_pitch_shift_keeps_length(song):
    shifted = audio_io.pitch_shift(song, 2)
    assert shifted.shape == song.shape


def test_analysis_detects_key_and_bpm():
    # Acorde de Lá menor (A-C-E) com "batida" a 120 BPM.
    seconds = 10
    chord = tone(220, seconds) + tone(261.63, seconds) + tone(329.63, seconds)
    t = np.arange(SR * seconds) / SR
    clicks = (np.sin(2 * np.pi * 60 * t) * (np.mod(t, 0.5) < 0.03)).astype(np.float32)
    audio = np.stack([chord + clicks, chord + clicks])
    info = analysis.analyze(audio, SR)
    assert info["key"] in ("Am", "C")  # relativas compartilham as mesmas notas
    assert info["bpm"] is not None
    assert min(abs(info["bpm"] - 120), abs(info["bpm"] - 60), abs(info["bpm"] - 240)) < 3


def test_compute_peaks():
    peaks = audio_io.compute_peaks(np.stack([tone(440), tone(440)]), points=100)
    assert len(peaks) == 100
    assert 0.25 < max(peaks) <= 0.31
