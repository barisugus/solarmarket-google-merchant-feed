#!/usr/bin/env python3
"""
URUNDETAY HTML content generator for 193 new products.
Generates SEO-friendly product descriptions in Turkish,
matching existing site format (HTML with <p>, <strong>, <table>, emoji).

Usage:
  python generate_urundetay.py --preview   # Preview first 5 of each type
  python generate_urundetay.py --apply      # Write to DB
"""

import json
import re
import sys
import pymssql
import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv('.env')

DB_SERVER = '37.148.209.147'
DB_USER = 'trSolarMarket.dogus.egebilgi'
DB_PASS = '3%DKveYq*6py0ntn'
DB_NAME = 'turkiyeSolarMarketDb'


def classify_product(name, categories):
    """Classify product into a type for template selection."""
    n = name.lower()
    cats = [c.lower() for c in categories]

    # Battery types
    if any(x in n for x in ['lityum', 'battery', 'batarya', 'enerji depolama']):
        if 'duvar' in n or 'wall' in n:
            return 'battery_wall'
        if 'rack' in n:
            return 'battery_rack'
        return 'battery_lithium'
    if 'jel akü' in n or 'deep cycle' in n:
        return 'battery_gel'
    if 'kursun asit' in n:
        return 'battery_lead'

    # Inverter types
    if 'hibrit' in n:
        return 'inverter_hybrid'
    if 'on-grid' in n or ('string' in n and 'inverter' in n):
        return 'inverter_ongrid'
    if 'mikro' in n or 'micro' in n:
        return 'inverter_micro'
    if 'off-grid' in n or 'gordion' in n or 'nml' in n or 'max' in n and 'mppt' in n:
        return 'inverter_offgrid'
    if 'modified sine' in n or 'pure sine' in n or 'ups inverter' in n:
        return 'inverter_portable'
    if 'ps plus' in n:
        return 'inverter_portable'
    if 'aspendos' in n or 'all-in-one' in n:
        return 'inverter_allinone'

    # Solar pump
    if 'pompa sürücü' in n and 'panos' not in n:
        return 'pump_driver'
    if 'pompa' in n and 'pano' in n:
        return 'pump_panel'

    # EV & Charge controllers
    if 'mppt' in n and 'sarj' in n:
        return 'charge_mppt'
    if 'pwm' in n and 'sarj' in n:
        return 'charge_pwm'
    if 'ev' in n and 'sarj' in n:
        return 'ev_charger'
    if 'sarj cihaz' in n and 'kontrol' not in n:
        return 'ev_charger'

    # Solar panel
    if 'panel' in n:
        return 'solar_panel'

    # Communication/monitoring
    if any(x in n for x in ['wifi', 'lan', 'dongle', 'logger', 'stick']):
        return 'accessory_comm'
    if 'kamera' in n:
        return 'solar_camera'
    if 'router' in n:
        return 'solar_router'

    # Mounting
    if any(x in n for x in ['montaj', 'konstruksiyon', 'kiremit', 'trapez', 'zemin']):
        return 'mounting'

    # Electrical
    if 'sigorta' in n and 'yuva' not in n:
        return 'dc_fuse'
    if 'sigorta yuvasi' in n or 'sigorta yuvası' in n:
        return 'dc_fuse_holder'
    if 'devre kesici' in n:
        return 'dc_breaker'
    if 'mc4' in n and ('konnektör' in n or 'konnektor' in n):
        return 'mc4_connector'
    if 'mc4' in n and ('pense' in n or 'crimping' in n):
        return 'mc4_tool'

    # Smart meter
    if 'meter' in n or 'sayac' in n or 'sayaç' in n:
        return 'smart_meter'

    # Export power manager
    if 'export' in n and 'manager' in n:
        return 'export_manager'

    # Control box
    if 'control box' in n:
        return 'control_box'

    return 'generic'


def parse_specs_from_name(name, brand):
    """Extract technical specs from product name."""
    specs = {'brand': brand, 'name': name}

    # Power/capacity
    m = re.search(r'(\d+(?:\.\d+)?)\s*kW', name, re.IGNORECASE)
    if m:
        specs['power_kw'] = m.group(1)

    m = re.search(r'(\d+(?:\.\d+)?)\s*kWh', name, re.IGNORECASE)
    if m:
        specs['capacity_kwh'] = m.group(1)

    m = re.search(r'(\d+(?:\.\d+)?)\s*W\b', name)
    if m:
        specs['power_w'] = m.group(1)

    # Voltage
    m = re.search(r'(\d+(?:\.\d+)?)\s*V\b', name)
    if m:
        specs['voltage'] = m.group(1)

    # Current
    m = re.search(r'(\d+)\s*A\b', name)
    if m:
        specs['current_a'] = m.group(1)

    m = re.search(r'(\d+)\s*Ah', name)
    if m:
        specs['capacity_ah'] = m.group(1)

    # Phase
    if 'mono faz' in name.lower() or 'monofaz' in name.lower():
        specs['phase'] = 'Mono Faz (Tek Faz)'
    elif 'tri faz' in name.lower() or 'trifaz' in name.lower():
        specs['phase'] = 'Tri Faz (Üç Faz)'

    # Voltage type
    if '380v' in name.lower():
        specs['input_voltage'] = '380V'
    elif '220v' in name.lower():
        specs['input_voltage'] = '220V'
    elif '3x220v' in name.lower():
        specs['input_voltage'] = '3x220V'

    # HV/LV
    if ' hv' in name.lower():
        specs['battery_type'] = 'Yüksek Gerilim (HV)'
    elif ' lv' in name.lower():
        specs['battery_type'] = 'Düşük Gerilim (LV)'

    return specs


