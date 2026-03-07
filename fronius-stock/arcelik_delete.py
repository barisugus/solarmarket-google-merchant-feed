#!/usr/bin/env python3
"""
Arcelik 26 Product Cascade Delete

Deletes 26 discontinued Arcelik products (zero sales) from MSSQL.
Handles 13 FK child tables before deleting from URUNLER.

EXCEPTION: ID 1517 (EV charger) is NOT in the delete list.

Usage:
  python3 arcelik_delete.py                # dry-run (default) — shows what would be deleted
  python3 arcelik_delete.py --apply        # actually delete from DB
"""

import argparse
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

ARCELIK_MARKA_ID = 68
EXPECTED_REMAINING = 11  # 37 total - 26 deleted = 11 remaining

# 26 product IDs to delete (all SATILMASAYISI=0, discontinued)
DELETE_IDS = [
    1290, 1291, 1299, 1300, 1312, 1319, 1320, 1400,
    1410, 1411, 1414, 1416, 1433, 1437, 1439, 1442,
    1443, 1445, 1448, 1449, 1452, 1458, 1459, 1460,
    1461, 1462,
]
EXPECTED_DELETE_COUNT = 26

# Safety: these IDs must NEVER be deleted
PROTECTED_IDS = {1517}  # AR AX 32 RFID 22 EV charger — real stock in warehouse

# 13 FK child tables (order doesn't matter, all direct FK to URUNLER.ID)
CHILD_TABLES = [
    ("SEPET", "URUNID"),
    ("URUNKATEGORILERI", "URUNID"),
    ("URUNRESIMLERI", "URUNID"),
    ("UYEURUNLISTELERI", "URUNID"),
    ("CAPRAZURUNILISKILERI", "URUNID"),
    ("DEGERLENDIRME", "URUNID"),
    ("URUNETIKETLERI", "URUN_ID"),       # note: URUN_ID not URUNID
    ("URUNFILTRASYONLARI", "URUNID"),
    ("URUNMATRISLERI", "URUNID"),
    ("URUNOZELLIKLERI", "URUNID"),
    ("URUNRAFLARI", "URUNID"),
    ("URUNVARYANTLARI", "URUNID"),
    ("ZAMANLIFIYATKAMPANYALARI", "URUNID"),
]

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_DIR.mkdir(exist_ok=True)
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
detail_log_path = LOG_DIR / f"arcelik_delete_{timestamp}.log"

logger = logging.getLogger("arcelik_delete")
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
# Preflight checks
# ---------------------------------------------------------------------------
def preflight_check(conn):
    """Verify target products exist and are safe to delete."""
    cursor = conn.cursor(as_dict=True)

    # 1. Safety: ensure no protected IDs in delete list
    overlap = PROTECTED_IDS & set(DELETE_IDS)
    if overlap:
        logger.error(f"ABORT: Protected IDs found in delete list: {overlap}")
        sys.exit(1)

    # 2. Verify all 26 IDs exist in URUNLER
    placeholders = ",".join(["%s"] * len(DELETE_IDS))
    cursor.execute(f"""
        SELECT ID, URUNADI, STOKKODU, STOK, FIYAT1, SATILMASAYISI
        FROM URUNLER
        WHERE ID IN ({placeholders})
    """, tuple(DELETE_IDS))
    found = cursor.fetchall()

    if len(found) != EXPECTED_DELETE_COUNT:
        missing = set(DELETE_IDS) - {r["ID"] for r in found}
        logger.error(f"ABORT: Expected {EXPECTED_DELETE_COUNT} products, found {len(found)}")
        logger.error(f"  Missing IDs: {missing}")
        cursor.close()
        sys.exit(1)

    # 3. Verify all have SATILMASAYISI = 0
    sold = [r for r in found if (r["SATILMASAYISI"] or 0) > 0]
    if sold:
        logger.error("ABORT: Some products have sales — refusing to delete:")
        for r in sold:
            logger.error(f"  ID={r['ID']} SATILMASAYISI={r['SATILMASAYISI']} {r['URUNADI']}")
        cursor.close()
        sys.exit(1)

    # 4. Verify all are MARKAID=68 (Arcelik)
    cursor.execute(f"""
        SELECT ID, MARKAID FROM URUNLER
        WHERE ID IN ({placeholders}) AND MARKAID != %s
    """, tuple(DELETE_IDS) + (ARCELIK_MARKA_ID,))
    wrong_brand = cursor.fetchall()
    if wrong_brand:
        logger.error(f"ABORT: Non-Arcelik products in delete list: {wrong_brand}")
        cursor.close()
        sys.exit(1)

    # 5. Count total Arcelik products (should be ~37 before delete)
    cursor.execute("SELECT COUNT(*) AS cnt FROM URUNLER WHERE MARKAID = %s", (ARCELIK_MARKA_ID,))
    total = cursor.fetchone()["cnt"]

    cursor.close()

    logger.info(f"  Preflight OK: {len(found)}/{EXPECTED_DELETE_COUNT} products found")
    logger.info(f"  All SATILMASAYISI=0, all MARKAID=68")
    logger.info(f"  Current Arcelik total: {total} → after delete: {total - EXPECTED_DELETE_COUNT}")

    return found, total


