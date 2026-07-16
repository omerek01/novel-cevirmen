"""jobs: arka plan zinciri, hata/durdurma, budama ve SQLite devamlılığı."""
import threading
import time

import pytest

from core import jobs


def _wait(job_id, states, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = jobs.get_status(job_id)
        if status and status["state"] in states:
            return status
        time.sleep(0.01)
    pytest.fail(f"İş zamanında bitmedi: {jobs.get_status(job_id)}")


@pytest.fixture(autouse=True)
def clean_job_memory():
    with jobs._LOCK:
        jobs._JOBS.clear()
        jobs._THREADS.clear()
    yield
    with jobs._LOCK:
        ids = list(jobs._JOBS)
    for job_id in ids:
        jobs.stop(job_id)
    deadline = time.monotonic() + 1
    while time.monotonic() < deadline:
        with jobs._LOCK:
            if not any(t.is_alive() for t in jobs._THREADS.values()):
                break
        time.sleep(0.01)
    with jobs._LOCK:
        jobs._JOBS.clear()
        jobs._THREADS.clear()


def test_start_bulk_follows_chain_until_done(monkeypatch):
    calls = []

    def fake(url, api_key):
        calls.append(url)
        no = int(url[-1])
        return {
            "title": f"Bölüm {no}",
            "next_url": f"u{no + 1}" if no < 3 else None,
            "cached": False,
        }

    monkeypatch.setattr(jobs.pipeline, "get_or_translate", fake)
    job_id = jobs.start_bulk("kitap", "u1", 5, None)
    status = _wait(job_id, {"done"})

    assert job_id
    assert calls == ["u1", "u2", "u3"]
    assert status["done"] == 3
    assert status["translated"] == 3
    assert status["total"] == 5


def test_start_bulk_records_error(monkeypatch):
    def fake(url, api_key):
        raise RuntimeError("bozuk bölüm")

    monkeypatch.setattr(jobs.pipeline, "get_or_translate", fake)
    job_id = jobs.start_bulk("kitap", "u1", 2, None)
    status = _wait(job_id, {"error"})

    assert "bozuk bölüm" in status["message"]
    assert status["done"] == 0


def test_stop_marks_running_job_stopped(monkeypatch):
    entered = threading.Event()
    release = threading.Event()

    def fake(url, api_key):
        entered.set()
        release.wait(1)
        return {"title": "Bölüm", "next_url": "u2", "cached": False}

    monkeypatch.setattr(jobs.pipeline, "get_or_translate", fake)
    job_id = jobs.start_bulk("kitap", "u1", 2, None)
    assert entered.wait(1)
    assert jobs.stop(job_id) is True
    assert jobs.get_status(job_id)["state"] == "stopped"
    release.set()
    assert _wait(job_id, {"stopped"})["state"] == "stopped"


def test_prune_caps_finished_jobs():
    with jobs._LOCK:
        for no in range(jobs._MAX_JOBS + 7):
            job_id = f"j{no}"
            jobs._JOBS[job_id] = {
                "id": job_id,
                "state": "done",
                "updated_at": no,
            }

        jobs._prune()

    assert len(jobs._JOBS) == jobs._MAX_JOBS
    assert "j0" not in jobs._JOBS


def test_status_roundtrip_reads_persisted_row(monkeypatch):
    monkeypatch.setattr(
        jobs.pipeline,
        "get_or_translate",
        lambda url, api_key: {"title": "B1", "next_url": None, "cached": False},
    )
    job_id = jobs.start_bulk("kitap", "u1", 1, None)
    original = _wait(job_id, {"done"})
    with jobs._LOCK:
        jobs._JOBS.clear()

    restored = jobs.get_status(job_id)
    assert restored["state"] == "done"
    assert restored["done"] == original["done"] == 1
    assert jobs.get_book_job("kitap")["id"] == job_id


def test_resume_running_uses_checkpoint_and_single_flight(monkeypatch):
    interrupted = {
        "id": "yarim",
        "slug": "kitap",
        "start_url": "u1",
        "count": 3,
        "done": 1,
        "translated": 1,
        "state": "running",
        "message": "Yarım kaldı",
        "next_url": "u2",
        "updated_at": time.time(),
        "stop": False,
    }
    jobs._persist(interrupted)
    entered = threading.Event()
    release = threading.Event()
    calls = []

    def fake(url, api_key):
        calls.append(url)
        if url == "u2":
            entered.set()
            release.wait(1)
        return {
            "title": url,
            "next_url": "u3" if url == "u2" else None,
            "cached": False,
        }

    monkeypatch.setattr(jobs.pipeline, "get_or_translate", fake)
    assert jobs.resume_running(None) == ["yarim"]
    assert entered.wait(1)
    assert jobs.resume_running(None) == []
    release.set()
    status = _wait("yarim", {"done"})

    assert calls == ["u2", "u3"]
    assert status["done"] == 3
    assert status["next_url"] is None
