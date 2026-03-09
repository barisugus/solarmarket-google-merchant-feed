#!/usr/bin/env python3
"""
1. Create 'Dyness Lityum Pil' category
2. INSERT 6 Dyness products into URUNLER
3. INSERT URUNKATEGORILERI (2 cats each) + URUNSTOKDURUMLARI
4. UPDATE 5 Jinko product prices
"""
import pymssql

DB_SERVER = '37.148.209.147'
DB_USER = 'trSolarMarket.dogus.egebilgi'
DB_PASS = '3%DKveYq*6py0ntn'
DB_NAME = 'turkiyeSolarMarketDb'

# Dyness products to INSERT
# Pricing: Liste × 0.60 = ALIS, ALIS × 1.35 = FIYAT1, FIYAT1 × 1.22 = PIYASA
DYNESS_PRODUCTS = [
    {
        'name': 'Dyness Tower T10 HV 9.6 kWh Yüksek Gerilim Lityum Batarya',
        'sku': 'DYN-HV9637',
        'slug': 'dyness-tower-t10-hv-96-kwh-yuksek-gerilim-lityum-batarya',
        'alis': 810.0, 'fiyat1': 1093.50, 'piyasa': 1334.07,
    },
    {
        'name': 'Dyness Tower T10 BDU – Batarya Dağıtım Ünitesi',
        'sku': 'DYN-TOWER-BDU',
        'slug': 'dyness-tower-t10-bdu-batarya-dagitim-unitesi',
        'alis': 510.0, 'fiyat1': 688.50, 'piyasa': 839.97,
    },
    {
        'name': 'Dyness Tower T10 HV 10 kWh Yüksek Gerilim Lityum Batarya',
        'sku': 'DYN-HV9640',
        'slug': 'dyness-tower-t10-hv-10-kwh-yuksek-gerilim-lityum-batarya',
        'alis': 846.0, 'fiyat1': 1142.10, 'piyasa': 1393.36,
    },
    {
        'name': 'Dyness Tower Pro T10 BDU – Batarya Dağıtım Ünitesi',
        'sku': 'DYN-TOWER-PRO-BDU',
        'slug': 'dyness-tower-pro-t10-bdu-batarya-dagitim-unitesi',
        'alis': 540.0, 'fiyat1': 729.0, 'piyasa': 889.38,
    },
    {
        'name': 'Dyness BX51100 51.2V 100Ah Ticari Lityum Batarya',
        'sku': 'DYN-S51100',
        'slug': 'dyness-bx51100-512v-100ah-ticari-lityum-batarya',
        'alis': 990.0, 'fiyat1': 1336.50, 'piyasa': 1630.53,
    },
    {
        'name': 'Dyness BX51100 BDU – Ticari Batarya Dağıtım Ünitesi',
        'sku': 'DYN-SBDU100',
        'slug': 'dyness-bx51100-bdu-ticari-batarya-dagitim-unitesi',
        'alis': 978.0, 'fiyat1': 1320.30, 'piyasa': 1610.77,
    },
]

# Jinko price updates (ALISFIYATI, FIYAT1, PIYASAFIYATI)
JINKO_UPDATES = [
    (1521, 1380.0, 1863.0, 2272.86),
    (1522, 1422.0, 1919.70, 2342.03),
    (1523, 1500.0, 2025.0, 2470.50),
    (1524, 1790.40, 2417.04, 2948.79),
    (1525, 1989.60, 2685.96, 3276.87),
]

