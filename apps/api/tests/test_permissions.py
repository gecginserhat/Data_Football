"""SPEC §12.1 rol × izin matrisinin tablo testi (`edit_squad` satırı A-79)."""

import pytest
from kurgu_api.identity.roles import Permission, Role, permissions_for, scope_for

P, R = Permission, Role
Y, S, OWN = "all", "summary", "own"

# Sütun sırası: admin, head_coach, sp_coach, analyst, performance, medical, player, viewer
ROLE_ORDER = [
    R.ADMIN,
    R.HEAD_COACH,
    R.SP_COACH,
    R.ANALYST,
    R.PERFORMANCE,
    R.MEDICAL,
    R.PLAYER,
    R.VIEWER,
]
EXPECTED: dict[Permission, list[str | None]] = {
    P.READ_ANALYSIS:          [Y, Y, Y, Y, Y, None, None, Y],
    P.EDIT_ROUTINES:          [Y, Y, Y, Y, None, None, None, None],
    P.DECIDE_RECOMMENDATIONS: [Y, Y, Y, None, None, None, None, None],
    P.MARK_PLAN_ITEMS:        [Y, Y, Y, Y, Y, None, None, None],
    P.LIVE_TAGGING_VIDEO:     [Y, None, Y, Y, None, None, None, None],
    P.LOAD_WELLNESS:          [S, None, None, None, Y, Y, OWN, None],
    P.MEDICAL_NOTES:          [None, None, None, None, None, Y, None, None],
    P.RULE_SETTINGS:          [Y, Y, None, None, None, None, None, None],
    P.USER_ADMIN_AUDIT:       [Y, None, None, None, None, None, None, None],
    P.PLAYER_CARDS:           [Y, Y, Y, Y, None, None, OWN, None],
    P.EDIT_SQUAD:             [Y, Y, Y, None, Y, None, None, None],
}  # fmt: skip

CASES = [
    (permission, role, EXPECTED[permission][i])
    for permission in Permission
    for i, role in enumerate(ROLE_ORDER)
]


@pytest.mark.parametrize(("permission", "role", "expected"), CASES)
def test_matrix(permission: Permission, role: Role, expected: str | None) -> None:
    assert scope_for(frozenset({role}), permission) == expected


def test_every_permission_is_covered() -> None:
    assert set(EXPECTED) == set(Permission)


def test_widest_scope_wins_when_roles_combine() -> None:
    assert scope_for(frozenset({R.ADMIN, R.PERFORMANCE}), P.LOAD_WELLNESS) == "all"
    assert permissions_for(frozenset({R.PLAYER}))[P.PLAYER_CARDS] == "own"
