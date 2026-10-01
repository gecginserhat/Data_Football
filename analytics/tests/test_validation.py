"""Doğrulama karşılaştırması: sentetik maçla etiket ve neden ataması (Faz 1.8)."""

import json
from pathlib import Path

from kurgu_analytics.setpieces.extract import Config
from kurgu_analytics.setpieces.validation import compare, render
from kurgu_analytics.testing.statsbomb import SBEvents


def _match(tmp_path: Path) -> Path:
    ev = SBEvents()
    # Korner → 2 sn sonra şut: iki taraf da korner der.
    ev.pass_(
        100,
        (120, 80),
        (114, 40),
        pass_type="Corner",
        height="High Pass",
        play_pattern="From Corner",
    )
    ev.shot(102, (114, 40), play_pattern="From Corner")
    # Kısa taç → şut: StatsBomb taç der, biz (uzun taç filtresi) demeyiz.
    ev.pass_(300, (70, 80), (75, 70), pass_type="Throw-in", play_pattern="From Throw In")
    ev.shot(305, (100, 40), play_pattern="From Throw In")
    # Serbest vuruş → 40 sn sonra şut: pencere dışı.
    ev.pass_(500, (40, 40), (60, 40), pass_type="Free Kick", play_pattern="From Free Kick")
    ev.pass_(530, (60, 40), (80, 40), play_pattern="From Free Kick")
    ev.shot(540, (100, 40), play_pattern="From Free Kick")
    # Akan oyun şutu; penaltı sayılmaz.
    ev.shot(700, (100, 40))
    ev.shot(800, (108, 40), shot_type="Penalty", play_pattern="Other")
    path = tmp_path / "1.json"
    path.write_text(json.dumps(ev.events))
    return path


def test_compare_labels_and_reasons(tmp_path: Path) -> None:
    c = compare([_match(tmp_path)], Config())
    assert c.total == 4
    assert c.confusion[("corner", "corner")] == 1
    assert c.confusion[("none", "throw_in")] == 1
    assert c.confusion[("none", "free_kick")] == 1
    assert c.confusion[("none", "none")] == 1
    reasons = sorted(m.reason for m in c.mismatches)
    assert reasons[0] == "kısa taç (uzun taç filtresi)"
    assert reasons[1].startswith("pencere dışı")
    assert c.agreement == 0.5
    assert c.aligned_agreement == 1.0
    assert c.precision_recall("corner") == (1.0, 1.0)


def test_all_throw_ins_setting(tmp_path: Path) -> None:
    c = compare([_match(tmp_path)], Config(all_throw_ins=True))
    assert c.confusion[("throw_in", "throw_in")] == 1


def test_render_mentions_both_measures(tmp_path: Path) -> None:
    c = compare([_match(tmp_path)], Config())
    text = render(c, c, [(20.0, c)], ["Test"])
    assert "Ham uyum" in text
    assert "Tanım farkları hariç uyum" in text
