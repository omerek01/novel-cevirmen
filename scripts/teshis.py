"""Tek komutluk arıza teşhisi: "neden çevirmiyor" sorusunun cevabı (bakım aracı).

Bu araç iki kez ödenmiş bir dersten doğdu. 2026-09-15 ve 2026-09-21'de aynı soru
soruldu ve her ikisinde de cevap ancak ALTI-YEDİ tur komut alışverişiyle
bulunabildi — kullanıcı çoğu zaman TABLETTEN, tarayıcı içi SSH ile yazıyor ve her
tur pahalı. Daha kötüsü, ilk turda yanlış bir hipotez (3.x ailesi 404 veriyor)
kuruldu ve `kota_durum.py` çıktısı gelene kadar çürütülemedi.

Bu yüzden araç TEK ÇIKTIDA arızayı daraltan bütün ucuz göstergeleri basar:
kod sürümü · servis · ayar + ÇÖZÜLMÜŞ zincir · anahtar havuzu · son çeviriler ·
GÜNLÜK çeviri sayısı · kaynaklar. Hiçbiri tek başına teşhis değildir; birlikte
hangi dalda olduğumuzu söylerler.

API ÇAĞIRMAZ ve SALT-OKUNURDUR. Teşhis aracı arızayı büyütmemeli: kota yakan bir
yoklama, kotası dolduğu için çalışmayan bir kurulumu daha da kapatırdı. Model
erişimini gerçekten yoklamak gerekirse `kota_durum.py` ayrı bir araçtır ve küçük
de olsa GERÇEK istek atar — bu araç sonunda onu ne zaman koşturacağını söyler.

Kullanım (sunucuda):
    .venv/bin/python scripts/teshis.py
    ... --gun 14        # günlük sayımda kaç gün geriye bakılsın (varsayılan 7)
"""
from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK / "app"))

# Windows konsolu cp1252 kullanır ve Türkçe `ı`/`ş`/`ğ` orada YOK — `kota_durum.py`
# tam bu yüzden bir kez çökmüştü (2026-09-09) ve teşhis edilen arızadan çok vakit
# yaktı. Aynı hatayı burada tekrarlamıyoruz.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):  # pragma: no cover — çok eski/tuhaf konsol
    pass

from dotenv import load_dotenv  # noqa: E402


