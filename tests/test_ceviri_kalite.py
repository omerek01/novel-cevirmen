"""Kaynak kanıtı, yabancı alfabe ve doğrulanan tek turluk onarım sözleşmesi."""
import json
from types import SimpleNamespace

import pytest

from core import translate, cache, pipeline


def kalite():
    from core import ceviri_kalite
    return ceviri_kalite


def cevap(veri):
    return SimpleNamespace(text=json.dumps(veri, ensure_ascii=False),
                           candidates=[SimpleNamespace(finish_reason="STOP")])


def temiz(n=1):
    return {"denetlenen": list(range(n)), "hatalar": []}


def hata(tr="Ucubin", en="abomination", i=0):
    return {"paragraf": i, "tur": "dilbilgisi", "kaynak": en,
            "ceviri": tr, "aciklama": "Tamlayan eki bozuk.", "guven": 0.98}


def test_kiril_kalintisi_kaynakta_yoksa_yakalanir():
    assert kalite().yabanci_alfabe(["O cüce едва yarısı kadardı."], ["He was barely half his size."]) == {0: ["едва"]}


def test_kaynak_ve_sozlukteki_yabanci_ad_korunur():
    assert kalite().yabanci_alfabe(["Иван, Ω işaretine baktı."],
                                  ["Иван looked at the Ω symbol."]) == {}
    assert kalite().yabanci_alfabe(["Иван geldi."], ["Ivan arrived."], {"Ivan": "Иван"}) == {}


def test_karisik_alfabe_ve_turkce_harfler():
    assert kalite().yabanci_alfabe(["Sunnу kıyıya çıktı. Türkçe doğru."], ["Sunny reached shore."]) == {0: ["Sunnу"]}
    assert kalite().yabanci_alfabe(["Çığlık, ıslak kıyı, İblis."], ["A scream on the wet shore."]) == {}


def test_denetim_sahte_kaniti_ve_eksik_kapsami_reddeder():
    q = kalite()
    with pytest.raises(q.KaliteHatasi):
        q.denetim_coz({"denetlenen": [0], "hatalar": [hata(tr="olmayan")]}, ["abomination"], ["Ucubin"])
    with pytest.raises(q.KaliteHatasi):
        q.denetim_coz(temiz(), ["a", "b"], ["A", "B"])


def test_dusuk_guven_ve_uslup_otomatik_onarima_gitmez():
    x = hata(); x["guven"] = 0.6
    assert kalite().denetim_coz({"denetlenen": [0], "hatalar": [x]}, ["abomination"], ["Ucubin"]) == []


def test_dusuk_guven_temiz_diye_kaydedilmez():
    q = kalite(); x = hata(); x["guven"] = .88
    tr = ["Ucubin altında kıpırdandı."]
    rapor = q.denetle_ve_onar(tr, ["beneath the abomination"], {}, {},
                            lambda *args: (cevap({"denetlenen": [0], "hatalar": [x]}), "model"))
    assert rapor["durum"] == "supheli"
    assert rapor["supheli"][0]["paragraf"] == 0
    assert rapor["onarilan"] == []


def test_gemini_disinda_da_bitmemis_yanit_kabul_edilmez():
    q = kalite()
    with pytest.raises(q.KaliteHatasi):
        q.yanit_coz(translate._MetinYanit('{"denetlenen":[0],"hatalar":[]}'))
    assert q.yanit_coz(translate._MetinYanit('{"denetlenen":[0],"hatalar":[]}', 'STOP')) == temiz()


def test_onarim_sonrasi_denetim_ve_komsunun_korunmasi():
    q = kalite(); cagrilar = []
    yanitlar = [cevap({"denetlenen": [0, 1], "hatalar": [hata()]}),
                cevap({"duzeltmeler": [{"paragraf": 0, "ceviri": "Ucubenin altında kıpırdandı."}]}),
                cevap(temiz())]
    def uret(user, system, asama):
        cagrilar.append((json.loads(user), asama)); return yanitlar.pop(0), "vertex/gemini-3.6-flash"
    tr = ["Ucubin altında kıpırdandı.", "Sunny kıyıya çıktı."]
    rapor = q.denetle_ve_onar(tr, ["He shifted beneath the abomination.", "Sunny reached shore."], {}, {}, uret)
    assert tr == ["Ucubenin altında kıpırdandı.", "Sunny kıyıya çıktı."]
    assert rapor["onarilan"] == [0]
    assert [a for _, a in cagrilar] == ["kalite_denetimi", "kalite_onarimi", "kalite_dogrulama"]
    assert cagrilar[1][0]["hedefler"][0]["paragraf"] == 0
    assert len(cagrilar[1][0]["hedefler"]) == 1


