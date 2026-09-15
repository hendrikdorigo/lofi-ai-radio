"""
Etapa 1 — Gera um lote de faixas de música via ElevenLabs Music API,
seguindo os prompts do mood escolhido (lofi_classical, lofi_medieval, ...).

As faixas ficam em assets/faixas/<mood>/faixa_NNN.mp3, com um catálogo
(assets/faixas/<mood>/catalogo.json) guardando duração e prompt de cada uma
— usado depois pela etapa de montagem da playlist.

Roda de novo quantas vezes quiser: só acrescenta faixas novas ao catálogo
existente (não sobrescreve as antigas), então dá pra ir engordando a
biblioteca aos poucos.

Uso:
    python 01_generate_tracks.py --mood lofi_classical --quantidade 10
"""
import argparse
import json
import os
import random
import subprocess
from pathlib import Path

import requests
from dotenv import load_dotenv
from moods import obter_mood

load_dotenv(Path(__file__).parent.parent / "config" / ".env")

FAIXAS_DIR = Path(__file__).parent.parent / "assets" / "faixas"

MUSIC_URL = "https://api.elevenlabs.io/v1/music"
DURACAO_MS_MIN = 120_000  # 2 min
DURACAO_MS_MAX = 240_000  # 4 min


def duracao_audio(path: Path) -> float:
    resultado = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ],
        capture_output=True, text=True, check=True,
    )
    return float(resultado.stdout.strip())


def gerar_faixa(prompt: str, destino: Path):
    api_key = os.environ["ELEVENLABS_API_KEY"]
    duracao_ms = random.randint(DURACAO_MS_MIN, DURACAO_MS_MAX)

    resp = requests.post(
        MUSIC_URL,
        headers={"xi-api-key": api_key, "Content-Type": "application/json"},
        json={
            "prompt": prompt,
            "music_length_ms": duracao_ms,
            "model_id": "music_v2",
        },
        timeout=180,
    )
    resp.raise_for_status()
    destino.write_bytes(resp.content)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mood", required=True, help="lofi_classical | lofi_medieval")
    parser.add_argument("--quantidade", type=int, default=5, help="Quantas faixas gerar")
    args = parser.parse_args()

    mood = obter_mood(args.mood)

    out_dir = FAIXAS_DIR / args.mood
    out_dir.mkdir(parents=True, exist_ok=True)
    catalogo_path = out_dir / "catalogo.json"

    catalogo = []
    if catalogo_path.exists():
        catalogo = json.loads(catalogo_path.read_text(encoding="utf-8"))

    proximo_indice = len(catalogo) + 1

    for i in range(args.quantidade):
        indice = proximo_indice + i
        prompt = random.choice(mood["prompts_musica"])
        destino = out_dir / f"faixa_{indice:03d}.mp3"

        print(f"Gerando faixa {indice} ({args.mood})... prompt: {prompt[:60]}...")
        gerar_faixa(prompt, destino)

        if not destino.exists() or destino.stat().st_size == 0:
            print(f"Aviso: faixa {indice} saiu vazia, pulando.")
            continue

        dur = duracao_audio(destino)
        catalogo.append(
            {
                "arquivo": destino.name,
                "prompt": prompt,
                "duracao_s": round(dur, 2),
            }
        )
        print(f"Faixa {indice} salva: {destino} ({dur:.1f}s)")

    catalogo_path.write_text(
        json.dumps(catalogo, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nCatálogo atualizado: {len(catalogo)} faixas em {catalogo_path}")


if __name__ == "__main__":
    main()
