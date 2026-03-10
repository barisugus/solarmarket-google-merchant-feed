/**
 * TSM Edge Cache Worker v4.1
 * turkiyesolarmarket.com.tr
 *
 * Changelog:
 *   v3.0  — Edge cache, non-www redirect, canonical injection, 500→410, Set-Cookie strip
 *   v3.1  — /arama bypass
 *   v3.2  — Dual-layer rate limit (/arama), /Icerik/Goster/ 500→410
 *   v3.3  — /merchant-feed.xml → GitHub raw proxy (1h cache)
 *   v3.4  — D-kategori 301/410 redirect map (14 slug + 1 gone)
 *   v3.5  — KRİTİK: 500→503 (Retry-After) — Google index kaybını durdur
 *   v3.6  — PageSpeed: lazy-load, CSS async, JS defer, preconnect, font-display
 *   v3.7  — Trailing slash 301 redirect + maintenance 503 logic kaldırıldı
 *   v3.8  — /kategori/ trailing slash muafiyeti (origin SEF_URL trailing slash gerektirir)
 *   v3.9  — Arçelik 26 ürün silme: 20 slug 410 GONE + 2 slug 301 redirect, last-segment matching
 *   v4.0  — FIX: bypass paths (/epanel, /sepet vb.) trailing slash redirect loop düzeltmesi
 *   v4.1  — CANONICAL: product-level canonical map (416 ürün) — çoklu kategori URL'leri için tek canonical
 *   v4.2  — 5xx FIX: /kategori/{sef}→/kategori/0/{sef} 301, origin 500→404 (/urunler/), /markaurunleri/ SEF→410, Icerik kaldırıldı (blog sayfaları)
 */

// ─── D-Kategori Redirect Map (v3.4 + v3.9) ───
const REDIRECT_301 = {
  'arcelik-crystal-400w-monokristal-gunes-paneli': '/urunler/arcelik-crystal-590w-monokristal-gunes-paneli',
  'arcelik-crystal-410w-monokristal-gunes-paneli': '/urunler/arcelik-crystal-590w-monokristal-gunes-paneli',
  'arcelik-crystal-half-cut-450w-monokristal-gunes-paneli': '/urunler/arcelik-crystal-590w-monokristal-gunes-paneli',
  'arcelik-crystal-half-cut-500w-monokristal-gunes-paneli': '/urunler/arcelik-crystal-590w-monokristal-gunes-paneli',
  'arcelik-crystal-550w-monokristal-gunes-paneli': '/urunler/arcelik-crystal-590w-monokristal-gunes-paneli',
  'arcelik-crystal-half-cut-545w-monokristal-gunes-paneli': '/urunler/arcelik-crystal-590w-monokristal-gunes-paneli',
  'arcelik-inv-100kt-arc---100-kw-trifaze-on-grid-solar-inverter': '/urunler/arcelik-inv-100kt-arc',
  'byd-battery-box-premium-lvs-4-0---4-kwh-lityum-pil': '/urunler/byd-battery-box-premium-hvs-5-1---5-12-kwh-lityum-pil',
  'byd-battery-box-premium-lvs-8-0---8-kwh-lityum-pil': '/urunler/byd-battery-box-premium-hvs-5-1---5-12-kwh-lityum-pil',
  'byd-battery-box-premium-lvs-12-0---12-kwh-lityum-pil': '/urunler/byd-battery-box-premium-hvm-8-3---8-28-kwh-lityum-pil',
  'byd-battery-box-premium-lvs-16-0---16-kwh-lityum-pil': '/urunler/byd-battery-box-premium-hvm-8-3---8-28-kwh-lityum-pil',
  'byd-battery-box-premium-lvs-20-0---20-kwh-lityum-pil': '/urunler/byd-battery-box-premium-hvm-11-04---11-04-kwh-lityum-pil',
  'byd-battery-box-premium-lvs-24-0---24-kwh-lityum-pil': '/urunler/byd-battery-box-premium-hvm-11-04---11-04-kwh-lityum-pil',
  'byd-battery-box-premium-lvs-3-2---3-2-kwh-lityum-pil': '/urunler/byd-battery-box-premium-hvs-5-1---5-12-kwh-lityum-pil',
  // v3.9 — Eski inverterler → ARC versiyonuna yönlendir (SEO link juice korunur)
  'arcelik-inv-15kt': '/urunler/inverter-markalari/arcelik/arcelik-inv-15kt-arc',
  'arcelik-inv-30kt': '/urunler/inverter-markalari/arcelik/arcelik-inv-30kt-arc',
};

// ─── v3.4 GONE products (single-segment, full-path match) ───
const GONE_410 = new Set([
  'jinko-tiger-pro-72hc-550w-monokristal-gunes-paneli',
]);

// ─── v3.9 GONE products (last-segment match — covers all category URL variants) ───
const GONE_PRODUCT_410 = new Set([
  'arcelik-590w-solar-panel--palet',
  'arcelik-595w-solar-panel',
  'arcelik-595w-solar-panel--palet',
  'arcelik-600w-solar-panel',
  'arcelik-600w-solar-panel--palet',
  'arcelik-arclkfsb100w-katlanabilir-solar-canta-sku-9009121100--12v-dc-pwm-sarj-regulatorlu-12v-aku-sarjli',
  'arcelik-arclkfsb200w-katlanabilir-solar-canta-sku-9009131100--12v-dc-pwm-sarj-regulatorlu-12v-aku-sarjli',
  'arcelik-inv-10kt',
  'arcelik-inv-50kt-pro',
  'arcelik-solar-panel-375-w-palet',
  'arcelik-solar-panel-375-w-tekli',
  'arcelik-solar-panel-445-w',
  'arcelik-solar-panel-445-w-palet',
  'arcelik-solar-panel-455-w-palet',
  'arcelik-solar-panel-455-w-tekli',
  'arcelik-sun-junior-10kt-10kwh',
  'arcelik-sun-junior-5kt-4-48kwh',
  'arclk-fsp-20w',
  'katlanir-gunes-paneli-arclk-fsp-100w',
  'katlanir-gunes-paneli-arclk-fsp-40w',
]);

// ─── v4.2 Icerik Numeric ID → SEF URL Redirect Map ───
const ICERIK_SEF_MAP = {
  '41': 'hakkimizda',
  '44': 'fronius-inverter-karsilastirma-primo-symo-verto-2026',
  '45': 'hibrit-inverter-nedir-on-grid-off-grid-karsilastirma-2026',
  '46': 'on-grid-inverter-nedir-mppt-verimlilik-secim-rehberi-2026',
  '47': 'byd-lityum-batarya-rehberi-hvs-hvm-lv-flex-karsilastirma-2026',
  '48': 'ev-icin-gunes-paneli-sistemi-maliyet-hesaplama-tasarruf-rehberi-2026',
  '49': 'elektrikli-arac-sarj-istasyonu-rehberi-ac-dc-sarj-farklari-2026',
  '50': 'ges-kurulum-sureci-lisanssiz-gunes-enerjisi-santrali-adim-adim-rehber-2026',
  '51': 'solar-panel-yatirim-geri-donus-suresi-hesaplama-roi-rehberi-2026',
  '52': 'gunes-enerjisi-mevzuati-tesvikler-2026-guncel-rehber',
  '53': 'solar-panel-bakim-temizlik-rehberi-verim-kaybini-onleyin-2026',
  '54': 'blog',
};

