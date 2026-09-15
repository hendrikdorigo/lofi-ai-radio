"""
Orquestrador — prepara tudo (faixas, fundo, playlist) e começa a
transmissão pra um mood.

Uso:
    python run_radio.py --mood lofi_classical --faixas-iniciais 15
    python run_radio.py --mood lofi_classical --pular-preparo   # já preparado, só transmite
"""
import argparse
import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent


def rodar(script: str, *args: str):
    print(f"\n{'=' * 50}\n▶ Rodando {script} {' '.join(args)}\n{'=' * 50}")
    resultado = subprocess.run([sys.executable, str(SCRIPTS_DIR / script), *args], check=False)
    if resultado.returncode != 0:
        print(f"Erro em {script}. Interrompido.")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mood", required=True, help="lofi_classical | lofi_medieval")
    parser.add_argument(
        "--faixas-iniciais", type=int, default=15,
        help="Quantas faixas gerar antes de montar a playlist (se ainda não tiver catálogo)",
    )
    parser.add_argument(
        "--pular-preparo", action="store_true",
        help="Pula geração de faixas/fundo/playlist — usa o que já existe e só transmite",
    )
    args = parser.parse_args()

    if not args.pular_preparo:
        catalogo = Path(__file__).parent.parent / "assets" / "faixas" / args.mood / "catalogo.json"
        if not catalogo.exists():
            rodar("01_generate_tracks.py", "--mood", args.mood, "--quantidade", str(args.faixas_iniciais))

        fundo = Path(__file__).parent.parent / "assets" / "fundo" / f"{args.mood}.png"
        fundo_animado = Path(__file__).parent.parent / "assets" / "fundo" / f"{args.mood}.mp4"
        if not fundo.exists():
            rodar("02_generate_background.py", "--mood", args.mood)
        if not fundo_animado.exists():
            rodar("02b_animate_background.py", "--mood", args.mood)  # pula sozinha sem RUNWAY_API_KEY

        rodar("03_montar_playlist.py", "--mood", args.mood)

    rodar("04_transmitir_live.py", "--mood", args.mood)


if __name__ == "__main__":
    main()
