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

from . import db, defter_kayit, glossary, karakter_defteri, runler, varlik_grafigi, wiki_arastirma
from .runler import genel

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


def _tekil_run(kayitlar: list[dict]) -> list[dict]:
    """Kişinin takma adlarıyla gelen tekil alanlarda (sınıf, rütbe…) yalnız en son değer kalır:
    353'te "Name: Nephis." Demon, 524'te "Master: Changing Star." Devil — ikisi aynı kişi."""
    coklu, secili = [], {}
    for k in kayitlar:
        if k["ad"] in defter_kayit.COKLU_ALANLAR:
            coklu.append(k)
            continue
        eski = secili.get(k["ad"])
        if eski is None or ((k["ilk_bolum"] or 0), k["origin"] == "elle") > \
                ((eski["ilk_bolum"] or 0), eski["origin"] == "elle"):
            secili[k["ad"]] = k
    return coklu + list(secili.values())


ANLATIM = "anlatim"  # anlatımdan gelen/türetilen rün alanının kökeni (rün mesajı değil)


def _ust_deger(run: list[dict], alan: str, adaylar: list[dict], basamak, sahip: str,
               sahip_kimlik: str) -> tuple[list[dict], dict | None]:
    """Anlatımdan gelen aday rün değerinden hem SONRA hem daha YÜKSEK basamaktaysa güncel değer
    odur (sınıf ve rütbe geri gitmez). Sonra gelen elle değer yine kazanır."""
    mevcut = next((k for k in run if k["ad"] == alan), None)
    taban, bolum = (basamak(mevcut["deger"]), mevcut["ilk_bolum"] or 0) if mevcut else (0, 0)
    secilen = [s for s in adaylar if basamak(s["ad"]) > taban and (s["ilk_bolum"] or 0) > bolum]
    if not secilen:
        return run, None
    en = max(secilen, key=lambda s: (basamak(s["ad"]), -(s["ilk_bolum"] or 0)))
    yeni = {"anahtar": None, "tur": "alan", "sahip": mevcut["sahip"] if mevcut else sahip,
            "sahip_kimlik": sahip_kimlik, "ad": alan, "deger": en["ad"], "kimlik": None, "tr": None,
            "alanlar": {}, "ilk_bolum": en["ilk_bolum"], "son_bolum": en["ilk_bolum"], "kanit": en["kanit"],
            "origin": ANLATIM}
    return [k for k in run if k is not mevcut] + [yeni], yeni


def _anlatim_sinifi(book_slug: str, sahip: str, sahip_kimlik: str, run: list[dict],
                    siniflar: list[dict], olaylar: list[dict] = ()) -> list[dict]:
    """Rün ekranı seyrek açılır; sınıf/rütbe atlaması çoğu zaman YALNIZ anlatımda geçer (Sunny
    1090: "His fifth one... And... he was a Tyrant." — rünler en son 1026'da "Class: Devil.").

    Adaylar: anlatımdan `sinifi` bağları ve modelin durum değişimleri (`olaylar`: sinif/rutbe/
    cekirdek "oldu"). Sıra profilden (`yaratik_sinifi`, `rutbe_basamaklari`). Rün biçimi çekirdek
    olayını sınıfa çevirir (`cekirdekten_sinif`) ve sınıfa bağlı alanları (çekirdek, parça eşiği)
    `siniftan_turet` ile günceller."""
    p = varlik_grafigi.profil(book_slug) or {}
    bicim = runler.bicim(p)
    dizi = list((p.get("diziler") or {}).get("yaratik_sinifi", ()))
    sira = [x.casefold() for x in dizi]
    rutbe_sira = {k.casefold(): v for k, v in (p.get("rutbe_basamaklari") or {}).items()}

    def basamak(ad):
        return sira.index(ad.casefold()) + 1 if (ad or "").casefold() in sira else 0

    siniflar, rutbeler = list(siniflar), []
    for o in olaylar:
        if o["i"] != "oldu":
            continue
        aday = {"ad": o["n"], "ilk_bolum": o["bolum"], "kanit": o["kanit"]}
        if o["k"] == "sinif":
            siniflar.append(aday)
        elif o["k"] == "rutbe":
            rutbeler.append(aday)
        elif o["k"] == "cekirdek" and bicim is not None and hasattr(bicim, "cekirdekten_sinif"):
            ad = bicim.cekirdekten_sinif(int(o["n"]), dizi)
            if ad:
                siniflar.append({**aday, "ad": ad})
    run, _ = _ust_deger(run, "rutbesi", rutbeler, lambda ad: rutbe_sira.get((ad or "").casefold(), 0),
                        sahip, sahip_kimlik)
    run, sinif = _ust_deger(run, "sinifi", siniflar, basamak, sahip, sahip_kimlik)
    if sinif is not None and bicim is not None and hasattr(bicim, "siniftan_turet"):
        run = bicim.siniftan_turet(run, sinif, basamak(sinif["deger"]))
    for k in run:
        if k["anahtar"] is None:
            k["anahtar"] = defter_kayit.anahtar("alan", k["sahip"], k["ad"], k["deger"])
    return run


