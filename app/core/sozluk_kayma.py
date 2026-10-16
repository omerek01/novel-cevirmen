"""Sözlük DIŞI terim kayması madenciliği (2026-10-16, Faz A8; kör nokta K10).

Saf modül, API çağırmaz. Sözlükte kaydı olmayan bir terim çevirilerde birden çok
Türkçe karşılıkla yerleşebiliyor (ölçülen vaka, SS: `Captain` 80 kez "Yüzbaşı", 7 kez
"Kaptan") ve hiçbir denetim buna bakmıyordu: uyum denetimleri yalnız KAYITLI terimleri
görür, model her bölümde yeniden karar verir.

Yöntem bilerek muhafazakâr (atfı güvenilir olan geçişler sayılır, gerisi atlanır):
* İngilizce paragrafta sözlükle açıklanmayan, cümle ortasında büyük harfle geçen TEK bir
  aday sözcük olmalı (iki aday varsa hangi Türkçe sözcüğün hangisine ait olduğu bilinmez).
* Türkçe paragrafta sözlük karşılıklarıyla ve İngilizce aynen kalan adlarla açıklanmayan,
  cümle ortasında büyük harfle geçen TEK bir sözcük kalmalı; o sözcük adayın karşılığıdır.
* Aday çeviride AYNEN geçiyorsa "İngilizce korunmuş" sayılır.
Çıktı yalnız ÖNERİDİR: sözlüğe yazılırsa `merge_terms(..., "auto")` ile yazma kapısından
ve bekleme + doğrulamadan geçer, kararı kullanıcı verir.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict

from . import turkce_eslesme

_EN_ADAY = re.compile(r"(?<=[a-z,;] )[A-Z][a-z]{2,}(?![\w'’-])")
_TR_SOZCUK = re.compile(r"(?<!\w)[A-ZÇĞİÖŞÜ][\wçğıöşü]+(?:['’]\w+)?")
# Cümle ortasında büyük harfle gelen ama terim olmayan sık İngilizce sözcükler.
_EN_DEGIL = frozenset("""The And But Then His Her Their They She He Its Our Your You Not
Mr Mrs Ms Sir Lady Lord God Gods""".split())

EN_AZ_GECIS = 5
EN_AZ_BOLUM = 3
# İkinci karşılık hem PAY hem SAYI eşiğini geçmeli. Kalibrasyon (SS + RSSG, kök gruplu):
# bilinen gerçek vaka `Captain` -> Kaptan ~%10 pay ile 4 geçiş; tek seferlik gürültüler
# ("Fate" -> İp, "Transcended" -> Yüce) 1-2 geçiş. Pay %15'te Captain kaçıyordu.
IKINCI_PAY = 0.08
IKINCI_EN_AZ = 3


def _kok(sozcuk: str) -> str:
    return re.split(r"['’]", sozcuk)[0]


def _ortu(metin: str, kaynaklar: list[str]) -> list[tuple[int, int]]:
    """Sözlük kayıtlarının metindeki aralıkları (büyük-küçük harf duyarsız)."""
    out = []
    kucuk = metin.lower()
    for s in kaynaklar:
        if s.lower() in kucuk:
            out += [m.span() for m in re.finditer(rf"(?<!\w){re.escape(s)}(?!\w)", metin, re.IGNORECASE)]
    return out


def paragraf_atfi(en: str, tr: str, sozluk: dict[str, str]) -> tuple[str, str] | None:
    """(İngilizce aday, Türkçe karşılık ya da "=" (aynen korunmuş)) — atıf güvenilmezse None."""
    ortu = _ortu(en, list(sozluk))
    adaylar = {m.group(0) for m in _EN_ADAY.finditer(en)
               if m.group(0) not in _EN_DEGIL
               and not any(a <= m.start() < b for a, b in ortu)}
    if len(adaylar) != 1:
        return None
    aday = adaylar.pop()
    if re.search(rf"(?<!\w){re.escape(aday)}", tr):
        return aday, "="
    aciklanan = [t for s, t in sozluk.items() if t and s.lower() in en.lower()]
    kalan = set()
    for m in _TR_SOZCUK.finditer(tr):
        once = tr[: m.start()].rstrip(" \"'“‘(*[")
        if not once or once[-1] in ".!?:…":
            continue  # cümle başı: büyük harf terim kanıtı değil
        k = _kok(m.group(0))
        if k in en:  # İngilizce aynen kalan başka bir ad
            continue
        if any(turkce_eslesme.karsilik_gecer(t, m.group(0)) or k in t for t in aciklanan):
            continue
        kalan.add(k)
    if len(kalan) != 1:
        return None
    return aday, kalan.pop()


def _koke_grupla(c: Counter) -> Counter:
    """Çekimli biçimleri köküne topla ("anılar", "anıları" -> "anı"; "yeteneği" -> "yetenek").

    Kalibrasyon (SS): gruplamasız ilk koşuda 16 "kayan" terimin çoğu yalnız çekim
    farkıydı (`Memories` -> Anılar/Anı/Anıları). Kök = grubun en kısa biçimi."""
    out: Counter = Counter()
    for b in sorted(c, key=len):
        kok = next((k for k in out if k != "=" and b != "=" and turkce_eslesme.ayni_karsilik(b, k)), b)
        out[kok] += c[b]
    return out


def kaymalar(paragraflar, sozluk_bolum) -> list[dict]:
    """`paragraflar`: (bölüm no, en, tr) akışı; `sozluk_bolum(no)` o bölümün sözlüğü.

    Döner: kayan terimler (≥ EN_AZ_GECIS geçiş, ≥ EN_AZ_BOLUM bölüm, ikinci karşılık
    ≥ IKINCI_PAY pay ve ≥ IKINCI_EN_AZ geçiş), en sık karşılıkla, geçiş sayısına göre sıralı."""
    bicim: dict[str, Counter] = defaultdict(Counter)
    bolumler: dict[str, set] = defaultdict(set)
    gorunen: dict[tuple, Counter] = defaultdict(Counter)
    for no, en, tr in paragraflar:
        atif = paragraf_atfi(en, tr, sozluk_bolum(no))
        if not atif:
            continue
        aday, karsilik = atif
        anahtar = "=" if karsilik == "=" else turkce_eslesme.isaretsiz(karsilik)
        bicim[aday][anahtar] += 1
        gorunen[(aday, anahtar)][karsilik] += 1
        bolumler[aday].add(no)
    out = []
    for aday, ham in bicim.items():
        c = _koke_grupla(ham)
        toplam = sum(c.values())
        if toplam < EN_AZ_GECIS or len(bolumler[aday]) < EN_AZ_BOLUM or len(c) < 2:
            continue
        (b1, n1), (b2, n2) = c.most_common(2)
        if n2 / toplam < IKINCI_PAY or n2 < IKINCI_EN_AZ:
            continue
        out.append({
            "kaynak": aday, "gecis": toplam, "bolum": len(bolumler[aday]),
            "karsiliklar": [{"karsilik": "(İngilizce)" if b == "=" else gorunen[(aday, b)].most_common(1)[0][0],
                             "sayi": n} for b, n in c.most_common(4)],
        })
    return sorted(out, key=lambda x: -x["gecis"])
