"""Kişisel veri envanteri (SPEC §12.3, ADR-0019, A-92).

Envanterin tek kaynağı budur: `/admin/privacy` ekranı ve döküm buradan üretilir. Bir test,
kullanıcıya ya da kadro oyuncusuna bağlanan her tablonun burada yer aldığını denetler.
Hukuki dayanak ve süreler kulübün hukuk ekibince teyit edilmelidir (`docs/compliance.md`).
"""

from dataclasses import dataclass
from typing import Literal

RetentionKey = Literal["wellness_days", "loads_days", "audit_days"]


@dataclass(frozen=True)
class InventoryItem:
    key: str
    title: str
    tables: tuple[str, ...]
    fields: tuple[str, ...]
    subjects: str
    purpose: str
    legal_basis: str
    special_category: bool
    encrypted: bool
    retention: str
    retention_key: RetentionKey | None = None


INVENTORY: tuple[InventoryItem, ...] = (
    InventoryItem(
        key="accounts",
        title="Kullanıcı hesapları ve üyelikler",
        tables=("users", "memberships"),
        fields=("e-posta", "görünen ad", "kimlik sağlayıcı kimliği", "kulüp rolü"),
        subjects="Kulüp çalışanları ve oyuncular",
        purpose="Kimlik doğrulama ve yetkilendirme",
        legal_basis="Sözleşmenin ifası (KVKK m.5/2-c)",
        special_category=False,
        encrypted=False,
        retention="Üyelik sürdükçe; üyelik kaldırılınca hesap pasifleşir",
    ),
    InventoryItem(
        key="invites",
        title="Üyelik davetleri",
        tables=("membership_invites",),
        fields=("e-posta", "davet edilen roller", "daveti veren"),
        subjects="Kulübe davet edilen kişiler",
        purpose="Kişinin ilk girişte kulübe doğru rollerle katılması",
        legal_basis="Sözleşmenin ifası (KVKK m.5/2-c)",
        special_category=False,
        encrypted=False,
        retention=(
            "En çok 14 gün bekler; kabul, geri çekme ya da süre dolumundan 30 gün sonra silinir"
        ),
    ),
    InventoryItem(
        key="squad",
        title="Kadro kaydı",
        tables=("squad_players",),
        fields=("ad", "forma numarası", "mevki", "boy", "hava topu oranı", "sıçrama skoru"),
        subjects="Kulübün oyuncuları",
        purpose="Duran top planlaması, markaj ve rol atamaları",
        legal_basis="Sözleşmenin ifası (KVKK m.5/2-c), meşru menfaat (m.5/2-f)",
        special_category=False,
        encrypted=False,
        retention="Oyuncu kadroda kaldıkça; silme talebiyle anonimleştirilir",
    ),
    InventoryItem(
        key="loads",
        title="Antrenman yükü",
        tables=("training_sessions", "session_loads"),
        fields=("RPE", "süre", "kafa vuruşu", "sıçrama sayısı"),
        subjects="Kulübün oyuncuları",
        purpose="Yük yönetimi ve sakatlık riskinin izlenmesi",
        legal_basis="Meşru menfaat (KVKK m.5/2-f)",
        special_category=False,
        encrypted=False,
        retention="Kiracı ayarı (varsayılan 1095 gün)",
        retention_key="loads_days",
    ),
    InventoryItem(
        key="wellness",
        title="İyi oluş (Hooper)",
        tables=("wellness_entries",),
        fields=("uyku", "stres", "yorgunluk", "kas ağrısı"),
        subjects="Kulübün oyuncuları",
        purpose="Toparlanma ve iyi oluşun izlenmesi",
        legal_basis="Açık rıza (KVKK m.6/2)",
        special_category=True,
        encrypted=True,
        retention="Kiracı ayarı (varsayılan 730 gün)",
        retention_key="wellness_days",
    ),
    InventoryItem(
        key="consents",
        title="Açık rıza kayıtları",
        tables=("health_consents",),
        fields=("metin sürümü", "yöntem", "belge referansı", "veriliş ve geri çekilme zamanı"),
        subjects="Kulübün oyuncuları",
        purpose="Açık rızanın ispatı",
        legal_basis="Hukuki yükümlülük (KVKK m.5/2-ç)",
        special_category=False,
        encrypted=False,
        retention="Silme talebine kadar",
    ),
    InventoryItem(
        key="requests",
        title="Veri sahibi talepleri",
        tables=("privacy_requests",),
        fields=("talep türü", "gerekçe", "karar"),
        subjects="Kulübün oyuncuları",
        purpose="KVKK m.11 başvurularının yürütülmesi",
        legal_basis="Hukuki yükümlülük (KVKK m.5/2-ç)",
        special_category=False,
        encrypted=False,
        retention="Talep kaydı silinmez; oyuncu anonimleştirilir",
    ),
    InventoryItem(
        key="assignments",
        title="Görev ve markaj atamaları",
        tables=("routine_assignments", "marking_plans"),
        fields=("rutin rolü", "markaj eşleşmesi"),
        subjects="Kulübün oyuncuları",
        purpose="Maç hazırlığı",
        legal_basis="Meşru menfaat (KVKK m.5/2-f)",
        special_category=False,
        encrypted=False,
        retention="Fikstür kaydıyla birlikte; silme talebinde rol atamaları silinir",
    ),
    InventoryItem(
        key="opponents",
        title="Rakip hedef oyuncular",
        tables=("opponent_targets",),
        fields=("ad", "forma numarası", "boy", "hava topu oranı", "duran top golü"),
        subjects="Rakip takımların oyuncuları",
        purpose="Rakip analizi",
        legal_basis="Meşru menfaat (KVKK m.5/2-f); alenileştirilmiş veri (m.5/2-d)",
        special_category=False,
        encrypted=False,
        retention="Kulüp siler",
    ),
    InventoryItem(
        key="league",
        title="Lig oyuncuları",
        tables=("players",),
        fields=("ad", "sağlayıcı kimliği"),
        subjects="Lig oyuncuları",
        purpose="Lig ve rakip analizi",
        legal_basis="Lisanslı sağlayıcı verisi; alenileştirilmiş veri (KVKK m.5/2-d)",
        special_category=False,
        encrypted=False,
        retention="Sağlayıcı lisansı süresince",
    ),
    InventoryItem(
        key="video",
        title="Maç ve antrenman videoları",
        tables=("video_assets", "video_clips"),
        fields=("görüntü",),
        subjects="Oyuncular ve görüntüdeki diğer kişiler",
        purpose="Video analizi",
        legal_basis="Meşru menfaat (KVKK m.5/2-f)",
        special_category=False,
        encrypted=False,
        retention="Kulüp siler",
    ),
    InventoryItem(
        key="audit",
        title="Denetim kaydı",
        tables=("audit_log",),
        fields=("işlemi yapan kullanıcı", "işlem", "önceki ve sonraki değer", "IP adresi"),
        subjects="Kulüp çalışanları ve oyuncular",
        purpose="Güvenlik ve hesap verebilirlik",
        legal_basis="Hukuki yükümlülük (KVKK m.12)",
        special_category=False,
        encrypted=False,
        retention="Kiracı ayarı (varsayılan 730 gün)",
        retention_key="audit_days",
    ),
    InventoryItem(
        key="work-records",
        title="İş kayıtlarında kullanıcı kimliği",
        tables=(
            "fixture_plans",
            "plan_items",
            "recommendations",
            "routines",
            "routine_versions",
            "rule_sets",
            "reports",
            "llm_runs",
            "imports",
            "ingestion_runs",
            "provider_id_map",
            "tagging_sessions",
        ),
        fields=("oluşturan, karar veren ya da sorumlu kullanıcı",),
        subjects="Kulüp çalışanları",
        purpose="İş akışının izlenebilirliği",
        legal_basis="Meşru menfaat (KVKK m.5/2-f)",
        special_category=False,
        encrypted=False,
        retention="Kayıtla birlikte",
    ),
)


def covered_tables() -> set[str]:
    return {table for item in INVENTORY for table in item.tables}
