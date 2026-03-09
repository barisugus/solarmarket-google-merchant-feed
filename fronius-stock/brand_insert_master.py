#!/usr/bin/env python3
"""
4 Marka Toplu Ürün Ekleme — BYD, Solis, Deye, Solinved

Fiyatlama formülü (tüm markalar):
  ALISFIYATI    = Liste × 0.50
  FIYAT1 (satış) = ALISFIYATI × 1.25 = Liste × 0.625
  PIYASAFIYATI   = FIYAT1 × 1.22    = Liste × 0.7625

Döviz: BYD/Deye/Solinved = USD, Solis = EUR

Usage:
  python3 brand_insert_master.py                          # dry-run (tüm fazlar)
  python3 brand_insert_master.py --phase byd              # sadece BYD
  python3 brand_insert_master.py --phase solis             # sadece Solis
  python3 brand_insert_master.py --phase deye              # sadece Deye
  python3 brand_insert_master.py --phase solinved          # sadece Solinved
  python3 brand_insert_master.py --phase setup             # sadece marka/kategori setup
  python3 brand_insert_master.py --apply                   # UYGULA (tüm fazlar)
  python3 brand_insert_master.py --phase byd --apply       # sadece BYD uygula
"""

import argparse
import os
import re
import sys
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import pymssql
from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).parent
load_dotenv(SCRIPT_DIR / ".env")

# ═══════════════════════════════════════════════════════════════════════════
# PRICING FORMULA
# ═══════════════════════════════════════════════════════════════════════════
ALIS_RATIO = Decimal("0.50")      # Liste × 0.50 = Alış
SATIS_MARKUP = Decimal("1.25")    # Alış × 1.25 = Satış (FIYAT1)
PIYASA_MARKUP = Decimal("1.22")   # Satış × 1.22 = Piyasa

DEFAULT_STOK = 1000
DEFAULT_KDV = 0                   # KDV dahil değil
DEFAULT_KDVORANI = Decimal("20.00")


def calc_price(list_price):
    """Liste fiyatından Alış/Satış/Piyasa hesapla."""
    lp = Decimal(str(list_price))
    alis = (lp * ALIS_RATIO).quantize(Decimal("0.01"), ROUND_HALF_UP)
    satis = (alis * SATIS_MARKUP).quantize(Decimal("0.01"), ROUND_HALF_UP)
    piyasa = (satis * PIYASA_MARKUP).quantize(Decimal("0.01"), ROUND_HALF_UP)
    return float(alis), float(satis), float(piyasa)


