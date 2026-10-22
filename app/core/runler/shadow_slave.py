"""Shadow Slave rün (Spell mesajı) biçimi — `runler` biçim modülü (plan Faz 2).

`varlik_grafigi` içinden DEĞİŞMEDEN taşındı: rün satırları, blok başlıkları (Memory /
Shadow / Echo), durum bloğu (`Name: X`), sayaçlar, öldürme/Gerçek Ad/Yankı/Gölge mesajları ve
evrim işaretleri. Saftır (veritabanı yok); `varlik_grafigi` düzenleyicisi profilin
`run_bicimi` alanıyla bu modülü seçer. Arayüz: `sistem_baglarini_bul`, `evrimleri_esle`.
"""
from __future__ import annotations

import json
import re
from collections import deque

from . import DEGER, ENVANTER, payda

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
               "Enchantments": "efsunu", "Enchantment": "efsunu", "Memory Enchantment": "efsunu"},
    # Gölge/yankı nitelikleri (2026-10-15, defter): "Shadow Attributes: [Battle Master], [Stalwart]".
    # Yetenekler (`Shadow Abilities`, `Echo Abilities`) 995 bölümlük taramada HİÇ okunmuyordu (8 satır).
    "Shadow": {"Shadow Rank": "rutbesi", "Shadow Class": "sinifi", "Shadow Attributes": "niteligi",
               "Shadow Abilities": "yetenegi"},
    "Echo": {"Echo Type": "sinifi", "Echo Class": "sinifi", "Echo Core": "rutbesi", "Echo Rank": "rutbesi",
             "Echo Attributes": "niteligi", "Echo Abilities": "yetenegi"},
}
_BLOK_SAHIPLIK = {"Memory": "anisi", "Shadow": "golgesi", "Echo": "yanki"}
# Sonraki bölümlerde Anı rünlerinin ARASINA anlatım giriyor ("He continued to study
# the runes."); düz paragraf bloğu kapattığı için `Memory Description` ve efsun
# satırları sahipsiz kalıyordu. YALNIZ Anıya özgü anahtarlar kapanmış bloğu bu kadar
# paragraf içinde yeniden açar — başka bir bloğun satırı sanılamazlar. Genel kural
# (düz paragraf bloğu kapatır) yerinde: ölçülen yanlış atıf başka anahtarlardaydı.
_ANI_ANAHTARLARI = frozenset(
    ("Memory Rank", "Memory Tier", "Memory Type", "Memory Description", "Memory Enchantments",
     "Enchantments", "Enchantment", "Enchantment Description", "Memory Enchantment",
     "Death Charge", "Vanquished Foes")
)
ANI_ANLATIM_PENCERESI = 12
# Gölge/yankı anahtarları ("Shadow Abilities") başka bir şeyin rünü sanılamaz; 655. bölümde
# Nightmare'ın rünleri arasında 13 paragraf anlatım var.
ESYA_ANLATIM_PENCERESI = 20
# "[Echoing Silence] Enchantment Description: ..." — açıklama efsun adıyla aynı paragrafta.
_SATIR_ICI_EFSUN = re.compile(r"^\[([^\]]+)\]\s*Enchantment Description:")
# Durum bloğu (`Name: X`) satırları -> ilişki (özne: X).
_DURUM_SATIRLARI = {
    "True Name": "gercek_adi", "Rank": "rutbesi", "Memories": "anisi", "Echoes": "yanki",
    "Attributes": "niteligi", "Aspect": "gorunusu", "Shadows": "golgesi",
    "Class": "sinifi", "Aspect Abilities": "yetenegi", "Aspect Legacy": "yetenegi",
    "Flaw": "kusuru", "Dream Anchor": "ruya_capasi",
    # Tekil biçimler (85/341/450/974: yeni Nitelik; 353/354/744: Görünüş yeteneği).
    "Attribute": "niteligi", "Aspect Ability": "yetenegi", "Innate Ability": "yetenegi",
}
# Durum DEĞERİ satırları (bağ değil, `varlik_deger`): blok türü -> anahtarlar. Sayaçlar
# (`Death Charge`, `Vanquished Foes`, `Nightmares required`) anının/gölgenin değeridir.
_DEGER_SATIRLARI = {
    # "Shadow Core: Dormant." BİLEREK yok: yalnız 2/16/189/310'da yazılıyor, sonra hiç; ayrı alan
    # olunca Yükselmiş Şeytan Sunny'de "Çekirdek rütbesi: Uykuda" kalıyordu. Rütbeyi `Rank` taşır.
    "durum": frozenset(("Soul", "Shadow Cores", "Shadow Fragments", "Soul Cores", "Soul Fragments",
                        "Shadow Dance Mastery Level")),
    "Memory": frozenset(("Memory Tier", "Death Charge", "Vanquished Foes")),
    "Shadow": frozenset(("Shadow Fragments", "Nightmares required", "Dormant Nightmares")),
}
_DEGER_ANAHTARLARI = frozenset().union(*_DEGER_SATIRLARI.values())
# Başlıksız küme (`Name:` olmadan "Aspect: [Shadow Slave]."): bölümün son durum öznesine,
# o yoksa ana karaktere gider (995 bölümlük tarama: 15, 219, 352, 353, 358, 549, 653...).
# `Rank`, `True Name`, `Class` BİLEREK yok: tek başına başka bir şeyin rünü ya da diyalog
# olabilir. Değer köşeli olmalı ("Memories: none of your business" rün değildir).
_BASLIKSIZ_DURUM = frozenset(_DURUM_SATIRLARI) - {"Rank", "True Name", "Class"}
# Gölge/yankı bloğunu anlatımdan sonra yeniden açan anahtarlar. `Shadow Fragments` BİLEREK
# yok: Sunny'nin kendi sayacıyla aynı ad; sahibini payda söyler (`_sayac_sahibi`).
_ESYA_DEVAM = {t: (frozenset(_BLOK_ALT[t]) | _DEGER_SATIRLARI.get(t, frozenset())) - {"Shadow Fragments"}
               for t in ("Shadow", "Echo")}
