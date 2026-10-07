"""Faz 2A v8 — ADAY-ÖNCELİKLİ çıkarım + SPAN KİMLİKLİ kanıt.

    STATE(N-1) + SOURCE(N) + aynı-N deterministik
      -> span_ayir (cümle span'ları, kararlı kimlik)
      -> aday_uret (kaynak-yalnız, olgu DEĞİL; en çok ADAY_SINIRI)
      -> TEK model çağrısı (aday kararları + en çok 3 serbest keşif)
      -> aday_dogrula (yapısal + yalnız yüksek etkide anlamsal)
      -> bilgi_delta.delta_degerlendir (kopya/çelişki/grafik sınıfı; YAZMAZ)

Model kanıt METNİ yazmaz: yalnız `evidence_span_ids` döndürür; kanıt uygulama
tarafından `kaynak[start:end]` ile alınır. Kopyalama/tırnak/kısaltma hatası yapısal
olarak imkânsızdır. Eski (v7) yol `bilgi_delta` içinde aynen durur.
"""
from __future__ import annotations

import json
import re

from . import bilgi_delta, bilgi_kanit, glossary, translate, varlik_grafigi as vg

ADAY_CIKARICI_SURUMU = "8"
ADAY_ISTEM_SURUMU = "7"
ADAY_SEMA_SURUMU = "delta-4-span-evidence"
ADAY_SINIRI = 24
ADAY_TOKEN_TAVANI = 1600   # sert üst sınır; hedef ortalama <= 1200
SERBEST_SINIRI = 3
KANIT_SPAN_AZAMI = 3

# ---------------------------------------------------------------------------
# SPAN'LAR
# ---------------------------------------------------------------------------
_SINIR = re.compile(r"[.!?…]+[\"'”’\])]*(\s+)(?=[\"'“‘\[(]?[A-Z0-9])")


def span_ayir(kaynak: str, bolum: int) -> list[dict]:
    """Kaynağı cümle span'larına ayır. Kimlik `ch{N}:p{satır}:s{cümle}` — aynı metin
    aynı kimlikleri üretir. `kaynak[char_start:char_end] == text` daima."""
    out, taban = [], 0
    for p, satir in enumerate((kaynak or "").split("\n")):
        bas = len(satir) - len(satir.lstrip())
        parcalar, a = [], bas
        for m in _SINIR.finditer(satir):
            if m.start(1) > a:
                parcalar.append((a, m.start(1)))
            a = m.end()
        if satir[a:].strip():
            parcalar.append((a, len(satir.rstrip())))
        for s, (x, y) in enumerate(parcalar):
            out.append({"span_id": f"ch{bolum}:p{p}:s{s}", "chapter": bolum, "paragraph_index": p,
                        "sentence_index": s, "char_start": taban + x, "char_end": taban + y, "text": satir[x:y]})
        taban += len(satir) + 1
    return out


def span_kimligi(ham: str, bolum: int) -> str:
    """'p12s3' / 'p12:s3' / 'ch{N}:p12:s3' -> kanonik kimlik (başka bölüm KABUL EDİLMEZ)."""
    m = re.fullmatch(r"(?:ch(\d+):)?p(\d+):?s(\d+)", (ham or "").strip())
    if not m or (m.group(1) and int(m.group(1)) != bolum):
        return ""
    return f"ch{bolum}:p{m.group(2)}:s{m.group(3)}"


# ---------------------------------------------------------------------------
# AD ANMALARI (sözlük + N-1 takma adları + yazımlar + kaynaktaki yeni özel adlar)
# ---------------------------------------------------------------------------
_OZEL_AD = re.compile(r"[A-Z][\w’'\-]*(?:\s+(?:of\s+(?:the\s+)?)?[A-Z][\w’'\-]*)*")
_ZAMIR = re.compile(r"\b(?:he|she|it|they|him|her|them|his|its|their)\b", re.I)


