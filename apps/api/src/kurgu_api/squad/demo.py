"""Geliştirme kiracısı için örnek kadro, seans yükleri ve iyi oluş kayıtları (A-79).

Yalnız `kurgu-dev-identities` çağırır (geliştirme ve test). Oyuncular ve seanslar `is_demo` ile
işaretlenir; arayüz "Örnek veri" rozeti gösterir. Kiracıda kadro varsa hiçbir şey yapılmaz.
Değerler sabit tohumlu rastgele sayılardır; gerçek bir oyuncuyu temsil etmez.
"""

import datetime as dt
import json
import random
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from kurgu_api.core.crypto import encrypt
from kurgu_api.performance.service import WELLNESS_FIELD, WELLNESS_TABLE, today
from kurgu_api.privacy.consent import CONSENT_VERSION

# (forma, mevki, boy cm, hava topu oranı, sıçrama skoru)
DEMO_SQUAD: list[tuple[int, str, int, float | None, float | None]] = [
    (1, "GK", 192, None, None),
    (12, "GK", 189, None, None),
    (3, "DEF", 191, 0.66, 0.70),
    (4, "DEF", 188, 0.61, 0.62),
    (5, "DEF", 185, 0.55, 0.58),
    (2, "DEF", 178, 0.44, 0.50),
    (15, "DEF", 186, 0.58, None),
    (22, "DEF", 180, None, 0.55),
    (6, "MID", 184, 0.52, 0.52),
    (8, "MID", 176, 0.38, 0.45),
    (10, "MID", 174, 0.30, 0.40),
    (16, "MID", 181, 0.47, None),
    (14, "MID", 178, None, None),
    (9, "FWD", 189, 0.57, 0.66),
    (11, "FWD", 175, 0.35, 0.48),
    (7, "FWD", 172, 0.33, None),
]
PLAYER_SHIRT = 4
"""Geliştirme `player` kullanıcısının bağlandığı kayıt."""
SPIKE_SHIRT = 4
"""Bu haftası sıçrama uyarısı üretecek kayıt."""
DAYS = 42
MD_BY_WEEKDAY = {0: "MD+1", 1: "MD-4", 2: "MD-3", 3: "MD-2", 4: "MD-1", 5: "MD"}


async def seed_demo_squad(conn: AsyncConnection, tenant_id: uuid.UUID) -> bool:
    """Örnek kadroyu ve son 6 haftanın kayıtlarını ekler. Eklediyse `True`."""
    existing: int = (
        await conn.execute(
            text("select count(*) from squad_players where tenant_id = :t"), {"t": tenant_id}
        )
    ).scalar_one()
    if existing:
        return False
    rng = random.Random(20261001)  # noqa: S311 (örnek veri, güvenlik amaçlı değil)
    players: dict[int, uuid.UUID] = {}
    for shirt, position, height, aerial, jump in DEMO_SQUAD:
        players[shirt] = (
            await conn.execute(
                text(
                    "insert into squad_players (tenant_id, name, shirt_number, position, height_cm,"
                    " aerial_win_pct, jump_score, is_demo) values (:t, :name, :shirt, :pos, :h,"
                    " :a, :j, true) returning id"
                ),
                {
                    "t": tenant_id,
                    "name": f"Örnek oyuncu {shirt}",
                    "shirt": shirt,
                    "pos": position,
                    "h": height,
                    "a": aerial,
                    "j": jump,
                },
            )
        ).scalar_one()
    await conn.execute(
        text(
            "update memberships set player_id = :p where tenant_id = :t and role = 'player'"
            " and player_id is null"
        ),
        {"p": players[PLAYER_SHIRT], "t": tenant_id},
    )

    end = today()
    for offset in range(DAYS - 1, -1, -1):
        day = end - dt.timedelta(days=offset)
        if day.weekday() == 6 and day != end:
            continue
        md = MD_BY_WEEKDAY.get(day.weekday())
        session_id: uuid.UUID = (
            await conn.execute(
                text(
                    "insert into training_sessions (tenant_id, date, md_code, title, is_demo)"
                    " values (:t, :d, :md, :title, true) returning id"
                ),
                {
                    "t": tenant_id,
                    "d": day,
                    "md": md,
                    "title": "Örnek seans" if md != "MD" else "Örnek maç",
                },
            )
        ).scalar_one()
        for shirt, position, *_ in DEMO_SQUAD:
            rpe = rng.choice([3, 4, 4.5, 5, 6, 6.5, 7, 8]) if md != "MD+1" else rng.choice([2, 3])
            minutes = 90 if md == "MD" else rng.choice([45, 60, 70, 75, 80])
            heading = position in {"DEF", "FWD"}
            jumps = (
                0 if position == "GK" else rng.randint(12, 20) if heading else rng.randint(6, 12)
            )
            headers = (
                0 if position == "GK" else rng.randint(6, 12) if heading else rng.randint(1, 5)
            )
            if shirt == SPIKE_SHIRT and day == end:
                jumps += 250
            await conn.execute(
                text(
                    "insert into session_loads (tenant_id, session_id, squad_player_id, rpe,"
                    " minutes, headers, jumps) values (:t, :s, :p, :rpe, :m, :h, :j)"
                ),
                {
                    "t": tenant_id,
                    "s": session_id,
                    "p": players[shirt],
                    "rpe": rpe,
                    "m": minutes,
                    "h": headers,
                    "j": jumps,
                },
            )
        for shirt, *_ in DEMO_SQUAD:
            scores = {k: rng.randint(2, 5) for k in ("sleep", "stress", "fatigue", "soreness")}
            envelope = encrypt(
                scores, tenant_id=tenant_id, table=WELLNESS_TABLE, field=WELLNESS_FIELD
            )
            await conn.execute(
                text(
                    "insert into wellness_entries (tenant_id, squad_player_id, date, scores)"
                    " values (:t, :p, :d, cast(:s as jsonb))"
                ),
                {"t": tenant_id, "p": players[shirt], "d": day, "s": json.dumps(envelope)},
            )
    return True


async def seed_demo_consents(conn: AsyncConnection, tenant_id: uuid.UUID) -> int:
    """Örnek oyuncular için örnek kâğıt rıza (A-92); rızası olmayanlara eklenir. İdempotenttir."""
    result = await conn.execute(
        text(
            "insert into health_consents (tenant_id, squad_player_id, text_version, method,"
            " reference, is_demo) select :t, p.id, :v, 'paper', 'Örnek veri', true"
            " from squad_players p where p.tenant_id = :t and p.is_demo and p.erased_at is null"
            " and not exists (select 1 from health_consents c where c.squad_player_id = p.id)"
        ),
        {"t": tenant_id, "v": CONSENT_VERSION},
    )
    return int(getattr(result, "rowcount", 0) or 0)
