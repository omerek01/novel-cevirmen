"""Varlık grafiği — MODEL çıkarımı (`PLAN-varlik-grafigi.md` aşama 3).

Sistem katmanı (`varlik_grafigi.sistem_baglarini_bul`) yalnız rün mesajlarını
okur: sunucu kopyasında 189 bağ. Kişiler arası ilişkiler, klanlar, yerler, takma
adlar düz anlatıda geçer ve ancak model çıkarabilir.

Kurallar (uydurma bağa karşı — grafiğin en büyük riski):
  * Model YALNIZ verilen listedeki varlıklar arasında bağ kurar (bölümde geçen
    sözlük kayıtları). Yeni ad bulursa ayrı listede döner; sözlüğe girmez,
    raporlanır (sözlüğe yazma kapısından geçerek girmeli).
  * İlişki türü denetimli sözlükten (`varlik_grafigi.ILISKILER`); bilinmeyen tür
    atılır.
  * KANIT cümlesi kaynakta birebir geçmeli VE iki varlığın adı (ya da kayıtlı
    yazımı) o cümlede bulunmalı. Değilse bağ ATILIR — `ayikla_terim_anahtarlari`
    dersiyle aynı: kaynakta doğrulanamayan çıktı kaydedilmez.
  * Model bağı `aday` olarak yazılır (sistem ve elle bağlar `onaylandi`).

Zincir: varsayılan ücretsiz (`sozluk_dogrulama.ucretsiz_zincir`). Ücretli bir
model (Vertex) YALNIZ açıkça `models=` ile verilince kullanılır — bakım aracında
`--model` bayrağıyla (kullanıcı kararı 2026-10-06: geriye dönük doldurma Vertex
kredisiyle). Arka planda kendiliğinden ücretli modele inilmez.
"""
from __future__ import annotations

import json
import re
import time

from . import cache, glossary, sozluk_dogrulama, translate, varlik_grafigi

GUVEN_ESIGI = 0.5
YENIDEN_DENEME_SN = (30.0, 90.0, 180.0)

