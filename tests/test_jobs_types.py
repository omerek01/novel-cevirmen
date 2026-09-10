"""jobs tip altyapısı (E-4/E-5/E-16/E-22) + bütçe sayaçları (E-12) + E-25."""
import sqlite3
import time
import uuid

import pytest

from core import budget, db, jobs


def _job(**kw):
    out = {
        "id": uuid.uuid4().hex, "slug": "s", "start_url": "u1", "count": 5,
        "done": 0, "translated": 0, "state": "running", "message": "m",
        "next_url": "u1", "type": "bulk", "params": None, "stop": False,
        "updated_at": time.time(),
    }
    out.update(kw)
    return out


def test_type_params_row_roundtrip():
    """E-4: type+params 5 pozisyonel noktadan bozulmadan geçer (persist→load)."""
    job = _job(type="pdf-import", params={"path": "a.pdf", "oran": 10})
    jobs._persist(job)
    loaded = jobs._load(job["id"])
    assert loaded["type"] == "pdf-import"
    assert loaded["params"] == {"path": "a.pdf", "oran": 10}


def test_legacy_row_defaults_to_bulk():
    """Eski satır (type NULL) bulk sayılır; params None."""
    job = _job()
    jobs._persist(job)
    conn = jobs._connect()
    conn.execute("UPDATE jobs SET type = NULL, params = NULL WHERE id = ?", (job["id"],))
    conn.commit()
    conn.close()
    loaded = jobs._load(job["id"])
    assert loaded["type"] == "bulk" and loaded["params"] is None


def test_resume_running_skips_broken_params():
    """E-4: bozuk params JSON'lu satır atlanır, startup çökmez."""
    job = _job()
    jobs._persist(job)
    conn = jobs._connect()
    conn.execute("UPDATE jobs SET params = '{bozuk' WHERE id = ?", (job["id"],))
    conn.commit()
    conn.close()
    assert jobs.resume_running(api_key=None) == []  # çökmedi, satır atlandı


def test_get_book_job_attention_priority_error_over_done():
    """E-5: bulk HATASI, daha yeni check-updates done'undan önce gelir."""
    err = _job(state="error", updated_at=time.time() - 100)
    done = _job(type="check-updates", state="done", updated_at=time.time())
    jobs._persist(err)
    jobs._persist(done)
    got = jobs.get_book_job("s")
    assert got["id"] == err["id"]  # hata rozeti sökülmez


def test_get_book_job_AYNI_TIPTE_yeni_basari_eski_hatayi_gizler():
    """E-5 tip-farkındaydı ama AYNI tip içinde TARİH yok sayılıyordu.

    Gerçek vaka (2026-09-10): shadow-slave'de bulk işi 09-09 23:20'de 2/15'te
    hataya düştü; kullanıcı 09-10 06:43'te yeniden çalıştırdı ve 10/10 bitti —
    ama rafta hâlâ "! HATA" rozeti duruyordu. Kullanıcı sorunu zaten çözmüşken
    rozetin kalması yanlış bilgi: raf "ilgilenmen gereken bir şey var" diyordu,
    oysa yoktu.

    Kural artık şu: her TİP kendi EN SON kaydıyla temsil edilir, öncelik ancak
    ondan sonra uygulanır. Böylece E-5 korunur (check-updates'in done'ı bulk
    hatasını sökmez) ama aynı tipte daha yeni bir başarı eskisini geçersiz kılar.
    """
    err = _job(state="error", updated_at=time.time() - 100)
    yeni = _job(state="done", updated_at=time.time())  # AYNI tip (bulk)
    jobs._persist(err)
    jobs._persist(yeni)
    got = jobs.get_book_job("s")
    assert got["id"] == yeni["id"]


def test_start_bulk_dedup_is_type_aware(monkeypatch):
    """E-22: koşan check-updates işi bulk dedup'unu TETİKLEMEZ."""
    monkeypatch.setattr(jobs, "_start_thread", lambda job_id, api_key: True)
    cu = _job(type="check-updates", state="running")
    jobs._persist(cu)
    new_id = jobs.start_bulk("s", "u1", 3, api_key=None)
    assert new_id != cu["id"]  # yeni bulk işi açıldı
    # Ama koşan BULK varken ikinci bulk açılmaz (mevcut davranış korunur).
    again = jobs.start_bulk("s", "u9", 3, api_key=None)
    assert again == new_id


def test_persist_preserves_unnamed_columns_e16():
    """E-16: _persist ON CONFLICT kullanır — elle eklenmiş sütun sıfırlanmaz."""
    job = _job()
    jobs._persist(job)
    conn = jobs._connect()
    conn.execute("ALTER TABLE jobs ADD COLUMN deneme TEXT")
    conn.execute("UPDATE jobs SET deneme = 'korunmalı' WHERE id = ?", (job["id"],))
    conn.commit()
    conn.close()
    job["done"] = 3
    jobs._persist(job)  # REPLACE olsaydı deneme NULL'a dönerdi
    conn = jobs._connect()
    val = conn.execute(
        "SELECT deneme FROM jobs WHERE id = ?", (job["id"],)
    ).fetchone()[0]
    conn.close()
    assert val == "korunmalı"


def test_budget_counters_roundtrip_and_day_isolation():
    """E-12: kalıcı günlük sayaç — artır/oku, günler birbirine karışmaz."""
    assert budget.get("2026-07-19", "auto_translate") == 0
    assert budget.increment("2026-07-19", "auto_translate") == 1
    assert budget.increment("2026-07-19", "auto_translate", 4) == 5
    assert budget.get("2026-07-19", "auto_translate") == 5
    assert budget.get("2026-07-20", "auto_translate") == 0  # yeni gün sıfırdan
    assert budget.DAILY_AUTO_TRANSLATE_BUDGET == 20


def test_ensure_column_raises_non_duplicate_errors():
    """E-25: yalnız 'duplicate column' yutulur; gerçek hatalar FIRLATILIR."""
    conn = db.connect()
    conn.execute("CREATE TABLE IF NOT EXISTS t25 (a TEXT)")
    db.ensure_column(conn, "t25", "a", "a TEXT")  # var olan sütun → sessiz no-op
    with pytest.raises(sqlite3.OperationalError):
        # PRIMARY KEY sütunu ALTER ile eklenemez — bu hata yutulmamalı.
        db.ensure_column(conn, "t25", "b", "b TEXT PRIMARY KEY")
    conn.close()
