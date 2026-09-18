"""API durum paneli — planın tarayıcıda doğrulanan kabul ölçütleri.

  * ayarlardan açılır, geri düğmesi (ve telefonun geri tuşu) AYARLARA döner;
  * boş kayıt, beş anahtarlı kartlar ve dar ekran;
  * sunucu hatasında eski veri zamanıyla kalır ve BAYAT diye işaretlenir;
  * yalnız panel GÖRÜNÜRKEN yenilenir, istekler üst üste binmez;
  * künyedeki "neden bu model?" satırı.

Test sunucusu bilerek ANAHTARSIZ açılır (`sunucu.py`): beş anahtarlı görünüm,
sunucu yanıtı Playwright ile değiştirilerek sınanır. Yenileme aralığı (15 sn)
sahte saatle (`page.clock`) ileri sarılır.
"""
from __future__ import annotations

import sqlite3
import time

import pytest
from playwright.sync_api import expect

import tohum
from core import db
from yardimci import js_bekle

DURUM = "**/api/settings/api-status"


def _ayarlar(sayfa):
    sayfa.locator(".navtab[data-tab=settings]").click()
    expect(sayfa.locator("#settingsPanel")).to_be_visible()


def _panel_ac(sayfa):
    tohum.kitap()
    sayfa.goto(sayfa.taban + "/")
    expect(sayfa.locator("#shelves .spine[data-slug]").first).to_be_visible()
    _ayarlar(sayfa)
    sayfa.locator("#apiDurumAc").click()
    expect(sayfa.locator("#apiDurumView")).to_be_visible()


def _bagli(sayfa):
    expect(sayfa.locator("#apiBaglanti")).to_contain_text("Bağlı")


def _sahte_durum(anahtar_sayisi=5):
    simdi = time.time()
    zincir = ["gemini-3.6-flash", "gemini-3.5-flash", "gemini-2.5-flash"]
    durumlar = [
        ("basarili", "Son istek başarılı", "iyi", None),
        ("kota_gunluk", "Günlük kota", "bekle", simdi + 3 * 3600),
        ("kota_dakikalik", "Dakikalık kota", "bekle", simdi + 40),
        ("gecici", "Geçici hata", "uyari", None),
        ("anahtar", "Anahtar/izin hatası", "hata", None),
    ]
    kartlar = []
    for i in range(anahtar_sayisi):
        durum, etiket, ton, bitis = durumlar[i % len(durumlar)]
        modeller = []
        for j, model in enumerate(zincir):
            ilk = j == 0
            modeller.append({
                "model": model,
                "durum": durum if ilk else "gozlenmedi",
                "etiket": etiket if ilk else "Henüz gözlenmedi",
                "ton": ton if ilk else "notr",
                "son_deneme": simdi - 60 if ilk else None,
                "son_basari": simdi - 3600 if ilk else None,
                "son_hata": simdi - 60 if ilk and durum != "basarili" else None,
                "hata_etiketi": "günlük kota" if ilk and durum != "basarili" else None,
                "http_kodu": 429 if ilk and durum != "basarili" else None,
                "kota_turu": "gunluk", "kota_sinir": 20,
                "soguma_bitis": bitis if ilk else None,
                "bugun": {"deneme": 12, "basari": 11, "hata": 1, "kota": 1},
            })
        kartlar.append({"etiket": f"Anahtar {i + 1}", "sira": i + 1, "modeller": modeller})
    return {
        "guncelleme": simdi, "kayit_baslangici": simdi - 86400, "gun": "2026-09-18",
        "sifirlama": simdi + 5 * 3600, "tercih": zincir[0], "zincir": zincir,
        "rotasyon": "Her istekte sonraki anahtar", "anahtar_sayisi": anahtar_sayisi,
        "sogumada": 2, "bugun_toplam": {"deneme": 60, "basari": 55, "hata": 5},
        "anahtarlar": kartlar, "claude_secili": False,
    }


# ---------------------------------------------------------------- aç / kapat

def test_ayarlardan_acilir_geri_dugmesi_ayarlara_doner(sayfa):
    _panel_ac(sayfa)
    expect(sayfa.locator("#settingsPanel")).to_be_hidden()  # iç içe modal yok
    _bagli(sayfa)
    sayfa.locator("#apiDurumGeri").click()
    expect(sayfa.locator("#apiDurumView")).to_be_hidden()
    expect(sayfa.locator("#settingsPanel")).to_be_visible()


def test_telefonun_geri_tusu_da_ayarlara_doner(sayfa):
    _panel_ac(sayfa)
    sayfa.go_back()
    expect(sayfa.locator("#apiDurumView")).to_be_hidden()
    expect(sayfa.locator("#settingsPanel")).to_be_visible()


