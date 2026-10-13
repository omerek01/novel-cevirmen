"""Kaynak kanıtı, yabancı alfabe ve doğrulanan çok turlu onarım sözleşmesi.

KAYDET, İŞARETLE (2026-10-11, kullanıcı kararı): kalite katmanı çeviriyi artık
düşürmez. Onarılamayan ya da kanıtı doğrulanamayan sorun paragrafı özgün hâliyle
kalır ve "şüpheli" işaretlenir; denetim hiç tamamlanamazsa çeviri "denetlenemedi"
durumuyla kaydedilir. Eski davranışta tek bir doğrulanamayan bulgu ya da onarım
sonrası kalan hata bütün çeviriyi reddediyordu; daha önce çevrilmemiş bölüm hiç
okunamıyordu (shadow-slave 968, iki deneme).

ÖNCE ONAR (2026-10-11, kullanıcı şikâyeti): işaret son çaredir. Doğrulama ilk
çeviride ZATEN olan bir hatayı buldu diye onarım atılmaz; kalan hata sonraki turda
onarılır, reddedilen deneme gerekçesiyle modele geri verilir.
"""
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


def asamali(**kuyruklar):
    """Aşamaya göre sıralı yanıt veren sahte üretici; çağrıları (aşama, istem) olarak kaydeder.

    Kuyruğu biten aşama çağrılırsa hata yükselir (katman bunu erişim hatası sayar);
    beklenmeyen çağrıları testler `uret.cagrilar` üzerinden ayrıca doğrular."""
    cagrilar = []
    def uret(user, system, asama):
        cagrilar.append((asama, json.loads(user)))
        kuyruk = kuyruklar.get(asama) or []
        if not kuyruk:
            raise RuntimeError(f"beklenmeyen {asama} çağrısı")
        return cevap(kuyruk.pop(0)), "model"
    uret.cagrilar = cagrilar
    return uret


# Canlı vakanın (shadow-slave 970, paragraf 36) uydurma metinli eşi.
ZARAFET_EN = ["He moved with practiced grace and slew the beast that resembled a bat."]
ZARAFET_TR = "Alışılagelmiş bir zarafetle hareket edip yarasa benzeyen canavarı öldürdü."
ZARAFET_ARA = "Alışılagelmiş bir zarafetle hareket edip yarasaya benzeyen canavarı öldürdü."
ZARAFET_SON = "Ustalıklı bir zarafetle hareket edip yarasaya benzeyen canavarı öldürdü."
ZARAFET_ILK = {"paragraf": 0, "tur": "dilbilgisi", "kaynak": "resembled a bat",
               "ceviri": "yarasa benzeyen", "aciklama": "Yönelme eki eksik: yarasaya benzeyen.",
               "guven": 0.98}
ZARAFET_KALAN = {"paragraf": 0, "tur": "anlam", "kaynak": "practiced grace",
                 "ceviri": "Alışılagelmiş bir zarafetle",
                 "aciklama": "practiced burada ustalıklı demek, alışılagelmiş değil.", "guven": 0.92}


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
    # Düşük güvenli bulgu da onarıma gider (2026-10-11); onarılamazsa son çare
    # olarak işaretlenir, bölüm "temiz" sayılmaz. Onarım metni değiştirmeye gerek
    # görmediyse zorla değişiklik istenmez: tek deneme yapılır.
    q = kalite(); x = hata(); x["guven"] = .88
    tr = ["Ucubin altında kıpırdandı."]
    uret = asamali(kalite_denetimi=[{"denetlenen": [0], "hatalar": [x]}],
                   kalite_onarimi=[{"duzeltmeler": [{"paragraf": 0, "ceviri": tr[0]}]}])
    rapor = q.denetle_ve_onar(tr, ["beneath the abomination"], {}, {}, uret)
    assert rapor["durum"] == "supheli"
    assert rapor["supheli"][0]["paragraf"] == 0
    assert "otomatik onarılamadı" in rapor["supheli"][0]["aciklama"]
    assert rapor["onarilan"] == []
    assert [a for a, _ in uret.cagrilar] == ["kalite_denetimi", "kalite_onarimi"]


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


