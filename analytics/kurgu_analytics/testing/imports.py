"""İçe aktarım testleri için sentetik CSV üreticileri (gerçek veri değildir)."""

from __future__ import annotations

import csv
import io

EVENT_COLUMNS = (
    "match_ref",
    "match_date",
    "home_team",
    "away_team",
    "period",
    "time_s",
    "team",
    "player",
    "type",
    "result",
    "bodypart",
    "start_x",
    "start_y",
    "end_x",
    "end_y",
    "xg",
)


def event_rows(
    match_ref: str = "M1",
    home: str = "Kurgu FK",
    away: str = "Rakip SK",
    date: str = "2025-08-10",
    passes: int = 320,
) -> list[dict[str, str]]:
    """Bir maç: `passes` pas, ardından ev sahibinin kafa golüyle biten bir korner."""
    base = {"match_ref": match_ref, "match_date": date, "home_team": home, "away_team": away}
    rows = [
        base
        | {
            "period": "1",
            "time_s": str(i * 5),
            "team": home if i % 2 == 0 else away,
            "player": f"Oyuncu {i % 11 + 1}",
            "type": "pass",
            "result": "success",
            "bodypart": "foot",
            "start_x": "40",
            "start_y": "30",
            "end_x": "55",
            "end_y": "32",
            "xg": "",
        }
        for i in range(passes)
    ]
    t = passes * 5 + 10
    rows.append(
        base
        | {
            "period": "1",
            "time_s": str(t),
            "team": home,
            "player": "Oyuncu 7",
            "type": "corner_crossed",
            "result": "success",
            "bodypart": "foot_right",
            "start_x": "105",
            "start_y": "0",
            "end_x": "99",
            "end_y": "37",
            "xg": "",
        }
    )
    rows.append(
        base
        | {
            "period": "1",
            "time_s": str(t + 2),
            "team": home,
            "player": "Oyuncu 9",
            "type": "shot",
            "result": "success",
            "bodypart": "head",
            "start_x": "99",
            "start_y": "37",
            "end_x": "105",
            "end_y": "34",
            "xg": "0.35",
        }
    )
    return rows


def to_csv(rows: list[dict[str, str]], sep: str = ",", columns: tuple[str, ...] = ()) -> bytes:
    fieldnames = list(columns or rows[0].keys())
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=fieldnames, delimiter=sep, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue().encode()
