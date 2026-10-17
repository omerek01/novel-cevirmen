"""Ö1 ölçümü: sözlük karşılığı değişince eski bölümleri yeniden çevirmeden güncellemek.

Veritabanı KOPYASI üzerinde çalışır, yazmaz. Üç ölçüm:

1. **Yerinde yazım** — sözlük geçmişindeki gerçek karşılık değişiklikleri (`sozluk_gecmis`,
   islem=guncelle) eski karşılığı içeren bölümlere uygulanır: kaç geçiş otomatik değişti,
   kaçı neden belirsiz kaldı.
2. **Kitapta tanıklık** — üretilen yeni yüzey (ör. "Oyuk'a") kitabın çevirilerinde modelin
   kendisinin yazdığı bir biçim olarak geçiyor mu (doğruluğun otomatik vekili).
3. **Yer tutucu** — bugünkü sözlükle her bölüm ``⟦n|ek|biçim⟧`` şablonuna çevrilir ve geri
   doldurulur: geri doldurma özgün metni birebir veriyor mu, geçişlerin kaçı belirteç oldu.

``--hakem``: değişen geçişlerden örneklem, sunucuda Vertex hakemine (varsayılan
gemini-2.5-pro) "yeni biçimin eki doğru mu" diye sorulur. Roman metni çıktı klasöründe kalır;
özet (`ozet.json`) metin içermez.

    python scripts/sozluk_yerinde_olcum.py --db KOPYA.db --kitap shadow-slave --cikti KLASOR
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK / "app"))

from core import sozluk_yerinde as sy  # noqa: E402
from core import translate  # noqa: E402
from core.turkce_eslesme import karsilik_gecer, tr_kucuk  # noqa: E402

_SOZCUK = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)?")


def bolumler(conn, kitap):
    return [dict(url=u, no=n, tr=t or "", en=s) for u, n, t, s in conn.execute(
        "SELECT url, chapter_no, translation, source_text FROM chapters "
        "WHERE book_slug = ? AND translation IS NOT NULL ORDER BY chapter_no", (kitap,))]


def degisiklikler(conn, kitap):
    sonuc, gorulen = [], set()
    for kaynak, onceki, sonraki in conn.execute(
            "SELECT source, onceki, sonraki FROM sozluk_gecmis WHERE book_slug = ? "
            "AND islem = 'guncelle' ORDER BY zaman", (kitap,)):
        try:
            o, s = json.loads(onceki or "{}"), json.loads(sonraki or "{}")
        except ValueError:
            continue
        if not (isinstance(o, dict) and isinstance(s, dict)):
            continue
        eski, yeni = (o.get("target") or "").strip(), (s.get("target") or "").strip()
        if eski and yeni and eski != yeni and (kaynak, eski, yeni) not in gorulen:
            gorulen.add((kaynak, eski, yeni))
            sonuc.append((kaynak, eski, yeni))
    return sonuc


def _cumle(paragraf: str, aranan: str) -> str:
    i = paragraf.find(aranan)
    if i < 0:
        return paragraf[:300]
    bas = max(paragraf.rfind(c, 0, i) for c in ".!?\n") + 1
    sonlar = [j for j in (paragraf.find(c, i + len(aranan)) for c in ".!?\n") if j >= 0]
    return paragraf[bas:(min(sonlar) + 1 if sonlar else len(paragraf))].strip()


def yerinde_olc(bols, degs, tanik):
    satirlar, ornekler = [], []
    for kaynak, eski, yeni in degs:
        desen = translate._term_regex(kaynak)
        say = Counter()
        bolum_say = 0
        for b in bols:
            if not karsilik_gecer(eski, b["tr"]):
                continue
            bolum_say += 1
            tr_p = b["tr"].split("\n\n")
            en_p = b["en"].split("\n\n") if b["en"] else None
            yeni_p, oz = sy.yeniden_yaz(tr_p, en_p, desen, eski, yeni)
            say["degisen"] += oz.degisen
            for neden in oz.belirsiz:
                say[neden] += 1
            for (es_y, ye_y) in oz.ornekler:
                son = tr_kucuk(ye_y.split()[-1])
                say["tanikli" if son in tanik else "taniksiz"] += 1
            # Hakem örneklemi için değişen paragrafların cümleleri.
            for i, (a, c) in enumerate(zip(tr_p, yeni_p)):
                if a != c:
                    for es_y, ye_y in oz.ornekler:
                        if ye_y in c:
                            ornekler.append(dict(kaynak=kaynak, eski=eski, yeni=yeni,
                                                 eski_yuzey=es_y, yeni_yuzey=ye_y,
                                                 once=_cumle(a, es_y), sonra=_cumle(c, ye_y),
                                                 bolum=b["no"]))
                            break
        toplam = say["degisen"] + sum(v for k, v in say.items()
                                      if k not in ("degisen", "tanikli", "taniksiz"))
        satirlar.append(dict(kaynak=kaynak, eski=eski, yeni=yeni, bolum=bolum_say,
                             gecis=toplam, **say))
    return satirlar, ornekler


def yer_tutucu_olc(bols, sozluk):
    kayitlar = {i: (s, t) for i, (s, t) in enumerate(sorted(sozluk.items()))}
    desenler = {i: translate._term_regex(s) for i, (s, _t) in kayitlar.items()}
    karsiliklar = {i: t for i, (_s, t) in kayitlar.items()}
    say = Counter()
    for b in bols:
        if not b["tr"]:
            continue
        say["bolum"] += 1
        tr_p = b["tr"].split("\n\n")
        en_p = b["en"].split("\n\n") if b["en"] else None
        sab, s = sy.sablon_bolum(tr_p, en_p, kayitlar, desenler)
        say.update(s)
        geri = [sy.doldur(p, karsiliklar) for p in sab]
        if geri == tr_p:
            say["geri_doldurma_birebir"] += 1
        else:
            say["geri_doldurma_farkli"] += 1
            say["farkli_paragraf"] += sum(1 for a, c in zip(tr_p, geri) if a != c)
    say["kayit"] = len(kayitlar)
    return dict(say)


HAKEM_TALIMAT = (
    "Türkçe dilbilgisi denetçisisin. Her maddede bir romandan alınmış iki cümle var: "
    "'once' özgün cümle, 'sonra' aynı cümlede bir özel ad/terim başka bir karşılıkla "
    "değiştirilmiş hâli ('eski_yuzey' -> 'yeni_yuzey'). YALNIZ 'yeni_yuzey' sözcüğünün "
    "Türkçe çekimini değerlendir: ek doğru mu (ünlü uyumu, kaynaştırma harfi, ünsüz "
    "benzeşmesi/yumuşaması, kesme işareti), cümlenin geri kalanıyla dilbilgisel olarak "
    "uyumlu mu. Terimin anlamını ya da çeviri seçimini DEĞERLENDİRME. JSON dizi döndür: "
    "[{\"id\": n, \"karar\": \"dogru\"|\"yanlis\"|\"emin_degil\", \"dogrusu\": \"yanlışsa "
    "doğru biçim, değilse boş\"}]."
)


def _yerel_yargila(model, isler):
    """Hakemi bu bilgisayardan AI Studio anahtar havuzuyla çağırır (sunucuya erişim
    yokken). 429'da sıradaki anahtar; havuz bitince iş hata satırıyla döner."""
    from dotenv import load_dotenv
    from google import genai
    from google.genai import types
    load_dotenv(KOK.parents[1] / ".env")
    anahtarlar = translate.gemini_anahtarlari()
    yapilandirma = types.GenerateContentConfig(
        system_instruction=HAKEM_TALIMAT, response_mime_type="application/json",
        temperature=0, max_output_tokens=32768)
    sonuc = []
    # İstemci saklanır: satır içinde kurulup bırakılan istemci istek gitmeden kapanıyordu
    # ("client has been closed").
    istemciler = [genai.Client(api_key=a) for a in anahtarlar]
    for is_ in isler:
        satir = {"anahtar": is_["anahtar"]}
        for istemci in istemciler:
            try:
                r = istemci.models.generate_content(
                    model=model, contents=json.dumps(is_["istem"], ensure_ascii=False),
                    config=yapilandirma)
                satir["yanit"] = r.text or ""
                break
            except Exception as e:  # kota/geçici: sıradaki anahtar
                satir["hata"] = type(e).__name__ + ": " + str(e)[:160]
        sonuc.append(satir)
        print(is_["anahtar"], "tamam" if "yanit" in satir else satir.get("hata"), flush=True)
    return sonuc


