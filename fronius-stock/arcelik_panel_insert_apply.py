#!/usr/bin/env python3
"""
Arçelik 12 Solar Panel — Faz B: INSERT Apply Script

Inserts 12 solar panel products into MSSQL with full safety guards.
ALL 47 non-identity URUNLER columns are explicitly set (no DB default reliance).
Requires Faz A analysis to have been completed and approved.

Usage:
  python3 arcelik_panel_insert_apply.py --watt-cost 0.23                    # simulation
  python3 arcelik_panel_insert_apply.py --watt-cost 0.23 --apply            # INSERT
  python3 arcelik_panel_insert_apply.py --watt-cost 0.23 --stok 500 --apply # custom STOK

Output:
  - Simulation JSON: logs/arcelik_panel_simulation_*.json
  - Pre-insert snapshot: logs/arcelik_panel_preinsert_snapshot_*.json
  - Apply log: logs/arcelik_panel_apply_*.log
  - Inserted records: logs/arcelik_panel_inserted_*.json
"""

import argparse
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
EXPECTED_INSERT_COUNT = 12

# Category IDs (verified in Faz A against DB)
CAT_ARCELIK_PANEL = 74    # Arçelik under Solar Panel Markaları
CAT_SOLAR_CATI = 49       # Solar Paneller Çatı
CAT_SOLAR_MARKA = 11      # Solar Panel Markaları (parent)

# (category_id, vitrin_value)  — vitrin as int for MSSQL bit
CATEGORY_BINDINGS = [
    (CAT_ARCELIK_PANEL, 1),   # VITRIN=1
    (CAT_SOLAR_CATI, 1),      # VITRIN=1
    (CAT_SOLAR_MARKA, 0),     # VITRIN=0
]

# Confirmed decisions (approved in Faz A)
CONFIRMED_DOVIZTIPI = "USD"
CONFIRMED_KDV = 0               # MSSQL bit: 0 = KDV dahil değil
CONFIRMED_KDVORANI = Decimal("20.00")
DEFAULT_STOK = 1000              # 10/11 active Arçelik = 1000 (placeholder, STOKTAKIBI=False)

# ---------------------------------------------------------------------------
# Product Dataset (12 panels — Arçelik Enerji Çözümleri Kataloğu 2026)
# ---------------------------------------------------------------------------
PANELS = [
    {"sku": "ARCLK-144PV10T-GG-590",  "pmax_w": 590, "pallet_qty": 29, "panel_type": "Cam-Cam Bifacial", "weight_kg": 32.0},
    {"sku": "ARCLK-144PV10T-GG-595",  "pmax_w": 595, "pallet_qty": 29, "panel_type": "Cam-Cam Bifacial", "weight_kg": 32.0},
    {"sku": "ARCLK-144PV10T-GG-600",  "pmax_w": 600, "pallet_qty": 29, "panel_type": "Cam-Cam Bifacial", "weight_kg": 32.0},
    {"sku": "ARCLK-144PV10RT-GG-600", "pmax_w": 600, "pallet_qty": 29, "panel_type": "Cam-Cam Bifacial", "weight_kg": 32.0},
    {"sku": "ARCLK-144PV10RT-GG-605", "pmax_w": 605, "pallet_qty": 29, "panel_type": "Cam-Cam Bifacial", "weight_kg": 32.0},
    {"sku": "ARCLK-144PV10RT-GG-610", "pmax_w": 610, "pallet_qty": 29, "panel_type": "Cam-Cam Bifacial", "weight_kg": 32.0},
    {"sku": "ARCLK-144PV10RT-GG-615", "pmax_w": 615, "pallet_qty": 29, "panel_type": "Cam-Cam Bifacial", "weight_kg": 32.0},
    {"sku": "ARCLK-144PV10RT-600",    "pmax_w": 600, "pallet_qty": 37, "panel_type": "Cam-Cam",          "weight_kg": 32.5},
    {"sku": "ARCLK-132PVRT-GG-610",   "pmax_w": 610, "pallet_qty": 29, "panel_type": "Cam-Cam Bifacial", "weight_kg": 32.5},
    {"sku": "ARCLK-132PVRT-GG-615",   "pmax_w": 615, "pallet_qty": 29, "panel_type": "Cam-Cam Bifacial", "weight_kg": 32.5},
    {"sku": "ARCLK-132PVRT-GG-620",   "pmax_w": 620, "pallet_qty": 29, "panel_type": "Cam-Cam Bifacial", "weight_kg": 32.5},
    {"sku": "ARCLK-132PVRT-GG-625",   "pmax_w": 625, "pallet_qty": 29, "panel_type": "Cam-Cam Bifacial", "weight_kg": 32.5},
]

# Template columns — majority values from existing Arçelik products (runtime read)
TEMPLATE_COLUMNS = [
    # Codes & tags
    "ENTEGREKODU", "RAPORKODU", "ETIKETLER",
    # Price tiers
    "PIYASAFIYATI", "FIYAT2", "FIYAT3", "FIYAT4", "FIYAT5",
    # Content & SEO
    "URUNDETAY", "METAKEYWORDS", "METADESCRIPTION", "PAGETITLE", "URUNACIKLAMASI",
    # Display & ordering
    "ANASAYFAVITRINI", "ANASAYFAVITRINSIRASI", "SIRA", "SEO_AYAR", "MESAJ",
    # Variant & matrix
    "MATRISGORUNUMU", "VARYANTGORUNUMU",
    # Stock & limits
    "STOKTAKIBI", "MAXSIPARISMIKTARI", "MAXSIPARISMIKTARIAKTIF",
    # Detail reserves
    "DETAY_YEDEK_1", "DETAY_YEDEK_2", "DETAY_YEDEK_3", "DETAY_YEDEK_4", "DETAY_YEDEK_5",
]

