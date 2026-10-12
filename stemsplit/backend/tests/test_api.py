"""Teste de ponta a ponta da API com um separador falso (não baixa modelos)."""

import io
import json
import time
import zipfile

import numpy as np
import pytest
import soundfile as sf

from conftest import SR, tone


@pytest.fixture
def client(monkeypatch):
    from fastapi.testclient import TestClient

    from stemsplit import api, jobs, pipeline

    def fake_separate(audio, mode, split_drums, progress, cache_dir=None):
        for i in range(5):
            progress("Separando (teste)", i / 5)
        n = audio.shape[1]
        names = pipeline.MODES[mode]["stems"]
        stems = {name: audio / len(names) for name in names}
        stems["outros"] = stems["outros"][:, :n]
        return pipeline.SeparationResult(stems=stems, warnings=["aviso de teste"])

    monkeypatch.setattr(jobs.pipeline, "separate", fake_separate)
    monkeypatch.setattr(jobs, "manager", jobs.JobManager())
    monkeypatch.setattr(api, "manager", jobs.manager)
    with TestClient(api.app) as c:
        yield c


def _wav_bytes() -> bytes:
    buf = io.BytesIO()
    audio = np.stack([tone(440, 3), tone(660, 3)]).T
    sf.write(buf, audio, SR, format="WAV")
    return buf.getvalue()


def _wait_done(client, job_id):
    for _ in range(600):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("concluido", "erro"):
            return job
        time.sleep(0.1)
    raise AssertionError("job não terminou")


def test_full_flow(client):
    assert client.get("/api/saude").json()["status"] == "ok"

    r = client.post("/api/jobs", files={"arquivo": ("Minha Música.wav", _wav_bytes(), "audio/wav")}, data={"modo": "completo"})
    assert r.status_code == 201, r.text
    job_id = r.json()["id"]

    job = _wait_done(client, job_id)
    assert job["status"] == "concluido", job
    assert job["warnings"] == ["aviso de teste"]
    assert job["analysis"]["duration"] == pytest.approx(3, abs=0.1)
    names = [s["name"] for s in job["stems"]]
    assert names[0] == "vocal" and "guitarra" in names

    # SSE devolve o estado final.
    events = client.get(f"/api/jobs/{job_id}/eventos").text
    assert json.loads(events.strip().split("data: ")[-1])["status"] == "concluido"

    peaks = client.get(f"/api/jobs/{job_id}/ondas").json()
    assert set(peaks) == set(names)

    r = client.get(f"/api/jobs/{job_id}/previa/vocal")
    assert r.status_code == 200 and r.headers["content-type"] == "audio/mpeg"
    r = client.get(f"/api/jobs/{job_id}/previa/vocal?tom=-2")
    assert r.status_code == 200

    r = client.get(f"/api/jobs/{job_id}/baixar/baixo?formato=flac")
    assert r.status_code == 200 and "Minha" in r.headers["content-disposition"]

    r = client.get(f"/api/jobs/{job_id}/zip?formato=mp3")
    assert len(zipfile.ZipFile(io.BytesIO(r.content)).namelist()) == len(names)

    r = client.post(f"/api/jobs/{job_id}/mix", json={"volumes": {"vocal": 0, "baixo": 1, "bateria": 0.5}, "formato": "wav16"})
    assert r.status_code == 200
    data, _ = sf.read(io.BytesIO(r.content))
    assert data.shape[1] == 2

    assert client.post(f"/api/jobs/{job_id}/mix", json={"volumes": {"vocal": 0}}).status_code == 400
    assert client.get(f"/api/jobs/{job_id}/baixar/inexistente").status_code == 400
    assert client.get(f"/api/jobs/{job_id}/previa/vocal?tom=40").status_code == 400

    assert [j["id"] for j in client.get("/api/jobs").json()] == [job_id]
    assert client.delete(f"/api/jobs/{job_id}").status_code == 204
    assert client.get(f"/api/jobs/{job_id}").status_code == 404


def test_rejects_bad_uploads(client):
    r = client.post("/api/jobs", files={"arquivo": ("x.txt", b"oi", "text/plain")})
    assert r.status_code == 400
    r = client.post("/api/jobs", files={"arquivo": ("x.mp3", b"", "audio/mpeg")})
    assert r.status_code == 400
    r = client.post("/api/jobs", files={"arquivo": ("x.mp3", b"123", "audio/mpeg")}, data={"modo": "turbo"})
    assert r.status_code == 400
    assert client.get("/api/jobs/../../etc").status_code == 404


def test_invalid_audio_marks_job_as_error(client):
    r = client.post("/api/jobs", files={"arquivo": ("ruim.mp3", b"isto nao e audio", "audio/mpeg")})
    job = _wait_done(client, r.json()["id"])
    assert job["status"] == "erro"
    assert "Não consegui ler" in job["error"]


def test_interrupted_job_becomes_error_and_can_be_retried(client):
    from stemsplit import api, jobs

    r = client.post("/api/jobs", files={"arquivo": ("a.wav", _wav_bytes(), "audio/wav")}, data={"modo": "detalhado"})
    job_id = r.json()["id"]
    _wait_done(client, job_id)

    # Simula queda do servidor no meio do processamento e um reinício.
    job = jobs.manager.get(job_id)
    job.status = "processando"
    jobs.manager._save(job)
    fresh = jobs.JobManager()
    fresh.load_history()
    assert fresh.get(job_id).status == "erro"
    assert "memória" in fresh.get(job_id).error

    api.manager._jobs[job_id] = fresh.get(job_id)
    assert client.post(f"/api/jobs/{job_id}/tentar-novamente", json={"modo": "turbo"}).status_code == 400
    r = client.post(f"/api/jobs/{job_id}/tentar-novamente", json={"modo": "completo"})
    assert r.status_code == 200 and r.json()["mode"] == "completo"
    assert _wait_done(client, job_id)["status"] == "concluido"
    # Só jobs com erro podem ser refeitos.
    assert client.post(f"/api/jobs/{job_id}/tentar-novamente").status_code == 409
