"""Fila de processamento e histórico de músicas.

Cada música enviada vira um *job* com pasta própria em ``data/jobs/<id>/``::

    original.mp3        arquivo enviado
    job.json            estado, stems, análise e avisos (é o "histórico")
    stems/<stem>.wav    stems em WAV float32 (qualidade máxima, sem clipping)
    previews/*.mp3      prévias leves para o player do navegador
    peaks.json          formas de onda resumidas
    exports/            downloads já gerados (cache)

Um único worker processa um job por vez — a GPU/CPU fica toda para ele e não
falta memória. O estado é salvo em disco, então o histórico sobrevive a
reinícios e jobs interrompidos voltam para a fila.
"""

from __future__ import annotations

import json
import queue
import shutil
import threading
import time
import traceback
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import analysis, audio_io, pipeline, stems as stem_catalog
from .config import settings
from .device import device_label

JOB_ID_LEN = 12


@dataclass
class Job:
    id: str
    filename: str
    mode: str
    split_drums: bool = False
    status: str = "na_fila"  # na_fila | processando | concluido | erro
    progress: float = 0.0
    stage: str = "Aguardando na fila"
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    seconds: float | None = None
    device: str | None = None
    stems: list[dict] = field(default_factory=list)
    analysis: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    original_name: str = "original"

    @property
    def dir(self) -> Path:
        return settings.jobs_dir / self.id

    @property
    def title(self) -> str:
        return Path(self.filename).stem

    def stem_names(self) -> list[str]:
        return [s["name"] for s in self.stems]

    def to_dict(self) -> dict:
        data = asdict(self)
        data["title"] = self.title
        return data


def valid_job_id(job_id: str) -> bool:
    return len(job_id) == JOB_ID_LEN and all(c in "0123456789abcdef" for c in job_id)


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._queue: queue.Queue[str] = queue.Queue()
        self._lock = threading.Lock()
        self._version = 0  # muda a cada atualização, usado pelo SSE
        self._worker: threading.Thread | None = None

    # ------------------------------------------------------------ persistência
    def load_history(self) -> None:
        settings.ensure_dirs()
        for job_file in sorted(settings.jobs_dir.glob("*/job.json")):
            try:
                job = Job(**json.loads(job_file.read_text(encoding="utf-8")))
            except Exception:  # noqa: BLE001 - ignora job corrompido
                continue
            self._jobs[job.id] = job
            if job.status in ("na_fila", "processando"):
                job.status, job.progress, job.stage = "na_fila", 0.0, "Retomando após reinício"
                self._queue.put(job.id)

    def _save(self, job: Job) -> None:
        job.dir.mkdir(parents=True, exist_ok=True)
        tmp = job.dir / "job.json.tmp"
        tmp.write_text(json.dumps(asdict(job), ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(job.dir / "job.json")

    def _touch(self, job: Job, persist: bool = False) -> None:
        with self._lock:
            self._version += 1
        if persist:
            self._save(job)

    @property
    def version(self) -> int:
        return self._version

    # ------------------------------------------------------------ API pública
    def start(self) -> None:
        if self._worker is None:
            self._worker = threading.Thread(target=self._run, name="stemsplit-worker", daemon=True)
            self._worker.start()

    def create(self, upload: Path, filename: str, mode: str, split_drums: bool) -> Job:
        """Registra um job a partir de um arquivo já salvo em ``upload`` e o enfileira."""
        if mode not in pipeline.MODES:
            raise ValueError(f"Modo inválido: {mode}")
        job = Job(id=uuid.uuid4().hex[:JOB_ID_LEN], filename=filename, mode=mode, split_drums=split_drums)
        job.original_name = "original" + Path(filename).suffix.lower()
        job.dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(upload), job.dir / job.original_name)
        self._jobs[job.id] = job
        self._touch(job, persist=True)
        self._queue.put(job.id)
        return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id) if valid_job_id(job_id) else None

    def list(self) -> list[Job]:
        return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)

    def queue_position(self, job_id: str) -> int | None:
        """Posição na fila (1 = próximo). ``None`` se não está esperando."""
        waiting = [j for j in self.list()[::-1] if j.status == "na_fila"]
        ids = [j.id for j in waiting]
        return ids.index(job_id) + 1 if job_id in ids else None

    def delete(self, job_id: str) -> bool:
        job = self.get(job_id)
        if job is None:
            return False
        if job.status == "processando":
            raise RuntimeError("Não dá para apagar uma música enquanto ela está sendo processada.")
        self._jobs.pop(job_id, None)
        shutil.rmtree(job.dir, ignore_errors=True)
        self._touch(job)
        return True

    # ------------------------------------------------------------ worker
    def _run(self) -> None:
        while True:
            job_id = self._queue.get()
            job = self._jobs.get(job_id)
            if job is None or job.status != "na_fila":
                continue
            try:
                self.process(job)
            except Exception as exc:  # noqa: BLE001 - qualquer erro vira mensagem para o usuário
                traceback.print_exc()
                job.status, job.error = "erro", str(exc) or exc.__class__.__name__
                job.stage = "Falhou"
                job.finished_at = time.time()
                self._touch(job, persist=True)

    def _report(self, job: Job, stage: str, progress: float) -> None:
        job.stage, job.progress = stage, round(progress, 4)
        self._touch(job)

    def process(self, job: Job) -> None:
        """Executa a separação completa de um job (também usado pela CLI/testes)."""
        start = time.time()
        job.status, job.error, job.device = "processando", None, device_label()
        self._report(job, "Lendo o arquivo de áudio", 0.01)
        self._save(job)

        audio = audio_io.load_audio(job.dir / job.original_name)

        self._report(job, "Detectando BPM e tom", 0.02)
        job.analysis = analysis.analyze(audio, settings.sample_rate)
        self._touch(job, persist=True)

        # A separação ocupa de 5% a 90% da barra de progresso.
        def on_progress(stage: str, frac: float) -> None:
            self._report(job, stage, 0.05 + 0.85 * frac)

        result = pipeline.separate(audio, job.mode, job.split_drums, on_progress)
        job.warnings = result.warnings

        self._report(job, "Gerando prévias e formas de onda", 0.9)
        save_stems(job.dir, result.stems)

        job.stems = stem_catalog.describe(list(result.stems))
        job.status, job.progress, job.stage = "concluido", 1.0, "Pronto!"
        job.finished_at = time.time()
        job.seconds = round(job.finished_at - start, 1)
        self._touch(job, persist=True)


def save_stems(job_dir: Path, stems: dict) -> None:
    """Salva os stems em WAV float, as prévias MP3 e o arquivo de formas de onda."""
    peaks = {}
    for name, audio in stems.items():
        audio_io.save_wav_float(job_dir / "stems" / f"{name}.wav", audio)
        preview = job_dir / "previews" / f"{name}.mp3"
        preview.parent.mkdir(parents=True, exist_ok=True)
        audio_io.encode_mp3(audio, preview, settings.sample_rate, settings.preview_bitrate)
        peaks[name] = audio_io.compute_peaks(audio)
    (job_dir / "peaks.json").write_text(json.dumps(peaks), encoding="utf-8")


manager = JobManager()
