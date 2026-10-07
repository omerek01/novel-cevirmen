"""Varlık grafiği boşluk bulucu (`core.varlik_bosluk`) ve hedefli soru — çevrimdışı.

Metinler yapay örneklerdir (roman metni değil)."""
from __future__ import annotations

import json

from core import cache, glossary, translate, varlik_bosluk as vb, varlik_cikarim, varlik_grafigi as vg

KITAP = "shadow-slave"


def _hazirla():
    for k, v in {"Sunny": "Sunny", "Effie": "Effie", "Jet": "Jet", "Master Jet": "Master Jet",
                 "Kai": "Kai", "Dark City": "Karanlık Şehir"}.items():
        glossary.set_term(KITAP, k, v)
    metin = (
        "Effie laughed and punched Sunny on the shoulder. "
        "Sunny and Effie walked to the Dark City together. "
        "Later, Effie told Sunny a joke.\n\n"
        "Master Jet watched the Sleepers. Master Jet smiled. Master Jet left.\n\n"
        "Kai sang. Sunny listened to Kai."
    )
    cache.save_chapter("https://x/ch-130", {
        "book_slug": KITAP, "book_title": "Shadow Slave", "title": "B130", "chapter_no": 130,
        "translation": "Çeviri.", "source": metin,
    })


def _ciftler(**kw):
    return {frozenset((c["a"], c["b"])): c for c in vb.ortak_gecisler(KITAP, **kw)}


def test_ortak_gecis_ayrik_anmalari_sayar_ic_ice_adi_saymaz():
    _hazirla()
    ciftler = _ciftler(en_az=3)
    assert frozenset(("Sunny", "Effie")) in ciftler
    assert ciftler[frozenset(("Sunny", "Effie"))]["sayi"] == 3
    # "Master Jet" içindeki `Jet` ayrı bir anma değildir.
    assert frozenset(("Jet", "Master Jet")) not in _ciftler(en_az=1)


def test_bagi_olan_cift_atlanir():
    _hazirla()
    k = vg.DugumCozucu(KITAP).coz
    vg.bag_ekle(KITAP, k("Sunny"), "yoldasi", k("Effie"), 130, None, "manual")
    assert frozenset(("Sunny", "Effie")) not in _ciftler(en_az=1)


class _Yanit:
    def __init__(self, veri):
        self.text = json.dumps(veri)


def test_hedefli_soru_kaniti_verilen_cumlelerle_dogrular(monkeypatch):
    _hazirla()
    cift = _ciftler(en_az=3)[frozenset(("Sunny", "Effie"))]

    def sahte(_f, models, user, system=None, max_tokens=None):
        assert "Sunny" in user and "Effie" in user
        return _Yanit({"baglar": [
            {"ozne": "Sunny", "iliski": "yoldasi", "nesne": "Effie",
             "kanit": "Sunny and Effie walked to the Dark City together.", "guven": 0.9},
            {"ozne": "Effie", "iliski": "dusmani", "nesne": "Sunny",
             "kanit": "Effie betrayed Sunny in the end.", "guven": 0.9},  # uydurma
        ]}), models[0]

    monkeypatch.setattr(translate, "_generate_with_fallback", sahte)
    sonuc = varlik_cikarim.ciftleri_sor(KITAP, [cift], api_key="x")
    assert [(g["iliski"], g["bolum"]) for g in sonuc["gecerli"]] == [("yoldasi", 130)]
    assert sonuc["red"][0]["sebep"] == "kanıt verilen cümlelerden değil"


