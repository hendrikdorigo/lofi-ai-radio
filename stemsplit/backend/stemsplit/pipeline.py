"""Pipeline de separação em cascata para os três modos do StemSplit.

Rápido     → Demucs htdemucs: voz, bateria, baixo, outros.
Completo   → Demucs htdemucs_6s: + guitarra e teclado/piano.
Detalhado  → 1) RoFormer separa voz x instrumental (melhor qualidade de voz)
             2) Demucs 6s no instrumental: bateria, baixo, guitarra, teclado, outros
             3) RoFormer "karaokê" na voz: voz principal x backing vocals
             4) (opcional) modelo específico de guitarra
             5) DSP na guitarra: solo, dueto (2ª voz) e base esquerda/direita/centro
             6) (opcional) bateria em bumbo, caixa e pratos

Se algum modelo RoFormer não estiver disponível, o pipeline continua com o
melhor resultado possível e registra um aviso (em vez de falhar).
"""

from __future__ import annotations

import time
from pathlib import Path
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from . import audio_io
from .config import settings
from .separators import demucs_backend, dsp

MODES = {
    "rapido": {
        "label": "Rápido",
        "description": "4 stems: voz, bateria, baixo e outros.",
        "stems": ["vocal", "bateria", "baixo", "outros"],
        "stage": "Separando voz, bateria, baixo e outros (Demucs)",
    },
    "completo": {
        "label": "Completo",
        "description": "6 stems: inclui guitarra e teclado/piano.",
        "stems": ["vocal", "guitarra", "baixo", "bateria", "teclado", "outros"],
        "stage": "Separando voz, guitarra, piano, baixo e bateria (Demucs 6 stems)",
    },
    "detalhado": {
        "label": "Detalhado",
        "description": "Voz principal x backing vocals, guitarra solo, dueto e base. "
        "Bem mais lento e a separação fina das guitarras é uma estimativa.",
        "stems": [
            "vocal_principal", "backing_vocals", "guitarra_solo", "guitarra_dueto", "guitarra_base",
            "guitarra_1", "guitarra_2", "baixo", "bateria", "teclado", "outros",
        ],
    },
}

DRUM_STAGE = "Dividindo a bateria (bumbo, caixa, pratos)"

# Callback: (mensagem da etapa, progresso total 0..1)
StageProgress = Callable[[str, float], None]


@dataclass
class SeparationResult:
    stems: dict[str, np.ndarray]
    warnings: list[str] = field(default_factory=list)
    seconds: float = 0.0


class _Stages:
    """Converte o progresso de cada etapa (0..1) em progresso total ponderado."""

    def __init__(self, plan: list[tuple[str, float]], report: StageProgress):
        total = sum(w for _, w in plan)
        self._plan = [(name, w / total) for name, w in plan]
        self._report = report
        self._index = -1
        self._base = 0.0

    def next(self) -> Callable[[float], None]:
        if self._index >= 0:
            self._base += self._plan[self._index][1]
        self._index += 1
        name, weight = self._plan[self._index]
        base = self._base

        def progress(frac: float) -> None:
            self._report(name, min(0.999, base + weight * max(0.0, min(1.0, frac))))

        progress(0.0)
        return progress


def _try_roformer(fn, warnings: list[str], what: str):
    """Executa uma etapa RoFormer; se falhar, registra aviso e devolve None."""
    try:
        return fn()
    except ImportError:
        warnings.append(f"{what}: pacote audio-separator não instalado — usando alternativa.")
    except Exception as exc:  # noqa: BLE001 - qualquer falha de modelo vira aviso
        warnings.append(f"{what}: modelo indisponível ({exc}) — usando alternativa.")
    return None