# Talimat ÖLÇÜLEREK düzeltildi (2026-10-06, Vertex 3.6-flash, 10 bölüm örneği):
# ilk sürüm bölüm başına 1,5 bağ verdi, kesinlik ~%70. Hatalar: genel adlar özne
# (`Echo`, `scavengers`, `Transcendents`), anlık konum kalıcı bağ sanıldı (Saint o
# sahnede bir katedraldeydi), "parçası" grup üyeliğine kullanıldı, kişiler arası
# ilişki HİÇ çıkmadı. Aşağıdaki öncelik listesi ve dışlama kuralları bunlara karşı.
CIKARIM_INSTRUCTION = (
    "Sen bir roman için bilgi grafiği çıkaran bir analistsin. Sana bir bölümün "
    "İngilizce metni ve bu bölümde geçen VARLIKLARIN listesi verilecek. Görevin: "
    "listedeki varlıklar arasındaki KALICI ilişkileri bulmak — okurun 'bu kim, kime "
    "bağlı, neyin parçası' sorusuna cevap veren bağları.\n"
    "ÖNCELİK (en değerliden): 1) kimlik: takma adı, Gerçek Adı (True Name), unvanı; "
    "2) kişiler arası: yoldaşı (aynı grupta birlikte savaşan/yaşayan), akrabası, "
    "düşmanı, öğretmeni, klanı, lideri; 3) sahiplik: Anısı (Memory), gölgesi, "
    "Yankısı (Echo), yeteneği, Görünüşü (Aspect); 4) mekân: bir yerin başka bir yerin "
    "parçası olması, bir kişinin bağlı olduğu/yönettiği yer; 5) düzen: türü, rütbesi.\n"
    "Kurallar:\n"
    "- YALNIZ listedeki varlıkları kullan; ad yazımını listedeki gibi AYNEN ver.\n"
    "- Özne ve nesne BELİRLİ bir varlık olmalı (kişi, yer, örgüt, eşya, yetenek). "
    "Genel sınıf/grup adları ÖZNE OLAMAZ ('Echo', 'scavengers', 'Transcendents', "
    "'horde' gibi). Genel ad yalnız türü/rütbesi/sınıfı ilişkisinin NESNESİ olabilir.\n"
    "- bulundugu_yer: bir DÖNEM boyunca yaşadığı, ait olduğu ya da hapsolduğu BÖLGE "
    "(şehir, ada, diyar). Bir sahnede bir odada durmak, yürümek, savaşmak "
    "bulundugu_yer DEĞİLDİR.\n"
    "- parcasi YALNIZ yer -> daha büyük yer içindir (bir kule bir adanın parçası); "
    "kişi/grup üyeliği için klani ya da yoldasi kullan.\n"
    "- unvani: unvan o kişiye METİNDE AÇIKÇA atfedilmeli ('X, the Y' / 'Y known as X').\n"
    # Ölçülen (16-35. bölümler): `Hero -> gercek_adi -> Auro of the Nine`. Hero bir
    # lakap, Auro of the Nine kişinin ADI; True Name ise Spell'in verdiği ayrı bir ad.
    "- niteligi YALNIZ Spell'in [Attribute] olarak adlandırdığı şeyler içindir (Fated, "
    "Mark of Divinity); toplanan kaynaklar, sayılar, yetenekler nitelik DEĞİLDİR.\n"
    "- gercek_adi YALNIZ Spell'in verdiği True Name içindir (rünlerde 'True Name: X' "
    "ya da 'You have been bestowed a True Name'). Bir kişinin asıl adı ile lakabı "
    "arasındaki bağ takma_adi'dır: özne ASIL ad, nesne lakap (Auro of the Nine -> "
    "takma_adi -> Hero).\n"
    "- YALNIZ metinde açıkça söylenen ya da tek cümleden kesin anlaşılan ilişkiyi "
    "yaz. Tahmin, yorum, dış bilgi YOK. Emin değilsen yazma.\n"
    "- Her ilişki için 'kanit': ilişkiyi gösteren cümleyi metinden KELİMESİ KELİMESİNE "
    "kopyala (tek cümle; iki varlığın adı da o cümlede geçmeli).\n"
    "- Listede '(kategori)' işaretli adlar BELİRLİ bir varlık değil, genel sistem "
    "terimidir (Abilities, Aspect Ability, Attribute, Lord, Fallen Terror gibi). "
    "Kategori YALNIZ turu / rutbesi / sinifi ilişkisinin NESNESİ olabilir; hiçbir "
    "ilişkinin öznesi ya da sahiplik/öldürme/düşmanlık/konum nesnesi OLAMAZ.\n"
    "- BİLİNEN BAĞLAR verilirse onlarla ÇELİŞME: bir şey bilinen bağlarda gölge "
    "(golgesi) ise ona Anı (anisi) deme. Bilinen bağı tekrar yazmana gerek yok; YENİ "
    "olanları yaz.\n"
    "- 'iliski' şu listeden biri olmalı (özne -> nesne yönünde):\n"
    + "".join(f"    {k}: {v['etiket']}\n" for k, v in varlik_grafigi.ILISKILER.items())
    + "- Yön: özne ilişkinin SAHİBİ ya da ETKENİDİR (Sunny -> anisi -> Azure Blade; "
    "Cassie -> yoldasi -> Sunny; Crimson Spire -> parcasi -> Forgotten Shore; "
    "Saint -> turu -> Shadow).\n"
    "- 'guven': 0-1 arası; metin ilişkiyi ne kadar açık söylüyor.\n"
    "- Listede OLMAYAN ama bir kişiyi/yeri/örgütü adlandıran özel ad görürsen "
    "'yeni_adlar' listesine yaz (ilişki kurma).\n"
    '- Yanıtı SADECE şu JSON ile ver: {"baglar": [{"ozne": "...", "iliski": "...", '
    '"nesne": "...", "kanit": "...", "guven": 0.9}], "yeni_adlar": ["..."]}'
)


def _normal(metin: str) -> str:
    """Kanıt karşılaştırması için: kıvrık tırnaklar düz, boşluklar tek."""
    metin = (metin or "").replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", metin).strip()


_VARSAYIM = re.compile(
    r"\b(?:if|perhaps|maybe|might|presumably|probably|assume|assumed|suppose|supposed|"
    r"whether|wonder(?:ed)?|suspect(?:ed)?|could be|seemed to be)\b",
    re.IGNORECASE,
)
_ETIKET_EKI = re.compile(r"\s*[\(\[][^()\[\]]*[\)\]]\s*$")


def ad_temizle(ad: str) -> str:
    """Modelin adın sonuna yapıştırdığı liste etiketini at. Ölçülen: listede
    "- Aspect (kategori)" görünce yanıtta ad "Aspect (kategori)" geldi ve doğru
    bağ "nesne kanıtta yok" diye reddedildi (7 bağ, 1-15. bölümler)."""
    return _ETIKET_EKI.sub("", (ad or "").strip()).strip()


