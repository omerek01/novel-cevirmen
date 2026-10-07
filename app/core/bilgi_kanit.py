"""Faz 2A semantik kanıt kapısı: saf/deterministik, LLM ve grafik yazımı YOK.

Yönün bilinmemesi kabul değildir. Simetrik ilişkiler rol/yön kapısını atlar.
Rün kanıtı yalnız mevcut `sistem_baglarini_bul` çıktısıyla doğrulanır.
"""
from __future__ import annotations

import re
from . import translate, varlik_grafigi as vg, varlik_cikarim as vc


def span_gecerli(kanit: str, kaynak: str) -> bool:
    # İnceleme için sınırlı gerçek span; normal düzyazıda ad şartı hâlâ var.
    k = vc._normal(kanit)
    return 8 <= len(k) <= 1400 and k in vc._normal(kaynak)


def review_span_gecerli(kanit: str, kaynak: str) -> bool:
    """One contiguous excerpt, bounded for dialogue punctuation as well as prose."""
    if not span_gecerli(kanit,kaynak) or len(kanit)>900:
        return False
    boundaries=re.findall(r"(?<![.!?])[.!?](?![.!?])(?:['’\"”])?(?=\s|$)",kanit)
    return len(boundaries)<=6


def isaretle(kanit: str, ozne: str, nesne: str, yazimlar: dict, kucult: bool = True) -> str | None:
    adaylar = [(ad, etiket, ad == isim) for isim, etiket in ((ozne, "SUBJECT"), (nesne, "OBJECT"))
               for ad in (isim, *(yazimlar.get(isim) or [])) if ad]
    bulunan = []
    for ad, etiket, _canonical in sorted(adaylar, key=lambda x: (not x[2], -len(x[0]))):
        for m in translate._term_regex(ad).finditer(kanit):
            if not any(m.start() < b and m.end() > a for a, b, _ in bulunan):
                bulunan.append((m.start(), m.end(), etiket))
    if {e for _, _, e in bulunan} != {"SUBJECT", "OBJECT"}:
        return None
    s = kanit
    for a, b, e in sorted(bulunan, reverse=True):
        s = s[:a] + e + s[b:]
    return vc._normal(s).casefold() if kucult else vc._normal(s)


def epistemik_kontrol(kanit: str, durum: str | None) -> str | None:
    k = vc._normal(kanit).casefold()
    yanlis = bool(re.search(r"mistakenly|falsely|wrongly believed|was not actually|wasn't really", k))
    kolektif = bool(re.search(r"(?:people|many|some|everyone|among the people|it is|it was).{0,45}\b(?:believ|thought|assum)|according to (?:the )?common belief|(?:widely|generally) (?:believed|assumed)|\b(?:supposedly|is supposed to|rumou?rs?|rumou?red|was said to)\b", k))
    suphe = kolektif or bool(re.search(r"\b(?:maybe|perhaps|might|suspect\w*|uncertain|not (?:quite )?sure|think|thought|believ\w*|supposed\w*)\b", k))
    if durum == "confirmed" and (kolektif or suphe):
        return "epistemik:kanıt kesin bilgi değil"
    if durum in ("believed", "rumor") and not kolektif:
        return "epistemik:yalnız karakter inancı ya da kaynakta epistemik işaret yok"
    if durum == "rumor" and not re.search(r"rumou?r|hearsay|was said to|stories|tales", k):
        return "epistemik:söylenti kanıtı yok"
    if durum == "uncertain" and not suphe:
        return "epistemik:belirsizlik kanıtı yok"
    if durum == "disproven" and not yanlis:
        return "epistemik:çürütme kanıtı yok"
    if durum == "deception" and not re.search(r"lie[ds]?|deceiv|deception|deliberately false", k):
        return "epistemik:aldatma kanıtı yok"
    if yanlis and durum not in ("disproven", "deception"):
        return "epistemik:anlatı bu inancı yanlış olarak kuruyor"
    return None


