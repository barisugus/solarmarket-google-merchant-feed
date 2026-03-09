#!/usr/bin/env python3
"""Generate URUNDETAY HTML for 6 Dyness products."""
import pymssql

DB_SERVER = '37.148.209.147'
DB_USER = 'trSolarMarket.dogus.egebilgi'
DB_PASS = '3%DKveYq*6py0ntn'
DB_NAME = 'turkiyeSolarMarketDb'

PRODUCTS = {
    1814: {
        'name': 'Dyness Tower T10 HV 9.6 kWh Yüksek Gerilim Lityum Batarya',
        'sku': 'DYN-HV9637',
        'cap': '9,6 kWh', 'voltage': '102,4–409,6 V', 'type': 'HV (Yüksek Gerilim)',
        'chemistry': 'LFP (LiFePO4)', 'cycles': '6.000+',
        'weight': '~55 kg/modül', 'ip': 'IP55', 'warranty': '10 yıl',
        'temp': '-10°C ~ +50°C', 'scalable': '5–40 kWh (modüler)',
        'desc': 'Tower T10 serisi, kompakt kule tasarımıyla ev ve küçük ticari GES projeleri için ideal yüksek gerilimli enerji depolama çözümüdür.',
        'use': 'Ev tipi çatı GES sistemleri, küçük ticari işletmeler, elektrik kesintisine karşı yedek güç',
    },
    1815: {
        'name': 'Dyness Tower T10 BDU – Batarya Dağıtım Ünitesi',
        'sku': 'DYN-TOWER-BDU',
        'cap': '-', 'voltage': '102,4–409,6 V', 'type': 'BDU (Dağıtım Ünitesi)',
        'chemistry': '-', 'cycles': '-',
        'weight': '~12 kg', 'ip': 'IP55', 'warranty': '10 yıl',
        'temp': '-10°C ~ +50°C', 'scalable': '-',
        'desc': 'Tower T10 BDU, Dyness Tower T10 HV batarya modüllerini inverter ile güvenli şekilde bağlayan dağıtım ünitesidir. Her Tower T10 sistemi için 1 adet BDU gereklidir.',
        'use': 'Tower T10 HV batarya sistemi kurulumu için zorunlu bileşen',
        'is_bdu': True,
    },
    1816: {
        'name': 'Dyness Tower T10 HV 10 kWh Yüksek Gerilim Lityum Batarya',
        'sku': 'DYN-HV9640',
        'cap': '10 kWh', 'voltage': '102,4–409,6 V', 'type': 'HV (Yüksek Gerilim)',
        'chemistry': 'LFP (LiFePO4)', 'cycles': '6.000+',
        'weight': '~58 kg/modül', 'ip': 'IP55', 'warranty': '10 yıl',
        'temp': '-10°C ~ +50°C', 'scalable': '5–40 kWh (modüler)',
        'desc': 'Tower T10 serisinin 10 kWh kapasiteli modeli, daha yüksek enerji ihtiyacı olan ev ve işletmeler için tasarlanmıştır.',
        'use': 'Ev tipi çatı GES sistemleri, küçük ticari işletmeler, yüksek öz tüketim projeleri',
    },
    1817: {
        'name': 'Dyness Tower Pro T10 BDU – Batarya Dağıtım Ünitesi',
        'sku': 'DYN-TOWER-PRO-BDU',
        'cap': '-', 'voltage': '102,4–409,6 V', 'type': 'BDU (Dağıtım Ünitesi)',
        'chemistry': '-', 'cycles': '-',
        'weight': '~14 kg', 'ip': 'IP55', 'warranty': '10 yıl',
        'temp': '-10°C ~ +50°C', 'scalable': '-',
        'desc': 'Tower Pro T10 BDU, Dyness Tower Pro serisi batarya modüllerini inverter ile bağlayan profesyonel dağıtım ünitesidir. Gelişmiş izleme ve koruma özellikleri sunar.',
        'use': 'Tower Pro T10 batarya sistemi kurulumu için zorunlu bileşen',
        'is_bdu': True,
    },
    1818: {
        'name': 'Dyness BX51100 51.2V 100Ah Ticari Lityum Batarya',
        'sku': 'DYN-S51100',
        'cap': '5,12 kWh (modül başı)', 'voltage': '51,2 V', 'type': 'LV (Düşük Gerilim / Ticari)',
        'chemistry': 'LFP (LiFePO4)', 'cycles': '6.000+',
        'weight': '~52 kg', 'ip': 'IP20', 'warranty': '10 yıl',
        'temp': '-10°C ~ +50°C', 'scalable': 'Paralel bağlantı ile 15+ modül',
        'desc': 'BX51100 serisi, ticari ve endüstriyel GES projeleri için tasarlanmış yüksek kapasiteli rack-mount lityum batarya modülüdür. 19" rack uyumlu tasarımı ile veri merkezi kalitesinde kurulum sunar.',
        'use': 'Ticari GES projeleri, endüstriyel enerji depolama, veri merkezi UPS, büyük ölçekli off-grid sistemler',
    },
    1819: {
        'name': 'Dyness BX51100 BDU – Ticari Batarya Dağıtım Ünitesi',
        'sku': 'DYN-SBDU100',
        'cap': '-', 'voltage': '51,2 V', 'type': 'BDU (Dağıtım Ünitesi)',
        'chemistry': '-', 'cycles': '-',
        'weight': '~15 kg', 'ip': 'IP20', 'warranty': '10 yıl',
        'temp': '-10°C ~ +50°C', 'scalable': '-',
        'desc': 'BX51100 BDU, Dyness BX51100 ticari batarya modüllerini inverter ile güvenli şekilde bağlayan profesyonel dağıtım ünitesidir. Rack-mount uyumlu, akıllı izleme ve koruma özellikleri sunar.',
        'use': 'BX51100 ticari batarya sistemi kurulumu için zorunlu bileşen',
        'is_bdu': True,
    },
}

