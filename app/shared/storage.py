import os
import tempfile


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
