#!/usr/bin/env python3
"""
Ürün Görseli Toplama + FTP Upload + DB Insert
193 yeni ürün için (BYD 2, Solis 42, Deye 35, Solinved 114)

Solinved.com, deyeinverter.com, solisinverters.com, bydbatterybox.com
kaynaklarından görsel indirir, FTP ile sunucuya yükler, DB'ye kaydeder.

Usage:
  python3 image_collector.py                # dry-run: eşleştirmeyi göster
  python3 image_collector.py --download     # görselleri indir (local)
  python3 image_collector.py --upload       # FTP upload + DB insert
"""

import argparse
import os
import re
import sys
import time
from ftplib import FTP
from io import BytesIO
from pathlib import Path
from urllib.parse import urljoin

import pymssql
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).parent
load_dotenv(SCRIPT_DIR / ".env")

IMAGE_DIR = SCRIPT_DIR / "extracted_images" / "product_images"
BASE_SOLINVED = "https://www.solinved.com"

# ═══════════════════════════════════════════════════════════════
# SOLINVED ÜRÜN → GÖRSEL EŞLEŞTİRME (solinved.com'dan crawl edildi)
# Anahtar: bizim STOKKODU, Değer: (solinved_page_url, image_path)
# ═══════════════════════════════════════════════════════════════
SOLINVED_IMAGE_MAP = {
    # GORDION SERIES — MPPT Off-Grid
    "SLV-3600-24": ("/3-6-kw-gordion-serisi-mppt-off-grid-inverter", "68d692556eca4175889262957"),
    "SLV-5000-24": ("/5-0-kw-gordion-serisi-mppt-off-grid-invertor", "68d692df6a637175889276744"),
    "SLV-5000-48": ("/5-0-kw-gordion-serisi-mppt-off-grid-invertor-48v", "68d692fb046e9175889279541"),
    "SLV-6000-48": ("/6-0-kw-gordion-serisi-mppt-off-grid-invertor", "68d6930292ac0175889280269"),
    # SLV-1200-12 Gordion 1.2kW — site'de yok, 3.6kW görseli kullanılacak (aynı seri)
    "SLV-1200-12": ("/3-6-kw-gordion-serisi-mppt-off-grid-inverter", "68d692556eca4175889262957"),
    # SLV-6500-48 — site'de yok, 6.0kW görseli kullanılacak (aynı seri)
    "SLV-6500-48": ("/6-0-kw-gordion-serisi-mppt-off-grid-invertor", "68d6930292ac0175889280269"),
    # MAX SERIES
    "MAX-8.2": ("/8-2-kw-max-serisi-mppt-off-grid-invertor", "67458833da68c173261009995"),
    # NML SERIES
    "NML-2000-12": ("/1-6-kw-nml-serisi-mppt-off-grid-invertor", "674587bdbd1f9173260998127"),
    # PS PLUS — site'de yok, NML görseli kullanılacak
    "PS-PLUS-1K": ("/1-6-kw-nml-serisi-mppt-off-grid-invertor", "674587bdbd1f9173260998127"),
    # ASPENDOS
    "ASPENDOS-INV": ("/aspendos-serisi-all-in-one-batarya-modulu-5kwh", "6953b35657b50176709307835"),
    "ASPENDOS-BAT": ("/aspendos-serisi-all-in-one-batarya-modulu-5kwh", "6953b35657b50176709307835"),
    # PURE SINE INVERTERS
    "SLVP600": ("/600w-tam-sinus-inverter-12v", "67457f445f4e3173260781236"),
    "SLVP1000": ("/1000w-tam-sinus-inverter-12v", "67457ecec8aa3173260769427"),
    "SLVP1500": ("/1500w-tam-sinus-inverter-12v", "6745796541f88173260630986"),
    "SLVP2000": ("/2000w-tam-sinus-inverter-12v", "67457e2f66870173260753590"),
    "SLVP2500": ("/2500w-tam-sinus-invertor-12v", "674589a3330fa173261046746"),
    "SLVP3000": ("/3000w-tam-sinus-inverter-12v", "67457e78b21e4173260760853"),
    "SLVP4000": ("/4000w-tam-sinus-inverter-12v", "67581a46eec6c173382714261"),
    "SLVP1500-24": ("/1500w-tam-sinus-inverter-24v", "67922550831f2173763105663"),
    "SLVP3000-24": ("/3000w-modifiye-sinus-inverter-24v", "67459f09a3b65173261594553"),  # closest match
    # PURE SINE UPS
    "SLVU600": ("/600w-tam-sinus-ups-sarjli-invertor-12v", "674579a1a6601173260636978"),
    "SLVU1000": ("/1000w-tam-sinus-ups-sarjli-invertor-12v", "67457840acae7173260601624"),
    "SLVU1500": ("/1500w-tam-sinus-ups-sarjli-invertor-12v", "674578f0c403f173260619268"),
    # MODIFIED SINE
    "SLVM300": ("/300w-modifiye-sinus-inverter-12v", "67457749bd3e0173260576968"),
    "SLVM600": ("/600w-modifiye-sinus-inverter-12v", "674582ab0bbc8173260868383"),
    "SLVM1000": ("/1000w-modifiye-sinus-inverter-12v", "674587720e736173260990642"),
    "SLVM1500": ("/1500w-modifiye-sinus-inverter-12v", "674577c6d861a173260589468"),
    "SLVM2000": ("/2000w-modifiye-sinus-inverter-12v", "67457806e91aa173260595880"),
    "SLVM2500": ("/2500w-modifiye-sinus-inverter-12v", "6745893e096dc173261036645"),
    "SLVM1500-24": ("/1500w-modifiye-sinus-inverter-24v", "67459f3eedc3e173261599876"),
    "SLVM3000-24": ("/3000w-modifiye-sinus-inverter-24v", "67459f09a3b65173261594553"),
    # MPPT CHARGE CONTROLLERS
    "SOL-MPPT320D": ("/20a-mppt-sarj-kontrol-cihazi", "674445494c6dc173252743314"),
    "SOL-MPPT330D": ("/30a-mppt-sarj-kontrol-cihazi", "674445a3f0a42173252752319"),
    "SOL-MPPT340D": ("/40a-mppt-sarj-kontrol-cihazi", "674445f1a781a173252760137"),
    "SOL-MPK60": ("/60a-mppt-sarj-kontrol-cihazi-12v-24v-48v", "67456d4fe97e4173260321545"),
    "SOL-MPK80": ("/80a-mppt-sarj-kontrol-cihazi-12v-24v-48v", "67456d80c5e20173260326466"),
    "SOL-MPK100": ("/100a-mppt-sarj-kontrol-cihazi-12v-24v-48v", "67456dbfb7312173260332737"),
    # PWM CHARGE CONTROLLERS (LT series)
    "SOL-LT10-1024": ("/10a-pwm-sarj-kontrol-cihazi", "674447306feb2173252792027"),
    "SOL-LT20-2024": ("/20a-pwm-sarj-kontrol-cihazi", "674447cc4c43e173252807688"),
    "SOL-LT30-3024": ("/30a-pwm-sarj-kontrol-cihazi", "67652cbcd88a9173468383677"),
    "SOL-LT40-4024": ("/40a-pwm-sarj-kontrol-cihazi", "6744485d0e4b2173252822119"),
    # GEL BATTERIES
    "SOL12-100": ("/12v-100-ah-jel-aku", "67457be1e15d6173260694519"),
    "SOL12-150": ("/12v-150-ah-jel-aku", "67457c13e3b3b173260699528"),
    "SOL12-200": ("/12v-200-ah-jel-aku", "67457d0ab9de0173260724271"),
    # LITHIUM BATTERIES
    "SOL-1280": ("/12-8-v-100ah-lityum-aku", "68a49008c455a175561524017"),
    "SOL-2560": ("/25-6-v-100ah-lityum-aku", "68a490c24d387175561542682"),
    "SOL-5100-HV-LV": ("/5-1-kwh-100ah-hv-kapadokya-serisi-lityum-aku", "691c33a4ae499176345590864"),
    "SOL-WL-15": ("/15-36-kwh-300ah-wl-15-lityum-iyon-aku", "6800d32769f7a174488451981"),
    "SOL-XH": ("/10-24-kwh-lityum-batarya-modulu", "6825ead95bf56174731541754"),
    "SOL-XH-CONTROLBOX": ("/10-24-kwh-lityum-batarya-modulu", "6825ead95bf56174731541754"),  # same series
    "SOL-LITHIUM-CABLE": ("/5-1-kwh-100ah-hv-kapadokya-serisi-lityum-aku", "691c33a4ae499176345590864"),  # generic
    # CIRCUIT BREAKERS (DC Salter)
    "SOLM3DC-80": ("/80a-dc-salter", "6765687af1397173469913015"),
    "SOLM3DC-100": ("/100a-dc-salter", "6765681704db5173469903170"),
    "SOLM3DC-125": ("/125a-dc-salter", "676567d00300a173469896015"),
    "SOLM3DC-200": ("/200a-dc-salter", "676567843fda8173469888478"),
    "SOLM3DC-250": ("/315a-dc-salter", "6765672db193a173469879787"),  # closest
    "SOLM3DC-315": ("/315a-dc-salter", "6765672db193a173469879787"),
    "SOLM3DC-350": ("/350a-dc-salter", "676566cd6c6f6173469870176"),
    # DC FUSES
    "SLVFS-16": ("/16a-solar-pv-dc-sigorta", "67456bada843d173260279765"),
    "SLVFS-32": ("/32a-solar-pv-dc-sigorta", "67456bda9ee5d173260284222"),
    "SLVFSHL": ("/dc-kartus-sigorta-yuvasi", "67456b66de41c173260272629"),
    # MC4 CONNECTORS
    "SOL-MC4-1000": ("/mc4-konnektor-seti", "67456a921b1ed173260251498"),
    "SOL-MC4H-1500": ("/1500v-mc4-konnektor-seti", "6745761410505173260546019"),
    "SOL-MC4-KIT": ("/mc4-konnektor-sikma-pensesi-seti", "674576587f7f6173260552848"),
    # SOLAR MOUNTING
    "KONST-2X15": ("/2x15-sehpa-konstruksiyon-seti", "6745a282dcf17173261683486"),
    "KONST-2X10": ("/2x10-sehpa-konstruksiyon-seti", "6745a23b368eb173261676327"),
    "KONST-2X9": ("/2x9-sehpa-konstruksiyon-seti", "6745a3529b189173261704262"),
    "KONST-2X8": ("/2x8-sehpa-konstruksiyon-seti", "6745a32b67d4e173261700316"),
    "KONST-2X7": ("/2x7-sehpa-konstruksiyon-seti", "6745a2e48f8cf173261693233"),
    "KONST-2X5": ("/2x5-sehpa-konstruksiyon-seti", "6874e8f8de963175249228092"),
    "KONST-2X4": ("/2x4-sehpa-konstruksiyon-seti", "6745a2a94f8a1173261687327"),
    # EV CHARGERS — site'de ürün yok, generic kullanılacak
    "SOL-EV-ANGORA-22": (None, None),
    "SOL-EV-RADIUS-22": (None, None),
    # PUMP DRIVERS - 1x220V (Monofaze)
    "SOL-CDI-SPDG1R5-SS2": ("/1-5-kw-2-hp-monofaze-1x220-solar-pompa-surucu", "67457de1e87d9173260745780"),
    "SOL-CDI-SPDG2R2-SS2": ("/2-2-kw-3-hp-monofaze-1x220-solar-pompa-surucu", "6745897ae49d4173261042682"),
    "SOL-CDI-SPDG4R0-SS2": ("/4-kw-5-5-hp-monofaze-1x220-solar-pompa-surucu", "674589d1b2f1e173261051393"),
    # PUMP DRIVERS - 3x220V
    "SOL-CDI-SPDG2R2-S2": ("/2-2-kw-3-hp-monofaze-3x220-solar-pompa-surucu", "674576a214d0c173260560265"),
    "SOL-CDI-SPDG4R0-S2": ("/4-kw-5-5-hp-monofaze-3x220-solar-pompa-surucu", "674588fe036a9173261030276"),
    # PUMP DRIVERS - 3x380V
    "SOL-CDI-SPDG1R5T4": ("/1-5-kw-2-hp-trifaze-solar-pompa-surucu", "67443f94a864e173252597240"),
    "SOL-CDI-SPDG2R2T4": ("/2-2-kw-3-hp-trifaze-solar-pompa-surucu", "682741bcea030174740319669"),
    "SOL-CDI-SPDG4R0T4": ("/4-kw-5-5-hp-trifaze-solar-pompa-surucu", "6827419d3151f174740316596"),
    "SOL-CDI-SPDG5R5T4": ("/5-5-kw-7-5-hp-trifaze-solar-pompa-surucu", "682741878559e174740314396"),
    "SOL-CDI-SPDG7R5T4": ("/7-5-kw-10-hp-trifaze-solar-pompa-surucu", "68274179ea970174740312989"),
    "SOL-CDI-SPDG011T4": ("/11-kw-15-hp-trifaze-solar-pompa-surucu", "6827415aeaedb174740309810"),
    "SOL-CDI-SPDG015T4": ("/15-kw-20-hp-trifaze-solar-pompa-surucu-900v", "68274213142bf174740328336"),
    "SOL-CDI-SPDG018T4": ("/18-5-kw-25-hp-trifaze-solar-pompa-surucu", "682737782560c174740056877"),
    "SOL-CDI-SPDG022T4": ("/22-kw-30-hp-trifaze-solar-pompa-surucu", "68273757a745d174740053522"),
    "SOL-CDI-SPDG030T4": ("/30-kw-40-hp-trifaze-solar-pompa-surucu", "6827372b59f4a174740049115"),
    "SOL-CDI-SPDG037T4": ("/37-kw-50-hp-trifaze-solar-pompa-surucu", "68273709b9f0f174740045741"),
    "SOL-CDI-SPDG045T4": ("/45-kw-60-hp-trifaze-solar-pompa-surucu", "682736ea18c3d174740042696"),
    "SOL-CDI-SPDG055T4": ("/55-kw-75-hp-trifaze-solar-pompa-surucu", "682736cf4a048174740039947"),
    "SOL-CDI-SPDG075T4": ("/75-kw-100-hp-trifaze-solar-pompa-surucu", "682736b015b91174740036893"),
    "SOL-CDI-SPDG090T4": ("/90-kw-120-hp-trifaze-solar-pompa-surucu", "6827368620287174740032685"),
    "SOL-CDI-SPDG110T4": ("/110-kw-150-hp-trifaze-solar-pompa-surucu", "68273665ad9ad174740029339"),
    # PUMP DRIVER PANELS
    "DKP-TIP1-PANO": ("/dkp-tip1-pano-1-5-kw-5-5-kw", "674573bb0980d173260485942"),
    "DKP-TIP2-PANO": ("/dkp-tip2-pano-7-5-kw-15-kw", "674573fc5f818173260492452"),
    "DKP-TIP3-PANO": ("/dkp-tip3-pano-18-5-kw-22-kw", "6745743caef10173260498835"),
    "DKP-TIP4-PANO": ("/dkp-tip4-pano-30-kw-37-kw", "674574cb0dea1173260513152"),
    "DKP-TIP5-PANO": ("/dkp-tip5-pano-45kw-55-kw", "67457ff6e8668173260799074"),
    # SOLAR CAMERAS
    "CM26-4G": ("/gunes-enerjili-ptz-4g-kamera-cm-26", "6798902ec863f173805163045"),
    "CM04-WIFI": ("/gunes-enerjili-akilli-ptz-wifi-kamera-cm-04", "679891efc7e87173805207918"),
    "CM27-4G": ("/gunes-enerjili-ptz-4g-kamera-10k-zoom-cm-27", "679890c60f9bc173805178273"),
    "CM04-4G": ("/gunes-enerjili-akilli-ptz-4g-kamera-cm-04", "679891633b1a7173805193979"),
    "CM22-WIFI": ("/gunes-enerjili-akilli-ptz-wifi-kamera-cm-22", "6798957b3430d173805298769"),
    "CM09-4G": ("/cift-lensli-gunes-enerjili-ptz-hd-kamera-cm-09", "67988f8b383bc173805146792"),
    "CM22-4G": ("/gunes-enerjili-akilli-ptz-4g-kamera-cm-22", "679895240db24173805290087"),
    "L8-4G": ("/l8-solar-router", "679b6f552eb58173823982957"),
    # LEAD ACID BATTERIES
    "SOL-12-7": ("/12v-7ah-ups-ve-alarm-akusu", "677e752c4cdb2173634078065"),
    "SOL-12-7-PREMIUM": ("/12v-7-ah-ups-ve-alarm-akusu-premium", "677e758bd197e173634087565"),
    "SOL-12-9": ("/12v-9ah-ups-ve-alarm-akusu", "677e7687c0667173634112728"),
    "SOL-12-12": ("/12v-12ah-ups-ve-alarm-akusu", "677e76d826d1f173634120828"),
    # E-BIKE BATTERIES
    "SOL-12-14": ("/12v-14ah-vrla-tipi-elektrikli-bisiklet-akusu", "677e71369e137173633976630"),
    "SOL-12-24": ("/12v-24ah-vrla-tipi-elektrikli-bisiklet-akusu", "677e71b967f75173633989780"),
    "SOL-12-24-PREMIUM": ("/12v-24ah-vrla-type-elektrikli-bisiklet-akusu-premium", "677e71f93d25a173633996112"),
}

