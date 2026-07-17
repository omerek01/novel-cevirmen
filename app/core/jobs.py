"""Sunucu-taraflı, SQLite checkpoint'li arka plan toplu çeviri.

Tarayıcı sekmesi kapansa da iş sürer. Her bölümden sonra sıradaki URL aynı
chapters.db dosyasına yazılır; sunucu yeniden başladığında yarım kalan işler bu
checkpoint'ten otomatik devam eder.
"""
from __future__ import annotations

import sqlite3
import threading
import time
import uuid

from . import db, pipeline
from .fetch import FetchError
from .translate import TranslateError

_JOBS: dict[str, dict] = {}
_THREADS: dict[str, threading.Thread] = {}
_LOCK = threading.RLock()
_MAX_JOBS = 50  # kayıt sınırsız büyümesin (en eski bitmişleri buda)


def _connect() -> sqlite3.Connection:
    conn = db.connect()
    # Terk edilmiş eski şemalı bir jobs tablosu (cursor_url + created_at NOT NULL,
    # next_url YOK) bu kodun SELECT/INSERT'iyle bağdaşmaz ve startup'ta çökertir.
    # next_url sütunu olmayan bir jobs tablosu varsa düşürüp doğru şemayla yeniden kur
    # (bir kerelik migration; tablo yalnız geçici iş durumu tutar, çeviriler chapters'ta).
    cols = {r[1] for r in conn.execute("PRAGMA table_info(jobs)")}
    if cols and "next_url" not in cols:
        conn.execute("DROP TABLE jobs")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            slug TEXT,
            start_url TEXT,
            count INTEGER,
            done INTEGER,
            translated INTEGER,
            state TEXT,
            message TEXT,
            next_url TEXT,
            updated_at REAL
        )
        """
    )
    conn.commit()
    return conn


def _public(job: dict) -> dict:
    """İç durdurma bayrağını gizleyip eski `total` API alanını korur."""
    out = {k: v for k, v in job.items() if k != "stop"}
    out["total"] = out.get("count", 0)
    return out


def _from_row(row) -> dict:
    return {
        "id": row[0],
        "slug": row[1],
        "start_url": row[2],
        "count": row[3],
        "done": row[4],
        "translated": row[5],
        "state": row[6],
        "message": row[7],
        "next_url": row[8],
        "updated_at": row[9],
        "stop": False,
    }


def _persist(job: dict) -> None:
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO jobs
                (id, slug, start_url, count, done, translated, state, message,
                 next_url, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job["id"], job["slug"], job["start_url"], job["count"],
                job["done"], job["translated"], job["state"], job["message"],
                job.get("next_url"), job["updated_at"],
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _load(job_id: str) -> dict | None:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT id, slug, start_url, count, done, translated, state, message, "
            "next_url, updated_at FROM jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
    finally:
        conn.close()
    return _from_row(row) if row else None


def _set(job_id: str, **fields) -> None:
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            job = _load(job_id)
            if job is None:
                return
            _JOBS[job_id] = job
        job.update(fields)
        # Kilit içinde persist et: bellek durumu asla DB checkpoint'inin ilerisinde
        # olmasın. Aksi halde get_status "done" görürken DB henüz eski satırı tutabilir
        # (resume yanlış yerden sürer / okuma yarışı). Bölüm başına kısa SQLite yazımı.
        _persist(dict(job))


def _should_stop(job_id: str) -> bool:
    with _LOCK:
        job = _JOBS.get(job_id)
        return bool(job and (job.get("stop") or job.get("state") == "stopped"))


def get_status(job_id: str) -> dict | None:
    with _LOCK:
        job = _JOBS.get(job_id)
    if job is None:
        job = _load(job_id)
        if job is None:
            return None
        with _LOCK:
            _JOBS[job_id] = job
    return _public(dict(job))


def get_book_job(slug: str) -> dict | None:
    """Kitabın çalışan, yoksa en son güncellenen toplu işini döndürür."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT id, slug, start_url, count, done, translated, state, message, "
            "next_url, updated_at FROM jobs WHERE slug = ? "
            "ORDER BY CASE WHEN state = 'running' THEN 0 ELSE 1 END, updated_at DESC "
            "LIMIT 1",
            (slug,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    job = _from_row(row)
    with _LOCK:
        memory = _JOBS.get(job["id"])
        if memory is not None:
            job = dict(memory)
        else:
            _JOBS[job["id"]] = job
    return _public(job)


def stop(job_id: str) -> bool:
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            job = _load(job_id)
            if job is None:
                return False
            _JOBS[job_id] = job
        if job["state"] != "running":
            return True
        job.update(
            stop=True,
            state="stopped",
            message=f"Durduruldu. {job['translated']} yeni bölüm çevrildi.",
            updated_at=time.time(),
        )
        _persist(dict(job))
    return True


def _prune() -> None:
    """Bitmiş eski işleri bellek ve SQLite'ta _MAX_JOBS sınırına indirir."""
    if len(_JOBS) > _MAX_JOBS:
        finished = sorted(
            (j for j in _JOBS.values() if j["state"] != "running"),
            key=lambda j: j.get("updated_at", 0),
        )
        for job in finished[: len(_JOBS) - _MAX_JOBS]:
            _JOBS.pop(job["id"], None)

    conn = _connect()
    try:
        stored = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        excess = max(stored - _MAX_JOBS, 0)
        if excess:
            conn.execute(
                "DELETE FROM jobs WHERE id IN ("
                "SELECT id FROM jobs WHERE state != 'running' ORDER BY updated_at LIMIT ?)",
                (excess,),
            )
            conn.commit()
    finally:
        conn.close()


def _thread_main(job_id: str, api_key: str | None) -> None:
    try:
        _run(job_id, api_key)
    finally:
        with _LOCK:
            current = _THREADS.get(job_id)
            if current is threading.current_thread():
                _THREADS.pop(job_id, None)


def _start_thread(job_id: str, api_key: str | None) -> bool:
    """Aynı iş için en fazla bir canlı worker başlatır."""
    with _LOCK:
        current = _THREADS.get(job_id)
        if current is not None and current.is_alive():
            return False
        thread = threading.Thread(
            target=_thread_main, args=(job_id, api_key), daemon=True
        )
        _THREADS[job_id] = thread
        thread.start()
    return True


def start_bulk(slug: str, start_url: str, count: int, api_key: str | None) -> str:
    """Arka plan toplu çeviri başlat; işi SQLite'a yazıp kimliğini döndür.

    Aynı kitap için zaten koşan bir iş varsa yenisi açılmaz: mevcut işin kimliği
    döner (worker ölmüşse checkpoint'ten yeniden başlatılır). Sınırsız paralel
    bulk worker hem Gemini kotasını yer hem okuyucuyu çekim kapısında bekletir.
    """
    existing = get_book_job(slug)
    if existing and existing["state"] == "running":
        _start_thread(existing["id"], api_key)  # canlıysa no-op, değilse sürdür
        return existing["id"]
    job_id = uuid.uuid4().hex
    job = {
        "id": job_id,
        "slug": slug,
        "start_url": start_url,
        "count": count,
        "done": 0,
        "translated": 0,
        "state": "running",
        "message": "Hazırlanıyor…",
        "next_url": start_url,
        "stop": False,
        "updated_at": time.time(),
    }
    with _LOCK:
        _JOBS[job_id] = job
    _persist(job)
    _prune()
    _start_thread(job_id, api_key)
    return job_id


def resume_running(api_key: str | None) -> list[str]:
    """SQLite'ta yarım kalmış işleri yükleyip checkpoint'lerinden sürdürür."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT id, slug, start_url, count, done, translated, state, message, "
            "next_url, updated_at FROM jobs WHERE state = 'running' ORDER BY updated_at"
        ).fetchall()
    finally:
        conn.close()
    started = []
    for row in rows:
        job = _from_row(row)
        with _LOCK:
            existing = _JOBS.get(job["id"])
            if existing is None or not existing.get("stop"):
                _JOBS[job["id"]] = job
        if _start_thread(job["id"], api_key):
            started.append(job["id"])
    return started


def _run(job_id: str, api_key: str | None) -> None:
    job = get_status(job_id)
    if job is None:
        return
    url = job.get("next_url") if job["done"] else job.get("start_url")
    total = job["total"]
    done = job["done"]
    translated = job["translated"]
    while done < total:
        if _should_stop(job_id):
            _set(
                job_id,
                state="stopped",
                message=f"Durduruldu. {translated} yeni bölüm çevrildi.",
                updated_at=time.time(),
            )
            return
        if not url:
            _set(
                job_id,
                state="done",
                message=f"Son bölüme ulaşıldı. {translated} yeni bölüm çevrildi.",
                updated_at=time.time(),
            )
            return
        _set(
            job_id,
            message=f"Bölüm {done + 1} / {total} hazırlanıyor…",
            updated_at=time.time(),
        )
        try:
            # background=True: çekim düşük öncelikli (okuyucu kapıda öne geçer)
            # ve kitabın "kaldığın yer" konumu ilerletilmez.
            data = pipeline.get_or_translate(url, api_key, background=True)
        except (FetchError, TranslateError) as exc:
            _set(
                job_id, state="error", message=f"Durdu: {exc}", done=done,
                translated=translated, updated_at=time.time(),
            )
            return
        except Exception as exc:  # beklenmedik; işi sızdırmadan bitir
            _set(
                job_id, state="error", message=f"Beklenmedik hata: {exc}",
                done=done, translated=translated, updated_at=time.time(),
            )
            return
        done += 1
        if not data.get("cached"):
            translated += 1
        url = data.get("next_url")
        _set(
            job_id,
            done=done,
            translated=translated,
            next_url=url,
            message=f"{done} / {total} bitti — {data.get('title', '')} "
                    f"({translated} yeni)",
            updated_at=time.time(),
        )
        if _should_stop(job_id):
            _set(
                job_id,
                state="stopped",
                message=f"Durduruldu. {translated} yeni bölüm çevrildi.",
                updated_at=time.time(),
            )
            return
        if not url:
            _set(
                job_id,
                state="done",
                message=f"Son bölüme ulaşıldı. {translated} yeni bölüm çevrildi.",
                updated_at=time.time(),
            )
            return
    _set(
        job_id,
        state="done",
        message=f"Bitti — {translated} yeni bölüm çevrildi.",
        updated_at=time.time(),
    )
