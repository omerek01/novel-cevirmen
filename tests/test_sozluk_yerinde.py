"""sozluk_yerinde: eski çeviride karşılık değiştirme ve yer tutucu şablonu."""
from core import sozluk_yerinde as sy
from core import translate


def _yaz(tr, en, kaynak, eski, yeni):
    return sy.yeniden_yaz(tr, en, translate._term_regex(kaynak), eski, yeni)


def test_kaynakta_gecen_paragrafta_ek_yeni_koke_uyar():
    tr = ["Kovan Dağı'na tırmandılar.", "Kovan Dağında rüzgâr vardı."]
    en = ["They climbed Hollow Mountain.", "There was wind on Hollow Mountain."]
    cikti, oz = _yaz(tr, en, "Hollow Mountain", "Kovan Dağı", "Oyuk Dağı")
    # Özel ada gelen ek kesmeyle ayrılır (TDK): özgün kesmesiz yazım yeni adda düzelir.
    assert cikti == ["Oyuk Dağı'na tırmandılar.", "Oyuk Dağı'nda rüzgâr vardı."]
    assert oz.degisen == 2 and not oz.belirsiz


def test_kaynakta_olmayan_paragraf_degismez():
    # Aynı Türkçe sözcük terimin karşılığı değilse (İngilizcede terim yok) dokunulmaz.
    tr = ["Arıların kovanı boştu."]
    en = ["The bees' hive was empty."]
    cikti, oz = _yaz(tr, en, "Hollow", "kovan", "oyuk")
    assert cikti == tr and oz.belirsiz == ["kaynakta_yok"]


def test_cok_anlamli_ek_belirsiz_kalir():
    tr = ["Kovanı gördü."]
    en = ["He saw the Hollow."]
    cikti, oz = _yaz(tr, en, "Hollow", "Kovan", "Kale")
    assert cikti == tr and oz.belirsiz == ["cok_anlamli"]


def test_hizasiz_bolum_degismez():
    cikti, oz = _yaz(["Kovan'a gitti.", "x"], ["He went to the Hollow."], "Hollow", "Kovan", "Oyuk")
    assert cikti == ["Kovan'a gitti.", "x"] and oz.belirsiz == ["hizasiz"]


def test_buyuk_harf_ve_kivrik_kesme_korunur():
    tr = ["KOVAN’A!"]
    en = ["TO THE HOLLOW!"]
    cikti, _ = _yaz(tr, en, "Hollow", "Kovan", "Oyuk")
    assert cikti == ["OYUK’A!"]


def _sablon(tr, en, kayit):
    kayitlar = {i: k for i, k in enumerate(kayit)}
    desenler = {i: translate._term_regex(s) for i, (s, _t) in kayitlar.items()}
    return sy.sablon_bolum(tr, en, kayitlar, desenler)


def test_yer_tutucu_geri_doldurma_birebir():
    tr = ["Yaratıkların arasından Sunny’nin sesi geldi.", "Kovan Dağına vardılar."]
    en = ["Sunny's voice came from among the creatures.", "They reached Hollow Mountain."]
    kayit = [("creature", "yaratık"), ("Sunny", "Sunny"), ("Hollow Mountain", "Kovan Dağı")]
    sab, say = _sablon(tr, en, kayit)
    assert say["belirtec"] == 3
    assert "⟦" in sab[0] and "Kovan" not in sab[1]
    karsiliklar = {i: t for i, (_s, t) in enumerate(kayit)}
    assert [sy.doldur(p, karsiliklar) for p in sab] == tr


def test_yer_tutucu_yeni_karsilikla_dolar():
    tr = ["Kovan Dağına vardılar."]
    sab, _ = _sablon(tr, ["They reached Hollow Mountain."], [("Hollow Mountain", "Kovan Dağı")])
    assert sy.doldur(sab[0], {0: "Oyuk Kale"}) == "Oyuk Kale'ye vardılar."


