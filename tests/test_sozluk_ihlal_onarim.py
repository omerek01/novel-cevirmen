"""Sözlük ihlalinin OTOMATİK onarımı + koşullu kayıtların denetim dışılığı.

Ölçülen arıza (2026-09-11, shadow-slave #376/#378/#380/#381): `Saint -> Aziz`
sözlükte kayıtlı, `_terim_metinde` prompt'a girdiğini doğruluyor, buna rağmen
model terimi bölümden bölüme farklı çeviriyor — 379/380'de "Aziz",
376/378/381'de "Saint". Kök neden PROMPT'taydı: SYSTEM_INSTRUCTION "İngilizce
korunacak TEK sınıf: bir KİŞİYİ ADLANDIRAN ifadeler" diyor ve
İngilizce-bırakma yasağına "Tek istisna yukarıdaki KİŞİ ADLARI kuralıdır" diye
açık bir KAÇIŞ KAPISI koyuyordu. Sözlüğün o istisnayı ezip ezmediği hiçbir
yerde yazmıyordu; model `Saint`'i bir varlığın adı gördüğü an kapıdan
çıkıyordu. Aynı prompt sistem terimleri için önceliği AÇIKÇA söylüyor
("SÖZLÜK'te farklı bir karşılık verilmişse SÖZLÜK geçerlidir") — çalışan
örnekle bozuk örnek arasındaki fark tam buydu.

İkinci katman: ihlal TESPİT ediliyordu (`glossary_leaks` künyeye yazılır,
okuyucuda ⚠ çıkar) ama kimse ONARMIYORDU. Bölüm kalıcı önbelleğe yazılıyor,
önbellek isabeti bir daha çeviri tetiklemediği için kullanıcı o terimi
SONSUZA DEK İngilizce görüyordu. Onarım deseni `_kalintiyi_onar`'dan alınır:
TEK tur, YALNIZ ihlalli paragraflar.

Üçüncü katman: KOŞULLU kayıtlar denetimin ve onarımın DIŞINDADIR. `Saint ->
Aziz [KOŞUL: rütbe anlamında]` kayıtlıyken terim gölge kölesinin ADI olarak
geçip İngilizce kaldığında bu DOĞRU çeviridir; koşulun sağlanıp sağlanmadığı
deterministik olarak ölçülemez. Koşulu yok sayan bir denetim önce sahte bir ⚠
üretir, sonra otomatik onarım doğru bırakılmış özel adı ZORLA çevirirdi.

Ağa çıkmaz — `_generate_with_fallback` sahtelenir.
"""
import json

from core import pipeline, translate


def _yanit(ceviri: str):
    """Gemini yanıtı taklidi: `.text` alanında JSON taşır."""

    class _Y:
        text = json.dumps({"translation": ceviri, "detected_names": []})

    return _Y()


def _kur(monkeypatch, yanitlar: list[str], cagrilar: list[str]):
    """`_generate_with_fallback`'i sırayla `yanitlar`ı dönecek şekilde sahtele."""

    def sahte(client_factory, models, user, system=None, max_tokens=None):
        cagrilar.append(user)
        i = min(len(cagrilar) - 1, len(yanitlar) - 1)
        return _yanit(yanitlar[i]), "gemini-3.5-flash"

    monkeypatch.setattr(translate, "_generate_with_fallback", sahte)
    monkeypatch.setattr(translate.genai, "Client", lambda api_key=None: object())


KAYNAK = (
    "The Saint raised his hand.\n\n"
    "Sunny watched the empty sky.\n\n"
    "Many Saints gathered below."
)
SOZLUK = {"Saint": "Aziz"}
KOSUL = {"Saint": "yalnız rütbe anlamında; kişi/varlık adıysa İngilizce kalır"}


# --- Kök neden: prompt'ta sözlük, kişi-adı istisnasını EZER -----------------

