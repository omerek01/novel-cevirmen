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


# ---------- İngilizce korunan ad: küçük harfli geçiş sıradan kelimedir ----------
# Ölçüm (gerçek bölümlerde, İngilizce kaynak): `Dark` 113, `Blue` 53, `Sun` 5 kez
# SIRADAN kelime olarak eşleşiyordu. Her eşleşme prompt'a "bu ad AYNEN İngilizce
# kalacak" kuralını sokuyor; model o zaman sıradan bir sıfatı çevirmiyor.


def test_ingilizce_korunan_ad_kucuk_harfli_gecisi_saymaz():
    assert not translate._terim_metinde("Sun", "Sun", "The sun rose over the hill.")
    assert translate._terim_metinde("Sun", "Sun", "Sun smiled at him.")


def test_bagirma_yazimi_ingilizce_korunan_adi_elemez():
    """Düz "büyük-küçük harf duyarlı arama" DEĞİL: tümü büyük harf de geçerli."""
    assert translate._terim_metinde("Sunny", "Sunny", "SUNNY! he shouted.")


def test_kucuk_harfli_kaynak_kucuk_harf_kuralindan_muaf():
    """Gerçek kayıt: `tls123 -> tls123` (kullanıcı adı) — metinde hep küçük harfli.

    Kuralı ona da uygulamak, kaydı hiç eşleşmez hâle getirir ve o ad "her bölümde
    yeniden karar" durumuna düşerdi.
    """
    assert translate._terim_metinde("tls123", "tls123", "posted by tls123 online")


def test_turkce_karsilikli_terim_kucuk_harfte_de_eslesir():
    """Kural YALNIZ İngilizce korunan kayda uygulanır; kaybın yönü asimetrik.

    Türkçe karşılığı olan kayıt küçük yazıma uygulanınca DOĞRU çeviri çıkar
    (zararsız); İngilizce korunan kayıt uygulanınca sıradan kelime İngilizce
    kalır (görünür bozukluk).
    """
    assert translate._terim_metinde(
        "Ore Empire", "Ork İmparatorluğu", "the ore empire fell that winter"
    )


def test_relevant_glossary_siradan_kelimeyi_getirmez(monkeypatch):
    monkeypatch.setattr(translate, "GLOSSARY_FILTER_MIN", 2)
    terms = {"Dark": "Dark", "Blue": "Blue", "Ore Empire": "Ork İmparatorluğu"}
    picked = translate._relevant_glossary(terms, "The dark blue sky over the ore empire.")
    assert picked == {"Ore Empire": "Ork İmparatorluğu"}


def test_ingilizce_korunan_varyant_kaydi_da_kural_kapsaminda():
    """`Ore Empire -> OreEmpire` de fiilen "İngilizce korunuyor" demektir."""
    assert translate._ingilizce_korunan("Ore Empire", "OreEmpire")
    assert not translate._ingilizce_korunan("Ore Empire", "Ork İmparatorluğu")


# ---------- zorlayıcı hatırlatma listesi DAİMA süzülür ----------


def test_korunacak_listesi_bolumde_gecmeyen_adi_saymaz():
    """Eşiğin ALTINDAKİ sözlükte de hatırlatma süzülmeli.

    `_relevant_glossary` küçük sözlüğü hiç süzmüyor (`GLOSSARY_FILTER_MIN`), o
    yüzden hatırlatma bölümde geçmeyen adları da dayatıyordu — ölçüm: 30 terimlik
    bir kitapta HER bölümde 18 ad. Ana SÖZLÜK listesi olduğu gibi kalır; dar
    tutulan yalnız ZORLAYICI kısımdır.
    """
    user = translate._build_user_prompt(
        ["Nephis drew her blade."],
        {"Nephis": "Nephis", "Sunny": "Sunny", "Zero Wing": "Sıfır Kanat"},
        "",
    )
    bas, son = user.split("SON HATIRLATMA", 1)
    assert "Nephis" in son          # bölümde geçiyor -> dayatılır
    assert "Sunny" not in son       # geçmiyor -> dayatılmaz
    assert "Sunny -> Sunny" in bas  # ama ana sözlük listesinden düşmez


def test_korunacak_listesi_turkce_karsilikli_terimi_saymaz():
    """Hatırlatma "AYNEN İngilizce kalacak" diyor; Türkçeleşen terim oraya girmez."""
    user = translate._build_user_prompt(
        ["The Zero Wing hall stood empty."], {"Zero Wing": "Sıfır Kanat"}, "",
    )
    assert "AYNEN kalacak" not in user.split("SON HATIRLATMA", 1)[1]