# ═══════════════════════════════════════════════════════════════
# DEYE — deyeinverter.com'dan veya solinved.com'dan
# ═══════════════════════════════════════════════════════════════
DEYE_IMAGE_MAP = {
    # MONO PHASE ON-GRID — solinved.com'da "Deye X kW Monofaz On-Grid String"
    "SUN-3K-MONO": ("/3-kw-monofaz-on-grid-string-invertor", "678a13cd3ef82173710228513"),
    "SUN-5K-MONO": ("/5-kw-monofaz-on-grid-string-invertor", "67459ffa0c01e173261618611"),
    "SUN-8K-MONO": ("/8-kw-monofaz-on-grid-string-invertor", "6745a0344c779173261624469"),
    "SUN-10K-MONO": ("/10-kw-monofaz-on-grid-string-invertor", "6745a098517d1173261634437"),
    # THREE PHASE ON-GRID
    "SUN-5K-G06P3-EU-AM2": ("/5-kw-trifaz-on-grid-string-invertor", "6745a0c769814173261639164"),
    "SUN-8K-G06P3-EU-AM2": ("/8-kw-trifaz-on-grid-string-invertor", "6745a0f344660173261643546"),
    "SUN-10K-G06P3-EU-AM2": ("/10-kw-trifaz-on-grid-string-invertor", "6745a116832ed173261647045"),
    "SUN-12K-G06P3-EU-AM2": ("/12-kw-trifaz-on-grid-string-invertor", "678e6b3adf6b1173738681074"),
    "SUN-15K-G05": ("/15-kw-trifaz-on-grid-string-invertor", "6745a1710f367173261656169"),
    "SUN-20K-G05": ("/20-kw-trifaz-on-grid-string-invertor", "6745a14770b0b173261651917"),
    "SUN-25K-G04": ("/25-kw-trifaz-on-grid-string-invertor", "6745a7752e6c5173261810191"),
    "SUN-30K-G04": ("/30-kw-trifaz-on-grid-string-invertor", "6745a3ca4c81f173261716213"),
    "SUN-40K-G04": ("/40-kw-trifaz-on-grid-string-invertor", "6745a4a4d43c5173261738096"),
    # HYBRID LV — solinved.com Deye hibrit sayfasından
    "SUN-5K-SG03LP1-EU": ("/5-kw-monofaz-lv-hibrit-invertor", "6745a50994d24173261748146"),
    "SUN-6K-SG03LP1-EU": ("/6-kw-monofaz-lv-hibrit-invertor", "6745a7970e611173261813552"),
    "SUN-10K-SG02LP1-EU": ("/10-kw-monofaz-lv-hibrit-invertor", "695f95d9ef0b7176787196170"),
    "SUN-16K-SG01LP1-EU": ("/16-kw-monofaz-lv-hibrit-invertor", "686e174a2ed13175204538671"),
    "SUN-8K-SG04LP3-EU": ("/8-kw-trifaz-lv-hibrit-invertor", "6745a7c76102d173261818384"),
    "SUN-10K-SG04LP3-EU": ("/10-kw-trifaz-lv-hibrit-invertor", "6745a55486e97173261755694"),
    "SUN-12K-SG04LP3-EU": ("/12-kw-lv-trifaz-hibrit-invertor", "6745a716c253a173261800622"),
    "SUN-15K-SG05LP3-EU-SM2": ("/15-kw-trifaz-lv-hibrit-invertor", "678a7411f20c0173712692950"),
    "SUN-20K-SG05LP3-EU-SM2": ("/15-kw-trifaz-lv-hibrit-invertor", "678a7411f20c0173712692950"),  # closest LV
    # HYBRID HV
    "SUN-10K-SG01HP3-EU": ("/10-kw-trifaz-hv-hibrit-invertor", "6745a7464c75f173261805481"),
    "SUN-12K-SG01HP3-EU": ("/12-kw-hv-hibrit-invertor", "6745a8ee2ba8d173261847879"),
    "SUN-15K-SG01HP3-EU": ("/15-kw-trifaz-hv-hibrit-invertor", "6745a7f426d3e173261822848"),
    "SUN-20K-SG01HP3-EU": ("/15-kw-trifaz-hv-hibrit-invertor", "6745a7f426d3e173261822848"),  # closest
    "SUN-25K-SG01HP3-EU-AM2": ("/40-kw-trifaze-hv-hibrit-invertor", "686b6eebb0c8f175187121186"),  # closest HV
    "SUN-30K-SG01HP3-EU-BM3": ("/40-kw-trifaze-hv-hibrit-invertor", "686b6eebb0c8f175187121186"),
    "SUN-40K-SG01HP3-EU-BM3": ("/40-kw-trifaze-hv-hibrit-invertor", "686b6eebb0c8f175187121186"),
    "SUN-50K-SG05LP3-EU-SM2": ("/40-kw-trifaze-hv-hibrit-invertor", "686b6eebb0c8f175187121186"),
    "SUN-80K-SG05LP3-EU-SM3": ("/40-kw-trifaze-hv-hibrit-invertor", "686b6eebb0c8f175187121186"),
    # ACCESSORIES — smart meter / wifi / lan
    "DEYE-WIFI-STICK": (None, None),   # web'den aranacak
    "DEYE-LAN-STICK": (None, None),
    "DEYE-SMART-METER-1P": ("/smart-meter-monofaz-akim-trafosu-dahil", "67457589ebf98173260532173"),
    "DEYE-SMART-METER-3P": ("/smart-meter-monofaz-akim-trafosu-dahil", "67457589ebf98173260532173"),  # same image
}

