"""Sözlük terimlerinin çeviriye doğru taşınması + çevrimdışı düzenleme uçları.

Hepsi çevrimdışı: Gemini/Playwright çağrılmaz, yalnız saf fonksiyonlar, SQLite
roundtrip'leri ve ağ gerektirmeyen endpoint'ler.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

import server
from core import glossary, translate


# ---------- terim eşleştirme: ek almış hâlleri yakala, komşu kelimeye bulaşma ----------


def test_term_regex_cekim_ekiyle_eslesir():
    pattern = translate._term_regex("Tier")
    assert pattern.search("He reached Tier 5.")
    assert pattern.search("Both Tiers collapsed.")
    assert pattern.search("The Tier's power faded.")


def test_term_regex_farkli_kelimeye_bulasmaz():
    pattern = translate._term_regex("Tier")
    # Kullanıcının bildirdiği karışma: "level" hiçbir şekilde Tier eşleşmesi olmamalı.
    assert not pattern.search("He reached level 57.")
    assert not pattern.search("Tiernan drew his sword.")  # kelime içinde geçiyor


def test_term_regex_cok_kelimeli_isim():
    pattern = translate._term_regex("Kim Dokja")
    assert pattern.search("Kim Dokja's hand trembled.")
    assert not pattern.search("Kim walked away.")


def test_relevant_glossary_metinde_gecmeyen_terimi_atar(monkeypatch):
    monkeypatch.setattr(translate, "GLOSSARY_FILTER_MIN", 2)
    terms = {"Tier": "Kademe", "Nightmare": "Kabus", "Sunny": "Sunny"}
    picked = translate._relevant_glossary(terms, "Sunny climbed to the second Tier.")
    assert picked == {"Tier": "Kademe", "Sunny": "Sunny"}


def test_relevant_glossary_cekimli_hali_gorunce_terimi_tutar(monkeypatch):
    monkeypatch.setattr(translate, "GLOSSARY_FILTER_MIN", 2)
    terms = {"Tier": "Kademe", "Nightmare": "Kabus"}
    picked = translate._relevant_glossary(terms, "The upper Tiers were sealed.")
    assert picked == {"Tier": "Kademe"}


def test_relevant_glossary_kucuk_sozlugu_oldugu_gibi_gecirir():
    # Eşiğin altında süzme yok: kazanç yok, düzensiz çoğulda terim kaçırma riski var.
    terms = {"Tier": "Kademe", "Nightmare": "Kabus"}
    assert translate._relevant_glossary(terms, "Nothing matches here.") == terms


def test_sistem_talimati_yakin_terimleri_ayirir():
    assert dict(translate.CORE_TERM_HINTS)["level"] == "seviye"
    assert dict(translate.CORE_TERM_HINTS)["tier"] == "kademe"
    assert "level -> seviye" in translate.SYSTEM_INSTRUCTION
    assert "kademesi" in translate.SYSTEM_INSTRUCTION  # ek getirme kuralı örneği


def test_prompt_sozluk_hatirlatmasini_metnin_sonuna_koyar(monkeypatch):
    """Uzun bölümde sözlük kuralı kaybolmamalı.

    Ölçülen sorun: 1500 kelimelik bölümde promptun BAŞINDAKİ sözlük "unutuluyor",
    korunması gereken 26 adın 23'ü Türkçeleştiriliyordu (uydurma "Işıkölge" böyle
    çıktı). Hatırlatma metnin sonuna eklenince ihlal 4 turda da 0'a indi. Bu test
    hatırlatmanın METİNDEN SONRA geldiğini sabitler — sıra bozulursa etki gider.
    """
    yakalanan = {}

    class _Yanit:
        text = '{"translation": "[[1]] ç", "detected_names": []}'

    def sahte_uret(client, models, user, system=None, max_tokens=None):
        yakalanan["user"] = user
        return _Yanit(), models[0]  # (yanıt, fiilen çeviren model)

    monkeypatch.setattr(translate, "_generate_with_fallback", sahte_uret)
    monkeypatch.setattr(translate.genai, "Client", lambda api_key=None: object())

    translate.translate_chapter(
        "Blackwater attacked the Zero Wing guild.",
        api_key="k",
        glossary={"Blackwater": "Blackwater", "Zero Wing": "Zero Wing"},
    )

    user = yakalanan["user"]
    assert "SON HATIRLATMA" in user
    # Hatırlatma çevrilecek METNİN ARDINDAN gelmeli (yakınlık etkisi).
    assert user.index("SON HATIRLATMA") > user.index("ÇEVRİLECEK METİN")
    # Aynen korunacak adlar hatırlatmada tek tek sayılmalı.
    son = user[user.index("SON HATIRLATMA"):]
    assert "Blackwater" in son and "Zero Wing" in son


def test_prompt_hatirlatmasi_sozluk_bosken_eklenmez(monkeypatch):
    """Sözlüksüz kitapta boş bir hatırlatma prompt'u şişirmesin."""
    yakalanan = {}

    class _Yanit:
        text = '{"translation": "[[1]] ç", "detected_names": []}'

    monkeypatch.setattr(
        translate, "_generate_with_fallback",
        lambda c, m, user, system=None, max_tokens=None: (
            yakalanan.update(user=user), (_Yanit(), m[0])
        )[1],
    )
    monkeypatch.setattr(translate.genai, "Client", lambda api_key=None: object())

    translate.translate_chapter("A quiet sentence.", api_key="k", glossary={})

    assert "SON HATIRLATMA" not in yakalanan["user"]