def test_cilalama_oncesi_metin_yalniz_degisen_hedefte_denetlenir():
    q = kalite()
    en = ["The brave hunter arrived.", "Mira waited."]
    once = ["Cesur avcı geldi.", "Mira bekledi."]
    tr = ["Avcı geldi.", once[1]]
    uret = asamali(kalite_denetimi=[temiz(2)])
    q.denetle_ve_onar(tr, en, {}, {}, uret, onceki_tr=once)
    hedefler = uret.cagrilar[0][1]["hedefler"]
    assert hedefler[0]["onceki_ceviri"] == once[0]
    assert "onceki_ceviri" not in hedefler[1]
    assert once == ["Cesur avcı geldi.", "Mira bekledi."]


def test_yanlis_hizali_onceki_ceviri_modele_gonderilmez():
    q = kalite(); uret = asamali(kalite_denetimi=[temiz(2)])
    with pytest.raises(q.KaliteHatasi):
        q.denetle_ve_onar(["A", "B"], ["a", "b"], {}, {}, uret, onceki_tr=["A"])
    assert uret.cagrilar == []


def test_onarim_dogrulamasi_bir_onceki_adayi_gorur():
    q = kalite()
    uret = asamali(kalite_denetimi=[{"denetlenen": [0], "hatalar": [hata()]}],
                   kalite_onarimi=[{"duzeltmeler": [{"paragraf": 0, "ceviri": "Ucubenin altında kıpırdandı."}]}],
                   kalite_dogrulama=[temiz()])
    tr = ["Ucubin altında kıpırdandı."]
    q.denetle_ve_onar(tr, ["He shifted beneath the abomination."], {}, {}, uret)
    hedef = uret.cagrilar[-1][1]["hedefler"][0]
    assert hedef["onceki_ceviri"] == "Ucubin altında kıpırdandı."
    assert hedef["ceviri"] == "Ucubenin altında kıpırdandı."


def test_yeni_eksiltme_degismeyen_yakin_alinti_yuzunden_kabul_edilmez():
    q = kalite()
    en = ["The brave hunter immediately reached the shore and met his old friends waiting there."]
    eski = "Cesur avcı hemen kıyıya geldi. Orada kendisini bekleyen eski arkadaşlarıyla karşılaştı."
    aday = "Cesur avcı kıyıya ulaştı. Orada kendisini bekleyen eski arkadaşlarıyla karşılaştı."
    ilk = {"paragraf": 0, "tur": "uslup", "kaynak": "reached the shore", "ceviri": "kıyıya geldi",
           "aciklama": "Cümle kuruluşu kusuru.", "guven": .9}
    eksik = {"paragraf": 0, "tur": "anlam", "kaynak": "immediately", "ceviri": "avcı",
             "onceki_ceviri_alintisi": "hemen", "aciklama": "Onarım hemen anlamını sildi.", "guven": .99}
    uret = asamali(kalite_denetimi=[{"denetlenen": [0], "hatalar": [ilk]}],
                   kalite_onarimi=[{"duzeltmeler": [{"paragraf": 0, "ceviri": aday}]}],
                   kalite_dogrulama=[{"denetlenen": [0], "hatalar": [eksik]}])
    tr = [eski]; iz = {}
    q.denetle_ve_onar(tr, en, {}, {}, uret, iz=iz)
    assert tr == [eski]
    assert iz["onarim_kaniti"][0]["kabul"] is False
    assert iz["onarim_kaniti"][0]["neden"] == "onarım yeni bir hata getirdi"


def test_kayip_kaniti_onceki_metinde_yoksa_kabul_kararini_degistirmez():
    q = kalite()
    assert not q._yeni_kayip({"onceki_ceviri_alintisi": "olmayan"}, "Avcı hemen geldi.", "Avcı geldi.")
    assert not q._yeni_kayip({"onceki_ceviri_alintisi": "avcı"}, "avcı hemen geldi.", "avcı geldi.")


