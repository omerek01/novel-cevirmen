"""Sözlükte OLMAYAN ama çevirilerde farklı karşılıklarla yerleşen terimleri bul (bakım aracı).

Neden var (2026-10-16, Faz A8): uyum denetimleri yalnız KAYITLI terimleri görür. Kaydı
olmayan terimde model her bölümde yeniden karar verir ve aynı unvan bölümden bölüme
başka çevrilebilir (ölçülen vaka, SS: `Captain` -> Yüzbaşı 35 / Kaptan 4). Yöntem ve
eşikler `core.sozluk_kayma`da.

API ÇAĞIRMAZ. Varsayılan KURU çalıştırmadır (yalnız rapor).

Kullanım (proje kökünden):
    .venv\\Scripts\\python.exe scripts\\sozluk_kayma.py --kitap shadow-slave
    ... --uygula      # en sık TÜRKÇE karşılığı otomatik aday olarak sözlüğe yaz
    ... --json r.json

`--uygula` kuralı DOĞRUDAN yazmaz: aday `merge_terms(..., "auto")` ile yazma kapısından ve
bekleme + model doğrulamasından geçer, inceleme listesine düşer; kararı kullanıcı verir.
En sık karşılığı İngilizce olan terim yazılmaz (bir İngilizce-korunan karar kişi adı
kuralına dokunur; kullanıcıya bırakılır), yalnız raporlanır.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK / "app"))

from core import cache, glossary, library, sozluk_kayma  # noqa: E402

INGILIZCE = "(İngilizce)"


def tara(kitap: str) -> list[dict]:
    onbellek: dict[int, dict] = {}

    def soz(no):
        if no not in onbellek:
            onbellek[no] = glossary.bolumdeki_sozluk(kitap, no)
        return onbellek[no]

    def akis():
        for b in cache.denetim_bolumleri(kitap):
            tp = [p for p in b["translation"].split("\n\n") if p.strip()]
            sp = [p for p in b["source"].split("\n\n") if p.strip()]
            if len(tp) == len(sp):
                for en, tr in zip(sp, tp):
                    yield b["chapter_no"], en, tr

    return sozluk_kayma.kaymalar(akis(), soz)


def oneriler(kaymalar: list[dict], sozluk: dict[str, str]) -> dict[str, str]:
    """{kaynak: en sık Türkçe karşılık} — İngilizce önde olan ve zaten kayıtlı terim hariç."""
    kayitli = {glossary.fold_term(s) for s in sozluk}
    out = {}
    for x in kaymalar:
        ilk = x["karsiliklar"][0]["karsilik"]
        if ilk != INGILIZCE and glossary.fold_term(x["kaynak"]) not in kayitli:
            out[x["kaynak"]] = ilk
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--kitap", required=True)
    ap.add_argument("--uygula", action="store_true", help="önerileri otomatik aday olarak yaz")
    ap.add_argument("--json", help="raporu bu dosyaya yaz")
    a = ap.parse_args()
    kitap = library.resolve_slug(a.kitap)
    sonuc = tara(kitap)
    oner = oneriler(sonuc, glossary.get_glossary(kitap))
    print(f"{kitap}: kayan terim {len(sonuc)}, yazılabilir öneri {len(oner)}")
    for x in sonuc:
        dagilim = ", ".join(f"{k['karsilik']}={k['sayi']}" for k in x["karsiliklar"])
        isaret = " -> ÖNERİ: " + oner[x["kaynak"]] if x["kaynak"] in oner else ""
        print(f"  {x['kaynak']} | {x['gecis']} geçiş, {x['bolum']} bölüm | {dagilim}{isaret}")
    if a.json:
        Path(a.json).write_text(json.dumps({"kitap": kitap, "kaymalar": sonuc, "oneriler": oner},
                                           ensure_ascii=False, indent=2), encoding="utf-8")
    if a.uygula and oner:
        yazilan = glossary.merge_terms(kitap, oner, "auto")
        print(f"yazıldı (inceleme bekliyor): {len(yazilan)}")
    elif not a.uygula:
        print("KURU çalıştırma: sözlüğe yazılmadı (--uygula ile yazılır).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
