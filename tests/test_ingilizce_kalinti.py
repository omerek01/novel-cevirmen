"""Çevrilmeden İNGİLİZCE kalan paragrafların denetimi ve onarımı.

Ölçülen arıza (2026-09-05, shadow-slave önbelleği): hizalama TUTTUĞU hâlde tek
tek paragraflar İngilizce dönüyor ve boru hattında bunu gören hiçbir denetim
yok — çeviri kalıcı önbelleğe yazılıyor, önbellek isabeti bir daha çeviri
tetiklemediği için kullanıcı o paragrafı SONSUZA DEK İngilizce görüyor.

Vakalar (hepsi gemini-3.5/3.6-flash, hepsi cümle-başı işlev sözcüğüyle başlıyor):
  #179 p51  "But seriously. How did you survive, Sunny?"   (tam)
  #181 p56  Then, suppressing laughter, she said:           (tam)
  #188 p46  "But to me, it's a paradise."                   (tam)
  #177 p41  Was Neph... teğmenlerden biriyle mi çalışıyordu? (kısmî)
  #194 p41  ...But sadece birkaç dakika sonra, ...           (kısmî)
  #58  p26  ... Sunny and Nephis aralarında ...              (kısmî)

Denetçi 21.411 gerçek paragrafta kalibre edildi: 6 gerçek vaka, 0 yanlış pozitif.
Ağa çıkmaz.
"""
import pytest

from core import translate


# ---------- denetçi: yakalaması GEREKENLER ----------

def test_tam_ingilizce_paragraf_yakalanir():
    """Kaynakla birebir aynı dönen paragraf = hiç çevrilmemiş."""
    kalinti = translate.ingilizce_kalinti(
        ["Sunny başını salladı.", '"But to me, it\u2019s a paradise."'],
        ["Sunny nodded.", '"But to me, it\u2019s a paradise."'],
    )
    assert set(kalinti) == {1}


def test_cumle_basi_kalinti_yakalanir():
    """Kısmî vaka: model çevirmiş ama baştaki İngilizce bağlacı silmemiş."""
    kalinti = translate.ingilizce_kalinti(
        ["...But sadece birkaç dakika sonra, bu sözleri sesli düşündüğü için pişman oldu."],
        ["...But just a few minutes later, he bitterly regretted thinking those words aloud."],
    )
    assert set(kalinti) == {0}


def test_cumle_ici_baglac_kalintisi_yakalanir():
    """`Sunny and Nephis` — iki özel ad ARASINDA kalan bağlaç da sızıntıdır."""
    kalinti = translate.ingilizce_kalinti(
        ["Bunca zamandan sonra, Sunny and Nephis sessiz bir anlayış geliştirmişti."],
        ["After all this time, Sunny and Nephis developed a silent understanding."],
    )
    assert set(kalinti) == {0}


def test_yardimci_fiil_kalintisi_yakalanir():
    """`Was Neph...` — Türkçede eke dönüşen yardımcı fiil olduğu gibi kalmış."""
    kalinti = translate.ingilizce_kalinti(
        ["Was Neph... teğmenlerden biriyle mi çalışıyordu?"],
        ["Was Neph... working with one of the lieutenants?"],
    )
    assert set(kalinti) == {0}


# ---------- denetçi: yakalamaması GEREKENLER (kalibrasyonda ölçülen YP'ler) ----------

def test_duzgun_ceviri_yakalanmaz():
    kalinti = translate.ingilizce_kalinti(
        ["Sunny karanlık koridorda ilerledi ve kapıyı araladı."],
        ["Sunny moved down the dark corridor and pushed the door ajar."],
    )
    assert kalinti == {}


def test_kisa_unlem_yakalanmaz():
    """`"Sunny! Sunny! Uyan!"` — özel ad + ünlem; oran yüksek ama çeviri DOĞRU."""
    kalinti = translate.ingilizce_kalinti(
        ['"Sunny! Sunny! Uyan!"', "'...Ne?'", "Dang! Dang! Dang!"],
        ['"Sunny! Sunny! Wake up!"', "'...What?'", "Dang! Dang! Dang!"],
    )
    assert kalinti == {}


