"""Kitabın VARLIK GRAFİĞİNİ kur / raporla (bakım aracı) — `core.varlik_grafigi`.

Sistem katmanı: önbellekteki bütün bölümlerin rün mesajlarından (Shadow Slave)
deterministik bağlar. API ÇAĞIRMAZ. Varsayılan KURU çalıştırmadır.

Kullanım (proje kökünden):
    .venv\\Scripts\\python.exe scripts\\varlik_grafigi.py --kitap shadow-slave
    ... --uygula          # bağları yaz
    ... --json graph.json # graphify uyumlu düğüm/kenar dosyası (yazılı grafikten)
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK / "app"))

from core import library, varlik_grafigi  # noqa: E402


def main() -> int:
    ayristirici = argparse.ArgumentParser(description=__doc__)
    ayristirici.add_argument("--kitap", required=True)
    ayristirici.add_argument("--uygula", action="store_true", help="sistem bağlarını yaz")
    ayristirici.add_argument("--json", help="yazılı grafiği graph.json olarak dışa aktar")
    args = ayristirici.parse_args()

    slug = library.resolve_slug(args.kitap)
    if varlik_grafigi.profil(slug) is None:
        print(f"{slug}: kitap profili yok — sistem katmanı bu kitapta çalışmaz.")
    sonuc = varlik_grafigi.sistem_baglarini_cikar(slug, yaz=args.uygula)
    tekil = {b[:3] for b in sonuc["baglar"]}
    print(f"=== {slug}: {len(tekil)} tekil sistem bağı ({len(sonuc['baglar'])} geçiş)")
    for iliski, n in Counter(b[1] for b in tekil).most_common():
        print(f"  {varlik_grafigi.ILISKILER[iliski]['etiket']:20} {n}")
    if sonuc["cozulemeyen"]:
        print("\nSözlükte OLMAYAN adlar (bağ kurulamadı; sözlüğe eklenirse bir sonraki koşuda bağlanır):")
        for ad, n in sorted(sonuc["cozulemeyen"].items(), key=lambda x: -x[1]):
            print(f"  {ad}  ({n})")
    if args.uygula:
        print(f"\n{sonuc['eklenen']} yeni bağ, {sonuc['birlesen']} birleşen.")
    else:
        print("\nKURU çalıştırma — yazmak için: --uygula")
    if args.json:
        Path(args.json).write_text(
            json.dumps(varlik_grafigi.graph_json(slug), ensure_ascii=False, indent=1), encoding="utf-8"
        )
        print(f"graph.json: {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