def test_yer_tutucu_siradan_sozcugu_belirtece_cevirmez():
    # "güçlü" karşılığı olan kayıt, İngilizce paragrafta terim yoksa aranmaz.
    tr = ["Güçlü bir rüzgâr esti."]
    sab, say = _sablon(tr, ["A strong wind blew."], [("Mighty", "Güçlü")])
    assert sab == tr and say["belirtec"] == 0


def test_turkce_karsiliktan_ingilizce_ada_gecis_kesme_ve_soylenis():
    # Hakem ölçümünde yanlış çıkan sınıf: Şövalye -> Knight (Knight'ı); çokluk eki
    # yabancı adda da kesmesiz (TDK; hakem 2026-10-18).
    tr = ["Şövalyeyi gördü.", "Şövalyelerden kaçtı."]
    en = ["He saw the Knight.", "He fled from the Knights."]
    cikti, oz = _yaz(tr, en, "Knight", "Şövalye", "Knight")
    assert cikti == ["Knight'ı gördü.", "Knightlardan kaçtı."] and oz.degisen == 2


def test_kitaptan_ogrenilen_uyum_kuraldan_once_gelir():
    uyum = sy.Uyum(["Reaper'ı gördü. Reaper'ın sesi. Reaper'a gitti."])
    assert uyum.unlu("Reaper") == "ı"
    cikti, _ = sy.yeniden_yaz(["Biçici'ye gitti."], ["He went to the Reaper."],
                              translate._term_regex("Reaper"), "Biçici", "Reaper", uyum=uyum)
    assert cikti == ["Reaper'a gitti."]


def test_tek_taniktan_uyum_ogrenilmez():
    assert sy.Uyum(["Reaper'e."]).unlu("Reaper") is None


def test_baslik_bicimi_korunur():
    cikti, _ = _yaz(["Kasvetli Gölgeyle döndü."], ["He returned with the gloomy shadow."],
                    "gloomy shadow", "kasvetli gölge", "karanlık gölge")
    assert cikti == ["Karanlık Gölgeyle döndü."]


def test_karisik_sozcuk_bicimi_geri_doldurmada_korunur():
    # Canlı ölçümde 4 paragraf: model kaydın bir sözcüğünü küçük yazmış ("ilk Lord'a",
    # "Demir El adasında"). "İlk harf büyük" sınıfı bunu "İlk lord'a" diye geri veriyordu.
    tr = ["Taht ilk Lord'a aitti.", "Gece dördüncü Kabus bitti.", "Eski Demir El adasında kaldı."]
    en = ["The throne belonged to the First Lord.", "The Fourth Nightmare ended at night.",
          "He stayed on Iron Hand Island of old."]
    kayit = [("First Lord", "İlk Lord"), ("Fourth Nightmare", "Dördüncü Kabus"),
             ("Iron Hand Island", "Demir El Adası")]
    sab, say = _sablon(tr, en, kayit)
    karsiliklar = {i: t for i, (_s, t) in enumerate(kayit)}
    assert [sy.doldur(p, karsiliklar) for p in sab] == tr
    assert say["belirtec"] == 3


def test_karisik_bicim_yeni_karsilikta_sozcuk_sayisi_tutunca_uygulanir():
    sab, _ = _sablon(["Taht ilk Lord'a aitti."], ["It belonged to the First Lord."],
                     [("First Lord", "İlk Lord")])
    assert sy.doldur(sab[0], {0: "Birinci Usta"}) == "Taht birinci Usta'ya aitti."


def test_geri_doldurmayi_bozacak_gecis_belirtece_cevrilmez():
    # Sözcük içi büyük harf hiçbir biçim sınıfına uymaz: metin olduğu gibi kalır.
    tr = ["Taht İLk Lord'a aitti."]
    sab, say = _sablon(tr, ["It belonged to the First Lord."], [("First Lord", "İlk Lord")])
    assert sab == tr and say["belirtec"] == 0 and say["cok_anlamli_kalan"] == 1


