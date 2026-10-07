"""Kapsama İPUÇLARI (Faz 2A v6) — model çağrısından önce, YALNIZ kaynak metinden.

İpucu bir OLGU DEĞİLDİR, kanıt değildir, doğrulayıcıyı atlatmaz: "bu cümle grafiğe
değer bir bilgi içerebilir, dikkatle bak" demektir. Model ipucunu reddedebilir
(CHECK != EMIT); kanıt yine kaynaktan birebir kopyalanır. Tarayıcı N-1 bilgisini
BİLMEZ — yeniliğe model karar verir. İkinci bir LLM çağrısı YOK.

Yanlış pozitif kabul edilebilir (model eler); patlama edilemez: bölüm başına en çok
`IPUCU_SINIRI` ipucu, metni `IPUCU_TOKEN_BUTCESI` içinde. Kategori listesi GENELdir;
bir kitabın ya da bölümün adı burada geçmez.
"""
from __future__ import annotations

import re

IPUCU_SINIRI = 12
IPUCU_TOKEN_BUTCESI = 800
SPAN_AZAMI = 220  # karakter
# Tek bir kategori bütün yerleri kapmasın (ölçüldü: ölüm yoğun bölümde 12/12 death_life).
KATEGORI_SINIRI = 4

# Öncelik sırası (küçük = önce). Tek cümle birden çok kategoriye uyarsa en öncelikli kalır.
KATEGORILER: tuple[tuple[str, int, re.Pattern], ...] = (
    ("identity", 1, re.compile(r"\btrue names?\b|\bidentity\b|\breal name\b", re.I)),
    ("death_life", 2, re.compile(
        r"\b(?:dead|died|dies|killed|kills|slain|slew|corpse|survived|survive|alive|perished|murdered)\b", re.I)),
    ("change", 3, re.compile(
        r"\b(?:no longer|ceased|betray\w*|transformed|evolved|was gone|ended|lost (?:his|her|their|its)\b)", re.I)),
    ("teaching", 4, re.compile(r"\b(?:taught|teacher|trained|mentor\w*|learned from|learnt from|student|disciple)\b", re.I)),
    ("lineage", 4, re.compile(
        r"\b(?:son|daughter|father|mother|sibling|brother|sister|descendant|ancestor|bloodline|lineage|heir|heiress)\b", re.I)),
    ("epistemic", 5, re.compile(
        r"\b(?:believed|rumou?red|rumou?rs?|supposedly|allegedly|thought to|said to|legend has it)\b", re.I)),
    ("title_alias", 6, re.compile(
        r"\b(?:known as|called|titled|title|alias|nicknamed|was appointed|was named)\b"
        # Genel unvan biçimi: "Ad, the Unvan of Yer" / "Ad — the Unvan" (büyük harfli)
        r"|\b[A-Z][\w’']+\s*[,—–-]\s*the\s+[A-Z][\w’']+(?:\s+of\s+(?:the\s+)?[A-Z][\w’']+)?")),
    ("structured", 7, re.compile(
        r"^\[?(?:\.\.\.)?(?:Attributes?|Abilities|Aspect(?: Ability)?(?: Name)?|Rank|Class|True Name|Flaw)\b[^:]{0,20}:", re.I)),
)
# Kategori içi sıralama (genel): güçlü sözcük + cümle ORTASINDA adlandırılmış varlık.
_GUCLU = re.compile(r"\b(?:dead|died|killed|slain|slew|corpse|perished|murdered|still alive|true names?|taught|"
                    r"betray\w*|no longer|heir|descendant|rumou?red|known as)\b", re.I)
_ORTA_AD = re.compile(r"(?<=[a-z,;] )[A-Z][a-z’']+")


def _guc(cumle: str) -> int:
    return (2 if _ORTA_AD.search(cumle) else 0) + (1 if _GUCLU.search(cumle) else 0)


_CUMLE = re.compile(r"[^.!?\n]+(?:[.!?]+[\"'”’]?|$)")


def _tok(metin: str) -> int:
    return (len(metin) + 3) // 4


def _kisalt(cumle: str, m: re.Match) -> str:
    if len(cumle) <= SPAN_AZAMI:
        return cumle
    orta = (m.start() + m.end()) // 2
    bas = max(0, min(orta - SPAN_AZAMI // 2, len(cumle) - SPAN_AZAMI))
    return cumle[bas:bas + SPAN_AZAMI].strip()


def ipuclari(kaynak: str, haric_kanitlar: tuple[str, ...] = ()) -> list[dict]:
    """[{kategori, span, konum}] — kaynak sırasına göre, en çok IPUCU_SINIRI.

    `haric_kanitlar`: aynı bölümün deterministik planının kanıt paragrafları; zaten
    çıkarılmış rün satırları ipucu yapılmaz (modeli tekrara itmesin)."""
    haric = {re.sub(r"\s+", " ", h).strip() for h in haric_kanitlar}
    adaylar: list[dict] = []
    konum = 0
    for paragraf in (kaynak or "").split("\n"):
        ham = paragraf
        paragraf = paragraf.strip()
        if paragraf and re.sub(r"\s+", " ", paragraf) not in haric:
            for cm in _CUMLE.finditer(paragraf):
                cumle = cm.group(0).strip()
                if len(cumle) < 6:
                    continue
                en_iyi = None
                for ad, oncelik, desen in KATEGORILER:
                    m = desen.search(cumle)
                    if m and (en_iyi is None or oncelik < en_iyi[1]):
                        en_iyi = (ad, oncelik, m)
                if en_iyi:
                    adaylar.append({"kategori": en_iyi[0], "oncelik": en_iyi[1], "guc": _guc(cumle),
                                    "span": _kisalt(cumle, en_iyi[2]), "konum": konum + cm.start()})
        konum += len(ham) + 1
    # Aynı span bir kez; sonra öncelik, sonra kaynak sırası.
    tekil: dict[str, dict] = {}
    for a in adaylar:
        tekil.setdefault(a["span"], a)
    secilen, toplam, sayac = [], 0, {}
    for a in sorted(tekil.values(), key=lambda a: (a["oncelik"], -a["guc"], a["konum"])):
        t = _tok(a["span"]) + 6
        if len(secilen) >= IPUCU_SINIRI or toplam + t > IPUCU_TOKEN_BUTCESI \
                or sayac.get(a["kategori"], 0) >= KATEGORI_SINIRI:
            continue
        secilen.append(a)
        sayac[a["kategori"]] = sayac.get(a["kategori"], 0) + 1
        toplam += t
    secilen.sort(key=lambda a: a["konum"])
    return [{"kategori": a["kategori"], "span": a["span"], "konum": a["konum"]} for a in secilen]


IPUCU_BASLIGI = "COVERAGE CUES — THESE ARE NOT FACTS"


def ipucu_bolumu(liste: list[dict]) -> str:
    if not liste:
        return f"{IPUCU_BASLIGI}:\n(none)"
    satirlar = [f"[{i}] ({c['kategori']}) {c['span']}" for i, c in enumerate(liste, 1)]
    return f"{IPUCU_BASLIGI}:\n" + "\n".join(satirlar)