def _anlatim_olaylari(book_slug: str, kimlikler: set[str], konum: int | None) -> list[dict]:
    """Modelin anlatımdan çektiği durum değişimleri (`defter_iddia`, tur='durum'), konuma kadar,
    bölüm sırasıyla. Rün mesajı olmadan olan kazanç/kayıp/evrim/basamak buradan gelir."""
    if not kimlikler:
        return []
    conn = karakter_defteri._connect()
    try:
        satirlar = conn.execute(
            "SELECT bolum, iliski, nesne_ad, deger, en_alinti FROM defter_iddia WHERE book_slug = ? "
            "AND tur = 'durum' AND gecerli = 1 AND bolum <= ? "
            f"AND ozne_kimlik IN ({', '.join('?' for _ in kimlikler)}) ORDER BY bolum, id",
            (book_slug, _sinir(konum), *sorted(kimlikler))).fetchall()
    finally:
        conn.close()
    out = []
    for bolum, kategori, ad, deger, kanit in satirlar:
        d = json.loads(deger or "{}") or {}
        out.append({"bolum": bolum, "k": kategori, "i": d.get("i"), "n": ad, "y": d.get("y"), "kanit": kanit})
    return out


def _anlatim_esyalari(olaylar: list[dict], sahip: str, sahip_kimlik: str, listeler: dict[str, list],
                      run: list[dict]) -> None:
    """Anlatımdaki kazanç/kayıp/evrimi kartın listelerine işle (yerinde). Rün kanıtı üstündür: olay
    öğenin rünlerde SON görüldüğü bölümden sonra değilse uygulanmaz (sonraki tam liste onu
    yeniden gösterdiyse kayıp sanılmaz). Kayıt silinmez; `elde` değişir, kanıtı yanında durur."""
    def bul(tur, ad):
        return next((k for k in listeler.get(tur, ()) if k["tur"] == tur
                     and glossary.fold_term(k["ad"]) == glossary.fold_term(ad)), None)

    def sonra_mi(k, bolum):
        return bolum > (k.get("son_bolum") or k.get("ilk_bolum") or 0)

    def elde_yap(k, durum, o):
        k["alanlar"] = {**(k.get("alanlar") or {}), "elde": durum}
        k["elde_bolum"], k["elde_kanit"] = o["bolum"], o["kanit"]

    for o in olaylar:
        tur = o["k"]
        if tur == "yetenek" and o["i"] == "kazandi":
            if not any(k["ad"] == "yetenegi" and glossary.fold_term(k["deger"]) == glossary.fold_term(o["n"])
                       for k in run):
                run.append({"anahtar": defter_kayit.anahtar("alan", sahip, "yetenegi", o["n"]), "tur": "alan",
                            "sahip": sahip, "sahip_kimlik": sahip_kimlik, "ad": "yetenegi", "deger": o["n"],
                            "kimlik": None, "tr": None, "alanlar": {}, "ilk_bolum": o["bolum"],
                            "son_bolum": o["bolum"], "kanit": o["kanit"], "origin": ANLATIM})
            continue
        if tur not in listeler:
            continue
        if o["i"] in ("kaybetti", "evrimlesti"):
            k = bul(tur, o["n"])
            if k is not None and sonra_mi(k, o["bolum"]) and (k.get("alanlar") or {}).get("elde") != "yok":
                elde_yap(k, "yok", o)
        kazanilan = o["y"] if o["i"] == "evrimlesti" else o["n"] if o["i"] == "kazandi" else None
        if not kazanilan:
            continue
        k = bul(tur, kazanilan)
        if k is None:
            listeler[tur].append({"anahtar": defter_kayit.anahtar(tur, sahip, kazanilan), "tur": tur,
                                  "sahip": sahip, "sahip_kimlik": sahip_kimlik, "ad": kazanilan, "deger": "",
                                  "kimlik": None, "tr": None, "alanlar": {}, "ilk_bolum": o["bolum"],
                                  "son_bolum": o["bolum"], "kanit": o["kanit"], "origin": ANLATIM,
                                  **({"efsunlar": []} if tur == "ani" else {})})
        elif (k.get("alanlar") or {}).get("elde") == "yok" and sonra_mi(k, o["bolum"]):
            elde_yap(k, "var", o)
        if tur == "golge":  # yankı gölgeye dönüştü
            y = bul("yanki", kazanilan)
            if y is not None and sonra_mi(y, o["bolum"]) and (y.get("alanlar") or {}).get("elde") != "yok":
                elde_yap(y, "yok", o)