def test_bilesik_ad_parcalari_isaretlenir_ve_ornek_olmaz():
    for k, v in {"Mantle": "Örtü", "Underworld": "Yeraltı", "Sunny": "Sunny", "Nephis": "Nephis"}.items():
        glossary.set_term(KITAP, k, v)
    metin = (
        "He wore the Mantle of the Underworld. The Mantle of the Underworld shone. "
        "Sunny touched the Mantle of the Underworld. The Underworld was far, but the Mantle was near.\n\n"
        "Nephis was Sunny's teacher. Sunny looked at Nephis. Nephis nodded to Sunny."
    )
    cache.save_chapter("https://x/ch-131", {
        "book_slug": KITAP, "book_title": "Shadow Slave", "title": "B131", "chapter_no": 131,
        "translation": "Çeviri.", "source": metin,
    })
    ciftler = _ciftler(en_az=3)
    bilesik = ciftler[frozenset(("Mantle", "Underworld"))]
    assert bilesik["bilesik"] is True
    # Bitişik anma cümlesi örnek olmaz; yalnız ayrık anma kalır.
    assert [s for _n, s in bilesik["ornekler"]] == ["The Underworld was far, but the Mantle was near."]
    # İyelik bir KİŞİYE bağlıysa da bitişik sayılır, ama çoğunluk ayrık olduğu için çift ilişkidir.
    insan = ciftler[frozenset(("Sunny", "Nephis"))]
    assert insan["bilesik"] is False


def test_ornek_secimi_ipucu_cumlelerini_one_alir():
    adaylar = [(n, f"Sunny and Jet stood there {n}.") for n in range(1, 10)]
    adaylar.append((50, "Jet was the teacher of Sunny."))
    secilen = vb._ornek_sec(adaylar, sinir=3)
    assert (50, "Jet was the teacher of Sunny.") in secilen
    assert [n for n, _s in secilen] == [1, 2, 50]  # kalan yer en erkenlerle, kronolojik


def test_bilesik_ad_icindeki_anma_ucuncu_varlikla_cift_kurmaz():
    for k, v in {"Sanctuary": "Tapınak", "Noctis": "Noctis", "Sunny": "Sunny"}.items():
        glossary.set_term(KITAP, k, v)
    metin = (
        "Sunny walked to the Sanctuary of Noctis. Sunny left the Sanctuary of Noctis at dawn. "
        "Sunny returned to the Sanctuary of Noctis.\n\n"
        "Noctis smiled at Sunny. Sunny thanked Noctis. Noctis was Sunny's teacher."
    )
    cache.save_chapter("https://x/ch-132", {
        "book_slug": KITAP, "book_title": "Shadow Slave", "title": "B132", "chapter_no": 132,
        "translation": "Çeviri.", "source": metin,
    })
    ciftler = _ciftler(en_az=1)
    # Yalnız gerçek (ayrık) anmalar sayılır: bileşik ad içindeki üç geçiş değil.
    assert ciftler[frozenset(("Sunny", "Noctis"))]["sayi"] == 3
    assert frozenset(("Sunny", "Sanctuary")) not in ciftler
    assert ciftler[frozenset(("Sanctuary", "Noctis"))]["bilesik"] is True


def test_profil_cumleleri_bilesik_anmayi_saymaz_ve_kitaba_yayar():
    for k, v in {"Sanctuary": "Tapınak", "Noctis": "Noctis", "Sunny": "Sunny"}.items():
        glossary.set_term(KITAP, k, k if k != "Sanctuary" else v)
    for no in range(1, 61):
        metin = (f"Noctis was the teacher of Sunny in part {no}. "
                 f"His teacher lived in the Sanctuary of Noctis.")  # ipuçlu ama bileşik anma
        cache.save_chapter(f"https://x/p-{no}", {
            "book_slug": KITAP, "book_title": "Shadow Slave", "title": f"P{no}", "chapter_no": no,
            "translation": "Çeviri.", "source": metin,
        })
    cumleler = vb.profil_cumleleri(KITAP, "Noctis", sinir=10)
    assert len(cumleler) == 10
    # Bileşik ad içindeki anma ADAY bile olmaz (sınır yüksekken bütün adaylar döner).
    hepsi = vb.profil_cumleleri(KITAP, "Noctis", sinir=500)
    assert len(hepsi) == 60 and all("Sanctuary" not in s for _n, s in hepsi)
    bolumler = [n for n, _s in cumleler]
    assert bolumler[0] == 1 and bolumler[-1] >= 50  # ilk 10 bölüme hapsolmaz