// ─── v4.1 Product Canonical Map (416 entries) ───
// Maps product slug (last URL segment) → canonical full path
// Generated from DB: each product gets ONE canonical URL (brand subcategory preferred)
const CANONICAL_MAP = {
  '-batarya-yonetim-unitesi-chint-power-cps-ecd500':'/urunler/inverter-markalari/chint/-batarya-yonetim-unitesi-chint-power-cps-ecd500',
  '-solar-kablolar-h1z2z2k-15kv-dc':'/urunler/solar-kablo/-solar-kablolar-h1z2z2k-15kv-dc',
  '10-kv--500-metre':'/urunler/solar-kablo/10-kv--500-metre',
  '10-kw-ges-acil-mod-panosu':'/urunler/inverterler--invertor/10-kw-ges-acil-mod-panosu',
  '100-inverter--charger':'/urunler/inverter-markalari/victron/victron-quattro-48/10000/140100/100-inverter--charger',
  '1000w-offgrid-sistem':'/urunler/solar-paket-cesitleri/1000w-offgrid-sistem',
  '11000-offgrid-sistem':'/urunler/solar-paket-cesitleri/11000-offgrid-sistem',
  '2200w-offgrid-sistem':'/urunler/solar-paket-cesitleri/2200w-offgrid-sistem',
  '3000w-offgrid-sistem':'/urunler/solar-paket-cesitleri/3000w-offgrid-sistem',
  '32-a--22kw-3-fazli-elektrikli-arac-sarj-kablosu-tip-2--disi--erkek':'/urunler/elektrikli-arac-sarj-cihazi/32-a--22kw-3-fazli-elektrikli-arac-sarj-kablosu-tip-2--disi--erkek',
  '500-metre--temka-pe-4x2x23-awg-cat6-kablo':'/urunler/solar-kablo/500-metre--temka-pe-4x2x23-awg-cat6-kablo',
  '5500w-offgrid-sistem':'/urunler/solar-paket-cesitleri/5500w-offgrid-sistem',
  '6xur--disi':'/urunler/solar-konnektor/pvkst4/6xur--disi',
  '6xur--erkek':'/urunler/solar-konnektor/pvkbt4/6xur--erkek',
  '6xur--set--100-adet':'/urunler/solar-konnektor/pvkbt4/6xur--ve-pvkst4/6xur--set--100-adet',
  '750w-offgrid-sistem':'/urunler/solar-paket-cesitleri/750w-offgrid-sistem',
  '8-metre-32-a--22kw-3-fazli-elektrikli-arac-sarj-kablosu-tip-2--disi--erkek':'/urunler/elektrikli-arac-sarj-kablosu/8-metre-32-a--22kw-3-fazli-elektrikli-arac-sarj-kablosu-tip-2--disi--erkek',
  'AEL-KC-811-cift-yonlu-X-5A-Trafo-Bagli-sayac-TEDAS-MLZ--2017-062A-sartnamesine-uygun':'/urunler/solar-malzemeler/AEL-KC-811-cift-yonlu-X-5A-Trafo-Bagli-sayac-TEDAS-MLZ--2017-062A-sartnamesine-uygun',
  'EVLink-Parking-Dikili-Tip-22kW':'/urunler/elektrikli-arac-sarj-cihazi/EVLink-Parking-Dikili-Tip-22kW',
  'Jinko-JKS-B28837-CS-1066-kWh-RESS-lityum-pil':'/urunler/inverter-markalari/jinko-solar/Jinko-JKS-B28837-CS-1066-kWh-RESS-lityum-pil',
  'MAKEL-T610.AMT.2556-cift-yonlu-sayac':'/urunler/solar-malzemeler/MAKEL-T610.AMT.2556-cift-yonlu-sayac',
  'abb-terra-ac-wallbox-22-kw':'/urunler/elektrikli-arac-sarj-cihazi/abb-terra-ac-wallbox-22-kw',
  'abb-terra-dc-wallbox':'/urunler/elektrikli-arac-sarj-cihazi/abb-terra-dc-wallbox',
  'aeltf24-cift-yonlu-direkt-bagli':'/urunler/solar-malzemeler/aeltf24-cift-yonlu-direkt-bagli',
  'akim-trafolu-aeltf21-cift-yonlu-sayac':'/urunler/solar-malzemeler/akim-trafolu-aeltf21-cift-yonlu-sayac',
  'ar-ax-32-rfid-22-kw-elektrikli-arac-sarj-istasyonu':'/urunler/elektrikli-arac-sarj-cihazi/ar-ax-32-rfid-22-kw-elektrikli-arac-sarj-istasyonu',
  'arcelik--100-kw--solar-inverter':'/urunler/inverter-markalari/arcelik/arcelik--100-kw--solar-inverter',
  'arcelik-inv-100kt-arc':'/urunler/inverter-markalari/arcelik/arcelik-inv-100kt-arc',
  'arcelik-inv-10kth':'/urunler/inverter-markalari/arcelik/arcelik-inv-10kth',
  'arcelik-inv-15kt-arc':'/urunler/inverter-markalari/arcelik/arcelik-inv-15kt-arc',
  'arcelik-inv-20kt':'/urunler/inverter-markalari/arcelik/arcelik-inv-20kt',
  'arcelik-inv-20kt-arc':'/urunler/inverter-markalari/arcelik/arcelik-inv-20kt-arc',
  'arcelik-inv-30kt-arc':'/urunler/inverter-markalari/arcelik/arcelik-inv-30kt-arc',
  'arcelik-inv-8kt':'/urunler/inverter-markalari/arcelik/arcelik-inv-8kt',
  'arcelik-inv-8kth':'/urunler/inverter-markalari/arcelik/arcelik-inv-8kth',
  'arclk-132pvrt-gg-610':'/urunler/solar-panel-markalari/arcelik/arclk-132pvrt-gg-610',
  'arclk-132pvrt-gg-615':'/urunler/solar-panel-markalari/arcelik/arclk-132pvrt-gg-615',
  'arclk-132pvrt-gg-620':'/urunler/solar-panel-markalari/arcelik/arclk-132pvrt-gg-620',
  'arclk-132pvrt-gg-625':'/urunler/solar-panel-markalari/arcelik/arclk-132pvrt-gg-625',
  'arclk-144pv10rt-600':'/urunler/solar-panel-markalari/arcelik/arclk-144pv10rt-600',
  'arclk-144pv10rt-gg-600':'/urunler/solar-panel-markalari/arcelik/arclk-144pv10rt-gg-600',
  'arclk-144pv10rt-gg-605':'/urunler/solar-panel-markalari/arcelik/arclk-144pv10rt-gg-605',
  'arclk-144pv10rt-gg-610':'/urunler/solar-panel-markalari/arcelik/arclk-144pv10rt-gg-610',
  'arclk-144pv10rt-gg-615':'/urunler/solar-panel-markalari/arcelik/arclk-144pv10rt-gg-615',
  'arclk-144pv10t-gg-590':'/urunler/solar-panel-markalari/arcelik/arclk-144pv10t-gg-590',
  'arclk-144pv10t-gg-595':'/urunler/solar-panel-markalari/arcelik/arclk-144pv10t-gg-595',
  'arclk-144pv10t-gg-600':'/urunler/solar-panel-markalari/arcelik/arclk-144pv10t-gg-600',
  'battery-box-premium-hvs-module-256-kwh':'/urunler/byd-lityum-pil/battery-box-premium-hvs-module-256-kwh',
  'bbox-premium-hvs-51-512-kwh':'/urunler/byd-lityum-pil/bbox-premium-hvs-51-512-kwh',
  'bbox-premium-hvs-77-768-kwh':'/urunler/byd-lityum-pil/bbox-premium-hvs-77-768-kwh',
  'byd-battery-box-lv5-0-5-kwh-51-2v-lityum-enerji-depolama-bataryasi':'/urunler/byd-lityum-pil/byd-battery-box-lv5-0-5-kwh-51-2v-lityum-enerji-depolama-bataryasi',
  'byd-battery-box-lvl-premium-15-4-kwh-lityum-enerji-depolama-bataryasi':'/urunler/byd-lityum-pil/byd-battery-box-lvl-premium-15-4-kwh-lityum-enerji-depolama-bataryasi',
  'byd-battery-box-premium-hvm-11--11-kwh-lityum-enerji-depolama-bataryasi':'/urunler/byd-lityum-pil/byd-battery-box-premium-hvm-11--11-kwh-lityum-enerji-depolama-bataryasi',
  'byd-battery-box-premium-hvm-138--138-kwh-lityum-enerji-depolama-bataryasi':'/urunler/byd-lityum-pil/byd-battery-box-premium-hvm-138--138-kwh-lityum-enerji-depolama-bataryasi',
  'byd-battery-box-premium-hvm-166--166-kwh-lityum-enerji-depolama-bataryasi':'/urunler/byd-lityum-pil/byd-battery-box-premium-hvm-166--166-kwh-lityum-enerji-depolama-bataryasi',
  'byd-battery-box-premium-hvm-193--193-kwh-lityum-enerji-depolama-bataryas':'/urunler/byd-lityum-pil/byd-battery-box-premium-hvm-193--193-kwh-lityum-enerji-depolama-bataryas',
  'byd-battery-box-premium-hvm-221--221-kwh-lityum-enerji-depolama-bataryasi':'/urunler/byd-lityum-pil/byd-battery-box-premium-hvm-221--221-kwh-lityum-enerji-depolama-bataryasi',
  'byd-battery-box-premium-hvm-83--83-kwh-lityum-enerji-depolama-bataryasi':'/urunler/byd-lityum-pil/byd-battery-box-premium-hvm-83--83-kwh-lityum-enerji-depolama-bataryasi',
  'byd-battery-box-premium-hvs-102--102-kwh-lityum-enerji-depolama-bataryasi':'/urunler/byd-lityum-pil/byd-battery-box-premium-hvs-102--102-kwh-lityum-enerji-depolama-bataryasi',
  'byd-battery-box-premium-hvs-128--128-kwh-lityum-enerji-depolama-bataryasi':'/urunler/byd-lityum-pil/byd-battery-box-premium-hvs-128--128-kwh-lityum-enerji-depolama-bataryasi',
  'byd-bbox-premium-lvs-120-battery-storage-12-kwh':'/urunler/byd-lityum-pil/byd-bbox-premium-lvs-120-battery-storage-12-kwh',
  'byd-bbox-premium-lvs-160-battery-storage-16-kwh':'/urunler/byd-lityum-pil/byd-bbox-premium-lvs-160-battery-storage-16-kwh',
  'byd-bbox-premium-lvs-192-battery-storage-192-kwh':'/urunler/byd-lityum-pil/byd-bbox-premium-lvs-192-battery-storage-192-kwh',
  'byd-bbox-premium-lvs-240-battery-storage-24-kwh':'/urunler/byd-lityum-pil/byd-bbox-premium-lvs-240-battery-storage-24-kwh',
  'byd-bbox-premium-lvs-40-battery-storage-4-kwh':'/urunler/byd-lityum-pil/byd-bbox-premium-lvs-40-battery-storage-4-kwh',
  'byd-bbox-premium-lvs-80-battery-storage-8-kwh':'/urunler/byd-lityum-pil/byd-bbox-premium-lvs-80-battery-storage-8-kwh',
  'byd-flex-lite-bmu-turkiye-solar-market':'/urunler/byd-lityum-pil/byd-flex-lite-bmu-turkiye-solar-market',
  'byd-lv-flex-lite-5kwh':'/urunler/byd-lityum-pil/byd-lv-flex-lite-5kwh',
  'cati-kancasi':'/urunler/solar-malzemeler/cati-kancasi',
  'chint-power-cps-ecd51-alcak-voltaj-batarya-yonetim-unitesi-bmu':'/urunler/inverter-markalari/chint/chint-power-cps-ecd51-alcak-voltaj-batarya-yonetim-unitesi-bmu',
  'chint-power-cps-essr-05kl1-5-12-kwh-alcak-voltaj-lityum-batarya':'/urunler/inverter-markalari/chint/chint-power-cps-essr-05kl1-5-12-kwh-alcak-voltaj-lityum-batarya',
  'chint-power-cps-essr-10kl1-10-24-kwh-alcak-voltaj-lityum-batarya':'/urunler/inverter-markalari/chint/chint-power-cps-essr-10kl1-10-24-kwh-alcak-voltaj-lityum-batarya',
  'chint-power-cps-essr-15kl1-15-36-kwh-alcak-voltaj-lityum-batarya':'/urunler/inverter-markalari/chint/chint-power-cps-essr-15kl1-15-36-kwh-alcak-voltaj-lityum-batarya',
  'chint-power-cps-essr-20kl1-20-48-kwh-alcak-voltaj-lityum-batarya':'/urunler/inverter-markalari/chint/chint-power-cps-essr-20kl1-20-48-kwh-alcak-voltaj-lityum-batarya',
  'chint-power-ech10k-th-eu':'/urunler/inverter-markalari/chint/chint-power-ech10k-th-eu',
  'chint-power-ech12ktheu--12kw-hibrit-trifaze-solar-inverter':'/urunler/inverter-markalari/chint/chint-power-ech12ktheu--12kw-hibrit-trifaze-solar-inverter',
  'chint-power-ech15ktheu--15kw-hibrit-trifaze-solar-inverter':'/urunler/inverter-markalari/chint/chint-power-ech15ktheu--15kw-hibrit-trifaze-solar-inverter',
  'chint-power-ech18ktheu--18kw-hibrit-trifaze-solar-inverter':'/urunler/inverter-markalari/chint/chint-power-ech18ktheu--18kw-hibrit-trifaze-solar-inverter',
  'chint-power-ech20ktheu--20kw-hibrit-trifaze-solar-inverter':'/urunler/inverter-markalari/chint/chint-power-ech20ktheu--20kw-hibrit-trifaze-solar-inverter',
  'chint-power-ech3k-sml-eu-3-kw-tek-fazli-hibrit-inverter':'/urunler/inverter-markalari/chint/chint-power-ech3k-sml-eu-3-kw-tek-fazli-hibrit-inverter',
  'chint-power-ech5k-sml-eu-5-kw-tek-fazli-hibrit-inverter':'/urunler/inverter-markalari/chint/chint-power-ech5k-sml-eu-5-kw-tek-fazli-hibrit-inverter',
  'chint-power-ech6k-sml-eu-6-kw-tek-fazli-hibrit-inverter':'/urunler/inverter-markalari/chint/chint-power-ech6k-sml-eu-6-kw-tek-fazli-hibrit-inverter',
  'chint-power-ech8ktheu--8kw-hibrit-trifaze-solar-inverter':'/urunler/inverter-markalari/chint/chint-power-ech8ktheu--8kw-hibrit-trifaze-solar-inverter',
  'chint-power-sca15ktl-t1-ab-15-kw-uc-fazli-string-inverter':'/urunler/inverter-markalari/chint/chint-power-sca15ktl-t1-ab-15-kw-uc-fazli-string-inverter',
  'chint-power-sca20ktl-t1-ab-20-kw-uc-fazli-string-inverter':'/urunler/inverter-markalari/chint/chint-power-sca20ktl-t1-ab-20-kw-uc-fazli-string-inverter',
  'chint-power-sca25ktl-t1-ab-25-kw-uc-fazli-string-inverter':'/urunler/inverter-markalari/chint/chint-power-sca25ktl-t1-ab-25-kw-uc-fazli-string-inverter',
  'chint-power-sca30ktl-t1-ab-30-kw-uc-fazli-string-inverter':'/urunler/inverter-markalari/chint/chint-power-sca30ktl-t1-ab-30-kw-uc-fazli-string-inverter',
  'chint-power-sca50ktl-t-eu-50-kw-uc-fazli-string-inverter':'/urunler/inverter-markalari/chint/chint-power-sca50ktl-t-eu-50-kw-uc-fazli-string-inverter',
  'chs250kt6x-50-kw-hibrit-enerji-depolama-sistemi':'/urunler/all-in-one-hibrit-sistem/chs250kt6x-50-kw-hibrit-enerji-depolama-sistemi',
  'cwt-perc-monokristal-395wp-gunes-paneli':'/urunler/solar-panel-markalari/cwt-perc-monokristal-395wp-gunes-paneli',
  'deye-10-kw-mono-faz-hibrit-inverter-lv':'/urunler/inverter-markalari/deye/deye-10-kw-mono-faz-hibrit-inverter-lv',
  'deye-10-kw-mono-faz-on-grid-string-inverter':'/urunler/inverter-markalari/deye/deye-10-kw-mono-faz-on-grid-string-inverter',
  'deye-10-kw-tri-faz-hibrit-inverter-hv':'/urunler/inverter-markalari/deye/deye-10-kw-tri-faz-hibrit-inverter-hv',
  'deye-10-kw-tri-faz-hibrit-inverter-lv':'/urunler/inverter-markalari/deye/deye-10-kw-tri-faz-hibrit-inverter-lv',
  'deye-10-kw-tri-faz-on-grid-inverter':'/urunler/inverter-markalari/deye/deye-10-kw-tri-faz-on-grid-inverter',
  'deye-12-kw-tri-faz-hibrit-inverter-hv':'/urunler/inverter-markalari/deye/deye-12-kw-tri-faz-hibrit-inverter-hv',
  'deye-12-kw-tri-faz-hibrit-inverter-lv':'/urunler/inverter-markalari/deye/deye-12-kw-tri-faz-hibrit-inverter-lv',
  'deye-12-kw-tri-faz-on-grid-inverter':'/urunler/inverter-markalari/deye/deye-12-kw-tri-faz-on-grid-inverter',
  'deye-15-kw-tri-faz-hibrit-inverter-hv':'/urunler/inverter-markalari/deye/deye-15-kw-tri-faz-hibrit-inverter-hv',
  'deye-15-kw-tri-faz-hibrit-inverter-lv':'/urunler/inverter-markalari/deye/deye-15-kw-tri-faz-hibrit-inverter-lv',
  'deye-15-kw-tri-faz-on-grid-inverter':'/urunler/inverter-markalari/deye/deye-15-kw-tri-faz-on-grid-inverter',
  'deye-16-kw-mono-faz-hibrit-inverter-lv':'/urunler/inverter-markalari/deye/deye-16-kw-mono-faz-hibrit-inverter-lv',
  'deye-20-kw-tri-faz-hibrit-inverter-hv':'/urunler/inverter-markalari/deye/deye-20-kw-tri-faz-hibrit-inverter-hv',
  'deye-20-kw-tri-faz-hibrit-inverter-lv':'/urunler/inverter-markalari/deye/deye-20-kw-tri-faz-hibrit-inverter-lv',
  'deye-20-kw-tri-faz-on-grid-inverter':'/urunler/inverter-markalari/deye/deye-20-kw-tri-faz-on-grid-inverter',
  'deye-25-kw-tri-faz-hibrit-inverter-hv':'/urunler/inverter-markalari/deye/deye-25-kw-tri-faz-hibrit-inverter-hv',
  'deye-25-kw-tri-faz-on-grid-inverter':'/urunler/inverter-markalari/deye/deye-25-kw-tri-faz-on-grid-inverter',
  'deye-3-kw-mono-faz-on-grid-string-inverter':'/urunler/inverter-markalari/deye/deye-3-kw-mono-faz-on-grid-string-inverter',
  'deye-30-kw-tri-faz-hibrit-inverter-hv':'/urunler/inverter-markalari/deye/deye-30-kw-tri-faz-hibrit-inverter-hv',
  'deye-30-kw-tri-faz-on-grid-inverter':'/urunler/inverter-markalari/deye/deye-30-kw-tri-faz-on-grid-inverter',
  'deye-40-kw-tri-faz-hibrit-inverter-hv':'/urunler/inverter-markalari/deye/deye-40-kw-tri-faz-hibrit-inverter-hv',
  'deye-40-kw-tri-faz-on-grid-inverter':'/urunler/inverter-markalari/deye/deye-40-kw-tri-faz-on-grid-inverter',
  'deye-5-kw-mono-faz-hibrit-inverter-lv':'/urunler/inverter-markalari/deye/deye-5-kw-mono-faz-hibrit-inverter-lv',
  'deye-5-kw-mono-faz-on-grid-string-inverter':'/urunler/inverter-markalari/deye/deye-5-kw-mono-faz-on-grid-string-inverter',
  'deye-5-kw-tri-faz-on-grid-inverter':'/urunler/inverter-markalari/deye/deye-5-kw-tri-faz-on-grid-inverter',
  'deye-50-kw-tri-faz-hibrit-inverter-hv':'/urunler/inverter-markalari/deye/deye-50-kw-tri-faz-hibrit-inverter-hv',
  'deye-6-kw-mono-faz-hibrit-inverter-lv':'/urunler/inverter-markalari/deye/deye-6-kw-mono-faz-hibrit-inverter-lv',
  'deye-8-kw-mono-faz-on-grid-string-inverter':'/urunler/inverter-markalari/deye/deye-8-kw-mono-faz-on-grid-string-inverter',
  'deye-8-kw-tri-faz-hibrit-inverter-lv':'/urunler/inverter-markalari/deye/deye-8-kw-tri-faz-hibrit-inverter-lv',
  'deye-8-kw-tri-faz-on-grid-inverter':'/urunler/inverter-markalari/deye/deye-8-kw-tri-faz-on-grid-inverter',
  'deye-80-kw-tri-faz-hibrit-inverter-hv':'/urunler/inverter-markalari/deye/deye-80-kw-tri-faz-hibrit-inverter-hv',
  'deye-lan-stick':'/urunler/inverter-markalari/deye/deye-lan-stick',
  'deye-monofaze-smart-meter':'/urunler/inverter-markalari/deye/deye-monofaze-smart-meter',
  'deye-trifaze-smart-meter':'/urunler/inverter-markalari/deye/deye-trifaze-smart-meter',
  'deye-wifi-stick':'/urunler/inverter-markalari/deye/deye-wifi-stick',
  'dyness-bx51100-512v-100ah-ticari-lityum-batarya':'/urunler/dyness-lityum-pil/dyness-bx51100-512v-100ah-ticari-lityum-batarya',
  'dyness-bx51100-bdu-ticari-batarya-dagitim-unitesi':'/urunler/dyness-lityum-pil/dyness-bx51100-bdu-ticari-batarya-dagitim-unitesi',
  'dyness-tower-pro-t10-bdu-batarya-dagitim-unitesi':'/urunler/dyness-lityum-pil/dyness-tower-pro-t10-bdu-batarya-dagitim-unitesi',
  'dyness-tower-t10-bdu-batarya-dagitim-unitesi':'/urunler/dyness-lityum-pil/dyness-tower-t10-bdu-batarya-dagitim-unitesi',
  'dyness-tower-t10-hv-10-kwh-yuksek-gerilim-lityum-batarya':'/urunler/dyness-lityum-pil/dyness-tower-t10-hv-10-kwh-yuksek-gerilim-lityum-batarya',
  'dyness-tower-t10-hv-96-kwh-yuksek-gerilim-lityum-batarya':'/urunler/dyness-lityum-pil/dyness-tower-t10-hv-96-kwh-yuksek-gerilim-lityum-batarya',
  'eastron--sdm630mct-turkiye':'/urunler/solar-malzemeler/eastron--sdm630mct-turkiye',
  'elk-arac-sarj-evlink-smart-wallbox-22kw-t2-soketli-rfid':'/urunler/elektrikli-arac-sarj-cihazi/elk-arac-sarj-evlink-smart-wallbox-22kw-t2-soketli-rfid',
  'enerji-depolama-chint-power-ebm032050lf-h':'/urunler/inverter-markalari/chint/enerji-depolama-chint-power-ebm032050lf-h',
  'fronius-adaptor-15w-240v-12v':'/urunler/inverter-markalari/fronius/fronius-adaptor-15w-240v-12v',
  'fronius-argeno-125--125-kw-trifaze-saha-tipi-solar-inverter':'/urunler/inverter-markalari/fronius/fronius-argeno-125--125-kw-trifaze-saha-tipi-solar-inverter',
  'fronius-argeno-125-afci--125-kw-trifaze-saha-tipi-solar-inverter-yangin-koruma--afci':'/urunler/inverter-markalari/fronius/fronius-argeno-125-afci--125-kw-trifaze-saha-tipi-solar-inverter-yangin-koruma--afci',
  'fronius-backup-controller-3p-35a':'/urunler/inverter-markalari/fronius/fronius-backup-controller-3p-35a',
  'fronius-backup-switch-1p-3p-63a':'/urunler/inverter-markalari/fronius/fronius-backup-switch-1p-3p-63a',
  'fronius-backup-switch-1pn-3pn-63a':'/urunler/inverter-markalari/fronius/fronius-backup-switch-1pn-3pn-63a',
  'fronius-datamanager-20-box-wlan':'/urunler/inverter-markalari/fronius/fronius-datamanager-20-box-wlan',
  'fronius-datamanager-20-wlan':'/urunler/inverter-markalari/fronius/fronius-datamanager-20-wlan',
  'fronius-eco---2703s-wlan':'/urunler/inverterler--invertor/fronius-eco---2703s-wlan',
  'fronius-gen24-120-plus-sc':'/urunler/inverter-markalari/fronius/fronius-gen24-120-plus-sc',
  'fronius-isinim-sensoru':'/urunler/inverter-markalari/fronius/fronius-isinim-sensoru',
  'fronius-modul-sicaklik-sensoru':'/urunler/inverter-markalari/fronius/fronius-modul-sicaklik-sensoru',
  'fronius-ohmpilot-903-ohmpilot--akilli-pv-tuketim-ve-su-isitma-cihazi-enerji-yonetimi-9kw-3-faz':'/urunler/solar-malzemeler/fronius-ohmpilot-903-ohmpilot--akilli-pv-tuketim-ve-su-isitma-cihazi-enerji-yonetimi-9kw-3-faz',
  'fronius-ohmpilot-eco':'/urunler/inverter-markalari/fronius/fronius-ohmpilot-eco',
  'fronius-ortam-sicaklik-sensoru':'/urunler/inverter-markalari/fronius/fronius-ortam-sicaklik-sensoru',
  'fronius-primo-gen24-100':'/urunler/inverter-markalari/fronius/fronius-primo-gen24-100',
  'fronius-primo-gen24-100-plus':'/urunler/inverter-markalari/fronius/fronius-primo-gen24-100-plus',
  'fronius-primo-gen24-30':'/urunler/inverter-markalari/fronius/fronius-primo-gen24-30',
  'fronius-primo-gen24-30-plus':'/urunler/inverter-markalari/fronius/fronius-primo-gen24-30-plus',
  'fronius-primo-gen24-36':'/urunler/inverter-markalari/fronius/fronius-primo-gen24-36',
  'fronius-primo-gen24-36-plus':'/urunler/inverter-markalari/fronius/fronius-primo-gen24-36-plus',
  'fronius-primo-gen24-40':'/urunler/inverter-markalari/fronius/fronius-primo-gen24-40',
  'fronius-primo-gen24-40-plus':'/urunler/inverter-markalari/fronius/fronius-primo-gen24-40-plus',
  'fronius-primo-gen24-46':'/urunler/inverter-markalari/fronius/fronius-primo-gen24-46',
  'fronius-primo-gen24-46-plus':'/urunler/inverter-markalari/fronius/fronius-primo-gen24-46-plus',
  'fronius-primo-gen24-50':'/urunler/inverter-markalari/fronius/fronius-primo-gen24-50',
  'fronius-primo-gen24-50-plus':'/urunler/inverter-markalari/fronius/fronius-primo-gen24-50-plus',
  'fronius-primo-gen24-60':'/urunler/inverter-markalari/fronius/fronius-primo-gen24-60',
  'fronius-primo-gen24-60-plus':'/urunler/inverter-markalari/fronius/fronius-primo-gen24-60-plus',
  'fronius-primo-gen24-80':'/urunler/inverter-markalari/fronius/fronius-primo-gen24-80',
  'fronius-primo-gen24-80-plus':'/urunler/inverter-markalari/fronius/fronius-primo-gen24-80-plus',
  'fronius-pv-point-comfort':'/urunler/inverter-markalari/fronius/fronius-pv-point-comfort',
  'fronius-reserva-12-6':'/urunler/fronius-reserva-pil/fronius-reserva-12-6',
  'fronius-reserva-15-8':'/urunler/fronius-reserva-pil/fronius-reserva-15-8',
  'fronius-reserva-63--63-kwh-akilli-lityum-enerji-depolama-bataryasi':'/urunler/fronius-reserva-pil/fronius-reserva-63--63-kwh-akilli-lityum-enerji-depolama-bataryasi',
  'fronius-reserva-9-5':'/urunler/fronius-reserva-pil/fronius-reserva-9-5',
  'fronius-rfid-etiketler-10-adet':'/urunler/inverter-markalari/fronius/fronius-rfid-etiketler-10-adet',
  'fronius-ruzgar-sensoru':'/urunler/inverter-markalari/fronius/fronius-ruzgar-sensoru',
  'fronius-sensor-kutusu':'/urunler/inverter-markalari/fronius/fronius-sensor-kutusu',
  'fronius-smart-meter-63a1':'/urunler/solar-malzemeler/fronius-smart-meter-63a1',
  'fronius-smart-meter-63a3':'/urunler/solar-malzemeler/fronius-smart-meter-63a3',
  'fronius-smart-meter-ip':'/urunler/solar-malzemeler/fronius-smart-meter-ip',
  'fronius-smart-meter-ts-5ka3':'/urunler/solar-malzemeler/fronius-smart-meter-ts-5ka3',
  'fronius-smart-meter-ts-65a3--akilli-enerji-sayac-trifaze-65a-dogru-olcum-gelismis-izleme':'/urunler/solar-malzemeler/fronius-smart-meter-ts-65a3--akilli-enerji-sayac-trifaze-65a-dogru-olcum-gelismis-izleme',
  'fronius-symo-1003m-wlan--10-kw-uc-faz-trifaze-ongrid-solar-inverter-dahili-wifi':'/urunler/inverter-markalari/fronius/fronius-symo-1003m-wlan--10-kw-uc-faz-trifaze-ongrid-solar-inverter-dahili-wifi',
  'fronius-symo-advanced-12-5-3-m':'/urunler/inverter-markalari/fronius/fronius-symo-advanced-12-5-3-m',
  'fronius-symo-advanced-15-0-3-m':'/urunler/inverter-markalari/fronius/fronius-symo-advanced-15-0-3-m',
  'fronius-symo-advanced-1753m--175-kw-uc-faz-trifaze-ongrid-solar-inverter':'/urunler/inverter-markalari/fronius/fronius-symo-advanced-1753m--175-kw-uc-faz-trifaze-ongrid-solar-inverter',
  'fronius-symo-advanced-2003m--20-kw-uc-faz-trifaze-ongrid-solar-inverter':'/urunler/inverter-markalari/fronius/fronius-symo-advanced-2003m--20-kw-uc-faz-trifaze-ongrid-solar-inverter',
  'fronius-symo-gen24-10-0-plus':'/urunler/inverter-markalari/fronius/fronius-symo-gen24-10-0-plus',
  'fronius-symo-gen24-100':'/urunler/inverter-markalari/fronius/fronius-symo-gen24-100',
  'fronius-symo-gen24-120-sc':'/urunler/inverter-markalari/fronius/fronius-symo-gen24-120-sc',
  'fronius-symo-gen24-3-0':'/urunler/inverter-markalari/fronius/fronius-symo-gen24-3-0',
  'fronius-symo-gen24-30':'/urunler/inverter-markalari/fronius/fronius-symo-gen24-30',
  'fronius-symo-gen24-40':'/urunler/inverter-markalari/fronius/fronius-symo-gen24-40',
  'fronius-symo-gen24-40-plus--4-kw-uc-faz-trifaze-ongrid-solar-inverter':'/urunler/inverter-markalari/fronius/fronius-symo-gen24-40-plus--4-kw-uc-faz-trifaze-ongrid-solar-inverter',
  'fronius-symo-gen24-5-0-plus':'/urunler/inverter-markalari/fronius/fronius-symo-gen24-5-0-plus',
  'fronius-symo-gen24-50':'/urunler/inverter-markalari/fronius/fronius-symo-gen24-50',
  'fronius-symo-gen24-6-0-plus':'/urunler/inverter-markalari/fronius/fronius-symo-gen24-6-0-plus',
  'fronius-symo-gen24-60':'/urunler/inverter-markalari/fronius/fronius-symo-gen24-60',
  'fronius-symo-gen24-8-0-plus':'/urunler/inverter-markalari/fronius/fronius-symo-gen24-8-0-plus',
  'fronius-symo-gen24-80':'/urunler/inverter-markalari/fronius/fronius-symo-gen24-80',
  'fronius-tauro-503d--50-kw-trifaze-saha-tipi-solar-inverter':'/urunler/inverter-markalari/fronius/fronius-tauro-503d--50-kw-trifaze-saha-tipi-solar-inverter',
  'fronius-tauro-eco-1003d-30a--100-kw-trifaze-saha-tipi-solar-inverter-30a-dc-giris-yuksek-akim-buyuk-projeler-icin-lider-teknoloji':'/urunler/inverter-markalari/fronius/fronius-tauro-eco-1003d-30a--100-kw-trifaze-saha-tipi-solar-inverter-30a-dc-giris-yuksek-akim-buyuk-projeler-icin-lider-teknoloji',
  'fronius-tauro-eco-1003d-afci-20a--100-kw-trifaze-saha-tipi-solar-inverter-afci-koruma-coklu-mppt-endustriyel-proje-inverteri':'/urunler/inverter-markalari/fronius/fronius-tauro-eco-1003d-afci-20a--100-kw-trifaze-saha-tipi-solar-inverter-afci-koruma-coklu-mppt-endustriyel-proje-inverteri',
  'fronius-tauro-eco-503d--50-kw-trifaze-saha-tipi-solar-inverter':'/urunler/inverter-markalari/fronius/fronius-tauro-eco-503d--50-kw-trifaze-saha-tipi-solar-inverter',
  'fronius-tip-2-duvar-braketi':'/urunler/inverter-markalari/fronius/fronius-tip-2-duvar-braketi',
  'fronius-tip-2-sarj-kablosu-25m':'/urunler/inverter-markalari/fronius/fronius-tip-2-sarj-kablosu-25m',
  'fronius-tip-2-sarj-kablosu-5m':'/urunler/inverter-markalari/fronius/fronius-tip-2-sarj-kablosu-5m',
  'fronius-tip-2-sarj-kablosu-75m':'/urunler/inverter-markalari/fronius/fronius-tip-2-sarj-kablosu-75m',
  'fronius-verto-150-plus-spd-12':'/urunler/inverter-markalari/fronius/fronius-verto-150-plus-spd-12',
  'fronius-verto-150-spd-12':'/urunler/inverter-markalari/fronius/fronius-verto-150-spd-12',
  'fronius-verto-175-plus-spd-12':'/urunler/inverter-markalari/fronius/fronius-verto-175-plus-spd-12',
  'fronius-verto-175-spd-12':'/urunler/inverter-markalari/fronius/fronius-verto-175-spd-12',
  'fronius-verto-200-plus-spd-12':'/urunler/inverter-markalari/fronius/fronius-verto-200-plus-spd-12',
  'fronius-verto-200-spd-12':'/urunler/inverter-markalari/fronius/fronius-verto-200-spd-12',
  'fronius-verto-250-plus-spd-12':'/urunler/inverter-markalari/fronius/fronius-verto-250-plus-spd-12',
  'fronius-verto-250-spd-12--25-kw-trifaze-solar-inverter-entegre-parafudr-premium-koruma':'/urunler/inverter-markalari/fronius/fronius-verto-250-spd-12--25-kw-trifaze-solar-inverter-entegre-parafudr-premium-koruma',
  'fronius-verto-270-spd-12--27-kw-trifaze-solar-inverter-entegre-parafudr-yuksek-verimlilik-premium-koruma':'/urunler/inverter-markalari/fronius/fronius-verto-270-spd-12--27-kw-trifaze-solar-inverter-entegre-parafudr-yuksek-verimlilik-premium-koruma',
  'fronius-verto-300-plus-spd-12':'/urunler/inverter-markalari/fronius/fronius-verto-300-plus-spd-12',
  'fronius-verto-300-spd-12--30-kw-trifaze-solar-inverter-entegre-parafudr-yuksek-verimlilik-premium-koruma':'/urunler/inverter-markalari/fronius/fronius-verto-300-spd-12--30-kw-trifaze-solar-inverter-entegre-parafudr-yuksek-verimlilik-premium-koruma',
  'fronius-verto-333-plus-spd-12':'/urunler/inverter-markalari/fronius/fronius-verto-333-plus-spd-12',
  'fronius-verto-333-spd-12--333-kw-trifaze-solar-inverter-entegre-parafudr-yuksek-verimlilik-premium-koruma':'/urunler/inverter-markalari/fronius/fronius-verto-333-spd-12--333-kw-trifaze-solar-inverter-entegre-parafudr-yuksek-verimlilik-premium-koruma',
  'fronius-wattpilot-flex-home-22-c6':'/urunler/elektrikli-arac-sarj-cihazi/fronius-wattpilot-flex-home-22-c6',
  'fronius-wattpilot-flex-pro-22-c6e':'/urunler/elektrikli-arac-sarj-cihazi/fronius-wattpilot-flex-pro-22-c6e',
  'fronius-wattpilot-go-20-montaj-plakasi':'/urunler/inverter-markalari/fronius/fronius-wattpilot-go-20-montaj-plakasi',
  'fronius-wattpilot-go-22-adaptor-seti':'/urunler/inverter-markalari/fronius/fronius-wattpilot-go-22-adaptor-seti',
  'fronius-wattpilot-go-22-cee16-kirmizi':'/urunler/inverter-markalari/fronius/fronius-wattpilot-go-22-cee16-kirmizi',
  'fronius-wattpilot-go-22-cee16-mavi':'/urunler/inverter-markalari/fronius/fronius-wattpilot-go-22-cee16-mavi',
  'fronius-wattpilot-go-22-j':'/urunler/elektrikli-arac-sarj-cihazi/fronius-wattpilot-go-22-j',
  'fronius-wattpilot-go-22-type-f':'/urunler/inverter-markalari/fronius/fronius-wattpilot-go-22-type-f',
  'growatt-spf-5000tl-hvmp-48v-offgrid-inverter':'/urunler/off-grid-inverter/growatt-spf-5000tl-hvmp-48v-offgrid-inverter',
  'huawei-sun2000-100ktl-m2':'/urunler/inverter-markalari/huawei/huawei-sun2000-100ktl-m2',
  'huawei-sun2000-50ktl-m3':'/urunler/inverter-markalari/huawei/huawei-sun2000-50ktl-m3',
  'isotrap-mini-trapez--sandvic-cati-montaj-sistemi':'/urunler/solar-malzemeler/isotrap-mini-trapez--sandvic-cati-montaj-sistemi',
  'isotrap-tile-pro':'/urunler/solar-malzemeler/isotrap-tile-pro',
  'istanbul-dc-40-kw-elektrikli-arac-sarj-istasyonu':'/urunler/elektrikli-arac-sarj-cihazi/istanbul-dc-40-kw-elektrikli-arac-sarj-istasyonu',
  'jinko-jks10hei-10-kw-hibrit-inverter':'/urunler/inverter-markalari/jinko-solar/jinko-jks10hei-10-kw-hibrit-inverter',
  'jinko-jks12hei-12-kw-hibrit-inverter':'/urunler/inverter-markalari/jinko-solar/jinko-jks12hei-12-kw-hibrit-inverter',
  'jinko-jks15hei-15-kw-hibrit-inverter':'/urunler/inverter-markalari/jinko-solar/jinko-jks15hei-15-kw-hibrit-inverter',
  'jinko-jks20hei-20-kw-hibrit-inverter':'/urunler/inverter-markalari/jinko-solar/jinko-jks20hei-20-kw-hibrit-inverter',
  'jinko-jks8hei-8-kw-hibrit-inverter':'/urunler/inverter-markalari/jinko-solar/jinko-jks8hei-8-kw-hibrit-inverter',
  'jinko-jksb19237cs-71-kwh-ress-lityum-batarya-modulu':'/urunler/inverter-markalari/jinko-solar/jinko-jksb19237cs-71-kwh-ress-lityum-batarya-modulu',
  'jinko-jksb38437cs-142-kwh-ress-lityum-batarya-modulu':'/urunler/inverter-markalari/jinko-solar/jinko-jksb38437cs-142-kwh-ress-lityum-batarya-modulu',
  'jinko-jksb38437cs-1775-kwh-ress-lityum-batarya-modulu':'/urunler/inverter-markalari/jinko-solar/jinko-jksb38437cs-1775-kwh-ress-lityum-batarya-modulu',
  'jinko-jksb38437cs-2125-kwh-ress-lityum-batarya-modulu':'/urunler/inverter-markalari/jinko-solar/jinko-jksb38437cs-2125-kwh-ress-lityum-batarya-modulu',
  'jksb28837cs-Jinko-Solar-Lityum-Pil':'/urunler/inverter-markalari/jinko-solar/jksb28837cs-Jinko-Solar-Lityum-Pil',
  'makel-c520amt2556-class-05-cift-yonlu-sayac-rs485':'/urunler/solar-malzemeler/makel-c520amt2556-class-05-cift-yonlu-sayac-rs485',
  'nak-kablo--6-mm-solar-kablo---siyah':'/urunler/solar-kablo/nak-kablo--6-mm-solar-kablo---siyah',
  'nak-kablo--6-mm-solar-kablo---siyah-1-metre':'/urunler/solar-kablo/nak-kablo--6-mm-solar-kablo---siyah-1-metre',
  'nak-kablo--6-mm-solar-kablo-5km':'/urunler/solar-kablo/nak-kablo--6-mm-solar-kablo-5km',
  'orbus-10kw-hibrit-sistem-hazir-sistem':'/urunler/inverter-markalari/orbus/orbus-10kw-hibrit-sistem-hazir-sistem',
  'orbus-10kw-hibrit-sistem-paket':'/urunler/inverter-markalari/orbus/orbus-10kw-hibrit-sistem-paket',
  'osarj-ac-22-kw-elektrikli-arac-sarj-istasyonu':'/urunler/elektrikli-arac-sarj-cihazi/osarj-ac-22-kw-elektrikli-arac-sarj-istasyonu',
  'osarj-ac-22-kw-elektrikli-arac-sarj-istasyonu-stand-haric':'/urunler/elektrikli-arac-sarj-cihazi/osarj-ac-22-kw-elektrikli-arac-sarj-istasyonu-stand-haric',
  'osarj-dc-30-kw-elektrikli-arac-sarj-istasyonu':'/urunler/elektrikli-arac-sarj-cihazi/osarj-dc-30-kw-elektrikli-arac-sarj-istasyonu',
  'oznur-solar-kablo':'/urunler/solar-kablo/oznur-solar-kablo',
  'panasonic-ae7h395vc5b':'/urunler/solar-panel-markalari/panasonic/panasonic-ae7h395vc5b',
  'rcelik-inv-12kth':'/urunler/inverter-markalari/arcelik/rcelik-inv-12kth',
  'solinved-1-5-5-5-kw-pompa-surucu-panosu':'/urunler/inverter-markalari/solinved/solinved-1-5-5-5-kw-pompa-surucu-panosu',
  'solinved-1-5-kw-mono-faz-solar-pompa-surucu-220v':'/urunler/inverter-markalari/solinved/solinved-1-5-kw-mono-faz-solar-pompa-surucu-220v',
  'solinved-1-5-kw-tri-faz-solar-pompa-surucu-380v':'/urunler/inverter-markalari/solinved/solinved-1-5-kw-tri-faz-solar-pompa-surucu-380v',
  'solinved-1000w-modified-sine-inverter-12v':'/urunler/inverter-markalari/solinved/solinved-1000w-modified-sine-inverter-12v',
  'solinved-1000w-pure-sine-inverter-12v':'/urunler/inverter-markalari/solinved/solinved-1000w-pure-sine-inverter-12v',
  'solinved-1000w-pure-sine-ups-inverter-12v':'/urunler/inverter-markalari/solinved/solinved-1000w-pure-sine-ups-inverter-12v',
  'solinved-100a-mppt-sarj-kontrol-cihazi-12v-48v':'/urunler/inverter-markalari/solinved/solinved-100a-mppt-sarj-kontrol-cihazi-12v-48v',
  'solinved-102-4v-100ah-lityum-duvar-tipi-batarya':'/urunler/inverter-markalari/solinved/solinved-102-4v-100ah-lityum-duvar-tipi-batarya',
  'solinved-10a-pwm-sarj-kontrol-cihazi-12-24v':'/urunler/inverter-markalari/solinved/solinved-10a-pwm-sarj-kontrol-cihazi-12-24v',
  'solinved-11-kw-tri-faz-solar-pompa-surucu-380v':'/urunler/inverter-markalari/solinved/solinved-11-kw-tri-faz-solar-pompa-surucu-380v',
  'solinved-110-kw-tri-faz-solar-pompa-surucu-380v':'/urunler/inverter-markalari/solinved/solinved-110-kw-tri-faz-solar-pompa-surucu-380v',
  'solinved-12v-100ah-lityum-batarya':'/urunler/inverter-markalari/solinved/solinved-12v-100ah-lityum-batarya',
  'solinved-12v-100ah-solar-jel-aku-deep-cycle':'/urunler/inverter-markalari/solinved/solinved-12v-100ah-solar-jel-aku-deep-cycle',
  'solinved-12v-12ah-kursun-asit-aku':'/urunler/inverter-markalari/solinved/solinved-12v-12ah-kursun-asit-aku',
  'solinved-12v-14ah-e-bike-batarya':'/urunler/inverter-markalari/solinved/solinved-12v-14ah-e-bike-batarya',
  'solinved-12v-150ah-solar-jel-aku-deep-cycle':'/urunler/inverter-markalari/solinved/solinved-12v-150ah-solar-jel-aku-deep-cycle',
  'solinved-12v-200ah-solar-jel-aku-deep-cycle':'/urunler/inverter-markalari/solinved/solinved-12v-200ah-solar-jel-aku-deep-cycle',
  'solinved-12v-24ah-e-bike-batarya':'/urunler/inverter-markalari/solinved/solinved-12v-24ah-e-bike-batarya',
  'solinved-12v-24ah-premium-e-bike-batarya':'/urunler/inverter-markalari/solinved/solinved-12v-24ah-premium-e-bike-batarya',
  'solinved-12v-7ah-kursun-asit-aku':'/urunler/inverter-markalari/solinved/solinved-12v-7ah-kursun-asit-aku',
  'solinved-12v-7ah-premium-kursun-asit-aku':'/urunler/inverter-markalari/solinved/solinved-12v-7ah-premium-kursun-asit-aku',
  'solinved-12v-9ah-kursun-asit-aku':'/urunler/inverter-markalari/solinved/solinved-12v-9ah-kursun-asit-aku',
  'solinved-15-kw-tri-faz-solar-pompa-surucu-380v':'/urunler/inverter-markalari/solinved/solinved-15-kw-tri-faz-solar-pompa-surucu-380v',
  'solinved-1500w-modified-sine-inverter-12v':'/urunler/inverter-markalari/solinved/solinved-1500w-modified-sine-inverter-12v',
  'solinved-1500w-modified-sine-inverter-24v':'/urunler/inverter-markalari/solinved/solinved-1500w-modified-sine-inverter-24v',
  'solinved-1500w-pure-sine-inverter-12v':'/urunler/inverter-markalari/solinved/solinved-1500w-pure-sine-inverter-12v',
  'solinved-1500w-pure-sine-inverter-24v':'/urunler/inverter-markalari/solinved/solinved-1500w-pure-sine-inverter-24v',
  'solinved-1500w-pure-sine-ups-inverter-12v':'/urunler/inverter-markalari/solinved/solinved-1500w-pure-sine-ups-inverter-12v',
  'solinved-16a-1000v-dc-sigorta':'/urunler/inverter-markalari/solinved/solinved-16a-1000v-dc-sigorta',
  'solinved-18-5-22-kw-pompa-surucu-panosu':'/urunler/inverter-markalari/solinved/solinved-18-5-22-kw-pompa-surucu-panosu',
  'solinved-18-5-kw-tri-faz-solar-pompa-surucu-380v':'/urunler/inverter-markalari/solinved/solinved-18-5-kw-tri-faz-solar-pompa-surucu-380v',
  'solinved-2-2-kw-mono-faz-solar-pompa-surucu-220v':'/urunler/inverter-markalari/solinved/solinved-2-2-kw-mono-faz-solar-pompa-surucu-220v',
  'solinved-2-2-kw-tri-faz-solar-pompa-surucu-380v':'/urunler/inverter-markalari/solinved/solinved-2-2-kw-tri-faz-solar-pompa-surucu-380v',
  'solinved-2-2-kw-tri-faz-solar-pompa-surucu-3x220v':'/urunler/inverter-markalari/solinved/solinved-2-2-kw-tri-faz-solar-pompa-surucu-3x220v',
  'solinved-2000w-modified-sine-inverter-12v':'/urunler/inverter-markalari/solinved/solinved-2000w-modified-sine-inverter-12v',
  'solinved-2000w-pure-sine-inverter-12v':'/urunler/inverter-markalari/solinved/solinved-2000w-pure-sine-inverter-12v',
  'solinved-20a-mppt-sarj-kontrol-cihazi-12v-24v':'/urunler/inverter-markalari/solinved/solinved-20a-mppt-sarj-kontrol-cihazi-12v-24v',
  'solinved-20a-pwm-sarj-kontrol-cihazi-12-24v':'/urunler/inverter-markalari/solinved/solinved-20a-pwm-sarj-kontrol-cihazi-12-24v',
  'solinved-22-kw-tri-faz-solar-pompa-surucu-380v':'/urunler/inverter-markalari/solinved/solinved-22-kw-tri-faz-solar-pompa-surucu-380v',
  'solinved-24v-100ah-lityum-batarya':'/urunler/inverter-markalari/solinved/solinved-24v-100ah-lityum-batarya',
  'solinved-2500w-modified-sine-inverter-12v':'/urunler/inverter-markalari/solinved/solinved-2500w-modified-sine-inverter-12v',
  'solinved-2500w-pure-sine-inverter-12v':'/urunler/inverter-markalari/solinved/solinved-2500w-pure-sine-inverter-12v',
  'solinved-2x10-solar-montaj-yapi-seti':'/urunler/inverter-markalari/solinved/solinved-2x10-solar-montaj-yapi-seti',
  'solinved-2x15-solar-montaj-yapi-seti':'/urunler/inverter-markalari/solinved/solinved-2x15-solar-montaj-yapi-seti',
  'solinved-2x4-solar-montaj-yapi-seti':'/urunler/inverter-markalari/solinved/solinved-2x4-solar-montaj-yapi-seti',
  'solinved-2x5-solar-montaj-yapi-seti':'/urunler/inverter-markalari/solinved/solinved-2x5-solar-montaj-yapi-seti',
  'solinved-2x7-solar-montaj-yapi-seti':'/urunler/inverter-markalari/solinved/solinved-2x7-solar-montaj-yapi-seti',
  'solinved-2x8-solar-montaj-yapi-seti':'/urunler/inverter-markalari/solinved/solinved-2x8-solar-montaj-yapi-seti',
  'solinved-2x9-solar-montaj-yapi-seti':'/urunler/inverter-markalari/solinved/solinved-2x9-solar-montaj-yapi-seti',
  'solinved-30-37-kw-pompa-surucu-panosu':'/urunler/inverter-markalari/solinved/solinved-30-37-kw-pompa-surucu-panosu',
  'solinved-30-kw-tri-faz-solar-pompa-surucu-380v':'/urunler/inverter-markalari/solinved/solinved-30-kw-tri-faz-solar-pompa-surucu-380v',
  'solinved-3000w-modified-sine-inverter-24v':'/urunler/inverter-markalari/solinved/solinved-3000w-modified-sine-inverter-24v',
  'solinved-3000w-pure-sine-inverter-12v':'/urunler/inverter-markalari/solinved/solinved-3000w-pure-sine-inverter-12v',
  'solinved-3000w-pure-sine-inverter-24v':'/urunler/inverter-markalari/solinved/solinved-3000w-pure-sine-inverter-24v',
  'solinved-300w-modified-sine-inverter-12v':'/urunler/inverter-markalari/solinved/solinved-300w-modified-sine-inverter-12v',
  'solinved-30a-mppt-sarj-kontrol-cihazi-12v-24v':'/urunler/inverter-markalari/solinved/solinved-30a-mppt-sarj-kontrol-cihazi-12v-24v',
  'solinved-30a-pwm-sarj-kontrol-cihazi-12-24v':'/urunler/inverter-markalari/solinved/solinved-30a-pwm-sarj-kontrol-cihazi-12-24v',
  'solinved-32a-1000v-dc-sigorta':'/urunler/inverter-markalari/solinved/solinved-32a-1000v-dc-sigorta',
  'solinved-37-kw-tri-faz-solar-pompa-surucu-380v':'/urunler/inverter-markalari/solinved/solinved-37-kw-tri-faz-solar-pompa-surucu-380v',
  'solinved-4-kw-mono-faz-solar-pompa-surucu-220v':'/urunler/inverter-markalari/solinved/solinved-4-kw-mono-faz-solar-pompa-surucu-220v',
  'solinved-4-kw-tri-faz-solar-pompa-surucu-380v':'/urunler/inverter-markalari/solinved/solinved-4-kw-tri-faz-solar-pompa-surucu-380v',
  'solinved-4-kw-tri-faz-solar-pompa-surucu-3x220v':'/urunler/inverter-markalari/solinved/solinved-4-kw-tri-faz-solar-pompa-surucu-3x220v',
  'solinved-4000w-pure-sine-inverter-12v':'/urunler/inverter-markalari/solinved/solinved-4000w-pure-sine-inverter-12v',
  'solinved-40a-mppt-sarj-kontrol-cihazi-12v-24v':'/urunler/inverter-markalari/solinved/solinved-40a-mppt-sarj-kontrol-cihazi-12v-24v',
  'solinved-40a-pwm-sarj-kontrol-cihazi-12-24v':'/urunler/inverter-markalari/solinved/solinved-40a-pwm-sarj-kontrol-cihazi-12-24v',
  'solinved-45-55-kw-pompa-surucu-panosu':'/urunler/inverter-markalari/solinved/solinved-45-55-kw-pompa-surucu-panosu',
  'solinved-45-kw-tri-faz-solar-pompa-surucu-380v':'/urunler/inverter-markalari/solinved/solinved-45-kw-tri-faz-solar-pompa-surucu-380v',
  'solinved-5-5-kw-tri-faz-solar-pompa-surucu-380v':'/urunler/inverter-markalari/solinved/solinved-5-5-kw-tri-faz-solar-pompa-surucu-380v',
  'solinved-51-2v-300ah-lityum-duvar-tipi-batarya':'/urunler/inverter-markalari/solinved/solinved-51-2v-300ah-lityum-duvar-tipi-batarya',
  'solinved-55-kw-tri-faz-solar-pompa-surucu-380v':'/urunler/inverter-markalari/solinved/solinved-55-kw-tri-faz-solar-pompa-surucu-380v',
  'solinved-600w-modified-sine-inverter-12v':'/urunler/inverter-markalari/solinved/solinved-600w-modified-sine-inverter-12v',
  'solinved-600w-pure-sine-inverter-12v':'/urunler/inverter-markalari/solinved/solinved-600w-pure-sine-inverter-12v',
  'solinved-600w-pure-sine-ups-inverter-12v':'/urunler/inverter-markalari/solinved/solinved-600w-pure-sine-ups-inverter-12v',
  'solinved-60a-mppt-sarj-kontrol-cihazi-12v-48v':'/urunler/inverter-markalari/solinved/solinved-60a-mppt-sarj-kontrol-cihazi-12v-48v',
  'solinved-7-5-15-kw-pompa-surucu-panosu':'/urunler/inverter-markalari/solinved/solinved-7-5-15-kw-pompa-surucu-panosu',
  'solinved-7-5-kw-tri-faz-solar-pompa-surucu-380v':'/urunler/inverter-markalari/solinved/solinved-7-5-kw-tri-faz-solar-pompa-surucu-380v',
  'solinved-75-kw-tri-faz-solar-pompa-surucu-380v':'/urunler/inverter-markalari/solinved/solinved-75-kw-tri-faz-solar-pompa-surucu-380v',
  'solinved-80a-mppt-sarj-kontrol-cihazi-12v-48v':'/urunler/inverter-markalari/solinved/solinved-80a-mppt-sarj-kontrol-cihazi-12v-48v',
  'solinved-90-kw-tri-faz-solar-pompa-surucu-380v':'/urunler/inverter-markalari/solinved/solinved-90-kw-tri-faz-solar-pompa-surucu-380v',
  'solinved-angora-22-kw-ac-sarj-cihazi-ocpp':'/urunler/inverter-markalari/solinved/solinved-angora-22-kw-ac-sarj-cihazi-ocpp',
  'solinved-aspendos-all-in-one-batarya-modulu-5-kwh':'/urunler/inverter-markalari/solinved/solinved-aspendos-all-in-one-batarya-modulu-5-kwh',
  'solinved-aspendos-all-in-one-inverter-modulu-6-kw-48v':'/urunler/inverter-markalari/solinved/solinved-aspendos-all-in-one-inverter-modulu-6-kw-48v',
  'solinved-cm04-solar-kamera-4g':'/urunler/inverter-markalari/solinved/solinved-cm04-solar-kamera-4g',
  'solinved-cm04-solar-kamera-wifi':'/urunler/inverter-markalari/solinved/solinved-cm04-solar-kamera-wifi',
  'solinved-cm09-solar-kamera-4g':'/urunler/inverter-markalari/solinved/solinved-cm09-solar-kamera-4g',
  'solinved-cm22-solar-kamera-4g':'/urunler/inverter-markalari/solinved/solinved-cm22-solar-kamera-4g',
  'solinved-cm22-solar-kamera-wifi':'/urunler/inverter-markalari/solinved/solinved-cm22-solar-kamera-wifi',
  'solinved-cm26-solar-kamera-4g':'/urunler/inverter-markalari/solinved/solinved-cm26-solar-kamera-4g',
  'solinved-cm27-solar-kamera-4g':'/urunler/inverter-markalari/solinved/solinved-cm27-solar-kamera-4g',
  'solinved-dc-100a-1000v-devre-kesici':'/urunler/inverter-markalari/solinved/solinved-dc-100a-1000v-devre-kesici',
  'solinved-dc-125a-1000v-devre-kesici':'/urunler/inverter-markalari/solinved/solinved-dc-125a-1000v-devre-kesici',
  'solinved-dc-200a-1000v-devre-kesici':'/urunler/inverter-markalari/solinved/solinved-dc-200a-1000v-devre-kesici',
  'solinved-dc-250a-1000v-devre-kesici':'/urunler/inverter-markalari/solinved/solinved-dc-250a-1000v-devre-kesici',
  'solinved-dc-315a-1000v-devre-kesici':'/urunler/inverter-markalari/solinved/solinved-dc-315a-1000v-devre-kesici',
  'solinved-dc-350a-1000v-devre-kesici':'/urunler/inverter-markalari/solinved/solinved-dc-350a-1000v-devre-kesici',
  'solinved-dc-80a-1000v-devre-kesici':'/urunler/inverter-markalari/solinved/solinved-dc-80a-1000v-devre-kesici',
  'solinved-dc-sigorta-yuvasi-10x38mm':'/urunler/inverter-markalari/solinved/solinved-dc-sigorta-yuvasi-10x38mm',
  'solinved-gordion-1-2-kw-mppt-off-grid-inverter-12v':'/urunler/inverter-markalari/solinved/solinved-gordion-1-2-kw-mppt-off-grid-inverter-12v',
  'solinved-gordion-3-6-kw-mppt-off-grid-inverter-24v':'/urunler/inverter-markalari/solinved/solinved-gordion-3-6-kw-mppt-off-grid-inverter-24v',
  'solinved-gordion-5-kw-mppt-off-grid-inverter-24v':'/urunler/inverter-markalari/solinved/solinved-gordion-5-kw-mppt-off-grid-inverter-24v',
  'solinved-gordion-5-kw-mppt-off-grid-inverter-48v':'/urunler/inverter-markalari/solinved/solinved-gordion-5-kw-mppt-off-grid-inverter-48v',
  'solinved-gordion-6-5-kw-mppt-off-grid-inverter-48v':'/urunler/inverter-markalari/solinved/solinved-gordion-6-5-kw-mppt-off-grid-inverter-48v',
  'solinved-gordion-6-kw-mppt-off-grid-inverter-48v':'/urunler/inverter-markalari/solinved/solinved-gordion-6-kw-mppt-off-grid-inverter-48v',
  'solinved-kapadokya-51-2v-100ah-lityum-rack-batarya':'/urunler/inverter-markalari/solinved/solinved-kapadokya-51-2v-100ah-lityum-rack-batarya',
  'solinved-l8-solar-router-4g':'/urunler/inverter-markalari/solinved/solinved-l8-solar-router-4g',
  'solinved-lityum-batarya-guc-kablo-seti-2x1-5m':'/urunler/inverter-markalari/solinved/solinved-lityum-batarya-guc-kablo-seti-2x1-5m',
  'solinved-max-8-2-kw-mppt-off-grid-inverter-48v':'/urunler/inverter-markalari/solinved/solinved-max-8-2-kw-mppt-off-grid-inverter-48v',
  'solinved-mc4-sikma-pensesi-crimping-tool':'/urunler/inverter-markalari/solinved/solinved-mc4-sikma-pensesi-crimping-tool',
  'solinved-mc4-solar-konnektor-seti-1000v':'/urunler/inverter-markalari/solinved/solinved-mc4-solar-konnektor-seti-1000v',
  'solinved-mc4-solar-konnektor-seti-1500v':'/urunler/inverter-markalari/solinved/solinved-mc4-solar-konnektor-seti-1500v',
  'solinved-nml-1-6-kw-mppt-off-grid-inverter-12v':'/urunler/inverter-markalari/solinved/solinved-nml-1-6-kw-mppt-off-grid-inverter-12v',
  'solinved-ps-plus-1-kw-pwm-smart-inverter-12v':'/urunler/inverter-markalari/solinved/solinved-ps-plus-1-kw-pwm-smart-inverter-12v',
  'solinved-radius-22-kw-ac-sarj-cihazi':'/urunler/inverter-markalari/solinved/solinved-radius-22-kw-ac-sarj-cihazi',
  'solinved-xh-control-box':'/urunler/inverter-markalari/solinved/solinved-xh-control-box',
  'solis-1-5-kw-mono-faz-mini-on-grid-inverter':'/urunler/inverter-markalari/solis/solis-1-5-kw-mono-faz-mini-on-grid-inverter',
  'solis-10-kw-tri-faz-hibrit-inverter-hv':'/urunler/inverter-markalari/solis/solis-10-kw-tri-faz-hibrit-inverter-hv',
  'solis-10-kw-tri-faz-hibrit-inverter-lv':'/urunler/inverter-markalari/solis/solis-10-kw-tri-faz-hibrit-inverter-lv',
  'solis-10-kw-tri-faz-on-grid-inverter':'/urunler/inverter-markalari/solis/solis-10-kw-tri-faz-on-grid-inverter',
  'solis-110k-5g-pro':'/urunler/inverter-markalari/solis/solis-110k-5g-pro',
  'solis-12-kw-mono-faz-hibrit-inverter-lv':'/urunler/inverter-markalari/solis/solis-12-kw-mono-faz-hibrit-inverter-lv',
  'solis-12-kw-tri-faz-hibrit-inverter-hv':'/urunler/inverter-markalari/solis/solis-12-kw-tri-faz-hibrit-inverter-hv',
  'solis-12-kw-tri-faz-hibrit-inverter-lv':'/urunler/inverter-markalari/solis/solis-12-kw-tri-faz-hibrit-inverter-lv',
  'solis-15-kw-tri-faz-hibrit-inverter-hv':'/urunler/inverter-markalari/solis/solis-15-kw-tri-faz-hibrit-inverter-hv',
  'solis-15-kw-tri-faz-hibrit-inverter-lv':'/urunler/inverter-markalari/solis/solis-15-kw-tri-faz-hibrit-inverter-lv',
  'solis-15-kw-tri-faz-on-grid-inverter':'/urunler/inverter-markalari/solis/solis-15-kw-tri-faz-on-grid-inverter',
  'solis-16-kw-mono-faz-hibrit-inverter-lv':'/urunler/inverter-markalari/solis/solis-16-kw-mono-faz-hibrit-inverter-lv',
  'solis-20-kw-tri-faz-hibrit-inverter-hv':'/urunler/inverter-markalari/solis/solis-20-kw-tri-faz-hibrit-inverter-hv',
  'solis-20-kw-tri-faz-on-grid-inverter':'/urunler/inverter-markalari/solis/solis-20-kw-tri-faz-on-grid-inverter',
  'solis-25-kw-tri-faz-on-grid-inverter':'/urunler/inverter-markalari/solis/solis-25-kw-tri-faz-on-grid-inverter',
  'solis-3-kw-mono-faz-mini-on-grid-inverter':'/urunler/inverter-markalari/solis/solis-3-kw-mono-faz-mini-on-grid-inverter',
  'solis-3-kw-mono-faz-on-grid-inverter-2-mppt':'/urunler/inverter-markalari/solis/solis-3-kw-mono-faz-on-grid-inverter-2-mppt',
  'solis-3-kw-tri-faz-on-grid-inverter':'/urunler/inverter-markalari/solis/solis-3-kw-tri-faz-on-grid-inverter',
  'solis-30-kw-tri-faz-hibrit-inverter-hv':'/urunler/inverter-markalari/solis/solis-30-kw-tri-faz-hibrit-inverter-hv',
  'solis-30-kw-tri-faz-on-grid-inverter':'/urunler/inverter-markalari/solis/solis-30-kw-tri-faz-on-grid-inverter',
  'solis-4-kw-mono-faz-on-grid-inverter-2-mppt':'/urunler/inverter-markalari/solis/solis-4-kw-mono-faz-on-grid-inverter-2-mppt',
  'solis-40-kw-tri-faz-hibrit-inverter-hv':'/urunler/inverter-markalari/solis/solis-40-kw-tri-faz-hibrit-inverter-hv',
  'solis-40-kw-tri-faz-on-grid-inverter':'/urunler/inverter-markalari/solis/solis-40-kw-tri-faz-on-grid-inverter',
  'solis-5-kw-mono-faz-hibrit-inverter-lv':'/urunler/inverter-markalari/solis/solis-5-kw-mono-faz-hibrit-inverter-lv',
  'solis-5-kw-mono-faz-on-grid-inverter-2-mppt':'/urunler/inverter-markalari/solis/solis-5-kw-mono-faz-on-grid-inverter-2-mppt',
  'solis-5-kw-tri-faz-hibrit-inverter-hv':'/urunler/inverter-markalari/solis/solis-5-kw-tri-faz-hibrit-inverter-hv',
  'solis-5-kw-tri-faz-on-grid-inverter':'/urunler/inverter-markalari/solis/solis-5-kw-tri-faz-on-grid-inverter',
  'solis-50-kw-tri-faz-hibrit-inverter-hv':'/urunler/inverter-markalari/solis/solis-50-kw-tri-faz-hibrit-inverter-hv',
  'solis-50-kw-tri-faz-on-grid-inverter':'/urunler/inverter-markalari/solis/solis-50-kw-tri-faz-on-grid-inverter',
  'solis-6-kw-mono-faz-hibrit-inverter-lv':'/urunler/inverter-markalari/solis/solis-6-kw-mono-faz-hibrit-inverter-lv',
  'solis-6-kw-mono-faz-on-grid-inverter-2-mppt':'/urunler/inverter-markalari/solis/solis-6-kw-mono-faz-on-grid-inverter-2-mppt',
  'solis-60-kw-tri-faz-on-grid-inverter':'/urunler/inverter-markalari/solis/solis-60-kw-tri-faz-on-grid-inverter',
  'solis-8-kw-mono-faz-hibrit-inverter-lv':'/urunler/inverter-markalari/solis/solis-8-kw-mono-faz-hibrit-inverter-lv',
  'solis-8-kw-tri-faz-hibrit-inverter-hv':'/urunler/inverter-markalari/solis/solis-8-kw-tri-faz-hibrit-inverter-hv',
  'solis-8-kw-tri-faz-hibrit-inverter-lv':'/urunler/inverter-markalari/solis/solis-8-kw-tri-faz-hibrit-inverter-lv',
  'solis-8-kw-tri-faz-on-grid-inverter':'/urunler/inverter-markalari/solis/solis-8-kw-tri-faz-on-grid-inverter',
  'solis-dlb-wifi-box':'/urunler/inverter-markalari/solis/solis-dlb-wifi-box',
  'solis-export-power-manager-10-inverter':'/urunler/inverter-markalari/solis/solis-export-power-manager-10-inverter',
  'solis-export-power-manager-pro-60-inverter':'/urunler/inverter-markalari/solis/solis-export-power-manager-pro-60-inverter',
  'solis-monofaze-smart-meter-ct-dahil':'/urunler/inverter-markalari/solis/solis-monofaze-smart-meter-ct-dahil',
  'solis-s2-wifi-stick-10-inverter-baglanti':'/urunler/inverter-markalari/solis/solis-s2-wifi-stick-10-inverter-baglanti',
  'solis-s3-wifi-stick':'/urunler/inverter-markalari/solis/solis-s3-wifi-stick',
  'solis-trifaze-smart-meter-ct-dahil':'/urunler/inverter-markalari/solis/solis-trifaze-smart-meter-ct-dahil',
  'tiger-pro-72hctv-525545-watt':'/urunler/solar-panel-markalari/tiger-pro-72hctv-525545-watt',
  'togg-T10X-arac-sarj-kablosu':'/urunler/elektrikli-arac-sarj-cihazi/togg-T10X-arac-sarj-kablosu',
  'vatan--vkpv-xlpo-izoleli-bakir-iletkenli-kablolarsiyah1000metre':'/urunler/solar-kablo/vatan--vkpv-xlpo-izoleli-bakir-iletkenli-kablolarsiyah1000metre',
  'victron-color-control-gx':'/urunler/inverter-markalari/victron/victron-color-control-gx',
  'victron-interface-mk3usb-vebus-to-usb':'/urunler/inverter-markalari/victron/victron-interface-mk3usb-vebus-to-usb',
  'victron-rj45-utp-network-kablosu':'/urunler/inverter-markalari/victron/victron-rj45-utp-network-kablosu',
};

