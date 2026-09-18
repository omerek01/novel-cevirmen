"""API gözlem kaydı (`core.api_durum`) ve çeviri yoluna bağlanışı.

Kayıt 2026-09-18'de eklendi: "3.6 seçiliyken neden 3.5?" sorusu tahminle
cevaplanıyordu, çünkü zincirin neden aşağı indiği hiçbir yerde tutulmuyordu.
Bu dosya üç şeyi tutar:
  * sayaçların ANLAMI — gerçek istek sayılır, soğuma atlaması sayılmaz;
  * geçiş NEDENİ — anahtar başına son sonuç, başarılı ilk halkada sahte geçiş yok;
  * kaydın çeviriye ZARAR VERMEMESİ — yazılamazsa çeviri sürer, anahtar sızmaz.
"""
import sqlite3
import threading
import time
from datetime import datetime, timezone

import pytest

from core import api_durum, db, translate

TERCIH, YEDEK = "gemini-3.6-flash", "gemini-3.5-flash"


# ---------------------------------------------------------------- sahteler

class _SahteModeller:
    def __init__(self, sonuclar, engel=None):
        self._sonuclar = list(sonuclar)
        self.cagrilar = []
        self._engel = engel

    def generate_content(self, **kw):
        if self._engel is not None:
            self._engel()
        self.cagrilar.append(kw.get("model"))
        sonuc = self._sonuclar.pop(0) if self._sonuclar else '{"translation": "ok"}'
        if isinstance(sonuc, Exception):
            raise sonuc
        if isinstance(sonuc, tuple):  # (metin, usage_metadata)
            return type("Y", (), {"text": sonuc[0], "usage_metadata": sonuc[1]})()
        return type("Y", (), {"text": sonuc})()


class _SahteClient:
    def __init__(self, sonuclar=(), engel=None):
        self.models = _SahteModeller(sonuclar, engel)


class _APIHatasi(Exception):
    def __init__(self, code, details=None, mesaj=None):
        super().__init__(mesaj or f"HTTP {code}")
        self.code = code
        if details is not None:
            self.details = details


def _kota(tur):
    """tur: "gunluk" | "dakikalik" | None (quotaId'siz, türü belirsiz)."""
    ihlal = {"quotaValue": "20"}
    if tur == "gunluk":
        ihlal["quotaId"] = "GenerateRequestsPerDayPerProjectPerModel-FreeTier"
    elif tur == "dakikalik":
        ihlal["quotaId"] = "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"
    detaylar = [{"@type": "type.googleapis.com/google.rpc.QuotaFailure",
                 "violations": [ihlal]},
                {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "37s"}]
    return _APIHatasi(429, {"error": {"code": 429, "details": detaylar}})


def _fabrika(*istemciler):
    def fabrika(indeks=0):
        if indeks >= len(istemciler):
            raise translate.TranslateError(translate.ANAHTAR_YOK_MESAJI)
        return istemciler[indeks]

    fabrika.anahtar_sayisi = len(istemciler)
    return fabrika


@pytest.fixture(autouse=True)
def _temiz(monkeypatch):
    for ad in translate.anahtar_degiskenleri():
        monkeypatch.delenv(ad, raising=False)
    translate.anahtar_sogumalarini_temizle()
    translate.anahtar_rotasyonunu_sifirla()
    api_durum.sifirla_temizlik_zamani()
    monkeypatch.setattr(translate.time, "sleep", lambda s: None)
    monkeypatch.setattr(translate.genai_errors, "APIError", _APIHatasi)
    monkeypatch.setattr(translate, "pasifik_gece_yarisina_kalan", lambda: 3600.0)
    yield
    translate.anahtar_sogumalarini_temizle()
    translate.anahtar_rotasyonunu_sifirla()


def _olaylar(tur=None):
    return api_durum.son_olaylar(500, turler=(tur,) if tur else None)


def _gecisler():
    return _olaylar("gecis") + _olaylar("tukendi")


# ---------------------------------------------------------------- sayaçlar

def test_basarili_ilk_halka_sayilir_ve_SAHTE_gecis_uretmez():
    fabrika = _fabrika(_SahteClient())
    _, model = translate._generate_with_fallback(fabrika, (TERCIH, YEDEK), "p")
    assert model == TERCIH
    [s] = api_durum.gunluk_sayaclar()
    assert (s["model"], s["deneme"], s["basari"], s["hata"]) == (TERCIH, 1, 1, 0)
    assert _gecisler() == []
    [son] = api_durum.son_durumlar()
    assert son["sonuc"] == api_durum.BASARI and son["son_basari"]