def test_prompt_sozlugun_kisi_adi_istisnasini_ezdigini_soyler():
    """Tel tuzağı: öncelik cümlesi silinirse arıza sessizce geri gelir.

    Model `Saint`'i bir varlığın adı sayıp "İngilizce korunacak TEK sınıf"
    kuralına sığınıyordu. Sözlükte KENDİNDEN FARKLI bir karşılığı olan kayıt
    o istisnayı ezmelidir — kişi adları sözlükte kendi yazımıyla durduğu için
    (`Sunny -> Sunny`, `merge_names`) bu kural onları etkilemez.
    """
    s = translate.SYSTEM_INSTRUCTION
    assert "KİŞİ ADLARI istisnası" in s, (
        "sözlüğün kişi-adı istisnasını ezdiği prompt'ta yazmıyor — "
        "model kaçış kapısından çıkar (shadow-slave #378/#381)"
    )


# --- Koşullu kayıtlar denetim DIŞI -----------------------------------------

def test_kosullu_terim_ihlal_sayilmaz():
    """Koşul sağlanmadığında İngilizce kalmak DOĞRUDUR; ölçülemez, suçlanamaz."""
    ihlal = translate.sozluk_ihlalleri(
        SOZLUK,
        kaynak="He dismissed Saint into the shadows.",
        ceviri="Saint'i gölgelere geri gönderdi.",
        kosullar=KOSUL,
    )
    assert ihlal == {}


def test_kosulsuz_terim_hala_ihlal_sayilir():
    """Koşulsuz kayıt KURALDIR — eski davranış korunur."""
    ihlal = translate.sozluk_ihlalleri(
        SOZLUK,
        kaynak="The Saint raised his hand.",
        ceviri="Saint elini kaldırdı.",
    )
    assert ihlal == {"Saint": "Aziz"}


# --- Paragraf bazlı tespit (onarımın ön koşulu) ----------------------------

def test_ihlalli_paragrafin_indeksi_bulunur():
    """Onarım için hangi paragrafın bozuk olduğu TAM bilinmeli."""
    tr = [
        "Saint elini kaldırdı.",
        "Sunny boş gökyüzünü izledi.",
        "Aşağıda birçok Aziz toplandı.",
    ]
    en = KAYNAK.split("\n\n")
    assert translate.sozluk_ihlali_paragraflari(SOZLUK, tr, en) == {0: {"Saint": "Aziz"}}


def test_uyan_ceviride_ihlalli_paragraf_yok():
    tr = [
        "Aziz elini kaldırdı.",
        "Sunny boş gökyüzünü izledi.",
        "Aşağıda birçok Aziz toplandı.",
    ]
    en = KAYNAK.split("\n\n")
    assert translate.sozluk_ihlali_paragraflari(SOZLUK, tr, en) == {}


def test_kosullu_terim_paragraf_tespitinde_de_elenir():
    """Denetim ve onarım AYNI ölçütü kullanmalı; ayrışırsa onarım sahte
    ihlali "düzeltmeye" kalkar ve doğru bırakılmış özel adı bozar."""
    tr = [
        "Saint elini kaldırdı.",
        "Sunny boş gökyüzünü izledi.",
        "Aşağıda birçok Aziz toplandı.",
    ]
    en = KAYNAK.split("\n\n")
    assert translate.sozluk_ihlali_paragraflari(SOZLUK, tr, en, KOSUL) == {}


# --- Otomatik onarım (translate_chapter uçtan uca) -------------------------

def test_ihlalli_paragraf_otomatik_onarilir(monkeypatch):
    """Asıl vaka: terim İngilizce kaldı, ikinci hedefli tur onu Türkçeleştirir."""
    cagrilar: list[str] = []
    _kur(
        monkeypatch,
        [
            "[[1]] Saint elini kaldırdı.\n\n"
            "[[2]] Sunny boş gökyüzünü izledi.\n\n"
            "[[3]] Aşağıda birçok Aziz toplandı.",
            "[[1]] Aziz elini kaldırdı.",
        ],
        cagrilar,
    )

    out = translate.translate_chapter(KAYNAK, api_key="k", glossary=SOZLUK)

    assert out["translation"].split("\n\n")[0] == "Aziz elini kaldırdı."
    assert out["glossary_leaks"] == {}
    assert len(cagrilar) == 2, "tam bir onarım turu bekleniyor"
    # Onarım YALNIZ ihlalli paragrafı taşımalı — bölümün tamamını yeniden
    # göndermek her ihlali tam bölüm maliyetine (ücretli modelde PARAYA) çıkarır.
    assert "raised his hand" in cagrilar[1]
    assert "empty sky" not in cagrilar[1]


