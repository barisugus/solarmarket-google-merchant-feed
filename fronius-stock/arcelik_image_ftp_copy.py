#!/usr/bin/env python3
"""
Arçelik Panel Image FTP Copy

Copies source image from product 1453 to 12 new product directories (1600-1611).
Renames to match DB RESIM field: arcelik-solar-panel-placeholder.jpg

Usage:
  python3 arcelik_image_ftp_copy.py              # dry-run (list only)
  python3 arcelik_image_ftp_copy.py --apply       # actually copy files
"""

import io
import sys
import argparse
from ftplib import FTP

# Config
FTP_HOST = "37.148.209.147"
FTP_USER = "turkiyes_u8ui8khk169"
FTP_PASS = "YGaSspdivyh4#36$"
BASE_PATH = "/httpdocs/epanel/upl"

SOURCE_ID = 1453
TARGET_IDS = list(range(1600, 1612))  # 1600-1611

# Source files to download (from product 1453)
SOURCE_FILES = [
    "big_arcelik-inv-30kt.jpg",
    "thumb_arcelik-inv-30kt.jpg",
    "arcelik-inv-30kt.jpg",
    "icon_arcelik-inv-30kt.jpg",
]

# DB RESIM field value
DB_RESIM = "arcelik-solar-panel-placeholder.jpg"

# Target filenames (must match DB RESIM pattern)
TARGET_MAP = {
    "big_arcelik-inv-30kt.jpg": f"big_{DB_RESIM}",
    "thumb_arcelik-inv-30kt.jpg": f"thumb_{DB_RESIM}",
    "arcelik-inv-30kt.jpg": DB_RESIM,
    "icon_arcelik-inv-30kt.jpg": f"icon_{DB_RESIM}",
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    
    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"=== Arçelik Image FTP Copy — {mode} ===")
    print(f"  Source: product {SOURCE_ID}")
    print(f"  Targets: {TARGET_IDS[0]}-{TARGET_IDS[-1]} ({len(TARGET_IDS)} products)")
    print()

    # Connect
    ftp = FTP()
    ftp.connect(FTP_HOST, 21, timeout=30)
    ftp.login(FTP_USER, FTP_PASS)
    ftp.set_pasv(False)  # Active mode required (Plesk firewall)
    print(f"  FTP connected: {ftp.getwelcome()}")
    print()

    # Step 1: Download source files into memory
    print("--- Downloading source files ---")
    source_buffers = {}
    for src_file in SOURCE_FILES:
        src_path = f"{BASE_PATH}/{SOURCE_ID}/{src_file}"
        buf = io.BytesIO()
        try:
            ftp.retrbinary(f"RETR {src_path}", buf.write)
            size = buf.tell()
            buf.seek(0)  # CRITICAL: reset for re-upload
            source_buffers[src_file] = buf
            print(f"  OK: {src_file} ({size:,} bytes)")
        except Exception as e:
            print(f"  SKIP: {src_file} — {e}")
    
    if not source_buffers:
        print("ERROR: No source files downloaded!")
        ftp.quit()
        sys.exit(1)
    
    # Must have at least big_ and thumb_
    required = ["big_arcelik-inv-30kt.jpg", "thumb_arcelik-inv-30kt.jpg"]
    for r in required:
        if r not in source_buffers:
            print(f"ERROR: Required source file missing: {r}")
            ftp.quit()
            sys.exit(1)
    
    print(f"\n  Downloaded {len(source_buffers)}/{len(SOURCE_FILES)} source files")
    print()

    # Step 2: Upload to each target directory
    print("--- Uploading to target directories ---")
    total_uploaded = 0
    total_skipped = 0
    errors = []

    for tid in TARGET_IDS:
        target_dir = f"{BASE_PATH}/{tid}"
        print(f"\n  Product {tid}:")
        
        # Check if directory exists
        try:
            ftp.cwd(target_dir)
        except Exception:
            if args.apply:
                try:
                    ftp.mkd(target_dir)
                    print(f"    Created directory: {target_dir}")
                    ftp.cwd(target_dir)
                except Exception as e:
                    print(f"    ERROR creating dir: {e}")
                    errors.append((tid, "mkdir", str(e)))
                    continue
            else:
                print(f"    Would create directory: {target_dir}")

        # Check existing files
        try:
            existing = ftp.nlst(target_dir)
            existing_names = [f.split("/")[-1] for f in existing]
        except Exception:
            existing_names = []

        for src_file, buf in source_buffers.items():
            target_name = TARGET_MAP[src_file]
            target_path = f"{target_dir}/{target_name}"
            
            # Skip if already exists
            if target_name in existing_names:
                print(f"    SKIP (exists): {target_name}")
                total_skipped += 1
                continue
            
            if args.apply:
                try:
                    buf.seek(0)  # Reset buffer position for each upload
                    ftp.storbinary(f"STOR {target_path}", buf)
                    print(f"    OK: {target_name}")
                    total_uploaded += 1
                except Exception as e:
                    print(f"    ERROR: {target_name} — {e}")
                    errors.append((tid, target_name, str(e)))
            else:
                print(f"    Would upload: {target_name}")
                total_uploaded += 1

    # Summary
    print()
    print("=" * 60)
    print(f"SUMMARY ({mode})")
    print("=" * 60)
    print(f"  Files uploaded: {total_uploaded}")
    print(f"  Files skipped (exist): {total_skipped}")
    print(f"  Errors: {len(errors)}")
    if errors:
        for tid, fname, err in errors:
            print(f"    ID={tid} file={fname}: {err}")
    print("=" * 60)
    
    if not args.apply:
        print("\nDRY-RUN: No files were uploaded.")
        print("Run with --apply to copy files.")

    ftp.quit()
    print("FTP disconnected.")


if __name__ == "__main__":
    main()
