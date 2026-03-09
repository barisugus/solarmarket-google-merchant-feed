#!/usr/bin/env python3
"""
Download Dyness product images from web, resize to 4 sizes, upload to FTP, insert DB records.
Image path: /httpdocs/epanel/upl/{URUNID}/big_{filename}
DB: URUNRESIMLERI (URUNID, RESIM, VARSAYILAN, ALTTAG, VARYANTALANID)
"""
import ftplib
import io
import os
import pymssql
from urllib.request import Request, urlopen
from PIL import Image

DB_SERVER = '37.148.209.147'
DB_USER = 'trSolarMarket.dogus.egebilgi'
DB_PASS = '3%DKveYq*6py0ntn'
DB_NAME = 'turkiyeSolarMarketDb'
FTP_HOST = '37.148.209.147'
FTP_USER = 'turkiyes_u8ui8khk169'
FTP_PASS = '3*Jo*90rMoErypeo'

# Product ID → image URL + alt text + filename
PRODUCTS = {
    1814: {
        'url': 'https://www.dyness.com/Public/Uploads/uploadfile/images/20240328/Tower.png',
        'alt': 'Dyness Tower T10 HV 9.6 kWh Yüksek Gerilim Lityum Batarya – Türkiye Solar Market',
        'filename': 'dyness-tower-t10-hv.png',
    },
    1815: {
        'url': 'https://b2b.ecoabm.com/media/catalog/product/cache/00c0ec2b6ff4fa1d9d73b690ed087b91/d/y/dyness-t9637-bms-tower-bdu-base-battery-management-system-0.jpg',
        'alt': 'Dyness Tower T10 BDU Batarya Dağıtım Ünitesi – Türkiye Solar Market',
        'filename': 'dyness-tower-t10-bdu.jpg',
    },
    1816: {
        'url': 'https://www.dyness.com/Public/Uploads/uploadfile/images/20240328/Tower.png',
        'alt': 'Dyness Tower T10 HV 10 kWh Yüksek Gerilim Lityum Batarya – Türkiye Solar Market',
        'filename': 'dyness-tower-t10-hv-10kwh.png',
    },
    1817: {
        'url': 'https://www.dyness.com/Public/Uploads/uploadfile/images/20240329/37.png',
        'alt': 'Dyness Tower Pro T10 BDU Batarya Dağıtım Ünitesi – Türkiye Solar Market',
        'filename': 'dyness-tower-pro-t10-bdu.png',
    },
    1818: {
        'url': 'https://batterydistributors.co.za/wp-content/uploads/2023/04/Dyness-BX51100.jpeg',
        'alt': 'Dyness BX51100 51.2V 100Ah Ticari Lityum Batarya – Türkiye Solar Market',
        'filename': 'dyness-bx51100.jpeg',
    },
    1819: {
        'url': 'https://techhutsa.co.za/cdn/shop/files/Dyness_BDU_and_HV_bx51100HV_Kit.png?v=1751442331',
        'alt': 'Dyness BX51100 BDU Ticari Batarya Dağıtım Ünitesi – Türkiye Solar Market',
        'filename': 'dyness-bx51100-bdu.png',
    },
}

# 4 size prefixes expected by the platform
SIZES = {
    'big_': (800, 800),
    'original/': (600, 600),
    'thumb_': (300, 300),
    'icon_': (100, 100),
}

USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'


def download_image(url):
    """Download image and return PIL Image."""
    req = Request(url, headers={'User-Agent': USER_AGENT})
    with urlopen(req, timeout=30) as resp:
        data = resp.read()
    return Image.open(io.BytesIO(data))


def resize_image(img, max_size, output_format='JPEG'):
    """Resize image maintaining aspect ratio, return bytes."""
    img_copy = img.copy()
    # Convert RGBA to RGB for JPEG
    if img_copy.mode in ('RGBA', 'P') and output_format == 'JPEG':
        background = Image.new('RGB', img_copy.size, (255, 255, 255))
        if img_copy.mode == 'P':
            img_copy = img_copy.convert('RGBA')
        background.paste(img_copy, mask=img_copy.split()[3] if img_copy.mode == 'RGBA' else None)
        img_copy = background

    img_copy.thumbnail(max_size, Image.LANCZOS)
    buf = io.BytesIO()
    if output_format == 'JPEG':
        img_copy.save(buf, 'JPEG', quality=85, optimize=True)
    else:
        img_copy.save(buf, 'PNG', optimize=True)
    buf.seek(0)
    return buf


def main():
    # Connect FTP
    ftp = ftplib.FTP(FTP_HOST)
    ftp.login(FTP_USER, FTP_PASS)
    ftp.set_pasv(False)

    # Connect DB
    conn = pymssql.connect(DB_SERVER, DB_USER, DB_PASS, DB_NAME)
    cursor = conn.cursor()

    for uid, info in PRODUCTS.items():
        print(f"\n--- ID={uid}: {info['filename']} ---")

        # Download
        try:
            img = download_image(info['url'])
            print(f"  Downloaded: {img.size[0]}x{img.size[1]} {img.mode}")
        except Exception as e:
            print(f"  DOWNLOAD ERROR: {e}")
            continue

        # Determine output format
        ext = info['filename'].rsplit('.', 1)[-1].lower()
        out_fmt = 'PNG' if ext == 'png' else 'JPEG'

        # Create directory on FTP
        upl_dir = f'/httpdocs/epanel/upl/{uid}'
        try:
            ftp.mkd(upl_dir)
            print(f"  Created dir: {upl_dir}")
        except:
            print(f"  Dir exists: {upl_dir}")

        # Upload 4 sizes
        for prefix, max_size in SIZES.items():
            resized = resize_image(img, max_size, out_fmt)
            remote_name = f"{prefix}{info['filename']}"
            remote_path = f"{upl_dir}/{remote_name}"
            try:
                ftp.storbinary(f'STOR {remote_path}', resized)
                size_kb = resized.getbuffer().nbytes / 1024
                print(f"  Uploaded: {remote_name} ({size_kb:.1f} KB)")
            except Exception as e:
                print(f"  UPLOAD ERROR {remote_name}: {e}")

        # Insert DB record (RESIM = filename only, without prefix)
        db_filename = info['filename']
        try:
            cursor.execute("""
                INSERT INTO URUNRESIMLERI (URUNID, RESIM, VARSAYILAN, ALTTAG, VARYANTALANID)
                VALUES (%s, %s, 1, %s, NULL)
            """, (uid, db_filename, info['alt']))
            print(f"  DB: URUNRESIMLERI inserted")
        except Exception as e:
            print(f"  DB ERROR: {e}")

    conn.commit()
    cursor.close()
    conn.close()
    ftp.quit()
    print("\nTamamlandı!")


if __name__ == '__main__':
    main()
