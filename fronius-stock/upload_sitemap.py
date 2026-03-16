#!/usr/bin/env python3
"""Upload updated sitemap to FTP."""
import ftplib
import io
import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent / ".env")

FTP_HOST = os.environ["FTP_HOST"]
FTP_USER = os.environ["FTP_USER"]
FTP_PASS = os.environ["FTP_PASS"]

def main():
    ftp = ftplib.FTP(FTP_HOST)
    ftp.login(FTP_USER, FTP_PASS)
    ftp.set_pasv(False)
    ftp.cwd('/httpdocs')

    # Backup current
    buf = io.BytesIO()
    ftp.retrbinary('RETR sitemap.xml', buf.write)
    buf.seek(0)
    ftp.storbinary('STOR sitemap.xml.bak-20260309-pre-dyness', buf)
    print("Backup: sitemap.xml.bak-20260309-pre-dyness")

    # Upload new
    with open('/Users/baris/Projects/solarmarket-google-merchant-feed/sitemap_new.xml', 'rb') as f:
        ftp.storbinary('STOR sitemap.xml', f)
    print("Uploaded: sitemap.xml")

    ftp.quit()
    print("Done!")

if __name__ == '__main__':
    main()
