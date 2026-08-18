"""Özel adların sözlüğe OTOMATİK işlenmesi (karakter / diğer TÜM özel adlar).

Neden var: bu adlar sözlükte olmadığı sürece model her bölümde yeniden karar
veriyordu; aynı şehir bölümden bölüme başka türlü çıkabiliyordu (gerçek bulgu:
"Lightshadow City" için uydurma "Işıkölge"). İki sınıf, iki davranış:

    karakter            -> İngilizce KALIR (`X -> X`); İngilizce kalan TEK sınıf budur
    diğer her özel ad   -> modelin çeviride kullandığı TÜRKÇE karşılıkla sabitlenir
                           (yer, lonca, EŞYA, BECERİ, unvan, ırk, sistem terimi…)

Ağa çıkmaz: model yanıtı sahtelenir.
"""
import pytest

from core import glossary, pipeline, translate


# ---------- _parse_response: terim alanı ----------

def test_yanittan_ozel_adlar_ayiklanir():
    ham = (
        '{"translation": "[[1]] ç", "detected_names": ["Wang Lin"], '
        '"detected_terms": {"Zero Wing": "Sıfır Kanat", '
        '"Lightshadow City": "Işıkgölge Şehri"}}'
    )
    out = translate._parse_response(ham)
    assert out["detected_names"] == ["Wang Lin"]
    assert out["detected_terms"] == {
        "Zero Wing": "Sıfır Kanat",
        "Lightshadow City": "Işıkgölge Şehri",
    }


def test_esya_ve_beceri_adlari_da_terimdir():
    """E-17: eşya/beceri adları hiçbir sınıfa girmediği için kaydedilmiyordu
    (gerçek bulgu: Shadow Slave 30. bölüm, "Puppeteer's Shroud")."""
    out = translate._parse_response(
        '{"translation": "ç", "detected_terms": '
        '{"Puppeteer\'s Shroud": "Kuklacının Örtüsü", "Shadow Step": "Gölge Adımı"}}'
    )
    assert out["detected_terms"]["Puppeteer's Shroud"] == "Kuklacının Örtüsü"
    assert out["detected_terms"]["Shadow Step"] == "Gölge Adımı"


def test_eski_alan_adlari_da_okunur():
    """Model kimi zaman eski şemayı (guilds/places) üretiyor; düşürmek terimi
    sessizce kaybettirirdi."""
    out = translate._parse_response(
        '{"translation": "ç", "detected_guilds": {"Zero Wing": "Sıfır Kanat"}, '
        '"detected_places": {"Cold Wind City": "Soğuk Rüzgar Şehri"}}'
    )
    assert out["detected_terms"] == {
        "Zero Wing": "Sıfır Kanat",
        "Cold Wind City": "Soğuk Rüzgar Şehri",
    }


def test_eksik_alanlar_bos_gelir():
    assert translate._parse_response('{"translation": "ç"}')["detected_terms"] == {}


def test_terim_listesi_karsiliksiz_geldiginde_atilir():
    """Düz liste = Türkçe karşılık yok; sözlüğü kirletmektense hiç ekleme."""
    out = translate._parse_response(
        '{"translation": "ç", "detected_terms": ["Zero Wing"]}'
    )
    assert out["detected_terms"] == {}


@pytest.mark.parametrize("deger,beklenen", [
    (["a", "b"], ["a", "b"]),
    ("tek", ["tek"]),          # model bazen düz string döndürür
    (None, []),
    ([], []),
    (["a", "", None, 5], ["a"]),  # boş/None/sayı elenir
    ({"a": "b"}, []),          # yanlış tip
])
def test_liste_savunmasi(deger, beklenen):
    assert translate._liste(deger) == beklenen


@pytest.mark.parametrize("deger,beklenen", [
    ({"A": "B"}, {"A": "B"}),
    ({" A ": " B "}, {"A": "B"}),
    ({"A": ""}, {}),           # karşılıksız ad ATILIR
    ({"A": None}, {}),
    (["A", "B"], {}),          # liste geldi: karşılık bilinmiyor → hiç ekleme
    (None, {}),
])
def test_esleme_savunmasi(deger, beklenen):
    """Yanlış karşılıkla sözlüğü kirletmektense terimi hiç eklememek yeğdir:
    sözlük prompt'ta KURALdır, öneri değil."""
    assert translate._esleme(deger) == beklenen


# ---------- glossary.merge_terms / merge_names ----------