def test_anlam_ve_akicilik_ayri_raporlanir_onarim_kaniti_saklanir():
    q = kalite(); x = hata(); iz = {}
    yanitlar = [cevap({"denetlenen": [0], "hatalar": [x]}),
                cevap({"duzeltmeler": [{"paragraf": 0, "ceviri": "Ucubenin altında kıpırdandı."}]}),
                cevap(temiz())]
    tr = ["Ucubin altında kıpırdandı."]
    r = q.denetle_ve_onar(tr, ["He shifted beneath the abomination."], {}, {},
                         lambda *a: (yanitlar.pop(0), "model"), iz=iz)
    assert r["surum"] == 2
    assert r["boyutlar"]["akicilik"]["bulgu_sayisi"] == 1
    assert r["boyutlar"]["sadakat"]["bulgu_sayisi"] == 0
    assert r["onarim_kaniti"][0]["once"] == "Ucubin altında kıpırdandı."
    assert r["onarim_kaniti"][0]["sonra"] == tr[0]
    assert iz["bulgular"][0]["ceviri"] == "Ucubin"


def test_dusuk_guvenli_uslup_notu_da_onarilir():
    # Canlı tekrar (shadow-slave 969, 2026-10-11): kaynaktaki iki ayrı sıfat çeviride
    # aynı sözcüğün art arda tekrarı olmuştu. Denetim bunu "uslup" ve 0,88 güvenle
    # verdiği için onarıma hiç gitmiyor, okura yalnız uyarı gidiyordu. Kullanıcı
    # kararı: düşük güvenli ve üslup notları da onarılsın.
    q = kalite()
    en = ["A huge, enormous wave rose over the deck."]
    tr = ["Devasa, devasa bir dalga güvertenin üstüne yükseldi."]
    tekrar = {"paragraf": 0, "tur": "uslup", "kaynak": "A huge, enormous wave",
              "ceviri": "Devasa, devasa bir dalga", "aciklama": "Aynı sıfat art arda tekrarlanmış.",
              "guven": 0.88}
    duzgun = "Kocaman, devasa bir dalga güvertenin üstüne yükseldi."
    uret = asamali(kalite_denetimi=[{"denetlenen": [0], "hatalar": [tekrar]}],
                   kalite_onarimi=[{"duzeltmeler": [{"paragraf": 0, "ceviri": duzgun}]}],
                   kalite_dogrulama=[temiz()])
    r = q.denetle_ve_onar(tr, en, {}, {}, uret)
    assert tr == [duzgun]
    assert r["onarilan"] == [0] and r["supheli"] == [] and r["durum"] == "denetlendi"
    hedef = [v for a, v in uret.cagrilar if a == "kalite_onarimi"][0]["hedefler"][0]
    assert hedef["hatalar"][0]["tur"] == "uslup"


def test_dogrulamanin_dusuk_guvenli_notu_da_sonraki_turda_onarilir():
    # Kabul edilen adayın doğrulamasında çıkan düşük güvenli not kabulü engellemez,
    # ama okura uyarı olarak da gitmez: sonraki turun hedefi olur.
    q = kalite(); tr = [ZARAFET_TR]
    uret = asamali(kalite_denetimi=[{"denetlenen": [0], "hatalar": [ZARAFET_ILK]}],
                   kalite_onarimi=[{"duzeltmeler": [{"paragraf": 0, "ceviri": ZARAFET_ARA}]},
                                   {"duzeltmeler": [{"paragraf": 0, "ceviri": ZARAFET_SON}]}],
                   kalite_dogrulama=[{"denetlenen": [0], "hatalar": [dict(ZARAFET_KALAN, guven=0.85)]},
                                     temiz()])
    r = q.denetle_ve_onar(tr, ZARAFET_EN, {}, {}, uret)
    assert tr == [ZARAFET_SON]
    assert r["supheli"] == [] and r["onarim_turu"] == 2