# Kanonik S→O rol örüntüleri. İlişki listesi ILISKILER'de kalır; bu kapı yeni tür üretmez.
ORUNTULER = {
    "ogretmeni": (r"object.{0,45}\b(?:taught|teaches|teaching|trained|instructed|mentored|mentors)\b(?!\s+by).{0,35}subject",
                   r"subject.{0,40}\b(?:was|were|had been|is|are)\s+(?:taught|trained|mentored|instructed)\s+by\b.{0,40}object",
                   r"subject.{0,180}object.{0,25}\b(?:taught|trained|mentored) (?:him|her|them)\b",
                   r"subject.{0,30}(?:learned|learnt|trained).{0,25}(?:from|under|by) object",
                   r"object.{0,25}(?:was|is).{0,12}subject(?:['’]s)? (?:teacher|mentor)"),
    "lideri": (r"object.{0,30}(?:leader|commander|captain).{0,20}(?:of|for) (?:the )?subject",
               r"subject['’]s.{0,10}(?:leader|commander).{0,10}object",
               r"object.{0,25}\b(?:led|leads|commanded|commands)\b(?!\s+by).{0,15}subject",
               # Edilgen: "Y was led by X" / "under the command of X" (aynı liderlik ailesi)
               r"subject.{0,60}\b(?:was|were|is|are|been|being)\s+(?:led|commanded|ruled|headed)\s+by\b.{0,60}object",
               r"subject.{0,40}\bunder (?:the )?(?:command|leadership) of\b.{0,30}object"),
    "klani": (r"subject.{0,35}(?:of|joined|belongs? to|member of).{0,12}object",),
    "grubu": (r"subject.{0,35}(?:joined|member of|belongs? to|part of|vassal.{0,15}to).{0,20}object",),
    "bulundugu_yer": (),  # `konum_kaniti` (kelime sınırlı, cümlecik korumalı; düz regex değil)
    "parcasi": (r"subject.{0,35}\b(?:part of|inside|within|in)\b.{0,15}object",),
    "oldurdu": (r"subject.{0,35}\b(?:killed|slew|slain|murdered|executed)\b.{0,25}object",
                 r"object.{0,25}(?:was|had been) (?:killed|slain|murdered|executed) by subject"),
    "takma_adi": (r"subject.{0,40}(?:called|known as|nicknamed|nickname).{0,15}object",),
    "unvani": (r"subject\s*[,—–-]\s*(?:the )?object", r"subject.{0,40}(?:title|known as|called).{0,15}object",
               r"object.{0,120}(?:called|named|known as).{0,15}subject", r"\bobject\s+subject\b"),
    "gercek_adi": (r"subject.{0,45}\btrue names?\b.{0,25}object", r"subject['’]s true names?.{0,20}object"),
    "turu": (r"subject.{0,35}(?:is|was|as|became|type of).{0,15}object",),
    "rutbesi": (r"\bobject\s+subject\b", r"subject.{0,30}(?:rank|ranked|became|is|was).{0,12}object"),
    "sinifi": (r"subject.{0,30}(?:class|became|is|was).{0,15}object",),
    "esya_turu": (r"subject.{0,30}(?:type|is|was).{0,15}object",),
    "ust_basamak": (r"subject.{0,35}(?:evolve|advance|ascend|higher).{0,25}object",),
    "donustu": (r"subject.{0,35}(?:transformed|evolved|turned|became).{0,25}object",),
    "bicimi": (r"subject.{0,30}(?:form|shape|became).{0,15}object",),
}
for _r in ("anisi", "golgesi", "kendi_golgesi", "yanki", "yetenegi", "efsunu", "niteligi", "gorunusu", "kusuru", "ruya_capasi"):
    ORUNTULER[_r] = (r"subject.{0,30}(?:has|had|owns|owned|possess\w*|acquired|received|master of).{0,20}object",
                     r"subject['’]s.{0,20}object", r"object.{0,30}(?:belongs? to|owned by|master.{0,10}is).{0,15}subject")
