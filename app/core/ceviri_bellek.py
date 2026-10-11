"""Bölümler arası tutarlılık belleği: önceki bölümlerden ilgili kaynak→çeviri çiftleri.

Ölçülen boşluk (2026-10-11, shadow-slave 850-967): askerî rütbe `Captain` 64
yerde "Yüzbaşı", 5 yerde "Kaptan" çevrildi; `sir` çoğunlukla "efendim", arada
"kaptanım"/"komutanım". Sıradan sözcük oldukları için sözlükte yoklar ve model her
bölümde yeniden karar veriyordu. Bölüm tek istekte çevrildiği için bölüm İÇİ bağlam
zaten var; eksik olan bölümler ARASI hafızaydı.

Yaklaşım DelTA'nın (ICLR 2025) kısa/uzun vadeli iki dilli belleğinin ek model
çağrısı yapmayan, sözcüksel uyarlamasıdır: bu bölümde geçen büyük harfli adlar ve
hitap/rütbe sözcükleri önceki bölümlerin hizalı paragraflarında aranır; seyrek ortak
sözcük ağır basar, aynı bilgiyi tekrarlayan çift yerine yeni sözcük getiren seçilir.
Örnekler önceki MODEL çevirileridir, onaylı değildir: tekil bir hata da taşınabilir.
Bu yüzden talimat örnekleri yalnız tutarlılık için verir; anlamın kaynağı çevrilecek
metindir. Gelecek bölüm havuza giremez (çağıran `bolum < mevcut` süzer, `sec` de).
"""
from __future__ import annotations

import math
import re

MAX_CIFT = 10
MAX_EN_KARAKTER = 500
KISA_VADELI = 3
_KAPSAM_CARPANI = 0.3
_DIYALOG_CARPANI = 1.2

_ISARETCI = re.compile(r"\[\[\d+\]\]\s*")
_SOZCUK = re.compile(r"[A-Za-z][A-Za-z0-9'’-]*")
_DIYALOG = re.compile(r'["“”]')

# Büyük harfle başladığı hâlde ad/unvan olmayan sık sözcükler (cümle başı vb.).
_DURAK = {
    "a", "an", "the", "and", "but", "or", "nor", "so", "yet", "for", "if", "as", "at",
    "in", "on", "of", "to", "by", "with", "from", "into", "onto", "over", "under",
    "after", "before", "then", "when", "while", "where", "what", "why", "how", "who",
    "whom", "which", "whose", "that", "this", "these", "those", "there", "here",
    "he", "she", "it", "they", "we", "i", "you", "his", "her", "its", "their", "our",
    "my", "your", "him", "them", "us", "me", "not", "no", "yes", "oh", "ah", "well",
    "now", "just", "still", "even", "only", "also", "too", "very", "all", "some",
    "any", "each", "every", "both", "either", "neither", "one", "two", "three",
    "is", "was", "were", "are", "be", "been", "being", "do", "did", "does", "done",
    "have", "had", "has", "can", "could", "will", "would", "shall", "should", "may",
    "might", "must", "let", "hey", "huh", "hmm", "uh", "um", "okay", "ok", "really",
    "maybe", "perhaps", "however", "instead", "suddenly", "finally", "indeed",
    "meanwhile", "although", "though", "because", "since", "until", "unless",
    "again", "once", "soon", "never", "always", "sometimes", "somehow", "anyway",
    "luckily", "unfortunately", "of course", "chapter", "translator", "editor",
}
# Küçük harfle de geçen hitap/rütbe sözcükleri: bölümler arası tutarsızlığın
# ölçülen kaynağı. Büyük harfli unvanlar (General, Master, Elder) ad kuralıyla yakalanır.
_HITAP = {
    "sir", "madam", "ma'am", "ma’am", "maam", "captain", "lieutenant", "sergeant",
    "corporal", "colonel", "commander", "professor", "highness", "majesty", "lord",
    "lady", "mister", "senior", "boss",
}


def _temiz(metin: str) -> str:
    return _ISARETCI.sub("", metin or "").strip()


def _sozcukler(metin: str) -> set[str]:
    return {s.lower() for s in _SOZCUK.findall(metin)}


def anahtarlar(paragraflar: list[str]) -> set[str]:
    """Bölümün bellek anahtarları: büyük harfli adlar + hitap/rütbe sözcükleri."""
    sonuc: set[str] = set()
    for p in paragraflar:
        for s in _SOZCUK.findall(p):
            k = s.lower()
            if (s[0].isupper() and len(s) > 1 and k not in _DURAK) or k in _HITAP:
                sonuc.add(k)
    return sonuc


