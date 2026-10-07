"""Faz 2A: sabit 19 bölümün yazmasız v2 doğrulaması ve denetim çıktıları.

Canlı DB'ye karşı çalışmaz: --db açıkça verilmiş ayrı SQLite kopyası olmalıdır.
Ara sonuçlar her bölümde kaydedilir; 1–100 işleme/yazma yolu çağrılmaz.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import time

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK / "app"))
BOLUMLER = (2, 15, 24, 61, 106, 162, 273, 313, 352, 360, 381, 394, 479, 555, 670, 691, 822, 848, 923)
ELLE = (15, 106, 360, 670, 691, 848)
TABLOLAR = ("chapters", "glossary", "sozluk_yazim", "varlik_bag", "varlik_deger",
            "bilgi_bas", "bilgi_inceleme", "bilgi_isleme", "bilgi_oneri")


def parmakizi(path):
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as c:
        var = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        out = {}
        for t in TABLOLAR:
            if t not in var:
                out[t] = None
                continue
            rows = sorted(json.dumps(r, ensure_ascii=False, default=str) for r in c.execute(f'SELECT * FROM "{t}"'))
            out[t] = {"rows": len(rows), "sha256": hashlib.sha256("\n".join(rows).encode()).hexdigest()}
        return out


def metrikler(rows):
    out = Counter()
    for r in rows:
        out["schema_failures"] += bool(r.get("sema_hatalari"))
        out["model_failures"] += r.get("durum") == "failed"
        d = r.get("model_deltasi") or {}
        out["raw_relationships"] += len(d.get("new_relationships") or [])
        out["identity_revelations"] += len(d.get("identity_revelations") or [])
        for tur in ("new_relationships", "new_aliases", "state_changes"):
            for x in d.get(tur) or []:
                if isinstance(x, dict):
                    out["epistemic_non_confirmed"] += x.get("durum_bilgisi") not in (None, "confirmed")
        de = r.get("degerlendirme") or {}
        out.update(de.get("sayac") or {})
        out["review_items"] += len(de.get("inceleme") or [])
        for x in de.get("oneriler") or []:
            out["accepted_relationships"] += x["tur"] == "new_relationships" and x["karar"] == "işle"
            out["accepted_aliases"] += x["tur"] == "new_aliases" and x["karar"] == "işle"
            out["accepted_state_changes"] += x["tur"] == "state_changes" and x["karar"] == "işle"
            out["evidence_failures"] += x["karar"].startswith("reddedildi:") and "kanıt" in x["karar"]
        o = r.get("olcum") or {}
        out["context_dropped"] += o.get("kesilen_satir") or 0
        for key in ("giris_tokeni", "cikis_tokeni", "dusunme_tokeni", "model_retries"):
            out[key] += o.get(key) or 0
        for s in r.get("girdi_bilgisi") or []:
            out["future_knowledge_violations"] += any(int(n) >= r["bolum"] for n in re.findall(r"(?:öğrenildi b|\(b)(\d+)", s))
    return dict(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, required=True)
    ap.add_argument("--v1", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--env", type=Path)
    ap.add_argument("--replay", action="store_true", help="Kaydedilmiş ham v2 yanıtlarını son doğrulayıcıyla tekrar denetle; API çağırmaz")
    args = ap.parse_args()
    if args.db.resolve() == (KOK / "cache" / "chapters.db").resolve():
        ap.error("Canlı DB yerine ayrı bir SQLite kopyası gerekli")
    from dotenv import load_dotenv
    if args.env:
        load_dotenv(args.env)
    os.environ["NOVEL_DB_PATH"] = str(args.db.resolve())
    from core import api_durum, bilgi_delta as bd, kullanim
    kaynaklar = {b["chapter_no"]: b["source"] for b in bd.cache.kaynak_bolumleri("shadow-slave")}
    v1 = json.loads(args.v1.read_text(encoding="utf-8"))
    assert tuple(r["bolum"] for r in v1) == BOLUMLER
    modeller = {r["olcum"]["fiili_model"] for r in v1}
    assert len(modeller) == 1
    model = modeller.pop()
    assert model.startswith("vertex/")
    bd._connect().close()  # yalnız kopyada tembel şema kurulumu
    before = parmakizi(args.db)
    eski = json.loads(args.out.read_text(encoding="utf-8")) if args.replay else []
    if args.replay:
        assert tuple(r["bolum"] for r in eski) == BOLUMLER
        initial = args.out.with_suffix(".initial.json")
        if not initial.exists():
            initial.write_text(json.dumps(eski, ensure_ascii=False, indent=1), encoding="utf-8")
    rows, calls = [], []
    asil = api_durum.istek_kaydet

    def kaydet(*a, **kw):
        calls.append({"model": a[2] if len(a) > 2 else kw.get("model"),
                      "sonuc": a[3] if len(a) > 3 else kw.get("sonuc"),
                      "kod": a[4] if len(a) > 4 else kw.get("kod"),
                      "sure_ms": a[5] if len(a) > 5 else kw.get("sure_ms")})
        return asil(*a, **kw)

    api_durum.istek_kaydet = kaydet
    args.out.parent.mkdir(parents=True, exist_ok=True)
    bas = time.time()
    with api_durum.islem("varlik_cikarim"):
        for n in BOLUMLER:
            start, nc = time.time(), len(calls)
            kayit = next((x for x in eski if x["bolum"] == n), None)
            if kayit:
                # Girdi/bağlam değişmedi: yeniden geri getirme ya da üretim yok,
                # yalnız ham yanıt son şema + doğrulayıcıdan geçer.
                veri = bd.varlik_cikarim_ayristir(kayit["ham_yanit"])
                hatalar = bd.sema_dogrula(veri) if veri is not None else ["yanıt JSON değil"]
                r = {**kayit, "model_deltasi": veri, "sema_hatalari": hatalar,
                     "degerlendirme": bd.delta_degerlendir("shadow-slave", n, veri, kaynaklar[n]) if not hatalar else None}
            else:
                r = bd.bolum_degerlendir("shadow-slave", n, model)
            o = r.setdefault("olcum", {})
            if kayit:
                r["api_cagrilari"] = kayit["api_cagrilari"]
                r["offline_validator_replay"] = True
            else:
                o["sure_sn"] = round(time.time() - start, 2)
                o["model_attempts"] = len(calls) - nc
                o["model_retries"] = max(0, o["model_attempts"] - 1)
                r["api_cagrilari"] = calls[nc:]
            rows.append(r)
            args.out.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"#{n}: {r['durum']} schema={len(r.get('sema_hatalari') or [])} "
                  f"delta={ {k:len(v) for k,v in (r.get('model_deltasi') or {}).items()} } "
                  f"sayac={(r.get('degerlendirme') or {}).get('sayac')} {o['sure_sn']}sn", flush=True)
            if r.get("hata_sinifi") == "api_schema_incompatibility":
                print("DURDU: API/şema uyumsuzluğu; kör tekrar yok", flush=True)
                break
    after = parmakizi(args.db)
    assert before == after, "Doğrulama grafiği/çeviri/inceleme verisini değiştirdi"
    sources = {str(n): kaynaklar[n] for n in ELLE}
    candidates = []
    with sqlite3.connect(args.db) as c:
        for n, source in c.execute("SELECT chapter_no, source_text FROM chapters WHERE book_slug='shadow-slave' ORDER BY chapter_no"):
            if n in BOLUMLER or not source:
                continue
            for s in re.split(r"(?<=[.!?])\s+|\n+", source):
                if re.search(r"\b(?:believed|thought|presumed|rumored|supposedly|was said to|turned out|wasn't really)\b", s, re.I):
                    candidates.append({"bolum": n, "cumle": s.strip()})
    f = kullanim.FIYAT.get(model)
    def cost(m):
        return ((m.get("giris_tokeni", 0) * f["giris"] + (m.get("cikis_tokeni", 0) + m.get("dusunme_tokeni", 0)) * f["cikis"]) / 1e6) if f else None
    v1m, v2m = metrikler(v1), metrikler(rows)
    v1m["cost_usd_estimate"], v2m["cost_usd_estimate"] = cost(v1m), cost(v2m)
    meta = {"model": model, "v1": v1m, "v2": v2m, "price_basis": f,
            "before": before, "after": after, "protected_tables_unchanged": before == after,
            "chapters": list(BOLUMLER), "completed": len(rows), "elapsed_seconds": round(time.time()-bas, 2),
            "manual_sources": sources, "epistemic_candidates": candidates}
    if args.replay:
        # V1'de şemadan düşen ham dizi öğelerini yalnız tekrar ölçümü için adlandır.
        # Bu, v1'in özgün schema/acceptance sonucunu değiştirmez; API çağırmaz.
        alanlar = {
            "new_relationships": ("ozne", "iliski", "nesne", "kanit", "durum_bilgisi", "gecerli_baslangic", "gecerli_bitis", "guven"),
            "new_aliases": ("asil", "ad", "tur", "kanit", "durum_bilgisi", "guven"),
            "state_changes": ("varlik", "anahtar", "deger", "kanit", "durum_bilgisi"),
        }
        ters = {v: k for k, v in bd.DURUM_ANAHTARLARI.items()}
        yeniden = []
        for r in v1:
            d = {k: [] for k in bd.DELTA_SEMASI}
            for tur, alan in alanlar.items():
                for x in (r.get("model_deltasi") or {}).get(tur) or []:
                    x = dict(zip(alan, x)) if isinstance(x, list) else dict(x)
                    x["guven"] = 0.9  # v1'in 'high' serbest alanı; tekrar eşleşmesi için sabit, kabul ölçümü DEĞİL
                    if any(a not in x for a in bd.DELTA_SEMASI[tur]["zorunlu"]):
                        continue
                    if tur == "state_changes":
                        x["anahtar"] = ters.get(x["anahtar"], x["anahtar"])
                    elif x.get("iliski", x.get("tur")) not in bd.varlik_grafigi.ILISKILER:
                        continue
                    d[tur].append(x)
            result = bd.delta_degerlendir("shadow-slave", r["bolum"], d, kaynaklar[r["bolum"]])
            yeniden.append({"bolum": r["bolum"], "sayac": result["sayac"], "oneriler": result["oneriler"]})
        meta["v1_duplicate_reanalysis"] = yeniden
        meta["v1_duplicate_reanalysis_totals"] = dict(sum((Counter(x["sayac"]) for x in yeniden), Counter()))
        assert before == parmakizi(args.db)
    args.out.with_suffix(".audit.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0 if len(rows) == len(BOLUMLER) else 2


if __name__ == "__main__":
    raise SystemExit(main())
