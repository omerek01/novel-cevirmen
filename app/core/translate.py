"""İsim-koruyan İngilizce -> Türkçe çeviri.

Gemini + paragraf bazlı parçalama (chunk) + parçalar arası bağlam taşıma +
sözlük (glossary) ile tutarlı özel isim koruması.

Dayanıklılık: her parça için model yedek zinciri denenir; bir model geçici
olarak meşgulse (429/500/503) üstel geri-çekilmeyle birkaç kez denenir, sonra
sıradaki modele düşülür.
"""
from __future__ import annotations

import json
import re
import time
from functools import lru_cache

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from .glossary import fold_term

# Çeviri modeli zinciri — ÖLÇÜMLE seçildi (2026-08-16, gerçek bölüm metinleriyle).
#
# TEK ZİNCİR, KALİTE ÖNCELİKLİ (2026-08-17, kullanıcı kararı). Sıra: en iyi modelden
# başla, kota/servis tökezledikçe bir alta in. Aynı zincir HER YERDE geçerlidir —
# okuma, prefetch, toplu çeviri, "yeniden çevir", içe aktarılan sayfa çevirisi ve
# sözlük terim önerisi. Gün içinde okumanın gövdesi büyük ihtimalle alt halkalardan
# geçecek (3.7/3.6 ücretsiz kotaları dar), o yüzden alt halkalar süsleme değil ASIL
# taşıyıcıdır; zincir tükenene kadar iner ve okuma durmaz.
#
# Ölçüm (450 kelimelik iki metin: oyun-terimli + edebi anlatı; 5 kısa çağrı güvenilirlik):
#   gemini-3.6-flash       akıcılık EN İYİ, doğal deyim ("kendini gözünde büyütmek"),
#                          Türkçe tırnak; 5/5 çağrı başarılı; ~15 sn/450 kelime
#                          ANCAK ücretsiz kotası ÇOK düşük (~25 istek/gün'de 429 verdi),
#                          o yüzden zincirin geri kalanı süsleme değil, asıl taşıyıcıdır
#   gemini-3.5-flash       akıcılık iyi, kota geniş; 3/5 çağrı 503 (yüksek talep) → orta halka
#   gemini-3.5-flash-lite  EN HIZLI (10 sn/bölüm, 3.6'da 36 sn) ve 5/5 güvenilir, üslubu
#                          en zayıf olan ama sözlüğe artık tam uyuyor → son çare
#   gemini-3.7-flash       ölçüm gününde uzun isteklerde ısrarla 503 verdi, kalitesi
#                          ÖLÇÜLEMEDİ; zincirin başında duruyor — 503 sürerse istek
#                          birkaç saniye geri-çekilip 3.6'ya düşer, okuma durmaz
#   gemini-3.1-pro-preview / gemini-pro-latest  429 — ücretsiz katmanda YOK, kullanılamaz
#
# Not: ücretsiz katmanın model-başına RPD tablosu Google tarafından artık yayınlanmıyor
# (AI Studio > Rate limits'ten bakılır). Bu yüzden kotaya göre değil, 429'a DAYANIKLI
# tasarıma güveniyoruz: bir halka tükenirse zincir kendiliğinden bir alta iner.
DEFAULT_MODELS = (
    "gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite",
)
# Parça çıktısı modelin token sınırını aşıp çeviriyi kesmesin diye ölçülü tutulur.
# Büyük parça = daha az kopma noktası = bölüm içinde daha tutarlı üslup; sınırı
# `max_output_tokens` (aşağıda) koruyor, ölçümle 1600'den yükseltildi.
MAX_WORDS_PER_CHUNK = 2800
# Çıktı token tavanı açıkça verilir: varsayılan sınır parçanın ortasında kesilirse
# JSON bozulur ve kurtarma ayrıştırıcısına düşeriz (hizalama kaybı). Türkçe çeviri
# İngilizce kaynaktan ~1.4x token tutar; 2800 kelimelik parça için bolca pay bırakır.
MAX_OUTPUT_TOKENS = 32768
# Bölümler arası bağlam: önceki bölümün son kaç kelimelik Türkçesi yeni bölümün ilk
# parçasına verilir (zamir/hitap/sahne sürekliliği bölüm sınırında kopmasın).
PREV_CHAPTER_CONTEXT_WORDS = 160
RETRY_CODES = {500, 503}  # geçici sunucu hatası: aynı modelde tekrar dene
FALLBACK_CODES = {404, 429}  # model yok / kota doldu: bekleme, sıradaki modele geç
MAX_RETRIES = 3
# Sözlük bu boyutun altındaysa parçaya süzme yapılmadan tamamı gönderilir.
GLOSSARY_FILTER_MIN = 40

# İçerik güvenlik filtreleri (kategori başına) — gevşetilebilir kategorileri kapat.
# Web romanlarda şiddet/karanlık tema sık; varsayılan filtreler yanlış-pozitif engeller.
# NOT: PROHIBITED_CONTENT bununla AŞILAMAZ (ayrı, kapatılamayan filtre) → o durumda
# yanıt boş gelir ve sıradaki modele düşülür (bir model engellerken başkası çevirebilir).
SAFETY_SETTINGS = [
    {"category": c, "threshold": "BLOCK_NONE"}
    for c in (
        "HARM_CATEGORY_HARASSMENT",
        "HARM_CATEGORY_HATE_SPEECH",
        "HARM_CATEGORY_SEXUALLY_EXPLICIT",
        "HARM_CATEGORY_DANGEROUS_CONTENT",
    )
]

# Yakın anlamlı sistem terimleri: model bunları birbirine karıştırıp sözlükteki bir
# karşılığı komşu kelimeye taşıyabiliyor (gözlenen: sözlükte "Tier -> Kademe" varken
# "level" de "kademe" çevrildi). Sabit ayrım listesi tutarlılığı bölümden bölüme korur.
# SÖZLÜK bunları EZER (kullanıcı kendi karşılığını yazarsa o geçerli).
CORE_TERM_HINTS = (
    ("level", "seviye"),
    ("tier", "kademe"),
    ("rank", "rütbe"),
    ("grade", "derece"),
    ("stage", "aşama"),
    ("class", "sınıf"),
    ("realm", "diyar"),
    ("skill", "beceri"),
    ("trait", "özellik"),
    ("attribute", "nitelik"),
)
_CORE_HINT_STR = ", ".join(f"{en} -> {tr}" for en, tr in CORE_TERM_HINTS)