# "[Shadow Fragments: 14/1000]." — erken bölümlerin köşeli biçimi (34, 41, 106, 511).
_KOSELI_SATIR = re.compile(r"^\[([A-Z][A-Za-z ]{1,30}):\s*([^\[\]]+?)\.?\]\.?$")
_TIRNAKLAR = "\"“”'‘’"


def _sayac_sahibi(anahtar: str, deger: str, paydalar: dict | None, ana_karakter: str,
                  esya: str | None = None) -> str | None:
    """Başlıksız sayaç satırının sahibi (ölçülen arıza: 848'den sonra Sunny'nin parça sayısı
    güncellenmiyordu; 870/873/922/989'da satır rün listesi AÇILMADAN okunuyor).

    Payda sahibini ayırır: Sunny'nin eşiği 1000 x çekirdek, Saint'inki 200, Nightmare'ınki 300.
    Önceki bölümlerde bu (anahtar, payda) kimde görüldüyse onundur; ana karakterin o anahtarda
    gördüğü en büyük paydadan BÜYÜKSE yeni çekirdeğin eşiğidir (ana karakterin). `esya`: az
    önce rünleri okunan gölge; paydası ana karakterinkinden KÜÇÜKSE onundur (106: Stone Saint'in
    ilk "[Shadow Fragments: 0/200.]" satırı anlatımdan sonra geliyor). Bilinmeyen payda kimseye
    yazılmaz: yanlış sahip, eksik kayıttan kötüdür."""
    p = payda(deger)
    if p is None or paydalar is None:
        return None
    if (anahtar, p) in paydalar:
        return paydalar[(anahtar, p)]
    ana_paydalari = [q for (a, q), o in paydalar.items() if a == anahtar and o == ana_karakter]
    if ana_paydalari and p > max(ana_paydalari):
        return ana_karakter
    if esya and ana_paydalari and p < max(ana_paydalari):
        return esya
    return None

# Durum bloğunu anlatımdan SONRA yeniden açabilen anahtarlar. `Rank`, `True Name`
# ve `Name` BİLEREK yok: tek başına "Rank:" başka bir şeyin rünü ya da diyalog
# olabilir (`test_duz_paragraf_run_blogunu_kapatir`). Bunlar yalnız kişi durumunda
# geçer; ölçülen: 848. bölümde Attributes ve Aspect satırları anlatımdan sonra
# geldiği için `Flame of Divinity`, `Master of Shadows`, `Shadow Slave` düşüyordu.
_DURUM_DEVAM_ANAHTARLARI = frozenset(
    ("Class", "Soul", "Shadow Cores", "Shadow Fragments", "Memories", "Echoes", "Shadows",
     "Attributes", "Attribute Description", "Aspect", "Aspect Rank", "Aspect Description",
     "Aspect Abilities", "Ability Description", "Aspect Legacy", "Flaw", "Flaw Description",
     "Dream Anchor", "Attribute", "Aspect Ability", "Innate Ability",
     "Shadow Dance Mastery Level", "Soul Cores", "Soul Fragments")
)


