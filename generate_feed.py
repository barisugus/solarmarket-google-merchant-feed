#!/usr/bin/env python3
"""
Google Merchant Center Product Feed Generator
Scrapes JSON-LD from turkiyesolarmarket.com.tr product pages
Generates RSS 2.0 XML feed with Google Shopping namespace

Usage:
  python generate_feed.py    # Generate merchant-feed.xml
"""

import hashlib
import json
import re
import sys
import time
from html import unescape
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

SITEMAP_URL = "https://www.turkiyesolarmarket.com.tr/sitemap.xml"
USER_AGENT = "Mozilla/5.0 (compatible; TSM-FeedBot/1.0)"
MAX_WORKERS = 10
OUTPUT_FILE = "merchant-feed.xml"


def fetch_url(url, retries=2):
    for attempt in range(retries + 1):
        try:
            req = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(req, timeout=15) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except (HTTPError, URLError, Exception):
            if attempt < retries:
                time.sleep(1)
            else:
                return None


def get_product_urls():
    content = fetch_url(SITEMAP_URL)
    if not content:
        print("ERROR: Could not fetch sitemap")
        sys.exit(1)
    urls = re.findall(
        r"<loc>(https://www\.turkiyesolarmarket\.com\.tr/urunler/[^<]+)</loc>",
        content,
    )
    print(f"Found {len(urls)} product URLs in sitemap")
    return urls


def extract_product_jsonld(html):
    blocks = re.findall(
        r'<script\s+type="application/ld\+json">\s*(.*?)\s*</script>',
        html,
        re.DOTALL,
    )
    for block in blocks:
        try:
            clean = block.replace("\n", " ").replace("\r", " ")
            data = json.loads(clean)
            if data.get("@type") == "Product":
                return data
        except json.JSONDecodeError:
            continue
    return None


def extract_og_tags(html):
    tags = {}
    for match in re.finditer(
        r'<meta\s+property="og:(\w+)"\s+content="([^"]*)"', html
    ):
        tags[match.group(1)] = unescape(match.group(2))
    m = re.search(r'<meta\s+name="description"\s+content="([^"]*)"', html)
    if m:
        tags["meta_description"] = unescape(m.group(1))
    return tags


def scrape_product(url):
    html = fetch_url(url)
    if not html:
        return None

    jsonld = extract_product_jsonld(html)
    og = extract_og_tags(html)

    if not jsonld:
        return None

    offers = jsonld.get("offers", {})
    price = offers.get("price", "")
    currency = offers.get("priceCurrency", "TRY")
    availability = offers.get("availability", "")

    avail_map = {
        "https://schema.org/InStock": "in_stock",
        "https://schema.org/OutOfStock": "out_of_stock",
        "https://schema.org/PreOrder": "preorder",
        "http://schema.org/InStock": "in_stock",
        "http://schema.org/OutOfStock": "out_of_stock",
    }
    g_availability = avail_map.get(availability, "in_stock")

    cond_map = {
        "https://schema.org/NewCondition": "new",
        "http://schema.org/NewCondition": "new",
        "https://schema.org/UsedCondition": "used",
        "https://schema.org/RefurbishedCondition": "refurbished",
    }
    g_condition = cond_map.get(offers.get("itemCondition", ""), "new")

    product = {
        "id": jsonld.get("sku", ""),
        "title": jsonld.get("name", og.get("title", "")),
        "description": (
            jsonld.get("description", "") or og.get("meta_description", "")
        ).strip()[:5000],
        "link": url,
        "image_link": jsonld.get("image", og.get("image", "")),
        "price": f"{price} {currency}" if price else "",
        "availability": g_availability,
        "condition": g_condition,
        "brand": jsonld.get("brand", {}).get("name", ""),
        "mpn": jsonld.get("mpn", ""),
        "gtin": jsonld.get("gtin13", jsonld.get("gtin", "")),
        "category": jsonld.get("category", ""),
    }

    if not product["id"]:
        slug = url.rstrip("/").split("/")[-1]
        product["id"] = slug

    if len(product["id"]) > 50:
        h = hashlib.md5(product["id"].encode()).hexdigest()[:8]
        product["id"] = product["id"][:41] + "-" + h

    product["google_category"] = map_google_category(url)

    if not product["title"] or not product["price"]:
        return None

    return product


