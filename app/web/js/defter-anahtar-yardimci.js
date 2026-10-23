// Karakter defteri aç/kapa düğmesinin saf yardımcıları: DOM'a dokunmaz, Node ile
// sınanır (`asama-yardimci.js` ile aynı desen).

/* Satırın alt notu: durumu DEĞİL (onu düğmenin kendisi gösteriyor) "neden böyle"
   ve "parası nereye gidiyor" bilgisini taşır.

   KAYNAK gösterilir çünkü "açık" sorusunun iki ayrı cevabı var: düğme ya da
   sunucudaki `KARAKTER_DEFTERI`. `ceviri_asamalari.durum()` aynı ayrımı zaten
   gösteriyor, okur "neden açık" sorusunu oradan okumayı öğrendi.

   MODEL gösterilir çünkü defter artık seçili çeviri modelini takip ediyor; ücret
   o seçime bağlı ve seçimle defterin ayrıştığı bir vaka ölçüldü (1117 bölüm
   Argon seçiliyken 3.8 Flash ile işlenmişti). */
export function defterNotu({ kaynak, model } = {}) {
  const nereden = kaynak === "ayar"
    ? "Bu düğmeyle ayarlandı"
    : "Sunucu ayarından geliyor (KARAKTER_DEFTERI)";
  return model ? `${nereden} · şu an ${model} ile işliyor` : nereden;
}