# KONUM (v6 genellik temizliği): ipucu TAM KELİME olarak aranır (`remained` içindeki "in"
# eşleşmez), ipucu yeri DOĞRUDAN önler (yalnız belirteç araya girebilir) ve özne ile ipucu
# AYNI cümlecikte durur. Kurulamayan konum kabul edilmez (ret/inceleme).
KONUM_IPUCU = (r"(?:in|inside|into|at|within|on|onto|entered|reached|arrived\s+(?:at|in)|"
               r"(?:lived|living|lives|resided|resides|remained|stayed|stood|located|situated)\s+(?:in|at|on|within|inside))")
# Özne ile ipucu arasında görülürse bağ kurulmaz: yeni cümlecik/özne ya da konum DIŞI "in".
_KONUM_ARA_YASAK = re.compile(
    r"\b(?:who|whom|whose|which|that|where|while|when|whereas|because|but|and|or|nor|if|"
    r"believ\w*|interest\w*|faith|trust\w*|hope\w*|involv\w*|engag\w*|particip\w*|"
    r"includ\w*|succeed\w*|fail\w*|lost|saw|see\w*|watch\w*|look\w*|heard|told|said|"
    r"thought|think\w*|remember\w*|dream\w*|imagin\w*)\b", re.I)
# Sıfır genişlikli: aynı özne birden çok geçtiğinde HER geçiş ayrı denenir.
_KONUM_ANA = re.compile(
    rf"(?=\bSUBJECT\b(?P<ara>[^.!?;:,\n]{{0,60}}?)\b{KONUM_IPUCU}\s+(?:(?:the|a|an)\s+)?OBJECT\b)", re.I)
_KONUM_YER = (
    # "the Silver Tower, where Arden lived" / "the citadel, home of the Arden clan"
    re.compile(r"\bOBJECT\b[^.!?;]{0,50}\bwhere\s+(?:the\s+)?SUBJECT\b", re.I),
    re.compile(r"\bOBJECT\b[^.!?;]{0,10}\bhome\s+(?:of|to)\s+(?:the\s+)?SUBJECT\b", re.I),
    # Artgönderim: önceki cümlenin konusu yer; sonraki cümlede özne onun "içinde" (its/their).
    re.compile(r"(?:^|[.!?][\"'’”]?\s+)(?:the\s+)?OBJECT\b[^.!?]{0,200}[.!?][\"'’”]?\s+[^.!?]{0,80}?\bSUBJECT\b"
               r"[^.!?;,]{0,40}?\b(?:stood|lay|rested|sat|was|were|lived|located|situated)\b[^.!?;,]{0,15}?"
               r"\b(?:in|at|within)\s+(?:its|their)\s+(?:middle|center|centre|heart|midst|depths|core)\b", re.I),
)


def konum_kaniti(isaretli: str) -> bool:
    """`isaretli`: büyük/küçük harfi korunmuş, adları SUBJECT/OBJECT ile değiştirilmiş kanıt."""
    for m in _KONUM_ANA.finditer(isaretli):
        ara = m.group("ara")
        # Araya giren büyük harfli sözcük başka bir varlıktır (konum ona ait olabilir).
        if re.search(r"\b[A-Z]", ara) or _KONUM_ARA_YASAK.search(ara):
            continue
        return True
    return any(p.search(isaretli) for p in _KONUM_YER)