def map_google_category(url):
    path = url.lower()
    if "solar-panel" in path or "gunes-paneli" in path:
        return "Hardware > Power & Electrical Supplies > Solar Panels"
    elif (
        "lityum-pil" in path
        or "batarya" in path
        or "reserva" in path
        or "enerji-depolama" in path
    ):
        return "Hardware > Power & Electrical Supplies > Power Storage Batteries"
    elif (
        "sarj-cihazi" in path
        or "wattpilot" in path
        or "sarj-kablosu" in path
        or "ev-sarj" in path
    ):
        return "Vehicles & Parts > Vehicle Parts & Accessories > Motor Vehicle Electronics > Motor Vehicle Charging"
    elif "solar-kablo" in path or "konnektor" in path or "kablo" in path:
        return "Hardware > Power & Electrical Supplies > Electrical Wires & Cable"
    elif "solar-malzeme" in path or "pano" in path or "sigorta" in path:
        return "Hardware > Power & Electrical Supplies > Solar Energy Kits"
    else:
        return "Hardware > Power & Electrical Supplies > Power Inverters"


def escape_xml(text):
    if not text:
        return ""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def generate_feed(products):
    lines = []
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append('<rss version="2.0" xmlns:g="http://base.google.com/ns/1.0">')
    lines.append("  <channel>")
    lines.append("    <title>Türkiye Solar Market - Ürün Kataloğu</title>")
    lines.append("    <link>https://www.turkiyesolarmarket.com.tr</link>")
    lines.append(
        "    <description>Solar enerji ekipmanları - inverter, panel, pil, şarj cihazı</description>"
    )

    for p in products:
        lines.append("    <item>")
        lines.append(f"      <g:id>{escape_xml(p['id'])}</g:id>")
        lines.append(f"      <g:title>{escape_xml(p['title'][:150])}</g:title>")
        lines.append(
            f"      <g:description>{escape_xml(p['description'][:5000])}</g:description>"
        )
        lines.append(f"      <g:link>{escape_xml(p['link'])}</g:link>")
        lines.append(
            f"      <g:image_link>{escape_xml(p['image_link'])}</g:image_link>"
        )
        lines.append(f"      <g:price>{escape_xml(p['price'])}</g:price>")
        lines.append(f"      <g:availability>{p['availability']}</g:availability>")
        lines.append(f"      <g:condition>{p['condition']}</g:condition>")
        if p["brand"]:
            lines.append(f"      <g:brand>{escape_xml(p['brand'])}</g:brand>")
        if p["mpn"]:
            lines.append(f"      <g:mpn>{escape_xml(p['mpn'])}</g:mpn>")
        if p["gtin"]:
            lines.append(f"      <g:gtin>{escape_xml(p['gtin'])}</g:gtin>")
        else:
            lines.append(
                "      <g:identifier_exists>false</g:identifier_exists>"
            )
        lines.append(
            f"      <g:google_product_category>{escape_xml(p.get('google_category', 'Hardware > Power & Electrical Supplies > Power Inverters'))}</g:google_product_category>"
        )
        lines.append("    </item>")

    lines.append("  </channel>")
    lines.append("</rss>")

    return "\n".join(lines)


def main():
    print("=== Google Merchant Center Feed Generator ===")
    print()

    urls = get_product_urls()

    products = []
    errors = 0
    print(f"Scraping {len(urls)} product pages ({MAX_WORKERS} threads)...")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_url = {executor.submit(scrape_product, url): url for url in urls}
        done = 0
        for future in as_completed(future_to_url):
            done += 1
            try:
                product = future.result()
                if product:
                    products.append(product)
                else:
                    errors += 1
            except Exception:
                errors += 1

            if done % 50 == 0 or done == len(urls):
                print(
                    f"  Progress: {done}/{len(urls)} scraped, {len(products)} OK, {errors} errors"
                )

    products.sort(key=lambda p: p["title"])

    print(f"\nGenerating feed with {len(products)} products...")
    xml_content = generate_feed(products)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(xml_content)

    print(f"Feed saved to {OUTPUT_FILE}")
    print(f"File size: {len(xml_content):,} bytes")

    brands = {}
    for p in products:
        b = p["brand"] or "Unknown"
        brands[b] = brands.get(b, 0) + 1

    print(f"\n=== Summary ===")
    print(f"Total products: {len(products)}")
    print(f"Errors/skipped: {errors}")
    print(f"Brands: {', '.join(f'{b}({c})' for b, c in sorted(brands.items(), key=lambda x: -x[1])[:5])}")

    if len(products) < 10:
        print("ERROR: Too few products scraped, feed not saved")
        sys.exit(1)


if __name__ == "__main__":
    main()
