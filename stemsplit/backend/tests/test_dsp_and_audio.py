import numpy as np

from conftest import SR, tone
from stemsplit import analysis, audio_io
from stemsplit.separators import dsp


def _energy(x: np.ndarray) -> float:
    return float(np.mean(x**2))


def test_split_guitar_reconstructs_input(song):
    parts = dsp.split_guitar(song, SR)
    assert set(parts) == {"guitarra_1", "guitarra_2", "guitarra_solo", "guitarra_base"}
    total = sum(parts.values())
    # As máscaras somam 1: a soma das partes reconstrói o stem original.
    assert np.max(np.abs(total - song)) < 1e-3


def test_split_guitar_routes_by_panning():
    # Nota só no canal esquerdo → Guitarra 1.
    left_only = np.stack([tone(220), np.zeros(SR * 2, np.float32)])
    p = dsp.split_guitar(left_only, SR)
    assert _energy(p["guitarra_1"]) > 0.9 * _energy(left_only)
    # Nota aguda sustentada no centro → guitarra solo.
    center = np.stack([tone(880), tone(880)])
    p = dsp.split_guitar(center, SR)
    assert _energy(p["guitarra_solo"]) > 0.7 * _energy(center)
    assert _energy(p["guitarra_1"]) < 0.01 * _energy(center)


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
