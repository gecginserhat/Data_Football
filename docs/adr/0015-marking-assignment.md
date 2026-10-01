# ADR-0015: Markaj ataması için Macar algoritması

- **Durum:** Kabul edildi · 01.10.2026
- **İlgili:** SPEC §7.3, §19 Faz 7; A-80 … A-82

## Bağlam
Duran top savunmasında rakibin hedef oyuncularına kendi savunmacılarımızdan hangisinin bakacağı, hava tehdidi ile hava kapasitesi arasındaki farkı en aza indirecek biçimde seçilmeli. Antrenör son kararı verir.

## Karar
- Atama bir dikdörtgen atama problemidir ve `scipy.optimize.linear_sum_assignment` ile çözülür. Maliyet A-82'deki formüldür; skorlar `kurgu_analytics.metrics.players`, atama `kurgu_analytics.recs.marking` içindedir (saf fonksiyonlar, testli).
- Kaleci ve antrenörün alan savunmasına ayırdığı oyuncular atamaya girmez. Hedef sayısı adam sayısından fazlaysa düşük tehditli hedefler atanmadan kalır.
- Öneri her istekte yeniden hesaplanır; kaydedilen plan önerinin yanında saklanır. Kaydedilen planla öneri farklıysa satır "elle değiştirildi" diye işaretlenir. Her kayıt yeni bir sürümdür ve denetim kaydına yazılır.

## Sonuçlar
- Optimum, girilen skorlara bağlıdır; boy dışındaki bileşenler girilmezse öneri yalnız boya dayanır. Arayüz her satırda skorun hangi bileşenlerden geldiğini gösterir.
- Kural motoruyla bağ yoktur; markaj önerisi ayrı bir bölüm olarak gösterilir.
