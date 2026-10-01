# ADR-0013: Kanıta bağlı LLM brifingi ve sayı eşleştirme

- **Durum:** Kabul edildi · 01.10.2026
- **İlgili:** SPEC §15, §19 Faz 6; CLAUDE.md "LLM" kuralı; ADR-0009

## Bağlam
Teknik ekip için kısa bir Türkçe brifing, hesaplanmış metriklerden, tetiklenen önerilerden ve MD planından üretilecek. Arayüzdeki her sayı bir kayda dayanmalı; modelin uydurduğu bir sayı kulübü yanlış hazırlığa götürür.

## Karar
- **Girdi** tek JSON belgesidir: fikstür, rakibin ve kulübün ilgili metrikleri (ham değer, sıra, takım sayısı, ekranda gösterilen biçim), öneriler (başlık, gerekçe, kanıt değerleri, durum), plan özeti. Sayılar hem ham hem gösterim biçimiyle verilir.
- **İstem** yalnızca bu JSON'daki sayıların kullanılmasını, oyuncu adı ve sayı uydurulmamasını, sayıların rakamla yazılmasını ve dolaylı göstergelerin "dolaylı" diye belirtilmesini şart koşar.
- **Doğrulama** saf bir fonksiyondur (`kurgu_analytics.reports.numbers`): metindeki sayılar Türkçe biçimleriyle (`20,4`, `%20,4`, `1.234`, `4.` sıra, `10.10.2026` tarih) çıkarılır ve girdideki sayılardan türetilen kümeyle eşleştirilir. Eşleşmeyen sayı varsa çıktı reddedilir, bir kez yeniden denenir; yine reddedilirse kullanıcıya yalnız "Brifing üretilemedi" gösterilir. Reddedilen metin kullanıcıya hiç gönderilmez.
- **Model ve anahtar** yalnız `KURGU_LLM_MODEL` ve `KURGU_ANTHROPIC_API_KEY` değişkenlerinden okunur; kodda varsayılan model yoktur. İkisinden biri yoksa özellik "yapılandırılmamış" döner. İstek resmi Anthropic Python SDK'sıyla yapılır; `thinking` ve örnekleme parametreleri gönderilmez, böylece seçilen modelin varsayılanları geçerli olur.
- **Kayıt ve sınırlar:** Her deneme `llm_runs` tablosuna yazılır (model, durum, token, süre, eşleşmeyen sayılar). Kiracı ayarı (`tenants.settings.llm`) özelliği kapatır ve aylık istek ile token sınırını belirler; sınır aşılırsa 429 döner.
- **Test ve geliştirme** için `KURGU_LLM_BACKEND=fake` girdiden belirlenimci bir metin üretir; üretimde kullanılamaz.

## Sonuçlar
- Yazıyla yazılmış sayılar ("iki") yakalanmaz; istem rakam ister, kalan risk kabul edildi.
- Doğrulama yalnız sayıları denetler; anlamsal hata (yanlış takıma yanlış sayı) yakalanmaz. Brifing "Yapay zekâ ile üretildi, sayılar kayıtla eşleşti" etiketiyle gösterilir.
