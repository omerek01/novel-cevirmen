"""Türkçe cilalama turu (`CEVIRI_CILALA=1`): çeviriden sonra, kalite katmanından önce.

Neden ayrı tur: 2026-10-13 araştırması (Lost in Literalism, ACL 2025; Iterative
Translation Refinement, EAMT 2024) hedef dilde ayrı bir "cilalama" geçişinin çeviri
kokusunu azalttığını, aynı kuralları çeviri istemine eklemenin azaltmadığını gösterdi.
Ölçüm (`scripts/cilalama_kiyas.py`, 12 Shadow Slave bölümü, kör 2.5 Pro hakem; cilalı +
kalite katmanı : canlı): akıcılık 41-13 (p<0,001), anlam 37-26, bölüm akışı 5-0.

Güvenlik: tur ÇEVİRİYİ ASLA DÜŞÜRMEZ. Model hatası/biçimsiz yanıt → çeviri olduğu gibi;
eksik ya da aşırı kısalmış/uzamış paragraf → özgün paragraf; yeni sözlük ihlali ya da
İngilizce kalıntı getiren paragraf → özgün paragraf. Ardından kalite katmanı kaynağa
karşı denetler (anlam kayması onarılır).

2026-10-13 devralma denetimi: STOP dışındaki yanıt uygulanmaz. Aynen korunan adın
paragraftaki geçiş sayısı azalırsa o paragraf özgün kalır; yeni bulunan adlar da
korumaya girer. Türkçe karşılıkların koşulları/ekleri sayım kuralıyla tahmin edilmez.
"""
from __future__ import annotations

import json

# 3. sürüm talimat (ölçülen hâli; değiştirirsen yeniden ölç).
TALIMAT = """Sen deneyimli bir Türkçe roman editörüsün. Sana İngilizce bir web roman
bölümünün paragrafları ("en") ve her paragrafın Türkçe çevirisi ("tr") veriliyor. Görevin
çeviriyi CİLALAMAK: metni, Türkçe yazılmış bir romandan çıkmış gibi doğal kılmak. Anlam ve
bilgi BİREBİR korunur.

DÜZELT (çeviri kokan her yeri düzelt; doğal olan cümleye dokunma):
- İngilizce söz dizimini izleyen cümleler: Türkçenin doğal sırasıyla yeniden kur.
- Ekten anlaşılan gereksiz özne ve iyelik zamirleri (o, onlar, onun). Zamiri ASLA bir kişi
  adıyla değiştirme; kim olduğu belirsizleşecekse zamiri bırak.
- İngilizce "a/an" karşılığı gereksiz "bir"; "tarafından" ile kurulmuş edilgen yapılar
  (etkene çevir).
- Kalıp aktarmaları: "sahip olmak" (have), "bir şekilde" (-ly), "gibi görünüyordu" (seemed;
  çekince anlamını koru: "-mış gibiydi", "anlaşılan"), gereksiz "olarak", "Bu, ..." ile
  başlayan açıklama cümleleri.
- Yakın sözcük tekrarı, uzun ad tamlaması zincirleri, aynı bağlacın üst üste kullanımı.
- Tırnak ve kesme işaretlerinin yanlış kullanımı.

ANLAM KURALLARI (çiğnenemez):
- Kaynaktaki HER bilgi kalır: zarflar ve süre/zaman sözcükleri (suddenly, immediately, a few
  moments, now, still, already), çekinceler (seemed, perhaps, almost, probably), sayılar,
  olumsuzluk, kip ve zaman.
- Kaynakta olmayan hiçbir sözcük, ad, duygu, açıklama ya da süsleme EKLENMEZ.
- Bir sözcüğü yalnız AYNI anlamda daha doğal bir karşılıkla değiştir; yakın ama farklı
  anlamlı sözcük seçme ("bozulmak" yerine "iflas etmek", "kaynak" yerine "masraf" olmaz).
- Az bilinen deyim ya da eskimiş sözcük getirme.
- "korunacak_terimler" listesindeki karşılıklar ve özel adlar AYNEN kalır (yalnız aldıkları
  ek cümleye göre değişebilir).
- Hitap düzeyi (sen/siz) ve karakterlerin konuşma biçimi aynen kalır.
- Paragraf sayısı ve sırası aynı: her "n" tam bir kez döner; paragraf birleştirme ya da
  bölme yok.

Bitirmeden önce değiştirdiğin her cümleyi İngilizcesiyle karşılaştır: kaynaktaki bilgilerin
hepsi duruyor mu, kaynakta olmayan bir şey girdi mi? Bir değişiklik anlamı zayıflatıyorsa o
cümlede özgün çeviriyi bırak.

Yalnız JSON: {"paragraflar":[{"n":0,"tr":"..."}]}"""