# ---------------------------------------------------------------------------
# v6 SINIRLI ZAMİR ÇÖZÜMÜ. Kanıt değişmez (model alıntısı birebir kalır); doğrulayıcı
# yalnız İÇ bağlam kurar: aynı paragrafta, hemen önceki TEK cümle, cümle BAŞINDAKİ özne
# zamiri, önceki cümlede TEK adlandırılmış aday ve o aday beklenen uç noktayla aynı.
# Cinsiyet addan TAHMİN EDİLMEZ; iyelik zamirleri (his/her/its/their) çözülmez.
# Herhangi bir belirsizlik -> None (otomatik kabul YOK).
# ---------------------------------------------------------------------------
ZAMIRLER = ("he", "she", "it", "they")
_ZAMIR_BASI = re.compile(r"^[\"'“‘]?(He|She|It|They)\b(?!['’])", re.I)
_CUMLE_SONU = re.compile(r"(?<=[.!?])[\"'”’]?\s+(?=[\"'“‘]?[A-Z])")
# Cümle başında büyük harfle yazılan sıradan sözcükler (ad sayılmaz).
_CUMLE_BASI_SIRADAN = frozenset("""a an the but and or so then yet still however finally suddenly soon later now
meanwhile instead even only in on at as with without of for from to by into after before when while once if
although though because since despite there here this that these those it he she they we you i his her its
their our my your somehow luckily unfortunately perhaps maybe indeed of course again also just what why how
where who which no not yes well oh ah nevertheless therefore thus moreover besides otherwise""".split())
_AD_DIZISI = re.compile(r"[A-Z][\w’'\-]*(?:\s+(?:of\s+(?:the\s+)?)?[A-Z][\w’'\-]*)*")


def _cumleler(paragraf: str) -> list[tuple[int, int]]:
    sinir, bas = [], 0
    for m in _CUMLE_SONU.finditer(paragraf):
        sinir.append((bas, m.start()))
        bas = m.end()
    sinir.append((bas, len(paragraf)))
    return sinir


def _adlandirilmis(cumle: str) -> list[str]:
    """Cümledeki ad dizileri; baştaki sıradan büyük harfli sözcükler ('The', 'Finally') atılır."""
    adlar = []
    for m in _AD_DIZISI.finditer(cumle):
        parcalar = m.group(0).split()
        while parcalar and parcalar[0].casefold() in _CUMLE_BASI_SIRADAN:
            parcalar.pop(0)
        if parcalar:
            adlar.append(" ".join(parcalar))
    return adlar


def _ad_esit(a: str, adlar: tuple[str, ...]) -> bool:
    na = vc._normal(a).casefold()
    return any(na == vc._normal(n).casefold() for n in adlar if n)


def zamir_baglami(kanit: str, kaynak: str, ad: str, yazimlar: dict) -> str | None:
    """`kanit` içindeki cümle başı özne zamirini `ad` ile değiştirilmiş İÇ metin, ya da None.

    Kurallar (hepsi şart): kanıt tek paragrafta birebir · zamir, kanıtın ilk cümlesinin
    BAŞINDA ve özne · öncül, AYNI paragrafta hemen önceki cümle · o cümlede TEK
    adlandırılmış aday · aday `ad` (ya da yazımları) ile aynı."""
    nk = vc._normal(kanit)
    if not nk:
        return None
    for paragraf in (vc._normal(p) for p in (kaynak or "").split("\n")):
        i = paragraf.find(nk)
        if i < 0:
            continue
        cumleler = _cumleler(paragraf)
        sira = next((j for j, (a, b) in enumerate(cumleler) if a <= i < max(b, a + 1)), None)
        if sira is None or sira == 0:
            return None  # paragrafın ilk cümlesi: öncül paragraf DIŞINDA olurdu
        a, b = cumleler[sira]
        if i != a:
            return None  # zamir kanıtın başında, cümlenin başında olmalı
        z = _ZAMIR_BASI.match(nk)
        if not z:
            return None
        onceki = paragraf[cumleler[sira - 1][0]:cumleler[sira - 1][1]]
        adaylar = list(dict.fromkeys(_adlandirilmis(onceki)))
        if len(adaylar) != 1 or not _ad_esit(adaylar[0], (ad, *(yazimlar.get(ad) or []))):
            return None
        bas = z.group(0)
        tirnak = bas[:-len(z.group(1))]
        return tirnak + ad + nk[len(bas):]
    return None


