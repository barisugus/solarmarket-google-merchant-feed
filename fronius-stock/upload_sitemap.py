#!/usr/bin/env python3
"""Upload updated sitemap to FTP."""
import ftplib
import io

FTP_HOST = '37.148.209.147'
FTP_USER = 'turkiyes_u8ui8khk169'
FTP_PASS = '3*Jo*90rMoErypeo'

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
