"""İnceleme listesi ve doğrulama: hız önbelleği, takma ad, durdurma (çevrimdışı).

Gerçek vaka (2026-10-09, sunucu): liste 1102 kayıtta ~10 sn hesaplanıyor, arayüz
8 sn'de ve Service Worker 4 sn'de vazgeçiyordu; Doğru/Reddet kabul edilmiyor sanıldı.
"""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

import server
from core import glossary, library, sozluk_dogrulama, sozluk_kapi

KITAP = "hiz-kitap"
KOK = Path(__file__).resolve().parents[1]


def test_agir_parca_onbellekten_gelir_silmede_yeniden_hesaplanmaz(monkeypatch):
    glossary.set_term(KITAP, "Orc Empire", "Ork İmparatorluğu")
    glossary.set_term(KITAP, "Ore Empire", "Ork İmparatorluğu")
    glossary.set_term(KITAP, "Temiz", "Temiz Karşılık")
    sayac = {"n": 0}
    asil = sozluk_kapi.ihlal_supheleri

    def say(*a, **k):
        sayac["n"] += 1
        return asil(*a, **k)

    monkeypatch.setattr(sozluk_kapi, "ihlal_supheleri", say)
    glossary._AGIR_ONBELLEK.clear()
    ilk = glossary.inceleme_listesi(KITAP)
    glossary.inceleme_listesi(KITAP)
    assert sayac["n"] == 1
    glossary.reddet(KITAP, "Temiz")  # silme: kalanların sonucu değişmez
    glossary.inceleme_listesi(KITAP)
    assert sayac["n"] == 1
    glossary.set_term(KITAP, "Orc Empire", "Ork Devleti")  # karşılık değişti: yeniden hesap
    glossary.inceleme_listesi(KITAP)
    assert sayac["n"] == 2
    assert {x["source"] for x in ilk} >= {"Orc Empire", "Ore Empire"}


def test_onaylanan_kayit_onbellekli_listeden_de_duser():
    glossary.set_term(KITAP, "Orc Empire", "Ork İmparatorluğu")
    glossary.set_term(KITAP, "Ore Empire", "Ork İmparatorluğu")
    assert "Orc Empire" in {x["source"] for x in glossary.inceleme_listesi(KITAP)}
    assert glossary.onayla(KITAP, "Orc Empire")
    assert "Orc Empire" not in {x["source"] for x in glossary.inceleme_listesi(KITAP)}


def test_karar_ucu_takma_adi_cozer():
    glossary.set_term(KITAP, "Orc Empire", "Ork İmparatorluğu")
    library.set_alias("takma-ad", KITAP)
    c = TestClient(server.app)
    r = c.post("/api/book/takma-ad/glossary/review", json={"source": "Orc Empire", "karar": "onayla"})
    assert r.status_code == 200, r.text


def test_dogrulama_durdurulabilir_ve_ilerleme_bildirir(monkeypatch):
    glossary.set_term(KITAP, "Orc Empire", "Ork İmparatorluğu")
    glossary.set_term(KITAP, "Ore Empire", "Ork İmparatorluğu")
    mesajlar = []
    sonuc = sozluk_dogrulama.kitabi_dogrula(
        KITAP, "hepsi", yaz=False, ilerleme=mesajlar.append, durdur=lambda: True
    )
    assert sonuc == []  # ilk kayıttan önce durdu: hiçbir şey hazırlanmadı, model çağrılmadı
    assert sozluk_dogrulama.durdur(KITAP) is False  # çalışan iş yoksa durdurulacak bir şey yok
    durum = sozluk_dogrulama.durum(KITAP)
    assert {"ilerleme", "durduruluyor", "calisiyor"} <= set(durum)


def test_baglam_on_elemesi_ciktiyi_degistirmez():
    bolumler = [
        {"chapter_no": 1, "source": "The Ore-Empire marched.\n\nNothing here."},
        {"chapter_no": 2, "source": "Nothing about it."},
        {"chapter_no": 3, "source": "Old ore empires fell.\n\nThe OreEmpire's gate."},
    ]
    kayit = {"source": "Ore Empire"}
    bulunan = sozluk_dogrulama.baglamlari_kur(kayit, [dict(b) for b in bolumler])
    assert [b["bolum"] for b in bulunan] == [1, 3, 3]


