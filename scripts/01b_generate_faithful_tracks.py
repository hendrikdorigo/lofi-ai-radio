"""
Etapa 1b (opcional) — Gera faixas 100% fiéis a uma peça de domínio público,
a partir de arquivos MIDI (você fornece), renderizados com um soundfont e
com efeito lofi aplicado por cima (corte de agudos, chiado de vinil, leve
"wobble" de fita).

Diferente da etapa 1 (ElevenLabs Music, que só "se inspira" no estilo), essa
etapa reproduz a melodia de verdade, nota por nota — útil se você quer
fidelidade total à peça original em vez de uma reinterpretação livre da IA.

Onde conseguir os .mid (domínio público): mutopiaproject.org é o mais
confiável — é um projeto dedicado especificamente a partituras/MIDI livres.
Baixe manualmente (evite sites que vendem "arranjos" próprios, cuja
transcrição específica pode não ser livre mesmo a peça sendo de domínio
público) e coloque em assets/midi_fonte/<mood>/*.mid

Requer:
- fluidsynth instalado no sistema
  (Windows: choco install fluidsynth  |  Mac: brew install fluid-synth
   |  Linux: sudo apt install fluidsynth)
- um soundfont General MIDI gratuito, ex. FluidR3_GM.sf2 — baixe e aponte
  o caminho em SOUNDFONT_PATH no config/.env

Uso:
    python 01b_generate_faithful_tracks.py --mood lofi_classical
"""
import argparse
import json
import os
import subprocess
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / "config" / ".env")

MIDI_DIR = Path(__file__).parent.parent / "assets" / "midi_fonte"
FAIXAS_DIR = Path(__file__).parent.parent / "assets" / "faixas"


def duracao_audio(path: Path) -> float:
    resultado = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ],
        capture_output=True, text=True, check=True,
    )
    return float(resultado.stdout.strip())


def renderizar_midi(midi_path: Path, soundfont: Path, wav_destino: Path):
    # As opções (-F, -r) precisam vir antes dos argumentos posicionais
    # (soundfont, midi) — o fluidsynth rejeita opções depois deles.
    subprocess.run(
        [
            "fluidsynth", "-ni",
            "-F", str(wav_destino), "-r", "44100",
            str(soundfont), str(midi_path),
        ],
        check=True,
    )


def gerar_batida_loop(destino: Path, bpm: int = 85):
    """Sintetiza um compasso de batida lofi (kick, snare, hi-hat) só com
    geradores do ffmpeg — sem sample de ninguém. Salva um loop curto que
    depois é repetido (-stream_loop) pra cobrir a faixa inteira."""
    beat_s = 60.0 / bpm
    loop_s = beat_s * 4  # 1 compasso de 4 tempos

    eventos = [
        ("kick", 0.0), ("kick", 2 * beat_s),
        ("snare", beat_s), ("snare", 3 * beat_s),
        *[("hihat", i * beat_s / 2) for i in range(8)],
    ]

    inputs = []
    filtros = []
    labels = []
    for i, (tipo, t) in enumerate(eventos):
        delay_ms = int(t * 1000)
        if tipo == "kick":
            inputs += ["-f", "lavfi", "-i", "sine=frequency=55:duration=0.25"]
            proc = (
                f"[{i}:a]lowpass=f=180,afade=t=out:st=0:d=0.25,"
                f"volume=1.0,adelay={delay_ms}[e{i}]"
            )
        elif tipo == "snare":
            inputs += ["-f", "lavfi", "-i", "anoisesrc=color=white:duration=0.15"]
            proc = (
                f"[{i}:a]bandpass=f=1200:width_type=h:w=1500,"
                f"afade=t=out:st=0:d=0.15,volume=0.5,adelay={delay_ms}[e{i}]"
            )
        else:  # hihat
            inputs += ["-f", "lavfi", "-i", "anoisesrc=color=white:duration=0.05"]
            proc = (
                f"[{i}:a]highpass=f=7000,afade=t=out:st=0:d=0.05,"
                f"volume=0.25,adelay={delay_ms}[e{i}]"
            )
        filtros.append(proc)
        labels.append(f"[e{i}]")

    mix = "".join(labels) + f"amix=inputs={len(labels)}:duration=longest:normalize=0[batida]"
    filtro_completo = ";".join(filtros) + ";" + mix

    subprocess.run(
        [
            "ffmpeg", "-y", *inputs,
            "-filter_complex", filtro_completo,
            "-map", "[batida]", "-t", str(loop_s),
            "-ar", "44100",
            str(destino),
        ],
        check=True,
    )