def test_bes_anahtar_yuz_istek_sayaclara_anahtar_basina_esit_duser():
    """Plan senaryosu: 5 x 20 hak — 100 isteğin hepsi seçilen modelde, dengeli."""
    istemciler = [_SahteClient(['{"translation": "ok"}'] * 20) for _ in range(5)]
    fabrika = _fabrika(*istemciler)
    for _ in range(100):
        assert translate._generate_with_fallback(fabrika, (TERCIH, YEDEK), "p")[1] == TERCIH
    sayac = {s["anahtar"]: s["deneme"] for s in api_durum.gunluk_sayaclar()}
    assert sayac == {f"sira{i}": 20 for i in range(1, 6)}
    assert _gecisler() == []


def test_token_sayilari_kaydedilir_dusunme_cikisa_eklenir():
    meta = type("M", (), {"prompt_token_count": 800, "candidates_token_count": 500,
                          "thoughts_token_count": 120})()
    fabrika = _fabrika(_SahteClient([('{"translation": "ok"}', meta)]))
    translate._generate_with_fallback(fabrika, (TERCIH,), "p")
    [s] = api_durum.gunluk_sayaclar()
    assert (s["giris_token"], s["cikis_token"]) == (800, 620)


def test_soguma_atlamasi_istek_SAYILMAZ_ama_gecis_nedeni_olur():
    # 1. istek: tek anahtar 3.6'da günlük kota → soğuma, 3.5 çevirir.
    # 2. istek: 3.6'ya HİÇ istek atılmaz (anahtar soğumada), 3.5 çevirir.
    istemci = _SahteClient([_kota("gunluk")])
    fabrika = _fabrika(istemci)
    for _ in range(2):
        assert translate._generate_with_fallback(fabrika, (TERCIH, YEDEK), "p")[1] == YEDEK
    toplam = sum(s["deneme"] for s in api_durum.gunluk_sayaclar())
    assert toplam == len(istemci.models.cagrilar) == 3  # 1 kota + 2 başarı
    [atlama] = _olaylar("atlama")
    assert (atlama["model"], atlama["sonuc"]) == (TERCIH, api_durum.SOGUMA)
    ikinci, birinci = _gecisler()
    assert "günlük kota" in birinci["ayrinti"]["ozet"]
    assert "soğumada, atlandı" in ikinci["ayrinti"]["ozet"]


# ---------------------------------------------------------------- geçiş nedeni

def test_gecis_nedeni_anahtar_basina_SON_sonuc():
    """Planın örneği: "3.6 → 3.5: 3 anahtarda günlük kota, 2 anahtarda geçici hata"."""
    istemciler = [_SahteClient([_kota("gunluk"), '{"translation": "ok"}']) for _ in range(3)]
    istemciler += [_SahteClient([_APIHatasi(503)] * translate.MAX_RETRIES) for _ in range(2)]
    fabrika = _fabrika(*istemciler)
    _, model = translate._generate_with_fallback(fabrika, (TERCIH, YEDEK), "p")
    assert model == YEDEK
    [g] = _gecisler()
    assert (g["tur"], g["model"], g["hedef"]) == ("gecis", TERCIH, YEDEK)
    ozet = g["ayrinti"]["ozet"]
    assert "3 anahtarda günlük kota" in ozet and "2 anahtarda geçici hata" in ozet
    # Geçici hata anahtar başına TUR sayısı kadar tekrarlandı ama bir kez sayıldı.
    assert "6 anahtarda" not in ozet


def test_bos_yanit_gecis_nedeni_olarak_ayrilir_anahtar_bozuk_sayilmaz():
    fabrika = _fabrika(_SahteClient(["", '{"translation": "ok"}']), _SahteClient())
    _, model = translate._generate_with_fallback(fabrika, (TERCIH, YEDEK), "p")
    assert model == YEDEK
    [g] = _gecisler()
    assert "boş/engellenmiş yanıt" in g["ayrinti"]["ozet"]
    sonlar = {d["model"]: d["sonuc"] for d in api_durum.son_durumlar()}
    assert sonlar == {TERCIH: api_durum.BOS, YEDEK: api_durum.BASARI}


