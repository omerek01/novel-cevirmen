"""Karakter defteri okuyucudan AÇ/KAPA edilir (2026-10-23, kullanıcı isteği).

Gerekçe PARA: defter çeviriden ayrı bir model çağrısı yapıyor ve ölçülen fatura
onu en pahalı kalem yapıyor (canlı `defter_isleme`, 1117 bölüm: 13,26M giriş +
3,08M çıkış, 3.8 Flash fiyatıyla 21,49 $ — aynı dönemdeki Argon çevirisinin 11,7
katı). Önceden defter yalnız `KARAKTER_DEFTERI` ortam değişkeniyle yönetiliyordu;
kapatmak sunucuya girip servisi yeniden başlatmak demekti. "Para tasarrufu
istersem bunu aç kapat yapabileyim" (kullanıcı).

Öncelik `ceviri_asamalari` ile AYNI: kayıtlı ayar > ortam değişkeni > varsayılan
(kapalı). Düğmeye hiç dokunulmadıysa davranış bugünküyle birebir aynıdır.

İKİ kapı birden gerekiyor, yoksa düğme parayı KESMEZ:
  * `kuyruga_ekle` — yeni çevrilen bölüm kuyruğa girmesin.
  * işçi döngüsü — ZATEN kuyrukta bekleyen bölümler boşaltılmaya devam ediyordu.
    Canlıda 1101 bölümlük bir yeniden işleme kuyruğu vardı; sadece ilk kapıyı
    koymak "kapattım" diyen kullanıcıya yüzlerce çağrı daha fatura ederdi.
"""
import sqlite3

import pytest

from core import karakter_defteri as kd
from core import settings


def test_varsayilan_KAPALI(monkeypatch):
    monkeypatch.delenv("KARAKTER_DEFTERI", raising=False)
    assert kd.acik_mi() is False


def test_ortam_degiskeni_acar(monkeypatch):
    monkeypatch.setenv("KARAKTER_DEFTERI", "1")
    assert kd.acik_mi() is True


def test_ayar_ortam_degiskenini_EZER(monkeypatch):
    """Düğme kazanır: yoksa panelde "kapalı" yazarken defter para harcamaya devam ederdi."""
    monkeypatch.setenv("KARAKTER_DEFTERI", "1")
    kd.ayarla(False)
    assert kd.acik_mi() is False


def test_ayar_ortam_kapaliyken_de_acar(monkeypatch):
    monkeypatch.setenv("KARAKTER_DEFTERI", "0")
    kd.ayarla(True)
    assert kd.acik_mi() is True


def test_ayar_okunamazsa_ortama_duser(monkeypatch):
    """Kilitli veritabanı çeviriyi durdurmamalı — `ceviri_asamalari._kayit` deseni."""
    def patlat(*a, **k):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setenv("KARAKTER_DEFTERI", "1")
    monkeypatch.setattr(settings, "get", patlat)
    assert kd.acik_mi() is True


def test_durum_okuyucuya_kaynagi_da_soyler(monkeypatch):
    """Panel "ayar mı ortam değişkeni mi" ayrımını göstermeli: aynı ayrım
    `ceviri_asamalari.durum()`da var ve okur "neden açık" sorusunu oradan okuyor."""
    monkeypatch.setenv("KARAKTER_DEFTERI", "1")
    assert kd.ayar_durumu()["kaynak"] == "ortam"
    kd.ayarla(True)
    d = kd.ayar_durumu()
    assert d["kaynak"] == "ayar" and d["acik"] is True
    assert d["etiket"] and d["aciklama"]


# ---------- kapı 1: yeni bölüm kuyruğa girmez ----------

def test_kapaliyken_kuyruga_girmez(monkeypatch):
    monkeypatch.setenv("KARAKTER_DEFTERI", "1")
    kd.ayarla(False)
    assert kd.kuyruga_ekle("shadow-slave", 5) is False




# ---------- kapı 2: BEKLEYEN kuyruk da boşaltılmaz ----------