# Çoğul durum satırı kişinin o anki TAM listesidir (tekil "Attribute:" yalnız yeni öğeyi söyler).
# Ölçülen (2026-10-22): kart Sunny'de 48 anı gösteriyordu, 1026'daki tam liste 32; 1080'deki
# "Shadows:" 4 gölge, kart 6 (Stone/Marble Saint, Onyx Saint'in eski hâlleri).
_ENVANTER_ANAHTARLARI = {"Memories": "ani", "Shadows": "golge", "Echoes": "yanki", "Attributes": "nitelik"}


def _tam_liste(deger: str) -> bool:
    """Liste kesik değilse tam: köşeli öğelerin DIŞINDA üç nokta yok ("[Endless Spring]..."
    — 241, 353; ad içindeki "[M... Un...old]" sayılmaz). "—" boş tam listedir ("Echoes: —")."""
    dis = _KOSELI.sub("", deger)
    return "..." not in dis and "…" not in dis


def _ogeler(deger: str) -> list[str]:
    """`[A], [B]` -> [A, B]; köşeli yoksa düz değer (`Rank: Dreamer.`)."""
    bulunan = _KOSELI.findall(deger)
    if bulunan:
        return [b.strip().rstrip(".") for b in bulunan]
    tek = deger.strip().rstrip(".").strip()
    return [] if tek in ("", "—", "-") else [tek]


