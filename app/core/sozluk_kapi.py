"""Sözlük YAZMA KAPISI ve tutarlılık denetimleri — deterministik, API'siz.

Neden var (2026-10-06, `SOZLUK-SISTEMI-ARASTIRMA.md`): Shadow Slave sözlüğünün
1100 kaydı incelendi ve hataların ortak paydası çıktı: bütün denetimler çeviriden
SONRA ve RAPOR olarak çalışıyordu (`--cakisan`, `--kardes`, `uyum_denetle`).
Sözlüğe YAZMA anında hiçbir kapı yoktu; model ne önerirse `merge_terms` onu
ekliyor ve eklenen prompt'ta KURAL oluyordu. Somut vakalar:

* `Hollow` ve `Stone Hive` ikisi de "Kovan", `Devil` ve `daemon` ikisi de
  "Şeytan" — iki ayrı kavram aynı Türkçe karşılığı aldı (ters benzersizlik).
* `Weaver -> Weaver’s` (177 geçiş), `Kızıl Kule'nin Dehşet'i` — biçim bozuk.
* `Seven -> Yediler`, `Lost -> Kayıplar` — tekil, sıradan bir sözcük çoğul bir
  grup adına bağlandı ve 143 / 320 bölümün prompt'una "seven"/"lost" geçtiği
  her yerde girdi.
* `Temple of Chalice` / `Temple of the Chalice`, `Locomotive Chiffonier` /
  `Chiffonnier` — aynı adın yazımları ayrı satır oldu ve karşılıkları ayrıştı.

Profesyonel terim yönetiminde (TBX/ISO 30042, Xbench "inconsistency in source")
bu denetimler GİRİŞTE yapılır. Burada da öyle: `glossary.merge_terms` her yeni
otomatik kaydı `kapi_denetle`den geçirir; takılan kayıt sözlüğe "tutuldu"
olarak yazılır — prompt'a GİRMEZ, inceleme listesinde sebebiyle bekler.

Kalibrasyon ilkesi (projenin `ISLEV_SOZCUKLERI` dersi): her şeye uyaran kapı
görmezden gelinir. Her kural gerçek sözlükte ölçülmüş bir hata sınıfına karşılık
gelir ve meşru kayıtları ölçülmüş istisnalarla dışarıda bırakır.

Hiçbir fonksiyon sözlüğe YAZMAZ; yazma `glossary` modülündedir.
"""
from __future__ import annotations

import json
import sqlite3
import re
from collections import Counter, defaultdict
from functools import lru_cache

from . import db
from . import glossary

# ---------- neden türleri (inceleme ekranı etiketleri bunlarla eşleşir) ----------
KARSILIK_CAKISMASI = "karsilik_cakismasi"
YAKIN_YAZIM = "yakin_yazim"
SAYI_UYUMSUZLUGU = "sayi_uyumsuzlugu"
BICIM = "bicim"
YASAK_KARSILIK = "yasak_karsilik"
POLITIKA = "politika"
KALIP = "kalip_tutarsizligi"
IHLAL_SUPHESI = "ihlal_suphesi"
DOGRULAMA = "dogrulama"

# ---------- normalizasyon ----------
_BASTAKI_BELIRTEC = re.compile(r"^(?:the|a|an)\s+", re.IGNORECASE)
_OF_THE = re.compile(r"\bof\s+the\b", re.IGNORECASE)


@lru_cache(maxsize=16384)
def varyant_anahtari(kaynak: str) -> str:
    """Aynı adın ZARARSIZ yazım farklarını tek anahtara indirir.

    `fold_term`'ün ötesinde iki fark daha katlanır, ikisi de gerçek sözlükte
    ayrı satır açmıştı ve ikisi de anlamı değiştirmez:
      * baştaki belirteç: `The Lord of the Dead` ~ `Lord of the Dead`,
        `The One in the North` ~ `One in the North`
      * `of the` ~ `of`: `Temple of the Chalice` ~ `Temple of Chalice`,
        `Seed of the Nightmare` ~ `Seed of Nightmare`

    Tek harf farkı BİLEREK katlanmaz: `Orc Empire` / `Ore Empire` vakası bunun
    gerçek bir anlam farkı olabileceğini gösterdi (bkz. `glossary.yakin_terimler`).
    """
    k = _BASTAKI_BELIRTEC.sub("", (kaynak or "").strip())
    k = _OF_THE.sub("of", k)
    k = _ICTEKI_IYELIK.sub("", k)  # `Puppeteer's Shroud` ~ `Puppeteer Shroud`
    return glossary.fold_term(k)


