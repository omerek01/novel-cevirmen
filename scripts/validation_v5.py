"""Faz 2A v5 — kapsama taramalı çıkarıcı: bilinen regresyon (3) + kör holdout (10).

YALNIZ simülasyon (`bolum_degerlendir`): grafik/değer/sözlük/inceleme/baş/işleme/öneri/
çeviri tablolarına YAZILMAZ; önce/sonra hash'leri eşit olmalı. Bütün model çağrıları
`bilgi_delta.CIKARICI_MODELI` (Vertex) — ücretsiz Gemini'ye ya da başka sağlayıcıya
yedek YOK; sayaç `free_gemini_calls` ile ölçülür ve 0 değilse koşu başarısızdır.
Vertex geçici hatası mevcut sınırlı geri-çekilmeyle tekrar edilir; yine yanıt yoksa
bölüm PROVIDER_BLOCKED yazılır (MODEL_FAIL / recall kaybı DEĞİL).

  --stage regression --gold G                  bölümler 313, 670, 691
  --stage holdout --gold G --holdout H         H: dondurulmuş liste (+ hash dosyası)
Var olan bir çıktı dosyasının üzerine YAZMAZ (sessiz tekrar yok).
"""
import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT))
REGRESSION = (313, 670, 691)
GORULEN_HOLDOUT = (83, 187, 343, 374, 542, 590, 681, 744, 782, 887,   # v5.2 holdout -> GÖRÜLDÜ
                   33, 141, 199, 322, 460, 556, 659, 740, 769, 888)   # v6 holdout -> GÖRÜLDÜ