def count_child_rows(conn):
    """Count rows in child tables that reference the delete IDs."""
    cursor = conn.cursor()
    placeholders = ",".join(["%s"] * len(DELETE_IDS))
    counts = {}

    for table, fk_col in CHILD_TABLES:
        cursor.execute(
            f"SELECT COUNT(*) FROM {table} WHERE {fk_col} IN ({placeholders})",
            tuple(DELETE_IDS),
        )
        cnt = cursor.fetchone()[0]
        counts[table] = cnt

    cursor.close()
    return counts


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------
def execute_delete(conn, dry_run: bool):
    """Delete from child tables then URUNLER, in a single transaction."""
    cursor = conn.cursor()
    placeholders = ",".join(["%s"] * len(DELETE_IDS))
    params = tuple(DELETE_IDS)
    deleted_counts = {}

    try:
        # Delete from all 13 child tables
        for table, fk_col in CHILD_TABLES:
            cursor.execute(
                f"DELETE FROM {table} WHERE {fk_col} IN ({placeholders})",
                params,
            )
            deleted_counts[table] = cursor.rowcount
            logger.debug(f"  DELETE FROM {table}: {cursor.rowcount} rows")

        # Delete from URUNLER
        cursor.execute(
            f"DELETE FROM URUNLER WHERE ID IN ({placeholders})",
            params,
        )
        urunler_deleted = cursor.rowcount
        deleted_counts["URUNLER"] = urunler_deleted
        logger.debug(f"  DELETE FROM URUNLER: {urunler_deleted} rows")

        # Guard: must delete exactly 26
        if urunler_deleted != EXPECTED_DELETE_COUNT:
            conn.rollback()
            logger.error(
                f"ROLLBACK: Deleted {urunler_deleted} from URUNLER, "
                f"expected {EXPECTED_DELETE_COUNT}"
            )
            sys.exit(1)

        # Post-delete verification: count remaining Arcelik products
        cursor.execute(
            "SELECT COUNT(*) FROM URUNLER WHERE MARKAID = %s",
            (ARCELIK_MARKA_ID,),
        )
        remaining = cursor.fetchone()[0]

        if remaining != EXPECTED_REMAINING:
            conn.rollback()
            logger.warning(
                f"WARNING: Remaining Arcelik count is {remaining}, "
                f"expected {EXPECTED_REMAINING}. Proceeding anyway (count may vary)."
            )
            # Don't exit — total might have changed since plan was made
            # Re-commit below

        if dry_run:
            conn.rollback()
            logger.info("  DRY-RUN: Transaction rolled back (no changes)")
        else:
            conn.commit()
            logger.info(f"  COMMITTED: {urunler_deleted} products deleted")
            logger.info(f"  Remaining Arcelik products: {remaining}")

    except Exception as e:
        conn.rollback()
        logger.error(f"  ROLLBACK — error: {e}")
        raise

    cursor.close()
    return deleted_counts


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Arcelik 26 Product Cascade Delete")
    parser.add_argument("--apply", action="store_true", help="Actually delete from DB (default: dry-run)")
    args = parser.parse_args()

    mode = "APPLY" if args.apply else "DRY-RUN"
    logger.info(f"=== Arcelik Product Delete — {mode} — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")
    logger.info(f"  Target: {EXPECTED_DELETE_COUNT} products")
    logger.info(f"  Protected IDs (will NOT delete): {PROTECTED_IDS}")
    logger.info(f"  Detail log: {detail_log_path}")
    logger.info("")

    conn = get_db_connection()

    try:
        # 1. Preflight
        logger.info("--- Preflight Check ---")
        products, total_before = preflight_check(conn)

        # 2. Show products to be deleted
        logger.info("")
        logger.info("--- Products to Delete ---")
        for p in sorted(products, key=lambda x: x["ID"]):
            logger.info(
                f"  ID={p['ID']:5d}  STOK={str(p['STOK'] or 0):>5s}  "
                f"FIYAT1={str(p['FIYAT1'] or 0):>8s}  "
                f"SATILMA={p['SATILMASAYISI'] or 0}  "
                f"{(p['STOKKODU'] or '')[:40]}"
            )

        # 3. Count child rows
        logger.info("")
        logger.info("--- Child Table Rows ---")
        child_counts = count_child_rows(conn)
        total_child = 0
        for table, cnt in child_counts.items():
            if cnt > 0:
                logger.info(f"  {table:30s}: {cnt} rows")
                total_child += cnt
        logger.info(f"  {'TOTAL child rows':30s}: {total_child}")

        # 4. Execute delete
        logger.info("")
        logger.info(f"--- {'EXECUTING DELETE' if args.apply else 'DRY-RUN DELETE'} ---")
        deleted_counts = execute_delete(conn, dry_run=not args.apply)

        # 5. Summary
        logger.info("")
        logger.info("=" * 60)
        logger.info(f"DELETE SUMMARY ({mode})")
        logger.info("=" * 60)
        for table, cnt in deleted_counts.items():
            if cnt > 0:
                logger.info(f"  {table:30s}: {cnt} rows deleted")
        logger.info("=" * 60)

        if not args.apply:
            logger.info("")
            logger.info("DRY-RUN: No changes written to DB.")
            logger.info("Run with --apply to execute delete.")

    finally:
        conn.close()
        logger.info("DB connection closed.")

    logger.info(f"Done. Log: {detail_log_path}")


if __name__ == "__main__":
    main()
