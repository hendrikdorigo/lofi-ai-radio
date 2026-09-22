# Classical Radio — Live 24/7 no YouTube

Pipeline pra rodar uma live contínua com peças clássicas de domínio público
(Bach, Chopin, Vivaldi...) tocando limpas, sem nenhum estilo lofi por cima
— testamos chiado/batida/wow-flutter e não ficou bom, então a via
recomendada (etapa `1b`) é a peça de verdade, renderizada fielmente a partir
de MIDI, sem tratamento nenhum. Como não usa gravação de terceiros — só a
composição (de domínio público) e uma renderização nova gerada por você —
não tem risco de Content ID. O repo também tem moods extras não usados no
canal principal (medieval, rock) caso queira expandir depois.

## Arquitetura do fluxo

```
01_generate_tracks.py      → (alternativa, não usada) gera faixas via ElevenLabs Music
01b_generate_faithful_tracks.py → via recomendada: renderiza MIDI de domínio público fielmente, sem estilo
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
playlist semanalmente com qualquer `.mid` novo que você subir — sem precisar
ficar rodando comandos manualmente.

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
   systemd e imprime os próximos passos manuais (preencher `.env`, subir os
   `.mid`, gerar fundo/playlist pela primeira vez).
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
  `deploy/refresh_playlist.sh`: renderiza qualquer `.mid` novo em
  `assets/midi_fonte/classical/` (a etapa 1b agora pula os que já foram
  processados, então rodar sem novidade não faz nada), remonta a playlist e
  reinicia a live pra pegar as faixas novas.

Sua única tarefa manual recorrente, se quiser variar o catálogo, é baixar
mais `.mid` do Mutopia e subir pra VPS:
```bash
scp minha_peca.mid root@SEU_IP:/opt/lofi-ai-radio/assets/midi_fonte/classical/
```
Se você nunca fizer isso, a live continua no ar em loop com o catálogo atual.

## Como rodar

```bash
pip install -r requirements.txt
cp config/.env.example config/.env
# preencha ELEVENLABS_API_KEY, IDEOGRAM_API_KEY e YOUTUBE_STREAM_KEY

# primeira vez (gera faixas + fundo + playlist + começa a live):
python scripts/run_radio.py --mood classical --faixas-iniciais 15

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
   python scripts/01b_generate_faithful_tracks.py --mood classical
   ```

Isso renderiza a melodia de verdade com um piano sintetizado, sem nenhum
efeito por cima (testamos tratamento lofi — chiado, batida sintetizada,
wow/flutter — e não convenceu; melodia clássica limpa soou melhor). Sem
usar nenhuma gravação de terceiros, então continua sem risco de Content ID
(só a composição, que é de domínio público, e uma renderização nova que
você mesmo gera).

**Essa é a via recomendada pro mood `classical`** — a etapa 1 (ElevenLabs)
fica só como alternativa caso você queira testar variações "inspiradas no
estilo" no futuro; o canal principal usa exclusivamente a 1b.

## Engordando a biblioteca de faixas

Pra não repetir a playlist toda hora, baixe mais `.mid` de domínio público
(Mutopia) e rode a etapa `1b` de novo — ela só renderiza os arquivos novos,
sem duplicar os que já estão no catálogo — depois remonte a playlist
(etapa 3) e reinicie a transmissão. Na VPS isso já roda sozinho toda semana
(veja [Deploy automatizado](#deploy-automatizado-numa-vps)).

## Custo estimado (fixo, não por vídeo)

| Item | Custo |
|---|---|
| ElevenLabs Music (faixas) | pago por minuto gerado — confira o preço atual no [elevenlabs.io](https://elevenlabs.io/pricing) |
| Ideogram (fundo, uma vez por mood) | ~$0,03-0,06 |
| Runway (fundo animado, opcional, uma vez por mood) | ~$0,25-0,50 |
| VPS rodando a live 24/7 | ~$5-10/mês |

## Legal

A via recomendada (etapa 1b) toca composições de domínio público
renderizadas por você a partir de MIDI — não usa nenhuma gravação,
partitura de terceiros ou sample de ninguém. Isso evita tanto o direito
autoral da composição (já expirado, domínio público) quanto o direito
conexo da gravação/fonograma, que continuaria protegido se fosse a
gravação de um pianista específico — aqui a "gravação" é nova, gerada por
você mesmo. Os títulos evitam citar nomes de compositores específicos pra
não confundir marca ("estilo barroco" em vez de "estilo Bach", por
exemplo) — ajuste em `scripts/moods.py` como preferir.