def test_yeni_hata_getiren_onarim_hicbir_turda_kabul_edilmez_izden_incelenebilir():
    # Onarım DEĞİŞTİRDİĞİ yerde yeni bir hata bulunursa reddedilir; her turda aynı
    # şey olursa paragraf özgün kalır ve son çare olarak işaretlenir.
    q = kalite(); iz = {}; n = q.MAX_ONARIM_TURU
    tr = ["Ucubin altında kıpırdandı."]
    bozuk = "Ucubenin altında kıpırdanmadı."
    uret = asamali(kalite_denetimi=[{"denetlenen": [0], "hatalar": [hata()]}],
                   kalite_onarimi=[{"duzeltmeler": [{"paragraf": 0, "ceviri": bozuk}]} for _ in range(n)],
                   kalite_dogrulama=[{"denetlenen": [0], "hatalar": [hata("kıpırdanmadı", "shifted")]}
                                     for _ in range(n)])
    r = q.denetle_ve_onar(tr, ["He shifted beneath the abomination."], {}, {}, uret, iz=iz)
    assert tr == ["Ucubin altında kıpırdandı."]
    assert r["onarilan"] == [] and r["onarilamayan"] == [0]
    assert r["durum"] == "supheli" and r["onarim_turu"] == n
    assert [a for a, _ in uret.cagrilar] == ["kalite_denetimi"] + ["kalite_onarimi", "kalite_dogrulama"] * n
    assert [x["sonra"] for x in iz["onarim_kaniti"]] == [bozuk] * n
    assert not any(x["kabul"] for x in iz["onarim_kaniti"])
    assert all("yeni bir hata" in x["neden"] for x in iz["onarim_kaniti"])
    # Reddedilen deneme gerekçesiyle sonraki tura geri verilir.
    ikinci = [v for a, v in uret.cagrilar if a == "kalite_onarimi"][1]["hedefler"][0]
    assert ikinci["ceviri"] == "Ucubin altında kıpırdandı."
    assert ikinci["reddedilen_onarim"]["ceviri"] == bozuk
    assert ikinci["reddedilen_onarim"]["sorunlar"] == ["Tamlayan eki bozuk."]
    assert any(x["paragraf"] == 0 and "otomatik onarılamadı" in x["aciklama"] for x in r["supheli"])


def test_onceden_var_olan_hata_onarimi_reddettirmez_sonraki_turda_duzeltilir():
    # Canlı vaka (shadow-slave 970, 2026-10-11): onarım iki hatayı düzeltti, doğrulama
    # ilk çeviride ZATEN duran başka bir hatayı buldu ve onarım atıldı. Okur iki
    # hatalı özgün paragrafı ve altta "otomatik onarılamadı" uyarısını gördü. Canlıdaki
    # 6 doğrulama reddinin 6'sı da bu türdendi (4'ü önceden vardı, 2'si aynı hata).
    q = kalite(); tr = [ZARAFET_TR]
    uret = asamali(kalite_denetimi=[{"denetlenen": [0], "hatalar": [ZARAFET_ILK]}],
                   kalite_onarimi=[{"duzeltmeler": [{"paragraf": 0, "ceviri": ZARAFET_ARA}]},
                                   {"duzeltmeler": [{"paragraf": 0, "ceviri": ZARAFET_SON}]}],
                   kalite_dogrulama=[{"denetlenen": [0], "hatalar": [ZARAFET_KALAN]}, temiz()])
    r = q.denetle_ve_onar(tr, ZARAFET_EN, {}, {}, uret)
    assert tr == [ZARAFET_SON]
    assert r["onarilan"] == [0] and r["onarilamayan"] == []
    assert r["supheli"] == [] and r["durum"] == "denetlendi" and r["onarim_turu"] == 2
    ikinci = [v for a, v in uret.cagrilar if a == "kalite_onarimi"][1]["hedefler"][0]
    assert ikinci["ceviri"] == ZARAFET_ARA  # kısmi onarımın üstüne çalışır
    assert [h["kaynak"] for h in ikinci["hatalar"]] == ["practiced grace"]
    assert "reddedilen_onarim" not in ikinci


