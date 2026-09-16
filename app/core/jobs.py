"""Sunucu-taraflı, SQLite checkpoint'li arka plan toplu çeviri.

Tarayıcı sekmesi kapansa da iş sürer. Her bölümden sonra sıradaki URL aynı
chapters.db dosyasına yazılır; sunucu yeniden başladığında yarım kalan işler bu
checkpoint'ten otomatik devam eder.
"""
from __future__ import annotations

import json
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

# GEÇİCİ çeviri hatası toplu işi ÖLDÜRMEZ (2026-09-10).
# Gerçek vaka: 15 bölümlük iş ikinci bölümde "Tüm modeller şu anda meşgul
# (geçici)" ile durdu ve kullanıcı kalan 13 bölümü hiç alamadı; rafta yalnız
# "! HATA" rozeti kaldı. Hata gerçekten geçiciydi — Google'ın 503 gövdesi bile
# "Spikes in demand are usually temporary. Please try again later." diyor.
# Toplu çeviri arka planda koşar ve acelesi yoktur; bir dalgayı beklemek,
# bütün işi feda etmekten her zaman ucuzdur. Tekrar SONSUZ değil: gerçekten
# kapalı bir kapıya sonsuza dek vurulmaz, üçüncü denemede iş hataya düşer.
BULK_GECICI_DENEME = 3
BULK_GECICI_BEKLEME = (30.0, 90.0)  # denemeler arası bekleme, sırayla