SYSTEM_INSTRUCTION = (
    "Sen profesyonel bir İngilizce'den Türkçe'ye web roman çevirmenisin.\n"
    "Kurallar:\n"
    "- Akıcı, doğal, edebi Türkçe üret. Birebir değil, anlamı koru.\n"
    # Gerçek bulgu (bölüm 1862): "turn the tables on them" → "masaları onlara karşı
    # çevirecekti". Genel "birebir değil" maddesi bunu tutmadı; deyimler AYRI ve
    # örnekli bir kural istiyor.
    "- DEYİMLERİ VE KALIP İFADELERİ KELİME KELİME ÇEVİRME. Türkçedeki karşılığını "
    "kullan; karşılığı yoksa anlamını açık Türkçeyle yaz. Örnekler: 'turn the tables "
    "(on someone)' -> 'durumu tersine çevirmek / işi onların aleyhine döndürmek' "
    "('masaları çevirmek' YANLIŞ); 'break the ice' -> 'buzları eritmek'; 'in his "
    "shoes' -> 'onun yerinde'; 'call it a day' -> 'paydos etmek'; 'the ball is in "
    "your court' -> 'sıra sende'. ÖLÇÜT: kurduğun Türkçe cümleyi bağlamı bilmeyen "
    "biri okuduğunda 'bu ne demek şimdi' diyorsa kalıbı birebir çevirmişsindir; "
    "o cümleyi anlamıyla yeniden yaz.\n"
    "- İngilizce korunacak TEK sınıf: gerçek kişi/karakter adları (örn. Sunny, "
    "Kim Dokja, Nephis). Başka hiçbir özel ad İngilizce kalmaz.\n"
    "- Büyü, beceri, sınıf, ırk, unvan, eşya, YER, LONCA/klan/birlik/örgüt ve "
    "sistem/dünya terimlerini İngilizce BIRAKMA; Türkçe'ye çevir (Spell -> Büyü, "
    "Nightmare -> Kabus, Skill -> Beceri, Zero Wing -> Sıfır Kanat gibi). Bir "
    "kelimenin büyük harfle başlaması onu korumak için sebep DEĞİLDİR.\n"
    "- Yer ve lonca adlarını çevirirken kelimeleri UYDURMA biçimde birleştirme: "
    "'Lightshadow City' -> 'Işıkgölge Şehri' (doğru), 'Işıkölge' (YANLIŞ). "
    "Türkçe karşılık gerçek Türkçe kelimelerden kurulmalı.\n"
    "- Bir lonca/örgüt adının İÇİNDE kişi adı geçiyorsa o kişi adı İngilizce kalır, "
    "geri kalanı çevrilir ('Wang Lin's Hall' -> 'Wang Lin Salonu').\n"
    "- SÖZLÜK bir eşlemedir (kaynak -> karşılık). Uygulama kuralları:\n"
    "  * Karşılığı YALNIZCA kaynak terimin KENDİSİ metinde geçtiğinde kullan; "
    "çoğul/iyelik hâli de sayılır (Tier, Tiers, Tier's).\n"
    "  * Kaynak terim metinde FARKLI YAZILMIŞ olabilir: bitişik, tireli, fazladan "
    "boşluklu ya da başka büyük-küçük harflerle ('Ore Empire' ~ 'OreEmpire' ~ "
    "'Ore-Empire' ~ 'ORE EMPIRE'). Hepsi AYNI terimdir; karşılığı yine uygula ve "
    "detected_terms'te sözlükteki yazımı kullan.\n"
    "  * Karşılığı BAŞKA bir kelimeye ASLA taşıma. Eşanlamlı ve yakın anlamlı "
    "kelimeler sözlüğe DAHİL DEĞİLDİR: sözlükte 'Tier -> Kademe' varsa 'level' "
    "yine 'seviye' olarak çevrilir, 'kademe' DEĞİL.\n"
    "  * Karşılık cümlede ek almalıysa Türkçe ekini DOĞRU getir (aşağıdaki EK KURALI).\n"
    "  * Kaynak çoğul veya iyelikse karşılık da Türkçe'de çoğul/iyelik olur "
    "(Tiers -> Kademeler; the Tier's power -> Kademenin gücü).\n"
    "  * İngilizce korunan özel isim ek alırken kesme işareti kullan ve eki "
    "okunuşa göre seç (Sunny'nin, Sunny'ye, Kim Dokja'yı, Nephis'in).\n"
    f"- Yakın anlamlı sistem terimlerini BİRBİRİNE KARIŞTIRMA; her biri ayrı "
    f"çevrilir: {_CORE_HINT_STR}. Bu listede olan bir kelime için SÖZLÜK'te farklı "
    "bir karşılık verilmişse SÖZLÜK geçerlidir.\n"
    # Gözlenen hata: "Blackwater farklı bir seviyeindeydi" (doğrusu: seviyesindeydi).
    # Ek kuralı yalnız SÖZLÜK maddesinin altındaydı; yukarıdaki sistem terimlerini
    # ve metnin geri kalanını kapsamıyordu. Artık bağımsız ve kaynaştırma ünsüzü açık.
    "- EK KURALI (sözlük karşılıkları, yukarıdaki sistem terimleri ve METNİN TAMAMI "
    "için geçerlidir): Ünlüyle biten bir köke ünlüyle başlayan ek gelirse ARAYA "
    "KAYNAŞTIRMA ÜNSÜZÜ girer — iyelikte 's', ilgi hâlinde 'n', yönelmede 'y': "
    "seviye -> seviyesi / seviyenin / seviyeye / seviyesinde; kademe -> kademesi / "
    "kademenin / kademeye; beceri -> becerisi / becerinin / beceriye. "
    "'seviyei', 'seviyein', 'seviyeinde', 'kademein', 'becerii' gibi kaynaştırmasız "
    "biçimler YANLIŞTIR ve ASLA yazılmaz. Ünlü uyumuna ve ünsüz yumuşamasına da uy, "
    "kökü bozma (Kabus -> Kabusu / Kabuslar).\n"
    "- ÖNCEKİ ÇEVİRİ verilirse onu TEKRAR çevirme; yalnızca devamlılık için kullan: "
    "anlatım kişisi, kip ve hitap düzeyi (sen/siz) oradan devam etmeli — bölüm başında "
    "üslup değiştirme.\n"
    "- ÜSLUP NOTU verilirse kitap boyunca ona uy (anlatım kişisi, hitap, ton). Notla "
    "metin çelişirse METİN kazanır; not bir tercih, uydurma sebebi değildir.\n"
    "- METİN paragrafları [[n]] ile numaralıdır. Çeviride HER paragrafın başına AYNI "
    "[[n]] işaretini koy; hiçbir işareti ATLAMA, BİRLEŞTİRME veya sırasını DEĞİŞTİRME. "
    "Bir İngilizce paragraf bir Türkçe paragrafa karşılık gelir.\n"
    '- Yanıtı SADECE şu JSON ile ver: {"translation": "[[1]] ...\\n\\n[[2]] ...", '
    '"detected_names": ["..."], '
    '"detected_terms": {"İngilizce özel ad": "Türkçe karşılığı"}}\n'
    "- detected_names: SADECE metinde geçen KARAKTER (kişi) isimleri — İngilizce "
    "yazımıyla (çeviride de İngilizce kalan tek sınıf bunlardır). Buraya KİŞİ "
    "OLMAYAN hiçbir şeyi yazma: lonca/klan, şehir, krallık, imparatorluk, kale, "
    "eşya, beceri, ırk, unvan, canavar türü buraya girerse kitabın sözlüğüne "
    "İngilizce olarak çakılır ve sonraki bölümlerde de Türkçeye çevrilemez. "
    "KİŞİ Mİ diye tereddüt ediyorsan detected_names'e DEĞİL detected_terms'e yaz.\n"
    "- detected_names'teki her ad çeviri metninde de AYNEN İngilizce yazımıyla "
    "geçmelidir. Çeviride Türkçeleştirdiğin bir adı buraya YAZMA ve buraya asla "
    "Türkçe kelime koyma (Türkçeleştirdiysen yeri detected_terms'tir).\n"
    "- detected_terms: metinde geçen DİĞER TÜM ÖZEL ADLAR — hiçbirini atlama: yer "
    "(şehir/imparatorluk/kale/bölge/diyar), lonca/klan/birlik/örgüt, EŞYA ve eser "
    "ve silah, BECERİ/büyü/teknik/yetenek, unvan, ırk/tür, sınıf, adı olan canavar, "
    "olay/kurum ve sistem/dünya terimi. Anahtar İngilizce özgün ad, değer senin "
    "çeviride KULLANDIĞIN Türkçe karşılık "
    "(\"Puppeteer's Shroud\" -> \"Kuklacının Örtüsü\", "
    '"Zero Wing" -> "Sıfır Kanat", "Lightshadow City" -> "Işıkgölge Şehri").\n'
    "- ÖLÇÜT: metinde BÜYÜK HARFLE başlayarak o dünyaya ait belirli bir şeyi "
    "adlandıran her ifade detected_terms'e girer; sıradan cins isim (a sword, the "
    "city) girmez ama adlandırılmış hâli (the Sword of Dawn) GİRER. Birden çok "
    "kelimeli adı BÜTÜN olarak ver, parçalama.\n"
    "- detected_terms'te çeviride ne yazdıysan burada AYNISINI ver; ikisi tutmazsa "
    "sözlük bozulur. Böyle bir ad yoksa boş bırak."
)

