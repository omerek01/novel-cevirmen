"""Yasak karşılık çeviriden sonra da denetlenir (canlı vaka 2026-11-10, shadow-slave 1642).

`Saint -> Aziz` koşullu kayıtken "Saint Cassia" "Azize Cassie" çevrildi; koşullu kayıtlar
denetim dışı olduğu için kimse görmedi. Yasak bağlamdan bağımsızdır: koşullu kayıtta da
ihlal sayılır ve onarım turuna girer. `Azize` aynı zamanda `Aziz`in yönelme hâlidir, o
yüzden yalnız kesin biçimler (ad önünde unvan, ek almış) sayılır.
"""
from core import translate

SOZLUK = {"Saint": "Aziz", "Great": "Ulu"}
KOSUL = {
    "Saint": 'Sunny yankısı için Saint olacak. ; YASAK KARŞILIK: "Azize"',
    "Great": 'YASAK KARŞILIK: "Büyük"',
}


def _ihlal(en, tr):
    return translate.sozluk_ihlalleri(SOZLUK, en, tr, KOSUL)


def test_ad_onunde_yasak_unvan_ihlaldir_kosullu_kayitta_da():
    assert _ihlal("That question is better aimed at you, Saint Cassia.",
                  "Bu soruyu sana yöneltmek daha doğru olur, Azize Cassie.") == {"Saint": "Aziz"}
    assert _ihlal("Saint Tyris of the White Feather fell.",
                  "Beyaz Tüy klanının Azizesi Tyris düştü.") == {"Saint": "Aziz"}


def test_yonelme_hali_ve_dogru_karsilik_ihlal_degildir():
    assert _ihlal("Sunny stared at the mighty Saint.", "Sunny kudretli Azize bakakaldı.") == {}
    assert _ihlal("Song now possessed nine Saints.", "Song artık dokuz Azize sahipti.") == {}
    assert _ihlal("You, Saint Cassia.", "Sen, Aziz Cassie.") == {}


def test_kaynakta_gecmeyen_terimin_yasagi_aranmaz():
    assert _ihlal("Cassia smiled.", "Azize Cassie gülümsedi.") == {}


def test_belirsiz_olmayan_yasak_her_geciste_ihlaldir():
    assert _ihlal("The Great Clan arrived.", "Büyük Klan geldi.") == {"Great": "Ulu"}
    assert _ihlal("The Great Clan arrived.", "Ulu Klan geldi.") == {}


def test_paragraf_tespiti_onarima_yasakli_paragrafi_verir():
    en = ["Saint Cassia nodded.", "Sunny stared at the mighty Saint."]
    tr = ["Azize Cassie başını salladı.", "Sunny kudretli Azize bakakaldı."]
    assert translate.sozluk_ihlali_paragraflari(SOZLUK, tr, en, KOSUL) == {0: {"Saint": "Aziz"}}
