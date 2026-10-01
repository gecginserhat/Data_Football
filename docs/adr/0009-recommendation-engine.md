# ADR-0009: Öneri motoru, kural setleri ve maç planı

- **Durum:** Kabul edildi · 01.10.2026
- **İlgili:** SPEC §7, §8.1, §10, §11, §12.1, §13.2 (maç hazırlığı), §19 Faz 4; A-46 … A-54

## Bağlam
Maç hazırlığı ekranı, rakip ve kulüp metriklerinden kural tabanlı öneriler üretir. Teknik ekip bu önerileri kabul eder ya da reddeder, kabul ettiklerini haftalık MD planına koyar. Kurallar kiracıya göre ayarlanabilir, sürümlenir ve denetlenir. SPEC iki şeyi açıkça istiyor: `eval` kullanılmaması ve her önerinin gerçek sayılarla açıklanması.

## Karar
- **Saf değerlendirici `kurgu_analytics.recs`.**
  - Kural, koşul ve birleştiriciler Pydantic modelleriyle doğrulanır. Operatörler sabit bir sözlükteki Python fonksiyonlarıdır. Metin şablonları `{özne.metrik|biçim}` dışında bir şey yorumlamaz: bilinmeyen yer tutucu ya da biçim kuralı geçersiz kılar.
  - Değerlendirici girdisi bir "olgular" sözlüğüdür: özne → metrik → değer, sıra, takım sayısı, yüzdelik, maç sayısı, az veri, yaklaşık.
  - Değerlendirici kural başına şunları döndürür: tetiklenip tetiklenmediği, koşul ayrıntısı (gerçek değer, eşik, sonuç, veri yok), güven (A-48), işlenmiş metinler ve kanıt JSON'u.
  - Değerlendirici veritabanına dokunmaz; birim testleri tohum değerleriyle çalışır.
- **Olgular API'de derlenir.** Kaynak, Faz 2'deki `compute_season_metrics` fonksiyonudur (A-36 kaynak önceliği dahil). Rutin olguları `v_routine_stats` görünümünden, savunma özeti kulübün kendi duran top kaydından gelir. Hangi sezonun okunduğu A-46'dadır.
- **Kural setleri `rule_sets` tablosunda.** Varsayılan set kiracısızdır (0. sürüm, tohumdan). Kulüp setleri değişmez sürümlerdir ve `base_version` ile iyimser eşzamanlılık kullanır. Uçlar:
  - `GET /rule-sets/current`
  - `PUT /rule-sets/current`
  - `GET /rule-sets/versions`
  - `POST /rule-sets/dry-run` (taslak setle de çalışır, kaydetmez)
- **Öneriler karar anında yazılır (A-50).**
  - `GET /fixtures/{id}/prep` önerileri o an hesaplar ve kayıtlı kararları üstüne bindirir.
  - `POST /recommendations/{id}/decision` kanıtın, metnin ve kural sürümünün anlık görüntüsünü yazar.
  - Kimlik `uuid5(fikstür, kural, rutin)` olduğu için, kural yeniden hesaplanınca aynı öneriye denk gelir.
- **Maç planı (`fixture_plans`, `plan_items`)** iki MD şablonundan (A-52) oluşturulur. Maddelerin MD kodu, sorumlusu, durumu ve isteğe bağlı bağları (öneri, rutin) vardır. Kabul edilen öneri plana madde ekler.
- **İzinler** (SPEC §12.1):
  - Öneri kararı `decide_recommendations`.
  - Plan maddeleri `mark_plan_items`.
  - Kural ayarları `rule_settings`.
  - Okuma `read_analysis`.

## Sonuçlar
- **Artı:** Değerlendirici saf ve testli. Aynı kod hem ekranı hem deneme modunu besler; deneme modunun "neden tetiklenmedi" açıklaması da buradan gelir.
- **Artı:** Ekranı açmak yazma yapmaz. Kurallar değiştiğinde kararı verilmemiş öneriler kendiliğinden güncellenir, verilmiş kararlar kendi kanıtıyla kalır.
- **Eksi:** Her hazırlık açılışında iki sezonun metrikleri hesaplanır (18 takım; milisaniyeler mertebesinde). Gerekirse istek başına önbelleğe alınır.
- **Eksi:** Kural metinleri v1'de kulüp tarafından düzenlenemez (A-51).

## Değerlendirilen seçenekler
- **Önerileri worker ile önceden üretip saklamak:** Kural ya da veri değişince bayat kalır ve yeniden üretim tetikleyicileri gerekir. Reddedildi.
- **JSONLogic gibi hazır bir kural kütüphanesi:** SPEC'in sıra ve yüzdelik operatörlerini, kanıt üretimini ve güven hesabını yine elle yazmak gerekecekti. Bağımlılık eklemeye değmez. Reddedildi.
- **Kuralları tablo satırlarına bölmek:** Sürüm anlık görüntüsü ve deneme modu zorlaşır. Set bütün halinde JSON olarak saklanır.