# Paragraf hizalama işaretçisi: [[1]], [[ 2 ]] gibi. Çeviride korunur → her Türkçe
# paragrafı kaynak İngilizce paragrafıyla eşler (sayı tutmasa bile hizalama bozulmaz).
MARKER_RE = re.compile(r"\[\[\s*(\d+)\s*\]\]")


class TranslateError(Exception):
    """Çeviri kalıcı olarak başarısız olduğunda fırlatılır (model meşgul, kota vb.)."""


class _Retryable(Exception):
    """İç sinyal: bu modelde geçici hata tükendi; sıradaki modele geç."""


def translate_chapter(
    text: str,
    api_key: str,
    glossary: dict[str, str] | None = None,
    models: tuple[str, ...] = DEFAULT_MODELS,
    prev_context: str = "",
    style_note: str = "",
) -> dict:
    """Tüm bölümü parçalayıp çevirir; bağlamı taşır, yeni isimleri biriktirir.

    İşaretçi (``[[n]]``) ile paragraf-hizalı üretir: dönen ``translation`` ve ``source``
    AYNI ``\\n\\n`` paragraf sayısına sahiptir (i. Türkçe paragraf <-> i. İngilizce
    paragraf). Bir parçada hizalama tutmazsa o parça tek blok olur ve ``source`` None
    döner (çeviri yine de tam; iki-dilli o bölümde devre dışı).

    ``prev_context``: ÖNCEKİ BÖLÜMÜN son Türkçe metni. İlk parçanın bağlamı olur —
    parçalar arası devamlılık zaten taşınıyordu ama bölüm sınırında sıfırlanıyor,
    sahnenin ortasında biten bir bölümün devamı bağlamsız çevriliyordu.
    ``style_note``: kitap başına serbest üslup notu (anlatım kişisi, hitap, ton).

    Döner: {"translation": str, "source": str|None, "detected_names": list[str],
            "detected_terms": dict[str, str], "chunk_count": int, "engine": str}

    ``detected_names`` karakter adlarıdır (İngilizce kalır); ``detected_terms``
    karakter dışı TÜM özel adlardır (kaynak -> modelin kullandığı Türkçe karşılık).

    ``engine`` dönüşte hep "gemini": tek motor var, ama alan bölüm künyesinin
    (`chapters.engine`) parçası ve DB'de eski kayıtlar başka değer taşıyor.
    """
    glossary = dict(glossary or {})
    chunks = _split_paragraphs(text)

    # Tembel: parça yoksa (boş bölüm) istemci hiç kurulmaz.
    _client: genai.Client | None = None

    def client_factory() -> genai.Client:
        nonlocal _client
        if _client is None:
            if not api_key:
                raise TranslateError("GEMINI_API_KEY ayarlı değil.")
            _client = genai.Client(api_key=api_key)
        return _client

    tr_paras: list[str] = []
    en_paras: list[str] = []
    new_names: set[str] = set()
    new_terms: dict[str, str] = {}
    # Kullanılan modeller: sıra korunur, tekrar elenir (dict anahtarı). Bölümün
    # parçaları farklı halkalara düşmüş olabilir; künye hepsini göstermeli.
    used_models: dict[str, None] = {}
    prev_tail = _tail_words(prev_context, PREV_CHAPTER_CONTEXT_WORDS)
    aligned = True

    for chunk in chunks:
        chunk_en = [p.strip() for p in chunk.split("\n\n") if p.strip()]
        result = _translate_chunk(
            client_factory, models, chunk_en, glossary, prev_tail, style_note,
        )
        if result.get("model"):
            used_models[result["model"]] = None
        for name in result["detected_names"]:
            if name and name not in glossary:
                new_names.add(name)
        # Karakter dışı özel adlar Türkçe karşılığıyla sabitlenir; ilk gören kazanır
        # (bölüm içinde tekrar gelirse ilki korunur), sözlükteki kullanıcı kaydı hep üstün.
        for kaynak, hedef in (result.get("detected_terms") or {}).items():
            if kaynak and hedef and kaynak not in glossary:
                new_terms.setdefault(kaynak, hedef)
        chunk_tr = _split_by_markers(result["translation"], len(chunk_en))
        if chunk_tr is not None:
            tr_paras.extend(chunk_tr)
            en_paras.extend(chunk_en)
            prev_tail = _last_sentences("\n\n".join(chunk_tr[-2:]), 2)
        else:
            # Hizalama tutmadı: işaretleri temizleyip tek blok ekle, kaynağı bırak.
            clean = _strip_markers(result["translation"])
            tr_paras.append(clean)
            en_paras.append(chunk)
            aligned = False
            prev_tail = _last_sentences(clean, 2)

    translation = "\n\n".join(tr_paras)
    return {
        "translation": translation,
        "source": "\n\n".join(en_paras) if aligned else None,
        # Süzgeç ŞART: model karakter olmayan adları (lonca, şehir, eşya) düzenli
        # olarak bu kutuya sızdırıyor ve oraya düşen her ad sözlüğe İNGİLİZCE
        # çakılıyor (`merge_names`, X -> X) — kitap boyunca çevrilemez hâle gelir.
        "detected_names": ayikla_karakter_adlari(sorted(new_names), new_terms, translation),
        "detected_terms": new_terms,
        # Künye: bölümü FİİLEN çeviren model(ler). Parçalar farklı halkalara düştüyse
        # hepsi yazılır ("… + …"); boş bölümde (hiç parça yok) None.
        "model": " + ".join(used_models) or None,
        "chunk_count": len(chunks),
        "engine": "gemini",  # künye alanı; tek motor kaldığından sabit
    }


