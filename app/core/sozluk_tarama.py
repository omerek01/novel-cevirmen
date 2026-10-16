"""Kitap düzeyi, ÖRNEKLEMELİ terim taraması (TranslateBooksWithLLMs `auto-extract` uyarlaması).

Kaynak yöntem (hydropix/TranslateBooksWithLLMs, `docs/GLOSSARY.md`, `src/core/glossary/ner.py`):
kitaptan eşit aralıklı N parça (vars. 10 parça, toplam ~6000 karakter) alınır, TEK bir LLM isteği
yinelenen özel adları {source, target, category} olarak önerir, kullanıcı onaylamadan hiçbir şey
uygulanmaz. Her çalıştırma FARKLI parçalar örneklediği için 2–3 tekrar yeni varlık getirir.

Bizdeki farklar (projenin dersleri):
  * Kanıt şartı: her öneri örnekte BİREBİR geçen bir cümle taşır (varlık çıkarımıyla aynı ilke);
    taşımayan ya da cümlede kaynak geçmeyen öneri atılır.
  * Zaten kayıtlı terim (`_term_regex` ile, yazım varyantı dahil) aday olmaz.
  * Kitabın kendi korpusunda sıradan sözcük olan aday (`genel_sozcuk_mu`) ve yalnız bir bölümde
    geçen aday elenir — TBWL bunları kullanıcıya bırakıyor; bizim veride en sık hata sınıfı buydu.
  * Yazma kapısı (`sozluk_kapi.kapi_denetle`) bulgusu adayın yanına yazılır.
  * Model YALNIZ ücretsiz zincirden; sonuç öneridir. Onaylanan aday `merge_terms` ile, yani
    normal yazma kapısından geçerek eklenir.
"""
from __future__ import annotations

import json
import os
import random
import re

from . import cache, glossary, library, sozluk_dogrulama, sozluk_kapi, translate

PARCA = 10
TOPLAM_KARAKTER = 6000
MIN_BOLUM = 2

TARAMA_INSTRUCTION = (
    "Sen İngilizce→Türkçe web roman çevirisi için TERİM çıkarıcısısın. Sana bir kitaptan farklı "
    "bölümlerden alınmış parçalar verilecek. Çevirmenin kitap boyunca TUTARLI tutması gereken, "
    "YİNELENMESİ muhtemel özel adları ve adlandırılmış kavramları çıkar: kişi (ad, lakap), yer, örgüt "
    "(klan, lonca, ordu), rütbe/basamak/sınıf, yetenek/büyü/nitelik, adlandırılmış eşya, ırk/yaratık türü, "
    "sistem terimi.\n"
    "Kurallar:\n"
    "- Sıradan sözcükleri ve betimleyici öbekleri ALMA (a sword, the city, seven days, lost).\n"
    "- Bir KİŞİYİ adlandıran ifade İngilizce kalır: target kaynağın AYNISIDIR.\n"
    + translate.LAKAP_KURALI +
    "- Başka her özel ad Türkçeye çevrilir; target yalın hâlde gerçek Türkçe sözcüklerden kurulur "
    "(iyelik 's ya da sonda kesmeli ek yok).\n"
    "- Her önerinin kanit alanına, parçalarda BİREBİR geçen ve source'u içeren TEK cümleyi kopyala.\n"
    "- Emin değilsen önerme; yanlış bir sözlük kaydı kitap boyunca KURAL olarak uygulanır.\n"
    'Yanıtı SADECE şu JSON ile ver: {"terms": [{"source": "...", "target": "...", '
    '"tur": "kisi|yer|orgut|rutbe|yetenek|nesne|diger", "kanit": "..."}]}'
)


