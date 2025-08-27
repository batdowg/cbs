from __future__ import annotations


def slug_for_badge(name: str) -> str:
    return (name or "").replace(" ", "").lower()


def badge_candidates(name: str) -> list[str]:
    slug = slug_for_badge(name)
    return [f"/badges/{slug}.webp", f"/badges/{slug}.png"]
