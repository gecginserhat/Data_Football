# ADR-0001: Modüler monolit

- **Durum:** Önerildi · 30.09.2026
- **İlgili:** SPEC §0, §9, §9.2; CLAUDE.md "Mimari"

## Bağlam
Kurgu tek kulüp için dağıtılacak, en fazla 20 kiracıya ölçeklenecek (SPEC §18): kulüp başına ~50 kullanıcı, eş zamanlı en fazla 15. İş yükü ağır analitik (metrik hesabı, çıkarım, PDF, video dönüştürme) ile hafif CRUD'un karışımı. Ekip küçük; operasyon yükü düşük tutulmalı. SPEC mikroservisi açıkça yasaklıyor.

## Karar
- Tek Python paketi (`analytics/kurgu_analytics` + `apps/api`) iki süreç olarak çalışır: **API** (FastAPI, uvicorn) ve **worker** (Arq). İkisi aynı kodu, aynı veritabanını ve aynı modelleri kullanır.
- Kod, alan modüllerine bölünür: `identity`, `league` (takım, sezon, maç), `ingestion`, `canonical`, `setpieces`, `metrics`, `recs`, `routines`, `prep`, `tagging`, `video`, `reports`, `perf`, `admin`.
- Modüller arası çağrı yalnızca modülün `service` katmanından yapılır; başka modülün tablolarına doğrudan sorgu atılmaz. Bu kural `import-linter` sözleşmeleriyle CI'da denetlenir.
- Uzun işler (yükleme, MV yenileme, PDF, HLS) worker kuyruğuna gider; API hemen `202` + iş kimliği döner.
- Web (Next.js) ayrı süreçtir ama API'ye yalnızca üretilmiş `packages/api-client` üzerinden erişir.

## Sonuçlar
- **Artı:** Tek dağıtım birimi, tek göç akışı, işlem sınırları basit, uçtan uca tipler kolay.
- **Artı:** Analitik ve API aynı dilde; metrik fonksiyonları hem uçlarda hem işlerde doğrudan kullanılır.
- **Eksi:** Ağır işler API ile aynı imajı taşır; imaj büyür. Worker ayrı ölçeklenebilir olduğu için kabul edilebilir.
- **Eksi:** Modül sınırları disiplin ister; `import-linter` bunu zorlar.
- **Geri dönüş yolu:** Bir modül ileride ayrılması gerekirse, service arayüzü zaten tek giriş noktasıdır.

## Değerlendirilen seçenekler
- **Mikroservisler:** SPEC yasaklıyor; bu ölçekte gereksiz operasyon yükü.
- **Ayrı analitik servisi (ör. ayrı Python servis + Node API):** İki dil, iki tip sistemi, ağ sınırında veri kopyası. Reddedildi.