def test_kismi_onarim_korunur_yalniz_kalan_hata_isaretlenir():
    # Turlar biterse kabul edilmiş kısmi onarım GERİ ALINMAZ; işaret yalnız metinde
    # hâlâ duran hatayı anlatır, düzeltilmiş olanı değil.
    q = kalite(); tr = [ZARAFET_TR]; n = q.MAX_ONARIM_TURU
    uret = asamali(kalite_denetimi=[{"denetlenen": [0], "hatalar": [ZARAFET_ILK]}],
                   kalite_onarimi=[{"duzeltmeler": [{"paragraf": 0, "ceviri": ZARAFET_ARA}]}] * n,
                   kalite_dogrulama=[{"denetlenen": [0], "hatalar": [ZARAFET_KALAN]}])
    r = q.denetle_ve_onar(tr, ZARAFET_EN, {}, {}, uret)
    assert tr == [ZARAFET_ARA]
    assert r["onarilan"] == [0] and r["onarilamayan"] == [0] and r["durum"] == "supheli"
    assert len(r["supheli"]) == 1
    assert r["supheli"][0]["aciklama"].startswith(ZARAFET_KALAN["aciklama"])
    assert "otomatik onarılamadı" in r["supheli"][0]["aciklama"]
    # Değiştirmeyen deneme doğrulamaya gönderilmez.
    assert [a for a, _ in uret.cagrilar].count("kalite_dogrulama") == 1


def test_hedef_hata_surerse_onarim_reddedilir_geri_bildirimle_yeniden_denenir():
    # Canlı vaka (shadow-slave 968): onarım hedeflenen yeri değiştirdi ama doğrulama
    # aynı sorunu yeni ifadede de buldu. Değişen yerde hata kalan aday kabul edilmez;
    # sonraki tur o denemeyi ve sorunu görür.
    q = kalite()
    en = ["Unless he used the coast road, of course. In that case they had a chance."]
    ilk = "Tabii sahil yolunu kullanmadığı sürece. Bu durumda bir şansları olurdu."
    tr = [ilk]
    hedef = {"paragraf": 0, "tur": "anlam", "kaynak": "Unless he used the coast road",
             "ceviri": "kullanmadığı sürece", "aciklama": "Koşul tersine dönmüş.", "guven": 0.95}
    aday1 = "Tabii sahil yolunu kullanmadıkça. Bu durumda bir şansları olurdu."
    suren = {"paragraf": 0, "tur": "anlam", "kaynak": "Unless he used the coast road, of course. In that case",
             "ceviri": "kullanmadıkça. Bu durumda", "aciklama": "Koşul hâlâ ters.", "guven": 0.92}
    aday2 = "Tabii sahil yolunu kullanırsa iş değişir. O durumda bir şansları olurdu."
    uret = asamali(kalite_denetimi=[{"denetlenen": [0], "hatalar": [hedef]}],
                   kalite_onarimi=[{"duzeltmeler": [{"paragraf": 0, "ceviri": aday1}]},
                                   {"duzeltmeler": [{"paragraf": 0, "ceviri": aday2}]}],
                   kalite_dogrulama=[{"denetlenen": [0], "hatalar": [suren]}, temiz()])
    iz = {}
    r = q.denetle_ve_onar(tr, en, {}, {}, uret, iz=iz)
    assert tr == [aday2]
    assert r["onarilan"] == [0] and r["supheli"] == [] and r["durum"] == "denetlendi"
    assert "hedeflenen hatayı gidermedi" in iz["onarim_kaniti"][0]["neden"]
    ikinci = [v for a, v in uret.cagrilar if a == "kalite_onarimi"][1]["hedefler"][0]
    assert ikinci["ceviri"] == ilk
    assert ikinci["reddedilen_onarim"]["ceviri"] == aday1
    assert ikinci["reddedilen_onarim"]["sorunlar"] == ["Koşul hâlâ ters."]