# ═══════════════════════════════════════════════════════════════
# SOLIS — solinved.com'dan (Solis ürünleri Solinved distribütör)
# ═══════════════════════════════════════════════════════════════
SOLIS_IMAGE_MAP = {
    # MONO PHASE ON-GRID — solinved.com/on-grid-invertorler
    "Solis-Mini-1500-4G-DC": ("/1-5-kw-monofaze-on-grid-invertor", "674458468f5b3173253229437"),
    "Solis-Mini-3000-4G-DC": ("/3-kw-monofaze-on-grid-invertor", "674573178a0a1173260469511"),
    "Solis-1P3K-4G-DC": ("/3-kw-monofaze-on-grid-invertor", "6792594d9309b173764436579"),  # Solis variant
    "Solis-1P4K-4G-DC": ("/4-kw-monofaze-on-grid-invertor", "6744597c2e4cc173253260412"),
    "Solis-1P5K-4G-DC": ("/5-kw-monofaze-on-grid-invertor", "67652c9353dd7173468379521"),
    "Solis-1P6K-4G-DC": ("/6-kw-monofaze-on-grid-invertor", "674466948c2f5173253595613"),
    # THREE PHASE ON-GRID
    "Solis-3P3K-4G-DC": ("/3-kw-trifaze-on-grid-invertor", "67925b229457d173764483418"),
    "Solis-3P5K-4G-DC": ("/5-kw-trifaze-on-grid-invertor", "674466d27497c173253601887"),
    "Solis-3P8K-4G-DC": ("/8-kw-trifaze-on-grid-invertor", "67446749616de173253613738"),
    "Solis-3P10K-4G-DC": ("/10-kw-trifaze-on-grid-invertor", "6744678f52213173253620713"),
    "Solis-3P15K-4G-DC": ("/15-kw-trifaze-on-grid-invertor", "674467fa8af8e173253631447"),
    "Solis-3P20K-4G-DC": ("/20-kw-trifaze-on-grid-invertor", "67446c7b688e8173253746787"),
    "S5-GC25K": ("/25-kw-trifaze-on-grid-invertor", "674470550dbb6173253845332"),
    "S5-GC30K": ("/30-kw-trifaze-on-grid-invertor", "6745687507483173260197370"),
    "S5-GC40K": ("/40-kw-trifaze-on-grid-invertor", "674568bc4efd6173260204448"),
    "Solis-GC-50K": ("/50-kw-trifaze-invertor", "67925d3310615173764536323"),
    "Solis-GC-60K": ("/60-kw-trifaze-on-grid-invertor", "67925e285987f173764560852"),
    # HYBRID — solinved.com Solis hibrit sayfasından
    "S6-EH1P5K-L-PLUS": ("/5-kw-trifaze-hibrit-invertor", "67459188371e8173261248861"),  # closest mono
    "S6-EH1P6K-L-PLUS": ("/5-kw-trifaze-hibrit-invertor", "67459188371e8173261248861"),
    "S6-EH1P8K-L-PLUS": ("/8-kw-hibrit-invertor", "6745915ab23be173261244249"),
    "S6-EH1P12K03-NV-YD-L": ("/10-kw-hibrit-invertor", "674590a46137b173261226060"),
    "S6-EH1P16K03-NV-YD-L": ("/10-kw-hibrit-invertor", "674590a46137b173261226060"),
    "S6-EH3P8K02-NV-YD-L": ("/8-kw-trifaze-hibrit-invertor-lv", "67933cf43598c173770264481"),
    "S6-EH3P10K02-NV-YD-L": ("/10-kw-trifaze-hibrit-invertor-lv", "67933e49916f2173770298526"),
    "S6-EH3P12K02-NV-YD-L": ("/12-kw-trifaze-hibrit-invertor-lv", "6793409fba332173770358399"),
    "S6-EH3P15K02-NV-YD-L": ("/15-kw-trifaze-hibrit-invertor-lv", "679346113bb4b173770497722"),
    "S6-EH3P5K-H-EU": ("/5-kw-trifaze-hibrit-invertor", "67459188371e8173261248861"),
    "S6-EH3P8K-H-EU": ("/8-kw-hibrit-invertor", "6745915ab23be173261244249"),
    "S6-EH3P10K-H-EU": ("/10-kw-hibrit-invertor", "674590a46137b173261226060"),
    "S6-EH3P12K-H-EU": ("/12-kw-trifaz-hibrit-invertor-hv", "6790e81930468173754984920"),
    "S6-EH3P15K-H-EU": ("/15-kw-trifaz-hibrit-invertor-hv", "6790daddaffad173754646192"),
    "S6-EH3P20K-H-EU": ("/20-kw-trifaz-hibrit-invertor-hv", "67d147b456f63174176862858"),
    "S6-EH3P30K-H-EU": ("/30-kw-trifaz-hibrit-invertor-hv", "6790df17c68a9173754754372"),
    "S6-EH3P40K-H-EU": ("/40-kw-trifaz-hibrit-invertor-hv", "6790e575d1ea3173754917344"),
    "S6-EH3P50K-H-EU": ("/40-kw-trifaz-hibrit-invertor-hv", "6790e575d1ea3173754917344"),
    # ACCESSORIES
    "S3-WiFi-ST": (None, None),  # web'den aranacak
    "Solis-DLB-WIFI": (None, None),
    "S2-WL-ST": (None, None),
    "Solis-EPM3-5G": (None, None),
    "Solis-EPM3-5G-PRO": (None, None),
    "Solis-Smart-Meter-1CT": ("/smart-meter-monofaz-akim-trafosu-dahil", "67457589ebf98173260532173"),
    "Solis-Smart-Meter-3CT": ("/smart-meter-monofaz-akim-trafosu-dahil", "67457589ebf98173260532173"),
}