# Türkçe'ye özgü harfler: İngilizce KALACAK bir karakter adı bunları içermez.
# Gerçek bulgu: model `detected_names`'e "Kızıl Alev Kalesi" ve "Dark Oyuncular"
# yazdı, ikisi de sözlüğe "İngilizce korunacak" diye girdi.
_TR_HARF_RE = re.compile(r"[çğıİöşüÇĞÖŞÜ]")


def ayikla_karakter_adlari(
    names: list[str], terms: dict[str, str], translation: str
) -> list[str]:
    """`detected_names`'ten gerçekten İngilizce kalan KİŞİ adlarını süz.

    Bu kutuya düşen her ad sözlüğe `X -> X` diye girer (`glossary.merge_names`) ve
    sözlük prompt'ta KURALdır: bir daha asla Türkçeye çevrilmez. Model ise kutuyu
    düzenli olarak karakter dışı adlarla dolduruyor — kullanıcının ölçtüğü sonuç,
    "karakter dışı her özel ad Türkçe olsun" kuralına rağmen sözlüğün İngilizce
    kayıtlarla dolması (`Blackwater Guild`, `Star-Moon Kingdom`, `Ancient Rock City`).

    Üç eleme, hepsi de modelin KENDİ çıktısına dayanır (tahmin/sözlük listesi yok):

    1. Ad `detected_terms`'te de varsa → Türkçe karşılık kazanır (orası daha bilgili).
    2. Ad Türkçe'ye özgü harf içeriyorsa → zaten Türkçeleştirilmiş, İngilizce sayma.
    3. Ad çeviri metninde AYNEN geçmiyorsa → model onu çeviride Türkçeleştirmiş
       demektir; `X -> X` yazmak modelin kendi kararıyla çelişir ve sonraki
       bölümleri İngilizceye zorlar.

    Karşılaştırma `fold_term` üzerinden: Türkçe ek/yazım varyantı ("Nephis'in",
    "OreEmpire") adı elemesin.
    """
    ceviri = fold_term(translation)
    terim_anahtarlari = {fold_term(k) for k in terms}
    ayikli: list[str] = []
    for ad in names:
        anahtar = fold_term(ad)
        if not anahtar or anahtar in terim_anahtarlari:
            continue
        if _TR_HARF_RE.search(ad):
            continue
        if anahtar not in ceviri:
            continue
        ayikli.append(ad)
    return ayikli


