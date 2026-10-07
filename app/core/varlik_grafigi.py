"""Kitap VARLIK GRAFİĞİ: sözlük kayıtları arasındaki bağlar (`PLAN-varlik-grafigi.md`).

Düğüm = sözlük kaydı (`glossary.kimlik`). Ayrı bir varlık tablosu AÇILMADI:
kimlik zaten kavramın ömür boyu adı, tür/tanım/alternatif yazım da orada; ikinci
bir kaynak sözlükle zamanla ayrışırdı (bu projede iki kaynaklı her bilgi ayrıştı).
Burada yalnız BAĞLAR durur (`varlik_bag`).

Bağ kaynakları, güven sırasıyla:
  * `sistem` — Spell'in rün mesajları (Shadow Slave), deterministik, API'siz.
    Sunucu kopyasında ölçüldü: 40 `Memory:` bloğu, 58 `You have slain`, 18 `True
    Name`, 26 `Attribute` satırı; rün blokları düzenli (`Name: … / True Name: … /
    Memories: [..] / Attributes: [..] / Aspect: [..]`).
  * `model` — ayrı bir çıkarım işi (`varlik_cikarim`), kanıt cümlesi birebir
    doğrulanır.
  * `manual` — okuyucudan.

SPOILER: her bağ `ilk_bolum` taşır. Okuyucu bağları okuma konumuna göre süzer;
varsayılan GİZLİ (kullanıcı kararı 2026-10-06). `ilk_bolum` yalnız KÜÇÜLTÜLÜR:
daha eski bir kanıt bulunursa bağ daha erken kurulmuş demektir; daha geç bir kanıt
bağı geç göstermemeli.

Bu modül sözlüğü DEĞİŞTİRMEZ.
"""
from __future__ import annotations

import re
import sqlite3
import time

from . import cache, db, glossary

# ---------- ilişki sözlüğü (denetimli) ----------
# Serbest metin ilişki grafiği çöplüğe çevirir; sabit tipler (graphify'ın kod
# tarafındaki calls/imports gibi). Yön tek: ÖZNE -> NESNE. Ters yön sorguda türer.
# `tekil`: öznenin aynı anda tek değeri olur (rütbe değişir); güncel değer, okuma
# konumundan önceki EN SON bağdır — kapanış (`son_bolum`) yazmak gerekmez.
ILISKILER: dict[str, dict] = {
    "takma_adi": {"etiket": "takma adı", "ters": "kimin takma adı", "grup": "kimlik"},
    "gercek_adi": {"etiket": "Gerçek Adı", "ters": "kimin Gerçek Adı", "grup": "kimlik", "tekil": True},
    "unvani": {"etiket": "unvanı", "ters": "kimin unvanı", "grup": "kimlik"},
    "anisi": {"etiket": "Anısı", "ters": "sahibi", "grup": "sahiplik"},
    "golgesi": {"etiket": "Gölgesi", "ters": "efendisi", "grup": "sahiplik"},
    "yanki": {"etiket": "Yankısı", "ters": "efendisi", "grup": "sahiplik"},
    "yetenegi": {"etiket": "yeteneği", "ters": "kimin yeteneği", "grup": "sahiplik"},
    # Anının EFSUNU ("Memory Enchantments: [Unbroken]"); efsunun ne yaptığı bağın
    # KANITINDA durur ("Enchantment Description" satırı). Ölçülen (2026-10-07): 13
    # efsun satırının hiçbiri bağa dönmüyordu ve model `Doubtless`ı nitelik sanmıştı.
    "efsunu": {"etiket": "efsunu", "ters": "hangi Anının efsunu", "grup": "sahiplik"},
    "niteligi": {"etiket": "niteliği", "ters": "kimin niteliği", "grup": "sahiplik"},
    "gorunusu": {"etiket": "Görünüşü", "ters": "kimin Görünüşü", "grup": "sahiplik"},
    "klani": {"etiket": "klanı", "ters": "üyesi", "grup": "toplum"},
    "lideri": {"etiket": "lideri", "ters": "yönettiği", "grup": "toplum"},
    "yoldasi": {"simetrik": True, "etiket": "yoldaşı", "ters": "yoldaşı", "grup": "toplum"},
    "akrabasi": {"simetrik": True, "etiket": "akrabası", "ters": "akrabası", "grup": "toplum"},
    "dusmani": {"simetrik": True, "etiket": "düşmanı", "ters": "düşmanı", "grup": "toplum"},
    "ogretmeni": {"etiket": "öğretmeni", "ters": "öğrencisi", "grup": "toplum"},
    # O DÖNEM yaşadığı/bulunduğu bölge (ilk_bolum dönemi gösterir); sahnelik anlık
    # konum değil. Ölçülen: `Kai -> Forgotten Shore` arc boyunca doğru bilgi.
    "bulundugu_yer": {"etiket": "bulunduğu yer (o dönem)", "ters": "orada bulunan", "grup": "mekan"},
    "parcasi": {"etiket": "parçası olduğu yer", "ters": "içerdiği", "grup": "mekan"},
    "turu": {"etiket": "türü", "ters": "örneği", "grup": "duzen"},
    "rutbesi": {"etiket": "rütbesi", "ters": "bu rütbede", "grup": "duzen", "tekil": True},
    # Gölgeler evrimleşir (Soul Serpent: Monster -> Demon -> Devil): sınıf da değişir.
    "sinifi": {"etiket": "sınıfı", "ters": "bu sınıfta", "grup": "duzen", "tekil": True},
    "ust_basamak": {"etiket": "bir üst basamak", "ters": "bir alt basamak", "grup": "duzen"},
    # Anının eşya türü ("Memory Type: Armor"). `sinifi` KULLANILMADI: sınıf nesneleri
    # kalite denetiminde sınıf SÖZCÜĞÜ sayılır ve Zırh/Kılıç orada gürültü üretirdi.
    "esya_turu": {"etiket": "eşya türü", "ters": "bu türde eşya", "grup": "duzen", "tekil": True},
    # ZAMANLA DEĞİŞEN KİMLİK (kullanıcı örneği, 2026-10-07): Sunny'nin gölgesi Saint
    # önce bir Yankıydı (Stone Saint), gölgeye çevrildi, sonra Marble Saint'e evrildi.
    # Biçimler ayrı karakter değildir; `bicimi` o dönemki adı/formu verir (tekil: konumdan
    # önceki en son biçim geçerli), `donustu` eski biçimden yenisine evrimi kaydeder.
    "bicimi": {"etiket": "o dönemki biçimi", "ters": "kimin biçimi", "grup": "kimlik", "tekil": True},
    "donustu": {"etiket": "dönüştüğü biçim", "ters": "önceki biçimi", "grup": "kimlik"},
    "oldurdu": {"etiket": "öldürdü", "ters": "öldüreni", "grup": "olay"},
}
ORIGIN_ONCELIGI = {"model": 0, "sistem": 1, "manual": 2}
DURUMLAR = ("aday", "onaylandi", "reddedildi")