// ─── Bypass Paths ───
const BYPASS_PREFIXES = [
  '/sepet', '/odeme', '/uyelik', '/hesabim',
  '/admin', '/epanel', '/Account', '/Login',
];

// ─── Rate Limit State ───
const rateLimitBurst = new Map();
const rateLimitWindow = new Map();
const BURST_LIMIT = 10;
const BURST_WINDOW_MS = 10000;
const WINDOW_LIMIT = 60;
const WINDOW_DURATION_MS = 300000;

function isRateLimited(ip) {
  const now = Date.now();

  // Burst check (10 req / 10s)
  const burst = rateLimitBurst.get(ip);
  if (burst && now - burst.start < BURST_WINDOW_MS) {
    burst.count++;
    if (burst.count > BURST_LIMIT) { return true; }
  } else {
    rateLimitBurst.set(ip, { start: now, count: 1 });
  }

  // Window check (60 req / 5min)
  const win = rateLimitWindow.get(ip);
  if (win && now - win.start < WINDOW_DURATION_MS) {
    win.count++;
    if (win.count > WINDOW_LIMIT) { return true; }
  } else {
    rateLimitWindow.set(ip, { start: now, count: 1 });
  }

  return false;
}

// ─── Canonical Injection (HTMLRewriter) ───
class CanonicalHandler {
  constructor(canonicalUrl) {
    this.canonicalUrl = canonicalUrl;
    this.found = false;
  }

