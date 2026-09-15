"""
Etapa 2b (opcional) — Anima a imagem de fundo com IA (Runway image_to_video),
criando um loop curto com movimento sutil (vela tremeluzindo, chuva caindo,
poeira no ar...) em vez da imagem parada da etapa 2.

Requer RUNWAY_API_KEY no config/.env. Sem essa chave, o pipeline
simplesmente pula essa etapa e a 04_transmitir_live.py usa a imagem
estática (assets/fundo/<mood>.png) como sempre.

ATENÇÃO: assim como no projeto de Shorts, Gen-4 Turbo cobra por segundo de
vídeo gerado. Aqui o custo é baixo porque só gera UM clipe por mood (não um
por cena) — confira o preço atual em docs.dev.runwayml.com antes de rodar.

Uso:
    python 02b_animate_background.py --mood lofi_classical
"""
import argparse
import base64
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv
from moods import obter_mood

load_dotenv(Path(__file__).parent.parent / "config" / ".env")

FUNDO_DIR = Path(__file__).parent.parent / "assets" / "fundo"

RUNWAY_BASE_URL = "https://api.dev.runwayml.com/v1"
RUNWAY_VERSION = "2024-11-06"

MOTION_SUFFIXO = (
    "subtle looping animation: flickering candlelight, gentle ambient motion, "
    "soft rain or dust in the air, slow and calm, seamless loop, no text, no watermark"
)


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {os.environ['RUNWAY_API_KEY']}",
        "Content-Type": "application/json",
        "X-Runway-Version": RUNWAY_VERSION,
    }


def _submeter_tarefa(imagem: Path, prompt_texto: str, duracao: int) -> str:
    b64 = base64.b64encode(imagem.read_bytes()).decode()
    prompt_image = f"data:image/png;base64,{b64}"

    model = os.environ.get("RUNWAY_MODEL", "gen4_turbo")
    ratio = os.environ.get("RUNWAY_RATIO", "720:1280")

    resp = requests.post(
        f"{RUNWAY_BASE_URL}/image_to_video",
        headers=_headers(),
        json={
            "model": model,
            "promptImage": prompt_image,
            "promptText": prompt_texto[:1000],
            "ratio": ratio,
            "duration": duracao,
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def _aguardar_tarefa(task_id: str, timeout_s: int = 300) -> str:
    """Espera a tarefa terminar e retorna a URL do vídeo gerado."""
    inicio = time.monotonic()
    while time.monotonic() - inicio < timeout_s:
        resp = requests.get(
            f"{RUNWAY_BASE_URL}/tasks/{task_id}", headers=_headers(), timeout=30
        )
        resp.raise_for_status()
        dados = resp.json()
        status = dados["status"]

        if status == "SUCCEEDED":
            return dados["output"][0]
        if status in ("FAILED", "CANCELLED"):
            raise RuntimeError(f"Tarefa Runway {task_id} falhou: {dados.get('failure', status)}")

        time.sleep(5)

    raise TimeoutError(f"Tarefa Runway {task_id} não terminou em {timeout_s}s")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mood", required=True, help="lofi_classical | lofi_medieval")
    parser.add_argument(
        "--duracao", type=int, default=8,
        help="Duração alvo do loop em segundos (Runway arredonda pra 5 ou 10)",
    )
    args = parser.parse_args()

    if not os.environ.get("RUNWAY_API_KEY"):
        print("RUNWAY_API_KEY não configurada — pulando animação (vai usar imagem estática).")
        return

    mood = obter_mood(args.mood)

    imagem = FUNDO_DIR / f"{args.mood}.png"
    if not imagem.exists():
        raise FileNotFoundError(
            f"Imagem de fundo não encontrada: {imagem}. Rode a etapa 2 primeiro."
        )

    destino = FUNDO_DIR / f"{args.mood}.mp4"
    duracao = 5 if args.duracao <= 5 else 10  # Runway trabalha com durações fixas
    prompt_texto = f"{mood['prompt_fundo']}, {MOTION_SUFFIXO}"

    print(f"Animando fundo do mood '{args.mood}'... (isso demora, pode levar alguns minutos)")
    task_id = _submeter_tarefa(imagem, prompt_texto, duracao)
    url_video = _aguardar_tarefa(task_id)

    video = requests.get(url_video, timeout=120)
    video.raise_for_status()
    destino.write_bytes(video.content)

    print(f"Fundo animado salvo em: {destino}")


if __name__ == "__main__":
    main()
