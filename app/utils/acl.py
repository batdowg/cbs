from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo
from typing import Any

from ..models import Session, User, ParticipantAccount


def is_admin(user: Any) -> bool:
    return bool(user and (getattr(user, "is_app_admin", False) or getattr(user, "is_admin", False)))


def is_kcrm(user: Any) -> bool:
    return bool(user and getattr(user, "is_kcrm", False))


def is_delivery(user: Any) -> bool:
    return bool(user and getattr(user, "is_kt_delivery", False))


def is_contractor(user: Any) -> bool:
    return bool(user and getattr(user, "is_kt_contractor", False))


def is_staff(user: Any) -> bool:
    return bool(
        user
        and (
            is_admin(user)
            or is_kcrm(user)
            or is_delivery(user)
            or is_contractor(user)
            or getattr(user, "is_kt_staff", False)
        )
    )


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
