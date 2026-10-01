# SPADL eşleyici uyumu: Kurgu ve socceraction 1.5.3

30 StatsBomb Open Data maçı, olay kimliğiyle eşleştirme. Bu dosya `scripts/compare_socceraction.py` ile üretilir.

| Ölçü | Değer |
|---|---:|
| Kurgu aksiyonu | 64083 |
| socceraction aksiyonu (sentetik dribble hariç) | 64077 |
| Ortak olay | 64074 |
| Tür uyumu | %100.00 |
| Tür + sonuç + vücut bölgesi uyumu | %99.78 |

## En sık farklar (Kurgu → socceraction)

| Kurgu | socceraction | Adet |
|---|---|---:|
| keeper_save | (yok) | 9 |
| (yok) | interception | 3 |

Data: StatsBomb Open Data (https://github.com/statsbomb/open-data).