def hakem(ornekler, model, es, cikti: Path, yerel=False):
    paketler = [ornekler[i:i + 25] for i in range(0, len(ornekler), 25)]
    isler = [{"anahtar": f"p{k}", "istem": [
        {"id": j, "once": o["once"], "sonra": o["sonra"], "eski_yuzey": o["eski_yuzey"],
         "yeni_yuzey": o["yeni_yuzey"]} for j, o in enumerate(p)]} for k, p in enumerate(paketler)]
    if yerel:
        yanitlar = _yerel_yargila(model, isler)
    else:
        sys.path.insert(0, str(KOK / "scripts"))
        import anlam_kiyas as ak  # sunucu yardımcıları (ssh + Vertex)
        # anlam_kiyas'ın yargılama betiği: sunucuda Vertex hakemi, JSON yanıt, sıcaklık 0.
        yanitlar = ak._uzak(ak._YARGILA,
                            {"hakem": model, "talimat": HAKEM_TALIMAT, "isler": isler, "es": es})
    kararlar = Counter()
    duz = []
    for y in yanitlar:
        k = int(y["anahtar"][1:])
        try:
            liste = json.loads(y.get("yanit") or "[]")
        except ValueError:
            kararlar["cozulemedi"] += len(paketler[k])
            continue
        for d in liste:
            o = paketler[k][int(d["id"])]
            kararlar[d.get("karar", "?")] += 1
            duz.append({**o, "karar": d.get("karar"), "dogrusu": d.get("dogrusu", "")})
    (cikti / "hakem.json").write_text(json.dumps(duz, ensure_ascii=False, indent=1), "utf-8")
    return dict(kararlar)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--kitap", default="shadow-slave")
    ap.add_argument("--cikti", required=True)
    ap.add_argument("--hakem", action="store_true")
    ap.add_argument("--hakem-model", default="gemini-2.5-pro")
    ap.add_argument("--orneklem", type=int, default=200)
    ap.add_argument("--es", type=int, default=2)
    ap.add_argument("--yerel", action="store_true", help="hakemi sunucu yerine yerel anahtarlarla çağır")
    a = ap.parse_args()
    cikti = Path(a.cikti)
    cikti.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    bols = bolumler(conn, a.kitap)
    tanik = {tr_kucuk(w) for b in bols for w in _SOZCUK.findall(b["tr"])}
    t0 = time.monotonic()
    satirlar, ornekler = yerinde_olc(bols, degisiklikler(conn, a.kitap), tanik)
    t1 = time.monotonic()
    sozluk = {s: t for s, t in conn.execute(
        "SELECT source, target FROM glossary WHERE book_slug = ? AND target IS NOT NULL "
        "AND target != ''", (a.kitap,))}
    yt = yer_tutucu_olc(bols, sozluk)
    t2 = time.monotonic()
    toplam = Counter()
    for s in satirlar:
        for k, v in s.items():
            if isinstance(v, int) and k not in ("bolum",):
                toplam[k] += v
    ozet = dict(kitap=a.kitap, bolum=len(bols), degisiklik=len(satirlar), toplam=dict(toplam),
                yer_tutucu=yt, sure_sn=dict(yerinde=round(t1 - t0, 1), yer_tutucu=round(t2 - t1, 1)),
                degisiklikler=[{k: v for k, v in s.items()} for s in satirlar])
    (cikti / "ornekler.json").write_text(json.dumps(ornekler, ensure_ascii=False, indent=1), "utf-8")
    if a.hakem and ornekler:
        random.seed(20261018)
        # Aynı (eski yüzey, yeni yüzey) çiftinden bir örnek: sık biçim örneklemi doldurmasın.
        tekil = {}
        for o in ornekler:
            tekil.setdefault((o["eski_yuzey"], o["yeni_yuzey"]), o)
        secim = random.sample(list(tekil.values()), min(a.orneklem, len(tekil)))
        ozet["hakem"] = dict(model=a.hakem_model, orneklem=len(secim), tekil_cift=len(tekil),
                             kararlar=hakem(secim, a.hakem_model, a.es, cikti, a.yerel))
    (cikti / "ozet.json").write_text(json.dumps(ozet, ensure_ascii=False, indent=1), "utf-8")
    print(json.dumps({k: v for k, v in ozet.items() if k != "degisiklikler"},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
