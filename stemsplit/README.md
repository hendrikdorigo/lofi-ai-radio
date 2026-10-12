# StemSplit 🎛️

Separe qualquer música em faixas individuais (stems) — voz, guitarras, baixo,
bateria, teclado — direto no seu computador, sem enviar nada para a internet.

Feito pensando em quem quer **estudar e tocar junto**: músicas de bandas como
Avenged Sevenfold, com guitarras dobradas, duetos em harmonia, solos, voz
principal e backing vocals.

- Arraste a música, escolha o modo, espere a barra encher.
- Ouça cada stem num player multitrack com **Mute**, **Solo** e **volume**.
- Mude a **velocidade sem mudar o tom**, **transponha o tom**, faça **loop A-B**.
- Presets de **Karaokê / Play-along**: "sem guitarra solo", "sem voz"…
- Baixe cada stem, todos em **ZIP**, ou um **mix personalizado** só com os canais ativos.
- **BPM e tom** detectados automaticamente.
- Saída em **MP3 320 kbps**, **WAV 16/24 bits** ou **FLAC**.

---

## Sumário

1. [Modos de separação](#modos-de-separação)
2. [Como funciona por dentro](#como-funciona-por-dentro)
3. [Requisitos de hardware](#requisitos-de-hardware)
4. [Instalação com Docker (mais fácil)](#instalação-com-docker-mais-fácil)
5. [Instalação manual](#instalação-manual-sem-docker)
6. [Uso pela linha de comando](#uso-pela-linha-de-comando)
7. [Configuração](#configuração-variáveis-de-ambiente)
8. [API](#api)
9. [Estrutura de pastas](#estrutura-de-pastas)
10. [Limitações conhecidas](#limitações-conhecidas)
11. [Sugestões de melhoria](#sugestões-de-melhoria)

---

## Modos de separação

| Modo | Stems | Modelos | Quando usar |
|---|---|---|---|
| **Rápido** | Voz, bateria, baixo, outros | Demucs `htdemucs` | Karaokê simples, testar rápido |
| **Completo** | + guitarra e teclado/piano | Demucs `htdemucs_6s` | A maioria dos casos |
| **Detalhado** | Voz principal, backing vocals, guitarra solo, guitarra base, guitarra 1 (esq.), guitarra 2 (dir.), baixo, bateria, teclado, outros | BS-RoFormer + Demucs 6s + Mel-Band RoFormer Karaokê + análise estéreo | Estudar solos e duetos de guitarra, separar coros |

Em qualquer modo (exceto Rápido na interface) dá para marcar **"Separar também a
bateria"** → bumbo, caixa/tons e pratos.

> ⚠️ O modo **Detalhado** é bem mais lento e a divisão fina das guitarras é uma
> **estimativa** (veja [limitações](#limitações-conhecidas)).

## Como funciona por dentro

Pipeline em cascata do modo Detalhado:

```
música ──► BS-RoFormer ──► voz ───────► Mel-Band RoFormer Karaokê ──► voz principal
                │                                                 └─► backing vocals
                └────────► instrumental ──► Demucs htdemucs_6s ──► bateria ──► (bumbo/caixa/pratos)
                                                           ├─► baixo
                                                           ├─► teclado
                                                           ├─► outros (+ restos de voz)
                                                           └─► guitarra ──► análise estéreo + HPSS
                                                                             ├─► guitarra 1 (esquerda)
                                                                             ├─► guitarra 2 (direita)
                                                                             ├─► guitarra solo (centro, sustentada)
                                                                             └─► guitarra base (centro, percussiva/grave)
```

- **Guitarra 1 / 2**: para cada ponto tempo-frequência do espectrograma, mede
  quanto o som está à esquerda ou à direita. Em gravações de metal as bases
  costumam ser gravadas duas vezes e abertas em L/R, e duetos em harmonia
  também — então isso separa bem "quem está de cada lado".
- **Solo × base**: o que sobra no centro é dividido por *HPSS* (separação
  harmônico/percussivo): notas sustentadas e agudas → solo; palhetadas abafadas,
  ataques e graves → base.
- As 4 partes de guitarra **somam exatamente** o stem de guitarra original — nada
  se perde, e o player continua soando como a música original com tudo ligado.
- Se um modelo RoFormer não puder ser carregado, o pipeline continua com o
  Demucs e mostra um aviso na tela (em vez de falhar).

## Requisitos de hardware

| | Mínimo | Recomendado |
|---|---|---|
| Sistema | Linux, Windows (WSL2 ou nativo), macOS | Linux ou Windows com GPU NVIDIA |
| RAM | 8 GB (modos Rápido/Completo) | 16 GB (necessário para o modo Detalhado) |
| GPU | — (roda em CPU) | NVIDIA com 6 GB+ de VRAM (CUDA) |
| Disco | ~6 GB (dependências + ~2 GB de modelos) | SSD |
| Primeira execução | Precisa de internet para baixar os modelos | Depois funciona offline |

**Tempo de processamento** (aproximado, música de 5 minutos):

| Modo | CPU 4 núcleos | GPU NVIDIA média |
|---|---|---|
| Rápido / Completo | 3 a 10 min | menos de 1 min |
| Detalhado | 30 min a 1 h (com os modelos MDX-Net, escolhidos automaticamente em CPU) | 2 a 5 min (com RoFormer) |

Em CPU o app usa automaticamente modelos de voz MDX-Net, bem mais leves: medido em
4 núcleos, 20 s de áudio levam 21 s (voz) e 28 s (voz principal × backing), contra
237 s e ~130 s dos RoFormer. A qualidade é um pouco menor; com GPU o app usa os
RoFormer. Os demais números são estimativas — varia muito de máquina para máquina.
**Para o modo Detalhado, uma GPU NVIDIA faz enorme diferença.** Em Mac com
Apple Silicon o PyTorch usa MPS automaticamente para o Demucs.

## Instalação com Docker (mais fácil)

1. Instale o [Docker Desktop](https://www.docker.com/products/docker-desktop/) (ou Docker Engine no Linux).
2. Baixe este projeto e entre na pasta `stemsplit`:
   ```bash
   cd stemsplit
   ```
3. Suba o app:
   ```bash
   # Só CPU:
   docker compose up --build

   # Com GPU NVIDIA (precisa do NVIDIA Container Toolkit):
   docker compose --profile gpu up --build stemsplit-gpu
   ```
4. Abra **http://localhost:8000** no navegador.

O histórico e os stems ficam em `./dados` e os modelos em `./modelos` (são
baixados uma vez só, ~2 GB no total). O app só escuta em `127.0.0.1` — ninguém
na sua rede consegue acessar.

### Memória do Docker no Windows

No Windows, o Docker roda dentro do WSL2, que por padrão só usa **metade da RAM** do
PC. O modo Detalhado pode estourar esse limite: aí o próprio Docker trava (no
navegador aparecem erros `ERR_EMPTY_RESPONSE` e `docker compose ps` responde
`500 Internal Server Error`). Para liberar mais memória, crie o arquivo
`C:\Users\<seu usuário>\.wslconfig` com:

```ini
[wsl2]
memory=12GB   # ~75% da RAM do PC
swap=8GB
```

Depois rode `wsl --shutdown` no PowerShell e abra o Docker Desktop de novo.

Se uma música for interrompida (servidor caiu, PC desligou), ela aparece no
histórico com erro e os botões **Tentar de novo** — no modo Detalhado as etapas já
concluídas são aproveitadas — ou **Tentar no modo Completo**, que usa bem menos memória.

## Instalação manual (sem Docker)

### Pré-requisitos

- **Python 3.10 a 3.12** (3.11 recomendado)
- **Node.js 18+** (só para compilar a interface)
- **ffmpeg** no PATH
  - Ubuntu/Debian: `sudo apt install ffmpeg`
  - macOS: `brew install ffmpeg rubberband`
  - Windows: `winget install ffmpeg`

### Passo a passo

```bash
cd stemsplit/backend

# 1) Ambiente virtual
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 2) PyTorch — escolha UMA linha:
pip install torch==2.5.1 torchaudio==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cpu     # só CPU
pip install torch==2.5.1 torchaudio==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cu121   # GPU NVIDIA

# 3) Demais dependências
#    (com GPU NVIDIA, troque "audio-separator[cpu]" por "audio-separator[gpu]" no requirements.txt)
pip install -r requirements.txt

# 4) Compile a interface (uma vez)
cd ../frontend
npm install
npm run build

# 5) Inicie o servidor
cd ../backend
python -m stemsplit servidor
```

Abra **http://localhost:8000**.

### Modo de desenvolvimento (interface com recarga automática)

```bash
# terminal 1
cd backend && python -m stemsplit servidor
# terminal 2
cd frontend && npm run dev     # abre em http://localhost:5173
```

### Testes

```bash
cd backend
pip install -r requirements-dev.txt
pytest
```

Os testes não baixam modelos: cobrem a separação por DSP, análise de BPM/tom,
exportação em todos os formatos, transposição e o fluxo completo da API
(upload → fila → progresso → downloads → histórico) com um separador simulado.

## Uso pela linha de comando

```bash
cd backend

# Separar (modo Completo, WAV 24 bits, pasta "<nome>_stems")
python -m stemsplit separar "Afterlife.mp3"

# Modo detalhado, com bateria dividida, em FLAC, numa pasta escolhida
python -m stemsplit separar "Afterlife.mp3" --modo detalhado --bateria --formato flac --saida ./afterlife

# Só detectar BPM e tom
python -m stemsplit analisar "Afterlife.mp3"

# Servidor em outra porta / acessível na rede local (cuidado: fica visível para a rede)
python -m stemsplit servidor --porta 9000 --host 0.0.0.0
```

Saída de exemplo (ilustrativa):

```
StemSplit — modo Detalhado em GPU (NVIDIA GeForce RTX 3060)
Duração: 352s  |  BPM: 128.0  |  Tom: Mi menor
[##############################] 100.0%  Salvando arquivos
  ✔ afterlife/vocal_principal.flac
  ✔ afterlife/backing_vocals.flac
  ✔ afterlife/guitarra_solo.flac
  ...
```

### Dicas para o caso de uso de guitarra

- **Tirar um solo**: modo Detalhado → preset **"Sem guitarra solo"** para tocar
  por cima, ou **Solo (S)** na "Guitarra solo" para ouvir só ela. Use **loop A-B**
  no trecho e diminua a **velocidade para 70–80%**.
- **Duetos/harmonias** (ex.: dobras do Synyster Gates e Zacky Vengeance): ouça
  **Guitarra 1 (esq.)** e **Guitarra 2 (dir.)** separadamente com Solo.
- **Afinação diferente** (ex.: música em Drop D / meio tom abaixo): use
  **Transpor tom** para trazer a música para a sua afinação.

## Configuração (variáveis de ambiente)

| Variável | Padrão | Descrição |
|---|---|---|
| `STEMSPLIT_DATA_DIR` | `./data` | Histórico e stems gerados |
| `STEMSPLIT_MODELS_DIR` | `./models` | Cache dos modelos |
| `STEMSPLIT_DEVICE` | `auto` | `auto`, `cuda`, `mps` ou `cpu` |
| `STEMSPLIT_DEMUCS_4S_MODEL` | `htdemucs` | Modelo do modo Rápido (ex.: `htdemucs_ft`, mais lento e melhor) |
| `STEMSPLIT_DEMUCS_6S_MODEL` | `htdemucs_6s` | Modelo de 6 stems |
| `STEMSPLIT_VOCAL_MODEL` | `auto` | Voz × instrumental. `auto` = BS-RoFormer em GPU, `UVR-MDX-NET-Voc_FT.onnx` em CPU |
| `STEMSPLIT_KARAOKE_MODEL` | `auto` | Voz principal × backing. `auto` = Mel-Band RoFormer Karaokê em GPU, `UVR_MDXNET_KARA_2.onnx` em CPU |
| `STEMSPLIT_GUITAR_MODEL` | *(vazio)* | Modelo dedicado de guitarra do audio-separator, se você tiver um |
| `STEMSPLIT_DRUM_MODEL` | *(vazio)* | Ex.: `MDX23C-DrumSep-aufr33-jarredou.ckpt` (bumbo/caixa/tons/pratos por IA, bem melhor que os filtros) |
| `STEMSPLIT_ROFORMER_OVERLAP` | `auto` | Sobreposição dos blocos do RoFormer: `auto` = 8 em GPU, 2 em CPU |
| `STEMSPLIT_MAX_UPLOAD_MB` | `200` | Tamanho máximo de upload |
| `STEMSPLIT_PREVIEW_BITRATE` | `192k` | Qualidade das prévias usadas no player |

Para ver todos os modelos disponíveis no audio-separator: `audio-separator --list_models`.

## API

Documentação interativa em **http://localhost:8000/docs**.

| Método | Rota | Descrição |
|---|---|---|
| GET | `/api/saude` | Dispositivo, modos e formatos |
| POST | `/api/jobs` | Envia música (multipart: `arquivo`, `modo`, `bateria`) |
| GET | `/api/jobs` | Histórico |
| GET | `/api/jobs/{id}` | Estado do job |
| DELETE | `/api/jobs/{id}` | Apaga job e arquivos |
| GET | `/api/jobs/{id}/eventos` | Progresso em tempo real (Server-Sent Events) |
| GET | `/api/jobs/{id}/ondas` | Formas de onda |
| GET | `/api/jobs/{id}/previa/{stem}?tom=0` | MP3 para o player |
| GET | `/api/jobs/{id}/baixar/{stem}?formato=wav24&tom=0` | Download de um stem |
| GET | `/api/jobs/{id}/zip?formato=wav24&tom=0` | Todos os stems em ZIP |
| POST | `/api/jobs/{id}/tentar-novamente` | Refaz um job com erro (`{"modo": "completo"}` opcional) |
| POST | `/api/jobs/{id}/mix` | Mix personalizado `{"volumes": {"baixo": 1, "vocal": 0}, "formato": "mp3", "tom": 0}` |

Exemplo com `curl`:

```bash
curl -F arquivo=@musica.mp3 -F modo=completo http://localhost:8000/api/jobs
```

## Estrutura de pastas

```
stemsplit/
├── Dockerfile                 imagem única (frontend compilado + backend)
├── docker-compose.yml         perfis CPU e GPU
├── README.md
├── backend/
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   ├── stemsplit/
│   │   ├── __main__.py        linha de comando (separar, analisar, servidor)
│   │   ├── config.py          configurações (variáveis STEMSPLIT_*)
│   │   ├── device.py          escolha CUDA / MPS / CPU
│   │   ├── audio_io.py        leitura (ffmpeg), exportação, transposição, formas de onda
│   │   ├── stems.py           catálogo de stems (nomes em pt-BR, grupos, cores)
│   │   ├── pipeline.py        cascata de separação dos 3 modos
│   │   ├── analysis.py        BPM e tom (librosa + Krumhansl-Schmuckler)
│   │   ├── jobs.py            fila de processamento e histórico em disco
│   │   ├── export.py          downloads: stem, ZIP, mix personalizado (com cache)
│   │   ├── api.py             API FastAPI + SSE + serve a interface
│   │   └── separators/
│   │       ├── demucs_backend.py    Demucs (4 e 6 stems)
│   │       ├── roformer_backend.py  BS/Mel-Band RoFormer via audio-separator
│   │       └── dsp.py               guitarras L/R/solo/base e bateria por frequência
│   └── tests/
└── frontend/                  React + TypeScript + Tailwind (Vite)
    └── src/
        ├── App.tsx            telas: início, progresso, resultado
        ├── lib/
        │   ├── api.ts         cliente da API
        │   ├── useMultitrack.ts  motor do player (sincronia, mute/solo, loop, velocidade)
        │   └── format.ts
        └── components/
            ├── UploadPanel.tsx    arrastar arquivo + escolha de modo
            ├── ProgressPanel.tsx  barra de progresso em tempo real
            ├── Player.tsx         transporte, velocidade, tom, loop, presets, downloads
            ├── TrackRow.tsx       canal: M / S / volume / download
            ├── Waveform.tsx       forma de onda clicável
            └── HistoryList.tsx    histórico
```

## Limitações conhecidas

1. **Guitarra solo × base e guitarra 1 × 2 são estimativas.** Não existe (ainda)
   modelo open source confiável treinado para separar guitarra base de solo. A
   divisão usa a posição no estéreo e o caráter do som:
   - funciona bem quando as guitarras estão abertas em L/R (muito comum no metal);
   - **não separa duas guitarras na mesma posição** do estéreo (ex.: solo e base
     ambos no centro, ou gravações mono/antigas) — nesse caso o app mostra um aviso;
   - o "solo" pode trazer um pouco de base sustentada (acordes abertos) e vice-versa.
2. **Voz principal × backing vocals** depende do modelo Karaokê: harmonias muito
   próximas da voz principal, ou gritos dobrados em uníssono, podem cair no stem errado.
3. **Bateria por frequência** (sem `STEMSPLIT_DRUM_MODEL`) é aproximada: tons
   graves vazam para o bumbo e o chimbal para a caixa. Use o modelo DrumSep para
   resultados bem melhores.
4. **Teclado/orquestra**: o Demucs só tem stem de *piano*; cordas, sintetizadores
   e orquestra costumam ir para "outros".
5. **Desempenho em CPU**: no modo Detalhado o app troca os RoFormer pelos MDX-Net
   (cerca de 10× mais rápidos, qualidade um pouco menor). Para forçar os RoFormer em
   CPU, defina `STEMSPLIT_VOCAL_MODEL` e `STEMSPLIT_KARAOKE_MODEL` — fica muito lento.
6. **Primeira execução precisa de internet** para baixar ~2 GB de modelos
   (Demucs do servidor da Meta; RoFormer de releases do GitHub). Depois, tudo
   funciona offline.
7. **Player**: cada stem toca num elemento `<audio>` e o app realinha os canais
   continuamente; em computadores muito lentos pode haver um leve "flanger" por
   alguns milissegundos ao pular de posição. A velocidade usa o algoritmo do
   navegador (bom até ~70%; abaixo disso fica com mais artefatos) e **não** é
   aplicada aos downloads (a transposição é).
8. **Memória**: o modo Detalhado mantém várias versões da música na memória ao mesmo
   tempo; com pouca RAM (ou com o limite padrão do Docker no Windows) o processo pode
   ser encerrado pelo sistema. Veja [Memória do Docker no Windows](#memória-do-docker-no-windows).
9. **Um job por vez**: a fila processa uma música de cada vez para não estourar
   a memória da GPU.
10. **Sem autenticação**: o app foi feito para uso local. Não exponha a porta na
   internet.

## Sugestões de melhoria

- **Modelo dedicado para guitarra solo/base**: treinar ou ajustar um
  Mel-Band RoFormer com dados de multitracks de metal; o pipeline já aceita
  `STEMSPLIT_GUITAR_MODEL` e é fácil adicionar uma etapa "lead/rhythm".
- **Separação por timbre**: agrupar notas por timbre (embeddings + clustering)
  para separar duas guitarras no centro.
- **Ensembles**: combinar vários modelos (ex.: `htdemucs_ft` + RoFormer) e fazer
  média dos resultados, como o UVR faz — melhor qualidade, mais lento.
- **Player com Web Audio + time-stretch em AudioWorklet** (ex.: SoundTouch/Rubber
  Band em WASM): sincronia perfeita por amostra e velocidade de melhor qualidade.
- **Exportar com velocidade alterada** (rubberband no servidor).
- **Transcrição em tablatura** do stem de guitarra (ex.: Basic Pitch → MIDI → tab).
- **Detecção de afinação** (Drop D, Eb) e sugestão automática de transposição.
- **Fila com vários workers** quando houver mais de uma GPU.
- **Aplicativo desktop** (Tauri/Electron) empacotando o backend, para instalar com
  um clique.