# Nullable group/variant IDs — always None in reference, set explicitly as None
NULLABLE_NONE_COLUMNS = [
    "STOKDURUMUID", "URUNGRUPID", "URUNGRUPID2",
    "VARYANTGRUPID", "ANASAYVAVITRINVARYANTID", "MATRISGRUPID",
]

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
apply_log_path = LOG_DIR / f"arcelik_panel_apply_{ts}.log"

logger = logging.getLogger("arcelik_panel_apply")
logger.setLevel(logging.DEBUG)

fh = logging.FileHandler(apply_log_path, encoding="utf-8")
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
    slug = sku.lower()
    slug = re.sub(r"[^a-z0-9-]", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")


def make_olcubirimi(pallet_qty: int) -> str:
    return f"Palet ({pallet_qty} adet solar panel)"


def make_stokkodu(sku: str) -> str:
    return f"Arçelik {sku}"


def make_product_name(panel: dict) -> str:
    return (
        f"Arçelik {panel['sku']} \u2013 {panel['pmax_w']}W "
        f"{panel['panel_type']} Güneş Paneli "
        f"(Palet: {panel['pallet_qty']} Adet)"
    )


def calc_pricing(panel: dict, watt_cost: float) -> dict:
    pmax = Decimal(str(panel["pmax_w"]))
    cost = Decimal(str(watt_cost))
    qty = Decimal(str(panel["pallet_qty"]))
    pallet_cost = (pmax * cost * qty).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return {
        "pallet_power_w": int(pmax * qty),
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
# 1. Pre-flight checks
# ---------------------------------------------------------------------------
def preflight(conn) -> dict:
    """Comprehensive pre-flight: template, schema, categories, duplicates."""
    cursor = conn.cursor(as_dict=True)
    ctx = {"errors": [], "warnings": []}

    logger.info("")
    logger.info("=" * 70)
    logger.info("1. PRE-FLIGHT CHECKS")
    logger.info("=" * 70)

    # ── 1a. Schema column coverage check ──
    logger.info("  [1a] URUNLER schema coverage check...")
    cursor.execute("""
        SELECT COLUMN_NAME, IS_NULLABLE, COLUMN_DEFAULT
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = 'URUNLER'
        ORDER BY ORDINAL_POSITION
    """)
    all_db_cols = cursor.fetchall()

    cursor.execute("""
        SELECT name FROM sys.identity_columns
        WHERE object_id = OBJECT_ID('URUNLER')
    """)
    identity_cols = {r["name"] for r in cursor.fetchall()}

    # Our INSERT set: product + template + nullable_none
    our_cols = set()
    our_cols.update([
        "URUNADI", "STOKKODU", "MARKAID", "FIYAT1", "ALISFIYATI",
        "STOK", "SATILMASAYISI", "GORUNTULENMESAYISI", "KARGOAGIRLIGI",
        "DOVIZTIPI", "KDV", "KDVORANI", "OLCUBIRIMI",
    ])
    our_cols.update(TEMPLATE_COLUMNS)
    our_cols.update(NULLABLE_NONE_COLUMNS)

    missing_safe = []
    for col in all_db_cols:
        name = col["COLUMN_NAME"]
        if name in identity_cols:
            continue
        if name not in our_cols:
            nullable = col["IS_NULLABLE"] == "YES"
            has_default = col["COLUMN_DEFAULT"] is not None
            if not nullable and not has_default:
                ctx["errors"].append(
                    f"CRITICAL: Column '{name}' is NOT NULL without DEFAULT and not in INSERT set"
                )
                logger.error(f"    CRITICAL: {name} NOT NULL, no DEFAULT, not in INSERT set!")
            else:
                missing_safe.append(name)
                logger.warning(f"    UNCOVERED: {name} (nullable={nullable}, default={has_default})")

    ctx["missing_safe_columns"] = missing_safe
    covered = len(our_cols)
    total_non_id = len(all_db_cols) - len(identity_cols)
    logger.info(f"    Coverage: {covered}/{total_non_id} non-identity columns in INSERT set")

    if missing_safe:
        logger.warning(f"    {len(missing_safe)} columns not in INSERT set (all nullable/defaulted)")
    else:
        logger.info(f"    ALL non-identity columns covered")

    # ── 1b. URUNKATEGORILERI schema check ──
    logger.info("  [1b] URUNKATEGORILERI schema check...")
    cursor.execute("""
        SELECT COLUMN_NAME, IS_NULLABLE, COLUMN_DEFAULT
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = 'URUNKATEGORILERI'
        ORDER BY ORDINAL_POSITION
    """)
    uk_db_cols = cursor.fetchall()

    cursor.execute("""
        SELECT name FROM sys.identity_columns
        WHERE object_id = OBJECT_ID('URUNKATEGORILERI')
    """)
    uk_identity = {r["name"] for r in cursor.fetchall()}

    uk_our_cols = {"URUNID", "KATEGORIID", "VITRIN", "SEFURL", "VITRINVARYANTID"}
    uk_missing = []
    for col in uk_db_cols:
        name = col["COLUMN_NAME"]
        if name in uk_identity:
            continue
        if name not in uk_our_cols:
            nullable = col["IS_NULLABLE"] == "YES"
            has_default = col["COLUMN_DEFAULT"] is not None
            if not nullable and not has_default:
                ctx["errors"].append(
                    f"CRITICAL: URUNKATEGORILERI.{name} NOT NULL without DEFAULT"
                )
            else:
                uk_missing.append(name)

    if uk_missing:
        logger.warning(f"    URUNKATEGORILERI uncovered: {uk_missing}")
    else:
        logger.info(f"    URUNKATEGORILERI: 5/5 non-identity columns covered")

    # ── 1c. Template values (majority from existing Arçelik) ──
    logger.info("  [1c] Reading Arçelik template values (majority)...")
    template_cols_sql = ", ".join(TEMPLATE_COLUMNS)
    cursor.execute(f"""
        SELECT {template_cols_sql}
        FROM URUNLER
        WHERE MARKAID = %s
    """, (ARCELIK_MARKA_ID,))
    all_rows = cursor.fetchall()

    if not all_rows:
        ctx["errors"].append("No Arçelik products found for template!")
        logger.error("    ABORT: No Arçelik products found!")
        cursor.close()
        return ctx

    logger.info(f"    Arçelik products in DB: {len(all_rows)}")

    template = {}
    for col in TEMPLATE_COLUMNS:
        counter = Counter()
        for row in all_rows:
            val = row[col]
            # For ntext/long strings, just check if empty or not
            if isinstance(val, str) and len(val) > 100:
                counter["<long_text>"] += 1
                template[col] = val  # take actual value from first match
            else:
                counter[val] += 1
        majority_val, majority_cnt = counter.most_common(1)[0]
        if majority_val != "<long_text>":
            template[col] = majority_val
        unanimous = len(counter) == 1
        tag = "unanimous" if unanimous else f"majority {majority_cnt}/{len(all_rows)}"
        display_val = repr(template[col])
        if len(display_val) > 60:
            display_val = display_val[:57] + "..."
        logger.info(f"    {col:30s} = {display_val:60s} ({tag})")

    ctx["template"] = template

    # ── 1d. Category verification ──
    logger.info("  [1d] Category verification...")
    cat_ids = [c[0] for c in CATEGORY_BINDINGS]
    placeholders = ",".join(["%s"] * len(cat_ids))
    cursor.execute(f"""
        SELECT ID, KATEGORI, UST_KATEGORI_ID, AKTIF, SEF_URL
        FROM KATEGORILER
        WHERE ID IN ({placeholders})
    """, tuple(cat_ids))

    found_cats = {}
    for r in cursor.fetchall():
        found_cats[r["ID"]] = r
        status = "OK" if r["AKTIF"] else "PASIF!"
        logger.info(
            f"    ID={r['ID']:3d}  [{r['KATEGORI']}]  "
            f"SEF_URL='{r['SEF_URL']}'  {status}"
        )

    missing_cats = [cid for cid in cat_ids if cid not in found_cats]
    inactive_cats = [cid for cid in cat_ids if cid in found_cats and not found_cats[cid]["AKTIF"]]
    if missing_cats:
        ctx["errors"].append(f"Missing categories: {missing_cats}")
    if inactive_cats:
        ctx["errors"].append(f"Inactive categories: {inactive_cats}")

    ctx["categories"] = found_cats

    # Check SEF_URL non-empty for primary and secondary
    for cat_id in [CAT_ARCELIK_PANEL, CAT_SOLAR_CATI, CAT_SOLAR_MARKA]:
        cat = found_cats.get(cat_id, {})
        sefurl = cat.get("SEF_URL", "")
        if not sefurl:
            ctx["errors"].append(f"Category {cat_id} has empty SEF_URL")

    # ── 1e. VITRINVARYANTID reference ──
    logger.info("  [1e] VITRINVARYANTID reference...")
    cursor.execute("""
        SELECT TOP 1 VITRINVARYANTID
        FROM URUNKATEGORILERI uk
        JOIN URUNLER u ON u.ID = uk.URUNID
        WHERE u.MARKAID = %s
    """, (ARCELIK_MARKA_ID,))
    uk_ref = cursor.fetchone()
    ctx["vitrinvaryantid_ref"] = uk_ref["VITRINVARYANTID"] if uk_ref else 0
    logger.info(f"    VITRINVARYANTID = {ctx['vitrinvaryantid_ref']}")

    # ── 1f. Duplicate SKU check ──
    logger.info("  [1f] Duplicate SKU check...")
    dup_skus = []
    for panel in PANELS:
        prefixed_sku = make_stokkodu(panel["sku"])
        cursor.execute(
            "SELECT ID, STOKKODU FROM URUNLER WHERE STOKKODU IN (%s, %s)",
            (panel["sku"], prefixed_sku),
        )
        for d in cursor.fetchall():
            dup_skus.append({"id": d["ID"], "stokkodu": d["STOKKODU"]})
            logger.warning(f"    DUPLICATE SKU: ID={d['ID']} '{d['STOKKODU']}'")

    ctx["duplicate_skus"] = dup_skus
    if not dup_skus:
        logger.info(f"    0/{len(PANELS)} duplicate SKU")

    # ── 1g. Duplicate NAME check ──
    logger.info("  [1g] Duplicate NAME check...")
    dup_names = []
    for panel in PANELS:
        name = make_product_name(panel)
        cursor.execute(
            "SELECT ID, URUNADI FROM URUNLER WHERE URUNADI = %s",
            (name,),
        )
        for d in cursor.fetchall():
            dup_names.append({"id": d["ID"], "urunadi": d["URUNADI"]})
            logger.warning(f"    DUPLICATE NAME: ID={d['ID']} '{d['URUNADI']}'")

    ctx["duplicate_names"] = dup_names
    if not dup_names:
        logger.info(f"    0/{len(PANELS)} duplicate name")

    # ── 1h. Slug uniqueness check ──
    logger.info("  [1h] Slug uniqueness check...")
    dup_slugs = []
    for panel in PANELS:
        slug = make_slug(panel["sku"])
        cursor.execute(
            "SELECT SEFURL FROM URUNKATEGORILERI WHERE SEFURL LIKE %s",
            (f"%/{slug}",),
        )
        for m in cursor.fetchall():
            dup_slugs.append({"sku": panel["sku"], "conflict": m["SEFURL"]})
            logger.warning(f"    SLUG CONFLICT: '{m['SEFURL']}' for {panel['sku']}")

    ctx["duplicate_slugs"] = dup_slugs
    if not dup_slugs:
        logger.info(f"    0/{len(PANELS)} slug conflict")

    # ── 1i. Current Arçelik count ──
    logger.info("  [1i] Current Arçelik product count...")
    cursor.execute(
        "SELECT COUNT(*) AS cnt FROM URUNLER WHERE MARKAID = %s",
        (ARCELIK_MARKA_ID,),
    )
    ctx["arcelik_count_before"] = cursor.fetchone()["cnt"]
    ctx["arcelik_count_expected"] = ctx["arcelik_count_before"] + EXPECTED_INSERT_COUNT
    logger.info(f"    Current: {ctx['arcelik_count_before']}")
    logger.info(f"    Expected after: {ctx['arcelik_count_expected']}")

    cursor.close()
    return ctx


# ---------------------------------------------------------------------------
# 2. Apply guards
# ---------------------------------------------------------------------------
def apply_guards(ctx: dict, watt_cost: float) -> bool:
    """Check all apply guards. Returns True only if ALL pass."""
    logger.info("")
    logger.info("=" * 70)
    logger.info("2. APPLY GUARDS")
    logger.info("=" * 70)

    guards = [
        ("watt_cost > 0",              watt_cost is not None and watt_cost > 0),
        ("panel_count == 12",           len(PANELS) == EXPECTED_INSERT_COUNT),
        ("duplicate_sku == 0",          len(ctx["duplicate_skus"]) == 0),
        ("duplicate_name == 0",         len(ctx["duplicate_names"]) == 0),
        ("duplicate_slug == 0",         len(ctx["duplicate_slugs"]) == 0),
        ("categories_ok",              len(ctx["errors"]) == 0),
        ("missing_safe_columns == 0",   len(ctx["missing_safe_columns"]) == 0),
        ("template_loaded",             "template" in ctx and len(ctx["template"]) > 0),
        ("all_sefurl_non_empty",        _check_sefurls_non_empty(ctx)),
    ]

    all_pass = True
    for name, passed in guards:
        status = "PASS" if passed else "FAIL"
        logger.info(f"  [{status}] {name}")
        if not passed:
            all_pass = False

    if not all_pass:
        logger.error("  GUARDS FAILED — ABORT")
        for err in ctx["errors"]:
            logger.error(f"    {err}")
        for w in ctx["warnings"]:
            logger.warning(f"    {w}")

    return all_pass


def _check_sefurls_non_empty(ctx: dict) -> bool:
    """Verify all 3 category SEF_URLs are non-empty."""
    cats = ctx.get("categories", {})
    for cat_id in [CAT_ARCELIK_PANEL, CAT_SOLAR_CATI, CAT_SOLAR_MARKA]:
        cat = cats.get(cat_id, {})
        if not cat.get("SEF_URL", ""):
            return False
    return True


# ---------------------------------------------------------------------------
# 3. Pre-insert snapshot
# ---------------------------------------------------------------------------
def take_preinsert_snapshot(conn) -> Path:
    """Snapshot current state for each SKU before insert."""
    cursor = conn.cursor(as_dict=True)
    snapshot = []

    for panel in PANELS:
        prefixed_sku = make_stokkodu(panel["sku"])
        slug = make_slug(panel["sku"])

        cursor.execute(
            "SELECT ID, STOKKODU, URUNADI FROM URUNLER WHERE STOKKODU IN (%s, %s)",
            (panel["sku"], prefixed_sku),
        )
        existing = cursor.fetchone()

        cursor.execute(
            "SELECT SEFURL FROM URUNKATEGORILERI WHERE SEFURL LIKE %s",
            (f"%/{slug}",),
        )
        existing_sefurls = [r["SEFURL"] for r in cursor.fetchall()]

        snapshot.append({
            "sku": panel["sku"],
            "stokkodu_checked": prefixed_sku,
            "existing_product_id": existing["ID"] if existing else None,
            "existing_stokkodu": existing["STOKKODU"] if existing else None,
            "existing_urunadi": existing["URUNADI"] if existing else None,
            "existing_sefurls": existing_sefurls,
        })

    cursor.close()

    snapshot_path = LOG_DIR / f"arcelik_panel_preinsert_snapshot_{ts}.json"
    with open(snapshot_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2, default=str)

    logger.info(f"  Snapshot: {snapshot_path}")
    return snapshot_path


# ---------------------------------------------------------------------------
# 4. Build INSERT records
# ---------------------------------------------------------------------------
def build_insert_records(watt_cost: float, stok: int, ctx: dict) -> list:
    """Build complete INSERT records — ALL 47 non-identity columns per product."""
    records = []
    template = ctx["template"]
    categories = ctx["categories"]

    for panel in PANELS:
        pricing = calc_pricing(panel, watt_cost)
        slug = make_slug(panel["sku"])

        # ── All 47 columns ──
        urunler = {}

        # Group A: Product-specific (13 columns)
        urunler["URUNADI"] = make_product_name(panel)
        urunler["STOKKODU"] = make_stokkodu(panel["sku"])
        urunler["MARKAID"] = ARCELIK_MARKA_ID
        urunler["FIYAT1"] = float(pricing["fiyat1"])
        urunler["ALISFIYATI"] = float(pricing["alisfiyati"])
        urunler["STOK"] = stok
        urunler["SATILMASAYISI"] = 0
        urunler["GORUNTULENMESAYISI"] = 0
        urunler["KARGOAGIRLIGI"] = panel["weight_kg"]
        urunler["DOVIZTIPI"] = CONFIRMED_DOVIZTIPI
        urunler["KDV"] = CONFIRMED_KDV
        urunler["KDVORANI"] = float(CONFIRMED_KDVORANI)
        urunler["OLCUBIRIMI"] = make_olcubirimi(panel["pallet_qty"])

        # Group B: Template (28 columns — runtime majority from existing Arçelik)
        for col in TEMPLATE_COLUMNS:
            val = template.get(col)
            # Long HTML content (URUNDETAY, DETAY_YEDEK_*): set empty for new panels
            if col in ("URUNDETAY", "DETAY_YEDEK_1", "DETAY_YEDEK_2",
                        "DETAY_YEDEK_3", "DETAY_YEDEK_4", "DETAY_YEDEK_5"):
                urunler[col] = ""
            # SEO/content: set empty for now (to be populated later)
            elif col in ("ETIKETLER", "METAKEYWORDS", "METADESCRIPTION",
                          "PAGETITLE", "URUNACIKLAMASI"):
                urunler[col] = ""
            # PIYASAFIYATI: no market price reference for panels yet
            elif col == "PIYASAFIYATI":
                urunler[col] = None
            else:
                urunler[col] = val

        # Group C: Nullable None (6 columns — explicit None)
        for col in NULLABLE_NONE_COLUMNS:
            urunler[col] = None

        # Category bindings (3 per product)
        cat_bindings = []
        for cat_id, vitrin in CATEGORY_BINDINGS:
            cat_data = categories[cat_id]
            sefurl = f"{cat_data['SEF_URL']}{slug}"
            cat_bindings.append({
                "KATEGORIID": cat_id,
                "VITRIN": vitrin,
                "SEFURL": sefurl,
                "VITRINVARYANTID": ctx["vitrinvaryantid_ref"],
            })

        records.append({
            "panel": panel,
            "pricing": pricing,
            "slug": slug,
            "urunler": urunler,
            "cat_bindings": cat_bindings,
        })

    return records


# ---------------------------------------------------------------------------
# 5. Simulation display + JSON
# ---------------------------------------------------------------------------
def display_simulation(records: list, ctx: dict, watt_cost: float, stok: int):
    """Show what would be inserted + write simulation JSON."""
    logger.info("")
    logger.info("=" * 70)
    logger.info("SIMULATION — DRY-RUN. DB'ye YAZILMADI.")
    logger.info("=" * 70)

    logger.info(f"  Watt cost: ${watt_cost}")
    logger.info(f"  STOK: {stok}  (referans: 10/11 aktif Arçelik = 1000)")
    logger.info(f"  Insert count: {len(records)}")
    logger.info(f"  Arçelik before: {ctx['arcelik_count_before']} → after: {ctx['arcelik_count_expected']}")
    logger.info(f"  Görseller: YOK (images_missing=1, tüm 12 ürün)")

    # Product table
    logger.info("")
    logger.info(
        f"{'#':>2}  {'SKU':<28}  {'Pmax':>5}  {'Plt':>3}  "
        f"{'FIYAT1':>12}  {'STOK':>5}  {'OLCUBIRIMI':<32}"
    )
    logger.info("-" * 110)
    for i, rec in enumerate(records, 1):
        p = rec["panel"]
        v = rec["urunler"]
        logger.info(
            f"{i:2d}  {p['sku']:<28}  {p['pmax_w']:>5}W  {p['pallet_qty']:>3}  "
            f"${v['FIYAT1']:>10,.2f}  {v['STOK']:>5}  {v['OLCUBIRIMI']:<32}"
        )

    # Column coverage
    sample = records[0]["urunler"]
    product_cols = {
        "URUNADI", "STOKKODU", "MARKAID", "FIYAT1", "ALISFIYATI",
        "STOK", "SATILMASAYISI", "GORUNTULENMESAYISI", "KARGOAGIRLIGI",
        "DOVIZTIPI", "KDV", "KDVORANI", "OLCUBIRIMI",
    }
    template_set = set(TEMPLATE_COLUMNS)
    nullable_set = set(NULLABLE_NONE_COLUMNS)

    logger.info("")
    logger.info(f"  URUNLER INSERT: {len(sample)} kolon (47/47 non-identity)")
    logger.info("")
    logger.info("  Product-specific (13):")
    for col in sorted(product_cols):
        val = sample[col]
        display = repr(val)
        if len(display) > 50:
            display = display[:47] + "..."
        logger.info(f"    {col:35s} = {display}")

    logger.info("")
    logger.info("  Template/reference (28):")
    for col in sorted(template_set):
        val = sample[col]
        display = repr(val)
        if len(display) > 50:
            display = display[:47] + "..."
        logger.info(f"    {col:35s} = {display}")

    logger.info("")
    logger.info("  Nullable None (6):")
    for col in sorted(nullable_set):
        logger.info(f"    {col:35s} = None")

    # Category bindings
    logger.info("")
    logger.info("  URUNKATEGORILERI (ürün başına 3 kayıt, 5 kolon):")
    for cb in records[0]["cat_bindings"]:
        logger.info(
            f"    KATID={cb['KATEGORIID']:3d}  VITRIN={cb['VITRIN']}  "
            f"SEFURL={cb['SEFURL']}"
        )

    # SEO/content warnings
    logger.info("")
    logger.info("  Boş bırakılan SEO/içerik alanları (sonradan doldurulabilir):")
    empty_fields = ["ETIKETLER", "METAKEYWORDS", "METADESCRIPTION",
                     "PAGETITLE", "URUNACIKLAMASI", "URUNDETAY"]
    for f in empty_fields:
        logger.info(f"    {f} = '' (boş)")

    logger.info("")
    logger.info(f"  Canlıya yazmak için:")
    logger.info(f"  python3 arcelik_panel_insert_apply.py --watt-cost {watt_cost} --stok {stok} --apply")

    # Write simulation JSON
    sim_data = {
        "timestamp": datetime.now().isoformat(),
        "mode": "SIMULATION",
        "watt_cost": watt_cost,
        "stok": stok,
        "insert_count": len(records),
        "arcelik_before": ctx["arcelik_count_before"],
        "arcelik_expected": ctx["arcelik_count_expected"],
        "columns_covered": len(sample),
        "images_missing": True,
        "empty_seo_fields": empty_fields,
        "products": [
            {
                "sku": rec["panel"]["sku"],
                "stokkodu": rec["urunler"]["STOKKODU"],
                "urunadi": rec["urunler"]["URUNADI"],
                "fiyat1": rec["urunler"]["FIYAT1"],
                "alisfiyati": rec["urunler"]["ALISFIYATI"],
                "stok": rec["urunler"]["STOK"],
                "olcubirimi": rec["urunler"]["OLCUBIRIMI"],
                "weight_kg": rec["panel"]["weight_kg"],
                "categories": [
                    {"cat_id": cb["KATEGORIID"], "vitrin": cb["VITRIN"], "sefurl": cb["SEFURL"]}
                    for cb in rec["cat_bindings"]
                ],
            }
            for rec in records
        ],
        "guards_passed": True,
        "preflight_errors": ctx["errors"],
        "preflight_warnings": ctx["warnings"],
        "missing_safe_columns": ctx["missing_safe_columns"],
    }
    sim_path = LOG_DIR / f"arcelik_panel_simulation_{ts}.json"
    with open(sim_path, "w", encoding="utf-8") as f_out:
        json.dump(sim_data, f_out, ensure_ascii=False, indent=2, default=str)
    logger.info(f"  Simulation JSON: {sim_path}")


# ---------------------------------------------------------------------------
# 6. Execute INSERT (transaction)
# ---------------------------------------------------------------------------
def execute_insert(conn, records: list, ctx: dict) -> dict:
    """INSERT all 12 products in a single transaction.

    Flow per product: INSERT URUNLER → SCOPE_IDENTITY() → INSERT URUNKATEGORILERI ×3
    All 12 in one transaction. Verify before COMMIT. ROLLBACK on any failure.
    """
    cursor = conn.cursor(as_dict=True)
    result = {
        "inserted": [],
        "urunler_count": 0,
        "urunkategorileri_count": 0,
        "committed": False,
        "errors": [],
    }

    try:
        for i, rec in enumerate(records, 1):
            v = rec["urunler"]
            panel = rec["panel"]

            # ── INSERT INTO URUNLER (47 columns) ──
            columns = list(v.keys())
            col_names = ", ".join(columns)
            placeholders = ", ".join(["%s"] * len(columns))
            values = tuple(v[c] for c in columns)

            cursor.execute(
                f"INSERT INTO URUNLER ({col_names}) VALUES ({placeholders})",
                values,
            )
            logger.debug(f"  [{i}/12] INSERT URUNLER: {panel['sku']}")

            # ── SCOPE_IDENTITY() ──
            cursor.execute("SELECT SCOPE_IDENTITY() AS new_id")
            id_row = cursor.fetchone()
            new_id = id_row["new_id"]

            if new_id is None:
                raise RuntimeError(
                    f"SCOPE_IDENTITY() returned None for {panel['sku']}. "
                    f"URUNLER.ID may not be an identity column."
                )

            new_id = int(new_id)
            logger.debug(f"    → ID = {new_id}")
            result["urunler_count"] += 1

            # ── INSERT INTO URUNKATEGORILERI ×3 ──
            for cb in rec["cat_bindings"]:
                cursor.execute("""
                    INSERT INTO URUNKATEGORILERI
                        (URUNID, KATEGORIID, VITRIN, SEFURL, VITRINVARYANTID)
                    VALUES (%s, %s, %s, %s, %s)
                """, (
                    new_id,
                    cb["KATEGORIID"],
                    cb["VITRIN"],
                    cb["SEFURL"],
                    cb["VITRINVARYANTID"],
                ))
                result["urunkategorileri_count"] += 1
                logger.debug(
                    f"    → URUNKATEGORILERI: KATID={cb['KATEGORIID']} "
                    f"VITRIN={cb['VITRIN']}"
                )

            result["inserted"].append({
                "sku": panel["sku"],
                "product_id": new_id,
                "stokkodu": v["STOKKODU"],
                "urunadi": v["URUNADI"],
                "fiyat1": v["FIYAT1"],
                "stok": v["STOK"],
                "olcubirimi": v["OLCUBIRIMI"],
                "weight_kg": panel["weight_kg"],
                "categories": [
                    {
                        "cat_id": cb["KATEGORIID"],
                        "vitrin": cb["VITRIN"],
                        "sefurl": cb["SEFURL"],
                    }
                    for cb in rec["cat_bindings"]
                ],
                "images_missing": True,
            })

        # ── VERIFY before COMMIT ──
        logger.info("")
        logger.info("-" * 70)
        logger.info("VERIFY (before COMMIT)")
        logger.info("-" * 70)
        verify = run_verify(cursor, result, ctx)
        result["verify"] = verify

        if verify["all_pass"]:
            conn.commit()
            result["committed"] = True
            logger.info("  >>> COMMITTED <<<")
        else:
            conn.rollback()
            result["committed"] = False
            result["errors"].append("Verification failed — ROLLBACK")
            logger.error("  >>> ROLLBACK — verification failed <<<")

    except Exception as e:
        conn.rollback()
        result["committed"] = False
        result["errors"].append(str(e))
        logger.error(f"  >>> ROLLBACK — error: {e} <<<")
        raise

    finally:
        cursor.close()

    return result


def run_verify(cursor, result: dict, ctx: dict) -> dict:
    """7-point verification before COMMIT."""
    verify = {"checks": [], "all_pass": True}
    inserted_ids = [r["product_id"] for r in result["inserted"]]

    if not inserted_ids:
        verify["all_pass"] = False
        verify["checks"].append({"name": "no_inserted_ids", "pass": False})
        return verify

    ph = ",".join(["%s"] * len(inserted_ids))
    params = tuple(inserted_ids)

    # 1. 12 products in URUNLER
    cursor.execute(
        f"SELECT COUNT(*) AS cnt FROM URUNLER WHERE ID IN ({ph})", params,
    )
    cnt = cursor.fetchone()["cnt"]
    ok = cnt == EXPECTED_INSERT_COUNT
    verify["checks"].append({"name": "urunler_count", "expected": EXPECTED_INSERT_COUNT, "actual": cnt, "pass": ok})
    logger.info(f"  [{'OK' if ok else 'FAIL'}] URUNLER count: {cnt}/{EXPECTED_INSERT_COUNT}")
    if not ok:
        verify["all_pass"] = False

    # 2. 36 category records (3 × 12)
    cursor.execute(
        f"SELECT COUNT(*) AS cnt FROM URUNKATEGORILERI WHERE URUNID IN ({ph})", params,
    )
    cat_cnt = cursor.fetchone()["cnt"]
    expected_cat = EXPECTED_INSERT_COUNT * len(CATEGORY_BINDINGS)
    ok = cat_cnt == expected_cat
    verify["checks"].append({"name": "urunkategorileri_count", "expected": expected_cat, "actual": cat_cnt, "pass": ok})
    logger.info(f"  [{'OK' if ok else 'FAIL'}] URUNKATEGORILERI count: {cat_cnt}/{expected_cat}")
    if not ok:
        verify["all_pass"] = False

    # 3-5. VITRIN correctness per category
    for cat_id, expected_vitrin in CATEGORY_BINDINGS:
        cursor.execute(
            f"SELECT COUNT(*) AS cnt FROM URUNKATEGORILERI "
            f"WHERE URUNID IN ({ph}) AND KATEGORIID = %s AND VITRIN = %s",
            params + (cat_id, expected_vitrin),
        )
        v_cnt = cursor.fetchone()["cnt"]
        ok = v_cnt == EXPECTED_INSERT_COUNT
        name = f"cat_{cat_id}_vitrin_{expected_vitrin}"
        verify["checks"].append({"name": name, "expected": EXPECTED_INSERT_COUNT, "actual": v_cnt, "pass": ok})
        logger.info(f"  [{'OK' if ok else 'FAIL'}] Cat {cat_id} VITRIN={expected_vitrin}: {v_cnt}/{EXPECTED_INSERT_COUNT}")
        if not ok:
            verify["all_pass"] = False

    # 6. SEFURL uniqueness among inserted
    cursor.execute(
        f"SELECT SEFURL, COUNT(*) AS cnt FROM URUNKATEGORILERI "
        f"WHERE URUNID IN ({ph}) GROUP BY SEFURL HAVING COUNT(*) > 1",
        params,
    )
    dup_sefurls = cursor.fetchall()
    ok = len(dup_sefurls) == 0
    verify["checks"].append({"name": "sefurl_unique", "duplicates": len(dup_sefurls), "pass": ok})
    logger.info(f"  [{'OK' if ok else 'FAIL'}] SEFURL uniqueness: {len(dup_sefurls)} duplicate(s)")
    if not ok:
        verify["all_pass"] = False
        for d in dup_sefurls:
            logger.error(f"    duplicate: '{d['SEFURL']}' × {d['cnt']}")

    # 7. Arçelik total count
    cursor.execute(
        "SELECT COUNT(*) AS cnt FROM URUNLER WHERE MARKAID = %s",
        (ARCELIK_MARKA_ID,),
    )
    total = cursor.fetchone()["cnt"]
    ok = total == ctx["arcelik_count_expected"]
    verify["checks"].append({
        "name": "arcelik_total",
        "expected": ctx["arcelik_count_expected"],
        "actual": total,
        "pass": ok,
    })
    logger.info(f"  [{'OK' if ok else 'FAIL'}] Arçelik total: {total}/{ctx['arcelik_count_expected']}")
    if not ok:
        verify["all_pass"] = False

    return verify


# ---------------------------------------------------------------------------
# 7. Output
# ---------------------------------------------------------------------------
def write_result_json(result: dict) -> Path:
    path = LOG_DIR / f"arcelik_panel_inserted_{ts}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    logger.info(f"  Result JSON: {path}")
    return path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Arçelik 12 Solar Panel — Faz B: INSERT Apply"
    )
    parser.add_argument(
        "--watt-cost", type=float, required=True,
        help="Watt cost in USD (e.g. 0.23)",
    )
    parser.add_argument(
        "--stok", type=int, default=DEFAULT_STOK,
        help=f"STOK value (default: {DEFAULT_STOK} — 10/11 active Arçelik pattern)",
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Actually INSERT into DB (default: simulation only)",
    )
    args = parser.parse_args()

    mode = "APPLY" if args.apply else "SIMULATION"

    logger.info(f"=== Arçelik Panel INSERT — {mode} — "
                f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")
    logger.info(f"  Target: {EXPECTED_INSERT_COUNT} panels")
    logger.info(f"  Watt cost: ${args.watt_cost}")
    logger.info(f"  STOK: {args.stok}")
    logger.info(f"  Mode: {mode}")
    logger.info(f"  Log: {apply_log_path}")
    logger.info("")

    conn = get_db_connection()

    try:
        # 1. Pre-flight
        ctx = preflight(conn)

        if ctx["errors"] and "template" not in ctx:
            logger.error("Pre-flight critical failure. Exiting.")
            sys.exit(1)

        # 2. Apply guards
        if not apply_guards(ctx, args.watt_cost):
            sys.exit(1)

        # 3. Pre-insert snapshot
        logger.info("")
        logger.info("=" * 70)
        logger.info("3. PRE-INSERT SNAPSHOT")
        logger.info("=" * 70)
        take_preinsert_snapshot(conn)

        # 4. Build insert records
        records = build_insert_records(args.watt_cost, args.stok, ctx)

        if not args.apply:
            # ── SIMULATION ──
            display_simulation(records, ctx, args.watt_cost, args.stok)
        else:
            # ── APPLY ──
            logger.info("")
            logger.info("=" * 70)
            logger.info("4. EXECUTING INSERT")
            logger.info("=" * 70)
            logger.info(f"  Inserting {len(records)} products (47 cols URUNLER + 3×5 cols URUNKATEGORILERI)...")

            result = execute_insert(conn, records, ctx)

            # Summary
            logger.info("")
            logger.info("=" * 70)
            logger.info("5. SUMMARY")
            logger.info("=" * 70)
            logger.info(f"  URUNLER inserted: {result['urunler_count']}")
            logger.info(f"  URUNKATEGORILERI inserted: {result['urunkategorileri_count']}")
            logger.info(f"  Committed: {result['committed']}")
            logger.info(f"  Görseller: YOK — 12 ürün images_missing=1")

            if result["committed"]:
                logger.info("")
                logger.info("  Inserted products:")
                for r in result["inserted"]:
                    logger.info(
                        f"    ID={r['product_id']:5d}  "
                        f"{r['stokkodu']:<45s}  "
                        f"${r['fiyat1']:>10,.2f}  "
                        f"STOK={r['stok']}  "
                        f"{r['olcubirimi']}"
                    )

            if result["errors"]:
                logger.error("")
                logger.error("  ERRORS:")
                for err in result["errors"]:
                    logger.error(f"    {err}")

            # Write JSON
            write_result_json(result)

    finally:
        conn.close()
        logger.info("DB connection closed.")

    logger.info(f"Done. Log: {apply_log_path}")


if __name__ == "__main__":
    main()