def _zamirli(k: str, kaynak: str | None, s: str, o: str, yazimlar: dict) -> str | None:
    """Uçlardan YALNIZ biri kanıtta adla geçmiyorsa onu zamirden çözmeyi dener."""
    if not kaynak:
        return None
    s_var = vc._gecer_mi(s, yazimlar.get(s) or [], k)
    o_var = vc._gecer_mi(o, yazimlar.get(o) or [], k)
    if s_var == o_var:
        return None
    return zamir_baglami(k, kaynak, o if s_var else s, yazimlar)


_GERCEK_AD = re.compile(r"\btrue names?\b", re.I)
_GERCEK_AD_COGUL = re.compile(r"\btrue names\b", re.I)
_DIGER_AD_DISI = frozenset(("true", "name", "names", "subject", "object"))


def coklu_gercek_ad_belirsiz(harfli: str) -> bool:
    """Çoğul 'True Names' + işaretli uçlar dışında başka ad varsa eşleme metinde kurulmamıştır
    (sıraya bakarak 'A->X, B->Y' TAHMİNİ yapılmaz)."""
    if not _GERCEK_AD_COGUL.search(harfli):
        return False
    for cumle in (harfli[a:b] for a, b in _cumleler(harfli)):
        for ad in _adlandirilmis(cumle):
            if not all(t.casefold() in _DIGER_AD_DISI for t in ad.split()):
                return True
    return False


def transfer_kaniti(kanit: str, new_holder: str, entity: str, yazimlar: dict) -> bool:
    """Recipient/item roles only; giving/entrusting does NOT establish mastership."""
    marker = isaretle(kanit, new_holder, entity, yazimlar)
    if not marker or re.search(r"\b(?:might|would|if|unless|never)\b|did not (?:give|hand|entrust)", marker):
        return False
    patterns = (r"(?:gave|given|gift\w*|handed|entrusted).{0,55}object.{0,25}(?:to|with) subject",
                r"object.{0,100}(?:gift\w*|given|handed|entrusted).{0,20}(?:to|with) subject",
                r"object.{0,25}(?:now belongs to|was given to|was entrusted to) subject")
    return any(re.search(p, marker, re.S) for p in patterns)


def rupture_kaniti(kanit: str, a: str, b: str, yazimlar: dict) -> bool:
    marker = isaretle(kanit, a, b, yazimlar)
    if not marker or re.search(r"(?:might|would|if|unless).{0,15}betray|never betrayed|did not betray", marker):
        return False
    return bool(re.search(r"\b(?:betrayed|betrayal)\b|trust.{0,20}(?:broken|destroyed)|friendship.{0,30}(?:ended|broken|over)|(?:cannot|can't|can not) forgive|(?:hope|want|wish).{0,25}never see (?:you|subject|object) again", marker))