@pytest.mark.parametrize("bozuk", ["Ucubin altında kıpırdandı.", "Ucubenin altında едва kıpırdandı."])
def test_basarisiz_onarim_asli_degistirmez_ve_isaretlenir(bozuk):
    # Değiştirmeyen ve yabancı alfabe bırakan deneme doğrulamaya bile gitmez.
    q = kalite(); tr = ["Ucubin altında kıpırdandı."]; n = q.MAX_ONARIM_TURU
    uret = asamali(kalite_denetimi=[{"denetlenen": [0], "hatalar": [hata()]}],
                   kalite_onarimi=[{"duzeltmeler": [{"paragraf": 0, "ceviri": bozuk}]}] * n)
    r = q.denetle_ve_onar(tr, ["beneath the abomination"], {}, {}, uret)
    assert tr == ["Ucubin altında kıpırdandı."]
    assert r["onarilamayan"] == [0] and r["durum"] == "supheli"
    assert [a for a, _ in uret.cagrilar] == ["kalite_denetimi"] + ["kalite_onarimi"] * n


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


def test_ceviri_akisinda_onarilamayan_yabanci_alfabe_kaydedilip_isaretlenir(monkeypatch):
    monkeypatch.setenv("CEVIRI_KALITE", "1")
    monkeypatch.setattr(translate, "_gemini_fabrikasi", lambda key: object())
    def uret(*args, **kwargs):
        if kwargs.get("system") == kalite().DENETIM_TALIMATI:
            return cevap(temiz()), "gemini-3.6-flash"
        if kwargs.get("system") == kalite().ONARIM_TALIMATI:
            return cevap({"duzeltmeler": [{"paragraf": 0, "ceviri": "Sunny едва kendi boyunun yarısıydı."}]}), "gemini-3.6-flash"
        return cevap({"translation": "[[1]] Sunny едва kendi boyunun yarısıydı.", "detected_names": [], "detected_terms": {}}), "gemini-3.6-flash"
    monkeypatch.setattr(translate, "_generate_with_fallback", uret)
    sonuc = translate.translate_chapter("Sunny was barely half his size.", "test", models=("gemini-3.6-flash",))
    assert "едва" in sonuc["translation"]
    assert sonuc["ceviri_kalitesi"]["durum"] == "supheli"
    assert sonuc["ceviri_kalitesi"]["onarilamayan"] == [0]
    assert any("едва" in x["aciklama"] for x in sonuc["ceviri_kalitesi"]["supheli"])

    # Yeniden çeviri de kaydedilir; eski çeviri arşive gider (geri yüklenebilir).
    url = "https://ornek.test/kitap/chapter-1"
    cache.save_chapter(url, {"book_slug": "kitap", "book_title": "Kitap", "chapter_no": 1,
                            "translation": "Sunny'nin boyu onun yarısı bile değildi.",
                            "source": "Sunny was barely half his size."})
    monkeypatch.setattr(translate, "ceviri_anahtari_var_mi", lambda key: True)
    monkeypatch.setattr(pipeline, "_anlam_tanimlari", lambda slug: None)
    pipeline.get_or_translate(url, "test", refresh=True, advance_position=False)
    assert "едва" in cache.get_chapter(url)["translation"]
    assert len(cache.arsiv_listesi(url)) == 1


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


