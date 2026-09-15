# Lofi AI Radio — Live 24/7 no YouTube

Pipeline pra rodar uma live contínua de música lofi composta 100% por IA,
em dois "moods" (estilos): **Lofi Clássico** (temas inspirados em Bach,
Chopin, Vivaldi...) e **Lofi Medieval** (taverna, alaúde, harpa). Como a
música é inteiramente gerada por IA — não usa nenhuma gravação ou
composição de terceiros — não tem risco de Content ID.

## Arquitetura do fluxo

```
01_generate_tracks.py      → gera faixas via ElevenLabs Music (lote, engorda o catálogo)
        ↓
02_generate_background.py  → gera a imagem de fundo da live (uma vez por mood, via Ideogram)
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

## Engordando a biblioteca de faixas

Pra não repetir a playlist toda hora, rode a etapa 1 periodicamente
(ex: 1x por semana via cron na VPS) pra acrescentar faixas novas ao
catálogo, depois remonte a playlist (etapa 3) e reinicie a transmissão.

## Custo estimado (fixo, não por vídeo)

| Item | Custo |
|---|---|
| ElevenLabs Music (faixas) | pago por minuto gerado — confira o preço atual no [elevenlabs.io](https://elevenlabs.io/pricing) |
| Ideogram (fundo, uma vez por mood) | ~$0,03-0,06 |
| VPS rodando a live 24/7 | ~$5-10/mês |

## Legal

A música é inteiramente composta por IA a partir de prompts — não usa
nenhuma gravação, partitura ou sample de terceiros. Isso evita tanto o
direito autoral da composição quanto o direito conexo da gravação
(fonograma), que continuariam protegidos mesmo em peças clássicas antigas
de domínio público. Os títulos evitam citar nomes de compositores/artistas
específicos pra não confundir marca ("estilo barroco" em vez de "estilo
Bach", por exemplo) — ajuste os prompts em `scripts/moods.py` como preferir.
