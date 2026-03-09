#!/usr/bin/env python3
"""
TSM Database Backup — Kritik tabloları local CSV'ye yedekler.
Ayrıca sunucuda MSSQL BACKUP DATABASE komutu çalıştırır.

Usage:
  python3 db_backup.py
"""

import csv
import os
from datetime import datetime
from pathlib import Path

import pymssql
from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).parent
load_dotenv(SCRIPT_DIR / ".env")

BACKUP_DIR = SCRIPT_DIR / "backups"
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

TABLES_TO_BACKUP = [
    ("URUNLER", "SELECT * FROM URUNLER"),
    ("MARKALAR", "SELECT * FROM MARKALAR"),
    ("KATEGORILER", "SELECT * FROM KATEGORILER"),
    ("URUNKATEGORILERI", "SELECT * FROM URUNKATEGORILERI"),
    ("URUNRESIMLERI", "SELECT * FROM URUNRESIMLERI"),
    ("URUNSTOKDURUMLARI", "SELECT * FROM URUNSTOKDURUMLARI"),
]


def get_connection():
    return pymssql.connect(
        server=os.getenv("MSSQL_SERVER"),
        port=int(os.getenv("MSSQL_PORT", "1433")),
        user=os.getenv("MSSQL_USER"),
        password=os.getenv("MSSQL_PASSWORD"),
        database=os.getenv("MSSQL_DATABASE"),
        charset="utf8",
    )


def backup_table(conn, table_name, query, backup_dir):
    cursor = conn.cursor(as_dict=True)
    cursor.execute(query)
    rows = cursor.fetchall()
    cursor.close()

    if not rows:
        print(f"  {table_name}: 0 rows — skipped")
        return 0

    filepath = backup_dir / f"{table_name}_{TIMESTAMP}.csv"
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    print(f"  {table_name}: {len(rows)} rows -> {filepath.name}")
    return len(rows)


def main():
    backup_dir = BACKUP_DIR / TIMESTAMP
    backup_dir.mkdir(parents=True, exist_ok=True)

    print(f"=== TSM DB Backup — {TIMESTAMP} ===")
    print(f"  Backup dir: {backup_dir}\n")

    conn = get_connection()
    print("DB connected.\n")

    total_rows = 0
    for table_name, query in TABLES_TO_BACKUP:
        total_rows += backup_table(conn, table_name, query, backup_dir)

    # Server-side MSSQL backup
    print("\nServer-side MSSQL backup...")
    try:
        cursor = conn.cursor()
        backup_path = f"C:\\Backup\\turkiyeSolarMarketDb_{TIMESTAMP}.bak"
        cursor.execute(f"BACKUP DATABASE turkiyeSolarMarketDb TO DISK = '{backup_path}'")
        conn.commit()
        cursor.close()
        print(f"  Server backup: {backup_path}")
    except Exception as e:
        print(f"  Server backup FAILED (non-critical): {e}")
        print("  Local CSV backups are sufficient.")

    conn.close()

    print(f"\n{'='*60}")
    print(f"  Total: {total_rows} rows backed up")
    print(f"  Local: {backup_dir}")
    print("Done.")


if __name__ == "__main__":
    main()
