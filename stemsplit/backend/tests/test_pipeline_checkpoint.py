"""O modo Detalhado retoma de onde parou usando os checkpoints em disco."""

import numpy as np
import pytest

from conftest import tone


def test_detailed_resumes_from_checkpoints(tmp_path, monkeypatch):
    from stemsplit import pipeline
    from stemsplit.separators import demucs_backend, roformer_backend

    calls = {"rf": 0, "demucs": 0}

    def fake_split_two(audio, model, primary, progress):
        calls["rf"] += 1
        return audio * 0.5, audio * 0.5

    def fake_demucs(audio, model, progress):
        calls["demucs"] += 1
        if calls["demucs"] == 1:
            raise MemoryError("simulando falta de memória")
        names = ["vocal", "bateria", "baixo", "outros", "guitarra", "teclado"]
        return {n: audio / len(names) for n in names}

    monkeypatch.setattr(roformer_backend, "split_two", fake_split_two)
    monkeypatch.setattr(demucs_backend, "separate", fake_demucs)
    audio = np.stack([tone(220), tone(330)])
    cache = tmp_path / "cache"

    with pytest.raises(MemoryError):
        pipeline.separate(audio, "detalhado", cache_dir=cache)
    assert calls == {"rf": 1, "demucs": 1}
    assert (cache / "1_voz" / "ok").exists()

    # Segunda tentativa: a etapa de voz vem do disco, não roda de novo.
    result = pipeline.separate(audio, "detalhado", cache_dir=cache)
    assert calls == {"rf": 2, "demucs": 2}  # +1 karaokê, +1 demucs; voz não foi refeita
    assert "vocal_principal" in result.stems and "guitarra_solo" in result.stems
    total = sum(result.stems.values())
    assert np.max(np.abs(total - audio)) < 1e-3  # nada se perde entre as etapas
