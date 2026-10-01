"""Brifing sayı eşleştirmesi (SPEC §15, A-74)."""

from hypothesis import given
from hypothesis import strategies as st
from kurgu_analytics.recs.evaluate import format_value
from kurgu_analytics.reports.numbers import allowed_keys, extract, verify

INPUT = {
    "fixture": {"week": 7, "date": "10.10.2026", "kickoff": "20:00", "season": "2025/26"},
    "opponent": {
        "id": "941f84fe-4a51-4f3b-a27a-e0e2cf173442",
        "metrics": [
            {"metric": "fouls_committed_per_match", "value": 14.82, "display": "14,82", "rank": 4},
            {"metric": "corners_per_match", "value": 6.4, "display": "6,40", "rank": 2},
            {"metric": "set_piece_goal_share", "value": 0.20431, "display": "%20,4", "rank": 9},
            {"metric": "set_piece_goals", "value": 15, "display": "15", "rank": 1, "teams": 18},
        ],
    },
    "notes": "Rakip 1.234 dakika oynadı; xG 15,4.",
}


def texts(text: str) -> list[str]:
    return [t.text for t in extract(text)]


def test_extracts_turkish_formats() -> None:
    assert texts("Pay %20,4, korner 6,40; 4. sırada, 7. hafta.") == ["20,4", "6,40", "4", "7"]
    assert texts("10.10.2026 saat 20:00") == ["10.10.2026", "20:00"]
    assert texts("1.234 dakika, 20,4% pay") == ["1.234", "20,4"]


def test_signs_and_ranges() -> None:
    assert texts("Gol eksi xG -2,8; 3-4 kişi") == ["2,8", "3", "4"]
    assert texts("−1,5 ve +2") == ["1,5", "2"]


def test_words_with_digits_are_not_numbers() -> None:
    assert texts("C6 bölgesi ve xG2 etiketi") == []


def test_numbers_from_input_pass() -> None:
    text = (
        "7. hafta 10.10.2026 20:00 maçında rakip maç başına 14,82 faul yapıyor (4.) ve "
        "maç başına 6,40 kornerle 2. sırada. Duran top payı %20,4; 15 golle 18 takım "
        "içinde 1. 2025/26 sezonunda xG 15,4."
    )
    result = verify(text, INPUT)
    assert result.ok, result.unmatched


def test_fabricated_number_is_rejected() -> None:
    result = verify("Rakip maç başına 7,1 korner kullanıyor.", INPUT)
    assert not result.ok
    assert result.unmatched == ("7,1",)


def test_rounding_is_not_free() -> None:
    assert not verify("xG 15 civarında.", {"xg": 15.4}).ok
    assert verify("xG 15,4.", {"xg": 15.4}).ok


def test_ratio_accepts_percent_form() -> None:
    assert verify("Kazanma oranı %25.", {"rate": 0.25}).ok
    assert verify("Kazanma oranı 0,25.", {"rate": 0.25}).ok


def test_ids_and_uuid_strings_do_not_widen_the_set() -> None:
    keys = allowed_keys(INPUT)
    assert "941" not in keys
    assert not verify("941 kez", INPUT).ok
    assert not verify("3 kez", {"id": 3, "ref": "aaaaaaaa-bbbb-4ccc-8ddd-333333333333"}).ok


def test_ambiguous_dot_tries_both_readings() -> None:
    assert verify("1.234 dakika", INPUT).ok
    assert verify("Değer 15.4", {"xg": 15.4}).ok


def test_dates_must_match_whole() -> None:
    assert not verify("11.10.2026 tarihinde", INPUT).ok
    assert verify("10.10.2026 tarihinde", INPUT).ok


def test_booleans_and_nulls_are_ignored() -> None:
    assert not verify("1 kez", {"low_sample": True, "x": None}).ok


@given(st.floats(min_value=0, max_value=10_000, allow_nan=False), st.sampled_from(["dec1", "int"]))
def test_formatted_values_match_their_source(value: float, fmt: str) -> None:
    display = format_value(value, fmt)
    assert verify(f"Değer {display}.", {"value": value, "display": display}).ok