class Anmalar:
    def __init__(self, book_slug: str, bolum: int, kaynak: str):
        self.cozucu = vg.DugumCozucu(book_slug)
        sozluk = glossary.ceviri_sozlugu(book_slug)
        adlar = set(translate.metinde_gecen_terimler(sozluk, kaynak))
        for kaynak_ad, ek in glossary.ekler(book_slug).items():
            for y in ek["yazimlar"]:
                if glossary.fold_term(y) in glossary.fold_term(kaynak):
                    adlar.add(y)
        # Takma/Gerçek Ad yalnız N-1'e kadar ÖĞRENİLMİŞ ve onaylı ise (gelecek takma ad YOK).
        self.takma: dict[str, str] = {}
        for b in vg.baglar(book_slug, en_cok_bolum=bolum - 1):
            if b["iliski"] in ("takma_adi", "gercek_adi") and b["durum"] == "onaylandi":
                self.takma[glossary.fold_term(b["hedef"])] = b["kaynak"]
                adlar.add(b["hedef"])
        self.desenler = sorted(((translate._term_regex(a), a) for a in adlar if a), key=lambda x: -len(x[1]))

    def kanonik(self, ad: str) -> str:
        t = self.takma.get(glossary.fold_term(ad))
        if t:
            return t
        k = self.cozucu.coz(ad)
        return self.cozucu.kaynak(k) if k else ad

    def bul(self, metin: str) -> list[dict]:
        """[{ad (yazıldığı gibi), kanonik, bilinen}] — örtüşmesiz, uzun önce."""
        alan, out = [], []
        for desen, ad in self.desenler:
            for m in desen.finditer(metin):
                if any(m.start() < b and m.end() > a for a, b in alan):
                    continue
                alan.append((m.start(), m.end()))
                out.append({"ad": m.group(0), "kanonik": self.kanonik(ad), "bilinen": True, "konum": m.start()})
        for m in _OZEL_AD.finditer(metin):
            if any(m.start() < b and m.end() > a for a, b in alan):
                continue
            parca = m.group(0).split()
            while parca and parca[0].casefold() in bilgi_kanit._CUMLE_BASI_SIRADAN:
                parca.pop(0)
            if parca and len(" ".join(parca)) > 2:
                ad = " ".join(parca)
                out.append({"ad": ad, "kanonik": self.kanonik(ad), "bilinen": bool(self.cozucu.coz(ad)),
                            "konum": m.start()})
        tekil = {}
        for x in sorted(out, key=lambda x: x["konum"]):
            tekil.setdefault(x["kanonik"], x)
        return list(tekil.values())


# ---------------------------------------------------------------------------
# ADAY ÜRETİCİ (kaynak-yalnız; N-1 grafiği KULLANMAZ)
# ---------------------------------------------------------------------------
KATEGORILER: tuple[tuple[str, int, re.Pattern], ...] = tuple((k, o, re.compile(d, re.I)) for k, o, d in (
    ("kill", 1, r"\b(?:killed|kills|slew|slain|murdered|executed)\b"),
    ("life_status", 1, r"\b(?:dead|died|dies|death|corpse|remains|perished|deceased|survived|alive)\b"),
    ("true_name", 2, r"\btrue names?\b"),
    ("identity", 2, r"\b(?:real name|actual name|identity|turned out|one and the same|also known as|is (?:she|he)\b)"),
    ("relationship_change", 3, r"\b(?:betray\w*|no longer|ceased|forgive|abandoned|parted ways|left (?:him|her|them|me) behind)\b"),
    ("teaching", 4, r"\b(?:taught|teacher|teach\w*|trained|mentor\w*|student|disciple|learn(?:ed|t) from|apprentice|lessons?)\b"),
    ("leadership", 4, r"\b(?:led by|leads|led|leader|commanded|commander of|under (?:the )?command of|in charge of|ruled by|lieutenants?)\b"),
    ("lineage", 5, r"\b(?:son|daughter|father|mother|parents?|sibling|brother|sister|descendant|ancestor|bloodline|lineage|heir|heiress|child of|offspring)\b"),
    ("role", 6, r"\b(?:served as|serves as|acted as|appointed|works? as|instructor|commander|captain|scout|healer|priest(?:ess)?|professor|lieutenant)\b"),
    ("location", 7, r"\b(?:situated|located|lives in|lived in|resides?|stationed|arrived at|entered|reached|returned to|stood in|remained in|stayed in|underside of)\b"),
    ("membership", 7, r"\b(?:member of|members of|joined|belongs? to|part of|clan|cohort|army|guild)\b"),
    ("transformation", 7, r"\b(?:transformed|turned into|evolved into|ascended|metamorphos\w*)\b"),
    ("title_alias", 8, r"\b(?:known as|called|titled|title|alias|nicknamed|named)\b|\b[A-Z][\w’']+\s*[,—–]\s*the\s+[A-Z][\w’']+"),
    ("epistemic_claim", 8, r"\b(?:believed|rumou?r\w*|supposedly|allegedly|said to|legend has it|thought to)\b"),
    ("generic_relationship", 9, r"\b(?:companion|friend|ally|allies|enemy|enemies|rival|comrade|partner)\b"),
))
_ZAMIR_OZNE = re.compile(r"(?:^|[\"'“‘…]\s*|\b(?:that|and|but|because|is that|while)\s+)(?:he|she|it|they)(?:['’]s)?\b", re.I)


def _onceki_anmalar(spans, i, anmalar, geri=2):
    """Zamir öncülü adayları: aynı paragrafta en çok `geri` cümle geri; paragrafın ilk
    cümlesiyse önceki dolu paragrafın son cümlesi (çapraz paragraf İŞARETLENİR)."""
    s = spans[i]
    out = []
    j, mesafe = i - 1, 1
    while j >= 0 and mesafe <= geri:
        o = spans[j]
        capraz = o["paragraph_index"] != s["paragraph_index"]
        bulunan = [x for x in anmalar.bul(o["text"]) if x["bilinen"]]
        if bulunan:
            return [{"entity": x["kanonik"], "source_span_id": o["span_id"], "distance": mesafe,
                     "cross_paragraph": capraz} for x in bulunan[:4]]
        if capraz:
            break
        j, mesafe = j - 1, mesafe + 1
    return out