def _wiki(book_slug: str, adlar: list[str], konum: int | None, kayitlar: list[dict]) -> dict:
    """Kişinin wiki notları (konuma kadar dipnotlu) ve wikide geçip defterde HİÇ olmayan köşeli
    adlar — defterin kaçırdığını gösteren dış kontrol. Sayfa henüz çekilmediyse arka planda başlar."""
    wiki_arastirma.sayfa_gerekirse(book_slug, adlar)
    w = wiki_arastirma.notlar(book_slug, adlar, konum)
    bilinen: set[str] = set()
    for k in kayitlar:
        degerler = [k.get("ad"), k.get("deger")]
        for v in (k.get("alanlar") or {}).values():
            degerler += v if isinstance(v, list) else [v]
        bilinen |= {glossary.fold_term(d) for d in degerler if isinstance(d, str) and d}
    w["eksikler"] = wiki_arastirma.eksik_adlar(w["notlar"], bilinen)
    return w


def _uyarilar(book_slug: str, run: list[dict], yankilar: list[dict]) -> list[str]:
    """Kartın kendi içindeki çelişkiler (rün biçiminin `tutarlilik` kuralları). Yalnız konumda
    elde olan gölgeler sayılır: evrimleşmiş eski hâller (Stone/Marble Saint) çekirdek tutmaz."""
    p = varlik_grafigi.profil(book_slug) or {}
    bicim = runler.bicim(p)
    if bicim is None or not hasattr(bicim, "tutarlilik"):
        return []
    golge = sum(1 for k in yankilar if k["tur"] == "golge" and (k.get("alanlar") or {}).get("elde") != "yok")
    sira = [x.casefold() for x in (p.get("diziler") or {}).get("yaratik_sinifi", ())]
    return bicim.tutarlilik(run, golge, sira)


