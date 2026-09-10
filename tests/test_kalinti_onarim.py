"""İngilizce kalan paragrafın OTOMATİK onarımı (hedefli yeniden çeviri).

Denetim tek başına yetmez: `sozluk_ihlalleri` de bir bayrak üretiyor ama kimse
onu onarmıyor ve kullanıcı bölümü yine bozuk okuyor. Sızıntı burada onarılabilir
çünkü hizalama TUTUYOR — hangi paragrafın çevrilmediği TAM olarak biliniyor, o
yüzden bölümün tamamı değil YALNIZ o paragraflar yeniden çevrilir (tipik vaka
60 paragraflık bölümde 1 paragraf).

Onarım TEK turdur. İkinci tur bilinçle yok: sızıntı modelin dikkat kaymasıdır,
kısa ve odaklı bir istek onu çoğunlukla düzeltir; düzeltmiyorsa döngü kurmak
yalnız maliyeti (ücretli model seçiliyken PARAYI) katlar. Onarılamayan sızıntı
künyeye bayrak olarak yazılır ve okuyucuda görünür.

Ağa çıkmaz — `_generate_with_fallback` sahtelenir.
"""
import json

from core import translate


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
    "Sunny nodded slowly.\n\n"
    '"But to me, it’s a paradise."\n\n'
    "He walked away into the dark."
)


def test_ingilizce_kalan_paragraf_onarilir(monkeypatch):
    """İlk turda İngilizce dönen paragraf, ikinci (hedefli) turda Türkçeleşir."""
    cagrilar: list[str] = []
    _kur(
        monkeypatch,
        [
            # 1. tur: ortadaki paragraf çevrilmeden dönüyor (gerçek arıza #188)
            '[[1]] Sunny yavaşça başını salladı.\n\n'
            '[[2]] "But to me, it’s a paradise."\n\n'
            "[[3]] Karanlığa doğru uzaklaştı.",
            # 2. tur: onarım isteği — yalnız o paragraf gelir
            '[[1]] "Ama bana göre burası bir cennet."',
        ],
        cagrilar,
    )

    out = translate.translate_chapter(KAYNAK, api_key="k")

    paras = out["translation"].split("\n\n")
    assert paras[1] == '"Ama bana göre burası bir cennet."'
    assert out["ingilizce_kalinti"] == {}
    assert len(cagrilar) == 2, "tam bir onarım turu bekleniyor"
    # Onarım isteği YALNIZ sızan paragrafı taşımalı; bölümün tamamını yeniden
    # göndermek her sızıntıyı tam bölüm maliyetine çıkarırdı.
    assert "But to me" in cagrilar[1]
    assert "Sunny nodded" not in cagrilar[1]


def test_onarilamayan_kalinti_bayraga_yazilir(monkeypatch):
    """Model ikinci turda da İngilizce dönerse: TEK tur denenir, bayrak kalır."""
    cagrilar: list[str] = []
    _kur(
        monkeypatch,
        [
            '[[1]] Sunny yavaşça başını salladı.\n\n'
            '[[2]] "But to me, it’s a paradise."\n\n'
            "[[3]] Karanlığa doğru uzaklaştı.",
            '[[1]] "But to me, it’s a paradise."',
        ],
        cagrilar,
    )

    out = translate.translate_chapter(KAYNAK, api_key="k")

    assert set(out["ingilizce_kalinti"]) == {1}
    assert len(cagrilar) == 2, "onarım TEK tur olmalı — döngü maliyeti katlar"


def test_temiz_ceviride_onarim_turu_yok(monkeypatch):
    """Sızıntı yoksa ikinci istek ATILMAZ — her bölüme ek maliyet bindirmez."""
    cagrilar: list[str] = []
    _kur(
        monkeypatch,
        [
            "[[1]] Sunny yavaşça başını salladı.\n\n"
            "[[2]] \"Ama bana göre burası bir cennet.\"\n\n"
            "[[3]] Karanlığa doğru uzaklaştı."
        ],
        cagrilar,
    )

    out = translate.translate_chapter(KAYNAK, api_key="k")

    assert out["ingilizce_kalinti"] == {}
    assert len(cagrilar) == 1


def test_hizalama_tutmazsa_onarim_denenmez(monkeypatch):
    """Hizalama yoksa hangi paragrafın sızdığı bilinemez; ölçüt uygulanamaz."""
    cagrilar: list[str] = []
    _kur(monkeypatch, ["işaretçisiz düz çeviri"], cagrilar)

    out = translate.translate_chapter(KAYNAK, api_key="k")

    assert out["source"] is None
    assert out["ingilizce_kalinti"] == {}
    assert len(cagrilar) == 1


def test_onarim_modeli_kunyeye_girer(monkeypatch):
    """Onarımı yapan model künyede görünmeli — rozet FİİLEN çevireni yazar."""
    cagrilar: list[str] = []

    def sahte(client_factory, models, user, system=None, max_tokens=None):
        cagrilar.append(user)
        if len(cagrilar) == 1:
            return _yanit(
                '[[1]] Sunny yavaşça başını salladı.\n\n'
                '[[2]] "But to me, it’s a paradise."\n\n'
                "[[3]] Karanlığa doğru uzaklaştı."
            ), "gemini-3.5-flash"
        return _yanit('[[1]] "Ama bana göre burası bir cennet."'), "gemini-3.6-flash"

    monkeypatch.setattr(translate, "_generate_with_fallback", sahte)
    monkeypatch.setattr(translate.genai, "Client", lambda api_key=None: object())

    out = translate.translate_chapter(KAYNAK, api_key="k")

    assert out["model"] == "gemini-3.5-flash + gemini-3.6-flash"