# ═══════════════════════════════════════════════════════════════
# BYD — sadece 2 yeni ürün
# ═══════════════════════════════════════════════════════════════
BYD_IMAGE_MAP = {
    "BYD-HVS-5.1": (None, None),   # web'den aranacak
    "BYD-HVM-8.3": (None, None),
}

# Tüm mapları birleştir
ALL_IMAGE_MAP = {}
ALL_IMAGE_MAP.update(SOLINVED_IMAGE_MAP)
ALL_IMAGE_MAP.update(DEYE_IMAGE_MAP)
ALL_IMAGE_MAP.update(SOLIS_IMAGE_MAP)
ALL_IMAGE_MAP.update(BYD_IMAGE_MAP)


def get_db_connection():
    return pymssql.connect(
        server=os.getenv("MSSQL_SERVER"),
        port=int(os.getenv("MSSQL_PORT", "1433")),
        user=os.getenv("MSSQL_USER"),
        password=os.getenv("MSSQL_PASSWORD"),
        database=os.getenv("MSSQL_DATABASE"),
        charset="utf8",
    )


def get_products_without_images(conn):
    """DB'den resimsiz ürünleri al."""
    cur = conn.cursor(as_dict=True)
    cur.execute("""
        SELECT u.ID, u.URUNADI, u.STOKKODU, m.MARKA
        FROM URUNLER u
        JOIN MARKALAR m ON u.MARKAID = m.ID
        WHERE u.STOK > 0
          AND NOT EXISTS (SELECT 1 FROM URUNRESIMLERI r WHERE r.URUNID = u.ID)
        ORDER BY m.MARKA, u.ID
    """)
    rows = cur.fetchall()
    cur.close()
    return rows


