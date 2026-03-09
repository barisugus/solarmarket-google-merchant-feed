#!/usr/bin/env python3
"""
Arçelik 12 Panel — URUNDETAY + URUNACIKLAMASI Content Generator & DB Updater

Generates rich SEO HTML content for 12 Arçelik solar panels from PDF catalog specs.
Follows the A-grade content pattern: intro + advantages + tech table + use cases + FAQ + FAQPage JSON-LD + internal links.

Usage:
  python3 arcelik_content_update.py                # dry-run: show generated content
  python3 arcelik_content_update.py --apply         # UPDATE DB with generated content
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Product Data (from Arçelik Enerji Çözümleri Kataloğu 2026, pages 16-27)
# ---------------------------------------------------------------------------
PRODUCTS = [
    # Family 1: ARCLK-144PV10T-GG (590/595/600W)
    {
        "id": 1600, "sku": "ARCLK-144PV10T-GG-590", "pmax": 590, "pallet": 29,
        "panel_type": "Cam-Cam Bifacial", "weight": 32.0,
        "efficiency": 22.9, "cells": 144, "cell_size": "182 x 91 mm",
        "dimensions": "2278 x 1134 x 30", "busbar": 16,
        "voc": 52.04, "isc": 14.37, "vmax": 43.67, "imax": 13.52,
        "pmax_tc": -0.32, "voc_tc": -0.26, "isc_tc": 0.046,
        "fuse": 30, "tolerance": "0 ~ +4,99W",
        "glass_front": "2,0 mm AR Kaplamalı Temperli Cam",
        "glass_rear": "2,0 mm Temperli Cam",
        "junction_box": "IP68 3 Adet Schottky Bypass Diyotu",
        "cable": "4,0 mm² ve 35 cm DC kablo (1,3 m yatay kurulum)",
        "connector": "MC4 (Staubli EVO2 MC4)",
        "family": "144PV10T-GG",
    },
    {
        "id": 1601, "sku": "ARCLK-144PV10T-GG-595", "pmax": 595, "pallet": 29,
        "panel_type": "Cam-Cam Bifacial", "weight": 32.0,
        "efficiency": 23.0, "cells": 144, "cell_size": "182 x 91 mm",
        "dimensions": "2278 x 1134 x 30", "busbar": 16,
        "voc": 52.24, "isc": 14.41, "vmax": 43.86, "imax": 13.57,
        "pmax_tc": -0.32, "voc_tc": -0.26, "isc_tc": 0.046,
        "fuse": 30, "tolerance": "0 ~ +4,99W",
        "glass_front": "2,0 mm AR Kaplamalı Temperli Cam",
        "glass_rear": "2,0 mm Temperli Cam",
        "junction_box": "IP68 3 Adet Schottky Bypass Diyotu",
        "cable": "4,0 mm² ve 35 cm DC kablo (1,3 m yatay kurulum)",
        "connector": "MC4 (Staubli EVO2 MC4)",
        "family": "144PV10T-GG",
    },
    {
        "id": 1602, "sku": "ARCLK-144PV10T-GG-600", "pmax": 600, "pallet": 29,
        "panel_type": "Cam-Cam Bifacial", "weight": 32.0,
        "efficiency": 23.2, "cells": 144, "cell_size": "182 x 91 mm",
        "dimensions": "2278 x 1134 x 30", "busbar": 16,
        "voc": 52.44, "isc": 14.46, "vmax": 44.06, "imax": 13.62,
        "pmax_tc": -0.32, "voc_tc": -0.26, "isc_tc": 0.046,
        "fuse": 30, "tolerance": "0 ~ +4,99W",
        "glass_front": "2,0 mm AR Kaplamalı Temperli Cam",
        "glass_rear": "2,0 mm Temperli Cam",
        "junction_box": "IP68 3 Adet Schottky Bypass Diyotu",
        "cable": "4,0 mm² ve 35 cm DC kablo (1,3 m yatay kurulum)",
        "connector": "MC4 (Staubli EVO2 MC4)",
        "family": "144PV10T-GG",
    },
    # Family 2: ARCLK-144PV10RT-GG (600/605/610/615W)
    {
        "id": 1603, "sku": "ARCLK-144PV10RT-GG-600", "pmax": 600, "pallet": 29,
        "panel_type": "Cam-Cam Bifacial", "weight": 32.0,
        "efficiency": 23.2, "cells": 144, "cell_size": "182.2 x 91.9 mm",
        "dimensions": "2278 x 1134 x 30", "busbar": 16,
        "voc": 53.40, "isc": 14.20, "vmax": 44.55, "imax": 13.47,
        "pmax_tc": -0.28, "voc_tc": -0.24, "isc_tc": 0.046,
        "fuse": 30, "tolerance": "0 ~ +4,99W",
        "glass_front": "2,0 mm AR Kaplamalı Temperli Cam",
        "glass_rear": "2,0 mm Temperli Cam",
        "junction_box": "IP68 3 Adet Schottky Bypass Diyotu",
        "cable": "4,0 mm² ve 1,3 m DC kablo",
        "connector": "Staubli EVO2A MC4",
        "family": "144PV10RT-GG",
    },
    {
        "id": 1604, "sku": "ARCLK-144PV10RT-GG-605", "pmax": 605, "pallet": 29,
        "panel_type": "Cam-Cam Bifacial", "weight": 32.0,
        "efficiency": 23.4, "cells": 144, "cell_size": "182.2 x 91.9 mm",
        "dimensions": "2278 x 1134 x 30", "busbar": 16,
        "voc": 53.60, "isc": 14.25, "vmax": 44.72, "imax": 13.54,
        "pmax_tc": -0.28, "voc_tc": -0.24, "isc_tc": 0.046,
        "fuse": 30, "tolerance": "0 ~ +4,99W",
        "glass_front": "2,0 mm AR Kaplamalı Temperli Cam",
        "glass_rear": "2,0 mm Temperli Cam",
        "junction_box": "IP68 3 Adet Schottky Bypass Diyotu",
        "cable": "4,0 mm² ve 1,3 m DC kablo",
        "connector": "Staubli EVO2A MC4",
        "family": "144PV10RT-GG",
    },
    {
        "id": 1605, "sku": "ARCLK-144PV10RT-GG-610", "pmax": 610, "pallet": 29,
        "panel_type": "Cam-Cam Bifacial", "weight": 32.0,
        "efficiency": 23.6, "cells": 144, "cell_size": "182.2 x 91.9 mm",
        "dimensions": "2278 x 1134 x 30", "busbar": 16,
        "voc": 53.80, "isc": 14.30, "vmax": 44.89, "imax": 13.60,
        "pmax_tc": -0.28, "voc_tc": -0.24, "isc_tc": 0.046,
        "fuse": 30, "tolerance": "0 ~ +4,99W",
        "glass_front": "2,0 mm AR Kaplamalı Temperli Cam",
        "glass_rear": "2,0 mm Temperli Cam",
        "junction_box": "IP68 3 Adet Schottky Bypass Diyotu",
        "cable": "4,0 mm² ve 1,3 m DC kablo",
        "connector": "Staubli EVO2A MC4",
        "family": "144PV10RT-GG",
    },
    {
        "id": 1606, "sku": "ARCLK-144PV10RT-GG-615", "pmax": 615, "pallet": 29,
        "panel_type": "Cam-Cam Bifacial", "weight": 32.0,
        "efficiency": 23.8, "cells": 144, "cell_size": "182.2 x 91.9 mm",
        "dimensions": "2278 x 1134 x 30", "busbar": 16,
        "voc": 54.00, "isc": 14.35, "vmax": 45.06, "imax": 13.67,
        "pmax_tc": -0.28, "voc_tc": -0.24, "isc_tc": 0.046,
        "fuse": 30, "tolerance": "0 ~ +4,99W",
        "glass_front": "2,0 mm AR Kaplamalı Temperli Cam",
        "glass_rear": "2,0 mm Temperli Cam",
        "junction_box": "IP68 3 Adet Schottky Bypass Diyotu",
        "cable": "4,0 mm² ve 1,3 m DC kablo",
        "connector": "Staubli EVO2A MC4",
        "family": "144PV10RT-GG",
    },
    # Family 3: ARCLK-144PV10RT (600W, Cam-Cam, 37/palet)
    {
        "id": 1607, "sku": "ARCLK-144PV10RT-600", "pmax": 600, "pallet": 37,
        "panel_type": "Cam-Cam", "weight": 32.5,
        "efficiency": 23.2, "cells": 144, "cell_size": "182.2 x 91.9 mm",
        "dimensions": "2278 x 1134 x 30", "busbar": 16,
        "voc": 52.00, "isc": 14.70, "vmax": 43.70, "imax": 13.73,
        "pmax_tc": -0.29, "voc_tc": -0.23, "isc_tc": 0.046,
        "fuse": 25, "tolerance": "0 ~ +3%",
        "glass_front": "2,0 mm Temperli Cam",
        "glass_rear": "2,0 mm Temperli Cam",
        "junction_box": "IP68",
        "cable": "4,0 mm² ve 1,2 m DC kablo",
        "connector": "Staubli EVO2A MC4",
        "family": "144PV10RT",
    },
    # Family 4: ARCLK-132PVRT-GG (610/615/620/625W)
    {
        "id": 1608, "sku": "ARCLK-132PVRT-GG-610", "pmax": 610, "pallet": 29,
        "panel_type": "Cam-Cam Bifacial", "weight": 32.5,
        "efficiency": 22.6, "cells": 132, "cell_size": "182.2 x 105 mm",
        "dimensions": "2382 x 1134 x 30", "busbar": 16,
        "voc": 48.70, "isc": 15.94, "vmax": 40.48, "imax": 15.07,
        "pmax_tc": -0.28, "voc_tc": -0.24, "isc_tc": 0.046,
        "fuse": 30, "tolerance": "0 ~ +3%",
        "glass_front": "2,0 mm Temperli Cam",
        "glass_rear": "2,0 mm Temperli Cam",
        "junction_box": "IP68",
        "cable": "4,0 mm² ve 1,3 m DC kablo",
        "connector": "Staubli EVO2A MC4",
        "family": "132PVRT-GG",
    },
    {
        "id": 1609, "sku": "ARCLK-132PVRT-GG-615", "pmax": 615, "pallet": 29,
        "panel_type": "Cam-Cam Bifacial", "weight": 32.5,
        "efficiency": 22.8, "cells": 132, "cell_size": "182.2 x 105 mm",
        "dimensions": "2382 x 1134 x 30", "busbar": 16,
        "voc": 48.90, "isc": 16.00, "vmax": 40.65, "imax": 15.13,
        "pmax_tc": -0.28, "voc_tc": -0.24, "isc_tc": 0.046,
        "fuse": 30, "tolerance": "0 ~ +3%",
        "glass_front": "2,0 mm Temperli Cam",
        "glass_rear": "2,0 mm Temperli Cam",
        "junction_box": "IP68",
        "cable": "4,0 mm² ve 1,3 m DC kablo",
        "connector": "Staubli EVO2A MC4",
        "family": "132PVRT-GG",
    },
    {
        "id": 1610, "sku": "ARCLK-132PVRT-GG-620", "pmax": 620, "pallet": 29,
        "panel_type": "Cam-Cam Bifacial", "weight": 32.5,
        "efficiency": 23.0, "cells": 132, "cell_size": "182.2 x 105 mm",
        "dimensions": "2382 x 1134 x 30", "busbar": 16,
        "voc": 49.10, "isc": 16.06, "vmax": 40.82, "imax": 15.19,
        "pmax_tc": -0.28, "voc_tc": -0.24, "isc_tc": 0.046,
        "fuse": 30, "tolerance": "0 ~ +3%",
        "glass_front": "2,0 mm Temperli Cam",
        "glass_rear": "2,0 mm Temperli Cam",
        "junction_box": "IP68",
        "cable": "4,0 mm² ve 1,3 m DC kablo",
        "connector": "Staubli EVO2A MC4",
        "family": "132PVRT-GG",
    },
    {
        "id": 1611, "sku": "ARCLK-132PVRT-GG-625", "pmax": 625, "pallet": 29,
        "panel_type": "Cam-Cam Bifacial", "weight": 32.5,
        "efficiency": 23.1, "cells": 132, "cell_size": "182.2 x 105 mm",
        "dimensions": "2382 x 1134 x 30", "busbar": 16,
        "voc": 49.30, "isc": 16.12, "vmax": 40.96, "imax": 15.26,
        "pmax_tc": -0.28, "voc_tc": -0.24, "isc_tc": 0.046,
        "fuse": 30, "tolerance": "0 ~ +3%",
        "glass_front": "2,0 mm Temperli Cam",
        "glass_rear": "2,0 mm Temperli Cam",
        "junction_box": "IP68",
        "cable": "4,0 mm² ve 1,3 m DC kablo",
        "connector": "Staubli EVO2A MC4",
        "family": "132PVRT-GG",
    },
]


# ---------------------------------------------------------------------------
# Content generators
# ---------------------------------------------------------------------------

def generate_urunaciklamasi(p):
    """Short product description (~150 chars)."""
    bifacial_text = "Bifacial " if "Bifacial" in p["panel_type"] else ""
    return (
        f"Arçelik {p['sku']} {p['pmax']}W {bifacial_text}güneş paneli. "
        f"N-Type Topcon hücre, %{p['efficiency']} verimlilik, "
        f"{p['cells']} half-cut hücre, {p['busbar']} busbar. "
        f"30 yıl performans garantisi."
    )


def generate_urundetay(p):
    """Rich SEO HTML content."""
    is_bifacial = "Bifacial" in p["panel_type"]
    bifacial_text = "bifacial (çift yüzlü) " if is_bifacial else ""
    pallet_kw = round(p["pmax"] * p["pallet"] / 1000, 1)

    # Intro paragraph — unique per family
    if p["family"] == "144PV10T-GG":
        intro = (
            f'Arçelik {p["sku"]}, N-Type Topcon hücre teknolojisi ve {p["cells"]} adet half-cut hücre yapısıyla '
            f'{p["pmax"]}W maksimum güç üreten {bifacial_text}güneş panelidir. '
            f'%{p["efficiency"]} modül verimliliği sayesinde sınırlı çatı alanlarından maksimum enerji üretimi sağlar. '
            f'AR kaplamalı ön cam ile ışık geçirgenliği artırılmış, 16 busbar teknolojisi ile iç dirençler minimize edilmiştir. '
            f'Palet başına {p["pallet"]} adet panel ({pallet_kw} kWp) içeren bu modül, konut ve ticari çatı uygulamaları için idealdir.'
        )
    elif p["family"] == "144PV10RT-GG":
        intro = (
            f'Arçelik {p["sku"]}, geliştirilmiş N-Type Topcon hücre yapısı ile {p["pmax"]}W güç kapasitesine sahip '
            f'yüksek performanslı {bifacial_text}güneş panelidir. '
            f'%{p["efficiency"]} verimlilik oranı ve düşük sıcaklık katsayısı (-{abs(p["pmax_tc"])}%/°C) ile '
            f'sıcak iklimlerde bile kararlı enerji üretimi sunar. '
            f'{p["cells"]} half-cut hücre tasarımı gölgelenme kayıplarını minimuma indirirken, '
            f'{p["busbar"]} busbar teknolojisi ile iletim verimliliğini en üst düzeye çıkarır. '
            f'Palet başına {p["pallet"]} adet ({pallet_kw} kWp) modül içerir.'
        )
    elif p["family"] == "144PV10RT":
        intro = (
            f'Arçelik {p["sku"]}, cam-cam yapısıyla uzun ömürlü ve yüksek dayanıklılık sunan {p["pmax"]}W güneş panelidir. '
            f'N-Type Topcon hücre teknolojisi ve %{p["efficiency"]} modül verimliliği ile üstün enerji dönüşümü sağlar. '
            f'{p["cells"]} adet half-cut hücre ve {p["busbar"]} busbar konfigürasyonu, '
            f'düşük ışınım koşullarında bile tutarlı performans sunar. '
            f'Palet başına {p["pallet"]} adet ({pallet_kw} kWp) modül içermesiyle büyük ölçekli projeler için maliyet avantajı sağlar.'
        )
    else:  # 132PVRT-GG
        intro = (
            f'Arçelik {p["sku"]}, {p["cells"]} adet büyük boyutlu N-Type Topcon hücre ile {p["pmax"]}W güç kapasitesine ulaşan '
            f'{bifacial_text}güneş panelidir. '
            f'%{p["efficiency"]} verimlilik ve {p["busbar"]} busbar teknolojisi sayesinde '
            f'yüksek enerji hasadı sunar. 2382 mm uzunluğuyla geniş çatı alanlarında daha az panel ile '
            f'hedef güce ulaşmayı mümkün kılar. '
            f'Palet başına {p["pallet"]} adet ({pallet_kw} kWp) modül içerir.'
        )

    # Advantages
    advantages = []
    advantages.append(
        f'N-Type Topcon hücre yapısı ile geleneksel PERC panellere kıyasla daha yüksek verimlilik (%{p["efficiency"]}) ve daha düşük degradasyon oranı sunar.'
    )
    if is_bifacial:
        advantages.append(
            'Bifacial (çift yüzlü) teknoloji sayesinde arka yüzeyden yansıyan ışınımları da değerlendirerek %10-30 arası ek enerji üretimi sağlar.'
        )
    advantages.append(
        f'{p["cells"]} adet half-cut hücre tasarımıyla kısmi gölgelenmede bile güç kaybını minimumda tutar.'
    )
    advantages.append(
        f'Ön taraf 5.400 Pa, arka taraf 2.400 Pa mekanik dayanım ile şiddetli rüzgâr ve kar yüküne karşı dirençlidir.'
    )
    advantages.append(
        'Cam-cam yapısı sayesinde PID (Potansiyel Kaynaklı Degradasyon) direnci yüksektir, modül ömrü 30+ yıla uzar.'
    )
    advantages.append(
        f'30 yılda %87 performans garantisi ve 15 yıl ürün garantisi ile uzun vadeli yatırım güvencesi sunar.'
    )
    advantages.append(
        f'{p["connector"]} konnektör ve IP68 bağlantı kutusu ile hızlı ve güvenli kurulum imkânı sağlar.'
    )

    adv_html = "\n".join(f"<li>{a}</li>" for a in advantages)

    # Technical specs table
    tech_rows = [
        ("Maksimum Güç (Pmax)", f'{p["pmax"]} Wp'),
        ("Modül Verimliliği", f'%{p["efficiency"]}'),
        ("Açık Devre Gerilimi (Voc)", f'{p["voc"]} V'),
        ("Kısa Devre Akımı (Isc)", f'{p["isc"]} A'),
        ("Maks. Güç Gerilimi (Vmax)", f'{p["vmax"]} V'),
        ("Maks. Güç Akımı (Imax)", f'{p["imax"]} A'),
        ("Hücre Tipi", f'N-Type Topcon {p["cell_size"]} ({p["cells"]} adet)'),
        ("Busbar Sayısı", f'{p["busbar"]} Adet'),
        ("Güç Toleransı", p["tolerance"]),
        ("Boyutlar (UxGxD)", f'{p["dimensions"]} mm'),
        ("Ağırlık", f'{p["weight"]} kg'),
        ("Ön Cam", p["glass_front"]),
        ("Arka Cam", p["glass_rear"]),
        ("Çerçeve", "Eloksallı Alüminyum Alaşım"),
        ("Bağlantı Kutusu", p["junction_box"]),
        ("Çıkış Kabloları", p["cable"]),
        ("Konnektör", p["connector"]),
        ("Mekanik Dayanım", "Ön Taraf 5.400 Pa / Arka Taraf 2.400 Pa"),
        ("Maks. Sistem Gerilimi", "1.500V DC"),
        ("Maks. Seri Sigorta Değeri", f'{p["fuse"]}A'),
        ("Pmax Sıcaklık Katsayısı", f'{p["pmax_tc"]}%/°C'),
        ("Voc Sıcaklık Katsayısı", f'{p["voc_tc"]}%/°C'),
        ("Isc Sıcaklık Katsayısı", f'+{p["isc_tc"]}%/°C'),
        ("Çalışma Sıcaklığı", "-40°C ~ +85°C"),
        ("NMOT", "45°C ± 2°C"),
    ]
    if is_bifacial:
        tech_rows.append(("Bifacial Faktörü", "80 ± %10"))

    tech_rows.append(("Paketleme", f'Palet başına {p["pallet"]} adet panel'))

    table_rows = "\n".join(
        f'<tr><td><strong>{k}</strong></td><td>{v}</td></tr>' for k, v in tech_rows
    )

    # Use cases
    if p["pallet"] == 37:
        use_case_text = (
            f'Arçelik {p["sku"]}, palet başına {p["pallet"]} adet yüksek kapasitesiyle büyük çatı GES projeleri, '
            f'sanayi tesisleri ve tarımsal sulama sistemleri için ekonomik bir çözümdür. '
            f'{pallet_kw} kWp palet gücüyle lojistik maliyetleri düşürür ve kurulum süresini kısaltır.'
        )
    elif p["cells"] == 132:
        use_case_text = (
            f'Arçelik {p["sku"]}, {p["pmax"]}W güç kapasitesiyle endüstriyel çatı GES projeleri, '
            f'ticari tesisler, tarımsal sulama ve serbest alan GES kurulumları için uygundur. '
            f'Büyük hücre boyutu sayesinde daha az panel ile hedef güce ulaşılır, kurulum ve kablolama maliyetleri düşer.'
        )
    else:
        use_case_text = (
            f'Arçelik {p["sku"]}, konut çatı sistemlerinden ticari GES projelerine, '
            f'tarımsal sulama sistemlerinden endüstriyel tesis çatılarına kadar geniş bir uygulama yelpazesine sahiptir. '
            f'{p["pmax"]}W gücü ve kompakt boyutlarıyla çatı alanını verimli kullanır.'
        )

    # FAQ
    faqs = _get_faqs(p)
    faq_html = ""
    faq_json_entries = []
    for q, a in faqs:
        faq_html += f"<h4>{q}</h4>\n<p>{a}</p>\n"
        faq_json_entries.append({
            "@type": "Question",
            "name": q,
            "acceptedAnswer": {"@type": "Answer", "text": a}
        })

    faq_json = json.dumps({
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": faq_json_entries
    }, ensure_ascii=False, indent=2)

    # Internal links
    links = [
        ('<a href="/kategori/0/solar-paneller-cati/">Solar Paneller (Çatı Tipi)</a>',),
        ('<a href="/kategori/0/solar-panel-markalari/arcelik/">Arçelik Güneş Paneli Modelleri</a>',),
        ('<a href="/kategori/0/inverter-markalari/">İnverter Markaları ve Modelleri</a>',),
        ('<a href="/kategori/0/solar-malzemeler/">Solar Montaj Malzemeleri</a>',),
    ]
    links_html = "\n".join(f"<li>{l[0]}</li>" for l in links)

    # Assemble
    html = f"""<div class="urun-detay-icerik">