  element(el) {
    const rel = el.getAttribute('rel');
    if (rel && rel.toLowerCase() === 'canonical') {
      el.setAttribute('href', this.canonicalUrl);
      this.found = true;
    }
  }
}

class HeadHandler {
  constructor(canonicalUrl, canonicalHandler) {
    this.canonicalUrl = canonicalUrl;
    this.canonicalHandler = canonicalHandler;
    this.injected = false;
  }

  element(el) {
    // Use onEndTag so the check runs AFTER all <link> children have been processed
    // (streaming: <head> opening tag fires before child elements)
    el.onEndTag((endTag) => {
      if (!this.canonicalHandler.found && !this.injected) {
        endTag.before(`<link rel="canonical" href="${this.canonicalUrl}" />`, { html: true });
        this.injected = true;
      }
    });
  }
}

// ─── v3.6 PageSpeed: Preconnect + font-display injection ───
class HeadPreconnectHandler {
  constructor() {
    this.injected = false;
  }

  element(el) {
    if (this.injected) { return; }
    this.injected = true;
    // Preconnect to external CDNs used by the site
    const hints = [
      '<link rel="preconnect" href="https://cdn.jsdelivr.net" crossorigin>',
      '<link rel="preconnect" href="https://cdnjs.cloudflare.com" crossorigin>',
      '<link rel="preconnect" href="https://unpkg.com" crossorigin>',
      '<link rel="preconnect" href="https://www.googletagmanager.com" crossorigin>',
    ];
    // Inject right after <head> opens (prepend = first child)
    el.prepend(hints.join('\n'), { html: true });
  }
}