# Cilalı paragraf özgünün bu oranları dışına çıkarsa içerik atlanmış ya da eklenmiş sayılır.
MIN_ORAN, MAX_ORAN = 0.6, 1.6


def korunacak_terimler(sozluk: dict, en: list[str]) -> list[str]:
    """Bölümde kaynağı geçen sözlük kayıtlarının karşılıkları (boş karşılık = İngilizce kalır)."""
    from .translate import _terim_metinde, _tekili_kayitli_cogullar

    kaynak = "\n\n".join(en)
    tekili = _tekili_kayitli_cogullar(sozluk)
    sonuc = {(v or k).strip() for k, v in (sozluk or {}).items()
             if k and _terim_metinde(k, v, kaynak, tekili)}
    return sorted(s for s in sonuc if s)


def coz(metin: str, ozgun: list[str]) -> list[str]:
    """Yanıttaki paragraflar; eksik, boş ya da boyu tutmayan paragraf özgün kalır."""
    veri = json.loads(metin)
    if isinstance(veri, list) and len(veri) == 1 and isinstance(veri[0], dict):
        veri = veri[0]
    liste = veri.get("paragraflar") if isinstance(veri, dict) else veri
    if not isinstance(liste, list):
        raise ValueError("Cilalama yanıtında paragraf listesi yok.")
    gelen = {}
    for k in liste:
        if isinstance(k, dict) and type(k.get("n")) is int and isinstance(k.get("tr"), str) and k["tr"].strip():
            gelen.setdefault(k["n"], k["tr"].strip())
    cikti = []
    for i, eski in enumerate(ozgun):
        yeni = gelen.get(i)
        oran = len(yeni) / max(1, len(eski)) if yeni else 0
        cikti.append(yeni if yeni and MIN_ORAN <= oran <= MAX_ORAN else eski)
    return cikti


def cilala(tr: list[str], en: list[str], sozluk: dict, uret, ihlaller) -> dict:
    """`tr`'yi yerinde cilalar. uret(user, system, asama) -> (yanıt, model);
    ihlaller(paragraflar) -> sözlük ihlali ya da İngilizce kalıntı taşıyan indeksler."""
    if not tr or len(tr) != len(en):
        return {"durum": "atlandi"}
    veri = {"korunacak_terimler": korunacak_terimler(sozluk, en),
            "paragraflar": [{"n": i, "en": e, "tr": t} for i, (e, t) in enumerate(zip(en, tr))]}
    try:
        yanit, model = uret(json.dumps(veri, ensure_ascii=False), TALIMAT, "cilalama")
        adaylar = getattr(yanit, "candidates", None)
        bitisler = ([getattr(a, "finish_reason", None) for a in adaylar] if adaylar
                    else [getattr(yanit, "finish_reason", None)])
        if any(str(b).split(".")[-1] != "STOP" for b in bitisler):
            raise ValueError("Cilalama tamamlanmış bir yanıt vermedi.")
        aday = coz(getattr(yanit, "text", yanit) or "", tr)
    except Exception as exc:  # tur çeviriyi asla düşürmez
        return {"durum": "cilalanamadi", "neden": type(exc).__name__}
    from .translate import _relevant_glossary, _term_regex

    # Aynen korunan adlar eski denetimde bilerek dışarıdadır. Cilalama bunları
    # zamirle değiştiremez/silemez. Sözcük içi eşleşme sayılmaz; kesmeli ek serbest.
    ilgili = _relevant_glossary(sozluk or {}, "\n\n".join(en))
    adlar = [_term_regex(k) for k, v in ilgili.items()
             if not v or k.casefold() == v.casefold()]
    ad_kaybi = {i for i, (eski, yeni) in enumerate(zip(tr, aday))
                if any(len(d.findall(yeni)) < len(d.findall(eski)) for d in adlar)}
    geri = sorted(i for i in (set(ihlaller(aday)) - set(ihlaller(tr))) | ad_kaybi
                  if aday[i] != tr[i])
    for i in geri:
        aday[i] = tr[i]
    degisen = sum(1 for a, b in zip(aday, tr) if a != b)
    tr[:] = aday
    return {"durum": "cilalandi", "model": model, "degisen": degisen, "geri_alinan": geri}
