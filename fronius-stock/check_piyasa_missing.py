#!/usr/bin/env python3
"""List products with STOK>0, FIYAT1>0 but PIYASAFIYATI=0."""
import os
import pymssql
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent / ".env")

conn = pymssql.connect(
    server=os.getenv("MSSQL_SERVER"),
    port=int(os.getenv("MSSQL_PORT", "1433")),
    user=os.getenv("MSSQL_USER"),
    password=os.getenv("MSSQL_PASSWORD"),
    database=os.getenv("MSSQL_DATABASE"),
    charset="utf8",
)
cur = conn.cursor(as_dict=True)
cur.execute("""
    SELECT u.ID, u.URUNADI, u.STOKKODU, u.FIYAT1, u.PIYASAFIYATI, u.STOK, u.MARKAID, m.MARKA
    FROM URUNLER u
    LEFT JOIN MARKALAR m ON u.MARKAID = m.ID
    WHERE u.STOK > 0 AND u.FIYAT1 > 0
      AND (u.PIYASAFIYATI IS NULL OR u.PIYASAFIYATI = 0)
    ORDER BY m.MARKA, u.URUNADI
""")
rows = cur.fetchall()
print(f"Toplam {len(rows)} urun (STOK>0, FIYAT1>0, PIYASAFIYATI=0):\n")

current_brand = None
brand_count = 0
for r in rows:
    brand = r["MARKA"] or "Markasiz"
    if brand != current_brand:
        if current_brand:
            print(f"  [{brand_count} urun]\n")
        current_brand = brand
        brand_count = 0
        print(f"--- {brand} ---")
    brand_count += 1
    print(
        f"  ID={r['ID']:5d} | FIYAT1: ${float(r['FIYAT1']):>9,.2f} | "
        f"STOK: {r['STOK']:3d} | {(r['URUNADI'] or '')[:60]}"
    )
if current_brand:
    print(f"  [{brand_count} urun]")

cur.close()
conn.close()