def duzen_iliskisini_duzelt(
    bag: dict, diziler: dict[str, tuple[str, ...]], ek_rutbeler: tuple[str, ...] = (),
) -> dict:
    """`rutbesi` ile `sinifi` karışmasını profildeki dizilere göre düzelt.

    Ölçülen: `Mountain King -> rutbesi -> Tyrant` (Tyrant bir SINIF). Nesne bir
    yaratık sınıfıysa ilişki `sinifi`, rütbe dizisindeyse `rutbesi` olur. Kanıt ve
    uçlar değişmez; yalnız etiket — reddetmek doğru bir bilgiyi atardı."""
    if bag.get("iliski") not in ("rutbesi", "sinifi"):
        return bag
    nesne = (bag.get("nesne") or "").casefold()
    siniflar = {x.casefold() for x in diziler.get("yaratik_sinifi", ())}
    rutbeler = {x.casefold() for k, d in diziler.items() if k != "yaratik_sinifi" for x in d}
    if nesne in siniflar and bag["iliski"] == "rutbesi":
        return {**bag, "iliski": "sinifi"}
    if nesne in rutbeler and bag["iliski"] == "sinifi":
        return {**bag, "iliski": "rutbesi"}
    # `rutbesi` YALNIZ gerçek rütbe adlarına (dizi + ek rütbeler); sözcüklerinden biri
    # rütbe değilse UNVANDIR. Ölçülen (502 bağ): Artisan, Chain Lord, Prince of War,
    # Dream Champion, Sorcerer of the East, Lord — 20 bağ "rütbe" yazılmıştı.
    tum_rutbe = rutbeler | siniflar | {x.casefold() for x in ek_rutbeler}
    if bag["iliski"] == "rutbesi" and diziler and not any(
        w.rstrip("s") in {r.rstrip("s") for r in tum_rutbe} for w in nesne.split()
    ):
        return {**bag, "iliski": "unvani"}
    # `sinifi` YALNIZ yaratık sınıfına ayrılır; başka kategori (Flaw, Legacy) türdür.
    # Ölçülen: `Clear Conscience -> sinifi -> Flaw`, `Caster -> sinifi -> Legacy`.
    if bag["iliski"] == "sinifi" and not any(
        w.rstrip("s") in {x.rstrip("s") for x in siniflar} for w in nesne.split()
    ):
        return {**bag, "iliski": "turu"}
    return bag


def _gecer_mi(ad: str, yazimlar: list[str], cumle: str) -> bool:
    return any(translate._term_regex(y).search(cumle) for y in [ad, *yazimlar] if y)


# Aynı iki uç arasında bu ilişkiler birbirini DIŞLAR: rün bağı "gölgesi" diyorsa
# modelin "Anısı" demesi yanlıştır (ölçülen: `Sunny -> anisi -> Soul Serpent`).
_SAHIPLIK = frozenset({"anisi", "golgesi", "yanki", "yetenegi", "niteligi", "gorunusu"})


def yapisal_red(bag: dict, a: str | None, n: str | None, kategoriler: set[str],
                sistem: dict[tuple[str, str], set[str]]) -> str | None:
    """Sözlük düğümlerine çözülmüş bağın yapısal denetimi; geçerliyse None."""
    if not a or not n:
        return "varlık sözlükte yok"
    if a == n:
        return "özne ve nesne aynı"
    if a in kategoriler:
        return "kategori özne olamaz"
    if n in kategoriler and bag.get("iliski") not in varlik_grafigi.KATEGORI_NESNESI_OLABILIR:
        return "kategori bu ilişkinin nesnesi olamaz"
    # Rün (sistem) bağı aynı iki uç için BAŞKA bir ilişki söylüyorsa model yanılıyor.
    # Ölçülen: `Sunless -> unvani -> Shadow Slave`, oysa rün "Aspect: [Shadow Slave]".
    celisen = sistem.get((a, n), set()) - {bag.get("iliski")}
    if celisen:
        return f"rün bağıyla çelişiyor ({', '.join(sorted(celisen))})"
    return None