def test_ceviri_akisinda_iki_turlu_onarim_kaydedilir_her_turun_modeli_kunyeye_girer(monkeypatch):
    # Uçtan uca: okurun gördüğü metin son onarımdır, künyede uyarı yoktur; turlar
    # zincirin farklı halkalarına düşerse ikisi de "çeviren model" olarak yazılır.
    monkeypatch.setenv("CEVIRI_KALITE", "1")
    monkeypatch.setattr(translate, "_gemini_fabrikasi", lambda key: object())
    onarimlar = [(ZARAFET_ARA, "gemini-2.5-flash"), (ZARAFET_SON, "gemini-3.5-flash")]
    dogrulamalar = [{"denetlenen": [0], "hatalar": [ZARAFET_KALAN]}, temiz()]
    def uret(*args, **kwargs):
        asama = translate.api_durum.mevcut_baglam().get("asama")
        if asama == "kalite_denetimi":
            return cevap({"denetlenen": [0], "hatalar": [ZARAFET_ILK]}), "gemini-3.6-flash"
        if asama == "kalite_dogrulama":
            return cevap(dogrulamalar.pop(0)), "gemini-3.6-flash"
        if asama == "kalite_onarimi":
            metin, model = onarimlar.pop(0)
            return cevap({"duzeltmeler": [{"paragraf": 0, "ceviri": metin}]}), model
        return cevap({"translation": "[[1]] " + ZARAFET_TR, "detected_names": [],
                      "detected_terms": {}}), "gemini-3.6-flash"
    monkeypatch.setattr(translate, "_generate_with_fallback", uret)
    sonuc = translate.translate_chapter(ZARAFET_EN[0], "test", models=("gemini-3.6-flash",))
    assert sonuc["translation"] == ZARAFET_SON
    assert sonuc["model"] == "gemini-3.6-flash + gemini-2.5-flash + gemini-3.5-flash"
    kalite_raporu = sonuc["ceviri_kalitesi"]
    assert kalite_raporu["supheli"] == [] and kalite_raporu["durum"] == "denetlendi"
    assert kalite_raporu["onarim_turu"] == 2 and onarimlar == [] and dogrulamalar == []


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
    sonuc = translate.translate_chapter("beneath the abomination near the Temple.", "test",
                                        glossary={"Temple": "Tapınak"}, models=("gemini-3.6-flash",))
    # Onarım yeni sözlük ihlali getirdiği için kabul edilmez; paragraf özgün kalır, işaretlenir.
    assert sonuc["translation"] == "Ucubin Temple yakınında kıpırdandı."
    assert sonuc["ceviri_kalitesi"]["onarilamayan"] == [0]


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
    r = q.denetle_ve_onar(tr, ["beneath the abomination"], {}, {},
                         lambda *args: (yanitlar.pop(0), "model"), lambda tr: False)
    assert tr == ["Ucubin altında kıpırdandı."]
    assert r["onarilamayan"] == [0]
    assert yanitlar == []  # aday kalmadığı için doğrulama çağrısı yapılmadı


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


# ---------- kaydet, işaretle (2026-10-11) ----------

def test_kaniti_dogrulanamayan_bulgu_cevirmeyi_dusurmez_paragrafi_isaretler():
    q = kalite(); tr = ["Ucubin altında kıpırdandı."]
    r = q.denetle_ve_onar(tr, ["He shifted beneath the abomination."], {}, {},
                         lambda *a: (cevap({"denetlenen": [0], "hatalar": [hata(tr="olmayan alıntı")]}), "model"))
    assert tr == ["Ucubin altında kıpırdandı."]
    assert r["onarilan"] == [] and r["durum"] == "supheli"
    assert "kanıt doğrulanamadı" in r["supheli"][0]["aciklama"]


def test_bicimsiz_bulgu_temiz_sayilmaz():
    q = kalite(); tr = ["Ucubin altında kıpırdandı."]
    r = q.denetle_ve_onar(tr, ["He shifted beneath the abomination."], {}, {},
                         lambda *a: (cevap({"denetlenen": [0], "hatalar": [dict(hata(), guven=float("nan"))]}), "model"))
    assert r["durum"] == "supheli" and r["gecersiz_bulgu"] == 1