def sistem_baglarini_bul(metin: str, ana_karakter: str, ana_adlar: tuple[str, ...] = (),
                         paydalar: dict | None = None, bilinen_anilar: set[str] | None = None) -> list[tuple]:
    """Bir bölümün kaynağından (özne, ilişki, nesne, kanıt) dörtlüleri — ad düzeyinde.

    Rün satırları ardışık paragraflar olarak gelir; boş olmayan ve rün biçiminde
    olmayan bir paragraf bloğu kapatır. `Name: X` (ya da efendinin kısa kümesi
    `Master: X`) bloğu X'in durumudur; `Memory:`, `Shadow:`, `Echo:` blokları rünleri
    okunan kişinin (bölümdeki son `Name:` öznesi, yoksa ana karakter) sahip olduğu şeyi anlatır.

    `paydalar`: bölümler arasında taşınan (anahtar, payda) -> sahip tablosu; verilirse
    başlıksız sayaç satırları ("Shadow Fragments: [870/4000].") sahibine yazılır ve
    tablo güncellenir. None: başlıksız sayaçlar atlanır.

    `bilinen_anilar`: önceki bölümlerden bilinen Anı adları. `Memory:` başlığı olmadan gelen
    Anı satırı ("he found the description of Weaver’s Mask and read:" + efsunlar; 378, 456,
    522) son `ANI_ANLATIM_PENCERESI` paragrafta adı geçen TEK bilinen Anıya yazılır.
    """
    out: list[tuple] = []
    blok_ozne: str | None = None
    blok_tur: str | None = None
    efsun_sirasi: list[int] = []  # açıklaması henüz gelmemiş efsunların `out` sırası
    efsunlar: dict[str, int] = {}  # son Anının efsunları: ad -> `out` sırası
    son_ani: str | None = None     # anlatımla kapanmış son Anı bloğunun öznesi
    son_durum: str | None = None   # anlatımla kapanmış son durum bloğunun öznesi
    son_esya: tuple | None = None  # anlatımla kapanmış son gölge/yankı bloğu: (özne, tür)
    anlatim = 0                    # o bloktan beri geçen düz paragraf
    gorunus: str | None = None     # durum bloğundaki Aspect (Aspect Rank'ın öznesi)
    sahip = ana_karakter           # rünleri okunan kişi: bölümdeki son `Name:`/`Master:` öznesi
    son_baslik: str | None = None  # bölümdeki son blok başlığının türü (durum/Memory/Shadow/Echo)
    son_anlatim: deque = deque(maxlen=ANI_ANLATIM_PENCERESI)  # son düz paragraflar (Anı adı için)

    def deger_ekle(ozne: str, anahtar: str, deger_metni: str, kanit: str) -> None:
        out.append((ozne, DEGER, f"{anahtar}\t{deger_metni}", kanit))
        p = payda(deger_metni)
        if paydalar is not None and p is not None:
            paydalar[(anahtar, p)] = ozne

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
        koseli = _KOSELI_SATIR.match(paragraf)
        if koseli and koseli.group(1) in _DEGER_ANAHTARLARI:
            satir = _RUN_SATIRI.match(f"{koseli.group(1)}: [{koseli.group(2).strip()}]")
        else:
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
            elif blok_tur == "durum":
                son_durum, anlatim = blok_ozne, 0
            elif blok_tur in _ESYA_DEVAM:
                son_esya, anlatim = (blok_ozne, blok_tur), 0
            elif son_ani or son_durum or son_esya:
                anlatim += 1
            son_anlatim.append(paragraf)
            blok_ozne = blok_tur = None
            continue
        anahtar, deger = satir.group(1).strip(), satir.group(2)
        if blok_tur is None:
            if anahtar in _ANI_ANAHTARLARI and son_ani and anlatim < ANI_ANLATIM_PENCERESI:
                blok_ozne, blok_tur = son_ani, "Memory"
            elif anahtar in _DURUM_DEVAM_ANAHTARLARI and son_durum and anlatim < ANI_ANLATIM_PENCERESI:
                blok_ozne, blok_tur = son_durum, "durum"
            elif son_esya and anahtar in _ESYA_DEVAM[son_esya[1]] and anlatim < ESYA_ANLATIM_PENCERESI:
                blok_ozne, blok_tur = son_esya
        if anahtar in ("Name", "Master"):
            if deger.lstrip()[:1] in _TIRNAKLAR:
                continue  # "Master: "Hello."" — sohbet satırı
            ad = _ogeler(deger)
            blok_ozne = ana_karakter if ad and ad[0] in ana_adlar else (ad[0] if ad else None)
            blok_tur = "durum"
            if anahtar == "Master" and blok_ozne and blok_ozne != sahip:
                # Rünleri okunan kişinin efendisi; sonraki kısa küme efendinin durumudur.
                out.append((sahip, "efendisi", blok_ozne, paragraf))
            sahip, son_baslik = blok_ozne or ana_karakter, "durum"
            son_ani, son_durum, son_esya, gorunus, efsunlar, efsun_sirasi = None, None, None, None, {}, []
            continue
        if anahtar in _BLOK_SAHIPLIK:
            ogeler = _ogeler(deger)
            if ogeler:
                blok_ozne, blok_tur, son_baslik = ogeler[0], anahtar, anahtar
                efsun_sirasi, efsunlar = [], {}
                son_ani = son_durum = son_esya = None
                out.append((sahip, _BLOK_SAHIPLIK[anahtar], ogeler[0], paragraf))
                out.append((ogeler[0], "turu", anahtar, paragraf))
            continue
        if blok_tur is None:
            # Açık blok yok: rün listesi açılmadan tek bir küme ya da sayaç okunuyor.
            if anahtar in _DEGER_ANAHTARLARI:
                ogeler = _ogeler(deger)
                deger_metni = ogeler[0] if ogeler else ""
                esya = son_esya[0] if son_esya and son_esya[1] == "Shadow" and anlatim < ESYA_ANLATIM_PENCERESI \
                    and anahtar in _DEGER_SATIRLARI["Shadow"] else None
                ozne = _sayac_sahibi(anahtar, deger_metni, paydalar, ana_karakter, esya)
                if ozne is None and anahtar in _DEGER_SATIRLARI["durum"] and payda(deger_metni) is None:
                    ozne = sahip  # "Soul: …" sayaç değil, okunan kişinin durumu
                if ozne and deger_metni:
                    deger_ekle(ozne, anahtar, deger_metni, paragraf)
                continue
            # Gölge/yankı rünlerinden sonra başlıksız "Attribute:" o gölgenindir (376: Saint'in
            # [Stalwart]'ı Sunny'ye yazılıyordu); gölgenin niteliği zaten `Shadow Attributes`ta.
            nitelik_golgenin = anahtar in ("Attribute", "Attributes") and son_baslik in _ESYA_DEVAM
            if anahtar in _BASLIKSIZ_DURUM and "[" in deger and not nitelik_golgenin:
                blok_ozne, blok_tur = sahip, "durum"
            elif anahtar in _BLOK_ALT["Memory"] and bilinen_anilar:
                # Satıra EN YAKIN, bilinen bir Anı adı geçen paragraf (456: önce Covetous Coffer,
                # sonra "The runes of Weaver’s Mask..."); o paragrafta iki ad varsa belirsiz.
                gecen = next((g for g in ({a for a in bilinen_anilar if a in p} for p in reversed(son_anlatim))
                              if g), set())
                if len(gecen) == 1:
                    blok_ozne, blok_tur = gecen.pop(), "Memory"
                    efsun_sirasi, efsunlar = [], {}
        if blok_tur == "Memory" and anahtar == "Enchantment Description" and efsun_sirasi:
            # Açıklamalar efsunlarla AYNI SIRADA gelir; efsunun ne yaptığı bağın kanıtı olur.
            i = efsun_sirasi.pop(0)
            ozne, iliski, nesne, _k = out[i]
            out[i] = (ozne, iliski, nesne, paragraf)
            continue
        if blok_tur in _DEGER_SATIRLARI and anahtar in _DEGER_SATIRLARI[blok_tur] and blok_ozne:
            # Köşeli değerin İÇİ alınır: hem parantezden hem satıra yapışan site
            # filigranından arınır (ölçülen: "[777/4000]. <filigran>").
            ogeler = _ogeler(deger)
            deger_metni = ogeler[0] if ogeler else ""
            if deger_metni:
                deger_ekle(blok_ozne, anahtar, deger_metni, paragraf)
            continue
        if blok_tur == "durum" and anahtar == "Aspect Rank" and gorunus:
            for oge in _ogeler(deger):
                out.append((gorunus, "rutbesi", oge, paragraf))
        elif blok_tur == "durum" and anahtar in _DURUM_SATIRLARI and blok_ozne:
            for oge in _ogeler(deger):
                out.append((blok_ozne, _DURUM_SATIRLARI[anahtar], oge, paragraf))
                if anahtar == "Aspect":
                    gorunus = oge
            if anahtar in _ENVANTER_ANAHTARLARI and _tam_liste(deger):
                out.append((blok_ozne, ENVANTER,
                            f"{_ENVANTER_ANAHTARLARI[anahtar]}\t{json.dumps(_ogeler(deger), ensure_ascii=False)}",
                            paragraf))
        elif blok_tur in _BLOK_ALT and anahtar in _BLOK_ALT[blok_tur] and blok_ozne:
            for oge in _ogeler(deger):
                if anahtar == "Enchantment" and oge in efsunlar:
                    # Listede zaten olan efsunun tekil satırı (SS 83: "Enchantment: [Doubtless].")
                    # sıradaki açıklamanın KİME ait olduğunu söyler; bağ yinelenmez.
                    i = efsunlar[oge]
                    if i in efsun_sirasi:
                        efsun_sirasi.remove(i)
                    efsun_sirasi.insert(0, i)
                    continue
                if _BLOK_ALT[blok_tur][anahtar] == "efsunu":
                    efsun_sirasi.append(len(out))
                    efsunlar[oge] = len(out)
                out.append((blok_ozne, _BLOK_ALT[blok_tur][anahtar], oge, paragraf))
    return out


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


