"""Mail helper utilities."""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable, Sequence

logger = logging.getLogger("cbs.mailer")

_SPLIT_RE = re.compile(r"[;,]")


def _iter_tokens(recipients: Sequence[str] | str | None) -> Iterable[str]:
    if recipients is None:
        return []
    if isinstance(recipients, str):
        return (part for part in _SPLIT_RE.split(recipients))
    return (str(value) for value in recipients)


def normalize_recipients(recipients: Sequence[str] | str | None) -> tuple[list[str], str]:
    """Normalize recipient entries for SMTP envelopes and headers."""

    seen: set[str] = set()
    kept: list[str] = []

    for raw in _iter_tokens(recipients):
        candidate = (raw or "").strip()
        if not candidate:
            continue
        normalized = candidate.lower()
        if "@" not in normalized or "." not in normalized.split("@")[-1]:
            logger.warning("[MAIL-INVALID-RECIPIENT] token=%s", candidate)
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        kept.append(candidate)

    header = ", ".join(kept)
    return kept, header