def test_bir_onarim_gecer_digeri_isaretlenir():
    q = kalite(); n = q.MAX_ONARIM_TURU
    en = ["He shifted beneath the abomination.", "Sunny reached the shore."]
    tr = ["Ucubin altında kıpırdandı.", "Sunny kıyıya ulaştılar."]
    kotu = {"duzeltmeler": [{"paragraf": 1, "ceviri": "Sunny kıyıya ulaştılar ki."}]}
    uret = asamali(
        kalite_denetimi=[{"denetlenen": [0, 1], "hatalar": [hata(), hata("ulaştılar", "reached", 1)]}],
        kalite_onarimi=[{"duzeltmeler": [{"paragraf": 0, "ceviri": "Ucubenin altında kıpırdandı."},
                                         {"paragraf": 1, "ceviri": "Sunny kıyıya ulaştılar ki."}]}]
                       + [kotu] * (n - 1),
        # Sonraki turlarda yalnız 1. paragraf doğrulanır: yerel numarası 0'dır.
        kalite_dogrulama=[{"denetlenen": [0, 1], "hatalar": [hata("ulaştılar ki", "reached", 1)]}]
                         + [{"denetlenen": [0], "hatalar": [hata("ulaştılar ki", "reached", 0)]}] * (n - 1))
    r = q.denetle_ve_onar(tr, en, {}, {}, uret)
    assert tr == ["Ucubenin altında kıpırdandı.", "Sunny kıyıya ulaştılar."]
    assert r["onarilan"] == [0] and r["onarilamayan"] == [1]
    sonraki = [v for a, v in uret.cagrilar if a == "kalite_onarimi"][1:]
    assert [[h["paragraf"] for h in v["hedefler"]] for v in sonraki] == [[1]] * (n - 1)


def test_cok_sayida_sorun_paketlere_bolunup_onarilir():
    # Eskiden sekizden fazla hedefte onarım hiç denenmiyor, hepsi okura uyarı olarak
    # gidiyordu. Artık hedefler en çok MAX_ONARIM_PARAGRAF'lık paketlerle onarılır.
    q = kalite(); n = q.MAX_ONARIM_PARAGRAF + 1
    en = [f"P{i} beneath the abomination." for i in range(n)]
    tr = [f"P{i} Ucubin altında." for i in range(n)]
    paket_boylari = []
    def uret(user, system, asama):
        veri = json.loads(user); hedefler = veri["hedefler"]
        if asama == "kalite_onarimi":
            paket_boylari.append(len(hedefler))
            return cevap({"duzeltmeler": [{"paragraf": h["paragraf"],
                                           "ceviri": h["ceviri"].replace("Ucubin", "Ucubenin")}
                                          for h in hedefler]}), "model"
        return cevap({"denetlenen": list(range(len(hedefler))),
                      "hatalar": [hata(i=k) for k, h in enumerate(hedefler) if "Ucubin " in h["ceviri"]]}), "model"
    r = q.denetle_ve_onar(tr, en, {}, {}, uret)
    assert tr == [f"P{i} Ucubenin altında." for i in range(n)]
    assert paket_boylari == [q.MAX_ONARIM_PARAGRAF, 1]
    assert r["onarilan"] == list(range(n)) and r["onarilamayan"] == [] and r["supheli"] == []


def test_denetim_tamamlanamazsa_ceviri_denetlenemedi_olarak_kaydedilir(monkeypatch):
    q = kalite()
    monkeypatch.setenv("CEVIRI_KALITE", "1")
    monkeypatch.setattr(translate, "_gemini_fabrikasi", lambda key: object())
    def uret(*args, **kwargs):
        if kwargs.get("system") == q.DENETIM_TALIMATI:
            return SimpleNamespace(text="{}", candidates=[SimpleNamespace(finish_reason="MAX_TOKENS")]), "m"
        return cevap({"translation": "[[1]] Sunny kıyıya çıktı.", "detected_names": [], "detected_terms": {}}), "m"
    monkeypatch.setattr(translate, "_generate_with_fallback", uret)
    sonuc = translate.translate_chapter("Sunny reached the shore.", "test", models=("m",))
    assert sonuc["translation"] == "Sunny kıyıya çıktı."
    assert sonuc["ceviri_kalitesi"]["durum"] == "denetlenemedi"
    assert sonuc["ceviri_kalitesi"]["neden"]
