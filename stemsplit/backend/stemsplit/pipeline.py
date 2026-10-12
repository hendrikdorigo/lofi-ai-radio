"""Pipeline de separação em cascata para os três modos do StemSplit.

Rápido     → Demucs htdemucs: voz, bateria, baixo, outros.
Completo   → Demucs htdemucs_6s: + guitarra e teclado/piano.
Detalhado  → 1) RoFormer separa voz x instrumental (melhor qualidade de voz)
             2) Demucs 6s no instrumental: bateria, baixo, guitarra, teclado, outros
             3) RoFormer "karaokê" na voz: voz principal x backing vocals
             4) (opcional) modelo específico de guitarra
             5) DSP na guitarra: guitarra 1/2 (L/R), solo e base (centro)
             6) (opcional) bateria em bumbo, caixa e pratos

Se algum modelo RoFormer não estiver disponível, o pipeline continua com o
melhor resultado possível e registra um aviso (em vez de falhar).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

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
        "description": "Voz principal x backing vocals, guitarra solo/base e guitarra 1/2. "
        "Bem mais lento e a separação fina das guitarras é uma estimativa.",
        "stems": [
            "vocal_principal", "backing_vocals", "guitarra_solo", "guitarra_base",
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
) -> SeparationResult:
    if mode not in MODES:
        raise ValueError(f"Modo inválido: {mode}. Use: {', '.join(MODES)}")
    start = time.time()
    sr = settings.sample_rate
    warnings: list[str] = []

    if mode == "detalhado":
        stems = _detailed(audio, split_drums, warnings, progress)
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


def _detailed(audio, split_drums, warnings, progress) -> dict[str, np.ndarray]:
    from .separators import roformer_backend as rf

    sr = settings.sample_rate
    plan = [
        ("Isolando a voz (BS-RoFormer)", 0.30),
        ("Separando instrumentos (Demucs 6 stems)", 0.45),
        ("Separando voz principal e backing vocals", 0.20),
    ]
    if settings.guitar_model:
        plan.append(("Refinando guitarra (modelo de guitarra)", 0.20))
    plan.append(("Dividindo guitarras (solo/base, esquerda/direita)", 0.05))
    if split_drums:
        plan.append((DRUM_STAGE, 0.05))
    st = _Stages(plan, progress)

    # 1) Voz x instrumental com RoFormer.
    p = st.next()
    vocal_split = _try_roformer(lambda: rf.split_two(audio, settings.vocal_model, "vocals", p), warnings, "Voz em alta qualidade")

    # 2) Demucs 6 stems no instrumental (ou no mix, se o RoFormer falhou).
    p = st.next()
    if vocal_split is not None:
        vocals, instrumental = vocal_split
        stems = demucs_backend.separate(instrumental, settings.demucs_6s_model, p)
        # Restos de voz que o Demucs achou no instrumental vão para "outros".
        stems["outros"] = stems["outros"] + stems.pop("vocal")
    else:
        stems = demucs_backend.separate(audio, settings.demucs_6s_model, p)
        vocals = stems.pop("vocal")

    # 3) Voz principal x backing vocals.
    p = st.next()
    lead_split = _try_roformer(
        lambda: rf.split_two(vocals, settings.karaoke_model, "vocals", p), warnings, "Voz principal x backing"
    )
    if lead_split is not None:
        stems["vocal_principal"], stems["backing_vocals"] = lead_split
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
        warnings.append("A guitarra está praticamente em mono: Guitarra 1 e 2 devem sair quase vazias.")
    stems.update(dsp.split_guitar(guitar, sr, p))

    # 6) Bateria em bumbo, caixa e pratos (opcional).
    if split_drums:
        stems.update(_split_drums(stems.pop("bateria"), sr, warnings, st.next()))
    return stems


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
