"""
Etapa 3 — Junta as faixas do catálogo numa playlist contínua, com
crossfade suave entre uma faixa e a próxima (sem corte seco).

Por padrão usa todas as faixas do catálogo, em ordem embaralhada. Pode
rodar de novo a qualquer momento pra gerar uma playlist nova (ex: depois
de acrescentar mais faixas com a etapa 1).

Uso:
    python 03_montar_playlist.py --mood lofi_classical
    python 03_montar_playlist.py --mood lofi_classical --duracao-min 30
"""
import argparse
import json
import random
import subprocess
from pathlib import Path

FAIXAS_DIR = Path(__file__).parent.parent / "assets" / "faixas"
PLAYLISTS_DIR = Path(__file__).parent.parent / "assets" / "playlists"

CROSSFADE_S = 3


def montar_playlist(faixas: list[Path], destino: Path):
    if len(faixas) == 1:
        subprocess.run(["ffmpeg", "-y", "-i", str(faixas[0]), "-c", "copy", str(destino)], check=True)
        return

    inputs = []
    for f in faixas:
        inputs += ["-i", str(f)]

    filtros = []
    label_anterior = "0"
    curva = "tri"  # crossfade em rampa linear (triangular), suave e previsível
    for i in range(1, len(faixas)):
        label_saida = f"a{i}"
        filtros.append(
            f"[{label_anterior}][{i}]acrossfade=d={CROSSFADE_S}:c1={curva}:c2={curva}[{label_saida}]"
        )
        label_anterior = label_saida

    filtro_completo = ";".join(filtros)

    subprocess.run(
        [
            "ffmpeg", "-y",
            *inputs,
            "-filter_complex", filtro_completo,
            "-map", f"[{label_anterior}]",
            "-c:a", "libmp3lame", "-q:a", "2",
            str(destino),
        ],
        check=True,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mood", required=True, help="lofi_classical | lofi_medieval")
    parser.add_argument(
        "--duracao-min", type=int, default=None,
        help="Duração alvo em minutos (usa faixas suficientes do catálogo pra cobrir isso; "
             "por padrão usa o catálogo inteiro)",
    )
    args = parser.parse_args()

    faixas_dir = FAIXAS_DIR / args.mood
    catalogo_path = faixas_dir / "catalogo.json"
    if not catalogo_path.exists():
        raise FileNotFoundError(
            f"Catálogo não encontrado em {catalogo_path}. Rode a etapa 1 primeiro."
        )

    catalogo = json.loads(catalogo_path.read_text(encoding="utf-8"))
    if not catalogo:
        raise ValueError("Catálogo está vazio — gere faixas com a etapa 1 primeiro.")

    random.shuffle(catalogo)

    if args.duracao_min:
        alvo_s = args.duracao_min * 60
        selecionadas = []
        total = 0.0
        for item in catalogo:
            selecionadas.append(item)
            total += item["duracao_s"]
            if total >= alvo_s:
                break
        catalogo = selecionadas

    faixas = [faixas_dir / item["arquivo"] for item in catalogo]
    duracao_total_s = sum(item["duracao_s"] for item in catalogo) - CROSSFADE_S * (len(catalogo) - 1)

    PLAYLISTS_DIR.mkdir(parents=True, exist_ok=True)
    destino = PLAYLISTS_DIR / f"{args.mood}.mp3"

    print(f"Montando playlist com {len(faixas)} faixas (~{duracao_total_s / 60:.1f} min)...")
    montar_playlist(faixas, destino)

    print(f"\nPlaylist gerada em: {destino}")


if __name__ == "__main__":
    main()
