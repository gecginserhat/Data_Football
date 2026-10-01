# ADR-0014: İyi oluş verisi için alan düzeyinde zarf şifreleme

- **Durum:** Kabul edildi · 01.10.2026
- **İlgili:** SPEC §8.3, §12.2, §12.3; CLAUDE.md "Güvenlik"; A-86

## Bağlam
İyi oluş ve sağlık verisi KVKK'da özel nitelikli kişisel veridir. SPEC alan düzeyinde zarf şifreleme ve her erişimin denetim kaydını ister. RLS kiracılar arası sızıntıyı önler ama veritabanı yedeğini ya da veritabanına doğrudan erişimi korumaz.

## Karar
- Her şifreli değer için rastgele bir veri anahtarı (DEK, 256 bit) üretilir. Değer AES-256-GCM ile bu anahtarla şifrelenir. DEK de anahtar şifreleme anahtarıyla (KEK) AES-256-GCM ile sarılır. Saklanan biçim sürümlü bir JSON zarfıdır: `{v, kid, wrapped_dek, nonce, ciphertext}`. İlişkili veri (AAD) olarak kiracı kimliği, tablo ve alan adı bağlanır; başka kiracıya ya da alana kopyalanan zarf çözülmez.
- KEK'ler `KURGU_DATA_KEYS` değişkeninden (`kid:base64` listesi) okunur; ilk anahtar yeni kayıtlarda kullanılır, diğerleri yalnız okuma içindir (döndürme). Üretimde bu değişken bir KMS'ten ya da anahtar dosyasından beslenir. Geliştirme ve testte sabit bir geliştirme anahtarı kullanılır; üretimde anahtar yoksa uygulama başlamaz.
- Şifreleme ve çözme yalnız API'nin `core/crypto.py` modülünde yapılır. İyi oluş okuma ve yazma uçları her erişimde denetim kaydı yazar (kim, hangi oyuncu, hangi tarih aralığı).

## Sonuçlar
- Şifreli alanlarda veritabanı tarafında sorgu ve toplama yapılamaz; Hooper hesapları API'de çözülmüş değerler üzerinden yapılır. Veri boyutu küçük olduğu için kabul edildi.
- Anahtar kaybı veri kaybıdır; anahtar yedekleme runbook'u Faz 8'de yazılır.
