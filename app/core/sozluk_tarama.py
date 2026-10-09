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


def tara(book_slug: str, tohum: int, api_key: str = "", parca: int = PARCA, toplam: int = TOPLAM_KARAKTER) -> dict:
    """Bir tarama turu (bir model isteği). DB'ye YAZMAZ."""
    api_key = api_key or os.getenv("GEMINI_API_KEY", "")
    if not translate.ceviri_anahtari_var_mi(api_key):
        raise translate.TranslateError(translate.ANAHTAR_YOK_MESAJI)
    bolumler = [b for b in cache.kaynak_bolumleri(book_slug) if b.get("source")]
    parcalar = ornekle(bolumler, tohum, parca, toplam)
    kitap = (library.get_book(book_slug) or {}).get("title") or ""
    user = (f"KİTAP: {kitap}\n\n" if kitap else "") + "\n\n".join(
        f"[PARÇA — bölüm {p['chapter_no']}]\n{p['text']}" for p in parcalar)
    response, model = translate._generate_with_fallback(
        translate._gemini_fabrikasi(api_key), sozluk_dogrulama.ucretsiz_zincir(), user,
        system=TARAMA_INSTRUCTION, max_tokens=translate.MAX_OUTPUT_TOKENS)
    ham = (getattr(response, "text", None) or "").strip()
    if ham.startswith("```"):
        ham = ham.strip("`").removeprefix("json").strip()
    try:
        veri = json.loads(ham)
        oneriler = [x for x in (veri.get("terms") if isinstance(veri, dict) else veri) or [] if isinstance(x, dict)]
    except (json.JSONDecodeError, TypeError, AttributeError):
        oneriler = []
    _t, _k, korpus = cache.kaynak_kapsamasi(book_slug)
    adaylar = adaylari_suz(oneriler, parcalar, glossary.get_glossary_rows(book_slug),
                           [b["source"] for b in bolumler], korpus,
                           glossary.yasaklar(book_slug), glossary.politikalar(book_slug))
    return dict(tohum=tohum, model=model, parcalar=[dict(chapter_no=p["chapter_no"], karakter=len(p["text"]))
                                                   for p in parcalar],
                oneri=len(oneriler), adaylar=adaylar)


def onaylananlari_ekle(book_slug: str, adaylar: list[dict]) -> dict[str, str]:
    """Kullanıcının `onay: true` verdiği adaylar. Normal yazma kapısından geçer (`merge_terms`/`merge_names`)."""
    terimler = {a["source"]: a["target"] for a in adaylar
                if a.get("onay") is True and a.get("durum") == "aday" and a["source"].casefold() != a["target"].casefold()}
    adlar = [a["source"] for a in adaylar
             if a.get("onay") is True and a.get("durum") == "aday" and a["source"].casefold() == a["target"].casefold()]
    eklenen = dict(glossary.merge_terms(book_slug, terimler, "auto") or {})
    eklenen.update(glossary.merge_names(book_slug, adlar, "auto") or {})
    return eklenen
