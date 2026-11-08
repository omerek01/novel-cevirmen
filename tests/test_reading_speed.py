"""Okuma hızı ölçümü (hızlı okuma planı Adım A, 2026-11-08): oturum kaydı + istatistik."""
from fastapi.testclient import TestClient

from core import library, reading_log

DK = 60_000  # ms


def _yaz(oid, gun="2026-11-08", harf=3000, sozcuk=460, ms=2 * DK, mod="serbest",
         gecerli=True, slug="s", url=None):
    return reading_log.log_speed(oid, gun, slug, url or f"u-{oid}", mod, harf, sozcuk, ms, gecerli)


def test_ayni_oturum_tekrar_gonderimde_guncellenir_farkli_oturum_ayri_satir():
    _yaz("oturum-0001", ms=1 * DK, gecerli=False)  # sekme gizlendi: yarım gönderim
    _yaz("oturum-0001", ms=2 * DK)  # bölüm bitti: aynı oturum güncellenir
    _yaz("oturum-0002", url="u-oturum-0001")  # aynı bölüm ikinci kez okundu: ayrı satır
    s = reading_log.speed_stats("2026-11-08")
    assert s["oturum_sayisi"] == 2
    assert s["bugun_dk"] == 4.0


def test_sunucu_gecerliligi_yeniden_hesaplar():
    assert _yaz("kisa-bolum1", harf=1000)["gecerli"] is False  # 1500 harften kısa
    assert _yaz("kisa-sure01", ms=30_000)["gecerli"] is False  # 60 sn'den az
    assert _yaz("cok-hizli01", harf=12000, ms=2 * DK)["gecerli"] is False  # 6000 harf/dk
    assert _yaz("istemci-hay", gecerli=False)["gecerli"] is False  # istemcinin hayırı geçerli olmaz
    assert _yaz("dogru-olcum")["gecerli"] is True  # 1500 harf/dk
    s = reading_log.speed_stats("2026-11-08")
    assert s["oturum_sayisi"] == 1
    # Geçersizler de pratik dakikasına girer: 5 oturum × 2 dk + 0,5 dk.
    assert s["bugun_dk"] == 8.5


def test_kisisel_hiz_suzgeci_ve_sozcuk_karsiligi():
    # Az veride (n < 3) süzgeç yok.
    _yaz("a-00000001", harf=3000, ms=2 * DK)  # 1500
    _yaz("a-00000002", harf=4000, ms=2 * DK)  # 2000
    s = reading_log.speed_stats("2026-11-08")
    assert s["kisisel_hiz"]["hdk"] == 1750
    # Göz gezdirme: ortancanın 2 katından hızlı oturum atılır.
    _yaz("a-00000003", harf=3200, ms=2 * DK)  # 1600
    _yaz("a-00000004", harf=9800, ms=2 * DK)  # 4900 (> 2 × 1600)
    s = reading_log.speed_stats("2026-11-08")
    assert s["kisisel_hiz"]["hdk"] == 1600  # kalan 1500, 1600, 2000
    # sözcük/dk = harf/dk × Σsözcük ÷ Σharf (aynı küme)
    assert s["kisisel_hiz"]["sdk"] == round(1600 * (460 * 3) / (3000 + 4000 + 3200))


def test_tempo_oturumu_kisisel_hiza_girmez_gunlukte_ayri_gorunur():
    _yaz("serbest-001")  # 1500
    _yaz("tempo-00001", harf=4000, mod="tempo")  # 2000
    s = reading_log.speed_stats("2026-11-08")
    assert s["kisisel_hiz"]["hdk"] == 1500
    assert s["gunluk"] == [{"gun": "2026-11-08", "hdk": 1500, "sdk": 230, "tempo_hdk": 2000}]