_ICTEKI_IYELIK = re.compile(r"['’]s\b", re.IGNORECASE)
_ICERIK_DISI = frozenset({"the", "a", "an", "of"})


def _sozcukler(kaynak: str) -> list[str]:
    metin = _ICTEKI_IYELIK.sub("", glossary.normalize_source(kaynak or ""))
    return [s for s in re.split(r"[\s\-_]+", metin.casefold()) if s and s not in _ICERIK_DISI]


def _tekil(sozcuk: str) -> str:
    if len(sozcuk) > 3 and sozcuk.endswith("s") and not sozcuk.endswith(_COGUL_DEGIL_SONLAR):
        return sozcuk[:-1]
    return sozcuk


@lru_cache(maxsize=16384)
def icerik_anahtari(kaynak: str) -> tuple[str, ...]:
    """Sözcük SIRASINDAN bağımsız içerik: `Song clan` ~ `clan Song`, `Sea of Soul` ~
    `Soul Sea`, `Kingdom of Hope` ~ `Hope's Kingdom`. Ölçülen sözlükte bu çiftlerin
    hepsi aynı karşılığı taşıyordu — aynı şeyin iki dizilişi."""
    return tuple(sorted(_sozcukler(kaynak)))


@lru_cache(maxsize=16384)
def tekil_anahtari(kaynak: str) -> tuple[str, ...]:
    """İçerik anahtarı, her sözcük tekile indirilmiş: `Seeds of Nightmares` ~
    `Nightmare Seeds`, `Shadows Sense` ~ `Shadow Sense`. Tekil/çoğul farkı ANLAMLI
    olabilir (`Seed` / `Seeds`); çağıran karşılıkların sayısına da bakar."""
    return tuple(sorted(_tekil(s) for s in _sozcukler(kaynak)))


# ---------- sayı (tekil/çoğul) ----------
# Çoğul gibi biten ama çoğul OLMAYAN İngilizce sonlar. `Eyeless`, `Sunless`,
# `Doubtless` (-ss), `Tenacious`/`Sonorous` (-ous), `Erebus` (-us), `Nephis` (-is),
# `Northern Quadrant Corps` (corps tekildir).
_COGUL_DEGIL_SONLAR = ("ss", "us", "is", "ous", "ics", "sis", "news", "corps", "series", "species")
# Ad öbeğinde başı sağdan ayıran edatlar: `Raised by Wolves` başı `Raised`,
# `One in the North` başı `One`.
_EDAT = r"of|by|in|from|with|for|to|on|at|under|beyond"
# Türkçe çoğul: son sözcük -lar/-ler ile biter ya da arkasından iyelik/belirtme
# eki gelir (`Mahlukları`, `Bakireleri`, `Tohumları`).
_TR_COGUL = re.compile(r"l[ae]r(?:[ıiuü]|[ıiuü]n|n[ıiuü]n|[ıi]n[ıi])?$", re.IGNORECASE)
_SOZCUK = re.compile(r"[^\s\-–—/]+")


def _bas_sozcuk(kaynak: str) -> str:
    """İngilizce ad öbeğinin BAŞ sözcüğü: `X of Y` yapısında X, değilse son sözcük.

    `Chains of Longing` çoğuldur (baş: Chains), `Lake of Bones` tekildir (baş:
    Lake). Son sözcüğe bakmak ikisini de ters sınıflandırırdı.
    """
    metin = glossary.normalize_source(kaynak)
    parca = re.split(rf"\s+(?:{_EDAT})\s+", metin, maxsplit=1, flags=re.IGNORECASE)[0]
    sozcukler = _SOZCUK.findall(parca)
    return sozcukler[-1] if sozcukler else ""


@lru_cache(maxsize=16384)
def kaynak_cogul_mu(kaynak: str) -> bool:
    bas = _bas_sozcuk(kaynak).casefold().strip("'’")
    if len(bas) <= 3 or not bas.endswith("s"):
        return False
    return not bas.endswith(_COGUL_DEGIL_SONLAR)


@lru_cache(maxsize=16384)
def hedef_cogul_mu(hedef: str) -> bool:
    sozcukler = _SOZCUK.findall((hedef or "").strip())
    if not sozcukler:
        return False
    son = re.sub(r"['’].*$", "", sozcukler[-1])  # `PTV'ler` -> `PTV` değil: ek sonra
    if son != sozcukler[-1]:
        # Kesmeli çoğul (`PTV'ler`, `gargoyle'lar`): ek kesmeden sonradır.
        return bool(re.search(r"['’]l[ae]r", sozcukler[-1], re.IGNORECASE))
    return bool(_TR_COGUL.search(son))


