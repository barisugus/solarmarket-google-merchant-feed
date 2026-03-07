#!/usr/bin/env python3
"""
Arçelik PDF → MSSQL Price Sync

Reads Arçelik inverter price list PDF, matches products against MSSQL URUNLER table,
and updates FIYAT1 (sell price) and ALISFIYATI (buy price).

Rules:
- ONLY exact normalized SKU match → auto update
- FIYAT1 = round(pdf_price * 1.17, 2), ALISFIYATI = pdf_price
- DB STOK kontrolü YAPILMAZ (Arçelik SAP paylaşmıyor, stok her zaman var kabul)
- No INSERT, DELETE, or STOK changes
- Transaction guard: expected update_count=10, if different → ROLLBACK

Usage:
  python3 arcelik_sync.py                     # dry-run (default)
  python3 arcelik_sync.py --apply             # actually write to DB
  python3 arcelik_sync.py --pdf path.pdf      # custom PDF path
"""

import argparse
import csv
import logging
import os
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import pdfplumber
import pymssql
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).parent
PDF_DEFAULT = SCRIPT_DIR.parent / "Arçelik Inverter EÇN Özel Fiyat Listesi_1.01.2026.pdf"
REPORT_CSV = SCRIPT_DIR / "arcelik_sync_report.csv"
LOG_DIR = SCRIPT_DIR / "logs"

MARKUP = 1.17  # FIYAT1 = pdf_price * MARKUP
ARCELIK_MARKA_ID = 68

# Expected counts — apply guard
EXPECTED_UPDATE_COUNT = 10
EXPECTED_NOT_IN_DB_COUNT = 5
EXPECTED_SKIP_COUNT = 27

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_DIR.mkdir(exist_ok=True)
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
detail_log_path = LOG_DIR / f"arcelik_sync_{timestamp}.log"

logger = logging.getLogger("arcelik_sync")
logger.setLevel(logging.DEBUG)

# File handler — detailed
fh = logging.FileHandler(detail_log_path, encoding="utf-8")
fh.setLevel(logging.DEBUG)
fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(fh)

# Console handler — info+
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
ch.setFormatter(logging.Formatter("%(message)s"))
logger.addHandler(ch)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def normalize_sku(raw: str) -> str:
    """Normalize SKU: remove commas, spaces, dashes, dots. Uppercase."""
    if not raw:
        return ""
    s = str(raw).strip()
    s = re.sub(r"[,\s\.\-]", "", s)
    return s.upper()


def normalize_turkish(s: str) -> str:
    """Replace Turkish special chars with ASCII equivalents."""
    tr_map = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
    return s.translate(tr_map)


def extract_arclk_sku(stokkodu: str) -> str:
    """Extract ARCLK-XXX part from DB STOKKODU which may have brand prefix.
    E.g., 'Arçelik ARCLK-INV-8KT' → 'ARCLK-INV-8KT'
    """
    s = normalize_turkish(stokkodu)
    m = re.search(r'(ARCLK[\w\-]+)', s, re.IGNORECASE)
    if m:
        return m.group(1)
    return stokkodu


# ---------------------------------------------------------------------------
# PDF Parser
# ---------------------------------------------------------------------------
def parse_pdf_price(raw: str) -> float:
    """Parse price from PDF cell. Handles '$1.052' (Turkish thousands dot) format."""
    s = raw.replace(" ", "").replace("$", "").replace("€", "")
    # Turkish format: dot is thousands separator, no decimal part in this PDF
    # Examples: "479", "1.052", "2.300"
    # All prices in this PDF are whole USD amounts
    s = s.replace(".", "")  # remove thousands separator
    if "," in s:
        s = s.replace(",", ".")  # decimal comma → dot (if any)
    return float(s)


