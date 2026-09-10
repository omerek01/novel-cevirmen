"""Sözlükte KOŞULLU karşılık: aynı terim, bağlama göre farklı çeviri.

Neden gerekti (2026-09-06, kullanıcı bildirimi): Shadow Slave'de `Great` bir
KABUS YARATIĞI rütbesidir ("Dormant, Awakened, Fallen, Corrupted, Great, Cursed
and Unholy") ve kullanıcı bunun `Ulu` olmasını istiyor; insan tarafındaki eşdeğer
rütbe `Supreme` ise `Yüce` kalmalı. Sözlük düz bir `kaynak -> karşılık` eşlemesi
olduğu için bu ayrım İFADE EDİLEMİYORDU.

Ölçüm (önbellekteki 32 geçiş) düz bir `Great -> Ulu` kaydının NEDEN yetmediğini
gösterdi: geçişlerin ~12'si gündelik İngilizce (`Great!`, `Great job`,
`Great people`) ve sözlük karşılığı prompt'ta KURAL olduğu için model onları da
"Ulu!" yapardı. Yani düz kayıt bir sorunu çözerken on ikisini açardı.

Koşul, karşılığın YERİNE GEÇMEZ; yanına iliştirilir ve YALNIZ prompt'a çıkar.
`sozluk_ihlalleri` ve terim eşleştirme karşılığı olduğu gibi görmeye devam eder.
"""
import pytest

from core import glossary, translate


KITAP = "shadow-slave"


# ---------- depolama ----------

def test_kosul_yazilir_ve_okunur():
    glossary.set_term(KITAP, "Great", "Ulu")
    glossary.set_kosul(KITAP, "Great", "yalnız Kabus Yaratığı rütbesi olarak")
    assert glossary.get_kosullar(KITAP) == {
        "Great": "yalnız Kabus Yaratığı rütbesi olarak"
    }


def test_kosulsuz_terim_kosullar_sozlugune_girmez():
    """Koşulsuz kayıtlar listeyi şişirmemeli — prompt'a boş satır çıkmasın."""
    glossary.set_term(KITAP, "Nephis", "Nephis")
    assert glossary.get_kosullar(KITAP) == {}


def test_set_term_mevcut_kosulu_SILMEZ():
    """Okuyucunun sözlük kuyruğu {source,target} gönderir — koşulu ezmemeli.

    Bu, alanı görünmez bir tuzağa çevirecek TEK hata olurdu: kullanıcı ekranda
    karşılığı düzeltince koşul sessizce kaybolur, terim ertesi bölümde yine
    yanlış çevrilir ve sebebi hiçbir yerde görünmezdi.
    """
    glossary.set_term(KITAP, "Great", "Ulu")
    glossary.set_kosul(KITAP, "Great", "yalnız canavar rütbesi")
    glossary.set_term(KITAP, "Great", "Ulu (düzeltildi)")
    assert glossary.get_kosullar(KITAP)["Great"] == "yalnız canavar rütbesi"
    assert glossary.get_glossary(KITAP)["Great"] == "Ulu (düzeltildi)"


def test_kosul_bosaltilabilir():
    glossary.set_term(KITAP, "Great", "Ulu")
    glossary.set_kosul(KITAP, "Great", "bir koşul")
    glossary.set_kosul(KITAP, "Great", "")
    assert glossary.get_kosullar(KITAP) == {}


def test_kosul_satirlarda_gorunur():
    """Sözlük ekranı koşulu göstermeli; görünmeyen kural hata ayıklanamaz."""
    glossary.set_term(KITAP, "Great", "Ulu")
    glossary.set_kosul(KITAP, "Great", "yalnız canavar rütbesi")
    satir = next(r for r in glossary.get_glossary_rows(KITAP) if r["source"] == "Great")
    assert satir["kosul"] == "yalnız canavar rütbesi"


def test_silinen_terimin_kosulu_da_gider():
    glossary.set_term(KITAP, "Great", "Ulu")
    glossary.set_kosul(KITAP, "Great", "x")
    glossary.delete_term(KITAP, "Great")
    assert glossary.get_kosullar(KITAP) == {}


# ---------- prompt ----------

def _prompt(paragraf, sozluk, kosullar=None):
    return translate._build_user_prompt([paragraf], sozluk, "", kosullar)


def test_kosul_prompta_karsiligin_YANINDA_cikar():
    p = _prompt(
        "The Great ranks are dangerous.",
        {"Great": "Ulu"},
        {"Great": "yalnız Kabus Yaratığı rütbesi olarak"},
    )
    assert "Great -> Ulu" in p
    assert "yalnız Kabus Yaratığı rütbesi olarak" in p


def test_kosulsuz_terim_prompta_sade_cikar():
    p = _prompt("Nephis walked.", {"Nephis": "Nephis"}, {})
    assert "Nephis -> Nephis" in p
    assert "KOŞUL" not in p


def test_metinde_GECMEYEN_terimin_kosulu_prompta_girmez():
    """Süzgeç koşulları da kapsamalı: geçmeyen terimin koşulu boşa token yakar."""
    sozluk = {f"Terim{i}": f"Karsilik{i}" for i in range(40)}
    sozluk["Great"] = "Ulu"
    p = _prompt("The Great ranks.", sozluk, {"Terim3": "asla görünmemeli"})
    assert "asla görünmemeli" not in p