def ingilizce_korunan(kaynak: str, hedef: str) -> bool:
    return glossary.fold_term(kaynak) == glossary.fold_term(hedef or "")


def sayi_uyumsuzlugu(kaynak: str, hedef: str) -> str | None:
    """Tekil kaynak çoğul karşılık (ya da tersi) — açıklama metni ya da None.

    Ölçülen vakalar: `Seven -> Yediler`, `Lost -> Kayıplar`, `Unknown ->
    Bilinmeyenler` (sıradan sözcük bir grup adına bağlanmış; `seven days` de
    "Yediler"e zorlanır), `Chained Island -> Zincirli Adalar`, `abominations ->
    ucube`. İngilizce korunan kayıt denetim dışıdır.
    """
    if not hedef or ingilizce_korunan(kaynak, hedef):
        return None
    k_cogul, h_cogul = kaynak_cogul_mu(kaynak), hedef_cogul_mu(hedef)
    if not k_cogul and h_cogul:
        return ("Tekil kaynak çoğul karşılığa bağlanmış. Sıradan bir sözcükse "
                "(seven, lost) metindeki her geçişi grup adına çevirir; grup adıysa "
                "koşul ekle (ör. 'yalnız grup adı olarak: the Seven').")
    if k_cogul and not h_cogul:
        return "Çoğul kaynak tekil karşılığa bağlanmış (çoğul eki eksik olabilir)."
    return None


# ---------- biçim ----------
# Karşılığın SONUNDA kesmeyle ayrılmış hâl/iyelik eki: kayıt yalın hâlde değil.
# Ölçülen: `Kızıl Kule'nin Dehşet'i`, `Valor'un Anvil'i`. Kesmeli ÇOĞUL eki
# (`PTV'ler`) meşrudur ve bilerek listede yok.
_SONDA_HAL_EKI = re.compile(
    r"['’](?:[ıiuü]|[sy][ıiuü]|n[ıiuü]n|[ıiuü]n|[dt][ae]n?|[ae]|y[ae]|[dt][ae]ki|l[ae]r[ıi])$",
    re.IGNORECASE,
)
# Türkçe karşılıkta İngilizce İŞLEV sözcüğü: çeviri değil, kaynak kopyalanmış.
# Liste DAR: Türkçede de yazımı olan sözcükler (not, has, of) yok.
_INGILIZCE_ISLEV = frozenset(
    "the and of what wait is are was were my your his her their with from".split()
)
_INGILIZCE_IYELIK = re.compile(r"['’]s\b", re.IGNORECASE)


def bicim_sorunlari(kaynak: str, hedef: str) -> list[str]:
    """Karşılığın biçim sorunları (açıklamalar). İngilizce korunan kayıt dışarıda."""
    if not hedef or ingilizce_korunan(kaynak, hedef):
        return []
    out = []
    if _INGILIZCE_IYELIK.search(hedef):
        out.append("Karşılıkta İngilizce iyelik eki ('s) var. İngilizce kalacaksa "
                   "karşılık kaynağın AYNISI olmalı; Türkçeyse Türkçe ek almalı "
                   "(Weaver'ın Maskesi).")
    if _SONDA_HAL_EKI.search(hedef.strip()):
        out.append("Karşılık yalın hâlde değil (sonda kesmeli ek var). Sözlük "
                   "karşılığı yalın yazılır, eki cümle getirir.")
    sozcukler = {s.casefold().strip("?!.,;:") for s in hedef.split()}
    islev = sorted(sozcukler & _INGILIZCE_ISLEV)
    if islev:
        out.append(f"Türkçe karşılıkta İngilizce işlev sözcüğü var ({', '.join(islev)}): "
                   "çeviri değil, kaynak kopyalanmış olabilir.")
    return out


# ---------- mevcut kayıtlarla karşılaştırma ----------
# Tek harf yakınlığı yalnız bu uzunluktan itibaren anlamlı. Ölçüm (shadow-slave,
# 1100 kayıt): kısa adlarda uyarıların TAMAMI meşru ayrı adlardı (Abel/Obel,
# Dale/Gale/Vale, Fool/Tool, Host/Lost, Knight/Night); 7+ harfte kalanlar gerçek
# yazım varyantı (Chiffonier/Chiffonnier, Autumn Lead/Leaf) ya da incelenmeye değer.
YAKIN_MIN_UZUNLUK = 7


