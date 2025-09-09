from __future__ import annotations

from typing import List, Tuple

# Mapping of region codes to human-readable names
REGION_CODE_NAMES: dict[str, str] = {
    "NA": "North America",
    "EU": "Europe",
    "SEA": "Southeast Asia",
    "Other": "Other",
}

NAME_TO_CODE = {v: k for k, v in REGION_CODE_NAMES.items()}


def get_region_options() -> List[Tuple[str, str]]:
    """Return region code/name pairs in display order."""
    order = ["NA", "EU", "SEA", "Other"]
    return [(code, REGION_CODE_NAMES[code]) for code in order]


def code_to_label(code: str) -> str:
    """Return human-readable region name for a code."""
    return REGION_CODE_NAMES.get(code, code)
