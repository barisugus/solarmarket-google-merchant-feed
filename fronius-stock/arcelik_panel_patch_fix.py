#!/usr/bin/env python3
"""
Arçelik 12 Panel — Faz C: 500 Fix / Minimal Safe Patch

Root cause: ASP.NET view crashes (HTTP 500) when URUNRESIMLERI has 0 records.
All 206 working products have ≥1 image record. Our 12 new panels have 0.

This script:
  1. UPDATEs PAGETITLE, METADESCRIPTION, METAKEYWORDS, ETIKETLER for 12 products
  2. INSERTs 1 URUNRESIMLERI record per product (placeholder image)
  3. Verifies the patch

Usage:
  python3 arcelik_panel_patch_fix.py --simulate      # show plan, no DB writes
  python3 arcelik_panel_patch_fix.py --apply          # execute patch in transaction
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

import pymssql
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).parent
LOG_DIR = SCRIPT_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

PATCH_IDS = list(range(1600, 1612))  # 1600–1611
EXPECTED_PATCH_COUNT = 12
ARCELIK_MARKA_ID = 68

# Product dataset (matches Faz B insert)
PRODUCTS = [
    {"id": 1600, "sku": "ARCLK-144PV10T-GG-590",  "pmax": 590, "pallet_qty": 29, "panel_type": "Cam-Cam Bifacial"},
    {"id": 1601, "sku": "ARCLK-144PV10T-GG-595",  "pmax": 595, "pallet_qty": 29, "panel_type": "Cam-Cam Bifacial"},
    {"id": 1602, "sku": "ARCLK-144PV10T-GG-600",  "pmax": 600, "pallet_qty": 29, "panel_type": "Cam-Cam Bifacial"},
    {"id": 1603, "sku": "ARCLK-144PV10RT-GG-600", "pmax": 600, "pallet_qty": 29, "panel_type": "Cam-Cam Bifacial"},
    {"id": 1604, "sku": "ARCLK-144PV10RT-GG-605", "pmax": 605, "pallet_qty": 29, "panel_type": "Cam-Cam Bifacial"},
    {"id": 1605, "sku": "ARCLK-144PV10RT-GG-610", "pmax": 610, "pallet_qty": 29, "panel_type": "Cam-Cam Bifacial"},
    {"id": 1606, "sku": "ARCLK-144PV10RT-GG-615", "pmax": 615, "pallet_qty": 29, "panel_type": "Cam-Cam Bifacial"},
    {"id": 1607, "sku": "ARCLK-144PV10RT-600",    "pmax": 600, "pallet_qty": 37, "panel_type": "Cam-Cam"},
    {"id": 1608, "sku": "ARCLK-132PVRT-GG-610",   "pmax": 610, "pallet_qty": 29, "panel_type": "Cam-Cam Bifacial"},
    {"id": 1609, "sku": "ARCLK-132PVRT-GG-615",   "pmax": 615, "pallet_qty": 29, "panel_type": "Cam-Cam Bifacial"},
    {"id": 1610, "sku": "ARCLK-132PVRT-GG-620",   "pmax": 620, "pallet_qty": 29, "panel_type": "Cam-Cam Bifacial"},
    {"id": 1611, "sku": "ARCLK-132PVRT-GG-625",   "pmax": 625, "pallet_qty": 29, "panel_type": "Cam-Cam Bifacial"},
]

# Field limits (from INFORMATION_SCHEMA)
FIELD_LIMITS = {
    "PAGETITLE": 255,
    "METADESCRIPTION": 255,
    "METAKEYWORDS": 255,
    "ETIKETLER": 1000,
}

# URUNRESIMLERI columns (non-identity): URUNID, RESIM, VARSAYILAN, ALTTAG, VARYANTALANID
IMAGE_RESIM_PLACEHOLDER = "arcelik-solar-panel-placeholder.jpg"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_path = LOG_DIR / f"arcelik_panel_patch_{timestamp}.log"

logger = logging.getLogger("patch_fix")
logger.setLevel(logging.DEBUG)

fh = logging.FileHandler(log_path, encoding="utf-8")
fh.setLevel(logging.DEBUG)
fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(fh)

ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
ch.setFormatter(logging.Formatter("%(message)s"))
logger.addHandler(ch)


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
    conn = pymssql.connect(
        server=server, port=port, user=user,
        password=password, database=database, charset="utf8",
    )
    return conn


# ---------------------------------------------------------------------------
# Field generators
# ---------------------------------------------------------------------------
def gen_pagetitle(p):
    val = f"Arçelik {p['sku']} {p['pmax']}W Güneş Paneli Fiyatları ve Özellikleri"
    return val[:FIELD_LIMITS["PAGETITLE"]]


def gen_metadescription(p):
    val = (
        f"Arçelik {p['sku']} {p['pmax']}W güneş paneli, palet bazlı satış, "
        f"{p['pallet_qty']} adet panel içeren palet yapısı, teknik özellikler "
        f"ve fiyat bilgisi Türkiye Solar Market'te."
    )
    return val[:FIELD_LIMITS["METADESCRIPTION"]]


def gen_metakeywords(p):
    base = f"Arçelik {p['sku']}, {p['pmax']}W güneş paneli, Arçelik solar panel"
    if "Bifacial" in p["panel_type"]:
        base += ", bifacial güneş paneli"
    base += ", palet güneş paneli"
    return base[:FIELD_LIMITS["METAKEYWORDS"]]


def gen_etiketler(p):
    tags = ["arcelik", "solar panel", f"{p['pmax']}w", "palet", "gunes paneli"]
    if "Bifacial" in p["panel_type"]:
        tags.insert(3, "bifacial")
    val = "; ".join(tags)
    return val[:FIELD_LIMITS["ETIKETLER"]]


def gen_alttag(p):
    """Alt tag for image record, max 255 chars."""
    urunadi = f"Arçelik {p['sku']} – {p['pmax']}W {p['panel_type']} Güneş Paneli"
    val = f"{urunadi} – Türkiye Solar Market"
    return val[:255]


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------
def preflight(conn):
    """Verify all 12 products exist, belong to Arçelik, and need patching."""
    cur = conn.cursor(as_dict=True)
    errors = []

    # 1. All 12 IDs exist and are MARKAID=68
    placeholders = ",".join(["%s"] * len(PATCH_IDS))
    cur.execute(
        f"SELECT ID, STOKKODU, MARKAID FROM URUNLER WHERE ID IN ({placeholders})",
        tuple(PATCH_IDS),
    )
    found = cur.fetchall()
    if len(found) != EXPECTED_PATCH_COUNT:
        missing = set(PATCH_IDS) - {r["ID"] for r in found}
        errors.append(f"Missing product IDs: {missing}")

    wrong_brand = [r for r in found if r["MARKAID"] != ARCELIK_MARKA_ID]
    if wrong_brand:
        errors.append(f"Non-Arçelik products: {[r['ID'] for r in wrong_brand]}")

    # 2. Check current image counts
    cur.execute(
        f"SELECT URUNID, COUNT(*) as cnt FROM URUNRESIMLERI WHERE URUNID IN ({placeholders}) GROUP BY URUNID",
        tuple(PATCH_IDS),
    )
    existing_images = {r["URUNID"]: r["cnt"] for r in cur.fetchall()}
    products_with_images = sum(1 for pid in PATCH_IDS if existing_images.get(pid, 0) > 0)

    # 3. Check current meta field states (for overwrite guard)
    cur.execute(
        f"""SELECT ID, PAGETITLE, METADESCRIPTION, METAKEYWORDS, ETIKETLER, PIYASAFIYATI,
                DATALENGTH(PAGETITLE) as pt_len,
                DATALENGTH(METADESCRIPTION) as md_len,
                DATALENGTH(METAKEYWORDS) as mk_len,
                DATALENGTH(ETIKETLER) as et_len
            FROM URUNLER WHERE ID IN ({placeholders})""",
        tuple(PATCH_IDS),
    )
    pt_rows = cur.fetchall()
    pt_empty = sum(1 for r in pt_rows if not r["PAGETITLE"] or r["pt_len"] == 0)
    # Per-product field state for overwrite guard
    field_state = {}
    for r in pt_rows:
        field_state[r["ID"]] = {
            "pt_empty": not r["PAGETITLE"] or (r["pt_len"] or 0) == 0,
            "md_empty": not r["METADESCRIPTION"] or (r["md_len"] or 0) == 0,
            "mk_empty": not r["METAKEYWORDS"] or (r["mk_len"] or 0) == 0,
            "et_empty": not r["ETIKETLER"] or (r["et_len"] or 0) == 0,
            "pf_null": r["PIYASAFIYATI"] is None,
        }

    # 4. Runtime verify URUNRESIMLERI schema
    cur.execute("""
        SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, IS_NULLABLE
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = 'URUNRESIMLERI'
        ORDER BY ORDINAL_POSITION
    """)
    img_schema = cur.fetchall()
    img_cols = {r["COLUMN_NAME"] for r in img_schema}
    required_cols = {"URUNID", "RESIM", "VARSAYILAN", "ALTTAG", "VARYANTALANID"}
    missing_cols = required_cols - img_cols
    if missing_cols:
        errors.append(f"URUNRESIMLERI missing expected columns: {missing_cols}")

    # 5. Get reference image record
    cur.execute("""
        SELECT TOP 1 r.URUNID, r.RESIM, r.VARSAYILAN, r.ALTTAG, r.VARYANTALANID
        FROM URUNRESIMLERI r
        JOIN URUNLER u ON u.ID = r.URUNID
        WHERE u.MARKAID = 68 AND r.VARSAYILAN = 1
        ORDER BY r.ID DESC
    """)
    ref_image = cur.fetchone()

    cur.close()

    return {
        "errors": errors,
        "products_found": len(found),
        "products_with_images": products_with_images,
        "products_needing_images": EXPECTED_PATCH_COUNT - products_with_images,
        "pagetitle_empty": pt_empty,
        "img_schema": img_schema,
        "ref_image": ref_image,
        "existing_images": existing_images,
        "field_state": field_state,
    }


# ---------------------------------------------------------------------------
# Simulate
# ---------------------------------------------------------------------------
def simulate(conn):
    """Show what the patch would do without writing anything."""
    logger.info("=" * 60)
    logger.info(f"FAZ C — SIMULATION — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    # Preflight
    logger.info("\n--- PREFLIGHT ---")
    pf = preflight(conn)
    if pf["errors"]:
        for e in pf["errors"]:
            logger.error(f"  PREFLIGHT ERROR: {e}")
        logger.error("ABORT: Preflight failed")
        sys.exit(1)

    logger.info(f"  Products found: {pf['products_found']}/{EXPECTED_PATCH_COUNT}")
    logger.info(f"  Products needing images: {pf['products_needing_images']}")
    logger.info(f"  PAGETITLE empty: {pf['pagetitle_empty']}")

    # Schema
    logger.info("\n--- URUNRESIMLERI SCHEMA ---")
    for col in pf["img_schema"]:
        logger.info(
            f"  {col['COLUMN_NAME']:20s} {col['DATA_TYPE']:10s} "
            f"max={str(col['CHARACTER_MAXIMUM_LENGTH'] or ''):>5s} "
            f"null={col['IS_NULLABLE']}"
        )

    # Reference image
    logger.info("\n--- REFERENCE IMAGE RECORD ---")
    ref = pf["ref_image"]
    if ref:
        for k, v in ref.items():
            logger.info(f"  {k}: {v}")
    else:
        logger.warning("  No reference image found!")

    # Image strategy
    logger.info("\n--- IMAGE STRATEGY ---")
    logger.info("  STRATEJI-1: Placeholder image record")
    logger.info(f"    RESIM = '{IMAGE_RESIM_PLACEHOLDER}'")
    logger.info(f"    VARSAYILAN = 1 (primary)")
    logger.info(f"    ALTTAG = '<Ürün Adı> – Türkiye Solar Market'")
    logger.info(f"    VARYANTALANID = NULL")
    logger.info("  Neden: ASP.NET view .First() çağrısı için en az 1 kayıt gerekli.")
    logger.info("  Görsel dosya sunucuda yoksa broken image gösterir ama sayfa 200 döner.")

    # Patch plan per product
    logger.info("\n--- PATCH PLAN (12 ürün) ---")
    sim_data = []
    for p in PRODUCTS:
        has_image = pf["existing_images"].get(p["id"], 0) > 0
        entry = {
            "id": p["id"],
            "sku": p["sku"],
            "pmax": p["pmax"],
            "pagetitle": gen_pagetitle(p),
            "metadescription": gen_metadescription(p),
            "metakeywords": gen_metakeywords(p),
            "etiketler": gen_etiketler(p),
            "alttag": gen_alttag(p),
            "image_action": "SKIP (already has image)" if has_image else "INSERT placeholder",
            "update_action": "UPDATE 4 fields",
        }
        sim_data.append(entry)

        logger.info(f"\n  [{p['id']}] {p['sku']}")
        logger.info(f"    PAGETITLE:       {entry['pagetitle']}")
        logger.info(f"    METADESCRIPTION: {entry['metadescription'][:80]}...")
        logger.info(f"    METAKEYWORDS:    {entry['metakeywords'][:80]}...")
        logger.info(f"    ETIKETLER:       {entry['etiketler']}")
        logger.info(f"    ALTTAG:          {entry['alttag'][:80]}...")
        logger.info(f"    IMAGE:           {entry['image_action']}")

    # Truncation warnings
    logger.info("\n--- TRUNCATION CHECK ---")
    truncated = False
    for p in PRODUCTS:
        pt = gen_pagetitle(p)
        md = gen_metadescription(p)
        mk = gen_metakeywords(p)
        et = gen_etiketler(p)
        raw_pt = f"Arçelik {p['sku']} {p['pmax']}W Güneş Paneli Fiyatları ve Özellikleri"
        raw_md = (
            f"Arçelik {p['sku']} {p['pmax']}W güneş paneli, palet bazlı satış, "
            f"{p['pallet_qty']} adet panel içeren palet yapısı, teknik özellikler "
            f"ve fiyat bilgisi Türkiye Solar Market'te."
        )
        if len(raw_pt) > FIELD_LIMITS["PAGETITLE"]:
            logger.warning(f"  {p['sku']}: PAGETITLE truncated {len(raw_pt)} → {FIELD_LIMITS['PAGETITLE']}")
            truncated = True
        if len(raw_md) > FIELD_LIMITS["METADESCRIPTION"]:
            logger.warning(f"  {p['sku']}: METADESCRIPTION truncated {len(raw_md)} → {FIELD_LIMITS['METADESCRIPTION']}")
            truncated = True
    if not truncated:
        logger.info("  No truncation needed — all values within limits")

    # Guards summary
    logger.info("\n--- APPLY GUARDS ---")
    guards = {
        "products_found == 12": pf["products_found"] == EXPECTED_PATCH_COUNT,
        "all MARKAID == 68": len(pf["errors"]) == 0,
        "preflight_clean": len(pf["errors"]) == 0,
        "img_schema_valid": len(pf["errors"]) == 0,
        "products_needing_images > 0": pf["products_needing_images"] > 0,
    }
    all_pass = True
    for guard, passed in guards.items():
        status = "PASS" if passed else "FAIL"
        if not passed:
            all_pass = False
        logger.info(f"  {guard:40s}: {status}")

    logger.info(f"\n  ALL GUARDS: {'PASS' if all_pass else 'FAIL'}")

    # Save simulation JSON
    sim_output = {
        "timestamp": datetime.now().isoformat(),
        "mode": "SIMULATION",
        "preflight": {
            "products_found": pf["products_found"],
            "products_needing_images": pf["products_needing_images"],
            "pagetitle_empty": pf["pagetitle_empty"],
        },
        "guards_passed": all_pass,
        "image_strategy": "STRATEJI-1: placeholder record per product",
        "products": sim_data,
    }
    sim_path = LOG_DIR / f"arcelik_panel_patch_sim_{timestamp}.json"
    with open(sim_path, "w", encoding="utf-8") as f:
        json.dump(sim_output, f, ensure_ascii=False, indent=2)
    logger.info(f"\n  Simulation JSON: {sim_path}")

    if not all_pass:
        logger.error("\nABORT: Guards failed. Fix issues before --apply.")
        sys.exit(1)

    logger.info("\n" + "=" * 60)
    logger.info("SIMULATION COMPLETE — run with --apply to execute patch")
    logger.info("=" * 60)

    return sim_output


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------
def apply_patch(conn):
    """Execute the patch in a single transaction."""
    logger.info("=" * 60)
    logger.info(f"FAZ C — APPLY — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    # Preflight
    pf = preflight(conn)
    if pf["errors"]:
        for e in pf["errors"]:
            logger.error(f"  PREFLIGHT ERROR: {e}")
        sys.exit(1)

    if pf["products_found"] != EXPECTED_PATCH_COUNT:
        logger.error(f"ABORT: Found {pf['products_found']} products, expected {EXPECTED_PATCH_COUNT}")
        sys.exit(1)

    logger.info(f"  Preflight OK: {pf['products_found']}/{EXPECTED_PATCH_COUNT} products")
    logger.info(f"  Images to insert: {pf['products_needing_images']}")

    # --- PRE-APPLY SNAPSHOT ---
    snapshot = {
        "timestamp": datetime.now().isoformat(),
        "products_needing_images": pf["products_needing_images"],
        "field_state": {str(k): v for k, v in pf["field_state"].items()},
        "existing_images": {str(k): v for k, v in pf["existing_images"].items()},
    }
    snap_path = LOG_DIR / f"arcelik_panel_patch_snapshot_{timestamp}.json"
    with open(snap_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)
    logger.info(f"  Pre-apply snapshot: {snap_path}")

    cur = conn.cursor(as_dict=True)
    update_count = 0
    field_updates = {"PAGETITLE": 0, "METADESCRIPTION": 0, "METAKEYWORDS": 0, "ETIKETLER": 0}
    image_insert_count = 0

    try:
        # --- A) UPDATE meta fields + PIYASAFIYATI (overwrite-guard: only fill empty/NULL) ---
        logger.info("\n--- UPDATING META FIELDS + PIYASAFIYATI (overwrite-guard: skip non-empty) ---")
        for p in PRODUCTS:
            fs = pf["field_state"].get(p["id"], {})
            set_clauses = []
            params = []

            if fs.get("pt_empty", True):
                set_clauses.append("PAGETITLE = %s")
                params.append(gen_pagetitle(p))
                field_updates["PAGETITLE"] += 1
            if fs.get("md_empty", True):
                set_clauses.append("METADESCRIPTION = %s")
                params.append(gen_metadescription(p))
                field_updates["METADESCRIPTION"] += 1
            if fs.get("mk_empty", True):
                set_clauses.append("METAKEYWORDS = %s")
                params.append(gen_metakeywords(p))
                field_updates["METAKEYWORDS"] += 1
            if fs.get("et_empty", True):
                set_clauses.append("ETIKETLER = %s")
                params.append(gen_etiketler(p))
                field_updates["ETIKETLER"] += 1
            # PIYASAFIYATI NULL causes ASP.NET 500 — set to 0 if NULL
            if fs.get("pf_null", True):
                set_clauses.append("PIYASAFIYATI = %s")
                params.append(0)
                field_updates.setdefault("PIYASAFIYATI", 0)
                field_updates["PIYASAFIYATI"] += 1

            if not set_clauses:
                logger.info(f"  SKIP UPDATE: ID={p['id']} all fields already filled")
                continue

            params.extend([p["id"], ARCELIK_MARKA_ID])
            sql = f"UPDATE URUNLER SET {', '.join(set_clauses)} WHERE ID = %s AND MARKAID = %s"
            cur.execute(sql, tuple(params))
            if cur.rowcount == 1:
                update_count += 1
                logger.debug(f"  UPDATE OK: ID={p['id']} {p['sku']} ({len(set_clauses)} fields)")
            else:
                conn.rollback()
                logger.error(f"  ROLLBACK: UPDATE ID={p['id']} affected {cur.rowcount} rows (expected 1)")
                sys.exit(1)

        logger.info(f"  URUNLER updated: {update_count} products")
        for col, cnt in field_updates.items():
            logger.info(f"    {col}: {cnt} fields written")

        # --- B) INSERT image records ---
        logger.info("\n--- INSERTING IMAGE RECORDS ---")
        for p in PRODUCTS:
            existing_count = pf["existing_images"].get(p["id"], 0)
            if existing_count > 0:
                logger.info(f"  SKIP: ID={p['id']} already has {existing_count} image(s)")
                continue

            alttag = gen_alttag(p)
            cur.execute(
                """INSERT INTO URUNRESIMLERI (URUNID, RESIM, VARSAYILAN, ALTTAG, VARYANTALANID)
                   VALUES (%s, %s, %s, %s, %s)""",
                (p["id"], IMAGE_RESIM_PLACEHOLDER, 1, alttag, None),
            )
            if cur.rowcount == 1:
                image_insert_count += 1
                logger.debug(f"  INSERT OK: URUNID={p['id']} {p['sku']}")
            else:
                conn.rollback()
                logger.error(f"  ROLLBACK: INSERT image for ID={p['id']} affected {cur.rowcount} rows")
                sys.exit(1)

        logger.info(f"  URUNRESIMLERI inserted: {image_insert_count}/{pf['products_needing_images']}")

        # Guard: image inserts must match needed count
        if image_insert_count != pf["products_needing_images"]:
            conn.rollback()
            logger.error(
                f"  ROLLBACK: Inserted {image_insert_count} images, "
                f"expected {pf['products_needing_images']}"
            )
            sys.exit(1)

        # --- VERIFY before commit ---
        logger.info("\n--- VERIFY (pre-commit) ---")
        verify_ok = True
        placeholders = ",".join(["%s"] * len(PATCH_IDS))

        # V1: All 12 have non-empty PAGETITLE
        cur.execute(
            f"""SELECT COUNT(*) as cnt FROM URUNLER
                WHERE ID IN ({placeholders})
                AND PAGETITLE IS NOT NULL AND DATALENGTH(PAGETITLE) > 0""",
            tuple(PATCH_IDS),
        )
        pt_count = cur.fetchone()["cnt"]
        v1 = pt_count == EXPECTED_PATCH_COUNT
        logger.info(f"  V1 PAGETITLE filled: {pt_count}/{EXPECTED_PATCH_COUNT} {'OK' if v1 else 'FAIL'}")
        if not v1:
            verify_ok = False

        # V2: All 12 have ≥1 image
        cur.execute(
            f"""SELECT COUNT(DISTINCT r.URUNID) as cnt
                FROM URUNRESIMLERI r
                WHERE r.URUNID IN ({placeholders})""",
            tuple(PATCH_IDS),
        )
        img_count = cur.fetchone()["cnt"]
        v2 = img_count == EXPECTED_PATCH_COUNT
        logger.info(f"  V2 Image records: {img_count}/{EXPECTED_PATCH_COUNT} {'OK' if v2 else 'FAIL'}")
        if not v2:
            verify_ok = False

        # V3: All 12 have non-empty METADESCRIPTION
        cur.execute(
            f"""SELECT COUNT(*) as cnt FROM URUNLER
                WHERE ID IN ({placeholders})
                AND METADESCRIPTION IS NOT NULL AND DATALENGTH(METADESCRIPTION) > 0""",
            tuple(PATCH_IDS),
        )
        md_count = cur.fetchone()["cnt"]
        v3 = md_count == EXPECTED_PATCH_COUNT
        logger.info(f"  V3 METADESCRIPTION filled: {md_count}/{EXPECTED_PATCH_COUNT} {'OK' if v3 else 'FAIL'}")
        if not v3:
            verify_ok = False

        # V4: All 12 have non-empty ETIKETLER
        cur.execute(
            f"""SELECT COUNT(*) as cnt FROM URUNLER
                WHERE ID IN ({placeholders})
                AND ETIKETLER IS NOT NULL AND DATALENGTH(ETIKETLER) > 0""",
            tuple(PATCH_IDS),
        )
        et_count = cur.fetchone()["cnt"]
        v4 = et_count == EXPECTED_PATCH_COUNT
        logger.info(f"  V4 ETIKETLER filled: {et_count}/{EXPECTED_PATCH_COUNT} {'OK' if v4 else 'FAIL'}")
        if not v4:
            verify_ok = False

        if not verify_ok:
            conn.rollback()
            logger.error("  ROLLBACK: Verify failed")
            sys.exit(1)

        logger.info("  ALL VERIFY: PASS")

        # --- COMMIT ---
        conn.commit()
        logger.info("\n  COMMITTED")

    except Exception as e:
        conn.rollback()
        logger.error(f"  ROLLBACK — error: {e}")
        raise

    cur.close()

    # Save result JSON
    result = {
        "timestamp": datetime.now().isoformat(),
        "mode": "APPLY",
        "urunler_updated": update_count,
        "field_updates": field_updates,
        "images_inserted": image_insert_count,
        "verify": {
            "pagetitle_filled": pt_count,
            "image_records": img_count,
            "metadescription_filled": md_count,
            "etiketler_filled": et_count,
        },
        "committed": True,
        "snapshot_path": str(snap_path),
    }
    result_path = LOG_DIR / f"arcelik_panel_patch_result_{timestamp}.json"
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    logger.info(f"\n  Result JSON: {result_path}")

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("PATCH SUMMARY")
    logger.info("=" * 60)
    logger.info(f"  URUNLER UPDATEd:       {update_count} products")
    for col, cnt in field_updates.items():
        logger.info(f"    {col:20s}: {cnt}")
    logger.info(f"  URUNRESIMLERI INSERTed: {image_insert_count}")
    logger.info(f"  Verify:                 4/4 PASS")
    logger.info(f"  Status:                 COMMITTED")
    logger.info("=" * 60)

    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Arçelik Panel Faz C — 500 Fix Patch")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--simulate", action="store_true", help="Show plan, no DB writes")
    group.add_argument("--apply", action="store_true", help="Execute patch in transaction")
    args = parser.parse_args()

    mode = "APPLY" if args.apply else "SIMULATE"
    logger.info(f"Mode: {mode}")
    logger.info(f"Log: {log_path}")

    conn = get_db_connection()
    logger.info("DB connected")

    try:
        if args.simulate:
            simulate(conn)
        else:
            apply_patch(conn)
    finally:
        conn.close()
        logger.info("DB connection closed.")


if __name__ == "__main__":
    main()
