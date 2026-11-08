/* Tempo yoklaması ve ölçüm bölümü önerisi (hızlı okuma planı Adım B). Hesap saf
   `yoklama-yardimci.js`'te; burada yalnız şerit çizilir. Şerit diyalog DEĞİLDİR:
   akışı durdurmaz, 20 sn'de kendiliğinden kapanır. Okuyucu bu modüle bağlanır
   (`yoklamaKur`), döngüsel içe aktarma yok. */
import { saveSettings, settings } from "./ayarlar.js";
import { bolumBitti, ETKINSIZ_SINIRI, yanit, yeniDurum } from "./yoklama-yardimci.js";
import { el } from "./temel.js";

const KAPANMA_MS = 20_000;
let durum = yeniDurum();
let kapama = 0;
let baglanti = { tempoDurdur() {}, etkinlik() {}, hizDegisti() {} };

const DUGMELER = {
  yoklama: [["rahatti", "Rahattı"], ["idare", "İdare eder"], ["zorlandim", "Zorlandım"]],
  olcum: [["tamam", "Tamam, tempoyu durdur"], ["kal", "Tempoda kal"]],
};

function kapat() {
  el("yoklama").hidden = true;
  clearTimeout(kapama);
}

function goster(tur) {
  el("yoklamaMetin").textContent = tur === "olcum"
    ? "Ölçüm için sıradaki bölümü kendi hızında oku."
    : "Takip edebildin mi?";
  el("yoklamaDugmeler").replaceChildren(...DUGMELER[tur].map(([cevap, yazi]) => {
    const b = document.createElement("button");
    b.type = "button";
    b.dataset.cevap = cevap;
    b.textContent = yazi;
    return b;
  }));
  el("yoklama").hidden = false;
  clearTimeout(kapama);
  kapama = setTimeout(kapat, KAPANMA_MS);
}

function cevapla(cevap) {
  baglanti.etkinlik();
  if (cevap === "tamam") {
    durum = { ...durum, etkinsiz: 0 };
    baglanti.tempoDurdur();
  } else if (cevap === "kal") {
    durum = { ...durum, etkinsiz: 0 };
  } else {
    const s = yanit(durum, cevap, settings.kaydirmaHizi || 1600);
    durum = s.durum;
    settings.kaydirmaHizi = s.hiz;
    saveSettings();
    baglanti.hizDegisti();
  }
  kapat();
}

// Bir bölüm bitti (okuma hızı ölçümünden): tempo mu, okurdan iz var mı.
export function tempoBolumuBitti(tempo, etkin) {
  const s = bolumBitti(durum, { tempo, etkin });
  durum = s.durum;
  if (s.goster) goster(s.goster);
  if (s.duraklat) {
    // Yoklamaya yanıt gelirse (sayaç sıfırlanır) durmaz; gelmezse tempo durur.
    setTimeout(() => {
      if (durum.etkinsiz >= ETKINSIZ_SINIRI) {
        durum = { ...durum, etkinsiz: 0 };
        baglanti.tempoDurdur();
      }
    }, KAPANMA_MS);
  }
}

export function yoklamaKur(b) {
  baglanti = { ...baglanti, ...b };
  el("yoklamaDugmeler").addEventListener("click", (ev) => {
    const d = ev.target.closest("[data-cevap]");
    if (d) cevapla(d.dataset.cevap);
  });
}
