"""Sunucu-taraflı arka plan toplu çeviri.

Tarayıcı sekmesi kapansa da sürer (eski istemci-taraflı döngünün yerine). İş
bellek-içi bir kayıtta tutulur; durum polling ile okunur. Çekme zaten global
kilitle serileştirildiği için işler doğal olarak sıralı koşar.

Not: bellek-içi → sunucu yeniden başlarsa iş kaybolur (kişisel araç; çevrilen
bölümler kalıcı önbellekte zaten durur, yeniden başlatınca atlanır).
"""
from __future__ import annotations

import threading
import time
import uuid

from . import pipeline
from .fetch import FetchError
from .translate import TranslateError

_JOBS: dict[str, dict] = {}
_LOCK = threading.Lock()
_MAX_JOBS = 50  # kayıt sınırsız büyümesin (en eski bitmişleri buda)


def _set(job_id: str, **fields) -> None:
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is not None:
            job.update(fields)


def _should_stop(job_id: str) -> bool:
    with _LOCK:
        job = _JOBS.get(job_id)
        return bool(job and job.get("stop"))


def get_status(job_id: str) -> dict | None:
    with _LOCK:
        job = _JOBS.get(job_id)
        return dict(job) if job else None


def stop(job_id: str) -> bool:
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job:
            return False
        job["stop"] = True
        return True


def _prune() -> None:
    """Bitmiş eski işleri buda (kayıt _MAX_JOBS'u aşmasın)."""
    if len(_JOBS) <= _MAX_JOBS:
        return
    finished = sorted(
        (j for j in _JOBS.values() if j["state"] != "running"),
        key=lambda j: j.get("updated_at", 0),
    )
    for job in finished[: len(_JOBS) - _MAX_JOBS]:
        _JOBS.pop(job["id"], None)


def start_bulk(slug: str, start_url: str, count: int, api_key: str | None) -> str:
    """Arka plan toplu çeviri başlat; iş kimliğini döndür."""
    job_id = uuid.uuid4().hex
    with _LOCK:
        _JOBS[job_id] = {
            "id": job_id,
            "slug": slug,
            "state": "running",  # running | done | stopped | error
            "total": count,
            "done": 0,
            "translated": 0,
            "message": "Hazırlanıyor…",
            "stop": False,
            "updated_at": time.time(),
        }
        _prune()
    thread = threading.Thread(
        target=_run, args=(job_id, start_url, count, api_key), daemon=True
    )
    thread.start()
    return job_id


def _run(job_id: str, start_url: str, count: int, api_key: str | None) -> None:
    url = start_url
    done = 0
    translated = 0
    for i in range(count):
        if _should_stop(job_id):
            _set(job_id, state="stopped",
                 message=f"Durduruldu. {translated} yeni bölüm çevrildi.",
                 updated_at=time.time())
            return
        _set(job_id, message=f"Bölüm {i + 1} / {count} hazırlanıyor…",
             updated_at=time.time())
        try:
            data = pipeline.get_or_translate(url, api_key)
        except (FetchError, TranslateError) as exc:
            _set(job_id, state="error",
                 message=f"Durdu: {exc}", done=done, translated=translated,
                 updated_at=time.time())
            return
        except Exception as exc:  # beklenmedik; işi sızdırmadan bitir
            _set(job_id, state="error", message=f"Beklenmedik hata: {exc}",
                 done=done, translated=translated, updated_at=time.time())
            return
        done += 1
        if not data.get("cached"):
            translated += 1
        _set(job_id, done=done, translated=translated,
             message=f"{done} / {count} bitti — {data.get('title', '')} "
                     f"({translated} yeni)",
             updated_at=time.time())
        if not data.get("next_url"):
            _set(job_id, state="done",
                 message=f"Son bölüme ulaşıldı. {translated} yeni bölüm çevrildi.",
                 updated_at=time.time())
            return
        url = data["next_url"]
    _set(job_id, state="done",
         message=f"Bitti — {translated} yeni bölüm çevrildi.",
         updated_at=time.time())