def test_profil_sorusu_kanit_ve_sorulan_varlik_denetimi(monkeypatch):
    for k in ("Sunny", "Belle", "Dorn", "First Irregular Company"):
        glossary.set_term(KITAP, k, k)
    cumleler = [(821, "Belle was a member of the First Irregular Company."),
                (821, "Dorn and Belle were members of the First Irregular Company.")]

    def sahte(_f, models, user, system=None, max_tokens=None):
        assert "VARLIK: Belle" in user and "[821]" in user
        return _Yanit({"baglar": [
            {"ozne": "Belle", "iliski": "grubu", "nesne": "First Irregular Company",
             "kanit": cumleler[0][1], "guven": 0.9},
            {"ozne": "Dorn", "iliski": "grubu", "nesne": "First Irregular Company",
             "kanit": cumleler[1][1], "guven": 0.9},  # doğru ama sorulan varlık değil
            {"ozne": "Belle", "iliski": "lideri", "nesne": "Sunny",
             "kanit": "Belle obeyed Sunny.", "guven": 0.9},  # uydurma kanıt
        ]}), models[0]

    monkeypatch.setattr(translate, "_generate_with_fallback", sahte)
    sonuc = varlik_cikarim.varlik_profili_sor(KITAP, "Belle", cumleler, api_key="x")
    assert [(g["ozne"], g["iliski"], g["bolum"]) for g in sonuc["gecerli"]] == [("Belle", "grubu", 821)]
    sebepler = sorted(r["sebep"] for r in sonuc["red"])
    assert sebepler == ["kanıt verilen cümlelerden değil", "sorulan varlığa değmiyor"]
    assert sonuc["degerler"] == []


def test_profil_gorevi_deger_olarak_dondurur(monkeypatch):
    glossary.set_term(KITAP, "Kim", "Kim")
    glossary.tanim_yaz(KITAP, "Kim", None, tur="kisi")
    cumleler = [(820, "Kim was a technician of the company.")]

    def sahte(_f, models, user, system=None, max_tokens=None):
        return _Yanit({"baglar": [
            {"ozne": "Kim", "iliski": "turu", "nesne": "technician", "kanit": cumleler[0][1], "guven": 0.9},
        ]}), models[0]

    monkeypatch.setattr(translate, "_generate_with_fallback", sahte)
    sonuc = varlik_cikarim.varlik_profili_sor(KITAP, "Kim", cumleler, api_key="x")
    assert [(d["anahtar"], d["deger"], d["bolum"]) for d in sonuc["degerler"]] == [("Görev", "technician", 820)]



def test_saint_oldurdu_kategori_diye_reddedilmez(monkeypatch):
    for k in ("Saint", "Black Knight"):
        glossary.set_term(KITAP, k, k)
    cozucu = vg.DugumCozucu(KITAP)
    cumleler = [(270, "The Saint struck down the Black Knight.")]

    def sahte(_f, models, user, system=None, max_tokens=None):
        return _Yanit({"baglar": [{"ozne": "Saint", "iliski": "oldurdu", "nesne": "Black Knight",
                                   "kanit": cumleler[0][1], "guven": 0.9}]}), models[0]

    monkeypatch.setattr(translate, "_generate_with_fallback", sahte)
    # Saint'in TABAN düğümü kategori olsa da (rütbe), öldüren gölgedir.
    sonuc = varlik_cikarim.varlik_profili_sor(KITAP, "Black Knight", cumleler, api_key="x",
                                             cozucu=cozucu, kategoriler={cozucu.coz("Saint")})
    assert [(g["ozne_kimlik"], g["iliski"]) for g in sonuc["gecerli"]] == [(cozucu.coz("Saint") + "#golge", "oldurdu")]



def test_kisi_olmayanin_turu_tur_anahtariyla_doner(monkeypatch):
    glossary.set_term(KITAP, "Reckoning Island", "Hesap Adası")
    glossary.tanim_yaz(KITAP, "Reckoning Island", None, tur="yer")
    cumleler = [(409, "Reckoning Island was a small island in the east.")]

    def sahte(_f, models, user, system=None, max_tokens=None):
        return _Yanit({"baglar": [{"ozne": "Reckoning Island", "iliski": "turu", "nesne": "small island",
                                   "kanit": cumleler[0][1], "guven": 0.9}]}), models[0]

    monkeypatch.setattr(translate, "_generate_with_fallback", sahte)
    sonuc = varlik_cikarim.varlik_profili_sor(KITAP, "Reckoning Island", cumleler, api_key="x")
    assert [(d["anahtar"], d["deger"]) for d in sonuc["degerler"]] == [("Tür", "small island")]