SUGGEST_INSTRUCTION = (
    "Sen bir İngilizce→Türkçe web roman çevirmenisin. Sana bir ÖZEL AD ve geçtiği "
    "cümle verilecek; bu adın kitap sözlüğüne nasıl kaydedileceğine karar ver.\n"
    "Kural (çeviri sözlüğünün kuralıyla AYNI):\n"
    "- Ad bir KİŞİ/KARAKTER adıysa İngilizce KALIR: karşılık, adın kendisidir.\n"
    "- Başka her özel ad (yer, şehir, imparatorluk, lonca/klan/örgüt, eşya, silah, "
    "beceri/büyü/teknik, unvan, ırk, adlandırılmış canavar, sistem/dünya terimi) "
    "TÜRKÇE'ye çevrilir; karşılık o Türkçe biçimdir.\n"
    "- Bir örgüt/yer adının İÇİNDE kişi adı geçiyorsa o kişi adı İngilizce kalır, "
    "gerisi çevrilir ('Wang Lin's Hall' -> 'Wang Lin Salonu').\n"
    "- Türkçe karşılık GERÇEK Türkçe kelimelerden kurulmalı; kelimeleri uydurma "
    "biçimde birleştirme ('Lightshadow City' -> 'Işıkgölge Şehri' doğru, 'Işıkölge' "
    "YANLIŞ). Kaynaktaki büyük harf, korunması için sebep DEĞİLDİR.\n"
    "- CÜMLE bağlamı belirleyicidir: aynı sözcük bir kitapta kişi adı, başkasında "
    "yer adı olabilir ('Rain' bir karakter de olabilir, 'yağmur' da).\n"
    '- Yanıtı SADECE şu JSON ile ver: {"is_character": true/false, "target": "..."}\n'
    "- is_character true ise target ADIN KENDİSİDİR (İngilizce yazımıyla, değiştirme)."
)


def suggest_term(
    source: str,
    context: str = "",
    api_key: str = "",
    models: tuple[str, ...] = DEFAULT_MODELS,
) -> dict:
    """Seçilen özel ad için sözlük karşılığı öner (okuyucudaki hızlı ekleme kısayolu).

    Döner: ``{"source": str, "target": str, "is_character": bool}``.

    Karakter adı → ``target == source`` (İngilizce kalır); başka her özel ad →
    Türkçe karşılık. Bu, `pipeline._sozluge_isle`'ın otomatik davranışının elle
    ekleme yolundaki karşılığıdır: iki yol aynı kuralı uygulamazsa aynı kitapta
    iki farklı politika oluşurdu.
    """
    source = (source or "").strip()
    if not source:
        raise TranslateError("Terim boş.")
    if not api_key:
        raise TranslateError("GEMINI_API_KEY ayarlı değil.")
    user = (
        f"ÖZEL AD: {source}\n\n"
        f"GEÇTİĞİ CÜMLE (bağlam): {(context or '').strip()[:600] or '(yok)'}"
    )
    response, _model = _generate_with_fallback(
        genai.Client(api_key=api_key), models, user,
        system=SUGGEST_INSTRUCTION, max_tokens=512,
    )
    try:
        data = json.loads((response.text or "").strip().strip("`"))
    except (json.JSONDecodeError, TypeError, AttributeError):
        data = {}
    is_char = bool(data.get("is_character"))
    hedef = (data.get("target") or "").strip()
    # Karakterde karşılık DAİMA kaynağın kendisi: model "Sunny -> Güneşli" gibi bir
    # şey döndürse bile sözlük kuralı bunu yasaklıyor.
    if is_char or not hedef:
        hedef = source
    return {"source": source, "target": hedef, "is_character": is_char}


CLASSIFY_INSTRUCTION = (
    "Sen bir İngilizce→Türkçe web roman çevirmenisin. Sana bir kitabın SÖZLÜĞÜNDEN "
    "özel ad listesi verilecek; hepsi şu an İngilizce korunuyor. Her ad için bunun "
    "doğru olup olmadığına karar ver.\n"
    "Kural (çeviri sözlüğünün kuralıyla AYNI):\n"
    "- Ad bir KİŞİ/KARAKTER adıysa İngilizce KALIR: karşılık adın kendisidir.\n"
    "- Başka her özel ad (yer, şehir, imparatorluk, krallık, kale, lonca/klan/örgüt, "
    "eşya, silah, zırh, beceri/büyü/teknik, unvan, ırk, sınıf, adlandırılmış canavar, "
    "olay, sistem/dünya terimi) TÜRKÇE'ye çevrilir; karşılık o Türkçe biçimdir.\n"
    "- Bir örgüt/yer adının İÇİNDE kişi adı geçiyorsa o kişi adı İngilizce kalır, "
    "gerisi çevrilir ('Wang Lin's Hall' -> 'Wang Lin Salonu').\n"
    "- Türkçe karşılık GERÇEK Türkçe kelimelerden kurulmalı; kelimeleri uydurma "
    "biçimde birleştirme ('Lightshadow City' -> 'Işıkgölge Şehri' doğru, 'Işıkölge' "
    "YANLIŞ). Kaynaktaki büyük harf, korunması için sebep DEĞİLDİR.\n"
    "- KİŞİ Mİ diye emin olamadığın adı KARAKTER say (is_character true): yanlış bir "
    "Türkçeleştirme kitap boyunca birebir uygulanır ve karakterin adını bozar.\n"
    '- Yanıtı SADECE şu JSON ile ver: {"terms": [{"source": "...", '
    '"is_character": true, "target": "..."}]}\n'
    "- source alanını sana verilen yazımla AYNEN geri ver ve listedeki HER ad için "
    "bir kayıt döndür; hiçbirini atlama."
)