def parse_pdf(path: str) -> list[dict]:
    """
    Parse Arçelik inverter price list PDF.
    Returns list of {name, sku, sku_norm, price}.

    PDF structure (1 page, 1 table):
      Col 0: SAP code (9009221100)
      Col 1: ÜRÜN ADI = ARCLK SKU (ARCLK-INV-8KT)
      Col 2: LİSTE FİYATI ($942)
      Col 3-5: Kampanyalı fiyatlar (ignored)
    Rows 0-1: headers, rows 2-16: data (15 products)
    """
    logger.info(f"Reading PDF: {path}")

    products = []
    seen_skus = set()

    with pdfplumber.open(path) as pdf:
        for page_num, page in enumerate(pdf.pages, 1):
            tables = page.extract_tables()
            logger.debug(f"  Page {page_num}: {len(tables)} table(s)")

            for table in tables:
                if not table or len(table) < 3:
                    continue

                # Skip header rows (rows 0-1), parse data rows
                for row_idx in range(2, len(table)):
                    row = table[row_idx]
                    if not row or len(row) < 3:
                        continue

                    sap_code = str(row[0] or "").strip()
                    sku_val = str(row[1] or "").strip()  # ARCLK-INV-xxx
                    price_val = str(row[2] or "").strip()  # Liste Fiyatı

                    if not sku_val or not price_val:
                        continue

                    # Must be ARCLK format
                    if not sku_val.upper().startswith("ARCLK"):
                        logger.debug(f"  Row {row_idx}: skipping non-ARCLK SKU: {sku_val}")
                        continue

                    try:
                        price = parse_pdf_price(price_val)
                    except (ValueError, TypeError):
                        logger.debug(f"  Row {row_idx}: non-numeric price {repr(price_val)} for {sku_val}")
                        continue

                    if price <= 0:
                        continue

                    sku_norm = normalize_sku(sku_val)
                    if not sku_norm:
                        continue

                    # Deduplicate
                    if sku_norm in seen_skus:
                        logger.debug(f"  Duplicate SKU {sku_norm}, skipping")
                        continue
                    seen_skus.add(sku_norm)

                    products.append({
                        "name": sku_val,  # ARCLK SKU doubles as name
                        "sku": sku_val,
                        "sku_norm": sku_norm,
                        "price": round(price, 2),
                        "sap_code": sap_code,
                    })

    logger.info(f"  Parsed {len(products)} products from PDF")
    for p in products:
        logger.debug(f"    {p['sku']:25s}  ${p['price']:>10.2f}")
    return products


# ---------------------------------------------------------------------------
# DB Functions
# ---------------------------------------------------------------------------
def get_db_connection():
    """Create MSSQL connection from .env credentials."""
    load_dotenv(SCRIPT_DIR / ".env")

    server = os.getenv("MSSQL_SERVER")
    port = int(os.getenv("MSSQL_PORT", "1433"))
    user = os.getenv("MSSQL_USER")
    password = os.getenv("MSSQL_PASSWORD")
    database = os.getenv("MSSQL_DATABASE")

    if not all([server, user, password, database]):
        logger.error("Missing DB credentials in .env")
        sys.exit(1)

    # SECRET SAFETY: never log credentials
    logger.info("Connecting to MSSQL...")
    conn = pymssql.connect(
        server=server,
        port=port,
        user=user,
        password=password,
        database=database,
        charset="utf8",
    )
    logger.info("  Connected OK")
    return conn


def fetch_arcelik_products(conn) -> list[dict]:
    """Fetch all Arçelik products from URUNLER (MARKAID=68)."""
    cursor = conn.cursor(as_dict=True)
    cursor.execute("""
        SELECT
            ID, URUNADI, STOKKODU, STOK, FIYAT1, ALISFIYATI
        FROM URUNLER
        WHERE MARKAID = %s
    """, (ARCELIK_MARKA_ID,))
    rows = cursor.fetchall()
    cursor.close()

    # Enrich with normalized SKU — extract ARCLK part first (strip brand prefix)
    for r in rows:
        raw = r["STOKKODU"] or ""
        arclk_part = extract_arclk_sku(raw)
        r["stokkodu_norm"] = normalize_sku(arclk_part)

    logger.info(f"  Fetched {len(rows)} Arçelik products from DB")
    return rows