def _tek_harf_yakin(a: str, b: str) -> bool:
    """Katlanmış iki anahtar arasında tek harf farkı (tekil/çoğul ve rakam hariç)."""
    if min(len(a), len(b)) < YAKIN_MIN_UZUNLUK:
        return False
    yer = glossary._fark_yeri(a, b)
    if not yer or glossary._cogul_cifti(a, b):
        return False
    i = yer[0]
    return not (a[i:i + 1].isdigit() or b[i:i + 1].isdigit())


ZARARSIZ = "zararsiz"        # the / of the / iyelik farkı — aynı ad
DIZILIS = "dizilis"          # aynı sözcükler, farklı sıra — aynı ad
SAYI_CIFTI = "sayi_cifti"    # tekil/çoğul çifti, karşılıklar da öyle — MEŞRU ayrı kayıt
TEKIL_VARYANT = "tekil_varyant"  # tekile indirince aynı, karşılık sayısı aynı — aynı ad
TEK_HARF = "tek_harf"        # tek harf farkı — yazım hatası olabilir


def varyant_iliskisi(a_kaynak: str, a_hedef: str, b_kaynak: str, b_hedef: str) -> str | None:
    """İki kaydın kaynakları arasındaki yazım ilişkisi (yukarıdaki sabitler) ya da None."""
    if glossary.fold_term(a_kaynak) == glossary.fold_term(b_kaynak):
        return None  # aynı kayıt
    if varyant_anahtari(a_kaynak) == varyant_anahtari(b_kaynak):
        return ZARARSIZ
    if icerik_anahtari(a_kaynak) == icerik_anahtari(b_kaynak):
        return DIZILIS
    if tekil_anahtari(a_kaynak) == tekil_anahtari(b_kaynak):
        if hedef_cogul_mu(a_hedef) != hedef_cogul_mu(b_hedef) or (
            kaynak_cogul_mu(a_kaynak) != kaynak_cogul_mu(b_kaynak)
            and ingilizce_korunan(a_kaynak, a_hedef) and ingilizce_korunan(b_kaynak, b_hedef)
        ):
            return SAYI_CIFTI
        return TEKIL_VARYANT
    if _tek_harf_yakin(glossary.fold_term(a_kaynak), glossary.fold_term(b_kaynak)):
        return TEK_HARF
    return None


def _cogul_cifti_mi(a_kaynak: str, b_kaynak: str) -> bool:
    a, b = varyant_anahtari(a_kaynak), varyant_anahtari(b_kaynak)
    kisa, uzun = (a, b) if len(a) <= len(b) else (b, a)
    return uzun in (kisa + "s", kisa + "es")