def test_merge_names_ingilizce_birakir():
    glossary.merge_names("k", ["Wang Lin", "Nephis"])
    terms = glossary.get_glossary("k")
    assert terms["Wang Lin"] == "Wang Lin"
    assert terms["Nephis"] == "Nephis"


def test_merge_terms_turkce_karsiligi_yazar():
    glossary.merge_terms("k", {"Lightshadow City": "Işıkgölge Şehri"})
    assert glossary.get_glossary("k")["Lightshadow City"] == "Işıkgölge Şehri"


def test_kullanici_kaydi_ezilmez():
    """Sözlük kullanıcınındır; otomatik algılama yalnız BOŞLUĞU doldurur."""
    glossary.set_term("k", "Lightshadow City", "Lightshadow City")   # elle: kalsın
    glossary.merge_terms("k", {"Lightshadow City": "Işıkgölge Şehri"})
    assert glossary.get_glossary("k")["Lightshadow City"] == "Lightshadow City"


def test_kaynak_kok_haline_indirilir():
    """Çekim ekli hâl ayrı satır açmamalı (aynı terim iki kez = karşılıklar ayrışır)."""
    glossary.merge_terms("k", {"Sunny's": "Sunny"})
    assert "Sunny" in glossary.get_glossary("k")


def test_ic_iyelik_tasiyan_ad_bozulmaz():
    """`normalize_source` yalnız SONDAKİ iyelik ekini atar; ad içindeki 's kalmalı."""
    glossary.merge_terms("k", {"Puppeteer's Shroud": "Kuklacının Örtüsü"})
    assert glossary.get_glossary("k")["Puppeteer's Shroud"] == "Kuklacının Örtüsü"


def test_bos_karsilik_kaynagi_korur():
    glossary.merge_terms("k", {"Wang Lin": "   "})
    assert glossary.get_glossary("k")["Wang Lin"] == "Wang Lin"


def test_bos_girdi_sorun_cikarmaz():
    glossary.merge_terms("k", None)
    glossary.merge_terms("k", {})
    glossary.merge_names("k", None)
    assert glossary.get_glossary("k") == {}


# ---------- translate_chapter toplama ----------

def _model_yaniti(monkeypatch, ham):
    class _Yanit:
        text = ham

    monkeypatch.setattr(
        translate, "_generate_with_fallback",
        lambda c, m, u, system=None, max_tokens=None: (_Yanit(), m[0]),
    )
    monkeypatch.setattr(translate.genai, "Client", lambda api_key=None: object())


def test_translate_chapter_ozel_adlari_toplar(monkeypatch):
    # Çeviri metni gerçekçi olmalı: karakter adı ÇEVİRİDE de geçiyorsa İngilizce
    # kalan sınıfa girer (bkz. detected_names süzgeci).
    _model_yaniti(monkeypatch, (
        '{"translation": "[[1]] Wang Lin, Sıfır Kanat locasına döndü.", '
        '"detected_names": ["Wang Lin"], '
        '"detected_terms": {"Zero Wing": "Sıfır Kanat", '
        '"Dark Night Empire": "Karanlık Gece İmparatorluğu"}}'
    ))
    r = translate.translate_chapter("Bir paragraf.", api_key="k")
    assert r["detected_names"] == ["Wang Lin"]
    assert r["detected_terms"] == {
        "Zero Wing": "Sıfır Kanat",
        "Dark Night Empire": "Karanlık Gece İmparatorluğu",
    }


def test_sozlukte_olan_terim_tekrar_bildirilmez(monkeypatch):
    """Zaten sözlükte olanı yeniden yazmaya gerek yok — gereksiz DB trafiği."""
    _model_yaniti(monkeypatch, (
        '{"translation": "[[1]] ç", "detected_names": [], '
        '"detected_terms": {"Zero Wing": "Sıfır Kanat", '
        '"Cold Wind City": "Soğuk Rüzgar Şehri"}}'
    ))
    r = translate.translate_chapter(
        "Bir paragraf.", api_key="k",
        glossary={"Zero Wing": "Sıfır Kanat", "Cold Wind City": "Soğuk Rüzgar Şehri"},
    )
    assert r["detected_terms"] == {}


# ---------- pipeline: sözlüğe işleme ----------

