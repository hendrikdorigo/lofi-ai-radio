"""
Etapa 2 — Gera a imagem de fundo (loop visual) da live, uma vez por mood.

Usa Ideogram (mesmo provedor pago do projeto de Shorts). Só precisa rodar
de novo se quiser trocar o visual — o arquivo gerado fica salvo e é
reaproveitado por todas as sessões de transmissão.

Uso:
    python 02_generate_background.py --mood lofi_classical
"""
import argparse
import os
from pathlib import Path

import requests
from dotenv import load_dotenv
from moods import obter_mood

load_dotenv(Path(__file__).parent.parent / "config" / ".env")

FUNDO_DIR = Path(__file__).parent.parent / "assets" / "fundo"


def gerar_fundo_ideogram(prompt: str, destino: Path):
    resp = requests.post(
        "https://api.ideogram.ai/generate",
        headers={
            "Api-Key": os.environ["IDEOGRAM_API_KEY"],
            "Content-Type": "application/json",
        },
        json={
            "image_request": {
                "prompt": prompt,
                "aspect_ratio": "ASPECT_9_16",
                "model": "V_2",
            }
        },
        timeout=120,
    )
    resp.raise_for_status()
    url = resp.json()["data"][0]["url"]
    img = requests.get(url, timeout=60)
    destino.write_bytes(img.content)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mood", required=True, help="lofi_classical | lofi_medieval")
    args = parser.parse_args()

    mood = obter_mood(args.mood)

    FUNDO_DIR.mkdir(parents=True, exist_ok=True)
    destino = FUNDO_DIR / f"{args.mood}.png"

    print(f"Gerando imagem de fundo pro mood '{args.mood}'...")
    gerar_fundo_ideogram(mood["prompt_fundo"], destino)

    print(f"Fundo salvo em: {destino}")


if __name__ == "__main__":
    main()
