"""Sözlük uyum denetimi: çeviri, sözlükteki karşılığa fiilen uydu mu?

Sebep ÖLÇÜLDÜ (2026-08-30, Shadow Slave'in önbellekteki 110 bölümü taranarak):
zincirin halkaları sözlük kuralına EŞİT uymuyor. Türkçe karşılığı kayıtlı olup
çeviride İngilizce kalan terim oranı:

    gemini-3.6-flash        1353 terim -> 9 kaçak    (%0,7)
    gemini-3.5-flash        1030 terim -> 3 kaçak    (%0,3)
    gemini-3.5-flash-lite    117 terim -> 28 kaçak   (%23,9)

Somut vaka: 109. bölümü flash-lite çevirdi; `Saint -> Aziz` kaynakta 12 kez
geçiyordu ve 12'si de İngilizce kaldı. Zincir yalnız ERİŞİLEBİLİRLİĞE bakarak
iniyor, kaliteyi hiçbir yerde ölçmüyordu; lite'ın çevirisi sessizce kalıcı
önbelleğe yazılıp bir daha kontrol edilmiyordu.

Denetim deterministiktir ve API çağırmaz — çeviriden sonra bedavaya koşar.
"""
import pytest

from core import translate


def test_ceviride_ingilizce_kalan_terim_ihlaldir():
    """Asıl vaka: karşılığı kayıtlı ama model kuralı uygulamamış."""
    ihlal = translate.sozluk_ihlalleri(
        {"Saint": "Aziz"},
        kaynak="The Saint raised his hand.",
        ceviri="Saint elini kaldırdı.",
    )
    assert ihlal == {"Saint": "Aziz"}


def test_karsiligi_uygulanmis_terim_ihlal_degil():
    ihlal = translate.sozluk_ihlalleri(
        {"Saint": "Aziz"},
        kaynak="The Saint raised his hand.",
        ceviri="Aziz elini kaldırdı.",
    )
    assert ihlal == {}


def test_ingilizce_korunan_ad_ihlal_sayilmaz():
    """`X -> X` kayıtları (karakter adları) İngilizce kalmak ZORUNDA — denetimin
    konusu değil. Sayılsaydı her bölümde onlarca sahte ihlal üretirdi."""
    ihlal = translate.sozluk_ihlalleri(
        {"Nephis": "Nephis"},
        kaynak="Nephis stood there.",
        ceviri="Nephis orada duruyordu.",
    )
    assert ihlal == {}


def test_kaynakta_gecmeyen_terim_ihlal_degil():
    """Sözlükte kayıtlı ama bu bölümde hiç geçmeyen terim denetime girmez."""
    ihlal = translate.sozluk_ihlalleri(
        {"Saint": "Aziz"},
        kaynak="He raised his hand.",
        ceviri="Elini kaldırdı.",
    )
    assert ihlal == {}


def test_cogul_kaydedilmis_terim_tekil_gecise_de_bakar():
    """`_terim_metinde` çoğul esnekliğiyle aynı ölçüt: `tyrants` kaydı `tyrant`
    tekilini de kapsar (bkz. test_sozluk_koken.py). Denetim de aynı ölçütü
    kullanmalı, yoksa prompt'a giren bir terim denetimden kaçardı."""
    ihlal = translate.sozluk_ihlalleri(
        {"tyrants": "Tiranlar"},
        kaynak="The tyrant laughed.",
        ceviri="The tyrant güldü.",
    )
    assert ihlal == {"tyrants": "Tiranlar"}


def test_yazim_varyanti_ceviride_kalirsa_yakalanir():
    """Kaynak `Ore-Empire` yazsa da kayıt `Ore Empire`; ayırıcıya toleranslı desen
    ikisini de görür (bkz. `_term_regex`)."""
    ihlal = translate.sozluk_ihlalleri(
        {"Ore Empire": "Ork İmparatorluğu"},
        kaynak="The Ore-Empire fell.",
        ceviri="The Ore-Empire düştü.",
    )
    assert ihlal == {"Ore Empire": "Ork İmparatorluğu"}


def test_karsiligi_kaynagi_iceren_kayit_ihlal_uretmez():
    """Karşılığın İÇİNDE kaynak geçiyorsa (`Ore Empire -> Ore Empire Krallığı`)
    doğru çeviri bile deseni tetikler — denetim o kaydı ölçemez, sahte ihlal
    üretmek yerine atlar. Aksi hâlde her bölümde kalıcı bir yanlış-pozitif olurdu."""
    ihlal = translate.sozluk_ihlalleri(
        {"Ore Empire": "Ore Empire Krallığı"},
        kaynak="The Ore Empire fell.",
        ceviri="Ore Empire Krallığı düştü.",
    )
    assert ihlal == {}


def test_bos_sozluk_ve_bos_metin_cokmez():
    assert translate.sozluk_ihlalleri({}, kaynak="a", ceviri="b") == {}
    assert translate.sozluk_ihlalleri({"X": "Y"}, kaynak="", ceviri="") == {}
    assert translate.sozluk_ihlalleri(None, kaynak="a", ceviri="b") == {}


def test_hizalanmamis_bolumde_kaynak_yoksa_denetim_bos_doner():
    """Hizalama tutmazsa `source` None döner (iki-dilli devre dışı). Denetim
    kaynağı olmayan bölümde ölçüm yapamaz; çökmek yerine boş dönmeli."""
    assert translate.sozluk_ihlalleri({"Saint": "Aziz"}, kaynak=None, ceviri="x") == {}
