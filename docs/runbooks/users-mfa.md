# Kullanıcı ve MFA yönetimi

İlgili: SPEC §12.1 (roller), ADR-0016, A-90. Kimlik Keycloak'ta, kulüp üyeliği ve roller Kurgu veritabanındadır.

## Kullanıcı ekleme
1. Kişinin kimlik sağlayıcıda hesabı olmalı. Yerelde: Keycloak yönetim konsolu → `kurgu` realm → Users → Add user; kullanıcı adı, e-posta, "Email verified" açık. Credentials sekmesinde geçici parola ("Temporary" açık).
2. Kulüp yöneticisi Kurgu'da `/admin/users` → **Davet gönder**: aynı e-posta ve roller (A-100). Davet 14 gün geçerlidir.
3. Kişi bu e-postayla Kurgu'ya girince davet üyeliğe dönüşür. E-posta IdP'de doğrulanmamışsa (`email_verified` yok) davet açılmaz ve kişi hiçbir kulübe üye olmadan girer.
4. Rol değiştirme ve kulüpten çıkarma da `/admin/users` ekranındadır; her işlem denetim kaydına (`/admin/audit`) yazılır. Kulübün son yöneticisi düşürülemez.
5. Oyuncu hesabı `/admin/squad` ekranında kadrodaki oyuncuyla eşleştirilir; oyuncu yalnız kendi yükünü, rızasını ve görev kartlarını görür.

Roller: `admin`, `head_coach`, `sp_coach`, `analyst`, `performance`, `medical`, `player`, `viewer`; izinler SPEC §12.1 matrisindedir.

**Hiç yönetici kalmadıysa (kurtarma):** uygulama son yöneticinin düşürülmesine izin vermez; yine de gerekirse veritabanında, olay kaydına yazarak:
```sql
insert into memberships (user_id, tenant_id, role)
select id, '<kulüp tenant_id>', 'admin' from users where email = 'ad.soyad@kulup.org';
```

## MFA
- Yönetici, sağlık ve performans rollerinde MFA zorunludur (`KURGU_ENV` staging/production ya da `KURGU_REQUIRE_MFA=true`; kulüp ayarı `mfa_required` tüm rollere açar).
- Kullanıcı MFA istenen bir sayfayı açınca Kurgu "Kodla devam et" ekranını gösterir; Keycloak doğrulayıcı uygulama (TOTP) kurulumunu ister: Google Authenticator, Microsoft Authenticator, 1Password vb. 6 haneli, 30 sn.
- **Telefonu kaybeden kullanıcı:** Keycloak → Users → kullanıcı → Credentials → OTP kaydını silin. Kullanıcı bir sonraki girişte yeniden kurar. Kimliği başka bir kanaldan doğrulamadan silmeyin; işlemi olay kaydına yazın.
- Kurtarma kodları v1'de yok; yönetici sıfırlaması tek yoldur.

## Kilitlenme
Kaba kuvvet koruması: 5 hatalı denemede geçici kilit (60 sn'den başlar, en çok 15 dk). Kilit süre dolunca kalkar. Erken açmak için: Users → kullanıcı → "Temporarily locked" anahtarını kapatın.

## Ayrılan personel
1. Keycloak'ta kullanıcıyı devre dışı bırakın ve oturumlarını sonlandırın (Sessions → Sign out). Silmeyin: denetim kaydındaki `actor_id` izlenebilir kalmalı.
2. Kurgu'da `/admin/users` ekranından kulüpten çıkarın.
3. Kişinin bildiği paylaşılan bir sır varsa döndürün ([keys.md](keys.md)).

## Oyuncu ayrılınca (KVKK)
Oyuncu ya da sağlık ekibi oyuncu sayfasından silme talebi açar; yönetici `/admin/privacy`'de onaylar. Onay; iyi oluş, yük, rıza ve görev kayıtlarını siler, adı "Silinmiş oyuncu" yapar. Ayrıntı: [../compliance.md](../compliance.md).