def _rutbe_gecmisi(book_slug: str, rutbeler) -> list[dict]:
    """Anlatımdan gelen rütbe bağları, bölüm sırasıyla. Kitap profilinde basamaklar varsa yalnız
    rütbeler kalır (canlı kart: Sunny "Awakened → Devil → Ascended" — Devil sınıftır) ve sonradan
    daha DÜŞÜĞÜ gelen rütbe atılır (Nephis 98'de "Saint", 352'de "Dreamer": rütbe geri gitmez)."""
    sirali = sorted(rutbeler, key=lambda r: (r["ilk_bolum"] or 0, r["ad"]))
    basamak = {k.casefold(): v for k, v in ((varlik_grafigi.profil(book_slug) or {})
                                            .get("rutbe_basamaklari") or {}).items()}
    if not basamak:
        return sirali
    sirali = [r for r in sirali if r["ad"].casefold() in basamak]
    return [r for i, r in enumerate(sirali)
            if all(basamak[x["ad"].casefold()] >= basamak[r["ad"].casefold()] for x in sirali[i + 1:])]


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
    takma_tr: dict[str, list[str]] = defaultdict(list)  # aramada Türkçe takma ad da bulunsun
    for b in _baglar(book_slug, konum):
        if b["iliski"] in ("takma_adi", "gercek_adi"):
            if b["durum"] == "onaylandi" or (b["guven"] or 0) >= 0.8:
                takma[b["kaynak_kimlik"]].append(b["hedef"])
                if b["hedef_karsilik"] and b["hedef_karsilik"] != b["hedef"]:
                    takma_tr[b["kaynak_kimlik"]].append(b["hedef_karsilik"])
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
        return {"kimlik": kimlik, "ad": ad, "tr": tr, "takma": takma.get(kimlik, []),
                "takma_tr": takma_tr.get(kimlik, []), "bolum_sayisi": bolum,
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
    efsunlar = defaultdict(list)
    for k in kayit["efsun"]:
        efsunlar[glossary.fold_term(k["sahip"])].append(k)
    anilar = [dict(k, efsunlar=efsunlar.get(glossary.fold_term(k["ad"]), []),
                   efsun_sayisi=len(efsunlar.get(glossary.fold_term(k["ad"]), []))) for k in kayit["ani"]]
    return {"sinir": konum, "kisiler": kisiler, "gruplar": gruplar, "yaratiklar": yaratiklar,
            "anilar": anilar, "nitelikler": kayit["nitelik"], "yankilar": kayit["golge"] + kayit["yanki"],
            "karsiliklar": _karsiliklar(book_slug, [*yaratiklar, *anilar, *kayit["golge"], *kayit["yanki"]]),
            "iliskiler": {k: v["etiket"] for k, v in varlik_grafigi.ILISKILER.items()
                          if k in karakter_defteri.DEFTER_ILISKILERI},
            # Rün biçimi olmayan kitapta "Sistem mesajları" sekmesi (veri ayrı uçtan: `sistem_mesajlari`).
            "sistem_sekmesi": runler.bicim(varlik_grafigi.profil(book_slug)) is None}


SISTEM_EN_COK = 500


def sistem_mesajlari(book_slug: str, konum: int | None) -> dict:
    """Rün biçimi olmayan kitabın HAM sistem mesajları (`runler.genel`), paragraf başına bir kayıt.

    Bölüm hizalıysa okurun gördüğü TÜRKÇE paragraf, değilse İngilizce satırlar gösterilir. Spoiler:
    yalnız `konum`a kadarki bölümler. En yeni `SISTEM_EN_COK` kayıt döner (bölüm sırasıyla).
    Biçimi olan kitapta (SS) ayrıntılı rün listesi kullanılır; burada boş döner."""
    p = varlik_grafigi.profil(book_slug) or {}
    if runler.bicim(p) is not None:
        return {"sinir": konum, "mesajlar": [], "anahtarlar": {}}
    sesler, anahtarlar = tuple(p.get("sistem_sesi") or ()), tuple(p.get("sistem_anahtarlari") or ())
    conn = db.connect()
    try:
        satirlar = conn.execute(
            "SELECT chapter_no, source_text, translation FROM chapters WHERE book_slug = ? AND chapter_no IS NOT NULL "
            "AND source_text IS NOT NULL AND IFNULL(content_type, 'text') != 'html' AND (? IS NULL OR chapter_no <= ?) "
            "ORDER BY chapter_no, created_at DESC", (book_slug, konum, konum)).fetchall()
    finally:
        conn.close()
    mesajlar, gorulen, sozluk = [], set(), Counter()
    for no, kaynak, ceviri in satirlar:
        if no in gorulen:
            continue  # aynı bölümün eski kaydı
        gorulen.add(no)
        bulunan = genel.sistem_satirlari(kaynak, sesler, anahtarlar)
        if not bulunan:
            continue
        sozluk.update(genel.anahtar_sozlugu(bulunan))
        en_p = [x.strip() for x in kaynak.split("\n\n")]
        tr_p = [x.strip() for x in (ceviri or "").split("\n\n")]
        hizali = bool(ceviri) and len(en_p) == len(tr_p)
        paragraflar: dict[int, list[dict]] = {}
        for s in bulunan:
            paragraflar.setdefault(s["paragraf"], []).append(s)
        for i, ss in paragraflar.items():
            en = "\n".join(s["satir"] for s in ss)
            mesajlar.append({"bolum": no, "tur": ss[0]["tur"], "anahtarlar": [s["anahtar"] for s in ss if s["anahtar"]],
                             "metin": tr_p[i] if hizali else en, "en": en, "turkce": hizali})
    return {"sinir": konum, "mesajlar": mesajlar[-SISTEM_EN_COK:], "anahtarlar": dict(sozluk.most_common(30))}


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
    adlar, oneriler, baglar, rutbeler, siniflar = [], [], [], {}, []
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
        if b["iliski"] == "sinifi" and giden:
            siniflar.append({"ad": diger, "ilk_bolum": b["ilk_bolum"], "kanit": b["kanit"]})
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
    # Kişinin bütün kimlikleri (Sunny + Sunless…): model iddiayı hangi adla yazdıysa.
    kimlikler = {kimlik} | {k for k, r in sozluk.items() if glossary.fold_term(r["source"]) in katli}
    olaylar = _anlatim_olaylari(book_slug, kimlikler, konum)
    run = _anlatim_sinifi(book_slug, ad, kimlik, _tekil_run(sahibin("alan")), siniflar, olaylar)
    yankilar = sahibin("golge") + sahibin("yanki")
    nitelikler = sahibin("nitelik")
    _anlatim_esyalari(olaylar, ad, kimlik, {"ani": anilar, "golge": yankilar, "yanki": yankilar,
                                             "nitelik": nitelikler}, run)
    karsiliklar = _karsiliklar(book_slug, [*run, *anilar, *yankilar, *nitelikler, *sahibin("yaratik")])
    wiki = _wiki(book_slug, [ad, *(a["ad"] for a in adlar)], konum,
                 [*(x for liste in kayit.values() for x in liste), *run, *anilar, *yankilar, *nitelikler])
    return {"kimlik": kimlik, "ad": ad, "tr": tr, "tur": tur, "sozlukte": kimlik in sozluk, "sinir": konum,
            "wiki": wiki,
            "uyarilar": _uyarilar(book_slug, run, yankilar),
            "bolum_sayisi": sayi.get(kimlik) or (sozluksuz.get(kimlik) or {}).get("bolum", 0), "ilk_bolum": ilk,
            "adlar": adlar, "oneriler": oneriler, "baglar": baglar, "hitaplar": hitaplar,
            "rutbeler": _rutbe_gecmisi(book_slug, rutbeler.values()),
            "run": run, "anilar": anilar, "yankilar": yankilar, "karsiliklar": karsiliklar,
            "nitelikler": nitelikler, "yaratiklar": sahibin("yaratik")}
