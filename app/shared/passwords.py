import logging
from passlib.context import CryptContext
from passlib.handlers import bcrypt as passlib_bcrypt

logging.getLogger("passlib.handlers.bcrypt").setLevel(logging.ERROR)

if not getattr(passlib_bcrypt._BcryptBackend, "_cbs_verify_patch", False):
    _orig_backend_verify = passlib_bcrypt._BcryptBackend.verify.__func__

    def _backend_verify_safe(cls, secret, hash, **context):
        try:
            return _orig_backend_verify(cls, secret, hash, **context)
        except ValueError as exc:
            message = str(exc)
            if "password cannot be longer than 72 bytes" in message:
                return False
            raise

    passlib_bcrypt._BcryptBackend.verify = classmethod(_backend_verify_safe)
    passlib_bcrypt._BcryptBackend._cbs_verify_patch = True

passlib_bcrypt._BcryptBackend._workrounds_initialized = True

pwd_ctx = CryptContext(
    schemes=["bcrypt_sha256", "bcrypt"],
    deprecated="auto",
)


def hash_password(plain: str) -> str:
    """Return bcrypt_sha256 hash for plain password."""
    return pwd_ctx.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify plain password against hash."""
    if not plain or not hashed:
        return False
    try:
        return pwd_ctx.verify(plain, hashed)
    except ValueError:
        return False


def check_password(plain: str, hashed: str) -> bool:
    """Backward-compatible alias for verify_password."""
    return verify_password(plain, hashed)