def kaniti_dogrula(bag: dict, kaynak_metin: str, yazimlar: dict[str, list[str]]) -> str | None:
    """Bağ geçerliyse None, değilse red sebebi. Deterministik, API'siz."""
    if bag.get("iliski") not in varlik_grafigi.ILISKILER:
        return "bilinmeyen ilişki"
    kanit = _normal(bag.get("kanit") or "")
    if len(kanit) < 8:
        return "kanıt yok"
    if kanit not in _normal(kaynak_metin):
        return "kanıt kaynakta birebir geçmiyor"
    for uc in ("ozne", "nesne"):
        if not _gecer_mi(bag.get(uc) or "", yazimlar.get(bag.get(uc) or "", []), kanit):
            return f"{uc} kanıt cümlesinde geçmiyor"
    if (bag.get("guven") or 0) < GUVEN_ESIGI:
        return "güven düşük"
    # Varsayım/koşul cümlesi bir olguyu KANITLAMAZ. Ölçülen: "If he were to assume
    # that Mountain King was a mature Puppeteer Worm..." -> `turu` bağı yazıldı.
    if _VARSAYIM.search(kanit):
        return "varsayım cümlesi kanıt olamaz"
    # Genel ad (küçük harfli sözlük kaydı: `scavengers`, `horde`) özne olamaz;
    # türü/rütbesi/sınıfı ilişkisinin NESNESİ olabilir (`dormant beast`).
    ozne = (bag.get("ozne") or "").strip()
    if ozne[:1].islower():
        return "genel ad özne olamaz"
    return None


def _ayristir(metin: str | None) -> dict:
    ham = (metin or "").strip()
    if ham.startswith("```"):
        ham = ham.strip("`").removeprefix("json").strip()
    try:
        veri = json.loads(ham)
    except (json.JSONDecodeError, TypeError):
        return {"baglar": [], "yeni_adlar": []}
    if not isinstance(veri, dict):
        return {"baglar": [], "yeni_adlar": []}
    return {
        "baglar": [b for b in veri.get("baglar") or [] if isinstance(b, dict)],
        "yeni_adlar": [a for a in veri.get("yeni_adlar") or [] if isinstance(a, str)],
    }


BAGLAM_BAG_SINIRI = 60


def _bilinen_baglar(book_slug: str, gecen_kimlik: set[str], bolum_no: int | None) -> list[dict]:
    """Bu bölümde geçen varlıklar arasında BU BÖLÜMDEN ÖNCE kurulmuş bağlar.

    Ardışık bölümler birbirine bağlansın diye prompt'a girer: model bilinen
    gölgeye "Anı" demez, aynı bağı tekrar üretmez. Spoiler mantığı burada da
    geçerli — sonraki bölümün bilgisi önceki bölümün çıkarımına sızmaz."""
    return [
        b for b in varlik_grafigi.baglar(book_slug, en_cok_bolum=bolum_no)
        if b["kaynak_kimlik"] in gecen_kimlik and b["hedef_kimlik"] in gecen_kimlik
    ][:BAGLAM_BAG_SINIRI]