def kapi_denetle(
    kaynak: str,
    hedef: str,
    mevcut: list[dict],
    yasaklar: dict[str, list[str]] | None = None,
    politikalar: dict[str, str] | None = None,
    tur: str | None = None,
    geriye_donuk: bool = False,
) -> dict:
    """Yeni (ya da denetlenen) bir kaydı kapıdan geçir.

    `geriye_donuk`: sözlükte ZATEN duran bir kaydı denetle. Varyant bulununca
    erken dönmez; "birleştir" nedeni yazıp öteki denetimlere devam eder.

    `mevcut`: kitabın ÖTEKİ kayıtları (`source`, `target`, ... satırları).
    `yasaklar`: {kaynak: [yasak karşılıklar]} — herhangi bir kavramın yasakladığı
    karşılık bu kayda da verilemez.

    Döner: ``{"yazim_of": kaynak | None, "nedenler": [...]}``
      * ``yazim_of``: kayıt mevcut bir kaydın yazım varyantı — ayrı satır açılmaz,
        o kayda alternatif yazım olarak bağlanır (neden listesi boştur). Zararsız
        fark (`the`, `of the`, iyelik) her zaman bağlanır; sözcük sırası ya da
        tekil/çoğul yazımı farkı YALNIZ karşılıklar da aynıysa bağlanır.
      * ``nedenler``: takılma sebepleri. Boşsa kayıt kapıdan geçer.
    """
    nedenler: list[dict] = []
    korunan = ingilizce_korunan(kaynak, hedef)
    hedef_anahtari = glossary.fold_term(hedef)

    iliskiler: dict[str, str] = {}
    birlesecek: list[str] = []
    for r in mevcut:
        iliski = varyant_iliskisi(kaynak, hedef, r["source"], r.get("target") or r["source"])
        if not iliski:
            continue
        iliskiler[r["source"]] = iliski
        ayni_karsilik = glossary.fold_term(r.get("target") or "") == hedef_anahtari
        if iliski == ZARARSIZ and not ayni_karsilik and geriye_donuk:
            continue  # aşağıda "farklı karşılık" olarak raporlanır
        if iliski == ZARARSIZ or (iliski in (DIZILIS, TEKIL_VARYANT) and ayni_karsilik):
            if not geriye_donuk:
                return {"yazim_of": r["source"], "nedenler": []}
            birlesecek.append(r["source"])
    if birlesecek:
        nedenler.append({
            "tur": YAKIN_YAZIM,
            "aciklama": (f"Aynı adın yazımı ayrı kayıt olarak duruyor (aynı karşılık): "
                         f"{', '.join(birlesecek)}. Tek kayıtta birleştir (alternatif yazım)."),
            "ilgili": birlesecek,
        })
    varyant_farkli = [
        k for k, i in iliskiler.items()
        if i in (DIZILIS, TEKIL_VARYANT, ZARARSIZ) and k not in birlesecek
    ]
    if varyant_farkli:
        nedenler.append({
            "tur": YAKIN_YAZIM,
            "aciklama": (f"Aynı adın başka bir yazımı FARKLI karşılıkla kayıtlı: "
                         + ", ".join(f"{k} → {next(r['target'] for r in mevcut if r['source'] == k)}"
                                     for k in varyant_farkli)
                         + ". Birini seç, ötekini alternatif yazım yap."),
            "ilgili": varyant_farkli,
        })

    for metin in bicim_sorunlari(kaynak, hedef):
        nedenler.append({"tur": BICIM, "aciklama": metin, "ilgili": []})
    sayi = sayi_uyumsuzlugu(kaynak, hedef)
    if sayi:
        nedenler.append({"tur": SAYI_UYUMSUZLUGU, "aciklama": sayi, "ilgili": []})

    if not korunan:
        # Yazım ilişkisi olan kayıtlar (varyant, tekil/çoğul çifti, tek harf)
        # çakışma sayılmaz: onları yukarıdaki/aşağıdaki YAKIN_YAZIM nedeni anlatır.
        cakisan = [
            r["source"] for r in mevcut
            if r.get("target") and glossary.fold_term(r["target"]) == hedef_anahtari
            and not ingilizce_korunan(r["source"], r["target"])
            and r["source"] not in iliskiler
            and not _cogul_cifti_mi(r["source"], kaynak)
        ]
        if cakisan:
            nedenler.append({
                "tur": KARSILIK_CAKISMASI,
                "aciklama": (f"Aynı karşılık '{hedef}' zaten başka kaynakta kullanılıyor: "
                             f"{', '.join(cakisan)}. Aynı şeyse alternatif yazım yap; "
                             "değilse karşılıklar ayrışmalı (okur ikisini ayırt edemez)."),
                "ilgili": cakisan,
            })
        for yasak_sahibi, liste in (yasaklar or {}).items():
            if any(glossary.fold_term(y) == hedef_anahtari for y in liste):
                nedenler.append({
                    "tur": YASAK_KARSILIK,
                    "aciklama": f"'{hedef}' karşılığı '{yasak_sahibi}' kaydında YASAK olarak işaretli.",
                    "ilgili": [yasak_sahibi],
                })

    yakin = [k for k, i in iliskiler.items() if i == TEK_HARF]
    if yakin:
        nedenler.append({
            "tur": YAKIN_YAZIM,
            "aciklama": (f"'{', '.join(yakin)}' ile tek harf farklı — biri yazım hatası "
                         "olabilir. Aynı adsa alternatif yazım olarak bağla."),
            "ilgili": yakin,
        })

    politika = politika_ihlali(tur, kaynak, hedef, politikalar)
    if politika:
        nedenler.append({"tur": POLITIKA, "aciklama": politika, "ilgili": []})
    return {"yazim_of": None, "nedenler": nedenler}


# ---------- kategori politikası ----------
POLITIKA_DEGERLERI = ("ingilizce", "turkce")


def politika_ihlali(
    tur: str | None, kaynak: str, hedef: str, politikalar: dict[str, str] | None
) -> str | None:
    """Kaydın türü için kitapta bir politika varsa ve kayıt ona uymuyorsa açıklama.

    Ölçülen tutarsızlık: Gerçek İsimlerin bir kısmı Türkçe (`Changing Star`,
    `Song of the Fallen`), bir kısmı İngilizce (`Sunless`, `Nightingale`); her kayıt
    öbüründen habersiz karar verilmişti. Tür düzeyinde tek kural bunu önler.
    """
    if not tur or not politikalar or tur not in politikalar or not hedef:
        return None
    kural = politikalar[tur]
    korunan = ingilizce_korunan(kaynak, hedef)
    if kural == "ingilizce" and not korunan:
        return f"Kitap politikası: '{tur}' türü İngilizce kalır; bu kayıt Türkçeleştirilmiş."
    if kural == "turkce" and korunan:
        return f"Kitap politikası: '{tur}' türü Türkçeye çevrilir; bu kayıt İngilizce kalmış."
    return None