# ---------- kitap profilleri ----------
# Rün mesajlarının biçimi kitaba özgüdür; yeni kitap = yeni kayıt (fetch.SITES gibi).
# Bilinmeyen kitapta sistem katmanı sessizce boş kalır.
KITAP_PROFILLERI: dict[str, dict] = {
    "shadow-slave": {
        "ana_karakter": "Sunny",
        # Rünlerdeki `Name: Sunless` ana karakterdir; `Sunny` onun takma adı.
        "ana_karakter_adlari": ("Sunless",),
        "runler": True,
        # Spell'in GENEL sistem terimleri: belirli bir varlık değil, kategori.
        # Ölçülen hata (Vertex, 15 bölüm): `Sunny -> yetenegi -> Abilities`,
        # `Nephis -> yetenegi -> Aspect Ability`, `Gateway -> parcasi -> ...`,
        # `Noctis -> unvani -> Lord`. Grafikten gelen sınıf/rütbeler ve onların
        # bileşimleri (`Fallen Terror`) de kategori sayılır (`kategori_kimlikleri`).
        # `Saint` ve `Nightmare` BİLEREK yok: ikisi de Sunny'nin gölgelerinin ADI
        # (koşullu sözlük kayıtları) — kategori sayılsalar bağları engellenirdi.
        "kategori_terimleri": (
            "Ability", "Abilities", "Aspect", "Aspects", "Aspect Ability", "Aspect Abilities",
            "Attribute", "Attributes", "Memory", "Memories", "Echo", "Echoes", "Shadow", "Shadows",
            "Flaw", "Flaws", "Gate", "Gates", "Gateway", "Gateways", "Seed", "Spell", "Rank",
            "Ranks", "Class", "Classes", "Tier", "Lord", "Lords", "Master", "Masters",
            "Saints", "Sovereign", "Sovereigns", "Legacy", "Legacies", "Citadel", "Citadels",
            "Nightmare Creature", "Nightmare Creatures", "Nightmares",
            "Sleeper", "Sleepers", "Dreamer", "Dreamers", "Awakened", "Aspirant", "Aspirants",
            "Transcendents", "Supremes", "Soul Core", "Soul Shards", "Shadow Core", "Relic",
            # Toplanan KAYNAKLAR (ölçülen: `Sunny -> niteligi -> Shadow Fragments`).
            "Shadow Fragment", "Shadow Fragments", "Soul Fragment", "Soul Fragments",
            "Soul Shard", "Soul Essence", "Shard Memory", "Shard Memories",
            "Dormant Ability", "Awakened Ability", "Ascended Ability", "Transformation Ability",
        ),
        # Spell'in sıralı düzenleri (kitap metninden, `CLAUDE.md` `Great -> Ulu`
        # kaydındaki dizi). Rütbe merdiveni `ust_basamak` bağlarıyla tohumlanır.
        "diziler": {
            "canavar_rutbesi": ("Dormant", "Awakened", "Fallen", "Corrupted", "Great", "Cursed", "Unholy"),
            "insan_rutbesi": ("Dormant", "Awakened", "Ascended", "Transcendent", "Supreme", "Sacred", "Divine"),
            # Kabus Yaratığı SINIFLARI da sıralıdır (rün mesajlarındaki "dormant beast",
            # "fallen monster", "corrupted demon"...); grafikten tek tek öğrenmek eşiğe
            # takılıyordu (Terror yalnız bir bağda) — bileşik kategori (`Fallen Terror`)
            # tanınmıyordu.
            "yaratik_sinifi": ("Beast", "Monster", "Demon", "Devil", "Tyrant", "Terror", "Titan"),
        },
        # Dizi DIŞINDA kalan ama rütbe sayılan adlar (insan tarafının yaygın karşılıkları).
        # `rutbesi` ilişkisinin nesnesi bunlardan ya da dizilerden değilse UNVANDIR
        # (ölçülen, 502 bağlık inceleme: Artisan, Chain Lord, Prince of War, Dream
        # Champion, Sorcerer of the East "rütbe" diye yazılmıştı — 20 bağ).
        "ek_rutbeler": ("Aspirant", "Sleeper", "Dreamer", "Master", "Saint", "Sovereign"),
    },
}


def profil(book_slug: str) -> dict | None:
    return KITAP_PROFILLERI.get(book_slug)


# ---------- şema ----------
def _connect() -> sqlite3.Connection:
    glossary.semayi_hazirla()
    conn = db.connect()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS varlik_bag (
            book_slug TEXT NOT NULL,
            kaynak_kimlik TEXT NOT NULL,
            iliski TEXT NOT NULL,
            hedef_kimlik TEXT NOT NULL,
            ilk_bolum INTEGER,
            kanit TEXT,
            kanit_bolum INTEGER,
            origin TEXT NOT NULL,
            durum TEXT NOT NULL,
            guven REAL,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            PRIMARY KEY (book_slug, kaynak_kimlik, iliski, hedef_kimlik)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS varlik_bag_hedef ON varlik_bag (book_slug, hedef_kimlik)"
    )
    return conn


# ---------- düğüm çözümleme ----------
class DugumCozucu:
    """Ad -> sözlük kaydı (kimlik, kaynak). Kayıt adı, alternatif yazım ve iç
    iyelik/belirteç farkı (`sozluk_kapi.varyant_anahtari`) üzerinden çözer.
    Kitabın sözlüğü bir kez okunur."""

    def __init__(self, book_slug: str):
        from . import sozluk_kapi

        self._varyant = sozluk_kapi.varyant_anahtari
        self.satirlar = {r["kimlik"]: r for r in glossary.get_glossary_rows(book_slug)}
        self._fold: dict[str, str] = {}
        self._var: dict[str, str] = {}
        for kimlik, r in self.satirlar.items():
            self._fold.setdefault(glossary.fold_term(r["source"]), kimlik)
            self._var.setdefault(self._varyant(r["source"]), kimlik)
        for kaynak, ek in glossary.ekler(book_slug).items():
            kimlik = next((k for k, r in self.satirlar.items() if r["source"] == kaynak), None)
            for yazim in ek["yazimlar"] if kimlik else ():
                self._fold.setdefault(glossary.fold_term(yazim), kimlik)

    def coz(self, ad: str) -> str | None:
        ad = (ad or "").strip().strip(".,;:!?\"“”'’[]")
        if not ad or ad in ("—", "-"):
            return None
        return self._fold.get(glossary.fold_term(ad)) or self._var.get(self._varyant(ad))

    def kaynak(self, kimlik: str) -> str:
        return self.satirlar[kimlik]["source"]


