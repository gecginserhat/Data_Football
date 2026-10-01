"""StatsBomb → kanonik koordinat dönüşümü: referans nokta testleri (SPEC §4)."""

import pytest
from kurgu_analytics.canonical.coords import flip, statsbomb_to_canonical


@pytest.mark.parametrize(
    ("sb", "canonical"),
    [
        ((0, 0), (0, 68)),  # sol taç - kendi kale çizgisi köşesi
        ((120, 80), (105, 0)),  # hücum edilen kale, sağ köşe
        ((120, 40), (105, 34)),  # kale merkezi
        ((60, 40), (52.5, 34)),  # başlama noktası
        ((108, 40), (94, 34)),  # penaltı noktası
        ((102, 18), (88.5, 54.16)),  # ceza sahası köşesi (sol)
        ((102, 62), (88.5, 13.84)),  # ceza sahası köşesi (sağ)
        ((114, 30), (99.5, 43.16)),  # altı pas köşesi
        ((120, 36), (105, 37.66)),  # sol direk
        ((120, 44), (105, 30.34)),  # sağ direk
    ],
)
def test_reference_points(sb: tuple[float, float], canonical: tuple[float, float]) -> None:
    x, y = statsbomb_to_canonical(*sb)
    assert x == pytest.approx(canonical[0])
    assert y == pytest.approx(canonical[1])


def test_statsbomb_right_corner_is_low_y() -> None:
    # StatsBomb'da y = 80 hücum eden takımın sağıdır; kanonikte y = 0 sağ taçtır.
    _, y = statsbomb_to_canonical(119, 79)
    assert y < 1


def test_monotonic_and_clamped() -> None:
    xs = [statsbomb_to_canonical(v / 2, 40)[0] for v in range(0, 241)]
    assert xs == sorted(xs)
    assert statsbomb_to_canonical(-5, 90) == (0, 0)
    assert statsbomb_to_canonical(125, -3) == (105, 68)


def test_flip() -> None:
    assert flip(100, 10) == (5, 58)
