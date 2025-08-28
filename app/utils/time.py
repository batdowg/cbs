from datetime import datetime, date, time, timezone


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