# ---------- yazma ----------
def bag_ekle(
    book_slug: str,
    kaynak_kimlik: str,
    iliski: str,
    hedef_kimlik: str,
    ilk_bolum: int | None,
    kanit: str | None,
    origin: str,
    guven: float | None = None,
    durum: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> bool:
    """Bağı ekle ya da birleştir. Yeni eklendiyse True.

    Birleştirme kuralları: `ilk_bolum` yalnız KÜÇÜLÜR (spoiler); kanıt en eski
    bölümünkidir; köken önceliği manual > sistem > model (güçlü kaynak zayıfı ezer,
    tersi olmaz); reddedilmiş bağ otomatik yolla dirilmez.
    """
    if iliski not in ILISKILER:
        raise ValueError(f"Bilinmeyen ilişki: {iliski!r}")
    if kaynak_kimlik == hedef_kimlik:
        return False
    # SİMETRİK ilişki (yoldaş, akraba, düşman) tek bağdır: uçlar kimliğe göre
    # sıralanır. Ölçülen: model `Sunny -> Kai` ve `Kai -> Sunny`yi ayrı döndürdü.
    if ILISKILER[iliski].get("simetrik") and kaynak_kimlik > hedef_kimlik:
        kaynak_kimlik, hedef_kimlik = hedef_kimlik, kaynak_kimlik
    if durum is None:
        durum = "onaylandi" if origin in ("manual", "sistem") else "aday"
    kendi = conn is None
    conn = conn or _connect()
    try:
        simdi = time.time()
        mevcut = conn.execute(
            "SELECT ilk_bolum, kanit, kanit_bolum, origin, durum, guven FROM varlik_bag "
            "WHERE book_slug = ? AND kaynak_kimlik = ? AND iliski = ? AND hedef_kimlik = ?",
            (book_slug, kaynak_kimlik, iliski, hedef_kimlik),
        ).fetchone()
        if mevcut is None:
            conn.execute(
                "INSERT INTO varlik_bag (book_slug, kaynak_kimlik, iliski, hedef_kimlik, ilk_bolum, "
                "kanit, kanit_bolum, origin, durum, guven, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (book_slug, kaynak_kimlik, iliski, hedef_kimlik, ilk_bolum, (kanit or "")[:600] or None,
                 ilk_bolum, origin, durum, guven, simdi, simdi),
            )
            yeni = True
        else:
            m_ilk, m_kanit, m_kbolum, m_origin, m_durum, m_guven = mevcut
            daha_erken = ilk_bolum is not None and (m_ilk is None or ilk_bolum < m_ilk)
            guclu = ORIGIN_ONCELIGI.get(origin, 0) > ORIGIN_ONCELIGI.get(m_origin, 0)
            if m_durum == "reddedildi" and origin != "manual":
                return False
            conn.execute(
                "UPDATE varlik_bag SET ilk_bolum = ?, kanit = ?, kanit_bolum = ?, origin = ?, "
                "durum = ?, guven = ?, updated_at = ? WHERE book_slug = ? AND kaynak_kimlik = ? "
                "AND iliski = ? AND hedef_kimlik = ?",
                (ilk_bolum if daha_erken else m_ilk,
                 ((kanit or "")[:600] or m_kanit) if daha_erken else m_kanit,
                 ilk_bolum if daha_erken else m_kbolum,
                 origin if guclu else m_origin,
                 durum if guclu or m_durum == "aday" and durum == "onaylandi" else m_durum,
                 max(x for x in (guven, m_guven, 0.0) if x is not None),
                 simdi, book_slug, kaynak_kimlik, iliski, hedef_kimlik),
            )
            yeni = False
        if kendi:
            conn.commit()
        return yeni
    finally:
        if kendi:
            conn.close()


def bag_durumu(book_slug: str, kaynak_kimlik: str, iliski: str, hedef_kimlik: str, durum: str) -> bool:
    if durum not in DURUMLAR:
        raise ValueError(f"Bilinmeyen durum: {durum!r}")
    conn = _connect()
    try:
        n = conn.execute(
            "UPDATE varlik_bag SET durum = ?, updated_at = ? WHERE book_slug = ? AND kaynak_kimlik = ? "
            "AND iliski = ? AND hedef_kimlik = ?",
            (durum, time.time(), book_slug, kaynak_kimlik, iliski, hedef_kimlik),
        ).rowcount
        conn.commit()
        return n > 0
    finally:
        conn.close()


def baglari_sil(book_slug: str, kimlik: str) -> int:
    """Düğüm (sözlük kaydı) silinince bağları da gider (`glossary.delete_term`)."""
    conn = _connect()
    try:
        n = conn.execute(
            "DELETE FROM varlik_bag WHERE book_slug = ? AND (kaynak_kimlik = ? OR hedef_kimlik = ?)",
            (book_slug, kimlik, kimlik),
        ).rowcount
        conn.commit()
        return n
    finally:
        conn.close()


# ---------- okuma ----------
def baglar(
    book_slug: str,
    en_cok_bolum: int | None = None,
    durumlar: tuple[str, ...] = ("aday", "onaylandi"),
    kimlik: str | None = None,
) -> list[dict]:
    """Bağlar, iki ucun kaynak adıyla. `en_cok_bolum` verilirse SPOILER süzgeci:
    ilk bölümü bilinmeyen ya da konumdan sonra kurulan bağ dönmez."""
    conn = _connect()
    try:
        sorgu = (
            "SELECT b.kaynak_kimlik, k.source, k.target, b.iliski, b.hedef_kimlik, h.source, h.target, "
            "b.ilk_bolum, b.kanit, b.kanit_bolum, b.origin, b.durum, b.guven "
            "FROM varlik_bag b "
            "JOIN glossary k ON k.book_slug = b.book_slug AND k.kimlik = b.kaynak_kimlik "
            "JOIN glossary h ON h.book_slug = b.book_slug AND h.kimlik = b.hedef_kimlik "
            f"WHERE b.book_slug = ? AND b.durum IN ({', '.join('?' for _ in durumlar)})"
        )
        parametre: list = [book_slug, *durumlar]
        if en_cok_bolum is not None:
            sorgu += " AND b.ilk_bolum IS NOT NULL AND b.ilk_bolum <= ?"
            parametre.append(en_cok_bolum)
        if kimlik:
            sorgu += " AND (b.kaynak_kimlik = ? OR b.hedef_kimlik = ?)"
            parametre += [kimlik, kimlik]
        satirlar = conn.execute(sorgu + " ORDER BY b.ilk_bolum, k.source", parametre).fetchall()
    finally:
        conn.close()
    return [
        {
            "kaynak_kimlik": r[0], "kaynak": r[1], "kaynak_karsilik": r[2], "iliski": r[3],
            "hedef_kimlik": r[4], "hedef": r[5], "hedef_karsilik": r[6], "ilk_bolum": r[7],
            "kanit": r[8], "kanit_bolum": r[9], "origin": r[10], "durum": r[11], "guven": r[12],
        }
        for r in satirlar
    ]