# ---------- elle ekleme, otomatik eklemenin sertleştirmelerini uygular ----------


def test_set_term_yazim_varyanti_ikinci_satir_acmaz():
    glossary.set_term("kitap", "Ore Empire", "Ork İmparatorluğu")
    glossary.set_term("kitap", "OreEmpire", "Ork İmparatorluğu")
    assert glossary.get_glossary("kitap") == {"Ore Empire": "Ork İmparatorluğu"}


def test_set_term_varyantla_gelen_duzeltmeyi_kayitli_satira_yazar():
    """Kayıtlı YAZIM korunur, değişen yalnız karşılıktır."""
    glossary.set_term("kitap", "Ore Empire", "Maden İmparatorluğu")
    glossary.set_term("kitap", "ore-empire", "Ork İmparatorluğu")
    assert glossary.get_glossary("kitap") == {"Ore Empire": "Ork İmparatorluğu"}


def test_set_term_cekim_ekini_koke_indirir():
    """Okuyucudaki hızlı ekleme "sunucu köke indiriyor" varsayımıyla yazılmıştı."""
    glossary.set_term("kitap", "Sunny's", "Sunny")
    assert list(glossary.get_glossary("kitap")) == ["Sunny"]


def test_set_term_ucu_varyanti_teklestirir():
    """Uç de aynı sertleştirmeyi almalı — API'ye doğrudan giden çağrı korumasız kalmasın."""
    with TestClient(server.app) as client:
        client.post("/api/book/kitap/glossary", json={"source": "Ore Empire", "target": "Ork"})
        r = client.post("/api/book/kitap/glossary", json={"source": "OreEmpire", "target": "Ork"})
        assert r.json()["terms"] == {"Ore Empire": "Ork"}


# ---------- lakap: ad yerine geçen sözcük de kişi sınıfındadır ----------
# Gerçek bulgu (Shadow Slave 6. bölüm, 2026-08-23): anlatıcı gerçek adını bilmediği
# kişileri özelliklerine göre adlandırıyor (Scholar, Shifty, Hero). Kural "İngilizce
# kalan TEK sınıf gerçek kişi adları, UNVAN çevrilir" derken model bunları harfiyen
# unvan sayıp Türkçeleştirdi ve karşılık sözlüğe KURAL olarak yazıldı; 7. bölüm de
# ona uydu. Model bunları `detected_names`e hiç önermedi — boşluk kuraldaydı.


def test_sistem_talimati_lakabi_kisi_sinifina_alir():
    metin = translate.SYSTEM_INSTRUCTION
    assert "LAKAP ÖLÇÜTÜ" in metin
    assert "Scholar" in metin and "Shifty" in metin


def test_lakap_olcutu_kategori_terimlerini_disarida_birakir():
    """Ölçüt DAR olmalı: belirteç alan ya da sınıf anlatan sözcük lakap DEĞİLDİR.

    Gevşek bir kural `an Aspirant` / `the Awakened` gibi sistem terimlerini de
    İngilizce'ye kaçırırdı — düzeltmeye çalıştığımız hatadan büyük bir zarar.
    """
    kural = translate.LAKAP_KURALI
    assert "a/an/the" in kural            # belirteç ölçütü
    assert "an Aspirant" in kural          # karşı örnek
    assert "the Awakened" in kural         # karşı örnek


def test_lakap_olcutu_uc_talimatta_da_ayni():
    """Çeviri, öneri ve sınıflandırma AYNI metni kullanmalı.

    Üçü ayrışırsa aynı kitapta iki farklı politika oluşur: okurken eklenen terim
    ile çevirinin kendi kararı çelişir.
    """
    for talimat in (
        translate.SYSTEM_INSTRUCTION,
        translate.SUGGEST_INSTRUCTION,
        translate.CLASSIFY_INSTRUCTION,
    ):
        assert translate.LAKAP_KURALI in talimat


def test_detected_names_lakabi_kabul_eder():
    """Kutu tanımı da genişlemeli: model lakabı bildirmezse sözlüğe hiç girmez ve
    sonraki bölümde yeniden karar konusu olur."""
    metin = translate.SYSTEM_INSTRUCTION
    bas = metin.index("- detected_names:")
    son = metin.index("- detected_terms:")
    kutu = metin[bas:son]
    assert "LAKAP ÖLÇÜTÜ" in kutu
    assert "kategori unvanı" in kutu   # sade "unvan" lakapla çelişirdi