def test_pipeline_iki_sinifi_da_sozluge_yazar(monkeypatch):
    def sahte_translate(text, api_key=None, glossary=None, **kw):
        return {
            "translation": "ç", "source": None, "chunk_count": 1, "engine": "gemini",
            "detected_names": ["Wang Lin"],
            "detected_terms": {
                "Zero Wing": "Sıfır Kanat",
                "Lightshadow City": "Işıkgölge Şehri",
                "Puppeteer's Shroud": "Kuklacının Örtüsü",
            },
        }

    monkeypatch.setattr(pipeline, "translate_chapter", sahte_translate)
    monkeypatch.setattr(pipeline, "fetch_chapter", lambda url, **kw: {
        "book_slug": "kitap", "book_title": "K", "title": "B1", "chapter_no": 1,
        "text": "t", "next_url": None, "prev_url": None,
    })

    pipeline.get_or_translate("u1", "anahtar")

    terms = glossary.get_glossary("kitap")
    assert terms["Wang Lin"] == "Wang Lin"                    # karakter: İngilizce KALIR
    assert terms["Zero Wing"] == "Sıfır Kanat"                # lonca: Türkçe
    assert terms["Lightshadow City"] == "Işıkgölge Şehri"     # yer: Türkçe
    assert terms["Puppeteer's Shroud"] == "Kuklacının Örtüsü"  # eşya: Türkçe


# ---------- detected_names süzgeci: karakter DIŞI ad İngilizce çakılmasın ----------
# Ölçülen sorun: sözlükte 201 kaydın 173'ü `X -> X` idi ve içlerinde "Blackwater
# Guild", "Star-Moon Kingdom", "Ancient Rock City", "Hell Tanks" gibi karakter
# OLMAYAN adlar vardı. Model bunları `detected_names` kutusuna sızdırıyor; oraya
# düşen ad sözlüğe İngilizce çakılıyor ve sözlük prompt'ta KURAL olduğu için kitap
# boyunca bir daha Türkçeye çevrilemiyor.

def test_terim_kutusundaki_ad_karakter_sayilmaz():
    """Model aynı adı iki kutuya birden yazabiliyor; Türkçe karşılık kazanmalı."""
    out = translate.ayikla_karakter_adlari(
        ["Blackwater Guild", "Nephis"],
        {"Blackwater Guild": "Karasu Loncası"},
        "Nephis, Karasu Loncası'na katıldı.",
    )
    assert out == ["Nephis"]


def test_ceviride_turkcelestirilmis_ad_ingilizce_cakilmaz():
    """Model o bölümde Türkçesini yazmışken `X -> X` kaydı kendi kararıyla çelişir
    ve sonraki bölümleri İngilizceye zorlar (gerçek bulgu: Star-Moon Kingdom)."""
    out = translate.ayikla_karakter_adlari(
        ["Star-Moon Kingdom"], {}, "Ay-Yıldız Krallığı'nın sınırına vardılar."
    )
    assert out == []


def test_turkce_harfli_ad_ingilizce_kalan_sinifa_girmez():
    """Gerçek bulgu: model detected_names'e 'Kızıl Alev Kalesi' yazmıştı."""
    out = translate.ayikla_karakter_adlari(
        ["Kızıl Alev Kalesi"], {}, "Kızıl Alev Kalesi'ne doğru yürüdüler."
    )
    assert out == []


def test_ceviride_gecen_karakter_adi_korunur():
    """Süzgeç karakter adlarını ELEMEMELİ: İngilizce kalan tek sınıf onlar."""
    out = translate.ayikla_karakter_adlari(["Shi Feng"], {}, "Shi Feng kılıcını çekti.")
    assert out == ["Shi Feng"]


@pytest.mark.parametrize("ceviri", [
    "Nephis'in gözleri parladı.",   # Türkçe ek
    "NEPHIS bağırdı.",              # büyük harf
    "Nephis, geri çekil!",          # noktalama
])
def test_karakter_adi_cekimli_gectiginde_de_korunur(ceviri):
    assert translate.ayikla_karakter_adlari(["Nephis"], {}, ceviri) == ["Nephis"]


def test_yazim_varyanti_ceviride_gectiginde_korunur():
    """Ad metinde bitişik yazılmış olabilir; fold karşılaştırması bunu görür."""
    assert translate.ayikla_karakter_adlari(["Han Li"], {}, "HanLi ayağa kalktı.") == ["Han Li"]


def test_translate_chapter_sizan_adi_temizler(monkeypatch):
    _model_yaniti(monkeypatch, (
        '{"translation": "[[1]] Karasu Loncası saldırdı, Nephis karşı koydu.", '
        '"detected_names": ["Nephis", "Blackwater Guild"], '
        '"detected_terms": {"Blackwater Guild": "Karasu Loncası"}}'
    ))
    r = translate.translate_chapter("Bir paragraf.", api_key="k")
    assert r["detected_names"] == ["Nephis"]
    assert r["detected_terms"] == {"Blackwater Guild": "Karasu Loncası"}


