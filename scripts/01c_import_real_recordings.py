"""
Etapa 1c (via recomendada) — Importa gravações reais de domínio público pro
catálogo da rádio. Isso é o oposto de síntese: é um músico de verdade
tocando, gravado de verdade — não MIDI renderizado (etapa 1b) nem música
gerada por IA (etapa 1).

Onde conseguir (nessa ordem de preferência):
1. musopen.org — ONG dedicada a gravações de domínio público/CC0 de peças
   clássicas, feitas com orquestras/músicos reais especificamente pra isso.
   Baixe SÓ faixas marcadas como "Public Domain" ou "CC0" (evite "CC BY-SA":
   ela permite uso comercial, mas exige creditar o intérprete e licenciar a
   live no mesmo termo — só use se você for adicionar esse crédito na
   descrição manualmente).
2. imslp.org — tem algumas gravações de domínio público (raro) além das
   partituras; confira a licença específica de cada gravação antes de usar.
3. archive.org — transferências de gravações históricas (pré-1930/1950)
   já em domínio público nos EUA; qualidade de áudio mais datada (mono,
   ruído de superfície).

Baixe manualmente (precisa de conta gratuita no Musopen, limite de ~5
arquivos/dia — dá pra engordar o catálogo aos poucos em alguns dias) e
coloque os arquivos em assets/gravacoes_fonte/<mood>/*.{mp3,flac,wav,ogg}

Uso:
    python 01c_import_real_recordings.py --mood classical
"""
import argparse
import json
import subprocess
from pathlib import Path

GRAVACOES_DIR = Path(__file__).parent.parent / "assets" / "gravacoes_fonte"
FAIXAS_DIR = Path(__file__).parent.parent / "assets" / "faixas"

EXTENSOES_SUPORTADAS = {".mp3", ".flac", ".wav", ".ogg", ".m4a"}


def duracao_audio(path: Path) -> float:
    resultado = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ],
        capture_output=True, text=True, check=True,
    )
    return float(resultado.stdout.strip())


def normalizar_para_mp3(origem: Path, mp3_destino: Path):
    """Só normaliza volume (pra todas as faixas ficarem num nível parecido
    na live) e converte pro formato final — sem nenhum efeito de estilo,
    a gravação real toca como ela é."""
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(origem),
            "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
            "-c:a", "libmp3lame", "-b:a", "192k",
            str(mp3_destino),
        ],
        check=True,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mood", required=True, help="classical | lofi_medieval")
    args = parser.parse_args()

    src_dir = GRAVACOES_DIR / args.mood
    todas_origens = sorted(
        p for p in src_dir.glob("*") if p.suffix.lower() in EXTENSOES_SUPORTADAS
    ) if src_dir.is_dir() else []
    if not todas_origens:
        raise FileNotFoundError(
            f"Nenhuma gravação encontrada em {src_dir}. Baixe gravações reais de "
            f"domínio público/CC0 (ex: musopen.org) e coloque nessa pasta."
        )

    out_dir = FAIXAS_DIR / args.mood
    out_dir.mkdir(parents=True, exist_ok=True)
    catalogo_path = out_dir / "catalogo.json"
    catalogo = (
        json.loads(catalogo_path.read_text(encoding="utf-8")) if catalogo_path.exists() else []
    )

    # Já importado = tem entrada no catálogo apontando pra esse nome de
    # arquivo de origem. Evita reimportar (e duplicar) ao rodar de novo
    # sobre uma pasta que já tem gravações processadas antes.
    ja_importados = {item.get("arquivo_original") for item in catalogo}
    origens = [o for o in todas_origens if o.name not in ja_importados]
    if not origens:
        print("Nenhuma gravação nova pra importar (todas já estão no catálogo).")
        return

    proximo_indice = len(catalogo) + 1

    for i, origem in enumerate(origens):
        indice = proximo_indice + i
        destino = out_dir / f"faixa_{indice:03d}.mp3"

        print(f"Importando {origem.name}...")
        normalizar_para_mp3(origem, destino)

        dur = duracao_audio(destino)
        catalogo.append(
            {
                "arquivo": destino.name,
                "arquivo_original": origem.name,
                "titulo": origem.stem,
                "prompt": f"real recording: {origem.stem}",
                "duracao_s": round(dur, 2),
            }
        )
        print(f"Faixa {indice} salva: {destino} ({dur:.1f}s)")

    catalogo_path.write_text(json.dumps(catalogo, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nCatálogo atualizado: {len(catalogo)} faixas em {catalogo_path}")


if __name__ == "__main__":
    main()