def gen_html(p):
    is_bdu = p.get('is_bdu', False)
    html = f'<p><strong>{p["name"]}</strong></p>\n'
    html += f'<p>{p["desc"]}</p>\n'

    if is_bdu:
        html += '<h4><strong>Temel Özellikler</strong></h4>\n'
        html += '<p>🔌 <strong>Güvenli Bağlantı:</strong> Batarya modülleri ile inverter arasında güvenli güç dağıtımı</p>\n'
        html += '<p>🛡️ <strong>Koruma Fonksiyonları:</strong> Aşırı akım, kısa devre, aşırı sıcaklık koruması</p>\n'
        html += '<p>📊 <strong>Akıllı İzleme:</strong> Batarya durumu ve performans takibi</p>\n'
        html += '<p>⚡ <strong>Kolay Kurulum:</strong> Tak-çalıştır bağlantı sistemi</p>\n'
    else:
        html += '<h4><strong>Öne Çıkan Avantajlar</strong></h4>\n'
        html += f'<p>🔋 <strong>{p["cap"]} Kapasite:</strong> Güneş enerjisinden maksimum fayda</p>\n'
        html += f'<p>⚡ <strong>{p["cycles"]} Çevrim Ömrü:</strong> Uzun vadeli yatırım koruması</p>\n'
        html += '<p>🔄 <strong>Modüler Yapı:</strong> İhtiyaca göre kapasite artırımı</p>\n'
        html += '<p>🛡️ <strong>LFP Güvenliği:</strong> Lityum demir fosfat hücre teknolojisi ile maksimum güvenlik</p>\n'
        html += '<p>🌞 <strong>Yüksek Verim:</strong> %95+ round-trip verimlilik</p>\n'
        html += '<p>🌍 <strong>Dyness Garantisi:</strong> Global marka güvencesi ve yaygın servis ağı</p>\n'

    html += '<h4><strong>Teknik Özellikler</strong></h4>\n'
    html += '<figure class="table"><table><thead><tr><th>Özellik</th><th>Değer</th></tr></thead><tbody>\n'

    specs = [
        ('Ürün Kodu', p['sku']),
        ('Tip', p['type']),
    ]
    if not is_bdu:
        specs += [
            ('Kapasite', p['cap']),
            ('Hücre Teknolojisi', p['chemistry']),
            ('Çevrim Ömrü', p['cycles']),
        ]
    specs += [
        ('Nominal Gerilim', p['voltage']),
        ('Koruma Sınıfı', p['ip']),
        ('Çalışma Sıcaklığı', p['temp']),
        ('Ağırlık', p['weight']),
        ('Garanti', p['warranty']),
    ]
    if not is_bdu and p['scalable'] != '-':
        specs.append(('Ölçeklenebilirlik', p['scalable']))

    for label, val in specs:
        html += f'<tr><td><strong>{label}</strong></td><td>{val}</td></tr>\n'
    html += '</tbody></table></figure>\n'

    html += f'<p><strong>Kullanım Alanları:</strong> {p["use"]}</p>\n'
    html += '<p>Dyness enerji depolama çözümleri en uygun fiyatlarla Türkiye Solar Market\'te!</p>'

    return html

def main():
    conn = pymssql.connect(DB_SERVER, DB_USER, DB_PASS, DB_NAME)
    cursor = conn.cursor()

    for uid, p in PRODUCTS.items():
        html = gen_html(p)
        cursor.execute("UPDATE URUNLER SET URUNDETAY=%s WHERE ID=%s", (html, uid))
        print(f"OK: ID={uid} {p['sku']} ({len(html)} chars)")

    conn.commit()
    cursor.close()
    conn.close()
    print(f"\n{len(PRODUCTS)} ürün URUNDETAY güncellendi.")

if __name__ == '__main__':
    main()
