from __future__ import annotations

from .app import db


class Settings(db.Model):
    __tablename__ = "settings"
    id = db.Column(db.Integer, primary_key=True, default=1)
    smtp_host = db.Column(db.String(255))
    smtp_port = db.Column(db.Integer)
    smtp_user = db.Column(db.String(255))
    smtp_from_default = db.Column(db.String(255))
    smtp_from_name = db.Column(db.String(255))
    use_tls = db.Column(db.Boolean, default=True)
    use_ssl = db.Column(db.Boolean, default=False)
    updated_at = db.Column(
        db.DateTime, server_default=db.func.now(), onupdate=db.func.now()
    )

    # always enforce singleton row id=1
    @staticmethod
    def get() -> "Settings | None":
        return db.session.get(Settings, 1)
