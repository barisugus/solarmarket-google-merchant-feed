#!/usr/bin/env python3
"""
Arçelik 12 Solar Panel — Faz A: Analysis & Planning Only

Reads DB reference patterns at runtime, validates dataset,
generates CSV report. NO INSERT/WRITE operations.

Usage:
  python3 arcelik_panel_insert.py                  # analysis (no pricing)
  python3 arcelik_panel_insert.py --watt-cost 0.23 # analysis + pricing

Output:
  - Console: reference patterns, dataset table, risk report
  - CSV: fronius-stock/arcelik_panel_insert_report.csv (when --watt-cost given)
  - Log: fronius-stock/logs/arcelik_panel_analysis_*.log
"""

import argparse
import csv
import json
import logging
import os
import re
import sys
from collections import Counter
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import pymssql
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).parent
LOG_DIR = SCRIPT_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

ARCELIK_MARKA_ID = 68
EXPECTED_PANEL_COUNT = 12

# Category IDs (VERIFIED against DB — Faz 1 analysis confirmed active)
EXPECTED_CAT_ARCELIK_PANEL = 74    # Arçelik under Solar Panel Markaları
EXPECTED_CAT_SOLAR_CATI = 49       # Solar Paneller Çatı
EXPECTED_CAT_SOLAR_MARKA = 11      # Solar Panel Markaları (parent)

# Confirmed decisions (user-approved, not hardcoded guesses)
CONFIRMED_DOVIZTIPI = "USD"        # majority 9/11 Arçelik, all active inverters
CONFIRMED_KDV = False              # majority 10/11, KDV dahil değil
CONFIRMED_KDVORANI = Decimal("20.00")  # unanimous 11/11
CONFIRMED_STOKKODU_FORMAT = "prefix"   # "Arçelik {SKU}" — 11/11 pattern

# ---------------------------------------------------------------------------
# Product Dataset (12 panels from Arçelik Enerji Çözümleri Kataloğu 2026)
# ---------------------------------------------------------------------------
PANELS = [
    {"sku": "ARCLK-144PV10T-GG-590",  "pmax_w": 590, "pallet_qty": 29, "panel_type": "Cam-Cam Bifacial", "weight_kg": 32.0, "weight_source": "pdf", "efficiency": "22.9%"},
    {"sku": "ARCLK-144PV10T-GG-595",  "pmax_w": 595, "pallet_qty": 29, "panel_type": "Cam-Cam Bifacial", "weight_kg": 32.0, "weight_source": "pdf", "efficiency": "23.0%"},
    {"sku": "ARCLK-144PV10T-GG-600",  "pmax_w": 600, "pallet_qty": 29, "panel_type": "Cam-Cam Bifacial", "weight_kg": 32.0, "weight_source": "pdf", "efficiency": "23.2%"},
    {"sku": "ARCLK-144PV10RT-GG-600", "pmax_w": 600, "pallet_qty": 29, "panel_type": "Cam-Cam Bifacial", "weight_kg": 32.0, "weight_source": "pdf", "efficiency": "23.2%"},
    {"sku": "ARCLK-144PV10RT-GG-605", "pmax_w": 605, "pallet_qty": 29, "panel_type": "Cam-Cam Bifacial", "weight_kg": 32.0, "weight_source": "pdf", "efficiency": "23.4%"},
    {"sku": "ARCLK-144PV10RT-GG-610", "pmax_w": 610, "pallet_qty": 29, "panel_type": "Cam-Cam Bifacial", "weight_kg": 32.0, "weight_source": "pdf", "efficiency": "23.6%"},
    {"sku": "ARCLK-144PV10RT-GG-615", "pmax_w": 615, "pallet_qty": 29, "panel_type": "Cam-Cam Bifacial", "weight_kg": 32.0, "weight_source": "pdf", "efficiency": "23.8%"},
    {"sku": "ARCLK-144PV10RT-600",    "pmax_w": 600, "pallet_qty": 37, "panel_type": "Cam-Cam",          "weight_kg": 32.5, "weight_source": "pdf", "efficiency": "23.2%"},
    {"sku": "ARCLK-132PVRT-GG-610",   "pmax_w": 610, "pallet_qty": 29, "panel_type": "Cam-Cam Bifacial", "weight_kg": 32.5, "weight_source": "pdf", "efficiency": "22.6%"},
    {"sku": "ARCLK-132PVRT-GG-615",   "pmax_w": 615, "pallet_qty": 29, "panel_type": "Cam-Cam Bifacial", "weight_kg": 32.5, "weight_source": "pdf", "efficiency": "22.8%"},
    {"sku": "ARCLK-132PVRT-GG-620",   "pmax_w": 620, "pallet_qty": 29, "panel_type": "Cam-Cam Bifacial", "weight_kg": 32.5, "weight_source": "pdf", "efficiency": "23.0%"},
    {"sku": "ARCLK-132PVRT-GG-625",   "pmax_w": 625, "pallet_qty": 29, "panel_type": "Cam-Cam Bifacial", "weight_kg": 32.5, "weight_source": "pdf", "efficiency": "23.1%"},
]

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
detail_log_path = LOG_DIR / f"arcelik_panel_analysis_{ts}.log"

logger = logging.getLogger("arcelik_panel")
logger.setLevel(logging.DEBUG)