# ---------- çoğul kaydedilmiş terim tekili de yakalar ----------
# Kuyruk eki (`s?`) çoğulu EKLİYOR ama ÇIKARMIYORDU: çoğul kaydedilmiş bir terim
# tekilini asla yakalayamıyordu ve kayıt sözlükte durduğu hâlde prompt'a hiç
# girmiyordu. Ölçülen vaka: `tyrants -> Tiranlar` kaydı varken metinde `tyrant`
# 22 kez tekil geçiyordu; model `the Tyrant`ı serbestçe "hükümdar" çevirdi.
# Gerçek sözlükte ölçüldü: kapsanan geçiş 14 -> 59.


def test_cogul_kayit_tekili_yakalar():
    assert translate._terim_metinde("tyrants", "Tiranlar", "the Tyrant roared")
    assert translate._terim_metinde("tyrants", "Tiranlar", "the tyrants roared")


def test_cok_kelimeli_cogul_kayit_tekili_yakalar():
    assert translate._terim_metinde(
        "Evil Beasts", "Kötü Canavarlar", "an Evil Beast appeared"
    )


def test_cogul_esnekligi_ingilizce_korunan_adda_kapali():
    """Risk sınıfı KİŞİ adlarıdır: `Nephis` esnetilirse `Nephi`ye bulaşır.

    Kaybın yönü asimetrik — İngilizce korunan kayıtta yanlış eşleşme sıradan bir
    sözcüğü İngilizce bıraktırır (görünür bozukluk); Türkçe karşılıklı kayıtta
    doğru çeviri çıkar (zararsız).
    """
    assert not translate._terim_metinde("Nephis", "Nephis", "Nephi walked alone")
    assert translate._terim_metinde("Nephis", "Nephis", "Nephis walked alone")


def test_cogul_esnekligi_kisa_koku_bozmaz():
    """`MIN_COGUL_KOK`: kısa kökte eşleşme sıradan harflere bulaşırdı."""
    assert not translate._terim_metinde("Os", "Oz", "O ran away")


def test_terim_anahtari_suzgeci_cogula_toleransli():
    """Model `Evil Beasts` bildirip kaynak `Evil Beast` diyorsa kayıt ELENMEMELİ.

    Meşru bir kaydı atmak, o adı her bölümde yeniden karar konusu yapar — sözlüğün
    var oluş sebebinin tersi.
    """
    assert translate.ayikla_terim_anahtarlari(
        {"Evil Beasts": "Kötü Canavarlar"}, "A single Evil Beast appeared."
    ) == {"Evil Beasts": "Kötü Canavarlar"}


# ---------- tekili AYRICA kayıtlı çoğul kayıt tekili YAKALAMAZ ----------
# Çoğul esnekliği, tekili sözlükte OLMAYAN çoğul kayıt içindir (`tyrants` vakası).
# Tekil de kayıtlıysa tekil geçişin sahibi TEKİL kayıttır; çoğul kayıt onu da
# yakalayınca tekilin KOŞULUNU ezer. Ölçülen arıza (2026-09-23, sunucu): koşullu
# `Saint -> Aziz [gölgenin ADI ise İngilizce kalır]` yanında koşulsuz
# `Saints -> Azizler` vardı. Gölgenin adı geçen her bölümde prompt'a koşulsuz
# "Saints -> Azizler" satırı giriyordu ve adı DOĞRU koruyan çeviri 44 bölümün
# 44'ünde sahte `Saints` ihlali alıp gereksiz bir onarım isteği tetikliyordu.
# Etki alanı geniş: shadow-slave sözlüğünde tekili de kayıtlı 85 çoğul var.

CIFT = {"Saint": "Aziz", "Saints": "Azizler"}


def test_tekili_kayitli_cogullar_bulunur():
    assert translate._tekili_kayitli_cogullar(CIFT) == {"Saints"}
    # Yazım varyantı da tekil sayılır (karşılaştırma `fold_term` ile).
    assert translate._tekili_kayitli_cogullar(
        {"Sailor-Doll": "Denizci Bebek", "Sailor Dolls": "Denizci Bebekler"}
    ) == {"Sailor Dolls"}
    # Tekili kayıtlı DEĞİLSE esneklik yerinde kalır (`tyrants` vakası).
    assert translate._tekili_kayitli_cogullar({"tyrants": "Tiranlar"}) == frozenset()


