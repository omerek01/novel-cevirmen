// SAF (DOM'suz, Node testli): okuyucu alt çubuğunun durum mantığı.
//
// Okuma Salonu (2026-10-13, kullanıcı isteği "alt bar açılıp kapanabilir olsun,
// boyutu da biraz daha küçük olsun"): kapalı hâl okurken varsayılandır ve yalnız
// küçük bir hap gösterir (ilerleme halkası + kalan süre); açık hâl tek sıra ince
// çubuktur. Aşağı kaydırma okumaya dönüş demektir, açık çubuk kendiliğinden kapanır;
// yukarı kaydırma çubuğu açmaz (okur yalnız geri bakıyor olabilir).

export function sonrakiHal(hal, olay) {
  if (olay === "hap") return "acik";
  if (olay === "kapat" || olay === "asagi-kaydir") return "kapali";
  return hal;
}

// Kalan okuma süresi (dakika, en az 1): kalan harf ÷ harf/dk (hızlı okuma planı §2).
// Hız bilinmiyorsa eski varsayım: 230 sözcük/dk × 6,5 harf.
export function kalanDakika(oran, harf, hizHdk) {
  const hiz = hizHdk > 0 ? hizHdk : 230 * 6.5;
  const kalan = Math.max(0, 1 - (oran || 0)) * (harf || 0);
  return Math.max(1, Math.round(kalan / hiz));
}
