#!/usr/bin/env python3
"""
Fronius — Piyasa Fiyatı Update (FIYAT1 × 1.22 = PIYASAFIYATI)

Sets PIYASAFIYATI for all Fronius products with STOK>0 and FIYAT1>0.
~%18 discount perception on product pages.

Usage:
  python3 fronius_piyasa_update.py              # dry-run
  python3 fronius_piyasa_update.py --apply       # write to DB
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

PIYASA_MARKUP = 1.22  # PIYASAFIYATI = FIYAT1 × 1.22
FRONIUS_MARKA_ID = 49


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


def main():
    parser = argparse.ArgumentParser(description="Fronius Piyasa Fiyatı Update")
    parser.add_argument("--apply", action="store_true", help="Write to DB")
    args = parser.parse_args()

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"=== Fronius Piyasa Fiyatı Update — {mode} — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")
    print(f"  PIYASAFIYATI = FIYAT1 × {PIYASA_MARKUP} (~%{round((1 - 1/PIYASA_MARKUP)*100, 1)} indirim algısı)")
    print()

    conn = get_connection()
    print("DB connected.")

    cursor = conn.cursor(as_dict=True)
    cursor.execute("""
        SELECT ID, URUNADI, STOKKODU, FIYAT1, PIYASAFIYATI, STOK
        FROM URUNLER
        WHERE MARKAID = %s AND STOK > 0 AND FIYAT1 > 0
        ORDER BY URUNADI
    """, (FRONIUS_MARKA_ID,))
    rows = cursor.fetchall()
    cursor.close()

    print(f"Found {len(rows)} Fronius products (STOK>0, FIYAT1>0).\n")

    updates = []
    for row in rows:
        fiyat1 = round(float(row["FIYAT1"]), 2)
        old_piyasa = round(float(row["PIYASAFIYATI"] or 0), 2)
        new_piyasa = round(fiyat1 * PIYASA_MARKUP, 2)

        updates.append({
            "id": row["ID"],
            "name": row["URUNADI"],
            "fiyat1": fiyat1,
            "old_piyasa": old_piyasa,
            "new_piyasa": new_piyasa,
        })

        marker = " *" if old_piyasa == 0 else ""
        print(
            f"  ID={row['ID']:5d} | FIYAT1: ${fiyat1:>9,.2f} | "
            f"PIYASA: ${old_piyasa:>9,.2f} -> ${new_piyasa:>9,.2f}{marker} | "
            f"{(row['URUNADI'] or '')[:55]}"
        )

    print(f"\n{'='*90}")
    print(f"  Total: {len(updates)} products")

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
