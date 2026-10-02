# Kullanıcı ve MFA yönetimi

İlgili: SPEC §12.1 (roller), ADR-0016, A-90. Kimlik Keycloak'ta, kulüp üyeliği ve roller Kurgu veritabanındadır.

## Kullanıcı ekleme
1. Keycloak yönetim konsolu → `kurgu` realm → Users → Add user. Kullanıcı adı, e-posta, "Email verified". Credentials sekmesinde geçici parola ("Temporary" açık).
2. Kullanıcı ilk girişte parolasını değiştirir. Kurgu, ilk girişte kullanıcı kaydını oluşturur.
3. Kulüp üyeliği ve rol: v1'de üyelik ekranı yok (bkz. Faz 8 raporu, riskler). Operatör, kullanıcının ilk girişinden sonra veritabanında ekler; rollerin izinleri SPEC §12.1 matrisindedir:
   ```sql
   insert into memberships (user_id, tenant_id, role)
   select id, '<kulüp tenant_id>', 'analyst' from users where email = 'ad.soyad@kulup.org';
   ```
   Roller: `admin`, `head_coach`, `sp_coach`, `analyst`, `performance`, `medical`, `player`, `viewer`. Bir kullanıcının birden çok rolü ayrı satırlardır.
4. Oyuncu hesabı `/admin/squad` ekranında kadrodaki oyuncuyla eşleştirilir; oyuncu yalnız kendi yükünü, rızasını ve görev kartlarını görür.

## MFA
- Yönetici, sağlık ve performans rollerinde MFA zorunludur (`KURGU_ENV` staging/production ya da `KURGU_REQUIRE_MFA=true`; kulüp ayarı `mfa_required` tüm rollere açar).
- Kullanıcı MFA istenen bir sayfayı açınca Kurgu "Kodla devam et" ekranını gösterir; Keycloak doğrulayıcı uygulama (TOTP) kurulumunu ister: Google Authenticator, Microsoft Authenticator, 1Password vb. 6 haneli, 30 sn.
- **Telefonu kaybeden kullanıcı:** Keycloak → Users → kullanıcı → Credentials → OTP kaydını silin. Kullanıcı bir sonraki girişte yeniden kurar. Kimliği başka bir kanaldan doğrulamadan silmeyin; işlemi olay kaydına yazın.
- Kurtarma kodları v1'de yok; yönetici sıfırlaması tek yoldur.

## Kilitlenme
Kaba kuvvet koruması: 5 hatalı denemede geçici kilit (60 sn'den başlar, en çok 15 dk). Kilit süre dolunca kalkar. Erken açmak için: Users → kullanıcı → "Temporarily locked" anahtarını kapatın.

## Ayrılan personel
1. Keycloak'ta kullanıcıyı devre dışı bırakın ve oturumlarını sonlandırın (Sessions → Sign out). Silmeyin: denetim kaydındaki `actor_id` izlenebilir kalmalı.
2. Kurgu'da üyeliği kaldırın.
3. Kişinin bildiği paylaşılan bir sır varsa döndürün ([keys.md](keys.md)).

## Oyuncu ayrılınca (KVKK)
Oyuncu ya da sağlık ekibi oyuncu sayfasından silme talebi açar; yönetici `/admin/privacy`'de onaylar. Onay; iyi oluş, yük, rıza ve görev kayıtlarını siler, adı "Silinmiş oyuncu" yapar. Ayrıntı: [../compliance.md](../compliance.md).
