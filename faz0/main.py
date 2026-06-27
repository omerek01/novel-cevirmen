"""Faz 0 kanıtı: novelbin URL -> isim-koruyan Türkçe çeviri (terminal çıktısı).

Kullanım:
    python faz0/main.py "https://novelbin.me/.../chapter-1"
    python faz0/main.py "<url>" --headed   # Cloudflare engellerse görünür tarayıcı
"""
from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv

from fetch import FetchError, fetch_chapter
from translate import translate_chapter

# Windows konsolunda Türkçe karakterler (ş, ğ, ı...) için UTF-8 çıkışı zorla.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="novelbin bölümünü Türkçe'ye çevir.")
    parser.add_argument("url", help="novelbin bölüm URL'i")
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Tarayıcıyı görünür çalıştır (Cloudflare engelini aşmaya yardımcı olur)",
    )
    args = parser.parse_args()

    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key == "buraya-anahtarinizi-yazin":
        print(
            "HATA: GEMINI_API_KEY ayarlı değil. faz0/.env dosyasına anahtarınızı yazın.",
            file=sys.stderr,
        )
        return 1

    print(f"-> Bölüm çekiliyor: {args.url}")
    try:
        chapter = fetch_chapter(args.url, headless=not args.headed)
    except FetchError as exc:
        print(f"ÇEKME HATASI: {exc}", file=sys.stderr)
        return 2

    word_count = len(chapter["text"].split())
    print(f"-> Başlık: {chapter['title']}  ({word_count} kelime)")
    print("-> Çevriliyor...")
    result = translate_chapter(chapter["text"], api_key=api_key)

    print("\n" + "=" * 60)
    print(chapter["title"])
    print("=" * 60 + "\n")
    print(result["translation"])
    print("\n" + "-" * 60)
    print(f"Parça sayısı: {result['chunk_count']}")
    if result["detected_names"]:
        print(
            "Algılanan yeni isimler (sözlüğe eklenebilir): "
            + ", ".join(result["detected_names"])
        )
    print(f"Sonraki bölüm: {chapter['next_url'] or '(yok / son bölüm)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