def test_zincir_tukenince_tukendi_kaydi_dusulur():
    fabrika = _fabrika(_SahteClient([_kota("gunluk"), _kota("gunluk")]))
    with pytest.raises(translate.TranslateError):
        translate._generate_with_fallback(fabrika, (TERCIH, YEDEK), "p")
    [g] = _gecisler()
    assert g["tur"] == "tukendi" and g["hedef"] is None
    assert "çeviri yapılamadı" in g["ayrinti"]["ozet"]


def test_bolum_gecisleri_url_ile_bulunur():
    fabrika = _fabrika(_SahteClient([_kota("gunluk"), '{"translation": "ok"}']))
    with api_durum.islem("prefetch", "https://s/novel/x/chapter-595"):
        translate._generate_with_fallback(fabrika, (TERCIH, YEDEK), "p")
    [g] = api_durum.bolum_gecisleri("https://s/novel/x/chapter-595")
    assert g["amac"] == "prefetch" and g["hedef"] == YEDEK
    assert api_durum.bolum_gecisleri("https://s/novel/x/chapter-596") == []


# ---------------------------------------------------------------- kota türleri

@pytest.mark.parametrize("tur, sinif", [
    ("gunluk", api_durum.KOTA_GUNLUK),
    ("dakikalik", api_durum.KOTA_DAKIKALIK),
    (None, api_durum.KOTA_BELIRSIZ),
])
def test_kota_turu_ayrilir_ve_sogumasi_kaydedilir(tur, sinif):
    fabrika = _fabrika(_SahteClient([_kota(tur)]), _SahteClient())
    once = time.time()
    translate._generate_with_fallback(fabrika, (TERCIH,), "p")
    [d] = [d for d in api_durum.son_durumlar() if d["sira"] == 1]
    assert d["sonuc"] == sinif and d["http_kodu"] == 429
    assert d["kota_sinir"] == 20 and d["yeniden_sn"] == 37.0
    assert d["soguma_bitis"] >= once + 59  # çeviri yolunun FİİLEN uyguladığı süre


def test_basari_sogumayi_kaldirir_ama_son_hatayi_unutmaz():
    kimlik = "sira1"
    api_durum.istek_kaydet(kimlik, 1, TERCIH, api_durum.KOTA_DAKIKALIK, 429, soguma_sn=60)
    api_durum.istek_kaydet(kimlik, 1, TERCIH, api_durum.BASARI, 200)
    [d] = api_durum.son_durumlar()
    assert d["soguma_bitis"] is None
    assert d["hata_sinifi"] == api_durum.KOTA_DAKIKALIK and d["son_hata"]


def test_gecici_hata_kota_sogumasini_SILMEZ():
    api_durum.istek_kaydet("sira1", 1, TERCIH, api_durum.KOTA_GUNLUK, 429, soguma_sn=3600)
    api_durum.istek_kaydet("sira1", 1, TERCIH, api_durum.GECICI, 503)
    [d] = api_durum.son_durumlar()
    assert d["soguma_bitis"] > time.time() + 3000


# ---------------------------------------------------------------- anahtar reddi

def test_reddedilen_anahtar_ceviriyi_OLDURMEZ_siradakine_gecilir():
    """Rotasyon açıkken tek iptal edilmiş anahtar her beş bölümden birini
    çevrilemez kılıyordu (401/403 doğrudan TranslateError'dı)."""
    istemciler = [_SahteClient([_APIHatasi(403)]), _SahteClient()]
    fabrika = _fabrika(*istemciler)
    _, model = translate._generate_with_fallback(fabrika, (TERCIH, YEDEK), "p")
    assert model == TERCIH  # model DEĞİŞMEDİ: arıza anahtara bağlı
    assert [len(c.models.cagrilar) for c in istemciler] == [1, 1]
    assert _gecisler() == []
    [d] = [d for d in api_durum.son_durumlar() if d["sira"] == 1]
    assert d["sonuc"] == api_durum.ANAHTAR


def test_gecersiz_anahtar_400_de_anahtar_reddidir():
    govde = {"error": {"code": 400, "details": [
        {"@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": "API_KEY_INVALID"}]}}
    fabrika = _fabrika(_SahteClient([_APIHatasi(400, govde)]), _SahteClient())
    assert translate._generate_with_fallback(fabrika, (TERCIH,), "p")[1] == TERCIH


