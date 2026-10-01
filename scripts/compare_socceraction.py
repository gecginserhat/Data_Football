"""Kurgu StatsBomb→SPADL eşleyicisini socceraction 1.5 ile karşılaştırır (assumptions A-16).

socceraction proje bağımlılığı değildir (numpy<2, pandera<0.18 sabitler). Betik ayrı, geçici
bir ortamda çalışır: `make spadl-compare` (çıktı `docs/validation/spadl_socceraction.md`).

Karşılaştırma olay kimliği üzerinden yapılır: aynı StatsBomb olayından gelen aksiyonların
türü, sonucu ve vücut bölgesi (socceraction'ın sol/sağ ayak ayrımı olmadan) eşleşiyor mu.
"""

import json
import sys
import warnings
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analytics"))
warnings.filterwarnings("ignore")

from kurgu_analytics.ingestion.statsbomb import events_to_actions  # noqa: E402
from socceraction.data.statsbomb import StatsBombLoader  # noqa: E402
from socceraction.spadl import config as spadl_config  # noqa: E402
from socceraction.spadl import statsbomb as sb_spadl  # noqa: E402

TYPES = spadl_config.actiontypes
RESULTS = spadl_config.results
BODYPARTS = spadl_config.bodyparts


def _body(value: str) -> str:
    return "foot" if value.startswith("foot") else value


def main() -> None:
    root = Path(sys.argv[1])
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    loader = StatsBombLoader(getter="local", root=str(root))
    matches = []
    for comp_dir in sorted((root / "matches").iterdir()):
        for season_file in sorted(comp_dir.iterdir()):
            matches += json.loads(season_file.read_text())[: max(1, limit // 3)]
    matches = matches[:limit]

    ours_total = theirs_total = matched = same_type = same_all = 0
    confusion: Counter[tuple[str, str]] = Counter()
    for m in matches:
        mid = m["match_id"]
        events_df = loader.events(mid)
        theirs = sb_spadl.convert_to_actions(events_df, m["home_team"]["home_team_id"])
        theirs = theirs[theirs["original_event_id"].notna()]
        by_event = {
            row.original_event_id: (
                TYPES[row.type_id],
                RESULTS[row.result_id],
                _body(BODYPARTS[row.bodypart_id]),
            )
            for row in theirs.itertuples()
            if TYPES[row.type_id] != "non_action"
        }
        raw = json.loads((root / "events" / f"{mid}.json").read_text())
        ours = {
            a.provider_event_id: (a.type, a.result, _body(a.bodypart))
            for a in events_to_actions(raw)
        }
        ours_total += len(ours)
        theirs_total += len(by_event)
        for eid, ours_value in ours.items():
            theirs_value = by_event.get(eid)
            if theirs_value is None:
                confusion[(ours_value[0], "(yok)")] += 1
                continue
            matched += 1
            same_type += ours_value[0] == theirs_value[0]
            same_all += ours_value == theirs_value
            if ours_value[0] != theirs_value[0]:
                confusion[(ours_value[0], theirs_value[0])] += 1
        for eid, theirs_value in by_event.items():
            if eid not in ours:
                confusion[("(yok)", theirs_value[0])] += 1

    print("# SPADL eşleyici uyumu: Kurgu ve socceraction 1.5.3\n")
    print(
        f"{len(matches)} StatsBomb Open Data maçı, olay kimliğiyle eşleştirme. "
        "Bu dosya `scripts/compare_socceraction.py` ile üretilir.\n"
    )
    print("| Ölçü | Değer |\n|---|---:|")
    print(f"| Kurgu aksiyonu | {ours_total} |")
    print(f"| socceraction aksiyonu (sentetik dribble hariç) | {theirs_total} |")
    print(f"| Ortak olay | {matched} |")
    print(f"| Tür uyumu | %{100 * same_type / matched:.2f} |")
    print(f"| Tür + sonuç + vücut bölgesi uyumu | %{100 * same_all / matched:.2f} |")
    print("\n## En sık farklar (Kurgu → socceraction)\n")
    print("| Kurgu | socceraction | Adet |\n|---|---|---:|")
    for (a, b), n in confusion.most_common(15):
        print(f"| {a} | {b} | {n} |")
    print("\nData: StatsBomb Open Data (https://github.com/statsbomb/open-data).")


if __name__ == "__main__":
    main()
