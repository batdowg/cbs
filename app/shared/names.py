"""Name utilities for CBS."""

from __future__ import annotations

import re
from typing import Iterable, Optional, Tuple

_PARENTHESES_RE = re.compile(r"\s*\([^)]*\)")


def strip_parenthetical(value: str) -> str:
    """Remove parenthetical segments like ``"Jane Doe (Learner)"`` → ``"Jane Doe"``."""

    return _PARENTHESES_RE.sub("", value).strip()


def split_full_name(full_name: str) -> Tuple[Optional[str], Optional[str]]:
    """Split a full name into first/last components.

    Parenthetical suffixes are ignored and the last token is treated as the last name.
    Single-token names become the first name only.
    """

    cleaned = strip_parenthetical(full_name or "").strip()
    if not cleaned:
        return None, None
    parts = cleaned.split()
    if len(parts) == 1:
        return parts[0], None
    first = " ".join(parts[:-1]).strip()
    last = parts[-1].strip()
    return (first or None, last or None)


def combine_first_last(first: Optional[str], last: Optional[str]) -> str:
    """Join first/last names with a space, omitting blanks."""

    segments: Iterable[str] = (
        segment.strip()
        for segment in (first or "", last or "")
        if segment and segment.strip()
    )
    return " ".join(segments).strip()


def greeting_name(
    participant=None,
    account=None,
    user=None,
) -> str:
    """Return the preferred greeting name for emails."""

    # Participant takes priority when available.
    if participant is not None:
        first = getattr(participant, "first_name", None)
        if first and first.strip():
            return first.strip()
        display = getattr(participant, "display_name", None)
        if display and display.strip():
            return display.strip()
    # Fall back to a linked user or account record.
    if user is not None:
        first = getattr(user, "first_name", None)
        if first and first.strip():
            return first.strip()
        display = getattr(user, "display_name", None)
        if display and display.strip():
            return display.strip()
    if account is not None:
        for attr in ("full_name", "certificate_name"):
            value = getattr(account, attr, None)
            if value and value.strip():
                return value.strip()
        email = getattr(account, "email", None)
        if email:
            return email.strip()
    return ""