def test_ozel_ad_icindeki_islev_sozcugu_yakalanmaz():
    """`Glorious Will` bir silah adı — `Will` sızıntı değil (çeviride BÜYÜK harfli)."""
    kalinti = translate.ingilizce_kalinti(
        ["Glorious Will, altın bir parıltı yayan altın rengi bir büyük kılıçtı."],
        ["Glorious Will was a golden greatsword that emitted a golden glow."],
    )
    assert kalinti == {}


def test_sozlukteki_ad_icindeki_islev_sozcugu_yakalanmaz():
    """`Auro of the Nine` sözlükte İngilizce korunuyor — içindeki `the` sızıntı değil."""
    kalinti = translate.ingilizce_kalinti(
        ["Karşılaştığı en tehlikeli şey tirandı, ardından Auro of the Nine geliyordu."],
        ["The most dangerous thing he met was the tyrant, then Auro of the Nine."],
        glossary={"Auro of the Nine": "Auro of the Nine"},
    )
    assert kalinti == {}


def test_turkce_esseslier_yakalanmaz():
    """`not` (kayıt), `has` (kendine has) Türkçe sözcüklerdir — ölçüt onları elemeli."""
    kalinti = translate.ingilizce_kalinti(
        ["Sunny onun kendine has savaş tarzını not etmişti."],
        ["Sunny had noted his peculiar fighting style, which has its own logic."],
    )
    assert kalinti == {}


def test_hizasiz_cift_denetlenmez():
    """Paragraf sayıları tutmuyorsa ölçüt uygulanamaz; sessizce boş döner."""
    assert translate.ingilizce_kalinti(["a"], ["a", "b"]) == {}


# ---------- SAYI sözcükleri (2026-09-05, kullanıcı bildirimi) ----------
#
# `ten times` -> `ten kat`: model "times"ı çevirmiş, "ten"i bırakmış. Sayı
# sözcükleri `ISLEV_SOZCUKLERI`'ne giremezdi çünkü `ten` Türkçede de bir sözcük
# (cilt) ve liste kuralı "Türkçe yazımı olan girmez" diyor. Ölçüm (21.411
# paragraf) bu sınıfın AYRI ele alınabileceğini gösterdi: sayı sözcüklerinin
# 112 geçişinin TAMAMI özel ad parçasıydı (`Solitary Nine`, `Ninth Heaven`,
# `Thousand Transformations`) ve hepsi BÜYÜK harfliydi; tek gerçek sızıntı
# küçük harfliydi.

def test_sayi_sozcugu_kalintisi_yakalanir():
    """`ten kat` — sayı İngilizce kalmış, ölçü sözcüğü çevrilmiş (gerçek vaka #201)."""
    kalinti = translate.ingilizce_kalinti(
        ["Bir İblis, bir Canavar'dan biraz daha güçlü olsa bile ten kat daha tehlikeliydi."],
        ["A demon, even if only slightly stronger than a monster, was ten times more dangerous."],
    )
    assert set(kalinti) == {0}


def test_ozel_addaki_sayi_yakalanmaz():
    """`Solitary Nine` bir karakter adı — büyük harfli, cümle ortasında."""
    kalinti = translate.ingilizce_kalinti(
        ["Saldırıyı gören Solitary Nine bir spiral sıçrayış yaptı."],
        ["Seeing the attack, Solitary Nine performed a spiral leap."],
    )
    assert kalinti == {}


def test_cumle_basindaki_ozel_ad_sayisi_yakalanmaz():
    """`Nine Dragons Emperor` cümle başında: büyük harf ayırt etmez, SONRAKİ sözcük eder.

    Guard YALNIZ sayı sınıfına uygulanır. İşlev sözcüklerine uygulanamaz: gerçek
    vaka `Was Neph...` tam olarak "sonraki sözcük büyük harfli" desenindedir ve
    aynı guard onu sessizce elerdi.
    """
    kalinti = translate.ingilizce_kalinti(
        ["Nine Dragons Emperor ile olan anlaşmam bozulmayacak."],
        ["My deal with the Nine Dragons Emperor will not be broken."],
    )
    assert kalinti == {}