def kategori_kimlikleri(
    book_slug: str, cozucu: "DugumCozucu | None" = None, korpus: str | None = None
) -> set[str]:
    """Belirli bir varlık değil GENEL kategori olan düğümler (kimlik kümesi).

    Üç kaynak: profilin `kategori_terimleri` · grafikten sınıf/rütbe adları (en az 2
    bağ) · SÖZCÜKLERİNİN HEPSİ bu ikisinden olan bileşik kayıtlar (`Fallen Terror`,
    `Corrupted Monster`, `awakened beasts`). Kategori bir ilişkinin ancak
    türü/rütbesi/sınıfı NESNESİ olabilir (`varlik_cikarim.kaniti_dogrula`)."""
    from . import sozluk_kapi

    p = profil(book_slug) or {}
    cozucu = cozucu or DugumCozucu(book_slug)
    adlar = set(p.get("kategori_terimleri", ()))
    adlar |= nesneler(book_slug, "sinifi", en_az=2) | nesneler(book_slug, "rutbesi", en_az=2)
    for dizi in p.get("diziler", {}).values():
        adlar |= set(dizi)
    sozcukler = {sozluk_kapi._tekil(w.casefold()) for ad in adlar for w in ad.split()}
    out = {k for ad in adlar if (k := cozucu.coz(ad))}
    for kimlik, r in cozucu.satirlar.items():
        parcalar = [sozluk_kapi._tekil(w.casefold()) for w in r["source"].split()]
        # YALNIZ çok sözcüklü kayıtlar: tek sözcük listede birebir olmalı. Ölçülen:
        # listedeki `Saints` tekile inince gölgenin ADI `Saint`i kategori yapıyordu.
        if len(parcalar) >= 2 and all(w in sozcukler for w in parcalar):
            out.add(kimlik)
    # SIRADAN TEK SÖZCÜK (`Armor`, `Fire`): kitapta küçük harfle en az büyük harfle
    # olduğu kadar geçen sözcük belirli bir varlık değildir. Ölçülen: `Armor ->
    # rutbesi -> Awakened Rank`. Kitabın KENDİ kaynağından ölçülür (sabit liste
    # kitabın diline uymaz). İngilizce korunan (kişi) kayıtlar dışarıda.
    if korpus:
        for kimlik, r in cozucu.satirlar.items():
            kaynak = r["source"]
            if " " in kaynak.strip() or sozluk_kapi.ingilizce_korunan(kaynak, r.get("target") or ""):
                continue
            if sozluk_kapi.genel_sozcuk_mu(kaynak, korpus):
                out.add(kimlik)
    return out


# Kategori NESNE olabilir yalnız bu ilişkilerde.
KATEGORI_NESNESI_OLABILIR = frozenset({"turu", "rutbesi", "sinifi"})


def nesneler(book_slug: str, iliski: str, en_az: int = 1) -> set[str]:
    """Bir ilişkinin NESNESİ olan düğümlerin kaynakları (ör. `sinifi` -> sınıflar).

    `en_az`: en az bu kadar bağda nesne olanlar. Tek bir rün satırı gürültü
    olabilir (ölçülen: "Memory Rank: Unknown" `Unknown`ı rütbe yapıyordu)."""
    from collections import Counter

    sayac = Counter(b["hedef"] for b in baglar(book_slug) if b["iliski"] == iliski)
    return {ad for ad, n in sayac.items() if n >= en_az}


# Kişi adının önüne gelen HİTAP unvanları ("Master Roan" = Roan).
HITAP_UNVANLARI = ("Master", "Saint", "Lord", "Lady", "Sir", "Prince", "Princess", "Queen",
                   "King", "Teacher", "Instructor", "Sovereign")
# Rütbe sözcükleri de ad önüne gelir ("Ascended Dale") ama kategorilerle de birleşir
# ("Ascended Demon"); YALNIZ arkasından İngilizce korunan bir KİŞİ adı gelirse unvandır.
RUTBE_ONEKLERI = ("Ascended", "Awakened", "Transcendent", "Sleeper", "Dreamer")


def unvanli_adlari_bagla(book_slug: str) -> int:
    """"Unvan + kayıtlı ad" düğümlerini asıl kişiye `takma_adi` ile bağla (API'siz).

    Ölçülen (altın standart, 2026-10-07): eksik bağların yarısı aynı varlığın iki
    düğüme bölünmesinden geliyordu — "Master Roan" / "Roan", "Lady Hope" / "Hope".
    Bağ `manual` kökenli ve onaylıdır (kural deterministik); ardından
    `takma_adlari_birlestir` bağları asıl kişiye taşır. Döner: eklenen bağ sayısı.

    Eşleşme kuralları (yanlış pozitife karşı, ölçüldü): hitap unvanı + kişi adı her
    zaman; rütbe öneki + kişi adı YALNIZ ad İngilizce korunuyorsa (`Ascended Demon ->
    Demon` bir kategori çiftidir, takma ad değil). Türkçeleştirilmiş kişide
    (`Lady Hope -> Leydi Umut`, `Hope -> Umut`) karşılık da karşılığı içermeli.
    """
    satirlar = glossary.get_glossary_rows(book_slug)
    katlanmis = {glossary.fold_term(r["source"]): r for r in satirlar}
    eklenen = 0
    conn = _connect()
    try:
        for r in satirlar:
            parca = r["source"].split(" ", 1)
            if len(parca) != 2:
                continue
            onek, ad = parca
            asil = katlanmis.get(glossary.fold_term(ad))
            if asil is None or asil["kimlik"] == r["kimlik"]:
                continue
            korunan = glossary.fold_term(asil["source"]) == glossary.fold_term(asil.get("target") or "")
            if onek in HITAP_UNVANLARI:
                if not korunan and glossary.fold_term(asil.get("target") or "") not in glossary.fold_term(
                    r.get("target") or ""
                ):
                    continue
            elif onek in RUTBE_ONEKLERI:
                if not korunan:
                    continue
            else:
                continue
            if bag_ekle(book_slug, asil["kimlik"], "takma_adi", r["kimlik"], r.get("first_chapter"),
                        None, "manual", 1.0, conn=conn):
                eklenen += 1
        conn.commit()
    finally:
        conn.close()
    return eklenen


def takma_adlari_birlestir(book_slug: str) -> int:
    """ONAYLI takma ad / Gerçek Ad düğümlerindeki bağları asıl kişiye taşı.

    Model bağları çoğu zaman metinde geçen adla kurulur (`Neph`, `Changing Star`,
    `Sevras`); bilgi iki düğüme bölünür ve okur kişinin kartında eksik görür. Kimlik
    bağı (takma_adi / gercek_adi) kendisi taşınmaz. Taşınan bağ `bag_ekle` ile
    birleşir (ilk bölüm küçük olan kalır), eskisi silinir. Döner: taşınan bağ sayısı.
    """
    kimlik_baglari = [
        b for b in baglar(book_slug, durumlar=("onaylandi",))
        if b["iliski"] in ("takma_adi", "gercek_adi")
    ]
    asil = {b["hedef_kimlik"]: b["kaynak_kimlik"] for b in kimlik_baglari}
    # Zincir (A -> B -> C): en üstteki asıl kişiye indir.
    def kok(k: str) -> str:
        gorulen = set()
        while k in asil and k not in gorulen:
            gorulen.add(k)
            k = asil[k]
        return k
    tasinan = 0
    conn = _connect()
    try:
        for b in baglar(book_slug, durumlar=("aday", "onaylandi")):
            if b["iliski"] in ("takma_adi", "gercek_adi"):
                continue
            a, n = kok(b["kaynak_kimlik"]), kok(b["hedef_kimlik"])
            if (a, n) == (b["kaynak_kimlik"], b["hedef_kimlik"]) or a == n:
                continue
            satir = conn.execute(
                "SELECT ilk_bolum, kanit, origin, durum, guven FROM varlik_bag WHERE book_slug = ? "
                "AND kaynak_kimlik = ? AND iliski = ? AND hedef_kimlik = ?",
                (book_slug, b["kaynak_kimlik"], b["iliski"], b["hedef_kimlik"]),
            ).fetchone()
            if satir is None:
                continue
            bag_ekle(book_slug, a, b["iliski"], n, satir[0], satir[1], satir[2], satir[4],
                     durum=satir[3], conn=conn)
            conn.execute(
                "DELETE FROM varlik_bag WHERE book_slug = ? AND kaynak_kimlik = ? AND iliski = ? "
                "AND hedef_kimlik = ?",
                (book_slug, b["kaynak_kimlik"], b["iliski"], b["hedef_kimlik"]),
            )
            tasinan += 1
        conn.commit()
    finally:
        conn.close()
    return tasinan