def test_ilk_hafta_ilk_bes_oturum_ve_degisim_esigi():
    for i in range(4):
        _yaz(f"ilk-0000{i}", gun=f"2026-11-0{i + 1}")
    s = reading_log.speed_stats("2026-11-08")
    assert s["ilk_hafta"] is None and s["degisim"] is None  # 5 oturum yok
    _yaz("ilk-00004", gun="2026-11-05")
    s = reading_log.speed_stats("2026-11-08")
    assert s["ilk_hafta"] == {"hdk": 1500, "sdk": 230, "n": 5, "bas_gun": "2026-11-01"}
    assert s["degisim"] is None  # 10 oturum dolmadan başlangıçla aynı küme
    for i in range(5):
        _yaz(f"sonra-0000{i}", gun="2026-11-08", harf=3600)  # 1800
    s = reading_log.speed_stats("2026-11-08")
    # Son 10 = 5×1800 + 5×1500 → ortanca 1650; ilk 5'in ortancası 1500.
    assert s["degisim"] == 0.1


def test_gunluk_son_30_gun_ile_sinirli():
    _yaz("eski-000001", gun="2026-10-01")
    _yaz("yeni-000001", gun="2026-11-08")
    gunler = [g["gun"] for g in reading_log.speed_stats("2026-11-08")["gunluk"]]
    assert gunler == ["2026-11-08"]


def test_bos_veride_istatistik():
    s = reading_log.speed_stats("2026-11-08")
    assert s == {"kisisel_hiz": None, "ilk_hafta": None, "degisim": None,
                 "gunluk": [], "bugun_dk": 0.0, "oturum_sayisi": 0,
                 "obek_hiz": None, "obek_oturum": 0}


def test_gecersiz_girdi_yazilmaz():
    assert reading_log.log_speed("x", "2026-11-08", "s", "u", "serbest", 3000, 460, DK, True) is None
    assert reading_log.log_speed("oturum-0001", "bugün", "s", "u", "serbest", 3000, 460, DK, True) is None
    assert reading_log.log_speed("oturum-0001", "2026-11-08", "s", "u", "uçuş", 3000, 460, DK, True) is None
    assert reading_log.speed_stats("2026-11-08")["oturum_sayisi"] == 0


def test_kitap_silinince_hiz_satirlari_gider_alias_dahil():
    import server

    library.upsert_book("kanon", "K", "u1", "B1", 1)
    library.set_alias("takma", "kanon")
    client = TestClient(server.app)
    res = client.post("/api/reading-speed", json={
        "oturum_id": "silme-000001", "day": "2026-11-08", "slug": "takma", "url": "u1",
        "mode": "serbest", "chars": 3000, "words": 460, "active_ms": 2 * DK, "gecerli": True})
    assert res.status_code == 200 and res.json()["gecerli"] is True
    assert reading_log.speed_stats("2026-11-08")["oturum_sayisi"] == 1
    library.delete_book("kanon")
    assert reading_log.speed_stats("2026-11-08")["oturum_sayisi"] == 0


def test_uc_dogrulamasi_422():
    import server

    client = TestClient(server.app)
    iyi = {"oturum_id": "dogrulama-01", "day": "2026-11-08", "slug": "s", "url": "u",
           "mode": "serbest", "chars": 3000, "words": 460, "active_ms": 2 * DK, "gecerli": True}
    assert client.post("/api/reading-speed", json=iyi).status_code == 200
    for bozuk in ({"words": 4000}, {"url": "u" * 2001}, {"oturum_id": "a b"},
                  {"oturum_id": "kisa"}, {"mode": "hizli"}, {"day": "dün"},
                  {"chars": -1}, {"active_ms": 86_400_001}, {"slug": ""}):
        assert client.post("/api/reading-speed", json={**iyi, **bozuk}).status_code == 422, bozuk
    res = client.get("/api/reading-speed/stats", params={"day": "2026-11-08"})
    assert res.status_code == 200 and res.json()["oturum_sayisi"] == 1


def test_obek_modundaki_oturum_kisisel_hiza_girmez_ayri_doner():
    _yaz("normal-0001")  # 1500
    reading_log.log_speed("obekli-0001", "2026-11-08", "s", "u9", "serbest", 4000, 600,
                          2 * DK, True, obek=True)  # 2000
    s = reading_log.speed_stats("2026-11-08")
    assert s["kisisel_hiz"]["hdk"] == 1500 and s["oturum_sayisi"] == 1
    assert s["obek_hiz"]["hdk"] == 2000 and s["obek_oturum"] == 1
    assert [g["hdk"] for g in s["gunluk"]] == [1500]
