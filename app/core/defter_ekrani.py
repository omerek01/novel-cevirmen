"""DEFTER EKRANI: karakter defterinin okura görünen yüzü (Faz 4, 2026-10-15).

Üç kaynağı tek görünümde birleştirir, hiçbirini kopyalamaz:
  * `karakter_defteri` — bölümlerde geçen kişiler (`defter_iddia`), sen/siz tablosu;
  * `varlik_grafigi.varlik_bag` — kişiler arası bağlar (model adayı, rün, elle);
  * `defter_kayit` — rün listesi, anılar/efsunlar, nitelikler, gölgeler/yankılar, yaratıklar.

SPOILER: her sayım ve kayıt `konum`a (okuma konumu) kadar süzülür; `konum` None = tüm kitap.
Karşılıklar sözlükten okunur (sözlükle ortak: düzeltme sözlükte yapılır)."""
from __future__ import annotations

import json
from collections import Counter, defaultdict

from . import defter_kayit, glossary, karakter_defteri, varlik_grafigi

KISI_TURU = "kisi"
GRUP_TURU = "orgut"
# Kullanıcının kendi açtığı tür adları (sözlükte "Canavar" türü 40 kayıt): yaratık sayılır.
_YARATIK_TURLERI = frozenset({"canavar", "yaratik", "yaratık", "monster"})
# Kişisiz kayıtlardan liste için en az bölüm (tek geçişli adlar kalabalık yapar).
SOZLUKSUZ_EN_AZ = 3
# Kartta gösterilmeyen bağlar: takma ad "Adları"nda, rün bağları rün listesinde gösterilir.
_KART_DISI_ILISKILER = frozenset({"takma_adi", "gercek_adi", "anisi", "golgesi", "yanki", "efsunu",
                                  "niteligi", "gorunusu", "yetenegi", "turu", "esya_turu", "sinifi",
                                  "kusuru", "ruya_capasi", "oldurdu", "kendi_golgesi", "ust_basamak",
                                  "rutbesi"})
# Sözlüksüz kişi adında unvan ya da cins sözcük: "Lady Nephis", "Captain Sunless" kayıtlı kişinin
# unvanlı hâlidir, "Knight"/"Prince" cins addır (sunucu kopyasında listeyi bunlar dolduruyordu).
_UNVANLAR = frozenset({
    "lady", "lord", "captain", "professor", "sergeant", "master", "saint", "prince", "princess", "sir",
    "knight", "teacher", "sister", "brother", "lieutenant", "colonel", "general", "doctor", "dr", "madam",
    "miss", "mister", "mr", "mrs", "king", "queen", "young", "old", "elder", "sovereign", "the", "little",
})


def _unvanli(ad: str) -> bool:
    sozcukler = [w.strip(".,").casefold() for w in (ad or "").split()]
    return not sozcukler or sozcukler[0] in _UNVANLAR or all(w in _UNVANLAR for w in sozcukler)


def _destek_anahtari(o, iliski: str, n) -> tuple:
    """Simetrik ilişkide yön yoktur; ötekinde "Sunny'nin öğretmeni Julius" ile tersi ayrı iddiadır."""
    if varlik_grafigi.ILISKILER.get(iliski, {}).get("simetrik"):
        return (frozenset((o, n)), iliski)
    return (o, iliski, n)


def _sinir(konum: int | None) -> int:
    return konum if konum is not None else 10**9


def _sozluk(book_slug: str) -> dict[str, dict]:
    return {r["kimlik"]: r for r in glossary.get_glossary_rows(book_slug) if r.get("kimlik")}


def _bolum_sayilari(conn, book_slug: str, konum: int | None) -> tuple[Counter, dict[str, dict]]:
    """Kimlik -> geçtiği bölüm sayısı; sözlüksüz kişi adları -> {ad, bolum, ilk}."""
    sayi: Counter = Counter()
    sozluksuz: dict[str, dict] = {}
    for kimlik, ad, deger, adet, ilk in conn.execute(
        "SELECT ozne_kimlik, ozne_ad, MAX(deger), COUNT(DISTINCT bolum), MIN(bolum) FROM defter_iddia "
        "WHERE book_slug = ? AND tur = 'varlik' AND gecerli = 1 AND bolum <= ? "
        "GROUP BY ozne_kimlik, CASE WHEN ozne_kimlik IS NULL THEN lower(ozne_ad) END",
        (book_slug, _sinir(konum)),
    ):
        if kimlik:
            sayi[kimlik] += adet
        elif (ad and (json.loads(deger or "{}") or {}).get("t") == KISI_TURU and adet >= SOZLUKSUZ_EN_AZ
              and not _unvanli(ad)):
            sozluksuz["ad:" + glossary.fold_term(ad)] = {"ad": ad, "bolum": adet, "ilk": ilk}
    return sayi, sozluksuz