# ---------------------------------------------------------------------------
# Matching — EXACT SKU ONLY
# ---------------------------------------------------------------------------
def match_products(pdf_products: list[dict], db_products: list[dict]) -> list[dict]:
    """
    Match PDF products to DB products using EXACT normalized SKU match only.
    No fuzzy match, no name match.
    """
    results = []

    # Build SKU lookup
    db_by_sku = {}
    for p in db_products:
        if p["stokkodu_norm"]:
            db_by_sku[p["stokkodu_norm"]] = p

    matched_db_ids = set()

    for pp in pdf_products:
        result = {
            "excel_sku": pp["sku"],
            "excel_name": pp["name"],
            "excel_price": pp["price"],
            "db_product_id": "",
            "db_stokkodu": "",
            "db_name": "",
            "db_stock": "",
            "old_fiyat1": "",
            "new_fiyat1": "",
            "old_alisfiyati": "",
            "new_alisfiyati": "",
            "action": "",
            "reason": "",
            "price_direction": "",
            "note": "",
        }

        # ONLY exact normalized SKU match
        db_match = db_by_sku.get(pp["sku_norm"])

        if db_match:
            matched_db_ids.add(db_match["ID"])
            stock = db_match["STOK"] or 0
            old_fiyat1 = round(float(db_match["FIYAT1"] or 0), 2)
            old_alis = round(float(db_match["ALISFIYATI"] or 0), 2)

            new_alis = round(pp["price"], 2)
            new_fiyat1 = round(pp["price"] * MARKUP, 2)

            result["db_product_id"] = db_match["ID"]
            result["db_stokkodu"] = db_match["STOKKODU"] or ""
            result["db_name"] = db_match["URUNADI"] or ""
            result["db_stock"] = stock
            result["old_fiyat1"] = old_fiyat1
            result["new_fiyat1"] = new_fiyat1
            result["old_alisfiyati"] = old_alis
            result["new_alisfiyati"] = new_alis
            result["action"] = "UPDATE_PRICE"
            result["reason"] = "exact_sku_match"

            # Price direction
            if new_fiyat1 > old_fiyat1:
                result["price_direction"] = "INCREASE"
            elif new_fiyat1 < old_fiyat1:
                result["price_direction"] = "DECREASE"
            else:
                result["price_direction"] = "SAME"

            # Special note for STOK=0 products
            if stock == 0:
                result["note"] = "DB_STOCK_ZERO_BUT_PRICE_UPDATED"

        else:
            result["action"] = "NOT_IN_DB"
            result["reason"] = "no exact SKU match in DB"

        results.append(result)

    # DB products not in PDF → SKIP
    for dp in db_products:
        if dp["ID"] not in matched_db_ids:
            results.append({
                "excel_sku": "",
                "excel_name": "",
                "excel_price": "",
                "db_product_id": dp["ID"],
                "db_stokkodu": dp["STOKKODU"] or "",
                "db_name": dp["URUNADI"] or "",
                "db_stock": dp["STOK"] or 0,
                "old_fiyat1": round(float(dp["FIYAT1"] or 0), 2),
                "new_fiyat1": "",
                "old_alisfiyati": round(float(dp["ALISFIYATI"] or 0), 2),
                "new_alisfiyati": "",
                "action": "SKIP",
                "reason": "DB product not in PDF",
                "price_direction": "",
                "note": "",
            })

    return results


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
CSV_COLUMNS = [
    "excel_sku", "excel_name", "excel_price",
    "db_product_id", "db_stokkodu", "db_name", "db_stock",
    "old_fiyat1", "new_fiyat1", "old_alisfiyati", "new_alisfiyati",
    "action", "reason", "price_direction", "note",
]


def write_report(results: list[dict], path: Path):
    """Write CSV report."""
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(results)
    logger.info(f"  Report written: {path}")