def test_sozluge_isle_ayni_ad_iki_kutuda_ise_turkce_kazanir():
    """SIRA load-bearing: `merge_*` INSERT OR IGNORE, ilk yazan kazanır."""
    eklenen = pipeline._sozluge_isle("kitap", {
        "detected_names": ["Blackwater Guild"],
        "detected_terms": {"Blackwater Guild": "Karasu Loncası"},
    })
    assert glossary.get_glossary("kitap")["Blackwater Guild"] == "Karasu Loncası"
    assert eklenen["Blackwater Guild"] == "Karasu Loncası"


def test_onbellekten_gelen_eski_kirli_ad_sozluge_yazilmaz():
    """Süzgeç ÇEVİRİ yolunda kalırsa yetmez: eski cache satırındaki HAM
    detected_names, bölüm her açıldığında merge_names'e gidip sözlüğü kirletir."""
    from core import cache

    cache.save_chapter("u1", {
        "book_slug": "kitap", "book_title": "K", "title": "B1", "chapter_no": 1,
        "translation": "Nephis, Kadim Kaya Şehri'ne vardı.", "next_url": None,
        "detected_names": ["Ancient Rock City", "Nephis"], "chunk_count": 1,
    })
    pipeline.get_or_translate("u1", None)  # önbellek isabeti: anahtar gerekmez
    terms = glossary.get_glossary("kitap")
    assert "Ancient Rock City" not in terms  # çeviride Türkçesi var → İngilizce çakılmaz
    assert terms.get("Nephis") == "Nephis"   # karakter adı korunur


# ---------- suggest_term: okurken seçilen terime karşılık önerisi ----------

def _oneri_yaniti(monkeypatch, ham):
    class _Yanit:
        text = ham

    yakalanan = {}

    def sahte(client, models, user, system=None, max_tokens=None):
        yakalanan["user"] = user
        yakalanan["system"] = system
        return _Yanit(), models[0]

    monkeypatch.setattr(translate, "_generate_with_fallback", sahte)
    monkeypatch.setattr(translate.genai, "Client", lambda api_key=None: object())
    return yakalanan


def test_suggest_karakteri_ingilizce_birakir(monkeypatch):
    _oneri_yaniti(monkeypatch, '{"is_character": true, "target": "Sunny"}')
    out = translate.suggest_term("Sunny", "Sunny drew his blade.", api_key="k")
    assert out == {"source": "Sunny", "target": "Sunny", "is_character": True}


def test_suggest_karakterde_modelin_cevirisini_yok_sayar(monkeypatch):
    """Sözlük kuralı: karakter adı İngilizce KALIR. Model 'Güneşli' önerse bile
    karşılık adın kendisi olmalı — aksi halde kural kitap boyunca ters uygulanırdı."""
    _oneri_yaniti(monkeypatch, '{"is_character": true, "target": "Güneşli"}')
    assert translate.suggest_term("Sunny", api_key="k")["target"] == "Sunny"


def test_suggest_diger_ozel_adi_turkceye_cevirir(monkeypatch):
    _oneri_yaniti(monkeypatch, '{"is_character": false, "target": "Kuklacının Örtüsü"}')
    out = translate.suggest_term("Puppeteer's Shroud", api_key="k")
    assert out["target"] == "Kuklacının Örtüsü" and out["is_character"] is False


def test_suggest_baglami_prompta_koyar(monkeypatch):
    yakalanan = _oneri_yaniti(monkeypatch, '{"is_character": false, "target": "Gümüşkanat Kasabası"}')
    translate.suggest_term("Silverwing Town", "straight to Silverwing Town.", api_key="k")
    assert "Silverwing Town" in yakalanan["user"]
    assert "straight to Silverwing Town." in yakalanan["user"]
    assert yakalanan["system"] is translate.SUGGEST_INSTRUCTION  # çeviri talimatı DEĞİL


def test_suggest_bozuk_yanitta_kaynagi_korur(monkeypatch):
    """Karşılıksız kalmaktansa aynen koru — boş hedef sözlüğü bozardı."""
    _oneri_yaniti(monkeypatch, "bu JSON değil")
    assert translate.suggest_term("Zero Wing", api_key="k")["target"] == "Zero Wing"


def test_suggest_anahtarsiz_reddedilir():
    with pytest.raises(translate.TranslateError):
        translate.suggest_term("Zero Wing", api_key="")


