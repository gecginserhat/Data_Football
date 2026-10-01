"""Roller ve izin matrisi (SPEC §12.1). Matris yalnızca burada tanımlanır."""

from enum import StrEnum
from typing import Literal


class Role(StrEnum):
    ADMIN = "admin"
    HEAD_COACH = "head_coach"
    SP_COACH = "sp_coach"
    ANALYST = "analyst"
    PERFORMANCE = "performance"
    MEDICAL = "medical"
    PLAYER = "player"
    VIEWER = "viewer"


class Permission(StrEnum):
    READ_ANALYSIS = "read_analysis"
    EDIT_ROUTINES = "edit_routines"
    DECIDE_RECOMMENDATIONS = "decide_recommendations"
    MARK_PLAN_ITEMS = "mark_plan_items"
    LIVE_TAGGING_VIDEO = "live_tagging_video"
    LOAD_WELLNESS = "load_wellness"
    MEDICAL_NOTES = "medical_notes"
    RULE_SETTINGS = "rule_settings"
    USER_ADMIN_AUDIT = "user_admin_audit"
    PLAYER_CARDS = "player_cards"


Scope = Literal["all", "summary", "own"]
"""`all`: tam erişim; `summary`: yalnızca özet (admin, yük verisi); `own`: yalnızca kendi kaydı."""

R = Role
PERMISSION_MATRIX: dict[Permission, dict[Role, Scope]] = {
    Permission.READ_ANALYSIS: {
        r: "all" for r in (R.ADMIN, R.HEAD_COACH, R.SP_COACH, R.ANALYST, R.PERFORMANCE, R.VIEWER)
    },
    Permission.EDIT_ROUTINES: {r: "all" for r in (R.ADMIN, R.HEAD_COACH, R.SP_COACH, R.ANALYST)},
    Permission.DECIDE_RECOMMENDATIONS: {r: "all" for r in (R.ADMIN, R.HEAD_COACH, R.SP_COACH)},
    Permission.MARK_PLAN_ITEMS: {
        r: "all" for r in (R.ADMIN, R.HEAD_COACH, R.SP_COACH, R.ANALYST, R.PERFORMANCE)
    },
    Permission.LIVE_TAGGING_VIDEO: {r: "all" for r in (R.ADMIN, R.SP_COACH, R.ANALYST)},
    Permission.LOAD_WELLNESS: {
        R.ADMIN: "summary",
        R.PERFORMANCE: "all",
        R.MEDICAL: "all",
        R.PLAYER: "own",
    },
    Permission.MEDICAL_NOTES: {R.MEDICAL: "all"},
    Permission.RULE_SETTINGS: {R.ADMIN: "all", R.HEAD_COACH: "all"},
    Permission.USER_ADMIN_AUDIT: {R.ADMIN: "all"},
    Permission.PLAYER_CARDS: {
        R.ADMIN: "all",
        R.HEAD_COACH: "all",
        R.SP_COACH: "all",
        R.ANALYST: "all",
        R.PLAYER: "own",
    },
}

MFA_REQUIRED_ROLES: frozenset[Role] = frozenset({R.ADMIN, R.MEDICAL, R.PERFORMANCE})

_SCOPE_RANK: dict[Scope, int] = {"own": 0, "summary": 1, "all": 2}


def scope_for(roles: frozenset[Role], permission: Permission) -> Scope | None:
    """Rollerin bir izin için sağladığı en geniş kapsamı döner; izin yoksa `None`."""
    grants = PERMISSION_MATRIX[permission]
    scopes = [grants[r] for r in roles if r in grants]
    if not scopes:
        return None
    return max(scopes, key=_SCOPE_RANK.__getitem__)


def permissions_for(roles: frozenset[Role]) -> dict[Permission, Scope]:
    result: dict[Permission, Scope] = {}
    for permission in Permission:
        scope = scope_for(roles, permission)
        if scope is not None:
            result[permission] = scope
    return result