def bolum_cikar(
    book_slug: str, bolum: dict, api_key: str = "", models: tuple[str, ...] | None = None,
    cozucu: varlik_grafigi.DugumCozucu | None = None,
    kategoriler: set[str] | None = None,
) -> dict:
    """Tek bölümden bağ çıkar. Döner: {"gecerli": [...], "red": [...], "yeni_adlar": [...], "model"}.

    `bolum`: `cache.kaynak_bolumleri` satırı (`source`, `chapter_no`)."""
    kaynak_metin = bolum.get("source") or ""
    cozucu = cozucu or varlik_grafigi.DugumCozucu(book_slug)
    sozluk = glossary.ceviri_sozlugu(book_slug)
    gecen = translate.metinde_gecen_terimler(sozluk, kaynak_metin)
    if len(gecen) < 2:
        return {"gecerli": [], "red": [], "yeni_adlar": [], "model": None}
    kategoriler = kategoriler if kategoriler is not None else varlik_grafigi.kategori_kimlikleri(book_slug, cozucu)
    satir_turu = {r["source"]: r.get("tur") for r in cozucu.satirlar.values()}

    def _etiket(ad: str) -> str:
        if cozucu.coz(ad) in kategoriler:
            return " (kategori)"
        return f" ({satir_turu[ad]})" if satir_turu.get(ad) else ""

    liste = "\n".join(f"- {ad}{_etiket(ad)}" for ad in gecen)
    gecen_kimlik = {k for ad in gecen if (k := cozucu.coz(ad))}
    bilinen = _bilinen_baglar(book_slug, gecen_kimlik, bolum.get("chapter_no"))
    bilinen_metni = "\n".join(
        f"- {b['kaynak']} -> {b['iliski']} -> {b['hedef']}" for b in bilinen
    )
    user = (
        f"VARLIKLAR:\n{liste}\n\n"
        + (f"BİLİNEN BAĞLAR (önceki bölümlerden):\n{bilinen_metni}\n\n" if bilinen else "")
        + f"BÖLÜM METNİ:\n{kaynak_metin}"
    )
    sistem: dict[tuple[str, str], set[str]] = {}
    # TAKMA AD -> asıl kişi (güvenilir kaynaklı `takma_adi` bağlarından). Ölçülen:
    # model `Sunless` (Sunny'nin resmî adı) için ayrı düğümde bağ kurdu; bilgi iki
    # düğüme bölünür ve rün bağlarıyla karşılaştırılamaz.
    asil: dict[str, str] = {}
    for b in varlik_grafigi.baglar(book_slug):
        if b["origin"] == "sistem":
            sistem.setdefault((b["kaynak_kimlik"], b["hedef_kimlik"]), set()).add(b["iliski"])
        # Gerçek Ad da kişiyi adlandırır (ölçülen: `Changing Star -> oldurdu -> ...`
        # Nephis'in düğümüne değil ayrı düğüme yazılıyordu).
        if b["iliski"] in ("takma_adi", "gercek_adi") and b["origin"] in ("sistem", "manual"):
            asil[b["hedef_kimlik"]] = b["kaynak_kimlik"]
    response, model = translate._generate_with_fallback(
        translate._gemini_fabrikasi(api_key), models or sozluk_dogrulama.ucretsiz_zincir(), user,
        system=CIKARIM_INSTRUCTION, max_tokens=translate.MAX_OUTPUT_TOKENS,
    )
    veri = _ayristir(getattr(response, "text", None))
    ekler = glossary.ekler(book_slug)
    yazimlar = {k: v["yazimlar"] for k, v in ekler.items()}
    gecerli, red = [], []
    diziler = (varlik_grafigi.profil(book_slug) or {}).get("diziler", {})
    ek_rutbeler = (varlik_grafigi.profil(book_slug) or {}).get("ek_rutbeler", ())
    for b in veri["baglar"]:
        b = {**b, "ozne": ad_temizle(b.get("ozne") or ""), "nesne": ad_temizle(b.get("nesne") or "")}
        b = duzen_iliskisini_duzelt(b, diziler, ek_rutbeler)
        sebep = kaniti_dogrula(b, kaynak_metin, yazimlar)
        a, n = cozucu.coz(b.get("ozne") or ""), cozucu.coz(b.get("nesne") or "")
        a, n = asil.get(a, a), asil.get(n, n)
        if sebep is None:
            sebep = yapisal_red(b, a, n, kategoriler, sistem)
        (red if sebep else gecerli).append({**b, "sebep": sebep, "ozne_kimlik": a, "nesne_kimlik": n,
                                           "bolum": bolum.get("chapter_no")})
    bilinen = {glossary.fold_term(s) for s in sozluk}
    yeni = sorted({a.strip() for a in veri["yeni_adlar"]
                   if a.strip() and glossary.fold_term(a) not in bilinen
                   and translate.kaynakta_gecen(a, kaynak_metin)})
    return {"gecerli": gecerli, "red": red, "yeni_adlar": yeni, "model": model}


