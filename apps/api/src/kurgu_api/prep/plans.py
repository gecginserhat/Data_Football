"""MD planı şablonları (SPEC §8.1, A-52).

Gün sırası: MD-4 … MD-1, MD, MD+1 (maçın ertesi günü). Sıkışık hafta iki maçlı dönem içindir.
Kabul edilen öneri, alanına göre planın ilgili gününe madde ekler.
"""

from typing import Literal

MdCode = Literal["MD-4", "MD-3", "MD-2", "MD-1", "MD", "MD+1"]
Template = Literal["standard", "congested"]

MD_ORDER: tuple[MdCode, ...] = ("MD-4", "MD-3", "MD-2", "MD-1", "MD", "MD+1")
MD_OFFSET: dict[str, int] = {"MD-4": -4, "MD-3": -3, "MD-2": -2, "MD-1": -1, "MD": 0, "MD+1": 1}

DAYS: dict[Template, tuple[tuple[MdCode, str], ...]] = {
    "standard": (
        ("MD-4", "Kuvvet ve gerilim"),
        ("MD-3", "Dayanıklılık"),
        ("MD-2", "Hız"),
        ("MD-1", "Aktivasyon"),
        ("MD", "Maç"),
        ("MD+1", "Toparlanma"),
    ),
    "congested": (
        ("MD-2", "Toparlanma ve hız"),
        ("MD-1", "Aktivasyon"),
        ("MD", "Maç"),
        ("MD+1", "Toparlanma"),
    ),
}
"""Şablondaki günler ve günün odağı (SPEC §8.1)."""

ITEMS: dict[Template, tuple[tuple[MdCode, str, str], ...]] = {
    "standard": (
        ("MD-4", "Savunma organizasyonu", "Orta yoğunluk; bölge ve adam adama görevleri."),
        ("MD-3", "Hücum rutinleri", "Tam tekrar; her rutin iki taraftan."),
        ("MD-2", "Kısa ve keskin prova", "Maç temposunda, düşük hacim."),
        ("MD-1", "Görevlerin teyidi", "Yürüyüş temposunda üzerinden geçme."),
        ("MD", "Canlı kayıt", "Duran topları maç içinde kaydedin."),
        ("MD+1", "Maç duran top incelemesi", "Video üzerinden; saha çalışması yok."),
    ),
    "congested": (
        ("MD-2", "Savunma organizasyonu ve kısa prova", "Düşük hacim, maç temposu."),
        ("MD-1", "Rutinlerin teyidi", "Yürüyüş temposunda üzerinden geçme."),
        ("MD", "Canlı kayıt", "Duran topları maç içinde kaydedin."),
        ("MD+1", "Maç duran top incelemesi", "Video üzerinden; saha çalışması yok."),
    ),
}
"""Şablonun varsayılan maddeleri (duran top çalışması önerisi, SPEC §8.1)."""

ACCEPT_DAY: dict[Template, dict[str, MdCode]] = {
    "standard": {"attack": "MD-3", "balance": "MD-3", "season": "MD-3", "defense": "MD-4"},
    "congested": {"attack": "MD-1", "balance": "MD-1", "season": "MD-1", "defense": "MD-2"},
}
"""Kabul edilen önerinin plana gireceği gün (A-52)."""


def md_rank(code: MdCode) -> int:
    return MD_ORDER.index(code)
