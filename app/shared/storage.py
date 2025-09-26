import os
import tempfile
from datetime import date
from typing import Optional


def ensure_dir(path: str) -> None:
    """Create directory if missing (mkdir -p equivalent)."""
    os.makedirs(path, exist_ok=True)


def write_atomic(path: str, data, mode: str = "wb") -> None:
    """Write data to a temporary file then atomically rename to target path."""
    dir_path = os.path.dirname(path)
    ensure_dir(dir_path)
    fd, tmp_path = tempfile.mkstemp(dir=dir_path)
    try:
        with os.fdopen(fd, mode) as f:
            f.write(data)
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def build_badge_public_url(
    session_id: int,
    session_end_date: Optional[date],
    certification_number: Optional[str],
) -> Optional[str]:
    if not certification_number or not session_end_date:
        return None
    return (
        f"/certificates/{session_end_date.year}/{session_id}/{certification_number}.png"
    )


def badge_png_exists(
    session_id: int,
    session_end_date: Optional[date],
    certification_number: Optional[str],
) -> bool:
    if not certification_number or not session_end_date:
        return False
    path = (
        f"/srv/certificates/{session_end_date.year}/{session_id}/{certification_number}.png"
    )
    return os.path.exists(path)
