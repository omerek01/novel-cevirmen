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
    kaynaklar = list(dict.fromkeys(kelimeler))

    def eski_yakin(liste):
        satirlar = [(s, glossary.fold_term(s)) for s in liste]
        out = []
        for i, (a, fa) in enumerate(satirlar):
            for b, fb in satirlar[i + 1:]:
                yer = glossary._fark_yeri(fa, fb)
                if not yer or glossary._cogul_cifti(fa, fb):
                    continue
                if fa[yer[0]:yer[0] + 1].isdigit() or fb[yer[0]:yer[0] + 1].isdigit():
                    continue
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