// ─── v3.6 PageSpeed: CSS async loading ───
// Convert non-critical CSS from render-blocking to async
// Critical CSS (bootstrap, meister, medias, new-mobile) stays blocking for FOUC prevention
const NON_CRITICAL_CSS = new Set([
  '/assets/stylesheets/creditcard/creditcard.css',
  '/assets/stylesheets/animsition/animsition.css',
  '/assets/stylesheets/mmenu/demo.css',
  '/assets/stylesheets/mmenu/mmenu.css',
  'swiper-bundle.min.css',        // partial match for unpkg URL
  'swiper-custom.css',
  'jquery.fancybox.min.css',      // partial match for jsdelivr URL
  '/assets/javascripts/izitoast/css/iziToast.min.css',
]);

class CssAsyncHandler {
  element(el) {
    const rel = el.getAttribute('rel');
    if (!rel || rel.toLowerCase() !== 'stylesheet') { return; }

    const href = el.getAttribute('href');
    if (!href) { return; }

    // Check if this CSS is non-critical
    let isNonCritical = false;
    for (const pattern of NON_CRITICAL_CSS) {
      if (href.includes(pattern)) {
        isNonCritical = true;
        break;
      }
    }
    if (!isNonCritical) { return; }

    // Convert to async: media="print" onload="this.media='all'"
    el.setAttribute('media', 'print');
    el.setAttribute('onload', "this.media='all'");
  }
}

