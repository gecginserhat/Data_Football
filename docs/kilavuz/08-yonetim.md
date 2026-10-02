# 8. Yönetim

Bu bölüm kulüp yöneticisi içindir. Yönetim sayfalarına girerken iki adımlı doğrulama istenir.

## Veri içe aktarma
**Yönetim → İçe aktarma** (`/admin/imports`) kulübünüzün kendi duran top kayıtlarını CSV ya da Excel dosyasından alır.

1. Dosyayı seçip **Yükle ve doğrula**. Dosya önce **Karantinada** bekler.
2. Sütun eşleştirmesini ve takım adlarını kontrol edin, gerekirse düzeltip **Eşleştirmeyi kaydet ve yeniden doğrula**.
3. Hata kalmadığında **Veriyi işle**. Durum **İşlendi** olur ve metrikler güncellenir. Kulübün kendi verisi, aynı metrik için lig verisinin yerine geçer.

![Karantina](../demo/faz1/tablet-import-quarantined.png)

Excel dosyası değilmiş gibi görünen ya da aşırı büyük açılan dosyalar güvenlik nedeniyle reddedilir.

## Öneri kuralları
**Yönetim → Kurallar** (`/admin/rules`) önerileri üreten kuralları düzenlemek içindir. Değişikliği **Taslağı dene** ile önce örnek maçlarda deneyin; sonuç beğenilirse **Yeni sürüm yayımla**. Eski sürümler geçmişte kalır.

![Kural denemesi](../demo/faz4/desktop-rules-dry-run.png)

## Yapay zekâ
**Yönetim → Yapay zekâ brifingi** (`/admin/llm`) özelliği açıp kapatır ve aylık istek ve token sınırını belirler. Model ve anahtar sunucu ayarlarındadır; anahtar bu sayfada gösterilmez.

![Yapay zekâ ayarı](../demo/faz6/desktop-admin-llm.png)

## Kadro
Bkz. [Performans, kadro ve markaj](06-performans-ve-kadro.md#kadro).

## Gizlilik (KVKK)
**Yönetim → Kişisel veriler (KVKK)** (`/admin/privacy`) üç bölümden oluşur:

- **Talepler**: oyuncuların silme taleplerini **Onayla ve sil** ya da **Reddet** ile sonuçlandırın. Onay geri alınamaz.
- **Saklama süreleri**: iyi oluş, antrenman yükü ve denetim kayıtlarının kaç gün saklanacağını girip **Kaydet**. Süresi dolan kayıtlar her gece silinir.
- **Veri envanteri**: hangi kişisel verinin nerede, hangi amaçla tutulduğunun listesi.

![Gizlilik](../demo/faz8/tablet-admin-privacy.png)

## Kullanıcılar ve roller
**Yönetim → Kullanıcılar ve roller** (`/admin/users`) kulübünüzdeki kişileri ve rollerini gösterir.

- **Rolleri değiştirmek:** kişinin kartında **rolleri düzenle**'yi açın, rolleri işaretleyip **Rolleri kaydet**. Bir kişinin birden çok rolü olabilir. Yönetici, sağlık ve performans rolleri iki adımlı doğrulama ister.
- **Kulüpten çıkarmak:** aynı bölümde **Eminim, kulüpten çıkar** kutusunu işaretleyip çıkar düğmesine basın. Kişi kulübün verilerine erişemez; kimlik sağlayıcıdaki hesabı açık kalır.
- Kulüpte en az bir yönetici kalmalıdır. Son yönetici kendi yönetici rolünü bırakamaz; önce başka birine yönetici rolü verin.

![Kullanıcılar](../demo/uyelik/tablet-users.png)

### Davet
**Davet gönder** bölümüne kişinin e-postasını yazın, rollerini seçip **Davet gönder**'e basın. Kişi bu e-postayla Kurgu'ya ilk girdiğinde seçtiğiniz rollerle kulübe katılır. Davet 14 gün geçerlidir; **Bekleyen davetler** listesinden geri çekebilirsiniz.

Kurgu e-posta göndermez: kişiye Kurgu adresini siz iletin. Kişinin kimlik sağlayıcıda (yerelde Keycloak, canlıda kulübün giriş sistemi) bu e-postayla doğrulanmış bir hesabı olmalıdır.

![Davet](../demo/uyelik/tablet-invite.png)

## Denetim kaydı
**Yönetim → Denetim kaydı** (`/admin/audit`) kimin, ne zaman, neyi değiştirdiğini ya da hassas veriyi görüntülediğini gösterir. **Tür** süzgeciyle (ör. Davetler, KVKK talepleri, İyi oluş) daraltın; **Daha eski kayıtlar** ile geriye gidin. Kayıtlar değiştirilemez; saklama süresi **Kişisel veriler (KVKK)** sayfasında ayarlanır.

![Denetim kaydı](../demo/uyelik/tablet-audit.png)
