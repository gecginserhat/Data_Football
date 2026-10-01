# ADR-0012: Raporlar HTML şablonundan Chromium ile PDF'e

- **Durum:** Kabul edildi · 01.10.2026
- **İlgili:** SPEC §9 (PDF: Jinja2 HTML şablonu → Playwright/Chromium), §14, §19 Faz 6; ADR-0001, ADR-0008, ADR-0010

## Bağlam
Rakip raporu (2-4 sayfa) ve maç planı tablo, saha görselleri, rutin diyagramları ve QR kodları içerir. Faz 6 kabul kriteri iki PDF'in 15 sn içinde üretilmesidir. Tek sayfalık rutin kartı API'de matplotlib ile çiziliyor (ADR-0008); çok sayfalı, metin ağırlıklı raporlar için sayfa düzeni HTML ve CSS ile daha kolay kurulur.

## Karar
- **İçerik ve şablon** `kurgu_analytics.reports` altında saftır: girdi sözlüğünden (API'nin topladığı veri) Jinja2 ile tek bir HTML belgesi üretilir. Saha ısı haritası ve QR kodları satır içi SVG'dir; rutin diyagramları mevcut çiziciyle (ADR-0008) SVG olarak çizilir. Şablon dış kaynak yüklemez.
- **Yazı tipi** IBM Plex Sans ve Condensed (OFL), woff2 olarak repodadır ve HTML'e gömülür; ekran ile PDF aynı yazı ailesini kullanır.
- **PDF** worker'da Playwright (Python) ve Chromium ile yazdırılır (A4, sayfa numarası altlıkta). Chromium yolu `KURGU_CHROMIUM_PATH` ile verilebilir; imajda `playwright install --with-deps chromium` kurulur.
- **Akış:** `POST /reports` satırı `queued` yazar ve işi kuyruğa atar (202). İş veriyi toplar, HTML üretir, PDF'i nesne deposuna yazar (`reports/{tenant}/{id}.pdf`), durumu `ready` yapar ve süreyi `duration_ms` olarak kaydeder. `GET /reports/{id}` hazır raporda kısa ömürlü imzalı indirme adresi döner (video ile aynı depo, ADR-0010).
- Her rapor kaynak ve veri tarihini (son maç haftası, üretim zamanı) yazar.

## Sonuçlar
- Şablon ve veri birim testlerinde Chromium olmadan sınanır; PDF üretimi ayrı, gerçek Chromium ile bir testte sınanır.
- API/worker imajı Chromium ile büyür (yaklaşık 300 MB). Ayrı bir PDF servisi kurulmaz (modüler monolit, ADR-0001).
- Rutin kartı (Faz 3) matplotlib'de kalır; iki yol aynı diyagram geometrisini kullanır.
