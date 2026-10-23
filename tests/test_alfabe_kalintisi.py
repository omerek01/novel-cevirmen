"""Çeviride YABANCI ALFABEYE kayan sözcüklerin denetimi ve onarımı.

Ölçülen arıza (2026-10-23, canlı önbellek + `ceviri_arsivi`, 1384 bölüm): model
doğru SÖZCÜĞÜ üretiyor ama YANLIŞ ALFABEDE. Cümlenin kalanı kusursuz Türkçe,
içinde tek sözcük başka bir yazı sistemine kayıyor. Gerçek vakalar:

  ss#1110 (argon, arşiv)  Saniyeninสี่'te biri      สี่ = Tayca "dört"
  ss#1107 (argon, arşiv)  tespit할 hiçbir yöntemi   Korece fiil eki
  ss#1116 (argon)         dehşet கலந்த bir hayranlık கலந்த = Tamilce "karışık"
  ss#1093 (argon)         "İyilik пе... lanet olsun" Kiril
  ss#957  (3.8, arşiv)    o lanet bücür едва        Rusça "ancak"
  ss#691  (2.5)           ウェブ                     Japonca katakana

Kaynakta o karakterler YOK — sızıntı modelden geliyor, kaynaktan değil. Ölçülen
sıklık 14/1384 bölüm (%1); model kırılımı argon 4/38, 2.5-flash 6/70,
vertex/3.6-flash 2/125, gemini-3.6-flash 1/479.

Neden hiçbir denetim görmüyordu — üçü de ALFABEYE bakmıyor:
  * `ingilizce_kalinti` tokeni yalnız LATİN harf sınıfını tarıyor:
    Tayca/Korece/Tamilce bir sözcük token olarak bile eşleşmiyor.
  * `sozluk_ihlalleri` yalnız KAYITLI terimlere bakıyor.
  * `uzunluk_orani`/`KISALMA_ORANI` düz karakter sayımı; tek sözcük oynatmıyor.

Ek aşamalar (cilalama/kalite) açıkken paragraf başka bir gerekçeyle modele ikinci
kez gidiyor ve sözcük çoğu zaman ŞANS ESERİ düzeliyor — arşivdeki #1107 ve #1110
taslakları tam olarak bunu gösteriyor. Hepsi kapalıyken ikinci tur yok: ilk
taslak kalıcı önbelleğe yazılıyor ve önbellek isabeti bir daha çeviri
tetiklemediği için kullanıcı o sözcüğü SONSUZA DEK yabancı alfabede görüyor.
Denetim bu yüzden aşama düğmelerinden BAĞIMSIZ koşar.

Deterministiktir, ağa çıkmaz.
"""
from pathlib import Path

import pytest

from core import cache, translate


# ---------- denetçi: yakalaması GEREKENLER (hepsi gerçek vaka) ----------

@pytest.mark.parametrize("tr, en", [
    # ss#1116 — Tamilce
    ("Tanımayanların kanı donmuştu ve onun acımasız ölümcüllüğü karşısında "
     "dehşet கலந்த bir hayranlık içindeydiler.",
     "Those who did not know him felt their blood run cold, caught in awe "
     "mixed with terror at his ruthless lethality."),
    # ss#1110 — Tayca sayı, Türkçe gövdeye yapışık
    ("Saniyeninสี่'te biri kadar bir süre sonra yaratık şimşeklerden bir "
     "kafese hapsedildi.",
     "A quarter of a second later, the creature was trapped in a cage of lightning."),
    # ss#1107 — Korece ek, Türkçe gövdeye yapışık
    ("Sunny, o büyük klanların gölgelerini tespit할 hiçbir yöntemi olmadığını "
     "düşünecek kadar saf değildi.",
     "Sunny was not naive enough to think the great clans had no way to detect shadows."),
    # ss#1093 — Kiril
    ('"İyilik пе... lanet olsun. Bu ikisi gerçekten birbirinin tıpkısı..."',
     '"Favor... damn it. These two really are just alike..."'),
    # ss#957 — Rusça sözcük
    ("Özellikle de o lanet bücür едва onun yarısı boyundayken...",
     "Especially when that damn midget was barely half his height..."),
    # ss#691 — Japonca katakana
    ("Ağda ウェブ araması yaptı.", "He ran a web search."),
    # Çince (kullanıcının bildirdiği biçim)
    ("Sunny 不要 diye bağırdı.", "Sunny shouted for him to stop."),
])
def test_yabanci_alfabeye_kayan_sozcuk_yakalanir(tr, en):
    assert set(translate.alfabe_kalintisi([tr], [en])) == {0}


def test_sizan_sozcuk_bildirilir():
    """Bayrak hangi sözcüğün sızdığını taşır: okuyucuda ⚠ tek başına yetmiyor."""
    kalinti = translate.alfabe_kalintisi(
        ["dehşet கலந்த bir hayranlık"], ["awe mixed with terror"]
    )
    assert "கலந்த" in kalinti[0]


def test_yalniz_sizan_paragraf_bildirilir():
    kalinti = translate.alfabe_kalintisi(
        ["Sunny başını salladı.", "Saniyeninสี่'te biri."],
        ["Sunny nodded.", "A quarter of a second."],
    )
    assert set(kalinti) == {1}