def ornekle(bolumler: list[dict], tohum: int, parca: int = PARCA, toplam: int = TOPLAM_KARAKTER) -> list[dict]:
    """Eşit aralıklı bölümlerden, tohuma göre kaydırılmış parçalar. Kenarlar paragraf sınırına oturur."""
    if not bolumler:
        return []
    rnd = random.Random(tohum)
    uzunluk = max(500, toplam // parca)
    adim = len(bolumler) / parca
    out = []
    for i in range(min(parca, len(bolumler))):
        b = bolumler[min(len(bolumler) - 1, int((i + rnd.random()) * adim))]
        metin = b.get("source") or ""
        if len(metin) <= uzunluk:
            out.append(dict(chapter_no=b.get("chapter_no"), text=metin))
            continue
        bas = rnd.randrange(0, len(metin) - uzunluk)
        bas = metin.rfind("\n", 0, bas) + 1
        son = metin.find("\n", bas + uzunluk)
        out.append(dict(chapter_no=b.get("chapter_no"), text=metin[bas:son if son > 0 else len(metin)].strip()))
    return out


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("’", "'").replace("“", '"').replace("”", '"')).strip()


def _kayitli(kaynak: str, desenler) -> bool:
    """Bir kaydın deseni adayın TAMAMINI karşılıyorsa kayıtlıdır. Parça eşleşmesi sayılmaz: tek
    sözcüklük `Rock` kaydı `Awakened Rock` adayını yutuyordu (ölçüldü, 46 adayda 1)."""
    return any(d.fullmatch(kaynak) for d in desenler)


def adaylari_suz(oneriler: list[dict], parcalar: list[dict], satirlar: list[dict], korpus_bolumleri: list[str],
                 korpus: str, yasaklar=None, politikalar=None) -> list[dict]:
    """Yerel süzgeç: kanıt, kayıtlılık, sıradan sözcük, tekrar, yazma kapısı. Dönüşte `durum` alanı."""
    birlesik = _norm("\n".join(p["text"] for p in parcalar))
    desenler = [translate._term_regex(r["source"]) for r in satirlar]
    out, gorulen = [], set()
    for x in oneriler:
        s, t = str(x.get("source") or "").strip(), str(x.get("target") or "").strip()
        kanit = _norm(str(x.get("kanit") or ""))
        aday = dict(source=s, target=t, tur=x.get("tur"), kanit=x.get("kanit"), durum="aday", nedenler=[])
        if not s or not t or glossary.fold_term(s) in gorulen:
            continue
        gorulen.add(glossary.fold_term(s))
        if not kanit or kanit not in birlesik or _norm(s).casefold() not in kanit.casefold():
            out.append({**aday, "durum": "elendi", "nedenler": ["kanıt örnekte birebir yok"]})
            continue
        if _kayitli(s, desenler):
            out.append({**aday, "durum": "zaten_kayitli"})
            continue
        if sozluk_kapi.genel_sozcuk_mu(s, korpus):
            out.append({**aday, "durum": "elendi", "nedenler": ["kitapta çoğunlukla sıradan sözcük"]})
            continue
        desen = re.compile(r"(?<!\w)" + re.escape(s) + r"(?!\w)")
        bolum_sayisi = sum(1 for m in korpus_bolumleri if desen.search(m))
        aday["bolum_sayisi"] = bolum_sayisi
        if bolum_sayisi < MIN_BOLUM:
            out.append({**aday, "durum": "elendi", "nedenler": [f"yalnız {bolum_sayisi} bölümde geçiyor"]})
            continue
        if s.casefold() != t.casefold():
            kapi = sozluk_kapi.kapi_denetle(s, t, satirlar, yasaklar, politikalar)
            aday["nedenler"] = [n.get("aciklama") or n.get("tur") for n in kapi.get("nedenler") or []]
            if kapi.get("yazim_of"):
                aday["durum"] = "yazim_varyanti"
                aday["yazim_of"] = kapi["yazim_of"]
        out.append(aday)
    return out


def ucretsiz_cagir(user: str, system: str, api_key: str = "") -> tuple[str, str]:
    """Tek model isteği, YALNIZ ücretsiz zincirden: (ham metin, model). Testler bunu taklit eder."""
    api_key = api_key or os.getenv("GEMINI_API_KEY", "")
    if not translate.ceviri_anahtari_var_mi(api_key):
        raise translate.TranslateError(translate.ANAHTAR_YOK_MESAJI)
    response, model = translate._generate_with_fallback(
        translate._gemini_fabrikasi(api_key), sozluk_dogrulama.ucretsiz_zincir(), user,
        system=system, max_tokens=translate.MAX_OUTPUT_TOKENS)
    return (getattr(response, "text", None) or "").strip(), model