@pytest.mark.parametrize("bozuk", ["Ucubin altında kıpırdandı.", "Ucubenin altında едва kıpırdandı."])
def test_basarisiz_onarim_asli_degistirmez(bozuk):
    q = kalite(); tr = ["Ucubin altında kıpırdandı."]
    yanitlar = [cevap({"denetlenen": [0], "hatalar": [hata()]}),
                cevap({"duzeltmeler": [{"paragraf": 0, "ceviri": bozuk}]}),
                cevap({"denetlenen": [0], "hatalar": [hata()]})]
    with pytest.raises(q.KaliteHatasi):
        q.denetle_ve_onar(tr, ["beneath the abomination"], {}, {}, lambda *args: (yanitlar.pop(0), "gemini-3.6-flash"))
    assert tr == ["Ucubin altında kıpırdandı."]


def test_bos_kesik_ve_hizalamayi_bozan_yanit_basari_sayilmaz():
    q = kalite()
    with pytest.raises(q.KaliteHatasi):
        q.yanit_coz(SimpleNamespace(text='{}', candidates=[SimpleNamespace(finish_reason="MAX_TOKENS")]))
    with pytest.raises(q.KaliteHatasi):
        q.denetle_ve_onar(["A"], ["a", "b"], {}, {}, lambda *args: (cevap(temiz()), "model"))


def test_kalite_raporu_cache_metin_degisince_bayat_kalmaz():
    veri = {"book_slug": "kitap", "translation": "İlk çeviri.", "source": "First translation.",
            "ceviri_kalitesi": {"surum": 1, "denetlenen": 1, "onarilan": []}}
    cache.save_chapter("test://kalite", veri)
    assert cache.get_chapter("test://kalite")["ceviri_kalitesi"]["denetlenen"] == 1
    cache.set_translation("test://kalite", "Değişen çeviri.")
    assert cache.get_chapter("test://kalite")["ceviri_kalitesi"] is None


def test_ceviri_akisinda_yabanci_alfabe_kayda_giremez(monkeypatch):
    monkeypatch.setenv("CEVIRI_KALITE", "1")
    monkeypatch.setattr(translate, "_gemini_fabrikasi", lambda key: object())
    def uret(*args, **kwargs):
        if kwargs.get("system") == kalite().DENETIM_TALIMATI:
            return cevap(temiz()), "gemini-3.6-flash"
        if kwargs.get("system") == kalite().ONARIM_TALIMATI:
            return cevap({"duzeltmeler": [{"paragraf": 0, "ceviri": "Sunny едва kendi boyunun yarısıydı."}]}), "gemini-3.6-flash"
        return cevap({"translation": "[[1]] Sunny едва kendi boyunun yarısıydı.", "detected_names": [], "detected_terms": {}}), "gemini-3.6-flash"
    monkeypatch.setattr(translate, "_generate_with_fallback", uret)
    with pytest.raises(translate.TranslateError):
        translate.translate_chapter("Sunny was barely half his size.", "test", models=("gemini-3.6-flash",))

    # Yeniden çeviri kalite kapısına takılırsa eski satır/arşiv korunur.
    url = "https://ornek.test/kitap/chapter-1"
    cache.save_chapter(url, {"book_slug": "kitap", "book_title": "Kitap", "chapter_no": 1,
                            "translation": "Sunny'nin boyu onun yarısı bile değildi.",
                            "source": "Sunny was barely half his size."})
    monkeypatch.setattr(translate, "ceviri_anahtari_var_mi", lambda key: True)
    monkeypatch.setattr(pipeline, "_anlam_tanimlari", lambda slug: None)
    with pytest.raises(translate.TranslateError):
        pipeline.get_or_translate(url, "test", refresh=True, advance_position=False)
    assert cache.get_chapter(url)["translation"] == "Sunny'nin boyu onun yarısı bile değildi."
    assert cache.arsiv_listesi(url) == []


def test_ceviri_akisinda_tamamlanan_denetim_raporu_tasinir(monkeypatch):
    q = kalite()
    monkeypatch.setenv("CEVIRI_KALITE", "1")
    monkeypatch.setattr(translate, "_gemini_fabrikasi", lambda key: object())
    def uret(*args, **kwargs):
        veri = temiz() if kwargs.get("system") == q.DENETIM_TALIMATI else {
            "translation": "[[1]] Sunny sessizce taş kıyıya çıktı.", "detected_names": [], "detected_terms": {}}
        return cevap(veri), "gemini-3.6-flash"
    monkeypatch.setattr(translate, "_generate_with_fallback", uret)
    sonuc = translate.translate_chapter("Sunny quietly reached the stone shore.", "test", models=("gemini-3.6-flash",))
    assert sonuc["translation"] == "Sunny sessizce taş kıyıya çıktı."
    assert sonuc["ceviri_kalitesi"]["denetlenen"] == 1
    assert sonuc["model"] == "gemini-3.6-flash"