def classify_terms(
    terms: list[str],
    api_key: str = "",
    book_title: str = "",
    models: tuple[str, ...] = DEFAULT_MODELS,
) -> dict[str, dict]:
    """Sözlükte İngilizce korunan adları TOPLU sınıflandır (bakım aracı).

    `suggest_term`'ün liste hâli: `scripts/sozluk_gozden_gecir.py` bununla eski
    kayıtları gözden geçirir. Neden gerek var: `detected_names` süzgeci yalnız
    BUNDAN SONRA çevrilecek bölümleri korur; kitapların sözlüğüne çakılmış eski
    "X -> X" kayıtları (ölçüldü: bir kitapta 201 kaydın 173'ü) prompt'ta KURAL
    olmaya devam eder ve o adlar bir daha asla Türkçeleşmez.

    Döner: ``{kaynak: {"is_character": bool, "target": str}}`` — modelin karşılık
    vermediği ad listeye HİÇ girmez (kaydı olduğu gibi bırakmak, uydurma bir
    karşılıkla değiştirmekten yeğdir).
    """
    temiz = [t.strip() for t in terms if (t or "").strip()]
    if not temiz:
        return {}
    if not api_key:
        raise TranslateError("GEMINI_API_KEY ayarlı değil.")
    user = (
        (f"KİTAP: {book_title}\n\n" if book_title else "")
        + "ADLAR:\n" + "\n".join(f"- {t}" for t in temiz)
    )
    response, _model = _generate_with_fallback(
        genai.Client(api_key=api_key), models, user,
        system=CLASSIFY_INSTRUCTION, max_tokens=MAX_OUTPUT_TOKENS,
    )
    try:
        data = json.loads((response.text or "").strip().strip("`").removeprefix("json"))
    except (json.JSONDecodeError, TypeError, AttributeError):
        return {}
    # Model kaynağı yazım varyantıyla geri verebiliyor → fold ile eşle, ama sözlükteki
    # ÖZGÜN yazımı anahtar yap (set_term o yazımı güncellemeli).
    fold_map = {fold_term(t): t for t in temiz}
    out: dict[str, dict] = {}
    for kayit in data.get("terms") or []:
        if not isinstance(kayit, dict):
            continue
        kaynak = fold_map.get(fold_term(str(kayit.get("source") or "")))
        hedef = str(kayit.get("target") or "").strip()
        if not kaynak or not hedef:
            continue
        is_char = bool(kayit.get("is_character"))
        out[kaynak] = {"is_character": is_char, "target": kaynak if is_char else hedef}
    return out


def _split_by_markers(translation: str, n: int) -> list[str] | None:
    """``[[k]]`` işaretli çeviriyi paragraf listesine böler (1..n tam ve sıralıysa).

    Her segment, ``[[k]]`` ile bir sonraki işarete kadarki metin. 1..n işaretlerinin
    hepsi yoksa, bir paragraf boş kalırsa → None (çağıran hizalamasız akışa düşer).
    """
    if not translation:
        return None
    matches = list(MARKER_RE.finditer(translation))
    if not matches:
        return None
    parts: dict[int, str] = {}
    for i, m in enumerate(matches):
        k = int(m.group(1))
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(translation)
        seg = translation[start:end].strip()
        parts[k] = (parts[k] + "\n\n" + seg).strip() if k in parts else seg
    if set(parts) != set(range(1, n + 1)):
        return None
    out = [parts[k] for k in range(1, n + 1)]
    return None if any(not s for s in out) else out


def _strip_markers(text: str) -> str:
    return MARKER_RE.sub("", text or "").strip()


def _split_paragraphs(text: str, max_words: int = MAX_WORDS_PER_CHUNK) -> list[str]:
    """Paragraf sınırlarında böl; cümle ortasından asla bölme."""
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current: list[str] = []
    current_words = 0

    for para in paragraphs:
        words = len(para.split())
        if current and current_words + words > max_words:
            chunks.append("\n\n".join(current))
            current, current_words = [para], words
        else:
            current.append(para)
            current_words += words

    if current:
        chunks.append("\n\n".join(current))
    return chunks or [text]


def _last_sentences(text: str, count: int = 2) -> str:
    sentences = re.split(r"(?<=[.!?…])\s+", text.strip())
    return " ".join(sentences[-count:]) if sentences else ""


def _tail_words(text: str, count: int) -> str:
    """Metnin son ``count`` kelimesi (bölümler arası bağlam için).

    Cümle sayısıyla değil kelimeyle ölçülür: bir bölümün sonu tek uzun cümle de
    olabilir, otuz kısa replik de — bağlam bütçesi ikisinde de aynı kalmalı."""
    words = (text or "").split()
    if not words:
        return ""
    return " ".join(words[-count:])


# Terim parçalama: aynı özel ad metinde farklı yazımlarla geçebiliyor
# ("Ore Empire" ~ "OreEmpire" ~ "Ore-Empire"). Deseni kelime PARÇALARINDAN kurup
# aralarına esnek ayırıcı koyarız; yoksa sözlükte kayıtlı terim süzmede kaybolur,
# prompt'a hiç girmez ve model o adı her bölümde yeniden çevirir (gerçek bulgu).
_TERM_SEP_RE = re.compile(r"[\s\-_'’.·]+")
# Ters yön: sözlükte BİTİŞİK kayıtlı terim ("OreEmpire") metinde ayrık geçebilir.
# İç büyük harf sınırından bölünür; tek parçalı ad ("Blackwater") bölünmez.
_CAMEL_RE = re.compile(r"[A-ZÇĞİÖŞÜ]?[a-zçğıöşü]+|[A-ZÇĞİÖŞÜ]+(?![a-zçğıöşü])|\d+")
_TERM_GLUE = r"[\s\-_'’]*"  # parçalar arası: hiç, boşluk, tire, alt çizgi…


def _term_parts(term: str) -> list[str]:
    """Terimi eşleştirilebilir kelime parçalarına ayırır (ayırıcı + CamelCase)."""
    parts = [p for p in _TERM_SEP_RE.split(term.strip()) if p]
    if len(parts) == 1:
        camel = _CAMEL_RE.findall(parts[0])
        # Eşitlik şartı: bölme kayıpsız olmalı, aksi halde ad bozulur.
        if len(camel) > 1 and "".join(camel) == parts[0]:
            return camel
    return parts


