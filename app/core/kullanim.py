"""Ücretli model kullanımı: TOKEN sayar, maliyeti TÜRETİR.

Neden maliyet DEĞİL token saklanıyor: fiyat sağlayıcının elinde ve zamanla değişir.
Doları kaydetseydik, fiyat değiştiği gün geçmiş kayıtlar sessizce yanlışa dönerdi ve
"bu ay ne harcadım" sorusunun cevabı iki farklı fiyatın karışımı olurdu. Token bir
OLGUDUR; fiyat bir yorumdur ve `FIYAT` tablosundan bugünkü hâliyle uygulanır.

Bu depo yalnız GÖSTERGE içindir — harcamayı durduran bir fren değil (kullanıcı
kararı 2026-09-02). Model okuyucudan elle seçiliyor ve ücretli halkaya sessizce
düşülmüyor, yani sürpriz harcamanın kaynağı zaten kapalı.
"""
from __future__ import annotations

import sqlite3
from datetime import date

from . import db

# $/1M token (Anthropic ilan fiyatları, 2026-09-02). Ölçüm: bu projenin ortalama
# bölümü ~8.284 giriş + ~4.952 çıkış token — yani maliyetin ~%75'i ÇIKIŞTAN gelir.
FIYAT = {
    "claude-haiku-4-5": {"giris": 1.00, "cikis": 5.00},
    "claude-sonnet-5": {"giris": 2.00, "cikis": 10.00},
}


def _connect() -> sqlite3.Connection:
    conn = db.connect()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS kullanim (
            day TEXT NOT NULL,
            model TEXT NOT NULL,
            istek INTEGER NOT NULL DEFAULT 0,
            giris_token INTEGER NOT NULL DEFAULT 0,
            cikis_token INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (day, model)
        )
        """
    )
    return conn


def ekle(model: str, giris: int, cikis: int, gun: str | None = None) -> None:
    """Bir isteğin token kullanımını gün+model kırılımında biriktir.

    Sessizce başarısız OLUR (`sqlite3.Error` yutulur): bu bir göstergedir, çeviri
    yolunun kritik parçası değil. Sayaç yazılamadığı için bölümün çevirisini
    kaybetmek, ölçmeye çalıştığımız şeyden çok daha pahalıya mal olurdu.
    """
    try:
        conn = _connect()
    except sqlite3.Error:
        return
    try:
        conn.execute(
            "INSERT INTO kullanim (day, model, istek, giris_token, cikis_token) "
            "VALUES (?, ?, 1, ?, ?) "
            "ON CONFLICT(day, model) DO UPDATE SET "
            "  istek = istek + 1,"
            "  giris_token = giris_token + excluded.giris_token,"
            "  cikis_token = cikis_token + excluded.cikis_token",
            (gun or date.today().isoformat(), model, int(giris), int(cikis)),
        )
        conn.commit()
    except sqlite3.Error:
        pass
    finally:
        conn.close()


def _maliyet(model: str, giris: int, cikis: int) -> float:
    f = FIYAT.get(model)
    if not f:
        return 0.0  # fiyatı bilinmeyen model (ücretsiz Gemini halkaları) 0 sayılır
    return giris * f["giris"] / 1e6 + cikis * f["cikis"] / 1e6


def ozet(ay: str | None = None) -> dict:
    """Bir AYIN ücretli kullanım özeti: {ay, istek, maliyet, modeller[]}.

    Ay penceresi seçildi çünkü fatura aylık okunuyor; günlük sayı tek başına
    "bu gidişle ne olur" sorusunu cevaplamıyor.
    """
    ay = ay or date.today().isoformat()[:7]
    try:
        conn = _connect()
    except sqlite3.Error:
        return {"ay": ay, "istek": 0, "maliyet": 0.0, "modeller": []}
    try:
        satirlar = conn.execute(
            "SELECT model, SUM(istek) i, SUM(giris_token) g, SUM(cikis_token) c "
            "FROM kullanim WHERE day LIKE ? GROUP BY model ORDER BY model",
            (f"{ay}-%",),
        ).fetchall()
    except sqlite3.Error:
        return {"ay": ay, "istek": 0, "maliyet": 0.0, "modeller": []}
    finally:
        conn.close()

    modeller = []
    for model, istek, giris, cikis in satirlar:
        # Fiyatı bilinmeyen (ücretsiz) modeller göstergeye girmez: "0,00 $ harcadın"
        # satırları asıl bilgiyi gürültüye boğardı.
        if model not in FIYAT:
            continue
        modeller.append(
            {
                "model": model,
                "istek": int(istek or 0),
                "giris_token": int(giris or 0),
                "cikis_token": int(cikis or 0),
                "maliyet": round(_maliyet(model, giris or 0, cikis or 0), 4),
            }
        )
    return {
        "ay": ay,
        "istek": sum(m["istek"] for m in modeller),
        "maliyet": round(sum(m["maliyet"] for m in modeller), 4),
        "modeller": modeller,
    }