def _baglar(book_slug: str, konum: int | None, kimlik: str | None = None) -> list[dict]:
    return [b for b in varlik_grafigi.baglar(book_slug, konum, kimlik=kimlik)
            if "#" not in b["kaynak_kimlik"] and "#" not in b["hedef_kimlik"]]


def _karsiliklar(book_slug: str, kayitlar) -> dict[str, str]:
    """Kayıtlardaki rün DEĞERLERİNİN (Awakened, Weapon, Devil…) sözlük karşılıkları."""
    cozucu = varlik_grafigi.DugumCozucu(book_slug)
    degerler: set[str] = set()
    for k in kayitlar:
        if k.get("deger"):
            degerler.add(k["deger"])
        for v in (k.get("alanlar") or {}).values():
            for x in (v if isinstance(v, list) else [v]):
                if isinstance(x, str) and len(x) <= 60:
                    degerler.add(x)
    out = {}
    for d in degerler:
        kim = cozucu.coz(d)
        if kim and cozucu.satirlar[kim].get("target"):
            out[d] = cozucu.satirlar[kim]["target"]
    return out


def liste(book_slug: str, konum: int | None) -> dict:
    """Defter ekranının sekmeleri: kişiler, gruplar, yaratıklar, anılar, nitelikler, yankılar."""
    sozluk = _sozluk(book_slug)
    conn = karakter_defteri._connect()
    try:
        sayi, sozluksuz = _bolum_sayilari(conn, book_slug, konum)
        tablo = karakter_defteri.hitap_tablosu(book_slug, konum, conn)
    finally:
        conn.close()
    kayit = defter_kayit.gorunum(book_slug, konum)["kayitlar"]
    bag_sayisi: Counter = Counter()
    takma: dict[str, list[str]] = defaultdict(list)
    for b in _baglar(book_slug, konum):
        if b["iliski"] in ("takma_adi", "gercek_adi"):
            if b["durum"] == "onaylandi" or (b["guven"] or 0) >= 0.8:
                takma[b["kaynak_kimlik"]].append(b["hedef"])
        elif b["iliski"] not in _KART_DISI_ILISKILER:
            bag_sayisi[b["kaynak_kimlik"]] += 1
            bag_sayisi[b["hedef_kimlik"]] += 1
    hitap_cifti: Counter = Counter()
    karisik: Counter = Counter()
    for (ko, mu), t in tablo.items():
        for uc in (ko, mu):
            if t["kararli"]:
                hitap_cifti[uc] += 1
            elif t["n"] >= karakter_defteri.KARARLI_EN_AZ:
                karisik[uc] += 1
    run_sahipleri = Counter(glossary.fold_term(k["sahip"]) for t in ("ani", "alan") for k in kayit[t])

    def ozet(kimlik: str, ad: str, tr: str | None, bolum: int) -> dict:
        katli = {glossary.fold_term(x) for x in (ad, *takma.get(kimlik, []))}
        return {"kimlik": kimlik, "ad": ad, "tr": tr, "takma": takma.get(kimlik, []), "bolum_sayisi": bolum,
                "bag_sayisi": bag_sayisi[kimlik], "hitap_cifti": hitap_cifti[kimlik], "karisik": karisik[kimlik],
                "ani_sayisi": sum(1 for k in kayit["ani"] if glossary.fold_term(k["sahip"]) in katli),
                "run": any(run_sahipleri[x] for x in katli)}

    # Takma adı olan kişi ayrı satır olmaz: aynı kişinin kayıtları tek satırda, en çok geçen adla.
    gizli: set[str] = set()
    kok: dict[str, str] = {}

    def bul(x):
        while kok.get(x, x) != x:
            x = kok[x]
        return x

    for b in _baglar(book_slug, konum):
        if (b["iliski"] == "takma_adi" and (b["durum"] == "onaylandi" or (b["guven"] or 0) >= 0.8)
                and all((sozluk.get(u) or {}).get("tur") == KISI_TURU for u in (b["kaynak_kimlik"], b["hedef_kimlik"]))):
            a, h = bul(b["kaynak_kimlik"]), bul(b["hedef_kimlik"])
            if a != h:
                ana, yan = sorted((a, h), key=lambda u: (-sayi[u], sozluk[u]["source"].casefold()))
                kok[yan] = ana
    for u in list(kok):
        ana = bul(u)
        if ana != u:
            gizli.add(u)
            ad_ = sozluk[u]["source"]
            if ad_ not in takma[ana]:
                takma[ana].append(ad_)
    kisiler, gruplar = [], []
    for kimlik, r in sozluk.items():
        if not sayi[kimlik] or kimlik in gizli:
            continue
        if r.get("tur") == KISI_TURU:
            kisiler.append(ozet(kimlik, r["source"], r.get("target"), sayi[kimlik]))
        elif r.get("tur") == GRUP_TURU:
            gruplar.append(ozet(kimlik, r["source"], r.get("target"), sayi[kimlik]))
    for uc, s in sozluksuz.items():
        kisiler.append(dict(ozet(uc, s["ad"], None, s["bolum"]), sozlukte=False))
    for liste_ in (kisiler, gruplar):
        liste_.sort(key=lambda k: (-k["bolum_sayisi"], k["ad"].casefold()))

    yaratiklar = [dict(k, oldurulme=k["ilk_bolum"]) for k in kayit["yaratik"]]
    oldurulen = {glossary.fold_term(k["ad"]) for k in yaratiklar}
    for kimlik, r in sozluk.items():
        if (r.get("tur") or "").casefold() in _YARATIK_TURLERI and glossary.fold_term(r["source"]) not in oldurulen:
            ilk = r.get("first_chapter")
            if konum is None or ilk is None or ilk <= konum:
                yaratiklar.append({"anahtar": None, "tur": "yaratik", "ad": r["source"], "tr": r.get("target"),
                                   "kimlik": kimlik, "sahip": "", "alanlar": {}, "ilk_bolum": ilk,
                                   "oldurulme": None, "origin": "sozluk"})
    yaratiklar.sort(key=lambda k: (k["ilk_bolum"] or 0, k["ad"].casefold()))
    efsun_sayisi = Counter(glossary.fold_term(k["sahip"]) for k in kayit["efsun"])
    anilar = [dict(k, efsun_sayisi=efsun_sayisi[glossary.fold_term(k["ad"])]) for k in kayit["ani"]]
    return {"sinir": konum, "kisiler": kisiler, "gruplar": gruplar, "yaratiklar": yaratiklar,
            "anilar": anilar, "nitelikler": kayit["nitelik"], "yankilar": kayit["golge"] + kayit["yanki"],
            "karsiliklar": _karsiliklar(book_slug, [*yaratiklar, *anilar, *kayit["golge"], *kayit["yanki"]]),
            "iliskiler": {k: v["etiket"] for k, v in varlik_grafigi.ILISKILER.items()
                          if k in karakter_defteri.DEFTER_ILISKILERI}}


