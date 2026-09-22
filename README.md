# Classical Radio — Live 24/7 no YouTube

Pipeline pra rodar uma live contínua com **gravações reais** de peças
clássicas de domínio público (Bach, Chopin, Vivaldi...) — músicos de
verdade tocando, não síntese nem IA. Sem nenhum estilo lofi por cima —
testamos chiado/batida/wow-flutter e não ficou bom.

A via recomendada (etapa `1c`) importa gravações que você baixa de fontes
como o [Musopen](https://musopen.org/), uma ONG dedicada especificamente a
gravar peças clássicas com músicos reais e liberar em domínio público/CC0.
Como você só usa faixas marcadas como Public Domain ou CC0, não tem risco
de Content ID nem de direito conexo de fonograma — a gravação em si já é
livre, não só a composição. O repo tem uma etapa `1b` como fallback (MIDI
sintetizado, pra peças que você não achar gravadas) e moods extras não
usados no canal principal (medieval, rock) caso queira expandir depois.

## Arquitetura do fluxo

```
01c_import_real_recordings.py → via recomendada: importa gravações reais (Musopen etc.), só normaliza volume
01b_generate_faithful_tracks.py → fallback: renderiza MIDI de domínio público via soundfont (síntese, não gravação real)
01_generate_tracks.py      → (alternativa, não usada) gera faixas via ElevenLabs Music
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

Pra isso praticamente sem manutenção manual, veja a seção
[Deploy automatizado numa VPS](#deploy-automatizado-numa-vps) abaixo.

## Deploy automatizado numa VPS

Deixa a live rodando sozinha 24/7, reconectando se cair, e reconstruindo a
playlist semanalmente com qualquer gravação nova que você subir — sem
precisar ficar rodando comandos manualmente.

1. Suba uma VPS Ubuntu/Debian (Hetzner CX22 ou DigitalOcean Basic, ~$5-6/mês).
2. Clone o repositório nela e rode o script de provisionamento:
   ```bash
   ssh root@SEU_IP
   git clone https://github.com/hendrikdorigo/lofi-ai-radio.git /opt/lofi-ai-radio
   cd /opt/lofi-ai-radio
   bash deploy/setup_vps.sh
   ```
   Isso instala ffmpeg/fluidsynth/python, cria um usuário sem privilégios
   (`lofiradio`) pra rodar o serviço, monta o venv, instala os serviços
   systemd e imprime os próximos passos manuais (preencher `.env`, subir as
   gravações, gerar fundo/playlist pela primeira vez).
3. Depois de seguir os passos impressos pelo script, suba a live:
   ```bash
   systemctl enable --now lofi-radio.service
   journalctl -u lofi-radio.service -f   # acompanhar os logs
   ```

O que fica automático a partir daí:

- **`lofi-radio.service`** — roda `04_transmitir_live.py` com
  `Restart=always`. Se a live cair (queda de rede, reboot da VPS), ela volta
  sozinha em segundos.
- **`lofi-radio-refresh.timer`** — toda segunda de madrugada, roda
  `deploy/refresh_playlist.sh`: importa qualquer gravação nova em
  `assets/gravacoes_fonte/classical/` (e `.mid` novo em
  `assets/midi_fonte/classical/`, se você usar o fallback) — ambas as
  etapas pulam o que já está no catálogo, então rodar sem novidade não faz
  nada — remonta a playlist e reinicia a live pra pegar as faixas novas.

Sua única tarefa manual recorrente, se quiser variar o catálogo, é baixar
mais gravações do Musopen e subir pra VPS:
```bash
scp minha_gravacao.mp3 root@SEU_IP:/opt/lofi-ai-radio/assets/gravacoes_fonte/classical/
```
Se você nunca fizer isso, a live continua no ar em loop com o catálogo atual.

## Como rodar

```bash
pip install -r requirements.txt
cp config/.env.example config/.env
# preencha IDEOGRAM_API_KEY e YOUTUBE_STREAM_KEY

# baixe gravações reais (musopen.org) pra assets/gravacoes_fonte/classical/
# e importe pro catálogo — veja a seção "Gravações reais" abaixo
python scripts/01c_import_real_recordings.py --mood classical

# primeira vez (gera fundo + playlist + começa a live):
python scripts/run_radio.py --mood classical

# depois, só transmitir de novo com o que já foi gerado:
python scripts/run_radio.py --mood classical --pular-preparo
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

## Gravações reais (via principal)

A live toca gravações de verdade — músicos reais tocando peças de domínio
público, gravadas especificamente pra uso livre. A fonte recomendada é o
[Musopen](https://musopen.org/), uma ONG que grava com orquestras e
solistas reais e libera o resultado em domínio público/CC0.

1. Crie uma conta gratuita em musopen.org (limite de ~5 downloads/dia — dá
   pra engordar o catálogo aos poucos, sem custo)
2. Busque a peça desejada (Bach, Chopin, Vivaldi...) e baixe **só faixas
   marcadas como "Public Domain" ou "CC0"** — evite "CC BY-SA", que exige
   creditar o intérprete e licenciar a live no mesmo termo (só use se for
   adicionar esse crédito manualmente na descrição)
3. Coloque o arquivo em `assets/gravacoes_fonte/<mood>/` (mp3, flac, wav ou
   m4a — qualquer formato que o ffmpeg leia)
4. Rode:
   ```bash
   python scripts/01c_import_real_recordings.py --mood classical
   ```

Isso só normaliza o volume (pra todas as faixas ficarem num nível parecido
na live) e converte pro formato final — sem nenhum efeito de estilo, a
gravação toca como ela é. Fontes alternativas, se não achar uma peça no
Musopen: [IMSLP](https://imslp.org/) (confira a licença de cada gravação
específica) e [archive.org](https://archive.org/) (transferências de
gravações históricas pré-1930/1950, já em domínio público nos EUA, mas com
qualidade de áudio mais datada).

### Fallback: MIDI sintetizado (etapa 1b)

Se não achar uma gravação real livre de alguma peça, a etapa `1b` gera uma
versão sintetizada a partir de MIDI (fiel nota por nota, mas com timbre de
sintetizador, não é um músico de verdade tocando):

1. Baixe arquivos `.mid` de domínio público em [mutopiaproject.org](https://www.mutopiaproject.org/)
2. Coloque em `assets/midi_fonte/<mood>/*.mid`
3. Instale o [FluidSynth](https://www.fluidsynth.org/) e baixe um soundfont
   General MIDI gratuito (ex: FluidR3_GM.sf2), configure o caminho em
   `SOUNDFONT_PATH` no `.env`
4. Rode: `python scripts/01b_generate_faithful_tracks.py --mood classical`

A etapa 1 (ElevenLabs, música "inspirada no estilo" gerada por IA) fica só
como alternativa não usada — o canal principal usa gravações reais (1c) e,
como fallback pontual, MIDI (1b).

## Engordando a biblioteca de faixas

Pra não repetir a playlist toda hora, baixe mais gravações do Musopen e
rode a etapa `1c` de novo — ela só importa os arquivos novos, sem duplicar
os que já estão no catálogo — depois remonte a playlist (etapa 3) e
reinicie a transmissão. Na VPS isso já roda sozinho toda semana (veja
[Deploy automatizado](#deploy-automatizado-numa-vps)).

## Custo estimado (fixo, não por vídeo)

| Item | Custo |
|---|---|
| Gravações reais (Musopen, domínio público/CC0) | grátis |
| Ideogram (fundo, uma vez por mood) | ~$0,03-0,06 |
| Runway (fundo animado, opcional, uma vez por mood) | ~$0,25-0,50 |
| VPS rodando a live 24/7 | ~$5-10/mês |

## Legal

A via principal (etapa 1c) toca gravações reais já liberadas em domínio
público ou CC0 pela própria fonte (Musopen) — tanto a composição quanto a
gravação em si são livres, então não tem risco de Content ID nem de
direito conexo de fonograma. Evite baixar gravações com licença CC BY-SA
sem adicionar o crédito exigido na descrição da live. O fallback (etapa 1b,
MIDI sintetizado) usa só a composição de domínio público, renderizada por
você — a "gravação" ali é nova, gerada por você mesmo. Os títulos evitam
citar nomes de compositores específicos pra não confundir marca ("estilo
barroco" em vez de "estilo Bach", por exemplo) — ajuste em
`scripts/moods.py` como preferir.
