from datetime import datetime, date, time, timezone
from zoneinfo import ZoneInfo


def now_utc() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def fmt_dt(value: datetime | date | None) -> str:
    """Format datetimes without seconds; dates use D MMM YYYY."""
    if not value:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%-d %b %Y %H:%M")
    if isinstance(value, date):
        return value.strftime("%-d %b %Y")
    return str(value)


def fmt_time(value: time | str | None) -> str:
    """Render times as HH:MM, accepting strings or time objects."""
    if not value:
        return ""
    if isinstance(value, str):
        try:
            value = time.fromisoformat(value)
        except ValueError:
            return value
    return value.strftime("%H:%M")


def fmt_time_range_with_tz(
    start: time | None, end: time | None, tz: str | None
) -> str:
    if not start or not end:
        return ""
    try:
        zone = ZoneInfo(tz) if tz else None
    except Exception:  # pragma: no cover - invalid tz
        zone = None
    today = date.today()
    start_dt = datetime.combine(today, start, tzinfo=zone)
    end_dt = datetime.combine(today, end, tzinfo=zone)
    tzname = start_dt.tzname() if zone else (tz or "")
    base = f"{start_dt.strftime('%H:%M')}–{end_dt.strftime('%H:%M')}"
    return f"{base} ({tzname})" if tzname else base
