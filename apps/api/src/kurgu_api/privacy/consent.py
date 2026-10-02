"""İyi oluş verisi için aydınlatma ve açık rıza metni (SPEC §12.3, ADR-0019, A-92).

Metin şablondur; kulübün hukuk ekibi onaylayınca sürüm artırılarak güncellenir. Rıza kaydı hangi
sürüme verildiğini saklar.
"""

CONSENT_VERSION = "2026-10-v1"

CONSENT_TEXT = (
    "Kulübümüz, toparlanmanızı ve sakatlık riskinizi izlemek için günlük iyi oluş puanlarınızı "
    "(uyku, stres, yorgunluk, kas ağrısı) Kurgu uygulamasında işler. Bu puanlar sağlıkla ilgili "
    "özel nitelikli kişisel veridir ve yalnız açık rızanızla işlenir. Puanlar şifreli saklanır; "
    "yalnız performans ve sağlık ekibi görür, kulüp yöneticisi yalnız takım özetini görür. Her "
    "erişim kayıt altına alınır. Veriler kulübün belirlediği saklama süresi sonunda silinir. "
    "Rızanızı istediğiniz zaman geri çekebilirsiniz; geri çekme yeni kayıt girilmesini durdurur. "
    "Verilerinizin bir kopyasını isteyebilir ve silinmesini talep edebilirsiniz (KVKK m.11)."
)
