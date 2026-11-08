"""Öbek modu (hızlı okuma planı Adım C, 2026-11-08; kullanıcı kararı "Deneme modu,
Gemini öbekleri"): Türkçe paragrafı 2-5 sözcüklük anlam öbeklerine böler.

Dayanak: metni anlam öbeklerine bölerek göstermek (phrase-cued text, Walker 2005
visual-syntactic text formatting) akıcılığı zayıf okurda anlamayı artırdı; akıcı
yetişkinde etkisi belirsiz, bu yüzden deneme modudur ve etkisi kişisel hız ölçümüyle
sınanır. Göz egzersiziyle görme alanı genişletilemez (Rayner 2010, 2016).

GÜVEN SINIRI: model metni değiştirebilir. Model çıktısı paragrafın KENDİ sözcüklerini
sırasıyla vermiyorsa (bir harf bile farklıysa) o paragraf reddedilir ve kural tabanlı
yedek kullanılır. Saklanan şey metnin kopyası değil, paragraf başına öbek BİTİŞ
konumlarıdır. Bölüm yeniden çevrilirse (`kaynak_sha256` değişir) öbekler bayatlar.

Üretim işlevi `uret(user, system, asama) -> (yanıt, model)` dışarıdan verilir
(`ozet_zinciri` kalıbı); testler sahte üretici verir.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time

from . import ceviri_kalite, db

EN_COK_SOZCUK = 8  # modelin öbeği bundan uzunsa paragraf reddedilir
KURAL_EN_COK = 5  # kural yedeğinde öbek bundan uzunsa bölünür

OBEK_TALIMATI = """Sen bir Türkçe okuma yardımcısısın. Sana bir romandan Türkçe paragraflar \
verilecek. Her paragrafı, okurun gözünün tek bakışta alabileceği ANLAM ÖBEKLERİNE böl.

Kurallar:
- Paragrafın HİÇBİR harfini, noktalamasını ya da sözcük sırasını değiştirme; yalnız böl.
- Öbek 2-5 sözcük olsun; tek sözcüklük öbek yalnız gerekirse.
- Bir arada tut: özne öbeği ("Gümüş Kule'nin çanı"), eylem öbeği ("uzaktan üç kez çaldı"),
  ad tamlaması, edat öbeği, -ken / -ınca / -ıp / -dığında ekli yan cümle parçası.
- Noktalamadan sonra (virgül, nokta, noktalı virgül, iki nokta, soru, ünlem) öbek biter.

