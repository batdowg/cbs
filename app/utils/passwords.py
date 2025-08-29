import logging
from passlib.hash import bcrypt

logging.getLogger("passlib.handlers.bcrypt").setLevel(logging.ERROR)


def hash_password(plain: str) -> str:
    """Return bcrypt hash for plain password."""
    return bcrypt.hash(plain)


def check_password(plain: str, hashed: str) -> bool:
    """Verify plain password against hash."""
    if not plain or not hashed:
        return False
    try:
        return bcrypt.verify(plain, hashed)
    except ValueError:
        return False