# ---------- sistem mesajı çıkarımı (Shadow Slave rünleri) ----------
_RUN_SATIRI = re.compile(r"^([A-Z][A-Za-z ]{1,30}):\s*(.+?)\s*$")
_KOSELI = re.compile(r"\[([^\[\]]+)\]")
_OLDURME = re.compile(
    r"\[You have slain (?:an?|the) ([A-Za-z]+) ([A-Za-z]+), ([^\]]+?)\.?\]", re.IGNORECASE
)
_GERCEK_AD_ODUL = re.compile(r"\[You have been bestowed a True Name: ([^\].]+)\.?\]")
_YANKI_ALINDI = re.compile(r"\[You have received an Echo: ([^\]]+?)\.?\]")
_GOLGE_ALINDI = re.compile(r"\[You have (?:created|received) a Shadow(?: [A-Z][a-z]+)?: ([^\]]+?)\.?\]")
# "[...The Stone Saint is evolving.]" / "[...Marble Saint is evolving.]"
_EVRIM = re.compile(r"\[(?:\.\.\.)?(?:The )?([A-Z][^\]]*?) is evolving\.{0,3}\]")

# Blok başlığı -> (öznenin kim olduğu, alt satır anahtarları -> ilişki)
_BLOK_ALT = {
    # Efsun satırı kitapta üç biçimde yazılıyor (ölçüldü): "Memory Enchantments:",
    # tekil "Enchantment:" ve düz "Enchantments:" (923. bölüm, Bitter Cusp / Stifled Scream).
    "Memory": {"Memory Rank": "rutbesi", "Memory Type": "esya_turu", "Memory Enchantments": "efsunu",
               "Enchantments": "efsunu", "Enchantment": "efsunu"},
    "Shadow": {"Shadow Rank": "rutbesi", "Shadow Class": "sinifi"},
    "Echo": {"Echo Type": "sinifi", "Echo Core": "rutbesi", "Echo Rank": "rutbesi"},
}
_BLOK_SAHIPLIK = {"Memory": "anisi", "Shadow": "golgesi", "Echo": "yanki"}
# Sonraki bölümlerde Anı rünlerinin ARASINA anlatım giriyor ("He continued to study
# the runes."); düz paragraf bloğu kapattığı için `Memory Description` ve efsun
# satırları sahipsiz kalıyordu. YALNIZ Anıya özgü anahtarlar kapanmış bloğu bu kadar
# paragraf içinde yeniden açar — başka bir bloğun satırı sanılamazlar. Genel kural
# (düz paragraf bloğu kapatır) yerinde: ölçülen yanlış atıf başka anahtarlardaydı.
_ANI_ANAHTARLARI = frozenset(
    ("Memory Rank", "Memory Tier", "Memory Type", "Memory Description", "Memory Enchantments",
     "Enchantments", "Enchantment", "Enchantment Description")
)
ANI_ANLATIM_PENCERESI = 12
# "[Echoing Silence] Enchantment Description: ..." — açıklama efsun adıyla aynı paragrafta.
_SATIR_ICI_EFSUN = re.compile(r"^\[([^\]]+)\]\s*Enchantment Description:")
# Durum bloğu (`Name: X`) satırları -> ilişki (özne: X).
_DURUM_SATIRLARI = {
    "True Name": "gercek_adi", "Rank": "rutbesi", "Memories": "anisi", "Echoes": "yanki",
    "Attributes": "niteligi", "Aspect": "gorunusu", "Shadows": "golgesi",
}


def _ogeler(deger: str) -> list[str]:
    """`[A], [B]` -> [A, B]; köşeli yoksa düz değer (`Rank: Dreamer.`)."""
    bulunan = _KOSELI.findall(deger)
    if bulunan:
        return [b.strip().rstrip(".") for b in bulunan]
    tek = deger.strip().rstrip(".").strip()
    return [] if tek in ("", "—", "-") else [tek]


def sistem_baglarini_bul(metin: str, ana_karakter: str, ana_adlar: tuple[str, ...] = ()) -> list[tuple]:
    """Bir bölümün kaynağından (özne, ilişki, nesne, kanıt) dörtlüleri — ad düzeyinde.

    Rün satırları ardışık paragraflar olarak gelir; boş olmayan ve rün biçiminde
    olmayan bir paragraf bloğu kapatır. `Name: X` bloğu X'in durumudur; `Memory:`,
    `Shadow:`, `Echo:` blokları ana karakterin sahip olduğu şeyi anlatır (rünleri
    okuyan odur — sunucu kopyasındaki bütün örneklerde öyle).
    """
    out: list[tuple] = []
    blok_ozne: str | None = None
    blok_tur: str | None = None
    efsun_sirasi: list[int] = []  # açıklaması henüz gelmemiş efsunların `out` sırası
    efsunlar: dict[str, int] = {}  # son Anının efsunları: ad -> `out` sırası
    son_ani: str | None = None     # anlatımla kapanmış son Anı bloğunun öznesi
    anlatim = 0                    # o bloktan beri geçen düz paragraf
    for paragraf in (p.strip() for p in metin.split("\n")):
        if not paragraf:
            continue
        for m in _OLDURME.finditer(paragraf):
            rutbe, sinif, ad = m.group(1), m.group(2), m.group(3).strip()
            out.append((ana_karakter, "oldurdu", ad, paragraf))
            out.append((ad, "rutbesi", rutbe, paragraf))
            out.append((ad, "sinifi", sinif, paragraf))
        for m in _GERCEK_AD_ODUL.finditer(paragraf):
            out.append((ana_karakter, "gercek_adi", m.group(1).strip(), paragraf))
        for m in _YANKI_ALINDI.finditer(paragraf):
            out.append((ana_karakter, "yanki", m.group(1).strip(), paragraf))
        for m in _GOLGE_ALINDI.finditer(paragraf):
            out.append((ana_karakter, "golgesi", m.group(1).strip(), paragraf))
        for m in _EVRIM.finditer(paragraf):
            # Evrim İŞARETİ: hangi ada dönüştüğü sonraki rün bloğunda görünür
            # (`evrim_baglari` bölümler arasında eşleştirir).
            out.append((m.group(1).strip(), "_evrim", "", paragraf))
        satir = _RUN_SATIRI.match(paragraf)
        if not satir:
            ic = _SATIR_ICI_EFSUN.match(paragraf)
            if ic and ic.group(1).strip() in efsunlar:
                i = efsunlar[ic.group(1).strip()]
                out[i] = (*out[i][:3], paragraf)
                if i in efsun_sirasi:
                    efsun_sirasi.remove(i)
            if blok_tur == "Memory":
                son_ani, anlatim = blok_ozne, 0
            elif son_ani:
                anlatim += 1
            blok_ozne = blok_tur = None
            continue
        anahtar, deger = satir.group(1).strip(), satir.group(2)
        if blok_tur is None and anahtar in _ANI_ANAHTARLARI and son_ani and anlatim < ANI_ANLATIM_PENCERESI:
            blok_ozne, blok_tur = son_ani, "Memory"
        if anahtar == "Name":
            ad = _ogeler(deger)
            blok_ozne = ana_karakter if ad and ad[0] in ana_adlar else (ad[0] if ad else None)
            blok_tur = "durum"
            son_ani, efsunlar, efsun_sirasi = None, {}, []
            continue
        if anahtar in _BLOK_SAHIPLIK:
            ogeler = _ogeler(deger)
            if ogeler:
                blok_ozne, blok_tur = ogeler[0], anahtar
                efsun_sirasi, efsunlar = [], {}
                son_ani = None
                out.append((ana_karakter, _BLOK_SAHIPLIK[anahtar], ogeler[0], paragraf))
                out.append((ogeler[0], "turu", anahtar, paragraf))
            continue
        if blok_tur == "Memory" and anahtar == "Enchantment Description" and efsun_sirasi:
            # Açıklamalar efsunlarla AYNI SIRADA gelir; efsunun ne yaptığı bağın kanıtı olur.
            i = efsun_sirasi.pop(0)
            ozne, iliski, nesne, _k = out[i]
            out[i] = (ozne, iliski, nesne, paragraf)
            continue
        if blok_tur == "durum" and anahtar in _DURUM_SATIRLARI and blok_ozne:
            for oge in _ogeler(deger):
                out.append((blok_ozne, _DURUM_SATIRLARI[anahtar], oge, paragraf))
        elif blok_tur in _BLOK_ALT and anahtar in _BLOK_ALT[blok_tur] and blok_ozne:
            for oge in _ogeler(deger):
                if _BLOK_ALT[blok_tur][anahtar] == "efsunu":
                    efsun_sirasi.append(len(out))
                    efsunlar[oge] = len(out)
                out.append((blok_ozne, _BLOK_ALT[blok_tur][anahtar], oge, paragraf))
    return out