// ─── v3.6 PageSpeed: Font Awesome font-display:swap ───
class FontAwesomeCssHandler {
  element(el) {
    const rel = el.getAttribute('rel');
    if (!rel || rel.toLowerCase() !== 'stylesheet') { return; }

    const href = el.getAttribute('href');
    if (!href) { return; }

    // Font Awesome + Line Awesome — make async and inject font-display:swap override
    if (href.includes('font-awesome') || href.includes('line-awesome')) {
      el.setAttribute('media', 'print');
      el.setAttribute('onload', "this.media='all'");
      // font-display:swap will be injected as inline <style> in HeadFontDisplayHandler
    }
  }
}

class HeadFontDisplayHandler {
  constructor() {
    this.injected = false;
  }

  element(el) {
    if (this.injected) { return; }
    this.injected = true;
    // Override font-display for Font Awesome and Line Awesome
    el.append(
      '<style>' +
      '@font-face{font-family:"Font Awesome 6 Free";font-display:swap}' +
      '@font-face{font-family:"Font Awesome 6 Brands";font-display:swap}' +
      '@font-face{font-family:"Line Awesome Free";font-display:swap}' +
      '@font-face{font-family:"Line Awesome Brands";font-display:swap}' +
      '</style>',
      { html: true }
    );
  }
}