def test_tekili_kayitli_cogul_kayit_tekili_yakalamaz():
    tekili = translate._tekili_kayitli_cogullar(CIFT)
    assert not translate._terim_metinde("Saints", "Azizler", "Saint raised her sword.", tekili)
    assert not translate._terim_metinde("Saints", "Azizler", "She studied Saint's figure.", tekili)
    # Gerçek çoğul geçiş çoğul kaydındır.
    assert translate._terim_metinde("Saints", "Azizler", "Many Saints gathered.", tekili)


# İyelik ŞART: `fold_term` kesme işaretini attığı için "Saint's" katlanınca
# "saints" olur ve süzgecin ucuz ön elemesini geçer — üretimde çoğul satırını
# prompt'a sokan tam olarak buydu (bölüm 667: "She studied Saint's motionless
# figure"). "Saint raised..." ön elemede zaten düştüğü için ayırt edici değil.
TEKIL_IYELIK = "She studied Saint's motionless figure."


def test_tekil_gecen_metinde_cogul_satiri_prompta_girmez():
    """Süzgeç ancak `GLOSSARY_FILTER_MIN` kayıttan sonra devreye girer."""
    sozluk = {**CIFT, **{f"Dolgu{i}": f"Doldurma{i}" for i in range(40)}}
    kosul = {"Saint": "yalnız rütbe; gölgenin ADI ise İngilizce kalır"}
    user = translate._build_user_prompt([TEKIL_IYELIK], sozluk, "", kosul)
    assert "Saint -> Aziz  [KOŞUL:" in user
    assert "Saints -> Azizler" not in user
    # Çoğul geçen metinde çoğul satırı yine girer.
    user = translate._build_user_prompt(["Many Saints gathered."], sozluk, "", kosul)
    assert "Saints -> Azizler" in user


def test_bolumde_gecen_terimler_tekil_geciste_coguli_listelemez():
    assert translate.metinde_gecen_terimler(CIFT, TEKIL_IYELIK) == ["Saint"]
    assert translate.metinde_gecen_terimler(CIFT, "Many Saints gathered.") == [
        "Saint", "Saints",
    ]


def test_terim_metinde_her_cagrisi_tekil_kumesini_gecirir():
    """Statik tel tuzağı: `_terim_metinde`'yi çağıran her yer tekil kümesini geçirmeli.

    Biri unutursa o yol çoğul esnekliğini eskisi gibi uygular; prompt süzgeci,
    uyum denetimi ve künye aynı terim için farklı karar verir. Bu projede künye
    alanları tam olarak böyle, bir yol güncellenmeyi unutunca ayrışmıştı.
    """
    import pathlib
    import re

    eksik = []
    for yol in sorted(pathlib.Path("app").rglob("*.py")):
        kaynak = yol.read_text(encoding="utf-8")
        for m in re.finditer(r"(?<!def )_terim_metinde\(", kaynak):
            derinlik, i = 1, m.end()
            while derinlik and i < len(kaynak):
                derinlik += {"(": 1, ")": -1}.get(kaynak[i], 0)
                i += 1
            if "tekili" not in kaynak[m.end():i]:
                eksik.append(f"{yol}:{kaynak.count(chr(10), 0, m.start()) + 1}")
    assert not eksik, f"tekil kümesini geçirmeyen çağrılar: {eksik}"


# ---------- hiyerarşi basamağı küçük harfli de olsa terimdir ----------


def test_sistem_talimati_hiyerarsi_basamagini_kapsar():
    """Gerçek bulgu (Shadow Slave 4. bölüm): canavar rütbeleri kaynakta ÇOĞUNLUKLA
    küçük harfli (`monsters` 13 küçük / 1 büyük) — büyük harf ölçütü onları kaçırdı
    ve hiçbiri sözlüğe geçmedi."""
    metin = translate.SYSTEM_INSTRUCTION
    assert "HİYERARŞİ İSTİSNASI" in metin
    bas = metin.index("HİYERARŞİ İSTİSNASI")
    madde = metin[bas:bas + 600]
    assert "KÜÇÜK harfle" in madde
    # Ayırt edici ŞART: düzene bağlanmayan sıradan cins isim girmemeli.
    assert "AYIRT EDİCİ" in madde

