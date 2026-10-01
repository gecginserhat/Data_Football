"""CSV/Excel içe aktarım: okuma, sütun eşleştirme, kalite kontrolleri (Faz 1.9)."""

import io
import zipfile

import pandas as pd
import pytest
from kurgu_analytics.ingestion.imports import (
    UnreadableFileError,
    apply_mapping,
    match_names,
    normalize,
    read_table,
    suggest_mapping,
    validate,
)
from kurgu_analytics.testing.imports import event_rows, to_csv


def _validate_csv(content: bytes, kind: str = "events"):  # type: ignore[no-untyped-def]
    frame = read_table(content, "file.csv")
    mapping = suggest_mapping(list(frame.columns), kind)  # type: ignore[arg-type]
    return validate(apply_mapping(frame, mapping), kind)  # type: ignore[arg-type]


def test_normalize_folds_turkish() -> None:
    assert normalize("  Takım Adı ") == "takim_adi"
    assert normalize("Göztepe") == "goztepe"
    assert normalize("İSTANBUL") == "istanbul"


def test_read_table_sniffs_delimiter_and_excel() -> None:
    frame = read_table("Takım;goals\nA;3\n".encode(), "x.csv")
    assert list(frame.columns) == ["Takım", "goals"]
    buf = io.BytesIO()
    pd.DataFrame({"team": ["A"], "goals": [3]}).to_excel(buf, index=False)
    assert read_table(buf.getvalue(), "x.xlsx").iloc[0].to_dict() == {"team": "A", "goals": "3"}
    with pytest.raises(UnreadableFileError):
        read_table(b"\xff\xfe\x00bad", "x.csv")


def test_read_table_rejects_disguised_and_bomb_files() -> None:
    with pytest.raises(UnreadableFileError, match="Excel dosyası değil"):
        read_table(b"team,goals\nA,3\n", "x.xlsx")
    with pytest.raises(UnreadableFileError, match="metin dosyası değil"):
        read_table(b"MZ\x90\x00\x03\x00binary", "x.csv")
    bomb = io.BytesIO()
    with zipfile.ZipFile(bomb, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/worksheets/sheet1.xml", b"0" * (101 * 1024 * 1024))
    assert len(bomb.getvalue()) < 1024 * 1024
    with pytest.raises(UnreadableFileError, match="çok büyük"):
        read_table(bomb.getvalue(), "x.xlsx")


def test_suggest_mapping_uses_aliases_and_ignores_unknown() -> None:
    mapping = suggest_mapping(["Takım", "Goals", "xG", "Notlar"], "team_season_stats")
    assert mapping == {"Takım": "team", "Goals": "goals", "xG": "xg", "Notlar": None}


def test_suggest_mapping_assigns_each_field_once() -> None:
    mapping = suggest_mapping(["x", "start_x", "y"], "events")
    assert list(mapping.values()).count("start_x") == 1


def test_match_names_prefers_short_code() -> None:
    candidates = [("1", "Göztepe", "GÖZ"), ("2", "Galatasaray", "GS")]
    result = match_names(["GS", "Goztepe A.S.", "Bilinmeyen"], candidates)
    assert result["GS"] == ("2", 1.0)
    assert result["Goztepe A.S."][0] == "1"
    assert result["Bilinmeyen"][1] < 0.85


def test_valid_events_pass() -> None:
    report, typed = _validate_csv(to_csv(event_rows()))
    assert report.critical == 0, report.to_dict()
    assert report.warnings == 0
    assert typed is not None
    assert typed["time_s"].dtype == float
    assert typed.index[0] == 2  # dosya satırı


def test_missing_required_column_is_critical() -> None:
    rows = event_rows()
    columns = tuple(c for c in rows[0] if c != "end_x")
    report, typed = _validate_csv(to_csv(rows, columns=columns))
    assert typed is None
    assert [i.check for i in report.issues] == ["required_column"]
    assert report.issues[0].column == "end_x"


def test_schema_errors_report_rows_once_per_column() -> None:
    rows = event_rows()
    rows[3]["start_x"] = "abc"
    rows[5]["start_x"] = "140"
    rows[7]["type"] = "roket"
    report, typed = _validate_csv(to_csv(rows))
    assert typed is None
    by_column = {i.column: i for i in report.issues}
    assert set(by_column) == {"start_x", "type"}
    # Tür dönüşümü başarısız olan sütunda pandera aralık kontrolünü çalıştırmaz; aralık hatası
    # düzeltilmiş dosyanın yeniden doğrulanmasında görünür.
    assert by_column["start_x"].rows == (5,)
    assert "geçersiz değer türü" in by_column["start_x"].message
    assert by_column["type"].rows == (9,)
    assert "izin verilmeyen değer" in by_column["type"].message

    rows[3]["start_x"] = "40"
    report, _ = _validate_csv(to_csv(rows))
    ranged = {i.column: i for i in report.issues}["start_x"]
    assert (ranged.rows, ranged.message) == ((7,), "start_x: aralık dışı değer")


def test_semicolon_csv_with_turkish_headers() -> None:
    rows = event_rows()
    renamed = [
        {("takim" if k == "team" else "oyuncu" if k == "player" else k): v for k, v in r.items()}
        for r in rows
    ]
    report, typed = _validate_csv(to_csv(renamed, sep=";"))
    assert report.critical == 0
    assert typed is not None
    assert "team" in typed.columns


def test_event_consistency_checks() -> None:
    rows = event_rows()
    rows[10]["team"] = "Başka Takım"
    rows[12]["home_team"] = "Kurgu FK B"
    rows[12]["team"] = "Kurgu FK B"
    rows.append(dict(rows[20]))
    report, typed = _validate_csv(to_csv(rows))
    checks = {i.check: i for i in report.issues}
    assert typed is None
    assert checks["team_reference"].rows == (12,)
    assert checks["match_consistency"].count == 1
    assert checks["duplicates"].count == 1


def test_warnings_do_not_block() -> None:
    rows = event_rows(passes=100)
    rows[50]["time_s"] = "1"
    report, typed = _validate_csv(to_csv(rows))
    assert report.critical == 0
    assert typed is not None
    assert {i.check for i in report.issues} == {"time_order", "events_per_match"}


def test_team_stats_duplicates_and_ranges() -> None:
    content = "Takım,goals,aerial_win_pct\nA,10,55\nA,11,50\nB,-1,120\n".encode()
    report, typed = _validate_csv(content, "team_season_stats")
    assert typed is None
    assert {i.column for i in report.issues} == {"goals", "aerial_win_pct"}
    fixed = "Takım,goals,aerial_win_pct\nA,10,55\nA,11,50\nB,1,20\n".encode()
    report, typed = _validate_csv(fixed, "team_season_stats")
    assert [i.check for i in report.issues] == ["duplicates"]
    assert report.issues[0].rows == (2, 3)


def test_team_stats_need_a_metric() -> None:
    report, typed = _validate_csv(b"team,notes\nA,x\n", "team_season_stats")
    assert typed is None
    assert report.issues[0].message == "en az bir metrik sütunu gerekli"
