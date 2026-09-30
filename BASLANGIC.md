# Başlangıç: Windows'ta Claude masaüstü uygulamasıyla Kurgu

Önerilen kurulum şudur: Claude masaüstü uygulaması, Code sekmesi, oturumlar **WSL 2 (Ubuntu)** üzerinde, proje dosyaları Ubuntu içinde. Bu projede Docker, Postgres, Python ve Next.js birlikte çalıştığı için en hızlı ve en az sorun çıkaran yol bu.

> Code sekmesi ücretli bir Claude planı gerektirir (Pro, Max, Team ya da Enterprise).

---

## 1. Programları kurun (bir kez)

1. **Claude masaüstü uygulaması:** claude.com/download adresinden Windows sürümünü indirip kurun ve hesabınızla giriş yapın. Uygulama Claude Code'u içinde getirir; ayrıca kurmanız gereken bir şey yoktur.
2. **WSL 2 ve Ubuntu:** Başlat menüsünde **PowerShell**'e sağ tıklayın, **Yönetici olarak çalıştır**'ı seçin ve şunu yazın:
   ```
   wsl --install
   ```
   Bilgisayarı yeniden başlatın. Ubuntu penceresi açılınca bir kullanıcı adı ve parola belirleyin. Bu parolayı unutmayın; `sudo` komutları sorar.
3. **Docker Desktop:** docker.com adresinden Windows sürümünü kurun. Sonra şu iki ayarı yapın:
   - **Settings → General:** "Use the WSL 2 based engine" işaretli olsun.
   - **Settings → Resources → WSL Integration:** **Ubuntu** açık olsun.

## 2. Ubuntu'ya geliştirme araçlarını kurun (bir kez)

Başlat menüsünden **Ubuntu**'yu açın ve komutları sırayla yapıştırın:

```bash
sudo apt update && sudo apt install -y git make build-essential curl unzip
curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash - && sudo apt install -y nodejs
sudo corepack enable
curl -LsSf https://astral.sh/uv/install.sh | sh
git config --global user.name "Adınız Soyadınız"
git config --global user.email "eposta@ornek.com"
git config --global core.autocrlf input
```

Ardından Ubuntu penceresini kapatıp yeniden açın ve kontrol edin:

```bash
docker run --rm hello-world && node -v && pnpm -v && uv --version
```

Dört komut da hata vermeden çalışıyorsa hazırsınız.

## 3. Paketi Ubuntu'ya koyun

`kurgu-claude-code.zip` dosyasını Windows'ta **İndirilenler** klasörüne indirin. Sonra Ubuntu'da şunu çalıştırın (`KULLANICI` yerine Windows kullanıcı adınızı yazın):

```bash
mkdir -p ~/projects && cd ~/projects
unzip /mnt/c/Users/KULLANICI/Downloads/kurgu-claude-code.zip
mv kurgu-claude-code kurgu && cd kurgu && git init
```

> Proje mutlaka Ubuntu'nun kendi klasöründe (`/home/...`) dursun. `C:\` altında tutarsanız Docker ve Next.js belirgin şekilde yavaşlar.

## 4. Claude Code oturumunu açın

1. Claude uygulamasında üstteki **Code** sekmesine geçin.
2. Ortam seçicide **WSL** bölümünden **Ubuntu**'yu seçin. İlk açılış biraz uzun sürer.
3. **Select folder** ile `/home/<kullanıcı>/projects/kurgu` klasörünü seçin ve klasöre güvenmeyi onaylayın.
4. Gönder düğmesinin yanındaki izin modunu ilk mesaj için **Plan** yapın. Bu modda Claude hiçbir dosyayı değiştirmeden plan çıkarır. Planı onayladıktan sonra **Accept edits** moduna geçebilirsiniz; bu modda dosya değişiklikleri otomatik uygulanır ve değişiklik göstergesinden (`+12 -1` gibi) incelenir.

> WSL oturumlarında uygulamanın gömülü terminali henüz yok. Sunucuları başlatmak ve `sudo` komutları için ayrı bir **Ubuntu** penceresi açık tutun.

## 5. İlk mesaj (olduğu gibi yapıştırın)

```
Bu repoda Kurgu'yu geliştireceğiz: Süper Lig kulüpleri için profesyonel bir duran top analiz ve hazırlık platformu. Ortam: Windows 11 + WSL 2 (Ubuntu), Docker Desktop WSL entegrasyonu açık.

1) Önce CLAUDE.md, docs/SPEC.md ve seed/ altındaki üç JSON dosyasını baştan sona oku.
2) Kod yazmadan önce:
   - docs/assumptions.md: belirsizlikleri listele; engelleyici olanları bana sor, diğerleri için varsayım yaz.
   - docs/adr/: en az 5 ADR yaz (modüler monolit, Postgres + RLS çok kiracılık, SPADL kanonik model, offline senkronizasyon, OIDC kimlik).
   - docs/PROGRESS.md: Faz 0 ve Faz 1 için ayrıntılı görev listesini çıkar.
   - sudo gerektiren kurulumlar varsa (ör. Playwright sistem bağımlılıkları) bana ayrı bir liste halinde ver; ben Ubuntu terminalinde çalıştırırım.
3) Planı bana göster ve onayımı bekle.

Onaydan sonra fazları sırayla uygula. Her adımda testleri, lint'i ve typecheck'i çalıştır, sonra commit at. Her fazın sonunda kabul kriterlerini PROGRESS.md içinde işaretle ve bana kısa bir rapor ver.
```