def json_coz(ham: str):
    """Modelin JSON yanıtı (``` çitli olabilir); çözülemezse None."""
    ham = (ham or "").strip()
    if ham.startswith("```"):
        ham = ham.strip("`").removeprefix("json").strip()
    try:
        return json.loads(ham)
    except (json.JSONDecodeError, TypeError):
        return None


def _parca_metni(book_slug: str, parcalar: list[dict]) -> str:
    kitap = (library.get_book(book_slug) or {}).get("title") or ""
    return (f"KİTAP: {kitap}\n\n" if kitap else "") + "\n\n".join(
        f"[PARÇA — bölüm {p['chapter_no']}]\n{p['text']}" for p in parcalar)


def tara(book_slug: str, tohum: int, api_key: str = "", parca: int = PARCA, toplam: int = TOPLAM_KARAKTER,
         bolumler: list[dict] | None = None, cagir=None) -> dict:
    """Bir tarama turu (bir model isteği). DB'ye YAZMAZ.

    `bolumler` verilmezse kitabın kaynağı olan bütün bölümleri; ön tarama ilk bölümleri verir."""
    if bolumler is None:
        bolumler = [b for b in cache.kaynak_bolumleri(book_slug) if b.get("source")]
    parcalar = ornekle(bolumler, tohum, parca, toplam)
    ham, model = (cagir or ucretsiz_cagir)(_parca_metni(book_slug, parcalar), TARAMA_INSTRUCTION, api_key)
    veri = json_coz(ham)
    oneriler = [x for x in ((veri.get("terms") if isinstance(veri, dict) else veri) or [])
                if isinstance(x, dict)] if isinstance(veri, (dict, list)) else []
    _t, _k, korpus = cache.kaynak_kapsamasi(book_slug)
    adaylar = adaylari_suz(oneriler, parcalar, glossary.get_glossary_rows(book_slug),
                           [b["source"] for b in bolumler], korpus,
                           glossary.yasaklar(book_slug), glossary.politikalar(book_slug))
    return dict(tohum=tohum, model=model, parcalar=[dict(chapter_no=p["chapter_no"], karakter=len(p["text"]))
                                                   for p in parcalar],
                oneri=len(oneriler), adaylar=adaylar)


# İKİNCİ GEÇİŞ (TransAgents, TACL 2025: "ekle, sonra genel sözcükleri çıkar" iki ayrı ajan). Birinci
# istem hem bulur hem süzer; ayrı bir denetçi sıradan sözcüğü ve betimleyici öbeği daha iyi görür.
ELEME_INSTRUCTION = (
    "Sen İngilizce→Türkçe web roman sözlüğü denetçisisin. Sana bir terim çıkarıcının önerdiği sözlük "
    "adayları kanıt cümleleriyle verilecek. Sözlüğe GİRMEMESİ gerekenleri seç: sıradan sözcükler, "
    "betimleyici öbekler, tek seferlik ifadeler, çevirmenin her seferinde bağlama göre çevirmesi gereken "
    "genel kavramlar (ör. 'the Guard', 'Old Man', 'Main Hall'). Kitap boyunca tutarlı kalması gereken özel "
    "ad, adlandırılmış kavram, rütbe, yetenek ya da sistem terimi ise ELEME.\n"
    "Emin değilsen eleme. Yanıtı SADECE şu JSON ile ver: "
    '{"ele": [{"source": "...", "neden": "kısa Türkçe gerekçe"}]}'
)