def semantik_sonuc(x: dict, yazimlar: dict, deterministik: list[tuple] = (),
                   kaynak: str | None = None) -> tuple[str, str]:
    """verified / wrong / unknown. Kaynağın birebirliği çağıranda denetlenir."""
    r, s, o, k = x["iliski"], x["ozne"], x["nesne"], x.get("kanit") or ""
    for a, il, b, evidence in deterministik:
        same_s = any(vc._normal(a).casefold() == vc._normal(n).casefold() for n in (s, *yazimlar.get(s, [])))
        same_o = any(vc._normal(b).casefold() == vc._normal(n).casefold() for n in (o, *yazimlar.get(o, [])))
        if il == r and same_s and same_o and len(vc._normal(k)) >= 8 and vc._normal(k) in vc._normal(evidence):
            return "verified", "system_block"
    if r == "gercek_adi" and not _GERCEK_AD.search(k):
        return "wrong", "ordinary_name_is_not_true_name"
    if r == "gercek_adi" and re.search(r"not.{0,15}true names?|no true names?|never.{0,15}true names?", k, re.I):
        return "wrong", "true_name_not_established"
    marker = isaretle(k, s, o, yazimlar)
    if marker is None:
        zk = _zamirli(k, kaynak, s, o, yazimlar)
        if zk is not None:
            return semantik_sonuc({**x, "kanit": zk}, yazimlar, deterministik)
        return "wrong", "entity_name_missing"
    if r == "gercek_adi" and coklu_gercek_ad_belirsiz(isaretle(k, s, o, yazimlar, kucult=False)):
        return "unknown", "plural_true_name_mapping_ambiguous"
    if r in ("golgesi", "anisi", "yanki", "grubu", "yoldasi") and transfer_kaniti(k, s, o, yazimlar):
        return "unknown", "MISSING_RELATION_CAPABILITY"
    if re.search(r"\b(?:not|never|could|would|might|if|unless|attempted|tried|failed)\b", marker) and r in ("oldurdu", "donustu"):
        return "wrong", "high_impact_evidence_missing"
    if vg.ILISKILER[r]["symmetric"]:
        words = {"yoldasi": r"companion|friend|ally|allies|comrade|cohort", "akrabasi": r"brother|sister|father|mother|son|daughter|relative|sibling", "dusmani": r"enemy|enemies|nemesis|foe"}
        if re.search(words[r], marker) and not re.search(r"\b(?:not|never)\b", marker):
            return "verified", "symmetric"
        return "unknown", "symmetric_claim_not_established"
    if r == "bulundugu_yer":
        harfli = isaretle(k, s, o, yazimlar, kucult=False)
        if konum_kaniti(harfli):
            return "verified", "semantic_roles"
        if konum_kaniti(harfli.replace("SUBJECT", "@@@").replace("OBJECT", "SUBJECT").replace("@@@", "OBJECT")):
            return "wrong", "direction_reversed"
        return "unknown", "direction_not_established"
    patterns = ORUNTULER.get(r, ())
    if any(re.search(p, marker, re.S) for p in patterns):
        return "verified", "semantic_roles"
    reverse = marker.replace("subject", "@@@").replace("object", "subject").replace("@@@", "object")
    if any(re.search(p, reverse, re.S) for p in patterns):
        return "wrong", "direction_reversed"
    if vg.ILISKILER[r]["requires_strong_evidence"]:
        return "wrong", "high_impact_evidence_missing"
    return "unknown", "direction_not_established"


def rol_kaniti(varlik: str, deger: str, kanit: str, yazimlar: dict) -> bool:
    """Açık rol: 'X was/served as (the) V' ya da unvan biçimi 'V X' (Instructor X).
    Özne ve değer AYNI cümlede, aralarında yalnız bu kalıp."""
    adlar = (varlik, *(yazimlar.get(varlik) or []))
    name = "(?:" + "|".join(re.escape(n) for n in adlar if n) + ")"
    v = re.escape(deger.strip())
    return bool(re.search(
        rf"\b{name}\b\s+(?:is|was|served as|acted as|worked as|became)\s+(?:(?:the|a|an|their|his|her)\s+)?(?:\w+\s+)?{v}\b"
        rf"|\b{v}\s+{name}\b", kanit, re.I))