def kart(book_slug: str, kimlik: str, konum: int | None) -> dict | None:
    """Tek kişinin kartı: adları, takma ad önerileri, bağları (destekle), hitapları, rün listesi,
    anıları (efsunlarıyla), gölgeleri/yankıları ve nitelikleri. Bilinmeyen kimlik -> None."""
    sozluk = _sozluk(book_slug)
    conn = karakter_defteri._connect()
    try:
        sayi, sozluksuz = _bolum_sayilari(conn, book_slug, konum)
        if kimlik in sozluk:
            r = sozluk[kimlik]
            ad, tr, tur = r["source"], r.get("target"), r.get("tur")
        elif kimlik in sozluksuz:
            ad, tr, tur = sozluksuz[kimlik]["ad"], None, KISI_TURU
        else:
            return None
        ilk = conn.execute(
            "SELECT MIN(bolum) FROM defter_iddia WHERE book_slug = ? AND tur = 'varlik' AND gecerli = 1 "
            "AND (ozne_kimlik = ? OR (ozne_kimlik IS NULL AND lower(ozne_ad) = lower(?))) AND bolum <= ?",
            (book_slug, kimlik, ad, _sinir(konum))).fetchone()[0]
        destek: Counter = Counter()
        for o, i, n, adet in conn.execute(
            "SELECT ozne_kimlik, iliski, nesne_kimlik, COUNT(DISTINCT bolum) FROM defter_iddia WHERE book_slug = ? "
            "AND tur = 'bag' AND gecerli = 1 AND bolum <= ? AND (ozne_kimlik = ? OR nesne_kimlik = ?) "
            "GROUP BY ozne_kimlik, iliski, nesne_kimlik", (book_slug, _sinir(konum), kimlik, kimlik)):
            destek[_destek_anahtari(o, i, n)] += adet
        tablo = karakter_defteri.hitap_tablosu(book_slug, konum, conn)
    finally:
        conn.close()
    adlar, oneriler, baglar, rutbeler = [], [], [], {}
    for b in (_baglar(book_slug, konum, kimlik) if kimlik in sozluk else []):
        giden = b["kaynak_kimlik"] == kimlik
        diger_k, diger, diger_tr = ((b["hedef_kimlik"], b["hedef"], b["hedef_karsilik"]) if giden
                                    else (b["kaynak_kimlik"], b["kaynak"], b["kaynak_karsilik"]))
        if b["iliski"] in ("takma_adi", "gercek_adi"):
            if b["durum"] == "onaylandi" or (b["guven"] or 0) >= 0.8:
                adlar.append({"ad": diger, "tr": diger_tr, "iliski": b["iliski"]})
            elif giden or b["iliski"] == "takma_adi":
                oneriler.append({"asil_kimlik": b["kaynak_kimlik"], "takma_kimlik": b["hedef_kimlik"],
                                 "ad": diger, "destek": destek[_destek_anahtari(
                                     b["kaynak_kimlik"], b["iliski"], b["hedef_kimlik"])]})
            continue
        if b["iliski"] == "rutbesi":
            # Rütbe bağları rün listesinde "rütbe geçmişi" olur (anlatımdan; rün mesajı seyrek).
            if giden:
                r = rutbeler.setdefault(diger_k, {"ad": diger, "tr": diger_tr, "ilk_bolum": b["ilk_bolum"],
                                                  "destek": 0, "origin": b["origin"]})
                r["destek"] = max(r["destek"], destek[_destek_anahtari(kimlik, "rutbesi", diger_k)])
            continue
        if b["iliski"] in _KART_DISI_ILISKILER:
            continue
        tanim = varlik_grafigi.ILISKILER.get(b["iliski"], {})
        baglar.append({
            "iliski": b["iliski"], "etiket": tanim.get("etiket", b["iliski"]), "simetrik": bool(tanim.get("simetrik")),
            "yon": "iki" if tanim.get("simetrik") else ("giden" if giden else "gelen"),
            "kaynak_kimlik": b["kaynak_kimlik"], "hedef_kimlik": b["hedef_kimlik"],
            "diger_kimlik": diger_k, "diger_ad": diger, "diger_tr": diger_tr, "ilk_bolum": b["ilk_bolum"],
            "destek": destek[_destek_anahtari(b["kaynak_kimlik"], b["iliski"], b["hedef_kimlik"])],
            "durum": b["durum"], "origin": b["origin"], "guven": b["guven"],
        })
    baglar.sort(key=lambda x: (x["durum"] != "onaylandi" and (x["guven"] or 0) < 0.8, -x["destek"],
                               x["diger_ad"].casefold()))
    hitaplar = []
    for (ko, mu), t in tablo.items():
        if kimlik not in (ko, mu) or not t["bicim"]:
            continue
        hitaplar.append({"ko": ko, "mu": mu, "konusan": t["konusan"], "muhatap": t["muhatap"],
                         "bicim": t["bicim"], "n": t["n"], "oran": t["oran"], "kararli": t["kararli"],
                         "elle": t["elle"], "son_bolum": t["son_bolum"]})
    hitaplar.sort(key=lambda h: (not h["elle"] and not h["kararli"], -h["n"]))
    tekil, gorulen = [], {glossary.fold_term(ad)}
    for a in adlar:
        if glossary.fold_term(a["ad"]) not in gorulen:
            gorulen.add(glossary.fold_term(a["ad"]))
            tekil.append(a)
    adlar = tekil
    oneri_tekil = {}
    for o in sorted(oneriler, key=lambda o: -o["destek"]):
        oneri_tekil.setdefault(glossary.fold_term(o["ad"]), o)
    oneriler = [o for k, o in oneri_tekil.items() if k not in gorulen][:8]
    katli = set(gorulen)
    kayit = defter_kayit.gorunum(book_slug, konum)["kayitlar"]

    def sahibin(tur):
        return [k for k in kayit[tur] if glossary.fold_term(k["sahip"]) in katli]

    efsunlar = defaultdict(list)
    for k in kayit["efsun"]:
        efsunlar[glossary.fold_term(k["sahip"])].append(k)
    anilar = [dict(k, efsunlar=efsunlar.get(glossary.fold_term(k["ad"]), [])) for k in sahibin("ani")]
    run, yankilar = sahibin("alan"), sahibin("golge") + sahibin("yanki")
    karsiliklar = _karsiliklar(book_slug, [*run, *anilar, *yankilar, *sahibin("yaratik")])
    return {"kimlik": kimlik, "ad": ad, "tr": tr, "tur": tur, "sozlukte": kimlik in sozluk, "sinir": konum,
            "bolum_sayisi": sayi.get(kimlik) or (sozluksuz.get(kimlik) or {}).get("bolum", 0), "ilk_bolum": ilk,
            "adlar": adlar, "oneriler": oneriler, "baglar": baglar, "hitaplar": hitaplar,
            "rutbeler": sorted(rutbeler.values(), key=lambda r: (r["ilk_bolum"] or 0, r["ad"])),
            "run": run, "anilar": anilar, "yankilar": yankilar, "karsiliklar": karsiliklar,
            "nitelikler": sahibin("nitelik"), "yaratiklar": sahibin("yaratik")}
