# StemSplit — imagem única com backend (FastAPI) + frontend (React já compilado).
#
#   CPU: docker compose up --build
#   GPU: docker compose --profile gpu up --build stemsplit-gpu
#
# TORCH_VARIANT escolhe o build do PyTorch: "cpu" ou "cu121" (CUDA 12.1, placas NVIDIA).

# ---------- 1) Compila o frontend ----------
FROM node:20-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---------- 2) Backend Python ----------
FROM python:3.11-slim
ARG TORCH_VARIANT=cpu
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    STEMSPLIT_DATA_DIR=/data \
    STEMSPLIT_MODELS_DIR=/models \
    STEMSPLIT_FRONTEND_DIR=/app/frontend/dist

# ffmpeg do Debian já vem com rubberband (transposição de tom de boa qualidade).
# build-essential (gcc): o pacote diffq, dependência do audio-separator, é compilado na instalação.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg libsndfile1 build-essential \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install torch==2.5.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/${TORCH_VARIANT} \
 && if [ "$TORCH_VARIANT" = "cpu" ]; then EXTRA=cpu; else EXTRA=gpu; fi \
 && sed -i "s/audio-separator\[cpu\]/audio-separator[$EXTRA]/" requirements.txt \
 && pip install -r requirements.txt

COPY backend/stemsplit ./stemsplit
COPY --from=frontend /app/frontend/dist /app/frontend/dist

# /data = histórico e stems gerados; /models = pesos baixados na 1ª execução (~2 GB).
VOLUME ["/data", "/models"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/saude')" || exit 1
CMD ["python", "-m", "stemsplit", "servidor", "--host", "0.0.0.0", "--porta", "8000"]