def download_solinved_image(image_hash, sku):
    """Solinved.com'dan _400.webp görsel indir, jpg'ye çevir."""
    url = f"{BASE_SOLINVED}/assets/thumbnails/{image_hash}_400.webp"
    try:
        resp = requests.get(url, timeout=15, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
        })
        if resp.status_code == 200:
            return resp.content, "webp"
        # 400 versiyonu yoksa 250 dene
        url250 = f"{BASE_SOLINVED}/assets/thumbnails/{image_hash}_250.webp"
        resp = requests.get(url250, timeout=15, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
        })
        if resp.status_code == 200:
            return resp.content, "webp"
    except Exception as e:
        print(f"  HATA indirme {sku}: {e}")
    return None, None


def webp_to_jpg(webp_data):
    """WebP veriyi JPG'ye çevir."""
    from PIL import Image
    from io import BytesIO
    img = Image.open(BytesIO(webp_data))
    if img.mode in ('RGBA', 'P'):
        img = img.convert('RGB')
    buf = BytesIO()
    img.save(buf, format='JPEG', quality=85)
    return buf.getvalue()


def search_web_image(query, sku):
    """Bulunamayan ürünler için web'den ara (placeholder)."""
    # Bu fonksiyon şimdilik None döner, ileride genişletilebilir
    return None, None