<p>{intro}</p>

<h3>Öne Çıkan Özellikler</h3>
<ul>
{adv_html}
</ul>

<h3>Teknik Özellikler</h3>
<table class="table table-bordered table-striped">
<thead><tr><th>Parametre</th><th>Değer</th></tr></thead>
<tbody>
{table_rows}
</tbody>
</table>

<h3>Kullanım Alanları</h3>
<p>{use_case_text}</p>

<h3>İlgili Ürünler ve Kategoriler</h3>
<ul>
{links_html}
</ul>

<h3>Sıkça Sorulan Sorular</h3>
{faq_html}
<script type="application/ld+json">
{faq_json}
</script>
</div>"""

    return html


def _get_faqs(p):
    """Return 3 unique FAQs per product family."""
    is_bifacial = "Bifacial" in p["panel_type"]
    sku = p["sku"]
    pmax = p["pmax"]
    eff = p["efficiency"]
    pallet = p["pallet"]
    pallet_kw = round(pmax * pallet / 1000, 1)

    if p["family"] == "144PV10T-GG":
        return [
            (
                f"Arçelik {sku} panelin gerçek güç çıkışı ne kadar?",
                f"{sku} panelin STC koşullarında nominal gücü {pmax}W'tır. Pozitif güç toleransı (0 ~ +4,99W) "
                f"sayesinde etiket değerinin altında güç üretmez. Bifacial özelliği ile arka yüzeyden ek %10-30 "
                f"enerji kazanımı da sağlanır."
            ),
            (
                f"Bu panelin AR kaplamalı camı ne avantaj sağlar?",
                f"AR (Anti-Reflektif) kaplama, cam yüzeyindeki ışık yansımasını azaltarak daha fazla güneş ışığının "
                f"hücrelere ulaşmasını sağlar. Bu sayede özellikle düşük açılı güneş ışığında (sabah, akşam ve kış ayları) "
                f"enerji üretimi artırılır. Standart temperli cama kıyasla %2-3 daha fazla enerji hasadı elde edilir."
            ),
            (
                f"Arçelik {sku} hangi inverterlerle uyumludur?",
                f"1.500V DC sistem gerilimine sahip tüm string ve hibrit inverterlerle uyumludur. "
                f"Fronius, Huawei, Sungrow, GoodWe ve CHINT Power marka inverterlerle sorunsuz çalışır. "
                f"Dizi tasarımında {p['voc']}V Voc ve {p['isc']}A Isc değerleri dikkate alınmalıdır."
            ),
        ]
    elif p["family"] == "144PV10RT-GG":
        return [
            (
                f"Arçelik {sku} ile {pmax}W gerçekten elde edilebilir mi?",
                f"Evet, {sku} STC koşullarında (1000 W/m², 25°C, AM1.5) {pmax}W nominal güç üretir. "
                f"Pozitif güç toleransı (0 ~ +4,99W) sayesinde gerçek üretim etiket değerini aşabilir. "
                f"Bifacial özelliğiyle arazi veya açık renkli çatılarda ek enerji kazanımı mümkündür."
            ),
            (
                f"Düşük sıcaklık katsayısı ne anlama gelir?",
                f"{sku} panelin Pmax sıcaklık katsayısı {p['pmax_tc']}%/°C olup bu değer sektör ortalamasının "
                f"(-0,35%/°C) altındadır. Yani sıcak yaz günlerinde güç kaybı daha azdır. Örneğin 45°C hücre "
                f"sıcaklığında (25°C STC'den 20°C farkla) bu panel yalnızca %{abs(p['pmax_tc']) * 20:.1f} güç kaybeder."
            ),
            (
                f"Palet başına kaç panel ve ne kadar güç geliyor?",
                f"Her palette {pallet} adet {sku} panel bulunur. Toplam palet gücü {pallet_kw} kWp'dir. "
                f"Palet bazlı satış sayesinde lojistik maliyetler optimize edilir ve toplu alımlarda birim fiyat avantajı sağlanır."
            ),
        ]
    elif p["family"] == "144PV10RT":
        return [
            (
                f"Arçelik {sku} neden 37 adet palet ile satılıyor?",
                f"Bu modelin cam-cam yapısı ve standart boyutları, paletleme optimizasyonuna olanak tanır. "
                f"37 adet/palet ile toplam {pallet_kw} kWp palet gücü elde edilir. "
                f"Daha fazla panel/palet oranı, nakliye maliyetlerini düşürür ve büyük projelerde önemli maliyet avantajı sağlar."
            ),
            (
                f"Cam-cam yapısının avantajı nedir?",
                f"Cam-cam (double glass) yapı, geleneksel cam-backsheet panellere kıyasla daha yüksek nem direnci, "
                f"daha düşük PID riski ve daha uzun mekanik ömür sunar. Arka yüzey de cam olduğu için çevresel etkilere "
                f"(nem, tuz, amonyak) karşı üstün koruma sağlar. Bu nedenle 30+ yıl ömür beklentisi desteklenir."
            ),
            (
                f"Bu paneli konut çatısında kullanabilir miyim?",
                f"Evet, {sku} konut çatı sistemlerinde rahatlıkla kullanılabilir. {p['dimensions']} mm boyutları "
                f"standart çatı montaj sistemlerine uygundur. {p['weight']} kg ağırlığı ile çatı statik yükünü "
                f"minimum düzeyde etkiler. 5.400 Pa rüzgâr ve 2.400 Pa kar yükü dayanımı Türkiye koşullarında yeterlidir."
            ),
        ]
    else:  # 132PVRT-GG
        return [
            (
                f"Arçelik {sku} panelin boyutu neden daha büyük?",
                f"Bu model {p['cells']} adet 182,2 x 105 mm boyutunda büyük hücre kullanır (standart modellerde 91 mm). "
                f"Daha büyük hücre alanı sayesinde {pmax}W yüksek güce ulaşılır. 2382 mm panel uzunluğu, "
                f"geniş çatı ve arazi uygulamalarında daha az panel ile hedef güce ulaşmayı mümkün kılar."
            ),
            (
                f"Bifacial kazanım gerçekte ne kadar?",
                f"{sku} panelin bifacial faktörü %80±10'dur. Gerçek ek kazanım, montaj yüksekliği, zemin yansıtıcılığı "
                f"(albedo) ve tilt açısına bağlıdır. Açık renkli beton zeminlerde %10-15, kar üzerinde %25-30 ek kazanım "
                f"mümkündür. Koyu toprak zeminlerde ise %5-8 arasında ek üretim beklenir."
            ),
            (
                f"{sku} ile kaç panelde 10 kWp sisteme ulaşılır?",
                f"{pmax}W gücündeki bu panelden 10 kWp sistem için {10000 // pmax + (1 if 10000 % pmax > 0 else 0)} adet panel yeterlidir "
                f"(toplam {(10000 // pmax + (1 if 10000 % pmax > 0 else 0)) * pmax / 1000:.2f} kWp). "
                f"Konut çatı GES projelerinde bu adet, ortalama 4-5 string inverter girişine uygun şekilde dizayn edilebilir."
            ),
        ]


# ---------------------------------------------------------------------------
# DB operations
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).parent
LOG_DIR = SCRIPT_DIR / "logs"


def get_db_connection():
    env = {}
    for line in (SCRIPT_DIR / ".env").read_text().strip().split("\n"):
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()

    import pymssql
    return pymssql.connect(
        server=env["MSSQL_SERVER"],
        port=int(env.get("MSSQL_PORT", "1433")),
        user=env["MSSQL_USER"],
        password=env["MSSQL_PASSWORD"],
        database=env["MSSQL_DATABASE"],
        charset="utf8",
    )


def verify_products(conn):
    """Verify all 12 product IDs exist and have empty URUNDETAY."""
    cursor = conn.cursor(as_dict=True)
    ids = [p["id"] for p in PRODUCTS]
    placeholders = ",".join(["%s"] * len(ids))
    cursor.execute(f"""
        SELECT ID, STOKKODU,
               LEN(CAST(URUNDETAY AS NVARCHAR(MAX))) as detay_len,
               LEN(ISNULL(URUNACIKLAMASI,'')) as aciklama_len
        FROM URUNLER WHERE ID IN ({placeholders})
    """, tuple(ids))
    rows = {r["ID"]: r for r in cursor.fetchall()}
    cursor.close()

    found = len(rows)
    if found != 12:
        missing = set(ids) - set(rows.keys())
        print(f"ERROR: Expected 12 products, found {found}. Missing: {missing}")
        sys.exit(1)

    already_filled = [r for r in rows.values() if (r["detay_len"] or 0) > 100]
    if already_filled:
        print(f"WARNING: {len(already_filled)} products already have URUNDETAY content:")
        for r in already_filled:
            print(f"  ID={r['ID']} SKU={r['STOKKODU']} detay_len={r['detay_len']}")
        return rows, True

    return rows, False


def apply_updates(conn, updates):
    """UPDATE URUNDETAY and URUNACIKLAMASI for all 12 products."""
    import pymssql
    cursor = conn.cursor()
    try:
        for u in updates:
            cursor.execute(
                "UPDATE URUNLER SET URUNDETAY = %s, URUNACIKLAMASI = %s WHERE ID = %s",
                (u["urundetay"], u["urunaciklamasi"], u["id"]),
            )
            if cursor.rowcount != 1:
                conn.rollback()
                print(f"ERROR: UPDATE for ID={u['id']} affected {cursor.rowcount} rows, expected 1. ROLLBACK.")
                sys.exit(1)

        # Verify
        ids = [u["id"] for u in updates]
        placeholders = ",".join(["%s"] * len(ids))
        cursor.execute(f"""
            SELECT ID, LEN(CAST(URUNDETAY AS NVARCHAR(MAX))) as detay_len,
                   LEN(ISNULL(URUNACIKLAMASI,'')) as aciklama_len
            FROM URUNLER WHERE ID IN ({placeholders})
        """, tuple(ids))
        results = cursor.fetchall()

        empty = [r for r in results if (r[1] or 0) < 100]
        if empty:
            conn.rollback()
            print(f"ERROR: {len(empty)} products still have empty URUNDETAY after UPDATE. ROLLBACK.")
            sys.exit(1)

        conn.commit()
        print(f"COMMITTED: {len(updates)} products updated.")

    except Exception as e:
        conn.rollback()
        print(f"ERROR: {e}. ROLLBACK.")
        raise
    finally:
        cursor.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Arçelik 12 Panel Content Generator")
    parser.add_argument("--apply", action="store_true", help="Actually UPDATE DB")
    parser.add_argument("--show-html", action="store_true", help="Show full HTML for first product")
    args = parser.parse_args()

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"=== Arçelik Panel Content Update — {mode} — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")
    print(f"  Target: {len(PRODUCTS)} products")
    print()

    # Generate content for all 12 products
    updates = []
    for p in PRODUCTS:
        detay = generate_urundetay(p)
        aciklama = generate_urunaciklamasi(p)
        updates.append({
            "id": p["id"],
            "sku": p["sku"],
            "pmax": p["pmax"],
            "urundetay": detay,
            "urunaciklamasi": aciklama,
            "detay_len": len(detay),
            "aciklama_len": len(aciklama),
        })

    # Show summary
    print("--- Generated Content Summary ---")
    for u in updates:
        print(f"  ID={u['id']:5d}  {u['sku']:30s}  {u['pmax']}W  detay={u['detay_len']:5d} chars  aciklama={u['aciklama_len']:3d} chars")
    print()

    total_chars = sum(u["detay_len"] for u in updates)
    print(f"  Total URUNDETAY: {total_chars:,} chars across {len(updates)} products")
    print(f"  Average: {total_chars // len(updates):,} chars/product")
    print()

    if args.show_html:
        print("--- Sample HTML (first product) ---")
        print(updates[0]["urundetay"])
        print()
        print("--- Sample URUNACIKLAMASI ---")
        print(updates[0]["urunaciklamasi"])
        print()

    # DB operations
    conn = get_db_connection()
    try:
        print("--- DB Verification ---")
        rows, has_content = verify_products(conn)
        print(f"  All 12 products found in DB.")

        if has_content and args.apply:
            print("  WARNING: Some products already have content. Will OVERWRITE.")

        if args.apply:
            print()
            print("--- Applying Updates ---")
            apply_updates(conn, updates)

            # Log
            LOG_DIR.mkdir(exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_path = LOG_DIR / f"arcelik_content_update_{ts}.json"
            log_data = {
                "timestamp": datetime.now().isoformat(),
                "mode": "APPLY",
                "products_updated": len(updates),
                "total_detay_chars": total_chars,
                "products": [
                    {"id": u["id"], "sku": u["sku"], "detay_len": u["detay_len"], "aciklama_len": u["aciklama_len"]}
                    for u in updates
                ],
            }
            log_path.write_text(json.dumps(log_data, ensure_ascii=False, indent=2))
            print(f"  Log: {log_path}")
        else:
            print()
            print("DRY-RUN: No changes written to DB.")
            print("Run with --apply to update DB.")
            print("Run with --show-html to see generated HTML.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
