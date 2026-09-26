"""API durum panelinin salt-okunur uçları ve "neden bu model?" kararı.

Planın tamamlanma ölçütü: paneli açmak ya da yenilemek Gemini kotası
TÜKETMEZ, beş anahtarın son gözlemleri birbirinden ayrılır ve "3.6 seçiliyken
neden 3.5?" sorusu ya tarihli bir geçişle ya da "önceden kaydedildi"
açıklamasıyla cevaplanır.
"""
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import server
from core import api_durum, cache, settings, translate

TERCIH, YEDEK = "gemini-3.6-flash", "gemini-3.5-flash"
A1, A2 = "test-anahtar-bir-1111", "test-anahtar-iki-2222"
K1, K2 = api_durum.anahtar_kimligi(A1), api_durum.anahtar_kimligi(A2)
URL = "https://freewebnovel.com/novel/deneme/chapter-595"


@pytest.fixture(autouse=True)
def _ortam(monkeypatch):
    for ad in translate.anahtar_degiskenleri():
        monkeypatch.delenv(ad, raising=False)
    monkeypatch.setattr(server, "API_KEY", A1)
    monkeypatch.setenv("GEMINI2_API_KEY", A2)
    translate.anahtar_sogumalarini_temizle()
    translate.anahtar_rotasyonunu_sifirla()
    yield
    translate.anahtar_sogumalarini_temizle()
    translate.anahtar_rotasyonunu_sifirla()


def _istemci():
    return TestClient(server.app)


def _bolum_kaydet(url=URL, model=YEDEK, baslik="Bölüm 595"):
    cache.save_chapter(url, {
        "book_slug": "deneme", "book_title": "Deneme", "title": baslik,
        "chapter_no": 595, "translation": "metin", "next_url": None, "prev_url": None,
        "detected_names": [], "chunk_count": 1, "engine": "gemini", "model": model,
    })


# ---------------------------------------------------------------- kota tüketmez

def test_panel_istekleri_saglayiciya_GITMEZ_rotasyonu_ilerletmez(monkeypatch):
    def yasak(*a, **k):
        raise AssertionError("panel sağlayıcıya istek attı")

    monkeypatch.setattr(translate.genai, "Client", yasak)
    monkeypatch.setattr(translate, "_tek_anahtarla_uret", yasak)
    monkeypatch.setattr(translate, "_claude_uret", yasak)
    _bolum_kaydet()
    once = translate._ROTASYON
    c = _istemci()
    for yol in ("/api/settings/api-status", "/api/settings/api-events",
                f"/api/settings/api-neden?url={URL}"):
        res = c.get(yol)
        assert res.status_code == 200, yol
        assert res.headers["cache-control"] == "no-store"
    assert translate._ROTASYON == once


def test_yanitlar_anahtar_degeri_ya_da_kimligi_SIZDIRMAZ():
    api_durum.istek_kaydet(K1, 1, TERCIH, api_durum.BASARI, 200)
    with api_durum.islem("okuma", URL):
        api_durum.istek_kaydet(K2, 2, TERCIH, api_durum.KOTA_GUNLUK, 429, soguma_sn=600)
    c = _istemci()
    govde = (c.get("/api/settings/api-status").text
             + c.get("/api/settings/api-events?tur=hepsi").text)
    for gizli in (A1, A2, K1, K2):
        assert gizli not in govde


# ---------------------------------------------------------------- kartlar

def test_bos_kayitta_her_anahtar_henuz_gozlenmedi():
    veri = _istemci().get("/api/settings/api-status").json()
    assert [k["etiket"] for k in veri["anahtarlar"]] == ["Anahtar 1", "Anahtar 2"]
    assert veri["tercih"] == TERCIH and veri["zincir"][0] == TERCIH
    assert veri["rotasyon"] == "Her istekte sonraki anahtar"
    for kart in veri["anahtarlar"]:
        assert {m["durum"] for m in kart["modeller"]} == {"gozlenmedi"}
    assert veri["sogumada"] == 0 and veri["kayit_baslangici"]


