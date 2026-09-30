# ADR-0004: Canlı kayıt için çevrimdışı öncelikli senkronizasyon

- **Durum:** Önerildi · 30.09.2026 (uygulama Faz 5)
- **İlgili:** SPEC §11 "Çevrimdışı senkronizasyon protokolü", §13.2 "Canlı kayıt", §16 E2E akış 2

## Bağlam
Analist stadyumda tabletle kayıt tutar; bağlantı güvenilmez. Hedef: dokunuştan yerel kayda ≤ 50 ms, bir duran top kaydı ≤ 3 dokunuş ve 5 sn. Birden çok analist aynı maçı kaydedebilir. Uçak modunda 20 kayıt atılıp çevrimiçine dönüldüğünde sunucuda tam 20 kayıt olmalı, yineleme olmamalı.

## Karar
- **Yerel kayıt esastır.** Her kayıt istemcide üretilen UUID v7 ile Dexie (IndexedDB) içine anında yazılır ve bir `outbox` kuyruğuna eklenir. Arayüz ağ yanıtını beklemez.
- **Senkronizasyon ucu:** `POST /tagging-sessions/{id}/sync`, gövde `[{id, op: upsert|delete, payload, client_ts, device_id}]`, `Idempotency-Key` başlığı zorunlu. Toplu ve idempotent: aynı `id` ile gelen upsert var olan satırı günceller, yeni satır açmaz.
- **Çakışma:** Kayıt düzeyinde son yazan kazanır; karşılaştırma `client_ts` ile, eşitlikte `device_id` sözlük sırasıyla (deterministik). Silme **mezar taşı** (`deleted=true`) olarak tutulur ve sonraki bir upsert ile diriltilemez (silme kazanır). Yanıtta sunucu sürümü (`server_seq`) ve reddedilen kayıtlar (gerekçesiyle) döner.
- **Çekme:** İstemci `since=server_seq` ile diğer cihazların değişikliklerini alır; çevrimiçiyken `WS /ws/tagging/{id}` yeni `server_seq` bildirir.
- **Zaman:** `created_at_client` ve `server_received_at` ayrı tutulur; maç saati manuel ya da senkronize (SPEC §13.2).
- **PWA:** Serwist ile uygulama kabuğu ve `/live/*` rotası önbelleğe alınır; Background Sync desteklenmiyorsa (iPadOS Safari) çevrimiçi olayında ve periyodik olarak kuyruk boşaltılır.
- Sunucuda senkronize kayıt `set_pieces` satırına dönüşür (`source='live_tag'`), MV yenilemesi kuyruğa alınır.

## Sonuçlar
- **Artı:** Bağlantıdan bağımsız kayıt; idempotent uç yeniden denemeyi güvenli kılar.
- **Artı:** Protokol basit; CRDT gerektirmez çünkü kayıtlar çoğunlukla ekleme, düzenleme nadir.
- **Eksi:** Aynı kaydı iki cihaz aynı anda düzenlerse biri kaybolur. Kabul edilebilir: kayıtlar kişiseldir, düzenleme penceresi kısadır (10 sn geri al).
- **Eksi:** iOS'ta IndexedDB kotası ve arka plan kısıtları; kuyruk boyutu arayüzde her zaman görünür.

## Değerlendirilen seçenekler
- **CRDT (Yjs/Automerge):** Eş zamanlı zengin düzenleme için güçlü ama bu veri için aşırı. Reddedildi.
- **Yalnız çevrimiçi + yeniden deneme:** Stadyumda kabul edilemez. Reddedildi.

## Faz 0-1 etkisi
Faz 0-1'de uygulanmaz; yalnızca şema (`tagging_sessions`, `live_tags`: `client_id uuid unique`, `device_id`, `created_at_client`, `server_received_at`, `deleted`, `payload`) Faz 1 göçlerinde yer alır ki Faz 5'te şema kırılmasın.