def test_suggest_bos_terim_reddedilir():
    with pytest.raises(translate.TranslateError):
        translate.suggest_term("   ", api_key="k")


def test_suggest_ucu_oneriyi_dondurur(monkeypatch):
    """Uç ağa ÇIKMAZ: suggest_term sahtelenir, yalnız kablolama sınanır."""
    from fastapi.testclient import TestClient

    import server

    monkeypatch.setattr(
        server, "suggest_term",
        lambda source, context, key: {"source": source, "target": "Ork İmparatorluğu",
                                      "is_character": False},
    )
    res = TestClient(server.app).post(
        "/api/book/kitap/glossary/suggest",
        json={"source": "Orc Empire", "context": "in the Orc Empire"},
    )
    assert res.status_code == 200
    assert res.json()["target"] == "Ork İmparatorluğu"


# ---------- classify_terms: sözlükteki ESKİ İngilizce kayıtları gözden geçirme ----------
# `scripts/sozluk_gozden_gecir.py` bunu kullanır: süzgeç yalnız bundan sonrasını
# korur, kitaplara çakılmış eski `X -> X` kayıtları prompt'ta KURAL olmayı sürdürür.

def test_classify_karakterde_modelin_cevirisini_yok_sayar(monkeypatch):
    _oneri_yaniti(
        monkeypatch,
        '{"terms": [{"source": "Nephis", "is_character": true, "target": "Nefis"}]}',
    )
    out = translate.classify_terms(["Nephis"], api_key="k")
    assert out["Nephis"] == {"is_character": True, "target": "Nephis"}


def test_classify_karakter_disini_turkceye_cevirir(monkeypatch):
    _oneri_yaniti(
        monkeypatch,
        '{"terms": [{"source": "Blackwater Guild", "is_character": false, '
        '"target": "Karasu Loncası"}]}',
    )
    out = translate.classify_terms(["Blackwater Guild"], api_key="k")
    assert out["Blackwater Guild"]["target"] == "Karasu Loncası"


def test_classify_yazim_varyantiyla_donen_kaynagi_esler(monkeypatch):
    """Sözlükteki ÖZGÜN yazım anahtar olmalı: set_term o satırı güncelleyecek."""
    _oneri_yaniti(
        monkeypatch,
        '{"terms": [{"source": "OreEmpire", "is_character": false, '
        '"target": "Ork İmparatorluğu"}]}',
    )
    out = translate.classify_terms(["Ore Empire"], api_key="k")
    assert out == {"Ore Empire": {"is_character": False, "target": "Ork İmparatorluğu"}}


@pytest.mark.parametrize("ham", [
    '{"terms": [{"source": "Zero Wing", "is_character": false, "target": ""}]}',
    '{"terms": [{"source": "Bilinmeyen", "is_character": false, "target": "X"}]}',
    '{"terms": ["Zero Wing"]}',
    "JSON değil",
])
def test_classify_supheli_yaniti_kaydi_bozmaz(ham, monkeypatch):
    """Kaydı OLDUĞU GİBİ bırakmak, uydurma karşılıkla değiştirmekten yeğdir."""
    _oneri_yaniti(monkeypatch, ham)
    assert translate.classify_terms(["Zero Wing"], api_key="k") == {}


def test_classify_anahtarsiz_reddedilir():
    with pytest.raises(translate.TranslateError):
        translate.classify_terms(["Zero Wing"], api_key="")


def test_classify_bos_liste_cagri_yapmaz():
    assert translate.classify_terms([], api_key="") == {}


def test_all_terms_tum_kitaplari_dondurur():
    glossary.set_term("k1", "Nephis", "Nephis")
    glossary.set_term("k2", "Ore Empire", "Ork İmparatorluğu")
    assert set(glossary.all_terms()) == {
        ("k1", "Nephis", "Nephis"), ("k2", "Ore Empire", "Ork İmparatorluğu"),
    }
    assert glossary.all_terms("k2") == [("k2", "Ore Empire", "Ork İmparatorluğu")]


def test_suggest_ucu_kaydetmez(monkeypatch):
    """Öneri ÖNERİDİR: kullanıcı onaylamadan sözlüğe yazılmamalı."""
    from fastapi.testclient import TestClient

    import server

    monkeypatch.setattr(
        server, "suggest_term",
        lambda source, context, key: {"source": source, "target": "X", "is_character": False},
    )
    TestClient(server.app).post("/api/book/kitap/glossary/suggest", json={"source": "Orc Empire"})
    assert glossary.get_glossary("kitap") == {}
