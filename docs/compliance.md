# KVKK uyum notları

İlgili: SPEC §12.3, ADR-0014, ADR-0019, A-92. Bu belge teknik önlemleri ve kulübün hukuk ekibine açık soruları listeler; hukuki görüş değildir.

## Roller
- **Veri sorumlusu:** kulüp. Kurgu'yu kulüp adına işleten ekip veri işleyendir; aralarında veri işleme sözleşmesi gerekir.
- **İlgili kişiler:** oyuncular (kadro), kulüp personeli (kullanıcılar), rakip ve lig oyuncuları (alenileştirilmiş ya da lisanslı veri).

## Uygulamadaki teknik ve idari önlemler
| Konu | Kurgu'da | Kanıt |
|---|---|---|
| Kişisel veri envanteri | Kodda tek kayıt; `/admin/privacy` ekranı. Kişisel veri taşıyan her tablonun envanterde olduğu testle denetlenir. | `privacy/inventory.py`, `tests/test_privacy.py` |
| Özel nitelikli veri (sağlık: iyi oluş) | Açık rıza olmadan kaydedilmez (409 `consent-required`); rıza metni sürümlü; oyuncu kendisi verir ya da ıslak imzalı form referansıyla kaydedilir; geri çekilebilir. | `privacy/consent.py`, `privacy/router.py` |
| Şifreleme | İyi oluş puanları alan düzeyinde zarf şifreleme (AES-256-GCM); yedekler age ile şifreli; aktarımda TLS. | ADR-0014, ADR-0018 |
| Erişim kontrolü | Rol izin matrisi, kiracı başına RLS, yönetici/sağlık/performans için MFA. | SPEC §12.1, ADR-0016 |
| Erişim kaydı | İyi oluş okuma ve yazmaları, dışa aktarma, rıza ve talepler denetim kaydına yazılır. | `audit_log` |
| Saklama ve imha | Kulüp ayarı (iyi oluş 730, yük 1095, denetim 730 gün varsayılan); her gece süresi dolan kayıtlar silinir, sayılar denetim kaydına yazılır. | `privacy/jobs.py` |
| İlgili kişi hakları (m.11) | Oyuncu kendi verisini JSON olarak indirir; silme talebi açar; yönetici onaylar; veriler silinir, kadro kaydı anonimleşir. | `/me`, `/admin/privacy` |
| Veri bölgesi | Kiracı alanı (`tenants.data_region`); `/admin/privacy` ekranında gösterilir. | `privacy/router.py` |
| Gözlem araçları | Sentry olaylarından kişisel veri temizlenir; loglarda yalnız kimlikler. | `core/observability.py` |
| İhlal | Olay müdahalesi runbook'u; 72 saatlik bildirim süresi. | `docs/runbooks/incident.md` |

## Kulübün hukuk ekibine açık sorular
1. **Hukuki dayanaklar:** envanterdeki dayanaklar varsayımdır (sözleşmenin ifası, meşru menfaat, açık rıza). Özellikle antrenman yükü (sRPE, sıçrama, kafa vuruşu) sağlık verisi sayılır mı? Sayılırsa açık rıza kapsamına alınmalı ve şifrelenmelidir.
2. **Açık rıza metni:** `CONSENT_VERSION 2026-10-v1` taslaktır. Aydınlatma metniyle birlikte onaylanmalı; onaylanan metin yeni bir sürüm olarak yayımlanır ve oyunculardan yeniden rıza alınır.
3. **Reşit olmayan oyuncular:** altyapı oyuncuları için veli rızası nasıl alınacak? v1 yalnız A takım kadrosunu varsayar.
4. **VERBİS kaydı:** kulübün kaydında Kurgu'nun işlediği veri kategorileri (envanter) yer almalı.
5. **Yurt dışına aktarım:** barındırma, nesne deposu, Sentry, OpenTelemetry toplayıcısı ve LLM sağlayıcısı yurt dışındaysa m.9 kapsamında değerlendirilmeli. LLM brifinginin girdisi rakip raporu ve maç planı özetidir (`llm/service.py`, `build_input`); iyi oluş ve yük verisi içermez. Sağlayıcının konumu ve girdideki oyuncu adları m.9 açısından değerlendirilmeli; brifing kulüp ayarıyla tamamen kapatılabilir (`/admin/llm`).
6. **Saklama süreleri:** varsayılan süreler kulübün imha politikasıyla eşleştirilmeli. Denetim kaydının en az süresi (365 gün alt sınır) yeterli mi?
7. **Silme ve meşru istisnalar:** sözleşme uyuşmazlığı ya da sakatlık sigortası gibi durumlarda silme talebi reddedilebilir mi? Ret gerekçesi talep kaydına not olarak yazılır.
8. **Video:** maç ve antrenman videolarında oyuncuların görüntüsü kişisel veridir; saklama süresi ve erişim kuralı belirlenmeli (v1'de kulüp elle siler).
9. **Veri işleme sözleşmesi** ve alt işleyenler listesi (bulut sağlayıcı, e-posta, hata izleme).

## Yapılacaklar (kulüp tarafı)
- Aydınlatma metni ve rıza metninin onayı; `privacy/consent.py` güncellemesi.
- Saklama sürelerinin `/admin/privacy` ekranından ayarlanması.
- Kâğıt rıza formlarının fiziksel saklama yeri ve referans biçimi.