def havuz_kur(satirlar) -> list[dict]:
    """(bölüm_no, hizalı kaynak, çeviri) satırlarından paragraf çiftleri.

    Hizası tutmayan bölüm (paragraf sayıları farklı) atlanır: hangi Türkçe
    paragrafın hangi kaynağa karşılık geldiği bilinmez."""
    havuz = []
    for bolum, en, tr in satirlar:
        en_p = [p.strip() for p in (en or "").split("\n\n")]
        tr_p = [p.strip() for p in (tr or "").split("\n\n")]
        if not en or not tr or len(en_p) != len(tr_p):
            continue
        havuz.extend({"bolum": bolum, "en": e, "tr": t} for e, t in zip(en_p, tr_p) if e and t)
    return havuz


def sec(havuz: list[dict], kaynak_paragraflari: list[str], en_fazla: int = MAX_CIFT,
        bolum_no: int | None = None) -> list[dict]:
    """Bu bölümle ortak ad/hitap taşıyan en bilgilendirici çiftler (kronolojik)."""
    adaylar = []
    for sira, x in enumerate(havuz):
        if bolum_no is not None and not (type(x.get("bolum")) is int and x["bolum"] < bolum_no):
            continue
        en, tr = _temiz(x.get("en", "")), _temiz(x.get("tr", ""))
        if not en or not tr or len(en) > MAX_EN_KARAKTER:
            continue
        adaylar.append({"bolum": x.get("bolum"), "en": en, "tr": tr, "_sira": sira,
                        "_sozcuk": _sozcukler(en), "_diyalog": bool(_DIYALOG.search(en))})
    anahtar = anahtarlar(kaynak_paragraflari)
    if not adaylar or not anahtar:
        return []
    df: dict[str, int] = {}
    for a in adaylar:
        for k in a["_sozcuk"] & anahtar:
            df[k] = df.get(k, 0) + 1
    agirlik = {k: math.log(1 + len(adaylar) / (1 + n)) for k, n in df.items()}
    secilen: list[dict] = []
    while len(secilen) < en_fazla:
        en_iyi, en_iyi_puan = None, 0.0
        for a in adaylar:
            if a in secilen:
                continue
            puan = sum(agirlik[k] for k in a["_sozcuk"] & anahtar if k in agirlik)
            puan *= _DIYALOG_CARPANI if a["_diyalog"] else 1.0
            anahtar_ = (puan, a["bolum"] or 0, -a["_sira"])
            if puan > 0 and (en_iyi is None or anahtar_ > (en_iyi_puan, en_iyi["bolum"] or 0, -en_iyi["_sira"])):
                en_iyi, en_iyi_puan = a, puan
        if en_iyi is None:
            break
        secilen.append(en_iyi)
        for k in en_iyi["_sozcuk"] & anahtar:
            if k in agirlik:
                agirlik[k] *= _KAPSAM_CARPANI
    secilen.sort(key=lambda a: (a["bolum"] or 0, a["_sira"]))
    return [{"bolum": a["bolum"], "en": a["en"], "tr": a["tr"]} for a in secilen]


def son_ciftler(kaynak: str, ceviri: str, adet: int = KISA_VADELI) -> list[dict]:
    """Önceki bölümün son paragraf çiftleri (kısa vadeli bellek); hizasızsa boş."""
    en_p = [p.strip() for p in (kaynak or "").split("\n\n") if p.strip()]
    tr_p = [p.strip() for p in (ceviri or "").split("\n\n") if p.strip()]
    if not en_p or len(en_p) != len(tr_p):
        return []
    return [{"en": _temiz(e), "tr": _temiz(t)} for e, t in zip(en_p[-adet:], tr_p[-adet:])]


def metin(uzun: list[dict], kisa: list[dict]) -> str:
    """Çeviri isteğine eklenen bellek bloğu; bellek boşsa boş dizgi (istem değişmez)."""
    if not uzun and not kisa:
        return ""
    satirlar = [
        "TUTARLILIK BELLEĞİ — aşağıdaki çiftler bu kitabın ÖNCEKİ bölümlerinde kullanılan "
        "çevirilerdir. Yalnız TUTARLILIK içindir: hitap (sen/siz, efendim), rütbe ve unvanlar, "
        "karakterlerin konuşma biçimi ve tekrar eden ifadeler bu çevirilerdeki gibi kalsın. "
        "Bu çiftleri ÇEVİRME ve çıktına EKLEME; anlam için her zaman ÇEVRİLECEK METNE bak."
    ]
    for x in uzun:
        satirlar.append(f"(Bölüm {x['bolum']})\nEN: {x['en']}\nTR: {x['tr']}")
    if kisa:
        satirlar.append("ÖNCEKİ BÖLÜMÜN SON PARAGRAFLARI (kaynak → çeviri):")
        satirlar.extend(f"EN: {x['en']}\nTR: {x['tr']}" for x in kisa)
    return "\n\n".join(satirlar)