def aday_uret(kaynak: str, bolum: int, anmalar: Anmalar, haric_kanitlar: tuple[str, ...] = ()) -> list[dict]:
    spans = span_ayir(kaynak, bolum)
    haric = {re.sub(r"\s+", " ", h).strip() for h in haric_kanitlar}
    satir_haric = {re.sub(r"\s+", " ", ln).strip() for ln in (kaynak or "").split("\n")} & haric
    adaylar = []
    for i, s in enumerate(spans):
        paragraf = re.sub(r"\s+", " ", (kaynak.split("\n")[s["paragraph_index"]])).strip()
        if paragraf in satir_haric:
            continue  # rün/sistem satırı: aynı-N deterministik plan kapsar, model adayı DEĞİL
        kat = [(k, o, m) for k, o, d in KATEGORILER for m in [d.search(s["text"])] if m]
        if not kat:
            continue
        anilan = anmalar.bul(s["text"])
        zamir = bool(_ZAMIR_OZNE.search(s["text"]))
        onculler = _onceki_anmalar(spans, i, anmalar) if zamir or not anilan else []
        if not anilan and not onculler:
            continue
        oncelik = min(o for _, o, _ in kat)
        k0 = min(kat, key=lambda x: x[1])[2]
        a, b = max(0, k0.start() - 60), min(len(s["text"]), k0.end() + 60)
        adaylar.append({
            "category": sorted({k for k, _, _ in kat}, key=lambda k: dict((x, o) for x, o, _ in KATEGORILER)[k]),
            "span_ids": [s["span_id"]],
            "context_span_ids": sorted({x["source_span_id"] for x in onculler}),
            "mention_candidates": [x["kanonik"] for x in anilan],
            "antecedent_candidates": onculler,
            "cue": k0.group(0), "claim_window": [a, b],
            "snippet": s["text"][a:b], "priority": oncelik,
            "_guc": len([x for x in anilan if x["bilinen"]]), "_sira": i,
        })
    adaylar.sort(key=lambda c: (c["priority"], -min(c["_guc"], 2), c["_sira"]))
    secilen, toplam = [], 0
    for c in adaylar:
        t = bilgi_delta._tok(_aday_satiri("C00", c))
        if len(secilen) >= ADAY_SINIRI or toplam + t > ADAY_TOKEN_TAVANI:
            continue
        secilen.append(c)
        toplam += t
    secilen.sort(key=lambda c: c["_sira"])
    for n, c in enumerate(secilen, 1):
        c["candidate_id"] = f"C{n:02d}"
    return secilen


def _kisa(sid: str) -> str:
    return sid.split(":", 1)[1].replace(":", "") if ":" in sid else sid


def _aday_satiri(cid: str, c: dict) -> str:
    ant = ", ".join(f"{a['entity']}@{_kisa(a['source_span_id'])}" + ("(prev-paragraph)" if a["cross_paragraph"] else "")
                    for a in c["antecedent_candidates"])
    return (f"{cid} [{','.join(c['category'])}] span={_kisa(c['span_ids'][0])} cue=\"{c['cue']}\" "
            f"mentions=[{', '.join(c['mention_candidates'])}]" + (f" antecedents=[{ant}]" if ant else "")
            + f" | …{c['snippet']}…")


# ---------------------------------------------------------------------------
# İSTEM + ŞEMA
# ---------------------------------------------------------------------------
KARARLAR = ("accept", "review", "capability_gap", "reject")
BILGI_TURLERI = ("relationship", "state", "identity", "update")
DEGISIM = ("none", "ended", "disproven")
ILISKI_VEYA_DURUM = tuple(vg.ILISKILER) + tuple(bilgi_delta.DURUM_ANAHTARLARI) + ("identity_revelation", "capability_gap")


def yanit_semasi() -> dict:
    karar = {"type": "object", "additionalProperties": False,
             "properties": {"candidate_id": {"type": "string"},
                            "decision": {"type": "string", "enum": list(KARARLAR)},
                            "knowledge_type": {"type": "string", "enum": list(BILGI_TURLERI)},
                            "subject": {"type": "string"},
                            "relation_or_state": {"type": "string", "enum": list(ILISKI_VEYA_DURUM)},
                            "object_or_value": {"type": "string"},
                            "epistemic": {"type": "string", "enum": list(vg.DURUM_BILGISI)},
                            "change": {"type": "string", "enum": list(DEGISIM)},
                            "gap_note": {"type": "string"},
                            "evidence_span_ids": {"type": "array", "items": {"type": "string"}, "maxItems": KANIT_SPAN_AZAMI},
                            "confidence": {"type": "number"}},
             "required": ["decision", "knowledge_type", "subject", "relation_or_state", "object_or_value",
                          "epistemic", "evidence_span_ids"]}
    serbest = {**karar, "properties": {k: v for k, v in karar["properties"].items() if k != "candidate_id"}}
    return {"type": "object", "additionalProperties": False, "required": ["candidate_decisions", "free_discoveries"],
            "properties": {"candidate_decisions": {"type": "array", "items": {**karar, "required": ["candidate_id", *karar["required"]]}},
                           "free_discoveries": {"type": "array", "items": serbest, "maxItems": SERBEST_SINIRI}}}