def kitabi_cikar(
    book_slug: str, api_key: str = "", models: tuple[str, ...] | None = None,
    bolum_nolari: set[int] | None = None, sinir: int | None = None, yaz: bool = True,
    ilerleme=None,
) -> dict:
    """Önbellekteki bölümlerden sırayla çıkar. `bolum_nolari` / `sinir` örnek koşu için.

    Bölümler SIRAYLA işlenir: `ilk_bolum` metinde ilk kurulduğu bölüm olmalı
    (spoiler süzgecinin temeli; `bag_ekle` yalnız küçültür, sıra da bunu korur)."""
    cozucu = varlik_grafigi.DugumCozucu(book_slug)
    _t, _k, korpus = cache.kaynak_kapsamasi(book_slug)
    kategoriler = varlik_grafigi.kategori_kimlikleri(book_slug, cozucu, korpus)
    bolumler = sorted(cache.kaynak_bolumleri(book_slug), key=lambda b: b["chapter_no"] or 0)
    if bolum_nolari is not None:
        bolumler = [b for b in bolumler if b["chapter_no"] in bolum_nolari]
    if sinir:
        bolumler = bolumler[:sinir]
    ozet = {"bolum": 0, "gecerli": [], "red": [], "yeni_adlar": {}, "hata": []}
    def _dene(b):
        # Vertex hız sınırı (ölçülen: 2 saatte 49 kez 429) — geri çekilerek dene.
        # Sıra korunur: atlanan bölüm, sonrakinin "bilinen bağlar" bağlamını eksiltir.
        for bekleme in (*YENIDEN_DENEME_SN, None):
            try:
                return bolum_cikar(book_slug, b, api_key, models, cozucu, kategoriler)
            except translate.TranslateError:
                if bekleme is None:
                    raise
                time.sleep(bekleme)

    kuyruk = list(bolumler)
    ikinci_tur: list[dict] = []
    while kuyruk:
        b = kuyruk.pop(0)
        try:
            s = _dene(b)
        except translate.TranslateError as hata:
            # İlk geçişte düşen bölüm EN SONA bir kez daha eklenir (yoğunluk geçmiş olur).
            if b not in ikinci_tur:
                ikinci_tur.append(b)
                kuyruk.append(b)
                if ilerleme:
                    ilerleme(f"  bölüm {b['chapter_no']}: ertelendi ({str(hata)[:80]})")
                continue
            ozet["hata"].append({"bolum": b["chapter_no"], "hata": str(hata)[:200]})
            if ilerleme:
                ilerleme(f"! bölüm {b['chapter_no']}: {str(hata)[:120]}")
            continue
        ozet["bolum"] += 1
        ozet["gecerli"] += s["gecerli"]
        ozet["red"] += s["red"]
        for ad in s["yeni_adlar"]:
            ozet["yeni_adlar"][ad] = ozet["yeni_adlar"].get(ad, 0) + 1
        if yaz:
            conn = varlik_grafigi._connect()
            try:
                for g in s["gecerli"]:
                    varlik_grafigi.bag_ekle(
                        book_slug, g["ozne_kimlik"], g["iliski"], g["nesne_kimlik"], b["chapter_no"],
                        g.get("kanit"), "model", float(g.get("guven") or 0), conn=conn,
                    )
                conn.commit()
            finally:
                conn.close()
        if ilerleme:
            ilerleme(f"  bölüm {b['chapter_no']}: {len(s['gecerli'])} bağ, {len(s['red'])} red ({s['model']})")
    return ozet


# ---------- hedefli soru (boşluk doldurma, `varlik_bosluk`) ----------
CIFT_INSTRUCTION = (
    "Sen bir roman için bilgi grafiğini tamamlayan bir analistsin. Sana varlık "
    "ÇİFTLERİ ve her çiftin birlikte geçtiği cümleler verilecek. Her çift için bu "
    "cümlelerin AÇIKÇA söylediği kalıcı ilişkiyi bul; söylemiyorsa o çift için "
    "hiçbir şey yazma.\n"
    "Kurallar ÇIKARIM kurallarıyla aynıdır: yalnız açıkça söyleneni yaz; varsayım "
    "cümlesi kanıt değildir; kategori yalnız tür/rütbe/sınıf nesnesi olabilir; "
    "bulundugu_yer bir dönem boyunca bulunulan BÖLGE'dir; gercek_adi yalnız Spell'in "
    "True Name'idir; lakap için takma_adi (özne asıl ad).\n"
    "- 'kanit': VERİLEN cümlelerden birini KELİMESİ KELİMESİNE kopyala.\n"
    "- 'iliski' şu listeden biri (özne -> nesne):\n"
    + "".join(f"    {k}: {v['etiket']}\n" for k, v in varlik_grafigi.ILISKILER.items())
    + '- Yanıtı SADECE şu JSON ile ver: {"baglar": [{"ozne": "...", "iliski": "...", '
    '"nesne": "...", "kanit": "...", "guven": 0.9}]}'
)
CIFT_PARTI = 6


def ciftleri_sor(
    book_slug: str, ciftler: list[dict], api_key: str = "", models: tuple[str, ...] | None = None,
    cozucu: varlik_grafigi.DugumCozucu | None = None, kategoriler: set[str] | None = None,
) -> dict:
    """Bir parti çifti modele sor; kanıtı VERİLEN cümlelerle doğrula.

    `ciftler`: `varlik_bosluk.ortak_gecisler` satırları (`a`, `b`, `ornekler`).
    Kanıt verilen bir cümleyle (normalize) eşleşmezse bağ atılır: model kitabın
    dışından bilgi getiremez. `ilk_bolum` eşleşen cümlenin bölümüdür."""
    cozucu = cozucu or varlik_grafigi.DugumCozucu(book_slug)
    if kategoriler is None:
        kategoriler = varlik_grafigi.kategori_kimlikleri(book_slug, cozucu)
    bloklar = []
    for i, c in enumerate(ciftler, 1):
        cumleler = "\n".join(f"  - {s}" for _no, s in c["ornekler"])
        bloklar.append(f"ÇİFT {i}: {c['a']} | {c['b']}\n{cumleler}")
    response, model = translate._generate_with_fallback(
        translate._gemini_fabrikasi(api_key), models or sozluk_dogrulama.ucretsiz_zincir(),
        "\n\n".join(bloklar), system=CIFT_INSTRUCTION, max_tokens=translate.MAX_OUTPUT_TOKENS,
    )
    veri = _ayristir(getattr(response, "text", None))
    havuz = [(no, s, _normal(s)) for c in ciftler for no, s in c["ornekler"]]
    gecerli, red = _kanitli_coz(book_slug, veri["baglar"], havuz, cozucu, kategoriler)
    return {"gecerli": gecerli, "red": red, "model": model}