def test_onarilamayan_ihlal_kunyeye_yazilir(monkeypatch):
    """Model ikinci turda da uymazsa: TEK tur denenir, bayrak kalır (⚠ rozeti)."""
    cagrilar: list[str] = []
    _kur(
        monkeypatch,
        [
            "[[1]] Saint elini kaldırdı.\n\n"
            "[[2]] Sunny boş gökyüzünü izledi.\n\n"
            "[[3]] Aşağıda birçok Aziz toplandı.",
            "[[1]] Saint elini kaldırdı.",
        ],
        cagrilar,
    )

    out = translate.translate_chapter(KAYNAK, api_key="k", glossary=SOZLUK)

    assert out["glossary_leaks"] == {"Saint": "Aziz"}
    assert len(cagrilar) == 2, "onarım TEK tur olmalı — döngü maliyeti katlar"


def test_temiz_ceviride_onarim_turu_atilmaz(monkeypatch):
    """İhlal yoksa ikinci istek ATILMAZ — her bölüme ek maliyet bindirmez."""
    cagrilar: list[str] = []
    _kur(
        monkeypatch,
        [
            "[[1]] Aziz elini kaldırdı.\n\n"
            "[[2]] Sunny boş gökyüzünü izledi.\n\n"
            "[[3]] Aşağıda birçok Aziz toplandı."
        ],
        cagrilar,
    )

    out = translate.translate_chapter(KAYNAK, api_key="k", glossary=SOZLUK)

    assert out["glossary_leaks"] == {}
    assert len(cagrilar) == 1


def test_kosullu_terim_icin_onarim_turu_atilmaz(monkeypatch):
    """Koşullu kayıtta İngilizce kalmak doğru olabilir — onarım onu BOZARDI."""
    cagrilar: list[str] = []
    _kur(
        monkeypatch,
        [
            "[[1]] Saint elini kaldırdı.\n\n"
            "[[2]] Sunny boş gökyüzünü izledi.\n\n"
            "[[3]] Aşağıda birçok Aziz toplandı."
        ],
        cagrilar,
    )

    out = translate.translate_chapter(
        KAYNAK, api_key="k", glossary=SOZLUK, kosullar=KOSUL,
    )

    assert out["glossary_leaks"] == {}
    assert len(cagrilar) == 1, "koşullu terim onarım turu TETİKLEMEMELİ"
    assert out["translation"].split("\n\n")[0] == "Saint elini kaldırdı."


# --- Koşulsuz ÇOĞUL kayıt, koşullu TEKİLİN yerine geçmez ---------------------
# Ölçülen arıza (2026-09-23, sunucu): `Saints -> Azizler` (koşulsuz, otomatik)
# çoğul esnekliğiyle tekil "Saint"i de yakalıyordu. `Saints` bayrağı taşıyan 44
# bölümün 44'ünde çeviride gerçek bir "Saints" YOKTU — hepsi koşula uyularak
# DOĞRU korunmuş gölge adıydı. Her biri okuyucuda sahte ⚠ ve kotadan düşen
# gereksiz bir onarım isteği demekti; onarım da adı "Aziz"e zorlayabilirdi.

SOZLUK_CIFT = {"Saint": "Aziz", "Saints": "Azizler"}
KAYNAK_AD = (
    "She studied Saint's motionless figure.\n\n"
    "Sunny watched the empty sky."
)


def test_korunan_tekil_ad_cogul_kaydin_ihlali_sayilmaz():
    ihlal = translate.sozluk_ihlalleri(
        SOZLUK_CIFT,
        kaynak="She studied Saint's motionless figure.",
        ceviri="Saint'in hareketsiz bedenini inceledi.",
        kosullar=KOSUL,
    )
    assert ihlal == {}


def test_gercek_cogul_hala_denetlenir():
    """Düzeltme çoğul kaydı SUSTURMAZ: çoğul gerçekten İngilizce kaldıysa ihlaldir."""
    ihlal = translate.sozluk_ihlalleri(
        SOZLUK_CIFT,
        kaynak="Many Saints gathered below.",
        ceviri="Aşağıda birçok Saints toplandı.",
        kosullar=KOSUL,
    )
    assert ihlal == {"Saints": "Azizler"}


