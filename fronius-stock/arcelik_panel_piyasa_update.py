#!/usr/bin/env python3
"""
Arçelik Solar Panel — Piyasa Fiyatı Update (×1.22 markup over FIYAT1)

Formula: Watt × $0.2928/W × palet_adedi = PIYASAFIYATI (USD)
İndirim algısı: ~%18

Usage:
  python3 arcelik_panel_piyasa_update.py              # dry-run
  python3 arcelik_panel_piyasa_update.py --apply       # write to DB
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

import pymssql
from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).parent
load_dotenv(SCRIPT_DIR / ".env")

PIYASA_PER_WATT = 0.2928  # ×1.22 of $0.24/W

# 12 panel: (slug_keyword, watt, palet_adedi)
PANELS = [
    ("PV10T-GG-590", 590, 29),
    ("PV10T-GG-595", 595, 29),
    ("PV10T-GG-600", 600, 29),
    ("PV10RT-GG-600", 600, 29),
    ("PV10RT-GG-605", 605, 29),
    ("PV10RT-GG-610", 610, 29),
    ("PV10RT-GG-615", 615, 29),
    ("132PVRT-GG-610", 610, 29),
    ("132PVRT-GG-615", 615, 29),
    ("132PVRT-GG-620", 620, 29),
    ("132PVRT-GG-625", 625, 29),
    ("PV10RT-600", 600, 37),
]

EXPECTED_COUNT = 12


def get_connection():
    server = os.getenv("MSSQL_SERVER")
    port = int(os.getenv("MSSQL_PORT", "1433"))
    user = os.getenv("MSSQL_USER")
    password = os.getenv("MSSQL_PASSWORD")
    database = os.getenv("MSSQL_DATABASE")
    return pymssql.connect(
        server=server, port=port, user=user,
        password=password, database=database, charset="utf8",
    )


def fetch_arcelik_panels(conn):
    cursor = conn.cursor(as_dict=True)
    cursor.execute("""
        SELECT ID, URUNADI, STOKKODU, FIYAT1, PIYASAFIYATI, STOK
        FROM URUNLER
        WHERE MARKAID = 68
          AND (URUNADI LIKE '%%Solar Panel%%'
               OR URUNADI LIKE '%%Güneş Paneli%%'
               OR URUNADI LIKE '%%PV10%%'
               OR URUNADI LIKE '%%PVRT%%'
               OR STOKKODU LIKE '%%PV10%%'
               OR STOKKODU LIKE '%%PVRT%%')
          AND STOK > 0
    """)
    rows = cursor.fetchall()
    cursor.close()
    return rows


def match_panel(db_row, panel_keyword):
    stokkodu = (db_row.get("STOKKODU") or "").upper()
    urunadi = (db_row.get("URUNADI") or "").upper()
    keyword = panel_keyword.upper()
    return keyword in stokkodu or keyword in urunadi


def main():
    parser = argparse.ArgumentParser(description="Arçelik Panel Piyasa Fiyatı Update")
    parser.add_argument("--apply", action="store_true", help="Write to DB")
    args = parser.parse_args()

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"=== Arçelik Panel Piyasa Fiyatı Update — {mode} — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")
    print(f"  Piyasa: ${PIYASA_PER_WATT}/W (×1.22 of $0.24/W → ~%18 indirim algısı)")
    print()

    conn = get_connection()
    print("DB connected.")

    db_panels = fetch_arcelik_panels(conn)
    print(f"Found {len(db_panels)} Arçelik panel products in DB (STOK>0).\n")

    updates = []
    unmatched_panels = []

    for keyword, watt, adet in PANELS:
        matched = None
        for row in db_panels:
            if match_panel(row, keyword):
                matched = row
                break

        if not matched:
            unmatched_panels.append(keyword)
            print(f"  NOT FOUND: {keyword}")
            continue

        fiyat1 = round(float(matched["FIYAT1"] or 0), 2)
        old_piyasa = round(float(matched["PIYASAFIYATI"] or 0), 2)
        new_piyasa = round(watt * PIYASA_PER_WATT * adet, 2)
        discount_pct = round((1 - fiyat1 / new_piyasa) * 100, 1) if new_piyasa > 0 else 0

        updates.append({
            "id": matched["ID"],
            "keyword": keyword,
            "watt": watt,
            "adet": adet,
            "stokkodu": matched["STOKKODU"],
            "fiyat1": fiyat1,
            "old_piyasa": old_piyasa,
            "new_piyasa": new_piyasa,
        })

        print(
            f"  ID={matched['ID']:5d} | {keyword:25s} | "
            f"{watt}W x {adet} | "
            f"FIYAT1: ${fiyat1:,.2f} | "
            f"PIYASA: ${old_piyasa:,.2f} -> ${new_piyasa:,.2f} | "
            f"indirim: %{discount_pct}"
        )

    print(f"\n{'='*80}")
    print(f"  Matched: {len(updates)}/{EXPECTED_COUNT}")
    if unmatched_panels:
        print(f"  Unmatched: {unmatched_panels}")

    if len(updates) != EXPECTED_COUNT:
        print(f"\n  GUARD FAIL: Expected {EXPECTED_COUNT}, got {len(updates)}. ABORT.")
        conn.close()
        sys.exit(1)

    print(f"  Count guard OK ({EXPECTED_COUNT}/{EXPECTED_COUNT})")

    if args.apply:
        print(f"\n*** APPLYING {len(updates)} PIYASAFIYATI updates... ***")
        cursor = conn.cursor()
        try:
            for u in updates:
                cursor.execute("""
                    UPDATE URUNLER
                    SET PIYASAFIYATI = %s
                    WHERE ID = %s
                """, (u["new_piyasa"], u["id"]))
            conn.commit()
            print(f"  COMMITTED {len(updates)} updates.")
        except Exception as e:
            conn.rollback()
            print(f"  ROLLBACK: {e}")
            raise
    else:
        print(f"\nDRY-RUN — no changes. Run with --apply to execute.")

    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