def test_sistem_talimati_kaynastirma_kuralini_genel_verir():
    """Ek kuralı SÖZLÜK maddesine hapsedilmemeli.

    Gerçek bulgu: kural yalnız sözlük bendindeyken CORE_TERM_HINTS ile gelen
    "level -> seviye" kapsam dışı kaldı ve "farklı bir seviyeindeydi" üretildi
    (doğrusu: seviyesindeydi). Kural artık bağımsız madde; kaynaştırma ünsüzünü
    ve yanlış biçimleri açıkça sayar."""
    talimat = translate.SYSTEM_INSTRUCTION
    assert "EK KURALI" in talimat
    assert "KAYNAŞTIRMA" in talimat
    for dogru in ("seviyesi", "seviyenin", "seviyeye"):
        assert dogru in talimat
    for yanlis in ("seviyein", "kademein"):  # yasaklı biçimler örnekleniyor
        assert yanlis in talimat


# ---------- otomatik eklenen isimlerin kök hâle indirgenmesi ----------


def test_normalize_source_iyelik_ve_noktalama_temizler():
    assert glossary.normalize_source("Sunny's") == "Sunny"
    assert glossary.normalize_source("“Nephis”") == "Nephis"
    assert glossary.normalize_source("  Kim Dokja,  ") == "Kim Dokja"
    assert glossary.normalize_source("Ess") == "Ess"  # kısa isimde 's' kırpılmaz


def test_merge_names_cekimli_hali_ayri_kayit_acmaz():
    glossary.merge_names("kitap", ["Sunny", "Sunny's", "Sunny"])
    assert glossary.get_glossary("kitap") == {"Sunny": "Sunny"}


def test_merge_names_kullanici_duzenlemesini_bozmaz():
    glossary.set_term("kitap", "Nightmare", "Kabus")
    glossary.merge_names("kitap", ["Nightmare's"])
    assert glossary.get_glossary("kitap")["Nightmare"] == "Kabus"


# ---------- sözlük uçları (telefondaki kuyruk bunlara boşalıyor) ----------


def test_glossary_ucu_ekle_oku_sil():
    client = TestClient(server.app)

    added = client.post("/api/book/kitap/glossary", json={"source": "Tier", "target": "Kademe"})
    assert added.status_code == 200
    assert added.json()["terms"] == {"Tier": "Kademe"}

    assert client.get("/api/book/kitap/glossary").json()["terms"] == {"Tier": "Kademe"}

    dropped = client.delete("/api/book/kitap/glossary", params={"source": "Tier"})
    assert dropped.status_code == 200
    assert dropped.json()["terms"] == {}


def test_glossary_ucu_ayni_terimi_gunceller():
    client = TestClient(server.app)
    client.post("/api/book/kitap/glossary", json={"source": "Tier", "target": "Basamak"})
    latest = client.post("/api/book/kitap/glossary", json={"source": "Tier", "target": "Kademe"})
    assert latest.json()["terms"] == {"Tier": "Kademe"}


# ---------- yazım varyantı: aynı ad bitişik/tireli/başka harflerle geçince ----------


def test_fold_term_yazim_varyantlarini_tek_anahtara_indirir():
    hepsi = {glossary.fold_term(y) for y in (
        "Ore Empire", "OreEmpire", "ore-empire", "ORE  EMPIRE", "Ore_Empire",
    )}
    assert hepsi == {"oreempire"}


def test_fold_term_farkli_terimleri_birlestirmez():
    assert glossary.fold_term("Ore Empire") != glossary.fold_term("Ore Emperor")


def test_term_regex_bitisik_yazimi_yakalar():
    """Asıl bulgu: sözlükte 'Ore Empire' kayıtlıyken metinde 'OreEmpire' geçiyor."""
    pattern = translate._term_regex("Ore Empire")
    for metin in (
        "The OreEmpire fell.", "The Ore Empire fell.", "The Ore-Empire fell.",
        "the ore empire fell.", "The OreEmpire's army marched.",
        "Two Ore Empires clashed.",
    ):
        assert pattern.search(metin), metin


