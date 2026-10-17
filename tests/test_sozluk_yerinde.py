"""sozluk_yerinde: eski çeviride karşılık değiştirme ve yer tutucu şablonu."""
from core import sozluk_yerinde as sy
from core import translate


def _yaz(tr, en, kaynak, eski, yeni):
    return sy.yeniden_yaz(tr, en, translate._term_regex(kaynak), eski, yeni)


def test_kaynakta_gecen_paragrafta_ek_yeni_koke_uyar():
    tr = ["Kovan Dağı'na tırmandılar.", "Kovan Dağında rüzgâr vardı."]
    en = ["They climbed Hollow Mountain.", "There was wind on Hollow Mountain."]
    cikti, oz = _yaz(tr, en, "Hollow Mountain", "Kovan Dağı", "Oyuk Dağı")
    assert cikti == ["Oyuk Dağı'na tırmandılar.", "Oyuk Dağında rüzgâr vardı."]
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
    assert sy.doldur(sab[0], {0: "Oyuk Kale"}) == "Oyuk Kaleye vardılar."


def test_yer_tutucu_siradan_sozcugu_belirtece_cevirmez():
    # "güçlü" karşılığı olan kayıt, İngilizce paragrafta terim yoksa aranmaz.
    tr = ["Güçlü bir rüzgâr esti."]
    sab, say = _sablon(tr, ["A strong wind blew."], [("Mighty", "Güçlü")])
    assert sab == tr and say["belirtec"] == 0
