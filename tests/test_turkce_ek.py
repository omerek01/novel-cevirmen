"""turkce_ek: soyut ek ayrıştırma ve yeni köke yeniden kurma."""
import pytest

from core.turkce_ek import Kok, ayristir, kur, kur_tek


@pytest.mark.parametrize("kok,ekler,beklenen", [
    (Kok("kovan"), ("(y)A",), "kovana"),
    (Kok("kale"), ("(y)A",), "kaleye"),
    (Kok("göz"), ("DA",), "gözde"),
    (Kok("kitap"), ("DA",), "kitapta"),
    (Kok("kitap"), ("(y)I",), "kitabı"),
    (Kok("renk"), ("(y)I",), "rengi"),
    (Kok("top"), ("(y)I",), "topu"),               # tek hece yumuşamaz
    (Kok("sunny", kesmeli=True), ("(y)A",), "sunny'ye"),
    (Kok("kabuk", kesmeli=True), ("(y)I",), "kabuk'u"),  # kesmeli özel ad yumuşamaz
    (Kok("kovan"), ("lAr", "DAn"), "kovanlardan"),
    (Kok("kovan"), ("(n)In",), "kovanın"),
    (Kok("kale"), ("(n)In",), "kalenin"),
    (Kok("dağı", iyelikli=True), ("(y)A",), "dağına"),
    (Kok("dağı", iyelikli=True), ("DA",), "dağında"),
    (Kok("dağı", iyelikli=True), ("lAr",), "dağları"),
    (Kok("dağı", iyelikli=True), ("lAr", "(y)A"), "dağlarına"),
    (Kok("yaratığı", iyelikli=True), ("lAr",), "yaratıkları"),
    (Kok("saat"), ("(y)I",), "saati"),             # ince alan alıntı
    (Kok("kovan"), ("DA", "ki"), "kovandaki"),
    (Kok("gölge"), ("(y)lA",), "gölgeyle"),
])
def test_kur(kok, ekler, beklenen):
    assert kur(kok, ekler) == beklenen


def test_ayristir_geri_uretim_tutar():
    for yuzey in ["kovana", "kovanlardan", "kovandaki", "kovanın"]:
        adaylar = ayristir(Kok("kovan"), yuzey)
        assert adaylar
        assert all(kur(Kok("kovan"), d) == yuzey for d in adaylar)


def test_ayrismayan_bos_doner():
    assert ayristir(Kok("kovan"), "kovanxyz") == ()


@pytest.mark.parametrize("eski,yuzey,yeni,beklenen", [
    (Kok("kovan"), "kovana", Kok("oyuk"), "oyuğa"),
    (Kok("kovan"), "kovanda", Kok("oyuk"), "oyukta"),
    (Kok("kovan", kesmeli=True), "kovan'a", Kok("oyuk", kesmeli=True), "oyuk'a"),
    (Kok("kovan"), "kovanlardan", Kok("kale"), "kalelerden"),
    (Kok("dağı", iyelikli=True), "dağına", Kok("kovan"), "kovana"),
    (Kok("kovan"), "kovana", Kok("dağı", iyelikli=True), "dağına"),
])
def test_kur_tek(eski, yuzey, yeni, beklenen):
    assert kur_tek(eski, yuzey, yeni) == beklenen


def test_kur_tek_belirsizde_karar_vermez():
    # "kovanı" belirtme de iyelik de olabilir; ünlüyle biten yeni kökte ikisi ayrışır.
    assert kur_tek(Kok("kovan"), "kovanı", Kok("kale")) is None
    # Ünsüzle biten yeni kökte ikisi aynı yüzeyi verir -> karar verilir.
    assert kur_tek(Kok("kovan"), "kovanı", Kok("oyuk")) == "oyuğu"


def test_ozel_ada_yapim_eki_kesmesiz():
    assert kur(Kok("bülbül", kesmeli=True), ("lI",)) == "bülbüllü"


def test_soylenis_unlusu_uyumu_belirler_kaynastirmayi_degil():
    knight = Kok("knight", kesmeli=True, unlu="ı")
    assert kur(knight, ("(y)I",)) == "knight'ı"
    # Çokluk eki özel adda kesmesiz (TDK); uyum yine söylenişten: -lardan, -lerden değil.
    assert kur(knight, ("lAr", "DAn")) == "knightlardan"
    assert kur(Kok("reaper", kesmeli=True, unlu="ı"), ("(y)A",)) == "reaper'a"
