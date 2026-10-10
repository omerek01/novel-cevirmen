"""Kaydedilmiş çeviri izlerini salt okunur gösterir; model çağırmaz."""
import argparse
import json
import sqlite3
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", type=Path, required=True)
    p.add_argument("--url", required=True)
    a = p.parse_args()
    conn = sqlite3.connect(a.db.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        rows = conn.execute("SELECT id,zaman,veri FROM ceviri_izleri WHERE url=? ORDER BY zaman DESC", (a.url,))
        print(json.dumps([{"id": r[0], "zaman": r[1], "veri": json.loads(r[2])} for r in rows],
                         ensure_ascii=False, indent=2))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