def test_ozel_ada_cokluk_eki_kesmesiz_gelir():
    # TDK: özel ada gelen çokluk eki ve ardındaki ekler kesmeyle ayrılmaz (Türkler,
    # Ahmetlerden). Hakem ölçümünde 13/19 yanlış bu sınıftı: İblis'lerle, Titan'lar.
    tr = ["Şeytanlarla savaştı.", "Şeytanı gördü."]
    en = ["He fought the daemons.", "He saw the daemon."]
    cikti, oz = _yaz(tr, en, "daemon", "Şeytan", "İblis")
    assert cikti == ["İblislerle savaştı.", "İblis'i gördü."] and oz.degisen == 2


def test_eslesmenin_ardinda_kesmeli_ek_kalirsa_belirsiz():
    # "Şövalyesi'nden": eşleşme kesmede biter, "'nden" dışarıda kalır; yazılsa
    # "Knight'ı'nden" (çift kesme, uyumsuz ek) çıkıyordu.
    tr = ["Klanın iki Şövalyesi'nden biri geldi."]
    cikti, oz = _yaz(tr, ["One of the clan's two Knights came."], "Knight", "Şövalye", "Knight")
    assert cikti == tr and oz.belirsiz == ["kesme_sonrasi"]


def test_tekil_cogul_karsilik_degisimi_belirsiz():
    # "Kayıplar" -> "Kayıp": çoğul anlamı mı kalmalı tekile mi dönmeli, metinden bilinmez.
    tr = ["Kayıplar'ın çoğu döndü."]
    cikti, oz = _yaz(tr, ["Most of the Lost returned."], "Lost", "Kayıplar", "Kayıp")
    assert cikti == tr and oz.belirsiz == ["cogul_uyumsuz"]


def test_kitaptan_ogrenilen_ayni_unlu_cokluk_kesmesini_geri_getirmez():
    # Canlı ölçümde kural tutmadı: kitap "İblis'i" yazdığı için uyum "i" öğreniyor ve kök
    # söyleniş ünlülü kuruluyor; çokluk kesmesi buna bakmamalı.
    uyum = sy.Uyum(["İblis'i gördü. İblis'in sesi. İblis'e gitti."])
    cikti, _ = sy.yeniden_yaz(["Şeytanlarla savaştı."], ["He fought the daemons."],
                              translate._term_regex("daemon"), "Şeytan", "İblis", uyum=uyum)
    assert cikti == ["İblislerle savaştı."]



def test_ayni_bas_sozcukte_yalniz_onceki_sozcukler_degisir():
    # Son sözcük aynıysa ek ona bağlı kalır: kesmeli ikinci ek ve çoğul da korunur.
    tr = ["Kovan Dağları'nın eteğine vardılar.", "KOVAN DAĞI'NA!", "Kader İblisinin sesi."]
    en = ["They reached the foot of the Hollow Mountains.", "TO HOLLOW MOUNTAIN!",
          "The voice of the Demon of Destiny."]
    cikti, oz = _yaz(tr[:2], en[:2], "Hollow Mountain", "Kovan Dağı", "Oyuk Dağı")
    assert cikti == ["Oyuk Dağları'nın eteğine vardılar.", "OYUK DAĞI'NA!"]
    assert oz.degisen == 2 and not oz.belirsiz
    cikti, oz = _yaz(tr[2:], en[2:], "Demon of Destiny", "Kader İblisi", "Yazgı İblisi")
    # Genel yol ayrıştırabildiği geçişte önceliklidir (özel ad kesmesi de gelir).
    assert cikti == ["Yazgı İblisi'nin sesi."] and oz.degisen == 1


def test_bas_sozcuk_degisince_kesme_sonrasi_belirsiz_kalir():
    tr = ["Kovan Dağları'nın eteğine vardılar."]
    en = ["They reached the foot of the Hollow Mountains."]
    cikti, oz = _yaz(tr, en, "Hollow Mountain", "Kovan Dağı", "Oyuk Tepe")
    assert cikti == tr and oz.belirsiz == ["kesme_sonrasi"]
