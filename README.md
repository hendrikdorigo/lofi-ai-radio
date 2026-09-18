# Lofi AI Radio — Live 24/7 no YouTube

Pipeline pra rodar uma live contínua de música lofi composta 100% por IA,
em dois "moods" (estilos): **Lofi Clássico** (temas inspirados em Bach,
Chopin, Vivaldi...) e **Lofi Medieval** (taverna, alaúde, harpa). Como a
música é inteiramente gerada por IA — não usa nenhuma gravação ou
composição de terceiros — não tem risco de Content ID.

## Arquitetura do fluxo

```
01_generate_tracks.py      → gera faixas via ElevenLabs Music (lote, engorda o catálogo)
01b_generate_faithful_tracks.py → (opcional) renderiza MIDI de domínio público fielmente, com efeito lofi
        ↓
02_generate_background.py  → gera a imagem de fundo da live (uma vez por mood, via Ideogram)
        ↓
02b_animate_background.py  → (opcional) anima o fundo com IA (Runway) — pula se RUNWAY_API_KEY vazia
        ↓
03_montar_playlist.py      → junta as faixas com crossfade suave numa playlist contínua
        ↓
04_transmitir_live.py      → transmite fundo + playlist em loop pro YouTube Live via RTMP
```

`run_radio.py` roda tudo em sequência pra um mood.

## Diferença importante vs. o projeto de Shorts

**Isso precisa rodar num servidor ligado 24/7 — não no seu PC.** Uma live
para assim que o processo do ffmpeg é interrompido. Use uma VPS barata
(~$5-10/mês) com Python, ffmpeg e este repositório, rodando o
`04_transmitir_live.py` como serviço systemd ou via `nohup ... &`.

## Como rodar

```bash
pip install -r requirements.txt
cp config/.env.example config/.env
# preencha ELEVENLABS_API_KEY, IDEOGRAM_API_KEY e YOUTUBE_STREAM_KEY

# primeira vez (gera faixas + fundo + playlist + começa a live):
python scripts/run_radio.py --mood lofi_classical --faixas-iniciais 15

# depois, só transmitir de novo com o que já foi gerado:
python scripts/run_radio.py --mood lofi_classical --pular-preparo
```

## Pegando a chave de transmissão do YouTube

1. Vá em [studio.youtube.com](https://studio.youtube.com) → Criar → Ir ao vivo
2. Configure a live (título, descrição — pode usar o texto sugerido em
   `scripts/moods.py`, campo `titulo_live`/`descricao_live`)
3. Copie a **chave de transmissão** (stream key) e cole em
   `YOUTUBE_STREAM_KEY` no `.env`
4. Rode o script — a live deve aparecer como "ao vivo" no YouTube Studio
   assim que o ffmpeg conectar

## Fundo animado (opcional)

Por padrão o fundo é uma imagem parada (Ideogram) que fica congelada a live
inteira. Pra ter um loop animado de verdade (vela tremeluzindo, chuva
caindo, tipo a estética "Lofi Girl"), preencha `RUNWAY_API_KEY` no `.env`
com uma chave da [Runway API](https://dev.runwayml.com/) — a etapa
`02b_animate_background.py` gera um clipe curto (5-10s) a partir da mesma
imagem e ele passa a tocar em loop na live. Como é só **um clipe por mood**
(não um por cena, como no projeto de Shorts), o custo é baixo — confira o
preço atual em [docs.dev.runwayml.com](https://docs.dev.runwayml.com/api-details/pricing/).
Deixe `RUNWAY_API_KEY` em branco pra continuar com a imagem estática.

## Faixas fiéis ao original (opcional)

O ElevenLabs Music (etapa 1) só se **inspira** no estilo pedido — ele não
reproduz uma melodia específica nota por nota (nenhum gerador texto-pra-música
faz isso hoje). Se você quer a melodia real de uma peça (ex: o tema principal
do Rondo Alla Turca reconhecível de verdade), use a etapa `1b`:

1. Baixe arquivos `.mid` de domínio público — [mutopiaproject.org](https://www.mutopiaproject.org/)
   é a fonte mais confiável (projeto dedicado a partituras/MIDI livres;
   evite sites que vendem "arranjos" próprios, cuja transcrição específica
   pode não ser livre mesmo a peça sendo de domínio público)
2. Coloque os arquivos em `assets/midi_fonte/<mood>/*.mid`
3. Instale o [FluidSynth](https://www.fluidsynth.org/) e baixe um soundfont
   General MIDI gratuito (ex: FluidR3_GM.sf2), configure o caminho em
   `SOUNDFONT_PATH` no `.env`
4. Rode:
   ```bash
   python scripts/01b_generate_faithful_tracks.py --mood lofi_classical
   ```

Isso renderiza a melodia de verdade com um piano sintetizado e aplica um
tratamento lofi por cima (corte de agudos, chiado de vinil sintetizado,
leve wobble) — sem usar nenhuma gravação de terceiros, então continua sem
risco de Content ID (só a composição, que é de domínio público, e uma
renderização nova que você mesmo gera).

## Engordando a biblioteca de faixas

Pra não repetir a playlist toda hora, rode a etapa 1 periodicamente
(ex: 1x por semana via cron na VPS) pra acrescentar faixas novas ao
catálogo, depois remonte a playlist (etapa 3) e reinicie a transmissão.

## Custo estimado (fixo, não por vídeo)

| Item | Custo |
|---|---|
| ElevenLabs Music (faixas) | pago por minuto gerado — confira o preço atual no [elevenlabs.io](https://elevenlabs.io/pricing) |
| Ideogram (fundo, uma vez por mood) | ~$0,03-0,06 |
| Runway (fundo animado, opcional, uma vez por mood) | ~$0,25-0,50 |
| VPS rodando a live 24/7 | ~$5-10/mês |

## Legal

A música é inteiramente composta por IA a partir de prompts — não usa
nenhuma gravação, partitura ou sample de terceiros. Isso evita tanto o
direito autoral da composição quanto o direito conexo da gravação
(fonograma), que continuariam protegidos mesmo em peças clássicas antigas
de domínio público. Os títulos evitam citar nomes de compositores/artistas
específicos pra não confundir marca ("estilo barroco" em vez de "estilo
Bach", por exemplo) — ajuste os prompts em `scripts/moods.py` como preferir.
