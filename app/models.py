from __future__ import annotations

import base64
from flask import current_app

from .app import db


class Settings(db.Model):
    __tablename__ = "settings"
    id = db.Column(db.Integer, primary_key=True, default=1)
    smtp_host = db.Column(db.String(255))
    smtp_port = db.Column(db.Integer)
    smtp_user = db.Column(db.String(255))
    smtp_from_default = db.Column(db.String(255))
    smtp_from_name = db.Column(db.String(255))
    smtp_pass_enc = db.Column(db.Text)
    use_tls = db.Column(db.Boolean, default=True)
    use_ssl = db.Column(db.Boolean, default=False)
    updated_at = db.Column(
        db.DateTime, server_default=db.func.now(), onupdate=db.func.now()
    )

    # always enforce singleton row id=1
    @staticmethod
    def get() -> "Settings | None":
        return db.session.get(Settings, 1)

    def set_smtp_pass(self, plain: str) -> None:
        if not plain:
            self.smtp_pass_enc = None
            return
        key = current_app.config.get("SECRET_KEY", "").encode()
        data = plain.encode()
        xored = bytes([b ^ key[i % len(key)] for i, b in enumerate(data)])
        self.smtp_pass_enc = base64.b64encode(xored).decode()

    def get_smtp_pass(self) -> str | None:
        if not self.smtp_pass_enc:
            return None
        try:
            key = current_app.config.get("SECRET_KEY", "").encode()
            raw = base64.b64decode(self.smtp_pass_enc.encode())
            data = bytes([b ^ key[i % len(key)] for i, b in enumerate(raw)])
            return data.decode()
        except Exception:
            return None