def test_turkce_ten_yakalanmaz():
    """`ten` Türkçede cilt demek; kaynakta sayı olarak geçmiyorsa sızıntı değil."""
    kalinti = translate.ingilizce_kalinti(
        ["Gördüğü ilk şey beyaz bir ten oldu, bolca ten."],
        ["The first thing he saw was white skin... a lot of skin."],
    )
    assert kalinti == {}


def test_siraya_ait_sayi_ozel_adda_yakalanmaz():
    """`Ninth Heaven` bir lonca adı — sıra sayıları da aynı guard'a tabi."""
    kalinti = translate.ingilizce_kalinti(
        ["Melody ve diğer Ninth Heaven üyeleri şaşkına döndü."],
        ["Melody and the other Ninth Heaven members were stunned."],
    )
    assert kalinti == {}


# ---------- prompt: önleme katmanı ----------

def test_prompt_ingilizce_birakmayi_yasaklar():
    """Kural prompt'ta AÇIKÇA olmalı — bugün hiçbir madde bunu söylemiyor."""
    # NOT: `.lower()` KULLANMA — Python Türkçe "İ"yi "i̇" (i + birleşik
    # nokta) yapar ve "ingilizce" araması sessizce tutmaz.
    metin = translate.SYSTEM_INSTRUCTION
    assert "İngilizce BIRAKMA" in metin
    assert "KOPYALAMA" in metin


# ---------- kalıcılık: bayrak DB'ye gidip geri gelmeli ----------

def test_bayrak_cache_gidis_donus():
    """Bayrak `save_chapter` -> `get_chapter` turunda kaybolmamalı.

    Bu projede künye alanları bir kez tam böyle kaybolmuştu: `model` yalnız BİR
    yazma noktasındaydı ve öteki yoldan gelen bölüm hangi halkanın çevirdiğini
    söyleyemiyordu. Bayrağı üreten her noktanın kalıcılığı tel tuzağıyla tutulur.
    """
    from core import cache

    cache.save_chapter("u://1", {
        "translation": "tr", "source": "en", "book_slug": "k",
        "ingilizce_kalinti": {3: "But seriously."},
    })
    assert cache.get_chapter("u://1")["ingilizce_kalinti"] == {"3": "But seriously."}


def test_bayrak_kunyesiz_guncellemede_silinmez():
    """Künye TAŞIMAYAN bir payload aynı satırı güncelleyince bayrak NULL'a düşmemeli.

    E-16 sınıfı hata: `COALESCE(excluded.x, x)` olmadan, çevrilecek metni olmayan
    görsel sayfa gibi künyesiz bir yazma mevcut bayrağı sessizce siliyordu.
    """
    from core import cache

    cache.save_chapter("u://2", {
        "translation": "tr", "source": "en", "book_slug": "k",
        "ingilizce_kalinti": {0: "Then, she said:"},
    })
    cache.save_chapter("u://2", {"translation": "tr2", "book_slug": "k"})
    assert cache.get_chapter("u://2")["ingilizce_kalinti"] == {"0": "Then, she said:"}


def test_set_ingilizce_kalinti_yalniz_bayraga_dokunur():
    """Geriye dönük işaretleme çevirinin ya da künyenin üzerine YAZMAMALI."""
    from core import cache

    cache.save_chapter("u://3", {
        "translation": "tr", "source": "en", "book_slug": "k", "model": "m",
    })
    assert cache.set_ingilizce_kalinti("u://3", {1: "But to me."})
    satir = cache.get_chapter("u://3")
    assert satir["ingilizce_kalinti"] == {"1": "But to me."}
    assert satir["translation"] == "tr"
    assert satir["model"] == "m"
    assert not cache.set_ingilizce_kalinti("u://yok", {})