def separate(
    audio: np.ndarray,
    mode: str = "completo",
    split_drums: bool = False,
    progress: StageProgress = lambda *_: None,
    cache_dir: Path | None = None,
    vocal_quality: str = "rapida",
) -> SeparationResult:
    """Separa ``audio`` no modo pedido.

    ``cache_dir`` guarda etapas intermediárias (modo Detalhado). ``vocal_quality``
    ("rapida" ou "melhor") escolhe o modelo de voz principal x backing vocals.
    """
    if mode not in MODES:
        raise ValueError(f"Modo inválido: {mode}. Use: {', '.join(MODES)}")
    start = time.time()
    sr = settings.sample_rate
    warnings: list[str] = []

    if mode == "detalhado":
        stems = _detailed(audio, split_drums, warnings, progress, cache_dir, vocal_quality)
    else:
        model = settings.demucs_4s_model if mode == "rapido" else settings.demucs_6s_model
        plan = [(MODES[mode]["stage"], 1.0)]
        if split_drums:
            plan.append((DRUM_STAGE, 0.05))
        st = _Stages(plan, progress)
        stems = demucs_backend.separate(audio, model, st.next())
        if split_drums:
            stems.update(_split_drums(stems.pop("bateria"), sr, warnings, st.next()))

    return SeparationResult(stems=stems, warnings=warnings, seconds=time.time() - start)


# Modelos de voz por dispositivo quando a configuração é "auto": (GPU, CPU).
AUTO_MODELS = {
    "vocal": ("model_bs_roformer_ep_317_sdr_12.9755.ckpt", "UVR-MDX-NET-Voc_FT.onnx"),
    "karaoke": ("mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.ckpt", "UVR_MDXNET_KARA_2.onnx"),
}


VOCAL_QUALITIES = ("rapida", "melhor")


def resolve_model(kind: str, quality: str = "rapida") -> str:
    """Nome do modelo de voz a usar.

    O configurado tem prioridade. Em "auto": RoFormer em GPU; em CPU, MDX-Net
    (rápido) — exceto o modelo de voz principal x backing com qualidade
    "melhor", que usa o RoFormer mesmo em CPU (medido: ~6x mais lento, bem
    mais preciso; nota 8,4 x 5,4 no catálogo do audio-separator).
    """
    from .device import get_device

    configured = settings.vocal_model if kind == "vocal" else settings.karaoke_model
    if configured != "auto":
        return configured
    gpu_model, cpu_model = AUTO_MODELS[kind]
    if kind == "karaoke" and quality == "melhor":
        return gpu_model
    return gpu_model if get_device() in ("cuda", "mps") else cpu_model


def split_lead_backing(vocals: np.ndarray, quality: str, progress) -> dict[str, np.ndarray]:
    """Separa uma faixa de voz em voz principal e backing vocals (usado também para refazer)."""
    from .separators import roformer_backend as rf

    lead, backing = rf.split_two(vocals, resolve_model("karaoke", quality), "vocals", progress)
    return {"vocal_principal": lead, "backing_vocals": backing}


def _model_label(model: str) -> str:
    name = model.lower()
    if "roformer" in name:
        return "BS-RoFormer" if "bs_roformer" in name else "Mel-Band RoFormer"
    if "mdx" in name:
        return "MDX-Net"
    return model