def get_ftp_connection():
    """FTP bağlantısı aç (tek bağlantı, birçok dosya için kullanılır)."""
    ftp = FTP()
    ftp.encoding = 'latin-1'  # Windows server
    ftp.connect(os.getenv("MSSQL_SERVER"), 21)
    ftp.login(
        os.getenv("FTP_USER"),
        os.getenv("FTP_PASS"),
    )
    ftp.set_pasv(False)  # Aktif mod zorunlu!
    ftp.cwd("/httpdocs/epanel/upl")
    return ftp


def ftp_upload_image(ftp, jpg_data, filename, urun_id):
    """FTP ile sunucuya görsel yükle — /epanel/upl/{URUNID}/ dizinine.

    4 boyut yüklenir: original, big_, thumb_, icon_
    """
    from PIL import Image

    # Ürün klasörünü oluştur
    upl_dir = str(urun_id)
    try:
        ftp.mkd(upl_dir)
    except Exception:
        pass  # zaten var
    ftp.cwd(upl_dir)

    # Original boyut
    img = Image.open(BytesIO(jpg_data))
    if img.mode in ('RGBA', 'P'):
        img = img.convert('RGB')

    # big_ (600x600 max)
    big_img = img.copy()
    big_img.thumbnail((600, 600), Image.LANCZOS)
    big_buf = BytesIO()
    big_img.save(big_buf, format='JPEG', quality=85)
    big_buf.seek(0)
    ftp.storbinary(f"STOR big_{filename}", big_buf)

    # original (400x400 max — aynı zamanda listeleme görseli)
    orig_img = img.copy()
    orig_img.thumbnail((400, 400), Image.LANCZOS)
    orig_buf = BytesIO()
    orig_img.save(orig_buf, format='JPEG', quality=85)
    orig_buf.seek(0)
    ftp.storbinary(f"STOR {filename}", orig_buf)

    # thumb_ (200x200 max)
    thumb_img = img.copy()
    thumb_img.thumbnail((200, 200), Image.LANCZOS)
    thumb_buf = BytesIO()
    thumb_img.save(thumb_buf, format='JPEG', quality=85)
    thumb_buf.seek(0)
    ftp.storbinary(f"STOR thumb_{filename}", thumb_buf)

    # icon_ (50x50 max)
    icon_img = img.copy()
    icon_img.thumbnail((50, 50), Image.LANCZOS)
    icon_buf = BytesIO()
    icon_img.save(icon_buf, format='JPEG', quality=80)
    icon_buf.seek(0)
    ftp.storbinary(f"STOR icon_{filename}", icon_buf)

    # Geri dön
    ftp.cwd("..")
    return True