# Çekirdek sayısı sınıf basamağıdır (Beast 1 … Titan 7). Ölçülen (Sunny): 352 "Class: Monster" +
# "Shadow Cores: [2/7]", 526 Demon + 3/7, 702 Devil + 4/7. Parça eşiği 1000 x çekirdek; yeni
# çekirdekte sayaç sıfırlanır (354 "0/2000", 526 "0/3000", 702 "0/4000").
_CEKIRDEK_SAYACLARI = (("Shadow Cores", "Shadow Fragments"), ("Soul Cores", "Soul Fragments"))
_SAYAC = re.compile(r"^\s*(\d+)\s*/\s*(\d+)\s*$")
PARCA_CARPANI = 1000


def siniftan_turet(run: list[dict], sinif: dict, basamak: int) -> list[dict]:
    """Anlatımla gelen sınıftan (`sinif`, rün alanı biçiminde) çekirdek sayısını ve parça eşiğini
    türet. Ölçülen: 1090'da beşinci çekirdek "Sunny did not have to summon the runes" ile oluştu,
    kart 1026'daki "4/7" ve 1047'deki "3857/4000"de kaldı.

    Yalnız rünlerde zaten olan ve sınıftan ESKİ sayaç güncellenir; parça eşiği yalnız sahibin
    son eşiği 1000 x çekirdek kuralına uyuyorsa yeniden yazılır. Güncel parça sayısı bilinmez
    ("?/5000"): sıfır yazmak uydurma olurdu. Yeni kayıtların `anahtar`ı çağıran doldurur."""
    alanlar = {k["ad"]: k for k in run}
    eskiler, yeniler = set(), []
    for cekirdek_ad, parca_ad in _CEKIRDEK_SAYACLARI:
        cekirdek = alanlar.get(cekirdek_ad)
        m = _SAYAC.match(cekirdek["deger"]) if cekirdek else None
        if not m or int(m.group(1)) >= basamak or (cekirdek["ilk_bolum"] or 0) >= (sinif["ilk_bolum"] or 0):
            continue
        n = int(m.group(1))
        eskiler.add(id(cekirdek))
        yeniler.append(_turetilmis(cekirdek, f"{basamak}/{m.group(2)}", sinif,
                                   f"Çekirdek sayısı sınıftan türetildi: {basamak}. sınıf, {basamak} çekirdek."))
        parca = alanlar.get(parca_ad)
        if parca and payda(parca["deger"]) == PARCA_CARPANI * n \
                and (parca["ilk_bolum"] or 0) < (sinif["ilk_bolum"] or 0):
            esik = PARCA_CARPANI * basamak
            eskiler.add(id(parca))
            yeniler.append(_turetilmis(parca, f"?/{esik}", sinif,
                                       f"Yeni çekirdekte sayaç {esik} eşiğinden yeniden başlar; "
                                       "güncel sayı rünlerde görünmedi."))
    return [k for k in run if id(k) not in eskiler] + yeniler