def bolumden_sistem_baglari(book_slug: str, chapter_no: int | None, metin: str) -> int:
    """Yeni çevrilen TEK bölümün rün bağlarını ekle (çeviri akışı). Eklenen sayısı.

    Profilsiz kitapta hiçbir şey yapmaz. Tohum bağları (takma ad, rütbe dizisi)
    geriye dönük araç (`sistem_baglarini_cikar`) kurar."""
    p = profil(book_slug)
    if not p or not p.get("runler") or not metin:
        return 0
    bulunan = sistem_baglarini_bul(metin, p["ana_karakter"], tuple(p.get("ana_karakter_adlari", ())))
    bulunan = evrimleri_esle(bulunan, {}, chapter_no)
    if not bulunan:
        return 0
    cozucu = DugumCozucu(book_slug)
    eklenen = 0
    conn = _connect()
    try:
        for ozne, iliski, nesne, kanit in bulunan:
            a, b = cozucu.coz(ozne), cozucu.coz(nesne)
            if a and b and bag_ekle(book_slug, a, iliski, b, chapter_no, kanit, "sistem", 1.0, conn=conn):
                eklenen += 1
        conn.commit()
    finally:
        conn.close()
    return eklenen


EVRIM_PENCERESI = 60  # evrim işaretinden sonra yeni adın görülebileceği en çok bölüm
_EVRIM_HEDEFI = ("golgesi", "yanki")


def evrimleri_esle(bulunan: list[tuple], durum: dict, bolum_no: int | None) -> list[tuple]:
    """`_evrim` işaretlerini gerçek `donustu` bağlarına çevir. `durum` bölümler
    arasında taşınır (çağıran saklar): {"bekleyen": ..., "gorulen": set()}.

    "[X is evolving.]" mesajı yeni adı SÖYLEMEZ; yeni ad sonraki bir gölge/Echo rün
    bloğunda görünür — ölçülen: 273'te "Stone Saint is evolving", ancak 310'da
    "Shadow: [Marble Saint]" (37 bölüm sonra). Eşleşme kuralları, ikisi de ölçülmüş
    bir yanlıştan:
      * yalnız GÖLGE/ECHO bloğu (`_EVRIM_HEDEFI`): ilk sürüm sonraki Anı bloğuyla
        eşleşip `Stone Saint -> donustu -> Weaver's Mask` üretti;
      * yeni ad DAHA ÖNCE bu sahibin gölgesi/Echo'su olarak görülmemiş olmalı: eski
        bir gölgenin yeniden listelenmesi evrim sonucu değildir.
    "Your Shadow has evolved" gibi ADSIZ mesajlar kullanılmaz: birden çok gölge varken
    hangisi olduğu belirsizdir.
    """
    gorulen: set = durum.setdefault("gorulen", set())
    out = []
    for ozne, iliski, nesne, kanit in bulunan:
        if iliski == "_evrim":
            durum["bekleyen"] = {"ad": ozne, "bolum": bolum_no, "kanit": kanit}
            continue
        out.append((ozne, iliski, nesne, kanit))
        if iliski not in _EVRIM_HEDEFI or not nesne:
            continue
        anahtar = nesne.casefold()
        bekleyen = durum.get("bekleyen")
        if bekleyen and anahtar != bekleyen["ad"].casefold() and anahtar not in gorulen:
            out.append((bekleyen["ad"], "donustu", nesne, bekleyen["kanit"]))
            durum["bekleyen"] = None
        gorulen.add(anahtar)
    bekleyen = durum.get("bekleyen")
    if bekleyen and bolum_no is not None and bekleyen["bolum"] is not None \
            and bolum_no - bekleyen["bolum"] > EVRIM_PENCERESI:
        durum["bekleyen"] = None
    return out


def sistemle_celisenleri_reddet(book_slug: str) -> int:
    """Aynı çift için SİSTEM bağı başka bir ilişki söylüyorsa model bağını reddet.

    Rün kesin bilgidir; model çıkarımı aynı kuralı yeni bağlarda zaten uygular
    (`varlik_cikarim.yapisal_red`), bu, kural gelmeden ÖNCE yazılmış bağları temizler
    (ölçülen: `Puppeteer's Shroud -> niteligi -> Doubtless`, rün `efsunu` diyor).
    Elle kurulmuş bağa dokunulmaz. Döner: reddedilen sayısı."""
    hepsi = baglar(book_slug, durumlar=("aday", "onaylandi"))
    sistem: dict[frozenset, set[str]] = {}
    for b in hepsi:
        if b["origin"] == "sistem":
            sistem.setdefault(frozenset((b["kaynak_kimlik"], b["hedef_kimlik"])), set()).add(b["iliski"])
    n = 0
    for b in hepsi:
        if b["origin"] != "model":
            continue
        iliskiler = sistem.get(frozenset((b["kaynak_kimlik"], b["hedef_kimlik"])))
        if iliskiler and b["iliski"] not in iliskiler:
            bag_durumu(book_slug, b["kaynak_kimlik"], b["iliski"], b["hedef_kimlik"], "reddedildi")
            n += 1
    return n