// ─── v3.6 PageSpeed: JS defer for blocking head scripts ───
// These scripts are in <head> without async/defer — they block rendering
const DEFER_SCRIPTS = new Set([
  '/assets/javascripts/printthis/printthis.js',
  '/assets/javascripts/printthis/printthis.custom.js',
  '/assets/javascripts/placeholdem/placeholdem.min.js',
  '/assets/javascripts/functions.js',
]);

// Scripts that should be deferred in body too
const DEFER_BODY_SCRIPTS = new Set([
  'swiper-bundle.min.js',     // partial match for unpkg URL
  '/assets/javascripts/tmpl/tmpl.js',
  '/assets/javascripts/format-currency/format-currency.js',
]);

class ScriptDeferHandler {
  element(el) {
    const src = el.getAttribute('src');
    if (!src) { return; }

    // Already has async or defer — skip
    if (el.getAttribute('async') !== null || el.getAttribute('defer') !== null) { return; }

    // Check head blocking scripts
    let shouldDefer = false;
    for (const pattern of DEFER_SCRIPTS) {
      if (src.includes(pattern)) {
        shouldDefer = true;
        break;
      }
    }
    // Check body blocking scripts
    if (!shouldDefer) {
      for (const pattern of DEFER_BODY_SCRIPTS) {
        if (src.includes(pattern)) {
          shouldDefer = true;
          break;
        }
      }
    }

    if (shouldDefer) {
      el.setAttribute('defer', '');
    }
  }
}

