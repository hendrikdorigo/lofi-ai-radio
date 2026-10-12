"""API HTTP do StemSplit (FastAPI).

Rotas principais (todas sob ``/api``):

    GET    /saude                         dispositivo, modos e formatos disponíveis
    POST   /jobs                          envia música (multipart: arquivo, modo, bateria)
    GET    /jobs                          histórico
    GET    /jobs/{id}                     estado de um job
    DELETE /jobs/{id}                     apaga job e arquivos
    POST   /jobs/{id}/tentar-novamente    recoloca na fila um job com erro (opcional: outro modo)
    POST   /jobs/{id}/refazer-guitarras   refaz só a divisão das guitarras (modo Detalhado)
    GET    /jobs/{id}/eventos             progresso em tempo real (Server-Sent Events)
    GET    /jobs/{id}/ondas               formas de onda de todos os stems
    GET    /jobs/{id}/previa/{stem}       MP3 para o player (?tom=-2 transpõe)
    GET    /jobs/{id}/baixar/{stem}       download de um stem (?formato=wav24&tom=0)
    GET    /jobs/{id}/zip                 todos os stems em ZIP (?formato=&tom=)
    POST   /jobs/{id}/mix                 mix personalizado só com os canais ativos

Se existir ``frontend/dist`` (build do React), ele é servido em ``/``.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import export
from .audio_io import EXPORT_FORMATS
from .config import ALLOWED_EXTENSIONS, settings
from .device import device_label
from . import jobs
from .jobs import Job, manager
from .pipeline import MODES


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.ensure_dirs()
    manager.load_history()
    manager.start()
    yield


app = FastAPI(title="StemSplit", version="1.0.0", lifespan=lifespan)

# Em desenvolvimento o Vite roda em outra porta (5173).
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("STEMSPLIT_CORS", "http://localhost:5173,http://127.0.0.1:5173").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------- helpers
def _job_or_404(job_id: str) -> Job:
    job = manager.get(job_id)
    if job is None:
        raise HTTPException(404, "Música não encontrada no histórico.")
    return job


def _job_payload(job: Job) -> dict:
    data = job.to_dict()
    data["queue_position"] = manager.queue_position(job.id)
    return data


async def _run(fn, *args):
    """Roda trabalho pesado fora do event loop e converte erros em HTTP 400."""
    try:
        return await run_in_threadpool(fn, *args)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


def _download(result: tuple[Path, str]) -> FileResponse:
    path, name = result
    return FileResponse(path, filename=name)


# --------------------------------------------------------------------- rotas
@app.get("/api/saude")
def health() -> dict:
    return {
        "status": "ok",
        "dispositivo": device_label(),
        "modos": [{"id": k, "label": v["label"], "descricao": v["description"], "stems": v["stems"]} for k, v in MODES.items()],
        "formatos": [{"id": k, "label": v["label"]} for k, v in EXPORT_FORMATS.items()],
        "extensoes": sorted(ALLOWED_EXTENSIONS),
        "max_upload_mb": settings.max_upload_mb,
    }


@app.post("/api/jobs", status_code=201)
async def create_job(
    arquivo: UploadFile = File(...),
    modo: str = Form("completo"),
    bateria: bool = Form(False),
) -> dict:
    filename = Path(arquivo.filename or "musica").name
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Formato não suportado ({ext or 'sem extensão'}). Envie MP3, WAV, FLAC ou M4A.")
    if modo not in MODES:
        raise HTTPException(400, "Modo inválido. Escolha Rápido, Completo ou Detalhado.")

    # Grava em disco em blocos, respeitando o limite de tamanho.
    limit = settings.max_upload_mb * 1024 * 1024
    settings.ensure_dirs()
    fd, tmp_name = tempfile.mkstemp(suffix=ext, dir=settings.data_dir)
    size = 0
    try:
        with os.fdopen(fd, "wb") as out:
            while chunk := await arquivo.read(1024 * 1024):
                size += len(chunk)
                if size > limit:
                    raise HTTPException(413, f"Arquivo muito grande (máximo {settings.max_upload_mb} MB).")
                out.write(chunk)
        if size == 0:
            raise HTTPException(400, "O arquivo está vazio.")
        job = manager.create(Path(tmp_name), filename, modo, bateria)
    finally:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)
    return _job_payload(job)


@app.get("/api/jobs")
def list_jobs() -> list[dict]:
    return [_job_payload(j) for j in manager.list()]


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    return _job_payload(_job_or_404(job_id))


@app.delete("/api/jobs/{job_id}", status_code=204)
def delete_job(job_id: str) -> None:
    _job_or_404(job_id)
    try:
        manager.delete(job_id)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc


class RetryRequest(BaseModel):
    modo: str | None = None


@app.post("/api/jobs/{job_id}/tentar-novamente")
def retry_job(job_id: str, body: RetryRequest | None = None) -> dict:
    _job_or_404(job_id)
    try:
        job = manager.retry(job_id, body.modo if body else None)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    return _job_payload(job)


@app.post("/api/jobs/{job_id}/refazer-guitarras")
async def resplit_guitars(job_id: str) -> dict:
    """Refaz só a divisão das guitarras (rápido; útil após melhorias no algoritmo)."""
    return _job_payload(await _run(jobs.resplit_guitars, _job_or_404(job_id)))


@app.get("/api/jobs/{job_id}/eventos")
async def job_events(job_id: str, request: Request) -> StreamingResponse:
    """Server-Sent Events: envia o estado do job sempre que ele muda."""
    job = _job_or_404(job_id)

    async def stream():
        last = None
        while not await request.is_disconnected():
            payload = json.dumps(_job_payload(job), ensure_ascii=False)
            if payload != last:
                last = payload
                yield f"data: {payload}\n\n"
            if job.status in ("concluido", "erro"):
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.get("/api/jobs/{job_id}/ondas")
def job_peaks(job_id: str) -> dict:
    return export.peaks(_job_or_404(job_id))


@app.get("/api/jobs/{job_id}/previa/{stem}")
async def stem_preview(job_id: str, stem: str, tom: int = Query(0)) -> FileResponse:
    path = await _run(export.preview_path, _job_or_404(job_id), stem, tom)
    return FileResponse(path, media_type="audio/mpeg")


@app.get("/api/jobs/{job_id}/baixar/{stem}")
async def download_stem(job_id: str, stem: str, formato: str = "wav24", tom: int = 0) -> FileResponse:
    return _download(await _run(export.stem_file, _job_or_404(job_id), stem, formato, tom))


@app.get("/api/jobs/{job_id}/zip")
async def download_zip(job_id: str, formato: str = "wav24", tom: int = 0) -> FileResponse:
    return _download(await _run(export.zip_all, _job_or_404(job_id), formato, tom))


class MixRequest(BaseModel):
    volumes: dict[str, float] = Field(description="stem → volume (0 = desligado, 1 = original)")
    formato: str = "wav24"
    tom: int = 0


@app.post("/api/jobs/{job_id}/mix")
async def download_mix(job_id: str, body: MixRequest) -> FileResponse:
    return _download(await _run(export.mix, _job_or_404(job_id), body.volumes, body.formato, body.tom))


# --------------------------------------------------------------------- frontend
_dist = Path(os.environ.get("STEMSPLIT_FRONTEND_DIR", Path(__file__).resolve().parents[2] / "frontend" / "dist"))
if _dist.is_dir():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="frontend")