def test_siradan_400_hala_ceviri_hatasidir_ve_kaydedilir():
    """Bozuk istek her anahtarda aynı cevabı verir; havuzu dolaşmak boşa olurdu."""
    fabrika = _fabrika(_SahteClient([_APIHatasi(400)]), _SahteClient())
    with pytest.raises(translate.TranslateError, match="Çeviri hatası"):
        translate._generate_with_fallback(fabrika, (TERCIH,), "p")
    [o] = _olaylar("istek")
    assert (o["sonuc"], o["http_kodu"]) == (api_durum.DIGER, 400)


def test_butun_anahtarlar_reddedilirse_mesaj_MESGUL_demez():
    fabrika = _fabrika(*[_SahteClient([_APIHatasi(401)] * 3) for _ in range(2)])
    with pytest.raises(translate.TranslateError) as bilgi:
        translate._generate_with_fallback(fabrika, (TERCIH, YEDEK), "p")
    mesaj = str(bilgi.value)
    assert "kabul edilmedi" in mesaj and "meşgul" not in mesaj


def test_red_ve_404_karisiksa_ikisi_de_soylenir():
    fabrika = _fabrika(
        _SahteClient([_APIHatasi(403)] * 3), _SahteClient([_APIHatasi(404)] * 3)
    )
    with pytest.raises(translate.TranslateError) as bilgi:
        translate._generate_with_fallback(fabrika, (TERCIH, YEDEK), "p")
    mesaj = str(bilgi.value)
    assert "401/403" in mesaj and "404" in mesaj and "meşgul" not in mesaj


def test_red_ve_kota_karisiksa_mesaj_erisim_DEMEZ():
    """Bir anahtar kotadaysa beklemek işe yarayabilir; "erişim yok" yanlış olurdu."""
    fabrika = _fabrika(
        _SahteClient([_APIHatasi(403)] * 3), _SahteClient([_kota("gunluk")] * 3)
    )
    with pytest.raises(translate.TranslateError) as bilgi:
        translate._generate_with_fallback(fabrika, (TERCIH, YEDEK), "p")
    assert "kabul edilmedi" not in str(bilgi.value)
    assert "sunulmuyor" not in str(bilgi.value)


# ---------------------------------------------------------------- yeniden başlatma

def _gercek_fabrika(monkeypatch, **anahtarlar):
    for ad, deger in anahtarlar.items():
        monkeypatch.setenv(ad, deger)
    return translate._gemini_fabrikasi(None)


def test_soguma_yeniden_baslatmada_GERI_YUKLENIR(monkeypatch):
    b = api_durum.anahtar_kimligi("anahtar-bbbb")
    api_durum.istek_kaydet(b, 2, TERCIH, api_durum.KOTA_GUNLUK, 429, soguma_sn=3600)
    translate.anahtar_sogumalarini_temizle()  # süreç öldü: bellek boş
    fabrika = _gercek_fabrika(
        monkeypatch, GEMINI_API_KEY="anahtar-aaaa", GEMINI2_API_KEY="anahtar-bbbb"
    )
    assert fabrika.anahtar_kimlikleri[1] == b
    assert translate._sogumada(1, TERCIH)
    assert not translate._sogumada(0, TERCIH)
    assert not translate._sogumada(1, YEDEK)  # soğuma MODEL başına


def test_soguma_anahtar_KIMLIGIYLE_eslenir_sirayla_degil(monkeypatch):
    """`.env` yeniden sıralanırsa soğuma yanlış anahtara taşınmamalı."""
    b = api_durum.anahtar_kimligi("anahtar-bbbb")
    api_durum.istek_kaydet(b, 2, TERCIH, api_durum.KOTA_GUNLUK, 429, soguma_sn=3600)
    translate.anahtar_sogumalarini_temizle()
    _gercek_fabrika(monkeypatch, GEMINI_API_KEY="anahtar-bbbb", GEMINI2_API_KEY="anahtar-aaaa")
    assert translate._sogumada(0, TERCIH) and not translate._sogumada(1, TERCIH)


def test_cikarilan_anahtarin_sogumasi_yeni_anahtara_TASINMAZ(monkeypatch):
    eski = api_durum.anahtar_kimligi("anahtar-silindi")
    api_durum.istek_kaydet(eski, 1, TERCIH, api_durum.KOTA_GUNLUK, 429, soguma_sn=3600)
    translate.anahtar_sogumalarini_temizle()
    _gercek_fabrika(monkeypatch, GEMINI_API_KEY="anahtar-yeni")
    assert not translate._sogumada(0, TERCIH)