def ani_niteliklerini_efsune_cevir(book_slug: str) -> int:
    """Bir ANININ "niteliği" diye bağlanmış model bağını `efsunu`na çevir.

    Nitelik ([Attribute]) kişiye aittir; eşyanın özelliği efsundur. Model bunu
    ayıramıyordu (ölçülen: `Puppeteer's Shroud -> niteligi -> Doubtless`, kanıt
    cümlesi "trait of the Puppeteer's Shroud"). Anı olduğu sistem bağıyla (`turu
    Memory`) bilinen özneye uygulanır; eski bağ reddedilir, yenisi kanıtını, ilk
    bölümünü ve durumunu korur. Döner: çevrilen sayısı."""
    hepsi = baglar(book_slug, durumlar=("aday", "onaylandi"))
    anilar = {b["kaynak_kimlik"] for b in hepsi if b["iliski"] == "turu" and b["hedef"] in ("Memory", "Memories")}
    n = 0
    for b in hepsi:
        if b["origin"] == "model" and b["iliski"] == "niteligi" and b["kaynak_kimlik"] in anilar:
            bag_durumu(book_slug, b["kaynak_kimlik"], "niteligi", b["hedef_kimlik"], "reddedildi")
            bag_ekle(book_slug, b["kaynak_kimlik"], "efsunu", b["hedef_kimlik"], b["ilk_bolum"], b["kanit"],
                     "model", b["guven"], durum=b["durum"])
            n += 1
    return n


def sistem_baglarini_cikar(book_slug: str, yaz: bool = True) -> dict:
    """Kitabın önbellekteki TÜM bölümlerinden sistem bağlarını çıkar (sırayla).

    Döner: {"eklenen", "birlesen", "cozulemeyen": {ad: adet}, "baglar": [...]}.
    Çözülemeyen ad = sözlükte olmayan varlık; sözlüğe OTOMATİK eklenmez (Türkçe
    karşılığı bilinmiyor), raporlanır. `yaz=False` kuru çalıştırma.
    """
    p = profil(book_slug)
    sonuc = {"eklenen": 0, "birlesen": 0, "cozulemeyen": {}, "baglar": []}
    if not p or not p.get("runler"):
        return sonuc
    cozucu = DugumCozucu(book_slug)
    conn = _connect() if yaz else None
    try:
        ana = cozucu.coz(p["ana_karakter"])
        if ana and yaz:
            for ad in p.get("ana_karakter_adlari", ()):
                hedef = cozucu.coz(ad)
                if hedef:
                    bag_ekle(book_slug, ana, "takma_adi", hedef, 1, None, "manual", 1.0, conn=conn)
            for dizi in p.get("diziler", {}).values():
                kimlikler = [cozucu.coz(x) for x in dizi]
                for alt, ust in zip(kimlikler, kimlikler[1:]):
                    if alt and ust:
                        bag_ekle(book_slug, alt, "ust_basamak", ust, 1, None, "manual", 1.0, conn=conn)
        evrim_durumu: dict = {}  # bölümler arası: bekleyen evrim + görülen gölge adları
        for bolum in sorted(cache.kaynak_bolumleri(book_slug), key=lambda b: b["chapter_no"] or 0):
            bulunan = sistem_baglarini_bul(
                bolum["source"] or "", p["ana_karakter"], tuple(p.get("ana_karakter_adlari", ())),
            )
            bulunan = evrimleri_esle(bulunan, evrim_durumu, bolum["chapter_no"])
            for ozne, iliski, nesne, kanit in bulunan:
                a, b = cozucu.coz(ozne), cozucu.coz(nesne)
                if not a or not b:
                    for ad, kim in ((ozne, a), (nesne, b)):
                        if not kim:
                            sonuc["cozulemeyen"][ad] = sonuc["cozulemeyen"].get(ad, 0) + 1
                    continue
                sonuc["baglar"].append((cozucu.kaynak(a), iliski, cozucu.kaynak(b), bolum["chapter_no"]))
                if yaz:
                    yeni = bag_ekle(book_slug, a, iliski, b, bolum["chapter_no"], kanit, "sistem", 1.0, conn=conn)
                    sonuc["eklenen" if yeni else "birlesen"] += 1
        if conn is not None:
            conn.commit()
    finally:
        if conn is not None:
            conn.close()
    if yaz:
        sonuc["reddedilen_model"] = sistemle_celisenleri_reddet(book_slug)
        sonuc["efsune_cevrilen"] = ani_niteliklerini_efsune_cevir(book_slug)
    return sonuc


# ---------- grafik tabanlı kalite kuralları ----------
SOZCUK_KARISMASI = "sozcuk_karismasi"
AD_TUTARLILIGI = "ad_tutarliligi"


def _tr_kok(sozcuk: str) -> str:
    """Türkçe karşılığın ek almış hâllerini yakalayan kök. Kısa sözcük olduğu gibi
    (`iblis` -> iblisi, iblisler); uzun sözcükte son harf düşer (`mahluk` ->
    mahluğu, `şeytan` -> şeytani). Ölçülen tuzak: `düşmüş`ün dört harflik kökü
    `düşman`ı da yakalıyordu (`Vanquished Foes -> Alt Edilen Düşmanlar`)."""
    s = sozcuk.casefold().strip("'’")
    return s if len(s) <= 5 else s[:-1]


def _en_eslesir(token: str, sozcuk: str) -> bool:
    """İngilizce sözcük bir sınıf/rütbe adının biçimi mi (`devils` ~ `devil`,
    `transcended` ~ `transcendent`, `supremacy` ~ `supreme`)."""
    t, w = token.casefold(), sozcuk.casefold()
    if t == w:
        return True
    ortak = 0
    for a, b in zip(t, w):
        if a != b:
            break
        ortak += 1
    return ortak >= max(5, len(w) - 3)


def duzen_sozcukleri(book_slug: str) -> dict[str, list[str]]:
    """Sınıf ve rütbe adları -> Türkçe karşılıklarının sözcükleri.

    Liste GRAFİKTEN gelir (`sinifi` / `rutbesi` bağlarının nesneleri + profildeki
    diziler): hangi sözcüğün bir sınıf olduğunu tahmin etmek yerine Spell'in kendi
    rünleri söyler. Tek geçiş yetmez (en az 2 bağ ya da profil dizisi). İngilizce korunan (`Titan -> titan`) ve koşullu olmayan
    karşılığı bilinmeyen sözcük listeye girmez.
    """
    adlar = nesneler(book_slug, "sinifi", en_az=2) | nesneler(book_slug, "rutbesi", en_az=2)
    for dizi in (profil(book_slug) or {}).get("diziler", {}).values():
        adlar |= set(dizi)
    sozluk = {glossary.fold_term(k): (k, v) for k, v in glossary.get_glossary(book_slug).items()}
    out: dict[str, list[str]] = {}
    for ad in adlar:
        kayit = sozluk.get(glossary.fold_term(ad))
        if not kayit or not kayit[1] or glossary.fold_term(kayit[0]) == glossary.fold_term(kayit[1]):
            continue
        out[kayit[0]] = [w for w in re.split(r"[\s\-]+", kayit[1]) if len(w) >= 3]
    return out