def test_term_regex_bitisik_kayit_ayrik_metni_yakalar():
    """Ters yön: sözlükte bitişik kayıtlı ad metinde ayrık geçebilir."""
    pattern = translate._term_regex("OreEmpire")
    assert pattern.search("The Ore Empire fell.")
    assert pattern.search("The OreEmpire fell.")


def test_term_regex_varyant_toleransi_baska_kelimeye_bulasmaz():
    """Esneklik yalnız AYIRICIDA; kelimenin kendisi hâlâ tam eşleşmeli."""
    pattern = translate._term_regex("Ore Empire")
    assert not pattern.search("The ore was heavy.")       # yalnız ilk parça
    assert not pattern.search("The Empire fell.")         # yalnız ikinci parça
    assert not pattern.search("The OreEmpirical study.")  # kelime içinde
    # Tek parçalı ad CamelCase bölmesinden zarar görmemeli.
    assert not translate._term_regex("Tier").search("Tiernan drew his sword.")
    assert translate._term_regex("Blackwater").search("Blackwater attacked.")


def test_term_parts_kayipsiz_bolunemeyen_adi_bolmez():
    assert translate._term_parts("Blackwater") == ["Blackwater"]
    assert translate._term_parts("OreEmpire") == ["Ore", "Empire"]
    assert translate._term_parts("Ore Empire") == ["Ore", "Empire"]


def test_relevant_glossary_varyantla_gecen_terimi_tutar(monkeypatch):
    """SÜZME KAYBI (asıl hata): terim sözlükte var ama metindeki yazımı farklı diye
    prompt'a hiç girmiyordu — model de o adı her bölümde yeniden çeviriyordu."""
    monkeypatch.setattr(translate, "GLOSSARY_FILTER_MIN", 2)
    terms = {"Ore Empire": "Cevher İmparatorluğu", "Nightmare": "Kabus"}
    picked = translate._relevant_glossary(terms, "The OreEmpire sent its legions.")
    assert picked == {"Ore Empire": "Cevher İmparatorluğu"}


def test_merge_terms_yazim_varyanti_ikinci_satir_acmaz():
    """Kayıtlı terimin varyantı yeni satır açsaydı karşılıklar ayrışırdı."""
    glossary.merge_terms("kitap", {"Ore Empire": "Cevher İmparatorluğu"})
    glossary.merge_terms("kitap", {"OreEmpire": "Maden İmparatorluğu"})
    assert glossary.get_glossary("kitap") == {"Ore Empire": "Cevher İmparatorluğu"}


def test_merge_terms_ayni_yanittaki_iki_varyanti_teklestirir():
    eklenen = glossary.merge_terms("kitap", {
        "Ore Empire": "Cevher İmparatorluğu", "OreEmpire": "Maden İmparatorluğu",
    })
    assert len(eklenen) == 1
    assert len(glossary.get_glossary("kitap")) == 1


def test_merge_terms_kullanici_yazimini_korur():
    """Kullanıcı okunaklı yazımı görmeli: saklanan anahtar fold'lanmış hâl DEĞİL."""
    glossary.merge_terms("kitap", {"Ore Empire": "Cevher İmparatorluğu"})
    assert "Ore Empire" in glossary.get_glossary("kitap")


def test_term_regex_kesme_isareti_varyantini_yakalar():
    """GERÇEK BULGU (219 bölümlük ölçüm): aynı ad metinde hem düz (') hem kıvrık (’)
    kesme işaretiyle geçiyor. Sözlükte kıvrıkla kayıtlı terim, düz yazılan bölümlerde
    süzmede kayboluyordu — kaydı olmasına rağmen prompt'a hiç girmiyordu."""
    kivrik = translate._term_regex("Heaven\u2019s Burial")
    assert kivrik.search("He drew Heaven's Burial.")        # düz kesme
    assert kivrik.search("He drew Heaven\u2019s Burial.")   # kıvrık kesme
    duz = translate._term_regex("King's Return")
    assert duz.search("The King\u2019s Return began.")


def test_sistem_talimati_deyimleri_ayri_kural_yapar():
    """GERÇEK BULGU (bölüm 1862): "turn the tables on them" → "masaları onlara karşı
    çevirecekti". Genel "birebir değil, anlamı koru" maddesi kalıpları tutmadı;
    deyim AYRI ve ÖRNEKLİ bir madde istiyor. Örnekleri silme — etki onlardan geliyor."""
    talimat = translate.SYSTEM_INSTRUCTION
    assert "DEYİM" in talimat
    assert "turn the tables" in talimat
    assert "masaları çevirmek" in talimat  # yanlış biçim açıkça yasaklanıyor
    assert "ÖLÇÜT" in talimat              # modele kendini denetleme ölçütü verilir
