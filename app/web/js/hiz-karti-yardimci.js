// SAF (DOM'suz, Node testli): ayarlardaki "Okuma hızı" kartının HTML'i (hızlı okuma
// planı §4). Kalıcı hızın asıl kaynağı pratik: bugünkü dakika en üstte ve en büyük; hız
// ikincil, hedefe dönüşmesin. Girdi `/api/reading-speed/stats` yanıtı (yalnız sayılar).
const sayi = (n, k = 0) => Number(n).toLocaleString("tr-TR", { maximumFractionDigits: k });

function cizgi(gunluk, alan, sinif) {
  const noktalar = gunluk.map((g, i) => [i, g[alan]]).filter(([, v]) => v > 0);
  if (noktalar.length < 2) return "";
  const enCok = Math.max(...gunluk.flatMap((g) => [g.hdk || 0, g.tempo_hdk || 0]));
  const enAz = Math.min(...gunluk.flatMap((g) => [g.hdk, g.tempo_hdk]).filter((v) => v > 0));
  const aralik = Math.max(1, enCok - enAz);
  const n = Math.max(1, gunluk.length - 1);
  const d = noktalar.map(([i, v], j) =>
    `${j ? "L" : "M"}${((i / n) * 280).toFixed(1)},${(54 - ((v - enAz) / aralik) * 48).toFixed(1)}`).join(" ");
  return `<path class="${sinif}" d="${d}"/>`;
}

export function kartHtml(v) {
  const parca = [];
  const dk = v ? v.bugun_dk || 0 : 0;
  parca.push(`<p class="hk-bugun"><b>${sayi(dk, 1)}</b> dk <span>bugün okudun</span></p>`);
  const k = v && v.kisisel_hiz;
  if (!k) {
    parca.push('<p class="hk-not">Birkaç bölümü baştan sona okuyunca hızın burada görünecek.</p>');
  } else {
    parca.push(`<p class="hk-hiz">Kişisel hızın <b>${sayi(k.sdk || 0)}</b> kel/dk ` +
      `<span>(${sayi(k.hdk)} harf/dk · ${sayi(v.oturum_sayisi || 0)} bölüm)</span></p>`);
    if (v.degisim != null) {
      const y = Math.round(v.degisim * 100);
      parca.push(`<p class="hk-degisim">İlk 5 bölümüne göre <b>${y >= 0 ? "+" : "−"}%${Math.abs(y)}</b></p>`);
    }
  }
  const g = (v && v.gunluk) || [];
  const yollar = cizgi(g, "hdk", "hk-serbest") + cizgi(g, "tempo_hdk", "hk-tempo");
  if (yollar) {
    parca.push(`<svg class="hk-grafik" viewBox="0 0 280 60" role="img" ` +
      `aria-label="Son 30 günün okuma hızı: düz çizgi kendi hızın, kesikli tempo">${yollar}</svg>`);
  }
  const oh = (v && v.obek_hizlari) || {};
  const boylar = Object.keys(oh).sort((a, b) => a - b);
  if (boylar.length) {
    parca.push('<ul class="hk-obek">' + boylar.map((b) =>
      `<li>Öbek ${b} sözcük: <b>${sayi(oh[b].sdk || 0)}</b> kel/dk <span>(${sayi(oh[b].n)} bölüm)</span></li>`).join("") + "</ul>");
  }
  parca.push('<p class="hk-bilgi">Tempo ve öbek kılavuzu, araştırmalardaki silinen metin yönteminin ' +
    "yumuşatılmış hali; etkisi sende ölçülüyor. Anlama nesnel ölçülmüyor, yalnız senin yanıtınla.</p>");
  return parca.join("");
}