def main():
    conn = pymssql.connect(DB_SERVER, DB_USER, DB_PASS, DB_NAME)
    cursor = conn.cursor()

    # =========================================
    # 1. Create Dyness Lityum Pil category
    # =========================================
    print("--- 1. KATEGORİ OLUŞTUR ---")
    cursor.execute("SELECT ID FROM KATEGORILER WHERE SEF_URL = 'dyness-lityum-pil/'")
    row = cursor.fetchone()
    if row:
        dyness_kat_id = row[0]
        print(f"Zaten mevcut: ID={dyness_kat_id}")
    else:
        cursor.execute("""
            INSERT INTO KATEGORILER (KATEGORI, AKTIF, ACIKLAMA, SIRA, SEF_URL,
                PAGE_TITLE, META_KEYWORDS, META_DESCRIPTION,
                UST_KATEGORI_ID, FILTRASYONGRUPID, GORUNTULENMESAYISI,
                ENTEGREKODU, BANNER, DETAY, SEPET_INDIRIMI_AKTIF, SEPET_INDIRIMI_ORAN)
            VALUES (
                'Dyness Lityum Pil', 1, 'Dyness enerji depolama bataryalari', 0,
                'dyness-lityum-pil/',
                'Dyness Lityum Pil Fiyatlari | Turkiye Solar Market',
                'dyness, lityum pil, batarya, enerji depolama',
                'Dyness lityum pil ve enerji depolama bataryalari en uygun fiyatlarla Turkiye Solar Markette.',
                NULL, NULL, 0, '', NULL, NULL, 0, 0
            )
        """)
        conn.commit()
        cursor.execute("SELECT ID FROM KATEGORILER WHERE SEF_URL = 'dyness-lityum-pil/'")
        dyness_kat_id = cursor.fetchone()[0]
        print(f"Oluşturuldu: ID={dyness_kat_id}")

    # =========================================
    # 2. INSERT Dyness products
    # =========================================
    print("\n--- 2. DYNESS ÜRÜN INSERT ---")
    inserted_ids = []
    for p in DYNESS_PRODUCTS:
        cursor.execute("""
            INSERT INTO URUNLER (
                URUNADI, STOKKODU, ENTEGREKODU, RAPORKODU,
                STOK, KARGOAGIRLIGI, ETIKETLER, DOVIZTIPI,
                KDVORANI, KDV, PIYASAFIYATI, FIYAT1,
                FIYAT2, FIYAT3, FIYAT4, FIYAT5,
                URUNDETAY, ANASAYFAVITRINI, MARKAID, STOKDURUMUID,
                METAKEYWORDS, METADESCRIPTION, PAGETITLE,
                URUNGRUPID, URUNACIKLAMASI,
                ANASAYFAVITRINSIRASI, VARYANTGRUPID,
                ANASAYVAVITRINVARYANTID,
                SIRA, ALISFIYATI, GORUNTULENMESAYISI,
                SATILMASAYISI, SEO_AYAR, OLCUBIRIMI,
                MATRISGRUPID, MESAJ, URUNGRUPID2,
                DETAY_YEDEK_1, DETAY_YEDEK_2, DETAY_YEDEK_3,
                DETAY_YEDEK_4, DETAY_YEDEK_5,
                MATRISGORUNUMU, VARYANTGORUNUMU,
                STOKTAKIBI, MAXSIPARISMIKTARI, MAXSIPARISMIKTARIAKTIF
            ) VALUES (
                %s, %s, '', '',
                1, 0, %s, 'EUR',
                20, 0, %s, %s,
                0, 0, 0, 0,
                '', 0, 96, 4,
                %s, %s, %s,
                NULL, %s,
                0, NULL,
                NULL,
                999, %s, 0,
                0, 1, 'Adet',
                NULL, 1, NULL,
                '', '', '',
                '', '',
                1, 1,
                0, 0, 0
            )
        """, (
            p['name'], p['sku'],
            f"dyness, lityum batarya, {p['sku']}",
            p['piyasa'], p['fiyat1'],
            f"dyness, lityum pil, batarya, enerji depolama, {p['sku']}",
            f"{p['name']} en uygun fiyatlarla Turkiye Solar Market'te. Hemen siparis verin.",
            f"{p['name']} Fiyati | Turkiye Solar Market",
            p['name'],
            p['alis'],
        ))
        # Get the inserted ID
        cursor.execute("SELECT @@IDENTITY")
        new_id = int(cursor.fetchone()[0])
        inserted_ids.append((new_id, p))
        print(f"  OK: ID={new_id} SKU={p['sku']} FIYAT1={p['fiyat1']}")
    conn.commit()
    print(f"  {len(inserted_ids)} ürün eklendi")

    # =========================================
    # 3. URUNKATEGORILERI + URUNSTOKDURUMLARI
    # =========================================
    print("\n--- 3. KATEGORİ + STOK KAYITLARI ---")
    for uid, p in inserted_ids:
        slug = p['slug']
        # Two categories: Dyness Lityum Pil + Solar Malzemeler (64)
        for kid, kat_sef in [(dyness_kat_id, 'dyness-lityum-pil'), (64, 'solar-malzemeler')]:
            sefurl = f"{kat_sef}/{slug}"
            cursor.execute("""
                INSERT INTO URUNKATEGORILERI (URUNID, KATEGORIID, VITRIN, SEFURL, VITRINVARYANTID)
                VALUES (%s, %s, 1, %s, NULL)
            """, (uid, kid, sefurl))
            print(f"  KAT: URUNID={uid} → KAT={kid} SEF={sefurl}")

        # URUNSTOKDURUMLARI
        cursor.execute("""
            INSERT INTO URUNSTOKDURUMLARI (URUNID, STOKDURUMUID)
            VALUES (%s, 4)
        """, (uid,))
        print(f"  STOK: URUNID={uid} → STOKDURUMUID=4")
    conn.commit()

    # =========================================
    # 4. Jinko price updates
    # =========================================
    print("\n--- 4. JINKO FİYAT UPDATE ---")
    for uid, alis, fiyat1, piyasa in JINKO_UPDATES:
        cursor.execute("""
            UPDATE URUNLER SET ALISFIYATI=%s, FIYAT1=%s, PIYASAFIYATI=%s
            WHERE ID=%s
        """, (alis, fiyat1, piyasa, uid))
        print(f"  OK: ID={uid} ALIS={alis} FIYAT1={fiyat1} PIYASA={piyasa}")
    conn.commit()

    # =========================================
    # 5. Verify
    # =========================================
    print("\n--- 5. DOĞRULAMA ---")
    all_ids = [uid for uid, _ in inserted_ids] + [1521,1522,1523,1524,1525]
    id_list = ','.join(str(i) for i in all_ids)
    cursor.execute(f"""
        SELECT u.ID, u.STOKKODU, u.ALISFIYATI, u.FIYAT1, u.PIYASAFIYATI, u.STOK, u.DOVIZTIPI,
               (SELECT COUNT(*) FROM URUNKATEGORILERI uk WHERE uk.URUNID = u.ID) as kat_count,
               (SELECT COUNT(*) FROM URUNSTOKDURUMLARI us WHERE us.URUNID = u.ID) as stok_count
        FROM URUNLER u
        WHERE u.ID IN ({id_list})
        ORDER BY u.ID
    """)
    for row in cursor.fetchall():
        status = "✓" if row[7] > 0 else "✗"
        print(f"  {status} ID={row[0]} SKU={row[1]} ALIS={row[2]} FIYAT1={row[3]} PIYASA={row[4]} STOK={row[5]} DOV={row[6]} KAT={row[7]} STOKDUR={row[8]}")

    # SEFURL check
    print("\n--- SEFURL KONTROL ---")
    dyness_ids = ','.join(str(uid) for uid, _ in inserted_ids)
    cursor.execute(f"""
        SELECT uk.URUNID, uk.KATEGORIID, uk.VITRIN, uk.SEFURL
        FROM URUNKATEGORILERI uk
        WHERE uk.URUNID IN ({dyness_ids})
        ORDER BY uk.URUNID, uk.KATEGORIID
    """)
    for row in cursor.fetchall():
        print(f"  URUNID={row[0]} KAT={row[1]} VITRIN={row[2]} SEF={row[3]}")

    cursor.close()
    conn.close()
    print("\nTamamlandı!")

if __name__ == '__main__':
    main()