ESKI_DOGRULAMA = {2, 15, 24, 61, 106, 162, 273, 313, 352, 360, 381, 394, 412, 431, 479, 555,
                  670, 685, 686, 691, 822, 848, 923}


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def model_sec(ad: str | None) -> str:
    """Model kıyası (v5.1) için çıkarıcı modeli. YALNIZ tanımlı Vertex modelleri; boşsa
    varsayılan `CIKARICI_MODELI`. Çeviri yapılandırmasına dokunmaz."""
    from core import bilgi_delta as bd
    model = ad or bd.CIKARICI_MODELI
    bd.saglayici_dogrula(model)
    return model


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--gold", type=Path, required=True)
    ap.add_argument("--stage", choices=("regression", "holdout", "seen"), required=True)
    ap.add_argument("--chapters", help="seen aşaması: virgüllü, görülen holdout alt kümesi")
    ap.add_argument("--holdout", type=Path)
    ap.add_argument("--env", type=Path)
    ap.add_argument("--model", help="yalnız Vertex (varsayılan: CIKARICI_MODELI)")
    ap.add_argument("--aday", action="store_true", help="v8 aday-öncelikli + span kimlikli çıkarım")
    a = ap.parse_args()
    if a.db.resolve() == (ROOT / "cache/chapters.db").resolve():
        ap.error("canlı DB yasak")
    if a.out.exists():
        ap.error("çıktı var: sessiz tekrar/üzerine yazma yok")
    gold_sha = sha(a.gold)
    gold_sha_dosya = a.gold.with_suffix(".sha256")
    if gold_sha_dosya.exists() and gold_sha_dosya.read_text().split()[0] != gold_sha:
        ap.error("gold dondurulmuş hash'le uyuşmuyor")
    if a.stage == "regression":
        bolumler = REGRESSION
    elif a.stage == "seen":
        bolumler = tuple(int(x) for x in (a.chapters or "").split(",") if x)
        if not bolumler or not set(bolumler) <= set(GORULEN_HOLDOUT):
            ap.error("seen: yalnız görülen holdout bölümleri")
    else:
        if not a.holdout:
            ap.error("--holdout gerekli")
        h = json.loads(a.holdout.read_text(encoding="utf-8"))
        bolumler = tuple(h["chapters"])
        beklenen = a.holdout.with_suffix(".sha256").read_text().split()[0]
        if sha(a.holdout) != beklenen:
            ap.error("holdout listesi dondurulmuş hash'le uyuşmuyor")
        if len(bolumler) != 10 or set(bolumler) & (ESKI_DOGRULAMA | set(GORULEN_HOLDOUT)):
            ap.error("holdout 10 bölüm olmalı ve eski doğrulama bölümlerini içermemeli")
        gold_bolumler = {x["chapter"] for x in json.loads(a.gold.read_text(encoding="utf-8"))["items"]}
        if not gold_bolumler <= set(bolumler):
            ap.error("gold holdout dışı bölüm içeriyor")

    from dotenv import load_dotenv
    if a.env:
        load_dotenv(a.env)
    os.environ["NOVEL_DB_PATH"] = str(a.db.resolve())
    from core import api_durum, bilgi_aday as ba, bilgi_delta as bd, translate
    talimat = ba.ADAY_TALIMATI if a.aday else bd.CIKARICI_TALIMATI
    surum = ({"extractor": ba.ADAY_CIKARICI_SURUMU, "prompt": ba.ADAY_ISTEM_SURUMU, "schema": ba.ADAY_SEMA_SURUMU} if a.aday
             else {"extractor": bd.CIKARICI_SURUMU, "prompt": bd.ISTEM_SURUMU, "schema": bd.SEMA_SURUMU})
    from scripts.validation_v3 import parmakizi

    model = model_sec(a.model)
    assert bd.saglayici_dogrula(model) == "VERTEX"
    bd._connect().close()
    once = parmakizi(a.db)

    denemeler, zincirler = [], []
    asil_kayit = api_durum.istek_kaydet

    def kaydet(*args, **kw):
        v = dict(zip(("anahtar", "sira", "model", "sonuc", "kod", "sure_ms"), args)); v.update(kw)
        denemeler.append({k: v.get(k) for k in ("anahtar", "model", "sonuc", "kod", "sure_ms")})
        return asil_kayit(*args, **kw)
    api_durum.istek_kaydet = kaydet
    asil_zincir = translate._generate_with_fallback

    def zincir(fabrika, modeller, *args, **kw):
        zincirler.append(tuple(modeller))
        if tuple(modeller) != (model,):
            raise bd.SaglayiciHatasi(f"izin verilmeyen zincir: {modeller}")
        return asil_zincir(fabrika, modeller, *args, **kw)
    translate._generate_with_fallback = zincir

    rows = []
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with api_durum.islem("varlik_cikarim"):
        for n in bolumler:
            t0, i0 = time.time(), len(denemeler)
            r = (ba.aday_degerlendir if a.aday else bd.bolum_degerlendir)("shadow-slave", n, model)
            kaynak = bd.kaynak_metin("shadow-slave", n) or ""
            r["girdi_hash"] = {
                "kaynak": hashlib.sha256(kaynak.encode()).hexdigest(),
                "baglam": hashlib.sha256(chr(10).join(r.get("girdi_bilgisi") or []).encode()).hexdigest(),
                "deterministik": hashlib.sha256(chr(10).join(r.get("deterministik_bilgi") or []).encode()).hexdigest(),
                "talimat": hashlib.sha256(talimat.encode()).hexdigest(),
            }
            r["api_cagrilari"] = denemeler[i0:]
            r.setdefault("olcum", {}).update(sure_sn=round(time.time() - t0, 2),
                                            model_attempts=len(denemeler) - i0,
                                            model_retries=max(0, len(denemeler) - i0 - 1))
            if r["durum"] == "failed":
                r["provider_status"] = ("PROVIDER_BLOCKED" if r.get("hata_sinifi") == "model_api_failure"
                                        else "ERROR")
            else:
                r["provider_status"] = "SUCCESS"
            rows.append(r)
            a.out.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
            print(json.dumps({"chapter": n, "provider": r["provider_status"], "schema": r.get("sema_hatalari"),
                              "delta": r.get("model_deltasi"),
                              "counters": (r.get("degerlendirme") or {}).get("sayac")}, ensure_ascii=False), flush=True)
            if r.get("sema_hatalari") or r["provider_status"] == "ERROR":
                print("STOP: model/şema sözleşme hatası", flush=True)
                break
            if r["provider_status"] == "SUCCESS":
                assert r["olcum"]["baglam_tokeni"] <= 4000
    sonra = parmakizi(a.db)
    assert once == sonra, "korunan tablo değişti"
    assert gold_sha == sha(a.gold), "gold koşu sırasında değişti"
    ucretsiz = [d for d in denemeler if d["model"] != model]
    audit = {
        "stage": a.stage, "chapters": list(bolumler), "completed": [r["bolum"] for r in rows],
        "protected_tables_unchanged": once == sonra, "before": once, "after": sonra,
        "gold_sha256": gold_sha,
        "holdout_sha256": sha(a.holdout) if a.holdout else None,
        "provider": bd.CIKARICI_SAGLAYICI, "model": model,
        "talimat_sha256": hashlib.sha256(talimat.encode()).hexdigest(),
        "versions": surum,
        "model_chains_requested": sorted({"|".join(z) for z in zincirler}),
        "provider_attempts": denemeler, "free_gemini_calls": len(ucretsiz),
        "logical_calls": len(rows),
    }
    a.out.with_suffix(".audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = (not ucretsiz and len(rows) == len(bolumler)
          and all(r["provider_status"] != "ERROR" and not r.get("sema_hatalari") for r in rows))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