def test_gecmis_soguma_aktif_engel_SAYILMAZ(monkeypatch):
    a = api_durum.anahtar_kimligi("anahtar-aaaa")
    api_durum.istek_kaydet(a, 1, TERCIH, api_durum.KOTA_DAKIKALIK, 429, soguma_sn=60)
    translate.anahtar_sogumalarini_temizle()
    gelecek = time.time() + 120
    monkeypatch.setattr(api_durum.time, "time", lambda: gelecek)
    monkeypatch.setattr(translate.time, "time", lambda: gelecek)
    _gercek_fabrika(monkeypatch, GEMINI_API_KEY="anahtar-aaaa")
    assert not translate._sogumada(0, TERCIH)


def test_sayaclar_yeniden_baslatmaya_dayanir():
    api_durum.istek_kaydet("sira1", 1, TERCIH, api_durum.BASARI, 200)
    api_durum._KURULAN.clear()  # yeni süreç: tablo kurulumu yeniden koşar
    api_durum.istek_kaydet("sira1", 1, TERCIH, api_durum.BASARI, 200)
    [s] = api_durum.gunluk_sayaclar()
    assert s["deneme"] == 2


# ---------------------------------------------------------------- bağlam

def test_paralel_islemler_birbirinin_kaydina_KARISMAZ():
    # Veritabanı ÖNCEDEN var (sunucudaki gibi, WAL kipinde). Sıfırdan dosyada iki
    # bağlantının aynı anda WAL'a geçmesi SQLite'ta beklemeden reddedilir; bu
    # yalnız ilk kurulumda bir kez olur ve bu testin ölçtüğü şey değildir.
    api_durum._connect().close()
    engel = threading.Barrier(2, timeout=5)
    sonuc = {}

    def calis(amac, url, model):
        fabrika = _fabrika(_SahteClient(engel=engel.wait))
        with api_durum.islem(amac, url):
            sonuc[amac] = translate._generate_with_fallback(fabrika, (model,), "p")

    iplikler = [
        threading.Thread(target=calis, args=("okuma", "https://s/a", "gemini-a")),
        threading.Thread(target=calis, args=("prefetch", "https://s/b", "gemini-b")),
    ]
    for t in iplikler:
        t.start()
    for t in iplikler:
        t.join()
    olaylar = _olaylar("istek")
    assert {(o["model"], o["amac"], o["url"]) for o in olaylar} == {
        ("gemini-a", "okuma", "https://s/a"),
        ("gemini-b", "prefetch", "https://s/b"),
    }
    assert len({o["islem"] for o in olaylar}) == 2


def test_onarim_asamasi_ayri_isaretlenir():
    with api_durum.islem("okuma", "https://s/a"):
        with api_durum.baglam(asama="kalinti_onarimi", url=None):
            translate._generate_with_fallback(_fabrika(_SahteClient()), (TERCIH,), "p")
    [o] = _olaylar("istek")
    assert (o["amac"], o["asama"], o["url"]) == ("okuma", "kalinti_onarimi", "https://s/a")


def test_baglamsiz_cagri_diger_amacla_kaydedilir():
    translate._generate_with_fallback(_fabrika(_SahteClient()), (TERCIH,), "p")
    [o] = _olaylar("istek")
    assert o["amac"] == "diger" and o["url"] is None


# ---------------------------------------------------------------- güvenlik

def test_kayit_yazilamazsa_ceviri_SURER(monkeypatch):
    def bozuk():
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(api_durum, "_connect", bozuk)
    fabrika = _fabrika(_SahteClient([_kota("gunluk"), "x"]), _SahteClient())
    _, model = translate._generate_with_fallback(fabrika, (TERCIH, YEDEK), "p")
    assert model == TERCIH


def test_anahtar_degeri_veritabanina_HIC_girmez(monkeypatch):
    gizli = "AIzaSyGIZLI-anahtar-degeri-1234567890"
    monkeypatch.setenv("GEMINI_API_KEY", gizli)
    fabrika = translate._gemini_fabrikasi(None)
    fabrika_sahte = _fabrika(_SahteClient([_kota("gunluk")]), _SahteClient())
    fabrika_sahte.anahtar_kimlikleri = fabrika.anahtar_kimlikleri + ["x"]
    translate._generate_with_fallback(fabrika_sahte, (TERCIH, YEDEK), "p")
    conn = sqlite3.connect(str(db.db_path()))
    dokum = "\n".join(conn.iterdump())
    conn.close()
    assert gizli not in dokum
    assert api_durum.anahtar_kimligi(gizli) in dokum