@lru_cache(maxsize=2048)
def _term_regex(term: str) -> re.Pattern[str]:
    """Terimi kelime-sınırlı, çekim ekine ve YAZIM VARYANTINA toleranslı arayan desen.

    ``Tier`` deseni ``Tier``, ``Tiers``, ``Tier's`` ile eşleşir; ``Tiernan`` ile
    eşleşmez. ``Ore Empire`` deseni ``OreEmpire`` ve ``Ore-Empire`` ile de eşleşir
    (parçalar arası ayırıcı serbest). Alfanümerik olmayan uçlarda ``\\b`` eşleşmeyi
    öldüreceğinden koşullu.
    """
    parts = _term_parts(term)
    if not parts:
        return re.compile(r"(?!)")  # hiçbir şeyle eşleşmeyen desen
    head = r"\b" if parts[0][:1].isalnum() else ""
    tail = r"(?:['’]s|es|s)?\b" if parts[-1][-1:].isalnum() else ""
    core = _TERM_GLUE.join(re.escape(p) for p in parts)
    return re.compile(head + core + tail, re.IGNORECASE)


def _relevant_glossary(glossary: dict[str, str], text: str) -> dict[str, str]:
    """Bu parçada fiilen geçen sözlük terimlerini süz (ek almış hâlleri dahil).

    Sözlüğün TAMAMINI her parçaya göndermek, metinde hiç geçmeyen terimlerin
    karşılıklarının komşu kelimelere sızmasına zemin hazırlıyor (gözlenen:
    ``Tier -> Kademe`` kaydı varken ``level`` de "kademe" çevrildi). Küçük
    sözlüklerde süzme yapılmaz: kazanç yok, düzensiz çoğul (``wolf/wolves``)
    yüzünden terim kaçırma riski var.

    Ön eleme `fold_term` üzerinden yapılır (boşluk/tire/kesme atılmış hâl). Düz
    ``term.lower() in text.lower()`` kontrolü, metinde ``OreEmpire`` yazan bir adı
    ``Ore Empire`` kaydıyla eşleştiremiyordu: terim daha regex'e VARMADAN eleniyor,
    sözlükte kayıtlı olmasına rağmen prompt'a girmiyordu.
    """
    if not glossary or len(glossary) < GLOSSARY_FILTER_MIN:
        return dict(glossary or {})
    folded = fold_term(text)  # metin de aynı indirgemeden geçer
    out: dict[str, str] = {}
    for source, target in glossary.items():
        term = (source or "").strip()
        if not term or fold_term(term) not in folded:  # ucuz ön eleme
            continue
        if _term_regex(term).search(text):
            out[source] = target
    return out


def _translate_chunk(
    client_factory,
    models: tuple[str, ...],
    en_paras: list[str],
    glossary: dict[str, str],
    prev_tail: str,
    style_note: str = "",
) -> dict:
    """Bir parçayı Gemini ile çevirir (model yedek zinciriyle).

    Dönen sözlükte ``model`` = bu parçayı FİİLEN çeviren model. Parça başına ayrı
    tutulur: uzun bölümde ilk parça kotayı bitirip sonraki parçalar bir alt halkaya
    düşebiliyor, tek bir "bölümün modeli" varsayımı yanlış olurdu.
    """
    user = _build_user_prompt(en_paras, glossary, prev_tail, style_note)
    response, model = _generate_with_fallback(client_factory(), models, user)
    out = _parse_response(response.text)
    out["model"] = model
    return out


def _build_user_prompt(
    en_paras: list[str],
    glossary: dict[str, str],
    prev_tail: str,
    style_note: str = "",
) -> str:
    """Çeviri promptunu kurar. Bölümlerin SIRASI load-bearing — bkz. SON HATIRLATMA."""
    relevant = _relevant_glossary(glossary, "\n\n".join(en_paras))
    glossary_str = (
        "\n" + "\n".join(f"{s} -> {t}" for s, t in relevant.items())
        if relevant
        else "(boş)"
    )
    numbered = "\n\n".join(f"[[{i + 1}]] {p}" for i, p in enumerate(en_paras))
    user = (
        f"ÜSLUP NOTU (bu kitap boyunca geçerli): {style_note.strip() or '(yok)'}\n\n"
        f"SÖZLÜK — YALNIZ bu terimler için geçerli (kaynak -> karşılık); kaynağı "
        f"görünce karşılığını yaz, cümle gerektiriyorsa Türkçe ekini getir; "
        f"listede OLMAYAN kelimelere bu karşılıkları UYGULAMA: {glossary_str}\n\n"
        f"ÖNCEKİ ÇEVİRİNİN SONU (sadece bağlam, tekrar çevirme): "
        f"{prev_tail or '(yok)'}\n\n"
        f"ÇEVRİLECEK METİN (her paragraf [[n]] ile numaralı; işaretleri koru):\n{numbered}"
    )
    # SÖZLÜK hatırlatması metnin SONUNA da konur. Ölçülen sorun: uzun bölümlerde
    # (1500+ kelime) model, promptun başındaki sözlüğü "unutup" korunması gereken
    # özel adları Türkçeleştiriyordu (gerçek bulgu: 26 terimin 23'ü tek turda kayıp
    # → "Lightshadow City" yerine uydurma "Işıkölge"). Talimat metne en yakın yerde
    # tekrarlanınca kural görüş alanında kalıyor.
    if relevant:
        korunacak = [s for s, t in relevant.items() if s == t]
        user += (
            "\n\nSON HATIRLATMA — SÖZLÜK KURALI HÂLÂ GEÇERLİDİR: yukarıdaki sözlükte "
            "verilen karşılıkları BİREBİR kullan."
        )
        if korunacak:
            user += (
                " Şu adlar İngilizce yazımıyla AYNEN kalacak (yalnız Türkçe eki "
                "eklenebilir), ASLA Türkçeye çevrilmeyecek ve ASLA birleştirilip "
                "uydurma bir kelime yapılmayacak: " + ", ".join(korunacak) + "."
            )
    return user


