import os
import tempfile


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def write_atomic(file_path: str, data: bytes) -> None:
    dir_path = os.path.dirname(file_path)
    ensure_dir(dir_path)
    fd, tmp_path = tempfile.mkstemp(dir=dir_path)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
        os.replace(tmp_path, file_path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