def test_onarilan_paragrafta_eski_sozluk_hatasi_da_kalamaz(monkeypatch):
    q = kalite()
    monkeypatch.setenv("CEVIRI_KALITE", "1")
    monkeypatch.setattr(translate, "_gemini_fabrikasi", lambda key: object())
    def uret(*args, **kwargs):
        system = kwargs.get("system")
        if system == q.DENETIM_TALIMATI:
            user = json.loads(args[2]); tr = user["hedefler"][0]["ceviri"]
            veri = temiz() if "Ucubenin" in tr else {"denetlenen": [0], "hatalar": [hata()]}
        elif system == q.ONARIM_TALIMATI:
            veri = {"duzeltmeler": [{"paragraf": 0, "ceviri": "Ucubenin Temple yakınında kıpırdandı."}]}
        else:
            veri = {"translation": "[[1]] Ucubin Temple yakınında kıpırdandı.", "detected_names": [], "detected_terms": {}}
        return cevap(veri), "gemini-3.6-flash"
    monkeypatch.setattr(translate, "_generate_with_fallback", uret)
    with pytest.raises(translate.KaliteKontrolHatasi):
        translate.translate_chapter("beneath the abomination near the Temple.", "test", glossary={"Temple": "Tapınak"}, models=("gemini-3.6-flash",))


def test_uzun_paragrafta_iki_ad_duzeltmesi_yeniden_yazim_sayilmaz():
    # SequenceMatcher'ın otomatik sık karakter elemesi uzun Türkçe paragrafta
    # iki küçük değişikliği bile büyük yeniden yazım gibi gösterebiliyordu.
    q = kalite(); eski = "Bunun üzerine, Savaş Bakireleri silahlarını yavaşça indirdiler ve sonra liderleri kılıç mezarlığından geçen yolda yürümek için döndüğünde onu takip ettiler. Onlar tarafından çevrelenmiş olan Aziz, Sunny ve Kai'nin ileri yürümekten başka seçeneği yoktu. Birkaç dakika sonra, suskun iblis, Kabus'un sırtından zarifçe atladı, Kabus da gölgelere karışarak Sunny'nin ruhuna geri döndü."
    yeni = eski.replace("Aziz", "Saint").replace("Kabus", "Nightmare")
    en = "With that, the War Maidens slowly lowered their weapons, and then followed their leader as she turned to walk on the path through the graveyard of swords. Surrounded by them, Saint, Sunny, and Kai had no choice but to walk forward. After a few moments, the taciturn demon gracefully jumped down from Nightmare’s back, who then dissipated into shadows and returned to Sunny’s soul."
    yanitlar = [cevap({"denetlenen": [0], "hatalar": [hata("Aziz", "Saint")]}),
                cevap({"duzeltmeler": [{"paragraf": 0, "ceviri": yeni}]}), cevap(temiz())]
    tr = [eski]
    q.denetle_ve_onar(tr, [en], {}, {}, lambda *args: (yanitlar.pop(0), "model"))
    assert tr == [yeni]


def test_yeni_sozluk_ihlali_onarimin_kabulu_engeller():
    q = kalite(); tr = ["Ucubin altında kıpırdandı."]
    yanitlar = [cevap({"denetlenen": [0], "hatalar": [hata()]}),
                cevap({"duzeltmeler": [{"paragraf": 0, "ceviri": "Ucubenin altında kıpırdandı."}]})]
    with pytest.raises(q.KaliteHatasi):
        q.denetle_ve_onar(tr, ["beneath the abomination"], {}, {},
                         lambda *args: (yanitlar.pop(0), "model"), lambda tr: False)
    assert tr == ["Ucubin altında kıpırdandı."]


def test_kalite_raporu_arsiv_geri_yuklemede_dogru_metne_aittir():
    rapor = {"surum": 1, "denetlenen": 1, "onarilan": []}
    cache.save_chapter("test://arsiv-kalite", {"translation": "Eski metin.", "ceviri_kalitesi": rapor})
    cache.save_chapter("test://arsiv-kalite", {"translation": "Yeni metin."})
    assert cache.get_chapter("test://arsiv-kalite")["ceviri_kalitesi"] is None
    assert cache.arsivden_geri_yukle("test://arsiv-kalite", cache.son_arsiv_id("test://arsiv-kalite"))
    assert cache.get_chapter("test://arsiv-kalite")["ceviri_kalitesi"] == rapor


@pytest.mark.parametrize("veri", [
    {"denetlenen": [0, 0], "hatalar": []},
    {"denetlenen": [True], "hatalar": []},
    {"denetlenen": [0], "hatalar": [dict(hata(), guven=float('nan'))]},
    {"denetlenen": [0], "hatalar": [dict(hata(), paragraf=-1)]},
])
def test_hileli_denetim_yaniti_temiz_sayilmaz(veri):
    q = kalite()
    with pytest.raises(q.KaliteHatasi):
        q.denetim_coz(veri, ["abomination"], ["Ucubin"])