def insert_image_record(conn, urun_id, filename, alt_tag):
    """URUNRESIMLERI tablosuna görsel kaydı ekle."""
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO URUNRESIMLERI (URUNID, RESIM, VARSAYILAN, ALTTAG, VARYANTALANID)
        VALUES (%s, %s, 1, %s, NULL)
    """, (urun_id, filename, alt_tag))
    conn.commit()
    cur.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--download", action="store_true", help="Görselleri indir")
    parser.add_argument("--upload", action="store_true", help="FTP upload + DB insert")
    args = parser.parse_args()

    IMAGE_DIR.mkdir(parents=True, exist_ok=True)

    conn = get_db_connection()
    products = get_products_without_images(conn)
    print(f"Resimsiz ürün sayısı: {len(products)}\n")

    matched = 0
    unmatched = []
    download_ok = 0
    download_fail = 0
    upload_ok = 0
    ftp = None

    if args.upload:
        print("FTP bağlantısı açılıyor...")
        ftp = get_ftp_connection()
        print("FTP bağlantısı OK\n")

    for p in products:
        sku = p["STOKKODU"]
        urun_id = p["ID"]
        urun_adi = p["URUNADI"]
        marka = p["MARKA"]

        map_entry = ALL_IMAGE_MAP.get(sku)

        if map_entry is None:
            unmatched.append(f"  {marka} | {sku} | {urun_adi}")
            continue

        page_url, image_hash = map_entry
        if image_hash is None:
            unmatched.append(f"  {marka} | {sku} | {urun_adi} (görsel kaynağı yok)")
            continue

        matched += 1
        filename = f"{sku.lower().replace('.', '-').replace(' ', '-')}.jpg"

        if not args.download and not args.upload:
            # Dry run
            print(f"  ✓ {marka:<10} {sku:<30} → {image_hash[:20]}... → {filename}")
            continue

        # Download
        local_path = IMAGE_DIR / filename
        if local_path.exists() and local_path.stat().st_size > 1000:
            print(f"  ⏭ {sku} — zaten indirilmiş")
            jpg_data = local_path.read_bytes()
            download_ok += 1
        else:
            data, fmt = download_solinved_image(image_hash, sku)
            if data is None:
                print(f"  ✗ {sku} — indirilemedi")
                download_fail += 1
                continue

            jpg_data = webp_to_jpg(data) if fmt == "webp" else data
            local_path.write_bytes(jpg_data)
            download_ok += 1
            print(f"  ↓ {sku} — {len(jpg_data)//1024}KB indirildi")
            time.sleep(0.3)  # rate limit

        # Upload
        if args.upload:
            try:
                ftp_upload_image(ftp, jpg_data, filename, urun_id)
                insert_image_record(conn, urun_id, filename, urun_adi)
                upload_ok += 1
                print(f"  ↑ {sku} (ID={urun_id}) — FTP 4 boyut + DB OK")
            except Exception as e:
                print(f"  ✗ {sku} — upload hatası: {e}")
                # FTP bağlantısı kopmuş olabilir, yeniden bağlan
                try:
                    ftp = get_ftp_connection()
                    ftp_upload_image(ftp, jpg_data, filename, urun_id)
                    insert_image_record(conn, urun_id, filename, urun_adi)
                    upload_ok += 1
                    print(f"  ↑ {sku} (ID={urun_id}) — retry FTP + DB OK")
                except Exception as e2:
                    print(f"  ✗✗ {sku} — retry de başarısız: {e2}")

    if ftp:
        try:
            ftp.quit()
        except Exception:
            pass
    conn.close()

    # Rapor
    print(f"\n{'='*60}")
    print(f"RAPOR")
    print(f"  Toplam resimsiz ürün: {len(products)}")
    print(f"  Eşleşen:  {matched}")
    print(f"  Eşleşmeyen: {len(unmatched)}")
    if args.download or args.upload:
        print(f"  İndirilen: {download_ok}")
        print(f"  İndirilemedi: {download_fail}")
    if args.upload:
        print(f"  Yüklenen (FTP+DB): {upload_ok}")

    if unmatched:
        print(f"\nEŞLEŞMEYEN ÜRÜNLER ({len(unmatched)}):")
        for u in unmatched:
            print(u)


if __name__ == "__main__":
    main()