def _talimat() -> str:
    iliski = "".join(f"    {k}: {v['subject_role']} -> {v['object_role']}\n" for k, v in vg.ILISKILER.items())
    tanim = "".join(f"    {k}: {v}\n" for k, v in bilgi_delta.DURUM_BILGISI_TANIMLARI.items())
    return (
        "You update a novel's CHRONOLOGICAL KNOWLEDGE GRAPH as if reading it for the first time. You receive "
        "KNOWN THROUGH N-1, facts " + bilgi_delta.AYNI_BOLUM_BASLIGI + ", a CANDIDATE LIST and the full chapter "
        "text split into sentence spans marked [pXsY]. Decide what NEW knowledge this chapter adds.\n"
        "CANDIDATES are spans a keyword scanner flagged. They are NOT facts. For each candidate decide: accept "
        "(new fact, evidenced), review (graph-worthy but uncertain/needs a human), capability_gap (graph-worthy "
        "but the vocabulary cannot represent it, e.g. directed lineage/descent, transfer/custody), or omit it "
        "(= reject; most candidates should be omitted). Output decisions only for accept/review/capability_gap.\n"
        "FREE DISCOVERIES: at most " + str(SERBEST_SINIRI) + " important facts NOT covered by any candidate.\n"
        "EVIDENCE: never write quotes. Give evidence_span_ids: 1-3 CONTIGUOUS span ids from ONE paragraph, in "
        "order, that establish the fact (e.g. [\"p12s3\",\"p12s4\"]). Include the sentence naming a pronoun's "
        "antecedent when the fact uses a pronoun.\n"
        "ENTITIES: subject/object must be a name appearing in the evidence spans or one of the candidate's "
        "antecedents. Use canonical names as listed. Never attach a pronoun to someone not offered as antecedent.\n"
        "DIRECTION: store relations as subject -> object using the roles below (e.g. 'The Guard was led by Ada' "
        "=> Guard lideri Ada; 'Ayla taught Boran' => Boran ogretmeni Ayla).\n"
        "STATES: relation_or_state may be a state key (" + ", ".join(bilgi_delta.DURUM_ANAHTARLARI) + "); "
        "life_status values: " + ", ".join(bilgi_delta.LIFE_STATUS) + "; role = a person's explicit role/position "
        "(e.g. 'served as the scout' => role scout).\n"
        "EPISTEMIC: judge the clause that states the fact, not hedges elsewhere in the sentence. Definitions:\n" + tanim +
        "IDENTITY: ordinary name, title (unvani), alias (takma_adi), magical True Name (gercek_adi; needs explicit "
        "True Name statement), identity revelation (two previously separate entities are the same; use "
        "relation_or_state=identity_revelation with decision=review). Never map several names by position.\n"
        "UPDATES: an existing KNOWN relation that ends/is disproven => knowledge_type=update, change=ended|disproven, "
        "decision=review.\n"
        "HIGH IMPACT (oldurdu, life_status, gercek_adi, identity, updates): only explicit statements; a parasite or "
        "part dying is not its host dying; stabbing/defeating is not killing. Do not re-extract "
        + bilgi_delta.AYNI_BOLUM_BASLIGI + " facts or facts already in KNOWN.\n"
        "Relations (subject -> object):\n" + iliski +
        "OUTPUT: JSON matching the schema only.\n" + json.dumps(yanit_semasi(), ensure_ascii=False)
    )


ADAY_TALIMATI = _talimat()


def istem_kur(baglam: dict, kaynak: str, bolum: int, adaylar: list[dict]) -> str:
    spans = span_ayir(kaynak, bolum)
    satirlar, son_p = [], None
    for s in spans:
        if s["paragraph_index"] != son_p and son_p is not None:
            satirlar.append("\n")
        satirlar.append(f"[{_kisa(s['span_id'])}] {s['text']} ")
        son_p = s["paragraph_index"]
    bilgi = "\n".join(baglam["satirlar"]) or "(none)"
    run = "\n".join(baglam.get("run_satirlari") or []) or "(none)"
    aday = "\n".join(_aday_satiri(c["candidate_id"], c) for c in adaylar) or "(none)"
    return (f"CHAPTER {bolum}\n\nKNOWN THROUGH {baglam['bilgi_siniri']}:\n{bilgi}\n\n"
            f"{bilgi_delta.AYNI_BOLUM_BASLIGI} (CHAPTER {bolum}):\n{run}\n\n"
            f"CANDIDATES — THESE ARE NOT FACTS:\n{aday}\n\n"
            f"THIS CHAPTER'S TEXT (sentence spans):\n{''.join(satirlar).strip()}")