def _detailed(audio, split_drums, warnings, progress, cache_dir: Path | None, vocal_quality: str = "rapida") -> dict[str, np.ndarray]:
    from .separators import roformer_backend as rf

    sr = settings.sample_rate
    vocal_model, karaoke_model = resolve_model("vocal"), resolve_model("karaoke", vocal_quality)
    plan = [
        (f"Isolando a voz ({_model_label(vocal_model)})", 0.30),
        ("Separando instrumentos (Demucs 6 stems)", 0.45),
        (f"Separando voz principal e backing vocals ({_model_label(karaoke_model)})", 0.20),
    ]
    if settings.guitar_model:
        plan.append(("Refinando guitarra (modelo de guitarra)", 0.20))
    plan.append(("Dividindo guitarras (solo, dueto e base)", 0.05))
    if split_drums:
        plan.append((DRUM_STAGE, 0.05))
    st = _Stages(plan, progress)

    # As 3 etapas pesadas salvam o resultado em cache_dir: se o processo cair
    # (ex.: falta de memória), a próxima tentativa continua de onde parou.

    # 1) Voz x instrumental com RoFormer.
    p = st.next()

    def vocal_step():
        r = _try_roformer(lambda: rf.split_two(audio, vocal_model, "vocals", p), warnings, "Voz em alta qualidade")
        return None if r is None else {"voz": r[0], "instrumental": r[1]}

    vocal_split = _checkpoint(cache_dir, f"1_voz_{vocal_model}", p, vocal_step)

    # 2) Demucs 6 stems no instrumental (ou no mix, se o RoFormer falhou).
    p = st.next()
    if vocal_split is not None:
        vocals, instrumental = vocal_split["voz"], vocal_split["instrumental"]
        stems = _checkpoint(cache_dir, "2_demucs_instrumental", p, lambda: demucs_backend.separate(instrumental, settings.demucs_6s_model, p))
        # Restos de voz que o Demucs achou no instrumental vão para "outros".
        stems["outros"] = stems["outros"] + stems.pop("vocal")
    else:
        stems = _checkpoint(cache_dir, "2_demucs_mix", p, lambda: demucs_backend.separate(audio, settings.demucs_6s_model, p))
        vocals = stems.pop("vocal")

    # 3) Voz principal x backing vocals.
    p = st.next()

    def lead_step():
        r = _try_roformer(lambda: rf.split_two(vocals, karaoke_model, "vocals", p), warnings, "Voz principal x backing")
        return None if r is None else {"vocal_principal": r[0], "backing_vocals": r[1]}

    lead_split = _checkpoint(cache_dir, f"3_karaoke_{karaoke_model}", p, lead_step)
    if lead_split is not None:
        stems.update(lead_split)
    else:
        stems["vocal"] = vocals

    # 4) Guitarra com modelo dedicado (opcional).
    if settings.guitar_model:
        p = st.next()
        source = instrumental if vocal_split is not None else audio
        gsplit = _try_roformer(lambda: rf.split_two(source, settings.guitar_model, "guitar", p), warnings, "Modelo de guitarra")
        if gsplit is not None:
            # Mantém a soma dos stems igual ao original: a diferença vai para "outros".
            stems["outros"] = stems["outros"] + stems["guitarra"] - gsplit[0]
            stems["guitarra"] = gsplit[0]

    # 5) Divisão fina das guitarras.
    p = st.next()
    guitar = stems.pop("guitarra")
    if dsp.stereo_width(guitar) < 0.02:
        warnings.append("A guitarra está praticamente em mono: Base esquerda e direita devem sair quase vazias.")
    stems.update(dsp.split_guitar(guitar, sr, p))

    # 6) Bateria em bumbo, caixa e pratos (opcional).
    if split_drums:
        stems.update(_split_drums(stems.pop("bateria"), sr, warnings, st.next()))
    return stems


def _checkpoint(cache_dir: Path | None, key: str, progress, fn) -> dict[str, np.ndarray] | None:
    """Executa ``fn()`` (que devolve ``{nome: áudio}`` ou None) guardando o resultado em disco.

    Se a etapa já foi concluída numa tentativa anterior, só carrega os arquivos.
    """
    if cache_dir is None:
        return fn()
    folder = cache_dir / key
    if (folder / "ok").exists():
        progress(1.0)
        return {f.stem: audio_io.read_wav(f) for f in sorted(folder.glob("*.wav"))}
    result = fn()
    if result is not None:
        folder.mkdir(parents=True, exist_ok=True)
        for name, x in result.items():
            audio_io.save_wav_float(folder / f"{name}.wav", x)
        (folder / "ok").touch()
    return result


def _split_drums(drums: np.ndarray, sr: int, warnings: list[str], progress) -> dict[str, np.ndarray]:
    if settings.drum_model:
        from .separators import roformer_backend as rf

        parts = _try_roformer(lambda: rf.separate(drums, settings.drum_model, progress), warnings, "Modelo de bateria")
        if parts:
            out = {"bumbo": np.zeros_like(drums), "caixa": np.zeros_like(drums), "pratos": np.zeros_like(drums)}
            for label, x in parts.items():
                x = x[:, : drums.shape[1]]
                if "kick" in label:
                    out["bumbo"][:, : x.shape[1]] += x
                elif any(k in label for k in ("hh", "hat", "ride", "crash", "cymbal")):
                    out["pratos"][:, : x.shape[1]] += x
                else:
                    out["caixa"][:, : x.shape[1]] += x
            return out
    return dsp.split_drums(drums, sr, progress)