def _bekle(job_id: str, saniye: float) -> bool:
    """Durdurmaya duyarlı bekleme. False dönerse kullanıcı işi durdurmuştur.

    Bekleme PARÇALI: tek bir uzun uyku olsaydı "DURDUR" düğmesi dakikalarca
    cevapsız kalırdı. Adım `time.sleep` sahtelense bile azalır (testler uyku
    yapmadan koşar), yani döngü her koşulda sonlanır.
    """
    kalan = saniye
    while kalan > 0:
        if _should_stop(job_id):
            return False
        adim = min(1.0, kalan)
        time.sleep(adim)
        kalan -= adim
    return not _should_stop(job_id)


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
            updated_at REAL,
            type TEXT DEFAULT 'bulk',
            params TEXT
        )
        """
    )
    # Eski kurulumlar için idempotent migration (E-4): iş tipi + tip-özgü meta.
    db.ensure_column(conn, "jobs", "type", "type TEXT DEFAULT 'bulk'")
    db.ensure_column(conn, "jobs", "params", "params TEXT")
    conn.commit()
    return conn


# SELECT sütun listesi — _from_row ile birebir aynı sırada (E-4 disiplini).
_COLS = (
    "id, slug, start_url, count, done, translated, state, message, "
    "next_url, updated_at, type, params"
)


def _public(job: dict) -> dict:
    """İç durdurma bayrağını gizleyip eski `total` API alanını korur."""
    out = {k: v for k, v in job.items() if k != "stop"}
    out["total"] = out.get("count", 0)
    return out


def _from_row(row) -> dict:
    """Satır → iş sözlüğü. Bozuk params JSON'u ValueError fırlatır (E-4:
    resume_running o satırı atlar; startup çökmez)."""
    raw_params = row[11]
    try:
        params = json.loads(raw_params) if raw_params else None
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Bozuk iş params JSON'u: {exc}")
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
        "type": row[10] or "bulk",  # eski satırlar (NULL) bulk'tır
        "params": params,
        "stop": False,
    }


def _persist(job: dict) -> None:
    conn = _connect()
    try:
        # E-16: INSERT OR REPLACE değil — REPLACE, ileride eklenecek adlandırıl-
        # mamış sütunları her yazımda sessizce sıfırlar. ON CONFLICT yalnız
        # burada sahiplenilen sütunları günceller.
        conn.execute(
            """
            INSERT INTO jobs
                (id, slug, start_url, count, done, translated, state, message,
                 next_url, updated_at, type, params)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                slug = excluded.slug, start_url = excluded.start_url,
                count = excluded.count, done = excluded.done,
                translated = excluded.translated, state = excluded.state,
                message = excluded.message, next_url = excluded.next_url,
                updated_at = excluded.updated_at, type = excluded.type,
                params = excluded.params
            """,
            (
                job["id"], job["slug"], job["start_url"], job["count"],
                job["done"], job["translated"], job["state"], job["message"],
                job.get("next_url"), job["updated_at"], job.get("type", "bulk"),
                json.dumps(job["params"], ensure_ascii=False)
                if job.get("params") is not None else None,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _load(job_id: str) -> dict | None:
    conn = _connect()
    try:
        row = conn.execute(
            f"SELECT {_COLS} FROM jobs WHERE id = ?", (job_id,)
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


def get_book_job(slug: str, job_type: str | None = None) -> dict | None:
    """Kitabın dikkat gerektiren işini döndürür (rozet bu sırayla seçer).

    Kural İKİ AŞAMALI: önce her TİP kendi EN SON kaydıyla temsil edilir, sonra
    tipler arasında dikkat önceliği uygulanır (çalışan iş > hata > gerisi).

    E-5: tip-farkındalık böylece korunur — gece check-updates işinin 'done'
    kaydı, yarım bulk HATASININ rozetini sökmez.

    İlk aşama 2026-09-10'da eklendi. Öncelik doğrudan uygulanınca AYNI tip
    içinde TARİH yok sayılıyordu: shadow-slave'de bulk 09-09 23:20'de 2/15'te
    hataya düştü, kullanıcı 09-10 06:43'te yeniden çalıştırdı ve 10/10 bitti,
    ama raf hâlâ "! HATA" gösteriyordu. Rozet "ilgilenmen gereken bir şey var"
    demek; kullanıcı sorunu çözmüşken orada durması yanlış bilgiydi.

    job_type verilirse yalnız o tip (E-22 dedup anahtarı (slug, type) bunu
    kullanır)."""
    conn = _connect()
    try:
        where = "slug = ?"
        args: list = [slug]
        if job_type is not None:
            where += " AND COALESCE(type, 'bulk') = ?"
            args.append(job_type)
        row = conn.execute(
            f"SELECT {_COLS} FROM jobs WHERE {where} "
            # 1. aşama: her tipin yalnız EN SON kaydı yarışa girer.
            "AND updated_at = (SELECT MAX(j2.updated_at) FROM jobs j2 "
            "  WHERE j2.slug = jobs.slug "
            "    AND COALESCE(j2.type, 'bulk') = COALESCE(jobs.type, 'bulk')) "
            # 2. aşama: kalanlar arasında dikkat önceliği.
            "ORDER BY CASE state WHEN 'running' THEN 0 WHEN 'error' THEN 1 ELSE 2 END, "
            "updated_at DESC LIMIT 1",
            args,
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


def start_bulk(
    slug: str, start_url: str, count: int, api_key: str | None,
    job_type: str = "bulk",
) -> str:
    """Arka plan toplu çeviri başlat; işi SQLite'a yazıp kimliğini döndür.

    Aynı kitap için zaten koşan bir iş varsa yenisi açılmaz: mevcut işin kimliği
    döner (worker ölmüşse checkpoint'ten yeniden başlatılır). Sınırsız paralel
    bulk worker hem Gemini kotasını yer hem okuyucuyu çekim kapısında bekletir.
    """
    # Kontrol+oluşturma tek _LOCK altında (RLock, iç çağrılar yeniden alabilir):
    # iki eşzamanlı istek (çift dokunuş / iki cihaz) ikisi de "koşan iş yok" görüp
    # aynı kitaba iki worker açmasın. FastAPI istekleri paralel thread'lerde koşar.
    with _LOCK:
        # E-22: tekilleştirme anahtarı (slug, type) — başka tipte bir iş
        # (örn. check-updates) bulk dedup'unu tetiklemez.
        existing = get_book_job(slug, job_type=job_type)
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
            "type": job_type,
            "params": None,
            "stop": False,
            "updated_at": time.time(),
        }
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
            f"SELECT {_COLS} FROM jobs WHERE state = 'running' ORDER BY updated_at"
        ).fetchall()
    finally:
        conn.close()
    started = []
    for row in rows:
        try:
            job = _from_row(row)
        except ValueError:
            continue  # E-4: bozuk params JSON'lu satır atlanır, startup sürer
        with _LOCK:
            existing = _JOBS.get(job["id"])
            if existing is None or not existing.get("stop"):
                _JOBS[job["id"]] = job
        if _start_thread(job["id"], api_key):
            started.append(job["id"])
    return started


def _run(job_id: str, api_key: str | None) -> None:
    """İş türüne göre yönlendirir (Yaklaşım B temeli). Bilinmeyen tip → error."""
    job = get_status(job_id)
    if job is None:
        return
    runner = _RUNNERS.get(job.get("type", "bulk"))
    if runner is None:
        _set(
            job_id, state="error",
            message=f"Bilinmeyen iş tipi: {job.get('type')!r}",
            updated_at=time.time(),
        )
        return
    runner(job_id, api_key)


def _run_bulk(job_id: str, api_key: str | None) -> None:
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
        # ÇEVİRİ hatası geçici olabilir (model yükü) → bekleyip aynı bölümü
        # yeniden dene. ÇEKİM hatası ayrı tutulur: `fetch` kendi üstel
        # geri-çekilmesini zaten yapıyor, buradan ikinci bir tekrar katmanı
        # eklemek Cloudflare'e üst üste inmek olurdu.
        data = None
        deneme = 0
        while data is None:
            try:
                # background=True: çekim düşük öncelikli (okuyucu kapıda öne
                # geçer) ve kitabın "kaldığın yer" konumu ilerletilmez.
                data = pipeline.get_or_translate(url, api_key, background=True)
            except TranslateError as exc:
                deneme += 1
                if deneme >= BULK_GECICI_DENEME:
                    _set(
                        job_id, state="error", message=f"Durdu: {exc}", done=done,
                        translated=translated, updated_at=time.time(),
                    )
                    return
                bekleme = BULK_GECICI_BEKLEME[
                    min(deneme - 1, len(BULK_GECICI_BEKLEME) - 1)
                ]
                _set(
                    job_id,
                    message=(
                        f"Modeller meşgul; {int(bekleme)} sn sonra yeniden "
                        f"denenecek ({deneme}/{BULK_GECICI_DENEME})…"
                    ),
                    done=done, translated=translated, updated_at=time.time(),
                )
                if not _bekle(job_id, bekleme):
                    _set(
                        job_id, state="stopped",
                        message=f"Durduruldu. {translated} yeni bölüm çevrildi.",
                        done=done, translated=translated, updated_at=time.time(),
                    )
                    return
            except FetchError as exc:
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


def start_retranslate(slug: str, urls: list[str], api_key: str | None) -> str:
    """Seçili bölümleri yeniden çeviren arka plan işi başlat; kimliğini döndür.

    Sözlük düzeltmesinin eski bölümlere yansıması için (belge: "yalnız seçtiği
    bölümler çevrilir"). Zincir İZLENMEZ: yalnız verilen URL'ler çevrilir. Aynı
    kitapta koşan bir yeniden çeviri işi varsa yenisi açılmaz, onun kimliği döner
    — iki iş aynı bölümü iki kez çevirip kotayı ikiye katlardı.
    """
    with _LOCK:
        existing = get_book_job(slug, job_type="retranslate")
        if existing and existing["state"] == "running":
            _start_thread(existing["id"], api_key)
            return existing["id"]
        job_id = uuid.uuid4().hex
        job = {
            "id": job_id,
            "slug": slug,
            "start_url": urls[0] if urls else None,
            "count": len(urls),
            "done": 0,
            "translated": 0,
            "state": "running",
            "message": "Hazırlanıyor…",
            "next_url": None,
            "type": "retranslate",
            "params": {"urls": list(urls), "sonuclar": {}},
            "stop": False,
            "updated_at": time.time(),
        }
        _JOBS[job_id] = job
        _persist(job)
        _prune()
        _start_thread(job_id, api_key)
    return job_id


def _run_retranslate(job_id: str, api_key: str | None) -> None:
    """Verilen bölümleri `refresh=True` ile sırayla yeniden çevir.

    Her bölümün SONUCU kaydedilir (hizalama tuttu mu, kaç sözlük ihlali, kaç
    İngilizce kalıntı, hangi model): belge "yeniden üretimde hizalama ve sözlük
    uyumu denetlenmeli" diyor ve kullanıcı bunu işin sonunda görmeli. Tek bir
    bölümün kalıcı hatası işi DURDURMAZ, o bölüme yazılır; geçici çeviri hatası
    toplu çeviriyle aynı kuralla bekletilip yeniden denenir.
    """
    job = get_status(job_id)
    if job is None:
        return
    params = dict(job.get("params") or {})
    urls = list(params.get("urls") or [])
    sonuclar = dict(params.get("sonuclar") or {})
    done = job["done"]
    translated = job["translated"]

    def durdu() -> None:
        _set(
            job_id, state="stopped", done=done, translated=translated,
            params={**params, "sonuclar": sonuclar},
            message=f"Durduruldu. {translated} bölüm yeniden çevrildi.",
            updated_at=time.time(),
        )

    while done < len(urls):
        if _should_stop(job_id):
            durdu()
            return
        url = urls[done]
        _set(
            job_id, message=f"Bölüm {done + 1} / {len(urls)} yeniden çevriliyor…",
            updated_at=time.time(),
        )
        deneme = 0
        while True:
            try:
                data = pipeline.get_or_translate(url, api_key, refresh=True, background=True)
            except TranslateError as exc:
                deneme += 1
                if deneme >= BULK_GECICI_DENEME:
                    sonuclar[url] = {"durum": "hata", "mesaj": str(exc)}
                    break
                bekleme = BULK_GECICI_BEKLEME[min(deneme - 1, len(BULK_GECICI_BEKLEME) - 1)]
                _set(
                    job_id,
                    message=(
                        f"Modeller meşgul; {int(bekleme)} sn sonra yeniden "
                        f"denenecek ({deneme}/{BULK_GECICI_DENEME})…"
                    ),
                    updated_at=time.time(),
                )
                if not _bekle(job_id, bekleme):
                    durdu()
                    return
                continue
            except Exception as exc:  # çekim hatası dahil: bu bölüme yaz, işe devam
                sonuclar[url] = {"durum": "hata", "mesaj": str(exc)}
                break
            sonuclar[url] = {
                "durum": "tamam",
                "hizali": bool(data.get("source")),
                "ihlal": len(data.get("glossary_leaks") or {}),
                "kalinti": len(data.get("ingilizce_kalinti") or {}),
                "model": data.get("model"),
            }
            translated += 1
            break
        done += 1
        _set(
            job_id, done=done, translated=translated,
            params={**params, "sonuclar": sonuclar},
            message=f"{done} / {len(urls)} bitti ({translated} yeniden çevrildi)",
            updated_at=time.time(),
        )
    hatali = sum(1 for s in sonuclar.values() if s.get("durum") == "hata")
    _set(
        job_id, state="done",
        message=f"Bitti — {translated} bölüm yeniden çevrildi" + (f", {hatali} hata." if hatali else "."),
        updated_at=time.time(),
    )


# Tip -> koşucu kayıt tablosu. Yeni iş tipleri (epub-import, check-updates, ...)
# buraya eklenir; checkpoint/rozet/arka-plana-al davranışını miras alır.
# paste-import da zincir gezicisidir: sahneli sentetik bölümler pipeline'ın
# content yolundan (raw_source) çevrilir — _run_bulk aynen çalışır (DRY).
_RUNNERS = {"bulk": _run_bulk, "paste-import": _run_bulk, "retranslate": _run_retranslate}