def _komut(*argv: str) -> str:
    """Komutun BAŞARILI çıktısı; yoksa/patlarsa/başarısızsa boş.

    Teşhis aracı HİÇBİR eksik yüzünden ölmemeli — `systemctl` konteynerde,
    `git` sunucuda olmayabilir. Hata çıktısı BİLEREK yutulur: `systemctl`
    systemd'siz bir kutuda iki satırlık bir yakınma basıyor ve onu "durum"
    diye ekrana yazmak teşhisi okunmaz hâle getiriyordu.
    """
    try:
        cikti = subprocess.run(
            argv, capture_output=True, text=True, timeout=10, cwd=str(KOK)
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if cikti.returncode != 0:
        # `systemctl is-active` durum "inactive"ken de sıfırdan farklı döner;
        # o bilgi DEĞERLİ, ama yalnız tek kelimelik temiz bir çıktıysa.
        ilk = (cikti.stdout or "").strip()
        return ilk if ilk and len(ilk.split()) == 1 else ""
    return (cikti.stdout or "").strip()


def _baslik(metin: str) -> None:
    print(f"\n=== {metin} " + "=" * max(0, 58 - len(metin)))


def _kod() -> None:
    _baslik("KOD")
    dal = _komut("git", "rev-parse", "--abbrev-ref", "HEAD") or "(git yok)"
    commit = _komut("git", "log", "-1", "--format=%h %ad %s", "--date=short")
    kirli = _komut("git", "status", "--porcelain")
    print(f"dal    : {dal}")
    print(f"commit : {commit or '(okunamadı)'}")
    if kirli:
        # Sunucuya elle konmuş düzeltme `git pull`da sessizce kaybolabilir;
        # görünür olması şart (CLAUDE.md'deki CRLF tuzağı da burada patlar).
        print(f"UYARI  : çalışma ağacı KİRLİ ({len(kirli.splitlines())} dosya)")


def _servis() -> None:
    _baslik("SERVİS")
    durum = _komut("systemctl", "is-active", "novel-cevirmen")
    if not durum:
        # systemd yoksa (konteyner, yerel geliştirme) "servis ölü" demek YANLIŞ
        # teşhis olurdu — bu projede yanlış teşhisin bedeli bir kez ödendi.
        print("durum  : okunamadı (systemd yok ya da yetki yetersiz)")
        return
    print(f"durum  : {durum}")
    if durum != "active":
        print("  -> Servis ayakta değil. Sebebi için:")
        print("     sudo journalctl -u novel-cevirmen -n 50 --no-pager")
        return
    # Süreç ne zamandır ayakta: çok yeniyse yakın zamanda çökmüş/yeniden başlamış
    # demektir ve bellek-içi toplu çeviri işleri o anda ölmüştür (`jobs.py`).
    baslangic = _komut(
        "systemctl", "show", "-p", "ActiveEnterTimestamp", "--value", "novel-cevirmen"
    )
    if baslangic:
        print(f"başlangıç: {baslangic}")


def _ayar_ve_zincir() -> None:
    _baslik("AYAR + ZİNCİR")
    try:
        from core import translate
    except Exception as hata:  # noqa: BLE001 — import zinciri sunucuda kırık olabilir
        print(f"translate içe aktarılamadı: {type(hata).__name__}: {hata}")
        print("  -> Bağımlılık eksik olabilir: .venv/bin/pip install -r requirements.txt")
        return

    try:
        secili = translate._ayarlar.get(
            translate.MODEL_AYAR_ANAHTARI, translate.VARSAYILAN_MODEL
        )
    except sqlite3.Error as hata:
        secili = f"(okunamadı: {hata})"
    # Zincir ÇÖZÜLMÜŞ hâliyle basılır, ayar değeriyle değil: seçim zincirin YERİNİ
    # ALMAZ, BAŞINA geçer ve bu ayrım kullanıcıyı bir kez yanılttı ("3.6 seçtim ama
    # 2.5 çeviriyor" — aslında ayar hâlâ 2.5'teydi ve zincirin başındaydı).
    print(f"seçili model : {secili}")
    print(f"ÇÖZÜLEN zincir: {' -> '.join(translate.secili_zincir())}")

    _baslik("ANAHTAR HAVUZU")
    adlar = translate.gemini_anahtar_degiskenleri()
    anahtarlar = translate.gemini_anahtarlari()
    print(f"gemini : {len(anahtarlar)} anahtar — {', '.join(adlar) or '(YOK)'}")
    if not anahtarlar:
        print("  -> Çeviri anahtarsız YAPILAMAZ. .env okunuyor mu?")
    print(f"claude : {'var (ÜCRETLİ)' if translate.claude_anahtari() else 'yok'}")


def _cevirilerin_hareketi(gun: int) -> None:
    from core import db

    yol = db.db_path()
    _baslik("ÇEVİRİ HAREKETİ")
    if not yol.exists():
        print(f"DB YOK: {yol}")
        return
    print(f"db     : {yol}")
    try:
        conn = sqlite3.connect(f"file:{yol}?mode=ro", uri=True)
    except sqlite3.Error as hata:
        print(f"DB açılamadı: {hata}")
        return
    try:
        try:
            toplam = conn.execute(
                "SELECT COUNT(*) FROM chapters WHERE translation IS NOT NULL"
            ).fetchone()[0]
        except sqlite3.Error as hata:
            # Tablo yoksa DB ya boş ya da YANLIŞ dosya. İkisi de teşhis açısından
            # değerli bilgi; araç burada ÇÖKMEMELİ — geri kalan bölümler
            # (kaynaklar, yön) hâlâ basılmalı. `kota_durum.py` bir kez tam bu
            # sınıf hatadan öldü ve kalan anahtarlar hiç yoklanmadı.
            print(f"chapters tablosu okunamadı: {hata}")
            print("  -> DB boş ya da yanlış dosya. NOVEL_DB_PATH ayarlı mı?")
            return
        print(f"toplam çevrilmiş bölüm: {toplam}")

        # GÜNLÜK SAYIM load-bearing: ücretsiz kota model başına 20 istek/GÜN/PROJE
        # ve bir bölüm 1-2 istek (+ onarım turları). Yani "bugün kaç bölüm çevrildi"
        # kotaya ne kadar yaklaşıldığını söyleyen TEK ucuz göstergedir — API
        # çağırmadan. Kota Pasifik gece yarısı sıfırlanır; sayım YEREL güne göre
        # yapıldığı için bire bir örtüşmez, büyüklük sırası için yeterlidir.
        satirlar = conn.execute(
            "SELECT created_at, model FROM chapters "
            "WHERE translation IS NOT NULL AND created_at IS NOT NULL"
        ).fetchall()
        gunluk: Counter = Counter()
        gunluk_model: dict[str, Counter] = {}
        for ts, model in satirlar:
            try:
                g = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
            except (OverflowError, OSError, ValueError, TypeError):
                continue
            gunluk[g] += 1
            gunluk_model.setdefault(g, Counter())[model or "(künyesiz)"] += 1

        print(f"\nson {gun} günde çevrilen bölüm:")
        if not gunluk:
            print("  (tarihli kayıt yok)")
        for g in sorted(gunluk, reverse=True)[:gun]:
            dagilim = ", ".join(
                f"{m}={n}" for m, n in gunluk_model[g].most_common()
            )
            print(f"  {g}  {gunluk[g]:4}  [{dagilim}]")

        print("\nson 12 çeviri:")
        son = conn.execute(
            "SELECT created_at, model, book_slug, chapter_no FROM chapters "
            "WHERE translation IS NOT NULL ORDER BY created_at DESC LIMIT 12"
        ).fetchall()
        for ts, model, slug, no in son:
            try:
                t = datetime.fromtimestamp(ts).strftime("%m-%d %H:%M")
            except (OverflowError, OSError, ValueError, TypeError):
                t = "??-?? ??:??"
            print(f"  {t}  {(model or '(künyesiz)'):20} {(slug or '?')[:28]:28} #{no}")
    finally:
        conn.close()


def _kaynaklar() -> None:
    _baslik("KAYNAKLAR")
    # e2-micro'nun 1 GB RAM'i var ve Python süreci + SQLite orada rahat değil.
    # Bellek tükenmesi (OOM) servisi ÖLDÜRÜR ve arıza "çevirmiyor" kılığına girer.
    try:
        kullanim = shutil.disk_usage(KOK)
        bos_gb = kullanim.free / 1024**3
        print(f"disk   : {bos_gb:.1f} GB boş / {kullanim.total / 1024**3:.1f} GB")
        if bos_gb < 1.0:
            print("  -> DİSK DOLMAK ÜZERE. SQLite yazamazsa çeviri kaydedilemez.")
    except OSError as hata:
        print(f"disk okunamadı: {hata}")
    try:
        bilgi = dict(
            (p[0].rstrip(":"), p[1])
            for p in (s.split() for s in Path("/proc/meminfo").read_text().splitlines())
            if len(p) >= 2
        )
        toplam = int(bilgi.get("MemTotal", 0)) / 1024
        musait = int(bilgi.get("MemAvailable", 0)) / 1024
        print(f"bellek : {musait:.0f} MB müsait / {toplam:.0f} MB")
        if toplam and musait / toplam < 0.10:
            print("  -> BELLEK DARALDI. OOM servisi öldürebilir (e2-micro 1 GB).")
    except (OSError, ValueError):
        pass


def _yon() -> None:
    _baslik("SIRADAKİ ADIM")
    print("Yukarıdaki tabloya göre:")
    print("  servis active DEĞİL       -> journalctl (yukarıda yazılı komut)")
    print("  bugün çeviri sayısı YÜKSEK-> kota; .venv/bin/python scripts/kota_durum.py")
    print("  anahtar sayısı 0          -> .env okunmuyor")
    print("  zincir beklediğin gibi DEĞİL -> ayar; POST /api/settings/model")
    print("  hepsi normal görünüyor    -> hata METNİ lazım:")
    print("     sudo journalctl -u novel-cevirmen --since '2 hours ago' --no-pager \\")
    print("       | grep -iE 'error|hata|429|503|404|Traceback' | tail -40")


def main() -> int:
    ayristirici = argparse.ArgumentParser(description=__doc__)
    ayristirici.add_argument("--gun", type=int, default=7,
                             help="günlük sayımda kaç gün geriye bakılsın")
    a = ayristirici.parse_args()

    load_dotenv(KOK / ".env")
    print(f"novel-cevirmen teşhis — {datetime.now():%Y-%m-%d %H:%M} yerel saat")
    _kod()
    _servis()
    _ayar_ve_zincir()
    _cevirilerin_hareketi(a.gun)
    _kaynaklar()
    _yon()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