# ---------- kalıp (aile) tutarlılığı ----------
# Aynı sözcüğün iki biçimi arasında yalnız bu ekler varsa bu bir YAZIM tercihi
# ayrışmasıdır, anlam farkı değil (`Uykuda` / `Uykudaki`).
_SIFAT_EKLERI = ("ki", "daki", "deki", "taki", "teki")
_YUMUSAMA = {("k", "ğ"), ("ğ", "k"), ("t", "d"), ("d", "t"), ("p", "b"), ("b", "p"), ("ç", "c"), ("c", "ç")}


def _yumusama_cifti(a: str, b: str) -> bool:
    """Yalnız ünsüz yumuşamasıyla ayrışan iki biçim (`mahluku` / `mahluğu`)."""
    if len(a) != len(b) or a == b:
        return False
    farklar = [(x, y) for x, y in zip(a, b) if x != y]
    return len(farklar) == 1 and farklar[0] in _YUMUSAMA


def kalip_tutarsizliklari(satirlar: list[dict]) -> dict[str, dict]:
    """Aynı ailedeki terimlerin Türkçe yazımı ayrışıyor: {kaynak: neden}.

    İki ölçüt, ikisi de gerçek sözlükte ölçülmüş vakadan:
      1. AYNI İngilizce ilk sözcük, yalnız sıfat ekiyle ayrışan Türkçe ilk sözcük:
         `Dormant -> Uykuda`, `Dormant Memory -> Uykuda Anı` ama
         `Dormant Ability -> Uykudaki Yetenek`. Azınlık biçim işaretlenir.
      2. Aynı Türkçe sözcüğün yalnız ünsüz yumuşamasıyla ayrışan iki yazımı:
         `Ayna Mahluğu` / `Ruh Mahluku`. Azınlık biçim işaretlenir.

    Anlam farkı olabilecek ayrışmalar BİLEREK dışarıda: `Great -> Ulu` ile
    `Great Clan -> Büyük Klan` ortak kök taşımaz (iki anlam), `Gölge Rütbesi` ile
    `Yüce Rütbe` ad tamlaması / sıfat tamlaması farkıdır — ikisi de doğru Türkçe.
    """
    turkce = [r for r in satirlar if r.get("target") and not ingilizce_korunan(r["source"], r["target"])]
    out: dict[str, dict] = {}

    gruplar: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for r in turkce:
        ks, hs = r["source"].split(), r["target"].split()
        if ks and hs:
            gruplar[ks[0].casefold()].append((r["source"], hs[0]))
    for _ilk, uyeler in gruplar.items():
        if len(uyeler) < 3:
            continue
        sayac = Counter(h.casefold() for _k, h in uyeler)
        if len(sayac) < 2:
            continue
        cogunluk = sayac.most_common(1)[0][0]
        for kaynak, h in uyeler:
            bicim = h.casefold()
            if bicim == cogunluk:
                continue
            kisa, uzun = sorted((bicim, cogunluk), key=len)
            if uzun.startswith(kisa) and uzun[len(kisa):] in _SIFAT_EKLERI:
                out.setdefault(kaynak, {
                    "tur": KALIP,
                    "aciklama": (f"Aynı ailenin {sayac[cogunluk]} kaydı '{cogunluk}' yazıyor, "
                                 f"bu kayıt '{bicim}'. Aileyi tek biçime çek."),
                    "ilgili": [k for k, x in uyeler if x.casefold() == cogunluk][:5],
                })

    biçimler: dict[str, list[str]] = defaultdict(list)
    for r in turkce:
        for s in r["target"].split():
            biçimler[s.casefold().strip("'’")].append(r["source"])
    # Her biçim çiftini denemek (n²) sunucuda 3 sn sürüyordu. Yumuşama çifti tek bir
    # yumuşayan harfte ayrışır: o harf maskelenince iki biçim aynı anahtara düşer.
    # Yalnız aynı anahtarı paylaşanlar, eski taramanın sırasıyla denenir.
    harfler = {x for x, _ in _YUMUSAMA}
    sira = {w: i for i, w in enumerate(biçimler)}
    maskeler: dict[str, list[str]] = defaultdict(list)
    for w in biçimler:
        for i, ch in enumerate(w):
            if ch in harfler:
                maskeler[w[:i] + "*" + w[i + 1:]].append(w)
    komsular: dict[str, set[str]] = defaultdict(set)
    for kova in maskeler.values():
        for w in kova:
            komsular[w].update(kova)
    for a, kaynaklar_a in biçimler.items():
        for b in sorted(komsular.get(a, ()), key=sira.__getitem__):
            kaynaklar_b = biçimler[b]
            if a >= b or not _yumusama_cifti(a, b):
                continue
            azinlik, cogunluk = (a, b) if len(kaynaklar_a) < len(kaynaklar_b) else (b, a)
            if len(kaynaklar_a) == len(kaynaklar_b):
                azinlik = None  # eşitlikte ikisi de işaretlenir
            for bicim, sahipler in ((a, kaynaklar_a), (b, kaynaklar_b)):
                if azinlik is not None and bicim != azinlik:
                    continue
                for kaynak in sahipler:
                    out.setdefault(kaynak, {
                        "tur": KALIP,
                        "aciklama": (f"'{a}' ve '{b}' aynı sözcüğün iki yazımı "
                                     f"({len(kaynaklar_a)} / {len(kaynaklar_b)} kayıt). Tek yazıma çek."),
                        "ilgili": [x for x in (kaynaklar_b if bicim == a else kaynaklar_a)][:5],
                    })
    return out


