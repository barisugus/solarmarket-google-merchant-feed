/**
 * TSM Edge Cache Worker v3.5
 * turkiyesolarmarket.com.tr
 *
 * Changelog:
 *   v3.0  — Edge cache, non-www redirect, canonical injection, 500→410, Set-Cookie strip
 *   v3.1  — /arama bypass
 *   v3.2  — Dual-layer rate limit (/arama), /Icerik/Goster/ 500→410
 *   v3.3  — /merchant-feed.xml → GitHub raw proxy (1h cache)
 *   v3.4  — D-kategori 301/410 redirect map (14 slug + 1 gone)
 *   v3.5  — KRİTİK: 500→503 (Retry-After) — Google index kaybını durdur
 *           D-kategori 410 ve 301 redirect'ler AYNEN korunuyor
 */

// ─── D-Kategori Redirect Map (v3.4) ───
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
};

const GONE_410 = new Set([
  'jinko-tiger-pro-72hc-550w-monokristal-gunes-paneli',
]);

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
    el.onEndTag((endTag) => {
      if (!this.canonicalHandler.found && !this.injected) {
        endTag.before(`<link rel="canonical" href="${this.canonicalUrl}" />`, { html: true });
        this.injected = true;
      }
    });
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

  // 2. Bypass paths — pass through to origin
  for (const prefix of BYPASS_PREFIXES) {
    if (pathname.startsWith(prefix)) {
      return fetch(request);
    }
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

  // 4. /merchant-feed.xml → GitHub raw proxy (1h cache)
  if (pathname === '/merchant-feed.xml') {
    const ghUrl = 'https://raw.githubusercontent.com/barisugus/solarmarket-google-merchant-feed/main/merchant-feed.xml';
    const ghResponse = await fetch(ghUrl, {
      cf: { cacheEverything: true, cacheTtl: 3600 },
    });

    const headers = new Headers(ghResponse.headers);
    headers.set('content-type', 'application/xml; charset=utf-8');
    headers.set('x-tsm-worker', 'merchant-feed');
    headers.delete('set-cookie');

    return new Response(ghResponse.body, {
      status: ghResponse.status,
      headers,
    });
  }

  // 5. D-Kategori redirect map (v3.4)
  if (pathname.startsWith('/urunler/')) {
    const slug = pathname.replace('/urunler/', '').replace(/\/$/, '');

    // 5a. GONE — kalıcı olarak kaldırılmış ürünler
    if (GONE_410.has(slug)) {
      return new Response('This product has been permanently removed.', {
        status: 410,
        headers: {
          'content-type': 'text/html; charset=utf-8',
          'x-tsm-worker': 'gone-product',
        },
      });
    }

    // 5b. 301 Redirect — eski model → yeni model
    if (REDIRECT_301[slug]) {
      return new Response(null, {
        status: 301,
        headers: {
          'Location': `https://www.turkiyesolarmarket.com.tr${REDIRECT_301[slug]}`,
          'x-tsm-worker': 'redirect-product',
        },
      });
    }
  }

  // 6. Fetch from origin with edge cache
  const response = await fetch(request, {
    cf: { cacheEverything: true, cacheTtl: 300 },
  });

  // 7. ─── v3.5 KRİTİK DEĞİŞİKLİK ───
  //    Origin 500 → 503 Service Unavailable + Retry-After
  //    Eski davranış (v3.0-3.4): 500 → 410 Gone (YANLIŞ — Google de-index eder)
  //    Yeni davranış (v3.5):     500 → 503 (Google geçici hata sayar, index korur)
  //    Kapsam: /urunler/* ve /Icerik/Goster/* path'leri
  if (response.status === 500) {
    if (pathname.startsWith('/urunler/') || pathname.startsWith('/Icerik/Goster/')) {
      return new Response(
        '<!DOCTYPE html><html><head><title>Bakım - Türkiye Solar Market</title></head>' +
        '<body style="font-family:sans-serif;text-align:center;padding:60px 20px;">' +
        '<h1>Geçici Bakım</h1>' +
        '<p>Bu sayfa şu anda bakımdadır. Lütfen kısa bir süre sonra tekrar deneyin.</p>' +
        '<p><a href="/">Ana Sayfaya Dön</a></p>' +
        '</body></html>',
        {
          status: 503,
          headers: {
            'Content-Type': 'text/html; charset=utf-8',
            'Retry-After': '3600',
            'Cache-Control': 'no-store',
            'x-tsm-worker': 'maintenance-503',
          },
        }
      );
    }
  }

  // 8. Build response with custom headers
  const newHeaders = new Headers(response.headers);
  newHeaders.set('x-tsm-worker', 'active');
  newHeaders.set('cache-control', 'public, max-age=300');
  newHeaders.delete('set-cookie');

  // 9. Canonical injection (only for HTML responses)
  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('text/html') && response.status === 200) {
    const canonicalUrl = `https://www.turkiyesolarmarket.com.tr${pathname}`;
    const canonicalHandler = new CanonicalHandler(canonicalUrl);
    const headHandler = new HeadHandler(canonicalUrl, canonicalHandler);

    const transformed = new HTMLRewriter()
      .on('link[rel="canonical"]', canonicalHandler)
      .on('head', headHandler)
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