def genel_olanlari_ele(book_slug: str, adaylar: list[dict], api_key: str = "", cagir=None) -> list[dict]:
    """`aday` durumundakileri ikinci bir model isteğiyle süz; elenenler `elendi` olur. Yeni liste döner."""
    bekleyen = [a for a in adaylar if a.get("durum") == "aday"]
    if not bekleyen:
        return adaylar
    user = json.dumps([{"source": a["source"], "target": a["target"], "tur": a.get("tur"), "kanit": a.get("kanit")}
                       for a in bekleyen], ensure_ascii=False)
    ham, _model = (cagir or ucretsiz_cagir)(user, ELEME_INSTRUCTION, api_key)
    veri = json_coz(ham)
    ele = {}
    for x in (veri.get("ele") if isinstance(veri, dict) else None) or []:
        if isinstance(x, dict) and x.get("source"):
            ele[glossary.fold_term(str(x["source"]))] = str(x.get("neden") or "").strip()
    out = []
    for a in adaylar:
        neden = ele.get(glossary.fold_term(a["source"])) if a.get("durum") == "aday" else None
        if neden is not None:
            a = {**a, "durum": "elendi", "nedenler": [*a.get("nedenler", []), "ikinci geçiş: " + (neden or "genel")]}
        out.append(a)
    return out


ON_TARAMA_BOLUM = 10  # soğuk başlangıçta örneklenen ilk bölüm sayısı
ON_TARAMA_KARAKTER = 9000


def on_tara(book_slug: str, bolumler: list[dict], api_key: str = "", ikinci_gecis: bool = True,
            yaz: bool = True, cagir=None) -> dict:
    """YENİ kitabın ilk bölümlerinden sözlük ön taraması (plan Faz 3, soğuk başlangıç).

    Bugün ilk bölümler sözlüksüz çevriliyor: aday ancak çeviri sırasında algılanınca girer ve
    doğrulanana kadar bekler. Ön tarama aynı adayları ÇEVİRİDEN ÖNCE önerir. Kural değişmez:
    `yaz` ise kalan adaylar `origin='auto'` ile yazma kapısından geçer, ÖNCE BEKLEME kuralıyla
    tutulur ve arka plan model doğrulamasından geçmeden prompt'a girmez. Kayıt, adayın ilk
    geçtiği bölümle yazılır (köken)."""
    bolumler = [b for b in bolumler if b.get("source")]
    sonuc = tara(book_slug, 0, api_key, parca=min(PARCA, max(1, len(bolumler))), toplam=ON_TARAMA_KARAKTER,
                 bolumler=bolumler, cagir=cagir)
    adaylar = sonuc["adaylar"]
    if ikinci_gecis:
        adaylar = genel_olanlari_ele(book_slug, adaylar, api_key, cagir)
    yazilan = []
    if yaz:
        for a in adaylar:
            if a.get("durum") != "aday":
                continue
            desen = re.compile(r"(?<!\w)" + re.escape(a["source"]) + r"(?!\w)")
            ilk = next((b.get("chapter_no") for b in bolumler if desen.search(b["source"])), None)
            if a["source"].casefold() == a["target"].casefold():
                glossary.merge_names(book_slug, [a["source"]], "auto", ilk)
            else:
                glossary.merge_terms(book_slug, {a["source"]: a["target"]}, "auto", ilk)
            yazilan.append(a["source"])
        if yazilan:
            sozluk_dogrulama.arka_planda_dogrula(book_slug)
    return {**sonuc, "adaylar": adaylar, "yazilan": yazilan}


def onaylananlari_ekle(book_slug: str, adaylar: list[dict]) -> dict[str, str]:
    """Kullanıcının `onay: true` verdiği adaylar. Normal yazma kapısından geçer (`merge_terms`/`merge_names`)."""
    terimler = {a["source"]: a["target"] for a in adaylar
                if a.get("onay") is True and a.get("durum") == "aday" and a["source"].casefold() != a["target"].casefold()}
    adlar = [a["source"] for a in adaylar
             if a.get("onay") is True and a.get("durum") == "aday" and a["source"].casefold() == a["target"].casefold()]
    eklenen = dict(glossary.merge_terms(book_slug, terimler, "auto") or {})
    eklenen.update(glossary.merge_names(book_slug, adlar, "auto") or {})
    return eklenen