def test_anahtarlarin_son_gozlemleri_BIRBIRINDEN_ayrilir_ve_soguma_geri_yuklenir():
    api_durum.istek_kaydet(K1, 1, TERCIH, api_durum.BASARI, 200, giris=10, cikis=5)
    api_durum.istek_kaydet(K2, 2, TERCIH, api_durum.KOTA_GUNLUK, 429,
                           kota={"tur": "gunluk", "sinir": 20}, soguma_sn=3600)
    translate.anahtar_sogumalarini_temizle()  # sunucu yeniden başladı
    veri = _istemci().get("/api/settings/api-status").json()
    k1, k2 = ([m for m in k["modeller"] if m["model"] == TERCIH][0]
              for k in veri["anahtarlar"])
    assert (k1["durum"], k1["bugun"]["deneme"], k1["soguma_bitis"]) == ("basarili", 1, None)
    assert k2["durum"] == "kota_gunluk" and k2["etiket"] == "Günlük kota"
    assert k2["kota_sinir"] == 20 and k2["soguma_bitis"] > time.time() + 3000
    assert veri["sogumada"] == 1
    # Panel ile çeviri yolu AYNI kaynağa bakar: geri yüklenen soğuma çeviride de geçerli.
    assert translate._sogumada(1, TERCIH)


def test_soguma_bitince_yeniden_denenebilir_basarili_SAYILMAZ(monkeypatch):
    api_durum.istek_kaydet(K2, 2, TERCIH, api_durum.KOTA_DAKIKALIK, 429, soguma_sn=60)
    translate.anahtar_sogumalarini_temizle()
    gelecek = time.time() + 600
    monkeypatch.setattr(time, "time", lambda: gelecek)
    veri = _istemci().get("/api/settings/api-status").json()
    k2 = [m for m in veri["anahtarlar"][1]["modeller"] if m["model"] == TERCIH][0]
    assert k2["durum"] == "yeniden_denenebilir" and k2["etiket"] == "Yeniden denenebilir"
    assert veri["sogumada"] == 0


def test_claude_seciliyken_gemini_havuzu_kullanilmadigi_soylenir():
    settings.set(translate.MODEL_AYAR_ANAHTARI, "claude-haiku-4-5")
    veri = _istemci().get("/api/settings/api-status").json()
    assert veri["claude_secili"] is True
    assert tuple(veri["zincir"]) == tuple(
        m for m in translate.DEFAULT_MODELS if translate.gemini_modeli(m)
    )


@pytest.mark.parametrize("son, bitis, beklenen", [
    (None, None, "gozlenmedi"),
    ({"sonuc": "basari"}, None, "basarili"),
    ({"sonuc": "kota_gunluk"}, 2000.0, "kota_gunluk"),
    ({"sonuc": "kota_gunluk"}, 500.0, "yeniden_denenebilir"),
    ({"sonuc": "kota_belirsiz"}, 2000.0, "kota_belirsiz"),
    ({"sonuc": "baglanti"}, None, "gecici"),
    ({"sonuc": "erisim"}, None, "erisim"),
    ({"sonuc": "anahtar"}, None, "anahtar"),
    ({"sonuc": "bos"}, None, "bos"),
])
def test_kart_durumu_tablosu(son, bitis, beklenen):
    assert api_durum.kart_durumu(son, bitis, 1000.0) == beklenen
    etiket, ton = api_durum.DURUM[beklenen]
    assert etiket and ton  # her durumun METNİ var: yalnız renkle anlatılmaz


# ---------------------------------------------------------------- olaylar

def _gecis(url, hedef=YEDEK):
    with api_durum.islem("prefetch", url):
        with api_durum.cagri() as d:
            api_durum.istek_kaydet(K1, 1, TERCIH, api_durum.KOTA_GUNLUK, 429)
            api_durum.istek_kaydet(K2, 2, TERCIH, api_durum.GECICI, 503)
            api_durum.gecis_kaydet(TERCIH, hedef, list(d))


def test_gecis_listesi_bolum_basligi_neden_ve_denenen_anahtarlari_tasir():
    _bolum_kaydet()
    _gecis(URL)
    [o] = _istemci().get("/api/settings/api-events").json()["olaylar"]
    assert (o["tur"], o["model"], o["hedef"]) == ("gecis", TERCIH, YEDEK)
    assert o["amac_etiketi"] == "ön yükleme"
    assert o["bolum"]["baslik"] == "Bölüm 595" and o["bolum"]["no"] == 595
    assert "1 anahtarda günlük kota" in o["ozet"] and o["denenen"] == [1, 2]


