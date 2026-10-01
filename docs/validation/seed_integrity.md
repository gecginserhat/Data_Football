# Tohum bütünlük raporu

Kaynak: `seed/super_lig.json` (derlenme 2026-09-28). Bu dosya `make seed-report` ile üretilir; elle düzenlenmez.

| Kontrol | Sonuç |
|---|---|
| Referans bütünlüğü (takım kimlikleri) | Tuttu |
| 1. Gol kırılımı = toplam gol (0-1 tolerans) | Uyarı (7 bulgu) |
| 2. Sonuçlardan puan tablosu | Tuttu |
| 3. Duran top golü 166 / toplam gol 812 | Tuttu |

## Kontrol 1 farkları

Veri düzeltilmedi (assumptions A-02). Fark büyük olasılıkla kaynaklar arası tanım farkından ve kendi kalesine gollerden geliyor. Yükleme durmaz; kayıtlar olduğu gibi yüklenir.

| Takım | Gol | Akan oyun | Hızlı hücum | Penaltı | Duran top | Fark |
|---|---:|---:|---:|---:|---:|---:|
| GS | 77 | 48 | 8 | 6 | 11 | +4 |
| IBFK | 58 | 33 | 5 | 6 | 11 | +3 |
| SAM | 46 | 29 | 5 | 2 | 7 | +3 |
| FB | 77 | 47 | 8 | 6 | 14 | +2 |
| GEN | 36 | 15 | 5 | 4 | 10 | +2 |
| KAS | 33 | 16 | 4 | 4 | 7 | +2 |
| KON | 43 | 25 | 3 | 5 | 8 | +2 |
