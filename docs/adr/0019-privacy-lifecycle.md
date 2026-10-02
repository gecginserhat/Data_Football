# ADR-0019: KVKK veri yaşam döngüsü

- **Durum:** Kabul edildi · 01.10.2026
- **İlgili:** SPEC §12.3; A-92; ADR-0014

## Bağlam
İyi oluş verisi özel nitelikli kişisel veridir ve açık rızaya dayanır. SPEC aydınlatma ve rıza kaydı, kişisel veri envanteri, saklama süreleri ve otomatik silme, veri sahibinin dışa aktarma ve silme talebi ile veri bölgesi seçimini ister. Oyuncuların bir kısmının hesabı olmayabilir.

## Karar
- Rıza kadro oyuncusuna bağlıdır (`health_consents`). Oyuncu kendi hesabından rıza verebilir; hesabı olmayan oyuncu için performans ekibi kâğıt rızayı belge referansıyla kaydeder. İyi oluş yazımı etkin rıza ister.
- Kişisel veri envanteri kodda tek bir kayıttır (`privacy/inventory.py`): tablo, alanlar, veri kategorisi, amaç, hukuki dayanak ve saklama ayarı. Ekran ve döküm bu kayıttan üretilir. Bir test, kişisel veri taşıyan her tablonun envanterde olduğunu denetler.
- Saklama süreleri `tenants.settings.retention` içindedir. Worker'daki gecelik görev süresi dolan kayıtları siler ve her kiracı için silme sayılarını denetim kaydına yazar.
- Veri sahibi talepleri `privacy_requests` tablosunda izlenir (dışa aktarma ya da silme; açık, tamamlandı, reddedildi). Dışa aktarma anında üretilir ve denetlenir. Silme yönetici onayı ister. Onayda oyuncunun iyi oluş, yük, rıza ve atama kayıtları silinir, kadro kaydı anonimleştirilir ve hesap bağlantısı kaldırılır. Denetim kayıtları yasal saklama gereği silinmez.

## Sonuçlar
- Anonimleştirilen oyuncunun geçmiş markaj planlarında kimliği "silinmiş oyuncu" olarak görünür.
- Hukuki yorum gerektiren konular (VERBİS, yurt dışına aktarım, süreler) `docs/compliance.md` dosyasında kulübün hukuk ekibine açık soru olarak bırakılır.