# ---------------------------------------------------------------------------
# DOĞRULAYICI: yapısal her ilişkide; anlamsal yalnız yüksek etkide / sahte birliktelik riskinde
# ---------------------------------------------------------------------------
# Risk katmanı (metadata + açık liste; ILISKILER DEĞİŞMEDİ):
YUKSEK_ETKI = {r for r, v in vg.ILISKILER.items() if v["requires_strong_evidence"]} | {"gercek_adi"}
ANLAMSAL_GEREKLI = {r for r, v in vg.ILISKILER.items() if v["symmetric"]} | {
    "anisi", "golgesi", "kendi_golgesi", "yanki", "yetenegi", "efsunu", "niteligi", "gorunusu", "kusuru", "ruya_capasi"}
YAPISAL = set(vg.ILISKILER) - YUKSEK_ETKI - ANLAMSAL_GEREKLI
_OLUM_ADI = re.compile(r"\b(?:death|died|dead|corpse|remains)\b", re.I)
_CANLI_ADI = re.compile(r"\b(?:alive|survived)\b", re.I)


def _kanit_spanlari(ids: list[str], bolum: int, span_harita: dict) -> tuple[list[dict] | None, str]:
    kimlik = [span_kimligi(x, bolum) for x in ids or []]
    if not kimlik or "" in kimlik or len(kimlik) > KANIT_SPAN_AZAMI:
        return None, "invalid_span_id"
    sp = [span_harita.get(k) for k in kimlik]
    if None in sp:
        return None, "invalid_span_id"
    if len({s["paragraph_index"] for s in sp}) != 1:
        return None, "cross_paragraph_span"
    if [s["sentence_index"] for s in sp] != list(range(sp[0]["sentence_index"], sp[0]["sentence_index"] + len(sp))):
        return None, "non_contiguous_span"
    return sp, ""


def _bagla(ad: str, kanit_anmalari: list[dict], onculler: list[dict], anmalar: Anmalar):
    """Ucu izinli kümeye bağla: kanıtta geçen ad ya da adayın öncülü. -> (kanonik, öncül mü, öncül kaydı)"""
    hedef = glossary.fold_term(anmalar.kanonik(ad))
    for x in kanit_anmalari:
        if glossary.fold_term(x["kanonik"]) == hedef or glossary.fold_term(x["ad"]) == glossary.fold_term(ad):
            return x["kanonik"], False, None
    for o in onculler:
        if glossary.fold_term(o["entity"]) == hedef:
            return o["entity"], True, o
    return None, False, None


def _iddia_penceresi(metin: str, adlar: list[str]) -> str:
    """Epistemik yerellik: iddia, uçların arasındaki parçadır; tek uçluda uç ile bir sonraki
    cümlecik sınırı ('who/which', ';', ':' ya da cümle sonu) arası. Yan cümledeki 'perhaps'
    bütün iddiayı bulaştırmaz."""
    konum = []
    for ad in adlar:
        m = translate._term_regex(ad).search(metin)
        if m:
            konum.append((m.start(), m.end()))
    if not konum:
        return metin
    a, b = min(x[0] for x in konum), max(x[1] for x in konum)
    if len(konum) == 1:
        son = re.search(r",\s*(?:who|which|whose)\b|[;:]|[.!?](?:\s|$)", metin[b:])
        b = b + (son.start() if son else len(metin) - b)
        bas = metin.rfind(".", 0, a)
        a = bas + 1 if bas >= 0 else 0
    return metin[a:b]


def _zamir_degistir(metin: str, ad: str) -> str:
    """İç bağlam: ilk özne zamiri öncülün adıyla değişir (kanıt metni DEĞİŞMEZ)."""
    return re.sub(r"(?i)\b(he|she|it|they)\b", ad, metin, count=1)