def generate_html(product_type, specs, sku):
    """Generate URUNDETAY HTML based on product type and specs."""
    brand = specs['brand']
    name = specs['name']

    # Common brand descriptions
    brand_desc = {
        'Solinved': 'Solinved, Türkiye\'nin lider solar enerji ekipmanları tedarikçisi olarak geniş ürün yelpazesi ve rekabetçi fiyatlarıyla öne çıkmaktadır.',
        'Deye': 'Deye, dünya genelinde 180\'den fazla ülkede kullanılan, yenilenebilir enerji sektörünün önde gelen inverter ve enerji çözümleri üreticisidir.',
        'Solis': 'Solis (Ginlong), dünya çapında 2 milyondan fazla kurulumla kanıtlanmış güvenilirliği ile solar inverter sektörünün global liderlerinden biridir.',
        'BYD': 'BYD, dünyada lityum batarya teknolojisinin öncüsü ve enerji depolama sistemlerinde lider üreticidir. BYD bataryaları, üstün güvenlik ve uzun ömürleriyle tercih edilmektedir.',
    }

    bd = brand_desc.get(brand, f'{brand}, güneş enerjisi sektöründe güvenilir çözümler sunan bir üreticidir.')

    # ---- INVERTER HYBRID ----
    if product_type == 'inverter_hybrid':
        phase = specs.get('phase', 'Tri Faz')
        power = specs.get('power_kw', '?')
        btype = specs.get('battery_type', '')
        btype_text = f' {btype}' if btype else ''

        return f"""<p><strong>{name}</strong></p>
<p>{bd}</p>
<p>{brand} {power} kW {phase} Hibrit İnverter{btype_text}, güneş enerjisi sistemlerinde hem şebekeye bağlı (on-grid) hem de şebekeden bağımsız (off-grid) çalışabilme esnekliği sunar. Batarya depolama desteği sayesinde üretilen fazla enerji akülerde depolanarak gece saatlerinde veya kesinti anlarında kullanılabilir.</p>

<h4><strong>Öne Çıkan Özellikler</strong></h4>
<p>⚡ <strong>{power} kW Nominal Güç:</strong> Konut ve ticari uygulamalar için yüksek verimli enerji dönüşümü</p>
<p>🔋 <strong>Batarya Uyumlu:</strong> Lityum ve kurşun-asit bataryalarla entegre çalışır{', ' + btype + ' batarya uyumlu' if btype else ''}</p>
<p>🔄 <strong>Hibrit Çalışma:</strong> On-grid ve off-grid modları arasında otomatik geçiş</p>
<p>📊 <strong>Akıllı İzleme:</strong> WiFi/LAN üzerinden uzaktan izleme ve yönetim imkanı</p>
<p>🌞 <strong>Yüksek MPPT Verimi:</strong> Birden fazla MPPT girişi ile maksimum enerji hasadı</p>
<p>🛡️ <strong>Kapsamlı Koruma:</strong> Aşırı gerilim, aşırı akım, kısa devre ve toprak hata koruması</p>
<p>📱 <strong>{phase} Bağlantı:</strong> Türkiye şebeke koşullarına tam uyumlu</p>

<h4><strong>Teknik Bilgiler</strong></h4>
<figure class="table"><table><thead><tr><th>Özellik</th><th>Değer</th></tr></thead><tbody>
<tr><td><strong>Marka</strong></td><td>{brand}</td></tr>
<tr><td><strong>Model</strong></td><td>{sku}</td></tr>
<tr><td><strong>Nominal Güç</strong></td><td>{power} kW</td></tr>
<tr><td><strong>Tip</strong></td><td>Hibrit İnverter</td></tr>
<tr><td><strong>Faz</strong></td><td>{phase}</td></tr>
{f'<tr><td><strong>Batarya Tipi</strong></td><td>{btype}</td></tr>' if btype else ''}
<tr><td><strong>Garanti</strong></td><td>Üretici garantisi</td></tr>
</tbody></table></figure>

<p><strong>Türkiye Solar Market</strong> güvencesiyle orijinal {brand} ürünü. Teknik destek ve kurulum danışmanlığı için bizimle iletişime geçin.</p>"""

    # ---- INVERTER ON-GRID ----
    if product_type == 'inverter_ongrid':
        phase = specs.get('phase', 'Tri Faz')
        power = specs.get('power_kw', '?')

        return f"""<p><strong>{name}</strong></p>
<p>{bd}</p>
<p>{brand} {power} kW {phase} On-Grid String İnverter, güneş panellerinden üretilen DC elektriği yüksek verimle AC elektriğe çevirerek şebekeye besler. Ticari ve endüstriyel güneş enerji santrallerinde (GES) güvenilir performans sunar.</p>

<h4><strong>Öne Çıkan Özellikler</strong></h4>
<p>⚡ <strong>{power} kW Çıkış Gücü:</strong> Yüksek verimli DC-AC dönüşüm</p>
<p>📊 <strong>Çoklu MPPT:</strong> Birden fazla MPPT tracker ile farklı yönlerdeki panellerden maksimum verim</p>
<p>🔌 <strong>{phase}:</strong> Türkiye şebeke standartlarına uyumlu</p>
<p>📱 <strong>Uzaktan İzleme:</strong> WiFi/LAN üzerinden anlık üretim takibi</p>
<p>🛡️ <strong>Geniş Gerilim Aralığı:</strong> Değişken hava koşullarında stabil performans</p>
<p>🌡️ <strong>Yüksek Sıcaklık Dayanımı:</strong> IP65 koruma sınıfı, dış mekan kurulumuna uygun</p>

<h4><strong>Teknik Bilgiler</strong></h4>
<figure class="table"><table><thead><tr><th>Özellik</th><th>Değer</th></tr></thead><tbody>
<tr><td><strong>Marka</strong></td><td>{brand}</td></tr>
<tr><td><strong>Model</strong></td><td>{sku}</td></tr>
<tr><td><strong>Nominal Güç</strong></td><td>{power} kW</td></tr>
<tr><td><strong>Tip</strong></td><td>On-Grid String İnverter</td></tr>
<tr><td><strong>Faz</strong></td><td>{phase}</td></tr>
<tr><td><strong>Garanti</strong></td><td>Üretici garantisi</td></tr>
</tbody></table></figure>

<p><strong>Türkiye Solar Market</strong> güvencesiyle orijinal {brand} ürünü. Proje bazlı fiyat teklifi ve teknik destek için bizimle iletişime geçin.</p>"""

    # ---- INVERTER MICRO ----
    if product_type == 'inverter_micro':
        power = specs.get('power_w', specs.get('power_kw', '?'))
        unit = 'W' if 'power_w' in specs else 'kW'

        return f"""<p><strong>{name}</strong></p>
<p>{bd}</p>
<p>{brand} {power} {unit} Mikro İnverter, her güneş paneline ayrı ayrı takılarak panel bazında maksimum enerji hasadı sağlar. Gölgeleme ve panel uyumsuzluğu kayıplarını minimize eder.</p>

<h4><strong>Öne Çıkan Özellikler</strong></h4>
<p>⚡ <strong>Panel Bazında Optimizasyon:</strong> Her panel bağımsız çalışarak gölgelenme kayıplarını minimize eder</p>
<p>🔒 <strong>Güvenlik:</strong> Çatıda yüksek DC gerilim riski ortadan kalkar</p>
<p>📊 <strong>Panel Bazında İzleme:</strong> Her panelin performansını ayrı ayrı takip edin</p>
<p>🔧 <strong>Kolay Kurulum:</strong> Plug & play tasarım ile hızlı montaj</p>
<p>🛡️ <strong>IP67 Koruma:</strong> Her türlü hava koşuluna dayanıklı</p>
<p>📱 <strong>Uzaktan İzleme:</strong> Online portal üzerinden anlık üretim verileri</p>

<h4><strong>Teknik Bilgiler</strong></h4>
<figure class="table"><table><thead><tr><th>Özellik</th><th>Değer</th></tr></thead><tbody>
<tr><td><strong>Marka</strong></td><td>{brand}</td></tr>
<tr><td><strong>Model</strong></td><td>{sku}</td></tr>
<tr><td><strong>Nominal Güç</strong></td><td>{power} {unit}</td></tr>
<tr><td><strong>Tip</strong></td><td>Mikro İnverter</td></tr>
<tr><td><strong>Garanti</strong></td><td>Üretici garantisi</td></tr>
</tbody></table></figure>

<p><strong>Türkiye Solar Market</strong> güvencesiyle orijinal {brand} ürünü.</p>"""

    # ---- INVERTER OFF-GRID (Gordion, NML, Max etc) ----
    if product_type == 'inverter_offgrid':
        power = specs.get('power_kw', '?')
        voltage = specs.get('voltage', '48')

        return f"""<p><strong>{name}</strong></p>
<p>{bd}</p>
<p>{brand} {power} kW MPPT Off-Grid İnverter, şebekeden bağımsız güneş enerji sistemleri için tasarlanmış entegre MPPT şarj kontrolcülü inverterdir. Dahili MPPT sayesinde güneş panellerinden gelen enerjiyi en yüksek verimle bataryalara aktarır ve AC çıkış sağlar.</p>

<h4><strong>Öne Çıkan Özellikler</strong></h4>
<p>⚡ <strong>{power} kW Saf Sinüs Çıkış:</strong> Tüm ev aletleri ve hassas cihazlarla uyumlu</p>
<p>🔋 <strong>Dahili MPPT Şarj Kontrolcü:</strong> Güneş panellerinden maksimum enerji hasadı</p>
<p>🔌 <strong>{voltage}V DC Giriş:</strong> Batarya bağlantısı</p>
<p>🔄 <strong>Otomatik Şebeke/Solar/Batarya Geçişi:</strong> Kesintisiz güç kaynağı</p>
<p>📊 <strong>LCD Ekran:</strong> Anlık üretim, tüketim ve batarya durumu gösterimi</p>
<p>🛡️ <strong>Kapsamlı Koruma:</strong> Aşırı yük, kısa devre, düşük batarya koruması</p>

<h4><strong>Teknik Bilgiler</strong></h4>
<figure class="table"><table><thead><tr><th>Özellik</th><th>Değer</th></tr></thead><tbody>
<tr><td><strong>Marka</strong></td><td>{brand}</td></tr>
<tr><td><strong>Model</strong></td><td>{sku}</td></tr>
<tr><td><strong>Nominal Güç</strong></td><td>{power} kW</td></tr>
<tr><td><strong>Tip</strong></td><td>Off-Grid MPPT İnverter</td></tr>
<tr><td><strong>Batarya Gerilimi</strong></td><td>{voltage}V DC</td></tr>
<tr><td><strong>Garanti</strong></td><td>Üretici garantisi</td></tr>
</tbody></table></figure>

<p><strong>Türkiye Solar Market</strong> güvencesiyle orijinal {brand} ürünü. Bağ, bahçe, çiftlik ve yazlık evler için ideal çözüm.</p>"""

    # ---- INVERTER PORTABLE (Modified/Pure Sine, UPS) ----
    if product_type == 'inverter_portable':
        power = specs.get('power_w', '?')
        voltage = specs.get('voltage', '12')
        is_pure = 'pure' in name.lower() or 'saf' in name.lower()
        is_ups = 'ups' in name.lower()
        wave_type = 'Saf Sinüs (Pure Sine Wave)' if is_pure else 'Modifiye Sinüs (Modified Sine Wave)'

        ups_text = ''
        if is_ups:
            ups_text = '<p>🔌 <strong>UPS Fonksiyonu:</strong> Şebeke kesintisinde otomatik bataryaya geçiş, kesintisiz güç</p>\n'

        return f"""<p><strong>{name}</strong></p>
<p>{bd}</p>
<p>{brand} {power}W {wave_type.split('(')[0].strip()} İnverter, {voltage}V DC akü gerilimini 230V AC'ye dönüştürerek evde, karavanda, teknede veya şebekesiz alanlarda elektrik kullanımı sağlar.{' UPS özelliği ile şebeke kesintilerinde kesintisiz enerji aktarımı yapar.' if is_ups else ''}</p>

<h4><strong>Öne Çıkan Özellikler</strong></h4>
<p>⚡ <strong>{power}W Çıkış Gücü:</strong> {voltage}V DC → 230V AC dönüşüm</p>
<p>〰️ <strong>{wave_type}:</strong> {'Tüm elektronik cihazlarla uyumlu, hassas cihazlar için güvenli' if is_pure else 'Aydınlatma, fan, basit aletler için ekonomik çözüm'}</p>
{ups_text}<p>🛡️ <strong>Koruma Sistemleri:</strong> Aşırı yük, kısa devre, düşük batarya, aşırı sıcaklık koruması</p>
<p>🔌 <strong>Kolay Kullanım:</strong> Akü bağlantısı ve AC priz çıkışı ile anında kullanıma hazır</p>
<p>🚐 <strong>Taşınabilir:</strong> Kompakt tasarım, karavan, tekne ve açık alan kullanımına uygun</p>

<h4><strong>Teknik Bilgiler</strong></h4>
<figure class="table"><table><thead><tr><th>Özellik</th><th>Değer</th></tr></thead><tbody>
<tr><td><strong>Marka</strong></td><td>{brand}</td></tr>
<tr><td><strong>Model</strong></td><td>{sku}</td></tr>
<tr><td><strong>Çıkış Gücü</strong></td><td>{power}W</td></tr>
<tr><td><strong>Dalga Tipi</strong></td><td>{wave_type}</td></tr>
<tr><td><strong>Giriş Gerilimi</strong></td><td>{voltage}V DC</td></tr>
<tr><td><strong>Çıkış Gerilimi</strong></td><td>230V AC 50Hz</td></tr>
<tr><td><strong>Garanti</strong></td><td>Üretici garantisi</td></tr>
</tbody></table></figure>

<p><strong>Türkiye Solar Market</strong> güvencesiyle orijinal {brand} ürünü.</p>"""

    # ---- INVERTER ALL-IN-ONE (Aspendos) ----
    if product_type == 'inverter_allinone':
        power = specs.get('power_kw', '?')
        voltage = specs.get('voltage', '48')

        return f"""<p><strong>{name}</strong></p>
<p>{bd}</p>
<p>{brand} Aspendos All-In-One İnverter Modülü, MPPT şarj kontrolcü, inverter ve batarya yönetim sistemini tek bir cihazda birleştiren kompakt çözümdür. Off-grid ve hibrit sistemler için ideal olan bu cihaz, kurulum kolaylığı ve yüksek verim sağlar.</p>

<h4><strong>Öne Çıkan Özellikler</strong></h4>
<p>⚡ <strong>{power} kW Entegre Sistem:</strong> İnverter + MPPT şarj kontrolcü tek cihazda</p>
<p>🔋 <strong>{voltage}V Batarya Uyumlu:</strong> Lityum ve kurşun-asit bataryalarla çalışır</p>
<p>🔄 <strong>Çoklu Çalışma Modu:</strong> Solar öncelikli, batarya öncelikli, şebeke öncelikli</p>
<p>📊 <strong>Akıllı Enerji Yönetimi:</strong> Otomatik kaynak seçimi ve yük dengeleme</p>
<p>🛡️ <strong>Kapsamlı Koruma:</strong> Aşırı yük, kısa devre, düşük batarya koruması</p>

<h4><strong>Teknik Bilgiler</strong></h4>
<figure class="table"><table><thead><tr><th>Özellik</th><th>Değer</th></tr></thead><tbody>
<tr><td><strong>Marka</strong></td><td>{brand}</td></tr>
<tr><td><strong>Model</strong></td><td>{sku}</td></tr>
<tr><td><strong>Nominal Güç</strong></td><td>{power} kW</td></tr>
<tr><td><strong>Tip</strong></td><td>All-In-One İnverter Modülü</td></tr>
<tr><td><strong>Batarya Gerilimi</strong></td><td>{voltage}V DC</td></tr>
<tr><td><strong>Garanti</strong></td><td>Üretici garantisi</td></tr>
</tbody></table></figure>

<p><strong>Türkiye Solar Market</strong> güvencesiyle orijinal {brand} ürünü.</p>"""

    # ---- BATTERY LITHIUM ----
    if product_type in ('battery_lithium', 'battery_wall', 'battery_rack'):
        capacity = specs.get('capacity_kwh', '')
        voltage = specs.get('voltage', '')
        ah = specs.get('capacity_ah', '')

        cap_text = f'{capacity} kWh' if capacity else (f'{ah}Ah' if ah else '')
        form_text = ''
        if product_type == 'battery_wall':
            form_text = 'Duvar tipi kompakt tasarımıyla alan tasarrufu sağlar.'
        elif product_type == 'battery_rack':
            form_text = 'Rack tipi tasarımıyla profesyonel kurulumlar için idealdir.'

        return f"""<p><strong>{name}</strong></p>
<p>{bd}</p>
<p>{brand} {cap_text} Lityum Enerji Depolama Bataryası, güneş enerji sistemlerinde üretilen fazla enerjiyi depolayarak gece saatlerinde veya şebeke kesintilerinde kullanım imkanı sağlar. {form_text}</p>

<h4><strong>Öne Çıkan Özellikler</strong></h4>
<p>🔋 <strong>{cap_text} Kapasite:</strong> Ev ve ticari uygulamalar için yeterli enerji depolama</p>
<p>⚡ <strong>Lityum Demir Fosfat (LFP):</strong> Yüksek güvenlik, uzun ömür, 6000+ çevrim</p>
<p>🔄 <strong>Modüler Yapı:</strong> İhtiyaca göre kapasite artırma imkanı</p>
<p>🌞 <strong>Yüksek Verim:</strong> %95+ çevrim verimliliği ile minimum enerji kaybı</p>
<p>🛡️ <strong>BMS Koruması:</strong> Dahili batarya yönetim sistemi ile güvenli kullanım</p>
<p>📱 <strong>İnverter Uyumu:</strong> Lider hibrit inverter markalarıyla sorunsuz entegrasyon</p>

<h4><strong>Teknik Bilgiler</strong></h4>
<figure class="table"><table><thead><tr><th>Özellik</th><th>Değer</th></tr></thead><tbody>
<tr><td><strong>Marka</strong></td><td>{brand}</td></tr>
<tr><td><strong>Model</strong></td><td>{sku}</td></tr>
<tr><td><strong>Kapasite</strong></td><td>{cap_text}</td></tr>
{f'<tr><td><strong>Nominal Gerilim</strong></td><td>{voltage}V</td></tr>' if voltage else ''}
<tr><td><strong>Hücre Tipi</strong></td><td>LFP (Lityum Demir Fosfat)</td></tr>
<tr><td><strong>Garanti</strong></td><td>Üretici garantisi</td></tr>
</tbody></table></figure>

<p><strong>Türkiye Solar Market</strong> güvencesiyle orijinal {brand} ürünü. Enerji bağımsızlığınız için doğru yatırım.</p>"""

    # ---- BATTERY GEL ----
    if product_type == 'battery_gel':
        voltage = specs.get('voltage', '12')
        ah = specs.get('capacity_ah', '?')

        return f"""<p><strong>{name}</strong></p>
<p>{bd}</p>
<p>{brand} {voltage}V {ah}Ah Solar Jel Akü, güneş enerji sistemleri için özel olarak tasarlanmış derin deşarj (deep cycle) aküdür. Jel elektrolit teknolojisi sayesinde bakım gerektirmez ve her pozisyonda güvenle kullanılabilir.</p>

<h4><strong>Öne Çıkan Özellikler</strong></h4>
<p>🔋 <strong>{ah}Ah Kapasite:</strong> Uzun süreli enerji depolama</p>
<p>⚡ <strong>Deep Cycle:</strong> Derin deşarj dayanımı, güneş enerji sistemleri için optimize</p>
<p>🛡️ <strong>Jel Teknolojisi:</strong> Sızıntısız, bakımsız, güvenli</p>
<p>🌡️ <strong>Geniş Sıcaklık Aralığı:</strong> -20°C ile +60°C arası çalışma</p>
<p>♻️ <strong>Uzun Ömür:</strong> Yüksek çevrim sayısı ile uzun yıllar servis</p>

<h4><strong>Teknik Bilgiler</strong></h4>
<figure class="table"><table><thead><tr><th>Özellik</th><th>Değer</th></tr></thead><tbody>
<tr><td><strong>Marka</strong></td><td>{brand}</td></tr>
<tr><td><strong>Model</strong></td><td>{sku}</td></tr>
<tr><td><strong>Gerilim</strong></td><td>{voltage}V</td></tr>
<tr><td><strong>Kapasite</strong></td><td>{ah}Ah</td></tr>
<tr><td><strong>Tip</strong></td><td>Jel Akü (Deep Cycle)</td></tr>
<tr><td><strong>Garanti</strong></td><td>Üretici garantisi</td></tr>
</tbody></table></figure>

<p><strong>Türkiye Solar Market</strong> güvencesiyle orijinal {brand} ürünü.</p>"""

    # ---- BATTERY LEAD ACID ----
    if product_type == 'battery_lead':
        voltage = specs.get('voltage', '12')
        ah = specs.get('capacity_ah', '?')

        return f"""<p><strong>{name}</strong></p>
<p>{bd}</p>
<p>{brand} {voltage}V {ah}Ah Kurşun Asit Akü, UPS sistemleri, alarm, güvenlik ve küçük solar uygulamalar için güvenilir enerji depolama çözümüdür. Bakım gerektirmeyen kapalı yapısıyla her ortamda güvenle kullanılabilir.</p>

<h4><strong>Öne Çıkan Özellikler</strong></h4>
<p>🔋 <strong>{ah}Ah Kapasite:</strong> UPS, alarm ve güvenlik sistemleri için ideal</p>
<p>🛡️ <strong>VRLA Teknoloji:</strong> Bakımsız, sızıntısız, kapalı yapı</p>
<p>⚡ <strong>Anlık Yüksek Akım:</strong> Acil durum yedekleme için yeterli güç</p>
<p>🔌 <strong>Kolay Montaj:</strong> Standart terminaller ile hızlı bağlantı</p>

<h4><strong>Teknik Bilgiler</strong></h4>
<figure class="table"><table><thead><tr><th>Özellik</th><th>Değer</th></tr></thead><tbody>
<tr><td><strong>Marka</strong></td><td>{brand}</td></tr>
<tr><td><strong>Model</strong></td><td>{sku}</td></tr>
<tr><td><strong>Gerilim</strong></td><td>{voltage}V</td></tr>
<tr><td><strong>Kapasite</strong></td><td>{ah}Ah</td></tr>
<tr><td><strong>Tip</strong></td><td>Kurşun Asit (VRLA/SLA)</td></tr>
<tr><td><strong>Garanti</strong></td><td>Üretici garantisi</td></tr>
</tbody></table></figure>

<p><strong>Türkiye Solar Market</strong> güvencesiyle orijinal {brand} ürünü.</p>"""

    # ---- PUMP DRIVER ----
    if product_type == 'pump_driver':
        power = specs.get('power_kw', '?')
        phase = specs.get('phase', '')
        input_v = specs.get('input_voltage', '')

        return f"""<p><strong>{name}</strong></p>
<p>{bd}</p>
<p>{brand} {power} kW {phase + ' ' if phase else ''}Solar Pompa Sürücü, güneş panellerinden gelen DC enerjiyi kullanarak su pompalarını doğrudan çalıştıran frekans dönüştürücüdür. Tarımsal sulama, hayvancılık ve su temin sistemlerinde şebeke bağlantısı olmadan çalışabilir.</p>

<h4><strong>Öne Çıkan Özellikler</strong></h4>
<p>⚡ <strong>{power} kW Güç:</strong> Dalgıç ve yüzey pompalarını sürebilir</p>
<p>🌞 <strong>Doğrudan Solar Besleme:</strong> PV panellerden direkt çalışma, bataryaya gerek yok</p>
<p>🔄 <strong>MPPT Algoritma:</strong> Güneş enerjisinden maksimum verim</p>
<p>💧 <strong>Kuru Çalışma Koruması:</strong> Susuz çalışmada otomatik durma</p>
<p>📊 <strong>LCD Ekran:</strong> Anlık debi, basınç ve enerji bilgileri</p>
<p>🛡️ <strong>IP Koruma:</strong> Dış mekan kurulumuna uygun dayanıklı yapı</p>
{f'<p>🔌 <strong>{input_v} Giriş:</strong> {phase}</p>' if input_v else ''}

<h4><strong>Teknik Bilgiler</strong></h4>
<figure class="table"><table><thead><tr><th>Özellik</th><th>Değer</th></tr></thead><tbody>
<tr><td><strong>Marka</strong></td><td>{brand}</td></tr>
<tr><td><strong>Model</strong></td><td>{sku}</td></tr>
<tr><td><strong>Nominal Güç</strong></td><td>{power} kW</td></tr>
<tr><td><strong>Tip</strong></td><td>Solar Pompa Sürücü (VFD)</td></tr>
{f'<tr><td><strong>Faz</strong></td><td>{phase}</td></tr>' if phase else ''}
{f'<tr><td><strong>Giriş Gerilimi</strong></td><td>{input_v}</td></tr>' if input_v else ''}
<tr><td><strong>Garanti</strong></td><td>Üretici garantisi</td></tr>
</tbody></table></figure>

<p><strong>Türkiye Solar Market</strong> güvencesiyle orijinal {brand} ürünü. Tarımsal sulama projeniz için teknik destek alın.</p>"""

    # ---- PUMP PANEL ----
    if product_type == 'pump_panel':
        # Extract kW range from name
        m = re.search(r'(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)\s*kW', name)
        kw_range = f'{m.group(1)}-{m.group(2)} kW' if m else ''

        return f"""<p><strong>{name}</strong></p>
<p>{bd}</p>
<p>{brand} {kw_range + ' ' if kw_range else ''}Pompa Sürücü Panosu, solar pompa sürücüler için hazır elektrik panosu çözümüdür. İçerisinde gerekli koruma elemanları, sigorta, devre kesici ve bağlantı klemensleri bulunur.</p>

<h4><strong>Öne Çıkan Özellikler</strong></h4>
<p>📦 <strong>Hazır Pano:</strong> Tüm koruma ve bağlantı elemanları dahil</p>
<p>🛡️ <strong>Koruma Elemanları:</strong> AC/DC sigorta, devre kesici, SPD (yıldırımdan koruma)</p>
<p>🔧 <strong>Kolay Kurulum:</strong> Plug & play bağlantı, hızlı devreye alma</p>
<p>⚡ <strong>{kw_range + ' Aralık:' if kw_range else 'Uyumluluk:'}</strong> Belirtilen güç aralığındaki pompa sürücülerle uyumlu</p>

<h4><strong>Teknik Bilgiler</strong></h4>
<figure class="table"><table><thead><tr><th>Özellik</th><th>Değer</th></tr></thead><tbody>
<tr><td><strong>Marka</strong></td><td>{brand}</td></tr>
<tr><td><strong>Model</strong></td><td>{sku}</td></tr>
{f'<tr><td><strong>Güç Aralığı</strong></td><td>{kw_range}</td></tr>' if kw_range else ''}
<tr><td><strong>Tip</strong></td><td>Pompa Sürücü Panosu</td></tr>
<tr><td><strong>Garanti</strong></td><td>Üretici garantisi</td></tr>
</tbody></table></figure>

<p><strong>Türkiye Solar Market</strong> güvencesiyle orijinal {brand} ürünü.</p>"""

    # ---- CHARGE CONTROLLER MPPT ----
    if product_type == 'charge_mppt':
        current = specs.get('current_a', '?')
        voltage = specs.get('voltage', '')

        return f"""<p><strong>{name}</strong></p>
<p>{bd}</p>
<p>{brand} {current}A MPPT Şarj Kontrol Cihazı, güneş panellerinden gelen enerjiyi en verimli şekilde bataryalara aktaran MPPT (Maximum Power Point Tracking) teknolojili şarj kontrolcüdür. Geleneksel PWM kontrolcülere göre %20-30 daha fazla enerji hasadı sağlar.</p>

<h4><strong>Öne Çıkan Özellikler</strong></h4>
<p>⚡ <strong>{current}A Şarj Akımı:</strong> Yüksek güçlü panel dizileri için yeterli kapasite</p>
<p>📊 <strong>MPPT Teknolojisi:</strong> Değişken hava koşullarında bile maksimum verim</p>
<p>🔋 <strong>Çoklu Batarya Desteği:</strong> Lityum, jel, AGM ve sulu akülerle uyumlu</p>
{f'<p>🔌 <strong>{voltage}V Sistem:</strong> Batarya gerilim desteği</p>' if voltage else ''}
<p>📱 <strong>LCD Ekran:</strong> Anlık şarj akımı, batarya durumu ve üretim verileri</p>
<p>🛡️ <strong>Tam Koruma:</strong> Aşırı şarj, ters polarite, kısa devre koruması</p>

<h4><strong>Teknik Bilgiler</strong></h4>
<figure class="table"><table><thead><tr><th>Özellik</th><th>Değer</th></tr></thead><tbody>
<tr><td><strong>Marka</strong></td><td>{brand}</td></tr>
<tr><td><strong>Model</strong></td><td>{sku}</td></tr>
<tr><td><strong>Şarj Akımı</strong></td><td>{current}A</td></tr>
<tr><td><strong>Teknoloji</strong></td><td>MPPT</td></tr>
{f'<tr><td><strong>Sistem Gerilimi</strong></td><td>{voltage}V</td></tr>' if voltage else ''}
<tr><td><strong>Garanti</strong></td><td>Üretici garantisi</td></tr>
</tbody></table></figure>

<p><strong>Türkiye Solar Market</strong> güvencesiyle orijinal {brand} ürünü.</p>"""

    # ---- CHARGE CONTROLLER PWM ----
    if product_type == 'charge_pwm':
        current = specs.get('current_a', '?')

        return f"""<p><strong>{name}</strong></p>
<p>{bd}</p>
<p>{brand} {current}A PWM Şarj Kontrol Cihazı, güneş panellerinden gelen enerjiyi bataryalara güvenli şekilde aktaran ekonomik şarj kontrolcüdür. Küçük ve orta ölçekli off-grid sistemler için ideal çözümdür.</p>

<h4><strong>Öne Çıkan Özellikler</strong></h4>
<p>⚡ <strong>{current}A Şarj Akımı:</strong> Küçük-orta ölçekli sistemler için yeterli</p>
<p>🔋 <strong>Batarya Koruma:</strong> Aşırı şarj ve derin deşarj koruması ile akü ömrünü uzatır</p>
<p>📊 <strong>LED/LCD Gösterge:</strong> Batarya durumu ve şarj bilgileri</p>
<p>🛡️ <strong>Tam Koruma:</strong> Ters polarite, kısa devre, aşırı yük koruması</p>
<p>🔌 <strong>Kolay Kurulum:</strong> Basit kablolama ile hızlı devreye alma</p>

<h4><strong>Teknik Bilgiler</strong></h4>
<figure class="table"><table><thead><tr><th>Özellik</th><th>Değer</th></tr></thead><tbody>
<tr><td><strong>Marka</strong></td><td>{brand}</td></tr>
<tr><td><strong>Model</strong></td><td>{sku}</td></tr>
<tr><td><strong>Şarj Akımı</strong></td><td>{current}A</td></tr>
<tr><td><strong>Teknoloji</strong></td><td>PWM</td></tr>
<tr><td><strong>Garanti</strong></td><td>Üretici garantisi</td></tr>
</tbody></table></figure>

<p><strong>Türkiye Solar Market</strong> güvencesiyle orijinal {brand} ürünü.</p>"""

    # ---- SOLAR CAMERA ----
    if product_type == 'solar_camera':
        conn_type = '4G' if '4g' in name.lower() else ('WiFi' if 'wifi' in name.lower() else '')

        return f"""<p><strong>{name}</strong></p>
<p>{bd}</p>
<p>{brand} Solar Kamera {conn_type}, güneş enerjisi ile çalışan kablosuz güvenlik kamerasıdır. Dahili solar panel ve şarj edilebilir batarya sayesinde elektrik hattı çekilemeyen alanlarda 7/24 güvenlik sağlar.</p>

<h4><strong>Öne Çıkan Özellikler</strong></h4>
<p>☀️ <strong>Solar Beslemeli:</strong> Dahili güneş paneli, elektrik hattına gerek yok</p>
<p>📡 <strong>{conn_type} Bağlantı:</strong> {'SIM kart ile her yerden uzaktan erişim' if '4G' in conn_type else 'WiFi üzerinden uzaktan izleme'}</p>
<p>📹 <strong>Yüksek Çözünürlük:</strong> Gece görüşlü, hareket algılamalı kayıt</p>
<p>🔋 <strong>Şarj Edilebilir Batarya:</strong> Bulutlu günlerde bile kesintisiz çalışma</p>
<p>📱 <strong>Mobil Uygulama:</strong> Canlı izleme ve anlık bildirim</p>
<p>🛡️ <strong>IP Koruma:</strong> Dış mekan koşullarına dayanıklı</p>

<h4><strong>Teknik Bilgiler</strong></h4>
<figure class="table"><table><thead><tr><th>Özellik</th><th>Değer</th></tr></thead><tbody>
<tr><td><strong>Marka</strong></td><td>{brand}</td></tr>
<tr><td><strong>Model</strong></td><td>{sku}</td></tr>
<tr><td><strong>Bağlantı</strong></td><td>{conn_type}</td></tr>
<tr><td><strong>Besleme</strong></td><td>Solar + Batarya</td></tr>
<tr><td><strong>Garanti</strong></td><td>Üretici garantisi</td></tr>
</tbody></table></figure>

<p><strong>Türkiye Solar Market</strong> güvencesiyle orijinal {brand} ürünü. Çiftlik, tarla, bağ-bahçe güvenliği için ideal.</p>"""

    # ---- SOLAR ROUTER ----
    if product_type == 'solar_router':
        return f"""<p><strong>{name}</strong></p>
<p>{bd}</p>
<p>{brand} Solar Router 4G, güneş enerji sistemlerinde uzaktan izleme ve internet erişimi sağlayan 4G destekli router cihazıdır. SIM kart ile şebekesiz alanlarda bile inverter ve enerji sistemlerinin uzaktan yönetimini mümkün kılar.</p>

<h4><strong>Öne Çıkan Özellikler</strong></h4>
<p>📡 <strong>4G LTE Bağlantı:</strong> SIM kart ile her yerden internet erişimi</p>
<p>🌞 <strong>Solar Sistem Uyumlu:</strong> İnverter izleme portallarına bağlantı</p>
<p>🔌 <strong>Düşük Güç Tüketimi:</strong> 12V/24V DC besleme, solar sisteme uyumlu</p>
<p>📱 <strong>Uzaktan Yönetim:</strong> Web arayüzü üzerinden konfigürasyon</p>

<h4><strong>Teknik Bilgiler</strong></h4>
<figure class="table"><table><thead><tr><th>Özellik</th><th>Değer</th></tr></thead><tbody>
<tr><td><strong>Marka</strong></td><td>{brand}</td></tr>
<tr><td><strong>Model</strong></td><td>{sku}</td></tr>
<tr><td><strong>Bağlantı</strong></td><td>4G LTE</td></tr>
<tr><td><strong>Garanti</strong></td><td>Üretici garantisi</td></tr>
</tbody></table></figure>

<p><strong>Türkiye Solar Market</strong> güvencesiyle orijinal {brand} ürünü.</p>"""

    # ---- DC FUSE ----
    if product_type == 'dc_fuse':
        current = specs.get('current_a', '?')
        voltage = specs.get('voltage', '1000')

        return f"""<p><strong>{name}</strong></p>
<p>{bd}</p>
<p>{brand} {current}A {voltage}V DC Sigorta, güneş enerji sistemlerinde DC taraf koruma elemanı olarak kullanılır. PV panel dizileri ve batarya hatlarında aşırı akım ve kısa devre koruması sağlar.</p>

<h4><strong>Öne Çıkan Özellikler</strong></h4>
<p>⚡ <strong>{current}A / {voltage}V DC:</strong> Solar sistemler için yüksek gerilim dayanımı</p>
<p>🛡️ <strong>Hızlı Müdahale:</strong> Aşırı akımda anında devre kesme</p>
<p>🔧 <strong>Kolay Değişim:</strong> Standart 10x38mm boyut</p>
<p>☀️ <strong>Solar Sertifikalı:</strong> PV sistemleri için özel tasarım</p>

<h4><strong>Teknik Bilgiler</strong></h4>
<figure class="table"><table><thead><tr><th>Özellik</th><th>Değer</th></tr></thead><tbody>
<tr><td><strong>Marka</strong></td><td>{brand}</td></tr>
<tr><td><strong>Model</strong></td><td>{sku}</td></tr>
<tr><td><strong>Anma Akımı</strong></td><td>{current}A</td></tr>
<tr><td><strong>Anma Gerilimi</strong></td><td>{voltage}V DC</td></tr>
<tr><td><strong>Garanti</strong></td><td>Üretici garantisi</td></tr>
</tbody></table></figure>

<p><strong>Türkiye Solar Market</strong> güvencesiyle orijinal {brand} ürünü.</p>"""

    # ---- DC FUSE HOLDER ----
    if product_type == 'dc_fuse_holder':
        return f"""<p><strong>{name}</strong></p>
<p>{bd}</p>
<p>{brand} DC Sigorta Yuvası, 10x38mm standart DC sigortalar için sigorta taşıyıcıdır. DIN ray montajlı kompakt tasarımıyla güneş enerji panolarında kullanılır.</p>

<h4><strong>Öne Çıkan Özellikler</strong></h4>
<p>🔧 <strong>10x38mm Uyumlu:</strong> Standart DC sigortalar için</p>
<p>📦 <strong>DIN Ray Montaj:</strong> Panoya kolay montaj</p>
<p>🛡️ <strong>Yüksek İzolasyon:</strong> DC sistemler için güvenli kullanım</p>

<h4><strong>Teknik Bilgiler</strong></h4>
<figure class="table"><table><thead><tr><th>Özellik</th><th>Değer</th></tr></thead><tbody>
<tr><td><strong>Marka</strong></td><td>{brand}</td></tr>
<tr><td><strong>Model</strong></td><td>{sku}</td></tr>
<tr><td><strong>Sigorta Boyutu</strong></td><td>10x38mm</td></tr>
<tr><td><strong>Garanti</strong></td><td>Üretici garantisi</td></tr>
</tbody></table></figure>

<p><strong>Türkiye Solar Market</strong> güvencesiyle orijinal {brand} ürünü.</p>"""

    # ---- DC BREAKER ----
    if product_type == 'dc_breaker':
        current = specs.get('current_a', '?')
        voltage = specs.get('voltage', '1000')

        return f"""<p><strong>{name}</strong></p>
<p>{bd}</p>
<p>{brand} DC {current}A {voltage}V Devre Kesici, güneş enerji sistemlerinde DC taraf ana şalteri olarak kullanılır. Bakım ve arıza durumlarında güvenli devre kesme imkanı sağlar. Aşırı akım ve kısa devrede otomatik açma özelliğine sahiptir.</p>

<h4><strong>Öne Çıkan Özellikler</strong></h4>
<p>⚡ <strong>{current}A / {voltage}V DC:</strong> Yüksek güçlü solar sistemler için</p>
<p>🛡️ <strong>Otomatik Trip:</strong> Aşırı akımda otomatik devre kesme</p>
<p>🔧 <strong>Manuel Açma/Kapama:</strong> Bakım çalışmalarında güvenli izolasyon</p>
<p>📦 <strong>DIN Ray Montaj:</strong> Standart pano montajı</p>

<h4><strong>Teknik Bilgiler</strong></h4>
<figure class="table"><table><thead><tr><th>Özellik</th><th>Değer</th></tr></thead><tbody>
<tr><td><strong>Marka</strong></td><td>{brand}</td></tr>
<tr><td><strong>Model</strong></td><td>{sku}</td></tr>
<tr><td><strong>Anma Akımı</strong></td><td>{current}A</td></tr>
<tr><td><strong>Anma Gerilimi</strong></td><td>{voltage}V DC</td></tr>
<tr><td><strong>Garanti</strong></td><td>Üretici garantisi</td></tr>
</tbody></table></figure>

<p><strong>Türkiye Solar Market</strong> güvencesiyle orijinal {brand} ürünü.</p>"""

    # ---- MC4 CONNECTOR ----
    if product_type == 'mc4_connector':
        voltage = specs.get('voltage', '1000')

        return f"""<p><strong>{name}</strong></p>
<p>{bd}</p>
<p>{brand} MC4 Solar Konnektör Seti, güneş panelleri arasındaki kablo bağlantıları için endüstri standardı MC4 konnektördür. {voltage}V DC gerilime dayanıklı, su geçirmez yapısıyla dış mekan kurulumlarında güvenle kullanılır.</p>

<h4><strong>Öne Çıkan Özellikler</strong></h4>
<p>🔌 <strong>MC4 Standart:</strong> Tüm solar panel ve kablolarla uyumlu</p>
<p>🛡️ <strong>{voltage}V DC Dayanım:</strong> Yüksek gerilim solar diziler için</p>
<p>💧 <strong>IP67 Su Geçirmez:</strong> Dış mekan koşullarına tam dayanıklılık</p>
<p>⚡ <strong>Düşük Temas Direnci:</strong> Minimum enerji kaybı</p>

<h4><strong>Teknik Bilgiler</strong></h4>
<figure class="table"><table><thead><tr><th>Özellik</th><th>Değer</th></tr></thead><tbody>
<tr><td><strong>Marka</strong></td><td>{brand}</td></tr>
<tr><td><strong>Model</strong></td><td>{sku}</td></tr>
<tr><td><strong>Gerilim Dayanımı</strong></td><td>{voltage}V DC</td></tr>
<tr><td><strong>Koruma</strong></td><td>IP67</td></tr>
<tr><td><strong>Garanti</strong></td><td>Üretici garantisi</td></tr>
</tbody></table></figure>

<p><strong>Türkiye Solar Market</strong> güvencesiyle orijinal {brand} ürünü.</p>"""

    # ---- MC4 CRIMPING TOOL ----
    if product_type == 'mc4_tool':
        return f"""<p><strong>{name}</strong></p>
<p>{bd}</p>
<p>{brand} MC4 Sıkma Pensesi (Crimping Tool), MC4 solar konnektörlerin kablolara profesyonel sıkıştırma yapılması için kullanılan özel el aletidir. Doğru sıkıştırma ile düşük temas direnci ve güvenli bağlantı sağlar.</p>

<h4><strong>Öne Çıkan Özellikler</strong></h4>
<p>🔧 <strong>MC4 Uyumlu:</strong> Standart MC4 konnektörler için özel tasarım</p>
<p>⚡ <strong>Profesyonel Sıkıştırma:</strong> Düşük temas direnci, güvenli bağlantı</p>
<p>🛡️ <strong>Dayanıklı Yapı:</strong> Uzun ömürlü çelik gövde</p>
<p>🔌 <strong>Ergonomik Tasarım:</strong> Rahat kullanım için kaymaz tutamak</p>

<h4><strong>Teknik Bilgiler</strong></h4>
<figure class="table"><table><thead><tr><th>Özellik</th><th>Değer</th></tr></thead><tbody>
<tr><td><strong>Marka</strong></td><td>{brand}</td></tr>
<tr><td><strong>Model</strong></td><td>{sku}</td></tr>
<tr><td><strong>Tip</strong></td><td>MC4 Crimping Tool</td></tr>
<tr><td><strong>Garanti</strong></td><td>Üretici garantisi</td></tr>
</tbody></table></figure>

<p><strong>Türkiye Solar Market</strong> güvencesiyle orijinal {brand} ürünü.</p>"""

    # ---- SMART METER ----
    if product_type == 'smart_meter':
        phase = specs.get('phase', '')

        return f"""<p><strong>{name}</strong></p>
<p>{bd}</p>
<p>{brand} {phase + ' ' if phase else ''}Smart Meter, güneş enerji sistemlerinde enerji akışını izlemek için kullanılan akıllı sayaçtır. İnverter ile entegre çalışarak üretim, tüketim ve şebekeye verilen/alınan enerji miktarını gerçek zamanlı ölçer.</p>

<h4><strong>Öne Çıkan Özellikler</strong></h4>
<p>📊 <strong>Gerçek Zamanlı Ölçüm:</strong> Üretim, tüketim ve şebeke akışını anlık izleme</p>
<p>🔌 <strong>İnverter Entegrasyonu:</strong> {brand} inverterler ile doğrudan iletişim</p>
<p>⚡ <strong>Sıfır Enjeksiyon:</strong> Şebekeye fazla enerji verilmesini önleme desteği</p>
<p>📱 <strong>Uzaktan İzleme:</strong> İnverter portalı üzerinden enerji verileri</p>
<p>🔧 <strong>Kolay Kurulum:</strong> DIN ray montaj, CT sensör dahil olabilir</p>

<h4><strong>Teknik Bilgiler</strong></h4>
<figure class="table"><table><thead><tr><th>Özellik</th><th>Değer</th></tr></thead><tbody>
<tr><td><strong>Marka</strong></td><td>{brand}</td></tr>
<tr><td><strong>Model</strong></td><td>{sku}</td></tr>
{f'<tr><td><strong>Faz</strong></td><td>{phase}</td></tr>' if phase else ''}
<tr><td><strong>Tip</strong></td><td>Enerji Sayacı (Smart Meter)</td></tr>
<tr><td><strong>Garanti</strong></td><td>Üretici garantisi</td></tr>
</tbody></table></figure>

<p><strong>Türkiye Solar Market</strong> güvencesiyle orijinal {brand} ürünü.</p>"""

    # ---- COMMUNICATION ACCESSORIES ----
    if product_type == 'accessory_comm':
        conn_type = 'WiFi' if 'wifi' in name.lower() else 'LAN' if 'lan' in name.lower() else 'İletişim'

        return f"""<p><strong>{name}</strong></p>
<p>{bd}</p>
<p>{brand} {conn_type} {'Stick' if 'stick' in name.lower() else 'Dongle' if 'dongle' in name.lower() else 'Logger' if 'logger' in name.lower() else 'Modül'}, inverterinizin uzaktan izlenmesini sağlayan iletişim aksesuarıdır. {conn_type} bağlantısı üzerinden inverter verilerinizi cep telefonunuzdan veya bilgisayarınızdan gerçek zamanlı takip edebilirsiniz.</p>

<h4><strong>Öne Çıkan Özellikler</strong></h4>
<p>📡 <strong>{conn_type} Bağlantı:</strong> {'Kablosuz' if conn_type == 'WiFi' else 'Ethernet kablo ile'} inverter izleme</p>
<p>📱 <strong>Mobil Uygulama:</strong> Anlık üretim ve performans verileri</p>
<p>📊 <strong>Veri Loglama:</strong> Tarihsel üretim kayıtları ve raporlama</p>
<p>🔌 <strong>Kolay Kurulum:</strong> İnverter üzerindeki portuna takılır, plug & play</p>
<p>🛡️ <strong>Uyarı Sistemi:</strong> Arıza ve performans düşüşü bildirimleri</p>

<h4><strong>Teknik Bilgiler</strong></h4>
<figure class="table"><table><thead><tr><th>Özellik</th><th>Değer</th></tr></thead><tbody>
<tr><td><strong>Marka</strong></td><td>{brand}</td></tr>
<tr><td><strong>Model</strong></td><td>{sku}</td></tr>
<tr><td><strong>Bağlantı Tipi</strong></td><td>{conn_type}</td></tr>
<tr><td><strong>Uyumluluk</strong></td><td>{brand} inverterler</td></tr>
<tr><td><strong>Garanti</strong></td><td>Üretici garantisi</td></tr>
</tbody></table></figure>

<p><strong>Türkiye Solar Market</strong> güvencesiyle orijinal {brand} ürünü.</p>"""

    # ---- MOUNTING ----
    if product_type == 'mounting':
        # Extract panel count from name
        m = re.search(r'(\d+)x(\d+)', name)
        config = f'{m.group(1)} sıra × {m.group(2)} panel' if m else ''

        return f"""<p><strong>{name}</strong></p>
<p>{bd}</p>
<p>{brand} Solar Montaj Yapı Seti, güneş panellerinin çatı veya zemine güvenli şekilde montajı için gerekli tüm yapısal elemanları içeren komple settir. {config + ' konfigürasyonu ile kurulum kolaylığı sağlar.' if config else ''}</p>

<h4><strong>Öne Çıkan Özellikler</strong></h4>
<p>🔩 <strong>Komple Set:</strong> Ray, kelepçe, bağlantı elemanları dahil</p>
<p>🛡️ <strong>Alüminyum Yapı:</strong> Korozyona dayanıklı, hafif ve sağlam</p>
<p>🔧 <strong>Kolay Montaj:</strong> Standart aletlerle hızlı kurulum</p>
<p>🌬️ <strong>Rüzgar Dayanımı:</strong> Türkiye iklim koşullarına uygun hesaplar</p>
<p>☀️ <strong>Evrensel Uyum:</strong> Farklı panel boyutlarına uyarlanabilir</p>

<h4><strong>Teknik Bilgiler</strong></h4>
<figure class="table"><table><thead><tr><th>Özellik</th><th>Değer</th></tr></thead><tbody>
<tr><td><strong>Marka</strong></td><td>{brand}</td></tr>
<tr><td><strong>Model</strong></td><td>{sku}</td></tr>
{f'<tr><td><strong>Konfigürasyon</strong></td><td>{config}</td></tr>' if config else ''}
<tr><td><strong>Malzeme</strong></td><td>Alüminyum</td></tr>
<tr><td><strong>Garanti</strong></td><td>Üretici garantisi</td></tr>
</tbody></table></figure>

<p><strong>Türkiye Solar Market</strong> güvencesiyle orijinal {brand} ürünü.</p>"""

    # ---- EXPORT POWER MANAGER ----
    if product_type == 'export_manager':
        m = re.search(r'(\d+)\s*Inverter', name, re.IGNORECASE)
        inv_count = m.group(1) if m else '?'

        return f"""<p><strong>{name}</strong></p>
<p>{bd}</p>
<p>{brand} Export Power Manager, güneş enerji santrallerinde şebekeye verilen gücü yöneten kontrol cihazıdır. En fazla {inv_count} inverteri tek merkezden kontrol ederek sıfır enjeksiyon, güç sınırlama ve reaktif güç kompanzasyonu fonksiyonlarını yerine getirir.</p>

<h4><strong>Öne Çıkan Özellikler</strong></h4>
<p>⚡ <strong>{inv_count} İnverter Desteği:</strong> Tek cihazdan çoklu inverter yönetimi</p>
<p>📊 <strong>Sıfır Enjeksiyon:</strong> Şebekeye fazla enerji verilmesini önler</p>
<p>🔌 <strong>Güç Sınırlama:</strong> Dağıtım şirketi limitine uyum</p>
<p>📱 <strong>Uzaktan İzleme:</strong> Anlık güç yönetimi ve raporlama</p>

<h4><strong>Teknik Bilgiler</strong></h4>
<figure class="table"><table><thead><tr><th>Özellik</th><th>Değer</th></tr></thead><tbody>
<tr><td><strong>Marka</strong></td><td>{brand}</td></tr>
<tr><td><strong>Model</strong></td><td>{sku}</td></tr>
<tr><td><strong>Maks. İnverter</strong></td><td>{inv_count} adet</td></tr>
<tr><td><strong>Garanti</strong></td><td>Üretici garantisi</td></tr>
</tbody></table></figure>

<p><strong>Türkiye Solar Market</strong> güvencesiyle orijinal {brand} ürünü.</p>"""

    # ---- CONTROL BOX ----
    if product_type == 'control_box':
        return f"""<p><strong>{name}</strong></p>
<p>{bd}</p>
<p>{brand} XH Control Box, solar enerji sistemleri için kontrol ve izleme ünitesidir. Sistem bileşenleri arasında iletişimi koordine ederek verimli enerji yönetimi sağlar.</p>

<h4><strong>Öne Çıkan Özellikler</strong></h4>
<p>📊 <strong>Merkezi Kontrol:</strong> Sistem bileşenlerinin koordinasyonu</p>
<p>🔌 <strong>Kolay Entegrasyon:</strong> {brand} ürünleriyle sorunsuz çalışma</p>
<p>🛡️ <strong>Koruma:</strong> Güvenli ve stabil sistem yönetimi</p>

<h4><strong>Teknik Bilgiler</strong></h4>
<figure class="table"><table><thead><tr><th>Özellik</th><th>Değer</th></tr></thead><tbody>
<tr><td><strong>Marka</strong></td><td>{brand}</td></tr>
<tr><td><strong>Model</strong></td><td>{sku}</td></tr>
<tr><td><strong>Garanti</strong></td><td>Üretici garantisi</td></tr>
</tbody></table></figure>

<p><strong>Türkiye Solar Market</strong> güvencesiyle orijinal {brand} ürünü.</p>"""

    # ---- EV CHARGER ----
    if product_type == 'ev_charger':
        return f"""<p><strong>{name}</strong></p>
<p>{bd}</p>
<p>{brand} EV Şarj Cihazı, elektrikli araçlarınızı evde veya işyerinizde güvenle şarj etmenizi sağlar. Akıllı şarj yönetimi ve güvenlik özellikleriyle donatılmıştır.</p>

<h4><strong>Öne Çıkan Özellikler</strong></h4>
<p>⚡ <strong>Hızlı Şarj:</strong> Elektrikli aracınızı verimli şekilde şarj edin</p>
<p>🔒 <strong>Güvenlik:</strong> Aşırı akım, kaçak akım ve toprak hata koruması</p>
<p>📱 <strong>Akıllı Yönetim:</strong> Şarj programlama ve izleme</p>
<p>🔌 <strong>Kolay Kurulum:</strong> Duvar montajlı kompakt tasarım</p>

<h4><strong>Teknik Bilgiler</strong></h4>
<figure class="table"><table><thead><tr><th>Özellik</th><th>Değer</th></tr></thead><tbody>
<tr><td><strong>Marka</strong></td><td>{brand}</td></tr>
<tr><td><strong>Model</strong></td><td>{sku}</td></tr>
<tr><td><strong>Garanti</strong></td><td>Üretici garantisi</td></tr>
</tbody></table></figure>

<p><strong>Türkiye Solar Market</strong> güvencesiyle orijinal {brand} ürünü.</p>"""

    # ---- SOLAR PANEL ----
    if product_type == 'solar_panel':
        power = specs.get('power_w', specs.get('power_kw', '?'))
        unit = 'W' if 'power_w' in specs else 'kW'

        return f"""<p><strong>{name}</strong></p>
<p>{bd}</p>
<p>{brand} {power}{unit} Güneş Paneli, yüksek verimli monokristal hücre teknolojisiyle elektrik üretimi sağlar. Konut, ticari ve endüstriyel güneş enerji sistemleri için uygundur.</p>

<h4><strong>Öne Çıkan Özellikler</strong></h4>
<p>☀️ <strong>{power}{unit} Güç:</strong> Yüksek verimli enerji üretimi</p>
<p>🔬 <strong>Monokristal Hücre:</strong> Yüksek verimlilik oranı</p>
<p>🛡️ <strong>Dayanıklılık:</strong> Anti-PID, tuz sisi ve amonyak direnci</p>
<p>🌡️ <strong>Düşük Sıcaklık Katsayısı:</strong> Sıcak iklimlerde bile yüksek performans</p>
<p>📐 <strong>25 Yıl Performans Garantisi:</strong> Uzun vadeli yatırım güvencesi</p>

<h4><strong>Teknik Bilgiler</strong></h4>
<figure class="table"><table><thead><tr><th>Özellik</th><th>Değer</th></tr></thead><tbody>
<tr><td><strong>Marka</strong></td><td>{brand}</td></tr>
<tr><td><strong>Model</strong></td><td>{sku}</td></tr>
<tr><td><strong>Güç</strong></td><td>{power}{unit}</td></tr>
<tr><td><strong>Hücre Tipi</strong></td><td>Monokristal</td></tr>
<tr><td><strong>Garanti</strong></td><td>Üretici garantisi</td></tr>
</tbody></table></figure>

<p><strong>Türkiye Solar Market</strong> güvencesiyle orijinal {brand} ürünü.</p>"""

    # ---- GENERIC FALLBACK ----
    return f"""<p><strong>{name}</strong></p>
<p>{bd}</p>
<p>{brand} güvencesiyle sunulan bu ürün, güneş enerji sistemleri için tasarlanmış kaliteli bir çözümdür. Detaylı teknik bilgi ve fiyat teklifi için bizimle iletişime geçin.</p>

<h4><strong>Teknik Bilgiler</strong></h4>
<figure class="table"><table><thead><tr><th>Özellik</th><th>Değer</th></tr></thead><tbody>
<tr><td><strong>Marka</strong></td><td>{brand}</td></tr>
<tr><td><strong>Model</strong></td><td>{sku}</td></tr>
<tr><td><strong>Garanti</strong></td><td>Üretici garantisi</td></tr>
</tbody></table></figure>

<p><strong>Türkiye Solar Market</strong> güvencesiyle orijinal {brand} ürünü. Teknik destek için bizimle iletişime geçin.</p>"""


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else '--preview'

    with open('products_need_detay.json', 'r', encoding='utf-8') as f:
        products = json.load(f)

    print(f"Processing {len(products)} products...")

    results = []
    type_counts = {}

    for p in products:
        ptype = classify_product(p['name'], p['categories'])
        specs = parse_specs_from_name(p['name'], p['brand'])
        html = generate_html(ptype, specs, p['sku'])

        results.append({
            'id': p['id'],
            'name': p['name'],
            'type': ptype,
            'html': html,
        })

        type_counts[ptype] = type_counts.get(ptype, 0) + 1

    print("\nType distribution:")
    for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"  {t}: {c}")

    if mode == '--preview':
        # Show 1 sample of each type
        shown_types = set()
        for r in results:
            if r['type'] not in shown_types:
                shown_types.add(r['type'])
                print(f"\n{'='*60}")
                print(f"TYPE: {r['type']} | {r['name']}")
                print(f"{'='*60}")
                print(r['html'][:500])
                print("...")

    elif mode == '--apply':
        conn = pymssql.connect(server=DB_SERVER, user=DB_USER, password=DB_PASS, database=DB_NAME)
        cur = conn.cursor()

        updated = 0
        errors = 0
        for r in results:
            try:
                cur.execute(
                    "UPDATE URUNLER SET URUNDETAY = %s WHERE ID = %s",
                    (r['html'], r['id'])
                )
                updated += 1
            except Exception as e:
                print(f"ERROR updating ID={r['id']} ({r['name']}): {e}")
                errors += 1

        conn.commit()
        conn.close()
        print(f"\nDone! Updated: {updated}, Errors: {errors}")

    else:
        print(f"Unknown mode: {mode}")
        print("Usage: python generate_urundetay.py [--preview|--apply]")


if __name__ == '__main__':
    main()