## 6. Çalıştırma ve görme

Faz 0 bittiğinde Ubuntu penceresinde şunu çalıştırın:

```bash
cd ~/projects/kurgu && make dev
```

Ardından Windows tarayıcısında **http://localhost:3000** adresini açın. WSL 2, bu adresi Windows'a otomatik yönlendirir.

## 7. Sonraki fazlar için kısa mesajlar
- `Faz 1 onaylandı. Başla. Duran top çıkarım doğrulama raporunu docs/validation/ altına yaz.`
- `Faz 2'ye geç. Genel bakış, Lig ve Rakip analizi sayfalarında seed verisiyle SPEC §19'daki örnek sayıları doğrula.`
- `Faz 4: öneri motorunu seed/recommendation_rules.json ile kur. Trabzonspor–Samsunspor kabul testini yaz.`

## 8. İpuçları ve sık sorunlar
- **Her faz için yeni oturum açın.** Uzun oturumlarda bağlam dolar. Yeni oturumu "CLAUDE.md ve docs/PROGRESS.md'yi oku, Faz N'e devam et" diyerek başlatın. Uygulamanın kenar çubuğunda birden fazla oturumu yan yana tutabilirsiniz.
- **`docker` komutu bulunamıyorsa:** Docker Desktop açık mı ve WSL Integration altında Ubuntu seçili mi, kontrol edin.
- **Port meşgul hatası:** Aynı port Windows'ta başka bir programca kullanılıyorsa Claude'dan `.env` üzerinden portu değiştirmesini isteyin.
- **Yavaşlık:** Projenin `/mnt/c/...` altında değil, `~/projects/kurgu` altında olduğundan emin olun.
- **Gerçek veri lisans ister.** `seed/super_lig.json` geliştirme ve demo içindir. Canlı kullanımda veri lisanslı bir sağlayıcıdan API ile gelmelidir; web kazıma yaptırmayın.

## 9. Claude Pro ile verimli çalışma
- **Limit ortak.** Claude sohbetleri ile Claude Code aynı kullanım limitini paylaşır. Uzun sohbetler de bu limitten yer. Ağır işi Claude Code'da yapın, sohbeti kısa sorular için kullanın.
- **Bir oturum, bir iş.** Her fazı ve her büyük görevi ayrı oturumda yapın. Uzun oturumlar her mesajda daha fazla bağlam taşır ve limiti daha hızlı tüketir.
- **Önce plan, sonra kod.** Plan modunda planı netleştirin. Yanlış yöne yazılan kodu geri almak, planı düzeltmekten pahalıdır.
- **Dar mesajlar yazın.** "Her şeyi yap" yerine "SPEC §5.5'teki çıkarım algoritmasını yaz ve testlerini ekle" gibi bölüm numarası veren mesajlar gönderin. Claude her seferinde bütün SPEC'i yeniden okumasın.
- **Limite yaklaşınca devir teslim yaptırın.** "Kaldığın yeri docs/PROGRESS.md'ye yaz ve commit at" deyin. Limit sıfırlanınca yeni oturum oradan devam eder.
- **Rutin işlerde daha hafif model.** Gönder düğmesinin yanındaki model seçiciden basit işler (test düzeltme, küçük arayüz değişikliği) için daha hafif bir model seçin. Bu, limitinizi daha uzun süre yeterli kılar.
- **`ANTHROPIC_API_KEY` tanımlamayın.** Bu değişken sisteminizde tanımlıysa Claude Code aboneliğiniz yerine API anahtarını kullanır ve ayrıca ücret çıkar. Kurgu'nun kendi LLM özelliği bu yüzden `KURGU_ANTHROPIC_API_KEY` adını kullanıyor; o anahtar yalnızca proje `.env` dosyasında durmalı.

---

### WSL istemezseniz: doğrudan Windows (alternatif)

Code sekmesinde ortam olarak **Local**'i seçip `C:\projeler\kurgu` gibi bir klasörle de çalışabilirsiniz. Bu durumda şunları kurmanız gerekir: Git for Windows, Docker Desktop, Node.js LTS (pnpm ile) ve `uv`. İlk mesaja da şu cümleyi ekleyin: "Ortam doğrudan Windows; Makefile yerine pnpm script'leri kullan ve tüm komutlar PowerShell'de çalışsın."

Bu yol çalışır, ancak Docker dosya paylaşımı yavaştır, bazı Linux araçları eksiktir ve satır sonu sorunları çıkabilir. Bu proje için WSL yolu önerilir.
