# Duran top çıkarımı doğrulama raporu

Bu dosya `make validate` ile üretilir; elle düzenlenmez. Yöntem: SPEC §5.5, assumptions A-07.

**Veri:** 149 maç (FIFA World Cup 2022, UEFA Euro 2024, 1. Bundesliga 2023/2024). Data: StatsBomb Open Data (https://github.com/statsbomb/open-data).

**Ölçü:** Şut düzeyinde etiket uyumu. Bizim etiketimiz şutun ait olduğu duran top dizisinin türüdür (yoksa `none`); StatsBomb etiketi şutun `play_pattern` alanıdır. Penaltılar iki taraftan da çıkarılmıştır.

## Özet

| Ayar | Şut | Ham uyum | Tanım farkları hariç uyum | Duran top şutlarında ham uyum |
|---|---:|---:|---:|---:|
| Varsayılan (uzun taç, 20 sn) | 3642 | %74,3 | %99,5 | %52,7 |
| Tüm taçlar, 20 sn | 3642 | %78,3 | %98,9 | %60,1 |

Hedef %95. Ham uyum (StatsBomb etiketiyle birebir): **tutmadı**. Tanım farkları hariç uyum: **tuttu**.

Neden iki ölçü var: StatsBomb `play_pattern` etiketi topa sahip olma (possession) boyunca süre sınırı olmadan taşınır ve tüm taçları kapsar. Şartnamemizdeki duran top tanımı ise teslimden sonra 20 saniyelik pencereyle ve yalnızca uzun taçlarla sınırlıdır (SPEC §3.1, §3.2). Bu yüzden StatsBomb'un duran top dediği ama bizim tanımımızın dışında kalan şutlar (kısa taç, 20 saniyeden sonra gelen şut) ham ölçüde uyumsuz görünür. "Tanım farkları hariç" ölçüsü bu iki grubu uyumlu sayar; geriye kalan uyumsuzluklar algoritmanın gerçek farklarıdır (aşağıdaki neden tablosu).

"Duran top şutlarında ham uyum", iki taraftan en az birinin duran top dediği şutlarla sınırlı, daha sert ölçüdür.

## Pencere duyarlılığı (tüm taçlar)

Pencere uzadıkça etiketimiz StatsBomb'un possession tanımına yaklaşır. Bu tablo farkın algoritmadan değil tanımdan geldiğini gösterir.

| Pencere | Ham uyum | Duran top şutlarında ham uyum |
|---:|---:|---:|
| 20 sn | %78,3 | %60,1 |
| 60 sn | %90,3 | %82,2 |
| 180 sn | %92,1 | %85,7 |

## Tür bazında kesinlik ve duyarlılık (varsayılan ayar)

| Tür | Kesinlik | Duyarlılık |
|---|---:|---:|
| corner | %100,0 | %87,3 |
| free_kick | %99,5 | %57,6 |
| throw_in | %100,0 | %16,4 |
| throw_in (tüm taçlar) | %100,0 | %38,1 |

Taç duyarlılığı varsayılan ayarda düşüktür, çünkü tanımımız bilinçli olarak dardır: yalnızca hücum üçte birinden ceza sahasına atılan uzun taçlar duran toptur (CLAUDE.md sözlüğü). StatsBomb tüm taçları sayar.

## Şut sonucu türetme

Dizi sonucu (`shot_on_target`, `shot_off_target`, `shot_blocked`) sağlayıcıdan bağımsız türetilir: rakip kaleci kurtarışı isabetli, kale çizgisine ulaşan isabetsiz, ulaşmayan engellenmiş sayılır. Tüm şutlarda StatsBomb sonucuyla uyum: **%94,1**.

| Bizim ↓ / StatsBomb → | goal | shot_on_target | shot_off_target | shot_blocked |
|---|---:|---:|---:|---:|
| goal | 352 | 0 | 0 | 0 |
| shot_on_target | 0 | 884 | 15 | 13 |
| shot_off_target | 0 | 0 | 1206 | 9 |
| shot_blocked | 0 | 0 | 178 | 985 |

## Karışıklık matrisi (varsayılan ayar)

| Bizim ↓ / StatsBomb → | corner | free_kick | throw_in | none |
|---|---:|---:|---:|---:|
| corner | 537 | 0 | 0 | 0 |
| free_kick | 0 | 394 | 0 | 2 |
| throw_in | 0 | 0 | 111 | 0 |
| none | 78 | 290 | 567 | 1663 |

## Karışıklık matrisi (tüm taçlar)

| Bizim ↓ / StatsBomb → | corner | free_kick | throw_in | none |
|---|---:|---:|---:|---:|
| corner | 537 | 0 | 0 | 0 |
| free_kick | 0 | 394 | 0 | 2 |
| throw_in | 0 | 0 | 258 | 0 |
| none | 78 | 290 | 420 | 1663 |

## Uyumsuzluk nedenleri (varsayılan ayar)

| Neden | Adet |
|---|---:|
| kısa taç (uzun taç filtresi) | 571 |
| pencere dışı (> 20 sn) | 349 |
| top kaybıyla dizi bitti | 15 |
| StatsBomb topa sahip olmayı yeni atak saydı | 2 |

Nedenler şuttan geriye doğru son ölü topa bakılarak otomatik atanır; yaklaşık sınıflamadır.
StatsBomb'un `play_pattern` alanı topa sahip olma (possession) boyunca taşınır ve süre sınırı yoktur; bizim tanımımız 20 saniyelik pencere ve top kaybıyla biter (SPEC §3.2).

## Örnek uyumsuzluklar

| Maç | Periyot | Dakika | Bizim | StatsBomb | Neden |
|---|---:|---:|---|---|---|
| 3857276 | 1 | 3:29 | none | throw_in | kısa taç (uzun taç filtresi) |
| 3857276 | 1 | 22:36 | none | throw_in | kısa taç (uzun taç filtresi) |
| 3857271 | 1 | 29:08 | none | free_kick | pencere dışı (67 sn) |
| 3857271 | 2 | 13:56 | none | free_kick | pencere dışı (24 sn) |
| 3857271 | 2 | 24:03 | none | throw_in | kısa taç (uzun taç filtresi) |
| 3857271 | 2 | 44:01 | none | free_kick | pencere dışı (85 sn) |
| 3857275 | 1 | 46:45 | none | free_kick | top kaybıyla dizi bitti |
| 3857285 | 2 | 19:40 | none | free_kick | top kaybıyla dizi bitti |
| 3869685 | 2 | 13:21 | none | free_kick | top kaybıyla dizi bitti |
| 3938639 | 1 | 40:43 | free_kick | none | StatsBomb topa sahip olmayı yeni atak saydı |
| 3895194 | 1 | 17:09 | free_kick | none | StatsBomb topa sahip olmayı yeni atak saydı |
