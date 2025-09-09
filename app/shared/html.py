from __future__ import annotations

try:  # pragma: no cover - optional dependency
    import bleach
except ModuleNotFoundError:  # pragma: no cover - runtime fallback
    bleach = None


ALLOWED_TAGS = [
    "p",
    "br",
    "strong",
    "em",
    "u",
    "ul",
    "ol",
    "li",
    "a",
    "h3",
    "h4",
    "blockquote",
]

ALLOWED_ATTRS = {"a": ["href", "rel"]}


def sanitize_html(raw: str) -> str:
    """Sanitize HTML based on a small whitelist."""

    if bleach:
        return bleach.clean(
            raw or "",
            tags=ALLOWED_TAGS,
            attributes=ALLOWED_ATTRS,
            protocols=["http", "https"],
            strip=True,
        )
    return raw or ""