# ---------- ihlal şüphesi (denetim geri beslemesi) ----------
# Bu modellerin "ihlali" kanıt sayılmaz: zincirden kalite gerekçesiyle çıkarıldılar
# (lite 4 bölümde 30 ihlal; OpenRouter/Mistral önekli eski kayıtlar).
def _guvenilir_model(model: str | None) -> bool:
    m = model or ""
    return bool(m) and "lite" not in m and ":" not in m


SUPHE_MIN_BOLUM = 2


def ihlal_supheleri(
    book_slug: str, kaynaklar: set[str] | None = None, tam: bool = False
) -> dict[str, dict]:
    """İyi modellerin ısrarla UYMADIĞI kayıtlar: {kaynak: neden}.

    `uyum_denetle` bunu bir yan not olarak söylüyordu: iyi bir modelin bir terimi
    ısrarla "ihlal etmesi" genellikle kaydın yanlış olduğunu gösterir (gerçek
    bulgu: elle eklenmiş `Rock -> Taş`, oysa Rock bir karakter). Ölçülen güncel
    vakalar: `Fool -> Aptal` (3.6-flash, 5 bölüm), `Changing Star -> Değişen
    Yıldız` (2.5-flash, 2 bölüm). Eşik: en az `SUPHE_MIN_BOLUM` ayrı bölüm.

    Saklı bayrak (`chapters.glossary_leaks`) yalnız ADAY seçer, kanıt değildir:
    bayrağı eski ölçütle yazılmış bölümler var (sunucu kopyası 2026-10-06:
    `Saints` 44 bölümde "ihlal" — tekili kayıtlı çoğul düzeltmesinden ÖNCE
    yazılmış sahte bayraklar). Bayraklı bölümler BUGÜNKÜ ölçütle yeniden ölçülür
    (`uyum_denetle` ile aynı: o bölümdeki sözlük + bugünkü koşullar); yalnız
    bugün de ihlal sayılanlar kalır. Bayraklı bölüm az olduğu için ucuzdur.

    `tam=True`: bayrağa bakmadan kaynağı ve çevirisi olan HER bölüm ölçülür
    (bakım aracı). Bayrak yalnız ölçüm sütunu eklendikten sonra yazıldı; eski
    bölümlerde NULL olduğu için `Fool` (5 bölüm) bayrak seçimiyle görünmüyordu.
    Sözlük ekranı hızlı kipi kullanır.
    """
    from . import translate  # döngüsel içe aktarmayı önle (translate -> glossary)

    conn = db.connect()
    try:
        satirlar = conn.execute(
            "SELECT chapter_no, model, source_text, translation FROM chapters "
            "WHERE book_slug = ? AND source_text IS NOT NULL AND translation IS NOT NULL"
            + ("" if tam else " AND glossary_leaks IS NOT NULL AND glossary_leaks NOT IN ('', '{}')"),
            (book_slug,),
        ).fetchall()
    except sqlite3.OperationalError:  # tablo yoksa (boş DB) şüphe de yok
        return {}
    finally:
        conn.close()
    if not satirlar:
        return {}
    kosullar = glossary.ceviri_kosullari(book_slug)
    bolumler: dict[str, set] = defaultdict(set)
    modeller: dict[str, Counter] = defaultdict(Counter)
    for no, model, kaynak_metin, ceviri in satirlar:
        if not _guvenilir_model(model):
            continue
        ihlal = translate.sozluk_ihlalleri(
            glossary.bolumdeki_sozluk(book_slug, no), kaynak_metin, ceviri, kosullar
        )
        for kaynak in ihlal:
            bolumler[kaynak].add(no)
            modeller[kaynak][model] += 1
    out: dict[str, dict] = {}
    for kaynak, nolar in bolumler.items():
        if len(nolar) < SUPHE_MIN_BOLUM or (kaynaklar is not None and kaynak not in kaynaklar):
            continue
        out[kaynak] = {
            "tur": IHLAL_SUPHESI,
            "aciklama": (f"İyi modeller bu karşılığa {len(nolar)} bölümde UYMADI "
                         f"({', '.join(f'{m} {n}' for m, n in modeller[kaynak].most_common(3))}). "
                         "Israrlı ihlal çoğu zaman kaydın yanlış olduğunu gösterir."),
            "ilgili": [],
            "bolumler": sorted(n for n in nolar if n is not None)[:10],
        }
    return out