# ---------- denetçi: yakalamaması GEREKENLER (yanlış pozitif) ----------

@pytest.mark.parametrize("tr, en", [
    # Türkçe harflerin tamamı
    ("Çığlık şiddetli ğüzel İpek ıslık öğütücü ÜŞÜDÜ.", "A violent scream."),
    # Türkçede kullanılan şapkalı harfler
    ("Kâğıt üzerinde âdeta bir îma vardı.", "There was almost a hint on paper."),
    # Avrupa dillerinden gelen özel adlar (Latin Ext-A/B hepsi meşru)
    ("Noël, Zoë ve Łukasz geldi.", "Noël, Zoë and Łukasz arrived."),
    # Vietnamca (Latin Extended Additional) özel ad
    ("Nguyễn ayağa kalktı.", "Nguyễn stood up."),
    # Düz Türkçe
    ("Sunny gölgeye adım attı ve kapıyı kapattı.", "Sunny stepped into the shadow."),
])
def test_dogru_ceviri_yakalanmaz(tr, en):
    assert translate.alfabe_kalintisi([tr], [en]) == {}


def test_kaynakta_da_gecen_karakter_sizinti_sayilmaz():
    """Kaynak zaten o yazı sistemini taşıyorsa model onu SADAKATLE aktarmıştır.

    Gerçek vaka: `reincarnation-of-the-strongest-sword-god` kaynaklarının 12
    bölümünde `叮`, `卜` gibi ses efektleri var (İngilizce metnin kendisi
    Çinceden fan çevirisi) ve hiçbiri çeviriye sızmamıştı. Onarım turu burada
    işe yaramaz — model aynı karakteri yine getirir — ve her bölümde bir istek
    daha PARA harcardı.
    """
    assert translate.alfabe_kalintisi(
        ["Bir 叮 sesi duyuldu."], ["A 叮 sound was heard."]
    ) == {}


def test_hizasiz_cift_denetlenmez():
    """Hangi Türkçe paragraf hangi İngilizce paragrafa denk, bilinmiyor."""
    tr = ["Sunny başını salladı.", "Saniyeninสี่'te biri."]
    en = ["Sunny nodded."]
    assert translate.alfabe_kalintisi(tr, en) == {}


def test_bos_paragraf_atlanir():
    assert translate.alfabe_kalintisi(["", "   "], ["x", "y"]) == {}


# ---------- onarım (desen `_kalintiyi_onar`'dan) ----------

def _onar(monkeypatch, yeni):
    def sahte(cf, models, deneme, en_paras, indeksler, *a, **k):
        for i in indeksler:
            deneme[i] = yeni
        return True
    monkeypatch.setattr(translate, "_paragraflari_yeniden_cevir", sahte)
    tr = ["Saniyeninสี่'te biri kadar bir süre sonra yaratık kaçtı."]
    en = ["A quarter of a second later, the creature escaped."]
    kalan = translate._alfabeyi_onar(
        None, (), tr, en, translate.alfabe_kalintisi(tr, en), {}, {}, set(), {}, None
    )
    return tr[0], kalan


def test_onarim_duzeltirse_bayrak_temizlenir(monkeypatch):
    metin, kalan = _onar(
        monkeypatch, "Saniyenin dörtte biri kadar bir süre sonra yaratık kaçtı."
    )
    assert "dörtte" in metin and kalan == {}


def test_onarim_duzeltmezse_bayrak_kalir(monkeypatch):
    """TEK tur bilinçli: döngü kurmak maliyeti katlar. Düzelmezse bayrak taşınır."""
    metin, kalan = _onar(
        monkeypatch, "Saniyeninสี่'te biri kadar sonra yaratık kaçtı."
    )
    assert set(kalan) == {0} and "สี่" in metin


# ---------- künye: kalıcı önbelleğe gidip gelir ----------

def test_bayrak_cache_gidis_donus(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVEL_DB_PATH", str(Path(tmp_path) / "t.db"))
    url = "https://x/ss/chapter-1116"
    cache.save_chapter(url, {
        "book_slug": "ss", "chapter_no": 1116,
        "translation": "dehşet கலந்த bir hayranlık",
        "alfabe_kalintisi": {0: "கலந்த"},
    })
    assert cache.get_chapter(url)["alfabe_kalintisi"] == {"0": "கலந்த"}


def test_bayrak_kunyesiz_guncellemede_silinmez(tmp_path, monkeypatch):
    """Sonraki yazma bayrağı taşımıyorsa eski bayrak KORUNUR (COALESCE deseni)."""
    monkeypatch.setenv("NOVEL_DB_PATH", str(Path(tmp_path) / "t.db"))
    url = "https://x/ss/chapter-1116"
    cache.save_chapter(url, {"book_slug": "ss", "chapter_no": 1116,
                             "translation": "a", "alfabe_kalintisi": {0: "க"}})
    cache.save_chapter(url, {"book_slug": "ss", "chapter_no": 1116, "translation": "a"})
    assert cache.get_chapter(url)["alfabe_kalintisi"] == {"0": "க"}
