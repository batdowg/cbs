from __future__ import annotations


def normalize_email(s: str) -> str:
    """Normalize an email by stripping whitespace and lowercasing."""
    return (s or "").strip().lower()