# ---------- sıradan sözcük sıklığı (bilgi) ----------
def genel_sozcuk_sikligi(kaynak: str, korpus: str) -> tuple[int, int] | None:
    """Tek sözcüklü kaynağın korpusta (küçük harfli, cümle içi büyük harfli) sayısı.

    Sıradan bir İngilizce sözcük (`seven`, `lost`) küçük harfle sık geçer; bir ad
    çoğunlukla büyük harfle. Kitabın KENDİ kaynak metninden ölçülür — sabit bir
    sözcük listesi kitabın diline (`Hollow` bir yer adı) uymazdı.
    """
    if " " in kaynak.strip() or not korpus:
        return None
    desen = re.compile(r"\b" + re.escape(kaynak.strip()) + r"\b", re.IGNORECASE)
    kucuk = buyuk = 0
    for m in desen.finditer(korpus):
        if m.group(0).islower():
            kucuk += 1
        else:
            onceki = korpus[max(0, m.start() - 3):m.start()].rstrip()
            if onceki and onceki[-1] not in ".!?\"“”'’\n:":
                buyuk += 1
    return kucuk, buyuk


def genel_sozcuk_mu(kaynak: str, korpus: str) -> bool:
    sayi = genel_sozcuk_sikligi(kaynak, korpus)
    return bool(sayi) and sayi[0] >= 5 and sayi[0] >= sayi[1]


# ---------- tüm sözlüğü denetle (geriye dönük) ----------
def sozlugu_denetle(
    satirlar: list[dict],
    yasaklar: dict[str, list[str]] | None = None,
    politikalar: dict[str, str] | None = None,
    korpus: str = "",
) -> dict[str, list[dict]]:
    """Her kaydı ÖTEKİ kayıtlara karşı kapıdan geçir + aile denetimi: {kaynak: nedenler}.

    Geriye dönük kipte (`geriye_donuk=True`) varyantlar erken dönüş yerine
    "birleştir" nedeni olarak raporlanır. Sayı uyumsuzluğu taşıyan tek sözcüklü
    kayıtlara kitabın kendi kaynağındaki sıklık eklenir: sıradan sözcük olduğu
    ancak böyle görülür (`seven` küçük harfle 247 kez).
    """
    out: dict[str, list[dict]] = defaultdict(list)
    for i, r in enumerate(satirlar):
        digerleri = satirlar[:i] + satirlar[i + 1:]
        sonuc = kapi_denetle(
            r["source"], r.get("target") or "", digerleri, yasaklar, politikalar,
            r.get("tur"), geriye_donuk=True,
        )
        for n in sonuc["nedenler"]:
            if n["tur"] == SAYI_UYUMSUZLUGU and korpus and genel_sozcuk_mu(r["source"], korpus):
                kucuk, buyuk = genel_sozcuk_sikligi(r["source"], korpus)
                n = {**n, "aciklama": n["aciklama"]
                     + f" Kitapta küçük harfle {kucuk}, cümle içinde büyük harfle {buyuk} kez geçiyor."}
            out[r["source"]].append(n)
    for kaynak, n in kalip_tutarsizliklari(satirlar).items():
        out[kaynak].append(n)
    return dict(out)