def test_canli_sozluk_uclari_service_worker_onbelleginden_gecmez():
    sw = (KOK / "app" / "web" / "sw.js").read_text(encoding="utf-8")
    kural = sw.index('endsWith("/glossary/review")')
    assert kural < sw.index("networkFirst(request)); // /api/books")


def test_elle_duzenlenen_kayit_hesaplanan_nedenle_de_listeden_duser():
    # Çakışma "bekliyor" değildir, hesaplanan bir nedendir; panelden kaydedilen kayıt
    # yine de incelenmiş sayılmalı (kullanıcı bildirimi, 2026-10-09).
    glossary.set_term(KITAP, "Orc Empire", "Ork İmparatorluğu")
    glossary.set_term(KITAP, "Ore Empire", "Ork İmparatorluğu")
    assert "Orc Empire" in {x["source"] for x in glossary.inceleme_listesi(KITAP)}
    glossary.terimi_yaz(KITAP, "Orc Empire", "Ork İmparatorluğu")
    assert "Orc Empire" not in {x["source"] for x in glossary.inceleme_listesi(KITAP)}


def test_yakin_ve_kalip_taramasi_her_cifti_denemekle_ayni_sonucu_verir(monkeypatch):
    # Aday elemesi (n² yerine) sunucuda 10 sn'yi kesti; sonuç ve SIRA eski tam
    # taramayla birebir aynı kalmalı.
    import random

    rnd = random.Random(7)
    harf = "aeiokğtdpbçcsr"
    kelimeler = ["".join(rnd.choice(harf) for _ in range(rnd.randint(2, 5))) for _ in range(160)]
    # Yakın yazım için AYRI liste (aşağıdaki kalıp taraması `kelimeler`i ve `rnd`yi
    # kullanır). Kısa ad sınırının (`YAKIN_MIN_UZUNLUK`) üstünde de çift olsun:
    # rastgele uzun kelimeler neredeyse hiç tek harf yakın düşmez, birkaçına tek
    # harf değişimi ya da eklemesi uygulanır.
    rnd_y = random.Random(11)
    uzunlar = ["".join(rnd_y.choice(harf) for _ in range(rnd_y.randint(7, 9))) for _ in range(40)]
    for k in uzunlar[:20]:
        i = rnd_y.randrange(len(k))
        uzunlar.append(k[:i] + rnd_y.choice(harf) + k[i + 1:])
        uzunlar.append(k[:i] + rnd_y.choice(harf) + k[i:])
    kaynaklar = list(dict.fromkeys(kelimeler + uzunlar))

    def eski_yakin(liste):
        satirlar = [(s, glossary.fold_term(s)) for s in liste]
        out = []
        for i, (a, fa) in enumerate(satirlar):
            for b, fb in satirlar[i + 1:]:
                if sozluk_kapi._tek_harf_yakin(fa, fb):
                    out.append((a, b))
        return out

    monkeypatch.setattr(glossary, "get_glossary", lambda _slug: {k: k for k in kaynaklar})
    assert glossary.yakin_terimler(KITAP) == eski_yakin(kaynaklar)
    assert glossary.yakin_terimler(KITAP)  # test gerçekten çift içeriyor

    satirlar = [{"source": f"Src{i}", "target": " ".join(rnd.sample(kelimeler, 2))} for i in range(120)]
    monkeypatch.setattr(sozluk_kapi, "ingilizce_korunan", lambda _k, _h: False)
    yeni = sozluk_kapi.kalip_tutarsizliklari(satirlar)

    # Eski davranış: komşuluk filtresi olmadan, tüm biçim çiftleri aday.
    biçimler = {}
    for r in satirlar:
        for s in r["target"].split():
            biçimler.setdefault(s.casefold().strip("'’"), []).append(r["source"])
    beklenen_ciftler = {
        (a, b) for a in biçimler for b in biçimler if a < b and sozluk_kapi._yumusama_cifti(a, b)
    }
    bulunan = {k for k, n in yeni.items() if "aynı sözcüğün iki yazımı" in n["aciklama"]}
    beklenen = set()
    for a, b in beklenen_ciftler:
        ka, kb = biçimler[a], biçimler[b]
        if len(ka) < len(kb):
            beklenen.update(ka)
        elif len(kb) < len(ka):
            beklenen.update(kb)
        else:
            beklenen.update(ka + kb)
    assert beklenen and bulunan == beklenen


