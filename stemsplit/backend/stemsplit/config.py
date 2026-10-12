"""Configuração central do StemSplit.

Tudo pode ser sobrescrito por variáveis de ambiente (prefixo ``STEMSPLIT_``),
o que facilita rodar igual no terminal, no Docker ou num servidor.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(name: str, default: str) -> str:
    return os.environ.get(f"STEMSPLIT_{name}", default)


@dataclass(frozen=True)
class Settings:
    # Pasta onde ficam uploads, stems gerados e o histórico (job.json).
    data_dir: Path = field(default_factory=lambda: Path(_env("DATA_DIR", "./data")).resolve())

    # Pasta de cache dos modelos (pesos baixados na primeira execução).
    models_dir: Path = field(default_factory=lambda: Path(_env("MODELS_DIR", "./models")).resolve())

    # "auto" escolhe CUDA > MPS (Mac) > CPU. Também aceita "cuda", "cpu", "mps".
    device: str = field(default_factory=lambda: _env("DEVICE", "auto"))

    # Modelos Demucs usados nos modos Rápido (4 stems) e Completo/Detalhado (6 stems).
    demucs_4s_model: str = field(default_factory=lambda: _env("DEMUCS_4S_MODEL", "htdemucs"))
    demucs_6s_model: str = field(default_factory=lambda: _env("DEMUCS_6S_MODEL", "htdemucs_6s"))

    # Modelos do audio-separator (RoFormer). Nomes conforme `audio-separator --list_models`.
    # Vocal x instrumental de alta qualidade:
    vocal_model: str = field(
        default_factory=lambda: _env("VOCAL_MODEL", "model_bs_roformer_ep_317_sdr_12.9755.ckpt")
    )
    # Modelo "karaokê": separa voz principal (lead) do resto (backing vocals).
    karaoke_model: str = field(
        default_factory=lambda: _env(
            "KARAOKE_MODEL", "mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.ckpt"
        )
    )
    # Opcional: modelo específico de guitarra (ex.: um Mel-Band RoFormer de guitarra).
    # Vazio = usa a guitarra do Demucs. Quando definido, substitui o stem de guitarra.
    guitar_model: str = field(default_factory=lambda: _env("GUITAR_MODEL", ""))
    # Opcional: modelo de separação de bateria (ex.: MDX23C DrumSep). Vazio = filtros DSP.
    drum_model: str = field(default_factory=lambda: _env("DRUM_MODEL", ""))

    # Sobreposição dos blocos nos modelos RoFormer: maior = um pouco melhor e bem mais lento.
    # "auto" usa 8 (padrão do UVR) em GPU e 2 em CPU (medido: ~1,5x mais rápido em CPU).
    roformer_overlap: str = field(default_factory=lambda: _env("ROFORMER_OVERLAP", "auto"))

    # Limite de upload em MB.
    max_upload_mb: int = field(default_factory=lambda: int(_env("MAX_UPLOAD_MB", "200")))

    # Bitrate das prévias em MP3 usadas pelo player do navegador.
    preview_bitrate: str = field(default_factory=lambda: _env("PREVIEW_BITRATE", "192k"))

    # Taxa de amostragem interna (os modelos trabalham em 44.1 kHz).
    sample_rate: int = 44100

    @property
    def jobs_dir(self) -> Path:
        return self.data_dir / "jobs"

    def ensure_dirs(self) -> None:
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.models_dir.mkdir(parents=True, exist_ok=True)
        # Demucs usa o cache do torch.hub; apontamos para a mesma pasta de modelos.
        os.environ.setdefault("TORCH_HOME", str(self.models_dir / "torch"))


ALLOWED_EXTENSIONS = {".mp3", ".wav", ".flac", ".m4a", ".ogg", ".aac"}

settings = Settings()