Yanıtı YALNIZ şu JSON olarak ver, açıklama ekleme:
{"obekler": [["öbek 1", "öbek 2", ...], ...]}
Dış listede paragraf sayısı kadar eleman olmalı, sıra korunmalı."""

_BAGLAC = {"ve", "ama", "fakat", "ancak", "ki", "çünkü", "ile", "veya", "yahut", "hem",
           "ya", "oysa", "yoksa", "sonra", "önce", "gibi", "kadar", "için"}
_YAN_CUMLE = re.compile(r"(ken|ınca|ince|unca|ünce|ıp|ip|up|üp|dığında|diğinde|duğunda|"
                        r"düğünde|tığında|tiğinde|tuğunda|tüğünde|madan|meden|arak|erek)[,;:.!?…]*$")
_NOKTALAMA_SON = re.compile(r"[,;:.!?…—\"”’)]$")


def paragraflar(metin: str) -> list[str]:
    """Okuyucuyla aynı bölme: boş satırla ayrılmış, kırpılmış, boş olmayan."""
    return [p.strip() for p in re.split(r"\n\n+", metin or "") if p.strip()]


def _sozcukler(p: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in re.finditer(r"\S+", p)]


def kural_obekleri(p: str) -> list[int]:
    """Kural tabanlı öbek bitiş konumları (karakter sırası, son öbek len(p)'ye kadar)."""
    sozcuk = _sozcukler(p)
    if not sozcuk:
        return []
    gruplar: list[list[tuple[int, int]]] = [[]]
    for i, (a, b) in enumerate(sozcuk):
        w = p[a:b].lower().strip("\"“”'‘’(")
        # Bağlaç yeni öbeğe başlar (önceki öbek boş değilse).
        if w in _BAGLAC and gruplar[-1]:
            gruplar.append([])
        gruplar[-1].append((a, b))
        son = i == len(sozcuk) - 1
        if not son and (_NOKTALAMA_SON.search(p[a:b]) or _YAN_CUMLE.search(w)):
            gruplar.append([])
    # Uzun öbekleri böl, tek sözcüklüğü bir sonrakine kat (noktalamayla bitmiyorsa).
    duz: list[list[tuple[int, int]]] = []
    for g in gruplar:
        if not g:
            continue
        while len(g) > KURAL_EN_COK:
            duz.append(g[:3])
            g = g[3:]
        duz.append(g)
    birlesik: list[list[tuple[int, int]]] = []
    for g in duz:
        onceki = birlesik[-1] if birlesik else None
        if (onceki and len(onceki) == 1 and not _NOKTALAMA_SON.search(p[onceki[0][0]:onceki[0][1]])
                and len(onceki) + len(g) <= KURAL_EN_COK):
            onceki.extend(g)
        else:
            birlesik.append(list(g))
    return [g[-1][1] for g in birlesik]


def _model_sinirlari(p: str, parcalar) -> list[int] | None:
    """Model öbeklerini paragrafta sırayla bul; harf farkı / uzun öbek / boşluk varsa None."""
    if not isinstance(parcalar, list) or not parcalar:
        return None
    konum, sinirlar = 0, []
    for parca in parcalar:
        if not isinstance(parca, str) or not parca.strip():
            return None
        parca = parca.strip()
        if len(parca.split()) > EN_COK_SOZCUK:
            return None
        bulunan = p.find(parca, konum)
        # Öbekler arasında yalnız boşluk olabilir: atlanan metin = model bir şeyi değiştirdi.
        if bulunan < 0 or p[konum:bulunan].strip():
            return None
        konum = bulunan + len(parca)
        sinirlar.append(konum)
    return sinirlar if not p[konum:].strip() else None


def model_ile_obekle(paraflar: list[str], uret) -> tuple[list[list[int]], str | None, int]:
    """(sınırlar, model, reddedilen paragraf sayısı). Hata/bozuk yanıtta hepsi kural."""
    yanit, model = uret(json.dumps({"paragraflar": paraflar}, ensure_ascii=False),
                        OBEK_TALIMATI, "obek")
    try:
        liste = ceviri_kalite.yanit_coz(yanit).get("obekler")
    except ceviri_kalite.KaliteHatasi:
        liste = None
    if not isinstance(liste, list) or len(liste) != len(paraflar):
        return [kural_obekleri(p) for p in paraflar], model, len(paraflar)
    sonuc, red = [], 0
    for p, parcalar in zip(paraflar, liste):
        s = _model_sinirlari(p, parcalar)
        if s is None:
            red += 1
            s = kural_obekleri(p)
        sonuc.append(s)
    return sonuc, model, red


def _connect() -> sqlite3.Connection:
    conn = db.connect()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS obekler (
            url TEXT NOT NULL UNIQUE,
            book_slug TEXT,
            kaynak_sha256 TEXT NOT NULL,
            sinirlar_json TEXT NOT NULL,
            model TEXT,
            reddedilen INTEGER NOT NULL DEFAULT 0,
            ts REAL
        )
        """
    )
    return conn


def ozet_al(metin: str) -> str:
    return hashlib.sha256((metin or "").encode("utf-8")).hexdigest()


def kayitli(url: str, sha: str) -> list[list[int]] | None:
    conn = _connect()
    try:
        row = conn.execute("SELECT kaynak_sha256, sinirlar_json FROM obekler WHERE url = ?",
                           (url,)).fetchone()
    finally:
        conn.close()
    if not row or row[0] != sha:
        return None  # yok ya da bölüm yeniden çevrilmiş: bayat
    return json.loads(row[1])


def kaydet(url: str, book_slug: str | None, sha: str, sinirlar, model, reddedilen: int) -> None:
    try:
        conn = _connect()
        try:
            conn.execute(
                "INSERT INTO obekler (url, book_slug, kaynak_sha256, sinirlar_json, model,"
                " reddedilen, ts) VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(url) DO UPDATE SET"
                " book_slug=excluded.book_slug, kaynak_sha256=excluded.kaynak_sha256,"
                " sinirlar_json=excluded.sinirlar_json, model=excluded.model,"
                " reddedilen=excluded.reddedilen, ts=excluded.ts",
                (url, book_slug, sha, json.dumps(sinirlar), model, reddedilen, time.time()))
            conn.commit()
        finally:
            conn.close()
    except sqlite3.OperationalError:
        pass  # kayıt düşerse sonraki açılışta yeniden üretilir