def sozcuk_karismalari(book_slug: str, duzen: dict[str, list[str]] | None = None) -> dict[str, dict]:
    """Bir sınıfın/rütbenin Türkçe sözcüğü, o sınıfı/rütbeyi İÇERMEYEN bir kaydın
    karşılığında geçiyor: {kaynak: neden}.

    Ölçülen vakalar (model doğrulamasının KAÇIRDIKLARI): `Winter Beast -> Kış
    Canavarı` (Canavar = Monster), `Transcended Echo -> Yüce Yankı` (Yüce =
    Supreme), `great Labyrinth -> Yüce Labirent`; ayrıca `Dread Wolf -> Dehşet
    Kurdu` (Dehşet = Terror sınıfı), `Blood Fiend -> Kan İblisi` (İblis = Demon),
    `Fallen Creatures -> Düşmüş Mahluklar` (Mahluk = Beast). Okur Türkçede sınıfı
    sözcükten tanır; başka sınıfın sözcüğü yanlış bilgi verir.

    Kaydın kaynağında geçen sınıf/rütbelerin KENDİ karşılık sözcükleri serbesttir
    (`Unholy -> Kutsal Olmayan` "Kutsal"ı Sacred'dan almış sayılmaz).
    """
    duzen = duzen_sozcukleri(book_slug) if duzen is None else duzen
    if not duzen:
        return {}
    kokler = {ad: [_tr_kok(w) for w in sozcukler] for ad, sozcukler in duzen.items()}
    out: dict[str, dict] = {}
    for kaynak, hedef in glossary.get_glossary(book_slug).items():
        if not hedef or glossary.fold_term(kaynak) == glossary.fold_term(hedef) or kaynak in duzen:
            continue
        en = re.findall(r"[A-Za-z]+", kaynak)
        icerdigi = {ad for ad in duzen if any(_en_eslesir(t, ad) for t in en)}
        serbest = {k for ad in icerdigi for k in kokler[ad]}
        tr = [w.casefold().strip("'’") for w in re.split(r"[\s\-]+", hedef) if w]
        for ad, ad_kokleri in kokler.items():
            if ad in icerdigi:
                continue
            kullanilan = [k for k in ad_kokleri if k not in serbest and any(w.startswith(k) for w in tr)]
            if kullanilan:
                out[kaynak] = {
                    "tur": SOZCUK_KARISMASI,
                    "aciklama": (f"Karşılıkta '{duzen[ad][0]}' sözcüğü var, bu '{ad}' sınıfının/rütbesinin "
                                 f"karşılığı; ama kaynakta '{ad}' geçmiyor. Okur Türkçede sınıfı "
                                 "sözcükten tanır — başka sınıfın sözcüğü yanlış bilgi verir."),
                    "ilgili": [ad],
                }
                break
    return out


def ad_tutarsizliklari(book_slug: str) -> dict[str, dict]:
    """Aynı kişinin adları farklı politikada: {kaynak: neden}.

    Grafikte `takma_adi` ve `gercek_adi` bağları kişinin bütün adlarını toplar.
    Ölçülen: Sunny / Sunless İngilizce, Gerçek Adı `Lost from Light -> Işıktan
    Mahrum` Türkçe; Nephis İngilizce, `Changing Star -> Değişen Yıldız` Türkçe.
    Proje kuralı kişiyi adlandıran ifadeyi İngilizce bırakır; Gerçek Ad bilerek
    Türkçeleştirildiyse bu bir kategori politikasıyla (tür) açıkça söylenmeli.
    """
    gruplar: dict[str, dict[str, str]] = {}
    for b in baglar(book_slug):
        if b["iliski"] in ("takma_adi", "gercek_adi"):
            grup = gruplar.setdefault(b["kaynak"], {b["kaynak"]: b["kaynak_karsilik"]})
            grup[b["hedef"]] = b["hedef_karsilik"]
    out: dict[str, dict] = {}
    for kisi, adlar in gruplar.items():
        korunan = {a for a, t in adlar.items() if glossary.fold_term(a) == glossary.fold_term(t or "")}
        turkce = set(adlar) - korunan
        if not korunan or not turkce:
            continue
        ozet = ", ".join(f"{a} ({'İngilizce' if a in korunan else '→ ' + adlar[a]})" for a in sorted(adlar))
        for ad in sorted(turkce):
            out[ad] = {
                "tur": AD_TUTARLILIGI,
                "aciklama": (f"{kisi} kişisinin adları farklı politikada: {ozet}. Aynı kişinin "
                             "adları tek kurala bağlı olmalı (ya da Gerçek Adlar için açık bir "
                             "politika yaz)."),
                "ilgili": sorted(korunan),
            }
    return out


def kalite_nedenleri(book_slug: str) -> dict[str, list[dict]]:
    """Grafik tabanlı bütün kalite bulguları: {kaynak: nedenler}. Grafik boşsa boş."""
    out: dict[str, list[dict]] = {}
    for kural in (sozcuk_karismalari, ad_tutarsizliklari):
        for kaynak, neden in kural(book_slug).items():
            out.setdefault(kaynak, []).append(neden)
    return out


# ---------- dışa aktarma ----------
def graph_json(book_slug: str, en_cok_bolum: int | None = None) -> dict:
    """graphify'ın `graph.json` biçimine yakın düğüm/kenar listesi.

    Yalnız bağı OLAN düğümler girer (1100 kayıtlık sözlüğün bağsız kayıtları
    çizimi yumağa çevirir). `en_cok_bolum` verilirse SPOILER süzgeci uygulanır ve
    konumdan sonra ilk görülen düğüm de çıkar.
    """
    bag_listesi = baglar(book_slug, en_cok_bolum=en_cok_bolum)
    satirlar = {r["kimlik"]: r for r in glossary.get_glossary_rows(book_slug)}
    kullanilan = {b["kaynak_kimlik"] for b in bag_listesi} | {b["hedef_kimlik"] for b in bag_listesi}
    dugumler = []
    for kimlik in sorted(kullanilan):
        r = satirlar.get(kimlik)
        if r is None:
            continue
        if en_cok_bolum is not None and r.get("first_chapter") and r["first_chapter"] > en_cok_bolum:
            continue
        dugumler.append({
            "id": kimlik, "label": r["source"], "karsilik": r["target"], "tur": r.get("tur"),
            "tanim": r.get("tanim"), "ilk_bolum": r.get("first_chapter"),
        })
    gorunur = {d["id"] for d in dugumler}
    kenarlar = [
        {"source": b["kaynak_kimlik"], "target": b["hedef_kimlik"], "relation": b["iliski"],
         "etiket": ILISKILER[b["iliski"]]["etiket"], "ilk_bolum": b["ilk_bolum"],
         "origin": b["origin"], "durum": b["durum"], "guven": b["guven"]}
        for b in bag_listesi if b["kaynak_kimlik"] in gorunur and b["hedef_kimlik"] in gorunur
    ]
    return {"book_slug": book_slug, "en_cok_bolum": en_cok_bolum, "nodes": dugumler, "edges": kenarlar}