def aday_dogrula(book_slug: str, bolum: int, kaynak: str, veri: dict, adaylar: list[dict], anmalar: Anmalar) -> dict:
    span_harita = {s["span_id"]: s for s in span_ayir(kaynak, bolum)}
    aday_harita = {c["candidate_id"]: c for c in adaylar}
    kayit, delta, inceleme = [], {k: [] for k in bilgi_delta.DELTA_SEMASI}, []
    sayac = {"invalid_span": 0, "unknown_candidate": 0, "free_over_cap": 0, "entity_not_allowed": 0,
             "direction_reversed": 0, "high_impact_rejected": 0, "high_impact_review": 0, "structural_review": 0}
    kararlar = [(x, "candidate") for x in veri.get("candidate_decisions") or []]
    serbest = veri.get("free_discoveries") or []
    sayac["free_over_cap"] = max(0, len(serbest) - SERBEST_SINIRI)
    kararlar += [(x, "free") for x in serbest[:SERBEST_SINIRI]]

    def sonuc(x, kanal, durum, sebep, **ek):
        kayit.append({"channel": kanal, "candidate_id": x.get("candidate_id"), "decision": x.get("decision"),
                      "subject": x.get("subject"), "relation_or_state": x.get("relation_or_state"),
                      "object_or_value": x.get("object_or_value"), "epistemic": x.get("epistemic"),
                      "evidence_span_ids": x.get("evidence_span_ids"), "outcome": durum, "reason": sebep, **ek})

    for x, kanal in kararlar:
        if x.get("decision") not in ("accept", "review", "capability_gap"):
            continue
        aday = aday_harita.get(x.get("candidate_id")) if kanal == "candidate" else None
        if kanal == "candidate" and aday is None:
            sayac["unknown_candidate"] += 1
            sonuc(x, kanal, "rejected", "unknown_candidate")
            continue
        sp, hata = _kanit_spanlari(x.get("evidence_span_ids"), bolum, span_harita)
        if sp is None:
            sayac["invalid_span"] += 1
            sonuc(x, kanal, "rejected", hata)
            continue
        kanit = kaynak[sp[0]["char_start"]:sp[-1]["char_end"]]
        kanit_anmalari = anmalar.bul(kanit)
        if aday:
            onculler = aday["antecedent_candidates"]
        else:
            tum = span_ayir(kaynak, bolum)
            i = next(n for n, s in enumerate(tum) if s["span_id"] == sp[0]["span_id"])
            onculler = _onceki_anmalar(tum, i, anmalar)
        r = x.get("relation_or_state")
        durum_mu = r in bilgi_delta.DURUM_ANAHTARLARI
        s_ad, s_oncul, s_kayit = _bagla(x.get("subject", ""), kanit_anmalari, onculler, anmalar)
        if durum_mu:
            o_ad, o_oncul, o_kayit = x.get("object_or_value"), False, None
        else:
            o_ad, o_oncul, o_kayit = _bagla(x.get("object_or_value", ""), kanit_anmalari, onculler, anmalar)
        if not s_ad or not o_ad:
            sayac["entity_not_allowed"] += 1
            sonuc(x, kanal, "rejected", "entity_not_allowed", evidence=kanit)
            continue
        oncul = s_kayit or o_kayit
        ic = _zamir_degistir(kanit, oncul["entity"]) if oncul else kanit
        guvenli_oncul = not oncul or (len(onculler) == 1 and oncul["distance"] == 1 and not oncul["cross_paragraph"])

        # ---- açık inceleme / boşluk / kimlik / güncelleme ----
        if x["decision"] == "capability_gap" or r == "capability_gap":
            inceleme.append(("relation_capability_gap", "medium",
                             f"MISSING_RELATION_CAPABILITY: {s_ad} -> {o_ad} ({x.get('gap_note') or 'unrepresentable'})",
                             {"subject": s_ad, "object": o_ad, "note": x.get("gap_note"), "kanit": kanit, "capability_gap": True}))
            sonuc(x, kanal, "capability_gap", "ok", evidence=kanit)
            continue
        if r == "identity_revelation" or x.get("knowledge_type") == "identity" and r not in vg.ILISKILER:
            inceleme.append(("identity_merge", "critical", f"Kimlik açığa çıkması önerisi (b{bolum}): {s_ad} = {o_ad}",
                             {"ad_1": s_ad, "ad_2": o_ad, "kanit": kanit}))
            sonuc(x, kanal, "review", "identity_review_first", evidence=kanit)
            continue
        if x.get("knowledge_type") == "update" or x.get("change") in ("ended", "disproven"):
            inceleme.append(("relationship_conflict", "medium", f"Güncelleme önerisi: {s_ad} {r} {o_ad} ({x.get('change')})",
                             {"ozne": s_ad, "iliski": r, "nesne": o_ad, "kanit": kanit, "auto_close": False}))
            sonuc(x, kanal, "review", "update_review_first", evidence=kanit)
            continue
        if x["decision"] == "review":
            inceleme.append(("model_review", "medium", f"Model incelemesi: {s_ad} {r} {o_ad}",
                             {"ozne": s_ad, "iliski": r, "nesne": o_ad, "kanit": kanit}))
            sonuc(x, kanal, "review", "model_review", evidence=kanit)
            continue

        # ---- kabul adayı: risk katmanına göre ----
        pencere = _iddia_penceresi(ic, [s_ad] + ([] if durum_mu else [o_ad]))
        epi = bilgi_kanit.epistemik_kontrol(pencere, x.get("epistemic"))
        if epi:
            sonuc(x, kanal, "rejected", epi, evidence=kanit)
            continue
        if durum_mu:
            anahtar = bilgi_delta.DURUM_ANAHTARLARI[r]
            ox = {"varlik": s_ad, "anahtar": anahtar, "makine_anahtari": r, "deger": o_ad,
                  "durum_bilgisi": x.get("epistemic"), "kanit": pencere}
            if r == "life_status":
                if not guvenli_oncul:
                    _incele_yuksek(inceleme, sayac, s_ad, r, o_ad, kanit)
                    sonuc(x, kanal, "review", "ambiguous_antecedent", evidence=kanit)
                    continue
                gecerli, sebep = bilgi_kanit.state_kaniti(ox, pencere, {}, [])
                if not gecerli:
                    if (o_ad == "dead" and _OLUM_ADI.search(ic)) or (o_ad == "alive" and _CANLI_ADI.search(ic)):
                        _incele_yuksek(inceleme, sayac, s_ad, r, o_ad, kanit)
                        sonuc(x, kanal, "review", "high_impact_binding_unverified", evidence=kanit)
                    else:
                        sayac["high_impact_rejected"] += 1
                        sonuc(x, kanal, "rejected", sebep, evidence=kanit)
                    continue
            elif r == "role":
                if not (re.search(re.escape(o_ad.rstrip("s")), pencere, re.I) and
                        translate._term_regex(s_ad).search(pencere)):
                    sonuc(x, kanal, "rejected", "role_value_not_in_claim", evidence=kanit)
                    continue
            else:
                gecerli, sebep = bilgi_kanit.state_kaniti(ox, pencere, {}, [])
                if not gecerli:
                    sonuc(x, kanal, "rejected", sebep, evidence=kanit)
                    continue
            delta["state_changes"].append({"varlik": s_ad, "anahtar": r, "deger": o_ad, "kanit": kanit,
                                           "durum_bilgisi": x.get("epistemic"), "_dogrulandi": True})
            sonuc(x, kanal, "accepted", "state", evidence=kanit)
            continue
        if r not in vg.ILISKILER:
            sonuc(x, kanal, "rejected", "unknown_relation")
            continue
        # İddia yerelliği: anlamsal denetim, iki ucu BİRLİKTE içeren cümle(ler)de yapılır;
        # başka cümledeki olumsuzluk/şüphe iddiayı bulaştırmaz. Böyle cümle yoksa yüksek
        # etkili iddia otomatik kabul DE ret DE edilmez -> inceleme.
        iddia = " ".join(t for t in re.split(r"(?<=[.!?])\s+", ic)
                         if all(translate._term_regex(a_).search(t) for a_ in (s_ad, o_ad)))
        if not iddia and (r in YUKSEK_ETKI or r in ANLAMSAL_GEREKLI):
            _incele_yuksek(inceleme, sayac, s_ad, r, o_ad, kanit)
            sonuc(x, kanal, "review", "endpoints_not_in_one_sentence", evidence=kanit)
            continue
        ham = {"ozne": s_ad, "iliski": r, "nesne": o_ad, "kanit": iddia or ic}
        sem, sebep = bilgi_kanit.semantik_sonuc(ham, {}, ())
        if sem == "wrong" and sebep == "direction_reversed":
            sayac["direction_reversed"] += 1
            sonuc(x, kanal, "rejected", "direction_reversed", evidence=kanit)
            continue
        if r in YUKSEK_ETKI or r in ANLAMSAL_GEREKLI:
            if sem != "verified" or not guvenli_oncul:
                if r in YUKSEK_ETKI and sem == "wrong":
                    sayac["high_impact_rejected"] += 1
                    sonuc(x, kanal, "rejected", sebep, evidence=kanit)
                else:
                    _incele_yuksek(inceleme, sayac, s_ad, r, o_ad, kanit)
                    sonuc(x, kanal, "review", "semantic_unverified:" + sebep, evidence=kanit)
                continue
        else:  # YAPISAL: uçlar aynı cümlede (öncül zamiri bu cümlededir) olmalı
            if not any(all(translate._term_regex(a).search(t) for a in (s_ad, o_ad))
                       for t in re.split(r"(?<=[.!?])\s+", ic)):
                sayac["structural_review"] += 1
                inceleme.append(("model_review", "low", f"Uçlar aynı cümlede değil: {s_ad} {r} {o_ad}",
                                 {"ozne": s_ad, "iliski": r, "nesne": o_ad, "kanit": kanit}))
                sonuc(x, kanal, "review", "endpoints_not_in_one_sentence", evidence=kanit)
                continue
        delta["new_relationships"].append({"ozne": s_ad, "iliski": r, "nesne": o_ad, "kanit": kanit,
                                           "durum_bilgisi": x.get("epistemic"), "_dogrulandi": True})
        sonuc(x, kanal, "accepted", "relationship", evidence=kanit)
    return {"kayit": kayit, "delta": delta, "inceleme": inceleme, "sayac": sayac}