def print_summary(results: list[dict]):
    """Print action summary to console."""
    counts = Counter(r["action"] for r in results)

    logger.info("")
    logger.info("=" * 60)
    logger.info("SYNC SUMMARY")
    logger.info("=" * 60)
    for action in ["UPDATE_PRICE", "NOT_IN_DB", "SKIP"]:
        if counts.get(action, 0) > 0:
            logger.info(f"  {action:25s}: {counts[action]}")
    logger.info(f"  {'TOTAL':25s}: {len(results)}")
    logger.info("=" * 60)

    # Count guard check
    update_count = counts.get("UPDATE_PRICE", 0)
    not_in_db_count = counts.get("NOT_IN_DB", 0)
    skip_count = counts.get("SKIP", 0)

    guard_ok = True
    if update_count != EXPECTED_UPDATE_COUNT:
        logger.warning(f"  ⚠ UPDATE_PRICE count {update_count} != expected {EXPECTED_UPDATE_COUNT}")
        guard_ok = False
    if not_in_db_count != EXPECTED_NOT_IN_DB_COUNT:
        logger.warning(f"  ⚠ NOT_IN_DB count {not_in_db_count} != expected {EXPECTED_NOT_IN_DB_COUNT}")
        guard_ok = False
    if skip_count != EXPECTED_SKIP_COUNT:
        logger.warning(f"  ⚠ SKIP count {skip_count} != expected {EXPECTED_SKIP_COUNT}")
        guard_ok = False

    if guard_ok:
        logger.info("  ✓ All counts match expected values")
    else:
        logger.warning("  ⚠ COUNT MISMATCH — apply will be BLOCKED until counts are correct")

    # Show price changes detail
    updates = [r for r in results if r["action"] == "UPDATE_PRICE"]
    if updates:
        logger.info("")
        logger.info("PRICE CHANGES:")
        for r in updates:
            old_f = r["old_fiyat1"]
            new_f = r["new_fiyat1"]
            direction = r["price_direction"]
            diff = float(new_f) - float(old_f) if old_f and new_f else 0
            note = f"  [{r['note']}]" if r["note"] else ""
            marker = ""
            if direction == "DECREASE":
                marker = " ⚠ DECREASE"
            logger.info(
                f"  [{direction:8s}] {r['db_stokkodu'][:40]:40s} "
                f"FIYAT1: {old_f} → {new_f} (diff: {diff:+.2f}){marker}{note}"
            )

    # Show NOT_IN_DB
    not_in_db = [r for r in results if r["action"] == "NOT_IN_DB"]
    if not_in_db:
        logger.info("")
        logger.info("NOT IN DB (PDF'de var, DB'de yok):")
        for r in not_in_db:
            logger.info(f"  {r['excel_sku']:25s}  ${r['excel_price']:>10}  {r['excel_name']}")

    return guard_ok


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------
def apply_updates(conn, results: list[dict]):
    """Apply price updates to DB in a single transaction with count guard."""
    updates = [r for r in results if r["action"] == "UPDATE_PRICE"]

    if not updates:
        logger.info("No updates to apply.")
        return

    # GUARD: check count before applying
    if len(updates) != EXPECTED_UPDATE_COUNT:
        logger.error(
            f"ABORT: update count {len(updates)} != expected {EXPECTED_UPDATE_COUNT}. "
            f"Will NOT apply. Fix matching or update EXPECTED_UPDATE_COUNT."
        )
        sys.exit(1)

    logger.info(f"Applying {len(updates)} price updates in transaction...")

    cursor = conn.cursor()
    try:
        for r in updates:
            product_id = r["db_product_id"]
            new_fiyat1 = r["new_fiyat1"]
            new_alis = r["new_alisfiyati"]

            # ONLY update FIYAT1 and ALISFIYATI — nothing else
            cursor.execute("""
                UPDATE URUNLER
                SET FIYAT1 = %s, ALISFIYATI = %s
                WHERE ID = %s
            """, (new_fiyat1, new_alis, product_id))

            logger.debug(
                f"  Updated ID={product_id}: FIYAT1={new_fiyat1}, ALISFIYATI={new_alis}"
            )

        # Verify update count matches
        actual_count = len(updates)
        if actual_count != EXPECTED_UPDATE_COUNT:
            conn.rollback()
            logger.error(
                f"ROLLBACK — update count {actual_count} != expected {EXPECTED_UPDATE_COUNT}"
            )
            sys.exit(1)

        conn.commit()
        logger.info(f"  COMMITTED {len(updates)} updates successfully")

    except Exception as e:
        conn.rollback()
        logger.error(f"  ROLLBACK — error during apply: {e}")
        raise


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Arçelik PDF → MSSQL Price Sync")
    parser.add_argument("--apply", action="store_true", help="Actually write to DB (default: dry-run)")
    parser.add_argument("--pdf", type=str, default=str(PDF_DEFAULT), help="Path to PDF file")
    args = parser.parse_args()

    mode = "APPLY" if args.apply else "DRY-RUN"
    logger.info(f"=== Arçelik Price Sync — {mode} — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")
    logger.info(f"  Markup: {MARKUP}x")
    logger.info(f"  Detail log: {detail_log_path}")

    # 1. Parse PDF
    pdf_products = parse_pdf(args.pdf)
    if not pdf_products:
        logger.error("No products found in PDF. Aborting.")
        sys.exit(1)

    # 2. Connect to DB
    conn = get_db_connection()

    try:
        # 3. Fetch DB products
        db_products = fetch_arcelik_products(conn)

        # 4. Match
        results = match_products(pdf_products, db_products)

        # 5. Report
        write_report(results, REPORT_CSV)
        guard_ok = print_summary(results)

        # 6. Apply if requested
        if args.apply:
            if not guard_ok:
                logger.error("")
                logger.error("ABORT: Count guard failed. Will NOT apply.")
                logger.error("Fix matching or update expected counts before --apply.")
                sys.exit(1)

            logger.info("")
            logger.info("*** APPLY MODE — writing to database ***")
            apply_updates(conn, results)
        else:
            logger.info("")
            logger.info("DRY-RUN mode — no changes written to DB.")
            logger.info(f"Review report: {REPORT_CSV}")
            logger.info("Run with --apply to execute updates.")

    finally:
        conn.close()
        logger.info("DB connection closed.")

    logger.info(f"Done. Log: {detail_log_path}")


if __name__ == "__main__":
    main()