def _kanitli_coz(
    book_slug: str, ham_baglar: list[dict], havuz: list[tuple], cozucu: varlik_grafigi.DugumCozucu,
    kategoriler: set[str],
) -> tuple[list[dict], list[dict]]:
    """Modelin önerdiği bağları VERİLEN cümle havuzuna karşı doğrula ve düğümlere çöz.

    Hedefli soruların (çift, profil) ORTAK gövdesi: iki yol ayrı kural yazsaydı
    zamanla ayrışırdı (bu projede künye alanları tam böyle ayrışmıştı).
    `havuz`: [(bölüm, cümle, normalize cümle)]. Döner: (geçerli, red)."""
    yazimlar = {k: v["yazimlar"] for k, v in glossary.ekler(book_slug).items()}
    diziler = (varlik_grafigi.profil(book_slug) or {}).get("diziler", {})
    ek_rutbeler = (varlik_grafigi.profil(book_slug) or {}).get("ek_rutbeler", ())
    sistem: dict[tuple[str, str], set[str]] = {}
    asil: dict[str, str] = {}
    for b in varlik_grafigi.baglar(book_slug):
        if b["origin"] == "sistem":
            sistem.setdefault((b["kaynak_kimlik"], b["hedef_kimlik"]), set()).add(b["iliski"])
        if b["iliski"] in ("takma_adi", "gercek_adi") and b["durum"] == "onaylandi":
            asil[b["hedef_kimlik"]] = b["kaynak_kimlik"]
    gecerli, red = [], []
    for b in ham_baglar:
        b = {**b, "ozne": ad_temizle(b.get("ozne") or ""), "nesne": ad_temizle(b.get("nesne") or "")}
        b = duzen_iliskisini_duzelt(b, diziler, ek_rutbeler)
        kanit = _normal(b.get("kanit") or "")
        eslesme = next(((no, s) for no, s, n in havuz if kanit and len(kanit) >= 8 and kanit in n), None)
        if eslesme is None:
            sebep, eslesen = "kanıt verilen cümlelerden değil", None
        else:
            eslesen, cumle = eslesme
            # Aynı deterministik kurallar, eşleşen cümlenin kendisine karşı.
            sebep = kaniti_dogrula({**b, "kanit": kanit}, cumle, yazimlar)
        a, n = cozucu.coz(b.get("ozne") or ""), cozucu.coz(b.get("nesne") or "")
        a, n = asil.get(a, a), asil.get(n, n)
        if sebep is None:
            sebep = yapisal_red(b, a, n, kategoriler, sistem)
        (red if sebep else gecerli).append({**b, "sebep": sebep, "ozne_kimlik": a, "nesne_kimlik": n,
                                           "bolum": eslesen})
    return gecerli, red