def _incele_yuksek(inceleme, sayac, s, r, o, kanit):
    sayac["high_impact_review"] += 1
    inceleme.append(("high_impact_review", "high", f"Yüksek etkili iddia doğrulanamadı: {s} {r} {o}",
                     {"ozne": s, "iliski": r, "nesne": o, "kanit": kanit}))


# ---------------------------------------------------------------------------
# ORKESTRASYON (yalnız DOĞRULAMA kipi: hiçbir şey yazılmaz)
# ---------------------------------------------------------------------------
def _model_cagir(model: str):
    bilgi_delta.saglayici_dogrula(model)

    def cagir(user: str, system: str):
        with translate.yanit_semasi(yanit_semasi()):
            yanit, fiili = translate._generate_with_fallback(translate._gemini_fabrikasi(""), (model,), user,
                                                             system=system, max_tokens=translate.MAX_OUTPUT_TOKENS)
        if fiili != model:
            raise bilgi_delta.SaglayiciHatasi(f"beklenen {model}, yanıtlayan {fiili}")
        meta = getattr(yanit, "usage_metadata", None)
        k = {"fiili_model": fiili, "saglayici": bilgi_delta.CIKARICI_SAGLAYICI}
        if meta is not None:
            k.update({"giris_tokeni": getattr(meta, "prompt_token_count", None),
                      "cikis_tokeni": getattr(meta, "candidates_token_count", None),
                      "dusunme_tokeni": getattr(meta, "thoughts_token_count", None)})
        return getattr(yanit, "text", None), k
    return cagir


