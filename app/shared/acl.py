from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo
from typing import Any

from ..models import Session, User, ParticipantAccount
from .constants import (
    SYS_ADMIN,
    ADMIN,
    CONTRACTOR,
    MANAGE_USERS_ROLES,
)


def is_sys_admin(user: Any) -> bool:
    return bool(user and user.has_role(SYS_ADMIN))


def is_admin(user: Any) -> bool:
    return bool(user and (user.has_role(ADMIN) or is_sys_admin(user)))


def can_manage_users(user: Any) -> bool:
    return bool(user and any(user.has_role(r) for r in MANAGE_USERS_ROLES))


def is_kcrm(user: Any) -> bool:
    return bool(user and getattr(user, "is_kcrm", False))


def is_delivery(user: Any) -> bool:
    return bool(user and getattr(user, "is_kt_delivery", False))


def is_contractor(user: Any) -> bool:
    return bool(user and user.has_role(CONTRACTOR))


def is_kt_staff(user: Any) -> bool:
    """Return True when the account should be treated as KT Staff."""

    if not user:
        return False

    if isinstance(user, ParticipantAccount):
        return False

    if not isinstance(user, User):
        return False

    positive_flags = (
        "is_app_admin",
        "is_admin",
        "is_kt_admin",
        "is_kcrm",
        "is_kt_delivery",
        "is_kt_staff",
    )
    if any(getattr(user, flag, False) for flag in positive_flags):
        return True

    if getattr(user, "is_kt_contractor", False):
        return False

    if hasattr(user, "has_role") and user.has_role(CONTRACTOR):
        return False

    return True


def can_demote_to_contractor(actor: User, target: User) -> bool:
    if not can_manage_users(actor):
        return False
    if is_sys_admin(target):
        return False
    if getattr(actor, "id", None) == getattr(target, "id", None):
        return False
    return True


def is_participant(user: Any) -> bool:
    return isinstance(user, ParticipantAccount)


def is_csa_for_session(user: Any, session: Session) -> bool:
    return bool(user and getattr(user, "id", None) == getattr(session, "csa_account_id", None))


def session_start_dt_utc(session: Session) -> datetime:
    start_date = session.start_date
    start_time = session.daily_start_time or time(0, 0)
    if start_date is None:
        dt = datetime.utcnow()
    else:
        dt = datetime.combine(start_date, start_time)
    tz_name = getattr(session, "timezone", None) or "UTC"
    try:
        tz = ZoneInfo(tz_name)
    except Exception:  # pragma: no cover - invalid timezone fallback
        tz = ZoneInfo("UTC")
    dt = dt.replace(tzinfo=tz)
    return dt.astimezone(ZoneInfo("UTC"))


def csa_can_manage_participants(user: Any, session: Session) -> bool:
    """CSA may manage participants until session is marked Ready for Delivery."""
    return is_csa_for_session(user, session) and not getattr(session, "ready_for_delivery", False)


def validate_role_combo(role_names: list[str]) -> None:
    if CONTRACTOR in role_names and len(role_names) > 1:
        raise ValueError("Contractor role cannot be combined with other roles")