def _generate_with_fallback(
    client: genai.Client,
    models: tuple[str, ...],
    user: str,
    system: str = SYSTEM_INSTRUCTION,
    max_tokens: int = MAX_OUTPUT_TOKENS,
):
    """Model yedek zincirini sırayla dener; hepsi başarısızsa TranslateError fırlatır.

    ``system``/``max_tokens`` varsayılanları bölüm çevirisidir; terim önerisi gibi
    kısa işler kendi talimatını ve daha küçük bir tavanı geçer.

    Döner: ``(response, model)`` — FİİLEN çeviren modelin adı künyeye kadar taşınır.
    Yalnız `response` dönseydi zincirin hangi halkasının çevirdiği kaybolurdu; kalite
    şikâyetlerinde "bunu hangi model çevirdi" sorusu tahminle cevaplanıyordu.
    """
    last_exc: Exception | None = None
    blocked = False
    for model in models:
        try:
            return _generate_once_with_retry(client, model, user, system, max_tokens), model
        except _Retryable as exc:
            last_exc = exc
            blocked = blocked or getattr(exc, "blocked", False)
            continue
    if blocked:
        raise TranslateError(
            "Bu bölümün içeriği hiçbir model tarafından çevrilemedi (içerik filtresi); "
            "metin engellenmiş olabilir."
        ) from last_exc
    raise TranslateError(
        "Tüm modeller şu anda meşgul (geçici). Biraz sonra tekrar deneyin."
    ) from last_exc


def _generate_once_with_retry(
    client: genai.Client,
    model: str,
    user: str,
    system: str = SYSTEM_INSTRUCTION,
    max_tokens: int = MAX_OUTPUT_TOKENS,
):
    """Tek modelde üstel geri-çekilmeyle dener; geçici hata/engel tükenince _Retryable."""
    delay = 2.0
    for attempt in range(MAX_RETRIES):
        try:
            response = client.models.generate_content(
                model=model,
                contents=user,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    response_mime_type="application/json",
                    temperature=0.3,
                    max_output_tokens=max_tokens,
                    safety_settings=SAFETY_SETTINGS,
                ),
            )
        except genai_errors.APIError as exc:
            code = getattr(exc, "code", None)
            if code in FALLBACK_CODES:
                raise _Retryable() from exc  # kota/erişim yok -> sıradaki modele geç
            if code in RETRY_CODES:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise _Retryable() from exc
            raise TranslateError(f"Çeviri hatası: {exc}") from exc
        # Yanıt geldi ama boş/engellenmiş olabilir (finish_reason PROHIBITED_CONTENT/
        # SAFETY/RECITATION → HTTP 200, metin yok). Bu deterministiktir; aynı modelde
        # tekrar denemek beyhude → sıradaki modele düş (başka model çevirebilir).
        try:
            txt = response.text or ""
        except Exception:  # bazı engellenmiş yanıtlarda .text istisna fırlatır
            txt = ""
        if txt.strip():
            return response
        exc = _Retryable()
        exc.blocked = True
        raise exc


def _BOS_AYRISTIRMA() -> dict:
    return {
        "translation": "",
        "detected_names": [],
        "detected_terms": {},
    }


def _parse_response(raw: str | None) -> dict:
    if not raw:
        return _BOS_AYRISTIRMA()
    text = raw.strip()
    # Bazı modeller JSON'u ```json ... ``` çitiyle sarar; temizle.
    if text.startswith("```"):
        text = text.strip("`")
        if text[:4].lower() == "json":
            text = text[4:]
        text = text.strip()
    try:
        data = json.loads(text)
        # Eski şema (detected_guilds/detected_places) da okunur: tek "diğer özel
        # adlar" kutusuna genişletildi, ama model kimi zaman eski alan adlarını
        # üretiyor — o yanıtları düşürmek terimi sessizce kaybettirirdi.
        terimler = _esleme(data.get("detected_terms"))
        for eski in ("detected_guilds", "detected_places"):
            for kaynak, hedef in _esleme(data.get(eski)).items():
                terimler.setdefault(kaynak, hedef)
        return {
            "translation": data.get("translation", ""),
            "detected_names": _liste(data.get("detected_names")),
            "detected_terms": terimler,
        }
    except (json.JSONDecodeError, TypeError, AttributeError):
        # JSON bozuk/yarım: ham basmak yerine 'translation' alanını ayıklamayı dene.
        out = _BOS_AYRISTIRMA()
        out["translation"] = _extract_translation(text)
        return out


def _liste(deger) -> list[str]:
    """Model bazen tek string, bazen null döndürür; her hâlde listeye indir."""
    if isinstance(deger, str):
        return [deger] if deger.strip() else []
    if not isinstance(deger, list):
        return []
    return [d for d in deger if isinstance(d, str) and d.strip()]


def _esleme(deger) -> dict[str, str]:
    """``detected_terms`` eşlemesini temizle (kaynak -> karşılık).

    Model kimi zaman sözlük yerine düz liste döndürür; o durumda karşılık
    bilinmediği için kayıt ATILIR — yanlış karşılıkla sözlüğü kirletmektense
    terimi hiç eklememek yeğdir (sözlük prompt'ta KURALdır, öneri değil).
    """
    if not isinstance(deger, dict):
        return {}
    out: dict[str, str] = {}
    for kaynak, hedef in deger.items():
        if not isinstance(kaynak, str) or not isinstance(hedef, str):
            continue
        k, h = kaynak.strip(), hedef.strip()
        if k and h:
            out[k] = h
    return out


def _extract_translation(text: str) -> str:
    """Bozuk/yarım JSON'dan çeviri metnini kurtar; olmazsa ham metni döndür."""
    match = re.search(
        r'"translation"\s*:\s*"(.*?)"\s*,\s*"detected_names"', text, re.DOTALL
    ) or re.search(r'"translation"\s*:\s*"(.*)$', text, re.DOTALL)
    if not match:
        return text
    captured = match.group(1)
    try:
        return json.loads('"' + captured + '"')  # \n, \" gibi kaçışları çöz
    except json.JSONDecodeError:
        return captured.replace("\\n", "\n").replace('\\"', '"').rstrip('"')