def test_baska_yerde_geri_basmak_ayarlari_SEBEPSIZ_acmaz(sayfa):
    """Panelden alt gezinmeyle çıkıldıktan sonraki geri, ayarlara dönüş sayılmaz."""
    _panel_ac(sayfa)
    sayfa.locator(".navtab[data-tab=library]").click()
    expect(sayfa.locator("#libraryView")).to_be_visible()
    sayfa.locator("#shelves .spine[data-slug]").first.click()
    expect(sayfa.locator("#bookView")).to_be_visible()
    sayfa.go_back()
    expect(sayfa.locator("#libraryView")).to_be_visible()
    expect(sayfa.locator("#settingsPanel")).to_be_hidden()


# ---------------------------------------------------------------- içerik

def test_bos_kayit_anahtarsiz_sunucu_durumu_soyler(sayfa):
    _panel_ac(sayfa)
    _bagli(sayfa)
    expect(sayfa.locator("#apiKartlar")).to_contain_text("anahtarı tanımlı değil")
    expect(sayfa.locator("#apiGecisler")).to_contain_text("hiç inilmedi")
    expect(sayfa.locator("#apiOzet")).to_contain_text("Her istekte sonraki anahtar")


@pytest.mark.parametrize(
    "sayfa", [{"width": 320, "height": 640}, {"width": 390, "height": 844}],
    indirect=True, ids=["320px", "390px"],
)
def test_bes_anahtar_karti_durumlari_metinle_ve_dar_ekranda_tasmadan(sayfa):
    sayfa.route(DURUM, lambda r: r.fulfill(json=_sahte_durum()))
    _panel_ac(sayfa)
    kartlar = sayfa.locator("#apiKartlar .api-kart")
    expect(kartlar).to_have_count(5)
    # Durum YALNIZ renkle anlatılmaz: rozetin metni var.
    expect(kartlar.nth(1).locator(".api-rozet").first).to_contain_text("Günlük kota")
    expect(kartlar.nth(1)).to_contain_text("Soğumada")
    expect(kartlar.nth(4).locator(".api-rozet").first).to_contain_text("Anahtar/izin hatası")
    expect(sayfa.locator("#apiOzet")).to_contain_text("2 / 5 anahtar")
    fazla = sayfa.evaluate(
        "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    assert fazla <= 1, f"{fazla}px yatay taşma"


def test_gecis_listesi_nedeni_gosterir(sayfa):
    from core import api_durum  # `temiz_db` NOVEL_DB_PATH'i sunucunun DB'sine çevirdi

    url = tohum.bolum_url("gumus-kule", 1)
    tohum.kitap()
    with api_durum.islem("prefetch", url):
        with api_durum.cagri() as d:
            api_durum.istek_kaydet("sira1", 1, "gemini-3.6-flash", api_durum.KOTA_GUNLUK, 429)
            api_durum.gecis_kaydet("gemini-3.6-flash", "gemini-3.5-flash", list(d))
    sayfa.goto(sayfa.taban + "/")
    _ayarlar(sayfa)
    sayfa.locator("#apiDurumAc").click()
    gecis = sayfa.locator("#apiGecisler .api-gecis")
    expect(gecis).to_have_count(1)
    expect(gecis).to_contain_text("3.6-flash → 3.5-flash")
    expect(gecis).to_contain_text("günlük kota")
    expect(gecis).to_contain_text("ön yükleme")
    expect(gecis).to_contain_text("Gumus Kule")


# ---------------------------------------------------------------- bağlantı

def test_sunucu_hatasinda_eski_veri_KALIR_ve_bayat_denir(sayfa):
    _panel_ac(sayfa)
    _bagli(sayfa)
    once = sayfa.locator("#apiOzet dt").count()
    assert once > 0
    sayfa.route(DURUM, lambda r: r.fulfill(status=500, body="bozuk"))
    sayfa.locator("#apiYenile").click()
    expect(sayfa.locator("#apiBaglanti")).to_contain_text("bayat")
    expect(sayfa.locator("#apiBaglanti")).to_have_class("gloss-hint api-baglanti api-bayat")
    expect(sayfa.locator("#apiOzet dt")).to_have_count(once)


def test_ilk_yukleme_basarisizsa_ulasilamadi_der(sayfa):
    sayfa.route(DURUM, lambda r: r.abort())
    _panel_ac(sayfa)
    expect(sayfa.locator("#apiBaglanti")).to_contain_text("ulaşılamadı")


# ---------------------------------------------------------------- yenileme

def _durum_istekleri(sayfa):
    liste = []
    sayfa.on(
        "request",
        lambda r: liste.append(r.url) if "/api/settings/api-status" in r.url else None,
    )
    return liste


def _sayi_bekle(liste, n, sure=5.0):
    son = time.monotonic() + sure
    while len(liste) < n and time.monotonic() < son:
        time.sleep(0.05)
    return len(liste)


def test_yalniz_gorunurken_yenilenir_gizlenince_DURUR(sayfa):
    sayfa.clock.install()
    istekler = _durum_istekleri(sayfa)
    _panel_ac(sayfa)
    _bagli(sayfa)
    assert _sayi_bekle(istekler, 1) == 1
    sayfa.clock.run_for(16_000)
    assert _sayi_bekle(istekler, 2) == 2, "görünür panel 15 sn'de bir yenilenmeli"

    # Sekme arka plana geçti: yenileme durur.
    sayfa.evaluate("""() => {
      Object.defineProperty(document, 'visibilityState', {configurable: true, get: () => 'hidden'});
      document.dispatchEvent(new Event('visibilitychange'));
    }""")
    sayfa.clock.run_for(60_000)
    time.sleep(0.3)
    assert len(istekler) == 2, "gizli sekmede istek atıldı"

    # Geri geldi: hemen bir kez yeniler.
    sayfa.evaluate("""() => {
      Object.defineProperty(document, 'visibilityState', {configurable: true, get: () => 'visible'});
      document.dispatchEvent(new Event('visibilitychange'));
    }""")
    assert _sayi_bekle(istekler, 3) == 3

    # Panelden çıkıldı: yenileme durur.
    _bagli(sayfa)
    sayfa.locator("#apiDurumGeri").click()
    expect(sayfa.locator("#apiDurumView")).to_be_hidden()
    sayfa.clock.run_for(60_000)
    time.sleep(0.3)
    assert len(istekler) == 3, "gizli panel için istek atıldı"


def test_istekler_UST_USTE_binmez(sayfa):
    sayfa.clock.install()
    bekleyen = []
    sayfa.route(DURUM, lambda r: bekleyen.append(r))
    _panel_ac(sayfa)
    js_bekle(sayfa, "() => document.getElementById('apiYenile').disabled")
    assert _sayi_bekle(bekleyen, 1) == 1
    # Uçuştayken yenilemeyi tetikleyen her yol: görünürlük olayı, zamanlayıcı.
    for _ in range(3):
        sayfa.evaluate("() => document.dispatchEvent(new Event('visibilitychange'))")
    # Zaman aşımından (8 sn) KISA: uzun sarma bekleyen isteği iptal ederdi.
    sayfa.clock.run_for(5_000)
    time.sleep(0.3)
    assert len(bekleyen) == 1, "uçuştaki yenilemenin üstüne yenisi atıldı"
    for r in bekleyen:
        r.continue_()
    _bagli(sayfa)


# ---------------------------------------------------------------- künye

def _model_yaz(url, model):
    conn = sqlite3.connect(db.db_path(), timeout=10)
    try:
        conn.execute("UPDATE chapters SET model = ? WHERE url = ?", (model, url))
        conn.commit()
    finally:
        conn.close()


def _okuyucuda_kunyeyi_ac(sayfa):
    sayfa.goto(sayfa.taban + "/")
    sayfa.locator("#shelves .spine[data-slug]").first.click()
    sayfa.locator("#chapterList .chapter-row").last.click()
    expect(sayfa.locator("#readerView")).to_be_visible()
    kunye = sayfa.locator("#readerBody article.chapter").first.locator(".kunye")
    with sayfa.expect_response(lambda r: "/api/settings/api-neden" in r.url):
        kunye.locator("summary").click()
    return kunye


def test_kunye_yedek_modelle_kaydedilen_bolumun_nedenini_soyler(sayfa):
    urller = tohum.kitap()
    _model_yaz(urller[0], "gemini-3.5-flash")
    kunye = _okuyucuda_kunyeyi_ac(sayfa)
    satir = kunye.locator(".kunye-neden")
    expect(satir).to_be_visible()
    expect(satir).to_contain_text("Neden bu model?")
    expect(satir).to_contain_text("3.5-flash")
    expect(satir).to_contain_text("daha önce")


def test_kunye_tercihle_cevrilen_bolumde_neden_satiri_GORUNMEZ(sayfa):
    tohum.kitap()  # model: gemini-3.6-flash (tercih edilen)
    kunye = _okuyucuda_kunyeyi_ac(sayfa)
    sayfa.wait_for_timeout(200)
    expect(kunye.locator(".kunye-neden")).to_be_hidden()
