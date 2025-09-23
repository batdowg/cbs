from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from urllib.parse import urlparse

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

PREWORK_ALLOWED_TAGS = ["p", "br", "strong", "em", "ul", "ol", "li", "a"]
PREWORK_ALLOWED_ATTRS = {"a": ["href"]}


def _clean_html(raw: str, tags: list[str], attrs: dict[str, list[str]]) -> str:
    if bleach:
        cleaner = bleach.Cleaner(
            tags=tags,
            attributes=attrs,
            protocols=["http", "https"],
            strip=True,
        )
        return cleaner.clean(raw or "")
    if not raw:
        return ""

    allowed_tags = set(tags)
    allowed_attrs = {tag: set(attrs.get(tag, [])) for tag in tags}
    void_tags = {"br"}

    def is_allowed_url(value: str) -> bool:
        if not value:
            return False
        parsed = urlparse(value)
        scheme = (parsed.scheme or "").lower()
        if scheme and scheme not in {"http", "https"}:
            return False
        if not scheme and value.startswith("//"):
            return False
        if value.lower().startswith("javascript:"):
            return False
        return True

    class _Sanitizer(HTMLParser):
        def __init__(self) -> None:
            super().__init__(convert_charrefs=True)
            self.chunks: list[str] = []
            self.block_stack: list[str] = []

        def handle_starttag(self, tag: str, attrs_list: list[tuple[str, str | None]]):
            if tag not in allowed_tags:
                self.block_stack.append(tag)
                return
            attrs_out: list[str] = []
            allowed = allowed_attrs.get(tag, set())
            for attr_name, attr_val in attrs_list:
                if attr_name not in allowed or attr_val is None:
                    continue
                if attr_name == "href" and not is_allowed_url(attr_val):
                    continue
                escaped_val = html.escape(attr_val, quote=True)
                attrs_out.append(f" {attr_name}=\"{escaped_val}\"")
            attrs_str = "".join(attrs_out)
            self.chunks.append(f"<{tag}{attrs_str}>")
            if tag not in void_tags:
                self.block_stack.append("")

        def handle_endtag(self, tag: str):
            if not self.block_stack:
                return
            if self.block_stack[-1] == "":
                self.block_stack.pop()
                if tag in allowed_tags and tag not in void_tags:
                    self.chunks.append(f"</{tag}>")
            else:
                # Pop until matching blocked tag removed
                for idx in range(len(self.block_stack) - 1, -1, -1):
                    if self.block_stack[idx] == tag:
                        del self.block_stack[idx]
                        break

        def handle_startendtag(self, tag: str, attrs_list: list[tuple[str, str | None]]):
            self.handle_starttag(tag, attrs_list)
            if not self.block_stack:
                return
            if self.block_stack[-1] == "":
                self.block_stack.pop()
            elif self.block_stack[-1] == tag:
                self.block_stack.pop()

        def handle_data(self, data: str):
            if any(tag for tag in self.block_stack if tag):
                return
            self.chunks.append(html.escape(data))

        def get_html(self) -> str:
            return "".join(self.chunks)

    sanitizer = _Sanitizer()
    sanitizer.feed(raw)
    return sanitizer.get_html()


def sanitize_html(raw: str) -> str:
    """Sanitize HTML based on a small whitelist."""

    return _clean_html(raw, ALLOWED_TAGS, ALLOWED_ATTRS)


def sanitize_prework_html(raw: str) -> str:
    """Sanitize prework question text allowing limited rich text."""

    cleaned = _clean_html(raw, PREWORK_ALLOWED_TAGS, PREWORK_ALLOWED_ATTRS)
    if not cleaned:
        return ""
    return re.sub(
        r"<a\s+href=",
        '<a target="_blank" rel="noopener" href=',
        cleaned,
        flags=re.IGNORECASE,
    )