// ─── v3.6 PageSpeed: reCAPTCHA lazy load ───
// Remove reCAPTCHA from pages that don't need it (only /iletisim, /uyelik, /hesabim need it)
class RecaptchaHandler {
  constructor(pathname) {
    this.pathname = pathname;
    // Pages that actually have forms needing reCAPTCHA
    this.formPages = ['/iletisim', '/Icerik/Goster/iletisim', '/uyelik', '/hesabim'];
  }

  element(el) {
    const src = el.getAttribute('src');
    if (!src || !src.includes('recaptcha')) { return; }

    // If NOT a form page, remove reCAPTCHA entirely (saves 243KB)
    const needsRecaptcha = this.formPages.some(p => this.pathname.startsWith(p));
    if (!needsRecaptcha) {
      el.remove();
    }
  }
}

// ─── v3.6 PageSpeed: Image lazy loading ───
// Add loading="lazy" to images below the fold
class ImgLazyHandler {
  constructor() {
    this.count = 0;
  }

  element(el) {
    this.count++;

    // Skip first image (likely logo / LCP candidate)
    if (this.count <= 1) { return; }

    // Already has loading attribute — skip
    if (el.getAttribute('loading')) { return; }

    el.setAttribute('loading', 'lazy');
  }
}

// ─── Main Handler ───
async function handleRequest(request) {
  const url = new URL(request.url);
  const { hostname, pathname } = url;

  // 1. non-www → www redirect
  if (hostname === 'turkiyesolarmarket.com.tr') {
    const wwwUrl = `https://www.turkiyesolarmarket.com.tr${pathname}${url.search}`;
    return new Response(null, {
      status: 301,
      headers: {
        'Location': wwwUrl,
        'x-tsm-worker': 'www-redirect',
      },
    });
  }

  // 1b. Bypass paths — pass through to origin (v4.0: moved BEFORE slash redirect to prevent loop)
  for (const prefix of BYPASS_PREFIXES) {
    if (pathname.toLowerCase().startsWith(prefix)) {
      return fetch(request);
    }
  }

  // 1c. /kategori/ → doğru formata yönlendir (v3.8 + v4.2)
  // Doğru format: /kategori/0/{sef-url}/ — DLL bu formatta çalışır
  if (pathname.startsWith('/kategori/')) {
    // v4.2: /kategori/{sef}/ (eksik /0/) → /kategori/0/{sef}/ 301 redirect
    // Regex: /kategori/ ardından SAYI İLE BAŞLAMAYAN segment(ler)
    const kategoriMatch = pathname.match(/^\/kategori\/(?!0\/|0$)(.+)/);
    if (kategoriMatch) {
      const sefPart = kategoriMatch[1].replace(/\/+$/, '');
      const redirectUrl = `https://www.turkiyesolarmarket.com.tr/kategori/0/${sefPart}/${url.search}`;
      return new Response(null, {
        status: 301,
        headers: {
          'Location': redirectUrl,
          'x-tsm-worker': 'kategori-fix-301',
        },
      });
    }
    // Trailing slash zorunlu (v3.8)
    if (!pathname.endsWith('/')) {
      const redirectUrl = `https://www.turkiyesolarmarket.com.tr${pathname}/${url.search}`;
      return new Response(null, {
        status: 301,
        headers: {
          'Location': redirectUrl,
          'x-tsm-worker': 'kategori-slash-add',
        },
      });
    }
  }

  // 1d. Trailing slash → 301 redirect (v3.7 — canonical hygiene)
  // Skip root "/", preserve query string, /kategori/ muaf (yukarıda handle edildi)
  if (pathname.length > 1 && pathname.endsWith('/') && !pathname.startsWith('/kategori/')) {
    const cleanPath = pathname.replace(/\/+$/, '');
    const redirectUrl = `https://www.turkiyesolarmarket.com.tr${cleanPath}${url.search}`;
    return new Response(null, {
      status: 301,
      headers: {
        'Location': redirectUrl,
        'x-tsm-worker': 'slash-redirect',
      },
    });
  }

  // 3. /arama — rate limit + no cache
  if (pathname.startsWith('/arama')) {
    const ip = request.headers.get('cf-connecting-ip') || 'unknown';
    if (isRateLimited(ip)) {
      return new Response('Rate limited', {
        status: 429,
        headers: {
          'Retry-After': '60',
          'x-tsm-worker': 'rate-limited',
        },
      });
    }
    return fetch(request);
  }

  // 4. /merchant-feed.xml + /sitemap_new.xml → GitHub raw proxy (1h cache)
  if (pathname === '/merchant-feed.xml' || pathname === '/sitemap_new.xml') {
    const fileName = pathname.substring(1); // strip leading /
    const ghUrl = `https://raw.githubusercontent.com/barisugus/solarmarket-google-merchant-feed/main/${fileName}`;
    const ghResponse = await fetch(ghUrl, {
      cf: { cacheEverything: true, cacheTtl: 3600 },
    });

    const headers = new Headers(ghResponse.headers);
    headers.set('content-type', 'application/xml; charset=utf-8');
    headers.set('x-tsm-worker', fileName === 'merchant-feed.xml' ? 'merchant-feed' : 'sitemap');
    headers.delete('set-cookie');

    return new Response(ghResponse.body, {
      status: ghResponse.status,
      headers,
    });
  }

  // 5. Product redirect/gone map (v3.4 + v3.9)
  if (pathname.startsWith('/urunler/')) {
    const slug = pathname.replace('/urunler/', '').replace(/\/$/, '');
    const productSlug = slug.split('/').pop(); // v3.9: last segment for multi-category URLs

    // 5a. GONE — kalıcı olarak kaldırılmış ürünler (full slug OR product slug match)
    if (GONE_410.has(slug) || GONE_PRODUCT_410.has(productSlug)) {
      return new Response('This product has been permanently removed.', {
        status: 410,
        headers: {
          'content-type': 'text/html; charset=utf-8',
          'x-tsm-worker': 'gone-product',
        },
      });
    }

    // 5b. 301 Redirect — eski model → yeni model (full slug OR product slug match)
    const redirectTarget = REDIRECT_301[slug] || REDIRECT_301[productSlug];
    if (redirectTarget) {
      return new Response(null, {
        status: 301,
        headers: {
          'Location': `https://www.turkiyesolarmarket.com.tr${redirectTarget}`,
          'x-tsm-worker': 'redirect-product',
        },
      });
    }
  }

  // 5c. /Icerik/Goster/{numericID} → 301 SEF URL (v4.2)
  // DLL numeric ID ile 500 veriyor, SEF URL ile çalışıyor
  if (pathname.startsWith('/Icerik/Goster/')) {
    const segment = pathname.replace('/Icerik/Goster/', '').replace(/\/+$/, '');
    const sefUrl = ICERIK_SEF_MAP[segment];
    if (sefUrl) {
      return new Response(null, {
        status: 301,
        headers: {
          'Location': `https://www.turkiyesolarmarket.com.tr/Icerik/Goster/${sefUrl}`,
          'x-tsm-worker': 'icerik-sef-redirect',
        },
      });
    }
  }

  // 5d. /markaurunleri/{brand-sef}/ → 410 GONE (v4.2)
  // DLL Int32 markaID bekliyor, SEF URL string alınca 500 veriyor
  // Doğru format: /markaurunleri/{numericID}/ — SEF varyantları artık kullanılmıyor
  if (pathname.startsWith('/markaurunleri/')) {
    const segment = pathname.replace('/markaurunleri/', '').replace(/\/+$/, '');
    if (segment && !/^\d+$/.test(segment)) {
      return new Response('This page has been permanently removed.', {
        status: 410,
        headers: {
          'content-type': 'text/html; charset=utf-8',
          'x-tsm-worker': 'gone-markaurunleri',
        },
      });
    }
  }


  // 6. Fetch from origin with edge cache
  const response = await fetch(request, {
    cf: { cacheEverything: true, cacheTtl: 300 },
  });

  // 7. v4.2: Origin 500 → 404 for /urunler/ (non-existent product slugs)
  // DLL NullRef yerine temiz 404 döndür — Google index'ten düşürsün
  if (response.status === 500 && pathname.startsWith('/urunler/')) {
    return new Response('<html><head><title>404 - Ürün Bulunamadı</title></head><body><h1>404</h1><p>Bu ürün bulunamadı veya kaldırılmış olabilir.</p><p><a href="/">Ana Sayfa</a></p></body></html>', {
      status: 404,
      headers: {
        'content-type': 'text/html; charset=utf-8',
        'cache-control': 'public, max-age=3600',
        'x-tsm-worker': 'origin-500-to-404',
      },
    });
  }

  // 8. Build response with custom headers
  const newHeaders = new Headers(response.headers);
  newHeaders.set('x-tsm-worker', 'active');
  newHeaders.set('cache-control', 'public, max-age=300');
  newHeaders.delete('set-cookie');

  // 9. HTML transformation (canonical + v3.6 PageSpeed optimizations)
  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('text/html') && response.status === 200) {
    // v4.1: Resolve canonical URL from product map for /urunler/ pages
    let canonicalUrl;
    if (pathname.startsWith('/urunler/')) {
      const productSlug = pathname.replace('/urunler/', '').replace(/\/$/, '').split('/').pop();
      const mappedPath = CANONICAL_MAP[productSlug];
      canonicalUrl = mappedPath
        ? `https://www.turkiyesolarmarket.com.tr${mappedPath}`
        : `https://www.turkiyesolarmarket.com.tr${pathname}`;
    } else {
      canonicalUrl = `https://www.turkiyesolarmarket.com.tr${pathname}`;
    }
    const canonicalHandler = new CanonicalHandler(canonicalUrl);
    const headHandler = new HeadHandler(canonicalUrl, canonicalHandler);

    // v3.6 PageSpeed handlers
    const preconnectHandler = new HeadPreconnectHandler();
    const cssAsyncHandler = new CssAsyncHandler();
    const fontAwesomeCssHandler = new FontAwesomeCssHandler();
    const fontDisplayHandler = new HeadFontDisplayHandler();
    const scriptDeferHandler = new ScriptDeferHandler();
    const recaptchaHandler = new RecaptchaHandler(pathname);
    const imgLazyHandler = new ImgLazyHandler();

    const transformed = new HTMLRewriter()
      // Existing: canonical
      .on('link[rel="canonical"]', canonicalHandler)
      .on('head', headHandler)
      // v3.6: preconnect hints (injected at start of <head>)
      .on('head', preconnectHandler)
      // v3.6: font-display:swap (injected at end of <head>)
      .on('head', fontDisplayHandler)
      // v3.6: CSS async loading for non-critical stylesheets
      .on('link[rel="stylesheet"]', cssAsyncHandler)
      // v3.6: Font icon CSS async
      .on('link[rel="stylesheet"]', fontAwesomeCssHandler)
      // v3.6: JS defer for blocking scripts
      .on('script[src]', scriptDeferHandler)
      // v3.6: reCAPTCHA removal on non-form pages
      .on('script[src]', recaptchaHandler)
      // v3.6: Image lazy loading
      .on('img', imgLazyHandler)
      .transform(new Response(response.body, {
        status: response.status,
        headers: newHeaders,
      }));

    return transformed;
  }

  return new Response(response.body, {
    status: response.status,
    headers: newHeaders,
  });
}

addEventListener('fetch', (event) => {
  event.respondWith(handleRequest(event.request));
});