fh = logging.FileHandler(detail_log_path, encoding="utf-8")
fh.setLevel(logging.DEBUG)
fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(fh)

ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
ch.setFormatter(logging.Formatter("%(message)s"))
logger.addHandler(ch)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def make_slug(sku: str) -> str:
    """URL-safe slug from SKU. Deterministic, no Turkish chars."""
    slug = sku.lower()
    slug = re.sub(r"[^a-z0-9-]", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")


def make_olcubirimi(pallet_qty: int) -> str:
    """OLCUBIRIMI based on pallet quantity (user-confirmed decision).
    29 → 'Palet (29 adet solar panel)'
    37 → 'Palet (37 adet solar panel)'
    """
    return f"Palet ({pallet_qty} adet solar panel)"


def calc_pricing(panel: dict, watt_cost: float) -> dict:
    """Calculate pallet pricing."""
    pmax = Decimal(str(panel["pmax_w"]))
    cost = Decimal(str(watt_cost))
    qty = Decimal(str(panel["pallet_qty"]))
    pallet_cost = (pmax * cost * qty).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return {
        "pallet_power_w": int(pmax * qty),
        "watt_cost_usd": float(cost),
        "pallet_cost_usd": float(pallet_cost),
        "fiyat1": pallet_cost,
        "alisfiyati": pallet_cost,
    }


# ---------------------------------------------------------------------------
# DB
# ---------------------------------------------------------------------------
def get_db_connection():
    load_dotenv(SCRIPT_DIR / ".env")
    server = os.getenv("MSSQL_SERVER")
    port = int(os.getenv("MSSQL_PORT", "1433"))
    user = os.getenv("MSSQL_USER")
    password = os.getenv("MSSQL_PASSWORD")
    database = os.getenv("MSSQL_DATABASE")

    if not all([server, user, password, database]):
        logger.error("Missing DB credentials in .env")
        sys.exit(1)

    logger.info("Connecting to MSSQL...")
    conn = pymssql.connect(
        server=server, port=port, user=user,
        password=password, database=database, charset="utf8",
    )
    logger.info("  Connected OK")
    return conn


# ---------------------------------------------------------------------------
# 1. DB Reference Pattern Discovery (runtime, not hardcoded)
# ---------------------------------------------------------------------------
def discover_db_reference(conn) -> dict:
    """Read all reference values from DB at runtime. Returns dict of patterns."""
    cursor = conn.cursor(as_dict=True)
    ref = {}

    # --- 1a. Arçelik product reference values ---
    logger.info("=" * 80)
    logger.info("1. ARÇELIK ÜRÜN REFERANS DEĞERLERİ (runtime okuma)")
    logger.info("=" * 80)

    cursor.execute("""
        SELECT DOVIZTIPI, KDV, KDVORANI, OLCUBIRIMI,
               STOKDURUMUID, MATRISGORUNUMU, VARYANTGORUNUMU,
               STOKTAKIBI, ANASAYFAVITRINI, MAXSIPARISMIKTARI,
               MAXSIPARISMIKTARIAKTIF, SIRA, SEO_AYAR, MESAJ,
               GORUNTULENMESAYISI
        FROM URUNLER
        WHERE MARKAID = %s
    """, (ARCELIK_MARKA_ID,))
    arcelik_rows = cursor.fetchall()

    if not arcelik_rows:
        logger.error("  NO Arçelik products found in DB!")
        ref["arcelik_count"] = 0
        cursor.close()
        return ref

    ref["arcelik_count"] = len(arcelik_rows)
    logger.info(f"  Arçelik product count: {len(arcelik_rows)}")

    # For each field, show distinct values and counts
    fields_to_check = [
        "DOVIZTIPI", "KDV", "KDVORANI", "OLCUBIRIMI",
        "STOKDURUMUID", "MATRISGORUNUMU", "VARYANTGORUNUMU",
        "STOKTAKIBI", "ANASAYFAVITRINI", "MAXSIPARISMIKTARI",
        "MAXSIPARISMIKTARIAKTIF", "SIRA", "SEO_AYAR", "MESAJ",
    ]

    ref["field_patterns"] = {}
    for field in fields_to_check:
        counter = Counter(row[field] for row in arcelik_rows)
        most_common = counter.most_common()
        ref["field_patterns"][field] = {
            "values": most_common,
            "unanimous": len(most_common) == 1,
            "majority_value": most_common[0][0],
            "majority_count": most_common[0][1],
        }

        # Display
        if len(most_common) == 1:
            val, cnt = most_common[0]
            logger.info(f"  {field:30s} = {repr(val):20s}  (unanimous, {cnt}/{len(arcelik_rows)})")
        else:
            logger.info(f"  {field:30s} = MIXED:")
            for val, cnt in most_common:
                logger.info(f"    {repr(val):20s}  ({cnt}/{len(arcelik_rows)})")

    # --- 1b. STOKKODU format pattern ---
    logger.info("")
    logger.info("=" * 80)
    logger.info("2. STOKKODU FORMAT PATTERNİ")
    logger.info("=" * 80)

    cursor.execute("""
        SELECT ID, STOKKODU, URUNADI
        FROM URUNLER
        WHERE MARKAID = %s
        ORDER BY ID
    """, (ARCELIK_MARKA_ID,))
    sku_rows = cursor.fetchall()

    ref["stokkodu_samples"] = []
    has_prefix = 0
    no_prefix = 0
    for r in sku_rows:
        sku = r["STOKKODU"] or ""
        ref["stokkodu_samples"].append(sku)
        logger.info(f"  ID={r['ID']:5d}  STOKKODU='{sku}'")
        if sku.startswith("Arçelik ") or sku.startswith("AR "):
            has_prefix += 1
        else:
            no_prefix += 1

    if has_prefix > 0 and no_prefix == 0:
        ref["stokkodu_format"] = "prefix"  # "Arçelik {SKU}"
        logger.info(f"  PATTERN: Tüm {has_prefix} ürün 'Arçelik ...' prefix'li")
    elif no_prefix > 0 and has_prefix == 0:
        ref["stokkodu_format"] = "raw"  # just SKU
        logger.info(f"  PATTERN: Tüm {no_prefix} ürün raw SKU")
    else:
        ref["stokkodu_format"] = "mixed"
        logger.info(f"  PATTERN: KARIŞIK — prefix={has_prefix}, raw={no_prefix}")

    # --- 1c. OLCUBIRIMI tüm DB ---
    logger.info("")
    logger.info("=" * 80)
    logger.info("3. OLCUBIRIMI TÜM DB DEĞERLERİ")
    logger.info("=" * 80)

    cursor.execute("""
        SELECT OLCUBIRIMI, COUNT(*) AS cnt
        FROM URUNLER
        GROUP BY OLCUBIRIMI
        ORDER BY cnt DESC
    """)
    ref["olcubirimi_all"] = []
    for r in cursor.fetchall():
        ref["olcubirimi_all"].append((r["OLCUBIRIMI"], r["cnt"]))
        logger.info(f"  '{r['OLCUBIRIMI']}': {r['cnt']} ürün")

    # Palet benzeri olanları vurgula
    palet_like = [o for o, _ in ref["olcubirimi_all"] if o and "alet" in o.lower()]
    if palet_like:
        logger.info(f"  Palet benzeri mevcut değerler: {palet_like}")

    # --- 1d. DOVIZTIPI tüm DB ---
    logger.info("")
    logger.info("=" * 80)
    logger.info("4. DOVIZTIPI TÜM DB DEĞERLERİ")
    logger.info("=" * 80)

    cursor.execute("""
        SELECT DOVIZTIPI, COUNT(*) AS cnt
        FROM URUNLER
        GROUP BY DOVIZTIPI
        ORDER BY cnt DESC
    """)
    ref["doviztipi_all"] = []
    for r in cursor.fetchall():
        ref["doviztipi_all"].append((r["DOVIZTIPI"], r["cnt"]))
        logger.info(f"  '{r['DOVIZTIPI']}': {r['cnt']} ürün")

    # --- 1e. KDV + KDVORANI tüm DB ---
    logger.info("")
    logger.info("=" * 80)
    logger.info("5. KDV + KDVORANI KOMBİNASYONLARI (tüm DB)")
    logger.info("=" * 80)

    cursor.execute("""
        SELECT KDV, KDVORANI, COUNT(*) AS cnt
        FROM URUNLER
        GROUP BY KDV, KDVORANI
        ORDER BY cnt DESC
    """)
    ref["kdv_combos"] = []
    for r in cursor.fetchall():
        ref["kdv_combos"].append((r["KDV"], r["KDVORANI"], r["cnt"]))
        logger.info(f"  KDV={repr(r['KDV']):8s}  KDVORANI={r['KDVORANI']}  → {r['cnt']} ürün")

    # --- 1f. KARGOAGIRLIGI dağılım ---
    logger.info("")
    logger.info("=" * 80)
    logger.info("6. KARGOAGIRLIGI DAĞILIMI")
    logger.info("=" * 80)

    cursor.execute("""
        SELECT
            SUM(CASE WHEN KARGOAGIRLIGI IS NULL THEN 1 ELSE 0 END) AS null_cnt,
            SUM(CASE WHEN KARGOAGIRLIGI = 0 THEN 1 ELSE 0 END) AS zero_cnt,
            SUM(CASE WHEN KARGOAGIRLIGI > 0 THEN 1 ELSE 0 END) AS positive_cnt,
            COUNT(*) AS total
        FROM URUNLER
    """)
    r = cursor.fetchone()
    ref["kargo_dist"] = {
        "null": r["null_cnt"], "zero": r["zero_cnt"],
        "positive": r["positive_cnt"], "total": r["total"],
    }
    logger.info(f"  NULL={r['null_cnt']}  ZERO={r['zero_cnt']}  POSITIVE={r['positive_cnt']}  TOTAL={r['total']}")

    cursor.close()
    return ref


# ---------------------------------------------------------------------------
# 2. Category Pattern Discovery
# ---------------------------------------------------------------------------
def discover_category_pattern(conn) -> dict:
    """Discover category structure and VITRIN pattern from existing products."""
    cursor = conn.cursor(as_dict=True)
    cat_info = {}

    logger.info("")
    logger.info("=" * 80)
    logger.info("7. KATEGORİ YAPISI DOĞRULAMASI")
    logger.info("=" * 80)

    # 7a. Verify expected categories exist
    cursor.execute("""
        SELECT ID, KATEGORI, UST_KATEGORI_ID, AKTIF, SEF_URL
        FROM KATEGORILER
        WHERE ID IN (%s, %s, %s)
    """, (EXPECTED_CAT_ARCELIK_PANEL, EXPECTED_CAT_SOLAR_CATI, EXPECTED_CAT_SOLAR_MARKA))

    found_cats = {}
    for r in cursor.fetchall():
        found_cats[r["ID"]] = r
        status = "AKTIF" if r["AKTIF"] else "PASIF"
        logger.info(
            f"  ID={r['ID']:3d}  '{r['KATEGORI']}'  "
            f"UST={r['UST_KATEGORI_ID']}  {status}  SEF={r['SEF_URL']}"
        )

    cat_info["expected_categories"] = found_cats
    cat_info["all_expected_found"] = all(
        cid in found_cats for cid in
        [EXPECTED_CAT_ARCELIK_PANEL, EXPECTED_CAT_SOLAR_CATI, EXPECTED_CAT_SOLAR_MARKA]
    )
    cat_info["all_expected_active"] = all(
        found_cats.get(cid, {}).get("AKTIF", False) for cid in
        [EXPECTED_CAT_ARCELIK_PANEL, EXPECTED_CAT_SOLAR_CATI, EXPECTED_CAT_SOLAR_MARKA]
    )

    if cat_info["all_expected_found"] and cat_info["all_expected_active"]:
        logger.info("  3 kategori mevcut ve aktif")
    else:
        logger.warning("  KATEGORI DOGRULAMASI BASARISIZ")

    # 7b. Mevcut Arçelik ürünlerinin kategori bağlama pattern'i
    logger.info("")
    logger.info("=" * 80)
    logger.info("8. MEVCUT ARÇELİK KATEGORİ BAĞLAMA PATTERNİ (tüm ürünler)")
    logger.info("=" * 80)

    cursor.execute("""
        SELECT u.ID, u.STOKKODU,
               uk.KATEGORIID, uk.VITRIN, uk.SEFURL,
               k.KATEGORI AS KAT_ADI
        FROM URUNLER u
        JOIN URUNKATEGORILERI uk ON uk.URUNID = u.ID
        JOIN KATEGORILER k ON k.ID = uk.KATEGORIID
        WHERE u.MARKAID = %s
        ORDER BY u.ID, uk.VITRIN DESC, uk.KATEGORIID
    """, (ARCELIK_MARKA_ID,))

    cat_rows = cursor.fetchall()
    cat_info["product_categories"] = {}

    current_id = None
    for r in cat_rows:
        if r["ID"] != current_id:
            current_id = r["ID"]
            cat_info["product_categories"][current_id] = []
            logger.info(f"  --- ID={r['ID']} SKU={r['STOKKODU']} ---")

        cat_info["product_categories"][current_id].append({
            "kategoriid": r["KATEGORIID"],
            "vitrin": r["VITRIN"],
            "sefurl": r["SEFURL"],
            "kat_adi": r["KAT_ADI"],
        })
        vitrin_str = "VITRIN=1" if r["VITRIN"] else "VITRIN=0"
        logger.info(
            f"    KATID={r['KATEGORIID']:3d}  {vitrin_str}  "
            f"SEF={r['SEFURL']}  [{r['KAT_ADI']}]"
        )

    # 7c. Analyze pattern: how many categories per product, how many VITRIN=1
    logger.info("")
    logger.info("=" * 80)
    logger.info("9. KATEGORİ PATTERN ANALİZİ")
    logger.info("=" * 80)

    cat_count_dist = Counter()
    vitrin_count_dist = Counter()
    vitrin_categories = Counter()  # which categories have VITRIN=1

    for pid, entries in cat_info["product_categories"].items():
        cat_count_dist[len(entries)] += 1
        vitrin_ones = [e for e in entries if e["vitrin"]]
        vitrin_count_dist[len(vitrin_ones)] += 1
        for e in vitrin_ones:
            vitrin_categories[e["kategoriid"]] += 1

    logger.info("  Kategori sayısı / ürün:")
    for cnt, freq in sorted(cat_count_dist.items()):
        logger.info(f"    {cnt} kategori → {freq} ürün")

    logger.info("  VITRIN=1 sayısı / ürün:")
    for cnt, freq in sorted(vitrin_count_dist.items()):
        logger.info(f"    {cnt} VITRIN=1 → {freq} ürün")

    logger.info("  VITRIN=1 olan kategori ID'leri:")
    for cat_id, freq in vitrin_categories.most_common():
        cat_name = ""
        for entries in cat_info["product_categories"].values():
            for e in entries:
                if e["kategoriid"] == cat_id:
                    cat_name = e["kat_adi"]
                    break
            if cat_name:
                break
        logger.info(f"    KATID={cat_id:3d}  [{cat_name}]  → {freq} üründe VITRIN=1")

    cat_info["cat_count_dist"] = dict(cat_count_dist)
    cat_info["vitrin_count_dist"] = dict(vitrin_count_dist)
    cat_info["vitrin_categories"] = dict(vitrin_categories)

    # 7d. SEFURL prefix pattern extraction
    logger.info("")
    logger.info("=" * 80)
    logger.info("10. SEFURL PREFIX PATTERNLERİ")
    logger.info("=" * 80)

    sefurl_prefixes = {}
    for entries in cat_info["product_categories"].values():
        for e in entries:
            cat_id = e["kategoriid"]
            sefurl = e["sefurl"] or ""
            # Extract prefix (everything before the last segment)
            parts = sefurl.rsplit("/", 1)
            if len(parts) == 2:
                prefix = parts[0] + "/"
            else:
                prefix = ""
            if cat_id not in sefurl_prefixes:
                sefurl_prefixes[cat_id] = Counter()
            sefurl_prefixes[cat_id][prefix] += 1

    cat_info["sefurl_prefixes"] = {}
    for cat_id, prefix_counter in sorted(sefurl_prefixes.items()):
        cat_name = ""
        for entries in cat_info["product_categories"].values():
            for e in entries:
                if e["kategoriid"] == cat_id:
                    cat_name = e["kat_adi"]
                    break
            if cat_name:
                break
        most_common_prefix = prefix_counter.most_common(1)[0][0]
        cat_info["sefurl_prefixes"][cat_id] = most_common_prefix
        logger.info(f"  KATID={cat_id:3d}  [{cat_name}]")
        for prefix, cnt in prefix_counter.most_common():
            logger.info(f"    prefix='{prefix}'  ({cnt} ürün)")

    cursor.close()
    return cat_info


# ---------------------------------------------------------------------------
# 3. Duplicate & Slug Checks
# ---------------------------------------------------------------------------
def run_conflict_checks(conn, ref: dict) -> dict:
    """Check for duplicate SKUs, names, and slug conflicts."""
    cursor = conn.cursor(as_dict=True)
    conflicts = {
        "duplicate_skus": [],
        "duplicate_names": [],
        "slug_conflicts": [],
    }

    logger.info("")
    logger.info("=" * 80)
    logger.info("11. DUPLICATE & SLUG KONTROLLERI")
    logger.info("=" * 80)

    # Build both formats to check
    for panel in PANELS:
        raw_sku = panel["sku"]
        prefixed_sku = f"Arçelik {panel['sku']}"

        # Check BOTH formats
        cursor.execute(
            "SELECT ID, STOKKODU, URUNADI FROM URUNLER WHERE STOKKODU IN (%s, %s)",
            (raw_sku, prefixed_sku),
        )
        dupes = cursor.fetchall()
        for d in dupes:
            logger.warning(f"  DUPLICATE SKU: ID={d['ID']} '{d['STOKKODU']}'")
            conflicts["duplicate_skus"].append(d)

    if not conflicts["duplicate_skus"]:
        logger.info(f"  SKU: 0/{len(PANELS)} duplicate (both raw and prefixed checked)")

    # Name duplicate check
    for panel in PANELS:
        name = make_product_name(panel, ref)
        cursor.execute(
            "SELECT ID, STOKKODU, URUNADI FROM URUNLER WHERE URUNADI = %s",
            (name,),
        )
        dupes = cursor.fetchall()
        for d in dupes:
            logger.warning(f"  DUPLICATE NAME: ID={d['ID']} '{d['URUNADI']}'")
            conflicts["duplicate_names"].append(d)

    if not conflicts["duplicate_names"]:
        logger.info(f"  NAME: 0/{len(PANELS)} duplicate")

    # Slug uniqueness check
    for panel in PANELS:
        slug = make_slug(panel["sku"])
        # Check all possible SEFURL patterns from discovered prefixes
        cursor.execute(
            "SELECT SEFURL FROM URUNKATEGORILERI WHERE SEFURL LIKE %s",
            (f"%{slug}%",),
        )
        matches = cursor.fetchall()
        for m in matches:
            logger.warning(f"  SLUG CONFLICT: '{m['SEFURL']}' matches slug '{slug}'")
            conflicts["slug_conflicts"].append(m["SEFURL"])

    if not conflicts["slug_conflicts"]:
        logger.info(f"  SLUG: 0/{len(PANELS)} conflict")

    cursor.close()
    return conflicts


def make_product_name(panel: dict, ref: dict) -> str:
    """Deterministic product name."""
    return (
        f"Arçelik {panel['sku']} \u2013 {panel['pmax_w']}W "
        f"{panel['panel_type']} Güneş Paneli "
        f"(Palet: {panel['pallet_qty']} Adet)"
    )


def make_stokkodu(sku: str, ref: dict) -> str:
    """STOKKODU format: 'Arçelik {SKU}' (confirmed — 11/11 pattern)."""
    # Runtime verification: check discovered pattern matches confirmed
    fmt = ref.get("stokkodu_format", "unknown")
    if fmt != CONFIRMED_STOKKODU_FORMAT and fmt != "unknown":
        logger.warning(
            f"  STOKKODU format mismatch: confirmed='{CONFIRMED_STOKKODU_FORMAT}', "
            f"discovered='{fmt}'"
        )
    return f"Arçelik {sku}"


# ---------------------------------------------------------------------------
# 4. Build Analysis Records
# ---------------------------------------------------------------------------
def build_analysis_records(panels: list, ref: dict, cat_info: dict,
                           conflicts: dict, watt_cost: float | None) -> list:
    """Build analysis records with action determination."""
    records = []
    dup_skus = {d["STOKKODU"] for d in conflicts["duplicate_skus"]}
    dup_names = {d["URUNADI"] for d in conflicts["duplicate_names"]}
    slug_set = set(conflicts["slug_conflicts"])

    # Determine majority values for DB reference fields
    majority = {}
    for field, info in ref.get("field_patterns", {}).items():
        majority[field] = info["majority_value"]

    for panel in panels:
        stokkodu = make_stokkodu(panel["sku"], ref)
        urunadi = make_product_name(panel, ref)
        slug = make_slug(panel["sku"])

        # Build proposed SEFURLs from discovered prefixes
        proposed_sefurls = {}
        for cat_id, prefix in cat_info.get("sefurl_prefixes", {}).items():
            proposed_sefurls[cat_id] = f"{prefix}{slug}"

        # Also build for expected panel categories if not in discovered prefixes
        # (Arçelik currently has inverters, not panels — prefixes may differ)
        if EXPECTED_CAT_ARCELIK_PANEL not in proposed_sefurls:
            cat_data = cat_info.get("expected_categories", {}).get(EXPECTED_CAT_ARCELIK_PANEL)
            if cat_data:
                proposed_sefurls[EXPECTED_CAT_ARCELIK_PANEL] = f"{cat_data['SEF_URL']}{slug}"
        if EXPECTED_CAT_SOLAR_CATI not in proposed_sefurls:
            cat_data = cat_info.get("expected_categories", {}).get(EXPECTED_CAT_SOLAR_CATI)
            if cat_data:
                proposed_sefurls[EXPECTED_CAT_SOLAR_CATI] = f"{cat_data['SEF_URL']}{slug}"
        if EXPECTED_CAT_SOLAR_MARKA not in proposed_sefurls:
            cat_data = cat_info.get("expected_categories", {}).get(EXPECTED_CAT_SOLAR_MARKA)
            if cat_data:
                proposed_sefurls[EXPECTED_CAT_SOLAR_MARKA] = f"{cat_data['SEF_URL']}{slug}"

        # Conflict checks
        is_dup_sku = stokkodu in dup_skus
        is_dup_name = urunadi in dup_names
        has_slug_conflict = any(s in slug_set for s in proposed_sefurls.values())

        # Required fields assessment
        required_issues = []
        if not cat_info.get("all_expected_found"):
            required_issues.append("category_missing")
        if not cat_info.get("all_expected_active"):
            required_issues.append("category_inactive")
        if ref.get("stokkodu_format") == "mixed":
            required_issues.append("stokkodu_format_ambiguous")
        if panel["weight_source"] == "assumed":
            required_issues.append("weight_assumed")

        # OLCUBIRIMI — confirmed: dynamic palet format per product
        olcubirimi = make_olcubirimi(panel["pallet_qty"])

        # Determine action
        if is_dup_sku:
            action = "ALREADY_EXISTS"
            reason = f"STOKKODU '{stokkodu}' already in DB"
        elif is_dup_name:
            action = "MANUAL_REVIEW"
            reason = f"URUNADI already in DB"
        elif has_slug_conflict:
            action = "MANUAL_REVIEW"
            reason = f"Slug conflict for '{slug}'"
        elif required_issues:
            action = "MANUAL_REVIEW"
            reason = f"Issues: {', '.join(required_issues)}"
        else:
            action = "INSERT_CANDIDATE"
            reason = "Ready"

        # Pricing
        pricing = calc_pricing(panel, watt_cost) if watt_cost else {
            "pallet_power_w": panel["pmax_w"] * panel["pallet_qty"],
            "watt_cost_usd": None,
            "pallet_cost_usd": None,
            "fiyat1": None,
            "alisfiyati": None,
        }

        record = {
            **panel,
            "stokkodu": stokkodu,
            "urunadi": urunadi,
            "slug": slug,
            "proposed_sefurls": proposed_sefurls,
            "duplicate_sku": is_dup_sku,
            "duplicate_name": is_dup_name,
            "slug_unique": not has_slug_conflict,
            "category_verified": cat_info.get("all_expected_active", False),
            "olcubirimi": olcubirimi,
            "images_missing": True,
            "required_issues": required_issues,
            "required_fields_missing": len(required_issues) > 0,
            "insert_ready": action == "INSERT_CANDIDATE",
            "db_ref_majority": majority,
            "action": action,
            "reason": reason,
            **pricing,
        }
        records.append(record)

    return records


# ---------------------------------------------------------------------------
# 5. Display & CSV
# ---------------------------------------------------------------------------
def display_records(records: list, ref: dict, watt_cost: float | None):
    """Display analysis results."""
    majority = {}
    for field, info in ref.get("field_patterns", {}).items():
        majority[field] = info

    logger.info("")
    logger.info("=" * 80)
    logger.info("12. DATASET ÖNİZLEMESİ")
    logger.info("=" * 80)
    logger.info(
        f"{'#':>2}  {'SKU':<28}  {'Pmax':>5}  {'Plt':>3}  "
        f"{'Tip':<20}  {'Wt':>5}  {'WtSrc':<5}  {'Action':<18}"
    )
    logger.info("-" * 105)
    for i, r in enumerate(records, 1):
        logger.info(
            f"{i:2d}  {r['sku']:<28}  {r['pmax_w']:>5}W  {r['pallet_qty']:>3}  "
            f"{r['panel_type']:<20}  {r['weight_kg']:>5.1f}  {r['weight_source']:<5}  "
            f"{r['action']:<18}"
        )

    if watt_cost:
        logger.info("")
        logger.info("=" * 80)
        logger.info("13. FİYAT TABLOSU")
        logger.info("=" * 80)
        doviz = majority.get("DOVIZTIPI", {}).get("majority_value", "?")
        kdv = majority.get("KDV", {}).get("majority_value", "?")
        kdvorani = majority.get("KDVORANI", {}).get("majority_value", "?")
        logger.info(f"  Watt cost: ${watt_cost} | Döviz: {doviz} | KDV: {kdv} | KDVOranı: {kdvorani}")
        logger.info("")
        logger.info(
            f"{'#':>2}  {'SKU':<28}  {'Pmax':>5}  {'Plt':>3}  "
            f"{'PltPwr':>8}  {'Fiyat1':>12}  {'AlısFyt':>12}"
        )
        logger.info("-" * 90)
        for i, r in enumerate(records, 1):
            fiyat = f"${r['fiyat1']:,.2f}" if r["fiyat1"] else "N/A"
            alis = f"${r['alisfiyati']:,.2f}" if r["alisfiyati"] else "N/A"
            pwr = f"{r['pallet_power_w']:,}W"
            logger.info(
                f"{i:2d}  {r['sku']:<28}  {r['pmax_w']:>5}W  {r['pallet_qty']:>3}  "
                f"{pwr:>8}  {fiyat:>12}  {alis:>12}"
            )

    # Product names
    logger.info("")
    logger.info("=" * 80)
    logger.info("14. ÖNERİLEN ÜRÜN ADLARI")
    logger.info("=" * 80)
    for r in records:
        logger.info(f"  {r['urunadi']}")

    # STOKKODU
    logger.info("")
    logger.info("=" * 80)
    logger.info("15. ÖNERİLEN STOKKODU")
    logger.info("=" * 80)
    for r in records:
        logger.info(f"  {r['stokkodu']}")

    # SEFURLs (only panel categories: 74, 49, 11)
    logger.info("")
    logger.info("=" * 80)
    logger.info("16. ÖNERİLEN SEFURL (sadece panel kategorileri)")
    logger.info("=" * 80)
    panel_cat_ids = {EXPECTED_CAT_ARCELIK_PANEL, EXPECTED_CAT_SOLAR_CATI, EXPECTED_CAT_SOLAR_MARKA}
    for r in records[:3]:
        logger.info(f"  SKU: {r['sku']}")
        for cat_id, sefurl in sorted(r["proposed_sefurls"].items()):
            if cat_id in panel_cat_ids:
                vitrin = "VITRIN=1" if cat_id != EXPECTED_CAT_SOLAR_MARKA else "VITRIN=0"
                logger.info(f"    [{cat_id:3d}] {vitrin}  {sefurl}")
        logger.info("")
    logger.info("  (Tüm 12 ürün aynı pattern — sadece slug değişir)")

    # OLCUBIRIMI (confirmed)
    logger.info("")
    logger.info("=" * 80)
    logger.info("17. OLCUBIRIMI (onaylanmış karar)")
    logger.info("=" * 80)
    olcu_29 = make_olcubirimi(29)
    olcu_37 = make_olcubirimi(37)
    cnt_29 = sum(1 for r in records if r["pallet_qty"] == 29)
    cnt_37 = sum(1 for r in records if r["pallet_qty"] == 37)
    logger.info(f"  29'luk ürünler ({cnt_29} adet): '{olcu_29}'")
    logger.info(f"  37'lik ürünler ({cnt_37} adet): '{olcu_37}'")

    # Summary
    logger.info("")
    logger.info("=" * 80)
    logger.info("18. ÖZET")
    logger.info("=" * 80)
    insert_ready = sum(1 for r in records if r["insert_ready"])
    manual_review = sum(1 for r in records if r["action"] == "MANUAL_REVIEW")
    already_exists = sum(1 for r in records if r["action"] == "ALREADY_EXISTS")

    logger.info(f"  Toplam panel: {len(records)}")
    logger.info(f"  INSERT_CANDIDATE: {insert_ready}")
    logger.info(f"  MANUAL_REVIEW: {manual_review}")
    logger.info(f"  ALREADY_EXISTS: {already_exists}")
    logger.info(f"  Görselsiz: {sum(1 for r in records if r['images_missing'])}")

    # Confirmed decisions
    logger.info("")
    logger.info("  Onaylanmış kararlar:")
    logger.info(f"    DOVIZTIPI       = '{CONFIRMED_DOVIZTIPI}'")
    logger.info(f"    KDV             = {CONFIRMED_KDV}")
    logger.info(f"    KDVORANI        = {CONFIRMED_KDVORANI}")
    logger.info(f"    STOKKODU format = '{CONFIRMED_STOKKODU_FORMAT}' (Arçelik {{SKU}})")
    logger.info(f"    OLCUBIRIMI      = dinamik palet format")
    logger.info(f"    Kategoriler     = [74] VITRIN=1, [49] VITRIN=1, [11] VITRIN=0")

    # Issues requiring decision
    all_issues = set()
    for r in records:
        all_issues.update(r["required_issues"])
    if all_issues:
        logger.info("")
        logger.info(f"  Çözülmesi gereken konular:")
        for issue in sorted(all_issues):
            logger.info(f"    - {issue}")
    else:
        logger.info("")
        logger.info(f"  Çözülmesi gereken konu YOK")

    # DB reference values that will be used
    logger.info("")
    logger.info("  DB referans değerleri (runtime okunan):")
    for field in ["DOVIZTIPI", "KDV", "KDVORANI", "OLCUBIRIMI",
                   "STOKDURUMUID", "MATRISGORUNUMU", "VARYANTGORUNUMU",
                   "STOKTAKIBI", "ANASAYFAVITRINI", "MAXSIPARISMIKTARI", "SIRA"]:
        info = majority.get(field, {})
        val = info.get("majority_value", "?") if isinstance(info, dict) else info
        unanimous = info.get("unanimous", False) if isinstance(info, dict) else False
        tag = "unanimous" if unanimous else "MIXED"
        logger.info(f"    {field:30s} = {repr(val):20s}  ({tag})")


def write_csv_report(records: list, output_path: Path, ref: dict):
    """Write CSV report."""
    fieldnames = [
        "sku", "stokkodu", "urunadi", "pmax_w", "pallet_qty", "panel_type",
        "pallet_power_w", "watt_cost_usd", "pallet_cost_usd",
        "fiyat1", "alisfiyati",
        "doviztipi", "kdv", "kdvorani", "olcubirimi",
        "stokkodu_format", "markaid",
        "cat_primary", "cat_secondary", "cat_parent",
        "slug", "sefurl_primary",
        "weight_kg", "weight_source",
        "duplicate_sku", "duplicate_name", "slug_unique",
        "category_verified", "images_missing",
        "required_issues", "insert_ready",
        "action", "reason",
    ]

    majority = {}
    for field, info in ref.get("field_patterns", {}).items():
        majority[field] = info["majority_value"]

    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for r in records:
            writer.writerow({
                "sku": r["sku"],
                "stokkodu": r["stokkodu"],
                "urunadi": r["urunadi"],
                "pmax_w": r["pmax_w"],
                "pallet_qty": r["pallet_qty"],
                "panel_type": r["panel_type"],
                "pallet_power_w": r["pallet_power_w"],
                "watt_cost_usd": r["watt_cost_usd"] or "",
                "pallet_cost_usd": r["pallet_cost_usd"] or "",
                "fiyat1": r["fiyat1"] or "",
                "alisfiyati": r["alisfiyati"] or "",
                "doviztipi": CONFIRMED_DOVIZTIPI,
                "kdv": CONFIRMED_KDV,
                "kdvorani": float(CONFIRMED_KDVORANI),
                "olcubirimi": r["olcubirimi"],
                "stokkodu_format": ref.get("stokkodu_format", ""),
                "markaid": ARCELIK_MARKA_ID,
                "cat_primary": f"{EXPECTED_CAT_ARCELIK_PANEL} (Arçelik)",
                "cat_secondary": f"{EXPECTED_CAT_SOLAR_CATI} (Solar Paneller Çatı)",
                "cat_parent": f"{EXPECTED_CAT_SOLAR_MARKA} (Solar Panel Markaları)",
                "slug": r["slug"],
                "sefurl_primary": r["proposed_sefurls"].get(EXPECTED_CAT_ARCELIK_PANEL, ""),
                "weight_kg": r["weight_kg"],
                "weight_source": r["weight_source"],
                "duplicate_sku": r["duplicate_sku"],
                "duplicate_name": r["duplicate_name"],
                "slug_unique": r["slug_unique"],
                "category_verified": r["category_verified"],
                "images_missing": r["images_missing"],
                "required_issues": "; ".join(r["required_issues"]) if r["required_issues"] else "",
                "insert_ready": r["insert_ready"],
                "action": r["action"],
                "reason": r["reason"],
            })

    logger.info(f"  CSV rapor: {output_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Arçelik 12 Solar Panel — Analysis & Planning (Faz A)"
    )
    parser.add_argument(
        "--watt-cost", type=float, default=None,
        help="Watt cost in USD (e.g. 0.23) — enables pricing calculation"
    )
    args = parser.parse_args()

    mode = "ANALYSIS + PRICING" if args.watt_cost else "ANALYSIS"

    logger.info(f"=== Arçelik Panel Analysis — {mode} — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")
    logger.info(f"  Target: {EXPECTED_PANEL_COUNT} panels")
    logger.info(f"  Watt cost: {args.watt_cost or 'not set (analysis only)'}")
    logger.info(f"  Log: {detail_log_path}")
    logger.info(f"  NOTE: Bu script sadece ANALİZ yapar. DB'ye YAZMAZ.")
    logger.info("")

    conn = get_db_connection()

    try:
        # 1. Discover DB reference patterns (runtime)
        ref = discover_db_reference(conn)

        # 2. Discover category patterns (runtime)
        cat_info = discover_category_pattern(conn)

        # 3. Run conflict checks
        conflicts = run_conflict_checks(conn, ref)

        # 4. Build analysis records
        records = build_analysis_records(PANELS, ref, cat_info, conflicts, args.watt_cost)

        # 5. Display results
        display_records(records, ref, args.watt_cost)

        # 6. Write CSV report
        csv_path = SCRIPT_DIR / "arcelik_panel_insert_report.csv"
        write_csv_report(records, csv_path, ref)

        # 7. Next steps
        logger.info("")
        logger.info("=" * 80)
        logger.info("SONRAKI ADIMLAR")
        logger.info("=" * 80)
        logger.info("  1. Yukarıdaki referans değerlerini doğrulayın")
        logger.info("  2. OLCUBIRIMI kararı verin (Adet / Palet / Özel)")
        logger.info("  3. STOKKODU format kararı verin")
        logger.info("  4. Kategori bağlama planını onaylayın")
        logger.info("  5. Watt maliyeti verin (--watt-cost X)")
        logger.info("  6. Fiyat tablosunu gözden geçirin")
        logger.info("  7. Onay sonrası: Faz B insert script yazılacak")
        logger.info("")
        logger.info("  Bu script DB'ye YAZMAZ. Insert için Faz B gereklidir.")

    finally:
        conn.close()
        logger.info("DB connection closed.")

    logger.info(f"Done. Log: {detail_log_path}")


if __name__ == "__main__":
    main()