def test_ham_hata_govdesi_saklanmaz():
    hata = _APIHatasi(429, {"error": {"code": 429, "message": "GIZLI-PROJE-12345 bilgisi",
                                      "details": []}})
    fabrika = _fabrika(_SahteClient([hata]), _SahteClient())
    translate._generate_with_fallback(fabrika, (TERCIH,), "p")
    conn = sqlite3.connect(str(db.db_path()))
    dokum = "\n".join(conn.iterdump())
    conn.close()
    assert "GIZLI-PROJE-12345" not in dokum


# ---------------------------------------------------------------- zaman

def test_pasifik_gunu_yaz_ve_kis_saatinde_dogru():
    # Yaz (PDT, UTC-7): 2026-07-01 06:30 UTC → Pasifik'te hâlâ 30 Haziran.
    yaz = datetime(2026, 7, 1, 6, 30, tzinfo=timezone.utc).timestamp()
    assert api_durum.pasifik_gunu(yaz) == "2026-06-30"
    assert api_durum.pasifik_gunu(yaz + 3600) == "2026-07-01"
    # Kış (PST, UTC-8): 2026-12-01 07:30 UTC → Pasifik'te 30 Kasım.
    kis = datetime(2026, 12, 1, 7, 30, tzinfo=timezone.utc).timestamp()
    assert api_durum.pasifik_gunu(kis) == "2026-11-30"
    assert api_durum.pasifik_gunu(kis + 3600) == "2026-12-01"


def test_sonraki_sifirlama_pasifik_gece_yarisi():
    yaz = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc).timestamp()
    sifir = datetime.fromtimestamp(api_durum.sonraki_sifirlama(yaz), timezone.utc)
    assert (sifir.day, sifir.hour) == (19, 7)  # PDT gece yarısı = 07:00 UTC = TSİ 10:00


# ---------------------------------------------------------------- saklama

def test_eski_olaylar_ve_gunluk_ozetler_temizlenir():
    api_durum.istek_kaydet("sira1", 1, TERCIH, api_durum.BASARI, 200)
    conn = api_durum._connect()
    eski = time.time() - 40 * 86400
    conn.execute("INSERT INTO api_olay (zaman, tur) VALUES (?, 'istek')", (eski,))
    conn.execute(
        "INSERT INTO api_gunluk (anahtar, model, gun) VALUES ('sira1', ?, '2020-01-01')",
        (TERCIH,),
    )
    conn.commit()
    conn.close()
    api_durum.sifirla_temizlik_zamani()
    api_durum.istek_kaydet("sira1", 1, TERCIH, api_durum.BASARI, 200)
    assert all(o["zaman"] > eski for o in _olaylar())
    assert api_durum.gunluk_sayaclar("2020-01-01") == []


def test_olay_tavani_uygulanir(monkeypatch):
    monkeypatch.setattr(api_durum, "OLAY_TAVAN", 5)
    for _ in range(8):
        api_durum.sifirla_temizlik_zamani()
        api_durum.istek_kaydet("sira1", 1, TERCIH, api_durum.BASARI, 200)
    assert len(_olaylar()) == 5


# ---------------------------------------------------------------- kota ayrıştırma

def test_kota_ayrintisi_gunluk_ihlali_dakikaliga_ustun_tutar():
    hata = _APIHatasi(429, {"error": {"details": [{
        "@type": "type.googleapis.com/google.rpc.QuotaFailure",
        "violations": [
            {"quotaId": "GenerateRequestsPerMinutePerProjectPerModel-FreeTier",
             "quotaValue": "5"},
            {"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier",
             "quotaValue": "20"},
        ]}]}})
    k = translate.kota_ayrintisi(hata)
    assert (k["tur"], k["sinir"]) == ("gunluk", 20)
    assert translate.gunluk_kota_mi(hata)


def test_kota_ayrintisi_okunamayan_govdede_BELIRSIZ():
    k = translate.kota_ayrintisi(_APIHatasi(429))
    assert k == {"tur": None, "sinir": None, "kimlik": None, "yeniden_sn": None}
    assert not translate.gunluk_kota_mi(_APIHatasi(429))