def aplicar_efeito_lofi(wav_origem: Path, mp3_destino: Path, batida_loop: Path):
    """Corta agudos/graves extremos, adiciona wow/flutter de fita (duas
    camadas: oscilação lenta + rápida), chorus sutil pra dar corpo/calor,
    leve compressão, mixa um chiado de vinil com variação orgânica
    (tremolo), e uma batida lofi discreta por baixo — dá a textura lofi
    sem alterar a melodia."""
    filtro = (
        "[0:a]lowpass=f=3500,highpass=f=80,"
        "vibrato=f=0.2:d=0.12,vibrato=f=6:d=0.03,"
        "chorus=0.6:0.9:50:0.4:0.25:2,"
        "acompressor=threshold=-18dB:ratio=3:attack=20:release=250[piano];"
        "[1:a]highpass=f=800,lowpass=f=7000,volume=0.03,tremolo=f=3:d=0.5[chiado];"
        "[2:a]volume=0.35[batida];"
        # dither inaudível: o loop de bateria tem trechos de silêncio digital
        # puro entre as batidas, e isso trava o libmp3lame (bug conhecido do
        # encoder com blocos de zero absoluto) mesmo em bitrate fixo
        "[3:a]volume=0.0004[dither];"
        "[piano][chiado][batida][dither]amix=inputs=4:duration=first:normalize=0[out]"
    )
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(wav_origem),
            "-f", "lavfi", "-i", "anoisesrc=color=pink:amplitude=1:sample_rate=44100",
            "-stream_loop", "-1", "-i", str(batida_loop),
            "-f", "lavfi", "-i", "anoisesrc=color=white:amplitude=1:sample_rate=44100",
            "-filter_complex", filtro,
            "-map", "[out]",
            # bitrate fixo em vez de -q:a (VBR): o modo VBR do libmp3lame trava
            # com "Assertion failed: el >= 0" em trechos de silêncio digital
            "-c:a", "libmp3lame", "-b:a", "192k",
            str(mp3_destino),
        ],
        check=True,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mood", required=True, help="lofi_classical | lofi_medieval")
    args = parser.parse_args()

    soundfont_str = os.environ.get("SOUNDFONT_PATH", "").strip()
    soundfont = Path(soundfont_str) if soundfont_str else None
    if not soundfont or not soundfont.is_file():
        raise FileNotFoundError(
            "SOUNDFONT_PATH não configurado ou não aponta pra um arquivo válido "
            f"(valor atual: {soundfont_str!r}). Baixe um soundfont General MIDI "
            "gratuito (ex: FluidR3_GM.sf2) e aponte o caminho completo até o "
            "arquivo .sf2 em config/.env."
        )

    midi_dir = MIDI_DIR / args.mood
    midis = sorted(midi_dir.glob("*.mid"))
    if not midis:
        raise FileNotFoundError(
            f"Nenhum .mid encontrado em {midi_dir}. Baixe arquivos MIDI de "
            f"domínio público (ex: mutopiaproject.org) e coloque nessa pasta."
        )

    out_dir = FAIXAS_DIR / args.mood
    out_dir.mkdir(parents=True, exist_ok=True)
    catalogo_path = out_dir / "catalogo.json"
    catalogo = (
        json.loads(catalogo_path.read_text(encoding="utf-8")) if catalogo_path.exists() else []
    )
    proximo_indice = len(catalogo) + 1

    batida_loop = out_dir / "_batida_loop.wav"
    gerar_batida_loop(batida_loop)

    for i, midi_path in enumerate(midis):
        indice = proximo_indice + i
        wav_tmp = out_dir / f"_tmp_{indice}.wav"
        destino = out_dir / f"faixa_{indice:03d}.mp3"

        print(f"Renderizando {midi_path.name}...")
        renderizar_midi(midi_path, soundfont, wav_tmp)
        aplicar_efeito_lofi(wav_tmp, destino, batida_loop)
        wav_tmp.unlink()

        dur = duracao_audio(destino)
        catalogo.append(
            {
                "arquivo": destino.name,
                "prompt": f"faithful rendition of {midi_path.stem} (public domain MIDI)",
                "duracao_s": round(dur, 2),
            }
        )
        print(f"Faixa {indice} salva: {destino} ({dur:.1f}s)")

    batida_loop.unlink()
    catalogo_path.write_text(json.dumps(catalogo, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nCatálogo atualizado: {len(catalogo)} faixas em {catalogo_path}")


if __name__ == "__main__":
    main()