def sema_dogrula(veri) -> list[str]:
    if not isinstance(veri, dict) or set(veri) != {"candidate_decisions", "free_discoveries"}:
        return ["kök alanlar candidate_decisions/free_discoveries olmalı"]
    hatalar = []
    for ad in veri:
        if not isinstance(veri[ad], list):
            hatalar.append(f"{ad} liste değil")
            continue
        for i, x in enumerate(veri[ad]):
            if not isinstance(x, dict) or x.get("decision") not in KARARLAR or \
                    x.get("relation_or_state") not in ILISKI_VEYA_DURUM or x.get("epistemic") not in vg.DURUM_BILGISI or \
                    not isinstance(x.get("evidence_span_ids"), list):
                hatalar.append(f"{ad}[{i}] şema dışı")
    return hatalar


def aday_degerlendir(book_slug: str, bolum: int, model: str, cagri=None) -> dict:
    if cagri is None:
        bilgi_delta.saglayici_dogrula(model)
    kaynak = bilgi_delta.kaynak_metin(book_slug, bolum)
    if not kaynak:
        return {"bolum": bolum, "durum": "failed", "hata": "kaynak metin yok"}
    baglam = bilgi_delta.baglam_kur(book_slug, bolum, kaynak)
    anmalar = Anmalar(book_slug, bolum, kaynak)
    plan = bilgi_delta.canonical_plan(book_slug, kaynak)
    adaylar = aday_uret(kaynak, bolum, anmalar, tuple(e for *_, e in plan))
    istem = istem_kur(baglam, kaynak, bolum, adaylar)
    olcum = {"kaynak_tokeni": baglam["kaynak_tokeni"], "baglam_tokeni": baglam["baglam_tokeni"],
             "aday_sayisi": len(adaylar),
             "aday_tokeni": bilgi_delta._tok("\n".join(_aday_satiri(c["candidate_id"], c) for c in adaylar)),
             "talimat_tokeni": bilgi_delta._tok(ADAY_TALIMATI), "istem_tokeni": bilgi_delta._tok(istem)}
    try:
        metin, kullanim = (cagri or _model_cagir(model))(istem, ADAY_TALIMATI)
    except Exception as exc:  # noqa: BLE001 — doğrulama kipi: kayıt yazılmaz
        return {"bolum": bolum, "durum": "failed", "hata": f"{type(exc).__name__}: {exc}",
                "hata_sinifi": bilgi_delta._hata_sinifi(exc), "adaylar": adaylar, "olcum": olcum}
    olcum.update(kullanim or {})
    veri = bilgi_delta.varlik_cikarim_ayristir(metin)
    hatalar = sema_dogrula(veri) if veri is not None else ["yanıt JSON değil"]
    if hatalar:
        return {"bolum": bolum, "durum": "dogrulama", "sema_hatalari": hatalar, "ham_yanit": metin,
                "adaylar": adaylar, "olcum": olcum}
    dog = aday_dogrula(book_slug, bolum, kaynak, veri, adaylar, anmalar)
    degerlendirme = bilgi_delta.delta_degerlendir(book_slug, bolum, dog["delta"], kaynak)
    degerlendirme["inceleme"] = list(degerlendirme["inceleme"]) + dog["inceleme"]
    return {"bolum": bolum, "durum": "dogrulama", "sema_hatalari": [], "ham_yanit": metin, "model_deltasi": veri,
            "adaylar": adaylar, "aday_kararlari": dog["kayit"], "dogrulayici_sayac": dog["sayac"],
            "degerlendirme": degerlendirme, "deterministik_bilgi": baglam["run_satirlari"],
            "girdi_bilgisi": baglam["satirlar"], "olcum": olcum,
            "surumler": {"cikarici": ADAY_CIKARICI_SURUMU, "istem": ADAY_ISTEM_SURUMU, "sema": ADAY_SEMA_SURUMU},
            "saglayici": bilgi_delta.CIKARICI_SAGLAYICI if cagri is None else "enjekte", "model": model}
