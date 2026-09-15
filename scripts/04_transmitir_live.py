"""
Etapa 4 — Transmite a playlist em loop contínuo pro YouTube Live via RTMP.

Precisa rodar num servidor ligado 24/7 (não no seu PC) — ex: `nohup python
04_transmitir_live.py --mood lofi_classical &` numa VPS, ou como serviço
systemd. Roda pra sempre até você interromper (Ctrl+C ou matar o processo).

Uso:
    python 04_transmitir_live.py --mood lofi_classical
"""
import argparse
import os
import platform
import subprocess
from pathlib import Path

from dotenv import load_dotenv
from moods import obter_mood

BASE_DIR = Path(__file__).parent.parent
load_dotenv(BASE_DIR / "config" / ".env")

FUNDO_DIR = BASE_DIR / "assets" / "fundo"
PLAYLISTS_DIR = BASE_DIR / "assets" / "playlists"

LARGURA, ALTURA = 1080, 1920  # 9:16, igual Shorts — mas também funciona em 16:9 se preferir

# drawtext depende do fontconfig pra achar fonte por nome, e nem todo build
# (principalmente no Windows) vem com isso configurado — apontamos direto
# pro arquivo .ttf pra evitar essa dependência (mesma solução do projeto
# youtube-shorts-terror).
FONTES_PADRAO_POR_SO = {
    "Windows": r"C:\Windows\Fonts\arial.ttf",
    "Darwin": "/System/Library/Fonts/Supplemental/Arial.ttf",
    "Linux": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
}


def resolver_fonte() -> Path:
    caminho = os.environ.get("CAPTION_FONT_FILE") or FONTES_PADRAO_POR_SO.get(
        platform.system(), ""
    )
    if not caminho or not Path(caminho).exists():
        raise FileNotFoundError(
            "Não achei uma fonte .ttf pro texto na tela. Defina CAPTION_FONT_FILE no "
            "config/.env apontando pro caminho de uma fonte instalada no seu sistema."
        )
    return Path(caminho)


def transmitir(fundo: Path, playlist: Path, titulo: str, stream_key: str):
    rtmp_url = f"rtmp://a.rtmp.youtube.com/live2/{stream_key}"

    titulo_escapado = (
        titulo.replace("\\", r"\\").replace("'", r"\'").replace(":", r"\:").replace(",", r"\,")
    )
    fontfile = str(resolver_fonte()).replace("\\", "/").replace(":", r"\:")

    filtro = (
        f"drawtext=fontfile='{fontfile}':text='{titulo_escapado}':fontcolor=white:fontsize=36:"
        f"borderw=2:bordercolor=black:x=30:y=30"
    )

    subprocess.run(
        [
            "ffmpeg",
            "-re",
            "-loop", "1", "-i", str(fundo),
            "-stream_loop", "-1", "-i", str(playlist),
            "-vf", f"scale={LARGURA}:{ALTURA},{filtro}",
            "-c:v", "libx264", "-preset", "veryfast", "-b:v", "2500k",
            "-pix_fmt", "yuv420p",
            "-g", "60",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
            "-f", "flv",
            rtmp_url,
        ],
        check=True,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mood", required=True, help="lofi_classical | lofi_medieval")
    args = parser.parse_args()

    mood = obter_mood(args.mood)

    fundo = FUNDO_DIR / f"{args.mood}.png"
    playlist = PLAYLISTS_DIR / f"{args.mood}.mp3"

    if not fundo.exists():
        raise FileNotFoundError(f"Fundo não encontrado: {fundo}. Rode a etapa 2 primeiro.")
    if not playlist.exists():
        raise FileNotFoundError(f"Playlist não encontrada: {playlist}. Rode a etapa 3 primeiro.")

    stream_key = os.environ["YOUTUBE_STREAM_KEY"]

    print(f"Transmitindo '{mood['nome']}' pro YouTube Live... (Ctrl+C pra parar)")
    transmitir(fundo, playlist, mood["nome"], stream_key)


if __name__ == "__main__":
    main()
