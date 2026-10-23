"""Gemini 4 Argon'un DÜŞÜNME düzeyi ile çeviri kalitesini kıyaslar.

Soru (kullanıcı, 2026-10-23): Argon'da düşünme açık mı, ve açmak çeviri
kalitesini artırıyor mu? Üretim yolu `thinking_config=None` gönderiyor
(`GEMINI_DUSUNME_BUTCESI` None, `_DUSUNME_AYARI` yalnız defter tarafında
kuruluyor), yani Argon KENDİ varsayılan düşünmesiyle koşuyor. Argon
`thinking_budget`'ı ve `minimal` düzeyini 400 ile reddediyor; yalnız
`thinking_level` LOW/MEDIUM/HIGH kabul ediyor.

Kollar: varsayilan (hiç alan göndermez) · low · medium · high.

Ölçütler DETERMİNİSTİK ve bedava (hakem modeli YOK): hizalama, uzunluk oranı,
İngilizce kalıntı, yabancı alfabe sızıntısı, sözlük ihlali. Düşünme tokenı
`usage_metadata.thoughts_token_count`'tan okunur — "düşünme açık mı" sorusunun
TEK doğrudan cevabı bu.

Üretim koduna ve DB'ye YAZMAZ; bölümler yalnız kaynak metin ve sözlük için
OKUNUR. Kaynak, sözlük ve istem kurulumu da SUNUCUDA yapılır: gerçek önbellek
orada, yerel kopyada kaynak metin olmayabilir. `--calistir` olmadan hiçbir
ücretli çağrı yapılmaz, yalnız kol listesi ve istem boyutları basılır.

MALİYET: bölüm x kol kadar Argon çağrısı. Ölçülen üretim profili bölüm başına
~4,8k giriş + ~1,3k çıkış; düşünme açıkken çıkış birkaç katına çıkabilir.
4 bölüm x 4 kol ~ 0,3-1,5 $ arası (tanıtım fiyatı 2,00/10,00 $).

Örnek:
    python scripts/argon_dusunme_kiyas.py --kitap shadow-slave \
        --bolumler 1095 1096 1097 1098 --cikti olcum/argon-dusunme.jsonl --calistir
    python scripts/argon_dusunme_kiyas.py --ozet olcum/argon-dusunme.jsonl
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import subprocess
import sys

# Konsolu UTF-8'e zorla: Windows varsayılanı cp1252 ve ölçümün KONUSU zaten
# Latin dışı karakterler. Zorlanmadığı ilk koşuda `print` 3. satırda
# UnicodeEncodeError ile çöktü, yerel boru kapandı ve ölçüm yarıda kaldı —
# modelin değil betiğin arızasıydı, ücretli çağrılar boşa gitti.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SUNUCU = "OMEREK@100.75.105.102"
CANLI = "/home/OMEREK/novel-cevirmen-sozluk"
VENV = "/home/OMEREK/novel-cevirmen/.venv/bin/python"
MODEL = "gemini-4-argon"
# Argon'un kabul ettiği düzeyler + "hiç alan göndermeme" kolu. `minimal` ve
# `thinking_budget` 400 ile reddedilir, bu yüzden kollara GİRMEZ.
KOLLAR = ("varsayilan", "low", "medium", "high")

# Sunucuda koşan gövde: kaynak + sözlük + istem + çağrı + puanlama hepsi orada.
UZAK = r'''
import json, os, re, sys, time
from dotenv import load_dotenv
load_dotenv(CANLI + "/.env")
sys.path.insert(0, CANLI + "/app")
from google import genai
from google.genai import types
from core import cache, glossary, translate as t

ALANLAR = {"varsayilan": None, "low": {"thinking_level": "low"},
           "medium": {"thinking_level": "medium"}, "high": {"thinking_level": "high"}}

# Yabancı alfabe denetimi burada YENİDEN yazılır: canlı kopya henüz bu denetimi
# taşımıyor olabilir ve ölçüm kodu üretim sürümüne bağlı kalmamalı.
LATIN = re.compile(r"[A-Za-zÀ-ɏḀ-ỿ]")
def yabanci(s):
    return {c for c in s if c.isalpha() and not LATIN.match(c)}
def alfabe_sizinti(tr_p, en_p):
    if len(tr_p) != len(en_p):
        return {}
    out = {}
    for i, (tr, en) in enumerate(zip(tr_p, en_p)):
        kaynakta = yabanci(en)
        s = [w for w in tr.split() if yabanci(w) - kaynakta]
        if s:
            out[i] = " ".join(s)
    return out

sozluk = glossary.get_glossary(KITAP)
kosullar = glossary.ceviri_kosullari(KITAP)
kaynaklar = {r["chapter_no"]: r["source"] for r in cache.kaynak_bolumleri(KITAP)}
paketler = []
for no in BOLUMLER:
    kaynak = kaynaklar.get(no)
    if not kaynak:
        print(json.dumps({"bolum": no, "hata": "kaynak metin onbellekte yok"}), flush=True)
        continue
    paras = [x.strip() for x in kaynak.split("\n\n") if x.strip()]
    # Bağlam BİLEREK boş: kollar arasındaki tek değişken düşünme düzeyi olmalı.
    paketler.append({"bolum": no, "paras": paras,
                     "user": t._build_user_prompt(paras, sozluk, "", kosullar)})

if not CALISTIR:
    for x in paketler:
        print(json.dumps({"bolum": x["bolum"], "paragraf": len(x["paras"]),
                          "istem_karakter": len(x["user"]),
                          "tahmini_giris_token": round(len(x["user"]) / 3.5)}), flush=True)
    sys.exit(0)

istemci = genai.Client(
    vertexai=True, project=os.environ["VERTEX_PROJE"],
    location=os.getenv("VERTEX_KONUM") or "global",
    http_options=types.HttpOptions(timeout=300000,
                                   retry_options=types.HttpRetryOptions(attempts=1)))

for x in paketler:
    for kol in KOLLAR:
        jeton = t._DUSUNME_AYARI.set(ALANLAR[kol])
        satir = {"bolum": x["bolum"], "kol": kol}
        bas = time.monotonic()
        try:
            cfg = t._gemini_yapilandirmasi(t.SYSTEM_INSTRUCTION, t.MAX_OUTPUT_TOKENS, MODEL)
            satir["dusunme_gonderildi"] = (
                None if cfg.thinking_config is None
                else cfg.thinking_config.model_dump(mode="json", exclude_none=True))
            y = istemci.models.generate_content(model=MODEL, contents=x["user"], config=cfg)
            m = y.usage_metadata
            satir.update(
                giris=getattr(m, "prompt_token_count", 0) or 0,
                gorunur_cikis=getattr(m, "candidates_token_count", 0) or 0,
                dusunme=getattr(m, "thoughts_token_count", 0) or 0,
                bitis=[str(c.finish_reason) for c in (y.candidates or [])],
                model_surumu=y.model_version)
            ceviri = (json.loads(y.text).get("translation") or "")
            tr_p = t._split_by_markers(ceviri, len(x["paras"]))
            satir["hizali"] = tr_p is not None
            if tr_p is None:
                tr_p, olcum_en = [t._strip_markers(ceviri)], ["\n\n".join(x["paras"])]
            else:
                olcum_en = x["paras"]
            duz, kaynak = "\n\n".join(tr_p), "\n\n".join(x["paras"])
            satir["uzunluk_orani"] = round(len(duz) / len(kaynak), 4) if kaynak else None
            satir["ingilizce_kalinti"] = len(t.ingilizce_kalinti(tr_p, olcum_en, sozluk))
            satir["alfabe_kalintisi"] = alfabe_sizinti(tr_p, olcum_en)
            satir["sozluk_ihlali"] = len(t.sozluk_ihlalleri(sozluk, kaynak, duz, kosullar))
            satir["ceviri"] = duz
        except Exception as exc:
            satir.update(hata_turu=type(exc).__name__, hata=str(exc)[:300])
        finally:
            t._DUSUNME_AYARI.reset(jeton)
        satir["sure_sn"] = round(time.monotonic() - bas, 2)
        print(json.dumps(satir, ensure_ascii=True), flush=True)
'''

# Tanıtım fiyatı (2026-11-30'a kadar), $/1M token. `kullanim.FIYAT` ile aynı kalmalı.
FIYAT_GIRIS, FIYAT_CIKIS = 2.00, 10.00


def ozetle(yol: Path) -> None:
    """Kol kol özet: düşünme payı, maliyet, kalite ölçütleri."""
    satirlar = [json.loads(x) for x in yol.read_text(encoding="utf-8").splitlines() if x.strip()]
    print(f"{'kol':<11} {'n':>2} {'dusunme':>8} {'gorunur':>8} {'pay':>5} "
          f"{'uzunluk':>8} {'hizali':>6} {'ing':>4} {'alfabe':>6} {'sozluk':>6} "
          f"{'sn':>5} {'$/bolum':>8}")
    for kol in KOLLAR:
        g = [s for s in satirlar if s.get("kol") == kol and "hata" not in s]
        if not g:
            print(f"{kol:<11} — ölçüm yok (hata)")
            continue
        d = statistics.mean(s["dusunme"] for s in g)
        c = statistics.mean(s["gorunur_cikis"] for s in g)
        i = statistics.mean(s["giris"] for s in g)
        mal = (i * FIYAT_GIRIS + (c + d) * FIYAT_CIKIS) / 1e6
        print(f"{kol:<11} {len(g):>2} {d:>8.0f} {c:>8.0f} "
              f"{(d / (d + c) * 100 if d + c else 0):>4.0f}% "
              f"{statistics.mean(s['uzunluk_orani'] for s in g):>8.3f} "
              f"{sum(s['hizali'] for s in g):>3}/{len(g):<2} "
              f"{sum(s['ingilizce_kalinti'] for s in g):>4} "
              f"{sum(len(s['alfabe_kalintisi']) for s in g):>6} "
              f"{sum(s['sozluk_ihlali'] for s in g):>6} "
              f"{statistics.mean(s['sure_sn'] for s in g):>5.0f} {mal:>8.4f}")
    sizan = [(s["kol"], s["bolum"], v) for s in satirlar
             for v in (s.get("alfabe_kalintisi") or {}).values()]
    if sizan:
        print("\nyabancı alfabe sızıntıları:")
        for kol, bolum, v in sizan:
            print(f"  {kol:<11} #{bolum}  {v}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--kitap")
    p.add_argument("--bolumler", type=int, nargs="+")
    p.add_argument("--cikti", type=Path)
    p.add_argument("--calistir", action="store_true",
                   help="ÜCRETLİ: bölüm x kol kadar Argon çağrısı yapar.")
    p.add_argument("--ozet", type=Path, help="Mevcut ölçüm dosyasını özetle, çağrı yapmaz.")
    a = p.parse_args()

    if a.ozet:
        ozetle(a.ozet)
        return
    if not (a.kitap and a.bolumler and a.cikti):
        raise SystemExit("--kitap, --bolumler ve --cikti gerekli (ya da --ozet)")
    if a.cikti.exists():
        raise SystemExit("Ölçüm çıktısı zaten var; farklı --cikti kullanın.")

    basliklar = "\n".join([
        f"CANLI = {CANLI!r}", f"KITAP = {a.kitap!r}", f"BOLUMLER = {a.bolumler!r}",
        f"KOLLAR = {list(KOLLAR)!r}", f"MODEL = {MODEL!r}", f"CALISTIR = {a.calistir!r}",
    ])
    proc = subprocess.Popen(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
         "-i", str(Path.home() / ".ssh/google_compute_engine"), SUNUCU,
         f"{VENV} -u -"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    proc.stdin.write((basliklar + "\n" + UZAK).encode())
    proc.stdin.close()
    a.cikti.parent.mkdir(parents=True, exist_ok=True)
    with a.cikti.open("x", encoding="utf-8") as f:
        for satir in proc.stdout:
            kayit = json.loads(satir)
            f.write(json.dumps(kayit, ensure_ascii=False) + "\n")
            f.flush()
            print(json.dumps({k: v for k, v in kayit.items() if k != "ceviri"},
                             ensure_ascii=False), flush=True)
    if proc.wait():
        raise RuntimeError(proc.stderr.read().decode("utf-8", "replace"))
    if a.calistir:
        print()
        ozetle(a.cikti)


if __name__ == "__main__":
    main()
