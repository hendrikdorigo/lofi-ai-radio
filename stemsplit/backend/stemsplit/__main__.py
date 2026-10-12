"""Linha de comando do StemSplit.

Exemplos::

    python -m stemsplit separar musica.mp3
    python -m stemsplit separar musica.mp3 --modo detalhado --bateria --formato wav24 --saida ./stems
    python -m stemsplit analisar musica.mp3
    python -m stemsplit servidor --porta 8000
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


def _bar(stage: str, frac: float) -> None:
    width = 30
    filled = int(width * frac)
    sys.stdout.write(f"\r[{'#' * filled}{'.' * (width - filled)}] {frac * 100:5.1f}%  {stage[:60]:<60}")
    sys.stdout.flush()


def cmd_separar(args: argparse.Namespace) -> int:
    from . import analysis, audio_io, pipeline
    from .config import settings
    from .device import device_label

    settings.ensure_dirs()
    src = Path(args.arquivo)
    if not src.exists():
        print(f"Arquivo não encontrado: {src}")
        return 1
    out_dir = Path(args.saida or f"{src.stem}_stems")
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"StemSplit — modo {pipeline.MODES[args.modo]['label']} em {device_label()}")
    start = time.time()
    audio = audio_io.load_audio(src)
    info = analysis.analyze(audio, settings.sample_rate)
    print(f"Duração: {info['duration']:.0f}s  |  BPM: {info['bpm'] or '?'}  |  Tom: {info['key_label'] or '?'}")

    result = pipeline.separate(audio, args.modo, args.bateria, _bar)
    _bar("Salvando arquivos", 1.0)
    print()

    ext = audio_io.EXPORT_FORMATS[args.formato]["ext"]
    for name, stem in result.stems.items():
        dest = out_dir / f"{name}.{ext}"
        audio_io.export_audio(stem, dest, args.formato)
        print(f"  ✔ {dest}")
    for w in result.warnings:
        print(f"  ⚠ {w}")
    print(f"Concluído em {time.time() - start:.0f}s. Stems em: {out_dir.resolve()}")
    return 0


def cmd_analisar(args: argparse.Namespace) -> int:
    from . import analysis, audio_io
    from .config import settings

    info = analysis.analyze(audio_io.load_audio(args.arquivo), settings.sample_rate)
    print(f"Duração: {info['duration']:.1f}s")
    print(f"BPM: {info['bpm'] or 'não detectado'}")
    print(f"Tom: {info['key_label'] or 'não detectado'} ({info['key'] or '-'})")
    return 0


def cmd_servidor(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run("stemsplit.api:app", host=args.host, port=args.porta)
    return 0


def main(argv: list[str] | None = None) -> int:
    from .audio_io import EXPORT_FORMATS
    from .pipeline import MODES

    parser = argparse.ArgumentParser(prog="stemsplit", description="Separação de faixas (stems) de músicas.")
    sub = parser.add_subparsers(dest="comando", required=True)

    p = sub.add_parser("separar", help="Separa uma música em stems")
    p.add_argument("arquivo", help="MP3, WAV, FLAC ou M4A")
    p.add_argument("--modo", choices=list(MODES), default="completo", help="rapido, completo ou detalhado")
    p.add_argument("--bateria", action="store_true", help="Divide a bateria em bumbo, caixa e pratos")
    p.add_argument("--formato", choices=list(EXPORT_FORMATS), default="wav24")
    p.add_argument("--saida", help="Pasta de saída (padrão: <nome>_stems)")
    p.set_defaults(func=cmd_separar)

    p = sub.add_parser("analisar", help="Detecta BPM e tom")
    p.add_argument("arquivo")
    p.set_defaults(func=cmd_analisar)

    p = sub.add_parser("servidor", help="Inicia a API + interface web")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--porta", type=int, default=8000)
    p.set_defaults(func=cmd_servidor)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