def test_olaylar_sayfalanir():
    for i in range(5):
        _gecis(f"{URL}-{i}")
    c = _istemci()
    ilk = c.get("/api/settings/api-events?limit=2").json()
    assert len(ilk["olaylar"]) == 2 and ilk["sonraki"]
    ikinci = c.get(f"/api/settings/api-events?limit=2&cursor={ilk['sonraki']}").json()
    ucuncu = c.get(f"/api/settings/api-events?limit=2&cursor={ikinci['sonraki']}").json()
    assert len(ucuncu["olaylar"]) == 1 and ucuncu["sonraki"] is None
    kimlikler = [o["id"] for s in (ilk, ikinci, ucuncu) for o in s["olaylar"]]
    assert kimlikler == sorted(kimlikler, reverse=True) and len(set(kimlikler)) == 5


def test_cikarilmis_anahtar_yeni_anahtara_yazilmaz():
    api_durum.istek_kaydet(api_durum.anahtar_kimligi("silinen"), 3, TERCIH,
                           api_durum.ANAHTAR, 403)
    [o] = _istemci().get("/api/settings/api-events?tur=istek").json()["olaylar"]
    assert o["anahtar"] == "Çıkarılmış anahtar"


def test_bilinmeyen_olay_turu_reddedilir():
    assert _istemci().get("/api/settings/api-events?tur=uydurma").status_code == 400


# ---------------------------------------------------------------- neden bu model?

def test_neden_gecis_kaydi_varsa_nedeni_soyler():
    _gecis(URL)
    _bolum_kaydet()  # bölüm satırı çeviri BİTİNCE yazılır (geçişten sonra)
    veri = _istemci().get(f"/api/settings/api-neden?url={URL}").json()
    assert veri["durum"] == "gecis"
    assert "günlük kota" in veri["nedenler"][0]


def test_neden_tercihle_cevrildiyse_soylenecek_bir_sey_yok():
    _bolum_kaydet(model=TERCIH)
    assert _istemci().get(f"/api/settings/api-neden?url={URL}").json()["durum"] == "tercih"


def test_neden_kayit_oncesi_bolumde_GECMIS_KAYDEDILMEMIS_der():
    bolum = {"model": YEDEK, "ceviri_zamani": 1000.0}
    veri = api_durum.model_nedeni(bolum, TERCIH, [], baslangic=5000.0)
    assert veri["durum"] == "kayitsiz"
    assert "Geçmiş neden kaydedilmemiş" in veri["aciklama"]
    assert "daha önce" in veri["aciklama"] and "3.5-flash" in veri["aciklama"]


def test_neden_kayittan_sonra_gecissiz_bolum_onceki_secimdir():
    bolum = {"model": YEDEK, "ceviri_zamani": 9000.0}
    veri = api_durum.model_nedeni(bolum, TERCIH, [], baslangic=5000.0)
    assert veri["durum"] == "onceki_secim"
    assert "o sırada tercih edilen model buydu" in veri["aciklama"]


def test_neden_ESKI_ceviriye_ait_gecis_yeni_ceviriye_yazilmaz():
    """Bölüm sonradan yeniden çevrildiyse eski geçiş onun nedeni değildir."""
    bolum = {"model": YEDEK, "ceviri_zamani": 100_000.0}
    eski = {"tur": "gecis", "zaman": 100_000.0 - api_durum.NEDEN_PENCERESI_SN - 10,
            "ozet": "eski"}
    veri = api_durum.model_nedeni(bolum, TERCIH, [eski], baslangic=1.0)
    assert veri["durum"] == "onceki_secim"


def test_neden_onbellekte_olmayan_bolum():
    assert _istemci().get(f"/api/settings/api-neden?url={URL}-yok").json()["durum"] == "yok"


# ---------------------------------------------------------------- service worker

def test_service_worker_panel_yanitlarini_ONBELLEGE_ALMAZ():
    """Canlı durum çevrimdışı önbellekten gelirse bayat "başarılı" gösterilirdi.
    Kural `/api/` genel dalından ÖNCE durmalı, yoksa hiç çalışmaz."""
    sw = (Path(server.__file__).parent / "web" / "sw.js").read_text(encoding="utf-8")
    atla = sw.index('"/api/settings/api-"')
    genel = sw.index('url.pathname.startsWith("/api/")')
    assert atla < genel
