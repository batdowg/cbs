from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo
from typing import Any

from ..models import Session, User, ParticipantAccount
from ..constants import (
    SYS_ADMIN,
    ADMIN,
    CONTRACTOR,
    MANAGE_USERS_ROLES,
    ROLE_ATTRS,
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


def is_staff_user(user: Any) -> bool:
    if not user:
        return False
    has_any = any(getattr(user, attr, False) for attr in ROLE_ATTRS.values())
    return bool(has_any and not is_contractor(user))


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


def csa_can_manage_participants(user: Any, session: Session, now_utc: datetime) -> bool:
    return is_csa_for_session(user, session) and now_utc < session_start_dt_utc(session)


def validate_role_combo(role_names: list[str]) -> None:
    if CONTRACTOR in role_names and len(role_names) > 1:
        raise ValueError("Contractor role cannot be combined with other roles")