def make_slug(text):
    """URL-safe slug."""
    slug = text.lower()
    # Turkish chars
    tr_map = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
    slug = slug.translate(tr_map)
    slug = re.sub(r"[^a-z0-9-]", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")


# ═══════════════════════════════════════════════════════════════════════════
# PRODUCT DATA
# ═══════════════════════════════════════════════════════════════════════════

# --- BYD (MARKAID=50, USD) ---
# Mevcut stoklular güncellenir, yeni ürünler eklenir
BYD_UPDATES = [
    # (DB_ID, list_price) — mevcut stoklu ürünlerin yeni fiyatlaması
    (1237, 7200),    # HVS 5.1
    (1238, 10200),   # HVS 7.7
    (1239, 13200),   # HVS 10.2
    (1240, 16200),   # HVS 12.8
    (1241, 10300),   # HVM 8.3
    (1242, 13300),   # HVM 11
    (1243, 16300),   # HVM 13.8
    (1244, 19300),   # HVM 16.6
    (1245, 22300),   # HVM 19.3
    (1246, 25400),   # HVM 22.1
    (1489, 3200),    # FLEX LITE 5kWh
    (1490, 300),     # FLEX LITE BMU
]

BYD_NEW = [
    # (stokkodu, urunadi, list_price)
    ("BYD-LV5", "BYD Battery Box LV5.0 – 5 kWh 51.2V Lityum Enerji Depolama Bataryası", 2100),
    ("BYD-LVL", "BYD Battery Box LVL Premium – 15.4 kWh Lityum Enerji Depolama Bataryası", 13000),
]

# --- SOLIS (MARKAID=85, EUR) ---
SOLIS_PRODUCTS = [
    # MONO PHASE ON GRID
    ("Solis-Mini-1500-4G-DC", "Solis 1.5 kW Mono Faz Mini On-Grid Inverter", 470),
    ("Solis-Mini-3000-4G-DC", "Solis 3 kW Mono Faz Mini On-Grid Inverter", 780),
    ("Solis-1P3K-4G-DC", "Solis 3 kW Mono Faz On-Grid Inverter 2 MPPT", 930),
    ("Solis-1P4K-4G-DC", "Solis 4 kW Mono Faz On-Grid Inverter 2 MPPT", 990),
    ("Solis-1P5K-4G-DC", "Solis 5 kW Mono Faz On-Grid Inverter 2 MPPT", 1070),
    ("Solis-1P6K-4G-DC", "Solis 6 kW Mono Faz On-Grid Inverter 2 MPPT", 1180),
    # THREE PHASE ON GRID
    ("Solis-3P3K-4G-DC", "Solis 3 kW Tri Faz On-Grid Inverter", 1000),
    ("Solis-3P5K-4G-DC", "Solis 5 kW Tri Faz On-Grid Inverter", 1030),
    ("Solis-3P8K-4G-DC", "Solis 8 kW Tri Faz On-Grid Inverter", 1170),
    ("Solis-3P10K-4G-DC", "Solis 10 kW Tri Faz On-Grid Inverter", 1260),
    ("Solis-3P15K-4G-DC", "Solis 15 kW Tri Faz On-Grid Inverter", 1450),
    ("Solis-3P20K-4G-DC", "Solis 20 kW Tri Faz On-Grid Inverter", 1670),
    ("S5-GC25K", "Solis 25 kW Tri Faz On-Grid Inverter", 2000),
    ("S5-GC30K", "Solis 30 kW Tri Faz On-Grid Inverter", 2400),
    ("S5-GC40K", "Solis 40 kW Tri Faz On-Grid Inverter", 3260),
    ("Solis-GC-50K", "Solis 50 kW Tri Faz On-Grid Inverter", 3600),
    ("Solis-GC-60K", "Solis 60 kW Tri Faz On-Grid Inverter", 4500),
    # HYBRID INVERTERS
    ("S6-EH1P5K-L-PLUS", "Solis 5 kW Mono Faz Hibrit Inverter LV", 2000),
    ("S6-EH1P6K-L-PLUS", "Solis 6 kW Mono Faz Hibrit Inverter LV", 2100),
    ("S6-EH1P8K-L-PLUS", "Solis 8 kW Mono Faz Hibrit Inverter LV", 3200),
    ("S6-EH1P12K03-NV-YD-L", "Solis 12 kW Mono Faz Hibrit Inverter LV", 4000),
    ("S6-EH1P16K03-NV-YD-L", "Solis 16 kW Mono Faz Hibrit Inverter LV", 4900),
    ("S6-EH3P8K02-NV-YD-L", "Solis 8 kW Tri Faz Hibrit Inverter LV", 4100),
    ("S6-EH3P10K02-NV-YD-L", "Solis 10 kW Tri Faz Hibrit Inverter LV", 4200),
    ("S6-EH3P12K02-NV-YD-L", "Solis 12 kW Tri Faz Hibrit Inverter LV", 4350),
    ("S6-EH3P15K02-NV-YD-L", "Solis 15 kW Tri Faz Hibrit Inverter LV", 5000),
    ("S6-EH3P5K-H-EU", "Solis 5 kW Tri Faz Hibrit Inverter HV", 3000),
    ("S6-EH3P8K-H-EU", "Solis 8 kW Tri Faz Hibrit Inverter HV", 3300),
    ("S6-EH3P10K-H-EU", "Solis 10 kW Tri Faz Hibrit Inverter HV", 3450),
    ("S6-EH3P12K-H-EU", "Solis 12 kW Tri Faz Hibrit Inverter HV", 3800),
    ("S6-EH3P15K-H-EU", "Solis 15 kW Tri Faz Hibrit Inverter HV", 4000),
    ("S6-EH3P20K-H-EU", "Solis 20 kW Tri Faz Hibrit Inverter HV", 5000),
    ("S6-EH3P30K-H-EU", "Solis 30 kW Tri Faz Hibrit Inverter HV", 9000),
    ("S6-EH3P40K-H-EU", "Solis 40 kW Tri Faz Hibrit Inverter HV", 10000),
    ("S6-EH3P50K-H-EU", "Solis 50 kW Tri Faz Hibrit Inverter HV", 11900),
    # ACCESSORIES
    ("S3-WiFi-ST", "Solis S3 WiFi Stick", 50),
    ("Solis-DLB-WIFI", "Solis DLB WiFi Box", 500),
    ("S2-WL-ST", "Solis S2 WiFi Stick (10 Inverter Bağlantı)", 100),
    ("Solis-EPM3-5G", "Solis Export Power Manager (10 Inverter)", 700),
    ("Solis-EPM3-5G-PRO", "Solis Export Power Manager Pro (60 Inverter)", 900),
    ("Solis-Smart-Meter-1CT", "Solis Monofaze Smart Meter (CT Dahil)", 170),
    ("Solis-Smart-Meter-3CT", "Solis Trifaze Smart Meter (CT Dahil)", 250),
]

# --- DEYE (yeni marka, USD) ---
DEYE_PRODUCTS = [
    # MONO PHASE ON-GRID
    ("SUN-3K-MONO", "Deye 3 kW Mono Faz On-Grid String Inverter", 600),
    ("SUN-5K-MONO", "Deye 5 kW Mono Faz On-Grid String Inverter", 850),
    ("SUN-8K-MONO", "Deye 8 kW Mono Faz On-Grid String Inverter", 1250),
    ("SUN-10K-MONO", "Deye 10 kW Mono Faz On-Grid String Inverter", 1300),
    # THREE PHASE ON-GRID
    ("SUN-5K-G06P3-EU-AM2", "Deye 5 kW Tri Faz On-Grid Inverter", 1050),
    ("SUN-8K-G06P3-EU-AM2", "Deye 8 kW Tri Faz On-Grid Inverter", 1070),
    ("SUN-10K-G06P3-EU-AM2", "Deye 10 kW Tri Faz On-Grid Inverter", 1100),
    ("SUN-12K-G06P3-EU-AM2", "Deye 12 kW Tri Faz On-Grid Inverter", 1150),
    ("SUN-15K-G05", "Deye 15 kW Tri Faz On-Grid Inverter", 1580),
    ("SUN-20K-G05", "Deye 20 kW Tri Faz On-Grid Inverter", 1750),
    ("SUN-25K-G04", "Deye 25 kW Tri Faz On-Grid Inverter", 1900),
    ("SUN-30K-G04", "Deye 30 kW Tri Faz On-Grid Inverter", 2300),
    ("SUN-40K-G04", "Deye 40 kW Tri Faz On-Grid Inverter", 3500),
    # HYBRID LV
    ("SUN-5K-SG03LP1-EU", "Deye 5 kW Mono Faz Hibrit Inverter LV", 2100),
    ("SUN-6K-SG03LP1-EU", "Deye 6 kW Mono Faz Hibrit Inverter LV", 2350),
    ("SUN-10K-SG02LP1-EU", "Deye 10 kW Mono Faz Hibrit Inverter LV", 4000),
    ("SUN-16K-SG01LP1-EU", "Deye 16 kW Mono Faz Hibrit Inverter LV", 5500),
    ("SUN-8K-SG04LP3-EU", "Deye 8 kW Tri Faz Hibrit Inverter LV", 4400),
    ("SUN-10K-SG04LP3-EU", "Deye 10 kW Tri Faz Hibrit Inverter LV", 4600),
    ("SUN-12K-SG04LP3-EU", "Deye 12 kW Tri Faz Hibrit Inverter LV", 4800),
    ("SUN-15K-SG05LP3-EU-SM2", "Deye 15 kW Tri Faz Hibrit Inverter LV", 5200),
    ("SUN-20K-SG05LP3-EU-SM2", "Deye 20 kW Tri Faz Hibrit Inverter LV", 7000),
    # HYBRID HV
    ("SUN-10K-SG01HP3-EU", "Deye 10 kW Tri Faz Hibrit Inverter HV", 3500),
    ("SUN-12K-SG01HP3-EU", "Deye 12 kW Tri Faz Hibrit Inverter HV", 4200),
    ("SUN-15K-SG01HP3-EU", "Deye 15 kW Tri Faz Hibrit Inverter HV", 4500),
    ("SUN-20K-SG01HP3-EU", "Deye 20 kW Tri Faz Hibrit Inverter HV", 4800),
    ("SUN-25K-SG01HP3-EU-AM2", "Deye 25 kW Tri Faz Hibrit Inverter HV", 5600),
    ("SUN-30K-SG01HP3-EU-BM3", "Deye 30 kW Tri Faz Hibrit Inverter HV", 7800),
    ("SUN-40K-SG01HP3-EU-BM3", "Deye 40 kW Tri Faz Hibrit Inverter HV", 11000),
    ("SUN-50K-SG05LP3-EU-SM2", "Deye 50 kW Tri Faz Hibrit Inverter HV", 12000),
    ("SUN-80K-SG05LP3-EU-SM3", "Deye 80 kW Tri Faz Hibrit Inverter HV", 16500),
    # ACCESSORIES
    ("DEYE-WIFI-STICK", "Deye WiFi Stick", 120),
    ("DEYE-LAN-STICK", "Deye LAN Stick", 140),
    ("DEYE-SMART-METER-1P", "Deye Monofaze Smart Meter", 90),
    ("DEYE-SMART-METER-3P", "Deye Trifaze Smart Meter", 220),
]

# --- SOLINVED (yeni marka, USD) ---
SOLINVED_PRODUCTS = [
    # GORDION SERIES MPPT OFF-GRID
    ("SLV-1200-12", "Solinved Gordion 1.2 kW MPPT Off-Grid Inverter 12V", 270),
    ("SLV-3600-24", "Solinved Gordion 3.6 kW MPPT Off-Grid Inverter 24V", 420),
    ("SLV-5000-24", "Solinved Gordion 5 kW MPPT Off-Grid Inverter 24V", 580),
    ("SLV-5000-48", "Solinved Gordion 5 kW MPPT Off-Grid Inverter 48V", 630),
    ("SLV-6000-48", "Solinved Gordion 6 kW MPPT Off-Grid Inverter 48V", 620),
    ("SLV-6500-48", "Solinved Gordion 6.5 kW MPPT Off-Grid Inverter 48V", 650),
    # MAX SERIES
    ("MAX-8.2", "Solinved Max 8.2 kW MPPT Off-Grid Inverter 48V", 1000),
    # NML SERIES
    ("NML-2000-12", "Solinved NML 1.6 kW MPPT Off-Grid Inverter 12V", 280),
    # PS PLUS
    ("PS-PLUS-1K", "Solinved PS Plus 1 kW PWM Smart Inverter 12V", 230),
    # ASPENDOS ALL-IN-ONE
    ("ASPENDOS-INV", "Solinved Aspendos All-In-One Inverter Modülü 6 kW 48V", 800),
    ("ASPENDOS-BAT", "Solinved Aspendos All-In-One Batarya Modülü 5 kWh", 1800),
    # PURE SINE INVERTER
    ("SLVP600", "Solinved 600W Pure Sine Inverter 12V", 130),
    ("SLVP1000", "Solinved 1000W Pure Sine Inverter 12V", 180),
    ("SLVP1500", "Solinved 1500W Pure Sine Inverter 12V", 250),
    ("SLVP2000", "Solinved 2000W Pure Sine Inverter 12V", 330),
    ("SLVP2500", "Solinved 2500W Pure Sine Inverter 12V", 380),
    ("SLVP3000", "Solinved 3000W Pure Sine Inverter 12V", 450),
    ("SLVP4000", "Solinved 4000W Pure Sine Inverter 12V", 710),
    ("SLVP1500-24", "Solinved 1500W Pure Sine Inverter 24V", 250),
    ("SLVP3000-24", "Solinved 3000W Pure Sine Inverter 24V", 450),
    # PURE SINE UPS INVERTER
    ("SLVU600", "Solinved 600W Pure Sine UPS Inverter 12V", 160),
    ("SLVU1000", "Solinved 1000W Pure Sine UPS Inverter 12V", 220),
    ("SLVU1500", "Solinved 1500W Pure Sine UPS Inverter 12V", 330),
    # MODIFIED SINE INVERTER
    ("SLVM300", "Solinved 300W Modified Sine Inverter 12V", 35),
    ("SLVM600", "Solinved 600W Modified Sine Inverter 12V", 50),
    ("SLVM1000", "Solinved 1000W Modified Sine Inverter 12V", 85),
    ("SLVM1500", "Solinved 1500W Modified Sine Inverter 12V", 140),
    ("SLVM2000", "Solinved 2000W Modified Sine Inverter 12V", 190),
    ("SLVM2500", "Solinved 2500W Modified Sine Inverter 12V", 240),
    ("SLVM1500-24", "Solinved 1500W Modified Sine Inverter 24V", 140),
    ("SLVM3000-24", "Solinved 3000W Modified Sine Inverter 24V", 300),
    # MPPT CHARGE CONTROLLERS
    ("SOL-MPPT320D", "Solinved 20A MPPT Şarj Kontrol Cihazı 12V/24V", 75),
    ("SOL-MPPT330D", "Solinved 30A MPPT Şarj Kontrol Cihazı 12V/24V", 100),
    ("SOL-MPPT340D", "Solinved 40A MPPT Şarj Kontrol Cihazı 12V/24V", 120),
    # MPK CHARGE CONTROLLERS
    ("SOL-MPK60", "Solinved 60A MPPT Şarj Kontrol Cihazı 12V/48V", 220),
    ("SOL-MPK80", "Solinved 80A MPPT Şarj Kontrol Cihazı 12V/48V", 290),
    ("SOL-MPK100", "Solinved 100A MPPT Şarj Kontrol Cihazı 12V/48V", 320),
    # LT PWM CHARGE CONTROLLERS
    ("SOL-LT10-1024", "Solinved 10A PWM Şarj Kontrol Cihazı 12/24V", 11),
    ("SOL-LT20-2024", "Solinved 20A PWM Şarj Kontrol Cihazı 12/24V", 14),
    ("SOL-LT30-3024", "Solinved 30A PWM Şarj Kontrol Cihazı 12/24V", 28),
    ("SOL-LT40-4024", "Solinved 40A PWM Şarj Kontrol Cihazı 12/24V", 35),
    # GEL BATTERIES
    ("SOL12-100", "Solinved 12V 100Ah Solar Jel Akü Deep Cycle", 270),
    ("SOL12-150", "Solinved 12V 150Ah Solar Jel Akü Deep Cycle", 405),
    ("SOL12-200", "Solinved 12V 200Ah Solar Jel Akü Deep Cycle", 540),
    # LITHIUM BATTERIES
    ("SOL-1280", "Solinved 12V 100Ah Lityum Batarya", 520),
    ("SOL-2560", "Solinved 24V 100Ah Lityum Batarya", 840),
    ("SOL-5100-HV-LV", "Solinved Kapadokya 51.2V 100Ah Lityum Rack Batarya", 1700),
    ("SOL-WL-15", "Solinved 51.2V 300Ah Lityum Duvar Tipi Batarya", 4400),
    ("SOL-XH", "Solinved 102.4V 100Ah Lityum Duvar Tipi Batarya", 3500),
    ("SOL-XH-CONTROLBOX", "Solinved XH Control Box", 1800),
    ("SOL-LITHIUM-CABLE", "Solinved Lityum Batarya Güç Kablo Seti 2x1.5m", 60),
    # CIRCUIT BREAKERS
    ("SOLM3DC-80", "Solinved DC 80A 1000V Devre Kesici", 50),
    ("SOLM3DC-100", "Solinved DC 100A 1000V Devre Kesici", 55),
    ("SOLM3DC-125", "Solinved DC 125A 1000V Devre Kesici", 60),
    ("SOLM3DC-200", "Solinved DC 200A 1000V Devre Kesici", 80),
    ("SOLM3DC-250", "Solinved DC 250A 1000V Devre Kesici", 100),
    ("SOLM3DC-315", "Solinved DC 315A 1000V Devre Kesici", 200),
    ("SOLM3DC-350", "Solinved DC 350A 1000V Devre Kesici", 300),
    # DC FUSE
    ("SLVFS-16", "Solinved 16A 1000V DC Sigorta", 3.30),
    ("SLVFS-32", "Solinved 32A 1000V DC Sigorta", 3.30),
    ("SLVFSHL", "Solinved DC Sigorta Yuvası 10x38mm", 3.30),
    # MC4 CONNECTORS
    ("SOL-MC4-1000", "Solinved MC4 Solar Konnektör Seti 1000V", 1.30),
    ("SOL-MC4H-1500", "Solinved MC4 Solar Konnektör Seti 1500V", 1.80),
    ("SOL-MC4-KIT", "Solinved MC4 Sıkma Pensesi (Crimping Tool)", 100),
    # SOLAR MOUNTING
    ("KONST-2X15", "Solinved 2x15 Solar Montaj Yapı Seti", 1110),
    ("KONST-2X10", "Solinved 2x10 Solar Montaj Yapı Seti", 740),
    ("KONST-2X9", "Solinved 2x9 Solar Montaj Yapı Seti", 666),
    ("KONST-2X8", "Solinved 2x8 Solar Montaj Yapı Seti", 592),
    ("KONST-2X7", "Solinved 2x7 Solar Montaj Yapı Seti", 518),
    ("KONST-2X5", "Solinved 2x5 Solar Montaj Yapı Seti", 370),
    ("KONST-2X4", "Solinved 2x4 Solar Montaj Yapı Seti", 300),
    # EV CHARGER
    ("SOL-EV-ANGORA-22", "Solinved Angora 22 kW AC Şarj Cihazı OCPP", 1000),
    ("SOL-EV-RADIUS-22", "Solinved Radius 22 kW AC Şarj Cihazı", 800),
    # PUMP DRIVERS - 1x220V
    ("SOL-CDI-SPDG1R5-SS2", "Solinved 1.5 kW Mono Faz Solar Pompa Sürücü 220V", 290),
    ("SOL-CDI-SPDG2R2-SS2", "Solinved 2.2 kW Mono Faz Solar Pompa Sürücü 220V", 460),
    ("SOL-CDI-SPDG4R0-SS2", "Solinved 4 kW Mono Faz Solar Pompa Sürücü 220V", 510),
    # PUMP DRIVERS - 3x220V
    ("SOL-CDI-SPDG2R2-S2", "Solinved 2.2 kW Tri Faz Solar Pompa Sürücü 3x220V", 270),
    ("SOL-CDI-SPDG4R0-S2", "Solinved 4 kW Tri Faz Solar Pompa Sürücü 3x220V", 400),
    # PUMP DRIVERS - 3x380V (250-750V DC Input) — most popular range
    ("SOL-CDI-SPDG1R5T4", "Solinved 1.5 kW Tri Faz Solar Pompa Sürücü 380V", 270),
    ("SOL-CDI-SPDG2R2T4", "Solinved 2.2 kW Tri Faz Solar Pompa Sürücü 380V", 310),
    ("SOL-CDI-SPDG4R0T4", "Solinved 4 kW Tri Faz Solar Pompa Sürücü 380V", 360),
    ("SOL-CDI-SPDG5R5T4", "Solinved 5.5 kW Tri Faz Solar Pompa Sürücü 380V", 480),
    ("SOL-CDI-SPDG7R5T4", "Solinved 7.5 kW Tri Faz Solar Pompa Sürücü 380V", 520),
    ("SOL-CDI-SPDG011T4", "Solinved 11 kW Tri Faz Solar Pompa Sürücü 380V", 680),
    ("SOL-CDI-SPDG015T4", "Solinved 15 kW Tri Faz Solar Pompa Sürücü 380V", 760),
    ("SOL-CDI-SPDG018T4", "Solinved 18.5 kW Tri Faz Solar Pompa Sürücü 380V", 960),
    ("SOL-CDI-SPDG022T4", "Solinved 22 kW Tri Faz Solar Pompa Sürücü 380V", 1100),
    ("SOL-CDI-SPDG030T4", "Solinved 30 kW Tri Faz Solar Pompa Sürücü 380V", 1500),
    ("SOL-CDI-SPDG037T4", "Solinved 37 kW Tri Faz Solar Pompa Sürücü 380V", 1800),
    ("SOL-CDI-SPDG045T4", "Solinved 45 kW Tri Faz Solar Pompa Sürücü 380V", 2200),
    ("SOL-CDI-SPDG055T4", "Solinved 55 kW Tri Faz Solar Pompa Sürücü 380V", 2600),
    ("SOL-CDI-SPDG075T4", "Solinved 75 kW Tri Faz Solar Pompa Sürücü 380V", 3000),
    ("SOL-CDI-SPDG090T4", "Solinved 90 kW Tri Faz Solar Pompa Sürücü 380V", 3900),
    ("SOL-CDI-SPDG110T4", "Solinved 110 kW Tri Faz Solar Pompa Sürücü 380V", 4000),
    # PUMP DRIVER PANELS
    ("DKP-TIP1-PANO", "Solinved 1.5-5.5 kW Pompa Sürücü Panosu", 220),
    ("DKP-TIP2-PANO", "Solinved 7.5-15 kW Pompa Sürücü Panosu", 250),
    ("DKP-TIP3-PANO", "Solinved 18.5-22 kW Pompa Sürücü Panosu", 470),
    ("DKP-TIP4-PANO", "Solinved 30-37 kW Pompa Sürücü Panosu", 600),
    ("DKP-TIP5-PANO", "Solinved 45-55 kW Pompa Sürücü Panosu", 800),
    # SOLAR CAMERAS
    ("CM26-4G", "Solinved CM26 Solar Kamera 4G", 90),
    ("CM04-WIFI", "Solinved CM04 Solar Kamera WiFi", 100),
    ("CM27-4G", "Solinved CM27 Solar Kamera 4G", 120),
    ("CM04-4G", "Solinved CM04 Solar Kamera 4G", 120),
    ("CM22-WIFI", "Solinved CM22 Solar Kamera WiFi", 135),
    ("CM09-4G", "Solinved CM09 Solar Kamera 4G", 150),
    ("CM22-4G", "Solinved CM22 Solar Kamera 4G", 140),
    ("L8-4G", "Solinved L8 Solar Router 4G", 125),
    # LEAD ACID BATTERIES
    ("SOL-12-7", "Solinved 12V 7Ah Kurşun Asit Akü", 14),
    ("SOL-12-7-PREMIUM", "Solinved 12V 7Ah Premium Kurşun Asit Akü", 16),
    ("SOL-12-9", "Solinved 12V 9Ah Kurşun Asit Akü", 20),
    ("SOL-12-12", "Solinved 12V 12Ah Kurşun Asit Akü", 28),
    # E-BIKE BATTERIES
    ("SOL-12-14", "Solinved 12V 14Ah E-Bike Batarya", 33),
    ("SOL-12-24", "Solinved 12V 24Ah E-Bike Batarya", 48),
    ("SOL-12-24-PREMIUM", "Solinved 12V 24Ah Premium E-Bike Batarya", 50),
]

# ═══════════════════════════════════════════════════════════════════════════
# CATEGORY MAPPING
# ═══════════════════════════════════════════════════════════════════════════
# Mevcut kategoriler
CAT_INVERTER_MARKALARI = 78    # İnverter Markaları (parent)
CAT_SOLIS_INV = 95             # Solis (under 78)
CAT_HIBRIT = 83                # Hibrit İnverterler
CAT_OFFGRID = 84               # Off Grid İnverter
CAT_BYD_LITYUM = 56            # BYD Lityum Pil
CAT_SOLAR_MALZEME = 64         # Solar Malzemeler
CAT_SOLAR_KABLO = 58           # Solar Kablo
CAT_SOLAR_KONNEKTOR = 59       # Solar Konnektör
CAT_EV_CHARGER = 63            # Elektrikli Araç Şarj Cihazı
CAT_EV_KABLO = 91              # EV Elektrikli Araç Kablosu

# Yeni oluşturulacak kategoriler (ID'ler runtime'da alınır)
NEW_CATEGORIES = {
    "Deye": {"parent": CAT_INVERTER_MARKALARI, "sef": "deye"},
    "Solinved": {"parent": CAT_INVERTER_MARKALARI, "sef": "solinved"},
}

# Ürün tipi → kategori mapping
# Her ürün tipi: (primary_categories, vitrin_category_id)
# primary_categories: list of (category_id, vitrin_value)


def get_product_categories(brand, stokkodu, urunadi):
    """Ürün adına göre kategori ataması yap."""
    name_lower = urunadi.lower()

    if brand == "BYD":
        return [
            (CAT_BYD_LITYUM, 1),
            (CAT_SOLAR_MALZEME, 1),
        ]

    if brand == "Solis":
        cats = [(CAT_SOLIS_INV, 1), (CAT_INVERTER_MARKALARI, 0)]
        if "hibrit" in name_lower:
            cats.append((CAT_HIBRIT, 1))
        if "smart meter" in name_lower or "wifi" in name_lower or "power manager" in name_lower:
            cats = [(CAT_SOLAR_MALZEME, 1), (CAT_SOLIS_INV, 1)]
        return cats

    if brand == "Deye":
        cats = [("Deye", 1), (CAT_INVERTER_MARKALARI, 0)]
        if "hibrit" in name_lower:
            cats.append((CAT_HIBRIT, 1))
        if "smart meter" in name_lower or "wifi" in name_lower or "lan" in name_lower:
            cats = [(CAT_SOLAR_MALZEME, 1), ("Deye", 1)]
        return cats

    if brand == "Solinved":
        cats = [("Solinved", 1)]
        if "off-grid" in name_lower or "inverter" in name_lower:
            if "off-grid" in name_lower:
                cats.append((CAT_OFFGRID, 1))
            cats.append((CAT_INVERTER_MARKALARI, 0))
        elif "akü" in name_lower or "lityum" in name_lower or "batarya" in name_lower:
            cats.append((CAT_SOLAR_MALZEME, 1))
        elif "konnektör" in name_lower or "mc4" in name_lower:
            cats.append((CAT_SOLAR_KONNEKTOR, 1))
        elif "şarj cihazı" in name_lower and "ev" not in name_lower:
            cats.append((CAT_SOLAR_MALZEME, 1))
        elif "şarj cihazı" in name_lower and ("22 kw" in name_lower or "ev" in name_lower):
            cats.append((CAT_EV_CHARGER, 1))
        elif "pompa" in name_lower or "montaj" in name_lower or "devre kesici" in name_lower or "sigorta" in name_lower:
            cats.append((CAT_SOLAR_MALZEME, 1))
        elif "kamera" in name_lower or "router" in name_lower:
            cats.append((CAT_SOLAR_MALZEME, 1))
        elif "pano" in name_lower:
            cats.append((CAT_SOLAR_MALZEME, 1))
        else:
            cats.append((CAT_SOLAR_MALZEME, 1))
        return cats

    return [(CAT_SOLAR_MALZEME, 1)]


# ═══════════════════════════════════════════════════════════════════════════
# DB OPERATIONS
# ═══════════════════════════════════════════════════════════════════════════

def get_connection():
    return pymssql.connect(
        server=os.getenv("MSSQL_SERVER"),
        port=int(os.getenv("MSSQL_PORT", "1433")),
        user=os.getenv("MSSQL_USER"),
        password=os.getenv("MSSQL_PASSWORD"),
        database=os.getenv("MSSQL_DATABASE"),
        charset="utf8",
    )


def get_or_create_brand(conn, brand_name, apply=False):
    """Marka varsa ID döner, yoksa oluşturur."""
    cur = conn.cursor(as_dict=True)
    cur.execute("SELECT ID FROM MARKALAR WHERE MARKA = %s", (brand_name,))
    row = cur.fetchone()
    cur.close()
    if row:
        return row["ID"]

    if apply:
        cur = conn.cursor()
        cur.execute("INSERT INTO MARKALAR (MARKA) VALUES (%s)", (brand_name,))
        cur.execute("SELECT SCOPE_IDENTITY() AS new_id")
        new_id = int(cur.fetchone()[0])
        cur.close()
        print(f"  MARKA OLUŞTURULDU: {brand_name} → ID={new_id}")
        return new_id
    else:
        print(f"  [DRY-RUN] MARKA OLUŞTURULACAK: {brand_name}")
        return None


def get_or_create_category(conn, cat_name, parent_id, sef_url, apply=False):
    """Kategori varsa ID döner, yoksa oluşturur."""
    cur = conn.cursor(as_dict=True)
    cur.execute("SELECT ID, SEF_URL FROM KATEGORILER WHERE KATEGORI = %s AND UST_KATEGORI_ID = %s",
                (cat_name, parent_id))
    row = cur.fetchone()
    cur.close()
    if row:
        return row["ID"], row["SEF_URL"]

    if apply:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO KATEGORILER (KATEGORI, UST_KATEGORI_ID, AKTIF, SIRA, SEF_URL,
                PAGE_TITLE, META_KEYWORDS, META_DESCRIPTION, ACIKLAMA,
                GORUNTULENMESAYISI, ENTEGREKODU, BANNER, DETAY,
                SEPET_INDIRIMI_AKTIF, SEPET_INDIRIMI_ORAN)
            VALUES (%s, %s, 1, 0, %s, %s, %s, %s, '', 0, '', '', '', 0, 0)
        """, (cat_name, parent_id, sef_url, cat_name, cat_name, cat_name))
        cur.execute("SELECT SCOPE_IDENTITY() AS new_id")
        new_id = int(cur.fetchone()[0])
        cur.close()
        print(f"  KATEGORİ OLUŞTURULDU: {cat_name} (parent={parent_id}) → ID={new_id}")
        return new_id, sef_url
    else:
        print(f"  [DRY-RUN] KATEGORİ OLUŞTURULACAK: {cat_name} (parent={parent_id})")
        return None, sef_url


def get_category_sef(conn, cat_id):
    """Kategori SEF_URL'ini al."""
    cur = conn.cursor(as_dict=True)
    cur.execute("SELECT SEF_URL FROM KATEGORILER WHERE ID = %s", (cat_id,))
    row = cur.fetchone()
    cur.close()
    return row["SEF_URL"] if row else ""


def insert_product(conn, stokkodu, urunadi, marka_id, doviztipi,
                   alis, fiyat1, piyasa, cat_list, apply=False):
    """Ürün INSERT + kategori bağlama."""
    slug = make_slug(urunadi)

    # NULL trap'lere dikkat — CLAUDE.md'deki kritik lesson
    urunler_vals = {
        "URUNADI": urunadi,
        "STOKKODU": stokkodu,
        "MARKAID": marka_id,
        "FIYAT1": fiyat1,
        "ALISFIYATI": alis,
        "PIYASAFIYATI": piyasa,
        "STOK": DEFAULT_STOK,
        "DOVIZTIPI": doviztipi,
        "KDV": DEFAULT_KDV,
        "KDVORANI": float(DEFAULT_KDVORANI),
        "OLCUBIRIMI": "Adet",
        # NULL trap: numerik alanlar 0
        "KARGOAGIRLIGI": 0,
        "FIYAT2": 0,
        "FIYAT3": 0,
        "FIYAT4": 0,
        "FIYAT5": 0,
        "GORUNTULENMESAYISI": 0,
        "SATILMASAYISI": 0,
        "MATRISGORUNUMU": 0,
        "VARYANTGORUNUMU": 0,
        "MAXSIPARISMIKTARI": 0,
        "ANASAYFAVITRINSIRASI": 0,
        "SIRA": 0,
        # NULL trap: string alanlar ''
        "ENTEGREKODU": "",
        "RAPORKODU": "",
        "ETIKETLER": "",
        "URUNDETAY": "",
        "METAKEYWORDS": "",
        "METADESCRIPTION": "",
        "PAGETITLE": "",
        "URUNACIKLAMASI": "",
        "DETAY_YEDEK_1": "",
        "DETAY_YEDEK_2": "",
        "DETAY_YEDEK_3": "",
        "DETAY_YEDEK_4": "",
        "DETAY_YEDEK_5": "",
        # Bit fields
        "ANASAYFAVITRINI": 0,
        "STOKTAKIBI": 0,
        "MAXSIPARISMIKTARIAKTIF": 0,
        # SEO
        "SEO_AYAR": 0,
        "MESAJ": 0,
        # Nullable — explicit None
        "STOKDURUMUID": None,
        "URUNGRUPID": None,
        "URUNGRUPID2": None,
        "VARYANTGRUPID": None,
        "ANASAYVAVITRINVARYANTID": None,
        "MATRISGRUPID": None,
    }

    if not apply:
        return None  # dry-run, sadece göster

    cur = conn.cursor(as_dict=True)

    # INSERT URUNLER
    columns = list(urunler_vals.keys())
    col_names = ", ".join(columns)
    placeholders = ", ".join(["%s"] * len(columns))
    values = tuple(urunler_vals[c] for c in columns)

    cur.execute(f"INSERT INTO URUNLER ({col_names}) VALUES ({placeholders})", values)
    cur.execute("SELECT SCOPE_IDENTITY() AS new_id")
    new_id = int(cur.fetchone()["new_id"])

    # INSERT URUNKATEGORILERI
    for cat_id, vitrin in cat_list:
        sef = get_category_sef(conn, cat_id)
        sefurl = f"{sef}{slug}" if sef else slug
        cur.execute("""
            INSERT INTO URUNKATEGORILERI (URUNID, KATEGORIID, VITRIN, SEFURL, VITRINVARYANTID)
            VALUES (%s, %s, %s, %s, %s)
        """, (new_id, cat_id, vitrin, sefurl, None))

    cur.close()
    return new_id


# ═══════════════════════════════════════════════════════════════════════════
# PHASE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════

def phase_setup(conn, apply):
    """Faz 0: Yeni markalar ve kategoriler oluştur."""
    print("\n" + "=" * 70)
    print("FAZ 0: MARKA & KATEGORİ SETUP")
    print("=" * 70)

    brands = {}
    brands["BYD"] = 50  # mevcut
    brands["Solis"] = 85  # mevcut

    # Deye markası
    deye_id = get_or_create_brand(conn, "Deye", apply)
    brands["Deye"] = deye_id

    # Solinved markası
    solinved_id = get_or_create_brand(conn, "Solinved", apply)
    brands["Solinved"] = solinved_id

    # Yeni kategoriler
    categories = {}
    for cat_name, info in NEW_CATEGORIES.items():
        cat_id, sef = get_or_create_category(
            conn, cat_name, info["parent"], info["sef"], apply
        )
        categories[cat_name] = {"id": cat_id, "sef": sef}

    if apply:
        conn.commit()
        print("  COMMIT OK")

    return brands, categories


def phase_byd(conn, apply):
    """Faz 1: BYD fiyat güncelleme + yeni ürünler."""
    print("\n" + "=" * 70)
    print("FAZ 1: BYD — Fiyat Güncelleme + Yeni Ürünler")
    print("=" * 70)

    # Mevcut ürünleri güncelle
    print("\n--- Mevcut BYD Ürünleri Güncelleme ---")
    for db_id, list_price in BYD_UPDATES:
        alis, fiyat1, piyasa = calc_price(list_price)

        # Mevcut değerleri oku
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT URUNADI, FIYAT1, ALISFIYATI, PIYASAFIYATI FROM URUNLER WHERE ID=%s", (db_id,))
        row = cur.fetchone()
        cur.close()

        if not row:
            print(f"  HATA: ID={db_id} bulunamadı!")
            continue

        old_fiyat1 = float(row["FIYAT1"] or 0)
        name = (row["URUNADI"] or "")[:55]
        change = "DEĞİŞİM" if abs(old_fiyat1 - fiyat1) > 0.01 else "AYNI"

        print(
            f"  ID={db_id:5d} | ALIS=${alis:>9,.2f} | "
            f"FIYAT1: ${old_fiyat1:>9,.2f} -> ${fiyat1:>9,.2f} | "
            f"PIYASA=${piyasa:>9,.2f} | {change} | {name}"
        )

        if apply:
            cur = conn.cursor()
            cur.execute("""
                UPDATE URUNLER
                SET ALISFIYATI=%s, FIYAT1=%s, PIYASAFIYATI=%s
                WHERE ID=%s
            """, (alis, fiyat1, piyasa, db_id))
            cur.close()

    # Yeni BYD ürünleri
    print("\n--- Yeni BYD Ürünleri ---")
    for stokkodu, urunadi, list_price in BYD_NEW:
        alis, fiyat1, piyasa = calc_price(list_price)

        # Duplicate kontrolü
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT ID FROM URUNLER WHERE STOKKODU=%s", (stokkodu,))
        existing = cur.fetchone()
        cur.close()

        if existing:
            print(f"  MEVCUT: {stokkodu} (ID={existing['ID']}) — atlanıyor")
            continue

        cats = get_product_categories("BYD", stokkodu, urunadi)
        # Resolve category IDs
        resolved_cats = []
        for cat, vitrin in cats:
            if isinstance(cat, int):
                resolved_cats.append((cat, vitrin))

        print(
            f"  YENİ: {stokkodu} | ALIS=${alis:>8,.2f} | "
            f"FIYAT1=${fiyat1:>8,.2f} | PIYASA=${piyasa:>8,.2f} | {urunadi[:50]}"
        )

        if apply:
            new_id = insert_product(conn, stokkodu, urunadi, 50, "USD",
                                     alis, fiyat1, piyasa, resolved_cats, True)
            print(f"    → ID={new_id}")

    if apply:
        conn.commit()
        print("  BYD COMMIT OK")


def phase_brand_insert(conn, brand_name, marka_id, doviztipi, products, new_cat_ids, apply):
    """Genel marka ekleme fonksiyonu."""
    print(f"\n--- {brand_name} Ürün Ekleme ({len(products)} ürün) ---")

    inserted = 0
    skipped = 0

    for stokkodu, urunadi, list_price in products:
        alis, fiyat1, piyasa = calc_price(list_price)

        # Duplicate kontrolü
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT ID FROM URUNLER WHERE STOKKODU=%s", (stokkodu,))
        existing = cur.fetchone()
        cur.close()

        if existing:
            print(f"  MEVCUT: {stokkodu} (ID={existing['ID']}) — atlanıyor")
            skipped += 1
            continue

        cats = get_product_categories(brand_name, stokkodu, urunadi)

        # Resolve string category names to IDs
        resolved_cats = []
        for cat, vitrin in cats:
            if isinstance(cat, int):
                resolved_cats.append((cat, vitrin))
            elif isinstance(cat, str) and cat in new_cat_ids:
                resolved_cats.append((new_cat_ids[cat], vitrin))

        # VITRIN=1 olan en az 1 kategori olmalı
        has_vitrin = any(v == 1 for _, v in resolved_cats)
        if not has_vitrin and resolved_cats:
            # İlk kategoriyi VITRIN=1 yap
            resolved_cats[0] = (resolved_cats[0][0], 1)

        print(
            f"  {stokkodu:35s} | ${list_price:>9,.2f} → "
            f"ALIS=${alis:>8,.2f} | FIYAT1=${fiyat1:>8,.2f} | "
            f"PIYASA=${piyasa:>8,.2f} | KAT={[c[0] for c in resolved_cats]}"
        )

        if apply:
            new_id = insert_product(conn, stokkodu, urunadi, marka_id, doviztipi,
                                     alis, fiyat1, piyasa, resolved_cats, True)
            if new_id:
                inserted += 1

    if apply:
        conn.commit()
        print(f"  {brand_name} COMMIT OK — {inserted} eklendi, {skipped} atlandı")
    else:
        print(f"  [DRY-RUN] {len(products) - skipped} eklenecek, {skipped} atlanacak")


def phase_solis(conn, new_cat_ids, apply):
    """Faz 2: Solis ürün ekleme."""
    print("\n" + "=" * 70)
    print("FAZ 2: SOLIS — 41 Ürün Ekleme (EUR)")
    print("=" * 70)

    # Mevcut Solis ürünü kontrol
    cur = conn.cursor(as_dict=True)
    cur.execute("SELECT ID, URUNADI, FIYAT1, STOKKODU FROM URUNLER WHERE MARKAID=85")
    existing = cur.fetchall()
    cur.close()
    if existing:
        print(f"  Mevcut Solis ürünleri: {len(existing)}")
        for r in existing:
            print(f"    ID={r['ID']} | {r['STOKKODU']} | FIYAT1={float(r['FIYAT1'] or 0):,.2f}")

    phase_brand_insert(conn, "Solis", 85, "EUR", SOLIS_PRODUCTS, new_cat_ids, apply)


def phase_deye(conn, brands, new_cat_ids, apply):
    """Faz 3: Deye ürün ekleme."""
    print("\n" + "=" * 70)
    print("FAZ 3: DEYE — 35 Ürün Ekleme (USD)")
    print("=" * 70)

    marka_id = brands.get("Deye")
    if not marka_id:
        print("  HATA: Deye markası bulunamadı! Önce --phase setup --apply çalıştır.")
        return

    phase_brand_insert(conn, "Deye", marka_id, "USD", DEYE_PRODUCTS, new_cat_ids, apply)


def phase_solinved(conn, brands, new_cat_ids, apply):
    """Faz 4: Solinved ürün ekleme."""
    print("\n" + "=" * 70)
    print(f"FAZ 4: SOLİNVED — {len(SOLINVED_PRODUCTS)} Ürün Ekleme (USD)")
    print("=" * 70)

    marka_id = brands.get("Solinved")
    if not marka_id:
        print("  HATA: Solinved markası bulunamadı! Önce --phase setup --apply çalıştır.")
        return

    phase_brand_insert(conn, "Solinved", marka_id, "USD", SOLINVED_PRODUCTS, new_cat_ids, apply)


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="4 Marka Toplu Ürün Ekleme")
    parser.add_argument("--apply", action="store_true", help="DB'ye yaz")
    parser.add_argument("--phase", type=str, default="all",
                        choices=["all", "setup", "byd", "solis", "deye", "solinved"],
                        help="Hangi faz çalışsın")
    args = parser.parse_args()

    mode = "APPLY" if args.apply else "DRY-RUN"
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print(f"{'=' * 70}")
    print(f"4 MARKA TOPLU ÜRÜN EKLEME — {mode} — {ts}")
    print(f"{'=' * 70}")
    print(f"  Faz: {args.phase}")
    print(f"  Formül: ALIS=Liste×{ALIS_RATIO}, FIYAT1=ALIS×{SATIS_MARKUP}, PIYASA=FIYAT1×{PIYASA_MARKUP}")
    print(f"  BYD: {len(BYD_UPDATES)} güncelleme + {len(BYD_NEW)} yeni")
    print(f"  Solis: {len(SOLIS_PRODUCTS)} ürün (EUR)")
    print(f"  Deye: {len(DEYE_PRODUCTS)} ürün (USD)")
    print(f"  Solinved: {len(SOLINVED_PRODUCTS)} ürün (USD)")
    total = len(BYD_UPDATES) + len(BYD_NEW) + len(SOLIS_PRODUCTS) + len(DEYE_PRODUCTS) + len(SOLINVED_PRODUCTS)
    print(f"  TOPLAM: {total} işlem")

    conn = get_connection()
    print("\nDB connected.")

    try:
        # Faz 0: Setup (markalar + kategoriler)
        if args.phase in ("all", "setup"):
            brands, categories = phase_setup(conn, args.apply)
        else:
            # Mevcut marka ID'lerini oku
            brands = {"BYD": 50, "Solis": 85}
            cur = conn.cursor(as_dict=True)
            cur.execute("SELECT ID, MARKA FROM MARKALAR WHERE MARKA IN ('Deye', 'Solinved')")
            for r in cur.fetchall():
                brands[r["MARKA"]] = r["ID"]
            cur.close()
            categories = {}

        # Yeni kategori ID'lerini topla
        new_cat_ids = {}
        for cat_name, info in categories.items():
            if info.get("id"):
                new_cat_ids[cat_name] = info["id"]
        # Mevcut kategoriler de burada
        cur = conn.cursor(as_dict=True)
        for cat_name in ["Deye", "Solinved"]:
            cur.execute("SELECT ID FROM KATEGORILER WHERE KATEGORI=%s AND UST_KATEGORI_ID=%s",
                        (cat_name, CAT_INVERTER_MARKALARI))
            row = cur.fetchone()
            if row and cat_name not in new_cat_ids:
                new_cat_ids[cat_name] = row["ID"]
        cur.close()

        # Faz 1: BYD
        if args.phase in ("all", "byd"):
            phase_byd(conn, args.apply)

        # Faz 2: Solis
        if args.phase in ("all", "solis"):
            phase_solis(conn, new_cat_ids, args.apply)

        # Faz 3: Deye
        if args.phase in ("all", "deye"):
            phase_deye(conn, brands, new_cat_ids, args.apply)

        # Faz 4: Solinved
        if args.phase in ("all", "solinved"):
            phase_solinved(conn, brands, new_cat_ids, args.apply)

        # Özet
        print(f"\n{'=' * 70}")
        print("ÖZET")
        print(f"{'=' * 70}")
        print(f"  Mod: {mode}")
        if not args.apply:
            print(f"  DB'ye YAZILMADI. --apply ile çalıştır.")
        else:
            print(f"  TÜM İŞLEMLER TAMAMLANDI.")

    except Exception as e:
        conn.rollback()
        print(f"\n  HATA — ROLLBACK: {e}")
        raise
    finally:
        conn.close()
        print("\nDB connection closed.")


if __name__ == "__main__":
    main()
