# ADR-0008: Rutin diyagramı, sürümleme ve dışa aktarım

- **Durum:** Kabul edildi · 01.10.2026
- **İlgili:** SPEC §3.4, §4, §10, §11, §13.2 (rutin editörü), §19 Faz 3; A-39 … A-45

## Bağlam
Rutin editörü bir duran top çizimini (oyuncular, koşular, top yolları, perdeleme, bölgeler, kareler) kaydeder, sürümler ve PNG/PDF olarak dışa aktarır. Aynı çizim üç yerde okunur: tarayıcıdaki SVG editörü, API'deki doğrulama ve dışa aktarım çizicisi. Tanımlar ayrışırsa ekrandaki ile PDF'teki çizim farklı olur.

## Karar
- **Tek JSON biçimi (v1), kanonik koordinatlarda** (SPEC §4, metre). `schema: 1`, `players[]` (`id`, `team` own/opponent, `role`, `number`, `label`, `x`, `y`), `lines[]` (`id`, `kind` run/ball_path/screen, `from`, `to`, `curve`, `player_id`), `zones[]` (`id`, `x`, `y`, `w`, `h`, `label`), `ball`, `frames[]` (`id`, `positions{player_id: [x, y]}`, `ball`, `duration_ms`). Şablon dosyasının `lines[]` yapısı korunur (A-39).
- **Geometri tek tanımlı, iki dilde, ortak test vektörleriyle.** Kavis kontrol noktası, ayna ve enterpolasyon `@kurgu/pitch` (TS) ile `kurgu_analytics.reports.diagram` (Python) içinde; `packages/pitch/diagram.vectors.json` her iki tarafın testinde aynı beklenen değerleri doğrular (zones.json ile aynı desen).
- **Rol sözlüğü** `packages/pitch/roles.json`: rol kimliği, takım tarafı ve tr/en adı. Web ve PDF aynı dosyayı okur.
- **Sürümleme:** `routines` başlık kaydı (güncel ad, tür, taraf, `current_version`, arşiv), `routine_versions` değişmez anlık görüntü (ad, taraf, notlar, ne zaman kullanılır, diyagram, mesaj, yazan, zaman). Uygulama rollerine `routine_versions` üzerinde güncelleme ve silme yetkisi verilmez. İyimser eşzamanlılık: `PUT` `base_version` ister, güncel değilse 409 (A-41).
- **Şablonlar** paylaşılan `routine_templates` tablosunda (kiracısız, herkes okur, göç rolü yazar). Şablondan ekleme, şablonun diyagramıyla 1. sürümü açar ve `from_template` bağını tutar (A-40).
- **Dışa aktarım** API'de eşzamanlı: `kurgu_analytics.reports.routine_sheet` (matplotlib) kaydedilmiş sürümü PNG ya da A4 vektör PDF olarak çizer. Rakip raporu gibi çok sayfalı raporlar Faz 6'da worker'da (A-42).
- **Editör durumu** Zustand + zundo (SPEC yığını): geri al / yinele yalnızca diyagram ve başlık alanlarını izler; seçim, araç ve kare seçimi geçmişe girmez.

## Sonuçlar
- **Artı:** Ekran, API doğrulaması ve PDF aynı biçimi ve aynı geometriyi kullanır; sapma testte yakalanır.
- **Artı:** Sürümler değişmez olduğundan maç kayıtları ve öneriler (Faz 4-5) belirli bir sürüme güvenle bağlanabilir.
- **Eksi:** PDF yazı tipi web'deki IBM Plex değil, DejaVu Sans (A-42).
- **Eksi:** matplotlib API imajına eklenir (~40 MB).

## Değerlendirilen seçenekler
- **İstemcide PDF (jsPDF + svg2pdf):** Kaydedilmemiş çizim de aktarılabilirdi; ama Türkçe karakterler için TTF gömmek ve ikinci bir çizim yolu gerekiyordu. Reddedildi.
- **Playwright ile sunucuda PDF:** Faz 6 raporları için uygun; tek sayfalık rutin için API imajına Chromium eklemek ağır. Faz 6'ya bırakıldı.
- **Diyagramı tablolara bölmek (oyuncu, çizgi satırları):** Sürüm anlık görüntüsü ve karşılaştırma zorlaşır; çizim her zaman bütün okunur. Reddedildi.