def _sayan_ihlal(monkeypatch, bekle=None):
    """`ihlal_supheleri` yerine çağrı sayısını neden metnine yazan sahte hesap."""
    import time

    sayac = {"n": 0}

    def sahte(book_slug, kaynaklar=None, tam=False):
        sayac["n"] += 1
        n = sayac["n"]
        if bekle is not None:
            bekle.wait(10)
        else:
            time.sleep(0.3)  # eşzamanlı isteklerin hesabın içinde çakışması için
        return {"Orc Empire": {"tur": sozluk_kapi.IHLAL_SUPHESI, "aciklama": f"hesap {n}", "ilgili": []}}

    monkeypatch.setattr(sozluk_kapi, "ihlal_supheleri", sahte)
    glossary._AGIR_ONBELLEK.clear()
    return sayac


def _ihlal_notu(liste):
    kayit = next(x for x in liste if x["source"] == "Orc Empire")
    return [n["aciklama"] for n in kayit["nedenler"] if n["tur"] == sozluk_kapi.IHLAL_SUPHESI]


def test_ayni_anda_gelen_istekler_tek_hesap_yapar(monkeypatch):
    # Ölçüldü (sunucu, 2026-10-13): eşzamanlı 3 istek ayrı ayrı hesaplayıp 251 sn sürdü.
    import threading

    glossary.set_term(KITAP, "Orc Empire", "Ork İmparatorluğu")
    sayac = _sayan_ihlal(monkeypatch)
    sonuclar = []
    isler = [threading.Thread(target=lambda: sonuclar.append(glossary.inceleme_listesi(KITAP)))
             for _ in range(3)]
    for t in isler:
        t.start()
    for t in isler:
        t.join()
    assert sayac["n"] == 1
    assert [_ihlal_notu(x) for x in sonuclar] == [["hesap 1"]] * 3


def test_arayuz_eski_sonucu_beklemeden_alir_tazesi_arka_planda_hesaplanir(monkeypatch):
    import threading
    import time

    glossary.set_term(KITAP, "Orc Empire", "Ork İmparatorluğu")
    serbest = threading.Event()
    serbest.set()
    sayac = _sayan_ihlal(monkeypatch, bekle=serbest)
    liste, guncelleniyor = glossary.inceleme_durumu(KITAP)  # saklı sonuç yok: hesaplanır
    assert (_ihlal_notu(liste), guncelleniyor) == (["hesap 1"], False)

    serbest.clear()  # arka plan hesabı bitmesin
    # Elle düzenlenen kayıt onaylı sayılıp listeden düşer; hesabı yeni kayıt eskitir.
    glossary.set_term(KITAP, "Yeni Kayit", "Yeni Kayıt")
    baslangic = time.perf_counter()
    liste, guncelleniyor = glossary.inceleme_durumu(KITAP)
    assert time.perf_counter() - baslangic < 2
    assert (_ihlal_notu(liste), guncelleniyor) == (["hesap 1"], True)
    glossary.inceleme_durumu(KITAP)  # ikinci istek ikinci bir arka plan işi açmaz
    serbest.set()
    son = time.perf_counter() + 10
    while time.perf_counter() < son:
        liste, guncelleniyor = glossary.inceleme_durumu(KITAP)
        if not guncelleniyor:
            break
        time.sleep(0.05)
    assert (_ihlal_notu(liste), guncelleniyor) == (["hesap 2"], False)
    assert sayac["n"] == 2


def test_inceleme_ucu_guncelleniyor_bilgisini_doner():
    glossary.set_term(KITAP, "Orc Empire", "Ork İmparatorluğu")
    glossary._AGIR_ONBELLEK.clear()  # saklı sonuç yoksa uç hesabı bekler: taze döner
    r = TestClient(server.app).get(f"/api/book/{KITAP}/glossary/review")
    assert r.status_code == 200, r.text
    assert r.json()["guncelleniyor"] is False