# ---------- varlık profili (tek varlık, kitabın tamamı) ----------
# Çift sorusu (boşluk bulucu) ölçülen denemede 30 çiftten 1 bağ verdi: ilişki
# nadiren TEK bir çiftin 6 cümlesinde açıkça söyleniyor. Profil, tek varlığın
# kitap boyunca geçtiği İPUCU taşıyan cümlelerin hepsine bakar (kullanıcı isteği:
# Sunny'nin ekibi "her şeyiyle", yaratıklar "kim öldürdü").
PROFIL_INSTRUCTION = (
    "Sen bir roman için bilgi grafiğini dolduran bir analistsin. Sana TEK bir VARLIK "
    "ve onun kitapta geçtiği cümleler (bölüm numarasıyla, kronolojik) verilecek. Bu "
    "varlığın ÖZNE ya da NESNE olduğu, cümlelerin AÇIKÇA söylediği kalıcı ilişkileri yaz: "
    "rütbesi, sınıfı, Görünüşü, yetenekleri, Anıları, kimin nesi olduğu, hangi gruba bağlı "
    "olduğu, kimin lideri olduğu, nerede bulunduğu, kimi öldürdüğü / kim tarafından "
    "öldürüldüğü.\n"
    "Kurallar ÇIKARIM kurallarıyla aynıdır: yalnız açıkça söyleneni yaz; varsayım/koşul "
    "cümlesi kanıt değildir; diğer uç BİR ADLA anılan varlık olmalı (zamir, 'the man' "
    "gibi genel söz olmaz); kategori yalnız tür/rütbe/sınıf nesnesi olabilir; "
    "bulundugu_yer bir dönem boyunca bulunulan BÖLGE'dir; grubu bir ekibe/bölüğe/loncaya "
    "üyeliktir (klan için klani); lideri GRUP -> lideri olan kişi yönündedir.\n"
    "- 'kanit': VERİLEN cümlelerden birini KELİMESİ KELİMESİNE kopyala; iki ad da o "
    "cümlede geçmeli.\n"
    "- 'iliski' şu listeden biri (özne -> nesne):\n"
    + "".join(f"    {k}: {v['etiket']}\n" for k, v in varlik_grafigi.ILISKILER.items())
    + '- Yanıtı SADECE şu JSON ile ver: {"baglar": [{"ozne": "...", "iliski": "...", '
    '"nesne": "...", "kanit": "...", "guven": 0.9}]}'
)


def varlik_profili_sor(
    book_slug: str, ad: str, cumleler: list[tuple[int, str]], api_key: str = "",
    models: tuple[str, ...] | None = None, cozucu: varlik_grafigi.DugumCozucu | None = None,
    kategoriler: set[str] | None = None,
) -> dict:
    """Tek varlığın profilini sor; kanıt VERİLEN cümlelerden olmalı (`_kanitli_coz`).

    Bilinen bağlar da verilir (tekrar üretmesin, düzeltsin diye değil). Döner:
    {"gecerli", "red", "model"}."""
    cozucu = cozucu or varlik_grafigi.DugumCozucu(book_slug)
    if kategoriler is None:
        kategoriler = varlik_grafigi.kategori_kimlikleri(book_slug, cozucu)
    kimlik = cozucu.coz(ad)
    bilinen = [
        f"  - {b['kaynak']} {b['iliski']} {b['hedef']}"
        for b in (varlik_grafigi.baglar(book_slug, kimlik=kimlik) if kimlik else [])
    ][:BAGLAM_BAG_SINIRI]
    metin = (
        f"VARLIK: {ad}\n"
        + ("BİLİNEN BAĞLAR (tekrar yazma):\n" + "\n".join(bilinen) + "\n" if bilinen else "")
        + "CÜMLELER:\n" + "\n".join(f"  [{no}] {s}" for no, s in cumleler)
    )
    response, model = translate._generate_with_fallback(
        translate._gemini_fabrikasi(api_key), models or sozluk_dogrulama.ucretsiz_zincir(),
        metin, system=PROFIL_INSTRUCTION, max_tokens=translate.MAX_OUTPUT_TOKENS,
    )
    veri = _ayristir(getattr(response, "text", None))
    havuz = [(no, s, _normal(s)) for no, s in cumleler]
    gecerli, red = _kanitli_coz(book_slug, veri["baglar"], havuz, cozucu, kategoriler)
    # Profil TEK varlık içindir: o varlığa değmeyen öneri sorunun dışındadır.
    disarida = [g for g in gecerli if kimlik not in (g["ozne_kimlik"], g["nesne_kimlik"])]
    for g in disarida:
        g["sebep"] = "sorulan varlığa değmiyor"
    # GÖREV: kişinin türü olarak önerilen, sözlükte kaydı olmayan KÜÇÜK harfli cins ad
    # ("technician", "combat medic"). Bağ olamaz (nesne düğüm değil) ama kanıtı
    # doğrulanmış bir özelliktir; durum değeri olarak döner. Ölçülen: altı kişilik
    # denemede doğru üç görev "varlık sözlükte yok" diye kayboluyordu.
    degerler = [
        {"kimlik": kimlik, "anahtar": GOREV_ANAHTARI, "deger": r["nesne"], "bolum": r["bolum"],
         "kanit": r.get("kanit")}
        for r in red
        if r.get("sebep") == "varlık sözlükte yok" and r.get("iliski") in ("turu", "sinifi")
        and r.get("ozne_kimlik") == kimlik and r.get("nesne_kimlik") is None
        and (r.get("nesne") or "")[:1].islower()
    ]
    return {"gecerli": [g for g in gecerli if g not in disarida], "red": red + disarida,
            "degerler": degerler, "model": model}


GOREV_ANAHTARI = "Görev"