def test_sistem_talimati_kosulu_ACIKLAR():
    """Prompt'ta bir sözdizimi varsa modele ne demek olduğu SÖYLENMELİ."""
    assert "KOŞUL" in translate.SYSTEM_INSTRUCTION


# ---------- koşul karşılığın YERİNE GEÇMEZ ----------

def test_ihlal_denetimi_kosuldan_ETKILENMEZ():
    """`sozluk_ihlalleri` karşılığı olduğu gibi görmeli — koşul ona sızmamalı."""
    assert translate.sozluk_ihlalleri(
        {"Great": "Ulu"}, "A Great Devil appeared.", "Bir Great Devil belirdi."
    ) == {"Great": "Ulu"}
    assert translate.sozluk_ihlalleri(
        {"Great": "Ulu"}, "A Great Devil appeared.", "Bir Ulu Şeytan belirdi."
    ) == {}


def test_ceviri_yolu_kosullari_TASIR(monkeypatch):
    """Uçtan uca: pipeline'ın verdiği koşul prompt'a ulaşmalı."""
    gorulen = {}

    class _Yanit:
        text = '{"translation": "[[1]] Ulu Şeytan belirdi.", "detected_names": []}'

    def sahte(client_factory, models, user, system=None, max_tokens=None):
        gorulen["user"] = user
        return _Yanit(), "gemini-3.6-flash"

    monkeypatch.setattr(translate, "_generate_with_fallback", sahte)
    monkeypatch.setattr(translate.genai, "Client", lambda api_key=None: object())

    translate.translate_chapter(
        "A Great Devil appeared.",
        api_key="k",
        glossary={"Great": "Ulu"},
        kosullar={"Great": "yalnız Kabus Yaratığı rütbesi olarak"},
    )
    assert "yalnız Kabus Yaratığı rütbesi olarak" in gorulen["user"]


# ---------- uc + boru hatti kablolamasi ----------

def test_uc_kosulu_yazar_ve_dondurur():
    from fastapi.testclient import TestClient

    import server

    c = TestClient(server.app)
    yol = f"/api/book/{KITAP}/glossary"
    c.post(yol, json={"source": "Great", "target": "Ulu", "kosul": "canavar rutbesi"})
    assert c.get(yol).json()["kosullar"] == {"Great": "canavar rutbesi"}


def test_uc_kosulsuz_gonderimde_mevcut_kosulu_KORUR():
    """Okuyucunun kuyrugu {source,target} gonderir; kosul kaybolmamali."""
    from fastapi.testclient import TestClient

    import server

    c = TestClient(server.app)
    yol = f"/api/book/{KITAP}/glossary"
    c.post(yol, json={"source": "Great", "target": "Ulu", "kosul": "canavar rutbesi"})
    c.post(yol, json={"source": "Great", "target": "Ulu Rutbe"})  # kosul YOK
    assert c.get(yol).json()["kosullar"] == {"Great": "canavar rutbesi"}


def test_boru_hattinin_HER_ceviri_cagrisi_kosullari_TASIR():
    """Statik tel tuzağı: `translate_chapter`'ı çağıran HER yol koşulları geçirmeli.

    Davranış testi yerine statik denetim, çünkü iki çağrı noktası da çekimi kendi
    yapıyor (`_do_fetch_translate_save`, `fetch_into_book`) ve ağı sahtelemek testi
    asıl iddiadan uzaklaştırırdı. Asıl iddia zaten yapısal: SÖZLÜĞÜ okuyan her yol
    KOŞULLARI da okumalı.

    Bu projede aynı sınıf hata yaşandı: `model` künyesi bir süre yalnız TEK
    noktadaydı ve "web'den devam" ile eklenen bölüm hangi halkanın çevirdiğini
    söyleyemiyordu. Yeni bir çeviri yolu eklenirse bu test onu yakalar.
    """
    import pathlib
    import re

    kaynak = pathlib.Path("app/core/pipeline.py").read_text(encoding="utf-8")
    # Non-greedy `.*?\)` IC ICE parantezde erken kapanir (`prev_translation(...)`),
    # o yuzden cagri basindan itibaren bir PENCERE alinir.
    baslangiclar = [m.end() for m in re.finditer(r"= translate_chapter\(", kaynak)]
    assert baslangiclar, "pipeline'da translate_chapter cagrisi bulunamadi"
    eksik = [i for i in baslangiclar if "kosullar=" not in kaynak[i:i + 320]]
    assert not eksik, f"kosullari gecirmeyen cagri sayisi: {len(eksik)}"


def test_sozlugu_okuyan_her_yol_kosullari_da_OKUR():
    """`get_glossary` çağrılan her yerde `get_kosullar` da çağrılmalı."""
    import pathlib

    kaynak = pathlib.Path("app/core/pipeline.py").read_text(encoding="utf-8")
    assert kaynak.count("glossary.get_glossary(") == kaynak.count(
        "glossary.get_kosullar("
    ), "sözlüğü okuyan bir yol koşulları okumuyor"