def test_tekil_sizinti_cift_kayitta_bir_kez_sayilir():
    """Koşulsuz çiftte de tekil sızıntı ÇOĞUL kaydına yazılmaz (ölçülen vaka:
    bölüm 654-655'te aynı sızıntı hem `Nightmare` hem `Nightmares` diye sayıldı)."""
    ihlal = translate.sozluk_ihlalleri(
        {"Nightmare": "Kabus", "Nightmares": "Kabuslar"},
        kaynak="In this harrowing Nightmare, it felt like home.",
        ceviri="Bu korkunç Nightmare içinde evinde gibiydi.",
    )
    assert ihlal == {"Nightmare": "Kabus"}


def test_korunan_tekil_ad_onarim_turu_tetiklemez(monkeypatch):
    """Uçtan uca: ad DOĞRU korunduysa ikinci istek ATILMAZ."""
    cagrilar: list[str] = []
    _kur(
        monkeypatch,
        [
            "[[1]] Saint'in hareketsiz bedenini inceledi.\n\n"
            "[[2]] Sunny boş gökyüzünü izledi."
        ],
        cagrilar,
    )

    out = translate.translate_chapter(
        KAYNAK_AD, api_key="k", glossary=SOZLUK_CIFT, kosullar=KOSUL,
    )

    assert out["glossary_leaks"] == {}
    assert len(cagrilar) == 1, "korunan ad sahte ihlalle onarım turu TETİKLEMEMELİ"


# --- Geriye dönük araç da AYNI ölçütü kullanır -----------------------------

def test_geriye_donuk_denetim_araci_kosullari_gecirir():
    """Statik tel tuzağı: `scripts/uyum_denetle.py` koşulları okumadan ölçerse
    koşullu kayıtlara sahte ihlal yazar ve `--uygula` o bayrakları DB'ye basar.

    Araç `translate.sozluk_ihlalleri`'ni çağırır; çeviri yolu koşulu eleyip
    araç elemezse aynı bölüm iki yerde farklı ölçülür — bu projede `model`
    künyesi tam olarak böyle ayrışmıştı.
    """
    import pathlib
    import re

    kaynak = pathlib.Path("scripts/uyum_denetle.py").read_text(encoding="utf-8")
    cagrilar = [m.end() for m in re.finditer(r"sozluk_ihlalleri\(", kaynak)]
    assert cagrilar, "araçta sozluk_ihlalleri çağrısı bulunamadı"
    eksik = [i for i in cagrilar if "kosullar" not in kaynak[i:i + 320]]
    assert not eksik, f"koşulları geçirmeyen çağrı sayısı: {len(eksik)}"


# --- Pipeline denetimi YENİDEN hesaplamaz ----------------------------------

def test_pipeline_bayragi_ceviri_sonucundan_alir():
    """Bayrak `translate_chapter`'da onarımdan SONRA ölçülür.

    Pipeline aynı ölçütü ikinci kez yazsaydı iki ölçüt ayrışırdı: pipeline
    `kosullar`ı hiç görmüyor, yani koşullu terim orada sahte ihlal üretir ve
    onarımı başarılı geçmiş bölüme ⚠ rozeti basardı.
    """
    sonuc = {
        "source": "The Saint raised his hand.",
        "translation": "Saint elini kaldırdı.",
        "glossary_leaks": {},  # translate_chapter: koşullu kayıt, ihlal değil
    }
    assert pipeline._uyum_denetimi(sonuc) == {}


def test_hizalama_tutmazsa_onarim_denenmez(monkeypatch):
    """Hizalama yoksa hangi paragrafın bozuk olduğu bilinemez; denetim yine koşar."""
    cagrilar: list[str] = []
    _kur(monkeypatch, ["Saint elini kaldırdı. Sunny gökyüzünü izledi."], cagrilar)

    out = translate.translate_chapter(KAYNAK, api_key="k", glossary=SOZLUK)

    assert out["source"] is None
    assert len(cagrilar) == 1, "hizalama yokken onarım turu atılmamalı"
    # Denetim hizalamaya İHTİYAÇ DUYMAZ (düz metin karşılaştırması); bayrak
    # düşerse kullanıcı bozuk bölümü hiçbir uyarı görmeden okur.
    assert out["glossary_leaks"] == {"Saint": "Aziz"}