def state_kaniti(x: dict, kaynak: str, yazimlar: dict, deterministik: list[tuple]) -> tuple[bool, str]:
    key = x["anahtar"]
    value = x["deger"]
    k = x.get("kanit") or ""
    if not span_gecerli(k, kaynak):
        return False, "state_evidence_not_verbatim"
    for s, r, o, e in deterministik:
        if r == vg.DEGER and s in (x["varlik"], *(yazimlar.get(x["varlik"]) or [])) and o == f"{key}\t{value}" and vc._normal(k) == vc._normal(e):
            return True, "system_block"
    if not vc._gecer_mi(x["varlik"], yazimlar.get(x["varlik"]) or [], k):
        zk = zamir_baglami(k, kaynak, x["varlik"], yazimlar)
        if zk is None:
            return False, "state_subject_missing"
        k = zk  # iç bağlam: zamir öncülüyle değiştirildi; birebirlik yukarıda denetlendi
    if epistemik_kontrol(k, x.get("durum_bilgisi")):
        return False, "state_epistemic_mismatch"
    if x.get("makine_anahtari") == "life_status" or key == "Yaşam":
        if re.search(r"\b(?:not alive|never died|would die|might die|could die|never survived|not survive|might survive|would survive)\b", k, re.I):
            return False, "life_status_not_established"
        adlar = (x["varlik"], *(yazimlar.get(x["varlik"]) or []))
        # Kısaltılmış ad yalnız aynı span'da TAM ad varsa; yeni kimlik çözümü değil.
        if " " in x["varlik"]:
            adlar += (x["varlik"].split()[-1],)
        name = "(?:" + "|".join(re.escape(n) for n in adlar) + ")"
        forms = {
            "alive": rf"{name}.{{0,22}}\b(?:(?:is|was|were|remained|stayed|still)\s+(?:still\s+)?alive|survived|(?:is|was) not dead)\b"
                     # Yüklem sıfatı: "<ad> ..., (still) alive" — "alive" AÇIKÇA söylenir; eylemin kendisi değil.
                     rf"|\b{name}\b[^.!?;]{{0,30}},\s*(?:still\s+|very\s+much\s+)?alive\b",
            "dead": rf"(?:\b{name}.{{0,20}}(?:is|was|lay|fell)\s+(?:(?:now|already|certainly)\s+)?dead\b|\b{name}.{{0,10}}(?:died|perished)\b|(?:killed|slain)\s+(?:\w+\s+)?{name})"
                    # v6: ceset — yalnız ÖLÜM durumu (öldüren ilişkisi ÇIKARILMAZ); benzetme ve
                    # bileşik adlar (corpse-like / corpse puppet / corpse eater) dışarıda.
                    rf"|(?<!like )(?<!as )(?<!resembling )\b(?:the\s+)?corpse of (?:the\s+)?{name}\b(?![\w-])"
                    rf"|\b{name}['’]s corpse\b(?!\s*(?:-|puppet|eater|like))"
                    rf"|\bbody of the dead (?:\w+\s+)?{name}\b"
                    # v8: adlaştırılmış ölüm, AD ile bağlı: "X's death" / "the death of X"
                    rf"|\b{name}['’]s death\b|\b(?:the\s+)?death of (?:the\s+)?{name}\b",
            "missing": rf"{name}.{{0,20}}(?:missing|disappeared|vanished)",
            "presumed_dead": rf"(?:believ\w*|presum\w*|thought).{{0,30}}{name}.{{0,15}}dead",
            "unknown": rf"(?:unknown|not sure).{{0,45}}{name}",
        }
        if value == "dead" and re.search(r"\b(?:like|as if|as though|resembl\w*|shaped like|statue)\b[^.!?]{0,25}\bcorpse\b", k, re.I) \
                and not re.search(forms["dead"].split("|(?<!like )")[0], k, re.I):
            return False, "life_status_not_established"
        if not re.search(forms.get(value, r"(?!)"), k, re.I):
            return False, "life_status_not_established"
    else:
        properties = {"Shadow Cores": r"shadow cores?", "Shadow Fragments": r"shadow fragments?", "Soul": r"soul", "Memory Tier": r"(?:memory )?tier", "Görev": r"role|task|duty|job", "Tür": r"type|kind|species"}
        if key == "Görev" and rol_kaniti(x["varlik"], value, k, yazimlar):
            return True, "named_prose"
        if not re.search(re.escape(value), k, re.I) or not re.search(properties.get(key, r"(?!)"), k, re.I):
            return False, "state_property_or_value_not_in_evidence"
    return True, "named_prose"