def _kuyruk_kur(book_slug="ss", bolumler=(1, 2, 3)):
    conn = kd._connect()
    try:
        for bolum in bolumler:
            conn.execute(
                "INSERT INTO defter_isleme (book_slug, bolum, durum, deneme, updated_at) "
                "VALUES (?, ?, 'pending', 0, 0)", (book_slug, bolum))
        conn.commit()
    finally:
        conn.close()


def _bekleyenler(book_slug="ss") -> list[int]:
    conn = kd._connect()
    try:
        return [r[0] for r in conn.execute(
            "SELECT bolum FROM defter_isleme WHERE book_slug = ? AND durum = 'pending' "
            "ORDER BY bolum", (book_slug,)).fetchall()]
    finally:
        conn.close()


def _sahte_isleyici(islenen, *, sonra=None):
    """`bolum_isle` yerine geçer. Satıra 'completed' YAZMAK ZORUNDA: gerçek
    `bolum_isle` bunu yapıyor ve `_siradaki` yalnız 'pending' satır arıyor. Yazmayan
    bir sahte işleyici aynı bölümü sonsuza dek döndürtüp işçi döngüsünü kilitler
    (bu test yazılırken yaşandı: iki pytest süreci dakikalarca CPU yaktı).

    `sonra`: bölüm işlendikten sonra koşan kanca — kullanıcının düğmeye tam o anda
    dokunmasını taklit eder."""
    def isle(book_slug, bolum, **k):
        islenen.append(bolum)
        conn = kd._connect()
        try:
            kd._isleme_yaz(conn, book_slug, bolum, "completed")
            conn.commit()
        finally:
            conn.close()
        if sonra:
            sonra()
        return {"bolum": bolum, "durum": "completed"}
    return isle


def _isci_kur(monkeypatch, islenen, *, sonra=None):
    monkeypatch.setattr(kd, "bolum_isle", _sahte_isleyici(islenen, sonra=sonra))
    monkeypatch.setattr(kd, "hitap_denetle", lambda *a, **k: None)
    monkeypatch.setattr(kd, "uzlastir", lambda *a, **k: None)
    monkeypatch.setattr(kd.budget, "etkilesimli_var", lambda: False)


def test_isci_kapatilinca_bekleyen_kuyrugu_BOSALTMAZ(monkeypatch):
    """Ayar kapatıldığında işçi sıradaki bölüme GEÇMEZ.

    Canlı vaka: 1101 bölümlük yeniden işleme kuyruğu koşarken kapatmak yalnız
    yeni bölümleri engelliyor, boşaltma sürüyordu — "kapattım" diyen kullanıcıya
    yüzlerce ücretli çağrı daha giderdi.
    """
    monkeypatch.setenv("KARAKTER_DEFTERI", "1")
    kd.ayarla(True)
    islenen = []
    # İlk bölüm işlendikten SONRA kullanıcı düğmeyi kapatıyor.
    _isci_kur(monkeypatch, islenen, sonra=lambda: kd.ayarla(False))
    _kuyruk_kur()

    kd._isle_simdi("ss")

    assert islenen == [1]
    # Kuyruk SİLİNMEZ, yalnız durur: düğme yeniden açılınca kaldığı yerden sürer.
    assert _bekleyenler() == [2, 3]


def test_isci_acikken_kuyrugu_bosaltir(monkeypatch):
    """Karşı test: kapı yalnız KAPALIYKEN durdurmalı, yoksa defter hiç koşmaz."""
    monkeypatch.setenv("KARAKTER_DEFTERI", "1")
    kd.ayarla(True)
    islenen = []
    _isci_kur(monkeypatch, islenen)
    _kuyruk_kur()

    kd._isle_simdi("ss")

    assert islenen == [1, 2, 3]
    assert _bekleyenler() == []


# ---------- uç ----------

def test_uc_okur_ve_yazar(monkeypatch):
    from fastapi.testclient import TestClient
    import server

    monkeypatch.setenv("KARAKTER_DEFTERI", "0")
    istemci = TestClient(server.app)
    assert istemci.get("/api/settings/defter").json()["acik"] is False
    assert istemci.post("/api/settings/defter", json={"acik": True}).json()["acik"] is True
    assert kd.acik_mi() is True
    assert istemci.post("/api/settings/defter", json={"acik": False}).json()["acik"] is False
    assert kd.acik_mi() is False