def _turetilmis(eski: dict, deger: str, sinif: dict, not_: str) -> dict:
    kanit = "\n".join(x for x in (sinif.get("kanit"), f"({not_})") if x)
    return {**eski, "anahtar": None, "deger": deger, "alanlar": {"deger": deger},
            "ilk_bolum": sinif["ilk_bolum"], "son_bolum": sinif["ilk_bolum"], "kanit": kanit,
            "origin": sinif["origin"]}


def tutarlilik(run: list[dict], golge_sayisi: int, sinif_sirasi: list[str]) -> list[str]:
    """Kartın kendi içinde çelişen değerleri (kitabın kuralları). DÜZELTMEZ, yalnız söyler: bir
    tarafın eski ya da yanlış okunduğunu gösterir (ölçülen: Tiran sınıfı, 4/7 çekirdek, 3857/4000).

    Kurallar: sınıf basamağı = çekirdek sayısı; parça eşiği = 1000 x çekirdek; gölge sayısı
    çekirdeği aşamaz (her gölge bir çekirdekte durur)."""
    alanlar = {k["ad"]: k for k in run}
    uyarilar = []
    sinif = alanlar.get("sinifi")
    basamak = (sinif_sirasi.index(sinif["deger"].casefold()) + 1
               if sinif and sinif["deger"].casefold() in sinif_sirasi else 0)
    for cekirdek_ad, parca_ad in _CEKIRDEK_SAYACLARI:
        cekirdek = alanlar.get(cekirdek_ad)
        m = _SAYAC.match(cekirdek["deger"]) if cekirdek else None
        if not m:
            continue
        n = int(m.group(1))
        if basamak and n != basamak:
            uyarilar.append(f"Sınıf {sinif['deger']} ({basamak}. basamak) ile {cekirdek_ad} {n} uyuşmuyor "
                            f"(sınıf bölüm {sinif['ilk_bolum']}, çekirdek bölüm {cekirdek['ilk_bolum']}).")
        parca = alanlar.get(parca_ad)
        p = payda(parca["deger"]) if parca else None
        if p is not None and p != PARCA_CARPANI * n:
            uyarilar.append(f"{parca_ad} eşiği {p}, {n} çekirdek için {PARCA_CARPANI * n} olmalı "
                            f"(parça bölüm {parca['ilk_bolum']}).")
        if golge_sayisi > n:
            uyarilar.append(f"{golge_sayisi} gölge var ama {n} çekirdek: gölge listesi ya da çekirdek eski.")
    return uyarilar
